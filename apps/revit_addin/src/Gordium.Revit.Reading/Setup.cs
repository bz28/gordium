using System.Globalization;
using System.Text.RegularExpressions;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

// The Setup form (docs/decisions/2026-11-22_setup_form.md; design pass pieces 7 and 9 merged): when Check project finds
// facts the check needs missing, the panel shows one form where the architect states them, instead of "Nothing was
// checked: fill these in first" and the Mark facts dialog. Every decision is here, without Revit: which facts the form
// lists (whatever Marks.All binds to Project Information: data, so a mark added there appears with no change here),
// each field's kind and its allowed values (the rulebooks' districts, Gordium's use words), the interior facts as a
// checklist with counts, the suggestions and what each is based on, which facts are needed before the check runs by
// itself, and the words by building type. The Revit layer only reads the marks, shows this, and writes what the
// architect chose (one transaction per Save or accept). Nothing here writes, and nothing is ever written that the
// architect didn't choose: a suggestion is data until the architect's click accepts it, a blank stays blank.

/// <summary>How a project fact is entered in the form.</summary>
public enum FieldKind
{
    /// <summary>One of a known list (a dropdown): the zone, the use, the ground's markers.</summary>
    Choice,

    /// <summary>Yes or No (two toggles; neither pressed is not stated).</summary>
    YesNo,

    /// <summary>A whole number (the stories).</summary>
    Number,

    /// <summary>A length, as typed in the project's length units (a decimal number, 0 or more: the distance from a
    /// stream), never rounded; saved in feet, so Revit shows the same length.</summary>
    Feet,

    /// <summary>The street edge: picked on the plan by a click (the check's own street pick), never typed.</summary>
    StreetPick,

    /// <summary>Text with no known list (a mark whose words Gordium doesn't list yet).</summary>
    Text,
}

/// <summary>One choice of a <see cref="FieldKind.Choice"/> field: the word written to the mark, and its label.</summary>
public sealed record FieldChoice(string Value, string Label);

/// <summary>One project fact in the form: a mark on Project Information, how it is entered, its allowed values, what it
/// holds now, and the law it answers (the mark's own tooltip, in the building's words).</summary>
/// <param name="Mark">The mark it reads and writes.</param>
/// <param name="Label">Its name in the form ("Zone", "This building has no stairs").</param>
/// <param name="Kind">How it is entered.</param>
/// <param name="Group">The form's heading it sits under.</param>
/// <param name="Required">The check sends nothing without it (host_core.facts.REQUIRED; ProjectFacts.Read).</param>
/// <param name="Choices">The allowed values (Choice fields; Yes/No for YesNo), else empty.</param>
/// <param name="Current">What the mark holds now, as the form writes it (the word, "Yes" or "No", the number), or null
/// when not stated.</param>
/// <param name="Law">The law it answers: the mark's description, in the building's words.</param>
/// <param name="Problem">Why what it holds can't be used (a word not in the list, a count under 1), or null.</param>
public sealed record SetupField(MarkDefinition Mark, string Label, FieldKind Kind, string Group, bool Required,
                                IReadOnlyList<FieldChoice> Choices, string? Current, string Law, string? Problem)
{
    /// <summary>Stated, and usable.</summary>
    public bool IsSet => Current is not null && Problem is null;

    /// <summary>For a length field: the unit it is shown and typed in (the project's, as Revit's dialogs show it).</summary>
    public LengthUnit LengthUnit { get; init; } = LengthUnits.Feet;

    /// <summary>For a length field: the feet the mark holds, exactly (null when blank).</summary>
    public double? HeldFeet { get; init; }

    /// <summary>The label of what it holds now (a use's name, not its word), or null.</summary>
    public string? CurrentLabel => Current is null ? null : CurrentChoice?.Label ?? Current;

    /// <summary>The choice the check reads what the mark holds as (SetupFacts.Reads, the one matcher: a ground word in
    /// any case, a zone or use word for word), or null: what the form shows selected.</summary>
    public FieldChoice? CurrentChoice => Current is null ? null : Choices.FirstOrDefault(c => SetupFacts.Reads(Mark, Current, [c]));
}

/// <summary>A window's or door's rooms on each side and its level (FamilyInstance.FromRoom / ToRoom in the last phase,
/// its LevelId): what the escape-opening and exit-door suggestions are based on. Read by the Revit layer; never sent.</summary>
public sealed record OpeningSides(string Id, string? FromRoom, string? ToRoom, string? LevelId, string? LevelName, double? LevelElevation);

/// <summary>One suggestion: a value Gordium proposes for one mark on one element (or type), and what it is based on.
/// Only shown; written only when the architect accepts it (<see cref="SetupWrites.Accept"/>).</summary>
/// <param name="Element">The element's UniqueId, or its type's when <paramref name="OnType"/>.</param>
/// <param name="OnType">A type mark: set once on the type.</param>
/// <param name="Mark">Which mark.</param>
/// <param name="Value">The value proposed, as Revit stores it.</param>
/// <param name="Words">The value in words ("Yes", "Casement").</param>
/// <param name="Label">The element (or type) in the architect's words.</param>
/// <param name="Basis">What the suggestion is based on, in plain words.</param>
public sealed record Suggestion(string Element, bool OnType, MarkDefinition Mark, MarkValue Value, string Words,
                                string Label, string Basis)
{
    /// <summary>The write accepting it makes.</summary>
    public MarkWrite Write => new(Element, OnType, Mark, Value, Label);
}

/// <summary>One fact inside the building, as one line of the checklist: how many of its elements (or types) are set,
/// the unset ones to select, why Gordium can't read it from the model, what a blank leaves, and the suggestions.</summary>
/// <param name="Key">Its id (what "Check now anyway" remembers).</param>
/// <param name="Mark">The mark it sets.</param>
/// <param name="Title">"Escape opening".</param>
/// <param name="Noun">What is counted ("windows and doors", "window and door types").</param>
/// <param name="Set">How many are set to something Gordium reads.</param>
/// <param name="Total">How many there are.</param>
/// <param name="Unset">The elements to select for it (an unset type's every instance), by UniqueId.</param>
/// <param name="PerType">Set once on each type (Edit Type in Properties), not on each element.</param>
/// <param name="Needed">The check runs by itself only once it is done (a blank one leaves a whole kind unread).</param>
/// <param name="WhyAsked">Why Gordium can't read it from the model.</param>
/// <param name="IfBlank">What a blank one leaves.</param>
/// <param name="Suggestions">What Gordium proposes, each with its basis (only for unset ones).</param>
/// <param name="Notes">More the architect should know (the makers' clear openings Gordium holds).</param>
public sealed record ChecklistLine(string Key, MarkDefinition Mark, string Title, string Noun, int Set, int Total,
                                   IReadOnlyList<string> Unset, bool PerType, bool Needed, string WhyAsked, string IfBlank,
                                   IReadOnlyList<Suggestion> Suggestions, IReadOnlyList<string> Notes)
{
    /// <summary>Nothing left to set (nothing of the kind drawn counts as done: there is nothing to set).</summary>
    public bool Done => DoneWhen ?? Set >= Total;

    /// <summary>A line whose blank has its own meaning says when it is done itself (the exits: once one is marked).</summary>
    public bool? DoneWhen { get; init; }

    /// <summary>"Escape opening: 0 of 119 set" (or the line's own words).</summary>
    public string Count => CountWords ?? (Total == 0 ? $"{Title}: no {Noun} drawn" : $"{Title}: {Set} of {Total} {Noun} set");

    /// <summary>The line's own count words, or null.</summary>
    public string? CountWords { get; init; }
}

