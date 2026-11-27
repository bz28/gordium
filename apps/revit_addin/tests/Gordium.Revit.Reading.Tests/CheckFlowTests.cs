using System.Diagnostics;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>PR 8, a check that doesn't freeze Revit: every decision of one check (CheckFlow: idle, reading, checking,
/// then done, cancelled or failed; an answer fresh only for the model it read; Cancel back to what was there; one
/// check at a time; a crash or timeout the error state), its words (CheckWords), the panel's button and line
/// (CheckAgainState), the time Revit's thread was blocked (UiThreadTime), and the add-in's wiring of each (source
/// text: it builds only with Revit). The send and wait run against the stand-in worker (a crash, a hang) and the
/// real one.</summary>
public sealed class CheckFlowTests(RealWorker real) : IClassFixture<RealWorker>
{
    private static readonly ProjectRequest Request = new(
        JsonNode.Parse("""{"schema": "gordium.site/1"}""")!.AsObject(), JsonNode.Parse("""{"zone": "R-1b"}""")!.AsObject(), new JsonObject());

    private static Task<CheckResult> Answer() => Task.FromResult<CheckResult>(null!);           // an answer came back
    private static Task<CheckResult> Crash() => Task.FromException<CheckResult>(new WorkerExitedException("check_site", 3, ""));

    // ---- the stages ----------------------------------------------------------------------------------------

