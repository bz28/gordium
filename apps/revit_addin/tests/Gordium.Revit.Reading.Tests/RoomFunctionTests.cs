using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>A room's Table 1004.5 function (BCNYS 1004.5: the Building Code's occupant loads are worked out from it):
/// a Room mark, <c>Gordium: Function</c>, read into <c>rooms[].function</c> only as one of Table 1004.5's rows (a word
/// not in the list is said and not sent; blank is not stated, its load needs review). Never guessed: the Setup form
/// suggests one from a room's name, shown with its basis and written only when the architect accepts it, and never
/// for a corridor, an exit enclosure, a closet or a toilet.</summary>
public sealed class RoomFunctionTests
{
    /// <summary>Table 1004.5's rows in its order, as the BCNYS rulebook names them (group 3's
    /// records/occupant_load_factors.yaml <c>functions</c>; docs/interior/interior_description_format.md's
    /// <c>function</c> row on that branch).</summary>
    private static readonly string[] TableRows =
    [
        "accessory_storage_mechanical", "agricultural", "aircraft_hangar", "airport_baggage_claim", "airport_baggage_handling",
        "airport_concourse", "airport_waiting", "gaming_floor", "exhibit_gallery_museum", "assembly_fixed_seats",
        "assembly_concentrated", "assembly_standing", "assembly_unconcentrated", "bowling_center", "business",
        "concentrated_business", "courtroom", "day_care", "dormitory", "classroom", "vocational_shop", "exercise_room",
        "h5_fabrication", "industrial", "information_technology", "inpatient_treatment", "outpatient", "institutional_sleeping",
        "commercial_kitchen", "library_reading_room", "library_stack", "locker_room", "mall", "mercantile",
        "storage_stock_shipping", "parking_garage", "residential", "rink_pool", "pool_deck", "stage_platform", "warehouse",
    ];

    private static readonly string Factors = Path.Combine(Env.Repo, "regulations", "jurisdictions", "new_york", "new_york_state_building",
                                                          "5_building_code_rules", "drafted", "records", "occupant_load_factors.yaml");

    [Fact]
    public void The_mark_is_a_room_text_mark_whose_words_are_table_1004_5s_rows_in_order()
    {
        var m = Marks.RoomFunction;
        Assert.Contains(m, Marks.All);
        Assert.Equal([Marks.Rooms], m.Categories);
        Assert.Equal((MarkValueKind.Text, MarkBinding.Instance, "rooms[].function"), (m.Kind, m.Binding, m.Feeds));
        Assert.Equal(TableRows, RoomFunctions.Words.Select(w => RoomFunctions.Table.Of(w)));
        Assert.Equal(41, RoomFunctions.Words.Distinct(StringComparer.OrdinalIgnoreCase).Count());
        // the table's Decks row sits under "Skating rinks, swimming pools": a rink's deck too (review round 1)
        Assert.Equal("pool_deck", RoomFunctions.Table.Of("Rink or pool deck"));
        foreach (var w in RoomFunctions.Words)
            Assert.Contains(w, m.Description, StringComparison.Ordinal);       // the tooltip lists each
        // once group 3's factors are in this tree, its rows are exactly these (the names are fixed: group 3's review)
        if (File.Exists(Factors))
        {
            var keys = File.ReadAllLines(Factors).SkipWhile(l => l != "functions:").Skip(1)
                .Where(l => l.Length > 2 && l[..2] == "  " && l[2] != ' ' && l.TrimEnd().EndsWith(':')).Select(l => l.Trim().TrimEnd(':'));
            Assert.Equal(TableRows, keys);
        }
    }

    [Fact]
    public void A_function_is_sent_only_as_one_of_the_tables_words()
    {
        var floor = new FakeFloor();
        floor.SetMark("A", Marks.RoomFunction, new(true, Text: " business area "));      // any case, trimmed
        floor.SetMark("B", Marks.RoomFunction, new(true, Text: "office"));               // not a row: said, not sent
        floor.SetMark("L", Marks.RoomFunction, new(false, Text: ""));                    // never set
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal("business", FakeFloor.Part(read, "rooms", "A")!["function"]!.GetValue<string>());
        Assert.Null(FakeFloor.Part(read, "rooms", "B")!["function"]);
        Assert.Null(FakeFloor.Part(read, "rooms", "L")!["function"]);
        Assert.Null(FakeFloor.Part(read, "rooms", "C")!["function"]);                     // no mark at all
        var said = read.RouteNotes.Concat(read.Notes).Where(n => n.Field == "function").ToList();
        var note = Assert.Single(said);                                                  // blank is the usual answer: no note
        Assert.Equal(FakeFloor.Uid("B"), note.Part);
        Assert.Contains("\"office\", not one of Table 1004.5's functions", note.Why, StringComparison.Ordinal);
    }

