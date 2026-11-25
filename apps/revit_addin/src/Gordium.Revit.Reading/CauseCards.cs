using System.Text.Json;
using System.Text.RegularExpressions;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>What a cause asks of the architect, the worker's <c>kind</c> (design_checker/panel_data.py): fix the model
/// (or its marks), state a mark or a fact, measure by hand (Gordium doesn't read or measure this yet), or decide (a
/// flag rule, an open question, a reading to confirm). A kind the add-in doesn't know is <see cref="Decide"/>: a
/// person looks at it, never a button that claims to fix it.</summary>
public enum CauseKind { FixModel, Mark, MeasureByHand, Decide }

/// <summary>What a cause card's button does in Revit (CauseCards.Action).</summary>
public enum CardAction
{
    /// <summary>No button: the card names nothing the panel can select or open (its rows still open).</summary>
    None,
    /// <summary>Select its elements in Revit and zoom to them.</summary>
    Show,
    /// <summary>Select its elements and bring up Properties, the mark to set named.</summary>
    ShowAndProperties,
    /// <summary>Open Manage › Project Information, the mark to set named.</summary>
    ProjectInformation,
    /// <summary>Open the card on its rows: each to check by hand against the law's words.</summary>
    ByHand,
    /// <summary>Open the card on its rows and the question a person decides.</summary>
    Decide,
}

/// <summary>A room a cause names (the rooms with no route), as the worker names it, and why.</summary>
public sealed record CauseRoom(string Id, string Name, string? Why);

/// <summary>
/// One cause card of the worker's (a review or by-hand group's <c>causes[]</c>: one card per first cause, rows sharing
/// a cause on one card, so "5 rooms have no route to an exit" is one job, not 11 rows). Every word is the worker's.
/// </summary>
/// <param name="Key">The worker's key (rows sharing a key share the cause); the same across checks while the cause is.</param>
/// <param name="Kind">What it asks (an unknown kind: <see cref="CauseKind.Decide"/>).</param>
/// <param name="Words">The cause in the worker's words.</param>
/// <param name="Elements">The element ids it names (the rooms with no route), each once, in the worker's order.</param>
/// <param name="Items">The rows it holds, by id, each a row of this answer, in the worker's order.</param>
/// <param name="Rules">How many rules those rows are of (the worker's count), or null when it sends none.</param>
/// <param name="GroupKey">The worker group it is a card of.</param>
public sealed record CauseCard(string Key, CauseKind Kind, string Words, IReadOnlyList<string> Elements,
                               IReadOnlyList<string> Items, int? Rules, string GroupKey)
{
    /// <summary>The rooms it names, with why each, from its rows' own causes of the same key (the worker sends them
    /// there); empty when none.</summary>
    public IReadOnlyList<CauseRoom> Rooms { get; init; } = [];

    /// <summary>The interior description's (or the project's) fields a mark card needs the architect to state, the
    /// worker's <c>fields</c> (or its one <c>field</c>): "doors[].exit", "openings[].escape", "stairs", "facts.zone".
    /// The add-in names its mark from them (<see cref="CauseCards.MarksOf"/>); empty when the worker sends none.</summary>
    public IReadOnlyList<string> Fields { get; init; } = [];

    /// <summary>"11 rows · 7 rules": how many rows it holds (and rules, the worker's count), counted, never a figure.</summary>
    public string Count =>
        $"{Items.Count} row{(Items.Count == 1 ? "" : "s")}" + (Rules is { } n && n != Items.Count ? $" · {n} rule{(n == 1 ? "" : "s")}" : "");
}

/// <summary>
/// The "Fix these first" cards (docs/revit/ui_design_pass.md section 2.4, PR 6), Revit-free so they are tested: the
/// worker's cause cards in its order, at most three shown (the rest behind "+N more causes"), and what each card's
/// button does. Nothing here changes or makes a verdict: a card says the worker's words, opens its rows, selects its
/// elements, or opens Properties or Project Information; only Check again changes a verdict.
/// </summary>
public static class CauseCards
{
    /// <summary>How many cards are shown before "+N more causes": three, as the design says (a docked pane shows them
    /// with the first rows below).</summary>
    public const int Top = 3;

