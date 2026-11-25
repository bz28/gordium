namespace Gordium.Revit.Reading;

// The two results views as the pane's list draws them (UI polish changes 17, 21, 25, 33 to 37; Ben approved
// 2026-11-23): the entries of "What to fix" (each group, its cards, a card's rows when opened) and of "By code" (each
// node of the law's tree at its depth, a rule's rows when opened), from ResultViews. Revit-free and tested: the pane
// only draws these entries. A search shows the matching rows of either view as the plain list does. The rules: every
// row can be reached in either view (a fold opens to it, never hides it); a status is the rows' own (stale once the
// model changed: never green then), and a group or node holding anything unsettled is never drawn green.

/// <summary>A "What to fix" group's heading ("Answer 21 questions about the project", its sub line, "See 22 results").</summary>
/// <param name="Group">The group.</param>
/// <param name="Key">What the open set names it by (<see cref="ResultViewList.GroupKey"/>).</param>
/// <param name="Open">Whether its cards (or rows) are shown under it.</param>
/// <param name="Status">Its glyph (<see cref="ResultViewList.StatusOf(FixKind, IReadOnlyCollection{ResultRow}, bool)"/>).</param>
public sealed record FixGroupEntry(FixGroup Group, string Key, bool Open, PanelStatus Status) : ListEntry;

/// <summary>One card of an open group: the ask's headline, how many results wait on it, open to its rows.</summary>
public sealed record FixCardEntry(FixCard Card, string Key, bool Open, PanelStatus Status) : ListEntry;

/// <summary>One node of "By code" at its depth (0 a document): its state's glyph, its title and status line; open
/// to what is inside (a rule: its rows).</summary>
public sealed record CodeNodeEntry(CodeNode Node, string Key, int Depth, bool Open, bool CanOpen, PanelStatus Status) : ListEntry;

public static class ResultViewList
{
    /// <summary>The words of the switch (change 17), in its order.</summary>
    public static string Words(ResultsViewKind view) => view == ResultsViewKind.WhatToFix ? "What to fix" : "By code";

    public static string GroupKey(FixGroup g) => "fix:" + g.Kind;

    public static string CardKey(FixCard c) => "card:" + c.Kind + ":" + c.Key;

    /// <summary>What a group's heading looks like: what fails is fails; a group of questions, marks, fixes, hand checks
    /// or judgments needs review; not checked yet is its own dashed glyph; only the folded "complies or doesn't apply"
    /// group may be green, and only when every row in it complies. Stale: never green.</summary>
    public static PanelStatus StatusOf(FixKind kind, IReadOnlyCollection<ResultRow> rows, bool stale) => stale ? PanelStatus.Stale : kind switch
    {
        FixKind.Fails => PanelStatus.Fails,
        FixKind.NotChecked => PanelStatus.NotChecked,
        FixKind.Done => rows.Count > 0 && rows.All(r => r.Verdict == Gordium.Worker.Verdict.Complies) ? PanelStatus.Complies : PanelStatus.NotApplicable,
        _ => PanelStatus.Review,
    };

    /// <summary>A node's glyph from its state (change 34): green only for Complies, which ResultViews gives only when
    /// every row inside complies and nothing inside is unchecked. Stale: never green.</summary>
    public static PanelStatus StatusOf(CodeState state, bool stale) => stale ? PanelStatus.Stale : state switch
    {
        CodeState.Fails => PanelStatus.Fails,
        CodeState.Review => PanelStatus.Review,
        CodeState.NotCheckedYet => PanelStatus.NotChecked,
        CodeState.Complies => PanelStatus.Complies,
        _ => PanelStatus.NotApplicable,
    };

    /// <summary>Which groups and nodes start open: what fails and the first group of work (the architect's next
    /// step); in By code, each document.</summary>
    public static IEnumerable<string> OpenAtFirst(ResultViewsModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        foreach (var g in model.Fix.Where(g => g.Kind != FixKind.Done && g.Kind != FixKind.NotChecked).Take(1)
                                   .Concat(model.Fix.Where(g => g.Kind == FixKind.Fails)).Distinct())
            yield return GroupKey(g);
        for (var i = 0; i < model.Code.Count; i++)
            yield return NodeKey("", i);
    }

    private static string NodeKey(string parent, int index) => parent + "/" + index;

