using System.Globalization;
using System.Net;
using System.Text;

namespace Gordium.Revit.Reading;

/// <summary>
/// The printable compliance summary (docs/revit/ui_design_pass.md, change 15), Revit-free so it is tested: one HTML
/// file of every row of one check, in the checker's groups and order, each with its rule, what was proposed and what
/// is required (the checker's figures, split as the pane splits them: <see cref="ResultRow.FigureLines"/>), its result
/// as a glyph and a word, the checker's reason when it doesn't comply or needs review, and the law's exact words with
/// their section and page (links to the source at its page when the checker sends them). Headed "Not a permit or an
/// approval; every needs review is for the architect". No figure, verdict or word is the add-in's own beyond the
/// headings and the verdict words the pane already uses (<see cref="StatusLook.Word"/>); a stale answer is never
/// summarised (<see cref="Refusal"/>).
/// <para>HTML, not PDF: the browser the architect already has opens it, prints it (to paper or to PDF, letter size,
/// the table's head repeated on each page) and keeps the law's links working; Unicode (≥, ≤, §, ’) needs no font
/// embedding; and the add-in needs no PDF library (it takes no packages).</para>
/// </summary>
public static class ComplianceSummary
{
    /// <summary>The words at the head of every summary.</summary>
    public const string NotAPermit = "Not a permit or an approval; every needs review is for the architect";

    /// <summary>Why no summary can be made of what the pane shows, or null when one can: nothing checked yet, a check
    /// that sent nothing (a fact to set first), or results the model changed after (they may no longer hold).</summary>
    public static string? Refusal(ResultModel? model, DateTime checkedAt)
    {
        if (model is null)
            return "Nothing has been checked in this session yet: click Check project, then save the summary.";
        if (model.Stale is not null)
            return PaneWords.StaleSummaryRefusal(checkedAt.ToString("HH:mm", CultureInfo.InvariantCulture), model.StaleKind ?? StaleReason.ModelChanged);
        return null;
    }

    /// <summary>A file name for the summary: the project's title, the words "compliance summary" and when it was checked,
    /// with any character Windows doesn't take in a file name replaced.</summary>
    public static string FileName(string project, DateTime checkedAt)
    {
        ArgumentNullException.ThrowIfNull(project);
        var bad = new HashSet<char>("<>:\"/\\|?*");
        var safe = new string([.. project.Select(c => c < 32 || bad.Contains(c) ? '_' : c)]).Trim().TrimEnd('.');
        return $"{(safe.Length == 0 ? "Project" : safe)} compliance summary {checkedAt.ToString("yyyy-MM-dd HHmm", CultureInfo.InvariantCulture)}.html";
    }

    /// <summary>Every row of the summary, in order: each group of the checker's (its title), then its rows.</summary>
    public static IReadOnlyList<(ResultGroup Group, IReadOnlyList<ResultRow> Rows)> Sections(ResultModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        return [.. model.Groups.Select(g => (g, (IReadOnlyList<ResultRow>)[.. g.AllRows])).Where(s => s.Item2.Count > 0)];
    }

    /// <summary>The pane's heading for a check sent anyway, each fact left out then listed (ResultsView's words).</summary>
    public static string NotStatedTitle(int count) =>
        $"Checked without {count} {(count == 1 ? "fact" : "facts")}: the rules they decide need review";

