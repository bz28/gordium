using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>A point on the plan, in feet.</summary>
public readonly record struct PlanPoint(double X, double Y);

/// <summary>A wall of the data: its centre line from <see cref="Start"/> to <see cref="End"/> on the level.
/// <see cref="NoJoinStart"/> and <see cref="NoJoinEnd"/>: Revit is not to join the wall at that end (a trimmed end, a
/// fill's ends: a join there with a wall it overlaps made Revit delete both, "Can't keep elements joined", the Children's
/// Odyssey build, 2026-11-21). <see cref="Level"/>: the level it stands on (a name in <see cref="BuildModel.Levels"/>;
/// null: the data's one level).</summary>
public sealed record BuildWall(int Id, PlanPoint Start, PlanPoint End, double ThicknessIn, string Status, bool SmokePartition,
                               string? FireRating, double HeightFt, bool Exterior, bool NoJoinStart = false, bool NoJoinEnd = false,
                               string? Level = null);

/// <summary>A door of the data (<see cref="Number"/> its place in the list from 1, as the script's marks D01...): its
/// centre on its host wall, <see cref="SwingDir"/> the side its leaf opens to (none when the source doesn't say: the
/// door is left as Revit places it, never flipped on a guess), <see cref="Hinge"/> its hinge jamb (a single door's; none
/// on a double, or when the source doesn't say).</summary>
public sealed record BuildDoor(int Number, PlanPoint Center, double WidthIn, double HeightIn, string Kind, int HostWall,
                               PlanPoint? SwingDir, PlanPoint? Hinge)
{
    public bool IsDouble => Kind == "double";
}

/// <summary>A window of the data (<see cref="Number"/> from 1, as the script's marks WN01...), its sill above its
/// host wall's level.</summary>
public sealed record BuildWindow(int Number, PlanPoint Center, double WidthIn, double HeightIn, double SillIn, int HostWall);

/// <summary>A room of the data: Revit places it at <see cref="TagPoint"/> on its <see cref="Level"/> (null: the data's
/// one level) and finds its outline from the walls; <see cref="Boundary"/> and <see cref="AreaSf"/> (the sheet's) are
/// kept to compare with what Revit finds.</summary>
public sealed record BuildRoom(string Number, string Name, PlanPoint TagPoint, IReadOnlyList<PlanPoint> Boundary, double? AreaSf,
                               string? Level = null);

/// <summary>A level of the data (<c>levels</c>): its name and elevation, feet.</summary>
public sealed record BuildLevel(string Name, double ElevationFt);

/// <summary>A floor slab of the data (<c>floors</c>): on its level, its top <see cref="TopOffsetFt"/> above the level,
/// its outline (no closing point) and its thickness.</summary>
public sealed record BuildFloor(string Level, IReadOnlyList<PlanPoint> Outline, double ThicknessIn, double TopOffsetFt);

/// <summary>A room's ceiling of the data (<c>ceilings</c>): a thin solid (a DirectShape in Ceilings, as HouseDraw draws
/// one) whose underside, at <see cref="UndersideFt"/> (an elevation, feet), covers its outline (no closing point).</summary>
public sealed record BuildCeiling(string Name, IReadOnlyList<PlanPoint> Outline, double UndersideFt, double ThicknessIn);

/// <summary>A room separation line of the data (<c>separations</c>), on its level.</summary>
public sealed record BuildSeparation(string Level, PlanPoint Start, PlanPoint End);

/// <summary>A point of the ground (<c>spot_grades</c>), drawn as Gordium's spot-grade marker (read when
/// <c>Gordium: Ground from</c> says "Spot grades").</summary>
public sealed record BuildSpot(double X, double Y, double Z);

/// <summary>A building to draw in a new Revit project (apps/revit_addin/tools/extract_build_data.py writes it from a
/// drawing script's DATA): one level, its walls, the doors and windows in them, its rooms and the floor under its
/// footprint (a closed ring: its last point its first). Data with <c>levels</c> in place of <c>level</c>
/// (apps/revit_addin/tools/evals/make_ny_build_data.py) has several, each wall and room on one by name (a door or window on
/// its wall's), and may give its own floor slabs (<c>floors</c>, in place of the footprint), rooms' ceilings, room
/// separation lines, the lot (a property line) and spot grades.</summary>
public sealed record BuildModel(string Project, string LevelName, double LevelElevation, IReadOnlyList<BuildWall> Walls,
                                IReadOnlyList<BuildDoor> Doors, IReadOnlyList<BuildWindow> Windows, IReadOnlyList<BuildRoom> Rooms,
                                IReadOnlyList<PlanPoint> Footprint, string? SourceFile, string? SourceSha256)
{
    /// <summary>Every level, as the data lists them (the one level when it gives <c>level</c>).</summary>
    public IReadOnlyList<BuildLevel> Levels { get; init; } = [new(LevelName, LevelElevation)];

    /// <summary>The floor slabs (<c>floors</c>); empty: the one floor under <see cref="Footprint"/>.</summary>
    public IReadOnlyList<BuildFloor> Floors { get; init; } = [];

    /// <summary>The rooms' ceilings (<c>ceilings</c>).</summary>
    public IReadOnlyList<BuildCeiling> Ceilings { get; init; } = [];

    /// <summary>The room separation lines (<c>separations</c>).</summary>
    public IReadOnlyList<BuildSeparation> Separations { get; init; } = [];

    /// <summary>The lot's outline (no closing point), drawn as a property line at elevation 0; null: no lot.</summary>
    public IReadOnlyList<PlanPoint>? Lot { get; init; }

    /// <summary>The spot grades (<c>spot_grades</c>).</summary>
    public IReadOnlyList<BuildSpot> SpotGrades { get; init; } = [];

    /// <summary>What the door and window types are named after (<c>Door 36" x 84" (LS1.0)</c>): the data's
    /// <c>type_suffix</c>, or the life-safety sheet LS1.0 the first data came from.</summary>
    public string TypeSuffix { get; init; } = "LS1.0";

    /// <summary>The level a wall or room stands on: its own (by name), or the one level.</summary>
    public BuildLevel LevelOf(string? name) => Levels.First(l => l.Name == (name ?? LevelName));
}

/// <summary>A correction the request makes to the data before drawing: wall W<see cref="Wall"/>'s end moved to
/// <see cref="ExtendEndTo"/> (along its own line, at most <see cref="BuildData.MaxCorrection"/> ft), and why. Applied
/// only when it keeps the wall's direction; logged either way.</summary>
/// <param name="Wall">The wall's number (W16 is 16).</param>
/// <param name="ExtendEndTo">Where its end (or, for <see cref="CorrectionKind.TrimStart"/>, its start) goes.</param>
/// <param name="Why">Why, in words (required).</param>
/// <param name="Kind">Which end moves, and which way: <see cref="CorrectionKind.ExtendEnd"/> (<c>extend_end_to</c>),
/// or a trim (<c>trim_end_to</c>, <c>trim_start_to</c>) that only shortens the wall back along its own line: two of the
/// trace's walls overlapping (a sliver Revit finds as an enclosed area) are joined end to end, never by a Room.</param>
/// <param name="FillStart">For <see cref="CorrectionKind.Fill"/>: the new wall's start (its end is
/// <paramref name="ExtendEndTo"/>, <paramref name="Wall"/> unused).</param>
/// <param name="FillThicknessIn">For <see cref="CorrectionKind.Fill"/>: the new wall's thickness, inches.</param>
/// <param name="MergeWith">For <see cref="CorrectionKind.Merge"/>: the wall taken into <paramref name="Wall"/>.</param>
public sealed record WallCorrection(int Wall, PlanPoint ExtendEndTo, string Why, CorrectionKind Kind = CorrectionKind.ExtendEnd,
                                    PlanPoint? FillStart = null, double? FillThicknessIn = null, int? MergeWith = null);

