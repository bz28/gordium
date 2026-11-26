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
        Assert.Equal(["a linked model"], Ids(site, "unsent"));
        Assert.Equal(["link"], Ids(site, "left_out"));
    }

    [Fact]
    public async Task A_link_holding_a_building_is_also_left_out_under_its_own_id_and_touches_nothing_of_itself()
    {
        // scene 19's reading (design note, section 1): unsent once, named by its kind (ids are unique), and each
        // such link left out under its UniqueId, as Rhino lists every block off the Building layer. Its own box is
        // no building's, so a link beside nothing touches nothing (Rhino's answer); the not_a_solid already makes
        // every building measure need review.
        var house = new RevitModel { Document = "house.rvt", Elements = [FakeRevit.Wall("w", [Block(15, 30, 45, 80)])] };
        var shed = new RevitModel { Document = "shed.rvt", Elements = [FakeRevit.Wall("s", [Block(20, 90, 30, 100)])] };
        var lotOnly = Box.Model("as drawn") with { Elements = [] };
        var site = await Site(lotOnly with { Elements = [FakeRevit.LinkOf("house_link", house), FakeRevit.LinkOf("shed_link", shed)] });
        var u = Assert.Single(site["unsent"]!.AsArray())!;
        Assert.Equal("a linked model", u["id"]!.GetValue<string>());
        Assert.Equal("not_a_solid", u["problem"]!["code"]!.GetValue<string>());
        Assert.Equal(["house_link", "shed_link"], Ids(site, "left_out"));
        Assert.False(LeftOut(site, "house_link")["touching"]!.GetValue<bool>());
        Assert.Empty(site["buildings"]!.AsArray());
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
            ["w_none"] = "a Walls element with no geometry", ["w_failed"] = "Walls", ["w_lines"] = "a Walls element with no geometry",
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
        // like a family, whatever it holds, even nothing (review round 1: an empty import was skipped as Ordinary)
        var empty = cad with { UniqueId = "cad_empty", Geometry = null, BoundingBox = null };
        Assert.Null(LeftOut(await Site(House(empty)), "cad_empty")["touching"]);
    }

    [Fact]
    public async Task A_coordination_model_is_left_out_as_touching_wherever_it_stands()
    {
        // review round 5: a Navisworks coordination model gives no geometry (Revit draws it for show only) yet may
        // hold a garage on the lot; it was skipped as an element with no geometry. Far off the lot, and whatever type
        // Revit gives its category, it still counts as on the lot and touching (contents not known, as a linked block)
        var nwc = new RevitElement { UniqueId = "nwc", BuiltInCategory = "OST_Coordination_Model", Category = "Coordination Model",
                                     Kind = ElementKind.CoordinationModel, CategoryType = CategoryType.Internal,
                                     BoundingBox = new RevitBox(new(1000, 1000, 0), new(1010, 1010, 10)) };
        var o = LeftOut(await Site(House(nwc)), "nwc");
        Assert.Null(o["touching"]);
        // inside a linked model too: its place can't be told, so the link has no box
        var far = FakeRevit.Directshape("far", [Block(1000, 1000, 1010, 1010)]);
        var doc = new RevitModel { Document = "consultant.rvt", Elements = [nwc, far] };
        Assert.Null(LeftOut(await Site(House(FakeRevit.LinkOf("link", doc))), "link")["touching"]);
    }

    [Fact]
    public async Task A_nested_family_of_lines_only_does_not_put_a_far_family_on_the_lot()
    {
        // review round 5: a nested family holding only lines (or only empty solids) was sent as a part with no box,
        // so a family 1000 ft off the lot counted as on it and touching; Walk skips such pieces, and so must Parts
        foreach (var inner in new GeometryItem[] { new LineworkItem(), new SolidItem([], []) })
        {
            var car = FakeRevit.Family("car", [Block(1000, 1000, 1010, 1010), new InstanceItem([inner])]);
            Assert.DoesNotContain("car", Ids(await Site(House(car)), "left_out"));
        }
        // a nested family that gives nothing still leaves it with no box (touching: null)
        var empty = FakeRevit.Family("car", [Block(1000, 1000, 1010, 1010), new InstanceItem([])]);
        Assert.Null(LeftOut(await Site(House(empty)), "car")["touching"]);
    }

    [Fact]
    public async Task An_element_whose_nested_geometry_gives_nothing_is_never_dropped()
    {
        // review round 1: a DirectShape (or a context object, or a curtain wall) whose only geometry is a nested
        // instance that gives nothing was skipped for having no faces; it has no box, so it counts as touching
        var ds = new RevitElement { UniqueId = "ds", BuiltInCategory = "OST_GenericModel", Category = "Generic Models",
                                    Geometry = [new InstanceItem(null)], BoundingBox = new RevitBox(new(20, 90, 0), new(30, 100, 10)) };
        var context = FakeRevit.Family("ctx", []) with { Mark = GordiumMark.Context, Geometry = [new InstanceItem(null)] };
        var site = await Site(House(ds, context));
        Assert.Null(LeftOut(site, "ds")["touching"]);
        Assert.Null(LeftOut(site, "ctx")["touching"]);
        Assert.True(LeftOut(site, "ctx")["context"]!.GetValue<bool>());
        var cw = new RevitElement { UniqueId = "cw", BuiltInCategory = "OST_Walls", Category = "Walls",
                                    Kind = ElementKind.CurtainWallHost, Geometry = [new InstanceItem(null)] };
        Assert.Equal(["cw"], Ids(await Site(House(cw)), "unsent"));
        // review round 2: a curtain wall whose geometry comes back null is reported like any wall, never dropped
        Assert.Equal(["cw"], Ids(await Site(House(cw with { Geometry = null })), "unsent"));
    }

    [Fact]
    public async Task A_shared_nested_family_is_read_as_part_of_its_host()
    {
        // Revit lists a shared nested family (a sub-component) as its own element, outside its host's geometry (trial,
        // 2026-11-19, scene 26): read alone, the shed touched nothing and its empty part was a third object
        var shed = FakeRevit.Family("shed", [Block(48, 90, 56, 98, 0, 8)]);
        var empty = FakeRevit.Family("part", [new SolidItem([], [])]) with { SuperComponent = "shed" };
        var site = await Site(House(shed, empty));
        Assert.DoesNotContain("part", Ids(site, "left_out"));
        Assert.Null(LeftOut(site, "shed")["touching"]);           // the part gives nothing: the shed's place can't be told

        // a part that reaches the house makes its host touch it
        var porch = FakeRevit.Family("porch", [Block(45, 79, 48, 90, 0, 8)]) with { SuperComponent = "shed" };
        site = await Site(House(shed, porch));
        Assert.DoesNotContain("porch", Ids(site, "left_out"));
        Assert.True(LeftOut(site, "shed")["touching"]!.GetValue<bool>());

        // a part whose geometry can't be read makes its host's unreadable
        var failed = FakeRevit.Family("bad", []) with { SuperComponent = "shed", GeometryFailed = true };
        site = await Site(House(shed, failed));
        Assert.Contains("shed", Ids(site, "unsent"));

        // a sub-component whose host isn't there is read on its own
        site = await Site(House(empty with { SuperComponent = "gone" }));
        Assert.Null(LeftOut(site, "part")["touching"]);
    }

    [Fact]
    public async Task A_part_drawn_only_at_a_coarser_detail_level_is_never_missed()
    {
        // design note section 8, "Detail level": a shed whose Fine solid stands 10 ft off the house but whose Coarse
        // drawing reaches it touches the house; read at Fine alone it touched nothing
        var shed = FakeRevit.Family("shed", [Block(48, 90, 56, 98, 0, 8)]) with { CoarserGeometry = [Block(45, 79, 56, 98, 0, 8)] };
        Assert.True(LeftOut(await Site(House(shed)), "shed")["touching"]!.GetValue<bool>());
        Assert.False(LeftOut(await Site(House(shed with { CoarserGeometry = null })), "shed")["touching"]!.GetValue<bool>());

        // a family with nothing at Fine keeps no box: its coarser drawing alone never gives it a place
        var empty = FakeRevit.Family("empty", [new SolidItem([], [])]) with { CoarserGeometry = [Block(48, 90, 56, 98, 0, 8)] };
        Assert.Null(LeftOut(await Site(House(empty)), "empty")["touching"]);

        // a building drawn bigger at Medium or Coarse: its faces are Fine's, and it says it may be bigger
        var door = FakeRevit.Family("door", [Block(20, 29, 23, 30, 0, 7)], "OST_Doors", "Doors");
        JsonObject Door(JsonObject site) => site["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "door")!.AsObject();
        Assert.Empty(Codes(Door(await Site(House(door with { CoarserGeometry = [Block(20, 29, 23, 30, 0, 7)] })))));
        var bigger = Door(await Site(House(door with { CoarserGeometry = [Block(20, 27, 23, 30, 0, 7)] })));
        Assert.Equal(["tool_words"], Codes(bigger));
        Assert.Equal(6, bigger["faces"]!.AsArray().Count);
    }

    [Fact]
    public async Task A_coarser_part_inside_the_buildings_box_but_off_its_solids_is_flagged()
    {
        // review round 1 (P0): an L-shaped door whose notch is filled at Coarse only; the notch is inside Fine's box,
        // so comparing boxes missed it
        var door = FakeRevit.Family("door", [Block(20, 29, 23, 30, 0, 7), Block(20, 30, 21, 33, 0, 7)], "OST_Doors", "Doors")
            with { CoarserGeometry = [Block(21, 30, 23, 33, 0, 7)] };
        var b = (await Site(House(door)))["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "door")!.AsObject();
        Assert.Equal(["tool_words"], Codes(b));
    }

    [Fact]
    public async Task A_part_nested_in_a_building_never_adds_its_coarser_drawing_as_faces()
    {
        // review round 1: a trim nested in a window was sent three times (Fine, Medium, Coarse) as the window's faces
        var win = FakeRevit.Family("win", [Block(20, 29, 23, 30, 3, 7)], "OST_Windows", "Windows")
            with { CoarserGeometry = [Block(20, 29, 23, 30, 3, 7)] };
        var trim = FakeRevit.Family("trim", [Block(20, 28, 23, 29, 3, 4)])
            with { SuperComponent = "win", CoarserGeometry = [Block(20, 28, 23, 29, 3, 4)] };
        var b = (await Site(House(win, trim)))["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "win")!.AsObject();
        Assert.Equal(12, b["faces"]!.AsArray().Count);
        Assert.Empty(Codes(b));
    }

    [Fact]
    public async Task A_part_nested_two_levels_down_in_a_building_never_adds_its_coarser_drawing_as_faces()
    {
        // review round 2: only the direct host was checked, so a bead in a trim in a window sent its coarser drawing
        // as the window's faces, never weighed
        var win = FakeRevit.Family("win", [Block(20, 29, 23, 30, 3, 7)], "OST_Windows", "Windows")
            with { CoarserGeometry = [Block(20, 29, 23, 30, 3, 7)] };
        var trim = FakeRevit.Family("trim", [Block(20, 28, 23, 29, 3, 4)]) with { SuperComponent = "win" };
        var bead = FakeRevit.Family("bead", [Block(20, 27.5, 23, 28, 3, 3.5)])
            with { SuperComponent = "trim", CoarserGeometry = [Block(20, 27.5, 23, 28, 3, 3.5)] };
        JsonObject Win(JsonObject site) => site["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "win")!.AsObject();
        var b = Win(await Site(House(win, trim, bead)));
        Assert.Equal(18, b["faces"]!.AsArray().Count);
        Assert.Empty(Codes(b));
        b = Win(await Site(House(win, trim, bead with { CoarserGeometry = [Block(20, 26, 23, 28, 3, 3.5)] })));
        Assert.Equal(18, b["faces"]!.AsArray().Count);
        Assert.Equal(["tool_words"], Codes(b));
    }

    [Fact]
    public async Task A_detailed_family_drawn_the_same_at_every_level_is_read_quickly()
    {
        // review round 2: every coarser point was compared with every Fine point, on Revit's own thread
        const int n = 300;
        var v = new List<Xyz>();
        for (var j = 0; j <= n; j++)
            for (var i = 0; i <= n; i++)
                v.Add(new Xyz(20 + 3.0 * i / n, 29 + 1.0 * j / n, 3));
        var t = new List<(int, int, int)>();
        for (var j = 0; j < n; j++)
            for (var i = 0; i < n; i++)
            {
                var a = j * (n + 1) + i;
                t.Add((a, a + 1, a + n + 2));
                t.Add((a, a + n + 2, a + n + 1));
            }
        var mesh = new MeshItem(v, t, false);
        var panel = FakeRevit.Family("panel", [mesh], "OST_Windows", "Windows") with { CoarserGeometry = [mesh] };
        var clock = System.Diagnostics.Stopwatch.StartNew();
        await Site(House(panel));
        Assert.True(clock.Elapsed.TotalSeconds < 20, $"took {clock.Elapsed.TotalSeconds:0.0} s");
    }

    [Fact]
    public async Task A_nested_part_shown_at_fine_only_draws_nothing_to_add()
    {
        // review round 1: a nested family giving nothing at Medium or Coarse made a door "bigger" and a shed's place
        // unknown, though Fine had read both
        var door = FakeRevit.Family("door", [Block(20, 29, 23, 30, 0, 7)], "OST_Doors", "Doors")
            with { CoarserGeometry = [Block(20, 29, 23, 30, 0, 7), new InstanceItem([])] };
        var b = (await Site(House(door)))["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "door")!.AsObject();
        Assert.Empty(Codes(b));
        var shed = FakeRevit.Family("shed", [Block(48, 90, 56, 98, 0, 8)])
            with { CoarserGeometry = [Block(48, 90, 56, 98, 0, 8), new InstanceItem(null)] };
        Assert.False(LeftOut(await Site(House(shed)), "shed")["touching"]!.GetValue<bool>());
    }

    [Fact]
    public async Task A_building_part_nested_in_a_family_is_still_a_building()
    {
        // review round 1: folded into a Generic Model kit, a shared nested window vanished into a left-out family,
        // and a linked model holding only such a window no longer counted as holding a building (a false pass)
        var kit = FakeRevit.Family("kit", [Block(48, 90, 52, 94)]);
        var window = FakeRevit.Family("win", [Block(48, 90, 50, 91)], "OST_Windows", "Windows") with { SuperComponent = "kit" };
        var site = await Site(House(kit, window));
        Assert.Contains("win", Ids(site, "buildings"));
        Assert.Contains("kit", Ids(site, "left_out"));

        var doc = new RevitModel { Document = "kit.rvt", Elements = [kit, window] };
        site = await Site(House(FakeRevit.LinkOf("link", doc)));
        Assert.Contains(SiteReader.LinkedModelKind, Ids(site, "unsent"));
    }

    [Fact]
    public async Task Sub_components_in_a_loop_are_each_read_on_their_own()
    {
        // review round 1: two elements each naming the other as its host were both dropped
        var a = FakeRevit.Family("a", [Block(48, 90, 56, 98, 0, 8)]) with { SuperComponent = "b" };
        var b = FakeRevit.Family("b", [Block(48, 100, 56, 108, 0, 8)]) with { SuperComponent = "a" };
        var site = await Site(House(a, b));
        Assert.Contains("a", Ids(site, "left_out"));
        Assert.Contains("b", Ids(site, "left_out"));
    }

    [Fact]
    public async Task A_nested_family_that_gives_an_empty_list_counts_as_missing_too()
    {
        // review round 2: GetInstanceGeometry() may give an empty list rather than null; both mean "nothing to read"
        var doc = new RevitModel { Document = "shed.rvt", Elements = [
            new RevitElement { UniqueId = "shed", BuiltInCategory = "OST_GenericModel", Category = "Generic Models",
                               Geometry = [Block(20, 105, 30, 115), new InstanceItem([])] }] };
        Assert.Null(LeftOut(await Site(House(FakeRevit.LinkOf("link", doc))), "link")["touching"]);
        var door = FakeRevit.Family("door", [Block(25, 29.5, 28, 30, 0, 7), new InstanceItem([])], "OST_Doors", "Doors");
        var b = (await Site(House(door)))["buildings"]!.AsArray().Single(x => x!["id"]!.GetValue<string>() == "door")!.AsObject();
        Assert.Equal(["tool_words"], Codes(b));
    }

    [Fact]
    public async Task A_link_holding_an_element_whose_nested_geometry_gives_nothing_has_no_box()
    {
        var doc = new RevitModel { Document = "shed.rvt", Elements = [Thing("shed", 20, 105, 30, 115),
            new RevitElement { UniqueId = "ds", BuiltInCategory = "OST_GenericModel", Category = "Generic Models",
                               Geometry = [new InstanceItem(null)] }] };
        Assert.Null(LeftOut(await Site(House(FakeRevit.LinkOf("link", doc))), "link")["touching"]);
    }

    [Fact]
    public async Task A_family_cad_import_or_toposolid_that_cant_be_read_is_reported_even_with_no_lot()
    {
        // review round 1: a Toposolid unread was placed by Revit's own box alone (off the lot here); review round 3:
        // left out with no box, it vanished when there was no lot (nothing is left out then). Not sent, it counts.
        var topo = new RevitElement { UniqueId = "topo", BuiltInCategory = "OST_Toposolid", Category = "Toposolid",
                                      Kind = ElementKind.Toposolid, GeometryFailed = true,
                                      BoundingBox = new RevitBox(new(100, 100, 0), new(101, 101, 1)) };
        var garage = FakeRevit.Family("garage", [Block(5, 40, 15, 60)]) with { IsInPlace = true, GeometryFailed = true };
        var cad = FakeRevit.Family("cad", [Block(20, 90, 30, 100), new OtherItem("PolyLine")]) with { Kind = ElementKind.CadImport };
        var site = await Site(House(topo, garage, cad) with { LotLines = [] });
        Assert.Null(site["lot"]);
        Assert.Equal(["topo", "garage", "cad"], Ids(site, "unsent"));
        Assert.Equal(["topo", "garage", "cad"], Ids(await Site(House(topo, garage, cad)), "unsent"));
    }

    [Fact]
    public async Task A_link_is_looked_at_whatever_type_Revit_gives_its_category()
    {
        var gone = new RevitModel { Document = "house.rvt" };
        var link = FakeRevit.LinkOf("link", gone, status: "Unloaded") with { CategoryType = CategoryType.Internal };
        Assert.False((await Site(House(link)))["inventory_complete"]!.GetValue<bool>());
        var cad = FakeRevit.Family("cad", [Block(20, 90, 30, 100)]) with { Kind = ElementKind.CadImport, CategoryType = CategoryType.Internal };
        Assert.Equal(["cad"], Ids(await Site(House(cad)), "left_out"));
    }

    [Fact]
    public async Task A_toposolid_is_left_out_and_never_labelled_as_the_ground()
    {
        var topo = new RevitElement { UniqueId = "topo", BuiltInCategory = "OST_Toposolid", Category = "Toposolid",
                                      Kind = ElementKind.Toposolid, Geometry = [F.Prism(Rect(-5, -5, 65, 125), -3, 0, open: true)] };
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

    // Snowdon Towers (Revit 2027): a full-circle model line has no ends (Curve.IsBound false), and reading it failed
    // the whole check. The Revit layer now only counts such a curve (LotLineElement.Unbound); here is what it means.
    private static readonly LotLineElement Circle = new("pl-circle", true, [], Unbound: 1);

    private static List<string> Words(JsonObject site) =>
        site["problems"]!.AsArray().Select(p => p!["code"]!.GetValue<string>() == "tool_words"
            ? p["args"]!["words"]!.GetValue<string>() : p["code"]!.GetValue<string>()).ToList();

    [Fact]
    public async Task A_lot_line_with_a_curve_with_no_ends_leaves_the_lot_unread_never_read_without_it()
    {
        // alone, nothing picked: it may be the lot (a circle is closed), so the lot needs review, saying why
        var alone = await Site(Lots(Circle));
        Assert.Null(alone["lot"]);
        Assert.Equal([LotReader.UnboundPropertyLine], Words(alone));
        // beside one closed property line: never dropped, so the other is never taken as "the one"
        var beside = await Site(Lots(Lot, Circle));
        Assert.Null(beside["lot"]);
        Assert.Equal([LotReader.UnboundPropertyLine], Words(beside));
        // its other curves closing by themselves: never read as the lot without the curve left out
        var part = await Site(Lots(Lot with { UniqueId = "pl-part", Unbound = 1 }));
        Assert.Null(part["lot"]);
        Assert.Equal([LotReader.UnboundPropertyLine], Words(part));
        // the architect picked the other lot: that one is read (the pick says which lot it is)
        var picked = await Site(Lots(Lot, Circle), With("pl-lot"));
        Assert.Equal("pl-lot", picked["lot"]!["id"]!.GetValue<string>());
        Assert.Empty(Problems(picked));
        // picked itself, or a full-circle model line picked: the lot needs review, saying why (not "lot_not_found")
        Assert.Equal([LotReader.UnboundPicked], Words(await Site(Lots(Lot, Circle), With("pl-circle"))));
        var ml = new LotLineElement("ml-circle", false, [], Unbound: 1);
        var withModelLine = await Site(House() with { LotLines = [Lot, ml] }, With("ml-circle"));
        Assert.Null(withModelLine["lot"]);
        Assert.Equal([LotReader.UnboundPicked], Words(withModelLine));
        // a full-circle model line nobody picked is no lot line at all: the one property line is the lot
        Assert.Equal("pl-lot", (await Site(House() with { LotLines = [Lot, ml] }))["lot"]!["id"]!.GetValue<string>());
    }

    [Fact]
    public void The_Revit_layer_reads_a_lot_curve_s_ends_only_when_it_has_ends()
    {
        // only Revit can say IsBound, so the guard lives in RevitRead (pinned by its text): every property line's and
        // model line's curve goes through LotLine, which reads the bound ones and counts the rest
        var src = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "RevitRead.cs"));
        Assert.Contains("curves.Where(c => c.IsBound).Select(Curve).ToList(), curves.Count(c => !c.IsBound)", src, StringComparison.Ordinal);
        Assert.Contains("lines.Add(LotLine(pl.UniqueId, true, pl.GetBoundary().SelectMany(loop => loop).ToList()));", src, StringComparison.Ordinal);
        Assert.Contains("lines.Add(LotLine(ce.UniqueId, false, [c]));", src, StringComparison.Ordinal);
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(src, @"Select\(Curve\)|Curve\(c\)"));
    }

    [Fact]
    public async Task No_lot_and_a_lot_no_longer_there()
    {
        Assert.Equal(["no_lot_outline"], Problems(await Site(Lots())));
        Assert.Equal(["lot_not_found"], Problems(await Site(Lots(Lot), With("deleted"))));
    }

    [Fact]
    public async Task A_property_line_in_a_linked_model_makes_the_lot_need_review()
    {
        // review round 4: the lot may be the link's, not the host's (Rhino: lot_block, a block holding Site objects)
        var site = new RevitModel { Document = "site.rvt", LotLines = [F.PropertyLine("pl-linked", Rect(0, 0, 60, 125))] };
        var outer = new RevitModel { Document = "outer.rvt", Elements = [FakeRevit.LinkOf("site", site)] };
        foreach (var facts in new[] { Box.Facts, With("pl-lot") })
        {
            var read = await Site(House(FakeRevit.LinkOf("link", outer)), facts);
            Assert.Equal("pl-lot", read["lot"]!["id"]!.GetValue<string>());
            Assert.Equal(["lot_block"], Problems(read));
        }
        Assert.Empty(Problems(await Site(House())));
    }

    [Fact]
    public async Task An_element_with_no_category_that_cant_be_read_is_still_a_valid_description()
    {
        // review round 4: an empty kind would have the whole description refused
        var odd = new RevitElement { UniqueId = "odd", BuiltInCategory = "", Category = "", GeometryFailed = true };
        var site = await Site(House(odd));
        Assert.Equal("an element with no category", Assert.Single(site["unsent"]!.AsArray())!["kind"]!.GetValue<string>());
        var result = await (await worker.RunningAsync()).CheckSiteAsync(site, Box.Facts);
        Assert.NotEmpty(result.Items);
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
        Assert.Throws<Gordium.Worker.WorkerProtocolException>(() => WorkerLeftOut.Read(objects, E("[]"), E("""[{"id":"a","touching":null}]""")));
        Assert.Throws<Gordium.Worker.WorkerProtocolException>(() => WorkerLeftOut.Read(objects, E("""[{"id":"b","left_out":true}]"""), E("""[{"id":"a","touching":true}]""")));
        Assert.Throws<Gordium.Worker.WorkerProtocolException>(() => WorkerLeftOut.Read(objects, E("""[{"id":"a","left_out":1}]"""), E("""[{"id":"a","touching":true}]""")));
        Assert.Throws<Gordium.Worker.WorkerProtocolException>(() => WorkerLeftOut.Read(objects, E("""[{"id":"a","left_out":true}]"""), E("""[{"id":"a"}]""")));
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
