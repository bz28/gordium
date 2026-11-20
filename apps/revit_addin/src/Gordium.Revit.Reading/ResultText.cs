using System.Text;
using System.Text.Json;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>The words "Check my project" shows: a headline, what was checked, the rows that matter.</summary>
/// <param name="Headline">The worker's overall state and its summary line (never a count of the add-in's own).</param>
/// <param name="Checked">The phase and design options checked.</param>
/// <param name="Main">The groups, in the worker's order, every failure and every row that needs review in full.</param>
/// <param name="Inside">What the inside reader left out, list by list.</param>
/// <param name="Outline">The dialog's first view: each group's heading with its count, and every failure in full (the
/// rest is <see cref="Main"/>, under "Show details").</param>
public sealed record ResultWords(string Headline, string Checked, string Main, string Inside, string Outline = "")
{
    /// <summary>All of it, as one text (the log's copy).</summary>
    public override string ToString() => $"{Headline}\n{Checked}\n\n{Main}" + (Inside.Length > 0 ? $"\n\n{Inside}" : "");
}

/// <summary>
/// A check_site answer as the Revit dialog's words (reading design note, section 9). Nothing is ever shown kinder than
/// the worker said: the headline is the worker's own state and summary; each row carries its own verdict as the
/// add-in reads it (a status word it doesn't know is needs review, its word kept); the groups are the worker's, in its
/// order, with its counts. A row that fails, needs review or isn't checked is never cut; only rows that comply or don't
/// apply are, past <c>maxOtherRows</c>, with "N more (in the log)".
/// </summary>
public static class ResultText
{
    /// <summary>The words for the overall state.</summary>
    public static string StateWords(Verdict state) => state switch
    {
        Verdict.Complies => "Complies",
        Verdict.DoesNotComply => "Does not comply",
        Verdict.NotChecked => "Not checked",
        _ => "Needs review",
    };

    /// <summary>A row's verdict as shown beside it; a word the add-in doesn't know is shown as needs review, with the
    /// worker's word.</summary>
    public static string RowWords(CheckItem row) => !Verdicts.IsKnown(row.StatusWord)
        ? $"needs review (the checker said \"{row.StatusWord}\")"
        : row.Status switch
        {
            Verdict.Complies => "complies",
            Verdict.DoesNotComply => "DOES NOT COMPLY",
            Verdict.NotChecked => "not checked",
            Verdict.NotApplicable => "not applicable",
            _ => "needs review",
        };

    /// <summary>Whether a row may be cut from the dialog: only one that complies or doesn't apply (with its reason).</summary>
    public static bool MayCut(CheckItem row) => Verdicts.IsKnown(row.StatusWord) && row.Status is Verdict.Complies or Verdict.NotApplicable;

    /// <param name="result">The worker's answer.</param>
    /// <param name="phase">The phase checked (its name), or null for a model with no phases.</param>
    /// <param name="options">The design options checked ("set: option").</param>
    /// <param name="inside">The interior read, for its not-read lists; null when none.</param>
    /// <param name="element">A Revit UniqueId as the architect finds it (Revit's element id); null keeps the UniqueId.</param>
    /// <param name="maxOtherRows">How many rows that comply or don't apply are shown in all before the rest are cut.</param>
    /// <param name="street">The street line the check was sent with, in words (ProjectPrepared.Street): named in
    /// <see cref="ResultWords.Checked"/>, so a wrong edge picked is seen.</param>
    public static ResultWords Format(CheckResult result, string? phase, IReadOnlyList<string> options, InteriorReadResult? inside,
                                     Func<string, string?>? element = null, int maxOtherRows = 30, string? street = null)
    {
        ArgumentNullException.ThrowIfNull(result);
        ArgumentNullException.ThrowIfNull(options);
        var headline = Headline(result);
        var checkedWords = CheckedWords(phase, options, street);
        var rows = result.Items.ToDictionary(i => i.Id, StringComparer.Ordinal);
        var budget = maxOtherRows;
        var main = new StringBuilder();
        var outline = new StringBuilder();
        foreach (var g in result.Groups)
        {
            if (main.Length > 0)
                main.Append('\n');
            main.Append($"{g.Title} ({g.Count})\n");
            outline.Append($"{g.Title} ({g.Count})\n");
            foreach (var id in g.Items.Where(id => rows[id].Status == Verdict.DoesNotComply))
                outline.Append("  - ").Append(Row(rows[id], element)).Append('\n');
            if (g.Lines.Count == 0)
                List(main, g.Items.Select(id => rows[id]), "  ", ref budget, element);
            else
                foreach (var line in g.Lines)
                {
                    main.Append($"  {line.Title}\n");
                    List(main, line.Items.Select(id => rows[id]), "    ", ref budget, element);
                }
        }
        return new ResultWords(headline, checkedWords, main.ToString().TrimEnd('\n'), InsideWords(inside), outline.ToString().TrimEnd('\n'));
    }

