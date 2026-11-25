using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Group 2's two building facts (BCNYS Tables 1006.3.4(1) and (2), a story's one exit): whether the building's
/// Group R-2 is of sleeping units (which table it reads, notes b and c) and whether it has emergency escape and rescue
/// openings per Section 1031 (note a). Each a Yes/No on Project Information, sent in the building block only when set
/// (blank is not stated, never No); one holding neither Yes nor No is asked again; each quotes the table's own note;
/// the Setup form lists each; a card for either opens Project Information on its mark.</summary>
public sealed class GroupTwoFactsTests
{
    private static readonly (MarkDefinition Mark, string Key)[] Each =
    [
        (Marks.R2SleepingUnits, "r2_sleeping_units"), (Marks.EscapeOpenings1031, "emergency_escape_openings_1031"),
    ];

    public static TheoryData<string> Keys => [.. Each.Select(e => e.Key)];

    private static RevitModel Model(Dictionary<Guid, MarkValue> marks) => new() { Document = "b.rvt", ProjectMarks = marks };

    [Fact]
    public void Each_is_a_yes_no_project_information_mark_quoting_its_tables_note()
    {
        foreach (var (m, key) in Each)
        {
            Assert.Contains(m, Marks.All);
            Assert.Equal([Marks.ProjectInformation], m.Categories);
            Assert.Equal((MarkValueKind.YesNo, MarkBinding.Instance, "building." + key), (m.Kind, m.Binding, m.Feeds));
            Assert.Contains("Blank:", m.Description, StringComparison.Ordinal);
        }
        Assert.Contains("\"This table is used for Group R-2 occupancies consisting of dwelling units. For Group R-2 occupancies consisting of sleeping units, use Table 1006.3.4(2).\"",
                        Marks.R2SleepingUnits.Description, StringComparison.Ordinal);
        Assert.Contains("and provided with emergency escape and rescue openings in accordance with Section 1031.\"", Marks.EscapeOpenings1031.Description, StringComparison.Ordinal);
        // Gordium doesn't check 1031's openings under the Building Code: Yes is the architect's statement, said so
        Assert.Contains("Gordium doesn't check them under the Building Code", Marks.EscapeOpenings1031.Description, StringComparison.Ordinal);
    }

    [Fact]
    public void Each_set_is_sent_as_ticked_and_blank_never()
    {
        var read = BuildingFacts.Read(Model(new() { [Marks.R2SleepingUnits.Guid] = new(true, 0), [Marks.EscapeOpenings1031.Guid] = new(true, 1) }));
        Assert.Empty(read.Missing);
        Assert.Equal("{\"r2_sleeping_units\":false,\"emergency_escape_openings_1031\":true}", read.Building!.ToJsonString());
        foreach (var (m, key) in Each)
            foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false) })
            {
                var marks = new Dictionary<Guid, MarkValue> { [Marks.SprinklerSystem.Guid] = new(true, Text: "None") };
                if (blank is { } b)
                    marks[m.Guid] = b;
                Assert.False(BuildingFacts.Read(Model(marks)).Building!.ContainsKey(key));
                Assert.Null(SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == m).Current);
            }
    }

    [Theory]
    [MemberData(nameof(Keys))]
    public void One_holding_neither_yes_nor_no_is_asked_again_and_the_form_waits(string key)
    {
        var (mark, _) = Each.Single(e => e.Key == key);
        var model = Model(new() { [mark.Guid] = new(true, 3) });
        var read = BuildingFacts.Read(model);
        Assert.Equal([mark], read.NotRead);
        Assert.StartsWith($"{mark.Name} holds a value that isn't Yes or No", Assert.Single(read.Missing), StringComparison.Ordinal);
        Assert.Contains(mark.Name, SetupScreen.Build(model, [], null, null).Needed);
    }

    [Theory]
    [MemberData(nameof(Keys))]
    public void The_setup_form_lists_each_and_a_card_opens_project_information_on_it(string key)
    {
        var (mark, _) = Each.Single(e => e.Key == key);
        var f = SetupScreen.Build(Model([]), [], null, null).Fields.Single(x => x.Mark == mark);
        Assert.Equal((FieldKind.YesNo, SetupFacts.CodeGroup, false), (f.Kind, f.Group, f.Required));
        var card = new CauseCard($"field:building.{key}", CauseKind.Mark, "Say whether", [], ["r"], null, "review") { Fields = [$"building.{key}"] };
        Assert.Equal([mark], CauseCards.MarksOf(card));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
    }
}
