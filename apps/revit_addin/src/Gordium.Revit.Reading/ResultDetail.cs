using System.Globalization;

namespace Gordium.Revit.Reading;

/// <summary>What a step of "What to do" lets the architect do from the panel.</summary>
public enum DetailAction
{
    /// <summary>Words only (the worker's advice, or a step done in the model).</summary>
    None,
    /// <summary>Show (zoom to) the row's elements in the model.</summary>
    ShowElements,
    /// <summary>Open the law at its page (the worker's first link).</summary>
    OpenLaw,
    /// <summary>Check the project again: only the check changes a verdict.</summary>
    CheckAgain,
}

/// <summary>One step of "What to do": its words and what its button does.</summary>
public sealed record DetailStep(string Words, DetailAction Action);

/// <summary>An element the row is about, by the name the architect knows it by (<see cref="ElementNames"/>).</summary>
/// <param name="Uid">Its UniqueId (what Show selects).</param>
/// <param name="Name">"CLOSET (40)", "Door D06"; "not in this model now" for one the project no longer has.</param>
/// <param name="InModel">Whether the project has it (else Show can't select it).</param>
/// <param name="RevitId">Revit's element id, for Select by ID, when the project has it.</param>
public sealed record DetailElement(string Uid, string Name, bool InModel, long? RevitId = null)
{
    /// <summary>Its Show button's tooltip: "Zoom to CLOSET (40) in the model. Revit id 341207, for Select by ID".</summary>
    public string ShowTip => $"Zoom to {Name} in the model" +
        (RevitId is { } id ? $". Revit id {id.ToString(CultureInfo.InvariantCulture)}, for Select by ID" : "");
}

/// <summary>
/// A result's detail (docs/revit/ui_design_pass.md section 2.4, PR 4): everything the panel shows for one row, every
/// word and figure the worker's or the add-in's fixed words, never a figure made here.
/// </summary>
/// <param name="Position">"3 of 8": the row's place among the rows the list shows (a count of rows, not a figure).</param>
/// <param name="Status">Its glyph and colour: the row's own (the clock once stale, never green then).</param>
/// <param name="VerdictWords">Its verdict in words, as the list and the text file say it.</param>
/// <param name="Name">The rule's name (with its part) as the worker gives it.</param>
/// <param name="Section">The law's section, or null.</param>
/// <param name="Stale">Why the verdict may no longer hold (the model changed since the check), or null.</param>
/// <param name="Why">The worker's reason, in full, or null when it gives none or it only restates the figures.</param>
/// <param name="Steps">What to do, in order; empty for a row that complies or doesn't apply (and still stands).</param>
/// <param name="Figures">The figures against their limits, in the worker's words.</param>
/// <param name="HowFar">How far off (or the room to spare), the worker's words, or null.</param>
/// <param name="Quotes">The law's exact words, each with where it is.</param>
/// <param name="NoQuote">What the panel says when the worker sent no quote, or null.</param>
/// <param name="Links">"Open the law": the worker's links to the source at its page.</param>
/// <param name="Elements">The elements, by name.</param>
public sealed record ResultDetail(string Position, PanelStatus Status, string VerdictWords, string Name, string? Section,
                                  string? Stale, string? Why, IReadOnlyList<DetailStep> Steps,
                                  IReadOnlyList<FigureLine> Figures, string? HowFar, IReadOnlyList<LawQuote> Quotes,
                                  string? NoQuote, IReadOnlyList<LawLink> Links, IReadOnlyList<DetailElement> Elements)
{
    /// <summary>The measured-vs-limit bar (the row's, from the worker's two lengths), or null.</summary>
    public MeasureBar? Bar { get; init; }

    /// <summary>Whether the row takes a "looked at" tick (<see cref="LookedAt.Tickable"/>).</summary>
    public bool Tickable { get; init; }

    /// <summary>The worker's row id (what its tick is kept by).</summary>
    public string Id { get; init; } = "";

    /// <summary>The generic "What to do" step of a row in review with no advice of its own: the pane shows the fix the
    /// row waits on in its place (<see cref="Fixes.Step"/>), when there is one.</summary>
    public const string ResolveStep =
        "Resolve what the reason above says (a fact to enter, a mark to set, the model to fix), or decide it by hand against the law's words below.";

    /// <summary>Whether a step is the generic one (<see cref="ResolveStep"/>).</summary>
    public static bool IsGenericStep(DetailStep step) => step?.Words == ResolveStep;

    /// <summary>The detail as plain text, top to bottom (the snapshot tests' form, and what a screen reader reads).</summary>
    public string Text()
    {
        var s = new List<string> { $"[{Position}] {VerdictWords} · {Name}" + (Section is null ? "" : $" · {Section}") };
        if (Stale is not null)
            s.Add("STALE: " + Stale);
        if (Why is not null)
            s.Add("WHY: " + Why);
        if (Steps.Count > 0)
            s.Add("WHAT TO DO:");
        s.AddRange(Steps.Select((x, i) => $"  {i + 1}. {x.Words}" + (x.Action == DetailAction.None ? "" : $" [{x.Action}]")));
        if (Figures.Count > 0)
            s.Add("MEASURED VS LIMIT:");
        s.AddRange(Figures.Select(f => $"  {f.What ?? "figure"}: {f.Measured ?? "—"} ({f.How}) | limit {f.Limit}"));
        if (HowFar is not null)
            s.Add("HOW FAR: " + HowFar);
        if (Bar is not null)
            s.Add($"BAR: {Bar.Words} (the bar's marks: {Bar.Measured.ToString("R", CultureInfo.InvariantCulture)} and limit " +
                  $"{Bar.Limit.ToString("R", CultureInfo.InvariantCulture)} {Bar.Unit}, the worker's numbers)");
        s.Add("THE LAW'S WORDS:");
        if (NoQuote is not null)
            s.Add("  " + NoQuote);
        s.AddRange(Quotes.Select(q => $"  \"{q.Text}\"" + (q.Where is null ? "" : $" ({q.Where})")));
        s.AddRange(Links.Select(l => $"  OPEN THE LAW: {l.Citation} <{l.Url}>"));
        if (Elements.Count > 0)
            s.Add("ELEMENTS:");
        s.AddRange(Elements.Select(e => "  " + e.Name + (e.InModel ? "" : " (not in this model now)")));
        return string.Join("\n", s);
    }
}