/// <summary>Everything the Setup form shows, made from the model's marks alone.</summary>
/// <param name="Noun">The building in words ("house", "building").</param>
/// <param name="Fields">The project facts, in the form's order.</param>
/// <param name="Lines">The checklist, needed ones first.</param>
/// <param name="FixFirst">What stops facts being read at all (Rooms not placed), each a line.</param>
/// <param name="Needed">What is still needed before the check runs by itself: each field's mark name or line's key.</param>
public sealed record SetupScreen(string Noun, IReadOnlyList<SetupField> Fields, IReadOnlyList<ChecklistLine> Lines,
                                 IReadOnlyList<string> FixFirst, IReadOnlyList<string> Needed)
{
    /// <summary>Every needed fact is set: the check runs by itself.</summary>
    public bool Ready => Needed.Count == 0;

    /// <summary>The Building Code governs as far as the form can tell (<see cref="SetupSteps.BuildingCodeGoverns"/>):
    /// the occupancy group and the sprinkler system are then required steps.</summary>
    public bool BuildingCode { get; init; }

    /// <summary>The street edge kept on Project Information in words ("the south edge, 100'-0\""), when the Revit
    /// layer could say it; null otherwise.</summary>
    public string? StreetWords { get; init; }

    /// <summary>The numbered steps (<see cref="SetupSteps.Of"/>), with the draft as it was when the screen was made.</summary>
    public IReadOnlyList<SetupTask> Steps { get; init; } = [];

    /// <summary>The form's headline: "Set 6 things to check this project".</summary>
    public string Headline => SetupSteps.Headline(Steps);

    /// <summary>Made from the model's marks, the openings' sides, the place's options (null while the worker hasn't
    /// answered: the zone and use are then typed), what the architect has chosen but not saved, the kept street edge in words (null when not known), and
    /// whether the kept edges are still edges of the lot (false: the property line changed, so a problem the form
    /// waits for, as the check would refuse it; null when not known).</summary>
    public static SetupScreen Build(RevitModel model, IReadOnlyList<OpeningSides>? sides, PlaceOptions? options,
                                    SetupDraft? draft = null, string? streetWords = null,
                                    bool? streetOnLot = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        var use = draft?.Chosen(Marks.Use) ?? Marks.Text(SetupFacts.Get(model, Marks.Use));
        var noun = SetupWords.Noun(use);
        var follows = draft?.Chosen(Marks.FollowsBuildingCode) is { } f ? f == "Yes" : Marks.YesNo(SetupFacts.Get(model, Marks.FollowsBuildingCode));
        var governs = SetupSteps.BuildingCodeGoverns(use, follows, options);
        var fields = SetupFacts.Fields(model, options, draft, noun, governs).Select(f =>
            f.Mark == Marks.StreetEdge && streetOnLot == false && f.Current is not null && f.Problem is null
                ? f with { Problem = SetupSteps.StreetOffLot } : f).ToList();
        var routes = !SetupWords.IsDwelling(use) && use is not null || SetupChecklist.AnyRouteMark(model);
        var lines = SetupChecklist.Build(model, sides ?? [], noun, routes, governs, draft?.Chosen(Marks.OccupancyGroups), use);
        var fixFirst = MarkReading.RoomBlockers(model).Select(e =>
            $"Room {ElementNames.Of("Rooms", e.Name, e.Number, null, 0)} " + (e.Placement switch
            {
                RoomPlacement.Unplaced => "isn't placed. Place it in a closed area, or delete it.",
                RoomPlacement.NotEnclosed => "isn't enclosed. Close its walls, or delete it.",
                RoomPlacement.Redundant => "is in the same area as another room. Delete one.",
                _ => "can't be read where it is placed.",
            }) + " Until then, no room is checked for egress.").ToList();
        var needed = SetupGate.Needed(model, fields, lines);
        var screen = new SetupScreen(noun, fields, lines, fixFirst, needed) { BuildingCode = governs, StreetWords = streetWords };
        return screen with { Steps = SetupSteps.Of(screen, draft) };
    }
}

/// <summary>The project facts: every mark Marks.All binds to Project Information, as a form field.</summary>
public static class SetupFacts
{
    /// <summary>Stands for Project Information's own UniqueId in a <see cref="MarkWrite"/> (the Revit layer writes it to
    /// <c>Document.ProjectInformation</c>).</summary>
    public const string ProjectInformation = "gordium:project-information";

    /// <summary>The facts the check sends nothing without (ProjectFacts.Read; host_core.facts.REQUIRED).</summary>
    public static IReadOnlyList<MarkDefinition> Required { get; } = [Marks.Zone, Marks.Use, Marks.LotSurveyed, Marks.StreetEdge];

    /// <summary>The headings, in the form's order: the needed facts (the numbered steps), then the "More facts"
    /// fold's plain sub-heads.</summary>
    public const string NeededGroup = "Needed to check";
    public const string LotGroup = "The lot";
    public const string DwellingsGroup = "Dwellings";
    public const string CodeGroup = "Building code";
    public const string DrawnGroup = "What is drawn";
    public const string NoneGroup = "What the {0} has none of";
    public const string OtherGroup = "Other facts";

    /// <summary>The dwelling's own facts (its units, an ADU, a home business, rooms let), under "Dwellings".</summary>
    private static readonly HashSet<Guid> Dwelling =
    [
        Marks.DwellingUnits.Guid, Marks.UnitsInAttachedBuilding.Guid, Marks.RoomsLetForProfit.Guid, Marks.AdusOnParcel.Guid,
        Marks.AccessoryDwellingUnit.Guid, Marks.AduDetached.Guid, Marks.HomeOccupation.Guid, Marks.OwnerOccupied.Guid,
        Marks.UnrelatedPersons.Guid, Marks.FunctionalFamilyUnit.Guid,
    ];

    /// <summary>The choices of a Text mark whose words Gordium lists (by GUID). The zone and use come from the place's
    /// options; a text mark not here is typed (and checked by the worker). A mark added to Marks.cs with its own word
    /// list adds one line here.</summary>
    private static readonly Dictionary<Guid, Func<IReadOnlyList<FieldChoice>>> Listed = new()
    {
        [Marks.GroundFrom.Guid] = () => Marks.GroundWords.Select(w => new FieldChoice(w.Word, w.Word)).ToList(),
        [Marks.OccupancyGroups.Guid] = () => OccupancyGroupWords.Words.Select(w => new FieldChoice(w, w)).ToList(),
        [Marks.SprinklerSystem.Guid] = () => SprinklerWords.Table.Words.Select(w => new FieldChoice(w, w)).ToList(),
    };

    /// <summary>What a project mark holds, or null.</summary>
    public static MarkValue? Value(RevitModel model, MarkDefinition m)
    {
        ArgumentNullException.ThrowIfNull(model);
        return Get(model, m);
    }

    internal static MarkValue? Get(RevitModel model, MarkDefinition m) =>
        model.ProjectMarks.TryGetValue(m.Guid, out var v) ? v : null;

    /// <summary>The heading a mark sits under, from what it feeds (data: a new mark finds its heading by its Feeds).</summary>
    public static string Group(MarkDefinition m, string noun)
    {
        if (Required.Contains(m))
            return NeededGroup;
        if (m == Marks.AllStairs || m == Marks.AllGuards)
            return DrawnGroup;
        if (Dwelling.Contains(m.Guid))
            return DwellingsGroup;
        if (m.Feeds.StartsWith("building.", StringComparison.Ordinal))
            return CodeGroup;
        if (m.Feeds.Contains("has_none", StringComparison.Ordinal) || m.Feeds.EndsWith(": []", StringComparison.Ordinal))
            return string.Format(CultureInfo.InvariantCulture, NoneGroup, noun);
        if (m.Feeds.StartsWith("facts.", StringComparison.Ordinal))
            return string.Format(CultureInfo.InvariantCulture, LotGroup, noun);
        return OtherGroup;
    }

    private static int Order(string group) => group switch
    {
        NeededGroup => 0,
        LotGroup => 1,
        DwellingsGroup => 2,
        CodeGroup => 3,
        DrawnGroup => 4,
        OtherGroup => 6,
        _ => 5,
    };

