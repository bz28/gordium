using System.Text.Json.Nodes;
using Autodesk.Revit.DB;

namespace Gordium.Revit.Addin;

/// <summary>
/// Draws one conformance scene in a new Revit document, from the suite's own numbers (scene_data.py, from
/// design_checker.conformance), as the runbook's section 4 says and as SceneDrawing.cs draws it in fake records
/// (each feature below has the same meaning there):
/// <list type="bullet">
/// <item>the lot: a property line (an arc where the scene has one; finished open, every piece but the last, where the
/// scene draws it open); a picked lot: the facts' <c>lot_id</c> is the picked property line's UniqueId, and a
/// picked lot the scene doesn't draw (23) is drawn, its UniqueId taken, then deleted;</item>
/// <item>each floor block: a Gordium-marked DirectShape solid carrying "&lt;story&gt;;&lt;height&gt;" (a curved face where the
/// scene has one, an open shell with no floor or roof where it draws it open);</item>
/// <item>a house of parts (18): each part a DirectShape in its building category (a curtain wall's panel and mullions
/// in Curtain Panels and Curtain Wall Mullions; the roof slab a closed mesh), and the built-in an in-place family in
/// Walls, which Revit's API can't create: copied from a source model made once by hand (InPlaceSource), as Copy and
/// Paste does;</item>
/// <item>each other solid: a Generic Model DirectShape (context-marked on Gordium::Context); a terrain mesh: an open
/// mesh DirectShape; each spot grade: a spot-marked DirectShape holding one point;</item>
/// <item>a survey offset: the drawing near Revit's internal origin, the shared coordinates moved by the offset;
/// millimetres: the project's display unit (Revit's points are feet whatever it shows);</item>
/// <item>the edit: each building moved in place (<c>ElementTransformUtils.MoveElement</c>), every UniqueId kept.</item>
/// </list>
/// A scene with something the drawer can't draw yet is refused whole, its reasons named: never drawn partly.
/// </summary>
internal static class SceneDraw
{
    /// <summary>Why a scene can't be drawn yet; empty when it can.</summary>
    internal static List<string> Unsupported(JsonObject scene)
    {
        var why = new List<string>();
        foreach (var (_, data) in scene["steps"]!.AsObject())
            foreach (var s in data!["solids"]!.AsArray())
            {
                if (s!["id"]!.GetValue<string>() == "built_in" && !System.IO.File.Exists(InPlaceSource.SourcePath))
                    why.Add($"built_in: an in-place family, which Revit's API can't create: copied from {InPlaceSource.SourcePath}, " +
                            "made once by hand (InPlaceSource), which isn't there");
            }
        return why.Distinct().ToList();
    }

    /// <summary>What a drawn scene gives back: {Revit UniqueId: the scene's id}, the facts to check it with, and each
    /// building's element by the scene's id (for the edit).</summary>
    internal sealed record Drawn(Dictionary<string, string> Ids, JsonObject Facts, Dictionary<string, ElementId> Buildings);

    /// <summary>Draws the scene's first step in <paramref name="doc"/>.</summary>
    internal static Drawn Draw(Autodesk.Revit.ApplicationServices.Application app, Document doc, JsonObject scene)
    {
        var ids = new Dictionary<string, string>();
        var buildings = new Dictionary<string, ElementId>();
        var facts = scene["facts"]!.DeepClone().AsObject();
        var offset = Offset(scene);
        // the built-in (18): an in-place family, copied from its source model, opened before this drawing's transaction
        var builtIn = scene["steps"]!["as drawn"]!["solids"]!.AsArray().Any(s => s!["id"]!.GetValue<string>() == "built_in");
        if (builtIn && offset.GetLength() > 0)
            throw new InvalidOperationException("the in-place built-in is copied as drawn: a scene with an offset can't have one");
        var source = builtIn ? app.OpenDocumentFile(InPlaceSource.SourcePath) : null;
        try
        {
            return Draw(app, doc, scene, ids, buildings, facts, offset, source);
        }
        finally
        {
            source?.Close(false);
        }
    }

