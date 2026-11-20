using System.Globalization;
using System.IO;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.Structure;
using Gordium.Revit.Reading;
using RevitApplication = Autodesk.Revit.ApplicationServices.Application;

namespace Gordium.Revit.Addin;

/// <summary>
/// Draws a hand-worked house (test_data/interior_houses/) in a new Revit project from its own data, as the interior
/// design note's section 6 asks: the drawing's numbers come from <c>python -m model_measurement.interior.recordings
/// draw</c>, never retyped. Each level gets its exterior walls (their inside faces on the rooms' outline), a floor slab
/// whose top is the level, a wall filling any gap between rooms, a room separation line wherever two rooms meet, and a
/// Room in each room, named as the house names it and marked Sleeping room Yes or No. Each room's ceiling is a thin
/// solid (a DirectShape in Ceilings) whose underside is the house's ceiling. Each window is a window family of its own
/// (made from Revit's Window.rft, which cuts the wall: a frame solid of the window's size in the middle of the wall),
/// in an outside wall of its room at its sill height, marked Escape opening Yes or No, its type's Operation set, and,
/// on an escape window, the maker's clear opening (what the measuring code works out from the house's frame and sash)
/// with its Clear offset above the sill line, confirmed with Gordium's stamp as the architect's tick would be. Stairs,
/// doors and guards are later steps: not drawn. What it can't draw is an error, never a house drawn differently.
/// </summary>
internal static class HouseDraw
{
    /// <summary>Who the confirmation stamp names: the trial's drawing, never an architect.</summary>
    internal const string StampedBy = "Gordium add-in, Record houses (the trial's drawing of a hand-worked house)";

    private static double D(JsonNode? n) => n!.GetValue<double>();

    private static (double X, double Y) P(JsonNode n) => (D(n[0]), D(n[1]));