    /// <summary>The facts a check sent anyway leaves out (ProjectFacts.Read gave none for them): a required one not
    /// set, the street edge not picked (or not one Gordium wrote), and an optional one holding what Gordium can't read.</summary>
    public static IReadOnlyList<MarkDefinition> NotSent(RevitModel model, ProjectFactsRead read)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(read);
        var left = new List<MarkDefinition>();
        foreach (var (m, key) in new[] { (Marks.Zone, "zone"), (Marks.Use, "use"), (Marks.LotSurveyed, "lot_surveyed") })
            if (read.Facts[key] is null)
                left.Add(m);
        if (read.StreetEdges is null)
            left.Add(Marks.StreetEdge);
        if (Marks.Text(Get(model, Marks.GroundFrom)) is not null && read.Facts["grade_from"] is null)
            left.Add(Marks.GroundFrom);
        if (Marks.Count(Get(model, Marks.Stories)) is not null && read.Facts["stories"] is null)
            left.Add(Marks.Stories);
        // the dwelling's own counts (which New York code governs reads them): one set under its least isn't sent
        foreach (var (m, key) in new[] { (Marks.DwellingUnits, "dwelling_units"), (Marks.UnitsInAttachedBuilding, "attached_units_in_building"),
                     (Marks.RoomsLetForProfit, "rooms_let_for_profit"), (Marks.AdusOnParcel, "adus_on_parcel") })
            if (Marks.Count(Get(model, m)) is not null && read.Facts[key] is null)
                left.Add(m);
        // the house's own facts (UI design change 20): one holding what Gordium can't send
        left.AddRange(ProjectFacts.HouseFacts(model).Select(p => p.Mark));
        return left;
    }

    /// <summary>The least a whole-number mark takes: 1 for one whose words say "1 or more" (the stories), else 0.</summary>
    public static int Least(MarkDefinition m) => m.Description.Contains("1 or more", StringComparison.Ordinal) ? 1 : 0;

    /// <summary>Every project fact as a field; <paramref name="buildingCode"/>: the Building Code governs, so the
    /// occupancy group and the sprinkler system are required too (<see cref="SetupSteps.BuildingCodeFacts"/>).</summary>
    public static IReadOnlyList<SetupField> Fields(RevitModel model, PlaceOptions? options, SetupDraft? draft, string noun,
                                                   bool buildingCode = false)
    {
        ArgumentNullException.ThrowIfNull(model);
        var zone = draft?.Chosen(Marks.Zone) ?? Marks.Text(Get(model, Marks.Zone));
        var fields = new List<SetupField>();
        var unsendable = ProjectFacts.HouseFacts(model).ToDictionary(p => p.Mark.Guid, p => p.Problem);
        foreach (var m in Marks.All.Where(m => m.Categories.Contains(Marks.ProjectInformation)))
        {
            var v = Get(model, m);
            var required = Required.Contains(m) || buildingCode && SetupSteps.BuildingCodeFacts.Contains(m);
            var group = required ? NeededGroup : Group(m, noun);
            var label = SetupWords.Label(m, noun);
            var law = SetupWords.InBuildingWords(m.Description, noun);
            switch (m.Kind)
            {
                case MarkValueKind.YesNo:
                {
                    var yes = Marks.YesNo(v);
                    // a building fact set to neither Yes nor No: BuildingFacts asks it again, so the form says so and waits
                    var unread = yes is null && v is { HasValue: true } && m.Feeds.StartsWith("building.", StringComparison.Ordinal)
                                 ? "It holds a value that isn't Yes or No. Choose Yes or No." : null;
                    fields.Add(new(m, label, FieldKind.YesNo, group, required, [new("Yes", "Yes"), new("No", "No")],
                                   yes is null ? null : yes.Value ? "Yes" : "No", law, unread));
                    break;
                }
                case MarkValueKind.Integer:
                {
                    var n = Marks.Count(v);
                    var least = Least(m);
                    fields.Add(new(m, label, FieldKind.Number, group, required, [],
                                   n?.ToString(CultureInfo.InvariantCulture), law,
                                   n is { } k && k < least ? $"{k} isn't a count Gordium reads: {least} or more" : null));
                    break;
                }
                case MarkValueKind.Text when m == Marks.StreetEdge:
                {
                    var text = Marks.Text(v);
                    fields.Add(new(m, label, FieldKind.StreetPick, group, required, [], text, law,
                                   text is not null && StreetEdges.Parse(text) is null
                                       ? "The street edge was typed by hand. Pick it on the plan." : null));
                    break;
                }
                case MarkValueKind.Text:
                {
                    var text = Marks.Text(v);
                    var choices = Choices(m, options, zone);
                    // a building of more than one group, typed on Project Information ("R-2, B"): its groups as typed
                    // are one choice (the dropdown lists one group each)
                    if (m == Marks.OccupancyGroups && text is not null && OccupancyGroupWords.Parse(text) is not null
                        && !Reads(m, text, choices!))
                        choices = [new FieldChoice(text.Trim(), text.Trim()), .. choices!];
                    var kind = choices is { Count: > 0 } ? FieldKind.Choice : FieldKind.Text;
                    string? problem = null;
                    // set exactly when the check reads it (Reads: the zone and use exactly, as the checker matches them;
                    // the ground's words in any case, as ProjectFacts.Read does); a zone or use in another case is a
                    // problem (choose it from the list), kept as typed so a Save writes it over
                    if (text is not null && kind == FieldKind.Choice && !Reads(m, text, choices!))
                        problem = choices!.Any(c => string.Equals(c.Value, text, StringComparison.OrdinalIgnoreCase))
                                  ? $"“{text}” is typed in another case. Choose it from the list."
                                  : m == Marks.Zone ? $"Gordium has no rules for “{text}”. Choose a district."
                                  : m == Marks.Use ? $"“{text}” isn't one of the City's uses Gordium knows. Choose one."
                                  : $"“{text}” isn't one of Gordium's words. Choose one.";
                    fields.Add(new(m, label, kind, group, required, choices ?? [], text, Plain.TryGetValue(m.Guid, out var plain) ? plain : law, problem));
                    break;
                }
                case MarkValueKind.Length:
                {
                    // shown and typed in the project's length units, as Revit's own dialogs show it; feet inside
                    var unit = LengthUnits.Of(model.DisplayUnits);
                    var shown = LengthUnits.Shown(Marks.Length(v), unit);
                    var note = unit.Known ? "" : $" This project's length units ({model.DisplayUnits}) aren't ones Gordium reads: type feet here.";
                    fields.Add(new(m, SetupWords.Label(m, noun, unit.Symbol), FieldKind.Feet, group, required, [], shown, law + note, null)
                    {
                        LengthUnit = unit,
                        HeldFeet = Marks.Length(v),
                    });
                    break;
                }
                default:
                    break;
            }
            // a house fact holding what Gordium can't send (another kind of value, under its least): said, so the form
            // waits for it, never shown as blank
            if (unsendable.TryGetValue(m.Guid, out var why) && fields.Count > 0 && fields[^1].Mark == m && fields[^1].Problem is null)
                fields[^1] = fields[^1] with { Problem = why };
        }
        return fields.OrderBy(f => Order(f.Group)).ToList();      // stable: Marks.All's order within each heading
    }

    /// <summary>The marks the checker reads word for word (it chooses the rulebook by the zone and matches the use
    /// against the chart's list exactly); every other listed word is read in any case (ProjectFacts.Read's ground).</summary>
    public static IReadOnlyList<MarkDefinition> ReadExactly { get; } = [Marks.Zone, Marks.Use];

    /// <summary>Whether the check reads <paramref name="text"/> as one of <paramref name="choices"/>: the one matcher the
    /// form's "set" and its problems use, the same as the check's own reading of each mark.</summary>
    public static bool Reads(MarkDefinition m, string text, IReadOnlyList<FieldChoice> choices) =>
        choices.Any(c => string.Equals(c.Value, text.Trim(),
                                       ReadExactly.Contains(m) ? StringComparison.Ordinal : StringComparison.OrdinalIgnoreCase));

    /// <summary>The form's own help for a mark whose tooltip is written in Gordium's words (the use: its tooltip names the
    /// stored words and the room uses too). The tooltip in Revit stays as it is.</summary>
    private static readonly Dictionary<Guid, string> Plain = new()
    {
        [Marks.Use.Guid] = "What the building is used for, as the City of Ithaca's zoning chart names it. A use the district's " +
                           "chart doesn't list is still yours to state: its use row then won't comply (a special-permit use needs review), never a pass.",
    };

    /// <summary>A Text mark's allowed values, or null when Gordium lists none (typed). The zone: the districts with a
    /// rulebook; the use: every use of the city, by its name, the district's own first (permitted first, each
    /// special-permit one saying so), then the others "not listed for" the district (as host_core.facts.district_use_names
    /// keeps a use the district doesn't list): the architect can always state the true use. Both null until the worker
    /// has answered (typed meanwhile).</summary>
    public static IReadOnlyList<FieldChoice>? Choices(MarkDefinition m, PlaceOptions? options, string? zone)
    {
        if (m == Marks.Zone)
            return options?.Zones.Select(z => new FieldChoice(z, z)).ToList();
        if (m == Marks.Use)
        {
            if (options is null)
                return null;
            var names = options.Uses.ToDictionary(u => u.Id, u => u.Name, StringComparer.Ordinal);
            var district = zone is not null && options.DistrictUses.TryGetValue(zone, out var d) ? d : null;
            if (district is not { Count: > 0 })
                return options.Uses.Select(u => new FieldChoice(u.Id, u.Name)).ToList();
            var listed = district.Select(u => new FieldChoice(u.Id, u.Permitted == false && u.Note is { } note ? $"{u.Name} ({note})" : u.Name)).ToList();
            var ids = district.Select(u => u.Id).ToHashSet(StringComparer.Ordinal);
            return listed.Concat(options.Uses.Where(u => !ids.Contains(u.Id))
                .Select(u => new FieldChoice(u.Id, $"{u.Name} — not allowed in {zone}"))).ToList();
        }
        return Listed.TryGetValue(m.Guid, out var list) ? list() : null;
    }
}