    private static Drawn Draw(Autodesk.Revit.ApplicationServices.Application app, Document doc, JsonObject scene,
                              Dictionary<string, string> ids, Dictionary<string, ElementId> buildings, JsonObject facts,
                              XYZ offset, Document? source)
    {
        using var t = new Transaction(doc, "Gordium: draw conformance scene");
        Warnings.Accept(t);
        t.Start();
        if (offset.GetLength() > 0)       // shared coordinates: internal (0, 0, 0) is the scene's offset
            doc.ActiveProjectLocation.SetProjectPosition(XYZ.Zero, new ProjectPosition(offset.X, offset.Y, offset.Z, 0));
        if (scene["units"]!.GetValue<string>() is { } units && units != "Feet")
        {
            var u = doc.GetUnits();
            u.SetFormatOptions(SpecTypeId.Length, new FormatOptions(units switch
            {
                "Millimeters" => UnitTypeId.Millimeters,
                _ => throw new InvalidOperationException($"display units {units} aren't drawn yet"),
            }));
            doc.SetUnits(u);
        }
        var lots = scene["lots"]!.AsArray();
        var arcs = scene["lot_arcs"]!.AsObject();
        var open = scene["open_lots"]!.AsArray().Select(k => k!.GetValue<int>()).ToHashSet();
        var lotUid = new Dictionary<string, string>();
        for (var k = 0; k < lots.Count; k++)
        {
            var ring = Outline(lots[k]!).Select(p => Shift(p, offset)).ToList();
            var curves = new List<Curve>();
            for (var i = 0; i < (open.Contains(k) ? ring.Count - 1 : ring.Count); i++)
            {
                var (a, b) = (ring[i], ring[(i + 1) % ring.Count]);
                curves.Add(k == 0 && arcs[i.ToString(System.Globalization.CultureInfo.InvariantCulture)] is JsonObject arc
                    ? Arc.Create(Xyz(a, 0), Xyz(b, 0), Xyz(Shift(P(arc["through"]!), offset), 0))
                    : Line.CreateBound(Xyz(a, 0), Xyz(b, 0)));
            }
            var loop = new CurveLoop();
            foreach (var c in curves)
                loop.Append(c);
            var line = PropertyLine.Create(doc, new List<CurveLoop> { loop });
            var id = scene["lot_ids"]![k]!.GetValue<string>();
            ids[line.UniqueId] = id;
            lotUid[id] = line.UniqueId;
        }
        if (scene["picked"] is JsonValue picked)
        {
            var name = picked.GetValue<string>();
            if (!lotUid.TryGetValue(name, out var uid))
            {
                // a picked lot that is no longer there (23): drawn, its id taken, then deleted
                var gone = PropertyLine.Create(doc, new List<CurveLoop> { Loop([(0, 0), (1, 0), (1, 1)], 0, null) });
                uid = gone.UniqueId;
                doc.Delete(gone.Id);
            }
            facts["lot_id"] = uid;
        }
        var inLinks = new Dictionary<string, List<JsonNode>>();
        foreach (var s in scene["steps"]!["as drawn"]!["solids"]!.AsArray())
        {
            if (s!["in_block"] is JsonValue link)
            {
                (inLinks.TryGetValue(link.GetValue<string>(), out var held) ? held : inLinks[link.GetValue<string>()] = []).Add(s);
                continue;
            }
            var name = s["id"]!.GetValue<string>();
            var part = name == "built_in" ? CopyBuiltIn(source!, doc) : Building(doc, s, offset);
            ids[part.UniqueId] = name;
            buildings[name] = part.Id;
        }
        if (scene["group"]!.GetValue<bool>())     // every part in one model group (20): moved together at the edit
            buildings[GroupKey] = doc.Create.NewGroup(buildings.Values.ToList()).Id;
        foreach (var o in scene["others"]!.AsArray())
        {
            var oid = o!["id"]!.GetValue<string>();
            if (o["holds_buildings"]?.GetValue<bool>() == true)
            {
                ids[Link(app, doc, oid, inLinks[oid], offset).UniqueId] = oid;
                continue;
            }
            if (o["empty"]?.GetValue<bool>() == true)
            {
                ids[Place(doc, Family(app, doc, oid, null, null)).UniqueId] = oid;
                continue;
            }
            var outline = Outline(o["outline"]!).Select(p => Shift(p, offset)).ToList();
            double z0 = o["base"]!.GetValue<double>() - offset.Z, z1 = o["top"]!.GetValue<double>() - offset.Z;
            if (o["block"]?.GetValue<bool>() == true)
            {
                // a Generic Models family instance; with nested_empty, a nested family with no geometry beside its solid
                // drawn about the family's own origin and placed at the outline's middle, as real families are made:
                // Revit's box of an instance reaches to its origin, so a solid drawn far from it reads bigger
                var nested = o["nested_empty"]?.GetValue<bool>() == true ? FamilyFile(app, oid + "_part", null, null, shared: true) : null;
                var (cx, cy) = ((outline.Min(q => q.X) + outline.Max(q => q.X)) / 2, (outline.Min(q => q.Y) + outline.Max(q => q.Y)) / 2);
                var local = outline.Select(q => (q.X - cx, q.Y - cy)).ToList();
                ids[Place(doc, Family(app, doc, oid, (local, z0, z1), nested), new XYZ(cx, cy, 0)).UniqueId] = oid;
                continue;
            }
            var context = o["layer"]?.GetValue<string>().StartsWith("Gordium::Context", StringComparison.Ordinal) == true;
            var ds = o["mesh"] is JsonObject mesh
                ? Grid(doc, outline, z0, mesh["cells"]!.GetValue<int>())
                : Prism(doc, outline, z0, z1, context ? RevitRead.ContextMark : null);
            ids[ds.UniqueId] = oid;
        }
        foreach (var p in scene["spots"]!.AsArray())
        {
            var ds = DirectShape.CreateElement(doc, new ElementId(BuiltInCategory.OST_GenericModel));
            ds.ApplicationId = RevitRead.MarkApplication;
            ds.ApplicationDataId = RevitRead.SpotMark;
            ds.SetShape(new List<GeometryObject> { Autodesk.Revit.DB.Point.Create(new XYZ(p![0]!.GetValue<double>() - offset.X,
                p[1]!.GetValue<double>() - offset.Y, p[2]!.GetValue<double>() - offset.Z)) });
        }
        if (t.Commit() != TransactionStatus.Committed)
            throw new InvalidOperationException("Revit didn't commit the scene's drawing");
        return new Drawn(ids, facts, buildings);
    }

