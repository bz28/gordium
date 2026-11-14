using System.Text.Json;
using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The reader's Revit-only decisions (design note, sections 1 to 5), each pinned on fake records built as
/// the design note says the Revit API gives them. No conformance scene covers these yet (the note's proposed scenes
/// A to K); each test names its scene. Every one is <b>to confirm on Windows</b>: the logic is what the note says,
/// but whether Revit's API gives the records these fakes give (a phase's id, an option's primary flag, a closed
/// workset, a link's status, a curtain wall's own faces) is the trial's to check.</summary>
public sealed class ReaderTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly FakeRevit F = new(Transform3.Identity);
    private static readonly SceneDrawing Box = SceneDrawing.Named("01_box_house");

    /// <summary>Scene 01 (the 60 × 120 ft lot, the 30 × 50 ft house of two floor blocks) with more elements.</summary>
    private static RevitModel House(params RevitElement[] more) => Box.Model("as drawn") is var m
        ? m with { Elements = [.. m.Elements, .. more] } : null!;

    private static List<(double X, double Y)> Rect(double x0, double y0, double x1, double y1) =>
        [(x0, y0), (x1, y0), (x1, y1), (x0, y1)];

    private static SolidItem Block(double x0, double y0, double x1, double y1, double z0 = 0, double z1 = 10) =>
        F.Prism(Rect(x0, y0, x1, y1), z0, z1);

    /// <summary>A Generic Model DirectShape: anything that could be a building and isn't one.</summary>
    private static RevitElement Thing(string id, double x0, double y0, double x1, double y1) =>
        FakeRevit.Directshape(id, [Block(x0, y0, x1, y1)]);

    private async Task<JsonObject> Site(RevitModel m, JsonObject? facts = null) =>
        (await ReadAsync(m, facts)).Site;

    private async Task<ReadResult> ReadAsync(RevitModel m, JsonObject? facts = null) =>
        await SiteReader.DescribeAsync(m, facts ?? Box.Facts, new WorkerLeftOut(await worker.RunningAsync()));

    private static List<string> Ids(JsonObject site, string key) =>
        site[key]!.AsArray().Select(o => o!["id"]!.GetValue<string>()).ToList();

    private static JsonObject LeftOut(JsonObject site, string id) =>
        site["left_out"]!.AsArray().Single(o => o!["id"]!.GetValue<string>() == id)!.AsObject();

    private static List<string> Codes(JsonObject building) =>
        building["problems"]!.AsArray().Select(p => p!["code"]!.GetValue<string>()).ToList();

    // ---- phases (new scene C) ----------------------------------------------------------------------------------

    [Fact]
    public async Task Phases_only_what_is_gone_by_the_last_phase_is_left_off()
    {
        var m = House(
            Thing("shed", 20, 90, 30, 100) with { PhaseCreated = "existing", PhaseDemolished = "new" },     // demolished now
            Thing("old_shed", 46, 100, 56, 110) with { PhaseCreated = "existing", PhaseDemolished = "existing" }, // before
            Thing("temp", 2, 100, 8, 110) with { PhaseCreated = "new", PhaseDemolished = "new" },          // temporary
            Thing("garage", 20, 102, 44, 118) with { PhaseCreated = "existing" },                          // existing, stays
            Thing("no_phase", 48, 30, 56, 38),                                                              // no phase
            Thing("odd_phase", 48, 40, 56, 48) with { PhaseDemolished = "a phase not in the list" }) with
        {
            Phases = ["existing", "new"],
        };
        var read = await ReadAsync(m);
        Assert.Equal(["garage", "no_phase", "odd_phase"], Ids(read.Site, "left_out"));
        Assert.Equal("new", read.PhaseChecked);
    }

    // ---- design options (new scene D) --------------------------------------------------------------------------

    [Fact]
    public async Task Design_options_the_main_model_and_one_option_from_every_set()
    {
        var m = House(
            Thing("wing_narrow", 45, 40, 50, 60) with { DesignOption = "w1" },
            Thing("wing_wide", 45, 40, 55, 60) with { DesignOption = "w2" },
            Thing("garage_a", 20, 95, 44, 118) with { DesignOption = "g1" },
            Thing("unknown_option", 2, 100, 8, 110) with { DesignOption = "not in any set" }) with
        {
            OptionSets = [new("wing", "Wing", [new("w1", "Narrow", true), new("w2", "Wide", false)]),
                          new("garage", "Garage", [new("g1", "Two-car", true)])],
            ActiveOption = "w2",
        };
        var read = await ReadAsync(m);
        Assert.Equal(["wing_wide", "garage_a", "unknown_option"], Ids(read.Site, "left_out"));
        Assert.Equal(["Wing: Wide", "Garage: Two-car"], read.OptionsChecked);
    }

    [Fact]
    public async Task Design_options_with_none_being_edited_each_sets_primary()
    {
        var m = House(Thing("wing_narrow", 45, 40, 50, 60) with { DesignOption = "w1" },
                      Thing("wing_wide", 45, 40, 55, 60) with { DesignOption = "w2" }) with
        {
            OptionSets = [new("wing", "Wing", [new("w1", "Narrow", false), new("w2", "Wide", true)])],
        };
        Assert.Equal(["wing_wide"], Ids(await Site(m), "left_out"));
    }

    // ---- worksets and links (new scene B) ----------------------------------------------------------------------

    [Fact]
    public async Task A_closed_user_workset_means_not_everything_was_looked_at()
    {
        var open = House() with { UserWorksets = [new("1", "Shared Levels and Grids", true)] };
        Assert.True((await Site(open))["inventory_complete"]!.GetValue<bool>());
        var closed = open with { UserWorksets = [new("1", "Shared Levels and Grids", true), new("2", "Site", false)] };
        Assert.False((await Site(closed))["inventory_complete"]!.GetValue<bool>());
    }

    [Fact]
    public async Task A_link_not_loaded_means_not_everything_was_looked_at()
    {
        var doc = new RevitModel { Document = "house.rvt" };
        var site = await Site(House(FakeRevit.LinkOf("link", doc, status: "Unloaded")));
        Assert.False(site["inventory_complete"]!.GetValue<bool>());
        Assert.Empty(site["unsent"]!.AsArray());
        Assert.Empty(site["left_out"]!.AsArray());
    }

    [Fact]
    public async Task A_link_holding_a_building_element_at_any_depth_is_not_sent_wherever_it_is()
    {
        // the wall two links deep, and the link placed far off the lot: still every building measure needs review
        var inner = new RevitModel { Document = "inner.rvt", Elements = [FakeRevit.Wall("w", [Block(0, 0, 1, 10)])] };
        var outer = new RevitModel { Document = "outer.rvt", Elements = [FakeRevit.LinkOf("inner", inner)] };
        var site = await Site(House(FakeRevit.LinkOf("link", outer, at: Transform3.Translation(new(5000, 5000, 0)))));
        var u = Assert.Single(site["unsent"]!.AsArray())!;
        Assert.Equal("a linked model", u["kind"]!.GetValue<string>());
        Assert.Equal("not_a_solid", u["problem"]!["code"]!.GetValue<string>());
        Assert.True(site["inventory_complete"]!.GetValue<bool>());
    }

    [Fact]
    public async Task A_link_with_a_closed_workset_of_its_own_is_not_sent()
    {
        var doc = new RevitModel { Document = "site.rvt", UserWorksets = [new("9", "Hidden", false)],
                                   Elements = [Thing("shed", 20, 90, 30, 100)] };
        var site = await Site(House(FakeRevit.LinkOf("link", doc)));
        Assert.Equal(["link"], Ids(site, "unsent"));
    }

    [Fact]
    public async Task A_link_with_no_building_element_is_left_out_like_a_family()
    {
        var doc = new RevitModel { Document = "shed.rvt", Elements = [Thing("shed", 20, 90, 30, 100)] };
        var site = await Site(House(FakeRevit.LinkOf("link", doc)));
        var o = LeftOut(site, "link");
        Assert.False(o["touching"]!.GetValue<bool>());
        Assert.False(o["ground_like"]!.GetValue<bool>());
        Assert.Empty(site["unsent"]!.AsArray());
    }

    [Fact]
    public async Task A_link_holding_a_link_not_loaded_has_no_box_and_not_everything_was_looked_at()
    {
        var gone = new RevitModel { Document = "gone.rvt" };
        var doc = new RevitModel { Document = "shed.rvt",
                                   Elements = [Thing("shed", 20, 90, 30, 100), FakeRevit.LinkOf("overlay", gone, status: "NotFound")] };
        var site = await Site(House(FakeRevit.LinkOf("link", doc)));
        Assert.False(site["inventory_complete"]!.GetValue<bool>());
        Assert.Null(LeftOut(site, "link")["touching"]);              // no box: counts as touching
    }

    // ---- the element kinds (new scenes A and H) ----------------------------------------------------------------

    [Fact]
    public async Task A_curtain_wall_sends_its_own_faces_only_if_it_has_any()
    {
        var host = new RevitElement { UniqueId = "cw", BuiltInCategory = "OST_Walls", Category = "Walls",
                                      Kind = ElementKind.CurtainWallHost, Geometry = [] };
        var panel = new RevitElement { UniqueId = "panel", BuiltInCategory = "OST_CurtainWallPanels", Category = "Curtain Panels",
                                       Geometry = [Block(15, 29.9, 45, 30)] };
        var site = await Site(House(host, panel));
        Assert.Contains("panel", Ids(site, "buildings"));
        Assert.DoesNotContain("cw", Ids(site, "buildings"));
        Assert.Empty(site["unsent"]!.AsArray());
        var withFaces = host with { Geometry = [Block(15, 29.5, 45, 30)] };
        Assert.Contains("cw", Ids(await Site(House(withFaces)), "buildings"));
    }

    [Fact]
    public async Task A_model_group_is_never_read_itself()
    {
        var group = new RevitElement { UniqueId = "g", BuiltInCategory = "OST_IOSModelGroups", Category = "Model Groups",
                                       Kind = ElementKind.Group, GeometryFailed = true };
        var site = await Site(House(group));
        Assert.Empty(site["unsent"]!.AsArray());
        Assert.Empty(site["left_out"]!.AsArray());
    }

    [Fact]
    public async Task An_in_place_family_goes_by_its_category()
    {
        var wall = FakeRevit.Family("ip_wall", [Block(15, 80, 45, 81, 0, 20)], "OST_Walls", "Walls") with { IsInPlace = true };
        var shed = FakeRevit.Family("ip_shed", [Block(20, 90, 30, 100)]) with { IsInPlace = true };
        var site = await Site(House(wall, shed));
        Assert.Contains("ip_wall", Ids(site, "buildings"));
        Assert.Equal(["ip_shed"], Ids(site, "left_out"));
    }

    [Fact]
    public async Task An_empty_family_on_the_lot_is_left_out_and_counts_as_touching()
    {
        var empty = FakeRevit.Family("empty", []) with { BoundingBox = new RevitBox(new(20, 90, 0), new(30, 100, 10)) };
        var nothing = FakeRevit.Family("nothing", []) with { Geometry = null };
        var nestedGone = FakeRevit.Family("nested_gone", [Block(20, 105, 30, 115), new InstanceItem(null)]);
        var nestedEmpty = FakeRevit.Family("nested_empty", [Block(46, 105, 56, 115), new InstanceItem([])]);
        var site = await Site(House(empty, nothing, nestedGone, nestedEmpty));
        foreach (var id in new[] { "empty", "nothing", "nested_gone", "nested_empty" })
            Assert.Null(LeftOut(site, id)["touching"]);
    }

    [Fact]
    public async Task A_family_that_holds_its_geometry_is_placed_by_it()
    {
        var shed = FakeRevit.Family("shed", [Block(20, 105, 30, 115), new InstanceItem([Block(31, 105, 33, 107)])]);
        Assert.False(LeftOut(await Site(House(shed)), "shed")["touching"]!.GetValue<bool>());
    }

    [Fact]
    public async Task A_building_element_with_nothing_to_send_is_never_skipped()
    {
        var none = new RevitElement { UniqueId = "w_none", BuiltInCategory = "OST_Walls", Category = "Walls" };
        var failed = none with { UniqueId = "w_failed", GeometryFailed = true };
        var lines = none with { UniqueId = "w_lines", Geometry = [new LineworkItem()] };
        var other = none with { UniqueId = "w_other", Geometry = [Block(15, 80, 45, 81), new OtherItem("PolyLine")] };
        var site = await Site(House(none, failed, lines, other));
        var unsent = site["unsent"]!.AsArray().ToDictionary(u => u!["id"]!.GetValue<string>(), u => u!["kind"]!.GetValue<string>());
        Assert.Equal(new Dictionary<string, string>
        {
            ["w_none"] = "a Walls with no geometry", ["w_failed"] = "Walls", ["w_lines"] = "a Walls with no geometry",
            ["w_other"] = "Walls",
        }, unsent);
        Assert.All(site["unsent"]!.AsArray(), u => Assert.Equal("not_a_solid", u!["problem"]!["code"]!.GetValue<string>()));
    }

    [Fact]
    public async Task A_building_with_an_empty_solid_beside_its_real_one_is_read_from_the_real_one()
    {
        var wall = FakeRevit.Wall("w", [new SolidItem([], []), Block(15, 80, 45, 81, 0, 20)]);
        var b = (await Site(House(wall)))["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "w")!.AsObject();
        Assert.Equal(6, b["faces"]!.AsArray().Count);
        Assert.Empty(Codes(b));
    }

    [Fact]
    public async Task A_building_whose_nested_family_gives_nothing_says_so()
    {
        var door = FakeRevit.Family("door", [Block(25, 29.5, 28, 30, 0, 7), new InstanceItem(null)], "OST_Doors", "Doors");
        var b = (await Site(House(door)))["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "door")!.AsObject();
        Assert.Equal(["tool_words"], Codes(b));
    }

    [Fact]
    public async Task Elements_that_are_not_model_objects_are_not_looked_at()
    {
        var failed = new RevitElement { UniqueId = "x", BuiltInCategory = "OST_GenericModel", Category = "Generic Models", GeometryFailed = true };
        var site = await Site(House(
            failed with { UniqueId = "tag", CategoryType = CategoryType.Annotation },
            failed with { UniqueId = "cad2d", Kind = ElementKind.CadImport, ViewSpecific = true },
            failed with { UniqueId = "room", BuiltInCategory = "OST_Rooms", Category = "Rooms" },
            new RevitElement { UniqueId = "no_geometry", BuiltInCategory = "OST_GenericModel", Category = "Generic Models" },
            new RevitElement { UniqueId = "curves", BuiltInCategory = "OST_GenericModel", Category = "Generic Models", Geometry = [new LineworkItem()] }));
        Assert.Empty(site["unsent"]!.AsArray());
        Assert.Empty(site["left_out"]!.AsArray());
        // a model element whose geometry can't be read is reported, never dropped
        Assert.Equal(["x"], Ids(await Site(House(failed)), "unsent"));
    }

    [Fact]
    public async Task A_cad_import_on_the_lot_is_left_out()
    {
        var cad = FakeRevit.Family("cad", [Block(20, 90, 30, 100)]) with { Kind = ElementKind.CadImport, Category = "shed.dwg" };
        Assert.Equal(["cad"], Ids(await Site(House(cad)), "left_out"));
    }

    [Fact]
    public async Task A_toposolid_is_left_out_and_never_labelled_as_the_ground()
    {
        var topo = new RevitElement { UniqueId = "topo", BuiltInCategory = "OST_Toposolid", Category = "Toposolid",
                                      Kind = ElementKind.Toposolid, Geometry = [Block(-5, -5, 65, 125, -3, 0)] };
        topo = topo with { BoundingBox = FakeRevit.BoxOf(topo.Geometry!) };
        var o = LeftOut(await Site(House(topo)), "topo");
        Assert.True(o["touching"]!.GetValue<bool>());
        Assert.False(o["ground_like"]!.GetValue<bool>());
    }

    [Fact]
    public async Task A_mesh_is_open_unless_Revit_says_it_is_closed()
    {
        var mesh = F.Grid((15, 80), (45, 81), 0, 2);
        var site = await Site(House(FakeRevit.Wall("m_open", [mesh]), FakeRevit.Wall("m_closed", [mesh with { IsClosed = true }])));
        var b = site["buildings"]!.AsArray().ToDictionary(x => x!["id"]!.GetValue<string>(), x => x!.AsObject());
        Assert.Equal(["open_mesh"], Codes(b["m_open"]));
        Assert.Empty(Codes(b["m_closed"]));
        Assert.Equal(8, b["m_closed"]["faces"]!.AsArray().Count);
    }

    // ---- faces ---------------------------------------------------------------------------------------------------

    [Fact]
    public void A_face_with_a_hole_has_its_largest_loop_as_its_outline_whichever_comes_first()
    {
        LoopCurve L(double x, double y) => new(new(x, y, 0), true);
        var hole = new List<LoopCurve> { L(2, 2), L(4, 2), L(4, 4), L(2, 4) };
        var outer = new List<LoopCurve> { L(0, 0), L(10, 0), L(10, 10), L(0, 10) };
        var e = new RevitElement { UniqueId = "slab", BuiltInCategory = "OST_Floors", Category = "Floors" };
        var g = Read.Walk([new SolidItem([new FaceRecord("PlanarFace", [hole, outer], [])], [])], Transform3.Identity, e);
        var face = Assert.Single(g.Faces);
        Assert.Equal(10.0, face["points"]![1]![0]!.GetValue<double>());
        Assert.Equal(2.0, face["holes"]![0]![0]![0]!.GetValue<double>());
    }

    [Fact]
    public void A_curved_face_or_edge_is_reported_never_sent()
    {
        var e = new RevitElement { UniqueId = "w", BuiltInCategory = "OST_Walls", Category = "Walls", Name = "Curved wall" };
        var curved = F.Prism(Rect(0, 0, 10, 10), 0, 10, curvedEdge: 2, through: (5, 12));
        var g = Read.Walk([curved], Transform3.Identity, e);
        Assert.Equal(3, g.Faces.Count);                            // three flat walls; the curved wall, floor and roof not
        Assert.Equal(["curved_surface", "curved_edge"], g.Problems.Select(p => p["code"]!.GetValue<string>()));
        var open = Read.Walk([F.Prism(Rect(0, 0, 10, 10), 0, 10, open: true)], Transform3.Identity, e);
        Assert.Equal("Curved wall", Assert.Single(open.Problems)["args"]!["what"]!.GetValue<string>());
    }

    // ---- coordinates (new scene J) --------------------------------------------------------------------------------

    [Fact]
    public void A_box_turned_30_degrees_is_turned_by_all_8_corners_and_never_shrinks()
    {
        var t = Transform3.TurnThenMove(Math.PI / 6, new(875000, 885000, 820));
        var b = Box3.Turned(new(0, 0, 0), new(30, 50, 20), t);
        foreach (var x in new[] { 0.0, 30 })
            foreach (var y in new[] { 0.0, 50 })
            {
                var p = t.Apply(new(x, y, 20));
                Assert.InRange(p.X, b.Min.X, b.Max.X);
                Assert.InRange(p.Y, b.Min.Y, b.Max.Y);
            }
        // the box around two opposite corners alone would be 30 cos 30° - 50 sin 30° = 0.98 ft wide: far too small
        Assert.Equal(30 * Math.Cos(Math.PI / 6) + 50 * Math.Sin(Math.PI / 6), b.Max.X - b.Min.X, 9);
        Assert.Equal(820.0, b.Min.Z, 9);
    }

    [Fact]
    public async Task On_a_model_turned_30_degrees_Revits_own_boxes_grow_so_more_reads_as_touching()
    {
        // Scene 15 turned 30°: Revit's box for each element is square to its internal axes, so turned into shared
        // coordinates it is bigger than the element. The context solid 15 ft behind the house then reads as touching:
        // the cautious side (more review), which the trial's scene J hand-works (design note, section 7).
        var scene = SceneDrawing.Named("15_objects_left_out_touching_on_context_and_a_block");
        var site = (await SiteReader.DescribeAsync(scene.Model("as drawn", Math.PI / 6), scene.Facts,
                                                   new WorkerLeftOut(await worker.RunningAsync()))).Site;
        Assert.True(LeftOut(site, "uid-porch")["touching"]!.GetValue<bool>());
        Assert.True(LeftOut(site, "uid-neighbour_solid")["touching"]!.GetValue<bool>());
    }

    // ---- the lot (new scene G) ----------------------------------------------------------------------------------

    private static RevitModel Lots(params LotLineElement[] lines) => House() with { LotLines = lines };

    private static readonly LotLineElement Lot = F.PropertyLine("pl-lot", Rect(0, 0, 60, 120));
    private static readonly LotLineElement East = F.PropertyLine("pl-east", Rect(60, 0, 120, 120));

    private static LotLineElement Open(string id) =>
        new(id, true, F.PropertyLine(id, Rect(0, 0, 60, 120)).Curves.Take(3).ToList());

    private static JsonObject With(string lotId) => Box.Facts is var f ? Set(f, "lot_id", lotId) : null!;

    private static JsonObject Set(JsonObject o, string k, JsonNode? v)
    {
        o[k] = v;
        return o;
    }

    private static List<string> Problems(JsonObject site) =>
        site["problems"]!.AsArray().Select(p => p!["code"]!.GetValue<string>()).ToList();

    [Fact]
    public async Task The_lot_picked_is_the_lot_even_among_several()
    {
        var site = await Site(Lots(Lot, East), With("pl-lot"));
        Assert.Equal("pl-lot", site["lot"]!["id"]!.GetValue<string>());
        Assert.Empty(Problems(site));
        var none = await Site(Lots(Lot, East));
        Assert.Null(none["lot"]);
        Assert.Equal(["several_lot_outlines"], Problems(none));
        Assert.Equal("2", none["problems"]![0]!["args"]!["count"]!.GetValue<string>());
    }

    [Fact]
    public async Task Lines_picked_as_the_lot_join_whichever_way_each_runs()
    {
        var c = Lot.Curves;
        var lines = new[]
        {
            new LotLineElement("l1", false, [c[0]]),
            new LotLineElement("l2", false, [new LotCurve(c[2].End, c[2].Start, true)]),   // drawn backwards
            new LotLineElement("l3", false, [c[1]]),                                        // out of order
            new LotLineElement("l4", false, [c[3]]),
        };
        var site = await Site(House() with { LotLines = lines }, With("l1+l2+l3+l4"));
        Assert.Equal("l1+l2+l3+l4", site["lot"]!["id"]!.GetValue<string>());
        Assert.Equal(4, site["lot"]!["edges"]!.AsArray().Count);
        var notClosed = await Site(House() with { LotLines = lines }, With("l1+l2+l3"));
        Assert.Equal(["lot_not_found"], Problems(notClosed));
    }

    [Fact]
    public async Task An_open_property_line_is_never_a_lot()
    {
        Assert.Equal(["no_lot_outline"], Problems(await Site(Lots(Open("pl-open")))));
        Assert.Equal(["lot_not_found"], Problems(await Site(Lots(Open("pl-open")), With("pl-open"))));
        // beside one closed property line, the open one counts for nothing: the closed one is the lot
        Assert.Equal("pl-lot", (await Site(Lots(Lot, Open("pl-open"))))["lot"]!["id"]!.GetValue<string>());
    }

    [Fact]
    public async Task No_lot_and_a_lot_no_longer_there()
    {
        Assert.Equal(["no_lot_outline"], Problems(await Site(Lots())));
        Assert.Equal(["lot_not_found"], Problems(await Site(Lots(Lot), With("deleted"))));
    }

    [Fact]
    public void Two_loops_that_share_a_corner_are_not_one_lot()
    {
        var a = F.PropertyLine("a", Rect(0, 0, 10, 10)).Curves;
        var b = F.PropertyLine("b", Rect(10, 10, 20, 20)).Curves;
        Assert.Null(LotReader.Loop([.. a, .. b], 1e-6));
        Assert.NotNull(LotReader.Loop([.. a], 1e-6));
    }

    // ---- the ground -----------------------------------------------------------------------------------------------

    private static RevitElement Marker(string id, GordiumMark mark, double z) => new()
    {
        UniqueId = id, BuiltInCategory = "OST_GenericModel", Category = "Generic Models", Mark = mark, Location = new(30, 20, z),
    };

    [Fact]
    public async Task The_grade_comes_from_the_markers_the_facts_name_never_both()
    {
        var m = House(Marker("s", GordiumMark.SpotGrade, 1), Marker("f", GordiumMark.FinishedGrade, 2));
        JsonObject Facts(string? from)
        {
            var f = Box.Facts;
            f.Remove("ground_is_flat");
            f.Remove("grade_elevation");
            return Set(f, "grade_from", from);
        }
        var spot = (await Site(m, Facts("spot")))["grade"]!;
        Assert.Equal("spot", spot["source"]!.GetValue<string>());
        Assert.Equal(1.0, spot["points"]![0]![2]!.GetValue<double>());
        var finished = (await Site(m, Facts("finished_spots")))["grade"]!;
        Assert.Equal("finished_spots", finished["source"]!.GetValue<string>());
        Assert.Equal(2.0, Assert.Single(finished["points"]!.AsArray())![2]!.GetValue<double>());
        Assert.Equal("none", (await Site(m))["grade"]!["source"]!.GetValue<string>());
        await Assert.ThrowsAsync<ReadRefusedException>(() => Site(m, Facts("terrain")));
        await Assert.ThrowsAsync<ReadRefusedException>(() => Site(House(Marker("s", GordiumMark.SpotGrade, 1) with { Location = null }), Facts("spot")));
    }

    // ---- reading the worker's answer --------------------------------------------------------------------------------

    [Fact]
    public void The_workers_left_out_answer_is_read_strictly()
    {
        var objects = new JsonArray(new JsonObject { ["id"] = "a" });
        JsonElement E(string json) => JsonDocument.Parse(json).RootElement;
        Assert.Single(WorkerLeftOut.Read(objects, E("""[{"id":"a","left_out":true,"why":"on_lot"}]"""), E("""[{"id":"a","touching":null}]""")));
        Assert.Throws<InvalidOperationException>(() => WorkerLeftOut.Read(objects, E("[]"), E("""[{"id":"a","touching":null}]""")));
        Assert.Throws<InvalidOperationException>(() => WorkerLeftOut.Read(objects, E("""[{"id":"b","left_out":true}]"""), E("""[{"id":"a","touching":true}]""")));
        Assert.Throws<InvalidOperationException>(() => WorkerLeftOut.Read(objects, E("""[{"id":"a","left_out":1}]"""), E("""[{"id":"a","touching":true}]""")));
        Assert.Throws<InvalidOperationException>(() => WorkerLeftOut.Read(objects, E("""[{"id":"a","left_out":true}]"""), E("""[{"id":"a"}]""")));
    }

    [Fact]
    public void A_floor_blocks_height_is_read_from_its_mark_or_not_at_all()
    {
        Assert.Equal(10.5, Read.FloorHeight("2;10.5"));
        Assert.Null(Read.FloorHeight("2"));
        Assert.Null(Read.FloorHeight("2;tall"));
        Assert.Null(Read.FloorHeight(null));
    }
}
