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
        Assert.Equal("98 need review · 8 not checked yet · 1 complies · 1 doesn't apply", m.Summary);
        Assert.Equal("Nothing fails yet. 98 results can't be decided until the questions below are answered.", m.Headline);
        Assert.Equal("1 fails · 2 need review", ResultViews.Summary([Verdict.NeedsReview, Verdict.DoesNotComply, Verdict.NeedsReview]));
        Assert.Equal("1 rule fails. Fix it first; 2 results also need review.",
                     ResultViews.Headline([Verdict.NeedsReview, Verdict.DoesNotComply, Verdict.NeedsReview]));
        // never "complies" as the whole story: Gordium doesn't check every part of the code
        Assert.Contains("doesn't check every part", ResultViews.Headline([Verdict.Complies]), StringComparison.Ordinal);
        Assert.Contains("not checked yet", ResultViews.Headline([Verdict.Complies, Verdict.NotChecked]), StringComparison.Ordinal);
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
    public void The_occupancy_group_and_sprinkler_system_are_questions_to_answer()
    {
        var m = ResultViews.Build(Apartment());
        var answer = m.Fix.Single(g => g.Kind == FixKind.Answer);
        Assert.Equal(["building.sprinkler_system", "building.occupancy_groups"], answer.Cards.Take(2).Select(c => c.Field));
        Assert.Equal([28, 22], answer.Cards.Take(2).Select(c => c.Rows.Count));
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
        var others = m.Code[1].Children.Single(c => c.Level == CodeLevel.Others);
        Assert.True(others.Greyed);
        Assert.Contains("chapters not checked yet", m.Code[1].Line, StringComparison.Ordinal);
        Assert.All(others.Children, c => Assert.Equal(CodeLevel.Chapter, c.Level));
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
