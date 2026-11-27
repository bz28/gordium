using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Groups 4 and 5's building facts (BCNYS 1020 corridors, 1005.3 egress capacity): whether another level's
/// occupants reach the corridors (1004.2.2, 1004.2.3, 1005.6), an ambulatory care facility (Table 1020.3), corridors
/// within dwelling units (1020.2 exception 2), an emergency voice/alarm system (907.5.2.2). Each a Yes/No on Project
/// Information sent in the building block only when set (blank is not stated, never No: No is each one's narrowing
/// answer, so never assumed); the Setup form lists each; a card for each opens Project Information on its mark.</summary>
public sealed class CorridorFactsTests
{
    private static readonly (MarkDefinition Mark, string Key)[] Each =
    [
        (Marks.OtherLevelsReachCorridors, "other_level_egress_into_corridors"), (Marks.AmbulatoryCareFacility, "ambulatory_care_facility"),
        (Marks.CorridorsWithinDwellingUnits, "corridors_within_dwelling_units"), (Marks.EmergencyVoiceAlarm, "emergency_voice_alarm_system"),
        (Marks.Mezzanines, "mezzanines"), (Marks.LoadsNotByArea, "loads_not_by_area"),   // the occupant loads' ceiling
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
            Assert.Null(BuildingFacts.Read(Model(marks)).Building);
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
    public void Each_says_what_yes_no_and_blank_do_and_quotes_its_law()
    {
        Assert.Contains("\"A fire-resistance rating is not required for corridors contained within a dwelling unit or sleeping unit in an occupancy in Groups I-1 and R.\"",
                        Marks.CorridorsWithinDwellingUnits.Description, StringComparison.Ordinal);
        // review round 1: the whole building's, never a system in part of it (the lower factors are for buildings
        // "equipped throughout"); 13R only in Group R, as the capacity rule reads it
        Assert.Contains("Yes only when the building is equipped throughout with an emergency voice/alarm communication system in accordance with BCNYS Section 907.5.2.2. A system in only part of the building: No.",
                        Marks.EmergencyVoiceAlarm.Description, StringComparison.Ordinal);
        Assert.Contains("NFPA 13R in Group R only", Marks.EmergencyVoiceAlarm.Description, StringComparison.Ordinal);
        Assert.Contains("No: none does, so each corridor's load lies between none and its whole story's", Marks.OtherLevelsReachCorridors.Description, StringComparison.Ordinal);
        // the door size rules (#202) read it too: No holds a door onto a corridor to the full size (merge review)
        Assert.Contains("1010.1.1's exceptions for doors inside a dwelling unit", Marks.CorridorsWithinDwellingUnits.Description, StringComparison.Ordinal);
        Assert.Contains("Table 1020.3 asks 72 in", Marks.AmbulatoryCareFacility.Description, StringComparison.Ordinal);
    }
}
