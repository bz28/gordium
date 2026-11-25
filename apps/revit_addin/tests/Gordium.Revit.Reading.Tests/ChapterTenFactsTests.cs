using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>What the 2025 Building Code of New York State's Chapter 10 egress rules read of the whole building
/// (design_checker/code_scope.py FACTS) that no drawing shows: fixed assembly seating, special egress spaces,
/// merchandise pads, the egress balcony increase and an atrium. Each is a Yes/No on Project Information, sent in the
/// interior description's <c>building</c> block only when set (blank is not stated, so every rule that reads it needs
/// review, never read as No); one holding neither Yes nor No is asked again; the Setup form lists each; the worker's
/// cards for them open Project Information on their mark.</summary>
public sealed class ChapterTenFactsTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly (MarkDefinition Mark, string Key)[] Each =
    [
        (Marks.AssemblyFixedSeating, "assembly_fixed_seating"), (Marks.SpecialEgressSpaces, "special_egress_spaces"),
        (Marks.MerchandisePads, "merchandise_pads"), (Marks.EgressBalconyIncrease, "egress_balcony_increase_taken"),
        (Marks.Atrium, "building_has_atrium"),
    ];

    public static TheoryData<string> Keys => [.. Each.Select(e => e.Key)];

    /// <summary>Every Yes/No building mark BuildingFacts reads: the five above and the four the code choice reads
    /// (review round 1: a value neither Yes nor No on the older four was dropped as not stated before this branch).</summary>
    private static readonly (MarkDefinition Mark, string Key)[] EveryYesNo =
    [
        .. Each, (Marks.FollowsBuildingCode, "follows_building_code"), (Marks.SeparateMeansOfEgress, "separate_means_of_egress"),
        (Marks.TownhouseUnits, "townhouse_units"), (Marks.CareFacility, "care_facility"),
    ];

    public static TheoryData<string> EveryYesNoKey => [.. EveryYesNo.Select(e => e.Key)];

    private static RevitModel Model(Dictionary<Guid, MarkValue> marks) => new() { Document = "b.rvt", ProjectMarks = marks };

    [Fact]
    public void Each_is_a_yes_no_project_information_mark_feeding_its_building_fact()
    {
        foreach (var (m, key) in Each)
        {
            Assert.Contains(m, Marks.All);                                    // MarkSetup adds it; the Setup form lists it
            Assert.Equal([Marks.ProjectInformation], m.Categories);
            Assert.Equal((MarkValueKind.YesNo, MarkBinding.Instance), (m.Kind, m.Binding));
            Assert.Equal("building." + key, m.Feeds);                          // the field the worker's card names
            // what each answer does, said before it is ticked: blank is never No
            Assert.Contains("Yes:", m.Description, StringComparison.Ordinal);
            Assert.Contains("No:", m.Description, StringComparison.Ordinal);
            Assert.Contains("Blank: the rules that turn on it need review.", m.Description, StringComparison.Ordinal);
        }
        // the law's own words (each checked character for character by HouseFactFieldsTests' quote test)
        Assert.Contains("\"c. For a room or space used for assembly purposes having fixed seating, see Section 1030.8.\"",
                        Marks.AssemblyFixedSeating.Description, StringComparison.Ordinal);
        Assert.Contains("from any point in the merchandise pad.\"", Marks.MerchandisePads.Description, StringComparison.Ordinal);
        Assert.Contains("that occurs within the atrium shall be not greater than 200 feet (60 960 mm).\"", Marks.Atrium.Description, StringComparison.Ordinal);
        Assert.Contains("in the uses described in Sections 1006.2.2.1 through 1006.2.2.6.\"", Marks.SpecialEgressSpaces.Description, StringComparison.Ordinal);
        // each section named for what it says (review round 1: 1030.7's aisle measuring was credited to 1030.8)
        Assert.Contains("1030.7 measures its travel along the aisles, never over or on the seats; 1030.8 limits its common path from any seat",
                        Marks.AssemblyFixedSeating.Description, StringComparison.Ordinal);
    }

    [Fact]
    public void Each_set_is_sent_as_the_architect_ticked_it()
    {
        var marks = new Dictionary<Guid, MarkValue>();
        for (var i = 0; i < Each.Length; i++)
            marks[Each[i].Mark.Guid] = new(true, i % 2);                        // No, Yes, No, Yes, No
        var read = BuildingFacts.Read(Model(marks));
        Assert.Empty(read.Missing);
        Assert.Empty(read.NotRead);
        Assert.Equal("{\"assembly_fixed_seating\":false,\"special_egress_spaces\":true,\"merchandise_pads\":false," +
                     "\"egress_balcony_increase_taken\":true,\"building_has_atrium\":false}", read.Building!.ToJsonString());
    }

    /// <summary>The one that could turn "needs review" into a pass: a blank mark (absent, or Revit's unset parameter,
    /// whose AsInteger() is 0) is never sent, so never read as No.</summary>
    [Theory]
    [MemberData(nameof(Keys))]
    public void A_blank_mark_is_not_stated_never_sent_as_no(string key)
    {
        var (mark, _) = Each.Single(e => e.Key == key);
        foreach (var blank in new MarkValue?[] { null, new(false, 0), new(false), new(false, Text: "") })
        {
            var marks = new Dictionary<Guid, MarkValue>();
            if (blank is { } b)
                marks[mark.Guid] = b;
            var read = BuildingFacts.Read(Model(marks));
            Assert.Null(read.Building);                                        // nothing else set: no block at all
            Assert.Empty(read.Missing);
            marks[Marks.SprinklerSystem.Guid] = new(true, Text: "None");       // a block sent for another fact
            Assert.False(BuildingFacts.Read(Model(marks)).Building!.ContainsKey(key));
            var field = SetupScreen.Build(Model(marks), [], null, null).Fields.Single(f => f.Mark == mark);
            Assert.Null(field.Current);                                        // the form shows it not stated
            Assert.False(field.IsSet);
            Assert.Null(field.Problem);
        }
    }

    /// <summary>A Yes/No building mark holding neither 1 nor 0 (set through the API) is asked again and never dropped
    /// as not stated: sent anyway, the value goes as held, so the code decision says it can't read it.</summary>
    [Theory]
    [MemberData(nameof(EveryYesNoKey))]
    public void A_mark_holding_neither_yes_nor_no_is_asked_again(string key)
    {
        var (mark, _) = EveryYesNo.Single(e => e.Key == key);
        Assert.Equal("building." + key, mark.Feeds);                           // the form's problem is for building facts
        var model = Model(new() { [mark.Guid] = new(true, 2) });
        var read = BuildingFacts.Read(model);
        Assert.Equal($"{mark.Name} holds a value that isn't Yes or No: tick Yes or No, or leave it blank on Project Information (Manage > Project Information).",
                     Assert.Single(read.Missing));
        Assert.Equal([mark], read.NotRead);
        Assert.Equal(2, read.Building![key]!.GetValue<int>());
        var screen = SetupScreen.Build(model, [], null, null);
        Assert.NotNull(screen.Fields.Single(f => f.Mark == mark).Problem);    // the form waits for it
        Assert.Contains(mark.Name, screen.Needed);
    }

    [Fact]
    public void The_setup_form_lists_each_under_building_code_optional()
    {
        var fields = SetupScreen.Build(Model([]), [], null, null).Fields;
        foreach (var (m, _) in Each)
        {
            var f = fields.Single(x => x.Mark == m);
            Assert.Equal((FieldKind.YesNo, SetupFacts.CodeGroup, false), (f.Kind, f.Group, f.Required));
            Assert.Equal(["Yes", "No"], f.Choices.Select(c => c.Value));
        }
        // the form writes one only when the architect chooses it
        var draft = new SetupDraft();
        Assert.Empty(draft.Writes(fields).Writes);
        draft.Choose(Marks.SpecialEgressSpaces, "No");
        var w = Assert.Single(draft.Writes(fields).Writes);
        Assert.Equal((Marks.SpecialEgressSpaces, 0), (w.Mark, w.Value.Integer!.Value));
    }

    [Theory]
    [MemberData(nameof(Keys))]
    public void The_workers_card_for_each_opens_project_information_on_its_mark(string key)
    {
        var (mark, _) = Each.Single(e => e.Key == key);
        var card = new CauseCard($"field:building.{key}", CauseKind.Mark, "Say whether", [], ["r"], null, "review")
        {
            Fields = [$"building.{key}"],
        };
        Assert.Equal([mark], CauseCards.MarksOf(card));
        Assert.Equal(CardAction.ProjectInformation, CauseCards.Action(card, null));
    }

    /// <summary>PR #181 review round 13: in the pane's "What to fix", an answer card says "Set on Project Information";
    /// on the four-unit apartment's real answer (regenerated from the checker) five of them asked for building facts no
    /// mark held. Every answer card for a building fact now has the mark that answers it, among them the
    /// Chapter 10 facts this answer asks.</summary>
    [Fact]
    public void Every_answer_card_for_a_building_fact_on_the_apartments_answer_has_its_mark()
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "four_unit_apartment_check_answer.json");
        var doc = JsonDocument.Parse(File.ReadAllText(file, System.Text.Encoding.UTF8));
        var about = new WorkerAbout("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());
        var model = ResultViews.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), about)));
        var fed = Marks.All.SelectMany(m => m.Feeds.Split(", ").Select(p => p.Split(' ')[0])).ToHashSet(StringComparer.Ordinal);
        var asked = model.Fix.Where(g => g.Kind == FixKind.Answer).SelectMany(g => g.Cards)
                         .Select(c => c.Field).OfType<string>().Where(f => f.StartsWith("building.", StringComparison.Ordinal))
                         .Distinct().ToList();
        Assert.Superset(new HashSet<string> { "building.assembly_fixed_seating", "building.special_egress_spaces",
                                              "building.egress_balcony_increase_taken" }, asked.ToHashSet());
        Assert.All(asked, f => Assert.Contains(f, fed));
    }

    /// <summary>End to end through the real worker: the ranch under the Building Code (Gordium: Follows the Building
    /// Code Yes, Group R-3, no sprinkler system), blank then each mark No. Blank, the atrium's and balcony's rules need
    /// review; No, they are not applicable. Ticked Yes, they need review again: never a pass on Yes or blank.</summary>
    [Fact]
    public async Task Stated_no_the_rules_that_read_them_move_and_blank_or_yes_they_need_review()
    {
        var house = FakeHouse.Draw("1_ranch_compliant");
        var outside = ProjectCheckTests.Outside(house.Model());
        foreach (var (m, v) in new (MarkDefinition, MarkValue)[]
                 {
                     (Marks.Zone, new(true, Text: "R-1b")), (Marks.Use, new(true, Text: "one_family_detached")),
                     (Marks.LotSurveyed, new(true, 1)), (Marks.CornerLot, new(true, 0)), (Marks.GroundFrom, new(true, Text: "Spot grades")),
                     (Marks.StreetEdge, new(true, Text: ProjectCheckTests.SouthEdge(outside))),
                     (Marks.FollowsBuildingCode, new(true, 1)), (Marks.OccupancyGroups, new(true, Text: "R-3")),
                     (Marks.SprinklerSystem, new(true, Text: "None")),
                 })
            house.ProjectMarks[m.Guid] = v;
        var client = await worker.RunningAsync();

        async Task<Dictionary<string, string>> Results()
        {
            var prepared = await ProjectCheck.PrepareAsync(outside, house.Model(), new WorkerLeftOut(client));
            Assert.Empty(prepared.Missing);
            var raw = (await ProjectCheck.SendAsync(client, prepared.Request!)).Raw;
            Assert.Equal("building_code", raw.GetProperty("which_code").GetProperty("code").GetString());
            var got = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (var item in raw.GetProperty("view").GetProperty("items").EnumerateArray())
                if (item.TryGetProperty("rule", out var r) && r.ValueKind == JsonValueKind.String)
                    got[r.GetString()!] = item.GetProperty("status").GetString()!;
            return got;
        }

        string[] rules = ["general.bc_1017_3_2_3_atrium", "general.bc_1017_2_1_balcony_increase"];
        var blank = await Results();
        Assert.All(rules, r => Assert.Equal("needs_review", blank[r]));
        foreach (var (m, _) in Each)
            house.ProjectMarks[m.Guid] = new(true, 0);
        var no = await Results();
        Assert.All(rules, r => Assert.Equal("not_applicable", no[r]));
        foreach (var (m, _) in Each)
            house.ProjectMarks[m.Guid] = new(true, 1);
        var yes = await Results();
        Assert.All(rules, r => Assert.Equal("needs_review", yes[r]));
        // never a pass that blank didn't give
        Assert.DoesNotContain(yes, kv => kv.Value == "complies" && blank.GetValueOrDefault(kv.Key) != "complies");
    }
}
