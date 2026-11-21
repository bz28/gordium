using System.Globalization;

namespace Gordium.Revit.Reading;

/// <summary>Revit's own light or dark theme, which the results panel follows (UIThemeManager.CurrentTheme).</summary>
public enum PanelTheme { Light, Dark }

/// <summary>A colour as its red, green and blue bytes ("#1D2229").</summary>
public readonly record struct Rgb(byte R, byte G, byte B)
{
    /// <summary>A colour from "#RRGGBB".</summary>
    public static Rgb Parse(string hex)
    {
        ArgumentNullException.ThrowIfNull(hex);
        if (hex.Length != 7 || hex[0] != '#' || !int.TryParse(hex.AsSpan(1), NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var v))
            throw new FormatException($"not a #RRGGBB colour: \"{hex}\"");
        return new Rgb((byte)(v >> 16), (byte)(v >> 8), (byte)v);
    }

    public override string ToString() => $"#{R:X2}{G:X2}{B:X2}";

    /// <summary>The colour's relative luminance, WCAG 2.2's definition (sRGB, 0 for black to 1 for white).</summary>
    public double Luminance => 0.2126 * Linear(R) + 0.7152 * Linear(G) + 0.0722 * Linear(B);

    private static double Linear(byte c)
    {
        var s = c / 255.0;
        return s <= 0.04045 ? s / 12.92 : Math.Pow((s + 0.055) / 1.055, 2.4);
    }
}

/// <summary>One type token (design pass section 2.5): its size in WPF device-independent pixels, weight, family,
/// and whether its figures line up (tabular numerals).</summary>
/// <param name="Name">"type.body".</param>
/// <param name="Size">The size, in device-independent pixels.</param>
/// <param name="SemiBold">SemiBold (600) when true, else Regular (400).</param>
/// <param name="Family">The font family (a WPF fallback list).</param>
/// <param name="Tabular">Whether numerals are tabular (figures aligned).</param>
public sealed record TypeToken(string Name, double Size, bool SemiBold, string Family, bool Tabular = false);

/// <summary>
/// The results panel's look as data (docs/revit/ui_design_pass.md section 2.5): the colour tokens of each theme,
/// the type tokens, and where each text and mark sits, so its contrast is tested here (WCAG 2.2: text at least
/// 4.5:1 on what it sits on, a status mark at least 3:1). The add-in builds one WPF ResourceDictionary per theme
/// from these tables and swaps it when Revit's theme changes; no colour is written anywhere else.
/// </summary>
public static class PanelTokens
{
    public const string BgPane = "bg.pane";
    public const string BgSurface = "bg.surface";
    public const string BgHover = "bg.hover";
    public const string BgSelected = "bg.selected";
    public const string Line = "line";
    public const string Text = "text";
    public const string TextMuted = "text.muted";
    public const string Accent = "accent";
    /// <summary>Text on an accent background (the mockup's <c>--accent-ink</c>).</summary>
    public const string AccentInk = "accent.ink";
    public const string StatusFail = "status.fail";
    public const string StatusFailFill = "status.fail.fill";
    public const string StatusReview = "status.review";
    public const string StatusReviewFill = "status.review.fill";
    public const string StatusPass = "status.pass";
    public const string StatusPassFill = "status.pass.fill";
    public const string StatusNa = "status.na";
    /// <summary>Stale: the muted text colour (hatched where it fills a bar), never a status hue.</summary>
    public const string StatusStale = "status.stale";
    /// <summary>A fact the architect marked (a confirmed mark, the checklist): blue, never the pass green.</summary>
    public const string Marked = "marked";
    public const string MarkedFill = "marked.fill";

    // The design note's values (docs/revit/ui_design_pass.md section 2.5, origin/design/revit-ui-pass 5758d576):
    // section 2.5's first table with the mockup's fills, changed where a text colour was under 4.5:1 on a background
    // or its own fill (light accent, fail, review, pass, na; dark text.muted, accent, bg.selected, fail, pass, na).
    private static readonly Dictionary<string, Rgb> LightColours = Table(
        (BgPane, "#F4F5F7"), (BgSurface, "#FFFFFF"), (BgHover, "#EEF1F5"), (BgSelected, "#DCE9FA"), (Line, "#D7DBE1"),
        (Text, "#1D2229"), (TextMuted, "#5B6470"), (Accent, "#0A5FC2"), (AccentInk, "#FFFFFF"),
        (StatusFail, "#B03A0A"), (StatusFailFill, "#FDE8DF"), (StatusReview, "#8A5C00"), (StatusReviewFill, "#FFF4D6"),
        (StatusPass, "#0B6E61"), (StatusPassFill, "#DDF3EF"), (StatusNa, "#5F6672"), (StatusStale, "#5B6470"),
        (Marked, "#1F5FAD"), (MarkedFill, "#E3EEFB"));

