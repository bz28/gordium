using Autodesk.Revit.UI;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>
/// What the results panel asks Revit to do (check again, select and zoom, open Project Information), run on
/// Revit's own thread in a valid API context: a click in the panel is a WPF event, outside it, so it is queued
/// (<see cref="ActionQueue{T}"/>, tested without Revit) and run when Revit raises the one ExternalEvent made at
/// startup. A request Revit refuses is taken back off the queue. Nothing in the panel calls the Revit API itself.
/// </summary>
internal sealed class PanelActions : IExternalEventHandler
{
    private readonly ActionQueue<UIApplication> _queue;
    private ExternalEvent? _event;

    private PanelActions() => _queue = new ActionQueue<UIApplication>(() =>
    {
        var said = _event!.Raise();
        return said is ExternalEventRequest.Accepted or ExternalEventRequest.Pending ? null : said.ToString();
    });

    /// <summary>The one queue, made in <see cref="App.OnStartup"/> (an ExternalEvent is made in an API context).</summary>
    internal static PanelActions? Current { get; private set; }

    internal static void Start()
    {
        var actions = new PanelActions();
        actions._event = ExternalEvent.Create(actions);
        Current = actions;
    }

    /// <summary>Queues an action; Revit's word when it refused (the action is then dropped and
    /// <paramref name="refused"/> run), else null.</summary>
    internal string? Post(string what, Action<UIApplication> act, Action? refused = null) => _queue.Post(what, act, refused);

    public void Execute(UIApplication app) => _queue.Run(app, (what, e) =>
    {
        // never out of Revit's event: said in the panel and logged
        Trial.Log("results_panel", new Dictionary<string, object?>
        {
            ["action"] = what, ["error"] = $"{e.GetType().Name}: {e.Message}",
            ["where"] = e.StackTrace?.Split('\n').Take(8).Select(l => l.Trim()).ToList(),
        });
        ResultsPane.Say($"{what} failed: {e.GetType().Name}: {e.Message} (logged to {Trial.LogPath()})");
    });

    public string GetName() => "Gordium results pane";
}
