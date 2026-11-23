using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The Setup form's notice ("Nothing was checked: the zone chooses the rules…") lives only as long as the facts
/// it names are the ones needed (found in Revit 2027, 2026-11-23: after the zone was saved, the notice still said the
/// zone was missing). Each test fails when the rule is taken out.</summary>
public sealed class SetupNoticeTests
{
    private const string NoZone = "Nothing was checked: the zone chooses the rules, so nothing can be checked without it. Choose it above.";

    private static RevitModel Model(Dictionary<Guid, MarkValue>? project = null) =>
        new() { Document = "x", Marked = [], ProjectMarks = project ?? new Dictionary<Guid, MarkValue>() };

    private static SetupScreen Screen(RevitModel model, SetupDraft? draft = null) => SetupScreen.Build(model, [], null, draft ?? new SetupDraft());

    /// <summary>The zone case, end to end: the notice shown with the zone missing; it stays while the zone is only
    /// chosen (nothing the check reads has changed); once the zone is saved, it is gone.</summary>
    [Fact]
    public void The_zone_notice_goes_once_the_zone_is_saved()
    {
        var shown = Screen(Model());
        Assert.Contains(Marks.Zone.Name, shown.Needed);
        var madeFor = shown.Needed;
        Assert.Equal(NoZone, SetupNotice.Keep(NoZone, madeFor, shown));
        // chosen, not saved: the model's facts are the same, the notice still holds
        var draft = new SetupDraft();
        draft.Choose(Marks.Zone, "R-1b");
        var chosen = Screen(Model(), draft);
        Assert.Equal(shown.Needed.ToHashSet(), chosen.Needed.ToHashSet());
        Assert.Equal(NoZone, SetupNotice.Keep(NoZone, madeFor, chosen));
        // saved: the zone is on Project Information, no longer needed, and the notice goes
        var saved = Screen(Model(new Dictionary<Guid, MarkValue> { [Marks.Zone.Guid] = new(true, Text: "R-1b") }));
        Assert.DoesNotContain(Marks.Zone.Name, saved.Needed);
        Assert.Null(SetupNotice.Keep(NoZone, madeFor, saved));
    }

    /// <summary>The rule itself: kept while the facts needed are the same ones (in any order), gone when any changed;
    /// no notice, none.</summary>
    [Fact]
    public void A_notice_holds_only_for_the_facts_it_was_made_for()
    {
        var a = new SetupScreen("house", [], [], [], ["Gordium: Zone", "Gordium: Use"]);
        Assert.Equal("n", SetupNotice.Keep("n", ["Gordium: Use", "Gordium: Zone"], a));
        Assert.Null(SetupNotice.Keep("n", ["Gordium: Zone"], a));                         // one newly missing: new words needed
        Assert.Null(SetupNotice.Keep("n", ["Gordium: Zone", "Gordium: Use", "Gordium: Lot surveyed"], a));
        Assert.Null(SetupNotice.Keep(null, ["Gordium: Zone"], a));
        Assert.Null(SetupNotice.Keep("n", null, a));
    }

    /// <summary>The form keeps its notice only through SetupNotice: when it is drawn again after a choice, and when
    /// it is shown again after a Save, an accept, a pick or an edit (Refreshed); a new notice is made for the facts
    /// missing when it is shown.</summary>
    [Fact]
    public void The_form_keeps_its_notice_only_through_the_rule()
    {
        var flow = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupFlow.cs"))
                       .Replace("\r\n", "\n", StringComparison.Ordinal);
        Assert.Contains("_notice = SetupNotice.Keep(_notice, _noticeFor, _shown);", flow, StringComparison.Ordinal);
        Assert.Contains("_notice = SetupNotice.Keep(notice, _noticeFor, screen);", flow, StringComparison.Ordinal);
        Assert.Contains("ShowKept(ui, doc, screen, _notice);", flow, StringComparison.Ordinal);
        Assert.Contains("_noticeFor = screen.Needed;", flow, StringComparison.Ordinal);
        Assert.DoesNotContain("Show(ui, doc, screen, _notice);", flow, StringComparison.Ordinal);
        Assert.DoesNotContain("RedrawSetup(_shown = Screen(), Draft, Handlers, _notice, Open);", flow, StringComparison.Ordinal);
    }
}
