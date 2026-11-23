using System.Net;
using System.Text.RegularExpressions;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Change 15 of the UI design pass, Revit-free: the printable compliance summary holds exactly the checker's
/// rows (each once, in its groups' order) and words (names, figures, the law's quotes), headed "Not a permit or an
/// approval", with no figure of its own, and is never made of a stale answer.</summary>
public sealed class ComplianceSummaryTests
{
    private static readonly DateTime At = new(2026, 11, 23, 14, 32, 0);
    private static readonly DateTime Made = new(2026, 11, 23, 15, 1, 0);

    private static readonly Regex RowTag = new("<tr data-row=\"(?<id>[^\"]*)\" data-status=\"(?<status>[a-z]+)\">(?<body>.*?)</tr>",
                                               RegexOptions.Singleline | RegexOptions.CultureInvariant);

    private static ResultModel Zoning() => UxAnswers.Model(UxAnswers.Answer("does_not_comply",
        UxAnswers.Item("coverage", "does_not_comply", "Lot coverage", reason: "28.3% measured, needs ≤ 25%", proposed: "28.3%", required: "25%",
                       sign: "≤", quote: "Maximum lot coverage by buildings · Percent of lot area · R-1B: 25%",
                       where: "City of Ithaca Zoning Charts (April 2026), p.3, line 34"),
        UxAnswers.Item("front", "complies", "Front yard", proposed: "30'-0\"", required: "25'-0\"", sign: "≥",
                       quote: "Yard Dimensions · Front (minimum) · R-1B: 25 ft", where: "City of Ithaca Zoning Charts (April 2026), p.3, line 37"),
        UxAnswers.Item("stream", "needs_review", "New structures at least 20 ft from an inlet wall or stream bank", reason: "Enter whether a stream is within 20 ft",
                       required: "20'-0\"", sign: "≥", quote: "No new structure shall be located nearer than 20 feet to an inlet wall", where: "§325-8, p.12"),
        UxAnswers.Item("evil", "needs_review", "<script>alert(1)</script> & “quotes”", reason: null)));

    [Fact]
    public void The_summary_holds_exactly_the_checkers_rows_each_once_in_its_groups_order()
    {
        foreach (var model in new[] { UxAnswers.Model(UxAnswers.Odyssey()), Zoning() })
        {
            var html = ComplianceSummary.Html(model, "Children's Odyssey", At, Made);
            var ids = RowTag.Matches(html).Select(m => WebUtility.HtmlDecode(m.Groups["id"].Value)).ToList();
            Assert.Equal(model.Groups.SelectMany(g => g.AllRows).Select(r => r.Id), ids);
            Assert.Equal(ids.Count, ids.Distinct().Count());
            // each group of the checker's is a heading, with its count
            foreach (var g in model.Groups.Where(g => g.AllRows.Any()))
                Assert.Contains($"<h2>{WebUtility.HtmlEncode(g.Title)} ({g.AllRows.Count()})</h2>", html, StringComparison.Ordinal);
        }
        Assert.Equal(190, RowTag.Matches(ComplianceSummary.Html(UxAnswers.Model(UxAnswers.Odyssey()), "o", At, Made)).Count);
    }

    /// <summary>The pin on the words: every row's name, status word and every quote of the law (with where it is) as the
    /// checker gave them; every number in a row is one of that row's own (no figure of the add-in's).</summary>
    [Fact]
    public void The_summary_says_the_checkers_words_and_no_figure_of_its_own()
    {
        foreach (var model in new[] { UxAnswers.Model(UxAnswers.Odyssey()), Zoning() })
        {
            var html = ComplianceSummary.Html(model, "P", At, Made);
            var rows = model.Groups.SelectMany(g => g.AllRows).ToDictionary(r => r.Id, StringComparer.Ordinal);
            foreach (Match m in RowTag.Matches(html))
            {
                var row = rows[WebUtility.HtmlDecode(m.Groups["id"].Value)];
                var body = m.Groups["body"].Value;
                var text = WebUtility.HtmlDecode(Regex.Replace(Regex.Replace(body, "<svg.*?</svg>", "", RegexOptions.Singleline), "<[^>]+>", " "));
                Assert.Contains(row.Name, text, StringComparison.Ordinal);
                Assert.Equal(StatusLook.Of(row.Tone, false).ToString().ToLowerInvariant(), m.Groups["status"].Value);
                Assert.Contains(StatusLook.Word(StatusLook.Of(row.Tone, false)), text, StringComparison.Ordinal);
                foreach (var q in row.Quotes)
                    Assert.Contains($"“{q.Text}”" + (q.Where is null ? "" : $" ({q.Where})"), text, StringComparison.Ordinal);
                var own = string.Join("\n", new[] { row.Name, row.Figures, row.HowFar, row.Reason, row.Hint, row.Section, row.VerdictWords }
                                                .Concat(row.Quotes.SelectMany(q => new[] { q.Text, q.Where }))
                                                .Concat(row.FigureLines.SelectMany(l => new[] { l.What, l.Measured, l.Limit }))
                                                .Concat(row.Links.Select(l => l.Citation)).Where(s => s is not null));
                foreach (Match n in Regex.Matches(text, @"[0-9]+(?:[.,][0-9]+)*"))
                    Assert.True(own.Contains(n.Value, StringComparison.Ordinal), $"{row.Id}: {n.Value} is not the checker's");
            }
        }
    }

