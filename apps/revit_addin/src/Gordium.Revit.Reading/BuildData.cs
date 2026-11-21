using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>A point on the plan, in feet.</summary>
public readonly record struct PlanPoint(double X, double Y);

/// <summary>A wall of the data: its centre line from <see cref="Start"/> to <see cref="End"/> on the level.</summary>
public sealed record BuildWall(int Id, PlanPoint Start, PlanPoint End, double ThicknessIn, string Status, bool SmokePartition,
                               string? FireRating, double HeightFt, bool Exterior);

/// <summary>A door of the data (<see cref="Number"/> its place in the list from 1, as the script's marks D01...): its
/// centre on its host wall, <see cref="SwingDir"/> the side its leaf opens to, <see cref="Hinge"/> its hinge jamb (a
/// single door's; none on a double).</summary>
public sealed record BuildDoor(int Number, PlanPoint Center, double WidthIn, double HeightIn, string Kind, int HostWall,
                               PlanPoint SwingDir, PlanPoint? Hinge)
{
    public bool IsDouble => Kind == "double";
}

/// <summary>A window of the data (<see cref="Number"/> from 1, as the script's marks WN01...).</summary>
public sealed record BuildWindow(int Number, PlanPoint Center, double WidthIn, double HeightIn, double SillIn, int HostWall);

/// <summary>A room of the data: Revit places it at <see cref="TagPoint"/> and finds its outline from the walls;
/// <see cref="Boundary"/> and <see cref="AreaSf"/> (the sheet's) are kept to compare with what Revit finds.</summary>
public sealed record BuildRoom(string Number, string Name, PlanPoint TagPoint, IReadOnlyList<PlanPoint> Boundary, double? AreaSf);

/// <summary>A building to draw in a new Revit project (apps/revit_addin/tools/extract_build_data.py writes it from a
/// drawing script's DATA): one level, its walls, the doors and windows in them, its rooms and the floor under its
/// footprint (a closed ring: its last point its first).</summary>
public sealed record BuildModel(string Project, string LevelName, double LevelElevation, IReadOnlyList<BuildWall> Walls,
                                IReadOnlyList<BuildDoor> Doors, IReadOnlyList<BuildWindow> Windows, IReadOnlyList<BuildRoom> Rooms,
                                IReadOnlyList<PlanPoint> Footprint, string? SourceFile, string? SourceSha256);

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
        var known = new HashSet<string> { "data", "template", "save_as", "swing_opposite_facing", "hinge_opposite_hand", "use_phases" };
        problems.AddRange(o.Select(p => p.Key).Where(k => !known.Contains(k)).Select(k => $"the request has {k}, which isn't asked for (a misspelling?)"));
        var data = Text("data", true);
        var template = Text("template", false);
        var save = Text("save_as", true);
        if (save is not null && !save.EndsWith(".rvt", StringComparison.OrdinalIgnoreCase))
            problems.Add($"save_as {save} isn't a .rvt file");
        if (template is not null && !template.EndsWith(".rte", StringComparison.OrdinalIgnoreCase))
            problems.Add($"template {template} isn't a .rte file");
        var request = new BuildRequest(data ?? "", template, save ?? "", Flag("swing_opposite_facing"), Flag("hinge_opposite_hand"), Flag("use_phases"));
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
        if (data["level"] is not JsonObject level || Str(level["name"]) is not { Length: > 0 } ln || !Num(level["elevation_ft"], out elevation))
            p.Add("data: level isn't a level with a name and elevation_ft");
        else
            levelName = ln;

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
            if (w["fire_rating"] is { } fr)
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
            walls.Add(new BuildWall(id, start, end, thick, status ?? "", smoke ?? false, rating, height, exterior ?? false));
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
            var swing = NeedPt(d, where, "swing_dir");
            if (d["swing_dir"] is not null && Pt(d["swing_dir"], out _) && Math.Abs(Math.Sqrt(swing.X * swing.X + swing.Y * swing.Y) - 1) >= 0.01)
                p.Add($"{where}: swing_dir is {d["swing_dir"]!.ToJsonString()}, not a unit vector [x, y]");
            PlanPoint? hinge = null;
            if (d["hinge"] is { } hn)
            {
                if (Pt(hn, out var hp))
                    hinge = hp;
                else
                    p.Add($"{where}: hinge is {hn.ToJsonString()}, not a point [x, y]");
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
            if (r["area_sf"] is { } an)
            {
                if (Num(an, out var a))
                    area = a;
                else
                    p.Add($"{where}: area_sf is {an.ToJsonString()}, not a number");
            }
            rooms.Add(new BuildRoom(number ?? "", name ?? "", tag, boundary, area));
        }
        var footprint = new List<PlanPoint>();
        if (data["footprint"] is JsonArray fp && fp.Count >= 4 && fp.All(n => Pt(n, out _)))
        {
            footprint.AddRange(fp.Select(n => { Pt(n, out var q); return q; }));
            if (Distance(footprint[0], footprint[^1]) > 1e-9)
                p.Add("footprint: its last point isn't its first (the add-in, as the script, drops the closing point)");
        }
        else
            p.Add("footprint: not a list of 4 or more points [x, y]");
        if (data["stats"] is JsonObject stats)
            foreach (var (key, count) in new[] { ("walls", walls.Count), ("doors", doors.Count), ("windows", windows.Count), ("rooms", rooms.Count) })
                if (stats[key] is { } s && !(s is JsonValue sv && sv.TryGetValue(out int n) && n == count))
                    p.Add($"stats: {key} says {s.ToJsonString()}, the data has {count}");
        if (p.Count > 0)
            throw new BuildDataException(p);
        var source = data["extracted_from"] as JsonObject;
        return new BuildModel(project!, levelName, elevation, walls, doors, windows, rooms, footprint,
                              Str(source?["file"]), Str(source?["sha256"]));
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
    public static string OpeningTypeName(string tag, double widthIn, double heightIn) => $"{tag} {G(widthIn)}\" x {G(heightIn)}\" (LS1.0)";

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

    /// <summary>Whether to flip a door's facing so its leaf opens to <paramref name="swingDir"/>: in Revit's stock door
    /// families the leaf opens to the side opposite the facing arrow (the script's SWING_OPPOSITE_FACING, true), so the
    /// facing is flipped when it points the way the door should swing (or, with the toggle false, when it points
    /// away). A facing square to the swing (dot 0) is left.</summary>
    public static bool FlipFacing(PlanPoint facing, PlanPoint swingDir, bool swingOppositeFacing) =>
        (facing.X * swingDir.X + facing.Y * swingDir.Y) * (swingOppositeFacing ? -1.0 : 1.0) < 0;

    /// <summary>Whether to flip a door's hand so it hinges at <paramref name="hinge"/>: read once the facing is set
    /// (flipping the facing mirrors across the wall, which leaves the hand as it was). The script's
    /// HINGE_OPPOSITE_HAND (true): the stock families hinge on the side opposite the hand arrow.</summary>
    public static bool FlipHand(PlanPoint hand, PlanPoint center, PlanPoint hinge, bool hingeOppositeHand) =>
        (hand.X * (hinge.X - center.X) + hand.Y * (hinge.Y - center.Y)) * (hingeOppositeHand ? -1.0 : 1.0) < 0;

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

    public static double Distance(PlanPoint a, PlanPoint b) => Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));
}
