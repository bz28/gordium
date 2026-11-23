using System.Text;
using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The intuitive pane (docs/revit/ui_design_pass.md, "The intuitive pane"; Ben approved 2026-11-23), Revit-free:
/// the "Start here" fixes (the worker's cause cards joined where they share one fix, ranked, three shown: never a
/// result hidden, the same order every time), one vocabulary and one word per kind of action, the welcome (never over
/// results), the header's button, the Setup footer, the results' first sentence and the filters' counts, what changed
/// as a short list, a result's "What to do" naming its fix, and the error and stale states in plain words. Each test
/// fails when its change is taken out. Every count is a count of the worker's rows: nothing here makes a verdict.</summary>
public sealed class PaneTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static readonly string Answers = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers");

    private static CheckResult Load(string file)
    {
        var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(Answers, file), Encoding.UTF8));
        return CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About));
    }

    /// <summary>106 Ithaca Rd as Revit read it in the trial (2026-11-22), checked again: 46 cause cards.</summary>
    private static CheckResult House() => Load("ithaca_106_house_check_answer.json");

    /// <summary>The same house after its lot facts were set (What changed).</summary>
    private static CheckResult HouseAfter() => Load("ithaca_106_house_after_check_answer.json");

    private static CheckResult Odyssey() => Load("children_odyssey_check_answer.json");

    private static ResultModel Model(CheckResult r) => ResultRows.Build(r, null, [], null);

    /// <summary>Every element the answer names, as the project would have it (the check read each one's name).</summary>
    private static Dictionary<string, string> Labels(CheckResult r)
    {
        var labels = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var c in Model(r).Causes)
            foreach (var e in c.Elements)
                labels[e] = e;
        foreach (var i in r.Items)
            if (i.Raw.TryGetProperty("objects", out var os) && os.ValueKind == JsonValueKind.Array)
                foreach (var o in os.EnumerateArray())
                    if (o.GetString() is { } id)
                        labels[id] = id;
        return labels;
    }

    private static IReadOnlyList<Fix> FixesOf(CheckResult r) => Fixes.Of(Model(r).Causes, Labels(r));

    public static TheoryData<string> AllAnswers => new()
    {
        "ithaca_106_house_check_answer.json", "ithaca_106_house_after_check_answer.json", "children_odyssey_check_answer.json",
    };

    // ---- change 4: fewer, ranked fixes; never a result hidden; the same order every time ------------------------

    /// <summary>Grouping never hides a result: every cause card is in exactly one fix, and the fixes' results are
    /// exactly the cards' results (each fix's are its cards', in their order), on every real answer.</summary>
    [Theory]
    [MemberData(nameof(AllAnswers))]
    public void Grouping_never_hides_a_result(string file)
    {
        var r = Load(file);
        var cards = Model(r).Causes;
        var fixes = Fixes.Of(cards, Labels(r));
        Assert.All(cards, c => Assert.Single(fixes, f => f.Members.Contains(c)));
        Assert.True(fixes.SelectMany(f => f.Rows).ToHashSet().SetEquals(cards.SelectMany(c => c.Items)));
        Assert.All(fixes, f => Assert.Equal(f.Members.SelectMany(m => m.Items).Distinct(), f.Rows));
        // every card's every result reachable from a fix opened ("See the N results"), and from the detail's fix
        var placed = ResultList.Place(Model(r)).Select(p => p.Row.Id).ToHashSet();
        Assert.All(cards.SelectMany(c => c.Items), id => Assert.True(Fixes.For(fixes, id) is not null && placed.Contains(id), id));
    }

    /// <summary>The ranking is a pure function of the answer: the same fixes in the same order every time, and from
    /// cards in the worker's order whatever else changed (a fresh read of the same answer).</summary>
    [Theory]
    [MemberData(nameof(AllAnswers))]
    public void Ranking_is_deterministic(string file)
    {
        var first = FixesOf(Load(file)).Select(f => f.Key).ToList();
        for (var i = 0; i < 3; i++)
            Assert.Equal(first, FixesOf(Load(file)).Select(f => f.Key));
        var fixes = FixesOf(Load(file));
        // where the fix is made, then the results it clears, then the worker's order: never two in another order
        Assert.All(fixes.Zip(fixes.Skip(1)), p => Assert.True(
            p.First.Tier < p.Second.Tier || p.First.Tier == p.Second.Tier && (p.First.Rows.Count > p.Second.Rows.Count
                || p.First.Rows.Count == p.Second.Rows.Count && p.First.FirstIndex < p.Second.FirstIndex), $"{p.First.Key} before {p.Second.Key}"));
    }

    /// <summary>The house: 46 cards become 8 fixes; fix 1 is the one a click in Revit makes (Project Information), not
    /// the facts Gordium has no field for (the worker's first cards, which have no button); the facts with no field are
    /// one fix, last, with Decide.</summary>
    [Fact]
    public void The_house_opens_on_a_fix_it_can_make_in_Revit()
    {
        var r = House();
        Assert.Equal(46, Model(r).Causes.Count);
        Assert.Equal(CardAction.None, CauseCards.Action(Model(r).Causes[0], Labels(r)));     // the worker's first: no button
        var fixes = FixesOf(r);
        Assert.Equal(8, fixes.Count);
        Assert.Equal("pi", fixes[0].Key);
        Assert.Equal(CardAction.ProjectInformation, fixes[0].Action);
        Assert.Equal("Set 2 facts on Project Information: the stairs list and the guards and handrails list", fixes[0].Title);
        Assert.Equal("In Manage › Project Information, set Gordium: These are all the stairs and Gordium: These are all the guards and handrails, then Check again.",
                     Fixes.Note(fixes[0]));
        Assert.Equal("2 results waiting on this · 2 facts", fixes[0].Count);
        Assert.Equal(["Stairs: 11 things Gordium couldn't measure from the model", "Escape windows: 10 things Gordium couldn't measure from the model"],
                     fixes.Skip(1).Take(2).Select(f => f.Title));
        var nofield = fixes[^1];
        Assert.Equal(("nofield", CardAction.Decide, 3), (nofield.Key, nofield.Action, nofield.Tier));
        Assert.Equal("+5 more fixes (76 results)", Fixes.MoreWords(fixes));
        Assert.Equal(3, Fixes.Shown(fixes, all: false).Count);
        Assert.Equal(8, Fixes.Shown(fixes, all: true).Count);
    }

    /// <summary>The childcare centre: the 5 rooms with no route stay fix 1 (Show), its words the worker's own.</summary>
    [Fact]
    public void The_childcare_centre_opens_on_the_rooms_with_no_route()
    {
        var fixes = FixesOf(Odyssey());
        Assert.Equal(10, fixes.Count);
        Assert.StartsWith("5 rooms have no route to an exit: ", fixes[0].Title);
        Assert.Equal(CardAction.Show, fixes[0].Action);
        Assert.Equal(5, fixes[0].Elements.Count);
        Assert.Equal("10 fixes cover the 183 results that need review or a hand check. Start with these 3: what you can fix in Revit comes first.",
                     Fixes.Intro(fixes));
    }

    /// <summary>A mark's name as a title says it.</summary>
    [Theory]
    [InlineData("Gordium: These are all the stairs", "the stairs list")]
    [InlineData("Gordium: These are all the guards and handrails", "the guards and handrails list")]
    [InlineData("Gordium: Stories", "stories")]
    public void A_mark_said_short(string mark, string said) => Assert.Equal(said, Fixes.Short(mark));

    // ---- change 5: one button word per kind of action ------------------------------------------------------------

    /// <summary>One word per action, everywhere (the cards, the detail): Show, Set in Properties, Open Project
    /// Information, Measure by hand, Decide; never today's "Show and open Properties" or "Check by hand".</summary>
    [Fact]
    public void One_button_word_per_kind_of_action()
    {
        Assert.Equal(["", "Show", "Set in Properties", "Open Project Information", "Measure by hand", "Decide"],
                     Enum.GetValues<CardAction>().Select(Fixes.ButtonWords));
        var cards = Read("CauseCardsView.cs");
        Assert.Contains("Fixes.ButtonWords(g.Action)", cards, StringComparison.Ordinal);
        Assert.Contains("Fixes.ButtonWords(fix.Action)", Read("DetailView.cs"), StringComparison.Ordinal);
        Assert.DoesNotContain("CauseCards.ButtonWords", cards + Read("DetailView.cs") + Read("ResultsView.cs"), StringComparison.Ordinal);
    }

    // ---- change 6: one vocabulary --------------------------------------------------------------------------------

    /// <summary>Results, not rows; "need review", never the worker's "to review" beside it; the same counts.</summary>
    [Fact]
    public void One_vocabulary()
    {
        Assert.Equal("1 result", PaneWords.Results(1));
        Assert.Equal("77 results", PaneWords.Results(77));
        Assert.Equal("8 need review", PaneWords.Count("8 to review"));
        Assert.Equal("1 does not comply", PaneWords.Count("1 does not comply"));
        Assert.Contains("PaneWords.Count(chip.Words)", Read("ResultsView.cs"), StringComparison.Ordinal);
        Assert.Contains("PaneWords.Results(h.Rows)", Read("ResultsList.cs"), StringComparison.Ordinal);
        foreach (var f in FixesOf(House()))
            Assert.DoesNotContain(" rows", f.Count + Fixes.Note(f), StringComparison.Ordinal);
    }

    // ---- changes 1 and 2: the welcome and the header ------------------------------------------------------------

    /// <summary>The welcome shows only while no results were ever shown in the pane, and never with results or the
    /// Setup form; the pane draws it only through that rule, into the empty body that results replace.</summary>
    [Fact]
    public void The_welcome_never_shows_over_results()
    {
        Assert.True(PaneWords.WelcomeShows(PaneShows.Welcome, everShownResults: false));
        Assert.False(PaneWords.WelcomeShows(PaneShows.Welcome, everShownResults: true));
        foreach (var other in new[] { PaneShows.Results, PaneShows.Setup, PaneShows.Error })
        {
            Assert.False(PaneWords.WelcomeShows(other, false));
            Assert.False(PaneWords.WelcomeShows(other, true));
        }
        Assert.Equal(3, PaneWords.WelcomeLines.Count);
        Assert.Contains(PaneWords.WelcomeLines, l => l.Words.Contains("never complies", StringComparison.Ordinal));
        var view = Read("ResultsView.cs");
        var welcome = Between(view, "    private void Welcome(string? checking = null)", "\n    }\n");
        Assert.Contains("if (!PaneWords.WelcomeShows(PaneShows.Welcome, _everShown))\n            return;", welcome, StringComparison.Ordinal);
        Assert.Contains("_missing.Children.Add(frame);", welcome, StringComparison.Ordinal);    // the empty body only
        Assert.Contains("_everShown |= content.Model is not null;", view, StringComparison.Ordinal);
        // results replace the body the welcome is in
        Assert.Contains("_bodyHost.Child = _results;", Between(view, "    internal void Show(PanelContent content)", "\n    }\n"), StringComparison.Ordinal);
    }

    /// <summary>No Check again in the header before anything was checked (the welcome's Check project and the form's
    /// Save are the one action); once results were shown, it stays.</summary>
    [Fact]
    public void The_header_says_check_again_only_after_a_check()
    {
        Assert.False(PaneWords.HeaderCheckAgain(PaneShows.Welcome, false));
        Assert.False(PaneWords.HeaderCheckAgain(PaneShows.Setup, false));
        Assert.True(PaneWords.HeaderCheckAgain(PaneShows.Setup, true));
        Assert.True(PaneWords.HeaderCheckAgain(PaneShows.Results, true));
        Assert.Contains("PaneWords.HeaderCheckAgain(PaneShows.Setup, _everShown)", Read("ResultsView.cs"), StringComparison.Ordinal);
    }

    // ---- change 3: Setup's Save pinned at the foot ---------------------------------------------------------------

    /// <summary>The form's Save is in its footer, which the pane pins at its foot (outside the form's scroll); its
    /// words say whether the check runs after it, and how many facts are needed and chosen.</summary>
    [Fact]
    public void Setup_save_is_pinned_at_the_foot()
    {
        Assert.Equal("Save", PaneWords.SaveAndCheck(0, checksAfter: true));
        Assert.Equal("Save 3 facts", PaneWords.SaveAndCheck(3, checksAfter: false));
        Assert.Equal("Save 1 fact and check", PaneWords.SaveAndCheck(1, checksAfter: true));
        Assert.Equal("4 facts needed; 3 chosen, not saved yet. The street edge is picked on the plan (Pick on plan, above).",
                     PaneWords.SetupFooter(4, 3, streetToPick: true));
        Assert.Equal("1 fact needed; none chosen yet.", PaneWords.SetupFooter(1, 0, streetToPick: false));
        // Revit 2027 trial: opened by Mark facts with everything set, never "0 facts needed" nor Check without them
        Assert.Equal("Every fact the check needs is set.", PaneWords.SetupFooter(0, 0, streetToPick: false));
        var view = Read("ResultsView.cs");
        Assert.Contains("page.Children.Add(_setupFoot);\n        page.Children.Add(_setupScroll);", view, StringComparison.Ordinal);
        Assert.Contains("_setupFoot.Child = _setup.Footer;", view, StringComparison.Ordinal);
        var setup = Read("SetupView.cs");
        Assert.Contains("Footer = MakeFooter();", setup, StringComparison.Ordinal);
        Assert.DoesNotContain("line.Children.Add(save);\n        if (changes > 0)", setup, StringComparison.Ordinal);    // not under the facts
        Assert.DoesNotContain("\n        Children.Add(anyway);", setup, StringComparison.Ordinal);                     // nor Check now anyway first
        // Revit 2027 trial (2026-11-23): shown again after Save (the facts read again), the foot moves to the new page
        // (it was "already the logical child of another element"); in the docked pane the link wraps under Save
        Assert.Contains("if (_setupFoot.Parent is C.Panel before)\n            before.Children.Remove(_setupFoot);", view, StringComparison.Ordinal);
        Assert.Contains("var line = new C.WrapPanel", setup, StringComparison.Ordinal);
        Assert.Contains("var buttons = new C.WrapPanel", Read("CauseCardsView.cs"), StringComparison.Ordinal);
    }

    // ---- change 7: the results' top -------------------------------------------------------------------------------

    /// <summary>Where to start, in one sentence; the filters carry the counts (of the rows placed, by section).</summary>
    [Fact]
    public void The_results_top_says_where_to_start()
    {
        Assert.Equal("Start with what fails, just below; then fix 1.", PaneWords.StartHere(1, 8));
        Assert.Equal("Nothing fails. Start with fix 1 below.", PaneWords.StartHere(0, 10));
        Assert.Equal("Start with what fails, just below.", PaneWords.StartHere(2, 0));
        Assert.Equal("", PaneWords.StartHere(0, 0));
        var placed = ResultList.Place(Model(House()));
        Assert.Equal(placed.Count, PaneWords.FilterCount(placed, ListFilter.All));
        Assert.Equal(1, PaneWords.FilterCount(placed, ListFilter.Fails));
        Assert.Equal(placed.Count, new[] { ListFilter.Fails, ListFilter.Review, ListFilter.Complies }.Sum(f => PaneWords.FilterCount(placed, f)));
        Assert.Equal("Counts by law (Zoning, Egress)", PaneWords.CountsByLaw(["Zoning", null, "Egress"], open: false));
        Assert.Contains("PaneWords.FilterCount(_placed, chip.Filter)", Read("ResultsView.cs"), StringComparison.Ordinal);
    }

    // ---- change 8: a result's detail names its fix ----------------------------------------------------------------

    /// <summary>A result in review with only the generic step gets its fix's number, title and where it is made in its
    /// place; any other step is left as it is.</summary>
    [Fact]
    public void A_results_detail_names_its_fix()
    {
        var r = House();
        var fixes = FixesOf(r);
        var id = fixes[0].Rows[0];
        var detail = new ResultDetail("1 of 1", PanelStatus.Review, "Needs review", "n", null, null, "why",
                                      [new DetailStep(ResultDetail.ResolveStep, DetailAction.None)], [], null, [], null, [], []) { Id = id };
        var step = Fixes.Step(detail, fixes, detail.Steps[0]);
        Assert.NotNull(step);
        Assert.StartsWith("Fix 1: Set 2 facts on Project Information", step!.Words, StringComparison.Ordinal);
        Assert.Null(Fixes.Step(detail, fixes, new DetailStep("Change the design so it meets the limit (the figures below).", DetailAction.None)));
        Assert.Null(Fixes.Step(detail with { Id = "not a row" }, fixes, detail.Steps[0]));
        Assert.Contains("Fixes.Step(d, causes.Groups, step)", Read("DetailView.cs"), StringComparison.Ordinal);
    }

    // ---- change 9: what changed as a short list --------------------------------------------------------------------

    /// <summary>The house after its lot facts were set: 9 verdicts changed, 4 listed with their new verdict's glyph
    /// (complies only from the worker's complies), the rest counted.</summary>
    [Fact]
    public void What_changed_is_a_short_list()
    {
        var change = CheckChanges.Between(Model(House()), new DateTime(2026, 11, 22, 14, 32, 0), Model(HouseAfter()));
        Assert.NotNull(change);
        Assert.Equal("WHAT CHANGED SINCE THE LAST CHECK · 9 verdicts", PaneWords.ChangeHeading(change!));
        Assert.Equal(4, PaneWords.ChangesShown(change!).Count);
        Assert.StartsWith("And 5 more changed verdicts", PaneWords.ChangesMore(change!), StringComparison.Ordinal);
        Assert.True(PaneWords.ChangeIsList(change!));
        // nothing changed: the worker's own line, never "· 0 verdicts" (Revit 2027 trial)
        var same = CheckChanges.Between(Model(House()), new DateTime(2026, 11, 22, 14, 32, 0), Model(House()));
        Assert.False(PaneWords.ChangeIsList(same!));
        Assert.Contains("if (!PaneWords.ChangeIsList(change))", Read("ResultsView.cs"), StringComparison.Ordinal);
        Assert.Equal(Tone.Complies, PaneWords.ChangeTone(new RowChange("a", "a", Verdict.NeedsReview, Verdict.Complies, "a now complies")));
        Assert.Equal(Tone.Review, PaneWords.ChangeTone(new RowChange("a", "a", Verdict.Complies, Verdict.NeedsReview, "a")));
        Assert.Equal(Tone.Review, PaneWords.ChangeTone(new RowChange("a", "a", Verdict.Complies, null, "a no longer in the check")));
    }

    // ---- changes 10 and 11: error and stale in plain words ---------------------------------------------------------

    /// <summary>The error says nothing passed and nothing changed, with Try again and Copy details; the exception and
    /// the log's path go to the clipboard and the tooltip, never the pane's words. Stale says so with its own Check again.</summary>
    [Fact]
    public void Error_and_stale_are_in_plain_words()
    {
        Assert.Contains("nothing here passes", PaneWords.ErrorWords, StringComparison.Ordinal);
        Assert.Equal("The model changed after this check (14:32)", PaneWords.StaleTitle(StaleReason.ModelChanged, new DateTime(2026, 11, 22, 14, 32, 0)));
        var view = Read("ResultsView.cs");
        var failed = Between(view, "    internal void Failed(string words)", "\n    }\n");
        Assert.Contains("ToolTip = words", failed, StringComparison.Ordinal);
        Assert.Contains("W.Clipboard.SetText(words)", failed, StringComparison.Ordinal);
        Assert.DoesNotContain("Say(_checkAgainState.Status(words))", failed, StringComparison.Ordinal);   // never the words on screen
        Assert.DoesNotContain("Text = words", failed, StringComparison.Ordinal);
        var stale = Between(view, "                case PanelPart.Stale:", "break;");
        Assert.Contains("PaneWords.StaleTitle(", stale, StringComparison.Ordinal);
        Assert.Contains("CauseCardsView.Primary(\"Check again\"", stale, StringComparison.Ordinal);
    }

    // ---- helpers -------------------------------------------------------------------------------------------------

    private static string Read(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file)).Replace("\r\n", "\n", StringComparison.Ordinal);

    private static string Between(string text, string start, string end)
    {
        var a = text.IndexOf(start, StringComparison.Ordinal);
        Assert.True(a >= 0, "not found: " + start);
        var b = text.IndexOf(end, a + start.Length, StringComparison.Ordinal);
        return text[a..(b < 0 ? text.Length : b + end.Length)];
    }
}
