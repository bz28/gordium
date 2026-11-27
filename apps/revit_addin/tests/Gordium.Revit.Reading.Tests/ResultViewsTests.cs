using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The results as two views of one answer (ResultViews; UI polish changes 17 to 21, 23 to 27, 33 to 37),
/// Revit-free, on the four-unit apartment's real answer (Ben's 2026-11-23 trial request,
/// test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json, answered by the
/// worker: answers/four_unit_apartment_check_answer.json) and on that answer changed one way at a time. The rules each
/// test holds: every row is in both views (never hidden); every count is a count of the checker's rows; a group or
/// node is never green while anything in it fails, needs review or isn't checked yet; nothing here makes a verdict.
/// The apartment's answer is made by the checker, never committed (tools/evals/make_apartment_answer.py), so the counts
/// compared on it are counted here from the answer's own JSON (its statuses and asks), never written in as numbers a
/// rule change would move; the words and the counting are pinned with numbers on a small answer made here
/// (<see cref="Small"/>).</summary>
public sealed class ResultViewsTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static readonly string File_ = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests",
                                                        "answers", "four_unit_apartment_check_answer.json");

    private static JsonNode Answer() => JsonNode.Parse(File.ReadAllText(File_, Encoding.UTF8))!["result"]!;

    private static CheckResult Parse(JsonNode result) =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(result.ToJsonString()).RootElement.Clone(), About));

    private static CheckResult Apartment() => Parse(Answer());

    private static JsonArray Items(JsonNode result) => result["view"]!["items"]!.AsArray();

    private static IEnumerable<CodeNode> Walk(IEnumerable<CodeNode> nodes) => nodes.SelectMany(n => Walk(n.Children).Prepend(n));

    private static IEnumerable<ResultRow> RowsIn(CodeNode n) => n.Rows.Concat(n.Children.SelectMany(RowsIn));

    /// <summary>The checker's status words and the summary's words for each, worst first, as the design writes them
    /// (change 18), kept here apart from the pane's own table so a slip in either shows.</summary>
    private static readonly (string Status, string One, string Many)[] Words =
    [
        ("does_not_comply", "fails", "fail"),
        ("needs_review", "needs review", "need review"),
        ("not_checked", "not checked yet", "not checked yet"),
        ("complies", "complies", "comply"),
        ("not_applicable", "doesn't apply", "don't apply"),
    ];

    /// <summary>A row's status word as the pane must count it, read from the answer's JSON (never through the pane):
    /// the checker's word, except that "not applicable" with no reason is needs review (a rule is never set aside
    /// without its reason shown).</summary>
    private static string? StatusOf(JsonNode item) =>
        (string?)item["status"] is "not_applicable" && string.IsNullOrWhiteSpace((string?)item["reason"]) ? "needs_review" : (string?)item["status"];

    /// <summary>How many of the answer's rows the pane must count under each status word.</summary>
    private static int Count(JsonNode result, string status) => Items(result).Count(i => StatusOf(i!) == status);

    /// <summary>The summary line the answer's own statuses make: each word's count, worst first, zero counts left out.
    /// An answer with a status word not listed in <see cref="Words"/> fails here, so a new word is never counted as
    /// nothing.</summary>
    private static string SummaryOf(JsonNode result)
    {
        Assert.All(Items(result), i => Assert.Contains((string)i!["status"]!, Words.Select(w => w.Status)));
        return string.Join(" · ", Words.Select(w => (w, n: Count(result, w.Status))).Where(x => x.n > 0)
                                       .Select(x => $"{x.n} {(x.n == 1 ? x.w.One : x.w.Many)}"));
    }

    /// <summary>The ids of the rows in review that make an ask <paramref name="asks"/> picks (an ask the pane can show:
    /// with a key and a headline), read from the answer's JSON: what a card of those asks must list, each row once.</summary>
    private static HashSet<string> Asking(JsonNode result, Func<JsonNode, bool> asks) =>
        Items(result).Where(i => StatusOf(i!) == "needs_review" && i!["asks"] is JsonArray all
                                 && all.Any(a => a is JsonObject && (string?)a["key"] is { Length: > 0 }
                                                 && (string?)a["headline"] is { Length: > 0 } && asks(a)))
                     .Select(i => (string)i!["id"]!).ToHashSet(StringComparer.Ordinal);

    /// <summary>The ids of the rows in the card of <paramref name="field"/>'s question, read from the answer's JSON.</summary>
    private static HashSet<string> AskingFor(JsonNode result, string field) =>
        Asking(result, a => (string?)a["field"] == field && (string?)a["kind"] == "mark");

    /// <summary>The group an ask's card belongs in, by the design's table (strings.md, "What to fix"), written here
    /// apart from the pane's <see cref="ResultViews.KindOf"/> so a slip in it can't move the test's expectation too: a
    /// mark of a fact on Project Information (<c>facts.</c>, <c>building.</c>) is a question to answer, any other mark
    /// an element to mark; an unknown or missing kind is a person's to decide.</summary>
    private static FixKind GroupOf(JsonNode ask) => ((string?)ask["kind"], (string?)ask["field"]) switch
    {
        ("mark", { } f) when f.StartsWith("facts.", StringComparison.Ordinal) || f.StartsWith("building.", StringComparison.Ordinal) => FixKind.Answer,
        ("mark", _) => FixKind.Mark,
        ("fix_model", _) => FixKind.FixModel,
        ("survey", _) => FixKind.Survey,
        ("measure", _) => FixKind.Measure,
        ("open_question", _) => FixKind.OpenQuestion,
        _ => FixKind.Decide,
    };

    private static JsonObject Work(string kind, string key) => new() { ["kind"] = kind, ["key"] = key, ["headline"] = "Do " + key };

    private static JsonObject Ask(string field, string? headline = null) => new()
    {
        ["kind"] = "mark", ["key"] = "field:" + field, ["headline"] = headline ?? "Say " + field, ["why"] = "w",
        ["elements"] = new JsonArray(), ["field"] = field,
    };

    private static JsonObject Asked(string id, params JsonObject[] asks)
    {
        var item = UxAnswers.Item(id, "needs_review");
        item["asks"] = new JsonArray(asks.Select(a => (JsonNode)a.DeepClone()).ToArray());
        return item;
    }

    /// <summary>A small answer made here, its counts known by hand: one fails; thirteen in review (three ask the
    /// occupancy group, one of those first the sprinkler system; one asks for a room's function; one each asks to fix the
    /// model, for a survey, to measure by hand, an open question, to decide, and work of a kind the add-in doesn't know;
    /// one asks nothing, one has a status word the add-in doesn't know and one doesn't apply but says no reason, each of
    /// those last three review); two not checked yet; two comply; one doesn't apply.</summary>
    private static CheckResult Small() => UxAnswers.Answer("does_not_comply",
        UxAnswers.Item("f1", "does_not_comply"),
        Asked("r1", Ask("building.sprinkler_system"), Ask("building.occupancy_groups")),
        Asked("r2", Ask("building.occupancy_groups")),
        Asked("r3", Ask("building.occupancy_groups"), Ask("building.occupancy_groups")),
        Asked("r4", new JsonObject { ["kind"] = "mark", ["key"] = "mark:rooms", ["headline"] = "Set the room's function", ["field"] = "rooms[].function" }),
        Asked("r6", Work("fix_model", "fix:walls")), Asked("r7", Work("survey", "survey")), Asked("r8", Work("measure", "measure:sill")),
        Asked("r9", Work("open_question", "open:yard")), Asked("r10", Work("decide", "decide:use")), Asked("r11", Work("brand_new", "new:x")),
        UxAnswers.Item("r5", "needs_review"),
        UxAnswers.Item("u1", "something_new"),
        UxAnswers.Item("a2", "not_applicable", reason: null),
        UxAnswers.Item("n1", "not_checked"), UxAnswers.Item("n2", "not_checked"),
        UxAnswers.Item("c1", "complies"), UxAnswers.Item("c2", "complies"),
        UxAnswers.Item("a1", "not_applicable"));

    /// <summary>The counting and the words, pinned with numbers counted by hand on <see cref="Small"/>: the apartment's
    /// own counts are counted from its answer (it changes with the rules), so a slip that moved both the pane's count
    /// and the test's would hide there; here it can't.</summary>
    [Fact]
    public void The_counts_and_their_words_on_a_small_answer_counted_by_hand()
    {
        var m = ResultViews.Build(Small());
        Assert.Equal("1 fails · 13 need review · 2 not checked yet · 2 comply · 1 doesn't apply", m.Summary);
        // every group, in the design's order, each with its rows and its words
        Assert.Equal([FixKind.Fails, FixKind.Answer, FixKind.Mark, FixKind.FixModel, FixKind.Survey, FixKind.Measure, FixKind.Decide,
                      FixKind.OpenQuestion, FixKind.NotChecked, FixKind.Done], m.Fix.Select(g => g.Kind));
        Assert.Equal(["f1", "r1 r2 r3", "r4", "r6", "r7", "r8", "r10 r11 r5 u1 a2", "r9", "n1 n2", "c1 c2 a1"],
                     m.Fix.Select(g => string.Join(" ", g.Rows.Select(r => r.Id))));
        Assert.Equal(["Fails · 1", "Answer 2 questions about the project", "Mark 1 kind of element", "Fix 1 thing in the model",
                      "Get a survey", "Measure 1 thing by hand", "5 code questions for you to decide", "1 open question about the law",
                      "Not checked yet by Gordium", "Complies or doesn't apply · 3"], m.Fix.Select(g => g.Title));
        var answer = m.Fix.Single(g => g.Kind == FixKind.Answer);
        // the card most rows wait on first, though the sprinkler system was asked first; a row asking twice is listed once
        Assert.Equal(["building.occupancy_groups", "building.sprinkler_system"], answer.Cards.Select(c => c.Field));
        Assert.Equal(["r1 r2 r3", "r1"], answer.Cards.Select(c => string.Join(" ", c.Rows.Select(r => r.Id))));
        Assert.Equal("Answer 2 questions about the project", answer.Title);
        Assert.Equal(["r1", "r2", "r3"], answer.Rows.Select(r => r.Id));
        Assert.Equal(["decide:use", "new:x", "row:r5", "row:u1", "row:a2"], m.Fix.Single(g => g.Kind == FixKind.Decide).Cards.Select(c => c.Key));
        Assert.Equal("No results", ResultViews.Summary([]));
        Assert.Equal("1 needs review · 1 complies", ResultViews.Summary([Verdict.Complies, Verdict.NeedsReview]));
    }

    [Fact]
    public void The_top_says_the_checker_s_counts_and_what_they_mean()
    {
        var result = Answer();
        var m = ResultViews.Build(Parse(result));
        // the line's numbers are the answer's own counts, in the line's words and order (pinned with numbers on Small)
        Assert.Equal(SummaryOf(result), m.Summary);
        Assert.True(Count(result, "needs_review") > 0 && Words.Count(w => Count(result, w.Status) > 0) >= 2);   // never a count of nothing
        // only the results that wait on a question are said to (egress UI audit): their count is the questions card's
        var review = m.Fix.SelectMany(g => g.Rows).Where(r => r.Verdict == Verdict.NeedsReview).Select(r => r.Id).Distinct().Count();
        var asked = m.Fix.Single(g => g.Kind == FixKind.Answer).Rows.Where(r => r.Verdict == Verdict.NeedsReview).Select(r => r.Id).Distinct().Count();
        Assert.InRange(asked, 1, review - 1);                                    // the apartment: some wait on marks and hand checks
        var cards = m.Fix.Single(g => g.Kind == FixKind.Answer).Cards.Count;
        Assert.True(cards > 1);
        Assert.Equal($"Nothing fails yet. {review} results need review; {asked} of them wait on the questions below.", m.Headline);
        Assert.Equal("Nothing fails yet. 2 results can't be decided until the questions below are answered.",
                     ResultViews.Headline([(Verdict.NeedsReview, "a"), (Verdict.NeedsReview, "b")], onQuestions: 2));
        Assert.Equal("Nothing fails yet. 2 results need review: each says below what it needs.",
                     ResultViews.Headline([(Verdict.NeedsReview, "a"), (Verdict.NeedsReview, "b")], onQuestions: 0));
        Assert.Equal("Nothing fails yet. 1 result needs review: it says below what it needs.",
                     ResultViews.Headline([(Verdict.NeedsReview, "a")], onQuestions: 0));
        // review round 1: one result waits, and one question asked, said so
        var eighty = Enumerable.Range(0, 80).Select(i => (Verdict.NeedsReview, $"r{i}")).ToList();
        Assert.Equal("Nothing fails yet. 80 results need review; 2 of them wait on the question below.",
                     ResultViews.Headline(eighty, onQuestions: 2, questions: 1));
        Assert.Equal("Nothing fails yet. 80 results need review; 1 of them waits on the questions below.",
                     ResultViews.Headline(eighty, onQuestions: 1, questions: 3));
        Assert.Equal("Nothing fails yet. 2 results can't be decided until the question below is answered.",
                     ResultViews.Headline([(Verdict.NeedsReview, "a"), (Verdict.NeedsReview, "b")], onQuestions: 2, questions: 1));
        Assert.Equal("1 fails · 2 need review", ResultViews.Summary([Verdict.NeedsReview, Verdict.DoesNotComply, Verdict.NeedsReview]));
        Assert.Equal("1 rule fails. Fix it first; 2 results also need review.",
                     ResultViews.Headline([(Verdict.NeedsReview, "a"), (Verdict.DoesNotComply, "b"), (Verdict.NeedsReview, "c")]));
        // a rule failing in three spaces is one rule that fails (review round 1), two rules are two
        Assert.Equal("1 rule fails. Fix it first.",
                     ResultViews.Headline([(Verdict.DoesNotComply, "exits"), (Verdict.DoesNotComply, "exits"), (Verdict.DoesNotComply, "exits")]));
        Assert.StartsWith("2 rules fail. Fix them first",
                          ResultViews.Headline([(Verdict.DoesNotComply, "exits"), (Verdict.DoesNotComply, "width")]), StringComparison.Ordinal);
        // never "complies" as the whole story: Gordium doesn't check every part of the code
        Assert.Contains("doesn't check every part", ResultViews.Headline([(Verdict.Complies, "a")]), StringComparison.Ordinal);
        Assert.Contains("not checked yet", ResultViews.Headline([(Verdict.Complies, "a"), (Verdict.NotChecked, "b")]), StringComparison.Ordinal);
    }

    /// <summary>Egress UI audit, finding 3: cards of a group headed by the same words (the apartment's "Check this by
    /// hand: a person decides it") are each named by the rule their results are about, so they can be told apart; the
    /// checker's words stay the headline and the tooltip says both.</summary>
    [Fact]
    public void Cards_headed_alike_are_named_by_their_rule()
    {
        var m = ResultViews.Build(Apartment());
        var named = 0;
        foreach (var g in m.Fix)
        {
            // the renamed cards of a group are told apart: no two share a title
            var renamed = g.Cards.Where(c => c.Title != c.Headline).ToList();
            Assert.Equal(renamed.Count, renamed.Select(c => c.Title).Distinct().Count());
            foreach (var c in g.Cards)
            {
                if (c.Title != c.Headline)
                {
                    named++;
                    Assert.All(c.Rows, r => Assert.EndsWith(c.Title, r.Name, StringComparison.Ordinal));
                    var entry = new FixCardEntry(c, ResultViewList.CardKey(c), false, PanelStatus.Review);
                    var tip = ResultViewList.Tip(entry)!;
                    Assert.StartsWith(c.Title + "\n" + c.Headline, tip, StringComparison.Ordinal);      // both, rule first
                    Assert.StartsWith(c.Title + ",", ResultViewList.Spoken(entry), StringComparison.Ordinal);   // what a screen reader says
                }
            }
        }
        var decide = m.Fix.Single(g => g.Kind == FixKind.Decide);
        Assert.True(named >= decide.Cards.Count(c => c.Headline == "Check this by hand: a person decides it"), $"{named} named");
        Assert.True(decide.Cards.Select(c => c.Title).Distinct().Count() > decide.Cards.Select(c => c.Headline).Distinct().Count());
        // the rule part of a real row's name, and none for rows about two rules
        var corridorWidth = decide.Cards.Single(c => c.Rows.Count == 1 && c.Rows[0].Name.EndsWith("Corridor width kept clear (BCNYS 1020.4)", StringComparison.Ordinal));
        Assert.Equal("Corridor width kept clear (BCNYS 1020.4)", ResultViews.RuleOf(corridorWidth.Rows));
        Assert.Null(ResultViews.RuleOf([.. decide.Cards.Where(c => c.Rows.Count == 1).Take(2).Select(c => c.Rows[0])]));
        var list = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsList.cs"));
        Assert.Contains("Text = e.Card.Title, TextTrimming", list, StringComparison.Ordinal);
        // review round 1: one rule on two elements under the same words: each named by its result's whole name; the
        // same whole name twice: the checker's words stay
        var two = corridorWidth.Rows[0];
        FixCard Card(string key, ResultRow row) => new(key, FixKind.Decide, "Look at it", null, null, [], [row]);
        var a = two with { Id = "a", Name = "Level 1 \u203A CORRIDOR L1 (3) \u00B7 Corridor width kept clear (BCNYS 1020.4)" };
        var b = two with { Id = "b", Name = "Level 2 \u203A CORRIDOR L2 (8) \u00B7 Corridor width kept clear (BCNYS 1020.4)" };
        Assert.Equal([a.Name, b.Name], ResultViews.Named([Card("1", a), Card("2", b)]).Select(c => c.Title));
        Assert.Equal(["Look at it", "Look at it"], ResultViews.Named([Card("1", a), Card("2", a with { Id = "c" })]).Select(c => c.Title));
        Assert.Equal(["Look at it", "Other words"], ResultViews.Named([Card("1", a), Card("2", b) with { Headline = "Other words" }]).Select(c => c.Title));
    }

    [Fact]
    public void What_to_fix_holds_every_row_and_each_ask_of_each_row_in_review()
    {
        var raw = Answer();
        var result = Parse(raw);
        var m = ResultViews.Build(result);
        var all = m.Fix.SelectMany(g => g.Rows).Select(r => r.Id).ToHashSet();
        Assert.All(result.Items, i => Assert.Contains(i.Id, all));
        Assert.Equal(m.Fix.Select(g => g.Kind).OrderBy(k => k), m.Fix.Select(g => g.Kind));          // the design's order
        foreach (var item in result.Items.Where(i => i.Status == Verdict.NeedsReview))
            foreach (var ask in ResultViews.Asks(item.Raw))
            {
                var kind = GroupOf(new JsonObject { ["kind"] = ask.Kind, ["field"] = ask.Field });
                var card = m.Fix.SelectMany(g => g.Cards).Single(c => c.Key == ask.Key && c.Kind == kind);
                Assert.Contains(card.Rows, r => r.Id == item.Id);
                Assert.All(ask.Elements, e => Assert.Contains(e, card.Elements));
            }
        // a group's rows are its cards' rows, each once
        Assert.All(m.Fix, g => Assert.Equal(g.Cards.SelectMany(c => c.Rows).Select(r => r.Id).Distinct().Count(), g.Rows.Count));
        // and no more: each card lists exactly the rows in review whose asks it shows, counted from the answer's JSON
        // (the numbers once written here, 198 and the rest, each a rule change away from wrong), the most first
        foreach (var g in m.Fix.Where(g => g.Kind is not (FixKind.Fails or FixKind.NotChecked or FixKind.Done)))
        {
            foreach (var card in g.Cards)
            {
                var asking = Asking(raw, a => (string?)a["key"] == card.Key && GroupOf(a) == card.Kind);
                if (asking.Count == 0)                                       // a row in review with no ask it can show
                {
                    Assert.StartsWith("row:", card.Key, StringComparison.Ordinal);
                    asking = [card.Key["row:".Length..]];
                }
                Assert.Equal(asking.Order(StringComparer.Ordinal), card.Rows.Select(r => r.Id).Order(StringComparer.Ordinal));
            }
            Assert.Equal(g.Cards.Select(c => c.Rows.Count).OrderDescending(), g.Cards.Select(c => c.Rows.Count));
        }
        // the groups by status alone, each exactly the answer's rows of that status
        foreach (var (kind, statuses) in new (FixKind, string[])[] { (FixKind.Fails, ["does_not_comply"]), (FixKind.NotChecked, ["not_checked"]),
                                                                     (FixKind.Done, ["complies", "not_applicable"]) })
            Assert.Equal(Items(raw).Where(i => statuses.Contains(StatusOf(i!))).Select(i => (string)i!["id"]!).Order(StringComparer.Ordinal),
                         m.Fix.Where(g => g.Kind == kind).SelectMany(g => g.Rows).Select(r => r.Id).Order(StringComparer.Ordinal));
    }

    [Fact]
    public void A_room_with_no_function_is_one_card_setting_the_gordium_function_mark()
    {
        // group 3 (PR #192) end to end with PR #191: the worker's answer for the trial apartment (no room function
        // marked) asks for the room's function by its field, and that field is the room mark Revit writes it from
        var m = ResultViews.Build(Apartment());
        var card = m.Fix.SelectMany(g => g.Cards).Single(c => c.Field == "rooms[].function");
        Assert.Equal(FixKind.Mark, card.Kind);
        Assert.Equal("Set the room's function", card.Headline);
        Assert.Equal(Marks.RoomFunction, Marks.All.Single(k => k.Feeds == card.Field));
        // the rooms only (the four apartments), never a story's level: the mark is on Rooms (round 14)
        Assert.Equal(4, card.Elements.Count);
        Assert.DoesNotContain("933c4a06-93b8-11d3-80f8-00c04f8efc32-0000001e", card.Elements);
        Assert.DoesNotContain("6341822b-d4f3-11d3-a039-0000863f1523-000026da", card.Elements);
        // never a mark to set for an occupant load (no host has one); group 4a's corridors ask instead whether another
        // level's occupants reach them, a question on Project Information its own mark answers (Gordium: Other levels
        // reach corridors, the Revit-fields PR for groups 4 and 5; before it, asked by hand)
        Assert.DoesNotContain(m.Fix.SelectMany(g => g.Cards),
                              c => c.Kind == FixKind.Mark && c.Headline.Contains("occupant load", StringComparison.Ordinal));
        var levels = m.Fix.SelectMany(g => g.Cards).Single(c => c.Field == "building.other_level_egress_into_corridors");
        Assert.Equal((FixKind.Answer, "Say whether another level's occupants reach the corridors"), (levels.Kind, levels.Headline));
        Assert.Equal(Marks.OtherLevelsReachCorridors, Marks.All.Single(k => k.Feeds == levels.Field));
    }

    [Fact]
    public void The_occupancy_group_and_sprinkler_system_are_questions_to_answer()
    {
        var raw = Answer();
        var m = ResultViews.Build(Parse(raw));
        var answer = m.Fix.Single(g => g.Kind == FixKind.Answer);
        // the occupancy group, the special egress spaces, fixed seating and the sprinkler system are each a question
        // card listing exactly the rows in review that ask it, counted from the answer (no number a rule change moves)
        foreach (var field in new[] { "building.occupancy_groups", "building.special_egress_spaces", "building.assembly_fixed_seating",
                                      "building.sprinkler_system" })
        {
            var asking = AskingFor(raw, field);
            Assert.NotEmpty(asking);
            Assert.Equal(asking.Order(StringComparer.Ordinal),
                         answer.Cards.Single(c => c.Field == field).Rows.Select(r => r.Id).Order(StringComparer.Ordinal));
        }
        // the card most results wait on comes first
        Assert.Equal(answer.Cards.Max(c => c.Rows.Count), answer.Cards[0].Rows.Count);
        // the title counts the questions shown: the six ADU follow-ups (three on "Is there an ADU?", three on "Is the
        // ADU detached?") wait until their parent is answered
        Assert.Equal(6, answer.Cards.Count(c => c.DependsOn is not null));
        Assert.Equal($"Answer {answer.Cards.Count - 6} questions about the project", answer.Title);
        Assert.DoesNotContain(m.Fix.Where(g => g.Kind != FixKind.Answer).SelectMany(g => g.Cards),
                              c => c.Field is { } f && (f.StartsWith("facts.", StringComparison.Ordinal) || f.StartsWith("building.", StringComparison.Ordinal)));
        var notChecked = m.Fix.SingleOrDefault(g => g.Kind == FixKind.NotChecked);
        Assert.Equal(Count(raw, "not_checked"), notChecked?.Rows.Count ?? 0);
        if (notChecked is not null)
            Assert.Equal("Not checked yet by Gordium", notChecked.Title);
    }

    [Fact]
    public void A_row_in_review_with_no_ask_or_an_unknown_kind_is_a_person_s_to_decide_never_dropped()
    {
        var result = Answer();
        var items = Items(result);
        var bare = items.First(i => (string?)i!["status"] == "needs_review")!;
        bare.AsObject().Remove("asks");
        var odd = items.Last(i => (string?)i!["status"] == "needs_review" && i!["asks"] is JsonArray { Count: > 0 })!;
        odd["asks"]![0]!["kind"] = "something_new";
        var m = ResultViews.Build(Parse(result));
        var decide = m.Fix.Single(g => g.Kind == FixKind.Decide);
        Assert.Contains(decide.Rows, r => r.Id == (string?)bare["id"]);
        Assert.Contains(decide.Rows, r => r.Id == (string?)odd["id"]);
    }

    [Fact]
    public void By_code_holds_every_row_exactly_once()
    {
        var result = Apartment();
        var m = ResultViews.Build(result);
        var ids = m.Code.SelectMany(RowsIn).Select(r => r.Id).ToList();
        Assert.Equal(result.Items.Select(i => i.Id).Order(), ids.Order());
    }

    [Fact]
    public void By_code_shows_the_governing_book_with_why_and_not_the_one_that_doesn_t_govern()
    {
        var m = ResultViews.Build(Apartment());
        // the rows the checker sends without a place in the code (the not-checked-yet gaps, the code choice) last
        Assert.Equal(["City of Ithaca Code, Chapter 325 Zoning (full text)", "2025 Building Code of New York State (BCNYS)",
                      ResultViews.Unplaced], m.Code.Select(d => d.Title));
        Assert.StartsWith("Governs this building: ", m.Code[1].Note, StringComparison.Ordinal);
        Assert.Null(m.Code[0].Note);
        // the chapters Gordium has no rows in are greyed and folded, never hidden
        var folds = m.Code[1].Children.Where(c => c.Level == CodeLevel.Others).ToList();
        Assert.NotEmpty(folds);
        Assert.All(folds, f => Assert.True(f.Greyed && f.Children.Count >= 2 && f.Children.All(c => c.Greyed && c.Level == CodeLevel.Chapter)));
        Assert.Contains("chapters not checked yet", m.Code[1].Line, StringComparison.Ordinal);
        Assert.Contains("appendices not checked yet", m.Code[1].Line, StringComparison.Ordinal);
    }

    /// <summary>The pieces of a section the contents say aren't checked yet (or the rest of a section only partly
    /// brought in) keep that section from green even when every row in it complies (review round 1: a section with
    /// rows was judged by its rows alone).</summary>
    [Fact]
    public void A_section_whose_rows_all_comply_is_not_green_while_a_piece_of_it_is_not_checked_yet()
    {
        var result = AllComplyButOneSection();
        var m = ResultViews.Build(Parse(result));
        var sections = Walk(m.Code).Where(n => n.Level == CodeLevel.Section && !n.Greyed).ToList();
        var zoning825 = sections.Single(n => n.Number == "325-8");
        var bc1020 = sections.Single(n => n.Number == "1020");
        foreach (var n in new[] { zoning825, bc1020 })
        {
            Assert.All(RowsIn(n), r => Assert.Equal(Verdict.Complies, r.Verdict));
            Assert.Equal(CodeState.NotCheckedYet, n.State);
            Assert.Contains("not checked yet", n.Line, StringComparison.Ordinal);
        }
        // the class: every section the contents list with a piece not checked yet, or not whole, is never green
        var listed = result["view"]!["contents"]!.AsArray().SelectMany(d => d!["chapters"]!.AsArray())
                           .SelectMany(c => c!["sections"]!.AsArray())
                           .Where(x => x!["whole"]?.GetValue<bool>() != true
                                       || x!["pieces"]?.AsArray().Any(p => (string?)p!["coverage"] is "not_checked_yet" or "not_brought_in") == true)
                           .Select(x => (string?)x!["number"]).ToHashSet();
        Assert.Contains("1020", listed);
        Assert.All(sections.Where(n => listed.Contains(n.Number)), n => Assert.NotEqual(CodeState.Complies, n.State));
    }

    /// <summary>Greyed runs are folded where they are, in the document's order, and named as the document names them:
    /// the zoning chapter's articles, never "chapters" (review round 1).</summary>
    [Fact]
    public void Greyed_runs_fold_in_place_and_are_named_as_the_document_names_them()
    {
        var zoning = ResultViews.Build(Apartment()).Code[0];
        var titles = zoning.Children.Select(c => c.Level == CodeLevel.Others ? c.Title : c.Number).ToList();
        Assert.Equal("I", titles[0]);
        Assert.Contains("Articles III–IV", titles);
        Assert.True(titles.IndexOf("Articles III–IV") > titles.IndexOf("II") && titles.IndexOf("Articles III–IV") < titles.IndexOf("V"));
        Assert.Contains("articles not checked yet", zoning.Line, StringComparison.Ordinal);
        Assert.DoesNotContain("chapter", zoning.Line, StringComparison.Ordinal);
    }

    /// <summary>A section with no rows is "nothing to check" only when all of it was brought in and none of its pieces
    /// waits for rules (review round 2): BCNYS 903 (sprinkler systems) is a reference section only partly brought in,
    /// so the rest of it (903.2, where sprinklers are required) is not checked yet, and so is its chapter.</summary>
    [Fact]
    public void A_section_only_partly_brought_in_is_not_checked_yet_even_with_no_rows()
    {
        // BCNYS chapter 9 as if every section in it were a whole reference section, then with 903 only partly brought in
        static JsonNode Chapter9(bool whole903)
        {
            var result = Answer();
            var bc = result["view"]!["contents"]!.AsArray().Single(d => ((string?)d!["document"])!.StartsWith("2025 Building Code", StringComparison.Ordinal))!;
            var ch9 = bc["chapters"]!.AsArray().Single(c => (string?)c!["number"] == "9")!;
            foreach (var sec in ch9["sections"]!.AsArray())
            {
                sec!["coverage"] = "not_for_checking";
                sec["whole"] = (string?)sec["number"] != "903" || whole903;
                sec["pieces"] = new JsonArray();
            }
            return result;
        }
        CodeNode Ch9(bool whole903) => Walk(ResultViews.Build(Parse(Chapter9(whole903))).Code[1].Children)
                                           .Single(n => n.Level == CodeLevel.Chapter && n.Number == "9");
        Assert.Equal(CodeState.NothingToCheck, Ch9(true).State);
        Assert.Equal(CodeState.NotCheckedYet, Ch9(false).State);
        Assert.Equal("Not checked yet by Gordium", Ch9(false).Line);
    }

    /// <summary>A fold's title says only what is true of every part in it (review round 2): chapters and appendices are
    /// two folds, never "Parts 11–S"; a section's pieces not checked yet are counted, not given a range that would take
    /// in a piece between them that is checked.</summary>
    [Fact]
    public void A_fold_names_one_kind_and_gives_a_range_only_for_parts_side_by_side()
    {
        var m = ResultViews.Build(Apartment());
        var bcFolds = m.Code[1].Children.Where(c => c.Level == CodeLevel.Others).Select(c => c.Title).ToList();
        Assert.Contains(bcFolds, t => t.StartsWith("Chapters ", StringComparison.Ordinal) && t.EndsWith("–35", StringComparison.Ordinal));
        Assert.Contains(bcFolds, t => t.StartsWith("Appendices A–", StringComparison.Ordinal));
        var folds = Walk(m.Code).Where(n => n.Level == CodeLevel.Others).ToList();
        Assert.All(folds, f => Assert.All(f.Children, c => Assert.Equal(f.Kind, c.Kind)));
        Assert.DoesNotContain(folds, f => f.Title.StartsWith("Parts", StringComparison.Ordinal) || f.Title.Contains(" –", StringComparison.Ordinal));
        var s318 = Walk(m.Code).Single(n => n.Level == CodeLevel.Section && n.Number == "325-18");
        Assert.All(s318.Children.Where(c => c.Level == CodeLevel.Others), f => Assert.DoesNotContain("–", f.Title, StringComparison.Ordinal));
    }

    /// <summary>By code says which code governs only where it can (review round 3): the apartment's answer does; with no
    /// contents, or no reason sent, it doesn't, so the pane keeps the which-code line at its top.</summary>
    [Fact]
    public void By_code_says_which_code_governs_only_when_it_has_the_book_and_the_reason()
    {
        var m = ResultViews.Build(Apartment());
        Assert.True(m.ShowsWhichCode);
        // the law's own words behind the choice are where it is shown (the governing book's note, on hover)
        var governing = m.Code.Single(d => d.Note is not null);
        Assert.Contains("R101.2", governing.NoteTooltip, StringComparison.Ordinal);
        var list = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsList.cs"));
        Assert.Contains("ToolTip = n.NoteTooltip", list, StringComparison.Ordinal);
        // and to a screen reader and the keyboard (review rounds 4, 5): on the list item the keyboard focuses
        var entry = ResultViewList.Layout(m, [], ResultsViewKind.ByCode, new HashSet<string>(), null, null, false)
                                  .OfType<CodeNodeEntry>().Single(n => n.Node.Note is not null);
        Assert.Contains("Governs this building", ResultViewList.Spoken(entry), StringComparison.Ordinal);
        Assert.Contains("R101.2", ResultViewList.Tip(entry), StringComparison.Ordinal);
        var select = list[list.IndexOf("public override W.Style SelectStyle(", StringComparison.Ordinal)..];
        Assert.Contains("if (item is ListItem { Spoken: { } spoken } li)\n        {\n            W.Automation.AutomationProperties.SetName(c, spoken);\n            c.ToolTip = li.Tip;", select, StringComparison.Ordinal);
        Assert.Contains("internal override string? Spoken => ResultViewList.Spoken(Entry);", list, StringComparison.Ordinal);
        var none = Answer();
        none["view"]!["contents"] = new JsonArray();
        Assert.False(ResultViews.Build(Parse(none)).ShowsWhichCode);
        var noWhy = Answer();
        noWhy["which_code"]!.AsObject().Remove("why");
        Assert.False(ResultViews.Build(Parse(noWhy)).ShowsWhichCode);
    }

    /// <summary>The class rule of change 34, over every node: complies only when every row inside complies or doesn't
    /// apply and nothing inside is not checked yet; fails or review whenever a row inside does.</summary>
    [Fact]
    public void No_node_is_green_while_anything_inside_fails_needs_review_or_is_not_checked_yet()
    {
        foreach (var result in new[] { Apartment(), Parse(AllComplyButOneSection()) })
            foreach (var n in Walk(ResultViews.Build(result).Code))
            {
                var rows = RowsIn(n).ToList();
                if (rows.Any(r => r.Verdict == Verdict.DoesNotComply))
                    Assert.Equal(CodeState.Fails, n.State);
                else if (rows.Any(r => r.Verdict == Verdict.NeedsReview))
                    Assert.Equal(CodeState.Review, n.State);
                if (n.State == CodeState.Complies)
                {
                    Assert.All(rows, r => Assert.Contains(r.Verdict, new[] { Verdict.Complies, Verdict.NotApplicable }));
                    Assert.DoesNotContain(Walk(n.Children), c => c.State == CodeState.NotCheckedYet);
                }
            }
    }

    /// <summary>The apartment's answer with every row complying: the zoning chapter's sections Gordium has no rows for
    /// keep its chapter from green.</summary>
    private static JsonNode AllComplyButOneSection()
    {
        var result = Answer();
        foreach (var i in Items(result))
        {
            i!["status"] = "complies";
            i.AsObject().Remove("asks");
        }
        return result;
    }

    [Fact]
    public void A_chapter_where_every_row_complies_is_not_green_while_a_section_in_it_is_not_checked_yet()
    {
        var m = ResultViews.Build(Parse(AllComplyButOneSection()));
        var zoning = m.Code[0];
        var article = zoning.Children.First(c => c.Level == CodeLevel.Chapter && !c.Greyed && Walk(c.Children).Any(x => x.State == CodeState.NotCheckedYet));
        Assert.All(RowsIn(article), r => Assert.Equal(Verdict.Complies, r.Verdict));
        Assert.Equal(CodeState.NotCheckedYet, article.State);
        Assert.Contains("not checked yet", article.Line, StringComparison.Ordinal);
        Assert.Equal(CodeState.NotCheckedYet, zoning.State);
        Assert.Contains(Walk(m.Code), n => n.Level == CodeLevel.Rule && n.State == CodeState.Complies);
    }

    [Fact]
    public void A_row_the_contents_can_t_place_is_shown_on_its_own_never_dropped()
    {
        var result = Answer();
        var item = Items(result)[0]!;
        item.AsObject().Remove("in_code");
        var m = ResultViews.Build(Parse(result));
        var last = m.Code[^1];
        Assert.Equal(ResultViews.Unplaced, last.Title);
        Assert.Contains(RowsIn(last), r => r.Id == (string?)item["id"]);
        Assert.Equal(Items(result).Count, m.Code.SelectMany(RowsIn).Count());
    }
}
