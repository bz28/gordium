namespace Gordium.Revit.Reading;

// "Answer N questions about the project" asks its questions in the card (UI polish changes 22 and 23; Ben approved
// 2026-11-23: answered in the pane, written only on Save, as one undo). Each question is one of the checker's asks for
// a project fact (asks[].field, "facts.corner_lot", "building.occupancy_groups"), matched to the Setup form's own field
// for that fact (the mark that feeds it: SetupField.Mark.Feeds), so the same control, the same allowed values and the
// same write (SetupDraft.Writes) answer it here as in Setup. Revit-free and tested. The rules: nothing is written until
// Save, and then only what the architect chose here (a blank stays blank); a question Gordium has no field for says so
// and is never dropped; "affects N results" is the count of the checker's rows waiting on it.

/// <summary>One question of the card: the checker's ask (its headline and the rows waiting on it) and the Setup field
/// that answers it, or null when Gordium has no field for it in Revit yet.</summary>
public sealed record ProjectQuestion(FixCard Card, SetupField? Field)
{
    /// <summary>How many of the checker's results wait on it.</summary>
    public int Affects => Card.Rows.Count;
}

public static class ProjectQuestions
{
    /// <summary>How many questions show before "+ N more questions".</summary>
    public const int ShownAtFirst = 5;

    /// <summary>The card's line about saving (strings.md: "Set on Project Information. Nothing is saved until you click
    /// Save.").</summary>
    public const string NothingSaved = "Nothing is saved until you click Save. Save is one step you can undo (Ctrl+Z).";

    /// <summary>What a question Gordium has no field for says.</summary>
    public const string NoField = "Gordium has no field for this in Revit yet. Decide it by hand from its results.";

    /// <summary>The questions of an "Answer" group the card shows, each with its field: in its cards' order (the most
    /// results first), a follow-up right after the question it hangs on (<see cref="FixCard.DependsOn"/>). A follow-up
    /// whose parent is asked here is held back until the parent is answered (chosen in <paramref name="draft"/>, or
    /// what its mark holds), hidden once that answer makes it moot, and shown once it is answered otherwise. Its results
    /// are never dropped: a follow-up not shown leaves them on its nearest shown parent (they wait on that question
    /// first), still in review.</summary>
    public static IReadOnlyList<ProjectQuestion> Of(FixGroup group, IReadOnlyList<SetupField>? fields, SetupDraft? draft = null)
    {
        ArgumentNullException.ThrowIfNull(group);
        var all = fields ?? [];
        string? AnswerOf(FixCard parent) =>
            FieldFor(parent.Field, all) is not { } f ? null
            : draft?.Chosen(f.Mark) ?? (f.IsSet ? f.CurrentChoice?.Value ?? f.Current : null);
        return [.. Arrange(group.Cards, AnswerOf).Select(c => new ProjectQuestion(c, FieldFor(c.Field, all)))];
    }

    /// <summary>What a follow-up question is in the card now.</summary>
    private enum Shown { Yes, Held, Moot }

    /// <summary>The cards the questions card shows, in its order (<see cref="Of"/>), given the answer each parent question
    /// has (<paramref name="answerOf"/>: null while unanswered). A follow-up is held back or hidden only when the
    /// question it hangs on is one of <paramref name="cards"/> (else its parent is answered in the project already,
    /// and the checker still asks it); a shown card carries the results of the follow-ups not shown under it.</summary>
    public static IReadOnlyList<FixCard> Arrange(IReadOnlyList<FixCard> cards, Func<FixCard, string?> answerOf)
    {
        ArgumentNullException.ThrowIfNull(cards);
        ArgumentNullException.ThrowIfNull(answerOf);
        var byField = new Dictionary<string, FixCard>(StringComparer.Ordinal);
        foreach (var c in cards)
            if (c.Field is { Length: > 0 } f)
                byField.TryAdd(f, c);
        FixCard? Named(FixCard c) =>
            c.DependsOn is { } d && byField.TryGetValue(d.Field, out var p) && !ReferenceEquals(p, c) ? p : null;
        // a card whose chain of parents loops (two follow-ups naming each other) is asked as any other: never held
        // back on a question that is itself held back on it
        bool Loops(FixCard c)
        {
            var seen = new HashSet<FixCard>(ReferenceEqualityComparer.Instance) { c };
            for (var p = Named(c); p is not null; p = Named(p))
                if (!seen.Add(p))
                    return true;
            return false;
        }
        var looping = cards.Where(Loops).ToHashSet(ReferenceEqualityComparer.Instance);
        FixCard? ParentOf(FixCard c) => looping.Contains(c) ? null : Named(c);
        var state = new Dictionary<FixCard, Shown>(ReferenceEqualityComparer.Instance);
        Shown StateOf(FixCard c)
        {
            if (state.TryGetValue(c, out var s))
                return s;
            if (ParentOf(c) is not { } parent)
                return Shown.Yes;                                // no parent asked here (or a loop): asked as any other
            var ps = StateOf(parent);
            s = ps != Shown.Yes ? ps                             // under a parent held back or moot: so is this one
                : answerOf(parent) is not { } answer ? Shown.Held
                : c.DependsOn!.MootIf.Any(m => Same(m, answer)) ? Shown.Moot : Shown.Yes;
            state[c] = s;
            return s;
        }
        FixCard ShownAbove(FixCard c)
        {
            while (StateOf(c) != Shown.Yes && ParentOf(c) is { } p)    // a card not shown has a parent; no loop is followed
                c = p;
            return c;
        }
        // the results of the follow-ups not shown, on the question shown above each
        var carried = new Dictionary<FixCard, List<ResultRow>>(ReferenceEqualityComparer.Instance);
        foreach (var c in cards.Where(c => StateOf(c) != Shown.Yes))
        {
            var above = ShownAbove(c);
            if (!carried.TryGetValue(above, out var list))
                carried[above] = list = [.. above.Rows];
            foreach (var r in c.Rows)
                if (!list.Contains(r))
                    list.Add(r);
        }
        FixCard Carrying(FixCard c) =>
            carried.TryGetValue(c, out var rows) && rows.Count > c.Rows.Count ? c with { Rows = rows } : c;
        // each question shown, then the follow-ups shown under it (in the cards' order)
        var shown = cards.Where(c => StateOf(c) == Shown.Yes).ToList();
        var placed = new HashSet<FixCard>(ReferenceEqualityComparer.Instance);
        var order = new List<FixCard>();
        void Place(FixCard c)
        {
            if (!placed.Add(c))
                return;
            order.Add(Carrying(c));
            foreach (var child in shown.Where(x => ReferenceEquals(ParentOf(x), c)))
                Place(child);
        }
        foreach (var c in shown.Where(c => ParentOf(c) is null))   // a card shown has no parent, or one shown
            Place(c);
        return order;
    }

