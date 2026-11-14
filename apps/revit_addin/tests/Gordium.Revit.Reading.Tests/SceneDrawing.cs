using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading.Tests;

/// <summary>One drawn conformance scene, from scene_data.py (the suite's own numbers), drawn as fake Revit records as
/// the Windows trial would draw it in Revit (test_data/host_conformance/README.md, "How to add a host"):
/// <list type="bullet">
/// <item>the lot: a property line (an arc where the scene has one); two outlines: two property lines;</item>
/// <item>each floor block: a Gordium-marked DirectShape solid carrying "&lt;story&gt;;&lt;height&gt;";</item>
/// <item>a block on the Building layer (scene 04): a linked Revit model holding a wall;</item>
/// <item>each other solid: a Generic Model DirectShape; a block: a Generic Models family instance; one on
/// Gordium::Context: a context-marked DirectShape; the terrain mesh: an open-mesh DirectShape;</item>
/// <item>each spot grade: a spot-grade marker;</item>
/// <item>a survey offset: shared coordinates moved by it, the drawing near Revit's internal origin; millimetres:
/// the project's display unit (Revit's points are feet whatever it shows);</item>
/// <item>the edit: the buildings moved in place, every UniqueId kept.</item>
/// </list></summary>
public sealed record SceneDrawing(string Name, JsonObject Data)
{
    public override string ToString() => Name;

    public static IReadOnlyList<SceneDrawing> All => _all.Value;

    private static readonly Lazy<IReadOnlyList<SceneDrawing>> _all = new(() =>
        Env.RunPython("scene_data.py").Split('\n', StringSplitOptions.RemoveEmptyEntries)
           .Select(l => JsonNode.Parse(l)!.AsObject()).Select(o => new SceneDrawing(o["name"]!.GetValue<string>(), o)).ToList());

    public static SceneDrawing Named(string name) => All.Single(s => s.Name == name);

    public IReadOnlyList<string> Steps => Data["steps"]!.AsObject().Select(p => p.Key).ToList();

    public JsonObject Facts => Data["facts"]!.DeepClone().AsObject();

    public IReadOnlyDictionary<string, string> Verdicts(string step) =>
        Data["steps"]![step]!["verdicts"]!.AsObject().ToDictionary(p => p.Key, p => p.Value!.GetValue<string>());

    /// <summary>The Revit UniqueId each of the scene's objects is drawn with ({Revit id: scene id}).</summary>
    public Dictionary<string, string> Ids()
    {
        var ids = Data["lot_ids"]!.AsArray().Select(i => i!.GetValue<string>()).ToDictionary(i => "pl-" + i, i => i);
        foreach (var s in Data["steps"]![Steps[0]]!["solids"]!.AsArray())
            ids["uid-" + s!["id"]!.GetValue<string>()] = s["id"]!.GetValue<string>();
        foreach (var o in Data["others"]!.AsArray())
            ids["uid-" + o!["id"]!.GetValue<string>()] = o["id"]!.GetValue<string>();
        return ids;
    }

    private static (double X, double Y) P(JsonNode p) => (p[0]!.GetValue<double>(), p[1]!.GetValue<double>());

    private static List<(double X, double Y)> Outline(JsonNode o) => o.AsArray().Select(p => P(p!)).ToList();

    /// <summary>The scene at one step, drawn in Revit with shared coordinates <paramref name="turn"/> (turned
    /// about the vertical, radians) on top of the scene's survey offset.</summary>
    public RevitModel Model(string step, double turn = 0)
    {
        var off = Data["offset"]!.AsArray().Select(v => v!.GetValue<double>()).ToArray();
        var shared = Transform3.TurnThenMove(turn, new Xyz(off[0], off[1], off[2]));
        var f = new FakeRevit(shared);
        var elements = new List<RevitElement>();
        foreach (var s in Data["steps"]![step]!["solids"]!.AsArray())
        {
            var id = "uid-" + s!["id"]!.GetValue<string>();
            var curved = s["curved"] as JsonObject;
            var prism = f.Prism(Outline(s["outline"]!), s["base"]!.GetValue<double>(), s["top"]!.GetValue<double>(),
                                curved?["edge"]!.GetValue<int>(), curved is null ? null : P(curved["through"]!),
                                s["open"]!.GetValue<bool>());
            if (s["block"]!.GetValue<bool>())
            {
                var linked = new RevitModel { Document = "shed.rvt", Elements = [FakeRevit.Wall("shed-wall", [prism])] };
                elements.Add(FakeRevit.LinkOf(id, linked));
            }
            else if (s["floor"] is JsonValue floor)
            {
                var story = s["id"]!.GetValue<string>().Split("floor")[^1];
                elements.Add(FakeRevit.Directshape(id, [prism], GordiumMark.FloorBlock, $"{story};{floor.GetValue<double>()}"));
            }
            else
                elements.Add(FakeRevit.Wall(id, [prism]));
        }
        foreach (var o in Data["others"]!.AsArray())
        {
            var id = "uid-" + o!["id"]!.GetValue<string>();
            var outline = Outline(o["outline"]!);
            double z0 = o["base"]!.GetValue<double>(), z1 = o["top"]!.GetValue<double>();
            if (o["mesh"] is JsonObject mesh)
            {
                var lo = (outline.Min(p => p.X), outline.Min(p => p.Y));
                var hi = (outline.Max(p => p.X), outline.Max(p => p.Y));
                elements.Add(FakeRevit.Directshape(id, [f.Grid(lo, hi, z0, mesh["cells"]!.GetValue<int>())]));
            }
            else if (o["block"]?.GetValue<bool>() == true)
                elements.Add(FakeRevit.Family(id, [f.Prism(outline, z0, z1)]));
            else
                elements.Add(FakeRevit.Directshape(id, [f.Prism(outline, z0, z1)],
                    o["layer"]!.GetValue<string>().StartsWith("Gordium::Context", StringComparison.Ordinal) ? GordiumMark.Context : GordiumMark.None));
        }
        var n = 0;
        foreach (var p in Data["spots"]!.AsArray())
            elements.Add(new RevitElement
            {
                UniqueId = $"uid-grade_{++n}", BuiltInCategory = "OST_GenericModel", Category = "Generic Models",
                Mark = GordiumMark.SpotGrade,
                Location = f.Place(p![0]!.GetValue<double>(), p[1]!.GetValue<double>(), p[2]!.GetValue<double>()),
            });
        var arcs = Data["lot_arcs"]!.AsObject().ToDictionary(a => int.Parse(a.Key), a => a.Value!.AsObject());
        var lots = Data["lots"]!.AsArray().Select((ring, k) => f.PropertyLine(
            "pl-" + Data["lot_ids"]![k]!.GetValue<string>(), Outline(ring!), k == 0 ? arcs : null)).ToList();
        return new RevitModel
        {
            Document = Name + ".rvt", Version = "fake", DisplayUnits = Data["units"]!.GetValue<string>(),
            InternalToShared = shared, Elements = elements, LotLines = lots,
        };
    }
}
