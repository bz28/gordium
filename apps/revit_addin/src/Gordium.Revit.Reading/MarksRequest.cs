using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>One mark to write: on the element (its <c>UniqueId</c>) or on its type, the value as Revit stores it.</summary>
/// <param name="Element">The element's <c>UniqueId</c>, or its type's when <paramref name="OnType"/>.</param>
/// <param name="OnType">A type mark (<see cref="MarkBinding.Type"/>): written once on the type.</param>
/// <param name="Mark">Which mark.</param>
/// <param name="Value">Its value, as Revit stores it (a Yes/No as 1 or 0, a length in feet).</param>
/// <param name="Label">The element, in words, for the log.</param>
public sealed record MarkWrite(string Element, bool OnType, MarkDefinition Mark, MarkValue Value, string Label);

/// <summary>A Room the request places before marking: on the level (its <c>UniqueId</c>), at a point (internal feet),
/// with its name and number.</summary>
public sealed record RoomToPlace(string Level, string LevelName, double X, double Y, string Name, string Number);

/// <summary>What a marks request writes, and every entry it refuses with why.</summary>
public sealed record MarksPlan(IReadOnlyList<MarkWrite> Writes, IReadOnlyList<string> Refused);

/// <summary>
/// A trial request that writes Gordium's marks into a copy of a model (set_marks_request.json, read while Revit is idle:
/// docs/revit/revit_interior_reading_design.md section 10): the eval's marks, Gordium standing in for the architect,
/// each labelled so. The decisions are here, tested; the Revit layer (<c>SetMarks.cs</c>) only writes the plan.
/// <code>
/// {"model": "...rvt", "save_as": "...rvt", "by": "eval assumption (Gordium, not the architect)", "date": "2026-11-21",
///  "marks": [{"room": "2", "mark": "Gordium: Use", "value": "Day care"},
///            {"door": "D02", "mark": "Gordium: Exit", "value": "Exterior door at discharge"},
///            {"unique_id": "...", "mark": "Gordium: Pass through", "value": false},
///            {"door": "D01", "clear": {"width_in": 34, "height_in": 80, "operation": "Side-hinged door", "source": "..."}}]}
/// </code>
/// A room is found by its number, a door or a window by its Mark, any element by its <c>UniqueId</c>; one that isn't found, or is
/// found twice, is refused. A value of the wrong kind, a word Gordium doesn't read (a use, an exit, an operation), a mark
/// not bound to the element's category, or two different values for one mark on one element (two doors of one type
/// given different clear openings) is refused, never guessed. A clear opening writes the type's operation, clear
/// width, height and source, and the confirmation stamp, made by <c>by</c>: so the stamp itself says who stood in.
/// </summary>
public static class MarksRequest
{
    /// <summary>Why a model path can't be used (null when it can): only a file under the trial folder
    /// (<c>%LOCALAPPDATA%\Gordium\trial</c>), never the architect's own files.</summary>
    public static string? PathProblem(string? path, string trialDir)
    {
        if (string.IsNullOrWhiteSpace(path))
            return "no path given";
        string full, root;
        try
        {
            full = Path.GetFullPath(path);
            root = Path.GetFullPath(trialDir).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        }
        catch (Exception x) when (x is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return $"\"{path}\" isn't a path ({x.Message})";
        }
        return full.StartsWith(root, StringComparison.OrdinalIgnoreCase) && full.EndsWith(".rvt", StringComparison.OrdinalIgnoreCase)
            ? null : $"\"{full}\" isn't a .rvt file under {root}: marks are only written into the trial's own copies";
    }

    public static MarksPlan Plan(JsonArray marks, RevitModel model, string by, string date)
    {
        var writes = new List<MarkWrite>();
        var refused = new List<string>();
        var elements = MarkReading.InDesign(model).ToList();
        foreach (var (entry, n) in marks.Select((e, i) => (e, i + 1)))
        {
            var where = $"entry {n}";
            if (entry is not JsonObject o)
            {
                refused.Add($"{where}: not a mapping");
                continue;
            }
            var (target, why) = Find(o, elements);
            if (target is null)
            {
                refused.Add($"{where}: {why}");
                continue;
            }
            where = $"entry {n} ({MarkingList.Label(target)})";
            if (o["clear"] is JsonObject clear)
                Clear(clear, target, by, date, where, writes, refused);
            else if (Mark(o, target, where, refused) is { } write)
                writes.Add(write);
        }
        // two different values for one mark on one element: neither is written
        var clashes = writes.GroupBy(w => (w.Element, w.Mark.Guid)).Where(g => g.Select(w => w.Value).Distinct().Count() > 1).ToList();
        foreach (var g in clashes)
            refused.Add($"{g.First().Label}: {g.First().Mark.Name} is given {g.Select(w => w.Value).Distinct().Count()} different values: none is written");
        var bad = clashes.Select(g => g.Key).ToHashSet();
        return new(writes.Where(w => !bad.Contains((w.Element, w.Mark.Guid))).DistinctBy(w => (w.Element, w.Mark.Guid)).ToList(), refused);
    }

