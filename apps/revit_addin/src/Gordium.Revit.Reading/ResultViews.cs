using Gordium.Worker;
using System.Text.Json;

namespace Gordium.Revit.Reading;

// The results as two views of one answer (UI polish changes 17 to 21, 23 to 27 and 33 to 37; Ben approved 2026-11-23):
// "What to fix" groups what needs review by what the architect can do next, from the checker's own asks
// (result.view.items[].asks, docs/revit/checker_ui_data.md); "By code" places every row in its document's chapters
// and sections (items[].in_code, view.contents). Revit-free: what each view says is decided here and tested; the
// Revit layer only draws it. The rules: every row is in both views, never hidden (a row the data can't place goes in a
// group or node of its own, said so); every count is a count of the checker's rows; nothing here works out a verdict;
// a group or chapter is never green while anything in it fails, needs review or isn't checked yet.

/// <summary>The two views (change 17), the first the default.</summary>
public enum ResultsViewKind { WhatToFix, ByCode }

/// <summary>What the architect can do about a group of results, in the order the groups are shown (change 21): what
/// fails first; then what needs review, by the kind of work; then what Gordium hasn't checked; then what complies or
/// doesn't apply (folded, so no row is ever out of the view).</summary>
public enum FixKind { Fails, Answer, Mark, FixModel, Survey, Measure, Decide, OpenQuestion, NotChecked, Done }

/// <summary>One thing to do, the checker's ask (<c>asks[]</c>, one key for every row asking the same), and the rows
/// waiting on it.</summary>
/// <param name="Key">The ask's key (rows with the same key ask the same thing), or the row's id for a row with no ask.</param>
/// <param name="Kind">Its group.</param>
/// <param name="Headline">What to do, in a few words (the ask's <c>headline</c>); a row with no ask: its name.</param>
/// <param name="Why">The checker's own words behind "Why?" (the ask's <c>why</c>, or the row's reason), or null.</param>
/// <param name="Field">The fact or mark that answers it (<c>building.occupancy_groups</c>, <c>doors[].exit</c>), or null.</param>
/// <param name="Elements">The elements it names (UniqueIds), each once.</param>
/// <param name="Rows">The rows waiting on it, each once, in the answer's order.</param>
public sealed record FixCard(string Key, FixKind Kind, string Headline, string? Why, string? Field,
                             IReadOnlyList<string> Elements, IReadOnlyList<ResultRow> Rows)
{
    private readonly string? _title;

    /// <summary>The card's one line in the list: its <see cref="Headline"/>, or, where the same words head other cards
    /// of its group, the rule its results are about ("Corridor width kept clear (BCNYS 1020.4)"), so the cards can be
    /// told apart (egress UI audit, finding 3: 29 cards read "Check this by hand: a person decides it"). The checker's
    /// words stay the headline: the detail page's steps and the card's tooltip say them.</summary>
    public string Title { get => _title ?? Headline; init => _title = value; }
}

/// <summary>One group of "What to fix": its kind, title, the cards in it and every row it holds (each once).</summary>
public sealed record FixGroup(FixKind Kind, string Title, string? Sub, IReadOnlyList<FixCard> Cards, IReadOnlyList<ResultRow> Rows)
{
    /// <summary>"See 8 results".</summary>
    public string SeeWords => Rows.Count == 1 ? "See 1 result" : $"See {Rows.Count} results";
}

/// <summary>A node's state in "By code", the worst inside it (change 34): fails, then needs review, then not checked
/// yet (a row Gordium didn't check, or a part of the document it has no rules for), then complies only when every row
/// inside complies and nothing inside is unchecked; doesn't apply when every row inside doesn't; nothing to check
/// (a definitions chapter, no rows) last.</summary>
public enum CodeState { Fails, Review, NotCheckedYet, Complies, NotApplicable, NothingToCheck }

/// <summary>What a node of "By code" is.</summary>
public enum CodeLevel { Document, Chapter, Section, Rule, Others }

/// <summary>One node of the "By code" tree: a document, chapter (or article), section, a rule with its rows, or a fold
/// of the parts Gordium hasn't checked ("30 other chapters"), each with its state from the rows inside.</summary>
/// <param name="Level">Document, chapter, section, rule, or a fold of greyed ones.</param>
/// <param name="Number">"10", "II", "1006", "325-8", a rule's piece "1006.2.1"; null for a document or a fold.</param>
/// <param name="Title">The document's, chapter's, section's or rule's title.</param>
/// <param name="Note">A document's "Governs this building: …" line, or null.</param>
/// <param name="State">The worst state inside (<see cref="ResultViews.StateOf"/>).</param>
/// <param name="Line">The status line: "62 need review · 26 sections not checked yet".</param>
/// <param name="Greyed">Gordium has no row here (not checked yet, or nothing to check): drawn greyed, never hidden.</param>
/// <param name="Children">The nodes inside, in the document's order (greyed runs folded).</param>
/// <param name="Rows">A rule's rows (its parts); empty above the rule.</param>
public sealed record CodeNode(CodeLevel Level, string? Number, string Title, string? Note, CodeState State, string Line,
                              bool Greyed, IReadOnlyList<CodeNode> Children, IReadOnlyList<ResultRow> Rows)
{
    /// <summary>What the document calls it, from its contents: "chapter", "article", "appendix", "section", or
    /// "part" (a piece of a section); a fold's is its nodes' when they share one, else "part".</summary>
    public string Kind { get; init; } = "part";

    /// <summary>The law's own words behind the governing book's <see cref="Note"/> (which_code's cited sections and
    /// quotes, as the which-code line's tooltip says them: <see cref="WhichCode.Tooltip"/>), or null (review round 3:
    /// the quotes are shown where the choice is).</summary>
    public string? NoteTooltip { get; init; }

    /// <summary>A document's scope note (change 24: "Gordium's Building Code egress rules are drafted for day care
    /// (Group I-4) so far…"), said once under the book its rows say it of, or null.</summary>
    public string? Scope { get; init; }
}

