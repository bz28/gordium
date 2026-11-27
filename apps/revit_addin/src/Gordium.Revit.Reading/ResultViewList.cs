namespace Gordium.Revit.Reading;

// The two results views as the pane's list draws them (UI polish changes 17, 21, 25, 33 to 37; Ben approved
// 2026-11-23): the entries of "What to fix" (each group, its cards, a card's rows when opened) and of "By code" (each
// node of the law's tree at its depth, a rule's rows when opened), from ResultViews. Revit-free and tested: the pane
// only draws these entries. A search shows the matching rows of either view as the plain list does. The rules: every
// row can be reached in either view (a fold opens to it, never hides it); a status is the rows' own (stale once the
// model changed: never green then), and a group or node holding anything unsettled is never drawn green.

/// <summary>A "What to fix" group's heading ("Answer 21 questions about the project", its sub line, "See 22 results").</summary>
/// <param name="Group">The group.</param>
/// <param name="Key">What the open set names it by (<see cref="ResultViewList.GroupKey"/>).</param>
/// <param name="Open">Whether its cards (or rows) are shown under it.</param>
/// <param name="Status">Its glyph (<see cref="ResultViewList.StatusOf(FixKind, IReadOnlyCollection{ResultRow}, bool)"/>).</param>
public sealed record FixGroupEntry(FixGroup Group, string Key, bool Open, PanelStatus Status) : ListEntry;

/// <summary>One card of an open group: the ask's headline, how many results wait on it, open to its rows.</summary>
public sealed record FixCardEntry(FixCard Card, string Key, bool Open, PanelStatus Status) : ListEntry;

/// <summary>One node of "By code" at its depth (0 a document): its state's glyph, its title and status line; open
/// to what is inside (a rule: its rows).</summary>
public sealed record CodeNodeEntry(CodeNode Node, string Key, int Depth, bool Open, bool CanOpen, PanelStatus Status) : ListEntry;

/// <summary>One question of the open "Answer N questions" group (changes 22, 23): the checker's ask, its field's
/// control, "affects N results" (opening to them).</summary>
public sealed record QuestionEntry(ProjectQuestion Question, string Key, bool Open, PanelStatus Status) : ListEntry;

/// <summary>"+ N more questions" (or "Fewer questions"), after the first <see cref="ProjectQuestions.ShownAtFirst"/>.</summary>
public sealed record MoreQuestionsEntry(string Key, int Hidden, bool Open) : ListEntry;

/// <summary>The questions' foot: the scope note (change 24), Save and check again, Open Project Information.</summary>
public sealed record AnswerFootEntry(FixGroup Group, IReadOnlyList<ProjectQuestion> Questions, string? Scope) : ListEntry;

public static class ResultViewList
{
    /// <summary>The key of the "Answer" group's "+ N more questions".</summary>
    public const string MoreQuestionsKey = "questions:more";

    /// <summary>The words of the switch (change 17), in its order.</summary>
    public static string Words(ResultsViewKind view) => view == ResultsViewKind.WhatToFix ? "What to fix" : "By code";

    public static string GroupKey(FixGroup g) => "fix:" + g.Kind;

    /// <summary>The kind of work a group is, as its icon (change 46: scan by kind of work): a form for questions, a pin
    /// for marks, a pencil for the model, a map for a survey, a ruler for a hand measure, scales for a judgment, a
    /// question for the law; null for what fails, isn't checked or is settled (their status glyph says it). Drawn in the
    /// text's colour, never a status colour.</summary>
    public static PaneIcon? IconOf(FixKind kind) => kind switch
    {
        FixKind.Answer => PaneIcon.Form,
        FixKind.Mark => PaneIcon.Pin,
        FixKind.FixModel => PaneIcon.Pencil,
        FixKind.Survey => PaneIcon.Map,
        FixKind.Measure => PaneIcon.Ruler,
        FixKind.Decide => PaneIcon.Scales,
        FixKind.OpenQuestion => PaneIcon.Question,
        _ => null,
    };

