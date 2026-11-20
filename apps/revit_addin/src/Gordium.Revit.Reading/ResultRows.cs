using System.Text.Json;
using System.Text.RegularExpressions;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

/// <summary>How a row, a group or a count is coloured: red, amber, green, or grey (a rule set aside with its
/// reason). Never green for anything but what the worker said complies.</summary>
public enum Tone { Fails, Review, Complies, Neutral }

/// <summary>One of the law's own sentences a row was decided on, and where it is ("R319.2.2, 2025 Residential
/// Code of New York State (RCNYS), PDF p.102").</summary>
public sealed record LawQuote(string Text, string? Where);

/// <summary>
/// One row of a check as the text file and the results panel both say it (the one place its words are made):
/// its verdict, its name, how far off it is, the checker's reason, the law's section and quotes, and the Revit
/// elements it is about.
/// </summary>
/// <param name="Id">The worker's row id.</param>
/// <param name="Name">The row's name as the worker gives it.</param>
/// <param name="Verdict">The row's verdict as the add-in reads it (a word it doesn't know is needs review).</param>
/// <param name="VerdictWords">That verdict in words; an unknown word keeps the worker's own.</param>
/// <param name="Tone">Its colour, from the verdict alone.</param>
/// <param name="Figures">What was measured against what is allowed, in the worker's own figures, or null: a zoning
/// row's <c>proposed</c>, <c>sign</c> and <c>required</c> ("20'-0\" measured, ≥ 25'-0\" allowed", or "allowed 25'-0\""
/// when nothing was measured); an egress row's figures as its reason states them ("net clear height 20 in, needs ≥
/// 24 in"). Never a number the worker didn't give.</param>
/// <param name="HowFar">How far off (or the room to spare), in the worker's own words: its <c>delta</c> (over every
/// reading of the lot lines and the open questions, never overstated), or its <c>margin</c> from a worker that
/// gives no delta; null when it gives neither. Never worked out here: an egress row gives neither, so its
/// <see cref="Figures"/> alone say it.</param>
/// <param name="Reason">The worker's reason, each repeated part said once with its count, without the part the name
/// already says; null when none.</param>
/// <param name="Section">The law's section the row is decided on (an egress row's <c>code.section</c>, else the
/// citation the worker gives), or null.</param>
/// <param name="Quotes">The law's exact words the row was decided on, as the worker answered with them.</param>
/// <param name="Elements">The Revit elements it is about, by UniqueId (a zoning row's <c>objects</c>, an egress
/// row's <c>part.id</c>).</param>
public sealed record ResultRow(string Id, string Name, Verdict Verdict, string VerdictWords, Tone Tone, string? Figures,
                               string? HowFar, string? Reason, string? Section, IReadOnlyList<LawQuote> Quotes,
                               IReadOnlyList<string> Elements)
{
    /// <summary>Whether the reason already says the figures (an egress row's figures are read from its reason): the
    /// text file then says them once, in the reason; the panel shows the reason only when it says more.</summary>
    public bool FiguresInReason => Reason is not null && Figures is not null && Reason.Contains(Figures, StringComparison.Ordinal);

    /// <summary>Whether the reason says nothing beyond the figures (the panel then shows the figures alone).</summary>
    public bool ReasonIsFigures => Reason is not null && Reason == Figures;

    /// <summary>The row as one line of the text file: "[verdict] name: figures (how far). reason [elements]".</summary>
    public string Line(Func<string, string?>? element = null)
    {
        var said = new List<string>();
        if (Figures is not null && !FiguresInReason)
            said.Add(Figures + (HowFar is null ? "" : $" ({HowFar})"));
        if (Reason is { Length: > 0 })
            said.Add(Reason);
        var s = $"[{VerdictWords}] {Name}" + (said.Count > 0 ? ": " + string.Join(". ", said) : "");
        if (Elements.Count > 0)
        {
            var shown = Elements.Take(6).Select(id => element?.Invoke(id) ?? id).ToList();
            s += " [" + string.Join(", ", shown) + (Elements.Count > 6 ? $", {Elements.Count - 6} more" : "") + "]";
        }
        return s;
    }
}

/// <summary>A line of a law's group (a part's rules, one cause): its rows, folded as the worker said.</summary>
public sealed record ResultLine(string Title, Tone Tone, bool Folded, IReadOnlyList<ResultRow> Rows);

/// <summary>One heading of the list, the worker's: its title and count, folded as the worker said (never a group
/// holding a failure: CheckResult), its rows, or its lines when it has them.</summary>
public sealed record ResultGroup(string Key, string Title, int Count, bool Folded, Tone Tone, IReadOnlyList<ResultRow> Rows,
                                 IReadOnlyList<ResultLine> Lines)
{
    /// <summary>Every row in it, in order (in its lines' order when it has lines).</summary>
    public IEnumerable<ResultRow> AllRows => Lines.Count == 0 ? Rows : Lines.SelectMany(l => l.Rows);
}

