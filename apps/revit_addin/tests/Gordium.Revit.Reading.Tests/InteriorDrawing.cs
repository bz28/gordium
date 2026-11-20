using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading.Tests;

/// <summary>A hand-worked house (test_data/interior_houses/) drawn as fake Revit records, the way the Revit layer would
/// fill them from the house the add-in draws (RecordHouses, HouseDraw): the drawing's numbers come from the house's own
/// data through <c>python -m model_measurement.interior.recordings draw</c>, never retyped. Each level's exterior walls
/// (inside faces on the rooms' outline, a cut where each window is), a floor slab whose top is the level, a thin
/// ceiling solid over each room whose underside is its ceiling, room separation lines where rooms meet, each window
/// hosted in its room's outside wall, cutting it from its sill line up, with its type's marks and confirmation stamp.
/// The lists are open, so a test can change one thing the way a model can be wrong.</summary>
internal sealed class FakeHouse
{
    public const string LastPhase = "phase-2";
    public const string Confirmed = "2026-11-20";

    private static readonly Lazy<Dictionary<string, JsonObject>> Drawings = new(() =>
        Env.RunModule("model_measurement.interior.recordings", "draw")
            .Split('\n', StringSplitOptions.RemoveEmptyEntries)
            .Select(l => JsonNode.Parse(l)!.AsObject())
            .ToDictionary(d => d["house"]!.GetValue<string>()));

    public static IReadOnlyCollection<string> Houses => Drawings.Value.Keys;

    public string Name { get; }
    public JsonObject Drawing { get; }
    public FakeRevit Fake { get; }
    public List<MarkedElement> Marked { get; } = [];
    public List<RoomRecord> Rooms { get; } = [];
    public List<OpeningRecord> Openings { get; } = [];
    public List<EnclosedArea> Areas { get; } = [];
    public List<InteriorLink> Links { get; } = [];
    public List<WorksetRecord> Worksets { get; } = [];
    public Dictionary<string, string> Ids { get; } = [];

    public RevitModel Model() => new()
    {
        Document = Name,
        InternalToShared = Fake.InternalToShared,
        Phases = ["phase-1", LastPhase],
        Marked = Marked,
        UserWorksets = Worksets,
        Interior = new InteriorRecords { Rooms = Rooms, Openings = Openings, EnclosedAreas = Areas, Links = Links },
    };

    /// <summary>The recording the add-in writes for this reading (RecordHouses.cs), for the interior conformance check.</summary>
    public JsonObject Recording(InteriorReadResult read) => new()
    {
        ["host"] = "revit",
        ["house"] = Name,
        ["step"] = 3,
        ["recorded"] = new JsonObject { ["by"] = "InteriorTests (fake Revit records)", ["date"] = Confirmed, ["tool"] = "dotnet test" },
        ["ids"] = new JsonObject(Ids.Select(p => KeyValuePair.Create(p.Key, (JsonNode?)p.Value))),
        ["interior"] = read.Interior.DeepClone(),
    };

    public static string Uid(string houseId) => "uid-" + houseId;

    private static double D(JsonNode? n) => n!.GetValue<double>();

    private static (double X, double Y) P(JsonNode n) => (D(n[0]), D(n[1]));

