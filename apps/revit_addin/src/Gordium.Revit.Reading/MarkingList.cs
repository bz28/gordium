using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace Gordium.Revit.Reading;

// The architect's marks read from the model (docs/revit/revit_interior_reading_design.md, sections 2, 3 and 5a), and
// the marking list built from them. The one rule (principle 4): a mark never set is not stated, never "No"; a
// suggestion is shown, never read as a mark.

public enum MarkedKind { Room, Window, Door }

/// <summary>A room's mark, read: <see cref="Sleeping"/> null when not stated.</summary>
public sealed record RoomMarks(string Id, string? Name, bool? Sleeping);

/// <summary>A window's or door's marks as an opening: null when not stated (an operation word not in the list, or a
/// door's word that isn't a door's, is not stated).</summary>
public sealed record OpeningMarks(string Id, MarkedKind Kind, bool? Escape, string? Operation);

/// <summary>A door's marks as a door.</summary>
public sealed record DoorMarks(string Id, bool? Exit, string? Operation);

/// <summary>What the reader takes from the marks: the rooms, windows and doors in the design checked (the last phase,
/// the main model and the option checked of each set: the outside reader's one rule), each mark read as stated or
/// not. The interior reader (section 7, step 3 on) builds the description's flags from these alone.</summary>
public static class MarkReading
{
    public static IEnumerable<MarkedElement> InDesign(RevitModel model) =>
        model.Marked.Where(e => SiteReader.InDesignChecked(model, e.PhaseDemolished, e.DesignOption) && InLastPhase(model, e));

    /// <summary>A room belongs to one phase: only the last phase's rooms are the design checked (an earlier phase's
    /// room is the house as it was). A window or door created in any phase is there by the last one unless
    /// demolished (<see cref="SiteReader.InDesignChecked"/>). A phase the document doesn't list, or none, is kept: an
    /// extra room can only make the check more cautious.</summary>
    private static bool InLastPhase(RevitModel model, MarkedElement e) =>
        KindOf(e) != MarkedKind.Room || model.Phases.Count == 0 || e.PhaseCreated is not { } phase
        || !model.Phases.Contains(phase) || phase == model.Phases[^1];

    /// <summary>The rooms in the design checked that aren't rooms on the plan: unplaced, not enclosed, redundant, or
    /// a placement the Revit layer didn't give. While any exists no room can be read (design note, section 2: a
    /// bedroom may be one of them), so they are listed first, never as rows to mark.</summary>
    public static IReadOnlyList<MarkedElement> RoomBlockers(RevitModel model) =>
        InDesign(model).Where(e => KindOf(e) == MarkedKind.Room && e.Placement != RoomPlacement.Placed).ToList();

    public static MarkedKind? KindOf(MarkedElement e) => e.BuiltInCategory switch
    {
        Marks.Rooms => MarkedKind.Room,
        Marks.Windows => MarkedKind.Window,
        Marks.Doors => MarkedKind.Door,
        _ => null,
    };

    private static MarkValue? Get(MarkedElement e, MarkDefinition m) =>
        (m.Binding == MarkBinding.Instance ? e.Instance : e.Type).TryGetValue(m.Guid, out var v) ? v : null;

    /// <summary>The rooms in the design checked, each with its mark; <b>null (rooms not read)</b> while any
    /// <see cref="RoomBlockers"/> exists: a bedroom may be the room not on the plan, so the description leaves
    /// <c>rooms</c> out until each is placed or deleted (design note, section 2), never a list without it.</summary>
    public static IReadOnlyList<RoomMarks>? Rooms(RevitModel model) =>
        RoomBlockers(model).Count > 0 ? null
        : InDesign(model).Where(e => KindOf(e) == MarkedKind.Room)
            .Select(e => new RoomMarks(e.UniqueId, e.Name, Marks.YesNo(Get(e, Marks.SleepingRoom)))).ToList();

    public static IReadOnlyList<OpeningMarks> Openings(RevitModel model) =>
        InDesign(model).Where(e => KindOf(e) is MarkedKind.Window or MarkedKind.Door)
            .Select(e => new OpeningMarks(e.UniqueId, KindOf(e)!.Value, Marks.YesNo(Get(e, Marks.EscapeOpening)),
                                          Operations.ForOpening(Marks.Text(Get(e, Marks.Operation)),
                                                                isDoor: KindOf(e) == MarkedKind.Door))).ToList();

