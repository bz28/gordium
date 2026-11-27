using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>
/// The escape routes' part of the interior description (docs/revit/revit_interior_reading_design.md, section 10; the
/// keys: docs/interior/interior_description_format.md, "The route additions"): each story's levels, each room's use,
/// lock and pass-through marks, holes and obstructions, each door's place in its wall, the rooms it joins and which
/// exit it is, and the passages where two rooms meet with no wall. The route code reads them
/// (<c>model_measurement.routes.floor</c>). The one rule, as everywhere in the reader: a value is sent only when it is
/// read exactly; anything else is left out with its reason in <see cref="InteriorReadResult.Notes"/>, and a key left
/// out is "not read" (the route code then measures nothing it could get wrong), never a default.
/// </summary>
public static class RouteReader
{
    /// <summary>IBC 1003.3.1, headroom: "Protruding objects are permitted to extend below the minimum ceiling height
    /// ... provided a minimum headroom of 80 inches (2032 mm) shall be provided for any walking surface". Anything in
    /// a room lower than this stands in a route's way (ft).</summary>
    public const double Headroom = 80.0 / 12;

    /// <summary>The far side of a door that opens to no room.</summary>
    public const string Outside = "outside";

    private const double S = InteriorReader.Sixteenth;

    /// <summary>The least floor a door opens onto, sq ft: its narrowest clear width the route code reads (24 in) by an
    /// inch beyond its wall's face. An enclosed area with no Room smaller than this (a sliver between two walls drawn face
    /// to face, which Revit can't outline: the Children's Odyssey's two, 0 sq ft) can't be what is beyond a door, so it
    /// never stops a door's far side being read as outside; any larger one not outlined does.</summary>
    public const double SmallestBeyond = 2.0 * (1.0 / 12);

    /// <summary>How far the middle of the opening a door takes in its wall (the opening it cuts; only when no cut is found,
    /// what is drawn of it strictly between the wall's faces) may be from where the door is placed, ft: 1 in; farther,
    /// its clear opening isn't placed.</summary>
    public const double CentreAgree = 1.0 / 12;

    /// <summary>How much wider than the door (its type's width or its clear width, the larger) the opening it takes in its
    /// wall may be (the opening it cuts; only when no cut is found, what is drawn of it strictly between the wall's
    /// faces), ft: 8 in, two frame jambs of up to 4 in each; wider is a sidelight or a pocket.</summary>
    public const double FrameAllowance = 8.0 / 12;

    /// <summary>What stands in a route's way, by Revit category (the format's kinds: casework, furniture, equipment,
    /// fixture), with whether it is fixed in place. Revit can't tell a movable piece from a fixed one, so each category
    /// says it once (furniture is movable; casework, systems furniture, plumbing and lighting fixtures, and equipment
    /// fixed). An element of any other category within <see cref="Headroom"/> of a room's floor over it leaves the
    /// room's obstructions not read (section 10: an unknown solid is never ignored).</summary>
    public static readonly IReadOnlyDictionary<string, (string Kind, bool Fixed)> ObstructionKinds =
        new Dictionary<string, (string, bool)>(StringComparer.Ordinal)
        {
            ["OST_Casework"] = ("casework", true),
            ["OST_Furniture"] = ("furniture", false),
            ["OST_FurnitureSystems"] = ("furniture", true),
            ["OST_PlumbingFixtures"] = ("fixture", true),
            ["OST_LightingFixtures"] = ("fixture", true),
            ["OST_SpecialityEquipment"] = ("equipment", true),
            ["OST_MechanicalEquipment"] = ("equipment", true),
            ["OST_ElectricalEquipment"] = ("equipment", true),
        };

    /// <summary>A wall standing in a room without bounding it (a room that isn't a sleeping room keeps its floor, section
    /// 10): the format has no wall kind, so it is sent as a fixed fixture, its footprint taken out of the floor.</summary>
    public static readonly (string Kind, bool Fixed) StandingWall = ("fixture", true);

    // ---- a room's marks ---------------------------------------------------------------------------------------

    /// <summary>A room's use, lock and pass-through marks: each sent only as the architect set it (a word through
    /// <see cref="RoomUses"/>); unset or not a word Gordium reads, left out (the room is then end-only: a route may
    /// start in it, never cross it).</summary>
    internal static void RoomMarks(RoomMarks r, JsonObject room, List<InteriorNote> notes)
    {
        if (r.Use is { } use)
            room["use"] = use;
        else
            notes.Add(new(r.Id, "use", r.UseWord is null
                ? Marks.Use.Name + " is not set: an escape route never passes through it"
                : $"{Marks.Use.Name} is \"{r.UseWord}\", not one of Gordium's ({RoomUses.Table.Listed}): an escape route never passes through it"));
        if (r.Lockable is { } lockable)
            room["lockable"] = lockable;
        else
            notes.Add(new(r.Id, "lockable", Marks.CanBeLocked.Name + " is not set: an escape route never passes through it"));
        if (r.PassThrough is { } through)
            room["pass_through"] = through;
        else
            notes.Add(new(r.Id, "pass_through", Marks.PassThrough.Name + " is not set: an escape route never passes through it"));
        // the architect's statement that nobody occupies the room (route note decision 1b): sent as marked; unset is
        // left out, and the room is occupied (measured), so no note: blank is the usual answer
        if (r.NotOccupied is { } notOccupied)
            room["not_occupied"] = notOccupied;
        // its Table 1004.5 function (the Building Code's occupant loads): one of Gordium's words as the table's row; a
        // word not in the list is sent as typed, so the checker says it and leaves the room's load, and its story's, not
        // worked out (the format's rule) and still sees a function stated on a corridor or an exit: never dropped, which
        // would read a closet or toilet as holding no load of its own (review round 7); blank is the usual answer
        if (r.Function is { } function)
            room["function"] = function;
        else if (r.FunctionWord is { } typed)
        {
            room["function"] = typed;
            notes.Add(new(r.Id, "function", $"{Marks.RoomFunction.Name} is \"{typed}\", not one of Table 1004.5's functions Gordium lists: sent as typed, so its occupant load and its story's need review"));
        }
    }

    // ---- everything else, once the rooms and doors are read ----------------------------------------------------