/// <summary>What the architect chose in the form and hasn't saved: only what they touched, nothing else.</summary>
public sealed class SetupDraft
{
    private readonly Dictionary<Guid, string> _chosen = [];

    /// <summary>The architect chose <paramref name="value"/> for <paramref name="mark"/> ("Yes", a word, a number as typed).</summary>
    public void Choose(MarkDefinition mark, string value)
    {
        ArgumentNullException.ThrowIfNull(mark);
        ArgumentNullException.ThrowIfNull(value);
        _chosen[mark.Guid] = value;
    }

    /// <summary>The choice taken back (the field shows what the mark holds again).</summary>
    public void Forget(MarkDefinition mark) => _chosen.Remove(mark.Guid);

    public string? Chosen(MarkDefinition mark) => _chosen.TryGetValue(mark.Guid, out var v) ? v : null;

    /// <summary>The picked street edges in words ("the south edge, 100'-0\""), as the pick said them; null when none
    /// was picked in the form (or the words weren't known).</summary>
    public string? PickedWords { get; set; }

    /// <summary>The street edges the architect picked on the plan, kept in the draft as the Street edge mark's text
    /// (exactly as StreetEdges.Keep writes it): nothing is written until Save, which writes it with the other facts in
    /// the one transaction. Returns the text; none picked changes nothing.</summary>
    public string? Pick(IReadOnlyList<PickedEdge> edges)
    {
        ArgumentNullException.ThrowIfNull(edges);
        if (edges.Count == 0)
            return null;
        string? text = null;
        StreetEdges.Keep(edges, t => { text = t; return true; }, new Dictionary<string, object?>());
        Choose(Marks.StreetEdge, text!);
        return text;
    }

    public int Count => _chosen.Count;

    /// <summary>Whether <paramref name="chosen"/> is what the field's mark holds already: a length by the feet it
    /// parses to against the feet the mark holds (never the shown text, rounded to 6 places: 6.096 typed over a mark
    /// holding 19.999999999999996 ft is written, so it is 20 ft); anything else by its text.</summary>
    private static bool Holds(SetupField f, string chosen)
    {
        if (f.Kind != FieldKind.Feet)
            return chosen == f.Current;
        return f.HeldFeet is { } held && double.TryParse(chosen, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out var typed)
               && double.IsFinite(typed) && f.LengthUnit.ToFeet(typed) == held;
    }

    public void Clear()
    {
        _chosen.Clear();
        PickedWords = null;
    }

    /// <summary>Whether the draft changes <paramref name="f"/>: something is chosen, and it isn't what the mark holds
    /// already (<see cref="Holds"/>: a length by its feet, never its text), or the field holds a problem (a Save writes
    /// over it). The one rule Save's count, "not saved yet" and <see cref="Writes"/> all use, so the button never
    /// counts a fact Save won't write, or greys out over one it will (review round 4 of change 20).</summary>
    public bool Changes(SetupField f)
    {
        ArgumentNullException.ThrowIfNull(f);
        return Chosen(f.Mark) is { } raw && raw.Trim() is { Length: > 0 } chosen && !(f.Problem is null && Holds(f, chosen));
    }

    /// <summary>The writes a Save makes: each field the architect chose a value for that differs from what the mark
    /// holds, as Revit stores it; a choice that isn't an allowed value is refused with why (and not written). A field
    /// not touched is never written: a blank stays blank.</summary>
    public (IReadOnlyList<MarkWrite> Writes, IReadOnlyList<string> Problems) Writes(IReadOnlyList<SetupField> fields)
    {
        ArgumentNullException.ThrowIfNull(fields);
        var writes = new List<MarkWrite>();
        var problems = new List<string>();
        foreach (var f in fields)
        {
            if (!Changes(f))
                continue;                                   // nothing chosen, or what it holds already
            var chosen = Chosen(f.Mark)!.Trim();
            MarkValue? value = f.Kind switch
            {
                FieldKind.YesNo when chosen is "Yes" or "No" => new MarkValue(true, chosen == "Yes" ? 1 : 0),
                FieldKind.Number when int.TryParse(chosen, NumberStyles.None, CultureInfo.InvariantCulture, out var n)
                                      && n >= SetupFacts.Least(f.Mark) => new MarkValue(true, n),
                FieldKind.Choice when f.Choices.FirstOrDefault(c => c.Value == chosen) is { } c => new MarkValue(true, Text: c.Value),
                FieldKind.Feet when double.TryParse(chosen, NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out var typed)
                                    && double.IsFinite(typed) && typed >= 0 => new MarkValue(true, Number: f.LengthUnit.ToFeet(typed)),
                FieldKind.Text => new MarkValue(true, Text: chosen),
                // the street edge: only edges Gordium's pick kept (never typed text)
                FieldKind.StreetPick when StreetEdges.Parse(chosen) is not null => new MarkValue(true, Text: chosen),
                _ => null,
            };
            if (value is null)
            {
                problems.Add(f.Kind switch
                {
                    FieldKind.Number => $"{f.Label}: \"{chosen}\" isn't a whole number {SetupFacts.Least(f.Mark)} or more: not saved",
                    FieldKind.Feet => $"{f.Label}: \"{chosen}\" isn't a length in {f.LengthUnit.Words}, 0 or more (a number such as 18.5): not saved",
                    FieldKind.StreetPick => $"{f.Label}: pick it on the plan",
                    _ => $"{f.Label}: \"{chosen}\" isn't one of its choices: not saved",
                });
                continue;
            }
            writes.Add(new MarkWrite(SetupFacts.ProjectInformation, false, f.Mark, value, "Project Information"));
        }
        return (writes, problems);
    }
}

/// <summary>The writes the form makes, each one Revit transaction (one Ctrl+Z), named for Gordium: both names are not
/// the check's own (ResultRows.ChangesTheCheck), so results shown go stale after either.</summary>
public static class SetupWrites
{
    /// <summary>The Save of the project facts.</summary>
    public const string FactsTransaction = "Gordium: project facts";

    /// <summary>The architect's accept of one or more suggestions.</summary>
    public const string SuggestionsTransaction = "Gordium: suggestions accepted";

    /// <summary>The writes accepting <paramref name="accepted"/> makes: exactly those, never another of the line's.</summary>
    public static IReadOnlyList<MarkWrite> Accept(IEnumerable<Suggestion> accepted) =>
        accepted.Select(s => s.Write).DistinctBy(w => (w.Element, w.Mark.Guid)).ToList();
}

/// <summary>What Check project does with what is missing (<see cref="SetupGate.Decide"/>).</summary>
public enum SetupStep
{
    /// <summary>The Setup form, nothing sent.</summary>
    Show,

    /// <summary>Sent as Check now anyway sends: what is missing was already checked anyway for.</summary>
    SendAnyway,

    /// <summary>Nothing needed is missing: the check as before.</summary>
    Send,
}

/// <summary>Whether the form shows, and whether the check runs by itself.</summary>
public static class SetupGate
{
    /// <summary>What is still needed: each required project fact not set (or holding something unusable), any other
    /// project fact holding something unusable (the check would refuse it), and each needed checklist line not done.</summary>
    public static IReadOnlyList<string> Needed(RevitModel model, IReadOnlyList<SetupField> fields, IReadOnlyList<ChecklistLine> lines)
    {
        ArgumentNullException.ThrowIfNull(fields);
        ArgumentNullException.ThrowIfNull(lines);
        return fields.Where(f => f.Required && !f.IsSet || f.Problem is not null).Select(f => f.Mark.Name)
            .Concat(lines.Where(l => l.Needed && !l.Done).Select(l => l.Key)).ToList();
    }

