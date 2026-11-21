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
/// with its Clear offset above the sill line, confirmed with Gordium's stamp as the architect's tick would be. In a house
/// of the stairs step (4), each flight is a component stair (DrawStairs). In a house of step 5, each door is a door
/// family of its own (Door.rft: a leaf of its size) in an outside wall with no window, marked Escape opening No and Exit
/// door as the house says, its type's maker's clear opening confirmed with a door's stamp; each stair's handrail is a
/// railing on the stair whose top rail (a square rail profile of the drawing's) is the handrail, marked so; each level
/// guard a railing (its rails and balusters the drawing's) along the edge of a floor between a wall and a post; and the
/// tick "these are all the guards and handrails" set. A real house placed by its layout (a level with <c>walls</c>, no
/// box: test_data/real_houses/) has each of its walls drawn as given, the floor under its outline, each opening in the
/// wall the drawing names and each Room at the drawing's point inside it. What it can't draw is an error, never a house
/// drawn differently.
/// </summary>
internal static class HouseDraw
{
    /// <summary>Who the confirmation stamp names: the trial's drawing, never an architect.</summary>
    internal const string StampedBy = "Gordium add-in, Record houses (the trial's drawing of a hand-worked house)";

    private static double D(JsonNode? n) => n!.GetValue<double>();

    private static (double X, double Y) P(JsonNode n) => (D(n[0]), D(n[1]));

    /// <summary>Draws the house; gives the house's ids to the Revit elements' <c>UniqueId</c>s.</summary>
    internal static Dictionary<string, string> Draw(RevitApplication app, Document doc, JsonObject house, List<string> log)
    {
        var plan = MarkSetup.Plan(RevitMarks.Bindings(doc));
        if (plan.FirstOrDefault(s => s.Action == MarkSetupAction.Conflict) is { } conflict)
            throw new InvalidOperationException($"{conflict.Mark.Name}: {conflict.Words}");
        RevitMarks.AddMarks(doc, app, plan);

        var windows = house["windows"]!.AsArray().Select(n => n!.AsObject()).ToList();
        var families = windows.ToDictionary(w => w["id"]!.GetValue<string>(), w => WindowFamily(app, doc, w));
        // step 5: a door family of its own per door, and the rail profile and baluster families the railings use, each
        // made and loaded before anything is drawn (a family loads only outside the project's transactions)
        var doors = (house["doors"] as JsonArray ?? []).Select(n => n!.AsObject()).ToList();
        var doorFamilies = doors.ToDictionary(d => d["id"]!.GetValue<string>(), d => DoorFamily(app, doc, d));
        var guards = (house["guards"] as JsonArray ?? []).Select(n => n!.AsObject()).ToList();
        var handrails = (house["stairs"] as JsonArray ?? []).Any(s => s!["handrails"] is JsonArray { Count: > 0 });
        var rail = house["rail"] is JsonNode railSize ? D(railSize) : 1.5 / 12;
        var profile = handrails || guards.Count > 0 ? RailProfile(app, doc, rail, log) : null;
        var balusters = guards.ToDictionary(g => g["id"]!.GetValue<string>(), g => BalusterFamily(app, doc, g["balusters"]!.AsObject(), log));

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
            var height = D(level["wall_height"]);
            var key = z.ToString(CultureInfo.InvariantCulture);
            // a wall per rectangle, along its longer side, as thick as its shorter: a gap between rooms (a hand-worked
            // house's fillers), or every wall of a house placed by its layout (a real house: `walls`, indexed by the
            // openings hosted in them)
            Wall RectWall(JsonNode f)
            {
                var (fx0, fy0) = P(f[0]!);
                var (fx1, fy1) = P(f[1]!);
                var alongX = fx1 - fx0 >= fy1 - fy0;
                var thick = alongX ? fy1 - fy0 : fx1 - fx0;
                var line = alongX
                    ? Line.CreateBound(new XYZ(fx0, (fy0 + fy1) / 2, z), new XYZ(fx1, (fy0 + fy1) / 2, z))
                    : Line.CreateBound(new XYZ((fx0 + fx1) / 2, fy0, z), new XYZ((fx0 + fx1) / 2, fy1, z));
                return Wall.Create(doc, line, WallTypeOf(doc, thick).Id, lv.Id, height, 0, false, false);
            }
            if (level["walls"] is JsonArray placed)
            {
                // a house placed by its layout: its own walls and no box; the floor under its outline, as thick as the
                // drawing's slab (the gap the layout leaves under it: the project's own floor type, 12 in, cut 1 1/2 in
                // into the Orangetown main floor's 9'-0" ceiling, review round 1)
                foreach (var (f, k) in placed.Select((f, k) => (f!, k)))
                    walls[$"{key}-wall-{k}"] = RectWall(f);
                var outline = level["outline"]!.AsArray().Select(p => P(p!)).ToList();
                var loop = new CurveLoop();
                for (var i = 0; i < outline.Count; i++)
                    loop.Append(Line.CreateBound(new XYZ(outline[i].X, outline[i].Y, z), new XYZ(outline[(i + 1) % outline.Count].X, outline[(i + 1) % outline.Count].Y, z)));
                var slab = FloorTypeOf(doc, floorType, D(level["slab"]));
                var made = Floor.Create(doc, [loop], slab.Id, lv.Id);
                doc.Regenerate();
                var box = made.get_BoundingBox(null);
                var drawnThick = made.get_Parameter(BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)?.AsDouble();
                log.Add($"floor at {key} ft: type {slab.Name}, thickness {drawnThick * 12:0.###} in (drawing {D(level["slab"]) * 12:0.###}), " +
                        $"box z {box?.Min.Z:0.####} to {box?.Max.Z:0.####} ft");
                if (drawnThick is not { } th || Math.Abs(th - D(level["slab"])) > 1e-9)
                    throw new InvalidOperationException($"the floor at {key} ft came out {drawnThick} ft thick, not the drawing's {D(level["slab"])}");
            }
            else
            {
                var (x0, y0) = P(level["box"]![0]!);
                var (x1, y1) = P(level["box"]![1]!);
                var h = wallThickness / 2;
                var exterior = WallTypeOf(doc, wallThickness);
                var corners = new[] { new XYZ(x0 - h, y0 - h, z), new XYZ(x1 + h, y0 - h, z), new XYZ(x1 + h, y1 + h, z), new XYZ(x0 - h, y1 + h, z) };
                var sides = new[] { "ymin", "xmax", "ymax", "xmin" };
                for (var i = 0; i < 4; i++)
                    walls[$"{key}-{sides[i]}"] =
                        Wall.Create(doc, Line.CreateBound(corners[i], corners[(i + 1) % 4]), exterior.Id, lv.Id, height, 0, false, false);
                Floor.Create(doc, [Rectangle(x0 - wallThickness, y0 - wallThickness, x1 + wallThickness, y1 + wallThickness, z)], floorType.Id, lv.Id);
                foreach (var f in level["fillers"]!.AsArray())
                    RectWall(f!);
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
            // Revit refuses \ : { } [ ] | ; < > ? ` ~ in an element's name (the Orangetown main floor's "Main floor: ...")
            shape.Name = new string(("Ceiling of " + room["name"]!.GetValue<string>())
                .Select(c => @"\:{}[]|;<>?`~".Contains(c) ? '-' : c).ToArray());
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
        // the walls, slabs and ceilings committed and regenerated before any window is placed in them (with the regenerate
        // after each window below, what run 6 changed): windows placed in
        // the walls' own transaction were hosted but cut nothing (trial runs 2 to 5, Revit 2027.4); placed after this
        // commit, each cuts its wall (run 6)
        t.Commit();
        using var t2 = new Transaction(doc, "Gordium: place the windows and Rooms");
        t2.Start();

        foreach (var w in windows)
        {
            var id = w["id"]!.GetValue<string>();
            var z = D(w["level"]);
            var (wall, at) = Host(walls, w, z, wallThickness);
            var symbol = families[id];
            if (!symbol.IsActive)
                symbol.Activate();
            var fi = doc.Create.NewFamilyInstance(at, symbol, wall, levels[z], StructuralType.NonStructural);
            Set(fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM), D(w["sill"]), "Sill Height");
            // load-bearing: regenerated right after each window is placed and its Sill Height set, Revit cuts the wall;
            // without this (trial runs 2 to 5, and again once removed in 830fbedc) every window was hosted but cut
            // nothing, and the reader found no wall opening (run 6, a34f4f9d, cut with it; the re-recording of 830fbedc,
            // with it removed and the walls still committed first, cut nothing again)
            doc.Regenerate();
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
        // step 5: each door in an outside wall with no window (house.yaml gives a door no room or place, and where it
        // stands changes none of its measures: the reader sends its marks and the maker's clear opening, nothing drawn;
        // so house 2's front door is upstairs, in the only level the house draws: Ben, 2026-11-20, fine), in its room's
        // outside wall at the level, placed as the windows are (the walls committed
        // first, regenerated right after it is placed), marked Escape opening No and Exit door as the house says, its
        // type's Operation and maker's clear opening set
        foreach (var d in doors)
        {
            var id = d["id"]!.GetValue<string>();
            var z = D(d["level"]);
            var (wall, at) = Host(walls, d, z, wallThickness);
            var symbol = doorFamilies[id];
            if (!symbol.IsActive)
                symbol.Activate();
            var fi = doc.Create.NewFamilyInstance(at, symbol, wall, levels[z], StructuralType.NonStructural);
            if (fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM) is { IsReadOnly: false } sill)
                sill.Set(0.0);
            doc.Regenerate();
            Set(fi.get_Parameter(Marks.EscapeOpening.Guid), 0, Marks.EscapeOpening.Name);
            Set(fi.get_Parameter(Marks.ExitDoor.Guid), d["exit"]!.GetValue<bool>() ? 1 : 0, Marks.ExitDoor.Name);
            fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.Set(d["name"]!.GetValue<string>());
            var word = Operations.Words.First(x => Operations.ForDoor(x) == d["operation"]!.GetValue<string>());
            Set(symbol.get_Parameter(Marks.Operation.Guid), word, Marks.Operation.Name);
            if (d["clear"] is JsonObject c)
            {
                Set(symbol.get_Parameter(Marks.ClearWidth.Guid), D(c["width"]), Marks.ClearWidth.Name);
                Set(symbol.get_Parameter(Marks.ClearHeight.Guid), D(c["height"]), Marks.ClearHeight.Name);
                Set(symbol.get_Parameter(Marks.ClearSource.Guid), c["source"]!.GetValue<string>(), Marks.ClearSource.Name);
            }
            var box = fi.get_BoundingBox(null);
            log.Add($"door {id}: placed in wall {wall.Id.Value}, host {fi.Host?.Id.Value}, box {box?.Min.X:0.###},{box?.Min.Y:0.###},{box?.Min.Z:0.###} to " +
                    $"{box?.Max.X:0.###},{box?.Max.Y:0.###},{box?.Max.Z:0.###}, type size {RevitInterior.TypeSize(symbol)}");
            ids[id] = fi.UniqueId;
        }
        doc.Regenerate();
        // the stamp, from the type's values as Revit now gives them (read the way the reader reads them): a window's,
        // and a door's (its width and height, no offset)
        foreach (var (symbol, door) in windows.Where(w => w["clear"] is JsonObject).Select(w => (families[w["id"]!.GetValue<string>()], false))
                     .Concat(doors.Where(d => d["clear"] is JsonObject).Select(d => (doorFamilies[d["id"]!.GetValue<string>()], true))))
        {
            var (width, height) = RevitInterior.TypeSize(symbol);
            var values = new ClearValues(symbol.UniqueId, width, height, symbol.get_Parameter(Marks.Operation.Guid)?.AsString()?.Trim(),
                                         Length(symbol, Marks.ClearWidth), Length(symbol, Marks.ClearHeight),
                                         door ? null : Length(symbol, Marks.ClearOffset),
                                         symbol.get_Parameter(Marks.ClearSource.Guid)?.AsString()?.Trim(), Door: door);
            Set(symbol.get_Parameter(Marks.ClearConfirmed.Guid),
                ClearStamp.Make(values, StampedBy, DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)),
                Marks.ClearConfirmed.Name);
        }

