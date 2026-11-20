using System.Collections.Concurrent;
using Autodesk.Revit.UI;

namespace Gordium.Revit.Addin;

/// <summary>
/// What the results panel asks Revit to do (check again, select and zoom, open Project Information), run on
/// Revit's own thread in a valid API context: a click in the panel is a WPF event, outside it, so it is queued here
/// and run when Revit raises the one ExternalEvent made at startup. Nothing in the panel ever calls the Revit API
/// itself.
/// </summary>
internal sealed class PanelActions : IExternalEventHandler
{
    private readonly ConcurrentQueue<(string What, Action<UIApplication> Act)> _todo = new();
    private ExternalEvent? _event;

    /// <summary>The one queue, made in <see cref="App.OnStartup"/> (an ExternalEvent is made in an API context).</summary>
    internal static PanelActions? Current { get; private set; }

    internal static void Start()
    {
        var actions = new PanelActions();
        actions._event = ExternalEvent.Create(actions);
        Current = actions;
    }

    /// <summary>Queues an action; false (with Revit's word) when Revit refused to raise the event.</summary>
    internal bool Post(string what, Action<UIApplication> act, out string? refused)
    {
        _todo.Enqueue((what, act));
        var said = _event!.Raise();
        refused = said is ExternalEventRequest.Accepted or ExternalEventRequest.Pending ? null : said.ToString();
        return refused is null;
    }

    public void Execute(UIApplication app)
    {
        while (_todo.TryDequeue(out var job))
        {
            try
            {
                job.Act(app);
            }
            catch (Exception e)          // never out of Revit's event: said in the panel and logged
            {
                Trial.Log("results_panel", new Dictionary<string, object?>
                {
                    ["action"] = job.What, ["error"] = $"{e.GetType().Name}: {e.Message}",
                    ["where"] = e.StackTrace?.Split('\n').Take(8).Select(l => l.Trim()).ToList(),
                });
                ResultsPane.Say($"{job.What} failed: {e.GetType().Name}: {e.Message} (logged to {Trial.LogPath()})");
            }
        }
    }

    public string GetName() => "Gordium results panel";
}
