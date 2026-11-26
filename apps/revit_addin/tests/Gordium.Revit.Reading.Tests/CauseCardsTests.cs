using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>UI PR 6 (docs/revit/ui_design_pass.md section 4 row 6), Revit-free: the cause cards (the worker's, in its
/// order, three shown, each card's button), the "looked at" ticks (never a verdict; carried to a new check only where
/// nothing changed), what changed between two checks (by row id, the worker's verdicts only; a stale answer not
/// compared), the measured-vs-limit bar (only from the worker's two lengths), and failures sorted by how_far lengths.</summary>
public sealed class CauseCardsTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static readonly string Here = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests");

    private static CheckResult Odyssey() => Parse(JsonNode.Parse(File.ReadAllText(Path.Combine(Here, "answers", "children_odyssey_check_answer.json"),
                                                                                     Encoding.UTF8))!["result"]!.AsObject());

    private static CheckResult Parse(JsonObject result) =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(result.ToJsonString()).RootElement, About));

    private static JsonObject Item(string id, string status = "needs_review", string? name = null, string? reason = "r", string? howFar = null,
                                   JsonObject? limitLength = null) => new()
    {
        ["id"] = id, ["name"] = name ?? id, ["group"] = "law", ["status"] = status, ["reason"] = reason, ["objects"] = new JsonArray(),
        ["how_far"] = howFar, ["limit_length"] = limitLength,
    };

    private static JsonObject Card(string key, string kind, string words, string[] items, string[]? elements = null, int? rules = null) => new()
    {
        ["key"] = key, ["kind"] = kind, ["words"] = words, ["items"] = new JsonArray(items.Select(i => (JsonNode)i).ToArray()),
        ["elements"] = new JsonArray((elements ?? []).Select(i => (JsonNode)i).ToArray()), ["rules"] = rules,
    };

    private static JsonObject Group(string key, string[] items, params JsonObject[] cards) => new()
    {
        ["key"] = key, ["title"] = key, ["items"] = new JsonArray(items.Select(i => (JsonNode)i).ToArray()),
        ["causes"] = new JsonArray(cards.Select(c => (JsonNode)c).ToArray()),
    };

    private static JsonObject Result(JsonArray items, params JsonObject[] groups) => new()
    {
        ["view"] = new JsonObject
        {
            ["items"] = items, ["summary"] = "s", ["state"] = "needs_review", ["groups"] = new JsonArray(groups.Select(g => (JsonNode)g).ToArray()),
        },
        ["report_error"] = null,
    };

    private static ResultModel Model(CheckResult r) => ResultRows.Build(r, null, [], null);

    // ---- the cause cards ------------------------------------------------------------------------------------

    /// <summary>The Odyssey: the worker's 14 review cards then its 1 by-hand card, in its order, every one with its
    /// rows; the first the 5 rooms with no route (11 rows, 7 rules), naming the 5 rooms of eval_comparison.yaml.</summary>
    [Fact]
    public void The_odyssey_cards_are_the_workers_in_its_order_the_rooms_first()
    {
        var result = Odyssey();
        var cards = CauseCards.Read(result);
        Assert.Equal(15, cards.Count);
        var raw = JsonNode.Parse(result.Raw.GetRawText())!["view"]!["groups"]!.AsArray();
        var workers = raw.SelectMany(g => g!["causes"]?.AsArray() ?? []).Select(c => c!["key"]!.GetValue<string>()).ToList();
        Assert.Equal(workers, cards.Select(c => c.Key));                                          // its order, every one
        Assert.Equal(Enumerable.Repeat("maine/maine_state:review", 14).Append("maine/maine_state:by_hand"), cards.Select(c => c.GroupKey));
        var rooms = cards[0];
        Assert.Equal(CauseKind.FixModel, rooms.Kind);
        Assert.StartsWith("5 rooms have no route to an exit: ", rooms.Words);
        Assert.Equal("11 rows · 7 rules", rooms.Count);
        Assert.Equal(["SPRINKLERED ABANDONED SPACE (32)", "SPRINKLERED ABANDONED SPACE (33)", "CLOSET (40)", "STORAGE (13)", "ELEC. (21)"],
                     rooms.Rooms.Select(r => r.Name));
        Assert.Equal(rooms.Elements, rooms.Rooms.Select(r => r.Id));
        Assert.All(rooms.Rooms, r => Assert.NotNull(r.Why));
        Assert.Equal([CauseKind.FixModel, CauseKind.Mark, CauseKind.Mark], cards.Take(3).Select(c => c.Kind));     // the model first, then its marks
        // the stairs not read: the project-wide tick the worker's field names, on Project Information
        var stairs = cards.Single(c => c.Fields is ["stairs"]);
        Assert.Equal(CauseKind.Mark, stairs.Kind);
        Assert.Equal([Marks.AllStairs], CauseCards.MarksOf(stairs));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(stairs, null));
        Assert.Equal(CauseKind.MeasureByHand, cards[^1].Kind);
        // shown: the first three, the rest behind "+12 more causes"
        Assert.Equal(cards.Take(3), CauseCards.Shown(cards, all: false));
        Assert.Equal(cards, CauseCards.Shown(cards, all: true));
        Assert.Equal("+12 more causes", CauseCards.MoreWords(cards));
        Assert.Null(CauseCards.MoreWords(cards.Take(3).ToList()));
        // the model carries them, and a card never changes a row: the rows are the answer's with or without causes
        var model = Model(result);
        Assert.Equal(cards.Select(c => c.Key), model.Causes.Select(c => c.Key));
        var bare = JsonNode.Parse(result.Raw.GetRawText())!.AsObject();
        foreach (var g in bare["view"]!["groups"]!.AsArray())
            g!.AsObject().Remove("causes");
        var without = Model(Parse(bare));
        Assert.Empty(without.Causes);
        Assert.Equal(without.Groups.SelectMany(g => g.AllRows).Select(r => (r.Id, r.Verdict, r.VerdictWords, r.Tone)),
                     model.Groups.SelectMany(g => g.AllRows).Select(r => (r.Id, r.Verdict, r.VerdictWords, r.Tone)));
    }

    /// <summary>Each card's button, by its kind and what the project has: the rooms Show (select and zoom) only when
    /// the project has them; the drawing's exit door names its mark but has nothing to select; a mark card naming no
    /// mark Shows its elements (nothing to set in Properties) and says it names none; by hand and decide open the rows.</summary>
    [Fact]
    public void Each_odyssey_cards_button_is_its_kinds_and_only_what_the_project_has()
    {
        var cards = CauseCards.Read(Odyssey()).ToDictionary(c => c.Key);
        var rooms = cards.Values.First();
        var labels = rooms.Elements.ToDictionary(e => e, e => "room " + e[^4..]);
        Assert.Equal(CardAction.Show, CauseCards.Action(rooms, labels));
        Assert.Equal("Show", CauseCards.ButtonWords(CardAction.Show));
        Assert.Equal(CardAction.None, CauseCards.Action(rooms, new Dictionary<string, string>()));   // none in the project: no button
        Assert.Null(CauseCards.Note(rooms, labels));

        var door = cards.Values.Single(c => c.Words.Contains("say whether it is the required exit door", StringComparison.Ordinal));
        Assert.Equal(CauseKind.Mark, door.Kind);
        Assert.Equal([Marks.ExitDoor], CauseCards.MarksOf(door));                                    // its field, doors[].exit
        Assert.Equal(["doors[].exit"], door.Fields);
        Assert.Equal(CardAction.None, CauseCards.Action(door, labels));                                // no element id to select
        Assert.Equal("Set Gordium: Exit door in Properties, on the element the card names (the card has none to select).", CauseCards.Note(door, labels));
        var window = cards.Values.Single(c => c.Words.Contains("emergency escape and rescue opening", StringComparison.Ordinal));
        Assert.Equal([Marks.EscapeOpening], CauseCards.MarksOf(window));

        var load = cards["mark:space:space_occupant_load"];
        Assert.Empty(CauseCards.MarksOf(load));                                                        // the worker: "no mark for it yet"
        var loadLabels = load.Elements.ToDictionary(e => e, e => "space");
        Assert.Equal(CardAction.Show, CauseCards.Action(load, loadLabels));
        Assert.Equal("No Gordium mark is named for this: do what the card says, or decide it by hand.", CauseCards.Note(load, loadLabels));

        Assert.Equal(CardAction.ByHand, CauseCards.Action(cards.Values.Last(), labels));
        Assert.Equal("Check by hand", CauseCards.ButtonWords(CardAction.ByHand));
        Assert.Equal(CardAction.Decide, CauseCards.Action(cards["flag"], labels));

        // Show sends exactly what its button promised: the corridor card's one real element, never its dead ends'
        // measured-part ids ("<corridor> (dead end 2)"), which Revit would report as "not in this model now"
        var corridor = cards["mark:corridor:corridor_occupant_load"];
        var real = corridor.Elements.Single(e => !e.Contains(' ', StringComparison.Ordinal));
        Assert.True(corridor.Elements.Count > 1);
        Assert.Equal([real], CauseCards.ShowIds(corridor, new Dictionary<string, string> { [real] = "CORRIDOR (26)" }));
        Assert.Equal("Decide", CauseCards.ButtonWords(CardAction.Decide));
    }

    /// <summary>A mark card: Show and open Properties when it names a mark set on its elements; Open Project
    /// Information when every mark it names is a project fact's (a fact key's facts each fed by a Project Information
    /// mark, or a mark named in its words); a fact no mark feeds: no button. A name inside a longer one is the longer's.</summary>
    [Fact]
    public void A_mark_card_opens_properties_or_project_information_by_where_its_mark_is()
    {
        var items = new JsonArray(Item("a"), Item("b"), Item("c"), Item("d"), Item("e"), Item("f"));
        var r = Parse(Result(items, Group("x:review", ["a", "b", "c", "d", "e", "f"],
            Card("mark:door:exit", "mark", "door D1: set its Gordium: Exit door mark", ["a"], ["uid-d1"]),
            Card("fact:stories", "mark", "stories: not stated for the project", ["b"]),
            Card("facts:accessory_dwelling_unit", "mark", "Enter whether an ADU is on the lot", ["c"]),
            Card("facts:stories,zone", "mark", "the stories and the zone", ["d"]),
            Card("fact:use", "mark", "use: not stated for the project", ["e"]),
            Card("mark:door:exit2", "mark", "door D2: set its Gordium: Exit door mark", ["f"]))));
        var cards = CauseCards.Read(r);
        var labels = new Dictionary<string, string> { ["uid-d1"] = "Door D1" };
        Assert.Equal([Marks.ExitDoor], CauseCards.MarksOf(cards[0]));                                  // not "Gordium: Exit" too
        Assert.Equal(CardAction.ShowAndProperties, CauseCards.Action(cards[0], labels));
        Assert.Equal("Show and open Properties", CauseCards.ButtonWords(CardAction.ShowAndProperties));
        Assert.Equal("Set Gordium: Exit door in Properties.", CauseCards.Note(cards[0], labels));
        Assert.Equal("Selected 1 element; Properties is open: set Gordium: Exit door there, then Check again.", CauseCards.AfterProperties(cards[0], 1));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(cards[1], labels));
        Assert.Equal("Set Gordium: Stories on Project Information.", CauseCards.Note(cards[1], labels));
        // the ADU fact has its mark on Project Information since 2026-11-22 (Gordium: Accessory dwelling unit)
        Assert.Equal([Marks.AccessoryDwellingUnit], CauseCards.MarksOf(cards[2]));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(cards[2], labels));
        Assert.Equal([Marks.Zone, Marks.Stories], CauseCards.MarksOf(cards[3]));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(cards[3], labels));
        // Gordium: Use is on Project Information and on Rooms: a project fact's is set on Project Information
        Assert.Equal([Marks.Use], CauseCards.MarksOf(cards[4]));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(cards[4], labels));
        Assert.Equal("Set Gordium: Use on Project Information.", CauseCards.Note(cards[4], labels));
        // an element's mark with no element to select: no button, never Project Information
        Assert.Equal(CardAction.None, CauseCards.Action(cards[5], labels));
    }

    /// <summary>The worker's field picks the mark (never the card's words): doors[].exit is Gordium: Exit door though
    /// its words name no mark and no back-quoted field; stairs is the project-wide stairs tick, on Project
    /// Information; facts.use is Gordium: Use, on Project Information though it is also on Rooms; several fields,
    /// every one's mark; a field no mark feeds names none, even when its words name a mark (never one guessed).</summary>
    [Fact]
    public void A_mark_card_names_the_mark_its_field_needs()
    {
        static JsonObject With(JsonObject card, params string[] fields)
        {
            if (fields.Length == 1)
                card["field"] = fields[0];
            else
                card["fields"] = new JsonArray(fields.Select(f => (JsonNode)f).ToArray());
            return card;
        }
        var items = new JsonArray(Item("a"), Item("b"), Item("c"), Item("d"), Item("e"));
        var r = Parse(Result(items, Group("x:review", ["a", "b", "c", "d", "e"],
            With(Card("drawing:door", "mark", "door D01 doesn't say whether it is the required exit door (yes or no)", ["a"], ["uid-d1"]), "doors[].exit"),
            With(Card("drawing:stairs", "mark", "the stairs weren't read: the model doesn't say these are all the stairs", ["b"]), "stairs"),
            With(Card("fact:use", "mark", "use: not stated for the project", ["c"]), "facts.use"),
            With(Card("facts:stories,zone", "mark", "the stories and the zone", ["d"]), "facts.stories", "facts.zone"),
            With(Card("fact:x", "mark", "x: set Gordium: Exit door", ["e"]), "facts.not_a_mark"))));
        var cards = CauseCards.Read(r);
        var labels = new Dictionary<string, string> { ["uid-d1"] = "Door D01" };
        Assert.Equal(["doors[].exit"], cards[0].Fields);
        Assert.Equal([Marks.ExitDoor], CauseCards.MarksOf(cards[0]));
        Assert.Equal(CardAction.ShowAndProperties, CauseCards.Action(cards[0], labels));
        Assert.Equal("Set Gordium: Exit door in Properties.", CauseCards.Note(cards[0], labels));
        Assert.Equal([Marks.AllStairs], CauseCards.MarksOf(cards[1]));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(cards[1], labels));
        Assert.Equal("Set Gordium: These are all the stairs on Project Information.", CauseCards.Note(cards[1], labels));
        Assert.Equal([Marks.Use], CauseCards.MarksOf(cards[2]));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(cards[2], labels));
        Assert.Equal([Marks.Zone, Marks.Stories], CauseCards.MarksOf(cards[3]));
        Assert.Empty(CauseCards.MarksOf(cards[4]));                                                   // not the words' mark
    }

    /// <summary>Only the answer's own: a card's row the answer doesn't have is left out, a card with none is left
    /// out, a key given twice is one card, a card of a group that isn't review or by hand (a failure's, what
    /// complies) is no card, a kind not known is Decide, and an unreadable card is skipped, never guessed.</summary>
    [Fact]
    public void Only_the_answers_own_cards_and_rows_are_read()
    {
        var items = new JsonArray(Item("a"), Item("b"), Item("f", "does_not_comply"), Item("y", "complies"));
        var r = Parse(Result(items,
            Group("law:review", ["a", "b"],
                  Card("k1", "fix_model", "one", ["a", "zz"], ["e1", "e1"]), Card("k2", "fix_model", "none of its rows", ["zz"]),
                  Card("k1", "mark", "the same key again", ["b"]), Card("k3", "something_new", "a kind not known", ["b"]),
                  new JsonObject { ["kind"] = "mark", ["words"] = "no key", ["items"] = new JsonArray("a") }),
            Group("law:fails", ["f"], Card("kf", "fix_model", "a failure's card", ["f"])),
            Group("law:complies", ["y"], Card("ky", "decide", "a pass's card", ["y"]))));
        var cards = CauseCards.Read(r);
        Assert.Equal(["k1", "k3"], cards.Select(c => c.Key));
        Assert.Equal(["a"], cards[0].Items);
        Assert.Equal(["e1"], cards[0].Elements);
        Assert.Equal("1 row", cards[0].Count);
        Assert.Equal(CauseKind.Decide, cards[1].Kind);
    }

    /// <summary>The cards sit right under the first needs-review (or check-by-hand) heading, with the filter all or
    /// needs review and no search; never with a search (only the matching rows), nor under does not comply or
    /// complies; never a row Up and Down move to.</summary>
    [Fact]
    public void The_cards_are_at_the_top_of_the_needs_review_part_only()
    {
        var model = Model(Odyssey());
        var placed = ResultList.Place(model);
        var layout = ResultList.Layout(placed, ListFilter.All, null, null, false);
        var with = ResultList.WithCauses(layout, cards: true, ListFilter.All, null);
        var at = with.ToList().FindIndex(e => e is ListCauses);
        Assert.Equal(ListSection.Review, Assert.IsType<ListHeading>(with[at - 1]).Section);
        Assert.Equal(layout, with.Where(e => e is not ListCauses));
        Assert.Contains(ResultList.WithCauses(layout, true, ListFilter.Review, null), e => e is ListCauses);
        Assert.Same(layout, ResultList.WithCauses(layout, true, ListFilter.Fails, null));
        Assert.Same(layout, ResultList.WithCauses(layout, true, ListFilter.Complies, null));
        Assert.Same(layout, ResultList.WithCauses(layout, true, ListFilter.All, "dead end"));
        Assert.Same(layout, ResultList.WithCauses(layout, false, ListFilter.All, null));
        Assert.IsType<ListRowEntry>(with[ResultList.Next(with, at - 1, 1)]);                            // Down skips the cards
        // no review place: under the check-by-hand heading
        var byHand = layout.Where(e => e is not ListHeading { Section: ListSection.Review }).ToList();
        byHand.RemoveAll(e => e is ListSubheading s && placed.Any(p => p.SourceKey == s.Key && p.Section == ListSection.Review)
                              || e is ListRowEntry r && r.Row.Section == ListSection.Review);
        var under = ResultList.WithCauses(byHand, true, ListFilter.All, null).ToList();
        Assert.Equal(ListSection.ByHand, Assert.IsType<ListHeading>(under[under.FindIndex(e => e is ListCauses) - 1]).Section);
    }

    // ---- looked at -------------------------------------------------------------------------------------------

    /// <summary>A tick is the architect's note, never a verdict: ticking every card and row leaves every row's verdict,
    /// tone, place and status as they were; only rows in review or to check by hand take one (a failure, a pass
    /// refused); progress counts both.</summary>
    [Fact]
    public void A_tick_never_changes_a_verdict_and_only_rows_to_look_at_take_one()
    {
        var model = Model(Odyssey());
        var placed = ResultList.Place(model);
        var before = placed.Select(p => (p.Row.Id, p.Row.Verdict, p.Row.Tone, p.Section, p.Status)).ToList();
        var looked = new LookedAt();
        Assert.Equal("Looked at: 0 of 15 causes · 0 of 183 rows", looked.Progress(model.Causes, placed));
        foreach (var c in model.Causes)
            looked.SetCard(c.Key, true);
        foreach (var p in placed)
            looked.SetRow(p, true);
        Assert.Equal(before, ResultList.Place(model).Select(p => (p.Row.Id, p.Row.Verdict, p.Row.Tone, p.Section, p.Status)));
        Assert.Equal(model.Groups.SelectMany(g => g.AllRows).Select(r => r.Verdict), Model(Odyssey()).Groups.SelectMany(g => g.AllRows).Select(r => r.Verdict));
        Assert.Equal(183, looked.Rows.Count);                                                          // not the 7 that comply
        Assert.All(placed.Where(p => p.Section == ListSection.Complies), p => Assert.False(looked.Row(p.Row.Id)));
        Assert.Equal("Looked at: 15 of 15 causes · 183 of 183 rows", looked.Progress(model.Causes, placed));
        looked.SetCard(model.Causes[0].Key, false);
        Assert.Equal("Looked at: 14 of 15 causes · 183 of 183 rows", looked.Progress(model.Causes, placed));
        Assert.Equal("", new LookedAt().Progress([], []));
        Assert.Contains("changes no verdict", LookedAt.Tip, StringComparison.Ordinal);
    }

    /// <summary>A new check keeps a tick only on what is still the same thing to look at: a card of the same key,
    /// words and rows; a row of the same id with the same verdict, reason, figures and how far, still to look at.
    /// A changed card or row, one now passing, or one gone starts unticked; no check before: none.</summary>
    [Fact]
    public void Ticks_carry_to_a_new_check_only_where_nothing_changed()
    {
        ResultModel Check(string bStatus, string cReason, string[] cardItems, string? dHowFar = "1 ft over; see why") => Model(Parse(Result(
            new JsonArray(Item("a"), Item("b", bStatus), Item("c", reason: cReason), Item("d", howFar: dHowFar), Item("e")),
            Group("law:review", ["a", "b", "c", "d", "e"], Card("same", "decide", "a person decides", ["a"]),
                  Card("grows", "fix_model", "rooms", cardItems)))));
        var was = Check("needs_review", "r", ["b"]);
        var ticks = new LookedAt();
        ticks.SetCard("same", true);
        ticks.SetCard("grows", true);
        foreach (var p in ResultList.Place(was))
            ticks.SetRow(p, true);
        var now = Check("complies", "another reason", ["b", "c"], dHowFar: "2 ft over; see why");
        var carried = LookedAt.Carry(ticks, was, now);
        Assert.Equal(["same"], carried.Cards);
        Assert.Equal(["a", "e"], carried.Rows.Order());                // b now complies, c's reason and d's how far changed
        Assert.Equal(["a", "b", "c", "d", "e"], LookedAt.Carry(ticks, was, was).Rows.Order());
        Assert.Empty(LookedAt.Carry(null, was, now).Rows);
        Assert.Empty(LookedAt.Carry(ticks, null, now).Cards);
        Assert.Empty(LookedAt.Carry(ticks, was, Check("needs_review", "r", ["b"]) with { Causes = [] }).Cards);   // the card gone
    }

    // ---- what changed ---------------------------------------------------------------------------------------

    private static ResultModel Rows(params (string Id, string Status, string Name, string? Reason)[] rows) => Model(Parse(Result(
        new JsonArray(rows.Select(r => (JsonNode)Item(r.Id, r.Status, r.Name, r.Reason)).ToArray()),
        Group("law:review", rows.Select(r => r.Id).ToArray()))));

    private static readonly DateTime At = new(2026, 11, 22, 14, 32, 0);

    /// <summary>By row id, in the worker's verdicts: "2 rows changed since 14:32: Dead end: needs review → does not
    /// comply; Travel distance now complies", worst now first; a row that only says something new is counted, not
    /// named as changed; the same answer: nothing changed; no check before: nothing said.</summary>
    [Fact]
    public void What_changed_is_said_by_row_id_in_the_workers_verdicts()
    {
        var before = Rows(("t", "needs_review", "Travel distance", "r"), ("d", "needs_review", "Dead end", "r"), ("h", "needs_review", "Height", "r"));
        var after = Rows(("t", "complies", "Travel distance", null), ("d", "does_not_comply", "Dead end", "r"), ("h", "needs_review", "Height", "other"));
        var change = CheckChanges.Between(before, At, after)!;
        Assert.True(change.Compared);
        Assert.Equal("2 rows changed since 14:32: Dead end: needs review → does not comply; Travel distance now complies. " +
                     "1 more says something new with the same verdict.", change.Words);
        Assert.Equal(["d", "t"], change.Rows.Select(r => r.Id));
        Assert.Equal((Verdict.NeedsReview, Verdict.DoesNotComply), (change.Rows[0].Before, change.Rows[0].After));
        Assert.Equal(1, change.Said);
        Assert.Equal("Nothing changed since the check at 14:32.", CheckChanges.Between(before, At, before)!.Words);
        Assert.Null(CheckChanges.Between(null, At, after));
        var onlySaid = CheckChanges.Between(before, At, Rows(("t", "needs_review", "Travel distance", "r"), ("d", "needs_review", "Dead end", "x"),
                                                            ("h", "needs_review", "Height", "r")))!;
        Assert.Equal("No verdict changed since the check at 14:32: 1 row says something new (figures or reason).", onlySaid.Words);
        Assert.Empty(onlySaid.Rows);
    }

    /// <summary>Never a change the worker didn't send: a stale before (only its colours grey) is the same verdicts;
    /// an answer stale when it arrives isn't compared; new and gone rows are said as such; a status word the add-in
    /// doesn't know is said in the row's own words, never "now complies"; past three, "and N more".</summary>
    [Fact]
    public void Nothing_is_claimed_beyond_the_two_answers()
    {
        var before = Rows(("a", "needs_review", "A", "r"), ("b", "needs_review", "B", "r"), ("c", "needs_review", "C", "r"),
                          ("d", "needs_review", "D", "r"), ("e", "needs_review", "E", "r"));
        Assert.Equal("Nothing changed since the check at 14:32.", CheckChanges.Between(ResultRows.Stale(before, At), At, before)!.Words);
        var stale = CheckChanges.Between(before, At, ResultRows.Stale(Rows(("a", "complies", "A", null)), At, "changed while checked"))!;
        Assert.False(stale.Compared);
        Assert.Empty(stale.Rows);
        Assert.StartsWith("Not compared with the check at 14:32: the model changed while this one ran", stale.Words);

        var after = Rows(("a", "maybe", "A", "r"), ("b", "complies", "B", null), ("c", "complies", "C", null), ("d", "complies", "D", null),
                         ("n", "needs_review", "N", "r"));
        var change = CheckChanges.Between(before, At, after)!;
        Assert.Equal(["a", "n", "b", "c", "d", "e"], change.Rows.Select(r => r.Id));
        Assert.Equal("A: needs review → needs review (the checker said \"maybe\")", change.Rows[0].Words);
        Assert.Equal("N: new, needs review", change.Rows[1].Words);
        Assert.Equal("E: no longer in the check (it was needs review)", change.Rows[^1].Words);
        Assert.Null(change.Rows[^1].After);
        Assert.EndsWith("; and 3 more.", change.Words);
        Assert.StartsWith("6 rows changed since 14:32: A: needs review → needs review (the checker said \"maybe\"); N: new, needs review; B now complies", change.Words);
    }

    // ---- the bar ---------------------------------------------------------------------------------------------

    /// <summary>The Odyssey's remoteness row: the bar from the worker's limit_length, its words the worker's, the two
    /// marks placed by the worker's two numbers (the longer spans the bar), at least the limit; no other row has one.</summary>
    [Fact]
    public void The_bar_is_drawn_only_from_the_workers_two_lengths()
    {
        var rows = Model(Odyssey()).Groups.SelectMany(g => g.AllRows).ToList();
        var bar = Assert.Single(rows, r => r.Bar is not null).Bar!;
        Assert.Equal("exits 187.16 ft apart, needs ≥ 71 ft (1/3 of the 212.99 ft diagonal)", bar.Words);
        Assert.Equal((187.1643328131042, 70.99510361186105, "ft", LimitSide.AtLeast), (bar.Measured, bar.Limit, bar.Unit, bar.Side));
        Assert.Equal(1, bar.MeasuredAt);
        Assert.Equal(70.99510361186105 / 187.1643328131042, bar.LimitAt, 12);
        Assert.Contains("BAR: exits 187.16 ft apart", Details.Of(new ListRow(rows.First(r => r.Bar is not null), ListSection.Review, PanelStatus.Review, "", "", 1, false),
                                                                  0, 1, null, null).Text(), StringComparison.Ordinal);
    }

    /// <summary>Not a bar: no limit_length, a number that isn't one (a string, NaN as text), two units that differ,
    /// a negative length, no words; one unit given twice the same is one.</summary>
    [Theory]
    [InlineData("""{"measured": 10, "limit": 5, "unit": "ft", "words": "w"}""", true)]
    [InlineData("""{"measured": 10, "limit": 5, "measured_unit": "ft", "limit_unit": "ft", "words": "w"}""", true)]
    [InlineData("""{"measured": 10, "limit": 5, "measured_unit": "ft", "limit_unit": "in", "words": "w"}""", false)]
    [InlineData("""{"measured": 10, "limit": 5, "unit": "ft", "limit_unit": "in", "words": "w"}""", false)]
    [InlineData("""{"measured": "10", "limit": 5, "unit": "ft", "words": "w"}""", false)]
    [InlineData("""{"measured": -1, "limit": 5, "unit": "ft", "words": "w"}""", false)]
    [InlineData("""{"measured": 0, "limit": 0, "unit": "ft", "words": "w"}""", false)]
    [InlineData("""{"measured": 10, "limit": 5, "unit": "ft"}""", false)]
    [InlineData("""{"measured": 10, "limit": 5, "words": "w"}""", false)]
    [InlineData("null", false)]
    public void A_bar_needs_two_numbers_in_one_unit_and_the_workers_words(string limitLength, bool bar)
    {
        var row = JsonDocument.Parse($$"""{"id": "x", "limit_length": {{limitLength}}}""").RootElement;
        Assert.Equal(bar, MeasureBar.Of(row) is not null);
        Assert.Null(MeasureBar.Of(JsonDocument.Parse("""{"id": "x"}""").RootElement));
    }

    // ---- the add-in's wiring (Revit-only, not built here: read in its source) --------------------------------

    private static string Addin(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file)).Replace("\r\n", "\n", StringComparison.Ordinal);

    /// <summary>A card's Show and Show-and-open-Properties run on Revit's thread (Post, the one ExternalEvent);
    /// Properties comes up only after its elements were selected; a tick only records the tick and redraws the ticks
    /// (never a selection, a zoom or a check); a new check is compared only with the project's last check that arrived
    /// current, and an answer stale on arrival is never the one the next is compared with.</summary>
    [Fact]
    public void The_addin_runs_card_actions_on_revits_thread_and_a_tick_does_nothing_else()
    {
        var pane = Addin("ResultsPane.cs");
        Assert.Contains("new ResultsView(Zoom, Select, CheckAgain, OpenProjectInformation, Card, SetUp, _theme, SaveAnswers, MoreTime)", pane, StringComparison.Ordinal);
        Assert.Contains("    private static void Card(CardRequest request) => Post(", pane, StringComparison.Ordinal);
        Assert.Contains("            var selected = ShowElements(ui, request.Elements, request.What, zoom: true);\n" +
                        "            if (request.Action != CardAction.ShowAndProperties || selected == 0)\n                return;\n" +
                        "            ui.GetDockablePane(DockablePanes.BuiltInDockablePanes.PropertiesPalette).Show();\n" +
                        "            Say(CauseCards.AfterProperties(request.Card, selected));", pane, StringComparison.Ordinal);
        var view = Addin("ResultsView.cs");
        // a fix (the intuitive pane: the cards joined) sends exactly its cards' elements the project has (Fixes.ShowIds)
        Assert.Contains("_card(new CardRequest(first, action, Fixes.ShowIds(group, Labels), Short(group.Title)));", view, StringComparison.Ordinal);
        Assert.DoesNotContain("new CardRequest(card, action, card.Elements", view, StringComparison.Ordinal);
        Assert.DoesNotContain("group.Elements, ", view, StringComparison.Ordinal);
        Assert.Contains("    public void TickRow(ListRow row, bool ticked)\n    {\n        _looked.SetRow(row, ticked);\n        RefreshTicks();\n    }", view, StringComparison.Ordinal);
        Assert.Contains("    public void TickCard(Fix group, bool ticked)\n    {\n        _looked.SetCard(group.Key, ticked);\n        RefreshTicks();\n    }", view, StringComparison.Ordinal);
        Assert.Contains("    internal void Show(PanelContent content)\n    {\n        NewCheck(content);", view, StringComparison.Ordinal);
        // compared and carried by the document's identity (review round 2 of UI changes 13-15: a Save As renames it)
        Assert.Contains("        if (key is not null && model.Stale is null)\n            _compared[key] = (content.When, model, content.Questions);", view, StringComparison.Ordinal);
        Assert.Contains("        if (_shownCheck == (content.Key ?? content.Project, content.When))\n            return;", view, StringComparison.Ordinal);
    }

    // ---- failures by how far ----------------------------------------------------------------------------------

    /// <summary>The worker's how_far words for egress are decimal feet or inches ("2.5 ft short", "4 in over"):
    /// failures are ordered by them too, largest first; an area, a percent, room to spare: not a length.</summary>
    [Theory]
    [InlineData("2.5 ft short", 2.5)]
    [InlineData("4 in over", 4.0 / 12)]
    [InlineData("at least 1.25 ft short", 1.25)]
    [InlineData("up to 19.79 ft over under some reading", 19.79)]
    [InlineData("1,200.5 ft over", 1200.5)]
    [InlineData("2'-6\" short", 2.5)]
    [InlineData("3.24% over", null)]
    [InlineData("213 sq ft over", null)]
    [InlineData("116.16 ft to spare if confirmed", null)]
    [InlineData("at the limit", null)]
    public void How_far_off_reads_decimal_lengths(string words, double? feet)
    {
        var row = new ResultRow("x", "x", Verdict.DoesNotComply, "DOES NOT COMPLY", Tone.Fails, null, words, null, null, [], []);
        var got = ResultList.HowFarOff(row);
        if (feet is null)
            Assert.Null(got);
        else
            Assert.Equal(feet.Value, got!.Value, 9);
    }

    [Fact]
    public void Failures_are_largest_first_by_decimal_how_far()
    {
        var r = Parse(Result(new JsonArray(Item("small", "does_not_comply", howFar: "4 in short"), Item("none", "does_not_comply"),
                                           Item("big", "does_not_comply", howFar: "2.5 ft short"), Item("mid", "does_not_comply", howFar: "1 ft over")),
                             Group("law:fails", ["small", "none", "big", "mid"])));
        Assert.Equal(["big", "mid", "small", "none"], ResultList.Place(Model(r)).Select(p => p.Row.Id));
    }
}
