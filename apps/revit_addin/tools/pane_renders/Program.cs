using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Gordium.Revit.Reading;
using Gordium.Worker;

namespace Gordium.Revit.PaneRenders;

using Gordium.Revit.Addin;

/// <summary>
/// Off-screen renders of the Gordium pane (the add-in's own view files), step by step through an architect's first run,
/// from the checker's real answers: the house (106 Ithaca Rd as Revit read it in the trial: the reader tests' answer)
/// and the childcare centre (Children's Odyssey), light and dark; and what each screen shows (words, buttons, fixes).
/// Usage: <c>Gordium.Revit.PaneRenders &lt;out dir&gt;</c>.
/// </summary>
internal static class Program
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());
    private static readonly StringBuilder Numbers = new();
    private static string _out = "";

    [STAThread]
    private static int Main(string[] args)
    {
        _out = args[0];
        Directory.CreateDirectory(_out);
        var here = AppContext.BaseDirectory;
        var fix = Path.Combine(here, "fixtures");
        var answers = Path.Combine(here, "answers");
        var options = Options(Path.Combine(fix, "setup_options.json"));
        // the egress audit: each answer given, as text and pictures (Audit.cs)
        if (args.Length > 1 && args[1] == "--audit")
        {
            var (_, auditModel, auditSides) = Fixture(Path.Combine(fix, "setup_apartment.json"));
            return Audit.Run(_out, args[2..], Labels, (pane, name, height, act) => Step(pane, name, height, false, act),
                             SetupScreen.Build(auditModel, auditSides, options).Fields);
        }
        var house = Load(Path.Combine(answers, "ithaca_106_house_check_answer.json"));
        var houseAfter = Load(Path.Combine(answers, "ithaca_106_house_after_check_answer.json"));
        var childcare = Load(Path.Combine(answers, "children_odyssey_check_answer.json"));
        var apartment = Load(Path.Combine(answers, "four_unit_apartment_check_answer.json"));
        // the same answer with three Chapter 10 results (one of them a question's) saying their rules are drafted
        // for Group I-4 only (since #182 no real result says it): what the scope note looks like where it shows
        var apartmentScoped = LoadSaying(Path.Combine(answers, "four_unit_apartment_check_answer.json"));
        // the four-unit apartment's Setup records (Ben's Revit trial, 2026-11-23): the Building Code governs its use
        foreach (var (n, r) in new[] { ("house", house), ("childcare", childcare) })
        {
            var cs = ResultRows.Build(r, "New Construction", [], null).Causes;
            Console.WriteLine($"{n}: {cs.Count} cause cards");
            foreach (var g in Fixes.Of(cs, Labels(r)))
                Console.WriteLine($"   tier {g.Tier} {g.Action}, {g.Rows.Count} results, {g.Members.Count} cards | {g.Title}");
        }
        Numbers.AppendLine("step\ttheme\theight\twords\tbuttons\tfixes shown\tfixes in all\tcause cards");
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
            foreach (var make in new Func<PanelTheme, List<string>, Pane>[] { (t, a) => new Pane(t, a) })
            {
                var dark = theme == PanelTheme.Dark;
                // a: first open, before any check
                Step(make(theme, []), "01_welcome", 430, dark, _ => { });
                // the house (106 Ithaca Rd) and the childcare centre (Children's Odyssey)
                // the apartment's Setup (UI polish, PR 1): the form as Revit shows it in a docked pane of the trial's height
                // (740 px, Ben's screenshot), its numbered steps all above the fold; filled; More facts open; picking
                {
                    var (_, model, sides) = Fixture(Path.Combine(fix, "setup_apartment.json"));
                    const string title = "Four-unit apartment";
                    var blank = SetupScreen.Build(model, sides, options, new SetupDraft());
                    Step(make(theme, []), "02_setup_apartment", 740, dark, p =>
                    {
                        p.Setup(title, blank, new SetupDraft());
                        StepsAboveFold(p.View, "02 apartment", 740);
                        NoAmberOnEmptyFields(p.View, "02 apartment");
                    });
                    var draft = Filled(blank, "apartment");
                    var filled = SetupScreen.Build(model, sides, options, draft);
                    Check(filled.BuildingCode, "apartment: multiple family is a use the Building Code governs, so the form asks for its two facts");
                    Check(filled.Steps.Any(st => st.Field?.Mark == Marks.OccupancyGroups) && filled.Steps.Any(st => st.Field?.Mark == Marks.SprinklerSystem),
                          "apartment: occupancy group and sprinkler system are numbered steps");
                    Step(make(theme, []), "03_setup_filled_apartment", 1150, dark, p => p.Setup(title, filled, draft));
                    Step(make(theme, []), "03b_setup_more_facts_open_apartment", 740, dark, p =>
                    {
                        p.Setup(title, filled, draft, [SetupView.MoreKey]);
                        Settle(p.View);
                        var form = FindAll<SetupView>(p.View).Single();
                        var scroll = FindAll<ScrollViewer>(p.View).First(v => v.Content == form);
                        var more = FindAll<Expander>(form).Single();
                        scroll.ScrollToVerticalOffset(more.TranslatePoint(new Point(0, 0), form).Y - 8);
                    });
                    Step(make(theme, []), "04_picking_street_edge_apartment", 520, dark, p =>
                    {
                        p.Setup(title, blank, new SetupDraft());
                        p.Picking(true);
                        Settle(p.View);
                        Check(FindAll<Border>(p.View).Any(b => b.IsVisible && Equals(b.Tag, ResultsView.PickTag)), "picking: the card says what Revit waits for");
                        Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t) == PaneWords.PickFormStays), "picking: the form stays as it was");
                    });
                    Step(make(theme, []), "04c_picking_ended_apartment", 740, dark, p =>
                    {
                        p.Setup(title, blank, new SetupDraft());
                        p.Picking(true);
                        p.Picking(false);
                        Settle(p.View);
                        Check(!FindAll<Border>(p.View).Any(b => b.IsVisible && Equals(b.Tag, ResultsView.PickTag)) && FindAll<DockPanel>(p.View).Any(d => d.IsVisible && Equals(d.Tag, SetupView.StepTag)),
                              "picking ended: the form back, the card gone");
                    });
                }
                // the results as two views (UI polish PR 3): the four-unit apartment's real answer (Ben's 2026-11-23
                // request), What to fix (the default) and By code, light and dark; stale By code never green
                {
                    const string title = "Four-unit apartment";
                    var when = new DateTime(2026, 11, 23, 11, 42, 0);
                    var rows = ResultRows.Build(apartment, "New Construction", [], null);
                    var views = rows.Views!;
                    Check(views.Fix.Count > 0 && views.Code.Count > 0, "apartment: both views have entries");
                    Step(make(theme, []), "13_what_to_fix_apartment", 900, dark, p => p.Show(title, when, rows, Labels(apartment)));
                    Step(make(theme, []), "13b_what_to_fix_card_open_apartment", 900, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment));
                        p.Toggle(ResultViewList.CardKey(views.Fix.First(g => g.Kind == FixKind.Answer).Cards[0]));
                    });
                    Step(make(theme, []), "14_by_code_apartment", 900, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment));
                        p.UseView(ResultsViewKind.ByCode);
                        // the Building Code's Chapter 10 opened (the apartment's egress rules)
                        var bc = views.Code.Select((d, i) => (d, i)).First(x => x.d.Title.StartsWith("2025 Building Code", StringComparison.Ordinal));
                        var ch10 = bc.d.Children.Select((c, i) => (c, i)).First(x => x.c.Number == "10");
                        p.Toggle($"/{bc.i}/{ch10.i}");
                        // review round 5: the list item the keyboard focuses carries the words a screen reader says and
                        // the tooltip (which code governs, the law's quoted words), not only the drawing inside it
                        Settle(p.View);
                        var items = FindAll<ListBoxItem>(p.View).ToList();
                        var book = items.FirstOrDefault(i => System.Windows.Automation.AutomationProperties.GetName(i).Contains("Governs this building", StringComparison.Ordinal));
                        Check(book is not null && (book.ToolTip as string ?? "").Contains("R101.2", StringComparison.Ordinal),
                              "14 By code: the governing book's list item says which code governs, with the law's words in its tooltip");
                        Check(items.Where(i => i.DataContext is CodeNodeItem).All(i => System.Windows.Automation.AutomationProperties.GetName(i).Length > 0),
                              "14 By code: every node's list item has words for a screen reader");
                    });
                    // UI polish PR 4: the questions asked in the card (changes 22 to 24), the result detail (28 to 32)
                    var (_, setupModel, setupSides) = Fixture(Path.Combine(fix, "setup_apartment.json"));
                    var questions = SetupScreen.Build(setupModel, setupSides, options).Fields;
                    var answerGroup = views.Fix.First(g => g.Kind == FixKind.Answer);
                    Step(make(theme, []), "16_questions_apartment", 1100, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment), questions);
                        Settle(p.View);
                        var combos = FindAll<ComboBox>(p.View).Count(c => c.IsVisible);
                        var yesNo = FindAll<System.Windows.Controls.Primitives.ToggleButton>(p.View).Count(t => t.IsVisible && (t.Content as string) is "Yes" or "No");
                        Check(combos >= 2 && yesNo >= 2, $"16 questions: asked in the card ({combos} dropdowns, {yesNo} Yes/No buttons)");
                        var save = FindAll<Button>(p.View).SingleOrDefault(b => b.IsVisible && b.Content as string == ProjectQuestions.SaveWords(0));
                        Check(save is { IsEnabled: false }, "16 questions: Save is off until an answer is chosen (nothing is written before)");
                        var cardScoped = answerGroup.Rows.Any(r => views.Scoped.Contains(r.Id));
                        Check(FindAll<Border>(p.View).Any(b => b.IsVisible && Equals(b.Tag, EntryView.ScopeTag)) == cardScoped, $"16 questions: the scope note is in the card only when its own results say it ({cardScoped})");
                    });
                    var exits = rows.Groups.SelectMany(g => g.AllRows).First(r => r.Name.Contains("Two exits", StringComparison.Ordinal) && r.Name.Contains("APARTMENT SOUTH L1", StringComparison.Ordinal));
                    foreach (var why in new[] { false, true })
                        Step(make(theme, []), why ? "17b_detail_why_open_apartment" : "17_detail_apartment", 900, dark, p =>
                        {
                            p.Show(title, when, rows, Labels(apartment), questions);
                            p.OpenResult(exits.Id);
                            Settle(p.View);
                            var callout = FindAll<Border>(p.View).SingleOrDefault(b => b.IsVisible && Equals(b.Tag, DetailView.CalloutTag));
                            Check(callout is not null, "17 detail: one callout with the headline");
                            var asked = ResultViews.CardsOf(views, exits.Id).Count(c => c.Kind == FixKind.Answer);
                            Check(FindAll<Button>(p.View).Any(b => b.IsVisible && (b.Content as TextBlock)?.Text == $"Answer {asked} questions"), $"17 detail: Answer {asked} questions beside it");
                            Check(!FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t) == "MEASURED AGAINST THE LIMIT"), "17 detail: nothing measured, so no Measured block");
                            Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t) == "WHAT THE CODE SAYS"), "17 detail: What the code says");
                            if (why)
                            {
                                var link = FindAll<Button>(p.View).First(b => b.IsVisible && (b.Content as TextBlock)?.Text == "Why?");
                                link.RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Primitives.ButtonBase.ClickEvent));
                                Settle(p.View);
                                Check(FindAll<StackPanel>(p.View).Any(s => s.IsVisible && Equals(s.Tag, DetailView.WhyTag)), "17b detail: Why? opens the checker's own words");
                            }
                        });
                    Step(make(theme, []), "18_detail_answer_goes_to_questions_apartment", 900, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment), questions);
                        p.OpenResult(exits.Id);
                        p.Answer();
                        Settle(p.View);
                        Check(FindAll<ComboBox>(p.View).Any(c => c.IsVisible), "18: Answer N questions goes back to the questions card, open");
                    });
                    // the scope note where it shows (the answer changed one way): once under the Building Code in By code, and
                    // in the questions card for the card's own result
                    var scopedRows = ResultRows.Build(apartmentScoped, "New Construction", [], null);
                    Step(make(theme, []), "14s_by_code_scope_note_apartment", 900, dark, p =>
                    {
                        p.Show(title, when, scopedRows, Labels(apartmentScoped), questions);
                        p.UseView(ResultsViewKind.ByCode);
                        Settle(p.View);
                        var notes = FindAll<Border>(p.View).Where(b => b.IsVisible && Equals(b.Tag, EntryView.ScopeTag)).ToList();
                        Check(notes.Count == 1, $"14s: the scope note once, under the Building Code whose results say it ({notes.Count})");
                    });
                    Step(make(theme, []), "16s_questions_scope_note_apartment", 1100, dark, p =>
                    {
                        p.Show(title, when, scopedRows, Labels(apartmentScoped), questions);
                        Settle(p.View);
                        Check(FindAll<Border>(p.View).Any(b => b.IsVisible && Equals(b.Tag, EntryView.ScopeTag)), "16s: the scope note in the card, for its own result");
                    });
                    // UI polish PR 4b: What changed with what the architect changed (change 40; two checks of one
                    // project, the second after the sprinkler system and corner lot were answered), the proportion bar
                    // (18), the selection strip (41), the printable summary in By code order (38)
                    // the house (106 Ithaca Rd) before and after its lot facts were answered: its two real answers, and its
                    // Setup facts before and after (no ADU, no stream nearby, a garage for 2 cars)
                    var (_, houseModel, houseSides) = Fixture(Path.Combine(fix, "setup_ithaca106.json"));
                    var houseAnswered = new RevitModel
                    {
                        Document = houseModel.Document, Marked = houseModel.Marked, DisplayUnits = houseModel.DisplayUnits,
                        ProjectMarks = new Dictionary<Guid, MarkValue>(houseModel.ProjectMarks)
                        {
                            [Marks.AccessoryDwellingUnit.Guid] = new(true, 0),
                            [Marks.StreamNearLot.Guid] = new(true, 0),
                            [Marks.GarageCars.Guid] = new(true, 2),
                        },
                    };
                    Step(make(theme, []), "19_what_changed_house", 900, dark, p =>
                    {
                        p.Show("106 Ithaca Rd", when, ResultRows.Build(house, "New Construction", [], null), Labels(house),
                               SetupScreen.Build(houseModel, houseSides, options).Fields, key: "render:what-changed");
                        p.Show("106 Ithaca Rd", when.AddMinutes(9), ResultRows.Build(houseAfter, "New Construction", [], null), Labels(houseAfter),
                               SetupScreen.Build(houseAnswered, houseSides, options).Fields, key: "render:what-changed");
                        Settle(p.View);
                        Check(FindAll<Border>(p.View).Any(b => b.IsVisible && Equals(b.Tag, ResultsView.ChangeTag)), "19: What changed sits at the top");
                        Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t).StartsWith("You changed: ", StringComparison.Ordinal)), "19: it says what you changed");
                        Check(!FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t).Contains("hover for all", StringComparison.Ordinal)), "19: no \"hover for all\"");
                        Check(FindAll<Grid>(p.View).Any(g => g.IsVisible && Equals(g.Tag, ResultsView.BarTag)), "19: the proportion bar under the summary line");
                        NoComplies(FindAll<Grid>(p.View).First(g => Equals(g.Tag, ResultsView.BarTag)), "19: the bar has no green while results need review");
                    });
                    Step(make(theme, []), "20_selection_strip_apartment", 740, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment), questions);
                        var map = SelectionMap.Of(rows, when);
                        var wall = map.Elements.OrderByDescending(u => map.For([u]).Count).First();
                        p.Strip(map.Answer([wall], _ => "Wall “LS New 6\"”"));
                        Settle(p.View);
                        var strip = FindAll<Border>(p.View).Single(b => b.IsVisible && Equals(b.Tag, SelectionStrip.Tag));
                        var links = FindAll<Button>(strip).Count(b => b.IsVisible && (b.Content as TextBlock)?.Text is { } t && !t.StartsWith("Show all", StringComparison.Ordinal));
                        Check(links == SelectionMap.Shown, $"20: the strip lists the top {SelectionMap.Shown} ({links})");
                        Check(FindAll<Button>(strip).Any(b => b.IsVisible && b.Content as string == "Clear"), "20: Clear puts it away");
                    });
                    if (!dark)
                        File.WriteAllText(Path.Combine(_out, "21_summary_by_code_apartment.html"),
                                          ComplianceSummary.Html(rows, title, when, when.AddMinutes(3)), new UTF8Encoding(false));
                    // UI polish PR 5: the check's progress as three steps (change 12), a message per failure with no raw
                    // text anywhere (13, 14), the time-out with Try again with more time (15), the read failure in the
                    // pane (16), the slim stale banner (39)
                    Step(make(theme, []), "22_checking_steps_apartment", 740, dark, p =>
                    {
                        p.Setup(title, SetupScreen.Build(setupModel, setupSides, options, new SetupDraft()), new SetupDraft());
                        p.Progress(CheckStage.Reading, DateTime.Now.AddSeconds(-47));
                        p.Progress(CheckStage.Checking, DateTime.Now.AddSeconds(-45));
                        p.Step("Measuring the building…");
                        Settle(p.View);
                        Check(FindAll<Border>(p.View).Any(b => b.IsVisible && Equals(b.Tag, ResultsView.ProgressTag)), "22: the progress card");
                        Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t) == CheckSteps.Check), "22: the checking step");
                        Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t).EndsWith(CheckSteps.Long, StringComparison.Ordinal)), "22: after 40 s, large models take longer");
                        Check(!FindAll<SetupView>(p.View).Any(v => v.IsVisible), "22: the form is hidden behind the progress");
                    });
                    var failures = new (string Name, CheckFailure Failure)[]
                    {
                        ("23_error_timeout", CheckFailures.Of(new WorkerTimeoutException("t") { Limit = TimeSpan.FromSeconds(60), Silent = true, Command = "check_site" },
                            "WorkerTimeoutException: The Gordium checker said nothing for 60 s while answering check_site (logged to C:\\x\\results.jsonl)")),
                        ("24_error_read", CheckFailures.ReadFailed("Nothing was checked: InvalidOperationException: boom (logged to C:\\x\\results.jsonl)")),
                        ("25_error_closed", CheckFailures.Closed()),
                        ("26_error_unreadable", CheckFailures.Of(new WorkerProtocolException("p"), "WorkerProtocolException: result.view.groups is null")),
                    };
                    foreach (var (name, failure) in failures)
                        Step(make(theme, []), name, 430, dark, p =>
                        {
                            p.Failed(failure);
                            Settle(p.View);
                            var card = FindAll<StackPanel>(p.View).Single(s => s.IsVisible && Equals(s.Tag, ResultsView.ErrorTag));
                            Check(FindAll<FrameworkElement>(card).Prepend(card).All(e => e.ToolTip is null), $"{name}: no tooltip on the error card (change 14)");
                            Check(!FindAll<TextBlock>(p.View).Any(t => t.IsVisible && (TextOf(t).Contains("Exception", StringComparison.Ordinal) || TextOf(t).Contains("results.jsonl", StringComparison.Ordinal))),
                                  $"{name}: no raw text on screen");
                            Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t) == failure.Title), $"{name}: its own title");
                            if (name == "23_error_timeout")
                                Check(failure.Title == "The check took too long" && failure.Action == FailureAction.TryAgainWithMoreTime, "23: the check's own time-out, with more time");
                        });
                    Step(make(theme, []), "27_stale_slim_apartment", 740, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment), questions);
                        p.Stale();
                        Settle(p.View);
                        var banner = FindAll<StackPanel>(p.View).Single(s => s.IsVisible && Equals(s.Tag, ResultsView.StaleTag));
                        Check(!FindAll<Button>(banner).Any(), "27: the stale banner has no button (the header's is the one)");
                        Check(FindAll<TextBlock>(p.View).Any(t => t.IsVisible && TextOf(t).Contains("needed review", StringComparison.Ordinal)), "27: counts in the past tense");
                        NoComplies(p.View, "27 stale slim");
                    });
                    Step(make(theme, []), "15_by_code_stale_apartment", 900, dark, p =>
                    {
                        p.Show(title, when, rows, Labels(apartment));
                        p.UseView(ResultsViewKind.ByCode);
                        p.Stale();
                        NoComplies(p.View, "15 By code stale");
                    });
                }
                foreach (var (tag, title, setupFile, answer) in new[] { ("house", "106 Ithaca Rd", "setup_ithaca106.json", house), ("childcare", "Children's Odyssey", "setup_childcare.json", childcare) })
                {
                    if (dark && tag == "childcare")
                        continue;                       // dark: the house only
                    var (setupTitle, model, sides) = Fixture(Path.Combine(fix, setupFile));
                    var blank = SetupScreen.Build(model, sides, options, new SetupDraft());
                    // b: Check project with facts missing: the Setup form
                    Step(make(theme, []), $"02_setup_{tag}", 740, dark, p =>
                    {
                        p.Setup(title, blank, new SetupDraft());
                        StepsAboveFold(p.View, $"02 {tag}", 740);
                        NoAmberOnEmptyFields(p.View, $"02 {tag}");
                    });
                    // c: the form filled in, then the check running
                    var draft = Filled(blank, tag);
                    var filled = SetupScreen.Build(model, sides, options, draft);
                    Step(make(theme, []), $"03_setup_filled_{tag}", 740, dark, p => p.Setup(title, filled, draft));
                    Step(make(theme, []), $"04_checking_{tag}", 430, dark, p =>
                    {
                        p.Setup(title, filled, draft);
                        p.Progress(CheckStage.Checking, DateTime.Now.AddSeconds(-4));
                    });
                    // d: the results' top
                    var labels = Labels(answer);
                    var rows = ResultRows.Build(answer, "New Construction", [], null);
                    var when = new DateTime(2026, 11, 22, 14, 32, 0);
                    foreach (var h in new[] { 430, 900 })
                        Step(make(theme, []), $"05_results_{tag}", h, dark, p => p.Show(title, when, rows, labels));
                    // e: the first card opened on its rows
                    Step(make(theme, []), $"06_card_open_{tag}", 900, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.OpenFirstFix();
                        ScrollToCards(p.View);
                    });
                    // the pane as narrow as Revit docks it in the trial (narrower than at 340: Revit draws the same words wider): the fix's button stays one
                    // line and its link wraps under it, never squeezed to a letter a line (Revit 2027 trial, 2026-11-23)
                    if (!dark)
                        Step(make(theme, []), $"06_card_open_{tag}_narrow", 900, dark, p =>
                        {
                            p.Show(title, when, rows, labels);
                            p.OpenFirstFix();
                            ScrollToCards(p.View);
                            Settle(p.View);
                            var tall = FindAll<Button>(p.View).Where(b => b.IsVisible && b.Content is string && b.ActualHeight > 40).ToList();   // a button of words, not a wrapped link
                            Check(tall.Count == 0, $"{tag} narrow: no button taller than a line ({tall.Count})");
                        }, width: 280);
                    // the form shown again (its facts read again after Save): one foot, no error
                    if (!dark)
                        Step(make(theme, []), $"03_setup_again_{tag}", 430, dark, p =>
                        {
                            p.Setup(title, filled, draft);
                            p.Setup(title, filled, draft);
                            Check(true, $"{tag}: the Setup form shown twice");
                        });
                    // f: a row's detail (the first card's first row)
                    Step(make(theme, []), $"07_detail_{tag}", 900, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.OpenRow(p.FirstFixRows[0]);
                    });
                    if (tag != "house")
                        continue;
                    // g: after the fix (the lot facts set) and Check again: what changed
                    var afterLabels = Labels(houseAfter);
                    Step(make(theme, []), "08_what_changed_house", 430, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.Show(title, when.AddMinutes(9), ResultRows.Build(houseAfter, "New Construction", [], null), afterLabels);
                    });
                    // h: a project with nothing missing that just runs: Check project straight to checking
                    Step(make(theme, []), "09_just_runs_house", 430, dark, p => p.Progress(CheckStage.Checking, DateTime.Now.AddSeconds(-6)));
                    // the error state, and stale
                    Step(make(theme, []), "10_error_house", 430, dark, p => p.Failed(CheckFailures.Of(new WorkerExitedException("exited", 1, ""),
                        CheckWords.CheckerStopped("the worker exited with code 1") + @" (logged to C:\Users\you\AppData\Local\Gordium\trial\results.jsonl)")));
                    Step(make(theme, []), "11_stale_house", 430, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.Stale();
                        NoComplies(p.View, "11 stale");
                    });
                    // stale after What changed (its list has "now complies"): every glyph the clock, never green
                    Step(make(theme, []), "12_stale_what_changed_house", 900, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.Show(title, when.AddMinutes(9), ResultRows.Build(houseAfter, "New Construction", [], null), afterLabels);
                        p.Stale();
                        NoComplies(p.View, "12 stale after What changed");
                    });
                }
            }
        File.WriteAllText(Path.Combine(_out, "numbers.tsv"), Numbers.ToString());
        Console.WriteLine(Numbers.ToString());
        Console.WriteLine(Failures == 0 ? "ALL CHECKS OK" : $"{Failures} CHECKS FAILED");
        return Failures;
    }

    /// <summary>The form as an architect fills it in: the facts a check needs chosen (nothing written: a draft).</summary>
    private static SetupDraft Filled(SetupScreen blank, string tag)
    {
        var draft = new SetupDraft();
        foreach (var f in blank.Fields.Where(f => f.Required && f.Current is null))
        {
            var pick = f.Mark == Marks.Zone ? (tag == "house" ? "R-1b" : tag == "apartment" ? "R-3a" : f.Choices.FirstOrDefault()?.Value)
                : f.Mark == Marks.Use ? (tag == "house" ? "one_family_detached" : tag == "apartment" ? "multiple_family" : f.Choices.FirstOrDefault(c => c.Value.Contains("day_care"))?.Value ?? f.Choices.FirstOrDefault()?.Value)
                : f.Mark == Marks.LotSurveyed ? "No"
                : f.Kind == FieldKind.YesNo ? "Yes" : null;
            if (pick is not null && f.Kind != FieldKind.StreetPick)
                draft.Choose(f.Mark, pick);
        }
        return draft;
    }

    /// <summary>Every numbered step of the Setup form is above the fold of a docked pane <paramref name="fold"/> px tall
    /// (UI polish change 1: Ben saw "6 facts to set" and found 4; the other 2 were ~1,100 px down).</summary>
    private static void StepsAboveFold(FrameworkElement view, string what, int fold)
    {
        Settle(view);
        // the form's scroll viewport (the header above it, the sticky footer below): each step's title within it
        var form = FindAll<SetupView>(view).Single();
        var scroll = FindAll<ScrollViewer>(view).First(v => v.Content == form);
        var steps = FindAll<DockPanel>(form).Where(d => d.IsVisible && Equals(d.Tag, SetupView.StepTag)).ToList();
        var bottom = steps.Count == 0 ? 0 : steps.Max(d => d.TranslatePoint(new Point(0, 22), scroll).Y);
        Check(steps.Count > 0 && bottom <= scroll.ViewportHeight,
              $"{what}: {steps.Count} steps, the last one's title at {bottom:0} px of a {scroll.ViewportHeight:0} px view (pane {fold} px)");
    }

    /// <summary>No text in the review colour on a form with nothing set (UI polish change 8: status colours are for
    /// results; an empty field is a task, not a warning), other than a problem a field holds.</summary>
    private static void NoAmberOnEmptyFields(FrameworkElement view, string what)
    {
        Settle(view);
        var amber = ((SolidColorBrush)view.FindResource(PanelTokens.StatusReview)).Color;
        var said = FindAll<TextBlock>(view).Where(t => t.IsVisible && t.Foreground is SolidColorBrush b && b.Color == amber).Select(TextOf).ToList();
        Check(said.All(w => w.Contains("Choose", StringComparison.Ordinal) || w.Contains("Pick it", StringComparison.Ordinal)),
              $"{what}: no amber \"needed\" ({string.Join(" | ", said)})");
    }

    /// <summary>A stale pane shows no complies colour anywhere: no shape filled or stroked in status.pass.</summary>
    private static void NoComplies(FrameworkElement view, string what)
    {
        Settle(view);
        var pass = ((SolidColorBrush)view.FindResource(PanelTokens.StatusPass)).Color;
        bool Green(Brush? b) => b is SolidColorBrush c && c.Color == pass;
        var green = FindAll<System.Windows.Shapes.Shape>(view).Count(s => s.IsVisible && (Green(s.Fill) || Green(s.Stroke)))
                    + FindAll<TextBlock>(view).Count(t => t.IsVisible && Green(t.Foreground));
        Check(green == 0, $"{what}: nothing in a complies colour ({green})");
    }

    internal static int Failures;

    private static void Check(bool ok, string what)
    {
        Console.WriteLine((ok ? "ok   " : "FAIL ") + what);
        if (!ok)
            Failures++;
    }

    private static void Step(Pane pane, string name, int height, bool dark, Action<Pane> act, int width = 340)
    {
        var window = new Window
        {
            Content = pane.View, Width = width, Height = height, WindowStyle = WindowStyle.None, ShowInTaskbar = false,
            Left = -20000, Top = -20000, ShowActivated = false, SizeToContent = SizeToContent.Manual,
        };
        window.Show();
        act(pane);
        Settle(pane.View);
        var file = $"{name}_built{(height == 430 ? "" : "_" + height)}{(dark ? "_dark" : "")}.png";
        Render(pane.View, Path.Combine(_out, file));
        var (words, buttons) = Measure(pane.View);
        var welcome = FindAll<TextBlock>(pane.View).Any(t => t.IsVisible && TextOf(t) == PaneWords.WelcomeTitle);
        Check(welcome == name is "01_welcome" or "09_just_runs_house", $"{file}: the welcome {(welcome ? "shows" : "doesn't show")} (only before the first results, never over them)");
        var (shown, total, cards) = pane.Cards;
        Numbers.AppendLine($"{name}\t{(dark ? "dark" : "light")}\t{height}\t{words}\t{buttons}\t{shown}\t{total}\t{cards}");
        Console.WriteLine($"{file}: {words} words, {buttons} buttons, fixes {shown}/{total} of {cards} cause cards");
        window.Close();
    }

    internal static void Settle(FrameworkElement v)
    {
        for (var i = 0; i < 3; i++)
        {
            v.UpdateLayout();
            System.Windows.Threading.Dispatcher.CurrentDispatcher.Invoke(() => { }, System.Windows.Threading.DispatcherPriority.ApplicationIdle);
        }
    }

    /// <summary>Scrolls the pane's list so its "Fix these first" entry is at the top.</summary>
    private static void ScrollToCards(FrameworkElement view)
    {
        Settle(view);
        var list = FindAll<ListBox>(view).FirstOrDefault();
        if (list is null)
            return;
        var at = Enumerable.Range(0, list.Items.Count).FirstOrDefault(i => list.Items[i].GetType().Name is "CausesItem");
        if (at <= 0)
            return;
        var sv = FindAll<ScrollViewer>(list).First();
        list.ScrollIntoView(list.Items[at]);
        list.UpdateLayout();
        if (list.ItemContainerGenerator.ContainerFromIndex(at - 1) is FrameworkElement box)
            sv.ScrollToVerticalOffset(sv.VerticalOffset + box.TranslatePoint(new Point(0, 0), sv).Y);
        list.UpdateLayout();
    }

    /// <summary>The words an architect sees on screen (every visible text inside the pane's frame) and the buttons.</summary>
    internal static (int Words, int Buttons) Measure(FrameworkElement view)
    {
        var frame = new Rect(0, 0, view.ActualWidth, view.ActualHeight);
        bool OnScreen(FrameworkElement e)
        {
            if (!e.IsVisible || e.ActualHeight < 1)
                return false;
            try
            {
                var r = e.TransformToAncestor(view).TransformBounds(new Rect(0, 0, e.ActualWidth, e.ActualHeight));
                // clipped by a scroll viewer: count only what its viewport shows
                for (DependencyObject? p = VisualTreeHelper.GetParent(e); p is not null && p != view; p = VisualTreeHelper.GetParent(p))
                    if (p is ScrollContentPresenter sp)
                        r.Intersect(sp.TransformToAncestor(view).TransformBounds(new Rect(0, 0, sp.ActualWidth, sp.ActualHeight)));
                return !r.IsEmpty && r.Height >= 4 && r.IntersectsWith(frame);
            }
            catch (InvalidOperationException)
            {
                return false;
            }
        }
        var words = FindAll<TextBlock>(view).Where(OnScreen).Sum(t => Regex.Matches(TextOf(t), @"\S+").Count);
        var buttons = FindAll<System.Windows.Controls.Primitives.ButtonBase>(view).Count(b => OnScreen(b) && b is not CheckBox);
        return (words, buttons);
    }

    private static string TextOf(TextBlock t) =>
        t.Text is { Length: > 0 } x ? x : new System.Windows.Documents.TextRange(t.ContentStart, t.ContentEnd).Text;

    // a question of the questions card, by the pane's own rule (a "mark" ask is a project question only with a facts. or
    // building. field; review after #202: a door's field-less mark, or rooms[].function, is a per-element mark)
    private static bool Asked(System.Text.Json.Nodes.JsonNode? ask) =>
        ResultViews.KindOf((string?)ask!["kind"], (string?)ask["field"]) == FixKind.Answer;

    internal static CheckResult LoadSaying(string path)
    {
        var node = System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))!;
        var items = node["result"]!["view"]!["items"]!.AsArray();
        var picked = items.Where(i => (string?)i!["in_code"]?["chapter"] == "10"
                                      && ((string?)i!["in_code"]?["document"])?.StartsWith("2025 Building Code", StringComparison.Ordinal) == true
                                      && i!["asks"] is System.Text.Json.Nodes.JsonArray a && !a.Any(Asked)).Take(2)
                          .Concat(items.Where(i => (string?)i!["in_code"]?["chapter"] == "10"
                                                   && ((string?)i!["in_code"]?["document"])?.StartsWith("2025 Building Code", StringComparison.Ordinal) == true
                                                   && i!["asks"] is System.Text.Json.Nodes.JsonArray a && a.Any(Asked)).Take(1));
        foreach (var i in picked)
            i!["reason"] = "the building holds another occupancy: this rulebook's rules are " + ResultViews.DraftedFor + ", so a person checks";
        var doc = JsonDocument.Parse(node.ToJsonString());
        return (CheckResult)typeof(CheckResult).GetMethod("Parse", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, [new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About)])!;
    }

    internal static CheckResult Load(string path)
    {
        var doc = JsonDocument.Parse(File.ReadAllText(path, Encoding.UTF8));
        return (CheckResult)typeof(CheckResult).GetMethod("Parse", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, [new WorkerAnswer(doc.RootElement.GetProperty("result"), About)])!;
    }

    /// <summary>Each element a name, as the answer gives it (what Revit would label it).</summary>
    internal static Dictionary<string, string> Labels(CheckResult r)
    {
        var labels = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var i in r.Items)
        {
            var raw = i.Raw;
            if (raw.TryGetProperty("part", out var p) && p.ValueKind == JsonValueKind.Object && p.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String
                && p.TryGetProperty("name", out var n) && n.ValueKind == JsonValueKind.String && !id.GetString()!.Contains(' '))
                labels.TryAdd(id.GetString()!, n.GetString()!.Split(" › ")[^1]);
            if (raw.TryGetProperty("causes", out var cs) && cs.ValueKind == JsonValueKind.Array)
                foreach (var c in cs.EnumerateArray())
                    if (c.TryGetProperty("rooms", out var rs) && rs.ValueKind == JsonValueKind.Array)
                        foreach (var room in rs.EnumerateArray())
                            labels[room.GetProperty("id").GetString()!] = room.GetProperty("name").GetString()!;
            if (raw.TryGetProperty("objects", out var os) && os.ValueKind == JsonValueKind.Array)
                foreach (var o in os.EnumerateArray())
                    labels.TryAdd(o.GetString()!, i.Name == "Lot coverage" ? "Building: House" : "Lot line " + (labels.Count + 1));
        }
        return labels;
    }

    internal static void Render(FrameworkElement v, string file)
    {
        v.UpdateLayout();
        var bmp = new RenderTargetBitmap((int)Math.Ceiling(v.ActualWidth), (int)Math.Ceiling(v.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        bmp.Render(v);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(bmp));
        using var f = File.Create(file);
        enc.Save(f);
    }

    internal static IEnumerable<T> FindAll<T>(DependencyObject root) where T : DependencyObject
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var c = VisualTreeHelper.GetChild(root, i);
            if (c is T t)
                yield return t;
            foreach (var d in FindAll<T>(c))
                yield return d;
        }
    }

    // ---- the Setup fixtures (the unmarked models' records, as the Setup renders of PR #164 read them) ------------

    private static PlaceOptions Options(string file)
    {
        var j = JsonDocument.Parse(File.ReadAllText(file)).RootElement;
        var uses = j.GetProperty("uses").EnumerateObject().Select(p => (p.Name, p.Value.GetString()!)).ToList();
        var district = j.GetProperty("district_uses").EnumerateObject().ToDictionary(d => d.Name, d => (IReadOnlyList<UseChoice>)d.Value.EnumerateArray()
            .Select(u => new UseChoice(u.GetProperty("id").GetString()!, u.GetProperty("name").GetString()!,
                                       u.GetProperty("permitted").ValueKind switch { JsonValueKind.True => true, JsonValueKind.False => false, _ => null },
                                       u.GetProperty("note").ValueKind == JsonValueKind.String ? u.GetProperty("note").GetString() : null)).ToList());
        return new PlaceOptions(j.GetProperty("zones").EnumerateArray().Select(z => z.GetString()!).ToList(), uses, district)
        {
            BuildingCodeUses = j.TryGetProperty("building_code_uses", out var bc) ? bc.EnumerateArray().Select(u => u.GetString()!).ToList() : [],
        };
    }

    private static MarkValue? Yes(JsonElement m, string key) =>
        m.TryGetProperty(key, out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False ? new MarkValue(true, v.GetBoolean() ? 1 : 0) : null;

    private static MarkValue? Word(JsonElement m, string key, Func<string, string>? map = null) =>
        m.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? new MarkValue(true, Text: map is null ? v.GetString() : map(v.GetString()!)) : null;

    private static (string, RevitModel, List<OpeningSides>) Fixture(string file)
    {
        var j = JsonDocument.Parse(File.ReadAllText(file)).RootElement;
        var marked = new List<MarkedElement>();
        foreach (var e in j.GetProperty("elements").EnumerateArray())
        {
            var m = e.GetProperty("marks");
            var inst = new Dictionary<Guid, MarkValue>();
            void Put(MarkDefinition d, MarkValue? v)
            {
                if (v is not null)
                    inst[d.Guid] = v;
            }
            var cat = e.GetProperty("cat").GetString()!;
            if (cat == "OST_Rooms")
            {
                Put(Marks.SleepingRoom, Yes(m, "sleeping"));
                Put(Marks.Use, Word(m, "use"));
                Put(Marks.CanBeLocked, Yes(m, "lockable"));
                Put(Marks.PassThrough, Yes(m, "pass_through"));
            }
            else
                Put(Marks.Exit, Word(m, "exit", k => ExitKinds.Table.WordFor(k)));
            string? S(string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
            double? D(string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;
            marked.Add(new MarkedElement
            {
                UniqueId = e.GetProperty("id").GetString()!, BuiltInCategory = cat, Name = S("name"), Number = S("number"), Family = S("family"),
                TypeUniqueId = S("type"), TypeWidth = D("w"), TypeHeight = D("h"), Placement = cat == "OST_Rooms" ? RoomPlacement.Placed : null,
                Instance = inst,
            });
        }
        var sides = j.GetProperty("sides").EnumerateArray().Select(s => new OpeningSides(s.GetProperty("id").GetString()!,
            s.GetProperty("from").ValueKind == JsonValueKind.String ? s.GetProperty("from").GetString() : null,
            s.GetProperty("to").ValueKind == JsonValueKind.String ? s.GetProperty("to").GetString() : null, "L1", "Level 1", 0)).ToList();
        return (j.GetProperty("title").GetString()!, new RevitModel { Document = file, Marked = marked, ProjectMarks = new Dictionary<Guid, MarkValue>() }, sides);
    }
}
