using Gordium.Worker;
using System.Globalization;

namespace Gordium.Revit.Reading;

// The Setup form as numbered steps (UI polish changes 1 to 8; Ben approved 2026-11-23): only the things a check needs,
// numbered, above the fold; one short help line each, the law behind ⓘ; the property line's source said as "Survey"
// or "Tax map"; the occupancy group and the sprinkler system required where the Building Code governs (Ben's call);
// every optional fact in one fold, "More facts (optional)", with no "0 of N set" counts; no amber "needed" on an empty
// field (status colours are for results). Revit-free: what the form shows is decided here and tested; the Revit layer
// only draws it. Nothing here writes, and nothing is ever written that the architect didn't choose.

/// <summary>One numbered step of the Setup form: a project fact (<see cref="Field"/>) or a fact inside the building
/// (<see cref="Line"/>), under its section, and whether it is set (in the model, or chosen in the form and still to
/// save: the step's circle turns ✓ either way, and the footer says what Save writes).</summary>
/// <param name="Key">The mark's name or the checklist line's key (what <see cref="SetupScreen.Needed"/> lists).</param>
/// <param name="Title">"Zoning district", "Escape openings".</param>
/// <param name="Section">The heading it sits under (<see cref="SetupSteps.Lot"/>, <see cref="SetupSteps.Building"/>,
/// <see cref="SetupSteps.InModel"/>).</param>
/// <param name="Field">The project fact, or null for a line.</param>
/// <param name="Line">The checklist line, or null for a field.</param>
/// <param name="Done">Set (or chosen, valid, still to save).</param>
public sealed record SetupTask(string Key, string Title, string Section, SetupField? Field, ChecklistLine? Line, bool Done);

/// <summary>The steps, the "More facts" fold and the words of each, from a <see cref="SetupScreen"/>.</summary>
public static class SetupSteps
{
    public const string Lot = "THE LOT";
    public const string Building = "THE BUILDING";
    public const string InModel = "IN THE MODEL";

    /// <summary>The fold that holds every optional fact.</summary>
    public const string MoreTitle = "More facts (optional)";

    /// <summary>The project facts the Building Code's egress rules turn on: required where it governs (Ben,
    /// 2026-11-23: occupancy group and sprinkler system are required when the Building Code governs).</summary>
    public static IReadOnlyList<MarkDefinition> BuildingCodeFacts { get; } = [Marks.OccupancyGroups, Marks.SprinklerSystem];

    /// <summary>Whether the 2025 Building Code of New York State governs the building as far as the form can tell
    /// before a check: the use is one the Building Code covers whatever else is stated (the worker's
    /// <c>building_code_uses</c>, code_scope.by_use), the architect applies the Building Code (Gordium: Follows
    /// building code, R101.2's exception), or the last check of this project said so. Never a guess the other way:
    /// false only means the form doesn't ask for the two facts first (the results still ask for them).</summary>
    public static bool BuildingCodeGoverns(string? use, bool? followsBuildingCode, PlaceOptions? options, string? lastCheckCode) =>
        use is not null && options is not null && options.BuildingCodeUses.Contains(use, StringComparer.Ordinal)
        || followsBuildingCode == true
        || lastCheckCode == WhichCodeWords.BuildingCode;

    /// <summary>A step's title: the architect's name for the fact.</summary>
    public static string Title(MarkDefinition m, string fallback) =>
        m == Marks.Zone ? "Zoning district"
        : m == Marks.Use ? "Use"
        : m == Marks.LotSurveyed ? "Property line drawn from"
        : m == Marks.StreetEdge ? "Street edge"
        : m == Marks.OccupancyGroups ? "Occupancy group"
        : m == Marks.SprinklerSystem ? "Sprinkler system"
        : fallback;

    /// <summary>A checklist line's step title ("Escape openings").</summary>
    public static string Title(ChecklistLine l) => l.Key switch
    {
        "escape_opening" => "Escape openings",
        "exit_door" => "Exit doors",
        "sleeping_room" => "Sleeping rooms",
        _ => l.Title,
    };