/// <summary>What a correction does to its wall.</summary>
public enum CorrectionKind
{
    /// <summary>The end moved along the wall's own line (<c>extend_end_to</c>).</summary>
    ExtendEnd,

    /// <summary>The end moved back toward the start (<c>trim_end_to</c>): shorter, never longer.</summary>
    TrimEnd,

    /// <summary>The start moved toward the end (<c>trim_start_to</c>): shorter, never longer.</summary>
    TrimStart,

    /// <summary>A short wall added where the sheet shows solid wall the trace left hollow (<c>fill</c>: a pocket
    /// between three of its walls): at most <see cref="BuildData.MaxFillLength"/> long and
    /// <see cref="BuildData.MaxCorrection"/> thick, every corner within <see cref="BuildData.MaxCorrection"/> of a wall
    /// of the data, so it fills between walls and never stands on its own.</summary>
    Fill,

    /// <summary>Two walls the trace drew face to face along the same stretch (<c>merge</c>: a hairline Revit finds as an
    /// enclosed area with no point inside) drawn as one wall of their two thicknesses, <see cref="WallCorrection.Wall"/>'s
    /// kept, <see cref="WallCorrection.MergeWith"/> taken into it: only parallel, their faces within 1/16 in, their ends
    /// within 1/16 in, and no door or window in either.</summary>
    Merge,
}

/// <summary>Data the add-in can't build all of: every problem found, each in words (never a part dropped).</summary>
public sealed class BuildDataException(IReadOnlyList<string> problems)
    : Exception("the data can't be built from: " + string.Join("; ", problems))
{
    public IReadOnlyList<string> Problems { get; } = problems;
}

/// <summary>What build_model_request.json asks for: the data (<see cref="Data"/>), the project template (none: Revit's
/// own imperial architectural one), the .rvt to save, and the script's three toggles (each the script's own default
/// when not given: true).</summary>
public sealed record BuildRequest(string Data, string? Template, string SaveAs, bool SwingOppositeFacing, bool HingeOppositeHand,
                                  bool UsePhases)
{
    /// <summary>The request's corrections to the data (<c>"corrections"</c>), each applied before drawing and logged.</summary>
    public IReadOnlyList<WallCorrection> Corrections { get; init; } = [];

    public static BuildRequest Parse(JsonNode? node)
    {
        var problems = new List<string>();
        if (node is not JsonObject o)
            throw new BuildDataException(["the request isn't a JSON object"]);
        string? Text(string key, bool required)
        {
            if (o[key] is null)
            {
                if (required)
                    problems.Add($"the request has no {key}");
                return null;
            }
            if (o[key] is JsonValue v && v.TryGetValue<string>(out var s) && s.Trim() != "")
                return s;
            problems.Add($"the request's {key} isn't a path");
            return null;
        }
        bool Flag(string key)
        {
            if (o[key] is null)
                return true;
            if (o[key] is JsonValue v && v.TryGetValue<bool>(out var b))
                return b;
            problems.Add($"the request's {key} isn't true or false");
            return true;
        }
        var corrections = new List<WallCorrection>();
        if (o["corrections"] is { } cs)
        {
            if (cs is not JsonArray list)
                problems.Add("the request's corrections isn't a list");
            else
                foreach (var (c, k) in list.Select((c, k) => (c, k + 1)))
                {
                    if (c is not JsonObject co)
                    {
                        problems.Add($"correction {k}: not an object");
                        continue;
                    }
                    if (co.ContainsKey("merge"))
                    {
                        // {"merge": ["W57", "W111"], "why": "..."}
                        static int? Mark(JsonNode? n) => n is JsonValue v && v.TryGetValue<string>(out var t) && t is { Length: > 1 } && t[0] == 'W'
                            && int.TryParse(t[1..], System.Globalization.NumberStyles.None, CultureInfo.InvariantCulture, out var id) ? id : null;
                        var pair = co["merge"] as JsonArray;
                        var (ma, mb) = pair is { Count: 2 } ? (Mark(pair[0]), Mark(pair[1])) : (null, null);
                        var mwhy = co["why"] is JsonValue myv && myv.TryGetValue<string>(out var mys) && mys.Trim() != "" ? mys : null;
                        if (ma is null || mb is null || ma == mb)
                            problems.Add($"correction {k}: merge needs two different walls' marks [\"W57\", \"W111\"]");
                        if (mwhy is null)
                            problems.Add($"correction {k}: no why (every correction to the data says why)");
                        problems.AddRange(co.Select(p => p.Key).Where(x => x is not ("merge" or "why")).Select(x => $"correction {k}: has {x}, which a merge doesn't take"));
                        if (ma is { } a0 && mb is { } b0 && a0 != b0 && mwhy is not null && co.Count == 2)
                            corrections.Add(new WallCorrection(a0, default, mwhy, CorrectionKind.Merge, MergeWith: b0));
                        continue;
                    }
                    if (co.ContainsKey("fill"))
                    {
                        // {"fill": {"start": [x, y], "end": [x, y], "thickness_in": t}, "why": "..."}: a new short wall
                        PlanPoint? Pt(JsonNode? n) => n is JsonArray { Count: 2 } pa && pa.All(x => x is JsonValue xv && xv.TryGetValue<double>(out var d) && double.IsFinite(d))
                            ? new PlanPoint(pa[0]!.GetValue<double>(), pa[1]!.GetValue<double>()) : null;
                        var f = co["fill"] as JsonObject;
                        var (fs, fe) = (Pt(f?["start"]), Pt(f?["end"]));
                        var ft = f?["thickness_in"] is JsonValue tv && tv.TryGetValue<double>(out var td) && double.IsFinite(td) && td > 0 ? td : (double?)null;
                        var fwhy = co["why"] is JsonValue fyv && fyv.TryGetValue<string>(out var fys) && fys.Trim() != "" ? fys : null;
                        if (fs is null || fe is null || ft is null)
                            problems.Add($"correction {k}: fill needs start and end points [x, y] and thickness_in more than 0");
                        if (fwhy is null)
                            problems.Add($"correction {k}: no why (every correction to the data says why)");
                        problems.AddRange(co.Select(p => p.Key).Where(x => x is not ("fill" or "why")).Select(x => $"correction {k}: has {x}, which a fill doesn't take"));
                        if (fs is { } s0 && fe is { } e0 && ft is { } t0 && fwhy is not null && co.Count == 2)
                            corrections.Add(new WallCorrection(0, e0, fwhy, CorrectionKind.Fill, s0, t0));
                        continue;
                    }
                    var wall = co["wall"] is JsonValue wv && wv.TryGetValue<string>(out var ws) ? ws : null;
                    var id = wall is { Length: > 1 } && wall[0] == 'W' && int.TryParse(wall[1..], System.Globalization.NumberStyles.None,
                                                                                        CultureInfo.InvariantCulture, out var n) ? n : (int?)null;
                    (string Key, CorrectionKind Kind)[] kinds =
                        [("extend_end_to", CorrectionKind.ExtendEnd), ("trim_end_to", CorrectionKind.TrimEnd), ("trim_start_to", CorrectionKind.TrimStart)];
                    var given = kinds.Where(x => co.ContainsKey(x.Key)).ToList();
                    var key = given.Count == 1 ? given[0].Key : "extend_end_to";
                    var to = co[key] is JsonArray { Count: 2 } a && a.All(x => x is JsonValue xv && xv.TryGetValue<double>(out var d) && double.IsFinite(d))
                        ? new PlanPoint(a[0]!.GetValue<double>(), a[1]!.GetValue<double>()) : (PlanPoint?)null;
                    var why = co["why"] is JsonValue yv && yv.TryGetValue<string>(out var ys) && ys.Trim() != "" ? ys : null;
                    var unknown = co.Select(p => p.Key).Where(x => x != "wall" && x != "why" && kinds.All(kd => kd.Key != x)).ToList();
                    if (id is null)
                        problems.Add($"correction {k}: wall is {co["wall"]?.ToJsonString() ?? "missing"}, not a wall's mark (W16)");
                    if (given.Count > 1)
                        problems.Add($"correction {k}: gives {string.Join(" and ", given.Select(x => x.Key))}: one change per correction");
                    else if (to is null)
                        problems.Add($"correction {k}: {key} is {co[key]?.ToJsonString() ?? "missing"}, not a point [x, y]");
                    if (why is null)
                        problems.Add($"correction {k}: no why (every correction to the data says why)");
                    problems.AddRange(unknown.Select(x => $"correction {k}: has {x}, which isn't asked for"));
                    if (id is { } i && to is { } p && why is not null && given.Count <= 1)
                        corrections.Add(new WallCorrection(i, p, why, given.Count == 1 ? given[0].Kind : CorrectionKind.ExtendEnd));
                }
        }
        var known = new HashSet<string> { "data", "template", "save_as", "swing_opposite_facing", "hinge_opposite_hand", "use_phases", "corrections" };
        problems.AddRange(o.Select(p => p.Key).Where(k => !known.Contains(k)).Select(k => $"the request has {k}, which isn't asked for (a misspelling?)"));
        var data = Text("data", true);
        var template = Text("template", false);
        var save = Text("save_as", true);
        if (save is not null && !save.EndsWith(".rvt", StringComparison.OrdinalIgnoreCase))
            problems.Add($"save_as {save} isn't a .rvt file");
        if (template is not null && !template.EndsWith(".rte", StringComparison.OrdinalIgnoreCase))
            problems.Add($"template {template} isn't a .rte file");
        var request = new BuildRequest(data ?? "", template, save ?? "", Flag("swing_opposite_facing"), Flag("hinge_opposite_hand"), Flag("use_phases"))
        {
            Corrections = corrections,
        };
        if (problems.Count > 0)
            throw new BuildDataException(problems);
        return request;
    }
}

