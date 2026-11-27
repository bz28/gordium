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
                                        JsonObject Evidence)
{
    /// <summary>Why <c>stairs</c> was left out (empty when it was sent; step 4).</summary>
    public IReadOnlyList<string> StairsNotRead { get; init; } = [];

    /// <summary>Each escape-route value left out (section 10), apart from <see cref="InteriorReadResult.Notes"/>: a house
    /// never sets the route marks, so its count of values left out stays as it was (review round 1).</summary>
    public IReadOnlyList<InteriorNote> RouteNotes { get; init; } = [];

    /// <summary>Why <c>doors</c> was left out (empty when it was sent; step 5).</summary>
    public IReadOnlyList<string> DoorsNotRead { get; init; } = [];

    /// <summary>Why <c>guards</c> was left out (empty when it was sent; step 5).</summary>
    public IReadOnlyList<string> GuardsNotRead { get; init; } = [];

    /// <summary>Every "this house has none of" tick, read (step 6): the lists' and the claims', sent or not and why.</summary>
    public IReadOnlyList<NoneTick> Ticks { get; init; } = [];

    /// <summary>Each enclosed area with no Room sent as a space whose use isn't known (<c>unknown_spaces</c>), in words.</summary>
    public IReadOnlyList<string> UnknownSpaces { get; init; } = [];

    /// <summary>Each level marked "no rooms on this level" with a Room drawn on it (the mark doesn't count).</summary>
    public IReadOnlyList<string> LevelConflicts { get; init; } = [];

    /// <summary>Each element the architect cleared with <c>Gordium: Not a stair</c>, a line per category and type
    /// (<see cref="StairReader.NotAStairLines"/>).</summary>
    public IReadOnlyList<string> NotAStair { get; init; } = [];

    /// <summary>Each Revit stair or railing marked <c>Gordium: Not a stair</c> Yes (the mark doesn't count).</summary>
    public IReadOnlyList<string> NotAStairConflicts { get; init; } = [];
}