/// <summary>One count as the worker said it ("4 do not comply"), coloured by its words.</summary>
public sealed record CountChip(string Words, Tone Tone);

/// <summary>A law's counts (the worker's <c>view.sections[]</c>: "Zoning (City of Ithaca)"), or the whole summary's
/// (<see cref="Title"/> null) from a worker that gives no sections.</summary>
public sealed record CountLine(string? Title, IReadOnlyList<CountChip> Chips);

/// <summary>Everything the results panel shows for one check.</summary>
/// <param name="State">The worker's overall state.</param>
/// <param name="Headline">"Does not comply: ..." (the worker's state and summary, as the text file says it).</param>
/// <param name="Checked">The phase, design options and street line checked.</param>
/// <param name="Counts">The worker's counts, never recounted.</param>
/// <param name="Groups">The worker's groups, in its order, every row in one.</param>
/// <param name="Inside">What the inside reader left out.</param>
/// <param name="Stale">Why these results no longer stand for the model (it changed since the check), or null while
/// they do: everything is then grey (<see cref="ResultRows.Stale"/>), never green.</param>
public sealed record ResultModel(Verdict State, string Headline, string Checked, IReadOnlyList<CountLine> Counts,
                                 IReadOnlyList<ResultGroup> Groups, string Inside, string? Stale = null)
{
    /// <summary>The state's colour: green only for a check that complies and still stands; red for one that
    /// doesn't; amber otherwise; grey once the model changed.</summary>
    public Tone StateTone => Stale is not null ? Tone.Neutral : State switch
    {
        Verdict.DoesNotComply => Tone.Fails,
        Verdict.Complies => Tone.Complies,
        _ => Tone.Review,
    };
}

/// <summary>The parts of the results panel, top to bottom (<see cref="ResultRows.Layout"/>).</summary>
public enum PanelPart
{
    /// <summary>"The model changed since this check (14:32): click Check again".</summary>
    Stale,
    /// <summary>The worker's state, one line.</summary>
    State,
    /// <summary>The worker's counts, one compact line of chips per law.</summary>
    Counts,
    /// <summary>The groups and their rows.</summary>
    Groups,
    /// <summary>What was not read from the model (folded).</summary>
    Inside,
    /// <summary>The phase, design options and street line checked, and where the files are (folded).</summary>
    Details,
}

/// <summary>
/// A check_site answer as rows (reading design note, section 9): the one model the text file
/// (<see cref="ResultText"/>) and the Revit results panel both read, so both say every row the same way. Nothing is
/// shown kinder than the worker said, nothing is recounted, and no figure is made that the worker didn't give.
/// </summary>
public static class ResultRows
{
    /// <summary>The whole panel: the worker's state and counts, and its groups with every row (none ever cut).</summary>
    public static ResultModel Build(CheckResult result, string? phase, IReadOnlyList<string> options, InteriorReadResult? inside,
                                    string? street = null)
    {
        ArgumentNullException.ThrowIfNull(result);
        ArgumentNullException.ThrowIfNull(options);
        var rows = result.Items.ToDictionary(i => i.Id, Row, StringComparer.Ordinal);
        var groups = result.Groups.Select(g => new ResultGroup(
            g.Key, g.Title, g.Count, g.Folded, Worst(g.Items.Select(id => rows[id])),
            g.Lines.Count == 0 ? g.Items.Select(id => rows[id]).ToList() : [],
            g.Lines.Select(l => new ResultLine(l.Title, ToneOf(l.Status, l.StatusWord), l.Folded,
                                               l.Items.Select(id => rows[id]).ToList())).ToList())).ToList();
        return new ResultModel(result.State, ResultText.Headline(result), ResultText.CheckedWords(phase, options, street),
                               Counts(result), groups, ResultText.InsideWords(inside));
    }

    /// <summary>The panel's parts in the order it shows them, all in one scrolling list: the stale notice (when
    /// stale), the state, the counts, then straight away the groups, so the first failing row is on screen at the
    /// pane's docked height (Revit 2027 trial: ~420 px); what was not read and the details (phase, options, street
    /// line, files) after the rows, folded.</summary>
    public static IReadOnlyList<PanelPart> Layout(ResultModel model)
    {
        ArgumentNullException.ThrowIfNull(model);
        var parts = new List<PanelPart>();
        if (model.Stale is not null)
            parts.Add(PanelPart.Stale);
        parts.AddRange([PanelPart.State, PanelPart.Counts, PanelPart.Groups]);
        if (model.Inside.Length > 0)
            parts.Add(PanelPart.Inside);
        parts.Add(PanelPart.Details);
        return parts;
    }