    /// <summary>The summary as one self-contained HTML file (no script, no file it loads), for <paramref name="project"/>
    /// checked at <paramref name="checkedAt"/>, saved at <paramref name="madeAt"/>. Everything the pane shows that
    /// qualifies the results is said too, in its words: the facts a check sent anyway left out
    /// (<paramref name="notStated"/>), which code (the worker's which_code line), the drafts this run filled
    /// (<paramref name="drafts"/>: ClearPrefills.PanelStatus), and what wasn't read from the model
    /// (<see cref="ResultModel.Inside"/>). Throws for a model <see cref="Refusal"/> refuses.</summary>
    public static string Html(ResultModel model, string project, DateTime checkedAt, DateTime madeAt,
                              IReadOnlyList<string>? notStated = null, string? drafts = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(project);
        if (Refusal(model, checkedAt) is { } why)
            throw new InvalidOperationException(why);
        var light = PanelTokens.Colours(PanelTheme.Light);
        string C(string token) => light[token].ToString();
        var h = new StringBuilder();
        h.Append("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n")
         .Append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
         .Append("<title>").Append(E(project)).Append(" · compliance summary</title>\n<style>\n")
         .Append("@page { size: letter; margin: 0.55in 0.5in; }\n")
         .Append("body { font: 10.5pt/1.35 'Segoe UI', system-ui, sans-serif; color: ").Append(C(PanelTokens.Text))
         .Append("; background: #FFFFFF; margin: 0 auto; max-width: 10.5in; padding: 24px 16px; }\n")
         .Append("h1 { font-size: 19pt; font-weight: 600; margin: 0 0 2px; }\n")
         .Append("h2 { font-size: 12pt; font-weight: 600; margin: 18px 0 4px; break-after: avoid; }\n")
         .Append(".muted { color: ").Append(C(PanelTokens.TextMuted)).Append("; }\n")
         .Append(".not-permit { border: 2px solid ").Append(C(PanelTokens.StatusReview)).Append("; background: ").Append(C(PanelTokens.StatusReviewFill))
         .Append("; padding: 8px 12px; margin: 10px 0 12px; font-weight: 600; font-size: 12pt; }\n")
         .Append("table { border-collapse: collapse; width: 100%; margin-top: 4px; }\n")
         .Append("thead { display: table-header-group; }\n")
         .Append("th { text-align: left; font-weight: 600; font-size: 9pt; color: ").Append(C(PanelTokens.TextMuted))
         .Append("; border-bottom: 1px solid ").Append(C(PanelTokens.Line)).Append("; padding: 4px 6px; }\n")
         .Append("td { vertical-align: top; padding: 5px 6px; border-bottom: 1px solid ").Append(C(PanelTokens.Line)).Append("; }\n")
         .Append("tr { break-inside: avoid; }\n")
         .Append(".result { white-space: nowrap; }\n")
         .Append(".result svg { width: 13px; height: 13px; vertical-align: -2px; margin-right: 4px; }\n")
         .Append(".why { font-size: 9pt; margin-top: 2px; }\n")
         .Append(".law { font-family: Georgia, 'Times New Roman', serif; font-size: 9pt; }\n")
         .Append(".law p { margin: 0 0 4px; }\n")
         .Append(".greyed { margin: 2px 0 2px 12px; }\n")
         .Append(".appendix { margin: 0 0 10px; break-inside: avoid; }\n")
         .Append("h3, h4, h5 { font-weight: 600; margin: 12px 0 2px; break-after: avoid; }\n")
         .Append(".verbatim { white-space: pre-line; }\n")
         .Append("a { color: ").Append(C(PanelTokens.Accent)).Append("; }\n")
         .Append("@media print { body { padding: 0; max-width: none; } a { text-decoration: none; } }\n")
         .Append("</style>\n</head>\n<body>\n");

        h.Append("<h1>Compliance summary</h1>\n<div>").Append(E(project)).Append("</div>\n");
        h.Append("<div class=\"not-permit\" id=\"not-a-permit\">").Append(E(NotAPermit)).Append(".</div>\n");
        h.Append("<p class=\"muted\">Prepared with Gordium from the Revit model, checked ")
         .Append(E(checkedAt.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture))).Append(" and saved ")
         .Append(E(madeAt.ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture)))
         .Append(". A summary for the architect's own review: every result marked needs review is for the architect to resolve ")
         .Append("before relying on it, and a result that complies holds only for the model as it was checked.</p>\n");
        h.Append("<p><b>").Append(E(model.Headline)).Append("</b></p>\n");
        if (model.Checked.Length > 0)
            h.Append("<p class=\"muted\">").Append(E(model.Checked)).Append("</p>\n");
        if (notStated is { Count: > 0 })
        {
            // checked anyway: what was left out, each making its rules need review (the pane says it first)
            h.Append("<div id=\"not-stated\"><p><b>").Append(E(NotStatedTitle(notStated.Count))).Append("</b></p><ul>");
            foreach (var n in notStated)
                h.Append("<li>").Append(E(n)).Append("</li>");
            h.Append("</ul></div>\n");
        }
        if (model.Code is { } code)
        {
            h.Append("<p id=\"which-code\">").Append(E(code.Words)).Append("</p>\n");
            // its cited sections, documents and pages with the law's words, as the pane's tooltip says them (review round 2)
            if (code.Tooltip is { } cites)
                h.Append("<div id=\"which-code-cites\" class=\"law verbatim\">").Append(E(cites)).Append("</div>\n");
        }
        if (drafts is { Length: > 0 })
            h.Append("<p id=\"drafts\" class=\"verbatim\">").Append(E(drafts)).Append("</p>\n");
        if (model.Inside.Length > 0)
            h.Append("<h2>Not read from the model</h2>\n<p id=\"not-read\" class=\"verbatim\">").Append(E(model.Inside)).Append("</p>\n");

        if (model.Views is { } views)
            ByCode(h, views);
        else
            foreach (var (group, rows) in Sections(model))
            {
                h.Append("<h2>").Append(E(group.Title)).Append(" (").Append(rows.Count.ToString(CultureInfo.InvariantCulture)).Append(")</h2>\n");
                Table(h, rows, appendix: false);
            }
        h.Append("<p class=\"muted\" style=\"margin-top:16px\">Every figure and verdict here is the checker's own, as the Gordium pane ")
         .Append("showed it; each law's words are quoted exactly, with where they are. ").Append(E(NotAPermit)).Append(".</p>\n");
        h.Append("</body>\n</html>\n");
        return h.ToString();
    }

    private static void Table(StringBuilder h, IReadOnlyList<ResultRow> rows, bool appendix, int first = 0)
    {
        h.Append("<table>\n<thead><tr><th style=\"width:24%\">Rule</th><th style=\"width:11%\">Proposed</th>")
         .Append("<th style=\"width:11%\">Required</th><th style=\"width:15%\">Result</th>")
         .Append(appendix ? "" : "<th>The law's words</th>").Append("</tr></thead>\n<tbody>\n");
        for (var i = 0; i < rows.Count; i++)
            Row(h, rows[i], appendix, appendix ? first + i + 1 : 0);
        h.Append("</tbody>\n</table>\n");
    }

    // ---- UI polish change 38: the summary in the By code order -------------------------------------------------

    /// <summary>The title of the appendix holding every row's law, in the same order as the tables.</summary>
    public const string AppendixTitle = "The law's words, in the same order";

    /// <summary>Every row in the order a plan reviewer reads, By code's (document › chapter or article › section ›
    /// rule; <see cref="ResultViews"/>, where each row is placed exactly once), the parts of each document Gordium hasn't
    /// checked listed greyed, never left out; then the law's words of every row, in the same order, in an appendix.</summary>
    private static void ByCode(StringBuilder h, ResultViewsModel views)
    {
        var order = new List<ResultRow>();
        foreach (var doc in views.Code)
            Node(h, doc, 0, order);
        h.Append("<h2 id=\"the-laws-words\">").Append(E(AppendixTitle)).Append("</h2>\n");
        var n = 0;
        foreach (var row in order)
        {
            var at = (++n).ToString(CultureInfo.InvariantCulture);
            h.Append("<div class=\"law appendix\" id=\"law-").Append(at).Append("\" data-law=\"").Append(E(row.Id)).Append("\">")
             .Append("<p><b>").Append(at).Append(". ").Append(E(row.Name)).Append("</b></p>");
            Law(h, row);
            h.Append("</div>\n");
        }
    }

    /// <summary>A node of the law's tree: its heading and status line (a document's which-code note and scope note),
    /// its rules' rows as one table, its greyed parts said as not checked yet by Gordium, then what is inside.</summary>
    private static void Node(StringBuilder h, CodeNode node, int depth, List<ResultRow> order)
    {
        if (node.Greyed || node.Level == CodeLevel.Others)
        {
            // not checked yet by Gordium (or nothing to check): listed, greyed, never left out (change 35)
            h.Append("<p class=\"muted greyed\" data-greyed=\"").Append(E(node.State.ToString())).Append("\">")
             .Append(E(ResultViewList.Title(node))).Append(": ").Append(E(node.Line));
            if (node.Level == CodeLevel.Others && node.Children.Count > 0)
                h.Append(" (").Append(E(string.Join("; ", node.Children.Select(ResultViewList.Title)))).Append(')');
            h.Append("</p>\n");
            return;
        }
        var tag = "h" + Math.Min(2 + depth, 5).ToString(CultureInfo.InvariantCulture);
        h.Append('<').Append(tag).Append('>').Append(E(ResultViewList.Title(node))).Append("</").Append(tag).Append(">\n")
         .Append("<p class=\"muted\">").Append(E(node.Line)).Append("</p>\n");
        if (node.Note is { } note)
            h.Append("<p class=\"which-code\">").Append(E(note)).Append("</p>\n");
        if (node.Scope is { } scope)
            h.Append("<p class=\"scope\">").Append(E(scope)).Append("</p>\n");
        var rows = node.Rows.Concat(node.Children.Where(c => c.Level == CodeLevel.Rule && !c.Greyed).SelectMany(c => c.Rows)).ToList();
        if (rows.Count > 0)
        {
            Table(h, rows, appendix: true, first: order.Count);   // each row numbered as its law in the appendix
            order.AddRange(rows);
        }
        foreach (var child in node.Children.Where(c => c.Level != CodeLevel.Rule || c.Greyed))
            Node(h, child, depth + 1, order);
    }

    private static void Row(StringBuilder h, ResultRow row, bool appendix, int law = 0)
    {
        var status = StatusLook.Of(row.Tone, stale: false);
        var word = StatusLook.Word(status);
        h.Append("<tr data-row=\"").Append(E(row.Id)).Append("\" data-status=\"").Append(status.ToString().ToLowerInvariant()).Append("\">");
        // the rule, and why when it isn't a pass (the checker's reason, its advice)
        h.Append("<td>");
        // in By code order: the row's number, a link to its law's words in the appendix (review round 2)
        if (law > 0)
            h.Append("<a class=\"law-ref\" href=\"#law-").Append(law.ToString(CultureInfo.InvariantCulture)).Append("\">")
             .Append(law.ToString(CultureInfo.InvariantCulture)).Append(".</a> ");
        h.Append(E(row.Name));
        if (status is PanelStatus.Fails or PanelStatus.Review)
        {
            if (row.Reason is { Length: > 0 } reason && !row.ReasonIsFigures)
                h.Append("<div class=\"why muted\">").Append(E(reason)).Append("</div>");
            if (row.Hint is { Length: > 0 } hint)
                h.Append("<div class=\"why muted\">").Append(E(hint)).Append("</div>");
        }
        h.Append("</td>");
        // what was proposed and what is required: the checker's figures as the pane splits them
        if (row.FigureLines.Count == 0 && row.Figures is { } figures)
            h.Append("<td colspan=\"2\">").Append(E(figures)).Append("</td>");      // figures the pane couldn't split: as said
        else
            h.Append("<td>").Append(Lines(row.FigureLines.Select(l => (l.What is null ? "" : l.What + ": ") + (l.Measured ?? "—")
                                                                     + (l.How == "stated by the architect" ? " (stated by the architect)" : ""))))
             .Append("</td><td>").Append(Lines(row.FigureLines.Select(l => l.Limit))).Append("</td>");
        // the result: its glyph and its word (and the checker's own word when the pane reads it otherwise)
        h.Append("<td class=\"result\">").Append(Svg(status)).Append(E(word));
        if (!string.Equals(row.VerdictWords, word, StringComparison.OrdinalIgnoreCase))
            h.Append("<div class=\"why muted\">").Append(E(row.VerdictWords)).Append("</div>");
        if (row.HowFar is { Length: > 0 } far && status != PanelStatus.Complies)
            h.Append("<div class=\"why muted\">").Append(E(far)).Append("</div>");
        h.Append("</td>");
        if (appendix)
        {
            h.Append("</tr>\n");                                // the law's words: in the appendix, in the same order
            return;
        }
        h.Append("<td class=\"law\">");
        Law(h, row);
        h.Append("</td></tr>\n");
    }

    /// <summary>A row's law: its exact words, each with where it is; its section when no quote says where; the
    /// checker's links.</summary>
    private static void Law(StringBuilder h, ResultRow row)
    {
        foreach (var q in row.Quotes)
            h.Append("<p>“").Append(E(q.Text)).Append("”").Append(q.Where is null ? "" : " (" + E(q.Where) + ")").Append("</p>");
        if (row.Section is { Length: > 0 } section && !row.Quotes.Any(q => q.Where?.Contains(section, StringComparison.Ordinal) == true))
            h.Append("<p>").Append(E(section)).Append("</p>");
        if (row.Quotes.Count == 0 && row.Section is null)
            h.Append("<p class=\"muted\">The checker sent no words of the law for this result.</p>");
        if (row.Links.Count > 0)
            h.Append("<p>").AppendJoin(" · ", row.Links.Select(l => $"<a href=\"{E(l.Url)}\">{E(l.Citation)}</a>")).Append("</p>");
    }

    private static string Lines(IEnumerable<string> lines)
    {
        var all = lines.ToList();
        return all.Count == 0 ? "—" : string.Join("<br>", all.Select(E));
    }

    /// <summary>A status's glyph as inline SVG, from the pane's own (<see cref="StatusLook.GlyphOf"/>: WPF's path
    /// markup is SVG's path syntax), in the light theme's colours.</summary>
    internal static string Svg(PanelStatus s)
    {
        var look = StatusLook.GlyphOf(s);
        var light = PanelTokens.Colours(PanelTheme.Light);
        var ink = light[StatusLook.Colour(s)].ToString();
        var fill = look.Fill is { } f ? light[f].ToString() : "none";
        return $"<svg viewBox=\"0 0 16 16\" role=\"img\" aria-label=\"{E(StatusLook.Word(s))}\">" +
               $"<path d=\"{look.Outline}\" fill=\"{fill}\" stroke=\"{ink}\" stroke-width=\"1.4\" stroke-linejoin=\"round\"/>" +
               $"<path d=\"{look.Mark}\" fill=\"none\" stroke=\"{ink}\" stroke-width=\"1.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg>";
    }

    private static string E(string s) => WebUtility.HtmlEncode(s);
}