    // ---- the suggestions --------------------------------------------------------------------------------------

    /// <summary>The floor with the project's groups and use (an apartment building, multiple_family, unless said).</summary>
    private static RevitModel Model(FakeFloor floor, string? groups, string? use = "multiple_family")
    {
        var marks = new Dictionary<Guid, MarkValue>();
        if (groups is not null)
            marks[Marks.OccupancyGroups.Guid] = new(true, Text: groups);
        if (use is not null)
            marks[Marks.Use.Guid] = new(true, Text: use);
        return floor.Model() with { ProjectMarks = marks };
    }

    /// <summary>The fake floor's doors' sides: dS joins the corridor and the stair (an exit enclosure door).</summary>
    private static List<OpeningSides> Sides() =>
    [
        new(FakeFloor.Uid("dA"), FakeFloor.Uid("A"), FakeFloor.Uid("C"), FakeFloor.Level, "Level 1", 0),
        new(FakeFloor.Uid("dB"), FakeFloor.Uid("B"), FakeFloor.Uid("C"), FakeFloor.Level, "Level 1", 0),
        new(FakeFloor.Uid("dS"), FakeFloor.Uid("C"), FakeFloor.Uid("S"), FakeFloor.Level, "Level 1", 0),
        new(FakeFloor.Uid("dE"), FakeFloor.Uid("L"), null, FakeFloor.Level, "Level 1", 0),
    ];

    private static void Name(FakeFloor floor, string id, string name)
    {
        var i = floor.MarkedIndex(id);
        floor.Marked[i] = floor.Marked[i] with { Name = name };
    }

    private static ChecklistLine? Line(RevitModel model, bool buildingCode = true) =>
        SetupChecklist.Build(model, Sides(), "building", routes: true, buildingCode).SingleOrDefault(l => l.Key == "room_function");

    private static Dictionary<string, string> Suggested(ChecklistLine line) =>
        line.Suggestions.ToDictionary(s => s.Element, s => s.Value.Text!, StringComparer.Ordinal);

    [Fact]
    public void The_line_shows_only_where_the_building_code_governs_and_is_never_needed_to_check()
    {
        var floor = new FakeFloor();
        Assert.Null(Line(Model(floor, "R-2"), buildingCode: false));
        var line = Line(Model(floor, "R-2"))!;
        Assert.False(line.Needed);                                         // blank: its load needs review, never blocks
        // counted: the offices and the lobby; never the corridor or the stair an exit enclosure door opens onto, left
        // blank by design (review round 1: the line never read done)
        Assert.Equal((0, 3), (line.Set, line.Total));
        Assert.Equal([FakeFloor.Uid("A"), FakeFloor.Uid("B"), FakeFloor.Uid("L")], line.Unset);
        floor.SetMark("A", Marks.RoomFunction, new(true, Text: "Business area"));
        floor.SetMark("B", Marks.RoomFunction, new(true, Text: "office"));  // not a row: not set
        Assert.Equal(1, Line(Model(floor, "R-2"))!.Set);
    }

    [Fact]
    public void Each_name_gives_its_function_and_nothing_else_is_guessed()
    {
        var floor = new FakeFloor();
        Name(floor, "A", "Bedroom 2");
        Name(floor, "B", "Living Room");
        Name(floor, "L", "Storage");
        Name(floor, "S", "Storage 2");             // the stair room: named so, but an exit enclosure door opens onto it
        var got = Suggested(Line(Model(floor, "R-2"))!);
        Assert.Equal(new Dictionary<string, string>
        {
            [FakeFloor.Uid("A")] = "Residential", [FakeFloor.Uid("B")] = "Residential",
            [FakeFloor.Uid("L")] = "Storage, stock or shipping area",
        }, got);
        // the corridor (by its use) and the stair (an exit enclosure door opens onto it) are offered none
        Assert.DoesNotContain(FakeFloor.Uid("C"), got.Keys);
        Assert.DoesNotContain(FakeFloor.Uid("S"), got.Keys);
        // Residential only where every stated group is Group R (a dormitory's rooms are Dormitory, 50 gross): never
        // with no groups stated, nor in a building of another group
        foreach (var groups in new string?[] { null, "B", "R-2, B", "office" })
            Assert.Equal([FakeFloor.Uid("L")], Suggested(Line(Model(floor, groups))!).Keys);
        // each with its basis, said beside it
        var bed = Line(Model(floor, "R-2"))!.Suggestions.Single(s => s.Element == FakeFloor.Uid("A"));
        Assert.Contains("named \"Bedroom 2\"", bed.Basis, StringComparison.Ordinal);
        Assert.Contains("a shared lounge or dining room is Assembly unconcentrated instead", bed.Basis, StringComparison.Ordinal);
        // a hotel (R-1) or a care home (R-4): a "Bedroom" is a guest or care room, a "Living Room" may be a lounge
        foreach (var groups in new[] { "R-1", "R-4" })
            Assert.Equal([FakeFloor.Uid("L")], Suggested(Line(Model(floor, groups))!).Keys);
        Assert.Contains("a building of dwelling units (multiple_family, Group R-2)", bed.Basis, StringComparison.Ordinal);
    }