    /// <summary>Whether an answer is one of the moot ones: the same word (Yes, No, a choice's word, in any case), or
    /// the same number.</summary>
    private static bool Same(string moot, string answer) =>
        string.Equals(moot.Trim(), answer.Trim(), StringComparison.OrdinalIgnoreCase)
        || double.TryParse(moot, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var a)
           && double.TryParse(answer, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var b)
           && a == b;

    /// <summary>The Setup field that answers <paramref name="field"/> (an ask's fact: the mark that feeds it), or null
    /// when Gordium has none in Revit for it (or the fact is the street edge, picked on the plan).</summary>
    public static SetupField? FieldFor(string? field, IReadOnlyList<SetupField> fields)
    {
        ArgumentNullException.ThrowIfNull(fields);
        if (field is not { Length: > 0 })
            return null;
        // a mark's Feeds is the fact ("facts.corner_lot") or the fact and where else it is used ("facts.use (on
        // Project Information), rooms[].use (on a Room)")
        var f = fields.FirstOrDefault(x => x.Mark.Feeds == field || x.Mark.Feeds.StartsWith(field + " ", StringComparison.Ordinal));
        return f is { Kind: FieldKind.StreetPick } ? null : f;
    }

    /// <summary>"affects 28 results".</summary>
    public static string Affects(int n) => n == 1 ? "affects 1 result" : $"affects {n} results";

    /// <summary>The fields the questions answer, each once.</summary>
    public static IReadOnlyList<SetupField> Fields(IReadOnlyList<ProjectQuestion> questions)
    {
        ArgumentNullException.ThrowIfNull(questions);
        return [.. questions.Select(q => q.Field).OfType<SetupField>().DistinctBy(f => f.Mark.Guid)];
    }

    /// <summary>How many answers a Save would write (SetupDraft.Changes: chosen, and not what the mark holds already).</summary>
    public static int Unsaved(IReadOnlyList<ProjectQuestion> questions, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(draft);
        return Fields(questions).Count(draft.Changes);
    }

    /// <summary>The writes a Save makes, and the answers it refuses with why: SetupDraft.Writes over the questions'
    /// fields only (an answer to anything else is never written from here).</summary>
    public static (IReadOnlyList<MarkWrite> Writes, IReadOnlyList<string> Problems) Writes(IReadOnlyList<ProjectQuestion> questions, SetupDraft draft)
    {
        ArgumentNullException.ThrowIfNull(draft);
        return draft.Writes(Fields(questions));
    }

    /// <summary>The Save button's words: "Save 2 answers and check again".</summary>
    public static string SaveWords(int unsaved) => unsaved switch
    {
        0 => "Save and check again",
        1 => "Save 1 answer and check again",
        _ => $"Save {unsaved} answers and check again",
    };

    /// <summary>The unit said beside a length's or an area's box: its symbol, and when Gordium can't read the project's
    /// units, what to type instead (feet for a length, square feet for an area: after #193 an area said "type feet").</summary>
    public static string UnitWords(LengthUnit unit)
    {
        ArgumentNullException.ThrowIfNull(unit);
        return unit.Known ? unit.Symbol
            : $"{unit.Symbol} (this project's units aren't ones Gordium reads: type {(unit.Quantity == "area" ? "square feet" : "feet")})";
    }

    /// <summary>"+ 4 more questions" / "Fewer questions".</summary>
    public static string MoreWords(int hidden, bool open) =>
        open ? "Fewer questions" : hidden == 1 ? "+ 1 more question" : $"+ {hidden} more questions";
}
