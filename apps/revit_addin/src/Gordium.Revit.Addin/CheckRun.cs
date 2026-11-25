using System.Diagnostics;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;
using Gordium.Worker;

namespace Gordium.Revit.Addin;

/// <summary>
/// One "Check my project" that doesn't freeze Revit (design pass PR 8): its ticket in the one <see cref="Flow"/>
/// (which decides every step, tested without Revit), its log line (written once, when it ends however it ends, with
/// <c>ui_thread</c>: where Revit's thread went), the worker being started, and what the read gave. The steps:
/// <list type="number">
/// <item><see cref="Start"/> (Revit's thread, a command or a panel action): refused while a check runs; else the
/// worker's start begun on a pool thread, the panel brought up saying "Reading the model..." with Cancel, and the read
/// queued for after the panel has drawn that line (the read blocks Revit's thread, so nothing is drawn during it).</item>
/// <item>The read (<see cref="CheckProjectCommand.ReadAndSend"/>, Revit's thread through the panel's ExternalEvent):
/// Revit waits, as Revit's API requires.</item>
/// <item><see cref="Send"/>: the request sent and waited for on a pool thread; the panel says "Checking..." and Revit
/// is free. Cancel cancels the wait's token: the worker is stopped (WorkerClient stops it on a cancel) and the next
/// check starts a new one.</item>
/// <item>The answer back on Revit's thread (<see cref="CheckProjectCommand.Answered"/>, the ExternalEvent again):
/// shown fresh, shown stale (an edit was committed after the read: counted from Revit's DocumentChanged by
/// <see cref="ResultsPane.OnDocumentChanged"/>), or ignored (cancelled).</item>
/// </list>
/// </summary>
internal sealed class CheckRun
{
    /// <summary>The one check flow of this Revit session: one check at a time.</summary>
    internal static readonly CheckFlow Flow = new();

    private static CheckRun? _last;

    private int _ended;

    private CheckRun(long ticket, Document doc)
    {
        Ticket = ticket;
        Doc = doc;
    }

    internal long Ticket { get; }

    /// <summary>The document this check reads.</summary>
    internal Document Doc { get; }

    /// <summary>The log line (Revit's thread only: the pool thread hands its figures over through the answer's action).</summary>
    internal Dictionary<string, object?> Log { get; } = new();

    internal UiThreadTime Clock { get; } = new();

    /// <summary>The worker, being started while Revit reads.</summary>
    internal Task<WorkerClient> Worker { get; private set; } = null!;

    /// <summary>When the read ended: the results' "Checked HH:mm", and the stale notice's "read at".</summary>
    internal DateTime ReadAt { get; private set; }

    internal ProjectPrepared? Prepared { get; private set; }
    internal int MarksAdded { get; private set; }

    /// <summary>Whether this check wrote to the project before it failed (marks added, drafts filled, a street edge
    /// picked): its failure card then never says the model wasn't changed.</summary>
    internal bool Wrote { get; set; }
    internal StreetAsk Ask { get; private set; }
    internal string Clear { get; private set; } = "";

    /// <summary>Whether <paramref name="doc"/> is the one the running check reads (its edits are counted).</summary>
    internal static bool Reads(Document doc) => _last is { } r && Flow.IsCurrent(r.Ticket) && r.Doc.Equals(doc);

    /// <summary>The architect's "Check now anyway" (the Setup form): sent with the facts that are set, each one
    /// missing making its rules need review; no Setup form and no street pick first.</summary>
    internal bool Anyway { get; private init; }

    /// <summary>Begins a check of <paramref name="doc"/>; <see cref="CheckWords.Refused"/> while one runs.
    /// <paramref name="anyway"/>: the Setup form's "Check now anyway".</summary>
    internal static string? Start(UIApplication ui, Document doc, bool anyway = false)
    {
        var started = Stopwatch.GetTimestamp();
        if (Flow.TryStart(ResultsPane.Had()) is not { } ticket)
            return CheckWords.Refused;
        var check = new CheckRun(ticket, doc) { Anyway = anyway };
        _last = check;
        check.Log["document"] = doc.Title;
        check.Log["check"] = ticket;
        check.Log["anyway"] = anyway;
        // Python started now, on a pool thread, while Revit reads (a start that fails is said when the worker is needed)
        check.Worker = StartWorker();
        ResultsPane.Reading(ui);
        check.Clock.Blocked("start", Stopwatch.GetElapsedTime(started).TotalSeconds);
        ResultsPane.AfterDrawn(() => ResultsPane.Post("Read the model", app => CheckProjectCommand.ReadAndSend(app, doc, check),
                                                      refused: () => check.Refused("the model's read")));
        return null;
    }

    private static Task<WorkerClient> StartWorker()
    {
        try
        {
            return Started(Trial.WorkerAsync());
        }
        catch (Exception e)                                    // no clone: said when the worker is needed
        {
            return Task.FromException<WorkerClient>(new WorkerUnavailableException($"The Gordium checker couldn't be started: {e.Message}", e));
        }
    }