/// <summary>Both views of one answer, and the words at the top of either.</summary>
/// <param name="Summary">"98 need review · 8 not checked yet · 1 complies" (zero counts left out; change 18).</param>
/// <param name="Headline">What the state means (change 19).</param>
/// <param name="Fix">"What to fix": the groups in their order, only the ones with rows.</param>
/// <param name="Code">"By code": one node per document.</param>
public sealed record ResultViewsModel(string Summary, string Headline, IReadOnlyList<FixGroup> Fix, IReadOnlyList<CodeNode> Code)
{
    /// <summary>Whether By code says which code governs and why (a document's "Governs this building: …"): only then may
    /// the pane leave the which-code line off its top (UI polish PR 3 review round 3: with no contents, or no reason
    /// sent, the code choice would otherwise be shown nowhere).</summary>
    public bool ShowsWhichCode => Code.Any(d => d.Note is not null);

    /// <summary>The ids of the rows the scope note is said of (<see cref="ResultViews.DraftedForOneGroup"/>).</summary>
    public IReadOnlySet<string> Scoped { get; init; } = new HashSet<string>(StringComparer.Ordinal);

    /// <summary>The scope note (change 24), said once where it matters (the questions card and the book in By code),
    /// or null when no row says its rules are drafted for one group only.</summary>
    public string? Scope { get; init; }
}

public static class ResultViews
{
    /// <summary>The node of the rows the checker sends with no place in a document (<c>in_code</c>): the
    /// not-checked-yet gaps, the code choice. Shown last, never dropped.</summary>
    public const string Unplaced = "Other results";

    /// <summary>Both views of a check's answer. Every row of the answer is in both, once per place it is asked about
    /// in "What to fix" (a row waiting on two asks is in both cards, and once in each group's count) and exactly once
    /// in "By code".</summary>
    public static ResultViewsModel Build(CheckResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        var rows = result.Items.Select(i => (Item: i, Row: ResultRows.Row(i))).ToList();
        var scoped = rows.Where(r => DraftedForOneGroup(r.Item.Raw)).ToList();
        var fix = FixGroups(rows);
        // the results in review that wait on a question of the questions card (never more than there are)
        var answers = fix.Where(g => g.Kind == FixKind.Answer).ToList();
        var onQuestions = answers.SelectMany(g => g.Rows)
                                 .Where(r => r.Verdict == Verdict.NeedsReview).Select(r => r.Id).Distinct(StringComparer.Ordinal).Count();
        return new ResultViewsModel(Summary(rows.Select(r => r.Row.Verdict)),
                                    Headline(rows.Select(r => (r.Row.Verdict, Str(r.Item.Raw, "rule") ?? r.Row.Id)), onQuestions,
                                             answers.Sum(g => g.Cards.Count)),
                                    fix, CodeTree(result, rows, scoped.Select(r => r.Row).ToHashSet()))
        {
            Scope = scoped.Count == 0 ? null : ScopeWords(scoped.Count),
            Scoped = scoped.Select(r => r.Row.Id).ToHashSet(StringComparer.Ordinal),
        };
    }

    // ---- the scope note (change 24) ---------------------------------------------------------------------------

    /// <summary>The checker's words for a rule drafted for one occupancy group only ("this rulebook's rules are drafted
    /// for Group I-4 only", in a result's reason or an ask's why). Since #182 no New York rule says them; the note stays
    /// for a rulebook that does, and shows only then.</summary>
    public const string DraftedFor = "drafted for Group I-4 only";

    /// <summary>Whether the checker says of this row (its reason, or an ask's why) that its rules are drafted for Group
    /// I-4 only: the rows the scope note is said for.</summary>
    public static bool DraftedForOneGroup(JsonElement raw)
    {
        if (Str(raw, "reason")?.Contains(DraftedFor, StringComparison.Ordinal) == true)
            return true;
        return raw.ValueKind == JsonValueKind.Object && raw.TryGetProperty("asks", out var asks) && asks.ValueKind == JsonValueKind.Array
               && asks.EnumerateArray().Any(a => Str(a, "why")?.Contains(DraftedFor, StringComparison.Ordinal) == true);
    }

