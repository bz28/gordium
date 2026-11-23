using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;

namespace Gordium.Revit.Addin;

/// <summary>
/// The pane's selection strip (docs/revit/ui_design_pass.md, change 14): what is selected in Revit and the results that
/// mention it (<see cref="SelectionMap.Answer"/>), each a link to its detail with its own status glyph, eight shown
/// then "Show all N", and "Show every result" to put the strip away. Plain WPF with no Revit type, so it is drawn
/// off-screen too; every colour a theme token (it sits in the pane, so it follows Revit's theme with it). It never
/// says a verdict of its own: the line and each glyph are the rows' (stale once the model changed).
/// </summary>
internal static class SelectionStrip
{
    /// <summary>The strip's tag (the off-screen renders find it by it).</summary>
    internal const string Tag = "pane.selection";

    /// <summary>The strip for <paramref name="answer"/>: <paramref name="open"/> opens a result's detail,
    /// <paramref name="close"/> puts the strip away; <paramref name="all"/> lists every result, not the first eight.</summary>
    internal static W.FrameworkElement Build(SelectionAnswer answer, Action<string> open, Action close, bool all, Action showAll)
    {
        var inner = new C.StackPanel();
        inner.Children.Add(Words("SELECTED IN REVIT", "type.caption", PanelTokens.TextMuted, semi: true));
        inner.Children.Add(Words(answer.Title, "type.body", PanelTokens.Text, semi: true, top: 2));
        inner.Children.Add(Words(answer.Line, "type.body", PanelTokens.Text, top: 2));
        var shown = all ? answer.Rows : answer.Rows.Take(SelectionMap.Shown).ToList();
        foreach (var row in shown)
        {
            var line = new C.DockPanel { Margin = new W.Thickness(0, 5, 0, 0), LastChildFill = true };
            var glyph = PanelLook.Glyph(row.Status, 12);
            glyph.Margin = new W.Thickness(0, 2, 6, 0);
            glyph.VerticalAlignment = W.VerticalAlignment.Top;
            C.DockPanel.SetDock(glyph, C.Dock.Left);
            line.Children.Add(glyph);
            var id = row.Row.Id;
            line.Children.Add(Link(row.Row.Name, "Open its detail: why, what to do, the law's words", () => open(id)));
            inner.Children.Add(line);
        }
        var foot = new C.WrapPanel { Margin = new W.Thickness(0, 8, 0, 0) };
        if (shown.Count < answer.Rows.Count)
        {
            var more = Link($"Show all {answer.Rows.Count}", "List every result that mentions it here", showAll);
            more.Margin = new W.Thickness(0, 0, 14, 4);
            foot.Children.Add(more);
        }
        var every = new C.Button { Content = "Show every result", Padding = new W.Thickness(8, 1, 8, 1), Margin = new W.Thickness(0, 0, 0, 4),
                                   ToolTip = "Put this away: the pane lists every result again" };
        every.Click += (_, e) =>
        {
            e.Handled = true;
            close();
        };
        foot.Children.Add(every);
        inner.Children.Add(foot);
        var box = new C.Border
        {
            Child = inner, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Padding = new W.Thickness(10, 8, 10, 6), Tag = Tag,
        };
        box.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSelected);
        box.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Accent);
        W.Automation.AutomationProperties.SetName(box, $"Selected in Revit: {answer.Title}. {answer.Line}");
        // never more than about half the docked pane (~430 px): the list keeps the rest; the strip scrolls
        return new C.ScrollViewer
        {
            Content = box, MaxHeight = 260, Margin = new W.Thickness(12, 4, 12, 4),
            VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled,
        };
    }

    private static C.TextBlock Words(string text, string type, string ink, bool semi = false, double top = 0)
    {
        var t = new C.TextBlock { Text = text, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, top, 0, 0) };
        t.SetResourceReference(W.FrameworkElement.StyleProperty, type);
        t.SetResourceReference(C.TextBlock.ForegroundProperty, ink);
        if (semi)
            t.FontWeight = W.FontWeights.SemiBold;
        return t;
    }

    private static C.Button Link(string words, string tip, Action act)
    {
        var link = new C.Button
        {
            Content = new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap },
            Padding = new W.Thickness(0), BorderThickness = new W.Thickness(0),
            HorizontalContentAlignment = W.HorizontalAlignment.Left, HorizontalAlignment = W.HorizontalAlignment.Left,
            ToolTip = tip, Cursor = W.Input.Cursors.Hand,
        };
        link.SetResourceReference(C.Control.ForegroundProperty, PanelTokens.Accent);
        link.SetResourceReference(C.Control.BackgroundProperty, PanelTokens.BgSelected);     // on the strip's own colour
        W.Automation.AutomationProperties.SetName(link, words);
        link.Click += (_, e) =>
        {
            e.Handled = true;
            act();
        };
        return link;
    }
}
