using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The results panel's Revit-free supports: its action queue (a request Revit refuses is dropped, never run
/// later unasked, and what was greyed comes back) and when the street edge is asked for by a click.</summary>
public sealed class PanelSupportTests
{
    /// <summary>Review round 1 (P3): a refused Raise left Check again greyed and the job queued, to run unasked with
    /// the next accepted action.</summary>
    [Fact]
    public void A_refused_request_is_dropped_and_its_refusal_runs_and_the_next_one_runs_alone()
    {
        string? answer = "Denied";
        var queue = new ActionQueue<List<string>>(() => answer);
        var refusals = 0;
        Assert.Equal("Denied", queue.Post("Check again", ran => ran.Add("check"), () => refusals++));
        Assert.Equal(0, queue.Count);
        Assert.Equal(1, refusals);

        answer = null;                                     // Revit takes the next one
        Assert.Null(queue.Post("Show in model", ran => ran.Add("zoom"), () => refusals++));
        Assert.Equal(1, refusals);
        var ran = new List<string>();
        queue.Run(ran, (_, e) => throw e);
        Assert.Equal(["zoom"], ran);                       // never the refused check, unasked
        Assert.Equal(0, queue.Count);
    }

    /// <summary>Review round 2 (P3): an edit while Check again waited redrew the panel greyed, re-enabled the button
    /// and erased "Checking...". The waiting survives every redraw until the check ends.</summary>
    [Fact]
    public void A_redraw_while_a_check_waits_keeps_check_again_greyed_and_checking_said()
    {
        var state = new CheckAgainState();
        Assert.True(state.Enabled);
        Assert.Equal("", state.Status(""));
        state.Start();
        Assert.False(state.Enabled);                       // the redraw (MarkStale's Show) reads this
        Assert.Equal("Checking...", state.Status(""));
        Assert.Equal("Checking...", state.Status("Added 3 Gordium marks to this project."));
        Assert.Equal("Checking...", state.Status(""));           // a later greyed redraw: nothing to say
        // review round 3: said once it ends, while the panel still says Checking...
        Assert.Equal("Added 3 Gordium marks to this project.", state.Stop("Checking..."));
        Assert.True(state.Enabled);
        Assert.Equal("Added 3 Gordium marks to this project.", state.Status("Added 3 Gordium marks to this project."));
        state.Start();
        Assert.Equal("", state.Stop("Checking..."));             // nothing held from before
        state.Start();
        state.Status("Added 3 Gordium marks to this project.");
        // a failure said meanwhile (Failed, a refusal) is kept as it is
        Assert.Equal("Nothing was checked: IOException: x", state.Stop("Nothing was checked: IOException: x"));
    }

    [Fact]
    public void Taken_actions_run_in_order_and_one_that_throws_doesnt_stop_the_rest()
    {
        var queue = new ActionQueue<List<string>>(() => null);
        queue.Post("a", ran => ran.Add("a"));
        queue.Post("b", _ => throw new InvalidOperationException("no"));
        queue.Post("c", ran => ran.Add("c"));
        var ran = new List<string>();
        var failed = new List<string>();
        queue.Run(ran, (what, e) => failed.Add($"{what}: {e.Message}"));
        Assert.Equal(["a", "c"], ran);
        Assert.Equal(["b: no"], failed);
    }

    private static ProjectFactsRead Facts(params MarkDefinition[] set)
    {
        var h = FakeHouse.Draw("5_basement_window_well");
        foreach (var m in new[] { Marks.Zone, Marks.Use, Marks.LotSurveyed, Marks.StreetEdge })
            h.ProjectMarks.Remove(m.Guid);
        if (set.Contains(Marks.Zone)) h.ProjectMarks[Marks.Zone.Guid] = new(true, Text: "R-1b");
        if (set.Contains(Marks.Use)) h.ProjectMarks[Marks.Use.Guid] = new(true, Text: "one_family_detached");
        if (set.Contains(Marks.LotSurveyed)) h.ProjectMarks[Marks.LotSurveyed.Guid] = new(true, 1);
        return ProjectFacts.Read(h.Model());
    }

