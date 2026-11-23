using System.Globalization;

namespace Gordium.Revit.Reading;

/// <summary>What the pane's selection strip says about what is selected in Revit (the UI design pass, change 14).</summary>
/// <param name="Title">The element as an architect names it ("STORAGE (13)"), or "3 elements".</param>
/// <param name="Line">How many results mention it and their verdicts ("11 results mention it: 11 need review"), or
/// that none does (never read as a pass), or, once the model changed, that they did at the check.</param>
/// <param name="Rows">The results that mention it, each once, in the pane's order (worst first), each with its own
/// status (stale once the model changed).</param>
public sealed record SelectionAnswer(string Title, string Line, IReadOnlyList<ListRow> Rows);

/// <summary>
/// Which results mention an element (docs/revit/ui_design_pass.md, change 14), Revit-free so it is tested: an element
/// is mentioned by a result whose own elements name it (a zoning row's <c>objects</c>, an egress row's part), and by
/// every result of a cause card that names it as one of its rooms (<see cref="RoomsOf"/>) (the worker's "5 rooms have no route to an exit":
/// the card's rows wait on those rooms). Built once per answer the pane shows; a selection is then a lookup. Nothing
/// here makes or changes a verdict: each row is the pane's own <see cref="ListRow"/>, with its status.
/// </summary>
public sealed class SelectionMap
{
    private readonly Dictionary<string, List<ListRow>> _byElement = new(StringComparer.Ordinal);
    private readonly Dictionary<ListRow, int> _order = [];

    /// <summary>The results the map was made from, in the pane's order.</summary>
    public IReadOnlyList<ListRow> Placed { get; }

    /// <summary>When the answer was checked, and whether the model changed since (the rows' statuses are then stale).</summary>
    public DateTime CheckedAt { get; }

    /// <summary>Whether the model changed after the check.</summary>
    public bool Stale { get; }

    private SelectionMap(IReadOnlyList<ListRow> placed, DateTime checkedAt, bool stale)
    {
        Placed = placed;
        CheckedAt = checkedAt;
        Stale = stale;
        for (var i = 0; i < placed.Count; i++)
            _order[placed[i]] = i;
    }

    /// <summary>The map of one answer: every row placed as the pane places it (<see cref="ResultList.Place"/>), under
    /// each element it names and each room its cause cards name.</summary>
    public static SelectionMap Of(ResultModel model, DateTime checkedAt)
    {
        ArgumentNullException.ThrowIfNull(model);
        var placed = ResultList.Place(model);
        var map = new SelectionMap(placed, checkedAt, model.Stale is not null);
        var byId = new Dictionary<string, ListRow>(StringComparer.Ordinal);
        foreach (var p in placed)
            byId.TryAdd(p.Row.Id, p);
        foreach (var p in placed)
            foreach (var uid in p.Row.Elements)
                map.Add(uid, p);
        foreach (var card in model.Causes)
            foreach (var room in RoomsOf(card))
                foreach (var id in card.Items)
                    if (byId.TryGetValue(id, out var p))
                        map.Add(room, p);
        return map;
    }

    /// <summary>The rooms a cause card names: its rows' own rooms of its key (<see cref="CauseCard.Rooms"/>), and, for a
    /// rooms card (key "rooms:..."), the card's own elements too. The worker merges rooms cards whose rooms overlap
    /// (grouping._rooms_together: "rooms:A,B" and "rooms:B,C" become one "rooms:A,B,C" card) while each row keeps its
    /// narrower key, so the card's Rooms can be empty: its elements are then the only place its rooms are named
    /// (review round 1).</summary>
    public static IReadOnlyList<string> RoomsOf(CauseCard card)
    {
        ArgumentNullException.ThrowIfNull(card);
        var rooms = card.Rooms.Select(r => r.Id).ToList();
        if (card.Key.StartsWith("rooms:", StringComparison.Ordinal))
            rooms.AddRange(card.Elements);
        return [.. rooms.Distinct(StringComparer.Ordinal)];
    }

    private void Add(string uid, ListRow row)
    {
        if (!_byElement.TryGetValue(uid, out var rows))
            _byElement[uid] = rows = [];
        if (!rows.Contains(row))
            rows.Add(row);
    }

    /// <summary>Every element (by UniqueId) some result mentions.</summary>
    public IEnumerable<string> Elements => _byElement.Keys;

    /// <summary>The results that mention any of <paramref name="uids"/>, each once, in the pane's order.</summary>
    public IReadOnlyList<ListRow> For(IEnumerable<string> uids)
    {
        ArgumentNullException.ThrowIfNull(uids);
        var found = new HashSet<ListRow>();
        foreach (var uid in uids)
            if (_byElement.TryGetValue(uid, out var rows))
                found.UnionWith(rows);
        return [.. found.OrderBy(r => _order[r])];
    }

    /// <summary>What the strip says for a selection of <paramref name="uids"/>; <paramref name="label"/> names an
    /// element as the architect knows it ("STORAGE (13)"), or null when it can't.</summary>
    public SelectionAnswer Answer(IReadOnlyList<string> uids, Func<string, string?> label)
    {
        ArgumentNullException.ThrowIfNull(uids);
        ArgumentNullException.ThrowIfNull(label);
        var distinct = uids.Distinct(StringComparer.Ordinal).ToList();
        var title = distinct.Count == 1 ? label(distinct[0]) ?? "1 element" : $"{distinct.Count} elements";
        var rows = For(distinct);
        var it = distinct.Count == 1 ? "it" : "them";
        var at = CheckedAt.ToString("HH:mm", CultureInfo.InvariantCulture);
        string line;
        if (rows.Count == 0)
            line = $"No result of this check mentions {it}. That is not a pass: Gordium may not read or check {it}.";
        else if (Stale)
            line = $"{Results(rows.Count)} mentioned {it} at the check at {at}; the model changed since, so check again.";
        else
            line = $"{Results(rows.Count)} mention{(rows.Count == 1 ? "s" : "")} {it}: {Verdicts(rows)}";
        return new SelectionAnswer(title, line, rows);
    }

    private static string Results(int n) => n == 1 ? "1 result" : $"{n} results";

    /// <summary>The rows' verdicts counted in the pane's words, worst first: "1 does not comply, 2 need review, 3 comply".</summary>
    internal static string Verdicts(IReadOnlyList<ListRow> rows)
    {
        var fails = rows.Count(r => r.Section == ListSection.Fails);
        var review = rows.Count(r => r.Section is ListSection.Review or ListSection.ByHand);
        var complies = rows.Count(r => r.Section == ListSection.Complies && r.Row.Tone == Tone.Complies);
        var aside = rows.Count(r => r.Section == ListSection.Complies && r.Row.Tone != Tone.Complies);
        var said = new List<string>();
        if (fails > 0)
            said.Add($"{fails} {(fails == 1 ? "does" : "do")} not comply");
        if (review > 0)
            said.Add($"{review} need{(review == 1 ? "s" : "")} review");
        if (complies > 0)
            said.Add($"{complies} compl{(complies == 1 ? "ies" : "y")}");
        if (aside > 0)
            said.Add($"{aside} not applicable");
        return string.Join(", ", said);
    }

    /// <summary>How many rows the strip lists before "Show all N": eight (the docked pane keeps room for the list).</summary>
    public const int Shown = 8;
}