    /// <summary>The one help line under a step's field (≤ 1 line at 340 px; the law's whole words behind ⓘ), or null.
    /// The property line's says what the choice means once made.</summary>
    public static string? Help(SetupField f, string? shown)
    {
        ArgumentNullException.ThrowIfNull(f);
        if (f.Mark == Marks.Zone)
            return "As the City's zoning map shows it.";
        if (f.Mark == Marks.Use)
            return "As the zoning chart names it.";
        if (f.Mark == Marks.LotSurveyed)
            return shown switch
            {
                "No" => "Tax map lines are ±2 ft, so lot area and coverage will need review.",
                "Yes" => "Lot area and coverage are measured from the surveyed line.",
                _ => "A survey, or traced from the tax map?",
            };
        if (f.Mark == Marks.StreetEdge)
            return "Click the lot edge along the street in a plan.";
        if (f.Mark == Marks.OccupancyGroups)
            return "As the Building Code's Chapter 3 classifies the building.";
        if (f.Mark == Marks.SprinklerSystem)
            return "The system the whole building is equipped with.";
        return null;
    }

    /// <summary>The choices a step's field shows: the property line's as "Survey" and "Tax map" (Yes and No on the
    /// mark: surveyed or traced from the tax map), every other as the field has them.</summary>
    public static IReadOnlyList<FieldChoice> Choices(SetupField f)
    {
        ArgumentNullException.ThrowIfNull(f);
        return f.Mark == Marks.LotSurveyed ? [new("Yes", "Survey"), new("No", "Tax map")] : f.Choices;
    }

    /// <summary>The numbered steps: the required project facts (the lot's, then the building's where the Building
    /// Code governs), then the needed facts inside the building still to mark. A line with nothing of its kind drawn
    /// is no step (nothing to set: <see cref="NothingDrawn"/>), nor is one already set in the model (said once:
    /// <see cref="AlreadySet"/>); a project fact is always a step (its circle ✓ once set).</summary>
    public static IReadOnlyList<SetupTask> Of(SetupScreen screen, SetupDraft? draft)
    {
        ArgumentNullException.ThrowIfNull(screen);
        var steps = new List<SetupTask>();
        foreach (var f in screen.Fields.Where(f => f.Required))
            steps.Add(new(f.Mark.Name, Title(f.Mark, f.Label), BuildingCodeFacts.Contains(f.Mark) ? Building : Lot, f, null, Done(f, draft)));
        foreach (var l in screen.Lines.Where(l => l.Needed && !NothingDrawn(l) && !l.Done))
            steps.Add(new(l.Key, Title(l), InModel, null, l, l.Done));
        return steps;
    }

    /// <summary>The needed facts inside the building already set in the model (every one of their elements marked).</summary>
    public static IReadOnlyList<ChecklistLine> AlreadySet(SetupScreen screen)
    {
        ArgumentNullException.ThrowIfNull(screen);
        return screen.Lines.Where(l => l.Needed && !NothingDrawn(l) && l.Done).ToList();
    }

    /// <summary>A line with nothing of its kind drawn: nothing to set (said once, never a step or "done").</summary>
    public static bool NothingDrawn(ChecklistLine l)
    {
        ArgumentNullException.ThrowIfNull(l);
        return l.Total == 0 && l.DoneWhen is null;
    }

    /// <summary>A field is set: it holds a usable value the draft doesn't take away, or the draft chooses a value Save
    /// would write (the same rule as <see cref="SetupDraft.Writes"/>: a choice it would refuse is not set).</summary>
    public static bool Done(SetupField f, SetupDraft? draft)
    {
        ArgumentNullException.ThrowIfNull(f);
        if (draft?.Chosen(f.Mark) is not { } raw || raw.Trim().Length == 0)
            return f.IsSet;
        var (writes, problems) = draft.Writes([f]);
        return problems.Count == 0 && (writes.Count == 1 || f.IsSet);
    }

    /// <summary>"Set 6 things to check this project", or, all set, that the check has what it needs.</summary>
    public static string Headline(IReadOnlyList<SetupTask> steps)
    {
        ArgumentNullException.ThrowIfNull(steps);
        return steps.All(s => s.Done) ? "Everything the check needs is set" : $"Set {steps.Count} {(steps.Count == 1 ? "thing" : "things")} to check this project";
    }