    /// <summary>What Check project does: shows the form (something needed missing), sends anyway (missing only what the
    /// architect already chose Check now anyway for this session: sent as Check now anyway sends, each fact left out
    /// said, never a pick first), or sends.</summary>
    public static SetupStep Decide(IReadOnlyCollection<string> needed, IReadOnlyCollection<string>? anywayFor) =>
        needed.Count == 0 ? SetupStep.Send : ShowSetup(needed, anywayFor) ? SetupStep.Show : SetupStep.SendAnyway;

    /// <summary>Whether Check project shows the form: something needed is missing, unless the architect already chose
    /// "Check now anyway" for exactly what is missing (or more) in this session: a fact newly missing shows it again.</summary>
    public static bool ShowSetup(IReadOnlyCollection<string> needed, IReadOnlyCollection<string>? anywayFor) =>
        needed.Count > 0 && !(anywayFor is not null && needed.All(anywayFor.Contains));

    /// <summary>After a write or an edit (a Save, an accept, a value set in Properties, an undo): the check runs by
    /// itself only when the form was waiting for something needed and now nothing needed is missing; never on an edit
    /// to a form that had nothing to wait for (Mark facts opened on a project already set).</summary>
    public static bool RunsByItself(SetupScreen before, SetupScreen after)
    {
        ArgumentNullException.ThrowIfNull(before);
        ArgumentNullException.ThrowIfNull(after);
        return !before.Ready && after.Ready;
    }
}

/// <summary>The form's words by building type.</summary>
public static class SetupWords
{
    /// <summary>Whether a use word is a dwelling the residential code calls a house (one- or two-family).</summary>
    public static bool IsDwelling(string? use) =>
        use is { } u && (u.StartsWith("one_family", StringComparison.Ordinal) || u.StartsWith("two_family", StringComparison.Ordinal));

    /// <summary>"house" for a one- or two-family dwelling; "building" for any other use or none stated (never "house"
    /// on a building that isn't one).</summary>
    public static string Noun(string? use) => IsDwelling(use) ? "house" : "building";

    private static readonly Regex House = new(@"\bhouse\b", RegexOptions.CultureInvariant);
    private static readonly Regex HouseCap = new(@"\bHouse\b", RegexOptions.CultureInvariant);

    /// <summary>Words written for a house, said for this building ("This house has no stairs" → "This building has no
    /// stairs" on a day care).</summary>
    public static string InBuildingWords(string words, string noun)
    {
        ArgumentNullException.ThrowIfNull(words);
        if (noun == "house")
            return words;
        return HouseCap.Replace(House.Replace(words, noun), char.ToUpperInvariant(noun[0]) + noun[1..]);
    }

    /// <summary>A mark's name in the form: without "Gordium: ", in the building's words, with what its number is:
    /// "(count)", or a length's unit as the form takes it (<paramref name="lengthUnit"/>, the project's: "(mm)"; feet
    /// when not given).</summary>
    public static string Label(MarkDefinition m, string noun, string? lengthUnit = null)
    {
        var name = m.Name.StartsWith("Gordium: ", StringComparison.Ordinal) ? m.Name["Gordium: ".Length..] : m.Name;
        var unit = m.Kind == MarkValueKind.Length ? lengthUnit ?? LengthUnits.Feet.Symbol : Marks.Unit(m);
        return InBuildingWords(name, noun) + (unit is not null ? $" ({unit})" : "");
    }

    /// <summary>The form's notice when a check sent nothing, in plain words from what is missing (never the marks'
    /// typing instructions): the street edge kept no longer on the lot (or matching two edges), or the facts not set.</summary>
    public static string NothingSent(StreetRefusal refused, IReadOnlyList<MarkDefinition> notSet, string noun, string? lengthUnit = null)
    {
        ArgumentNullException.ThrowIfNull(notSet);
        if (refused == StreetRefusal.NoLongerAnEdge)
            return "The property line changed, so the street edge needs picking again. Nothing was checked.";
        if (refused == StreetRefusal.Ambiguous)
            return "The street edge matches two edges of the lot (an arc and its chord), so it needs picking again. Nothing was checked.";
        var names = notSet.Select(m => SetupSteps.Title(m, Label(m, noun, lengthUnit)).ToLowerInvariant()).ToList();
        if (notSet.Contains(Marks.Zone))
            return "Choose the zoning district first: it decides which rules apply. Nothing was checked" +
                   (names.Count > 1 ? $"; also not set: {string.Join(", ", names.Where(n => n != "zoning district"))}." : ".");
        return names.Count == 0 ? "Nothing was checked. Set the facts above, then Save and check."
            : $"Nothing was checked: not set: {string.Join(", ", names)}. Set them above, then Save and check.";
    }

    /// <summary>What a fact not set leaves when the architect checks anyway: each is needs review, never a pass.</summary>
    public static string SentWithout(MarkDefinition m, string noun, string? lengthUnit = null) =>
        m == Marks.Use ? "Use not set: every rule that turns on the use needs review."
        : m == Marks.LotSurveyed ? "Lot surveyed not set: the property line is read as traced from the tax map (its 2 ft accuracy), never as surveyed."
        : m == Marks.StreetEdge ? "Street edge not picked: the front yard, the yards measured from it and the lot width need review."
        : m == Marks.Zone ? "Zone not set: the district chooses the rules, so nothing can be checked without it."
        : m == Marks.Stories ? "Stories holds a count under 1 (a count is 1 or more), so it wasn't sent: height and stories need review."
        : $"{Label(m, noun, lengthUnit)}: what it holds isn't one of Gordium's words, so it wasn't sent: the rows it decides need review.";
}

