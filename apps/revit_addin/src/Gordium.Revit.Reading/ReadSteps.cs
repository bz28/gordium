using System.Diagnostics;

namespace Gordium.Revit.Reading;

/// <summary>
/// How long each step of a Revit read took, and how much it read (the trial log's <c>read_steps</c>; README, "The
/// results log"). Only for finding out where a slow read spends its time (Snowdon Towers froze Revit 408 s inside the
/// read, 2026-11-22): it is never part of a record, never sent to the worker, and changes nothing that is read.
/// The Revit layer reaches it through <see cref="Current"/>, set for one read by <see cref="Begin"/> on Revit's own
/// thread (thread-static: nothing else sees it); with none set, every call here does nothing. Cheap: a timestamp per
/// step and a dictionary add, never a log line per element.
/// </summary>
public sealed class ReadSteps
{
    [ThreadStatic] private static ReadSteps? current;

    private readonly Dictionary<string, (long Ticks, long Calls)> times = new(StringComparer.Ordinal);
    private readonly Dictionary<string, long> counts = new(StringComparer.Ordinal);
    private readonly Dictionary<string, long> maxes = new(StringComparer.Ordinal);
    private readonly List<LinkStep> links = [];

    /// <summary>The steps being kept on this thread, or null (then nothing is kept).</summary>
    public static ReadSteps? Current => current;

    /// <summary>Keeps this thread's steps in <paramref name="steps"/> until the scope is disposed (the one kept
    /// before, if any, then kept again).</summary>
    public static IDisposable Begin(ReadSteps steps)
    {
        var before = current;
        current = steps;
        return new Restore(before);
    }

    private sealed class Restore(ReadSteps? before) : IDisposable
    {
        private bool done;

        public void Dispose()
        {
            if (done)
                return;
            done = true;
            current = before;
        }
    }

    /// <summary>A timed step: its seconds (and one call) added when disposed, to the steps kept when it began.</summary>
    public static Timer Step(string name) => current is { } s ? new Timer(s, name, Stopwatch.GetTimestamp()) : default;

    /// <summary><paramref name="read"/>'s value, the time it took added to step <paramref name="name"/>.</summary>
    public static T Time<T>(string name, Func<T> read)
    {
        using var _ = Step(name);
        return read();
    }

    /// <summary>Adds <paramref name="n"/> to the count <paramref name="name"/>.</summary>
    public static void Count(string name, long n = 1)
    {
        if (current is { } s)
            s.counts[name] = s.counts.GetValueOrDefault(name) + n;
    }

    /// <summary>Keeps the largest <paramref name="n"/> seen under <paramref name="name"/>.</summary>
    public static void Max(string name, long n)
    {
        if (current is { } s && (!s.maxes.TryGetValue(name, out var m) || n > m))
            s.maxes[name] = n;
    }

    /// <summary>One linked model read: its name, how deep (1 for a link of the project), its seconds (its own links'
    /// included) and its elements (its own, not its links').</summary>
    public static void Link(string name, int depth, double seconds, int elements)
    {
        current?.links.Add(new LinkStep(name, depth, seconds, elements));
    }

    /// <summary>The faces and edges of a read's geometry items, instances' items included.</summary>
    public static (long Solids, long Faces, long Edges, long Meshes) Tally(IReadOnlyList<GeometryItem>? items)
    {
        long solids = 0, faces = 0, edges = 0, meshes = 0;
        void Walk(IReadOnlyList<GeometryItem>? list)
        {
            foreach (var i in list ?? [])
                switch (i)
                {
                    case SolidItem s:
                        solids++;
                        faces += s.Faces.Count;
                        edges += s.Edges.Count;
                        break;
                    case MeshItem:
                        meshes++;
                        break;
                    case InstanceItem inner:
                        Walk(inner.Items);
                        break;
                }
        }
        Walk(items);
        return (solids, faces, edges, meshes);
    }

    /// <summary>Adds <see cref="Tally"/>'s counts under <c>&lt;prefix&gt;.solids</c>, <c>.faces</c>, <c>.edges</c>, <c>.meshes</c>.</summary>
    public static void CountGeometry(string prefix, IReadOnlyList<GeometryItem>? items)
    {
        if (current is null)
            return;
        var (solids, faces, edges, meshes) = Tally(items);
        Count(prefix + ".solids", solids);
        Count(prefix + ".faces", faces);
        Count(prefix + ".edges", edges);
        Count(prefix + ".meshes", meshes);
    }

    internal void Add(string name, long ticks)
    {
        var (t, c) = times.GetValueOrDefault(name);
        times[name] = (t + ticks, c + 1);
    }

    /// <summary>The steps as the log writes them: each timed step's seconds (to the millisecond) and calls, each count,
    /// each largest, by name; and each link read, in the order read.</summary>
    public Dictionary<string, object?> ToLog() => new()
    {
        ["steps"] = times.OrderBy(p => p.Key, StringComparer.Ordinal).ToDictionary(p => p.Key, p => (object)new Dictionary<string, object>
        {
            ["seconds"] = Seconds(p.Value.Ticks), ["calls"] = p.Value.Calls,
        }),
        ["counts"] = counts.OrderBy(p => p.Key, StringComparer.Ordinal).ToDictionary(p => p.Key, p => p.Value),
        ["max"] = maxes.OrderBy(p => p.Key, StringComparer.Ordinal).ToDictionary(p => p.Key, p => p.Value),
        ["links"] = links.Select(l => new Dictionary<string, object>
        {
            ["link"] = l.Name, ["depth"] = l.Depth, ["seconds"] = Math.Round(l.Seconds, 3), ["elements"] = l.Elements,
        }).ToList(),
    };

    internal static double Seconds(long ticks) => Math.Round((double)ticks / Stopwatch.Frequency, 3);

    private sealed record LinkStep(string Name, int Depth, double Seconds, int Elements);

    /// <summary>A step being timed (<see cref="Step"/>); the default one times nothing.</summary>
    public readonly struct Timer : IDisposable
    {
        private readonly ReadSteps? owner;
        private readonly string name;
        private readonly long start;

        internal Timer(ReadSteps owner, string name, long start)
        {
            this.owner = owner;
            this.name = name;
            this.start = start;
        }

        /// <summary>Adds the time since the step began.</summary>
        public void Dispose() => owner?.Add(name, Stopwatch.GetTimestamp() - start);
    }
}
