using System.Diagnostics;
using System.Globalization;
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
using RevitApplication = Autodesk.Revit.ApplicationServices.Application;

namespace Gordium.Revit.Addin;

/// <summary>
/// Interior conformance in Revit (docs/revit/revit_interior_reading_design.md, section 6; section 7, step 3): each
/// hand-worked house of the step drawn in a new Revit project by <see cref="HouseDraw"/>, read exactly as a check would
/// read it (<see cref="RevitInterior"/>, then <see cref="InteriorReader"/>), recorded to
/// test_data/interior_houses/recorded/revit/&lt;house&gt;.json, and judged by the same rules CI applies
/// (<c>python -m model_measurement.interior.recordings check</c>). Which houses: those named in
/// %LOCALAPPDATA%\Gordium\trial\interior_request.json (<c>{"houses": [...]}</c>), else every house of the step. The
/// earlier recording of a house is deleted before it is drawn, so a run that fails leaves no recording CI could take
/// for this one's. Asked for by the button, or by that file appearing while Revit is idle (App.OnIdling).
/// </summary>
[Transaction(TransactionMode.Manual)]
public sealed class RecordHousesCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        try
        {
            var lines = Run(commandData.Application.Application, Requested(RequestPath));
            TaskDialog.Show("Gordium: record interior houses", string.Join("\n", lines) + $"\n\nLogged to {Trial.LogPath()}");
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            Trial.Log("record_houses", new Dictionary<string, object?> { ["error"] = $"{e.GetType().Name}: {e.Message}" });
            TaskDialog.Show("Gordium: record interior houses", $"Failed: {e.GetType().Name}\n{e.Message}");
            message = e.Message;
            return Result.Failed;
        }
    }

    /// <summary>The request file: <c>{"houses": ["1_ranch_compliant", ...]}</c>, or <c>{}</c> for every house of the
    /// step. Written by whoever runs the trial; taken (renamed) by App.OnIdling before it runs, so it runs once.</summary>
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "interior_request.json");

    internal static HashSet<string>? Requested(string path) =>
        File.Exists(path) && JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8))?["houses"] is JsonArray houses
            ? houses.Select(h => h!.GetValue<string>()).ToHashSet()
            : null;

    /// <summary>Records the houses named (every house of the step for null): one line each, every result logged.</summary>
    internal static List<string> Run(RevitApplication app, HashSet<string>? wanted)
    {
        var clone = Trial.Clone();
        var python = Trial.Python(clone);
        var drawings = PythonOnce.Run(python, clone, ["-m", "model_measurement.interior.recordings", "draw"], TimeSpan.FromMinutes(2), Trial.PythonEnvironment(clone))
            .Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(l => JsonNode.Parse(l)!.AsObject()).ToList();
        if (wanted is not null && wanted.Except(drawings.Select(d => d["house"]!.GetValue<string>())).ToList() is { Count: > 0 } unknown)
            throw new InvalidOperationException("not a house of this step: " + string.Join(", ", unknown));
        var lines = new List<string>();
        foreach (var house in drawings)
        {
            if (wanted is null || wanted.Contains(house["house"]!.GetValue<string>()))
                lines.Add(Record(app, clone, python, house));
        }
        Trial.Log("record_houses_done", new Dictionary<string, object?> { ["houses"] = lines });
        return lines;
    }

    private static string Record(RevitApplication app, string clone, string python, JsonObject house)
    {
        var name = house["house"]!.GetValue<string>();
        var log = new Dictionary<string, object?> { ["house"] = name, ["not_drawn"] = house["not_drawn"]?.ToJsonString() };
        var path = Path.Combine(clone, "test_data", "interior_houses", "recorded", "revit", name + ".json");
        Document? doc = null;
        try
        {
            if (File.Exists(path))
                File.Delete(path);                            // never an earlier run's recording left as this one's
            var sw = Stopwatch.StartNew();
            doc = app.NewProjectDocument(UnitSystem.Imperial);
            var ids = HouseDraw.Draw(app, doc, house);
            log["draw_s"] = sw.Elapsed.TotalSeconds;
            sw.Restart();
            var model = RevitInterior.Model(doc);
            var read = InteriorReader.Read(model);
            log["read_s"] = sw.Elapsed.TotalSeconds;
            var recording = new JsonObject
            {
                ["host"] = "revit",
                ["house"] = name,
                ["step"] = 3,
                ["recorded"] = new JsonObject
                {
                    ["by"] = "Gordium add-in, Record interior houses (Windows trial)",
                    ["date"] = DateTime.Now.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture),
                    ["tool"] = $"{app.VersionName} ({app.SubVersionNumber}), Gordium add-in (trial)",
                },
                ["ids"] = new JsonObject(ids.Select(p => KeyValuePair.Create(p.Key, (JsonNode?)p.Value))),
                ["interior"] = read.Interior.DeepClone(),
                ["rooms_not_read"] = new JsonArray(read.RoomsNotRead.Select(w => (JsonNode?)w).ToArray()),
                ["openings_not_read"] = new JsonArray(read.OpeningsNotRead.Select(w => (JsonNode?)w).ToArray()),
                ["notes"] = new JsonArray(read.Notes.Select(n => (JsonNode)new JsonObject
                {
                    ["part"] = n.Part, ["field"] = n.Field, ["why"] = n.Why,
                }).ToArray()),
                ["evidence"] = read.Evidence.DeepClone(),
                ["revit_layer"] = new JsonArray(model.Interior!.Diagnostics.Select(d => (JsonNode?)d).ToArray()),
            };
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, recording.ToJsonString(new JsonSerializerOptions { WriteIndented = true, NewLine = "\n" }) + "\n",
                              new UTF8Encoding(false));
            sw.Restart();
            var problems = JsonNode.Parse(PythonOnce.Run(python, clone,
                ["-m", "model_measurement.interior.recordings", "check", path], TimeSpan.FromMinutes(2), Trial.PythonEnvironment(clone)))!.AsArray();
            log["check_s"] = sw.Elapsed.TotalSeconds;
            log["problems"] = problems.Select(p => p!.GetValue<string>()).ToList();
            log["notes"] = read.Notes.Select(n => $"{n.Part} {n.Field}: {n.Why}").ToList();
            log["rooms_not_read"] = read.RoomsNotRead;
            log["openings_not_read"] = read.OpeningsNotRead;
            log["evidence"] = read.Evidence.ToJsonString();
            log["revit_layer"] = model.Interior!.Diagnostics;
            Trial.Log("record_house", log);
            return problems.Count == 0 ? $"{name}: OK" : $"{name}: {problems.Count} problem(s): {problems[0]}";
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            log["where"] = e.StackTrace?.Split('\n').Take(6).Select(l => l.Trim()).ToList();
            Trial.Log("record_house", log);
            return $"{name}: failed ({e.GetType().Name}: {e.Message})";
        }
        finally
        {
            doc?.Close(false);
        }
    }
}