/// <summary>The facts inside the building, as the checklist's lines.</summary>
public static class SetupChecklist
{
    /// <summary>Room names a sleeping room is suggested from (never from a room's area alone).</summary>
    private static readonly Regex Sleeping = new(@"\b(bed\s*room|bedrm|bdrm|bed|br\s*\d*|sleeping(\s*room)?|bunk\s*room)\b",
                                                 RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>A family or type name to the operation it says, the first that matches (windows, then doors).</summary>
    private static readonly (Regex Name, string Word)[] WindowOperations =
    [
        (Rx(@"\bcasement"), "Casement"), (Rx(@"\bdouble[\s_-]*hung"), "Double hung"), (Rx(@"\bsingle[\s_-]*hung"), "Single hung"),
        (Rx(@"\bawning"), "Awning"), (Rx(@"\bhopper"), "Hopper"), (Rx(@"\btilt[\s_-]*(and[\s_-]*)?turn"), "Tilt-turn"),
        (Rx(@"\bpivot"), "Pivot"), (Rx(@"\b(slider|sliding|glider)"), "Horizontal slider"), (Rx(@"\b(fixed|picture)\b"), "Fixed"),
    ];

    private static readonly (Regex Name, string Word)[] DoorOperations =
    [
        (Rx(@"\bpocket"), "Pocket door"), (Rx(@"\b(bi[\s_-]*fold|folding)"), "Folding door"),
        (Rx(@"\b(slid(ing|er)|glider)"), "Sliding door"),
        (Rx(@"\b(single|double)[\s_-]*(flush|panel|glass|glazed)|\b(flush|panel|hinged|swing|french)\b"), "Side-hinged door"),
    ];

    private static Regex Rx(string p) => new(p, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    /// <summary>The operation word a type's family and name say, or null.</summary>
    internal static string? OperationFromName(string? family, string? name, bool door)
    {
        var text = string.Join(" ", new[] { family, name }.Where(s => !string.IsNullOrWhiteSpace(s)));
        return (door ? DoorOperations : WindowOperations).FirstOrDefault(o => o.Name.IsMatch(text)).Word;
    }

    /// <summary>Whether any escape-route mark (a room's use, lock or pass-through, a door's exit) is set.</summary>
    internal static bool AnyRouteMark(RevitModel model) =>
        MarkReading.InDesign(model).Any(e =>
            new[] { Marks.Use, Marks.CanBeLocked, Marks.PassThrough, Marks.Exit }.Any(m =>
                MarkReading.KindOf(e) is MarkedKind.Room or MarkedKind.Door && m.Categories.Contains(e.BuiltInCategory)
                && MarkReading.Value(e, m) is { HasValue: true } v && (v.Text is null || !string.IsNullOrWhiteSpace(v.Text))));

    private static string RoomName(MarkedElement e) => ElementNames.Of("Rooms", e.Name, e.Number, null, 0);

    private static string OpeningName(MarkedElement e) =>
        ElementNames.Of(MarkReading.KindOf(e) == MarkedKind.Door ? "Doors" : "Windows", e.Name, null, e.Number, 0);

    private static string TypeName(MarkedElement e) =>
        string.Join(": ", new[] { e.Family, e.Name }.Where(s => !string.IsNullOrWhiteSpace(s))) is { Length: > 0 } l ? l : e.TypeUniqueId ?? e.UniqueId;

    private static string Feet(double? ft) => ft is { } f
        ? $"{(int)Math.Floor(f + 1e-9)}'-{Math.Round((f - Math.Floor(f + 1e-9)) * 12, 1).ToString("0.#", CultureInfo.InvariantCulture)}\""
        : "?";

    /// <summary>The checklist: needed lines first (a blank one leaves a whole kind unread), then the others; each with
    /// its counts, the unset elements, why Gordium asks, and its suggestions.</summary>
    /// <param name="model">The model's marks (RevitMarks.Model).</param>
    /// <param name="sides">Each window's and door's rooms and level.</param>
    /// <param name="noun">The building in words.</param>
    /// <param name="routes">Show the escape-route lines (a building that isn't a house, or one already marked).</param>
    /// <param name="buildingCode">The Building Code governs: show the rooms' functions line (its occupant loads).</param>
    /// <param name="groupsTyped">The occupancy groups the form holds, chosen and not saved yet (null: as saved).</param>
    /// <param name="projectUse">The project's use the form holds (null: as saved): Residential is offered only for a
    /// building of dwelling units (<see cref="MarkingList.DwellingUses"/>).</param>
    public static IReadOnlyList<ChecklistLine> Build(RevitModel model, IReadOnlyList<OpeningSides> sides, string noun, bool routes,
                                                     bool buildingCode = false, string? groupsTyped = null, string? projectUse = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(sides);
        var design = MarkReading.InDesign(model).ToList();
        var rooms = design.Where(e => MarkReading.KindOf(e) == MarkedKind.Room && e.Placement == RoomPlacement.Placed).ToList();
        var windows = design.Where(e => MarkReading.KindOf(e) == MarkedKind.Window).ToList();
        var doors = design.Where(e => MarkReading.KindOf(e) == MarkedKind.Door).ToList();
        var openings = windows.Concat(doors).ToList();
        var side = sides.GroupBy(s => s.Id, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.First(), StringComparer.Ordinal);
        var roomById = rooms.ToDictionary(r => r.UniqueId, StringComparer.Ordinal);
        bool? Yes(MarkedElement e, MarkDefinition m) => Marks.YesNo(MarkReading.Value(e, m));

        // ---- sleeping rooms: suggested Yes from the name only; never a suggested No (it could hide a bedroom)
        var sleepingSuggested = new HashSet<string>(StringComparer.Ordinal);
        var sleepSuggestions = new List<Suggestion>();
        foreach (var r in rooms.Where(r => Yes(r, Marks.SleepingRoom) is null))
            if (r.Name is { } n && Sleeping.IsMatch(n))
            {
                sleepingSuggested.Add(r.UniqueId);
                sleepSuggestions.Add(new(r.UniqueId, false, Marks.SleepingRoom, new MarkValue(true, 1), "Yes", RoomName(r),
                                         $"named \"{n.Trim()}\""));
            }
        bool SleepingRoom(string? id) => id is not null && roomById.TryGetValue(id, out var r)
                                         && (Yes(r, Marks.SleepingRoom) == true || sleepingSuggested.Contains(r.UniqueId));
        bool NotSleeping(string? id) => id is not null && roomById.TryGetValue(id, out var r) && Yes(r, Marks.SleepingRoom) == false;

        // ---- each window's operation, set or as its name says (for "operable")
        string? OperationOf(MarkedElement e) =>
            Marks.Text(MarkReading.Value(e, Marks.Operation)) ?? OperationFromName(e.Family, e.Name, MarkReading.KindOf(e) == MarkedKind.Door);

        // ---- escape openings
        var escapeSuggestions = new List<Suggestion>();
        var unsetOpenings = openings.Where(o => Yes(o, Marks.EscapeOpening) is null).ToList();
        string? RoomOf(MarkedElement o) => side.TryGetValue(o.UniqueId, out var s)
            ? (s.FromRoom is { } f && roomById.ContainsKey(f) ? f : s.ToRoom is { } t && roomById.ContainsKey(t) ? t : null) : null;
        foreach (var group in windows.GroupBy(RoomOf).Where(g => g.Key is not null && SleepingRoom(g.Key)))
        {
            var room = roomById[group.Key!];
            var only = Yes(room, Marks.SleepingRoom) is null ? $"; {RoomName(room)} is only suggested as a sleeping room" : "";
            var already = group.FirstOrDefault(w => Yes(w, Marks.EscapeOpening) == true);
            // never a window the architect marked No (it isn't their escape opening), nor a fixed one
            var operable = group.Where(w => Yes(w, Marks.EscapeOpening) != false
                                            && !string.Equals(OperationOf(w), "Fixed", StringComparison.OrdinalIgnoreCase)).ToList();
            var chosen = already ?? operable.OrderByDescending(w => (w.TypeWidth ?? 0) * (w.TypeHeight ?? 0))
                                            .ThenBy(w => w.UniqueId, StringComparer.Ordinal).FirstOrDefault();
            foreach (var w in group.Where(w => Yes(w, Marks.EscapeOpening) is null))
            {
                if (ReferenceEquals(w, chosen))
                    escapeSuggestions.Add(new(w.UniqueId, false, Marks.EscapeOpening, new MarkValue(true, 1), "Yes", OpeningName(w),
                        $"the largest operable window of {RoomName(room)}, a sleeping room, by its frame ({Feet(w.TypeWidth)} x " +
                        $"{Feet(w.TypeHeight)}){(OperationOf(w) is null ? ", its operation not set" : "")}: the law measures its " +
                        $"clear opening, which the check reads once set{only}. If another window is the intended one, pick it instead"));
                else if (chosen is not null)
                    escapeSuggestions.Add(new(w.UniqueId, false, Marks.EscapeOpening, new MarkValue(true, 0), "No", OpeningName(w),
                        $"{RoomName(room)}'s escape opening is {(already is not null ? "marked" : "suggested")} as {OpeningName(chosen)}; " +
                        "one per sleeping room is what the law asks (R310.1)"));
                else if (string.Equals(OperationOf(w), "Fixed", StringComparison.OrdinalIgnoreCase))
                    escapeSuggestions.Add(new(w.UniqueId, false, Marks.EscapeOpening, new MarkValue(true, 0), "No", OpeningName(w),
                        "a fixed window doesn't open, so it can't be an escape opening"));
            }
        }
        foreach (var o in unsetOpenings.Where(o => escapeSuggestions.All(s => s.Element != o.UniqueId)))
        {
            side.TryGetValue(o.UniqueId, out var s);
            var touching = new[] { s?.FromRoom, s?.ToRoom }.Where(id => id is not null && roomById.ContainsKey(id)).ToList();
            // No only when every room it opens to is marked not a sleeping room (a room unmarked could be one)
            if (touching.Count > 0 && touching.All(NotSleeping))
                escapeSuggestions.Add(new(o.UniqueId, false, Marks.EscapeOpening, new MarkValue(true, 0), "No", OpeningName(o),
                    $"it opens only to {string.Join(" and ", touching.Select(id => RoomName(roomById[id!])))}, marked not a sleeping room"));
        }

        // ---- exit doors: a door to the outside on the entry level (the lowest level with one)
        var exitSuggestions = new List<Suggestion>();
        bool HasRoom(string? id) => id is not null && roomById.ContainsKey(id);
        var outside = doors.Where(d => side.TryGetValue(d.UniqueId, out var s) && HasRoom(s.FromRoom) != HasRoom(s.ToRoom)).ToList();
        var entry = outside.Select(d => side[d.UniqueId]).Where(s => s.LevelElevation is not null)
                           .OrderBy(s => s.LevelElevation).FirstOrDefault();
        foreach (var d in doors.Where(d => Yes(d, Marks.ExitDoor) is null))
        {
            if (!side.TryGetValue(d.UniqueId, out var s))
                continue;
            if (outside.Contains(d) && entry is not null && s.LevelId == entry.LevelId)
                exitSuggestions.Add(new(d.UniqueId, false, Marks.ExitDoor, new MarkValue(true, 1), "Yes", OpeningName(d),
                    $"a door to the outside on {entry.LevelName ?? "the lowest level"} (one side has no Room: outside, or a space " +
                    $"with no Room such as a garage); {entry.LevelName ?? "that level"} is taken as the entry level, the lowest " +
                    "with a door to the outside. Each dwelling unit needs one exit door (R311.1): keep Yes on its main one"));
            else if (HasRoom(s.FromRoom) && HasRoom(s.ToRoom))
                exitSuggestions.Add(new(d.UniqueId, false, Marks.ExitDoor, new MarkValue(true, 0), "No", OpeningName(d),
                    $"it is between two rooms ({RoomName(roomById[s.FromRoom!])} and {RoomName(roomById[s.ToRoom!])}), not a door to the outside"));
        }

        // ---- operations, per type
        var types = openings.Where(o => o.TypeUniqueId is not null).GroupBy(o => o.TypeUniqueId!, StringComparer.Ordinal).ToList();
        var opSuggestions = new List<Suggestion>();
        var opUnset = new List<string>();
        var opSet = 0;
        foreach (var t in types)
        {
            var first = t.First();
            var door = MarkReading.KindOf(first) == MarkedKind.Door;
            var word = Marks.Text(MarkReading.Value(first, Marks.Operation));
            if (word is not null && Operations.ForOpening(word, door) is not null)
            {
                opSet++;
                continue;
            }
            opUnset.AddRange(t.Select(e => e.UniqueId));
            if (word is null && OperationFromName(first.Family, first.Name, door) is { } suggested)
                opSuggestions.Add(new(t.Key, true, Marks.Operation, new MarkValue(true, Text: suggested), suggested, TypeName(first),
                    $"its family and type are named \"{TypeName(first)}\" ({t.Count()} {(door ? "door" : "window")}{(t.Count() == 1 ? "" : "s")})"));
        }

        // ---- the makers' clear openings, per type: confirmed by the architect's stamp only
        var clearSet = types.Count(t => Marks.Text(MarkReading.Value(t.First(), Marks.ClearConfirmed)) is not null);
        var clearUnset = types.Where(t => Marks.Text(MarkReading.Value(t.First(), Marks.ClearConfirmed)) is null).SelectMany(t => t.Select(e => e.UniqueId)).ToList();
        var clearNotes = ClearPrefills.Plan(model).Select(p => p.Line).ToList();

        string Blank(MarkDefinition m) => SetupWords.InBuildingWords(m.Description, noun);
        var lines = new List<ChecklistLine>
        {
            new("sleeping_room", Marks.SleepingRoom, "Sleeping room", "rooms",
                rooms.Count(r => Yes(r, Marks.SleepingRoom) is not null), rooms.Count,
                rooms.Where(r => Yes(r, Marks.SleepingRoom) is null).Select(r => r.UniqueId).ToList(), false, true,
                "Revit doesn't record what a room is used for, and the law's test is the use (a room used or meant for sleeping), not its name.",
                Blank(Marks.SleepingRoom), sleepSuggestions, []),
            new("escape_opening", Marks.EscapeOpening, "Escape opening", "windows and doors",
                openings.Count - unsetOpenings.Count, openings.Count, unsetOpenings.Select(o => o.UniqueId).ToList(), false, true,
                "Which opening is a room's emergency escape and rescue opening is the design's intent; Revit doesn't record it.",
                Blank(Marks.EscapeOpening), escapeSuggestions, []),
            new("exit_door", Marks.ExitDoor, "Exit door", "doors",
                doors.Count(d => Yes(d, Marks.ExitDoor) is not null), doors.Count,
                doors.Where(d => Yes(d, Marks.ExitDoor) is null).Select(d => d.UniqueId).ToList(), false, true,
                $"Which door is the {noun}'s required exit is the design's intent; Revit doesn't record it.",
                Blank(Marks.ExitDoor), exitSuggestions, []),
            new("operation", Marks.Operation, "Operation", "window and door types", opSet, types.Count, opUnset, true, false,
                "Revit's families don't say how a window or door opens in a way Gordium can read, and the law measures each kind's opening its own way.",
                Blank(Marks.Operation), opSuggestions, []),
            new("clear_opening", Marks.ClearConfirmed, "Clear opening confirmed", "window and door types", clearSet, types.Count,
                clearUnset, true, false,
                "The law needs the clear opening; Revit stores the frame size. Gordium fills a maker's published clear opening as a " +
                "draft only where it holds that maker's data for the exact product; otherwise take it from the maker's tables.",
                "Not confirmed: no clear opening is sent, so the opening's size rules need review.", [], clearNotes),
        };
        if (routes)
        {
            var useSuggestions = rooms.Where(r => Marks.Text(MarkReading.Value(r, Marks.Use)) is null)
                .Select(r => (Room: r, Word: MarkingList.UseFromName(r.Name))).Where(x => x.Word is not null)
                .Select(x => new Suggestion(x.Room.UniqueId, false, Marks.Use, new MarkValue(true, Text: x.Word), x.Word!, RoomName(x.Room),
                                            $"named \"{x.Room.Name!.Trim()}\"")).ToList();
            int Given(MarkDefinition m, IEnumerable<MarkedElement> of, Func<MarkValue?, bool> ok) => of.Count(e => ok(MarkReading.Value(e, m)));
            List<string> NotGiven(MarkDefinition m, IEnumerable<MarkedElement> of, Func<MarkValue?, bool> ok) =>
                of.Where(e => !ok(MarkReading.Value(e, m))).Select(e => e.UniqueId).ToList();
            bool Use(MarkValue? v) => RoomUses.Table.Of(Marks.Text(v)) is not null;
            bool YesNoSet(MarkValue? v) => Marks.YesNo(v) is not null;
            bool ExitSet(MarkValue? v) => ExitKinds.Table.Of(Marks.Text(v)) is not null;
            const string route = "A route never passes through a room left blank, and a door left blank is not an exit (Gordium never guesses one).";
            lines.Add(new("room_use", Marks.Use, "Room use (escape routes)", "rooms", Given(Marks.Use, rooms, Use), rooms.Count,
                          NotGiven(Marks.Use, rooms, Use), false, false,
                          "What each room is (a corridor, a kitchen, a closet) decides whether an escape route may pass through it; Revit doesn't record it.",
                          route, useSuggestions, []));
            lines.Add(new("can_be_locked", Marks.CanBeLocked, "Can be locked", "rooms", Given(Marks.CanBeLocked, rooms, YesNoSet), rooms.Count,
                          NotGiven(Marks.CanBeLocked, rooms, YesNoSet), false, false,
                          "Whether a room can be locked against those passing through is hardware and operation, not drawn in Revit.", route, [], []));
            lines.Add(new("pass_through", Marks.PassThrough, "Pass through", "rooms", Given(Marks.PassThrough, rooms, YesNoSet), rooms.Count,
                          NotGiven(Marks.PassThrough, rooms, YesNoSet), false, false,
                          "Whether a room is accessory to those it serves, with a discernible path (IBC 1014.2 item 1), is the design's intent.", route, [], []));
            // only the exits are marked: every other door stays blank (not an exit), so the line counts the exits
            var exits = Given(Marks.Exit, doors, ExitSet);
            lines.Add(new("exit", Marks.Exit, "Exits", "doors", exits, doors.Count,
                          NotGiven(Marks.Exit, doors, ExitSet), false, false,
                          "Which doors are the building's exits, and which kind (IBC 1016.1's list), is the design's intent; " +
                          "mark only the exits (every other door stays blank).", route, [], [])
            {
                DoneWhen = exits > 0,
                CountWords = $"Exits: {exits} {(exits == 1 ? "door" : "doors")} marked as {(exits == 1 ? "an exit" : "exits")}",
            });
        }
        if (buildingCode)
            lines.Add(FunctionLine(model, rooms, doors, side, groupsTyped, projectUse ?? Marks.Text(SetupFacts.Get(model, Marks.Use))));
        return lines;
    }

    /// <summary>The rooms' Table 1004.5 functions (the Building Code's occupant loads), with a suggestion from each unset
    /// room's name (<see cref="MarkingList.FunctionFromName"/>), written only when accepted. Never one for a room an
    /// exit enclosure or exit passageway door opens onto (either side: the enclosure, never guessed which), a corridor,
    /// a closet or a toilet. Not needed to check: a room left blank has its occupant load at needs review. The groups
    /// are those the form holds (<c>groupsTyped</c>: chosen and not saved yet, else as saved; review round 1: a
    /// suggestion is written by Accept, apart from Save, so it is offered on what the form shows).</summary>
    private static ChecklistLine FunctionLine(RevitModel model, List<MarkedElement> rooms, List<MarkedElement> doors,
                                              Dictionary<string, OpeningSides> side, string? groupsTyped, string? projectUse)
    {
        var typed = groupsTyped ?? Marks.Text(SetupFacts.Get(model, Marks.OccupancyGroups));
        var groups = typed is null ? null : OccupancyGroupWords.Parse(typed);
        var enclosed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var d in doors)
            if (ExitKinds.Table.Of(Marks.Text(MarkReading.Value(d, Marks.Exit))) is ExitKinds.Enclosure or ExitKinds.Passageway
                && side.TryGetValue(d.UniqueId, out var s))
                foreach (var id in new[] { s.FromRoom, s.ToRoom })
                    if (id is not null)
                        enclosed.Add(id);
        bool Set(MarkedElement r) => RoomFunctions.Table.Of(Marks.Text(MarkReading.Value(r, Marks.RoomFunction))) is not null;
        var suggestions = new List<Suggestion>();
        foreach (var r in rooms.Where(r => Marks.Text(MarkReading.Value(r, Marks.RoomFunction)) is null && !enclosed.Contains(r.UniqueId)))
        {
            var use = RoomUses.Table.Of(Marks.Text(MarkReading.Value(r, Marks.Use)));
            if (MarkingList.FunctionFromName(r.Name, use, groups, projectUse) is not { } function)
                continue;
            var word = RoomFunctions.Table.WordFor(function);
            var basis = use == "accessory_storage" && function == "accessory_storage_mechanical"
                ? $"its {Marks.Use.Name} is Accessory storage"
                : $"named \"{r.Name!.Trim()}\"" + (function == "residential"
                    ? $"; a building of dwelling units ({projectUse}, Group {string.Join(", ", groups!)}), so a room inside a " +
                      "dwelling unit (a shared lounge or dining room is Assembly unconcentrated instead)" : "");
            suggestions.Add(new(r.UniqueId, false, Marks.RoomFunction, new MarkValue(true, Text: word), word, RoomName(r), basis));
        }
        // counted: every room but those left blank by design (a room whose Use is a corridor, a closet or a toilet, and
        // the exit enclosure itself), unless it has one set (review round 1: the line never read done)
        var exits = EnteredExits(doors, side);
        bool BlankByDesign(MarkedElement r) => exits.Contains(r.UniqueId)
            || RoomUses.Table.Of(Marks.Text(MarkReading.Value(r, Marks.Use))) is "corridor" or "closet" or "toilet";
        var counted = rooms.Where(r => Set(r) || !BlankByDesign(r)).ToList();
        return new("room_function", Marks.RoomFunction, "Room function (occupant loads)", "rooms", counted.Count(Set), counted.Count,
                   counted.Where(r => !Set(r)).Select(r => r.UniqueId).ToList(), false, false,
                   "What each room is used for, in Table 1004.5's words, gives its occupant load factor; Revit doesn't record it.",
                   $"A room whose {Marks.Use.Name} is Corridor, Closet or Toilet, and an exit stair enclosure, stay blank (they " +
                   "aren't counted here); any other room left blank has its occupant load, and its story's, at needs review.",
                   suggestions, []);
    }

    /// <summary>The rooms an exit stair enclosure or exit passageway door enters, as the route reader reads it
    /// (RouteReader.ExitId): of the two rooms it joins, the one whose every door between two rooms is an exit of that
    /// kind; none where both or neither are (never a guess: both stay counted). Review round 2: the occupied room on
    /// the door's other side was left uncounted.</summary>
    private static HashSet<string> EnteredExits(List<MarkedElement> doors, Dictionary<string, OpeningSides> side)
    {
        string? KindOf(MarkedElement d) => ExitKinds.Table.Of(Marks.Text(MarkReading.Value(d, Marks.Exit)));
        bool Only(string room, string kind) => doors
            .Where(d => side.TryGetValue(d.UniqueId, out var s) && (s.FromRoom == room || s.ToRoom == room))
            .All(d => side[d.UniqueId] is { FromRoom: null } or { ToRoom: null } || KindOf(d) == kind);
        var entered = new HashSet<string>(StringComparer.Ordinal);
        foreach (var d in doors)
            if (KindOf(d) is ExitKinds.Enclosure or ExitKinds.Passageway && side.TryGetValue(d.UniqueId, out var s)
                && s.FromRoom is { } a && s.ToRoom is { } b)
            {
                var kind = KindOf(d)!;
                var enters = new[] { a, b }.Where(x => Only(x, kind)).ToList();
                if (enters.Count == 1)
                    entered.Add(enters[0]);
            }
        return entered;
    }
}

/// <summary>A length unit the Setup form shows and takes a length mark in: its symbol, its words, the feet in one of it,
/// and whether it is the project's own (false: the project's units aren't ones Gordium reads, and feet are used).</summary>
public sealed record LengthUnit(string Symbol, string Words, double PerFoot, bool Known = true)
{
    /// <summary>A number typed in this unit, in feet: typed / units per foot, as Revit converts it (6.096 m is exactly
    /// 20 ft; times a feet-per-unit factor gave 19.999999999999996, which fails 20 ft).</summary>
    public double ToFeet(double typed) => typed / PerFoot;