    internal static void Add(RevitModel model, InteriorRecords records, JsonObject interior,
                             Dictionary<string, InteriorReader.RoomPlan> plans, List<InteriorNote> notes, JsonObject evidence)
    {
        // each door's place in its wall as read, sent or not (the trial's record that it can be read)
        var routeEvidence = new JsonObject();
        evidence["route_doors"] = routeEvidence;
        var levels = records.Levels?.GroupBy(l => l.UniqueId, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.First(), StringComparer.Ordinal);
        var used = new HashSet<string>(StringComparer.Ordinal);
        string? Level(string part, string? id, string field = "level")
        {
            var why = levels is null ? "the model's levels weren't read"
                : id is null ? "its level couldn't be read"
                : !levels.ContainsKey(id) ? "its level isn't one of the model's levels" : null;
            if (why is not null)
            {
                notes.Add(new(part, field, why + ": its story's escape routes aren't measured"));
                return null;
            }
            used.Add(id!);
            return id;
        }

        var roomObjects = interior["rooms"]?.AsArray().Select(x => x!.AsObject()).ToList() ?? [];
        var roomLevel = new Dictionary<string, string?>(StringComparer.Ordinal);
        foreach (var room in roomObjects)
        {
            var id = room["id"]!.GetValue<string>();
            var rec = records.Rooms.FirstOrDefault(x => x.UniqueId == id);
            if (Level(id, rec?.LevelId) is { } level)
                room["level"] = level;
            roomLevel[id] = rec?.LevelId;
            if (!plans.TryGetValue(id, out var plan))
            {
                notes.Add(new(id, "obstructions", "read over its floor's outline, which isn't read: its story's escape routes aren't measured"));
                continue;
            }
            room["holes"] = new JsonArray(plan.Holes.Select(Outline).ToArray());
            if (Obstructions(model, plan, out var why) is { } obstructions)
                room["obstructions"] = obstructions;
            else
                notes.Add(new(id, "obstructions", why! + ": its story's escape routes aren't measured"));
        }
        foreach (var space in interior["unknown_spaces"]?.AsArray().Select(x => x!.AsObject()) ?? [])
            if (space["level"] is JsonNode l)
                used.Add(l.GetValue<string>());
            else
                notes.Add(new(space["id"]!.GetValue<string>(), "level", "its level couldn't be read: no story's escape routes are measured"));

        // the passages first: a room open to another along a separation line is never an exit enclosure
        var joined = new HashSet<string>(StringComparer.Ordinal);
        if (interior["rooms"] is not null)
        {
            if (records.SeparationLines is null)
                notes.Add(new("model", "passages", "the room separation lines weren't read: no story's escape routes are measured"));
            else
            {
                var passages = Passages(model, records, roomObjects.Select(r => r["id"]!.GetValue<string>()).ToHashSet(StringComparer.Ordinal));
                interior["passages"] = passages;
                foreach (var p in passages)
                    foreach (var r in p!["rooms"]!.AsArray())
                        joined.Add(r!.GetValue<string>());
            }
        }

        if (interior["doors"] is JsonArray doors)
            Doors(model, records, doors, roomObjects, plans, notes, joined, routeEvidence,
                  id => Level(id, records.Openings.FirstOrDefault(o => o.UniqueId == id)?.LevelId, "doors.level"));

        // each story's outlines (the diagonal and the areas, decision 8): only where they close exactly
        if (levels is not null)
        {
            var outlines = new JsonArray();
            foreach (var level in records.Levels!.Where(l => used.Contains(l.UniqueId)))
            {
                var (outer, inner, why) = Outlines(model, level.UniqueId);
                if (outer is not null && inner is not null)
                    outlines.Add(new JsonObject { ["level"] = level.UniqueId, ["outer"] = Outline(outer), ["inner"] = Outline(inner) });
                else
                    notes.Add(new(level.UniqueId, "story_outlines", why! + ": the diagonal and the story's areas aren't measured"));
            }
            if (outlines.Count > 0)
                interior["story_outlines"] = outlines;
        }

        // every level of the model, a level with nothing drawn on it too (an open parking story, a roof, a datum): which
        // story is the first above grade plane can't be told while one may be missing (story_place.py: every place
        // needs review without them)
        if (levels is not null && used.Count > 0)
            interior["all_levels"] = new JsonArray(levels.Values.Select(l => (JsonNode)new JsonObject
            {
                ["id"] = l.UniqueId, ["name"] = l.Name, ["elevation"] = model.InternalToShared.Apply(new Xyz(0, 0, l.Elevation)).Z,
            }).ToArray());
        if (levels is not null && used.Count > 0)
            interior["levels"] = new JsonArray(records.Levels!.Where(l => used.Remove(l.UniqueId)).Select(l => (JsonNode)new JsonObject
            {
                ["id"] = l.UniqueId, ["name"] = l.Name, ["elevation"] = model.InternalToShared.Apply(new Xyz(0, 0, l.Elevation)).Z,
            }).ToArray());
        else if (levels is null)
            notes.Add(new("model", "levels", "the model's levels weren't read: no story's escape routes are measured"));
    }

    private static JsonArray Outline(List<P2> p) => new(p.Select(q => (JsonNode)new JsonArray(q.X, q.Y)).ToArray());

    /// <summary>One story's outlines (<see cref="StoryOutlines"/>) from Revit's gross building area of its level.</summary>
    internal static (List<P2>? Outer, List<P2>? Inner, string? Why) Outlines(RevitModel model, string level)
    {
        if (model.Interior?.GrossAreas is not { } gross)
            return (null, null, "the building's outlines weren't read");
        // a courtyard is an enclosed area with no Room inside the building's outline: its area isn't told apart
        if (InteriorReader.UnknownSpaceList(model).Any(u => u.Area.LevelId == level && u.Area.Area >= SmallestBeyond))
            return (null, null, "an enclosed area with no Room on the level may be a courtyard, whose area the outline would count");
        var got = StoryOutlines.Of(gross.GetValueOrDefault(level), model.InternalToShared);
        return (got.Outer, got.Inner, got.Why);
    }

    private static string Xy(P2 p) => I($"({p.X:0.###}, {p.Y:0.###})");

    private static string I(FormattableString s) => s.ToString(CultureInfo.InvariantCulture);

    /// <summary>What was read for the escape routes, counted, for Read inside's log and dialog (the trial's check on a
    /// real model): the levels, the rooms with each field, the doors with each, the passages.</summary>
    public static List<string> Summary(InteriorReadResult read)
    {
        var i = read.Interior;
        var rooms = i["rooms"]?.AsArray().Select(r => r!.AsObject()).ToList() ?? [];
        var doors = i["doors"]?.AsArray().Select(d => d!.AsObject()).ToList() ?? [];
        int Rooms(string key) => rooms.Count(r => r[key] is not null);
        int Doors(string key) => doors.Count(d => d[key] is not null);
        return
        [
            i["levels"] is JsonArray levels
                ? $"levels: {levels.Count} ({string.Join(", ", levels.Select(l => l!["name"]!.GetValue<string>()))})" : "levels: not sent",
            $"rooms: {rooms.Count}; with a level {Rooms("level")}, a floor {Rooms("floor")}, holes {Rooms("holes")} " +
            $"({rooms.Sum(r => r["holes"]?.AsArray().Count ?? 0)} in all), obstructions {Rooms("obstructions")} " +
            $"({rooms.Sum(r => r["obstructions"]?.AsArray().Count ?? 0)} footprints); use {Rooms("use")}, can be locked {Rooms("lockable")}, " +
            $"pass through {Rooms("pass_through")}, marked not occupied {rooms.Count(r => r["not_occupied"]?.GetValue<bool>() == true)}",
            $"doors: {doors.Count}; with a level {Doors("level")}, a place in its wall {Doors("plan")} (its wall read " +
            $"{(read.Evidence["route_doors"] as JsonObject)?.Count(e => e.Value?["centre"] is not null) ?? 0}), sides {Doors("sides")} " +
            $"({doors.Count(d => d["sides"]?.AsArray().Any(s => s!.GetValue<string>() == Outside) == true)} to outside), " +
            $"exits {Doors("exit_kind")} ({doors.Where(d => d["exit_id"] is not null).Select(d => d["exit_id"]!.GetValue<string>()).Distinct().Count()} exits by id)",
            i["passages"] is JsonArray passages ? $"passages: {passages.Count}" : "passages: not sent",
            $"unknown spaces: {i["unknown_spaces"]?.AsArray().Count ?? 0}",
            i["story_outlines"] is JsonArray so ? $"story outlines: {so.Count}" : "story outlines: not sent (the notes say why)",
        ];
    }

