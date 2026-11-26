using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using Gordium.Revit.Addin;
using Gordium.Revit.Reading;
using Gordium.Worker;

namespace Gordium.Revit.PaneRenders;

/// <summary>The egress audit (a hands-on read of what an architect meets): for each check answer given, every row's
/// place in the list, its cards and its detail page as text, and the pane's states as pictures: What to fix, By code,
/// the questions card, one detail page per egress group, and the printable summary. Run as
/// <c>Gordium.Revit.PaneRenders.exe &lt;out&gt; --audit &lt;answer.json&gt;...</c>.</summary>
internal static class Audit
{
    /// <summary>The egress groups an architect meets, by the Building Code section their rules come from.</summary>
    private static readonly (string Tag, string Rule)[] Groups =
    [
        ("travel", "bc_1017"), ("one_exit", "bc_1006_3"), ("two_exits", "bc_1006_2"), ("corridors", "bc_1020"),
        ("exit_width", "bc_1005"), ("doors", "bc_1010"), ("exit_access", "bc_1016"), ("stairs", "bc_1007"),
    ];

    internal static int Run(string output, IReadOnlyList<string> answers, Func<CheckResult, Dictionary<string, string>> labelsOf,
                            Action<Pane, string, int, Action<Pane>> step, IReadOnlyList<SetupField> fields)
    {
        Directory.CreateDirectory(output);
        var when = new DateTime(2026, 11, 25, 10, 0, 0);
        foreach (var path in answers)
        {
            var name = Path.GetFileNameWithoutExtension(path);
            var answer = Program.Load(path);
            var rows = ResultRows.Build(answer, "New Construction", [], null);
            var views = rows.Views!;
            var labels = labelsOf(answer);
            var placed = ResultList.Place(rows);
            var text = new StringBuilder();
            text.AppendLine($"# {name}: {placed.Count} results");
            text.AppendLine();
            text.AppendLine("## What to fix: groups");
            foreach (var g in views.Fix)
            {
                text.AppendLine($"- [{g.Kind}] {g.Title} | {g.Sub} | {g.Rows.Count} results, {g.Cards.Count} cards");
                foreach (var c in g.Cards)
                    text.AppendLine($"    - {c.Headline} ({c.Rows.Count} results){(c.Field is null ? "" : $" field {c.Field}")}");
            }
            text.AppendLine();
            var answerGroup = views.Fix.FirstOrDefault(g => g.Kind == FixKind.Answer);
            if (answerGroup is not null)
            {
                text.AppendLine("## Questions card");
                foreach (var q in ProjectQuestions.Of(answerGroup, fields))
                    text.AppendLine($"- {q.Card.Headline} | {ProjectQuestions.Affects(q.Affects)} | " +
                                    (q.Field is null ? ProjectQuestions.NoField : $"{q.Field.Kind} \"{q.Field.Label}\""));
                text.AppendLine();
            }
            text.AppendLine("## Every result: its place, its cards, its detail page");
            var elementLabels = placed.SelectMany(p => p.Row.Elements).Distinct(StringComparer.Ordinal)
                                      .ToDictionary(u => u, u => labels.TryGetValue(u, out var l) ? l : u, StringComparer.Ordinal);
            for (var i = 0; i < placed.Count; i++)
            {
                var p = placed[i];
                var cards = ResultViews.CardsOf(views, p.Row.Id, fields);
                var detail = Details.Of(p, i, placed.Count, elementLabels, null);
                var page = DetailPages.Of(detail, p, cards);
                text.AppendLine($"=== [{p.Section} / {p.Status}] {p.Row.Name}");
                text.AppendLine($"    id: {p.Row.Id}");
                foreach (var c in cards)
                    text.AppendLine($"    card: {c.Kind}: {c.Headline}{(c.Field is null ? "" : $" ({c.Field})")}");
                foreach (var line in page.Text().Split('\n'))
                    text.AppendLine("    " + line);
            }
            File.WriteAllText(Path.Combine(output, name + "_pages.txt"), text.ToString(), new UTF8Encoding(false));

            // the pictures, light theme, the pane's docked width
            const string title = "Four-unit apartment";
            step(new Pane(PanelTheme.Light, []), $"{name}_a_what_to_fix", 900, pn => pn.Show(title, when, rows, labels, fields));
            step(new Pane(PanelTheme.Light, []), $"{name}_b_by_code", 900, pn =>
            {
                pn.Show(title, when, rows, labels, fields);
                pn.UseView(ResultsViewKind.ByCode);
            });
            if (answerGroup is not null)
            {
                step(new Pane(PanelTheme.Light, []), $"{name}_c_questions", 1400, pn =>
                {
                    pn.Show(title, when, rows, labels, fields);       // the questions card opens at first
                    pn.Toggle(ResultViewList.MoreQuestionsKey);
                });
                // "Is there an ADU?" answered in the card: Yes brings in its follow-ups, No leaves them out
                if (answerGroup.Cards.Any(c => c.DependsOn?.Field == "facts.accessory_dwelling_unit"))
                    foreach (var (tag, value) in new[] { ("adu_yes", "Yes"), ("adu_no", "No") })
                        step(new Pane(PanelTheme.Light, []), $"{name}_c_questions_{tag}", 1400, pn =>
                        {
                            pn.Show(title, when, rows, labels, fields);
                            pn.Toggle(ResultViewList.MoreQuestionsKey);
                            pn.Answer(Marks.AccessoryDwellingUnit, value);
                        });
            }
            foreach (var kind in new[] { FixKind.Decide, FixKind.Measure })
                if (views.Fix.FirstOrDefault(g => g.Kind == kind) is { } open)
                    step(new Pane(PanelTheme.Light, []), $"{name}_c_{kind.ToString().ToLowerInvariant()}_open", 1400, pn =>
                    {
                        pn.Show(title, when, rows, labels, fields);
                        pn.Toggle(ResultViewList.GroupKey(open));
                    });
            foreach (var (tag, rule) in Groups)
            {
                var pick = placed.FirstOrDefault(p => p.Row.Id.Contains("." + rule, StringComparison.Ordinal) && p.Section != ListSection.Complies)
                           ?? placed.FirstOrDefault(p => p.Row.Id.Contains("." + rule, StringComparison.Ordinal));
                if (pick is null)
                    continue;
                step(new Pane(PanelTheme.Light, []), $"{name}_d_detail_{tag}", 900, pn =>
                {
                    pn.Show(title, when, rows, labels, fields);
                    pn.OpenResult(pick.Row.Id);
                });
            }
            File.WriteAllText(Path.Combine(output, name + "_e_summary.html"),
                              ComplianceSummary.Html(rows, title, when, when.AddMinutes(3)), new UTF8Encoding(false));
        }
        // what changed between the first answer given and the last (the architect answering the questions card)
        if (answers.Count > 1)
        {
            var first = ResultRows.Build(Program.Load(answers[0]), "New Construction", [], null);
            var lastAnswer = Program.Load(answers[^1]);
            var last = ResultRows.Build(lastAnswer, "New Construction", [], null);
            step(new Pane(PanelTheme.Light, []), "z_what_changed_after_answers", 900, pn =>
            {
                pn.Show("Four-unit apartment", when, first, labelsOf(lastAnswer), fields, key: "audit:what-changed");
                pn.Show("Four-unit apartment", when.AddMinutes(9), last, labelsOf(lastAnswer), fields, key: "audit:what-changed");
            });
        }
        return 0;
    }
}