    /// <summary>The transactions "Check my project" itself makes before it shows a result (adding Gordium's marks,
    /// keeping the street edge picked): never a change that makes the result stale.</summary>
    public static readonly IReadOnlySet<string> OwnTransactions = new HashSet<string>(StringComparer.Ordinal)
    {
        MarksTransaction, StreetTransaction, AreasTransaction,
    };

    /// <summary>The names of those transactions (the add-in names its transactions with these).</summary>
    public const string MarksTransaction = "Gordium: add the egress marks";
    public const string StreetTransaction = "Gordium: the street edge";
    public const string AreasTransaction = "Gordium: read the enclosed areas (rolled back)";

    /// <summary>Whether a change to the checked project (Revit's DocumentChanged: its transactions' names) makes the
    /// shown results stale: any change but the check's own; a change with no name (an undo, a redo) too.</summary>
    public static bool ChangesTheCheck(IReadOnlyCollection<string> transactions)
    {
        ArgumentNullException.ThrowIfNull(transactions);
        return transactions.Count == 0 || transactions.Any(t => !OwnTransactions.Contains(t));
    }

    /// <summary>The results as shown once the model changed after the check (made at <paramref name="checkedAt"/>):
    /// every colour grey (the state, the counts, the groups, the lines, the rows: never a green "complies" for a
    /// model that may no longer comply), the words kept, and why said ("The model changed since this check (14:32):
    /// click Check again").</summary>
    public static ResultModel Stale(ResultModel model, DateTime checkedAt)
    {
        ArgumentNullException.ThrowIfNull(model);
        static ResultRow Grey(ResultRow r) => r with { Tone = Tone.Neutral };
        return model with
        {
            Stale = $"The model changed since this check ({checkedAt:HH:mm}): click Check again",
            Counts = model.Counts.Select(c => c with { Chips = c.Chips.Select(x => x with { Tone = Tone.Neutral }).ToList() }).ToList(),
            Groups = model.Groups.Select(g => g with
            {
                Tone = Tone.Neutral, Rows = g.Rows.Select(Grey).ToList(),
                Lines = g.Lines.Select(l => l with { Tone = Tone.Neutral, Rows = l.Rows.Select(Grey).ToList() }).ToList(),
            }).ToList(),
        };
    }

    /// <summary>The colour of a verdict: a word the add-in doesn't know is amber, never green.</summary>
    public static Tone ToneOf(Verdict v, string word) => !Verdicts.IsKnown(word) ? Tone.Review : v switch
    {
        Verdict.DoesNotComply => Tone.Fails,
        Verdict.Complies => Tone.Complies,
        Verdict.NotApplicable => Tone.Neutral,
        _ => Tone.Review,
    };

    /// <summary>The most cautious tone of the rows: red, then amber, green, grey; grey for none.</summary>
    private static Tone Worst(IEnumerable<ResultRow> rows)
    {
        var tones = rows.Select(r => r.Tone).ToList();
        return tones.Contains(Tone.Fails) ? Tone.Fails : tones.Contains(Tone.Review) ? Tone.Review
             : tones.Contains(Tone.Complies) ? Tone.Complies : Tone.Neutral;
    }

    /// <summary>One row, as the worker answered it.</summary>
    public static ResultRow Row(CheckItem row)
    {
        ArgumentNullException.ThrowIfNull(row);
        var raw = row.Raw;
        // an egress row's reason starts with its part, which its name already says: said once
        var reason = ResultText.Once(row.Reason);
        var part = row.Name.Split(" · ")[0];
        if (reason is not null && row.Name.Contains(" · ", StringComparison.Ordinal) && reason.StartsWith(part + ": ", StringComparison.Ordinal))
            reason = reason[(part.Length + 2)..];
        if (reason is { Length: 0 })
            reason = null;

        string? figures = null;
        var proposed = Text(raw, "proposed");
        var required = Text(raw, "required");
        if (proposed is not null && required is not null)
        {
            var sign = Text(raw, "sign") is { } g && !required.StartsWith(g, StringComparison.Ordinal) ? g + " " : "";
            figures = $"{proposed} measured, {sign}{required} allowed";
        }
        else if (required is not null)
            figures = $"allowed {required}";
        else if (reason is not null && Stated(reason) is { } stated)
            figures = stated;

        // the worker's delta when it gives one (an empty delta: it says nothing of how far); else its margin
        var howFar = raw.ValueKind == JsonValueKind.Object && raw.TryGetProperty("delta", out var d) && d.ValueKind != JsonValueKind.Null
            ? Text(raw, "delta") : Text(raw, "margin");

        return new ResultRow(row.Id, row.Name, row.Status, ResultText.RowWords(row), ToneOf(row.Status, row.StatusWord),
                             figures, howFar, reason, Section(raw), Quotes(raw), ResultText.Elements(raw));
    }