    [Fact]
    public void A_zoning_row_says_proposed_required_and_its_result_with_its_glyph()
    {
        var html = ComplianceSummary.Html(Zoning(), "106 Ithaca Rd", At, Made);
        var coverage = RowTag.Matches(html).Single(m => m.Groups["id"].Value == "coverage").Groups["body"].Value;
        Assert.Contains("<td>28.3%</td><td>≤ 25%</td>", coverage, StringComparison.Ordinal);
        Assert.Contains(ComplianceSummary.Svg(PanelStatus.Fails) + "Does not comply", coverage, StringComparison.Ordinal);
        Assert.Contains(PanelTokens.Colours(PanelTheme.Light)[PanelTokens.StatusFail].ToString(), ComplianceSummary.Svg(PanelStatus.Fails), StringComparison.Ordinal);
        var stream = RowTag.Matches(html).Single(m => m.Groups["id"].Value == "stream").Groups["body"].Value;
        Assert.Contains("<td>—</td><td>≥ 20&#39;-0&quot;</td>", stream, StringComparison.Ordinal);
        Assert.Contains("Enter whether a stream is within 20 ft", stream, StringComparison.Ordinal);
        var front = RowTag.Matches(html).Single(m => m.Groups["id"].Value == "front").Groups["body"].Value;
        Assert.Contains(ComplianceSummary.Svg(PanelStatus.Complies) + "Complies", front, StringComparison.Ordinal);
    }

    /// <summary>The head: "Not a permit or an approval; every needs review is for the architect", before any result.</summary>
    [Fact]
    public void The_summary_is_headed_not_a_permit_or_an_approval()
    {
        var html = ComplianceSummary.Html(Zoning(), "106 Ithaca Rd", At, Made);
        Assert.Equal("Not a permit or an approval; every needs review is for the architect", ComplianceSummary.NotAPermit);
        var head = html.IndexOf("<div class=\"not-permit\" id=\"not-a-permit\">" + ComplianceSummary.NotAPermit + ".</div>", StringComparison.Ordinal);
        Assert.InRange(head, 0, html.IndexOf("<table>", StringComparison.Ordinal));
        Assert.Contains("checked 2026-11-23 14:32 and saved 2026-11-23 15:01", html, StringComparison.Ordinal);
        Assert.DoesNotContain("<script", html, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("&lt;script&gt;alert(1)&lt;/script&gt; &amp; “quotes”", html, StringComparison.Ordinal);
    }

    /// <summary>Never a stale summary, nor one of a check that sent nothing: the pane's results must stand.</summary>
    [Fact]
    public void A_stale_answer_or_nothing_checked_is_never_summarised()
    {
        var stale = ResultRows.Stale(Zoning(), At);
        Assert.Equal("The model changed after the check at 14:32, so its results may not hold: click Check project, then save the summary.",
                     ComplianceSummary.Refusal(stale, At));
        Assert.Throws<InvalidOperationException>(() => ComplianceSummary.Html(stale, "P", At, Made));
        Assert.NotNull(ComplianceSummary.Refusal(null, At));
        Assert.Null(ComplianceSummary.Refusal(Zoning(), At));
    }

    [Fact]
    public void The_file_is_named_for_the_project_and_the_check()
    {
        Assert.Equal("106 Ithaca Rd compliance summary 2026-11-23 1432.html", ComplianceSummary.FileName("106 Ithaca Rd", At));
        Assert.Equal("a_b_c compliance summary 2026-11-23 1432.html", ComplianceSummary.FileName("a/b:c", At));
        Assert.Equal("Project compliance summary 2026-11-23 1432.html", ComplianceSummary.FileName("  ", At));
    }
}
