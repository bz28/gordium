using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Group 2's two building facts (BCNYS Tables 1006.3.4(1) and (2), a story's one exit): what the building's
/// Group R-2 units are (which table it reads, notes b and c), as three words, All sleeping units, All dwelling units or
/// Both (review round 3: a Yes/No once set can't be cleared, and a building of both kinds, which neither table fits,
/// must send nothing); and whether it has emergency escape and rescue openings per Section 1031 (note a), a Yes/No.
/// Each sent in the building block only when it says something (blank and Both are not stated, never false); a value
/// Gordium can't read is asked again; each quotes the table's note; the Setup form lists each; a card for either opens
/// Project Information on its mark.</summary>
public sealed class GroupTwoFactsTests
{
    private static readonly (MarkDefinition Mark, string Key)[] Each =
    [
        (Marks.R2SleepingUnits, "r2_sleeping_units"), (Marks.EscapeOpenings1031, "emergency_escape_openings_1031"),
    ];

    public static TheoryData<string> Keys => [.. Each.Select(e => e.Key)];

    private static RevitModel Model(Dictionary<Guid, MarkValue> marks) => new() { Document = "b.rvt", ProjectMarks = marks };

    [Fact]
    public void Each_is_a_project_information_mark_quoting_its_tables_note()
    {
        foreach (var (m, key) in Each)
        {
            Assert.Contains(m, Marks.All);
            Assert.Equal([Marks.ProjectInformation], m.Categories);
            Assert.Equal((MarkBinding.Instance, "building." + key), (m.Binding, m.Feeds));
            Assert.Contains("Blank:", m.Description, StringComparison.Ordinal);
        }
        Assert.Equal((MarkValueKind.Text, MarkValueKind.YesNo), (Marks.R2SleepingUnits.Kind, Marks.EscapeOpenings1031.Kind));
        Assert.Contains("\"This table is used for Group R-2 occupancies consisting of dwelling units. For Group R-2 occupancies consisting of sleeping units, use Table 1006.3.4(2).\"",
                        Marks.R2SleepingUnits.Description, StringComparison.Ordinal);
        Assert.Contains("one of: All sleeping units, All dwelling units, Both.", Marks.R2SleepingUnits.Description, StringComparison.Ordinal);
        Assert.Contains("Both: neither table fits every story, so both tables' one-exit rows need review", Marks.R2SleepingUnits.Description, StringComparison.Ordinal);
        Assert.Contains("and provided with emergency escape and rescue openings in accordance with Section 1031.\"", Marks.EscapeOpenings1031.Description, StringComparison.Ordinal);
        Assert.Contains("Gordium doesn't check them under the Building Code", Marks.EscapeOpenings1031.Description, StringComparison.Ordinal);
    }

    /// <summary>All sleeping units is true, all dwelling units false (any case), Both nothing: never false for a building of
    /// both kinds (review rounds 1 to 3: false sent its sleeping-unit stories to Table 1006.3.4(1)'s looser travel limit,
    /// true its apartment stories past Table (1)'s four-unit limit).</summary>
    [Theory]
    [InlineData("All sleeping units", "true")]
    [InlineData(" all dwelling units ", "false")]
    [InlineData("Both", null)]
    public void What_the_units_are_is_sent_as_the_table_reads_it_and_both_never(string typed, string? sent)
    {
        var read = BuildingFacts.Read(Model(new() { [Marks.R2SleepingUnits.Guid] = new(true, Text: typed), [Marks.SprinklerSystem.Guid] = new(true, Text: "None") }));
        Assert.Empty(read.Missing);
        Assert.Equal(sent, read.Building!["r2_sleeping_units"]?.ToJsonString());
        Assert.Equal(sent is not null, read.Building.ContainsKey("r2_sleeping_units"));
    }

