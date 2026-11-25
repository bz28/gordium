using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading.Tests;

/// <summary>A small commercial story drawn as fake Revit records, the way the Revit layer fills them (escape routes,
/// docs/revit/revit_interior_reading_design.md section 10). One level; walls 6 in thick; in feet, inside faces:
/// <code>
///   y 26 ┌───────────┬───────────────────────────────┐     dE: lobby to outside (Exterior door at discharge)
///        │  stair S  │  lobby L                      │     dS2: stair to outside (unmarked)
///  dS2 → │ 0..10     │  10.5..40 x 16..26            │     dS: corridor to stair (Exit stair enclosure)
///   y 16 ├──dS───────┤- - - - separation line - - - -│     dA, dB: offices to corridor
///        │  corridor C 0..40 x 10..16                │
///   y 10 ├────dA─────────────┬────────dB─────────────┤
///        │  office A         │  office B (column)    │
///        │  0..20 (a desk)   │  20.5..40             │
///   y 0  └───────────────────┴───────────────────────┘
/// </code>
/// The lists are open, so a test can change one thing the way a model can be wrong.</summary>
internal sealed class FakeFloor
{
    public const string Level = "level-1";
    public const string Phase = "phase-1";
    public const double T = 0.5;              // wall thickness
    public const double Clear = 3.0;          // every door's confirmed clear width
    public const double Frame = 3.25;         // its frame's width along the wall
    public const double Height = 7.0;

    public FakeRevit Fake { get; }
    public List<MarkedElement> Marked { get; } = [];
    public List<RoomRecord> Rooms { get; } = [];
    public List<OpeningRecord> Openings { get; } = [];
    public List<EnclosedArea> Areas { get; } = [];
    public List<LevelRecord>? Levels { get; set; }
    public List<string>? SeparationLines { get; set; } = ["sep-1"];
    public Dictionary<string, GrossArea>? GrossAreas { get; set; }

    public RevitModel Model() => new()
    {
        Document = "fake floor",
        InternalToShared = Fake.InternalToShared,
        Phases = [Phase],
        Marked = Marked,
        Interior = new InteriorRecords
        {
            Rooms = Rooms, Openings = Openings, EnclosedAreas = Areas, Levels = Levels, SeparationLines = SeparationLines, GrossAreas = GrossAreas,
            Stairs = [], Railings = [], Ramps = [],
        },
    };

    public static string Uid(string id) => "uid-" + id;

    public FakeFloor(Transform3? turn = null)
    {
        Fake = new FakeRevit(turn ?? Transform3.Identity);
        Levels = [new LevelRecord(Level, "Level 1", Fake.Place(0, 0, 0).Z)];
        // the rooms: each loop's segments with what bounds them
        Room("A", "Office 101", [Seg(0, 0, 20, 0, "wall-s"), Seg(20, 0, 20, 9.5, "wall-ab"), Seg(20, 9.5, 0, 9.5, "wall-c1"), Seg(0, 9.5, 0, 0, "wall-w")],
             "Other", false, false);
        Room("B", "Office 102", [Seg(20.5, 0, 40, 0, "wall-s"), Seg(40, 0, 40, 9.5, "wall-e"), Seg(40, 9.5, 20.5, 9.5, "wall-c1"), Seg(20.5, 9.5, 20.5, 0, "wall-ab")],
             "Other", false, false,
             hole: [Seg(30, 4, 30, 5, "col-1"), Seg(30, 5, 31, 5, "col-1"), Seg(31, 5, 31, 4, "col-1"), Seg(31, 4, 30, 4, "col-1")]);
        Room("C", "Corridor", [Seg(0, 10, 40, 10, "wall-c1"), Seg(40, 10, 40, 16, "wall-e"), Seg(40, 16, 10.5, 16, "sep-1"), Seg(10.5, 16, 0, 16, "wall-c2"), Seg(0, 16, 0, 10, "wall-w")],
             "Corridor", false, false);
        Room("L", "Lobby", [Seg(10.5, 16, 40, 16, "sep-1"), Seg(40, 16, 40, 26, "wall-e"), Seg(40, 26, 10.5, 26, "wall-n"), Seg(10.5, 26, 10.5, 16, "wall-sl")],
             "Lobby", false, true);
        Room("S", "Stair 1", [Seg(0, 16.5, 10, 16.5, "wall-c2"), Seg(10, 16.5, 10, 26, "wall-sl"), Seg(10, 26, 0, 26, "wall-n"), Seg(0, 26, 0, 16.5, "wall-w")],
             "Other", false, false);
        // a desk in office A: a box 4 by 2 ft, 2.5 ft high
        AddOver("A", new NearbyElement("desk-1", "OST_Furniture", "Desk", Faces: Prism([(2, 2), (6, 2), (6, 4), (2, 4)], 0, 2.5)));
        // the column office B goes round (it bounds the room: its second loop)
        AddOver("B", new NearbyElement("col-1", "OST_Columns", "Column", Faces: Prism([(30, 4), (31, 4), (31, 5), (30, 5)], 0, 10)));
        // the doors: in the wall between the faces at n0 and n1 (n across the wall), centred at u along it
        Door("dA", "A", "C", horizontal: true, u: 10, n0: 9.5, n1: 10);
        Door("dB", "B", "C", horizontal: true, u: 30, n0: 9.5, n1: 10);
        Door("dS", "C", "S", horizontal: true, u: 5, n0: 16, n1: 16.5, exit: "Exit stair enclosure");
        Door("dE", "L", null, horizontal: true, u: 25, n0: 26, n1: 26.5, exit: "Exterior door at discharge");
        Door("dS2", "S", null, horizontal: false, u: 21, n0: -0.5, n1: 0);
    }

