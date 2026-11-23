using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>A result's detail (Details, PR 4 of docs/revit/ui_design_pass.md section 4): snapshots of every row's
/// detail on the box house's real answer and the Children's Odyssey's; every figure shown is one the worker sent;
/// what to do never makes a pass (a stale detail is never green and says so first; Check again is the last step of
/// anything not complying); the law's links are the worker's; elements by the names architects use.</summary>
public sealed class DetailTests(RealWorker worker) : IClassFixture<RealWorker>
{
    private static readonly WorkerAbout About = new("1.2", "gordium.site/1", new string('f', 64),
                                                    new Dictionary<string, string> { ["maine/maine_state"] = new('a', 64) });

    private static readonly string Here = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests");

    /// <summary>The Children's Odyssey's answer (answers/children_odyssey_check_answer.json, made by
    /// tools/evals/make_odyssey_answer.py from the add-in's read of the marked model).</summary>
    private static CheckResult Odyssey()
    {
        var doc = JsonDocument.Parse(File.ReadAllText(Path.Combine(Here, "answers", "children_odyssey_check_answer.json"), Encoding.UTF8));
        return CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result"), About));
    }

    /// <summary>The box house's real answer (the basement house inside), as ResultRowsTests checks it.</summary>
    private async Task<CheckResult> BoxHouse()
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
        return await ProjectCheck.SendAsync(client, prepared.Request!);
    }

    /// <summary>Every element a name, by first appearance ("Element 1"...), the last one left out (not in the model now).</summary>
    private static Dictionary<string, string> Labels(IReadOnlyList<ListRow> placed)
    {
        var uids = placed.SelectMany(p => p.Row.Elements).Distinct(StringComparer.Ordinal).ToList();
        return uids.Take(Math.Max(0, uids.Count - 1)).Select((u, i) => (u, i)).ToDictionary(x => x.u, x => $"Element {x.i + 1}");
    }

    /// <summary>Every row's detail, in the list's order (its position among all rows).</summary>
    private static List<(ListRow Row, ResultDetail Detail, JsonElement Raw)> All(CheckResult result, bool stale = false)
    {
        var model = ResultRows.Build(result, "New Construction", [], null);
        if (stale)
            model = ResultRows.Stale(model, new DateTime(2026, 11, 22, 14, 32, 0));
        var placed = ResultList.Place(model);
        var labels = Labels(placed);
        var entries = ResultList.Layout(placed, ListFilter.All, null, labels, stale, new HashSet<ListSection>(Enum.GetValues<ListSection>()));
        var (rows, _) = Details.Among(entries, "");
        var raw = result.Items.ToDictionary(i => i.Id, i => i.Raw, StringComparer.Ordinal);
        return rows.Select((r, i) => (r, Details.Of(r, i, rows.Count, labels, stale ? new DateTime(2026, 11, 22, 14, 32, 0) : null),
                                      raw[r.Row.Id])).ToList();
    }

    /// <summary>The snapshot of <paramref name="name"/>: every row's detail as text; GORDIUM_UPDATE_SNAPSHOTS=1 writes it.</summary>
    private static void Snapshot(string name, IEnumerable<ResultDetail> details)
    {
        var text = string.Join("\n\n", details.Select(d => d.Text())) + "\n";
        var file = Path.Combine(Here, "snapshots", name);
        if (Environment.GetEnvironmentVariable("GORDIUM_UPDATE_SNAPSHOTS") == "1")
            File.WriteAllText(file, text, new UTF8Encoding(false));
        Assert.True(File.Exists(file), $"no snapshot {file}: run with GORDIUM_UPDATE_SNAPSHOTS=1 and read it");
        Assert.Equal(File.ReadAllText(file, Encoding.UTF8).ReplaceLineEndings("\n"), text);
    }

    [Fact]
    public void Every_row_of_the_odyssey_answer_has_its_detail_as_snapshotted() =>
        Snapshot("children_odyssey_details.txt", All(Odyssey()).Select(x => x.Detail));

    [Fact]
    public async Task Every_row_of_the_box_house_has_its_detail_as_snapshotted() =>
        Snapshot("box_house_details.txt", All(await BoxHouse()).Select(x => x.Detail));

    private static readonly Regex Number = new(@"[0-9]+(?:[.,][0-9]+)*", RegexOptions.CultureInvariant);

    /// <summary>Every number a detail says (its reason, steps, figures, how far, the law's words and links, element
    /// names) is in the worker's item for the row, or in an element's name; a step's count of elements is the count of
    /// its elements in the model; the position is the row's place in the list. No figure is made in the add-in.</summary>
    private static void EveryFigureIsTheWorkers(List<(ListRow Row, ResultDetail Detail, JsonElement Raw)> all)
    {
        Assert.NotEmpty(all);
        for (var n = 0; n < all.Count; n++)
        {
            var (row, d, raw) = all[n];
            Assert.Equal($"{n + 1} of {all.Count}", d.Position);
            var sent = string.Join('\n', [raw.GetRawText(), Unescaped(raw), .. d.Elements.Select(e => e.Name)]);
            var said = new List<string?> { d.Why, d.HowFar, d.Name, d.Section };
            said.AddRange(d.Figures.SelectMany(f => new[] { f.What, f.Measured, f.Limit }));
            said.AddRange(d.Quotes.SelectMany(q => new[] { q.Text, q.Where }));
            said.AddRange(d.Links.SelectMany(l => new[] { l.Citation, l.Url }));
            foreach (var step in d.Steps)
            {
                var count = d.Elements.Count(e => e.InModel).ToString(System.Globalization.CultureInfo.InvariantCulture);
                said.Add(step.Action == DetailAction.ShowElements ? step.Words.Replace($"its {count} elements", "its elements", StringComparison.Ordinal) : step.Words);
            }
            foreach (var words in said.Where(w => w is not null))
                foreach (Match m in Number.Matches(words!))
                    Assert.True(sent.Contains(m.Value, StringComparison.Ordinal),
                                $"row {row.Row.Id}: \"{m.Value}\" in \"{words}\" is not the worker's");
        }
    }

    private static string Unescaped(JsonElement raw) => JsonSerializer.Serialize(raw, new JsonSerializerOptions
    {
        Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
    });

    [Fact]
    public void Every_figure_of_the_odyssey_details_is_one_the_worker_sent() => EveryFigureIsTheWorkers(All(Odyssey()));

    [Fact]
    public async Task Every_figure_of_the_box_house_details_is_one_the_worker_sent() => EveryFigureIsTheWorkers(All(await BoxHouse()));

    /// <summary>The check the figure test makes catches a figure the add-in made (a test of the test).</summary>
    [Fact]
    public void A_figure_made_in_the_add_in_is_caught()
    {
        var all = All(Odyssey());
        var at = all.FindIndex(x => x.Detail.Why is not null);
        all[at] = all[at] with { Detail = all[at].Detail with { HowFar = "9876.5 ft over" } };
        Assert.ThrowsAny<Xunit.Sdk.XunitException>(() => EveryFigureIsTheWorkers(all));
    }

    // ---- what to do, and never a false pass ------------------------------------------------------------------

    private static ResultRow Row(Verdict v, string? hint = null, string[]? elements = null, LawLink[]? links = null,
                                 string? reason = "the reason") =>
        new("r", "Front yard", v, v switch
        {
            Verdict.DoesNotComply => "DOES NOT COMPLY",
            Verdict.Complies => "complies",
            Verdict.NotChecked => "not checked",
            _ => "needs review",
        }, ResultRows.ToneOf(v, Verdicts.Word(v)), null, null, reason, "§325-8", [], elements ?? [])
        { Hint = hint, Links = links ?? [] };

    private static ListRow Placed(ResultRow r, bool byHand = false) =>
        new(r, ResultList.SectionOf(r.Verdict, byHand), StatusLook.Of(r.Tone, false), "s", "k", 1, false);

    [Fact]
    public void A_failure_says_the_workers_advice_first_and_ends_with_check_again()
    {
        var d = Details.Of(Placed(Row(Verdict.DoesNotComply, hint: "To comply: reduce the footprint by at least 213 sf.",
                                      elements: ["a"], links: [new("§325-8A, p.25", "https://x/y.pdf#page=25")])), 0, 1,
                           new Dictionary<string, string> { ["a"] = "Building: Box" }, null);
        Assert.Equal("To comply: reduce the footprint by at least 213 sf.", d.Steps[0].Words);
        Assert.Equal([DetailAction.None, DetailAction.None, DetailAction.ShowElements, DetailAction.OpenLaw, DetailAction.CheckAgain],
                     d.Steps.Select(s => s.Action));
        Assert.Equal("Show Building: Box in the model.", d.Steps[2].Words);
        Assert.DoesNotContain(d.Steps, s => s.Words.Contains("compl", StringComparison.OrdinalIgnoreCase) && s != d.Steps[0]);
    }

    [Fact]
    public void A_row_that_complies_has_nothing_to_do_until_the_model_changes_and_then_is_never_green()
    {
        var row = Placed(Row(Verdict.Complies, reason: null));
        Assert.Empty(Details.Of(row, 0, 1, null, null).Steps);
        var stale = Details.Of(row with { Status = StatusLook.Of(Tone.Complies, true) }, 0, 1, null, new DateTime(2026, 11, 22, 14, 32, 0));
        Assert.Equal(PanelStatus.Stale, stale.Status);
        Assert.StartsWith("The model changed after this check (14:32)", stale.Stale);
        Assert.Equal([DetailAction.CheckAgain], stale.Steps.Select(s => s.Action));
    }

    [Fact]
    public void A_stale_odyssey_has_no_green_detail_and_every_detail_says_why_first()
    {
        foreach (var (_, d, _) in All(Odyssey(), stale: true))
        {
            Assert.Equal(PanelStatus.Stale, d.Status);
            Assert.NotNull(d.Stale);
            Assert.Contains("STALE:", d.Text().Split('\n')[1], StringComparison.Ordinal);
            Assert.Equal(DetailAction.CheckAgain, d.Steps[^1].Action);
        }
    }

    [Theory]
    [InlineData(Verdict.NeedsReview, false, "Resolve what the reason above says")]
    [InlineData(Verdict.NeedsReview, true, "Check it by hand against the law's words below")]
    [InlineData(Verdict.NotChecked, false, "Give what the check needs")]
    public void A_needs_review_says_how_it_is_resolved_by_its_place(Verdict v, bool byHand, string first)
    {
        var d = Details.Of(Placed(Row(v), byHand), 0, 1, null, null);
        Assert.StartsWith(first, d.Steps[0].Words, StringComparison.Ordinal);
        Assert.Equal(DetailAction.CheckAgain, d.Steps[^1].Action);
    }

    [Fact]
    public void Elements_are_named_as_the_project_names_them_and_one_not_in_the_model_is_said_and_not_shown()
    {
        var d = Details.Of(Placed(Row(Verdict.NeedsReview, elements: ["a", "b", "gone"])), 0, 1,
                           new Dictionary<string, string> { ["a"] = "CLOSET (40)", ["b"] = "Door D06" }, null);
        Assert.Equal(["CLOSET (40)", "Door D06", Details.NotInModel], d.Elements.Select(e => e.Name));
        Assert.Equal([true, true, false], d.Elements.Select(e => e.InModel));
        Assert.Contains(d.Steps, s => s is { Action: DetailAction.ShowElements, Words: "Show its 2 elements in the model." });
        Assert.DoesNotContain(d.Elements, e => e.Name.Contains("gone", StringComparison.Ordinal));     // never the UniqueId
    }

    /// <summary>Review round 1: Revit's id goes with each element apart from its name, and Show's tooltip says it.</summary>
    [Fact]
    public void Each_elements_show_tooltip_gives_its_revit_id_for_select_by_id()
    {
        var d = Details.Of(Placed(Row(Verdict.NeedsReview, elements: ["a", "b", "gone"])), 0, 1,
                           new Dictionary<string, string> { ["a"] = "CLOSET (40)", ["b"] = "Door D06" }, null,
                           new Dictionary<string, long> { ["a"] = 341207, ["gone"] = 9 });
        Assert.Equal([341207L, null, null], d.Elements.Select(e => e.RevitId));            // one not in the model: none
        Assert.Equal("Zoom to CLOSET (40) in the model. Revit id 341207, for Select by ID", d.Elements[0].ShowTip);
        Assert.Equal("Zoom to Door D06 in the model", d.Elements[1].ShowTip);
        Assert.DoesNotContain("341207", d.Elements[0].Name, StringComparison.Ordinal);
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "DetailView.cs"));
        Assert.Contains("var show = Button(\"Show\", e.ShowTip, () => host.ShowElements(e.Uid));", view, StringComparison.Ordinal);
        var results = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        Assert.Contains("Details.Of(rows[index], index, rows.Count, _content?.Labels, stale, _content?.Ids, _content?.Model?.StaleKind ?? StaleReason.ModelChanged);", results, StringComparison.Ordinal);
    }

    [Fact]
    public void No_show_step_when_no_element_is_in_the_model_and_no_open_law_step_without_a_link()
    {
        var d = Details.Of(Placed(Row(Verdict.NeedsReview, elements: ["gone"])), 0, 1, null, null);
        Assert.DoesNotContain(d.Steps, s => s.Action is DetailAction.ShowElements or DetailAction.OpenLaw);
    }

    [Fact]
    public void The_reason_is_why_unless_it_only_restates_the_figures_or_the_advice()
    {
        Assert.Equal("the reason", Details.Of(Placed(Row(Verdict.NeedsReview)), 0, 1, null, null).Why);
        Assert.Null(Details.Of(Placed(Row(Verdict.NotChecked, hint: "the reason")), 0, 1, null, null).Why);
        var figures = Row(Verdict.NeedsReview, reason: "allowed 20'-0\"") with { Figures = "allowed 20'-0\"" };
        Assert.Null(Details.Of(Placed(figures), 0, 1, null, null).Why);
    }

    [Fact]
    public void No_quote_is_said_with_where_to_look()
    {
        var d = Details.Of(Placed(Row(Verdict.NeedsReview)), 0, 1, null, null);
        Assert.Equal("The checker sent no quote with this row: see §325-8.", d.NoQuote);
    }

    [Fact]
    public void Among_is_the_rows_shown_in_order_headings_skipped()
    {
        var a = Placed(Row(Verdict.DoesNotComply) with { Id = "a" });
        var b = Placed(Row(Verdict.NeedsReview) with { Id = "b" });
        var entries = ResultList.Layout([a, b], ListFilter.All, null, null, false);
        var (rows, index) = Details.Among(ResultList.WithSummary(entries), "b");
        Assert.Equal(["a", "b"], rows.Select(r => r.Row.Id));
        Assert.Equal(1, index);
        Assert.Equal(-1, Details.Among(entries, "nope").Index);
    }

    // ---- what the worker sends, read for the detail -----------------------------------------------------------

    private static ResultRow One(string json) =>
        ResultRows.Row(CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(
            "{\"view\":{\"items\":[" + json + "],\"groups\":[{\"key\":\"review\",\"title\":\"t\",\"items\":[\"r\"]}],\"summary\":\"s\",\"state\":\"needs_review\"},\"report_error\":null}").RootElement, About)).Items[0]);

    [Fact]
    public void An_egress_rows_figures_are_split_into_measure_figure_and_need_in_its_own_words()
    {
        var r = One("{\"id\":\"r\",\"name\":\"Window 5 · Sill\",\"group\":\"law\",\"status\":\"needs_review\"," +
                    "\"reason\":\"net clear height 20 in, needs ≥ 24 in; sill height 48 in, needs ≤ 44 in\"}");
        Assert.Equal([new FigureLine("net clear height", "20 in", "measured", "≥ 24 in"), new FigureLine("sill height", "48 in", "measured", "≤ 44 in")],
                     r.FigureLines);
        Assert.Equal(r.Figures, string.Join("; ", r.FigureLines.Select(f => $"{f.What} {f.Measured}, needs {f.Limit}")));
    }

    [Fact]
    public void A_zoning_rows_figures_are_its_proposed_and_required_with_its_sign()
    {
        var r = One("{\"id\":\"r\",\"name\":\"Lot coverage\",\"group\":\"building\",\"reason\":null,\"status\":\"needs_review\",\"proposed\":\"28.3%\"," +
                    "\"required\":\"25%\",\"sign\":\"≤\",\"hint\":\"To comply: reduce the footprint by at least 213 sf.\"}");
        Assert.Equal([new FigureLine(null, "28.3%", "measured", "≤ 25%")], r.FigureLines);
        Assert.Equal("To comply: reduce the footprint by at least 213 sf.", r.Hint);
        var limit = One("{\"id\":\"r\",\"name\":\"Stream\",\"group\":\"building\",\"reason\":null,\"status\":\"needs_review\",\"proposed\":\"—\",\"required\":\"20'-0\\\"\",\"sign\":\"≥\"}");
        Assert.Equal([new FigureLine(null, null, "not measured", "≥ 20'-0\"")], limit.FigureLines);
    }

    [Fact]
    public void The_laws_links_are_the_workers_cited_each_once_and_only_web_or_file_addresses()
    {
        var r = One("{\"id\":\"r\",\"name\":\"n\",\"group\":\"building\",\"reason\":null,\"status\":\"needs_review\",\"detail\":{\"cited\":[" +
                    "{\"citation\":\"§325-26, p.67\",\"link\":\"https://example.org/c.pdf#page=67\"}," +
                    "{\"citation\":\"again\",\"link\":\"https://example.org/c.pdf#page=67\"}," +
                    "{\"citation\":\"bad\",\"link\":\"javascript:alert(1)\"},{\"citation\":\"none\",\"link\":\"\"}]}}");
        Assert.Equal([new LawLink("§325-26, p.67", "https://example.org/c.pdf#page=67")], r.Links);
    }
}
