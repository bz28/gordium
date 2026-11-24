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

    /// <summary>The key of a type token's font family ("type.body.family") and of its size ("type.body.size").</summary>
    internal static string FamilyKey(string token) => token + ".family";

    internal static string SizeKey(string token) => token + ".size";

    /// <summary>What every theme shares: the type tokens as TextBlock styles (and each one's family and size) and the status glyphs' geometries.</summary>
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
            // the token's family and size on their own, for the controls' styles (PanelStyles.xaml)
            d[FamilyKey(t.Name)] = new M.FontFamily(t.Family);
            d[SizeKey(t.Name)] = t.Size;
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

    /// <summary>A small line icon (UI polish change 46), <paramref name="size"/> pixels square, in the muted text
    /// colour (never a status colour; the review triangle is the status glyph itself).</summary>
    internal static W.FrameworkElement Icon(PaneIcon icon, double size = 16)
    {
        if (icon == PaneIcon.Review)
            return Glyph(PanelStatus.Review, size);
        var data = icon switch
        {
            PaneIcon.Page => "M 4,2 L 10,2 L 13,5 L 13,14 L 4,14 Z M 10,2 L 10,5 L 13,5",
            PaneIcon.Pencil => "M 3,13 L 4,10 L 11,3 L 13,5 L 6,12 Z M 9.5,4.5 L 11.5,6.5",
            PaneIcon.Pin => "M 8,14 C 8,14 3.5,9.5 3.5,6.5 A 4.5,4.5 0 0 1 12.5,6.5 C 12.5,9.5 8,14 8,14 Z M 9.5,6.5 A 1.5,1.5 0 1 1 6.5,6.5 A 1.5,1.5 0 1 1 9.5,6.5",
            PaneIcon.Form => "M 3,3 L 13,3 L 13,13 L 3,13 Z M 5,6 L 11,6 M 5,8.5 L 11,8.5 M 5,11 L 9,11",
            PaneIcon.Map => "M 2,4 L 6,2.5 L 10,4 L 14,2.5 L 14,12 L 10,13.5 L 6,12 L 2,13.5 Z M 6,2.5 L 6,12 M 10,4 L 10,13.5",
            PaneIcon.Ruler => "M 2,10 L 10,2 L 14,6 L 6,14 Z M 5,9 L 6.5,10.5 M 7,7 L 8.5,8.5 M 9,5 L 10.5,6.5",
            PaneIcon.Scales => "M 8,2.5 L 8,13.5 M 5,13.5 L 11,13.5 M 3,5 L 13,5 M 3,5 L 1.5,9 L 4.5,9 Z M 13,5 L 11.5,9 L 14.5,9 Z",
            PaneIcon.Question => "M 14.5,8 A 6.5,6.5 0 1 1 1.5,8 A 6.5,6.5 0 1 1 14.5,8 M 6,6 A 2,2 0 1 1 8,8 L 8,9.5 M 8,11.5 L 8,12",
            _ => "M 3,3 L 13,13",
        };
        var path = new S.Path
        {
            Data = Frozen(M.Geometry.Parse(data)), StrokeThickness = 1.2, StrokeLineJoin = M.PenLineJoin.Round,
            StrokeStartLineCap = M.PenLineCap.Round, StrokeEndLineCap = M.PenLineCap.Round, Stretch = M.Stretch.None,
        };
        path.SetResourceReference(S.Shape.StrokeProperty, PanelTokens.TextMuted);
        var canvas = new C.Canvas { Width = 16, Height = 16 };
        canvas.Children.Add(path);
        return new C.Viewbox { Width = size, Height = size, Child = canvas, IsHitTestVisible = false };
    }
}