    // ---- a room's holes ---------------------------------------------------------------------------------------

    /// <summary>Why a room's inner loops can't be read as holes in its outline (null when they can): each must lie
    /// wholly inside the outline, clear of its edges, and no two may overlap.</summary>
    public static string? HolesProblem(List<P2> outer, List<List<P2>> holes)
    {
        foreach (var h in holes)
            if (h.Any(p => !StrictlyInside(p, outer)))
                return "an inner boundary loop isn't wholly inside its outline";
        for (var i = 0; i < holes.Count; i++)
            for (var j = i + 1; j < holes.Count; j++)
                if (PlanGeometry.OverlapArea(PlanGeometry.Local(holes[i], outer[0]), PlanGeometry.Local(holes[j], outer[0])) is not { } a
                    || a > 1e-9 * PlanGeometry.Area(outer))
                    return "two of its inner boundary loops overlap";
        return null;
    }

    /// <summary>Inside the polygon (even-odd) and more than 1/16 in from every edge.</summary>
    internal static bool StrictlyInside(P2 p, List<P2> poly)
    {
        var inside = false;
        for (var i = 0; i < poly.Count; i++)
        {
            P2 a = poly[i], b = poly[(i + 1) % poly.Count];
            if (DistanceToSegment(p, a, b) <= S)
                return false;
            if ((a.Y > p.Y) != (b.Y > p.Y) && p.X < a.X + (p.Y - a.Y) * (b.X - a.X) / (b.Y - a.Y))
                inside = !inside;
        }
        return inside;
    }

    private static double DistanceToSegment(P2 p, P2 a, P2 b)
    {
        var d = b - a;
        var len2 = d.X * d.X + d.Y * d.Y;
        var t = len2 > 0 ? Math.Clamp(((p.X - a.X) * d.X + (p.Y - a.Y) * d.Y) / len2, 0, 1) : 0;
        return Math.Sqrt(Math.Pow(p.X - a.X - t * d.X, 2) + Math.Pow(p.Y - a.Y - t * d.Y, 2));
    }

    // ---- a room's obstructions --------------------------------------------------------------------------------

    /// <summary>Every piece of casework, furniture, equipment and fixture standing in the room (a face of it lower than
    /// <see cref="Headroom"/> over the room's floor), as the plan footprints of its faces (each face that isn't vertical:
    /// a flat one's outline, a curved one's points' convex hull; together they cover the piece's shadow, which the route
    /// code unites); <c>[]</c> when there is none. Null, with why, when anything else is within the headroom over the
    /// floor (a beam, a bulkhead, a low ceiling, an element of a category Gordium doesn't read), when an element's
    /// geometry couldn't be read, or when the floor's elevation isn't known.</summary>
    internal static JsonArray? Obstructions(RevitModel model, InteriorReader.RoomPlan plan, out string? why)
    {
        why = null;
        var rec = plan.Record;
        if (plan.Floor is not { } floor)
        {
            why = "its floor's elevation couldn't be read, so what stands on it can't be told from what is over it";
            return null;
        }
        if (rec.Over is not { } over || rec.Inside is not { } inside)
        {
            why = "what stands in it couldn't be looked for";
            return null;
        }
        var origin = plan.Outer[0];
        var outer = PlanGeometry.Local(plan.Outer, origin);
        var holes = plan.Holes.Select(h => PlanGeometry.Local(h, origin)).ToList();
        var roomArea = PlanGeometry.Area(outer) - holes.Sum(PlanGeometry.Area);
        double? AreaIn(List<P2> shape)
        {
            if (PlanGeometry.Overlap(outer, PlanGeometry.Local(shape, origin)) is not { } pieces)
                return null;
            foreach (var h in holes)
                if (PlanGeometry.Subtract(pieces, h) is { } left)
                    pieces = left;
                else
                    return null;
            return pieces.Sum(PlanGeometry.Area);
        }
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var list = new JsonArray();
        var looked = new HashSet<string>(StringComparer.Ordinal);
        foreach (var e in over.Where(e => InteriorReader.InDesign(model, e)))
        {
            if (e.UniqueId == rec.UniqueId || plan.Bounding.Contains(e.UniqueId) || InteriorReader.InBoundingWall(e, plan.Bounding)
                || e.BuiltInCategory is "OST_Rooms" or "OST_RoomSeparationLines")
                continue;                                    // the room, what bounds it, a window or door in its walls
            looked.Add(e.UniqueId);
            var known = ObstructionKinds.TryGetValue(e.BuiltInCategory, out var kind);
            if (plan.StandingWalls?.Contains(e.UniqueId) == true)
                (known, kind) = (true, StandingWall);        // a wall standing in it: its footprint stands in the way
            // no 3D faces, and the band's cut agrees nothing is there (round 5: an open shell or a failed cut is never
            // passed over as nothing drawn)
            if (e is { GeometryFailed: false, Faces.Count: 0, BandFailed: false, OpenShells: 0 })
            {
                if (!known)
                    continue;                                // nothing drawn (a base point, a line)
                // casework, furniture, equipment or a fixture drawn in 2D alone, its box over the room's floor (or no
                // box to tell): where it stands isn't read (review round 1: it was skipped as nothing drawn); one whose
                // box is beside the room changes nothing in it (round 2)
                if (e.Box is { } flat && Box3.Turned(flat.Min, flat.Max, flat.Transform is { } fown ? model.InternalToShared.After(fown) : model.InternalToShared) is var fb
                    && AreaIn([new(fb.Min.X, fb.Min.Y), new(fb.Max.X, fb.Min.Y), new(fb.Max.X, fb.Max.Y), new(fb.Min.X, fb.Max.Y)]) is { } over2d
                    && over2d <= roomArea * 1e-9)
                    continue;
                why = $"{InteriorReader.Named(e)} is drawn with no 3D faces, so where it stands isn't read";
                return null;
            }
            // what of it lies in the room's band, from just above its floor to the headroom: the Revit layer's
            // intersection of each of its solids with that slab (review round 3: picking faces by height kept only a
            // sill's strip of a standing wall). Its footprint is the plan outlines of the result's faces that aren't
            // vertical (a curved face by its points' hull), which together cover what of it is in the band
            if (e.OpenShells > 0)
            {
                why = $"{InteriorReader.Named(e)} is drawn with open surfaces (no volume) reaching within {Headroom * 12:0} in of its floor, which can't be cut to it, so what of it stands there isn't read";
                return null;
            }
            if (e.BandFailed || e.Banded is null)
            {
                if (e.Box is { } box && Box3.Turned(box.Min, box.Max, box.Transform is { } own ? model.InternalToShared.After(own)
                                                                                                : model.InternalToShared).Min.Z >= floor + Headroom)
                    continue;                                // wholly above the headroom
                why = e.Banded is null && !e.BandFailed
                    ? $"what of {InteriorReader.Named(e)} stands within {Headroom * 12:0} in of its floor wasn't read"
                    : $"what of {InteriorReader.Named(e)} stands within {Headroom * 12:0} in of its floor couldn't be cut out (Revit refused, or a mesh)";
                return null;
            }
            var shapes = new List<List<P2>>();
            var meets = false;
            foreach (var f in e.Banded)
            {
                List<P2>? shape;
                if (f.Planar)
                {
                    if (Math.Abs(InteriorReader.Turned(model, f.Normal).Z) <= 1e-9)
                        continue;                            // a side: no footprint of its own
                    shape = f.Loops.Any(l => l.Any(c => !c.IsLine))
                        ? Hull(InteriorReader.Shared(model, f.Points).Select(q => new P2(q.X, q.Y)))   // an arc edge: its hull
                        : f.Loops.Select(l => PlanGeometry.Clean(l.Select(c => model.InternalToShared.Apply(c.Start)).Select(q => new P2(q.X, q.Y)).ToList()))
                            .OfType<List<P2>>().OrderByDescending(PlanGeometry.Area).FirstOrDefault();
                    if (shape is not null && !PlanGeometry.IsSimple(shape))
                    {
                        why = $"a face of {InteriorReader.Named(e)} in it isn't a simple outline in plan";
                        return null;
                    }
                }
                else
                    shape = Hull(InteriorReader.Shared(model, f.Points).Select(q => new P2(q.X, q.Y)));
                if (shape is null)
                    continue;                                // a face with no area in plan
                if (AreaIn(shape) is not { } a)
                {
                    why = $"a face of {InteriorReader.Named(e)} in it couldn't be read in plan";
                    return null;
                }
                meets |= a > roomArea * 1e-9;
                shapes.Add(shape);
            }
            if (!meets)
                continue;                                    // beside the room, or above the headroom
            if (!known)
            {
                why = $"{InteriorReader.Named(e)} is lower than {Headroom * 12:0} in over its floor, and only casework, furniture, " +
                      "equipment and fixtures are read as what stands in a route's way";
                return null;
            }
            foreach (var shape in shapes)
                if (seen.Add(string.Join(";", shape.Select(p => $"{p.X.ToString("R", CultureInfo.InvariantCulture)},{p.Y.ToString("R", CultureInfo.InvariantCulture)}").Order(StringComparer.Ordinal))))
                    list.Add(new JsonObject { ["outline"] = Outline(shape), ["kind"] = kind.Kind, ["fixed"] = kind.Fixed });
        }
        // what the solid test found standing in the room must have been looked at above: never skipped unseen
        if (inside.Where(e => InteriorReader.InDesign(model, e) && (ObstructionKinds.ContainsKey(e.BuiltInCategory) || plan.StandingWalls?.Contains(e.UniqueId) == true)
                              && !looked.Contains(e.UniqueId))
                  .Select(InteriorReader.Named).FirstOrDefault() is { } missed)
        {
            why = $"{missed} stands in it, but its geometry wasn't read";
            return null;
        }
        return list;
    }