    /// <summary>The scope note in words, for the results that say it: how many, and what to do. Said of those results
    /// only, never of all egress (the Chapter 10 rules cover every group since #181 and #182).</summary>
    public static string ScopeWords(int results) =>
        (results == 1 ? "1 Building Code result is" : $"{results} Building Code results are") +
        " drafted for day care (Group I-4) only so far. For any other group, " + (results == 1 ? "it stays" : "they stay") +
        " Needs review: check " + (results == 1 ? "it" : "them") + " by hand.";

    // ---- the top: one summary line and the headline sentence --------------------------------------------------

    private static readonly (Verdict Verdict, string One, string Many)[] Counted =
    [
        (Verdict.DoesNotComply, "fails", "fail"),
        (Verdict.NeedsReview, "needs review", "need review"),
        (Verdict.NotChecked, "not checked yet", "not checked yet"),
        (Verdict.Complies, "complies", "comply"),
        (Verdict.NotApplicable, "doesn't apply", "don't apply"),
    ];

    /// <summary>"1 fails · 98 need review · 8 not checked yet · 1 complies", worst first, zero counts left out; every
    /// verdict the add-in knows is counted (an unknown word is already needs review).</summary>
    public static string Summary(IEnumerable<Verdict> verdicts)
    {
        var all = verdicts.ToList();
        var parts = Counted.Select(c => (c, n: all.Count(v => v == c.Verdict))).Where(x => x.n > 0)
                           .Select(x => $"{x.n} {(x.n == 1 ? x.c.One : x.c.Many)}").ToList();
        return parts.Count == 0 ? "No results" : string.Join(" · ", parts);
    }

    private static readonly (Verdict Verdict, string One, string Many)[] Past =
    [
        (Verdict.DoesNotComply, "failed", "failed"),
        (Verdict.NeedsReview, "needed review", "needed review"),
        (Verdict.NotChecked, "wasn't checked yet", "weren't checked yet"),
        (Verdict.Complies, "complied", "complied"),
        (Verdict.NotApplicable, "didn't apply", "didn't apply"),
    ];

    /// <summary>The summary line in the past tense, for results the model changed after (UI polish change 39: "1
    /// failed · 132 needed review"): what the check said then, never what holds now.</summary>
    public static string SummaryPast(IEnumerable<Verdict> verdicts)
    {
        var all = verdicts.ToList();
        var parts = Past.Select(c => (c, n: all.Count(v => v == c.Verdict))).Where(x => x.n > 0)
                        .Select(x => $"{x.n} {(x.n == 1 ? x.c.One : x.c.Many)}").ToList();
        return parts.Count == 0 ? "No results" : string.Join(" · ", parts);
    }

    /// <summary>The headline sentence (change 19): what fails first; else that nothing fails yet and how many results
    /// wait on the architect; never that the design complies (a check where everything Gordium checked complies still
    /// says Gordium doesn't check everything). <paramref name="onQuestions"/>: how many of the results in review wait on
    /// a question of the questions card (null: all of them, as the approved words say). Only those are said to wait on
    /// the questions (egress UI audit: "80 results can't be decided until the questions below are answered" with 2
    /// waiting on the one question left, the rest on marks and checks by hand).</summary>
    public static string Headline(IEnumerable<(Verdict Verdict, string Rule)> rows, int? onQuestions = null, int? questions = null)
    {
        var list = rows.ToList();
        var all = list.Select(r => r.Verdict).ToList();
        // the rules that fail, each once (a rule failing in 3 spaces is one rule)
        int fails = list.Where(r => r.Verdict == Verdict.DoesNotComply).Select(r => r.Rule).Distinct().Count(), review = all.Count(v => v == Verdict.NeedsReview),
            notChecked = all.Count(v => v == Verdict.NotChecked);
        if (fails > 0)
            return (fails == 1 ? "1 rule fails. Fix it first" : $"{fails} rules fail. Fix them first")
                   + (review == 0 ? "." : $"; {Results(review)} also need{(review == 1 ? "s" : "")} review.");
        if (review > 0)
        {
            var asked = Math.Min(onQuestions ?? review, review);
            // the card's own count: "the question below" when it asks one (review round 1)
            var below = questions == 1 ? "the question below" : "the questions below";
            return asked == review ? $"Nothing fails yet. {Results(review)} can't be decided until {below} {(questions == 1 ? "is" : "are")} answered."
                : asked == 0 ? $"Nothing fails yet. {Results(review)} need{(review == 1 ? "s" : "")} review: {(review == 1 ? "it" : "each")} says below what it needs."
                : $"Nothing fails yet. {Results(review)} need{(review == 1 ? "s" : "")} review; {asked} of them wait{(asked == 1 ? "s" : "")} on {below}.";
        }
        if (notChecked > 0)
            return $"Nothing fails and nothing needs review, but {Results(notChecked)} {(notChecked == 1 ? "is" : "are")} not checked yet by Gordium: check {(notChecked == 1 ? "it" : "them")} by hand.";
        return all.Count == 0
            ? "Gordium gave no results for this project."
            : "Every result Gordium checked complies. Gordium doesn't check every part of the code: see By code for what it covers.";
    }

    private static string Results(int n) => n == 1 ? "1 result" : $"{n} results";