/// <summary>
/// A row's detail made from the row alone (Revit-free, so it is tested): the worker's reason as Why, "What to do"
/// from the worker's advice and the row's own place, the figures and how far off in the worker's words, the law's
/// words and links as the worker sent them, and the elements by their project names. Never a false pass: a stale
/// row says so first and is never green; no step ever says a row will comply; the last step of anything not
/// complying is Check again (only the check changes a verdict).
/// </summary>
public static class Details
{
    /// <summary>Words for an element the project no longer has.</summary>
    public const string NotInModel = "not in this model now";

    /// <summary>The detail of <paramref name="row"/>, the <paramref name="index"/>-th (from 0) of <paramref name="count"/>
    /// rows the list shows; <paramref name="labels"/>: each element's name by UniqueId (absent: not in the model now);
    /// <paramref name="staleSince"/>: when the check was made, once the model changed after it; <paramref name="ids"/>:
    /// each element's Revit id by UniqueId (its Show tooltip says it, for Select by ID).</summary>
    public static ResultDetail Of(ListRow row, int index, int count, IReadOnlyDictionary<string, string>? labels, DateTime? staleSince,
                                  IReadOnlyDictionary<string, long>? ids = null)
    {
        ArgumentNullException.ThrowIfNull(row);
        var r = row.Row;
        var stale = staleSince is { } at
            ? $"The model changed after this check ({at:HH:mm}): this verdict may no longer hold. Check again before acting on it."
            : null;
        var elements = r.Elements.Select(uid => labels?.GetValueOrDefault(uid) is { } name
            ? new DetailElement(uid, name, true, ids is not null && ids.TryGetValue(uid, out var id) ? id : null)
            : new DetailElement(uid, NotInModel, false)).ToList();
        var why = r.Reason is null || r.ReasonIsFigures || r.Reason == r.Hint ? null : r.Reason;
        return new ResultDetail(
            string.Create(CultureInfo.InvariantCulture, $"{index + 1} of {count}"), row.Status, r.VerdictWords, r.Name, r.Section,
            stale, why, Steps(row, elements, stale is not null), r.FigureLines, r.HowFar, r.Quotes,
            r.Quotes.Count == 0 ? "The checker sent no quote with this row" + (r.Section is null ? "." : $": see {r.Section}.") : null,
            r.Links, elements)
        {
            Bar = r.Bar, Tickable = LookedAt.Tickable(row), Id = r.Id,
        };
    }

    /// <summary>What to do, from the worker's own advice and the row's place (never a figure of the add-in's): a
    /// failure is changed in the design; a needs review is resolved as its reason says, or decided by hand; a row to
    /// check by hand is checked against the law's words; then show its elements, open the law, and Check again. A row
    /// that complies or doesn't apply has nothing to do, unless the model changed since (then: Check again).</summary>
    public static IReadOnlyList<DetailStep> Steps(ListRow row, IReadOnlyList<DetailElement> elements, bool stale)
    {
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(elements);
        var r = row.Row;
        var steps = new List<DetailStep>();
        if (row.Section == ListSection.Complies)
        {
            if (stale)
                steps.Add(new("Check again: the model changed after this check.", DetailAction.CheckAgain));
            return steps;
        }
        if (r.Hint is not null)
            steps.Add(new(r.Hint, DetailAction.None));                       // the worker's own advice, first
        steps.Add(new(row.Section switch
        {
            ListSection.Fails => r.Hint is null
                ? "Change the design so it meets the limit (the figures below)."
                : "Or change the design another way, so it meets the limit.",
            ListSection.ByHand when r.Verdict == Gordium.Worker.Verdict.NotChecked
                => "Give what the check needs (the reason above says what), or check it by hand against the law's words below.",
            ListSection.ByHand => "Check it by hand against the law's words below: Gordium doesn't decide this one yet.",
            _ => ResultDetail.ResolveStep,
        }, DetailAction.None));
        var shown = elements.Count(e => e.InModel);
        if (shown > 0)
            steps.Add(new(shown == 1 ? $"Show {elements.First(e => e.InModel).Name} in the model." : $"Show its {shown} elements in the model.",
                          DetailAction.ShowElements));
        if (r.Links.Count > 0)
            steps.Add(new($"Open the law at {r.Links[0].Citation}.", DetailAction.OpenLaw));
        steps.Add(new("Check again once it's changed: only the check changes a verdict.", DetailAction.CheckAgain));
        return steps;
    }

    /// <summary>The row the detail's Back returns to and the neighbours Previous / Next go to: the rows the list shows,
    /// in order (headings and sub-headings skipped), and where <paramref name="id"/> is among them (−1 if not shown).</summary>
    public static (IReadOnlyList<ListRow> Rows, int Index) Among(IReadOnlyList<ListEntry> entries, string id)
    {
        ArgumentNullException.ThrowIfNull(entries);
        var rows = entries.OfType<ListRowEntry>().Select(e => e.Row).ToList();
        return (rows, rows.FindIndex(p => p.Row.Id == id));
    }
}
