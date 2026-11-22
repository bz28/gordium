using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Which New York code governs the building (design_checker/code_scope.py; decision
/// docs/decisions/2026-11-22_which_ny_code.md): the marks on Project Information are read into the interior
/// description's <c>building</c> block (<see cref="BuildingFacts"/>), only those set, a bad word asked again (nothing
/// sent), and the real worker's answer carries the decision as <c>which_code</c> for the panel to show first. R101.2's
/// exception, the architect's one real choice, reaches the decision: Gordium: Follows the Building Code Yes puts a
/// house the Residential Code covers under the Building Code.</summary>
public sealed class WhichCodeTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static void Mark(FakeHouse house, MarkDefinition m, MarkValue v) => house.ProjectMarks[m.Guid] = v;

    [Fact]
    public void No_building_mark_set_sends_no_building_block()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var read = BuildingFacts.Read(house.Model());
        Assert.Null(read.Building);              // the interior description is exactly as before
        Assert.Empty(read.Missing);
        Mark(house, Marks.FollowsBuildingCode, new(false, 0));           // never set: not stated
        Assert.Null(BuildingFacts.Read(house.Model()).Building);
    }

    [Fact]
    public void Each_mark_set_is_sent_under_its_own_key_as_the_architect_gave_it()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        Mark(house, Marks.FollowsBuildingCode, new(true, 1));
        Mark(house, Marks.StoriesAboveGradePlane, new(true, 2));
        Mark(house, Marks.SeparateMeansOfEgress, new(true, 0));
        Mark(house, Marks.TownhouseUnits, new(true, 1));
        Mark(house, Marks.CareFacility, new(true, 0));
        Mark(house, Marks.OccupancyGroups, new(true, Text: " r-2, S-2 ,R-2"));
        Mark(house, Marks.SprinklerSystem, new(true, Text: "nfpa 13r"));
        var read = BuildingFacts.Read(house.Model());
        Assert.Empty(read.Missing);
        Assert.Equal("{\"follows_building_code\":true,\"separate_means_of_egress\":false,\"townhouse_units\":true," +
                     "\"care_facility\":false,\"stories_above_grade_plane\":2,\"occupancy_groups\":[\"R-2\",\"S-2\"]," +
                     "\"sprinkler_system\":\"nfpa_13r\"}", read.Building!.ToJsonString());
    }

    [Theory]
    [InlineData("groups", "R-2, office")]
    [InlineData("sprinkler", "wet pipe")]
    [InlineData("stories", "0")]
    public void A_word_that_isnt_one_of_the_marks_words_is_asked_again_never_sent(string which, string value)
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var (mark, v) = which switch
        {
            "groups" => (Marks.OccupancyGroups, new MarkValue(true, Text: value)),
            "sprinkler" => (Marks.SprinklerSystem, new MarkValue(true, Text: value)),
            _ => (Marks.StoriesAboveGradePlane, new MarkValue(true, int.Parse(value, System.Globalization.CultureInfo.InvariantCulture))),
        };
        Mark(house, mark, v);
        var read = BuildingFacts.Read(house.Model());
        Assert.Null(read.Building);
        Assert.StartsWith(mark.Name + " is ", Assert.Single(read.Missing), StringComparison.Ordinal);
    }

    [Fact]
    public void The_new_marks_are_project_information_marks_the_add_in_adds()
    {
        foreach (var m in new[] { Marks.FollowsBuildingCode, Marks.StoriesAboveGradePlane, Marks.SeparateMeansOfEgress,
                     Marks.TownhouseUnits, Marks.CareFacility, Marks.OccupancyGroups, Marks.SprinklerSystem })
        {
            Assert.Contains(m, Marks.All);                                     // MarkSetup adds every one of Marks.All
            Assert.Equal([Marks.ProjectInformation], m.Categories);
        }
        Assert.Contains("is permitted, provided that all applicable provisions of the Building Code of New York State are applied",
                        Marks.FollowsBuildingCode.Description, StringComparison.Ordinal);   // R101.2's exception, quoted
    }

    private static (FakeHouse, RevitModel) Project(string house)
    {
        var h = FakeHouse.Draw(house);
        var outside = ProjectCheckTests.Outside(h.Model());
        Mark(h, Marks.Zone, new(true, Text: "R-1b"));
        Mark(h, Marks.Use, new(true, Text: "one_family_detached"));
        Mark(h, Marks.LotSurveyed, new(true, 1));
        Mark(h, Marks.CornerLot, new(true, 0));
        Mark(h, Marks.GroundFrom, new(true, Text: "Spot grades"));
        Mark(h, Marks.StreetEdge, new(true, Text: ProjectCheckTests.SouthEdge(outside)));
        return (h, outside);
    }

    private async Task<JsonElement> WhichCode(FakeHouse house, RevitModel outside)
    {
        var client = await worker.RunningAsync();
        var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client));
        Assert.Empty(prepared.Missing);
        var result = await ProjectCheck.SendAsync(client, prepared.Request!);
        return result.Raw.GetProperty("which_code");
    }

    /// <summary>The ranch (one story, scene 01's box: two floor blocks, nothing below the ground) is a detached one-family
    /// dwelling the Residential Code covers; with Gordium: Follows the Building Code Yes it is under the Building Code
    /// (R101.2 exception), the words and sections the worker's own.</summary>
    [Fact]
    public async Task The_answer_carries_which_code_and_the_exception_mark_reaches_it()
    {
        var (house, outside) = Project("1_ranch_compliant");
        var house_code = await WhichCode(house, outside);
        Assert.Equal("residential_code", house_code.GetProperty("code").GetString());
        Assert.Equal("2025 Residential Code of New York State", house_code.GetProperty("title").GetString());
        Assert.Equal(JsonValueKind.Null, house_code.GetProperty("ask").ValueKind);
        var first = house_code.GetProperty("cites")[0];
        Assert.Equal("RCNYS R101.2 item 1", first.GetProperty("section").GetString());
        Assert.Equal(24, first.GetProperty("page").GetInt32());
        Assert.Equal("1. Detached one-family dwellings.", first.GetProperty("quote").GetString());

        Mark(house, Marks.FollowsBuildingCode, new(true, 1));
        var chosen = await WhichCode(house, outside);
        Assert.Equal("building_code", chosen.GetProperty("code").GetString());
        Assert.Equal("2025 Building Code of New York State", chosen.GetProperty("title").GetString());
        Assert.Equal("RCNYS R101.2 exception", chosen.GetProperty("cites")[0].GetProperty("section").GetString());
    }
}
