using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading.Tests;

/// <summary>One drawn conformance scene, from scene_data.py (the suite's own numbers), drawn as fake Revit records as
/// the Windows trial would draw it in Revit (test_data/host_conformance/README.md, "How to add a host"; each row the
/// Revit equivalent the design note, docs/revit/revit_reading_design.md, gives):
/// <list type="bullet">
/// <item>the lot: a property line (an arc where the scene has one; finished open, every piece but the last, where
/// the scene draws it open: 24, 25); two outlines: two property lines; a picked lot (21, 23, 25): the facts'
/// <c>lot_id</c> is the picked property line's UniqueId, as the add-in saves it (the scene's own is the reference
/// model's Rhino id), so a picked lot that was deleted (23) names a line that isn't there;</item>
/// <item>each floor block: a Gordium-marked DirectShape solid carrying "&lt;story&gt;;&lt;height&gt;";</item>
/// <item>a house of parts (18, 20), each part its own element in its building category (section 1, row 1): the
/// slabs Floors and Roofs, the walls Walls, the window a Windows family, the mullions and panel Curtain Wall
/// Mullions and Panels beside a curtain wall host with no faces of its own, the built-in an in-place family in a
/// building category; the roof slab drawn as a closed mesh (Mesh.IsClosed true) of the suite's triangles;</item>
/// <item>a block on the Building layer (04): a wall whose geometry holds a piece the reader doesn't know (section 2,
/// "anything else in the geometry": unsent, not_a_solid), never a linked model, which Revit can't place "on the
/// Building layer" and which is left out too (section 1; scene 19);</item>
/// <item>a block holding the house, off the Building layer (19): a linked model holding the floor blocks;</item>
/// <item>each other solid: a Generic Model DirectShape; a block: a Generic Models family instance (26: one holding
/// only an empty solid, and one holding beside its solid a nested family that gives no geometry, section 7, H:
/// "a nested family with no geometry"; in Revit a nested family holding only an empty solid, or only lines, is read
/// as nothing instead, since it takes no room, and the shed keeps its own box: ReaderTests pins that, review round
/// 5 of the reader);
/// one on Gordium::Context: a context-marked DirectShape; the terrain mesh: an open-mesh DirectShape;</item>
/// <item>a group (20): a model group of every part, its geometry theirs (what <c>get_Geometry</c> of a group gives),
/// never read itself (section 1, "Model group");</item>
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

    /// <summary>The scene's facts, a picked lot's <c>lot_id</c> the Revit id of the property line picked.</summary>
    public JsonObject Facts
    {
        get
        {
            var facts = Data["facts"]!.DeepClone().AsObject();
            if (Data["picked"] is JsonValue picked)
                facts["lot_id"] = "pl-" + picked.GetValue<string>();
            return facts;
        }
    }

    public IReadOnlyDictionary<string, string> Verdicts(string step) =>
        Data["steps"]![step]!["verdicts"]!.AsObject().ToDictionary(p => p.Key, p => p.Value!.GetValue<string>());

    /// <summary>The Revit UniqueId each of the scene's objects is drawn with ({Revit id: scene id}).</summary>
    public Dictionary<string, string> Ids()
    {
        var ids = Data["lot_ids"]!.AsArray().Select(i => i!.GetValue<string>()).ToDictionary(i => "pl-" + i, i => i);
        foreach (var s in Data["steps"]![Steps[0]]!["solids"]!.AsArray())
            if (s!["in_block"] is not JsonValue)            // inside a linked model: never sent, so never named
                ids["uid-" + s["id"]!.GetValue<string>()] = s["id"]!.GetValue<string>();
        foreach (var o in Data["others"]!.AsArray())
            ids["uid-" + o!["id"]!.GetValue<string>()] = o["id"]!.GetValue<string>();
        return ids;
    }

    /// <summary>A part of a house built from parts (18, 20), in its building category (design note, section 1): the
    /// window a Windows family and the built-in an in-place family (read by their category), the rest system
    /// elements.</summary>
    private static RevitElement PartOf(string id, string name, SolidItem prism) => name switch
    {
        "floor_slab" => FakeRevit.Part(id, "OST_Floors", "Floors", [prism]),
        "roof_slab" => FakeRevit.Part(id, "OST_Roofs", "Roofs", [prism]),
        "window" => FakeRevit.Family(id, [prism], "OST_Windows", "Windows"),
        "built_in" => FakeRevit.Family(id, [prism], "OST_Walls", "Walls") with { IsInPlace = true },
        "curtain_panel" => FakeRevit.Family(id, [prism], "OST_CurtainWallPanels", "Curtain Panels"),
        _ when name.StartsWith("mullion_", StringComparison.Ordinal) => FakeRevit.Part(id, "OST_CurtainWallMullions", "Curtain Wall Mullions", [prism]),
        _ => FakeRevit.Wall(id, [prism]),
    };

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
        var inLinks = new Dictionary<string, List<RevitElement>>();
        var parts = new List<GeometryItem>();
        foreach (var s in Data["steps"]![step]!["solids"]!.AsArray())
        {
            var name = s!["id"]!.GetValue<string>();
            var id = "uid-" + name;
            var outline = Outline(s["outline"]!);
            double z0 = s["base"]!.GetValue<double>(), z1 = s["top"]!.GetValue<double>();
            var curved = s["curved"] as JsonObject;
            var prism = f.Prism(outline, z0, z1, curved?["edge"]!.GetValue<int>(), curved is null ? null : P(curved["through"]!),
                                s["open"]!.GetValue<bool>());
            parts.Add(prism);
            var drawn = s["floor"] is JsonValue floor
                ? FakeRevit.Directshape(id, [prism], GordiumMark.FloorBlock, $"{name.Split("floor")[^1]};{floor.GetValue<double>()}")
                : s["block"]!.GetValue<bool>()
                    ? FakeRevit.Wall(id, [new OtherItem("a piece the reader doesn't know")]) with { BoundingBox = FakeRevit.BoxOf([prism]) }
                    : s["mesh"]!.GetValue<bool>()
                        ? FakeRevit.Part(id, "OST_Roofs", "Roofs", [f.ClosedMesh(outline, z0, z1)])
                        : PartOf(id, name, prism);
            if (s["in_block"] is JsonValue link)
                (inLinks.TryGetValue(link.GetValue<string>(), out var held) ? held : inLinks[link.GetValue<string>()] = []).Add(drawn);
            else
                elements.Add(drawn);
        }
        if (elements.Any(e => e.BuiltInCategory == "OST_CurtainWallPanels"))
            elements.Add(FakeRevit.Part("uid-curtain_wall", "OST_Walls", "Walls", []) with { Kind = ElementKind.CurtainWallHost });
        if (Data["group"]!.GetValue<bool>())
            elements.Add(FakeRevit.Part("uid-group", "OST_IOSModelGroups", "Model Groups", parts) with { Kind = ElementKind.Group });
        foreach (var o in Data["others"]!.AsArray())
        {
            var name = o!["id"]!.GetValue<string>();
            var id = "uid-" + name;
            if (o["holds_buildings"]?.GetValue<bool>() == true)
            {
                elements.Add(FakeRevit.LinkOf(id, new RevitModel { Document = name + ".rvt", Elements = inLinks[name] }));
                continue;
            }
            if (o["empty"]?.GetValue<bool>() == true)
            {
                elements.Add(FakeRevit.Family(id, [new SolidItem([], [])]));
                continue;
            }
            var outline = Outline(o["outline"]!);
            double z0 = o["base"]!.GetValue<double>(), z1 = o["top"]!.GetValue<double>();
            if (o["mesh"] is JsonObject mesh)
            {
                var lo = (outline.Min(p => p.X), outline.Min(p => p.Y));
                var hi = (outline.Max(p => p.X), outline.Max(p => p.Y));
                elements.Add(FakeRevit.Directshape(id, [f.Grid(lo, hi, z0, mesh["cells"]!.GetValue<int>())]));
            }
            else if (o["nested_empty"]?.GetValue<bool>() == true)
            {
                // as Revit gives a shared nested family (trial, 2026-11-19): its own element, a sub-component of the
                // shed, holding only an empty solid; the shed's own geometry without it
                elements.Add(FakeRevit.Family(id, [f.Prism(outline, z0, z1)]));
                elements.Add(FakeRevit.Family(id + "_part", [new SolidItem([], [])]) with { SuperComponent = id });
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
        var open = Data["open_lots"]!.AsArray().Select(k => k!.GetValue<int>()).ToHashSet();
        var lots = Data["lots"]!.AsArray().Select((ring, k) => f.PropertyLine(
            "pl-" + Data["lot_ids"]![k]!.GetValue<string>(), Outline(ring!), k == 0 ? arcs : null, open.Contains(k))).ToList();
        return new RevitModel
        {
            Document = Name + ".rvt", Version = "fake", DisplayUnits = Data["units"]!.GetValue<string>(),
            InternalToShared = shared, Elements = elements, LotLines = lots,
        };
    }
}
