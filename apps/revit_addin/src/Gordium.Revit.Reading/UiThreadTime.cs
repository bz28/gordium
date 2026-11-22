using System.Diagnostics;

namespace Gordium.Revit.Reading;

/// <summary>
/// How long one "Check my project" kept Revit's own thread busy (the trial log's <c>ui_thread</c>, beside
/// <c>read_steps</c>; README, "The results log"): Revit is frozen while its thread runs the add-in's code, so this is
/// the time the architect waited with Revit not answering. Three kinds of time, kept apart:
/// <list type="bullet">
/// <item><b>blocked</b>: the add-in's code on Revit's thread (the start, the read, showing the answer): the freeze.</item>
/// <item><b>architect</b>: on Revit's thread but waiting for the architect (the street edge pick and its question):
/// Revit answers then, so it is never counted as blocked.</item>
/// <item><b>off_thread</b>: waited for off Revit's thread (the worker's answer): Revit is free meanwhile.</item>
/// </list>
/// Only a measurement: never in a record or the request. Thread-safe (the off-thread wait ends on a pool thread).
/// </summary>
public sealed class UiThreadTime
{
    private readonly object _lock = new();
    private readonly Dictionary<string, (double Seconds, int Calls)> _blocked = new(StringComparer.Ordinal);
    private readonly Dictionary<string, (double Seconds, int Calls)> _architect = new(StringComparer.Ordinal);
    private readonly Dictionary<string, (double Seconds, int Calls)> _off = new(StringComparer.Ordinal);

    /// <summary>The seconds Revit's thread was blocked, summed.</summary>
    public double BlockedSeconds
    {
        get { lock (_lock) return Math.Round(_blocked.Values.Sum(v => v.Seconds), 3); }
    }

    /// <summary>The seconds Revit's thread waited for the architect, summed (a read's blocked time is its own time
    /// less this).</summary>
    public double ArchitectSeconds
    {
        get { lock (_lock) return _architect.Values.Sum(v => v.Seconds); }
    }

    /// <summary>Adds <paramref name="seconds"/> of Revit's thread blocked to <paramref name="name"/>.</summary>
    public void Blocked(string name, double seconds) => Add(_blocked, name, seconds);

    /// <summary>Adds <paramref name="seconds"/> of Revit's thread waiting for the architect to <paramref name="name"/>.</summary>
    public void Architect(string name, double seconds) => Add(_architect, name, seconds);

    /// <summary>Adds <paramref name="seconds"/> waited off Revit's thread to <paramref name="name"/>.</summary>
    public void OffThread(string name, double seconds) => Add(_off, name, seconds);

    /// <summary><paramref name="run"/>'s value, its time (a throw's too) added as blocked.</summary>
    public T Blocked<T>(string name, Func<T> run) => Timed(_blocked, name, run);

    /// <summary><paramref name="run"/>'s value, its time (a throw's too) added as the architect's.</summary>
    public T Architect<T>(string name, Func<T> run) => Timed(_architect, name, run);

    private T Timed<T>(Dictionary<string, (double, int)> into, string name, Func<T> run)
    {
        ArgumentNullException.ThrowIfNull(run);
        var start = Stopwatch.GetTimestamp();
        try
        {
            return run();
        }
        finally
        {
            Add(into, name, Stopwatch.GetElapsedTime(start).TotalSeconds);
        }
    }

    private void Add(Dictionary<string, (double Seconds, int Calls)> into, string name, double seconds)
    {
        ArgumentNullException.ThrowIfNull(name);
        lock (_lock)
        {
            var (s, c) = into.GetValueOrDefault(name);
            into[name] = (s + seconds, c + 1);
        }
    }

    /// <summary>The log's <c>ui_thread</c>: <c>blocked_s</c> (the sum), and per name, in each kind, its seconds (to
    /// the millisecond) and calls.</summary>
    public Dictionary<string, object?> ToLog()
    {
        lock (_lock)
        {
            static Dictionary<string, object?> Of(Dictionary<string, (double Seconds, int Calls)> d) =>
                d.OrderBy(kv => kv.Key, StringComparer.Ordinal).ToDictionary(
                    kv => kv.Key,
                    kv => (object?)new Dictionary<string, object?> { ["seconds"] = Math.Round(kv.Value.Seconds, 3), ["calls"] = kv.Value.Calls },
                    StringComparer.Ordinal);
            return new Dictionary<string, object?>(StringComparer.Ordinal)
            {
                ["blocked_s"] = Math.Round(_blocked.Values.Sum(v => v.Seconds), 3),
                ["blocked"] = Of(_blocked),
                ["architect"] = Of(_architect),
                ["off_thread"] = Of(_off),
            };
        }
    }
}
