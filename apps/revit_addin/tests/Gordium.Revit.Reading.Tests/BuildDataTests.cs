using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The Revit-free part of building a model from a drawing script's data (BuildData.cs), ported from the
/// script Ben received (the Children's Odyssey childcare centre, rebuilt from its life-safety sheet LS1.0): the data
/// as the extractor writes it (apps/revit_addin/tools/extract_build_data.py, run here on its made-up test script), the
/// script's names and marks, its door flips, the floor's outline and the phase of existing walls.</summary>
public sealed class BuildDataTests
{
    private static readonly string Tiny = Path.Combine(Env.Repo, "apps", "revit_addin", "tools", "tests", "tiny_drawing_script.py");

    /// <summary>The extractor's output for the made-up script, as the add-in reads it.</summary>
    private static JsonObject Extracted()
    {
        const string code = "import importlib.util, json, sys; from pathlib import Path; " +
                            "s = importlib.util.spec_from_file_location('x', sys.argv[1]); m = importlib.util.module_from_spec(s); " +
                            "s.loader.exec_module(m); print(json.dumps(m.extract(Path(sys.argv[2]))))";
        var tool = Path.Combine(Env.Repo, "apps", "revit_addin", "tools", "extract_build_data.py");
        return JsonNode.Parse(Env.RunCode(code, tool, Tiny))!.AsObject();
    }

    private static BuildDataException Refused(Action<JsonObject> change)
    {
        var data = Extracted();
        change(data);
        return Assert.Throws<BuildDataException>(() => BuildData.Parse(data));
    }

    [Fact]
    public void The_extractors_data_is_read_whole()
    {
        var m = BuildData.Parse(Extracted());
        Assert.Equal((5, 2, 1, 2), (m.Walls.Count, m.Doors.Count, m.Windows.Count, m.Rooms.Count));
        Assert.Equal(("Level 1", 0.0), (m.LevelName, m.LevelElevation));
        Assert.Equal("tiny_drawing_script.py", m.SourceFile);
        Assert.Equal(64, m.SourceSha256!.Length);
        var partition = m.Walls[4];
        Assert.Equal((4, 4.5, "New", true, "1 HR", 3.5), (partition.Id, partition.ThicknessIn, partition.Status, partition.SmokePartition,
                                                         partition.FireRating, partition.HeightFt));
        Assert.Equal(new PlanPoint(6.5, 0), m.Doors[0].Hinge);
        Assert.Null(m.Doors[1].Hinge);
        Assert.True(m.Doors[1].IsDouble);
        Assert.Equal((2, 1), (m.Doors[1].Number, m.Windows[0].Number));
        Assert.Equal((36.0, 2), (m.Windows[0].SillIn, m.Windows[0].HostWall));
        Assert.Equal(("1", "Classroom", 88.5), (m.Rooms[0].Number, m.Rooms[0].Name, m.Rooms[0].AreaSf));
        Assert.Null(m.Rooms[1].AreaSf);
    }

    [Fact]
    public void Every_problem_is_named_at_once_never_a_part_dropped()
    {
        var x = Refused(d =>
        {
            d["doors"]![0]!["host_wall"] = 99;
            d["windows"]![0]!.AsObject().Remove("sill_in");
            d["walls"]![1]!["status"] = "Demolished";
            d["rooms"]![0]!["boundary"] = new JsonArray(new JsonArray(0, 0));
            d["stats"]!["doors"] = 3;
        });
        Assert.Contains("door 1: host_wall is 99, not the id of a wall in the data", x.Problems);
        Assert.Contains("window 1: no sill_in", x.Problems);
        Assert.Contains("wall 1: status is \"Demolished\", not \"Existing\" or \"New\"", x.Problems);
        Assert.Contains("room 1: boundary isn't a list of 3 or more points", x.Problems);
        Assert.Contains("stats: doors says 3, the data has 2", x.Problems);
    }

    [Theory]
    [InlineData("swing", "door 1: swing_dir is [1,1], not a unit vector [x, y]")]
    [InlineData("hinge", "door 1: hinge is \"left\", not a point [x, y]")]
    [InlineData("kind", "door 2: kind is \"triple\", not \"single\" or \"double\"")]
    [InlineData("id", "wall 0: a second wall with this id")]
    [InlineData("bool", "wall 0: thickness_in is true, not a thickness over 0")]
    [InlineData("units", "data: units is \"metres\", not \"feet\"")]
    [InlineData("open", "footprint: its last point isn't its first (the add-in, as the script, drops the closing point)")]
    [InlineData("rating", "wall 0: fire_rating is \"\", not null or text")]
    // as the extractor refuses them (review round 1): the key is required, a null hinge is no hinge, a blank level name
    [InlineData("no rating", "wall 0: no fire_rating")]
    [InlineData("null hinge", "door 1: hinge is null, not a point [x, y]")]
    [InlineData("blank level", "data: level isn't a level with a name and elevation_ft")]
    [InlineData("null area", "room 1: area_sf is null, not a number")]
    public void Each_bad_part_is_refused_in_words(string what, string words)
    {
        var x = Refused(d =>
        {
            switch (what)
            {
                case "swing": d["doors"]![0]!["swing_dir"] = new JsonArray(1, 1); break;
                case "hinge": d["doors"]![0]!["hinge"] = "left"; break;
                case "kind": d["doors"]![1]!["kind"] = "triple"; break;
                case "id": d["walls"]![4]!["id"] = 0; break;
                case "bool": d["walls"]![0]!["thickness_in"] = true; break;
                case "units": d["units"] = "metres"; break;
                case "open": d["footprint"]!.AsArray().RemoveAt(d["footprint"]!.AsArray().Count - 1); break;
                case "rating": d["walls"]![0]!["fire_rating"] = ""; break;
                case "no rating": d["walls"]![0]!.AsObject().Remove("fire_rating"); break;
                case "null hinge": d["doors"]![0]!["hinge"] = null; break;
                case "blank level": d["level"]!["name"] = "   "; break;
                case "null area": d["rooms"]![0]!["area_sf"] = null; break;
            }
        });
        Assert.Contains(words, x.Problems);
    }

