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
public sealed record ListRow(ResultRow Row, ListSection Section, PanelStatus Status, string Source, string SourceKey,
                             int SourceRows, bool FromLine);

/// <summary>One entry of the list as shown: a place's heading, a sub-heading, or a row.</summary>
public abstract record ListEntry;

/// <summary>A place's heading ("NEEDS REVIEW · 12 rows"): folded or open, and whether a click can fold it (not while
/// a filter or a search shows only matching rows: those are always shown).</summary>
public sealed record ListHeading(ListSection Section, string Title, int Rows, bool Folded, bool Foldable, PanelStatus Status)
    : ListEntry;

/// <summary>The worker's line (or group) a run of rows is in ("Not read from the model yet: handrails (10 rules)..."),
/// with its place's glyph.</summary>
public sealed record ListSubheading(string Key, string Title, PanelStatus Status) : ListEntry;

/// <summary>A row of the list.</summary>
public sealed record ListRowEntry(ListRow Row) : ListEntry;

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
            if (g.Lines.Count == 0)
                placed.AddRange(g.Rows.Select(r => Placed(r, byHand, stale, g.Title, "g:" + g.Key, g.Rows.Count, fromLine: false)));
            else
                foreach (var l in g.Lines)
                    placed.AddRange(l.Rows.Select(r => Placed(r, byHand, stale, l.Title, "l:" + g.Key + "/" + l.Title, l.Rows.Count, fromLine: true)));
        }
        // stable: OrderBy keeps the worker's order within a place (and among failures of the same size, or none)
        return placed.Select((p, n) => (p, n))
                     .OrderBy(x => x.p.Section)
                     .ThenBy(x => x.p.Section == ListSection.Fails && HowFarOff(x.p.Row) is { } size ? -size : double.PositiveInfinity)
                     .ThenBy(x => x.n)
                     .Select(x => x.p).ToList();
    }

    private static ListRow Placed(ResultRow r, bool byHand, bool stale, string source, string key, int count, bool fromLine) =>
        new(r, SectionOf(r.Verdict, byHand), StatusLook.Of(r.Tone, stale), source, key, count, fromLine);

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
    /// places (a line of one row is that row, no sub-heading; the failures are one run, largest first). With no filter
    /// and no search, the complies place is folded unless <paramref name="opened"/> holds it, and a place in
    /// <paramref name="closed"/> is folded too (never the failures); with a filter or a search, only the matching rows,
    /// nothing folded (a match is never hidden).</summary>
    public static IReadOnlyList<ListEntry> Layout(IReadOnlyList<ListRow> placed, ListFilter filter, string? query,
                                                  IReadOnlyDictionary<string, string>? labels, bool stale,
                                                  IReadOnlySet<ListSection>? opened = null, IReadOnlySet<ListSection>? closed = null)
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
            var folded = !narrowed && section != ListSection.Fails
                         && (section == ListSection.Complies ? opened?.Contains(section) != true : closed?.Contains(section) == true);
            entries.Add(new ListHeading(section, Title(section, all), shown.Count, folded, Foldable: !narrowed && section != ListSection.Fails,
                                        StatusOf(section, all, stale)));
            if (folded)
                continue;
            var several = all.Select(p => p.SourceKey).Distinct().Skip(1).Any();     // more than one line or group here
            var status = StatusOf(section, all, stale);
            string? run = null;
            foreach (var r in shown)
            {
                if (section != ListSection.Fails && r.SourceKey != run)
                {
                    run = r.SourceKey;
                    if (r.FromLine ? r.SourceRows > 1 : several)
                        entries.Add(new ListSubheading(r.SourceKey, r.Source, status));
                }
                entries.Add(new ListRowEntry(r));
            }
        }
        return entries;
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
