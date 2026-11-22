namespace Gordium.Revit.Reading;

/// <summary>
/// What one read has already worked out, kept for the rest of that read so it is worked out once: the Revit layer's
/// per-element geometry (an element over 60 rooms was read and triangulated 60 times: Snowdon Towers, read_steps
/// 2026-11-22). Kept only while <see cref="Open"/>'s scope lasts (the inside read's rooms, openings, stairs and
/// railings, before anything in the model changes); with none open, every <see cref="Get"/> works its value out
/// afresh, as before. A value is kept only when <c>make</c> returns: one that throws is thrown again on the next ask,
/// worked out afresh. How many asks found a value kept (hits) and how many worked one out (misses) are handed to
/// the scope's <c>closed</c> when it ends (the Revit layer adds them to the log's read_steps; never part of a
/// record). One read at a time, on Revit's own thread.
/// </summary>
public sealed class ReadMemo<TKey, TValue> where TKey : notnull
{
    private Scope? open;

    /// <summary>Whether a scope is open (values kept).</summary>
    public bool IsOpen => open is not null;

    /// <summary>Keeps values until the scope is disposed; then every value kept is let go, <paramref name="closed"/>
    /// is told the scope's hits and misses, and the scope open before, if any, is open again with what it kept.</summary>
    public IDisposable Open(Action<long, long>? closed = null)
    {
        open = new Scope(this, open, closed);
        return open;
    }

    /// <summary>The value kept for <paramref name="key"/>, or <paramref name="make"/>'s, kept while a scope is open.</summary>
    public TValue Get(TKey key, Func<TValue> make)
    {
        if (open is not { } scope)
            return make();
        if (scope.Kept.TryGetValue(key, out var value))
        {
            scope.Hits++;
            return value;
        }
        scope.Misses++;
        value = make();
        scope.Kept[key] = value;
        return value;
    }

    private sealed class Scope(ReadMemo<TKey, TValue> memo, Scope? before, Action<long, long>? closed) : IDisposable
    {
        internal Dictionary<TKey, TValue> Kept { get; } = [];
        internal long Hits;
        internal long Misses;
        private bool done;

        public void Dispose()
        {
            if (done)
                return;
            done = true;
            memo.open = before;
            closed?.Invoke(Hits, Misses);
        }
    }
}