    /// <summary>Review round 1: a suggestion only for the room type as the whole name (with a number or letter): a word
    /// inside a longer name is another row, often with a smaller factor (a larger load).</summary>
    [Theory]
    [InlineData("Mechanical Engineering Lab", null)]
    [InlineData("Mech Shop", null)]
    [InlineData("Mech Lab", null)]
    [InlineData("The Boiler Room", null)]
    [InlineData("Storage Unit Leasing Office", null)]
    [InlineData("Community Living Room", null)]
    [InlineData("Assisted Living Dining", null)]
    [InlineData("Living Room Lounge", null)]
    [InlineData("Master Bedroom Suite", null)]
    [InlineData("Mechanical Room", "Accessory storage or mechanical equipment room")]
    [InlineData("Boiler Room 2", "Accessory storage or mechanical equipment room")]
    [InlineData("Mech. Rm 3", "Accessory storage or mechanical equipment room")]
    [InlineData("Storage", "Storage, stock or shipping area")]
    [InlineData("Stock Room B", "Storage, stock or shipping area")]
    [InlineData("Bedroom 2", "Residential")]
    [InlineData("BEDROOM A", "Residential")]
    [InlineData("Living Room", "Residential")]
    public void Only_the_room_type_as_the_whole_name_is_suggested(string name, string? word)
    {
        var floor = new FakeFloor();
        Name(floor, "A", name);
        var got = Suggested(Line(Model(floor, "R-2"))!);
        if (word is null)
            Assert.DoesNotContain(FakeFloor.Uid("A"), got.Keys);
        else
            Assert.Equal(word, got[FakeFloor.Uid("A")]);
    }

    /// <summary>Review round 1: Accept writes apart from Save, so Residential is offered on the groups the form holds,
    /// chosen and not saved yet, never only on those saved.</summary>
    [Fact]
    public void Residential_follows_the_groups_the_form_holds_not_only_those_saved()
    {
        var floor = new FakeFloor();
        Name(floor, "A", "Bedroom 1");
        var model = floor.Model() with
        {
            ProjectMarks = new Dictionary<Guid, MarkValue>
            {
                [Marks.OccupancyGroups.Guid] = new(true, Text: "R-2"), [Marks.FollowsBuildingCode.Guid] = new(true, 1),
                [Marks.Use.Guid] = new(true, Text: "multiple_family"),
            },
        };
        string? Offered(SetupDraft? draft) => SetupScreen.Build(model, Sides(), null, draft).Lines
            .Single(l => l.Key == "room_function").Suggestions.SingleOrDefault(s => s.Element == FakeFloor.Uid("A"))?.Value.Text;
        Assert.Equal("Residential", Offered(null));
        var mixed = new SetupDraft();
        mixed.Choose(Marks.OccupancyGroups, "R-2, B");
        Assert.Null(Offered(mixed));
        var cleared = new SetupDraft();
        cleared.Choose(Marks.OccupancyGroups, "");
        Assert.Null(Offered(cleared));
    }

    /// <summary>Review round 2: a dormitory's or a fraternity's (Group R-2 too) bedroom is Dormitories, 50 gross, and its
    /// living room a shared lounge: Residential (200 gross) only for a building of dwelling units.</summary>
    [Theory]
    [InlineData("dormitory")]
    [InlineData("fraternity_sorority_group_house")]
    [InlineData("hotel_motel")]
    [InlineData(null)]
    public void Residential_only_for_a_building_of_dwelling_units(string? use)
    {
        var floor = new FakeFloor();
        Name(floor, "A", "Bedroom 2");
        Name(floor, "B", "Living Room");
        Name(floor, "L", "Storage");
        Assert.Equal([FakeFloor.Uid("L")], Suggested(Line(Model(floor, "R-2", use))!).Keys);
        foreach (var dwelling in new[] { "one_family_detached", "two_family", "multiple_family" })
            Assert.Equal(3, Suggested(Line(Model(floor, "R-3", dwelling))!).Count);
    }

