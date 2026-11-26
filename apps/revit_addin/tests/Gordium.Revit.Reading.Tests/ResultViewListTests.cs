using System.Text;
using System.Text.Json;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The two results views as the pane's list draws them (ResultViewList; UI polish PR 3), on the four-unit
/// apartment's real answer: what starts open, that every result can be reached in either view (opening the path to
/// it), that a glyph is never green for anything unsettled and never once stale, and that a search shows the plain
/// list's matches in both views.</summary>
public sealed class ResultViewListTests
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());

    private static ResultModel Apartment()
    {
        var file = Path.Combine(Env.Repo, "apps", "revit_addin", "tests", "Gordium.Revit.Reading.Tests", "answers", "four_unit_apartment_check_answer.json");
        var doc = JsonDocument.Parse(File.ReadAllText(file, Encoding.UTF8));
        return ResultRows.Build(CheckResult.Parse(new WorkerAnswer(doc.RootElement.GetProperty("result").Clone(), About)), "New Construction", [], null);
    }

    private static IReadOnlyList<ListEntry> Layout(ResultModel m, ResultsViewKind view, IEnumerable<string> open, string? query = null) =>
        ResultViewList.Layout(m.Views!, ResultList.Place(m), view, open.ToHashSet(), query, null, m.Stale is not null);

    [Fact]
    public void What_to_fix_opens_on_the_first_group_of_work_and_by_code_on_each_document()
    {
        var m = Apartment();
        var open = ResultViewList.OpenAtFirst(m.Views!).ToList();
        var fix = Layout(m, ResultsViewKind.WhatToFix, open);
        var groups = fix.OfType<FixGroupEntry>().ToList();
        Assert.Equal(m.Views!.Fix.Count, groups.Count);                       // every group is listed
        Assert.True(groups[0].Open);
        Assert.Equal(FixKind.Answer, groups[0].Group.Kind);
        Assert.All(groups.Skip(1), g => Assert.False(g.Open));
        Assert.Equal(ProjectQuestions.Of(groups[0].Group, null).Count, fix.OfType<FixCardEntry>().Count());   // the follow-ups held back (FollowUpQuestionsTests)
        var code = Layout(m, ResultsViewKind.ByCode, open).OfType<CodeNodeEntry>().ToList();
        Assert.All(code.Where(n => n.Depth == 0), n => Assert.True(n.Open));
        Assert.Equal(m.Views!.Code.Count, code.Count(n => n.Depth == 0));
    }

    [Fact]
    public void Every_result_can_be_reached_in_either_view()
    {
        var m = Apartment();
        foreach (var view in new[] { ResultsViewKind.WhatToFix, ResultsViewKind.ByCode })
            foreach (var row in ResultList.Place(m))
            {
                var path = ResultViewList.PathTo(m.Views!, view, row.Row.Id);
                Assert.NotEmpty(path);
                Assert.Contains(Layout(m, view, path), e => e is ListRowEntry r && r.Row.Row.Id == row.Row.Id);
            }
    }

    [Fact]
    public void Nothing_unsettled_is_drawn_green_and_nothing_is_green_once_stale()
    {
        var m = Apartment();
        var everything = m.Views!.Fix.Select(ResultViewList.GroupKey)
            .Concat(m.Views.Fix.SelectMany(g => g.Cards).Select(ResultViewList.CardKey))
            .Concat(m.Views.Code.SelectMany((d, i) => Keys(d, "/" + i))).ToList();
        foreach (var model in new[] { m, ResultRows.Stale(m, DateTime.Now) })
        {
            var stale = model.Stale is not null;
            var entries = Layout(model, ResultsViewKind.WhatToFix, everything).Concat(Layout(model, ResultsViewKind.ByCode, everything)).ToList();
            foreach (var e in entries)
            {
                var (status, rows) = e switch
                {
                    FixGroupEntry g => (g.Status, g.Group.Rows),
                    FixCardEntry c => (c.Status, c.Card.Rows),
                    CodeNodeEntry n => (n.Status, Rows(n.Node).ToList()),
                    _ => ((PanelStatus?)null, (IReadOnlyList<ResultRow>)[]),
                };
                if (status is not { } s)
                    continue;
                if (stale)
                    Assert.Equal(PanelStatus.Stale, s);
                if (s == PanelStatus.Complies)
                    Assert.All(rows, r => Assert.Contains(r.Verdict, new[] { Verdict.Complies, Verdict.NotApplicable }));
                if (e is CodeNodeEntry node && s == PanelStatus.Complies)
                    Assert.Equal(CodeState.Complies, node.Node.State);
                if (e is FixGroupEntry { Group.Kind: FixKind.NotChecked } && !stale)
                    Assert.Equal(PanelStatus.NotChecked, s);
            }
        }
    }

    private static IEnumerable<string> Keys(CodeNode n, string key) =>
        n.Children.SelectMany((c, i) => Keys(c, key + "/" + i)).Prepend(key);

    private static IEnumerable<ResultRow> Rows(CodeNode n) => n.Rows.Concat(n.Children.SelectMany(Rows));

    [Fact]
    public void A_search_shows_the_same_matching_results_in_both_views()
    {
        var m = Apartment();
        var fix = Layout(m, ResultsViewKind.WhatToFix, [], "exit").OfType<ListRowEntry>().Select(r => r.Row.Row.Id).ToList();
        var code = Layout(m, ResultsViewKind.ByCode, [], "exit").OfType<ListRowEntry>().Select(r => r.Row.Row.Id).ToList();
        Assert.NotEmpty(fix);
        Assert.Equal(fix, code);
    }

    [Fact]
    public void The_not_checked_status_is_its_own_glyph_and_word_never_green()
    {
        Assert.Equal("Not checked yet by Gordium", StatusLook.Word(PanelStatus.NotChecked));
        Assert.NotEqual(StatusLook.Colour(PanelStatus.Complies), StatusLook.Colour(PanelStatus.NotChecked));
        Assert.Null(StatusLook.GlyphOf(PanelStatus.NotChecked).Fill);
        Assert.Equal(PanelStatus.NotChecked, ResultViewList.StatusOf(CodeState.NotCheckedYet, stale: false));
        Assert.Equal(PanelStatus.Review, ResultViewList.StatusOf(FixKind.Answer, [], stale: false));
    }

    /// <summary>A result asked for by two open cards is listed under both, and Previous / Next in its detail still
    /// visits every result once, in order, never looping back to its first place (review round 1).</summary>
    [Fact]
    public void Stepping_through_details_visits_each_result_once_when_two_open_cards_share_one()
    {
        var m = Apartment();
        var cards = m.Views!.Fix.SelectMany(g => g.Cards).ToList();
        var (a, b) = cards.SelectMany((x, i) => cards.Skip(i + 1).Select(y => (x, y)))
                          .First(p => p.x.Rows.Any(r => p.y.Rows.Any(q => q.Id == r.Id)));
        var groups = m.Views.Fix.Where(g => g.Cards.Contains(a) || g.Cards.Contains(b)).Select(ResultViewList.GroupKey);
        var entries = Layout(m, ResultsViewKind.WhatToFix, [.. groups, ResultViewList.CardKey(a), ResultViewList.CardKey(b)]);
        var listed = entries.OfType<ListRowEntry>().Select(e => e.Row.Row.Id).ToList();
        Assert.True(listed.Count > listed.Distinct().Count());                    // a result listed twice
        var (rows, index) = Details.Among(entries, listed[0]);
        var seen = new List<string>();
        for (var at = index; at >= 0 && at < rows.Count; at = Details.Among(entries, rows[at].Row.Id).Index + 1)
        {
            Assert.DoesNotContain(rows[at].Row.Id, seen);
            seen.Add(rows[at].Row.Id);
        }
        Assert.Equal(listed.Distinct(), seen);
    }

    /// <summary>The keyboard reaches and opens what a click does (review round 1): Up/Down stop on each group, card
    /// and node; Enter, Space or Right opens one, Left folds it; opening along the way reaches every result.</summary>
    [Fact]
    public void The_keyboard_reaches_every_opener_and_through_them_every_result()
    {
        var m = Apartment();
        foreach (var view in new[] { ResultsViewKind.WhatToFix, ResultsViewKind.ByCode })
        {
            var open = ResultViewList.OpenAtFirst(m.Views!).ToHashSet();
            var entries = Layout(m, view, open);
            Assert.NotEqual(-1, ResultList.Next(entries, -1, 1));
            Assert.All(entries.Where(e => e is FixGroupEntry or FixCardEntry or CodeNodeEntry), e => Assert.True(ResultList.Stops(e)));
            // open every opener the keyboard lands on, Down by Down, until nothing new opens: every result is then listed
            for (var round = 0; round < 12; round++)
            {
                var more = entries.Select(e => ResultViewList.KeyToggles(e, "Right")).OfType<string>().ToList();
                if (more.Count == 0)
                    break;
                open.UnionWith(more);
                entries = Layout(m, view, open);
            }
            var listed = entries.OfType<ListRowEntry>().Select(e => e.Row.Row.Id).ToHashSet();
            Assert.All(ResultList.Place(m), r => Assert.Contains(r.Row.Id, listed));
            var first = entries.First(e => e is FixGroupEntry or CodeNodeEntry);
            Assert.NotNull(ResultViewList.KeyToggles(first, "Left"));
            Assert.NotNull(ResultViewList.KeyToggles(first, "Return"));
            Assert.Null(ResultViewList.KeyToggles(first, "Right"));               // already open
        }
    }

    /// <summary>The view is remembered per project across sessions (change 17); a file that can't be read, or a word
    /// it doesn't know, starts on What to fix.</summary>
    [Fact]
    public void The_view_is_remembered_per_project_and_a_bad_file_starts_on_what_to_fix()
    {
        var dir = Path.Combine(Path.GetTempPath(), "gordium_views_" + Guid.NewGuid().ToString("N"));
        var file = Path.Combine(dir, "results_views.json");
        try
        {
            var first = new ViewChoices(file);
            Assert.Equal(ResultsViewKind.WhatToFix, first.Of("doc-a"));
            first.Set("doc-a", ResultsViewKind.ByCode);
            var again = new ViewChoices(file);
            Assert.Equal(ResultsViewKind.ByCode, again.Of("doc-a"));
            Assert.Equal(ResultsViewKind.WhatToFix, again.Of("doc-b"));
            File.WriteAllText(file, "{ not json", Encoding.UTF8);
            Assert.Equal(ResultsViewKind.WhatToFix, new ViewChoices(file).Of("doc-a"));
            File.WriteAllText(file, "{\"doc-a\": \"Sideways\", \"doc-b\": \"7\"}", Encoding.UTF8);
            Assert.Equal(ResultsViewKind.WhatToFix, new ViewChoices(file).Of("doc-a"));
            Assert.Equal(ResultsViewKind.WhatToFix, new ViewChoices(file).Of("doc-b"));
        }
        finally
        {
            if (Directory.Exists(dir))
                Directory.Delete(dir, recursive: true);
        }
    }
}