    [Fact]
    public void The_escape_openings_are_sent_as_ticked_and_blank_never()
    {
        var read = BuildingFacts.Read(Model(new() { [Marks.EscapeOpenings1031.Guid] = new(true, 1) }));
        Assert.Equal("{\"emergency_escape_openings_1031\":true}", read.Building!.ToJsonString());
        foreach (var (m, key) in Each)
            foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false), new(false, Text: "") })
            {
                var marks = new Dictionary<Guid, MarkValue> { [Marks.SprinklerSystem.Guid] = new(true, Text: "None") };
                if (blank is { } b)
                    marks[m.Guid] = b;
                Assert.False(BuildingFacts.Read(Model(marks)).Building!.ContainsKey(key));
                Assert.Null(SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == m).Current);
            }
    }

    [Theory]
    [InlineData("r2_sleeping_units")]
    [InlineData("emergency_escape_openings_1031")]
    public void One_holding_what_gordium_cant_read_is_asked_again_and_the_form_waits(string key)
    {
        var (mark, _) = Each.Single(e => e.Key == key);
        var model = Model(new() { [mark.Guid] = mark.Kind == MarkValueKind.Text ? new(true, Text: "mostly dorms") : new(true, 3) });
        var read = BuildingFacts.Read(model);
        Assert.Equal([mark], read.NotRead);
        Assert.StartsWith($"{mark.Name} ", Assert.Single(read.Missing), StringComparison.Ordinal);
        Assert.Contains(mark.Name, SetupScreen.Build(model, [], null, null).Needed);
        // sent anyway as held, so the code decision says it can't read it (never read as not stated or as No)
        Assert.NotNull(read.Building![key]);
    }

    /// <summary>Group 3's two (BCNYS 1004.7 outdoor areas, 1004.5.1's increased occupant load): Yes/No marks sent only
    /// when set, never blank as No: No is the statement that can narrow a check (no outdoor areas: 1004.7's check not
    /// applicable; no increase: each room's load the table's alone), so it is never assumed.</summary>
    [Fact]
    public void Group_threes_two_are_yes_no_marks_sent_only_when_set()
    {
        foreach (var (m, key) in new[] { (Marks.OccupiedOutdoorAreas, "occupied_outdoor_areas"), (Marks.OccupantLoadIncreased, "occupant_load_increased") })
        {
            Assert.Contains(m, Marks.All);
            Assert.Equal((MarkValueKind.YesNo, "building." + key), (m.Kind, m.Feeds));
            Assert.Equal("{\"" + key + "\":false}", BuildingFacts.Read(Model(new() { [m.Guid] = new(true, 0) })).Building!.ToJsonString());
            Assert.Null(BuildingFacts.Read(Model(new() { [m.Guid] = new(false, 0) })).Building);
            Assert.Equal(FieldKind.YesNo, SetupScreen.Build(Model([]), [], null, null).Fields.Single(f => f.Mark == m).Kind);
            var card = new CauseCard($"field:building.{key}", CauseKind.Mark, "Say whether", [], ["r"], null, "review") { Fields = [$"building.{key}"] };
            Assert.Equal([m], CauseCards.MarksOf(card));
        }
        Assert.Contains("\"Yards, patios, occupiable roofs, courts and similar outdoor areas accessible to and usable by the building occupants shall be provided with means of egress as required by this chapter.\"",
                        Marks.OccupiedOutdoorAreas.Description, StringComparison.Ordinal);
        Assert.Contains("at most one occupant per 7 sq ft of occupiable floor space", Marks.OccupantLoadIncreased.Description, StringComparison.Ordinal);
        Assert.Contains("Yes or blank: each room's larger reading is at least its area / 7", Marks.OccupantLoadIncreased.Description, StringComparison.Ordinal);
    }

    [Fact]
    public void The_setup_form_offers_the_three_words_and_a_card_opens_project_information()
    {
        var fields = SetupScreen.Build(Model([]), [], null, null).Fields;
        var units = fields.Single(x => x.Mark == Marks.R2SleepingUnits);
        Assert.Equal((FieldKind.Choice, SetupFacts.CodeGroup, false), (units.Kind, units.Group, units.Required));
        Assert.Equal(["All sleeping units", "All dwelling units", "Both"], units.Choices.Select(c => c.Value));
        Assert.Equal(FieldKind.YesNo, fields.Single(x => x.Mark == Marks.EscapeOpenings1031).Kind);
        // a choice already made can be changed to Both, so a building that becomes mixed can say so
        var marks = new Dictionary<Guid, MarkValue> { [Marks.R2SleepingUnits.Guid] = new(true, Text: "All dwelling units") };
        var draft = new SetupDraft();
        draft.Choose(Marks.R2SleepingUnits, "Both");
        var w = Assert.Single(draft.Writes(SetupScreen.Build(Model(marks), [], null, null).Fields).Writes);
        Assert.Equal("Both", w.Value.Text);
        foreach (var (mark, key) in Each)
        {
            var card = new CauseCard($"field:building.{key}", CauseKind.Mark, "Say whether", [], ["r"], null, "review") { Fields = [$"building.{key}"] };
            Assert.Equal([mark], CauseCards.MarksOf(card));
            Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
        }
    }
}
