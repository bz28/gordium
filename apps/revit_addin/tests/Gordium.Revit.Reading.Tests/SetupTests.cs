using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The Setup form's decisions (Setup.cs; docs/decisions/2026-11-22_setup_form.md), without Revit: which facts it
/// lists and how each is entered, what a Save writes (only what the architect chose: a blank stays blank), that a
/// suggestion is never written by itself and each says what it is based on, when the form shows and when the check runs
/// by itself, that a write makes results stale, and the words by building type.</summary>
public sealed class SetupTests
{
    // ---- a small house: two bedrooms, a living room, a hall; windows and doors with their rooms --------------------

    private static MarkValue YesNo(bool? v) => v is { } b ? new(true, b ? 1 : 0) : new(false, 0);

    private static MarkedElement Room(string id, string name, bool? sleeping = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Rooms, Name = name, Number = id, Placement = RoomPlacement.Placed,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.SleepingRoom.Guid] = YesNo(sleeping) },
    };

    private static MarkedElement Window(string id, string type, string family, double w, double h, bool? escape = null, string? operation = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Windows, Name = type, Family = family, Number = id, TypeUniqueId = "t-" + family + type,
        TypeWidth = w, TypeHeight = h,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = YesNo(escape) },
        Type = operation is null ? new Dictionary<Guid, MarkValue>() : new Dictionary<Guid, MarkValue> { [Marks.Operation.Guid] = new(true, Text: operation) },
    };

    private static MarkedElement Door(string id, string family = "Single-Flush", bool? exit = null) => new()
    {
        UniqueId = id, BuiltInCategory = Marks.Doors, Name = "36\" x 80\"", Family = family, Number = id, TypeUniqueId = "t-" + family,
        Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = YesNo(null), [Marks.ExitDoor.Guid] = YesNo(exit) },
    };

    private static readonly MarkedElement[] House =
    [
        Room("bed1", "Bedroom 1"), Room("bed2", "BR 2"), Room("living", "Living", sleeping: false), Room("hall", "Hall"),
        Window("w1", "36 x 60", "Casement", 3, 5), Window("w2", "48 x 60", "Fixed", 4, 5), Window("w3", "24 x 36", "Casement", 2, 3),
        Window("w4", "36 x 48", "Double Hung", 3, 4), Window("w5", "36 x 48", "Double Hung", 3, 4),
        Door("front"), Door("bed1door"), Door("upper", "Exterior Single"),
    ];

    private static readonly OpeningSides[] Sides =
    [
        new("w1", "bed1", null, "L1", "Level 1", 0), new("w2", "bed1", null, "L1", "Level 1", 0), new("w3", "bed1", null, "L1", "Level 1", 0),
        new("w4", "living", null, "L1", "Level 1", 0), new("w5", "hall", null, "L1", "Level 1", 0),
        new("front", "hall", null, "L1", "Level 1", 0), new("bed1door", "bed1", "hall", "L1", "Level 1", 0),
        new("upper", null, "bed2", "L2", "Level 2", 10),
    ];

    private static RevitModel Model(Dictionary<Guid, MarkValue>? project = null, params MarkedElement[] marked) =>
        new() { Document = "house.rvt", Marked = marked.Length == 0 ? House : marked, ProjectMarks = project ?? [] };

    private static readonly PlaceOptions Options = new(
        ["R-1a", "R-1b", "R-2a"],
        [("one_family_detached", "One-family dwelling, detached"), ("two_family_detached", "Two-family dwelling, detached"),
         ("day_care", "Day care center")],
        new Dictionary<string, IReadOnlyList<UseChoice>>
        {
            ["R-1b"] = [new("one_family_detached", "One-family dwelling, detached", true, null),
                        new("two_family_detached", "Two-family dwelling, detached", false, "by special permit (zoning chart p.2)")],
        });

    private static Dictionary<Guid, MarkValue> AllStated() => new()
    {
        [Marks.Zone.Guid] = new(true, Text: "R-1b"), [Marks.Use.Guid] = new(true, Text: "one_family_detached"),
        [Marks.LotSurveyed.Guid] = new(true, 1), [Marks.StreetEdge.Guid] = new(true, Text: StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(60, 0, 0))])),
    };

    private static SetupScreen Screen(RevitModel model, SetupDraft? draft = null, PlaceOptions? options = null) =>
        SetupScreen.Build(model, Sides, options ?? Options, draft);

    // ---- the project facts --------------------------------------------------------------------------------------

    /// <summary>Data, not a hand list: every mark Marks.All binds to Project Information is a field, exactly once, in
    /// a heading found from what it feeds, so the marks another branch adds there appear with no change here.</summary>
    [Fact]
    public void Every_project_information_mark_is_a_field_once()
    {
        var fields = Screen(Model()).Fields;
        var want = Marks.All.Where(m => m.Categories.Contains(Marks.ProjectInformation)).Select(m => m.Guid).Order().ToList();
        Assert.Equal(want, fields.Select(f => f.Mark.Guid).Order().ToList());
        Assert.Equal([Marks.Zone, Marks.Use, Marks.LotSurveyed, Marks.StreetEdge],
                     fields.Where(f => f.Group == SetupFacts.NeededGroup).Select(f => f.Mark));
        Assert.All(fields, f => Assert.Equal(f.Required, SetupFacts.Required.Contains(f.Mark)));
        // a new mark's heading from its Feeds: building.* is which code, facts.* the lot, has_none what it has none of
        var code = new MarkDefinition("Gordium: Sprinkler system", Guid.NewGuid(), MarkValueKind.Text, MarkBinding.Instance,
                                      [Marks.ProjectInformation], "building.sprinkler_system", "x");
        Assert.Equal(SetupFacts.CodeGroup, SetupFacts.Group(code, "building"));
        Assert.Equal("The lot and the building", SetupFacts.Group(Marks.CornerLot, "building"));
        Assert.Equal("What the house has none of", SetupFacts.Group(Marks.NoStairs, "house"));
    }

    /// <summary>Each field's kind and allowed values: the zone the districts with a rulebook, the use the district's
    /// uses with their names (a special-permit one saying so), Yes/No toggles, a number for the stories, a pick for the
    /// street edge; each shows the law it answers (the mark's own words).</summary>
    [Fact]
    public void Fields_are_dropdowns_toggles_a_number_and_a_pick_with_their_law()
    {
        var fields = Screen(Model(new() { [Marks.Zone.Guid] = new(true, Text: "R-1b") })).Fields.ToDictionary(f => f.Mark.Guid);
        var zone = fields[Marks.Zone.Guid];
        Assert.Equal(FieldKind.Choice, zone.Kind);
        Assert.Equal(["R-1a", "R-1b", "R-2a"], zone.Choices.Select(c => c.Value));
        var use = fields[Marks.Use.Guid];
        // the district's own first, then every other city use, said not listed there (the true use can always be stated)
        Assert.Equal(["one_family_detached", "two_family_detached", "day_care"], use.Choices.Select(c => c.Value));
        // R2 #2: what the checker decides for a use the chart doesn't list (its use row: does not comply)
        Assert.Equal("Day care center (not on R-1b's list of uses: its use row won't comply)", use.Choices[2].Label);
        Assert.DoesNotContain("needs review", use.Choices[2].Label, StringComparison.Ordinal);
        Assert.DoesNotContain("one_family_detached", use.Law, StringComparison.Ordinal);   // plain help, not Gordium's words
        Assert.Equal("Two-family dwelling, detached (by special permit (zoning chart p.2))", use.Choices[1].Label);
        Assert.Equal(FieldKind.YesNo, fields[Marks.LotSurveyed.Guid].Kind);
        Assert.Equal(FieldKind.Number, fields[Marks.Stories.Guid].Kind);
        Assert.Equal(FieldKind.StreetPick, fields[Marks.StreetEdge.Guid].Kind);
        Assert.Equal(FieldKind.Choice, fields[Marks.GroundFrom.Guid].Kind);
        Assert.Equal(Marks.Zone.Description, zone.Law);
        // before the worker answers, the zone and use are typed (never an empty dropdown)
        var none = SetupScreen.Build(Model(), Sides, null).Fields;
        Assert.Equal(FieldKind.Text, none.Single(f => f.Mark == Marks.Zone).Kind);
        // a zone typed that isn't a district Gordium has rules for: a problem, so needed
        var odd = Screen(Model(new() { [Marks.Zone.Guid] = new(true, Text: "B-1a") }));
        Assert.Contains("isn't a district", odd.Fields.Single(f => f.Mark == Marks.Zone).Problem);
        Assert.Contains(Marks.Zone.Name, odd.Needed);
    }

    /// <summary>A Save writes only what the architect chose, and only where it differs from what the mark holds: a
    /// field never touched is never written (a blank stays blank), a value not allowed is refused and not written.</summary>
    [Fact]
    public void A_save_writes_only_the_choices_and_a_blank_stays_blank()
    {
        var draft = new SetupDraft();
        var screen = Screen(Model(), draft);
        Assert.Empty(draft.Writes(screen.Fields).Writes);              // nothing chosen: nothing written
        draft.Choose(Marks.Zone, "R-1b");
        draft.Choose(Marks.LotSurveyed, "No");
        draft.Choose(Marks.Stories, "0");                              // under 1: refused
        draft.Choose(Marks.GroundFrom, "Toposolid");                   // not a choice: refused
        screen = Screen(Model(), draft);
        var (writes, problems) = draft.Writes(screen.Fields);
        Assert.Equal([Marks.Zone, Marks.LotSurveyed], writes.Select(w => w.Mark));
        Assert.All(writes, w => Assert.Equal(SetupFacts.ProjectInformation, w.Element));
        Assert.Equal(new MarkValue(true, Text: "R-1b"), writes[0].Value);
        Assert.Equal(new MarkValue(true, 0), writes[1].Value);          // No is 0, chosen; never a default
        Assert.Equal(2, problems.Count);
        // every other field (the corner lot, the use, every has-none tick) not touched: not written
        Assert.DoesNotContain(writes, w => w.Mark == Marks.CornerLot || w.Mark == Marks.Use || w.Mark == Marks.NoStairs);
        // the same value as the mark holds: nothing to write
        var held = new SetupDraft();
        held.Choose(Marks.Zone, "R-1b");
        Assert.Empty(held.Writes(Screen(Model(AllStated()), held).Fields).Writes);
    }

    /// <summary>Pick on plan writes nothing: the edge picked is a choice in the draft, "not saved yet", and Save writes
    /// it with the other facts in the same batch (one "Gordium: project facts" transaction, one Ctrl+Z), as the text
    /// Gordium's pick writes (StreetEdges.Keep's); typed text that isn't an edge Gordium wrote is never written.</summary>
    [Fact]
    public void Pick_on_plan_writes_nothing_until_save_and_save_writes_the_edge_with_the_other_facts()
    {
        var project = new Dictionary<Guid, MarkValue>();
        var model = Model(project);
        var draft = new SetupDraft();
        draft.Choose(Marks.Zone, "R-1b");
        var edge = new PickedEdge(new Xyz(0, 0, 0), new Xyz(60, 0, 0), true, 60, new Xyz(30, 0, 0));
        var text = draft.Pick([edge]);
        Assert.Empty(project);                                          // picked: nothing in the model
        var screen = Screen(model, draft);
        var street = screen.Fields.Single(f => f.Mark == Marks.StreetEdge);
        Assert.Null(street.Current);
        Assert.Contains(Marks.StreetEdge.Name, screen.Needed);          // not saved: still needed, the check doesn't run
        var kept = "";
        StreetEdges.Keep([edge], t => { kept = t; return true; }, new Dictionary<string, object?>());
        Assert.Equal(kept, text);
        var (writes, problems) = draft.Writes(screen.Fields);
        Assert.Empty(problems);
        Assert.Equal([Marks.Zone, Marks.StreetEdge], writes.Select(w => w.Mark));        // one Save, one batch
        Assert.Equal(new MarkValue(true, Text: kept), writes[1].Value);
        Assert.Equal(SetupFacts.ProjectInformation, writes[1].Element);
        Assert.Null(draft.Pick([]));                                    // nothing picked: the choice stays as it was
        Assert.Equal(kept, draft.Chosen(Marks.StreetEdge));
        var typed = new SetupDraft();
        typed.Choose(Marks.StreetEdge, "the front");
        Assert.Empty(typed.Writes(screen.Fields).Writes);
        // the Revit side: the form's pick keeps the edges in the draft and writes nothing itself
        var flow = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupFlow.cs"));
        var pick = flow[flow.IndexOf("private static void PickStreet()", StringComparison.Ordinal)..];
        pick = pick[..pick.IndexOf("\n    }", StringComparison.Ordinal)];
        Assert.Contains("CheckProjectCommand.PickEdges(uidoc, log)", pick, StringComparison.Ordinal);
        Assert.Contains("Draft.Pick(kept)", pick, StringComparison.Ordinal);
        Assert.DoesNotContain("PickStreet(uidoc", pick, StringComparison.Ordinal);
        Assert.DoesNotContain("Transaction", pick, StringComparison.Ordinal);
        Assert.DoesNotContain("Write(", pick, StringComparison.Ordinal);
    }

    // ---- the checklist and its suggestions ----------------------------------------------------------------------

    private static ChecklistLine Line(SetupScreen s, string key) => s.Lines.Single(l => l.Key == key);

    /// <summary>A line per fact with its counts, not a line per element; the unset ones selectable together.</summary>
    [Fact]
    public void The_checklist_is_one_line_per_fact_with_counts()
    {
        var s = Screen(Model());
        Assert.Equal("Sleeping room: 1 of 4 rooms set", Line(s, "sleeping_room").Count);
        Assert.Equal("Escape opening: 0 of 8 windows and doors set", Line(s, "escape_opening").Count);
        Assert.Equal(3, Line(s, "exit_door").Unset.Count);
        var op = Line(s, "operation");
        Assert.True(op.PerType);
        Assert.Equal(6, op.Total);                                     // per type: 4 window types, 2 door types
        Assert.Equal(8, op.Unset.Count);                               // every element of those types, to select
        Assert.All(s.Lines.Where(l => l.Key is "sleeping_room" or "escape_opening" or "exit_door"), l => Assert.True(l.Needed));
        Assert.All(s.Lines, l => Assert.False(string.IsNullOrWhiteSpace(l.WhyAsked)));
        Assert.Contains("Revit stores the frame size", Line(s, "clear_opening").WhyAsked);
    }

    /// <summary>A sleeping room is suggested from its name only ("Bedroom", "BR"), never from its area, and never as
    /// No (a suggested No could hide a bedroom).</summary>
    [Fact]
    public void Sleeping_rooms_are_suggested_from_their_names_only_and_never_as_no()
    {
        var sleep = Line(Screen(Model()), "sleeping_room").Suggestions;
        Assert.Equal(["bed1", "bed2"], sleep.Select(x => x.Element));
        Assert.All(sleep, x => Assert.Equal("Yes", x.Words));
        Assert.Equal("named \"Bedroom 1\"", sleep[0].Basis);
        Assert.DoesNotContain(sleep, x => x.Element == "hall");
    }

    /// <summary>In a sleeping room (marked or suggested), the largest operable window is suggested as its escape opening,
    /// saying so; its other windows No; a window in a room marked not sleeping No; a window in a room not known, none.</summary>
    [Fact]
    public void The_largest_operable_window_of_a_sleeping_room_is_suggested_saying_so()
    {
        var escape = Line(Screen(Model()), "escape_opening").Suggestions.ToDictionary(x => x.Element);
        Assert.Equal("Yes", escape["w1"].Words);                        // 3 x 5 casement: larger than w3; w2 is fixed
        Assert.Contains("the largest operable window of Bedroom 1 (bed1)", escape["w1"].Basis);
        Assert.Contains("only suggested as a sleeping room", escape["w1"].Basis);
        Assert.Equal("No", escape["w2"].Words);
        Assert.Equal("No", escape["w3"].Words);
        Assert.Equal("No", escape["w4"].Words);                         // Living: marked not a sleeping room
        Assert.Contains("marked not a sleeping room", escape["w4"].Basis);
        Assert.False(escape.ContainsKey("w5"));                         // Hall: not marked either way
        Assert.False(escape.ContainsKey("bed1door"));                   // opens to a sleeping room: the architect's
    }

    /// <summary>A door to the outside on the entry level (the lowest with one) is suggested as the exit door; a door
    /// between two rooms No; a door to the outside on another level, none.</summary>
    [Fact]
    public void An_outside_door_on_the_entry_level_is_suggested_as_the_exit_door()
    {
        var exit = Line(Screen(Model()), "exit_door").Suggestions.ToDictionary(x => x.Element);
        Assert.Equal("Yes", exit["front"].Words);
        Assert.Contains("taken as the entry level", exit["front"].Basis);
        Assert.Equal("No", exit["bed1door"].Words);
        Assert.False(exit.ContainsKey("upper"));
    }

    /// <summary>A type's operation is suggested from its family and type name, once per type; a type already set isn't.</summary>
    [Fact]
    public void An_operation_is_suggested_per_type_from_its_name()
    {
        var model = Model(null, [.. House.Where(e => e.UniqueId is not ("w4" or "w5")),
                                 Window("w4", "36 x 48", "Double Hung", 3, 4, operation: "Double hung"),
                                 Window("w5", "36 x 48", "Double Hung", 3, 4, operation: "Double hung")]);
        var op = Line(Screen(model), "operation").Suggestions.ToDictionary(x => x.Label, x => x);
        Assert.Equal("Casement", op["Casement: 36 x 60"].Words);
        Assert.True(op["Casement: 36 x 60"].OnType);
        Assert.Equal("Fixed", op["Fixed: 48 x 60"].Words);
        Assert.Equal("Side-hinged door", op["Single-Flush: 36\" x 80\""].Words);
        Assert.False(op.ContainsKey("Double Hung: 36 x 48"));         // set (w4 and w5 share the type)
        Assert.Null(SetupChecklist.OperationFromName("Window", "W-1", door: false));   // nothing said: nothing suggested
    }

    /// <summary>A suggestion is data: building the form writes nothing, a Save never carries one, and accepting one
    /// writes exactly that one.</summary>
    [Fact]
    public void A_suggestion_is_never_written_by_itself()
    {
        var draft = new SetupDraft();
        var s = Screen(Model(), draft);
        Assert.NotEmpty(s.Lines.SelectMany(l => l.Suggestions));
        Assert.Empty(draft.Writes(s.Fields).Writes);
        var one = Line(s, "sleeping_room").Suggestions[0];
        Assert.Equal([new MarkWrite("bed1", false, Marks.SleepingRoom, new MarkValue(true, 1), "Bedroom 1 (bed1)")], SetupWrites.Accept([one]));
    }

    // ---- when the form shows, and when the check runs by itself --------------------------------------------------

    [Fact]
    public void The_form_shows_while_a_needed_fact_is_missing_and_the_check_runs_once_none_is()
    {
        var s = Screen(Model());
        Assert.Equal([Marks.Zone.Name, Marks.Use.Name, Marks.LotSurveyed.Name, Marks.StreetEdge.Name, "sleeping_room", "escape_opening", "exit_door"], s.Needed);
        Assert.True(SetupGate.ShowSetup(s.Needed, null));
        Assert.False(SetupGate.RunsByItself(s, s));
        // everything needed set: the form doesn't show, the check runs
        var marked = House.Select(e => e with
        {
            Instance = new Dictionary<Guid, MarkValue>(e.Instance.Select(p => KeyValuePair.Create(p.Key, YesNo(false)))),
        }).ToArray();
        var ready = Screen(Model(AllStated(), marked));
        Assert.Empty(ready.Needed);
        Assert.True(SetupGate.RunsByItself(s, ready));                 // the form was waiting: the check runs
        Assert.False(SetupGate.RunsByItself(ready, ready));            // nothing was waiting (Mark facts, all set): an edit runs nothing
        Assert.False(SetupGate.ShowSetup(ready.Needed, null));
        // an optional fact (the operations, the corner lot) never holds the check back
        Assert.False(Line(ready, "operation").Done);
    }

    /// <summary>Check now anyway, remembered for exactly the facts missing then: the form isn't shown again for them,
    /// and is for a fact newly missing.</summary>
    [Fact]
    public void Check_now_anyway_is_remembered_for_the_same_facts_only()
    {
        var anyway = new HashSet<string> { Marks.Use.Name, "escape_opening" };
        Assert.False(SetupGate.ShowSetup([Marks.Use.Name], anyway));
        Assert.False(SetupGate.ShowSetup([Marks.Use.Name, "escape_opening"], anyway));
        Assert.True(SetupGate.ShowSetup([Marks.Use.Name, Marks.Zone.Name], anyway));
        Assert.False(SetupGate.ShowSetup([], null));
    }

    /// <summary>A Save or an accept is a change to the model: results shown go stale after either (never one of the
    /// check's own transactions).</summary>
    [Theory]
    [InlineData(SetupWrites.FactsTransaction)]
    [InlineData(SetupWrites.SuggestionsTransaction)]
    public void A_write_makes_the_results_stale(string transaction) =>
        Assert.True(ResultRows.ChangesTheCheck([transaction], committed: true));

    /// <summary>One Save is one batch of writes (the Revit layer writes a batch as one transaction, so one Ctrl+Z):
    /// applied to a stand-in for Revit's undo, undoing it gives back every value it changed, a blank one blank.</summary>
    [Fact]
    public void One_save_is_one_undo_step_that_restores_every_value()
    {
        var project = new Dictionary<Guid, MarkValue> { [Marks.Zone.Guid] = new(true, Text: "R-1a") };
        var draft = new SetupDraft();
        draft.Choose(Marks.Zone, "R-1b");
        draft.Choose(Marks.Use, "one_family_detached");
        draft.Choose(Marks.CornerLot, "Yes");
        var (writes, _) = draft.Writes(Screen(Model(project), draft).Fields);
        var undo = new UndoStack(project);
        undo.Transaction(SetupWrites.FactsTransaction, writes);
        Assert.Equal("R-1b", project[Marks.Zone.Guid].Text);
        Assert.Equal(1, project[Marks.CornerLot.Guid].Integer);
        Assert.Equal(1, undo.Count);                                    // one Save, one step
        undo.Undo();
        Assert.Equal("R-1a", project[Marks.Zone.Guid].Text);
        Assert.False(project.ContainsKey(Marks.Use.Guid));              // blank before: blank again
        Assert.False(project.ContainsKey(Marks.CornerLot.Guid));
        Assert.DoesNotContain(Screen(Model(project)).Fields, f => f.Mark == Marks.CornerLot && f.Current is not null);
    }

    /// <summary>A stand-in for Revit's undo: each transaction keeps what it overwrote; Undo puts it back.</summary>
    private sealed class UndoStack(Dictionary<Guid, MarkValue> marks)
    {
        private readonly Stack<List<(Guid Guid, MarkValue? Was)>> _steps = new();

        public int Count => _steps.Count;

        public void Transaction(string name, IReadOnlyList<MarkWrite> writes)
        {
            Assert.False(string.IsNullOrEmpty(name));
            _steps.Push(writes.Select(w => (w.Mark.Guid, marks.TryGetValue(w.Mark.Guid, out var v) ? v : (MarkValue?)null)).ToList());
            foreach (var w in writes)
                marks[w.Mark.Guid] = w.Value;
        }

        public void Undo()
        {
            foreach (var (guid, was) in _steps.Pop())
                if (was is null)
                    marks.Remove(guid);
                else
                    marks[guid] = was;
        }
    }

    // ---- words by building type ---------------------------------------------------------------------------------

    /// <summary>"house" only for a one- or two-family dwelling: a day care, or a use not stated, is "building".</summary>
    [Fact]
    public void The_words_follow_the_building_type()
    {
        Assert.Equal("house", SetupWords.Noun("one_family_detached"));
        Assert.Equal("house", SetupWords.Noun("two_family_semi_detached"));
        Assert.Equal("building", SetupWords.Noun("day_care"));
        Assert.Equal("building", SetupWords.Noun(null));
        Assert.Equal("This building has no stairs", SetupWords.Label(Marks.NoStairs, "building"));
        Assert.Equal("This house has no stairs", SetupWords.Label(Marks.NoStairs, "house"));
        var care = Screen(Model(new() { [Marks.Use.Guid] = new(true, Text: "day_care") }));
        Assert.Equal("building", care.Noun);
        // never the building called a house; a term of the law that holds the letters (a townhouse unit, the
        // household) is no such word (merged with the code decision's marks, 2026-11-22)
        var house = new System.Text.RegularExpressions.Regex(@"\bhouses?\b", System.Text.RegularExpressions.RegexOptions.IgnoreCase);
        Assert.DoesNotContain(care.Fields, f => house.IsMatch(f.Label) || house.IsMatch(f.Law));
        Assert.Contains(care.Fields, f => f.Label == "This building has no stairs");
        // a building that isn't a house gets the escape-route lines
        Assert.Contains(care.Lines, l => l.Key == "room_use");
        Assert.DoesNotContain(Screen(Model(new() { [Marks.Use.Guid] = new(true, Text: "one_family_detached") })).Lines, l => l.Key == "room_use");
    }

    // ---- review round 1 -------------------------------------------------------------------------------------------

    /// <summary>R1 #1: after Check now anyway, a later Check with the same facts missing is sent anyway (as Check now
    /// anyway sends), never skipped with nothing sent; a fact newly missing shows the form; nothing missing sends.</summary>
    [Fact]
    public void A_later_check_with_the_same_facts_missing_is_sent_anyway()
    {
        var anyway = new HashSet<string> { Marks.Use.Name };
        Assert.Equal(SetupStep.SendAnyway, SetupGate.Decide([Marks.Use.Name], anyway));
        Assert.Equal(SetupStep.Show, SetupGate.Decide([Marks.Use.Name, Marks.Zone.Name], anyway));
        Assert.Equal(SetupStep.Show, SetupGate.Decide([Marks.Use.Name], null));
        Assert.Equal(SetupStep.Send, SetupGate.Decide([], anyway));
        // the add-in sends it as anyway: no street pick, read with anyway, the results' "Checked without"
        var check = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "CheckProject.cs"));
        Assert.Contains("var anyway = step == SetupStep.SendAnyway;", check, StringComparison.Ordinal);
        Assert.Contains("var ask = anyway ? StreetAsk.NotNeeded :", check, StringComparison.Ordinal);
        Assert.Contains("ReadModel(doc, ui.Application, log, check.Worker, anyway);", check, StringComparison.Ordinal);
    }

    /// <summary>R1 #2: a city use the district's chart doesn't list (a day care in R-1b) is the architect's to state:
    /// kept, labelled not listed, no problem, not needed; only a word that isn't a city use at all is a problem.</summary>
    [Fact]
    public void A_city_use_the_district_doesnt_list_can_be_stated()
    {
        var s = Screen(Model(new() { [Marks.Zone.Guid] = new(true, Text: "R-1b"), [Marks.Use.Guid] = new(true, Text: "day_care") }));
        var use = s.Fields.Single(f => f.Mark == Marks.Use);
        Assert.Null(use.Problem);
        Assert.True(use.IsSet);
        Assert.DoesNotContain(Marks.Use.Name, s.Needed);
        Assert.Contains("not on R-1b's list of uses", use.CurrentLabel, StringComparison.Ordinal);
        var odd = Screen(Model(new() { [Marks.Use.Guid] = new(true, Text: "casino") })).Fields.Single(f => f.Mark == Marks.Use);
        Assert.Contains("isn't one of the City's uses", odd.Problem, StringComparison.Ordinal);
    }

    /// <summary>R1 #3: a window the architect marked No is never the one suggested; the next largest operable is.</summary>
    [Fact]
    public void A_window_marked_no_is_never_the_suggested_escape_opening()
    {
        var model = Model(null, [.. House.Where(e => e.UniqueId != "w1"), Window("w1", "36 x 60", "Casement", 3, 5, escape: false)]);
        var escape = Line(Screen(model), "escape_opening").Suggestions.ToDictionary(x => x.Element);
        Assert.False(escape.ContainsKey("w1"));
        Assert.Equal("Yes", escape["w3"].Words);
        Assert.DoesNotContain(escape.Values, x => x.Basis.Contains("as Window w1", StringComparison.Ordinal));
    }

    /// <summary>R1 #4: the check that runs by itself checks the form's own project, never the active one.</summary>
    [Fact]
    public void The_check_that_runs_by_itself_is_the_forms_project()
    {
        var flow = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupFlow.cs"));
        var refreshed = flow[flow.IndexOf("private static void Refreshed(", StringComparison.Ordinal)..];
        refreshed = refreshed[..refreshed.IndexOf("\n    }", StringComparison.Ordinal)];
        Assert.Contains("CheckRun.Start(ui, doc)", refreshed, StringComparison.Ordinal);
        Assert.DoesNotContain("CheckProjectCommand.Check(ui)", refreshed, StringComparison.Ordinal);
    }

    /// <summary>R1 #5: the form's "Nothing was checked" is in plain words from what is missing: never Gordium's stored
    /// words or "when Check project asks".</summary>
    [Fact]
    public void Nothing_sent_is_said_in_plain_words()
    {
        var words = SetupWords.NothingSent(StreetRefusal.None, [Marks.Zone, Marks.Use, Marks.StreetEdge], "building");
        Assert.StartsWith("Nothing was checked: the zone chooses the rules", words, StringComparison.Ordinal);
        Assert.Contains("use, street edge", words, StringComparison.Ordinal);
        Assert.DoesNotContain("one_family_detached", words, StringComparison.Ordinal);
        Assert.DoesNotContain("Check project asks", words, StringComparison.Ordinal);
        Assert.Contains("Pick it again on the plan", SetupWords.NothingSent(StreetRefusal.NoLongerAnEdge, [], "house"), StringComparison.Ordinal);
        var check = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "CheckProject.cs"));
        Assert.Contains("notice: clear + SetupWords.NothingSent(prepared.StreetRefused, notSet,", check, StringComparison.Ordinal);
        Assert.DoesNotContain("notice: clear + \"Nothing was checked: \" + string.Join", check, StringComparison.Ordinal);
    }

    /// <summary>R1 #6: a zone or use typed in another case isn't set (the checker reads it exactly): a problem, needed,
    /// and choosing the list's word writes it over.</summary>
    [Fact]
    public void A_word_typed_in_another_case_is_a_problem_and_a_save_writes_it_over()
    {
        var project = new Dictionary<Guid, MarkValue> { [Marks.Zone.Guid] = new(true, Text: "r-1b"), [Marks.Use.Guid] = new(true, Text: "One_Family_Detached") };
        var s = Screen(Model(project));
        var use = s.Fields.Single(f => f.Mark == Marks.Use);
        Assert.Contains("another case", use.Problem, StringComparison.Ordinal);
        Assert.Contains(Marks.Use.Name, s.Needed);
        Assert.Contains(Marks.Zone.Name, s.Needed);
        var draft = new SetupDraft();
        draft.Choose(Marks.Zone, "R-1b");
        draft.Choose(Marks.Use, "one_family_detached");
        var (writes, _) = draft.Writes(Screen(Model(project), draft).Fields);
        Assert.Equal([new MarkValue(true, Text: "R-1b"), new MarkValue(true, Text: "one_family_detached")], writes.Select(w => w.Value));
    }

    /// <summary>R1 #7: a box typed in counts at once, with no redraw (so the click on Save right after isn't lost to a
    /// redraw), and a typed count is in the Save's writes.</summary>
    [Fact]
    public void A_typed_value_counts_without_leaving_the_box()
    {
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupView.cs"));
        Assert.Contains("text.TextChanged += (_, _) =>\n                {\n                    _do.Type(f.Mark, text.Text);\n                    SaveWords();", view, StringComparison.Ordinal);
        Assert.DoesNotContain("LostKeyboardFocus", view, StringComparison.Ordinal);
        var flow = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupFlow.cs"));
        var type = flow[flow.IndexOf("Type: (mark, value) =>", StringComparison.Ordinal)..];
        type = type[..type.IndexOf("},", StringComparison.Ordinal)];
        Assert.DoesNotContain("Redraw", type, StringComparison.Ordinal);
        var draft = new SetupDraft();
        draft.Choose(Marks.Stories, "3");
        Assert.Equal([new MarkValue(true, 3)], draft.Writes(Screen(Model(), draft).Fields).Writes.Select(w => w.Value));
    }

    // ---- review round 2 -------------------------------------------------------------------------------------------

    /// <summary>R2 #1: the form calls a fact set exactly when the check reads it: the ground's words in any case (as
    /// ProjectFacts.Read sends grade_from), the zone and use word for word.</summary>
    [Fact]
    public void The_form_and_the_check_read_each_word_alike()
    {
        var project = new Dictionary<Guid, MarkValue>(AllStated()) { [Marks.GroundFrom.Guid] = new(true, Text: "spot grades") };
        var model = Model(project);
        var s = Screen(model);
        var ground = s.Fields.Single(f => f.Mark == Marks.GroundFrom);
        Assert.Null(ground.Problem);
        // R3: shown as the choice it is read as (the form shows it selected), never blank
        Assert.Equal("Spot grades", ground.CurrentLabel);
        Assert.Equal("Spot grades", ground.CurrentChoice?.Value);
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupView.cs"));
        Assert.Contains("var shown = chosen ?? f.CurrentChoice?.Value ?? f.Current;", view, StringComparison.Ordinal);
        // a zone in another case: not shown as selected (its problem says why)
        Assert.Null(Screen(Model(new(AllStated()) { [Marks.Zone.Guid] = new(true, Text: "r-1b") })).Fields.Single(f => f.Mark == Marks.Zone).CurrentChoice);
        Assert.DoesNotContain(Marks.GroundFrom.Name, s.Needed);
        var read = ProjectFacts.Read(model);
        Assert.Equal("spot", read.Facts["grade_from"]!.GetValue<string>());
        Assert.DoesNotContain(read.Missing, w => w.StartsWith(Marks.GroundFrom.Name, StringComparison.Ordinal));
        // a word the check doesn't read: a problem in the form and missing in the check, both
        project[Marks.GroundFrom.Guid] = new(true, Text: "Toposolid");
        Assert.NotNull(Screen(Model(project)).Fields.Single(f => f.Mark == Marks.GroundFrom).Problem);
        Assert.Contains(ProjectFacts.Read(Model(project)).Missing, w => w.StartsWith(Marks.GroundFrom.Name, StringComparison.Ordinal));
        Assert.Equal([Marks.Zone, Marks.Use], SetupFacts.ReadExactly);
    }

    /// <summary>R2 #3: Check project knows the place's districts and uses before its gate decides, whatever the form
    /// was opened before (a stated zone or use is always checked against them).</summary>
    [Fact]
    public void The_gate_decides_with_the_places_options()
    {
        var check = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "CheckProject.cs"));
        var options = check.IndexOf("SetupRun.Options(check.Worker, log);", StringComparison.Ordinal);
        Assert.True(options > 0 && options < check.IndexOf("SetupRun.Needs(doc)", StringComparison.Ordinal));
        var flow = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupFlow.cs"));
        Assert.Contains("if (asked.Wait(OptionsWait))\n                _options = asked.Result;", flow, StringComparison.Ordinal);
        // with the options known, a zone in another case is caught by the gate
        var s = Screen(Model(new(AllStated()) { [Marks.Zone.Guid] = new(true, Text: "r-1b") }));
        Assert.Contains(Marks.Zone.Name, s.Needed);
    }

    /// <summary>R1 #8: a stories count under 1 left out says so, never "not one of Gordium's words".</summary>
    [Fact]
    public void A_stories_count_under_one_left_out_says_so()
    {
        var words = SetupWords.SentWithout(Marks.Stories, "house");
        Assert.DoesNotContain("words", words, StringComparison.Ordinal);
        Assert.Contains("1 or more", words, StringComparison.Ordinal);
    }

    /// <summary>What a fact left out of a check sent anyway does, in words: never a pass.</summary>
    [Fact]
    public void A_fact_left_out_says_its_rules_need_review()
    {
        Assert.Contains("needs review", SetupWords.SentWithout(Marks.Use, "house"));
        Assert.Contains("tax map", SetupWords.SentWithout(Marks.LotSurveyed, "house"));
        Assert.Contains("need review", SetupWords.SentWithout(Marks.StreetEdge, "house"));
    }
}
