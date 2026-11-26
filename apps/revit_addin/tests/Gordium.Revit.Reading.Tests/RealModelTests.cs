using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>What stopped a real model being read (Autodesk's "Pacific Continental Residence Sample.rvt", Read inside on
/// 2026-11-20; docs/revit/revit_interior_reading_design.md, section 2): a window's grille muntins (Generic Models
/// nested in the window) counted as stairs nobody drew, and one enclosed area with no Room anywhere (a roof level's
/// parapets, a chase) stopped every room in the house being read. Each pinned on the hand-worked ranch drawn as fake
/// Revit records, both ways, and through the real measuring code and checker.</summary>
public sealed class RealModelTests
{
    private static readonly MarkValue Yes = new(true, 1);
    private const string Level0 = "level-0";

    // ---- a window's grille is not a stair -----------------------------------------------------------------------

    private static RevitBox Box(double x0, double y0, double z0, double x1, double y1, double z1) => new(new(x0, y0, z0), new(x1, y1, z1));

    private static readonly RevitBox WindowBox = Box(10, 0, 3, 13, 0.5, 8);

    private static StairCandidate Muntin(RevitBox? box, params NestHost[] chain) =>
        new("muntin", "OST_GenericModel", "Muntin Pattern_1x2", "a loadable family", Box: box, NestedIn: chain);

    public static TheoryData<string, bool> Grilles() => new()
    {
        { "inside its window", false },
        { "inside its window, two deep", false },
        { "inside its door", false },
        { "touching its window's box", false },
        { "sticking out of its window", true },
        { "not nested", true },
        { "nested in a generic model", true },
        { "no box", true },
        { "its window has no box", true },
        { "an in-place family's", true },
    };

    [Theory]
    [MemberData(nameof(Grilles))]
    public void A_generic_model_nested_inside_a_window_or_door_is_no_stair_anything_else_still_is(string how, bool blocks)
    {
        var window = new NestHost("w", "OST_Windows", WindowBox);
        var inside = Box(10.5, 0.1, 4, 12.5, 0.4, 7);
        var candidate = how switch
        {
            "inside its window" => Muntin(inside, window),
            "inside its window, two deep" => Muntin(inside, new NestHost("sash", "OST_GenericModel", Box(10.2, 0, 3.2, 12.8, 0.5, 7.8)), window),
            "inside its door" => Muntin(inside, new NestHost("d", "OST_Doors", WindowBox)),
            "touching its window's box" => Muntin(Box(10, 0, 3, 13, 0.5, 8 + InteriorReader.Sixteenth / 2), window),
            "sticking out of its window" => Muntin(Box(10.5, 0.1, 4, 12.5, 0.4, 8.5), window),
            "not nested" => Muntin(inside),
            "nested in a generic model" => Muntin(inside, new NestHost("gm", "OST_GenericModel", WindowBox)),
            "no box" => Muntin(null, window),
            "its window has no box" => Muntin(inside, window with { Box = null }),
            _ => Muntin(inside, window) with { Kind = "an in-place family", BuiltInCategory = "OST_StairsRailing" },
        };
        Assert.Equal(!blocks, StairReader.InsideWindowOrDoor(candidate));
        var house = FakeHouse.Draw("3_tall_riser");
        house.StairCandidates.Add(candidate);
        var read = InteriorReader.Read(house.Model());
        if (blocks)
        {
            Assert.Null(read.Interior["stairs"]);
            Assert.Contains(read.StairsNotRead, w => w.Contains("can't tell every stair is read"));
        }
        else
        {
            Assert.NotNull(read.Interior["stairs"]);
            Assert.Empty(read.StairsNotRead);
            Assert.Empty(StairReader.Blockers(house.Model()));
        }
    }

    [Fact]
    public void A_grille_inside_a_window_turned_off_the_axes_is_judged_in_the_window_boxs_own_turn()
    {
        // a box with its own transform: both turned the same way, the grille still sits inside
        var turn = Transform3.TurnThenMove(Math.PI / 6, new Xyz(100, 50, 0));
        var window = new NestHost("w", "OST_Windows", WindowBox with { Transform = turn });
        Assert.True(StairReader.InsideWindowOrDoor(Muntin(Box(10.5, 0.1, 4, 12.5, 0.4, 7) with { Transform = turn }, window)));
        // the grille's box unturned, far from the turned window: not inside it
        Assert.False(StairReader.InsideWindowOrDoor(Muntin(Box(10.5, 0.1, 4, 12.5, 0.4, 7), window)));
    }

    // ---- the architect's "Not a stair" (Q2: the sample's 19 standalone Generic Models) -----------------------------

    private static Dictionary<Guid, MarkValue> NotAStair(MarkValue v) => new() { [Marks.NotAStair.Guid] = v };

    /// <summary>House 2 with the sample's kind of standalone Generic Models beside it (not nested in anything): two
    /// corbels and a wall niche, each marked <paramref name="mark"/> (null: the mark not on the element at all).</summary>
    private static FakeHouse WithGenericModels(MarkValue? mark)
    {
        var house = FakeHouse.Draw("2_two_story_small_window");
        foreach (var (id, name) in new[] { ("gm1", "Corbel"), ("gm2", "Corbel"), ("gm3", "Wall niche") })
            house.StairCandidates.Add(new(id, "OST_GenericModel", name, "a loadable family", Box: Box(50, 50, 0, 51, 51, 1),
                                          InstanceMarks: mark is { } m ? NotAStair(m) : null));
        return house;
    }

    public static TheoryData<string, bool> NotAStairMarks() => new()
    {
        { "Yes", true }, { "No", false }, { "never set", false }, { "not on the element", false },
    };

    [Theory]
    [MemberData(nameof(NotAStairMarks))]
    public void A_generic_model_marked_not_a_stair_is_cleared_and_listed_unset_or_no_still_blocks(string how, bool cleared)
    {
        var house = WithGenericModels(how switch
        {
            "Yes" => Yes, "No" => new MarkValue(true, 0), "never set" => new MarkValue(false, 0), _ => null,
        });
        var read = InteriorReader.Read(house.Model());
        var list = MarkingList.Build(house.Model());
        if (cleared)
        {
            Assert.NotNull(read.Interior["stairs"]);
            Assert.Empty(read.StairsNotRead);
            Assert.Empty(StairReader.Blockers(house.Model()));
            Assert.DoesNotContain(GuardReader.Blockers(house.Model(), null), w => w.Contains("GenericModel"));   // nor a guard's
            // every exemption traceable: one line per type, in the Read inside log and in the marking list
            string[] lines = ["Not a stair (architect): GenericModel \"Corbel\" x 2, ids in the log",
                              "Not a stair (architect): GenericModel \"Wall niche\" x 1, ids in the log"];
            Assert.Equal(lines, read.NotAStair);
            Assert.Equal(lines, list.NotAStair);
            Assert.Contains(lines[0], MarkingList.Text(list));
            Assert.Equal([], InteriorTests.Problems(house, read));                                   // measured as worked by hand
        }
        else
        {
            Assert.Null(read.Interior["stairs"]);
            Assert.Contains(read.StairsNotRead, w => w.Contains("3 GenericModel elements are each a loadable family"));
            Assert.Empty(read.NotAStair);
            Assert.Empty(list.NotAStair);
        }
        Assert.Empty(read.NotAStairConflicts);
    }

    [Fact]
    public void One_generic_model_left_unmarked_still_stops_the_stairs()
    {
        var house = WithGenericModels(Yes);
        house.StairCandidates[2] = house.StairCandidates[2] with { InstanceMarks = null };     // the niche not marked
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["stairs"]);
        Assert.Contains(read.StairsNotRead, w => w.Contains("GenericModel \"Wall niche\" is a loadable family"));
        Assert.Equal(["Not a stair (architect): GenericModel \"Corbel\" x 2, ids in the log"], read.NotAStair);
    }

    [Fact]
    public void Not_a_stair_never_clears_a_revit_stair_or_railing_it_is_a_conflict_listed_first()
    {
        var house = FakeHouse.Draw("2_two_story_small_window");
        house.Stairs[0] = house.Stairs[0] with { InstanceMarks = NotAStair(Yes) };
        var r = house.Railings!.Count - 1;
        house.Railings[r] = house.Railings[r] with { InstanceMarks = NotAStair(Yes) };
        var read = InteriorReader.Read(house.Model());
        Assert.Equal(2, read.NotAStairConflicts.Count);
        Assert.Contains("is marked Gordium: Not a stair Yes, but the mark can't clear a Revit stair or railing", read.NotAStairConflicts[0]);
        Assert.StartsWith("Stair ", read.NotAStairConflicts[0]);
        Assert.StartsWith("Railing ", read.NotAStairConflicts[1]);
        Assert.Empty(read.NotAStair);
        Assert.NotNull(read.Interior["stairs"]);                                                   // read as what it is
        Assert.Equal([], InteriorTests.Problems(house, read));
        var list = MarkingList.Build(house.Model());
        Assert.Equal(read.NotAStairConflicts, list.NotAStairConflicts);
        Assert.StartsWith("Conflict: Stair ", MarkingList.Text(list));                             // listed first
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);

        // a multistory stair marked so: still a stair the reader doesn't walk, and a conflict
        house = FakeHouse.Draw("2_two_story_small_window");
        house.StairCandidates.Add(new("ms", "OST_MultistoryStairs", "Tower stair", "a multistory stair", InstanceMarks: NotAStair(Yes)));
        read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["stairs"]);
        Assert.Contains(read.StairsNotRead, w => w.Contains("\"Tower stair\" is a multistory stair"));
        Assert.Contains("(a multistory stair) is marked Gordium: Not a stair Yes", read.NotAStairConflicts.Single());
        Assert.Empty(read.NotAStair);
    }

    // ---- an enclosed area with no Room ----------------------------------------------------------------------------

    /// <summary>The ranch with its rooms and areas on level 0 given that level's id, plus the level itself.</summary>
    private static FakeHouse Ranch(bool? noRooms = null)
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        for (var i = 0; i < house.Rooms.Count; i++)
            house.Rooms[i] = house.Rooms[i] with { LevelId = Level0 };
        for (var i = 0; i < house.Areas.Count; i++)
            house.Areas[i] = house.Areas[i] with { LevelId = Level0 };
        house.Marked.Add(new MarkedElement
        {
            UniqueId = Level0, BuiltInCategory = Marks.Levels, Name = "Level 0",
            Instance = noRooms is { } v ? new Dictionary<Guid, MarkValue> { [Marks.NoRoomsOnLevel.Guid] = new(true, v ? 1 : 0) }
                : new Dictionary<Guid, MarkValue>(),
        });
        return house;
    }

    private static EnclosedArea Unroomed(double area = 331.4, double x = 30, double y = 3, string? level = Level0) =>
        new("Level 0", area, false, new Xyz(x, y, 0), level);

    private static JsonNode Measured(InteriorReadResult read)
    {
        var path = Path.Combine(Path.GetTempPath(), $"gordium_unknown_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, read.Interior.ToJsonString());
        try
        {
            return JsonNode.Parse(Env.RunCode(
                "import json, sys; from model_measurement.interior import measure; from rule_format.parts import rows, rule_result; " +
                "from rule_format.rulebook import load, REPO; " +
                "m = measure(json.load(open(sys.argv[1]))); " +
                "rule = next(r for r in load(REPO / 'regulations/jurisdictions/new_york/new_york_state/5_building_code_rules/drafted/general.yaml')['rules'] " +
                "if r['id'] == 'general.r319_1_sleeping_room_escape_opening_operable'); " +
                "got = rows(rule, m['parts'], {}, {'use': set()}); " +
                "print(json.dumps({'rooms': [[p['id'], p.get('maybe')] for p in m['parts']['sleeping_room'] or []], 'problems': m['problems'], " +
                "'rows': [[(r['within'] or {}).get('id'), r['outcome'], r['reason']] for r in got], 'result': rule_result(got)}))", path))!;
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void An_enclosed_area_revit_gives_no_point_inside_stays_a_space_whose_use_isnt_known()
    {
        // the Children's Odyssey model (2026-11-20): Revit threw "Could not obtain valid UV point" for a sliver between
        // overlapping walls; such an area is kept, lies in no Room, and keeps every sleeping-room rule needing review
        var house = Ranch();
        house.Areas.Add(new EnclosedArea("Level 0", 0.4, false, null, Level0));
        var read = InteriorReader.Read(house.Model());
        Assert.Equal(3, read.Interior["rooms"]!.AsArray().Count);
        var space = Assert.Single(read.Interior["unknown_spaces"]!.AsArray())!;
        Assert.Equal("enclosed-area:level-0:no-point:0.4sf", space["id"]!.GetValue<string>());
        Assert.StartsWith("An enclosed area on Level 0 has no Room (0.4 sq ft; Revit couldn't give a point inside it",
                          space["name"]!.GetValue<string>());
        // the same id at every read
        Assert.Equal(space["id"]!.GetValue<string>(), InteriorReader.Read(house.Model()).Interior["unknown_spaces"]![0]!["id"]!.GetValue<string>());
        // it has no place to put a Room in: the architect is told to fix the walls, never "place a Room in it"
        var alone = Assert.Single(InteriorReader.AreaBlockers(house.Model()));
        Assert.Contains("find and fix the overlapping or doubled walls on Level 0", alone);
        Assert.DoesNotContain("place a Room in it", alone);
        Assert.Contains("until the overlapping or doubled walls closing it off are fixed (Revit couldn't locate it)",
                        Assert.Single(MarkingList.Build(house.Model()).Summary, l => l.StartsWith("1 enclosed area has no Room")));

        // with one that has a place: the log line says which have places, and what to do about the one without
        house.Areas.Add(Unroomed());
        var both = Assert.Single(InteriorReader.AreaBlockers(house.Model()));
        Assert.Contains("each listed in the log, with its place where Revit gives one", both);
        Assert.Contains("place a Room in each of the 1 with a place", both);
        Assert.Contains("the 1 Revit couldn't locate (no point inside, often a sliver between overlapping walls): " +
                        "find and fix the overlapping or doubled walls on Level 0", both);
        Assert.DoesNotContain("each listed with its place in the log", both);
        var mixed = Assert.Single(MarkingList.Build(house.Model()).Summary, l => l.StartsWith("2 enclosed areas have no Room"));
        Assert.Contains("until a Room is placed in each Revit locates, and the overlapping or doubled walls closing off the 1 " +
                        "it couldn't are fixed", mixed);
        Assert.DoesNotContain("until a Room is placed in each,", mixed);

        // several, none with a place: never told to place a Room in any of them
        var slivers = Ranch();
        slivers.Areas.Add(new EnclosedArea("Level 0", 0.4, false, null, Level0));
        slivers.Areas.Add(new EnclosedArea("Level 0", 0.6, false, null, Level0));
        var none = Assert.Single(InteriorReader.AreaBlockers(slivers.Model()));
        Assert.StartsWith("2 enclosed areas on Level 0 have no Room (0.4 to 0.6 sq ft; each listed in the log; Revit couldn't " +
                          "locate any of them", none);
        Assert.Contains("find and fix the overlapping or doubled walls on Level 0 that close them off", none);
        Assert.DoesNotContain("place a Room", none);
        // the marking list's summary beside it says the same
        var line = Assert.Single(MarkingList.Build(slivers.Model()).Summary, l => l.StartsWith("2 enclosed areas have no Room"));
        Assert.Contains("until the overlapping or doubled walls closing them off are fixed (Revit couldn't locate any of them)", line);
        Assert.DoesNotContain("until a Room is placed in each", line);
    }

    [Fact]
    public void An_enclosed_area_with_no_room_is_sent_as_a_space_whose_use_isnt_known_and_the_rooms_drawn_are_read()
    {
        var house = Ranch();
        house.Areas.Add(Unroomed());
        var read = InteriorReader.Read(house.Model());
        Assert.Empty(read.RoomsNotRead);
        Assert.Equal(3, read.Interior["rooms"]!.AsArray().Count);                // every room drawn is still read
        var space = Assert.Single(read.Interior["unknown_spaces"]!.AsArray())!;
        Assert.StartsWith("enclosed-area:level-0:", space["id"]!.GetValue<string>());
        Assert.StartsWith("An enclosed area on Level 0 has no Room (331.4 sq ft", space["name"]!.GetValue<string>());
        Assert.StartsWith("An enclosed area on Level 0 has no Room (331.4 sq ft", Assert.Single(read.UnknownSpaces));
        // the same id at every read of the same model
        Assert.Equal(space["id"]!.GetValue<string>(), InteriorReader.Read(house.Model()).Interior["unknown_spaces"]![0]!["id"]!.GetValue<string>());

        // through the real measuring code and rule: a sleeping room that may not be one, "every sleeping room has an
        // escape opening" needs review on it (never "fails": it may be a closet), the drawn bedrooms each their own row
        var got = Measured(read);
        Assert.Empty(got["problems"]!.AsArray());
        var rooms = got["rooms"]!.AsArray().Select(r => (Id: r![0]!.GetValue<string>(), Maybe: r[1]?.GetValue<string>())).ToList();
        Assert.Equal([FakeHouse.Uid("bed1"), FakeHouse.Uid("bed2"), space["id"]!.GetValue<string>()], rooms.Select(r => r.Id));
        Assert.Null(rooms[0].Maybe);
        Assert.Contains("its use isn't known, so it may be a sleeping room", rooms[2].Maybe);
        var rows = got["rows"]!.AsArray().Select(r => (Within: r![0]?.GetValue<string>(), Outcome: r[1]!.GetValue<string>())).ToList();
        Assert.Equal("needs_review", rows.Single(r => r.Within == space["id"]!.GetValue<string>()).Outcome);
        Assert.Contains(rows, r => r.Within == FakeHouse.Uid("bed1"));
        Assert.NotEqual("pass", got["result"]!.GetValue<string>());

        // the marking list: the area listed (not as stopping the rooms), the headline not all marked, the level's row to mark
        var list = MarkingList.Build(house.Model());
        Assert.Empty(list.RoomBlockers);
        Assert.StartsWith("An enclosed area on Level 0 has no Room (331.4 sq ft", Assert.Single(list.UnknownAreas));
        Assert.Contains(Marks.NoRoomsOnLevel.Name + " Yes", list.UnknownAreas[0]);
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
        Assert.Contains(list.Summary, s => s.StartsWith("1 enclosed area has no Room (listed above): the rooms drawn are read", StringComparison.Ordinal));
        var level = list.Rows.Single(r => r.Kind == MarkedKind.Level);
        Assert.Equal("Level 0 (1 enclosed area with no Room)", level.Label);
        Assert.True(level.NeedsMarking);
        Assert.Contains("An enclosed area on Level 0 has no Room", MarkingList.Text(list));
    }

    [Fact]
    public void Beside_an_unplaced_room_the_list_never_says_the_rooms_drawn_are_read()
    {
        // review round 1: the area's line said "the rooms drawn are read" while an unplaced Room stopped every room
        var house = Ranch();
        house.Areas.Add(Unroomed());
        var i = house.MarkedIndex("living");
        house.Marked[i] = house.Marked[i] with { Placement = RoomPlacement.Unplaced };
        Assert.Null(InteriorReader.Read(house.Model()).Interior["rooms"]);
        var summary = MarkingList.Build(house.Model()).Summary;
        Assert.Contains(summary, s => s.Contains("so no room is read for egress until each is placed or deleted"));
        Assert.DoesNotContain(summary, s => s.Contains("the rooms drawn are read"));
        Assert.Contains(summary, s => s.StartsWith("1 enclosed area has no Room (listed above): once the rooms are read", StringComparison.Ordinal));
    }

    [Fact]
    public void With_no_room_drawn_at_all_the_list_never_says_the_rooms_drawn_are_read()
    {
        // review round 2: walls only (a first run): no rooms sent, yet the area's line said "the rooms drawn are read"
        var house = Ranch();
        house.Marked.RemoveAll(e => e.BuiltInCategory == Marks.Rooms);
        house.Rooms.Clear();
        house.Areas.Add(Unroomed());
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["rooms"]);
        Assert.Null(read.Interior["unknown_spaces"]);
        var summary = MarkingList.Build(house.Model()).Summary;
        Assert.DoesNotContain(summary, s => s.Contains("the rooms drawn are read"));
        Assert.Contains(summary, s => s.StartsWith("1 enclosed area has no Room (listed above): once the rooms are read", StringComparison.Ordinal));
    }

    [Fact]
    public void With_no_area_unroomed_nothing_is_added_and_no_level_is_listed()
    {
        var house = Ranch();
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["unknown_spaces"]);                            // the houses' recordings are unchanged
        Assert.DoesNotContain(MarkingList.Build(house.Model()).Rows, r => r.Kind == MarkedKind.Level);
        Assert.Equal([], InteriorTests.Problems(house, read));
    }

    [Fact]
    public void Enclosed_areas_that_couldnt_be_read_still_leave_every_room_out()
    {
        var house = Ranch();
        var model = house.Model() with { Interior = house.Model().Interior! with { EnclosedAreas = null } };
        var read = InteriorReader.Read(model);
        Assert.Null(read.Interior["rooms"]);
        Assert.Null(read.Interior["unknown_spaces"]);
        Assert.Contains(read.RoomsNotRead, w => w.StartsWith("the enclosed areas on each level couldn't be read"));
    }

    [Fact]
    public void An_area_lying_in_a_room_of_the_design_checked_has_its_room_one_in_another_option_doesnt()
    {
        // Revit's circuits are the main model's: a Room in the option checked can leave its circuit "no Room"
        var house = Ranch();
        var bed1 = house.Rooms[house.RoomIndex("bed1")];
        var pts = bed1.Boundary![0].Select(s => s.Start).ToList();
        var middle = new Xyz(pts.Average(p => p.X), pts.Average(p => p.Y), 0);
        house.Areas.Add(Unroomed(100, middle.X, middle.Y));
        Assert.Null(InteriorReader.Read(house.Model()).Interior["unknown_spaces"]);

        // on its edge, or on another level, it isn't clearly in the room: sent
        house.Areas[^1] = Unroomed(100, pts[0].X, pts[0].Y);
        Assert.NotNull(InteriorReader.Read(house.Model()).Interior["unknown_spaces"]);
        house.Areas[^1] = Unroomed(100, middle.X, middle.Y, level: "level-1");
        Assert.NotNull(InteriorReader.Read(house.Model()).Interior["unknown_spaces"]);
        house.Areas[^1] = Unroomed(100, middle.X, middle.Y, level: null);
        Assert.NotNull(InteriorReader.Read(house.Model()).Interior["unknown_spaces"]);

        // the room in a design option that isn't the one checked: not the design, so the area has no room in it
        house.Areas[^1] = Unroomed(100, middle.X, middle.Y);
        var i = house.MarkedIndex("bed1");
        house.Marked[i] = house.Marked[i] with { DesignOption = "opt-b" };
        var options = new OptionSet("set-1", "Entry", [new DesignOptionRecord("opt-a", "El Cabrillo", true), new DesignOptionRecord("opt-b", "Dover", false)]);
        var read = InteriorReader.Read(house.Model() with { OptionSets = [options] });
        Assert.NotNull(read.Interior["unknown_spaces"]);
        Assert.DoesNotContain(read.Interior["rooms"]!.AsArray(), r => r!["id"]!.GetValue<string>() == FakeHouse.Uid("bed1"));
        // in the primary option: the design checked
        house.Marked[i] = house.Marked[i] with { DesignOption = "opt-a" };
        Assert.Null(InteriorReader.Read(house.Model() with { OptionSets = [options] }).Interior["unknown_spaces"]);
    }

    [Fact]
    public void A_level_marked_no_rooms_clears_its_areas_unless_a_room_is_drawn_on_it_then_the_conflict_is_listed_first()
    {
        // a roof level: its areas are between parapets, none a room
        var house = Ranch();
        house.Areas.Add(Unroomed(level: "roof"));
        house.Marked.Add(new MarkedElement
        {
            UniqueId = "roof", BuiltInCategory = Marks.Levels, Name = "Roof",
            Instance = new Dictionary<Guid, MarkValue> { [Marks.NoRoomsOnLevel.Guid] = Yes },
        });
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["unknown_spaces"]);
        Assert.Empty(read.LevelConflicts);
        var list = MarkingList.Build(house.Model());
        Assert.Empty(list.UnknownAreas);
        var roof = list.Rows.Single(r => r.Kind == MarkedKind.Level);
        Assert.Equal("Roof (1 enclosed area with no Room)", roof.Label);
        Assert.False(roof.NeedsMarking);
        Assert.Equal(MarkingListResult.AllMarked, list.Headline);

        // marked No: not stated as having none, the area is sent
        house.Marked[^1] = house.Marked[^1] with { Instance = new Dictionary<Guid, MarkValue> { [Marks.NoRoomsOnLevel.Guid] = new(true, 0) } };
        Assert.NotNull(InteriorReader.Read(house.Model()).Interior["unknown_spaces"]);

        // level 0 marked Yes, with the ranch's rooms on it: the mark doesn't count, each Room is read, the conflict is first
        house = Ranch(noRooms: true);
        house.Areas.Add(Unroomed());
        read = InteriorReader.Read(house.Model());
        Assert.Equal(3, read.Interior["rooms"]!.AsArray().Count);                // never dropped in silence
        Assert.NotNull(read.Interior["unknown_spaces"]);                          // the mark doesn't count
        var conflict = Assert.Single(read.LevelConflicts);
        Assert.StartsWith($"Level \"Level 0\" is marked {Marks.NoRoomsOnLevel.Name} Yes, but Room \"", conflict);
        list = MarkingList.Build(house.Model());
        Assert.Equal(read.LevelConflicts, list.LevelConflicts);
        Assert.StartsWith("Conflict: Level \"Level 0\"", MarkingList.Text(list));
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
    }

    /// <summary>The level row's Not a story cell (#239's to-do): its blank says what it means (the level is tried both as
    /// a story and not) and never makes the row one to mark, so a list with every level unset is as it was; a level is
    /// listed for it once it is set either way, never asked for its No rooms mark when nothing needs one.</summary>
    [Fact]
    public void A_levels_not_a_story_cell_shows_its_blank_and_never_marks_a_level_to_mark()
    {
        // level 0 with an area with no Room: the row is to mark for No rooms on this level alone
        var house = Ranch();
        house.Areas.Add(Unroomed());
        var row = MarkingList.Build(house.Model()).Rows.Single(r => r.Kind == MarkedKind.Level);
        Assert.Equal([Marks.NoRoomsOnLevel, Marks.NotAStory], row.Cells.Select(c => c.Mark));
        var story = row.Cells[1];
        Assert.Equal((MarkState.LeftBlank, MarkingList.NotAStoryBlank), (story.State, story.Words));
        Assert.False(story.NeedsMarking);
        Assert.Equal([Marks.NoRoomsOnLevel], row.Cells.Where(c => c.NeedsMarking).Select(c => c.Mark));
        // marked No rooms: nothing left to mark, Not a story still blank
        house = Ranch(noRooms: true);
        var list = MarkingList.Build(house.Model());
        row = list.Rows.Single(r => r.Kind == MarkedKind.Level);
        Assert.False(row.NeedsMarking);
        Assert.Equal(MarkState.LeftBlank, row.Cells[1].State);

        // a datum level with nothing on it: not listed while unset (no row for every level), listed once set either way
        house = Ranch();
        house.Marked.Add(new MarkedElement { UniqueId = "tof", BuiltInCategory = Marks.Levels, Name = "Top of foundation" });
        list = MarkingList.Build(house.Model());
        Assert.DoesNotContain(list.Rows, r => r.Kind == MarkedKind.Level);
        Assert.Equal(MarkingListResult.AllMarked, list.Headline);
        foreach (var (value, state, word) in new[] { (1, MarkState.Yes, "Yes"), (0, MarkState.No, "No") })
        {
            house.Marked[^1] = house.Marked[^1] with { Instance = new Dictionary<Guid, MarkValue> { [Marks.NotAStory.Guid] = new(true, value) } };
            list = MarkingList.Build(house.Model());
            row = list.Rows.Single(r => r.Kind == MarkedKind.Level);
            Assert.Equal("Top of foundation", row.Label);
            Assert.Equal((state, word), (row.Cells[1].State, row.Cells[1].Value));
            // no area with no Room on it: its blank No rooms on this level asks nothing
            Assert.Equal((MarkState.LeftBlank, MarkingList.NoRoomsBlank), (row.Cells[0].State, row.Cells[0].Words));
            Assert.False(row.NeedsMarking);
            Assert.Equal(MarkingListResult.AllMarked, list.Headline);
            Assert.Contains(Marks.NotAStory.Name, MarkingList.Text(list), StringComparison.Ordinal);
        }
    }

    [Fact]
    public void An_area_with_no_room_holds_back_no_basements_attics_or_lofts_and_the_checker_refuses_them_too()
    {
        var house = Ranch();
        house.ProjectMarks[Marks.NoSleepingLofts.Guid] = Yes;
        house.ProjectMarks[Marks.NoRamps.Guid] = Yes;
        Assert.Contains(InteriorReader.Read(house.Model()).Interior["has_none"]!.AsArray(), e => e!["kind"]!.GetValue<string>() == "sleeping_loft");
        house.Areas.Add(Unroomed());
        var read = InteriorReader.Read(house.Model());
        var kinds = read.Interior["has_none"]!.AsArray().Select(e => e!["kind"]!.GetValue<string>()).ToList();
        Assert.Equal(["ramp"], kinds);                                            // a ramp isn't a space
        var tick = read.Ticks.Single(t => t.Kind.Kind == "sleeping_loft");
        Assert.Contains(tick.Blockers, b => b.StartsWith("An enclosed area on Level 0 has no Room"));
    }

    // ---- hundreds alike are one line each, for the architect --------------------------------------------------

    [Fact]
    public void Many_alike_are_counted_on_one_line_per_type_and_per_level()
    {
        // Pacific Continental's Mark for egress: one line per grille and per area, ~300 lines nobody can read
        var house = Ranch();
        for (var k = 0; k < 136; k++)
            house.StairCandidates.Add(new($"m12-{k}", "OST_GenericModel", "Muntin Pattern_1x2", "a loadable family"));
        for (var k = 0; k < 130; k++)
            house.StairCandidates.Add(new($"m22-{k}", "OST_GenericModel", "Muntin Pattern_2x2", "a loadable family"));
        for (var k = 0; k < 6; k++)
            house.StairCandidates.Add(new($"pf-{k}", "OST_GenericModel", "Picture Frame", "a loadable family"));
        house.StairCandidates.Add(new("ip", "OST_GenericModel", "Ladder", "an in-place family"));
        for (var k = 0; k < 19; k++)
            house.Areas.Add(Unroomed(2 + k, 100 + 20 * k, 3, "roof") with { Level = "Roof" });
        house.Areas.Add(Unroomed());

        var stairs = StairReader.Blockers(house.Model());
        Assert.Equal(
            ["272 GenericModel elements are each a loadable family (3 types: Muntin Pattern_1x2 x136, Muntin Pattern_2x2 x130, " +
             "Picture Frame x6; each listed by id in the log): a stair or its railing drawn this way isn't read, so Gordium " +
             "can't tell every stair is read",
             "GenericModel \"Ladder\" is an in-place family: a stair or its railing drawn this way isn't read, so Gordium can't " +
             "tell every stair is read"], stairs);
        var areas = InteriorReader.AreaBlockers(house.Model());
        Assert.Equal(2, areas.Count);
        Assert.StartsWith("19 enclosed areas on Roof have no Room (2 to 20 sq ft; each listed with its place in the log)", areas[0]);
        Assert.StartsWith("An enclosed area on Level 0 has no Room (331.4 sq ft", areas[1]);

        var list = MarkingList.Build(house.Model());
        Assert.Equal(stairs, list.StairBlockers);
        Assert.Equal(areas, list.UnknownAreas);
        // one line more than before for the level row's Not a story cell (#239's to-do): still tens, never hundreds
        var lines = MarkingList.Text(list).Split('\n').Length;
        Assert.True(lines < 62, lines.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Assert.Contains(list.Summary, s => s.StartsWith("20 enclosed areas have no Room", StringComparison.Ordinal));
        // each one still in the reading, by id and place: the description's spaces and the log's words
        var read = InteriorReader.Read(house.Model());
        Assert.Equal(20, read.Interior["unknown_spaces"]!.AsArray().Count);
        Assert.Equal(20, read.UnknownSpaces.Count);
    }

    // ---- what is in, under and over a room: the design checked only -------------------------------------------

    [Fact]
    public void A_wall_in_a_design_option_not_checked_doesnt_stand_in_a_room()
    {
        var house = Ranch();
        var i = house.RoomIndex("bed1");
        var wall = new NearbyElement("option-wall", "OST_Walls", "Dover wall", DesignOption: "opt-b");
        house.Rooms[i] = house.Rooms[i] with { Inside = [wall] };
        var options = new OptionSet("set-1", "Entry", [new DesignOptionRecord("opt-a", "El Cabrillo", true), new DesignOptionRecord("opt-b", "Dover", false)]);
        var model = house.Model() with { OptionSets = [options] };
        var bed1 = InteriorReader.Read(model).Interior["rooms"]!.AsArray().Single(r => r!["id"]!.GetValue<string>() == FakeHouse.Uid("bed1"))!;
        Assert.NotNull(bed1["floor"]);
        // the same wall in the option checked stands in it: no floor
        house.Rooms[i] = house.Rooms[i] with { Inside = [wall with { DesignOption = "opt-a" }] };
        bed1 = InteriorReader.Read(house.Model() with { OptionSets = [options] }).Interior["rooms"]!.AsArray()
            .Single(r => r!["id"]!.GetValue<string>() == FakeHouse.Uid("bed1"))!;
        Assert.Null(bed1["floor"]);
    }

    // ---- a wall whose faces Revit can't give ------------------------------------------------------------------

    [Fact]
    public void A_window_whose_walls_faces_couldnt_be_read_says_so_and_sends_no_clear_opening()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.Openings.FindIndex(o => o.UniqueId == FakeHouse.Uid("w1"));
        house.Openings[i] = house.Openings[i] with { WallOpening = null, WallOpeningBy = null, WallOpeningUnread = true };
        var read = InteriorReader.Read(house.Model());
        var w1 = read.Interior["openings"]!.AsArray().Single(o => o!["id"]!.GetValue<string>() == FakeHouse.Uid("w1"))!;
        Assert.Null(w1["stated_clear"]);
        Assert.StartsWith("its wall's geometry couldn't be read",
                          read.Notes.Single(n => n.Part == FakeHouse.Uid("w1") && n.Field == "stated_clear").Why);
    }
}