/// <summary>
/// The Revit-free part of building a model from a drawing script's data, ported from the script Ben received
/// (a pyRevit/Dynamo script rebuilding the Children's Odyssey childcare centre from its life-safety sheet LS1.0): the
/// data's shape, the names and marks the script gives, which way each door is flipped, the footprint's outline, and
/// which phase existing walls go in. The add-in's ModelBuild does the Revit part with these.
/// </summary>
public static class BuildData
{
    // ---- the data ----------------------------------------------------------------------------------------------

    /// <summary>The data, every part checked; <see cref="BuildDataException"/> with every problem when the add-in
    /// couldn't build all of it (the same checks as extract_build_data.py's, as the file may be edited between).</summary>
    public static BuildModel Parse(JsonNode? node)
    {
        var p = new List<string>();
        if (node is not JsonObject data)
            throw new BuildDataException(["the data isn't a JSON object"]);
        static bool Num(JsonNode? n, out double v)
        {
            v = 0;
            if (n is not JsonValue x || x.GetValueKind() != System.Text.Json.JsonValueKind.Number)
                return false;
            // a value parsed from text gives a double; one made in code (a C# int) only its own type
            if (x.TryGetValue(out double d))
                v = d;
            else if (x.TryGetValue(out int i))
                v = i;
            else if (x.TryGetValue(out long l))
                v = l;
            else if (x.TryGetValue(out decimal m))
                v = (double)m;
            else
                return false;
            return double.IsFinite(v);
        }
        static bool Pt(JsonNode? n, out PlanPoint pt)
        {
            pt = default;
            if (n is not JsonArray { Count: 2 } a || !Num(a[0], out var x) || !Num(a[1], out var y))
                return false;
            pt = new PlanPoint(x, y);
            return true;
        }
        static string? Str(JsonNode? n) => n is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;
        static bool? Bool(JsonNode? n) => n is JsonValue v && v.TryGetValue<bool>(out var b) ? b : null;
        double Need(JsonObject o, string where, string key, Func<double, bool> ok, string what)
        {
            if (o[key] is null)
                p.Add($"{where}: no {key}");
            else if (!Num(o[key], out var v) || !ok(v))
                p.Add($"{where}: {key} is {o[key]!.ToJsonString()}, not {what}");
            else
                return v;
            return double.NaN;
        }
        PlanPoint NeedPt(JsonObject o, string where, string key)
        {
            if (o[key] is null)
                p.Add($"{where}: no {key}");
            else if (!Pt(o[key], out var pt))
                p.Add($"{where}: {key} is {o[key]!.ToJsonString()}, not a point [x, y]");
            else
                return pt;
            return default;
        }
        List<JsonObject> List(string key)
        {
            if (data[key] is not JsonArray a)
            {
                p.Add($"data: {key} isn't a list");
                return [];
            }
            var objects = new List<JsonObject>();
            foreach (var (n, k) in a.Select((n, k) => (n, k)))
                if (n is JsonObject o)
                    objects.Add(o);
                else
                    p.Add($"{key} {k}: not an object");
            return objects;
        }

        var project = Str(data["project"]);
        if (project is null)
            p.Add("data: project isn't text");
        if (Str(data["units"]) != "feet")
            p.Add($"data: units is {data["units"]?.ToJsonString() ?? "missing"}, not \"feet\"");
        string levelName = "";
        double elevation = 0;
        // one level (`level`, the script's), or several (`levels`), never both: each wall and room then names its own
        var levels = new List<BuildLevel>();
        var several = data.ContainsKey("levels");
        if (several && data.ContainsKey("level"))
            p.Add("data: gives both level and levels: one or the other");
        else if (several)
        {
            if (data["levels"] is not JsonArray given || given.Count == 0)
                p.Add("data: levels isn't a list of levels");
            else
                foreach (var (n, k) in given.Select((n, k) => (n, k)))
                {
                    if (n is not JsonObject lo || Str(lo["name"]) is not { } name || name.Trim() == "" || !Num(lo["elevation_ft"], out var z))
                        p.Add($"level {k}: not a level with a name and elevation_ft");
                    else if (levels.Any(l => l.Name == name))
                        p.Add($"level {k}: a second level named {name}");
                    else if (levels.Any(l => Math.Abs(l.ElevationFt - z) < 1e-6))
                        p.Add(I($"level {k}: a second level at {z} ft"));
                    else
                        levels.Add(new BuildLevel(name, z));
                }
            if (levels.Count > 0)
                (levelName, elevation) = (levels[0].Name, levels[0].ElevationFt);
        }
        else if (data["level"] is not JsonObject level || Str(level["name"]) is not { } ln || ln.Trim() == "" || !Num(level["elevation_ft"], out elevation))
            p.Add("data: level isn't a level with a name and elevation_ft");
        else
        {
            levelName = ln;
            levels.Add(new BuildLevel(ln, elevation));
        }
        // an element's level: with several, required and one of them; with one, not given (or that one)
        string? LevelKey(JsonObject o, string where)
        {
            if (!o.ContainsKey("level"))
            {
                if (several)
                    p.Add($"{where}: no level (the data has several)");
                return null;
            }
            var name = Str(o["level"]);
            if (name is null || levels.All(l => l.Name != name))
            {
                p.Add($"{where}: level is {o["level"]?.ToJsonString() ?? "null"}, not one of the data's levels");
                return null;
            }
            return name;
        }
        // a closed ring of points, given with its last point its first: returned without it
        List<PlanPoint>? Ring(JsonNode? n, string where, int least = 3)
        {
            if (n is not JsonArray a || a.Count < least + 1 || !a.All(x => Pt(x, out _)))
            {
                p.Add($"{where}: not a closed ring of {least} or more points [x, y]");
                return null;
            }
            var pts = a.Select(x => { Pt(x, out var q); return q; }).ToList();
            if (Distance(pts[0], pts[^1]) > 1e-9)
            {
                p.Add($"{where}: its last point isn't its first");
                return null;
            }
            pts.RemoveAt(pts.Count - 1);
            return pts;
        }

        var walls = new List<BuildWall>();
        var ids = new HashSet<int>();
        foreach (var (w, k) in List("walls").Select((w, k) => (w, k)))
        {
            var where = $"wall {k}";
            int id = -1;
            if (w["id"] is JsonValue iv && iv.GetValueKind() == System.Text.Json.JsonValueKind.Number && iv.TryGetValue(out int i))
            {
                id = i;
                where = $"wall {id}";
                if (!ids.Add(id))
                    p.Add($"{where}: a second wall with this id");
            }
            else
                p.Add($"{where}: id isn't a whole number");
            var start = NeedPt(w, where, "start");
            var end = NeedPt(w, where, "end");
            if (Distance(start, end) < 0.01)
                p.Add($"{where}: its start and end are the same point");
            var thick = Need(w, where, "thickness_in", v => v > 0, "a thickness over 0");
            var status = Str(w["status"]);
            if (status is not ("Existing" or "New"))
                p.Add($"{where}: status is {w["status"]?.ToJsonString() ?? "missing"}, not \"Existing\" or \"New\"");
            var smoke = Bool(w["smoke_partition"]);
            if (smoke is null)
                p.Add($"{where}: smoke_partition isn't true or false");
            string? rating = null;
            // the key is required (null or text), as the extractor and the script read it
            if (!w.ContainsKey("fire_rating"))
                p.Add($"{where}: no fire_rating");
            else if (w["fire_rating"] is { } fr)
            {
                if (Str(fr) is { } r && r.Trim() != "")
                    rating = r;
                else
                    p.Add($"{where}: fire_rating is {fr.ToJsonString()}, not null or text");
            }
            var height = Need(w, where, "height_ft", v => v > 0, "a height over 0");
            var exterior = Bool(w["exterior"]);
            if (exterior is null)
                p.Add($"{where}: exterior isn't true or false");
            walls.Add(new BuildWall(id, start, end, thick, status ?? "", smoke ?? false, rating, height, exterior ?? false,
                                    Level: LevelKey(w, where)));
        }

        int Host(JsonObject o, string where)
        {
            if (o["host_wall"] is JsonValue hv && hv.GetValueKind() == System.Text.Json.JsonValueKind.Number && hv.TryGetValue(out int h) && ids.Contains(h))
                return h;
            p.Add($"{where}: host_wall is {o["host_wall"]?.ToJsonString() ?? "missing"}, not the id of a wall in the data");
            return -1;
        }
        var doors = new List<BuildDoor>();
        foreach (var (d, k) in List("doors").Select((d, k) => (d, k)))
        {
            var where = $"door {k + 1}";
            var center = NeedPt(d, where, "center");
            var width = Need(d, where, "width_in", v => v > 0, "a width over 0");
            var height = Need(d, where, "height_in", v => v > 0, "a height over 0");
            var kind = Str(d["kind"]);
            if (kind is not ("single" or "double"))
                p.Add($"{where}: kind is {d["kind"]?.ToJsonString() ?? "missing"}, not \"single\" or \"double\"");
            var host = Host(d, where);
            // the script's data always gives a swing; data whose source doesn't say leaves it out (several levels only:
            // the script's own data keeps its check that every door has one)
            PlanPoint? swing = null;
            if (several && !d.ContainsKey("swing_dir"))
                swing = null;
            else
            {
                var sw = NeedPt(d, where, "swing_dir");
                if (d["swing_dir"] is not null && Pt(d["swing_dir"], out _) && Math.Abs(Math.Sqrt(sw.X * sw.X + sw.Y * sw.Y) - 1) >= 0.01)
                    p.Add($"{where}: swing_dir is {d["swing_dir"]!.ToJsonString()}, not a unit vector [x, y]");
                swing = sw;
            }
            PlanPoint? hinge = null;
            if (d.ContainsKey("hinge"))
            {
                // given, it is a point (a null hinge is refused, as the extractor refuses it)
                if (Pt(d["hinge"], out var hp))
                    hinge = hp;
                else
                    p.Add($"{where}: hinge is {d["hinge"]?.ToJsonString() ?? "null"}, not a point [x, y]");
            }
            doors.Add(new BuildDoor(k + 1, center, width, height, kind ?? "", host, swing, hinge));
        }
        var windows = new List<BuildWindow>();
        foreach (var (w, k) in List("windows").Select((w, k) => (w, k)))
        {
            var where = $"window {k + 1}";
            windows.Add(new BuildWindow(k + 1, NeedPt(w, where, "center"), Need(w, where, "width_in", v => v > 0, "a width over 0"),
                                        Need(w, where, "height_in", v => v > 0, "a height over 0"),
                                        Need(w, where, "sill_in", v => v >= 0, "a sill height of 0 or more"), Host(w, where)));
        }
        var rooms = new List<BuildRoom>();
        foreach (var (r, k) in List("rooms").Select((r, k) => (r, k)))
        {
            var where = $"room {k + 1}";
            var number = Str(r["number"]);
            var name = Str(r["name"]);
            if (number is not { } nb || nb.Trim() == "")
                p.Add($"{where}: number isn't text");
            if (name is not { } nm || nm.Trim() == "")
                p.Add($"{where}: name isn't text");
            var tag = NeedPt(r, where, "tag_point");
            var boundary = new List<PlanPoint>();
            if (r["boundary"] is JsonArray ring && ring.Count >= 3 && ring.All(n => Pt(n, out _)))
                boundary.AddRange(ring.Select(n => { Pt(n, out var q); return q; }));
            else
                p.Add($"{where}: boundary isn't a list of 3 or more points");
            double? area = null;
            if (r.ContainsKey("area_sf"))
            {
                if (Num(r["area_sf"], out var a))
                    area = a;
                else
                    p.Add($"{where}: area_sf is {r["area_sf"]?.ToJsonString() ?? "null"}, not a number");
            }
            rooms.Add(new BuildRoom(number ?? "", name ?? "", tag, boundary, area, LevelKey(r, where)));
        }
        if (rooms.GroupBy(r => r.Number).FirstOrDefault(g => g.Count() > 1) is { } twice && several)
            p.Add($"room number {twice.Key}: given to {twice.Count()} rooms (marks find a room by its number)");

        // ---- what data with several levels may give besides: its floors, ceilings, separation lines, lot, ground ----
        List<JsonObject> Optional(string key) => data.ContainsKey(key) ? List(key) : [];
        var floors = new List<BuildFloor>();
        foreach (var (f, k) in Optional("floors").Select((f, k) => (f, k)))
        {
            var where = $"floor {k + 1}";
            var lv = LevelKey(f, where);
            var outline = Ring(f["outline"], $"{where}: outline");
            var thick = Need(f, where, "thickness_in", v => v > 0, "a thickness over 0");
            var top = f.ContainsKey("top_offset_ft") ? Need(f, where, "top_offset_ft", _ => true, "a number") : 0;
            if (lv is not null && outline is not null)
                floors.Add(new BuildFloor(lv, outline, thick, top));
        }
        var ceilings = new List<BuildCeiling>();
        foreach (var (c, k) in Optional("ceilings").Select((c, k) => (c, k)))
        {
            var where = $"ceiling {k + 1}";
            var name = Str(c["name"]);
            if (name is null || name.Trim() == "")
                p.Add($"{where}: name isn't text");
            var outline = Ring(c["outline"], $"{where}: outline");
            var under = Need(c, where, "underside_ft", _ => true, "an elevation");
            var thick = Need(c, where, "thickness_in", v => v > 0, "a thickness over 0");
            if (name is not null && outline is not null)
                ceilings.Add(new BuildCeiling(name, outline, under, thick));
        }
        var separations = new List<BuildSeparation>();
        foreach (var (s, k) in Optional("separations").Select((s, k) => (s, k)))
        {
            var where = $"separation {k + 1}";
            var lv = LevelKey(s, where);
            var (a, b) = (NeedPt(s, where, "start"), NeedPt(s, where, "end"));
            if (Distance(a, b) < 0.01)
                p.Add($"{where}: its start and end are the same point");
            if (lv is not null)
                separations.Add(new BuildSeparation(lv, a, b));
        }
        List<PlanPoint>? lot = null;
        if (data.ContainsKey("lot"))
        {
            if (data["lot"] is not JsonObject lo)
                p.Add("data: lot isn't an object with an outline");
            else
                lot = Ring(lo["outline"], "lot: outline");
        }
        var spots = new List<BuildSpot>();
        foreach (var (s, k) in Optional("spot_grades").Select((s, k) => (s, k)))
        {
            if (s["at"] is JsonArray { Count: 3 } at && Num(at[0], out var x) && Num(at[1], out var y) && Num(at[2], out var z))
                spots.Add(new BuildSpot(x, y, z));
            else
                p.Add($"spot grade {k + 1}: at isn't a point [x, y, z]");
        }
        if (!several && (floors.Count > 0 || ceilings.Count > 0 || separations.Count > 0 || lot is not null || spots.Count > 0))
            p.Add("data: floors, ceilings, separations, a lot and spot grades are read only with levels");
        var footprint = new List<PlanPoint>();
        if (several && !data.ContainsKey("footprint"))
        {
            if (floors.Count == 0)
                p.Add("data: no floors and no footprint (with levels, give the floors)");
        }
        else if (data["footprint"] is JsonArray fp && fp.Count >= 4 && fp.All(n => Pt(n, out _)))
        {
            footprint.AddRange(fp.Select(n => { Pt(n, out var q); return q; }));
            if (Distance(footprint[0], footprint[^1]) > 1e-9)
                p.Add("footprint: its last point isn't its first (the add-in, as the script, drops the closing point)");
        }
        else
            p.Add("footprint: not a list of 4 or more points [x, y]");
        if (several && floors.Count > 0 && footprint.Count > 0)
            p.Add("data: gives both floors and a footprint: one or the other");
        var suffix = data.ContainsKey("type_suffix") ? Str(data["type_suffix"]) : "LS1.0";
        if (suffix is null || suffix.Trim() == "")
            p.Add($"data: type_suffix is {data["type_suffix"]?.ToJsonString()}, not text");
        // as the extractor: no stats (or null) is no check; stats not an object is refused; each count given must be a
        // number equal to the data's (2.0 for 2 is equal; null, text or true is not)
        if (data["stats"] is JsonObject stats)
        {
            foreach (var (key, count) in new[] { ("walls", walls.Count), ("doors", doors.Count), ("windows", windows.Count), ("rooms", rooms.Count) })
                if (stats.ContainsKey(key) && !(Num(stats[key], out var n) && n == count))
                    p.Add($"stats: {key} says {stats[key]?.ToJsonString() ?? "null"}, the data has {count}");
        }
        else if (data["stats"] is not null)
            p.Add("stats: not an object");
        if (p.Count > 0)
            throw new BuildDataException(p);
        var source = data["extracted_from"] as JsonObject;
        return new BuildModel(project!, levelName, elevation, walls, doors, windows, rooms, footprint,
                              Str(source?["file"]), Str(source?["sha256"]))
        {
            Levels = levels, Floors = floors, Ceilings = ceilings, Separations = separations, Lot = lot, SpotGrades = spots,
            TypeSuffix = suffix!,
        };
    }