    [Fact]
    public void The_request_names_its_data_and_rvt_and_takes_the_scripts_toggles()
    {
        var r = BuildRequest.Parse(JsonNode.Parse("""{"data": "d.json", "save_as": "C:/out/odyssey.rvt"}"""));
        Assert.Equal(("d.json", null, "C:/out/odyssey.rvt", true, true, true),
                     (r.Data, r.Template, r.SaveAs, r.SwingOppositeFacing, r.HingeOppositeHand, r.UsePhases));
        r = BuildRequest.Parse(JsonNode.Parse("""{"data": "d.json", "template": "a.rte", "save_as": "o.rvt", "swing_opposite_facing": false}"""));
        Assert.Equal(("a.rte", false, true), (r.Template, r.SwingOppositeFacing, r.HingeOppositeHand));
        var x = Assert.Throws<BuildDataException>(() =>
            BuildRequest.Parse(JsonNode.Parse("""{"data": "d.json", "save_as": "o.txt", "swing_oposite_facing": false, "use_phases": "yes"}""")));
        Assert.Contains("save_as o.txt isn't a .rvt file", x.Problems);
        Assert.Contains("the request has swing_oposite_facing, which isn't asked for (a misspelling?)", x.Problems);
        Assert.Contains("the request's use_phases isn't true or false", x.Problems);
        Assert.Contains("the request has no data",
                        Assert.Throws<BuildDataException>(() => BuildRequest.Parse(JsonNode.Parse("""{"save_as": "o.rvt"}"""))).Problems);
    }

    [Fact]
    public void Names_and_marks_are_the_scripts()
    {
        var m = BuildData.Parse(Extracted());
        Assert.Equal("LS Existing 8\"", BuildData.WallTypeName(m.Walls[0]));
        Assert.Equal("LS New 4.5\" 1 HR", BuildData.WallTypeName(m.Walls[4]));
        Assert.Equal("Existing", BuildData.WallComment(m.Walls[0]));
        Assert.Equal("New | SMOKE PARTITION | 1 HR | PARTIAL HEIGHT (height assumed)", BuildData.WallComment(m.Walls[4]));
        Assert.Equal(("W4", "D01", "D02", "WN01"), (BuildData.WallMark(m.Walls[4]), BuildData.DoorMark(m.Doors[0]),
                                                   BuildData.DoorMark(m.Doors[1]), BuildData.WindowMark(m.Windows[0])));
        Assert.Equal("Door 36\" x 84\" (LS1.0)", BuildData.OpeningTypeName("Door", 36, 84));
        Assert.Equal("Window 33.5\" x 48\" (LS1.0)", BuildData.OpeningTypeName("Window", 33.5, 48));
    }

    [Fact]
    public void Families_are_picked_by_the_scripts_keywords_in_order()
    {
        string[] labels = ["Bifold-2 Panel 36\"", "Double-Glass 72\"", "Single-Flush 36\" x 84\"", "Double-Flush 72\" x 84\""];
        Assert.Equal(2, BuildData.PickSymbol(labels, BuildData.SingleKeywords));
        Assert.Equal(3, BuildData.PickSymbol(labels, BuildData.DoubleKeywords));       // Double-Flush before plain "Double"
        Assert.Equal(0, BuildData.PickSymbol(["Bifold"], BuildData.DoubleKeywords));     // the first, which isn't a double
        Assert.False(BuildData.IsDoubleFamily("Bifold"));
        Assert.Null(BuildData.PickSymbol([], BuildData.WindowKeywords));
    }

    [Fact]
    public void The_floor_outline_drops_the_closing_point_and_the_short_sides_and_stays_closed()
    {
        PlanPoint[] ring = [new(0, 0), new(10, 0), new(10, 0.005), new(10, 10), new(0, 10), new(0.004, 0), new(0, 0)];
        Assert.Equal([new(0, 0), new(10, 0), new(10, 10), new(0, 10)], BuildData.FloorOutline(ring));
        Assert.Equal(100, BuildData.Area(BuildData.FloorOutline(ring)), 9);
        Assert.Throws<BuildDataException>(() => BuildData.FloorOutline([new(0, 0), new(0.001, 0), new(0, 0.001), new(0, 0)]));
        var m = BuildData.Parse(Extracted());
        Assert.Equal(4, BuildData.FloorOutline(m.Footprint).Count);
    }

    // ---- data with several levels: the New York eval's (apps/revit_addin/tools/evals/make_ny_build_data.py) ----

    private static JsonObject NewYork(string folder) =>
        JsonNode.Parse(File.ReadAllText(Path.Combine(Env.Repo, folder, "revit_build_data.json")))!.AsObject();

    private const string Orangetown = "test_data/real_houses/orangetown_ny_80_south_william";
    private const string IthacaRd = "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd";

