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

    public List<StairRecord> Stairs { get; } = [];
    public List<StairCandidate> StairCandidates { get; } = [];
    public Dictionary<Guid, MarkValue> ProjectMarks { get; } = new() { [Marks.AllStairs.Guid] = new(true, 1) };   // ticked
    public int CoordinationModels { get; set; }

    public RevitModel Model() => new()
    {
        Document = Name,
        InternalToShared = Fake.InternalToShared,
        Phases = ["phase-1", LastPhase],
        Marked = Marked,
        UserWorksets = Worksets,
        ProjectMarks = ProjectMarks,
        Interior = new InteriorRecords
        {
            Rooms = Rooms, Openings = Openings, EnclosedAreas = Areas, Links = Links, Stairs = Stairs,
            StairCandidates = StairCandidates, CoordinationModels = CoordinationModels,
        },
    };

    /// <summary>The stair <paramref name="houseId"/>'s record and its one run's index there.</summary>
    public int StairIndex(string houseId) => Stairs.FindIndex(s => s.UniqueId == "stair-" + houseId);

    /// <summary>Changes the one run of stair <paramref name="houseId"/>.</summary>
    public void SetRun(string houseId, Func<RunRecord, RunRecord> change)
    {
        var i = StairIndex(houseId);
        Stairs[i] = Stairs[i] with { Runs = [change(Stairs[i].Runs[0])] };
    }

    /// <summary>Adds something around stair <paramref name="houseId"/>'s run (its box worked out from its faces).</summary>
    public void AddNear(string houseId, NearbyElement e) =>
        SetRun(houseId, r => r with { Near = [.. r.Near!, Boxed(e)] });

    /// <summary>The element with its box (internal, axis-aligned) around its faces, as Revit gives it.</summary>
    public static NearbyElement Boxed(NearbyElement e)
    {
        var pts = (e.Faces ?? []).SelectMany(f => f.Points).ToList();
        return pts.Count == 0 ? e : e with
        {
            Box = new RevitBox(new(pts.Min(p => p.X), pts.Min(p => p.Y), pts.Min(p => p.Z)), new(pts.Max(p => p.X), pts.Max(p => p.Y), pts.Max(p => p.Z))),
        };
    }

    /// <summary>A point of stair <paramref name="st"/>'s frame (s up its path from the first riser, a across it to the
    /// left looking up), in shared plan coordinates.</summary>
    public static (double X, double Y) StairAt(JsonObject st, double s, double a)
    {
        var (x0, y0) = P(st["path"]![0]!);
        var (x1, y1) = P(st["path"]![1]!);
        var len = Math.Sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0));
        double ux = (x1 - x0) / len, uy = (y1 - y0) / len;
        return (x0 + s * ux - a * uy, y0 + s * uy + a * ux);
    }

    /// <summary>A box in a stair's frame, as a prism (its plan anticlockwise in shared coordinates).</summary>
    public List<SurfaceRecord> StairBox(JsonObject st, double s0, double s1, double a0, double a1, double z0, double z1) =>
        Prism([StairAt(st, s0, a0), StairAt(st, s1, a0), StairAt(st, s1, a1), StairAt(st, s0, a1)], z0, z1);

    public JsonObject StairDrawing(string houseId) =>
        Drawing["stairs"]!.AsArray().Select(n => n!.AsObject()).First(s => s["id"]!.GetValue<string>() == houseId);

    /// <summary>Each stair of the drawing as the Revit layer would read the component stair HouseDraw draws: one
    /// straight run whose treads are slabs 1 in thick (their tops the treads), its path from the first riser to the
    /// last, the stair's typed riser and tread equal to the drawn ones; around it the side walls, the floor at its foot
    /// and head, and what is overhead (thin solids whose undersides are the house's pieces).</summary>
    private void DrawStairs()
    {
        foreach (var st in Drawing["stairs"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = st["id"]!.GetValue<string>();
            double b = D(st["base"]), r = D(st["riser"]), t = D(st["tread"]), w = D(st["width"]);
            var n = st["risers"]!.GetValue<int>();
            var faces = new List<SurfaceRecord>();
            for (var k = 1; k < n; k++)
                faces.AddRange(StairBox(st, (k - 1) * t, k * t, -w / 2, w / 2, b + k * r - 1.0 / 12, b + k * r));
            // the last riser, carried up to the run's top as Revit draws it (trial step 4 run 1: a top face more than
            // the treads), its face on the last riser's line
            faces.AddRange(StairBox(st, (n - 1) * t, (n - 1) * t + 1.0 / 12, -w / 2, w / 2, b + (n - 1) * r, b + n * r));
            var near = new List<NearbyElement> { new("run-" + id, "OST_StairsRuns", "Run", Faces: faces) };
            var slab = D(st["slab"]);
            foreach (var (key, what) in new[] { ("foot", "Floor at the foot"), ("head", "Floor at the head") })
            {
                var plan = st[key]!["plan"]!.AsArray().Select(p => P(p!)).ToList();
                if (PlanGeometry.SignedArea(plan.Select(p => new P2(p.X, p.Y)).ToList()) < 0)
                    plan.Reverse();
                var top = D(st[key]!["top"]);
                near.Add(new($"{key}-{id}", "OST_Floors", what, Faces: Prism(plan, top - slab, top)));
            }
            var thick = D(st["wall_thickness"]);
            foreach (var wall in st["walls"]!.AsArray().Select(x => x!.AsObject()))
            {
                var (fx0, fy0) = P(wall["face"]![0]!);
                var (fx1, fy1) = P(wall["face"]![1]!);
                var (ox, oy) = P(wall["outward"]!);
                List<(double X, double Y)> plan = [(fx0, fy0), (fx1, fy1), (fx1 + ox * thick, fy1 + oy * thick), (fx0 + ox * thick, fy0 + oy * thick)];
                if (PlanGeometry.SignedArea(plan.Select(p => new P2(p.X, p.Y)).ToList()) < 0)
                    plan.Reverse();
                near.Add(new($"wall-{id}-{wall["side"]}", "OST_Walls", "Stair wall", Faces: Prism(plan, b, D(st["wall_top"]))));
            }
            foreach (var (piece, k) in st["overhead"]!.AsArray().Select((p, k) => (p!.AsArray(), k)))
            {
                var pts = piece.Select(p => (X: D(p![0]), Y: D(p[1]), Z: D(p[2]))).ToList();
                var thin = D(Drawing["ceiling_thickness"]);
                near.Add(new($"over-{id}-{k}", "OST_Ceilings", "Overhead", Faces: [Face(Down(pts), pts), Face(new(0, 0, 1), pts.Select(p => (p.X, p.Y, p.Z + thin)))]));
            }
            var (px0, py0) = P(st["path"]![0]!);
            var (px1, py1) = P(st["path"]![1]!);
            Stairs.Add(new StairRecord
            {
                UniqueId = "stair-" + id, Name = st["name"]!.GetValue<string>(), IsByComponent = true, PhaseCreated = LastPhase,
                BaseElevation = Fake.Place(px0, py0, b).Z, ActualRiserHeight = r, ActualTreadDepth = t,
                Runs =
                [
                    new RunRecord
                    {
                        UniqueId = "run-" + id, Style = "Straight", BaseElevation = 0, TopElevation = n * r, RisersNumber = n,
                        TreadsNumber = n - 1, BeginsWithRiser = true, EndsWithRiser = true,
                        Path = [Fake.Place(px0, py0, b), Fake.Place(px1, py1, b)], Faces = faces, Near = near.Select(Boxed).ToList(),
                    },
                ],
            });
            Ids[id] = "run-" + id;
        }
    }

    /// <summary>The recording the add-in writes for this reading (RecordHouses.cs), for the interior conformance check.</summary>
    public JsonObject Recording(InteriorReadResult read) => new()
    {
        ["host"] = "revit",
        ["house"] = Name,
        ["step"] = Drawing["step"]!.GetValue<int>(),
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
        DrawStairs();
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