    public BoundarySegmentRecord Seg(double x0, double y0, double x1, double y1, string by) =>
        new(Fake.Place(x0, y0, 0), Fake.Place(x1, y1, 0), true, by);

    public int RoomIndex(string id) => Rooms.FindIndex(r => r.UniqueId == Uid(id));

    public int MarkedIndex(string id) => Marked.FindIndex(m => m.UniqueId == Uid(id));

    public int OpeningIndex(string id) => Openings.FindIndex(o => o.UniqueId == Uid(id));

    public void AddOver(string room, NearbyElement e)
    {
        var i = RoomIndex(room);
        Rooms[i] = Rooms[i] with { Over = [.. Rooms[i].Over!, Band(e)] };
    }

    /// <summary>What of an element lies in a room's band (floor at 0, from 1/16 in up to 80 in), as the Revit layer's
    /// intersection gives it: for a prism (flat faces only, its plan its bottom face), the prism cut to the band; for any
    /// other shape, its faces that reach the band, as they are (the tests' curved pieces stand within it); a failed
    /// geometry, a failed intersection.</summary>
    public NearbyElement Band(NearbyElement e)
    {
        if (e.Banded is not null || e.BandFailed)
            return e;                                        // the test says what the intersection gives
        if (e.GeometryFailed || e.Faces is null)
            return e with { BandFailed = e.GeometryFailed };
        double lo = InteriorReader.Sixteenth, hi = RouteReader.Headroom;
        var shared = e.Faces.Select(f => f.Points.Select(InternalToSharedPoint).ToList()).ToList();
        var all = shared.SelectMany(p => p).ToList();
        if (all.Count == 0)
            return e with { Banded = [] };
        double z0 = all.Min(q => q.Z), z1 = all.Max(q => q.Z);
        if (z1 <= lo || z0 >= hi)
            return e with { Banded = [] };
        if (e.Faces.All(f => f.Planar))
        {
            var bottom = e.Faces.Select((f, k) => (f, k)).First(x => (Fake.InternalToShared.Apply(x.f.Normal) - Fake.InternalToShared.Apply(new Xyz(0, 0, 0))).Z < -0.5);
            var plan = shared[bottom.k].Select(q => (q.X, q.Y)).ToList();
            return e with { Banded = Prism(plan, Math.Max(z0, lo), Math.Min(z1, hi)) };
        }
        return e with { Banded = e.Faces.Where((f, k) => shared[k].Max(q => q.Z) > lo && shared[k].Min(q => q.Z) < hi).ToList() };
    }

    private Xyz InternalToSharedPoint(Xyz p) => Fake.InternalToShared.Apply(p);

    /// <summary>Sets (a value) or clears (null) one of a room's or door's own marks.</summary>
    public void SetMark(string id, MarkDefinition mark, MarkValue? value)
    {
        var i = MarkedIndex(id);
        var marks = new Dictionary<Guid, MarkValue>(Marked[i].Instance);
        if (value is null)
            marks.Remove(mark.Guid);
        else
            marks[mark.Guid] = value;
        Marked[i] = Marked[i] with { Instance = marks };
    }

