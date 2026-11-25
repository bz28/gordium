using System.IO;
using Autodesk.Revit.UI;
using Gordium.Worker;

namespace Gordium.Revit.Addin;

/// <summary>Revit starts this when it loads the add-in: it adds the Gordium tab and its buttons, and stops the
/// checker (the worker) when Revit closes.</summary>
public sealed class App : IExternalApplication
{
    /// <summary>The one worker this Revit session uses, started by the first button that needs it. Set and cleared
    /// only by Trial (WorkerAsync, StopWorker), under its lock.</summary>
    internal static WorkerClient? Worker { get; set; }

    public Result OnStartup(UIControlledApplication application)
    {
        // the Gordium tab: Check, Results, Help, and Trial only in a trial build or with GORDIUM_TRIAL=1 (the request
        // files below work either way: they never use a button)
        try
        {
            Ribbon.Build(application);
        }
        catch (Exception x)       // no tab is no reason to lose the results panel or the request files
        {
            Trial.Log("ribbon", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
        }
        // the results panel (Check my project's), in Revit's light or dark theme and following it, and the one
        // ExternalEvent its clicks run through on Revit's thread
        ResultsPane.FollowTheme();
        application.ThemeChanged += ResultsPane.OnThemeChanged;
        application.ThemeChanged += Ribbon.OnThemeChanged;
        ResultsPane.Register(application);
        PanelActions.Start();
        PaneExtras.Start(application);        // UI changes 13-15: the badge, the selection strip (after the ribbon's theme swap)
        // the results greyed when the checked project changes, taken down when it closes: never a stale pass
        application.ControlledApplication.DocumentChanged += ResultsPane.OnDocumentChanged;
        application.ControlledApplication.DocumentClosing += ResultsPane.OnDocumentClosing;
        application.Idling += OnIdling;
        Trial.Log("startup", new Dictionary<string, object?> { ["build"] = Trial.Build(), ["runtime"] = Trial.Runtime() });
        return Result.Succeeded;
    }

    /// <summary>A run asked for by file, so the trial can be driven with no click: the in-place source
    /// (InPlaceSource.RequestPath), the interior houses (RecordHousesCommand.RequestPath), a project checked
    /// (CheckProjectCommand.RequestPath), a model built from data (ModelBuild.RequestPath) or the scenes
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
        if (File.Exists(SetMarks.RequestPath))
        {
            try
            {
                var takenMarks = SetMarks.RequestPath + ".taken";
                File.Move(SetMarks.RequestPath, takenMarks, overwrite: true);
                SetMarks.Run(ui.Application, takenMarks);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("set_marks", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(ModelBuild.RequestPath))
        {
            try
            {
                var takenBuild = ModelBuild.RequestPath + ".taken";
                File.Move(ModelBuild.RequestPath, takenBuild, overwrite: true);
                ModelBuild.Run(ui.Application, takenBuild);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("build_model", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
            }
            return;
        }
        if (File.Exists(SwingCheck.RequestPath))
        {
            try
            {
                var takenSwing = SwingCheck.RequestPath + ".taken";
                File.Move(SwingCheck.RequestPath, takenSwing, overwrite: true);
                SwingCheck.Run(ui.Application, takenSwing);
            }
            catch (Exception x)       // never out of Revit's Idling event
            {
                Trial.Log("swing_check", new Dictionary<string, object?> { ["error"] = $"{x.GetType().Name}: {x.Message}" });
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
        application.ThemeChanged -= ResultsPane.OnThemeChanged;
        application.ThemeChanged -= Ribbon.OnThemeChanged;
        PaneExtras.Stop(application);
        var worker = Trial.StopWorker();
        if (worker is not null)
        {
            int? pid = worker.ProcessId;
            worker.Dispose();
            Trial.Log("shutdown", new Dictionary<string, object?> { ["worker_stopped"] = pid });
        }
        return Result.Succeeded;
    }
}