    [Fact]
    public void The_orangetown_house_is_read_whole_on_its_three_levels()
    {
        var m = BuildData.Parse(NewYork(Orangetown));
        Assert.Equal((41, 1, 14, 17), (m.Walls.Count, m.Doors.Count, m.Windows.Count, m.Rooms.Count));
        Assert.Equal([("Second floor", 0.0), ("Main floor", -9.875), ("Basement", -18.875)], m.Levels.Select(l => (l.Name, l.ElevationFt)));
        Assert.Equal((3, 17, 1), (m.Floors.Count, m.Ceilings.Count, m.Separations.Count));
        Assert.Empty(m.Footprint);
        Assert.Equal(4, m.Lot!.Count);
        // every wall and room on a level of the data, each window on a second-floor or basement wall, the door on the main floor
        Assert.Equal(24, m.Walls.Count(w => w.Level == "Second floor"));
        Assert.Equal([("Second floor", 14), ("Main floor", 2), ("Basement", 1)],
                     m.Rooms.GroupBy(r => r.Level!).Select(g => (g.Key, g.Count())));
        Assert.Equal("Main floor", m.LevelOf(m.Walls.First(w => w.Id == m.Doors[0].HostWall).Level).Name);
        Assert.Equal(12, m.Windows.Count(w => m.Walls.First(x => x.Id == w.HostWall).Level == "Second floor"));
        // the door's swing isn't in the source: none, so it is never flipped on a guess
        Assert.Null(m.Doors[0].SwingDir);
        Assert.Null(m.Doors[0].Hinge);
        Assert.Equal((36.0, 54.0, 27.0), (m.Windows[0].WidthIn, m.Windows[0].HeightIn, m.Windows[0].SillIn));
        Assert.Equal(("1", 229.5), (m.Rooms[0].Number, m.Rooms[0].AreaSf));
        Assert.Equal(8.0, m.Ceilings[0].UndersideFt);
        Assert.Equal("Door 36\" x 96\" (Orangetown A-1 to A-5)", BuildData.OpeningTypeName("Door", 36, 96, m.TypeSuffix));
    }

    [Fact]
    public void The_orangetown_rooms_are_closed_by_their_own_levels_walls()
    {
        // each room's boundary runs on walls of its own level, but where bedroom 2 meets its alcove: the separation line
        var m = BuildData.Parse(NewYork(Orangetown));
        var sep = m.Separations.Single();
        foreach (var r in m.Rooms)
        {
            var gaps = BuildData.BoundaryGaps(r, m.Walls.Where(w => m.LevelOf(w.Level) == m.LevelOf(r.Level)).ToList());
            if (r.Number is "2" or "8")
                Assert.All(gaps, g => Assert.True(Math.Abs(g.From.Y - sep.Start.Y) < 1e-6 && Math.Abs(g.To.Y - sep.Start.Y) < 1e-6, g.Words));
            else
                Assert.Empty(gaps);
        }
    }

    [Fact]
    public void The_106_ithaca_rd_box_its_lot_and_ground_are_read_whole()
    {
        var m = BuildData.Parse(NewYork(IthacaRd));
        Assert.Equal((4, 0, 0, 0), (m.Walls.Count, m.Doors.Count, m.Windows.Count, m.Rooms.Count));
        Assert.Equal([("Level 1", 0.0), ("Roof", 35.0)], m.Levels.Select(l => (l.Name, l.ElevationFt)));
        Assert.Equal(6570, BuildData.Area(m.Lot!), 9);                                   // 73 x 90 (Inputs!B3, B4)
        var roof = Assert.Single(m.Floors);
        Assert.Equal(("Roof", 0.0), (roof.Level, roof.TopOffsetFt));
        Assert.Equal(1855, BuildData.Area(roof.Outline), 9);                             // Inputs!B10
        Assert.All(m.Walls, w => Assert.Equal((35.0, "Level 1"), (w.HeightFt, w.Level)));
        Assert.Equal(4, m.SpotGrades.Count);
        Assert.All(m.SpotGrades, s => Assert.Equal(0, s.Z));
    }

    /// <summary>The Building Code eval's four-unit building (apartment.yaml): two levels, each with its four
    /// exterior walls and four partitions, four doors (Level 1 also its two discharge doors) and five rooms, each room
    /// closed by its own level's walls, a slab under each level and the roof.</summary>
    [Fact]
    public void The_four_unit_apartment_is_read_whole_on_its_two_levels()
    {
        var m = BuildData.Parse(NewYork("test_data/test_sites/new_york/ithaca_city/four_unit_apartment"));
        Assert.Equal((16, 10, 0, 10), (m.Walls.Count, m.Doors.Count, m.Windows.Count, m.Rooms.Count));
        Assert.Equal([("Level 1", 0.0), ("Level 2", 10.0)], m.Levels.Select(l => (l.Name, l.ElevationFt)));
        Assert.Equal(3, m.Floors.Count);
        Assert.Equal(6, m.Doors.Count(d => m.Walls.First(w => w.Id == d.HostWall).Level == "Level 1"));
        foreach (var r in m.Rooms)
            Assert.Empty(BuildData.BoundaryGaps(r, m.Walls.Where(w => m.LevelOf(w.Level) == m.LevelOf(r.Level)).ToList()));
    }