    /// <summary>Revit trial (2026-11-20): from a sheet view with no fact set, the pick waited with no prompt where no
    /// property line could be clicked. Asked only when it is the one fact left, in a view showing a property line.</summary>
    [Fact]
    public void The_street_edge_is_asked_for_only_last_and_only_in_a_view_showing_the_property_line()
    {
        var none = Facts();
        Assert.Equal(StreetAsk.OtherFactsFirst, StreetEdges.Ask(none, needed: true, viewShowsPropertyLine: true, active: true));
        Assert.Equal(StreetAsk.OtherFactsFirst, StreetEdges.Ask(none, needed: true, viewShowsPropertyLine: false, active: true));
        var rest = Facts(Marks.Zone, Marks.Use, Marks.LotSurveyed);
        Assert.Equal([ProjectFacts.StreetNotSet], rest.Missing);
        Assert.Equal(StreetAsk.Pick, StreetEdges.Ask(rest, needed: true, viewShowsPropertyLine: true, active: true));
        Assert.Equal(StreetAsk.OpenAPlan, StreetEdges.Ask(rest, needed: true, viewShowsPropertyLine: false, active: true));
        Assert.Equal(StreetAsk.NotNeeded, StreetEdges.Ask(rest, needed: false, viewShowsPropertyLine: false, active: true));

        // in a view that can't show it, the panel says to open a site plan, never "when Check project asks"
        Assert.Equal([StreetEdges.OpenAPlan], StreetEdges.MissingAsShown(rest.Missing, StreetAsk.OpenAPlan));
        Assert.Equal(none.Missing, StreetEdges.MissingAsShown(none.Missing, StreetAsk.OtherFactsFirst));
        var refused = new[] { "Gordium: Street edge: the street edge picked is no longer an edge of the lot ..." };
        Assert.Equal([refused[0], StreetEdges.OpenAPlan], StreetEdges.MissingAsShown(refused, StreetAsk.OpenAPlan));
        Assert.Equal("Click the lot edge along the street (Esc to skip)", StreetEdges.PickPrompt);
    }

    /// <summary>The street edge's words for where its pick was asked (2026-11-23): from Check project the next step
    /// is Check again, from the Setup form's Pick on plan that button again; the pick's own dialogs are titled for the
    /// street edge, never "check my project" (wired in the add-in: the source says which it shows).</summary>
    [Fact]
    public void The_street_edge_says_its_next_step_for_where_the_pick_was_asked()
    {
        Assert.EndsWith("then click Check again: it asks you to click the lot edge along the street.", StreetEdges.OpenAPlan, StringComparison.Ordinal);
        Assert.EndsWith("then press Pick on plan again.", StreetEdges.OpenAPlanFromSetup, StringComparison.Ordinal);
        Assert.DoesNotContain("Check again", StreetEdges.OpenAPlanFromSetup, StringComparison.Ordinal);
        Assert.Equal("Gordium: street edge", StreetEdges.PickTitle);
        var addin = Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin");
        var setup = File.ReadAllText(Path.Combine(addin, "SetupFlow.cs"));
        // round 7: every message the Setup form's Pick on plan path shows names Pick on plan, never Check again, and
        // the path shows only those (and the picked edge's own words)
        Assert.All(StreetEdges.FromSetup, m => Assert.Contains("Pick on plan again", m, StringComparison.Ordinal));
        Assert.All(StreetEdges.FromSetup, m => Assert.DoesNotContain("Check", m, StringComparison.Ordinal));
        var path = setup[setup.IndexOf("private static void PickStreet()", StringComparison.Ordinal)..];
        path = path[..path.IndexOf("Save writes it with the other facts.", StringComparison.Ordinal)];
        foreach (var name in new[] { "OpenAPlanFromSetup", "SwitchToItFromSetup", "NoPropertyLineFromSetup", "NonePickedFromSetup" })
            Assert.Contains("StreetEdges." + name, path, StringComparison.Ordinal);
        Assert.DoesNotContain("StreetEdges.OpenAPlan)", path, StringComparison.Ordinal);
        Assert.DoesNotContain("StreetEdges.SwitchToIt)", path, StringComparison.Ordinal);
        Assert.DoesNotContain("Check again", path, StringComparison.Ordinal);
        var check = File.ReadAllText(Path.Combine(addin, "CheckProject.cs"));
        var pick = check[check.IndexOf("static List<PickedEdge> PickEdges(", StringComparison.Ordinal)..];
        pick = pick[..pick.IndexOf("return [.. session.Kept];", StringComparison.Ordinal)];
        Assert.Contains("new TaskDialog(StreetEdges.PickTitle)", pick, StringComparison.Ordinal);
        Assert.Contains("TaskDialog.Show(StreetEdges.PickTitle, why)", pick, StringComparison.Ordinal);
        Assert.DoesNotContain("(Title", pick, StringComparison.Ordinal);
    }
}
