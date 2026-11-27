using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>
/// One card of "Start here" (docs/revit/ui_design_pass.md, the intuitive pane, change 4; Ben, 2026-11-23): the
/// worker's cause cards that share one fix (one action in Revit on one kind of thing: every Project Information fact,
/// the same mark on many elements, one kind of part Gordium couldn't measure, the facts Gordium has no field for), with
/// every card it joins kept, so every result stays reachable from it.
/// </summary>
/// <param name="Key">Stable across checks while the fix is: "pi", "nofield", "marks:Gordium: Exit door", "fix:stair",
/// "byhand:&lt;group&gt;" or "card:&lt;the worker's key&gt;".</param>
/// <param name="Title">What to do: the worker's own words for a fix of one card; for a joined fix, the add-in's words
/// naming the fix and how many it joins ("Set 2 facts on Project Information: the stairs list and the guards and handrails list").</param>
/// <param name="Action">Its one button (the cards' shared action; <see cref="CardAction.Decide"/> for facts with no field).</param>
/// <param name="Members">The worker's cards it joins, in the worker's order.</param>
/// <param name="Tier">Where the fix is made: 0 in Revit, with a field or elements to go to; 1 in the model, with
/// nothing to select; 2 by hand; 3 a person decides (or Gordium has no field for it yet).</param>
/// <param name="FirstIndex">Its first card's place in the worker's order (the last tie-break).</param>
public sealed record Fix(string Key, string Title, CardAction Action, IReadOnlyList<CauseCard> Members, int Tier, int FirstIndex)
{
    /// <summary>Every result its cards hold, each once, in the cards' order: exactly the results this fix is for.</summary>
    public IReadOnlyList<string> Rows { get; } = Members.SelectMany(m => m.Items).Distinct(StringComparer.Ordinal).ToList();

    /// <summary>Every element its cards name, each once, in their order.</summary>
    public IReadOnlyList<string> Elements { get; } = Members.SelectMany(m => m.Elements).Distinct(StringComparer.Ordinal).ToList();

    /// <summary>What it joins, in words: "facts", "kinds of part", "causes" (the key's family, before its "@action").</summary>
    public string Noun => Key switch
    {
        "pi" or "nofield" => "facts",
        _ when Key.StartsWith("byhand:", StringComparison.Ordinal) => "kinds of part",
        _ => "causes",
    };

    /// <summary>How many things it joins: the facts to set for a Project Information fix (its cards' marks, each once:
    /// one card can ask two, the stream's yes and its distance), else its cards.</summary>
    public int Joined => Key == "pi" && Members.SelectMany(CauseCards.MarksOf).Distinct().Count() is var n and > 0 ? n : Members.Count;

    /// <summary>The opened fix's overline over its cards: "The 11 causes, in Gordium's checker's words"; for a
    /// Project Information fix whose cards ask more facts than there are cards, both counts ("The 6 causes asking 9
    /// facts, …"), so it never claims a number of facts the title and count don't.</summary>
    public string MembersWords =>
        (Noun == "facts" && Joined != Members.Count ? $"The {Members.Count} causes asking {Joined} facts" : $"The {Members.Count} {Noun}")
        + ", in Gordium's checker's words";

    /// <summary>"28 results waiting on this · 11 causes": counted, never a figure.</summary>
    public string Count => $"{PaneWords.Results(Rows.Count)} waiting on this" + (Joined > 1 ? $" · {Joined} {Noun}" : "");
}

/// <summary>
/// The "Start here" fixes, Revit-free so they are tested (the intuitive pane, change 4): the worker's cause cards
/// (<see cref="CauseCards.Read"/>) joined where they share one fix, then ranked: what can be fixed in Revit first, then
/// the most results one fix is for, then the worker's order. Nothing here makes or changes a verdict: a fix's results
/// are exactly its cards' results, every card is in exactly one fix, and the order is a pure function of the answer
/// (no clock, no hash order), so the same answer always ranks the same.
/// </summary>
public static class Fixes
{
    /// <summary>How many fixes are shown before "+N more fixes".</summary>
    public const int Top = 3;

    /// <summary>The fixes of these cards (in the worker's order), ranked.</summary>
    public static IReadOnlyList<Fix> Of(IReadOnlyList<CauseCard> cards, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(cards);
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
        return order.Select(k =>
            {
                var members = byKey[k].Select(m => m.Card).ToList();
                // every member has this action (it is part of the key): the fix's button is every card's own
                var action = k == "nofield" ? CardAction.Decide : CauseCards.Action(members[0], labels);
                return new Fix(k, Title(k, members, labels), action, members, TierOf(k, action), byKey[k][0].Index);
            })
            .OrderBy(f => f.Tier).ThenByDescending(f => f.Rows.Count).ThenBy(f => f.FirstIndex).ToList();
    }