/// <summary>"Read inside": what the interior reader would send for the open project, and why anything is left out,
/// shown and logged (the description itself in the log). A reading only: nothing is sent to the checker yet, and the
/// one transaction it opens (Revit works out enclosed areas only in a document it can change) is rolled back.</summary>
[Transaction(TransactionMode.Manual)]
public sealed class ReadInteriorCommand : IExternalCommand
{
    public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
    {
        var doc = commandData.Application.ActiveUIDocument?.Document;
        if (doc is null || doc.IsFamilyDocument)
        {
            TaskDialog.Show("Gordium: read inside", "Open a project (not a family) to read its inside.");
            return Result.Cancelled;
        }
        var log = new Dictionary<string, object?> { ["document"] = doc.Title };
        try
        {
            var sw = Stopwatch.StartNew();
            var model = RevitInterior.Model(doc);
            var read = InteriorReader.Read(model);
            log["read_s"] = sw.Elapsed.TotalSeconds;
            log["rooms_not_read"] = read.RoomsNotRead;
            log["openings_not_read"] = read.OpeningsNotRead;
            log["notes"] = read.Notes.Select(n => $"{n.Part} {n.Field}: {n.Why}").ToList();
            log["evidence"] = read.Evidence.ToJsonString();
            log["revit_layer"] = model.Interior!.Diagnostics;
            log["interior"] = read.Interior.ToJsonString();
            Trial.Log("read_interior", log);
            var rooms = read.Interior["rooms"] is JsonArray r ? $"{r.Count} rooms read" : "Rooms not read: " + string.Join("; ", read.RoomsNotRead.Take(5));
            var openings = read.Interior["openings"] is JsonArray o ? $"{o.Count} windows and doors read" : "Openings not read: " + string.Join("; ", read.OpeningsNotRead.Take(5));
            var notes = string.Join("\n", read.Notes.Take(20).Select(n => $"- {n.Field}: {n.Why}"));
            TaskDialog.Show("Gordium: read inside", $"{rooms}\n{openings}\n\n{read.Notes.Count} values left out" +
                            (notes.Length > 0 ? ":\n" + notes : "") + $"\n\nLogged to {Trial.LogPath()}");
            return Result.Succeeded;
        }
        catch (Exception e)
        {
            log["error"] = $"{e.GetType().Name}: {e.Message}";
            Trial.Log("read_interior", log);
            TaskDialog.Show("Gordium: read inside", $"Failed: {e.GetType().Name}\n{e.Message}");
            message = e.Message;
            return Result.Failed;
        }
    }
}
