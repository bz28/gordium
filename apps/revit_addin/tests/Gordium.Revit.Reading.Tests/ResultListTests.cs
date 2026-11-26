using System.Diagnostics;
using Gordium.Worker;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The results list's decisions (ResultList, PR 3 of docs/revit/ui_design_pass.md section 4 row 3): every row
/// in exactly one place, a failure never below a needs review, a stale list with no green, filters and the search
/// showing exactly the matching rows, Up/Down over rows only, Ctrl+C as the text file says it, and 1,000 rows placed
/// and filtered in under 100 ms.</summary>
public sealed class ResultListTests
{
    private static ResultRow Row(string id, Verdict v, string? howFar = null, string name = "Front yard", string? section = "§325-8",
                                 string[]? elements = null, string? words = null) =>
        new(id, name, v, words ?? v switch
        {
            Verdict.DoesNotComply => "DOES NOT COMPLY",
            Verdict.Complies => "complies",
            Verdict.NotChecked => "not checked",
            Verdict.NotApplicable => "not applicable",
            _ => "needs review",
        }, ResultRows.ToneOf(v, Verdicts.Word(v)), null, howFar, null, section, [], elements ?? []);

    private static ResultGroup Group(string key, params ResultRow[] rows) => new(key, key, rows.Length, false, Tone.Review, rows, []);

    private static ResultGroup Lines(string key, params (string Title, ResultRow[] Rows)[] lines) =>
        new(key, key, lines.Length, false, Tone.Review, [], lines.Select(l => new ResultLine(l.Title, Tone.Review, false, l.Rows)).ToList());

    private static ResultModel Model(params ResultGroup[] groups) => new(Verdict.NeedsReview, "h", "c", [], groups, "");

    /// <summary>The worker's shape: zoning's groups by status, then egress's tiers as lines; and some rows the worker
    /// grouped where their own verdict doesn't belong (a failure in "complies", a needs review in "complies"): the
    /// list places each by its own verdict.</summary>
    private static ResultModel Mixed() => Model(
        Group("fails", Row("z.front", Verdict.DoesNotComply, "0'-6\" short"), Row("z.side", Verdict.DoesNotComply, "2'-6\" short")),
        Group("review", Row("z.height", Verdict.NeedsReview), Row("z.odd", Verdict.NeedsReview, words: "needs review (the checker said \"maybe\")")),
        Group("complies", Row("z.lot", Verdict.Complies), Row("z.lost_fail", Verdict.DoesNotComply, "+570 sf"), Row("z.lost_review", Verdict.NeedsReview)),
        Group("not_checked", Row("z.parking", Verdict.NotChecked)),
        Lines("egress:fails", ("Bedroom 3 › Window 5", [Row("e.w5", Verdict.DoesNotComply, name: "Bedroom 3 › Window 5 · Escape opening (R319.2.1)", section: "R319.2.1")])),
        Lines("egress:review", ("Front door: 2 need review", [Row("e.d1", Verdict.NeedsReview, name: "Front door · One egress door", section: "R318.2", elements: ["uid-door"]),
                                                             Row("e.d2", Verdict.NeedsReview, name: "Front door · Side-hinged", section: "R318.2", elements: ["uid-door"])])),
        Lines("egress:by_hand", ("Not read from the model yet: handrails (2 rules)", [Row("e.h1", Verdict.NeedsReview, name: "Handrail height", section: "R320.2"),
                                                                                       Row("e.h2", Verdict.NeedsReview, name: "Handrail grip", section: "R320.4")]),
                                ("Not checked yet by Gordium: 86 code sections", [Row("e.sections", Verdict.NeedsReview, name: "Not checked yet", section: null)])),
        Lines("egress:complies", ("Bedroom 1 › Window 2", [Row("e.w2a", Verdict.Complies, name: "Window 2 · Sill height", section: "R319.2.3"),
                                                          Row("e.w2b", Verdict.NotApplicable, name: "Window 2 · Area well", section: "R319.3")])));

    private static List<ResultRow> AllRows(ResultModel m) => m.Groups.SelectMany(g => g.AllRows).ToList();

    private static List<string> Ids(IEnumerable<ListEntry> entries) => entries.OfType<ListRowEntry>().Select(e => e.Row.Row.Id).ToList();

    private static readonly HashSet<ListSection> Everything = [.. Enum.GetValues<ListSection>()];

    [Fact]
    public void Every_row_is_in_exactly_one_place_and_shown_exactly_once()
    {
        var model = Mixed();
        var placed = ResultList.Place(model);
        Assert.Equal(AllRows(model).Select(r => r.Id).Order(), placed.Select(p => p.Row.Id).Order());     // each once, none made
        Assert.Equal(placed.Count, placed.Select(p => p.Row.Id).Distinct().Count());
        // the whole list, every place open: each row exactly once
        var shown = Ids(ResultList.Layout(placed, ListFilter.All, null, null, stale: false, opened: Everything));
        Assert.Equal(placed.Select(p => p.Row.Id), shown);
        // the three filters split the rows between them: each row under exactly one
        var byFilter = new[] { ListFilter.Fails, ListFilter.Review, ListFilter.Complies }
            .SelectMany(f => Ids(ResultList.Layout(placed, f, null, null, stale: false))).ToList();
        Assert.Equal(shown.Order(), byFilter.Order());
    }

