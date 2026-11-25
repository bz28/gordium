using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Which code the building was checked against (the worker's <c>which_code</c>, Ben 2026-11-22): the line at
/// the top of the summary in the worker's words exactly, absent without the field, never green, needs review when the
/// code wasn't decided, greyed when stale, and read tolerantly.</summary>
public sealed class WhichCodeTests
{
    private static readonly WorkerAbout About = new("1.2", "gordium.site/1", new string('f', 64),
                                                    new Dictionary<string, string> { ["new_york/ithaca_city"] = new('a', 64) });

    private static ResultModel Build(JsonNode? whichCode, bool sent = false)
    {
        var result = new JsonObject
        {
            ["view"] = new JsonObject
            {
                ["items"] = new JsonArray(new JsonObject { ["id"] = "r", ["name"] = "Front yard", ["group"] = "building", ["status"] = "needs_review", ["reason"] = "why" }),
                ["groups"] = new JsonArray(new JsonObject { ["key"] = "review", ["title"] = "Needs review", ["items"] = new JsonArray("r") }),
                ["summary"] = "1 needs review", ["state"] = "needs_review",
            },
            ["report_error"] = null,
        };
        if (whichCode is not null || sent)
            result["which_code"] = whichCode;
        var check = CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(result.ToJsonString()).RootElement, About));
        return ResultRows.Build(check, null, [], null);
    }

    private static JsonObject Residential() => new()
    {
        ["code"] = "residential_code", ["title"] = "2025 Residential Code of NYS",
        ["why"] = "a detached one-family dwelling, 3 stories above grade plane (R101.2)",
        ["cites"] = new JsonArray(new JsonObject
        {
            ["section"] = "RCNYS R101.2", ["document"] = "2025 Residential Code of New York State", ["page"] = 21,
            ["quote"] = "The provisions of this code shall apply to ... detached one- and two-family dwellings ... not more than three stories above grade plane",
        }),
        ["later_field"] = "ignored",
    };

    [Fact]
    public void A_decided_code_is_one_line_in_the_workers_words_at_the_top_of_the_summary_never_green()
    {
        var model = Build(Residential());
        Assert.Equal("Checked against: 2025 Residential Code of NYS — a detached one-family dwelling, 3 stories above grade plane (R101.2)",
                     model.Code!.Words);
        Assert.Equal([PanelPart.Code, PanelPart.State, PanelPart.Counts, PanelPart.Groups, PanelPart.Details], ResultRows.Layout(model));
        Assert.Null(model.Code.Status(stale: false));                                    // plain words: no status, no green
        Assert.Equal("RCNYS R101.2, 2025 Residential Code of New York State, p.21: “The provisions of this code shall apply to ... detached one- and two-family dwellings ... not more than three stories above grade plane”",
                     model.Code.Tooltip);
    }

    [Fact]
    public void Without_the_field_no_line_is_shown()
    {
        var model = Build(null);
        Assert.Null(model.Code);
        Assert.DoesNotContain(PanelPart.Code, ResultRows.Layout(model));
        Assert.Null(Build(JsonValue.Create("residential_code")).Code);                   // not an object: as if not sent
        Assert.Null(Build(null, sent: true).Code);                                       // the worker's None: no line
    }

    [Fact]
    public void A_code_not_decided_is_needs_review_with_the_workers_ask()
    {
        var code = Build(new JsonObject { ["code"] = null, ["ask"] = "how many stories above grade plane: enter Gordium: Stories" }).Code!;
        Assert.False(code.Decided);
        Assert.Equal("Which code: needs review — how many stories above grade plane: enter Gordium: Stories", code.Words);
        Assert.Equal(PanelStatus.Review, code.Status(stale: false));
        Assert.Equal("Which code: needs review", Build(new JsonObject()).Code!.Words);   // nothing said: no guess
        // a code word with no title isn't shown as decided (never a default)
        Assert.Equal(PanelStatus.Review, Build(new JsonObject { ["code"] = "building_code" }).Code!.Status(false));
    }

    [Fact]
    public void A_stale_result_greys_the_line_and_keeps_its_words()
    {
        var model = ResultRows.Stale(Build(Residential()), new DateTime(2026, 11, 22, 14, 32, 0));
        Assert.Contains(PanelPart.Code, ResultRows.Layout(model));
        Assert.Equal(PanelStatus.Stale, model.Code!.Status(stale: model.Stale is not null));
        Assert.Equal(PanelStatus.Stale, Build(new JsonObject { ["code"] = null }).Code!.Status(stale: true));
    }

    [Fact]
    public void The_line_is_never_green_whatever_the_worker_sends()
    {
        foreach (var w in new JsonNode?[] { Residential(), new JsonObject { ["code"] = "complies", ["title"] = "complies" }, new JsonObject() })
            foreach (var stale in new[] { false, true })
                Assert.NotEqual(PanelStatus.Complies, Build(w!.DeepClone()).Code!.Status(stale));
    }

    /// <summary>The view draws the line from WhichCode alone: its words, its status (never green), its tooltip.</summary>
    [Fact]
    public void The_view_draws_the_line_from_its_words_and_status_only()
    {
        var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "ResultsView.cs"));
        // shown at the top without the two views, or while the code isn't decided (UI polish PR 3: By code says it otherwise)
        var at = view.IndexOf("case PanelPart.Code when model.Code is { } code && (model.Views is null || !code.Decided):", StringComparison.Ordinal);
        Assert.True(at > 0);
        var block = view[at..view.IndexOf("case PanelPart.State:", at, StringComparison.Ordinal)];
        Assert.Contains("var codeStatus = code.Status(stale);", block, StringComparison.Ordinal);
        Assert.Contains("Text = code.Words,", block, StringComparison.Ordinal);
        Assert.Contains("codeStatus is { } cs ? StatusLook.Colour(cs) : PanelTokens.TextMuted", block, StringComparison.Ordinal);
        Assert.DoesNotContain("StatusPass", block, StringComparison.Ordinal);
    }
}
