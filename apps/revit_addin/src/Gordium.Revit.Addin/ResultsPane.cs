using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>
/// Check project's results as a Revit dockable pane, titled "Gordium" (RibbonPlan.PaneTitle) (tabbed with Properties on first use), registered at
/// startup. It holds the one <see cref="ResultsView"/>, the document last checked, and the panel's Revit actions,
/// each run on Revit's thread through <see cref="PanelActions"/>: Check again, select a row's elements (and zoom, on Show), open
/// Project Information. A check asked for by file (CheckProjectCommand.RunRequest) never uses the pane.
/// </summary>
internal sealed class ResultsPane : IDockablePaneProvider
{
    /// <summary>The pane's id: never changed (Revit keeps where the architect docked it under this id).</summary>
    internal static readonly DockablePaneId Id = new(new Guid("6f4d2a1e-3b7c-4e58-9a0d-2c1b7e5f8a93"));

    private static ResultsView? _view;
    private static Document? _checked;

    internal static void Register(UIControlledApplication app) =>
        app.RegisterDockablePane(Id, RibbonPlan.PaneTitle, new ResultsPane());

    public void SetupDockablePane(DockablePaneProviderData data)
    {
        data.FrameworkElement = View();
        data.VisibleByDefault = false;
        data.InitialState = new DockablePaneState
        {
            DockPosition = DockPosition.Tabbed,
            TabBehind = DockablePanes.BuiltInDockablePanes.PropertiesPalette,
        };
    }

    private static ResultsView View() => _view ??= new ResultsView(Zoom, Select, CheckAgain, OpenProjectInformation, _theme);

    /// <summary>Revit's theme as the panel last read it (light until read).</summary>
    private static PanelTheme _theme = PanelTheme.Light;

