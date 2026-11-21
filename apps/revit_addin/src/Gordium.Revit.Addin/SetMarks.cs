using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
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

    /// <summary>Places one Room (<c>NewRoom(level, UV)</c>) and names and numbers it; null when it stands where asked,
    /// else why, and it is taken back: a Room already there, one that isn't enclosed (no area), or one not in the last
    /// phase (the design the reader reads).</summary>
    private static string? Place(Document doc, RoomToPlace p, Phase last)
    {
        if (doc.GetElement(p.Level) is not Level level)
            return "its level isn't in the model";
        if (doc.GetRoomAtPoint(new XYZ(p.X, p.Y, level.ProjectElevation + 1), last) is { } there)
            return $"Room \"{there.Name}\" is already there";
        var room = doc.Create.NewRoom(level, new UV(p.X, p.Y));
        room.Name = p.Name;
        room.Number = p.Number;
        doc.Regenerate();
        var phase = room.get_Parameter(BuiltInParameter.ROOM_PHASE)?.AsElementId();
        var why = room.Area <= 0 ? "it isn't in an enclosed area (Revit gives it no area)"
            : phase is not null && phase != last.Id ? $"Revit put it in phase {doc.GetElement(phase)?.Name}, not the last ({last.Name})"
            : null;
        if (why is not null)
            doc.Delete(room.Id);
        return why;
    }

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
            // the Rooms to place first (an enclosed area the sheet names), each checked where it lands, then the marks
            var (places, placeRefused) = MarksRequest.Placements(request["place_rooms"] as JsonArray, RevitMarks.Model(doc));
            var placed = new List<string>();
            var notPlaced = new List<string>(placeRefused);
            if (places.Count > 0)
                using (var t = new Transaction(doc, "Gordium: the eval's Rooms (standing in for the architect)"))
                {
                    t.Start();
                    var last = doc.Phases.Cast<Phase>().Last();
                    foreach (var p in places)
                    {
                        var words = FormattableString.Invariant($"{p.Name} {p.Number} at ({p.X:0.###}, {p.Y:0.###})");
                        if (Place(doc, p, last) is { } why)
                            notPlaced.Add($"{words}: {why}");
                        else
                            placed.Add(words);
                    }
                    log["rooms_commit"] = t.Commit().ToString();
                }
            log["rooms_placed"] = placed;
            log["rooms_refused"] = notPlaced;
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
