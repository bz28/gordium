using System.IO;
using System.Text;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace Gordium.Revit.Addin;

/// <summary>Scene 18's built-in is an in-place family, which Revit's API can't create (and inside the in-place
/// editor Revit raises no Idling event and greys out every add-in button, so no code runs there): it is made once by
/// hand, in a source model (%LOCALAPPDATA%\Gordium\trial\in_place_source.rvt), and the scene drawer copies it from
/// there into each scene model (as Copy and Paste does). Driven by request file (in_place_request.json,
/// <c>{"step": ...}</c>) while Revit is idle:
/// <list type="number">
/// <item><c>start</c>: a new model with the built-in's outline drawn as four model lines, (15.5, 60) to
/// (19.5, 62) on Level 1, saved as the source, opened, zoomed to fit, and Model In-Place started. Then by hand:
/// category Walls, name built_in, Create > Extrusion, Pick Lines on the four lines, Extrusion Start 1 and End 10,
/// Finish edit mode, Finish Model;</item>
/// <item><c>finish</c>: the four lines deleted, the in-place family checked (Walls, its box (15.5, 60, 1) to
/// (19.5, 62, 10)) and the source saved.</item>
/// </list></summary>
internal static class InPlaceSource
{
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "in_place_request.json");

    internal static string SourcePath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "in_place_source.rvt");

    internal static readonly XYZ Min = new(15.5, 60, 1), Max = new(19.5, 62, 10);

    internal static void Run(UIApplication ui, string requestFile)
    {
        var step = JsonNode.Parse(File.ReadAllText(requestFile, Encoding.UTF8))!["step"]!.GetValue<string>();
        var log = new Dictionary<string, object?> { ["step"] = step };
        try
        {
            switch (step)
            {
                case "start":
                {
                    var doc = ui.Application.NewProjectDocument(UnitSystem.Imperial);
                    using (var t = new Transaction(doc, "Gordium: the built-in's outline"))
                    {
                        t.Start();
                        var plane = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, XYZ.Zero));
                        XYZ[] c = [new(Min.X, Min.Y, 0), new(Max.X, Min.Y, 0), new(Max.X, Max.Y, 0), new(Min.X, Max.Y, 0)];
                        for (var i = 0; i < 4; i++)
                            doc.Create.NewModelCurve(Line.CreateBound(c[i], c[(i + 1) % 4]), plane);
                        t.Commit();
                    }
                    doc.SaveAs(SourcePath, new SaveAsOptions { OverwriteExistingFile = true });
                    doc.Close(false);
                    var ud = ui.OpenAndActivateDocument(SourcePath);
                    foreach (var v in ud.GetOpenUIViews())
                        v.ZoomToFit();
                    ui.PostCommand(RevitCommandId.LookupPostableCommandId(PostableCommand.ModelInPlace));
                    break;
                }
                case "finish":
                {
                    var doc = ui.ActiveUIDocument.Document;
                    using (var t = new Transaction(doc, "Gordium: the outline's lines removed"))
                    {
                        t.Start();
                        doc.Delete(new FilteredElementCollector(doc).OfClass(typeof(CurveElement)).OfCategory(BuiltInCategory.OST_Lines)
                            .ToElementIds());
                        t.Commit();
                    }
                    var placed = new FilteredElementCollector(doc).OfClass(typeof(FamilyInstance)).Cast<FamilyInstance>()
                        .Where(f => f.Symbol.Family.IsInPlace).ToList();
                    log["in_place"] = placed.Select(f =>
                    {
                        var b = f.get_BoundingBox(null);
                        return $"{f.Symbol.Family.Name} ({f.Category?.Name}): {b?.Min} .. {b?.Max}";
                    }).ToList();
                    if (placed.Count != 1 || placed[0].Category?.BuiltInCategory != BuiltInCategory.OST_Walls)
                        throw new InvalidOperationException("expected one in-place family, in Walls");
                    var box = placed[0].get_BoundingBox(null);
                    if (!box.Min.IsAlmostEqualTo(Min) || !box.Max.IsAlmostEqualTo(Max))
                        throw new InvalidOperationException($"its box is {box.Min} .. {box.Max}, not {Min} .. {Max}");
                    doc.Save();
                    break;
                }
                default:
                    throw new InvalidOperationException($"no step {step}");
            }
            log["ok"] = true;
        }
        catch (Exception x)
        {
            log["error"] = $"{x.GetType().Name}: {x.Message}";
        }
        Trial.Log("in_place_source", log);
    }
}
