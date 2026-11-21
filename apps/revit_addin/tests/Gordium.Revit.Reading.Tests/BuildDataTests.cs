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

    [Theory]
    // facing, swing, toggle -> flip: with the toggle on (the stock families' leaf opens away from the facing) a facing
    // pointing the way the door should swing is flipped
    [InlineData(0, 1, 0, 1, true, true)]
    [InlineData(0, -1, 0, 1, true, false)]
    [InlineData(0, 1, 0, 1, false, false)]
    [InlineData(0, -1, 0, 1, false, true)]
    [InlineData(1, 0, 0, 1, true, false)]     // square to the swing: left as it is
    public void A_door_is_flipped_to_open_the_way_the_data_swings(double fx, double fy, double sx, double sy, bool opposite, bool flip) =>
        Assert.Equal(flip, BuildData.FlipFacing(new(fx, fy), new(sx, sy), opposite));

    [Theory]
    // the tiny script's single door: centre (5, 0), hinge (6.5, 0), so its hinge is +x of its centre
    [InlineData(1, 0, true, true)]
    [InlineData(-1, 0, true, false)]
    [InlineData(1, 0, false, false)]
    [InlineData(-1, 0, false, true)]
    public void A_single_door_is_hinged_at_the_datas_jamb(double hx, double hy, bool opposite, bool flip) =>
        Assert.Equal(flip, BuildData.FlipHand(new(hx, hy), new(5, 0), new(6.5, 0), opposite));

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
        // the five "Highlighted walls overlap" warnings of run 1, each a pair the data draws along each other
        Assert.Equal([(2, 119), (27, 120), (28, 121), (32, 105), (33, 34)], BuildData.WallOverlaps(m.Walls).Select(o => (o.A, o.B)));
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