    private void Room(string id, string name, List<BoundarySegmentRecord> loop, string use, bool lockable, bool through,
                      List<BoundarySegmentRecord>? hole = null)
    {
        var uid = Uid(id);
        Marked.Add(new MarkedElement
        {
            UniqueId = uid, BuiltInCategory = Marks.Rooms, Name = name, Number = id, PhaseCreated = Phase, Placement = RoomPlacement.Placed,
            Instance = new Dictionary<Guid, MarkValue>
            {
                [Marks.SleepingRoom.Guid] = new(true, 0),
                [Marks.Use.Guid] = new(true, Text: use),
                [Marks.CanBeLocked.Guid] = new(true, lockable ? 1 : 0),
                [Marks.PassThrough.Guid] = new(true, through ? 1 : 0),
            },
        });
        var plan = loop.Select(s => (X: Fake.InternalToShared.Apply(s.Start).X, Y: Fake.InternalToShared.Apply(s.Start).Y)).ToList();
        var ceiling = new NearbyElement("ceiling-" + id, "OST_Ceilings", "Ceiling",
                                        Faces: [Face(new(0, 0, -1), plan.Select(p => (p.X, p.Y, 9.0))), Face(new(0, 0, 1), plan.Select(p => (p.X, p.Y, 9.1)))]);
        var slab = new NearbyElement("slab", "OST_Floors", "Floor", Faces: Prism([(-1, -1), (41, -1), (41, 27), (-1, 27)], -1, 0));
        Rooms.Add(new RoomRecord
        {
            UniqueId = uid, Level = "Level 1", LevelId = Level, LevelElevation = Fake.Place(0, 0, 0).Z, BaseOffset = 0,
            Boundary = hole is null ? [loop] : [loop, hole], Inside = [], Under = [slab],
            Over = [Band(ceiling), Band(new NearbyElement("wall-c1", "OST_Walls", "Wall", Faces: Prism([(0, 9.5), (40, 9.5), (40, 10), (0, 10)], 0, 10)))],
        });
        Areas.Add(new EnclosedArea("Level 1", 100, true, Fake.Place(plan[0].X + 0.5, plan[0].Y + 0.5, 0), Level));
    }

    /// <summary>A door hosted in a straight wall: <paramref name="horizontal"/> for a wall along x (faces at y = n0 and
    /// n1, the door at x = u), else along y. Its frame, a solid within the wall's thickness, <see cref="Frame"/> wide;
    /// its type's confirmed clear opening <see cref="Clear"/> wide.</summary>
    /// <summary>Where each door was drawn (<see cref="Door"/>): along x (horizontal) or y, its centre u along the wall,
    /// its wall's faces at n0 and n1 across it.</summary>
    public Dictionary<string, (bool Horizontal, double U, double N0, double N1)> Drawn { get; } = [];

    /// <summary>Draws a swing in a door's plan symbol, as the Revit layer reads it in its plan view: a leaf of
    /// <paramref name="radius"/> (the clear width when not given) hinged at the jamb on the side <paramref name="hinge"/>
    /// (-1: toward smaller u, +1: larger) on the face at n1 (<paramref name="into"/> +1: it swings toward larger n) or
    /// n0 (-1), its arc's middle half way between closed (along the wall) and open 90 degrees. Adds to its arcs.</summary>
    public void Swing(string id, int into, int hinge = -1, double? radius = null, double? hingeN = null)
    {
        var (horizontal, u, n0, n1) = Drawn[id];
        var r = radius ?? Clear;
        var pinU = u + hinge * Clear / 2;
        var pinN = hingeN ?? (into > 0 ? n1 : n0);
        var midU = pinU - hinge * r * Math.Cos(Math.PI / 4);
        var midN = pinN + into * r * Math.Sin(Math.PI / 4);
        (double X, double Y) At(double a, double n) => horizontal ? (a, n) : (n, a);
        var (cx, cy) = At(pinU, pinN);
        var (mx, my) = At(midU, midN);
        AddArc(id, new SwingArc(Fake.Place(cx, cy, 0), r, Fake.Place(mx, my, 0)));
    }

    /// <summary>Adds an arc to a door's plan symbol as read (a drawing that read none yet starts empty).</summary>
    public void AddArc(string id, SwingArc arc)
    {
        var i = OpeningIndex(id);
        Openings[i] = Openings[i] with { Swing = new SwingDrawing([.. Openings[i].Swing?.Arcs ?? [], arc]) };
    }

