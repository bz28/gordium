using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace Gordium.Revit.Reading;

// The architect's marks read from the model (docs/revit/revit_interior_reading_design.md, sections 2, 3 and 5a), and
// the marking list built from them. The one rule (principle 4): a mark never set is not stated, never "No"; a
// suggestion is shown, never read as a mark.

public enum MarkedKind { Room, Window, Door, Level, SiteSlab, SiteObject }

/// <summary>A room's marks, read: each null when not stated. <see cref="Use"/> is the description's word (null for a
/// word not in <see cref="RoomUses"/>), <see cref="UseWord"/> what the architect typed.</summary>
public sealed record RoomMarks(string Id, string? Name, bool? Sleeping, string? Use = null, string? UseWord = null,
                               bool? Lockable = null, bool? PassThrough = null, bool? NotOccupied = null,
                               string? Function = null, string? FunctionWord = null,
                               int? FireRatingMinutes = null, bool? SmokePartitions = null);

/// <summary>A window's or door's marks as an opening: null when not stated (an operation word not in the list, or a
/// door's word that isn't a door's, is not stated).</summary>
public sealed record OpeningMarks(string Id, MarkedKind Kind, bool? Escape, string? Operation);

/// <summary>A door's marks as a door. <see cref="ExitKind"/> is the description's word (null when not set, or for a
/// word not in <see cref="ExitKinds"/>), <see cref="ExitWord"/> what the architect typed; <see cref="Hardware"/> likewise
/// the description's word for <c>Gordium: Hardware</c> (null when not set or not a word in <see cref="HardwareWords"/>),
/// <see cref="HardwareWord"/> what was typed.</summary>
public sealed record DoorMarks(string Id, bool? Exit, string? Operation, string? ExitKind = null, string? ExitWord = null,
                               int? Leaves = null, string? Hardware = null, string? HardwareWord = null);

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
        Marks.Levels => MarkedKind.Level,
        _ => null,
    };

    /// <summary>The levels in the model the architect marked "no rooms on this level" Yes (unset or No: not stated).</summary>
    public static IReadOnlyList<MarkedElement> LevelsMarkedNoRooms(RevitModel model) =>
        InDesign(model).Where(e => KindOf(e) == MarkedKind.Level && Marks.YesNo(Get(e, Marks.NoRoomsOnLevel)) is true).ToList();

    private static MarkValue? Get(MarkedElement e, MarkDefinition m) =>
        (m.Binding == MarkBinding.Instance ? e.Instance : e.Type).TryGetValue(m.Guid, out var v) ? v : null;

    /// <summary>The rooms in the design checked, each with its mark; <b>null (rooms not read)</b> while any
    /// <see cref="RoomBlockers"/> exists: a bedroom may be the room not on the plan, so the description leaves
    /// <c>rooms</c> out until each is placed or deleted (design note, section 2), never a list without it.</summary>
    public static IReadOnlyList<RoomMarks>? Rooms(RevitModel model) =>
        RoomBlockers(model).Count > 0 ? null
        : InDesign(model).Where(e => KindOf(e) == MarkedKind.Room)
            .Select(e => new RoomMarks(e.UniqueId, e.Name, Marks.YesNo(Get(e, Marks.SleepingRoom)),
                                       RoomUses.Table.Of(Marks.Text(Get(e, Marks.Use))), Marks.Text(Get(e, Marks.Use)),
                                       Marks.YesNo(Get(e, Marks.CanBeLocked)), Marks.YesNo(Get(e, Marks.PassThrough)),
                                       Marks.YesNo(Get(e, Marks.NotOccupied)),
                                       RoomFunctions.Of(Marks.Text(Get(e, Marks.RoomFunction))), Marks.Text(Get(e, Marks.RoomFunction)),
                                       Marks.Count(Get(e, Marks.CorridorFireRating)), Marks.YesNo(Get(e, Marks.SmokePartitionWalls)))).ToList();

    public static IReadOnlyList<OpeningMarks> Openings(RevitModel model) =>
        InDesign(model).Where(e => KindOf(e) is MarkedKind.Window or MarkedKind.Door)
            .Select(e => new OpeningMarks(e.UniqueId, KindOf(e)!.Value, Marks.YesNo(Get(e, Marks.EscapeOpening)),
                                          Operations.ForOpening(Marks.Text(Get(e, Marks.Operation)),
                                                                isDoor: KindOf(e) == MarkedKind.Door))).ToList();

    public static IReadOnlyList<DoorMarks> Doors(RevitModel model) =>
        InDesign(model).Where(e => KindOf(e) == MarkedKind.Door)
            .Select(e => new DoorMarks(e.UniqueId, Marks.YesNo(Get(e, Marks.ExitDoor)),
                                       Operations.ForDoor(Marks.Text(Get(e, Marks.Operation))),
                                       ExitKinds.Table.Of(Marks.Text(Get(e, Marks.Exit))), Marks.Text(Get(e, Marks.Exit)), Marks.Count(Get(e, Marks.DoorLeaves)),
                                       HardwareWords.Table.Of(Marks.Text(Get(e, Marks.DoorHardware))), Marks.Text(Get(e, Marks.DoorHardware)))).ToList();

    internal static MarkValue? Value(MarkedElement e, MarkDefinition m) => Get(e, m);

    /// <summary>The architect's "these are all the stairs" tick on Project Information: null when not set.</summary>
    public static bool? AllStairs(RevitModel model) =>
        Marks.YesNo(model.ProjectMarks.TryGetValue(Marks.AllStairs.Guid, out var v) ? v : null);

    /// <summary>The architect's "these are all the guards and handrails" tick on Project Information: null when not set.</summary>
    public static bool? AllGuards(RevitModel model) =>
        Marks.YesNo(model.ProjectMarks.TryGetValue(Marks.AllGuards.Guid, out var v) ? v : null);
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

    /// <summary>Set on an element the reader doesn't read it on (a context object, one of Gordium's own markers): shown
    /// with why, never as given; nothing to mark.</summary>
    NotReadHere,

    /// <summary>Never set, on a mark whose blank the description itself gives a meaning (escape routes: a room with no
    /// use, lock or pass-through mark is never crossed by a route; a door with no exit mark is not an exit): shown
    /// with that meaning, and nothing to mark, since a house never needs it. Never sent as a value.</summary>
    LeftBlank,
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

    /// <summary>Every "this house has none of" tick that disagrees with what is drawn (step 6): listed first of all.</summary>
    public IReadOnlyList<string> HasNoneConflicts { get; init; } = [];

    /// <summary>Every level marked "no rooms on this level" with a Room drawn on it: listed first, with the ticks'.</summary>
    public IReadOnlyList<string> LevelConflicts { get; init; } = [];

    /// <summary>Every Revit stair or railing marked <c>Gordium: Not a stair</c> Yes (the mark can't clear one): listed
    /// first, with the other conflicts.</summary>
    public IReadOnlyList<string> NotAStairConflicts { get; init; } = [];

    /// <summary>Every element the architect cleared with <c>Gordium: Not a stair</c>, a line per category and type:
    /// listed with what could hide a stair, so each exemption is seen.</summary>
    public IReadOnlyList<string> NotAStair { get; init; } = [];

    /// <summary>Every enclosed area with no Room (sent as a space whose use isn't known, so every sleeping-room rule
    /// needs review), listed after what stops the rooms being read.</summary>
    public IReadOnlyList<string> UnknownAreas { get; init; } = [];

    /// <summary>A line per "this house has none of" tick (step 6): sent, not sent and why, or not set (with what the
    /// reader found, as a proposal only).</summary>
    public IReadOnlyList<string> HasNoneLines { get; init; } = [];

    /// <summary>A line per window type a maker's clear-opening data concerns (<see cref="ClearPrefills"/>): filled by
    /// Gordium as a draft to confirm, not filled and why, or the maker's PDF to take it from.</summary>
    public IReadOnlyList<string> ClearLines { get; init; } = [];

    /// <summary>The list's headline: every room, window and door marked only when there are rooms, nothing is
    /// unset, and nothing stops a mark or a room being read.</summary>
    public string Headline =>
        Rows.Count == 0 && RoomBlockers.Count == 0 ? NothingDrawn
        : HasNoneConflicts.Count > 0 || LevelConflicts.Count > 0 || NotAStairConflicts.Count > 0 || SetupProblems.Count > 0 || RoomBlockers.Count > 0
          || UnknownAreas.Count > 0 || Rows.Any(r => r.NeedsMarking) ? NotAllMarked
        : !Rows.Any(r => r.Kind == MarkedKind.Room) ? NoRooms
        : AllMarked;
}

