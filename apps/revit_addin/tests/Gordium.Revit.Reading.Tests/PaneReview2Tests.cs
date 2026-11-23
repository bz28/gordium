using System.Text;
using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Review round 2 of the intuitive pane (2026-11-23), each fix pinned by a test that fails when it is taken out:
/// every stale wording comes from one PaneWords helper keyed on why (a cancelled check's results never say "before the
/// model changed", in the banner, the state line, a copied row or a result's detail), and the Setup footer and the Save
/// button count the same thing (what Save writes).</summary>
public sealed class PaneReview2Tests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static readonly string Src = Path.Combine(Env.Repo, "apps", "revit_addin", "src");

    private static ResultModel House() =>
        ResultRows.Build(CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(File.ReadAllText(
            Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "ithaca_106_house_check_answer.json"),
            Encoding.UTF8)).RootElement.GetProperty("result").Clone(), About)), null, [], null);

    /// <summary>The stale wordings live in PaneWords only: a scan of every source file of the add-in and the reader
    /// finds "before the model changed" and "before the check you cancelled" nowhere else.</summary>
    [Fact]
    public void Every_stale_wording_comes_from_PaneWords()
    {
        foreach (var file in Directory.EnumerateFiles(Src, "*.cs", SearchOption.AllDirectories)
                                      .Where(f => !f.Contains($"{Path.DirectorySeparatorChar}obj{Path.DirectorySeparatorChar}", StringComparison.Ordinal)
                                               && !f.Contains($"{Path.DirectorySeparatorChar}bin{Path.DirectorySeparatorChar}", StringComparison.Ordinal)))
        {
            if (Path.GetFileName(file) == "PaneWords.cs")
                continue;
            var text = File.ReadAllText(file);
            Assert.DoesNotContain("before the model changed", text, StringComparison.Ordinal);
            Assert.DoesNotContain("before the check you cancelled", text, StringComparison.Ordinal);
        }
    }

    /// <summary>A cancelled check's earlier results say so everywhere: the state line, a copied row, a result's
    /// detail and its Check again step; a model that changed says that, from the same helper.</summary>
    [Fact]
    public void A_cancelled_checks_lines_say_before_the_check_you_cancelled()
    {
        var at = new DateTime(2026, 11, 22, 14, 32, 0);
        var cancelled = ResultRows.Stale(House(), at, CheckWords.CancelledStale(at), StaleReason.Cancelled);
        var reason = cancelled.StaleKind!.Value;
        Assert.Equal("Does not comply (before the check you cancelled)", PaneWords.StaleState("Does not comply", reason));
        var row = ResultList.Place(cancelled).First();
        Assert.EndsWith("(checked 14:32, before the check you cancelled)", ResultList.CopyText(row.Row, null, at, reason), StringComparison.Ordinal);
        var detail = Details.Of(row, 0, 1, null, at, null, reason);
        Assert.StartsWith("These results are from 14:32, before the check you cancelled", detail.Stale, StringComparison.Ordinal);
        Assert.Contains("before the check you cancelled", CheckWords.CancelledStale(at), StringComparison.Ordinal);
        // the model changed: its own words
        Assert.Equal("Does not comply (before the model changed)", PaneWords.StaleState("Does not comply", StaleReason.ModelChanged));
        Assert.EndsWith("(checked 14:32, before the model changed)", ResultList.CopyText(row.Row, null, at), StringComparison.Ordinal);
        // the pane passes the model's reason to each
        var view = File.ReadAllText(Path.Combine(Src, "Gordium.Revit.Addin", "ResultsView.cs")).Replace("\r\n", "\n", StringComparison.Ordinal);
        Assert.Contains("PaneWords.StaleState(ResultText.StateWords(model.State), model.StaleKind ?? StaleReason.ModelChanged)", view, StringComparison.Ordinal);
        Assert.Contains("_content?.Model?.StaleKind ?? StaleReason.ModelChanged);", view, StringComparison.Ordinal);
        Assert.Contains("_content?.Ids, _content?.Model?.StaleKind ?? StaleReason.ModelChanged);", view, StringComparison.Ordinal);
    }

    /// <summary>The footer and Save count the same thing, what Save writes: a ready form with Stories changed says
    /// "1 chosen, not saved yet" beside "Save 1 fact"; a waiting form with only a field that isn't needed changed
    /// never says "none chosen" beside "Save 1 fact".</summary>
    [Fact]
    public void The_footer_and_Save_count_the_same()
    {
        var stories = new SetupField(Marks.Stories, "Stories", FieldKind.Number, SetupFacts.OtherGroup, false, [], "2", "law", null);
        var draft = new SetupDraft();
        draft.Choose(Marks.Stories, "3");
        var ready = new SetupScreen("house", [stories], [], [], []);
        Assert.Equal(1, PaneWords.Unsaved(ready, draft));
        Assert.Equal("Every fact the check needs is set; 1 chosen, not saved yet.", PaneWords.SetupFooter(ready, draft));
        Assert.Equal("Save 1 fact", PaneWords.SaveAndCheck(PaneWords.Unsaved(ready, draft), PaneWords.ChecksAfterSave(ready, draft)));
        var zone = new SetupField(Marks.Zone, "Zone", FieldKind.Choice, SetupFacts.NeededGroup, true, [], null, "law", null);
        var waiting = new SetupScreen("house", [zone, stories], [], [], [Marks.Zone.Name]);
        var footer = PaneWords.SetupFooter(waiting, draft);
        Assert.DoesNotContain("none chosen", footer, StringComparison.Ordinal);
        Assert.Equal("1 fact needed; 1 chosen, not saved yet.", footer);
        Assert.Equal("Save 1 fact", PaneWords.SaveAndCheck(PaneWords.Unsaved(waiting, draft), PaneWords.ChecksAfterSave(waiting, draft)));
        Assert.Contains("private int Changes() => PaneWords.Unsaved(_screen, _draft);",
                        File.ReadAllText(Path.Combine(Src, "Gordium.Revit.Addin", "SetupView.cs")), StringComparison.Ordinal);
    }
}
