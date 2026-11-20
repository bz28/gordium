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

    public void Start() => Busy = true;

    public void Stop() => Busy = false;

    /// <summary>The line to show after a redraw that would show <paramref name="shown"/>: "Checking..." while busy.</summary>
    public string Status(string shown) => Busy ? Checking : shown;
}
