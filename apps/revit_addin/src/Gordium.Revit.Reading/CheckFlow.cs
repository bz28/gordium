using System.Diagnostics;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>Where one "Check my project" is (design pass section 2.6, PR 8): <see cref="Idle"/> before any, then
/// <see cref="Reading"/> (on Revit's thread: Revit's API can only be called there, so Revit waits), then
/// <see cref="Checking"/> (the request sent and waited for off Revit's thread: Revit is free), then one of
/// <see cref="Done"/>, <see cref="Cancelled"/> or <see cref="Failed"/>.</summary>
public enum CheckStage
{
    Idle,
    Reading,
    Checking,
    Done,
    Cancelled,
    Failed,
}

/// <summary>What the panel showed when a check began: what Cancel goes back to.</summary>
public enum PanelHad
{
    /// <summary>Nothing checked yet (the empty state).</summary>
    Nothing,

    /// <summary>An earlier check's results: kept on Cancel, marked stale (never shown as the new ones).</summary>
    Results,

    /// <summary>An earlier "nothing was checked: fill these in first": shown again as it was.</summary>
    Missing,

    /// <summary>An earlier check that failed (the error state).</summary>
    Error,
}

/// <summary>What to do with a worker's answer when it reaches Revit's thread.</summary>
public enum AnswerUse
{
    /// <summary>Not this check's (cancelled, a later check began, or it already ended): never shown.</summary>
    Ignore,

    /// <summary>The model is as it was read: shown as the current results.</summary>
    ShowFresh,

    /// <summary>The model changed after the read (an edit committed while the checker worked): shown stale, greyed,
    /// never green; the answer is for a model that is no longer the one open.</summary>
    ShowStale,

    /// <summary>No answer (the worker crashed, timed out, or answered something unreadable): the error state, no row
    /// of this check shown, so never a partial pass.</summary>
    ShowError,
}

/// <summary>
/// One "Check my project" at a time, without Revit (PR 8: a check that doesn't freeze Revit). The add-in reads the
/// model on Revit's thread, sends it and waits off that thread, then shows the answer back on Revit's thread; this
/// class decides, for each of those steps, whether it still belongs to the check the panel is waiting for:
/// <list type="bullet">
/// <item>Each check has a ticket (<see cref="TryStart"/>); a step of any other ticket is ignored, so an answer that
/// arrives after Cancel, or after a later check began, is never shown.</item>
/// <item>A second check while one runs is refused (the panel's button is Cancel meanwhile): the read is the part
/// that makes Revit wait, and a check started on top of another would read the model twice; an edit made meanwhile
/// already makes the coming answer stale, and Check again after it reads the model as it is.</item>
/// <item>Edits of the model being checked are counted (<see cref="Edited"/>, from Revit's DocumentChanged); the
/// count is kept when the read ends (<see cref="ReadDone"/>), and an answer is shown fresh only when it hasn't moved
/// since (<see cref="Answered"/>): an edit committed after the read and before the answer makes it stale.</item>
/// <item>Cancel (<see cref="Cancel"/>) cancels the wait's token (the add-in's worker request is then stopped) and
/// says what the panel goes back to: the earlier results marked stale, or the empty, missing or error state.</item>
/// <item>A failure (<see cref="Fail"/>: the worker crashed, timed out, or answered something unreadable) is the error
/// state: no row of the failed check is ever shown, so never a partial pass.</item>
/// </list>
/// Thread-safe (the answer's task ends on a pool thread); every call is cheap.
/// </summary>
public sealed class CheckFlow
{
    private readonly object _lock = new();
    private long _last;
    private long _current;                        // the running or last check's ticket; 0 before any
    private CheckStage _stage = CheckStage.Idle;
    private PanelHad _had;
    private long _edits;
    private long _editsAtRead;
    private CancellationTokenSource? _cancel;

    /// <summary>The stage of the running, or last, check.</summary>
    public CheckStage Stage
    {
        get { lock (_lock) return _stage; }
    }

    /// <summary>Whether a check is reading or checking (the panel's button is then Cancel).</summary>
    public bool Running
    {
        get { lock (_lock) return IsRunning(_stage); }
    }

    private static bool IsRunning(CheckStage s) => s is CheckStage.Reading or CheckStage.Checking;

    /// <summary>What a panel shows, for <see cref="TryStart"/>: results when it shows a check's rows, the list of what
    /// to fill in when it shows a check that sent nothing, the error state after a failure, else nothing.</summary>
    public static PanelHad Had(bool shown, bool rows, bool failed) =>
        shown ? (rows ? PanelHad.Results : PanelHad.Missing) : failed ? PanelHad.Error : PanelHad.Nothing;

