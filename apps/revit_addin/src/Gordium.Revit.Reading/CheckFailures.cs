using Gordium.Worker;

namespace Gordium.Revit.Reading;

// The check's waiting and failure states (UI polish changes 12 to 16; Ben approved 2026-11-23): progress as three
// steps; one message per failure, each saying what happened, what is safe, and what to do; no raw text anywhere on
// screen or in a tooltip (the exception and the log's path go only to "Copy details for support"); a time-out on the
// checker's silence, not on the whole check, with "Try again with more time". Revit-free and tested. The rule they keep:
// a failure shows no result of the check (nothing passes or fails), and says so.

/// <summary>What went wrong, as the pane tells it apart (strings.md, Errors).</summary>
public enum FailureKind
{
    /// <summary>The checker said nothing for the time limit, and was stopped.</summary>
    TookTooLong,

    /// <summary>The checker's process ended before answering.</summary>
    CheckerStopped,

    /// <summary>The checker answered something Gordium can't trust.</summary>
    Unreadable,

    /// <summary>The checker refused what was sent, with its reason.</summary>
    Refused,

    /// <summary>Reading the model in Revit failed: nothing was sent.</summary>
    ReadFailed,

    /// <summary>The project being checked was closed.</summary>
    ProjectClosed,

    /// <summary>Revit didn't run the check's next step (its ExternalEvent refused).</summary>
    NotStarted,

    /// <summary>Anything else.</summary>
    Other,
}

/// <summary>The card's main button.</summary>
public enum FailureAction { TryAgain, TryAgainWithMoreTime, None }

/// <summary>One failure as the pane shows it: a title, what happened and what is safe, what to do, its button, and
/// the technical details (only on the clipboard through "Copy details for support", never on screen).</summary>
public sealed record CheckFailure(FailureKind Kind, string Title, string Words, string? Next, FailureAction Action, string Details)
{
    /// <summary>The button's words.</summary>
    public string? ActionWords => Action switch
    {
        FailureAction.TryAgain => CheckFailures.TryAgain,
        FailureAction.TryAgainWithMoreTime => CheckFailures.MoreTime,
        _ => null,
    };

    /// <summary>What Gordium had already written to the project before it failed (the makers' clear openings filled as
    /// drafts, or why they couldn't be: ClearPrefills.Head), shown on screen under the words, or null.</summary>
    public string? Done { get; init; }
}

public static class CheckFailures
{
    /// <summary>The failure with what this check had already written to the project before it (<paramref name="done"/>:
    /// ClearPrefills.StatusLine's words, the marks added and the makers' clear openings filled as drafts), on screen in
    /// plain words (ClearPrefills.OnScreen: never Revit's exception text, change 14). A check that fails after the drafts
    /// were written still says so (review round 7 of the clear openings; PR 5 moved the failure from a dialog into the
    /// pane). When the check <paramref name="wrote"/> anything (marks, drafts, a street edge picked), the card never says
    /// "your model wasn't changed" (review after main 4077716d).</summary>
    public static CheckFailure After(this CheckFailure failure, string? done, bool wrote)
    {
        ArgumentNullException.ThrowIfNull(failure);
        var words = wrote ? failure.Words.Replace(Safe, NothingChecked, StringComparison.Ordinal)
                                         .Replace(" Your model wasn't changed.", "", StringComparison.Ordinal) : failure.Words;
        return failure with { Words = words, Done = string.IsNullOrWhiteSpace(done) ? null : ClearPrefills.OnScreen(done.Trim()) };
    }

    /// <summary><see cref="Safe"/> without its claim about the model, for a check that wrote to it before failing.</summary>
    public const string NothingChecked = "Nothing was checked.";

    public const string TryAgain = "Try again";

    public const string MoreTime = "Try again with more time";

    public const string CopyDetails = "Copy details for support";

    /// <summary>What every failure of the checker says is safe.</summary>
    public const string Safe = "Nothing was checked, and your model wasn't changed.";