    // ---- names and marks, as the script gives them -------------------------------------------------------------

    /// <summary>A number as Python's <c>{:g}</c> writes it (12.0 as 12, 4.5 as 4.5): the script's names.</summary>
    public static string G(double v) => v.ToString("G6", CultureInfo.InvariantCulture);

    /// <summary>The wall type a wall is drawn with: <c>LS Existing 12"</c>, <c>LS New 4.5" 1 HR</c>; one per name.</summary>
    public static string WallTypeName(BuildWall w) => $"LS {w.Status} {G(w.ThicknessIn)}\"" + (w.FireRating is { } r ? " " + r : "");

    /// <summary>The wall's Comments: its status, SMOKE PARTITION, its rating, and PARTIAL HEIGHT when under 10 ft (the
    /// sheet gives no height: 10 ft is assumed, a low wall's 3.5 ft too).</summary>
    public static string WallComment(BuildWall w) =>
        w.Status + (w.SmokePartition ? " | SMOKE PARTITION" : "") + (w.FireRating is { } r ? " | " + r : "")
        + (w.HeightFt < 10 ? " | PARTIAL HEIGHT (height assumed)" : "");

    public static string WallMark(BuildWall w) => $"W{w.Id}";

    public static string DoorMark(BuildDoor d) => $"D{d.Number:00}";

