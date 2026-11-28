using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The facts the checker already reads that architects had no way to enter (derive before asking: a mark only
/// for what the model can't show for certain). A door's hardware (BCNYS 1010.2.8): no Revit door family or type
/// parameter says it, so the door's own mark Gordium: Hardware, sent as <c>doors[].hardware</c>. An escape opening's
/// place below grade and its area well (BCNYS 1031.5): a well isn't in Revit's vocabulary (below grade and the depth
/// are also measured from a Toposolid stated to be the finished ground: GroundTests), so the window's or door's own marks, sent as <c>openings[].stated_well</c>, each only
/// when set (blank is not stated, never 0 or No).</summary>
public sealed class HardwareAndWellMarksTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    // ---- the door's hardware -------------------------------------------------------------------------------------

    [Fact]
    public void The_hardware_mark_is_each_doors_own_word_quoting_1010_2_8()
    {
        var m = Marks.DoorHardware;
        Assert.Contains(m, Marks.All);
        Assert.Equal((MarkValueKind.Text, MarkBinding.Instance, "doors[].hardware"), (m.Kind, m.Binding, m.Feeds));
        Assert.Equal([Marks.Doors], m.Categories);
        Assert.Contains("\"Swinging doors serving a Group H occupancy and swinging doors serving rooms or spaces with an occupant load of 50 or more in a Group A or E occupancy shall not be provided with a latch or lock other than panic hardware or fire exit hardware.\"",
                        m.Description, StringComparison.Ordinal);
        // each word reaches exactly the measuring's word (model_measurement/routes/doors.py HARDWARE)
        Assert.Equal(["panic", "panic_electric", "latch", "none"], HardwareWords.Table.Words.Select(w => HardwareWords.Table.Of(w)!).ToList());
        var said = Env.RunCode("import json\nfrom model_measurement.routes.doors import HARDWARE\nprint(json.dumps(sorted(HARDWARE)))");
        Assert.Equal(JsonSerializer.Deserialize<List<string>>(said)!.Order(), HardwareWords.Table.Words.Select(w => HardwareWords.Table.Of(w)!).Order());
        Assert.Equal("latch", HardwareWords.Table.Of("  other LATCH or lock "));
    }

    [Fact]
    public void Hardware_is_sent_only_as_a_word_of_the_list_and_anything_else_is_said_never_sent()
    {
        var floor = new FakeFloor();
        floor.SetMark("dA", Marks.DoorHardware, new(true, Text: "Panic or fire exit hardware"));
        floor.SetMark("dB", Marks.DoorHardware, new(true, Text: "No latch or lock"));
        floor.SetMark("dS", Marks.DoorHardware, new(true, Text: "Panic bar"));          // not a word of the list
        floor.SetMark("dE", Marks.DoorHardware, new(false, Text: ""));                 // never set
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal("panic", FakeFloor.Part(read, "doors", "dA")!["hardware"]!.GetValue<string>());
        Assert.Equal("none", FakeFloor.Part(read, "doors", "dB")!["hardware"]!.GetValue<string>());
        foreach (var id in new[] { "dS", "dE", "dS2" })                                 // dS2: no mark at all
            Assert.Null(FakeFloor.Part(read, "doors", id)!["hardware"]);
        var notes = read.Notes.Where(n => n.Field == "doors.hardware").ToDictionary(n => n.Part, n => n.Why);
        Assert.Equal("Gordium: Hardware is \"Panic bar\", not one of: " + HardwareWords.Table.Listed, notes[FakeFloor.Uid("dS")]);
        Assert.Equal("Gordium: Hardware is not set", notes[FakeFloor.Uid("dE")]);
        Assert.False(notes.ContainsKey(FakeFloor.Uid("dA")));
    }

    private static CheckResult Apartment()
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "four_unit_apartment_check_answer.json");
        var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
        return CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About));
    }

    /// <summary>The trial apartment's real answer (no door's hardware marked): before, its panic hardware results asked
    /// "Mark the door latched in the model" and "Mark the door electric lock in the model", marks Revit didn't have;
    /// now one card names the field Gordium: Hardware answers and selects the doors to set it on.</summary>
    [Fact]
    public void The_apartments_panic_hardware_ask_is_one_card_opening_the_hardware_mark()
    {
        var model = ResultViews.Build(Apartment());
        var cards = model.Fix.SelectMany(g => g.Cards).ToList();
        var card = Assert.Single(cards, c => c.Field == "doors[].hardware");
        Assert.Equal((FixKind.Mark, "Set what latches or locks each door (panic hardware, an electric lock with it, a latch, or none)"),
                     (card.Kind, card.Headline));
        Assert.Equal(Marks.DoorHardware, Marks.All.Single(k => CauseCardsFields(k).Contains(card.Field!)));
        Assert.DoesNotContain(cards, c => c.Headline.Contains("latched in the model", StringComparison.Ordinal)
                                          || c.Headline.Contains("panic hardware in the model", StringComparison.Ordinal));
        var cause = Assert.Single(ResultRows.Build(Apartment(), null, [], null).Causes, c => c.Fields.Contains("doors[].hardware"));
        var labels = cause.Elements.ToDictionary(e => e, e => "door " + e, StringComparer.Ordinal);
        Assert.Equal(CardAction.ShowAndProperties, CauseCards.Action(cause, labels));
        Assert.Equal([Marks.DoorHardware], CauseCards.MarksOf(cause));
        Assert.DoesNotContain("Edit Type", CauseCards.AfterProperties(cause, 3), StringComparison.Ordinal);   // the door's own mark
    }

    private static IEnumerable<string> CauseCardsFields(MarkDefinition m) =>
        m.Feeds.Split(", ").Select(p => p.Split(' ')[0]).Where(p => p.Length > 0);

    // ---- an escape opening's place below grade and its area well --------------------------------------------------

    private static void SetMark(FakeHouse house, string id, MarkDefinition mark, MarkValue? value)
    {
        var i = house.Marked.FindIndex(m => m.UniqueId == FakeHouse.Uid(id));
        var marks = new Dictionary<Guid, MarkValue>(house.Marked[i].Instance);
        if (value is null)
            marks.Remove(mark.Guid);
        else
            marks[mark.Guid] = value;
        house.Marked[i] = house.Marked[i] with { Instance = marks };
    }

    private static JsonObject Opening(InteriorReadResult read, string id) =>
        read.Interior["openings"]!.AsArray().Select(o => o!.AsObject()).Single(o => o["id"]!.GetValue<string>() == FakeHouse.Uid(id));

    [Fact]
    public void Each_well_mark_is_an_escape_openings_own_and_feeds_its_stated_well_key()
    {
        Assert.Equal(14, Marks.WellMarks.Count);
        foreach (var (m, key) in Marks.WellMarks)
        {
            Assert.Contains(m, Marks.All);
            Assert.Equal(MarkBinding.Instance, m.Binding);
            Assert.Equal([Marks.Windows, Marks.Doors], m.Categories);
            Assert.Equal("openings[].stated_well." + key, m.Feeds);
            Assert.Contains("Blank", m.Description, StringComparison.Ordinal);
        }
        // the keys are exactly the measuring's (model_measurement/interior/openings.py STATED_WELL), and so are the
        // ladder's words
        var said = JsonNode.Parse(Env.RunCode("import json\nfrom model_measurement.interior.openings import STATED_WELL, LADDER_WORDS\n" +
                                              "print(json.dumps({'keys': list(STATED_WELL), 'ladder': list(LADDER_WORDS)}))"))!;
        Assert.Equal(said["keys"]!.AsArray().Select(k => k!.GetValue<string>()), Marks.WellMarks.Select(w => w.Key));
        Assert.Equal(said["ladder"]!.AsArray().Select(k => k!.GetValue<string>()).Order(),
                     WellLadderWords.Table.Words.Select(w => WellLadderWords.Table.Of(w)!).Order());
        Assert.Equal("ladder_blocked", WellLadderWords.Table.Of("ladder BLOCKED when open"));
    }

    [Fact]
    public void A_well_mark_set_is_sent_as_typed_and_a_blank_one_isnt_sent_never_0_or_no()
    {
        var house = FakeHouse.Draw("5_basement_window_well");
        SetMark(house, "we1", Marks.BelowGrade, new(true, 1));
        SetMark(house, "we1", Marks.WellArea, new(true, Number: 9.5));                 // square feet, Revit's own
        SetMark(house, "we1", Marks.WellWidth, new(true, Number: 3.5));                // feet
        SetMark(house, "we1", Marks.WellDepth, new(true, Number: 4.0));
        SetMark(house, "we1", Marks.WellLadder, new(true, Text: "Ladder"));
        SetMark(house, "we1", Marks.WellLadderFullHeight, new(true, 0));
        SetMark(house, "we1", Marks.WellOtherEncroachment, new(true, Number: 0.0));     // 0 stated is sent: nothing reaches in
        SetMark(house, "we1", Marks.WellProjection, new(false, Number: 0.0));          // never set: Revit reads 0
        var read = InteriorReader.Read(house.Model());
        var well = Opening(read, "we1")["stated_well"]!.AsObject();
        Assert.Equal(new Dictionary<string, string>
        {
            ["below_grade"] = "true", ["area"] = "9.5", ["width"] = "3.5", ["depth"] = "4", ["ladder"] = "\"ladder\"",
            ["full_height"] = "false", ["other_encroachment"] = "0",
        }, well.ToDictionary(p => p.Key, p => p.Value!.ToJsonString()));
        // each blank one of an escape opening said by its mark; another window's or door's blanks aren't noise
        var notes = read.Notes.Where(n => n.Part == FakeHouse.Uid("we1") && n.Field.StartsWith("stated_well.", StringComparison.Ordinal))
            .ToDictionary(n => n.Field, n => n.Why);
        Assert.Equal("Gordium: Well projection is not set", notes["stated_well.projection"]);
        Assert.Equal(7, notes.Count);
        Assert.DoesNotContain(read.Notes, n => n.Part != FakeHouse.Uid("we1") && n.Part != FakeHouse.Uid("we2") && n.Field.StartsWith("stated_well.", StringComparison.Ordinal));
        // every opening says what it states, even nothing, so the measuring names each blank mark
        Assert.All(read.Interior["openings"]!.AsArray(), o => Assert.NotNull(o!["stated_well"]));
        Assert.Empty(Opening(read, "we2")["stated_well"]!.AsObject());
    }

    [Fact]
    public void A_ladder_word_gordium_cant_read_is_said_and_not_sent()
    {
        var house = FakeHouse.Draw("5_basement_window_well");
        SetMark(house, "we1", Marks.WellLadder, new(true, Text: "Rungs"));
        var read = InteriorReader.Read(house.Model());
        Assert.Null(Opening(read, "we1")["stated_well"]!["ladder"]);
        Assert.Equal("Gordium: Well ladder or steps is \"Rungs\", not one of: " + WellLadderWords.Listed,
                     read.Notes.Single(n => n.Part == FakeHouse.Uid("we1") && n.Field == "stated_well.ladder").Why);
    }

    /// <summary>The marks reach the rules in the measuring's own units: 3.5 ft typed is 42 in, 9.5 sq ft is 9.5 sq ft;
    /// a blank one is not stated, its reason naming the marks; below grade and the ladder go to the rules too.</summary>
    [Fact]
    public void The_marks_reach_the_measuring_as_the_architect_typed_them()
    {
        var house = FakeHouse.Draw("5_basement_window_well");
        SetMark(house, "we1", Marks.BelowGrade, new(true, 1));
        SetMark(house, "we1", Marks.WellArea, new(true, Number: 9.5));
        SetMark(house, "we1", Marks.WellWidth, new(true, Number: 3.5));
        SetMark(house, "we1", Marks.WellProjection, new(true, Number: 3.25));
        SetMark(house, "we1", Marks.WellLadder, new(true, Text: "Steps blocked when open"));
        // the well's size goes to the rules only once nothing but a required ladder or steps reaches into it
        SetMark(house, "we1", Marks.WellLadderEncroachment, new(true, Number: 0.0));
        SetMark(house, "we1", Marks.WellOtherEncroachment, new(true, Number: 0.0));
        var read = InteriorReader.Read(house.Model());
        var path = Path.Combine(Path.GetTempPath(), $"gordium_well_{Guid.NewGuid():N}.json");
        File.WriteAllText(path, read.Interior.ToJsonString());
        try
        {
            const string Code = "import json, sys\nfrom model_measurement.interior import measure\n" +
                                "d = json.load(open(sys.argv[1], encoding='utf-8'))\n" +
                                "p = [p for p in measure(d)['parts']['emergency_escape_opening'] if p['id'] == sys.argv[2]][0]\n" +
                                "print(json.dumps({'m': p['measures'], 'not': p['not_measured']}))";
            var got = JsonNode.Parse(Env.RunCode(Code, path, FakeHouse.Uid("we1")))!;
            var m = got["m"]!;
            Assert.True(m["opening_below_grade"]!.GetValue<bool>());
            Assert.Equal(9.5, m["area_well_area"]!.GetValue<double>(), 6);
            Assert.Equal(42.0, m["area_well_width"]!.GetValue<double>(), 6);
            Assert.Equal(39.0, m["area_well_projection"]!.GetValue<double>(), 6);
            // steps the open window blocks are steps, never the ladder or steps 1031.5.2 accepts
            Assert.False(m["area_well_ladder"]!.GetValue<bool>());
            Assert.True(m["area_well_steps"]!.GetValue<bool>());
            Assert.Null(m["area_well_depth"]);
            Assert.Contains("(its area well marks)", got["not"]!["area_well_depth"]!.GetValue<string>(), StringComparison.Ordinal);
        }
        finally
        {
            File.Delete(path);
        }
    }

    /// <summary>A card asking for an area well's fact names the mark that answers it (the worker names the field), and
    /// selects the escape opening to set it on (a window's own mark, no Edit Type).</summary>
    [Fact]
    public void An_area_well_card_opens_the_mark_its_field_names()
    {
        foreach (var (mark, key) in Marks.WellMarks)
        {
            var cause = new CauseCard("field:openings[].stated_well." + key, CauseKind.Mark, "w", ["w1"], [], 1, "g")
            {
                Fields = ["openings[].stated_well." + key],
            };
            Assert.Equal([mark], CauseCards.MarksOf(cause));
            Assert.DoesNotContain("Edit Type", CauseCards.AfterProperties(cause, 1), StringComparison.Ordinal);
        }
    }
}