    /// <summary>The convex hull (anticlockwise), or null when the points have no area.</summary>
    internal static List<P2>? Hull(IEnumerable<P2> points)
    {
        var p = points.Distinct().OrderBy(q => q.X).ThenBy(q => q.Y).ToList();
        if (p.Count < 3)
            return null;
        var h = new List<P2>();
        foreach (var pass in new[] { p, Enumerable.Reverse(p).ToList() })
        {
            var start = h.Count;
            foreach (var q in pass)
            {
                while (h.Count >= start + 2 && P2.Cross(h[^1] - h[^2], q - h[^2]) <= 0)
                    h.RemoveAt(h.Count - 1);
                h.Add(q);
            }
            h.RemoveAt(h.Count - 1);
        }
        return PlanGeometry.Clean(h);
    }

    // ---- doors ------------------------------------------------------------------------------------------------

    private static void Doors(RevitModel model, InteriorRecords records, JsonArray doors, List<JsonObject> rooms,
                              Dictionary<string, InteriorReader.RoomPlan> plans, List<InteriorNote> notes, HashSet<string> joined, JsonObject evidence,
                              Func<string, string?> level)
    {
        var sent = rooms.Select(r => r["id"]!.GetValue<string>()).ToHashSet(StringComparer.Ordinal);
        var marks = MarkReading.Doors(model).ToDictionary(d => d.Id, StringComparer.Ordinal);
        var openings = records.Openings.ToDictionary(o => o.UniqueId, StringComparer.Ordinal);
        var unknown = InteriorReader.UnknownSpaceList(model);
        var sides = new Dictionary<string, string[]>(StringComparer.Ordinal);
        foreach (var door in doors.Select(d => d!.AsObject()))
        {
            var id = door["id"]!.GetValue<string>();
            void Out(string field, string why) => notes.Add(new(id, "doors." + field, why));
            if (level(id) is { } l)
                door["level"] = l;
            if (!openings.TryGetValue(id, out var rec))
            {
                Out("plan", "the Revit layer gave nothing for this door");
                continue;
            }
            var width = (door["stated_clear"] as JsonObject)?["width"]?.GetValue<double>();
            var place = Place(model, rec, out var whyNot, width);
            evidence[id] = place is { } q
                ? new JsonObject
                {
                    ["centre"] = new JsonArray(q.Centre.X, q.Centre.Y), ["along"] = new JsonArray(q.Along.X, q.Along.Y),
                    ["wall_thickness"] = q.Thickness, ["clear_width"] = width,
                }
                : new JsonObject { ["not_read"] = whyNot };
            if (place is { } p && width is { } w)
                door["plan"] = new JsonObject
                {
                    ["centre"] = new JsonArray(p.Centre.X, p.Centre.Y), ["along"] = new JsonArray(p.Along.X, p.Along.Y),
                    ["clear_width"] = w, ["wall_thickness"] = p.Thickness,
                };
            else
                Out("plan", (place is null ? whyNot! : "its maker's clear width isn't confirmed (no stated_clear is sent), so where a route passes it isn't read")
                            + ": its story's escape routes aren't measured");
            if (Sides(rec, place, sent, plans, unknown, out whyNot) is { } joins)
            {
                door["sides"] = new JsonArray(joins.Select(s => (JsonNode)s).ToArray());
                sides[id] = joins;
                var operation = door["operation"] is JsonValue op && op.TryGetValue<string>(out var o) ? o : null;
                if (place is null)
                    Out("swings_into", "its place in its wall isn't read, so which side it swings into isn't read");
                else if (SwingsInto(model, rec, place, joins, plans, Math.Max(rec.TypeWidth ?? 0, width ?? 0), operation, out var swingWhy) is { } into)
                    door["swings_into"] = into;
                else
                    Out("swings_into", swingWhy!);
            }
            else
                Out("sides", whyNot! + ": its story's escape routes aren't measured");
        }
        // which exit each marked door is: decided once every door's sides are known
        foreach (var door in doors.Select(d => d!.AsObject()))
        {
            var id = door["id"]!.GetValue<string>();
            if (!marks.TryGetValue(id, out var d) || d.ExitWord is null)
                continue;                                    // not an exit (never guessed)
            if (d.ExitKind is not { } kind)
            {
                notes.Add(new(id, "doors.exit_kind", $"{Marks.Exit.Name} is \"{d.ExitWord}\", not one of Gordium's ({ExitKinds.Listed}): read as not an exit"));
                continue;
            }
            door["exit_kind"] = kind;
            if (ExitId(id, kind, sides, marks, openings, joined, out var why) is { } exit)
                door["exit_id"] = exit;
            else
                notes.Add(new(id, "doors.exit_id", why! + ": the door isn't read, so its story's escape routes aren't measured"));
        }
    }

