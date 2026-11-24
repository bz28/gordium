using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Answers made for the badge, selection and summary tests (changes 13 to 15 of the UI design pass).</summary>
internal static class UxAnswers
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    internal static readonly string Here = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests");

    /// <summary>The Children's Odyssey's committed answer (190 rows, 183 need review, 7 comply).</summary>
    internal static CheckResult Odyssey() => Parse(JsonNode.Parse(File.ReadAllText(Path.Combine(Here, "answers", "children_odyssey_check_answer.json"),
                                                                                       Encoding.UTF8))!["result"]!.AsObject());

    internal static CheckResult Parse(JsonObject result) =>
        CheckResult.Parse(new WorkerAnswer(JsonDocument.Parse(result.ToJsonString()).RootElement, About));

    internal static ResultModel Model(CheckResult r) => ResultRows.Build(r, null, [], null);

    internal static JsonObject Item(string id, string status, string? name = null, string? reason = "r", string[]? objects = null,
                                    string? proposed = null, string? required = null, string? sign = null, string? quote = null,
                                    string? where = null) => new()
    {
        ["id"] = id, ["name"] = name ?? id, ["group"] = "law", ["status"] = status, ["reason"] = reason,
        ["objects"] = new JsonArray((objects ?? []).Select(o => (JsonNode)o).ToArray()),
        ["proposed"] = proposed, ["required"] = required, ["sign"] = sign,
        ["detail"] = quote is null ? null : new JsonObject
        {
            ["quotes"] = new JsonArray(new JsonObject { ["text"] = quote, ["where"] = where }),
        },
    };

    internal static JsonObject Group(string key, string[] items, params JsonObject[] cards) => new()
    {
        ["key"] = key, ["title"] = key, ["items"] = new JsonArray(items.Select(i => (JsonNode)i).ToArray()),
        ["causes"] = new JsonArray(cards.Select(c => (JsonNode)c).ToArray()),
    };

    /// <summary>An answer of <paramref name="items"/> in one group per status (the worker's zoning keys), its state
    /// <paramref name="state"/>.</summary>
    internal static CheckResult Answer(string state, params JsonObject[] items)
    {
        var groups = items.GroupBy(i => (string)i["status"]! switch { "does_not_comply" => "fails", "complies" or "not_applicable" => "complies", _ => "review" })
                          .Select(g => Group(g.Key, [.. g.Select(i => (string)i["id"]!)]))
                          .ToArray();
        return Parse(new JsonObject
        {
            ["view"] = new JsonObject
            {
                ["items"] = new JsonArray(items.Select(i => (JsonNode)i).ToArray()), ["summary"] = "s", ["state"] = state,
                ["groups"] = new JsonArray(groups.Select(g => (JsonNode)g).ToArray()),
            },
            ["report_error"] = null,
        });
    }
}

/// <summary>Change 13 of the UI design pass, Revit-free: Check project's badge and tooltip. The counts are the pane's
/// own rows; the badge never shows a pass while a row needs review, and a stale answer shows the clock, never its
/// counts as current.</summary>
public sealed class RibbonBadgeTests
{
    private static readonly DateTime At = new(2026, 11, 23, 14, 32, 0);

    private static ResultModel Model(string state, params JsonObject[] items) => UxAnswers.Model(UxAnswers.Answer(state, items));

    private static bool Has(byte[] rgba, Rgb c)
    {
        for (var i = 0; i < rgba.Length; i += 4)
            if (rgba[i] == c.R && rgba[i + 1] == c.G && rgba[i + 2] == c.B && rgba[i + 3] == 255)
                return true;
        return false;
    }

    private static Rgb Token(string token, PanelTheme theme = PanelTheme.Light) => PanelTokens.Colours(theme)[token];

    [Fact]
    public void The_odyssey_badge_counts_its_183_rows_that_need_review()
    {
        var badge = RibbonBadge.Of(UxAnswers.Model(UxAnswers.Odyssey()), At);
        Assert.Equal(BadgeKind.Counts, badge.Kind);
        Assert.Equal(0, badge.Fails);
        Assert.Equal(183, badge.Review);
        // one sentence (UI polish change 42): by hand and not checked yet are the pane's to say, not the tooltip's
        Assert.Equal("Checked 14:32: 183 need review, 7 comply. Click to check again.", badge.ToolTip);
    }

