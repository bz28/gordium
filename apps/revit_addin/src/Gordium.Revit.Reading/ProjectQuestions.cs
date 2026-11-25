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

    /// <summary>What the street edge's question says (it is picked on the plan, in Setup).</summary>
    public const string PickInSetup = "The street edge is picked on the plan: use Set up on the ribbon.";

    /// <summary>The questions of an "Answer" group, in its cards' order (the most results first), each with its field.</summary>
    public static IReadOnlyList<ProjectQuestion> Of(FixGroup group, IReadOnlyList<SetupField>? fields)
    {
        ArgumentNullException.ThrowIfNull(group);
        return [.. group.Cards.Select(c => new ProjectQuestion(c, FieldFor(c.Field, fields ?? [])))];
    }

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

    /// <summary>"+ 4 more questions" / "Fewer questions".</summary>
    public static string MoreWords(int hidden, bool open) =>
        open ? "Fewer questions" : hidden == 1 ? "+ 1 more question" : $"+ {hidden} more questions";
}
