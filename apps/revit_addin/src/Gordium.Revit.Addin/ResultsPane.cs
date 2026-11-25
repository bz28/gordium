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

    private static ResultsView View() => _view ??= new ResultsView(Zoom, Select, CheckAgain, OpenProjectInformation, Card, SetUp, _theme, SaveAnswers, MoreTime);

    /// <summary>"Save and check again" in the questions card (UI polish changes 22, 23): the answers written to Project
    /// Information in one transaction (one Ctrl+Z, named for Gordium like the Setup form's Save), then the project
    /// checked again; nothing is checked when a write is refused (the pane says why, and the answers stay chosen).</summary>
    private static void SaveAnswers(IReadOnlyList<MarkWrite> writes) => Post("Save the answers", ui =>
    {
        if (_checked is not { IsValidObject: true } doc)
        {
            Say("The project checked is closed: open it and click Check project.");
            return;
        }
        var (applied, refused, status) = RevitMarks.Write(doc, SetupWrites.FactsTransaction, writes);
        Trial.Log("answers", new Dictionary<string, object?>
        {
            ["document"] = doc.Title, ["transaction"] = SetupWrites.FactsTransaction, ["status"] = status,
            ["applied"] = applied, ["refused"] = refused,
        });
        if (refused.Count > 0 || status is not ("Committed" or "Nothing"))
        {
            Say(PaneWords.AnswersNotSaved(refused, applied.Count, status));
            return;
        }
        Say(applied.Count == 0 ? "" : $"Saved {applied.Count} (Ctrl+Z undoes it).");
        if (CheckRun.Start(ui, doc) is { } refusedCheck)
            Say(refusedCheck);
    });

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

    /// <summary>Shows the Setup form for <paramref name="doc"/> in the pane and brings the pane up (Revit's thread).</summary>
    internal static void ShowSetup(UIApplication ui, Document doc, SetupScreen screen, SetupDraft draft, SetupHandlers handlers,
                                   string? notice, HashSet<string> open)
    {
        _checked = doc;
        if (!CheckRun.Flow.Running)
            View().EndProgress();
        View().ShowSetup(doc.Title, screen, draft, handlers, notice, open);
        ui.GetDockablePane(Id).Show();
    }

    /// <summary>Whether the pane shows the Setup form now.</summary>
    internal static bool ShowsSetup() => _view?.ShowsSetup == true;

    /// <summary>The Setup form drawn again (the panel's thread): after a choice, or when the place's options arrive;
    /// only while the pane shows it.</summary>
    internal static void RedrawSetup(SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open) =>
        _view?.RedrawSetup(screen, draft, handlers, notice, open);

    /// <summary>A check that failed: the last check's rows taken down (never shown as this one's), and why. From any
    /// thread (put on the panel's).</summary>
    internal static void Failed(CheckFailure failure) => Ui(() =>
    {
        if (_view is null)
            return;
        if (!CheckRun.Flow.Running)
            _view.EndProgress();
        _view.Failed(failure);
    });

    /// <summary>The checker's progress line (its stage, as it says it), under the check's step.</summary>
    internal static void Step(string words) => _view?.Step(words);

    /// <summary>"Try again with more time": the next check's silence doubled, then the check.</summary>
    private static void MoreTime()
    {
        CheckRun.MoreTime();
        CheckAgain();
    }

    /// <summary>A line in the panel (a click's result, a problem), when the panel exists. From any thread.</summary>
    internal static void Say(string words) => Ui(() => _view?.Say(words));

    /// <summary>While Revit waits for the street edge's click: the pane says so, with Cancel (UI polish change 9: the
    /// status bar alone is easy to miss, and the pane looked frozen); drawn at once (the pick runs on Revit's thread).</summary>
    internal static void Picking(bool on)
    {
        if (_view is null)
            return;
        _view.Picking(on, CancelPick);
        if (on)
            _view.Dispatcher.Invoke(() => { }, System.Windows.Threading.DispatcherPriority.Render);
    }

    /// <summary>Cancel on the picking card: Esc to Revit's main window, as the status bar says (PickObject then ends
    /// with OperationCanceledException, its own way out).</summary>
    private static void CancelPick()
    {
        var main = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;
        if (main != IntPtr.Zero)
        {
            NativeKeys.PostMessage(main, NativeKeys.KeyDown, (IntPtr)NativeKeys.Escape, IntPtr.Zero);
            NativeKeys.PostMessage(main, NativeKeys.KeyUp, (IntPtr)NativeKeys.Escape, IntPtr.Zero);
        }
    }

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

    /// <summary>A check's failure (Revit's thread, in an API context): the pane brought into view, so its error card is
    /// seen even when the architect hid the pane during the check (the read failure's dialog did this before PR 5). Best
    /// effort: Revit refusing to show it never keeps the error card from being drawn (confirm round after 4077716d).</summary>
    internal static void Reveal(UIApplication ui)
    {
        try
        {
            ui.GetDockablePane(Id).Show();
        }
        catch (Exception e) when (e is Autodesk.Revit.Exceptions.ApplicationException or InvalidOperationException)
        {
            // the card is still drawn in the pane; the architect opens it from the ribbon
        }
    }

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

    /// <summary>Runs <paramref name="act"/> after the input Revit queued meanwhile (WPF runs Background work only once
    /// no input is pending): a click made while Revit's thread was busy (Cancel during the read) is handled first.</summary>
    internal static void AfterInput(Action act) =>
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
            Say("The Gordium add-in didn't start its pane's actions: restart Revit.");
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
            {
                _view.MarkStale();
                SetupRun.Changed(doc);                       // the Setup form shown: its facts read again
            }
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
            Failed(CheckFailures.Closed());
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("results_panel", new Dictionary<string, object?> { ["document_closing"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    internal static void OpenProjectInformation() => Post("Open Project Information", ui =>
    {
        var id = RevitCommandId.LookupPostableCommandId(PostableCommand.ProjectInformation);
        if (id is null || !ui.CanPostCommand(id))
            Say("Open Manage > Project Information to fill in Gordium's marks.");
        else
            ui.PostCommand(id);
    });

    /// <summary>The results' "Set up the facts" (a check sent anyway): the Setup form for the project checked.</summary>
    private static void SetUp() => Post("Set up the facts", ui =>
    {
        if (_checked is { IsValidObject: true } doc)
            SetupRun.Show(ui, doc);
        else
            Say("The project checked is closed: open it and click Check project.");
    });

    private static void Zoom(ResultRow row) => Post("Show in model", ui => ShowElements(ui, row, zoom: true));

    /// <summary>A cause card's Show (its elements, or one room it names: selected and zoomed to), or Show and open
    /// Properties (selected and zoomed to, then Revit's Properties palette brought up, the mark to set named:
    /// CauseCards.AfterProperties). The API can't scroll Properties to a field, so the panel names it.</summary>
    private static void Card(CardRequest request) => Post(
        request.Action == CardAction.ShowAndProperties ? "Show and open Properties" : "Show the cause's elements", ui =>
        {
            var selected = ShowElements(ui, request.Elements, request.What, zoom: true);
            if (request.Action != CardAction.ShowAndProperties || selected == 0)
                return;
            ui.GetDockablePane(DockablePanes.BuiltInDockablePanes.PropertiesPalette).Show();
            Say(CauseCards.AfterProperties(request.Card, selected));
        });

    /// <summary>A row selected in the list (a click, Up or Down): its elements selected in Revit, the view not moved
    /// (design pass section 2.7: zoom is only an explicit Show), so Properties follows the panel.</summary>
    private static void Select(ResultRow row) => Post("Select in model", ui => ShowElements(ui, row, zoom: false));

    /// <summary>Selects the row's elements and, with <paramref name="zoom"/>, zooms to them, in the project that was
    /// checked, by their UniqueIds; says plainly when it can't (the project closed or not the active one, an element
    /// gone or not in this model). A row selected that names no element clears Revit's selection (what is selected is
    /// always the row's), quietly.</summary>
    private static void ShowElements(UIApplication ui, ResultRow row, bool zoom) => ShowElements(ui, row.Elements, row.Name, zoom);

    /// <summary>Selects <paramref name="uids"/> (each once) and, with <paramref name="zoom"/>, zooms to them, as
    /// the row's ShowElements does; <paramref name="what"/> names them in
    /// the panel's line. Gives how many were selected (0 when none could be).</summary>
    private static int ShowElements(UIApplication ui, IReadOnlyList<string> uids, string what, bool zoom)
    {
        var doc = _checked;
        if (doc is null || !doc.IsValidObject)
        {
            Say("The project checked is closed: open it and click Check again.");
            return 0;
        }
        var uidoc = ui.ActiveUIDocument;
        if (!zoom && uids.Count == 0)
        {
            if (uidoc is not null && uidoc.Document.Equals(doc))
            {
                PaneExtras.OwnSelection([]);
                uidoc.Selection.SetElementIds(new List<ElementId>());
            }
            return 0;
        }
        if (uidoc is null || !uidoc.Document.Equals(doc))
        {
            Say($"Switch to {doc.Title} to show it: the check was of that project.");
            return 0;
        }
        var found = new List<ElementId>();
        var asked = uids.Distinct(StringComparer.Ordinal).ToList();
        foreach (var uid in asked)
            if (doc.GetElement(uid) is { } e && !found.Contains(e.Id))
                found.Add(e.Id);
        var gone = asked.Count - found.Count;
        if (found.Count == 0)
        {
            Say("Its elements aren't in this model now (deleted since the check, in a linked model, or an area Gordium " +
                "read from the walls): click Check again.");
            return 0;
        }
        PaneExtras.OwnSelection(found);                    // the pane's own selection: the selection strip leaves it be
        uidoc.Selection.SetElementIds(found);
        if (zoom)
            uidoc.ShowElements(found);
        Say($"Selected {found.Count} element{(found.Count == 1 ? "" : "s")} for {what}" +
            (gone > 0 ? $"; {gone} not in this model now" : "") + (zoom ? "." : " (Show or Space zooms to them)."));
        return found.Count;
    }
}

/// <summary>The one Windows call the picking card's Cancel makes: Esc posted to Revit's main window.</summary>
internal static class NativeKeys
{
    internal const uint KeyDown = 0x0100;
    internal const uint KeyUp = 0x0101;
    internal const int Escape = 0x1B;

    [System.Runtime.InteropServices.DllImport("user32.dll", EntryPoint = "PostMessageW")]
    [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.Bool)]
    internal static extern bool PostMessage(IntPtr window, uint message, IntPtr wParam, IntPtr lParam);
}