    /// <summary>"4 of 6 set".</summary>
    public static string Progress(IReadOnlyList<SetupTask> steps)
    {
        ArgumentNullException.ThrowIfNull(steps);
        return $"{steps.Count(s => s.Done)} of {steps.Count} set";
    }

    /// <summary>The optional project facts, under plain sub-heads (The lot · Dwellings · Building code · What is drawn
    /// · What the building has none of · Other facts), in the form's order.</summary>
    public static IReadOnlyList<SetupField> MoreFields(SetupScreen screen)
    {
        ArgumentNullException.ThrowIfNull(screen);
        return screen.Fields.Where(f => !f.Required).ToList();
    }

    /// <summary>The facts inside the building the check doesn't need first (operation, clear opening, the escape
    /// routes' room facts), that have something drawn.</summary>
    public static IReadOnlyList<ChecklistLine> MoreLines(SetupScreen screen)
    {
        ArgumentNullException.ThrowIfNull(screen);
        return screen.Lines.Where(l => !l.Needed && !NothingDrawn(l)).ToList();
    }

    /// <summary>The fold's one line: "Corner lot, ADU, dwelling units and 14 more. Gordium asks for one when a result
    /// needs it." (the first three optional facts by name, the rest counted; never a "0 of N set").</summary>
    public static string MoreSummary(SetupScreen screen)
    {
        ArgumentNullException.ThrowIfNull(screen);
        var names = MoreFields(screen).Select(f => Short(f)).Concat(MoreLines(screen).Select(l => l.Title.ToLowerInvariant())).ToList();
        if (names.Count == 0)
            return "Nothing else to set.";
        var shown = names.Take(3).ToList();
        var rest = names.Count - shown.Count;
        var list = rest > 0 ? string.Join(", ", shown) + $" and {rest} more" : PaneWords.And(shown);
        return PaneWords.Capital(list) + ". Gordium asks for one when a result needs it.";
    }

    /// <summary>A fact's name as a list says it: its label, first letter small unless it is a short word in capitals
    /// ("ADU").</summary>
    private static string Short(SetupField f)
    {
        var label = Question(f) ?? f.Label;
        label = label.TrimEnd('?');
        return label.Length > 1 && char.IsUpper(label[1]) ? label : char.ToLowerInvariant(label[0]) + label[1..];
    }

    /// <summary>An optional fact asked as a question in the fold ("Corner lot (on two streets)?"), or null to show its
    /// label.</summary>
    public static string? Question(SetupField f)
    {
        ArgumentNullException.ThrowIfNull(f);
        return f.Mark == Marks.CornerLot ? "Corner lot (on two streets)?"
            : f.Mark == Marks.AccessoryDwellingUnit ? "ADU on the lot?"
            : f.Mark == Marks.HomeOccupation ? "Home business planned?"
            : f.Mark == Marks.FollowsBuildingCode ? "Designed to the Building Code anyway?"
            : null;
    }

    /// <summary>The fold's sub-head for an optional fact's group ("The lot", "Dwellings", "Building code").</summary>
    public static string SubHead(string group) => group;

    /// <summary>What a line's count says on its step: "0 of 10 doors and windows marked Yes or No."</summary>
    public static string LineCount(ChecklistLine l)
    {
        ArgumentNullException.ThrowIfNull(l);
        if (l.CountWords is { } own)
            return own + ".";
        return l.Key switch
        {
            "escape_opening" => $"{l.Set} of {l.Total} doors and windows marked Yes or No.",
            "exit_door" => $"{l.Set} of {l.Total} doors marked.",
            "sleeping_room" => $"{l.Set} of {l.Total} rooms marked Yes or No.",
            _ => $"{l.Set} of {l.Total} {l.Noun} set.",
        };
    }

    /// <summary>The one line a line's suggestions get on its step (what they are; each one's basis behind "Why?").</summary>
    public static string? SuggestsLine(ChecklistLine l)
    {
        ArgumentNullException.ThrowIfNull(l);
        if (l.Suggestions.Count == 0)
            return null;
        return l.Key switch
        {
            "exit_door" => "Gordium suggests the doors to the outside.",
            "escape_opening" => "Gordium suggests each sleeping room's largest operable window.",
            "sleeping_room" => "Gordium suggests the rooms named as bedrooms.",
            _ => $"Gordium suggests {l.Suggestions.Count} from their names.",
        };
    }

