namespace Gordium.Revit.Reading;

/// <summary>What the panel draws for a verdict, a group or a count: its shape and word as well as its colour (colour
/// is never the only sign). Stale is its own: results the model changed after are never drawn as any verdict's
/// colour, least of all a pass's.</summary>
public enum PanelStatus { Fails, Review, Complies, NotApplicable, Stale }

/// <summary>One status glyph (16 by 16, WPF path markup): its outline, drawn in the status colour and filled with
/// <see cref="Fill"/> when it has one, and its mark inside, stroked.</summary>
/// <param name="Outline">The shape: an octagon, a triangle, a circle.</param>
/// <param name="Mark">What is drawn in it: ✕, ?, ✓, a dash, a clock's hands.</param>
/// <param name="Fill">The colour token filling the outline, or null (drawn open).</param>
public sealed record Glyph(string Outline, string Mark, string? Fill);

/// <summary>
/// Each status's look (design pass section 2.5): its colour token, its glyph and its word. Pure decisions, tested in
/// Gordium.Revit.Reading.Tests: every status a different shape and a different word; green only for what the worker
/// said complies, and never once the results are stale.
/// </summary>
public static class StatusLook
{
    /// <summary>A tone's status: stale results are <see cref="PanelStatus.Stale"/> whatever their tone (never green);
    /// else red, amber, green or grey as the tone, which is green only for the worker's "complies"
    /// (<see cref="ResultRows.ToneOf"/>).</summary>
    public static PanelStatus Of(Tone tone, bool stale) => stale ? PanelStatus.Stale : tone switch
    {
        Tone.Fails => PanelStatus.Fails,
        Tone.Complies => PanelStatus.Complies,
        Tone.Neutral => PanelStatus.NotApplicable,
        _ => PanelStatus.Review,
    };

    /// <summary>The status in words, said with its glyph (its tooltip and the name a screen reader reads).</summary>
    public static string Word(PanelStatus s) => s switch
    {
        PanelStatus.Fails => "Does not comply",
        PanelStatus.Review => "Needs review",
        PanelStatus.Complies => "Complies",
        PanelStatus.NotApplicable => "Not applicable",
        PanelStatus.Stale => "Stale: the model changed after this check",
        _ => throw new ArgumentOutOfRangeException(nameof(s)),
    };

    /// <summary>The status's colour token.</summary>
    public static string Colour(PanelStatus s) => s switch
    {
        PanelStatus.Fails => PanelTokens.StatusFail,
        PanelStatus.Review => PanelTokens.StatusReview,
        PanelStatus.Complies => PanelTokens.StatusPass,
        PanelStatus.NotApplicable => PanelTokens.StatusNa,
        PanelStatus.Stale => PanelTokens.StatusStale,
        _ => throw new ArgumentOutOfRangeException(nameof(s)),
    };

    /// <summary>The background a count chip of this status sits on: its fill, or bg.hover (not applicable, stale).</summary>
    public static string ChipBackground(PanelStatus s) => GlyphOf(s).Fill ?? PanelTokens.BgHover;

    // the mockup's glyphs (ui_mockup/index.html, ICONS), in WPF's path markup (a circle as two arcs)
    private const string Circle = "M 1.6,8 A 6.4,6.4 0 1 1 14.4,8 A 6.4,6.4 0 1 1 1.6,8 Z";

    /// <summary>The status's glyph: fail an octagon with ✕, needs review a triangle with ?, complies a circle with
    /// ✓, not applicable an open circle with a dash, stale an open circle with a clock's hands.</summary>
    public static Glyph GlyphOf(PanelStatus s) => s switch
    {
        PanelStatus.Fails => new("M 5.2,1.5 H 10.8 L 14.5,5.2 V 10.8 L 10.8,14.5 H 5.2 L 1.5,10.8 V 5.2 Z",
                                 "M 5.8,5.8 L 10.2,10.2 M 10.2,5.8 L 5.8,10.2", PanelTokens.StatusFailFill),
        PanelStatus.Review => new("M 8,1.8 L 14.6,13.4 H 1.4 Z",
                                  "M 6.4,6.6 A 1.7,1.7 0 1 1 9.4,7.7 C 8.8,8.2 8,8.5 8,9.5 M 8,11.4 V 11.5", PanelTokens.StatusReviewFill),
        PanelStatus.Complies => new(Circle, "M 5,8.2 L 7,10.2 L 11,5.8", PanelTokens.StatusPassFill),
        PanelStatus.NotApplicable => new(Circle, "M 5,8 H 11", null),
        PanelStatus.Stale => new(Circle, "M 8,4.5 V 8 L 10.4,9.6", null),
        _ => throw new ArgumentOutOfRangeException(nameof(s)),
    };

    /// <summary>Every status, in the panel's order (the most cautious first, stale last).</summary>
    public static IReadOnlyList<PanelStatus> All { get; } = Enum.GetValues<PanelStatus>();
}