    /// <summary>The edit (scenes 07, 12): each building moved to where the step draws it, by moving the element (never
    /// redrawn), so every UniqueId stays.</summary>
    internal static void Edit(Document doc, JsonObject scene, string step, Drawn drawn)
    {
        var before = scene["steps"]!["as drawn"]!["solids"]!.AsArray().ToDictionary(s => s!["id"]!.GetValue<string>());
        using var t = new Transaction(doc, "Gordium: the scene's edit");
        Warnings.Accept(t);
        t.Start();
        foreach (var s in scene["steps"]![step]!["solids"]!.AsArray())
        {
            var name = s!["id"]!.GetValue<string>();
            var (a, b) = (P(before[name]!["outline"]![0]!), P(s["outline"]![0]!));
            var dz = s["base"]!.GetValue<double>() - before[name]!["base"]!.GetValue<double>();
            if (drawn.Buildings.TryGetValue(GroupKey, out var group))
            {
                ElementTransformUtils.MoveElement(doc, group, new XYZ(b.X - a.X, b.Y - a.Y, dz));   // the group, once
                break;
            }
            ElementTransformUtils.MoveElement(doc, drawn.Buildings[name], new XYZ(b.X - a.X, b.Y - a.Y, dz));
        }
        if (t.Commit() != TransactionStatus.Committed)
            throw new InvalidOperationException("Revit didn't commit the scene's edit");
    }

    private const string GroupKey = "\u0000group";

