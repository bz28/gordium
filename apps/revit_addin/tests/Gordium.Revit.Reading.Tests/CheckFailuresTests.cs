using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The check's waiting and failure states (UI polish changes 12 to 16, 39), Revit-free: progress as three
/// steps; one message per failure, each saying nothing was checked and never showing the technical words; the time-out
/// on silence with "Try again with more time" doubling it; the read failure in the pane, never a dialog; the slim stale
/// banner with its counts in the past tense.</summary>
public sealed class CheckFailuresTests
{
    private const string Details = "WorkerTimeoutException: The Gordium checker said nothing for 60 s (logged to C:\\x\\results.jsonl)";

    [Fact]
    public void Each_failure_has_its_own_message_and_none_shows_the_technical_words()
    {
        var all = new (Exception E, FailureKind Kind, FailureAction Action)[]
        {
            (new WorkerTimeoutException("t") { Limit = TimeSpan.FromSeconds(60), Silent = true }, FailureKind.TookTooLong, FailureAction.TryAgainWithMoreTime),
            (new WorkerExitedException("e", 1, ""), FailureKind.CheckerStopped, FailureAction.TryAgain),
            (new WorkerStoppedException("s"), FailureKind.CheckerStopped, FailureAction.TryAgain),
            (new WorkerProtocolException("p"), FailureKind.Unreadable, FailureAction.TryAgain),
            (new WorkerRefusedException("check_site", "facts: zone is missing", null), FailureKind.Refused, FailureAction.TryAgain),
            (new WorkerRefusedException("check_site", "KeyError: 'x'", "Traceback (most recent call last): ..."), FailureKind.CheckerStopped, FailureAction.TryAgain),
            (new InvalidOperationException("boom"), FailureKind.Other, FailureAction.TryAgain),
        };
        var titles = new HashSet<string>();
        foreach (var (e, kind, action) in all)
        {
            var f = CheckFailures.Of(e, Details);
            Assert.Equal(kind, f.Kind);
            Assert.Equal(action, f.Action);
            Assert.Equal(Details, f.Details);                                           // only behind Copy details
            foreach (var shown in new[] { f.Title, f.Words, f.Next ?? "" })
            {
                Assert.DoesNotContain("Exception", shown, StringComparison.Ordinal);    // change 14: no raw text
                Assert.DoesNotContain("results.jsonl", shown, StringComparison.Ordinal);
                Assert.DoesNotContain("Traceback", shown, StringComparison.Ordinal);
            }
            Assert.Contains("check", f.Words, StringComparison.OrdinalIgnoreCase);      // every one says nothing was checked
            Assert.Matches("[Nn]othing", f.Words);
            titles.Add(f.Title);
        }
        Assert.Equal(6, titles.Count);                                                  // one per cause (the two crashes differ)
        var timeout = CheckFailures.Of(all[0].E, Details);
        Assert.Equal("The check took too long", timeout.Title);
        Assert.StartsWith("Gordium stopped waiting after 60 seconds without a word from the checker.", timeout.Words, StringComparison.Ordinal);
        Assert.Equal("Try again with more time", timeout.ActionWords);
        Assert.Equal("The checker couldn't use what was sent", CheckFailures.Of(all[4].E, Details).Title);
        Assert.StartsWith("Facts: zone is missing.", CheckFailures.Of(all[4].E, Details).Words, StringComparison.Ordinal);
    }