    public static string WindowMark(BuildWindow w) => $"WN{w.Number:00}";

    /// <summary>The door or window type of a size: <c>Door 36" x 84" (LS1.0)</c>, <c>Window 45" x 48" (LS1.0)</c>.</summary>
    public static string OpeningTypeName(string tag, double widthIn, double heightIn, string suffix = "LS1.0") =>
        $"{tag} {G(widthIn)}\" x {G(heightIn)}\" ({suffix})";

    /// <summary>The family to take a type from, as the script picks it: the first of <paramref name="labels"/> (each a
    /// family's name and its type's) holding the first keyword that any holds (ignoring case), else the first; none
    /// when there are none.</summary>
    public static int? PickSymbol(IReadOnlyList<string> labels, IReadOnlyList<string> keywords)
    {
        foreach (var kw in keywords)
            for (var i = 0; i < labels.Count; i++)
                if (labels[i].Contains(kw, StringComparison.OrdinalIgnoreCase))
                    return i;
        return labels.Count > 0 ? 0 : null;
    }

    /// <summary>Whether a family is a double door, as the script asks it ("double" in its name).</summary>
    public static bool IsDoubleFamily(string familyName) => familyName.Contains("double", StringComparison.OrdinalIgnoreCase);

    /// <summary>The keywords the script picks its families by.</summary>
    public static readonly IReadOnlyList<string> SingleKeywords = ["Single-Flush", "Single"], DoubleKeywords = ["Double-Flush", "Double"],
                                                 WindowKeywords = ["Fixed", "Window"];