    public static string CardKey(FixCard c) => "card:" + c.Kind + ":" + c.Key;

    /// <summary>What a group's heading looks like: what fails is fails; a group of questions, marks, fixes, hand checks
    /// or judgments needs review; not checked yet is its own dashed glyph; only the folded "complies or doesn't apply"
    /// group may be green, and only when every row in it complies. Stale: never green.</summary>
    public static PanelStatus StatusOf(FixKind kind, IReadOnlyCollection<ResultRow> rows, bool stale) => stale ? PanelStatus.Stale : kind switch
    {
        FixKind.Fails => PanelStatus.Fails,
        FixKind.NotChecked => PanelStatus.NotChecked,
        FixKind.Done => rows.Count > 0 && rows.All(r => r.Verdict == Gordium.Worker.Verdict.Complies) ? PanelStatus.Complies : PanelStatus.NotApplicable,
        _ => PanelStatus.Review,
    };

    /// <summary>A node's glyph from its state (change 34): green only for Complies, which ResultViews gives only when
    /// every row inside complies and nothing inside is unchecked. Stale: never green.</summary>
    public static PanelStatus StatusOf(CodeState state, bool stale) => stale ? PanelStatus.Stale : state switch
    {
        CodeState.Fails => PanelStatus.Fails,
        CodeState.Review => PanelStatus.Review,
        CodeState.NotCheckedYet => PanelStatus.NotChecked,
        CodeState.Complies => PanelStatus.Complies,
        _ => PanelStatus.NotApplicable,
    };

    /// <summary>Which groups and nodes start open: what fails and the first group of work (the architect's next
    /// step); in By code, each document.</summary>
    public static IEnumerable<string> OpenAtFirst(ResultViewsModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        foreach (var g in model.Fix.Where(g => g.Kind != FixKind.Done && g.Kind != FixKind.NotChecked).Take(1)
                                   .Concat(model.Fix.Where(g => g.Kind == FixKind.Fails)).Distinct())
            yield return GroupKey(g);
        for (var i = 0; i < model.Code.Count; i++)
            yield return NodeKey("", i);
    }

    private static string NodeKey(string parent, int index) => parent + "/" + index;

