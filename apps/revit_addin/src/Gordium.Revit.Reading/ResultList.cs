using System.Globalization;
using System.Text.RegularExpressions;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>The four places of the results list, worst first (docs/revit/ui_design_pass.md section 2.3): what does not
/// comply, what needs review that the architect can act on (the worker's tier 2), what is to be checked by hand or
/// isn't checked (the worker's tier 3, and zoning's not checked), then what complies or doesn't apply (folded).</summary>
public enum ListSection { Fails, Review, ByHand, Complies }

/// <summary>The filter chips over the list, matching the count bar's kinds: all, does not comply, needs review (the
/// review and check-by-hand places: everything that is neither a failure nor a pass), complies (or doesn't apply).</summary>
public enum ListFilter { All, Fails, Review, Complies }

/// <summary>One row of the check in its one place in the list.</summary>
/// <param name="Row">The row, as the text file says it (<see cref="ResultRows.Row"/>).</param>
/// <param name="Section">Its place, from its own verdict (and, for a needs review, the worker's tier).</param>
/// <param name="Status">What its glyph and colour say: <see cref="StatusLook.Of"/> of its tone, stale once the model
/// changed (never green then).</param>
/// <param name="Source">The worker's line it is in (its title), or its group's title for a group listed row by row:
/// the sub-heading it is shown under in the review, check-by-hand and complies places.</param>
/// <param name="SourceKey">That line's or group's key (rows of one source are shown together).</param>
/// <param name="SourceRows">How many rows that line or group holds.</param>
/// <param name="FromLine">Whether the source is a worker line (else a group listed row by row).</param>
/// <param name="SourcePlace">The place the worker's own tier or group puts that source in (<see cref="ResultList.PlaceOf"/>),
/// or null when its key names none: the source's own (possibly counted) title heads its rows only there, and only
/// when all its rows are there (<see cref="ResultList.RunTitle"/>); elsewhere its run is headed by a name that counts
/// nothing, so a row the add-in reads more cautiously is never shown under the line's words ("2 comply · 1 doesn't apply").</param>
public sealed record ListRow(ResultRow Row, ListSection Section, PanelStatus Status, string Source, string SourceKey,
                             int SourceRows, bool FromLine, ListSection? SourcePlace = null);

/// <summary>One entry of the list as shown: a place's heading, a sub-heading, or a row.</summary>
public abstract record ListEntry;

/// <summary>A place's heading ("NEEDS REVIEW · 12 rows"): folded or open, and whether a click can fold it (only the
/// complies place, and not while a filter or a search shows only matching rows: those are always shown).</summary>
public sealed record ListHeading(ListSection Section, string Title, int Rows, bool Folded, bool Foldable, PanelStatus Status)
    : ListEntry;

/// <summary>The worker's line (or group) a run of rows is in ("Not read from the model yet: handrails (10 rules)..."),
/// with its place's glyph.</summary>
public sealed record ListSubheading(string Key, string Title, PanelStatus Status) : ListEntry;

/// <summary>A row of the list.</summary>
public sealed record ListRowEntry(ListRow Row) : ListEntry;

/// <summary>The list's first entry: the worker's state and counts (and the stale notice), scrolling away with the rows
/// so the docked pane's height goes to the list; never selected or moved to (<see cref="ResultList.Next"/>).</summary>
public sealed record ListSummary : ListEntry;

/// <summary>A filter chip: its filter, its words and its glyph (stale once the model changed; none for All).</summary>
public sealed record ListChip(ListFilter Filter, string Words, PanelStatus? Status);