    /// <summary>A length in feet, in this unit.</summary>
    public double FromFeet(double feet) => feet * PerFoot;
}

/// <summary>The project's length display unit (<c>RevitModel.DisplayUnits</c>, Revit's unit type id) as the Setup form
/// uses it, so a length typed there is the length Revit's own dialogs show for the same number (review round 2 of
/// change 20: feet typed in a meters project's dialog were 3.28 times too long).</summary>
public static class LengthUnits
{
    public static readonly LengthUnit Feet = new("ft", "feet", 1);

    private static readonly (string Id, LengthUnit Unit)[] Table =
    [
        ("feet", Feet), ("feetFractionalInches", Feet),
        ("inches", new("in", "inches", 12)), ("fractionalInches", new("in", "inches", 12)),
        ("millimeters", new("mm", "millimeters", 304.8)), ("centimeters", new("cm", "centimeters", 30.48)),
        ("decimeters", new("dm", "decimeters", 3.048)),
        ("meters", new("m", "meters", 0.3048)), ("metersCentimeters", new("m", "meters", 0.3048)),
    ];

    /// <summary>The unit of a Revit unit type id ("autodesk.unit.unit:millimeters-1.0.1"; "Feet", the reader's default,
    /// is feet); feet, marked not known, for any other (said beside the field, never a guessed conversion).</summary>
    public static LengthUnit Of(string? typeId)
    {
        if (string.IsNullOrWhiteSpace(typeId) || typeId == "Feet")
            return Feet;
        var colon = typeId.IndexOf(':', StringComparison.Ordinal);
        var id = (colon >= 0 ? typeId[(colon + 1)..] : typeId).Split('-')[0];
        return Table.FirstOrDefault(t => t.Id == id).Unit ?? Feet with { Known = false };
    }

    /// <summary>A length in feet as the form shows it in <paramref name="unit"/> (to 6 places, so 22.5 ft is 6858 mm,
    /// never 6858.000000000001), or null.</summary>
    public static string? Shown(double? feet, LengthUnit unit) =>
        feet is { } f ? Math.Round(unit.FromFeet(f), 6).ToString("0.######", CultureInfo.InvariantCulture) : null;
}
