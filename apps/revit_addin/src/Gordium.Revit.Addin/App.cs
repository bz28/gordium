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
        var check = application.CreateRibbonPanel(Tab, "Check");
        check.AddItem(new PushButtonData("gordium_check_project", "Check my\nproject", dll, typeof(CheckProjectCommand).FullName)
        {
            ToolTip = "Checks this project against the City of Ithaca's zoning (the outside) and New York's egress rules " +
                      "(the inside) in one check, with the lot facts on Project Information (Gordium's marks, added on " +
                      "first use); the results open in the Gordium panel beside Properties: click a row to select and " +
                      "zoom to it. A fact not set and nothing is sent: the panel lists what to fill in",
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
        // the results panel (Check my project's), and the one ExternalEvent its clicks run through on Revit's thread
        ResultsPane.Register(application);
        PanelActions.Start();
        // the results greyed when the checked project changes, taken down when it closes: never a stale pass
        application.ControlledApplication.DocumentChanged += ResultsPane.OnDocumentChanged;
        application.ControlledApplication.DocumentClosing += ResultsPane.OnDocumentClosing;
        application.Idling += OnIdling;
        Trial.Log("startup", new Dictionary<string, object?> { ["build"] = Trial.Build(), ["runtime"] = Trial.Runtime() });
        return Result.Succeeded;
    }

    /// <summary>A run asked for by file, so the trial can be driven with no click: the in-place source
    /// (InPlaceSource.RequestPath), the interior houses (RecordHousesCommand.RequestPath), a project checked
    /// (CheckProjectCommand.RequestPath) or the scenes
    /// (RecordScenesCommand.RunRequestPath). Each is taken (renamed) first, so it runs once even if it fails; every result
    /// goes to the log, and nothing ever escapes Revit's Idling event.</summary>
    private static void OnIdling(object? sender, Autodesk.Revit.UI.Events.IdlingEventArgs e)
    {
        if (sender is not UIApplication ui)
            return;
        if (File.Exists(InPlaceSource.RequestPath))
        {
            try
            {
                var takenStep = InPlaceSource.RequestPath + ".taken";
                File.Move(InPlaceSource.RequestPath, takenStep, overwrite: true);
                InPlaceSource.Run(ui, takenStep);
            }
            catch (Exception x)       // never out of Revit's Idling event (review round 1)
            {
                Trial.Log("in_place_source", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(RecordHousesCommand.RequestPath))
        {
            try
            {
                var takenHouses = RecordHousesCommand.RequestPath + ".taken";
                File.Move(RecordHousesCommand.RequestPath, takenHouses, overwrite: true);
                RecordHousesCommand.Run(ui.Application, RecordHousesCommand.Requested(takenHouses));
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("record_houses", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(RealSite.RequestPath))
        {
            try
            {
                var takenSite = RealSite.RequestPath + ".taken";
                File.Move(RealSite.RequestPath, takenSite, overwrite: true);
                RealSite.Run(ui.Application, takenSite);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("real_site", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(ReadInteriorCommand.RequestPath))
        {
            try
            {
                var takenRead = ReadInteriorCommand.RequestPath + ".taken";
                File.Move(ReadInteriorCommand.RequestPath, takenRead, overwrite: true);
                ReadInteriorCommand.RunRequest(ui.Application, takenRead);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("read_interior", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(CheckProjectCommand.RequestPath))
        {
            try
            {
                var takenCheck = CheckProjectCommand.RequestPath + ".taken";
                File.Move(CheckProjectCommand.RequestPath, takenCheck, overwrite: true);
                CheckProjectCommand.RunRequest(ui.Application, takenCheck);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("check_project", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(DetailCheck.RequestPath))
        {
            try
            {
                File.Delete(DetailCheck.RequestPath);
                DetailCheck.Run(ui.Application);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("detail_check", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        var request = RecordScenesCommand.RunRequestPath;
        if (!File.Exists(request))
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
        application.ControlledApplication.DocumentChanged -= ResultsPane.OnDocumentChanged;
        application.ControlledApplication.DocumentClosing -= ResultsPane.OnDocumentClosing;
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
