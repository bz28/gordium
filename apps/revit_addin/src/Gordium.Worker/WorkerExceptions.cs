namespace Gordium.Worker;

/// <summary>Anything that went wrong talking to the worker. Never caught and turned into a result: an add-in shows
/// the message and no verdicts (Gordium's rule: never a false pass).</summary>
public class WorkerException : Exception
{
    public WorkerException(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>The worker couldn't be started at all (no Gordium folder found, Revit closing): the checker's failure,
/// never the model read's, though the read is what was waiting for it.</summary>
public sealed class WorkerUnavailableException : WorkerException
{
    public WorkerUnavailableException(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>The worker answered <c>"ok": false</c>: it refused the request (a bad field, an unknown command, facts
/// it can't read) and gave its words. The worker is still in step and keeps serving.</summary>
public sealed class WorkerRefusedException : WorkerException
{
    /// <summary>The worker's own words (<c>error</c>).</summary>
    public string Error { get; }

    /// <summary>The Python traceback, sent only when the worker itself crashed on the request (<c>trace</c>).</summary>
    public string? Trace { get; }

    public WorkerRefusedException(string command, string error, string? trace)
        : base($"The Gordium checker refused {command}: {error}")
    {
        Error = error;
        Trace = trace;
    }
}

/// <summary>An answer that can't be trusted: not JSON, not this request's, a field missing or of the wrong kind, a
/// status Gordium doesn't know. The client stops the worker: its later lines could belong to the wrong request.</summary>
public class WorkerProtocolException : WorkerException
{
    public WorkerProtocolException(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>The worker speaks a different major protocol version, or a different site description version, than
/// this client (worker_protocol_v1.md, Versions: each side refuses a different major version).</summary>
public sealed class WorkerVersionException : WorkerProtocolException
{
    public WorkerVersionException(string message) : base(message) { }
}

/// <summary>The worker process ended (it crashed, was killed, or closed its output) before answering.</summary>
public sealed class WorkerExitedException : WorkerException
{
    /// <summary>The process's exit code, when it had exited by the time this was raised.</summary>
    public int? ExitCode { get; }

    /// <summary>The last lines the worker wrote to its log (stderr), for the message an engineer reads.</summary>
    public string LogTail { get; }

    public WorkerExitedException(string message, int? exitCode, string logTail)
        : base(message + (exitCode is int c ? $" (exit code {c})" : "") + (logTail.Length > 0 ? $". Its last log lines:\n{logTail}" : ""))
    {
        ExitCode = exitCode;
        LogTail = logTail;
    }
}

/// <summary>No answer within the time limit. The client stops the worker (a late answer would arrive as the next
/// request's).</summary>
public sealed class WorkerTimeoutException : WorkerException
{
    /// <summary>The time limit that ran out (what "The check took too long" says), or null when not known.</summary>
    public TimeSpan? Limit { get; init; }

    /// <summary>The command it was waiting for ("hello" while the worker starts, "check_site" for a check), or null.</summary>
    public string? Command { get; init; }

    /// <summary>Whether the limit was on silence (no line from the worker for that long), not on the whole answer.</summary>
    public bool Silent { get; init; }

    public WorkerTimeoutException(string message) : base(message) { }
}

/// <summary>This client stopped its worker after an earlier failure (a timeout, a crash, an answer it couldn't
/// trust, a cancel). Start a new <see cref="WorkerClient"/>; the worker keeps nothing between requests, so nothing
/// is lost.</summary>
public sealed class WorkerStoppedException : WorkerException
{
    public WorkerStoppedException(string message) : base(message) { }
}

/// <summary>One part of a session command refused its input and gave its words under <c>result.refused</c>
/// (worker_protocol_v1.md, How a command is answered, 4). The other parts still answered.</summary>
public sealed class PartRefusedException : WorkerException
{
    /// <summary>The answer asked for.</summary>
    public string Answer { get; }

    /// <summary>The worker's words, to show beside the field.</summary>
    public string Words { get; }

    public PartRefusedException(string command, string answer, string words)
        : base($"{command}: {answer} refused: {words}")
    {
        Answer = answer;
        Words = words;
    }
}

/// <summary>An answer asked for that the session command didn't give: its part didn't run (its fields weren't
/// sent) or the request's <c>want</c> left it out. Never read as an empty or false answer.</summary>
public sealed class AnswerMissingException : WorkerException
{
    public AnswerMissingException(string message) : base(message) { }
}