    // "net clear height 20 in, needs ≥ 24 in": the measure, the figure measured and the figure needed, as
    // each_part._first_failing writes them (the worker's numbers, copied, never computed)
    private static readonly Regex Needs = new(
        @"(?<=^|; |: )[a-z][a-z /'-]*? -?[0-9][0-9.,]*(?: (?:sq ft|[a-z%]+))?, needs [≥≤<>] -?[0-9][0-9.,]*(?: (?:sq ft|[a-z%]+))?(?=$|; |\. |, | \()",
        RegexOptions.CultureInvariant);

    /// <summary>The figures a reason states ("net clear height 20 in, needs ≥ 24 in"), each as it says it, or null
    /// when it states none: the whole reason when it is only that, so it is said once.</summary>
    internal static string? Stated(string reason)
    {
        var found = Needs.Matches(reason).Select(m => m.Value).ToList();
        return found.Count == 0 ? null : string.Join("; ", found);
    }

    /// <summary>The section an egress row is decided on (<c>code.section</c>), else the worker's citation.</summary>
    private static string? Section(JsonElement raw)
    {
        if (raw.ValueKind != JsonValueKind.Object)
            return null;
        if (raw.TryGetProperty("code", out var c) && c.ValueKind == JsonValueKind.Object && Text(c, "section") is { } s)
            return s;
        return raw.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.Object ? Text(d, "citation") : null;
    }

    /// <summary>The law's words the row was decided on: the worker's <c>detail.quotes</c> (each with where it is),
    /// else the one <c>code.quote</c>; none when it gives none (the panel then says so).</summary>
    private static List<LawQuote> Quotes(JsonElement raw)
    {
        var quotes = new List<LawQuote>();
        if (raw.ValueKind != JsonValueKind.Object)
            return quotes;
        if (raw.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.Object
            && d.TryGetProperty("quotes", out var qs) && qs.ValueKind == JsonValueKind.Array)
            foreach (var q in qs.EnumerateArray())
                if (q.ValueKind == JsonValueKind.Object && Text(q, "text") is { } t)
                    quotes.Add(new LawQuote(t, Text(q, "where")));
        if (quotes.Count == 0 && raw.TryGetProperty("code", out var c) && c.ValueKind == JsonValueKind.Object && Text(c, "quote") is { } one)
            quotes.Add(new LawQuote(one, Text(c, "section")));
        return quotes;
    }

    /// <summary>The worker's counts, its words exactly: each law's summary (<c>view.sections[]</c>) split at " · ",
    /// or the whole summary's when the sections can't be read. Each count is coloured by its own words: red only
    /// for "N do(es) not comply", green only for "N comply"/"N complies", amber for anything else.</summary>
    public static IReadOnlyList<CountLine> Counts(CheckResult result)
    {
        ArgumentNullException.ThrowIfNull(result);
        var lines = new List<CountLine>();
        if (result.Raw.ValueKind == JsonValueKind.Object && result.Raw.TryGetProperty("view", out var view)
            && view.ValueKind == JsonValueKind.Object && view.TryGetProperty("sections", out var ss) && ss.ValueKind == JsonValueKind.Array)
        {
            foreach (var s in ss.EnumerateArray())
            {
                if (s.ValueKind != JsonValueKind.Object || Text(s, "title") is not { } title || Text(s, "summary") is not { } summary)
                {
                    lines.Clear();
                    break;                                             // one not readable: the whole summary instead
                }
                lines.Add(new CountLine(title, Chips(summary)));
            }
        }
        return lines.Count > 0 ? lines : [new CountLine(null, Chips(result.Summary))];
    }

    private static readonly Regex FailsWords = new(@"^(?:[^:]+: )?[0-9]+ (?:do|does) not comply$", RegexOptions.CultureInvariant);
    private static readonly Regex ComplyWords = new(@"^(?:[^:]+: )?[0-9]+ compl(?:y|ies)$", RegexOptions.CultureInvariant);

    private static List<CountChip> Chips(string summary) =>
        summary.Split(" · ", StringSplitOptions.RemoveEmptyEntries)
               .Select(p => new CountChip(p, FailsWords.IsMatch(p) ? Tone.Fails : ComplyWords.IsMatch(p) ? Tone.Complies : Tone.Review))
               .ToList();

    /// <summary>A text field, or null when absent, empty or the worker's "—" (nothing measured).</summary>
    internal static string? Text(JsonElement raw, string name) =>
        raw.ValueKind == JsonValueKind.Object && raw.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String
        && v.GetString() is { Length: > 0 } t && t != "—" ? t : null;
}
