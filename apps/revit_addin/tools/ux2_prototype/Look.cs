using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Gordium.Revit.Ux2Prototype;

/// <summary>The proposal's visual system: colour tokens for Revit's light and dark themes, a four-step type scale, a
/// 4-px spacing grid and one icon per status. The colours are the add-in's own (PanelTheme.cs, sampled against Revit
/// 2027's dark theme in Ben's screenshot: pane #2B3038, surface #343A44) plus three: a sunken fill for the view
/// switch, a faint text for greyed "not checked yet" rows, and an info blue fill.</summary>
internal static class T
{
    public static bool Dark;

    static SolidColorBrush B(string hex) => (SolidColorBrush)new BrushConverter().ConvertFromString(hex)!;

    public static Brush Pane = null!, Surface = null!, Sunken = null!, Hover = null!, Line = null!, Text = null!, Muted = null!, Faint = null!,
        Accent = null!, AccentInk = null!, AccentFill = null!, Fail = null!, FailFill = null!, Review = null!, ReviewFill = null!, ReviewInk = null!,
        Pass = null!, PassFill = null!, Na = null!, Chrome = null!, ChromeText = null!, CanvasBg = null!;

    public static void Set(bool dark)
    {
        Dark = dark;
        if (!dark)
        {
            Pane = B("#F4F5F7"); Surface = B("#FFFFFF"); Sunken = B("#E6E9EE"); Hover = B("#EEF1F5"); Line = B("#D7DBE1");
            Text = B("#1D2229"); Muted = B("#5B6470"); Faint = B("#8A929D");
            Accent = B("#0A5FC2"); AccentInk = B("#FFFFFF"); AccentFill = B("#E3EEFB");
            Fail = B("#B03A0A"); FailFill = B("#FDE8DF"); Review = B("#8A5C00"); ReviewFill = B("#FFF4D6"); ReviewInk = B("#FFFFFF");
            Pass = B("#0B6E61"); PassFill = B("#DDF3EF"); Na = B("#5F6672");
            Chrome = B("#E1E2E3"); ChromeText = B("#1D2229"); CanvasBg = B("#FFFFFF");
        }
        else
        {
            Pane = B("#2B3038"); Surface = B("#343A44"); Sunken = B("#232830"); Hover = B("#3D4450"); Line = B("#4A5260");
            Text = B("#E7EAEE"); Muted = B("#B8C0CA"); Faint = B("#8892A0");
            Accent = B("#82B8F7"); AccentInk = B("#0E1620"); AccentFill = B("#22344D");
            Fail = B("#FFA07A"); FailFill = B("#4A2A1E"); Review = B("#F2C14E"); ReviewFill = B("#4A3F1E"); ReviewInk = B("#2B2100");
            Pass = B("#5ED3C0"); PassFill = B("#1C3E3A"); Na = B("#B4BCC6");
            Chrome = B("#3B4453"); ChromeText = B("#E1E2E3"); CanvasBg = B("#222933");
        }
    }

    // ---- type scale: 4 sizes (Segoe UI, Revit's own UI font) -------------------------------------------------
    public const double Title = 15, Heading = 12.5, Body = 12, Small = 11;

    public static TextBlock Tx(string s, double size = Body, bool semi = false, Brush? fg = null, double top = 0, double bottom = 0,
                               bool wrap = true, bool italic = false)
    {
        var t = new TextBlock
        {
            Text = s, FontSize = size, Foreground = fg ?? Text, TextWrapping = wrap ? TextWrapping.Wrap : TextWrapping.NoWrap,
            Margin = new Thickness(0, top, 0, bottom), FontFamily = new FontFamily("Segoe UI"),
            FontWeight = semi ? FontWeights.SemiBold : FontWeights.Normal, TextTrimming = wrap ? TextTrimming.None : TextTrimming.CharacterEllipsis,
            LineHeight = size * 1.36, LineStackingStrategy = LineStackingStrategy.BlockLineHeight,
        };
        if (italic)
            t.FontStyle = FontStyles.Italic;
        return t;
    }

    public static TextBlock Overline(string s, double top = 16, Brush? fg = null) =>
        Tx(s.ToUpperInvariant(), 10.5, semi: true, fg: fg ?? Muted, top: top, bottom: 6);

    /// <summary>Text with a **bold** lead.</summary>
    public static TextBlock Lead(string lead, string rest, double size = Body, double top = 0, Brush? fg = null)
    {
        var t = Tx("", size, top: top, fg: fg);
        t.Inlines.Add(new System.Windows.Documents.Run(lead) { FontWeight = FontWeights.SemiBold });
        t.Inlines.Add(new System.Windows.Documents.Run(rest));
        return t;
    }

