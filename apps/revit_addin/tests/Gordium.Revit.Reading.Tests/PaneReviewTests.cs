using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Review round 1 of the intuitive pane (2026-11-23), each fix pinned by a test that fails when it is taken out:
/// what the pane says comes from the same rule as what it does (Save's words from SetupGate, the stale title from why,
/// the progress line from Fixes.Progress, a mark fix's count from the elements Show selects); anything with a verdict
/// colour follows stale (What changed's glyphs); a joined fix's properties hold for every card it joins (the action is
/// part of the key), and a fix's "looked at" tick is carried to the next check when the fix is the same.</summary>
public sealed class PaneReviewTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static readonly string Answers = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers");

    private static CheckResult House() =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(File.ReadAllText(Path.Combine(Answers, "ithaca_106_house_check_answer.json"), Encoding.UTF8))
                                               .RootElement.GetProperty("result").Clone(), About));

    private static CheckResult Parse(JsonObject result) =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(result.ToJsonString()).RootElement, About));

    private static ResultModel Model(CheckResult r) => ResultRows.Build(r, null, [], null);

    private static string Read(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file)).Replace("\r\n", "\n", StringComparison.Ordinal);

    private static JsonObject Item(string id) => new()
    {
        ["id"] = id, ["name"] = id, ["group"] = "law", ["status"] = "needs_review", ["reason"] = "r", ["objects"] = new JsonArray(),
    };

    private static JsonObject Card(string key, string kind, string words, string[] items, string[] elements) => new()
    {
        ["key"] = key, ["kind"] = kind, ["words"] = words, ["items"] = new JsonArray(items.Select(i => (JsonNode)i).ToArray()),
        ["elements"] = new JsonArray(elements.Select(i => (JsonNode)i).ToArray()),
    };

    /// <summary>An answer of rows a, b, c in review with these cause cards (one review group).</summary>
    private static CheckResult Answer(params JsonObject[] cards) => Parse(new JsonObject
    {
        ["view"] = new JsonObject
        {
            ["items"] = new JsonArray(Item("a"), Item("b"), Item("c")), ["summary"] = "s", ["state"] = "needs_review",
            ["groups"] = new JsonArray(new JsonObject
            {
                ["key"] = "review", ["title"] = "Needs review", ["items"] = new JsonArray("a", "b", "c"),
                ["causes"] = new JsonArray(cards.Select(c => (JsonNode)c).ToArray()),
            }),
        },
        ["report_error"] = null,
    });

    // ---- Class A: what the panel says comes from the same rule as what it does --------------------------------------

    /// <summary>P2, as the UI polish has it (change 7): Save always writes and then checks ("Save and check"), so its
    /// words never depend on what stays unset; the footer says what Save writes and what stays unset, by the steps'
    /// own titles (the same Done rule the steps' circles use).</summary>
    [Fact]
    public void Save_and_check_says_what_it_writes_and_what_stays_unset()
    {
        var stories = new SetupField(Marks.Stories, "Stories", FieldKind.Number, SetupFacts.OtherGroup, false, [], "2", "law", null);
        var ready = new SetupScreen("house", [stories], [], [], []);
        var draft = new SetupDraft();
        draft.Choose(Marks.Stories, "3");
        Assert.Equal("Save 1 and check", PaneWords.SaveAndCheck(PaneWords.Unsaved(ready, draft)));
        Assert.Equal("Saves 1 fact to Project Information (one undo).", PaneWords.SetupFooter(ready with { Steps = SetupSteps.Of(ready, draft) }, draft));
        // waiting on the zone and the use: the zone chosen, the use still to set
        var zone = new SetupField(Marks.Zone, "Zone", FieldKind.Choice, SetupFacts.NeededGroup, true, [new("R-1b", "R-1b")], null, "law", null);
        var use = new SetupField(Marks.Use, "Use", FieldKind.Choice, SetupFacts.NeededGroup, true, [new("one_family_detached", "One-family")], null, "law", null);
        var waiting = new SetupScreen("house", [zone, use], [], [], [Marks.Zone.Name, Marks.Use.Name]);
        // nothing chosen: without the zoning district nothing is checked (said first), then what a blank does
        Assert.Equal(PaneWords.NoZone + " " + PaneWords.BlankFact, PaneWords.SetupFooter(waiting, new SetupDraft()));
        var chosen = new SetupDraft();
        chosen.Choose(Marks.Zone, "R-1b");
        Assert.Equal("Saves 1 fact to Project Information (one undo). Use isn't set yet: its rules will need review.",
                     PaneWords.SetupFooter(waiting, chosen));
        Assert.Contains("PaneWords.SetupFooter(_screen, _draft)", Read("SetupView.cs"), StringComparison.Ordinal);
    }

    /// <summary>P3: the stale banner's title comes from why the results are stale (data in the model, not words
    /// matched): a cancelled check's earlier results never say "The model changed".</summary>
    [Fact]
    public void The_stale_title_says_why()
    {
        var at = new DateTime(2026, 11, 22, 14, 32, 0);
        var model = Model(House());
        Assert.Equal(StaleReason.ModelChanged, ResultRows.Stale(model, at).StaleKind);
        Assert.Equal(StaleReason.Cancelled, ResultRows.Stale(model, at, CheckWords.CancelledStale(at), StaleReason.Cancelled).StaleKind);
        Assert.Null(model.StaleKind);
        Assert.Equal("Check cancelled", PaneWords.StaleTitle(StaleReason.Cancelled, at));
        Assert.DoesNotContain("model changed", PaneWords.StaleTitle(StaleReason.Cancelled, at) + PaneWords.StaleWords(StaleReason.Cancelled, at), StringComparison.OrdinalIgnoreCase);
        Assert.Equal("The model changed after this check", PaneWords.StaleTitle(StaleReason.ModelChanged, at));
        Assert.StartsWith("These results are from 14:32 and may be out of date.", PaneWords.StaleWords(StaleReason.ModelChanged, at), StringComparison.Ordinal);
        var view = Read("ResultsView.cs");
        Assert.Contains("PaneWords.StaleTitle(why,", view, StringComparison.Ordinal);
        Assert.Contains("CheckWords.CancelledStale(content.When), StaleReason.Cancelled)", view, StringComparison.Ordinal);
    }

    /// <summary>P3: the progress line redrawn after a tick is Fixes.Progress, the same words as when drawn.</summary>
    [Fact]
    public void The_progress_line_is_one_rule()
    {
        var view = Read("ResultsView.cs");
        Assert.Contains("line.Text = Fixes.Progress(_looked, Groups, _placed);", view, StringComparison.Ordinal);
        Assert.DoesNotContain("line.Text = $\"Looked at:", view, StringComparison.Ordinal);
        Assert.Contains("Fixes.Progress(host.Looked, all, host.Placed)", Read("CauseCardsView.cs"), StringComparison.Ordinal);
    }

    /// <summary>P3: a joined mark fix counts the elements Set in Properties selects (ShowIds: those the project has),
    /// not the worker's raw ids (which can name a measured part that is no element).</summary>
    [Fact]
    public void A_mark_fix_counts_what_Show_selects()
    {
        var r = Answer(Card("mark:door:exit:1", "mark", "door D1: `exit`", ["a"], ["d1", "<corridor> (dead end 2)"]),
                       Card("mark:door:exit:2", "mark", "door D2: `exit`", ["b"], ["d2"]));
        var labels = new Dictionary<string, string> { ["d1"] = "Door D1", ["d2"] = "Door D2" };
        var fixes = Fixes.Of(Model(r).Causes, labels);
        var exit = Assert.Single(fixes, f => f.Key.StartsWith("marks:", StringComparison.Ordinal));
        Assert.Equal(2, Fixes.ShowIds(exit, labels).Count);
        Assert.Equal($"Set {Marks.ExitDoor.Name} on 2 elements", exit.Title);
    }

    // ---- Class B: a verdict colour follows stale ---------------------------------------------------------------------

    /// <summary>P2: What changed on stale results shows the clock, never a green complies; every glyph of the pane is
    /// drawn through StatusLook with stale.</summary>
    [Fact]
    public void What_changed_follows_stale()
    {
        var complies = new RowChange("a", "a", Verdict.NeedsReview, Verdict.Complies, "a now complies");
        Assert.Equal(PanelStatus.Complies, PaneWords.ChangeStatus(complies, stale: false));
        Assert.Equal(PanelStatus.Stale, PaneWords.ChangeStatus(complies, stale: true));
        foreach (var v in Enum.GetValues<Verdict>())
            Assert.NotEqual(PanelStatus.Complies, PaneWords.ChangeStatus(complies with { After = v }, stale: true));
        var view = Read("ResultsView.cs");
        Assert.Contains("summary.Children.Add(ChangeLine(change, stale));", view, StringComparison.Ordinal);
        Assert.Contains("WithGlyph(PaneWords.ChangeStatus(r, stale)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("StatusLook.Of(PaneWords.ChangeTone(r), false)", view, StringComparison.Ordinal);
        Assert.DoesNotContain("StatusLook.Of(model.StateTone, false)", view, StringComparison.Ordinal);   // the sweep
        Assert.Contains("StatusLook.Of(Tone.Review, host.Stale)", Read("CauseCardsView.cs"), StringComparison.Ordinal);
    }

    // ---- Class C: a joined fix's properties come from all of its members ---------------------------------------------

    /// <summary>P2: two cards of one kind with different buttons (one names an element the project has, one names
    /// none) are two fixes, each with its own button and tier, never one fix with the first card's button.</summary>
    [Fact]
    public void Cards_with_different_buttons_never_join()
    {
        var r = Answer(Card("model:stair:a", "fix_model", "a not measured", ["a"], ["s1"]),
                       Card("model:stair:b", "fix_model", "b not measured", ["b"], []));
        var labels = new Dictionary<string, string> { ["s1"] = "Stair 1" };
        var fixes = Fixes.Of(Model(r).Causes, labels);
        Assert.Equal(2, fixes.Count);
        Assert.Equal([CardAction.Show, CardAction.None], fixes.Select(f => f.Action));
        Assert.All(fixes, f => Assert.All(f.Members, m => Assert.Equal(f.Action, CauseCards.Action(m, labels))));
        Assert.Equal([0, 1], fixes.Select(f => f.Tier));
        // the same button: joined, one fix of both
        var same = Fixes.Of(Model(Answer(Card("model:stair:a", "fix_model", "a", ["a"], []), Card("model:stair:b", "fix_model", "b", ["b"], []))).Causes, labels);
        Assert.Equal("Stairs: 2 things Gordium couldn't measure from the model", Assert.Single(same).Title);
    }

    /// <summary>P2: a fix's "looked at" tick is carried to the next check when the fix is the same (its cards' keys,
    /// words and rows, in order): the same answer twice keeps the tick on "pi"; a changed card drops it.</summary>
    [Fact]
    public void A_fix_tick_is_carried_when_the_fix_is_the_same()
    {
        var model = Model(House());
        var labels = new Dictionary<string, string>();
        var looked = new LookedAt();
        looked.SetCard("pi", true);
        Assert.True(LookedAt.Carry(looked, model, Model(House()), labels, labels).Card("pi"));
        // a card of the fix changed (its words): the tick dropped
        var changed = model with { Causes = model.Causes.Select(c => Fixes.KeyOf(c, labels) == "pi" ? c with { Words = c.Words + " (changed)" } : c).ToList() };
        Assert.False(LookedAt.Carry(looked, model, changed, labels, labels).Card("pi"));
        Assert.Contains("LookedAt.Carry(t.Looked, t.Model, model, t.Labels, content.Labels)", Read("ResultsView.cs"), StringComparison.Ordinal);
    }
}
