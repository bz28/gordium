using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;
using S = System.Windows.Shapes;

namespace Gordium.Revit.Addin;

/// <summary>
/// The results panel's look in WPF (docs/revit/ui_design_pass.md section 2.5), built from Gordium.Revit.Reading's
/// tables so no colour is written twice: one ResourceDictionary of brushes per theme (PanelTokens), swapped when
/// Revit's theme changes; the type tokens as TextBlock styles; the status glyphs as Geometry resources (StatusLook);
/// and the restyled controls (PanelStyles.xaml). Every element names its colour by token with SetResourceReference,
/// so a swap recolours what is already on screen.
/// </summary>
internal static class PanelLook
{
    /// <summary>The key of the stale bar's hatch (status.stale in diagonal stripes).</summary>
    internal const string StaleHatch = "status.stale.hatch";

    /// <summary>A theme's brushes: one frozen SolidColorBrush per colour token, and the stale hatch.</summary>
    internal static W.ResourceDictionary Colours(PanelTheme theme)
    {
        var d = new W.ResourceDictionary();
        foreach (var (name, rgb) in PanelTokens.Colours(theme))
        {
            var b = new M.SolidColorBrush(M.Color.FromRgb(rgb.R, rgb.G, rgb.B));
            b.Freeze();
            d[name] = b;
        }
        var muted = PanelTokens.Colours(theme)[PanelTokens.StatusStale];
        var ink = M.Color.FromRgb(muted.R, muted.G, muted.B);
        var hatch = new M.LinearGradientBrush
        {
            MappingMode = M.BrushMappingMode.Absolute, StartPoint = new W.Point(0, 0), EndPoint = new W.Point(4, 4),
            SpreadMethod = M.GradientSpreadMethod.Repeat,
            GradientStops =
            {
                new M.GradientStop(ink, 0), new M.GradientStop(ink, 0.5),
                new M.GradientStop(M.Colors.Transparent, 0.5), new M.GradientStop(M.Colors.Transparent, 1),
            },
        };
        hatch.Freeze();
        d[StaleHatch] = hatch;
        return d;
    }

    /// <summary>The key of a status glyph's outline or mark geometry ("glyph.fails.outline").</summary>
    internal static string GlyphKey(PanelStatus s, bool outline) => $"glyph.{s.ToString().ToLowerInvariant()}.{(outline ? "outline" : "mark")}";

    /// <summary>What every theme shares: the type tokens as TextBlock styles and the status glyphs' geometries.</summary>
    internal static W.ResourceDictionary Shared()
    {
        var d = new W.ResourceDictionary();
        foreach (var t in PanelTokens.Type)
        {
            var style = new W.Style(typeof(C.TextBlock));
            style.Setters.Add(new W.Setter(C.TextBlock.FontSizeProperty, t.Size));
            style.Setters.Add(new W.Setter(C.TextBlock.FontWeightProperty, t.SemiBold ? W.FontWeights.SemiBold : W.FontWeights.Normal));
            style.Setters.Add(new W.Setter(C.TextBlock.FontFamilyProperty, new M.FontFamily(t.Family)));
            if (t.Tabular)
                style.Setters.Add(new W.Setter(W.Documents.Typography.NumeralAlignmentProperty, W.FontNumeralAlignment.Tabular));
            style.Seal();
            d[t.Name] = style;
        }
        foreach (var s in StatusLook.All)
        {
            var g = StatusLook.GlyphOf(s);
            d[GlyphKey(s, outline: true)] = Frozen(M.Geometry.Parse(g.Outline));
            d[GlyphKey(s, outline: false)] = Frozen(M.Geometry.Parse(g.Mark));
        }
        return d;
    }

    private static M.Geometry Frozen(M.Geometry g)
    {
        g.Freeze();
        return g;
    }

    /// <summary>The restyled controls (PanelStyles.xaml, embedded), read once.</summary>
    internal static W.ResourceDictionary Controls()
    {
        using var stream = typeof(PanelLook).Assembly.GetManifestResourceStream(StylesResource)
                           ?? throw new InvalidOperationException($"the add-in has no {StylesResource} built in");
        return (W.ResourceDictionary)W.Markup.XamlReader.Load(stream);
    }

    internal const string StylesResource = "Gordium.Revit.Addin.PanelStyles.xaml";

    /// <summary>Gives <paramref name="root"/> the panel's look in <paramref name="theme"/>: the theme's brushes first
    /// (replaced on every later call), then what every theme shares and the controls.</summary>
    internal static void Apply(W.FrameworkElement root, PanelTheme theme)
    {
        var merged = root.Resources.MergedDictionaries;
        if (merged.Count == 0)
        {
            merged.Add(Colours(theme));
            merged.Add(Shared());
            merged.Add(Controls());
        }
        else
            merged[0] = Colours(theme);
    }

    /// <summary>A status's glyph, <paramref name="size"/> pixels square: its outline in the status colour (filled
    /// when it has a fill), its mark inside; its word as its tooltip and the name a screen reader says.</summary>
    internal static W.FrameworkElement Glyph(PanelStatus s, double size = 16)
    {
        var look = StatusLook.GlyphOf(s);
        var colour = StatusLook.Colour(s);
        var outline = new S.Path { StrokeThickness = 1.4, StrokeLineJoin = M.PenLineJoin.Round };
        outline.SetResourceReference(S.Path.DataProperty, GlyphKey(s, outline: true));
        outline.SetResourceReference(S.Shape.StrokeProperty, colour);
        if (look.Fill is { } fill)
            outline.SetResourceReference(S.Shape.FillProperty, fill);
        var mark = new S.Path
        {
            StrokeThickness = 1.5, StrokeStartLineCap = M.PenLineCap.Round, StrokeEndLineCap = M.PenLineCap.Round,
            StrokeLineJoin = M.PenLineJoin.Round,
        };
        mark.SetResourceReference(S.Path.DataProperty, GlyphKey(s, outline: false));
        mark.SetResourceReference(S.Shape.StrokeProperty, colour);
        var canvas = new C.Canvas { Width = 16, Height = 16 };
        canvas.Children.Add(outline);
        canvas.Children.Add(mark);
        var box = new C.Viewbox
        {
            Width = size, Height = size, Child = canvas, ToolTip = StatusLook.Word(s), VerticalAlignment = W.VerticalAlignment.Center,
        };
        W.Automation.AutomationProperties.SetName(box, StatusLook.Word(s));
        return box;
    }

    /// <summary>Revit's theme as the panel's (UIThemeManager.CurrentTheme, Revit 2014+): dark only when Revit says dark.</summary>
    internal static PanelTheme OfRevit(Autodesk.Revit.UI.UITheme theme) =>
        theme == Autodesk.Revit.UI.UITheme.Dark ? PanelTheme.Dark : PanelTheme.Light;
}
