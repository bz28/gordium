using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The results panel's rows (ResultRows), the one model the panel and the text file both read: the worker's
/// state, counts and groups, never recounted; every row in one group, never cut; how far off only in the worker's
/// own words; the law's section and exact words from the answer itself.</summary>
public sealed class ResultRowsTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly WorkerAbout About = new("1.2", "gordium.site/1", new string('f', 64),
                                                    new Dictionary<string, string> { ["new_york/ithaca_city"] = new('a', 64) });

    private static CheckResult Answer(JsonObject view) =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(new JsonObject { ["view"] = view.DeepClone(), ["report_error"] = null }.ToJsonString()).RootElement, About));

    private static JsonObject View(JsonArray items, JsonArray groups, string state = "needs_review", string summary = "s") => new()
    {
        ["items"] = items.DeepClone(), ["summary"] = summary, ["state"] = state, ["groups"] = groups.DeepClone(),
    };

    private static JsonObject Group(string key, string title, params string[] ids) => new()
    {
        ["key"] = key, ["title"] = title, ["items"] = new JsonArray(ids.Select(i => (JsonNode)i).ToArray()),
    };

    /// <summary>A zoning row as the worker sends it (present.py): its figures, margin, delta, citation and quotes.</summary>
    private static JsonObject Zoning(string id, string status, string? delta, string margin = "−2'-6\"", string? reason = null) => new()
    {
        ["id"] = id, ["name"] = "Front yard", ["group"] = "building", ["status"] = status, ["reason"] = reason,
        ["proposed"] = "22'-6\"", ["required"] = "25'-0\"", ["sign"] = "≥", ["margin"] = margin, ["delta"] = delta,
        ["objects"] = new JsonArray("uid-house"),
        ["detail"] = new JsonObject
        {
            ["citation"] = "§325-8, District Regulations Chart, R-1b, Front yard column",
            ["quotes"] = new JsonArray(new JsonObject { ["text"] = "Minimum Front Yard · R-1B: 25 ft", ["where"] = "City of Ithaca Zoning Charts (April 2026), p.3, line 40" }),
        },
    };

    /// <summary>An egress row as the worker sends it (egress._decorated): no figures but its reason's, its section.</summary>
    private static JsonObject Egress(string id, string status, string reason) => new()
    {
        ["id"] = id, ["name"] = "Bedroom 1 › Window 2 · Escape opening minimum net clear height (R319.2.2)", ["group"] = "law",
        ["status"] = status, ["reason"] = "Bedroom 1 › Window 2: " + reason, ["proposed"] = "", ["required"] = "", ["margin"] = "",
        ["sign"] = "", ["objects"] = new JsonArray(),
        ["part"] = new JsonObject { ["part"] = "emergency_escape_opening", ["id"] = "uid-w2", ["name"] = "Window 2", ["within"] = null },
        ["code"] = new JsonObject { ["section"] = "R319.2.2", ["quote"] = "The minimum net clear opening height dimension shall be 24 inches (610 mm)." },
        ["detail"] = new JsonObject
        {
            ["citation"] = "R319.2.2, 2025 Residential Code of New York State (RCNYS), PDF p.102",
            ["quotes"] = new JsonArray(new JsonObject
            {
                ["text"] = "The minimum net clear opening height dimension shall be 24 inches (610 mm).",
                ["where"] = "R319.2.2, 2025 Residential Code of New York State (RCNYS), PDF p.102",
            }),
        },
    };

    private static ResultRow One(JsonObject item)
    {
        var id = item["id"]!.GetValue<string>();
        return ResultRows.Row(Answer(View(new JsonArray(item.DeepClone()), new JsonArray(Group("g", "G", id)))).Items[0]);
    }

    [Fact]
    public void A_zoning_row_says_its_figures_how_far_in_the_workers_delta_its_citation_and_quotes()
    {
        var row = One(Zoning("y", "does_not_comply", "2'-6\" short"));
        Assert.Equal("22'-6\" measured, ≥ 25'-0\" allowed", row.Figures);
        Assert.Equal("2'-6\" short", row.HowFar);                        // the worker's delta, never its bare margin
        Assert.Equal("§325-8, District Regulations Chart, R-1b, Front yard column", row.Section);
        var q = Assert.Single(row.Quotes);
        Assert.Equal("Minimum Front Yard · R-1B: 25 ft", q.Text);
        Assert.Equal("City of Ithaca Zoning Charts (April 2026), p.3, line 40", q.Where);
        Assert.Equal(["uid-house"], row.Elements);
        Assert.Equal(Tone.Fails, row.Tone);
        Assert.Equal("[DOES NOT COMPLY] Front yard: 22'-6\" measured, ≥ 25'-0\" allowed (2'-6\" short) [uid-house]", row.Line());
    }

    /// <summary>A row decided on a value the architect states (the worker's <c>stated</c>: the Gordium: Stories count)
    /// says "stated by the architect", never "measured"; one with no such flag is measured, as before.</summary>
    [Fact]
    public void A_stated_figure_is_shown_as_stated_never_as_measured()
    {
        var item = Zoning("R-1b.stories", "complies", "at limit", "at limit",
                          "3 stated by the architect for the whole building, within what the drawing allows (1 to 5)");
        item["name"] = "Stories";
        item["proposed"] = "3";
        item["required"] = "3";
        item["sign"] = "≤";
        item["stated"] = true;
        var row = One(item);
        Assert.Equal("3 stated by the architect, ≤ 3 allowed", row.Figures);
        Assert.Contains("within what the drawing allows (1 to 5)", row.Line(), StringComparison.Ordinal);
        item["stated"] = false;
        Assert.Equal("3 measured, ≤ 3 allowed", One(item).Figures);
    }

    /// <summary>A delta the worker left empty (settle: a row with no reading set) says nothing of how far, even with a
    /// margin as drawn beside it: the margin alone could be kinder than the readings. A worker that sends no delta
    /// at all: its margin.</summary>
    [Fact]
    public void An_empty_delta_says_nothing_and_only_a_worker_with_no_delta_has_its_margin_shown()
    {
        Assert.Null(One(Zoning("y", "needs_review", "", margin: "+1'-0\"")).HowFar);
        var old = Zoning("y", "does_not_comply", null);
        old.Remove("delta");
        Assert.Equal("−2'-6\"", One(old).HowFar);
        Assert.Equal("−2'-6\"", One(Zoning("y", "does_not_comply", null)).HowFar);   // delta null: as absent
    }

    [Fact]
    public void An_egress_row_shows_the_figures_its_reason_states_never_a_margin_worked_out()
    {
        var row = One(Egress("e", "does_not_comply", "net clear height 20 in, needs ≥ 24 in"));
        Assert.Equal("net clear height 20 in, needs ≥ 24 in", row.Figures);
        Assert.Null(row.HowFar);                                            // never "4 in short", made here
        Assert.True(row.ReasonIsFigures);
        Assert.Equal("R319.2.2", row.Section);
        Assert.StartsWith("The minimum net clear opening height", Assert.Single(row.Quotes).Text, StringComparison.Ordinal);
        Assert.Equal(["uid-w2"], row.Elements);
        // the text file says the figures once, as before
        Assert.Equal("[DOES NOT COMPLY] Bedroom 1 › Window 2 · Escape opening minimum net clear height (R319.2.2): " +
                     "net clear height 20 in, needs ≥ 24 in [uid-w2]", row.Line());

        var two = One(Egress("e", "does_not_comply", "sill height 46 in, needs ≤ 44 in; net clear area 5.1 sq ft, needs ≥ 5.7 sq ft (approx)"));
        Assert.Equal("sill height 46 in, needs ≤ 44 in; net clear area 5.1 sq ft, needs ≥ 5.7 sq ft", two.Figures);
        Assert.False(two.ReasonIsFigures);                                  // the reason says more: shown too

        var none = One(Egress("e", "needs_review", "clear height not measured: the top of the threshold isn't given"));
        Assert.Null(none.Figures);
        Assert.Equal("clear height not measured: the top of the threshold isn't given", none.Reason);
    }

    [Fact]
    public void A_row_with_no_quotes_but_its_code_quote_shows_that_and_one_with_neither_shows_none()
    {
        var e = Egress("e", "needs_review", "x");
        e["detail"]!.AsObject().Remove("quotes");
        var q = Assert.Single(One(e).Quotes);
        Assert.Equal("R319.2.2", q.Where);
        e.Remove("code");
        Assert.Empty(One(e).Quotes);
        Assert.Equal("R319.2.2, 2025 Residential Code of New York State (RCNYS), PDF p.102", One(e).Section);
    }

    [Theory]
    [InlineData("maybe_later", "Reason", Tone.Review, "needs review (the checker said \"maybe_later\")")]
    [InlineData("not_applicable", "Not applicable: no ramps (A-2)", Tone.Neutral, "not applicable")]
    [InlineData("not_applicable", null, Tone.Review, "needs review")]
    [InlineData("not_checked", "not in this release", Tone.Review, "not checked")]
    [InlineData("complies", null, Tone.Complies, "complies")]
    public void A_rows_colour_is_never_kinder_than_its_verdict(string status, string? reason, Tone tone, string words)
    {
        var row = One(new JsonObject { ["id"] = "r", ["name"] = "R", ["group"] = "building", ["status"] = status, ["reason"] = reason });
        Assert.Equal(tone, row.Tone);
        Assert.Equal(words, row.VerdictWords);
    }

    /// <summary>200 rows, the worker's groups (a later worker folding its unknown words with what complies), its counts
    /// deliberately not the rows': the panel keeps the worker's order and numbers, and every row once.</summary>
    [Fact]
    public void Two_hundred_rows_all_shown_once_in_the_workers_groups_with_its_counts()
    {
        var items = new JsonArray();
        var ids = new Dictionary<string, List<string>> { ["f"] = [], ["r"] = [], ["c"] = [] };
        for (var i = 0; i < 200; i++)
        {
            var (status, g) = i switch
            {
                < 30 => ("does_not_comply", "f"), < 60 => (i % 2 == 0 ? "needs_review" : "not_checked", "r"),
                < 70 => ("maybe_later", "c"), < 80 => ("not_applicable", "c"), _ => ("complies", "c"),
            };
            items.Add(i < 15 ? Egress($"x{i}", status, $"net clear height {i} in, needs ≥ 24 in")
                             : new JsonObject { ["id"] = $"x{i}", ["name"] = $"Row {i}", ["group"] = "building", ["status"] = status,
                                                ["reason"] = status == "not_applicable" ? "Not applicable: no ramps" : null });
            ids[g].Add($"x{i}");
        }
        var groups = new JsonArray(Group("fails", "Does not comply", [.. ids["f"]]), Group("review", "Needs review", [.. ids["r"]]),
                                   Group("complies", "Complies", [.. ids["c"]]));
        groups[0]!["count"] = 7;                                            // the worker's number, whatever the rows
        var model = ResultRows.Build(Answer(View(items, groups, "does_not_comply", "30 do not comply · 30 to review · 120 comply")), null, [], null);

        Assert.Equal(["fails", "review", "complies"], model.Groups.Select(g => g.Key));
        Assert.Equal([7, 30, 140], model.Groups.Select(g => g.Count));
        Assert.Equal(200, model.Groups.SelectMany(g => g.AllRows).Select(r => r.Id).Distinct().Count());
        Assert.Equal(200, model.Groups.SelectMany(g => g.AllRows).Count());
        Assert.False(model.Groups[0].Folded);
        // the complies group holds unknown words: never folded, never green (CheckResult opens it)
        Assert.False(model.Groups[2].Folded);
        Assert.Equal(Tone.Review, model.Groups[2].Tone);
        Assert.Equal(Tone.Fails, model.Groups[0].Tone);
        Assert.Equal(10, model.Groups[2].Rows.Count(r => r.VerdictWords.StartsWith("needs review (the checker said", StringComparison.Ordinal)));
        Assert.Equal("Does not comply: 30 do not comply · 30 to review · 120 comply", model.Headline);
        Assert.Equal(15, model.Groups[0].Rows.Count(r => r.Figures is not null && r.HowFar is null));

        // the text file's every row is the panel's row, word for word (one source of the wording)
        var text = ResultText.Format(Answer(View(items, groups, "does_not_comply")), null, [], null, maxOtherRows: int.MaxValue);
        foreach (var r in model.Groups.SelectMany(g => g.AllRows))
            Assert.Contains("- " + r.Line() + "\n", text.Main + "\n", StringComparison.Ordinal);
    }

    [Fact]
    public void A_folded_complies_group_and_a_law_groups_lines_keep_the_workers_folding()
    {
        var items = new JsonArray(Zoning("y", "complies", "+1'-0\"", margin: "+1'-0\""), Egress("e", "complies", "net clear height 30 in, needs ≥ 24 in"));
        var law = Group("law:complies", "Egress · Complies", "e");
        law["lines"] = new JsonArray(new JsonObject { ["key"] = "w2", ["title"] = "Window 2: 1 complies", ["status"] = "complies", ["items"] = new JsonArray("e") });
        var model = ResultRows.Build(Answer(View(items, new JsonArray(Group("complies", "Complies", "y"), law), "complies", "2 comply")), null, [], null);
        Assert.True(model.Groups[0].Folded);
        Assert.Equal(Tone.Complies, model.Groups[0].Tone);
        var line = Assert.Single(model.Groups[1].Lines);
        Assert.True(line.Folded);
        Assert.Equal("Window 2: 1 complies", line.Title);
        Assert.Empty(model.Groups[1].Rows);
        Assert.Equal(["e"], model.Groups[1].AllRows.Select(r => r.Id));
    }

    [Fact]
    public void The_counts_are_the_workers_words_per_law_coloured_only_by_what_they_say()
    {
        var view = View(new JsonArray(Zoning("y", "does_not_comply", "1'-0\" short")), new JsonArray(Group("fails", "F", "y")), "does_not_comply",
                        "Zoning: 1 does not comply · Egress: 4 do not comply · 5 to review · 4 comply · 10 parts not read yet");
        view["sections"] = new JsonArray(
            new JsonObject { ["key"] = "zoning", ["title"] = "Zoning (City of Ithaca)", ["state"] = "does_not_comply", ["summary"] = "1 does not comply" },
            new JsonObject { ["key"] = "egress", ["title"] = "Egress (NY State Residential Code 2025)", ["state"] = "does_not_comply",
                             ["summary"] = "4 do not comply · 5 to review · 4 comply · 10 parts not read yet · 0 comply if confirmed" });
        var counts = ResultRows.Counts(Answer(view));
        Assert.Equal(["Zoning (City of Ithaca)", "Egress (NY State Residential Code 2025)"], counts.Select(c => c.Title));
        Assert.Equal([("1 does not comply", Tone.Fails)], counts[0].Chips.Select(c => (c.Words, c.Tone)));
        Assert.Equal([("4 do not comply", Tone.Fails), ("5 to review", Tone.Review), ("4 comply", Tone.Complies),
                      ("10 parts not read yet", Tone.Review), ("0 comply if confirmed", Tone.Review)],
                     counts[1].Chips.Select(c => (c.Words, c.Tone)));

        // a section that can't be read: the whole summary, its "Egress: 4 do not comply" still red
        view["sections"]![1]!.AsObject().Remove("summary");
        var whole = Assert.Single(ResultRows.Counts(Answer(view)));
        Assert.Null(whole.Title);
        Assert.Equal(Tone.Fails, whole.Chips.Single(c => c.Words == "Egress: 4 do not comply").Tone);
        Assert.Equal(Tone.Fails, whole.Chips.Single(c => c.Words == "Zoning: 1 does not comply").Tone);
    }

    /// <summary>Review round 1 (P1): after a check that complies, an edit to the model left the panel's green
    /// "Complies" up. Stale: no green anywhere (state, chips, groups, lines, rows), the words kept, why said.</summary>
    [Fact]
    public void Results_after_the_model_changed_are_greyed_with_no_green_anywhere_and_say_why()
    {
        var items = new JsonArray(Zoning("y", "complies", "+1'-0\"", margin: "+1'-0\""), Egress("e", "complies", "net clear height 30 in, needs ≥ 24 in"));
        var law = Group("law:complies", "Egress · Complies", "e");
        law["lines"] = new JsonArray(new JsonObject { ["key"] = "w2", ["title"] = "Window 2: 1 complies", ["status"] = "complies", ["items"] = new JsonArray("e") });
        var model = ResultRows.Build(Answer(View(items, new JsonArray(Group("complies", "Complies", "y"), law), "complies", "2 comply")), null, [], null);
        static IEnumerable<Tone> Tones(ResultModel m) =>
            new[] { m.StateTone }.Concat(m.Counts.SelectMany(c => c.Chips).Select(c => c.Tone))
                .Concat(m.Groups.Select(g => g.Tone)).Concat(m.Groups.SelectMany(g => g.Lines).Select(l => l.Tone))
                .Concat(m.Groups.SelectMany(g => g.AllRows).Select(r => r.Tone));
        Assert.All(Tones(model), t => Assert.Equal(Tone.Complies, t));          // as checked: green throughout
        Assert.Null(model.Stale);

        var stale = ResultRows.Stale(model, new DateTime(2026, 11, 20, 14, 32, 0));
        Assert.DoesNotContain(Tone.Complies, Tones(stale));
        Assert.Equal("The model changed since this check (14:32): click Check again", stale.Stale);
        Assert.Equal(model.Headline, stale.Headline);                           // the words kept
        Assert.Equal(model.Groups.SelectMany(g => g.AllRows).Select(r => r.Line()), stale.Groups.SelectMany(g => g.AllRows).Select(r => r.Line()));
        Assert.Equal(PanelPart.Stale, ResultRows.Layout(stale)[0]);
    }

    /// <summary>Only the check's own committed transactions (adding the marks, keeping the street edge) leave the
    /// results standing; any other change makes them stale, and so does any undo or redo, whatever its names
    /// (review round 2: Revit names an undo by the transaction undone, so undoing the street edge kept a green pass).</summary>
    [Fact]
    public void Any_change_but_the_checks_own_makes_the_results_stale()
    {
        Assert.False(ResultRows.ChangesTheCheck([ResultRows.MarksTransaction], committed: true));
        Assert.False(ResultRows.ChangesTheCheck([ResultRows.StreetTransaction, ResultRows.MarksTransaction], committed: true));
        Assert.True(ResultRows.ChangesTheCheck(["Move"], committed: true));
        Assert.True(ResultRows.ChangesTheCheck([ResultRows.StreetTransaction, "Modify element attributes"], committed: true));
        Assert.True(ResultRows.ChangesTheCheck([], committed: true));
        Assert.True(ResultRows.ChangesTheCheck(["Gordium: the request's marks"], committed: true));     // a fact changed: stale
        // undone or redone: stale, the check's own included
        Assert.True(ResultRows.ChangesTheCheck([ResultRows.StreetTransaction], committed: false));
        Assert.True(ResultRows.ChangesTheCheck([ResultRows.MarksTransaction], committed: false));
        Assert.True(ResultRows.ChangesTheCheck(["Move"], committed: false));
    }

    /// <summary>Review (Revit trial, P2): at the docked size the header filled the pane and no row showed. The
    /// groups come straight after the state and counts; the details (phase, options, street line) after the rows.</summary>
    [Fact]
    public void The_rows_come_straight_after_the_state_and_counts_and_the_details_after_them()
    {
        var model = ResultRows.Build(Answer(View(new JsonArray(Zoning("y", "does_not_comply", "1'-0\" short")), new JsonArray(Group("fails", "F", "y")),
                                                 "does_not_comply", "1 does not comply")), "Phase 2", ["Porch: Deep"], null, "the 60.0 ft lot edge");
        Assert.Equal([PanelPart.State, PanelPart.Counts, PanelPart.Groups, PanelPart.Details], ResultRows.Layout(model));
        Assert.Equal([PanelPart.State, PanelPart.Counts, PanelPart.Groups, PanelPart.Inside, PanelPart.Details],
                     ResultRows.Layout(model with { Inside = "Stairs not read from the model:" }));
    }

    [Fact]
    public void A_reason_repeated_per_building_is_said_once_with_its_count_in_the_panel_too()
    {
        var row = One(new JsonObject
        {
            ["id"] = "r", ["name"] = "Lot area", ["group"] = "site", ["status"] = "needs_review",
            ["reason"] = string.Join("; ", Enumerable.Repeat("a building has a curved edge (not measured yet)", 12)),
        });
        Assert.Equal("a building has a curved edge (not measured yet) (x12)", row.Reason);
    }

    /// <summary>A real answer (the box house with the basement house inside): the egress failure's figures, section
    /// and law; the zoning rows' how far is the worker's delta; every text-file row is the panel's.</summary>
    [Fact]
    public async Task A_real_answer_gives_each_row_its_figures_section_and_the_laws_words()
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
        var model = ResultRows.Build(result, "phase 2", prepared.OptionsChecked, prepared.Inside, prepared.Street);

        Assert.Equal(result.Groups.Select(g => (g.Key, g.Count)), model.Groups.Select(g => (g.Key, g.Count)));
        Assert.Equal(result.Items.Count, model.Groups.SelectMany(g => g.AllRows).Count());
        var height = model.Groups.SelectMany(g => g.AllRows).Single(r => r.Id.Contains("r319_2_2", StringComparison.Ordinal) && r.Verdict == Verdict.DoesNotComply);
        Assert.Equal("net clear height 20 in, needs ≥ 24 in", height.Figures);
        Assert.Null(height.HowFar);
        Assert.Equal("R319.2.2", height.Section);
        Assert.Contains(height.Quotes, q => q.Text.Contains("24 inches", StringComparison.Ordinal) && q.Where!.StartsWith("R319.2.2", StringComparison.Ordinal));
        Assert.NotEmpty(height.Elements);
        foreach (var item in result.Items.Where(i => i.Raw.TryGetProperty("delta", out var d) && d.ValueKind == JsonValueKind.String && d.GetString()!.Length > 0))
            Assert.Equal(item.Raw.GetProperty("delta").GetString(), ResultRows.Row(item).HowFar);
        Assert.Equal(2, model.Counts.Count);
        var text = ResultText.Format(result, "phase 2", prepared.OptionsChecked, prepared.Inside, maxOtherRows: int.MaxValue, street: prepared.Street);
        foreach (var r in model.Groups.SelectMany(g => g.AllRows))
            Assert.Contains("- " + r.Line() + "\n", text.Main + "\n", StringComparison.Ordinal);
        Assert.Equal(text.Headline, model.Headline);
        Assert.Equal(text.Checked, model.Checked);
    }
}
