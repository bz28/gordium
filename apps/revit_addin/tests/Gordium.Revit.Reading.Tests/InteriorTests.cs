using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The interior reader, step 3 (docs/revit/revit_interior_reading_design.md, section 7): rooms and marked
/// escape windows. The houses of the step drawn as fake Revit records (InteriorDrawing.cs) must pass the interior
/// conformance check the recordings must pass in CI (<c>model_measurement.interior.recordings</c>: every measure of
/// the step equal to the hand-worked one, every other not measured); then each of Revit's traps, one change at a
/// time, must leave out exactly what it can't read, never send a guess. That Revit's API gives what the records say
/// is the Windows trial's (the recordings, README).</summary>
public sealed class InteriorTests
{
    private const string Ft = "ft";

    private static JsonObject? Room(InteriorReadResult r, string houseId) =>
        r.Interior["rooms"]?.AsArray().Select(x => x!.AsObject()).FirstOrDefault(x => x["id"]!.GetValue<string>() == FakeHouse.Uid(houseId));

    private static JsonObject? Opening(InteriorReadResult r, string houseId) =>
        r.Interior["openings"]?.AsArray().Select(x => x!.AsObject()).FirstOrDefault(x => x["id"]!.GetValue<string>() == FakeHouse.Uid(houseId));

    private static string? Note(InteriorReadResult r, string houseId, string field) =>
        r.Notes.FirstOrDefault(n => n.Part == FakeHouse.Uid(houseId) && n.Field == field)?.Why;

