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
    public List<RailingRecord>? Railings { get; set; } = [];
    public List<RampRecord>? Ramps { get; set; } = [];
    public Dictionary<Guid, MarkValue> ProjectMarks { get; } = new() { [Marks.AllStairs.Guid] = new(true, 1) };   // ticked
    public int CoordinationModels { get; set; }

    /// <summary>The grounds drawn (Toposolids), none by default (no ground: nothing read at the openings).</summary>
    public List<GroundRecord>? Grounds { get; set; }

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
            StairCandidates = StairCandidates, CoordinationModels = CoordinationModels, Railings = Railings, Ramps = Ramps,
            Grounds = Grounds,
        },
    };

    /// <summary>A Toposolid over the whole drawing (shared plan coordinates, ft, <paramref name="reach"/> each way of the
    /// origin) whose top is <paramref name="z"/> at the corners of a grid (its lines at <paramref name="xs"/> and
    /// <paramref name="ys"/> besides its edges: planes between), two triangles a cell, turned into internal coordinates as
    /// the Revit layer gives them.</summary>
    public GroundRecord Toposolid(Func<double, double, double> z, string id = "topo-1", string? name = "Finished grade",
                                  string? host = null, double reach = 100, double[]? xs = null, double[]? ys = null)
    {
        Xyz At(double x, double y) => Fake.Place(x, y, z(x, y));
        var gx = (xs ?? []).Append(-reach).Append(reach).Distinct().Order().ToList();
        var gy = (ys ?? []).Append(-reach).Append(reach).Distinct().Order().ToList();
        var triangles = new List<GroundTriangle>();
        for (var i = 0; i + 1 < gx.Count; i++)
            for (var j = 0; j + 1 < gy.Count; j++)
            {
                Xyz a = At(gx[i], gy[j]), b = At(gx[i + 1], gy[j]), c = At(gx[i + 1], gy[j + 1]), d = At(gx[i], gy[j + 1]);
                triangles.Add(new GroundTriangle(a, b, c));
                triangles.Add(new GroundTriangle(a, c, d));
            }
        return new GroundRecord(id, "Toposolid", name, triangles, Host: host);
    }

    /// <summary>The architect's word that the Toposolids show the finished ground (Project Information).</summary>
    public void FinishedGround(bool? yes) => SetProject(Marks.ToposolidFinished, yes is { } y ? new MarkValue(true, y ? 1 : 0) : null);

    private void SetProject(MarkDefinition mark, MarkValue? value)
    {
        if (value is null)
            ProjectMarks.Remove(mark.Guid);
        else
            ProjectMarks[mark.Guid] = value;
    }

    /// <summary>The drawing's rail width and a handrail's top over the line of nosings (recordings.py's RAIL, HANDRAIL_TOP).</summary>
    public double Rail => D(Drawing["rail"]);

    public int RailingIndex(string uid) => Railings!.FindIndex(r => r.UniqueId == uid);

    /// <summary>Changes the railing <paramref name="uid"/>, and the same parts wherever a run lists them nearby.</summary>
    public void SetRailing(string uid, Func<RailingRecord, RailingRecord> change)
    {
        var i = RailingIndex(uid);
        Railings![i] = change(Railings[i]);
        var r = Railings[i];
        for (var k = 0; k < Stairs.Count; k++)
        {
            var run = Stairs[k].Runs[0];
            if (run.Near is null)
                continue;
            var near = run.Near.Where(e => r.Parts.All(p => p.UniqueId != e.UniqueId)).ToList();
            if (near.Count == run.Near.Count)
                continue;
            near.AddRange(r.Parts.Select(PartNear));
            Stairs[k] = Stairs[k] with { Runs = [run with { Near = near }] };
        }
    }

    /// <summary>A railing part as the Revit layer lists it near a run: its category, its solids' faces, its box.</summary>
    public static NearbyElement PartNear(RailingPart p) => Boxed(new NearbyElement(
        p.UniqueId, p.Kind switch { RailingPartKind.TopRail => "OST_RailingTopRail", RailingPartKind.Handrail => "OST_RailingHandRail", _ => "OST_StairsRailing" },
        p.Kind.ToString(), Faces: p.Solids?.SelectMany(s => s).ToList(), GeometryFailed: p.GeometryFailed));

    /// <summary>A solid from its 8 corners (the 4 of its bottom, then the 4 of its top above them, each anticlockwise
    /// seen from above): 6 flat faces, each normal facing out (Newell's, turned away from the middle).</summary>
    public List<SurfaceRecord> Hexahedron(IReadOnlyList<(double X, double Y, double Z)> c)
    {
        int[][] quads = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]];
        var mid = (X: c.Average(p => p.X), Y: c.Average(p => p.Y), Z: c.Average(p => p.Z));
        var faces = new List<SurfaceRecord>();
        foreach (var q in quads)
        {
            var pts = q.Select(i => c[i]).ToList();
            double nx = 0, ny = 0, nz = 0;
            for (var i = 0; i < 4; i++)
            {
                var (x1, y1, z1) = pts[i];
                var (x2, y2, z2) = pts[(i + 1) % 4];
                nx += (y1 - y2) * (z1 + z2);
                ny += (z1 - z2) * (x1 + x2);
                nz += (x1 - x2) * (y1 + y2);
            }
            var len = Math.Sqrt(nx * nx + ny * ny + nz * nz);
            var (fx, fy, fz) = (pts.Average(p => p.X) - mid.X, pts.Average(p => p.Y) - mid.Y, pts.Average(p => p.Z) - mid.Z);
            var sign = nx * fx + ny * fy + nz * fz < 0 ? -1 : 1;
            faces.Add(Face(new(sign * nx / len, sign * ny / len, sign * nz / len), pts));
        }
        return faces;
    }

    /// <summary>A point's place in a stair's frame: (s up its path from the first riser, a across it to the left).</summary>
    public static (double S, double A) StairFrame(JsonObject st, double x, double y)
    {
        var (x0, y0) = P(st["path"]![0]!);
        var (x1, y1) = P(st["path"]![1]!);
        var len = Math.Sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0));
        double ux = (x1 - x0) / len, uy = (y1 - y0) / len;
        return ((x - x0) * ux + (y - y0) * uy, -(x - x0) * uy + (y - y0) * ux);
    }

    /// <summary>Each handrail of each stair as the railing HouseDraw puts on it: hosted by the stair, with no balusters,
    /// its top rail (RAIL square, its top HANDRAIL_TOP over the line of nosings, along its path from the first riser to
    /// the last) the handrail, its type marked so.</summary>
    private void DrawHandrails()
    {
        foreach (var st in Drawing["stairs"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = st["id"]!.GetValue<string>();
            double b = D(st["base"]), r = D(st["riser"]), t = D(st["tread"]), top = D(Drawing["handrail_top"]);
            var n = st["risers"]!.GetValue<int>();
            double Nosing(double s) => b + r + s * r / t;
            var k = StairIndex(id);
            foreach (var h in st["handrails"]!.AsArray().Select(x => x!.AsObject()))
            {
                var side = h["side"]!.GetValue<string>();
                var (px, py) = P(h["path"]![0]!);
                var a = StairFrame(st, px, py).A;
                double s0 = 0, s1 = (n - 1) * t, a0 = a - Rail / 2, a1 = a + Rail / 2;
                var corners = new List<(double X, double Y, double Z)>();
                foreach (var lift in new[] { top - Rail, top })
                    foreach (var (s, aa) in new[] { (s0, a0), (s1, a0), (s1, a1), (s0, a1) })
                    {
                        var (x, y) = StairAt(st, s, aa);
                        corners.Add((x, y, Nosing(s) + lift));
                    }
                var uid = $"railing-{id}-{side}";
                var parts = new List<RailingPart> { new(uid, RailingPartKind.Railing, []), new($"toprail-{id}-{side}", RailingPartKind.TopRail, [Hexahedron(corners)]) };
                Railings!.Add(new RailingRecord
                {
                    UniqueId = uid, Name = "Gordium test handrail", Host = "stair-" + id,
                    Path = [new PathCurve(Fake.Place(px, py, b), Fake.Place(D(h["path"]![1]![0]), D(h["path"]![1]![1]), b), true)],
                    BaseLevelElevation = Fake.Place(0, 0, b).Z, BaseOffset = 0,
                    TypeMarks = new Dictionary<Guid, MarkValue> { [Marks.TopRailIsHandrail.Guid] = new(true, 1) },
                    Parts = parts,
                });
                Stairs[k] = Stairs[k] with
                {
                    Railings = [.. Stairs[k].Railings, uid],
                    Runs = [Stairs[k].Runs[0] with { Near = [.. Stairs[k].Runs[0].Near!, .. parts.Select(PartNear)] }],
                };
            }
        }
    }

    /// <summary>Each level guard as HouseDraw draws it: a railing along the edge of a floor, its balusters and rails
    /// boxes RAIL deep centred on its path, its top rail its own part, a wall at its start and a post (a short wall) at
    /// its end.</summary>
    private void DrawGuards()
    {
        foreach (var g in Drawing["guards"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = g["id"]!.GetValue<string>();
            var uid = "railing-" + id;
            Ids[id] = uid;
            var z = D(g["level"]);
            var (x0, y0) = P(g["start"]!);
            var (x1, y1) = P(g["end"]!);
            var len = D(g["length"]);
            double ux = (x1 - x0) / len, uy = (y1 - y0) / len;
            List<SurfaceRecord> Box(double u0, double u1, double z0, double z1)
            {
                var c = new List<(double X, double Y, double Z)>();
                foreach (var zz in new[] { z0, z1 })
                    foreach (var (u, n) in new[] { (u0, -Rail / 2), (u1, -Rail / 2), (u1, Rail / 2), (u0, Rail / 2) })
                        c.Add((x0 + u * ux - n * uy, y0 + u * uy + n * ux, zz));
                return Hexahedron(c);
            }
            var tr = g["top_rail"]!;
            var railing = new List<IReadOnlyList<SurfaceRecord>>();
            foreach (var rail in g["rails"]!.AsArray())
                railing.Add(Box(0, len, z + D(rail!["bottom"]), z + D(rail["top"])));
            var bal = g["balusters"]!;
            for (var k = 0; k < bal["count"]!.GetValue<int>(); k++)
            {
                var left = D(bal["first"]) + k * D(bal["spacing"]);
                railing.Add(Box(left, left + D(bal["width"]), z + D(bal["bottom"]), z + D(bal["top"])));
            }
            var parts = new List<RailingPart>
            {
                new(uid, RailingPartKind.Railing, railing),
                new("toprail-" + id, RailingPartKind.TopRail, [Box(0, len, z + D(tr["bottom"]), z + D(tr["top"]))]),
            };
            var near = new List<NearbyElement>();
            var floor = g["floor"]!.AsArray().Select(p => P(p!)).ToList();
            near.Add(new("guardfloor-" + id, "OST_Floors", "Floor at the guard", Faces: Prism(floor, z - D(g["slab"]), z)));
            foreach (var (w, k) in g["end_walls"]!.AsArray().Select((w, k) => (w!, k)))
            {
                var (ax, ay) = P(w["line"]![0]!);
                var (bx, by) = P(w["line"]![1]!);
                var half = D(w["thickness"]) / 2;
                near.Add(new($"guardwall-{id}-{k}", "OST_Walls", "Guard end", Faces: Prism(Rect(ax - half, Math.Min(ay, by), ax + half, Math.Max(ay, by)), z, z + D(g["wall_top"]))));
            }
            near.AddRange(parts.Select(PartNear));
            Railings!.Add(new RailingRecord
            {
                UniqueId = uid, Name = g["name"]!.GetValue<string>(),
                Path = [new PathCurve(Fake.Place(x0, y0, z), Fake.Place(x1, y1, z), true)],
                BaseLevelElevation = Fake.Place(0, 0, z).Z, BaseOffset = 0, Parts = parts, Near = near.Select(Boxed).ToList(),
                TypeMarks = new Dictionary<Guid, MarkValue> { [Marks.TopRailIsHandrail.Guid] = new(true, 0) },
            });
        }
    }

    /// <summary>Each door as HouseDraw places it: hosted in its room's outside wall, at the level, with its marks (Escape
    /// opening No, Exit door as the house says, its type's Operation), its leaf a solid of its family's size, and, where
    /// the drawing has one, its type's maker's clear opening confirmed with a door's stamp.</summary>
    private void DrawDoors(double t)
    {
        foreach (var d in Drawing["doors"]!.AsArray().Select(n => n!.AsObject()))
        {
            var id = d["id"]!.GetValue<string>();
            var uid = Uid(id);
            Ids[id] = uid;
            var z = D(d["level"]);
            var (cx, cy) = P(d["center"]!);
            var (ox, oy) = P(d["outward"]!);
            double width = D(d["width"]), height = D(d["height"]);
            var word = Operations.Words.First(x => Operations.ForDoor(x) == d["operation"]!.GetValue<string>());
            var type = new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: word) };
            if (d["clear"] is JsonObject c)
            {
                type[Marks.ClearWidth.Guid] = new(true, Number: D(c["width"]));
                type[Marks.ClearHeight.Guid] = new(true, Number: D(c["height"]));
                type[Marks.ClearSource.Guid] = new(true, Text: c["source"]!.GetValue<string>());
                type[Marks.ClearConfirmed.Guid] = new(true, Text: ClearStamp.Make(
                    new ClearValues("type-" + id, width, height, word, D(c["width"]), D(c["height"]), null, c["source"]!.GetValue<string>(), Door: true),
                    "Fake Architect", Confirmed));
            }
            Marked.Add(new MarkedElement
            {
                UniqueId = uid, BuiltInCategory = Marks.Doors, Name = $"{width * 12:0.##} x {height * 12:0.##}",
                Number = d["name"]!.GetValue<string>(), Family = "Gordium test door", TypeUniqueId = "type-" + id, PhaseCreated = LastPhase,
                Instance = new Dictionary<Guid, MarkValue>
                {
                    [Marks.EscapeOpening.Guid] = new(true, 0),
                    [Marks.ExitDoor.Guid] = new(true, d["exit"]!.GetValue<bool>() ? 1 : 0),
                },
                Type = type,
            });
            Openings.Add(new OpeningRecord
            {
                UniqueId = uid, ToRoom = Uid(d["room"]!.GetValue<string>()), Host = DoorWall(d), HostIsWall = true,
                LevelElevation = Fake.Place(0, 0, z).Z, SillHeight = 0, Location = Fake.Place(cx, cy, z),
                Along = Fake.Place(-oy, ox, 0) - Fake.Place(0, 0, 0), TypeWidth = width, TypeHeight = height,
                Placed = Prism(OpeningPlan(cx, cy, ox, oy, width / 2, Thick(d, t), 0.25, 0.75), z, z + height).SelectMany(f => f.Points).ToList(),
            });
        }
    }

    private static string DoorWall(JsonObject d)
    {
        if (d["wall"] is JsonNode index)
            return $"wall-{D(d["level"])}-{index.GetValue<int>()}";
        var (ox, oy) = P(d["outward"]!);
        return $"wall-{D(d["level"])}-" + (oy < 0 ? "ymin" : ox < 0 ? "xmin" : oy > 0 ? "ymax" : "xmax");
    }

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
            // the last riser board as Revit 2027.4 draws it (trial step 4 run 2, house 2: a top face 1/2 in deep along
            // the path, 12.5 to 12.5417 ft, 9.75 ft up: the run's top less its 3 in tread), its face on the last riser's line
            faces.AddRange(StairBox(st, (n - 1) * t, (n - 1) * t + 0.5 / 12, -w / 2, w / 2, b + (n - 1) * r, b + n * r - 3.0 / 12));
            var near = new List<NearbyElement> { new("run-" + id, "OST_StairsRuns", "Run", Faces: faces) };
            var slab = D(st["slab"]);
            if (st["upper_floor"] is JsonObject upper)
            {
                // one floor around the stairwell opening (its edge on the last riser's line), as a real model has it
                var top = D(upper["top"]);
                near.Add(new("head-" + id, "OST_Floors", "Upper floor",
                             Faces: PrismWithHole(Ccw(upper["outer"]!), Ccw(upper["hole"]!), top - slab, top)));
            }
            foreach (var (key, what) in new[] { ("foot", "Floor at the foot"), ("head", "Floor at the head") })
            {
                if (st[key] is null)
                    continue;
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
                // its top faces up along the piece's own slope (house 4's roof rises 1 in 2), as Revit's extrusion's does
                // and its sides are faces too (a quad piece: the whole extrusion, as HouseDraw's DirectShape has it)
                var down = Down(pts);
                near.Add(new($"over-{id}-{k}", "OST_Ceilings", "Overhead",
                             Faces: pts.Count == 4 ? Hexahedron([.. pts, .. pts.Select(p => (p.X, p.Y, p.Z + thin))])
                                 : [Face(down, pts), Face(new(-down.X, -down.Y, -down.Z), pts.Select(p => (p.X, p.Y, p.Z + thin)))]));
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
            var h = D(level["wall_height"]);
            var list = new List<NearbyElement>();
            // the opening each window cuts in its wall: its head (an underside, inside the wall's thickness) and its sill
            List<SurfaceRecord> Cut(string id, List<SurfaceRecord> faces)
            {
                foreach (var w in windowsOn.GetValueOrDefault(id, []))
                {
                    var (cx, cy) = P(w["center"]!);
                    var (ox, oy) = P(w["outward"]!);
                    var half = D(w["width"]) / 2;
                    var top = z + D(w["sill"]) + D(w["height"]);
                    var cut = OpeningPlan(cx, cy, ox, oy, half, Thick(w, t));
                    faces.Add(Face(new(0, 0, -1), cut.Select(p => (p.X, p.Y, top))));
                    faces.Add(Face(new(0, 0, 1), cut.Select(p => (p.X, p.Y, z + D(w["sill"])))));
                }
                return faces;
            }
            if (level["walls"] is JsonArray placed)
            {
                // a house placed by its layout: each of its walls as drawn, no box; the floor under its outline
                foreach (var (k, f) in placed.Select((f, k) => (k, f!)))
                {
                    var (fx0, fy0) = P(f[0]!);
                    var (fx1, fy1) = P(f[1]!);
                    var id = $"wall-{z}-{k}";
                    list.Add(new NearbyElement(id, "OST_Walls", "Generic wall", Faces: Cut(id, Prism(Rect(fx0, fy0, fx1, fy1), z, z + h))));
                }
                walls[z] = list;
                slabs[z] = new NearbyElement($"slab-{z}", "OST_Floors", "Generic floor", Faces: Prism(Ccw(level["outline"]!), z - D(level["slab"]), z));
                continue;
            }
            var (x0, y0) = P(level["box"]![0]!);
            var (x1, y1) = P(level["box"]![1]!);
            foreach (var (side, plan) in new[]
                     {
                         ("ymin", Rect(x0 - t, y0 - t, x1 + t, y0)), ("xmin", Rect(x0 - t, y0, x0, y1)),
                         ("ymax", Rect(x0 - t, y1, x1 + t, y1 + t)), ("xmax", Rect(x1, y0, x1 + t, y1)),
                     })
            {
                var id = $"wall-{z}-{side}";
                list.Add(new NearbyElement(id, "OST_Walls", "Generic exterior", Faces: Cut(id, Prism(plan, z, z + h))));
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
            var floor = room["floor"]!.AsArray().Select(p => P(p!)).ToList();
            var segments = new List<BoundarySegmentRecord>();
            if (room["boundary"] is JsonArray boundary)
            {
                // a placed house: each edge piece with the wall the drawing says bounds it, else a separation line
                foreach (var (seg, i) in boundary.Select((x, i) => (x!.AsArray(), i)))
                {
                    var (ax, ay) = P(seg[0]!);
                    var (bx, by) = P(seg[1]!);
                    var element = seg[2] is JsonNode k ? $"wall-{z}-{k.GetValue<int>()}" : $"separation-{z}-{i}";
                    segments.Add(new(Fake.Place(ax, ay, z), Fake.Place(bx, by, z), true, element));
                }
            }
            var (bx0, by0) = level["box"] is JsonArray box ? P(box[0]!) : (double.NaN, double.NaN);
            var (bx1, by1) = level["box"] is JsonArray box1 ? P(box1[1]!) : (double.NaN, double.NaN);
            for (var i = 0; i < floor.Count && room["boundary"] is null; i++)
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
                                               Host: WallOf(w.AsObject()), Faces: WindowFaces(w.AsObject(), Thick(w.AsObject(), t)))));
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
            var cut = OpeningPlan(cx, cy, ox, oy, width / 2, Thick(w, t));
            var wall = Thick(w, t);
            Openings.Add(new OpeningRecord
            {
                UniqueId = uid, ToRoom = Uid(w["room"]!.GetValue<string>()), Host = WallOf(w), HostIsWall = true,
                LevelElevation = Fake.Place(0, 0, z).Z, SillHeight = sill, Location = Fake.Place(cx, cy, z),
                Along = Fake.Place(-oy, ox, 0) - Fake.Place(0, 0, 0), TypeWidth = width, TypeHeight = height,
                Placed = WindowFaces(w, Thick(w, t)).SelectMany(f => f.Points).ToList(),
                WallOpening = cut.SelectMany(p => new[] { Fake.Place(p.X, p.Y, z + sill), Fake.Place(p.X, p.Y, z + sill + height) }).ToList(),
                // the wall's two side faces: the room's at the window's centre line, the outside one a wall's thickness out
                // (its cut, OpeningPlan, runs from one to the other); nothing stands outside it
                WallSides =
                [
                    new WallFace(Fake.Place(cx + wall * ox, cy + wall * oy, z), Fake.Place(ox, oy, 0) - Fake.Place(0, 0, 0)),
                    new WallFace(Fake.Place(cx, cy, z), Fake.Place(-ox, -oy, 0) - Fake.Place(0, 0, 0)),
                ],
                Around = [],
            });
        }
        DrawStairs();
        DrawHandrails();
        DrawGuards();
        DrawDoors(t);
        foreach (var d in Drawing["doors"]!.AsArray().Select(n => n!.AsObject()))
        {
            var i = Rooms.FindIndex(r => r.UniqueId == Uid(d["room"]!.GetValue<string>()));
            Rooms[i] = Rooms[i] with { Over = [.. Rooms[i].Over!, new NearbyElement(Uid(d["id"]!.GetValue<string>()), "OST_Doors", "Gordium test door", Host: DoorWall(d))] };
        }
        // the architect's tick once every guard and handrail is drawn as a railing (as HouseDraw sets it)
        var notDrawn = Drawing["not_drawn"]!.AsArray().Select(n => n!.GetValue<string>()).ToList();
        if (!notDrawn.Contains("guards") && !notDrawn.Contains("handrails"))
            ProjectMarks[Marks.AllGuards.Guid] = new(true, 1);
        // step 6: the "this house has none of" ticks the drawing names (as HouseDraw sets them)
        foreach (var kind in Drawing["has_none"]!.AsArray().Select(n => n!.GetValue<string>()))
            ProjectMarks[HasNone.All.Single(k => k.Kind == kind).Mark.Guid] = new(true, 1);
    }

    public static FakeHouse Draw(string name, Transform3? turn = null) => new(name, turn ?? Transform3.Identity);

    private static string WallOf(JsonObject w)
    {
        if (w["wall"] is JsonNode index)                  // a placed house: its wall by index in its level's walls
            return $"wall-{D(w["level"])}-{index.GetValue<int>()}";
        var (ox, oy) = P(w["outward"]!);
        return $"wall-{D(w["level"])}-" + (oy < 0 ? "ymin" : ox < 0 ? "xmin" : oy > 0 ? "ymax" : "xmax");
    }

    private static List<(double X, double Y)> Rect(double x0, double y0, double x1, double y1) => [(x0, y0), (x1, y0), (x1, y1), (x0, y1)];

    /// <summary>The thickness of the wall an opening is in: its own (a placed house's walls differ), else the exterior
    /// wall's.</summary>
    private static double Thick(JsonObject o, double t) => o["wall_thickness"] is JsonNode w ? w.GetValue<double>() : t;

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

    private static List<(double X, double Y)> Ccw(JsonNode n)
    {
        var plan = n.AsArray().Select(p => P(p!)).ToList();
        if (PlanGeometry.SignedArea(plan.Select(p => new P2(p.X, p.Y)).ToList()) < 0)
            plan.Reverse();
        return plan;
    }

    /// <summary>A slab over an outline with an opening (both anticlockwise): its top and bottom faces each two loops
    /// (the outline, then the opening), a side per outline edge facing out, a side per opening edge facing in.</summary>
    public List<SurfaceRecord> PrismWithHole(List<(double X, double Y)> outer, List<(double X, double Y)> hole, double z0, double z1)
    {
        SurfaceRecord Flat(double z, double nz)
        {
            var o = outer.Select(p => Fake.Place(p.X, p.Y, z)).ToList();
            var h = hole.Select(p => Fake.Place(p.X, p.Y, z)).ToList();
            var n = Fake.Place(0, 0, nz) - Fake.Place(0, 0, 0);
            return new SurfaceRecord(true, n, [o.Select(p => new LoopCurve(p, true)).ToList(), h.Select(p => new LoopCurve(p, true)).ToList()], o.Concat(h).ToList());
        }
        var faces = new List<SurfaceRecord> { Flat(z1, 1), Flat(z0, -1) };
        foreach (var (ring, outward) in new[] { (outer, 1.0), (hole, -1.0) })
            for (var i = 0; i < ring.Count; i++)
            {
                var a = ring[i];
                var b = ring[(i + 1) % ring.Count];
                var len = Math.Sqrt((b.X - a.X) * (b.X - a.X) + (b.Y - a.Y) * (b.Y - a.Y));
                faces.Add(Face(new(outward * (b.Y - a.Y) / len, -outward * (b.X - a.X) / len, 0), [(a.X, a.Y, z0), (b.X, b.Y, z0), (b.X, b.Y, z1), (a.X, a.Y, z1)]));
            }
        return faces;
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