/// <summary>
/// The results list's decisions, without WPF or Revit (PR 3 of docs/revit/ui_design_pass.md): where each row goes
/// (worst first), which rows a filter and a search show, which entry Up and Down move to, and what Ctrl+C copies.
/// Never a false pass: every row is in exactly one place, a failure is never below a needs review, a row's status is
/// only ever its own verdict's (a stale list has no green), and a folded place holds only what complies or doesn't
/// apply.
/// </summary>
public static class ResultList
{
    /// <summary>Every row of the check in its one place, in the order shown: does not comply (the largest how far off
    /// first, where the worker's figure is a length; the rest in the worker's order), needs review (the worker's
    /// order: its tier 2), check by hand and not checked, then complies and not applicable.</summary>
    public static IReadOnlyList<ListRow> Place(ResultModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        var stale = model.Stale is not null;
        var placed = new List<ListRow>();
        foreach (var g in model.Groups)
        {
            var byHand = g.Key.EndsWith(":by_hand", StringComparison.Ordinal);
            var own = PlaceOf(g.Key);
            if (g.Lines.Count == 0)
                placed.AddRange(g.Rows.Select(r => Placed(r, byHand, stale, g.Title, "g:" + g.Key, g.Rows.Count, fromLine: false, own)));
            else
                foreach (var l in g.Lines)
                    placed.AddRange(l.Rows.Select(r => Placed(r, byHand, stale, l.Title, "l:" + g.Key + "/" + l.Title, l.Rows.Count, fromLine: true, own)));
        }
        // stable: OrderBy keeps the worker's order within a place (and among failures of the same size, or none)
        return placed.Select((p, n) => (p, n))
                     .OrderBy(x => x.p.Section)
                     .ThenBy(x => x.p.Section == ListSection.Fails && HowFarOff(x.p.Row) is { } size ? -size : double.PositiveInfinity)
                     .ThenBy(x => x.n)
                     .Select(x => x.p).ToList();
    }

    private static ListRow Placed(ResultRow r, bool byHand, bool stale, string source, string key, int count, bool fromLine,
                                  ListSection? own) =>
        new(r, SectionOf(r.Verdict, byHand), StatusLook.Of(r.Tone, stale), source, key, count, fromLine, own);

    /// <summary>The place a worker group's key gives its rows (present.grouped: zoning's <c>fails</c>, <c>review</c>,
    /// <c>use_details</c>, <c>complies</c>, <c>not_checked</c>, <c>not_covered</c>; a law's
    /// <c>&lt;law&gt;:fails|review|by_hand|complies</c>), or null for any other (a law still waiting for rooms).</summary>
    public static ListSection? PlaceOf(string groupKey)
    {
        ArgumentNullException.ThrowIfNull(groupKey);
        var tier = groupKey.LastIndexOf(':') is var i and >= 0 ? groupKey[(i + 1)..] : groupKey;
        return tier switch
        {
            "fails" => ListSection.Fails,
            "review" or "use_details" => ListSection.Review,
            "by_hand" or "not_checked" or "not_covered" => ListSection.ByHand,
            "complies" => ListSection.Complies,
            _ => null,
        };
    }

    /// <summary>A row's place, from its own verdict as the add-in reads it (a status word it doesn't know, or "not
    /// applicable" with no reason, is already needs review): a failure is always first, wherever the worker grouped
    /// it; only a row that complies or doesn't apply is ever in the folded place; a needs review is "check by hand"
    /// only when the worker put it in its tier 3 (<c>&lt;law&gt;:by_hand</c>).</summary>
    public static ListSection SectionOf(Verdict verdict, bool inByHandTier) => verdict switch
    {
        Verdict.DoesNotComply => ListSection.Fails,
        Verdict.Complies or Verdict.NotApplicable => ListSection.Complies,
        Verdict.NotChecked => ListSection.ByHand,
        _ => inByHandTier ? ListSection.ByHand : ListSection.Review,
    };

    // a length as the worker writes it: 2'-6", 0'-11 1/4", 12'-2 3/4"
    private static readonly Regex Length = new(@"(?<ft>[0-9][0-9,]*)'-(?<in>[0-9]+)(?: (?<n>[0-9]+)/(?<d>[0-9]+))?""",
                                               RegexOptions.CultureInvariant);