    private static (MarkedElement? Found, string? Why) Find(JsonObject o, List<MarkedElement> elements)
    {
        List<MarkedElement> found;
        string what;
        if (Text(o["unique_id"]) is { } id)
            (found, what) = (elements.Where(e => e.UniqueId == id).ToList(), $"element {id}");
        else if (Text(o["room"]) is { } room)
            (found, what) = (elements.Where(e => MarkReading.KindOf(e) == MarkedKind.Room && e.Number?.Trim() == room).ToList(), $"room number {room}");
        else if (Text(o["door"]) is { } door)
            (found, what) = (elements.Where(e => MarkReading.KindOf(e) == MarkedKind.Door && e.Number?.Trim() == door).ToList(), $"door Mark {door}");
        else if (Text(o["window"]) is { } window)
            (found, what) = (elements.Where(e => MarkReading.KindOf(e) == MarkedKind.Window && e.Number?.Trim() == window).ToList(), $"window Mark {window}");
        else
            return (null, "names no unique_id, room, door or window");
        return found.Count switch
        {
            1 => (found[0], null),
            0 => (null, $"no {what} in the design checked"),
            _ => (null, $"{found.Count} elements are {what}: which one is meant isn't known"),
        };
    }

    private static MarkWrite? Mark(JsonObject o, MarkedElement e, string where, List<string> refused)
    {
        var name = Text(o["mark"]);
        var m = Marks.All.FirstOrDefault(x => x.Name == name);
        if (m is null)
        {
            refused.Add($"{where}: \"{name}\" isn't one of Gordium's marks");
            return null;
        }
        if (!m.Categories.Contains(e.BuiltInCategory))
        {
            refused.Add($"{where}: {m.Name} isn't bound to {e.BuiltInCategory}");
            return null;
        }
        MarkValue? value = (m.Kind, o["value"]) switch
        {
            (MarkValueKind.YesNo, JsonValue v) when v.GetValueKind() is JsonValueKind.True or JsonValueKind.False =>
                new MarkValue(true, v.GetValue<bool>() ? 1 : 0),
            (MarkValueKind.Text, JsonValue v) when v.GetValueKind() == JsonValueKind.String && Text(v) is { } t && Readable(m, e, t) =>
                new MarkValue(true, Text: t),
            (MarkValueKind.Length, _) when Number(o["value_in"]) is { } d && d > 0 =>
                new MarkValue(true, Number: d / 12),
            _ => null,
        };
        if (value is null)
        {
            refused.Add($"{where}: {m.Name}'s value {o["value"]?.ToJsonString() ?? o["value_in"]?.ToJsonString() ?? "(none)"} isn't " +
                        (m.Kind switch
                        {
                            MarkValueKind.YesNo => "true or false",
                            MarkValueKind.Length => "a length in inches (value_in) more than 0",
                            _ => "a word Gordium reads there",
                        }));
            return null;
        }
        if (m.Binding == MarkBinding.Type && e.TypeUniqueId is null)
        {
            refused.Add($"{where}: {m.Name} is a type mark, and the element has no type");
            return null;
        }
        return m.Binding == MarkBinding.Type
            ? new(e.TypeUniqueId!, true, m, value, $"type of {MarkingList.Label(e)}")
            : new(e.UniqueId, false, m, value, MarkingList.Label(e));
    }

    /// <summary>A text mark's word must be one Gordium reads on that element, so the mark written is the mark read.</summary>
    private static bool Readable(MarkDefinition m, MarkedElement e, string word) =>
        m == Marks.Use ? MarkReading.KindOf(e) != MarkedKind.Room || RoomUses.Table.Of(word) is not null
        : m == Marks.Exit ? ExitKinds.Table.Of(word) is not null
        : m == Marks.Operation ? Operations.ForOpening(word, MarkReading.KindOf(e) == MarkedKind.Door) is not null
        : m != Marks.ClearConfirmed;                         // the stamp is written only with its clear opening

