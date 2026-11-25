using System.IO;
using System.Reflection;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;
using RevitButton = Autodesk.Revit.UI.RibbonButton;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Gordium tab, built from <see cref="RibbonPlan"/> (docs/revit/ui_design_pass.md section 2.2; UI polish change
/// 48): Check (Check project, Set up), Results (Results, Summary), Help (About, and the Trial pull-down only in a trial
/// build or with <c>GORDIUM_TRIAL=1</c>). Each button's 16 and 32 px icons are drawn by <see cref="RibbonIcons"/> in Revit's theme;
/// Revit doesn't switch an add-in's images by theme, so they are swapped on ThemeChanged (as Autodesk's own sample
/// does: The Building Coder, "Dark Icons", 2023). The request files the trial runs by (App's Idling handler) never
/// depend on a button: they work with or without the Trial panel.
/// </summary>
internal static class Ribbon
{
#if GORDIUM_TRIAL_BUILD
    /// <summary>A trial build (install_trial_addin.ps1 builds one, <c>-p:GordiumTrial=true</c>): the Trial panel always.</summary>
    internal const bool TrialBuild = true;
#else
    /// <summary>Not a trial build: the Trial panel only with <c>GORDIUM_TRIAL=1</c>.</summary>
    internal const bool TrialBuild = false;
#endif

    /// <summary>The command each button runs, by its id.</summary>
    private static readonly Dictionary<string, Type> Commands = new(StringComparer.Ordinal)
    {
        [RibbonPlan.CheckProject] = typeof(CheckProjectCommand),
        [RibbonPlan.MarkFacts] = typeof(MarkForEgressCommand),        // opens the Setup form in the pane
        [RibbonPlan.Panel] = typeof(TogglePanelCommand),
        [RibbonPlan.Summary] = typeof(SaveSummaryCommand),
        [RibbonPlan.About] = typeof(AboutCommand),
        [RibbonPlan.CheckBoxHouse] = typeof(CheckBoxHouseCommand),
        [RibbonPlan.RecordScenes] = typeof(RecordScenesCommand),
        [RibbonPlan.ReadInside] = typeof(ReadInteriorCommand),
        [RibbonPlan.RecordHouses] = typeof(RecordHousesCommand),
    };

    private static readonly List<(RevitButton Button, string Icon)> Made = [];
    private static readonly Dictionary<(string, int, PanelTheme), ImageSource> Images = [];
    private static PanelTheme _theme = PanelTheme.Light;

    /// <summary>Whether this session shows the Trial panel.</summary>
    internal static bool TrialOn() =>
        RibbonPlan.TrialOn(TrialBuild, Environment.GetEnvironmentVariable(RibbonPlan.TrialVariable));

    /// <summary>Makes the tab, its panels and buttons, with the icons of Revit's current theme.</summary>
    internal static void Build(UIControlledApplication app)
    {
        try
        {
            app.CreateRibbonTab(RibbonPlan.Tab);
        }
        catch (Autodesk.Revit.Exceptions.ArgumentException)
        {
            // the tab already exists (another Gordium build loaded): add the panels to it
        }
        try
        {
            _theme = Theme();
        }
        catch (Exception x)       // a theme that can't be read: the light icons, and the log says why
        {
            Trial.Log("ribbon", new Dictionary<string, object?> { ["theme"] = $"{x.GetType().Name}: {x.Message}" });
        }
        var trial = TrialOn();
        foreach (var plan in RibbonPlan.Panels(trial))
        {
            var panel = app.CreateRibbonPanel(RibbonPlan.Tab, plan.Name);
            foreach (var b in plan.Buttons)
                Add(b, data => panel.AddItem(data) as PushButton);
            if (plan.Pulldown is { } menu)
            {
                try
                {
                    var data = new PulldownButtonData(menu.Id, menu.Text)
                    {
                        ToolTip = menu.ToolTip, Image = Image(menu.Icon, 16, _theme), LargeImage = Image(menu.Icon, 32, _theme),
                    };
                    if (panel.AddItem(data) is PulldownButton made)
                    {
                        Made.Add((made, menu.Icon));
                        foreach (var b in menu.Buttons)
                            Add(b, made.AddPushButton);
                    }
                }
                catch (Exception x)       // a pull-down that can't be made never takes the other buttons down
                {
                    Trial.Log("ribbon", new Dictionary<string, object?> { ["button"] = menu.Id, ["error"] = $"{x.GetType().Name}: {x.Message}" });
                }
            }
        }
        Trial.Log("ribbon", new Dictionary<string, object?>
        {
            ["trial"] = trial, ["trial_build"] = TrialBuild, ["theme"] = _theme.ToString(),
            ["buttons"] = Made.Select(m => m.Button.Name).ToList(),
        });
    }

    /// <summary>One push button made by <paramref name="add"/> (a panel's AddItem, or a pull-down's AddPushButton).</summary>
    private static void Add(Gordium.Revit.Reading.RibbonButton b, Func<PushButtonData, PushButton?> add)
    {
        try
        {
            var data = new PushButtonData(b.Id, b.Text, Assembly.GetExecutingAssembly().Location, Commands[b.Id].FullName)
            {
                ToolTip = b.ToolTip,
                LongDescription = b.LongDescriptionText,
                Image = Image(b.Icon, 16, _theme),
                LargeImage = Image(b.Icon, 32, _theme),
            };
            if (b.AnyTime)
                data.AvailabilityClassName = typeof(AnyTime).FullName;
            if (add(data) is { } made)
                Made.Add((made, b.Icon));
        }
        catch (Exception x)       // one button that can't be made never takes the others (or the add-in) down
        {
            Trial.Log("ribbon", new Dictionary<string, object?> { ["button"] = b.Id, ["error"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    /// <summary>Revit's ThemeChanged: the buttons' icons swapped to the new theme's. Never throws out of Revit's event.</summary>
    internal static void OnThemeChanged(object? sender, Autodesk.Revit.UI.Events.ThemeChangedEventArgs e)
    {
        try
        {
            var theme = Theme();
            if (theme == _theme)
                return;
            _theme = theme;
            foreach (var (button, icon) in Made)
            {
                button.Image = Image(icon, 16, theme);
                button.LargeImage = Image(icon, 32, theme);
            }
        }
        catch (Exception x)       // never out of Revit's event
        {
            Trial.Log("ribbon", new Dictionary<string, object?> { ["theme"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    private static PanelTheme Theme() => PanelLook.OfRevit(UIThemeManager.CurrentTheme);

    /// <summary>An icon as WPF reads it, drawn once per size and theme.</summary>
    private static ImageSource? Image(string icon, int size, PanelTheme theme)
    {
        if (Images.TryGetValue((icon, size, theme), out var made))
            return made;
        try
        {
            using var png = new MemoryStream(RibbonIcons.Png(icon, size, theme));
            var image = BitmapFrame.Create(png, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
            image.Freeze();
            return Images[(icon, size, theme)] = image;
        }
        catch (Exception x)       // an icon that can't be drawn leaves its button with words only, never no button
        {
            Trial.Log("ribbon", new Dictionary<string, object?> { ["icon"] = $"{icon} {size} {theme}", ["error"] = $"{x.GetType().Name}: {x.Message}" });
            return null;
        }
    }
}

/// <summary>Usable with no project open (Panel, About): Revit otherwise greys an add-in's button until one is.</summary>
public sealed class AnyTime : IExternalCommandAvailability
{
    public bool IsCommandAvailable(UIApplication applicationData, CategorySet selectedCategories) => true;
}

/// <summary>"Results": shows the Gordium results pane, or hides it when it is showing. Revit keeps where it is docked.</summary>
[Transaction(TransactionMode.ReadOnly)]
public sealed class TogglePanelCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        try
        {
            var pane = commandData.Application.GetDockablePane(ResultsPane.Id);
            if (pane.IsShown())
                pane.Hide();
            else
                pane.Show();
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            Trial.Log("results_panel", new Dictionary<string, object?> { ["toggle"] = $"{e.GetType().Name}: {e.Message}" });
            message = PaneWords.PaneWontOpen;
            return Result.Failed;
        }
    }
}
