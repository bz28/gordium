using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Site slabs (reading design note, section 1, "Site slabs"; SiteSlabs.cs): a Revit Floor under none of the
/// house's walls or roofs is a slab whose kind Revit can't know, read by its <c>Gordium: Site slab is</c> mark. Found
/// on Autodesk's Pacific Continental sample: a ~110 sq ft "Concrete 10\"" slab outside the house, partly past the
/// property line, was read as part of a building, so lot coverage did not comply. The law: a porch, deck, landing or
/// ramp counts in lot coverage and the yards (§325-3B BUILDING AREA, §325-18A); a patio or terrace doesn't count in
/// lot coverage, but "neither pergolas or terraces and patios above grade shall be located in a required yard"; building
/// area "shall not include parking areas and parking spaces". Scene 01's box house (two floor blocks, every measure
/// complies) with floors drawn beside it.</summary>
public sealed class SiteSlabTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly FakeRevit F = new(Transform3.Identity);
    private static readonly SceneDrawing Box = SceneDrawing.Named("01_box_house");
    private const string Concrete = "Concrete 10\"";

    private static RevitModel House(params RevitElement[] more) => Box.Model("as drawn") is var m
        ? m with { Elements = [.. m.Elements, .. more] } : null!;

    private static SolidItem Block(double x0, double y0, double x1, double y1, double z0 = 0, double z1 = 1) =>
        F.Prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1);

    /// <summary>A Floor (a system floor), marked when <paramref name="mark"/> is given.</summary>
    private static RevitElement Floor(string id, double x0, double y0, double x1, double y1, string? mark = null) =>
        FakeRevit.Part(id, "OST_Floors", "Floors", [Block(x0, y0, x1, y1)]) with
        {
            Name = Concrete,
            InstanceMarks = mark is null ? new Dictionary<Guid, MarkValue>()
                : new Dictionary<Guid, MarkValue> { [Marks.SiteSlab.Guid] = new(true, Text: mark) },
        };

    private static RevitElement Wall(string id, double x0, double y0, double x1, double y1) =>
        FakeRevit.Wall(id, [Block(x0, y0, x1, y1, 0, 10)]);

    private async Task<JsonObject> Site(RevitModel m) =>
        (await SiteReader.DescribeAsync(m, Box.Facts, new WorkerLeftOut(await worker.RunningAsync()))).Site;

    private static List<string> Ids(JsonObject site, string key) =>
        site[key]!.AsArray().Select(o => o!["id"]!.GetValue<string>()).ToList();

    private static JsonObject LeftOut(JsonObject site, string id) =>
        site["left_out"]!.AsArray().Single(o => o!["id"]!.GetValue<string>() == id)!.AsObject();

    // ---- which floors are site slabs ---------------------------------------------------------------------------

    [Fact]
    public async Task A_floor_under_no_wall_or_roof_is_a_site_slab_left_out_unmarked_with_its_name()
    {
        var site = await Site(House(Floor("pad", 50, 90, 58, 100)));
        Assert.DoesNotContain("pad", Ids(site, "buildings"));
        var pad = LeftOut(site, "pad");
        Assert.Equal("unmarked", pad["slab"]!.GetValue<string>());
        Assert.Equal(Concrete, pad["name"]!.GetValue<string>());
        Assert.Equal("Floors", pad["layer"]!.GetValue<string>());
    }

    [Fact]
    public async Task A_floor_under_a_wall_or_a_roof_is_part_of_the_building_as_before_whatever_it_is_marked()
    {
        var site = await Site(House(
            Floor("garage_floor", 20, 90, 40, 110, mark: "Patio"), Wall("garage_wall", 20, 90, 40, 91),
            Floor("porch", 46, 40, 56, 50), FakeRevit.Part("porch_roof", "OST_Roofs", "Roofs", [Block(45, 39, 57, 51, 9, 10)])));
        Assert.Contains("garage_floor", Ids(site, "buildings"));
        Assert.Contains("porch", Ids(site, "buildings"));
        Assert.DoesNotContain("garage_floor", Ids(site, "left_out"));
        Assert.DoesNotContain("porch", Ids(site, "left_out"));
    }

    [Fact]
    public void A_floor_poured_against_a_walls_outer_face_only_touches_it_so_is_outside_the_house()
    {
        // the wall's face at y = 91, the patio from 91 on: touching at an edge is not under the wall
        var m = House(Wall("w", 20, 90, 40, 91), Floor("patio", 20, 91, 40, 100), Floor("under", 20, 90.5, 40, 100));
        var found = SiteSlabs.Find(m);
        Assert.True(found.ContainsKey("patio"));
        Assert.False(found.ContainsKey("under"));          // half a foot under the wall: part of the house
    }

    [Fact]
    public void A_demolished_wall_or_one_in_another_design_option_holds_no_floor()
    {
        var m = House(Wall("old", 20, 90, 40, 91) with { PhaseDemolished = "new" }, Floor("slab", 20, 90, 40, 100)) with
        {
            Phases = ["existing", "new"],
        };
        Assert.True(SiteSlabs.Find(m).ContainsKey("slab"));
    }

    [Fact]
    public void A_floor_with_no_box_or_one_that_isnt_a_system_floor_is_read_as_before()
    {
        var noBox = Floor("nobox", 50, 90, 58, 100) with { BoundingBox = null };
        var family = FakeRevit.Family("inplace", [Block(50, 90, 58, 100)], "OST_Floors", "Floors") with { IsInPlace = true };
        var found = SiteSlabs.Find(House(noBox, family));
        Assert.Empty(found);
    }

    // ---- what the mark says ------------------------------------------------------------------------------------

    [Theory]
    [InlineData("Deck", null)]          // a building: sent as one
    [InlineData("porch", null)]
    [InlineData("Landing", null)]
    [InlineData("Ramp", null)]
    [InlineData("Patio", "patio")]
    [InlineData(" Terrace ", "patio")]
    [InlineData("Walk", "patio")]
    [InlineData("Driveway", "parking")]
    [InlineData("Parking", "parking")]
    [InlineData("Garage", "unmarked")]  // not a word Gordium reads: not stated, never a near guess
    public async Task A_site_slab_is_read_by_its_mark(string word, string? slab)
    {
        var site = await Site(House(Floor("pad", 50, 90, 58, 100, mark: word)));
        if (slab is null)
        {
            Assert.Contains("pad", Ids(site, "buildings"));
            Assert.DoesNotContain("pad", Ids(site, "left_out"));
        }
        else
        {
            Assert.DoesNotContain("pad", Ids(site, "buildings"));
            Assert.Equal(slab, LeftOut(site, "pad")["slab"]!.GetValue<string>());
        }
    }

    [Fact]
    public void A_blank_mark_is_not_stated()
    {
        var blank = Floor("pad", 50, 90, 58, 100) with
        {
            InstanceMarks = new Dictionary<Guid, MarkValue> { [Marks.SiteSlab.Guid] = new(false, Text: "Deck") },
        };
        Assert.Null(SiteSlabs.Find(House(blank))["pad"].Kind);
    }

    // ---- the checks: the Pacific Continental case ----------------------------------------------------------------

    /// <summary>A slab 50 to 70 ft across, past the lot's east line at 60 ft, 10 ft behind the house's side.</summary>
    private async Task<Dictionary<string, CheckItem>> Check(string? mark)
    {
        var site = await Site(House(Floor("pad", 50, 90, 70, 96, mark)));
        var result = await (await worker.RunningAsync()).CheckSiteAsync(site, Box.Facts);
        return result.Items.ToDictionary(i => i.Id);
    }

    private static readonly string[] Yards =
        ["R-1b.front_yard", "R-1b.side_yards#east", "R-1b.side_yards#west", "R-1b.rear_yard", "R-1b.yard_projections"];

    [Fact]
    public async Task An_unmarked_slab_past_the_lot_line_needs_review_never_a_failure_naming_it()
    {
        var items = await Check(null);
        foreach (var id in Yards.Append("R-1b.lot_coverage"))
        {
            Assert.Equal(Verdict.NeedsReview, items[id].Status);
            Assert.Contains(Concrete, items[id].Reason);
        }
        Assert.DoesNotContain(items.Values, i => i.Status == Verdict.DoesNotComply);
        Assert.Contains("mark what it is", items["scope.not_included"].Reason);
    }

    [Fact]
    public async Task A_patio_is_not_in_lot_coverage_but_the_yards_need_review()
    {
        var items = await Check("Patio");
        Assert.Equal(Verdict.Complies, items["R-1b.lot_coverage"].Status);
        foreach (var id in Yards)
            Assert.Equal(Verdict.NeedsReview, items[id].Status);
        Assert.False(items.ContainsKey("scope.not_included"));
        Assert.DoesNotContain(items.Values, i => i.Status == Verdict.DoesNotComply);
    }

    [Fact]
    public async Task A_driveway_changes_nothing()
    {
        var plain = (await (await worker.RunningAsync()).CheckSiteAsync(await Site(House()), Box.Facts)).Items
            .ToDictionary(i => i.Id, i => (i.Status, i.Reason));
        Assert.Equal(plain, (await Check("Driveway")).ToDictionary(p => p.Key, p => (p.Value.Status, p.Value.Reason)));
    }

    [Fact]
    public async Task A_deck_is_part_of_the_building_so_past_the_lot_line_it_does_not_comply()
    {
        var items = await Check("Deck");
        Assert.Equal(Verdict.DoesNotComply, items["R-1b.lot_coverage"].Status);
    }

    // ---- the marking list ---------------------------------------------------------------------------------------

    [Fact]
    public void The_marking_list_shows_each_site_slab_and_says_what_an_unmarked_one_leaves()
    {
        var m = House(Floor("pad", 50, 90, 58, 100), Floor("walk", 25, 0, 30, 30, mark: "Walk"),
                      Floor("odd", 2, 100, 8, 110, mark: "Garage"),
                      Floor("in_house", 20, 90, 40, 110, mark: "Patio"), Wall("w", 20, 90, 40, 91));
        var list = MarkingList.Build(m);
        var rows = list.Rows.Where(r => r.Kind == MarkedKind.SiteSlab).ToDictionary(r => r.Id);
        Assert.Equal(["odd", "pad", "walk"], rows.Keys.Order());
        Assert.Equal(MarkState.Unset, rows["pad"].Cells.Single().State);
        Assert.Equal(MarkState.NotUnderstood, rows["odd"].Cells.Single().State);
        Assert.Equal(MarkState.Given, rows["walk"].Cells.Single().State);
        Assert.Contains(Concrete, rows["pad"].Label);
        Assert.Contains("Gordium: Site slab is: 2 of 3 floors outside the house not marked, so lot coverage and the yards need review until each says what it is.", list.Summary);
        Assert.Contains(list.Summary, s => s.Contains("under the house's walls or roof") && s.Contains("in_house"));
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
    }
}
