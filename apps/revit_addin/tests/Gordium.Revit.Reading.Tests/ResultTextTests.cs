using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>"Check my project"'s words (reading design note, section 9): nothing shown kinder than the worker said.
/// The headline is the worker's state and summary; every failure, every row that needs review and every status word
/// the add-in doesn't know is shown in full, never cut; a row is shown as complying only when it does.</summary>
public sealed class ResultTextTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly WorkerAbout About = new("1.2", "gordium.site/1", new string('f', 64),
                                                    new Dictionary<string, string> { ["new_york/ithaca_city"] = new('a', 64) });

    private static CheckResult Answer(JsonObject view) =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(new JsonObject { ["view"] = view, ["report_error"] = null }.ToJsonString()).RootElement, About));

    private static JsonObject Row(string id, string status, string? reason = null, string? proposed = null) => new()
    {
        ["id"] = id, ["name"] = "Row " + id, ["group"] = "building", ["status"] = status, ["reason"] = reason,
        ["proposed"] = proposed ?? "", ["required"] = proposed is null ? "" : "25'-0\"", ["sign"] = proposed is null ? "" : "≥",
        ["objects"] = new JsonArray("uid-" + id),
    };

    /// <summary>200 rows: 100 comply, 40 need review, 30 fail, 10 with a status word the add-in doesn't know, 10 not
    /// checked, 10 not applicable; the worker's groups put the unknown words with what complies (a later worker's
    /// grouping may), so only each row's own verdict can keep them from reading as a pass.</summary>
    private static (JsonObject View, List<JsonObject> Rows) TwoHundred(string state)
    {
        var rows = new List<JsonObject>();
        void Add(string kind, int n, Func<int, JsonObject> make) { for (var i = 0; i < n; i++) rows.Add(make(i)); }
        Add("c", 100, i => Row($"c{i}", "complies", proposed: "30'-0\""));
        Add("r", 40, i => Row($"r{i}", "needs_review", reason: $"say whether {i}"));
        Add("f", 30, i => Row($"f{i}", "does_not_comply", proposed: "20'-0\""));
        Add("u", 10, i => Row($"u{i}", "maybe_later"));
        Add("n", 10, i => Row($"n{i}", "not_checked", reason: "not in this release"));
        Add("a", 10, i => Row($"a{i}", "not_applicable", reason: "Not applicable: the house has no ramps (A-2)"));
        JsonObject Group(string key, string title, Func<JsonObject, bool> which) => new()
        {
            ["key"] = key, ["title"] = title,
            ["items"] = new JsonArray(rows.Where(which).Select(r => (JsonNode)r["id"]!.GetValue<string>()).ToArray()),
        };
        var s = (JsonObject r) => r["status"]!.GetValue<string>();
        var view = new JsonObject
        {
            ["items"] = new JsonArray(rows.Select(r => (JsonNode)r.DeepClone()).ToArray()),
            ["summary"] = "30 do not comply · 40 need review · 100 comply",
            ["state"] = state,
            ["groups"] = new JsonArray(
                Group("fails", "Does not comply", r => s(r) == "does_not_comply"),
                Group("review", "Needs review", r => s(r) == "needs_review"),
                Group("not_checked", "Not checked", r => s(r) == "not_checked"),
                Group("complies", "Complies", r => s(r) is "complies" or "maybe_later" or "not_applicable")),
        };
        return (view, rows);
    }

    private static List<string> Lines(ResultWords w) => w.Main.Split('\n').ToList();

    private static int CountOf(string s, string part) => (s.Length - s.Replace(part, "", StringComparison.Ordinal).Length) / part.Length;

    /// <summary>The Revit trial (Pacific sample): "Lot area per main building" gave one reason part per building,
    /// the same two twelve times. Said once each with the count; distinct parts all kept, in order.</summary>
    [Fact]
    public void A_reason_repeated_per_building_is_said_once_with_its_count()
    {
        var parts = Enumerable.Repeat("a building has a curved edge (not measured yet); a building has a curved surface (not measured yet)", 12);
        var reason = string.Join("; ", parts) + "; enter the stories";
        var view = new JsonObject
        {
            ["items"] = new JsonArray(Row("r0", "needs_review", reason: reason)),
            ["summary"] = "1 needs review", ["state"] = "needs_review",
            ["groups"] = new JsonArray(new JsonObject { ["key"] = "review", ["title"] = "Needs review", ["items"] = new JsonArray("r0") }),
        };
        Assert.Contains("- [needs review] Row r0: a building has a curved edge (not measured yet) (x12); a building has a curved " +
                        "surface (not measured yet) (x12); enter the stories [uid-r0]",
                        Lines(ResultText.Format(Answer(view), null, [], null)).Select(l => l.Trim()));
        Assert.Equal("a (x2); b", ResultText.Once("a; b; a"));
        Assert.Equal("no repeats; here", ResultText.Once("no repeats; here"));
    }

    [Fact]
    public void A_row_not_measured_says_what_is_allowed_and_why_never_a_dash_measured()
    {
        var view = new JsonObject
        {
            ["items"] = new JsonArray(
                new JsonObject { ["id"] = "y", ["name"] = "Front yard", ["group"] = "building", ["status"] = "needs_review",
                                 ["reason"] = "enter corner lot yes or no", ["proposed"] = "—", ["required"] = "25'-0\"", ["sign"] = "≥" },
                new JsonObject { ["id"] = "e", ["name"] = "Eaves into front yard", ["group"] = "building", ["status"] = "complies",
                                 ["reason"] = null, ["proposed"] = "24'-0\"", ["required"] = "≥ 23'-0\"", ["sign"] = "≥" }),
            ["summary"] = "1 needs review · 1 complies", ["state"] = "needs_review",
            ["groups"] = new JsonArray(new JsonObject { ["key"] = "review", ["title"] = "Needs review", ["items"] = new JsonArray("y", "e") }),
        };
        var lines = Lines(ResultText.Format(Answer(view), null, [], null)).Select(l => l.Trim()).ToList();
        Assert.Contains("- [needs review] Front yard: allowed 25'-0\". enter corner lot yes or no", lines);
        Assert.Contains("- [complies] Eaves into front yard: 24'-0\" measured, ≥ 23'-0\" allowed", lines);
    }

    [Fact]
    public void Two_hundred_rows_every_failure_and_doubt_shown_and_only_passes_cut()
    {
        var (view, rows) = TwoHundred("does_not_comply");
        var result = Answer(view);
        var words = ResultText.Format(result, "New Construction", ["Porch: Deep"], null, id => "id " + id[4..], maxOtherRows: 25);
        Assert.Equal("Does not comply: 30 do not comply · 40 need review · 100 comply", words.Headline);
        Assert.Contains("the last phase, New Construction", words.Checked, StringComparison.Ordinal);
        Assert.Contains("Porch: Deep", words.Checked, StringComparison.Ordinal);
        var lines = Lines(words);
        foreach (var r in rows)
        {
            var id = r["id"]!.GetValue<string>();
            var shown = lines.Where(l => l.Contains($"] Row {id}:", StringComparison.Ordinal) || l.EndsWith($"] Row {id} [id {id}]", StringComparison.Ordinal)).ToList();
            if (r["status"]!.GetValue<string>() is "complies" or "not_applicable")
                Assert.True(shown.Count <= 1);
            else
                Assert.Single(shown);                          // never cut
        }
        // shown as complying only what complies; the unknown word as needs review, with the worker's word
        Assert.All(lines.Where(l => l.Contains("[complies]", StringComparison.Ordinal)),
                   l => Assert.Matches(@"\] Row c\d+:", l));
        Assert.Equal(10, lines.Count(l => l.Contains("[needs review (the checker said \"maybe_later\")] Row u", StringComparison.Ordinal)));
        Assert.Equal(30, lines.Count(l => l.Contains("[DOES NOT COMPLY] Row f", StringComparison.Ordinal)));
        // measured against allowed, and the element
        Assert.Contains("- [DOES NOT COMPLY] Row f0: 20'-0\" measured, ≥ 25'-0\" allowed [id f0]", lines.Select(l => l.Trim()));
        // the groups are the worker's, in its order, with its counts; 25 passes shown, the other 85 said
        Assert.Equal(["Does not comply (30)", "Needs review (40)", "Not checked (10)", "Complies (120)"],
                     lines.Where(l => l.Length > 0 && !l.StartsWith(' ')));
        Assert.Equal(25, lines.Count(l => l.Contains("[complies]", StringComparison.Ordinal) || l.Contains("[not applicable]", StringComparison.Ordinal)));
        Assert.Contains("  85 more (in the log)", lines);
        // the dialog's first view: every heading with its count and every failure, nothing shown as passing
        var outline = words.Outline.Split('\n');
        Assert.Equal(["Does not comply (30)", "Needs review (40)", "Not checked (10)", "Complies (120)"], outline.Where(l => !l.StartsWith(' ')));
        Assert.Equal(30, outline.Count(l => l.StartsWith("  - [DOES NOT COMPLY] Row f", StringComparison.Ordinal)));
        Assert.Equal(34, outline.Length);
    }

    [Theory]
    [InlineData("needs_review", "Needs review: ")]
    [InlineData("not_checked", "Not checked: ")]
    [InlineData("a_word_not_known", "Needs review: ")]
    [InlineData("not_applicable", "Needs review: ")]
    public void The_headline_is_the_workers_state_never_a_pass_it_didnt_say(string state, string head)
    {
        var (view, _) = TwoHundred(state);
        Assert.StartsWith(head, ResultText.Format(Answer(view), null, [], null).Headline, StringComparison.Ordinal);
    }

    [Fact]
    public void A_check_that_complies_says_so_and_the_rows_that_dont_apply_say_why()
    {
        var view = new JsonObject
        {
            ["items"] = new JsonArray(Row("c0", "complies", proposed: "30'-0\""), Row("a0", "not_applicable", reason: "Not applicable: no ramps (A-2)")),
            ["summary"] = "1 complies", ["state"] = "complies",
            ["groups"] = new JsonArray(new JsonObject { ["key"] = "complies", ["title"] = "Complies", ["items"] = new JsonArray("c0", "a0") }),
        };
        var words = ResultText.Format(Answer(view), null, [], null);
        Assert.Equal("Complies: 1 complies", words.Headline);
        Assert.Contains("[not applicable] Row a0: Not applicable: no ramps (A-2) [uid-a0]", words.Main, StringComparison.Ordinal);
        Assert.Contains("the model (it has no phases)", words.Checked, StringComparison.Ordinal);
    }

    [Fact]
    public void A_not_applicable_with_no_reason_is_needs_review_and_never_cut()
    {
        var view = new JsonObject
        {
            ["items"] = new JsonArray(Row("c0", "complies", proposed: "30'-0\""), Row("a0", "not_applicable")),
            ["summary"] = "1 complies", ["state"] = "needs_review",
            ["groups"] = new JsonArray(new JsonObject { ["key"] = "complies", ["title"] = "Complies", ["items"] = new JsonArray("c0", "a0") }),
        };
        var words = ResultText.Format(Answer(view), null, [], null, maxOtherRows: 0);
        Assert.Contains("[needs review] Row a0 [uid-a0]", words.Main, StringComparison.Ordinal);
        Assert.Contains("  1 more (in the log)", Lines(words));
    }

    /// <summary>A real answer: the box house with the basement house inside (ProjectCheckTests), as the dialog shows it.</summary>
    [Fact]
    public async Task A_real_answer_shows_the_egress_failure_with_its_figures_and_element()
    {
        var h = FakeHouse.Draw("5_basement_window_well");
        var scene = SceneDrawing.Named("01_box_house");
        var outside = scene.Model(scene.Steps[0]) with { Phases = h.Model().Phases };
        var edge = outside.LotLines[0].Curves.Single(c => Math.Abs(c.Start.Y) < 1e-9 && Math.Abs(c.End.Y) < 1e-9);
        h.ProjectMarks[Marks.Zone.Guid] = new(true, Text: "R-1b");
        h.ProjectMarks[Marks.Use.Guid] = new(true, Text: "one_family_detached");
        h.ProjectMarks[Marks.LotSurveyed.Guid] = new(true, 1);
        h.ProjectMarks[Marks.StreetEdge.Guid] = new(true, Text: StreetEdges.Format([(edge.Start, edge.End)]));
        var client = await worker.RunningAsync();
        var prepared = await ProjectCheck.PrepareAsync(outside, h.Model(), new WorkerLeftOut(client));
        var result = await ProjectCheck.SendAsync(client, prepared.Request!);
        var words = ResultText.Format(result, "phase 2", prepared.OptionsChecked, prepared.Inside, maxOtherRows: 5);

        Assert.Equal($"{ResultText.StateWords(result.State)}: {result.Summary}", words.Headline);
        Assert.StartsWith("Does not comply: ", words.Headline, StringComparison.Ordinal);
        var fail = result.Items.First(i => i.Status == Verdict.DoesNotComply && i.Id.Contains("r319_2_1", StringComparison.Ordinal));
        var line = Assert.Single(Lines(words), l => l.Contains("[DOES NOT COMPLY] " + fail.Name, StringComparison.Ordinal));
        // its figures, in the reason, the part it starts with said once (the row's name says it)
        var part = fail.Name.Split(" · ")[0];
        Assert.StartsWith(part + ": ", fail.Reason, StringComparison.Ordinal);
        Assert.Contains(": " + fail.Reason![(part.Length + 2)..] + " [", line, StringComparison.Ordinal);
        Assert.Equal(1, CountOf(line, part));
        Assert.EndsWith($"[{fail.Raw.GetProperty("part").GetProperty("id").GetString()}]", line, StringComparison.Ordinal);
        foreach (var i in result.Items.Where(i => !ResultText.MayCut(i)))
            Assert.Contains("] " + i.Name, words.Main, StringComparison.Ordinal);                 // never cut
        foreach (var g in result.Groups)
            Assert.Contains($"{g.Title} ({g.Count})", Lines(words));
        // the inside's not-read lists, each reason in full
        foreach (var why in prepared.Inside!.StairsNotRead.Concat(prepared.Inside.GuardsNotRead))
            Assert.Contains(why, words.Inside, StringComparison.Ordinal);
    }
}
