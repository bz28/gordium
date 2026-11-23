using Gordium.Revit.Reading;

namespace Gordium.Revit.PanePrototype.Proposed;

/// <summary>PROTOTYPE: one card of the proposed "Fix these first": the worker's cause cards that share one fix (one
/// action in Revit on one kind of thing), with every member kept, so every row stays reachable.</summary>
/// <param name="Key">Stable: the action and the family ("pi", "fix:stair", "marks:Gordium: Exit door").</param>
/// <param name="Title">What to do, in the add-in's words when it joins several cards; the worker's own words for one.</param>
/// <param name="Action">The one button (the members' shared action).</param>
/// <param name="Members">The worker's cards it holds, in the worker's order.</param>
/// <param name="Tier">0 a fix in Revit with a field or elements to go to; 1 a fix in the model with nothing to select;
/// 2 measure by hand; 3 a person decides (or Gordium has no field for it yet).</param>
internal sealed record CardGroup(string Key, string Title, CardAction Action, IReadOnlyList<CauseCard> Members, int Tier, int FirstIndex)
{
    /// <summary>Every row its members hold, each once, in the members' order: the rows this one fix is for.</summary>
    public IReadOnlyList<string> Rows { get; } = Members.SelectMany(m => m.Items).Distinct(StringComparer.Ordinal).ToList();

    /// <summary>Every element its members name, each once.</summary>
    public IReadOnlyList<string> Elements { get; } = Members.SelectMany(m => m.Elements).Distinct(StringComparer.Ordinal).ToList();

    /// <summary>"6 results" (and "· 2 facts" when it joins several cards): counted, never a figure.</summary>
    public string Count => $"{Rows.Count} result{(Rows.Count == 1 ? "" : "s")} waiting on this" +
                           (Members.Count > 1 ? $" · {Members.Count} {Noun}" : "");

    internal string Noun => Key switch
    {
        "pi" or "nofield" => "facts",
        _ when Key.StartsWith("byhand", StringComparison.Ordinal) => "kinds of part",
        _ => "causes",
    };
}

/// <summary>
/// PROTOTYPE (the proposed "Fewer, ranked cards"; would move to Gordium.Revit.Reading with tests when approved): the
/// worker's cause cards joined where they share one fix, then ranked by what one action clears. Nothing here makes or
/// changes a verdict: a group's rows are exactly its members' rows, every card is in exactly one group, and the
/// order is a pure function of the answer (no clock, no hash order).
/// </summary>
internal static class CardGroups
{
    internal const int Top = 3;

    internal static IReadOnlyList<CardGroup> Of(IReadOnlyList<CauseCard> cards, IReadOnlyDictionary<string, string>? labels)
    {
        var byKey = new Dictionary<string, List<(CauseCard Card, int Index)>>(StringComparer.Ordinal);
        var order = new List<string>();
        for (var i = 0; i < cards.Count; i++)
        {
            var key = KeyOf(cards[i], labels);
            if (!byKey.TryGetValue(key, out var list))
            {
                byKey[key] = list = [];
                order.Add(key);
            }
            list.Add((cards[i], i));
        }
        var groups = order.Select(k =>
        {
            var members = byKey[k];
            var action = ActionOf(k, members[0].Card, labels);
            return new CardGroup(k, Title(k, members.Select(m => m.Card).ToList(), labels), action, members.Select(m => m.Card).ToList(),
                                 TierOf(k, action), members[0].Index);
        });
        // ranked: what one action in Revit clears first, then the most results it is for, then the worker's order
        return groups.OrderBy(g => g.Tier).ThenByDescending(g => g.Rows.Count).ThenBy(g => g.FirstIndex).ToList();
    }

    /// <summary>The fix a card shares with others: where it is done and on what kind of thing.</summary>
    internal static string KeyOf(CauseCard card, IReadOnlyDictionary<string, string>? labels)
    {
        var action = CauseCards.Action(card, labels);
        var marks = CauseCards.MarksOf(card);
        switch (card.Kind)
        {
            case CauseKind.Mark when action == CardAction.ProjectInformation:
                return "pi";                                                     // every Project Information field: one dialog
            case CauseKind.Mark when marks.Count > 0:
                return "marks:" + string.Join("+", marks.Select(m => m.Name));    // the same mark on many elements
            case CauseKind.Mark:
                return "nofield";                                                // no Gordium field holds it yet
            case CauseKind.FixModel:
                var parts = card.Key.Split(':');
                return parts.Length >= 3 && parts[0] == "model" ? "fix:" + parts[1] : "card:" + card.Key;
            case CauseKind.MeasureByHand:
                return "byhand:" + card.GroupKey;
            default:
                return "card:" + card.Key;                                       // a decision is its own
        }
    }

