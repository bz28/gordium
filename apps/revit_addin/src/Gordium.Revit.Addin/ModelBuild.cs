using System.Globalization;
using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.Structure;
using Gordium.Revit.Reading;
using RevitApplication = Autodesk.Revit.ApplicationServices.Application;

namespace Gordium.Revit.Addin;

/// <summary>
/// A Revit model built, with no click, from a drawing script's building data: the C# port of the pyRevit/Dynamo script
/// Ben received (the Children's Odyssey childcare centre, 19 Libby St, Portland ME, rebuilt from its life-safety sheet
/// LS1.0), its data taken out of the script's text by apps/revit_addin/tools/extract_build_data.py (the script itself is
/// never run). Asked for by request file (build_model_request.json, beside the trial log:
/// <c>{"data": "&lt;data&gt;.json", "template": "&lt;optional .rte&gt;", "save_as": "&lt;model&gt;.rvt"}</c>, plus the
/// script's toggles <c>swing_opposite_facing</c>, <c>hinge_opposite_hand</c> and <c>use_phases</c>, each true when not
/// given), read while Revit is idle.
/// <para>As the script: a new project from Revit's own imperial architectural template (English-Imperial\default.rte);
/// Level 1 and its floor plan; a wall type per thickness, status and rating (<c>LS Existing 12"</c>, one layer of the
/// generic wall's core material, its Fire Rating set); each wall on its centre line, its Comments (status, SMOKE
/// PARTITION, rating, PARTIAL HEIGHT), Mark W&lt;id&gt; and, when Existing, the project's first phase; a door type per
/// kind and size from the template's own families (or Revit's library, or, when there is no double door, a family made
/// from Revit's Door.rft), each door in its wall (Mark D01...), its facing and hand flipped to swing and hinge as the data
/// says; a window type per size (Mark WN01..., at its sill); the floor under the footprint; and a Room at each tag point
/// with its Name (in capitals, as the script) and Number, tagged in the plan. Then saved as the request's .rvt and closed.</para>
/// <para>Data with several levels (apps/revit_addin/tools/evals/make_ny_build_data.py: the New York eval's buildings): each
/// level and its plan (the template's levels the data doesn't have deleted), each wall and room on its own level and
/// each door and window on its wall's, the data's floor slabs (a type per thickness, its top at its offset) in place of
/// the footprint's floor, each room's ceiling a thin solid in Ceilings (as HouseDraw draws one), its room separation
/// lines, the lot as a property line and its spot grades as Gordium's spot-grade markers. A door with no swing in the
/// data is left as Revit places it.</para>
/// <para>Unlike the script, nothing fails quietly: every element Revit refused or removed is in the log with Revit's
/// reason, the counts drawn are set beside the data's, and each door's flips and each room's area (Revit's beside the
/// sheet's) are logged.</para>
/// </summary>
internal static class ModelBuild
{
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "build_model_request.json");

    internal static void Run(RevitApplication app, string requestFile)
    {
        var log = new Dictionary<string, object?> { ["request"] = requestFile };
        Document? doc = null;
        try
        {
            var raw = JsonNode.Parse(File.ReadAllText(requestFile, Encoding.UTF8));
            var request = BuildRequest.Parse(raw);
            // the old flip conventions: read, never used (each door's swing is read back from what Revit draws)
            var unused = new[] { "swing_opposite_facing", "hinge_opposite_hand" }.Where(k => raw is JsonObject o && o.ContainsKey(k)).ToList();
            log["data"] = request.Data;
            log["save_as"] = request.SaveAs;
            var model = BuildData.Parse(JsonNode.Parse(File.ReadAllText(request.Data, Encoding.UTF8)));
            log["project"] = model.Project;
            log["source"] = model.SourceFile is null ? null : $"{model.SourceFile} (sha256 {model.SourceSha256})";
            // the request's corrections to the data, each applied or refused in words, never silently
            var (corrected, applied, refused) = BuildData.Correct(model, request.Corrections);
            model = corrected;
            log["corrections"] = applied;
            log["corrections_refused"] = refused;
            var template = ProjectTemplate(app, request.Template);
            log["template"] = template;
            doc = app.NewProjectDocument(template);
            var report = new Report();
            report.Failed.AddRange(refused.Select(r => $"correction not applied: {r}"));
            if (unused.Count > 0)
                report.Notes.Add($"{string.Join(" and ", unused)} given: not used (each door is flipped until the swing its plan symbol draws is the data's)");
            Build(app, doc, model, request, report);
            report.Into(log);
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(request.SaveAs))!);
            doc.SaveAs(request.SaveAs, new SaveAsOptions { OverwriteExistingFile = true });
            log["saved"] = request.SaveAs;
            log["ok"] = true;
            log["all_built"] = report.Failed.Count == 0;
        }
        catch (BuildDataException x)
        {
            log["error"] = "the request or its data can't be built from";
            log["problems"] = x.Problems;
        }
        catch (Exception x)
        {
            log["error"] = $"{x.GetType().Name}: {x.Message}";
            log["where"] = x.StackTrace?.Split('\n').Take(6).Select(s => s.Trim()).ToList();
        }
        finally
        {
            doc?.Close(false);
        }
        Trial.Log("build_model", log);
    }

    /// <summary>What was built, what wasn't (each with Revit's reason) and what Revit said along the way.</summary>
    private sealed class Report
    {
        public readonly Dictionary<string, object?> Counts = [];
        public readonly List<string> Failed = [], Notes = [], Doors = [], Rooms = [];
        public readonly Dictionary<string, int> Warnings = [];

        public void Into(Dictionary<string, object?> log)
        {
            log["counts"] = Counts;
            log["failed"] = Failed;
            log["notes"] = Notes;
            log["doors"] = Doors;
            log["rooms"] = Rooms;
            log["revit_warnings_dismissed"] = Warnings;
        }
    }

    /// <summary>Revit's own imperial architectural template, or the request's: <c>English-Imperial\default.rte</c> in
    /// Revit's template folder (where HouseDraw finds Revit's family templates, under Templates).</summary>
    private static string ProjectTemplate(RevitApplication app, string? asked)
    {
        if (asked is not null)
            return File.Exists(asked) ? asked : throw new InvalidOperationException($"the request's template {asked} doesn't exist");
        var tried = new List<string>
        {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Autodesk", $"RVT {app.VersionNumber}",
                         "Templates", "English-Imperial", "default.rte"),
        };
        if (!string.IsNullOrEmpty(app.DefaultProjectTemplate) && Path.GetDirectoryName(app.DefaultProjectTemplate) is { } dir)
            tried.Add(Path.Combine(dir, "English-Imperial", "default.rte"));
        return tried.FirstOrDefault(File.Exists)
               ?? throw new InvalidOperationException("Revit's imperial architectural template wasn't found (looked for " + string.Join("; ", tried) +
                                                      "): name one as the request's template");
    }

    private static void Build(RevitApplication app, Document doc, BuildModel model, BuildRequest request, Report report)
    {
        // ---- the levels and their plans (the data's one level, or each of its levels) ----
        var levels = new Dictionary<string, Level>();
        var plans = new Dictionary<string, ViewPlan>();
        Step(doc, "Gordium: the levels and their plans", report, [], _ =>
        {
            var several = model.Levels.Count > 1;
            var template = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>().ToList();
            foreach (var lv in model.Levels)
                levels[lv.Name] = template.FirstOrDefault(l => Math.Abs(l.Elevation - lv.ElevationFt) < 1e-6 && !levels.ContainsValue(l))
                                  ?? Level.Create(doc, lv.ElevationFt);
            if (several)
            {
                // the template's own levels the data doesn't have (Level 2 at 10 ft) taken out, so every level of the
                // model is the data's (a wall through an extra level would enclose areas there with no Room)
                foreach (var extra in template.Where(l => !levels.ContainsValue(l)))
                {
                    report.Notes.Add(I($"the template's level \"{extra.Name}\" at {extra.Elevation:0.###} ft deleted: not in the data"));
                    doc.Delete(extra.Id);
                }
            }
            foreach (var (name, level) in levels)
                if (level.Name != name && !new FilteredElementCollector(doc).OfClass(typeof(Level)).Any(l => l.Name == name))
                    level.Name = name;
            var planType = new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType)).Cast<ViewFamilyType>()
                               .FirstOrDefault(v => v.ViewFamily == ViewFamily.FloorPlan)
                           ?? throw new InvalidOperationException("the template has no floor plan view type");
            foreach (var (name, level) in levels)
                plans[name] = new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).Cast<ViewPlan>()
                                  .FirstOrDefault(v => !v.IsTemplate && v.ViewType == ViewType.FloorPlan && v.GenLevel?.Id == level.Id)
                              ?? ViewPlan.Create(doc, planType.Id, level.Id);
        });
        foreach (var lv in model.Levels)
            report.Notes.Add(I($"level \"{levels[lv.Name].Name}\" at {levels[lv.Name].Elevation:0.###} ft (the data's {lv.Name} at {lv.ElevationFt:0.###}), plan \"{plans[lv.Name].Name}\""));
        Level LevelOf(string? name) => levels[model.LevelOf(name).Name];
        ViewPlan PlanOf(string? name) => plans[model.LevelOf(name).Name];
        XYZ At(PlanPoint p, string? level, double above = 0) => new(p.X, p.Y, model.LevelOf(level).ElevationFt + above);
        string? WallLevel(int wall) => model.Walls.First(w => w.Id == wall).Level;

        // ---- phases ----
        var phases = doc.Phases;
        Phase? existing = BuildData.ExistingPhase(phases.Size, request.UsePhases) is { } k ? phases.get_Item(k) : null;
        report.Notes.Add($"phases: {string.Join(", ", Enumerable.Range(0, phases.Size).Select(i => phases.get_Item(i).Name))}; existing walls in " +
                         (existing?.Name ?? "the view's own phase (use_phases off or one phase)"));

        // ---- wall types, then walls ----
        var wallTypes = new Dictionary<string, WallType>();
        Step(doc, "Gordium: wall types", report, [], _ =>
        {
            var all = new FilteredElementCollector(doc).OfClass(typeof(WallType)).Cast<WallType>().ToList();
            var basic = all.FirstOrDefault(t => t.Kind == WallKind.Basic && t.Name.Contains("Generic"))
                        ?? all.FirstOrDefault(t => t.Kind == WallKind.Basic)
                        ?? throw new InvalidOperationException("the template has no basic wall type");
            var cs = basic.GetCompoundStructure();
            var material = cs is { LayerCount: > 0 } ? cs.GetLayers()[Math.Max(cs.GetFirstCoreLayerIndex(), 0)].MaterialId : ElementId.InvalidElementId;
            report.Notes.Add($"wall types from \"{basic.Name}\" (its core material {material.Value})");
            foreach (var w in model.Walls)
            {
                var name = BuildData.WallTypeName(w);
                if (wallTypes.ContainsKey(name))
                    continue;
                var type = all.FirstOrDefault(t => t.Name == name) ?? (WallType)basic.Duplicate(name);
                type.SetCompoundStructure(CompoundStructure.CreateSingleLayerCompoundStructure(MaterialFunctionAssignment.Structure,
                                                                                               w.ThicknessIn / 12, material));
                // missing, read-only or refused: a failure in the log (life-safety data), never dropped
                if (w.FireRating is { } rating)
                    Need(type.get_Parameter(BuiltInParameter.FIRE_RATING), rating, $"wall type {name}", "Fire Rating", report);
                wallTypes[name] = type;
            }
        });
        report.Counts["wall_types"] = wallTypes.Count;

        var walls = new Dictionary<int, Wall>();
        var made = new Dictionary<ElementId, string>();
        Step(doc, "Gordium: walls", report, made, _ =>
        {
            foreach (var w in model.Walls)
            {
                var label = $"wall {BuildData.WallMark(w)}";
                try
                {
                    var wall = Wall.Create(doc, Line.CreateBound(At(w.Start, w.Level), At(w.End, w.Level)), wallTypes[BuildData.WallTypeName(w)].Id, LevelOf(w.Level).Id,
                                           w.HeightFt, 0, false, false);
                    wall.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM)?.Set(0);      // its location line the centre line
                    // a trimmed end, a fill's ends: never joined (Revit deleted both walls of such a join)
                    if (w.NoJoinStart)
                        WallUtils.DisallowWallJoinAtEnd(wall, 0);
                    if (w.NoJoinEnd)
                        WallUtils.DisallowWallJoinAtEnd(wall, 1);
                    Need(wall.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS), BuildData.WallComment(w), label, "Comments", report);
                    Need(wall.get_Parameter(BuiltInParameter.ALL_MODEL_MARK), BuildData.WallMark(w), label, "Mark", report);
                    if (existing is not null && w.Status == "Existing")
                    {
                        try
                        {
                            wall.CreatedPhaseId = existing.Id;
                        }
                        catch (Exception x)
                        {
                            report.Failed.Add($"{label}: drawn, but left in New Construction, not {existing.Name}: {x.Message}");
                        }
                    }
                    walls[w.Id] = wall;
                    made[wall.Id] = label;
                }
                catch (Exception x)
                {
                    report.Failed.Add($"{label}: not drawn: {x.Message}");
                }
            }
        });
        foreach (var id in walls.Where(p => !p.Value.IsValidObject).Select(p => p.Key).ToList())
            walls.Remove(id);
        // a wall Revit removed at commit is drawn again alone, its joins disallowed at both ends, each in its own
        // transaction; the log says so either way (never a wall dropped in silence)
        foreach (var w in model.Walls.Where(w => !walls.ContainsKey(w.Id)).ToList())
        {
            var label = $"wall {BuildData.WallMark(w)}";
            var again = new Dictionary<ElementId, string>();
            Wall? redrawn = null;
            try
            {
                Step(doc, $"Gordium: wall {BuildData.WallMark(w)} again, its joins disallowed", report, again, _ =>
                {
                    redrawn = Wall.Create(doc, Line.CreateBound(At(w.Start, w.Level), At(w.End, w.Level)), wallTypes[BuildData.WallTypeName(w)].Id, LevelOf(w.Level).Id,
                                          w.HeightFt, 0, false, false);
                    redrawn.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM)?.Set(0);
                    WallUtils.DisallowWallJoinAtEnd(redrawn, 0);
                    WallUtils.DisallowWallJoinAtEnd(redrawn, 1);
                    Need(redrawn.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS), BuildData.WallComment(w), label, "Comments", report);
                    Need(redrawn.get_Parameter(BuiltInParameter.ALL_MODEL_MARK), BuildData.WallMark(w), label, "Mark", report);
                    if (existing is not null && w.Status == "Existing")
                        redrawn.CreatedPhaseId = existing.Id;
                    again[redrawn.Id] = label;
                });
            }
            catch (Exception x)
            {
                report.Failed.Add($"{label}: drawn again alone with its joins disallowed, and still not kept: {x.Message}");
                continue;
            }
            if (redrawn is { IsValidObject: true })
            {
                walls[w.Id] = redrawn;
                report.Notes.Add($"{label}: Revit removed it at the first commit; drawn again alone with its joins disallowed at both ends, and kept");
                report.Failed.RemoveAll(f => f.StartsWith(label + ":", StringComparison.Ordinal) && f.Contains("removed when Revit committed \"Gordium: walls\"", StringComparison.Ordinal));
            }
        }
        report.Counts["walls"] = new { data = model.Walls.Count, drawn = walls.Count };
        // Revit's "Highlighted walls overlap" warnings, named from the data: walls drawn as the data has them
        foreach (var o in BuildData.WallOverlaps(model.Walls))
            report.Notes.Add($"the data's {o.Words}");

        // ---- door and window types ----
        var types = OpeningTypes(app, doc, model, report);

        // ---- doors ----
        var doors = new List<(BuildDoor D, FamilyInstance Fi, bool Made)>();
        made.Clear();
        Step(doc, "Gordium: doors", report, made, _ =>
        {
            foreach (var d in model.Doors)
            {
                var label = $"door {BuildData.DoorMark(d)} ({d.Kind}, {BuildData.G(d.WidthIn)} x {BuildData.G(d.HeightIn)} in, in wall W{d.HostWall})";
                if (!walls.TryGetValue(d.HostWall, out var host))
                {
                    report.Failed.Add($"{label}: not placed: its wall W{d.HostWall} wasn't drawn");
                    continue;
                }
                if (!types.TryGetValue(DoorKey(d), out var t))
                {
                    report.Failed.Add($"{label}: not placed: no door type of its kind and size could be made");
                    continue;
                }
                try
                {
                    var fi = doc.Create.NewFamilyInstance(At(d.Center, WallLevel(d.HostWall)), t.Symbol, host, LevelOf(WallLevel(d.HostWall)), StructuralType.NonStructural);
                    Need(fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK), BuildData.DoorMark(d), label, "Mark", report);
                    doc.Regenerate();      // each opening cut into its wall as it is placed (HouseDraw's lesson)
                    if (fi.Host?.Id != host.Id)
                        report.Failed.Add($"{label}: placed, but hosted by {fi.Host?.Id.Value.ToString() ?? "nothing"}, not its wall");
                    doors.Add((d, fi, t.Made));
                    made[fi.Id] = label;
                }
                catch (Exception x)
                {
                    report.Failed.Add($"{label}: not placed: {x.Message}");
                }
            }
        });
        // flipped to swing and hinge as the data says, from what Revit draws (never a family's facing or hand
        // convention: Revit 2027's own Single-Flush swings toward its facing, the opposite of what was once assumed,
        // 2026-11-25): each door's swing read back from its plan symbol (RouteReader.ReadBuildSwings), its facing
        // flipped where the side read isn't the data's, read again, its hand flipped where the hinge read isn't, and
        // read once more; the log says what was read at the end, never what was meant
        SwingDoors(doc, doors, report, made);
        report.Counts["doors"] = new { data = model.Doors.Count, placed = doors.Count(x => x.Fi.IsValidObject) };

        // ---- windows ----
        var windows = new List<FamilyInstance>();
        made.Clear();
        Step(doc, "Gordium: windows", report, made, _ =>
        {
            foreach (var w in model.Windows)
            {
                var label = $"window {BuildData.WindowMark(w)} ({BuildData.G(w.WidthIn)} x {BuildData.G(w.HeightIn)} in, sill {BuildData.G(w.SillIn)} in, in wall W{w.HostWall})";
                if (!walls.TryGetValue(w.HostWall, out var host))
                {
                    report.Failed.Add($"{label}: not placed: its wall W{w.HostWall} wasn't drawn");
                    continue;
                }
                if (!types.TryGetValue(WindowKey(w), out var t))
                {
                    report.Failed.Add($"{label}: not placed: no window type of its size could be made");
                    continue;
                }
                try
                {
                    var fi = doc.Create.NewFamilyInstance(At(w.Center, WallLevel(w.HostWall), w.SillIn / 12), t.Symbol, host, LevelOf(WallLevel(w.HostWall)), StructuralType.NonStructural);
                    Need(fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM), w.SillIn / 12, label, "Sill Height", report);
                    Need(fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK), BuildData.WindowMark(w), label, "Mark", report);
                    doc.Regenerate();
                    if (fi.Host?.Id != host.Id)
                        report.Failed.Add($"{label}: placed, but hosted by {fi.Host?.Id.Value.ToString() ?? "nothing"}, not its wall");
                    windows.Add(fi);
                    made[fi.Id] = label;
                }
                catch (Exception x)
                {
                    report.Failed.Add($"{label}: not placed: {x.Message}");
                }
            }
        });
        report.Counts["windows"] = new { data = model.Windows.Count, placed = windows.Count(x => x.IsValidObject) };

        // ---- the floor (the script's: under the footprint), or the data's floor slabs ----
        made.Clear();
        var floors = new List<Floor>();
        CurveLoop Loop(IReadOnlyList<PlanPoint> outline, double z)
        {
            var loop = new CurveLoop();
            for (var i = 0; i < outline.Count; i++)
                loop.Append(Line.CreateBound(new XYZ(outline[i].X, outline[i].Y, z), new XYZ(outline[(i + 1) % outline.Count].X, outline[(i + 1) % outline.Count].Y, z)));
            return loop;
        }
        Step(doc, model.Floors.Count == 0 ? "Gordium: the floor" : "Gordium: the floor slabs", report, made, _ =>
        {
            var basic = new FilteredElementCollector(doc).OfClass(typeof(FloorType)).Cast<FloorType>().FirstOrDefault(f => !f.IsFoundationSlab);
            if (basic is null)
            {
                report.Failed.Add("the floor: not drawn: the template has no floor type");
                return;
            }
            if (model.Floors.Count == 0)
            {
                try
                {
                    var outline = BuildData.FloorOutline(model.Footprint);
                    var floor = Floor.Create(doc, [Loop(outline, model.LevelElevation)], basic.Id, LevelOf(null).Id);
                    floors.Add(floor);
                    made[floor.Id] = "the floor";
                    report.Notes.Add(I($"floor: type \"{basic.Name}\", {outline.Count} corners, {BuildData.Area(outline):0} sq ft inside its outline"));
                }
                catch (Exception x)
                {
                    report.Failed.Add($"the floor: not drawn: {x.Message}");
                }
                return;
            }
            foreach (var (f, k) in model.Floors.Select((f, k) => (f, k + 1)))
            {
                var label = I($"floor slab {k} on {f.Level} ({f.ThicknessIn:0.###} in, top {f.TopOffsetFt:0.###} ft above it)");
                try
                {
                    // a type of its thickness, one layer (HouseDraw's: the slab's underside is where the data puts it)
                    var type = HouseDraw.FloorTypeOf(doc, basic, f.ThicknessIn / 12);
                    var floor = Floor.Create(doc, [Loop(f.Outline, model.LevelOf(f.Level).ElevationFt)], type.Id, LevelOf(f.Level).Id);
                    if (Math.Abs(f.TopOffsetFt) > 1e-12)
                        Need(floor.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM), f.TopOffsetFt, label, "Height Offset From Level", report);
                    floors.Add(floor);
                    made[floor.Id] = label;
                    report.Notes.Add(I($"{label}: type \"{type.Name}\", {f.Outline.Count} corners, {BuildData.Area(f.Outline):0.#} sq ft"));
                }
                catch (Exception x)
                {
                    report.Failed.Add($"{label}: not drawn: {x.Message}");
                }
            }
        });
        report.Counts["floors"] = new { data = Math.Max(1, model.Floors.Count), drawn = floors.Count(f => f.IsValidObject) };

        // ---- the rooms' ceilings (thin solids in Ceilings, as HouseDraw draws them), the room separation lines ----
        if (model.Ceilings.Count > 0 || model.Separations.Count > 0)
        {
            var drawnCeilings = 0;
            made.Clear();
            Step(doc, "Gordium: ceilings and room separation lines", report, made, _ =>
            {
                var category = new ElementId(DirectShape.IsValidCategoryId(new ElementId(BuiltInCategory.OST_Ceilings), doc)
                    ? BuiltInCategory.OST_Ceilings : BuiltInCategory.OST_GenericModel);
                foreach (var c in model.Ceilings)
                {
                    var label = $"ceiling {c.Name}";
                    try
                    {
                        var shape = DirectShape.CreateElement(doc, category);
                        // Revit refuses \ : { } [ ] | ; < > ? ` ~ in an element's name
                        shape.Name = new string(label.Select(ch => @"\:{}[]|;<>?`~".Contains(ch) ? '-' : ch).ToArray());
                        shape.SetShape([GeometryCreationUtilities.CreateExtrusionGeometry([Loop(c.Outline, c.UndersideFt)], XYZ.BasisZ, c.ThicknessIn / 12)]);
                        made[shape.Id] = label;
                        drawnCeilings++;
                    }
                    catch (Exception x)
                    {
                        report.Failed.Add($"{label}: not drawn: {x.Message}");
                    }
                }
                foreach (var group in model.Separations.GroupBy(s => s.Level))
                {
                    var curves = new CurveArray();
                    var z = model.LevelOf(group.Key).ElevationFt;
                    foreach (var s in group)
                        curves.Append(Line.CreateBound(new XYZ(s.Start.X, s.Start.Y, z), new XYZ(s.End.X, s.End.Y, z)));
                    try
                    {
                        doc.Create.NewRoomBoundaryLines(SketchPlane.Create(doc, LevelOf(group.Key).Id), curves, PlanOf(group.Key));
                    }
                    catch (Exception x)
                    {
                        report.Failed.Add($"the room separation lines on {group.Key}: not drawn: {x.Message}");
                    }
                }
            });
            report.Counts["ceilings"] = new { data = model.Ceilings.Count, drawn = drawnCeilings };
            report.Counts["separations"] = model.Separations.Count;
        }

        // ---- the lot (a property line) and the ground (Gordium's spot-grade markers) ----
        if (model.Lot is not null || model.SpotGrades.Count > 0)
        {
            made.Clear();
            Step(doc, "Gordium: the lot and the ground", report, made, _ =>
            {
                if (model.Lot is { } ring)
                {
                    try
                    {
                        var line = PropertyLine.Create(doc, [Loop(ring, 0)]);
                        made[line.Id] = "the lot";
                        report.Notes.Add(I($"the lot: a property line of {ring.Count} sides, {BuildData.Area(ring):0.#} sq ft inside it"));
                    }
                    catch (Exception x)
                    {
                        report.Failed.Add($"the lot: not drawn: {x.Message}");
                    }
                }
                foreach (var (s, k) in model.SpotGrades.Select((s, k) => (s, k + 1)))
                {
                    var ds = DirectShape.CreateElement(doc, new ElementId(BuiltInCategory.OST_GenericModel));
                    ds.ApplicationId = RevitRead.MarkApplication;
                    ds.ApplicationDataId = RevitRead.SpotMark;
                    ds.SetShape(new List<GeometryObject> { Autodesk.Revit.DB.Point.Create(new XYZ(s.X, s.Y, s.Z)) });
                    made[ds.Id] = I($"spot grade {k} at ({s.X:0.###}, {s.Y:0.###}, {s.Z:0.###})");
                }
            });
            report.Counts["lot"] = model.Lot is null ? 0 : 1;
            report.Counts["spot_grades"] = model.SpotGrades.Count;
        }

        // ---- rooms ----
        var rooms = new List<(BuildRoom R, Room Room)>();
        made.Clear();
        Step(doc, "Gordium: rooms", report, made, _ =>
        {
            doc.Regenerate();
            foreach (var r in model.Rooms)
            {
                var label = $"room {r.Number} {r.Name}";
                try
                {
                    var uv = new UV(r.TagPoint.X, r.TagPoint.Y);
                    var room = doc.Create.NewRoom(LevelOf(r.Level), uv) ?? throw new InvalidOperationException("Revit placed no room");
                    room.Name = r.Name.ToUpperInvariant();
                    room.Number = r.Number;
                    rooms.Add((r, room));
                    made[room.Id] = label;
                    try
                    {
                        doc.Create.NewRoomTag(new LinkElementId(room.Id), uv, PlanOf(r.Level).Id);
                    }
                    catch (Exception x)
                    {
                        report.Notes.Add($"{label}: placed, but not tagged in {PlanOf(r.Level).Name}: {x.Message}");
                    }
                }
                catch (Exception x)
                {
                    report.Failed.Add($"{label}: not placed: {x.Message}");
                }
            }
        });
        // the walls Revit drew (a wall of the data not drawn leaves its rooms open, and is named so)
        foreach (var (r, room) in rooms.Where(x => x.Room.IsValidObject))
        {
            // the walls on the room's own level (a wall of another level, over or under it, bounds nothing here)
            var drawnWalls = model.Walls.Where(w => walls.ContainsKey(w.Id) && model.LevelOf(w.Level) == model.LevelOf(r.Level)).ToList();
            var inside = BuildData.Area(r.Boundary);
            var line = I($"{room.Number} {room.Name}: Revit's area {room.Area:0.#} sq ft, the sheet's {(r.AreaSf is { } a ? a.ToString("0.#", CultureInfo.InvariantCulture) : "none")}, ") +
                       I($"inside its boundary {inside:0.#}");
            // where the drawn walls leave its boundary open: Revit bounds a room by walls alone, drawn where the data
            // ends them, so a gap the tracing left is said here, never closed by the builder
            var gaps = BuildData.BoundaryGaps(r, drawnWalls);
            string Words(BuildData.BoundaryGap g)
            {
                var mid = new PlanPoint((g.From.X + g.To.X) / 2, (g.From.Y + g.To.Y) / 2);
                var undrawn = model.Walls.Where(w => !walls.ContainsKey(w.Id) && BuildData.DistanceToWall(mid, w) <= 0.25).Select(w => BuildData.WallMark(w)).ToList();
                return g.Words + (undrawn.Count > 0 ? $" (where the data has {string.Join(", ", undrawn)}, which wasn't drawn)" : "");
            }
            var open = gaps.Count == 0 ? "" : "; the drawn walls leave its boundary open: " + string.Join("; ", gaps.Select(Words));
            if (room.Area <= 0)
            {
                line += ": NOT ENCLOSED (Revit found no walls around its tag point)" + open;
                report.Failed.Add($"room {r.Number} {r.Name}: placed, but not enclosed by walls (area 0)" +
                                  (gaps.Count == 0 ? ": no gap in the drawn walls along its boundary (look at the walls Revit ignored as overlapping)" : open));
            }
            else
            {
                line += open;
                // a room enclosed, but not the sheet's: a wrong test model is a wrong test
                if (BuildData.RoomAreaOff(room.Area, r) is { } off)
                {
                    line += $": AREA OFF ({off})";
                    report.Failed.Add($"room {r.Number} {r.Name}: area off: {off}");
                }
            }
            report.Rooms.Add(line);
        }
        report.Counts["rooms"] = new { data = model.Rooms.Count, placed = rooms.Count(x => x.Room.IsValidObject),
                                       enclosed = rooms.Count(x => x.Room.IsValidObject && x.Room.Area > 0) };
    }

    // ---- door and window types ------------------------------------------------------------------------------------

    private sealed record OpeningType(FamilySymbol Symbol, bool Made);

    private static string DoorKey(BuildDoor d) => $"{d.Kind} {d.WidthIn} {d.HeightIn}";

    private static string WindowKey(BuildWindow w) => $"window {w.WidthIn} {w.HeightIn}";

    /// <summary>A type per door kind and size and per window size. As the script: the template's own door and window
    /// families (picked by its keywords), loaded from Revit's library when the template has none; each size a type
    /// duplicated from the family's and its Width and Height set. Where there is no such family (no double door, as in
    /// Revit 2027's install, whose library is online), or a size can't be set, a family of the size is made from Revit's
    /// own Door.rft (its leaves and their swing drawn) or Window.rft (HouseDraw's), never a door placed as another kind.</summary>
    private static Dictionary<string, OpeningType> OpeningTypes(RevitApplication app, Document doc, BuildModel model, Report report)
    {
        List<FamilySymbol> Symbols(BuiltInCategory c) =>
            new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).OfCategory(c).Cast<FamilySymbol>().ToList();
        string Label(FamilySymbol s) => s.FamilyName + " " + s.Name;

        // the script's library paths, and Revit's own library folders (its Imperial Library: Libraries\English-Imperial\US)
        IEnumerable<string> Library(string sub, params string[] names)
        {
            var roots = new List<string>();
            for (var year = 2027; year >= 2020; year--)
                foreach (var folder in new[] { "English-Imperial", "English_I" })
                    roots.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Autodesk", $"RVT {year}", "Libraries", folder));
            roots.AddRange(app.GetLibraryPaths().Values);
            return roots.SelectMany(r => names.Select(n => Path.Combine(r, sub, n)));
        }
        string? Load(IEnumerable<string> paths)
        {
            foreach (var p in paths.Where(File.Exists))
                if (doc.LoadFamily(p, out _))
                    return p;
            return null;
        }
        Step(doc, "Gordium: door and window families", report, [], _ =>
        {
            if (Symbols(BuiltInCategory.OST_Doors).Count == 0)
                report.Notes.Add("single door family loaded from " + (Load(Library("Doors", "Single-Flush.rfa", "Door-Single-Panel.rfa")) ?? "nowhere (none found)"));
            if (!Symbols(BuiltInCategory.OST_Doors).Any(s => BuildData.IsDoubleFamily(s.FamilyName)))
                report.Notes.Add("double door family loaded from " + (Load(Library("Doors", "Double-Flush.rfa", "Door-Double-Flush_Panel.rfa")) ?? "nowhere (none found)"));
            if (Symbols(BuiltInCategory.OST_Windows).Count == 0)
                report.Notes.Add("window family loaded from " + (Load(Library("Windows", "Fixed.rfa", "Window-Fixed.rfa")) ?? "nowhere (none found)"));
        });

        FamilySymbol? Pick(BuiltInCategory c, IReadOnlyList<string> keywords, Func<FamilySymbol, bool> ok)
        {
            var all = Symbols(c);
            return BuildData.PickSymbol(all.Select(Label).ToList(), keywords) is { } i && ok(all[i]) ? all[i] : null;
        }
        var single = Pick(BuiltInCategory.OST_Doors, BuildData.SingleKeywords, _ => true);
        var @double = Pick(BuiltInCategory.OST_Doors, BuildData.DoubleKeywords, s => BuildData.IsDoubleFamily(s.FamilyName));
        var window = Pick(BuiltInCategory.OST_Windows, BuildData.WindowKeywords, _ => true);
        report.Notes.Add($"stock families: single door {(single is null ? "none" : Label(single))}; double door " +
                         $"{(@double is null ? "none: made from Door.rft" : Label(@double))}; window {(window is null ? "none: made from Window.rft" : Label(window))}");

        var types = new Dictionary<string, OpeningType>();
        var toMake = new List<(string Key, string Kind, double W, double H)>();
        Step(doc, "Gordium: door and window types", report, [], _ =>
        {
            OpeningType? Sized(FamilySymbol? stock, string key, string tag, double w, double h)
            {
                if (stock is null)
                    return null;
                var name = BuildData.OpeningTypeName(tag, w, h, model.TypeSuffix);
                var s = Symbols(stock.Category.BuiltInCategory).FirstOrDefault(x => x.Name == name && x.FamilyName == stock.FamilyName)
                        ?? (FamilySymbol)stock.Duplicate(name);
                bool Set(BuiltInParameter[] ps, double v) =>
                    ps.Select(p => s.get_Parameter(p)).FirstOrDefault(p => p is { IsReadOnly: false }) is { } param && param.Set(v);
                var setW = Set([BuiltInParameter.DOOR_WIDTH, BuiltInParameter.WINDOW_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM, BuiltInParameter.GENERIC_WIDTH], w / 12);
                var setH = Set([BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.WINDOW_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM, BuiltInParameter.GENERIC_HEIGHT], h / 12);
                doc.Regenerate();
                var (sw, sh) = RevitInterior.TypeSize(s);
                if (!setW || !setH || sw is not { } a || sh is not { } b || Math.Abs(a - w / 12) > 1e-6 || Math.Abs(b - h / 12) > 1e-6)
                {
                    report.Notes.Add($"{Label(stock)}: a {BuildData.G(w)} x {BuildData.G(h)} in type couldn't be set (it came out {I($"{sw * 12:0.###} x {sh * 12:0.###}")} in): made from Revit's {(tag == "Door" ? "Door.rft" : "Window.rft")} instead");
                    doc.Delete(s.Id);
                    return null;
                }
                if (!s.IsActive)
                    s.Activate();
                return new OpeningType(s, false);
            }
            foreach (var d in model.Doors.DistinctBy(DoorKey))
                if (Sized(d.IsDouble ? @double : single, DoorKey(d), "Door", d.WidthIn, d.HeightIn) is { } t)
                    types[DoorKey(d)] = t;
                else
                    toMake.Add((DoorKey(d), d.Kind, d.WidthIn, d.HeightIn));
            foreach (var w in model.Windows.DistinctBy(WindowKey))
                if (Sized(window, WindowKey(w), "Window", w.WidthIn, w.HeightIn) is { } t)
                    types[WindowKey(w)] = t;
                else
                    toMake.Add((WindowKey(w), "window", w.WidthIn, w.HeightIn));
        });
        // families are loaded outside the project's transactions
        foreach (var (key, kind, w, h) in toMake)
        {
            try
            {
                var family = $"Gordium {(kind == "window" ? "window" : kind + " door")} {BuildData.G(w)} x {BuildData.G(h)} in ({model.TypeSuffix})";
                var symbol = kind == "window"
                    ? HouseDraw.WindowFamily(app, doc, new JsonObject { ["id"] = key, ["width"] = w / 12, ["height"] = h / 12 }, family)
                    : DoorFamily(app, doc, kind == "double", w / 12, h / 12, family);
                using (var t = new Transaction(doc, "Gordium: name a made type"))
                {
                    t.Start();
                    symbol.Name = BuildData.OpeningTypeName(kind == "window" ? "Window" : "Door", w, h, model.TypeSuffix);
                    if (!symbol.IsActive)
                        symbol.Activate();
                    t.Commit();
                }
                types[key] = new OpeningType(symbol, kind != "window");
                report.Notes.Add($"made {family} from Revit's {(kind == "window" ? "Window.rft" : "Door.rft")}");
            }
            catch (Exception x)
            {
                report.Failed.Add($"{kind} {BuildData.G(w)} x {BuildData.G(h)} in: no type could be made: {x.Message}");
            }
        }
        report.Counts["opening_types"] = types.Count;
        return types;
    }

    /// <summary>A door family of a size, made from Revit's Door.rft (as HouseDraw's DoorFamily): its leaf a solid
    /// filling the opening, 1 3/4 in thick, centred in the wall; and in plan, as the stock families draw a door, each
    /// leaf open square to the wall with the arc it sweeps: on the side opposite the family's facing (family -Y), a
    /// single leaf hinged opposite its hand (at Door.rft's Left plane, family -X), a double door's two leaves at its two
    /// jambs. Loaded into the project.</summary>
    private static FamilySymbol DoorFamily(RevitApplication app, Document project, bool isDouble, double width, double height, string name)
    {
        var fdoc = app.NewFamilyDocument(HouseDraw.Template(app, "Door.rft"));
        try
        {
            using (var t = new Transaction(fdoc, "Gordium: a door"))
            {
                t.Start();
                var fm = fdoc.FamilyManager;
                if (fm.CurrentType is null)
                    fm.NewType(name);
                fm.Set(HouseDraw.FamilyParameterOf(fm, BuiltInParameter.DOOR_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM, "Width"), width);
                fm.Set(HouseDraw.FamilyParameterOf(fm, BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM, "Height"), height);
                fdoc.Regenerate();
                var planes = new FilteredElementCollector(fdoc).OfClass(typeof(ReferencePlane)).Cast<ReferencePlane>()
                    .Where(p => !string.IsNullOrEmpty(p.Name)).GroupBy(p => p.Name).ToDictionary(g => g.Key, g => g.First().GetPlane().Origin);
                double left = planes.TryGetValue("Left", out var l) ? l.X : -width / 2, right = planes.TryGetValue("Right", out var r) ? r.X : width / 2;
                double y = planes.TryGetValue("Center (Front/Back)", out var c) ? c.Y : 0;
                if (Math.Abs(right - left - width) > 1e-6)
                    throw new InvalidOperationException(I($"Door.rft's Left and Right planes didn't flex to {width} ft (they are {right - left} apart)"));
                var profile = new CurveArray();
                var corners = new[] { new XYZ(left, y, 0), new XYZ(right, y, 0), new XYZ(right, y, height), new XYZ(left, y, height) };
                for (var i = 0; i < 4; i++)
                    profile.Append(Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                var loops = new CurveArrArray();
                loops.Append(profile);
                const double depth = 1.75 / 12;
                var leaf = fdoc.FamilyCreate.NewExtrusion(true, loops, SketchPlane.Create(fdoc, Plane.CreateByNormalAndOrigin(XYZ.BasisY, new XYZ(0, y, 0))), depth);
                leaf.StartOffset = -depth / 2;
                leaf.EndOffset = depth / 2;
                // the plan's swing: each leaf open to -Y from its hinge, and its arc back to the closed position
                var floorPlane = SketchPlane.Create(fdoc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero));
                void Swing(XYZ hinge, double reach, double from, double to)
                {
                    fdoc.FamilyCreate.NewSymbolicCurve(Line.CreateBound(hinge, hinge + new XYZ(0, -reach, 0)), floorPlane);
                    fdoc.FamilyCreate.NewSymbolicCurve(Arc.Create(hinge, reach, from, to, XYZ.BasisX, XYZ.BasisY), floorPlane);
                }
                if (isDouble)
                {
                    Swing(new XYZ(left, y, 0), width / 2, -Math.PI / 2, 0);
                    Swing(new XYZ(right, y, 0), width / 2, Math.PI, 1.5 * Math.PI);
                }
                else
                    Swing(new XYZ(left, y, 0), width, -Math.PI / 2, 0);
                t.Commit();
            }
            var family = fdoc.LoadFamily(project) ?? throw new InvalidOperationException($"{name} didn't load into the project");
            using (var rename = new Transaction(project, "Gordium: name a door family"))
            {
                rename.Start();
                family.Name = name;
                rename.Commit();
            }
            var symbols = family.GetFamilySymbolIds().Select(project.GetElement).OfType<FamilySymbol>().ToList();
            return symbols.FirstOrDefault(s => RevitInterior.TypeSize(s) is var (sw, sh) && sw is { } a && sh is { } b
                                               && Math.Abs(a - width) < 1e-9 && Math.Abs(b - height) < 1e-9)
                   ?? throw new InvalidOperationException(I($"{name} has no type {width} x {height} ft once loaded"));
        }
        finally
        {
            fdoc.Close(false);
        }
    }

    /// <summary>Each door the data gives a swing flipped until what its plan symbol draws is what the data says (see the
    /// call), and every door's line in the log: what was read back at the end, with the flips made. A door whose swing
    /// can't be read back is never flipped and never said to swing as the data (a failure, with why).</summary>
    private static void SwingDoors(Document doc, List<(BuildDoor D, FamilyInstance Fi, bool Made)> doors, Report report,
                                   Dictionary<ElementId, string> made)
    {
        var placed = doors.Where(x => x.Fi.IsValidObject).ToList();
        var data = placed.Where(x => x.D.SwingDir is not null).ToDictionary(
            x => x.Fi.UniqueId,
            x => (new Xyz(x.D.SwingDir!.Value.X, x.D.SwingDir.Value.Y, 0),
                  x.D.Hinge is { } h ? new Xyz(h.X, h.Y, 0) : (Xyz?)null,
                  new Xyz(x.D.Center.X, x.D.Center.Y, 0)));
        Dictionary<string, RouteReader.BuildSwing> Read() =>
            RouteReader.ReadBuildSwings(RevitInterior.DoorsModel(doc), data).ToDictionary(r => r.Id, StringComparer.Ordinal);
        var flips = placed.ToDictionary(x => x.Fi.UniqueId, _ => new List<string>(), StringComparer.Ordinal);
        void Flip(string name, Func<RouteReader.BuildSwing, bool> needs, Func<FamilyInstance, bool> can, Func<FamilyInstance, bool> flip, string word)
        {
            var read = Read();
            var labels = placed.Where(x => x.Fi.IsValidObject).ToDictionary(x => x.Fi.Id, x => $"door {BuildData.DoorMark(x.D)}");
            Step(doc, name, report, labels, _ =>
            {
                foreach (var (_, fi, _) in placed)
                    if (fi.IsValidObject && read.TryGetValue(fi.UniqueId, out var r) && needs(r))
                    {
                        if (!can(fi) || !flip(fi))
                            report.Failed.Add($"door {Mark(fi)}: Revit wouldn't flip its {word}");
                        else
                            flips[fi.UniqueId].Add($"{word} flipped");
                    }
            });
        }
        Flip("Gordium: doors flipped to swing to the data's side", r => r.FlipFacing, fi => fi.CanFlipFacing, fi => fi.flipFacing(), "facing");
        Flip("Gordium: doors flipped to hinge at the data's jamb", r => r.FlipHand, fi => fi.CanFlipHand, fi => fi.flipHand(), "hand");
        var end = Read();
        placed = placed.Where(x => x.Fi.IsValidObject).ToList();      // a door Revit removed in a flip: a failure, named by Step
        static string Way(int? s) => s switch { 1 => "+", -1 => "-", _ => "not read" };
        foreach (var (d, fi, madeHere) in placed)
        {
            var family = madeHere ? "Gordium's family" : "the template's family";
            var flipped = flips[fi.UniqueId].Count == 0 ? "nothing flipped" : string.Join(", ", flips[fi.UniqueId]);
            if (d.SwingDir is null)
            {
                report.Doors.Add($"{BuildData.DoorMark(d)} ({family}): no swing in the data, left as Revit placed it");
                continue;
            }
            var r = end[fi.UniqueId];
            var words = $"{BuildData.DoorMark(d)} ({family}, swing {Xy(d.SwingDir.Value)}): {flipped}; read back: swings {Way(r.Side)} " +
                        $"(the data {Way(r.DataSide)})" + (d.Hinge is null
                            ? d.IsDouble ? "" : ", no hinge in the data: its hand left as placed"
                            : $", hinged {Way(r.Hinge)} (the data {(r.DataHinge == 0 ? "at its centre" : Way(r.DataHinge))})");
            if (r.AsTheData)
                report.Doors.Add(words + "; swings as the data");
            else
            {
                var why = r.Side is null ? r.Why ?? "its swing isn't read" : r.DataSide is null || r.DataHinge == 0 ? r.Why! :
                    r.Hinge is null && d.Hinge is not null ? "its hinge isn't read" : "what is read isn't the data's";
                report.Doors.Add(words + $"; NOT shown to swing as the data: {why}");
                report.Failed.Add($"door {BuildData.DoorMark(d)}: placed, but not shown to swing as the data ({why})");
            }
        }
        string Mark(FamilyInstance fi) => fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString() ?? fi.UniqueId;
    }

    // ---- transactions and what Revit says in them ------------------------------------------------------------------

    /// <summary>One transaction: <paramref name="body"/> run in it, Revit's warnings dismissed (counted in the log), and
    /// each error Revit raises at commit resolved by deleting the elements it names (or Revit's own resolution), so one
    /// bad element never takes the others with it. Each element of <paramref name="made"/> (by id, its label) that
    /// Revit removed is a failure, with Revit's words.</summary>
    private static void Step(Document doc, string name, Report report, Dictionary<ElementId, string> made, Action<Transaction> body)
    {
        var failures = new Failures(report);
        using var t = new Transaction(doc, name);
        var options = t.GetFailureHandlingOptions();
        options.SetFailuresPreprocessor(failures);
        options.SetClearAfterRollback(true);
        t.SetFailureHandlingOptions(options);
        t.Start();
        body(t);
        var status = t.Commit();
        if (status != TransactionStatus.Committed)
            throw new InvalidOperationException($"\"{name}\" wasn't committed ({status}): " + string.Join(" | ", failures.Errors.Select(e => e.Words)));
        foreach (var (id, label) in made)
            if (doc.GetElement(id) is null)
            {
                var why = failures.Errors.Where(e => e.Ids.Contains(id)).Select(e => e.Words).ToList();
                report.Failed.Add($"{label}: removed when Revit committed \"{name}\": " + (why.Count > 0 ? string.Join(" | ", why) : "Revit gave no reason naming it"));
            }
        foreach (var e in failures.Errors.Where(e => !e.Ids.Any(made.ContainsKey)))
            report.Notes.Add($"\"{name}\": Revit error resolved: {e.Words}");
    }

    private sealed class Failures(Report report) : IFailuresPreprocessor
    {
        public readonly List<(List<ElementId> Ids, string Words)> Errors = [];

        public FailureProcessingResult PreprocessFailures(FailuresAccessor a)
        {
            var resolved = false;
            foreach (var f in a.GetFailureMessages())
            {
                var words = f.GetDescriptionText();
                if (f.GetSeverity() == FailureSeverity.Warning)
                {
                    report.Warnings[words] = report.Warnings.GetValueOrDefault(words) + 1;
                    a.DeleteWarning(f);
                    continue;
                }
                var ids = f.GetFailingElementIds().ToList();
                Errors.Add((ids, $"{f.GetSeverity()}: {words}"));
                if (ids.Count > 0 && TryDelete(a, ids))
                    resolved = true;
                else if (f.HasResolutions())
                {
                    a.ResolveFailure(f);
                    resolved = true;
                }
            }
            return resolved ? FailureProcessingResult.ProceedWithCommit : FailureProcessingResult.Continue;
        }

        /// <summary>The elements an error names deleted, when Revit lets them be (an element it can't delete is left
        /// to Revit's own resolution, else the step rolls back and says so).</summary>
        private static bool TryDelete(FailuresAccessor a, List<ElementId> ids)
        {
            try
            {
                a.DeleteElements(ids);
                return true;
            }
            catch (Autodesk.Revit.Exceptions.ApplicationException)
            {
                return false;
            }
        }
    }

    private static void Need(Parameter? p, string value, string label, string what, Report report)
    {
        if (p is null || p.IsReadOnly || !p.Set(value))
            report.Failed.Add($"{label}: its {what} couldn't be set to {value}");
    }

    private static void Need(Parameter? p, double value, string label, string what, Report report)
    {
        if (p is null || p.IsReadOnly || !p.Set(value))
            report.Failed.Add(I($"{label}: its {what} couldn't be set to {value * 12:0.###} in"));
    }

    private static PlanPoint P(XYZ v) => new(v.X, v.Y);

    /// <summary>A message's numbers written the same on every machine (a decimal point, whatever Revit's culture).</summary>
    private static string I(FormattableString s) => s.ToString(CultureInfo.InvariantCulture);

    private static string Xy(XYZ v) => I($"({v.X:0.###}, {v.Y:0.###})");

    private static string Xy(PlanPoint v) => I($"({v.X:0.###}, {v.Y:0.###})");
}