    /// <summary>The street edge's state on its step: "Not picked", the edge in words ("South edge, 100'-0\""),
    /// "Picked — click Save" (chosen in the form, its words not known), or "The lot changed — pick again".</summary>
    public static string StreetState(SetupField f, SetupDraft? draft, string? edgeWords)
    {
        ArgumentNullException.ThrowIfNull(f);
        var chosen = draft?.Chosen(f.Mark);
        if (chosen is not null && chosen != f.Current)
            return draft!.PickedWords is { } picked ? PaneWords.Capital(picked) : "Picked — click Save";
        if (f.Current is null)
            return "Not picked";
        if (f.Problem is not null)
            return "The lot changed — pick again";
        return edgeWords is { } w ? PaneWords.Capital(w) : "Picked";
    }
}

/// <summary>Which code word the worker's <c>which_code.code</c> carries for each book (code_scope.CODES).</summary>
public static class WhichCodeWords
{
    public const string BuildingCode = "building_code";
    public const string ResidentialCode = "residential_code";
}

/// <summary>A suggested occupancy group from the building's use (Ben, 2026-11-23: offered only as a suggestion, with
/// its basis, and chosen only by the architect's Accept; written with the other facts on Save). Only where the
/// Building Code's own list names the use unambiguously; anything else, no suggestion (Gordium never guesses a
/// group: R3 of the design's rejected list).</summary>
/// <param name="Group">The group suggested ("R-2").</param>
/// <param name="Basis">Why, with the code's own words.</param>
public sealed record GroupSuggestion(string Group, string Basis)
{
    /// <summary>The suggestion for a use, or null. Multiple-family dwellings (three or more units, Ithaca §325-3B) are
    /// BCNYS 310.3's "Apartment houses": "Residential Group R-2 occupancies containing sleeping units or more than
    /// two dwelling units where the occupants are primarily permanent in nature" (2025 BCNYS, PDF p.80). A use the
    /// book lists under two groups (dormitories, R-2 and R-3) gets none.</summary>
    public static GroupSuggestion? For(string? use) => use switch
    {
        "multiple_family" => new("R-2",
            "BCNYS 310.3: “Residential Group R-2 occupancies containing sleeping units or more than two dwelling units " +
            "where the occupants are primarily permanent in nature, including: Apartment houses”. If its occupants are " +
            "transient, it is R-1 instead."),
        _ => null,
    };

    /// <summary>The words the form shows: "Gordium suggests R-2 for a multiple-family building."</summary>
    public string Words => $"Gordium suggests {Group} from the use.";
}

/// <summary>A street edge in the architect's words: the side of the lot it is on, by the compass, and its length
/// in feet and inches ("the south edge, 100'-0\""), never coordinates (UI polish change 11; the coordinates go only to
/// the log and Copy details).</summary>
public static class EdgeWords
{
    private static readonly string[] Sides = ["east", "north-east", "north", "north-west", "west", "south-west", "south", "south-east"];

    /// <summary>The compass side of an edge whose outward normal (away from the lot, in shared coordinates: +Y is
    /// north) points at <paramref name="nx"/>, <paramref name="ny"/>; null for no direction.</summary>
    public static string? Side(double nx, double ny)
    {
        if (!double.IsFinite(nx) || !double.IsFinite(ny) || Math.Abs(nx) < 1e-12 && Math.Abs(ny) < 1e-12)
            return null;
        var deg = Math.Atan2(ny, nx) * 180 / Math.PI;
        var i = (int)Math.Round((deg + 360) % 360 / 45.0) % 8;
        return Sides[i];
    }

    /// <summary>A length in feet as an architect writes it: 100'-0", 47'-1 1/2" (to the nearest half inch).</summary>
    public static string FeetInches(double feet)
    {
        var halves = (long)Math.Round(feet * 24, MidpointRounding.AwayFromZero);
        var ft = halves / 24;
        var rest = halves % 24;
        var inches = rest / 2;
        var half = rest % 2 == 1 ? " 1/2" : "";
        return string.Create(CultureInfo.InvariantCulture, $"{ft}'-{inches}{half}\"");
    }