    /// <summary>One of the scene's buildings: a marked floor block (a curved face, or an open shell, where the scene
    /// has one); a part of a house of parts in its building category (as SceneDrawing.PartOf: the slabs Floors and
    /// Roofs, the window Windows, the rest Walls; DirectShapes in those categories, not native walls, slabs, a window family or
    /// a curtain wall: the reading design note's section 8 says so, and keeps native elements open); a block on the Building layer (04): a Walls element holding only a line, which the
    /// reader can't send as a solid.</summary>
    private static DirectShape Building(Document doc, JsonNode s, XYZ offset)
    {
        var name = s["id"]!.GetValue<string>();
        var outline = Outline(s["outline"]!).Select(p => Shift(p, offset)).ToList();
        double z0 = s["base"]!.GetValue<double>() - offset.Z, z1 = s["top"]!.GetValue<double>() - offset.Z;
        if (s["block"]!.GetValue<bool>())
            return Shape(doc, [Line.CreateBound(Xyz(outline[0], z0), Xyz(outline[2], z1))], null, BuiltInCategory.OST_Walls);
        if (s["floor"] is not JsonValue floor)
        {
            var category = name switch
            {
                "floor_slab" => BuiltInCategory.OST_Floors,
                "roof_slab" => BuiltInCategory.OST_Roofs,
                "window" => BuiltInCategory.OST_Windows,
                "curtain_panel" => BuiltInCategory.OST_CurtainWallPanels,
                _ when name.StartsWith("mullion_", StringComparison.Ordinal) => BuiltInCategory.OST_CurtainWallMullions,
                _ => BuiltInCategory.OST_Walls,
            };
            return s["mesh"]!.GetValue<bool>()
                ? Shape(doc, ClosedMesh(outline, z0, z1), null, category)
                : Shape(doc, [Solid(outline, z0, z1, null, null)], null, category);
        }
        var mark = $"{RevitRead.FloorPrefix}{name.Split("floor")[^1]};{Num(floor.GetValue<double>())}";
        var curved = s["curved"] as JsonObject;
        return s["open"]!.GetValue<bool>()
            ? OpenPrism(doc, outline, z0, z1, mark)
            : Prism(doc, outline, z0, z1, mark, curved?["edge"]!.GetValue<int>(),
                    curved is null ? null : Shift(P(curved["through"]!), offset));
    }

