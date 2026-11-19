using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Gordium.Revit.Reading;
using Gordium.Worker;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace Gordium.Revit.Addin;

/// <summary>Days 5 to 8 (runbook section 4): each conformance scene drawn in a new Revit document, read by the
/// reader exactly as a check reads it (RevitRead, then SiteReader), recorded to
/// test_data/host_conformance/recorded/revit/&lt;scene&gt;.json, and judged by the suite's own rules
/// (check_recording.py). The scenes come from scene_data.py, the suite's own numbers. Which scenes: those named in
/// %LOCALAPPDATA%\Gordium\trial\record_request.json (<c>{"scenes": [...]}</c>), else every drawn scene; a scene the
/// drawer can't draw yet is skipped with its reasons, never recorded.</summary>
[Transaction(TransactionMode.Manual)]
public sealed class RecordScenesCommand : IExternalCommand
{
    private const string Tool = "Revit {0}, Gordium add-in (trial)";

    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var app = commandData.Application.Application;
        var lines = new List<string>();
        try
        {
            var clone = Trial.Clone();
            var worker = Trial.Worker();
            var tests = Path.Combine(clone, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests");
            var scenes = PythonOnce.Run(Trial.Python(clone), clone, [Path.Combine(tests, "scene_data.py")], TimeSpan.FromMinutes(2))
                .Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(l => JsonNode.Parse(l)!.AsObject()).ToList();
            var wanted = Requested();
            foreach (var scene in scenes)
            {
                var name = scene["name"]!.GetValue<string>();
                if (wanted is not null && !wanted.Contains(name))
                    continue;
                lines.Add(Record(app, clone, tests, worker, scene));
            }
            TaskDialog.Show("Gordium: record scenes", string.Join("\n", lines) + $"\n\nLogged to {Trial.LogPath()}");
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            Trial.Log("record_scenes", new Dictionary<string, object?> { ["error"] = $"{e.GetType().Name}: {e.Message}" });
            TaskDialog.Show("Gordium: record scenes", $"Failed: {e.GetType().Name}\n{e.Message}");
            message = e.Message;
            return Result.Failed;
        }
    }

    private static HashSet<string>? Requested()
    {
        var path = Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "record_request.json");
        return File.Exists(path)
            ? JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))!["scenes"]!.AsArray().Select(s => s!.GetValue<string>()).ToHashSet()
            : null;
    }

    private static string Record(Autodesk.Revit.ApplicationServices.Application app, string clone, string tests,
                                 WorkerClient worker, JsonObject scene)
    {
        var name = scene["name"]!.GetValue<string>();
        var log = new Dictionary<string, object?> { ["scene"] = name };
        var why = SceneDraw.Unsupported(scene);
        if (why.Count > 0)
        {
            log["skipped"] = why;
            Trial.Log("record_scene", log);
            return $"{name}: skipped ({string.Join("; ", why)})";
        }
        var sw = Stopwatch.StartNew();
        var doc = app.NewProjectDocument(UnitSystem.Imperial);
        try
        {
            var ids = SceneDraw.Draw(doc, scene);
            log["draw_s"] = sw.Elapsed.TotalSeconds;
            sw.Restart();
            var model = RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance);
            log["read_s"] = sw.Elapsed.TotalSeconds;
            sw.Restart();
            // on Revit's thread: the lot is read (calling back into the API) before the reader's first wait, and every
            // wait inside it lets go of this thread (ConfigureAwait(false)), so blocking here can't deadlock
            var read = SiteReader.DescribeAsync(model, scene["facts"]!.DeepClone().AsObject(), new WorkerLeftOut(worker))
                                 .GetAwaiter().GetResult();
            log["describe_s"] = sw.Elapsed.TotalSeconds;
            var recording = new JsonObject
            {
                ["host"] = "revit",
                ["scene"] = name,
                ["recorded"] = new JsonObject
                {
                    ["by"] = "Gordium add-in, Record scenes (Windows trial)",
                    ["date"] = DateTime.Now.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture),
                    ["tool"] = string.Format(System.Globalization.CultureInfo.InvariantCulture, Tool, app.VersionName),
                },
                ["ids"] = new JsonObject(ids.Select(p => KeyValuePair.Create(p.Key, (JsonNode?)p.Value))),
                ["steps"] = new JsonObject { ["as drawn"] = read.Site },
            };
            var path = Path.Combine(clone, "test_data", "host_conformance", "recorded", "revit", name + ".json");
            File.WriteAllText(path, recording.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n",
                              new UTF8Encoding(false));
            sw.Restart();
            var problems = JsonNode.Parse(PythonOnce.Run(Trial.Python(clone), clone,
                [Path.Combine(tests, "check_recording.py"), path], TimeSpan.FromMinutes(2)))!.AsArray();
            log["check_s"] = sw.Elapsed.TotalSeconds;
            log["problems"] = problems.Select(p => p!.ToJsonString()).ToList();
            Trial.Log("record_scene", log);
            return problems.Count == 0 ? $"{name}: OK" : $"{name}: {problems.Count} problem(s): {problems[0]}";
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            Trial.Log("record_scene", log);
            return $"{name}: failed ({e.GetType().Name}: {e.Message})";
        }
        finally
        {
            doc.Close(false);
        }
    }
}
