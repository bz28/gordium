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
        if (scene["group"]!.GetValue<bool>())
            why.Add("a model group");
        foreach (var (_, data) in scene["steps"]!.AsObject())
            foreach (var s in data!["solids"]!.AsArray())
            {
                if (s!["floor"] is not JsonValue)
                    why.Add($"{s["id"]}: a building that isn't a floor block (native walls, slabs, families)");
                if (s["mesh"]!.GetValue<bool>() || s["block"]!.GetValue<bool>() || s["in_block"] is JsonValue)
                    why.Add($"{s["id"]}: a mesh, a block or a linked model");
            }
        foreach (var o in scene["others"]!.AsArray())
            if (o!["block"]?.GetValue<bool>() == true || o["empty"]?.GetValue<bool>() == true
                || o["nested_empty"]?.GetValue<bool>() == true || o["holds_buildings"]?.GetValue<bool>() == true)
                why.Add($"{o["id"]}: a family or a linked model");
        return why.Distinct().ToList();
    }

    /// <summary>What a drawn scene gives back: {Revit UniqueId: the scene's id}, the facts to check it with, and each
    /// building's element by the scene's id (for the edit).</summary>
    internal sealed record Drawn(Dictionary<string, string> Ids, JsonObject Facts, Dictionary<string, ElementId> Buildings);

    /// <summary>Draws the scene's first step in <paramref name="doc"/>.</summary>
    internal static Drawn Draw(Document doc, JsonObject scene)
    {
        var ids = new Dictionary<string, string>();
        var buildings = new Dictionary<string, ElementId>();
        var facts = scene["facts"]!.DeepClone().AsObject();
        var offset = Offset(scene);
        using var t = new Transaction(doc, "Gordium: draw conformance scene");
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
        foreach (var s in scene["steps"]!["as drawn"]!["solids"]!.AsArray())
        {
            var name = s!["id"]!.GetValue<string>();
            var story = name.Split("floor")[^1];
            var mark = $"{RevitRead.FloorPrefix}{story};{Num(s["floor"]!.GetValue<double>())}";
            var outline = Outline(s["outline"]!).Select(p => Shift(p, offset)).ToList();
            double z0 = s["base"]!.GetValue<double>() - offset.Z, z1 = s["top"]!.GetValue<double>() - offset.Z;
            var curved = s["curved"] as JsonObject;
            var ds = s["open"]!.GetValue<bool>()
                ? OpenPrism(doc, outline, z0, z1, mark)
                : Prism(doc, outline, z0, z1, mark, curved?["edge"]!.GetValue<int>(),
                        curved is null ? null : Shift(P(curved["through"]!), offset));
            ids[ds.UniqueId] = name;
            buildings[name] = ds.Id;
        }
        foreach (var o in scene["others"]!.AsArray())
        {
            var outline = Outline(o!["outline"]!).Select(p => Shift(p, offset)).ToList();
            double z0 = o["base"]!.GetValue<double>() - offset.Z, z1 = o["top"]!.GetValue<double>() - offset.Z;
            var context = o["layer"]?.GetValue<string>().StartsWith("Gordium::Context", StringComparison.Ordinal) == true;
            var ds = o["mesh"] is JsonObject mesh
                ? Grid(doc, outline, z0, mesh["cells"]!.GetValue<int>())
                : Prism(doc, outline, z0, z1, context ? RevitRead.ContextMark : null);
            ids[ds.UniqueId] = o["id"]!.GetValue<string>();
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
        t.Start();
        foreach (var s in scene["steps"]![step]!["solids"]!.AsArray())
        {
            var name = s!["id"]!.GetValue<string>();
            var (a, b) = (P(before[name]!["outline"]![0]!), P(s["outline"]![0]!));
            var dz = s["base"]!.GetValue<double>() - before[name]!["base"]!.GetValue<double>();
            ElementTransformUtils.MoveElement(doc, drawn.Buildings[name], new XYZ(b.X - a.X, b.Y - a.Y, dz));
        }
        if (t.Commit() != TransactionStatus.Committed)
            throw new InvalidOperationException("Revit didn't commit the scene's edit");
    }

    private static DirectShape Shape(Document doc, IList<GeometryObject> geometry, string? mark)
    {
        var ds = DirectShape.CreateElement(doc, new ElementId(BuiltInCategory.OST_GenericModel));
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

    /// <summary>A flat open mesh over the outline's plan box at height z, cells × cells squares (two triangles each),
    /// as FakeRevit.Grid: the terrain the architect hasn't picked (scene 16).</summary>
    private static DirectShape Grid(Document doc, List<(double X, double Y)> outline, double z, int cells)
    {
        double x0 = outline.Min(p => p.X), x1 = outline.Max(p => p.X), y0 = outline.Min(p => p.Y), y1 = outline.Max(p => p.Y);
        XYZ V(int i, int j) => new(x0 + (x1 - x0) * i / cells, y0 + (y1 - y0) * j / cells, z);
        var b = new TessellatedShapeBuilder { Target = TessellatedShapeBuilderTarget.Mesh, Fallback = TessellatedShapeBuilderFallback.Abort };
        b.OpenConnectedFaceSet(false);
        for (var j = 0; j < cells; j++)
            for (var i = 0; i < cells; i++)
            {
                b.AddFace(new TessellatedFace(new List<XYZ> { V(i, j), V(i + 1, j), V(i + 1, j + 1) }, ElementId.InvalidElementId));
                b.AddFace(new TessellatedFace(new List<XYZ> { V(i, j), V(i + 1, j + 1), V(i, j + 1) }, ElementId.InvalidElementId));
            }
        b.CloseConnectedFaceSet();
        b.Build();
        return Shape(doc, b.GetBuildResult().GetGeometricalObjects(), null);
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