    private static void Clear(JsonObject c, MarkedElement e, string by, string date, string where, List<MarkWrite> writes, List<string> refused)
    {
        double? Inches(string key) => Number(c[key]) is { } d
                                      && double.IsFinite(d) && d > 0 ? d / 12 : null;
        var (width, height, operation, source) = (Inches("width_in"), Inches("height_in"), Text(c["operation"]), Text(c["source"]));
        var door = MarkReading.KindOf(e) == MarkedKind.Door;
        if (!door || width is null || height is null || source is null || Operations.ForOpening(operation, isDoor: true) is null
            || e.TypeUniqueId is null || e.TypeWidth is null || e.TypeHeight is null)
        {
            refused.Add($"{where}: a door's clear opening needs width_in and height_in (more than 0), a door's operation word, a " +
                        "source, and a door whose type has its own width and height");
            return;
        }
        if (width > e.TypeWidth + InteriorReader.Sixteenth || height > e.TypeHeight + InteriorReader.Sixteenth)
        {
            refused.Add($"{where}: its clear opening ({width * 12:0.##} x {height * 12:0.##} in) is bigger than the door's type " +
                        $"({e.TypeWidth * 12:0.##} x {e.TypeHeight * 12:0.##} in)");
            return;
        }
        var stamp = ClearStamp.Make(new ClearValues(e.TypeUniqueId, e.TypeWidth, e.TypeHeight, operation, width, height, null, source, Door: true), by, date);
        var label = $"type of {MarkingList.Label(e)}";
        writes.Add(new(e.TypeUniqueId, true, Marks.Operation, new(true, Text: operation), label));
        writes.Add(new(e.TypeUniqueId, true, Marks.ClearWidth, new(true, Number: width), label));
        writes.Add(new(e.TypeUniqueId, true, Marks.ClearHeight, new(true, Number: height), label));
        writes.Add(new(e.TypeUniqueId, true, Marks.ClearSource, new(true, Text: source), label));
        writes.Add(new(e.TypeUniqueId, true, Marks.ClearConfirmed, new(true, Text: stamp), label));
    }

    /// <summary>A finite JSON number (an integer or not, however the node was made), or null.</summary>
    private static double? Number(JsonNode? n) =>
        n is JsonValue v && v.GetValueKind() == JsonValueKind.Number
        && double.TryParse(v.ToJsonString(), NumberStyles.Float, CultureInfo.InvariantCulture, out var d) && double.IsFinite(d) ? d : null;

    private static string? Text(JsonNode? n) =>
        n is JsonValue v && v.GetValueKind() == JsonValueKind.String && v.GetValue<string>() is { } s && !string.IsNullOrWhiteSpace(s)
            ? s.Trim() : null;

    /// <summary>The Rooms the request places before marking (<c>place_rooms</c>: <c>{"level": "Level 1", "at": [x, y],
    /// "name": "TOILET", "number": "31"}</c>, the point in the model's internal feet): each on a level of the model, at a
    /// finite point, with a name and a number no Room of the model has nor another placement; anything else refused
    /// with why. Where it lands is the Revit layer's to check (in an enclosed area with no Room, in the last phase), and
    /// a Room that isn't is taken back.</summary>
    public static (List<RoomToPlace> Rooms, List<string> Refused) Placements(JsonArray? place, RevitModel model)
    {
        var rooms = new List<RoomToPlace>();
        var refused = new List<string>();
        var levels = model.Marked.Where(e => MarkReading.KindOf(e) == MarkedKind.Level).ToList();
        var numbers = MarkReading.InDesign(model).Where(e => MarkReading.KindOf(e) == MarkedKind.Room)
            .Select(e => e.Number?.Trim()).OfType<string>().ToHashSet(StringComparer.Ordinal);
        foreach (var (entry, n) in (place ?? []).Select((e, i) => (e, i + 1)))
        {
            var where = $"room to place {n}";
            if (entry is not JsonObject o)
            {
                refused.Add($"{where}: not a mapping");
                continue;
            }
            var (levelName, name, number) = (Text(o["level"]), Text(o["name"]), Text(o["number"]));
            var at = o["at"] is JsonArray { Count: 2 } a && Number(a[0]) is { } x && Number(a[1]) is { } y ? (X: x, Y: y) : ((double X, double Y)?)null;
            var level = levels.Where(l => l.Name?.Trim() == levelName).ToList();
            var why = name is null || number is null ? "needs a name and a number"
                : at is null ? "needs `at`, a point [x, y] in feet"
                : level.Count != 1 ? $"{(level.Count == 0 ? "no" : level.Count.ToString(CultureInfo.InvariantCulture))} levels are named \"{levelName}\""
                : !numbers.Add(number) ? $"a Room numbered {number} is already in the model or the request"
                : null;
            if (why is not null)
                refused.Add($"{where} ({name ?? "?"} {number ?? "?"}): {why}");
            else
                rooms.Add(new RoomToPlace(level[0].UniqueId, levelName!, at!.Value.X, at.Value.Y, name!, number!));
        }
        return (rooms, refused);
    }

    /// <summary>The request's date: given, or today's (UTC) when not.</summary>
    public static string Date(JsonNode? n) => Text(n) ?? DateTime.UtcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
}
