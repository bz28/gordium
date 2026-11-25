namespace Gordium.Revit.Reading;

/// <summary>One law's counts on one line of the count bar: the chips shown, and the rest behind "+N more".</summary>
/// <param name="Title">The law's short name ("Zoning"), or null for the whole summary's line.</param>
/// <param name="FullTitle">The law's whole title ("Zoning (City of Ithaca)"), for the tooltip.</param>
/// <param name="Shown">The chips on the line: every "does not comply" count, then the first others in the worker's
/// order, up to <see cref="CountBar.Keep"/> in all.</param>
/// <param name="Hidden">The rest, in the worker's order: behind "+N more", and in the tooltip.</param>
public sealed record CountRow(string? Title, string? FullTitle, IReadOnlyList<CountChip> Shown, IReadOnlyList<CountChip> Hidden)
{
    /// <summary>"+4" (null when nothing is hidden): how many counts more, not a count of rows; short, so it stays on
    /// the law's line at the docked width (Revit trial: "+4 more" wrapped to a line of its own).</summary>
    public string? More => Hidden.Count == 0 ? null : $"+{Hidden.Count}";

    /// <summary>"4 more counts" (for a screen reader and the button's name), or null.</summary>
    public string? MoreWords => Hidden.Count == 0 ? null : $"{Hidden.Count} more count{(Hidden.Count == 1 ? "" : "s")}";

    /// <summary>Every count of the law, one a line, in the worker's order (the tooltip on the line and on "+N more").</summary>
    public string Tooltip => string.Join("\n", new[] { FullTitle }.Where(t => t is not null).Concat(Shown.Concat(Hidden).Select(c => c.Words)));
}

/// <summary>
/// The compact count bar (Revit trial, 106 Ithaca Rd, 2026-11-22: at the default docked pane, ~340 by 430 px, the
/// worker's 9 counts took 6 lines and the first result was below the pane): one line per law with its most important
/// counts, the rest behind "+N more" (opened in place) and every one in the tooltip. Nothing is recounted and no count
/// is dropped: the chips are the worker's words (<see cref="ResultRows.Counts"/>), only some shown later. A "does not
/// comply" count is never hidden, whatever the room.
/// </summary>
public static class CountBar
{
    /// <summary>How many chips a law's line shows before "+N more" (two chips, the law's name and "+N more" fit
    /// the docked pane's 316 px between its gutters).</summary>
    public const int Keep = 2;

    /// <summary>A law's line: its failures always shown, then the worker's other counts in its order up to
    /// <paramref name="keep"/>; the rest hidden in order. <paramref name="open"/>: the architect opened "+N more"
    /// (every chip shown, nothing hidden).</summary>
    public static CountRow Row(CountLine line, bool open = false, int keep = Keep)
    {
        ArgumentNullException.ThrowIfNull(line);
        if (open)
            return new CountRow(Short(line.Title), line.Title, line.Chips, []);
        // by position, never by value (two counts may say the same words), shown in the worker's order
        var room = Math.Max(0, keep - line.Chips.Count(c => c.IsFailure));
        var show = new bool[line.Chips.Count];
        for (var i = 0; i < show.Length; i++)
            if (line.Chips[i].IsFailure)                // what it means, never its colour (grey once stale)
                show[i] = true;
            else if (room > 0)
            {
                show[i] = true;
                room--;
            }
        return new CountRow(Short(line.Title), line.Title, line.Chips.Where((_, i) => show[i]).ToList(),
                            line.Chips.Where((_, i) => !show[i]).ToList());
    }

    /// <summary>A law's short name for its line: "Zoning" from "Zoning (City of Ithaca)".</summary>
    public static string? Short(string? title) =>
        title is not null && title.IndexOf(" (", StringComparison.Ordinal) is var i and > 0 ? title[..i] : title;
}

/// <summary>One segment of the results' proportion bar (UI polish change 18): the status it is drawn in, how many of
/// the checker's rows it stands for, and their verdict in words ("1 complies": review round 1, a complying slice drawn
/// neutral was called "Not applicable" on hover).</summary>
public sealed record BarSegment(PanelStatus Status, int Count)
{
    /// <summary>What the slice is, in the checker's verdict: "98 need review", "1 complies".</summary>
    public string Words { get; init; } = "";
}

/// <summary>
/// The proportion bar under the results' summary line (UI polish change 18): one segment per verdict, as long as its
/// share of the checker's rows, worst first, zero counts left out. Never green while anything fails, needs review or
/// isn't checked yet (what complies is then drawn in the neutral colour: the bar is a glance, and a green sliver beside
/// 98 results in review reads as "some of it passes"); never a verdict's colour once stale.
/// </summary>
public static class ProportionBar
{
    private static readonly (Gordium.Worker.Verdict Verdict, PanelStatus Status)[] Order =
    [
        (Gordium.Worker.Verdict.DoesNotComply, PanelStatus.Fails),
        (Gordium.Worker.Verdict.NeedsReview, PanelStatus.Review),
        (Gordium.Worker.Verdict.NotChecked, PanelStatus.NotChecked),
        (Gordium.Worker.Verdict.Complies, PanelStatus.Complies),
        (Gordium.Worker.Verdict.NotApplicable, PanelStatus.NotApplicable),
    ];

    /// <summary>The segments of <paramref name="verdicts"/>, worst first; every verdict counted once (an unknown one is
    /// already needs review).</summary>
    public static IReadOnlyList<BarSegment> Segments(IReadOnlyCollection<Gordium.Worker.Verdict> verdicts, bool stale)
    {
        ArgumentNullException.ThrowIfNull(verdicts);
        var unsettled = verdicts.Any(v => v is Gordium.Worker.Verdict.DoesNotComply or Gordium.Worker.Verdict.NeedsReview or Gordium.Worker.Verdict.NotChecked);
        return [.. Order.Select(o => (o, n: verdicts.Count(v => v == o.Verdict))).Where(x => x.n > 0).Select(x => new BarSegment(
            stale ? PanelStatus.Stale : x.o.Status == PanelStatus.Complies && unsettled ? PanelStatus.NotApplicable : x.o.Status, x.n)
        {
            Words = (stale ? ResultViews.SummaryPast(Enumerable.Repeat(x.o.Verdict, x.n)) : ResultViews.Summary(Enumerable.Repeat(x.o.Verdict, x.n))),
        })];
    }
}