    // ---- which side a door swings into ------------------------------------------------------------------------

    /// <summary>How far a swing arc's centre (its hinge) may stand off the wall's middle beyond half the wall's
    /// thickness, and off a jamb along the wall; how far its middle must stand clear of the wall's face.</summary>
    internal const double HingeOff = 2.0 / 12, JambOff = 6.0 / 12, ClearOfFace = 1.0 / 12;

    /// <summary>The shortest arc read as a leaf's swing: 9 in, whatever the door's width, under the narrowest leaf a
    /// pair is made with (12 in, or 300 mm, which is 11.8 in, drawn to its panel a little less), so a pair's narrow
    /// leaf is always counted and a pair hung opposite ways is seen to swing both ways; a lever's arc is shorter (about
    /// 5 in). An arc counted that isn't a leaf's (a closer's arm, drawn rarely, on the push side) can only add a side
    /// beside the leaf's own, which leaves the swing unstated.</summary>
    internal const double LeastLeaf = 9.0 / 12;

    /// <summary>The side of its wall a door's plan symbol draws its swing on, as the sign along the wall's normal
    /// (<see cref="DoorPlace.Normal"/>): see <see cref="SwingsInto"/>; null with why where the drawing doesn't settle
    /// it. Also what the Revit trial's swing check (SwingCheck) holds against the side the model was built to.</summary>
    internal static int? SwingSide(RevitModel model, OpeningRecord rec, DoorPlace p, double width, out string? why) =>
        SwingRead(model, rec, p, width, out why, out _);

    /// <summary><see cref="SwingSide"/>, and the jambs its counted arcs are hinged at (each the sign along the wall,
    /// <see cref="DoorPlace.Along"/>, of its centre from the door's).</summary>
    internal static int? SwingRead(RevitModel model, OpeningRecord rec, DoorPlace p, double width, out string? why, out HashSet<int> jambs)
    {
        why = null;
        jambs = [];
        if (rec.Swing is not { } drawn)
        {
            why = "its plan symbol wasn't read, so which side it swings into isn't read";
            return null;
        }
        if (drawn.NotRead is { } notRead)
        {
            why = notRead + ", so which side it swings into isn't read";
            return null;
        }
        if (width <= 0)
        {
            why = "its width isn't read, so its swing can't be told from other arcs it draws";
            return null;
        }
        var t = model.InternalToShared;
        var half = p.Thickness / 2;
        var found = new HashSet<int>();
        foreach (var arc in drawn.Arcs)
        {
            var c3 = t.Apply(arc.Centre);
            var m3 = t.Apply(arc.Mid);
            var c = new P2(c3.X, c3.Y) - p.Centre;
            var m = new P2(m3.X, m3.Y) - p.Centre;
            double uC = P2Dot(c, p.Along), nC = P2Dot(c, p.Normal), nM = P2Dot(m, p.Normal);
            var hinge = Math.Abs(nC) <= half + HingeOff && Math.Abs(Math.Abs(uC) - width / 2) <= JambOff;
            var leaf = arc.Radius >= LeastLeaf && arc.Radius <= width + JambOff;
            if (!hinge || !leaf)
                continue;
            if (Math.Abs(nM) <= half + ClearOfFace)
            {
                why = "its plan symbol draws a swing that ends within its wall, so which side it swings into isn't read";
                return null;
            }
            found.Add(Math.Sign(nM));
            jambs.Add(Math.Sign(uC));
        }
        if (found.Count == 0)
        {
            why = drawn.Arcs.Count == 0
                ? "its plan symbol draws no swing at Fine detail (none drawn, or drawn some other way), so which side it swings into isn't read (never read as a door that doesn't swing)"
                : I($"none of the {drawn.Arcs.Count} arcs its plan symbol draws is a leaf's swing from a jamb, so which side it swings into isn't read (never read as a door that doesn't swing)");
            return null;
        }
        if (found.Count > 1)
        {
            why = "its plan symbol draws swings on both sides of its wall (a double-acting door, or a pair hung opposite ways), so which side it swings into isn't read";
            return null;
        }
        return found.Single();
    }

    /// <summary>One door of the Revit trial's swing check: the side its plan symbol's swing is read on (+1 or -1 along
    /// its wall's normal, or null with why) beside the side the model was built to swing it (the build data's
    /// <c>swing_dir</c>, internal, along the same normal).</summary>
    public sealed record SwingCheckRow(string Id, int? Read, int? Built, string? Why);

    /// <summary>The Revit trial's swing check (SwingCheck.cs): each door given a built swing direction (internal plan
    /// vector, by <c>UniqueId</c>), its read side beside its built one. Plain reading code: the same
    /// <see cref="SwingSide"/> the check uses, with the door's type width only (the check's own reading also takes a
    /// stamped clear width): the side alone. SwingCheck's room rows are the whole reading's own (InteriorReader.Read),
    /// held against Revit's room on the built side.</summary>
    public static List<SwingCheckRow> CheckSwings(RevitModel model, IReadOnlyDictionary<string, Xyz> built)
    {
        var rows = new List<SwingCheckRow>();
        foreach (var rec in model.Interior?.Openings ?? [])
        {
            if (!built.TryGetValue(rec.UniqueId, out var dir))
                continue;
            if (Place(model, rec, out var why) is not { } place)
            {
                rows.Add(new(rec.UniqueId, null, null, why));
                continue;
            }
            var d = InteriorReader.Turned(model, dir);
            var b = Math.Sign(P2Dot(new P2(d.X, d.Y), place.Normal));
            rows.Add(new(rec.UniqueId, SwingSide(model, rec, place, rec.TypeWidth ?? 0, out why), b == 0 ? null : b, why));
        }
        return rows;
    }