    [Fact]
    public void A_failure_and_reviews_are_a_red_and_an_amber_count_said_in_words()
    {
        var badge = RibbonBadge.Of(Model("does_not_comply", UxAnswers.Item("a", "does_not_comply"), UxAnswers.Item("b", "needs_review"),
                                         UxAnswers.Item("c", "needs_review"), UxAnswers.Item("d", "complies")), At);
        Assert.Equal((BadgeKind.Counts, 1, 2), (badge.Kind, badge.Fails, badge.Review));
        Assert.Equal("Checked 14:32: 1 fails, 2 need review, 1 complies. Click to check again.", badge.ToolTip);
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
        {
            var px = RibbonBadge.Pixels(badge, 32, theme);
            Assert.True(Has(px, Token(PanelTokens.StatusFail, theme)));
            Assert.True(Has(px, Token(PanelTokens.StatusReview, theme)));
            Assert.False(Has(px, Token(PanelTokens.StatusPass, theme)));
            Assert.True(Has(RibbonBadge.Pixels(badge, 16, theme), Token(PanelTokens.StatusFail, theme)));
        }
    }

    /// <summary>The pin: a state of "complies" while one row needs review (or is not checked, or has a word the add-in
    /// doesn't know) gets counts, never the pass tick; no pixel of the badge is the pass colour. (The worker reader
    /// already refuses such an answer, CheckResult.CheckComplies; the badge doesn't rely on it.)</summary>
    [Theory]
    [InlineData("needs_review")]
    [InlineData("not_checked")]
    [InlineData("maybe")]
    public void The_badge_never_shows_a_pass_while_any_row_needs_review(string word)
    {
        var model = Model("needs_review", UxAnswers.Item("a", "complies"), UxAnswers.Item("b", "complies"), UxAnswers.Item("c", word))
                    with { State = Verdict.Complies };
        var badge = RibbonBadge.Of(model, At);
        Assert.Equal(BadgeKind.Counts, badge.Kind);
        Assert.Equal(1, badge.Review);
        Assert.Equal(PanelStatus.Review, RibbonBadge.Dot(badge));
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
            foreach (var size in new[] { 16, 32 })
                Assert.False(Has(RibbonBadge.Pixels(badge, size, theme), Token(PanelTokens.StatusPass, theme)));
    }

    /// <summary>Never a green badge (UI polish change 42): a check the checker says complies, with nothing to review,
    /// is the plain icon at both sizes and in both themes (a glance can't say what Gordium didn't check: "all comply"
    /// is the pane's to say, beside it), its tooltip saying the counts.</summary>
    [Fact]
    public void A_complying_check_is_the_plain_icon_never_green()
    {
        var pass = RibbonBadge.Of(Model("complies", UxAnswers.Item("a", "complies"), UxAnswers.Item("b", "not_applicable")), At);
        Assert.Equal(BadgeKind.Complies, pass.Kind);
        Assert.Equal("Checked 14:32: 1 complies, 1 not applicable. Click to check again.", pass.ToolTip);
        Assert.Null(RibbonBadge.Dot(pass));
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
            foreach (var size in new[] { 16, 32 })
            {
                Assert.Equal(RibbonIcons.Pixels(RibbonIcons.CheckProject, size, theme), RibbonBadge.Pixels(pass, size, theme));
                Assert.False(Has(RibbonBadge.Pixels(pass, size, theme), Token(PanelTokens.StatusPass, theme)));
            }
        // every rule set aside, or a state that isn't "complies": an amber "?", never the pass colour
        foreach (var unclear in new[]
                 {
                     RibbonBadge.Of(Model("needs_review", UxAnswers.Item("a", "not_applicable")), At),
                     RibbonBadge.Of(Model("needs_review", UxAnswers.Item("a", "complies")), At),
                     RibbonBadge.Of(Model("needs_review", UxAnswers.Item("a", "not_applicable")) with { State = Verdict.Complies }, At),
                 })
        {
            Assert.Equal(BadgeKind.Unclear, unclear.Kind);
            Assert.False(Has(RibbonBadge.Pixels(unclear, 32, PanelTheme.Light), Token(PanelTokens.StatusPass)));
            Assert.True(Has(RibbonBadge.Pixels(unclear, 32, PanelTheme.Light), Token(PanelTokens.StatusReview)));
        }
    }

