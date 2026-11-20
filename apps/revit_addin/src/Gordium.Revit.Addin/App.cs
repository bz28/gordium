using System.IO;
using System.Reflection;
using Autodesk.Revit.UI;
using Gordium.Worker;

namespace Gordium.Revit.Addin;

/// <summary>Revit starts this when it loads the add-in: it adds the Gordium tab and its buttons, and stops the
/// checker (the worker) when Revit closes.</summary>
public sealed class App : IExternalApplication
{
    internal const string Tab = "Gordium";

    /// <summary>The one worker this Revit session uses, started by the first button that needs it.</summary>
    internal static WorkerClient? Worker { get; set; }

    public Result OnStartup(UIControlledApplication application)
    {
        try
        {
            application.CreateRibbonTab(Tab);
        }
        catch (Autodesk.Revit.Exceptions.ArgumentException)
        {
            // the tab already exists (another Gordium build loaded): add the panel to it
        }
        var panel = application.CreateRibbonPanel(Tab, "Trial");
        var dll = Assembly.GetExecutingAssembly().Location;
        panel.AddItem(new PushButtonData("gordium_about", "About", dll, typeof(AboutCommand).FullName)
        {
            ToolTip = "Which build of the Gordium add-in Revit loaded, and on which .NET runtime",
        });
        panel.AddItem(new PushButtonData("gordium_check_box_house", "Check box\nhouse", dll,
                                         typeof(CheckBoxHouseCommand).FullName)
        {
            ToolTip = "Starts Gordium's checker and checks conformance scene 01 (the box house), comparing every " +
                      "row with the hand-worked verdicts",
        });
        panel.AddItem(new PushButtonData("gordium_record_scenes", "Record\nscenes", dll, typeof(RecordScenesCommand).FullName)
        {
            ToolTip = "Draws each conformance scene in a new Revit model, reads it as a check would, records it to " +
                      "test_data/host_conformance/recorded/revit/ and checks it by the suite's own rules",
        });
        application.Idling += OnIdling;
        Trial.Log("startup", new Dictionary<string, object?> { ["build"] = Trial.Build(), ["runtime"] = Trial.Runtime() });
        return Result.Succeeded;
    }

    /// <summary>A run asked for by file (RecordScenesCommand.RunRequestPath), so the trial can be driven with no
    /// click: taken (renamed) first, so it runs once even if it fails; every result goes to the log.</summary>
    private static void OnIdling(object? sender, Autodesk.Revit.UI.Events.IdlingEventArgs e)
    {
        var request = RecordScenesCommand.RunRequestPath;
        if (sender is not UIApplication ui || !File.Exists(request))
            return;
        var taken = request + ".taken";
        try
        {
            File.Move(request, taken, overwrite: true);
            RecordScenesCommand.Run(ui.Application, RecordScenesCommand.Requested(taken));
        }
        catch (Exception x)
        {
            Trial.Log("record_scenes", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
        }
    }

    public Result OnShutdown(UIControlledApplication application)
    {
        var worker = Worker;
        Worker = null;
        if (worker is not null)
        {
            int? pid = worker.ProcessId;
            worker.Dispose();
            Trial.Log("shutdown", new Dictionary<string, object?> { ["worker_stopped"] = pid });
        }
        return Result.Succeeded;
    }
}
