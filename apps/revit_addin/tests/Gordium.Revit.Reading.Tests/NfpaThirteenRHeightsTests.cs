using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>BCNYS 903.3.1.2's heights for an NFPA 13R system (items 2 and 3): Group R-2's roof assembly under 45 ft,
/// another Group R's highest story's floor 30 ft or less, above the lowest level of fire department vehicle access, and
/// the lowest story's floor 30 ft or less below it. The model can't show where fire trucks reach the building, so the
/// architect states it: a Yes/No on Project Information, sent in the building block only when set (blank is not stated,
/// never Yes: a 13R system counts only where every limit is known to hold, code_scope.nfpa_13r_counts); the Setup form
/// lists it; a card for it opens Project Information on its mark.</summary>
public sealed class NfpaThirteenRHeightsTests
{
    private static RevitModel Model(Dictionary<Guid, MarkValue> marks) => new() { Document = "b.rvt", ProjectMarks = marks };

    [Fact]
    public void It_is_a_yes_no_sent_only_when_set_listed_and_answering_its_card()
    {
        var m = Marks.NfpaThirteenRHeights;
        const string key = "nfpa_13r_heights_within";
        Assert.Contains(m, Marks.All);
        Assert.Equal((MarkValueKind.YesNo, MarkBinding.Instance, "building." + key), (m.Kind, m.Binding, m.Feeds));
        Assert.Equal([Marks.ProjectInformation], m.Categories);
        Assert.Equal("{\"" + key + "\":true}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 1) })).Building!.ToJsonString());
        Assert.Equal("{\"" + key + "\":false}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 0) })).Building!.ToJsonString());
        foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false) })
        {
            var marks = new Dictionary<Guid, MarkValue>();
            if (blank is { } b)
                marks[m.Guid] = b;
            Assert.Null(BuildingFacts.Read(Model(marks)).Building);           // blank: not stated, never Yes
        }
        var held = BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 2) }));
        Assert.Equal([m], held.NotRead);                                   // neither Yes nor No: asked again
        var field = SetupScreen.Build(Model([]), [], null, null).Fields.Single(f => f.Mark == m);
        Assert.Equal((FieldKind.YesNo, SetupFacts.CodeGroup, false), (field.Kind, field.Group, field.Required));
        var card = new CauseCard($"field:building.{key}", CauseKind.Mark, "Say whether", [], ["r"], null, "review") { Fields = [$"building.{key}"] };
        Assert.Equal([m], CauseCards.MarksOf(card));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
    }

    [Fact]
    public void It_quotes_items_2_and_3_whole_with_how_the_roof_is_measured_and_says_what_yes_no_and_blank_do()
    {
        var d = Marks.NfpaThirteenRHeights.Description;
        Assert.Contains("\"For other than Group R-2 occupancies, the floor level of the highest story is 30 feet (9144 mm) or less above the lowest level of fire department vehicle access. For Group R-2 occupancies, the roof assembly is less than 45 feet (13 716 mm) above the lowest level of fire department vehicle access.", d, StringComparison.Ordinal);
        // review round 2: the roof's height measured to the highest eave, roof-wall line or parapet top, never the deck
        Assert.Contains("The height of the roof assembly shall be determined by measuring the distance from the lowest required fire vehicle access road surface adjacent to the building to the eave of the highest pitched roof, the intersection of the highest roof to the exterior wall, or the top of the highest parapet, whichever yields the greatest distance.", d, StringComparison.Ordinal);
        Assert.Contains("\"The floor level of the lowest story is 30 feet (9144 mm) or less below the lowest level of fire department vehicle access.\"", d, StringComparison.Ordinal);
        Assert.Contains("Gordium never decides it", d, StringComparison.Ordinal);
        Assert.Contains("Yes, with Group R alone and the stories above grade plane stated four or fewer, and not a Group R-2 high-rise", d, StringComparison.Ordinal);
        Assert.Contains("No, in a building of Group R alone (and in a Group R-2 high-rise, whatever this mark says):", d, StringComparison.Ordinal);
        Assert.Contains("Blank, or a building of Group R beside another group", d, StringComparison.Ordinal);
        Assert.Contains("whether it counts isn't known", d, StringComparison.Ordinal);
    }
}