    /// <summary>The pin: once the model changed, the clock alone (the same pixels whatever the counts were), and the
    /// tooltip says no count, only that the results may not hold.</summary>
    [Fact]
    public void A_stale_answer_shows_the_clock_never_the_counts_as_current()
    {
        var model = Model("does_not_comply", UxAnswers.Item("a", "does_not_comply"), UxAnswers.Item("b", "needs_review"), UxAnswers.Item("c", "needs_review"));
        Assert.Equal(BadgeKind.Counts, RibbonBadge.Of(model, At).Kind);
        var stale = RibbonBadge.Of(ResultRows.Stale(model, At), At);
        Assert.Equal((BadgeKind.Stale, 0, 0), (stale.Kind, stale.Fails, stale.Review));
        Assert.Equal("The model changed after the 14:32 check. Click to check again.", stale.ToolTip);
        var passStale = RibbonBadge.Of(ResultRows.Stale(Model("complies", UxAnswers.Item("a", "complies")), At), At);
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
        {
            var px = RibbonBadge.Pixels(stale, 32, theme);
            Assert.Equal(px, RibbonBadge.Pixels(passStale, 32, theme));
            Assert.True(Has(px, Token(PanelTokens.StatusStale, theme)));
            foreach (var verdict in new[] { PanelTokens.StatusFail, PanelTokens.StatusReview, PanelTokens.StatusPass })
                Assert.False(Has(px, Token(verdict, theme)));
        }
    }

    [Fact]
    public void Nothing_checked_a_fact_to_set_or_a_failed_check_is_the_plain_icon()
    {
        var plain = RibbonIcons.Pixels(RibbonIcons.CheckProject, 32, PanelTheme.Light);
        var none = RibbonBadge.Of(null, At);
        Assert.Equal((BadgeKind.NotChecked, RibbonBadge.NotCheckedTip), (none.Kind, none.ToolTip));
        Assert.Equal(RibbonBadge.NotCheckedTip, RibbonPlan.Buttons(false).Single(b => b.Id == RibbonPlan.CheckProject).ToolTip);
        var missing = RibbonBadge.Of(null, At, missing: 3);
        Assert.Equal("Not checked yet: 3 things to set first. Click to set them.", missing.ToolTip);
        Assert.Equal("Not checked yet: 1 thing to set first. Click to set it.", RibbonBadge.Of(null, At, missing: 1).ToolTip);
        var failed = RibbonBadge.Of(Model("does_not_comply", UxAnswers.Item("a", "does_not_comply")), At, failed: true);
        Assert.Equal(BadgeKind.NotChecked, failed.Kind);
        Assert.Equal("The last check didn't finish. Click to check again.", failed.ToolTip);
        foreach (var b in new[] { none, missing, failed })
            Assert.Equal(plain, RibbonBadge.Pixels(b, 32, PanelTheme.Light));
    }

    [Fact]
    public void Counts_over_99_say_99_plus_and_pills_that_do_not_fit_side_by_side_go_top_and_bottom()
    {
        Assert.Equal("7", RibbonBadge.Pill(7));
        Assert.Equal("99", RibbonBadge.Pill(99));
        Assert.Equal("99+", RibbonBadge.Pill(100));
        // two short pills side by side in the top row; two long ones, one under the other
        var near = RibbonBadge.Pixels(new BadgeState(BadgeKind.Counts, 1, 77, ""), 32, PanelTheme.Light);
        var far = RibbonBadge.Pixels(new BadgeState(BadgeKind.Counts, 120, 300, ""), 32, PanelTheme.Light);
        static bool RowHas(byte[] px, int y, Rgb c) => Enumerable.Range(0, 32).Any(x =>
            px[(y * 32 + x) * 4] == c.R && px[(y * 32 + x) * 4 + 1] == c.G && px[(y * 32 + x) * 4 + 2] == c.B);
        var fail = Token(PanelTokens.StatusFail);
        var review = Token(PanelTokens.StatusReview);
        Assert.True(RowHas(near, 5, fail) && RowHas(near, 5, review));
        Assert.False(RowHas(near, 26, review));
        Assert.True(RowHas(far, 5, fail) && !RowHas(far, 5, review));
        Assert.True(RowHas(far, 26, review));
        Assert.False(RowHas(far, 15, review) || RowHas(far, 15, fail));          // the icon's middle left clear
    }

    [Fact]
    public void The_badge_is_a_png_of_the_size_revit_takes()
    {
        var png = RibbonBadge.Png(new BadgeState(BadgeKind.Counts, 1, 77, ""), 32, PanelTheme.Dark);
        Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47 }, png[..4]);
        Assert.Equal(32, System.Buffers.Binary.BinaryPrimitives.ReadInt32BigEndian(png.AsSpan(16)));
        Assert.Throws<ArgumentOutOfRangeException>(() => RibbonBadge.Pixels(new BadgeState(BadgeKind.Counts, 1, 0, ""), 24, PanelTheme.Light));
    }
}
