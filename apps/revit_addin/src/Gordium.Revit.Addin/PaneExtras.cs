using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Revit glue for the UI design pass's changes 13 to 15, beyond the pane's own view: Check project's status badge
/// (its LargeImage, Image and ToolTip swapped at runtime from <see cref="RibbonBadge"/>), the selection strip (Revit's
/// SelectionChanged, Revit 2023+, answered by <see cref="SelectionMap"/> in the pane's slot), and the compliance
/// summary's command (<see cref="SaveSummaryCommand"/>). It follows what the pane shows (ResultsView.Shown): every
/// count, status and word is the pane's rows'. It reads only; it never writes to the model.
/// </summary>
internal static class PaneExtras
{
    private static PushButton? _check;
    private static PanelTheme _theme = PanelTheme.Light;
    private static BadgeState _badge = RibbonBadge.Of(null, default);
    private static ResultsView? _view;
    private static SelectionMap? _map;

    // the selection the strip answers (in the project shown), and whether it is showing
    private static IReadOnlyList<string> _selected = [];
    private static Dictionary<string, string?> _names = new(StringComparer.Ordinal);
    private static bool _stripOn;
    private static bool _all;

    // a selection the pane made itself (a result's Show): never answered by the strip
    private static (HashSet<long> Ids, DateTime At)? _own;

    /// <summary>What the pane shows now (null: nothing checked, or its rows taken down): what the summary is made of.</summary>
    internal static PanelContent? Content { get; private set; }

    /// <summary>At startup, after the ribbon is built and its theme handler added: finds Check project's button, and
    /// follows the pane, Revit's selection and its theme (after the ribbon's own icon swap, so the badge is drawn
    /// back on).</summary>
    internal static void Start(UIControlledApplication app)
    {
        try
        {
            _check = app.GetRibbonPanels(RibbonPlan.Tab).SelectMany(p => p.GetItems()).OfType<PushButton>()
                        .FirstOrDefault(b => b.Name == RibbonPlan.CheckProject);
            _theme = Theme();
        }
        catch (Exception x)       // no badge is no reason to lose the strip or the add-in
        {
            Trial.Log("pane_extras", new Dictionary<string, object?> { ["badge"] = $"{x.GetType().Name}: {x.Message}" });
        }
        ResultsView.Shown += OnShown;
        app.SelectionChanged += OnSelectionChanged;
        app.ThemeChanged += OnThemeChanged;
        Trial.Log("pane_extras", new Dictionary<string, object?> { ["check_button"] = _check is not null });
    }

    internal static void Stop(UIControlledApplication app)
    {
        ResultsView.Shown -= OnShown;
        app.SelectionChanged -= OnSelectionChanged;
        app.ThemeChanged -= OnThemeChanged;
    }

    private static PanelTheme Theme() => PanelLook.OfRevit(UIThemeManager.CurrentTheme);

    // ---- what the pane shows: the badge, and the strip answered again ---------------------------------------------