    /// <summary>The list for <paramref name="view"/>: its entries, with each row as the plain list places it
    /// (<paramref name="placed"/>, by id: its status, stale or not). A search (any term) shows the plain list's
    /// matching rows instead, the same in both views.</summary>
    public static IReadOnlyList<ListEntry> Layout(ResultViewsModel model, IReadOnlyList<ListRow> placed, ResultsViewKind view,
                                                  IReadOnlySet<string> open, string? query,
                                                  IReadOnlyDictionary<string, string>? labels, bool stale,
                                                  IReadOnlyList<SetupField>? fields = null, SetupDraft? draft = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(placed);
        ArgumentNullException.ThrowIfNull(open);
        if (ResultList.Terms(query).Count > 0)
            return ResultList.Layout(placed, ListFilter.All, query, labels, stale);
        var byId = placed.ToDictionary(p => p.Row.Id, StringComparer.Ordinal);
        var entries = new List<ListEntry>();
        void Rows(IEnumerable<ResultRow> rows)
        {
            foreach (var r in rows)
                if (byId.TryGetValue(r.Id, out var p))
                    entries.Add(new ListRowEntry(p));
        }
        if (view == ResultsViewKind.WhatToFix)
        {
            foreach (var fixGroup in model.Fix)
            {
                var g = fixGroup;
                var key = GroupKey(g);
                var isOpen = open.Contains(key);
                // the questions the card shows (a follow-up waits for its parent's answer, chosen here or held), and
                // its title says how many
                var questions = g.Kind == FixKind.Answer && fields is not null ? ProjectQuestions.Of(g, fields, draft) : null;
                if (questions is not null)
                    g = g with { Title = ResultViews.GroupWords(g.Kind, [.. questions.Select(q => q.Card)], g.Rows.Count).Title };
                entries.Add(new FixGroupEntry(g, key, isOpen, StatusOf(g.Kind, g.Rows, stale)));
                if (!isOpen)
                    continue;
                // a group of rows, not asks (what fails, not checked yet, complies): its rows straight under it
                if (g.Kind is FixKind.Fails or FixKind.NotChecked or FixKind.Done)
                {
                    Rows(g.Rows);
                    continue;
                }
                // the questions asked in the card (changes 22, 23), once the project's fields are known
                if (questions is not null)
                {
                    var more = open.Contains(MoreQuestionsKey);
                    foreach (var q in more ? questions : questions.Take(ProjectQuestions.ShownAtFirst))
                    {
                        var qk = CardKey(q.Card);
                        var qOpen = open.Contains(qk);
                        entries.Add(new QuestionEntry(q, qk, qOpen, StatusOf(g.Kind, q.Card.Rows, stale)));
                        if (qOpen)
                            Rows(q.Card.Rows);
                    }
                    if (questions.Count > ProjectQuestions.ShownAtFirst)
                        entries.Add(new MoreQuestionsEntry(MoreQuestionsKey, questions.Count - ProjectQuestions.ShownAtFirst, more));
                    // the scope note, said of the questions' own results only (short review after #181: the rows it
                    // counts can sit elsewhere, with no question of their own)
                    var scopedHere = g.Rows.Count(r => model.Scoped.Contains(r.Id));
                    entries.Add(new AnswerFootEntry(g, questions, scopedHere == 0 ? null : ResultViews.ScopeWords(scopedHere)));
                    continue;
                }
                // without the fields (not read), the questions as cards: a follow-up still held back on its parent's
                foreach (var c in g.Kind == FixKind.Answer ? Shown(g, null, null) : g.Cards)
                {
                    var ck = CardKey(c);
                    var cardOpen = open.Contains(ck);
                    entries.Add(new FixCardEntry(c, ck, cardOpen, StatusOf(g.Kind, c.Rows, stale)));
                    if (cardOpen)
                        Rows(c.Rows);
                }
            }
            return entries;
        }
        void Node(CodeNode n, string key, int depth)
        {
            var canOpen = n.Children.Count > 0 || n.Rows.Count > 0;
            var isOpen = canOpen && open.Contains(key);
            entries.Add(new CodeNodeEntry(n, key, depth, isOpen, canOpen, StatusOf(n.State, stale)));
            if (!isOpen)
                return;
            for (var i = 0; i < n.Children.Count; i++)
                Node(n.Children[i], NodeKey(key, i), depth + 1);
            Rows(n.Rows);
        }
        for (var i = 0; i < model.Code.Count; i++)
            Node(model.Code[i], NodeKey("", i), 0);
        return entries;
    }

    /// <summary>The opener a key on <paramref name="e"/> toggles (UI polish PR 3 review round 1: the keyboard opens
    /// what a click opens): Enter or Space either way, Right only to open, Left only to fold; null for any other key
    /// or entry (a node with nothing inside opens nothing).</summary>
    public static string? KeyToggles(ListEntry e, string key)
    {
        var (k, open, canOpen) = e switch
        {
            FixGroupEntry g => (g.Key, g.Open, true),
            FixCardEntry c => (c.Key, c.Open, true),
            CodeNodeEntry n => (n.Key, n.Open, n.CanOpen),
            QuestionEntry q => (q.Key, q.Open, true),
            MoreQuestionsEntry m => (m.Key, m.Open, true),
            _ => ((string?)null, false, false),
        };
        if (k is null || !canOpen)
            return null;
        // a question with a control: Enter and Space go into its control (EntersControl), Right and Left open its results
        if (e is QuestionEntry { Question.Field: not null } && key is "Enter" or "Return" or "Space")
            return null;
        return key switch
        {
            "Enter" or "Return" or "Space" => k,
            "Right" when !open => k,
            "Left" when open => k,
            _ => null,
        };
    }