    // ---- doors -------------------------------------------------------------------------------------------------

    // (Which way to flip a door is never worked out from its facing or hand: a family's convention is its own, and
    // Revit 2027's Single-Flush swings toward its facing, the opposite of what the script assumed. The build reads
    // each door's drawn swing back and flips until it is the data's: ModelBuild.SwingDoors, RouteReader.ReadBuildSwings.)

    // ---- the floor, the rooms, the phases ----------------------------------------------------------------------

    /// <summary>The floor's outline: the footprint without its closing point (as the script drops it), each point
    /// within 0.01 ft of the one kept before it left out (the script's "segment over 0.01 ft", kept closed: a short
    /// side dropped would leave a gap, which Revit refuses). Under 3 points left is an error.</summary>
    public static IReadOnlyList<PlanPoint> FloorOutline(IReadOnlyList<PlanPoint> footprint)
    {
        var kept = new List<PlanPoint>();
        foreach (var q in footprint.Take(footprint.Count - 1))
            if (kept.Count == 0 || Distance(kept[^1], q) > 0.01)
                kept.Add(q);
        while (kept.Count > 1 && Distance(kept[^1], kept[0]) <= 0.01)
            kept.RemoveAt(kept.Count - 1);
        if (kept.Count < 3)
            throw new BuildDataException([$"footprint: {kept.Count} points left once the short sides are dropped, not a floor"]);
        return kept;
    }

    /// <summary>The area inside a ring of points (closed or not), in square feet.</summary>
    public static double Area(IReadOnlyList<PlanPoint> ring)
    {
        var a = 0.0;
        for (var i = 0; i < ring.Count; i++)
        {
            var (p, q) = (ring[i], ring[(i + 1) % ring.Count]);
            a += p.X * q.Y - q.X * p.Y;
        }
        return Math.Abs(a) / 2;
    }

    /// <summary>Which of the project's phases an Existing wall is created in: the first (Revit's templates name it
    /// Existing) when the script's USE_PHASES is on and there is more than one; else none, and it is in the view's own
    /// (New Construction), as the script does.</summary>
    public static int? ExistingPhase(int phaseCount, bool usePhases) => usePhases && phaseCount > 1 ? 0 : null;

    // ---- corrections the request makes to the data ----------------------------------------------------------------

    /// <summary>The farthest a correction may move a wall's end, in feet: a trace's slip, never a new wall.</summary>
    public const double MaxCorrection = 2.0;

    /// <summary>The longest a fill may be, in feet: a pocket's side (the Children's Odyssey's east-entry jamb pockets,
    /// 2.78 ft), never a new run of wall.</summary>
    public const double MaxFillLength = 3.0;