    public void Door(string id, string from, string? to, bool horizontal, double u, double n0, double n1, string? exit = null)
    {
        var uid = Uid(id);
        Drawn[id] = (horizontal, u, n0, n1);
        const string word = "Side-hinged door";
        var type = new Dictionary<Guid, MarkValue>
        {
            [Marks.Operation.Guid] = new(true, Text: word),
            [Marks.ClearWidth.Guid] = new(true, Number: Clear),
            [Marks.ClearHeight.Guid] = new(true, Number: 6.75),
            [Marks.ClearSource.Guid] = new(true, Text: "Maker catalogue 2026"),
            [Marks.ClearConfirmed.Guid] = new(true, Text: ClearStamp.Make(
                new ClearValues("type-" + id, Frame, Height, word, Clear, 6.75, null, "Maker catalogue 2026", Door: true), "Fake Architect", "2026-11-21")),
        };
        var instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = new(true, 0), [Marks.ExitDoor.Guid] = new(true, 0) };
        if (exit is not null)
            instance[Marks.Exit.Guid] = new(true, Text: exit);
        Marked.Add(new MarkedElement
        {
            UniqueId = uid, BuiltInCategory = Marks.Doors, Name = "36 x 84", Number = id, Family = "Single door",
            TypeUniqueId = "type-" + id, PhaseCreated = Phase, Instance = instance, Type = type, TypeWidth = Frame, TypeHeight = Height,
        });
        (double X, double Y) At(double a, double n) => horizontal ? (a, n) : (n, a);
        var frame = new List<(double X, double Y)> { At(u - Frame / 2, n0), At(u + Frame / 2, n0), At(u + Frame / 2, n1), At(u - Frame / 2, n1) };
        if (PlanGeometry.SignedArea(frame.Select(p => new P2(p.X, p.Y)).ToList()) < 0)
            frame.Reverse();
        var (cx, cy) = At(u, (n0 + n1) / 2);
        Openings.Add(new OpeningRecord
        {
            UniqueId = uid, FromRoom = Uid(from), ToRoom = to is null ? null : Uid(to), Host = "wall-of-" + id, HostIsWall = true,
            LevelElevation = Fake.Place(0, 0, 0).Z, LevelId = Level, SillHeight = 0, Location = Fake.Place(cx, cy, 0),
            Along = Fake.Place(horizontal ? 1 : 0, horizontal ? 0 : 1, 0) - Fake.Place(0, 0, 0), TypeWidth = Frame, TypeHeight = Height,
            Placed = Prism(frame, 0, Height).SelectMany(f => f.Points).ToList(),
            WallOpening = frame.SelectMany(p => new[] { Fake.Place(p.X, p.Y, 0), Fake.Place(p.X, p.Y, Height) }).ToList(),   // the rough opening it cuts
            WallSides =
            [
                new WallFace(Fake.Place(At(0, n0).X, At(0, n0).Y, 0), Fake.Place(horizontal ? 0 : -1, horizontal ? -1 : 0, 0) - Fake.Place(0, 0, 0)),
                new WallFace(Fake.Place(At(0, n1).X, At(0, n1).Y, 0), Fake.Place(horizontal ? 0 : 1, horizontal ? 1 : 0, 0) - Fake.Place(0, 0, 0)),
            ],
        });
    }

    /// <summary>A planar face in shared coordinates, as the Revit layer gives it (internal).</summary>
    public SurfaceRecord Face(Xyz normal, IEnumerable<(double X, double Y, double Z)> points)
    {
        var pts = points.Select(p => Fake.Place(p.X, p.Y, p.Z)).ToList();
        var n = Fake.Place(normal.X, normal.Y, normal.Z) - Fake.Place(0, 0, 0);
        return new SurfaceRecord(true, n, [pts.Select(p => new LoopCurve(p, true)).ToList()], pts);
    }

    /// <summary>A prism over a plan outline (anticlockwise): top, bottom and a side per edge.</summary>
    public List<SurfaceRecord> Prism(List<(double X, double Y)> plan, double z0, double z1)
    {
        var faces = new List<SurfaceRecord> { Face(new(0, 0, 1), plan.Select(p => (p.X, p.Y, z1))), Face(new(0, 0, -1), plan.Select(p => (p.X, p.Y, z0))) };
        for (var i = 0; i < plan.Count; i++)
        {
            var a = plan[i];
            var b = plan[(i + 1) % plan.Count];
            var len = Math.Sqrt((b.X - a.X) * (b.X - a.X) + (b.Y - a.Y) * (b.Y - a.Y));
            faces.Add(Face(new((b.Y - a.Y) / len, -(b.X - a.X) / len, 0), [(a.X, a.Y, z0), (b.X, b.Y, z0), (b.X, b.Y, z1), (a.X, a.Y, z1)]));
        }
        return faces;
    }

    /// <summary>The description's part with this id (a room or a door).</summary>
    public static JsonObject? Part(InteriorReadResult r, string key, string id) =>
        r.Interior[key]?.AsArray().Select(x => x!.AsObject()).FirstOrDefault(x => x["id"]!.GetValue<string>() == Uid(id));

    public static string? Note(InteriorReadResult r, string id, string field) =>
        r.Notes.Concat(r.RouteNotes).FirstOrDefault(n => n.Part == Uid(id) && n.Field == field)?.Why;
}