    /// <summary>What Cancel can go back to: what the panel had when the check began (<paramref name="had"/>), when it
    /// still shows it (<paramref name="now"/>: the earlier results or the list of what to fill in); else no rows (the
    /// earlier project closed meanwhile, say): the error state when either was one, else nothing. Cancel's words
    /// (<see cref="CheckWords.Cancelled"/>) are this one's, never "the results below" with none below.</summary>
    public static PanelHad Restored(PanelHad had, PanelHad now) =>
        had == now ? had : had == PanelHad.Error || now == PanelHad.Error ? PanelHad.Error : PanelHad.Nothing;

    /// <summary>Begins a check: its ticket, its stage Reading; null (and nothing changes) when one is running.
    /// <paramref name="had"/> is what the panel showed, for Cancel.</summary>
    public long? TryStart(PanelHad had)
    {
        lock (_lock)
        {
            if (IsRunning(_stage))
                return null;
            _cancel?.Dispose();
            _cancel = new CancellationTokenSource();
            _current = ++_last;
            _stage = CheckStage.Reading;
            _had = had;
            return _current;
        }
    }

    /// <summary>Whether <paramref name="ticket"/> is the check running now.</summary>
    public bool IsCurrent(long ticket)
    {
        lock (_lock)
            return ticket == _current && IsRunning(_stage);
    }

    /// <summary>The token that cancels <paramref name="ticket"/>'s wait (already cancelled when the ticket isn't the
    /// running check's).</summary>
    public CancellationToken Token(long ticket)
    {
        lock (_lock)
            return ticket == _current && IsRunning(_stage) && _cancel is { } c ? c.Token : new CancellationToken(canceled: true);
    }

    /// <summary>An edit of the model being checked, committed (Revit's DocumentChanged, the check's own transactions
    /// left out: ResultRows.ChangesTheCheck).</summary>
    public void Edited()
    {
        lock (_lock)
            _edits++;
    }

    /// <summary>The read ended and the request is about to be sent: Reading becomes Checking, and the model's edit
    /// count is kept, so any later edit makes the answer stale. False (nothing changes) when the ticket isn't the
    /// running check's or it isn't reading (cancelled meanwhile: nothing is sent).</summary>
    public bool ReadDone(long ticket)
    {
        lock (_lock)
        {
            if (ticket != _current || _stage != CheckStage.Reading)
                return false;
            _editsAtRead = _edits;
            _stage = CheckStage.Checking;
            return true;
        }
    }

    /// <summary>The check ended with nothing sent (a fact missing: the panel lists what to fill in): Done. False when
    /// the ticket isn't the running check's.</summary>
    public bool NothingSent(long ticket)
    {
        lock (_lock)
        {
            if (ticket != _current || _stage != CheckStage.Reading)
                return false;
            _stage = CheckStage.Done;
            return true;
        }
    }

    /// <summary>The worker answered, on Revit's thread now: Done, and how to show it (fresh only when no edit was
    /// counted since the read); <see cref="AnswerUse.Ignore"/> (nothing changes) for any other ticket, or one not
    /// checking (cancelled, failed, or already answered).</summary>
    public AnswerUse Answered(long ticket)
    {
        lock (_lock)
        {
            if (ticket != _current || _stage != CheckStage.Checking)
                return AnswerUse.Ignore;
            _stage = CheckStage.Done;
            return _edits == _editsAtRead ? AnswerUse.ShowFresh : AnswerUse.ShowStale;
        }
    }

    /// <summary>What to do with the outcome of <paramref name="ticket"/>'s wait (<see cref="Send"/>), on Revit's thread
    /// now: an answer is <see cref="Answered"/>'s; no answer (a fault or a cancel) is <see cref="AnswerUse.ShowError"/>
    /// when the check is still the running one (<see cref="Fail"/>), else ignored (a cancelled check's stopped worker).</summary>
    public AnswerUse Arrived(long ticket, Task<CheckResult> sent)
    {
        ArgumentNullException.ThrowIfNull(sent);
        if (sent.Status == TaskStatus.RanToCompletion)
            return Answered(ticket);
        return Fail(ticket) ? AnswerUse.ShowError : AnswerUse.Ignore;
    }