        foreach (var room in house["rooms"]!.AsArray().Select(n => n!.AsObject()))
        {
            var floor = room["floor"]!.AsArray().Select(p => P(p!)).ToList();
            // a placed house's rooms aren't all rectangles: the drawing's point inside each (its outline's average
            // could fall outside an L-shaped room)
            var inside = room["point"] is JsonArray point ? new UV(D(point[0]), D(point[1]))
                : new UV(floor.Average(p => p.X), floor.Average(p => p.Y));
            var r = doc.Create.NewRoom(levels[D(room["floor_elevation"])], inside)
                    ?? throw new InvalidOperationException($"Revit placed no Room in {room["id"]}");
            r.Name = room["name"]!.GetValue<string>();
            Set(r.get_Parameter(Marks.SleepingRoom.Guid), room["sleeping"]!.GetValue<bool>() ? 1 : 0, Marks.SleepingRoom.Name);
            ids[room["id"]!.GetValue<string>()] = r.UniqueId;
        }
        t2.Commit();
        if (house["stairs"] is JsonArray stairs && stairs.Count > 0)
            DrawStairs(doc, stairs.Select(n => n!.AsObject()).ToList(), levels, ids, log, profile, house);
        if (guards.Count > 0)
            DrawGuards(doc, guards, levels, ids, log, profile!, balusters, rail);
        // the architect's tick once every guard and handrail of the house is drawn as a railing (step 5)
        var notDrawn = (house["not_drawn"] as JsonArray ?? []).Select(n => n!.GetValue<string>()).ToList();
        if (!notDrawn.Contains("guards") && !notDrawn.Contains("handrails") && house["step"]!.GetValue<int>() >= 5)
        {
            using var tick = new Transaction(doc, "Gordium: these are all the guards and handrails");
            tick.Start();
            Set(doc.ProjectInformation.get_Parameter(Marks.AllGuards.Guid), 1, Marks.AllGuards.Name);
            tick.Commit();
        }
        // step 6: the architect's "this house has no ..." ticks, each kind the house's own data says it has none of
        // (an empty list, or a has_none claim), as the drawing names them
        var none = (house["has_none"] as JsonArray ?? []).Select(n => n!.GetValue<string>()).ToList();
        if (none.Count > 0)
        {
            using var tick = new Transaction(doc, "Gordium: this house has none of");
            tick.Start();
            foreach (var kind in none)
            {
                var mark = (HasNone.All.FirstOrDefault(k => k.Kind == kind)
                            ?? throw new InvalidOperationException($"no tick for \"{kind}\": not a kind the house can have none of")).Mark;
                Set(doc.ProjectInformation.get_Parameter(mark.Guid), 1, mark.Name);
                log.Add($"ticked {mark.Name}: Yes");
            }
            tick.Commit();
        }
        return ids;
    }

    /// <summary>The wall an opening (a window or door) is hosted by and the point it is placed at: in a placed house,
    /// its wall by index in its level's <c>walls</c> and its point <c>at</c> on that wall's centre line; else the box's
    /// side it faces out of, half the exterior wall's thickness out from its centre on the inside face.</summary>
    private static (Wall Wall, XYZ At) Host(Dictionary<string, Wall> walls, JsonObject o, double z, double wallThickness)
    {
        var key = z.ToString(CultureInfo.InvariantCulture);
        if (o["wall"] is JsonNode index)
        {
            var (ax, ay) = P(o["at"]!);
            return (walls[$"{key}-wall-{index.GetValue<int>()}"], new XYZ(ax, ay, z));
        }
        var (cx, cy) = P(o["center"]!);
        var (ox, oy) = P(o["outward"]!);
        var side = oy < 0 ? "ymin" : ox < 0 ? "xmin" : oy > 0 ? "ymax" : "xmax";
        return (walls[$"{key}-{side}"], new XYZ(cx + ox * wallThickness / 2, cy + oy * wallThickness / 2, z));
    }

    // ---- doors, railings and guards (step 5) -------------------------------------------------------------------

    /// <summary>A door family of this door's size, made from Revit's Door.rft: its leaf a solid filling the opening
    /// (from the level up its height, the width of the family, 1 3/4 in thick, centred in the wall), so the door as
    /// placed is the size its type says. One family per door. Loaded into the project.</summary>
    private static FamilySymbol DoorFamily(RevitApplication app, Document project, JsonObject d)
    {
        var id = d["id"]!.GetValue<string>();
        double width = D(d["width"]), height = D(d["height"]);
        var name = $"Gordium test door {id} ({width * 12:0.###} x {height * 12:0.###} in)";
        var fdoc = app.NewFamilyDocument(Template(app, "Door.rft"));
        try
        {
            using (var t = new Transaction(fdoc, "Gordium: a test door"))
            {
                t.Start();
                var fm = fdoc.FamilyManager;
                if (fm.CurrentType is null)
                    fm.NewType(name);
                fm.Set(FamilyParameterOf(fm, BuiltInParameter.DOOR_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM, "Width"), width);
                fm.Set(FamilyParameterOf(fm, BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM, "Height"), height);
                fdoc.Regenerate();
                var planes = new FilteredElementCollector(fdoc).OfClass(typeof(ReferencePlane)).Cast<ReferencePlane>()
                    .Where(p => !string.IsNullOrEmpty(p.Name)).GroupBy(p => p.Name).ToDictionary(g => g.Key, g => g.First().GetPlane().Origin);
                // Door.rft's Left and Right planes flex with its Width; without them the leaf is centred on the family's origin
                double left = planes.TryGetValue("Left", out var l) ? l.X : -width / 2, right = planes.TryGetValue("Right", out var rr) ? rr.X : width / 2;
                double y = planes.TryGetValue("Center (Front/Back)", out var c) ? c.Y : 0;
                if (Math.Abs(right - left - width) > 1e-6)
                    throw new InvalidOperationException($"Door.rft's Left and Right planes didn't flex to {width} ft (they are {right - left} apart; " +
                                                        "its planes: " + string.Join(", ", planes.Keys.Order()) + ")");
                var profile = new CurveArray();
                var corners = new[] { new XYZ(left, y, 0), new XYZ(right, y, 0), new XYZ(right, y, height), new XYZ(left, y, height) };
                for (var i = 0; i < 4; i++)
                    profile.Append(Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                var loops = new CurveArrArray();
                loops.Append(profile);
                var sketch = SketchPlane.Create(fdoc, Plane.CreateByNormalAndOrigin(XYZ.BasisY, new XYZ(0, y, 0)));
                const double depth = 1.75 / 12;
                var leaf = fdoc.FamilyCreate.NewExtrusion(true, loops, sketch, depth);
                leaf.StartOffset = -depth / 2;
                leaf.EndOffset = depth / 2;
                t.Commit();
            }
            var family = fdoc.LoadFamily(project) ?? throw new InvalidOperationException($"{name} didn't load into the project");
            using (var rename = new Transaction(project, "Gordium: name a test door"))
            {
                rename.Start();
                family.Name = name;
                rename.Commit();
            }
            var symbols = family.GetFamilySymbolIds().Select(project.GetElement).OfType<FamilySymbol>().ToList();
            return symbols.FirstOrDefault(s => RevitInterior.TypeSize(s) is var (sw, sh) && sw is { } a && sh is { } b
                                               && Math.Abs(a - width) < 1e-9 && Math.Abs(b - height) < 1e-9)
                   ?? throw new InvalidOperationException($"{name} has no type {width} x {height} ft once loaded (sizes: " +
                                                          string.Join(", ", symbols.Select(s => RevitInterior.TypeSize(s).ToString())) + ")");
        }
        finally
        {
            fdoc.Close(false);
        }
    }

    /// <summary>A rail profile <paramref name="size"/> square (Profile-Rail.rft), centred across the rail with its top
    /// on the profile's origin: a rail placed at a height has its top there. Loaded into the project.</summary>
    private static FamilySymbol RailProfile(RevitApplication app, Document project, double size, List<string> log)
    {
        var name = $"Gordium test rail {size * 12:0.###} in square";
        var fdoc = app.NewFamilyDocument(Template(app, "Profile-Rail.rft"));
        try
        {
            using (var t = new Transaction(fdoc, "Gordium: a rail profile"))
            {
                t.Start();
                var view = new FilteredElementCollector(fdoc).OfClass(typeof(ViewPlan)).Cast<ViewPlan>().FirstOrDefault(v => !v.IsTemplate)
                           ?? throw new InvalidOperationException("Profile-Rail.rft has no plan view to draw the profile in");
                var corners = new[] { new XYZ(-size / 2, -size, 0), new XYZ(size / 2, -size, 0), new XYZ(size / 2, 0, 0), new XYZ(-size / 2, 0, 0) };
                for (var i = 0; i < 4; i++)
                    fdoc.FamilyCreate.NewDetailCurve(view, Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                t.Commit();
            }
            var family = fdoc.LoadFamily(project) ?? throw new InvalidOperationException($"{name} didn't load into the project");
            using (var rename = new Transaction(project, "Gordium: name the rail profile"))
            {
                rename.Start();
                family.Name = name;
                rename.Commit();
            }
            var symbol = family.GetFamilySymbolIds().Select(project.GetElement).OfType<FamilySymbol>().FirstOrDefault()
                         ?? throw new InvalidOperationException($"{name} has no type once loaded");
            log.Add($"rail profile {name}: family {family.Id.Value}, type {symbol.Id.Value} \"{symbol.Name}\", category {family.FamilyCategory?.BuiltInCategory}");
            return symbol;
        }
        finally
        {
            fdoc.Close(false);
        }
    }

    /// <summary>A baluster family (Baluster.rft): a box the guard's balusters' width square, from its origin up their
    /// height (fixed: placed at its base, it is that tall whatever its top reference). Loaded into the project.</summary>
    private static FamilySymbol BalusterFamily(RevitApplication app, Document project, JsonObject b, List<string> log)
    {
        double width = D(b["width"]), height = D(b["top"]) - D(b["bottom"]);
        var name = $"Gordium test baluster {width * 12:0.###} in x {height * 12:0.###} in";
        var fdoc = app.NewFamilyDocument(Template(app, "Baluster.rft"));
        try
        {
            using (var t = new Transaction(fdoc, "Gordium: a baluster"))
            {
                t.Start();
                var profile = new CurveArray();
                var corners = new[] { new XYZ(-width / 2, -width / 2, 0), new XYZ(width / 2, -width / 2, 0), new XYZ(width / 2, width / 2, 0), new XYZ(-width / 2, width / 2, 0) };
                for (var i = 0; i < 4; i++)
                    profile.Append(Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                var loops = new CurveArrArray();
                loops.Append(profile);
                var sketch = SketchPlane.Create(fdoc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero));
                fdoc.FamilyCreate.NewExtrusion(true, loops, sketch, height);
                t.Commit();
            }
            var family = fdoc.LoadFamily(project) ?? throw new InvalidOperationException($"{name} didn't load into the project");
            using (var rename = new Transaction(project, "Gordium: name the baluster"))
            {
                rename.Start();
                family.Name = name;
                rename.Commit();
            }
            var symbol = family.GetFamilySymbolIds().Select(project.GetElement).OfType<FamilySymbol>().FirstOrDefault()
                         ?? throw new InvalidOperationException($"{name} has no type once loaded");
            log.Add($"baluster {name}: family {family.Id.Value}, type {symbol.Id.Value}, category {family.FamilyCategory?.BuiltInCategory}");
            return symbol;
        }
        finally
        {
            fdoc.Close(false);
        }
    }

    /// <summary>A railing type of the project's first, duplicated: its top rail the profile, its top at
    /// <paramref name="topHeight"/>; no handrails; no posts; the rails that aren't continuous <paramref name="rails"/>
    /// (each its top's height); and the balusters <paramref name="baluster"/> describes (one per pattern, from the base
    /// at its offset, the pattern its spacing long, the first its centre in from the start), or none. Every setting
    /// Revit refuses is an error, never a railing drawn differently; each is logged.</summary>
    private static RailingType RailingTypeOf(Document doc, string name, FamilySymbol profile, double topHeight, IEnumerable<double> rails,
                                             FamilySymbol? balusterFamily, JsonObject? baluster, List<string> log)
    {
        var basic = new FilteredElementCollector(doc).OfClass(typeof(RailingType)).Cast<RailingType>().FirstOrDefault()
                    ?? throw new InvalidOperationException("no railing type in a new project");
        var type = (RailingType)basic.Duplicate(name);
        var anyTop = doc.GetElement(type.TopRailType) as ElementType
                     ?? new FilteredElementCollector(doc).OfClass(typeof(TopRailType)).Cast<ElementType>().FirstOrDefault()
                     ?? throw new InvalidOperationException("no top rail type in a new project");
        var topType = (ContinuousRailType)anyTop.Duplicate(name + " top rail");
        topType.ProfileId = profile.Id;
        topType.StartOrBottomExtensionStyle = RailExtensionStyle.None;
        topType.EndOrTopExtensionStyle = RailExtensionStyle.None;
        topType.StartOrBottomTermination = ElementId.InvalidElementId;
        topType.EndOrTopTermination = ElementId.InvalidElementId;
        type.TopRailType = topType.Id;
        type.TopRailHeight = topHeight;
        // no handrails of the type's own: a handrail's position can be set only where the type has one (Revit 2027.4,
        // trial step 5 run 1: "The rail has no primary hand rail" on a type with none); where it has none, there is none
        if (type.PrimaryHandrailType != ElementId.InvalidElementId)
            type.PrimaryHandRailPosition = HandRailPosition.None;
        if (type.SecondaryHandrailType != ElementId.InvalidElementId)
            type.SecondaryHandRailPosition = HandRailPosition.None;
        log.Add($"railing type {name}: from \"{basic.Name}\", its own handrails {type.PrimaryHandrailType.Value} / {type.SecondaryHandrailType.Value} " +
                $"(positions {type.PrimaryHandRailPosition} / {type.SecondaryHandRailPosition})");
        var structure = type.RailStructure;
        for (var i = structure.GetNonContinuousRailCount() - 1; i >= 0; i--)
            structure.RemoveNonContinuousRail(i);
        var k = 0;
        foreach (var height in rails)
        {
            structure.AddNonContinuousRail($"Gordium rail {++k}", height, 0);
            structure.GetNonContinuousRail(structure.GetNonContinuousRailCount() - 1).ProfileId = profile.Id;
        }
        var placement = type.BalusterPlacement;
        placement.UseBalusterPerTreadOnStairs = false;
        var pattern = placement.BalusterPattern;
        if (pattern.GetBalusterCount() == 0)
            throw new InvalidOperationException($"railing type {basic.Name}'s baluster pattern has no baluster to set");
        while (pattern.GetBalusterCount() > 1)
            pattern.RemoveBaluster(pattern.GetBalusterCount() - 1);
        var info = pattern.GetBaluster(0);
        if (balusterFamily is null || baluster is null)
            info.BalusterFamilyId = ElementId.InvalidElementId;
        else
        {
            double first = D(baluster["first"]) + D(baluster["width"]) / 2, spacing = D(baluster["spacing"]);
            info.BalusterFamilyId = balusterFamily.Id;
            info.BaseReferenceName = BalusterInfo.GetReferenceNameForHost();
            info.BaseOffset = D(baluster["bottom"]);
            info.TopReferenceName = BalusterInfo.GetReferenceNameForTopRail();
            info.TopOffset = 0;
            info.Offset = 0;
            info.DistanceFromPreviousOrSpace = first;
            pattern.EndSpace = Math.Max(spacing - first, 0);
            pattern.DistributionJustification = PatternJustification.Beginning;
            pattern.ExcessLengthFillBalusterId = ElementId.InvalidElementId;
        }
        foreach (var post in new[] { placement.PostPattern.StartPost, placement.PostPattern.EndPost, placement.PostPattern.CornerPost })
            post.BalusterFamilyId = ElementId.InvalidElementId;
        log.Add($"railing type {name}: top rail {topType.Id.Value} at {topHeight * 12:0.###} in, {structure.GetNonContinuousRailCount()} other rails, " +
                $"balusters {(balusterFamily is null ? "none" : $"{balusterFamily.Name} from {D(baluster!["bottom"]) * 12:0.###} in, first at {pattern.GetBaluster(0).DistanceFromPreviousOrSpace * 12:0.###} in, pattern {pattern.Length * 12:0.###} in")}");
        return type;
    }

    /// <summary>Each handrail of a stair as a railing on it (Revit's own, made on its treads), its path moved to the
    /// drawing's (the handrail's inner edge RAIL / 2 inward), the railing on the other side deleted; its type's top rail
    /// the handrail (marked so), with no balusters. What Revit gives back is logged.</summary>
    private static void DrawHandrails(Document doc, ElementId stairsId, JsonObject st, FamilySymbol profile, double top, List<string> log)
    {
        var id = st["id"]!.GetValue<string>();
        using var t = new Transaction(doc, "Gordium: the stair's handrails");
        t.Start();
        var type = RailingTypeOf(doc, $"Gordium test handrail {id}", profile, top, [], null, null, log);
        Set(type.get_Parameter(Marks.TopRailIsHandrail.Guid), 1, Marks.TopRailIsHandrail.Name);
        var made = Railing.Create(doc, stairsId, type.Id, RailingPlacementPosition.Treads).ToList();
        doc.Regenerate();
        var (px0, py0) = P(st["path"]![0]!);
        var (px1, py1) = P(st["path"]![1]!);
        var len = Math.Sqrt((px1 - px0) * (px1 - px0) + (py1 - py0) * (py1 - py0));
        double lx = -(py1 - py0) / len, ly = (px1 - px0) / len;              // to the left, looking up the run
        double A(XYZ p) => (p.X - px0) * lx + (p.Y - py0) * ly;
        var wanted = st["handrails"]!.AsArray().Select(h => h!.AsObject()).ToDictionary(h => h["side"]!.GetValue<string>());
        var kept = new HashSet<string>();
        foreach (var rid in made)
        {
            var railing = (Railing)doc.GetElement(rid);
            var path = railing.GetPath().ToList();
            var mid = (path[0].GetEndPoint(0) + path[^1].GetEndPoint(1)) / 2;
            var side = A(mid) > 0 ? "left" : "right";
            log.Add($"stair {id}: Revit's railing {rid.Value} on its {side}: path " +
                    string.Join(" ", path.Select(c => $"({c.GetEndPoint(0).X:0.####},{c.GetEndPoint(0).Y:0.####},{c.GetEndPoint(0).Z:0.####})-({c.GetEndPoint(1).X:0.####},{c.GetEndPoint(1).Y:0.####},{c.GetEndPoint(1).Z:0.####})")));
            if (!wanted.TryGetValue(side, out var h) || !kept.Add(side))
            {
                doc.Delete(rid);
                continue;
            }
            var z = path[0].GetEndPoint(0).Z;
            var (ax, ay) = P(h["path"]![0]!);
            var (bx, by) = P(h["path"]![1]!);
            var loop = new CurveLoop();
            loop.Append(Line.CreateBound(new XYZ(ax, ay, z), new XYZ(bx, by, z)));
            railing.SetPath(loop);
            doc.Regenerate();
            // where the top rail's inner face (its edge nearest the middle) lands, against the house's: Revit placed a
            // stair railing's rail by its own offset whatever the path (trial step 5 run 3: 0.25 to 1.75 in off the wall,
            // the house's 3.5 and 3 in), so it is measured from the drawn rail and moved until it is the house's: first
            // by the path, then by the railing's placement offset either way, each move measured
            var want = A(new XYZ(D(h["inner"]![0]![0]), D(h["inner"]![0]![1]), 0));
            double? Inner()
            {
                var pts = RailPoints(doc.GetElement(railing.TopRail));
                return pts.Count == 0 ? null : side == "left" ? pts.Min(A) : pts.Max(A);
            }
            var tries = new List<string>();
            void Shift(double by)
            {
                var shifted = new CurveLoop();
                foreach (var c in railing.GetPath())
                    shifted.Append(c.CreateTransformed(Transform.CreateTranslation(new XYZ(lx * by, ly * by, 0))));
                railing.SetPath(shifted);
            }
            var param = railing.get_Parameter(BuiltInParameter.STAIRS_RAILING_PLACEMENT_OFFSET);
            for (var k = 0; k < 6 && Inner() is { } got && Math.Abs(got - want) > 1e-6; k++)
            {
                var delta = want - got;
                tries.Add($"inner {got * 12:0.####} in across, wanted {want * 12:0.####}");
                if (k < 2)
                    Shift(delta);
                else if (param is { IsReadOnly: false })
                    param.Set(param.AsDouble() + (k % 2 == 0 ? delta : -delta) * (k < 4 ? 1 : -1));
                doc.Regenerate();
            }
            var landed = Inner();
            log.Add($"stair {id}: handrail {side}: drawn inner face {(landed is { } li ? (li * 12).ToString("0.######", CultureInfo.InvariantCulture) : "none")} in across " +
                    $"the run's path, the house's {want * 12:0.######} in; moves: {(tries.Count == 0 ? "none" : string.Join(" | ", tries))}; " +
                    $"placement offset {param?.AsDouble() * 12:0.####} in");
            if (landed is not { } l2 || Math.Abs(l2 - want) > 1e-6)
                throw new InvalidOperationException($"stair {id}: its {side} handrail's inner face couldn't be put where the house has it: {log[^1]}");
        }
        if (kept.Count != wanted.Count)
            throw new InvalidOperationException($"stair {id}: Revit made no railing on its {string.Join(", ", wanted.Keys.Except(kept))} side");
        doc.Regenerate();
        t.Commit();
        var stair = (Stairs)doc.GetElement(stairsId);
        foreach (var rid in stair.GetAssociatedRailings())
        {
            var railing = (Railing)doc.GetElement(rid);
            var topRail = doc.GetElement(railing.TopRail);
            var box = topRail?.get_BoundingBox(null);
            log.Add($"stair {id}: railing {rid.Value} host {railing.HostId.Value}, top rail {railing.TopRail.Value} box " +
                    $"{box?.Min.X:0.####},{box?.Min.Y:0.####},{box?.Min.Z:0.####} to {box?.Max.X:0.####},{box?.Max.Y:0.####},{box?.Max.Z:0.####}, " +
                    $"handrails {railing.GetHandRails().Count}");
        }
    }

    /// <summary>Every vertex of an element's solids (a family's instance geometry included), for where a drawn rail is.</summary>
    private static List<XYZ> RailPoints(Element? e)
    {
        var pts = new List<XYZ>();
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                if (o is Solid s)
                    foreach (Edge edge in s.Edges)
                        pts.AddRange(edge.Tessellate());
                else if (o is GeometryInstance gi && gi.GetInstanceGeometry() is { } inner)
                    Walk(inner);
            }
        }
        if (e?.get_Geometry(new Options { DetailLevel = ViewDetailLevel.Fine }) is { } geometry)
            Walk(geometry);
        return pts;
    }

    /// <summary>Each solid of an element as its extents along a guard (u from its start along its unit direction),
    /// across it and up, for the log beside the drawing's members.</summary>
    private static List<string> SolidsAlong(Element? e, XYZ start, XYZ along, double walk)
    {
        var out_ = new List<string>();
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                if (o is Solid { Faces.Size: > 0 } s)
                {
                    var pts = s.Edges.Cast<Edge>().SelectMany(x => x.Tessellate()).ToList();
                    var u = pts.Select(p => (p - start).DotProduct(along)).ToList();
                    out_.Add($"u {u.Min() * 12:0.###}..{u.Max() * 12:0.###} in, z {(pts.Min(p => p.Z) - walk) * 12:0.###}..{(pts.Max(p => p.Z) - walk) * 12:0.###} in");
                }
                else if (o is GeometryInstance gi && gi.GetInstanceGeometry() is { } inner)
                    Walk(inner);
            }
        }
        if (e?.get_Geometry(new Options { DetailLevel = ViewDetailLevel.Fine }) is { } geometry)
            Walk(geometry);
        return out_;
    }

    /// <summary>Each level guard: the floor along its walking side (a DirectShape in Floors, its top the walking
    /// surface), a wall at its start and a post (a short wall) at its end, committed and regenerated first; then the
    /// railing along the floor's edge from the wall's face to the post's, its type's rails and balusters the drawing's.</summary>
    private static void DrawGuards(Document doc, List<JsonObject> guards, Dictionary<double, Level> levels, Dictionary<string, string> ids,
                                   List<string> log, FamilySymbol profile, Dictionary<string, FamilySymbol> balusters, double rail)
    {
        var floors = Category(doc, BuiltInCategory.OST_Floors);
        using (var t = new Transaction(doc, "Gordium: what the guards stand on and end against"))
        {
            t.Start();
            foreach (var g in guards)
            {
                var z = D(g["level"]);
                if (!levels.TryGetValue(z, out var level))
                    levels[z] = level = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                        .FirstOrDefault(l => Math.Abs(l.ProjectElevation - z) < 1e-9) ?? Level.Create(doc, z);
                var shape = DirectShape.CreateElement(doc, floors);
                shape.Name = $"Floor at the guard {g["id"]}";
                shape.SetShape([Prism(g["floor"]!.AsArray().Select(p => P(p!)).ToList(), z - D(g["slab"]), D(g["slab"]))]);
                foreach (var w in g["end_walls"]!.AsArray().Select(n => n!.AsObject()))
                {
                    var (ax, ay) = P(w["line"]![0]!);
                    var (bx, by) = P(w["line"]![1]!);
                    Wall.Create(doc, Line.CreateBound(new XYZ(ax, ay, z), new XYZ(bx, by, z)), WallTypeOf(doc, D(w["thickness"])).Id, level.Id,
                                D(g["wall_top"]), 0, false, false);
                }
            }
            doc.Regenerate();
            t.Commit();
        }
        foreach (var g in guards)
        {
            var id = g["id"]!.GetValue<string>();
            var z = D(g["level"]);
            using var t = new Transaction(doc, "Gordium: a guard");
            t.Start();
            var type = RailingTypeOf(doc, $"Gordium test guard {id}", profile, D(g["top_rail"]!["top"]),
                                     g["rails"]!.AsArray().Select(r => D(r!["top"])), balusters[id], g["balusters"]!.AsObject(), log);
            Set(type.get_Parameter(Marks.TopRailIsHandrail.Guid), 0, Marks.TopRailIsHandrail.Name);
            var (ax, ay) = P(g["start"]!);
            var (bx, by) = P(g["end"]!);
            var loop = new CurveLoop();
            loop.Append(Line.CreateBound(new XYZ(ax, ay, z), new XYZ(bx, by, z)));
            var railing = Railing.Create(doc, loop, type.Id, levels[z].Id);
            if (railing.get_Parameter(BuiltInParameter.STAIRS_RAILING_HEIGHT_OFFSET) is { IsReadOnly: false } offset)
                offset.Set(0.0);
            doc.Regenerate();
            t.Commit();
            var topRail = doc.GetElement(railing.TopRail);
            var box = railing.get_BoundingBox(null);
            var topBox = topRail?.get_BoundingBox(null);
            log.Add($"guard {id}: railing {railing.Id.Value} on level {levels[z].Name} ({z:0.###} ft), box {box?.Min.X:0.####},{box?.Min.Y:0.####},{box?.Min.Z:0.####} to " +
                    $"{box?.Max.X:0.####},{box?.Max.Y:0.####},{box?.Max.Z:0.####}; top rail {railing.TopRail.Value} box {topBox?.Min.Z:0.####} to {topBox?.Max.Z:0.####} " +
                    $"(drawing {z + D(g["top_rail"]!["bottom"]):0.####} to {z + D(g["top"]):0.####}), rail {rail * 12:0.###} in");
            // what was drawn, member by member (u along it, z over the walking surface), beside the house's
            var startPt = new XYZ(ax, ay, z);
            var dir = (new XYZ(bx, by, z) - startPt).Normalize();
            var b = g["balusters"]!;
            var data = new List<string> { $"top rail u 0..{D(g["length"]) * 12:0.###}, z {D(g["top_rail"]!["bottom"]) * 12:0.###}..{D(g["top_rail"]!["top"]) * 12:0.###}" };
            data.AddRange(g["rails"]!.AsArray().Select(rr => $"rail u 0..{D(g["length"]) * 12:0.###}, z {D(rr!["bottom"]) * 12:0.###}..{D(rr["top"]) * 12:0.###}"));
            for (var k = 0; k < b["count"]!.GetValue<int>(); k++)
            {
                var left = D(b["first"]) + k * D(b["spacing"]);
                data.Add($"baluster u {left * 12:0.###}..{(left + D(b["width"])) * 12:0.###}, z {D(b["bottom"]) * 12:0.###}..{D(b["top"]) * 12:0.###}");
            }
            log.Add($"guard {id}: drawn: " + string.Join("; ", SolidsAlong(railing, startPt, dir, z).Concat(SolidsAlong(topRail, startPt, dir, z))) +
                    " || the house's: " + string.Join("; ", data));
            ids[id] = railing.UniqueId;
        }
    }

    // ---- stairs (step 4) ----------------------------------------------------------------------------------------

    /// <summary>Each flight as a component stair (one straight run of equal risers, its riser count and tread depth the
    /// drawing's, its type's nosing length 0 and supports none), with its side walls, the floor at its foot and head as
    /// thin DirectShapes in Floors and what is overhead as thin DirectShapes in Ceilings (no joins: a real floor or
    /// wall could join and split the faces read). The lessons of step 3 kept: what the stair stands among is committed
    /// and regenerated before the stair is made (a StairsEditScope needs no transaction open anyway), and the document
    /// is regenerated once it is, before anything is read. The architect's tick ("these are all the stairs") is set, as
    /// the architect would once every stair is drawn. Every number Revit gives back is logged.</summary>
    private static void DrawStairs(Document doc, List<JsonObject> stairs, Dictionary<double, Level> levels,
                                   Dictionary<string, string> ids, List<string> log, FamilySymbol? profile, JsonObject house)
    {
        var floors = Category(doc, BuiltInCategory.OST_Floors);
        var ceilings = Category(doc, BuiltInCategory.OST_Ceilings);
        var made = new List<(JsonObject St, Level Base, Level Top, StairsType Type)>();
        using (var t = new Transaction(doc, "Gordium: what the stairs stand among"))
        {
            t.Start();
            Level LevelAt(double z)
            {
                if (levels.TryGetValue(z, out var lv))
                    return lv;
                lv = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                    .FirstOrDefault(l => Math.Abs(l.ProjectElevation - z) < 1e-9) ?? Level.Create(doc, z);
                levels[z] = lv;
                return lv;
            }
            foreach (var st in stairs)
            {
                var id = st["id"]!.GetValue<string>();
                double b = D(st["base"]), slab = D(st["slab"]);
                var baseLevel = LevelAt(b);
                var topLevel = LevelAt(D(st["head_top"]));
                if (st["upper_floor"] is JsonObject upper)
                {
                    // the floor the flight arrives at, one floor with the stairwell as an opening in it (its edge on the
                    // last riser's line), as a real model has it: the outline anticlockwise, the opening clockwise
                    var top = D(upper["top"]);
                    CurveLoop Loop(JsonNode ring, bool anticlockwise)
                    {
                        var pts = ring.AsArray().Select(p => P(p!)).ToList();
                        var area = 0.0;
                        for (var i = 0; i < pts.Count; i++)
                            area += pts[i].X * pts[(i + 1) % pts.Count].Y - pts[(i + 1) % pts.Count].X * pts[i].Y;
                        if ((area > 0) != anticlockwise)
                            pts.Reverse();
                        var loop = new CurveLoop();
                        for (var i = 0; i < pts.Count; i++)
                            loop.Append(Line.CreateBound(new XYZ(pts[i].X, pts[i].Y, top - slab), new XYZ(pts[(i + 1) % pts.Count].X, pts[(i + 1) % pts.Count].Y, top - slab)));
                        return loop;
                    }
                    var shape = DirectShape.CreateElement(doc, floors);
                    shape.Name = $"Upper floor at the head of {id}, with its stairwell opening";
                    shape.SetShape([GeometryCreationUtilities.CreateExtrusionGeometry([Loop(upper["outer"]!, true), Loop(upper["hole"]!, false)], XYZ.BasisZ, slab)]);
                }
                foreach (var key in new[] { "foot", "head" })
                {
                    if (st[key] is null)
                        continue;
                    var plan = st[key]!["plan"]!.AsArray().Select(p => P(p!)).ToList();
                    var top = D(st[key]!["top"]);
                    var shape = DirectShape.CreateElement(doc, floors);
                    shape.Name = $"Floor at the {key} of {id}";
                    shape.SetShape([Prism(plan, top - slab, slab)]);
                }
                foreach (var (piece, k) in st["overhead"]!.AsArray().Select((p, k) => (p!.AsArray(), k)))
                {
                    var pts = piece.Select(p => new XYZ(D(p![0]), D(p[1]), D(p[2]))).ToList();
                    var loop = new CurveLoop();
                    for (var i = 0; i < pts.Count; i++)
                        loop.Append(Line.CreateBound(pts[i], pts[(i + 1) % pts.Count]));
                    var shape = DirectShape.CreateElement(doc, ceilings);
                    shape.Name = $"Overhead {k + 1} of {id}";
                    shape.SetShape([GeometryCreationUtilities.CreateExtrusionGeometry([loop], XYZ.BasisZ, CeilingThickness)]);
                }
                var thick = D(st["wall_thickness"]);
                foreach (var w in st["walls"]!.AsArray().Select(n => n!.AsObject()))
                {
                    var (fx0, fy0) = P(w["face"]![0]!);
                    var (fx1, fy1) = P(w["face"]![1]!);
                    var (ox, oy) = P(w["outward"]!);
                    var line = Line.CreateBound(new XYZ(fx0 + ox * thick / 2, fy0 + oy * thick / 2, b), new XYZ(fx1 + ox * thick / 2, fy1 + oy * thick / 2, b));
                    Wall.Create(doc, line, WallTypeOf(doc, thick).Id, baseLevel.Id, D(st["wall_top"]) - b, 0, false, false);
                }
                made.Add((st, baseLevel, topLevel, StairTypeOf(doc, st, log)));
            }
            var tick = doc.ProjectInformation.get_Parameter(Marks.AllStairs.Guid);
            Set(tick, 1, Marks.AllStairs.Name);
            doc.Regenerate();
            t.Commit();
        }
        foreach (var (st, baseLevel, topLevel, type) in made)
        {
            var id = st["id"]!.GetValue<string>();
            var warnings = new List<string>();
            using var scope = new StairsEditScope(doc, "Gordium: a test stair");
            var stairsId = scope.Start(baseLevel.Id, topLevel.Id);
            StairsRun run;
            using (var t = new Transaction(doc, "Gordium: its run"))
            {
                t.Start();
                var s = (Stairs)doc.GetElement(stairsId);
                s.ChangeTypeId(type.Id);
                Set(s.get_Parameter(BuiltInParameter.STAIRS_BASE_OFFSET), 0.0, "the stair's base offset");
                // the floor at the head this far above the run's top: house 3's tall riser, where Revit makes one
                Set(s.get_Parameter(BuiltInParameter.STAIRS_TOP_OFFSET), -D(st["head_above_run"]), "the stair's top offset");
                s.DesiredRisersNumber = st["risers"]!.GetValue<int>();
                s.ActualTreadDepth = D(st["tread"]);
                doc.Regenerate();
                var (x0, y0) = P(st["path"]![0]!);
                var (x1, y1) = P(st["path"]![1]!);
                var b = D(st["base"]);
                run = StairsRun.CreateStraightRun(doc, stairsId, Line.CreateBound(new XYZ(x0, y0, b), new XYZ(x1, y1, b)), StairsRunJustification.Center);
                run.ActualRunWidth = D(st["width"]);
                var options = t.GetFailureHandlingOptions();
                options.SetFailuresPreprocessor(new Warnings(warnings));
                t.SetFailureHandlingOptions(options);
                t.Commit();
            }
            scope.Commit(new Warnings(warnings));
            using (var t = new Transaction(doc, "Gordium: regenerate after the stair"))
            {
                t.Start();
                // a railing Revit added on its own isn't the drawing's: the drawing's handrails are drawn next (step 5)
                if (((Stairs)doc.GetElement(stairsId)).GetAssociatedRailings() is { Count: > 0 } railings)
                {
                    log.Add($"stair {id}: {railings.Count} railings Revit added deleted (the drawing's own are drawn next)");
                    doc.Delete(railings);
                }
                doc.Regenerate();
                t.Commit();
            }
            if (st["handrails"] is JsonArray { Count: > 0 })
                DrawHandrails(doc, stairsId, st, profile!, D(house["handrail_top"]), log);
            var stair = (Stairs)doc.GetElement(stairsId);
            run = (StairsRun)doc.GetElement(run.Id);
            log.Add($"stair {id}: risers {stair.ActualRisersNumber} (drawing {st["risers"]}), riser {stair.ActualRiserHeight * 12:0.######} in " +
                    $"(drawing {D(st["riser"]) * 12:0.######}), tread {stair.ActualTreadDepth * 12:0.######} in, base {stair.BaseElevation:0.######}, " +
                    $"top {stair.TopElevation:0.######}; run risers {run.ActualRisersNumber}, treads {run.ActualTreadsNumber}, width " +
                    $"{run.ActualRunWidth * 12:0.######} in, supports {stair.GetStairsSupports().Count}, railings {stair.GetAssociatedRailings().Count}; " +
                    "warnings dismissed: " + (warnings.Count == 0 ? "none" : string.Join(" | ", warnings)));
            // what isn't the drawing is an error, never a stair drawn differently
            if (run.ActualRisersNumber != st["risers"]!.GetValue<int>() || Math.Abs(stair.ActualRiserHeight - D(st["riser"])) > 1e-9
                || Math.Abs(stair.ActualTreadDepth - D(st["tread"])) > 1e-9)
                throw new InvalidOperationException($"stair {id} came out unlike the drawing: {log[^1]}");
            ids[id] = run.UniqueId;
        }
    }

    private const double CeilingThickness = 1.0 / 12;

    private static ElementId Category(Document doc, BuiltInCategory c) =>
        DirectShape.IsValidCategoryId(new ElementId(c), doc) ? new ElementId(c)
            : throw new InvalidOperationException($"a DirectShape can't be in {c} here");

    private static Solid Prism(List<(double X, double Y)> plan, double z, double height)
    {
        var loop = new CurveLoop();
        for (var i = 0; i < plan.Count; i++)
            loop.Append(Line.CreateBound(new XYZ(plan[i].X, plan[i].Y, z), new XYZ(plan[(i + 1) % plan.Count].X, plan[(i + 1) % plan.Count].Y, z)));
        return GeometryCreationUtilities.CreateExtrusionGeometry([loop], XYZ.BasisZ, height);
    }

    /// <summary>A stair type of the project's first, duplicated for the drawing: its riser and tread limits wide
    /// enough for the drawing's (so Revit doesn't refuse or warn), its run width the drawing's, no side or middle
    /// supports (a stringer would stand inside the side walls), and a run type of its own with no nosing (the drawing's
    /// nosings are the riser lines). Each setting Revit refuses is logged, not hidden.</summary>
    private static StairsType StairTypeOf(Document doc, JsonObject st, List<string> log)
    {
        var name = $"Gordium test stair {st["id"]}";
        var types = new FilteredElementCollector(doc).OfClass(typeof(StairsType)).Cast<StairsType>().ToList();
        var basic = types.FirstOrDefault() ?? throw new InvalidOperationException("no stair type in a new project");
        var type = (StairsType)basic.Duplicate(name);
        type.MaxRiserHeight = D(st["riser"]) + 1.0 / 12;
        type.MinTreadDepth = D(st["tread"]);
        type.MinRunWidth = D(st["width"]);
        foreach (var p in new[] { BuiltInParameter.STAIRSTYPE_HAS_LEFT_SUPPORT, BuiltInParameter.STAIRSTYPE_HAS_RIGHT_SUPPORT,
                                  BuiltInParameter.STAIRSTYPE_HAS_INTERMEDIATE_SUPPORT })
            if (type.get_Parameter(p) is not { IsReadOnly: false } param || !param.Set(0))
                log.Add($"stair type {name}: {p} couldn't be set to none");
        var runType = (StairsRunType)((ElementType)doc.GetElement(type.RunType)).Duplicate(name + " run");
        runType.NosingLength = 0;
        type.RunType = runType.Id;
        log.Add($"stair type {name} from \"{basic.Name}\": run type monolithic {runType.IsMonolithic}, risers {runType.HasRisers}, " +
                $"treads {runType.HasTreads}, tread {runType.TreadThickness * 12:0.###} in thick, nosing {runType.NosingLength * 12:0.###} in");
        return type;
    }

    /// <summary>Takes Revit's warnings out of the way (each kept for the log); an error is left to roll back.</summary>
    private sealed class Warnings(List<string> seen) : IFailuresPreprocessor
    {
        public FailureProcessingResult PreprocessFailures(FailuresAccessor failures)
        {
            foreach (var f in failures.GetFailureMessages())
            {
                seen.Add($"{f.GetSeverity()}: {f.GetDescriptionText()}");
                if (f.GetSeverity() == FailureSeverity.Warning)
                    failures.DeleteWarning(f);
            }
            return FailureProcessingResult.Continue;
        }
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

    /// <summary>A floor type one layer <paramref name="thickness"/> thick (its top the level), made once per thickness
    /// from the project's own.</summary>
    private static FloorType FloorTypeOf(Document doc, FloorType basic, double thickness)
    {
        var name = $"Gordium test floor {thickness * 12:0.###} in";
        if (new FilteredElementCollector(doc).OfClass(typeof(FloorType)).Cast<FloorType>().FirstOrDefault(x => x.Name == name) is { } found)
            return found;
        var made = (FloorType)basic.Duplicate(name);
        var structure = CompoundStructure.CreateSingleLayerCompoundStructure(MaterialFunctionAssignment.Structure,
                                                                             thickness, ElementId.InvalidElementId);
        structure.EndCap = EndCapCondition.NoEndCap;   // a floor's structure has no end cap (Revit refuses one)
        made.SetCompoundStructure(structure);
        return made;
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
    private static string WindowTemplate(RevitApplication app) => Template(app, "Window.rft");

    /// <summary>One of Revit's own family templates by file name (<c>Door.rft</c>, <c>Baluster.rft</c>,
    /// <c>Profile-Rail.rft</c>), where <see cref="WindowTemplate"/> looks.</summary>
    internal static string Template(RevitApplication app, string file)
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
            var path = Path.Combine(dir, file);
            tried.Add(path);
            if (File.Exists(path))
                return path;
        }
        throw new InvalidOperationException($"Revit's {file} wasn't found (looked in " + string.Join("; ", tried) + ")");
    }

    /// <summary>A window family of this window's size, made from Window.rft (whose opening cuts the wall from the
    /// Sill reference plane to the Top one): a frame solid filling the opening, half the template wall's thickness
    /// deep, centred in it. One family per window, so each window has a type of its own. Loaded into the project, named
    /// <paramref name="familyName"/> when given (a model built from data: ModelBuild).</summary>
    internal static FamilySymbol WindowFamily(RevitApplication app, Document project, JsonObject w, string? familyName = null)
    {
        var id = w["id"]!.GetValue<string>();
        double width = D(w["width"]), height = D(w["height"]);
        var name = familyName ?? $"Gordium test window {id} ({width * 12:0.###} x {height * 12:0.###} in)";
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
                // the opening it cuts in its wall is the template's own (Revit 2027.4's Window.rft has one): without it
                // nothing would be cut, and the reader would find no wall opening (and send no clear opening)
                if (new FilteredElementCollector(fdoc).OfClass(typeof(Opening)).GetElementCount() == 0)
                    throw new InvalidOperationException("Window.rft has no opening to cut the wall");
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

    internal static FamilyParameter FamilyParameterOf(FamilyManager fm, BuiltInParameter first, BuiltInParameter second, string name) =>
        fm.get_Parameter(first) ?? fm.get_Parameter(second) ?? fm.get_Parameter(name)
        ?? throw new InvalidOperationException($"Window.rft has no {name} parameter (it has: " +
                                               string.Join(", ", fm.Parameters.Cast<FamilyParameter>().Select(p => p.Definition.Name).Order()) + ")");
}
