using System.Text.RegularExpressions;
using Gordium.Worker;

namespace Gordium.Revit.Reading;

// A result's detail as the UI polish lays it out (changes 28 to 32; Ben approved 2026-11-23): a one-line headline of
// what is needed with the action beside it, the checker's own words behind "Why?", plain numbered steps, one cite under
// the title, the first quote of the law shown with the rest folded, and "Measured against the limit" only when
// something was measured. Revit-free and tested; DetailView only draws it. The rules: every word here is the checker's
// (its asks' headlines, its reason, its quotes and links) or a fixed sentence of the pane's; no step ever says a result
// will pass; a result that isn't settled always ends with what moves it: "Check again", or for one a person looks at,
// the tick and when a check can decide it; nothing measured is never shown as measured.

/// <summary>What the callout's one button does.</summary>
public enum CalloutAction
{
    /// <summary>No button (a judgment, a hand check: the words are the action).</summary>
    None,

    /// <summary>Go to "Answer N questions about the project" in What to fix, where the questions are asked.</summary>
    Answer,

    /// <summary>Show the result's elements in the model.</summary>
    Show,
}

/// <summary>The detail page's parts, in its order.</summary>
/// <param name="Cite">The one cite under the title: the element and the section ("APARTMENT SOUTH L1 (1) · BCNYS
/// 1006.2.1"), or "" when the result names neither.</param>
/// <param name="Headline">The callout's one line of what is needed (the checker's ask's headline when it asks one
/// thing), or null for a result that is settled (no callout).</param>
/// <param name="Action">The callout's button.</param>
/// <param name="ActionWords">Its words ("Answer 2 questions", "Show in model"), or null.</param>
/// <param name="Steps">What to do, as plain numbered sentences (no buttons: the one button is the callout's).</param>
/// <param name="ShowMeasured">Whether "Measured against the limit" is shown: only when a figure was measured.</param>
/// <param name="FirstQuote">The law's first quote, shown, or null when none was sent.</param>
/// <param name="MoreQuotes">The rest, folded.</param>
/// <param name="MoreWords">The fold's words ("2 more quotes"), or null when there are none.</param>
/// <param name="Open">The link "Open the code" opens (the checker's first), or null.</param>
/// <param name="OpenWords">"Open the code at p.315".</param>
/// <param name="OtherLinks">The checker's other links, in the fold.</param>
/// <param name="NoLink">What the page says when the checker sent no link, or null.</param>
public sealed record DetailPage(string Cite, string? Headline, CalloutAction Action, string? ActionWords,
                                IReadOnlyList<string> Steps, bool ShowMeasured, LawQuote? FirstQuote,
                                IReadOnlyList<LawQuote> MoreQuotes, string? MoreWords, LawLink? Open, string? OpenWords,
                                IReadOnlyList<LawLink> OtherLinks, string? NoLink)
{
    /// <summary>The page as plain text, top to bottom (what the tests read).</summary>
    public string Text()
    {
        var s = new List<string> { "CITE: " + Cite };
        if (Headline is not null)
            s.Add("HEADLINE: " + Headline + (ActionWords is null ? "" : $" [{ActionWords}]"));
        s.AddRange(Steps.Select((x, i) => $"  {i + 1}. {x}"));
        s.Add("MEASURED: " + (ShowMeasured ? "shown" : "not shown"));
        if (FirstQuote is not null)
            s.Add($"QUOTE: \"{FirstQuote.Text}\"" + (FirstQuote.Where is null ? "" : $" ({FirstQuote.Where})"));
        if (MoreWords is not null)
            s.Add("FOLDED: " + MoreWords);
        if (OpenWords is not null)
            s.Add("OPEN: " + OpenWords);
        if (NoLink is not null)
            s.Add(NoLink);
        return string.Join("\n", s);
    }
}

public static class DetailPages
{
    /// <summary>The last step of anything not settled: only a check changes a verdict.</summary>
    public const string CheckAgainStep = "Check again. Only a check changes a verdict.";

    /// <summary>The callout's headline when the checker asks more than one thing for a result: what to do first, never
    /// that doing it decides the result (the checker's reason may name more: it is behind "Why?").</summary>
    public static string Several(int n) => $"Gordium can't decide this result yet. Start with these {n} things, then check again.";

