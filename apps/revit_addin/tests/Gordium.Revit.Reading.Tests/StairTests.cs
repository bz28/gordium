using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The stairs, step 4 (docs/revit/revit_interior_reading_design.md, section 7): each component run a flight,
/// read from what is drawn and checked against what was typed. Houses 2 and 3 drawn as fake Revit records
/// (InteriorDrawing.cs) must pass the interior conformance CI applies to the Revit recordings: house 2's risers,
/// treads, headroom and clear width as worked by hand; house 3's tall riser (drawn at the head, where Revit makes one)
/// not measured. Then each trap, one change at a time, must leave out exactly what it can't read, never a guess.</summary>
public sealed class StairTests
{
    private const string Two = "2_two_story_small_window";
    private const string Three = "3_tall_riser";

    private static JsonObject? Flight(InteriorReadResult r, string houseId) =>
        r.Interior["stairs"]?.AsArray().Select(x => x!.AsObject()).FirstOrDefault(x => x["id"]!.GetValue<string>() == "run-" + houseId);

    private static string? Note(InteriorReadResult r, string houseId, string field) =>
        r.Notes.FirstOrDefault(n => n.Part == "run-" + houseId && n.Field == field)?.Why;

    private static InteriorReadResult Read(FakeHouse h) => InteriorReader.Read(h.Model());

    // ---- the houses ---------------------------------------------------------------------------------------

    [Fact]
    public void House_2s_stair_reads_as_drawn_and_measures_as_worked_by_hand()
    {
        var house = FakeHouse.Draw(Two);
        var read = Read(house);
        var s1 = Flight(read, "s1")!;
        Assert.Equal(0.0, s1["bottom_elevation"]!.GetValue<double>(), 9);
        Assert.Equal(16, s1["nosings"]!.AsArray().Count);
        Assert.Equal(10.0, s1["nosings"]![15]![0]![2]!.GetValue<double>(), 9);              // the floor at the head
        Assert.NotEqual("open", s1["sides"]!["left"]!.ToString());
        Assert.Null(s1["handrails"]);                                                       // railings: step 5
        Assert.Contains("read with the guards", Note(read, "s1", "handrails"));
        Assert.Equal([], InteriorTests.Problems(house, read));
    }

    [Fact]
    public void House_3s_tall_riser_drawn_at_the_head_sends_no_nosings()
    {
        var house = FakeHouse.Draw(Three);
        var read = Read(house);
        var s = Flight(read, "s")!;
        Assert.Null(s["nosings"]);
        Assert.Contains("the floor at its head is 1.5 in from the run's top", Note(read, "s", "nosings"));
        Assert.Equal(-8.25, s["bottom_elevation"]!.GetValue<double>(), 9);                  // the foot agrees
        Assert.Equal("open", s["sides"]!["right"]!.GetValue<string>());                     // the guard: step 5
        var ev = read.Evidence["stairs"]!["run-s"]!;
        Assert.Equal(0.0, ev["head"]!.GetValue<double>(), 9);
        Assert.Equal(-0.125, ev["run_top"]!.GetValue<double>(), 9);
        Assert.Equal([], InteriorTests.Problems(house, read));                              // every stair measure not measured
    }

