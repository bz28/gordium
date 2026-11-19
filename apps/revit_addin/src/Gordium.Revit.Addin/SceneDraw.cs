using System.Text.Json.Nodes;
using Autodesk.Revit.DB;

namespace Gordium.Revit.Addin;

/// <summary>
/// Draws one conformance scene in a new Revit document, from the suite's own numbers (scene_data.py, from
/// design_checker.conformance), as the runbook's section 4 says and as SceneDrawing.cs draws it in fake records:
/// the lot a property line, each floor block a Gordium-marked DirectShape solid carrying "&lt;story&gt;;&lt;height&gt;",
/// each other solid a Generic Model DirectShape (context-marked on Gordium::Context). A scene with something the
/// drawer can't draw yet is refused whole, its reasons named: never drawn partly.
/// </summary>
internal static class SceneDraw
{
    /// <summary>Why a scene can't be drawn yet; empty when it can.</summary>
    internal static List<string> Unsupported(JsonObject scene)
    {
        var why = new List<string>();
        if (scene["offset"]!.AsArray().Any(v => v!.GetValue<double>() != 0))
            why.Add("a survey offset (shared coordinates)");
        if (scene["units"]!.GetValue<string>() != "Feet")
            why.Add("display units other than feet");
        if (scene["lot_arcs"]!.AsObject().Count > 0)
            why.Add("a curved lot line");
        if (scene["open_lots"]!.AsArray().Count > 0)
            why.Add("an open property line");
        if (scene["picked"] is JsonValue)
            why.Add("a picked lot");
        if (scene["group"]!.GetValue<bool>())
            why.Add("a model group");
        if (scene["spots"]!.AsArray().Count > 0)
            why.Add("spot grades");
        foreach (var (step, data) in scene["steps"]!.AsObject())
        {
            if (step != "as drawn")
                why.Add("a step after an edit");
            foreach (var s in data!["solids"]!.AsArray())
            {
                if (s!["floor"] is not JsonValue)
                    why.Add($"{s["id"]}: a building that isn't a floor block");
                if (s["curved"] is JsonObject)
                    why.Add($"{s["id"]}: a curved face");
                if (s["open"]!.GetValue<bool>() || s["mesh"]!.GetValue<bool>() || s["block"]!.GetValue<bool>() || s["in_block"] is JsonValue)
                    why.Add($"{s["id"]}: an open solid, a mesh, a block or a linked model");
            }
        }
        foreach (var o in scene["others"]!.AsArray())
            if (o!["mesh"] is JsonObject || o["block"]?.GetValue<bool>() == true || o["empty"]?.GetValue<bool>() == true
                || o["nested_empty"]?.GetValue<bool>() == true || o["holds_buildings"]?.GetValue<bool>() == true)
                why.Add($"{o["id"]}: a mesh, a family or a linked model");
        return why.Distinct().ToList();
    }

    /// <summary>Draws the scene's first step in <paramref name="doc"/>; gives {Revit UniqueId: the scene's id}.</summary>
    internal static Dictionary<string, string> Draw(Document doc, JsonObject scene)
    {
        var ids = new Dictionary<string, string>();
        using var t = new Transaction(doc, "Gordium: draw conformance scene");
        t.Start();
        var lots = scene["lots"]!.AsArray();
        for (var k = 0; k < lots.Count; k++)
        {
            var loop = Loop(Outline(lots[k]!), 0);
            var line = PropertyLine.Create(doc, new List<CurveLoop> { loop });
            ids[line.UniqueId] = scene["lot_ids"]![k]!.GetValue<string>();
        }
        foreach (var s in scene["steps"]!["as drawn"]!["solids"]!.AsArray())
        {
            var name = s!["id"]!.GetValue<string>();
            var story = name.Split("floor")[^1];
            var mark = $"{RevitRead.FloorPrefix}{story};{Num(s["floor"]!.GetValue<double>())}";
            ids[Prism(doc, Outline(s["outline"]!), s["base"]!.GetValue<double>(), s["top"]!.GetValue<double>(), mark).UniqueId] = name;
        }
        foreach (var o in scene["others"]!.AsArray())
        {
            var context = o!["layer"]?.GetValue<string>().StartsWith("Gordium::Context", StringComparison.Ordinal) == true;
            ids[Prism(doc, Outline(o["outline"]!), o["base"]!.GetValue<double>(), o["top"]!.GetValue<double>(),
                      context ? RevitRead.ContextMark : null).UniqueId] = o["id"]!.GetValue<string>();
        }
        if (t.Commit() != TransactionStatus.Committed)
            throw new InvalidOperationException("Revit didn't commit the scene's drawing");
        return ids;
    }

    /// <summary>A vertical prism, a Generic Model DirectShape; marked as Gordium's when <paramref name="mark"/> is given.</summary>
    private static DirectShape Prism(Document doc, List<(double X, double Y)> outline, double z0, double z1, string? mark)
    {
        var solid = GeometryCreationUtilities.CreateExtrusionGeometry([Loop(outline, z0)], XYZ.BasisZ, z1 - z0);
        var ds = DirectShape.CreateElement(doc, new ElementId(BuiltInCategory.OST_GenericModel));
        if (mark is not null)
        {
            ds.ApplicationId = RevitRead.MarkApplication;
            ds.ApplicationDataId = mark;
        }
        ds.SetShape(new List<GeometryObject> { solid });
        return ds;
    }

    private static CurveLoop Loop(List<(double X, double Y)> ring, double z)
    {
        var curves = new List<Curve>();
        for (var i = 0; i < ring.Count; i++)
        {
            var (a, b) = (ring[i], ring[(i + 1) % ring.Count]);
            curves.Add(Line.CreateBound(new XYZ(a.X, a.Y, z), new XYZ(b.X, b.Y, z)));
        }
        return CurveLoop.Create(curves);
    }

    private static List<(double X, double Y)> Outline(JsonNode o) =>
        o.AsArray().Select(p => (p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList();

    private static string Num(double v) => v.ToString("R", System.Globalization.CultureInfo.InvariantCulture);
}
