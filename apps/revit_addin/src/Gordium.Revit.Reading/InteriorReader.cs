using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>Why one value of one part was left out (the description has no place for a reason: the add-in shows it
/// beside the row, design note section 2).</summary>
/// <param name="Part">The part's id (its <c>UniqueId</c>).</param>
/// <param name="Field">The description's key left out (<c>floor</c>, <c>stated_clear</c>…).</param>
/// <param name="Why">In the architect's words.</param>
public sealed record InteriorNote(string Part, string Field, string Why);

/// <summary>What the interior reader sends, and why anything was left out.</summary>
/// <param name="Interior">The interior description (<c>gordium.interior/1</c>, feet, shared coordinates).</param>
/// <param name="RoomsNotRead">Why <c>rooms</c> was left out (empty when it was sent).</param>
/// <param name="OpeningsNotRead">Why <c>openings</c> was left out (empty when it was sent).</param>
/// <param name="Notes">Each value left out of a part, with its reason.</param>
/// <param name="Evidence">Per escape window: the sill line, the wall opening's bottom and the window's placed extents
/// the clear opening was checked against (shared coordinates, feet): the trial's record that the check can be made.</param>
public sealed record InteriorReadResult(JsonObject Interior, IReadOnlyList<string> RoomsNotRead,
                                        IReadOnlyList<string> OpeningsNotRead, IReadOnlyList<InteriorNote> Notes,
                                        JsonObject Evidence);

/// <summary>
/// The interior reader, section 7 step 3 of docs/revit/revit_interior_reading_design.md: the rooms and the windows and
/// doors that can be escape openings, as the interior description (<c>gordium.interior/1</c>). Its rules are the
/// note's section 2: a mark never set is not given; nothing found is never "none" (a kind with nothing found is left
/// out, never an empty list); every room counts (an enclosed area with no Room, an unplaced Room, a closed workset or
/// an unloaded link leaves <c>rooms</c> out); a part found is never dropped (a value that can't be read exactly is left
/// out, with its reason in <see cref="InteriorReadResult.Notes"/>); a value is sent only when what is drawn agrees
/// with it (a room's floor elevation against the slab under it, a window's sill line against the opening it cuts).
/// Stairs, doors, guards and what the house has none of are later steps: left out (not read).
/// </summary>
public static class InteriorReader
{
    /// <summary>1/16 in, in feet: the measuring code's drawing-noise allowance.</summary>
    public const double Sixteenth = 1.0 / 16 / 12;

    /// <summary>How far above or below a room's floor a slab top is looked for (ft).</summary>
    public const double SlabBand = 1.0;

    /// <summary>Not ceilings, and not what stands in a room's way (design note, section 4: furniture, casework,
    /// furniture systems, plumbing fixtures, specialty equipment and lighting fixtures), with the room and its
    /// separation lines.</summary>
    public static readonly IReadOnlySet<string> NotBuilding = new HashSet<string>(StringComparer.Ordinal)
    {
        "OST_Furniture", "OST_Casework", "OST_FurnitureSystems", "OST_PlumbingFixtures", "OST_SpecialityEquipment",
        "OST_LightingFixtures", "OST_Rooms", "OST_RoomSeparationLines",
    };

    /// <summary>Building or services: what is over a room is read as its ceiling (its downward faces, the lowest
    /// counting). Anything over a room in a category in neither list leaves its ceilings out.</summary>
    public static readonly IReadOnlySet<string> Building = new HashSet<string>(StringComparer.Ordinal)
    {
        "OST_Ceilings", "OST_Floors", "OST_Roofs", "OST_RoofSoffit", "OST_Fascia", "OST_Gutter", "OST_EdgeSlab",
        "OST_Walls", "OST_Cornices", "OST_Reveals", "OST_Columns", "OST_StructuralColumns", "OST_StructuralFraming",
        "OST_StructuralFoundation", "OST_GenericModel", "OST_Stairs", "OST_StairsRailing", "OST_Windows", "OST_Doors",
        "OST_CurtainWallPanels", "OST_CurtainWallMullions", "OST_DuctCurves", "OST_DuctFitting", "OST_DuctAccessory",
        "OST_FlexDuctCurves", "OST_DuctTerminal", "OST_PipeCurves", "OST_PipeFitting", "OST_PipeAccessory",
        "OST_FlexPipeCurves", "OST_CableTray", "OST_CableTrayFitting", "OST_Conduit", "OST_ConduitFitting",
        "OST_MechanicalEquipment", "OST_ElectricalEquipment",
    };

    public static InteriorReadResult Read(RevitModel model)
    {
        var notes = new List<InteriorNote>();
        var evidence = new JsonObject();
        var interior = new JsonObject { ["format"] = "gordium.interior/1", ["units"] = "ft" };
        var roomsNotRead = RoomsNotRead(model);
        var openingsNotRead = OpeningsNotRead(model);
        var records = model.Interior;

        var marks = MarkReading.Rooms(model);
        var rooms = new JsonArray();
        if (roomsNotRead.Count == 0 && marks is not null && records is not null)
        {
            var marked = MarkReading.InDesign(model).ToDictionary(e => e.UniqueId, StringComparer.Ordinal);
            foreach (var r in marks)
            {
                var room = new JsonObject { ["id"] = r.Id, ["name"] = RoomName(marked[r.Id]) };
                if (r.Sleeping is { } sleeping)
                    room["sleeping"] = sleeping;
                else
                    notes.Add(new(r.Id, "sleeping", Marks.SleepingRoom.Name + " is not set"));
                var rec = records.Rooms.FirstOrDefault(x => x.UniqueId == r.Id);
                if (rec is null)
                    notes.Add(new(r.Id, "floor", "the Revit layer gave nothing for this room"));
                else
                    ReadRoom(model, records, rec, room, notes);
                rooms.Add(room);
            }
        }
        if (roomsNotRead.Count == 0 && rooms.Count == 0)
            roomsNotRead = [MarkingListResult.NoRooms + ": no room is read for egress (never read as a house with none)"];
        if (roomsNotRead.Count == 0)
            interior["rooms"] = rooms;

        var openings = new JsonArray();
        if (openingsNotRead.Count == 0 && records is not null)
        {
            var marked = MarkReading.InDesign(model).ToDictionary(e => e.UniqueId, StringComparer.Ordinal);
            foreach (var o in MarkReading.Openings(model))
                openings.Add(ReadOpening(model, records, marked[o.Id], o, notes, evidence));
        }
        if (openingsNotRead.Count == 0 && openings.Count == 0)
            openingsNotRead = ["No windows or doors are drawn: no escape opening is read (never read as a house with none)"];
        if (openingsNotRead.Count == 0)
            interior["openings"] = openings;
        return new(interior, roomsNotRead, openingsNotRead, notes, evidence);
    }

    // ---- what stops a kind being read ---------------------------------------------------------------------------

    /// <summary>Why no room can be read: every Room not on the plan, every enclosed area with no Room, every closed
    /// workset and every link that could hold one (design note, section 2). The marking list shows these first.</summary>
    public static List<string> RoomsNotRead(RevitModel model)
    {
        var why = new List<string>();
        var placement = MarkReading.RoomBlockers(model).Count;
        if (placement > 0)
            why.Add((placement == 1 ? "1 Room is" : $"{placement} Rooms are") + " unplaced, not enclosed or redundant");
        if (model.Interior is null)
        {
            why.Add("the model's inside wasn't read");
            return why;
        }
        why.AddRange(OtherRoomBlockers(model));
        return why;
    }

    /// <summary>What stops every room being read besides a Room not on the plan (the marking list lists those itself):
    /// each enclosed area with no Room, each closed workset, each link that could hold a room. Empty when the model's
    /// inside wasn't read (the marking list alone).</summary>
    public static List<string> OtherRoomBlockers(RevitModel model) =>
        model.Interior is null ? [] : [.. AreaBlockers(model), .. WorksetAndLinkBlockers(model, rooms: true)];

    /// <summary>The enclosed areas with no Room, each in words (a bedroom may be one); one line when they couldn't be read.</summary>
    public static List<string> AreaBlockers(RevitModel model)
    {
        if (model.Interior is not { } records)
            return [];
        if (records.EnclosedAreas is not { } areas)
            return ["the enclosed areas on each level couldn't be read, so Gordium can't tell every room has a Room"];
        return areas.Where(a => !a.HasRoom).Select(a =>
        {
            var p = model.InternalToShared.Apply(a.PointInside);
            return string.Format(CultureInfo.InvariantCulture,
                "An enclosed area on {0} has no Room ({1:0.#} sq ft, around x {2:0.##}, y {3:0.##}): place a Room in it " +
                "(marked No if no one sleeps there), or open it up", a.Level, a.Area, p.X, p.Y);
        }).ToList();
    }

    private static IEnumerable<string> WorksetAndLinkBlockers(RevitModel model, bool rooms)
    {
        if (rooms)
            foreach (var w in model.UserWorksets.Where(w => !w.IsOpen))
                yield return $"Workset \"{w.Name}\" is closed: a room could be in it (open it)";
        foreach (var link in model.Interior?.Links ?? [])
        {
            if (rooms && !link.Loaded)
                yield return $"Linked model \"{link.Name}\" isn't loaded: a room could be in it";
            else if (rooms && link.HasLinks)
                yield return $"Linked model \"{link.Name}\" holds links of its own, which aren't read: a room could be in one";
            else if (rooms && link.Rooms > 0)
                yield return $"Linked model \"{link.Name}\" holds {Count(link.Rooms, "Room")}: rooms in a linked model aren't read yet";
            else if (!rooms && link.Loaded && link.WindowsAndDoors > 0)
                yield return $"Linked model \"{link.Name}\" holds {Count(link.WindowsAndDoors, "window or door", "windows and doors")}: " +
                             "escape openings in a linked model aren't read yet";
        }
    }

    /// <summary>Why no opening can be read: a window or door found inside a linked model (design note, section 4).
    /// A closed workset or an unloaded link doesn't stop them: an escape opening missed can only make a bedroom fail.</summary>
    public static List<string> OpeningsNotRead(RevitModel model) =>
        model.Interior is null ? ["the model's inside wasn't read"] : WorksetAndLinkBlockers(model, rooms: false).ToList();

    private static string Count(int n, string one, string? many = null) =>
        n == 1 ? $"1 {one}" : $"{n} {many ?? one + "s"}";

    private static string RoomName(MarkedElement e) =>
        string.IsNullOrWhiteSpace(e.Number) ? e.Name ?? e.UniqueId
        : string.IsNullOrWhiteSpace(e.Name) ? $"Room {e.Number}" : $"{e.Name} ({e.Number})";

    // ---- a room --------------------------------------------------------------------------------------------------

    private static void ReadRoom(RevitModel model, InteriorRecords records, RoomRecord rec, JsonObject room,
                                 List<InteriorNote> notes)
    {
        var id = rec.UniqueId;
        var t = model.InternalToShared;
        void Out(string field, string why) => notes.Add(new(id, field, why));

        // the floor's outline: one loop of straight segments at the finished faces, nothing inside it unbounded
        List<P2>? plan = null;
        var bounding = new HashSet<string>(StringComparer.Ordinal);
        if (rec.Boundary is not { } loops || loops.Count == 0)
            Out("floor", "Revit gives no boundary for this room");
        else if (loops.Count > 1)
            Out("floor", $"it has {loops.Count} boundary loops (a column or a chase inside it): a floor with a hole isn't read yet");
        else if (loops[0].Any(s => !s.IsLine))
            Out("floor", "its boundary has a curved segment: read only as straight segments, never as a chord");
        else
        {
            foreach (var s in loops[0].Where(s => s.Element is not null))
                bounding.Add(s.Element!);
            var points = loops[0].Select(s => t.Apply(s.Start)).Select(p => new P2(p.X, p.Y)).ToList();
            var clean = PlanGeometry.Clean(points);
            if (clean is null || !PlanGeometry.IsSimple(clean))
                Out("floor", "its boundary isn't a simple outline");
            else
                plan = clean;
        }
        if (plan is not null)
        {
            if (rec.Inside is not { } inside)
            {
                Out("floor", "what stands inside it couldn't be looked for");
                plan = null;
            }
            else if (inside.Where(e => !bounding.Contains(e.UniqueId) && !NotBuilding.Contains(e.BuiltInCategory)
                                       && !(e.Host is { } h && bounding.Contains(h)))
                           .Select(e => Named(e)).Distinct().ToList() is { Count: > 0 } standing)
            {
                Out("floor", "something stands inside its outline without bounding it (" + string.Join(", ", standing) +
                             "): it may be two rooms, or smaller than its outline");
                plan = null;
            }
        }
        // a loaded link reaching over the room: what's in it (a slab, a beam) isn't read yet
        if (plan is not null && records.Links.Where(l => l.Loaded && l.Box is not null && Reaches(model, l.Box!, plan))
                                    .Select(l => l.Name).ToList() is { Count: > 0 } over)
        {
            Out("floor", "linked model " + string.Join(", ", over.Select(n => $"\"{n}\"")) +
                         " reaches over this room, and what is in a link isn't read yet");
            Out("floor_elevation", "a linked model reaches over this room");
            Out("ceilings", "a linked model reaches over this room");
            return;
        }
        if (plan is null)
        {
            Out("floor_elevation", "checked against the slab under the whole floor, which needs the floor's outline");
            Out("ceilings", "clipped to the floor's outline, which wasn't read");
            return;
        }
        room["floor"] = new JsonArray(plan.Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray());

        // the floor's elevation: its level and offset, checked against the slab top under the whole room
        if (rec.LevelElevation is not { } level || rec.BaseOffset is not { } offset)
        {
            Out("floor_elevation", "its level or base offset couldn't be read");
            Out("ceilings", "worked out above the floor's elevation, which couldn't be read");
            return;
        }
        var at = rec.Boundary![0][0].Start;
        var claimed = t.Apply(new Xyz(at.X, at.Y, level + offset)).Z;
        if (SlabProblem(model, rec, plan, claimed) is { } slab)
            Out("floor_elevation", slab);
        else
            room["floor_elevation"] = claimed;

        if (Ceilings(model, rec, plan, claimed, bounding, out var why) is { } pieces)
            room["ceilings"] = pieces;
        else
            Out("ceilings", why!);
    }

    private static string Named(NearbyElement e) =>
        string.IsNullOrWhiteSpace(e.Name) ? e.BuiltInCategory.Replace("OST_", "") : $"{e.BuiltInCategory.Replace("OST_", "")} \"{e.Name}\"";

    private static bool Reaches(RevitModel model, RevitBox box, List<P2> plan)
    {
        var b = Box3.Turned(box.Min, box.Max, box.Transform is { } own ? model.InternalToShared.After(own) : model.InternalToShared);
        double x0 = plan.Min(p => p.X), x1 = plan.Max(p => p.X), y0 = plan.Min(p => p.Y), y1 = plan.Max(p => p.Y);
        return b.Min.X < x1 && b.Max.X > x0 && b.Min.Y < y1 && b.Max.Y > y0;
    }

    private static List<Xyz> Shared(RevitModel model, IEnumerable<Xyz> points) => points.Select(model.InternalToShared.Apply).ToList();

    private static Xyz Turned(RevitModel model, Xyz v)
    {
        var t = model.InternalToShared;
        return v.X * t.BasisX + v.Y * t.BasisY + v.Z * t.BasisZ;
    }

    private static bool PlanBoxesOverlap(IEnumerable<Xyz> points, List<P2> plan)
    {
        var pts = points.ToList();
        if (pts.Count == 0)
            return false;
        double x0 = plan.Min(p => p.X), x1 = plan.Max(p => p.X), y0 = plan.Min(p => p.Y), y1 = plan.Max(p => p.Y);
        return pts.Min(p => p.X) < x1 && pts.Max(p => p.X) > x0 && pts.Min(p => p.Y) < y1 && pts.Max(p => p.Y) > y0;
    }

    /// <summary>A face's loops in plan, in shared coordinates, moved by <paramref name="origin"/>; the outer loop
    /// (the largest) first.</summary>
    private static List<List<P2>> PlanLoops(RevitModel model, SurfaceRecord f, P2 origin) =>
        f.Loops.Select(l => l.Select(c => model.InternalToShared.Apply(c.Start)).Select(p => new P2(p.X - origin.X, p.Y - origin.Y)).ToList())
               .OrderByDescending(l => PlanGeometry.Area(l)).ToList();

    /// <summary>Why the floor elevation can't be confirmed by the slab under the whole room (null when it is): no slab
    /// top found within a foot of it, tops at different heights, a sloped or curved top, one that doesn't cover the
    /// whole room, or one more than 1/16 in from it (design note, section 4: a cross-check that can't be made counts as
    /// a failed one).</summary>
    private static string? SlabProblem(RevitModel model, RoomRecord rec, List<P2> plan, double claimed)
    {
        if (rec.Under is not { } under)
            return "the slab under it couldn't be looked for";
        var origin = plan[0];
        var room = PlanGeometry.Local(plan, origin);
        var roomArea = PlanGeometry.Area(room);
        var tops = new List<(double Z, List<List<P2>> Loops, string By)>();
        foreach (var e in under)
        {
            if (e.GeometryFailed || e.Faces is null)
                return $"the geometry of {Named(e)} under it couldn't be read";
            foreach (var f in e.Faces)
            {
                var pts = Shared(model, f.Points);
                if (pts.Count == 0 || pts.Max(p => p.Z) < claimed - SlabBand || pts.Min(p => p.Z) > claimed + SlabBand)
                    continue;
                if (!f.Planar)
                {
                    if (PlanBoxesOverlap(pts, plan))
                        return $"a curved face of {Named(e)} is under it";
                    continue;
                }
                if (Turned(model, f.Normal).Z <= 1e-9)
                    continue;                                   // a side or an underside
                var loops = PlanLoops(model, f, origin);
                var overlap = PlanGeometry.OverlapArea(room, loops[0]);
                if (overlap is null)
                    return $"a top face of {Named(e)} under it isn't a simple outline";
                if (overlap <= roomArea * 1e-9)
                    continue;
                if (pts.Max(p => p.Z) - pts.Min(p => p.Z) > Sixteenth)
                    return $"the top of {Named(e)} under it slopes";
                if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
                    return $"the top of {Named(e)} under it has a curved edge, which isn't read exactly";
                tops.Add((pts.Average(p => p.Z), loops, Named(e)));
            }
        }
        if (tops.Count == 0)
            return "no slab top was found under it within a foot of its floor";
        if (tops.Max(x => x.Z) - tops.Min(x => x.Z) > Sixteenth)
            return "the slab tops under it are at different heights (" +
                   string.Join(", ", tops.Select(x => ClearStamp.Inches(x.Z - claimed) + " from its floor, " + x.By).Distinct()) + ")";
        var z = tops[0].Z;
        if (Math.Abs(z - claimed) > Sixteenth)
            return $"the slab top under it ({tops[0].By}) is {ClearStamp.Inches(z - claimed)} from the floor its level and offset give";
        var covered = tops.Any(x =>
            PlanGeometry.OverlapArea(room, x.Loops[0]) is { } a && a >= roomArea * (1 - 1e-9)
            && x.Loops.Skip(1).All(h => PlanGeometry.OverlapArea(room, h) is { } ha && ha <= roomArea * 1e-9));
        return covered ? null : "no one slab top covers the whole room (a hole, or several slabs), so its floor isn't confirmed";
    }

    /// <summary>The room's ceilings: the downward flat faces of everything building or services over it, clipped to
    /// its floor, as flat pieces of 3D points (the lowest counts in the measuring code). Null, with why, when anything
    /// over it can't be read exactly.</summary>
    private static JsonArray? Ceilings(RevitModel model, RoomRecord rec, List<P2> plan, double floor,
                                       HashSet<string> bounding, out string? why)
    {
        why = null;
        if (rec.Over is not { } over)
        {
            why = "what is over it couldn't be looked for";
            return null;
        }
        var origin = plan[0];
        var room = PlanGeometry.Local(plan, origin);
        var roomArea = PlanGeometry.Area(room);
        var pieces = new JsonArray();
        foreach (var e in over)
        {
            if (e.UniqueId == rec.UniqueId || NotBuilding.Contains(e.BuiltInCategory) || (e.Host is { } h && bounding.Contains(h)))
                continue;                                    // a window or door in a wall bounding it isn't over it
            if (!Building.Contains(e.BuiltInCategory) && e is { GeometryFailed: false, Faces.Count: 0 })
                continue;                                    // nothing drawn (a base point, a line): nothing over it
            if (!Building.Contains(e.BuiltInCategory))
            {
                why = $"{Named(e)} is over it, in a category Gordium doesn't read as a ceiling or as furniture";
                return null;
            }
            if (e.GeometryFailed || e.Faces is null)
            {
                why = $"the geometry of {Named(e)} over it couldn't be read";
                return null;
            }
            foreach (var f in e.Faces)
            {
                var pts = Shared(model, f.Points);
                if (pts.Count == 0 || pts.Max(p => p.Z) <= floor + Sixteenth)
                    continue;                                // at or under the floor
                if (!f.Planar)
                {
                    if (PlanBoxesOverlap(pts, plan))
                    {
                        why = $"a curved face of {Named(e)} is over it, which isn't read exactly";
                        return null;
                    }
                    continue;
                }
                var n = Turned(model, f.Normal);
                if (n.Z >= -1e-9)
                    continue;                                // faces up, or a side
                var loops = PlanLoops(model, f, origin);
                var overlap = PlanGeometry.Overlap(room, loops[0]);
                if (overlap is null)
                {
                    why = $"an underside of {Named(e)} over it isn't a simple outline";
                    return null;
                }
                if (overlap.Sum(PlanGeometry.Area) <= roomArea * 1e-9)
                    continue;                                // beside it, not over it
                if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
                {
                    why = $"an underside of {Named(e)} over it has a curved edge, which isn't read exactly";
                    return null;
                }
                if (pts.Min(p => p.Z) <= floor + Sixteenth)
                {
                    why = $"an underside of {Named(e)} reaches down to its floor";
                    return null;
                }
                var p0 = pts[0];
                double Z(P2 q) => p0.Z - (n.X * (q.X + origin.X - p0.X) + n.Y * (q.Y + origin.Y - p0.Y)) / n.Z;
                foreach (var piece in overlap)
                    pieces.Add(new JsonArray(piece.Select(q => (JsonNode)new JsonArray(q.X + origin.X, q.Y + origin.Y, Z(q))).ToArray()));
            }
        }
        if (pieces.Count == 0)
        {
            why = "nothing was found over it";
            return null;
        }
        return pieces;
    }

    // ---- a window or door ----------------------------------------------------------------------------------------

    private static JsonObject ReadOpening(RevitModel model, InteriorRecords records, MarkedElement e, OpeningMarks o,
                                          List<InteriorNote> notes, JsonObject evidence)
    {
        var id = o.Id;
        void Out(string field, string why) => notes.Add(new(id, field, why));
        var opening = new JsonObject { ["id"] = id, ["name"] = MarkingList.Label(e) };
        var rec = records.Openings.FirstOrDefault(x => x.UniqueId == id);
        if (rec is null)
            Out("room", "the Revit layer gave nothing for this " + (o.Kind == MarkedKind.Door ? "door" : "window"));
        else if (rec.FromRoom is null && rec.ToRoom is null)
            Out("room", "it opens from no room");
        else if (rec.FromRoom is not null && rec.ToRoom is not null && rec.FromRoom != rec.ToRoom)
            Out("room", "it is between two rooms: which one it is the escape opening of isn't read yet");
        else
            opening["room"] = rec.FromRoom ?? rec.ToRoom;
        if (o.Escape is { } escape)
            opening["escape"] = escape;
        else
            Out("escape", Marks.EscapeOpening.Name + " is not set");
        if (o.Operation is { } operation)
            opening["operation"] = operation;
        else
            Out("operation", Marks.Operation.Name + " is not set on its type, or isn't a word Gordium reads");
        if (o.Kind == MarkedKind.Window && rec is not null)
        {
            if (StatedClear(model, e, rec, evidence, out var why) is { } clear)
                opening["stated_clear"] = clear;
            else
                Out("stated_clear", why!);
        }
        else if (o.Kind == MarkedKind.Door)
            Out("stated_clear", "a door's clear opening comes with the doors step (a door's maker's clear width)");
        return opening;
    }

    /// <summary>The window's values the stamp is checked against, read now.</summary>
    public static ClearValues ClearNow(MarkedElement e, OpeningRecord rec)
    {
        var mapped = MappedName(Marks.Text(MarkReading.Value(e, Marks.ClearConfirmed)));
        return new(e.TypeUniqueId, rec.TypeWidth, rec.TypeHeight, Marks.Text(MarkReading.Value(e, Marks.Operation)),
                   Marks.Length(MarkReading.Value(e, Marks.ClearWidth)), Marks.Length(MarkReading.Value(e, Marks.ClearHeight)),
                   Marks.Length(MarkReading.Value(e, Marks.ClearOffset)), Marks.Text(MarkReading.Value(e, Marks.ClearSource)),
                   mapped, mapped is not null && rec.TypeLengths.TryGetValue(mapped, out var v) ? v : null);
    }

    private static string? MappedName(string? stamp)
    {
        try
        {
            return stamp is null ? null : JsonNode.Parse(stamp)?["mapped"]?["name"]?.GetValue<string>();
        }
        catch (Exception x) when (x is System.Text.Json.JsonException or InvalidOperationException or FormatException)
        {
            return null;
        }
    }

    /// <summary>The maker's clear opening, sent only when the type's stamp confirms every value now, the sill line
    /// agrees with the bottom of the opening the window cuts in its wall, and the clear opening fits inside the window
    /// as placed (design note, section 4).</summary>
    private static JsonObject? StatedClear(RevitModel model, MarkedElement e, OpeningRecord rec, JsonObject evidence,
                                           out string? why)
    {
        why = null;
        var now = ClearNow(e, rec);
        if (ClearStamp.Why(Marks.Text(MarkReading.Value(e, Marks.ClearConfirmed)), now, rec.TypeLengths) is { } stamp)
        {
            why = stamp;
            return null;
        }
        if (rec.LevelElevation is not { } level || rec.SillHeight is not { } sill || rec.Location is not { } at)
        {
            why = "its level, Sill Height or place couldn't be read";
            return null;
        }
        var t = model.InternalToShared;
        var sillLine = level + sill;
        var record = new JsonObject { ["sill_line"] = t.Apply(new Xyz(at.X, at.Y, sillLine)).Z };
        evidence[e.UniqueId] = record;
        if (!rec.HostIsWall || rec.WallOpening is not { Count: > 0 } cut)
        {
            record["wall_opening_bottom"] = null;
            why = "no opening it cuts in a wall was found, so its sill line (Sill Height) can't be checked against anything drawn";
            return null;
        }
        var bottomCut = cut.Min(p => p.Z);
        record["wall_opening_bottom"] = t.Apply(new Xyz(at.X, at.Y, bottomCut)).Z;
        if (Math.Abs(bottomCut - sillLine) > Sixteenth)
        {
            why = $"the opening it cuts in its wall is {ClearStamp.Inches(bottomCut - sillLine)} from its sill line (Sill Height): " +
                  "they must agree within 1/16 in";
            return null;
        }
        if (rec.Placed is not { Count: > 0 } placed || rec.Along is not { } along)
        {
            why = "its drawn geometry couldn't be read, so the clear opening can't be checked to fit inside it";
            return null;
        }
        var length = Math.Sqrt(along.X * along.X + along.Y * along.Y);
        if (length < 1e-9)
        {
            why = "its direction along the wall couldn't be read";
            return null;
        }
        double low = placed.Min(p => p.Z), high = placed.Max(p => p.Z);
        var u = placed.Select(p => (p.X * along.X + p.Y * along.Y) / length).ToList();
        var width = u.Max() - u.Min();
        double clearWidth = now.ClearWidth!.Value, clearHeight = now.ClearHeight!.Value;
        var bottom = sillLine + now.ClearOffset!.Value;
        var top = bottom + clearHeight;
        record["placed"] = new JsonObject
        {
            ["bottom"] = t.Apply(new Xyz(at.X, at.Y, low)).Z, ["top"] = t.Apply(new Xyz(at.X, at.Y, high)).Z, ["width"] = width,
        };
        if (bottom < low - Sixteenth || top > high + Sixteenth || clearWidth > width + Sixteenth)
        {
            why = "its clear opening doesn't fit inside the window as placed (" +
                  $"clear {ClearStamp.Inches(clearWidth)} wide from {ClearStamp.Inches(bottom - sillLine)} to " +
                  $"{ClearStamp.Inches(top - sillLine)} above the sill line; the window {ClearStamp.Inches(width)} wide from " +
                  $"{ClearStamp.Inches(low - sillLine)} to {ClearStamp.Inches(high - sillLine)})";
            return null;
        }
        return new JsonObject
        {
            ["width"] = clearWidth,
            ["height"] = clearHeight,
            ["bottom"] = t.Apply(new Xyz(at.X, at.Y, bottom)).Z,
            ["source"] = now.Source,
        };
    }
}