    private static CardAction ActionOf(string key, CauseCard first, IReadOnlyDictionary<string, string>? labels) =>
        key == "nofield" ? CardAction.Decide : CauseCards.Action(first, labels);   // nofield today: no button at all (a dead end)

    private static int TierOf(string key, CardAction action) => key switch
    {
        "nofield" => 3,
        _ => action switch
        {
            CardAction.ProjectInformation or CardAction.ShowAndProperties or CardAction.Show => 0,
            CardAction.None => 1,
            CardAction.ByHand => 2,
            _ => 3,
        },
    };

    /// <summary>A joined card's title (the add-in's words, naming the fix and how many causes it joins); one card
    /// keeps the worker's words.</summary>
    private static string Title(string key, IReadOnlyList<CauseCard> members, IReadOnlyDictionary<string, string>? labels)
    {
        if (members.Count == 1)
            return Capital(members[0].Words);
        var n = members.Count;
        if (key == "pi")
            return $"Set {n} facts on Project Information";
        if (key == "nofield")
            return $"{n} facts Gordium has no field for yet";
        if (key.StartsWith("marks:", StringComparison.Ordinal))
            return $"Set {key[6..].Replace("+", " and ")} on {members.SelectMany(m => m.Elements).Distinct().Count()} elements";
        if (key.StartsWith("byhand:", StringComparison.Ordinal))
            return $"Measure by hand: {n} kinds of part Gordium doesn't read yet";
        if (key.StartsWith("fix:", StringComparison.Ordinal))
            return $"{Thing(key[4..])}: {n} things Gordium couldn't measure from the model";
        return Capital(members[0].Words);
    }

    private static string Thing(string kind) => kind switch
    {
        "emergency_escape_opening" => "Escape windows",
        "stair" => "Stairs",
        "egress_door" => "Egress doors",
        "guard" => "Guards",
        _ => Capital(kind.Replace('_', ' ')),
    };

    internal static string Capital(string s) => s.Length == 0 ? s : char.ToUpperInvariant(s[0]) + s[1..];

    /// <summary>The one button's words, one per kind of action, the same everywhere in the pane.</summary>
    internal static string ButtonWords(CardAction action) => action switch
    {
        CardAction.Show => "Show",
        CardAction.ShowAndProperties => "Set in Properties",
        CardAction.ProjectInformation => "Open Project Information",
        CardAction.ByHand => "Measure by hand",
        CardAction.Decide => "Decide",
        _ => "",
    };

    /// <summary>The line under a group: where the fix is made, in the pane's one vocabulary.</summary>
    internal static string? Note(CardGroup g, IReadOnlyDictionary<string, string>? labels)
    {
        var marks = g.Members.SelectMany(CauseCards.MarksOf).Distinct().Select(m => m.Name).ToList();
        return g.Key switch
        {
            "pi" => $"Set {Names(marks)} in Manage › Project Information, then Check again.",
            "nofield" => "Gordium has no field for these in Revit yet: until it does, each result needs review. Decide them by hand.",
            _ when g.Action == CardAction.ShowAndProperties => $"Set {Names(marks)} in Properties on the elements Show selects, then Check again.",
            _ when g.Action == CardAction.Show => "Fix the model where Show takes you, then Check again.",
            _ when g.Action == CardAction.None => "Gordium couldn't read these from the model. Check how they are drawn, or measure them by hand.",
            _ when g.Action == CardAction.ByHand => "Gordium doesn't read these from the model yet: measure each by hand against the law's words.",
            _ => "A person decides: open each result, read the law's words, and decide.",
        };
    }

    private static string Names(IReadOnlyList<string> names) =>
        names.Count == 0 ? "the facts" : names.Count <= 2 ? string.Join(" and ", names) : string.Join(", ", names.Take(names.Count - 1)) + " and " + names[^1];
}