    /// <summary>The callout's headline when every one of several asks is for a person to look at: never "then check
    /// again", which by itself changes nothing for these (egress UI audit, finding 2); "yet", as a later check may decide
    /// it (review round 1).</summary>
    public static string SeveralByHand(int n) => $"Gordium can't decide this result yet. Look at these {n} things yourself.";

    /// <summary>The step of a result a person looks at (every ask one for a person, or none): the tick at the page's
    /// foot, which is the architect's own note and never a verdict (egress UI audit, finding 2).</summary>
    public const string LookedStep = "When you've looked at it, tick " + LookedLabel + " below: it's your own note, not a verdict.";

    /// <summary>The tick's label at the page's foot (DetailView draws it), which <see cref="LookedStep"/> names.</summary>
    public const string LookedLabel = "Mark as looked at";

    /// <summary>Its last step: a check decides it only once something changes (the design, or a fact Gordium reads: spot
    /// grades for sloped ground, a curved surface modelled flat, a design that meets every reading of the law), so
    /// Check again is said with when it helps, never as the way forward by itself (review round 1).</summary>
    public const string CheckAfterChangeStep = "Check again after a change to the design or its facts: a check decides it once Gordium can.";

    /// <summary>Whether an ask is for a person to look at (to measure, to decide, an open question about the law): a
    /// check again with nothing changed doesn't decide it (some a later check can, once the design or a fact Gordium
    /// reads changes).</summary>
    public static bool ByHand(FixKind kind) => kind is FixKind.Measure or FixKind.Decide or FixKind.OpenQuestion;

    /// <summary>The section "Why?" opens on.</summary>
    public const string WhyHeading = "In the checker's words";

    /// <summary>The page of <paramref name="d"/> (the detail as Details.Of makes it), the row <paramref name="row"/>,
    /// and <paramref name="cards"/>: the What to fix cards that list the row (the checker's asks for it,
    /// <see cref="ResultViews.CardsOf"/>), in their order.</summary>
    public static DetailPage Of(ResultDetail d, ListRow row, IReadOnlyList<FixCard> cards)
    {
        ArgumentNullException.ThrowIfNull(d);
        ArgumentNullException.ThrowIfNull(row);
        ArgumentNullException.ThrowIfNull(cards);
        var r = row.Row;
        var asks = cards.Where(c => c.Kind is not (FixKind.Fails or FixKind.NotChecked or FixKind.Done)).ToList();
        var inModel = d.Elements.Where(e => e.InModel).ToList();
        string? headline;
        var action = CalloutAction.None;
        string? actionWords = null;
        var steps = new List<string>();
        // a result only a person can settle: every ask a check by hand, or none (never one that fails)
        var byHand = row.Section != ListSection.Fails && asks.All(a => ByHand(a.Kind));
        switch (row.Section)
        {
            case ListSection.Complies:
                headline = null;                                  // settled: no callout, nothing to do
                break;
            case ListSection.Fails:
                headline = Sentence(r.Hint ?? "Change the design so it meets the limit");
                if (r.Hint is not null)
                    steps.Add(Sentence(r.Hint));
                steps.Add(r.Hint is null ? "Change the design so it meets the limit (the figures below)." : "Or change the design another way, so it meets the limit.");
                break;
            default:
                if (asks.Count > 0)
                {
                    headline = asks.Count == 1 ? Sentence(asks[0].Headline) : byHand ? SeveralByHand(asks.Count) : Several(asks.Count);
                    if (r.Hint is not null)
                        steps.Add(Sentence(r.Hint));
                    steps.AddRange(asks.Select(a => Sentence(a.Headline)));
                    var questions = asks.Count(a => a.Kind == FixKind.Answer);
                    if (questions > 0)
                        (action, actionWords) = (CalloutAction.Answer, questions == 1 ? "Answer 1 question" : $"Answer {questions} questions");
                }
                else
                {
                    var notChecked = r.Verdict == Verdict.NotChecked;
                    headline = notChecked ? "Not checked yet by Gordium. Check it by hand against the code's words below."
                        : row.Section == ListSection.ByHand ? "Check it by hand against the code's words below: Gordium doesn't decide this one yet."
                        : "Decide it by hand against the code's words below.";
                    if (r.Hint is not null)
                        steps.Add(Sentence(r.Hint));
                    steps.Add(headline);
                }
                break;
        }
        // the one button: answering is in the questions card; else the elements to fix or look at, when the model has them
        if (headline is not null && action == CalloutAction.None && inModel.Count > 0)
            (action, actionWords) = (CalloutAction.Show, "Show in model");
        // anything not settled, and anything settled the model changed after, ends with Check again; a result a person
        // looks at ends with the tick, then Check again after a change; when the model changed after its check, Check
        // again comes first (its asks may be out of date), then the tick (confirm round)
        if (row.Section != ListSection.Complies && byHand)
        {
            if (d.Stale is not null)
                steps.Add(CheckAgainStep);
            steps.Add(LookedStep);
            if (d.Stale is null)
                steps.Add(CheckAfterChangeStep);
        }
        else if (row.Section != ListSection.Complies || d.Stale is not null)
            steps.Add(CheckAgainStep);
        var measured = d.Bar is not null || d.HowFar is not null || d.Figures.Any(f => f.Measured is not null);
        var more = d.Quotes.Skip(1).ToList();
        var link = d.Links.Count > 0 ? d.Links[0] : null;
        return new DetailPage(Cite(d, inModel), headline, action, actionWords, steps, measured,
                              d.Quotes.Count > 0 ? d.Quotes[0] : null, more,
                              more.Count == 0 && d.Links.Count < 2 ? null : MoreWords(more.Count, d.Links.Count - 1),
                              link, link is null ? null : OpenWords(link), [.. d.Links.Skip(1)],
                              link is null ? NoLinkWords(d.Section) : null);
    }