    /// <summary>Every cause card of the answer, in the worker's order: its review groups' and its check-by-hand
    /// groups' cards (<see cref="ResultList.PlaceOf"/>), as their groups come. A card's rows are only the answer's own
    /// rows (an id the answer doesn't have is left out); a card with none is left out; a key given twice is one card
    /// (its first). Anything not readable (not a list, a card that isn't an object, no key or words) is left out, never
    /// guessed at: the rows are all still in the list.</summary>
    public static IReadOnlyList<CauseCard> Read(CheckResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        var cards = new List<CauseCard>();
        var raw = result.Raw;
        if (raw.ValueKind != JsonValueKind.Object || !raw.TryGetProperty("view", out var view) || view.ValueKind != JsonValueKind.Object
            || !view.TryGetProperty("groups", out var groups) || groups.ValueKind != JsonValueKind.Array)
            return cards;
        var rows = result.Items.ToDictionary(i => i.Id, StringComparer.Ordinal);
        var keys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var g in groups.EnumerateArray())
        {
            if (g.ValueKind != JsonValueKind.Object || ResultRows.Text(g, "key") is not { } groupKey
                || ResultList.PlaceOf(groupKey) is not (ListSection.Review or ListSection.ByHand)
                || !g.TryGetProperty("causes", out var causes) || causes.ValueKind != JsonValueKind.Array)
                continue;
            foreach (var c in causes.EnumerateArray())
            {
                if (c.ValueKind != JsonValueKind.Object || ResultRows.Text(c, "key") is not { } key
                    || ResultRows.Text(c, "words") is not { } words || keys.Contains(key))
                    continue;
                var items = Strings(c, "items").Where(rows.ContainsKey).ToList();
                if (items.Count == 0)
                    continue;
                keys.Add(key);
                int? rules = c.TryGetProperty("rules", out var r) && r.ValueKind == JsonValueKind.Number && r.TryGetInt32(out var n) && n > 0 ? n : null;
                cards.Add(new CauseCard(key, KindOf(ResultRows.Text(c, "kind")), words, Strings(c, "elements"), items, rules, groupKey)
                {
                    Rooms = RoomsOf(key, items.Select(id => rows[id].Raw)),
                    Fields = FieldsOf(c),
                });
            }
        }
        return cards;
    }

    /// <summary>The worker's kind word as a <see cref="CauseKind"/>; any other word (or none) is Decide.</summary>
    public static CauseKind KindOf(string? word) => word switch
    {
        "fix_model" => CauseKind.FixModel,
        "mark" => CauseKind.Mark,
        "measure_by_hand" => CauseKind.MeasureByHand,
        _ => CauseKind.Decide,
    };

    /// <summary>The cards shown: the first <see cref="Top"/> in the worker's order, or every one once "+N more causes"
    /// is opened (<paramref name="all"/>).</summary>
    public static IReadOnlyList<CauseCard> Shown(IReadOnlyList<CauseCard> cards, bool all)
    {
        ArgumentNullException.ThrowIfNull(cards);
        return all ? cards : cards.Take(Top).ToList();
    }

    /// <summary>"+12 more causes", or null when every card is shown.</summary>
    public static string? MoreWords(IReadOnlyList<CauseCard> cards)
    {
        ArgumentNullException.ThrowIfNull(cards);
        var more = cards.Count - Top;
        return more <= 0 ? null : $"+{more} more cause{(more == 1 ? "" : "s")}";
    }

    /// <summary>The card's elements the project has (it had them at the check: their names were read), each once.</summary>
    public static IReadOnlyList<string> InModel(CauseCard card, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(card);
        return card.Elements.Distinct(StringComparer.Ordinal).Where(uid => labels?.ContainsKey(uid) == true).ToList();
    }

    /// <summary>The elements a card's Show (or Show and open Properties) sends to Revit: exactly the ones its button
    /// promised (<see cref="InModel"/>: named when the check read the project), never the worker's raw list, which can
    /// hold a measured part's own id ("&lt;corridor&gt; (dead end 2)") that is no element: those would be said "not in this
    /// model now", as if deleted. An element deleted since the check still has its name, so a real deletion is still said.</summary>
    public static IReadOnlyList<string> ShowIds(CauseCard card, IReadOnlyDictionary<string, string>? labels) => InModel(card, labels);

    /// <summary>What the card's button does: fix the model, Show its elements (select and zoom); a mark, bring up
    /// Properties on its elements with the mark named, or Project Information when that is where every mark it names
    /// is (a project fact), or Show alone when the card names no mark to set (nothing to set in Properties); measure by
    /// hand and decide open the card on its rows. No button when there is nothing in the project to select or open
    /// (an interior drawing's cause with no element id; a fact no Gordium mark holds).</summary>
    public static CardAction Action(CauseCard card, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(card);
        var shown = InModel(card, labels).Count > 0;
        switch (card.Kind)
        {
            case CauseKind.FixModel:
                return shown ? CardAction.Show : CardAction.None;
            case CauseKind.Mark:
                var marks = MarksOf(card);
                if (marks.Count > 0 && (marks.All(OnProjectInformationOnly) || FactsFed(card) || FieldsAreFacts(card)))
                    return CardAction.ProjectInformation;      // a project fact's mark is on Project Information
                if (!shown)
                    return CardAction.None;
                return marks.Count > 0 ? CardAction.ShowAndProperties : CardAction.Show;
            case CauseKind.MeasureByHand:
                return CardAction.ByHand;
            default:
                return CardAction.Decide;
        }
    }

    /// <summary>The button's words for an action ("" for none).</summary>
    public static string ButtonWords(CardAction action) => action switch
    {
        CardAction.Show => "Show",
        CardAction.ShowAndProperties => "Show and open Properties",
        CardAction.ProjectInformation => "Open Project Information",
        CardAction.ByHand => "Check by hand",
        CardAction.Decide => "Decide",
        _ => "",
    };

    /// <summary>The line under a card saying what to set where, from the marks it names: "Set Gordium: Exit door in
    /// Properties" or "Set Gordium: Stories on Project Information"; for a mark card naming none, that it names none
    /// (never a mark guessed); for a card to check by hand or decide, what that means; null for fix the model.</summary>
    public static string? Note(CauseCard card, IReadOnlyDictionary<string, string>? labels)
    {
        ArgumentNullException.ThrowIfNull(card);
        var action = Action(card, labels);
        var marks = MarksOf(card);
        var names = string.Join(" and ", marks.Select(m => m.Name));
        return card.Kind switch
        {
            CauseKind.Mark when action == CardAction.ProjectInformation => $"Set {names} on Project Information.",
            CauseKind.Mark when marks.Count > 0 => $"Set {names} in Properties" + OnType(marks) +
                (action == CardAction.ShowAndProperties ? "." : ", on the element the card names (the card has none to select)."),
            CauseKind.Mark => "No Gordium mark is named for this: do what the card says, or decide it by hand.",
            CauseKind.MeasureByHand => "Gordium doesn't read or measure this yet: check each row by hand against the law's words.",
            CauseKind.Decide => "A person decides: open each row, read the law's words, and decide.",
            _ => null,
        };
    }

    /// <summary>What the panel says once Properties is open on the card's elements (Revit selected <paramref name="selected"/>).</summary>
    public static string AfterProperties(CauseCard card, int selected)
    {
        ArgumentNullException.ThrowIfNull(card);
        var marks = MarksOf(card);
        var names = string.Join(" and ", marks.Select(m => m.Name));
        return $"Selected {selected} element{(selected == 1 ? "" : "s")}; Properties is open: set {names} there{OnType(marks)}, then Check again.";
    }

    /// <summary>Where a type's mark is set: the instance Properties palette doesn't show it, Edit Type does, once for each
    /// type (door leaves review round 1: the card said "set Gordium: Leaves there", which Properties alone doesn't
    /// hold). Edit Type is greyed with several types selected (round 2), and picking a type in Properties' Type Selector
    /// would retype every selected element (round 3), so the words name one element of a type, or the type's own
    /// Type Properties in the Project Browser; "" when every mark is the element's own.</summary>
    internal static string OnType(IReadOnlyList<MarkDefinition> marks) =>
        marks.Any(m => m.Binding == MarkBinding.Type)
            ? " (a type's mark: select one element of a type and click Edit Type, or right-click the type in the Project " +
              "Browser and choose Type Properties; once for each type)" : "";

    /// <summary>The Gordium marks the card names, each once, in Gordium's list order. When the worker names the
    /// fields the card needs (<see cref="CauseCard.Fields"/>): the mark that feeds each one exactly (doors[].exit:
    /// Gordium: Exit door; stairs: Gordium: These are all the stairs; facts.zone: Gordium: Zone), only when every
    /// field has one, else none (a field no mark feeds: never a mark guessed). With no fields (an older worker), as
    /// before: a mark named in its words ("Gordium: Exit door"); the mark an interior-drawing field it names in
    /// back-quotes feeds (<c>`exit`</c>: doors[].exit, Gordium: Exit door), when exactly one mark does; for a project
    /// fact's key (<c>fact:stories</c>, <c>facts:a,b</c>), the mark each fact is fed by, only when every one has one.
    /// Never a mark that isn't one of Gordium's (<see cref="Marks.All"/>).</summary>
    public static IReadOnlyList<MarkDefinition> MarksOf(CauseCard card)
    {
        ArgumentNullException.ThrowIfNull(card);
        if (card.Fields.Count > 0)
        {
            var byField = card.Fields.Select(f => Marks.All.FirstOrDefault(m => Fields(m).Contains(f))).ToList();
            return byField.All(m => m is not null) ? Marks.All.Where(byField.Contains).ToList() : [];
        }
        var found = Marks.All.Where(m => card.Words.Contains(m.Name, StringComparison.Ordinal)).ToList();
        // a shorter name inside a longer one ("Gordium: Exit" in "Gordium: Exit door") is the longer one's
        found = found.Where(m => !found.Any(o => o != m && o.Name.Contains(m.Name, StringComparison.Ordinal))).ToList();
        foreach (Match f in Field.Matches(card.Words))
        {
            var fed = Marks.All.Where(m => Fields(m).Any(x => x.EndsWith("." + f.Groups[1].Value, StringComparison.Ordinal))).ToList();
            if (fed.Count == 1 && !found.Contains(fed[0]))
                found.Add(fed[0]);
        }
        if (Facts(card.Key) is { Count: > 0 } facts)
        {
            var fed = facts.Select(f => Marks.All.FirstOrDefault(m => Fields(m).Contains("facts." + f))).ToList();
            if (fed.All(m => m is not null))
                found.AddRange(fed.Where(m => !found.Contains(m!)).Distinct().Select(m => m!));
        }
        return Marks.All.Where(found.Contains).ToList();
    }

    // an interior-drawing field the worker names in back-quotes: "(`exit`: true or false)"
    private static readonly Regex Field = new(@"`([a-z_]+)`", RegexOptions.CultureInvariant);

    /// <summary>The description fields a mark feeds, from its Feeds ("openings[].escape", "facts.use (on Project
    /// Information), rooms[].use (on a Room)" → facts.use, rooms[].use).</summary>
    private static IEnumerable<string> Fields(MarkDefinition m) =>
        m.Feeds.Split(", ").Select(p => p.Split(' ')[0]).Where(p => p.Length > 0);

    /// <summary>A project fact's key's facts: <c>fact:stories</c> → [stories]; <c>facts:a,b</c> → [a, b]; else none.</summary>
    private static List<string> Facts(string key)
    {
        var at = key.IndexOf(':');
        if (at < 0 || key[..at] is not ("fact" or "facts"))
            return [];
        return key[(at + 1)..].Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToList();
    }

    private static bool OnProjectInformationOnly(MarkDefinition m) => m.Categories is [Marks.ProjectInformation];

    /// <summary>Whether every field the card names is a project fact's (<c>facts.use</c>): set on Project Information,
    /// as <see cref="FactsFed"/>.</summary>
    private static bool FieldsAreFacts(CauseCard card) =>
        card.Fields.Count > 0 && card.Fields.All(f => f.StartsWith("facts.", StringComparison.Ordinal));

    /// <summary>The worker's <c>fields</c> (text, each once), or its one <c>field</c>; none when it sends neither.</summary>
    private static List<string> FieldsOf(JsonElement c)
    {
        var fields = Strings(c, "fields");
        if (fields.Count == 0 && ResultRows.Text(c, "field") is { Length: > 0 } one)
            fields.Add(one);
        return fields;
    }

    /// <summary>Whether the card is a project fact's (<c>fact:</c>/<c>facts:</c>) whose every fact a mark feeds (as
    /// <c>facts.use</c> by Gordium: Use, which is on Project Information and on Rooms): set on Project Information.</summary>
    private static bool FactsFed(CauseCard card) =>
        Facts(card.Key) is { Count: > 0 } facts && facts.All(f => Marks.All.Any(m => Fields(m).Contains("facts." + f)));

    /// <summary>The rooms a card names, from its rows' own causes of its key (<c>rooms[]</c>: id, name, why), each once,
    /// over all its rows (a joined card's rows may each name some).</summary>
    private static List<CauseRoom> RoomsOf(string key, IEnumerable<JsonElement> rows)
    {
        var rooms = new List<CauseRoom>();
        foreach (var raw in rows)
        {
            if (raw.ValueKind != JsonValueKind.Object || !raw.TryGetProperty("causes", out var cs) || cs.ValueKind != JsonValueKind.Array)
                continue;
            foreach (var c in cs.EnumerateArray())
                if (c.ValueKind == JsonValueKind.Object && ResultRows.Text(c, "key") == key
                    && c.TryGetProperty("rooms", out var rs) && rs.ValueKind == JsonValueKind.Array)
                    foreach (var r in rs.EnumerateArray())
                        if (r.ValueKind == JsonValueKind.Object && ResultRows.Text(r, "id") is { } id && rooms.All(x => x.Id != id))
                            rooms.Add(new CauseRoom(id, ResultRows.Text(r, "name") ?? id, ResultRows.Text(r, "why")));
        }
        return rooms;
    }

    private static List<string> Strings(JsonElement e, string name)
    {
        var list = new List<string>();
        if (e.TryGetProperty(name, out var a) && a.ValueKind == JsonValueKind.Array)
            foreach (var x in a.EnumerateArray())
                if (x.ValueKind == JsonValueKind.String && x.GetString() is { Length: > 0 } s && !list.Contains(s))
                    list.Add(s);
        return list;
    }
}
