using System.IO;
using System.Reflection;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Gordium tab, built from <see cref="RibbonPlan"/> (docs/revit/ui_design_pass.md section 2.2): Check (Check
/// project, Mark facts), Results (Panel), Help (About), and the Trial panel only in a trial build or with
/// <c>GORDIUM_TRIAL=1</c>. Each button's 16 and 32 px icons are drawn by <see cref="RibbonIcons"/> in Revit's theme;
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
        [RibbonPlan.MarkFacts] = typeof(MarkForEgressCommand),        // the checklist in the pane comes later (PR 7)
        [RibbonPlan.Panel] = typeof(TogglePanelCommand),
        [RibbonPlan.About] = typeof(AboutCommand),
        [RibbonPlan.CheckBoxHouse] = typeof(CheckBoxHouseCommand),
        [RibbonPlan.RecordScenes] = typeof(RecordScenesCommand),
        [RibbonPlan.ReadInside] = typeof(ReadInteriorCommand),
        [RibbonPlan.RecordHouses] = typeof(RecordHousesCommand),
    };

    private static readonly List<(PushButton Button, string Icon)> Made = [];
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
        var dll = Assembly.GetExecutingAssembly().Location;
        foreach (var plan in RibbonPlan.Panels(trial))
        {
            var panel = app.CreateRibbonPanel(RibbonPlan.Tab, plan.Name);
            foreach (var b in plan.Buttons)
            {
                try
                {
                    var data = new PushButtonData(b.Id, b.Text, dll, Commands[b.Id].FullName)
                    {
                        ToolTip = b.ToolTip,
                        LongDescription = b.LongDescriptionText,
                        Image = Image(b.Icon, 16, _theme),
                        LargeImage = Image(b.Icon, 32, _theme),
                    };
                    if (b.AnyTime)
                        data.AvailabilityClassName = typeof(AnyTime).FullName;
                    if (panel.AddItem(data) is PushButton made)
                        Made.Add((made, b.Icon));
                }
                catch (Exception x)       // one button that can't be made never takes the others (or the add-in) down
                {
                    Trial.Log("ribbon", new Dictionary<string, object?> { ["button"] = b.Id, ["error"] = $"{x.GetType().Name}: {x.Message}" });
                }
            }
        }
        Trial.Log("ribbon", new Dictionary<string, object?>
        {
            ["trial"] = trial, ["trial_build"] = TrialBuild, ["theme"] = _theme.ToString(),
            ["buttons"] = Made.Select(m => m.Button.Name).ToList(),
        });
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

/// <summary>"Panel": shows the Gordium results panel, or hides it when it is showing. Revit keeps where it is docked.</summary>
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
            message = $"The Gordium panel couldn't be shown: {e.Message}";
            return Result.Failed;
        }
    }
}
