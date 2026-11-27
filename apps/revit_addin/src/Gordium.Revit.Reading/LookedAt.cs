using System.Globalization;

namespace Gordium.Revit.Reading;

/// <summary>
/// The architect's "looked at" ticks for one project's check (docs/revit/ui_design_pass.md section 2.4, PR 6): one per
/// cause card and one per row needing review or to check by hand. A tick is the architect's own note of where they
/// are in the list, <b>never a verdict</b>: nothing here reads or changes a row's status, and a row ticked stays
/// needs review until the checker says otherwise (only Check again changes a verdict).
/// When a new check of the project comes back, a tick is carried over only to what is still the same thing to look
/// at (<see cref="Carry"/>); anything that changed is unticked, so it is looked at again.
/// </summary>
public sealed class LookedAt
{
    private readonly HashSet<string> _cards = new(StringComparer.Ordinal);
    private readonly HashSet<string> _rows = new(StringComparer.Ordinal);

    /// <summary>Whether card <paramref name="key"/> is ticked.</summary>
    public bool Card(string key) => _cards.Contains(key);

    /// <summary>Whether row <paramref name="id"/> is ticked.</summary>
    public bool Row(string id) => _rows.Contains(id);

    /// <summary>Ticks or unticks a card.</summary>
    public void SetCard(string key, bool ticked)
    {
        ArgumentNullException.ThrowIfNull(key);
        if (ticked)
            _cards.Add(key);
        else
            _cards.Remove(key);
    }

    /// <summary>Ticks or unticks a row (one that can be ticked: <see cref="Tickable"/>; any other is refused).</summary>
    public void SetRow(ListRow row, bool ticked)
    {
        ArgumentNullException.ThrowIfNull(row);
        if (!Tickable(row))
            return;
        if (ticked)
            _rows.Add(row.Row.Id);
        else
            _rows.Remove(row.Row.Id);
    }

    /// <summary>The cards ticked, for the tests.</summary>
    public IReadOnlyCollection<string> Cards => _cards;

    /// <summary>The rows ticked, for the tests.</summary>
    public IReadOnlyCollection<string> Rows => _rows;

    /// <summary>Whether a row takes a tick: one needing review or to check by hand (or not checked). What does not
    /// comply is changed in the design; what complies has nothing to look at.</summary>
    public static bool Tickable(ListRow row)
    {
        ArgumentNullException.ThrowIfNull(row);
        return row.Section is ListSection.Review or ListSection.ByHand;
    }

    /// <summary>The ticks a new check (<paramref name="after"/>) of the same project starts with, from the ticks of the
    /// check before (<paramref name="before"/>, ticked on <paramref name="was"/>): a worker card's tick only when the
    /// new answer has a card of the same key, the same words and the same rows; a fix's tick ("Start here": the pane
    /// ticks fixes by <see cref="Fix.Key"/>, each fix made with the element names of its check, <paramref name="wasLabels"/>
    /// and <paramref name="afterLabels"/>) only when the new answer has a fix of the same key whose cards are the same,
    /// in the same order (each card's key, words and rows); a row's only when the new answer has it with the same
    /// verdict (words and all), reason, figures and how far, and it still takes a tick. Everything else starts
    /// unticked (it changed: look again). No check before, or one of nothing (a fact missing): none.</summary>
    public static LookedAt Carry(LookedAt? before, ResultModel? was, ResultModel after,
                                 IReadOnlyDictionary<string, string>? wasLabels = null, IReadOnlyDictionary<string, string>? afterLabels = null)
    {
        ArgumentNullException.ThrowIfNull(after);
        var now = new LookedAt();
        if (before is null || was is null)
            return now;
        var oldCards = was.Causes.ToDictionary(c => c.Key, StringComparer.Ordinal);
        foreach (var c in after.Causes)
            if (before.Card(c.Key) && oldCards.TryGetValue(c.Key, out var o) && o.Words == c.Words && o.Items.SequenceEqual(c.Items))
                now._cards.Add(c.Key);
        var oldFixes = Fixes.Of(was.Causes, wasLabels).ToDictionary(f => f.Key, StringComparer.Ordinal);
        foreach (var f in Fixes.Of(after.Causes, afterLabels))
            if (before.Card(f.Key) && oldFixes.TryGetValue(f.Key, out var of) && SameCards(of.Members, f.Members))
                now._cards.Add(f.Key);
        var oldRows = ResultList.Place(was).ToDictionary(r => r.Row.Id, StringComparer.Ordinal);
        foreach (var r in ResultList.Place(after))
            if (before.Row(r.Row.Id) && Tickable(r) && oldRows.TryGetValue(r.Row.Id, out var p) && Same(p.Row, r.Row))
                now._rows.Add(r.Row.Id);
        return now;
    }

    /// <summary>Whether two fixes join the same cards, in the same order: each card's key, words and rows.</summary>
    private static bool SameCards(IReadOnlyList<CauseCard> a, IReadOnlyList<CauseCard> b) =>
        a.Count == b.Count && a.Zip(b).All(p => p.First.Key == p.Second.Key && p.First.Words == p.Second.Words && p.First.Items.SequenceEqual(p.Second.Items));

    /// <summary>Whether a row says the same in two checks: its verdict (and its words), reason, figures and how far.</summary>
    private static bool Same(ResultRow a, ResultRow b) =>
        a.Verdict == b.Verdict && a.VerdictWords == b.VerdictWords && a.Reason == b.Reason && a.Figures == b.Figures && a.HowFar == b.HowFar;

    /// <summary>The progress line: "Looked at: 2 of 3 causes · 5 of 181 rows" (cards and rows counted, the rows those
    /// that take a tick); "" when there is nothing to look at.</summary>
    public string Progress(IReadOnlyList<CauseCard> cards, IReadOnlyList<ListRow> placed)
    {
        ArgumentNullException.ThrowIfNull(cards);
        ArgumentNullException.ThrowIfNull(placed);
        var rows = placed.Where(Tickable).ToList();
        var said = new List<string>();
        if (cards.Count > 0)
            said.Add(string.Create(CultureInfo.InvariantCulture,
                $"{cards.Count(c => Card(c.Key))} of {cards.Count} cause{(cards.Count == 1 ? "" : "s")}"));
        if (rows.Count > 0)
            said.Add(string.Create(CultureInfo.InvariantCulture,
                $"{rows.Count(r => Row(r.Row.Id))} of {rows.Count} row{(rows.Count == 1 ? "" : "s")}"));
        return said.Count == 0 ? "" : "Looked at: " + string.Join(" · ", said);
    }

    /// <summary>The tooltip of every "Looked at" tick: what it is, and what it is not.</summary>
    public const string Tip = "Your own note that you've looked at this. It changes no verdict: only a check does. " +
                              "Kept for this project's check; carried to the next check only where nothing changed.";
}