    /// <summary>Follows Revit's light or dark theme (UIThemeManager.CurrentTheme): read at startup and on every
    /// ThemeChanged (Revit 2024+), the panel's token dictionary swapped when it differs. Never throws out of Revit's
    /// event: a theme that can't be read keeps the panel as it is, and says so in the log.</summary>
    internal static void FollowTheme()
    {
        try
        {
            var theme = PanelLook.OfRevit(UIThemeManager.CurrentTheme);
            if (theme == _theme && _view is not null)
                return;
            _theme = theme;
            _view?.UseTheme(theme);
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("results_panel", new Dictionary<string, object?> { ["theme"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    /// <summary>Revit's ThemeChanged: the UI theme or the canvas theme changed; the panel follows the UI theme.</summary>
    internal static void OnThemeChanged(object? sender, Autodesk.Revit.UI.Events.ThemeChangedEventArgs e) => FollowTheme();

    /// <summary>Shows a check in the pane and brings the pane up (on Revit's thread: a command or a panel action).
    /// The check's progress ends first, unless a check is still running (an earlier one's redraw).</summary>
    internal static void Show(UIApplication ui, Document doc, PanelContent content)
    {
        _checked = doc;
        if (!CheckRun.Flow.Running)
            View().EndProgress();
        View().Show(content);
        ui.GetDockablePane(Id).Show();
    }

    /// <summary>A check that failed: the last check's rows taken down (never shown as this one's), and why. From any
    /// thread (put on the panel's).</summary>
    internal static void Failed(string words) => Ui(() =>
    {
        if (_view is null)
            return;
        if (!CheckRun.Flow.Running)
            _view.EndProgress();
        _view.Failed(words);
    });

    /// <summary>A line in the panel (a click's result, a problem), when the panel exists. From any thread.</summary>
    internal static void Say(string words) => Ui(() => _view?.Say(words));

    /// <summary>Runs <paramref name="act"/> on the panel's thread (Revit's: WPF and Revit share it): now when called
    /// there, else queued to it (a pool thread's refusal). Never calls Revit's API.</summary>
    internal static void Ui(Action act)
    {
        var dispatcher = _view?.Dispatcher ?? System.Windows.Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.CheckAccess())
            act();
        else
            dispatcher.BeginInvoke(act);
    }

    /// <summary>What the panel shows now, for a check's Cancel to go back to.</summary>
    internal static PanelHad Had() => _view?.Had ?? PanelHad.Nothing;

    /// <summary>A check began (Revit's thread, in an API context): the pane brought up, saying "Reading the
    /// model...", its button Cancel.</summary>
    internal static void Reading(UIApplication ui)
    {
        View().Progress(CheckStage.Reading, DateTime.Now);
        ui.GetDockablePane(Id).Show();
    }

    /// <summary>The read ended and the checker works: "Checking (... s)...", Cancel; Revit is free.</summary>
    internal static void Checking(DateTime since) => View().Progress(CheckStage.Checking, since);

    /// <summary>Runs <paramref name="act"/> once the panel has drawn what it was just given (WPF lays out and draws at
    /// Loaded and Render priority, before Background): the read that follows blocks Revit's thread, so its line must
    /// be on screen first.</summary>
    internal static void AfterDrawn(Action act) =>
        View().Dispatcher.BeginInvoke(System.Windows.Threading.DispatcherPriority.Background, act);

    /// <summary>A check cancelled: the panel back to what it showed before it (<see cref="ResultsView.Restore"/>).</summary>
    internal static void Cancelled(PanelHad had, string? why)
    {
        View().EndProgress();
        View().Restore(had, why);
    }

    /// <summary>Queues a Revit action; on a refusal (or no queue) <paramref name="refused"/> runs and the panel says so.
    /// From any thread (ExternalEvent.Raise may be called from any).</summary>
    internal static void Post(string what, Action<UIApplication> act, Action? refused = null)
    {
        if (PanelActions.Current is not { } actions)
        {
            refused?.Invoke();
            Say("The Gordium add-in didn't start its panel actions: restart Revit.");
            return;
        }
        if (actions.Post(what, act, refused) is { } said)
            Say($"Revit didn't take \"{what}\" ({said}): finish what Revit is doing, then click again.");
    }

    /// <summary>The header button: Cancel while a check runs (CheckWords.Button), else Check again, queued for Revit's
    /// thread (greyed until Revit takes it, so a double click never queues two).</summary>
    private static void CheckAgain()
    {
        if (CheckRun.Flow.Running)
        {
            CheckRun.Cancel();
            return;
        }
        View().Busy(true);
        Post("Check again", ui =>
        {
            try
            {
                CheckProjectCommand.Check(ui);
            }
            finally
            {
                if (!CheckRun.Flow.Running)                // not begun (no project): usable again; begun: its end ends it
                    View().EndProgress();
            }
        }, refused: () => Ui(() => View().EndProgress()));  // refused: Check again usable again, as the words say
    }

    /// <summary>Revit's DocumentChanged: a change other than the check's own (ResultRows.ChangesTheCheck), to the
    /// project being checked, is counted (CheckFlow.Edited: an answer read before it arrives stale); to the project
    /// whose results are shown, greys them and says the model changed since the check (ResultRows.Stale).</summary>
    internal static void OnDocumentChanged(object? sender, Autodesk.Revit.DB.Events.DocumentChangedEventArgs e)
    {
        try
        {
            var doc = e.GetDocument();
            if (!ResultRows.ChangesTheCheck(e.GetTransactionNames().ToList(), committed: e.Operation == Autodesk.Revit.DB.Events.UndoOperation.TransactionCommitted))
                return;
            if (CheckRun.Reads(doc))
                CheckRun.Flow.Edited();
            if (_checked is not null && _view is not null && doc.Equals(_checked))
                _view.MarkStale();
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("results_panel", new Dictionary<string, object?> { ["document_changed"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    /// <summary>Revit's DocumentClosing: the project checked closing takes its rows down.</summary>
    internal static void OnDocumentClosing(object? sender, Autodesk.Revit.DB.Events.DocumentClosingEventArgs e)
    {
        try
        {
            if (CheckRun.Reads(e.Document))
                CheckRun.Cancel(CheckWords.Closed);           // the answer would be for a project no longer open
            if (_checked is null || !e.Document.Equals(_checked))
                return;
            _checked = null;
            Failed("The project checked was closed: open it and click Check project.");
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("results_panel", new Dictionary<string, object?> { ["document_closing"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    private static void OpenProjectInformation() => Post("Open Project Information", ui =>
    {
        var id = RevitCommandId.LookupPostableCommandId(PostableCommand.ProjectInformation);
        if (id is null || !ui.CanPostCommand(id))
            Say("Open Manage > Project Information to fill in Gordium's marks.");
        else
            ui.PostCommand(id);
    });

    private static void Zoom(ResultRow row) => Post("Show in model", ui => ShowElements(ui, row, zoom: true));

    /// <summary>A row selected in the list (a click, Up or Down): its elements selected in Revit, the view not moved
    /// (design pass section 2.7: zoom is only an explicit Show), so Properties follows the panel.</summary>
    private static void Select(ResultRow row) => Post("Select in model", ui => ShowElements(ui, row, zoom: false));

    /// <summary>Selects the row's elements and, with <paramref name="zoom"/>, zooms to them, in the project that was
    /// checked, by their UniqueIds; says plainly when it can't (the project closed or not the active one, an element
    /// gone or not in this model). A row selected that names no element clears Revit's selection (what is selected is
    /// always the row's), quietly.</summary>
    private static void ShowElements(UIApplication ui, ResultRow row, bool zoom)
    {
        var doc = _checked;
        if (doc is null || !doc.IsValidObject)
        {
            Say("The project checked is closed: open it and click Check again.");
            return;
        }
        var uidoc = ui.ActiveUIDocument;
        if (!zoom && row.Elements.Count == 0)
        {
            if (uidoc is not null && uidoc.Document.Equals(doc))
                uidoc.Selection.SetElementIds(new List<ElementId>());
            return;
        }
        if (uidoc is null || !uidoc.Document.Equals(doc))
        {
            Say($"Switch to {doc.Title} to show it: the check was of that project.");
            return;
        }
        var found = new List<ElementId>();
        foreach (var uid in row.Elements)
            if (doc.GetElement(uid) is { } e)
                found.Add(e.Id);
        var gone = row.Elements.Count - found.Count;
        if (found.Count == 0)
        {
            Say("Its elements aren't in this model now (deleted since the check, in a linked model, or an area Gordium " +
                "read from the walls): click Check again.");
            return;
        }
        uidoc.Selection.SetElementIds(found);
        if (zoom)
            uidoc.ShowElements(found);
        Say($"Selected {found.Count} element{(found.Count == 1 ? "" : "s")} for {row.Name}" +
            (gone > 0 ? $"; {gone} not in this model now" : "") + (zoom ? "." : " (Show or Space zooms to them)."));
    }
}