    [Fact]
    public void The_read_failure_the_closed_project_and_a_busy_revit_say_what_to_do()
    {
        var read = CheckFailures.ReadFailed(Details);
        Assert.Equal("Gordium couldn't read the model", read.Title);
        Assert.Contains("nothing was checked", read.Words, StringComparison.Ordinal);
        Assert.Equal(FailureAction.TryAgain, read.Action);
        var closed = CheckFailures.Closed();
        Assert.Equal("The project was closed", closed.Title);
        Assert.Equal(FailureAction.None, closed.Action);                                // nothing to try until it's open
        Assert.Null(closed.ActionWords);
        Assert.Equal("Revit was busy and didn't start the check", CheckFailures.NotStarted(Details).Title);
        // change 16: the read failure is in the pane, never a dialog that blocks Revit
        var check = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "CheckProject.cs"));
        Assert.Contains("ResultsPane.Failed(CheckFailures.ReadFailed(", check, StringComparison.Ordinal);
        Assert.DoesNotContain("TaskDialog.Show(Title, clear + $\"Nothing was checked", check, StringComparison.Ordinal);
    }

    [Fact]
    public void More_time_doubles_the_silence_up_to_a_ceiling()
    {
        Assert.Equal(TimeSpan.FromSeconds(60), CheckFailures.FirstSilence);
        Assert.Equal(TimeSpan.FromSeconds(120), CheckFailures.More(CheckFailures.FirstSilence));
        Assert.Equal(TimeSpan.FromMinutes(16), CheckFailures.More(TimeSpan.FromMinutes(12)));
        // review round 1: a ceiling on the whole check, whatever the checker says meanwhile
        Assert.Equal(TimeSpan.FromMinutes(10), CheckFailures.Ceiling(TimeSpan.FromSeconds(60)));
        Assert.Equal(TimeSpan.FromMinutes(20), CheckFailures.Ceiling(TimeSpan.FromSeconds(120)));
        var check = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Reading", "ProjectCheck.cs"));
        Assert.Contains("total: silence is { } s ? CheckFailures.Ceiling(s) : null", check, StringComparison.Ordinal);
        Assert.StartsWith("Gordium stopped waiting after 2 minutes",
                          CheckFailures.Of(new WorkerTimeoutException("t") { Limit = TimeSpan.FromSeconds(120) }, "").Words, StringComparison.Ordinal);
        // the add-in sends the check with the silence and doubles it on "Try again with more time"
        var run = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "CheckRun.cs"));
        Assert.Contains("Silence, new Said(", run, StringComparison.Ordinal);
        Assert.Contains("internal static void MoreTime() => Silence = CheckFailures.More(Silence);", run, StringComparison.Ordinal);
    }

    [Fact]
    public void Progress_is_three_steps_with_the_reads_seconds_and_a_note_after_forty_seconds()
    {
        var reading = CheckSteps.Of(CheckStage.Reading, null, TimeSpan.Zero);
        Assert.Equal([CheckSteps.Read, CheckSteps.Check, CheckSteps.Show], reading.Select(s => s.Words));
        Assert.Equal([StepState.Running, StepState.Waiting, StepState.Waiting], reading.Select(s => s.State));
        var checking = CheckSteps.Of(CheckStage.Checking, TimeSpan.FromSeconds(2.4), TimeSpan.FromSeconds(34.9));
        Assert.Equal([StepState.Done, StepState.Running, StepState.Waiting], checking.Select(s => s.State));
        Assert.Equal(["2 s", "34 s", null], checking.Select(s => s.Time));
        Assert.Equal(CheckSteps.ReadingNote, CheckSteps.Note(CheckStage.Reading, TimeSpan.Zero));
        Assert.Equal(CheckSteps.KeepWorking, CheckSteps.Note(CheckStage.Checking, TimeSpan.FromSeconds(39)));
        Assert.EndsWith(CheckSteps.Long, CheckSteps.Note(CheckStage.Checking, TimeSpan.FromSeconds(40)), StringComparison.Ordinal);
    }

    [Fact]
    public void Stale_counts_are_in_the_past_tense()
    {
        Assert.Equal("1 failed · 132 needed review · 1 complied",
                     ResultViews.SummaryPast([Verdict.DoesNotComply, .. Enumerable.Repeat(Verdict.NeedsReview, 132), Verdict.Complies]));
        Assert.Equal("1 wasn't checked yet · 2 didn't apply",
                     ResultViews.SummaryPast([Verdict.NotChecked, Verdict.NotApplicable, Verdict.NotApplicable]));
        Assert.Equal("Does not comply (at 14:32)", PaneWords.StaleState("Does not comply", new DateTime(2026, 11, 22, 14, 32, 0)));
    }
}