    /// <summary>The worker's start, its failures that aren't the worker's own words (no Gordium folder, Revit closing)
    /// said as the worker that couldn't be started, wherever it is first waited for: the read's question or the check
    /// (UI polish PR 5 review round 8: the same cause, one card). A cancel stays a cancel.</summary>
    internal static async Task<WorkerClient> Started(Task<WorkerClient> start)
    {
        try
        {
            return await start.ConfigureAwait(false);
        }
        catch (Exception e) when (e is not WorkerException and not OperationCanceledException)
        {
            throw new WorkerUnavailableException($"The Gordium checker couldn't be started: {e.Message}", e);
        }
    }

    /// <summary>What the read gave (for the answer's words, and the panel's status line).</summary>
    internal void Read(ProjectPrepared prepared, int marksAdded, StreetAsk ask, string clear)
    {
        Prepared = prepared;
        MarksAdded = marksAdded;
        Ask = ask;
        Clear = clear;
    }

    /// <summary>The read ended (Revit's thread, at once: the edit count is kept now, CheckFlow.ReadDone): Checking.
    /// False, and the log line written, when the check was cancelled during the read's picks: nothing is sent.</summary>
    internal bool ReadEnded()
    {
        if (!Flow.ReadDone(Ticket))
        {
            End("cancelled");
            return false;
        }
        ReadAt = DateTime.Now;
        ResultsPane.Checking(ReadAt);
        return true;
    }

    /// <summary>Sends the request and waits off Revit's thread (queued after <see cref="ReadEnded"/>, behind Revit's
    /// queued input): nothing sent, and the worker left running, when a Cancel came first.</summary>
    internal void Send(ProjectRequest request)
    {
        if (!Flow.IsCurrent(Ticket))
        {
            Log["cancelled_before_send"] = true;
            End("cancelled");                                  // cancelled during the read: nothing sent
            return;
        }
        // off Revit's thread (CheckFlow.Send); the outcome back on it through the panel's ExternalEvent
        // the checker is stopped only when it says nothing for Silence (UI polish change 15); each of its progress lines
        // is shown under the check's step
        Log["silence_s"] = Silence.TotalSeconds;
        _ = Flow.Send(Ticket, Worker, request, (sent, seconds) =>
            ResultsPane.Post("Show the check's answer", app =>
            {
                Log["check_s"] = seconds;
                Clock.OffThread("check", seconds);
                CheckProjectCommand.Answered(app, Doc, this, sent);
            }, refused: () => Refused("the checker's answer")), Silence, new Said(step => ResultsPane.Ui(() => ResultsPane.Step(step))));
    }

    /// <summary>How long the checker may say nothing before it is stopped: 60 s, doubled by each "Try again with more
    /// time" this session (CheckFailures.More).</summary>
    internal static TimeSpan Silence { get; private set; } = CheckFailures.FirstSilence;

    /// <summary>"Try again with more time": the next check's silence doubled.</summary>
    internal static void MoreTime() => Silence = CheckFailures.More(Silence);

    /// <summary>A progress line, handed on as it comes (never through a captured context: the pane's Ui does that).</summary>
    private sealed class Said(Action<string> said) : IProgress<string>
    {
        public void Report(string value) => said(value);
    }

    /// <summary>Revit refused the ExternalEvent for <paramref name="what"/>: the error state (never a check left
    /// waiting with nothing to end it), unless it was cancelled meanwhile.</summary>
    private void Refused(string what) => ResultsPane.Ui(() =>
    {
        Log["error"] = $"Revit refused {what}";
        if (!Flow.Fail(Ticket))
        {
            End("cancelled");
            return;
        }
        End("failed");
        ResultsPane.Failed(CheckFailures.NotStarted($"Revit didn't take {what}: nothing was checked.", afterRead: Prepared is not null)
                                         .After(ClearPrefills.StatusLine(MarksAdded, Clear), Wrote));   // after a read: what it wrote
    });

    /// <summary>Cancels the running check (the panel's Cancel, or the project read closing; on Revit's thread, no API
    /// call): the wait's token cancelled (the worker stopped), the panel back to what it showed before (the earlier
    /// results stale, or the empty, missing or error state); <paramref name="why"/> replaces the panel's words.</summary>
    internal static void Cancel(string? why = null)
    {
        var stage = Flow.Stage;
        if (Flow.Cancel() is not { } had)
            return;
        if (_last is { } check)
            check.Log["cancelled"] = $"{stage} at {DateTime.Now:O}";
        ResultsPane.Cancelled(had, why);
    }

    /// <summary>Writes the log line once, with how the check ended and where Revit's thread went.</summary>
    internal void End(string how)
    {
        if (Interlocked.Exchange(ref _ended, 1) == 1)
            return;
        Log["ended"] = how;
        Log["ui_thread"] = Clock.ToLog();
        Trial.Log("check_project", Log);
    }
}