    /// <summary>The list for <paramref name="view"/>: its entries, with each row as the plain list places it
    /// (<paramref name="placed"/>, by id: its status, stale or not). A search (any term) shows the plain list's
    /// matching rows instead, the same in both views.</summary>
    public static IReadOnlyList<ListEntry> Layout(ResultViewsModel model, IReadOnlyList<ListRow> placed, ResultsViewKind view,
                                                  IReadOnlySet<string> open, string? query,
                                                  IReadOnlyDictionary<string, string>? labels, bool stale)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(placed);
        ArgumentNullException.ThrowIfNull(open);
        if (ResultList.Terms(query).Count > 0)
            return ResultList.Layout(placed, ListFilter.All, query, labels, stale);
        var byId = placed.ToDictionary(p => p.Row.Id, StringComparer.Ordinal);
        var entries = new List<ListEntry>();
        void Rows(IEnumerable<ResultRow> rows)
        {
            foreach (var r in rows)
                if (byId.TryGetValue(r.Id, out var p))
                    entries.Add(new ListRowEntry(p));
        }
        if (view == ResultsViewKind.WhatToFix)
        {
            foreach (var g in model.Fix)
            {
                var key = GroupKey(g);
                var isOpen = open.Contains(key);
                entries.Add(new FixGroupEntry(g, key, isOpen, StatusOf(g.Kind, g.Rows, stale)));
                if (!isOpen)
                    continue;
                // a group of rows, not asks (what fails, not checked yet, complies): its rows straight under it
                if (g.Kind is FixKind.Fails or FixKind.NotChecked or FixKind.Done)
                {
                    Rows(g.Rows);
                    continue;
                }
                foreach (var c in g.Cards)
                {
                    var ck = CardKey(c);
                    var cardOpen = open.Contains(ck);
                    entries.Add(new FixCardEntry(c, ck, cardOpen, StatusOf(g.Kind, c.Rows, stale)));
                    if (cardOpen)
                        Rows(c.Rows);
                }
            }
            return entries;
        }
        void Node(CodeNode n, string key, int depth)
        {
            var canOpen = n.Children.Count > 0 || n.Rows.Count > 0;
            var isOpen = canOpen && open.Contains(key);
            entries.Add(new CodeNodeEntry(n, key, depth, isOpen, canOpen, StatusOf(n.State, stale)));
            if (!isOpen)
                return;
            for (var i = 0; i < n.Children.Count; i++)
                Node(n.Children[i], NodeKey(key, i), depth + 1);
            Rows(n.Rows);
        }
        for (var i = 0; i < model.Code.Count; i++)
            Node(model.Code[i], NodeKey("", i), 0);
        return entries;
    }

    /// <summary>The opener a key on <paramref name="e"/> toggles (UI polish PR 3 review round 1: the keyboard opens
    /// what a click opens): Enter or Space either way, Right only to open, Left only to fold; null for any other key
    /// or entry (a node with nothing inside opens nothing).</summary>
    public static string? KeyToggles(ListEntry e, string key)
    {
        var (k, open, canOpen) = e switch
        {
            FixGroupEntry g => (g.Key, g.Open, true),
            FixCardEntry c => (c.Key, c.Open, true),
            CodeNodeEntry n => (n.Key, n.Open, n.CanOpen),
            _ => ((string?)null, false, false),
        };
        if (k is null || !canOpen)
            return null;
        return key switch
        {
            "Enter" or "Return" or "Space" => k,
            "Right" when !open => k,
            "Left" when open => k,
            _ => null,
        };
    }

    /// <summary>The keys to open so a row shows in a view (its group and card, or its document, chapter, section
    /// and rule): what "show this result" opens, so no row is ever out of reach.</summary>
    public static IReadOnlyList<string> PathTo(ResultViewsModel model, ResultsViewKind view, string rowId)
    {
        ArgumentNullException.ThrowIfNull(model);
        if (view == ResultsViewKind.WhatToFix)
        {
            foreach (var g in model.Fix)
            {
                if (!g.Rows.Any(r => r.Id == rowId))
                    continue;
                if (g.Kind is FixKind.Fails or FixKind.NotChecked or FixKind.Done)
                    return [GroupKey(g)];
                var card = g.Cards.First(c => c.Rows.Any(r => r.Id == rowId));
                return [GroupKey(g), CardKey(card)];
            }
            return [];
        }
        List<string>? Find(CodeNode n, string key)
        {
            if (n.Rows.Any(r => r.Id == rowId))
                return [key];
            for (var i = 0; i < n.Children.Count; i++)
                if (Find(n.Children[i], NodeKey(key, i)) is { } path)
                    return [key, .. path];
            return null;
        }
        for (var i = 0; i < model.Code.Count; i++)
            if (Find(model.Code[i], NodeKey("", i)) is { } path)
                return path;
        return [];
    }
}