/// <summary>
/// The interior reader, section 7 step 3 of docs/revit/revit_interior_reading_design.md: the rooms and the windows and
/// doors that can be escape openings, as the interior description (<c>gordium.interior/1</c>). Its rules are the
/// note's section 2: a mark never set is not given; nothing found is never "none" (a kind with nothing found is left
/// out, never an empty list); every room counts (an unplaced Room, a closed workset or an unloaded link leaves
/// <c>rooms</c> out; an enclosed area with no Room is sent as a space whose use isn't known, <c>unknown_spaces</c>, so
/// every sleeping-room rule needs review while the rooms drawn are still checked); a part found is never dropped (a value that can't be read exactly is left
/// out, with its reason in <see cref="InteriorReadResult.Notes"/>); a value is sent only when what is drawn agrees
/// with it (a room's floor elevation against the slab under it, a window's sill line against the opening it cuts).
/// The stairs (step 4) are <see cref="StairReader"/>'s. The doors (step 5) are read here: each door's exit mark,
/// operation and the maker's clear opening its type's stamp confirms (nothing drawn: door families don't model their
/// stops and leaf consistently); the guards (step 5) are <see cref="GuardReader"/>'s. What the house has none of (step
/// 6) is the architect's ticks, read by <see cref="HasNone"/>: an empty list or a <c>has_none</c> claim only on a tick.
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
        // a stair's own parts (step 4: another run or a landing over a flight is its overhead) and a railing's
        "OST_StairsRuns", "OST_StairsLandings", "OST_StairsSupports", "OST_StairsStringerCarriage", "OST_RailingTopRail",
        "OST_RailingHandRail", "OST_RailingSupport", "OST_RailingTermination", "OST_StairsRailingBaluster",
        "OST_StairsRailingRail",
    };

    public static InteriorReadResult Read(RevitModel model)
    {
        var notes = new List<InteriorNote>();
        var routeNotes = new List<InteriorNote>();           // the escape routes' own, kept apart from a house's
        var evidence = new JsonObject();
        var interior = new JsonObject { ["format"] = "gordium.interior/1", ["units"] = "ft" };
        var roomsNotRead = RoomsNotRead(model);
        var openingsNotRead = OpeningsNotRead(model);
        var records = model.Interior;

        var marks = MarkReading.Rooms(model);
        var rooms = new JsonArray();
        var plans = new Dictionary<string, RoomPlan>(StringComparer.Ordinal);
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
                    ReadRoom(model, records, rec, room, notes, r.Sleeping, plans);
                RouteReader.RoomMarks(r, room, routeNotes);
                rooms.Add(room);
            }
        }
        if (roomsNotRead.Count == 0 && rooms.Count == 0)
            roomsNotRead = [MarkingListResult.NoRooms + ": no room is read for egress (never read as a house with none)"];
        var unknown = roomsNotRead.Count == 0 ? UnknownAreas(model) : [];
        if (roomsNotRead.Count == 0)
            interior["rooms"] = rooms;
        // an enclosed area with no Room doesn't stop the rooms drawn being read: each is sent as a space whose use
        // isn't known, a sleeping room that may not be one (every rule about it needs review, never a pass)
        if (unknown.Count > 0)
            interior["unknown_spaces"] = UnknownSpaces(model, unknown);

        var openings = new JsonArray();
        if (openingsNotRead.Count == 0 && records is not null)
        {
            var marked = MarkReading.InDesign(model).ToDictionary(e => e.UniqueId, StringComparer.Ordinal);
            // the ground outside each window, only where a ground is drawn in the design checked (GroundReader)
            var ground = GroundReader.Of(model) is { } grounds ? (grounds, UnknownSpaceList(model)) : ((GroundReader.Grounds, List<(EnclosedArea, string, List<P2>?)>)?)null;
            foreach (var o in MarkReading.Openings(model))
                openings.Add(ReadOpening(model, records, marked[o.Id], o, notes, evidence, plans, ground));
        }
        if (openingsNotRead.Count == 0 && openings.Count == 0)
            openingsNotRead = ["No windows or doors are drawn: no escape opening is read (never read as a house with none)"];
        if (openingsNotRead.Count == 0)
            interior["openings"] = openings;

        // step 4: the stairs, one flight per run, only on the architect's tick and with nothing that could be a stair
        // the reader doesn't walk; nothing found is never "none": that is the tick "this house has no stairs" (step 6),
        // sent as an empty list only with no stair drawn and nothing that could hide one; ticked Yes and not sent (a
        // stair drawn: the two disagree), no stair is read
        var noStairs = HasNone.Read(model, HasNone.Stairs);
        var stairsNotRead = StairReader.NotRead(model);
        var stairEvidence = new JsonObject();
        StairReader.RailingUse? use = null;
        if (noStairs.Sent)
        {
            interior["stairs"] = new JsonArray();
            stairsNotRead = [];
            use = new StairReader.RailingUse();
        }
        else if (noStairs.Ticked is true)
            stairsNotRead = [.. noStairs.WhyNot];
        else if (stairsNotRead.Count == 0)
        {
            use = new StairReader.RailingUse();
            var flights = StairReader.Flights(model, notes, stairEvidence, use);
            if (flights.Count == 0)
                stairsNotRead = ["No stairs are drawn: no stair is read for egress (never read as a house with none)"];
            else
                interior["stairs"] = flights;
        }
        if (stairEvidence.Count > 0)
            evidence["stairs"] = stairEvidence;

        // step 5: the doors (each one's exit mark, operation and maker's confirmed clear opening), and the guards, only
        // on the architect's tick and with every railing on a stair read as a handrail beside a wall; nothing found is
        // never "none": that is the ticks "this house has no doors" and "... no guards" (step 6), each as the stairs'
        var noDoors = HasNone.Read(model, HasNone.Doors);
        var doorsNotRead = OpeningsNotRead(model);
        if (noDoors.Sent)
        {
            interior["doors"] = new JsonArray();
            doorsNotRead = [];
        }
        else if (noDoors.Ticked is true)
            doorsNotRead = [.. noDoors.WhyNot];
        else if (doorsNotRead.Count == 0 && records is not null)
        {
            var marked = MarkReading.InDesign(model).ToDictionary(e => e.UniqueId, StringComparer.Ordinal);
            var doors = new JsonArray();
            foreach (var d in MarkReading.Doors(model))
                doors.Add(ReadDoor(records, marked[d.Id], d, notes, evidence));
            if (doors.Count == 0)
                doorsNotRead = ["No doors are drawn: no exit door is read (never read as a house with none)"];
            else
                interior["doors"] = doors;
        }
        var noGuards = HasNone.Read(model, HasNone.Guards, use);
        var guardsNotRead = GuardReader.NotRead(model, use);
        var guardEvidence = new JsonObject();
        if (noGuards.Sent)
        {
            interior["guards"] = new JsonArray();
            guardsNotRead = [];
        }
        else if (noGuards.Ticked is true)
            guardsNotRead = [.. noGuards.WhyNot];
        else if (guardsNotRead.Count == 0)
        {
            var guards = GuardReader.Guards(model, notes, guardEvidence);
            if (guards.Count == 0)
                guardsNotRead = ["No guards are drawn as railings off a stair: no guard is read for egress (never read as a house with none)"];
            else
                interior["guards"] = guards;
        }
        if (guardEvidence.Count > 0)
            evidence["guards"] = guardEvidence;

        // escape routes (section 10): each story's levels, rooms' holes and obstructions, doors' places, sides and
        // exits, and the passages between rooms, every one left out with its reason when it can't be read exactly
        if (records is not null)
            RouteReader.Add(model, records, interior, plans, routeNotes, evidence);

        // step 6: the format's has_none claims, each only on its tick, with nothing drawn against it and nothing that
        // could hide one; every tick's reading kept as evidence
        List<NoneTick> ticks = [noStairs, noDoors, noGuards, .. HasNone.Claims.Select(k => HasNone.Read(model, k, use))];
        if (HasNone.Entries(ticks) is { } claims)
            interior["has_none"] = claims;
        evidence["has_none"] = new JsonObject(ticks.Select(t => KeyValuePair.Create(t.Kind.Kind, (JsonNode?)HasNone.Evidence(t))));
        return new(interior, roomsNotRead, openingsNotRead, notes, evidence)
        {
            RouteNotes = routeNotes,
            StairsNotRead = stairsNotRead, DoorsNotRead = doorsNotRead, GuardsNotRead = guardsNotRead, Ticks = ticks,
            UnknownSpaces = unknown.Count > 0 ? UnknownAreaWords(model) : [], LevelConflicts = LevelConflicts(model),
            NotAStair = StairReader.NotAStairLines(model), NotAStairConflicts = StairReader.NotAStairConflicts(model),
        };
    }

    // ---- what stops a kind being read ---------------------------------------------------------------------------

    /// <summary>Why no room can be read: every Room not on the plan, enclosed areas that couldn't be read, every
    /// closed workset and every link that could hold one (design note, section 2). The marking list shows these first.
    /// An enclosed area with no Room doesn't stop the rooms being read: it is sent as a space whose use isn't known
    /// (<see cref="UnknownAreas"/>), whose every sleeping-room rule needs review.</summary>
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
    /// enclosed areas that couldn't be read, each closed workset, each link that could hold a room. Empty when the
    /// model's inside wasn't read (the marking list alone).</summary>
    public static List<string> OtherRoomBlockers(RevitModel model) =>
        model.Interior is null ? [] : [.. AreasNotRead(model), .. WorksetAndLinkBlockers(model, rooms: true)];

    private static List<string> AreasNotRead(RevitModel model) =>
        model.Interior is { EnclosedAreas: null }
            ? ["the enclosed areas on each level couldn't be read, so Gordium can't tell every room has a Room"] : [];

    /// <summary>Each enclosed area with no Room that is sent as a space whose use isn't known (<see cref="UnknownAreas"/>),
    /// in words, with what the architect can do about it: a bedroom may be one, so every sleeping-room rule needs
    /// review while any is there (and no "no basements, attics or lofts" claim is sent). One line per level (a roof can
    /// hold 19): one area in full, several counted with their sizes, each area by its place in
    /// <see cref="InteriorReadResult.UnknownSpaces"/> and the description's <c>unknown_spaces</c>.</summary>
    public static List<string> AreaBlockers(RevitModel model) =>
        UnknownAreas(model).GroupBy(a => (a.LevelId, a.Level)).Select(g =>
        {
            var list = g.ToList();
            var placeless = list.Count(a => a.PointInside is null);
            // an area Revit can't give a point inside has no place to put a Room in: its fix is the walls
            var fixWalls = "find and fix the overlapping or doubled walls on " + g.Key.Level + " that close it off";
            var roof = "on a level with no rooms at all (a roof), mark the level " + Marks.NoRoomsOnLevel.Name + " Yes";
            if (list.Count == 1)
                return AreaWords(model, list[0]) + ": it may be a bedroom nobody placed a Room in, so every sleeping-room " +
                       "rule needs review: " + (placeless == 1 ? fixWalls
                                                                 : "place a Room in it (marked No if no one sleeps there), or open it up") +
                       "; " + roof;
            var what = placeless == 0
                ? "each listed with its place in the log): each may be a bedroom nobody placed a Room in, so every " +
                  "sleeping-room rule needs review: place a Room in each (marked No if no one sleeps there), or open it up"
                : placeless == list.Count
                    ? "each listed in the log; Revit couldn't locate any of them, often slivers between overlapping walls): " +
                      "each may be a bedroom nobody placed a Room in, so every sleeping-room rule needs review: " +
                      "find and fix the overlapping or doubled walls on " + g.Key.Level + " that close them off"
                    : string.Format(CultureInfo.InvariantCulture,
                          "each listed in the log, with its place where Revit gives one): each may be a bedroom nobody " +
                          "placed a Room in, so every sleeping-room rule needs review: place a Room in each of the {0} with " +
                          "a place (marked No if no one sleeps there), or open it up; the {1} Revit couldn't locate (no point " +
                          "inside, often a sliver between overlapping walls): find and fix the overlapping or doubled walls " +
                          "on {2} that close them off", list.Count - placeless, placeless, g.Key.Level);
            return string.Format(CultureInfo.InvariantCulture, "{0} enclosed areas on {1} have no Room ({2:0.#} to {3:0.#} sq ft; ",
                                 list.Count, g.Key.Level, list.Min(a => a.Area), list.Max(a => a.Area)) + what + "; " + roof;
        }).ToList();

    /// <summary>Each enclosed area sent as a space whose use isn't known, one line each, for the log.</summary>
    public static List<string> UnknownAreaWords(RevitModel model) => UnknownAreas(model).Select(a => AreaWords(model, a)).ToList();

    private static string AreaWords(RevitModel model, EnclosedArea a)
    {
        if (a.PointInside is not { } inside)
            return string.Format(CultureInfo.InvariantCulture,
                                 "An enclosed area on {0} has no Room ({1:0.#} sq ft; Revit couldn't give a point inside it, " +
                                 "often a sliver between overlapping walls)", a.Level, a.Area);
        var p = model.InternalToShared.Apply(inside);
        return string.Format(CultureInfo.InvariantCulture, "An enclosed area on {0} has no Room ({1:0.#} sq ft, around x {2:0.##}, y {3:0.##})",
                             a.Level, a.Area, p.X, p.Y);
    }

    /// <summary>The enclosed areas the reader sends as spaces whose use isn't known (<c>unknown_spaces</c>): every
    /// area Revit finds with no Room in it (<c>PlanCircuit.IsRoomLocated</c> false), except one that lies in a placed
    /// Room of the design checked on its level (its point inside within the Room's own outline, 1/16 in clear of
    /// it: Revit's circuits are the main model's, and a Room in the design option checked doesn't count in them),
    /// and, with <paramref name="levelMarks"/>, one on a level marked "no rooms on this level" whose mark stands
    /// (no Room is drawn on it: <see cref="LevelConflicts"/>). Empty when the areas couldn't be read (then no room is).</summary>
    public static List<EnclosedArea> UnknownAreas(RevitModel model, bool levelMarks = true)
    {
        if (model.Interior is not { EnclosedAreas: { } areas } records)
            return [];
        var cleared = levelMarks ? ClearedLevels(model) : [];
        var rooms = PlacedRooms(model).ToList();
        return areas.Where(a => !a.HasRoom && !(a.LevelId is { } l && cleared.Contains(l)) && !rooms.Any(r => Lies(a, r))).ToList();
    }

    /// <summary>The records of the placed Rooms of the design checked.</summary>
    private static IEnumerable<RoomRecord> PlacedRooms(RevitModel model)
    {
        var placed = MarkReading.InDesign(model).Where(e => MarkReading.KindOf(e) == MarkedKind.Room && e.Placement == RoomPlacement.Placed)
            .Select(e => e.UniqueId).ToHashSet(StringComparer.Ordinal);
        return (model.Interior?.Rooms ?? []).Where(r => placed.Contains(r.UniqueId));
    }

    /// <summary>The area's point inside lies within the room's own outline (inside an odd number of its loops, so not
    /// in a hole), more than 1/16 in from every edge, on the same level; a room with a curved edge, or a level not
    /// given, never holds it (read as a chord, the point could be outside the room).</summary>
    private static bool Lies(EnclosedArea a, RoomRecord r)
    {
        if (a.PointInside is not { } point || a.LevelId is null || r.LevelId != a.LevelId ||
            r.Boundary is not { Count: > 0 } loops || loops.Any(l => l.Count < 3 || l.Any(s => !s.IsLine)))
            return false;                                           // no point inside: never said to lie in a Room
        var (x, y) = (point.X, point.Y);
        var inside = false;
        foreach (var loop in loops)
            foreach (var s in loop)
            {
                double x1 = s.Start.X, y1 = s.Start.Y, x2 = s.End.X, y2 = s.End.Y;
                double dx = x2 - x1, dy = y2 - y1, len2 = dx * dx + dy * dy;
                var t = len2 > 0 ? Math.Clamp(((x - x1) * dx + (y - y1) * dy) / len2, 0, 1) : 0;
                if (Math.Sqrt(Math.Pow(x - x1 - t * dx, 2) + Math.Pow(y - y1 - t * dy, 2)) <= Sixteenth)
                    return false;                                   // on its edge: not clearly in it
                if ((y1 > y) != (y2 > y) && x < x1 + (y - y1) * dx / dy)
                    inside = !inside;
            }
        return inside;
    }

    /// <summary>The levels marked "no rooms on this level" Yes with no Room of the design checked drawn on them.</summary>
    private static HashSet<string> ClearedLevels(RevitModel model)
    {
        var withRooms = RoomLevels(model);
        return MarkReading.LevelsMarkedNoRooms(model).Select(l => l.UniqueId).Where(id => !withRooms.ContainsKey(id))
            .ToHashSet(StringComparer.Ordinal);
    }

    /// <summary>Each level's Rooms of the design checked (placed or not), by the level's <c>UniqueId</c>.</summary>
    private static Dictionary<string, List<MarkedElement>> RoomLevels(RevitModel model)
    {
        var rooms = MarkReading.InDesign(model).Where(e => MarkReading.KindOf(e) == MarkedKind.Room)
            .ToDictionary(e => e.UniqueId, StringComparer.Ordinal);
        return (model.Interior?.Rooms ?? []).Where(r => r.LevelId is not null && rooms.ContainsKey(r.UniqueId))
            .GroupBy(r => r.LevelId!, StringComparer.Ordinal)
            .ToDictionary(g => g.Key, g => g.Select(r => rooms[r.UniqueId]).ToList(), StringComparer.Ordinal);
    }

    /// <summary>Each level marked "no rooms on this level" Yes with a Room drawn on it: the two disagree, so the mark
    /// doesn't count (its enclosed areas with no Room are sent as spaces whose use isn't known) and the Room is read as
    /// any other; listed first in the marking list, never dropped in silence.</summary>
    public static List<string> LevelConflicts(RevitModel model)
    {
        if (model.Interior is null)
            return [];
        var withRooms = RoomLevels(model);
        return MarkReading.LevelsMarkedNoRooms(model).Where(l => withRooms.ContainsKey(l.UniqueId))
            .Select(l => $"Level \"{l.Name ?? l.UniqueId}\" is marked {Marks.NoRoomsOnLevel.Name} Yes, but " +
                         string.Join(", ", withRooms[l.UniqueId].Select(r => $"Room \"{RoomName(r)}\"")) +
                         (withRooms[l.UniqueId].Count == 1 ? " is" : " are") + " drawn on it: delete the Room or mark the level No " +
                         "(until then the mark doesn't count, and its enclosed areas with no Room each keep the sleeping-room rules needing review)")
            .ToList();
    }

    /// <summary>The enclosed areas sent as spaces whose use isn't known, as the description's <c>unknown_spaces</c>
    /// (each <c>{id, name}</c>: an id from its level and place, the same at every read of the same model).</summary>
    private static JsonArray UnknownSpaces(RevitModel model, List<EnclosedArea> areas)
    {
        var spaces = new JsonArray();
        foreach (var (a, id, outline) in UnknownSpaceList(model, areas))
        {
            var space = new JsonObject { ["id"] = id, ["name"] = AreaWords(model, a) };
            // its story (escape routes): an unknown space on a story keeps that story's routes needing review
            if (a.LevelId is { } level && (model.Interior?.Levels ?? []).Any(l => l.UniqueId == level))
                space["level"] = level;
            if (outline is not null)
                space["outline"] = new JsonArray(outline.Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray());
            spaces.Add(space);
        }
        return spaces;
    }

    /// <summary>Each enclosed area sent as a space whose use isn't known, with its id in the description (from its level
    /// and place, the same at every read of the same model) and its outline in shared plan points (the loop Revit gives a
    /// Room placed in it for the moment, <see cref="EnclosedArea.Outline"/>), null when that couldn't be read or isn't a
    /// simple outline of straight segments.</summary>
    internal static List<(EnclosedArea Area, string Id, List<P2>? Outline)> UnknownSpaceList(RevitModel model, List<EnclosedArea>? areas = null)
    {
        var list = new List<(EnclosedArea, string, List<P2>?)>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var a in areas ?? UnknownAreas(model))
        {
            var id = a.PointInside is { } inside
                ? string.Format(CultureInfo.InvariantCulture, "enclosed-area:{0}:{1:0.###},{2:0.###}", a.LevelId ?? a.Level,
                                model.InternalToShared.Apply(inside).X, model.InternalToShared.Apply(inside).Y)
                : string.Format(CultureInfo.InvariantCulture, "enclosed-area:{0}:no-point:{1:0.###}sf", a.LevelId ?? a.Level, a.Area);
            for (var n = 2; !ids.Add(id); n++)
                id = $"{id}#{n}";
            var outline = a.Outline is { Count: >= 3 } o
                ? PlanGeometry.Clean(o.Select(model.InternalToShared.Apply).Select(p => new P2(p.X, p.Y)).ToList()) : null;
            list.Add((a, id, outline is not null && PlanGeometry.IsSimple(outline) ? outline : null));
        }
        return list;
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

    /// <summary>A room's floor as read (shared plan points): its outline, the holes in it (a column or chase it goes
    /// round: its second and later boundary loops), the floor's elevation its level and offset give (null when they
    /// can't be read), and the elements bounding it. What the escape routes are read over (<see cref="RouteReader"/>).</summary>
    internal sealed record RoomPlan(List<P2> Outer, List<List<P2>> Holes, double? Floor, HashSet<string> Bounding, RoomRecord Record,
                                    HashSet<string>? StandingWalls = null);

    private static void ReadRoom(RevitModel model, InteriorRecords records, RoomRecord rec, JsonObject room,
                                 List<InteriorNote> notes, bool? sleeping, Dictionary<string, RoomPlan> plans)
    {
        var id = rec.UniqueId;
        var t = model.InternalToShared;
        void Out(string field, string why) => notes.Add(new(id, field, why));

        // the floor's outline: loops of straight segments at the finished faces, nothing inside it unbounded; a loop
        // inside the outline is a hole (a column, a chase), sent as one for any room but one marked a sleeping room: the
        // house's floor area reads the outline alone, so a bedroom's would count the column's floor (never a pass). A
        // room not marked is sent so too: with a sleeping flag missing the house's measures read no room at all
        List<P2>? plan = null;
        List<List<P2>> holes = [];
        HashSet<string> walls = [];
        var bounding = new HashSet<string>(StringComparer.Ordinal);
        if (rec.Boundary is not { } loops || loops.Count == 0)
            Out("floor", "Revit gives no boundary for this room");
        else if (loops.Count > 1 && sleeping is true)
            Out("floor", $"it has {loops.Count} boundary loops (a column or a chase inside it): a floor with a hole isn't read yet " +
                         "for a sleeping room, whose floor area would count the hole");
        else if (loops.Any(l => l.Any(s => !s.IsLine)))
            Out("floor", "its boundary has a curved segment: read only as straight segments, never as a chord");
        else
        {
            foreach (var s in loops.SelectMany(l => l).Where(s => s.Element is not null))
                bounding.Add(s.Element!);
            var cleaned = loops.Select(l => PlanGeometry.Clean(l.Select(s => t.Apply(s.Start)).Select(p => new P2(p.X, p.Y)).ToList())).ToList();
            if (cleaned.Any(c => c is null || !PlanGeometry.IsSimple(c)))
                Out("floor", "its boundary isn't a simple outline");
            else
            {
                // the outline is the loop with the largest area (Revit doesn't promise the outer loop comes first)
                var outer = cleaned.OrderByDescending(c => PlanGeometry.Area(c!)).First()!;
                var inner = cleaned.Where(c => !ReferenceEquals(c, outer)).Select(c => c!).ToList();
                if (RouteReader.HolesProblem(outer, inner) is { } holesWhy)
                    Out("floor", holesWhy);
                else
                    (plan, holes) = (outer, inner);
            }
        }
        if (plan is not null)
        {
            if (rec.Inside is not { } inside)
            {
                Out("floor", "what stands inside it couldn't be looked for");
                plan = null;
            }
            else if (inside.Where(e => InDesign(model, e) && !bounding.Contains(e.UniqueId) && !NotBuilding.Contains(e.BuiltInCategory)
                                       && !InBoundingWall(e, bounding)).ToList() is { Count: > 0 } standing)
            {
                // a wall standing in a room that isn't a sleeping room is sent with the floor, as an obstruction (the
                // route code then only loses floor: more cautious); a sleeping room's floor area would count it, so a
                // sleeping room's floor is left out as before, and anything else standing in any room leaves it out
                if (sleeping is true || standing.Any(e => e.BuiltInCategory != "OST_Walls"))
                {
                    Out("floor", "something stands inside its outline without bounding it (" + string.Join(", ", standing.Select(Named).Distinct()) +
                                 "): it may be two rooms, or smaller than its outline");
                    plan = null;
                }
                else
                    walls = standing.Select(e => e.UniqueId).ToHashSet(StringComparer.Ordinal);
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
        plans[id] = new(plan, holes, null, bounding, rec, walls);

        // the floor's elevation: its level and offset, checked against the slab top under the whole room
        if (rec.LevelElevation is not { } level || rec.BaseOffset is not { } offset)
        {
            Out("floor_elevation", "its level or base offset couldn't be read");
            Out("ceilings", "worked out above the floor's elevation, which couldn't be read");
            return;
        }
        var at = rec.Boundary![0][0].Start;
        var claimed = t.Apply(new Xyz(at.X, at.Y, level + offset)).Z;
        plans[id] = plans[id] with { Floor = claimed };
        if (SlabProblem(model, rec, plan, claimed) is { } slab)
            Out("floor_elevation", slab);
        else
            room["floor_elevation"] = claimed;

        if (Ceilings(model, rec, plan, claimed, bounding, out var why) is { } pieces)
            room["ceilings"] = pieces;
        else
            Out("ceilings", why!);
    }

    /// <summary>A window or door in one of the walls bounding the room: part of that boundary, so neither something
    /// standing inside the room nor a ceiling over it (its trim may reach into the room). Only windows and doors:
    /// anything else a bounding wall hosts (a wall-hosted bulkhead, a shelf, a soffit) is read like any other element
    /// (review round 1: a wall-hosted Generic Model 6.5 ft up was never a ceiling).</summary>
    internal static bool InBoundingWall(NearbyElement e, HashSet<string> bounding) =>
        e.BuiltInCategory is "OST_Windows" or "OST_Doors" && e.Host is { } h && bounding.Contains(h);

    /// <summary>In the design checked (the outside reader's one rule, as the stairs' and guards' surroundings): an
    /// element demolished by the last phase, or in a design option that isn't the one checked of its set (a secondary
    /// option's wall, roof or floor: Revit's collectors give every option's), isn't in, under or over the room.</summary>
    internal static bool InDesign(RevitModel model, NearbyElement e) => SiteReader.InDesignChecked(model, e.PhaseDemolished, e.DesignOption);

    internal static string Named(NearbyElement e) =>
        string.IsNullOrWhiteSpace(e.Name) ? e.BuiltInCategory.Replace("OST_", "") : $"{e.BuiltInCategory.Replace("OST_", "")} \"{e.Name}\"";

    private static bool Reaches(RevitModel model, RevitBox box, List<P2> plan)
    {
        var b = Box3.Turned(box.Min, box.Max, box.Transform is { } own ? model.InternalToShared.After(own) : model.InternalToShared);
        double x0 = plan.Min(p => p.X), x1 = plan.Max(p => p.X), y0 = plan.Min(p => p.Y), y1 = plan.Max(p => p.Y);
        return b.Min.X < x1 && b.Max.X > x0 && b.Min.Y < y1 && b.Max.Y > y0;
    }

    internal static List<Xyz> Shared(RevitModel model, IEnumerable<Xyz> points) => points.Select(model.InternalToShared.Apply).ToList();

    internal static Xyz Turned(RevitModel model, Xyz v)
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
        foreach (var e in under.Where(e => InDesign(model, e)))
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
        foreach (var e in over.Where(e => InDesign(model, e)))
        {
            if (e.UniqueId == rec.UniqueId || NotBuilding.Contains(e.BuiltInCategory) || InBoundingWall(e, bounding))
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
                                          List<InteriorNote> notes, JsonObject evidence, Dictionary<string, RoomPlan> plans,
                                          (GroundReader.Grounds Set, List<(EnclosedArea Area, string Id, List<P2>? Outline)> Unknown)? ground)
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
            Out("stated_clear", "a door's maker's clear opening is sent with the door (doors); as an escape opening its " +
                                "bottom isn't stated by a door's marks yet");
        opening["stated_well"] = StatedWell(e, o, Out);
        // the ground just outside it, from a Toposolid stated to show the finished ground (GroundReader): below grade
        // and the well's least depth are then measured; only an escape opening's reason why not is said (its rules
        // read it), and nothing at all where no ground is drawn. A window's only: a door's clear bottom isn't sent, so
        // its ground could only unsettle its Below grade mark, never measure it (review round 1)
        if (ground is { } g && rec is not null && o.Kind == MarkedKind.Window)
        {
            if (evidence[id] is not JsonObject seen)
                evidence[id] = seen = new JsonObject();
            if (GroundReader.Outside(model, g.Set, rec, opening["room"]?.GetValue<string>(), "window", plans, g.Unknown, seen, out var why) is { } at)
                opening["ground_outside"] = at;
            else if (o.Escape is true)
                Out("ground_outside", why!);
        }
        return opening;
    }

    /// <summary>What the architect states of the opening and its area well (<c>stated_well</c>, BCNYS 1031.5): every
    /// <see cref="Marks.WellMarks"/> mark set, as typed (a length in feet and an area in square feet, the description's
    /// units); one blank is left out, which the measuring reads as not stated (never 0 or No), naming the field and the
    /// mark. Always sent, so a blank one is said by name. A word Gordium can't read is said here and not sent. Only an
    /// escape opening's blanks are noted (its rules read them): every other window's would be noise.</summary>
    private static JsonObject StatedWell(MarkedElement e, OpeningMarks o, Action<string, string> note)
    {
        var well = new JsonObject();
        foreach (var (mark, key) in Marks.WellMarks)
        {
            var v = MarkReading.Value(e, mark);
            switch (mark.Kind)
            {
                case MarkValueKind.YesNo when Marks.YesNo(v) is { } yes:
                    well[key] = yes;
                    break;
                case MarkValueKind.Length when Marks.Length(v) is { } feet:
                    well[key] = feet;
                    break;
                case MarkValueKind.Area when Marks.Area(v) is { } squareFeet:
                    well[key] = squareFeet;
                    break;
                case MarkValueKind.Text when Marks.Text(v) is { } word:
                    if (WellLadderWords.Table.Of(word) is { } said)
                        well[key] = said;
                    else
                        note("stated_well." + key, $"{mark.Name} is \"{word}\", not one of: {WellLadderWords.Listed}");
                    break;
                default:
                    if (o.Escape is true)
                        note("stated_well." + key, mark.Name + " is not set");
                    break;
            }
        }
        return well;
    }

    /// <summary>The window's (or, with <paramref name="door"/>, the door's) values the stamp is checked against, read
    /// now.</summary>
    public static ClearValues ClearNow(MarkedElement e, OpeningRecord rec, bool door = false)
    {
        var mapped = MappedName(Marks.Text(MarkReading.Value(e, Marks.ClearConfirmed)));
        return new(e.TypeUniqueId, rec.TypeWidth, rec.TypeHeight, Marks.Text(MarkReading.Value(e, Marks.Operation)),
                   Marks.Length(MarkReading.Value(e, Marks.ClearWidth)), Marks.Length(MarkReading.Value(e, Marks.ClearHeight)),
                   door ? null : Marks.Length(MarkReading.Value(e, Marks.ClearOffset)), Marks.Text(MarkReading.Value(e, Marks.ClearSource)),
                   mapped, mapped is not null && rec.TypeLengths.TryGetValue(mapped, out var v) ? v : null, door);
    }

    // ---- a door (step 5) -------------------------------------------------------------------------------------

    /// <summary>A door: its exit mark and operation (a mark never set is not given), and the maker's clear opening its
    /// type's stamp confirms. Nothing drawn is sent (its stops, hinge pin, leaf, threshold): door families don't model
    /// them consistently (decision 2), so a drawn size is never read from a family's geometry.</summary>
    private static JsonObject ReadDoor(InteriorRecords records, MarkedElement e, DoorMarks d, List<InteriorNote> notes,
                                       JsonObject evidence)
    {
        // a door is an opening too: its notes as a door say so (doors.stated_clear, never the opening's stated_clear)
        void Out(string field, string why) => notes.Add(new(d.Id, "doors." + field, why));
        var door = new JsonObject { ["id"] = d.Id, ["name"] = MarkingList.Label(e) };
        if (d.Exit is { } exit)
            door["exit"] = exit;
        else
            Out("exit", Marks.ExitDoor.Name + " is not set");
        if (d.Operation is { } operation)
            door["operation"] = operation;
        else
            Out("operation", Marks.Operation.Name + " is not set on its type, or isn't a door's word Gordium reads");
        // how many leaves its type's opening has (BCNYS 1010.1.1): sent only as 1 or 2; blank or another number is said
        // and not sent, so the door width rule needs review for it (never a pass)
        if (d.Leaves is 1 or 2)
            door["leaves"] = d.Leaves.Value;
        else
            Out("leaves", d.Leaves is { } n
                ? $"{Marks.DoorLeaves.Name} is {n.ToString(System.Globalization.CultureInfo.InvariantCulture)} on its type, not 1 or 2"
                : Marks.DoorLeaves.Name + " is not set on its type");
        // what latches or locks it (BCNYS 1010.2.8): sent only as one of the list's words; blank or another word is said
        // and not sent, so the panic hardware rule needs review for it (never a pass)
        if (d.Hardware is { } hardware)
            door["hardware"] = hardware;
        else
            Out("hardware", d.HardwareWord is { } typed
                ? $"{Marks.DoorHardware.Name} is \"{typed}\", not one of: {HardwareWords.Table.Listed}"
                : Marks.DoorHardware.Name + " is not set");
        Out("threshold_top", "a door's drawn stops, hinge, leaf, threshold and head stop aren't read from its family (door " +
                             "families don't model them consistently): its maker's clear opening is read instead");
        if (records.Openings.FirstOrDefault(x => x.UniqueId == d.Id) is not { } rec)
            Out("stated_clear", "the Revit layer gave nothing for this door");
        else if (DoorClear(e, rec, evidence, out var why) is { } clear)
            door["stated_clear"] = clear;
        else
            Out("stated_clear", why!);
        return door;
    }

    /// <summary>The door's maker's clear opening, sent only when its type's stamp, made for a door, confirms every
    /// value now (the type's id, size and operation, the clear width and height, the source, a mapped maker's
    /// parameter), and it fits inside the door as placed (its width along the wall, its height), 1/16 in to spare.</summary>
    private static JsonObject? DoorClear(MarkedElement e, OpeningRecord rec, JsonObject evidence, out string? why)
    {
        why = null;
        var now = ClearNow(e, rec, door: true);
        if (ClearStamp.Why(Marks.Text(MarkReading.Value(e, Marks.ClearConfirmed)), now, rec.TypeLengths) is { } stamp)
        {
            why = stamp;
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
        var u = placed.Select(p => (p.X * along.X + p.Y * along.Y) / length).ToList();
        double width = u.Max() - u.Min(), height = placed.Max(p => p.Z) - placed.Min(p => p.Z);
        double clearWidth = now.ClearWidth!.Value, clearHeight = now.ClearHeight!.Value;
        evidence[e.UniqueId] = new JsonObject
        {
            ["placed"] = new JsonObject { ["width"] = width, ["height"] = height },
            ["wall_opening_by"] = rec.WallOpeningBy,
            ["revit_layer"] = new JsonArray(rec.Diagnostics.Select(x => (JsonNode?)x).ToArray()),
        };
        if (clearWidth > width + Sixteenth || clearHeight > height + Sixteenth)
        {
            why = $"its clear opening ({ClearStamp.Inches(clearWidth)} by {ClearStamp.Inches(clearHeight)}) doesn't fit inside the door " +
                  $"as placed ({ClearStamp.Inches(width)} by {ClearStamp.Inches(height)})";
            return null;
        }
        return new JsonObject { ["width"] = clearWidth, ["height"] = clearHeight, ["source"] = now.Source };
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
        var record = new JsonObject
        {
            ["sill_line"] = t.Apply(new Xyz(at.X, at.Y, sillLine)).Z, ["wall_opening_by"] = rec.WallOpeningBy,
            ["revit_layer"] = new JsonArray(rec.Diagnostics.Select(d => (JsonNode?)d).ToArray()),
        };
        evidence[e.UniqueId] = record;
        if (!rec.HostIsWall || rec.WallOpening is not { Count: > 0 } cut)
        {
            record["wall_opening_bottom"] = null;
            why = rec.HostIsWall && rec.WallOpeningUnread
                ? "its wall's geometry couldn't be read (Revit gave no edges for one of its faces, or refused), so the opening " +
                  "it cuts, and so its sill line (Sill Height), can't be checked against anything drawn"
                : "no opening it cuts in a wall was found, so its sill line (Sill Height) can't be checked against anything drawn";
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
