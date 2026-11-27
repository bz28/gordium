using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The result detail page (DetailPages; UI polish changes 28 to 32) and the questions asked in the "Answer N
/// questions" card (ProjectQuestions; changes 22 to 24), Revit-free, on the four-unit apartment's real answer (Ben's
/// 2026-11-23 trial: answers/four_unit_apartment_check_answer.json) and 106 Ithaca Rd's (a failure). The rules each test
/// holds: no step ever says a result will pass; anything not settled ends with Check again; "Measured" only when
/// something was measured; one cite; every word of the callout is the checker's ask or a fixed sentence; a question is
/// written only from what the architect chose in the card, and a question without a field is said, never dropped.</summary>
public sealed class DetailPageTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static ResultModel Load(string name)
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", name);
        var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
        return ResultRows.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About)), "New Construction", [], null);
    }

    private static ResultModel Apartment() => Load("four_unit_apartment_check_answer.json");

    private static ResultModel House() => Load("ithaca_106_house_check_answer.json");

    /// <summary>Every row's page, as the pane opens it (every element in the model, by a made-up name).</summary>
    private static List<(ListRow Row, ResultDetail Detail, DetailPage Page)> Pages(ResultModel m, DateTime? stale = null)
    {
        var placed = ResultList.Place(m);
        var labels = placed.SelectMany(p => p.Row.Elements).Distinct(StringComparer.Ordinal)
                           .Select((u, i) => (u, i)).ToDictionary(x => x.u, x => $"Element {x.i + 1}", StringComparer.Ordinal);
        return placed.Select((p, i) =>
        {
            var d = Details.Of(p, i, placed.Count, labels, stale);
            return (p, d, DetailPages.Of(d, p, ResultViews.CardsOf(m.Views!, p.Row.Id)));
        }).ToList();
    }

    private static readonly Regex Passes = new(@"\b(will|would|now) (pass|comply|complies)\b|\bpasses\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    [Fact]
    public void Every_page_ends_with_what_moves_it_unless_settled_and_never_says_it_will_pass()
    {
        foreach (var m in new[] { Apartment(), House() })
            foreach (var (row, d, page) in Pages(m))
            {
                var settled = row.Section == ListSection.Complies;
                if (settled)
                {
                    Assert.Null(page.Headline);                       // nothing to do: no callout
                    Assert.Empty(page.Steps);
                }
                else
                {
                    Assert.NotNull(page.Headline);
                    // egress UI audit, finding 2: a result only a person can settle ends with the tick, never Check again
                    // (which changes nothing for it); anything a check can change ends with Check again
                    var asks = ResultViews.CardsOf(m.Views!, row.Row.Id).Where(c => c.Kind is not (FixKind.Fails or FixKind.NotChecked or FixKind.Done)).ToList();
                    var byHand = row.Section != ListSection.Fails && asks.All(a => DetailPages.ByHand(a.Kind));
                    Assert.Equal(byHand ? DetailPages.CheckAfterChangeStep : DetailPages.CheckAgainStep, page.Steps[^1]);   // not stale here
                    Assert.Equal(byHand, page.Steps.Contains(DetailPages.LookedStep));
                    Assert.Equal(!byHand, page.Steps.Contains(DetailPages.CheckAgainStep));
                    if (byHand)
                    {
                        Assert.True(LookedAt.Tickable(row));                       // the tick it points to is on the page
                        Assert.DoesNotContain("check again", page.Headline!, StringComparison.OrdinalIgnoreCase);
                    }
                }
                foreach (var words in page.Steps.Append(page.Headline ?? ""))
                    Assert.DoesNotMatch(Passes, words);
            }
    }

    /// <summary>Egress UI audit, finding 2: the apartment's hand checks (the corridor's fire partitions: a rating
    /// worked out by hand and a judgment) say what to check and to tick it; the model changed after the check, Check
    /// again comes first, then the tick.</summary>
    [Fact]
    public void A_result_only_a_person_settles_ends_with_the_tick_and_check_again_only_when_the_model_changed()
    {
        var pages = Pages(Apartment());
        var hand = pages.Where(p => p.Row.Section != ListSection.Complies && p.Page.Steps[^1] == DetailPages.CheckAfterChangeStep).ToList();
        Assert.NotEmpty(hand);
        Assert.Contains(hand, p => p.Page.Headline!.StartsWith("Gordium can't decide this result yet. Look at these ", StringComparison.Ordinal));
        Assert.All(hand, p => Assert.Equal(DetailPages.LookedStep, p.Page.Steps[^2]));
        Assert.Contains(pages, p => p.Page.Steps[^1] == DetailPages.CheckAgainStep);              // and the rest still do
        var stale = Pages(Apartment(), new DateTime(2026, 11, 23, 14, 32, 0));
        var after = stale.Single(p => p.Row.Row.Id == hand[0].Row.Row.Id);
        Assert.Equal([DetailPages.CheckAgainStep, DetailPages.LookedStep], after.Page.Steps.TakeLast(2));
        Assert.DoesNotContain(DetailPages.CheckAfterChangeStep, after.Page.Steps);
        // the step names the tick by its own label, which the page draws (confirm round)
        Assert.Contains(DetailPages.LookedLabel, DetailPages.LookedStep, StringComparison.Ordinal);
        Assert.Contains("host.TickDetail, DetailPages.LookedLabel)",
                        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "DetailView.cs")), StringComparison.Ordinal);
        Assert.DoesNotMatch(Passes, DetailPages.LookedStep);
        Assert.DoesNotMatch(Passes, DetailPages.CheckAfterChangeStep);
        // review round 1: never "it stays Needs review" as if for good (spot grades, a design change, a reading met can
        // let a later check decide it), never "check by hand" for an open question about the law, and "yet"
        Assert.DoesNotContain("stays", DetailPages.LookedStep + DetailPages.CheckAfterChangeStep, StringComparison.Ordinal);
        Assert.Contains("not a verdict", DetailPages.LookedStep, StringComparison.Ordinal);
        Assert.Contains("yet", DetailPages.SeveralByHand(2), StringComparison.Ordinal);
        Assert.DoesNotContain("by hand", DetailPages.SeveralByHand(2), StringComparison.Ordinal);
        Assert.Contains("only a check does", LookedAt.Tip, StringComparison.Ordinal);
    }

    [Fact]
    public void A_settled_result_the_model_changed_after_says_check_again_and_nothing_else()
    {
        var stale = Pages(Apartment(), new DateTime(2026, 11, 23, 14, 32, 0));
        var complies = stale.First(p => p.Row.Section == ListSection.Complies);
        Assert.Equal([DetailPages.CheckAgainStep], complies.Page.Steps);
        Assert.Null(complies.Page.Headline);
        Assert.NotNull(complies.Detail.Stale);
    }

    [Fact]
    public void Measured_is_shown_only_when_something_was_measured()
    {
        foreach (var m in new[] { Apartment(), House() })
            foreach (var (_, d, page) in Pages(m))
                Assert.Equal(d.Bar is not null || d.HowFar is not null || d.Figures.Any(f => f.Measured is not null), page.ShowMeasured);
        // the apartment's ADU row: "Measured: not measured" before; now nothing measured, not shown
        var adu = Pages(Apartment()).Single(p => p.Row.Row.Id == "R-3a.adu_one_per_parcel");
        Assert.False(adu.Page.ShowMeasured);
        Assert.Contains(adu.Detail.Figures, f => f.Measured is null);
        // the house's lot coverage failure: measured, shown
        Assert.Contains(Pages(House()), p => p.Row.Section == ListSection.Fails && p.Page.ShowMeasured);
    }

    [Fact]
    public void One_cite_under_the_title_and_the_first_quote_shown_with_the_rest_folded()
    {
        foreach (var (_, d, page) in Pages(Apartment()))
        {
            Assert.DoesNotContain(";", page.Cite, StringComparison.Ordinal);
            if (d.Section is { } s)
                Assert.EndsWith(s.Split(';')[0].Trim(), page.Cite, StringComparison.Ordinal);
            Assert.Equal(d.Quotes.FirstOrDefault(), page.FirstQuote);
            Assert.Equal(d.Quotes.Skip(1), page.MoreQuotes);
            Assert.Equal(d.Quotes.Count > 1 || d.Links.Count > 1, page.MoreWords is not null);
            Assert.Equal(d.Links.FirstOrDefault(), page.Open);
            Assert.Equal(d.Links.Count == 0, page.NoLink is not null);
        }
        Assert.Equal("Open the code at p.67", DetailPages.OpenWords(new LawLink("§325-26, p.67", "file:///x.pdf#page=67")));
        Assert.Equal("Open the code at §325-26", DetailPages.OpenWords(new LawLink("§325-26", "file:///x.pdf")));
    }

    [Fact]
    public void The_callout_says_the_checkers_one_ask_or_how_many_and_offers_to_answer_the_questions()
    {
        var m = Apartment();
        var pages = Pages(m);
        foreach (var (row, _, page) in pages.Where(p => p.Row.Section != ListSection.Complies))
        {
            var asks = ResultViews.CardsOf(m.Views!, row.Row.Id).Where(c => c.Kind is not (FixKind.Fails or FixKind.NotChecked or FixKind.Done)).ToList();
            if (asks.Count == 1)
                Assert.Equal(DetailPages.Sentence(asks[0].Headline), page.Headline);
            else if (asks.Count > 1)
                Assert.Equal(asks.All(a => DetailPages.ByHand(a.Kind)) ? DetailPages.SeveralByHand(asks.Count) : DetailPages.Several(asks.Count), page.Headline);
            // every ask is a step, in its order
            Assert.Equal(asks.Select(a => DetailPages.Sentence(a.Headline)), page.Steps.Where(s => asks.Any(a => DetailPages.Sentence(a.Headline) == s)));
            var questions = asks.Count(a => a.Kind == FixKind.Answer);
            if (questions > 0)
            {
                Assert.Equal(CalloutAction.Answer, page.Action);
                Assert.Equal(questions == 1 ? "Answer 1 question" : $"Answer {questions} questions", page.ActionWords);
            }
        }
        // the brief's row: two exits from Apartment South L1 waits on the occupancy group among its questions (the
        // checker's asks; their number is the answer's, and since main's occupant load factors no hand step for the load)
        var exits = pages.First(p => p.Row.Row.Name.Contains("Two exits", StringComparison.Ordinal) && p.Row.Row.Name.Contains("APARTMENT SOUTH L1", StringComparison.Ordinal));
        var exitQuestions = ResultViews.CardsOf(m.Views!, exits.Row.Row.Id).Count(c => c.Kind == FixKind.Answer);
        Assert.True(exitQuestions >= 2, $"{exitQuestions} questions");
        Assert.Equal(CalloutAction.Answer, exits.Page.Action);
        Assert.Equal($"Answer {exitQuestions} questions", exits.Page.ActionWords);
        Assert.Contains("Set the occupancy group.", exits.Page.Steps);
        Assert.Equal(exits.Page.Steps.Any(st => st.StartsWith("Work out the occupant load by hand", StringComparison.Ordinal)),
                     ResultViews.CardsOf(m.Views!, exits.Row.Row.Id).Any(c => c.Headline.StartsWith("Work out the occupant load", StringComparison.Ordinal)));
    }

    [Fact]
    public void A_failure_leads_with_the_checkers_advice_and_shows_its_elements()
    {
        var fail = Pages(House()).First(p => p.Row.Section == ListSection.Fails);
        Assert.Equal(DetailPages.Sentence(fail.Row.Row.Hint ?? "Change the design so it meets the limit"), fail.Page.Headline);
        Assert.Equal(CalloutAction.Show, fail.Page.Action);
        Assert.Equal("Show in model", fail.Page.ActionWords);
    }

    [Fact]
    public void A_sentence_ends_once()
    {
        Assert.Equal("Set the occupancy group.", DetailPages.Sentence("Set the occupancy group"));
        Assert.Equal("Is a home business planned? (§325-3B)", DetailPages.Sentence("Is a home business planned? (§325-3B)"));
        Assert.Equal("Is there an ADU on the lot?", DetailPages.Sentence("is there an ADU on the lot?"));
        Assert.Equal("Enter dwelling units.", DetailPages.Sentence("Enter dwelling units."));
    }

    // ---- the questions card -------------------------------------------------------------------------------------

    /// <summary>The apartment's project facts as the Setup form makes its fields (no mark set).</summary>
    private static IReadOnlyList<SetupField> Fields() =>
        SetupScreen.Build(new RevitModel { Document = "apartment.rvt", Marked = [], ProjectMarks = new Dictionary<Guid, MarkValue>() }, [], null).Fields;

    private static FixGroup Answers(ResultModel m) => m.Views!.Fix.Single(g => g.Kind == FixKind.Answer);

    /// <summary>After #193 and #194 the questions card meets an area fact (in the project's area unit) and the R-2 units'
    /// three words: each answered with the Setup form's own field, said in its own unit, and saved as the form saves it.</summary>
    [Theory]
    [InlineData("SquareFeet", "sq ft", "450.5", 450.5)]
    [InlineData("autodesk.unit.unit:squareMeters-1.0.1", "m²", "30", 30 / 0.09290304)]
    [InlineData("autodesk.unit.unit:hectares-1.0.1", "sq ft", "640", 640.0)]
    public void An_area_and_the_R2_choice_are_answered_in_the_card_as_the_setup_form_saves_them(string units, string symbol, string typed, double squareFeet)
    {
        var model = new RevitModel { Document = "apartment.rvt", Marked = [], ProjectMarks = new Dictionary<Guid, MarkValue>(), AreaDisplayUnits = units };
        var fields = SetupScreen.Build(model, [], null).Fields;
        // the apartment asks an area question: its card's field is the form's area field
        Assert.Contains(Answers(Apartment()).Cards, c => c.Field == "facts.home_occupation_area");
        var area = ProjectQuestions.FieldFor("facts.home_occupation_area", fields)!;
        Assert.Equal((Marks.HomeOccupationArea, FieldKind.Feet, "area"), (area.Mark, area.Kind, area.LengthUnit.Quantity));
        var words = ProjectQuestions.UnitWords(area.LengthUnit);
        Assert.StartsWith(symbol, words, StringComparison.Ordinal);
        Assert.Equal(!area.LengthUnit.Known, words.EndsWith("type square feet)", StringComparison.Ordinal));
        Assert.DoesNotContain("type feet", words, StringComparison.Ordinal);
        Assert.EndsWith("type feet)", ProjectQuestions.UnitWords(LengthUnits.Of("hectares")), StringComparison.Ordinal);
        var draft = new SetupDraft();
        draft.Choose(Marks.HomeOccupationArea, typed);
        var questions = ProjectQuestions.Of(Answers(Apartment()), fields);
        Assert.Same(area, questions.Single(q => q.Card.Field == "facts.home_occupation_area").Field);
        Assert.Equal(squareFeet, Assert.Single(ProjectQuestions.Writes(questions, draft).Writes).Value.Number!.Value, 9);
        // the R-2 units: a choice of the three words, saved as the word's value
        var r2 = ProjectQuestions.FieldFor("building.r2_sleeping_units", fields)!;
        Assert.Equal((Marks.R2SleepingUnits, FieldKind.Choice), (r2.Mark, r2.Kind));
        Assert.Equal(R2UnitWords.Table.Words, r2.Choices.Select(c => c.Value).Where(v => v.Length > 0));
        var choose = new SetupDraft();
        choose.Choose(Marks.R2SleepingUnits, "Both");
        var asked = new[] { new ProjectQuestion(questions[0].Card, r2) };          // the card's words don't matter to Save
        Assert.Equal("Both", Assert.Single(ProjectQuestions.Writes(asked, choose).Writes).Value.Text);
    }

    [Fact]
    public void Each_question_is_answered_with_the_setup_forms_own_field_and_one_without_is_said()
    {
        var m = Apartment();
        // the ADU's follow-ups shown (its answers chosen), so every question is in the card: none dropped
        var draft = new SetupDraft();
        draft.Choose(Marks.AccessoryDwellingUnit, "Yes");
        draft.Choose(Marks.All.Single(x => x.Feeds == "facts.adu_detached"), "Yes");
        var questions = ProjectQuestions.Of(Answers(m), Fields(), draft);
        Assert.Equal(Answers(m).Cards.Count - 2, questions.Count);              // a detached ADU's two size questions are moot
        FixCard Card(string field) => Answers(m).Cards.Single(c => c.Field == field);
        Assert.Equal(Marks.SprinklerSystem, questions.Single(q => q.Card == Card("building.sprinkler_system")).Field!.Mark);
        Assert.Equal(FieldKind.Choice, questions.Single(q => q.Card == Card("building.occupancy_groups")).Field!.Kind);
        Assert.Equal(FieldKind.YesNo, questions.Single(q => q.Card == Card("facts.corner_lot")).Field!.Kind);
        Assert.Equal(FieldKind.Number, questions.Single(q => q.Card == Card("facts.dwelling_units")).Field!.Kind);
        Assert.Equal(FieldKind.YesNo, questions.Single(q => q.Card == Card("facts.adu_existing_building")).Field!.Kind);  // a mark since #193
        // every question has the form's field that feeds it, and none only where no mark feeds it (said, never dropped)
        static bool Feeds(SetupField f, string? fact) => f.Mark.Feeds == fact || f.Mark.Feeds.StartsWith(fact + " ", StringComparison.Ordinal);
        foreach (var q in questions)
            if (q.Field is { } f)
                Assert.True(Feeds(f, q.Card.Field), $"{q.Card.Field} answered with {f.Mark.Name}");
            else
                Assert.DoesNotContain(Fields(), f => Feeds(f, q.Card.Field) && f.Kind != FieldKind.StreetPick);
        Assert.Equal(Card("building.sprinkler_system").Rows.Count, questions.Single(q => q.Card == Card("building.sprinkler_system")).Affects);
        Assert.True(questions.Single(q => q.Card == Card("building.sprinkler_system")).Affects > 1);
        Assert.Equal("affects 28 results", ProjectQuestions.Affects(28));
        Assert.Equal("affects 1 result", ProjectQuestions.Affects(1));
        // the street edge is picked on the plan, never asked with a box
        Assert.Null(ProjectQuestions.FieldFor("facts.street_line", Fields()));
    }

    [Fact]
    public void Save_writes_only_what_was_chosen_in_the_card_and_nothing_until_then()
    {
        var questions = ProjectQuestions.Of(Answers(Apartment()), Fields());
        var draft = new SetupDraft();
        Assert.Empty(ProjectQuestions.Writes(questions, draft).Writes);
        Assert.Equal(0, ProjectQuestions.Unsaved(questions, draft));
        Assert.Equal("Save and check again", ProjectQuestions.SaveWords(0));
        draft.Choose(Marks.SprinklerSystem, SprinklerWords.Table.Words[0]);
        draft.Choose(Marks.CornerLot, "No");
        draft.Choose(Marks.Zone, "R-1b");                                       // not a question here: never written from the card
        var (writes, problems) = ProjectQuestions.Writes(questions, draft);
        Assert.Empty(problems);
        Assert.Equal([Marks.SprinklerSystem, Marks.CornerLot], writes.Select(w => w.Mark).OrderBy(x => x == Marks.CornerLot));
        Assert.All(writes, w => Assert.Equal(SetupFacts.ProjectInformation, w.Element));
        Assert.Equal("Save 2 answers and check again", ProjectQuestions.SaveWords(ProjectQuestions.Unsaved(questions, draft)));
        // a count that isn't a whole number is refused with why, and not written
        draft.Choose(Marks.DwellingUnits, "four");
        var refused = ProjectQuestions.Writes(questions, draft);
        Assert.Single(refused.Problems);
        Assert.DoesNotContain(refused.Writes, w => w.Mark == Marks.DwellingUnits);
    }

    [Fact]
    public void The_card_lists_its_first_questions_then_more_then_its_foot_and_every_result_stays_reachable()
    {
        var m = Apartment();
        var answers = Answers(m);
        var open = new HashSet<string> { ResultViewList.GroupKey(answers) };
        var fields = Fields();
        IReadOnlyList<ListEntry> Lay(IEnumerable<string> keys) =>
            ResultViewList.Layout(m.Views!, ResultList.Place(m), ResultsViewKind.WhatToFix, keys.ToHashSet(), null, null, false, fields);
        var first = Lay(open);
        Assert.Equal(ProjectQuestions.ShownAtFirst, first.OfType<QuestionEntry>().Count());
        Assert.DoesNotContain(first, e => e is FixCardEntry { Card.Kind: FixKind.Answer });
        var more = Assert.Single(first.OfType<MoreQuestionsEntry>());
        var asked = ProjectQuestions.Of(answers, fields).Count;                 // the ADU's follow-ups held back (FollowUpQuestionsTests)
        Assert.Equal(asked - ProjectQuestions.ShownAtFirst, more.Hidden);
        var foot = Assert.Single(first.OfType<AnswerFootEntry>());
        Assert.Equal(asked, foot.Questions.Count);                              // Save covers every question, shown or behind "+ N more"
        // the card's scope note counts only its own results (none of them says it on the real answer)
        var scopedInCard = answers.Rows.Count(r => m.Views!.Scoped.Contains(r.Id));
        Assert.Equal(scopedInCard == 0 ? null : ResultViews.ScopeWords(scopedInCard), foot.Scope);
        Assert.Equal(asked, Lay(open.Append(ResultViewList.MoreQuestionsKey)).OfType<QuestionEntry>().Count());
        // every result of the group, even behind "+ N more", is reached by the path to it
        foreach (var row in answers.Rows)
        {
            var path = ResultViewList.PathTo(m.Views!, ResultsViewKind.WhatToFix, row.Id);
            Assert.Contains(Lay(path), e => e is ListRowEntry r && r.Row.Row.Id == row.Id);
        }
        // the keyboard stops on a question and on "+ N more", and opens them
        Assert.True(ResultList.Stops(first.OfType<QuestionEntry>().First()));
        Assert.Equal(more.Key, ResultViewList.KeyToggles(more, "Enter"));
        // review round 1: the keyboard answers a question (Enter goes into its control, Right opens its results) and
        // reaches Save (the foot is a stop, Enter saves)
        var question = first.OfType<QuestionEntry>().First(q => q.Question.Field is not null);
        Assert.True(ResultViewList.EntersControl(question, "Enter"));
        Assert.True(ResultViewList.EntersControl(question, "Space"));
        Assert.Null(ResultViewList.KeyToggles(question, "Enter"));
        Assert.Equal(question.Key, ResultViewList.KeyToggles(question, "Right"));
        Assert.True(ResultList.Stops(foot));
        Assert.True(ResultViewList.Saves(foot, "Enter"));
        Assert.False(ResultViewList.Saves(question, "Enter"));
        Assert.Contains("Save and check again", ResultViewList.Spoken(foot), StringComparison.Ordinal);
        // review round 2: the foot says the scope note drawn in it, and promises no answer that isn't chosen
        Assert.StartsWith(string.Join(" ", new[] { foot.Scope, ResultViewList.FootWords }.OfType<string>()), ResultViewList.Spoken(foot), StringComparison.Ordinal);
        Assert.DoesNotContain("the answers chosen", ResultViewList.Spoken(foot), StringComparison.Ordinal);
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        // review round 2: an open dropdown's item keeps its keys (a ComboBoxItem is a ListBoxItem)
        Assert.Contains("Within<C.ComboBoxItem>(source) is not null ||", view, StringComparison.Ordinal);
        Assert.Contains("if (Within<C.ComboBoxItem>(e.OriginalSource) is not null)\n                return;", view.Replace("\r\n", "\n"), StringComparison.Ordinal);
        Assert.Contains("ResultViewList.EntersControl(_entries[at], e.Key.ToString())", view, StringComparison.Ordinal);
        // review round 3: a key acts on the line it came from, Esc selects the line it focuses, and the keyboard going
        // into a control selects its line (a selection left on the foot never saves from a question's line)
        Assert.Contains("var at = Within<C.ListBoxItem>(e.OriginalSource) is { } from && _list.ItemContainerGenerator.IndexFromContainer(from) is var fi and >= 0", view, StringComparison.Ordinal);
        Assert.Contains("FocusEntry(_list.ItemContainerGenerator.IndexFromContainer(inItem));", view, StringComparison.Ordinal);
        Assert.DoesNotContain("inItem.Focus();", view, StringComparison.Ordinal);
        Assert.Contains("_list.PreviewGotKeyboardFocus += ", view, StringComparison.Ordinal);
        // review round 4: never a row, nor focus landing on a list item itself (a click on a row still sends it to Revit)
        Assert.Contains("Within<C.ListBoxItem>(e.NewFocus) is { DataContext: QuestionItem or MoreQuestionsItem or AnswerFootItem } item", view, StringComparison.Ordinal);
        Assert.Contains("&& !ReferenceEquals(e.NewFocus, item) &&", view, StringComparison.Ordinal);
        Assert.Contains("FocusEntry(ResultList.Next(_entries, at, ", view, StringComparison.Ordinal);
        Assert.Contains("ResultViewList.Saves(_entries[at], e.Key.ToString())", view, StringComparison.Ordinal);
        Assert.Contains("or AnswerFootItem => \"list.opener\"",
                        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsList.cs")), StringComparison.Ordinal);
        // without the fields (not read): the cards as before
        Assert.Contains(ResultViewList.Layout(m.Views!, ResultList.Place(m), ResultsViewKind.WhatToFix, open, null, null, false),
                        e => e is FixCardEntry { Card.Kind: FixKind.Answer });
    }

    /// <summary>Review round 1: the detail's "Answer N questions" opens the questions card so the result's own questions
    /// show, even one past the first few (behind "+ N more questions").</summary>
    [Fact]
    public void Answer_opens_the_card_so_the_results_own_questions_show()
    {
        var m = Apartment();
        var answers = Answers(m);
        var fields = Fields();
        var asked = ProjectQuestions.Of(answers, fields).Select(q => q.Card.Key).ToHashSet();
        foreach (var row in answers.Rows)
        {
            var keys = ResultViewList.AnswerKeys(m.Views!, row.Id, fields);
            Assert.Contains(ResultViewList.GroupKey(answers), keys);
            var shown = ResultViewList.Layout(m.Views!, ResultList.Place(m), ResultsViewKind.WhatToFix, keys.ToHashSet(), null, null, false, fields)
                                      .OfType<QuestionEntry>().Select(q => q.Question.Card).ToList();
            // each of its questions the card asks shows; a follow-up held back has it on the question shown above it
            Assert.All(answers.Cards.Where(c => c.Rows.Any(r => r.Id == row.Id) && asked.Contains(c.Key)), c => Assert.Contains(c, shown));
            Assert.Contains(shown, c => c.Rows.Any(r => r.Id == row.Id));
        }
        // a row whose question is past the first five: "+ N more" opened for it
        var late = ProjectQuestions.Of(answers, fields).Skip(ProjectQuestions.ShownAtFirst).SelectMany(q => q.Card.Rows).First();
        Assert.Contains(ResultViewList.MoreQuestionsKey, ResultViewList.AnswerKeys(m.Views!, late.Id, fields));
        // a row that asks no question: nothing to open
        var none = ResultList.Place(m).First(p => answers.Rows.All(r => r.Id != p.Row.Id)).Row.Id;
        Assert.Empty(ResultViewList.AnswerKeys(m.Views!, none));
    }

    /// <summary>Review round 1: a Save Revit took only part of says what it saved (and that Ctrl+Z undoes it), never
    /// that the answers weren't saved; a Save that wrote nothing says so.</summary>
    [Fact]
    public void A_partly_saved_answer_set_says_what_was_saved()
    {
        var part = PaneWords.AnswersNotSaved(["Gordium: Sprinkler system isn't on Project Information"], 1, "Committed");
        Assert.StartsWith("Saved 1 (Ctrl+Z undoes it)", part, StringComparison.Ordinal);
        Assert.DoesNotContain("weren't saved", part, StringComparison.Ordinal);
        Assert.Contains("Nothing was checked", part, StringComparison.Ordinal);
        Assert.DoesNotContain("answer the rest", part, StringComparison.Ordinal);       // review round 2: the refused ones were answered
        Assert.Contains("Check again", part, StringComparison.Ordinal);
        var none = PaneWords.AnswersNotSaved(["x"], 0, "RolledBack");
        Assert.StartsWith("Your answers weren't saved", none, StringComparison.Ordinal);
        Assert.Contains("PaneWords.AnswersNotSaved(refused, applied.Count, status)",
                        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsPane.cs")), StringComparison.Ordinal);
    }

    /// <summary>Review round 1: a length question says its unit beside the box (the project's, as the Setup form's
    /// label does), so "20" in a metric project is never read in a unit the architect didn't see.</summary>
    [Fact]
    public void A_length_question_says_its_unit()
    {
        var list = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsList.cs"));
        Assert.Contains("var unit = f.Kind == FieldKind.Feet ? f.LengthUnit : null;", list, StringComparison.Ordinal);
        Assert.Contains("Muted(ProjectQuestions.UnitWords(unit))", list, StringComparison.Ordinal);
        var metric = SetupScreen.Build(new RevitModel { Document = "m.rvt", Marked = [], ProjectMarks = new Dictionary<Guid, MarkValue>(),
                                                        DisplayUnits = "autodesk.unit.unit:meters-1.0.1" }, [], null).Fields;
        var stream = ProjectQuestions.FieldFor("facts.stream_distance", metric);
        Assert.Equal(FieldKind.Feet, stream!.Kind);
        Assert.Equal("m", stream.LengthUnit.Symbol);
    }

    /// <summary>The apartment's answer with <paramref name="count"/> rows matching <paramref name="pick"/> saying their
    /// rules are drafted for Group I-4 only (the checker's words: since #182 no rule of the apartment's still says it,
    /// so the note is tested on the real answer changed one way).</summary>
    private static ResultModel ApartmentSaying(Func<System.Text.Json.Nodes.JsonNode, bool> pick, int count)
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "four_unit_apartment_check_answer.json");
        var node = System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(file, Encoding.UTF8))!["result"]!;
        foreach (var item in node["view"]!["items"]!.AsArray().Where(i => pick(i!)).Take(count))
            item!["reason"] = "the building holds another occupancy: this rulebook's rules are " + ResultViews.DraftedFor + ", so a person checks";
        return ResultRows.Build(CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(node.ToJsonString()).RootElement.Clone(), About)),
                                "New Construction", [], null);
    }

    private static bool Contains(CodeNode n, string id) => n.Rows.Any(r => r.Id == id) || n.Children.Any(c => Contains(c, id));

    private static int SaysIt(ResultModel m) => ResultList.Place(m).Count(p => p.Row.Reason?.Contains(ResultViews.DraftedFor, StringComparison.Ordinal) == true
        || ResultViews.CardsOf(m.Views!, p.Row.Id).Any(c => c.Why?.Contains(ResultViews.DraftedFor, StringComparison.Ordinal) == true));

    /// <summary>The questions card's scope note is said of the card's own results only, with their count (short review
    /// after #181): none when no question's result says it, and the card's own count when one does.</summary>
    [Fact]
    public void The_cards_scope_note_counts_the_cards_own_results()
    {
        var fields = Fields();
        IReadOnlyList<ListEntry> Lay(ResultModel model) => ResultViewList.Layout(model.Views!, ResultList.Place(model), ResultsViewKind.WhatToFix,
            new HashSet<string> { ResultViewList.GroupKey(Answers(model)) }, null, null, false, fields);
        // the real answer: since #182 no result says it, so no note anywhere
        var m = Apartment();
        Assert.Equal(SaysIt(m), m.Views!.Scoped.Count);
        Assert.Null(Lay(m).OfType<AnswerFootEntry>().Single().Scope);
        // two Chapter 10 egress results (no question of their own) say it: the book says it, the card doesn't
        var inCard = Answers(m).Rows.Select(r => r.Id).ToHashSet(StringComparer.Ordinal);
        bool Egress(System.Text.Json.Nodes.JsonNode i) => ((string?)i["in_code"]?["document"])?.StartsWith("2025 Building Code", StringComparison.Ordinal) == true
            && (string?)i["in_code"]?["chapter"] == "10" && !inCard.Contains((string)i["id"]!);
        var two = ApartmentSaying(Egress, 2);
        Assert.Equal(2, two.Views!.Scoped.Count);
        Assert.Null(Lay(two).OfType<AnswerFootEntry>().Single().Scope);
        // one question's result says it too: the card says it, for that one result
        // one Chapter 10 question's result too (a Building Code row in the card)
        var question = Answers(m).Rows.First(r => m.Views!.Code.Single(d => d.Title.StartsWith("2025 Building Code", StringComparison.Ordinal))
                                                      .Children.Any(c => Contains(c, r.Id))).Id;
        var firstTwo = ApartmentSaying(Egress, 2).Views!.Scoped;
        var three = ApartmentSaying(i => firstTwo.Contains((string)i["id"]!) || (string)i["id"]! == question, 3);
        Assert.Equal(3, three.Views!.Scoped.Count);
        Assert.Equal(ResultViews.ScopeWords(1), Lay(three).OfType<AnswerFootEntry>().Single().Scope);
        // the book says its own count (all three are the Building Code's), the zoning book none
        Assert.Equal(ResultViews.ScopeWords(3), three.Views.Code.Single(d => d.Title.StartsWith("2025 Building Code", StringComparison.Ordinal)).Scope);
        Assert.Null(three.Views.Code.Single(d => d.Title.StartsWith("City of Ithaca", StringComparison.Ordinal)).Scope);
    }

    [Fact]
    public void The_scope_note_is_said_once_where_the_rows_say_the_rules_are_drafted_for_one_group()
    {
        // the real answer since #182: no result says it, so no note (never a note about all egress)
        Assert.Null(Apartment().Views!.Scope);
        Assert.All(Apartment().Views!.Code, d => Assert.Null(d.Scope));
        // two Building Code results say it: one note, under that book, with their count
        var m = ApartmentSaying(i => ((string?)i["in_code"]?["document"])?.StartsWith("2025 Building Code", StringComparison.Ordinal) == true, 2);
        var book = Assert.Single(m.Views!.Code, d => d.Scope is not null);
        Assert.StartsWith("2025 Building Code", book.Title, StringComparison.Ordinal);
        Assert.Equal(m.Views.Scope, book.Scope);                                 // every such row is under that book
        Assert.Equal(2, SaysIt(m));
        Assert.Equal(ResultViews.ScopeWords(2), m.Views.Scope);
        Assert.Contains("Group I-4", m.Views.Scope, StringComparison.Ordinal);
        Assert.StartsWith("1 Building Code result is", ResultViews.ScopeWords(1), StringComparison.Ordinal);
        // a house whose rows say nothing of the kind: no note
        Assert.Null(House().Views!.Scope);
    }
}
