using Xunit;
using Xunit.Abstractions;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The results panel's look (PanelTokens, StatusLook; design pass section 2.5): every text readable on every
/// background it sits on in both of Revit's themes (WCAG 2.2: 4.5:1), every status mark at least 3:1, and every
/// status told apart by its shape and its word, never by colour alone; green only for what complies, never stale.</summary>
public sealed class PanelThemeTests(ITestOutputHelper output)
{
    public static TheoryData<PanelTheme> Themes => new() { PanelTheme.Light, PanelTheme.Dark };

    [Fact]
    public void Contrast_is_wcag_s_own()
    {
        // WCAG's anchors: black on white is 21:1, a colour on itself 1:1; #767676 on white is the 4.5:1 grey
        Assert.Equal(21.0, PanelTokens.Contrast(Rgb.Parse("#000000"), Rgb.Parse("#FFFFFF")), 6);
        Assert.Equal(1.0, PanelTokens.Contrast(Rgb.Parse("#5B6470"), Rgb.Parse("#5B6470")), 6);
        Assert.Equal(4.54, PanelTokens.Contrast(Rgb.Parse("#767676"), Rgb.Parse("#FFFFFF")), 2);
        Assert.Equal(PanelTokens.Contrast(Rgb.Parse("#0B65CF"), Rgb.Parse("#DCE9FA")),
                     PanelTokens.Contrast(Rgb.Parse("#DCE9FA"), Rgb.Parse("#0B65CF")), 12);
    }

    [Fact]
    public void Both_themes_define_every_token_and_parse_back()
    {
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
        {
            var c = PanelTokens.Colours(theme);
            Assert.Equal(PanelTokens.Names.OrderBy(n => n, StringComparer.Ordinal), c.Keys.OrderBy(n => n, StringComparer.Ordinal));
            foreach (var (name, rgb) in c)
                Assert.Equal(rgb, Rgb.Parse(rgb.ToString()));
        }
        // section 2.5's tokens all there
        foreach (var name in new[] { "bg.pane", "bg.surface", "bg.hover", "bg.selected", "line", "text", "text.muted", "accent",
                                     "status.fail", "status.review", "status.pass", "status.na", "status.stale" })
            Assert.Contains(name, PanelTokens.Names);
        Assert.Throws<FormatException>(() => Rgb.Parse("1D2229"));
    }

    [Theory]
    [MemberData(nameof(Themes))]
    public void Every_text_is_at_least_4_5_to_1_on_every_background_it_sits_on(PanelTheme theme)
    {
        var c = PanelTokens.Colours(theme);
        var failed = new List<string>();
        foreach (var (text, on) in PanelTokens.TextOn)
            foreach (var bg in on)
            {
                var ratio = PanelTokens.Contrast(c[text], c[bg]);
                output.WriteLine($"{theme} {text} {c[text]} on {bg} {c[bg]}: {ratio:0.00}:1");
                if (ratio < 4.5)
                    failed.Add($"{text} on {bg} {ratio:0.00}");
            }
        Assert.Empty(failed);
        // text.muted is tested, on every background
        Assert.Contains(PanelTokens.TextOn, p => p.Text == PanelTokens.TextMuted && p.On.Contains(PanelTokens.BgSelected));
    }

    [Theory]
    [MemberData(nameof(Themes))]
    public void Every_status_mark_is_at_least_3_to_1_on_every_background_it_sits_on(PanelTheme theme)
    {
        var c = PanelTokens.Colours(theme);
        var failed = new List<string>();
        foreach (var (mark, on) in PanelTokens.MarksOn)
            foreach (var bg in on)
            {
                var ratio = PanelTokens.Contrast(c[mark], c[bg]);
                output.WriteLine($"{theme} {mark} {c[mark]} on {bg} {c[bg]}: {ratio:0.00}:1");
                if (ratio < 3.0)
                    failed.Add($"{mark} on {bg} {ratio:0.00}");
            }
        Assert.Empty(failed);
        // every status's colour is one of the marks tested, on its chip's background too
        foreach (var s in StatusLook.All)
            Assert.Contains(PanelTokens.MarksOn, p => p.Mark == StatusLook.Colour(s) && p.On.Contains(PanelTokens.BgPane)
                                                      && p.On.Contains(StatusLook.ChipBackground(s)));
    }