    [Fact]
    public void A_failure_is_never_below_a_needs_review_and_only_a_pass_or_not_applicable_is_folded()
    {
        var placed = ResultList.Place(Mixed());
        var lastFail = placed.ToList().FindLastIndex(p => p.Row.Verdict == Verdict.DoesNotComply);
        var firstOther = placed.ToList().FindIndex(p => p.Row.Verdict != Verdict.DoesNotComply);
        Assert.True(lastFail < firstOther);
        // the failure the worker grouped under "complies" is with the failures; the review grouped there is a review
        Assert.Equal(ListSection.Fails, placed.Single(p => p.Row.Id == "z.lost_fail").Section);
        Assert.Equal(ListSection.Review, placed.Single(p => p.Row.Id == "z.lost_review").Section);
        Assert.Equal(ListSection.Review, placed.Single(p => p.Row.Id == "z.odd").Section);       // a word not known: never folded
        // places come in order, and every needs review or not checked is above every pass
        Assert.Equal(placed.Select(p => p.Section).Order(), placed.Select(p => p.Section));
        var lastOpen = placed.ToList().FindLastIndex(p => p.Row.Verdict is Verdict.NeedsReview or Verdict.NotChecked);
        var firstPass = placed.ToList().FindIndex(p => p.Row.Verdict is Verdict.Complies or Verdict.NotApplicable);
        Assert.True(lastOpen < firstPass);
        // folded by default: the complies place alone, and it holds nothing but passes and not applicable
        var layout = ResultList.Layout(placed, ListFilter.All, null, null, stale: false);
        var folded = Assert.Single(layout.OfType<ListHeading>(), h => h.Folded);
        Assert.Equal(ListSection.Complies, folded.Section);
        Assert.All(placed.Where(p => p.Section == ListSection.Complies), p => Assert.Contains(p.Row.Verdict, new[] { Verdict.Complies, Verdict.NotApplicable }));
        // the failures can't be folded, even if asked
        // review round 1: no place but complies can be folded, by a click or by anything kept from an earlier check
        // (grouping.py: needs review and check by hand are lines that are shown, never a fold)
        foreach (var opened in new IReadOnlySet<ListSection>?[] { null, Everything, new HashSet<ListSection>() })
        {
            var any = ResultList.Layout(placed, ListFilter.All, null, null, false, opened);
            Assert.All(any.OfType<ListHeading>().Where(h => h.Section != ListSection.Complies), h => Assert.False(h.Folded || h.Foldable));
            Assert.True(any.OfType<ListHeading>().Single(h => h.Section == ListSection.Complies).Foldable);
            Assert.Equal(placed.Count(p => p.Section != ListSection.Complies),
                         Ids(any).Count(id => placed.Single(p => p.Row.Id == id).Section != ListSection.Complies));
        }
        var view = Addin("ResultsView.cs");
        Assert.DoesNotContain("_closed", view, StringComparison.Ordinal);
        Assert.Contains("        if (section != ListSection.Complies)\n            return;\n        if (!_opened.Remove(section))", view, StringComparison.Ordinal);
    }

    [Fact]
    public void Every_verdict_has_one_place()
    {
        foreach (var v in Enum.GetValues<Verdict>())
            foreach (var byHand in new[] { false, true })
            {
                var s = ResultList.SectionOf(v, byHand);
                Assert.Equal(v switch
                {
                    Verdict.DoesNotComply => ListSection.Fails,
                    Verdict.Complies or Verdict.NotApplicable => ListSection.Complies,
                    Verdict.NotChecked => ListSection.ByHand,
                    _ => byHand ? ListSection.ByHand : ListSection.Review,
                }, s);
            }
        // the worker's tier 3 (egress:by_hand) is check by hand; zoning's review is review
        var placed = ResultList.Place(Mixed());
        Assert.Equal(ListSection.ByHand, placed.Single(p => p.Row.Id == "e.h1").Section);
        Assert.Equal(ListSection.ByHand, placed.Single(p => p.Row.Id == "z.parking").Section);
        Assert.Equal(ListSection.Review, placed.Single(p => p.Row.Id == "e.d1").Section);
        // and the review place, the worker's tier 2, comes before check by hand
        Assert.True(placed.ToList().FindLastIndex(p => p.Section == ListSection.Review) < placed.ToList().FindIndex(p => p.Section == ListSection.ByHand));
    }

