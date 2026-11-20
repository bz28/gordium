using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Step 5 (docs/revit/revit_interior_reading_design.md, section 7): the doors (each one's exit mark, operation
/// and the maker's clear opening its type's stamp confirms, as windows' are), the stairs' handrails and the guards at a
/// level walking surface, read from railings. Houses 1, 2, 4, 5 and 6 drawn as fake Revit records (InteriorDrawing.cs)
/// must pass the interior conformance CI applies to the Revit recordings; then each trap, one change at a time, must
/// leave out exactly what it can't read, never a guess.</summary>
public sealed class DoorGuardTests
{
    private const string One = "1_ranch_compliant";
    private const string Two = "2_two_story_small_window";
    private const string Loft = "4_loft";
    private const string Six = "6_door_stated_clear";

    private static InteriorReadResult Read(FakeHouse h) => InteriorReader.Read(h.Model());

    private static JsonObject Door(InteriorReadResult r, string houseId) =>
        r.Interior["doors"]!.AsArray().Select(x => x!.AsObject()).Single(x => x["id"]!.GetValue<string>() == FakeHouse.Uid(houseId));

    private static JsonObject Guard(InteriorReadResult r) => r.Interior["guards"]!.AsArray().Single()!.AsObject();

    private static JsonObject Flight(InteriorReadResult r, string houseId) =>
        r.Interior["stairs"]!.AsArray().Select(x => x!.AsObject()).Single(x => x["id"]!.GetValue<string>() == "run-" + houseId);

    private static string? Note(InteriorReadResult r, string part, string field) =>
        r.Notes.FirstOrDefault(n => n.Part == part && n.Field == field)?.Why;

    // ---- doors ----------------------------------------------------------------------------------------------------

    [Fact]
    public void A_doors_confirmed_maker_clear_opening_is_sent_and_nothing_drawn()
    {
        var house = FakeHouse.Draw(Six);
        var read = Read(house);
        var d1 = Door(read, "d1");
        Assert.True(d1["exit"]!.GetValue<bool>());
        Assert.Equal("side_hinged", d1["operation"]!.GetValue<string>());
        Assert.Equal(33.5 / 12, d1["stated_clear"]!["width"]!.GetValue<double>(), 9);     // the less favourable of drawn and stated
        Assert.Equal(79.25 / 12, d1["stated_clear"]!["height"]!.GetValue<double>(), 9);
        Assert.Contains("made up", d1["stated_clear"]!["source"]!.GetValue<string>());
        foreach (var drawn in new[] { "stops", "hinge_pin", "leaf_closed", "threshold_top", "head_stop_bottom", "hinge_side" })
            Assert.Null(d1[drawn]);                                                         // a family's geometry is never read
        Assert.Equal([], InteriorTests.Problems(house, read));
        // a door that isn't the exit door, its type unconfirmed: sent, with no clear opening
        var one = Read(FakeHouse.Draw(One));
        Assert.False(Door(one, "d2")["exit"]!.GetValue<bool>());
        Assert.Null(Door(one, "d2")["stated_clear"]);
        Assert.Contains("isn't confirmed", Note(one, FakeHouse.Uid("d2"), "doors.stated_clear"));
    }

    public static TheoryData<string, string> DoorStampTraps() => new()
    {
        { "window's stamp", "the stamp wasn't made for a door" },
        { "duplicated type", "made on another type" },
        { "clear width edited", "Gordium: Clear width" },
        { "source edited", "Gordium: Clear source" },
        { "resized type", "the type's Width" },
        { "operation changed", "Gordium: Operation" },
        { "wider than the door", "doesn't fit inside the door as placed" },
        { "no geometry", "its drawn geometry couldn't be read" },
    };

    [Theory]
    [MemberData(nameof(DoorStampTraps))]
    public void A_door_type_changed_since_it_was_confirmed_sends_no_clear_opening(string trap, string words)
    {
        var house = FakeHouse.Draw(Six);
        var i = house.MarkedIndex("d1");
        var o = house.OpeningIndex("d1");
        var type = new Dictionary<Guid, MarkValue>(house.Marked[i].Type);
        switch (trap)
        {
            case "window's stamp":
                type[Marks.ClearConfirmed.Guid] = new(true, Text: ClearStamp.Make(new ClearValues("type-d1", house.Openings[o].TypeWidth,
                    house.Openings[o].TypeHeight, "Side-hinged door", Marks.Length(type[Marks.ClearWidth.Guid]), Marks.Length(type[Marks.ClearHeight.Guid]),
                    0, Marks.Text(type[Marks.ClearSource.Guid])), "Fake Architect", FakeHouse.Confirmed));
                break;
            case "duplicated type": house.Marked[i] = house.Marked[i] with { TypeUniqueId = "type-d1-copy" }; break;
            case "clear width edited": type[Marks.ClearWidth.Guid] = new(true, Number: 34.0 / 12); break;
            case "source edited": type[Marks.ClearSource.Guid] = new(true, Text: "another catalogue"); break;
            case "resized type": house.Openings[o] = house.Openings[o] with { TypeWidth = 3.5 }; break;
            case "operation changed": type[Marks.Operation.Guid] = new(true, Text: "Pocket door"); break;
            case "wider than the door":
                house.Openings[o] = house.Openings[o] with { Placed = house.Openings[o].Placed!.Select(p => p with { X = p.X * 0.5 + 3.75 }).ToList() };
                break;
            case "no geometry": house.Openings[o] = house.Openings[o] with { Placed = null }; break;
        }
        if (trap is not ("duplicated type"))
            house.Marked[i] = house.Marked[i] with { Type = type };
        var read = Read(house);
        Assert.Null(Door(read, "d1")["stated_clear"]);
        Assert.Contains(words, Note(read, FakeHouse.Uid("d1"), "doors.stated_clear"));
        // its clear width and height are then not measured: never the drawn size, never a pass
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("d1 door_clear_width not measured"));
    }

    [Fact]
    public void A_door_needs_no_clear_offset_and_a_window_still_does()
    {
        var house = FakeHouse.Draw(Six);
        house.SetType("d1", Marks.ClearOffset, null);                                       // blank: never a door's
        Assert.NotNull(Door(Read(house), "d1")["stated_clear"]);
        Assert.Contains("Gordium: Clear offset", ClearStamp.Missing(new ClearValues("t", 3, 7, "Casement", 2.9, 6.9, null, "x")));
        Assert.Null(ClearStamp.Missing(new ClearValues("t", 3, 7, "Side-hinged door", 2.9, 6.9, null, "x", Door: true)));
        // a door's stamp never confirms a window
        var stamp = ClearStamp.Make(new ClearValues("t", 3, 7, "Casement", 2.9, 6.9, 0, "x", Door: true), "a", "b");
        Assert.Contains("wasn't made for a window", ClearStamp.Why(stamp, new ClearValues("t", 3, 7, "Casement", 2.9, 6.9, 0, "x"), new Dictionary<string, double>()));
    }

    [Fact]
    public void An_unmarked_door_leaves_every_door_not_read_and_no_door_is_never_none()
    {
        var house = FakeHouse.Draw(One);
        var i = house.MarkedIndex("d1");
        house.Marked[i] = house.Marked[i] with
        {
            Instance = house.Marked[i].Instance.Where(p => p.Key != Marks.ExitDoor.Guid).ToDictionary(p => p.Key, p => p.Value),
        };
        var read = Read(house);
        Assert.Null(Door(read, "d1")["exit"]);
        Assert.Contains("Gordium: Exit door is not set", Note(read, FakeHouse.Uid("d1"), "doors.exit"));
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("egress_door not read"));
        // a window's word on a door is no door's operation
        house = FakeHouse.Draw(One);
        house.SetType("d1", Marks.Operation, new MarkValue(true, Text: "Casement"));
        Assert.Null(Door(Read(house), "d1")["operation"]);
        // no door drawn: doors left out, never []
        house = FakeHouse.Draw(One);
        house.Marked.RemoveAll(m => m.BuiltInCategory == Marks.Doors);
        read = Read(house);
        Assert.Null(read.Interior["doors"]);
        Assert.StartsWith("No doors are drawn", read.DoorsNotRead[0]);
        // a link holding windows or doors: doors not read
        house = FakeHouse.Draw(One);
        house.Links.Add(new InteriorLink("link-1", "Doors.rvt", true, new RevitBox(new(500, 500, 0), new(510, 510, 10)), 0, 2, false));
        Assert.Null(Read(house).Interior["doors"]);
    }

    // ---- the level guard (house 4's loft) ---------------------------------------------------------------------

    [Fact]
    public void House_4s_loft_guard_reads_as_drawn_and_measures_as_worked_by_hand()
    {
        var house = FakeHouse.Draw(Loft);
        var read = Read(house);
        var g = Guard(read);
        Assert.Equal(9.0, g["walking_surface"]!.GetValue<double>(), 9);
        Assert.Equal(12.0, g["top"]!.GetValue<double>(), 9);
        Assert.Equal(0.0, g["extent"]!["left"]!.GetValue<double>(), 9);
        Assert.Equal(4.0, g["extent"]!["right"]!.GetValue<double>(), 9);
        Assert.Equal(11, g["members"]!.AsArray().Count);                                     // 2 rails, 9 balusters
        Assert.Empty(read.GuardsNotRead);
        // the loft stair's handrail, beside its right wall, is a handrail: its sides and headroom read
        var ls = Flight(read, "ls");
        Assert.Equal("right", ls["handrails"]!.AsArray().Single()!["side"]!.GetValue<string>());
        Assert.NotNull(ls["sides"]);
        Assert.NotNull(ls["overhead"]);
        Assert.Equal([], InteriorTests.Problems(house, read));
    }

    [Fact]
    public void Under_turned_and_moved_shared_coordinates_doors_guards_and_handrails_measure_the_same()
    {
        var turn = Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0));
        foreach (var name in new[] { One, Two, Loft, Six })
        {
            var house = FakeHouse.Draw(name, turn);
            Assert.Equal([], InteriorTests.Problems(house, Read(house)));
        }
    }

    [Fact]
    public void Without_the_architects_tick_no_guard_and_no_handrail_is_read()
    {
        foreach (var value in new MarkValue?[] { null, new(true, 0), new(false, 0) })
        {
            var house = FakeHouse.Draw(Loft);
            if (value is null)
                house.ProjectMarks.Remove(Marks.AllGuards.Guid);
            else
                house.ProjectMarks[Marks.AllGuards.Guid] = value;
            var read = Read(house);
            Assert.Null(read.Interior["guards"]);
            Assert.Contains(read.GuardsNotRead, w => w.StartsWith(Marks.AllGuards.Name, StringComparison.Ordinal));
            Assert.Null(Flight(read, "ls")["handrails"]);
            Assert.NotNull(Flight(read, "ls")["sides"]);                                    // the walls are still its sides
            Assert.Contains("a handrail drawn as something else", Note(read, "run-ls", "handrails"));
        }
    }

    [Fact]
    public void No_guard_found_is_never_none()
    {
        var house = FakeHouse.Draw(Loft);
        house.Railings!.RemoveAll(r => r.Host is null);
        var read = Read(house);
        Assert.Null(read.Interior["guards"]);
        Assert.StartsWith("No guards are drawn", read.GuardsNotRead[0]);
        house = FakeHouse.Draw(Loft);
        house.Railings = null;                                                               // not read at all
        read = Read(house);
        Assert.Null(read.Interior["guards"]);
        Assert.Contains("the railings couldn't be read", read.GuardsNotRead);
        Assert.Null(Flight(read, "ls")["handrails"]);
        // a stair blocker (an in-place family in Railings) leaves the guards out too
        house = FakeHouse.Draw(Loft);
        house.StairCandidates.Add(new("ip", "OST_StairsRailing", "Balcony rail", "an in-place family"));
        Assert.Null(Read(house).Interior["guards"]);
    }

    public static TheoryData<string, string, string> GuardTraps() => new()
    {
        { "round baluster", "members", "isn't a box square to the guard" },
        { "L-shaped post", "members", "isn't a box square to the guard" },
        { "baluster unread", "members", "couldn't be read exactly" },
        { "no end wall", "extent", "nothing solid was found at its start" },
        { "end wall short", "extent", "nothing solid was found at its end" },
        { "end wall set back", "extent", "nothing solid was found at its start" },
        { "floor off its base", "walking_surface", "from its base (its level and base offset)" },
        { "no base offset", "walking_surface", "its base level or base offset couldn't be read" },
        { "two floors", "walking_surface", "at different heights" },
        { "no floor", "walking_surface", "no floor top was found" },
        { "curved path", "members", "its path has a curve" },
        { "bent path", "members", "isn't one straight line" },
        { "link", "members", "reaches it, and what is in a link isn't read yet" },
    };

    [Theory]
    [MemberData(nameof(GuardTraps))]
    public void A_guard_that_cant_be_read_exactly_leaves_out_what_it_cant_read(string trap, string field, string words)
    {
        var house = FakeHouse.Draw(Loft);
        var uid = "railing-lg";
        var g = house.Drawing["guards"]![0]!;
        double z = g["level"]!.GetValue<double>(), x0 = g["start"]![0]!.GetValue<double>();
        RailingRecord r = house.Railings![house.RailingIndex(uid)];
        List<NearbyElement> near = [.. r.Near!];
        var solids = r.Parts[0].Solids!.ToList();
        switch (trap)
        {
            case "round baluster":
                solids[^1] = [.. solids[^1].Take(5), new SurfaceRecord(false, new(0, 0, 0), [], [house.Fake.Place(x0 + 1, 0, z + 1)])];
                break;
            case "L-shaped post":
                solids.Add([.. solids[^1], solids[^1][0]]);                                  // 7 faces, each square
                break;
            case "baluster unread":
                r = r with { Parts = [r.Parts[0] with { Solids = null, GeometryFailed = true }, r.Parts[1]] };
                break;
            case "no end wall": near.RemoveAll(e => e.UniqueId == "guardwall-lg-0"); break;
            case "end wall short":
                near[near.FindIndex(e => e.UniqueId == "guardwall-lg-1")] = FakeHouse.Boxed(new("guardwall-lg-1", "OST_Walls", "Post",
                    Faces: house.Prism([(x0 + 4, -1), (x0 + 4 + 1.0 / 3, -1), (x0 + 4 + 1.0 / 3, 1), (x0 + 4, 1)], z, z + 2.5)));   // under its top
                break;
            case "end wall set back":
                near[near.FindIndex(e => e.UniqueId == "guardwall-lg-0")] = FakeHouse.Boxed(new("guardwall-lg-0", "OST_Walls", "Wall",
                    Faces: house.Prism([(x0 - 0.5, -1), (x0 - 1.0 / 12, -1), (x0 - 1.0 / 12, 1), (x0 - 0.5, 1)], z, z + 4)));       // an inch off
                break;
            case "floor off its base": r = r with { BaseOffset = 1.0 / 12 }; break;
            case "no base offset": r = r with { BaseOffset = null }; break;
            case "two floors":
                near.Add(FakeHouse.Boxed(new("step", "OST_Floors", "Step", Faces: house.Prism([(x0 + 1, 0), (x0 + 2, 0), (x0 + 2, 1), (x0 + 1, 1)], z - 1, z + 0.5))));
                break;
            case "no floor": near.RemoveAll(e => e.UniqueId == "guardfloor-lg"); break;
            case "curved path": r = r with { Path = [r.Path[0] with { IsLine = false }] }; break;
            case "bent path":
                r = r with { Path = [r.Path[0] with { End = house.Fake.Place(x0 + 2, 0, z) }, new PathCurve(house.Fake.Place(x0 + 2, 0, z), house.Fake.Place(x0 + 4, 1, z), true)] };
                break;
            case "link":
                house.Links.Add(new InteriorLink("link-1", "Structure.rvt", true, new RevitBox(house.Fake.Place(x0 - 1, -1, 0), house.Fake.Place(x0 + 5, 1, 20)), 0, 0, false));
                break;
        }
        if (trap is "round baluster" or "L-shaped post")
            r = r with { Parts = [r.Parts[0] with { Solids = solids }, r.Parts[1]] };
        var changed = r with { Near = near };
        house.SetRailing(uid, _ => changed);
        var read = Read(house);
        var guard = Guard(read);                                                             // a guard found is never dropped
        Assert.Null(guard[field]);
        Assert.Contains(words, Note(read, uid, field));
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("lg guard_height not measured"));
    }

    [Fact]
    public void Two_staggered_rows_of_balusters_at_different_depths_leave_the_openings_not_measured()
    {
        // each row 4.5 in clear between its balusters, the second row 3 in deeper and offset by half: seen in one
        // plane they overlap to 1.5 in gaps, yet a 4 in sphere can weave between them
        var house = FakeHouse.Draw(Loft);
        var g = house.Drawing["guards"]![0]!;
        double z = g["level"]!.GetValue<double>(), x0 = g["start"]![0]!.GetValue<double>(), y0 = g["start"]![1]!.GetValue<double>();
        const double inch = 1.0 / 12;
        List<SurfaceRecord> Box(double u0, double u1, double n0, double n1, double z0, double z1)
        {
            var c = new List<(double X, double Y, double Z)>();
            foreach (var zz in new[] { z0, z1 })
                foreach (var (u, n) in new[] { (u0, n0), (u1, n0), (u1, n1), (u0, n1) })
                    c.Add((x0 + u, y0 + n, zz));
            return house.Hexahedron(c);
        }
        var solids = new List<IReadOnlyList<SurfaceRecord>> { Box(0, 4, -0.75 * inch, 0.75 * inch, z + 2 * inch, z + 3.5 * inch) };
        for (var u = 0.0; u + 1.5 * inch <= 4; u += 6 * inch)
            solids.Add(Box(u, u + 1.5 * inch, -0.75 * inch, 0.75 * inch, z + 3.5 * inch, z + 34.5 * inch));
        for (var u = 3 * inch; u + 1.5 * inch <= 4; u += 6 * inch)
            solids.Add(Box(u, u + 1.5 * inch, 2.25 * inch, 3.75 * inch, z + 3.5 * inch, z + 34.5 * inch));
        house.SetRailing("railing-lg", r => r with { Parts = [r.Parts[0] with { Solids = solids }, r.Parts[1]] });
        var read = Read(house);
        Assert.Null(Guard(read)["members"]);
        Assert.Contains("aren't in one plane", Note(read, "railing-lg", "members"));
        Assert.Contains("at 2.25 in across the guard", Note(read, "railing-lg", "members"));
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("lg guard_opening_sphere not measured"));
    }

    // ---- a stair's handrails, and railings on a stair --------------------------------------------------------

    [Fact]
    public void The_top_rail_is_a_handrail_only_where_its_type_says_so()
    {
        var house = FakeHouse.Draw(Two);
        house.SetRailing("railing-s1-right", r => r with { TypeMarks = new Dictionary<Guid, MarkValue>() });
        var read = Read(house);
        Assert.Null(Flight(read, "s1")["handrails"]);
        Assert.Contains("Gordium: Top rail is handrail isn't set", Note(read, "run-s1", "handrails"));
        Assert.NotNull(Flight(read, "s1")["sides"]);
        house.SetRailing("railing-s1-right", r => r with { TypeMarks = new Dictionary<Guid, MarkValue> { [Marks.TopRailIsHandrail.Guid] = new(true, 0) } });
        read = Read(house);
        Assert.Empty(Flight(read, "s1")["handrails"]!.AsArray());                            // the architect's No: none on it
        Assert.Contains(InteriorTests.Problems(house, read), p => p.Contains("s1 stair_handrail_sides = 0, expected 1"));
    }

    public static TheoryData<string> RailingTraps() => ["round", "too high", "not on the stair", "past the middle"];

    [Theory]
    [MemberData(nameof(RailingTraps))]
    public void A_railing_beside_a_flight_not_read_as_its_handrail_leaves_its_sides_and_the_guards_out(string trap)
    {
        var house = FakeHouse.Draw(Two);
        var st = house.StairDrawing("s1");
        house.SetRailing("railing-s1-right", r =>
        {
            var top = r.Parts[1];
            return trap switch
            {
                "round" => r with { Parts = [r.Parts[0], top with { Solids = [[.. top.Solids![0].Take(5), new SurfaceRecord(false, new(0, 0, 0), [], top.Solids[0][5].Points)]] }] },
                "too high" => r with { Parts = [r.Parts[0], top with { Solids = [house.StairBox(st, 0, 12.5, -1.5 + 2.0 / 12, -1.5 + 3.5 / 12, 3.0, 12.0)] }] },
                "past the middle" => r with { Parts = [r.Parts[0], top with { Solids = [house.StairBox(st, 0, 12.5, -1.5 + 2.0 / 12, 0.2, 3.0, 4.0)] }] },
                _ => r with { Host = null },
            };
        });
        if (trap == "not on the stair")
            house.Stairs[0] = house.Stairs[0] with { Railings = [] };
        var read = Read(house);
        Assert.Null(Flight(read, "s1")["sides"]);
        Assert.Null(Flight(read, "s1")["handrails"]);
        Assert.Contains("isn't read as its handrail beside the wall", Note(read, "run-s1", "sides"));
        if (trap != "not on the stair")
            Assert.Contains(read.GuardsNotRead, w => w.Contains("isn't read as a handrail beside a wall: a guard along a stair isn't read yet"));
        else
        {
            // a railing on no stair is a level guard: sent, its sloped rail no box square to it, so nothing measured
            var g = Guard(read);
            Assert.Equal("railing-s1-right", g["id"]!.GetValue<string>());
            Assert.Null(g["members"]);
        }
    }
}
