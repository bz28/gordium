using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Chapter 4 part b's building facts (BCNYS 403 high-rise buildings, 405 underground buildings): whether the
/// building is a high-rise or more than 420 ft in building height (202, 403.2.2, 403.5.2), and whether a floor level
/// used for human occupancy is more than 30 ft below the lowest level of exit discharge (405.1). Each a Yes/No on
/// Project Information, sent in the building block only when set (blank is not stated, never No: No sets Section 403's
/// or 405's flags aside and lifts the story exit bands, so it is never assumed); the Setup form lists each; a card for
/// each opens Project Information on its mark.</summary>
public sealed class ChapterFourFactsTests
{
    private static readonly (MarkDefinition Mark, string Key)[] Each =
    [
        (Marks.HighRiseBuilding, "high_rise_building"), (Marks.UndergroundBuilding, "underground_building"),
    ];

    public static TheoryData<string> Keys => [.. Each.Select(e => e.Key)];

    private static RevitModel Model(Dictionary<Guid, MarkValue> marks) => new() { Document = "b.rvt", ProjectMarks = marks };

    [Theory]
    [MemberData(nameof(Keys))]
    public void Each_is_a_yes_no_sent_only_when_set_listed_and_answering_its_card(string key)
    {
        var (m, _) = Each.Single(e => e.Key == key);
        Assert.Contains(m, Marks.All);
        Assert.Equal((MarkValueKind.YesNo, MarkBinding.Instance, "building." + key), (m.Kind, m.Binding, m.Feeds));
        Assert.Equal([Marks.ProjectInformation], m.Categories);
        Assert.Contains("Blank", m.Description, StringComparison.Ordinal);
        Assert.Equal("{\"" + key + "\":true}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 1) })).Building!.ToJsonString());
        Assert.Equal("{\"" + key + "\":false}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 0) })).Building!.ToJsonString());
        foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false) })
        {
            var marks = new Dictionary<Guid, MarkValue>();
            if (blank is { } b)
                marks[m.Guid] = b;
            Assert.Null(BuildingFacts.Read(Model(marks)).Building);           // blank: not stated, never No
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
    public void Each_quotes_its_definition_whole_and_says_what_yes_no_and_blank_do()
    {
        // 202's whole definition, the occupiable roof included (review round 1 of part b: a question that left it out
        // let a building whose roof deck is the high part be answered No)
        Assert.Contains("\"A building with an occupied floor or occupiable roof located more than 75 feet (22 860 mm) above the lowest level of fire department vehicle access.\"",
                        Marks.HighRiseBuilding.Description, StringComparison.Ordinal);
        Assert.Contains("more than 420 ft in building height", Marks.HighRiseBuilding.Description, StringComparison.Ordinal);
        Assert.Contains("Gordium never decides it", Marks.HighRiseBuilding.Description, StringComparison.Ordinal);
        Assert.Contains("\"The provisions of Sections 405.2 through 405.9 apply to building spaces having a floor level used for human occupancy more than 30 feet (9144 mm) below the finished floor of the lowest level of exit discharge.\"",
                        Marks.UndergroundBuilding.Description, StringComparison.Ordinal);
        foreach (var (m, _) in Each)
        {
            Assert.Contains("Yes:", m.Description, StringComparison.Ordinal);
            Assert.Contains("No:", m.Description, StringComparison.Ordinal);
            Assert.Contains("Blank: as for Yes.", m.Description, StringComparison.Ordinal);
        }
    }
}