    [Fact]
    public void Failures_are_largest_how_far_off_first_where_the_worker_gives_a_length()
    {
        var placed = ResultList.Place(Mixed());
        // 2'-6" short, then 0'-6" short, then those with no length (room here "+570 sf", none) in the worker's order
        Assert.Equal(["z.side", "z.front", "z.lost_fail", "e.w5"],
                     placed.Where(p => p.Section == ListSection.Fails).Select(p => p.Row.Id));
        Assert.Equal(2.5, ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, "2'-6\" short")));
        Assert.Equal(2.5, ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, "−2'-6\"")));
        Assert.Equal(11.25 / 12, ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, "at least 0'-11 1/4\" short")));
        Assert.Equal(1.5, ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, "1'-6\" over")));
        Assert.Equal(2 + 11.5 / 12, ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, "2'-11 1/2\" short (still 0'-11 3/8\" short if the tax-map lines are 2 ft off the other way)")));
        Assert.Equal(1012.0, ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, "1,012'-0\" short")));
        // room to spare, at the limit, an area, a ratio, nothing: no size (never compared with a length)
        foreach (var words in new[] { "+2'-0 5/8\"", "≥ +5'-0 5/8\"", "at limit", "+570 sf", "−1,033 sf", "+3.34%", "−1.04%",
                                      "+1'-11 3/4\" (0'-0 1/4\" short if the tax-map lines are 2 ft off)", "" })
            Assert.Null(ResultList.HowFarOff(Row("a", Verdict.DoesNotComply, words)));
        Assert.Null(ResultList.HowFarOff(Row("a", Verdict.DoesNotComply)));
    }

    [Fact]
    public void A_stale_list_has_no_green()
    {
        var model = Mixed();
        var stale = ResultRows.Stale(model, new DateTime(2026, 11, 22, 14, 32, 0));
        var placed = ResultList.Place(stale);
        Assert.All(placed, p => Assert.Equal(PanelStatus.Stale, p.Status));
        var layout = ResultList.Layout(placed, ListFilter.All, null, null, stale: true, opened: Everything);
        foreach (var e in layout)
            Assert.Equal(PanelStatus.Stale, e switch
            {
                ListHeading h => h.Status,
                ListSubheading s => s.Status,
                ListRowEntry r => r.Row.Status,
                _ => throw new InvalidOperationException(),
            });
        Assert.All(ResultList.Chips(placed, stale: true), c => Assert.True(c.Status is null or PanelStatus.Stale));
        // stale changes only the colour: every row is in the same place as before the model changed
        Assert.Equal(ResultList.Place(model).Select(p => (p.Row.Id, p.Section)), placed.Select(p => (p.Row.Id, p.Section)));
        // and fresh, green is only on a row the worker said complies, and on the complies place only when all comply
        var fresh = ResultList.Place(model);
        Assert.All(fresh.Where(p => p.Status == PanelStatus.Complies), p => Assert.Equal(Verdict.Complies, p.Row.Verdict));
        Assert.Equal(PanelStatus.NotApplicable, ResultList.StatusOf(ListSection.Complies, fresh.Where(p => p.Section == ListSection.Complies).ToList(), false));
        Assert.Equal("Complies or not applicable", ResultList.Title(ListSection.Complies, fresh.Where(p => p.Section == ListSection.Complies)));
    }

    [Fact]
    public void A_row_shows_only_its_own_verdict()
    {
        // the glyph is the row's own tone's (never its group's, its line's or its place's), and its words the worker's
        var model = Mixed();
        var rows = AllRows(model).ToDictionary(r => r.Id);
        foreach (var p in ResultList.Place(model))
        {
            Assert.Same(rows[p.Row.Id], p.Row);
            Assert.Equal(StatusLook.Of(rows[p.Row.Id].Tone, stale: false), p.Status);
        }
    }

    [Fact]
    public void Each_filter_shows_exactly_its_rows()
    {
        var placed = ResultList.Place(Mixed());
        foreach (var f in Enum.GetValues<ListFilter>())
        {
            var expect = placed.Where(p => f switch
            {
                ListFilter.All => true,
                ListFilter.Fails => p.Row.Verdict == Verdict.DoesNotComply,
                ListFilter.Review => p.Row.Verdict is Verdict.NeedsReview or Verdict.NotChecked,
                ListFilter.Complies => p.Row.Verdict is Verdict.Complies or Verdict.NotApplicable,
                _ => false,
            }).Select(p => p.Row.Id).ToList();
            var layout = ResultList.Layout(placed, f, null, null, false, opened: f == ListFilter.All ? Everything : null);
            Assert.Equal(expect, Ids(layout));
            if (f != ListFilter.All)
                Assert.All(layout.OfType<ListHeading>(), h => Assert.False(h.Folded || h.Foldable));   // a match never folded away
        }
        // the complies filter shows what complies though its place is folded with no filter
        Assert.Equal(["z.lot", "e.w2a", "e.w2b"], Ids(ResultList.Layout(placed, ListFilter.Complies, null, null, false)));
    }

    [Fact]
    public void The_search_matches_rule_names_sections_and_element_names_and_nothing_else()
    {
        var placed = ResultList.Place(Mixed());
        var labels = new Dictionary<string, string> { ["uid-door"] = "Door D06" };
        List<string> Find(string q, ListFilter f = ListFilter.All) => Ids(ResultList.Layout(placed, f, q, labels, false));
        Assert.Equal(["e.h1", "e.h2"], Find("handrail"));                            // the name, any case
        Assert.Equal(["e.d1", "e.d2"], Find("r318.2"));                              // the section
        Assert.Equal(["e.d1", "e.d2"], Find("d06"));                                 // an element's label
        Assert.Equal(["e.d1"], Find("door  egress"));                                // every word, any order
        Assert.Empty(Find("uid-door"));                                              // never a UniqueId
        Assert.Empty(Ids(ResultList.Layout(placed, ListFilter.All, "uid-door", new Dictionary<string, string>(), false)));   // nor one with no label
        Assert.Empty(Find("short"));                                                 // never the figures or how far
        Assert.Equal(["z.lot"], Find("front yard", ListFilter.Complies));            // with a filter: both
        Assert.Equal(placed.Select(p => p.Row.Id), Ids(ResultList.Layout(placed, ListFilter.All, "   ", labels, false, opened: Everything)));
        // a match in the folded place is shown, never hidden by the fold
        Assert.Equal(["e.w2a"], Find("sill"));
        // brute force: for every term the list shows exactly the rows whose name, section or labels hold it
        foreach (var q in new[] { "window", "yard", "r3", "front", "x", "not", "§" })
            Assert.Equal(placed.Where(p => new[] { p.Row.Name, p.Row.Section ?? "" }.Concat(p.Row.Elements.Select(e => labels.GetValueOrDefault(e) ?? ""))
                                           .Any(s => s.Contains(q, StringComparison.OrdinalIgnoreCase))).Select(p => p.Row.Id),
                         Find(q));
    }

    [Fact]
    public void Sub_headings_are_the_workers_lines_and_a_line_of_one_row_is_named_by_its_part()
    {
        var layout = ResultList.Layout(ResultList.Place(Mixed()), ListFilter.All, null, null, false, opened: Everything);
        var subs = layout.OfType<ListSubheading>().Select(s => s.Title).ToList();
        Assert.Contains("Front door: 2 need review", subs);
        Assert.Contains("Not read from the model yet: handrails (2 rules)", subs);
        Assert.DoesNotContain("Not checked yet by Gordium: 86 code sections", subs);    // one row: named by its part, never counted
        Assert.DoesNotContain("Bedroom 3 › Window 5", subs);                            // the failures: one run, no lines
        // each sub-heading is right above the rows of its line
        var at = layout.ToList().FindIndex(e => e is ListSubheading { Title: "Front door: 2 need review" });
        Assert.Equal(["e.d1", "e.d2"], Ids(layout.Skip(at + 1).TakeWhile(e => e is ListRowEntry)));
        // headings say how many rows they show
        Assert.Equal(4, layout.OfType<ListHeading>().Single(h => h.Section == ListSection.Fails).Rows);
    }

    [Fact]
    public void A_line_title_heads_its_rows_only_where_its_worker_tier_puts_them_all()
    {
        // review round 1: the worker's complies line holds a row the add-in reads as needs review (a word it doesn't
        // know): that row is with the reviews, and neither it nor the line's other rows are under the line's words
        var odd = Row("e.w2c", Verdict.NeedsReview, name: "Window 2 · Opening control", words: "needs review (the checker said \"maybe\")");
        var model = Model(
            Lines("egress:review", ("Front door: 2 need review", [Row("e.d1", Verdict.NeedsReview, name: "Front door · One egress door"),
                                                                 Row("e.d2", Verdict.NeedsReview, name: "Front door · Side-hinged")])),
            Lines("egress:complies", ("Window 2: 2 comply · 1 doesn't apply", [Row("e.w2a", Verdict.Complies), Row("e.w2b", Verdict.NotApplicable), odd]),
                                     ("Window 3: 2 comply", [Row("e.w3a", Verdict.Complies), Row("e.w3b", Verdict.Complies)])));
        var layout = ResultList.Layout(ResultList.Place(model), ListFilter.All, null, null, false, opened: Everything);
        var subs = layout.OfType<ListSubheading>().Select(s => s.Title).ToList();
        // review round 2: the moved row and its line's other rows each under the part's name, which counts nothing
        Assert.Equal(["Front door: 2 need review", "Window 2", "Window 2", "Window 3: 2 comply"], subs);
        var at = layout.ToList().FindIndex(e => e is ListRowEntry { Row.Row.Id: "e.w2c" });
        Assert.Equal("Window 2", Assert.IsType<ListSubheading>(layout[at - 1]).Title);         // never under "Front door"
        Assert.Equal(ListSection.Review, ((ListRowEntry)layout[at]).Row.Section);
        EveryRunHeadedByItsOwnSource(layout);
        // a zoning group's title is never over a row it doesn't place (a review the worker grouped under "complies")
        var zoning = Model(Group("review", Row("z.h", Verdict.NeedsReview)), Group("complies", Row("z.c", Verdict.Complies), Row("z.r", Verdict.NeedsReview)));
        var z = ResultList.Layout(ResultList.Place(zoning), ListFilter.All, null, null, false, opened: Everything);
        Assert.DoesNotContain(z.OfType<ListSubheading>(), s => s.Title == "complies");
        Assert.Equal(ListSection.Review, ResultList.PlaceOf("review"));
        Assert.Equal(ListSection.ByHand, ResultList.PlaceOf("egress:by_hand"));
        Assert.Equal(ListSection.ByHand, ResultList.PlaceOf("not_covered"));
        Assert.Null(ResultList.PlaceOf("egress"));                                   // a law waiting for rooms
    }

    /// <summary>For every row outside the failures, the nearest sub-heading above it in its place is its own source's
    /// (a run never reads as more rows of the run before).</summary>
    private static void EveryRunHeadedByItsOwnSource(IReadOnlyList<ListEntry> layout)
    {
        ListSubheading? sub = null;
        foreach (var e in layout)
            switch (e)
            {
                case ListHeading:
                    sub = null;
                    break;
                case ListSubheading s:
                    sub = s;
                    break;
                case ListRowEntry { Row.Section: not ListSection.Fails } r:
                    Assert.True(sub?.Key == r.Row.SourceKey, $"{r.Row.Row.Id} is under {sub?.Title ?? "no sub-heading"}, not its own {r.Row.Source}");
                    break;
            }
    }

    [Fact]
    public void Every_run_has_its_own_sub_heading_and_a_law_waiting_for_rooms_keeps_its_name()
    {
        // review round 2: each run headed by its own source, in the mixed model, filtered and searched too
        var placed = ResultList.Place(Mixed());
        foreach (var f in Enum.GetValues<ListFilter>())
            foreach (var q in new[] { null, "window", "front", "handrail" })
                EveryRunHeadedByItsOwnSource(ResultList.Layout(placed, f, q, null, false, opened: Everything));
        // a line of one row is named by its part, never counted ("Not checked yet by Gordium", not "...: 86 code sections")
        var subs = ResultList.Layout(placed, ListFilter.All, null, null, false, opened: Everything).OfType<ListSubheading>().Select(s => s.Title).ToList();
        Assert.Contains("Not checked yet by Gordium", subs);
        // a law still waiting for rooms (present.grouped's tail: key "egress", no tier) under its own law's name, not
        // run on under zoning's group before it
        var waiting = new ResultGroup("egress", "Egress (NY State Residential Code 2025)", 2, false, Tone.Review,
                                      [Row("w.1", Verdict.NeedsReview, name: "Waiting 1"), Row("w.2", Verdict.NeedsReview, name: "Waiting 2")], []);
        var model = Model(Group("review", Row("z.h", Verdict.NeedsReview)), waiting);
        var layout = ResultList.Layout(ResultList.Place(model), ListFilter.All, null, null, false, opened: Everything);
        EveryRunHeadedByItsOwnSource(layout);
        Assert.Equal(["review", "Egress (NY State Residential Code 2025)"], layout.OfType<ListSubheading>().Select(s => s.Title));
        // split across places it still says only its law's name
        var split = Model(waiting with { Rows = [Row("w.1", Verdict.NeedsReview), Row("w.2", Verdict.NotChecked)] });
        Assert.All(ResultList.Layout(ResultList.Place(split), ListFilter.All, null, null, false).OfType<ListSubheading>(),
                   s => Assert.Equal("Egress (NY State Residential Code 2025)", s.Title));
        // a law group moved out of its tier says its law alone; zoning's says "Zoning"
        var lawRow = new ListRow(Row("x", Verdict.NeedsReview), ListSection.Review, PanelStatus.Review, "Egress · Complies", "g:egress:complies", 2, false, ListSection.Complies);
        Assert.Equal("Egress", ResultList.RunTitle(lawRow, ListSection.Review, 1));
        Assert.Equal("Zoning", ResultList.RunTitle(lawRow with { Source = "Complies", SourceKey = "g:complies" }, ListSection.Review, 1));
    }

    [Fact]
    public void The_lists_keys_act_only_on_a_row_or_the_list_and_sub_headings_draw_their_glyph()
    {
        // review round 1: Space on the Details fold's header (inside the list) opens it, never zooms to the row selected
        Assert.True(ResultList.ListTakesKey(onRow: true, onList: false));
        Assert.True(ResultList.ListTakesKey(onRow: false, onList: true));
        Assert.False(ResultList.ListTakesKey(onRow: false, onList: false));
        var view = Addin("ResultsView.cs");
        var keys = view[view.IndexOf("    private void ListKeys(", StringComparison.Ordinal)..];
        Assert.StartsWith("    private void ListKeys(object sender, I.KeyEventArgs e)\n    {\n        // only a key on a row, or on the list itself", keys, StringComparison.Ordinal);
        // a row, or an opener of the two results views (UI polish PR 3 review round 1: the keyboard opens what a click does);
        // never a fold after the rows
        Assert.Contains("var on = Within<C.ListBoxItem>(e.OriginalSource)?.DataContext;\n", keys, StringComparison.Ordinal);
        Assert.Contains("        if (!ResultList.ListTakesKey(onRow: on is RowItem or FixGroupItem or FixCardItem or CodeNodeItem or QuestionItem or MoreQuestionsItem or AnswerFootItem,\n" +
                        "                                     onList: ReferenceEquals(e.OriginalSource, _list)))\n            return;", keys, StringComparison.Ordinal);
        Assert.DoesNotContain("FoldItem", keys[..keys.IndexOf("return;", StringComparison.Ordinal)], StringComparison.Ordinal);
        // the add-in half of the keyboard fix (review round 2): an opener is focusable and drawn where the keyboard is,
        // it stays selected (never sent to Revit), and a key on it opens or folds it with the keyboard kept on it
        Assert.Contains("        if (!ctrl && at >= 0 && at < _entries.Count && ResultViewList.KeyToggles(_entries[at], e.Key.ToString()) is { } toggles)\n" +
                        "        {\n            ToggleOpen(toggles);\n            FocusEntry(at);", keys, StringComparison.Ordinal);
        var selected = view[view.IndexOf("    private void Selected()", StringComparison.Ordinal)..];
        Assert.Contains("_list.SelectedItem is not null and not (FixGroupItem or FixCardItem or CodeNodeItem or QuestionItem or MoreQuestionsItem or AnswerFootItem)", selected[..selected.IndexOf("_select(", StringComparison.Ordinal)], StringComparison.Ordinal);
        Assert.Contains("FixGroupItem or FixCardItem or CodeNodeItem or QuestionItem or MoreQuestionsItem or AnswerFootItem => \"list.opener\"", Addin("ResultsList.cs"), StringComparison.Ordinal);
        var stylesText = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "PanelStyles.xaml"));
        var opener = stylesText[stylesText.IndexOf("x:Key=\"list.opener\"", StringComparison.Ordinal)..];
        opener = opener[..opener.IndexOf("</Style>", StringComparison.Ordinal)];
        Assert.DoesNotContain("Focusable", opener, StringComparison.Ordinal);
        Assert.Contains("<Trigger Property=\"IsKeyboardFocused\" Value=\"True\">\n              <Setter TargetName=\"Frame\" Property=\"BorderBrush\" Value=\"{DynamicResource accent}\" />", opener, StringComparison.Ordinal);
        Assert.Contains("<Setter Property=\"FocusVisualStyle\" Value=\"{x:Null}\" />", opener, StringComparison.Ordinal);
        // Back returns to the place the detail was opened from, a relayout to a result's first place
        var back = view[view.IndexOf("    public void Back()", StringComparison.Ordinal)..];
        Assert.Contains("var at = _list.SelectedItem is RowItem s && s.Row.Row.Id == id ? _list.SelectedIndex", back, StringComparison.Ordinal);
        Assert.Contains("selected ??= row;", view, StringComparison.Ordinal);
        // a sub-heading's status is drawn, as its doc says (its place's glyph; the clock once stale)
        var entries = Addin("ResultsList.cs");
        var sub = entries[entries.IndexOf("    private static W.UIElement Sub(SubItem item)", StringComparison.Ordinal)..];
        sub = sub[..sub.IndexOf("\n    }\n", StringComparison.Ordinal)];
        Assert.Contains("var glyph = PanelLook.Glyph(item.Sub.Status, 11);", sub, StringComparison.Ordinal);
        Assert.Contains("line.Children.Add(glyph);", sub, StringComparison.Ordinal);
    }

    [Fact]
    public void Up_and_down_move_over_rows_only()
    {
        var layout = ResultList.Layout(ResultList.Place(Mixed()), ListFilter.All, null, null, false, opened: Everything);
        var rows = Enumerable.Range(0, layout.Count).Where(i => layout[i] is ListRowEntry).ToList();
        Assert.Equal(rows[0], ResultList.Next(layout, -1, 1));                     // nothing selected: Down is the first row
        Assert.Equal(rows[^1], ResultList.Next(layout, -1, -1));                   // Up the last
        for (var n = 0; n + 1 < rows.Count; n++)
        {
            Assert.Equal(rows[n + 1], ResultList.Next(layout, rows[n], 1));        // a heading between is skipped
            Assert.Equal(rows[n], ResultList.Next(layout, rows[n + 1], -1));
        }
        Assert.Equal(rows[^1], ResultList.Next(layout, rows[^1], 1));              // the ends stay
        Assert.Equal(rows[0], ResultList.Next(layout, rows[0], -1));
        Assert.Equal(-1, ResultList.Next([new ListHeading(ListSection.Fails, "t", 0, false, false, PanelStatus.Fails)], -1, 1));
        Assert.Throws<ArgumentOutOfRangeException>(() => ResultList.Next(layout, 0, 2));
    }

    [Fact]
    public void A_rows_second_line_says_its_verdict_when_its_heading_doesnt_then_its_figures_or_cause()
    {
        var fails = new ResultRow("a", "Front yard", Verdict.DoesNotComply, "DOES NOT COMPLY", Tone.Fails, "22'-6\" measured, ≥ 25'-0\" allowed",
                                  "2'-6\" short", "r", "§325-8", [], []);
        Assert.Equal("22'-6\" measured, ≥ 25'-0\" allowed · 2'-6\" short", ResultList.SecondLine(fails));
        Assert.Equal("2'-6\" short", ResultList.SecondLine(fails with { Figures = null }));
        Assert.Equal("r", ResultList.SecondLine(fails with { Figures = null, HowFar = null }));
        Assert.Equal("", ResultList.SecondLine(fails with { Figures = null, HowFar = null, Reason = null }));
        // a verdict its place's heading doesn't say is said: not checked, not applicable, a word not known
        Assert.Equal("not checked · waiting on the lot", ResultList.SecondLine(Row("b", Verdict.NotChecked) with { Reason = "waiting on the lot" }));
        Assert.Equal("not applicable", ResultList.SecondLine(Row("c", Verdict.NotApplicable)));
        Assert.Equal("needs review (the checker said \"maybe\")", ResultList.SecondLine(Row("d", Verdict.NeedsReview, words: "needs review (the checker said \"maybe\")")));
    }

    [Fact]
    public void Copy_is_the_row_as_the_text_file_writes_it()
    {
        var row = Row("z.front", Verdict.DoesNotComply, "2'-6\" short", elements: ["uid-house", "uid-gone"]);
        var labels = new Dictionary<string, string> { ["uid-house"] = "Walls id 341207" };
        // ResultText.Row writes row.Line(uid => Label(doc, uid)); a uid with no label is the uid, as there
        Assert.Equal(row.Line(uid => labels.GetValueOrDefault(uid)), ResultList.CopyText(row, labels, staleSince: null));
        Assert.Equal("[DOES NOT COMPLY] Front yard [Walls id 341207, uid-gone]", ResultList.CopyText(row, labels, null));
        // stale: said, so a copied verdict is never read as the model's now
        Assert.Equal("[DOES NOT COMPLY] Front yard [Walls id 341207, uid-gone] (checked 14:32, before the model changed)",
                     ResultList.CopyText(row, labels, new DateTime(2026, 11, 22, 14, 32, 0)));
    }

    private static string Addin(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file)).Replace("\r\n", "\n", StringComparison.Ordinal);

    [Fact]
    public void A_click_selects_without_zooming_and_only_show_zooms()
    {
        // the add-in (Revit-only, not built here): a row selected sends Select, which never calls ShowElements; Show
        // (the button, or Space) sends Zoom, which does
        var pane = Addin("ResultsPane.cs");
        Assert.Contains("new ResultsView(Zoom, Select, CheckAgain, OpenProjectInformation, Card, SetUp, _theme, SaveAnswers, MoreTime)", pane, StringComparison.Ordinal);
        Assert.Contains("private static void Select(ResultRow row) => Post(\"Select in model\", ui => ShowElements(ui, row, zoom: false));", pane, StringComparison.Ordinal);
        Assert.Contains("private static void Zoom(ResultRow row) => Post(\"Show in model\", ui => ShowElements(ui, row, zoom: true));", pane, StringComparison.Ordinal);
        Assert.Contains("        if (zoom)\n            uidoc.ShowElements(found);", pane, StringComparison.Ordinal);
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(pane, @"\.ShowElements\("));
        var view = Addin("ResultsView.cs");
        Assert.Contains("        if (!_quiet)\n            _select(row.Row.Row);", view, StringComparison.Ordinal);     // the click and Up/Down
        Assert.Contains("_list.SelectionChanged += (_, _) => Selected();", view, StringComparison.Ordinal);
        // Show alone zooms: the row's Show (or Space) in the list, and Show in its detail (DetailView)
        Assert.Equal(2, System.Text.RegularExpressions.Regex.Matches(view, @"_zoom\(").Count);
        Assert.Contains("        _zoom(uid is null ? row.Row : row.Row with { Elements = [uid] });", view, StringComparison.Ordinal);
        Assert.Contains("            case I.Key.Space when SelectedRow is { } row:\n                ShowRow(row);", view, StringComparison.Ordinal);
    }

    [Fact]
    public void The_view_draws_the_lists_decisions_and_stays_virtualized()
    {
        var view = Addin("ResultsView.cs");
        var entries = Addin("ResultsList.cs");
        var styles = Addin("PanelStyles.xaml");
        // the rows, their order, filters, search, keys and copy are ResultList's (tested here), never the view's own
        Assert.Contains("_placed = ResultList.Place(model);", view, StringComparison.Ordinal);
        // the two results views' entries are ResultViewList's (UI polish PR 3, tested in ResultViewListTests); the plain
        // list (an answer without them) is ResultList's
        Assert.Contains("var layout = _content?.Model?.Views is { } views\n" +
                        "            ? ResultViewList.Layout(views, _placed, _view, _openView, _search.Text, labels, stale, _content?.Questions)\n" +
                        "            : ResultList.WithCauses(ResultList.Layout(_placed, _filter, _search.Text, labels, stale, _opened),\n" +
                        "                                    _summary is not null && AllCards.Count > 0, _filter, _search.Text);\n" +
                        "        _entries = _summary is null ? layout : ResultList.WithSummary(layout);", view, StringComparison.Ordinal);
        Assert.Contains("FocusEntry(ResultList.Next(_entries, at, e.Key == I.Key.Down ? 1 : -1));", view, StringComparison.Ordinal);
        Assert.Contains("ResultList.CopyText(row.Row, _content?.Labels, _content?.Model?.Stale is null ? null : _content.When,", view, StringComparison.Ordinal);
        // each row's glyph and bar are its placed status (stale: the clock and the hatch), never a tone of the view's
        Assert.Contains("var glyph = PanelLook.Glyph(p.Status, 14);", entries, StringComparison.Ordinal);
        Assert.Contains("p.Status == PanelStatus.Stale ? PanelLook.StaleHatch : StatusLook.Colour(p.Status)", entries, StringComparison.Ordinal);
        Assert.DoesNotContain("StatusLook.Of(", entries, StringComparison.Ordinal);
        // virtualized: the list in the Grid's star row (a list in a ScrollViewer builds every row), its panel virtualizing
        Assert.Contains("_results.RowDefinitions.Add(new C.RowDefinition { Height = new W.GridLength(1, W.GridUnitType.Star) });", view, StringComparison.Ordinal);
        Assert.Contains("C.Grid.SetRow(_list, 1);", view, StringComparison.Ordinal);
        Assert.Contains("_list.SetResourceReference(StyleProperty, \"list\");", view, StringComparison.Ordinal);
        Assert.Contains("<VirtualizingStackPanel IsVirtualizing=\"True\" VirtualizationMode=\"Recycling\" />", styles, StringComparison.Ordinal);
        Assert.Contains("<Setter Property=\"ScrollViewer.CanContentScroll\" Value=\"True\" />", styles, StringComparison.Ordinal);
        // a heading is never selected or focused
        Assert.Contains("<Setter Property=\"Focusable\" Value=\"False\" />", styles[styles.IndexOf("x:Key=\"list.heading\"", StringComparison.Ordinal)..], StringComparison.Ordinal);
    }

    [Fact]
    public void The_summary_scrolls_with_the_list_and_only_the_toolbar_is_pinned()
    {
        // Revit trial (106 Ithaca Rd, pane ~340 by 430 px): pinned, the state and the count bar filled the whole pane and
        // the list got 0 px. The summary is now the list's first entry, never moved to or selected
        var layout = ResultList.Layout(ResultList.Place(Mixed()), ListFilter.All, null, null, false, opened: Everything);
        var with = ResultList.WithSummary(layout);
        Assert.IsType<ListSummary>(with[0]);
        Assert.Equal(layout, with.Skip(1));
        Assert.Single(with.OfType<ListSummary>());
        Assert.Equal(with.ToList().FindIndex(e => e is ListRowEntry), ResultList.Next(with, -1, 1));       // Down: the first row
        Assert.Equal(with.ToList().FindIndex(e => e is ListRowEntry), ResultList.Next(with, ResultList.Next(with, -1, 1), -1));   // Up: stays
        // the view: two Grid rows (the toolbar, the list), the summary built into the list's first entry, not the pinned area
        var view = Addin("ResultsView.cs");
        Assert.Equal(2, System.Text.RegularExpressions.Regex.Matches(view, @"_results\.RowDefinitions\.Add\(").Count);
        Assert.Contains("_summary = () => Summary(model, parts, stale);", view, StringComparison.Ordinal);
        Assert.Contains("                case ListSummary:\n                    items.Add(new SummaryItem(this, _summary!));", view, StringComparison.Ordinal);
        Assert.DoesNotContain("_results.Children.Add(_summary)", view, StringComparison.Ordinal);
        Assert.Contains("C.Grid.SetRow(tools, 0);", view, StringComparison.Ordinal);
        // the stale banner and the grey state are in the summary (never green: StatusLook.Of(model.StateTone, stale))
        var summary = Between(view, "    private W.UIElement Summary(ResultModel model", "\n    }\n");
        Assert.Contains("case PanelPart.Stale:", summary, StringComparison.Ordinal);
        Assert.Contains("var state = StatusLook.Of(model.StateTone, stale);", summary, StringComparison.Ordinal);
        // review round 6: the status line (problems and what to do, the action last) wraps, capped at three lines so
        // it never pushes the list off, the last trimmed, the whole on hover
        Assert.Contains("_status.TextWrapping = W.TextWrapping.Wrap;", view, StringComparison.Ordinal);
        Assert.DoesNotContain("_status.TextWrapping = W.TextWrapping.NoWrap;", view, StringComparison.Ordinal);
        Assert.Contains("_status.MaxHeight = 3 * 1.4 * PanelTokens.TypeOf(Caption).Size;", view, StringComparison.Ordinal);
        Assert.Contains("_status.TextTrimming = W.TextTrimming.CharacterEllipsis;", view, StringComparison.Ordinal);
        Assert.Contains("_status.ToolTip = words.Length == 0 ? null : words;", view, StringComparison.Ordinal);
        // the summary's entry is never selected
        var entries = Addin("ResultsList.cs");
        // review round 6: each item's doc comment above its own class
        var beforeFold = entries[..entries.IndexOf("internal sealed class FoldItem(", StringComparison.Ordinal)].TrimEnd();
        Assert.EndsWith("shows it as the architect left it.</summary>", beforeFold, StringComparison.Ordinal);
        var summaryItem = entries[..entries.IndexOf("internal sealed class SummaryItem(", StringComparison.Ordinal)];
        summaryItem = summaryItem[summaryItem.LastIndexOf("\n}\n", StringComparison.Ordinal)..];      // from the class before it
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(summaryItem, "<summary>"));
        Assert.Contains("box.MouseLeftButtonDown += (_, e) => e.Handled = true;", Between(entries, "    private static W.UIElement Summary(SummaryItem item)", "\n    }\n"), StringComparison.Ordinal);
    }

    private static string Between(string text, string start, string end)
    {
        var from = text.IndexOf(start, StringComparison.Ordinal);
        Assert.True(from >= 0, "no " + start);
        var to = text.IndexOf(end, from, StringComparison.Ordinal);
        return text[from..to];
    }

    [Fact]
    public void A_rows_name_has_its_whole_width_and_its_figures_are_never_cut()
    {
        // Revit trial: the section in a column beside the name squeezed it to a word a line, and the figures beside Show
        // were cut ("28.3% measured, \u2264 25..."). The name's line holds only the glyph and the name; the figures wrap,
        // never trimmed; the section has its own line, trimmed with the whole on hover, Show at its right
        var entries = Addin("ResultsList.cs");
        var row = Between(entries, "    private static W.UIElement Row(RowItem item)", "\n    }\n");
        var first = Between(row, "        // line 1:", "        // line 2:");
        Assert.DoesNotContain("Section", first, StringComparison.Ordinal);
        Assert.DoesNotContain("C.Dock.Right", first, StringComparison.Ordinal);
        Assert.Contains("Text = r.Name, FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap", first, StringComparison.Ordinal);
        var second = Between(row, "        // line 2:", "        // line 3:");
        Assert.Contains("var cause = Typed(new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap,", second, StringComparison.Ordinal);
        Assert.DoesNotContain("Show", second, StringComparison.Ordinal);
        var trimmed = Between(second, "            if (!figures)", "            text.Children.Add(cause);");
        Assert.Contains("cause.TextTrimming = W.TextTrimming.CharacterEllipsis;", trimmed, StringComparison.Ordinal);   // a cause alone
        Assert.Single(System.Text.RegularExpressions.Regex.Matches(second, @"\.TextTrimming ="));                          // never the figures
        var third = row[row.IndexOf("        // line 3:", StringComparison.Ordinal)..];
        Assert.Contains("var sec = Muted(r.Section ?? \"\");", third, StringComparison.Ordinal);
        Assert.Contains("sec.TextTrimming = W.TextTrimming.CharacterEllipsis;", third, StringComparison.Ordinal);
        Assert.Contains("sec.ToolTip = r.Section;", third, StringComparison.Ordinal);
        Assert.Contains("C.DockPanel.SetDock(show, C.Dock.Right);", third, StringComparison.Ordinal);
    }

    [Fact]
    public void A_run_title_that_restates_its_place_is_its_laws_name()
    {
        // Revit trial: NEEDS REVIEW · 77 rows, then a sub-heading "Needs review" (zoning's group's own title)
        var model = Model(new ResultGroup("review", "Needs review", 2, false, Tone.Review, [Row("z.a", Verdict.NeedsReview), Row("z.b", Verdict.NeedsReview)], []),
                          new ResultGroup("complies", "Complies", 1, true, Tone.Complies, [Row("z.c", Verdict.Complies)], []),
                          new ResultGroup("not_checked", "Not checked", 1, false, Tone.Review, [Row("z.n", Verdict.NotChecked)], []));
        var layout = ResultList.Layout(ResultList.Place(model), ListFilter.All, null, null, false, opened: Everything);
        Assert.Equal(["Zoning", "Not checked", "Zoning"], layout.OfType<ListSubheading>().Select(s => s.Title));
        EveryRunHeadedByItsOwnSource(layout);
        // the round-2 rule holds: every run headed, a worker line's counted words only in its own place
        var line = new ListRow(Row("x", Verdict.NeedsReview), ListSection.Review, PanelStatus.Review, "Front door: 2 need review", "l:egress:review/f", 2, true, ListSection.Review);
        Assert.Equal("Front door: 2 need review", ResultList.RunTitle(line, ListSection.Review, 2, "Needs review"));
        Assert.Equal("Egress", ResultList.RunTitle(line with { Source = "Egress · Needs review", FromLine = false }, ListSection.Review, 2, "Egress · needs review"));
    }

    [Fact]
    public void A_thousand_rows_place_filter_and_search_in_under_100_ms()
    {
        var rng = new Random(7);
        var verdicts = Enum.GetValues<Verdict>();
        var groups = Enumerable.Range(0, 10).Select(g => g % 2 == 0
            ? Group("zoning" + g, Enumerable.Range(0, 100).Select(n => Row($"z{g}.{n}", verdicts[rng.Next(verdicts.Length)],
                    rng.Next(3) == 0 ? $"{rng.Next(20)}'-{rng.Next(12)}\" short" : null, name: $"Rule {g}.{n}", section: $"§325-{n}",
                    elements: [$"uid{n}"])).ToArray())
            : Lines($"egress{g}:{(g % 4 == 1 ? "review" : "by_hand")}", Enumerable.Range(0, 10).Select(l => ($"Line {g}.{l}",
                    Enumerable.Range(0, 10).Select(n => Row($"e{g}.{l}.{n}", verdicts[rng.Next(verdicts.Length)], name: $"Window {l} · rule {n}",
                                                            section: $"R319.{n}", elements: [$"uid{n}"])).ToArray())).ToArray())).ToArray();
        var model = Model(groups);
        var labels = Enumerable.Range(0, 100).ToDictionary(n => $"uid{n}", n => $"Room {n}");
        Assert.Equal(1000, AllRows(model).Count);
        void Once()
        {
            var placed = ResultList.Place(model);
            foreach (var f in Enum.GetValues<ListFilter>())
                _ = ResultList.Layout(placed, f, null, labels, false, opened: Everything);
            _ = ResultList.Layout(placed, ListFilter.All, "room 4", labels, false);
            _ = ResultList.Layout(placed, ListFilter.Review, "window rule", labels, false);
        }
        Once();                                                                // warmed (the JIT is not the list's)
        var times = new List<double>();
        for (var n = 0; n < 5; n++)
        {
            var sw = Stopwatch.StartNew();
            Once();
            times.Add(sw.Elapsed.TotalMilliseconds);
        }
        var median = times.Order().ElementAt(2);                              // one slow run (a GC, the machine busy) is not the list's
        Assert.True(median < 100, $"placing and filtering 1,000 rows took {median:F1} ms (runs: {string.Join(", ", times.Select(t => t.ToString("F1")))})");
        // and every one of the 1,000 is shown exactly once
        Assert.Equal(1000, Ids(ResultList.Layout(ResultList.Place(model), ListFilter.All, null, null, false, opened: Everything)).Distinct().Count());
    }
}
