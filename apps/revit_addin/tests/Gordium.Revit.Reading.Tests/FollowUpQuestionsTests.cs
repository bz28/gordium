using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>A follow-up question in the questions card (an ask's <c>depends_on</c>, #226): "Is the ADU detached?" is
/// held back until "Is there an ADU?" is answered, hidden once that answer makes it moot (No), and shown right after
/// its parent once answered otherwise (Yes). Only the card's order and visibility change: every result stays in
/// review, a follow-up not shown leaves its results on the question shown above it, and the top sentence counts the
/// results waiting on the questions as before.</summary>
public sealed class FollowUpQuestionsTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static readonly string File_ = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests",
                                                         "answers", "four_unit_apartment_check_answer.json");

    private static ResultModel Apartment()
    {
        var doc = JsonDocument.Parse(File.ReadAllText(File_, Encoding.UTF8));
        return ResultRows.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About)), "New Construction", [], null);
    }

    /// <summary>How many of the answer's results need review, read from its JSON (never through the pane): the checker's
    /// word, and "not applicable" with no reason, as ResultViewsTests counts them (the answer is made, so no number is
    /// written here).</summary>
    private static int InReview() =>
        JsonNode.Parse(File.ReadAllText(File_, Encoding.UTF8))!["result"]!["view"]!["items"]!.AsArray()
                .Count(i => (string?)i!["status"] is "needs_review"
                            || ((string?)i!["status"] is "not_applicable" && string.IsNullOrWhiteSpace((string?)i!["reason"])));

    private static IReadOnlyList<SetupField> Fields() =>
        SetupScreen.Build(new RevitModel { Document = "apartment.rvt", Marked = [], ProjectMarks = new Dictionary<Guid, MarkValue>() }, [], null).Fields;

    private static FixGroup Answers(ResultModel m) => m.Views!.Fix.Single(g => g.Kind == FixKind.Answer);

    private static List<string?> Shown(ResultModel m, SetupDraft? draft = null) =>
        [.. ProjectQuestions.Of(Answers(m), Fields(), draft).Select(q => q.Card.Field)];

    private const string Adu = "facts.accessory_dwelling_unit";
    private const string Detached = "facts.adu_detached";

    private static readonly string[] OnAdu = ["facts.adus_on_parcel", "facts.adu_bedrooms", Detached];
    private static readonly string[] OnDetached = ["facts.adu_existing_building", "facts.adu_floor_area", "facts.primary_floor_area"];

    private static SetupDraft Draft(params (MarkDefinition Mark, string Value)[] chosen)
    {
        var d = new SetupDraft();
        foreach (var (mark, value) in chosen)
            d.Choose(mark, value);
        return d;
    }

    private static readonly MarkDefinition AduDetachedMark = Marks.All.Single(x => x.Feeds == Detached);

    [Fact]
    public void An_ask_reads_the_question_it_hangs_on_and_the_answers_that_make_it_moot()
    {
        var ask = JsonDocument.Parse("""{"kind": "mark", "key": "k", "headline": "Is the ADU detached?", "field": "facts.adu_detached", "depends_on": {"field": "facts.accessory_dwelling_unit", "moot_if": [false, true, "None", 0]}}""").RootElement;
        var d = ResultViews.DependsOnOf(ask)!;
        Assert.Equal(Adu, d.Field);
        Assert.Equal(["No", "Yes", "None", "0"], d.MootIf);
        // with no moot answers it still hangs on its parent; with none, or no field, it is asked as any other
        Assert.Empty(ResultViews.DependsOnOf(JsonDocument.Parse("""{"depends_on": {"field": "facts.x"}}""").RootElement)!.MootIf);
        Assert.Null(ResultViews.DependsOnOf(JsonDocument.Parse("""{"key": "k"}""").RootElement));
        Assert.Null(ResultViews.DependsOnOf(JsonDocument.Parse("""{"depends_on": {"moot_if": [false]}}""").RootElement));
        // the row's asks carry it, and the apartment's cards do: every follow-up names its parent
        var row = JsonDocument.Parse("""{"asks": [{"kind": "mark", "key": "k", "headline": "h", "field": "facts.adu_detached", "depends_on": {"field": "facts.accessory_dwelling_unit", "moot_if": [false]}}]}""").RootElement;
        Assert.Equal(["No"], Assert.Single(ResultViews.Asks(row)).DependsOn!.MootIf);
        var cards = Answers(Apartment()).Cards;
        foreach (var f in OnAdu)
            Assert.Equal(Adu, cards.Single(c => c.Field == f).DependsOn!.Field);
        foreach (var f in OnDetached)
            Assert.Equal(Detached, cards.Single(c => c.Field == f).DependsOn!.Field);
        Assert.Null(cards.Single(c => c.Field == Adu).DependsOn);
    }

    [Fact]
    public void A_follow_up_is_held_back_until_its_parent_is_answered_and_its_results_wait_on_the_parent()
    {
        var m = Apartment();
        var group = Answers(m);
        var shown = Shown(m);
        Assert.Contains(Adu, shown);
        foreach (var f in OnAdu.Concat(OnDetached))
            Assert.DoesNotContain(f, shown);
        Assert.Equal(group.Cards.Count - 6, shown.Count);
        // never dropped: every result of the card is on a question shown, still in review
        var questions = ProjectQuestions.Of(group, Fields());
        foreach (var r in group.Rows)
            Assert.Contains(questions, q => q.Card.Rows.Contains(r));
        var adu = questions.Single(q => q.Card.Field == Adu);
        foreach (var c in group.Cards.Where(c => OnAdu.Concat(OnDetached).Contains(c.Field)))
            Assert.All(c.Rows, r => Assert.Contains(r, adu.Card.Rows));
        // the title counts the questions shown, at the check and as laid out
        Assert.Equal($"Answer {shown.Count} questions about the project", group.Title);
        var open = new HashSet<string> { ResultViewList.GroupKey(group), ResultViewList.MoreQuestionsKey };
        var layout = ResultViewList.Layout(m.Views!, ResultList.Place(m), ResultsViewKind.WhatToFix, open, null, null, false, Fields());
        Assert.Equal(group.Title, layout.OfType<FixGroupEntry>().Single(g => g.Group.Kind == FixKind.Answer).Group.Title);
        Assert.Equal(shown, layout.OfType<QuestionEntry>().Select(q => q.Question.Card.Field).ToList());
    }

    [Fact]
    public void Yes_brings_the_follow_ups_in_right_after_their_parent_and_no_hides_them()
    {
        var m = Apartment();
        var yes = Shown(m, Draft((Marks.AccessoryDwellingUnit, "Yes")));
        var at = yes.IndexOf(Adu);
        Assert.Equal(OnAdu.OrderBy(f => f, StringComparer.Ordinal), yes.Skip(at + 1).Take(3).OfType<string>().OrderBy(f => f, StringComparer.Ordinal));   // right after "Is there an ADU?"
        foreach (var f in OnDetached)
            Assert.DoesNotContain(f, yes);                                      // their parent, detached, not answered yet
        // detached Yes: in an existing building? is asked; the attached ADU's sizes are moot
        var detached = Shown(m, Draft((Marks.AccessoryDwellingUnit, "Yes"), (AduDetachedMark, "Yes")));
        Assert.Equal("facts.adu_existing_building", detached[detached.IndexOf(Detached) + 1]);
        Assert.DoesNotContain("facts.adu_floor_area", detached);
        Assert.DoesNotContain("facts.primary_floor_area", detached);
        // detached No: the sizes are asked, the existing building moot
        var attached = Shown(m, Draft((Marks.AccessoryDwellingUnit, "Yes"), (AduDetachedMark, "No")));
        Assert.Contains("facts.adu_floor_area", attached);
        Assert.Contains("facts.primary_floor_area", attached);
        Assert.DoesNotContain("facts.adu_existing_building", attached);
        // No: every follow-up hidden, a detached answer chosen before included (its parent is moot)
        var no = Shown(m, Draft((Marks.AccessoryDwellingUnit, "No"), (AduDetachedMark, "No")));
        Assert.Equal(Shown(m), no);
        foreach (var f in OnAdu.Concat(OnDetached))
            Assert.DoesNotContain(f, no);
        // an answer the mark already holds counts as the parent's answer, as the card shows it selected
        var held = SetupScreen.Build(new RevitModel
        {
            Document = "apartment.rvt", Marked = [],
            ProjectMarks = new Dictionary<Guid, MarkValue> { [Marks.AccessoryDwellingUnit.Guid] = new(true, 1) },
        }, [], null).Fields;
        Assert.Contains(Detached, ProjectQuestions.Of(Answers(m), held).Select(q => q.Card.Field));
    }

    [Fact]
    public void A_follow_up_not_shown_is_never_saved_and_no_result_is_ever_passed()
    {
        var m = Apartment();
        var draft = Draft((Marks.AccessoryDwellingUnit, "No"), (AduDetachedMark, "Yes"));
        var questions = ProjectQuestions.Of(Answers(m), Fields(), draft);
        var write = Assert.Single(ProjectQuestions.Writes(questions, draft).Writes);  // only "Is there an ADU?"
        Assert.Equal(Marks.AccessoryDwellingUnit, write.Mark);
        Assert.Equal(1, ProjectQuestions.Unsaved(questions, draft));
        // every result is laid out as before: the follow-ups' results in review under the ADU question
        var open = new HashSet<string> { ResultViewList.GroupKey(Answers(m)), ResultViewList.MoreQuestionsKey };
        open.UnionWith(questions.Select(q => ResultViewList.CardKey(q.Card)));
        var layout = ResultViewList.Layout(m.Views!, ResultList.Place(m), ResultsViewKind.WhatToFix, open, null, null, false, Fields(), draft);
        var rows = layout.OfType<ListRowEntry>().Select(r => r.Row).ToList();
        foreach (var c in Answers(m).Cards.Where(c => c.DependsOn is not null))
            foreach (var r in c.Rows)
            {
                Assert.Contains(rows, p => p.Row.Id == r.Id);
                Assert.Equal(Verdict.NeedsReview, r.Verdict);
                Assert.All(rows.Where(p => p.Row.Id == r.Id), p => Assert.NotEqual(PanelStatus.Complies, p.Status));
            }
        Assert.StartsWith($"{InReview()} need review", m.Views!.Summary, StringComparison.Ordinal);   // every one still counted
    }

    /// <summary>Review round 1: a result's page offered the follow-ups the card held back ("Answer 5 questions" with one
    /// question in the card).</summary>
    [Fact]
    public void A_results_page_offers_the_questions_the_card_shows()
    {
        var m = Apartment();
        var placed = ResultList.Place(m);
        var at = placed.ToList().FindIndex(p => p.Row.Id.EndsWith("adu_attached_size", StringComparison.Ordinal));
        var p = placed[at];
        DetailPage Page(SetupDraft? draft) =>
            DetailPages.Of(Details.Of(p, at, placed.Count, null, null), p, ResultViews.CardsOf(m.Views!, p.Row.Id, Fields(), draft));
        var held = Page(null);
        Assert.Equal("Answer 1 question", held.ActionWords);
        Assert.Contains(held.Steps, s => s.StartsWith("Is there an ADU", StringComparison.Ordinal));
        Assert.DoesNotContain(held.Steps, s => s.StartsWith("Is the ADU detached", StringComparison.Ordinal));
        Assert.Equal("Answer 2 questions", Page(Draft((Marks.AccessoryDwellingUnit, "Yes"))).ActionWords);
        Assert.Equal("Answer 1 question", Page(Draft((Marks.AccessoryDwellingUnit, "No"))).ActionWords);
        // without the fields (not read), the follow-ups are held back the same way
        Assert.Equal(1, ResultViews.CardsOf(m.Views!, p.Row.Id).Count(c => c.Kind == FixKind.Answer));
    }

    [Fact]
    public void The_top_sentence_counts_the_held_back_results_as_waiting_on_the_questions_shown()
    {
        var m = Apartment();
        var group = Answers(m);
        var review = m.Views!.Fix.SelectMany(g => g.Rows).Where(r => r.Verdict == Verdict.NeedsReview).Select(r => r.Id).Distinct().Count();
        var asked = group.Rows.Where(r => r.Verdict == Verdict.NeedsReview).Select(r => r.Id).Distinct().Count();
        Assert.Equal($"Nothing fails yet. {review} results need review; {asked} of them wait on the questions below.", m.Views.Headline);
        // one question shown, its follow-ups held: "the question below", and every result counted
        var row = Row("r1");
        var parent = Card(Adu, row);
        var child = Card(Detached, row, Row("r2")) with { DependsOn = new DependsOn(Adu, ["No"]) };
        var one = new FixGroup(FixKind.Answer, "", null, [parent, child], [row, child.Rows[1]]);
        Assert.Equal([parent.Key], ProjectQuestions.Of(one, null).Select(q => q.Card.Key));
        Assert.Equal("Nothing fails yet. 2 results can't be decided until the question below is answered.",
                     ResultViews.Headline([(Verdict.NeedsReview, "r1"), (Verdict.NeedsReview, "r2")], onQuestions: 2,
                                          questions: ProjectQuestions.Of(one, null).Count));
        // review round 1: the sentence follows the card, as its title does: Yes brings the follow-up in, "the questions"
        var model = new ResultViewsModel("", "", [one], [])
        {
            HeadlineRows = [(Verdict.NeedsReview, "r1"), (Verdict.NeedsReview, "r2")], OnQuestions = 2,
        };
        Assert.Equal("Nothing fails yet. 2 results can't be decided until the question below is answered.",
                     ResultViews.HeadlineOf(model, Fields(), null));
        Assert.Equal("Nothing fails yet. 2 results can't be decided until the questions below are answered.",
                     ResultViews.HeadlineOf(model, Fields(), Draft((Marks.AccessoryDwellingUnit, "Yes"))));
        Assert.Equal(ResultViews.HeadlineOf(model, Fields(), null), ResultViews.HeadlineOf(model, Fields(), Draft((Marks.AccessoryDwellingUnit, "No"))));
        // the apartment's model says what Build said
        Assert.Equal(m.Views.Headline, ResultViews.HeadlineOf(m.Views, null, null));
        // the pane draws the sentence from it and says it again on each answer chosen; the page and list use the card's questions
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        Assert.Contains("Text = model.Views is { } v ? ResultViews.HeadlineOf(v, _content?.Questions, _answers)", view, StringComparison.Ordinal);
        Assert.Contains("_headline.Text = ResultViews.HeadlineOf(views, _content.Questions, _answers);", view, StringComparison.Ordinal);
        Assert.Contains("if (ResultViewList.QuestionsDiffer(_entries, after))", view, StringComparison.Ordinal);
        Assert.Contains("ResultViews.CardsOf(views, id, _content?.Questions, _answers)", view, StringComparison.Ordinal);
        Assert.Contains("ResultViewList.PathTo(views, _view, id, _content?.Questions, _answers)", view, StringComparison.Ordinal);
        Assert.Contains("ResultViewList.AnswerKeys(views, id, _content?.Questions, _answers)", view, StringComparison.Ordinal);
    }

    private static ResultRow Row(string id) => new(id, id, Verdict.NeedsReview, "NEEDS REVIEW", Tone.Review, null, null, null, null, [], []);

    private static FixCard Card(string field, params ResultRow[] rows) =>
        new("mark:" + field, FixKind.Answer, field, null, field, [], rows);

    [Fact]
    public void A_held_follow_ups_own_result_goes_to_its_parents_card_and_can_be_reached()
    {
        var shared = Row("shared");
        var own = Row("own");
        var parent = Card(Adu, shared);
        var child = Card(Detached, shared, own) with { DependsOn = new DependsOn(Adu, ["No"]) };
        var grand = Card("facts.adu_existing_building", Row("deep")) with { DependsOn = new DependsOn(Detached, ["No"]) };
        var group = new FixGroup(FixKind.Answer, "", null, [child, parent, grand], [shared, own, grand.Rows[0]]);
        var q = Assert.Single(ProjectQuestions.Of(group, null));
        Assert.Equal(parent.Key, q.Card.Key);
        Assert.Equal(["shared", "own", "deep"], q.Card.Rows.Select(r => r.Id));   // carried, each once
        Assert.Equal(3, q.Affects);
        var model = new ResultViewsModel("", "", [group], []);
        Assert.Equal([ResultViewList.GroupKey(group), ResultViewList.CardKey(parent)], ResultViewList.PathTo(model, ResultsViewKind.WhatToFix, "deep"));
        Assert.Equal([ResultViewList.GroupKey(group)], ResultViewList.AnswerKeys(model, "own"));
        // the parent answered (a field for it chosen Yes): the follow-up shows after it, before its own follow-up
        var fields = SetupScreen.Build(new RevitModel { Document = "x.rvt", Marked = [], ProjectMarks = new Dictionary<Guid, MarkValue>() }, [], null).Fields;
        var both = ProjectQuestions.Of(group, fields, Draft((Marks.AccessoryDwellingUnit, "Yes"), (AduDetachedMark, "Yes")));
        Assert.Equal([parent.Key, child.Key, grand.Key], both.Select(x => x.Card.Key));
        Assert.Same(parent, both[0].Card);                                      // nothing carried: the same card
    }

    [Fact]
    public void A_follow_up_whose_parent_is_not_asked_here_or_loops_is_asked_as_any_other()
    {
        // its parent answered in the project already (not asked): the checker still asks it, so it shows
        var lone = Card(Detached, Row("a")) with { DependsOn = new DependsOn(Adu, ["No"]) };
        Assert.Single(ProjectQuestions.Of(new FixGroup(FixKind.Answer, "", null, [lone], lone.Rows), null));
        // two follow-ups naming each other: both shown, never dropped
        var a = Card("facts.a", Row("a")) with { DependsOn = new DependsOn("facts.b", []) };
        var b = Card("facts.b", Row("b")) with { DependsOn = new DependsOn("facts.a", []) };
        var loop = ProjectQuestions.Of(new FixGroup(FixKind.Answer, "", null, [a, b], [a.Rows[0], b.Rows[0]]), null);
        Assert.Equal(2, loop.Count);
        // one naming itself: shown
        var self = Card("facts.s", Row("s")) with { DependsOn = new DependsOn("facts.s", []) };
        Assert.Single(ProjectQuestions.Of(new FixGroup(FixKind.Answer, "", null, [self], self.Rows), null));
    }

    [Fact]
    public void The_list_is_drawn_again_only_when_an_answer_changes_the_questions_shown()
    {
        var m = Apartment();
        var open = new HashSet<string> { ResultViewList.GroupKey(Answers(m)), ResultViewList.MoreQuestionsKey };
        IReadOnlyList<ListEntry> Lay(SetupDraft d) =>
            ResultViewList.Layout(m.Views!, ResultList.Place(m), ResultsViewKind.WhatToFix, open, null, null, false, Fields(), d);
        var before = Lay(new SetupDraft());
        Assert.True(ResultViewList.QuestionsDiffer(before, Lay(Draft((Marks.AccessoryDwellingUnit, "Yes")))));
        Assert.False(ResultViewList.QuestionsDiffer(before, Lay(Draft((Marks.AccessoryDwellingUnit, "No")))));
        Assert.False(ResultViewList.QuestionsDiffer(before, Lay(Draft((Marks.CornerLot, "Yes")))));
        // folded to the first few: the title's count still changes, so the list is drawn again
        open.Remove(ResultViewList.MoreQuestionsKey);
        Assert.True(ResultViewList.QuestionsDiffer(Lay(new SetupDraft()), Lay(Draft((Marks.AccessoryDwellingUnit, "Yes")))));
    }
}