    /// <summary>Review round 2: only the room an exit enclosure door enters is left out of the count (as the route
    /// reader reads it: its every door between rooms is that exit); where both rooms could be, both stay counted.</summary>
    [Fact]
    public void Only_the_exit_enclosure_itself_is_left_out_of_the_count()
    {
        var floor = new FakeFloor();
        floor.SetMark("dA", Marks.Exit, new(true, Text: "Exit stair enclosure"));
        var line = Line(Model(floor, "R-2"));
        // dA (office A to the corridor) is now marked an exit too: A's one door is that exit, so A could be the
        // enclosure, the corridor can't (dB is plain): A is left out, as the route reader reads it
        Assert.DoesNotContain(FakeFloor.Uid("A"), line!.Unset);
        // office A opening straight onto the stair, with a plain door to office B too: the stair is the enclosure, A is counted
        List<OpeningSides> sides =
        [
            new(FakeFloor.Uid("dA"), FakeFloor.Uid("A"), FakeFloor.Uid("S"), FakeFloor.Level, "Level 1", 0),
            new(FakeFloor.Uid("dB"), FakeFloor.Uid("A"), FakeFloor.Uid("B"), FakeFloor.Level, "Level 1", 0),
            new(FakeFloor.Uid("dS2"), FakeFloor.Uid("S"), null, FakeFloor.Level, "Level 1", 0),
        ];
        var direct = SetupChecklist.Build(Model(floor, "R-2"), sides, "building", routes: true, buildingCode: true).Single(l => l.Key == "room_function");
        Assert.Contains(FakeFloor.Uid("A"), direct.Unset);
        Assert.DoesNotContain(FakeFloor.Uid("S"), direct.Unset);
        // neither side can be told (A's one door is the exit too): both stay counted, never a guess
        List<OpeningSides> both = [sides[0], sides[2]];
        var unclear = SetupChecklist.Build(Model(floor, "R-2"), both, "building", routes: true, buildingCode: true).Single(l => l.Key == "room_function");
        Assert.Contains(FakeFloor.Uid("A"), unclear.Unset);
        Assert.Contains(FakeFloor.Uid("S"), unclear.Unset);
    }

    /// <summary>Review round 3: a function on a corridor or on the exit enclosure contradicts it (the occupant loads then
    /// leave the story's load not worked out), so the line names it to clear and never reads done.</summary>
    [Fact]
    public void A_function_on_a_corridor_or_the_exit_enclosure_is_named_to_clear_never_done()
    {
        var floor = new FakeFloor();
        foreach (var id in new[] { "A", "B", "L" })
            floor.SetMark(id, Marks.RoomFunction, new(true, Text: "Business area"));
        var before = Line(Model(floor, "B"))!;
        Assert.True(before.Done);                                                     // the three occupied rooms: done
        Assert.DoesNotContain("to clear", SetupSteps.LineCount(before), StringComparison.Ordinal);
        floor.SetMark("C", Marks.RoomFunction, new(true, Text: "Business area"));      // the corridor (its Use)
        floor.SetMark("S", Marks.RoomFunction, new(true, Text: "Business area"));      // the stair dS enters
        var line = Line(Model(floor, "B"))!;
        Assert.False(line.Done);
        Assert.Equal((3, 5), (line.Set, line.Total));
        Assert.Equal([FakeFloor.Uid("C"), FakeFloor.Uid("S")], line.Unset.Order(StringComparer.Ordinal));
        Assert.Equal(2, line.Notes.Count);
        Assert.Contains(line.Notes, n => n.Contains("a corridor holds no occupant load of its own", StringComparison.Ordinal));
        Assert.Contains(line.Notes, n => n.Contains("an exit stair enclosure holds no occupant load of its own", StringComparison.Ordinal));
        // said in the count itself, never only behind "Why?" (review round 4)
        Assert.Equal("Room function: 3 of 5 rooms set, 2 to clear (a function on corridors or exits: Corridor (C), Stair 1 (S)).",
                     SetupSteps.LineCount(line));
        // an exit passageway is named for what it is (review round 4)
        floor.SetMark("dS", Marks.Exit, new(true, Text: "Exit passageway"));
        Assert.Contains(Line(Model(floor, "B"))!.Notes, n => n.Contains("an exit passageway holds no occupant load of its own", StringComparison.Ordinal));
    }

