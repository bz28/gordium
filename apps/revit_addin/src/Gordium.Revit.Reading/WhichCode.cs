using System.Text.Json;

namespace Gordium.Revit.Reading;

/// <summary>One place in the law the code was chosen on (the worker's <c>which_code.cites[]</c>: design_checker
/// code_scope.decide's section, document, page and quote).</summary>
public sealed record CodeCite(string? Section, string? Page, string? Quote, string? Document = null);

/// <summary>
/// Which code the building was checked against, and why, as the worker sends it (<c>which_code</c>: Ben, 2026-11-22):
/// the code's title and why ("a detached one-family dwelling, 3 stories above grade plane (R101.2)"), with the law's
/// words it rests on; or, when the worker couldn't decide, what it asks. Read tolerantly: an answer without it (an
/// older worker, a zoning-only check) shows nothing, never a guess. Words only from the worker; the line is never
/// green (a code chosen is a fact of the check, not a pass), a code not decided is needs review, and a stale result
/// greys it like the rest.
/// </summary>
/// <param name="Code">The worker's code word ("residential_code", "building_code"), or null when not decided.</param>
/// <param name="Title">The code's title as the worker gives it, or null.</param>
/// <param name="Why">Why that code, the worker's words, or null.</param>
/// <param name="Ask">What the worker asks when it couldn't decide, or null.</param>
/// <param name="Cites">The law's words the choice rests on.</param>
public sealed record WhichCode(string? Code, string? Title, string? Why, string? Ask, IReadOnlyList<CodeCite> Cites)
{
    /// <summary>Whether a code was decided: a code word and its title both sent (anything less is needs review).</summary>
    public bool Decided => Code is not null && Title is not null;

    /// <summary>The line: "Checked against: {title} — {why}", or "Which code: needs review — {ask}".</summary>
    public string Words => Decided
        ? "Checked against: " + Title + (Why is null ? "" : " — " + Why)
        : "Which code: needs review" + (Ask is null ? "" : " — " + Ask);

    /// <summary>Its status: needs review when not decided; none (plain words, never green) when decided; stale once
    /// the model changed.</summary>
    public PanelStatus? Status(bool stale) => stale ? PanelStatus.Stale : Decided ? null : PanelStatus.Review;

    /// <summary>The tooltip: each cited section and page with the law's quoted words, one a paragraph; null for none.</summary>
    public string? Tooltip => Cites.Count == 0 ? null : string.Join("\n\n", Cites.Select(c =>
        string.Join(", ", new[] { c.Section, c.Document, c.Page is null ? null : "p." + c.Page }.Where(x => x is not null))
        + (c.Quote is null ? "" : (c.Section ?? c.Document ?? c.Page) is null ? "“" + c.Quote + "”" : ": “" + c.Quote + "”")));

    /// <summary>The worker's <c>which_code</c> in a check's result, or null when it sends none (or not an object).
    /// A field of another kind than expected is as if not sent.</summary>
    public static WhichCode? Read(JsonElement result)
    {
        if (result.ValueKind != JsonValueKind.Object || !result.TryGetProperty("which_code", out var w) || w.ValueKind != JsonValueKind.Object)
            return null;
        var cites = new List<CodeCite>();
        if (w.TryGetProperty("cites", out var cs) && cs.ValueKind == JsonValueKind.Array)
            foreach (var c in cs.EnumerateArray())
                if (c.ValueKind == JsonValueKind.Object && new CodeCite(Field(c, "section"), Field(c, "page"), Field(c, "quote"), Field(c, "document")) is var cite
                    && (cite.Section ?? cite.Page ?? cite.Quote ?? cite.Document) is not null)
                    cites.Add(cite);
        return new WhichCode(Field(w, "code"), Field(w, "title"), Field(w, "why"), Field(w, "ask"), cites);
    }

    /// <summary>A text (or a number, a page) field's words, or null.</summary>
    private static string? Field(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) ? v.ValueKind switch
        {
            JsonValueKind.String when v.GetString() is { } s && !string.IsNullOrWhiteSpace(s) => s.Trim(),
            JsonValueKind.Number => v.GetRawText(),
            _ => null,
        } : null;
}