    /// <summary>An edge in words, from <paramref name="a"/> to <paramref name="b"/> (shared plan coordinates), whose
    /// middle is <paramref name="mid"/>, on a lot whose outline is <paramref name="lot"/> (any order, any closed ring;
    /// its area's centre decides which way is out). A curved edge by its length along the curve
    /// (<paramref name="length"/>). Without a lot, or with no outward side, its length alone.</summary>
    public static EdgeDescription Describe((double X, double Y) a, (double X, double Y) b, (double X, double Y) mid, double length,
                                           IReadOnlyList<(double X, double Y)>? lot) =>
        new(lot is { Count: >= 3 } ? OutwardSide(a, b, mid, lot) : null, FeetInches(length));

    /// <summary>A kept or picked edge (ends <paramref name="a"/>, <paramref name="b"/> in Revit's internal
    /// coordinates) in words, on the property line one of whose curves it is: its compass side by the lot's outline
    /// (the property line's curves joined into a loop, LotReader.Loop) in the shared coordinates
    /// (<paramref name="toShared"/>: +Y is north), its length along the curve. Null when no property line has a
    /// curve with these ends (the words are then not said, never guessed).</summary>
    public static EdgeDescription? Of(Xyz a, Xyz b, IReadOnlyList<LotLineElement> lines, Transform3 toShared, double tolerance)
    {
        ArgumentNullException.ThrowIfNull(lines);
        ArgumentNullException.ThrowIfNull(toShared);
        static double Plan(Xyz p, Xyz q) => Math.Sqrt((p.X - q.X) * (p.X - q.X) + (p.Y - q.Y) * (p.Y - q.Y));
        foreach (var line in lines.Where(l => l.IsPropertyLine && l.Unbound == 0))
        {
            var curve = line.Curves.FirstOrDefault(c =>
                Plan(c.Start, a) <= StreetEdges.Tolerance && Plan(c.End, b) <= StreetEdges.Tolerance
                || Plan(c.Start, b) <= StreetEdges.Tolerance && Plan(c.End, a) <= StreetEdges.Tolerance);
            if (curve is null)
                continue;
            var loop = LotReader.Loop(line.Curves.ToList(), tolerance);
            var ring = loop?.Select(x => toShared.Apply(x.Reversed ? x.Curve.End : x.Curve.Start)).Select(p => (p.X, p.Y)).ToList();
            var mid = curve.IsLine || curve.PointAt is null ? 0.5 * (curve.Start + curve.End) : curve.PointAt(0.5);
            Xyz sa = toShared.Apply(curve.Start), sb = toShared.Apply(curve.End), sm = toShared.Apply(mid);
            var length = curve.IsLine ? Plan(curve.Start, curve.End) : curve.Length;
            return Describe((sa.X, sa.Y), (sb.X, sb.Y), (sm.X, sm.Y), length, ring);
        }
        return null;
    }

    /// <summary>The edges kept in the Street edge mark's text, in words ("the south edge, 100'-0\"" and ...), or null
    /// when any can't be said (not text Gordium wrote, or no longer a lot edge).</summary>
    public static string? OfMark(string? text, IReadOnlyList<LotLineElement> lines, Transform3 toShared, double tolerance)
    {
        if (text is null || StreetEdges.Parse(text) is not { } kept)
            return null;
        var said = kept.Select(e => Of(e.A, e.B, lines, toShared, tolerance)?.Words).ToList();
        return said.Any(w => w is null) ? null : PaneWords.And(said!);
    }

    /// <summary>The side the edge faces: its normal pointing away from the lot's centre.</summary>
    private static string? OutwardSide((double X, double Y) a, (double X, double Y) b, (double X, double Y) mid,
                                       IReadOnlyList<(double X, double Y)> lot)
    {
        var (cx, cy) = Centroid(lot);
        double dx = b.X - a.X, dy = b.Y - a.Y;
        double nx = dy, ny = -dx;                          // one of the two normals
        if (nx * (mid.X - cx) + ny * (mid.Y - cy) < 0)     // pointing into the lot: the other one
            (nx, ny) = (-nx, -ny);
        return Side(nx, ny);
    }