    public static IReadOnlyList<DoorMarks> Doors(RevitModel model) =>
        InDesign(model).Where(e => KindOf(e) == MarkedKind.Door)
            .Select(e => new DoorMarks(e.UniqueId, Marks.YesNo(Get(e, Marks.ExitDoor)),
                                       Operations.ForDoor(Marks.Text(Get(e, Marks.Operation))))).ToList();

    internal static MarkValue? Value(MarkedElement e, MarkDefinition m) => Get(e, m);

    /// <summary>The architect's "these are all the stairs" tick on Project Information: null when not set.</summary>
    public static bool? AllStairs(RevitModel model) =>
        Marks.YesNo(model.ProjectMarks.TryGetValue(Marks.AllStairs.Guid, out var v) ? v : null);
}

/// <summary>How one mark stands on one element in the marking list.</summary>
public enum MarkState
{
    Yes,
    No,

    /// <summary>A word from the operation list.</summary>
    Given,

    /// <summary>Never set: not stated.</summary>
    Unset,

    /// <summary>Set, but not to anything Gordium reads (an operation word not in the list): not stated.</summary>
    NotUnderstood,
}

/// <summary>One mark on one row. <see cref="Suggestion"/> is only shown ("suggested: Yes"); it is never a mark.</summary>
public sealed record MarkCell(MarkDefinition Mark, MarkState State, string? Value, string? Suggestion, string? Words)
{
    public bool NeedsMarking => State is MarkState.Unset or MarkState.NotUnderstood;
}

/// <summary>One room, window or door in the list.</summary>
public sealed record MarkingRow(string Id, MarkedKind Kind, string Label, IReadOnlyList<MarkCell> Cells)
{
    public bool NeedsMarking => Cells.Any(c => c.NeedsMarking);
}

/// <summary>The "Mark for egress" list: what stops a mark being added first, then a line per kind saying what an
/// unset mark leaves not read, then every row, the ones with anything unset first.</summary>
public sealed record MarkingListResult(IReadOnlyList<string> SetupProblems, IReadOnlyList<string> RoomBlockers,
                                       IReadOnlyList<string> Summary, IReadOnlyList<MarkingRow> Rows)
{
    public const string NothingDrawn = "No rooms, windows or doors are drawn";
    public const string NoRooms = "No rooms are drawn";
    public const string NotAllMarked = "Some marks are not set or can't be read";
    public const string AllMarked = "Every room, window and door is marked";

    /// <summary>What could hide a stair (step 4), listed after the room blockers: while any is there no stair is read.</summary>
    public IReadOnlyList<string> StairBlockers { get; init; } = [];

    /// <summary>The list's headline: every room, window and door marked only when there are rooms, nothing is
    /// unset, and nothing stops a mark or a room being read.</summary>
    public string Headline =>
        Rows.Count == 0 && RoomBlockers.Count == 0 ? NothingDrawn
        : SetupProblems.Count > 0 || RoomBlockers.Count > 0 || Rows.Any(r => r.NeedsMarking) ? NotAllMarked
        : !Rows.Any(r => r.Kind == MarkedKind.Room) ? NoRooms
        : AllMarked;
}