    /// <summary>The data with each correction applied, in order, and each in words: applied ("corrected W16: end
    /// (192.424, 48.167) → (193.867, 48.167): why") or refused and not applied (no such wall; the end moved more than
    /// <see cref="MaxCorrection"/> ft; the wall's direction changed, off its own line or turned back). Nothing else in
    /// the data changes.</summary>
    public static (BuildModel Model, IReadOnlyList<string> Applied, IReadOnlyList<string> Refused) Correct(BuildModel model,
                                                                                                        IReadOnlyList<WallCorrection> corrections)
    {
        var walls = model.Walls.ToList();
        var applied = new List<string>();
        var refused = new List<string>();
        static string Xy(PlanPoint p) => string.Create(CultureInfo.InvariantCulture, $"({p.X:0.###}, {p.Y:0.###})");
        foreach (var c in corrections)
        {
            if (c.Kind == CorrectionKind.Merge)
            {
                var (ka, kb) = (walls.FindIndex(x => x.Id == c.Wall), walls.FindIndex(x => x.Id == c.MergeWith));
                var said = $"W{c.MergeWith} into W{c.Wall}: {c.Why}";
                string? no = ka < 0 || kb < 0 ? "the data has no such wall"
                    : model.Doors.Any(d => d.HostWall == c.Wall || d.HostWall == c.MergeWith)
                      || model.Windows.Any(w => w.HostWall == c.Wall || w.HostWall == c.MergeWith) ? "a door or window is in one of them"
                    : MergeProblem(walls[ka], walls[kb]);
                if (no is not null)
                {
                    refused.Add($"refused merge {said} ({no})");
                    continue;
                }
                var (wa, wb) = (walls[ka], walls[kb]);
                double len = Distance(wa.Start, wa.End), ux = (wa.End.X - wa.Start.X) / len, uy = (wa.End.Y - wa.Start.Y) / len;
                // b's side of a, across: the merged centre line half way between the two outer faces
                var side = Math.Sign(-(wb.Start.X - wa.Start.X) * uy + (wb.Start.Y - wa.Start.Y) * ux);
                var shift = side * wb.ThicknessIn / 24;
                // the merged wall carries the stricter of each: a smoke partition if either is, the one fire rating given
                // (two different ratings are refused in MergeProblem), exterior if either is; its status (phase) is the
                // first's, and the line says what each was (review round 1: the second's were dropped in silence)
                var merged = wa with
                {
                    Start = new PlanPoint(wa.Start.X - uy * shift, wa.Start.Y + ux * shift),
                    End = new PlanPoint(wa.End.X - uy * shift, wa.End.Y + ux * shift),
                    ThicknessIn = wa.ThicknessIn + wb.ThicknessIn,
                    SmokePartition = wa.SmokePartition || wb.SmokePartition,
                    FireRating = wa.FireRating ?? wb.FireRating,
                    Exterior = wa.Exterior || wb.Exterior,
                };
                walls[ka] = merged;
                walls.RemoveAt(walls.FindIndex(x => x.Id == c.MergeWith));
                var differ = new List<string>();
                if (wa.Status != wb.Status)
                    differ.Add($"status {wa.Status} kept (W{c.MergeWith} was {wb.Status})");
                if (wa.SmokePartition != wb.SmokePartition)
                    differ.Add("a smoke partition (one of them was)");
                if (wa.FireRating != wb.FireRating)
                    differ.Add($"fire rating {merged.FireRating} (one of them had none)");
                if (wa.Exterior != wb.Exterior)
                    differ.Add("exterior (one of them was)");
                applied.Add(I($"merged {said} (one wall {merged.ThicknessIn:0.##} in thick, centre line moved {Math.Abs(shift):0.###} ft") +
                            (differ.Count > 0 ? "; " + string.Join("; ", differ) : "") + ")");
                continue;
            }
            if (c.Kind == CorrectionKind.Fill)
            {
                var (s, e, t) = (c.FillStart!.Value, c.ExtendEndTo, c.FillThicknessIn!.Value);
                var length = Distance(s, e);
                var fill = new BuildWall(walls.Max(x => x.Id) + 1, s, e, t, "Existing", false, null,
                                         model.Walls.Count == 0 ? 10 : model.Walls.Max(x => x.HeightFt), false, NoJoinStart: true, NoJoinEnd: true);
                // its four corners, each within the limit of a wall of the data: it fills between walls, never stands alone
                double ux = (e.X - s.X) / Math.Max(length, 1e-12), uy = (e.Y - s.Y) / Math.Max(length, 1e-12), half = t / 24;
                PlanPoint[] corners = [new(s.X - uy * half, s.Y + ux * half), new(s.X + uy * half, s.Y - ux * half),
                                       new(e.X - uy * half, e.Y + ux * half), new(e.X + uy * half, e.Y - ux * half)];
                var far = corners.Select(p => model.Walls.Count == 0 ? double.PositiveInfinity : model.Walls.Min(w => DistanceToWall(p, w))).Max();
                var said = I($"a {length:0.###} ft wall {t:0.##} in thick from {Xy(s)} to {Xy(e)}: {c.Why}");
                if (length < 1e-6 || length > MaxFillLength || t / 12 > MaxCorrection)
                    refused.Add(I($"refused fill: {said} (a fill is at most {MaxFillLength:0} ft long and {MaxCorrection:0} ft thick)"));
                else if (far > MaxCorrection)
                    refused.Add(I($"refused fill: {said} (a corner is {far:0.###} ft from every wall of the data, more than {MaxCorrection:0} ft: not a fill between walls)"));
                else
                {
                    walls.Add(fill);
                    applied.Add($"filled W{fill.Id}: {said}");
                }
                continue;
            }
            var i = walls.FindIndex(w => w.Id == c.Wall);
            var words = $"W{c.Wall}: end to {Xy(c.ExtendEndTo)}: {c.Why}";
            if (i < 0)
            {
                refused.Add($"refused {words}: the data has no wall W{c.Wall}");
                continue;
            }
            // measured from the data's own wall, never one an earlier correction moved: two corrections of a wall can't
            // add up past the limit (review round 1)
            var w = model.Walls.First(x => x.Id == c.Wall);
            if (c.Kind != CorrectionKind.ExtendEnd)
            {
                // a trim: the end (or start) moved back along the wall's own line, the wall shorter and still a wall
                var start = c.Kind == CorrectionKind.TrimStart;
                var (fixedEnd, movedEnd) = start ? (w.End, w.Start) : (w.Start, w.End);
                var trim = Distance(movedEnd, c.ExtendEndTo);
                double tx = movedEnd.X - fixedEnd.X, ty = movedEnd.Y - fixedEnd.Y, qx = c.ExtendEndTo.X - fixedEnd.X, qy = c.ExtendEndTo.Y - fixedEnd.Y;
                double full = Math.Sqrt(tx * tx + ty * ty), left = Math.Sqrt(qx * qx + qy * qy);
                var off = left < 1e-9 ? 1 : Math.Abs(tx * qy - ty * qx) / (full * left);
                var which = start ? "start" : "end";
                if (trim > MaxCorrection)
                    refused.Add(I($"refused W{c.Wall}: trimming its {which} {Xy(movedEnd)} → {Xy(c.ExtendEndTo)} moves it {trim:0.###} ft, more than {MaxCorrection:0} ft: {c.Why}"));
                else if (off > 1e-4 || tx * qx + ty * qy <= 0 || left >= full || left < 1e-9)
                    refused.Add($"refused W{c.Wall}: {Xy(c.ExtendEndTo)} isn't on the wall between its ends, so trimming its {which} to it " +
                                $"would lengthen, turn or remove it: {c.Why}");
                else
                {
                    walls[i] = start ? walls[i] with { Start = c.ExtendEndTo, NoJoinStart = true } : walls[i] with { End = c.ExtendEndTo, NoJoinEnd = true };
                    applied.Add(I($"trimmed W{c.Wall}: {which} {Xy(movedEnd)} → {Xy(c.ExtendEndTo)} ({trim:0.###} ft): {c.Why}"));
                }
                continue;
            }
            var moved = Distance(w.End, c.ExtendEndTo);
            double ox = w.End.X - w.Start.X, oy = w.End.Y - w.Start.Y, nx = c.ExtendEndTo.X - w.Start.X, ny = c.ExtendEndTo.Y - w.Start.Y;
            double oldLength = Math.Sqrt(ox * ox + oy * oy), newLength = Math.Sqrt(nx * nx + ny * ny);
            var sine = newLength < 1e-9 ? 1 : Math.Abs(ox * ny - oy * nx) / (oldLength * newLength);
            var same = newLength >= 1e-9 && ox * nx + oy * ny > 0;
            if (moved > MaxCorrection)
                refused.Add(I($"refused W{c.Wall}: end {Xy(w.End)} → {Xy(c.ExtendEndTo)} moves it {moved:0.###} ft from the data's end, more than {MaxCorrection:0} ft: {c.Why}"));
            else if (sine > 1e-4 || !same)
                refused.Add($"refused W{c.Wall}: end {Xy(w.End)} → {Xy(c.ExtendEndTo)} changes the wall's direction: {c.Why}");
            else
            {
                walls[i] = walls[i] with { End = c.ExtendEndTo };
                applied.Add(I($"corrected W{c.Wall}: end {Xy(w.End)} → {Xy(c.ExtendEndTo)} ({moved:0.###} ft): {c.Why}"));
            }
        }
        return (model with { Walls = walls }, applied, refused);
    }

    /// <summary>Why two walls can't be merged into one (null when they can): parallel, their facing faces within 1/16 in
    /// of each other, their ends within 1/16 in of each other's.</summary>
    public static string? MergeProblem(BuildWall a, BuildWall b)
    {
        if (a.FireRating is { } ra && b.FireRating is { } rb && ra != rb)
            return $"their fire ratings differ ({ra}, {rb}): which one the merged wall has isn't known";
        const double tol = 1.0 / 16 / 12;
        double la = Distance(a.Start, a.End), ux = (a.End.X - a.Start.X) / la, uy = (a.End.Y - a.Start.Y) / la;
        double lb = Distance(b.Start, b.End), vx = (b.End.X - b.Start.X) / lb, vy = (b.End.Y - b.Start.Y) / lb;
        if (Math.Abs(ux * vy - uy * vx) > 1e-6)
            return "they aren't parallel";
        double Across(PlanPoint p) => -(p.X - a.Start.X) * uy + (p.Y - a.Start.Y) * ux;
        double Along(PlanPoint p) => (p.X - a.Start.X) * ux + (p.Y - a.Start.Y) * uy;
        var gap = Math.Abs(Across(b.Start)) - (a.ThicknessIn + b.ThicknessIn) / 24;
        if (Math.Abs(Across(b.Start) - Across(b.End)) > tol || Math.Abs(gap) > tol)
            return I($"their faces aren't together (a gap of {gap * 12:0.###} in)");
        double b0 = Math.Min(Along(b.Start), Along(b.End)), b1 = Math.Max(Along(b.Start), Along(b.End));
        if (Math.Abs(b0) > tol || Math.Abs(b1 - la) > tol)
            return "they don't run the same stretch (their ends more than 1/16 in apart)";
        return null;
    }

    // ---- what the data's walls leave open, and where they overlap --------------------------------------------------