    // ---- layout -----------------------------------------------------------------------------------------
    public static StackPanel V(params UIElement?[] kids)
    {
        var p = new StackPanel();
        foreach (var k in kids)
            if (k is not null)
                p.Children.Add(k);
        return p;
    }

    public static DockPanel Row(UIElement left, UIElement? right = null, double top = 0)
    {
        var d = new DockPanel { LastChildFill = true, Margin = new Thickness(0, top, 0, 0) };
        if (right is not null)
        {
            DockPanel.SetDock(right, Dock.Right);
            d.Children.Add(right);
        }
        d.Children.Add(left);
        return d;
    }

    public static WrapPanel H(double gap, params UIElement?[] kids)
    {
        var p = new WrapPanel { Orientation = Orientation.Horizontal };
        foreach (var k in kids)
        {
            if (k is null)
                continue;
            if (k is FrameworkElement f && p.Children.Count > 0)
                f.Margin = new Thickness(gap, f.Margin.Top, f.Margin.Right, f.Margin.Bottom);
            p.Children.Add(k);
        }
        return p;
    }

    public static T2 Top<T2>(T2 e, double top) where T2 : FrameworkElement
    {
        e.Margin = new Thickness(e.Margin.Left, top, e.Margin.Right, e.Margin.Bottom);
        return e;
    }

