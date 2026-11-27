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
/// node is never green while anything in it fails, needs review or isn't checked yet; nothing here makes a verdict.</summary>
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

    [Fact]
    public void The_top_says_the_checker_s_counts_and_what_they_mean()
    {
        var m = ResultViews.Build(Apartment());
        Assert.Equal("546 need review · 8 not checked yet · 31 comply · 1 doesn't apply", m.Summary);   // group 2's story exits: +8; group 3's 1004.7 and 1004.9 flags: +2; group 4a's corridor width and capacity (2 corridors each) and the mixed-building flag: +5; group 4b's seven Table 1020.2 rows and the fire-partition flag (2 corridors each), and its mixed, Group I-2 and hoistway flags: +19; group 4c's obstruction and air-movement flags and the continuity flag (2 corridors): +4; group 5a's stairway and other-component capacity flags: +2; group 5b's continuity, distribution and convergence flags: +3; group 5c's three encroachment flags: +3; group 6a's door width (10 doors, needs review: leaves not stated) and its three flags: +13, its door height (10 doors) complies: +10; group 6b's door swing (10 doors, needs review: the side each swings into isn't stated): +10, its door-kind flag (10 doors, side-hinged) doesn't apply; group 6c's forces, floor-level, landing, threshold and doors-in-series flags: +5, its sliding-latch flag (10 doors, side-hinged) doesn't apply; group 6d's eight door-operation flags and its educational-locking flag (the group isn't stated as sent): +9; group 6e's panic hardware rule (10 doors, needs review: the group isn't stated) and its twelve flags (controlled egress among them, the group not stated): +22; group 8a's escape-opening rule and its three flags (the group not stated): +5; group 8b's five escape-opening size rules (the group not stated): +5; group 8c's seven area-well rules and its drainage and bars flags: +9; group 9a's 1003 and 1012 ramp flags: +26; group 9b's lighting and exit-sign flags (the group not stated): +17; group 9c's accessible-egress flags (the group and system not stated): +27; group 9d's aisle and exit-access-stairway flags (the group not stated): +5; group 9e's egress-balcony, exit and exit-stairway flags: +26; group 9f's exit-passageway and luminous-marking flags (the group not stated): +24; group 9g's horizontal-exit, exterior-stairway, exit-discharge and egress-court flags: +18; group 9h's Section 1030 assembly flags (the group not stated, assembly spaces not ruled out): +25; group 9i's 1030.10 to 1030.17 assembly flags: +37
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

    [Fact]
    public void What_to_fix_holds_every_row_and_each_ask_of_each_row_in_review()
    {
        var result = Apartment();
        var m = ResultViews.Build(result);
        var all = m.Fix.SelectMany(g => g.Rows).Select(r => r.Id).ToHashSet();
        Assert.All(result.Items, i => Assert.Contains(i.Id, all));
        Assert.Equal(m.Fix.Select(g => g.Kind).OrderBy(k => k), m.Fix.Select(g => g.Kind));          // the design's order
        foreach (var item in result.Items.Where(i => i.Status == Verdict.NeedsReview))
            foreach (var ask in ResultViews.Asks(item.Raw))
            {
                var card = m.Fix.SelectMany(g => g.Cards).Single(c => c.Key == ask.Key && c.Kind == ResultViews.KindOf(ask.Kind, ask.Field));
                Assert.Contains(card.Rows, r => r.Id == item.Id);
                Assert.All(ask.Elements, e => Assert.Contains(e, card.Elements));
            }
        // a group's rows are its cards' rows, each once
        Assert.All(m.Fix, g => Assert.Equal(g.Cards.SelectMany(c => c.Rows).Select(r => r.Id).Distinct().Count(), g.Rows.Count));
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
        var m = ResultViews.Build(Apartment());
        var answer = m.Fix.Single(g => g.Kind == FixKind.Answer);
        // the cards most results wait on come first: the occupancy group, then (NY Building Code egress for every
        // group, PR #181) the special egress spaces and fixed seating, then the sprinkler system
        Assert.Equal("building.occupancy_groups", answer.Cards[0].Field);
        Assert.Equal(221, answer.Cards[0].Rows.Count);                 // group 2's story-exit rules read it too; group 4a's corridor width (2); group 4b's Table 1020.2 rows (7 x 2); group 5a's corridor capacity rule (2); group 6a's door width (10 doors: Group I-2's 41 1/2 in); group 6b's door swing (10 doors: Group H); group 6e's panic hardware (10 doors: Groups A, E and H); group 8a's escape-opening rule, 8b's five size rules and 8c's seven area-well rules (Groups R-2, R-3 and R-4)
        Assert.Equal(60, answer.Cards.Single(c => c.Field == "building.sprinkler_system").Rows.Count);   // group 4b: Table 1020.2 rows whose answer turns on the system (8)
        Assert.Equal(82, answer.Cards.Single(c => c.Field == "building.special_egress_spaces").Rows.Count);
        Assert.Equal(84, answer.Cards.Single(c => c.Field == "building.assembly_fixed_seating").Rows.Count);   // group 5a: the corridor capacity rule (2)
        Assert.Equal($"Answer {answer.Cards.Count} questions about the project", answer.Title);
        Assert.DoesNotContain(m.Fix.Where(g => g.Kind != FixKind.Answer).SelectMany(g => g.Cards),
                              c => c.Field is { } f && (f.StartsWith("facts.", StringComparison.Ordinal) || f.StartsWith("building.", StringComparison.Ordinal)));
        Assert.Equal("Not checked yet by Gordium", m.Fix.Single(g => g.Kind == FixKind.NotChecked).Title);
        Assert.Equal(8, m.Fix.Single(g => g.Kind == FixKind.NotChecked).Rows.Count);
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