    /// <summary>Whether a key on <paramref name="e"/> moves the keyboard into the question's own control (its dropdown,
    /// Yes / No or box: review round 1, the keyboard could reach a question but never answer it): Enter or Space on a
    /// question Gordium has a field for.</summary>
    public static bool EntersControl(ListEntry e, string key) =>
        e is QuestionEntry { Question.Field: not null } && key is "Enter" or "Return" or "Space";

    /// <summary>Whether a key on <paramref name="e"/> presses the questions card's Save and check again (Enter or Space
    /// on its foot, which the keyboard stops on: review round 1).</summary>
    public static bool Saves(ListEntry e, string key) => e is AnswerFootEntry && key is "Enter" or "Return" or "Space";

    /// <summary>The keys to open so a result's questions show in the questions card (the detail's "Answer N
    /// questions": review round 1, a result's question past the first few was left behind "+ N more questions"): the
    /// "Answer" group, and "+ N more" when any of the result's questions is past the first few; empty when the result
    /// asks no question.</summary>
    public static IReadOnlyList<string> AnswerKeys(ResultViewsModel model, string rowId, IReadOnlyList<SetupField>? fields = null,
                                                   SetupDraft? draft = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        if (model.Fix.FirstOrDefault(g => g.Kind == FixKind.Answer) is not { } group)
            return [];
        // where the card shows the result's questions (a follow-up held back: its results are on its parent's)
        var at = Shown(group, fields, draft).Select((c, i) => (c, i)).Where(x => x.c.Rows.Any(r => r.Id == rowId)).Select(x => x.i).ToList();
        if (at.Count == 0)
            return [];
        return at.Any(i => i >= ProjectQuestions.ShownAtFirst) ? [GroupKey(group), MoreQuestionsKey] : [GroupKey(group)];
    }

    /// <summary>Whether an answer chosen in the card changed what the questions card shows (a follow-up brought in or
    /// hidden, so its title's count, its questions or its "+ N more"): only then is the list drawn again, so a box
    /// being typed in keeps its keyboard.</summary>
    public static bool QuestionsDiffer(IReadOnlyList<ListEntry> before, IReadOnlyList<ListEntry> after)
    {
        ArgumentNullException.ThrowIfNull(before);
        ArgumentNullException.ThrowIfNull(after);
        static IEnumerable<string> Shape(IReadOnlyList<ListEntry> entries) => entries.Select(e => e switch
        {
            FixGroupEntry g => "group:" + g.Key + ":" + g.Group.Title,
            QuestionEntry q => "question:" + q.Key + ":" + q.Question.Affects,
            MoreQuestionsEntry m => "more:" + m.Hidden,
            _ => null,
        }).OfType<string>();
        return !Shape(before).SequenceEqual(Shape(after), StringComparer.Ordinal);
    }

    /// <summary>The cards of the questions card as it shows them (<see cref="ProjectQuestions.Of"/>).</summary>
    private static IReadOnlyList<FixCard> Shown(FixGroup group, IReadOnlyList<SetupField>? fields, SetupDraft? draft) =>
        [.. ProjectQuestions.Of(group, fields, draft).Select(q => q.Card)];

    /// <summary>The questions card's foot, for a screen reader (review round 2: its scope note said first, and nothing
    /// promised that isn't chosen).</summary>
    public const string FootWords = "Save and check again: Enter saves what you chose in this card, once you have chosen. " + ProjectQuestions.NothingSaved;

