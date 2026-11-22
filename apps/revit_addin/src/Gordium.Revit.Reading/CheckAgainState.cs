namespace Gordium.Revit.Reading;

/// <summary>
/// Whether the results panel's Check again is waiting for Revit to run it, or a check runs, kept apart from what the
/// panel draws: a redraw while it waits or runs (the model edited, so the results are greyed) keeps the button as it
/// is and the progress line shown (review round 2: a redraw re-enabled it, and a second click queued a second check).
/// Two kinds of busy: <see cref="Start"/>, the click queued for Revit's thread (greyed, "Checking..."), and
/// <see cref="Running"/>, a check reading or checking (PR 8: the button is Cancel, usable, and the line is the
/// stage's progress, <see cref="CheckWords.Progress"/>).
/// </summary>
public sealed class CheckAgainState
{
    /// <summary>What the panel says while a click waits for Revit to take it.</summary>
    public const string Checking = "Checking...";

    /// <summary>Whether a check was asked for and hasn't finished.</summary>
    public bool Busy { get; private set; }

    /// <summary>Whether a check runs (its button is Cancel).</summary>
    public bool IsRunning { get; private set; }

    /// <summary>Whether the header button can be clicked: when nothing waits (Check again), or while a check runs
    /// (Cancel); greyed only while a click waits for Revit.</summary>
    public bool Enabled => !Busy || IsRunning;

    /// <summary>The progress line shown while busy.</summary>
    public string Line { get; private set; } = Checking;

    /// <summary>A line a redraw wanted while busy ("Added 3 Gordium marks to this project."), shown once it ends.</summary>
    private string _held = "";

    /// <summary>A click queued for Revit's thread: greyed, "Checking...".</summary>
    public void Start()
    {
        Busy = true;
        IsRunning = false;
        Line = Checking;
        _held = "";
    }

    /// <summary>A check runs, at the stage <paramref name="line"/> says: Cancel usable. Keeps what a redraw held.</summary>
    public void Running(string line)
    {
        ArgumentNullException.ThrowIfNull(line);
        if (!Busy)
            _held = "";
        Busy = true;
        IsRunning = true;
        Line = line;
    }

    /// <summary>Ends the wait and gives the line to show next: while the panel still says the progress line, the line
    /// a redraw wanted meanwhile (review round 3: a Check again that added marks never said so), "" when none; any
    /// other line (a failure's words) unchanged.</summary>
    public string Stop(string currentStatus)
    {
        ArgumentNullException.ThrowIfNull(currentStatus);
        var line = Line;
        Busy = false;
        IsRunning = false;
        Line = Checking;
        var held = _held;
        _held = "";
        return currentStatus == line ? held : currentStatus;
    }

    /// <summary>The line to show after a redraw that would show <paramref name="shown"/>: the progress line while
    /// busy, the line kept for <see cref="Stop"/> (a later redraw with nothing to say, a greyed one, never erases it).</summary>
    public string Status(string shown)
    {
        if (!Busy)
            return shown;
        if (shown.Length > 0)
            _held = shown;
        return Line;
    }
}