    /// <summary>A ring's area centre (shoelace), or the mean of its points for a ring of no area.</summary>
    internal static (double X, double Y) Centroid(IReadOnlyList<(double X, double Y)> ring)
    {
        double area = 0, cx = 0, cy = 0;
        for (var i = 0; i < ring.Count; i++)
        {
            var (x0, y0) = ring[i];
            var (x1, y1) = ring[(i + 1) % ring.Count];
            var cross = x0 * y1 - x1 * y0;
            area += cross;
            cx += (x0 + x1) * cross;
            cy += (y0 + y1) * cross;
        }
        if (Math.Abs(area) < 1e-9)
            return (ring.Average(p => p.X), ring.Average(p => p.Y));
        return (cx / (3 * area), cy / (3 * area));
    }
}

/// <summary>A street edge in words: the compass side it is on (null when not known) and its length ("100'-0\"").</summary>
public sealed record EdgeDescription(string? Side, string Length)
{
    /// <summary>"the south edge, 100'-0\"" (or "the 100'-0\" edge" with no side known).</summary>
    public string Words => Side is null ? $"the {Length} edge" : $"the {Side} edge, {Length}";

    /// <summary>The confirmation's line: "Gordium read your click as the south edge of the lot, 100'-0\" long."</summary>
    public string Sentence => Side is null
        ? $"Gordium read your click as the lot edge {Length} long."
        : $"Gordium read your click as the {Side} edge of the lot, {Length} long.";
}

/// <summary>What the architect chose in the street pick's confirmation (UI polish change 10: the dialog ends the pick,
/// replacing the silent wait for Esc after Yes, CheckProject.PickEdges).</summary>
public enum PickAnswer
{
    /// <summary>"Use this edge": keep it, and the pick ends.</summary>
    Use,

    /// <summary>"Use it, and pick another street edge": keep it, and ask for one more (a corner lot).</summary>
    UseAndAnother,

    /// <summary>"Pick a different edge": forget this click and ask again.</summary>
    Different,

    /// <summary>The dialog closed (Esc, ×): this click forgotten, and the pick ends with what was kept before.</summary>
    Close,
}

/// <summary>The street pick as a loop Revit drives (Revit-free, so it is tested): each confirmed click kept once,
/// the pick ending exactly when the architect says so (Use, or closing the dialog), or Esc in the plan.</summary>
public sealed class PickSession
{
    private readonly List<PickedEdge> _kept = [];

    /// <summary>The edges kept, in the order confirmed (never one twice).</summary>
    public IReadOnlyList<PickedEdge> Kept => _kept;

    /// <summary>Whether to ask for another click.</summary>
    public bool Asking { get; private set; } = true;

    /// <summary>The status bar's words for the next click: the first edge, or another.</summary>
    public string Prompt => _kept.Count == 0 ? "Gordium: " + StreetEdges.PickPrompt : "Gordium: click another lot edge along the street (Esc when done)";

    /// <summary>The architect's answer to a confirmed edge.</summary>
    public void Answer(PickedEdge edge, PickAnswer answer)
    {
        ArgumentNullException.ThrowIfNull(edge);
        if (!Asking)
            throw new InvalidOperationException("the pick has ended");
        if (answer is PickAnswer.Use or PickAnswer.UseAndAnother && !_kept.Contains(edge))
            _kept.Add(edge);
        Asking = answer is PickAnswer.UseAndAnother or PickAnswer.Different;
    }

    /// <summary>Esc in the plan: the pick ends with what was kept.</summary>
    public void Escape() => Asking = false;

    /// <summary>The confirmation's words for an edge: its title, its one line, and the three answers (command links).</summary>
    public static (string Instruction, string Content, string Use, string UseAndAnother, string Different) Confirm(EdgeDescription edge)
    {
        ArgumentNullException.ThrowIfNull(edge);
        return ("Use this edge as the street line?", edge.Sentence,
                "Use this edge", "Use it, and pick another street edge", "Pick a different edge");
    }
}