    /// <summary>How far off a failing row is, in feet, read from the worker's own words (<see cref="ResultRow.HowFar"/>)
    /// only to order the failures: when they say a shortfall or an excess ("2'-6\" short", "−2'-6\"", "at least
    /// 0'-11 1/4\" short", "1'-6\" over") as a length, its first length; else null (room to spare, "at limit", an area
    /// or a ratio, which can't be set against a length, or no figure). Never shown: the row shows the worker's
    /// words.</summary>
    public static double? HowFarOff(ResultRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        if (row.HowFar is not { } words)
            return null;
        var t = words.TrimStart();
        var off = t.StartsWith('−') || t.StartsWith('-') || Regex.IsMatch(t, @"^[^(;]*\b(short|over)\b", RegexOptions.CultureInvariant);
        if (!off || t.StartsWith('+') || t.StartsWith("≥", StringComparison.Ordinal))
            return null;
        var m = Length.Match(t);
        if (!m.Success)
            return null;
        var feet = double.Parse(m.Groups["ft"].Value.Replace(",", "", StringComparison.Ordinal), CultureInfo.InvariantCulture);
        var inches = double.Parse(m.Groups["in"].Value, CultureInfo.InvariantCulture);
        if (m.Groups["n"].Success && double.Parse(m.Groups["d"].Value, CultureInfo.InvariantCulture) is var d and > 0)
            inches += double.Parse(m.Groups["n"].Value, CultureInfo.InvariantCulture) / d;
        return feet + inches / 12;
    }

    /// <summary>Whether a filter shows a place: does not comply its own; needs review both the review and the
    /// check-by-hand places (neither a failure nor a pass); complies the complies and not applicable place.</summary>
    public static bool Shows(ListFilter filter, ListSection section) => filter switch
    {
        ListFilter.All => true,
        ListFilter.Fails => section == ListSection.Fails,
        ListFilter.Review => section is ListSection.Review or ListSection.ByHand,
        ListFilter.Complies => section == ListSection.Complies,
        _ => throw new ArgumentOutOfRangeException(nameof(filter)),
    };

    /// <summary>The search's words: each must be found (in any order, any case) in the row's name, its law section or
    /// the name of one of its elements as the project labels it.</summary>
    public static IReadOnlyList<string> Terms(string? query) =>
        (query ?? "").Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

    /// <summary>Whether a row matches the search: every term is in its name, its section or one of its elements' labels
    /// (an element with no label is not searched by its UniqueId). No terms: every row.</summary>
    public static bool Matches(ResultRow row, IReadOnlyList<string> terms, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(terms);
        if (terms.Count == 0)
            return true;
        var said = new List<string> { row.Name };
        if (row.Section is not null)
            said.Add(row.Section);
        if (labels is not null)
            foreach (var uid in row.Elements)
                if (labels.TryGetValue(uid, out var label))
                    said.Add(label);
        return terms.All(t => said.Any(s => s.Contains(t, StringComparison.OrdinalIgnoreCase)));
    }

    /// <summary>A place's heading words: the worker's own tier names; the folded place named by what it holds
    /// (grouping.tier_title: "Complies", "Not applicable", or "Complies or not applicable"), so a row that doesn't
    /// apply is never under "Complies" alone.</summary>
    public static string Title(ListSection section, IEnumerable<ListRow> rows) => section switch
    {
        ListSection.Fails => "Does not comply",
        ListSection.Review => "Needs review",
        ListSection.ByHand => "Check by hand or not checked yet",
        ListSection.Complies => rows.Select(r => r.Row.Verdict == Verdict.Complies).Distinct().ToList() switch
        {
            [true] => "Complies",
            [false] => "Not applicable",
            _ => "Complies or not applicable",
        },
        _ => throw new ArgumentOutOfRangeException(nameof(section)),
    };

    /// <summary>A place's glyph: its own tone (stale once the model changed); the folded place green only when every
    /// row in it complies (one that doesn't apply makes it the not-applicable dash).</summary>
    public static PanelStatus StatusOf(ListSection section, IReadOnlyCollection<ListRow> rows, bool stale) => section switch
    {
        ListSection.Fails => StatusLook.Of(Tone.Fails, stale),
        ListSection.Review or ListSection.ByHand => StatusLook.Of(Tone.Review, stale),
        ListSection.Complies => StatusLook.Of(rows.Count > 0 && rows.All(r => r.Row.Tone == Tone.Complies) ? Tone.Complies : Tone.Neutral, stale),
        _ => throw new ArgumentOutOfRangeException(nameof(section)),
    };

