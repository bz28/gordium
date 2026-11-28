using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The building facts the Building Code's rules already read but no Revit mark stated until now
/// (docs/decisions/2026-11-28_revit_marks_building_facts.md, PR A): Chapter 4 part f's stage, platform or technical
/// production area (202, 410.5), aircraft-related occupancy (Section 412) and service corridor (202, 415.11.3), and
/// section group 9h's assembly spaces (1030.1). Each a Yes/No on Project Information, sent in the building block only
/// when set (blank is not stated, never No: No sets flags aside and lifts bands, so it is never assumed); the Setup form
/// lists each; a card for each opens Project Information on its mark.</summary>
public sealed class BuildingFactsMarksTests
{
    private static readonly (MarkDefinition Mark, string Key)[] Each =
    [
        (Marks.StagesOrPlatforms, "stages_or_platforms"), (Marks.AircraftRelatedOccupancy, "aircraft_related_occupancy"),
        (Marks.ServiceCorridors, "service_corridors"), (Marks.AssemblySpaces, "assembly_spaces"),
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
        Assert.Equal("{\"" + key + "\":true}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 1) })).Building!.ToJsonString());
        Assert.Equal("{\"" + key + "\":false}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 0) })).Building!.ToJsonString());
        foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false) })
        {
            var marks = new Dictionary<Guid, MarkValue>();
            if (blank is { } b)
                marks[m.Guid] = b;
            var read = BuildingFacts.Read(Model(marks));
            Assert.Null(read.Building);                                       // blank: not stated, never No
            Assert.Empty(read.NotRead);
        }
        var held = BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 2) }));
        Assert.Equal([m], held.NotRead);                                     // neither Yes nor No: asked again
        Assert.Equal("{\"" + key + "\":2}", held.Building!.ToJsonString());  // sent as held: the check says it can't read it
        Assert.Contains(held.Missing, w => w.StartsWith(m.Name, StringComparison.Ordinal));
        var field = SetupScreen.Build(Model([]), [], null, null).Fields.Single(f => f.Mark == m);
        Assert.Equal((FieldKind.YesNo, SetupFacts.CodeGroup, false), (field.Kind, field.Group, field.Required));
        var card = new CauseCard($"field:building.{key}", CauseKind.Mark, "Say whether", [], ["r"], null, "review") { Fields = [$"building.{key}"] };
        Assert.Equal([m], CauseCards.MarksOf(card));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
    }

    [Fact]
    public void Each_quotes_the_law_and_says_what_yes_no_and_blank_do()
    {
        // each quote is the law's words exactly (the Python side checks each against the labels' quotes:
        // design_checker/tests/test_building_fact_marks.py)
        Assert.Contains("\"A space within a building utilized for entertainment or presentations, which includes overhead hanging curtains, drops, scenery or stage effects other than lighting and sound.\"",
                        Marks.StagesOrPlatforms.Description, StringComparison.Ordinal);
        // each definition whole (review round 1: TECHNICAL PRODUCTION AREA's galleries and catwalks, PLATFORM's
        // theater-in-the-round stages and horizontal sliding curtains, left out, could lead to a wrong No)
        Assert.Contains("\"Open elevated areas or spaces intended for entertainment technicians to walk on and occupy for servicing and operating entertainment technology systems and equipment. Galleries, including fly and lighting galleries, gridirons, catwalks, and similar areas are designed for these purposes.\"",
                        Marks.StagesOrPlatforms.Description, StringComparison.Ordinal);
        foreach (var each in new[] { "worship", "head table", "lecturers and speakers", "boxing and wrestling rings",
                                     "theater-in-the-round stages", "horizontal sliding curtains" })
            Assert.Contains(each, Marks.StagesOrPlatforms.Description, StringComparison.Ordinal);
        foreach (var each in new[] { "airport traffic control tower", "aircraft hangar", "aircraft paint hangar",
                                     "aircraft manufacturing facility", "heliport", "helistop" })
            Assert.Contains(each, Marks.AircraftRelatedOccupancy.Description, StringComparison.Ordinal);
        Assert.Contains("\"A fully enclosed passage used for transporting HPM and purposes other than required means of egress.\"",
                        Marks.ServiceCorridors.Description, StringComparison.Ordinal);
        Assert.Contains("\"A room or space used for assembly purposes that contains seats, tables, displays, equipment or other material shall comply with this section.\"",
                        Marks.AssemblySpaces.Description, StringComparison.Ordinal);
        foreach (var (m, _) in Each)
        {
            Assert.Contains("Yes:", m.Description, StringComparison.Ordinal);
            Assert.Contains("No:", m.Description, StringComparison.Ordinal);
            Assert.Contains("Blank:", m.Description, StringComparison.Ordinal);
        }
        // blank never reads as No: for the three Chapter 4 facts every rule reading them is a flag or a band, so blank
        // shows what Yes shows; the assembly checks are flags too, but Yes also makes seating possible on a story
        // (occupant_load.py) where blank doesn't, so its words differ
        foreach (var m in new[] { Marks.StagesOrPlatforms, Marks.AircraftRelatedOccupancy, Marks.ServiceCorridors })
            Assert.Contains("Blank: as for Yes.", m.Description, StringComparison.Ordinal);
        Assert.Contains("Blank: the checks that turn on it need review.", Marks.AssemblySpaces.Description, StringComparison.Ordinal);
        // a room's Function outranks the mark (code_scope.building_measures): said in each tooltip it applies to
        foreach (var m in new[] { Marks.StagesOrPlatforms, Marks.AircraftRelatedOccupancy, Marks.AssemblySpaces, Marks.SpecialEgressSpaces })
            Assert.Contains("makes it Yes, whatever this says", m.Description, StringComparison.Ordinal);
        Assert.Contains("Function is Stage or platform", Marks.StagesOrPlatforms.Description, StringComparison.Ordinal);
        Assert.Contains("Function is Aircraft hangar", Marks.AircraftRelatedOccupancy.Description, StringComparison.Ordinal);
        Assert.Contains("Function is Mall building (covered or open)", Marks.SpecialEgressSpaces.Description, StringComparison.Ordinal);
        Assert.Contains("any story may seat people served by aisles", Marks.AssemblySpaces.Description, StringComparison.Ordinal);
    }
}