    /// <summary>What a screen reader says for an opener (review round 5: on the list item the keyboard is on, not
    /// inside it): its title, which code governs (a book's note), its status, and its counts; null for other entries.</summary>
    public static string? Spoken(ListEntry e) => e switch
    {
        FixGroupEntry g => $"{g.Group.Title}, {StatusLook.Word(g.Status)}, {g.Group.SeeWords}" + (g.Open ? ", open" : ", folded"),
        FixCardEntry c => $"{c.Card.Title}, {(c.Card.Rows.Count == 1 ? "1 result" : $"{c.Card.Rows.Count} results")}" + (c.Open ? ", open" : ", folded"),
        CodeNodeEntry n => string.Join(", ", new[] { Title(n.Node), n.Node.Note, StatusLook.Word(n.Status), n.Node.Line, n.Node.Scope }.OfType<string>())
                           + (n.CanOpen ? n.Open ? ", open" : ", folded" : ""),
        QuestionEntry q => $"{q.Question.Card.Headline}, {ProjectQuestions.Affects(q.Question.Affects)}"
                           + (q.Question.Field is null ? ", " + ProjectQuestions.NoField : "") + (q.Open ? ", results shown" : ""),
        MoreQuestionsEntry m => ProjectQuestions.MoreWords(m.Hidden, m.Open),
        AnswerFootEntry f => string.Join(" ", new[] { f.Scope, FootWords }.OfType<string>()),
        _ => null,
    };

    /// <summary>An opener's tooltip, shown on hover and on the item the keyboard is on: a card's headline and the
    /// checker's words behind it ("Why"); a book's note and the law's quoted words behind which code governs; null for
    /// the rest.</summary>
    public static string? Tip(ListEntry e) => e switch
    {
        // the checker's words under a card named by its rule (egress UI audit, finding 3)
        FixCardEntry c => (c.Card.Title == c.Card.Headline ? c.Card.Headline : $"{c.Card.Title}\n{c.Card.Headline}")
                          + (c.Card.Why is { } why ? $"\n\nWhy: {why}" : ""),
        CodeNodeEntry { Node.Note: { } note } n => n.Node.NoteTooltip is { } quotes ? $"{note}\n\n{quotes}" : note,
        _ => null,
    };

    /// <summary>A node's title as shown: its number and title ("10 MEANS OF EGRESS"), a fold's title alone.</summary>
    public static string Title(CodeNode n) => n.Number is { Length: > 0 } number && n.Level != CodeLevel.Others ? $"{number} {n.Title}" : n.Title;

    /// <summary>The keys to open so a row shows in a view (its group and card, or its document, chapter, section
    /// and rule): what "show this result" opens, so no row is ever out of reach.</summary>
    public static IReadOnlyList<string> PathTo(ResultViewsModel model, ResultsViewKind view, string rowId,
                                               IReadOnlyList<SetupField>? fields = null, SetupDraft? draft = null)
    {
        ArgumentNullException.ThrowIfNull(model);
        if (view == ResultsViewKind.WhatToFix)
        {
            foreach (var g in model.Fix)
            {
                if (!g.Rows.Any(r => r.Id == rowId))
                    continue;
                if (g.Kind is FixKind.Fails or FixKind.NotChecked or FixKind.Done)
                    return [GroupKey(g)];
                // the questions as the card shows them (a follow-up held back: its results are on its parent's)
                var cards = g.Kind == FixKind.Answer ? Shown(g, fields, draft) : g.Cards;
                var at = cards.ToList().FindIndex(c => c.Rows.Any(r => r.Id == rowId));
                // a question past the first few is behind "+ N more questions" (the key is harmless elsewhere)
                return g.Kind == FixKind.Answer && at >= ProjectQuestions.ShownAtFirst
                    ? [GroupKey(g), MoreQuestionsKey, CardKey(cards[at])]
                    : [GroupKey(g), CardKey(cards[at])];
            }
            return [];
        }
        List<string>? Find(CodeNode n, string key)
        {
            if (n.Rows.Any(r => r.Id == rowId))
                return [key];
            for (var i = 0; i < n.Children.Count; i++)
                if (Find(n.Children[i], NodeKey(key, i)) is { } path)
                    return [key, .. path];
            return null;
        }
        for (var i = 0; i < model.Code.Count; i++)
            if (Find(model.Code[i], NodeKey("", i)) is { } path)
                return path;
        return [];
    }
}