    // ---- "What to fix" ------------------------------------------------------------------------------------------

    /// <summary>The kind of work an ask is: a fact on Project Information (<c>facts.</c> or <c>building.</c>) is a
    /// question to answer; any other mark is an element to mark; an unknown kind is a person's to decide (never
    /// dropped).</summary>
    public static FixKind KindOf(string? kind, string? field) => kind switch
    {
        "mark" when field is not null && (field.StartsWith("facts.", StringComparison.Ordinal) || field.StartsWith("building.", StringComparison.Ordinal)) => FixKind.Answer,
        "mark" => FixKind.Mark,
        "fix_model" => FixKind.FixModel,
        "survey" => FixKind.Survey,
        "measure" => FixKind.Measure,
        "open_question" => FixKind.OpenQuestion,
        _ => FixKind.Decide,
    };

    private static List<FixGroup> FixGroups(List<(CheckItem Item, ResultRow Row)> rows)
    {
        // card key -> (kind, headline, why, field, elements, rows), in the order first asked
        var cards = new Dictionary<(FixKind, string), (string Headline, string? Why, string? Field, List<string> Elements, List<ResultRow> Rows)>();
        var order = new List<(FixKind, string)>();
        void Add(FixKind kind, string key, string headline, string? why, string? field, IEnumerable<string> elements, ResultRow row)
        {
            if (!cards.TryGetValue((kind, key), out var c))
            {
                c = (headline, why, field, [], []);
                cards[(kind, key)] = c;
                order.Add((kind, key));
            }
            foreach (var e in elements)
                if (!c.Elements.Contains(e))
                    c.Elements.Add(e);
            if (!c.Rows.Contains(row))
                c.Rows.Add(row);
        }
        foreach (var (item, row) in rows)
        {
            switch (row.Verdict)
            {
                case Verdict.DoesNotComply:
                    Add(FixKind.Fails, "row:" + row.Id, row.Name, row.Reason, null, row.Elements, row);
                    continue;
                case Verdict.NotChecked:
                    Add(FixKind.NotChecked, "not_checked", "Not checked yet by Gordium", null, null, [], row);
                    continue;
                case Verdict.Complies or Verdict.NotApplicable:
                    Add(FixKind.Done, "done", "Complies or doesn't apply", null, null, [], row);
                    continue;
            }
            // needs review: each ask the checker made, or, with none (an older checker), the row itself for a person
            var asks = Asks(item.Raw);
            if (asks.Count == 0)
            {
                Add(FixKind.Decide, "row:" + row.Id, row.Name, row.Reason, null, row.Elements, row);
                continue;
            }
            foreach (var a in asks)
                Add(KindOf(a.Kind, a.Field), a.Key, a.Headline, a.Why, a.Field, a.Elements, row);
        }
        return order.GroupBy(k => k.Item1).OrderBy(g => g.Key).Select(g =>
        {
            var list = g.Select(k => (k, c: cards[k]))
                        .Select(x => new FixCard(x.k.Item2, x.k.Item1, x.c.Headline, x.c.Why, x.c.Field, x.c.Elements, x.c.Rows))
                        .OrderByDescending(c => c.Rows.Count).ToList();   // stable: ties keep the answer's order
            // cards of the group headed by the same words: each named by the rule its results are about, or, where two
            // would share that name (one rule on two elements), by its one result's whole name; else the words stay
            list = Named(list);
            var all = rows.Select(r => r.Row).Where(r => list.Any(c => c.Rows.Contains(r))).ToList();
            var (title, sub) = GroupWords(g.Key, list, all.Count);
            return new FixGroup(g.Key, title, sub, list, all);
        }).ToList();
    }

    /// <summary>The cards of one group, those headed by the same words named apart (<see cref="FixCard.Title"/>): by
    /// the rule their results are about; where that still leaves two alike, a one-result card by its result's whole name
    /// ("Level 1 › CORRIDOR L1 (3) · …"); a card that can't be told apart so keeps the checker's words (review round 1).</summary>
    public static List<FixCard> Named(IReadOnlyList<FixCard> cards)
    {
        ArgumentNullException.ThrowIfNull(cards);
        var repeated = cards.GroupBy(c => c.Headline, StringComparer.Ordinal).Where(x => x.Count() > 1).Select(x => x.Key).ToHashSet(StringComparer.Ordinal);
        var byRule = cards.Select(c => repeated.Contains(c.Headline) ? RuleOf(c.Rows) : null).ToList();
        var twice = byRule.OfType<string>().GroupBy(t => t, StringComparer.Ordinal).Where(x => x.Count() > 1).Select(x => x.Key).ToHashSet(StringComparer.Ordinal);
        var titles = cards.Select((c, i) => byRule[i] is not { } t ? null : !twice.Contains(t) ? t : c.Rows.Count == 1 ? c.Rows[0].Name : null).ToList();
        // a whole name shared too (or a card left with its words beside one renamed alike): those keep the checker's words
        var shared = titles.OfType<string>().GroupBy(t => t, StringComparer.Ordinal).Where(x => x.Count() > 1).Select(x => x.Key).ToHashSet(StringComparer.Ordinal);
        return [.. cards.Select((c, i) => titles[i] is { } t && !shared.Contains(t) ? c with { Title = t } : c)];
    }

