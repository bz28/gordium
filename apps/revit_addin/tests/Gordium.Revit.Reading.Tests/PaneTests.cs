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
        // the worker's first card, the ADU fact, has its mark on Project Information since 2026-11-22 (Gordium: Accessory
        // dwelling unit, the NY code decision's marks), so it too is set there
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(Model(r).Causes[0], Labels(r)));
        var fixes = FixesOf(r);
        Assert.Equal(8, fixes.Count);
        Assert.Equal("pi", fixes[0].Key);
        Assert.Equal(CardAction.ProjectInformation, fixes[0].Action);
        // the ADU's fact joins the two lists there (its mark since 2026-11-22), and since UI design change 20 the
        // stream, the household and the garage too: 9 facts, counted by their marks (the stream's card asks two)
        Assert.StartsWith("Set 9 facts on Project Information: ", fixes[0].Title, StringComparison.Ordinal);
        foreach (var said in new[] { "stream within 20 ft", "distance from stream", "unrelated people per unit", "owner-occupied",
                     "functional family unit", "garage cars" })
            Assert.Contains(said, fixes[0].Title, StringComparison.Ordinal);
        Assert.EndsWith("the stairs list and the guards and handrails list", fixes[0].Title, StringComparison.Ordinal);
        Assert.Contains("accessory dwelling unit", fixes[0].Title, StringComparison.OrdinalIgnoreCase);
        var note = Fixes.Note(fixes[0]);
        Assert.StartsWith("In Manage › Project Information, set Gordium: ", note, StringComparison.Ordinal);
        foreach (var mark in new[] { "Gordium: Accessory dwelling unit", "Gordium: Stream within 20 ft", "Gordium: Distance from stream",
                     "Gordium: Unrelated people per unit", "Gordium: Owner-occupied", "Gordium: Functional family unit", "Gordium: Garage cars",
                     "Gordium: These are all the stairs", "Gordium: These are all the guards and handrails" })
            Assert.Contains(mark, note, StringComparison.Ordinal);
        Assert.EndsWith(", then Check again.", note, StringComparison.Ordinal);
        Assert.Equal("11 results waiting on this · 9 facts", fixes[0].Count);   // 2, the ADU card's 6, and the stream's, household's and garage's
        Assert.Equal(["Stairs: 11 things Gordium couldn't measure from the model", "Escape windows: 10 things Gordium couldn't measure from the model"],
                     fixes.Skip(1).Take(2).Select(f => f.Title));
        var nofield = fixes[^1];
        Assert.Equal(("nofield", CardAction.Decide, 3), (nofield.Key, nofield.Action, nofield.Tier));
        Assert.Equal("+5 more fixes (67 results)", Fixes.MoreWords(fixes));   // the stream's, household's and garage's results now in fix 1
        Assert.Equal(4, nofield.Members.Count);         // what is left with no field: the nosings fact and the three "all of them" lists
        Assert.DoesNotContain(nofield.Members, c => c.Fields.Any(f => f is "facts.stream_near_lot" or "facts.unrelated_persons" or "facts.garage_cars"));
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
        Assert.Contains(PaneWords.WelcomeLines, l => l.Words.Contains("It never guesses a pass", StringComparison.Ordinal));
        Assert.Contains(PaneWords.WelcomeLines, l => l.Icon == PaneIcon.Review && l.Words.Contains("Needs review", StringComparison.Ordinal));
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
        Assert.Equal("Save and check", PaneWords.SaveAndCheck(0));
        Assert.Equal("Save 4 and check", PaneWords.SaveAndCheck(4));
        Assert.Equal("Saves 4 facts to Project Information (one undo). Escape openings and exit doors still need marking: their rules will need review.",
                     PaneWords.SetupFooter(4, [], ["escape openings", "exit doors"]));
        Assert.Equal("Saves 1 fact to Project Information (one undo). Street edge isn't set yet: its rules will need review.",
                     PaneWords.SetupFooter(1, ["street edge"], []));
        Assert.Equal(PaneWords.BlankFact, PaneWords.SetupFooter(0, ["zoning district"], []));
        // opened by Set up with everything set: only what Save writes
        Assert.Equal("Saves 2 facts to Project Information (one undo).", PaneWords.SetupFooter(2, [], []));
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
        Assert.StartsWith("Fix 1: Set 9 facts on Project Information", step!.Words, StringComparison.Ordinal);   // the ADU's, the stream's, the household's and the garage's too
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
        // UI polish change 40: "Since 14:32 · 9 results changed", four listed, "Show all 9" opens every one in place
        Assert.Equal("Since 14:32 · 9 results changed", PaneWords.ChangeHeading(change!));
        Assert.Equal(4, PaneWords.ChangesShown(change!).Count);
        Assert.Equal("Show all 9", PaneWords.ChangesMore(change!));
        Assert.Equal(change!.Rows, PaneWords.ChangesShown(change!, all: true));
        Assert.Equal("Show fewer", PaneWords.ChangesMore(change!, all: true));
        Assert.True(PaneWords.ChangeIsList(change!));
        // nothing changed: the worker's own line, never "· 0 verdicts" (Revit 2027 trial)
        var same = CheckChanges.Between(Model(House()), new DateTime(2026, 11, 22, 14, 32, 0), Model(House()));
        Assert.False(PaneWords.ChangeIsList(same!));
        Assert.Contains("if (!PaneWords.ChangeIsList(change))", Read("ResultsView.cs"), StringComparison.Ordinal);
        Assert.Equal(Tone.Complies, PaneWords.ChangeTone(new RowChange("a", "a", Verdict.NeedsReview, Verdict.Complies, "a now complies")));
        Assert.Equal(Tone.Review, PaneWords.ChangeTone(new RowChange("a", "a", Verdict.Complies, Verdict.NeedsReview, "a")));
        Assert.Equal(Tone.Review, PaneWords.ChangeTone(new RowChange("a", "a", Verdict.Complies, null, "a no longer in the check")));
    }

    /// <summary>What changed lists every changed result in place ("Show all 9"), never behind a hover (UI polish change
    /// 40: "(hover for all)" goes); for a screen reader its words still say every one (ChangesAll).</summary>
    [Fact]
    public void What_changed_shows_all_in_place_and_says_every_result_it_counts()
    {
        var change = CheckChanges.Between(Model(House()), new DateTime(2026, 11, 22, 14, 32, 0), Model(HouseAfter()))!;
        var all = PaneWords.ChangesAll(change).Split('\n');
        Assert.Equal(change.Rows.Select(r => "• " + r.Words), all.Where(l => l.StartsWith("• ", StringComparison.Ordinal)));
        var view = Read("ResultsView.cs");
        Assert.Contains("foreach (var r in PaneWords.ChangesShown(change, _changesAll))", view, StringComparison.Ordinal);
        Assert.DoesNotContain("ToolTip = PaneWords.ChangesAll(change)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("hover for all", string.Join("\n", PaneWords.ChangesMore(change), PaneWords.ChangesSaid(change)), StringComparison.Ordinal);
        // review round 1: what the architect changed is said even when no verdict changed, and the stale notice comes
        // before What changed
        var line = Between(view, "    private C.Border ChangeLine(CheckChange change, bool stale)", "\n    }\n");
        Assert.Equal(2, System.Text.RegularExpressions.Regex.Matches(line, @"_factsChanged is \{ \} ").Count);
        Assert.Contains("_change is { } top && !parts.Contains(PanelPart.Stale)", view, StringComparison.Ordinal);
        Assert.Contains("summary.Children.Add(ChangeLine(afterStale, stale));", view, StringComparison.Ordinal);
    }

    /// <summary>"You changed: …" (change 40) says each project fact that differs between the two checks, by its name and
    /// new value, and nothing when one check's facts aren't known.</summary>
    [Fact]
    public void What_changed_says_the_facts_the_architect_changed()
    {
        RevitModel M(params (MarkDefinition Mark, MarkValue Value)[] marks) => new()
        {
            Document = "x.rvt", Marked = [], ProjectMarks = marks.ToDictionary(m => m.Mark.Guid, m => m.Value),
        };
        IReadOnlyList<SetupField> F(RevitModel m) => SetupScreen.Build(m, [], null).Fields;
        var before = F(M((Marks.CornerLot, new MarkValue(true, 1))));
        var after = F(M((Marks.CornerLot, new MarkValue(true, 0)), (Marks.DwellingUnits, new MarkValue(true, 4))));
        var said = PaneWords.FactsChanged(before, after);
        Assert.NotNull(said);
        Assert.StartsWith("You changed: ", said, StringComparison.Ordinal);
        Assert.Contains(": No", said, StringComparison.Ordinal);
        Assert.Contains(": 4", said, StringComparison.Ordinal);
        Assert.Null(PaneWords.FactsChanged(before, before));
        Assert.Null(PaneWords.FactsChanged(null, after));
        // review round 2: a fact changed and no result did: "No result changed since 14:32.", never "Nothing changed"
        var none = CheckChanges.Between(Model(House()), new DateTime(2026, 11, 22, 14, 32, 0), Model(House()))!;
        Assert.Equal("No result changed since 14:32.", PaneWords.ChangeWords(none, factsChanged: true));
        Assert.StartsWith("Nothing changed", PaneWords.ChangeWords(none, factsChanged: false), StringComparison.Ordinal);
        Assert.Contains("PaneWords.ChangeWords(change, _factsChanged is not null)", Read("ResultsView.cs"), StringComparison.Ordinal);
        // review round 3: and a screen reader hears the same words, not the checker's "Nothing changed"
        Assert.Contains(": string.Join(\" \", new[] { PaneWords.ChangeWords(change, _factsChanged is not null), _factsChanged }.OfType<string>())", Read("ResultsView.cs"), StringComparison.Ordinal);
        // review round 4: with a list too: the heading shown ("Since 14:32 · 9 results changed") and what you changed
        Assert.Contains("? string.Join(\" \", new[] { PaneWords.ChangeHeading(change) + \".\", _factsChanged, PaneWords.ChangesAll(change) }.OfType<string>())", Read("ResultsView.cs"), StringComparison.Ordinal);
        // review round 5: the count said once (the heading's), the same-verdict line in the card's own words
        var listed = CheckChanges.Between(Model(House()), new DateTime(2026, 11, 22, 14, 32, 0), Model(HouseAfter()))!;
        Assert.DoesNotContain("changed:", PaneWords.ChangesAll(listed), StringComparison.Ordinal);
        Assert.StartsWith("• ", PaneWords.ChangesAll(listed), StringComparison.Ordinal);
        var saidOne = listed with { Said = 1 };
        Assert.EndsWith(PaneWords.ChangesSaid(saidOne)!, PaneWords.ChangesAll(saidOne), StringComparison.Ordinal);
        // review after main 7bdad7c5: an area (#193) said in its own unit, the same area in other units is no change,
        // an unreadable one is said so; the R-2 units (#194) by their word, the same word in another case no change
        IReadOnlyList<SetupField> Fa(RevitModel m, string units) => SetupScreen.Build(m with { AreaDisplayUnits = units }, [], null).Fields;
        const string SqM = "autodesk.unit.unit:squareMeters-1.0.1";
        var area500 = M((Marks.AduFloorArea, new MarkValue(true, Number: 500)));
        var area600 = M((Marks.AduFloorArea, new MarkValue(true, Number: 600)));
        Assert.Contains("(m²): 55.741824", PaneWords.FactsChanged(Fa(area500, SqM), Fa(area600, SqM)), StringComparison.Ordinal);
        Assert.Null(PaneWords.FactsChanged(Fa(area500, "SquareFeet"), Fa(area500, SqM)));
        var bigArea = PaneWords.FactsChanged(Fa(area500, SqM), Fa(M((Marks.AduFloorArea, new MarkValue(true, Text: "big"))), SqM));
        Assert.Contains("a value Gordium can't read", bigArea, StringComparison.Ordinal);
        Assert.DoesNotContain("cleared", bigArea, StringComparison.Ordinal);
        var dwellings = F(M((Marks.R2SleepingUnits, new MarkValue(true, Text: "All dwelling units"))));
        var both = PaneWords.FactsChanged(dwellings, F(M((Marks.R2SleepingUnits, new MarkValue(true, Text: "Both")))));
        Assert.Contains(": Both", both, StringComparison.Ordinal);
        Assert.Null(PaneWords.FactsChanged(F(M((Marks.R2SleepingUnits, new MarkValue(true, Text: "both")))), F(M((Marks.R2SleepingUnits, new MarkValue(true, Text: "Both"))))));
        Assert.Contains("a value Gordium can't read", PaneWords.FactsChanged(dwellings, F(M((Marks.R2SleepingUnits, new MarkValue(true, Text: "some")))))!, StringComparison.Ordinal);
        var cleared = PaneWords.FactsChanged(after, F(M()));
        Assert.Contains("cleared", cleared, StringComparison.Ordinal);
        // a building Yes/No fact holding something that isn't Yes or No (it has a problem, no current value): said as
        // unreadable, never cleared, and a change into it from blank is said too
        var odd = F(M((Marks.AssemblyFixedSeating, new MarkValue(true, Text: "maybe"))));
        Assert.NotNull(odd.Single(x => x.Mark == Marks.AssemblyFixedSeating).Problem);
        var intoOdd = PaneWords.FactsChanged(F(M((Marks.AssemblyFixedSeating, new MarkValue(true, 1)))), odd);
        Assert.Contains("a value Gordium can't read", intoOdd, StringComparison.Ordinal);
        Assert.DoesNotContain("cleared", intoOdd, StringComparison.Ordinal);
        Assert.Contains("a value Gordium can't read", PaneWords.FactsChanged(F(M()), odd), StringComparison.Ordinal);
        // the same use read before and after the place's options arrived (its list, so its problem, known only then): no change
        var options = new PlaceOptions(["R-3a"], [("multiple_family", "Multiple family dwelling")], new Dictionary<string, IReadOnlyList<UseChoice>>());
        var typedUse = M((Marks.Use, new MarkValue(true, Text: "Multiple_Family")));
        var withList = SetupScreen.Build(typedUse, [], options).Fields;
        Assert.NotNull(withList.Single(x => x.Mark == Marks.Use).Problem);
        Assert.Null(PaneWords.FactsChanged(F(typedUse), withList));
        // a street edge picked again is said so, never by its coordinates
        var edgeA = F(M((Marks.StreetEdge, new MarkValue(true, Text: StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(10, 0, 0))])))));
        var edgeB = F(M((Marks.StreetEdge, new MarkValue(true, Text: StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(0, 10, 0))])))));
        Assert.Equal("You changed: " + SetupSteps.Title(Marks.StreetEdge, edgeB.Single(x => x.Mark == Marks.StreetEdge).Label) + " picked again.",
                     PaneWords.FactsChanged(edgeA, edgeB));
    }

    /// <summary>The proportion bar (change 18): one segment per verdict, worst first, as long as its count; never green
    /// while anything fails, needs review or isn't checked yet; the clock once stale.</summary>
    [Fact]
    public void The_proportion_bar_is_never_green_while_anything_is_unsettled()
    {
        Verdict[] apartment = [.. Enumerable.Repeat(Verdict.NeedsReview, 98), .. Enumerable.Repeat(Verdict.NotChecked, 8), Verdict.Complies, Verdict.NotApplicable];
        var bar = ProportionBar.Segments(apartment, stale: false);
        Assert.Equal([(PanelStatus.Review, 98), (PanelStatus.NotChecked, 8), (PanelStatus.NotApplicable, 1), (PanelStatus.NotApplicable, 1)],
                     bar.Select(b => (b.Status, b.Count)));
        // review round 1: each slice says its own verdict on hover, the complying one drawn neutral still "1 complies"
        Assert.Equal(["98 need review", "8 not checked yet", "1 complies", "1 doesn't apply"], bar.Select(b => b.Words));
        Assert.Contains("ToolTip = segments[i].Words", Read("ResultsView.cs"), StringComparison.Ordinal);
        Assert.Equal(apartment.Length, bar.Sum(b => b.Count));
        Assert.DoesNotContain(bar, b => b.Status == PanelStatus.Complies);
        Assert.Equal([(PanelStatus.Complies, 2), (PanelStatus.NotApplicable, 1)],
                     ProportionBar.Segments([Verdict.Complies, Verdict.Complies, Verdict.NotApplicable], stale: false).Select(b => (b.Status, b.Count)));
        Assert.Equal("1 complied", ProportionBar.Segments([Verdict.Complies, Verdict.NeedsReview], stale: true)[1].Words);
        Assert.All(ProportionBar.Segments([Verdict.Complies, Verdict.DoesNotComply], stale: true), b => Assert.Equal(PanelStatus.Stale, b.Status));
        Assert.Equal(PanelStatus.Fails, ProportionBar.Segments([Verdict.Complies, Verdict.DoesNotComply], stale: false)[0].Status);
    }

    /// <summary>Each group of work has its kind's icon (change 46); what fails, isn't checked or is settled has none
    /// (its status glyph says it).</summary>
    [Fact]
    public void Each_kind_of_work_has_its_own_icon()
    {
        var kinds = new[] { FixKind.Answer, FixKind.Mark, FixKind.FixModel, FixKind.Survey, FixKind.Measure, FixKind.Decide, FixKind.OpenQuestion };
        var icons = kinds.Select(ResultViewList.IconOf).ToList();
        Assert.All(icons, i => Assert.NotNull(i));
        Assert.Equal(kinds.Length, icons.Distinct().Count());
        Assert.All(new[] { FixKind.Fails, FixKind.NotChecked, FixKind.Done }, k => Assert.Null(ResultViewList.IconOf(k)));
    }

    /// <summary>The house's Project Information fix says one number of facts everywhere: its title, its count and the
    /// opened card's overline (review round 1 of change 20: the overline counted its cards as facts).</summary>
    [Fact]
    public void The_house_project_information_fix_never_claims_two_numbers_of_facts()
    {
        var fix = FixesOf(House())[0];
        Assert.Equal("pi", fix.Key);
        var numbers = new[] { fix.Title, fix.Count, fix.MembersWords }
            .SelectMany(w => System.Text.RegularExpressions.Regex.Matches(w, @"(\d+) facts").Select(m => m.Groups[1].Value)).Distinct().ToList();
        Assert.Equal(["9"], numbers);
        Assert.Equal("The 6 causes asking 9 facts, in Gordium's checker's words", fix.MembersWords);
        Assert.Contains("Overline(g.MembersWords)", Read("CauseCardsView.cs"), StringComparison.Ordinal);
    }

    // ---- changes 10 and 11: error and stale in plain words ---------------------------------------------------------

    /// <summary>The error card (UI polish changes 13, 14): one message per failure, the technical words (the exception,
    /// the log's path) only on the clipboard through Copy details, never on screen nor in any tooltip. The stale banner
    /// (change 39): slim, without its own Check again (the header's is the one action).</summary>
    [Fact]
    public void Error_and_stale_are_in_plain_words()
    {
        Assert.Equal("The model changed after this check", PaneWords.StaleTitle(StaleReason.ModelChanged, new DateTime(2026, 11, 22, 14, 32, 0)));
        var view = Read("ResultsView.cs");
        var failed = Between(view, "    internal void Failed(CheckFailure? failure)", "\n    }\n");
        Assert.DoesNotContain("ToolTip", failed, StringComparison.Ordinal);                    // change 14
        Assert.Contains("W.Clipboard.SetText(words)", failed, StringComparison.Ordinal);
        Assert.DoesNotContain("Text = words", failed, StringComparison.Ordinal);
        Assert.Contains("Text = failure.Title", failed, StringComparison.Ordinal);
        var stale = Between(view, "                case PanelPart.Stale:", "break;");
        Assert.Contains("PaneWords.StaleTitle(", stale, StringComparison.Ordinal);
        Assert.DoesNotContain("Check again", stale, StringComparison.Ordinal);                 // change 39
        Assert.DoesNotContain("ToolTip", stale, StringComparison.Ordinal);
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