public static class MarkingList
{
    /// <summary>Room names offered as a suggestion that the room is a sleeping room (Ben, 2026-11-19, decision 3).
    /// Only a suggestion of Yes, and only on a room whose mark is unset: a suggested No is never offered (it is the
    /// direction that could hide a bedroom), and a suggestion is never read as the mark.</summary>
    private static readonly Regex SleepingName = new(@"\b(bed\s*room|sleeping)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    public static MarkingListResult Build(RevitModel model, IReadOnlyList<MarkSetupStep>? setup = null)
    {
        var rows = MarkReading.InDesign(model).Select(Row).OfType<MarkingRow>()
            .OrderByDescending(r => r.NeedsMarking).ThenBy(r => r.Kind)
            .ThenBy(r => r.Label, StringComparer.OrdinalIgnoreCase).ThenBy(r => r.Id, StringComparer.Ordinal)
            .ToList();
        var problems = (setup ?? []).Where(s => s.Action == MarkSetupAction.Conflict)
            .Select(s => $"{s.Mark.Name}: {s.Words}").ToList();
        var blockers = MarkReading.RoomBlockers(model).Select(Blocker).OrderBy(b => b, StringComparer.OrdinalIgnoreCase).ToList();
        var placement = blockers.Count;
        // with the model's inside read (step 3): every enclosed area with no Room, closed workset and link that could
        // hold one stops every room being read too, so it is listed first (design note, section 2)
        var others = InteriorReader.OtherRoomBlockers(model);
        blockers.AddRange(others);
        var summary = Summary(rows, placement, others.Count);
        // step 4: the project-wide tick, always shown; and, with the model's inside read, what could hide a stair
        var stairBlockers = StairReader.Blockers(model);
        summary.Add(MarkReading.AllStairs(model) switch
        {
            true => $"{Marks.AllStairs.Name}: Yes (on Project Information).",
            var tick => $"{Marks.AllStairs.Name}: {(tick is false ? "No" : "not set")} on Project Information, so no stair is " +
                        "read for egress until it says Yes.",
        });
        if (stairBlockers.Count > 0)
            summary.Add((stairBlockers.Count == 1 ? "1 element, workset or link" : $"{stairBlockers.Count} elements, worksets or links") +
                        " listed above could hide a stair, so no stair is read for egress until each is resolved.");
        return new(problems, blockers, summary, rows) { StairBlockers = stairBlockers };
    }

    private static string RoomLabel(MarkedElement e) =>
        string.Join(" ", new[] { e.Name, e.Number }.Where(s => !string.IsNullOrWhiteSpace(s))) is { Length: > 0 } label
            ? label : "(a room with no name or number)";

    /// <summary>A blocker's line: "Room "Room 100": not enclosed..." (the room's own name quoted, so Revit's default
    /// name "Room" doesn't read as a doubled word).</summary>
    private static string Blocker(MarkedElement e) =>
        (string.Join(" ", new[] { e.Name, e.Number }.Where(s => !string.IsNullOrWhiteSpace(s))) is { Length: > 0 } label
            ? $"Room \"{label}\"" : "A room with no name or number") + ": " + (e.Placement switch
    {
        RoomPlacement.Unplaced => "not placed: place it in a closed area or delete it",
        RoomPlacement.NotEnclosed => "not enclosed: close its walls or room separation lines, or delete it",
        RoomPlacement.Redundant => "redundant (another room is in the same area): delete one",
        _ => "its placement couldn't be read",
    });

    private static MarkingRow? Row(MarkedElement e)
    {
        switch (MarkReading.KindOf(e))
        {
            case MarkedKind.Room when e.Placement != RoomPlacement.Placed:
                return null;                                    // a blocker (RoomBlockers), not a room to mark
            case MarkedKind.Room:
                return new(e.UniqueId, MarkedKind.Room, RoomLabel(e), [YesNo(e, Marks.SleepingRoom, SuggestSleeping(e))]);
            case MarkedKind.Window:
                return new(e.UniqueId, MarkedKind.Window, Label(e),
                           [YesNo(e, Marks.EscapeOpening, null), Operation(e, door: false)]);
            case MarkedKind.Door:
                return new(e.UniqueId, MarkedKind.Door, Label(e),
                           [YesNo(e, Marks.EscapeOpening, null), YesNo(e, Marks.ExitDoor, null), Operation(e, door: true)]);
            default:
                return null;
        }
    }

    internal static string Label(MarkedElement e)
    {
        var what = string.Join(": ", new[] { e.Family, e.Name }.Where(s => !string.IsNullOrWhiteSpace(s)));
        if (what.Length == 0)
            what = e.UniqueId;
        return string.IsNullOrWhiteSpace(e.Number) ? what : $"{what} ({e.Number})";
    }

    private static string? SuggestSleeping(MarkedElement e) =>
        e.Name is { } n && SleepingName.IsMatch(n) ? $"suggested: Yes (named \"{n.Trim()}\"); set it yourself to accept" : null;

    private static MarkCell YesNo(MarkedElement e, MarkDefinition m, string? suggestion) =>
        Marks.YesNo(MarkReading.Value(e, m)) switch
        {
            true => new(m, MarkState.Yes, "Yes", null, null),
            false => new(m, MarkState.No, "No", null, null),
            null => new(m, MarkState.Unset, null, suggestion, "not set"),
        };

    private static MarkCell Operation(MarkedElement e, bool door)
    {
        var m = Marks.Operation;
        var word = Marks.Text(MarkReading.Value(e, m));
        if (word is null)
            return new(m, MarkState.Unset, null, null, "not set on this type");
        var read = Operations.ForOpening(word, isDoor: door);      // the reader's own rule (MarkReading.Openings)
        if (read is not null)
            return new(m, MarkState.Given, word, null, null);
        var words = Operations.ForOpening(word) is not null
            ? $"\"{word}\" is a window's operation, not a door's: use " +
              string.Join(", ", Operations.Words.Where(w => Operations.ForDoor(w) is not null))
            : $"\"{word}\" isn't one of Gordium's operations ({string.Join(", ", Operations.Words)})";
        return new(m, MarkState.NotUnderstood, word, null, words);
    }

    private static List<string> Summary(List<MarkingRow> rows, int placement, int others)
    {
        var lines = new List<string>();
        var blockers = placement + others;
        if (placement > 0)
            lines.Add((placement == 1 ? "1 Room is" : $"{placement} Rooms are") + " unplaced, not enclosed or redundant, " +
                      "so no room is read for egress until each is placed or deleted.");
        if (others > 0)
            lines.Add((others == 1 ? "1 enclosed area, workset or link" : $"{others} enclosed areas, worksets or links") +
                      " listed above could hide a room, " +
                      "so no room is read for egress until each is resolved.");
        void Flag(MarkedKind[] kinds, MarkDefinition m, string plural, string consequence)
        {
            var cells = rows.Where(r => kinds.Contains(r.Kind)).Select(r => r.Cells.First(c => c.Mark == m)).ToList();
            if (cells.Count == 0)
                return;
            var unset = cells.Count(c => c.NeedsMarking);
            lines.Add(unset == 0
                ? $"{m.Name}: all {cells.Count} {plural} marked."
                : $"{m.Name}: {unset} of {cells.Count} {plural} not marked, so {consequence} until each says Yes or No.");
        }
        if (blockers == 0 && !rows.Any(r => r.Kind == MarkedKind.Room))
            lines.Add(MarkingListResult.NoRooms + ": egress waits until the house's Rooms are placed.");
        Flag([MarkedKind.Room], Marks.SleepingRoom, "rooms", "no room is read for egress");
        Flag([MarkedKind.Window, MarkedKind.Door], Marks.EscapeOpening, "windows and doors", "no escape opening is read");
        Flag([MarkedKind.Door], Marks.ExitDoor, "doors", "no door is read");
        var noOperation = rows.Count(r => r.Cells.Any(c => c.Mark == Marks.Operation && c.NeedsMarking));
        if (noOperation > 0)
            lines.Add(string.Format(CultureInfo.InvariantCulture,
                "{0}: {1} windows and doors have no operation Gordium reads, so their egress measures need review.",
                Marks.Operation.Name, noOperation));
        return lines;
    }

    /// <summary>The list as plain text (the add-in's first, minimal view of it; a UI pass comes later).</summary>
    public static string Text(MarkingListResult list, int maxRows = 40)
    {
        var sb = new StringBuilder();
        foreach (var p in list.SetupProblems)
            sb.Append("Can't add ").Append(p).Append('\n');
        foreach (var b in list.RoomBlockers.Concat(list.StairBlockers))
            sb.Append(b).Append('\n');
        foreach (var s in list.Summary)
            sb.Append(s).Append('\n');
        var shown = 0;
        foreach (var r in list.Rows)
        {
            if (shown++ == maxRows)
            {
                sb.Append($"... and {list.Rows.Count - maxRows} more (every row is in the log)\n");
                break;
            }
            sb.Append('\n').Append(r.NeedsMarking ? "TO MARK  " : "marked   ").Append(r.Kind).Append(": ").Append(r.Label);
            foreach (var c in r.Cells)
            {
                sb.Append("\n    ").Append(c.Mark.Name).Append(": ").Append(c.Value ?? c.Words);
                if (c.Value is not null && c.Words is not null)
                    sb.Append(" (").Append(c.Words).Append(')');
                if (c.Suggestion is not null)
                    sb.Append(" - ").Append(c.Suggestion);
            }
        }
        return sb.ToString();
    }
}