    /// <summary>One door as the model build reads it back (ModelBuild: flipped until what Revit draws is what the data
    /// says, never by a family's facing or hand convention): the side its plan symbol swings to and the jamb its single
    /// leaf is hinged at (each a sign along the wall's normal and along the wall, from what is drawn; null when not
    /// read: the hinge of a pair, or of a swing not read), and the same for the data (null where it gives none).</summary>
    public sealed record BuildSwing(string Id, int? Side, int? Hinge, int? DataSide, int? DataHinge, string? Why)
    {
        /// <summary>The flips that bring what is read to the data: facing when both sides are known and differ; hand
        /// when both hinges are known and differ. Nothing is flipped on what isn't read.</summary>
        public bool FlipFacing => Side is { } s && DataSide is { } d && s != d;

        public bool FlipHand => Hinge is { } h && DataHinge is { } d && d != 0 && h != d;

        /// <summary>Read as the data says: the side read and equal to the data's, and the hinge too where the data
        /// gives one (a data hinge at the door's centre, 0, is never matched: build review round 1).</summary>
        public bool AsTheData => Side is { } s && s == DataSide && (DataHinge is null || DataHinge != 0 && Hinge == DataHinge);
    }

    /// <summary>Each door the build gives a swing (by <c>UniqueId</c>: its <c>swing_dir</c>, its centre and, for a single
    /// door, its hinge point, all internal), read back from its plan symbol (<see cref="SwingSide"/>, the door's type
    /// width). The data's side is the sign of its swing across the wall, none within 1e-6 of along it; its hinge, the
    /// sign along the wall of the hinge from the data's own centre, 0 within 1/16 in (so a turned model's rounding never
    /// makes a side or a jamb the data didn't give: build review round 3). A door whose place in its wall isn't read has
    /// nothing read.</summary>
    public static List<BuildSwing> ReadBuildSwings(RevitModel model, IReadOnlyDictionary<string, (Xyz Dir, Xyz? Hinge, Xyz Centre)> data)
    {
        var rows = new List<BuildSwing>();
        var t = model.InternalToShared;
        foreach (var rec in model.Interior?.Openings ?? [])
        {
            if (!data.TryGetValue(rec.UniqueId, out var d))
                continue;
            if (Place(model, rec, out var why) is not { } place)
            {
                rows.Add(new(rec.UniqueId, null, null, null, null, why));
                continue;
            }
            var dir = InteriorReader.Turned(model, d.Dir);
            var size = Math.Sqrt(dir.X * dir.X + dir.Y * dir.Y);
            var across = size > 0 ? P2Dot(new P2(dir.X / size, dir.Y / size), place.Normal) : 0;
            var dataSide = Math.Abs(across) <= 1e-6 ? 0 : Math.Sign(across);
            int? dataHinge = null;
            if (d.Hinge is { } h)
            {
                var h3 = t.Apply(h);
                var c3 = t.Apply(d.Centre);
                var off = P2Dot(new P2(h3.X - c3.X, h3.Y - c3.Y), place.Along);
                dataHinge = Math.Abs(off) <= S ? 0 : Math.Sign(off);
            }
            var side = SwingRead(model, rec, place, rec.TypeWidth ?? 0, out why, out var jambs);
            int? hinge = side is not null && jambs.Count == 1 ? jambs.Single() : null;
            // the data's own side or hinge that says neither way (a swing along the wall, a hinge at the door's centre):
            // kept so the door is never matched on it, and said (build review round 1)
            var dataWhy = dataSide == 0 ? "the data's swing runs along its wall, so which side it should swing to isn't told"
                : dataHinge == 0 ? "the data's hinge is at the door's centre along its wall, so which jamb it should hang at isn't told"
                : null;
            if (dataWhy is not null)
                why = why is null ? dataWhy : $"{why}; {dataWhy}";      // both said (build review round 2)
            rows.Add(new(rec.UniqueId, side, hinge, dataSide == 0 ? null : dataSide, dataHinge, why));
        }
        return rows;
    }

    /// <summary>The side a door swings into (BCNYS 1010.1.2.1), read only from the swing its own plan symbol draws
    /// (<see cref="OpeningRecord.Swing"/>), never from its facing or hand (which side a family swings to from them is
    /// the family's own convention): one of <paramref name="joins"/> (a room's id, or <see cref="Outside"/>), or null
    /// with why. A swing arc is one hinged at a jamb (its centre within <see cref="HingeOff"/> of the wall's middle
    /// band and within <see cref="JambOff"/> of half the door's width from its centre along the wall), as long as a
    /// leaf (<see cref="LeastLeaf"/> to the door's width and <see cref="JambOff"/>), and its middle beyond a face of
    /// the wall. Not read: no arc drawn, or none that is a swing (never read as a door that doesn't swing), arcs on
    /// both sides (a double-acting door, or a pair hung opposite ways), an arc whose middle is within the wall, a
    /// stated operation that doesn't swing, or a side whose room isn't found where the arcs are.</summary>
    internal static string? SwingsInto(RevitModel model, OpeningRecord rec, DoorPlace p, string[] joins,
                                       Dictionary<string, InteriorReader.RoomPlan> plans, double width, string? operation, out string? why)
    {
        why = null;
        if (operation is "sliding" or "folding" or "pocket")
        {
            why = $"its operation is {operation}: it has no swing to read";
            return null;
        }
        if (SwingSide(model, rec, p, width, out why) is not { } side)
            return null;
        var reach = p.Thickness / 2 + ClearOfFace;
        P2 Probe(int s) => new(p.Centre.X + s * reach * p.Normal.X, p.Centre.Y + s * reach * p.Normal.Y);
        bool In(string room, P2 q) => plans.TryGetValue(room, out var r) && StrictlyInside(q, r.Outer) && !r.Holes.Any(h => StrictlyInside(q, h));
        string? Room(int s)
        {
            var hits = joins.Where(j => j != Outside && In(j, Probe(s))).ToList();
            if (hits.Count == 1)
                return hits[0];
            // outside: no room of the door's on that side, and its one room on the other
            return hits.Count == 0 && joins.Contains(Outside) && joins.Any(j => j != Outside && In(j, Probe(-s))) ? Outside : null;
        }
        if (Room(side) is { } into && Room(-side) is { } other && other != into)
            return into;
        why = "the rooms on its two sides aren't found one on each side of its wall where it swings, so which side it swings into isn't read";
        return null;
    }

    /// <summary>A door's place in its wall, in shared plan coordinates: its clear opening's centre in the middle of the
    /// wall (half way between the wall's two side faces, at the middle along the wall of the opening it cuts, or, only
    /// when no cut is found, of what is drawn of it strictly between the faces), a unit direction along the wall, the maker's clear width (the stamp-confirmed <c>stated_clear</c>, never
    /// a size Gordium works out), and the wall's thickness between its faces.</summary>
    internal sealed record DoorPlace(P2 Centre, P2 Along, double Thickness, P2 Normal);