    public static Border Card(UIElement child, Brush? edge = null, Brush? fill = null, double top = 8, double pad = 12)
    {
        var inner = new Border { Child = child, Padding = new Thickness(pad) };
        var b = new Border
        {
            Background = fill ?? Surface, BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6),
            Margin = new Thickness(0, top, 0, 0), Child = inner,
        };
        if (edge is not null)
        {
            var g = new Grid();
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(3) });
            g.ColumnDefinitions.Add(new ColumnDefinition());
            b.Child = null;
            var bar = new Border { Background = edge, CornerRadius = new CornerRadius(5, 0, 0, 5) };
            g.Children.Add(bar);
            Grid.SetColumn(inner, 1);
            g.Children.Add(inner);
            b.Child = g;
        }
        return b;
    }

    public static Border Callout(UIElement child, Brush fill, Brush edge, double top = 8) => new()
    {
        Background = fill, BorderBrush = edge, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6),
        Padding = new Thickness(10, 8, 10, 8), Margin = new Thickness(0, top, 0, 0), Child = child,
    };

    public static Border Divider(double top = 12, double bottom = 0) =>
        new() { Height = 1, Background = Line, Margin = new Thickness(0, top, 0, bottom) };

    // ---- controls (drawn: the prototype has no behaviour) ----------------------------------------------------
    public static Border Btn(string s, bool primary = false, bool disabled = false, double top = 0)
    {
        var fg = disabled ? Faint : primary ? AccentInk : Text;
        return new Border
        {
            Background = disabled ? Sunken : primary ? Accent : Surface, BorderBrush = primary && !disabled ? Accent : Line,
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(4), Padding = new Thickness(12, 4, 12, 5),
            Margin = new Thickness(0, top, 0, 0), HorizontalAlignment = HorizontalAlignment.Left,
            Child = Tx(s, Body, semi: primary, fg: fg, wrap: false),
        };
    }

    public static TextBlock Link(string s, double size = Body, double top = 0)
    {
        var t = Tx(s, size, fg: Accent, top: top, wrap: false);
        t.TextDecorations = null;
        t.VerticalAlignment = VerticalAlignment.Center;
        return t;
    }

    public static Border Dropdown(string? value, string placeholder, double top = 4)
    {
        var g = Row(Tx(value ?? placeholder, Body, fg: value is null ? Muted : Text, wrap: false), Chevron(true));
        return new Border
        {
            Background = Surface, BorderBrush = Line, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(4),
            Padding = new Thickness(8, 4, 8, 5), Margin = new Thickness(0, top, 0, 0), Child = g,
        };
    }

    /// <summary>Two or three options side by side: the view switch, Yes / No, Survey / Tax map.</summary>
    public static Border Segmented(string[] labels, int selected, double top = 0, bool stretch = false)
    {
        var g = new Grid();
        for (var n = 0; n < labels.Length; n++)
        {
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = stretch ? new GridLength(1, GridUnitType.Star) : GridLength.Auto });
            var on = n == selected;
            var cell = new Border
            {
                Background = on ? Surface : Brushes.Transparent, CornerRadius = new CornerRadius(4), Padding = new Thickness(12, 3, 12, 4),
                BorderBrush = on ? Line : Brushes.Transparent, BorderThickness = new Thickness(on ? 1 : 0), Margin = new Thickness(1),
                Child = new TextBlock
                {
                    Text = labels[n], FontSize = Body, FontWeight = on ? FontWeights.SemiBold : FontWeights.Normal,
                    Foreground = on ? Text : Muted, HorizontalAlignment = HorizontalAlignment.Center, FontFamily = new FontFamily("Segoe UI"),
                },
            };
            Grid.SetColumn(cell, n);
            g.Children.Add(cell);
        }
        return new Border
        {
            Background = Sunken, CornerRadius = new CornerRadius(5), Padding = new Thickness(1), Child = g,
            Margin = new Thickness(0, top, 0, 0), HorizontalAlignment = stretch ? HorizontalAlignment.Stretch : HorizontalAlignment.Left,
        };
    }

    public static Border Pill(string s, Brush fg, Brush fill) => new()
    {
        Background = fill, CornerRadius = new CornerRadius(9), Padding = new Thickness(7, 1, 7, 2),
        Child = Tx(s, Small, semi: true, fg: fg, wrap: false), VerticalAlignment = VerticalAlignment.Center,
    };

    public static Border Tick(bool on) => new()
    {
        Width = 13, Height = 13, BorderBrush = on ? Accent : Muted, BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(2),
        Background = on ? Accent : Surface, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 6, 0),
    };

    /// <summary>A thin stacked bar of the checker's counts (fails, needs review, not checked yet, complies).</summary>
    public static Grid CountBar(int fail, int review, int notyet, int pass, double top = 8)
    {
        var g = new Grid { Height = 6, Margin = new Thickness(0, top, 0, 0) };
        var parts = new (int n, Brush b)[] { (fail, Fail), (review, Review), (notyet, Faint), (pass, Pass) };
        foreach (var (n, b) in parts)
        {
            if (n == 0)
                continue;
            g.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(Math.Max(n, 1.5), GridUnitType.Star) });
            var r = new Border { Background = b, Margin = new Thickness(0, 0, 2, 0), CornerRadius = new CornerRadius(1) };
            Grid.SetColumn(r, g.ColumnDefinitions.Count - 1);
            g.Children.Add(r);
        }
        return g;
    }

    // ---- icons: one per status, never colour alone ---------------------------------------------------------
    public static FrameworkElement Icon(string kind, double size = 14)
    {
        var c = new Canvas { Width = 16, Height = 16 };
        void Add(Shape s) => c.Children.Add(s);
        Path P(string data, Brush? stroke, Brush? fill, double w = 1.6) => new()
        {
            Data = Geometry.Parse(data), Stroke = stroke, Fill = fill, StrokeThickness = w,
            StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round,
        };
        switch (kind)
        {
            case "fail":
                Add(new Ellipse { Width = 15, Height = 15, Fill = Fail });
                Add(P("M5,5 L10.5,10.5 M10.5,5 L5,10.5", Dark ? Sunken : Brushes.White, null, 1.8));
                break;
            case "review":
                Add(P("M8,1.2 L15.2,14.4 L0.8,14.4 Z", null, Review, 0));
                Add(P("M8,5.4 L8,9.6", ReviewInk, null, 1.8));
                Add(new Ellipse { Width = 2.2, Height = 2.2, Fill = ReviewInk, Margin = new Thickness(6.9, 11, 0, 0) });
                break;
            case "pass":
                Add(new Ellipse { Width = 15, Height = 15, Fill = Pass });
                Add(P("M4.3,7.8 L6.8,10.3 L11.2,5.3", Dark ? Sunken : Brushes.White, null, 1.8));
                break;
            case "notyet":
                Add(new Ellipse { Width = 14, Height = 14, Stroke = Faint, StrokeThickness = 1.4, StrokeDashArray = new DoubleCollection { 1.6, 1.4 }, Margin = new Thickness(0.5) });
                break;
            case "na":
                Add(new Ellipse { Width = 14, Height = 14, Stroke = Na, StrokeThickness = 1.3, Margin = new Thickness(0.5) });
                Add(P("M4.5,7.5 L10.5,7.5", Na, null, 1.5));
                break;
            case "stale":
                Add(new Ellipse { Width = 14, Height = 14, Stroke = Muted, StrokeThickness = 1.4, Margin = new Thickness(0.5) });
                Add(P("M7.5,4 L7.5,7.8 L10.2,9.4", Muted, null, 1.4));
                break;
            case "info":
                Add(new Ellipse { Width = 14, Height = 14, Stroke = Accent, StrokeThickness = 1.3, Margin = new Thickness(0.5) });
                Add(P("M7.5,7 L7.5,11", Accent, null, 1.6));
                Add(new Ellipse { Width = 2, Height = 2, Fill = Accent, Margin = new Thickness(6.5, 3.8, 0, 0) });
                break;
            case "facts":
                Add(P("M3,2.5 L11,2.5 L13,4.5 L13,14 L3,14 Z", Muted, null, 1.3));
                Add(P("M5.5,7 L10.5,7 M5.5,9.5 L10.5,9.5 M5.5,12 L8.5,12", Muted, null, 1.2));
                break;
            case "drawing":
                Add(P("M2,13.5 L5,13.5 L13.5,5 L10.5,2 L2,10.5 Z", Muted, null, 1.3));
                Add(P("M9,3.5 L12,6.5", Muted, null, 1.2));
                break;
            case "survey":
                Add(P("M1.5,4 L5.5,2 L10.5,4 L14.5,2 L14.5,12 L10.5,14 L5.5,12 L1.5,14 Z M5.5,2 L5.5,12 M10.5,4 L10.5,14", Muted, null, 1.2));
                break;
            case "byhand":
                Add(P("M1.5,10 L10,1.5 L14.5,6 L6,14.5 Z", Muted, null, 1.3));
                Add(P("M4.5,8.5 L6,10 M6.5,6.5 L8.5,8.5 M8.5,4.5 L10,6", Muted, null, 1.1));
                break;
            case "judgment":
                Add(P("M8,2 L8,14 M3,14 L13,14 M2.5,4 L13.5,4 M2.5,4 L0.8,9 L4.2,9 Z M13.5,4 L11.8,9 L15.2,9 Z", Muted, null, 1.2));
                break;
            case "question":
                Add(new Ellipse { Width = 14, Height = 14, Stroke = Muted, StrokeThickness = 1.3, Margin = new Thickness(0.5) });
                Add(P("M5.6,6 C5.6,3.6 10.2,3.6 10.2,6.2 C10.2,7.8 7.9,8 7.9,9.8", Muted, null, 1.4));
                Add(new Ellipse { Width = 1.9, Height = 1.9, Fill = Muted, Margin = new Thickness(6.95, 11.2, 0, 0) });
                break;
            case "doc":
                Add(P("M3.5,1.5 L10,1.5 L13,4.5 L13,14.5 L3.5,14.5 Z M10,1.5 L10,4.5 L13,4.5", Muted, null, 1.2));
                break;
            case "pin":
                Add(P("M8,14.5 C8,14.5 3,9.2 3,6.2 A5,5 0 0 1 13,6.2 C13,9.2 8,14.5 8,14.5 Z", Muted, null, 1.3));
                Add(new Ellipse { Width = 3.4, Height = 3.4, Stroke = Muted, StrokeThickness = 1.2, Margin = new Thickness(6.3, 4.5, 0, 0) });
                break;
            case "check":
                Add(P("M3.5,8.2 L6.6,11.2 L12.5,4.8", Pass, null, 1.8));
                break;
            case "spinner":
                Add(new Ellipse { Width = 14, Height = 14, Stroke = Line, StrokeThickness = 2, Margin = new Thickness(0.5) });
                Add(P("M7.5,0.5 A7,7 0 0 1 14.5,7.5", Accent, null, 2));
                break;
        }
        var vb = new Viewbox { Width = size, Height = size, Child = c, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 1, 0, 0) };
        return vb;
    }

    public static FrameworkElement Chevron(bool open, double size = 10)
    {
        var p = new Path
        {
            Data = Geometry.Parse(open ? "M2,4 L6,8 L10,4" : "M4,2 L8,6 L4,10"), Stroke = Muted, StrokeThickness = 1.5,
            StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round,
            Width = 12, Height = 12, VerticalAlignment = VerticalAlignment.Center,
        };
        return new Viewbox { Width = size, Height = size, Child = p, VerticalAlignment = VerticalAlignment.Center };
    }

    /// <summary>An icon beside text, top-aligned.</summary>
    public static Grid WithIcon(FrameworkElement icon, UIElement body, double gap = 8, double top = 0)
    {
        var g = new Grid { Margin = new Thickness(0, top, 0, 0) };
        g.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        g.ColumnDefinitions.Add(new ColumnDefinition());
        icon.Margin = new Thickness(0, 2, gap, 0);
        g.Children.Add(icon);
        Grid.SetColumn(body, 1);
        g.Children.Add(body);
        return g;
    }

    public static Brush StateBrush(string s) => s switch
    {
        "fail" => Fail, "review" => Review, "pass" => Pass, "na" => Na, _ => Faint,
    };
}