    [Fact]
    public void Every_status_has_its_own_glyph_and_its_own_word()
    {
        var all = StatusLook.All;
        Assert.Equal(5, all.Count);
        Assert.Equal(all.Count, all.Select(StatusLook.Word).Distinct(StringComparer.OrdinalIgnoreCase).Count());
        // a glyph is its outline and its mark together: no two alike, and none empty
        Assert.Equal(all.Count, all.Select(s => StatusLook.GlyphOf(s).Outline + "|" + StatusLook.GlyphOf(s).Mark).Distinct().Count());
        // and no two the same mark inside (the shape inside tells them apart even where outlines are alike)
        Assert.Equal(all.Count, all.Select(s => StatusLook.GlyphOf(s).Mark).Distinct().Count());
        foreach (var s in all)
        {
            Assert.False(string.IsNullOrWhiteSpace(StatusLook.GlyphOf(s).Outline));
            Assert.False(string.IsNullOrWhiteSpace(StatusLook.GlyphOf(s).Mark));
            Assert.False(string.IsNullOrWhiteSpace(StatusLook.Word(s)));
        }
        // the three verdict hues each their own outline: octagon, triangle, circle
        Assert.Equal(3, new[] { PanelStatus.Fails, PanelStatus.Review, PanelStatus.Complies }.Select(s => StatusLook.GlyphOf(s).Outline).Distinct().Count());
    }

    [Theory]
    [MemberData(nameof(Themes))]
    public void Every_status_has_its_own_colour_and_stale_is_never_green(PanelTheme theme)
    {
        var c = PanelTokens.Colours(theme);
        // the three verdict hues and not applicable's grey each their own; stale is muted text's grey (told from not
        // applicable by its clock), and the pass green is no other status's colour, nor any text's
        var verdicts = new[] { PanelStatus.Fails, PanelStatus.Review, PanelStatus.Complies, PanelStatus.NotApplicable }
            .Select(s => c[StatusLook.Colour(s)]).ToList();
        Assert.Equal(verdicts.Count, verdicts.Distinct().Count());
        Assert.Equal(c[PanelTokens.TextMuted], c[StatusLook.Colour(PanelStatus.Stale)]);
        foreach (var s in StatusLook.All.Where(s => s != PanelStatus.Complies))
        {
            Assert.NotEqual(PanelTokens.StatusPass, StatusLook.Colour(s));
            Assert.NotEqual(c[PanelTokens.StatusPass], c[StatusLook.Colour(s)]);
            Assert.NotEqual(PanelTokens.StatusPassFill, StatusLook.GlyphOf(s).Fill);
            Assert.NotEqual(PanelTokens.StatusPassFill, StatusLook.ChipBackground(s));
        }
        foreach (var other in new[] { PanelTokens.Text, PanelTokens.TextMuted, PanelTokens.Accent, PanelTokens.Line, PanelTokens.Marked, PanelTokens.MarkedFill })
            Assert.NotEqual(c[PanelTokens.StatusPass], c[other]);
        Assert.Null(StatusLook.GlyphOf(PanelStatus.Stale).Fill);                   // a stale glyph is drawn open, never pass-filled
    }

    [Fact]
    public void Green_only_for_complies_and_never_once_stale()
    {
        foreach (var tone in Enum.GetValues<Tone>())
        {
            Assert.Equal(PanelStatus.Stale, StatusLook.Of(tone, stale: true));
            Assert.Equal(tone == Tone.Complies, StatusLook.Of(tone, stale: false) == PanelStatus.Complies);
        }
        Assert.Equal(PanelStatus.Fails, StatusLook.Of(Tone.Fails, false));
        Assert.Equal(PanelStatus.Review, StatusLook.Of(Tone.Review, false));
        Assert.Equal(PanelStatus.NotApplicable, StatusLook.Of(Tone.Neutral, false));
    }

    [Fact]
    public void Type_tokens_are_section_2_5_s()
    {
        Assert.Equal(15, PanelTokens.TypeOf("type.state").Size);
        Assert.True(PanelTokens.TypeOf("type.state").SemiBold);
        Assert.Equal(12, PanelTokens.TypeOf("type.body").Size);
        Assert.False(PanelTokens.TypeOf("type.body").SemiBold);
        Assert.Equal(10, PanelTokens.TypeOf("type.overline").Size);
        Assert.True(PanelTokens.TypeOf("type.figure").Tabular);
        Assert.StartsWith("Georgia", PanelTokens.TypeOf("type.quote").Family, StringComparison.Ordinal);
        Assert.All(PanelTokens.Type.Where(t => t.Name != "type.quote"), t => Assert.Equal("Segoe UI", t.Family));
        Assert.Throws<ArgumentOutOfRangeException>(() => PanelTokens.TypeOf("type.none"));
    }