    internal static DoorPlace? Place(RevitModel model, OpeningRecord rec, out string? why, double? clearWidth = null,
                                     string what = "door")
    {
        // a door's opening wider than it, or off its middle, may hold a sidelight or a pocket; a window's is only wider
        var hint = what == "door" ? " (a sidelight or a pocket?)" : "";
        why = null;
        if (!rec.HostIsWall || rec.WallSides is not { Count: >= 2 } faces)
        {
            why = "its wall's two side faces couldn't be read as flat (its host isn't a straight wall, or Revit gave no flat side faces)";
            return null;
        }
        if (rec.Along is not { } alongRaw || rec.Placed is not { Count: > 0 } placed)
        {
            why = "its direction along the wall or its drawn geometry couldn't be read";
            return null;
        }
        var t = model.InternalToShared;
        var planes = faces.Select(f => (N: InteriorReader.Turned(model, f.Normal), P: t.Apply(f.Point))).ToList();
        if (planes.Any(p => Math.Abs(p.N.Z) > 1e-6 || Math.Sqrt(p.N.X * p.N.X + p.N.Y * p.N.Y) < 1e-9))
        {
            why = "a side face of its wall isn't vertical";
            return null;
        }
        var n0 = Unit(new P2(planes[0].N.X, planes[0].N.Y));
        var offsets = new List<(int Sign, double C)>();
        foreach (var (n, p) in planes)
        {
            var dot = P2Dot(Unit(new P2(n.X, n.Y)), n0);
            if (Math.Abs(Math.Abs(dot) - 1) > 1e-6)
            {
                why = "its wall's side faces aren't parallel";
                return null;
            }
            offsets.Add((Math.Sign(dot), P2Dot(new P2(p.X, p.Y), n0)));
        }
        var plus = offsets.Where(o => o.Sign > 0).Select(o => o.C).ToList();
        var minus = offsets.Where(o => o.Sign < 0).Select(o => o.C).ToList();
        if (plus.Count == 0 || minus.Count == 0)
        {
            why = "only one side of its wall was read";
            return null;
        }
        if (plus.Max() - plus.Min() > S || minus.Max() - minus.Min() > S)
        {
            why = "a side of its wall isn't one flat face (its faces there are more than 1/16 in apart)";
            return null;
        }
        double a = plus.Average(), b = minus.Average(), thickness = Math.Abs(a - b);
        if (thickness <= S)
        {
            why = "its wall's faces couldn't be told apart";
            return null;
        }
        var along3 = InteriorReader.Turned(model, alongRaw);
        var alongPlan = new P2(along3.X, along3.Y);
        var size = Math.Sqrt(P2Dot(alongPlan, alongPlan));
        if (size < 1e-9 || Math.Abs(P2Dot(alongPlan, n0)) > 1e-6 * size)
        {
            why = "its direction along the wall isn't along its wall's faces";
            return null;
        }
        var along = new P2(-n0.Y, n0.X);
        if (P2Dot(alongPlan, along) < 0)
            along = new P2(-along.X, -along.Y);
        // where the door is along its wall: the opening it cuts in the wall (its rough opening: never the casing on the
        // wall's faces, round 3), else what is drawn of it strictly between the wall's faces (a point on a face may be
        // a casing's back); neither, and it isn't told
        var cutAlong = rec.WallOpening is { Count: > 0 } cut
            ? cut.Select(t.Apply).Select(p => P2Dot(new P2(p.X, p.Y), along)).ToList() : null;
        var inWall = cutAlong ?? placed.Select(t.Apply).Select(p => new P2(p.X, p.Y))
            .Where(p => P2Dot(p, n0) > Math.Min(a, b) + S && P2Dot(p, n0) < Math.Max(a, b) - S).Select(p => P2Dot(p, along)).ToList();
        if (inWall.Count == 0)
        {
            why = "it cuts no opening found in its wall and none of its drawn geometry is between the wall's faces, so where it is along the wall isn't read";
            return null;
        }
        var u = (inWall.Min() + inWall.Max()) / 2;
        // an opening wider than the door itself (its type's width, or its clear width) and a frame (FrameAllowance) holds
        // a sidelight or a pocket even when the unit is centred: where its clear opening is isn't told (round 2)
        var door = Math.Max(rec.TypeWidth ?? 0, clearWidth ?? 0);
        if (door <= 0)
        {
            // nothing to hold the opening against (review round 2: never "more than the window (0 in)")
            why = $"its type's width isn't read, so whether the opening it takes in its wall holds more than the {what} isn't known";
            return null;
        }
        if (inWall.Max() - inWall.Min() > door + FrameAllowance)
        {
            why = I($"the opening it takes in its wall is {(inWall.Max() - inWall.Min()) * 12:0.##} in wide, more than the {what} ({door * 12:0.##} in) and a frame ({FrameAllowance * 12:0} in)") + (what == "door" ? ": a sidelight or a pocket?" : "") + ", so where its clear opening is isn't told";
            return null;
        }
        // the middle of that opening must agree with where the door is placed (round 1)
        if (rec.Location is not { } placedAt)
        {
            why = "its placement point couldn't be read, so its opening's middle can't be checked against it";
            return null;
        }
        var atPoint = t.Apply(placedAt);
        var uPoint = P2Dot(new P2(atPoint.X, atPoint.Y), along);
        if (Math.Abs(u - uPoint) > CentreAgree)
        {
            why = I($"the opening it takes in its wall is centred {Math.Abs(u - uPoint) * 12:0.##} in from where it is placed") +
                  hint + ", so where its clear opening is isn't told";
            return null;
        }
        var c = (a + b) / 2;
        var centre = new P2(u * along.X + c * n0.X, u * along.Y + c * n0.Y);
        return new(centre, along, thickness, n0);
    }

    private static double P2Dot(P2 a, P2 b) => a.X * b.X + a.Y * b.Y;

    private static P2 Unit(P2 v)
    {
        var l = Math.Sqrt(P2Dot(v, v));
        return new(v.X / l, v.Y / l);
    }