    [Theory]
    [InlineData("both", "data: gives both level and levels: one or the other")]
    [InlineData("no level", "wall 1: no level (the data has several)")]
    [InlineData("unknown level", "room 1: level is \"Attic\", not one of the data's levels")]
    [InlineData("twin level", "level 1: a second level at 0 ft")]
    [InlineData("open floor", "floor 1: outline: its last point isn't its first")]
    [InlineData("floors and footprint", "data: gives both floors and a footprint: one or the other")]
    [InlineData("no floors", "data: no floors and no footprint (with levels, give the floors)")]
    [InlineData("spot", "spot grade 1: at isn't a point [x, y, z]")]
    [InlineData("room twice", "room number 1: given to 2 rooms (marks find a room by its number)")]
    [InlineData("swing", "door 1: swing_dir is [1,1], not a unit vector [x, y]")]
    public void Each_bad_part_of_data_with_levels_is_refused_in_words(string what, string words)
    {
        var d = NewYork(Orangetown);
        switch (what)
        {
            case "both": d["level"] = new JsonObject { ["name"] = "Level 1", ["elevation_ft"] = 0 }; break;
            case "no level": d["walls"]![0]!.AsObject().Remove("level"); break;
            case "unknown level": d["rooms"]![0]!["level"] = "Attic"; break;
            case "twin level": d["levels"]![1]!["elevation_ft"] = 0; break;
            case "open floor": d["floors"]![0]!["outline"]!.AsArray().RemoveAt(d["floors"]![0]!["outline"]!.AsArray().Count - 1); break;
            case "floors and footprint": d["footprint"] = d["floors"]![0]!["outline"]!.DeepClone(); break;
            case "no floors": d.Remove("floors"); break;
            case "spot": d["spot_grades"] = new JsonArray(new JsonObject { ["at"] = new JsonArray(1, 2) }); break;
            case "room twice": d["rooms"]![1]!["number"] = "1"; break;
            case "swing": d["doors"]![0]!["swing_dir"] = new JsonArray(1, 1); break;
        }
        Assert.Contains(words, Assert.Throws<BuildDataException>(() => BuildData.Parse(d)).Problems);
    }

    [Fact]
    public void The_scripts_one_level_data_still_needs_a_swing_and_takes_no_levels_keys()
    {
        // a door of the script's data with no swing is refused, as before: only data with levels may leave it out
        Assert.Contains("door 1: no swing_dir", Refused(d => d["doors"]![0]!.AsObject().Remove("swing_dir")).Problems);
        Assert.Contains("data: floors, ceilings, separations, a lot and spot grades are read only with levels",
                        Refused(d => d["lot"] = new JsonObject { ["outline"] = new JsonArray(new JsonArray(0, 0), new JsonArray(1, 0), new JsonArray(1, 1), new JsonArray(0, 0)) }).Problems);
        Assert.Contains("wall 0: level is \"Second floor\", not one of the data's levels",
                        Refused(d => d["walls"]![0]!["level"] = "Second floor").Problems);
        var m = BuildData.Parse(Extracted());
        Assert.Equal([("Level 1", 0.0)], m.Levels.Select(l => (l.Name, l.ElevationFt)));
        Assert.Equal("LS1.0", m.TypeSuffix);
        Assert.Null(m.Lot);
    }

    /// <summary>Ben's childcare centre as extracted (not in the repository): read whole when GORDIUM_BUILD_DATA names
    /// its JSON; with it unset there is nothing to read and the test does nothing.</summary>
    [Fact]
    public void Bens_childcare_centre_is_read_whole_when_GORDIUM_BUILD_DATA_names_it()
    {
        if (Environment.GetEnvironmentVariable("GORDIUM_BUILD_DATA") is not { Length: > 0 } path)
            return;
        var m = BuildData.Parse(JsonNode.Parse(File.ReadAllText(path)));
        Assert.Equal((122, 52, 67, 25), (m.Walls.Count, m.Doors.Count, m.Windows.Count, m.Rooms.Count));
        Assert.Equal(5, m.Doors.Count(d => d.IsDouble));
        Assert.True(BuildData.FloorOutline(m.Footprint).Count >= 3);
        // Revit 2027 run 1: rooms 2 and 3 not enclosed. The tracing stops walls W16 and W24 1.44 ft short of the east
        // vestibule's jambs W27 and W28 (ends at x 192.42, faces at 193.87), opening both classrooms to the open-air
        // entrance (no wall across it, x 194.58, y 36.32 to 49.36). Rooms 10 and 21 share a 0.5 ft gap between W26 and
        // W68 that Revit closed itself (both enclosed in run 1, as two rooms)
        var gaps = m.Rooms.ToDictionary(r => r.Number, r => BuildData.BoundaryGaps(r, m.Walls));
        Assert.Equal(["10", "2", "21", "3"], gaps.Where(g => g.Value.Count > 0).Select(g => g.Key).Order());
        var g2 = Assert.Single(gaps["2"]);
        Assert.Equal((16, 27), (g2.WallBefore, g2.WallAfter));
        Assert.InRange(g2.Length, 1.37, 1.47);
        var g3 = Assert.Single(gaps["3"]);
        Assert.Equal((28, 24), (g3.WallBefore, g3.WallAfter));
        Assert.InRange(g3.Length, 1.37, 1.47);
        Assert.Equal((26, 68), (Assert.Single(gaps["10"]).WallBefore, gaps["10"][0].WallAfter));
        Assert.InRange(gaps["21"].Single().Length, 0.45, 0.55);
        // the two corrections of build_corrected_request.json (LS1.0 shows W16 and W24 running on to the jambs' faces,
        // x 193.8667) close both classrooms, and change nothing else
        var (fixedModel, applied, refused) = BuildData.Correct(m, [new WallCorrection(16, new PlanPoint(193.8667, 48.1667), Why),
                                                                    new WallCorrection(24, new PlanPoint(193.8667, 37.5111), Why)]);
        Assert.Equal(2, applied.Count);
        Assert.Empty(refused);
        Assert.Equal(["10", "21"], fixedModel.Rooms.Where(r => BuildData.BoundaryGaps(r, fixedModel.Walls).Count > 0).Select(r => r.Number).Order());
        // the five "Highlighted walls overlap" warnings of run 1, each a pair the data draws along each other
        Assert.Equal([(2, 119), (27, 120), (28, 121), (32, 105), (33, 34)], BuildData.WallOverlaps(m.Walls).Select(o => (o.A, o.B)));
        // the eval's five trims (test_data/answer_keys/portland_me_19_libby_st/eval_marks.yaml, model_corrections): each
        // pair joined end to end, no overlap left (the slivers Revit found as enclosed areas with no Room)
        var (trimmed, done, notDone) = BuildData.Correct(fixedModel, LibbyTrims);
        Assert.Equal(5, done.Count);
        Assert.Empty(notDone);
        Assert.Empty(BuildData.WallOverlaps(trimmed.Walls));
        // and the two fills of the east entry's jamb pockets: added, overlapping no wall along its length
        var (filled, fillsDone, fillsNot) = BuildData.Correct(trimmed, LibbyFills);
        Assert.Equal(["filled W122", "filled W123"], fillsDone.Select(a => a[..11]));
        Assert.Empty(fillsNot);
        Assert.Empty(BuildData.WallOverlaps(filled.Walls));
        // and the two merges of the walls drawn face to face (the 0 sq ft slivers Revit gave no point in)
        var (_, mergesDone, mergesNot) = BuildData.Correct(filled, LibbyMerges);
        Assert.Equal(2, mergesDone.Count);
        Assert.Empty(mergesNot);
    }