    [Fact]
    public void A_check_goes_idle_reading_checking_done_and_its_answer_is_fresh()
    {
        var flow = new CheckFlow();
        Assert.Equal(CheckStage.Idle, flow.Stage);
        Assert.False(flow.Running);
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        Assert.Equal(CheckStage.Reading, flow.Stage);
        Assert.True(flow.Running);
        Assert.True(flow.IsCurrent(t));
        Assert.True(flow.ReadDone(t));
        Assert.Equal(CheckStage.Checking, flow.Stage);
        Assert.False(flow.Token(t).IsCancellationRequested);
        Assert.Equal(AnswerUse.ShowFresh, flow.Arrived(t, Answer()));
        Assert.Equal(CheckStage.Done, flow.Stage);
        Assert.False(flow.Running);
        Assert.False(flow.IsCurrent(t));
        Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, Answer()));             // answered once: never shown twice
    }

    [Fact]
    public void Nothing_sent_is_done_from_reading()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        Assert.True(flow.NothingSent(t));
        Assert.Equal(CheckStage.Done, flow.Stage);
        Assert.False(flow.NothingSent(t));
        Assert.False(flow.ReadDone(t));                                        // done: nothing is sent after it
    }

    // ---- staleness: an answer is fresh only for the model it read -------------------------------------------

    /// <summary>An edit committed after the read and before the answer leaves the new answer stale.</summary>
    [Fact]
    public void An_edit_between_the_read_and_the_answer_makes_the_answer_stale()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Results)!.Value;
        flow.Edited();                                                         // during the read (its own drafts): read
        Assert.True(flow.ReadDone(t));
        flow.Edited();                                                         // the architect, while the checker works
        Assert.Equal(AnswerUse.ShowStale, flow.Arrived(t, Answer()));
        Assert.Equal(CheckStage.Done, flow.Stage);
    }

    [Fact]
    public void An_edit_before_the_read_ends_is_in_the_read_and_the_next_check_starts_fresh()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        flow.Edited();
        flow.Edited();
        Assert.True(flow.ReadDone(t));
        Assert.Equal(AnswerUse.ShowFresh, flow.Arrived(t, Answer()));
        flow.Edited();                                                         // after the answer: the panel's own stale
        var u = flow.TryStart(PanelHad.Results)!.Value;
        Assert.True(flow.ReadDone(u));                                         // read after that edit: it is in the read
        Assert.Equal(AnswerUse.ShowFresh, flow.Arrived(u, Answer()));
    }

    [Fact]
    public void Edits_from_many_threads_are_all_counted()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        Assert.True(flow.ReadDone(t));
        Parallel.For(0, 1000, _ => flow.Edited());
        Assert.Equal(AnswerUse.ShowStale, flow.Arrived(t, Answer()));
    }

    // ---- cancel ----------------------------------------------------------------------------------------------

    /// <summary>Cancel leaves the previous results stale, never shown as the new ones: the flow says the panel goes
    /// back to its earlier results, the wait's token is cancelled (the worker stopped), and the cancelled check's
    /// answer, or its stopped worker's error, is ignored.</summary>
    [Fact]
    public void Cancel_goes_back_to_the_earlier_results_and_its_answer_is_never_shown()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Results)!.Value;
        Assert.True(flow.ReadDone(t));
        var token = flow.Token(t);
        Assert.Equal(PanelHad.Results, flow.Cancel());
        Assert.True(token.IsCancellationRequested);
        Assert.Equal(CheckStage.Cancelled, flow.Stage);
        Assert.False(flow.Running);
        Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, Answer()));             // the worker answered just before: dropped
        Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, Crash()));              // its stopped worker: not an error to show
        Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, Task.FromCanceled<CheckResult>(token)));
        Assert.Equal(CheckStage.Cancelled, flow.Stage);
        Assert.Null(flow.Cancel());                                            // nothing running
    }

    [Theory]
    [InlineData(PanelHad.Nothing)]
    [InlineData(PanelHad.Missing)]
    [InlineData(PanelHad.Error)]
    [InlineData(PanelHad.Results)]
    public void Cancel_goes_back_to_what_the_panel_had_while_reading_or_checking(PanelHad had)
    {
        var flow = new CheckFlow();
        flow.TryStart(had);
        Assert.Equal(had, flow.Cancel());                                      // reading (before the read, or in a pick)
        var t = flow.TryStart(had)!.Value;
        Assert.True(flow.ReadDone(t));
        Assert.Equal(had, flow.Cancel());                                      // checking
    }

    [Fact]
    public void A_check_cancelled_while_reading_sends_nothing()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        flow.Cancel();
        Assert.False(flow.IsCurrent(t));                                       // the read action: not begun
        Assert.False(flow.ReadDone(t));                                        // the request: never sent
        Assert.True(flow.Token(t).IsCancellationRequested);
        Assert.False(flow.NothingSent(t));                                     // nor its "fill these in" shown
        Assert.False(flow.Fail(t));                                            // nor its read's error
    }

    [Theory]
    [InlineData(false, false, false, PanelHad.Nothing)]
    [InlineData(false, false, true, PanelHad.Error)]
    [InlineData(true, false, false, PanelHad.Missing)]
    [InlineData(true, true, false, PanelHad.Results)]
    public void What_the_panel_had(bool shown, bool rows, bool failed, PanelHad had) =>
        Assert.Equal(had, CheckFlow.Had(shown, rows, failed));

    // ---- one check at a time ---------------------------------------------------------------------------------

    /// <summary>A second Check while one runs is refused (the panel's button is Cancel meanwhile): the running check
    /// goes on untouched; once it ends, a new one starts, and an earlier check's late answer is never the new one's.</summary>
    [Fact]
    public void A_second_check_while_one_runs_is_refused_and_a_late_answer_is_never_the_new_checks()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        Assert.Null(flow.TryStart(PanelHad.Results));                          // reading
        Assert.True(flow.ReadDone(t));
        Assert.Null(flow.TryStart(PanelHad.Results));                          // checking
        Assert.True(flow.IsCurrent(t));
        Assert.False(flow.Token(t).IsCancellationRequested);
        flow.Cancel();
        var u = flow.TryStart(PanelHad.Results)!.Value;                        // after Cancel: a new check
        Assert.NotEqual(t, u);
        Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, Answer()));             // the first's answer, late
        Assert.Equal(CheckStage.Reading, flow.Stage);                          // the new one untouched
        Assert.False(flow.ReadDone(t));
        Assert.True(flow.ReadDone(u));
        Assert.False(flow.Fail(t));
        Assert.Equal(AnswerUse.ShowFresh, flow.Arrived(u, Answer()));
    }

    // ---- failures: the error state, never a partial pass ---------------------------------------------------------

    [Fact]
    public void A_crash_or_a_timeout_is_the_error_state_and_never_an_answer()
    {
        foreach (var outcome in new[]
                 {
                     Crash(), Task.FromException<CheckResult>(new WorkerTimeoutException("check_site took longer than 60 s")),
                     Task.FromException<CheckResult>(new WorkerProtocolException("check_site's answer had no state")),
                 })
        {
            var flow = new CheckFlow();
            var t = flow.TryStart(PanelHad.Results)!.Value;
            Assert.True(flow.ReadDone(t));
            Assert.Equal(AnswerUse.ShowError, flow.Arrived(t, outcome));
            Assert.Equal(CheckStage.Failed, flow.Stage);
            Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, Answer()));         // nothing of it shown afterwards
            Assert.Null(flow.Cancel());
        }
    }

    [Fact]
    public void A_read_that_throws_is_the_error_state()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Results)!.Value;
        Assert.True(flow.Fail(t));
        Assert.Equal(CheckStage.Failed, flow.Stage);
        Assert.False(flow.ReadDone(t));
        Assert.NotNull(flow.TryStart(PanelHad.Error));                         // Check again works after it
    }

    // ---- the send and wait, off the caller's thread ------------------------------------------------------------

    private static string FakeWorker =>
        Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Worker.Tests", "fake_worker.py");

    private static Task<WorkerClient> Fake(string mode, TimeSpan? timeout = null, string? record = null) =>
        WorkerClient.StartAsync(new WorkerOptions
    {
        PythonPath = Env.Python, WorkingDirectory = Env.Repo,
        Arguments = record is null ? [FakeWorker, mode] : [FakeWorker, mode, record],   // record: each line it read
        StartTimeout = TimeSpan.FromSeconds(30), RequestTimeout = timeout ?? TimeSpan.FromSeconds(30),
        Environment = new Dictionary<string, string> { ["GORDIUM_FAKE_PROTOCOL"] = "1.2" },   // a check with an interior
    });

    private static (Task Sent, TaskCompletionSource<(Task<CheckResult> Outcome, double Seconds)> Arrived) Send(
        CheckFlow flow, long ticket, Task<WorkerClient> worker)
    {
        var arrived = new TaskCompletionSource<(Task<CheckResult>, double)>(TaskCreationOptions.RunContinuationsAsynchronously);
        var sent = flow.Send(ticket, worker, Request, (outcome, seconds) => arrived.SetResult((outcome, seconds)));
        return (sent, arrived);
    }

    /// <summary>The caller (Revit's thread) never waits: Send returns while the worker hangs, and Cancel stops the
    /// worker and the check's outcome is ignored. Shown by what happened, not by a clock: Send returned to the test
    /// with no answer come (the stand-in worker never answers, so a Send that waited for it would never return),
    /// and the cancel comes only once the worker holds the request (its record file has the check's line). A cancel before that sends nothing and
    /// keeps the worker (the next test), so cancelling after a fixed 300 ms raced a slow machine (CI, PR #177:
    /// the request hadn't reached the worker yet, so it was rightly not stopped).</summary>
    [Fact]
    public async Task Send_returns_at_once_and_cancel_stops_the_hung_worker_and_is_ignored()
    {
        var record = Path.Combine(Path.GetTempPath(), $"gordium_send_{Guid.NewGuid():N}.jsonl");
        try
        {
            using var worker = await Fake("hang", record: record);
            var flow = new CheckFlow();
            var t = flow.TryStart(PanelHad.Results)!.Value;
            Assert.True(flow.ReadDone(t));
            var (sent, arrived) = Send(flow, t, Task.FromResult(worker));
            Assert.False(arrived.Task.IsCompleted);                            // Send returned with no answer yet
            await Received(record, "check_site");                              // the worker holds the request...
            Assert.False(arrived.Task.IsCompleted);                            // ...and hangs on it: no answer
            Assert.False(sent.IsCompleted);
            Assert.Equal(PanelHad.Results, flow.Cancel());
            var (outcome, _) = await arrived.Task.WaitAsync(TimeSpan.FromSeconds(20));
            await sent.WaitAsync(TimeSpan.FromSeconds(20));
            Assert.NotEqual(TaskStatus.RanToCompletion, outcome.Status);
            Assert.True(worker.IsStopped);                                     // the request killed, not left running
            Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, outcome));
        }
        finally
        {
            try
            {
                File.Delete(record);
            }
            catch (IOException)
            {
                // the stopped worker's handle not let go yet: a temp file, left for the system to clear
            }
        }
    }

    /// <summary>Waits until the stand-in worker has read a request naming <paramref name="command"/> (its record
    /// file holds each line it reads, written as it reads it). The bound is only so a broken worker fails the test
    /// instead of hanging it: 60 s, far past any slow machine's start of a Python process and one pipe write.</summary>
    private static async Task Received(string record, string command)
    {
        var clock = Stopwatch.StartNew();
        while (!Holds(record, $"\"cmd\": \"{command}\"") && !Holds(record, $"\"cmd\":\"{command}\""))
        {
            Assert.True(clock.Elapsed < TimeSpan.FromSeconds(60), $"the worker never read a {command} request");
            await Task.Delay(20);
        }
    }

    private static bool Holds(string path, string text)
    {
        try
        {
            using var read = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            return new StreamReader(read).ReadToEnd().Contains(text, StringComparison.Ordinal);
        }
        catch (IOException)
        {
            return false;                                                      // not made yet, or being written
        }
    }

    [Fact]
    public async Task A_worker_that_dies_before_answering_is_the_error_state()
    {
        using var worker = await Fake("die");
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Results)!.Value;
        Assert.True(flow.ReadDone(t));
        var (_, arrived) = Send(flow, t, Task.FromResult(worker));
        var (outcome, _) = await arrived.Task.WaitAsync(TimeSpan.FromSeconds(30));
        Assert.True(outcome.Exception!.GetBaseException() is WorkerExitedException, outcome.Exception!.GetBaseException().ToString());
        Assert.Equal(AnswerUse.ShowError, flow.Arrived(t, outcome));
    }

    [Fact]
    public async Task A_worker_that_hangs_past_its_limit_is_the_error_state()
    {
        using var worker = await Fake("hang", TimeSpan.FromSeconds(2));
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        Assert.True(flow.ReadDone(t));
        var (_, arrived) = Send(flow, t, Task.FromResult(worker));
        var (outcome, seconds) = await arrived.Task.WaitAsync(TimeSpan.FromSeconds(30));
        Assert.True(outcome.Exception!.GetBaseException() is WorkerTimeoutException, outcome.Exception!.GetBaseException().ToString());
        Assert.True(seconds >= 1.5, $"waited {seconds} s");
        Assert.Equal(AnswerUse.ShowError, flow.Arrived(t, outcome));
    }

    [Fact]
    public async Task A_worker_that_fails_to_start_is_the_error_state()
    {
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Nothing)!.Value;
        Assert.True(flow.ReadDone(t));
        var (_, arrived) = Send(flow, t, Task.FromException<WorkerClient>(new InvalidOperationException("no clone")));
        var (outcome, _) = await arrived.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(AnswerUse.ShowError, flow.Arrived(t, outcome));
    }

    /// <summary>The real worker: the box house checked off the caller's thread is shown fresh; the same answer with an
    /// edit committed after the read and before it is handled is shown stale.</summary>
    [Fact]
    public async Task The_real_workers_answer_is_fresh_and_stale_after_an_edit_made_while_it_worked()
    {
        var client = await real.RunningAsync();
        var house = FakeHouse.Draw("1_ranch_compliant");
        var scene = SceneDrawing.Named("01_box_house");
        var outside = scene.Model(scene.Steps[0]) with { Phases = house.Model().Phases };
        foreach (var (m, v) in new (MarkDefinition, MarkValue)[]
                 {
                     (Marks.Zone, new(true, Text: "R-1b")), (Marks.Use, new(true, Text: "one_family_detached")),
                     (Marks.LotSurveyed, new(true, 1)), (Marks.CornerLot, new(true, 0)),
                 })
            house.ProjectMarks[m.Guid] = v;
        var c = outside.LotLines[0].Curves.Single(c => Math.Abs(c.Start.Y - c.End.Y) < 1e-9 && Math.Min(c.Start.Y, c.End.Y) < 1);
        house.ProjectMarks[Marks.StreetEdge.Guid] = new(true, Text: StreetEdges.Format([(c.Start, c.End)]));
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client));
        Assert.NotNull(prepared.Request);

        foreach (var edit in new[] { false, true })
        {
            var flow = new CheckFlow();
            var t = flow.TryStart(PanelHad.Nothing)!.Value;
            Assert.True(flow.ReadDone(t));
            var arrived = new TaskCompletionSource<Task<CheckResult>>(TaskCreationOptions.RunContinuationsAsynchronously);
            await flow.Send(t, Task.FromResult(client), prepared.Request!, (o, _) => arrived.SetResult(o)).WaitAsync(TimeSpan.FromSeconds(60));
            var outcome = await arrived.Task;
            Assert.Equal(TaskStatus.RanToCompletion, outcome.Status);
            if (edit)
                flow.Edited();                                                 // committed before Revit's thread shows it
            Assert.Equal(edit ? AnswerUse.ShowStale : AnswerUse.ShowFresh, flow.Arrived(t, outcome));
        }
    }

    /// <summary>Review round 1 (P3): a Cancel clicked during the read is handled before the send (which waits behind
    /// Revit's queued input): with the check's token already cancelled, nothing reaches the worker and it keeps
    /// running (it isn't killed and restarted), and the outcome is ignored.</summary>
    [Fact]
    public async Task A_cancel_before_the_send_sends_nothing_and_keeps_the_worker()
    {
        using var worker = await Fake("hang");
        var flow = new CheckFlow();
        var t = flow.TryStart(PanelHad.Results)!.Value;
        Assert.True(flow.ReadDone(t));                                         // the read ended: its edits counted
        Assert.Equal(PanelHad.Results, flow.Cancel());                          // the click queued during the read
        Assert.False(flow.IsCurrent(t));                                       // CheckRun.Send: nothing sent
        var (_, arrived) = Send(flow, t, Task.FromResult(worker));             // even if it were sent: token cancelled
        var (outcome, _) = await arrived.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(TaskStatus.Canceled, outcome.Status);
        Assert.False(worker.IsStopped);                                        // never asked anything, never killed
        Assert.Equal(AnswerUse.Ignore, flow.Arrived(t, outcome));
    }

    /// <summary>Review round 1 (P3): Cancel's words are what was restored, never "the results below" with none
    /// below (the earlier project closed during the check, say).</summary>
    [Theory]
    [InlineData(PanelHad.Results, PanelHad.Results, PanelHad.Results)]
    [InlineData(PanelHad.Results, PanelHad.Nothing, PanelHad.Nothing)]
    [InlineData(PanelHad.Results, PanelHad.Error, PanelHad.Error)]
    [InlineData(PanelHad.Missing, PanelHad.Missing, PanelHad.Missing)]
    [InlineData(PanelHad.Missing, PanelHad.Error, PanelHad.Error)]
    [InlineData(PanelHad.Error, PanelHad.Nothing, PanelHad.Error)]
    [InlineData(PanelHad.Nothing, PanelHad.Nothing, PanelHad.Nothing)]
    public void Cancel_says_what_was_restored(PanelHad had, PanelHad now, PanelHad restored)
    {
        Assert.Equal(restored, CheckFlow.Restored(had, now));
        if (restored != PanelHad.Results)
            Assert.DoesNotContain("results below", CheckWords.Cancelled(restored), StringComparison.Ordinal);
    }

    /// <summary>Review round 1 (P2): the street edge is never picked in a project that isn't the one being checked
    /// (the architect switched projects after clicking Check): not asked, and the panel says to switch.</summary>
    [Fact]
    public void The_street_edge_is_never_picked_in_another_project()
    {
        var h = FakeHouse.Draw("5_basement_window_well");
        foreach (var m in new[] { Marks.StreetEdge })
            h.ProjectMarks.Remove(m.Guid);
        h.ProjectMarks[Marks.Zone.Guid] = new(true, Text: "R-1b");
        h.ProjectMarks[Marks.Use.Guid] = new(true, Text: "one_family_detached");
        h.ProjectMarks[Marks.LotSurveyed.Guid] = new(true, 1);
        var read = ProjectFacts.Read(h.Model());
        Assert.Equal([ProjectFacts.StreetNotSet], read.Missing);
        Assert.Equal(StreetAsk.Pick, StreetEdges.Ask(read, needed: true, viewShowsPropertyLine: true, active: true));
        foreach (var view in new[] { true, false })
            Assert.Equal(StreetAsk.NotActive, StreetEdges.Ask(read, needed: true, viewShowsPropertyLine: view, active: false));
        Assert.Equal([StreetEdges.SwitchToIt], StreetEdges.MissingAsShown(read.Missing, StreetAsk.NotActive));
        Assert.Contains("switch to it", StreetEdges.SwitchToIt, StringComparison.Ordinal);
        // the add-in: every pick behind the guard, the view read only in the active project
        var check = Addin("CheckProject.cs");
        var readAndSend = Between(check, "    internal static void ReadAndSend(", "\n    }\n");
        Assert.Contains("bool Active() => ui.ActiveUIDocument?.Document.Equals(doc) == true;", readAndSend, StringComparison.Ordinal);
        Assert.Contains("var view = Active() && ShowsPropertyLine(ui.ActiveUIDocument!);", readAndSend, StringComparison.Ordinal);
        // each pick behind the guard (UI polish PR 5: both written one way, so a pick that wrote is known: CheckRun.Wrote)
        Assert.Equal(2, readAndSend.Split("if (ask == StreetAsk.Pick && Active() && check.Clock.Architect(\"street_pick\", () => PickStreet(").Length - 1);
        Assert.Equal(2, readAndSend.Split("PickStreet(").Length - 1);
        Assert.Equal(2, readAndSend.Split(", Active());").Length - 1);            // both asks told whether it is active
    }

    /// <summary>Review round 1 (P3): every worker start and stop goes through Trial's lock; no other file sets the
    /// session's worker (a check's background start and the box house's own could make two, one left running).</summary>
    [Fact]
    public void Only_trial_sets_the_sessions_worker()
    {
        var dir = Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin");
        foreach (var file in Directory.GetFiles(dir, "*.cs"))
        {
            var text = File.ReadAllText(file);
            var name = Path.GetFileName(file);
            var sets = System.Text.RegularExpressions.Regex.Matches(text, @"App\.Worker\s*=(?!=)").Count;
            Assert.True(name == "Trial.cs" || sets == 0, $"{name} sets App.Worker");
            Assert.DoesNotContain("WorkerClient.StartAsync(", name == "Trial.cs" ? "" : text, StringComparison.Ordinal);
        }
        // each of Trial's two worker methods keeps its own doc comment (review round 2)
        var t = File.ReadAllText(Path.Combine(dir, "Trial.cs")).Replace("\r\n", "\n");
        var beforeStart = t[..t.IndexOf("    internal static Task<WorkerClient> WorkerAsync()", StringComparison.Ordinal)].TrimEnd();
        Assert.EndsWith("trial tool's never make two.</summary>", beforeStart);
        var beforeStop = t[..t.IndexOf("    internal static WorkerClient? StopWorker()", StringComparison.Ordinal)].TrimEnd();
        var lastLines = beforeStop[(beforeStop.LastIndexOf(";", StringComparison.Ordinal) + 1)..];
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(lastLines, "<summary>"));
        var app = File.ReadAllText(Path.Combine(dir, "App.cs"));
        Assert.DoesNotContain("Worker = null", app, StringComparison.Ordinal);
        Assert.Contains("var worker = Trial.StopWorker();", app, StringComparison.Ordinal);
        var trial = File.ReadAllText(Path.Combine(dir, "Trial.cs"));
        Assert.Equal(3, System.Text.RegularExpressions.Regex.Matches(trial, @"App\.Worker\s*=(?!=)").Count);
        Assert.Equal(3, System.Text.RegularExpressions.Regex.Matches(trial, @"lock \(WorkerLock\)").Count);
    }

    // ---- the words, the button, the stale notice ----------------------------------------------------------------

    [Fact]
    public void The_button_is_cancel_while_a_check_runs_and_the_line_says_the_stage()
    {
        Assert.Equal("Cancel", CheckWords.Button(CheckStage.Reading));
        Assert.Equal("Cancel", CheckWords.Button(CheckStage.Checking));
        foreach (var s in new[] { CheckStage.Idle, CheckStage.Done, CheckStage.Cancelled, CheckStage.Failed })
        {
            Assert.Equal("Check again", CheckWords.Button(s));
            Assert.Null(CheckWords.Progress(s, TimeSpan.Zero));
        }
        Assert.StartsWith("Reading the model...", CheckWords.Progress(CheckStage.Reading, TimeSpan.FromSeconds(5)));
        Assert.Contains("Revit waits", CheckWords.Reading, StringComparison.Ordinal);
        Assert.StartsWith("Checking (Gordium's checker, 12 s)...", CheckWords.Progress(CheckStage.Checking, TimeSpan.FromSeconds(12.7)));
        Assert.Contains("an edit now makes this answer stale", CheckWords.Checking(TimeSpan.Zero), StringComparison.Ordinal);
    }

    [Fact]
    public void The_cancel_and_stale_words_never_say_the_earlier_results_are_the_new_ones()
    {
        var at = new DateTime(2026, 11, 22, 14, 32, 0);
        Assert.Equal("These results are from 14:32, before the check you cancelled; the model may have changed since: click Check again",
                     CheckWords.CancelledStale(at));
        Assert.Contains("earlier check's", CheckWords.Cancelled(PanelHad.Results), StringComparison.Ordinal);
        Assert.Equal("Check cancelled: nothing was checked.", CheckWords.Cancelled(PanelHad.Nothing));
        Assert.Equal("Check cancelled: nothing was checked.", CheckWords.Cancelled(PanelHad.Error));
        Assert.Contains("read at 14:32", CheckWords.ChangedWhileChecking(at), StringComparison.Ordinal);
        Assert.Contains("nothing was checked", CheckWords.CheckerStopped("WorkerTimeoutException: x"), StringComparison.Ordinal);
    }

    /// <summary>The stale notice given (an answer whose model changed while it ran, or the earlier results after
    /// Cancel) greys every colour as the panel's own stale does: never a green complies.</summary>
    [Fact]
    public void A_stale_answer_or_cancelled_check_is_grey_throughout_with_its_own_words()
    {
        var row = new ResultRow("z.lot", "Lot area", Verdict.Complies, "complies", Tone.Complies, "6,000 sf", null, null, "325-8", [], []);
        var model = new ResultModel(Verdict.Complies, "Complies", "c", [new CountLine("Zoning", [new CountChip("1 complies", Tone.Complies)])],
                                    [new ResultGroup("complies", "Complies", 1, false, Tone.Complies, [row], [])], "");
        var at = new DateTime(2026, 11, 22, 14, 32, 0);
        foreach (var why in new[] { CheckWords.ChangedWhileChecking(at), CheckWords.CancelledStale(at) })
        {
            var stale = ResultRows.Stale(model, at, why);
            Assert.Equal(why, stale.Stale);
            Assert.Equal(Tone.Neutral, stale.StateTone);
            Assert.All(stale.Counts.SelectMany(c => c.Chips), c => Assert.Equal(Tone.Neutral, c.Tone));
            Assert.All(stale.Groups, g => Assert.Equal(Tone.Neutral, g.Tone));
            Assert.All(stale.Groups.SelectMany(g => g.AllRows), r => Assert.Equal(Tone.Neutral, r.Tone));
            Assert.Equal(PanelPart.Stale, ResultRows.Layout(stale)[0]);
        }
        Assert.Equal("The model changed since this check (14:32): click Check again", ResultRows.Stale(model, at).Stale);
    }

    /// <summary>A redraw while a check runs (an edit greys the earlier results) keeps Cancel usable and the stage's
    /// line shown; the line a redraw wanted is said once the check ends.</summary>
    [Fact]
    public void A_redraw_while_a_check_runs_keeps_cancel_and_the_progress_line()
    {
        var state = new CheckAgainState();
        state.Start();                                                         // the click, queued: greyed
        Assert.False(state.Enabled);
        state.Running(CheckWords.Reading);
        Assert.True(state.Enabled);                                            // Cancel
        Assert.True(state.IsRunning);
        Assert.Equal(CheckWords.Reading, state.Status("Added 3 Gordium marks to this project."));
        var checking = CheckWords.Checking(TimeSpan.FromSeconds(3));
        state.Running(checking);
        Assert.Equal(checking, state.Status(""));
        Assert.True(state.Enabled);
        Assert.Equal("Added 3 Gordium marks to this project.", state.Stop(checking));
        Assert.False(state.Busy);
        Assert.True(state.Enabled);
        Assert.Equal("x", state.Status("x"));
        state.Running(CheckWords.Reading);                                     // begun by the ribbon (no click held)
        Assert.Equal("Nothing was checked: IOException: x", state.Stop("Nothing was checked: IOException: x"));
    }

    // ---- where Revit's thread went -------------------------------------------------------------------------------

    [Fact]
    public void Blocked_time_is_revits_threads_own_never_the_architects_or_the_wait_off_it()
    {
        var clock = new UiThreadTime();
        clock.Blocked("start", 0.0042);
        clock.Blocked("read", 48.9);
        clock.Architect("street_pick", 6.5);
        clock.OffThread("check", 3.2);
        clock.Blocked("show", 0.21);
        Assert.Equal(49.114, clock.BlockedSeconds);
        Assert.Equal(6.5, clock.ArchitectSeconds);
        Assert.Throws<InvalidOperationException>(() => clock.Blocked<int>("read", () => throw new InvalidOperationException()));
        var log = clock.ToLog();
        Assert.Equal(["blocked_s", "blocked", "architect", "off_thread"], log.Keys);
        var blocked = Assert.IsType<Dictionary<string, object?>>(log["blocked"]);
        Assert.Equal(["read", "show", "start"], blocked.Keys);
        Assert.Equal(2, Assert.IsType<Dictionary<string, object?>>(blocked["read"])["calls"]);   // a throw still counted
        Assert.Equal(0.004, Assert.IsType<Dictionary<string, object?>>(blocked["start"])["seconds"]);
        Assert.Equal(3.2, Assert.IsType<Dictionary<string, object?>>(Assert.IsType<Dictionary<string, object?>>(log["off_thread"])["check"])["seconds"]);
        Assert.True((double)log["blocked_s"]! >= 49.114);
    }

    [Fact]
    public void A_timed_piece_adds_its_own_time()
    {
        var clock = new UiThreadTime();
        Assert.Equal(7, clock.Architect("street_pick", () =>
        {
            Thread.Sleep(30);
            return 7;
        }));
        Assert.True(clock.ArchitectSeconds >= 0.025, $"{clock.ArchitectSeconds}");
        Assert.Equal(0, clock.BlockedSeconds);
    }

    // ---- the add-in's wiring (source text: it builds only with Revit) ---------------------------------------------

    private static string Addin(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file)).Replace("\r\n", "\n", StringComparison.Ordinal);

    private static string Between(string text, string from, string to)
    {
        var i = text.IndexOf(from, StringComparison.Ordinal);
        Assert.True(i >= 0, from);
        var j = text.IndexOf(to, i + from.Length, StringComparison.Ordinal);
        return text[i..(j < 0 ? text.Length : j)];
    }

    [Fact]
    public void The_add_in_reads_on_revits_thread_after_the_line_is_drawn_and_waits_off_it()
    {
        var run = Addin("CheckRun.cs");
        var start = Between(run, "    internal static string? Start(", "\n    }\n");
        Assert.Contains("if (Flow.TryStart(ResultsPane.Had()) is not { } ticket)\n            return CheckWords.Refused;", start, StringComparison.Ordinal);
        Assert.Contains("check.Worker = StartWorker();", start, StringComparison.Ordinal);       // Python starts during the read
        Assert.Contains("ResultsPane.Reading(ui);", start, StringComparison.Ordinal);
        // the read queued after the panel has drawn "Reading the model...", through the ExternalEvent (Revit's thread)
        Assert.Contains("ResultsPane.AfterDrawn(() => ResultsPane.Post(\"Read the model\", app => CheckProjectCommand.ReadAndSend(app, doc, check),", start, StringComparison.Ordinal);
        Assert.Contains("System.Windows.Threading.DispatcherPriority.Background, act", Addin("ResultsPane.cs"), StringComparison.Ordinal);
        // the read's end keeps the edit count at once (ReadDone); the send, queued behind Revit's input, sends nothing
        // once cancelled; off Revit's thread, the answer back on it
        var ended = Between(run, "    internal bool ReadEnded()", "\n    }\n");
        Assert.Contains("if (!Flow.ReadDone(Ticket))", ended, StringComparison.Ordinal);
        var send = Between(run, "    internal void Send(ProjectRequest request)", "\n    }\n");
        var guard = send.IndexOf("if (!Flow.IsCurrent(Ticket))\n        {\n            Log[\"cancelled_before_send\"] = true;\n            End(\"cancelled\");", StringComparison.Ordinal);
        Assert.True(guard >= 0 && guard < send.IndexOf("Flow.Send(Ticket, Worker, request,", StringComparison.Ordinal), "a cancelled check is sent");
        Assert.Contains("ResultsPane.Post(\"Show the check's answer\", app =>", send, StringComparison.Ordinal);
        Assert.Contains("CheckProjectCommand.Answered(app, Doc, this, sent);", send, StringComparison.Ordinal);
        Assert.DoesNotContain("GetResult()", run, StringComparison.Ordinal);
        Assert.DoesNotContain(".Wait(", run, StringComparison.Ordinal);
        // the flow's send: the worker and the check_site under the check's token, on a pool thread
        var flow = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Reading", "CheckFlow.cs"));
        Assert.Contains("var client = await worker.WaitAsync(cancel).ConfigureAwait(false);", flow, StringComparison.Ordinal);
        Assert.Contains("return await ProjectCheck.SendAsync(client, request, cancel, silence, step).ConfigureAwait(false);", flow, StringComparison.Ordinal);
        // and the command no longer waits for the worker on Revit's thread
        var check = Addin("CheckProject.cs");
        var readAndSend = Between(check, "    internal static void ReadAndSend(", "\n    }\n");
        Assert.DoesNotContain("SendAsync", readAndSend, StringComparison.Ordinal);
        Assert.Contains("if (check.ReadEnded())\n                ResultsPane.AfterInput(() => check.Send(request));", readAndSend, StringComparison.Ordinal);
    }

    [Fact]
    public void The_add_in_shows_the_answer_as_the_flow_decides_on_revits_thread()
    {
        var check = Addin("CheckProject.cs");
        var answered = Between(check, "    internal static void Answered(", "\n    internal sealed record Ran(");
        Assert.Contains("var use = CheckRun.Flow.Arrived(check.Ticket, sent);", answered, StringComparison.Ordinal);
        Assert.True(answered.IndexOf("if (use == AnswerUse.Ignore)", StringComparison.Ordinal) < answered.IndexOf("Answer(doc, check.Prepared!, sent.Result, log)", StringComparison.Ordinal));
        Assert.True(answered.IndexOf("if (use == AnswerUse.ShowError)", StringComparison.Ordinal) < answered.IndexOf("Answer(doc, check.Prepared!, sent.Result, log)", StringComparison.Ordinal));
        Assert.Contains("ResultsPane.Failed(CheckFailures.Of(why, CheckWords.CheckerStopped(", answered, StringComparison.Ordinal);
        Assert.Contains("stale: use == AnswerUse.ShowStale", answered, StringComparison.Ordinal);
        var show = Between(check, "    private static void Show(UIApplication ui, Document doc, Ran run,", "\n    }\n");
        Assert.Contains("if (stale)\n                model = ResultRows.Stale(model, when, CheckWords.ChangedWhileChecking(when));", show, StringComparison.Ordinal);
        Assert.Contains("new PanelContent(doc.Title, when, model,", show, StringComparison.Ordinal);
        // a read cancelled before it began, or during a pick, reads nothing more
        var read = Between(check, "    internal static void ReadAndSend(", "\n    }\n");
        Assert.Contains("if (!CheckRun.Flow.IsCurrent(check.Ticket) || !doc.IsValidObject)", read, StringComparison.Ordinal);
        Assert.True(read.IndexOf("check.Clock.Architect(\"street_pick\", () => PickStreet(", StringComparison.Ordinal)
                    < read.IndexOf("if (!CheckRun.Flow.IsCurrent(check.Ticket))\n", StringComparison.Ordinal));
        Assert.Contains("if (!CheckRun.Flow.Fail(check.Ticket))", read, StringComparison.Ordinal);
        Assert.Contains("var shown = CheckRun.Flow.NothingSent(check.Ticket);", read, StringComparison.Ordinal);
    }

    [Fact]
    public void The_panel_counts_edits_of_the_model_being_checked_and_cancel_restores_stale()
    {
        var pane = Addin("ResultsPane.cs");
        var changed = Between(pane, "    internal static void OnDocumentChanged(", "\n    }\n");
        Assert.True(changed.IndexOf("if (!ResultRows.ChangesTheCheck(", StringComparison.Ordinal) < changed.IndexOf("CheckRun.Flow.Edited();", StringComparison.Ordinal));
        Assert.Contains("if (CheckRun.Reads(doc))\n                CheckRun.Flow.Edited();", changed, StringComparison.Ordinal);
        Assert.Contains("_view.MarkStale();", changed, StringComparison.Ordinal);
        var closing = Between(pane, "    internal static void OnDocumentClosing(", "\n    }\n");
        Assert.Contains("if (CheckRun.Reads(e.Document))\n                CheckRun.Cancel(CheckWords.Closed);", closing, StringComparison.Ordinal);
        var again = Between(pane, "    private static void CheckAgain()", "\n    }\n");
        Assert.Contains("if (CheckRun.Flow.Running)\n        {\n            CheckRun.Cancel();\n            return;\n        }", again, StringComparison.Ordinal);
        var view = Addin("ResultsView.cs");
        var restore = Between(view, "    internal void Restore(PanelHad had, string? why)", "\n    }\n");
        Assert.Contains("var restored = CheckFlow.Restored(had, Had);", restore, StringComparison.Ordinal);
        Assert.Contains("switch (restored)", restore, StringComparison.Ordinal);
        Assert.Contains("Say(why ?? CheckWords.Cancelled(restored));", restore, StringComparison.Ordinal);
        Assert.Contains("case PanelHad.Results when _content is { Model: { } model } content:\n                Show(content with { Model = ResultRows.Stale(model, content.When, CheckWords.CancelledStale(content.When), StaleReason.Cancelled),", restore, StringComparison.Ordinal);
        Assert.Contains("Failed(null);", restore, StringComparison.Ordinal);
        Assert.Contains("_again.Content = CheckWords.Button(stage);", view, StringComparison.Ordinal);
        Assert.Contains("internal PanelHad Had => CheckFlow.Had(_content is not null, _content?.Model is not null, _failed);", view, StringComparison.Ordinal);
        var cancel = Between(Addin("CheckRun.cs"), "    internal static void Cancel(", "\n    }\n");
        Assert.Contains("if (Flow.Cancel() is not { } had)", cancel, StringComparison.Ordinal);
        Assert.Contains("ResultsPane.Cancelled(had, why);", cancel, StringComparison.Ordinal);
    }

    [Fact]
    public void The_log_line_says_where_revits_thread_went()
    {
        var run = Addin("CheckRun.cs");
        Assert.Contains("check.Clock.Blocked(\"start\", Stopwatch.GetElapsedTime(started).TotalSeconds);", run, StringComparison.Ordinal);
        Assert.Contains("Clock.OffThread(\"check\", seconds);", run, StringComparison.Ordinal);
        var end = Between(run, "    internal void End(string how)", "\n    }\n");
        Assert.Contains("Log[\"ui_thread\"] = Clock.ToLog();", end, StringComparison.Ordinal);
        Assert.Contains("Trial.Log(\"check_project\", Log);", end, StringComparison.Ordinal);
        var check = Addin("CheckProject.cs");
        Assert.Contains("void Blocked() => check.Clock.Blocked(\"read\", Stopwatch.GetElapsedTime(started).TotalSeconds - (check.Clock.ArchitectSeconds - picked));", check, StringComparison.Ordinal);
        Assert.Contains("check.Clock.Blocked(\"show\", Stopwatch.GetElapsedTime(started).TotalSeconds);", check, StringComparison.Ordinal);
        Assert.Equal(2, check.Split("check.Clock.Architect(\"street_pick\", () => PickStreet(").Length - 1);
    }
}