    /// <summary>The filter chips, in the count bar's order: all, does not comply, needs review, complies (named as its
    /// place is), each with its place's glyph (stale once the model changed).</summary>
    public static IReadOnlyList<ListChip> Chips(IReadOnlyList<ListRow> placed, bool stale)
    {
        ArgumentNullException.ThrowIfNull(placed);
        var complies = placed.Where(r => r.Section == ListSection.Complies).ToList();
        return
        [
            new ListChip(ListFilter.All, "All", null),
            new ListChip(ListFilter.Fails, "Does not comply", StatusOf(ListSection.Fails, [], stale)),
            new ListChip(ListFilter.Review, "Needs review", StatusOf(ListSection.Review, [], stale)),
            new ListChip(ListFilter.Complies, complies.Count == 0 ? "Complies" : Title(ListSection.Complies, complies),
                         complies.Count == 0 ? StatusLook.Of(Tone.Neutral, stale) : StatusOf(ListSection.Complies, complies, stale)),
        ];
    }

    /// <summary>The list as shown: each place that has rows to show, its heading, then (unless folded) its rows, a
    /// run of rows of one worker line or group under that line's sub-heading in the review, check-by-hand and complies
    /// places (the failures are one run, largest first). Every run has its own sub-heading (<see cref="RunTitle"/>), so
    /// no run reads as more rows of the one before: the worker's counted words only where they hold, else a name that
    /// claims no count or status (a row the add-in reads more cautiously than its line is never shown under that
    /// line's words, nor are the line's other rows: its words count a row no longer with them). With no filter and no
    /// search, the complies place is folded unless <paramref name="opened"/> holds it; no other place is ever folded
    /// (grouping.py: a line that is shown, never a fold); with a filter or a search, only the matching rows, nothing
    /// folded (a match is never hidden).</summary>
    public static IReadOnlyList<ListEntry> Layout(IReadOnlyList<ListRow> placed, ListFilter filter, string? query,
                                                  IReadOnlyDictionary<string, string>? labels, bool stale,
                                                  IReadOnlySet<ListSection>? opened = null)
    {
        ArgumentNullException.ThrowIfNull(placed);
        var terms = Terms(query);
        var narrowed = filter != ListFilter.All || terms.Count > 0;
        var entries = new List<ListEntry>();
        foreach (var section in Enum.GetValues<ListSection>())
        {
            if (!Shows(filter, section))
                continue;
            var all = placed.Where(r => r.Section == section).ToList();
            var shown = all.Where(r => Matches(r.Row, terms, labels)).ToList();
            if (shown.Count == 0)
                continue;
            var foldable = !narrowed && section == ListSection.Complies;
            var folded = foldable && opened?.Contains(section) != true;
            entries.Add(new ListHeading(section, Title(section, all), shown.Count, folded, foldable, StatusOf(section, all, stale)));
            if (folded)
                continue;
            var here = all.GroupBy(p => p.SourceKey, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);
            var status = StatusOf(section, all, stale);
            var place = Title(section, all);
            string? run = null;
            foreach (var r in shown)
            {
                if (section != ListSection.Fails && r.SourceKey != run)
                {
                    run = r.SourceKey;
                    entries.Add(new ListSubheading(r.SourceKey, RunTitle(r, section, here[r.SourceKey], place), status));
                }
                entries.Add(new ListRowEntry(r));
            }
        }
        return entries;
    }

    /// <summary>The words over a run of rows of one worker line or group in <paramref name="section"/> (every run has
    /// its own, so a run never reads as more rows of the one before): the worker's title, which may count its rows
    /// ("Front door: 2 need review"), only when all <paramref name="hereCount"/> of the source's rows are here and here
    /// is the place its worker tier gives it (or the key names no tier, as a law still waiting for rooms: its title is
    /// its law's name); a line of one row is named, not counted. Otherwise a name that claims no count or status: a
    /// line's part ("Window 2" from "Window 2: 2 comply · 1 doesn't apply"), a law group's law ("Egress" from "Egress ·
    /// Complies"), or "Zoning" for zoning's groups by status. A title that only restates its place's heading
    /// (<paramref name="placeTitle"/>: zoning's "Needs review" group under NEEDS REVIEW) is that name instead.</summary>
    public static string RunTitle(ListRow r, ListSection section, int hereCount, string? placeTitle = null)
    {
        ArgumentNullException.ThrowIfNull(r);
        var whole = hereCount == r.SourceRows && r.SourcePlace == section;          // a key with no tier: its name, below
        var title = whole && (!r.FromLine || r.SourceRows > 1) ? r.Source : Neutral(r);
        return placeTitle is not null && string.Equals(title, placeTitle, StringComparison.OrdinalIgnoreCase) ? Neutral(r) : title;
    }

