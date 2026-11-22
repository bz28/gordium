using System.Globalization;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>One row whose verdict differs between two checks, or that is in only one of them.</summary>
/// <param name="Id">The worker's row id (rows are matched by id, never by name).</param>
/// <param name="Name">Its name in the newer check (the older's when it is gone).</param>
/// <param name="Before">Its verdict in the check before, or null when it is new.</param>
/// <param name="After">Its verdict now, or null when it is gone.</param>
/// <param name="Words">"Travel distance now complies", "Dead end: needs review → does not comply".</param>
public sealed record RowChange(string Id, string Name, Verdict? Before, Verdict? After, string Words);

/// <summary>What changed between two checks of one project, by row id.</summary>
/// <param name="Words">One line: "2 rows changed since 14:32: Travel distance now complies; Dead end: needs review → does
/// not comply", or "Nothing changed since the check at 14:32", or why it isn't compared.</param>
/// <param name="Rows">Each row whose verdict changed, is new, or is gone, worst now first.</param>
/// <param name="Said">Rows with the same verdict whose reason, figures or how far changed.</param>
/// <param name="Compared">Whether the two checks were compared (not when the new answer is already stale).</param>
public sealed record CheckChange(string Words, IReadOnlyList<RowChange> Rows, int Said, bool Compared);

/// <summary>
/// Check again with what changed (docs/revit/ui_design_pass.md section 2.4, PR 6): the newer check's rows set
/// against the check before's, matched by row id, in the worker's verdicts only. Never a change the worker didn't
/// send: a row is changed only when its verdict (or its words) differ between the two answers; a row in only one is
/// new or gone; nothing is worked out from figures. An answer that is already stale when it arrives (the model changed
/// while it was checked) isn't compared: its rows may not be the model's.
/// </summary>
public static class CheckChanges
{
    /// <summary>How many changed rows the line names before "and N more".</summary>
    public const int Named = 3;

    /// <summary>What changed from <paramref name="before"/> (checked at <paramref name="beforeAt"/>) to
    /// <paramref name="after"/>; null when there is no check before to compare with.</summary>
    public static CheckChange? Between(ResultModel? before, DateTime beforeAt, ResultModel after)
    {
        ArgumentNullException.ThrowIfNull(after);
        if (before is null)
            return null;
        var at = beforeAt.ToString("HH:mm", CultureInfo.InvariantCulture);
        if (after.Stale is not null)
            return new CheckChange($"Not compared with the check at {at}: the model changed while this one ran, so its rows may not be the model's.",
                                   [], 0, Compared: false);
        var old = Rows(before);
        var now = Rows(after);
        var changes = new List<(RowChange Change, int Rank, int Order)>();
        var said = 0;
        var n = 0;
        foreach (var (id, r) in now)
        {
            n++;
            if (!old.TryGetValue(id, out var o))
                changes.Add((new RowChange(id, r.Name, null, r.Verdict, $"{r.Name}: new, {Word(r)}"), Rank(r.Verdict), n));
            else if (o.Verdict != r.Verdict || o.VerdictWords != r.VerdictWords)
                changes.Add((new RowChange(id, r.Name, o.Verdict, r.Verdict,
                                           r.Verdict == Verdict.Complies && Known(r) ? $"{r.Name} now complies" : $"{r.Name}: {Word(o)} → {Word(r)}"),
                             Rank(r.Verdict), n));
            else if (o.Reason != r.Reason || o.Figures != r.Figures || o.HowFar != r.HowFar)
                said++;
        }
        foreach (var (id, o) in old)
            if (!now.ContainsKey(id))
                changes.Add((new RowChange(id, o.Name, o.Verdict, null, $"{o.Name}: no longer in the check (it was {Word(o)})"), 5, ++n));
        var rows = changes.OrderBy(c => c.Rank).ThenBy(c => c.Order).Select(c => c.Change).ToList();
        if (rows.Count == 0 && said == 0)
            return new CheckChange($"Nothing changed since the check at {at}.", rows, 0, Compared: true);
        var words = rows.Count == 0
            ? $"No verdict changed since the check at {at}"
            : $"{rows.Count} row{(rows.Count == 1 ? "" : "s")} changed since {at}: " + string.Join("; ", rows.Take(Named).Select(c => c.Words))
              + (rows.Count > Named ? $"; and {rows.Count - Named} more" : "");
        if (said > 0)
            words += rows.Count == 0
                ? $": {said} row{(said == 1 ? "" : "s")} say{(said == 1 ? "s" : "")} something new (figures or reason)"
                : $". {said} more say{(said == 1 ? "s" : "")} something new with the same verdict";
        return new CheckChange(words + ".", rows, said, Compared: true);
    }

    /// <summary>Every row of a check by id, in the worker's order (an id given twice keeps its first).</summary>
    private static Dictionary<string, ResultRow> Rows(ResultModel m)
    {
        var rows = new Dictionary<string, ResultRow>(StringComparer.Ordinal);
        foreach (var r in m.Groups.SelectMany(g => g.AllRows))
            rows.TryAdd(r.Id, r);
        return rows;
    }

    /// <summary>Whether the row's verdict is a word the add-in knows (ResultText.RowWords: an unknown one is "needs
    /// review (the checker said ...)").</summary>
    private static bool Known(ResultRow r) => !r.VerdictWords.StartsWith("needs review (the checker said", StringComparison.Ordinal);

    /// <summary>Worst first: does not comply, needs review, not checked, complies, doesn't apply (grouping.py's CAUTION).</summary>
    private static int Rank(Verdict v) => v switch
    {
        Verdict.DoesNotComply => 0,
        Verdict.NotChecked => 2,
        Verdict.Complies => 3,
        Verdict.NotApplicable => 4,
        _ => 1,
    };

    /// <summary>A verdict in plain lower-case words ("does not comply"); a word the add-in doesn't know, the row's own.</summary>
    private static string Word(ResultRow r) => !Known(r) ? r.VerdictWords : r.Verdict switch
    {
        Verdict.DoesNotComply => "does not comply",
        Verdict.Complies => "complies",
        Verdict.NotChecked => "not checked",
        Verdict.NotApplicable => "doesn't apply",
        _ => "needs review",
    };
}