public static class MarkingList
{
    /// <summary>Room names offered as a suggestion that the room is a sleeping room (Ben, 2026-11-19, decision 3).
    /// Only a suggestion of Yes, and only on a room whose mark is unset: a suggested No is never offered (it is the
    /// direction that could hide a bedroom), and a suggestion is never read as the mark.</summary>
    private static readonly Regex SleepingName = new(@"\b(bed\s*room|sleeping)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <param name="model">The model read.</param>
    /// <param name="setup">The mark-setup steps planned.</param>
    /// <param name="clearWriteFailed">Why writing the makers' clear openings just failed, or null (<see cref="ClearPrefills.Plan"/>).</param>
    public static MarkingListResult Build(RevitModel model, IReadOnlyList<MarkSetupStep>? setup = null, string? clearWriteFailed = null)
    {
        // every floor outside the house (SiteSlabs), on the lot or not: which are on it is the check's own decision
        // (objects.left_out, with the lot the check is given), never guessed here (review round 2), so the list asks for
        // each and says that one off the lot changes nothing
        var slabs = SiteSlabs.Find(model).Values.ToList();
        // a level is listed when it has an enclosed area with no Room (whatever its mark), or its mark is set
        var unmarkedAreas = InteriorReader.UnknownAreas(model, levelMarks: false);
        var rows = MarkReading.InDesign(model)
            .Select(e => MarkReading.KindOf(e) == MarkedKind.Level ? LevelRow(e, unmarkedAreas) : Row(e)).OfType<MarkingRow>()
            .Concat(slabs.Select(SlabRow))
            .Concat(SiteObjectRows(model))
            .OrderByDescending(r => r.NeedsMarking).ThenBy(r => r.Kind)
            .ThenBy(r => r.Label, StringComparer.OrdinalIgnoreCase).ThenBy(r => r.Id, StringComparer.Ordinal)
            .ToList();
        var problems = (setup ?? []).Where(s => s.Action == MarkSetupAction.Conflict)
            .Select(s => $"{s.Mark.Name}: {s.Words}").ToList();
        var blockers = MarkReading.RoomBlockers(model).Select(Blocker).OrderBy(b => b, StringComparer.OrdinalIgnoreCase).ToList();
        var placement = blockers.Count;
        // with the model's inside read (step 3): enclosed areas that couldn't be read, each closed workset and each link
        // that could hold a room stop every room being read too, so they are listed first (design note, section 2); an
        // enclosed area with no Room doesn't (it is sent as a space whose use isn't known: UnknownAreas below)
        var others = InteriorReader.OtherRoomBlockers(model);
        blockers.AddRange(others);
        // each enclosed area with no Room (not on a level marked as having none): sent as a space whose use isn't known
        var unknown = InteriorReader.AreaBlockers(model);
        // what the reader sends, read once (with the model's inside read): the list says the rooms are read only when
        // the reader sends them (review round 2: with no Room drawn at all it said so beside "No rooms are drawn")
        var read = model.Interior is null ? null : InteriorReader.Read(model);
        var unknownAreas = InteriorReader.UnknownAreas(model);
        var summary = Summary(rows, placement, others.Count, unknownAreas.Count,
                              roomsSent: read?.Interior["rooms"] is not null,
                              placeless: unknownAreas.Count(a => a.PointInside is null));
        // the floors outside the house (SiteSlabs): what each is decides lot coverage and the yards
        if (slabs.Count > 0)
        {
            var unset = rows.Count(r => r.Kind == MarkedKind.SiteSlab && r.NeedsMarking);
            summary.Add(unset == 0
                ? $"{Marks.SiteSlab.Name}: all {slabs.Count} floors outside the house marked."
                // review round 3: an unknown word ("Garage") does say something, just not one of Gordium's words
                : $"{Marks.SiteSlab.Name}: {unset} of {slabs.Count} floors outside the house aren't marked with one of " +
                  "Gordium's words: one on the lot keeps lot coverage and the yards needing review until it says (" +
                  string.Join(", ", SlabKinds.Words) + "); one off the lot changes nothing.");
        }
        // the elements marked with Site object is (only those: which elements stand apart from the house, and so keep
        // the yards waiting, is the check's own decision, its rows naming each)
        var siteObjects = rows.Where(r => r.Kind == MarkedKind.SiteObject).ToList();
        if (siteObjects.Count > 0)
        {
            var odd = siteObjects.Count(r => r.NeedsMarking);
            summary.Add($"{Marks.SiteObject.Name}: set on {siteObjects.Count} element{(siteObjects.Count == 1 ? "" : "s")}" +
                        (odd == 0 ? "." : $", {odd} with a word that isn't one of Gordium's (" + SiteObjectKinds.Listed +
                                         "): read as not marked, so standing apart from the house it keeps the yards needing review."));
        }
        var inHouse = SiteSlabs.MarkedInHouse(model);
        if (inHouse.Count > 0)
            summary.Add($"{Marks.SiteSlab.Name} is set on {(inHouse.Count == 1 ? "1 floor" : $"{inHouse.Count} floors")} under " +
                        "the house's walls or roof (" + string.Join(", ", inHouse.Select(SlabLabel).Order(StringComparer.OrdinalIgnoreCase)) +
                        "): read as part of the building, the mark not read.");
        // step 4: the project-wide tick, always shown; and, with the model's inside read, what could hide a stair
        var stairBlockers = StairReader.Blockers(model);
        summary.Add(MarkReading.AllStairs(model) switch
        {
            true => $"{Marks.AllStairs.Name}: Yes (on Project Information).",
            var tick => $"{Marks.AllStairs.Name}: {(tick is false ? "No" : "not set")} on Project Information, so no stair is " +
                        "read for egress until it says Yes.",
        });
        summary.Add(MarkReading.AllGuards(model) switch
        {
            true => $"{Marks.AllGuards.Name}: Yes (on Project Information).",
            var tick => $"{Marks.AllGuards.Name}: {(tick is false ? "No" : "not set")} on Project Information, so no guard " +
                        "or handrail is read for egress until it says Yes.",
        });
        if (stairBlockers.Count > 0)
            summary.Add((stairBlockers.Count == 1 ? "What is listed above" : $"The {stairBlockers.Count} lines listed above") +
                        " (elements, worksets or links) could hide a stair, so no stair (and no guard) is read for egress until each is resolved.");
        // step 6: what the house has none of, read exactly as the reader reads it (the guards' tick needs the stairs read)
        // (the add-in builds the list from the model with its inside read, RevitInterior.Model; without it, a tick can't
        // be checked against the model, and the list says so instead of calling it held back)
        var ticks = read?.Ticks ?? HasNone.ReadAll(model);
        return new(problems, blockers, summary, rows)
        {
            StairBlockers = stairBlockers,
            LevelConflicts = InteriorReader.LevelConflicts(model),
            NotAStairConflicts = StairReader.NotAStairConflicts(model),
            NotAStair = StairReader.NotAStairLines(model),
            UnknownAreas = unknown,
            HasNoneConflicts = ticks.Where(t => t.Ticked is true && t.Conflicts.Count > 0)
                .SelectMany(t => t.WhyNot.Take(t.Conflicts.Count)).ToList(),
            HasNoneLines = ticks.Select(t => TickLine(t, read)).ToList(),
            ClearLines = ClearPrefills.Plan(model, clearWriteFailed).Select(p => p.Line).ToList(),
        };
    }

    /// <summary>One tick's line in the list; <paramref name="read"/> is what the reader sends (null: the model's inside
    /// wasn't read).</summary>
    internal static string TickLine(NoneTick t, InteriorReadResult? read)
    {
        var name = t.Kind.Mark.Name;
        if (read is null)
            return $"{name}: {(t.Ticked is true ? "Yes" : t.Ticked is false ? "No" : "not set")} on Project Information " +
                   "(not yet checked against the model: Set up checks it, reading the model's inside).";
        if (t.Sent)
            return $"{name}: Yes (on Project Information): read as a house with none.";
        if (t.Ticked is true && t.Conflicts.Count > 0)
            return $"{name}: Yes, but it disagrees with what is drawn (listed first): not read as none, and no {t.Kind.Words} " +
                   "read for egress until one or the other is changed.";
        if (t.Ticked is true)
            return $"{name}: Yes, but not read as none while {Count(t.Blockers.Count)} could hide one: " + string.Join("; ", t.Blockers) + ".";
        var proposal = t.Found is not null && t.Conflicts.Count == 0
            ? $" Gordium found {t.Found}: tick Yes if the house has none (Gordium never ticks it for you)." : "";
        return t.Ticked is false
            ? $"{name}: No (on Project Information): not stated as none, so " +
              (!t.Kind.IsList ? $"the rules for {t.Kind.Words} need review."
               : read.Interior[t.Kind.Kind] is not null ? $"the {t.Kind.Words} are read as drawn."
               : $"no {t.Kind.Words} are read for egress (" + string.Join("; ", NotRead(read, t.Kind)) + ").")   // every reason: one left off could be the one still blocking (review round 2)
            : $"{name}: not set on Project Information: not stated, never read as none." + proposal;
    }

    private static IReadOnlyList<string> NotRead(InteriorReadResult read, NoneKind kind) => kind.Kind switch
    {
        "stairs" => read.StairsNotRead,
        "doors" => read.DoorsNotRead,
        _ => read.GuardsNotRead,
    };

    private static string Count(int n) => n == 1 ? "1 thing" : $"{n} things";

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
                return new(e.UniqueId, MarkedKind.Room, RoomLabel(e),
                           [YesNo(e, Marks.SleepingRoom, SuggestSleeping(e)),
                            Word(e, Marks.Use, RoomUses.Table, SuggestUse(e), NotCrossed),
                            Blankable(e, Marks.CanBeLocked), Blankable(e, Marks.PassThrough)]);
            case MarkedKind.Window:
                return new(e.UniqueId, MarkedKind.Window, Label(e),
                           [YesNo(e, Marks.EscapeOpening, null), Operation(e, door: false)]);
            case MarkedKind.Door:
                return new(e.UniqueId, MarkedKind.Door, Label(e),
                           [YesNo(e, Marks.EscapeOpening, null), YesNo(e, Marks.ExitDoor, null), Operation(e, door: true),
                            Word(e, Marks.Exit, ExitKinds.Table, null, "not set: not an exit (exits are marked, never guessed)")]);
            default:
                return null;
        }
    }

    /// <summary>A level's row: shown when it has an enclosed area with no Room (unset is then to mark: place the Rooms,
    /// or fix the walls closing off one Revit can't locate, or say the level has none), or when its mark is set either way; never a suggestion (a suggested Yes could hide a
    /// bedroom).</summary>
    private static MarkingRow? LevelRow(MarkedElement e, List<EnclosedArea> areas)
    {
        var cell = YesNo(e, Marks.NoRoomsOnLevel, null);
        var count = areas.Count(a => a.LevelId == e.UniqueId);
        if (cell.State == MarkState.Unset && count == 0)
            return null;
        var label = (e.Name ?? e.UniqueId) + (count == 0 ? "" : count == 1 ? " (1 enclosed area with no Room)" : $" ({count} enclosed areas with no Room)");
        return new(e.UniqueId, MarkedKind.Level, label, [cell]);
    }

    /// <summary>A floor outside the house, as a row: its one mark, what it is.</summary>
    private static MarkingRow SlabRow(SiteSlab s)
    {
        var m = Marks.SiteSlab;
        var cell = s.Word is null ? new MarkCell(m, MarkState.Unset, null, null, "not set")
            : s.Kind is null ? new MarkCell(m, MarkState.NotUnderstood, s.Word, null,
                                            $"\"{s.Word}\" isn't one of Gordium's ({string.Join(", ", SlabKinds.Words)})")
            : new MarkCell(m, MarkState.Given, s.Word, null, null);
        return new(s.Floor.UniqueId, MarkedKind.SiteSlab, SlabLabel(s.Floor), [cell]);
    }

    /// <summary>Each element in the design checked with <see cref="Marks.SiteObject"/> set, as a row: what it is, or a
    /// word Gordium doesn't read (it then needs marking). Unset ones aren't listed: a project has hundreds (furniture,
    /// fittings), and the check's own rows name each one standing apart.</summary>
    private static IEnumerable<MarkingRow> SiteObjectRows(RevitModel model)
    {
        var m = Marks.SiteObject;
        var names = model.Elements.GroupBy(e => e.UniqueId).ToDictionary(g => g.Key, g => g.First().Name);
        foreach (var e in model.Elements)
        {
            if (!m.Categories.Contains(e.BuiltInCategory) || !SiteReader.Looked(e) || !SiteReader.OnLotNow(model, e)
                || Marks.Text(e.InstanceMarks.TryGetValue(m.Guid, out var v) ? v : null) is not { } word)
                continue;
            // review round 1: where the reader doesn't read the mark, the list never shows it as given
            var cell = e.Mark switch
            {
                GordiumMark.Context => new MarkCell(m, MarkState.NotReadHere, word, null,
                                                    "not read here: a Gordium context object (the neighbourhood's), read as one"),
                not GordiumMark.None => new MarkCell(m, MarkState.NotReadHere, word, null,
                                                     "not read here: one of Gordium's own markers (a floor block or a grade marker), read as one"),
                // review round 2: a shared nested family is read as part of its host (SiteReader.Fold), its own mark
                // not read, unless it is itself read as a building (then it is read on its own)
                _ when e.SuperComponent is { } host && host != e.UniqueId && !SiteReader.IsBuildingPart(e) =>
                    new MarkCell(m, MarkState.NotReadHere, word, null,
                                 $"not read here: part of {(names.TryGetValue(host, out var n) && n is { Length: > 0 } ? $"\"{n}\" ({host})" : host)}, read with it"),
                _ when SiteObjectKinds.Of(word) is not null => new MarkCell(m, MarkState.Given, word, null, null),
                _ when SlabKinds.Of(word) is not null => new MarkCell(m, MarkState.NotUnderstood, word, null,
                    $"\"{word}\" is a floor's word (Gordium: Site slab is), not read on a {e.Category}: one of {SiteObjectKinds.Listed}"),
                _ => new MarkCell(m, MarkState.NotUnderstood, word, null, $"\"{word}\" isn't one of Gordium's ({SiteObjectKinds.Listed})"),
            };
            yield return new(e.UniqueId, MarkedKind.SiteObject, SlabLabel(e), [cell]);
        }
    }

    private static string SlabLabel(RevitElement floor) =>
        $"{(floor.Category.Length > 0 ? floor.Category : "Floors")}: {floor.Name ?? "(no name)"} ({floor.UniqueId})";

    internal static string Label(MarkedElement e)
    {
        var what = string.Join(": ", new[] { e.Family, e.Name }.Where(s => !string.IsNullOrWhiteSpace(s)));
        if (what.Length == 0)
            what = e.UniqueId;
        return string.IsNullOrWhiteSpace(e.Number) ? what : $"{what} ({e.Number})";
    }

    private static string? SuggestSleeping(MarkedElement e) =>
        e.Name is { } n && SleepingName.IsMatch(n) ? $"suggested: Yes (named \"{n.Trim()}\"); set it yourself to accept" : null;

    private const string NotCrossed = "not set: an escape route never passes through this room";

    /// <summary>Room names offered as a suggestion of the room's use (escape routes), the first that matches. Only a
    /// suggestion, only on a room whose use is unset, and never sent: the use is the architect's word alone.</summary>
    private static readonly (Regex Name, string Use)[] UseNames =
    [
        (new(@"\b(corridor|hall\s*way|hall|circulation|passage)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "corridor"),
        (new(@"\b(lobby|vestibule|foyer)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "lobby"),
        (new(@"\b(kitchen|pantry|kitchenette)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "kitchen"),
        (new(@"\b(toilet|restroom|rest\s*room|wc|lavatory|bath\s*room)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "toilet"),
        (new(@"\b(closet|janitor|custodial)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "closet"),
        (new(@"\b(storage|store\s*room)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "accessory_storage"),
        (new(@"\b(work\s*room|copy)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "workroom"),
        (new(@"\b(day\s*care|child\s*care)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant), "day_care"),
    ];

    private static string? SuggestUse(MarkedElement e) =>
        UseFromName(e.Name) is { } word ? $"suggested: {word} (named \"{e.Name!.Trim()}\"); set it yourself to accept" : null;

    /// <summary>The room use word a room's name suggests (the first of <see cref="UseNames"/> that matches), or null:
    /// the one table both the marking list and the Setup checklist suggest from.</summary>
    internal static string? UseFromName(string? name) =>
        name is { } n && UseNames.FirstOrDefault(u => u.Name.IsMatch(n)) is { Name: not null } hit ? RoomUses.Table.WordFor(hit.Use) : null;

    /// <summary>Room names a Table 1004.5 function is suggested from (BCNYS occupant loads), the first that matches, each
    /// with the function and when it may be offered. Only a suggestion, only on a room whose function is unset, written
    /// only when the architect accepts it (SetupWrites.Accept). Never one for a corridor, an exit enclosure, a closet or
    /// a toilet (FunctionFromName's caller rules those out first). Each is the whole name, the room type alone with at
    /// most a number or a letter after it ("Bedroom 2", "Mechanical Rm 3"), never a word inside a longer name (review
    /// round 1: "Mechanical Engineering Lab", "The Boiler Room" bar and "Community Living Room" are other rows, with
    /// smaller factors: a larger load).</summary>
    private static readonly (Regex Name, string Function, string Rooms)[] FunctionNames =
    [
        (Whole(@"(mechanical|mech\.?|boiler|furnace)(\s*(room|rm\.?))?"), "accessory_storage_mechanical", "any"),
        (Whole(@"(storage|store\s*room|stock\s*room)(\s*(room|rm\.?))?"), "storage_stock_shipping", "any"),
        // Residential only in a building of dwelling units (DwellingUses, Group R-2 or R-3): a dormitory's or a
        // fraternity's bedroom is Dormitories (50 gross) and its living room a shared lounge (assembly, 15 net), and an
        // R-1 or R-4 one so named is often a guest or care room or a lounge (review rounds 1 and 2)
        (Whole(@"(bed\s*room|bedrm|bdrm)"), "residential", "dwelling"),
        (Whole(@"living(\s*room)?"), "residential", "dwelling"),
    ];

    /// <summary>The project uses (Gordium: Use on Project Information, the place's own words) whose building is made of
    /// dwelling units, where a bedroom or a living room is Table 1004.5's Residential: Ithaca's one- and two-family and
    /// multiple dwellings (never its dormitory or fraternity, sorority or group house, a congregate residence). A use
    /// not listed (another place's, or none) is offered no Residential.</summary>
    internal static readonly IReadOnlySet<string> DwellingUses = new HashSet<string>(StringComparer.Ordinal)
    {
        "one_family_detached", "one_family_detached_zero_lot_line", "one_family_semi_detached", "one_family_attached",
        "two_family", "multiple_family",
    };

    /// <summary>A room type as the whole name, with an optional number or single letter after it.</summary>
    private static Regex Whole(string type) =>
        new(@"^\s*" + type + @"(\s*[#.\-]?\s*(\d+[A-Za-z]?|[A-Za-z]))?\s*$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>Rooms a function is never suggested for, by name: a corridor, a closet, a toilet (and the stairs, which
    /// an exit enclosure holds).</summary>
    private static readonly Regex NoFunctionName =
        new(@"\b(corridor|hall\s*way|hall|circulation|passage|closet|janitor|custodial|toilet|restroom|rest\s*room|wc|lavatory|bath\s*room|bath|stair(s|way|well)?)\b",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>The Table 1004.5 function a room's name suggests, as the description's word, or null. <paramref name="use"/>:
    /// the room's use as marked (the description's word): an accessory storage room is Table 1004.5's accessory storage
    /// row whatever its name; a corridor, a closet or a toilet is offered none. <paramref name="groups"/>: the building's
    /// groups as stated (null when not stated or not read), <paramref name="projectUse"/> the project's use: Residential is
    /// offered only for a use of <see cref="DwellingUses"/> whose every group is R-2 or R-3; never otherwise.</summary>
    internal static string? FunctionFromName(string? name, string? use, IReadOnlyList<string>? groups, string? projectUse = null)
    {
        if (use is "corridor" or "closet" or "toilet")
            return null;
        if (use == "accessory_storage")
            return "accessory_storage_mechanical";
        if (name is not { } n || NoFunctionName.IsMatch(n))
            return null;
        foreach (var (rx, function, rooms) in FunctionNames)
        {
            if (!rx.IsMatch(n))
                continue;
            var allowed = rooms == "any" || projectUse is not null && DwellingUses.Contains(projectUse)
                && groups is { Count: > 0 } && groups.All(g => g is "R-2" or "R-3");
            return allowed ? function : null;
        }
        return null;
    }

    /// <summary>A word mark read through its table: given, not a word Gordium reads (to mark), or blank, whose meaning
    /// is said (nothing to mark: a house never needs it).</summary>
    private static MarkCell Word(MarkedElement e, MarkDefinition m, WordTable table, string? suggestion, string blank)
    {
        var word = Marks.Text(MarkReading.Value(e, m));
        return word is null ? new(m, MarkState.LeftBlank, null, suggestion, blank)
            : table.Of(word) is null ? new(m, MarkState.NotUnderstood, word, null, $"\"{word}\" isn't one of Gordium's ({table.Listed})")
            : new(m, MarkState.Given, word, null, null);
    }

    /// <summary>A room's Yes/No for escape routes: blank says the room is never crossed by a route, nothing to mark.</summary>
    private static MarkCell Blankable(MarkedElement e, MarkDefinition m) =>
        YesNo(e, m, null) is { State: MarkState.Unset } cell ? cell with { State = MarkState.LeftBlank, Words = NotCrossed } : YesNo(e, m, null);

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

    private static List<string> Summary(List<MarkingRow> rows, int placement, int others, int unknown, bool roomsSent,
                                        int placeless = 0)
    {
        var lines = new List<string>();
        var blockers = placement + others;
        if (placement > 0)
            lines.Add((placement == 1 ? "1 Room is" : $"{placement} Rooms are") + " unplaced, not enclosed or redundant, " +
                      "so no room is read for egress until each is placed or deleted.");
        if (others > 0)
            lines.Add((others == 1 ? "1 thing" : $"{others} things") + " listed above (a closed workset, a link, enclosed " +
                      "areas that couldn't be read) could hide a room, " +
                      "so no room is read for egress until each is resolved.");
        if (unknown > 0)
            // "the rooms drawn are read" only when the reader sends them (review rounds 1 and 2: beside an unplaced
            // Room, or with no Room drawn at all, the lines contradicted each other); unknown is 0 with the inside unread
            lines.Add((unknown == 1 ? "1 enclosed area has" : $"{unknown} enclosed areas have") + " no Room (listed above): " +
                      (roomsSent ? "the rooms drawn are read, but each such area may be a bedroom, so every sleeping-room rule needs review"
                                     : "once the rooms are read, each such area may be a bedroom, so it keeps every sleeping-room rule needing review") +
                      // an area Revit can't locate has no place for a Room: its walls are the fix (as AreaBlockers says)
                      (placeless == 0 ? " until a Room is placed in each"
                       : placeless == unknown ? " until the overlapping or doubled walls closing " + (unknown == 1 ? "it" : "them") + " off are fixed (Revit couldn't locate " + (unknown == 1 ? "it" : "any of them") + ")"
                       : " until a Room is placed in each Revit locates, and the overlapping or doubled walls closing off the " + placeless + " it couldn't are fixed") +
                      $", or its level is marked {Marks.NoRoomsOnLevel.Name} Yes.");
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
        // escape routes (a commercial story): said only once any of their marks is set, so a house's list stays as it was
        MarkDefinition[] routeMarks = [Marks.Use, Marks.CanBeLocked, Marks.PassThrough, Marks.Exit];
        var routeCells = rows.SelectMany(r => r.Cells).Where(c => routeMarks.Contains(c.Mark)).ToList();
        if (routeCells.Any(c => c.State != MarkState.LeftBlank))
        {
            var rooms = rows.Where(r => r.Kind == MarkedKind.Room).ToList();
            bool Crossing(MarkingRow r) => r.Cells.Where(c => c.Mark != Marks.SleepingRoom).All(c => c.State is MarkState.Given or MarkState.Yes or MarkState.No);
            var exits = routeCells.Count(c => c.Mark == Marks.Exit && c.State == MarkState.Given);
            lines.Add($"Escape routes: {rooms.Count(Crossing)} of {rooms.Count} rooms have {Marks.Use.Name}, {Marks.CanBeLocked.Name} and " +
                      $"{Marks.PassThrough.Name} all set (a room missing any is never passed through by a route); {exits} " +
                      (exits == 1 ? "door is" : "doors are") + $" marked {Marks.Exit.Name} (a door left blank is not an exit).");
        }
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
        foreach (var c in list.HasNoneConflicts.Concat(list.LevelConflicts).Concat(list.NotAStairConflicts))
            sb.Append("Conflict: ").Append(c).Append('\n');
        foreach (var p in list.SetupProblems)
            sb.Append("Can't add ").Append(p).Append('\n');
        foreach (var b in list.RoomBlockers.Concat(list.UnknownAreas).Concat(list.StairBlockers).Concat(list.NotAStair))
            sb.Append(b).Append('\n');
        foreach (var s in list.Summary.Concat(list.HasNoneLines).Concat(list.ClearLines))
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