    /// <summary>The two merges of eval_marks.yaml's model_corrections.</summary>
    internal static readonly WallCorrection[] LibbyMerges =
    [
        new(57, default, "W111 drawn face to face against W57: a 0 sq ft sliver between them", CorrectionKind.Merge, MergeWith: 111),
        new(65, default, "W114 drawn face to face against W65: a 0 sq ft sliver between them", CorrectionKind.Merge, MergeWith: 114),
    ];

    [Fact]
    public void A_merge_draws_two_walls_face_to_face_as_one_and_refuses_any_other_pair()
    {
        var data = BuildData.Parse(Extracted());
        var w = data.Walls[0];
        // a 12 in wall at x 61.7889 and a 16 in one beside it, faces together: the Children's Odyssey's W57 and W111
        var a = w with { Id = 57, Start = new PlanPoint(61.7889, 38.1778), End = new PlanPoint(61.7889, 34.8445), ThicknessIn = 12 };
        var b = w with { Id = 111, Start = new PlanPoint(60.6222, 38.1778), End = new PlanPoint(60.6222, 34.8444), ThicknessIn = 16, Status = "New" };
        var m = data with { Walls = [.. data.Walls, a, b] };
        var merge = new WallCorrection(57, default, "face to face", CorrectionKind.Merge, MergeWith: 111);
        var (merged, applied, refused) = BuildData.Correct(m, [merge]);
        Assert.Empty(refused);
        Assert.DoesNotContain(merged.Walls, x => x.Id == 111);
        var one = merged.Walls.Single(x => x.Id == 57);
        Assert.Equal(28, one.ThicknessIn);
        Assert.Equal(61.1222, one.Start.X, 4);                    // half way between the outer faces, 59.9555 and 62.2889
        Assert.StartsWith("merged W111 into W57", applied.Single());
        foreach (var (other, words) in new[]
                 {
                     (b with { Start = new PlanPoint(60.5, 38.1778), End = new PlanPoint(60.5, 34.8444) }, "faces aren't together"),
                     (b with { End = new PlanPoint(60.6222, 36) }, "the same stretch"),
                     (b with { End = new PlanPoint(59.6222, 34.8444) }, "aren't parallel"),
                 })
        {
            var (same, none, no) = BuildData.Correct(data with { Walls = [.. data.Walls, a, other] }, [merge]);
            Assert.Empty(none);
            Assert.Contains(words, no.Single());
            Assert.Contains(same.Walls, x => x.Id == 111);
        }
        // review round 1: the second wall's smoke partition and rating are carried (the stricter), and said; two
        // different ratings are refused
        var rated = data with { Walls = [.. data.Walls, a with { SmokePartition = false, FireRating = null }, b with { SmokePartition = true, FireRating = "1 hr" }] };
        var (carried, said, _) = BuildData.Correct(rated, [merge]);
        var kept = carried.Walls.Single(x => x.Id == 57);
        Assert.Equal((true, "1 hr"), (kept.SmokePartition, kept.FireRating));
        Assert.Contains("a smoke partition", said.Single());
        Assert.Contains("status Existing kept (W111 was New)", said.Single());
        var clash = data with { Walls = [.. data.Walls, a with { FireRating = "2 hr" }, b with { FireRating = "1 hr" }] };
        Assert.Contains("fire ratings differ", BuildData.Correct(clash, [merge]).Refused.Single());
        var hosting = m with { Doors = [.. m.Doors, data.Doors[0] with { HostWall = 111 }] };
        Assert.Contains("a door or window", BuildData.Correct(hosting, [merge]).Refused.Single());
        var r = BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt", "corrections": [{"merge": ["W57", "W111"], "why": "face to face"}]}
            """));
        Assert.Equal(merge, Assert.Single(r.Corrections));
    }

    /// <summary>The two fills of eval_marks.yaml's model_corrections: LS1.0 draws the east entry's angled jambs solid.</summary>
    internal static readonly WallCorrection[] LibbyFills =
    [
        new(0, new PlanPoint(192.2294, 48.2972), "LS1.0: the north jamb of the east entry is solid wall", CorrectionKind.Fill, new PlanPoint(189.6688, 47.2102), 12.151),
        new(0, new PlanPoint(192.2283, 37.3825), "LS1.0: the south jamb of the east entry is solid wall", CorrectionKind.Fill, new PlanPoint(189.6682, 38.4693), 12.185),
    ];

    [Fact]
    public void A_fill_adds_a_short_wall_only_between_walls_of_the_data()
    {
        var m = BuildData.Parse(Extracted());                    // wall W0 from (0, 0) to (20, 0)
        WallCorrection Fill(double x0, double y0, double x1, double y1, double t) =>
            new(0, new PlanPoint(x1, y1), Why, CorrectionKind.Fill, new PlanPoint(x0, y0), t);
        var (filled, applied, refused) = BuildData.Correct(m, [Fill(5, 1, 7, 1, 12)]);
        Assert.Empty(refused);
        var added = filled.Walls[^1];
        Assert.Equal((m.Walls.Max(w => w.Id) + 1, new PlanPoint(5, 1), new PlanPoint(7, 1), 12.0), (added.Id, added.Start, added.End, added.ThicknessIn));
        Assert.Equal((true, true), (added.NoJoinStart, added.NoJoinEnd));       // a fill joins nothing
        Assert.StartsWith($"filled W{added.Id}: a 2 ft wall 12 in thick from (5, 1) to (7, 1)", applied.Single());
        foreach (var (c, words) in new[]
                 {
                     (Fill(5, 1, 8.5, 1, 12), "at most 3 ft long"),        // a run of wall, not a fill
                     (Fill(5, 1, 7, 1, 30), "2 ft thick"),
                     (Fill(5, 6, 7, 6, 12), "from every wall of the data"),  // standing on its own
                 })
        {
            var (same, none, no) = BuildData.Correct(m, [c]);
            Assert.Empty(none);
            Assert.Contains(words, no.Single());
            Assert.Equal(m.Walls, same.Walls);
        }
        var r = BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt",
             "corrections": [{"fill": {"start": [5, 1], "end": [7, 1], "thickness_in": 12}, "why": "solid on the sheet"}]}
            """));
        Assert.Equal(CorrectionKind.Fill, Assert.Single(r.Corrections).Kind);
        Assert.Throws<BuildDataException>(() => BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt", "corrections": [{"fill": {"start": [5, 1], "end": [7, 1]}, "why": "no thickness"}]}
            """)));
    }

    /// <summary>The five trims of eval_marks.yaml's model_corrections.</summary>
    internal static readonly WallCorrection[] LibbyTrims =
    [
        new(119, new PlanPoint(132.9111, 84.9889), "overlaps W2 along 0.69 ft: ends where W2 begins", CorrectionKind.TrimEnd),
        new(27, new PlanPoint(194.3667, 49.3578), "overlaps W120 along 1.15 ft: starts where W120 ends", CorrectionKind.TrimStart),
        new(28, new PlanPoint(194.3667, 36.3244), "overlaps W121 along 1.15 ft: ends where W121 begins", CorrectionKind.TrimEnd),
        new(105, new PlanPoint(168.7167, 28.1889), "overlaps W32 along 0.33 ft: starts where W32 ends", CorrectionKind.TrimStart),
        new(34, new PlanPoint(168.5556, 16.1856), "overlaps W33 along 0.34 ft: starts where W33 ends", CorrectionKind.TrimStart),
    ];

    [Fact]
    public void A_trim_only_shortens_a_wall_along_its_line_by_at_most_2_ft()
    {
        var m = BuildData.Parse(Extracted());                    // wall W0 from (0, 0) to (20, 0)
        var (end, applied, _) = BuildData.Correct(m, [new WallCorrection(0, new PlanPoint(18.5, 0), Why, CorrectionKind.TrimEnd)]);
        Assert.Equal((new PlanPoint(0, 0), new PlanPoint(18.5, 0)), (end.Walls[0].Start, end.Walls[0].End));
        Assert.Equal($"trimmed W0: end (20, 0) → (18.5, 0) (1.5 ft): {Why}", applied.Single());
        var (start, _, _) = BuildData.Correct(m, [new WallCorrection(0, new PlanPoint(1, 0), Why, CorrectionKind.TrimStart)]);
        Assert.Equal((new PlanPoint(1, 0), new PlanPoint(20, 0)), (start.Walls[0].Start, start.Walls[0].End));
        // the trimmed end alone is drawn with its joins disallowed (a join there made Revit delete both walls)
        Assert.Equal((false, true), (end.Walls[0].NoJoinStart, end.Walls[0].NoJoinEnd));
        Assert.Equal((true, false), (start.Walls[0].NoJoinStart, start.Walls[0].NoJoinEnd));
        Assert.Equal((false, false), (m.Walls[0].NoJoinStart, m.Walls[0].NoJoinEnd));
        foreach (var (to, kind, words) in new[]
                 {
                     (new PlanPoint(17.5, 0), CorrectionKind.TrimEnd, "more than 2 ft"),
                     (new PlanPoint(21, 0), CorrectionKind.TrimEnd, "would lengthen"),         // a trim never lengthens
                     (new PlanPoint(-1, 0), CorrectionKind.TrimStart, "would lengthen"),
                     (new PlanPoint(19, 0.5), CorrectionKind.TrimEnd, "would lengthen, turn"),  // off its line
                 })
        {
            var (same, none, refused) = BuildData.Correct(m, [new WallCorrection(0, to, Why, kind)]);
            Assert.Empty(none);
            Assert.Contains(words, refused.Single());
            Assert.Equal(m.Walls, same.Walls);
        }
    }

    [Fact]
    public void The_request_reads_a_trim_and_refuses_two_changes_in_one_correction()
    {
        var r = BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt",
             "corrections": [{"wall": "W119", "trim_end_to": [132.9111, 84.9889], "why": "overlaps W2"}]}
            """));
        Assert.Equal(new WallCorrection(119, new PlanPoint(132.9111, 84.9889), "overlaps W2", CorrectionKind.TrimEnd), Assert.Single(r.Corrections));
        var x = Assert.Throws<BuildDataException>(() => BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt",
             "corrections": [{"wall": "W1", "trim_end_to": [1, 2], "extend_end_to": [1, 3], "why": "both"}]}
            """)));
        Assert.Contains(x.Problems, p => p.Contains("one change per correction"));
    }

    private const string Why = "LS1.0 shows the classroom wall meeting the vestibule wall; the trace stopped 1.4 ft short";

    [Fact]
    public void A_correction_moves_a_walls_end_along_its_line_and_says_so()
    {
        var m = BuildData.Parse(Extracted());
        var (fixedModel, applied, refused) = BuildData.Correct(m, [new WallCorrection(0, new PlanPoint(21.5, 0), Why)]);
        Assert.Equal(new PlanPoint(21.5, 0), fixedModel.Walls[0].End);
        Assert.Equal(m.Walls[0].Start, fixedModel.Walls[0].Start);
        Assert.Equal(m.Walls.Skip(1), fixedModel.Walls.Skip(1));
        Assert.Equal($"corrected W0: end (20, 0) → (21.5, 0) (1.5 ft): {Why}", Assert.Single(applied));
        Assert.Empty(refused);
        Assert.Equal(new PlanPoint(20, 0), m.Walls[0].End);          // the data itself untouched
    }

    [Theory]
    [InlineData(0, 22.5, 0, "moves it 2.5 ft from the data's end, more than 2 ft")]
    [InlineData(0, 21, 0.5, "changes the wall's direction")]            // off its own line
    [InlineData(5, -0.5, 0, "changes the wall's direction")]            // a 1 ft wall turned back past its start
    [InlineData(7, 1, 1, "the data has no wall W7")]
    public void A_correction_that_moves_too_far_or_turns_the_wall_is_refused_and_not_applied(int wall, double x, double y, string words)
    {
        var data = BuildData.Parse(Extracted());
        var m = data with { Walls = [.. data.Walls, data.Walls[0] with { Id = 5, Start = new PlanPoint(0, 0), End = new PlanPoint(1, 0) }] };
        var (same, applied, refused) = BuildData.Correct(m, [new WallCorrection(wall, new PlanPoint(x, y), Why)]);
        Assert.Empty(applied);
        Assert.Contains(words, Assert.Single(refused));
        Assert.Equal(m.Walls, same.Walls);
    }

    [Fact]
    public void Two_corrections_of_one_wall_are_measured_from_the_datas_end_so_they_cant_add_up_past_2_ft()
    {
        var m = BuildData.Parse(Extracted());
        var (fixedModel, applied, refused) = BuildData.Correct(m, [new WallCorrection(0, new PlanPoint(21.5, 0), Why),
                                                                    new WallCorrection(0, new PlanPoint(23, 0), Why)]);
        Assert.Single(applied);
        Assert.Contains("moves it 3 ft from the data's end, more than 2 ft", Assert.Single(refused));
        Assert.Equal(new PlanPoint(21.5, 0), fixedModel.Walls[0].End);
    }

    [Fact]
    public void Every_number_in_the_words_has_a_decimal_point_on_a_machine_that_writes_a_comma()
    {
        var was = System.Globalization.CultureInfo.CurrentCulture;
        System.Globalization.CultureInfo.CurrentCulture = new System.Globalization.CultureInfo("de-DE");
        try
        {
            var m = BuildData.Parse(Extracted());
            var (_, applied, _) = BuildData.Correct(m, [new WallCorrection(0, new PlanPoint(21.5, 0), Why)]);
            Assert.Equal($"corrected W0: end (20, 0) → (21.5, 0) (1.5 ft): {Why}", applied.Single());
            var (_, _, refused) = BuildData.Correct(m, [new WallCorrection(0, new PlanPoint(22.5, 0), Why)]);
            Assert.Contains("moves it 2.5 ft", refused.Single());
            var twin = m.Walls[0] with { Id = 9, Start = new PlanPoint(15, 0.2), End = new PlanPoint(25, 0.2) };
            Assert.Equal("walls W0 and W9 overlap along 5 ft (2.4 in apart, centre to centre)", BuildData.WallOverlaps([.. m.Walls, twin]).Single().Words);
            var gap = BuildData.BoundaryGaps(m.Rooms[0], m.Walls.Where(w => w.Id != 0).ToList()).Single();
            Assert.StartsWith("9.46 ft from (0.34, 0.33) to (9.8, 0.33)", gap.Words);     // to the 0.02 ft sampling
            Assert.Contains("(12.5%)", BuildData.AreaOff(90, 80.0));
            Assert.Equal("Window 33.5\" x 48\" (LS1.0)", BuildData.OpeningTypeName("Window", 33.5, 48));
        }
        finally
        {
            System.Globalization.CultureInfo.CurrentCulture = was;
        }
    }

    [Theory]
    [InlineData(841.0, 841.0, false)]
    [InlineData(737.9, 734.1, false)]        // run 1's kitchen: 3.8 sq ft, 0.5%
    [InlineData(27.6, 27.1, false)]          // run 1's storage 28: 1.8%
    [InlineData(27.7, 27.1, true)]           // 2.2%
    [InlineData(1745.0, 1737.9, true)]       // 7.1 sq ft, 0.4%
    [InlineData(830.0, 841.0, true)]         // smaller too
    public void A_room_more_than_2_percent_or_5_sq_ft_off_the_sheet_is_area_off(double revit, double sheet, bool off)
    {
        Assert.Equal(off, BuildData.AreaOff(revit, sheet) is not null);
        Assert.Null(BuildData.AreaOff(10, null));
    }

    [Fact]
    public void A_room_the_sheet_gives_no_area_is_checked_against_its_boundary_and_says_so()
    {
        var m = BuildData.Parse(Extracted());
        var storage = m.Rooms[1];                                     // no area_sf; 9.48 x 9.34 inside its boundary
        Assert.Null(storage.AreaSf);
        Assert.Null(BuildData.RoomAreaOff(BuildData.Area(storage.Boundary) + 1, storage));
        var off = BuildData.RoomAreaOff(100, storage);
        Assert.NotNull(off);
        Assert.Contains("its boundary's (the sheet gives no area)", off);
        Assert.Contains("the sheet's 88.5", BuildData.RoomAreaOff(100, m.Rooms[0]));   // the sheet's, when it gives one
    }

    [Theory]
    [InlineData("2.0", null)]                                        // 2.0 is 2, as the extractor reads it
    [InlineData("null", "stats: doors says null, the data has 2")]
    [InlineData("\"2\"", "stats: doors says \"2\", the data has 2")]
    [InlineData("true", "stats: doors says true, the data has 2")]
    public void The_stats_are_checked_as_the_extractor_checks_them(string doors, string? words)
    {
        var data = Extracted();
        data["stats"]!["doors"] = JsonNode.Parse(doors);
        if (words is null)
            Assert.Equal(2, BuildData.Parse(data).Doors.Count);
        else
            Assert.Contains(words, Assert.Throws<BuildDataException>(() => BuildData.Parse(data)).Problems);
        var one = Extracted();
        one["stats"]!["windows"] = true;                              // one window: true is not 1
        Assert.Contains("stats: windows says true, the data has 1", Assert.Throws<BuildDataException>(() => BuildData.Parse(one)).Problems);
        data["stats"] = JsonValue.Create(5);
        Assert.Contains("stats: not an object", Assert.Throws<BuildDataException>(() => BuildData.Parse(data)).Problems);
        data["stats"] = null;
        Assert.Equal(2, BuildData.Parse(data).Doors.Count);
    }

    [Fact]
    public void The_request_reads_its_corrections_and_refuses_one_without_a_why()
    {
        var r = BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt",
             "corrections": [{"wall": "W16", "extend_end_to": [193.8667, 48.1667], "why": "the trace stopped short"}]}
            """));
        Assert.Equal(new WallCorrection(16, new PlanPoint(193.8667, 48.1667), "the trace stopped short"), Assert.Single(r.Corrections));
        var x = Assert.Throws<BuildDataException>(() => BuildRequest.Parse(JsonNode.Parse("""
            {"data": "d.json", "save_as": "o.rvt", "corrections": [{"wall": "16", "extend_end_to": [1, 2]}]}
            """)));
        Assert.Contains("correction 1: wall is \"16\", not a wall's mark (W16)", x.Problems);
        Assert.Contains("correction 1: no why (every correction to the data says why)", x.Problems);
    }

    [Fact]
    public void A_wall_the_data_stops_short_leaves_its_room_open_and_the_gap_is_named()
    {
        var m = BuildData.Parse(Extracted());
        Assert.All(m.Rooms, r => Assert.Empty(BuildData.BoundaryGaps(r, m.Walls)));      // the tiny box is closed
        // its south wall starting at x 2, not 0 (as the tracing stopped W16 short of W27): 1.67 ft open, W3 to W0
        var walls = m.Walls.Select(w => w.Id == 0 ? w with { Start = new PlanPoint(2, 0) } : w).ToList();
        var gap = Assert.Single(BuildData.BoundaryGaps(m.Rooms[0], walls));
        Assert.Equal((3, 0), (gap.WallBefore, gap.WallAfter));
        Assert.InRange(gap.Length, 1.667 - 0.05, 1.667 + 0.05);      // to the sampling step, 0.02 ft each end
        Assert.Equal(0.33, gap.From.Y, 9);
        Assert.Empty(BuildData.BoundaryGaps(m.Rooms[1], walls));
    }

    [Fact]
    public void Walls_drawn_along_each_other_are_named_and_walls_meeting_at_a_corner_are_not()
    {
        var m = BuildData.Parse(Extracted());
        Assert.Empty(BuildData.WallOverlaps(m.Walls));
        var twin = m.Walls[0] with { Id = 9, Start = new PlanPoint(15, 0.2), End = new PlanPoint(25, 0.2) };
        var o = Assert.Single(BuildData.WallOverlaps([.. m.Walls, twin]));
        Assert.Equal((0, 9, 5.0), (o.A, o.B, Math.Round(o.Length, 9)));
        Assert.Equal("walls W0 and W9 overlap along 5 ft (2.4 in apart, centre to centre)", o.Words);
    }

    [Fact]
    public void Existing_walls_go_in_the_first_phase_only_when_there_is_a_second()
    {
        Assert.Equal(0, BuildData.ExistingPhase(2, usePhases: true));
        Assert.Null(BuildData.ExistingPhase(1, usePhases: true));
        Assert.Null(BuildData.ExistingPhase(2, usePhases: false));
    }
}
