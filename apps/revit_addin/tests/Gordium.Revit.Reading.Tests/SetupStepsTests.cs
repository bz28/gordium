using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The Setup form as numbered steps (UI polish changes 1 to 11; Ben approved 2026-11-23), Revit-free: only the
/// things a check needs are steps, numbered; the occupancy group and the sprinkler system are required exactly where
/// the Building Code governs (Ben's call), from the checker's own list of such uses, never a guess; a group is only
/// ever suggested, never chosen or written by itself; the street edge said by its side and length, never by
/// coordinates; and the pick ends exactly when the architect says so (the silent wait for Esc after Yes is gone).
/// Each test fails when its change is taken out.</summary>
public sealed class SetupStepsTests
{
    private static MarkValue YesNo(bool? v) => v is { } b ? new(true, b ? 1 : 0) : new(false, 0);

    private static readonly MarkedElement[] Building =
    [
        new() { UniqueId = "r1", BuiltInCategory = Marks.Rooms, Name = "Bedroom", Number = "1", Placement = RoomPlacement.Placed,
                Instance = new Dictionary<Guid, MarkValue> { [Marks.SleepingRoom.Guid] = YesNo(true) } },
        new() { UniqueId = "w1", BuiltInCategory = Marks.Windows, Name = "36 x 60", Family = "Casement", TypeUniqueId = "tw",
                Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = YesNo(null) } },
        new() { UniqueId = "d1", BuiltInCategory = Marks.Doors, Name = "36 x 80", Family = "Single-Flush", TypeUniqueId = "td",
                Instance = new Dictionary<Guid, MarkValue> { [Marks.EscapeOpening.Guid] = YesNo(false), [Marks.ExitDoor.Guid] = YesNo(null) } },
    ];

    private static RevitModel Model(Dictionary<Guid, MarkValue>? project = null) =>
        new() { Document = "x.rvt", Marked = Building, ProjectMarks = project ?? [] };

    /// <summary>The checker's options for Ithaca as the worker answers them (building_code_uses from check.options:
    /// multiple family is one, a one-family house isn't).</summary>
    private static readonly PlaceOptions Options = new(
        ["R-1b", "R-3a"],
        [("one_family_detached", "One-family dwelling, detached"), ("multiple_family", "Multiple family dwelling"), ("dormitory", "Dormitory")],
        new Dictionary<string, IReadOnlyList<UseChoice>>())
    {
        BuildingCodeUses = ["multiple_family", "dormitory"],
    };

    private static SetupScreen Screen(Dictionary<Guid, MarkValue>? project = null, SetupDraft? draft = null, PlaceOptions? options = null) =>
        SetupScreen.Build(Model(project), [], options ?? Options, draft);

    private static SetupDraft Use(string use)
    {
        var d = new SetupDraft();
        d.Choose(Marks.Use, use);
        return d;
    }

    // ---- change 1: only the things the check needs, numbered --------------------------------------------------------

    /// <summary>The steps are the lot's four facts, then the facts inside the building still to mark; a line already
    /// set is no step (said once), and no optional fact is a step.</summary>
    [Fact]
    public void The_steps_are_what_the_check_needs_in_order()
    {
        var s = Screen();
        Assert.Equal(["Zoning district", "Use", "Property line drawn from", "Street edge", "Escape openings", "Exit doors"], s.Steps.Select(x => x.Title));
        Assert.Equal([SetupSteps.Lot, SetupSteps.Lot, SetupSteps.Lot, SetupSteps.Lot, SetupSteps.InModel, SetupSteps.InModel], s.Steps.Select(x => x.Section));
        Assert.DoesNotContain(s.Steps, x => x.Key == "sleeping_room");                    // set in the model: no step
        Assert.Equal(["sleeping_room"], SetupSteps.AlreadySet(s).Select(l => l.Key));
        Assert.All(s.Steps.Where(x => x.Field is not null), x => Assert.True(x.Field!.Required));
        Assert.All(SetupSteps.MoreFields(s), f => Assert.False(f.Required));
        Assert.Equal("Set 6 things to check this project", s.Headline);
        Assert.Equal("0 of 6 set", SetupSteps.Progress(s.Steps));
        // every step is something SetupGate waits for: the steps and the gate never disagree
        Assert.True(s.Steps.Select(x => x.Key).ToHashSet().SetEquals(s.Needed));
    }

    /// <summary>A step is set when the model holds a usable value, or the draft chooses one Save would write; a
    /// choice Save would refuse (a zone not on the list) never ticks it.</summary>
    [Fact]
    public void A_step_is_set_only_by_a_value_Save_would_write()
    {
        var draft = new SetupDraft();
        draft.Choose(Marks.Zone, "R-3a");
        draft.Choose(Marks.LotSurveyed, "No");
        var s = Screen(draft: draft);
        Assert.True(s.Steps.Single(x => x.Field?.Mark == Marks.Zone).Done);
        Assert.True(s.Steps.Single(x => x.Field?.Mark == Marks.LotSurveyed).Done);
        Assert.Equal("2 of 6 set", SetupSteps.Progress(s.Steps));
        var bad = new SetupDraft();
        bad.Choose(Marks.Zone, "Z-9");
        Assert.False(Screen(draft: bad).Steps.Single(x => x.Field?.Mark == Marks.Zone).Done);
        // the model holds it: set; emptied in the draft: what the model holds stands
        var held = Screen(new Dictionary<Guid, MarkValue> { [Marks.Zone.Guid] = new(true, Text: "R-1b") });
        Assert.True(held.Steps.Single(x => x.Field?.Mark == Marks.Zone).Done);
    }

    // ---- Ben's call: occupancy group and sprinkler system required where the Building Code governs ------------------

    /// <summary>Where the use is one the checker says the Building Code covers (options.building_code_uses), the two
    /// facts are required steps under "The building", the gate waits for them, and the footer names them; a house
    /// use asks neither (never required on a building the Residential Code may cover).</summary>
    [Fact]
    public void Occupancy_group_and_sprinkler_system_are_required_where_the_building_code_governs()
    {
        var apartment = Screen(draft: Use("multiple_family"));
        Assert.True(apartment.BuildingCode);
        var building = apartment.Steps.Where(x => x.Section == SetupSteps.Building).Select(x => x.Field!.Mark).ToList();
        Assert.Equal([Marks.OccupancyGroups, Marks.SprinklerSystem], building);
        Assert.Contains(Marks.OccupancyGroups.Name, apartment.Needed);
        Assert.Contains(Marks.SprinklerSystem.Name, apartment.Needed);
        Assert.Equal(SetupStep.Show, SetupGate.Decide(apartment.Needed, null));
        Assert.DoesNotContain(SetupSteps.MoreFields(apartment), f => f.Mark == Marks.OccupancyGroups || f.Mark == Marks.SprinklerSystem);
        var house = Screen(draft: Use("one_family_detached"));
        Assert.False(house.BuildingCode);
        Assert.DoesNotContain(house.Steps, x => x.Section == SetupSteps.Building);
        Assert.DoesNotContain(Marks.OccupancyGroups.Name, house.Needed);
        Assert.Contains(SetupSteps.MoreFields(house), f => f.Mark == Marks.OccupancyGroups);   // still there, optional
        // no options yet (the worker hasn't answered): never required by a guess
        Assert.False(SetupScreen.Build(Model(), [], null, Use("multiple_family")).BuildingCode);
    }

    /// <summary>The other way the form knows the Building Code governs: the architect applies it (Follows building
    /// code, R101.2's exception). Rounds 3 and 4: never an earlier check's verdict (any fact it read may have changed
    /// since), so a house with four stories is asked for the two facts by its results, never required here.</summary>
    [Theory]
    [InlineData("one_family_detached", true, true)]
    [InlineData("one_family_detached", false, false)]
    [InlineData("one_family_detached", null, false)]
    [InlineData(null, null, false)]
    [InlineData("multiple_family", null, true)]
    [InlineData("multiple_family", false, true)]
    public void The_building_code_governs_by_the_use_or_the_exception(string? use, bool? follows, bool governs) =>
        Assert.Equal(governs, SetupSteps.BuildingCodeGoverns(use, follows, Options));

    /// <summary>Round 4: the form decides only from what the project holds now. A screen's Build takes no earlier
    /// check's code at all (the gate can't be held up by a verdict a corrected fact no longer supports), and a house
    /// whose stories make it the Building Code's is not asked for the two facts here.</summary>
    [Fact]
    public void No_earlier_verdict_requires_the_building_code_facts()
    {
        Assert.DoesNotContain(typeof(SetupScreen).GetMethod(nameof(SetupScreen.Build))!.GetParameters(),
                              p => p.Name!.Contains("last", StringComparison.OrdinalIgnoreCase) || p.Name!.Contains("code", StringComparison.OrdinalIgnoreCase));
        var four = Screen(new Dictionary<Guid, MarkValue> { [Marks.StoriesAboveGradePlane.Guid] = new(true, 4) }, Use("one_family_detached"));
        Assert.False(four.BuildingCode);
        Assert.Null(SetupSteps.BuildingNote(four));
        Assert.DoesNotContain(Marks.OccupancyGroups.Name, four.Needed);
        var pane = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsPane.cs"));
        Assert.DoesNotContain("LastCode", pane, StringComparison.Ordinal);
    }

    /// <summary>The two facts take the book's own words: the groups of BCNYS Chapter 3 and the sprinkler systems,
    /// each as a choice; a building of two groups typed on Project Information ("R-2, B") is one choice, set.</summary>
    [Fact]
    public void The_building_code_facts_offer_the_book_s_words()
    {
        var s = Screen(draft: Use("multiple_family"));
        var group = s.Fields.Single(f => f.Mark == Marks.OccupancyGroups);
        Assert.Equal(FieldKind.Choice, group.Kind);
        Assert.Equal(OccupancyGroupWords.Words, group.Choices.Select(c => c.Value));
        Assert.Equal(SprinklerWords.Table.Words, s.Fields.Single(f => f.Mark == Marks.SprinklerSystem).Choices.Select(c => c.Value));
        var two = Screen(new Dictionary<Guid, MarkValue> { [Marks.OccupancyGroups.Guid] = new(true, Text: "R-2, B") }, Use("multiple_family"));
        var f2 = two.Fields.Single(f => f.Mark == Marks.OccupancyGroups);
        Assert.True(f2.IsSet);
        Assert.Null(f2.Problem);
        Assert.True(two.Steps.Single(x => x.Field?.Mark == Marks.OccupancyGroups).Done);
        var wrong = Screen(new Dictionary<Guid, MarkValue> { [Marks.OccupancyGroups.Guid] = new(true, Text: "R-2, office") }, Use("multiple_family"));
        Assert.NotNull(wrong.Fields.Single(f => f.Mark == Marks.OccupancyGroups).Problem);
    }

    // ---- Ben's call: a suggested group from the use, applied only on Accept --------------------------------------

    /// <summary>A multiple-family building is offered R-2 with the code's own words; nothing is chosen or written by
    /// it (the field stays blank, the step unset, Save writes nothing for it) until the architect's Accept chooses
    /// it in the draft; a use the book lists under two groups, or none, is offered nothing.</summary>
    [Fact]
    public void A_group_is_only_ever_a_suggestion_until_accepted()
    {
        var g = GroupSuggestion.For("multiple_family");
        Assert.NotNull(g);
        Assert.Equal("R-2", g!.Group);
        Assert.Contains("BCNYS 310.3", g.Basis, StringComparison.Ordinal);
        Assert.Contains("Apartment houses", g.Basis, StringComparison.Ordinal);
        Assert.Contains(g.Group, OccupancyGroupWords.Words);
        Assert.Null(GroupSuggestion.For("dormitory"));        // R-2 and R-3 both list dormitories
        Assert.Null(GroupSuggestion.For("one_family_detached"));
        Assert.Null(GroupSuggestion.For(null));
        var draft = Use("multiple_family");
        var s = Screen(draft: draft);
        var field = s.Fields.Single(f => f.Mark == Marks.OccupancyGroups);
        Assert.Null(field.Current);
        Assert.False(s.Steps.Single(x => x.Field?.Mark == Marks.OccupancyGroups).Done);
        Assert.DoesNotContain(draft.Writes(s.Fields).Writes, w => w.Mark == Marks.OccupancyGroups);
        draft.Choose(Marks.OccupancyGroups, g.Group);               // the Accept
        var accepted = Screen(draft: draft);
        Assert.True(accepted.Steps.Single(x => x.Field?.Mark == Marks.OccupancyGroups).Done);
        Assert.Contains(draft.Writes(accepted.Fields).Writes, w => w.Mark == Marks.OccupancyGroups && w.Value.Text == "R-2");
    }

    // ---- changes 3, 4, 5, 8: one help line, Survey / Tax map, one fold, no counts of optional facts -----------------

    /// <summary>The property line's source is said in the architect's terms (Survey / Tax map, Yes / No on the mark),
    /// with what each means; every step's help is one short line; the fold's summary never counts what is set.</summary>
    [Fact]
    public void The_words_are_short_and_in_the_architect_s_terms()
    {
        var s = Screen();
        var lot = s.Fields.Single(f => f.Mark == Marks.LotSurveyed);
        Assert.Equal([("Yes", "Survey"), ("No", "Tax map")], SetupSteps.Choices(lot).Select(c => (c.Value, c.Label)));
        Assert.Equal("A survey, or traced from the tax map?", SetupSteps.Help(lot, null));
        Assert.Contains("±2 ft", SetupSteps.Help(lot, "No"), StringComparison.Ordinal);
        foreach (var step in s.Steps.Where(x => x.Field is not null))
        {
            var help = SetupSteps.Help(step.Field!, null);
            Assert.NotNull(help);
            Assert.True(help!.Length <= 60, $"{step.Title}: \"{help}\" ({help.Length})");     // one line at 340 px
        }
        var summary = SetupSteps.MoreSummary(s);
        Assert.EndsWith("Gordium asks for one when a result needs it.", summary, StringComparison.Ordinal);
        Assert.DoesNotMatch(@"\d+ of \d+", summary);
        Assert.Equal("Set 6 things to check this project", s.Headline);
        Assert.DoesNotContain("Before checking", s.Headline, StringComparison.Ordinal);
    }

    /// <summary>The street edge's state on its step says which edge, never coordinates.</summary>
    [Fact]
    public void The_street_edge_step_says_which_edge()
    {
        var kept = StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(100, 0, 0))]);
        var s = SetupScreen.Build(Model(new Dictionary<Guid, MarkValue> { [Marks.StreetEdge.Guid] = new(true, Text: kept) }), [], Options, null,
                                  "the south edge, 100'-0\"");
        var f = s.Fields.Single(x => x.Mark == Marks.StreetEdge);
        Assert.Equal("The south edge, 100'-0\"", SetupSteps.StreetState(f, null, s.StreetWords));
        Assert.Equal("Not picked", SetupSteps.StreetState(Screen().Fields.Single(x => x.Mark == Marks.StreetEdge), null, null));
        var typed = Screen(new Dictionary<Guid, MarkValue> { [Marks.StreetEdge.Guid] = new(true, Text: "the front") }).Fields.Single(x => x.Mark == Marks.StreetEdge);
        Assert.Equal("The street edge was typed by hand. Pick it on the plan.", typed.Problem);
        Assert.Equal("Typed by hand — pick again", SetupSteps.StreetState(typed, null, null));     // round 1, #3
        var draft = new SetupDraft();
        draft.Pick([new PickedEdge(new Xyz(0, 0, 0), new Xyz(100, 0, 0), true, 100)]);
        draft.PickedWords = "the south edge, 100'-0\"";
        Assert.Equal("The south edge, 100'-0\"", SetupSteps.StreetState(f with { Current = null }, draft, null));
        draft.Clear();
        Assert.Null(draft.PickedWords);
    }

    // ---- review round 1 -------------------------------------------------------------------------------------------

    /// <summary>Round 1, #1: the steps are exactly what the gate waits for, a problem on an optional fact included
    /// (a sprinkler system typed "NFPA13" on a house): never "Everything the check needs is set" over a form that
    /// Check project keeps showing; and that fact is a step, not only inside the fold.</summary>
    [Fact]
    public void A_fact_the_gate_waits_for_is_a_step_whatever_its_fold()
    {
        var kept = StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(100, 0, 0))]);
        var project = new Dictionary<Guid, MarkValue>
        {
            [Marks.Zone.Guid] = new(true, Text: "R-1b"), [Marks.Use.Guid] = new(true, Text: "one_family_detached"),
            [Marks.LotSurveyed.Guid] = new(true, 1), [Marks.StreetEdge.Guid] = new(true, Text: kept),
            [Marks.SprinklerSystem.Guid] = new(true, Text: "NFPA13"),
        };
        var s = Screen(project);
        Assert.False(s.Ready);
        Assert.NotEqual("Everything the check needs is set", s.Headline);
        var step = Assert.Single(s.Steps, x => x.Key == Marks.SprinklerSystem.Name);
        Assert.False(step.Done);
        Assert.Equal(SetupSteps.Building, step.Section);
        Assert.DoesNotContain(SetupSteps.MoreFields(s), f => f.Mark == Marks.SprinklerSystem);
        Assert.True(s.Steps.Where(x => !x.Done).Select(x => x.Key).ToHashSet().SetEquals(s.Needed));
        // round 2, #1: the house is under the Residential Code: never told the Building Code governs it
        Assert.False(s.BuildingCode);
        Assert.Null(SetupSteps.BuildingNote(s));
        Assert.NotNull(SetupSteps.BuildingNote(Screen(draft: Use("multiple_family"))));
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupView.cs"));
        Assert.Contains("SetupSteps.BuildingNote(_screen) is { } note", view, StringComparison.Ordinal);
        Assert.DoesNotContain("\"The NY Building Code governs", view, StringComparison.Ordinal);
    }

    /// <summary>Round 1, #3: a kept street edge no property line has any more (the lot redrawn) is a problem the form
    /// waits for, as the check would refuse it; never ✓ "Picked".</summary>
    [Fact]
    public void A_kept_edge_off_the_lot_is_asked_again()
    {
        var kept = StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(100, 0, 0))]);
        var project = new Dictionary<Guid, MarkValue> { [Marks.StreetEdge.Guid] = new(true, Text: kept) };
        var off = SetupScreen.Build(Model(project), [], Options, null, null, streetOnLot: false);
        var f = off.Fields.Single(x => x.Mark == Marks.StreetEdge);
        Assert.Equal(SetupSteps.StreetOffLot, f.Problem);
        Assert.Contains(Marks.StreetEdge.Name, off.Needed);
        Assert.False(off.Steps.Single(x => x.Field?.Mark == Marks.StreetEdge).Done);
        Assert.Equal("The lot changed — pick again", SetupSteps.StreetState(f, null, null));
        // round 2, #2: a check refuses it, so the footer never says only its rules will need review
        var draft = new SetupDraft();
        draft.Choose(Marks.Zone, "R-1b");
        var footer = PaneWords.SetupFooter(SetupScreen.Build(Model(project), [], Options, draft, null, streetOnLot: false), draft);
        Assert.Contains(PaneWords.NoStreet, footer, StringComparison.Ordinal);
        Assert.DoesNotContain("street edge isn't set yet", footer, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(PaneWords.NoStreet, PaneWords.SetupFooter(off, new SetupDraft()), StringComparison.Ordinal);   // round 3, #1
        var on = SetupScreen.Build(Model(project), [], Options, null, "the south edge, 100'-0\"", streetOnLot: true);
        Assert.Null(on.Fields.Single(x => x.Mark == Marks.StreetEdge).Problem);
        Assert.DoesNotContain(Marks.StreetEdge.Name, on.Needed);
    }

    /// <summary>Round 1, #4: one group typed any way the check reads it ("R-2," or "r-2") is set, never a problem that
    /// holds the check back.</summary>
    [Theory]
    [InlineData("R-2,")]
    [InlineData("r-2")]
    [InlineData("R-2, R-2")]
    public void One_group_typed_any_way_the_check_reads_is_set(string typed)
    {
        Assert.NotNull(OccupancyGroupWords.Parse(typed));
        var s = Screen(new Dictionary<Guid, MarkValue> { [Marks.OccupancyGroups.Guid] = new(true, Text: typed) }, Use("multiple_family"));
        var f = s.Fields.Single(x => x.Mark == Marks.OccupancyGroups);
        Assert.Null(f.Problem);
        Assert.True(f.IsSet);
        Assert.DoesNotContain(Marks.OccupancyGroups.Name, s.Needed);
        // round 2: never a group listed twice ("r-2" is R-2's choice, read in any case)
        Assert.Equal(f.Choices.Count, f.Choices.Select(c => c.Label.ToUpperInvariant()).Distinct().Count());
    }

    /// <summary>Round 1, #5: without the zoning district nothing is checked at all, so the footer never says only its
    /// rules will need review.</summary>
    [Fact]
    public void Without_the_zone_the_footer_says_nothing_can_be_checked()
    {
        var draft = new SetupDraft();
        draft.Choose(Marks.LotSurveyed, "Yes");
        var words = PaneWords.SetupFooter(Screen(draft: draft), draft);
        Assert.Contains(PaneWords.NoZone, words, StringComparison.Ordinal);
        Assert.DoesNotContain("zoning district", words.Replace(PaneWords.NoZone, "", StringComparison.Ordinal), StringComparison.Ordinal);
        // round 3, #1: before any choice too, never only "a blank makes its rules need review"
        var blank = PaneWords.SetupFooter(Screen(), new SetupDraft());
        Assert.StartsWith(PaneWords.NoZone, blank, StringComparison.Ordinal);
        Assert.NotEqual(PaneWords.BlankFact, blank);
        Assert.Equal(PaneWords.ZoneStep, SetupSteps.Title(Marks.Zone, "").ToLowerInvariant());
    }

    /// <summary>Round 1, #2: the pane and the ribbon promise what is true, nothing written without a click (Accept on a
    /// suggestion writes too), never "until you click Save" alone.</summary>
    [Fact]
    public void The_words_promise_nothing_without_a_click_not_only_Save()
    {
        var said = PaneWords.WelcomeLines.Select(l => l.Words).Concat(RibbonPlan.Buttons(true).SelectMany(b => b.LongDescription.Append(b.ToolTip))).ToList();
        Assert.DoesNotContain(said, w => w.Contains("unless you click Save", StringComparison.Ordinal) || w.Contains("until you click Save", StringComparison.Ordinal));
        Assert.Contains(said, w => w == "Nothing is written to your model without your click.");
    }

    /// <summary>Round 1, #6: a failed or cancelled check shows nothing of a project, so the header forgets the last
    /// project's name.</summary>
    [Fact]
    public void A_failed_check_drops_the_last_project_s_name()
    {
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        var failed = view[view.IndexOf("    internal void Failed(CheckFailure? failure)", StringComparison.Ordinal)..];   // UI polish PR 5
        failed = failed[..failed.IndexOf("\n    }\n", StringComparison.Ordinal)];
        Assert.Contains("_title.Text = PaneWords.HeaderTitle(null);", failed, StringComparison.Ordinal);
    }

    // ---- change 11: the edge in words ------------------------------------------------------------------------------

    [Theory]
    [InlineData(0, -1, "south")]
    [InlineData(0, 1, "north")]
    [InlineData(1, 0, "east")]
    [InlineData(-1, 0, "west")]
    [InlineData(1, 1, "north-east")]
    [InlineData(-1, -1, "south-west")]
    [InlineData(0.2, -1, "south")]
    public void An_outward_normal_is_its_compass_side(double nx, double ny, string side) => Assert.Equal(side, EdgeWords.Side(nx, ny));

    [Theory]
    [InlineData(100, "100'-0\"")]
    [InlineData(47.125, "47'-1 1/2\"")]
    [InlineData(0.5, "0'-6\"")]
    [InlineData(59.99, "60'-0\"")]
    public void A_length_in_feet_and_inches(double feet, string words) => Assert.Equal(words, EdgeWords.FeetInches(feet));

    /// <summary>Each edge of a rectangular lot is said by the side it faces (away from the lot), whichever way the
    /// outline runs.</summary>
    [Fact]
    public void Each_edge_of_a_lot_is_the_side_it_faces()
    {
        (double, double)[] ring = [(0, 0), (100, 0), (100, 60), (0, 60)];
        Assert.Equal("the south edge, 100'-0\"", EdgeWords.Describe((0, 0), (100, 0), (50, 0), 100, ring).Words);
        Assert.Equal("the north edge, 100'-0\"", EdgeWords.Describe((100, 60), (0, 60), (50, 60), 100, ring).Words);
        Assert.Equal("the east edge, 60'-0\"", EdgeWords.Describe((100, 0), (100, 60), (100, 30), 60, ring).Words);
        Assert.Equal("the west edge, 60'-0\"", EdgeWords.Describe((0, 60), (0, 0), (0, 30), 60, [.. ring.AsEnumerable().Reverse()]).Words);
        Assert.Equal("the 100'-0\" edge", EdgeWords.Describe((0, 0), (100, 0), (50, 0), 100, null).Words);
        Assert.Equal("Gordium read your click as the south edge of the lot, 100'-0\" long.",
                     EdgeWords.Describe((0, 0), (100, 0), (50, 0), 100, ring).Sentence);
    }

    /// <summary>From Revit's property line: the edge found by its ends, the lot's outline from the property line's
    /// own curves, turned into the shared coordinates (a lot turned 90° says another side); an edge no property line
    /// has is not said (never a guess).</summary>
    [Fact]
    public void A_kept_edge_is_said_from_its_property_line()
    {
        LotCurve L(double x0, double y0, double x1, double y1) => new(new Xyz(x0, y0, 0), new Xyz(x1, y1, 0), true, Math.Sqrt((x1 - x0) * (x1 - x0) + (y1 - y0) * (y1 - y0)));
        var line = new LotLineElement("pl", true, [L(0, 0, 100, 0), L(100, 0, 100, 60), L(100, 60, 0, 60), L(0, 60, 0, 0)]);
        Assert.Equal("the south edge, 100'-0\"", EdgeWords.Of(new Xyz(100, 0, 0), new Xyz(0, 0, 0), [line], Transform3.Identity, 0.001)!.Words);
        var turned = Transform3.Identity with { BasisX = new Xyz(0, 1, 0), BasisY = new Xyz(-1, 0, 0) };   // +X internal is north
        Assert.Equal("the east edge, 100'-0\"", EdgeWords.Of(new Xyz(0, 0, 0), new Xyz(100, 0, 0), [line], turned, 0.001)!.Words);
        Assert.Null(EdgeWords.Of(new Xyz(5, 5, 0), new Xyz(6, 6, 0), [line], Transform3.Identity, 0.001));
        Assert.Equal("the south edge, 100'-0\" and the east edge, 60'-0\"",
                     EdgeWords.OfMark(StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(100, 0, 0)), (new Xyz(100, 0, 0), new Xyz(100, 60, 0))]), [line], Transform3.Identity, 0.001));
        Assert.Null(EdgeWords.OfMark("the front", [line], Transform3.Identity, 0.001));
    }

    // ---- change 10: the dialog ends the pick ------------------------------------------------------------------------

    private static readonly PickedEdge South = new(new Xyz(0, 0, 0), new Xyz(100, 0, 0), true, 100);
    private static readonly PickedEdge East = new(new Xyz(100, 0, 0), new Xyz(100, 60, 0), true, 60);

    /// <summary>"Use this edge" keeps it and ends the pick at once (before, Yes kept it and Revit waited, silently,
    /// for Esc: CheckProject.PickEdges, the bug Ben hit in the trial).</summary>
    [Fact]
    public void Use_this_edge_ends_the_pick()
    {
        var p = new PickSession();
        Assert.True(p.Asking);
        p.Answer(South, PickAnswer.Use);
        Assert.False(p.Asking);
        Assert.Equal([South], p.Kept);
        Assert.Throws<InvalidOperationException>(() => p.Answer(East, PickAnswer.Use));
    }

    [Fact]
    public void Use_and_another_keeps_it_and_asks_once_more_never_twice_the_same()
    {
        var p = new PickSession();
        p.Answer(South, PickAnswer.UseAndAnother);
        Assert.True(p.Asking);
        Assert.Contains("another", p.Prompt, StringComparison.Ordinal);
        p.Answer(South, PickAnswer.UseAndAnother);
        p.Answer(East, PickAnswer.Use);
        Assert.Equal([South, East], p.Kept);
        Assert.False(p.Asking);
    }

    [Fact]
    public void A_different_edge_forgets_the_click_and_closing_or_Esc_ends_with_what_was_kept()
    {
        var p = new PickSession();
        p.Answer(South, PickAnswer.Different);
        Assert.True(p.Asking);
        Assert.Empty(p.Kept);
        p.Answer(East, PickAnswer.UseAndAnother);
        p.Answer(South, PickAnswer.Close);
        Assert.False(p.Asking);
        Assert.Equal([East], p.Kept);
        var q = new PickSession();
        q.Escape();
        Assert.False(q.Asking);
        Assert.Empty(q.Kept);
    }

    /// <summary>The confirmation's words are the design's (strings.md, Picking the street edge), with no coordinates.</summary>
    [Fact]
    public void The_confirmation_says_the_edge_in_words_with_three_answers()
    {
        var (instruction, content, use, another, different) = PickSession.Confirm(new EdgeDescription("south", "100'-0\""));
        Assert.Equal("Use this edge as the street line?", instruction);
        Assert.Equal("Gordium read your click as the south edge of the lot, 100'-0\" long.", content);
        Assert.Equal(("Use this edge", "Use it, and pick another street edge", "Pick a different edge"), (use, another, different));
        Assert.DoesNotMatch(@"\(-?\d+\.\d, -?\d+\.\d\)", content);
        var pick = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "CheckProject.cs"));
        var body = pick[pick.IndexOf("internal static List<PickedEdge> PickEdges(", StringComparison.Ordinal)..];
        body = body[..body.IndexOf("\n    }\n", StringComparison.Ordinal)];
        Assert.Contains("while (session.Asking)", body, StringComparison.Ordinal);
        Assert.DoesNotContain("TaskDialogCommonButtons.Yes", body, StringComparison.Ordinal);
        Assert.Contains("session.Answer(got, answer);", body, StringComparison.Ordinal);
    }
}