    /// <summary>What a door joins: its two rooms (<c>FromRoom</c>, <c>ToRoom</c>, both among the rooms read), or its one
    /// room and outside when Revit gives no room on its other side and no room read is drawn there (1 in beyond the
    /// wall's face). Null, with why, otherwise.</summary>
    internal static string[]? Sides(OpeningRecord rec, DoorPlace? place, HashSet<string> sent,
                                    Dictionary<string, InteriorReader.RoomPlan> plans,
                                    List<(EnclosedArea Area, string Id, List<P2>? Outline)> unknown, out string? why)
    {
        why = null;
        var (from, to) = (rec.FromRoom, rec.ToRoom);
        if (from is null && to is null)
        {
            why = "Revit gives no room on either side of it";
            return null;
        }
        if (from == to)
        {
            why = "Revit gives the same room on both sides of it";
            return null;
        }
        if (new[] { from, to }.OfType<string>().FirstOrDefault(r => !sent.Contains(r)) is { } other)
        {
            why = $"Revit gives a room on one side ({other}) that isn't one of the rooms read (another phase or design option)";
            return null;
        }
        if (from is not null && to is not null)
            return [from, to];
        var room = (from ?? to)!;
        if (place is not { } p)
        {
            why = "Revit gives no room on one side, and without its place in the wall that side can't be checked to be outside";
            return null;
        }
        if (!plans.TryGetValue(room, out var mine))
        {
            why = "Revit gives no room on one side, and its room's floor isn't read, so that side can't be checked to be outside";
            return null;
        }
        var reach = p.Thickness / 2 + 1.0 / 12;
        P2 Probe(int s) => new(p.Centre.X + s * reach * p.Normal.X, p.Centre.Y + s * reach * p.Normal.Y);
        bool In(InteriorReader.RoomPlan r, P2 q) => StrictlyInside(q, r.Outer) && !r.Holes.Any(h => StrictlyInside(q, h));
        var sides = new[] { 1, -1 }.Where(s => In(mine, Probe(s))).ToList();
        if (sides.Count != 1)
        {
            why = "Revit gives no room on one side, and its own room isn't found on just one side of it";
            return null;
        }
        var beyond = Probe(-sides[0]);
        if (plans.Values.FirstOrDefault(r => r.Record.LevelId == mine.Record.LevelId && In(r, beyond)) is { } there)
        {
            why = $"Revit gives no room on one side, but room {there.Record.UniqueId} is drawn there";
            return null;
        }
        // an enclosed area with no Room beyond it is that unknown space, never outside (the Children's Odyssey's
        // classroom toilets and closets, 2026-11-21); one on its level whose outline couldn't be read could be it
        var level = mine.Record.LevelId;
        foreach (var (area, id, outline) in unknown.Where(u => u.Area.LevelId == level || u.Area.LevelId is null))
        {
            if (outline is null && area.Area < SmallestBeyond)
                continue;                                    // a sliver: too small to be what a door opens onto
            if (outline is null)
            {
                why = "Revit gives no room on one side, and an enclosed area with no Room on its level couldn't be outlined, " +
                      "so that side may be it: never read as outside";
                return null;
            }
            if (StrictlyInside(beyond, outline))
                return [room, id];
        }
        return [room, Outside];
    }

    /// <summary>Which exit a door marked as one enters (<c>exit_id</c>): an exterior door's own id (it must open to
    /// outside); for a door into an exit stair enclosure or exit passageway, the Room it enters, the one of the two it
    /// joins whose every door either opens to outside or is marked the same kind of exit (and that is open to no other
    /// room along a separation line), so that every door into one
    /// stair is one exit. A horizontal exit (its compartment beyond isn't a Room of its own), or a door where both or
    /// neither of its rooms qualify, isn't read.</summary>
    internal static string? ExitId(string id, string kind, Dictionary<string, string[]> sides, Dictionary<string, DoorMarks> marks,
                                   Dictionary<string, OpeningRecord> openings, HashSet<string> joined, out string? why)
    {
        why = null;
        if (!sides.TryGetValue(id, out var joins))
        {
            why = "which exit it is isn't read, since what it joins isn't";
            return null;
        }
        if (kind is ExitKinds.Discharge or ExitKinds.OutsideStair)
        {
            if (joins.Contains(Outside))
                return id;
            why = $"it is marked {ExitKinds.Table.WordFor(kind)}, but it opens to no outside (it joins two rooms)";
            return null;
        }
        if (joins.Contains(Outside))
        {
            why = $"it is marked {ExitKinds.Table.WordFor(kind)}, but it opens to outside";
            return null;
        }
        if (kind == ExitKinds.Horizontal)
        {
            why = "which exit a horizontal exit enters (the area beyond its wall) isn't read yet";
            return null;
        }
        bool Only(string room) => !joined.Contains(room) && openings.Values.Where(o => marks.ContainsKey(o.UniqueId) && (o.FromRoom == room || o.ToRoom == room))
            .All(o => (o.FromRoom is null || o.ToRoom is null) || marks[o.UniqueId].ExitKind == kind);
        var enters = joins.Where(Only).ToList();
        if (enters.Count == 1)
            return enters[0];
        why = enters.Count == 0
            ? $"neither room it joins has only doors marked {ExitKinds.Table.WordFor(kind)} (or to outside), so which one it enters isn't known: " +
              "mark every door into the enclosure"
            : $"both rooms it joins have only doors marked {ExitKinds.Table.WordFor(kind)}, so which one it enters isn't known";
        return null;
    }

    // ---- passages ---------------------------------------------------------------------------------------------

    /// <summary>Every place two rooms read on one level meet along a room separation line (each room's boundary has a
    /// straight segment drawn by the same line, the two on one line within 1/16 in, sharing more than 1/16 in of
    /// it), as <c>{rooms, line}</c>; <c>[]</c> when there is none.</summary>
    internal static JsonArray Passages(RevitModel model, InteriorRecords records, HashSet<string> sent)
    {
        var lines = records.SeparationLines!.ToHashSet(StringComparer.Ordinal);
        var t = model.InternalToShared;
        var rooms = records.Rooms.Where(r => sent.Contains(r.UniqueId) && r.Boundary is not null && r.LevelId is not null)
            .OrderBy(r => r.UniqueId, StringComparer.Ordinal).ToList();
        List<(string Line, P2 A, P2 B)> Segments(RoomRecord r) => r.Boundary!.SelectMany(l => l)
            .Where(s => s.IsLine && s.Element is { } e && lines.Contains(e))
            .Select(s => (s.Element!, Plan(t.Apply(s.Start)), Plan(t.Apply(s.End)))).ToList();
        var passages = new JsonArray();
        for (var i = 0; i < rooms.Count; i++)
            for (var j = i + 1; j < rooms.Count; j++)
            {
                if (rooms[i].LevelId != rooms[j].LevelId)
                    continue;
                foreach (var a in Segments(rooms[i]))
                    foreach (var b in Segments(rooms[j]).Where(b => b.Line == a.Line))
                    {
                        var d = b.A - b.B;
                        var len = Math.Sqrt(P2Dot(a.B - a.A, a.B - a.A));
                        if (len <= S || DistanceToLine(b.A, a.A, a.B) > S || DistanceToLine(b.B, a.A, a.B) > S || P2Dot(d, d) <= S * S)
                            continue;
                        var dir = new P2((a.B.X - a.A.X) / len, (a.B.Y - a.A.Y) / len);
                        double ub1 = P2Dot(b.A - a.A, dir), ub2 = P2Dot(b.B - a.A, dir);
                        double lo = Math.Max(0, Math.Min(ub1, ub2)), hi = Math.Min(len, Math.Max(ub1, ub2));
                        if (hi - lo <= S)
                            continue;
                        passages.Add(new JsonObject
                        {
                            ["rooms"] = new JsonArray(rooms[i].UniqueId, rooms[j].UniqueId),
                            ["line"] = new JsonArray(new JsonArray(a.A.X + lo * dir.X, a.A.Y + lo * dir.Y),
                                                     new JsonArray(a.A.X + hi * dir.X, a.A.Y + hi * dir.Y)),
                        });
                    }
            }
        return passages;
    }

    private static P2 Plan(Xyz p) => new(p.X, p.Y);

    private static double DistanceToLine(P2 p, P2 a, P2 b)
    {
        var d = b - a;
        return Math.Abs(P2.Cross(d, p - a)) / Math.Sqrt(P2Dot(d, d));
    }
}