    private static void OnShown(ResultsView view, PanelContent? content)
    {
        try
        {
            if (!ReferenceEquals(_view, view))
            {
                _view = view;
                view.LayoutUpdated += (_, _) => HideOverSetup();
            }
            Content = content;
            _badge = content switch
            {
                null => RibbonBadge.Of(null, default, failed: true),
                { Model: null } => RibbonBadge.Of(null, content.When, missing: content.Missing.Count),
                _ => RibbonBadge.Of(content.Model, content.When),
            };
            ShowBadge();
            _map = content?.Model is { } model ? SelectionMap.Of(model, content.When) : null;
            if (_map is null)
                Hide();
            else if (_stripOn)
                Draw();                                   // the same selection, from this answer (stale: the clocks)
        }
        catch (Exception x)       // never out of the pane's redraw
        {
            Trial.Log("pane_extras", new Dictionary<string, object?> { ["shown"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    // ---- 13: the badge --------------------------------------------------------------------------------------------

    private static void ShowBadge()
    {
        if (_check is null)
            return;
        _check.LargeImage = Image(RibbonBadge.Png(_badge, 32, _theme));
        _check.Image = Image(RibbonBadge.Png(_badge, 16, _theme));
        _check.ToolTip = _badge.ToolTip;
    }

    /// <summary>Revit's ThemeChanged, after the ribbon's own swap to the plain icons: the badge drawn back, in the new theme.</summary>
    private static void OnThemeChanged(object? sender, Autodesk.Revit.UI.Events.ThemeChangedEventArgs e)
    {
        try
        {
            _theme = Theme();
            ShowBadge();
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("pane_extras", new Dictionary<string, object?> { ["theme"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    private static ImageSource Image(byte[] png)
    {
        using var stream = new MemoryStream(png);
        var image = BitmapFrame.Create(stream, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
        image.Freeze();
        return image;
    }

    // ---- 14: the selection strip ----------------------------------------------------------------------------------

    /// <summary>The pane is about to select <paramref name="ids"/> itself (a result's or a card's Show): that
    /// selection is the pane's, not the architect's, so the strip doesn't answer it (ResultsPane.ShowElements).</summary>
    internal static void OwnSelection(IEnumerable<ElementId> ids) => _own = ([.. ids.Select(i => i.Value)], DateTime.UtcNow);

    /// <summary>Revit's SelectionChanged (Revit 2023+): in the project whose results the pane shows, the results that
    /// mention what is selected, at the top of the pane; nothing selected, another project, or the pane's own
    /// selection puts it away. Never throws out of Revit's event.</summary>
    private static void OnSelectionChanged(object? sender, Autodesk.Revit.UI.Events.SelectionChangedEventArgs e)
    {
        try
        {
            if (_view is null || _map is null || Content is null)
                return;
            var doc = e.GetDocument();
            var ids = e.GetSelectedElements();
            if (_own is { } own && DateTime.UtcNow - own.At < TimeSpan.FromSeconds(5) && own.Ids.SetEquals(ids.Select(i => i.Value)))
            {
                _own = null;
                return;                                   // the pane's own: the strip stays as it was
            }
            if (doc is null || doc.Title != Content.Project || ids.Count == 0 || ids.Count > 5000)
            {
                Hide();
                return;
            }
            var uids = new List<string>();
            var names = new Dictionary<string, string?>(StringComparer.Ordinal);
            foreach (var id in ids)
                if (doc.GetElement(id) is { } el)
                {
                    uids.Add(el.UniqueId);
                    if (ids.Count == 1)
                        names[el.UniqueId] = Content.Labels.TryGetValue(el.UniqueId, out var l) ? l : CheckProjectCommand.Label(doc, el.UniqueId);
                }
            if (uids.Count == 0)
            {
                Hide();
                return;
            }
            _selected = uids;
            _names = names;
            _all = false;
            _stripOn = true;
            Draw();
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("pane_extras", new Dictionary<string, object?> { ["selection"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    private static void Draw()
    {
        if (_view is not { } view || _map is null || view.ShowsSetup)
            return;
        var answer = _map.Answer(_selected, uid => _names.TryGetValue(uid, out var n) ? n : null);
        view.SelectionSlot.Child = SelectionStrip.Build(answer, view.OpenResult, Hide, _all, () =>
        {
            _all = true;
            Draw();
        });
    }

    private static void Hide()
    {
        _stripOn = false;
        if (_view is not null)
            _view.SelectionSlot.Child = null;
    }

    /// <summary>The Setup form shown in the pane: the strip put away (it is about results).</summary>
    private static void HideOverSetup()
    {
        if (_view is { ShowsSetup: true, SelectionSlot.Child: not null })
            Hide();
    }
}

/// <summary>"Summary" (the UI design pass, change 15): the last check the pane shows as a printable HTML file the
/// architect saves (<see cref="ComplianceSummary"/>: the checker's rows and words only, headed "Not a permit or an
/// approval"), then opened in their browser to print or save as PDF. Refused, saying why, when nothing was checked or
/// the model changed after the check. Writes nothing to the model.</summary>
[Transaction(TransactionMode.ReadOnly)]
public sealed class SaveSummaryCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var content = PaneExtras.Content;
        if (content?.Model is not { } model || ComplianceSummary.Refusal(model, content.When) is not null)
        {
            Autodesk.Revit.UI.TaskDialog.Show("Gordium", ComplianceSummary.Refusal(content?.Model, content?.When ?? DateTime.Now)!);
            return Result.Succeeded;
        }
        var path = Ask(content.Project, content.When);
        if (path is null)
            return Result.Cancelled;
        try
        {
            File.WriteAllText(path, ComplianceSummary.Html(model, content.Project, content.When, DateTime.Now), new UTF8Encoding(false));
            Trial.Log("summary", new Dictionary<string, object?> { ["file"] = path, ["project"] = content.Project });
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
            return Result.Succeeded;
        }
        catch (Exception x)
        {
            Trial.Log("summary", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            message = $"The summary couldn't be saved: {x.Message}";
            return Result.Failed;
        }
    }

    private static string? Ask(string project, DateTime when)
    {
        var dialog = new Microsoft.Win32.SaveFileDialog
        {
            Title = "Save the compliance summary",
            FileName = ComplianceSummary.FileName(project, when),
            DefaultExt = ".html",
            Filter = "Web page, printable (*.html)|*.html",
            InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            AddExtension = true,
            OverwritePrompt = true,
        };
        return dialog.ShowDialog() == true ? dialog.FileName : null;
    }
}