    /// <summary>A family file built from Revit's Generic Model template: one solid (a vertical prism), or none; with a
    /// nested family (another such file) placed inside it.</summary>
    private static string FamilyFile(Autodesk.Revit.ApplicationServices.Application app, string name,
                                     (List<(double X, double Y)> Outline, double Z0, double Z1)? prism, string? nested,
                                     bool shared = false)
    {
        var templates = app.FamilyTemplatePath;
        var template = new[]
        {
            System.IO.Path.Combine(templates, "Generic Model.rft"),
            System.IO.Path.Combine(templates, "English-Imperial", "Generic Model.rft"),
            System.IO.Path.Combine(templates, "English", "Metric Generic Model.rft"),
            System.IO.Path.Combine(templates, "..", "English-Imperial", "Generic Model.rft"),
            System.IO.Path.Combine(templates, "Metric Generic Model.rft"),
        }.FirstOrDefault(System.IO.File.Exists) ?? throw new InvalidOperationException($"no Generic Model template under {templates}");
        var fam = app.NewFamilyDocument(template);
        try
        {
            using (var t = new Transaction(fam, "Gordium: scene family"))
            {
                t.Start();
                // a shared family stays its own instance when nested (Revit hands it back as a nested
                // GeometryInstance); a family not shared is merged into its host's geometry (seen in the trial,
                // 2026-11-19: an empty one came back as an empty solid inside the host's)
                if (shared)
                    fam.OwnerFamily.get_Parameter(BuiltInParameter.FAMILY_SHARED).Set(1);
                if (prism is { } p)
                {
                    var profile = new CurveArrArray();
                    var loop = new CurveArray();
                    for (var i = 0; i < p.Outline.Count; i++)
                        loop.Append(Line.CreateBound(Xyz(p.Outline[i], p.Z0), Xyz(p.Outline[(i + 1) % p.Outline.Count], p.Z0)));
                    profile.Append(loop);
                    var plane = SketchPlane.Create(fam, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, new XYZ(0, 0, p.Z0)));
                    fam.FamilyCreate.NewExtrusion(true, profile, plane, p.Z1 - p.Z0);
                }
                if (nested is not null)
                {
                    fam.LoadFamily(nested, out var inner);
                    var symbol = (FamilySymbol)fam.GetElement(inner.GetFamilySymbolIds().First());
                    symbol.Activate();
                    fam.FamilyCreate.NewFamilyInstance(XYZ.Zero, symbol, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);
                }
                t.Commit();
            }
            var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"gordium_{name}_{Guid.NewGuid():N}.rfa");
            fam.SaveAs(path);
            return path;
        }
        finally
        {
            fam.Close(false);
        }
    }

    private static FamilySymbol Family(Autodesk.Revit.ApplicationServices.Application app, Document doc, string name,
                                       (List<(double X, double Y)> Outline, double Z0, double Z1)? prism, string? nested)
    {
        doc.LoadFamily(FamilyFile(app, name, prism, nested), out var family);
        var symbol = (FamilySymbol)doc.GetElement(family.GetFamilySymbolIds().First());
        symbol.Activate();
        return symbol;
    }

    /// <summary>A family placed at <paramref name="at"/> (the origin when not given).</summary>
    private static FamilyInstance Place(Document doc, FamilySymbol symbol, XYZ? at = null) =>
        doc.Create.NewFamilyInstance(at ?? XYZ.Zero, symbol, Autodesk.Revit.DB.Structure.StructuralType.NonStructural);

    /// <summary>A linked Revit model holding the scene's buildings (19): another project, its floor blocks drawn, saved
    /// to a temporary file and linked, origin to origin.</summary>
    private static RevitLinkInstance Link(Autodesk.Revit.ApplicationServices.Application app, Document doc, string name,
                                          List<JsonNode> solids, XYZ offset)
    {
        var linked = app.NewProjectDocument(UnitSystem.Imperial);
        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"gordium_{name}_{Guid.NewGuid():N}.rvt");
        try
        {
            using (var t = new Transaction(linked, "Gordium: the linked model"))
            {
                t.Start();
                foreach (var s in solids)
                    Building(linked, s, offset);
                t.Commit();
            }
            linked.SaveAs(path);
        }
        finally
        {
            linked.Close(false);
        }
        var type = RevitLinkType.Create(doc, ModelPathUtils.ConvertUserVisiblePathToModelPath(path), new RevitLinkOptions(false));
        return RevitLinkInstance.Create(doc, type.ElementId);
    }

    private static Solid Solid(List<(double X, double Y)> outline, double z0, double z1, int? curvedEdge,
                               (double X, double Y)? through) =>
        GeometryCreationUtilities.CreateExtrusionGeometry([Loop(outline, z0, curvedEdge, through)], XYZ.BasisZ, z1 - z0);

    private static DirectShape Shape(Document doc, IList<GeometryObject> geometry, string? mark,
                                     BuiltInCategory category = BuiltInCategory.OST_GenericModel)
    {
        var ds = DirectShape.CreateElement(doc, new ElementId(category));
        if (mark is not null)
        {
            ds.ApplicationId = RevitRead.MarkApplication;
            ds.ApplicationDataId = mark;
        }
        ds.SetShape(geometry);
        return ds;
    }

    /// <summary>A vertical prism; its edge <paramref name="curvedEdge"/> an arc through <paramref name="through"/>.</summary>
    private static DirectShape Prism(Document doc, List<(double X, double Y)> outline, double z0, double z1, string? mark,
                                     int? curvedEdge = null, (double X, double Y)? through = null) =>
        Shape(doc, [GeometryCreationUtilities.CreateExtrusionGeometry([Loop(outline, z0, curvedEdge, through)], XYZ.BasisZ, z1 - z0)], mark);

    /// <summary>A prism's walls only, no floor or roof: an open shell (<c>BRepBuilder</c>, <c>BRepType.OpenShell</c>),
    /// so its top and bottom edges each have one face (scene 03, "an open solid").</summary>
    private static DirectShape OpenPrism(Document doc, List<(double X, double Y)> outline, double z0, double z1, string mark)
    {
        var b = new BRepBuilder(BRepType.OpenShell);
        var n = outline.Count;
        var bottom = new BRepBuilderGeometryId[n];
        var top = new BRepBuilderGeometryId[n];
        var vertical = new BRepBuilderGeometryId[n];
        for (var i = 0; i < n; i++)
        {
            var (p, q) = (outline[i], outline[(i + 1) % n]);
            bottom[i] = b.AddEdge(BRepBuilderEdgeGeometry.Create(Xyz(p, z0), Xyz(q, z0)));
            top[i] = b.AddEdge(BRepBuilderEdgeGeometry.Create(Xyz(p, z1), Xyz(q, z1)));
            vertical[i] = b.AddEdge(BRepBuilderEdgeGeometry.Create(Xyz(p, z0), Xyz(p, z1)));
        }
        for (var i = 0; i < n; i++)
        {
            var (p, q) = (outline[i], outline[(i + 1) % n]);
            var along = (Xyz(q, z0) - Xyz(p, z0)).Normalize();
            var plane = Plane.CreateByOriginAndBasis(Xyz(p, z0), along, XYZ.BasisZ);
            var width = Xyz(p, z0).DistanceTo(Xyz(q, z0));
            var face = b.AddFace(BRepBuilderSurfaceGeometry.Create(plane, new BoundingBoxUV(0, 0, width, z1 - z0)), false);
            var loop = b.AddLoop(face);
            b.AddCoEdge(loop, bottom[i], false);           // p -> q along the floor
            b.AddCoEdge(loop, vertical[(i + 1) % n], false); // up at q
            b.AddCoEdge(loop, top[i], true);               // q -> p along the top
            b.AddCoEdge(loop, vertical[i], true);          // down at p
            b.FinishLoop(loop);
            b.FinishFace(face);
        }
        if (b.Finish() != BRepBuilderOutcome.Success)
            throw new InvalidOperationException("Revit didn't build the open shell");
        return Shape(doc, [b.GetResult()], mark);
    }

    /// <summary>The in-place built-in (18), copied from its source model where it was made by hand, in place (the
    /// source draws it at the scene's own coordinates); checked to be the one in-place family there, in Walls.</summary>
    private static Element CopyBuiltIn(Document source, Document doc)
    {
        var made = new FilteredElementCollector(source).OfClass(typeof(FamilyInstance)).Cast<FamilyInstance>()
            .Where(f => f.Symbol.Family.IsInPlace).ToList();
        if (made.Count != 1 || made[0].Category?.BuiltInCategory != BuiltInCategory.OST_Walls)
            throw new InvalidOperationException($"{InPlaceSource.SourcePath} should hold one in-place family, in Walls");
        // both models come from the same template, so their types share names: Revit asks about each in a dialog
        // ("the following types already exist") unless told to keep the scene model's own (trial, 2026-11-19)
        var options = new CopyPasteOptions();
        options.SetDuplicateTypeNamesHandler(new KeepDestinationTypes());
        var copied = ElementTransformUtils.CopyElements(source, [made[0].Id], doc, Transform.Identity, options);
        return copied.Select(doc.GetElement).Single(e => e is FamilyInstance);
    }

    /// <summary>A vertical prism as a closed mesh of triangles (a roof slab "meshed", 18): two triangles a face, every
    /// edge shared by two triangles, wound outward.</summary>
    private static IList<GeometryObject> ClosedMesh(List<(double X, double Y)> outline, double z0, double z1)
    {
        if (outline.Count != 4)
            throw new InvalidOperationException("a closed mesh is drawn for a four-cornered outline only");
        // Fallback Abort threw InternalException from Build (trial, 2026-11-19), as for the terrain mesh: Salvage, and
        // the outcome checked below, so nothing but a mesh is drawn
        var b = new TessellatedShapeBuilder { Target = TessellatedShapeBuilderTarget.Mesh, Fallback = TessellatedShapeBuilderFallback.Salvage };
        b.OpenConnectedFaceSet(true);
        void Quad(XYZ a, XYZ c, XYZ d, XYZ e)
        {
            b.AddFace(new TessellatedFace(new List<XYZ> { a, c, d }, ElementId.InvalidElementId));
            b.AddFace(new TessellatedFace(new List<XYZ> { a, d, e }, ElementId.InvalidElementId));
        }
        // counter-clockwise in plan (as the scenes draw): the roof seen from above, the floor from below
        var lo = outline.Select(p => Xyz(p, z0)).ToList();
        var hi = outline.Select(p => Xyz(p, z1)).ToList();
        Quad(hi[0], hi[1], hi[2], hi[3]);
        Quad(lo[0], lo[3], lo[2], lo[1]);
        for (var i = 0; i < 4; i++)
        {
            var j = (i + 1) % 4;
            Quad(lo[i], lo[j], hi[j], hi[i]);
        }
        b.CloseConnectedFaceSet();
        b.Build();
        var built = b.GetBuildResult();
        var got = built.GetGeometricalObjects();
        if (built.Outcome != TessellatedShapeBuilderOutcome.Mesh || got.Count != 1 || got[0] is not Mesh m || m.NumTriangles != 12)
            throw new InvalidOperationException($"the closed mesh came back as {built.Outcome}, not one mesh of 12 triangles");
        return got;
    }

    /// <summary>A flat open mesh over the outline's plan box at height z, cells × cells squares (two triangles each),
    /// as FakeRevit.Grid: the terrain the architect hasn't picked (scene 16).</summary>
    private static DirectShape Grid(Document doc, List<(double X, double Y)> outline, double z, int cells)
    {
        double x0 = outline.Min(p => p.X), x1 = outline.Max(p => p.X), y0 = outline.Min(p => p.Y), y1 = outline.Max(p => p.Y);
        XYZ V(int i, int j) => new(x0 + (x1 - x0) * i / cells, y0 + (y1 - y0) * j / cells, z);
        var b = new TessellatedShapeBuilder { Target = TessellatedShapeBuilderTarget.Mesh, Fallback = TessellatedShapeBuilderFallback.Salvage };
        b.OpenConnectedFaceSet(false);
        for (var j = 0; j < cells; j++)
            for (var i = 0; i < cells; i++)
            {
                b.AddFace(new TessellatedFace(new List<XYZ> { V(i, j), V(i + 1, j), V(i + 1, j + 1) }, ElementId.InvalidElementId));
                b.AddFace(new TessellatedFace(new List<XYZ> { V(i, j), V(i + 1, j + 1), V(i, j + 1) }, ElementId.InvalidElementId));
            }
        b.CloseConnectedFaceSet();
        b.Build();
        // Salvage may give back less than was asked for: only the whole mesh is drawn (review round 1)
        var built = b.GetBuildResult();
        var got = built.GetGeometricalObjects();
        if (built.Outcome != TessellatedShapeBuilderOutcome.Mesh || got.Count != 1 || got[0] is not Mesh m
            || m.NumTriangles != 2 * cells * cells)
            throw new InvalidOperationException($"the terrain mesh came back as {built.Outcome}, not one mesh of {2 * cells * cells} triangles");
        return Shape(doc, got, null);
    }

    private static CurveLoop Loop(List<(double X, double Y)> ring, double z, int? curvedEdge, (double X, double Y)? through = null)
    {
        var loop = new CurveLoop();
        for (var i = 0; i < ring.Count; i++)
        {
            var (a, b) = (ring[i], ring[(i + 1) % ring.Count]);
            loop.Append(i == curvedEdge
                ? Arc.Create(Xyz(a, z), Xyz(b, z), Xyz(through!.Value, z))
                : Line.CreateBound(Xyz(a, z), Xyz(b, z)));
        }
        return loop;
    }

    private static XYZ Offset(JsonObject scene)
    {
        var o = scene["offset"]!.AsArray().Select(v => v!.GetValue<double>()).ToArray();
        return new XYZ(o[0], o[1], o[2]);
    }

    private static (double X, double Y) Shift((double X, double Y) p, XYZ offset) => (p.X - offset.X, p.Y - offset.Y);

    private static XYZ Xyz((double X, double Y) p, double z) => new(p.X, p.Y, z);

    private static (double X, double Y) P(JsonNode p) => (p[0]!.GetValue<double>(), p[1]!.GetValue<double>());

    private static List<(double X, double Y)> Outline(JsonNode o) => o.AsArray().Select(p => P(p!)).ToList();

    private static string Num(double v) => v.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
}

/// <summary>Copying between models: a type the scene model already has by name is kept, never asked about.</summary>
internal sealed class KeepDestinationTypes : IDuplicateTypeNamesHandler
{
    public DuplicateTypeAction OnDuplicateTypeNamesFound(DuplicateTypeNamesHandlerArgs args) => DuplicateTypeAction.UseDestinationTypes;
}

/// <summary>A scene is drawn as the suite asks, including what Revit only warns about (an open property line, scene
/// 24: "Property lines do not form a closed loop"): its warnings are accepted without a dialog. An error still stops
/// the transaction, so nothing Revit refuses is drawn.</summary>
internal sealed class Warnings : IFailuresPreprocessor
{
    internal static void Accept(Transaction t)
    {
        var options = t.GetFailureHandlingOptions();
        options.SetFailuresPreprocessor(new Warnings());
        t.SetFailureHandlingOptions(options);
    }

    public FailureProcessingResult PreprocessFailures(FailuresAccessor failures)
    {
        foreach (var f in failures.GetFailureMessages())
            if (f.GetSeverity() == FailureSeverity.Warning)
                failures.DeleteWarning(f);
        return FailureProcessingResult.Continue;
    }
}