    [Fact]
    public void The_results_view_has_no_fixed_colour()
    {
        // every colour in the panel comes from the token dictionaries (so it follows Revit's theme): none written
        // into the view itself
        foreach (var file in new[] { "ResultsView.cs", "ResultsList.cs", "DetailView.cs", "CauseCardsView.cs" })   // the panel, its list's entries (PR 3), the detail (PR 4), the cause cards (PR 6)
        {
            var view = File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file));
            foreach (var fixedColour in new[] { "Color.FromRgb", "Color.FromArgb", "Brushes.", "SystemColors.", "ColorOf", "Opacity =" })
                Assert.DoesNotContain(fixedColour, view, StringComparison.Ordinal);
        }
    }

    private static string Styles() =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", "PanelStyles.xaml"));

    /// <summary>Every value PanelStyles.xaml gives <paramref name="properties"/>, as an attribute
    /// (<c>Background="..."</c>) or a Setter (<c>Property="Background" Value="..."</c>), with its line.</summary>
    private static List<(string Property, string Value, int Line)> Values(string xaml, string properties)
    {
        var found = new List<(string, string, int)>();
        int LineOf(int at) => xaml.AsSpan(0, at).Count('\n') + 1;
        foreach (System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(xaml, $@"\b({properties})=""([^""]*)"""))
            found.Add((m.Groups[1].Value, m.Groups[2].Value, LineOf(m.Index)));
        foreach (System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(
                     xaml, $@"Property=""({properties})""\s+Value=""([^""]*)"""))
            found.Add((m.Groups[1].Value, m.Groups[2].Value, LineOf(m.Index)));
        return found;
    }

    [Fact]
    public void The_control_styles_have_no_fixed_colour()
    {
        // every colour of the restyled controls is a token (DynamicResource, so it follows Revit's theme), the
        // control's own (TemplateBinding), or Transparent: never a #hex or a named colour
        var xaml = Styles();
        var colours = Values(xaml, "Background|Foreground|BorderBrush|Stroke|Fill");
        Assert.NotEmpty(colours);
        var fixedOnes = colours.Where(c => !(c.Value.StartsWith("{DynamicResource ", StringComparison.Ordinal)
                                             || c.Value.StartsWith("{TemplateBinding ", StringComparison.Ordinal)
                                             || c.Value == "Transparent"))
                               .Select(c => $"line {c.Line}: {c.Property}=\"{c.Value}\"").ToList();
        Assert.Empty(fixedOnes);
        Assert.DoesNotMatch(@"=""#[0-9A-Fa-f]{3,8}""", xaml);
    }

    [Fact]
    public void The_control_styles_take_their_fonts_from_the_type_tokens()
    {
        // no font family or size written in the styles: each is a type token's, published by PanelLook.Shared
        var xaml = Styles();
        var fonts = Values(xaml, "FontFamily|FontSize");
        Assert.NotEmpty(fonts);
        var fromTokens = PanelTokens.Type.SelectMany(t => new[] { t.Name + ".family", t.Name + ".size" }).ToHashSet(StringComparer.Ordinal);
        var literal = fonts.Where(f => !(f.Value.StartsWith("{DynamicResource ", StringComparison.Ordinal)
                                         && fromTokens.Contains(f.Value["{DynamicResource ".Length..^1].Trim())))
                           .Select(f => $"line {f.Line}: {f.Property}=\"{f.Value}\"").ToList();
        Assert.Empty(literal);
        // and every resource the styles name is one PanelLook publishes: a colour token or a type token's font
        var published = PanelTokens.Names.Concat(fromTokens).ToHashSet(StringComparer.Ordinal);
        var unknown = System.Text.RegularExpressions.Regex.Matches(xaml, @"\{DynamicResource ([^}\s]+)\s*\}")
                           .Select(m => m.Groups[1].Value).Where(k => !published.Contains(k)).Distinct().ToList();
        Assert.Empty(unknown);
    }

    [Fact]
    public void The_add_in_never_names_the_pass_green_itself()
    {
        // the pass green is the worker's "complies" only: reached through StatusLook (a Complies tone, not stale),
        // never named by the add-in for anything else (a marked exit, a finished checklist)
        var addin = Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin");
        foreach (var file in Directory.EnumerateFiles(addin, "*.*", SearchOption.AllDirectories)
                                      .Where(f => f.EndsWith(".cs", StringComparison.Ordinal) || f.EndsWith(".xaml", StringComparison.Ordinal))
                                      .Where(f => !f.Contains(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar, StringComparison.Ordinal)
                                               && !f.Contains(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar, StringComparison.Ordinal)))
        {
            var text = File.ReadAllText(file);
            foreach (var green in new[] { "StatusPass", "status.pass", "PanelStatus.Complies" })
                Assert.False(text.Contains(green, StringComparison.Ordinal), $"{Path.GetFileName(file)} names {green}");
        }
    }
}