    /// <summary>The fix a card shares with others: where it is made, on what kind of thing, and with which button (the
    /// action is part of the key, so a joined fix's button, tier and words hold for every card it joins: a card with
    /// elements to Show never joins one with nothing to select). "pi" and "nofield" have one button whatever the card
    /// (Open Project Information; Decide), so their keys carry none.</summary>
    public static string KeyOf(CauseCard card, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(card);
        var action = CauseCards.Action(card, labels);
        var family = Family(card, action);
        return family is "pi" or "nofield" ? family : $"{family}@{action}";
    }

    private static string Family(CauseCard card, CardAction action)
    {
        var marks = CauseCards.MarksOf(card);
        switch (card.Kind)
        {
            case CauseKind.Mark when action == CardAction.ProjectInformation:
                return "pi";                                                     // every Project Information fact: one dialog
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

    private static int TierOf(string key, CardAction action) => key == "nofield" ? 3 : action switch
    {
        CardAction.ProjectInformation or CardAction.ShowAndProperties or CardAction.Show => 0,
        CardAction.None => 1,
        CardAction.ByHand => 2,
        _ => 3,
    };

    private static string Title(string key, IReadOnlyList<CauseCard> members, IReadOnlyDictionary<string, string>? labels)
    {
        if (members.Count == 1)
            return PaneWords.Capital(members[0].Words);
        var n = members.Count;
        if (key == "pi")
        {
            var marks = members.SelectMany(CauseCards.MarksOf).Distinct().Select(m => Short(m.Name)).ToList();
            return $"Set {(marks.Count > 0 ? marks.Count : n)} facts on Project Information" + (marks.Count > 0 ? ": " + PaneWords.And(marks) : "");
        }
        if (key == "nofield")
            return $"{n} facts Gordium has no field for yet";
        var family = key.Split('@')[0];
        if (family.StartsWith("marks:", StringComparison.Ordinal))
        {
            // the elements Set in Properties selects (the same set: ShowIds), or none to select
            var shown = members.SelectMany(m => CauseCards.ShowIds(m, labels)).Distinct(StringComparer.Ordinal).Count();
            var marks = PaneWords.And(family[6..].Split('+'));
            return shown > 0 ? $"Set {marks} on {shown} element{(shown == 1 ? "" : "s")}" : $"Set {marks}: {n} causes with no element to select";
        }
        if (family.StartsWith("byhand:", StringComparison.Ordinal))
            return $"Measure by hand: {n} kinds of part Gordium doesn't read yet";
        if (family.StartsWith("fix:", StringComparison.Ordinal))
            return $"{Thing(family[4..])}: {n} things Gordium couldn't measure from the model";
        return PaneWords.Capital(members[0].Words);
    }

    /// <summary>A mark's name as a title says it: "Gordium: These are all the stairs" is "the stairs list";
    /// "Gordium: Stories" is "stories".</summary>
    public static string Short(string mark)
    {
        ArgumentNullException.ThrowIfNull(mark);
        var name = mark.StartsWith("Gordium: ", StringComparison.Ordinal) ? mark[9..] : mark;
        const string all = "These are all the ";
        if (name.StartsWith(all, StringComparison.Ordinal))
            return $"the {name[all.Length..]} list";
        return name.Length == 0 ? name : char.ToLowerInvariant(name[0]) + name[1..];
    }

    private static string Thing(string kind) => kind switch
    {
        "emergency_escape_opening" => "Escape windows",
        "stair" => "Stairs",
        "egress_door" => "Egress doors",
        "guard" => "Guards",
        _ => PaneWords.Capital(kind.Replace('_', ' ')),
    };

    /// <summary>The elements a fix's Show (or Set in Properties) sends to Revit: its cards' elements the project has
    /// (named when the check read it: CauseCards.ShowIds, over every card it joins), each once.</summary>
    public static IReadOnlyList<string> ShowIds(Fix fix, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(fix);
        return fix.Members.SelectMany(m => CauseCards.ShowIds(m, labels)).Distinct(StringComparer.Ordinal).ToList();
    }

    /// <summary>The one button's words, one per kind of action, the same everywhere in the pane.</summary>
    public static string ButtonWords(CardAction action) => action switch
    {
        CardAction.Show => "Show",
        CardAction.ShowAndProperties => "Set in Properties",
        CardAction.ProjectInformation => "Open Project Information",
        CardAction.ByHand => "Measure by hand",
        CardAction.Decide => "Decide",
        _ => "",
    };

    /// <summary>The line under a fix: where it is made, naming the exact Gordium fields to set.</summary>
    public static string Note(Fix fix)
    {
        ArgumentNullException.ThrowIfNull(fix);
        var marks = fix.Members.SelectMany(CauseCards.MarksOf).Distinct().Select(m => m.Name).ToList();
        return fix.Key switch
        {
            "pi" => $"In Manage › Project Information, set {(marks.Count == 0 ? "the facts" : PaneWords.And(marks))}, then Check again.",
            "nofield" => "Gordium has no field for these in Revit yet: until it does, each result needs review. Decide them by hand.",
            _ when fix.Action == CardAction.ShowAndProperties => $"Set {PaneWords.And(marks)} in Properties on the elements Show selects{CauseCards.OnType(fix.Members.SelectMany(CauseCards.MarksOf).Distinct().ToList())}, then Check again.",
            _ when fix.Action == CardAction.Show => "Fix the model where Show takes you, then Check again.",
            _ when fix.Action == CardAction.None => "Gordium couldn't read these from the model. Check how they are drawn, or measure them by hand.",
            _ when fix.Action == CardAction.ByHand => "Gordium doesn't read these from the model yet: measure each by hand against the law's words.",
            _ => "A person decides: open each result, read the law's words, and decide.",
        };
    }

    /// <summary>"8 fixes cover the 130 results that need review or a hand check. Start with these 3: what you can fix
    /// in Revit comes first."</summary>
    public static string Intro(IReadOnlyList<Fix> fixes)
    {
        ArgumentNullException.ThrowIfNull(fixes);
        var rows = fixes.SelectMany(f => f.Rows).Distinct(StringComparer.Ordinal).Count();
        return $"{fixes.Count} fix{(fixes.Count == 1 ? "" : "es")} cover the {PaneWords.Results(rows)} that need review or a hand check. " +
               $"Start with {(fixes.Count <= Top ? "these" : $"these {Top}")}: what you can fix in Revit comes first.";
    }

    /// <summary>The fixes shown: the first <see cref="Top"/>, or every one once "+N more fixes" is opened.</summary>
    public static IReadOnlyList<Fix> Shown(IReadOnlyList<Fix> fixes, bool all)
    {
        ArgumentNullException.ThrowIfNull(fixes);
        return all ? fixes : fixes.Take(Top).ToList();
    }

    /// <summary>"+5 more fixes (76 results)", or null when every fix is shown.</summary>
    public static string? MoreWords(IReadOnlyList<Fix> fixes)
    {
        ArgumentNullException.ThrowIfNull(fixes);
        var more = fixes.Count - Top;
        if (more <= 0)
            return null;
        var rows = fixes.Skip(Top).SelectMany(f => f.Rows).Distinct(StringComparer.Ordinal).Count();
        return $"+{more} more fix{(more == 1 ? "" : "es")} ({PaneWords.Results(rows)})";
    }

    /// <summary>"Looked at: 0 of 8 fixes · 0 of 141 results" (the architect's own ticks, never a verdict).</summary>
    public static string Progress(LookedAt looked, IReadOnlyList<Fix> fixes, IReadOnlyList<ListRow> placed)
    {
        ArgumentNullException.ThrowIfNull(looked);
        ArgumentNullException.ThrowIfNull(fixes);
        ArgumentNullException.ThrowIfNull(placed);
        return $"Looked at: {fixes.Count(f => looked.Card(f.Key))} of {fixes.Count} fix{(fixes.Count == 1 ? "" : "es")} · " +
               $"{looked.Rows.Count} of {PaneWords.Results(placed.Count(LookedAt.Tickable))}";
    }

    /// <summary>The fix a result waits on (the first that holds it) and its number in the ranking, or null.</summary>
    public static (Fix Fix, int Number)? For(IReadOnlyList<Fix> fixes, string rowId)
    {
        ArgumentNullException.ThrowIfNull(fixes);
        for (var i = 0; i < fixes.Count; i++)
            if (fixes[i].Rows.Contains(rowId, StringComparer.Ordinal))
                return (fixes[i], i + 1);
        return null;
    }

    /// <summary>"What to do" step 1 of a result's detail, when it is the generic step and the result waits on a fix:
    /// the fix's number and title, then where it is made (its button is the fix's own).</summary>
    public static DetailStep? Step(ResultDetail detail, IReadOnlyList<Fix> fixes, DetailStep step)
    {
        ArgumentNullException.ThrowIfNull(detail);
        ArgumentNullException.ThrowIfNull(step);
        if (!ResultDetail.IsGenericStep(step) || For(fixes, detail.Id) is not { } f)
            return null;
        return new DetailStep($"Fix {f.Number}: {f.Fix.Title}. {Note(f.Fix)}", DetailAction.None);
    }
}
