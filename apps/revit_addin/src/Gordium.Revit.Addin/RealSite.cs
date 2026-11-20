using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.Revit.DB;
using Gordium.Revit.Reading;
using Gordium.Worker;

namespace Gordium.Revit.Addin;

/// <summary>A real Rhino model drawn in Revit and read back as a check reads it (the trial's real-lot test:
/// apps/revit_addin/tests/Gordium.Revit.Reading.Tests/real_site.py). Asked for by request file
/// (real_site_request.json: <c>{"model": "&lt;export&gt;.json", "out": "&lt;result&gt;.json"}</c>, read while Revit is
/// idle): the export's lots drawn as property lines, its buildings as Walls DirectShapes made of exactly the faces
/// Rhino's reader sends, its other curves as model lines; read (RevitRead, then SiteReader) with the export's facts and
/// the picked lot's UniqueId; the description and the id map written to <c>out</c>. The model is closed unsaved.</summary>
internal static class RealSite
{
    internal static string RequestPath => Path.Combine(Path.GetDirectoryName(Trial.LogPath())!, "real_site_request.json");

    internal static void Run(Autodesk.Revit.ApplicationServices.Application app, string requestFile)
    {
        var request = JsonNode.Parse(File.ReadAllText(requestFile, Encoding.UTF8))!;
        var export = JsonNode.Parse(File.ReadAllText(request["model"]!.GetValue<string>(), Encoding.UTF8))!.AsObject();
        var log = new Dictionary<string, object?> { ["model"] = request["model"]!.GetValue<string>() };
        var doc = app.NewProjectDocument(UnitSystem.Imperial);
        try
        {
            var ids = new JsonObject();
            string? picked = null;
            using (var t = new Transaction(doc, "Gordium: a real site"))
            {
                Warnings.Accept(t);
                t.Start();
                foreach (var lot in export["lots"]!.AsArray())
                {
                    var ring = lot!["points"]!.AsArray().Select(p => new XYZ(p![0]!.GetValue<double>(), p[1]!.GetValue<double>(), 0)).ToList();
                    var loop = new CurveLoop();
                    for (var i = 0; i < ring.Count; i++)
                        loop.Append(Line.CreateBound(ring[i], ring[(i + 1) % ring.Count]));
                    var line = PropertyLine.Create(doc, new List<CurveLoop> { loop });
                    var id = lot["id"]!.GetValue<string>();
                    ids[line.UniqueId] = id;
                    if (id == export["picked"]?.GetValue<string>())
                        picked = line.UniqueId;
                }
                foreach (var b in export["buildings"]!.AsArray())
                {
                    var builder = new TessellatedShapeBuilder
                    {
                        Target = TessellatedShapeBuilderTarget.Solid, Fallback = TessellatedShapeBuilderFallback.Abort,
                    };
                    builder.OpenConnectedFaceSet(true);
                    foreach (var f in b!["faces"]!.AsArray())
                        builder.AddFace(new TessellatedFace(f!.AsArray().Select(P).ToList(), ElementId.InvalidElementId));
                    builder.CloseConnectedFaceSet();
                    builder.Build();
                    var built = builder.GetBuildResult();
                    if (built.Outcome != TessellatedShapeBuilderOutcome.Solid)
                        throw new InvalidOperationException($"building {b["id"]} came back as {built.Outcome}, not a solid");
                    var ds = DirectShape.CreateElement(doc, new ElementId(BuiltInCategory.OST_Walls));
                    ds.SetShape(built.GetGeometricalObjects());
                    ids[ds.UniqueId] = b["id"]!.GetValue<string>();
                }
                foreach (var l in export["lines"]!.AsArray())
                {
                    var pts = l!.AsArray().Select(P).ToList();
                    var plane = SketchPlane.Create(doc, Plane.CreateByNormalAndOrigin(XYZ.BasisZ, new XYZ(0, 0, pts[0].Z)));
                    for (var i = 0; i + 1 < pts.Count; i++)
                        if (pts[i].DistanceTo(pts[i + 1]) > app.ShortCurveTolerance)
                            doc.Create.NewModelCurve(Line.CreateBound(pts[i], new XYZ(pts[i + 1].X, pts[i + 1].Y, pts[0].Z)), plane);
                }
                if (t.Commit() != TransactionStatus.Committed)
                    throw new InvalidOperationException("Revit didn't commit the drawing");
            }
            var facts = export["facts"]!.DeepClone().AsObject();
            facts["lot_id"] = picked;
            var model = RevitRead.Model(doc, app.VersionNumber, app.VertexTolerance);
            var read = SiteReader.DescribeAsync(model, facts, new WorkerLeftOut(Trial.Worker())).GetAwaiter().GetResult();
            var result = new JsonObject { ["site"] = read.Site, ["ids"] = ids };
            File.WriteAllText(request["out"]!.GetValue<string>(), result.ToJsonString(new JsonSerializerOptions { WriteIndented = true }),
                              new UTF8Encoding(false));
            log["ok"] = true;
        }
        catch (Exception x)
        {
            log["error"] = $"{x.GetType().Name}: {x.Message}";
            log["where"] = x.StackTrace?.Split('\n').Take(4).Select(s => s.Trim()).ToList();
        }
        finally
        {
            doc.Close(false);
        }
        Trial.Log("real_site", log);
    }

    private static XYZ P(JsonNode? p) => new(p![0]!.GetValue<double>(), p[1]!.GetValue<double>(), p[2]!.GetValue<double>());
}