    /// <summary>The one cite under the title (change 32): the element when the result is about one, and the first of
    /// the result's sections ("§325-28C, p.72; §325-8 …" → "§325-28C, p.72"); every cite stays in What the code says.</summary>
    private static string Cite(ResultDetail d, IReadOnlyList<DetailElement> inModel)
    {
        var parts = new List<string>();
        if (inModel.Count == 1)
            parts.Add(inModel[0].Name);
        if (d.Section is { } s && s.Split(';')[0].Trim() is { Length: > 0 } first)
            parts.Add(first);
        return string.Join(" · ", parts);
    }

    private static readonly Regex PageOf = new(@"\bp\.\s*(?<p>\d+)\b", RegexOptions.CultureInvariant);

    /// <summary>"Open the code at p.315" (the page the checker's link names), else "Open the code at {citation}".</summary>
    public static string OpenWords(LawLink link)
    {
        ArgumentNullException.ThrowIfNull(link);
        return PageOf.Match(link.Citation) is { Success: true } m ? $"Open the code at p.{m.Groups["p"].Value}" : $"Open the code at {link.Citation}";
    }

    private static string NoLinkWords(string? section) =>
        section is { Length: > 0 } s ? $"No link for this one: find it at {s}." : "No link for this one.";

    private static string MoreWords(int quotes, int links)
    {
        var parts = new List<string>();
        if (quotes > 0)
            parts.Add(quotes == 1 ? "1 more quote" : $"{quotes} more quotes");
        if (links > 0)
            parts.Add(links == 1 ? "1 more link" : $"{links} more links");
        return string.Join(" and ", parts);
    }

    /// <summary>A headline or step as a sentence: a capital first letter and a full stop (unless it ends in one).</summary>
    public static string Sentence(string words)
    {
        ArgumentNullException.ThrowIfNull(words);
        var w = PaneWords.Capital(words.Trim());
        if (w.Length == 0 || w[^1] is '.' or '?' or '!')
            return w;
        // a question with its section after it ("Is a home business planned? (§325-3B)") is already a sentence
        var open = w.LastIndexOf(" (", StringComparison.Ordinal);
        if (w[^1] == ')' && open > 0 && w[open - 1] is '.' or '?' or '!')
            return w;
        return w + ".";
    }
}