    /// <summary>Draws the house; gives the house's ids to the Revit elements' <c>UniqueId</c>s.</summary>
    internal static Dictionary<string, string> Draw(RevitApplication app, Document doc, JsonObject house, List<string> words)
    {
        var plan = MarkSetup.Plan(RevitMarks.Bindings(doc));
        if (plan.FirstOrDefault(s => s.Action == MarkSetupAction.Conflict) is { } conflict)
            throw new InvalidOperationException($"{conflict.Mark.Name}: {conflict.Words}");
        RevitMarks.AddMarks(doc, app, plan);

        var windows = house["windows"]!.AsArray().Select(n => n!.AsObject()).ToList();
        var families = windows.ToDictionary(w => w["id"]!.GetValue<string>(), w => WindowFamily(app, doc, w, words));

        var ids = new Dictionary<string, string>();
        var wallThickness = D(house["exterior_wall"]);
        using var t = new Transaction(doc, "Gordium: draw a hand-worked house");
        t.Start();
        var levels = new Dictionary<double, Level>();
        var walls = new Dictionary<string, Wall>();
        var floorPlan = new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType)).Cast<ViewFamilyType>()
            .FirstOrDefault(v => v.ViewFamily == ViewFamily.FloorPlan)
            ?? throw new InvalidOperationException("no floor plan view type in a new project");
        var floorType = new FilteredElementCollector(doc).OfClass(typeof(FloorType)).Cast<FloorType>()
            .FirstOrDefault(f => !f.IsFoundationSlab) ?? throw new InvalidOperationException("no floor type in a new project");
        foreach (var level in house["levels"]!.AsArray().Select(n => n!.AsObject()))
        {
            var z = D(level["elevation"]);
            var lv = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                .FirstOrDefault(l => Math.Abs(l.ProjectElevation - z) < 1e-9) ?? Level.Create(doc, z);
            // room outlines are worked out 2 ft up, under the 4 ft knee wall's ceiling (house 2's Bedroom 4)
            lv.get_Parameter(BuiltInParameter.LEVEL_ROOM_COMPUTATION_HEIGHT)?.Set(2.0);
            levels[z] = lv;
            var view = ViewPlan.Create(doc, floorPlan.Id, lv.Id);
            var (x0, y0) = P(level["box"]![0]!);
            var (x1, y1) = P(level["box"]![1]!);
            var height = D(level["wall_height"]);
            var h = wallThickness / 2;
            var exterior = WallTypeOf(doc, wallThickness);
            var corners = new[] { new XYZ(x0 - h, y0 - h, z), new XYZ(x1 + h, y0 - h, z), new XYZ(x1 + h, y1 + h, z), new XYZ(x0 - h, y1 + h, z) };
            var sides = new[] { "ymin", "xmax", "ymax", "xmin" };
            for (var i = 0; i < 4; i++)
                walls[$"{z.ToString(CultureInfo.InvariantCulture)}-{sides[i]}"] =
                    Wall.Create(doc, Line.CreateBound(corners[i], corners[(i + 1) % 4]), exterior.Id, lv.Id, height, 0, false, false);
            Floor.Create(doc, [Rectangle(x0 - wallThickness, y0 - wallThickness, x1 + wallThickness, y1 + wallThickness, z)], floorType.Id, lv.Id);
            foreach (var f in level["fillers"]!.AsArray())
            {
                var (fx0, fy0) = P(f![0]!);
                var (fx1, fy1) = P(f[1]!);
                var alongX = fx1 - fx0 >= fy1 - fy0;
                var thick = alongX ? fy1 - fy0 : fx1 - fx0;
                var line = alongX
                    ? Line.CreateBound(new XYZ(fx0, (fy0 + fy1) / 2, z), new XYZ(fx1, (fy0 + fy1) / 2, z))
                    : Line.CreateBound(new XYZ((fx0 + fx1) / 2, fy0, z), new XYZ((fx0 + fx1) / 2, fy1, z));
                Wall.Create(doc, line, WallTypeOf(doc, thick).Id, lv.Id, height, 0, false, false);
            }
            var separations = level["separations"]!.AsArray();
            if (separations.Count > 0)
            {
                var curves = new CurveArray();
                foreach (var s in separations)
                {
                    var (sx0, sy0) = P(s![0]!);
                    var (sx1, sy1) = P(s[1]!);
                    curves.Append(Line.CreateBound(new XYZ(sx0, sy0, z), new XYZ(sx1, sy1, z)));
                }
                doc.Create.NewRoomBoundaryLines(SketchPlane.Create(doc, lv.Id), curves, view);
            }
        }
        var thickness = D(house["ceiling_thickness"]);
        var ceilings = new ElementId(DirectShape.IsValidCategoryId(new ElementId(BuiltInCategory.OST_Ceilings), doc)
            ? BuiltInCategory.OST_Ceilings : BuiltInCategory.OST_GenericModel);
        foreach (var room in house["rooms"]!.AsArray().Select(n => n!.AsObject()))
        {
            var shape = DirectShape.CreateElement(doc, ceilings);
            shape.Name = "Ceiling of " + room["name"]!.GetValue<string>();
            var solids = new List<GeometryObject>();
            foreach (var piece in room["ceilings"]!.AsArray())
            {
                var pts = piece!.AsArray().Select(p => new XYZ(D(p![0]), D(p[1]), D(p[2]))).ToList();
                var loop = new CurveLoop();
                for (var i = 0; i < pts.Count; i++)
                    loop.Append(Line.CreateBound(pts[i], pts[(i + 1) % pts.Count]));
                solids.Add(GeometryCreationUtilities.CreateExtrusionGeometry([loop], XYZ.BasisZ, thickness));
            }
            shape.SetShape(solids);
        }
        doc.Regenerate();
        // the walls, slabs and ceilings committed and regenerated before any window is placed in them (trial run 5,
        // 2026-11-20: windows placed in the walls' own transaction were hosted but never inserts, the walls uncut)
        t.Commit();
        using var t2 = new Transaction(doc, "Gordium: place the windows and Rooms");
        t2.Start();

        foreach (var w in windows)
        {
            var id = w["id"]!.GetValue<string>();
            var z = D(w["level"]);
            var (cx, cy) = P(w["center"]!);
            var (ox, oy) = P(w["outward"]!);
            var side = oy < 0 ? "ymin" : ox < 0 ? "xmin" : oy > 0 ? "ymax" : "xmax";
            var wall = walls[$"{z.ToString(CultureInfo.InvariantCulture)}-{side}"];
            var symbol = families[id];
            if (!symbol.IsActive)
                symbol.Activate();
            var at = new XYZ(cx + ox * wallThickness / 2, cy + oy * wallThickness / 2, z);
            var fi = doc.Create.NewFamilyInstance(at, symbol, wall, levels[z], StructuralType.NonStructural);
            Set(fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM), D(w["sill"]), "Sill Height");
            doc.Regenerate();
            words.Add($"window {id} just placed and regenerated: its wall's inserts {wall.FindInserts(true, true, true, true).Count}, " +
                      $"this window among them {wall.FindInserts(true, true, true, true).Contains(fi.Id)}");
            Set(fi.get_Parameter(Marks.EscapeOpening.Guid), w["escape"]!.GetValue<bool>() ? 1 : 0, Marks.EscapeOpening.Name);
            fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set(w["name"]!.GetValue<string>());
            var word = Operations.Words.First(x => Operations.ForOpening(x) == w["operation"]!.GetValue<string>());
            Set(symbol.get_Parameter(Marks.Operation.Guid), word, Marks.Operation.Name);
            if (w["clear"] is JsonObject c)
            {
                Set(symbol.get_Parameter(Marks.ClearWidth.Guid), D(c["width"]), Marks.ClearWidth.Name);
                Set(symbol.get_Parameter(Marks.ClearHeight.Guid), D(c["height"]), Marks.ClearHeight.Name);
                Set(symbol.get_Parameter(Marks.ClearOffset.Guid), D(c["offset"]), Marks.ClearOffset.Name);
                Set(symbol.get_Parameter(Marks.ClearSource.Guid), c["source"]!.GetValue<string>(), Marks.ClearSource.Name);
            }
            ids[id] = fi.UniqueId;
        }
        doc.Regenerate();
        // the stamp, from the type's values as Revit now gives them (read the way the reader reads them)
        foreach (var w in windows.Where(w => w["clear"] is JsonObject))
        {
            var symbol = families[w["id"]!.GetValue<string>()];
            var (width, height) = RevitInterior.TypeSize(symbol);
            var values = new ClearValues(symbol.UniqueId, width, height, symbol.get_Parameter(Marks.Operation.Guid)?.AsString()?.Trim(),
                                         Length(symbol, Marks.ClearWidth), Length(symbol, Marks.ClearHeight), Length(symbol, Marks.ClearOffset),
                                         symbol.get_Parameter(Marks.ClearSource.Guid)?.AsString()?.Trim());
            Set(symbol.get_Parameter(Marks.ClearConfirmed.Guid),
                ClearStamp.Make(values, StampedBy, DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)),
                Marks.ClearConfirmed.Name);
        }

        foreach (var room in house["rooms"]!.AsArray().Select(n => n!.AsObject()))
        {
            var floor = room["floor"]!.AsArray().Select(p => P(p!)).ToList();
            var inside = new UV(floor.Average(p => p.X), floor.Average(p => p.Y));
            var r = doc.Create.NewRoom(levels[D(room["floor_elevation"])], inside)
                    ?? throw new InvalidOperationException($"Revit placed no Room in {room["id"]}");
            r.Name = room["name"]!.GetValue<string>();
            Set(r.get_Parameter(Marks.SleepingRoom.Guid), room["sleeping"]!.GetValue<bool>() ? 1 : 0, Marks.SleepingRoom.Name);
            ids[room["id"]!.GetValue<string>()] = r.UniqueId;
        }
        t2.Commit();
        // after the commit, regenerated again: each window's placement and whether its wall knows it as an insert
        using (var again = new Transaction(doc, "Gordium: regenerate (rolled back)"))
        {
            again.Start();
            doc.Regenerate();
            foreach (var w in windows)
                words.Add(Placement(doc, w["id"]!.GetValue<string>(), (FamilyInstance)doc.GetElement(ids[w["id"]!.GetValue<string>()])));
            again.RollBack();
        }
        return ids;
    }

    /// <summary>A window as placed, in words for the log (ft, internal): its family's placement type, its level and
    /// Sill Height, its box, its host wall's box, base and height, and whether the wall lists it as an insert.</summary>
    private static string Placement(Document doc, string id, FamilyInstance fi)
    {
        static string Z(BoundingBoxXYZ? b) => b is null ? "none" : $"{b.Min.Z:0.####}..{b.Max.Z:0.####} (x {b.Min.X:0.##}..{b.Max.X:0.##}, y {b.Min.Y:0.##}..{b.Max.Y:0.##})";
        var level = doc.GetElement(fi.LevelId) as Level;
        var wall = fi.Host as Wall;
        var inserts = wall?.FindInserts(true, true, true, true);
        var baseLevel = wall is null ? null : doc.GetElement(wall.get_Parameter(BuiltInParameter.WALL_BASE_CONSTRAINT)?.AsElementId() ?? ElementId.InvalidElementId) as Level;
        return $"window {id}: family {fi.Symbol.Family.Name}, placement {fi.Symbol.Family.FamilyPlacementType}, " +
               $"level {level?.Name} at {level?.ProjectElevation:0.####}, Sill Height {fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM)?.AsDouble():0.####}, " +
               $"box z {Z(fi.get_BoundingBox(null))}, point {(fi.Location as LocationPoint)?.Point}; host {wall?.Id.Value} " +
               $"box z {Z(wall?.get_BoundingBox(null))}, base {baseLevel?.Name} offset {wall?.get_Parameter(BuiltInParameter.WALL_BASE_OFFSET)?.AsDouble():0.####} " +
               $"height {wall?.get_Parameter(BuiltInParameter.WALL_USER_HEIGHT_PARAM)?.AsDouble():0.####}; its inserts after regenerating " +
               $"{inserts?.Count}, this window among them {inserts?.Contains(fi.Id)}";
    }

    private static double? Length(Element e, MarkDefinition m) =>
        e.get_Parameter(m.Guid) is { HasValue: true } p ? p.AsDouble() : null;

    private static void Set(Parameter? p, double value, string what)
    {
        if (p is null || !p.Set(value))
            throw new InvalidOperationException($"couldn't set {what}");
    }

    private static void Set(Parameter? p, int value, string what)
    {
        if (p is null || !p.Set(value))
            throw new InvalidOperationException($"couldn't set {what}");
    }

    private static void Set(Parameter? p, string value, string what)
    {
        if (p is null || !p.Set(value))
            throw new InvalidOperationException($"couldn't set {what}");
    }

    private static CurveLoop Rectangle(double x0, double y0, double x1, double y1, double z)
    {
        var pts = new[] { new XYZ(x0, y0, z), new XYZ(x1, y0, z), new XYZ(x1, y1, z), new XYZ(x0, y1, z) };
        var loop = new CurveLoop();
        for (var i = 0; i < 4; i++)
            loop.Append(Line.CreateBound(pts[i], pts[(i + 1) % 4]));
        return loop;
    }

    /// <summary>A basic wall type one layer thick (the finish face is the wall's face), made once per thickness.</summary>
    private static WallType WallTypeOf(Document doc, double thickness)
    {
        var name = $"Gordium test wall {thickness * 12:0.###} in";
        var types = new FilteredElementCollector(doc).OfClass(typeof(WallType)).Cast<WallType>().ToList();
        if (types.FirstOrDefault(x => x.Name == name) is { } found)
            return found;
        var basic = types.FirstOrDefault(x => x.Kind == WallKind.Basic)
                    ?? throw new InvalidOperationException("no basic wall type in a new project");
        var made = (WallType)basic.Duplicate(name);
        made.SetCompoundStructure(CompoundStructure.CreateSingleLayerCompoundStructure(MaterialFunctionAssignment.Structure,
                                                                                       thickness, ElementId.InvalidElementId));
        return made;
    }

    /// <summary>Revit's own window template (<c>Window.rft</c>), in the application's family template folder or the
    /// English-Imperial one beside it.</summary>
    private static string WindowTemplate(RevitApplication app)
    {
        var tried = new List<string>();
        foreach (var dir in new[]
                 {
                     app.FamilyTemplatePath,
                     Path.Combine(Path.GetDirectoryName(app.FamilyTemplatePath.TrimEnd('\\', '/')) ?? "", "English-Imperial"),
                     Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Autodesk",
                                  $"RVT {app.VersionNumber}", "Family Templates", "English-Imperial"),
                 })
        {
            var path = Path.Combine(dir, "Window.rft");
            tried.Add(path);
            if (File.Exists(path))
                return path;
        }
        throw new InvalidOperationException("Revit's Window.rft wasn't found (looked in " + string.Join("; ", tried) + ")");
    }

    /// <summary>A window family of this window's size, made from Window.rft (whose opening cuts the wall from the
    /// Sill reference plane to the Top one): a frame solid filling the opening, half the template wall's thickness
    /// deep, centred in it. One family per window, so each window has a type of its own. Loaded into the project.</summary>
    private static FamilySymbol WindowFamily(RevitApplication app, Document project, JsonObject w, List<string> words)
    {
        var id = w["id"]!.GetValue<string>();
        double width = D(w["width"]), height = D(w["height"]);
        var name = $"Gordium test window {id} ({width * 12:0.###} x {height * 12:0.###} in)";
        var fdoc = app.NewFamilyDocument(WindowTemplate(app));
        try
        {
            using (var t = new Transaction(fdoc, "Gordium: a test window"))
            {
                t.Start();
                var fm = fdoc.FamilyManager;
                if (fm.CurrentType is null)
                    fm.NewType(name);
                fm.Set(FamilyParameterOf(fm, BuiltInParameter.WINDOW_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM, "Width"), width);
                fm.Set(FamilyParameterOf(fm, BuiltInParameter.WINDOW_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM, "Height"), height);
                fdoc.Regenerate();
                var planes = new FilteredElementCollector(fdoc).OfClass(typeof(ReferencePlane)).Cast<ReferencePlane>()
                    .Where(p => !string.IsNullOrEmpty(p.Name)).GroupBy(p => p.Name).ToDictionary(g => g.Key, g => g.First());
                // Revit 2027.4's Window.rft names them: Center (Front/Back), Center (Left/Right), Left, Reference Plane,
                // Right, Sill, Top (trial run 1, 2026-11-20): the head is "Top"
                double At(Func<XYZ, double> coordinate, params string[] names) =>
                    names.Select(n => planes.TryGetValue(n, out var rp) ? rp : null).FirstOrDefault(rp => rp is not null) is { } found
                        ? coordinate(found.GetPlane().Origin)
                        : throw new InvalidOperationException("Window.rft has no reference plane named " +
                                                              string.Join(" or ", names.Select(n => $"\"{n}\"")) + " (it has: " +
                                                              string.Join(", ", planes.Keys.Order()) + ")");
                double left = At(p => p.X, "Left"), right = At(p => p.X, "Right");
                double sill = At(p => p.Z, "Sill"), head = At(p => p.Z, "Top", "Head");
                double y = At(p => p.Y, "Center (Front/Back)");
                if (Math.Abs(right - left - width) > 1e-6 || Math.Abs(head - sill - height) > 1e-6)
                    throw new InvalidOperationException($"Window.rft's Left/Right and Sill/Top planes didn't flex to {width} x {height} ft " +
                                                        $"(they are {right - left} x {head - sill})");
                var profile = new CurveArray();
                var corners = new[] { new XYZ(left, y, sill), new XYZ(right, y, sill), new XYZ(right, y, head), new XYZ(left, y, head) };
                for (var i = 0; i < 4; i++)
                    profile.Append(Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                var loops = new CurveArrArray();
                loops.Append(profile);
                var sketch = SketchPlane.Create(fdoc, Plane.CreateByNormalAndOrigin(XYZ.BasisY, new XYZ(0, y, 0)));
                const double depth = 2.0 / 12;
                var frame = fdoc.FamilyCreate.NewExtrusion(true, loops, sketch, depth);
                frame.StartOffset = -depth / 2;
                frame.EndOffset = depth / 2;
                // the opening it cuts in its wall: the template's own, else one made here on the template's wall (trial run 3,
                // 2026-11-20: the drawn walls showed no cut and no insert)
                var openings = new FilteredElementCollector(fdoc).OfClass(typeof(Opening)).GetElementCount();
                var host = new FilteredElementCollector(fdoc).OfClass(typeof(Wall)).FirstElement() as Wall;
                words.Add($"{name}: Window.rft has {openings} opening(s) and {(host is null ? "no" : "a")} host wall; planes left {left}, right {right}, sill {sill}, top {head}, wall centre y {y}; the template wall's box {(host?.get_BoundingBox(null) is { } hb ? $"{hb.Min} .. {hb.Max}" : "none")}");
                if (openings == 0)
                {
                    if (host is null)
                        throw new InvalidOperationException("Window.rft has no opening and no wall to cut one in");
                    var cut = new CurveArray();
                    for (var i = 0; i < 4; i++)
                        cut.Append(Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                    fdoc.FamilyCreate.NewOpening(host, cut);
                    words.Add($"{name}: made an opening {width} x {height} ft in the template's wall");
                }
                t.Commit();
            }
            var family = fdoc.LoadFamily(project) ?? throw new InvalidOperationException($"{name} didn't load into the project");
            using (var rename = new Transaction(project, "Gordium: name a test window"))
            {
                rename.Start();
                family.Name = name;
                rename.Commit();
            }
            var symbols = family.GetFamilySymbolIds().Select(project.GetElement).OfType<FamilySymbol>().ToList();
            return symbols.FirstOrDefault(s => RevitInterior.TypeSize(s) is var (sw, sh) && sw is { } a && sh is { } b
                                               && Math.Abs(a - width) < 1e-9 && Math.Abs(b - height) < 1e-9)
                   ?? throw new InvalidOperationException($"{name} has no type {width} x {height} ft once loaded");
        }
        finally
        {
            fdoc.Close(false);
        }
    }

    private static FamilyParameter FamilyParameterOf(FamilyManager fm, BuiltInParameter first, BuiltInParameter second, string name) =>
        fm.get_Parameter(first) ?? fm.get_Parameter(second) ?? fm.get_Parameter(name)
        ?? throw new InvalidOperationException($"Window.rft has no {name} parameter (it has: " +
                                               string.Join(", ", fm.Parameters.Cast<FamilyParameter>().Select(p => p.Definition.Name).Order()) + ")");
}
