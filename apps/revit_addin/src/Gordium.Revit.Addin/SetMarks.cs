using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Gordium.Revit.Reading;
using RevitApplication = Autodesk.Revit.ApplicationServices.Application;

namespace Gordium.Revit.Addin;

/// <summary>
/// The eval's marks written into a copy of a model, by request file (set_marks_request.json beside the trial log, read
/// while Revit is idle; the request's form and every decision: <see cref="MarksRequest"/>). Only a model and a copy under
/// the trial folder (<c>%LOCALAPPDATA%\Gordium\trial</c>) are opened and saved, never the architect's own files. Gordium's
/// marks are added to the copy first (as Mark for egress adds them), each write is done in one transaction, and every
/// entry written or refused is logged (<c>set_marks</c> in results.jsonl). It decides nothing.
/// </summary>
internal static class SetMarks
{
    internal static string RequestPath => Path.Combine(TrialDir, "set_marks_request.json");

    private static string TrialDir => Path.GetDirectoryName(Trial.LogPath())!;

    internal static void Run(RevitApplication app, string requestFile)
    {
        var log = new Dictionary<string, object?> { ["request"] = requestFile };
        Document? doc = null;
        try
        {
            var request = JsonNode.Parse(File.ReadAllText(requestFile, Encoding.UTF8))!.AsObject();
            var model = request["model"]?.GetValue<string>();
            var saveAs = request["save_as"]?.GetValue<string>();
            log["model"] = model;
            log["save_as"] = saveAs;
            if ((MarksRequest.PathProblem(model, TrialDir) ?? MarksRequest.PathProblem(saveAs, TrialDir)) is { } bad)
            {
                log["error"] = bad;
                return;
            }
            if (request["marks"] is not JsonArray marks || request["by"]?.GetValue<string>() is not { Length: > 0 } by)
            {
                log["error"] = "the request needs \"marks\" (a list) and \"by\" (who the marks stand in for)";
                return;
            }
            doc = app.OpenDocumentFile(model);
            var setup = RevitMarks.AddMarks(doc, app, MarkSetup.Plan(RevitMarks.Bindings(doc)));
            log["marks_added"] = setup.Select(s => $"{s.Action}: {s.Mark.Name}").ToList();
            var plan = MarksRequest.Plan(marks, RevitMarks.Model(doc), by, MarksRequest.Date(request["date"]));
            var applied = new List<string>();
            var refused = new List<string>(plan.Refused);
            using (var t = new Transaction(doc, "Gordium: the eval's marks (standing in for the architect)"))
            {
                t.Start();
                foreach (var w in plan.Writes)
                {
                    var p = doc.GetElement(w.Element)?.get_Parameter(w.Mark.Guid);
                    var done = p is { IsReadOnly: false } && (w.Mark.Kind switch
                    {
                        MarkValueKind.YesNo => p.Set(w.Value.Integer!.Value),
                        MarkValueKind.Length => p.Set(w.Value.Number!.Value),
                        _ => p.Set(w.Value.Text!),
                    });
                    (done ? applied : refused).Add($"{w.Label}: {w.Mark.Name} = {w.Value.Text ?? w.Value.Integer?.ToString() ?? w.Value.Number?.ToString()}" +
                                                   (done ? "" : p is null ? " (the element has no such parameter)" : " (Revit refused it)"));
                }
                log["commit"] = t.Commit().ToString();
            }
            log["applied"] = applied;
            log["refused"] = refused;
            doc.SaveAs(saveAs, new SaveAsOptions { OverwriteExistingFile = true });
            log["saved"] = saveAs;
            log["ok"] = true;
        }
        catch (Exception x)
        {
            log["error"] = $"{x.GetType().Name}: {x.Message}";
            log["where"] = x.StackTrace?.Split('\n').Take(6).Select(s => s.Trim()).ToList();
        }
        finally
        {
            doc?.Close(false);
            Trial.Log("set_marks", log);
        }
    }
}