    private FakeHouse(string name, Transform3 turn)
    {
        Name = name;
        Drawing = Drawings.Value[name];
        Fake = new FakeRevit(turn);
        var t = D(Drawing["exterior_wall"]);
        var thick = D(Drawing["ceiling_thickness"]);
        var walls = new Dictionary<double, List<NearbyElement>>();
        var slabs = new Dictionary<double, NearbyElement>();
        var ceilings = new Dictionary<string, NearbyElement>();
        var windowsOn = new Dictionary<string, List<JsonObject>>();
        foreach (var w in Drawing["windows"]!.AsArray().Select(n => n!.AsObject()))
        {
            var key = WallOf(w);
            windowsOn.TryAdd(key, []);
            windowsOn[key].Add(w);
        }
        foreach (var level in Drawing["levels"]!.AsArray().Select(n => n!.AsObject()))
        {
            var z = D(level["elevation"]);
            var (x0, y0) = P(level["box"]![0]!);
            var (x1, y1) = P(level["box"]![1]!);
            var h = D(level["wall_height"]);
            var list = new List<NearbyElement>();
            foreach (var (side, plan) in new[]
                     {
                         ("ymin", Rect(x0 - t, y0 - t, x1 + t, y0)), ("xmin", Rect(x0 - t, y0, x0, y1)),
                         ("ymax", Rect(x0 - t, y1, x1 + t, y1 + t)), ("xmax", Rect(x1, y0, x1 + t, y1)),
                     })
            {
                var id = $"wall-{z}-{side}";
                var faces = Prism(plan, z, z + h);
                foreach (var w in windowsOn.GetValueOrDefault(id, []))
                {
                    // the opening the window cuts: its head (an underside, inside the wall's thickness) and its sill
                    var (cx, cy) = P(w["center"]!);
                    var (ox, oy) = P(w["outward"]!);
                    var half = D(w["width"]) / 2;
                    var top = z + D(w["sill"]) + D(w["height"]);
                    var cut = OpeningPlan(cx, cy, ox, oy, half, t);
                    faces.Add(Face(new(0, 0, -1), cut.Select(p => (p.X, p.Y, top))));
                    faces.Add(Face(new(0, 0, 1), cut.Select(p => (p.X, p.Y, z + D(w["sill"])))));
                }
                list.Add(new NearbyElement(id, "OST_Walls", "Generic exterior", Faces: faces));
            }
            foreach (var (k, f) in level["fillers"]!.AsArray().Select((f, k) => (k, f!)))
            {
                var (fx0, fy0) = P(f[0]!);
                var (fx1, fy1) = P(f[1]!);
                list.Add(new NearbyElement($"filler-{z}-{k}", "OST_Walls", "Generic interior", Faces: Prism(Rect(fx0, fy0, fx1, fy1), z, z + h)));
            }
            walls[z] = list;
            slabs[z] = new NearbyElement($"slab-{z}", "OST_Floors", "Generic floor", Faces: Prism(Rect(x0 - t, y0 - t, x1 + t, y1 + t), z - 1, z));
        }
        foreach (var room in Drawing["rooms"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = room["id"]!.GetValue<string>();
            var faces = new List<SurfaceRecord>();
            foreach (var piece in room["ceilings"]!.AsArray())
            {
                var pts = piece!.AsArray().Select(p => (X: D(p![0]), Y: D(p[1]), Z: D(p[2]))).ToList();
                faces.Add(Face(Down(pts), pts));
                faces.Add(Face(new(0, 0, 1), pts.Select(p => (p.X, p.Y, p.Z + thick))));
            }
            ceilings[id] = new NearbyElement("ceiling-" + id, "OST_Ceilings", "Ceiling", Faces: faces);
        }
        foreach (var room in Drawing["rooms"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = room["id"]!.GetValue<string>();
            var uid = Uid(id);
            Ids[id] = uid;
            var z = D(room["floor_elevation"]);
            var level = Drawing["levels"]!.AsArray().First(l => D(l!["elevation"]) == z)!;
            var (bx0, by0) = P(level["box"]![0]!);
            var (bx1, by1) = P(level["box"]![1]!);
            var floor = room["floor"]!.AsArray().Select(p => P(p!)).ToList();
            var segments = new List<BoundarySegmentRecord>();
            for (var i = 0; i < floor.Count; i++)
            {
                var a = floor[i];
                var b = floor[(i + 1) % floor.Count];
                var element = a.Y == by0 && b.Y == by0 ? $"wall-{z}-ymin" : a.X == bx0 && b.X == bx0 ? $"wall-{z}-xmin"
                    : a.Y == by1 && b.Y == by1 ? $"wall-{z}-ymax" : a.X == bx1 && b.X == bx1 ? $"wall-{z}-xmax" : $"separation-{z}-{i}";
                segments.Add(new(Fake.Place(a.X, a.Y, z), Fake.Place(b.X, b.Y, z), true, element));
            }
            Marked.Add(new MarkedElement
            {
                UniqueId = uid, BuiltInCategory = Marks.Rooms, Name = room["name"]!.GetValue<string>(), Number = $"{Rooms.Count + 1}",
                PhaseCreated = LastPhase, Placement = RoomPlacement.Placed,
                Instance = new Dictionary<Guid, MarkValue>
                {
                    [Marks.SleepingRoom.Guid] = new(true, room["sleeping"]!.GetValue<bool>() ? 1 : 0),
                },
            });
            var over = new List<NearbyElement>(walls[z]);
            over.AddRange(ceilings.Values);
            over.AddRange(slabs.Where(s => s.Key > z).Select(s => s.Value));
            over.AddRange(Drawing["windows"]!.AsArray().Where(w => D(w!["level"]) == z)
                .Select(w => new NearbyElement(Uid(w!["id"]!.GetValue<string>()), "OST_Windows", "Gordium test window",
                                               Host: WallOf(w.AsObject()), Faces: WindowFaces(w.AsObject(), t))));
            Rooms.Add(new RoomRecord
            {
                UniqueId = uid, Level = $"Level {z}", LevelElevation = Fake.Place(0, 0, z).Z, BaseOffset = 0,
                Boundary = [segments], Inside = [], Under = [slabs[z]], Over = over,
            });
            Areas.Add(new EnclosedArea($"Level {z}", 0, true, Fake.Place(floor[0].X, floor[0].Y, z)));
        }
        foreach (var w in Drawing["windows"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = w["id"]!.GetValue<string>();
            var uid = Uid(id);
            Ids[id] = uid;
            var z = D(w["level"]);
            var (cx, cy) = P(w["center"]!);
            var (ox, oy) = P(w["outward"]!);
            double width = D(w["width"]), height = D(w["height"]), sill = D(w["sill"]);
            var word = Operations.Words.First(x => Operations.ForOpening(x) == w["operation"]!.GetValue<string>());
            var type = new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: word) };
            if (w["clear"] is JsonObject c)
            {
                type[Marks.ClearWidth.Guid] = new(true, Number: D(c["width"]));
                type[Marks.ClearHeight.Guid] = new(true, Number: D(c["height"]));
                type[Marks.ClearOffset.Guid] = new(true, Number: D(c["offset"]));
                type[Marks.ClearSource.Guid] = new(true, Text: c["source"]!.GetValue<string>());
                type[Marks.ClearConfirmed.Guid] = new(true, Text: ClearStamp.Make(
                    new ClearValues("type-" + id, width, height, word, D(c["width"]), D(c["height"]), D(c["offset"]),
                                    c["source"]!.GetValue<string>()), "Fake Architect", Confirmed));
            }
            Marked.Add(new MarkedElement
            {
                UniqueId = uid, BuiltInCategory = Marks.Windows, Name = $"{width * 12:0.##} x {height * 12:0.##}",
                Number = w["name"]!.GetValue<string>(), Family = "Gordium test window", TypeUniqueId = "type-" + id,
                PhaseCreated = LastPhase,
                Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = new(true, w["escape"]!.GetValue<bool>() ? 1 : 0) },
                Type = type,
            });
            var cut = OpeningPlan(cx, cy, ox, oy, width / 2, t);
            Openings.Add(new OpeningRecord
            {
                UniqueId = uid, ToRoom = Uid(w["room"]!.GetValue<string>()), Host = WallOf(w), HostIsWall = true,
                LevelElevation = Fake.Place(0, 0, z).Z, SillHeight = sill, Location = Fake.Place(cx, cy, z),
                Along = Fake.Place(-oy, ox, 0) - Fake.Place(0, 0, 0), TypeWidth = width, TypeHeight = height,
                Placed = WindowFaces(w, t).SelectMany(f => f.Points).ToList(),
                WallOpening = cut.SelectMany(p => new[] { Fake.Place(p.X, p.Y, z + sill), Fake.Place(p.X, p.Y, z + sill + height) }).ToList(),
            });
        }
    }

