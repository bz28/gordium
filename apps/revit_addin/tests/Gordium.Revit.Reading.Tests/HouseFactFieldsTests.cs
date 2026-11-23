using System.Text;
using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>UI design change 20: the house's own facts Ithaca's zoning reads and no drawing shows (a stream within
/// 20 ft, who lives there, the garage's cars) are Project Information fields, so the house's first fixes are made in
/// Revit. Each is sent only when set (a blank one is not stated, and its rule needs review: never No or 0); a value
/// Gordium can't read is said in plain words and not sent; the form writes nothing without a click; and the worker's
/// cards for them now have their button.</summary>
public sealed class HouseFactFieldsTests
{
    private static readonly (MarkDefinition Mark, string Key, MarkValue Value, string Sent)[] Each =
    [
        (Marks.StreamNearLot, "stream_near_lot", new(true, 1), "true"),
        (Marks.StreamDistance, "stream_distance", new(true, Number: 18.25), "18.25"),
        (Marks.UnrelatedPersons, "unrelated_persons", new(true, 2), "2"),
        (Marks.OwnerOccupied, "owner_occupied", new(true, 0), "false"),
        (Marks.FunctionalFamilyUnit, "functional_family_unit", new(true, 0), "false"),
        (Marks.GarageCars, "garage_cars", new(true, 0), "0"),
        (Marks.PrivateGarages, "private_garages", new(true, 1), "1"),
    ];

    private static RevitModel Model(Dictionary<Guid, MarkValue> marks) => new() { Document = "house.rvt", ProjectMarks = marks };

    /// <summary>The Project Information facts a check needs set, so only the house facts are in question.</summary>
    private static Dictionary<Guid, MarkValue> Needed() => new()
    {
        [Marks.Zone.Guid] = new(true, Text: "R-1b"), [Marks.Use.Guid] = new(true, Text: "one_family_detached"),
        [Marks.LotSurveyed.Guid] = new(true, 1), [Marks.StreetEdge.Guid] = new(true, Text: StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(60, 0, 0))])),
    };

    [Fact]
    public void Each_house_fact_is_a_project_information_mark_quoting_its_law()
    {
        Assert.Equal(Each.Select(e => e.Mark), ProjectFacts.HouseFactMarks.Select(h => h.Mark));
        foreach (var (m, key, _, _) in Each)
        {
            Assert.Contains(m, Marks.All);                                  // MarkSetup adds it; the Setup form lists it
            Assert.Equal([Marks.ProjectInformation], m.Categories);
            Assert.Equal("facts." + key, m.Feeds);                         // the field the worker's card names
            Assert.Contains("\"", m.Description, StringComparison.Ordinal);   // the law's own words, quoted
            Assert.Contains("Blank", m.Description, StringComparison.Ordinal);
        }
        Assert.Contains("No new structure shall be located nearer than 20 feet to an inlet wall", Marks.StreamNearLot.Description, StringComparison.Ordinal);
        Assert.Contains("permitted if the dwelling is owner-occupied", Marks.OwnerOccupied.Description, StringComparison.Ordinal);
        Assert.Contains("For not more than three cars.", Marks.GarageCars.Description, StringComparison.Ordinal);
        // the form's least for a count is read from its words: 0 for the cars and the people, 1 for the garages
        Assert.Equal((0, 0, 1), (SetupFacts.Least(Marks.GarageCars), SetupFacts.Least(Marks.UnrelatedPersons), SetupFacts.Least(Marks.PrivateGarages)));
    }

    [Fact]
    public void Each_fact_set_is_read_and_sent_under_its_own_key_as_the_architect_gave_it()
    {
        var marks = Needed();
        foreach (var e in Each)
            marks[e.Mark.Guid] = e.Value;
        var read = ProjectFacts.Read(Model(marks));
        Assert.DoesNotContain(read.Missing, m => m.StartsWith("Gordium: ", StringComparison.Ordinal) && Each.Any(e => m.StartsWith(e.Mark.Name, StringComparison.Ordinal)));
        foreach (var (_, key, _, sent) in Each)
            Assert.Equal(sent, read.Facts[key]!.ToJsonString());
        Assert.Empty(SetupFacts.NotSent(Model(marks), read));
    }

    [Theory]
    [MemberData(nameof(Keys))]
    public void A_blank_field_is_not_stated_never_No_or_0(string key)
    {
        var (mark, _, _, _) = Each.Single(e => e.Key == key);
        foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false, Number: 0), new(false) })
        {
            var marks = Needed();
            if (blank is { } b)
                marks[mark.Guid] = b;                                      // Revit's unset parameter: HasValue false
            var read = ProjectFacts.Read(Model(marks));
            Assert.False(read.Facts.ContainsKey(key));                     // not sent: its rule needs review
            Assert.DoesNotContain(read.Missing, m => m.StartsWith(mark.Name, StringComparison.Ordinal));
            var field = SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == mark);
            Assert.Null(field.Current);                                    // the form shows it not stated
            Assert.False(field.IsSet);
        }
    }

    public static TheoryData<string> Keys => [.. Each.Select(e => e.Key)];

    [Theory]
    [InlineData("stream_near_lot", "text", "holds a value that isn't Yes or No")]
    [InlineData("owner_occupied", "two", "holds a value that isn't Yes or No")]
    [InlineData("unrelated_persons", "text", "holds a value that isn't a whole number")]
    [InlineData("private_garages", "zero", "is 0: type 1 or more")]
    [InlineData("garage_cars", "minus", "is -1: type 0 or more")]
    [InlineData("stream_distance", "minus", "is -2.5 ft: type a distance of 0 ft or more")]
    [InlineData("stream_distance", "text", "holds a value that isn't a length")]
    public void A_value_Gordium_cant_read_is_said_plainly_and_not_sent(string key, string how, string said)
    {
        var (mark, _, _, _) = Each.Single(e => e.Key == key);
        var marks = Needed();
        marks[mark.Guid] = how switch
        {
            "text" => new MarkValue(true, Text: "yes please"),
            "two" => new MarkValue(true, 2),
            "zero" => new MarkValue(true, 0),
            "minus" when mark.Kind == MarkValueKind.Length => new MarkValue(true, Number: -2.5),
            _ => new MarkValue(true, -1),
        };
        var model = Model(marks);
        var read = ProjectFacts.Read(model);
        Assert.False(read.Facts.ContainsKey(key));                         // never sent as something near it
        Assert.StartsWith($"{mark.Name} {said}", Assert.Single(read.Missing), StringComparison.Ordinal);
        Assert.EndsWith("on Project Information (Manage > Project Information).", read.Missing[0], StringComparison.Ordinal);
        // a check sent anyway names it as not sent, so nothing reads it as not stated
        Assert.Equal([mark], SetupFacts.NotSent(model, read));
        // the form says it too, and waits for it
        var screen = SetupScreen.Build(model, [], null, null);
        var field = screen.Fields.Single(f => f.Mark == mark);
        Assert.NotNull(field.Problem);
        Assert.Contains(mark.Name, screen.Needed);
    }

    [Fact]
    public void The_stream_distance_is_a_feet_field_saved_as_typed_and_only_when_chosen()
    {
        var model = Model(Needed());
        var fields = SetupScreen.Build(model, [], null, null).Fields;
        var field = fields.Single(f => f.Mark == Marks.StreamDistance);
        Assert.Equal(FieldKind.Feet, field.Kind);
        var draft = new SetupDraft();
        Assert.Empty(draft.Writes(fields).Writes);                         // nothing chosen: nothing written
        draft.Choose(Marks.StreamDistance, "19.96");
        var w = Assert.Single(draft.Writes(fields).Writes);
        Assert.Equal((Marks.StreamDistance, 19.96), (w.Mark, w.Value.Number!.Value));   // never rounded to 20
        foreach (var bad in new[] { "-1", "twenty", "1e3", "NaN", "19,5" })
        {
            draft.Choose(Marks.StreamDistance, bad);
            var (writes, problems) = draft.Writes(fields);
            Assert.Empty(writes);
            Assert.Contains("isn't a length in feet, 0 or more", Assert.Single(problems), StringComparison.Ordinal);
        }
        // a distance the mark holds shows as Revit gives it (feet)
        var marks = Needed();
        marks[Marks.StreamDistance.Guid] = new(true, Number: 22.5);
        Assert.Equal("22.5", SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == Marks.StreamDistance).Current);
        Assert.Contains("case FieldKind.Feet:", File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "SetupView.cs")),
                        StringComparison.Ordinal);                         // the view shows it as a text box
    }

    [Fact]
    public void The_new_fields_are_in_the_lot_group_of_the_setup_form()
    {
        var fields = SetupScreen.Build(Model(Needed()), [], null, null).Fields;
        foreach (var (m, _, _, _) in Each)
            Assert.Equal("The lot and the house", fields.Single(f => f.Mark == m).Group);
    }

    // ---- review round 1: units before typing, and the law's words exactly ----------------------------------------

    /// <summary>Every number a mark takes says what it is before it is typed, and the words are true wherever they are
    /// read: a count says "A count:"; a length's tooltip (which Revit's own Project Information and Type Properties
    /// dialogs show, where a number is read in the project's length units) opens "A length, in this project's length
    /// units" and never names one unit (review round 2: "In feet" let 15 typed in a meters project be 15 m, 49 ft).</summary>
    [Fact]
    public void Every_numeric_mark_says_what_its_number_is_and_it_is_true_in_revits_dialogs_too()
    {
        var numeric = Marks.All.Where(m => m.Kind is MarkValueKind.Length or MarkValueKind.Integer).ToList();
        Assert.True(numeric.Count >= 13);
        foreach (var m in numeric)
        {
            if (m.Kind == MarkValueKind.Length)
            {
                Assert.Equal("length", Marks.Unit(m));
                Assert.StartsWith(Marks.LengthWords, m.Description, StringComparison.Ordinal);
                foreach (var claim in new[] { "In feet", "in feet", "(ft)", "In inches", "in inches" })
                    Assert.DoesNotContain(claim, m.Description, StringComparison.Ordinal);
                Assert.EndsWith(" (ft)", SetupWords.Label(m, "house"), StringComparison.Ordinal);      // the form's default, a feet project
                Assert.EndsWith(" (mm)", SetupWords.Label(m, "house", "mm"), StringComparison.Ordinal);
            }
            else
            {
                Assert.Equal("count", Marks.Unit(m));
                Assert.StartsWith("A count: ", m.Description, StringComparison.Ordinal);
                Assert.EndsWith(" (count)", SetupWords.Label(m, "house"), StringComparison.Ordinal);
            }
        }
        Assert.All(Marks.All.Where(m => !numeric.Contains(m)), m => Assert.Null(Marks.Unit(m)));
        var fields = SetupScreen.Build(Model(Needed()), [], null, null).Fields;
        Assert.Equal("Garage cars (count)", fields.Single(f => f.Mark == Marks.GarageCars).Label);
    }

    private static RevitModel InUnits(string displayUnits, double? streamFeet = null)
    {
        var marks = Needed();
        if (streamFeet is { } f)
            marks[Marks.StreamDistance.Guid] = new(true, Number: f);
        return new() { Document = "house.rvt", ProjectMarks = marks, DisplayUnits = displayUnits };
    }

    /// <summary>The Setup form's length field follows the project's length units, as Revit's dialogs do: labelled with
    /// the unit, shown in it, and a number typed there saved so Revit shows that same number (a feet project and a
    /// millimeters project); a project in units Gordium doesn't read takes feet and says so beside the field.</summary>
    [Theory]
    [InlineData("autodesk.unit.unit:feetFractionalInches-1.0.1", "ft", "22.5", "18.25", 18.25)]
    [InlineData("autodesk.unit.unit:feet-1.0.1", "ft", "22.5", "18.25", 18.25)]
    [InlineData("autodesk.unit.unit:millimeters-1.0.1", "mm", "6858", "6000", 6000 / 304.8)]
    [InlineData("autodesk.unit.unit:meters-1.0.1", "m", "6.858", "15", 15 / 0.3048)]
    [InlineData("autodesk.unit.unit:inches-1.0.1", "in", "270", "240", 20.0)]
    public void The_forms_length_field_is_in_the_projects_units_and_saves_what_revit_shows(
        string units, string symbol, string shown, string typed, double savedFeet)
    {
        var field = SetupScreen.Build(InUnits(units, 22.5), [], null, null).Fields.Single(f => f.Mark == Marks.StreamDistance);
        Assert.Equal($"Distance from stream ({symbol})", field.Label);
        Assert.Equal(shown, field.Current);                                // 22.5 ft as Revit shows it in this project
        Assert.DoesNotContain("type feet here", field.Law, StringComparison.Ordinal);
        var blank = SetupScreen.Build(InUnits(units), [], null, null).Fields;
        var draft = new SetupDraft();
        draft.Choose(Marks.StreamDistance, typed);
        var w = Assert.Single(draft.Writes(blank).Writes);
        Assert.Equal(savedFeet, w.Value.Number!.Value, 9);                 // feet, Revit's internal unit
        // read back as Revit would show it: the number typed
        var again = SetupScreen.Build(InUnits(units, w.Value.Number), [], null, null).Fields.Single(f => f.Mark == Marks.StreamDistance);
        Assert.Equal(typed, again.Current);
    }

    [Fact]
    public void A_project_in_units_gordium_doesnt_read_takes_feet_and_says_so()
    {
        var field = SetupScreen.Build(InUnits("autodesk.unit.unit:usSurveyFeet-1.0.0", 10), [], null, null).Fields.Single(f => f.Mark == Marks.StreamDistance);
        Assert.Equal("Distance from stream (ft)", field.Label);
        Assert.Equal("10", field.Current);
        Assert.Contains("aren't ones Gordium reads: type feet here", field.Law, StringComparison.Ordinal);
        Assert.Contains("DisplayUnits = doc.GetUnits().GetFormatOptions(SpecTypeId.Length).GetUnitTypeId().TypeId",
                        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "RevitMarks.cs")), StringComparison.Ordinal);
    }

    private static string Plain(string text) =>
        System.Text.RegularExpressions.Regex.Replace(text.Replace('\u201c', '"').Replace('\u201d', '"').Replace('\u2019', '\'')
                                                         .Replace('\u2014', '-').Replace('\u2013', '-'), @"\s+", " ");

    /// <summary>The law's words for New York, each passage kept apart: the City's extracted text (each document's lines in
    /// order), the rulebooks' and state law folders' <c>quote:</c> values (only those, never a reason or a note), and the
    /// code decision's cites (design_checker/code_scope.py CITES, each read again from its PDF page by
    /// test_every_quote_is_on_its_page_in_the_book: the state books' own text lives outside the repository).</summary>
    private static readonly Lazy<string> Law = new(() =>
    {
        var root = Path.Combine(Env.Repo, "regulations", "jurisdictions", "new_york");
        var sb = new StringBuilder();
        foreach (var f in Directory.EnumerateFiles(root, "*.jsonl", SearchOption.AllDirectories).Where(f => f.Contains("2_extracted_text", StringComparison.Ordinal)))
        {
            foreach (var line in File.ReadLines(f))
                if (JsonDocument.Parse(line).RootElement is { ValueKind: JsonValueKind.Object } o && o.TryGetProperty("text", out var t) && t.ValueKind == JsonValueKind.String)
                    sb.Append(t.GetString()).Append(' ');
            sb.Append(" ¦ ");
        }
        const string Quotes = "import json, pathlib, sys, yaml\n"
            + "from design_checker import code_scope\n"
            + "out = [q for _, _, q in code_scope.CITES.values()]\n"
            + "def walk(o):\n"
            + "    if isinstance(o, dict):\n"
            + "        for k, v in o.items():\n"
            + "            if k == 'quote' and isinstance(v, str): out.append(v)\n"
            + "            else: walk(v)\n"
            + "    elif isinstance(o, list):\n"
            + "        for v in o: walk(v)\n"
            + "for p in sorted(pathlib.Path(sys.argv[1]).rglob('*.yaml')): walk(yaml.safe_load(p.read_text(encoding='utf-8')))\n"
            + "sys.stdout.buffer.write(json.dumps(out, ensure_ascii=True).encode())\n";
        foreach (var q in JsonDocument.Parse(Env.RunCode(Quotes, root)).RootElement.EnumerateArray())
            sb.Append(q.GetString()).Append(" ¦ ");
        return Plain(sb.ToString());
    });

    /// <summary>Every passage a mark's tooltip quotes is the law's words character for character, and is a whole
    /// sentence or says it is cut short: it ends with a full stop (or ? or !) of the law's own, or with "…" (review
    /// rounds 1 and 2: §325-26 quoted to "average water level" left out its exception; a cut quote now must say so).</summary>
    [Fact]
    public void Every_passage_a_mark_quotes_is_the_laws_words_exactly_and_whole_or_marked_cut()
    {
        var quoted = Marks.All.SelectMany(m => System.Text.RegularExpressions.Regex.Matches(m.Description, "\"([^\"]{12,})\"")
            .Select(q => (m.Name, Text: q.Groups[1].Value))).ToList();
        Assert.True(quoted.Count >= 12);
        foreach (var (name, text) in quoted)
        {
            var cut = text.EndsWith('…');
            var words = Plain(cut ? text[..^1] : text);
            Assert.True(Law.Value.Contains(words, StringComparison.Ordinal), $"{name} quotes words not in the law: \"{text}\"");
            Assert.True(cut || words.EndsWith('.') || words.EndsWith('?') || words.EndsWith('!'),
                        $"{name} quotes part of a sentence without saying so (end it with …): \"{text}\"");
            // a whole sentence ends where the law's does: its full stop is the law's own (". " or the passage's end)
            if (!cut)
                Assert.True(Law.Value.Contains(words + " ", StringComparison.Ordinal), $"{name}: \"{text}\" isn't followed in the law by a new sentence");
        }
        foreach (var m in new[] { Marks.StreamNearLot, Marks.StreamDistance })
            Assert.Contains("measured at an average water level, except for those structures directly connected with marine or public or commercial recreation activities.\"",
                            m.Description, StringComparison.Ordinal);
    }

    // ---- the house's fix cards now have their button -----------------------------------------------------------

    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static CheckResult House()
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "ithaca_106_house_check_answer.json");
        var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
        return CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About));
    }

    /// <summary>106 Ithaca Rd as Revit read it: the stream's, the household's and the garage's cards had "No Gordium
    /// mark is named for this"; each now opens Project Information on the marks that answer it.</summary>
    [Fact]
    public void The_houses_fix_cards_for_these_facts_open_project_information_on_their_marks()
    {
        var cards = ResultRows.Build(House(), null, [], null).Causes;
        var expected = new Dictionary<string, MarkDefinition[]>
        {
            ["facts:stream_distance,stream_near_lot"] = [Marks.StreamNearLot, Marks.StreamDistance],
            ["facts:accessory_dwelling_unit,functional_family_unit,owner_occupied,unrelated_persons"] =
                [Marks.AccessoryDwellingUnit, Marks.UnrelatedPersons, Marks.OwnerOccupied, Marks.FunctionalFamilyUnit],
            ["facts:garage_cars"] = [Marks.GarageCars],
        };
        foreach (var (key, marks) in expected)
        {
            var card = Assert.Single(cards, c => c.Key == key);
            Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
            Assert.Equal(marks.OrderBy(m => Marks.All.ToList().IndexOf(m)), CauseCards.MarksOf(card));
            var note = CauseCards.Note(card, null)!;
            Assert.StartsWith("Set Gordium: ", note, StringComparison.Ordinal);
            Assert.DoesNotContain("No Gordium mark", note, StringComparison.Ordinal);
        }
        // no Project Information fact the worker asks of the house is left without a field
        Assert.DoesNotContain(cards, c => c.Kind == CauseKind.Mark && c.Fields.Any(f => f.StartsWith("facts.", StringComparison.Ordinal))
                                          && CauseCards.MarksOf(c).Count == 0 && c.Key != "fact:stair_nosings_under_floor_opening");
    }

    /// <summary>The private garages are asked only once the cars are over three (host_core.facts.ROW_ONLY_FACTS): its
    /// card, when the worker sends it, finds its field too.</summary>
    [Fact]
    public void The_private_garages_card_finds_its_field()
    {
        var card = new CauseCard("facts:private_garages", CauseKind.Mark, "Enter the private garages on the lot", [], ["r"], null, "review")
        {
            Fields = ["facts.private_garages"],
        };
        Assert.Equal([Marks.PrivateGarages], CauseCards.MarksOf(card));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
    }
}