    [Fact]
    public void Under_turned_and_moved_shared_coordinates_the_stairs_measure_the_same()
    {
        var turn = Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0));
        foreach (var name in new[] { Two, Three })
        {
            var house = FakeHouse.Draw(name, turn);
            Assert.Equal([], InteriorTests.Problems(house, Read(house)));
        }
    }

    // ---- when no stair is read ----------------------------------------------------------------------------

    [Fact]
    public void Without_the_architects_tick_no_stair_is_read()
    {
        var house = FakeHouse.Draw(Two);
        house.ProjectMarks.Clear();
        var read = Read(house);
        Assert.Null(read.Interior["stairs"]);
        Assert.Contains("Gordium: These are all the stairs is not set on Project Information", read.StairsNotRead[0]);
        house.ProjectMarks[Marks.AllStairs.Guid] = new MarkValue(true, 0);                   // No
        Assert.Contains("is No on Project Information", Read(house).StairsNotRead[0]);
        house.ProjectMarks[Marks.AllStairs.Guid] = new MarkValue(false, 0);                  // never set: not No, not Yes
        Assert.Null(Read(house).Interior["stairs"]);
        Assert.Contains(InteriorTests.Problems(house, Read(house)), p => p.Contains("stair not read"));
    }

    [Fact]
    public void Nothing_found_is_never_none()
    {
        var house = FakeHouse.Draw(Two);
        house.Stairs.Clear();
        var read = Read(house);
        Assert.Null(read.Interior["stairs"]);                                                // never stairs: []
        Assert.StartsWith("No stairs are drawn", read.StairsNotRead[0]);
        var demolished = FakeHouse.Draw(Two);
        demolished.Stairs[0] = demolished.Stairs[0] with { PhaseDemolished = FakeHouse.LastPhase };
        Assert.Null(Read(demolished).Interior["stairs"]);
        var unread = FakeHouse.Draw(Two);
        var model = unread.Model();
        model = model with { Interior = model.Interior! with { Stairs = null } };
        Assert.Contains("the stairs couldn't be read", InteriorReader.Read(model).StairsNotRead);
    }

    public static TheoryData<string, string> Blockers() => new()
    {
        { "generic model", "GenericModel \"Basement stair\" is an in-place family" },
        { "not by component", "isn't made of runs and landings" },
        { "multistory", "one of a multistory stair" },
        { "closed workset", "Workset \"Basement\" is closed: a stair could be in it" },
        { "unloaded link", "isn't loaded: a stair could be in it" },
        { "link with stairs", "holds 2 stairs, railings or generic models" },
        { "coordination model", "coordination model(s) linked" },
    };

    [Theory]
    [MemberData(nameof(Blockers))]
    public void Anything_that_could_be_a_stair_not_walked_leaves_the_stairs_out(string what, string words)
    {
        var house = FakeHouse.Draw(Two);
        switch (what)
        {
            case "generic model": house.StairCandidates.Add(new("gm", "OST_GenericModel", "Basement stair", "an in-place family")); break;
            case "not by component": house.Stairs[0] = house.Stairs[0] with { IsByComponent = false }; break;
            case "multistory": house.Stairs[0] = house.Stairs[0] with { MultistoryStairsId = "77" }; break;
            case "closed workset": house.Worksets.Add(new WorksetRecord("w", "Basement", false)); break;
            case "unloaded link": house.Links.Add(new InteriorLink("l", "Stairs.rvt", false, null, 0, 0, false)); break;
            case "link with stairs": house.Links.Add(new InteriorLink("l", "Stairs.rvt", true, new RevitBox(new(900, 900, 0), new(901, 901, 1)), 0, 0, false, 2)); break;
            case "coordination model": house.CoordinationModels = 1; break;
        }
        var read = Read(house);
        Assert.Null(read.Interior["stairs"]);
        Assert.Contains(read.StairsNotRead, w => w.Contains(words));
        Assert.Contains(MarkingList.Build(house.Model()).StairBlockers, w => w.Contains(words));    // listed first
        // a demolished candidate isn't in the design checked
        if (what == "generic model")
        {
            house.StairCandidates[0] = house.StairCandidates[0] with { PhaseDemolished = FakeHouse.LastPhase };
            Assert.NotNull(Read(house).Interior["stairs"]);
        }
    }

    // ---- the nosings: drawn, checked against what was typed ---------------------------------------------------

    [Fact]
    public void A_typed_riser_or_tread_disagreeing_with_the_drawn_ones_sends_no_nosings()
    {
        var house = FakeHouse.Draw(Two);
        house.Stairs[0] = house.Stairs[0] with { ActualRiserHeight = 7.0 / 12 };
        var read = Read(house);
        Assert.Null(Flight(read, "s1")!["nosings"]);
        Assert.Contains("riser 1 is drawn 7.5 in, but the stair's Actual Riser Height is 7 in", Note(read, "s1", "nosings"));
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("s1 stair_riser_height not measured"));

        house = FakeHouse.Draw(Two);
        house.Stairs[0] = house.Stairs[0] with { ActualTreadDepth = 11.0 / 12 };
        Assert.Contains("Actual Tread Depth is 11 in", Note(Read(house), "s1", "nosings"));

        house = FakeHouse.Draw(Two);                         // within 1/16 in: drawing noise, read
        house.Stairs[0] = house.Stairs[0] with { ActualRiserHeight = (7.5 + 1.0 / 32) / 12 };
        Assert.NotNull(Flight(Read(house), "s1")!["nosings"]);

        house = FakeHouse.Draw(Two);
        house.Stairs[0] = house.Stairs[0] with { ActualRiserHeight = null };
        Assert.Contains("typed riser height or tread depth couldn't be read", Note(Read(house), "s1", "nosings"));
    }

    [Fact]
    public void The_runs_own_counts_and_ends_must_agree()
    {
        var house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { RisersNumber = 17 });
        Assert.Contains("the run says 17", Note(Read(house), "s1", "nosings"));
        house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { TreadsNumber = 14 });
        Assert.Contains("16 tread tops, but the run says it has 14", Note(Read(house), "s1", "nosings"));
        house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { EndsWithRiser = false });
        Assert.Contains("16 tread tops, but the run says it has 15", Note(Read(house), "s1", "nosings"));
        house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { BeginsWithRiser = false });
        Assert.Contains("begin and end with a riser", Note(Read(house), "s1", "nosings"));
    }

    [Fact]
    public void The_last_risers_top_at_the_runs_top_is_the_heads_edge_never_a_tread()
    {
        // Revit 2027.4, trial step 4 run 1: a run ending with a riser has one top face more than its treads, at its top
        var read = Read(FakeHouse.Draw(Two));
        var ev = read.Evidence["stairs"]!["run-s1"]!;
        Assert.Equal(16, ev["tread_groups"]!.AsArray().Count);
        Assert.Equal(9.75, ev["head_riser_top"]!["z"]!.GetValue<double>(), 9);             // run 2's numbers
        Assert.Equal(12.5, ev["back"]!.GetValue<double>(), 9);                              // the last riser's line
        var nosings = Flight(read, "s1")!["nosings"]!.AsArray();
        Assert.Equal(16, nosings.Count);
        Assert.Equal(10.0, nosings[15]![0]![2]!.GetValue<double>(), 9);                     // the floor at the head
        // a face more than the treads that isn't a riser board's top is still one too many: as deep as a tread,
        // or above the run's top
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        // a top 6 in deep there (a step, not a riser board)
        house.SetRun("s1", r => r with { Faces = [.. r.Faces!, .. house.StairBox(st, 12.5, 13.0, -1.5, 1.5, 9.5, 9.75)] });
        Assert.Contains("16 tread tops, but the run says it has 15", Note(Read(house), "s1", "nosings"));
        house = FakeHouse.Draw(Two);                         // above the run's top
        house.SetRun("s1", r => r with { TopElevation = 9.5 });
        Assert.Contains("16 tread tops, but the run says it has 15", Note(Read(house), "s1", "nosings"));
    }

    [Fact]
    public void A_winder_a_curved_face_or_a_sloped_tread_isnt_read_but_the_flight_is_still_sent()
    {
        var house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { Style = "Winder" });
        var read = Read(house);
        Assert.NotNull(Flight(read, "s1"));                                                 // never dropped
        Assert.Null(Flight(read, "s1")!["nosings"]);
        Assert.Contains("a winder run", Note(read, "s1", "nosings"));

        house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { Faces = [.. r.Faces!, new SurfaceRecord(false, new(0, 0, 0), [], [new(0, 0, 0)])] });
        Assert.Contains("curved face", Note(Read(house), "s1", "nosings"));

        house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { Faces = null, GeometryFailed = true });
        Assert.Contains("geometry couldn't be read", Note(Read(house), "s1", "sides"));
    }

    [Fact]
    public void A_riser_top_hidden_under_its_tread_is_inside_the_run_not_a_tread()
    {
        // an assembled stair's riser board reaching up under the tread: its top face touches the tread's underside
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        double t = 10.0 / 12, r = 7.5 / 12;
        var riser = house.StairBox(st, 2 * t, 2 * t + 1.0 / 12, -1.5, 1.5, 2 * r, 3 * r - 1.0 / 12);   // under tread 3's front
        house.SetRun("s1", x => x with { Faces = [.. x.Faces!, .. riser] });
        Assert.Equal([], InteriorTests.Problems(house, Read(house)));
    }

    [Fact]
    public void The_floor_at_the_foot_must_agree_with_the_runs_base()
    {
        var house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with { Near = r.Near!.Where(e => e.UniqueId != "foot-s1").ToList() });
        var read = Read(house);
        Assert.Null(Flight(read, "s1")!["bottom_elevation"]);
        Assert.Contains("no floor or landing top was found", Note(read, "s1", "bottom_elevation"));
        Assert.Null(Flight(read, "s1")!["nosings"]);                                        // the first riser can't be checked

        house = FakeHouse.Draw(Two);                         // the floor an inch high: a short first riser
        var st = house.StairDrawing("s1");
        house.SetRun("s1", r => r with
        {
            Near = [.. r.Near!.Where(e => e.UniqueId != "foot-s1"),
                    FakeHouse.Boxed(new("foot2", "OST_Floors", "Floor", Faces: house.StairBox(st, -3, 0, -1.5, 1.5, -1, 1.0 / 12)))],
        });
        Assert.Contains("1 in from the run's base", Note(Read(house), "s1", "bottom_elevation"));

        house = FakeHouse.Draw(Two);                         // a floor under half the stair's width only
        house.SetRun("s1", r => r with
        {
            Near = [.. r.Near!.Where(e => e.UniqueId != "foot-s1"),
                    FakeHouse.Boxed(new("foot2", "OST_Floors", "Floor", Faces: house.StairBox(st, -3, 0, 0, 1.5, -1, 0)))],
        });
        Assert.Contains("no one floor top covers the stair's whole width", Note(Read(house), "s1", "bottom_elevation"));
    }

    [Fact]
    public void A_loaded_link_reaching_the_flight_leaves_what_is_around_it_out()
    {
        var house = FakeHouse.Draw(Two);
        var near = house.Stairs[0].Runs[0].Near!.First(e => e.UniqueId == "head-s1").Box!;
        house.Links.Add(new InteriorLink("link", "Structure.rvt", true, near, 0, 0, false));
        var read = Read(house);
        foreach (var field in new[] { "bottom_elevation", "nosings", "sides", "overhead" })
            Assert.Contains("\"Structure.rvt\" reaches over this flight", Note(read, "s1", field));
        Assert.NotNull(Flight(read, "s1"));
    }

    // ---- the sides ---------------------------------------------------------------------------------------------

    [Fact]
    public void A_wall_just_inside_the_tread_ends_narrows_the_width()
    {
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        // looking up the stair, its right is a < -1.5 ft: a wall face 2 in inside the right tread ends
        house.AddNear("s1", new("partition", "OST_Walls", "Partition", Faces: house.StairBox(st, -1, 13.5, -1.5 - 0.5, -1.5 + 2.0 / 12, 0, 17)));
        Assert.Contains(InteriorTests.Problems(house, Read(house)), p => p.Contains("s1 stair_clear_width = 34.0, expected 36.0"));
    }

    [Fact]
    public void Anything_but_a_wall_beside_the_flight_leaves_the_sides_out()
    {
        var house = FakeHouse.Draw(Three);                   // its right side is open
        var st = house.StairDrawing("s");
        house.AddNear("s", new("rail", "OST_StairsRailing", "Guard", Faces: house.StairBox(st, 0, 9.75, -1.6, -1.5, -8, 0)));
        var read = Read(house);
        Assert.Null(Flight(read, "s")!["sides"]);
        Assert.Contains("railings are read with the guards", Note(read, "s", "sides"));

        house = FakeHouse.Draw(Three);
        house.AddNear("s", new("col", "OST_Columns", "Column", Faces: house.StairBox(st, 4, 4.5, -1.9, -1.6, -8.25, 0)));
        Assert.Contains("Columns \"Column\" stands on its right side", Note(Read(house), "s", "sides"));

        house = FakeHouse.Draw(Three);                       // furniture too: in the way (review round 1)
        house.AddNear("s", new("chair", "OST_Furniture", "Chair", Faces: house.StairBox(st, 4, 4.5, -1.9, -1.6, -6, -3)));
        Assert.Contains("Furniture \"Chair\" stands on its right side", Note(Read(house), "s", "sides"));

        house = FakeHouse.Draw(Three);                       // something behind the wall is hidden by it
        house.AddNear("s", new("pipe", "OST_PipeCurves", "Pipe", Faces: house.StairBox(st, 4, 4.5, 1.6, 1.9, -8, -7)));
        Assert.NotNull(Flight(Read(house), "s")!["sides"]);
    }

    [Fact]
    public void A_fixture_in_the_headroom_or_the_width_counts_review_round_1()
    {
        // a pendant light (Lighting Fixtures: not a room's ceiling, but in the stairway's headroom, R311.7.2) over house
        // 2's flight, its underside 84 in over the line of nosings at 5.5 ft up the run
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        house.AddNear("s1", new("light", "OST_LightingFixtures", "Pendant", Faces: house.StairBox(st, 5, 5.5, -0.5, 0.5, 11.75, 12)));
        Assert.Contains(InteriorTests.Problems(house, Read(house)), p => p.Contains("s1 stair_headroom = 84.0, expected 85.5"));
        // a wall cabinet (Casework) standing 2 in into the flight's width on its right, at head height
        house = FakeHouse.Draw(Two);
        house.AddNear("s1", new("cabinet", "OST_Casework", "Wall cabinet", Faces: house.StairBox(st, 4, 6, -1.75, -1.5 + 2.0 / 12, 6, 8)));
        var read = Read(house);
        Assert.Null(Flight(read, "s1")!["sides"]);
        Assert.Contains("Casework \"Wall cabinet\" stands on its right side", Note(read, "s1", "sides"));
    }

    [Fact]
    public void A_floor_at_the_head_reaching_over_the_last_tread_sends_no_nosings_review_round_1()
    {
        // the floor at house 2's head with its edge 1.5 in over the last tread: that tread is 8.5 in nosing to
        // nosing, never the 10 in the riser line gives
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        house.SetRun("s1", r => r with
        {
            Near = [.. r.Near!.Where(e => e.UniqueId != "head-s1"),
                    FakeHouse.Boxed(new("head2", "OST_Floors", "Landing", Faces: house.StairBox(st, 12.5 - 1.5 / 12, 15.5, -1.5, 1.5, 10 - 1.0 / 12, 10)))],
        });
        var read = Read(house);
        Assert.Null(Flight(read, "s1")!["nosings"]);
        Assert.Contains("Floors \"Landing\") reaches back over the last tread", Note(read, "s1", "nosings"));
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("s1 stair_tread_depth not measured"));
    }

    [Fact]
    public void The_upper_floor_around_the_stairwell_opening_is_read_as_a_real_model_has_it_review_round_2()
    {
        // house 2 is drawn with one upper floor at the head, the stairwell an opening in it, its edge on the riser line
        var house = FakeHouse.Draw(Two);
        var floor = house.Stairs[0].Runs[0].Near!.Single(e => e.UniqueId == "head-s1");
        Assert.Contains(floor.Faces!, f => f.Loops.Count == 2);                             // an outline and its opening
        var read = Read(house);
        Assert.Equal(16, Flight(read, "s1")!["nosings"]!.AsArray().Count);
        Assert.NotNull(Flight(read, "s1")!["sides"]);                                       // its box spans the opening
        Assert.Equal([], InteriorTests.Problems(house, read));
        // the opening stopping 1 1/2 in short of the riser line: the floor reaches over the last tread
        var st = house.StairDrawing("s1");
        List<(double X, double Y)> outer = [.. new[] { (-1.67, -2.0), (15.5, -2.0), (15.5, 2.0), (-1.67, 2.0) }.Select(p => FakeHouse.StairAt(st, p.Item1, p.Item2))];
        List<(double X, double Y)> hole = [.. new[] { (1.67, -1.5), (12.5 - 1.5 / 12, -1.5), (12.5 - 1.5 / 12, 1.5), (1.67, 1.5) }.Select(p => FakeHouse.StairAt(st, p.Item1, p.Item2))];
        house.SetRun("s1", r => r with
        {
            Near = [.. r.Near!.Where(e => e.UniqueId != "head-s1"), FakeHouse.Boxed(new("short", "OST_Floors", "Upper floor", Faces: house.PrismWithHole(outer, hole, 9, 10)))],
        });
        Assert.Contains("reaches back over the last tread", Note(Read(house), "s1", "nosings"));
    }

    public static TheoryData<string> Unreadable() => ["mesh with a box", "failed with no box", "a face with points and no loops"];

    [Theory]
    [MemberData(nameof(Unreadable))]
    public void Anything_unreadable_at_the_heads_height_over_the_last_tread_sends_no_nosings_review_round_2(string what)
    {
        // a mesh landing nosing (its box ends at the riser line, so the floor's strip past it says nothing)
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        var nose = house.StairBox(st, 12.5 - 1.5 / 12, 12.5, -1.5, 1.5, 10 - 1.0 / 12, 10);
        var e = FakeHouse.Boxed(new NearbyElement("nose", "OST_Floors", "Nosing", Faces: nose));
        e = what switch
        {
            "mesh with a box" => e with { Faces = null, GeometryFailed = true },
            "failed with no box" => e with { Faces = null, GeometryFailed = true, Box = null },
            _ => e with { Faces = [new SurfaceRecord(true, house.Fake.Place(0, 0, 1) - house.Fake.Place(0, 0, 0), [], nose[0].Points)] },
        };
        house.SetRun("s1", r => r with { Near = [.. r.Near!, e] });
        var read = Read(house);
        Assert.Null(Flight(read, "s1")!["nosings"]);
        Assert.Contains("Floors \"Nosing\"", Note(read, "s1", "nosings"));
    }

    [Fact]
    public void A_wall_that_doesnt_run_the_whole_flight_leaves_the_sides_out()
    {
        var house = FakeHouse.Draw(Two);
        house.SetRun("s1", r => r with
        {
            Near = r.Near!.Select(e => e.UniqueId == "wall-s1-left"
                ? FakeHouse.Boxed(e with { Faces = house.StairBox(house.StairDrawing("s1"), -1, 6, 1.5, 2, 0, 17) }) : e).ToList(),
        });
        var read = Read(house);
        Assert.Null(Flight(read, "s1")!["sides"]);
        Assert.Contains("doesn't run the whole flight", Note(read, "s1", "sides"));
    }

    [Fact]
    public void The_stairs_own_support_counts_only_when_it_rises_into_the_width()
    {
        var house = FakeHouse.Draw(Three);
        var st = house.StairDrawing("s");
        var i = house.StairIndex("s");
        house.Stairs[i] = house.Stairs[i] with { Supports = ["stringer"] };
        house.AddNear("s", new("stringer", "OST_StairsSupports", "Stringer", Faces: house.StairBox(st, -0.5, 9.75, -1.625, -1.5, -8.5, -7.5)));
        Assert.Equal("open", Flight(Read(house), "s")!["sides"]!["right"]!.GetValue<string>());   // outside the treads, low
        house.SetRun("s", r => r with { Near = r.Near!.Where(e => e.UniqueId != "stringer").ToList() });
        house.AddNear("s", new("stringer", "OST_StairsSupports", "Stringer", Faces: house.StairBox(st, -0.5, 9.75, -1.625, -1.4, -8.5, -7.5)));
        Assert.Contains("support", Note(Read(house), "s", "sides"));                        // over the treads
    }

    // ---- what is overhead ----------------------------------------------------------------------------------

    [Fact]
    public void A_beam_over_the_flight_is_its_headroom()
    {
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        // a beam across the flight from 5 to 5.5 ft up the run, its underside 11.75 ft up: 84 in over the line of
        // nosings at 5.5 ft (66 in: 7.5 + 0.75 x 66 = 57 in; 141 - 57)
        house.AddNear("s1", new("beam", "OST_StructuralFraming", "Beam", Faces: house.StairBox(st, 5, 5.5, -2, 2, 11.75, 13)));
        Assert.Contains(InteriorTests.Problems(house, Read(house)), p => p.Contains("s1 stair_headroom = 84.0, expected 85.5"));
    }

    [Fact]
    public void Anything_over_the_flight_that_cant_be_read_exactly_leaves_the_overhead_out()
    {
        foreach (var (element, words) in new (Func<FakeHouse, NearbyElement>, string)[]
                 {
                     (h => new("m", "OST_Mass", "Mass", Faces: h.StairBox(h.StairDrawing("s1"), 3, 4, -1, 1, 12, 13)), "a category Gordium doesn't read"),
                     (h => new("d", "OST_DuctCurves", "Duct", Faces: h.StairBox(h.StairDrawing("s1"), 3, 4, -1, 1, 12, 13)) { GeometryFailed = true }, "couldn't be read"),
                     (h => new("x", "OST_StructuralFraming", "Beam", Faces: h.StairBox(h.StairDrawing("s1"), 3, 4, -1, 1, 1, 13)), "crosses the flight"),
                     (h => new("hr", "OST_RailingHandRail", "Handrail", Faces: h.StairBox(h.StairDrawing("s1"), 0, 12.5, -1.5, -1.2, 3.5, 3.6)), "a railing"),
                 })
        {
            var house = FakeHouse.Draw(Two);
            house.AddNear("s1", element(house));
            var read = Read(house);
            Assert.Null(Flight(read, "s1")!["overhead"]);
            Assert.Contains(words, Note(read, "s1", "overhead"));
        }
        var empty = FakeHouse.Draw(Two);
        empty.SetRun("s1", r => r with { Near = r.Near!.Where(e => !e.UniqueId.StartsWith("over-", StringComparison.Ordinal) && e.UniqueId != "head-s1").ToList() });
        Assert.Equal("nothing was found over it", Note(Read(empty), "s1", "overhead"));
    }

    [Fact]
    public void A_floors_stairwell_opening_is_taken_out_exactly()
    {
        // the floor over house 2's stair with an opening over all but its first 2 ft: only that strip is overhead
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        house.SetRun("s1", r => r with { Near = r.Near!.Where(e => !e.UniqueId.StartsWith("over-", StringComparison.Ordinal) && e.UniqueId != "head-s1").ToList() });
        var outer = new[] { (-2.0, -2.0), (14.0, -2.0), (14.0, 2.0), (-2.0, 2.0) }.Select(p => FakeHouse.StairAt(st, p.Item1, p.Item2)).ToList();
        var hole = new[] { (2.0, -1.5), (13.0, -1.5), (13.0, 1.5), (2.0, 1.5) }.Select(p => FakeHouse.StairAt(st, p.Item1, p.Item2)).ToList();
        var under = new SurfaceRecord(true, house.Fake.Place(0, 0, -1) - house.Fake.Place(0, 0, 0),
            [outer.Select(p => new LoopCurve(house.Fake.Place(p.X, p.Y, 9), true)).ToList(), hole.Select(p => new LoopCurve(house.Fake.Place(p.X, p.Y, 9), true)).ToList()],
            outer.Select(p => house.Fake.Place(p.X, p.Y, 9)).ToList());
        house.AddNear("s1", new("floor", "OST_Floors", "Upper floor", Faces: [under]));
        var over = Flight(Read(house), "s1")!["overhead"]!.AsArray();
        var area = over.Select(piece => piece!.AsArray().Select(p => new P2(p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList())
            .Sum(PlanGeometry.Area);
        Assert.Equal(2.0 * 3.0, area, 9);                    // s 0..2 across the 3 ft width; the opening, nothing
        Assert.Contains(InteriorTests.Problems(house, Read(house)), p => p.Contains("s1 stair_headroom not measured"));   // the rest open to the sky
    }

    [Fact]
    public void Subtracting_a_hole_leaves_exactly_the_rest()
    {
        List<P2> square = [new(0, 0), new(4, 0), new(4, 4), new(0, 4)];
        List<P2> hole = [new(1, 1), new(3, 1), new(3, 3), new(1, 3)];
        var left = PlanGeometry.Subtract([square], hole)!;
        Assert.Equal(12.0, left.Sum(PlanGeometry.Area), 12);
        Assert.Equal(16.0, PlanGeometry.Subtract([square], [new(5, 5), new(6, 5), new(6, 6)])!.Sum(PlanGeometry.Area), 12);
        Assert.Empty(PlanGeometry.Subtract([hole], square)!);
    }
}