    /// <summary>Sends <paramref name="ticket"/>'s request and waits off the caller's thread (Revit's never waits): the
    /// worker being started waited for, then the check_site, both under the check's token (Cancel stops the worker:
    /// WorkerClient stops it on a cancel); the outcome (the answer, or the fault or cancel) and the seconds waited are
    /// given to <paramref name="arrived"/> on a pool thread, whatever happens. The task ends after it.</summary>
    public Task Send(long ticket, Task<WorkerClient> worker, ProjectRequest request, Action<Task<CheckResult>, double> arrived,
                     TimeSpan? silence = null, IProgress<string>? step = null)
    {
        ArgumentNullException.ThrowIfNull(worker);
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(arrived);
        var cancel = Token(ticket);
        var started = Stopwatch.GetTimestamp();
        return Task.Run(async () =>
            {
                var client = await worker.WaitAsync(cancel).ConfigureAwait(false);
                return await ProjectCheck.SendAsync(client, request, cancel, silence, step).ConfigureAwait(false);
            }, cancel)
            .ContinueWith(sent => arrived(sent, Stopwatch.GetElapsedTime(started).TotalSeconds),
                          CancellationToken.None, TaskContinuationOptions.None, TaskScheduler.Default);
    }

    /// <summary>The running check failed (the read threw, the worker crashed, timed out or answered something
    /// unreadable): Failed, the panel's error state. False (nothing changes) for any other ticket or a check no
    /// longer running: a cancelled check's stopped worker is not a failure to show.</summary>
    public bool Fail(long ticket)
    {
        lock (_lock)
        {
            if (ticket != _current || !IsRunning(_stage))
                return false;
            _stage = CheckStage.Failed;
            return true;
        }
    }

    /// <summary>Cancels the running check (the architect's Cancel, or the project checked closing): Cancelled, its
    /// wait's token cancelled, and what the panel goes back to; null when nothing is running.</summary>
    public PanelHad? Cancel()
    {
        CancellationTokenSource? cancel;
        PanelHad had;
        lock (_lock)
        {
            if (!IsRunning(_stage))
                return null;
            _stage = CheckStage.Cancelled;
            cancel = _cancel;
            had = _had;
        }
        cancel?.Cancel();                                 // outside the lock: its callbacks stop the worker
        return had;
    }
}

/// <summary>The panel's words for each stage of a check (<see cref="CheckFlow"/>), kept here so they are tested.</summary>
public static class CheckWords
{
    /// <summary>The header button while a check runs.</summary>
    public const string Cancel = "Cancel";

    /// <summary>The header button otherwise.</summary>
    public const string CheckAgain = "Check again";

    /// <summary>The button's word for a stage.</summary>
    public static string Button(CheckStage stage) =>
        stage is CheckStage.Reading or CheckStage.Checking ? Cancel : CheckAgain;

    /// <summary>The progress line while reading: Revit waits (its API can be called only on its own thread).</summary>
    public const string Reading = "Reading the model... Revit waits until the read ends.";

    /// <summary>The progress line while the checker works, with how long it has: Revit is free.</summary>
    public static string Checking(TimeSpan waited) =>
        $"Checking (Gordium's checker, {Math.Max(0, (int)waited.TotalSeconds)} s)... You can keep working: an edit now " +
        "makes this answer stale.";

    /// <summary>The progress line for a running stage; null for any other.</summary>
    public static string? Progress(CheckStage stage, TimeSpan waited) => stage switch
    {
        CheckStage.Reading => Reading,
        CheckStage.Checking => Checking(waited),
        _ => null,
    };

    /// <summary>A second check asked for while one runs.</summary>
    public const string Refused = "A check is already running. Wait for it, or cancel it first (Cancel, at the top of the Gordium pane).";

    /// <summary>What the panel says after Cancel, by what it went back to.</summary>
    public static string Cancelled(PanelHad had) => had switch
    {
        PanelHad.Results => "Check cancelled: the results below are the earlier check's, and may not hold.",
        PanelHad.Missing => "Check cancelled: nothing new was checked.",
        _ => "Check cancelled: nothing was checked.",
    };

    /// <summary>The stale notice on the earlier results after Cancel (made at <paramref name="checkedAt"/>).</summary>
    public static string CancelledStale(DateTime checkedAt) =>
        $"These results are from {checkedAt:HH:mm}, {PaneWords.StaleBefore(StaleReason.Cancelled)}; the model may have changed since: click Check again";

    /// <summary>The stale notice on an answer whose model was edited while the checker worked (read at
    /// <paramref name="readAt"/>).</summary>
    public static string ChangedWhileChecking(DateTime readAt) =>
        $"The model changed while this check ran (read at {readAt:HH:mm}): these results may not hold: click Check again";

    /// <summary>The error state's line: the checker stopped (crashed, timed out, or answered something unreadable);
    /// no row of this check is shown.</summary>
    public static string CheckerStopped(string why) =>
        $"Gordium's checker stopped before answering ({why}): nothing was checked. Click Check again.";

    /// <summary>The project being checked was closed before the answer.</summary>
    public const string Closed = "The project being checked was closed: nothing was checked. Open it and click Check project.";
}