    /// <summary>The worker's state and its summary line: "Does not comply: 4 do not comply · ...".</summary>
    public static string Headline(CheckResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        return $"{StateWords(result.State)}: {result.Summary}";
    }

    /// <summary>What was checked: the phase, the design options and the street line.</summary>
    public static string CheckedWords(string? phase, IReadOnlyList<string> options, string? street)
    {
        ArgumentNullException.ThrowIfNull(options);
        return "Checked: " + (phase is null ? "the model (it has no phases)" : $"the last phase, {phase}") + "; design options: " +
               (options.Count == 0 ? "the main model (no design options)" : "the main model and " + string.Join(", ", options)) +
               (street is null ? "" : $"; street line: {street}") + ".";
    }

    private static void List(StringBuilder s, IEnumerable<CheckItem> items, string indent, ref int budget, Func<string, string?>? element)
    {
        var cut = 0;
        foreach (var row in items)
        {
            if (MayCut(row))
            {
                if (budget <= 0)
                {
                    cut++;
                    continue;
                }
                budget--;
            }
            s.Append(indent).Append("- ").Append(Row(row, element)).Append('\n');
        }
        if (cut > 0)
            s.Append(indent).Append($"{cut} more (in the log)\n");
    }

    /// <summary>One row: its verdict, its name, measured against allowed and how far off (or the checker's reason),
    /// and the Revit elements it is about; the words the results panel shows too (<see cref="ResultRows.Row"/>).</summary>
    public static string Row(CheckItem row, Func<string, string?>? element = null) => ResultRows.Row(row).Line(element);

    /// <summary>A reason whose "; "-separated parts repeat (one per building: "a building has a curved edge (not
    /// measured yet)" twelve times) said once each, in the order first said, with how many times ("(x12)"). Nothing
    /// is dropped: every distinct part stays, and the count says how many there were.</summary>
    public static string? Once(string? reason)
    {
        if (reason is null)
            return null;
        var parts = reason.Split("; ");
        if (parts.Length == parts.Distinct(StringComparer.Ordinal).Count())
            return reason;
        var counts = parts.GroupBy(p => p, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.Count(), StringComparer.Ordinal);
        return string.Join("; ", parts.Distinct(StringComparer.Ordinal).Select(p => counts[p] > 1 ? $"{p} (x{counts[p]})" : p));
    }

    /// <summary>The Revit elements a row is about: a zoning row's <c>objects</c> (the lot and the buildings), an
    /// egress row's <c>part.id</c>.</summary>
    public static IReadOnlyList<string> Elements(JsonElement raw)
    {
        var ids = new List<string>();
        if (raw.TryGetProperty("objects", out var o) && o.ValueKind == JsonValueKind.Array)
            ids.AddRange(o.EnumerateArray().Where(x => x.ValueKind == JsonValueKind.String).Select(x => x.GetString()!));
        if (raw.TryGetProperty("part", out var p) && p.ValueKind == JsonValueKind.Object
            && p.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String && !ids.Contains(id.GetString()!))
            ids.Add(id.GetString()!);
        return ids;
    }

    /// <summary>The inside's not-read lists, each reason in full, and how many values were left out.</summary>
    public static string InsideWords(InteriorReadResult? inside)
    {
        if (inside is null)
            return "";
        var s = new StringBuilder();
        foreach (var (what, why) in new[]
                 {
                     ("Rooms", inside.RoomsNotRead), ("Windows and doors", inside.OpeningsNotRead), ("Stairs", inside.StairsNotRead),
                     ("Doors", inside.DoorsNotRead), ("Guards", inside.GuardsNotRead),
                 })
        {
            if (why.Count == 0)
                continue;
            s.Append($"{what} not read from the model:\n");
            foreach (var w in why)
                s.Append($"  - {w}\n");
        }
        if (inside.Notes.Count > 0)
            s.Append($"{inside.Notes.Count} values left out of what was read (each in the log).\n");
        return s.ToString().TrimEnd('\n');
    }
}
