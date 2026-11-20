namespace Gordium.Revit.Reading;

/// <summary>
/// Whether the results panel's Check again is waiting for Revit to run it, kept apart from what the panel draws:
/// a redraw while it waits (the model edited, so the results are greyed) keeps the button greyed and "Checking..."
/// shown (review round 2: a redraw re-enabled it, and a second click queued a second check).
/// </summary>
public sealed class CheckAgainState
{
    /// <summary>What the panel says while a check waits or runs.</summary>
    public const string Checking = "Checking...";

    /// <summary>Whether a check was asked for and hasn't finished.</summary>
    public bool Busy { get; private set; }

    /// <summary>Whether Check again can be clicked.</summary>
    public bool Enabled => !Busy;

    /// <summary>A line a redraw wanted while busy ("Added 3 Gordium marks to this project."), shown once it ends.</summary>
    private string _held = "";

    public void Start()
    {
        Busy = true;
        _held = "";
    }

    /// <summary>Ends the wait; gives the line a redraw wanted meanwhile (review round 3: a Check again that added
    /// marks never said so), "" when none.</summary>
    public string Stop()
    {
        Busy = false;
        var held = _held;
        _held = "";
        return held;
    }

    /// <summary>The line to show after a redraw that would show <paramref name="shown"/>: "Checking..." while busy,
    /// the line kept for <see cref="Stop"/> (a later redraw with nothing to say, a greyed one, never erases it).</summary>
    public string Status(string shown)
    {
        if (!Busy)
            return shown;
        if (shown.Length > 0)
            _held = shown;
        return Checking;
    }
}
