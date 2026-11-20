using System.Diagnostics;
using System.Text.Json;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The architect's marks (docs/revit/revit_interior_reading_design.md, sections 2, 3 and 5a; section 7,
/// step 2): the shared parameters as data, adding them to a project, reading them (an unset mark is not stated,
/// never No), and the marking list (unset first; a room name only ever a suggestion). Each is pinned on fake records;
/// that Revit's API gives what the records say (an unset Yes/No's <c>HasValue</c> false, on old and new elements) is
/// for the trial to confirm.</summary>
public sealed class MarksTests
{
    // ---- the parameters, as the design note's table -------------------------------------------------------------

    [Fact]
    public void The_marks_are_the_design_notes_table_and_their_guids_never_change()
    {
        // a changed GUID is a different parameter: every mark set on the old one would read as not set
        var expected = new (string Name, string Guid, MarkValueKind Kind, MarkBinding Binding, string[] Categories)[]
        {
            ("Gordium: Sleeping room", "938333c3-b268-495a-8835-5c667a514122", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Rooms"]),
            ("Gordium: Escape opening", "04893afb-a562-4d71-b5c9-28c4e9541060", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Exit door", "ba0a9f39-5bce-4e05-98f9-15b639b9eb2a", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_Doors"]),
            ("Gordium: Operation", "7b1e6d97-1774-458d-8f46-90002a1881c0", MarkValueKind.Text, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            // step 5: a door type's maker's clear opening too (no offset: a door's clear opening has no bottom sent)
            ("Gordium: Clear width", "8cb5d70c-116d-4621-9876-fd15c4c55f5c", MarkValueKind.Length, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Clear height", "8a8a2307-84a5-4a36-9121-c21453707702", MarkValueKind.Length, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Clear offset", "07f4d517-54a6-4e39-ba85-90c299137a28", MarkValueKind.Length, MarkBinding.Type, ["OST_Windows"]),
            ("Gordium: Clear source", "2bc7eaef-1770-4077-870b-450ed224adde", MarkValueKind.Text, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Clear confirmed", "66ced3f6-2dd7-4aa7-a0ce-89d086652103", MarkValueKind.Text, MarkBinding.Type, ["OST_Windows", "OST_Doors"]),
            ("Gordium: Top rail is handrail", "8f09dc9e-0975-42ba-8a4b-43e43b393578", MarkValueKind.YesNo, MarkBinding.Type, ["OST_StairsRailing"]),
            ("Gordium: These are all the stairs", "90205a68-1eaf-4ca2-a350-0cb24012986c", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: These are all the guards and handrails", "80055f84-3feb-492a-b581-331ff692a2a9", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            // Check my project's lot facts (reading design note, section 9)
            ("Gordium: Zone", "7c0c478b-5959-44fd-bf53-ca89d9302bf0", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Use", "0a732869-f46a-4fbd-bab9-4d60735d96f3", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Lot surveyed", "133d30e3-832f-4956-88c3-6b48989ac3f7", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Corner lot", "b37e1302-284e-4440-bc43-a44309ea8991", MarkValueKind.YesNo, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Street edge", "260b3e70-6b9b-45d2-8137-a5c18db9ccf5", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
            ("Gordium: Ground from", "aa4ea7e3-5a41-48da-b6a8-979f3dfb3e5c", MarkValueKind.Text, MarkBinding.Instance, ["OST_ProjectInformation"]),
        };
        Assert.Equal(expected.Length, Marks.All.Count);
        foreach (var (m, e) in Marks.All.Zip(expected))
        {
            Assert.Equal(e.Name, m.Name);
            Assert.Equal(Guid.Parse(e.Guid), m.Guid);
            Assert.Equal(e.Kind, m.Kind);
            Assert.Equal(e.Binding, m.Binding);
            Assert.Equal(e.Categories, m.Categories);
            Assert.False(string.IsNullOrWhiteSpace(m.Description));
        }
        Assert.Equal(Marks.All.Count, Marks.All.Select(m => m.Guid).Distinct().Count());
    }

    [Fact]
    public void The_design_note_names_each_mark()
    {
        var note = File.ReadAllText(Path.Combine(Env.Repo, "docs", "revit", "revit_interior_reading_design.md"));
        foreach (var m in Marks.All)
            Assert.Contains(m.Name.Replace("Gordium: ", ""), note);
    }

    // ---- reading a mark: unset is not stated -------------------------------------------------------------------

    [Fact]
    public void An_unset_yes_no_is_not_stated_never_no()
    {
        Assert.Null(Marks.YesNo(null));                                   // not on the element at all
        Assert.Null(Marks.YesNo(new MarkValue(false, Integer: 0)));       // never set: Revit's AsInteger() gives 0
        Assert.Null(Marks.YesNo(new MarkValue(true)));                    // set, but not an integer
        Assert.Null(Marks.YesNo(new MarkValue(true, Integer: 2)));
        Assert.Null(Marks.YesNo(new MarkValue(true, Text: "Yes")));
        Assert.True(Marks.YesNo(new MarkValue(true, Integer: 1)));
        Assert.False(Marks.YesNo(new MarkValue(true, Integer: 0)));
    }

    [Fact]
    public void A_blank_length_or_text_is_not_stated_never_zero()
    {
        Assert.Null(Marks.Length(new MarkValue(false, Number: 0)));       // blank Clear offset: never 0
        Assert.Null(Marks.Length(new MarkValue(true, Number: double.NaN)));
        Assert.Null(Marks.Length(new MarkValue(true)));
        Assert.Equal(0.0, Marks.Length(new MarkValue(true, Number: 0)));  // a 0 typed is a 0 (the stamp, step 3, checks it)
        Assert.Null(Marks.Text(new MarkValue(true, Text: "   ")));
        Assert.Null(Marks.Text(new MarkValue(false, Text: "Casement")));
        Assert.Equal("Casement", Marks.Text(new MarkValue(true, Text: " Casement ")));
    }

    // ---- the operation list ---------------------------------------------------------------------------------

    [Fact]
    public void Operation_words_map_to_each_lists_own_word()
    {
        Assert.Equal("side_hinged_door", Operations.ForOpening("Side-hinged door"));
        Assert.Equal("side_hinged", Operations.ForDoor("side-hinged DOOR"));
        Assert.Equal("sliding_door", Operations.ForOpening("Sliding door"));
        Assert.Equal("sliding", Operations.ForDoor("Sliding door"));
        Assert.Equal("other", Operations.ForOpening("Pocket door"));     // no pocket word for an opening: needs the maker's
        Assert.Equal("pocket", Operations.ForDoor("Pocket door"));
        Assert.Equal("double_hung", Operations.ForOpening("Double hung"));
        Assert.Null(Operations.ForDoor("Casement"));                    // a window's word is not a door's
        Assert.Null(Operations.ForOpening("Double-hung"));             // near is not a word: not stated
        Assert.Null(Operations.ForOpening("Casment"));
        Assert.Null(Operations.ForOpening(null));
    }

    [Fact]
    public void Operation_words_reach_exactly_the_measuring_codes_words()
    {
        // the words the measuring code accepts, from its own tables (never retyped)
        var json = Python(
            "import json; from model_measurement.interior import openings, doors; " +
            "print(json.dumps({'opening': list(openings.OPERATIONS), 'door': list(doors.OPERATIONS)}))");
        using var doc = JsonDocument.Parse(json);
        var opening = doc.RootElement.GetProperty("opening").EnumerateArray().Select(e => e.GetString()!).ToHashSet();
        var door = doc.RootElement.GetProperty("door").EnumerateArray().Select(e => e.GetString()!).ToHashSet();
        Assert.Equal(opening, Operations.Words.Select(Operations.ForOpening).ToHashSet()!);
        Assert.Equal(door, Operations.Words.Select(Operations.ForDoor).OfType<string>().ToHashSet());
    }

    private static string Python(string code)
    {
        var info = new ProcessStartInfo(Env.Python)
        {
            WorkingDirectory = Env.Repo, RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false,
        };
        info.ArgumentList.Add("-c");
        info.ArgumentList.Add(code);
        using var p = Process.Start(info)!;
        var err = p.StandardError.ReadToEndAsync();
        var output = p.StandardOutput.ReadToEnd();
        Assert.True(p.WaitForExit(120_000), "python didn't finish");
        Assert.True(p.ExitCode == 0, err.Result);
        return output;
    }

    // ---- adding the marks to a project ----------------------------------------------------------------------

    private static BoundParameter Bound(MarkDefinition m, params string[] categories) =>
        new(m.Name, m.Guid, m.Kind, m.Kind.ToString(), m.Binding == MarkBinding.Instance, categories.Length > 0 ? categories : m.Categories);

    [Fact]
    public void A_new_project_gets_every_mark()
    {
        var plan = MarkSetup.Plan([]);
        Assert.All(plan, s => Assert.Equal(MarkSetupAction.Add, s.Action));
        Assert.Equal(Marks.All, plan.Select(s => s.Mark));
        Assert.Equal(Marks.EscapeOpening.Categories, plan[1].Categories);
    }

    [Fact]
    public void A_project_with_the_marks_is_left_as_it_is()
    {
        var plan = MarkSetup.Plan(Marks.All.Select(m => Bound(m)).ToList());
        Assert.All(plan, s => Assert.Equal(MarkSetupAction.None, s.Action));
    }

    [Fact]
    public void A_missing_category_is_added_and_the_architects_own_are_kept()
    {
        var bound = Marks.All.Select(m => m == Marks.EscapeOpening ? Bound(m, "OST_Windows", "OST_GenericModel") : Bound(m)).ToList();
        var step = MarkSetup.Plan(bound).Single(s => s.Mark == Marks.EscapeOpening);
        Assert.Equal(MarkSetupAction.AddCategories, step.Action);
        Assert.Equal(["OST_Windows", "OST_GenericModel", "OST_Doors"], step.Categories);
    }

    [Fact]
    public void Another_parameter_of_a_marks_name_is_never_taken_for_it()
    {
        var firms = new BoundParameter("gordium: sleeping room", Guid.NewGuid(), MarkValueKind.YesNo, "YesNo", true, ["OST_Rooms"]);
        var plan = MarkSetup.Plan([firms]);
        var step = plan.Single(s => s.Mark == Marks.SleepingRoom);
        Assert.Equal(MarkSetupAction.Conflict, step.Action);
        Assert.Contains("isn't Gordium's", step.Words);
        Assert.Equal(MarkSetupAction.Add, plan.Single(s => s.Mark == Marks.ExitDoor).Action);
        // and the reader reads by GUID: the firm's own Yes is not a mark
        var model = Model(Room("r", "Bedroom", null) with
        {
            Instance = new Dictionary<Guid, MarkValue> { [firms.Guid!.Value] = new(true, Integer: 1) },
        });
        Assert.Null(MarkReading.Rooms(model)!.Single().Sleeping);
    }

    [Fact]
    public void A_mark_bound_the_wrong_way_is_a_conflict_never_rebound()
    {
        var typeBound = Bound(Marks.SleepingRoom) with { IsInstance = false };
        var textKind = Bound(Marks.ExitDoor) with { Kind = MarkValueKind.Text };
        var plan = MarkSetup.Plan([typeBound, textKind]);
        Assert.Equal(MarkSetupAction.Conflict, plan.Single(s => s.Mark == Marks.SleepingRoom).Action);
        Assert.Equal(MarkSetupAction.Conflict, plan.Single(s => s.Mark == Marks.ExitDoor).Action);
        var list = MarkingList.Build(Model(), plan);
        Assert.Equal(2, list.SetupProblems.Count);
        Assert.StartsWith("Can't add Gordium: Sleeping room", MarkingList.Text(list));
    }

    // ---- reading the marks ----------------------------------------------------------------------------------

    private static RevitModel Model(params MarkedElement[] marked) => new() { Document = "house.rvt", Marked = marked };

    private static MarkValue YesNo(bool? v) => v is { } b ? new(true, Integer: b ? 1 : 0) : new(false, Integer: 0);

    private static MarkedElement Room(string id, string? name, bool? sleeping, string? number = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Rooms, Name = name, Number = number, Placement = RoomPlacement.Placed,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.SleepingRoom.Guid] = YesNo(sleeping) },
    };

    private static MarkedElement Window(string id, bool? escape, string? operation) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Windows, Name = "36 x 48", Family = "Casement", TypeUniqueId = "t-" + id,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = YesNo(escape) },
        Type = operation is null ? new Dictionary<Guid, MarkValue>()
            : new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: operation) },
    };

    private static MarkedElement Door(string id, bool? escape, bool? exit, string? operation) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Doors, Name = "36 x 80", Family = "Single-Flush",
        Instance = new Dictionary<Guid, MarkValue>
        {
            [Marks.EscapeOpening.Guid] = YesNo(escape), [Marks.ExitDoor.Guid] = YesNo(exit),
        },
        Type = operation is null ? new Dictionary<Guid, MarkValue>()
            : new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: operation) },
    };

    [Fact]
    public void Marks_are_read_as_set_and_unset_as_not_stated()
    {
        var model = Model(Room("bed", "Bedroom 2", true), Room("living", "Living", false), Room("study", "Study", null),
                          Window("w1", true, "Casement"), Window("w2", null, "Double-hung"),
                          Door("d1", false, true, "Side-hinged door"), Door("d2", false, null, "Casement"));
        Assert.Equal([true, false, null], MarkReading.Rooms(model)!.Select(r => r.Sleeping));
        var openings = MarkReading.Openings(model);
        Assert.Equal([true, null, false, false], openings.Select(o => o.Escape));
        Assert.Equal(["casement", null, "side_hinged_door", null], openings.Select(o => o.Operation));
        var doors = MarkReading.Doors(model);
        Assert.Equal([true, null], doors.Select(d => d.Exit));
        Assert.Equal(["side_hinged", null], doors.Select(d => d.Operation));
    }

    [Fact]
    public void A_bedroom_by_name_alone_is_never_read_as_a_sleeping_room()
    {
        var model = Model(Room("bed", "Bedroom 2", null));
        Assert.Null(MarkReading.Rooms(model)!.Single().Sleeping);
        var cell = MarkingList.Build(model).Rows.Single().Cells.Single();
        Assert.Equal(MarkState.Unset, cell.State);
        Assert.StartsWith("suggested: Yes", cell.Suggestion);
    }

    [Fact]
    public void Only_the_design_checked_is_read_and_listed()
    {
        var model = Model(
            Window("now", true, "Casement"),
            Window("demolished", true, "Casement") with { PhaseDemolished = "new" },
            Window("wide", true, "Casement") with { DesignOption = "w2" },
            Window("narrow", true, "Casement") with { DesignOption = "w1" }) with
        {
            Phases = ["existing", "new"],
            OptionSets = [new("wing", "Wing", [new("w1", "Narrow", true), new("w2", "Wide", false)])],
        };
        Assert.Equal(["now", "narrow"], MarkReading.Openings(model).Select(o => o.Id));
        Assert.Equal(["narrow", "now"], MarkingList.Build(model).Rows.Select(r => r.Id).Order());
    }

    // review round 1, finding 2: a room belongs to one phase; an earlier phase's room isn't the design checked
    [Fact]
    public void Only_the_last_phases_rooms_are_read()
    {
        var model = Model(Room("old", "Bedroom", true) with { PhaseCreated = "existing" },
                          Room("now", "Bedroom", true) with { PhaseCreated = "new" },
                          Window("kept", false, "Casement") with { PhaseCreated = "existing" }) with
        {
            Phases = ["existing", "new"],
        };
        Assert.Equal(["now"], MarkReading.Rooms(model)!.Select(r => r.Id));
        Assert.Equal(["kept"], MarkReading.Openings(model).Select(o => o.Id));
        Assert.Equal(["now", "kept"], MarkingList.Build(model).Rows.Select(r => r.Id));
    }

    // review round 1, finding 2: a Room not on the plan blocks every room, listed first, never a row to mark
    [Fact]
    public void An_unplaced_not_enclosed_or_redundant_room_is_a_blocker_not_a_row()
    {
        var model = Model(Room("placed", "Living", false),
                          Room("unplaced", "Bedroom 3", null) with { Placement = RoomPlacement.Unplaced },
                          Room("open", "Den", false) with { Placement = RoomPlacement.NotEnclosed },
                          Room("twice", "Study", false) with { Placement = RoomPlacement.Redundant },
                          Room("unknown", "Hall", false) with { Placement = null });
        Assert.Null(MarkReading.Rooms(model));            // round 2: rooms not read while any blocker exists
        Assert.Equal(["placed"], MarkReading.Rooms(model with { Marked = [model.Marked[0]] })!.Select(r => r.Id));
        Assert.Equal(4, MarkReading.RoomBlockers(model).Count);
        var list = MarkingList.Build(model);
        Assert.Equal(["placed"], list.Rows.Select(r => r.Id));
        Assert.Equal(
        [
            "Room \"Bedroom 3\": not placed: place it in a closed area or delete it",
            "Room \"Den\": not enclosed: close its walls or room separation lines, or delete it",
            "Room \"Hall\": its placement couldn't be read",
            "Room \"Study\": redundant (another room is in the same area): delete one",
        ], list.RoomBlockers);
        Assert.StartsWith("4 Rooms are unplaced", list.Summary[0]);
        Assert.StartsWith("Room \"Bedroom 3\": not placed", MarkingList.Text(list));
        Assert.Equal(MarkingListResult.NotAllMarked, list.Headline);
    }

    // review round 2, findings 1 and 2: a model whose only Room is a blocker says so once, in the singular, and
    // names Revit's default "Room 100" once
    [Fact]
    public void Only_a_blocker_room_one_line_singular_and_the_name_once()
    {
        var list = MarkingList.Build(Model(Room("r", "Room", null, "100") with { Placement = RoomPlacement.NotEnclosed }));
        Assert.StartsWith("1 Room is unplaced, not enclosed or redundant", list.Summary[0]);
        Assert.DoesNotContain(list.Summary, l => l.StartsWith(MarkingListResult.NoRooms, StringComparison.Ordinal));
        Assert.Equal(["Room \"Room 100\": not enclosed: close its walls or room separation lines, or delete it"], list.RoomBlockers);
        Assert.DoesNotContain("Room Room", MarkingList.Text(list));
        Assert.Equal("A room with no name or number: not placed: place it in a closed area or delete it",
                     MarkingList.Build(Model(Room("x", null, null) with { Placement = RoomPlacement.Unplaced })).RoomBlockers.Single());
        Assert.Null(MarkReading.Rooms(Model(Room("r", "Room", null, "100") with { Placement = RoomPlacement.NotEnclosed })));
    }

    // review round 1, finding 3: "every room, window and door is marked" only when there are rooms and all are marked
    [Fact]
    public void The_headline_says_all_marked_only_when_rooms_are_drawn_and_marked()
    {
        Assert.Equal(MarkingListResult.NothingDrawn, MarkingList.Build(Model()).Headline);
        Assert.Equal(MarkingListResult.NoRooms, MarkingList.Build(Model(Window("w", true, "Casement"))).Headline);
        Assert.Equal(MarkingListResult.NotAllMarked, MarkingList.Build(Model(Room("r", "Bed", null))).Headline);
        Assert.Equal(MarkingListResult.AllMarked,
                     MarkingList.Build(Model(Room("r", "Bed", true), Window("w", true, "Casement"))).Headline);
    }

    // ---- the marking list -------------------------------------------------------------------------------------

    [Fact]
    public void The_list_puts_anything_unset_first_and_says_what_it_leaves_not_read()
    {
        var model = Model(Room("living", "Living", false, "101"), Room("bed", "Bedroom 2", null, "102"),
                          Window("w1", true, "Casement"), Window("w2", false, null),
                          Door("d1", false, true, "Side-hinged door"), Door("d2", null, false, "Sliding door"));
        var list = MarkingList.Build(model);
        Assert.Equal(["bed", "w2", "d2", "living", "w1", "d1"], list.Rows.Select(r => r.Id));
        Assert.Equal(["Bedroom 2 102", "Casement: 36 x 48"], list.Rows.Take(2).Select(r => r.Label));
        Assert.Equal(
        [
            "Gordium: Sleeping room: 1 of 2 rooms not marked, so no room is read for egress until each says Yes or No.",
            "Gordium: Escape opening: 1 of 4 windows and doors not marked, so no escape opening is read until each says Yes or No.",
            "Gordium: Exit door: all 2 doors marked.",
            "Gordium: Operation: 1 windows and doors have no operation Gordium reads, so their egress measures need review.",
            "Gordium: These are all the stairs: not set on Project Information, so no stair is read for egress until it says Yes.",
            "Gordium: These are all the guards and handrails: not set on Project Information, so no guard or handrail is read for egress until it says Yes.",
        ], list.Summary);
        var ticked = model with
        {
            ProjectMarks = new Dictionary<Guid, MarkValue> { [Marks.AllStairs.Guid] = new(true, 1), [Marks.AllGuards.Guid] = new(true, 1) },
        };
        Assert.Equal("Gordium: These are all the stairs: Yes (on Project Information).", MarkingList.Build(ticked).Summary[^2]);
        Assert.Equal("Gordium: These are all the guards and handrails: Yes (on Project Information).", MarkingList.Build(ticked).Summary[^1]);
        var unset = model with
        {
            ProjectMarks = new Dictionary<Guid, MarkValue> { [Marks.AllStairs.Guid] = new(false, 0), [Marks.AllGuards.Guid] = new(false, 0) },   // never set reads 0
        };
        Assert.Contains("not set on Project Information", MarkingList.Build(unset).Summary[^2]);
        Assert.Contains("not set on Project Information", MarkingList.Build(unset).Summary[^1]);
        var text = MarkingList.Text(list);
        Assert.StartsWith("Gordium: Sleeping room: 1 of 2", text);
        Assert.Contains("TO MARK  Room: Bedroom 2 102\n    Gordium: Sleeping room: not set - suggested: Yes", text);
    }

    [Fact]
    public void A_suggestion_is_only_ever_yes_and_only_on_an_unset_room()
    {
        var list = MarkingList.Build(Model(Room("a", "Master bedroom", false), Room("b", "Sleeping porch", null),
                                           Room("c", "Bedroom closet", true), Room("d", "Bath", null), Room("e", null, null)));
        var byId = list.Rows.ToDictionary(r => r.Id, r => r.Cells.Single());
        Assert.Null(byId["a"].Suggestion);                // marked No: the architect's own fact stands
        Assert.NotNull(byId["b"].Suggestion);
        Assert.Null(byId["c"].Suggestion);
        Assert.Null(byId["d"].Suggestion);                 // never a suggested No
        Assert.Null(byId["e"].Suggestion);
        Assert.Equal("(a room with no name or number)", list.Rows.Single(r => r.Id == "e").Label);
    }

    [Fact]
    public void An_operation_word_gordium_doesnt_read_is_listed_with_why()
    {
        var list = MarkingList.Build(Model(Door("d", false, true, "Casement"), Window("w", false, "Double-hung")));
        var door = list.Rows.Single(r => r.Id == "d").Cells.Single(c => c.Mark == Marks.Operation);
        Assert.Equal(MarkState.NotUnderstood, door.State);
        Assert.Contains("a window's operation, not a door's", door.Words);
        var window = list.Rows.Single(r => r.Id == "w").Cells.Single(c => c.Mark == Marks.Operation);
        Assert.Equal(MarkState.NotUnderstood, window.State);
        Assert.Contains("isn't one of Gordium's operations", window.Words);
        Assert.All(list.Rows, r => Assert.True(r.NeedsMarking));
    }

    [Fact]
    public void A_model_with_no_rooms_says_so()
    {
        var list = MarkingList.Build(Model(Window("w", true, "Casement")));
        Assert.Equal("No rooms are drawn: egress waits until the house's Rooms are placed.", list.Summary[0]);
    }
}