    public static FakeHouse Draw(string name, Transform3? turn = null) => new(name, turn ?? Transform3.Identity);

    private static string WallOf(JsonObject w)
    {
        var (ox, oy) = P(w["outward"]!);
        return $"wall-{D(w["level"])}-" + (oy < 0 ? "ymin" : ox < 0 ? "xmin" : oy > 0 ? "ymax" : "xmax");
    }

    private static List<(double X, double Y)> Rect(double x0, double y0, double x1, double y1) => [(x0, y0), (x1, y0), (x1, y1), (x0, y1)];

    /// <summary>Where a window cuts its wall, in plan: its width along the wall, the wall's thickness across it.</summary>
    private static List<(double X, double Y)> OpeningPlan(double cx, double cy, double ox, double oy, double half, double t,
                                                          double from = 0, double to = 1)
    {
        double ax = -oy, ay = ox;                         // along the wall (anticlockwise seen from above)
        (double X, double Y) At(double u, double n) => (cx + u * ax + n * ox, cy + u * ay + n * oy);
        return [At(-half, from * t), At(-half, to * t), At(half, to * t), At(half, from * t)];
    }

    /// <summary>The window's frame: a solid in the middle of its wall's thickness, from its sill line up its height.</summary>
    private List<SurfaceRecord> WindowFaces(JsonObject w, double t)
    {
        var (cx, cy) = P(w["center"]!);
        var (ox, oy) = P(w["outward"]!);
        var z = D(w["level"]) + D(w["sill"]);
        return Prism(OpeningPlan(cx, cy, ox, oy, D(w["width"]) / 2, t, 0.25, 0.75), z, z + D(w["height"]));
    }

