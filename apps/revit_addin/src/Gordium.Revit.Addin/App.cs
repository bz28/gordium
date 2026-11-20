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
        var egress = application.CreateRibbonPanel(Tab, "Egress");
        egress.AddItem(new PushButtonData("gordium_mark_for_egress", "Mark for\negress", dll,
                                          typeof(MarkForEgressCommand).FullName)
        {
            ToolTip = "Adds Gordium's egress marks to this project if they aren't there, then lists every room, window " +
                      "and door with its marks, anything not set first",
        });
        egress.AddItem(new PushButtonData("gordium_read_interior", "Read\ninside", dll, typeof(ReadInteriorCommand).FullName)
        {
            ToolTip = "Reads this project's rooms and escape windows as Gordium's egress check would, and says what is " +
                      "left out and why (logged; nothing is sent to the checker yet)",
        });
        egress.AddItem(new PushButtonData("gordium_record_houses", "Record\nhouses", dll, typeof(RecordHousesCommand).FullName)
        {
            ToolTip = "Draws each hand-worked house of the interior step in a new Revit project, reads it, records it to " +
                      "test_data/interior_houses/recorded/revit/ and checks it against the hand-worked measures",
        });
        application.Idling += OnIdling;
        Trial.Log("startup", new Dictionary<string, object?> { ["build"] = Trial.Build(), ["runtime"] = Trial.Runtime() });
        return Result.Succeeded;
    }

    /// <summary>A run asked for by file while Revit is idle, so the trial needs no click: the interior houses
    /// (<see cref="RecordHousesCommand.RequestPath"/>). The file is taken (renamed) before it runs, so it runs once even
    /// if it fails; every result goes to the log, and nothing ever escapes Revit's Idling event.</summary>
    private static void OnIdling(object? sender, Autodesk.Revit.UI.Events.IdlingEventArgs e)
    {
        if (sender is not UIApplication ui)
            return;
        var request = RecordHousesCommand.RequestPath;
        if (!File.Exists(request))
            return;
        try
        {
            var taken = request + ".taken";
            File.Move(request, taken, overwrite: true);
            RecordHousesCommand.Run(ui.Application, RecordHousesCommand.Requested(taken));
        }
        catch (Exception x)
        {
            Trial.Log("record_houses", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
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
