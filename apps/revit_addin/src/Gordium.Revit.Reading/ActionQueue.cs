namespace Gordium.Revit.Reading;

/// <summary>
/// The results panel's queue of Revit actions (the add-in's PanelActions runs it from one ExternalEvent), without
/// Revit: <c>raise</c> is the event's Raise, giving null when Revit took the request or its word when it refused.
/// A refused action is taken back off the queue at once (never run later, unasked, with the next action Revit
/// takes) and its <c>refused</c> callback runs (the panel then re-enables what it greyed).
/// </summary>
/// <typeparam name="T">What each action is given when it runs (Revit's UIApplication).</typeparam>
public sealed class ActionQueue<T>
{
    private readonly Func<string?> _raise;
    private readonly LinkedList<(string What, Action<T> Act)> _todo = new();
    private readonly object _lock = new();

    public ActionQueue(Func<string?> raise) => _raise = raise ?? throw new ArgumentNullException(nameof(raise));

    /// <summary>The actions waiting to run.</summary>
    public int Count
    {
        get { lock (_lock) return _todo.Count; }
    }

    /// <summary>Queues an action and raises the event; null when taken, else Revit's word (the action then removed
    /// and <paramref name="refused"/> run).</summary>
    public string? Post(string what, Action<T> act, Action? refused = null)
    {
        ArgumentNullException.ThrowIfNull(act);
        LinkedListNode<(string, Action<T>)> node;
        lock (_lock)
            node = _todo.AddLast((what, act));
        var said = _raise();
        if (said is null)
            return null;
        lock (_lock)
            if (node.List is not null)
                _todo.Remove(node);                       // this exact action: never run later unasked
        refused?.Invoke();
        return said;
    }

    /// <summary>Runs every action waiting, in order; one that throws is given to <paramref name="failed"/> and the
    /// rest still run.</summary>
    public void Run(T app, Action<string, Exception> failed)
    {
        ArgumentNullException.ThrowIfNull(failed);
        while (true)
        {
            (string What, Action<T> Act) job;
            lock (_lock)
            {
                if (_todo.First is not { } first)
                    return;
                job = first.Value;
                _todo.RemoveFirst();
            }
            try
            {
                job.Act(app);
            }
            catch (Exception e)
            {
                failed(job.What, e);
            }
        }
    }
}