    private static Xyz Down(List<(double X, double Y, double Z)> pts)
    {
        double nx = 0, ny = 0, nz = 0;
        for (var i = 0; i < pts.Count; i++)
        {
            var (x1, y1, z1) = pts[i];
            var (x2, y2, z2) = pts[(i + 1) % pts.Count];
            nx += (y1 - y2) * (z1 + z2);
            ny += (z1 - z2) * (x1 + x2);
            nz += (x1 - x2) * (y1 + y2);
        }
        var s = Math.Sqrt(nx * nx + ny * ny + nz * nz) * (nz > 0 ? -1 : 1);
        return new(nx / s, ny / s, nz / s);
    }

    /// <summary>A planar face in shared coordinates, as the Revit layer gives it (internal: points and normal turned back).</summary>
    public SurfaceRecord Face(Xyz normal, IEnumerable<(double X, double Y, double Z)> points)
    {
        var pts = points.Select(p => Fake.Place(p.X, p.Y, p.Z)).ToList();
        var n = Fake.Place(normal.X, normal.Y, normal.Z) - Fake.Place(0, 0, 0);
        return new SurfaceRecord(true, n, [pts.Select(p => new LoopCurve(p, true)).ToList()], pts);
    }

    /// <summary>A prism over a plan outline (anticlockwise): top, bottom and a side per edge.</summary>
    public List<SurfaceRecord> Prism(List<(double X, double Y)> plan, double z0, double z1)
    {
        var faces = new List<SurfaceRecord>
        {
            Face(new(0, 0, 1), plan.Select(p => (p.X, p.Y, z1))),
            Face(new(0, 0, -1), plan.Select(p => (p.X, p.Y, z0))),
        };
        for (var i = 0; i < plan.Count; i++)
        {
            var a = plan[i];
            var b = plan[(i + 1) % plan.Count];
            var len = Math.Sqrt((b.X - a.X) * (b.X - a.X) + (b.Y - a.Y) * (b.Y - a.Y));
            faces.Add(Face(new((b.Y - a.Y) / len, -(b.X - a.X) / len, 0), [(a.X, a.Y, z0), (b.X, b.Y, z0), (b.X, b.Y, z1), (a.X, a.Y, z1)]));
        }
        return faces;
    }

    public int RoomIndex(string houseId) => Rooms.FindIndex(r => r.UniqueId == Uid(houseId));

    public int OpeningIndex(string houseId) => Openings.FindIndex(o => o.UniqueId == Uid(houseId));

    public int MarkedIndex(string houseId) => Marked.FindIndex(m => m.UniqueId == Uid(houseId));

    /// <summary>Changes one of a window type's marks (null: the mark cleared, as a blank Revit parameter).</summary>
    public void SetType(string windowId, MarkDefinition mark, MarkValue? value)
    {
        var i = MarkedIndex(windowId);
        var type = new Dictionary<Guid, MarkValue>(Marked[i].Type);
        if (value is null)
            type[mark.Guid] = new MarkValue(false);
        else
            type[mark.Guid] = value;
        Marked[i] = Marked[i] with { Type = type };
    }
}
