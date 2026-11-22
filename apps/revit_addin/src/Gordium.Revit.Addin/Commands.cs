using System.IO;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Worker;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace Gordium.Revit.Addin;

/// <summary>Day 3: which build Revit loaded, and on which .NET runtime.</summary>
[Transaction(TransactionMode.ReadOnly)]
public sealed class AboutCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var app = commandData.Application.Application;
        var revit = $"{app.VersionName} ({app.VersionNumber}, build {app.VersionBuild})";
        Trial.Log("about", new Dictionary<string, object?>
        {
            ["revit"] = revit, ["build"] = Trial.Build(), ["runtime"] = Trial.Runtime(),
            ["addin"] = typeof(AboutCommand).Assembly.Location,
        });
        TaskDialog.Show("Gordium",
            $"Revit: {revit}\nAdd-in build: {Trial.Build()}\nRuntime: {Trial.Runtime()}\n\nLogged to {Trial.LogPath()}");
        return Result.Succeeded;
    }
}

/// <summary>Day 4: starts the worker (or reuses the running one), says hello, checks conformance scene 01 (the box
/// house) with <c>check_site</c>, and compares every row with the scene's hand-worked verdicts.</summary>
[Transaction(TransactionMode.ReadOnly)]
public sealed class CheckBoxHouseCommand : IExternalCommand
{
    private const string Scene = "01_box_house";

    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var log = new Dictionary<string, object?> { ["scene"] = Scene };
        try
        {
            // the worker client is async; run it off Revit's thread and wait, so no await resumes on Revit's UI thread
            var report = Task.Run(() => RunAsync(log)).GetAwaiter().GetResult();
            Trial.Log("check_box_house", log);
            TaskDialog.Show("Gordium: box house", report);
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            Trial.Log("check_box_house", log);
            TaskDialog.Show("Gordium: box house", $"Failed: {e.GetType().Name}\n{e.Message}");
            message = e.Message;
            return Result.Failed;
        }
    }

    private static async Task<string> RunAsync(Dictionary<string, object?> log)
    {
        var clone = Trial.Clone();
        var sw = Stopwatch.StartNew();
        // the session's one worker, started through Trial's lock (never two, never one left running unseen)
        var worker = await Trial.WorkerAsync().ConfigureAwait(false);
        log["start_and_hello_s"] = sw.Elapsed.TotalSeconds;
        log["worker_pid"] = worker.ProcessId;

        sw.Restart();
        var about = await worker.HelloAsync().ConfigureAwait(false);
        log["hello_s"] = sw.Elapsed.TotalSeconds;
        log["about"] = new Dictionary<string, object?>
        {
            ["protocol"] = about.Protocol, ["site_schema"] = about.SiteSchema,
            ["worker_fingerprint"] = about.WorkerFingerprint, ["rulebook"] = about.Rulebook,
        };

        // the scene's facts and verdicts are worked out by the conformance suite in Python, never copied here
        var scene = JsonNode.Parse(Trial.RunPython(clone,
            "import json; from design_checker import conformance as c; s = c.scenes()['" + Scene + "']; " +
            "print(json.dumps({'facts': c.facts(s), 'expected': c.expected_verdicts(s)}))"))!;
        var site = JsonNode.Parse(File.ReadAllText(
            Path.Combine(clone, "test_data", "host_conformance", "expected", Scene + ".site.json"), Encoding.UTF8))!;

        sw.Restart();
        var result = await worker.CheckSiteAsync(site, scene["facts"]!).ConfigureAwait(false);
        log["check_site_s"] = sw.Elapsed.TotalSeconds;

        var expected = scene["expected"]!.AsObject().ToDictionary(kv => kv.Key, kv => kv.Value!.GetValue<string>());
        var got = result.Items.ToDictionary(i => i.Id, i => i.StatusWord);
        var differences = new List<string>();
        foreach (var (id, word) in expected)
        {
            if (!got.TryGetValue(id, out var mine))
                differences.Add($"{id}: expected {word}, row missing");
            else if (mine != word)
                differences.Add($"{id}: expected {word}, got {mine}");
        }
        differences.AddRange(got.Keys.Where(id => !expected.ContainsKey(id)).Select(id => $"{id}: row not expected ({got[id]})"));
        log["rows"] = got.Count;
        log["expected_rows"] = expected.Count;
        log["state"] = result.State.ToString();
        log["summary"] = result.Summary;
        log["matches"] = differences.Count == 0;
        log["differences"] = differences;

        var head = differences.Count == 0
            ? $"Every row matches the scene's hand-worked verdicts ({got.Count} rows)."
            : $"{differences.Count} rows differ from the hand-worked verdicts:\n" + string.Join("\n", differences.Take(15));
        return $"{head}\n\nState: {result.State} · {result.Summary}\n" +
               $"Worker pid {worker.ProcessId}, protocol {about.Protocol}\n" +
               $"Check took {(double)log["check_site_s"]!:0.00} s\n\nLogged to {Trial.LogPath()}";
    }
}