    /// <summary>A stretch of a room's boundary (the sheet's) with no wall of the data along it: Revit finds a room's
    /// outline from walls alone, so a room whose boundary has one leaks through it and is not enclosed.
    /// <see cref="WallBefore"/> and <see cref="WallAfter"/> are the walls nearest its two ends (none when none is within
    /// a foot).</summary>
    public sealed record BoundaryGap(PlanPoint From, PlanPoint To, double Length, int? WallBefore, int? WallAfter)
    {
        public string Words => I($"{Length:0.##} ft from ({From.X:0.###}, {From.Y:0.###}) to ({To.X:0.###}, {To.Y:0.###})") +
                               $" ({(WallBefore is { } a ? $"wall W{a}" : "no wall")} to {(WallAfter is { } b ? $"wall W{b}" : "no wall")})";
    }

    /// <summary>How far a point is from a wall's plan rectangle (its centre line, its thickness across, its ends where
    /// the data puts them: a wall is drawn no longer than the data).</summary>
    public static double DistanceToWall(PlanPoint p, BuildWall w)
    {
        var length = Distance(w.Start, w.End);
        double ux = (w.End.X - w.Start.X) / length, uy = (w.End.Y - w.Start.Y) / length;
        double u = (p.X - w.Start.X) * ux + (p.Y - w.Start.Y) * uy, v = -(p.X - w.Start.X) * uy + (p.Y - w.Start.Y) * ux;
        double du = Math.Max(0, Math.Max(-u, u - length)), dv = Math.Max(0, Math.Abs(v) - w.ThicknessIn / 24);
        return Math.Sqrt(du * du + dv * dv);
    }

    /// <summary>Every stretch of <paramref name="room"/>'s boundary farther than <paramref name="tolerance"/> from every
    /// wall (sampled every <paramref name="step"/> ft along each side; each stretch widened by the tolerance to where
    /// the walls' ends are). Doors and windows stand in their walls, so an opening is no gap. The sheet's boundary
    /// lies on the walls' faces within a few hundredths of a foot; 0.25 ft is well clear of that.</summary>
    public static IReadOnlyList<BoundaryGap> BoundaryGaps(BuildRoom room, IReadOnlyList<BuildWall> walls, double tolerance = 0.25, double step = 0.02)
    {
        var gaps = new List<BoundaryGap>();
        var ring = room.Boundary.Count > 1 && Distance(room.Boundary[0], room.Boundary[^1]) < 1e-9 ? room.Boundary.Take(room.Boundary.Count - 1).ToList()
                   : room.Boundary.ToList();
        int? Nearest(PlanPoint p) => walls.Select(w => (w.Id, D: DistanceToWall(p, w))).Where(x => x.D <= 1).OrderBy(x => x.D)
                                          .Select(x => (int?)x.Id).FirstOrDefault();
        for (var i = 0; i < ring.Count; i++)
        {
            var (a, b) = (ring[i], ring[(i + 1) % ring.Count]);
            var length = Distance(a, b);
            if (length < 1e-9)
                continue;
            PlanPoint At(double s) => new(a.X + (b.X - a.X) * s / length, a.Y + (b.Y - a.Y) * s / length);
            var n = Math.Max(1, (int)Math.Ceiling(length / step));
            double? open = null;
            for (var k = 0; k <= n + 1; k++)
            {
                var s = Math.Min(k * length / n, length);
                var covered = k > n || walls.Any(w => DistanceToWall(At(s), w) <= tolerance);
                if (!covered && open is null)
                    open = s;
                else if (covered && open is { } o)
                {
                    var last = Math.Min((k - 1) * length / n, length);
                    double from = Math.Max(0, o - tolerance), to = Math.Min(length, last + tolerance);
                    gaps.Add(new BoundaryGap(At(from), At(to), to - from, Nearest(At(from)), Nearest(At(to))));
                    open = null;
                }
            }
        }
        return gaps;
    }

    /// <summary>Two walls of the data that lie along each other (parallel, closer than their half thicknesses, sharing
    /// <see cref="Length"/> ft): Revit warns "Highlighted walls overlap" and may ignore one as a room boundary.</summary>
    public sealed record WallOverlap(int A, int B, double Length, double Offset)
    {
        public string Words => I($"walls W{A} and W{B} overlap along {Length:0.##} ft ({Offset * 12:0.#} in apart, centre to centre)");
    }

    public static IReadOnlyList<WallOverlap> WallOverlaps(IReadOnlyList<BuildWall> walls)
    {
        var found = new List<WallOverlap>();
        for (var i = 0; i < walls.Count; i++)
            for (var j = i + 1; j < walls.Count; j++)
            {
                var (a, b) = (walls[i], walls[j]);
                var la = Distance(a.Start, a.End);
                double ux = (a.End.X - a.Start.X) / la, uy = (a.End.Y - a.Start.Y) / la;
                var lb = Distance(b.Start, b.End);
                double vx = (b.End.X - b.Start.X) / lb, vy = (b.End.Y - b.Start.Y) / lb;
                if (Math.Abs(ux * vy - uy * vx) > 0.02)
                    continue;
                var offset = Math.Abs(-(b.Start.X - a.Start.X) * uy + (b.Start.Y - a.Start.Y) * ux);
                if (offset >= (a.ThicknessIn + b.ThicknessIn) / 24 - 0.01)
                    continue;
                double t0 = (b.Start.X - a.Start.X) * ux + (b.Start.Y - a.Start.Y) * uy, t1 = (b.End.X - a.Start.X) * ux + (b.End.Y - a.Start.Y) * uy;
                var shared = Math.Min(la, Math.Max(t0, t1)) - Math.Max(0, Math.Min(t0, t1));
                if (shared > 0.05)
                    found.Add(new WallOverlap(a.Id, b.Id, shared, offset));
            }
        return found;
    }

    /// <summary>How a room Revit enclosed differs from the sheet's area, in words, when it is off by more than 2% or
    /// more than 5 sq ft (either: a wrong test model is a wrong test); null when within both, or the sheet gives none.
    /// Run 1's 23 enclosed rooms are within both (at most 1.8%, 3.8 sq ft: Revit measures to the walls' faces).</summary>
    public static string? AreaOff(double revitArea, double? sheetArea)
    {
        if (sheetArea is not { } sheet)
            return null;
        var off = revitArea - sheet;
        var share = sheet > 0 ? Math.Abs(off) / sheet : double.PositiveInfinity;
        return Math.Abs(off) > 5 || share > 0.02
            ? I($"Revit's {revitArea:0.#} sq ft, the sheet's {sheet:0.#}: {off:+0.#;-0.#} sq ft ({share * 100:0.#}%), more than 2% or 5 sq ft")
            : null;
    }

    /// <summary>A room Revit enclosed checked against the sheet's area, or, where the data gives none, the area inside
    /// its boundary, by the same limit (<see cref="AreaOff"/>); the words say which it was checked against. Null when
    /// within it.</summary>
    public static string? RoomAreaOff(double revitArea, BuildRoom room) =>
        room.AreaSf is { } sheet ? AreaOff(revitArea, sheet)
            : AreaOff(revitArea, Area(room.Boundary))?.Replace("the sheet's", "its boundary's (the sheet gives no area)");

    /// <summary>A message's numbers written the same on every machine (a decimal point, whatever the culture).</summary>
    internal static string I(FormattableString s) => s.ToString(CultureInfo.InvariantCulture);

    public static double Distance(PlanPoint a, PlanPoint b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));
}