    /// <summary>The checker's failure, from the exception the wait ended with; <paramref name="details"/> is what Copy
    /// details puts on the clipboard (the exception and the log's path).</summary>
    public static CheckFailure Of(Exception e, string details)
    {
        ArgumentNullException.ThrowIfNull(e);
        ArgumentNullException.ThrowIfNull(details);
        return Unwrap(e) switch
        {
            // the worker couldn't be started at all (no Gordium folder, Python missing, Revit closing)
            WorkerUnavailableException => new(FailureKind.CheckerStopped, "Gordium's checker didn't start",
                $"It couldn't be started. {Safe}", "Restart Revit and try again; if it happens again, send the details to support.",
                FailureAction.TryAgain, details),
            // the checker didn't start (its hello timed out): more time for the check wouldn't help (review round 4)
            WorkerTimeoutException { Command: "hello" } => new(FailureKind.CheckerStopped, "Gordium's checker didn't start",
                $"It didn't start in time. {Safe}", "Try again; if it happens again, restart Revit, then send the details to support.",
                FailureAction.TryAgain, details),
            // any other request than the check itself (the read's question about what is left out): it stopped
            // answering; more time for the check wouldn't help either (review round 5)
            WorkerTimeoutException { Command: not "check_site" } => new(FailureKind.CheckerStopped, "Gordium's checker stopped answering",
                $"It stopped answering before the check began. {Safe}", "Try again; if it happens again, send the details to support.",
                FailureAction.TryAgain, details),
            WorkerTimeoutException t => new(FailureKind.TookTooLong, "The check took too long",
                $"Gordium stopped waiting after {Seconds(t.Limit)}{(t.Silent ? " without a word from the checker" : "")}. {Safe}",
                "Large models can take longer. Try again with more time; if it keeps stopping, send the details to support.",
                FailureAction.TryAgainWithMoreTime, details),
            WorkerExitedException or WorkerStoppedException => new(FailureKind.CheckerStopped, "Gordium's checker stopped",
                $"It closed before answering. {Safe}", "Try again; if it happens again, send the details to support.",
                FailureAction.TryAgain, details),
            WorkerProtocolException => new(FailureKind.Unreadable, "Gordium couldn't read the checker's answer",
                "Nothing from this check is shown, so nothing passes or fails. This is a Gordium bug: send the details to support.",
                null, FailureAction.TryAgain, details),
            // the checker crashed on the request (it sent its traceback): a bug, never the architect's input
            WorkerRefusedException { Trace: not null } => new(FailureKind.CheckerStopped, "Gordium's checker hit an error",
                $"It failed on this check before answering. {Safe}", "This is a Gordium bug: send the details to support.",
                FailureAction.TryAgain, details),
            // the checker's refusals are written for the architect ("Gordium doesn't have rules for district B-1a yet…",
            // "lot facts: no zone given"): its first line, plain, with what to do
            WorkerRefusedException r => new(FailureKind.Refused, "The checker couldn't use what was sent",
                $"{Plain(r.Error)} Nothing was checked.", "Fix what it says, then check again.", FailureAction.TryAgain, details),
            _ => new(FailureKind.Other, "Gordium couldn't finish this check",
                "Nothing was checked, so nothing here passes or fails. Your model wasn't changed.", null, FailureAction.TryAgain, details),
        };
    }

    /// <summary>What a failure during the model's read says (review round 5: the read waits for the checker too, so a
    /// checker that didn't start or crashed then is said as the checker's failure, never as Revit's read).</summary>
    public static CheckFailure OfRead(Exception e, string details)
    {
        ArgumentNullException.ThrowIfNull(e);
        return Unwrap(e) is WorkerException w ? Of(w, details) : ReadFailed(details);
    }

    /// <summary>The failure an exception stands for: a task's AggregateException opened (one inner each time), then the
    /// outermost WorkerException along the inner exceptions, else the exception itself (review round 7: never
    /// GetBaseException, which digs past a WorkerException to the JsonException or the start's own error inside it).</summary>
    public static Exception Unwrap(Exception e)
    {
        ArgumentNullException.ThrowIfNull(e);
        while (e is AggregateException { InnerExceptions.Count: 1 } a)
            e = a.InnerExceptions[0];
        for (var x = e; x is not null; x = x.InnerException is AggregateException { InnerExceptions.Count: 1 } ai ? ai.InnerExceptions[0] : x.InnerException)
            if (x is WorkerException)
                return x;
        return e;
    }

    /// <summary>Reading the model in Revit failed (change 16: in the pane, never a dialog): nothing was sent.</summary>
    public static CheckFailure ReadFailed(string details) => new(FailureKind.ReadFailed, "Gordium couldn't read the model",
        "Revit stopped the read, so nothing was sent and nothing was checked. Your model wasn't changed.",
        "Try again; if it happens again, send the details to support.", FailureAction.TryAgain, details);

