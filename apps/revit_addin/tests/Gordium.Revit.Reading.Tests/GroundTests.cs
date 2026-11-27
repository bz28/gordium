using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The ground just outside each window (<c>openings[].ground_outside</c>, GroundReader; a door's isn't read: its
/// clear bottom isn't sent), read from a
/// Toposolid the architect states shows the finished ground (Gordium: Toposolid is finished ground): RCNYS R202 "GRADE.
/// The finished ground level adjoining the building at all exterior walls", read 1 in beyond the wall's outer face at
/// each end of the opening and its middle. From it the measuring works out whether an escape opening is below grade and
/// how deep its well is at least; a mark the architect sets wins, and one the ground contradicts needs review. With no
/// ground drawn nothing changes. The houses are test_data/interior_houses (house 1's windows' clear bottoms 2.5 ft and
/// 2 ft over a floor at 0; house 5's basement windows' at -5 ft and -4 1/6 ft).</summary>
public sealed class GroundTests
{
    private static JsonObject Opening(InteriorReadResult read, string id) =>
        read.Interior["openings"]!.AsArray().Select(o => o!.AsObject()).Single(o => o["id"]!.GetValue<string>() == FakeHouse.Uid(id));

    private static List<double>? Ground(InteriorReadResult read, string id) =>
        Opening(read, id)["ground_outside"]?.AsArray().Select(z => z!.GetValue<double>()).ToList();

    private static string? Why(InteriorReadResult read, string id) =>
        read.Notes.SingleOrDefault(n => n.Part == FakeHouse.Uid(id) && n.Field == "ground_outside")?.Why;

    private static FakeHouse Drawn(string house, Func<double, double, double> z, bool? finished = true)
    {
        var h = FakeHouse.Draw(house);
        h.Grounds = [h.Toposolid(z)];
        h.FinishedGround(finished);
        return h;
    }

    private static void SetMark(FakeHouse house, string id, MarkDefinition mark, MarkValue value)
    {
        var i = house.MarkedIndex(id);
        house.Marked[i] = house.Marked[i] with { Instance = new Dictionary<Guid, MarkValue>(house.Marked[i].Instance) { [mark.Guid] = value } };
    }

    /// <summary>The measuring's escape opening, run on the description the reader sends.</summary>
    private static JsonNode Measured(InteriorReadResult read, string id)
    {
        var path = Path.Combine(Path.GetTempPath(), $"gordium_ground_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, read.Interior.ToJsonString());
        try
        {
            const string Code = "import json, sys\nfrom model_measurement.interior import measure\n" +
                                "d = json.load(open(sys.argv[1], encoding='utf-8'))\n" +
                                "p = [p for p in measure(d)['parts']['emergency_escape_opening'] if p['id'] == sys.argv[2]][0]\n" +
                                "print(json.dumps({'m': p['measures'], 'not': p['not_measured'], 'confirm': p.get('confirm', {})}))";
            return JsonNode.Parse(Env.RunCode(Code, path, FakeHouse.Uid(id)))!;
        }
        finally
        {
            File.Delete(path);
        }
    }

    // ---- the five fixtures ------------------------------------------------------------------------------------------

    /// <summary>Sloped ground, rising along the wall: the ground is read at each end and the middle (1/2 ft per ft
    /// along x, 2.5 ft at the window's middle), and over one end it stands above the clear bottom, so the opening is
    /// below grade there.</summary>
    [Fact]
    public void Sloped_ground_is_read_at_each_end_and_the_middle_and_over_one_end_is_below_grade()
    {
        var read = InteriorReader.Read(Drawn("1_ranch_compliant", (x, _) => 2.5 + (x - 6) / 2).Model());
        var at = Ground(read, "w1")!;
        Assert.Equal(3, at.Count);
        var half = 2.1666666666666665 / 2 / 2;                         // half the window's width, at 1/2 ft per ft
        Assert.Equal([2.5 - half, 2.5, 2.5 + half], at.Select(z => Math.Round(z, 9)).ToList(), (a, b) => Math.Abs(a - b) < 1e-9);
        var m = Measured(read, "w1");
        Assert.True(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        // 6.5 in over the bottom: at least 6.5 in deep, which settles nothing (not past 44 in)
        Assert.Null(m["m"]!["area_well_depth"]);
        Assert.Contains("6.5 in above its clear opening's bottom, so the well is at least that deep", m["not"]!["area_well_depth"]!.GetValue<string>());
    }

    /// <summary>A window above grade: flat finished ground at 0 under a clear bottom 2.5 ft up.</summary>
    [Fact]
    public void A_window_above_the_ground_is_measured_not_below_grade()
    {
        var read = InteriorReader.Read(Drawn("1_ranch_compliant", (_, _) => 0).Model());
        Assert.Equal([0.0, 0.0, 0.0], Ground(read, "w1"));
        Assert.Null(Why(read, "w1"));
        var m = Measured(read, "w1");
        Assert.False(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        Assert.Null(m["m"]!["area_well_depth"]);
    }

    /// <summary>A window below grade: house 5's basement window, its clear bottom 60 in under finished ground at 0:
    /// below grade, and its well at least 60 in deep, handed to the rules as a reading to confirm.</summary>
    [Fact]
    public void A_basement_window_under_the_ground_is_below_grade_and_its_well_at_least_as_deep()
    {
        var read = InteriorReader.Read(Drawn("5_basement_window_well", (_, _) => 0).Model());
        Assert.Equal([0.0, 0.0, 0.0], Ground(read, "we1"));
        var m = Measured(read, "we1");
        Assert.True(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        Assert.Equal(60.0, m["m"]!["area_well_depth"]!.GetValue<double>(), 6);
        Assert.StartsWith("Gordium's reading: an area well's floor is at or below the bottom", m["confirm"]!["area_well_depth"]!.GetValue<string>());
    }

    /// <summary>No Toposolid: nothing changes (no ground sent, nothing said), and the marks are what the rules use.</summary>
    [Fact]
    public void With_no_ground_drawn_nothing_changes()
    {
        var before = InteriorReader.Read(FakeHouse.Draw("5_basement_window_well").Model());
        Assert.Null(Ground(before, "we1"));
        Assert.DoesNotContain(before.Notes, n => n.Field == "ground_outside");
        var empty = FakeHouse.Draw("5_basement_window_well");
        empty.Grounds = [];
        empty.FinishedGround(true);
        var read = InteriorReader.Read(empty.Model());
        Assert.Equal(before.Interior.ToJsonString(), read.Interior.ToJsonString());
        Assert.Equal(before.Notes.Select(n => (n.Part, n.Field, n.Why)), read.Notes.Select(n => (n.Part, n.Field, n.Why)));
        // a ground demolished in the design checked is none too
        var gone = FakeHouse.Draw("5_basement_window_well");
        gone.Grounds = [gone.Toposolid((_, _) => 0) with { PhaseDemolished = FakeHouse.LastPhase }];
        gone.FinishedGround(true);
        Assert.Equal(before.Interior.ToJsonString(), InteriorReader.Read(gone.Model()).Interior.ToJsonString());
        // and the marks reach the rules as before
        SetMark(empty, "we1", Marks.BelowGrade, new(true, 1));
        var m = Measured(InteriorReader.Read(empty.Model()), "we1");
        Assert.True(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        Assert.Null(m["m"]!["area_well_depth"]);
    }

    /// <summary>A mark that disagrees with the ground: house 5's window marked not below grade, 60 in under the
    /// finished ground: neither is used, the reason naming both.</summary>
    [Fact]
    public void A_mark_the_ground_contradicts_is_needs_review_naming_both()
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        SetMark(house, "we1", Marks.BelowGrade, new(true, 0));
        SetMark(house, "we1", Marks.WellDepth, new(true, Number: 3.0));          // 36 in, under the 60 the ground shows
        var m = Measured(InteriorReader.Read(house.Model()), "we1");
        Assert.Null(m["m"]!["opening_below_grade"]);
        Assert.Contains("is stated not to be below the adjacent grade, yet the model shows the ground outside it at 0 in, above its clear opening's bottom",
                        m["not"]!["opening_below_grade"]!.GetValue<string>());
        Assert.Null(m["m"]!["area_well_depth"]);
        Assert.Contains("states its area well's vertical depth as 36 in, yet the model shows the ground outside it 60 in above",
                        m["not"]!["area_well_depth"]!.GetValue<string>());
        // a mark the ground agrees with wins, and a deeper stated well is the architect's
        SetMark(house, "we1", Marks.BelowGrade, new(true, 1));
        SetMark(house, "we1", Marks.WellDepth, new(true, Number: 5.5));
        m = Measured(InteriorReader.Read(house.Model()), "we1");
        Assert.True(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        Assert.Equal(66.0, m["m"]!["area_well_depth"]!.GetValue<double>(), 6);
        Assert.Null(m["confirm"]!["area_well_depth"]);
    }

    // ---- never a guess ---------------------------------------------------------------------------------------------

    [Fact]
    public void A_toposolid_not_stated_to_be_the_finished_ground_isnt_read_and_an_escape_opening_says_why()
    {
        foreach (var said in new bool?[] { null, false })
        {
            var read = InteriorReader.Read(Drawn("5_basement_window_well", (_, _) => 0, said).Model());
            Assert.Null(Ground(read, "we1"));
            Assert.StartsWith("Gordium: Toposolid is finished ground isn't Yes on Project Information, so the ground drawn (Toposolid \"Finished grade\") isn't read",
                              Why(read, "we1"));
        }
    }

    /// <summary>A well cut into the ground (the ground at the face 5 ft lower than 3 ft out), or ground rising toward
    /// the wall: which ground adjoins the opening isn't clear, so none is sent (the well's floor at the face would make
    /// a buried window look above grade).</summary>
    [Fact]
    public void Ground_rising_away_from_the_wall_is_never_read_as_the_ground_at_the_face()
    {
        // house 5's window wall is at y = 0, its outside toward -y
        var deep = FakeHouse.Draw("5_basement_window_well");
        deep.Grounds = [deep.Toposolid((_, y) => y > -3.25 ? -5.5 : 0, ys: [-3.3, -3.2])];
        deep.FinishedGround(true);
        var cut = InteriorReader.Read(deep.Model());
        Assert.Null(Ground(cut, "we1"));
        Assert.Contains("the ground rises 66 in from its wall's face to 3 ft out (an area well cut into the ground, or ground sloping toward the wall)", Why(cut, "we1"));
        var rising = InteriorReader.Read(Drawn("5_basement_window_well", (_, y) => -y / 10).Model());
        Assert.Null(Ground(rising, "we1"));
        Assert.Contains("the ground rises", Why(rising, "we1"));
        // falling away is the usual: the ground at the face is read
        var falling = InteriorReader.Read(Drawn("5_basement_window_well", (_, y) => y / 10).Model());
        Assert.NotNull(Ground(falling, "we1"));
    }

    [Fact]
    public void Something_standing_over_the_ground_outside_it_leaves_the_ground_unread()
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        var i = house.OpeningIndex("we1");
        var well = new NearbyElement("well-1", "OST_GenericModel", "Area well", Box: new RevitBox(
            house.Fake.Place(2, -4, -6), house.Fake.Place(5.5, -0.2, 0.5)));
        house.Openings[i] = house.Openings[i] with { Around = [well] };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Ground(read, "we1"));
        Assert.Equal("GenericModel \"Area well\" stands over the ground outside it, so what the finished grade is there isn't known",
                     Why(read, "we1"));
        // the window's own box and its own wall are never what stands outside it; one gone in the design checked isn't
        house.Openings[i] = house.Openings[i] with
        {
            Around = [well with { UniqueId = house.Openings[i].UniqueId }, well with { UniqueId = house.Openings[i].Host! },
                      well with { UniqueId = "gone", PhaseDemolished = FakeHouse.LastPhase }],
        };
        Assert.NotNull(Ground(InteriorReader.Read(house.Model()), "we1"));
        // nothing looked for: not read
        house.Openings[i] = house.Openings[i] with { Around = null };
        Assert.Equal("what stands outside it couldn't be looked for, so the ground there isn't read", Why(InteriorReader.Read(house.Model()), "we1"));
    }

    [Fact]
    public void Two_grounds_over_one_point_are_read_only_as_a_subdivision_on_its_host()
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        house.Grounds!.Add(house.Toposolid((_, _) => 0.1, "topo-2", "Old grade"));
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Ground(read, "we1"));
        Assert.Contains("two grounds are drawn just outside it (Toposolid \"Old grade\" at 0.1 ft, Toposolid \"Finished grade\" at 0 ft)", Why(read, "we1"));
        house.Grounds[1] = house.Grounds[1] with { Host = "topo-1", Name = "Path" };      // a path on the grade
        Assert.Equal([0.1, 0.1, 0.1], Ground(InteriorReader.Read(house.Model()), "we1")!.Select(z => Math.Round(z, 9)));
    }

    [Fact]
    public void A_ground_whose_edge_or_geometry_isnt_there_leaves_the_ground_unread()
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        house.Grounds = [house.Toposolid((_, _) => 0, reach: 2)];                           // ends 2 ft from the origin
        Assert.Contains("no finished ground is drawn", Why(InteriorReader.Read(house.Model()), "we1"));
        house.Grounds = [house.Toposolid((_, _) => 0) with { Triangles = null }];
        Assert.Equal("the geometry of the ground Toposolid \"Finished grade\" couldn't be read, so no ground is read", Why(InteriorReader.Read(house.Model()), "we1"));
    }

    // ---- review round 1 ---------------------------------------------------------------------------------------------

    /// <summary>A bump or a dip of the ground between the three places read (a point of the Toposolid a quarter of the
    /// way along house 1's window, x = 5.5; its clear bottom at 2.5 ft): the highest and lowest along the whole width
    /// are sent too, so a bump over the bottom is below grade, and a dip more than 44 in under it is no grade-floor
    /// opening (before: three places at 2 ft, read as above grade).</summary>
    [Theory]
    [InlineData(3.0, true)]
    [InlineData(-2.0, false)]
    public void A_bump_or_a_dip_between_the_places_read_is_sent_too(double peak, bool below)
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        house.Grounds = [house.Toposolid((x, _) => Math.Abs(x - 5.5) < 1e-9 ? peak : 2.0, xs: [5.0, 5.5, 6.0])];
        house.FinishedGround(true);
        var read = InteriorReader.Read(house.Model());
        var at = Ground(read, "w1")!;
        Assert.Contains(at, z => Math.Abs(z - peak) < 1e-9);
        var m = Measured(read, "w1");
        if (below)
            Assert.True(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        else
        {
            Assert.False(m["m"]!["opening_below_grade"]!.GetValue<bool>());
            Assert.Null(m["m"]!["opening_at_grade"]);               // within 44 in of 2 ft, not of -2 ft: mixed
        }
    }

    /// <summary>Something narrower than the places read apart, standing between them (a step 4 in wide in front of
    /// house 1's window, between its end, x 4.92, and its middle, x 6): what stands over the ground is looked for over
    /// the whole of the outside, never only at the places read.</summary>
    [Fact]
    public void Something_standing_between_the_places_read_is_found()
    {
        var house = Drawn("1_ranch_compliant", (_, _) => 0);
        var i = house.OpeningIndex("w1");
        var step = new NearbyElement("step-1", "OST_GenericModel", "Step", Box: new RevitBox(
            house.Fake.Place(5.2, -2.5, -0.2), house.Fake.Place(5.53, -1.5, 0.6)));
        house.Openings[i] = house.Openings[i] with { Around = [step] };
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Ground(read, "w1"));
        Assert.Equal("GenericModel \"Step\" stands over the ground outside it, so what the finished grade is there isn't known", Why(read, "w1"));
        // above the window's top it stands over nothing that matters to it
        house.Openings[i] = house.Openings[i] with { Around = [step with { Box = new RevitBox(house.Fake.Place(5.2, -2.5, 6), house.Fake.Place(5.53, -1.5, 7)) }] };
        Assert.NotNull(Ground(InteriorReader.Read(house.Model()), "w1"));
    }

    /// <summary>A Room's box (an L-shaped room's covers the ground outside a wall), an area's or a line's is never
    /// something standing over the ground.</summary>
    [Theory]
    [InlineData("OST_Rooms")]
    [InlineData("OST_Areas")]
    [InlineData("OST_RoomSeparationLines")]
    [InlineData("OST_Lines")]
    public void A_rooms_box_or_a_lines_is_never_something_standing_over_the_ground(string category)
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        var i = house.OpeningIndex("we1");
        house.Openings[i] = house.Openings[i] with
        {
            Around = [new NearbyElement("room-box", category, "Bedroom", Box: new RevitBox(house.Fake.Place(-20, -20, -10), house.Fake.Place(20, 20, 10)))],
        };
        Assert.NotNull(Ground(InteriorReader.Read(house.Model()), "we1"));
    }

    /// <summary>A door's clear bottom isn't sent, so its ground would only unsettle its Below grade mark: no door's
    /// ground is sent (house 1's two doors to outside).</summary>
    [Fact]
    public void No_doors_ground_is_sent()
    {
        var house = Drawn("1_ranch_compliant", (_, _) => 0);
        // the doors' wall faces, as the windows' (the room's at the centre line, the outside one a wall's thickness out
        // toward +y): without them no door could be placed, and the test would pass whatever the reader does
        foreach (var (d, x) in new[] { ("d1", 7.666666666666666), ("d2", 15.333333333333332) })
        {
            var i = house.OpeningIndex(d);
            house.Openings[i] = house.Openings[i] with
            {
                WallSides = [new WallFace(house.Fake.Place(x, 25.5, 0), house.Fake.Place(0, 1, 0) - house.Fake.Place(0, 0, 0)),
                             new WallFace(house.Fake.Place(x, 25, 0), house.Fake.Place(0, -1, 0) - house.Fake.Place(0, 0, 0))],
                Around = [],
            };
        }
        var read = InteriorReader.Read(house.Model());
        Assert.NotNull(Ground(read, "w1"));
        foreach (var d in new[] { "d1", "d2" })
        {
            Assert.Null(Ground(read, d));
            Assert.Null(Why(read, d));
        }
    }

    /// <summary>An older topography's subregion (a walk, a patio) lies on its host, as a Toposolid subdivision does:
    /// the Revit layer names its host, so it isn't read as a second ground.</summary>
    [Fact]
    public void An_older_topographys_subregion_is_read_on_its_host()
    {
        var source = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "RevitInterior.cs"));
        Assert.Contains("grounds.Add(GroundOf(doc, s, \"TopographySurface\", s.IsSiteSubRegion ? s.AsSiteSubRegion()?.HostId : null));", source);
        Assert.Contains("grounds.Add(GroundOf(doc, s, \"Toposolid\", s.HostTopoId));", source);
    }

    /// <summary>A window's reason never speaks of a door, a sidelight or a pocket (its rough opening 1 ft wider than
    /// its type).</summary>
    [Fact]
    public void A_windows_reason_speaks_of_a_window()
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        var i = house.OpeningIndex("we1");
        house.Openings[i] = house.Openings[i] with { TypeWidth = house.Openings[i].TypeWidth - 1 };
        var why = Why(InteriorReader.Read(house.Model()), "we1")!;
        Assert.StartsWith("the opening it takes in its wall is 30 in wide, more than the window (18 in) and a frame (8 in), so where", why);
        Assert.DoesNotContain("door", why, StringComparison.Ordinal);
        Assert.DoesNotContain("sidelight", why, StringComparison.Ordinal);
    }

    // ---- review round 2 ---------------------------------------------------------------------------------------------

    /// <summary>A hole or a cliff cut into the Toposolid between the places read (a cell of the grid across the line
    /// 1 in out from house 1's window, x 5 to 5.33, between its end and its middle), so each stretch between the edges
    /// the line crosses is read too, its plane taken at both ends. A hole: its rim is the ground at both its sides, no
    /// ground between, nothing sent. A cliff whose floor slopes from 4 ft down at x 5 to 1 ft at x 5.33 (review round 3:
    /// a flat floor was read at its own diagonal, so it pinned nothing): its lowest, 4 ft down at the rim's foot, is
    /// sent (read along the cell's diagonal alone it would be some 3.5 ft), and the window, more than 44 in over it, is
    /// no grade-floor opening.</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void A_hole_or_a_cliff_between_the_edges_the_face_line_crosses_is_read(bool cliff)
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var whole = house.Toposolid((_, _) => 0, xs: [5.0, 5.33], ys: [-0.6, -0.5]);
        bool InCell(GroundTriangle t)
        {
            double x = (t.A.X + t.B.X + t.C.X) / 3, y = (t.A.Y + t.B.Y + t.C.Y) / 3;
            return x > 5.0 && x < 5.33 && y > -0.6 && y < -0.5;
        }
        var kept = whole.Triangles!.Where(t => !InCell(t)).ToList();
        Xyz Floor(Xyz v) => v with { Z = v.X < 5.0 + 1e-9 ? -4 : -1 };      // the cell's floor, its sides sheer
        if (cliff)
            kept.AddRange(whole.Triangles!.Where(InCell).Select(t => new GroundTriangle(Floor(t.A), Floor(t.B), Floor(t.C))));
        house.Grounds = [whole with { Triangles = kept }];
        house.FinishedGround(true);
        var read = InteriorReader.Read(house.Model());
        if (!cliff)
        {
            Assert.Null(Ground(read, "w1"));
            Assert.StartsWith("no finished ground is drawn just outside it", Why(read, "w1"));
            return;
        }
        Assert.Contains(Ground(read, "w1")!, z => Math.Abs(z + 4) < 1e-9);
        var m = Measured(read, "w1");
        Assert.False(m["m"]!["opening_below_grade"]!.GetValue<bool>());
        Assert.Null(m["m"]!["opening_at_grade"]);                       // within 44 in of 0, not of -4 ft
    }

    /// <summary>A subregion level with its host (an older topography's lies on its host's surface), listed after or
    /// before it: the ground is read, never "two grounds".</summary>
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void A_subregion_level_with_its_host_is_read_on_it(bool subFirst)
    {
        var house = FakeHouse.Draw("5_basement_window_well");
        var host = house.Toposolid((_, _) => 0);
        var sub = house.Toposolid((_, _) => 0, "topo-2", "Walk", host: "topo-1");
        house.Grounds = subFirst ? [sub, host] : [host, sub];
        house.FinishedGround(true);
        var read = InteriorReader.Read(house.Model());
        Assert.Equal([0.0, 0.0, 0.0], Ground(read, "we1"));
        Assert.Null(Why(read, "we1"));
        // a host standing above its own subdivision is two grounds still
        house.Grounds = [host with { Triangles = house.Toposolid((_, _) => 0.5).Triangles }, sub];
        Assert.Contains("two grounds are drawn", Why(InteriorReader.Read(house.Model()), "we1"));
    }

    /// <summary>A window whose type has no width (an instance-width family): said as such, never "(0 in)".</summary>
    [Fact]
    public void A_window_with_no_type_width_says_so()
    {
        var house = Drawn("5_basement_window_well", (_, _) => 0);
        var i = house.OpeningIndex("we1");
        house.Openings[i] = house.Openings[i] with { TypeWidth = null };
        var why = Why(InteriorReader.Read(house.Model()), "we1")!;
        Assert.Equal("its type's width isn't read, so whether the opening it takes in its wall holds more than the window isn't known", why);
    }

    /// <summary>The marks' words say a window's ground is read, a door's not (its clear bottom isn't sent).</summary>
    [Fact]
    public void The_marks_say_the_ground_is_read_at_windows_only()
    {
        Assert.DoesNotContain("window and door", Marks.ToposolidFinished.Description, StringComparison.Ordinal);
        Assert.DoesNotContain("each window and door", File.ReadAllText(Path.Combine(Env.Repo, "docs", "revit", "revit_reading_design.md")), StringComparison.Ordinal);
        Assert.Contains("a door's isn't read yet", Marks.ToposolidFinished.Description, StringComparison.Ordinal);
        Assert.Contains("Blank: for a window, read from the Toposolid", Marks.BelowGrade.Description, StringComparison.Ordinal);
        Assert.Contains("Blank: for a window, where Gordium: Toposolid is finished ground is Yes", Marks.WellDepth.Description, StringComparison.Ordinal);
    }

    [Fact]
    public void Only_an_escape_opening_says_why_its_ground_isnt_read()
    {
        var read = InteriorReader.Read(Drawn("1_ranch_compliant", (_, _) => 0, finished: null).Model());
        Assert.NotNull(Why(read, "w1"));
        Assert.Null(Why(read, "w3"));                                                     // the living room's fixed window
    }

    /// <summary>The turn into shared coordinates (true north 30 degrees, survey-scale offsets) changes nothing: the
    /// ground is read in shared coordinates, where the description is.</summary>
    [Fact]
    public void The_ground_is_read_in_shared_coordinates_whatever_the_turn()
    {
        var house = FakeHouse.Draw("5_basement_window_well", Transform3.TurnThenMove(Math.PI / 6, new Xyz(875000, -420000, 312)));
        house.Grounds = [house.Toposolid((_, _) => 0)];
        house.FinishedGround(true);
        Assert.Equal([0.0, 0.0, 0.0], Ground(InteriorReader.Read(house.Model()), "we1")!.Select(z => Math.Round(z, 6)));
    }
}
