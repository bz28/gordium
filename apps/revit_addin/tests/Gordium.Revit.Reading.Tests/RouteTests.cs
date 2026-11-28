using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The interior reader's escape-route fields (docs/revit/revit_interior_reading_design.md, section 10; the
/// keys: docs/interior/interior_description_format.md, "The route additions"). A small commercial story drawn as fake
/// Revit records (RouteDrawing.cs) is read, and the real route code reads the description and draws its routes
/// (<c>model_measurement.routes</c>); then each trap, one change at a time, must leave out exactly what it can't read,
/// never send a guess. Each test here pins a decision that keeps a false pass out.</summary>
public sealed class RouteTests
{
    private static JsonObject Room(InteriorReadResult r, string id) => FakeFloor.Part(r, "rooms", id)!;

    private static JsonObject Door(InteriorReadResult r, string id) => FakeFloor.Part(r, "doors", id)!;

    private static string U(string id) => FakeFloor.Uid(id);

    /// <summary>The route code's own reading of the description: the description's and each story's reasons not to
    /// measure, and the route from each point (inches) named: the doors it passes and the exit it reaches.</summary>
    internal static JsonObject Routes(InteriorReadResult read, Dictionary<string, (double X, double Y)>? from = null)
    {
        const string code = """
            import json, sys
            from model_measurement.routes import floor, paths
            with open(sys.argv[1], encoding="utf-8") as f:
                d = json.load(f)
            got = floor.read(d)
            out = {"stops": got.stops, "stories": {k: s.stops for k, s in got.stories.items()}, "routes": {},
                   "crossable": {k: r.crossable for s in got.stories.values() for k, r in s.rooms.items() if r is not None},
                   "not_occupied": {k: r.not_occupied for s in got.stories.values() for k, r in s.rooms.items() if r is not None},
                   "outlines": {k: {"stop": s.outline_stop, "outer": s.outer.area if s.outer is not None else None,
                                    "inner": s.inner.area if s.inner is not None else None} for k, s in got.stories.items()}}
            for k, s in got.stories.items():
                if s.stops:
                    continue
                routes = paths.StoryRoutes(s)
                for name, p in json.loads(sys.argv[2]).items():
                    try:
                        x = routes.route(p)
                        out["routes"][name] = {"doors": list(x.doors), "exit": x.exit_id, "length": x.length}
                    except Exception as e:
                        out["routes"][name] = {"stop": getattr(e, "reason", str(e))}
            print(json.dumps(out))
            """;
        var path = Path.Combine(Path.GetTempPath(), $"gordium_routes_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, read.Interior.ToJsonString());
        try
        {
            var points = new JsonObject((from ?? []).Select(p => KeyValuePair.Create(p.Key, (JsonNode?)new JsonArray(p.Value.X * 12, p.Value.Y * 12))));
            return JsonNode.Parse(Env.RunCode(code, path, points.ToJsonString()))!.AsObject();
        }
        finally
        {
            File.Delete(path);
        }
    }

    private static List<string> StoryStops(JsonObject routes) =>
        routes["stops"]!.AsArray().Concat(routes["stories"]!.AsObject().SelectMany(s => s.Value!.AsArray())).Select(x => x!.GetValue<string>()).ToList();

    // ---- the story, end to end ----------------------------------------------------------------------------------

    [Fact]
    public void A_commercial_story_read_from_its_records_is_measured_by_the_route_code()
    {
        var floor = new FakeFloor();
        var read = InteriorReader.Read(floor.Model());
        // every route field of every part is read: no route note at all
        Assert.Equal([], read.RouteNotes.Where(n => n.Field is "level" or "use" or "lockable" or "pass_through" or "obstructions" or "levels" or "passages"
                                               || n.Field.StartsWith("doors.plan", StringComparison.Ordinal) || n.Field.StartsWith("doors.sides", StringComparison.Ordinal)
                                               || n.Field.StartsWith("doors.exit", StringComparison.Ordinal) || n.Field.StartsWith("doors.level", StringComparison.Ordinal))
                                .Select(n => $"{n.Part} {n.Field}: {n.Why}"));
        Assert.Equal([FakeFloor.Level], read.Interior["levels"]!.AsArray().Select(l => l!["id"]!.GetValue<string>()));
        Assert.Equal("corridor", Room(read, "C")["use"]!.GetValue<string>());
        Assert.True(Room(read, "L")["pass_through"]!.GetValue<bool>());
        Assert.Single(Room(read, "B")["holes"]!.AsArray());                     // the column
        Assert.Empty(Room(read, "A")["holes"]!.AsArray());
        var desk = Assert.Single(Room(read, "A")["obstructions"]!.AsArray())!;   // its top and bottom: one footprint
        Assert.Equal("furniture", desk["kind"]!.GetValue<string>());
        Assert.False(desk["fixed"]!.GetValue<bool>());
        Assert.Empty(Room(read, "C")["obstructions"]!.AsArray());              // the wall beside it isn't in it
        var dA = Door(read, "dA");
        Assert.Equal([10.0, 9.75], dA["plan"]!["centre"]!.AsArray().Select(x => x!.GetValue<double>()));
        Assert.Equal(0.5, dA["plan"]!["wall_thickness"]!.GetValue<double>(), 12);
        Assert.Equal(FakeFloor.Clear, dA["plan"]!["clear_width"]!.GetValue<double>());
        Assert.Equal([U("A"), U("C")], dA["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Null(dA["exit_kind"]);
        Assert.Equal([U("L"), RouteReader.Outside], Door(read, "dE")["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Equal("exterior_at_discharge", Door(read, "dE")["exit_kind"]!.GetValue<string>());
        Assert.Equal(U("dE"), Door(read, "dE")["exit_id"]!.GetValue<string>());
        Assert.Equal("exit_enclosure", Door(read, "dS")["exit_kind"]!.GetValue<string>());
        Assert.Equal(U("S"), Door(read, "dS")["exit_id"]!.GetValue<string>());   // the stair it enters
        var passage = Assert.Single(read.Interior["passages"]!.AsArray())!;
        Assert.Equal([U("C"), U("L")], passage["rooms"]!.AsArray().Select(x => x!.GetValue<string>()).Order());

        // the route code reads it all and draws the routes: from office A out through its door, along the corridor,
        // into the stair (its nearest exit); from office B along the corridor, across the passage into the lobby and
        // out of the lobby's door; from the lobby out of its own door
        var routes = Routes(read, new() { ["office A"] = (15, 2), ["office B"] = (35, 2), ["lobby"] = (30, 24) });
        Assert.Equal([], StoryStops(routes));
        var a = routes["routes"]!["office A"]!;
        Assert.Null(a["stop"]);
        Assert.Equal([U("dA"), U("dS")], a["doors"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Equal(U("S"), a["exit"]!.GetValue<string>());
        Assert.Equal([U("dB"), U("dE")], routes["routes"]!["office B"]!["doors"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Equal(U("dE"), routes["routes"]!["office B"]!["exit"]!.GetValue<string>());
        Assert.Equal([U("dE")], routes["routes"]!["lobby"]!["doors"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.True(routes["crossable"]![U("C")]!.GetValue<bool>());
        Assert.Equal(
        [
            "levels: 1 (Level 1)",
            "rooms: 5; with a level 5, a floor 5, holes 5 (1 in all), obstructions 5 (1 footprints); use 5, can be locked 5, pass through 5, marked not occupied 0",
            "doors: 5; with a level 5, a place in its wall 5 (its wall read 5), sides 5 (2 to outside), exits 2 (2 exits by id)",
            "passages: 1",
            "unknown spaces: 0",
            "story outlines: not sent (the notes say why)",
        ], RouteReader.Summary(read));
        Assert.False(routes["crossable"]![U("A")]!.GetValue<bool>());
    }

    [Fact]
    public void Every_level_is_sent_in_all_levels_one_with_nothing_drawn_on_it_too()
    {
        // an open parking story with no room, door or enclosed area: not a story the routes measure (levels), but one
        // that may be the first above grade plane, so the story places (story_place.py) need it
        var floor = new FakeFloor();
        floor.Levels!.Add(new LevelRecord("level-parking", "Parking", floor.Fake.Place(0, 0, -10).Z));
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal([FakeFloor.Level], read.Interior["levels"]!.AsArray().Select(l => l!["id"]!.GetValue<string>()));
        var all = read.Interior["all_levels"]!.AsArray();
        Assert.Equal([FakeFloor.Level, "level-parking"], all.Select(l => l!["id"]!.GetValue<string>()));
        Assert.Equal("Parking", all[1]!["name"]!.GetValue<string>());
        Assert.Equal(-10.0, all[1]!["elevation"]!.GetValue<double>(), 9);
    }

    [Fact]
    public void The_story_under_turned_and_moved_shared_coordinates_reads_the_same()
    {
        var turn = Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0));
        var floor = new FakeFloor(turn);
        var read = InteriorReader.Read(floor.Model());
        var dA = Door(read, "dA");
        Assert.Equal(0.5, dA["plan"]!["wall_thickness"]!.GetValue<double>(), 9);
        Assert.Equal([U("A"), U("C")], dA["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Single(read.Interior["passages"]!.AsArray());
        Assert.Single(Room(read, "A")["obstructions"]!.AsArray());
        Assert.Equal(0.0, read.Interior["levels"]![0]!["elevation"]!.GetValue<double>(), 9);   // shared: the level at 0
        Assert.Equal([], StoryStops(Routes(read)));
    }

    // ---- a room's marks: the architect's word alone, unset is left out -----------------------------------------

    [Fact]
    public void A_rooms_use_lock_and_pass_through_are_sent_only_as_marked()
    {
        var floor = new FakeFloor();
        floor.SetMark("C", Marks.Use, null);                                  // unset
        floor.SetMark("L", Marks.Use, new(true, Text: "Hallway"));             // not one of Gordium's words
        floor.SetMark("A", Marks.CanBeLocked, null);
        floor.SetMark("B", Marks.PassThrough, new(false, 0));                  // never set (Revit reads 0)
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Room(read, "C")["use"]);                                    // never its name ("Corridor")
        Assert.Contains("is not set", FakeFloor.Note(read, "C", "use"));
        Assert.Null(Room(read, "L")["use"]);
        Assert.Contains("\"Hallway\", not one of Gordium's", FakeFloor.Note(read, "L", "use"));
        Assert.Null(Room(read, "A")["lockable"]);
        Assert.Null(Room(read, "B")["pass_through"]);
        // the route code then never crosses the corridor: office B has no route (never a route through it)
        var routes = Routes(read, new() { ["office B"] = (35, 2) });
        Assert.False(routes["crossable"]![U("C")]!.GetValue<bool>());
        Assert.NotNull(routes["routes"]!["office B"]!["stop"]);
    }

    /// <summary>The architect's "nobody occupies this room" (Gordium: Not occupied, route note decision 1b): sent as
    /// marked, Yes as true and No as false; never set (Revit reads 0) is left out, so the room is occupied and
    /// measured, never left out on a blank. The route code reads it: NFPA's figures leave that room's points out.</summary>
    [Fact]
    public void A_rooms_not_occupied_mark_is_sent_only_as_marked()
    {
        var floor = new FakeFloor();
        floor.SetMark("A", Marks.NotOccupied, new(true, 1));
        floor.SetMark("B", Marks.NotOccupied, new(true, 0));
        floor.SetMark("C", Marks.NotOccupied, new(false, 0));                  // never set (Revit reads 0)
        var read = InteriorReader.Read(floor.Model());
        Assert.True(Room(read, "A")["not_occupied"]!.GetValue<bool>());
        Assert.False(Room(read, "B")["not_occupied"]!.GetValue<bool>());
        Assert.Null(Room(read, "C")["not_occupied"]);
        Assert.Null(Room(read, "L")["not_occupied"]);                         // no mark at all: left out
        Assert.Contains("marked not occupied 1", string.Join(" | ", RouteReader.Summary(read)), StringComparison.Ordinal);
        var json = Routes(read)["not_occupied"]!;
        Assert.True(json[U("A")]!.GetValue<bool>());
        Assert.False(json[U("B")]!.GetValue<bool>());
        Assert.False(json[U("C")]!.GetValue<bool>());
    }

    [Fact]
    public void The_use_words_and_exit_words_reach_exactly_the_route_codes_words()
    {
        var json = JsonNode.Parse(Env.RunCode(
            "import json; from model_measurement.routes import floor; print(json.dumps({'uses': list(floor.USES), 'exits': list(floor.EXIT_KINDS)}))"))!;
        Assert.Equal(json["uses"]!.AsArray().Select(x => x!.GetValue<string>()), RoomUses.Words.Select(w => RoomUses.Table.Of(w)!));
        Assert.Equal(json["exits"]!.AsArray().Select(x => x!.GetValue<string>()), ExitKinds.Words.Select(w => ExitKinds.Table.Of(w)!));
        Assert.Equal("day_care", RoomUses.Table.Of(" day CARE "));
        Assert.Null(RoomUses.Table.Of("Day-care"));                            // near is not a word
        Assert.Null(RoomUses.Table.Of("Hall"));
    }

    // ---- exits: marked, never guessed; one stair is one exit ---------------------------------------------------

    [Fact]
    public void A_door_with_no_exit_mark_is_not_an_exit_and_an_unknown_word_is_not_one_either()
    {
        var floor = new FakeFloor();
        floor.SetMark("dE", Marks.Exit, null);
        floor.SetMark("dS", Marks.Exit, new(true, Text: "Stair"));
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dE")["exit_kind"]);
        Assert.Null(Door(read, "dS")["exit_kind"]);
        Assert.Contains("\"Stair\", not one of Gordium's", FakeFloor.Note(read, "dS", "doors.exit_kind"));
        // no exit marked: the route code says so, never a route
        Assert.Contains(StoryStops(Routes(read)), s => s.Contains("exit", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void Every_door_into_one_stair_enclosure_is_one_exit()
    {
        var floor = new FakeFloor();
        floor.Door("dS3", "L", "S", horizontal: false, u: 20, n0: 10, n1: 10.5, exit: "Exit stair enclosure");
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal(U("S"), Door(read, "dS")["exit_id"]!.GetValue<string>());
        Assert.Equal(U("S"), Door(read, "dS3")["exit_id"]!.GetValue<string>());
        Assert.Equal([], StoryStops(Routes(read)));
    }

    [Fact]
    public void A_stair_door_whose_enclosure_cant_be_told_is_not_read()
    {
        // a closet door into the stair room, unmarked: the stair room no longer has only exit doors, so which room the
        // marked door enters is not known: no exit id, and the route code reads the door as not read (needs review)
        var floor = new FakeFloor();
        floor.Door("dX", "S", "L", horizontal: false, u: 20, n0: 10, n1: 10.5);
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal("exit_enclosure", Door(read, "dS")["exit_kind"]!.GetValue<string>());
        Assert.Null(Door(read, "dS")["exit_id"]);
        Assert.Contains("neither room it joins", FakeFloor.Note(read, "dS", "doors.exit_id"));
        Assert.Contains(StoryStops(Routes(read)), s => s.Contains("which exit the exit door leads into", StringComparison.Ordinal));

        // marked as a door to outside but between two rooms; a horizontal exit: neither is read as an exit
        floor = new FakeFloor();
        floor.SetMark("dA", Marks.Exit, new(true, Text: "Exterior door at discharge"));
        floor.SetMark("dB", Marks.Exit, new(true, Text: "Horizontal exit"));
        read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dA")["exit_id"]);
        Assert.Contains("opens to no outside", FakeFloor.Note(read, "dA", "doors.exit_id"));
        Assert.Null(Door(read, "dB")["exit_id"]);
        Assert.Contains("horizontal exit", FakeFloor.Note(read, "dB", "doors.exit_id"));
    }

    // ---- a door's place and sides ------------------------------------------------------------------------------

    [Fact]
    public void A_doors_place_is_sent_only_from_its_confirmed_clear_width_and_two_flat_parallel_wall_faces()
    {
        var floor = new FakeFloor();
        floor.Marked[floor.MarkedIndex("dA")] = floor.Marked[floor.MarkedIndex("dA")] with
        {
            Type = new Dictionary<Guid, MarkValue>(floor.Marked[floor.MarkedIndex("dA")].Type) { [Marks.ClearConfirmed.Guid] = new(false) },
        };
        var i = floor.OpeningIndex("dB");
        floor.Openings[i] = floor.Openings[i] with { WallSides = [floor.Openings[i].WallSides![0], floor.Openings[i].WallSides![0] with { Normal = new(0.6, 0.8, 0) }] };
        var j = floor.OpeningIndex("dS");
        floor.Openings[j] = floor.Openings[j] with { WallSides = null };      // a curved wall, a curtain wall
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dA")["plan"]);                                  // never its type's width
        Assert.Contains("clear width isn't confirmed", FakeFloor.Note(read, "dA", "doors.plan"));
        Assert.NotNull(Door(read, "dA")["sides"]);                              // what it joins is read all the same
        Assert.Equal(0.5, read.Evidence["route_doors"]![U("dA")]!["wall_thickness"]!.GetValue<double>(), 12);   // its wall, for the trial
        Assert.Null(Door(read, "dB")["plan"]);
        Assert.Contains("aren't parallel", FakeFloor.Note(read, "dB", "doors.plan"));
        Assert.Null(Door(read, "dS")["plan"]);
        Assert.Contains(StoryStops(Routes(read)), s => s.Contains("plan", StringComparison.Ordinal));
    }

    [Fact]
    public void A_door_whose_drawn_middle_isnt_where_it_is_placed_has_no_place()
    {
        // review round 1: dA's opening cut 9 in off where the door is placed: its clear opening isn't placed on a guess
        var floor = new FakeFloor();
        var i = floor.OpeningIndex("dA");
        List<Xyz> Cut(double x0, double x1) => [floor.Fake.Place(x0, 9.5, 0), floor.Fake.Place(x1, 10, 7)];
        floor.Openings[i] = floor.Openings[i] with { WallOpening = Cut(10.75 - 1.625, 10.75 + 1.625) };
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dA")["plan"]);
        Assert.Contains("centred 9 in from where it is placed", FakeFloor.Note(read, "dA", "doors.plan"));
        // round 2: a door-and-sidelight unit centred on itself (1.5 ft of sidelight each side, cut in the wall with it):
        // wider than the door and a frame, so its clear opening isn't placed either
        floor = new FakeFloor();
        floor.Openings[i] = floor.Openings[i] with { WallOpening = Cut(10 - 1.625 - 1.5, 10 + 1.625 + 1.5) };
        read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dA")["plan"]);
        Assert.Contains("a sidelight or a pocket", FakeFloor.Note(read, "dA", "doors.plan"));
        // round 3: a 36-in door with 4-in casing on both faces of its wall: the casing isn't the opening, the door is placed
        floor = new FakeFloor();
        var casing = floor.Prism([(10 - 1.625 - 0.333, 9.4), (10 + 1.625 + 0.333, 9.4), (10 + 1.625 + 0.333, 9.5), (10 - 1.625 - 0.333, 9.5)], 0, 7)
            .Concat(floor.Prism([(10 - 1.625 - 0.333, 10), (10 + 1.625 + 0.333, 10), (10 + 1.625 + 0.333, 10.1), (10 - 1.625 - 0.333, 10.1)], 0, 7));
        floor.Openings[i] = floor.Openings[i] with { Placed = [.. floor.Openings[i].Placed!, .. casing.SelectMany(f => f.Points)] };
        Assert.Equal([10.0, 9.75], Door(InteriorReader.Read(floor.Model()), "dA")["plan"]!["centre"]!.AsArray().Select(x => x!.GetValue<double>()));
        // no cut found: what is drawn strictly between the faces alone; a frame flush with them and casing on them give
        // nothing there, so its place isn't read
        floor.Openings[i] = floor.Openings[i] with { WallOpening = null };
        Assert.Contains("between the wall's faces", FakeFloor.Note(InteriorReader.Read(floor.Model()), "dA", "doors.plan"));
    }

    [Fact]
    public void A_door_opens_to_outside_only_when_no_room_is_drawn_beyond_it()
    {
        // Revit gives no room beyond dA (as on a door whose far room is in another phase), but the corridor is there
        var floor = new FakeFloor();
        var i = floor.OpeningIndex("dA");
        floor.Openings[i] = floor.Openings[i] with { ToRoom = null };
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dA")["sides"]);
        Assert.Contains($"room {U("C")} is drawn there", FakeFloor.Note(read, "dA", "doors.sides"));

        // a room on one side that isn't one of the rooms read; the same room on both sides; no room at all
        floor = new FakeFloor();
        floor.Openings[i] = floor.Openings[i] with { ToRoom = "uid-elsewhere" };
        var j = floor.OpeningIndex("dB");
        floor.Openings[j] = floor.Openings[j] with { ToRoom = U("B") };
        var k = floor.OpeningIndex("dS2");
        floor.Openings[k] = floor.Openings[k] with { FromRoom = null };
        read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dA")["sides"]);
        Assert.Null(Door(read, "dB")["sides"]);
        Assert.Null(Door(read, "dS2")["sides"]);
        Assert.Contains("no room on either side", FakeFloor.Note(read, "dS2", "doors.sides"));
    }

    [Fact]
    public void A_door_onto_an_enclosed_area_with_no_room_names_it_never_outside()
    {
        // the Children's Odyssey (2026-11-21): 19 doors read "to outside", many of them into classroom toilets and
        // closets with no Room. An enclosed area beyond the lobby's door: the door joins the lobby and that space
        var floor = new FakeFloor();
        (double X, double Y)[] beyondE = [(20, 26.5), (30, 26.5), (30, 32), (20, 32)];
        floor.Areas.Add(new EnclosedArea("Level 1", 55, false, floor.Fake.Place(25, 29, 0), FakeFloor.Level,
                                         beyondE.Select(p => floor.Fake.Place(p.X, p.Y, 0)).ToList()));
        var read = InteriorReader.Read(floor.Model());
        var space = Assert.Single(read.Interior["unknown_spaces"]!.AsArray())!;
        var id = space["id"]!.GetValue<string>();
        Assert.Equal(4, space["outline"]!.AsArray().Count);
        Assert.Equal([U("L"), id], Door(read, "dE")["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Null(Door(read, "dE")["exit_id"]);                               // an exterior door's mark, but no outside
        Assert.Equal([U("S"), RouteReader.Outside], Door(read, "dS2")["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Contains(StoryStops(Routes(read)), s => s.Contains("enclosed space", StringComparison.Ordinal));

        // its outline not read: no door on that level with no room beyond it is called outside
        floor.Areas[^1] = floor.Areas[^1] with { Outline = null };
        read = InteriorReader.Read(floor.Model());
        Assert.Null(Door(read, "dE")["sides"]);
        Assert.Null(Door(read, "dS2")["sides"]);
        Assert.Contains("couldn't be outlined", FakeFloor.Note(read, "dS2", "doors.sides"));
        Assert.Equal([U("A"), U("C")], Door(read, "dA")["sides"]!.AsArray().Select(x => x!.GetValue<string>()));   // two rooms: as before

        // a 0 sq ft sliver Revit can't outline or locate (two walls face to face, the Children's Odyssey's two): too
        // small to be beyond any door, so the exterior doors open to outside and the exit is read (review: 2026-11-21,
        // every exterior door had lost its sides to the slivers)
        floor.Areas[^1] = new EnclosedArea("Level 1", 0, false, null, FakeFloor.Level);
        read = InteriorReader.Read(floor.Model());
        Assert.Equal([U("L"), RouteReader.Outside], Door(read, "dE")["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        Assert.Equal(U("dE"), Door(read, "dE")["exit_id"]!.GetValue<string>());
        Assert.Equal([U("S"), RouteReader.Outside], Door(read, "dS2")["sides"]!.AsArray().Select(x => x!.GetValue<string>()));
        // one just large enough to be beyond a door, not outlined: still never outside
        floor.Areas[^1] = new EnclosedArea("Level 1", RouteReader.SmallestBeyond, false, null, FakeFloor.Level);
        Assert.Null(Door(InteriorReader.Read(floor.Model()), "dE")["sides"]);
    }

    // ---- what stands in a room ---------------------------------------------------------------------------------

    [Fact]
    public void Anything_else_lower_than_the_headroom_over_a_rooms_floor_leaves_its_obstructions_not_read()
    {
        // a beam 6 ft up over the corridor: not an obstruction kind, so the corridor isn't read (never ignored)
        var floor = new FakeFloor();
        floor.AddOver("C", new NearbyElement("beam", "OST_StructuralFraming", "Beam", Faces: floor.Prism([(15, 12), (16, 12), (16, 14), (15, 14)], 6, 6.5)));
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Room(read, "C")["obstructions"]);
        Assert.Contains("Beam", FakeFloor.Note(read, "C", "obstructions"));
        Assert.Contains(StoryStops(Routes(read)), s => s.Contains("what stands on its floor", StringComparison.Ordinal));

        // the same beam at 7 ft (above the 80 in headroom) stands in no one's way; a light fixture at 8 ft neither
        floor = new FakeFloor();
        floor.AddOver("C", new NearbyElement("beam", "OST_StructuralFraming", "Beam", Faces: floor.Prism([(15, 12), (16, 12), (16, 14), (15, 14)], 7, 7.5)));
        floor.AddOver("C", new NearbyElement("light", "OST_LightingFixtures", "Pendant", Faces: floor.Prism([(20, 12), (21, 12), (21, 13), (20, 13)], 8, 8.5)));
        Assert.Empty(Room(InteriorReader.Read(floor.Model()), "C")["obstructions"]!.AsArray());

        // a generic model on the floor that Revit's solid test didn't find; casework whose geometry failed
        floor = new FakeFloor();
        floor.AddOver("C", new NearbyElement("gm", "OST_GenericModel", "Planter", Faces: floor.Prism([(15, 12), (16, 12), (16, 14), (15, 14)], 0, 3)));
        Assert.Null(Room(InteriorReader.Read(floor.Model()), "C")["obstructions"]);
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("cw", "OST_Casework", "Counter", GeometryFailed: true));
        Assert.Contains("couldn't be cut out", FakeFloor.Note(InteriorReader.Read(floor.Model()), "A", "obstructions"));

        // furniture Revit's solid test found standing in the room but that wasn't read with its geometry
        floor = new FakeFloor();
        var i = floor.RoomIndex("A");
        floor.Rooms[i] = floor.Rooms[i] with { Inside = [new NearbyElement("chair", "OST_Furniture", "Chair")] };
        Assert.Contains("Chair", FakeFloor.Note(InteriorReader.Read(floor.Model()), "A", "obstructions"));
    }

    [Fact]
    public void A_piece_crossing_the_floor_or_drawn_in_2D_alone_is_never_dropped()
    {
        // review round 1, P0: a wall standing in the room from 1 ft under its floor to 10 ft up has no flat face in the
        // band: its footprint still stands in the way
        var floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("wall-in", "OST_Walls", "Partition", Faces: floor.Prism([(8, 5), (14, 5), (14, 6), (8, 6)], -1, 10)));
        var i = floor.RoomIndex("A");
        floor.Rooms[i] = floor.Rooms[i] with { Inside = [new NearbyElement("wall-in", "OST_Walls", "Partition")] };
        var obstructions = Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray();
        Assert.Contains(obstructions, o => o!["outline"]!.AsArray().Any(p => p![0]!.GetValue<double>() == 14 && p[1]!.GetValue<double>() == 6));
        // round 3: a standing wall with a door's threshold (a small flat face) in its band: what Revit cuts out of it is
        // its whole body in the band, the threshold with it; the footprint is all of it, never the threshold's strip
        floor = new FakeFloor();
        var body = floor.Prism([(8, 5), (14, 5), (14, 6), (8, 6)], InteriorReader.Sixteenth, RouteReader.Headroom);
        var sill = floor.Face(new(0, 0, 1), [(10.0, 5.0, 0.1), (13.0, 5.0, 0.1), (13.0, 6.0, 0.1), (10.0, 6.0, 0.1)]);
        floor.Rooms[i] = floor.Rooms[i] with
        {
            Inside = [new NearbyElement("wall-in", "OST_Walls", "Partition")],
            Over = [.. floor.Rooms[i].Over!, new NearbyElement("wall-in", "OST_Walls", "Partition", Faces: body) { Banded = [sill, .. body] }],
        };
        var footprints = Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray()
            .Select(o => o!["outline"]!.AsArray().Select(p => new P2(p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList()).ToList();
        Assert.Contains(footprints, o => Math.Abs(PlanGeometry.Area(o) - 6) < 1e-9);       // the wall's whole 6 by 1 ft
        // tall casework from under the floor past the headroom, the same
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("tall", "OST_Casework", "Tall cabinet", Faces: floor.Prism([(10, 0), (12, 0), (12, 2), (10, 2)], -0.5, 8)));
        Assert.Equal(2, Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray().Count);   // the desk and the cabinet

        // round 2, P0: an L of tall casework (0 to 8 ft, past the headroom) keeps its exact footprint: its notch, (12, 9),
        // is never inside it (a hull would fill it, and a bigger obstruction can shorten the common path)
        floor = new FakeFloor();
        List<(double X, double Y)> l = [(10, 5), (14, 5), (14, 6), (11, 6), (11, 9.5), (10, 9.5)];
        floor.AddOver("A", new NearbyElement("l-case", "OST_Casework", "L counter", Faces: floor.Prism(l, 0, 8)));
        var ls = Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray()
            .Select(o => o!["outline"]!.AsArray().Select(p => new P2(p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList()).ToList();
        Assert.DoesNotContain(ls, o => PlanGeometry.OverlapArea(o, [new(11.9, 8.9), new(12.1, 8.9), new(12.1, 9.1), new(11.9, 9.1)]) is > 1e-9);
        Assert.Contains(ls, o => o.Count == 6);

        // round 3: a shelf wholly above the band (7 ft 2 in to 8 ft): Revit's intersection gives nothing, no obstruction
        floor = new FakeFloor();
        var before = Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray().Count;
        floor.AddOver("A", new NearbyElement("shelf", "OST_Casework", "High shelf", Faces: floor.Prism([(10, 5), (14, 5), (14, 6), (10, 6)], 7.17, 8)));
        Assert.Equal(before, Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray().Count);
        // a wall standing in the room from the floor below (its base 10 ft down) to the ceiling: its whole body counts
        floor = new FakeFloor();
        floor.Rooms[i] = floor.Rooms[i] with { Inside = [new NearbyElement("wall-low", "OST_Walls", "Partition")] };
        floor.AddOver("A", new NearbyElement("wall-low", "OST_Walls", "Partition", Faces: floor.Prism([(8, 5), (14, 5), (14, 6), (8, 6)], -10, 9)));
        Assert.Contains(Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray()
            .Select(o => o!["outline"]!.AsArray().Select(p => new P2(p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList()),
            o => Math.Abs(PlanGeometry.Area(o) - 6) < 1e-9);
        // the intersection refused (a mesh, Revit threw): the room's obstructions aren't read, and why is said
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("mesh", "OST_Furniture", "Sofa (mesh)") { Banded = [], BandFailed = true });
        var refused = InteriorReader.Read(floor.Model());
        Assert.Null(Room(refused, "A")["obstructions"]);
        Assert.Contains("couldn't be cut out", FakeFloor.Note(refused, "A", "obstructions"));
        // round 4: a piece of open surfaces (no volume: imported, a DirectShape from an open Brep) reaching the band:
        // Revit can't cut it, so it is never dropped as nothing in the band; the room's obstructions aren't read
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("shell", "OST_Furniture", "Imported sofa") { Banded = [], OpenShells = 1 });
        var shell = InteriorReader.Read(floor.Model());
        Assert.Null(Room(shell, "A")["obstructions"]);
        Assert.Contains("open surfaces", FakeFloor.Note(shell, "A", "obstructions"));
        // round 5: a generic model with no faces read but the band's cut saying open surfaces, or a failed cut (a null
        // instance, a kind not read): never passed over as nothing drawn
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("gm-shell", "OST_GenericModel", "Imported mass", Faces: []) { Banded = [], OpenShells = 1 });
        Assert.Contains("open surfaces", FakeFloor.Note(InteriorReader.Read(floor.Model()), "A", "obstructions"));
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("gm-null", "OST_GenericModel", "Generic", Faces: []) { Banded = [], BandFailed = true });
        Assert.Contains("couldn't be cut out", FakeFloor.Note(InteriorReader.Read(floor.Model()), "A", "obstructions"));

        // review round 1, P0: furniture drawn in 2D alone (no 3D faces) with its box over the floor: where it stands
        // isn't read, never "nothing drawn"; round 2: one whose box is beside the room changes nothing
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("desk-2d-beside", "OST_Furniture", "Desk (2D)", Faces: [],
                                             Box: new RevitBox(floor.Fake.Place(30, 2, 0), floor.Fake.Place(32, 4, 3))));
        Assert.NotNull(Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]);
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("desk-2d", "OST_Furniture", "Desk (2D)", Faces: [],
                                             Box: new RevitBox(floor.Fake.Place(5, 6, 0), floor.Fake.Place(7, 8, 3))));
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Room(read, "A")["obstructions"]);
        Assert.Contains("no 3D faces", FakeFloor.Note(read, "A", "obstructions"));
        // a line or a base point of any other category is still nothing drawn
        floor = new FakeFloor();
        floor.AddOver("A", new NearbyElement("line", "OST_Lines", "Line", Faces: []));
        Assert.NotNull(Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]);
    }

    [Fact]
    public void A_low_hung_obstruction_and_a_curved_one_count_by_their_whole_footprint()
    {
        var floor = new FakeFloor();
        // a wall cabinet from 4.5 to 7 ft (under the headroom): counts; a round table (a curved face): its hull
        floor.AddOver("A", new NearbyElement("cab", "OST_Casework", "Wall cabinet", Faces: floor.Prism([(10, 0), (14, 0), (14, 1), (10, 1)], 4.5, 7)));
        var round = Enumerable.Range(0, 12).Select(k => (X: 15 + Math.Cos(k * Math.PI / 6), Y: 5 + Math.Sin(k * Math.PI / 6))).ToList();
        floor.AddOver("A", new NearbyElement("table", "OST_Furniture", "Round table",
            Faces: [new SurfaceRecord(false, new Xyz(0, 0, 0), [], round.SelectMany(p => new[] { floor.Fake.Place(p.X, p.Y, 0), floor.Fake.Place(p.X, p.Y, 2.4) }).ToList())]));
        var obstructions = Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]!.AsArray();
        Assert.Equal(3, obstructions.Count);
        Assert.Contains(obstructions, o => o!["kind"]!.GetValue<string>() == "casework" && o["fixed"]!.GetValue<bool>());
        Assert.Contains(obstructions, o => o!["outline"]!.AsArray().Count == 12);
    }

    // ---- a room's holes, the passages, the levels -------------------------------------------------------------

    [Fact]
    public void A_column_is_a_hole_only_in_a_room_that_isnt_a_sleeping_room()
    {
        var floor = new FakeFloor();
        floor.SetMark("B", Marks.SleepingRoom, new(true, 1));
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Room(read, "B")["floor"]);                                 // the house's floor area would count the column
        Assert.Null(Room(read, "B")["holes"]);
        Assert.Contains("2 boundary loops", FakeFloor.Note(read, "B", "floor"));

        // an inner loop that crosses the outline is no hole
        floor = new FakeFloor();
        var i = floor.RoomIndex("B");
        floor.Rooms[i] = floor.Rooms[i] with
        {
            Boundary = [floor.Rooms[i].Boundary![0], [floor.Seg(39, 4, 41, 4, "col-1"), floor.Seg(41, 4, 41, 5, "col-1"), floor.Seg(41, 5, 39, 5, "col-1"), floor.Seg(39, 5, 39, 4, "col-1")]],
        };
        read = InteriorReader.Read(floor.Model());
        Assert.Null(Room(read, "B")["floor"]);
        Assert.Contains("isn't wholly inside", FakeFloor.Note(read, "B", "floor"));

        // the outline found by area, whatever order Revit gives the loops in
        floor = new FakeFloor();
        floor.Rooms[i] = floor.Rooms[i] with { Boundary = [floor.Rooms[i].Boundary![1], floor.Rooms[i].Boundary![0]] };
        read = InteriorReader.Read(floor.Model());
        Assert.Equal(4, Room(read, "B")["floor"]!.AsArray().Count);
        Assert.Single(Room(read, "B")["holes"]!.AsArray());
        Assert.Equal(1.0, PlanGeometry.Area(Room(read, "B")["holes"]![0]!.AsArray().Select(p => new P2(p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList()), 9);
    }

    [Fact]
    public void A_room_not_marked_is_sent_with_its_holes_and_a_wall_standing_in_a_room_is_an_obstruction()
    {
        // the Children's Odyssey model (2026-11-21): KITCHEN (10) round a chase, its Sleeping room not set; a wall
        // standing in ADMINISTRATION (18). Not marked, the house's measures read no room at all, so the holes are safe
        var floor = new FakeFloor();
        floor.SetMark("B", Marks.SleepingRoom, null);
        floor.AddOver("A", new NearbyElement("wall-in", "OST_Walls", "LS Existing 12\"", Faces: floor.Prism([(8, 5), (14, 5), (14, 6), (8, 6)], 0, 10)));
        var i = floor.RoomIndex("A");
        floor.Rooms[i] = floor.Rooms[i] with { Inside = [new NearbyElement("wall-in", "OST_Walls", "LS Existing 12\"")] };
        var read = InteriorReader.Read(floor.Model());
        Assert.Single(Room(read, "B")["holes"]!.AsArray());
        Assert.NotNull(Room(read, "A")["floor"]);
        var wall = Assert.Single(Room(read, "A")["obstructions"]!.AsArray(), o => o!["outline"]!.AsArray().Count == 4
                                 && o["outline"]!.AsArray().Any(p => p![0]!.GetValue<double>() == 14));
        Assert.Equal("fixture", wall!["kind"]!.GetValue<string>());
        Assert.True(wall["fixed"]!.GetValue<bool>());

        // the same wall in a sleeping room: its floor area would count it, so no floor (the house's reading as before)
        floor.SetMark("A", Marks.SleepingRoom, new(true, 1));
        Assert.Null(Room(InteriorReader.Read(floor.Model()), "A")["floor"]);

        // anything else standing in a room (a column that doesn't bound it) still leaves its floor out
        floor = new FakeFloor();
        floor.Rooms[i] = floor.Rooms[i] with { Inside = [new NearbyElement("col-x", "OST_Columns", "Column")] };
        Assert.Null(Room(InteriorReader.Read(floor.Model()), "A")["floor"]);

        // a wall the solid test found standing in it, but whose geometry wasn't read: its obstructions aren't read
        floor = new FakeFloor();
        floor.Rooms[i] = floor.Rooms[i] with { Inside = [new NearbyElement("wall-in", "OST_Walls", "Partition")] };
        Assert.Null(Room(InteriorReader.Read(floor.Model()), "A")["obstructions"]);
    }

    // ---- the story's outlines (decision 8) ------------------------------------------------------------------------

    /// <summary>Revit's gross building area of the fake story as the Revit layer gives it: the walls' outer faces,
    /// each side with the wall bounding it (the south side in two pieces, one wall split in line).</summary>
    private static GrossArea Gross(FakeFloor floor, double northWidth = 0.5)
    {
        BoundarySegmentRecord S(double x0, double y0, double x1, double y1, string? by) =>
            new(floor.Fake.Place(x0, y0, 0), floor.Fake.Place(x1, y1, 0), true, by);
        return new GrossArea([[S(-0.5, -0.5, 20, -0.5, "wall-s1"), S(20, -0.5, 40.5, -0.5, "wall-s2"), S(40.5, -0.5, 40.5, 26.5, "wall-e"),
                               S(40.5, 26.5, -0.5, 26.5, "wall-n"), S(-0.5, 26.5, -0.5, -0.5, "wall-w")]],
                             new Dictionary<string, double> { ["wall-s1"] = 0.5, ["wall-s2"] = 0.5, ["wall-e"] = 0.5, ["wall-n"] = northWidth, ["wall-w"] = 0.5 });
    }

    private static string? OutlineNote(InteriorReadResult r) => r.RouteNotes.SingleOrDefault(n => n.Field == "story_outlines")?.Why;

    [Fact]
    public void A_storys_outlines_are_revits_gross_area_and_its_walls_inside_faces()
    {
        var floor = new FakeFloor();
        floor.GrossAreas = new() { [FakeFloor.Level] = Gross(floor) };
        var read = InteriorReader.Read(floor.Model());
        var outline = Assert.Single(read.Interior["story_outlines"]!.AsArray())!;
        Assert.Equal(FakeFloor.Level, outline["level"]!.GetValue<string>());
        P2 At(JsonNode p) => new(p[0]!.GetValue<double>(), p[1]!.GetValue<double>());
        var outer = outline["outer"]!.AsArray().Select(p => At(p!)).ToList();
        Assert.Equal(4, outer.Count);                                      // the split south side taken as one
        Assert.Equal(41.0 * 27, PlanGeometry.Area(outer), 9);
        Assert.Equal(40.0 * 26, PlanGeometry.Area(outline["inner"]!.AsArray().Select(p => At(p!)).ToList()), 9);
        var routes = Routes(read);
        Assert.Null(routes["outlines"]![FakeFloor.Level]!["stop"]);
        Assert.Equal(41.0 * 27 * 144, routes["outlines"]![FakeFloor.Level]!["outer"]!.GetValue<double>(), 6);   // sq in

        // a thicker north wall: its inside face moved in by its own thickness
        floor.GrossAreas = new() { [FakeFloor.Level] = Gross(floor, northWidth: 1) };
        outline = InteriorReader.Read(floor.Model()).Interior["story_outlines"]![0]!;
        Assert.Equal(40.0 * 25.5, PlanGeometry.Area(outline["inner"]!.AsArray().Select(p => At(p!)).ToList()), 9);
    }

    [Fact]
    public void An_outline_a_wall_lies_beyond_or_a_non_room_bounding_exterior_wall_is_never_sent()
    {
        // #281's review (a false pass): a brick veneer set Room Bounding = No stands outside the ring Room's boundary, so
        // the outline stops at the backup wall, short by the veneer at each end, and close exits read as placed apart
        // under BCNYS 1007.1.1. Every wall on the level is read with its footprint; one beyond the outline, or one in the
        // exterior walls' band that isn't room-bounding, or one that can't be read: no outlines, the wall named
        var floor = new FakeFloor();
        WallFootprint W(string id, string? mark, bool bounding, params (double X, double Y)[] at) =>
            new(id, mark, bounding, at.Select(p => floor.Fake.Place(p.X, p.Y, 0)).ToList());
        var inside = W("wall-in", "P1", false, (10, 5), (10.3, 5), (10.3, 15), (10, 15));        // a partition, not bounding: fine
        var west = W("wall-w", "EW1", true, (-0.5, -0.5), (0, -0.5), (0, 26.5), (-0.5, 26.5));    // the west wall itself: fine
        var g = Gross(floor);
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [inside, west] } };
        Assert.Null(OutlineNote(InteriorReader.Read(floor.Model())));
        var veneer = W("wall-v", "V1", false, (-0.85, -0.85), (-0.5, -0.85), (-0.5, 26.85), (-0.85, 26.85));
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [inside, west, veneer] } };
        Assert.Contains("lies outside the building's outline", OutlineNote(InteriorReader.Read(floor.Model())));
        Assert.Contains("Mark V1", OutlineNote(InteriorReader.Read(floor.Model())));
        // a wall running a hair past the outline where it steps (the Children's Odyssey's W2, 0.14 in past W74's face): fine
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [W("wall-s", "W2", true, (5, -0.5), (25, -0.5), (25, -0.512), (5, -0.512))] } };
        Assert.Null(OutlineNote(InteriorReader.Read(floor.Model())));
        // a thin cladding (3/8 in) not set Room Bounding, drawn tight to the west wall: within the half inch beyond the
        // outline, but its inner face is a whole wall past the inside face: refused by the band (confirming review)
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [W("wall-c", "C1", false, (-0.53, -0.5), (-0.5, -0.5), (-0.5, 26.5), (-0.53, 26.5))] } };
        Assert.Contains("isn't set Room Bounding", OutlineNote(InteriorReader.Read(floor.Model())));
        // a partition that isn't room-bounding whose studs run half an inch into the exterior wall's lining: fine
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [W("wall-t", "P2", false, (10, -0.04), (10.3, -0.04), (10.3, 5), (10, 5))] } };
        Assert.Null(OutlineNote(InteriorReader.Read(floor.Model())));
        // a garden wall that isn't room-bounding standing 10 ft off: not the building's, fine
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [W("wall-gd", null, false, (55, 0), (70, 0), (70, 0.5), (55, 0.5))] } };
        Assert.Null(OutlineNote(InteriorReader.Read(floor.Model())));
        // a bounding wall beyond it too (a garden wall on the level): never guessed which is the building's face
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [W("wall-g", null, true, (45, 0), (60, 0), (60, 0.5), (45, 0.5))] } };
        Assert.Contains("lies outside the building's outline", OutlineNote(InteriorReader.Read(floor.Model())));
        // an exterior wall (in the band between the outer and inner outlines) that isn't room-bounding
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [W("wall-e2", "E2", false, (40.1, 2), (40.4, 2), (40.4, 8), (40.1, 8))] } };
        Assert.Contains("isn't set Room Bounding", OutlineNote(InteriorReader.Read(floor.Model())));
        // a wall whose footprint couldn't be read
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Walls = [new WallFootprint("wall-x", null, true, [])] } };
        Assert.Contains("couldn't be read", OutlineNote(InteriorReader.Read(floor.Model())));
    }

    [Fact]
    public void A_short_side_no_element_bounds_is_a_walls_end_kept_where_it_is()
    {
        // the Children's Odyssey's ring (2026-11-21): steps of 0.006 to 0.64 ft where two walls in line stand apart, or
        // a jamb ends at an opening, came back with no element: the wall's end, kept; the walls either side moved in
        var t = Transform3.Identity;
        BoundarySegmentRecord S(double x0, double y0, double x1, double y1, string? by) => new(new(x0, y0, 0), new(x1, y1, 0), true, by);
        var widths = new Dictionary<string, double> { ["s"] = 0.5, ["e"] = 0.5, ["n1"] = 0.5, ["n2"] = 0.5, ["w"] = 0.5 };
        GrossArea Ring(double step) => new([[S(-0.5, -0.5, 40.5, -0.5, "s"), S(40.5, -0.5, 40.5, 26.5, "e"), S(40.5, 26.5, 20, 26.5, "n1"),
                                             S(20, 26.5, 20, 26.5 + step, null), S(20, 26.5 + step, -0.5, 26.5 + step, "n2"), S(-0.5, 26.5 + step, -0.5, -0.5, "w")]], widths);
        var got = StoryOutlines.Of(Ring(0.1), t);
        Assert.Null(got.Why);
        Assert.Equal(40 * 26 + 20 * 0.1, PlanGeometry.Area(got.Inner!), 9);
        Assert.Equal(41 * 27 + 20.5 * 0.1, PlanGeometry.Area(got.Outer!), 9);
        // a side with no element longer than any wall is thick: an opening across, never guessed
        Assert.Contains("isn't bounded by a wall", StoryOutlines.Of(Ring(StoryOutlines.WallEnd + 0.5), t).Why);
    }

    [Fact]
    public void Without_a_closed_gross_area_bounded_by_walls_no_outline_is_sent_and_why_is_said()
    {
        var floor = new FakeFloor();
        Assert.Contains("weren't read", OutlineNote(InteriorReader.Read(floor.Model())));                 // not read at all
        floor.GrossAreas = [];
        Assert.Contains("wasn't read", OutlineNote(InteriorReader.Read(floor.Model())));                  // not for this level
        floor.GrossAreas = new() { [FakeFloor.Level] = new GrossArea(null, new Dictionary<string, double>(), "Revit closed no gross area on the level") };
        Assert.Contains("closed no gross area", OutlineNote(InteriorReader.Read(floor.Model())));
        var g = Gross(floor);
        // a side bounded by an area boundary line, not a wall: its thickness unknown
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Loops = [[.. g.Loops![0].Take(4), g.Loops[0][4] with { Element = "area-line" }]] } };
        Assert.Contains("isn't bounded by a wall", OutlineNote(InteriorReader.Read(floor.Model())));
        // two walls of different thickness along one side
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { WallWidths = new Dictionary<string, double>(g.WallWidths) { ["wall-s2"] = 1 } } };
        Assert.Contains("different thickness", OutlineNote(InteriorReader.Read(floor.Model())));
        // a second building: the ring Room meets two outlines
        BoundarySegmentRecord S(double x0, double y0, double x1, double y1) => new(floor.Fake.Place(x0, y0, 0), floor.Fake.Place(x1, y1, 0), true, "wall-c");
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Loops = [g.Loops![0], [S(50, 5, 50, 8), S(50, 8, 53, 8), S(53, 8, 53, 5), S(53, 5, 50, 5)]] } };
        Assert.Contains("2 separate pieces", OutlineNote(InteriorReader.Read(floor.Model())));
        // a courtyard: an enclosed area with no Room on the level, whose area the outline would count
        floor.GrossAreas = new() { [FakeFloor.Level] = g };
        floor.Areas.Add(new EnclosedArea("Level 1", 30, false, floor.Fake.Place(25, 29, 0), FakeFloor.Level));
        Assert.Contains("courtyard", OutlineNote(InteriorReader.Read(floor.Model())));
        floor.Areas.RemoveAt(floor.Areas.Count - 1);
        // a curved side
        floor.GrossAreas = new() { [FakeFloor.Level] = g with { Loops = [[.. g.Loops![0].Take(4), g.Loops[0][4] with { IsLine = false }]] } };
        var read = InteriorReader.Read(floor.Model());
        Assert.Contains("curved", OutlineNote(read));
        Assert.Null(read.Interior["story_outlines"]);
    }

    [Fact]
    public void Passages_and_levels_not_read_are_left_out_never_empty()
    {
        var floor = new FakeFloor { SeparationLines = null, Levels = null };
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(read.Interior["passages"]);                                // never [] (that says the rooms meet nowhere)
        Assert.Null(read.Interior["levels"]);
        Assert.Null(Room(read, "C")["level"]);
        Assert.Null(Door(read, "dA")["level"]);
        var stops = StoryStops(Routes(read));
        Assert.Contains(stops, s => s.Contains("levels", StringComparison.Ordinal));

        // no separation line in the model: the corridor and lobby meet along nothing Gordium reads as one, so no passage
        floor = new FakeFloor { SeparationLines = [] };
        Assert.Empty(InteriorReader.Read(floor.Model()).Interior["passages"]!.AsArray());
    }

    [Fact]
    public void A_houses_description_measures_as_before()
    {
        // the houses of the step (InteriorTests) carry no levels: no route field is guessed for them
        var house = FakeHouse.Draw("1_ranch_compliant");
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["levels"]);
        Assert.All(read.Interior["rooms"]!.AsArray(), r => Assert.Null(r!["level"]));
        Assert.Equal([], InteriorTests.Problems(house, read));
        // review round 1: the route notes are kept apart, so a house's "values left out" stays its own
        string[] route = ["use", "lockable", "pass_through", "level", "holes", "obstructions", "levels", "passages", "story_outlines"];
        Assert.DoesNotContain(read.Notes, n => route.Contains(n.Field) || n.Field.StartsWith("doors.plan", StringComparison.Ordinal)
                                               || n.Field.StartsWith("doors.sides", StringComparison.Ordinal) || n.Field.StartsWith("doors.level", StringComparison.Ordinal)
                                               || n.Field.StartsWith("doors.exit_", StringComparison.Ordinal));
        Assert.NotEmpty(read.RouteNotes);
    }

    // ---- the marks in a project and in the list ----------------------------------------------------------------

    [Fact]
    public void A_project_with_gordiums_use_on_project_information_gets_it_on_rooms_too()
    {
        var bound = Marks.All.Select(m => new BoundParameter(m.Name, m.Guid, m.Kind, m.Kind.ToString(), m.Binding == MarkBinding.Instance,
                                                              m == Marks.Use ? [Marks.ProjectInformation] : m.Categories)).ToList();
        var step = MarkSetup.Plan(bound).Single(s => s.Mark == Marks.Use);
        Assert.Equal(MarkSetupAction.AddCategories, step.Action);
        Assert.Equal([Marks.ProjectInformation, Marks.Rooms], step.Categories);
    }

    [Fact]
    public void The_marking_list_shows_the_route_marks_a_name_only_ever_suggests_and_blank_needs_nothing()
    {
        var floor = new FakeFloor();
        floor.SetMark("C", Marks.Use, null);
        floor.SetMark("A", Marks.Use, new(true, Text: "Office"));
        floor.SetMark("dE", Marks.Exit, null);
        var list = MarkingList.Build(floor.Model());
        MarkCell Cell(string id, MarkDefinition m) => list.Rows.Single(r => r.Id == U(id)).Cells.Single(c => c.Mark == m);
        Assert.Equal(MarkState.LeftBlank, Cell("C", Marks.Use).State);
        Assert.StartsWith("suggested: Corridor", Cell("C", Marks.Use).Suggestion);
        Assert.False(Cell("C", Marks.Use).NeedsMarking);                       // a house never needs it
        Assert.Equal(MarkState.NotUnderstood, Cell("A", Marks.Use).State);      // a word Gordium doesn't read: to mark
        Assert.True(Cell("A", Marks.Use).NeedsMarking);
        Assert.Equal(MarkState.LeftBlank, Cell("dE", Marks.Exit).State);
        Assert.Contains("not an exit", Cell("dE", Marks.Exit).Words);
        Assert.Equal(MarkState.Given, Cell("dS", Marks.Exit).State);
        Assert.Contains(list.Summary, l => l.StartsWith("Escape routes: 3 of 5 rooms", StringComparison.Ordinal) && l.Contains("1 door is marked"));
        // the suggestion is never what is sent
        Assert.Null(Room(InteriorReader.Read(floor.Model()), "C")["use"]);
    }
}