    /// <summary>The project being checked was closed before the answer.</summary>
    public static CheckFailure Closed(string details = "") => new(FailureKind.ProjectClosed, "The project was closed",
        "Nothing was checked. Open it and click Check project.", null, FailureAction.None, details);

    /// <summary>Revit didn't take the check's next step (its ExternalEvent was refused).</summary>
    public static CheckFailure NotStarted(string details, bool afterRead = false) => afterRead
        // the read had run (and may have written marks and drafts): Revit didn't take the step that shows the answer
        ? new(FailureKind.NotStarted, "Revit was busy and didn't show the check's answer",
              "Nothing from this check is shown, so nothing here passes or fails. Click Try again.", null, FailureAction.TryAgain, details)
        : new(FailureKind.NotStarted, "Revit was busy and didn't start the check",
              "Nothing was checked. Click Try again.", null, FailureAction.TryAgain, details);

    /// <summary>"60 seconds", "2 minutes".</summary>
    private static string Seconds(TimeSpan? limit)
    {
        if (limit is not { } l)
            return "its time limit";
        var s = (int)Math.Round(l.TotalSeconds);
        return s % 60 == 0 && s >= 120 ? $"{s / 60} minutes" : $"{s} seconds";
    }

    /// <summary>The checker's refusal in one plain line: its first line, no traceback, at most 200 characters, ending
    /// with a full stop.</summary>
    public static string Plain(string error)
    {
        ArgumentNullException.ThrowIfNull(error);
        var first = error.Split('\n')[0].Trim();
        if (first.Length > 200)
            first = first[..199].TrimEnd() + "…";
        return first.Length == 0 ? "It gave no reason." : DetailPages.Sentence(first);
    }

    /// <summary>The silence the checker gets first (change 15: it is stopped only when it says nothing this long).</summary>
    public static readonly TimeSpan FirstSilence = TimeSpan.FromSeconds(60);

    /// <summary>The longest a whole check may take, whatever the checker says meanwhile (review round 1: its progress
    /// lines prove it is alive, not that it is getting anywhere): ten times the silence, at least 10 minutes.</summary>
    public static TimeSpan Ceiling(TimeSpan silence) => silence * 10 > TimeSpan.FromMinutes(10) ? silence * 10 : TimeSpan.FromMinutes(10);

    /// <summary>The silence after "Try again with more time": twice the last (at most 16 minutes).</summary>
    public static TimeSpan More(TimeSpan silence) => silence * 2 > TimeSpan.FromMinutes(16) ? TimeSpan.FromMinutes(16) : silence * 2;
}

/// <summary>Where a step of the check's progress is.</summary>
public enum StepState { Waiting, Running, Done }

/// <summary>One of the three steps (change 12): its words, where it is, and its seconds.</summary>
public sealed record CheckStep(string Words, StepState State, string? Time);

public static class CheckSteps
{
    public const string Read = "Read the model";
    public const string Check = "Checking zoning and egress rules";
    public const string Show = "Showing results";

    /// <summary>The line under the steps while Revit reads (it waits: its API runs on its own thread).</summary>
    public const string ReadingNote = "Revit waits while Gordium reads the model.";

    /// <summary>The line under the steps while the checker works (Revit is free).</summary>
    public const string KeepWorking = "You can keep working in Revit. If you edit the model now, these results will be marked out of date.";

    /// <summary>After 40 s of checking.</summary>
    public const string Long = "Large models can take a minute or two.";

    /// <summary>When the long note shows.</summary>
    public static readonly TimeSpan LongAfter = TimeSpan.FromSeconds(40);

    /// <summary>The three steps at <paramref name="stage"/>: the read's seconds once done, the check's while it runs.</summary>
    public static IReadOnlyList<CheckStep> Of(CheckStage stage, TimeSpan? read, TimeSpan checking)
    {
        static string S(TimeSpan t) => $"{Math.Max(0, (int)t.TotalSeconds)} s";
        return stage switch
        {
            CheckStage.Reading => [new(Read, StepState.Running, null), new(Check, StepState.Waiting, null), new(Show, StepState.Waiting, null)],
            _ => [new(Read, StepState.Done, read is { } r ? S(r) : null), new(Check, StepState.Running, S(checking)), new(Show, StepState.Waiting, null)],
        };
    }

    /// <summary>The note under the steps.</summary>
    public static string Note(CheckStage stage, TimeSpan checking) =>
        stage == CheckStage.Reading ? ReadingNote : checking >= LongAfter ? KeepWorking + " " + Long : KeepWorking;
}
