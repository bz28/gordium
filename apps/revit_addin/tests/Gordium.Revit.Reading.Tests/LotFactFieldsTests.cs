using System.Globalization;
using System.Text;
using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The lot facts the worker's cards asked for with no mark to set ("Set on Project Information" had nothing
/// there): whether R-1 land abuts the lot (§325-19E), a conversion (§325-3B), the primary buildings and their use
/// (§325-3B, §325-8B(1)), the home occupation's floor areas (§325-3B (1)(f)), and an ADU's building, bedrooms and floor
/// areas (§325-28C). Each is a Project Information mark of the kind the worker asks for (host_core.facts.STATED_FACTS: a
/// yes/no, a count from its least, an area in square feet), sent only when set: a blank one is not stated, never No, 0
/// or an area of 0. An area is a new kind of mark, typed and shown in the project's area units as Revit's own dialogs
/// do, and held and sent in square feet, never rounded.</summary>
public sealed class LotFactFieldsTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly (MarkDefinition Mark, string Key, MarkValue Value, string Sent)[] Each =
    [
        (Marks.AbutsR1, "abuts_r1_district", new(true, 1), "true"),
        (Marks.Conversion, "conversion", new(true, 0), "false"),
        (Marks.PrimaryBuildings, "primary_buildings", new(true, 2), "2"),
        (Marks.PrimaryBuildingsSameUse, "primary_buildings_same_use", new(true, 1), "true"),
        (Marks.HomeOccupationArea, "home_occupation_area", new(true, Number: 500.4), "500.4"),
        (Marks.HomeOccupationUnitArea, "home_occupation_unit_area", new(true, Number: 2001.75), "2001.75"),
        (Marks.AduExistingBuilding, "adu_existing_building", new(true, 0), "false"),
        (Marks.AduBedrooms, "adu_bedrooms", new(true, 0), "0"),
        (Marks.AduFloorArea, "adu_floor_area", new(true, Number: 640), "640"),
        (Marks.MainBuildingFloorArea, "primary_floor_area", new(true, Number: 1600), "1600"),
    ];

    public static TheoryData<string> Keys => [.. Each.Select(e => e.Key)];

    private static RevitModel Model(Dictionary<Guid, MarkValue> marks, string areaUnits = "SquareFeet") =>
        new() { Document = "house.rvt", ProjectMarks = marks, AreaDisplayUnits = areaUnits };

    private static Dictionary<Guid, MarkValue> Needed() => new()
    {
        [Marks.Zone.Guid] = new(true, Text: "R-1b"), [Marks.Use.Guid] = new(true, Text: "one_family_detached"),
        [Marks.LotSurveyed.Guid] = new(true, 1), [Marks.StreetEdge.Guid] = new(true, Text: StreetEdges.Format([(new Xyz(0, 0, 0), new Xyz(60, 0, 0))])),
    };

    /// <summary>The worker's own list of the facts it asks the architect (host_core.facts.STATED_FACTS: kind) and their
    /// least (MINIMUM), read from the checker so the two never drift.</summary>
    private static readonly Lazy<Dictionary<string, (string Kind, int Least)>> Stated = new(() =>
    {
        const string Code = "import json, sys\n"
            + "from design_checker.host_core import facts\n"
            + "out = {k: [v[1], facts.MINIMUM.get(k, 0)] for k, v in facts.STATED_FACTS.items()}\n"
            + "sys.stdout.buffer.write(json.dumps(out).encode())\n";
        return JsonDocument.Parse(Env.RunCode(Code, Env.Repo)).RootElement.EnumerateObject()
            .ToDictionary(p => p.Name, p => (p.Value[0].GetString()!, p.Value[1].GetInt32()));
    });

    private static IEnumerable<string> FactsFed(MarkDefinition m) =>
        m.Feeds.Split(", ").Select(p => p.Split(' ')[0]).Where(p => p.StartsWith("facts.", StringComparison.Ordinal)).Select(p => p["facts.".Length..]);

    [Fact]
    public void Each_is_a_project_information_mark_of_the_kind_and_least_the_worker_asks_for()
    {
        Assert.Equal(Each.Select(e => e.Mark), ProjectFacts.HouseFactMarks.TakeLast(Each.Length).Select(h => h.Mark));
        foreach (var (m, key, _, _) in Each)
        {
            Assert.Contains(m, Marks.All);
            Assert.Equal([Marks.ProjectInformation], m.Categories);
            Assert.Equal("facts." + key, m.Feeds);
            Assert.Contains("Blank", m.Description, StringComparison.Ordinal);
            Assert.Contains("\"", m.Description, StringComparison.Ordinal);   // the law's own words (quote test checks each)
        }
        // every mark that feeds a fact the worker asks for is that fact's kind, from the same least (a class pin: an area
        // typed as a count, or a count from 0 where the law's least is 1, would be read wrongly)
        var kinds = new Dictionary<string, MarkValueKind>
        {
            ["yes_no"] = MarkValueKind.YesNo, ["count"] = MarkValueKind.Integer, ["area"] = MarkValueKind.Area, ["length"] = MarkValueKind.Length,
        };
        var checkedAny = 0;
        foreach (var m in Marks.All.Where(m => m.Categories.Contains(Marks.ProjectInformation)))
            foreach (var key in FactsFed(m).Where(Stated.Value.ContainsKey))
            {
                var (kind, least) = Stated.Value[key];
                Assert.True(kinds[kind] == m.Kind, $"{m.Name} is {m.Kind}; the worker asks {key} as {kind}");
                // never below the worker's least (the form or the reader would send what the check refuses); a mark may
                // be stricter (the dwelling units and stories: 1 or more)
                var house = ProjectFacts.HouseFactMarks.Where(h => h.Mark == m).Select(h => (int?)h.Least).FirstOrDefault();
                if (m.Kind == MarkValueKind.Integer)
                {
                    Assert.True(SetupFacts.Least(m) >= least, $"{m.Name}: the form takes {SetupFacts.Least(m)} or more; the worker's least for {key} is {least}");
                    Assert.True(house is null || house == SetupFacts.Least(m), $"{m.Name}: the reader's least {house} isn't the form's {SetupFacts.Least(m)}");
                }
                checkedAny++;
            }
        Assert.True(checkedAny >= 25, checkedAny.ToString(CultureInfo.InvariantCulture));
    }

    [Fact]
    public void Each_set_is_sent_under_its_key_as_the_architect_gave_it_an_area_in_square_feet_never_rounded()
    {
        var marks = Needed();
        foreach (var e in Each)
            marks[e.Mark.Guid] = e.Value;
        var read = ProjectFacts.Read(Model(marks));
        Assert.Empty(read.Missing);
        foreach (var (_, key, _, sent) in Each)
            Assert.Equal(sent, read.Facts[key]!.ToJsonString());
        Assert.Empty(SetupFacts.NotSent(Model(marks), read));
    }

    [Theory]
    [MemberData(nameof(Keys))]
    public void A_blank_field_is_not_stated_never_no_0_or_an_area_of_0(string key)
    {
        var (mark, _, _, _) = Each.Single(e => e.Key == key);
        foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false, Number: 0), new(false) })
        {
            var marks = Needed();
            if (blank is { } b)
                marks[mark.Guid] = b;
            var read = ProjectFacts.Read(Model(marks));
            Assert.False(read.Facts.ContainsKey(key));
            Assert.DoesNotContain(read.Missing, m => m.StartsWith(mark.Name, StringComparison.Ordinal));
            var field = SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == mark);
            Assert.Null(field.Current);
            Assert.False(field.IsSet);
        }
    }

    [Theory]
    [InlineData("primary_buildings", "zero", "is 0: type 1 or more")]
    [InlineData("adu_bedrooms", "minus", "is -1: type 0 or more")]
    [InlineData("home_occupation_area", "minus", "is -2.5 sq ft: type an area of 0 sq ft or more")]
    [InlineData("adu_floor_area", "text", "holds a value that isn't an area: type an area in square feet")]
    [InlineData("conversion", "two", "holds a value that isn't Yes or No")]
    public void A_value_gordium_cant_read_is_said_and_not_sent(string key, string how, string said)
    {
        var (mark, _, _, _) = Each.Single(e => e.Key == key);
        var marks = Needed();
        marks[mark.Guid] = how switch
        {
            "zero" => new MarkValue(true, 0),
            "minus" when mark.Kind == MarkValueKind.Area => new MarkValue(true, Number: -2.5),
            "minus" => new MarkValue(true, -1),
            "two" => new MarkValue(true, 2),
            _ => new MarkValue(true, Text: "big"),
        };
        var model = Model(marks);
        var read = ProjectFacts.Read(model);
        Assert.False(read.Facts.ContainsKey(key));
        Assert.StartsWith($"{mark.Name} {said}", Assert.Single(read.Missing), StringComparison.Ordinal);
        Assert.Equal([mark], SetupFacts.NotSent(model, read));
        var screen = SetupScreen.Build(model, [], null, null);
        Assert.NotNull(screen.Fields.Single(f => f.Mark == mark).Problem);
        Assert.Contains(mark.Name, screen.Needed);
    }

    /// <summary>An area field is in the project's area units, as Revit's dialogs are: labelled with the unit, shown in
    /// it, and a number typed there saved as the square feet Revit holds for it (30 m² is 322.917 sq ft, never 30 sq
    /// ft, which would pass a 500 sq ft limit an area of 500 m² fails); units Gordium doesn't read take square feet and
    /// say so.</summary>
    [Theory]
    [InlineData("SquareFeet", "sq ft", "450.5", 450.5)]
    [InlineData("autodesk.unit.unit:squareMeters-1.0.1", "m²", "30", 30 / 0.09290304)]
    [InlineData("autodesk.unit.unit:squareMillimeters-1.0.1", "mm²", "92903.04", 1.0)]
    [InlineData("autodesk.unit.unit:hectares-1.0.1", "sq ft", "450.5", 450.5)]
    public void An_area_is_typed_and_shown_in_the_projects_area_units_and_held_in_square_feet(string units, string symbol, string typed, double squareFeet)
    {
        var model = Model(Needed(), units);
        var field = SetupScreen.Build(model, [], null, null).Fields.Single(f => f.Mark == Marks.HomeOccupationArea);
        Assert.Equal(FieldKind.Feet, field.Kind);                        // the form's number box
        Assert.Equal($"Home occupation area ({symbol})", field.Label);
        Assert.Equal(units.Contains("hectares", StringComparison.Ordinal), field.Law.Contains("aren't ones Gordium reads: type square feet here", StringComparison.Ordinal));
        var draft = new SetupDraft();
        draft.Choose(Marks.HomeOccupationArea, typed);
        var w = Assert.Single(draft.Writes(SetupScreen.Build(model, [], null, null).Fields).Writes);
        Assert.Equal(squareFeet, w.Value.Number!.Value, 9);
        // read back as Revit holds it, the field shows what was typed
        var marks = Needed();
        marks[Marks.HomeOccupationArea.Guid] = w.Value;
        Assert.Equal(typed, SetupScreen.Build(Model(marks, units), [], null, null).Fields.Single(f => f.Mark == Marks.HomeOccupationArea).Current);
        Assert.Equal(w.Value.Number!.Value, ProjectFacts.Read(Model(marks, units)).Facts["home_occupation_area"]!.GetValue<double>());
        // an area that isn't one is said in its own words
        draft.Choose(Marks.HomeOccupationArea, "big");
        Assert.Contains($"isn't an area in {AreaUnits.Of(units).Words}", Assert.Single(draft.Writes(SetupScreen.Build(model, [], null, null).Fields).Problems), StringComparison.Ordinal);
    }

    /// <summary>Review round 1: the form shows the law as quoted, never in "the building's words" (§325-8B(1)'s "one
    /// family house" in a multiple dwelling's form), and an area left out is named with its area unit, never the length one.</summary>
    [Fact]
    public void The_laws_words_are_never_changed_and_an_area_is_said_in_its_own_unit()
    {
        foreach (var m in Marks.All)
            foreach (System.Text.RegularExpressions.Match q in System.Text.RegularExpressions.Regex.Matches(m.Description, "\"[^\"]+\""))
                Assert.Contains(q.Value, SetupWords.InBuildingWords(m.Description, "building"), StringComparison.Ordinal);
        var marks = Needed();
        marks[Marks.Use.Guid] = new(true, Text: "multiple_family");
        var law = SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == Marks.PrimaryBuildingsSameUse).Law;
        Assert.Contains("an area of 3,000 square feet is required for a one family house or a two-family house", law, StringComparison.Ordinal);
        Assert.Contains("(Gordium: Use)", law, StringComparison.Ordinal);
        Assert.DoesNotContain("one family building", law, StringComparison.Ordinal);
        Assert.Contains("home occupation area (m²)", SetupWords.NothingSent(StreetRefusal.None, [Marks.HomeOccupationArea], "house", "mm", "m²"), StringComparison.Ordinal);
        Assert.StartsWith("Home occupation area (m²):", SetupWords.SentWithout(Marks.HomeOccupationArea, "house", "mm", "m²"), StringComparison.Ordinal);
        Assert.Contains("(8)(b), its setbacks", Marks.AduExistingBuilding.Description, StringComparison.Ordinal);
    }

    [Fact]
    public void Each_sits_under_its_heading_of_the_setup_form()
    {
        var fields = SetupScreen.Build(Model(Needed()), [], null, null).Fields;
        foreach (var (m, key, _, _) in Each)
            Assert.Equal(key.StartsWith("adu_", StringComparison.Ordinal) || key.StartsWith("home_occupation", StringComparison.Ordinal) || key == "primary_floor_area"
                             ? SetupFacts.DwellingsGroup : SetupFacts.LotGroup, fields.Single(f => f.Mark == m).Group);
    }

    /// <summary>The cards that had nothing to set: on the four-unit apartment's real answer every "Set on Project
    /// Information" card (a facts. or building. field) now has the mark that answers it, these ten among them.</summary>
    [Fact]
    public void Every_answer_card_on_the_apartments_answer_has_its_mark()
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "four_unit_apartment_check_answer.json");
        var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
        var about = new WorkerAbout("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());
        var model = ResultViews.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), about)));
        var fed = Marks.All.SelectMany(m => m.Feeds.Split(", ").Select(p => p.Split(' ')[0])).ToHashSet(StringComparer.Ordinal);
        var asked = model.Fix.Where(g => g.Kind == FixKind.Answer).SelectMany(g => g.Cards).Select(c => c.Field).OfType<string>().Distinct().ToList();
        Assert.Superset(new HashSet<string> { "facts.abuts_r1_district", "facts.conversion", "facts.adu_bedrooms", "facts.home_occupation_area" }, asked.ToHashSet());
        Assert.All(asked, f => Assert.Contains(f, fed));
    }

    /// <summary>End to end through the real worker: the ranch in R-1b with a home occupation stated by its marks.
    /// §325-3B HOME OCCUPATION (1)(f): no more than 500 indoor square feet and 25% of the unit. Exactly 500 sq ft of a
    /// 2,000 sq ft unit complies; 500.4 sq ft (never rounded to 500) does not; blank needs review.</summary>
    [Fact]
    public async Task The_home_occupations_areas_reach_the_check_in_square_feet()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var outside = ProjectCheckTests.Outside(house.Model());
        foreach (var (m, v) in new (MarkDefinition, MarkValue)[]
                 {
                     (Marks.Zone, new(true, Text: "R-1b")), (Marks.Use, new(true, Text: "one_family_detached")),
                     (Marks.LotSurveyed, new(true, 1)), (Marks.CornerLot, new(true, 0)), (Marks.GroundFrom, new(true, Text: "Spot grades")),
                     (Marks.StreetEdge, new(true, Text: ProjectCheckTests.SouthEdge(outside))), (Marks.HomeOccupation, new(true, 1)),
                 })
            house.ProjectMarks[m.Guid] = v;
        var client = await worker.RunningAsync();

        async Task<string> Size()
        {
            var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client));
            Assert.Empty(prepared.Missing);
            var raw = (await ProjectCheck.SendAsync(client, prepared.Request!)).Raw;
            return raw.GetProperty("view").GetProperty("items").EnumerateArray()
                .Single(i => i.TryGetProperty("rule", out var r) && r.GetString() == "R-1b.home_occupation_size").GetProperty("status").GetString()!;
        }

        Assert.Equal("needs_review", await Size());
        house.ProjectMarks[Marks.HomeOccupationUnitArea.Guid] = new(true, Number: 2000);
        house.ProjectMarks[Marks.HomeOccupationArea.Guid] = new(true, Number: 500);
        Assert.Equal("complies", await Size());
        house.ProjectMarks[Marks.HomeOccupationArea.Guid] = new(true, Number: 500.4);
        Assert.Equal("does_not_comply", await Size());
    }
}