    private static readonly Dictionary<string, Rgb> DarkColours = Table(
        (BgPane, "#2B3038"), (BgSurface, "#343A44"), (BgHover, "#3D4450"), (BgSelected, "#284263"), (Line, "#4A5260"),
        (Text, "#E7EAEE"), (TextMuted, "#B8C0CA"), (Accent, "#82B8F7"), (AccentInk, "#0E1620"),
        (StatusFail, "#FFA07A"), (StatusFailFill, "#4A2A1E"), (StatusReview, "#F2C14E"), (StatusReviewFill, "#4A3F1E"),
        (StatusPass, "#5ED3C0"), (StatusPassFill, "#1C3E3A"), (StatusNa, "#B4BCC6"), (StatusStale, "#B8C0CA"),
        (Marked, "#9CC4F3"), (MarkedFill, "#22344D"));

    private static Dictionary<string, Rgb> Table(params (string Name, string Hex)[] rows) =>
        rows.ToDictionary(r => r.Name, r => Rgb.Parse(r.Hex), StringComparer.Ordinal);

    /// <summary>Every colour token's name, in the order of section 2.5.</summary>
    public static IReadOnlyList<string> Names { get; } = [.. LightColours.Keys];

    /// <summary>A theme's colour tokens, by name.</summary>
    public static IReadOnlyDictionary<string, Rgb> Colours(PanelTheme theme) => theme switch
    {
        PanelTheme.Light => LightColours,
        PanelTheme.Dark => DarkColours,
        _ => throw new ArgumentOutOfRangeException(nameof(theme)),
    };

    /// <summary>The contrast ratio of two colours, WCAG 2.2's (1 to 21).</summary>
    public static double Contrast(Rgb a, Rgb b)
    {
        var (hi, lo) = a.Luminance >= b.Luminance ? (a.Luminance, b.Luminance) : (b.Luminance, a.Luminance);
        return (hi + 0.05) / (lo + 0.05);
    }

    private static readonly string[] Backgrounds = [BgPane, BgSurface, BgHover, BgSelected];
    private static readonly string[] Fills = [StatusFailFill, StatusReviewFill, StatusPassFill, MarkedFill];

    /// <summary>Every text colour and each background the panel puts it on (WCAG 1.4.3: at least 4.5:1): text and
    /// muted text on the pane, a card, a hovered or selected row and every fill (a count chip, a banner); a link
    /// (accent) on the pane and a row in any state; a primary button's text on the accent; each status ink and the
    /// marked blue on the pane, a card, a hovered or selected row and its own fill (a group's heading, a chip); stale's
    /// grey on the stale banner (the review fill) too.</summary>
    public static IReadOnlyList<(string Text, IReadOnlyList<string> On)> TextOn { get; } =
    [
        (Text, [.. Backgrounds, .. Fills]),
        (TextMuted, [.. Backgrounds, .. Fills]),
        (Accent, Backgrounds),
        (AccentInk, [Accent]),
        (StatusFail, [.. Backgrounds, StatusFailFill]),
        (StatusReview, [.. Backgrounds, StatusReviewFill]),
        (StatusPass, [.. Backgrounds, StatusPassFill]),
        (StatusNa, Backgrounds),
        (StatusStale, [.. Backgrounds, StatusReviewFill]),
        (Marked, [.. Backgrounds, MarkedFill]),
    ];

    /// <summary>Every status colour and each background its glyph or bar sits on (WCAG 1.4.11: at least 3:1; each
    /// also passes 4.5:1 as text, <see cref="TextOn"/>), and the selected row's accent outline.</summary>
    public static IReadOnlyList<(string Mark, IReadOnlyList<string> On)> MarksOn { get; } =
    [
        (StatusFail, [.. Backgrounds, StatusFailFill]),
        (StatusReview, [.. Backgrounds, StatusReviewFill]),
        (StatusPass, [.. Backgrounds, StatusPassFill]),
        (StatusNa, Backgrounds),
        (StatusStale, [.. Backgrounds, StatusReviewFill]),
        (Marked, [.. Backgrounds, MarkedFill]),
        (Accent, [BgSelected]),
    ];

    /// <summary>The type tokens of section 2.5 (Segoe UI, Revit's own; the law's words in a serif, so they read as the
    /// law's). <c>type.overline</c>'s +4% tracking is not drawn: WPF's TextBlock has no letter spacing.</summary>
    public static IReadOnlyList<TypeToken> Type { get; } =
    [
        new("type.state", 15, true, Sans),
        new("type.title", 13, true, Sans),
        new("type.body", 12, false, Sans),
        new("type.caption", 11, false, Sans),
        new("type.overline", 10, true, Sans),
        new("type.quote", 12, false, "Georgia, Cambria, Times New Roman"),
        new("type.figure", 12, true, Sans, Tabular: true),
    ];

    private const string Sans = "Segoe UI";

    /// <summary>A type token by name.</summary>
    public static TypeToken TypeOf(string name) =>
        Type.FirstOrDefault(t => t.Name == name) ?? throw new ArgumentOutOfRangeException(nameof(name), name, "no such type token");
}
