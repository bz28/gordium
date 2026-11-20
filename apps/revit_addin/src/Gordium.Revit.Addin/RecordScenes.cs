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
    private const string Tool = "{0} ({1}), Gordium add-in (trial)";

    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        try
        {
            var lines = Run(commandData.Application.Application, Requested(RequestPath));
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

    /// <summary>Which scenes the button records (absent: every drawn scene).</summary>
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "record_request.json");

    /// <summary>A request to record while Revit is idle, with no click (App's Idling handler): taken (renamed) before
    /// it runs, so it runs once; its <c>scenes</c> as the button's request file.</summary>
    internal static string RunRequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "run_request.json");

    /// <summary>Records the scenes named (all drawn scenes for null); one line each, every result logged.</summary>
    internal static List<string> Run(Autodesk.Revit.ApplicationServices.Application app, HashSet<string>? wanted)
    {
        var lines = new List<string>();
        var clone = Trial.Clone();
        var worker = Trial.Worker();
        var tests = Path.Combine(clone, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests");
        var scenes = PythonOnce.Run(Trial.Python(clone), clone, [Path.Combine(tests, "scene_data.py")], TimeSpan.FromMinutes(2))
            .Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(l => JsonNode.Parse(l)!.AsObject()).ToList();
        foreach (var scene in scenes)
        {
            var name = scene["name"]!.GetValue<string>();
            if (wanted is not null && !wanted.Contains(name))
                continue;
            lines.Add(Record(app, clone, tests, worker, scene));
        }
        Trial.Log("record_scenes_done", new Dictionary<string, object?> { ["scenes"] = lines.Count });
        return lines;
    }

    /// <summary>A request with <c>"debug": true</c>: each scene's records written beside the log (debug\&lt;scene&gt;.json),
    /// every element's category, kind, box and geometry tree, to see what Revit gave the reader.</summary>
    internal static bool Debug { get; set; }

    private static void Dump(RevitModel model, string scene, string step)
    {
        static JsonNode Item(GeometryItem g) => g switch
        {
            SolidItem s => new JsonObject { ["solid"] = $"{s.Faces.Count} faces, {s.Edges.Count} edges" },
            MeshItem m => new JsonObject { ["mesh"] = $"{m.Triangles.Count} triangles, closed {m.IsClosed}" },
            InstanceItem i => new JsonObject { ["instance"] = i.Items is null ? null : new JsonArray(i.Items.Select(Item).ToArray()) },
            OtherItem o => new JsonObject { ["other"] = o.TypeName },
            _ => JsonValue.Create("linework")!,
        };
        var dir = Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "debug");
        Directory.CreateDirectory(dir);
        var elements = new JsonArray(model.Elements.Where(e => e.CategoryType == Reading.CategoryType.Model && !e.ViewSpecific)
            .Select(e => (JsonNode)new JsonObject
            {
                ["id"] = e.UniqueId, ["category"] = e.BuiltInCategory, ["kind"] = e.Kind.ToString(), ["mark"] = e.Mark.ToString(),
                ["box"] = e.BoundingBox is { } b ? $"{b.Min} .. {b.Max}" : null,
                ["geometry"] = e.GeometryFailed ? "failed" : e.Geometry is null ? null : new JsonArray(e.Geometry.Select(Item).ToArray()),
            }).ToArray());
        File.WriteAllText(Path.Combine(dir, $"{scene} ({step}).json"),
                          elements.ToJsonString(new JsonSerializerOptions { WriteIndented = true }), new UTF8Encoding(false));
    }

    internal static HashSet<string>? Requested(string path)
    {
        Debug = File.Exists(path) && JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))?["debug"]?.GetValue<bool>() == true;
        // no file, or a file naming no scenes ({}): every drawn scene
        return File.Exists(path) && JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))?["scenes"] is JsonArray scenes
            ? scenes.Select(s => s!.GetValue<string>()).ToHashSet()
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
            var drawn = SceneDraw.Draw(app, doc, scene);
            log["draw_s"] = sw.Elapsed.TotalSeconds;
            var steps = new JsonObject();
            foreach (var (step, _) in scene["steps"]!.AsObject())
            {
                if (step != "as drawn")
                    SceneDraw.Edit(doc, scene, step, drawn);       // moved in place, every UniqueId kept
                sw.Restart();
                var model = RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance);
                log[$"read_s ({step})"] = sw.Elapsed.TotalSeconds;
                if (Debug)
                    Dump(model, name, step);
                sw.Restart();
                // on Revit's thread: the lot is read (calling back into the API) before the reader's first wait, and
                // every wait inside it lets go of this thread (ConfigureAwait(false)), so blocking here can't deadlock
                var read = SiteReader.DescribeAsync(model, drawn.Facts.DeepClone().AsObject(), new WorkerLeftOut(worker))
                                     .GetAwaiter().GetResult();
                log[$"describe_s ({step})"] = sw.Elapsed.TotalSeconds;
                steps[step] = read.Site;
            }
            var recording = new JsonObject
            {
                ["host"] = "revit",
                ["scene"] = name,
                ["recorded"] = new JsonObject
                {
                    ["by"] = "Gordium add-in, Record scenes (Windows trial)",
                    ["date"] = DateTime.Now.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture),
                    ["tool"] = string.Format(System.Globalization.CultureInfo.InvariantCulture, Tool, app.VersionName, app.SubVersionNumber),
                },
                ["ids"] = new JsonObject(drawn.Ids.Select(p => KeyValuePair.Create(p.Key, (JsonNode?)p.Value))),
                ["steps"] = steps,
            };
            var path = Path.Combine(clone, "test_data", "host_conformance", "recorded", "revit", name + ".json");
            File.WriteAllText(path, recording.ToJsonString(new JsonSerializerOptions { WriteIndented = true, NewLine = "\n" }) + "\n",
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
            log["where"] = e.StackTrace?.Split('\n').Take(4).Select(l => l.Trim()).ToList();
            Trial.Log("record_scene", log);
            return $"{name}: failed ({e.GetType().Name}: {e.Message})";
        }
        finally
        {
            doc.Close(false);
        }
    }
}