    /// <summary>A run's name that claims no count or status: a line's part, a law group's law, or "Zoning".</summary>
    private static string Neutral(ListRow r)
    {
        if (r.FromLine)
            return r.Source.IndexOf(": ", StringComparison.Ordinal) is var c and > 0 ? r.Source[..c] : r.Source;
        if (r.Source.IndexOf(" · ", StringComparison.Ordinal) is var d and > 0)
            return r.Source[..d];
        return r.SourcePlace is not null ? "Zoning" : r.Source;
    }

    /// <summary>The list with the summary (the state and the counts) as its first entry, above every place: it scrolls
    /// with the rows, and only the filter chips and the search stay pinned (Revit trial, 106 Ithaca Rd: pinned, the
    /// summary filled the whole docked pane).</summary>
    public static IReadOnlyList<ListEntry> WithSummary(IReadOnlyList<ListEntry> entries)
    {
        ArgumentNullException.ThrowIfNull(entries);
        return [new ListSummary(), .. entries];
    }

    /// <summary>Where Up (<paramref name="step"/> −1) or Down (+1) moves from entry <paramref name="from"/>: the
    /// nearest row that way, skipping headings; at the end, the same row. From nothing selected (−1), Down goes to the
    /// first row and Up to the last. −1 when the list has no rows.</summary>
    public static int Next(IReadOnlyList<ListEntry> entries, int from, int step)
    {
        ArgumentNullException.ThrowIfNull(entries);
        if (step is not (1 or -1))
            throw new ArgumentOutOfRangeException(nameof(step));
        if (from < 0 || from >= entries.Count)
            from = step > 0 ? -1 : entries.Count;
        for (var i = from + step; i >= 0 && i < entries.Count; i += step)
            if (entries[i] is ListRowEntry)
                return i;
        return from >= 0 && from < entries.Count && entries[from] is ListRowEntry ? from : -1;
    }

    /// <summary>A row's second line in the list (its first is its glyph, name and section): its verdict's words when its
    /// place's heading doesn't already say them ("not checked", "not applicable", a word the add-in doesn't know: "needs
    /// review (the checker said ...)"), then its figures and how far off in the worker's words, else how far off,
    /// else the worker's reason (the short cause). "" when the row has none of these.</summary>
    public static string SecondLine(ResultRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        var said = new List<string>();
        if (row.VerdictWords is not ("DOES NOT COMPLY" or "needs review" or "complies"))
            said.Add(row.VerdictWords);
        if (row.Figures is not null)
            said.Add(row.Figures + (row.HowFar is null ? "" : " · " + row.HowFar));
        else if (row.HowFar is not null)
            said.Add(row.HowFar);
        else if (row.Reason is not null)
            said.Add(row.Reason);
        return string.Join(" · ", said);
    }

    /// <summary>Whether the list's keys (Up, Down, Enter, Space, Ctrl+C) act on a key press: only one on a row
    /// (<paramref name="onRow"/>: its source is inside a row's container) or on the list itself (<paramref name="onList"/>:
    /// nothing in it focused yet). A key on anything else in the list (the Details and "What wasn't read" folds after the
    /// rows) is that control's own: Space on a fold's header opens it, never zooms to the row selected.</summary>
    public static bool ListTakesKey(bool onRow, bool onList) => onRow || onList;

    /// <summary>What Ctrl+C copies: the row as the text file writes it (<see cref="ResultText.Row"/>: its verdict, name,
    /// figures, reason and elements, each element by the project's label), and, once the model changed after the
    /// check, when it was checked, so a copied verdict is never read as the model's now.</summary>
    public static string CopyText(ResultRow row, IReadOnlyDictionary<string, string>? labels, DateTime? staleSince)
    {
        ArgumentNullException.ThrowIfNull(row);
        var line = row.Line(uid => labels?.GetValueOrDefault(uid));
        return staleSince is { } at ? $"{line} (checked {at:HH:mm}, before the model changed)" : line;
    }
}