    /// <summary>Review round 2: what stays blank is said by the Use mark, the one the count and the occupant loads read:
    /// a room only named so ("Bathroom 1") with no Use is counted, still to set.</summary>
    [Fact]
    public void What_stays_blank_is_said_by_the_use_mark()
    {
        var floor = new FakeFloor();
        Name(floor, "A", "Bathroom 1");
        floor.SetMark("A", Marks.Use, null);
        var line = Line(Model(floor, "R-2"))!;
        Assert.Contains(FakeFloor.Uid("A"), line.Unset);
        Assert.DoesNotContain(FakeFloor.Uid("A"), Suggested(line).Keys);             // never a suggestion for it
        Assert.Contains("A room whose Gordium: Use is Corridor, Closet or Toilet, and an exit stair enclosure or exit passageway, stay blank (they aren't counted here unless one holds a function)", line.IfBlank, StringComparison.Ordinal);
        Assert.Contains("on a room whose Gordium: Use is Corridor, Closet or Toilet", Marks.RoomFunction.Description, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("Closet 3", "Other")]
    [InlineData("Toilet", "Other")]
    [InlineData("Bath Room", "Other")]
    [InlineData("Hallway", "Other")]
    [InlineData("Storage", "Closet")]
    [InlineData("Bedroom", "Toilet")]
    [InlineData("Living", "Corridor")]
    [InlineData("Linen storage closet", "Other")]
    public void No_function_is_suggested_for_a_closet_a_toilet_or_a_corridor(string name, string use)
    {
        var floor = new FakeFloor();
        Name(floor, "A", name);
        floor.SetMark("A", Marks.Use, new(true, Text: use));
        Assert.DoesNotContain(FakeFloor.Uid("A"), Suggested(Line(Model(floor, "R-2"))!).Keys);
    }

    [Fact]
    public void An_accessory_storage_room_is_table_1004_5s_accessory_storage_row_and_a_set_function_is_kept()
    {
        var floor = new FakeFloor();
        floor.SetMark("A", Marks.Use, new(true, Text: "Accessory storage"));
        Name(floor, "B", "Mechanical Room");
        Name(floor, "L", "Bedroom");
        floor.SetMark("L", Marks.RoomFunction, new(true, Text: "Dormitory"));      // the architect's: never suggested over
        var line = Line(Model(floor, "R-2"))!;
        var got = Suggested(line);
        Assert.Equal("Accessory storage or mechanical equipment room", got[FakeFloor.Uid("A")]);
        Assert.Equal("Accessory storage or mechanical equipment room", got[FakeFloor.Uid("B")]);
        Assert.DoesNotContain(FakeFloor.Uid("L"), got.Keys);
        Assert.Contains("its Gordium: Use is Accessory storage", line.Suggestions.Single(s => s.Element == FakeFloor.Uid("A")).Basis, StringComparison.Ordinal);
        // a typed word not in the list is not set, but the architect typed it: never suggested over either
        floor.SetMark("L", Marks.RoomFunction, new(true, Text: "dorm"));
        Assert.DoesNotContain(FakeFloor.Uid("L"), Suggested(Line(Model(floor, "R-2"))!).Keys);
    }

    [Fact]
    public void A_suggestion_is_written_only_when_accepted_and_reads_back_as_its_row()
    {
        var floor = new FakeFloor();
        Name(floor, "A", "Bedroom 1");
        var line = Line(Model(floor, "R-3"))!;
        Assert.Null(FakeFloor.Part(InteriorReader.Read(floor.Model()), "rooms", "A")!["function"]);   // shown, not sent
        var write = Assert.Single(SetupWrites.Accept(line.Suggestions));
        Assert.Equal((FakeFloor.Uid("A"), false, Marks.RoomFunction, "Residential"), (write.Element, write.OnType, write.Mark, write.Value.Text));
        floor.SetMark("A", Marks.RoomFunction, write.Value);
        Assert.Equal("residential", FakeFloor.Part(InteriorReader.Read(floor.Model()), "rooms", "A")!["function"]!.GetValue<string>());
        Assert.Empty(SetupWrites.Accept([]));                              // nothing accepted: nothing written
    }

    [Fact]
    public void A_workers_card_for_a_rooms_function_names_its_mark()
    {
        var card = new CauseCard("model:space:function", CauseKind.Mark, "Set the room's function", ["uid-A"], ["r"], null, "review")
        {
            Fields = ["rooms[].function"],
        };
        Assert.Equal([Marks.RoomFunction], CauseCards.MarksOf(card));
    }
}