    private static List<string> Problems(FakeHouse house, InteriorReadResult read)
    {
        var path = Path.Combine(Path.GetTempPath(), $"gordium_interior_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, house.Recording(read).ToJsonString());
        try
        {
            return JsonNode.Parse(Env.RunModule("model_measurement.interior.recordings", "check", path))!.AsArray()
                .Select(p => p!.GetValue<string>()).ToList();
        }
        finally
        {
            File.Delete(path);
        }
    }

    // ---- the houses of the step, end to end ---------------------------------------------------------------------

    public static TheoryData<string> Houses() => ["1_ranch_compliant", "2_two_story_small_window", "5_basement_window_well"];

    [Theory]
    [MemberData(nameof(Houses))]
    public void Each_house_of_the_step_read_from_its_drawing_measures_as_worked_by_hand(string name)
    {
        var house = FakeHouse.Draw(name);
        var read = InteriorReader.Read(house.Model());
        Assert.Empty(read.RoomsNotRead);
        Assert.Empty(read.OpeningsNotRead);
        Assert.Equal(Ft, read.Interior["units"]!.GetValue<string>());
        Assert.Null(read.Interior["stairs"]);                 // later steps: not read, never "none"
        Assert.Null(read.Interior["doors"]);
        Assert.Null(read.Interior["guards"]);
        Assert.Null(read.Interior["has_none"]);
        Assert.Equal([], Problems(house, read));
    }

    [Fact]
    public void A_house_under_turned_and_moved_shared_coordinates_measures_the_same()
    {
        // true north turned 30 degrees and the survey point 875,000 ft out and 400 ft up: every point turned once
        var turn = Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0));
        foreach (var name in new[] { "1_ranch_compliant", "2_two_story_small_window", "5_basement_window_well" })
        {
            var house = FakeHouse.Draw(name, turn);
            var read = InteriorReader.Read(house.Model());
            Assert.Equal([], Problems(house, read));
            if (name == "5_basement_window_well")
                Assert.Equal(-8.0, Room(read, "bbed")!["floor_elevation"]!.GetValue<double>(), 9);   // drawn in shared: internal -408
        }
    }

    [Fact]
    public void A_short_jog_in_a_room_far_out_in_survey_coordinates_is_kept()
    {
        // review round 1: the outline was cleaned with a tolerance grown by the coordinates themselves (0.77 sq ft at
        // 875,000 ft), so a 6 in x 1 ft notch vanished and a 99.5 sq ft room was sent as 100
        var turn = Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0));
        var house = FakeHouse.Draw("1_ranch_compliant", turn);
        var i = house.RoomIndex("bed1");
        (double X, double Y)[] notched = [(0, 0), (4.5, 0), (4.5, 0.5), (5.5, 0.5), (5.5, 0), (10, 0), (10, 10), (0, 10)];
        const double X0 = 875_000.25, Y0 = -12_345.5;                 // the room drawn there in shared coordinates
        var loop = notched.Select((p, k) => new BoundarySegmentRecord(house.Fake.Place(X0 + p.X, Y0 + p.Y, 0),
            house.Fake.Place(X0 + notched[(k + 1) % notched.Length].X, Y0 + notched[(k + 1) % notched.Length].Y, 0), true, "wall-0-ymin")).ToList();
        house.Rooms[i] = house.Rooms[i] with { Boundary = [loop] };
        var floor = Room(InteriorReader.Read(house.Model()), "bed1")!["floor"]!.AsArray()
            .Select(p => new P2(p![0]!.GetValue<double>(), p[1]!.GetValue<double>())).ToList();
        Assert.Equal(8, floor.Count);
        double area = 0;
        for (var k = 1; k < floor.Count - 1; k++)
            area += P2.Cross(floor[k] - floor[0], floor[k + 1] - floor[0]) / 2;
        Assert.Equal(99.5, Math.Abs(area), 6);
    }

    [Fact]
    public void The_sill_line_check_is_recorded_as_evidence()
    {
        var read = InteriorReader.Read(FakeHouse.Draw("1_ranch_compliant").Model());
        var w1 = read.Evidence[FakeHouse.Uid("w1")]!;
        Assert.Equal(2.5, w1["sill_line"]!.GetValue<double>(), 9);
        Assert.Equal(2.5, w1["wall_opening_bottom"]!.GetValue<double>(), 9);
        Assert.Equal(26.0 / 12, w1["placed"]!["width"]!.GetValue<double>(), 9);
        Assert.Null(read.Evidence[FakeHouse.Uid("w3")]);      // not confirmed: no clear opening to check
    }

    // ---- every room counts ------------------------------------------------------------------------------------

    [Fact]
    public void An_enclosed_area_with_no_room_leaves_rooms_out_and_is_listed_first()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.Areas.Add(new EnclosedArea("Level 0", 24.0, false, new Xyz(30, 3, 0)));
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["rooms"]);
        Assert.Contains(read.RoomsNotRead, w => w.StartsWith("An enclosed area on Level 0 has no Room (24 sq ft"));
        Assert.NotNull(read.Interior["openings"]);           // a missed window can only fail: openings still read
        var list = MarkingList.Build(house.Model());
        Assert.StartsWith("An enclosed area on Level 0 has no Room", list.RoomBlockers[0]);
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
        Assert.Contains(list.Summary, s => s.Contains("could hide a room"));
    }

    [Fact]
    public void Enclosed_areas_not_read_leave_rooms_out()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var model = house.Model() with { Interior = house.Model().Interior! with { EnclosedAreas = null } };
        Assert.Null(InteriorReader.Read(model).Interior["rooms"]);
    }

    [Fact]
    public void An_unplaced_room_a_closed_workset_or_an_unloaded_link_leaves_rooms_out()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.MarkedIndex("living");
        house.Marked[i] = house.Marked[i] with { Placement = RoomPlacement.Unplaced };
        Assert.Null(InteriorReader.Read(house.Model()).Interior["rooms"]);

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Worksets.Add(new WorksetRecord("w9", "Upper floor", false));
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["rooms"]);
        Assert.Contains("Workset \"Upper floor\" is closed: a room could be in it (open it)", read.RoomsNotRead);
        Assert.NotNull(read.Interior["openings"]);

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Links.Add(new InteriorLink("link-1", "Structure.rvt", false, null, 0, 0, false));
        Assert.Null(InteriorReader.Read(house.Model()).Interior["rooms"]);

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Links.Add(new InteriorLink("link-1", "Neighbour.rvt", true, new RevitBox(new(500, 500, 0), new(510, 510, 10)), 2, 0, false));
        Assert.Contains(InteriorReader.Read(house.Model()).RoomsNotRead, w => w.Contains("holds 2 Rooms"));
    }

    [Fact]
    public void Windows_in_a_linked_model_leave_openings_out()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.Links.Add(new InteriorLink("link-1", "Windows.rvt", true, new RevitBox(new(500, 500, 0), new(510, 510, 10)), 0, 3, false));
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["openings"]);
        Assert.NotNull(read.Interior["rooms"]);              // the link is far from every room
    }

    [Fact]
    public void A_loaded_link_reaching_over_a_room_leaves_its_floor_and_ceilings_out()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.Links.Add(new InteriorLink("link-1", "Structure.rvt", true, new RevitBox(new(1, 1, -2), new(5, 5, 12)), 0, 0, false));
        var read = InteriorReader.Read(house.Model());
        var bed1 = Room(read, "bed1")!;
        Assert.Null(bed1["floor"]);
        Assert.Null(bed1["floor_elevation"]);
        Assert.Null(bed1["ceilings"]);
        Assert.Contains("\"Structure.rvt\" reaches over this room", Note(read, "bed1", "floor"));
        Assert.NotNull(Room(read, "bed2")!["floor"]);         // a room it doesn't reach
    }

    [Fact]
    public void Nothing_drawn_is_never_none()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.Marked.Clear();
        var read = InteriorReader.Read(house.Model());
        Assert.Null(read.Interior["rooms"]);                  // never rooms: [] (a house not drawn read as none)
        Assert.Null(read.Interior["openings"]);
        Assert.Null(InteriorReader.Read(new RevitModel { Document = "x" }).Interior["rooms"]);   // inside not read
    }

    [Fact]
    public void An_unmarked_room_is_sent_with_no_sleeping_flag_so_no_room_is_read()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.MarkedIndex("living");
        house.Marked[i] = house.Marked[i] with { Instance = new Dictionary<Guid, MarkValue>() };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Room(read, "living")!["sleeping"]);
        Assert.Contains(Problems(house, read), p => p.Contains("sleeping_room not read"));
    }

    // ---- a room's floor -----------------------------------------------------------------------------------------

    [Fact]
    public void A_floor_is_one_loop_of_straight_segments_with_nothing_inside_it_unbounded()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.RoomIndex("bed1");
        var loop = house.Rooms[i].Boundary![0];
        house.Rooms[i] = house.Rooms[i] with { Boundary = [loop, loop.Take(3).ToList()] };     // a column inside it
        Assert.Contains("2 boundary loops", Note(InteriorReader.Read(house.Model()), "bed1", "floor"));

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Rooms[i] = house.Rooms[i] with { Boundary = [loop.Select((s, k) => k == 1 ? s with { IsLine = false } : s).ToList()] };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Room(read, "bed1")!["floor"]);
        Assert.Contains("curved segment", Note(read, "bed1", "floor"));

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Rooms[i] = house.Rooms[i] with
        {
            Inside = [new NearbyElement("wall-x", "OST_Walls", "Partition"), new NearbyElement("bed", "OST_Furniture", "Bed"),
                      new NearbyElement("w1-frame", "OST_Windows", Host: "wall-0-ymin")],
        };
        read = InteriorReader.Read(house.Model());
        Assert.Null(Room(read, "bed1")!["floor"]);            // the partition set not to bound rooms
        Assert.Contains("Walls \"Partition\"", Note(read, "bed1", "floor"));
        Assert.DoesNotContain("Bed", Note(read, "bed1", "floor"));          // furniture changes nothing
        Assert.DoesNotContain("Windows", Note(read, "bed1", "floor"));      // nor a window in a wall bounding it

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Rooms[i] = house.Rooms[i] with { Inside = [new NearbyElement("bed", "OST_Furniture", "Bed")] };
        Assert.Equal([], Problems(house, InteriorReader.Read(house.Model())));   // a furnished bedroom measures the same

        house = FakeHouse.Draw("1_ranch_compliant");
        house.Rooms[i] = house.Rooms[i] with { Inside = null };
        Assert.Null(Room(InteriorReader.Read(house.Model()), "bed1")!["floor"]);
    }

    [Fact]
    public void A_floor_elevation_is_sent_only_when_one_slab_top_under_the_whole_room_agrees()
    {
        string? Elevation(FakeHouse h) => Note(InteriorReader.Read(h.Model()), "bed1", "floor_elevation");
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.RoomIndex("bed1");
        Assert.Null(Elevation(house));

        house.Rooms[i] = house.Rooms[i] with { Under = [] };
        Assert.Contains("no slab top was found", Elevation(house));

        house = FakeHouse.Draw("1_ranch_compliant");      // the slab drawn an inch high
        house.Rooms[i] = house.Rooms[i] with
        {
            Under = [new NearbyElement("slab", "OST_Floors", "Floor", Faces: house.Prism([(-1, -1), (30, -1), (30, 30), (-1, 30)], -1, 1.0 / 12))],
        };
        Assert.Contains("1 in from the floor", Elevation(house));

        house = FakeHouse.Draw("1_ranch_compliant");      // two slabs at two heights under it
        house.Rooms[i] = house.Rooms[i] with
        {
            Under = [new NearbyElement("a", "OST_Floors", "A", Faces: house.Prism([(-1, -1), (6, -1), (6, 30), (-1, 30)], -1, 0)),
                     new NearbyElement("b", "OST_Floors", "B", Faces: house.Prism([(6, -1), (30, -1), (30, 30), (6, 30)], -1, 0.5))],
        };
        Assert.Contains("different heights", Elevation(house));

        house = FakeHouse.Draw("1_ranch_compliant");      // a slab under part of it only
        house.Rooms[i] = house.Rooms[i] with
        {
            Under = [new NearbyElement("a", "OST_Floors", "A", Faces: house.Prism([(-1, -1), (6, -1), (6, 30), (-1, 30)], -1, 0))],
        };
        Assert.Contains("no one slab top covers the whole room", Elevation(house));

        house = FakeHouse.Draw("1_ranch_compliant");      // the room's base offset 1 in, the slab at the level
        house.Rooms[i] = house.Rooms[i] with { BaseOffset = 1.0 / 12 };
        Assert.Contains("from the floor its level and offset give", Elevation(house));
        Assert.Contains(Problems(house, InteriorReader.Read(house.Model())), p => p.Contains("bed1 sleeping_room_floor_area not measured"));
    }

    // ---- a room's ceilings --------------------------------------------------------------------------------------

    [Fact]
    public void A_soffit_under_the_ceiling_is_its_lowest_and_furniture_is_never_a_ceiling()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.RoomIndex("bed1");
        var over = house.Rooms[i].Over!.ToList();
        over.Add(new NearbyElement("soffit", "OST_GenericModel", "Soffit", Faces: house.Prism([(0, 9), (12, 9), (12, 11), (0, 11)], 6.5, 8)));
        over.Add(new NearbyElement("wardrobe", "OST_Furniture", "Wardrobe", Faces: house.Prism([(0, 0), (2, 0), (2, 2), (0, 2)], 0, 6)));
        house.Rooms[i] = house.Rooms[i] with { Over = over };
        var read = InteriorReader.Read(house.Model());
        var problems = Problems(house, read);
        Assert.Contains(problems, p => p.Contains("bed1 least_ceiling_height = 78.0, expected 96.0"));   // the soffit, 6.5 ft up
        Assert.DoesNotContain(problems, p => p.Contains("72.0"));                                        // never the wardrobe
    }

    [Fact]
    public void Only_a_window_or_door_in_a_bounding_wall_is_set_aside_never_anything_else_the_wall_hosts()
    {
        // review round 1: everything a bounding wall hosted was set aside, so a wall-hosted bulkhead 6.5 ft up was
        // never a ceiling (8 ft read) and never something standing in the room
        var house = FakeHouse.Draw("1_ranch_compliant");
        var i = house.RoomIndex("bed1");
        var bulkhead = new NearbyElement("bulkhead", "OST_GenericModel", "Bulkhead", Host: "wall-0-ymin",
                                         Faces: house.Prism([(0, 0), (12, 0), (12, 1), (0, 1)], 6.5, 8));
        house.Rooms[i] = house.Rooms[i] with { Over = [.. house.Rooms[i].Over!, bulkhead] };
        Assert.Contains(Problems(house, InteriorReader.Read(house.Model())),
                        p => p.Contains("bed1 least_ceiling_height = 78.0, expected 96.0"));
        house = FakeHouse.Draw("1_ranch_compliant");
        house.Rooms[i] = house.Rooms[i] with { Inside = [bulkhead with { Faces = null }] };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Room(read, "bed1")!["floor"]);
        Assert.Contains("GenericModel \"Bulkhead\"", Note(read, "bed1", "floor"));
    }

    [Fact]
    public void Anything_over_a_room_that_cant_be_read_exactly_leaves_its_ceilings_out()
    {
        foreach (var (element, words) in new[]
                 {
                     (new NearbyElement("m", "OST_Mass", "Mass", Faces: [new SurfaceRecord(true, new(0, 0, -1), [], [new(2, 2, 7)])]),
                      "a category Gordium doesn't read"),
                     (new NearbyElement("d", "OST_DuctCurves", "Duct", GeometryFailed: true), "couldn't be read"),
                     (new NearbyElement("c", "OST_Ceilings", "Vault", Faces: [new SurfaceRecord(false, new(0, 0, 0), [], [new(2, 2, 9), new(4, 4, 9)])]),
                      "a curved face"),
                 })
        {
            var house = FakeHouse.Draw("1_ranch_compliant");
            var i = house.RoomIndex("bed1");
            house.Rooms[i] = house.Rooms[i] with { Over = [.. house.Rooms[i].Over!, element] };
            var read = InteriorReader.Read(house.Model());
            Assert.Null(Room(read, "bed1")!["ceilings"]);
            Assert.Contains(words, Note(read, "bed1", "ceilings"));
        }
        var empty = FakeHouse.Draw("1_ranch_compliant");
        var k = empty.RoomIndex("bed1");
        empty.Rooms[k] = empty.Rooms[k] with { Over = [] };
        Assert.Equal("nothing was found over it", Note(InteriorReader.Read(empty.Model()), "bed1", "ceilings"));
        // something with nothing drawn (the project base point, a model line) is nothing over it, whatever its category
        var point = FakeHouse.Draw("1_ranch_compliant");
        point.Rooms[k] = point.Rooms[k] with { Over = [.. point.Rooms[k].Over!, new NearbyElement("pbp", "OST_ProjectBasePoint", Faces: [])] };
        Assert.Equal([], Problems(point, InteriorReader.Read(point.Model())));
    }

    // ---- an escape window's clear opening -----------------------------------------------------------------------

    [Fact]
    public void A_confirmed_window_sends_the_makers_clear_opening_from_its_sill_line()
    {
        var read = InteriorReader.Read(FakeHouse.Draw("2_two_story_small_window").Model());
        var w5 = Opening(read, "w5")!;
        Assert.Equal(FakeHouse.Uid("bed3"), w5["room"]!.GetValue<string>());
        Assert.Equal("casement", w5["operation"]!.GetValue<string>());
        Assert.True(w5["escape"]!.GetValue<bool>());
        Assert.Equal(20.5 / 12, w5["stated_clear"]!["width"]!.GetValue<double>(), 12);
        Assert.Equal(12.0, w5["stated_clear"]!["bottom"]!.GetValue<double>(), 12);          // level 10 ft + sill 2 ft + 0
        Assert.Null(w5["frame"]);                                                            // never a frame or sash
        Assert.Null(w5["ground_outside"]);                                                   // no ground drawn
    }

    public static TheoryData<string, string> UnconfirmedWindows() => new()
    {
        { "no stamp", "isn't confirmed" },
        { "offset blank", "Clear offset (blank is not 0)" },
        { "offset 0 in a schedule", "Gordium: Clear offset" },
        { "source edited", "Gordium: Clear source" },
        { "operation changed", "Gordium: Operation" },
        { "duplicated", "another type" },
        { "resized", "the type's Width" },
        { "no type size", "own Width and Height" },
        { "stamp typed over", "can't be read" },
        { "mapped value changed", "the maker's parameter Rough Width" },
        { "opening an inch below the sill line", "-1 in from its sill line" },
        { "no wall opening", "no opening it cuts in a wall was found" },
        { "hosted in no wall", "no opening it cuts in a wall was found" },
        { "clear wider than the window", "doesn't fit inside the window as placed" },
        { "no geometry", "drawn geometry couldn't be read" },
    };

    [Theory]
    [MemberData(nameof(UnconfirmedWindows))]
    public void A_window_whose_clear_opening_cant_be_trusted_sends_none(string what, string words)
    {
        var house = FakeHouse.Draw("5_basement_window_well");
        var w = house.OpeningIndex("we2");
        var m = house.MarkedIndex("we2");
        var stamp = Marks.Text(house.Marked[m].Type[Marks.ClearConfirmed.Guid])!;
        switch (what)
        {
            case "no stamp": house.SetType("we2", Marks.ClearConfirmed, null); break;
            case "offset blank": house.SetType("we2", Marks.ClearOffset, null); break;
            case "offset 0 in a schedule":
                house.SetType("we2", Marks.ClearOffset, new MarkValue(true, Number: 0.25));
                Restamp(house, "we2");                                                    // confirmed at 3 in
                house.SetType("we2", Marks.ClearOffset, new MarkValue(true, Number: 0));  // then bulk-filled as 0
                break;
            case "source edited": house.SetType("we2", Marks.ClearSource, new MarkValue(true, Text: "another catalogue")); break;
            case "operation changed": house.SetType("we2", Marks.Operation, new MarkValue(true, Text: "Hopper")); break;
            case "duplicated": house.Marked[m] = house.Marked[m] with { TypeUniqueId = "type-copy" }; break;
            case "resized": house.Openings[w] = house.Openings[w] with { TypeWidth = 1.5 }; break;
            case "no type size": house.Openings[w] = house.Openings[w] with { TypeWidth = null }; break;
            case "stamp typed over": house.SetType("we2", Marks.ClearConfirmed, new MarkValue(true, Text: stamp[..20])); break;
            case "mapped value changed":
                house.Openings[w] = house.Openings[w] with { TypeLengths = new Dictionary<string, double> { ["Rough Width"] = 2.0 } };
                Restamp(house, "we2", mapped: "Rough Width");
                house.Openings[w] = house.Openings[w] with { TypeLengths = new Dictionary<string, double> { ["Rough Width"] = 1.75 } };
                break;
            case "opening an inch below the sill line":
                house.Openings[w] = house.Openings[w] with { WallOpening = house.Openings[w].WallOpening!.Select(p => p with { Z = p.Z - 1.0 / 12 }).ToList() };
                break;
            case "no wall opening": house.Openings[w] = house.Openings[w] with { WallOpening = null }; break;
            case "hosted in no wall": house.Openings[w] = house.Openings[w] with { HostIsWall = false }; break;
            case "clear wider than the window":
                house.SetType("we2", Marks.ClearWidth, new MarkValue(true, Number: 2.5));
                Restamp(house, "we2");
                break;
            case "no geometry": house.Openings[w] = house.Openings[w] with { Placed = null }; break;
        }
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Opening(read, "we2")!["stated_clear"]);
        Assert.Contains(words, Note(read, "we2", "stated_clear"));
        Assert.NotNull(Opening(read, "we1")!["stated_clear"]);                            // its neighbour, untouched
        // so its clear opening and sill need review, never a pass
        Assert.Contains(Problems(house, read), p => p.Contains("we2 opening_net_clear_area not measured"));
    }

    private static void Restamp(FakeHouse house, string id, string? mapped = null)
    {
        var e = house.Marked[house.MarkedIndex(id)];
        var rec = house.Openings[house.OpeningIndex(id)];
        var now = InteriorReader.ClearNow(e, rec) with { MappedName = mapped, MappedValue = mapped is null ? null : rec.TypeLengths[mapped] };
        house.SetType(id, Marks.ClearConfirmed, new MarkValue(true, Text: ClearStamp.Make(now, "Fake Architect", FakeHouse.Confirmed)));
    }

    [Fact]
    public void A_stamp_is_never_made_half_way()
    {
        var full = new ClearValues("t", 2, 3, "Casement", 1.9, 2.9, 0, "catalogue");
        Assert.Null(ClearStamp.Why(ClearStamp.Make(full, "A", "2026-11-20"), full, new Dictionary<string, double>()));
        Assert.Throws<ArgumentException>(() => ClearStamp.Make(full with { ClearOffset = null }, "A", "2026-11-20"));
        Assert.Throws<ArgumentException>(() => ClearStamp.Make(full with { Width = null }, "A", "2026-11-20"));
        Assert.Throws<ArgumentException>(() => ClearStamp.Make(full, "", "2026-11-20"));
        Assert.Contains("isn't Gordium's stamp", ClearStamp.Why("{\"stamp\": \"x\"}", full, new Dictionary<string, double>()));
    }

    [Fact]
    public void An_escape_window_between_two_rooms_or_in_none_has_no_room()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var w = house.OpeningIndex("w1");
        house.Openings[w] = house.Openings[w] with { FromRoom = FakeHouse.Uid("bed2") };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Opening(read, "w1")!["room"]);
        Assert.Contains("between two rooms", Note(read, "w1", "room"));
        Assert.Contains(Problems(house, read), p => p.Contains("w1 opening_sill_height not measured"));
        house.Openings[w] = house.Openings[w] with { FromRoom = null, ToRoom = null };
        Assert.Contains("no room", Note(InteriorReader.Read(house.Model()), "w1", "room"));
    }

    [Fact]
    public void A_demolished_window_marked_as_an_escape_opening_is_not_read()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var m = house.MarkedIndex("w1");
        house.Marked[m] = house.Marked[m] with { PhaseDemolished = FakeHouse.LastPhase };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Opening(read, "w1"));
        Assert.Contains(Problems(house, read), p => p.Contains("w1 wasn't measured"));
    }

    [Fact]
    public void A_door_is_an_opening_with_its_marks_and_no_clear_opening_yet()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.Marked.Add(new MarkedElement
        {
            UniqueId = "door-1", BuiltInCategory = Marks.Doors, Name = "36 x 80", Family = "Single", PhaseCreated = FakeHouse.LastPhase,
            Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = new(true, 0), [Marks.ExitDoor.Guid] = new(true, 1) },
            Type = new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: "Side-hinged door") },
        });
        house.Openings.Add(new OpeningRecord { UniqueId = "door-1", ToRoom = FakeHouse.Uid("living"), HostIsWall = true });
        var read = InteriorReader.Read(house.Model());
        var door = read.Interior["openings"]!.AsArray().Single(o => o!["id"]!.GetValue<string>() == "door-1")!;
        Assert.Equal("side_hinged_door", door["operation"]!.GetValue<string>());
        Assert.False(door["escape"]!.GetValue<bool>());
        Assert.Null(door["stated_clear"]);
        Assert.Null(read.Interior["doors"]);                   // the doors step: not read
        Assert.Equal([], Problems(house, read));
    }
}
