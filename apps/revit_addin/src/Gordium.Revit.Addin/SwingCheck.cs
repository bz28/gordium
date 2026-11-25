using System.IO;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Gordium.Revit.Reading;

namespace Gordium.Revit.Addin;

/// <summary>The trial's check of the door swing reading (docs/revit/revit_interior_reading_design.md, section 10,
/// "Which side a door swings into"), asked for by request file while Revit is idle:
/// <c>swing_check_request.json</c>, <c>{"model": "&lt;built .rvt&gt;", "data": "&lt;its build data .json&gt;"}</c>: a model
/// the add-in built from that data (build_model_request), each door flipped to the swing the data gives. The model is
/// opened in the background (never the window's document), read as a check reads it, and each door's swing side as its
/// plan symbol draws it (RouteReader.SwingSide) logged beside the side the data built it to (its <c>swing_dir</c>), with
/// its facing and hand. Then, in the same background document, every view is turned to Coarse and the Doors category's
/// subcategories hidden in it (as an architect's own views may), and it is read again: the reader makes its own plan
/// view, so the sides must not change. Closed without saving. Expected: every door read, each on its built side, both
/// times.</summary>
internal static class SwingCheck
{
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "swing_check_request.json");

    internal static void Run(Autodesk.Revit.ApplicationServices.Application app, string requestFile)
    {
        var request = JsonNode.Parse(File.ReadAllText(requestFile))!.AsObject();
        var modelPath = request["model"]!.GetValue<string>();
        var data = BuildData.Parse(JsonNode.Parse(File.ReadAllText(request["data"]!.GetValue<string>())));
        var log = new Dictionary<string, object?> { ["model"] = modelPath };
        var doc = app.OpenDocumentFile(modelPath);
        try
        {
            // each door the data gives a swing, by its Mark (D01...)
            var byMark = data.Doors.Where(d => d.SwingDir is not null).ToDictionary(BuildData.DoorMark);
            var built = new Dictionary<string, Xyz>(StringComparer.Ordinal);
            var how = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var fi in new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Doors).WhereElementIsNotElementType().OfType<FamilyInstance>())
            {
                var mark = fi.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString();
                if (mark is null || !byMark.TryGetValue(mark, out var d))
                    continue;
                built[fi.UniqueId] = new Xyz(d.SwingDir!.Value.X, d.SwingDir.Value.Y, 0);
                how[fi.UniqueId] = $"{mark} ({fi.Symbol.FamilyName}: {fi.Symbol.Name}; {(d.IsDouble ? "double" : "single")}): " +
                                   $"facing ({fi.FacingOrientation.X:0.###}, {fi.FacingOrientation.Y:0.###}) flipped {fi.FacingFlipped}, " +
                                   $"hand ({fi.HandOrientation.X:0.###}, {fi.HandOrientation.Y:0.###}) flipped {fi.HandFlipped}, mirrored {fi.Mirrored}";
            }
            log["doors"] = built.Count;
            log["as_built"] = Rows(doc, built, how);
            log["rooms"] = Rooms(doc, built, how);
            // what Revit itself draws, to look at: each level's plan as a picture beside the model, and each door's
            // arcs as read (centre and middle, plan feet)
            log["pictures"] = Pictures(doc, Path.GetDirectoryName(modelPath)!);
            var swings = RevitInterior.SwingsOf(doc, []);
            log["arcs"] = swings.Where(s => how.ContainsKey(s.Key)).OrderBy(s => how[s.Key], StringComparer.Ordinal)
                .Select(s => how[s.Key][..3] + ": " + (s.Value.NotRead ?? string.Join("; ", s.Value.Arcs.Select(a =>
                    $"centre ({a.Centre.X:0.##}, {a.Centre.Y:0.##}) r {a.Radius:0.##} mid ({a.Mid.X:0.##}, {a.Mid.Y:0.##})")))).ToList();
            using (var t = new Transaction(doc, "Gordium: every view coarse, door subcategories hidden"))
            {
                t.Start();
                var category = Autodesk.Revit.DB.Category.GetCategory(doc, BuiltInCategory.OST_Doors);
                var hidden = 0;
                foreach (var v in new FilteredElementCollector(doc).OfClass(typeof(Autodesk.Revit.DB.View)).Cast<Autodesk.Revit.DB.View>().Where(v => !v.IsTemplate).ToList())
                {
                    try
                    {
                        v.DetailLevel = ViewDetailLevel.Coarse;
                        foreach (Autodesk.Revit.DB.Category sub in category.SubCategories)
                            if (v.CanCategoryBeHidden(sub.Id))
                            {
                                v.SetCategoryHidden(sub.Id, true);
                                hidden++;
                            }
                    }
                    catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                                   or Autodesk.Revit.Exceptions.ArgumentException)
                    {
                        // a view that has no detail level or can't hide them (a schedule, a sheet): left as it is
                    }
                }
                t.Commit();
                log["subcategories_hidden"] = hidden;
            }
            log["views_coarse_swings_hidden"] = Rows(doc, built, how);
        }
        finally
        {
            doc.Close(false);
        }
        Trial.Log("swing_check", log);
    }

    private static List<string> Rows(Document doc, Dictionary<string, Xyz> built, Dictionary<string, string> how)
    {
        var model = RevitInterior.Model(doc);
        return RouteReader.CheckSwings(model, built)
            .Select(r => $"{how[r.Id]}: read {Side(r.Read)}, built {Side(r.Built)}{(r.Read is not null && r.Read == r.Built ? " (agrees)" : " (DIFFERS)")}" +
                         (r.Why is null ? "" : $"; {r.Why}"))
            .OrderBy(x => x, StringComparer.Ordinal).ToList();
    }

    /// <summary>Each door's <c>swings_into</c> as the check's own reading sends it (InteriorReader.Read: its room's
    /// name, or outside, or the note why it isn't sent) beside the room Revit itself finds 1 ft past the wall's face
    /// on the side the door was built to swing (<c>Document.GetRoomAtPoint</c>, the last phase; none: outside).</summary>
    private static List<string> Rooms(Document doc, Dictionary<string, Xyz> built, Dictionary<string, string> how)
    {
        var read = InteriorReader.Read(RevitInterior.Model(doc));
        var phase = doc.Phases.Cast<Phase>().LastOrDefault();
        var names = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()
            .Cast<Element>().ToDictionary(r => r.UniqueId, r => r.Name, StringComparer.Ordinal);
        var doors = (read.Interior["doors"] as JsonArray ?? []).OfType<JsonObject>()
            .ToDictionary(d => d["id"]!.GetValue<string>(), StringComparer.Ordinal);
        var rows = new List<string>();
        foreach (var (id, dir) in built)
        {
            var fi = (FamilyInstance)doc.GetElement(id);
            var at = (fi.Location as LocationPoint)!.Point;
            var half = fi.Host is Wall w ? w.Width / 2 : 0.25;
            var level = doc.GetElement(fi.LevelId) as Level;
            var probe = new XYZ(at.X + dir.X * (half + 1), at.Y + dir.Y * (half + 1), (level?.ProjectElevation ?? at.Z) + 1);
            var there = phase is null ? null : doc.GetRoomAtPoint(probe, phase);
            var expected = there is null ? "outside" : there.Name;
            string got;
            if (doors.TryGetValue(id, out var d) && d["swings_into"]?.GetValue<string>() is { } into)
                got = into == RouteReader.Outside ? "outside" : names.GetValueOrDefault(into, into);
            else
                got = "not sent (" + (read.RouteNotes.FirstOrDefault(n => n.Part == id && n.Field == "doors.swings_into")?.Why ?? "no note") + ")";
            rows.Add($"{how[id][..3]}: swings_into {got}; Revit's room on the built side {expected}{(got == expected ? " (agrees)" : " (DIFFERS)")}");
        }
        return rows.OrderBy(x => x, StringComparer.Ordinal).ToList();
    }

    /// <summary>Each floor plan (not a template) exported as a PNG beside the model, to look at.</summary>
    private static List<string> Pictures(Document doc, string dir)
    {
        var made = new List<string>();
        foreach (var v in new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).Cast<ViewPlan>()
                     .Where(v => !v.IsTemplate && v.ViewType == ViewType.FloorPlan).ToList())
        {
            try
            {
                var file = Path.Combine(dir, "door_swing_" + string.Concat(v.Name.Select(c => char.IsLetterOrDigit(c) ? c : '_')));
                var o = new ImageExportOptions
                {
                    ExportRange = ExportRange.SetOfViews, FilePath = file, ZoomType = ZoomFitType.FitToPage, PixelSize = 2400,
                    ImageResolution = ImageResolution.DPI_150, HLRandWFViewsFileType = ImageFileType.PNG,
                };
                o.SetViewsAndSheets([v.Id]);
                doc.ExportImage(o);
                made.Add($"{v.Name}: {file}*.png");
            }
            catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                           or Autodesk.Revit.Exceptions.ArgumentException)
            {
                made.Add($"{v.Name}: not exported ({x.GetType().Name}: {x.Message})");
            }
        }
        return made;
    }

    private static string Side(int? s) => s switch { 1 => "+", -1 => "-", _ => "none" };
}
