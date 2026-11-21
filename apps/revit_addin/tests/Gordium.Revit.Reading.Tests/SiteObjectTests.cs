using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Objects standing apart (reading design note, section 1): a freestanding deck, porch, landing or ramp drawn
/// as a Generic Model or a family of another category, apart from the house, is left out (never measured) and touches
/// nothing, so the yards complied while it stood unmeasured in a required yard (the gap PR #135 left). The law:
/// "All porches, attached or freestanding decks, ... ramps, and/or landings shall be considered a part of the building
/// in both the determination of required yards and lot coverage" (§325-18A); a YARD "shall not be occupied by any other
/// building or structure from the ground upward" (§325-3B); a STRUCTURE is "Anything constructed or erected on the
/// ground" (§325-3B). Scene 01's box house (every measure complies) with one object 10 ft behind it, on the lot.</summary>
public sealed class SiteObjectTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly FakeRevit F = new(Transform3.Identity);
    private static readonly SceneDrawing Box = SceneDrawing.Named("01_box_house");
    private const string DeckName = "Deck - freestanding";

    private static RevitModel House(params RevitElement[] more) => Box.Model("as drawn") is var m
        ? m with { Elements = [.. m.Elements, .. more] } : null!;

    private static SolidItem Block(double x0, double y0, double x1, double y1, double z0 = 0, double z1 = 2) =>
        F.Prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1);

    /// <summary>A family of <paramref name="category"/> 10 ft behind the house (it stands at y 30 to 80), marked when
    /// <paramref name="mark"/> is given.</summary>
    private static RevitElement Thing(string id, string category = "OST_GenericModel", string name = "Generic Models",
                                      string? mark = null) =>
        FakeRevit.Family(id, [Block(20, 90, 40, 110)], category, name) with
        {
            Name = DeckName,
            InstanceMarks = mark is null ? new Dictionary<Guid, MarkValue>()
                : new Dictionary<Guid, MarkValue> { [Marks.SiteObject.Guid] = new(true, Text: mark) },
        };

    private async Task<JsonObject> Site(RevitModel m) =>
        (await SiteReader.DescribeAsync(m, Box.Facts, new WorkerLeftOut(await worker.RunningAsync()))).Site;

    private static List<string> Ids(JsonObject site, string key) =>
        site[key]!.AsArray().Select(o => o!["id"]!.GetValue<string>()).ToList();

    private static JsonObject LeftOut(JsonObject site, string id) =>
        site["left_out"]!.AsArray().Single(o => o!["id"]!.GetValue<string>() == id)!.AsObject();

    private async Task<Dictionary<string, CheckItem>> Check(RevitModel m) =>
        (await (await worker.RunningAsync()).CheckSiteAsync(await Site(m), Box.Facts)).Items.ToDictionary(i => i.Id);

    private static readonly string[] Yards =
        ["R-1b.front_yard", "R-1b.side_yards#east", "R-1b.side_yards#west", "R-1b.rear_yard", "R-1b.yard_projections"];

    // ---- the description --------------------------------------------------------------------------------------

    [Fact]
    public async Task A_generic_model_standing_apart_is_left_out_could_be_a_building_with_its_name()
    {
        var site = await Site(House(Thing("deck")));
        var deck = LeftOut(site, "deck");
        Assert.False(deck["touching"]!.GetValue<bool>());
        Assert.True(deck["could_be_building"]!.GetValue<bool>());
        Assert.Equal(DeckName, deck["name"]!.GetValue<string>());
        Assert.Null(deck["slab"]);
    }

    [Theory]
    [InlineData("OST_Planting", "Planting")]
    [InlineData("OST_Entourage", "Entourage")]
    public async Task A_tree_or_entourage_cant_be_a_structure(string category, string name)
    {
        var site = await Site(House(Thing("tree", category, name)));
        Assert.False(LeftOut(site, "tree")["could_be_building"]!.GetValue<bool>());       // still left out
    }

    [Theory]
    [InlineData("Deck", "building", null)]
    [InlineData("porch", "building", null)]
    [InlineData("Landing", "building", null)]
    [InlineData("Ramp", "building", null)]
    [InlineData("Garage, shed or carport", "building", null)]
    [InlineData(" garage, SHED or carport ", "building", null)]
    // review round 1: a slab's words are a floor's alone; on anything else not stated (never a slab, which leaves
    // every check: a garage marked "Parking" must stay an object that may be a building)
    [InlineData("Patio", null, true)]
    [InlineData(" Walk ", null, true)]
    [InlineData("Driveway", null, true)]
    [InlineData("Parking", null, true)]
    [InlineData("Not a structure", null, false)]
    [InlineData("not a STRUCTURE", null, false)]
    [InlineData("Shed", null, true)]                    // not a word Gordium reads: not stated, never a near guess
    public async Task An_object_is_read_by_its_site_object_mark(string word, string? sent, bool? couldBe)
    {
        var site = await Site(House(Thing("deck", mark: word)));
        if (sent == "building")
        {
            Assert.Contains("deck", Ids(site, "buildings"));
            Assert.DoesNotContain("deck", Ids(site, "left_out"));
            return;
        }
        var deck = LeftOut(site, "deck");
        Assert.Equal(sent, deck["slab"]?.GetValue<string>());
        Assert.Equal(couldBe, deck["could_be_building"]!.GetValue<bool>());
    }

    [Fact]
    public async Task The_mark_is_read_only_on_the_categories_it_is_bound_to_and_never_on_a_context_object()
    {
        var site = await Site(House(Thing("pipe", "OST_PipeAccessory", "Pipe Accessories", mark: "Not a structure"),
                                    Thing("next_door", mark: "Not a structure") with { Mark = GordiumMark.Context }));
        Assert.True(LeftOut(site, "pipe")["could_be_building"]!.GetValue<bool>());
        Assert.True(LeftOut(site, "next_door")["could_be_building"]!.GetValue<bool>());
    }

    /// <summary>Review round 1: an AC condenser or a site light standing apart holds every yard, so the mark is bound
    /// to Mechanical Equipment and Lighting Fixtures too.</summary>
    [Theory]
    [InlineData("OST_MechanicalEquipment", "Mechanical Equipment")]
    [InlineData("OST_LightingFixtures", "Lighting Fixtures")]
    public async Task An_ac_condenser_or_a_site_light_can_be_marked_not_a_structure(string category, string name)
    {
        var site = await Site(House(Thing("unit", category, name, mark: "Not a structure")));
        Assert.False(LeftOut(site, "unit")["could_be_building"]!.GetValue<bool>());
    }

    /// <summary>Review round 1, P0: a 24 x 24 x 10 ft Generic Model 10 ft behind the house marked "Parking" (a garage
    /// drawn as one) never leaves the check: lot coverage, the rear yard and the objects not included all need review;
    /// marked "Garage, shed or carport" it is measured as a building.</summary>
    [Fact]
    public async Task A_garage_marked_parking_stays_in_the_check_and_one_marked_a_garage_is_measured()
    {
        RevitElement Garage(string mark) => FakeRevit.Family("garage", [Block(18, 90, 42, 114, 0, 10)]) with
        {
            Name = "Garage",
            InstanceMarks = new Dictionary<Guid, MarkValue> { [Marks.SiteObject.Guid] = new(true, Text: mark) },
        };
        var parking = await Check(House(Garage("Parking")));
        foreach (var id in new[] { "R-1b.lot_coverage", "R-1b.rear_yard", "scope.not_included" })
            Assert.Equal(Verdict.NeedsReview, parking[id].Status);
        var site = await Site(House(Garage("Garage, shed or carport")));
        Assert.Contains("garage", Ids(site, "buildings"));
        Assert.DoesNotContain("garage", Ids(site, "left_out"));
    }

    // ---- the checks ----------------------------------------------------------------------------------------------

    [Fact]
    public async Task One_standing_apart_keeps_every_yard_needing_review_naming_it_never_a_failure()
    {
        var items = await Check(House(Thing("deck")));
        foreach (var id in Yards)
        {
            Assert.Equal(Verdict.NeedsReview, items[id].Status);
            Assert.Contains($"\"{DeckName}\" (deck)", items[id].Reason);
            Assert.Contains("§325-18A", items[id].Reason);
        }
        Assert.Equal(Verdict.NeedsReview, items["R-1b.lot_coverage"].Status);
        Assert.DoesNotContain(items.Values, i => i.Status == Verdict.DoesNotComply);
    }

    [Theory]
    [InlineData("OST_Planting", "Planting", null)]
    [InlineData("OST_GenericModel", "Generic Models", "Not a structure")]
    public async Task One_that_cant_be_a_structure_leaves_the_yards_complying(string category, string name, string? mark)
    {
        var items = await Check(House(Thing("thing", category, name, mark)));
        foreach (var id in Yards)
            Assert.Equal(Verdict.Complies, items[id].Status);
        Assert.Equal(Verdict.NeedsReview, items["R-1b.lot_coverage"].Status);    // an object on the lot not measured
    }

    [Fact]
    public async Task One_marked_a_deck_is_measured_as_part_of_the_building()
    {
        // 20 x 20 ft behind the house: measured, standing apart, so read both as a freestanding deck and as an
        // accessory building (measure._yards): the rear yard can't comply unless it is listed as one
        var items = await Check(House(Thing("deck", mark: "Deck")));
        Assert.NotEqual(Verdict.Complies, items["R-1b.rear_yard"].Status);
        Assert.False(items.ContainsKey("scope.not_included"));
    }

    // ---- review round 2: one marked a building is a building part everywhere (Fold, Coarser) -------------------------

    private static JsonObject Building(JsonObject site, string id) =>
        site["buildings"]!.AsArray().Single(o => o!["id"]!.GetValue<string>() == id)!.AsObject();

    private static List<string> Codes(JsonObject b) =>
        b["problems"]!.AsArray().Select(p => p!["code"]!.GetValue<string>()).ToList();

    [Fact]
    public async Task One_marked_a_deck_sends_its_fine_faces_alone_and_says_a_coarser_drawing_may_be_bigger()
    {
        var deck = Thing("deck", mark: "Deck") with { CoarserGeometry = [Block(20, 90, 40, 110), Block(40, 90, 44, 110)] };
        var b = Building(await Site(House(deck)), "deck");
        Assert.Equal(6, b["faces"]!.AsArray().Count);                  // Fine's box alone, never Coarse's added
        Assert.Equal(["tool_words"], Codes(b));
        var same = Building(await Site(House(deck with { CoarserGeometry = [Block(20, 90, 40, 110)] })), "deck");
        Assert.Equal(6, same["faces"]!.AsArray().Count);
        Assert.Empty(Codes(same));
    }

    [Fact]
    public async Task A_part_nested_in_one_marked_a_deck_has_its_coarser_drawing_weighed_never_added_as_faces()
    {
        var deck = Thing("deck", mark: "Deck") with { CoarserGeometry = [Block(20, 90, 40, 110)] };
        var step = FakeRevit.Family("step", [Block(25, 88, 35, 90, 0, 1)])
            with { SuperComponent = "deck", CoarserGeometry = [Block(25, 88, 35, 90, 0, 1)] };
        var b = Building(await Site(House(deck, step)), "deck");
        Assert.Equal(12, b["faces"]!.AsArray().Count);
        Assert.Empty(Codes(b));
        b = Building(await Site(House(deck, step with { CoarserGeometry = [Block(25, 86, 35, 90, 0, 1)] })), "deck");
        Assert.Equal(12, b["faces"]!.AsArray().Count);
        Assert.Equal(["tool_words"], Codes(b));
    }

    /// <summary>Review round 7: a DirectShape (not a family) marked a deck with no geometry is a building part, so it is
    /// unsent (every building measure needs review), never skipped as an element with nothing that could be a
    /// building, as an unmarked one is.</summary>
    [Fact]
    public void A_direct_shape_marked_a_deck_with_no_geometry_is_unsent_never_skipped()
    {
        var shape = Thing("shape", mark: "Deck") with { Kind = ElementKind.Ordinary, Geometry = null, CoarserGeometry = null };
        var read = new Read(House());
        read.Element(shape);
        Assert.Contains(read.Unsent, u => u["id"]!.GetValue<string>() == "shape" &&
                                          u["kind"]!.GetValue<string>() == "a Generic Models element with no geometry");
        Assert.DoesNotContain(read.Candidates, c => c.Id == "shape");

        var unmarked = new Read(House());
        unmarked.Element(shape with { InstanceMarks = new Dictionary<Guid, MarkValue>() });
        Assert.DoesNotContain(unmarked.Unsent, u => u["id"]!.GetValue<string>() == "shape");     // skipped, as before
    }

    /// <summary>Review round 3: inside a linked model, one marked a deck is a building part too (the link holds a
    /// building), and its Medium/Coarse-only piece stays in the link's place (Fold and Coarser leave it out of the
    /// geometry, so LookInside walks it itself).</summary>
    [Fact]
    public void In_a_linked_model_one_marked_a_deck_holds_a_building_and_its_coarser_piece_keeps_its_place()
    {
        var deck = Thing("deck", mark: "Deck") with { CoarserGeometry = [Block(40, 90, 44, 110)] };
        var linked = new RevitModel { Document = "site.rvt", Elements = [deck] };
        var model = House();
        var read = new Read(model);
        read.Element(FakeRevit.LinkOf("link", linked));
        Assert.Contains(read.Unsent, u => u["id"]!.GetValue<string>() == SiteReader.LinkedModelKind);
        var link = read.Candidates.Single(c => c.Id == "link");
        Assert.Equal(44, link.Sent["box"]!.AsArray()[3]!.GetValue<double>(), 6);      // x1: the coarser piece's
        Assert.Contains(link.Sent["points"]!.AsArray(), p => Math.Abs(p![0]!.GetValue<double>() - 44) < 1e-6);
    }

    [Fact]
    public void The_marking_list_says_a_nested_parts_mark_isnt_read()
    {
        var host = Thing("bench", "OST_Furniture", "Furniture") with { Name = "Bench" };
        var leg = Thing("leg", "OST_Furniture", "Furniture", mark: "Not a structure") with { SuperComponent = "bench" };
        var cell = MarkingList.Build(House(host, leg)).Rows.Single(r => r.Id == "leg").Cells.Single();
        Assert.Equal(MarkState.NotReadHere, cell.State);
        Assert.Contains("part of \"Bench\" (bench)", cell.Words);
        // one marked a building is read on its own, so its mark is given
        var deckLeg = leg with { InstanceMarks = new Dictionary<Guid, MarkValue> { [Marks.SiteObject.Guid] = new(true, Text: "Deck") } };
        Assert.Equal(MarkState.Given, MarkingList.Build(House(host, deckLeg)).Rows.Single(r => r.Id == "leg").Cells.Single().State);
    }

    // ---- the marking list ---------------------------------------------------------------------------------------

    [Fact]
    public void The_marking_list_shows_each_marked_object_and_a_word_it_doesnt_read()
    {
        var list = MarkingList.Build(House(Thing("deck", mark: "Deck"), Thing("shed", mark: "Shed"), Thing("unmarked")));
        var rows = list.Rows.Where(r => r.Kind == MarkedKind.SiteObject).ToDictionary(r => r.Id);
        Assert.Equal(["deck", "shed"], rows.Keys.Order());
        Assert.Equal(MarkState.Given, rows["deck"].Cells.Single().State);
        Assert.Equal(MarkState.NotUnderstood, rows["shed"].Cells.Single().State);
        Assert.Contains(list.Summary, s => s.StartsWith("Gordium: Site object is: set on 2 elements, 1 with a word") &&
                                           s.Contains("Not a structure"));
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
    }

    /// <summary>Review round 1: where the reader doesn't read the mark (a context object, a Gordium floor block) the
    /// list says so, never "given"; a slab's word on a non-floor says it is a floor's word.</summary>
    [Fact]
    public void The_marking_list_says_where_the_mark_isnt_read_and_a_floor_word_on_a_family()
    {
        var list = MarkingList.Build(House(Thing("next_door", mark: "Deck") with { Mark = GordiumMark.Context },
                                           Thing("block", mark: "Deck") with { Mark = GordiumMark.FloorBlock, FloorMark = "1;10" },
                                           Thing("garage", mark: "Parking")));
        var rows = list.Rows.Where(r => r.Kind == MarkedKind.SiteObject).ToDictionary(r => r.Id, r => r.Cells.Single());
        Assert.Equal(MarkState.NotReadHere, rows["next_door"].State);
        Assert.Contains("context object", rows["next_door"].Words);
        Assert.Equal(MarkState.NotReadHere, rows["block"].State);
        Assert.Equal(MarkState.NotUnderstood, rows["garage"].State);
        Assert.Contains("a floor's word", rows["garage"].Words);
    }
}