    /// <summary>The rule a card's results are about, as their names end ("Egress · Corridor width kept clear (BCNYS
    /// 1020.4)" → "Corridor width kept clear (BCNYS 1020.4)"), when they are all about one; else null.</summary>
    public static string? RuleOf(IReadOnlyList<ResultRow> rows)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var rules = rows.Select(r => r.Name[(r.Name.LastIndexOf(" \u00B7 ", StringComparison.Ordinal) is var i and >= 0 ? i + 3 : 0)..].Trim())
                        .Distinct(StringComparer.Ordinal).ToList();
        return rules.Count == 1 && rules[0].Length > 0 ? rules[0] : null;
    }

    /// <summary>A group's title and its one sub line (strings.md, "What to fix": action groups).</summary>
    public static (string Title, string? Sub) GroupWords(FixKind kind, IReadOnlyList<FixCard> cards, int rows)
    {
        var n = cards.Count;
        string S(int k, string one, string many) => k == 1 ? one : many;
        return kind switch
        {
            FixKind.Fails => ($"Fails · {rows}", "What must change in the design."),
            FixKind.Answer => ($"Answer {n} {S(n, "question", "questions")} about the project", "Set on Project Information."),
            FixKind.Mark => ($"Mark {n} {S(n, "kind", "kinds")} of element", "Gordium can't tell these from the model until they are marked."),
            FixKind.FixModel => ($"Fix {n} {S(n, "thing", "things")} in the model", "As drawn, these can't be measured."),
            FixKind.Survey => ("Get a survey", "The property line is traced from the tax map (±2 ft)."),
            FixKind.Measure => ($"Measure {n} {S(n, "thing", "things")} by hand", "Gordium doesn't read or measure these yet."),
            FixKind.Decide => ($"{n} code {S(n, "question", "questions")} for you to decide", "The code leaves these to judgment. Gordium shows the words; you decide."),
            FixKind.OpenQuestion => ($"{n} open {S(n, "question", "questions")} about the law", "The law reads more than one way here, so these can't pass yet."),
            FixKind.NotChecked => ("Not checked yet by Gordium", $"{Results(rows)} Gordium has no rules for yet. Check these by hand."),
            _ => ($"Complies or doesn't apply · {rows}", null),
        };
    }

    /// <summary>The cards of What to fix that list row <paramref name="rowId"/>, in their groups' order: the checker's
    /// asks for it (a row in no card of asks, such as what fails, gives the group's own row card).</summary>
    public static IReadOnlyList<FixCard> CardsOf(ResultViewsModel model, string rowId)
    {
        ArgumentNullException.ThrowIfNull(model);
        return [.. model.Fix.SelectMany(g => g.Cards).Where(c => c.Rows.Any(r => r.Id == rowId))];
    }

    /// <summary>One ask as the checker sent it (<c>asks[]</c>).</summary>
    public sealed record Ask(string Kind, string Key, string Headline, string? Why, string? Field, IReadOnlyList<string> Elements);

    /// <summary>A row's asks; an ask without a key or a headline is not one the pane can show, so it is left out here
    /// and the row, if that leaves it none, is shown for a person to decide (never dropped).</summary>
    public static IReadOnlyList<Ask> Asks(JsonElement raw)
    {
        if (raw.ValueKind != JsonValueKind.Object || !raw.TryGetProperty("asks", out var asks) || asks.ValueKind != JsonValueKind.Array)
            return [];
        var list = new List<Ask>();
        foreach (var a in asks.EnumerateArray())
        {
            if (a.ValueKind != JsonValueKind.Object || Str(a, "key") is not { Length: > 0 } key || Str(a, "headline") is not { Length: > 0 } headline)
                continue;
            var elements = a.TryGetProperty("elements", out var es) && es.ValueKind == JsonValueKind.Array
                ? es.EnumerateArray().Where(e => e.ValueKind == JsonValueKind.String).Select(e => e.GetString()!).Distinct().ToList()
                : [];
            list.Add(new Ask(Str(a, "kind") ?? "decide", key, headline, Str(a, "why"), Str(a, "field"), elements));
        }
        return list;
    }

    private static string? Str(JsonElement o, string name) =>
        o.ValueKind == JsonValueKind.Object && o.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;

    // ---- "By code" ----------------------------------------------------------------------------------------------

    /// <summary>Where a row's rule is (<c>in_code</c>), or null.</summary>
    public sealed record InCode(string Document, string? Chapter, string? ChapterTitle, string? Section, string? SectionTitle,
                                string? Piece, string? PieceTitle);

    public static InCode? InCodeOf(JsonElement raw) =>
        raw.ValueKind == JsonValueKind.Object && raw.TryGetProperty("in_code", out var c) && c.ValueKind == JsonValueKind.Object
        && Str(c, "document") is { Length: > 0 } doc
            ? new InCode(doc, Str(c, "chapter"), Str(c, "chapter_title"), Str(c, "section"), Str(c, "section_title"),
                         Str(c, "piece"), Str(c, "piece_title"))
            : null;

    /// <summary>A section as the contents list it: its coverage, whether all of it was brought in, and its pieces
    /// Gordium has no rules for yet (<c>not_checked_yet</c>, <c>not_brought_in</c>).</summary>
    private sealed record ContentsSection(string Number, string Title, string Coverage, bool Whole, List<(string Id, string Title)> Unchecked);

    private sealed record ContentsChapter(string Number, string Kind, string Title, List<ContentsSection> Sections);

    private sealed record Contents(string Document, List<ContentsChapter> Chapters);

    private static readonly HashSet<string> UncheckedCoverage = new(StringComparer.Ordinal) { "not_checked_yet", "not_brought_in" };

    private static List<Contents> ContentsOf(JsonElement result)
    {
        var list = new List<Contents>();
        if (result.ValueKind != JsonValueKind.Object || !result.TryGetProperty("view", out var view) || view.ValueKind != JsonValueKind.Object
            || !view.TryGetProperty("contents", out var docs) || docs.ValueKind != JsonValueKind.Array)
            return list;
        foreach (var d in docs.EnumerateArray())
        {
            if (d.ValueKind != JsonValueKind.Object || Str(d, "document") is not { Length: > 0 } name)
                continue;
            var chapters = new List<ContentsChapter>();
            if (d.TryGetProperty("chapters", out var cs) && cs.ValueKind == JsonValueKind.Array)
                foreach (var c in cs.EnumerateArray().Where(c => c.ValueKind == JsonValueKind.Object))
                {
                    var sections = new List<ContentsSection>();
                    if (c.TryGetProperty("sections", out var ss) && ss.ValueKind == JsonValueKind.Array)
                        foreach (var s in ss.EnumerateArray().Where(s => s.ValueKind == JsonValueKind.Object))
                        {
                            // a piece not yet checked, or a section only partly brought in, keeps its section from
                            // green (change 34); "whole" missing is read as partly brought in, never as all of it
                            var notYet = new List<(string, string)>();
                            if (s.TryGetProperty("pieces", out var ps) && ps.ValueKind == JsonValueKind.Array)
                                foreach (var piece in ps.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.Object))
                                    if (UncheckedCoverage.Contains(Str(piece, "coverage") ?? "not_brought_in"))
                                        notYet.Add((Str(piece, "id") ?? "", Str(piece, "title") ?? ""));
                            var whole = s.TryGetProperty("whole", out var w) && w.ValueKind == JsonValueKind.True;
                            sections.Add(new ContentsSection(Str(s, "number") ?? "", Str(s, "title") ?? "",
                                                             Str(s, "coverage") ?? "not_brought_in", whole, notYet));
                        }
                    chapters.Add(new ContentsChapter(Str(c, "number") ?? "", Str(c, "kind") ?? "chapter", Str(c, "title") ?? "", sections));
                }
            list.Add(new Contents(name, chapters));
        }
        return list;
    }

    /// <summary>The governing code's title and why (<c>which_code</c>), or nulls.</summary>
    private static (string? Title, string? Why) WhichCode(JsonElement result) =>
        result.ValueKind == JsonValueKind.Object && result.TryGetProperty("which_code", out var w) && w.ValueKind == JsonValueKind.Object
            ? (Str(w, "title"), Str(w, "why"))
            : (null, null);

    private static List<CodeNode> CodeTree(CheckResult result, List<(CheckItem Item, ResultRow Row)> rows, HashSet<ResultRow> scoped)
    {
        var placed = rows.Select(r => (r.Row, In: InCodeOf(r.Item.Raw), Rule: Str(r.Item.Raw, "rule") ?? r.Row.Id,
                                       RuleName: Str(r.Item.Raw, "rule_name") ?? r.Row.Name)).ToList();
        var contents = ContentsOf(result.Raw);
        var (governs, why) = WhichCode(result.Raw);
        var used = new HashSet<ResultRow>();
        var docs = new List<CodeNode>();
        foreach (var doc in contents)
        {
            var mine = placed.Where(p => p.In?.Document == doc.Document).ToList();
            var isGoverning = governs is not null && doc.Document.StartsWith(governs, StringComparison.Ordinal);
            if (mine.Count == 0 && !isGoverning)
                continue;   // a book that governs nothing here and holds no row (the Residential Code of an apartment)
            var chapters = new List<CodeNode>();
            foreach (var chapter in doc.Chapters)
            {
                var (cn, ct, sections) = (chapter.Number, chapter.Title, chapter.Sections);
                var inChapter = mine.Where(p => p.In!.Chapter == cn).ToList();
                var secNodes = new List<CodeNode>();
                foreach (var sec in sections)
                {
                    var inSection = inChapter.Where(p => p.In!.Section == sec.Number).ToList();
                    secNodes.Add(inSection.Count == 0
                        ? Empty(CodeLevel.Section, sec.Number, sec.Title, NothingIn(sec)) with { Kind = "section" }
                        : Node(CodeLevel.Section, sec.Number, sec.Title, null, Fold([.. Rules(inSection), .. Unchecked(sec)]), []) with { Kind = "section" });
                }
                // a row whose section the contents don't list stays in its chapter, under its own section
                foreach (var g in inChapter.Where(p => sections.All(s => s.Number != p.In!.Section)).GroupBy(p => p.In!.Section ?? ""))
                    secNodes.Add(Node(CodeLevel.Section, g.Key.Length == 0 ? null : g.Key, g.First().In!.SectionTitle ?? "Other rules", null, Rules(g.ToList()), []) with { Kind = "section" });
                chapters.Add((inChapter.Count == 0
                    ? Empty(CodeLevel.Chapter, cn, ct, sections.Count > 0 && sections.All(NothingIn))
                    : Node(CodeLevel.Chapter, cn, ct, null, Fold(secNodes), [])) with { Kind = chapter.Kind });
                used.UnionWith(inChapter.Select(p => p.Row));
            }
            // a row whose chapter the contents don't list: its own chapter, never dropped
            foreach (var g in mine.Where(p => doc.Chapters.All(c => c.Number != p.In!.Chapter)).GroupBy(p => p.In!.Chapter ?? ""))
            {
                chapters.Add(Node(CodeLevel.Chapter, g.Key.Length == 0 ? null : g.Key, g.First().In!.ChapterTitle ?? "Other rules", null, Rules(g.ToList()), []));
                used.UnionWith(g.Select(p => p.Row));
            }
            var note = isGoverning && why is not null ? $"Governs this building: {why}" : null;
            var scopedHere = mine.Count(p => scoped.Contains(p.Row));
            docs.Add(Node(CodeLevel.Document, null, doc.Document, note, Fold(chapters), []) with
            {
                NoteTooltip = note is null ? null : Gordium.Revit.Reading.WhichCode.Read(result.Raw)?.Tooltip,
                Scope = scopedHere == 0 ? null : ScopeWords(scopedHere),
            });
        }
        // a row the contents can't place (no in_code, or a document they don't list): its own document node, last
        var left = placed.Where(p => !used.Contains(p.Row)).ToList();
        foreach (var g in left.GroupBy(p => p.In?.Document ?? ""))
            docs.Add(Node(CodeLevel.Document, null, g.Key.Length == 0 ? Unplaced : g.Key, null,
                          g.Key.Length == 0 ? Rules(g.ToList()) : Chapters(g.ToList()), []));
        return docs;
    }

    private static List<CodeNode> Chapters(List<(ResultRow Row, InCode? In, string Rule, string RuleName)> rows) =>
        rows.GroupBy(p => p.In?.Chapter ?? "").Select(g => Node(CodeLevel.Chapter, g.Key.Length == 0 ? null : g.Key,
            g.First().In?.ChapterTitle ?? "Other rules", null, Rules(g.ToList()), [])).ToList();

    /// <summary>A section's rules, each with its rows (a rule's parts: "8 spaces"), in the answer's order.</summary>
    private static List<CodeNode> Rules(List<(ResultRow Row, InCode? In, string Rule, string RuleName)> rows) =>
        rows.GroupBy(p => p.Rule).Select(g =>
        {
            var piece = g.First().In?.Piece;
            return Node(CodeLevel.Rule, piece, g.First().RuleName, null, [], g.Select(p => p.Row).ToList());
        }).ToList();

    /// <summary>Whether a section holds nothing to check: the contents say so (definitions, references), all of it
    /// was brought in, and no piece of it is waiting for rules (review round 2: a definitions section only partly
    /// brought in is not checked yet, never "nothing to check").</summary>
    private static bool NothingIn(ContentsSection sec) =>
        sec.Coverage == "not_for_checking" && sec.Whole && sec.Unchecked.Count == 0;

    /// <summary>A chapter or section with no row: greyed; "nothing to check" only where nothing in it is to check
    /// (<see cref="NothingIn"/>, for a chapter: every section); anything else is not checked yet by Gordium, which a
    /// parent counts against green.</summary>
    private static CodeNode Empty(CodeLevel level, string? number, string title, bool nothing)
    {
        return new CodeNode(level, number, title, null, nothing ? CodeState.NothingToCheck : CodeState.NotCheckedYet,
                            nothing ? "Nothing to check here" : "Not checked yet by Gordium", true, [], []);
    }

    /// <summary>The pieces of a section that has rows which Gordium has no rules for yet, and the rest of a section
    /// only partly brought in: greyed "not checked yet" parts beside its rules, so the section is never green
    /// (change 34) while part of it isn't checked.</summary>
    private static List<CodeNode> Unchecked(ContentsSection sec)
    {
        var parts = sec.Unchecked.Select(p => new CodeNode(CodeLevel.Rule, p.Id.Length == 0 ? null : p.Id, p.Title, null,
                                                           CodeState.NotCheckedYet, NotCheckedWords, true, [], [])).ToList();
        if (!sec.Whole)
            parts.Add(new CodeNode(CodeLevel.Rule, null, $"The rest of {sec.Number}: not brought in by Gordium", null,
                                   CodeState.NotCheckedYet, NotCheckedWords, true, [], []));
        return parts;
    }

    private const string NotCheckedWords = "Not checked yet by Gordium";

    private static string Plural(string kind, int n) => n == 1 ? kind : kind switch
    {
        "appendix" => "appendices",
        _ => kind + "s",
    };

    /// <summary>Each run of two or more greyed nodes folded, where it is, into one node holding them ("Articles
    /// III–IV", "26 sections"; never hidden: it opens to the list); a single greyed node stays as it is.</summary>
    private static List<CodeNode> Fold(List<CodeNode> nodes)
    {
        var shown = new List<CodeNode>();
        for (var i = 0; i < nodes.Count;)
        {
            // a run: greyed nodes of one kind side by side (chapters, then appendices, are two runs)
            var j = i;
            while (j < nodes.Count && nodes[j].Greyed && (j == i || nodes[j].Kind == nodes[i].Kind))
                j++;
            if (j - i < 2)
            {
                shown.Add(nodes[i]);
                i = Math.Max(j, i + 1);
                continue;
            }
            var run = nodes.GetRange(i, j - i);
            var kind = run[0].Kind;
            var state = run.Any(n => n.State == CodeState.NotCheckedYet) ? CodeState.NotCheckedYet : CodeState.NothingToCheck;
            var words = Plural(kind, run.Count);
            // a range only for the document's own numbered parts listed side by side ("Articles III–IV"); a
            // section's pieces not checked yet aren't side by side with each other in the section: counted instead
            var title = kind != "part" && run[0].Number is { Length: > 0 } first && run[^1].Number is { Length: > 0 } last
                ? $"{char.ToUpperInvariant(words[0])}{words[1..]} {first}–{last}"
                : $"{run.Count} {(i == 0 ? "" : "other ")}{words}";
            shown.Add(new CodeNode(CodeLevel.Others, null, title, null, state,
                                   state == CodeState.NotCheckedYet ? NotCheckedWords : "Nothing to check here", true, run, []) { Kind = kind });
            i = j;
        }
        return shown;
    }

    private static CodeNode Node(CodeLevel level, string? number, string title, string? note, List<CodeNode> children, List<ResultRow> rows)
    {
        var all = AllRows(children).Concat(rows).ToList();
        var state = StateOf(all.Select(r => r.Verdict).ToList(), GreyedInside(children).Any(c => c.State == CodeState.NotCheckedYet));
        return new CodeNode(level, number, title, note, state, Line(all, children), false, children, rows);
    }

    private static IEnumerable<ResultRow> AllRows(IEnumerable<CodeNode> nodes) =>
        nodes.SelectMany(n => n.Rows.Concat(AllRows(n.Children)));

    /// <summary>The worst state inside (change 34): complies only when every row complies (or doesn't apply, with at
    /// least one that complies) and nothing inside is not checked yet.</summary>
    public static CodeState StateOf(IReadOnlyCollection<Verdict> verdicts, bool anythingUnchecked)
    {
        if (verdicts.Contains(Verdict.DoesNotComply))
            return CodeState.Fails;
        if (verdicts.Contains(Verdict.NeedsReview))
            return CodeState.Review;
        if (anythingUnchecked || verdicts.Contains(Verdict.NotChecked))
            return CodeState.NotCheckedYet;
        if (verdicts.Contains(Verdict.Complies))
            return CodeState.Complies;
        return verdicts.Count > 0 ? CodeState.NotApplicable : CodeState.NothingToCheck;
    }

    /// <summary>The greyed nodes inside, at any depth (a greyed chapter is one chapter, not its sections).</summary>
    private static IEnumerable<CodeNode> GreyedInside(IEnumerable<CodeNode> nodes) =>
        nodes.SelectMany(c => c.Level == CodeLevel.Others ? c.Children : c.Greyed ? [c] : GreyedInside(c.Children));

    /// <summary>"62 need review · 26 sections not checked yet": the rows inside by verdict, then the parts of the
    /// document inside that Gordium hasn't checked, by what they are.</summary>
    private static string Line(List<ResultRow> rows, List<CodeNode> children)
    {
        var parts = new List<string>();
        var summary = rows.Count == 0 ? null : Summary(rows.Select(r => r.Verdict));
        if (summary is not null)
            parts.Add(summary);
        // the parts at the next level Gordium hasn't checked, by what they are ("8 articles not checked yet"); what
        // is unchecked deeper down is said once, not counted level by level (the line stays short: change 34)
        var here = children.SelectMany(c => c.Level == CodeLevel.Others ? c.Children : c.Greyed ? [c] : Array.Empty<CodeNode>())
                           .Where(c => c.State == CodeState.NotCheckedYet).ToList();
        foreach (var g in here.GroupBy(c => c.Kind))
            parts.Add($"{g.Count()} {Plural(g.Key, g.Count())} not checked yet");
        if (children.Any(c => !c.Greyed && GreyedInside(c.Children).Any(x => x.State == CodeState.NotCheckedYet)))
        {
            if (here.Count == 0)
                parts.Add("parts inside not checked yet");
            else
                parts[^1] += ", nor parts of the others";
        }
        return parts.Count == 0 ? "Nothing to check here" : string.Join(" · ", parts);
    }
}
