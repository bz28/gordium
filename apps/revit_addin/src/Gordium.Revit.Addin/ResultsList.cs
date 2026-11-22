using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using I = System.Windows.Input;
using S = System.Windows.Shapes;

namespace Gordium.Revit.Addin;

/// <summary>What a list entry asks of the panel that shows it (the ResultsView): fold a place, zoom to a row's
/// elements, open a row's detail, an element's label, and a fold after the rows opened or closed.</summary>
internal interface IListHost
{
    void Toggle(ListSection section);
    void ShowRow(RowItem row);
    void ToggleOpen(RowItem row);
    string Label(string uid);
    void FoldChanged(FoldItem fold);
}

/// <summary>One item of the list's ItemsSource: what <see cref="EntryView"/> draws.</summary>
internal abstract class ListItem
{
    protected ListItem(IListHost host) => Host = host;

    internal IListHost Host { get; }
}

internal sealed class HeadingItem(IListHost host, ListHeading heading) : ListItem(host)
{
    internal ListHeading Heading { get; } = heading;
}

internal sealed class SubItem(IListHost host, ListSubheading sub) : ListItem(host)
{
    internal ListSubheading Sub { get; } = sub;
}

/// <summary>A row; <see cref="Open"/> shows its detail (the law's words), and <see cref="Changed"/> redraws it.</summary>
internal sealed class RowItem(IListHost host, ListRow row, bool open) : ListItem(host)
{
    internal ListRow Row { get; } = row;

    internal bool Open { get; private set; } = open;

    internal event Action? Changed;

    internal void SetOpen(bool open)
    {
        if (open == Open)
            return;
        Open = open;
        Changed?.Invoke();
    }
}

/// <summary>A fold after the rows (what wasn't read from the model, the details), its open state kept here so a
/// virtualized container made again shows it as the architect left it.</summary>
/// <summary>The list's first entry: the worker's state and counts, made afresh each time it scrolls into view.</summary>
internal sealed class SummaryItem(IListHost host, Func<W.UIElement> build) : ListItem(host)
{
    internal Func<W.UIElement> Build { get; } = build;
}

internal sealed class FoldItem(IListHost host, string title, Func<W.UIElement> build) : ListItem(host)
{
    internal string Title { get; } = title;

    internal Func<W.UIElement> Build { get; } = build;

    internal bool Open { get; set; }
}

/// <summary>Chooses each container's style from the panel's dictionary: a row is a card that can be selected
/// (list.row); a heading, a sub-heading or a fold is plain, never selected or focused (list.heading).</summary>
internal sealed class EntryStyles : C.StyleSelector
{
    public override W.Style SelectStyle(object item, W.DependencyObject container) =>
        (W.Style)((W.FrameworkElement)container).FindResource(item is RowItem ? "list.row" : "list.heading");
}

/// <summary>
/// One entry of the results list, drawn in code from its item (the DataTemplate's only element: the list is a
/// virtualized ListBox, so an entry is made only when it scrolls into view, and a container is reused for another
/// item, when this redraws). Every colour is a token (SetResourceReference), every status its glyph and its words.
/// </summary>
public sealed class EntryView : C.Border
{
    private RowItem? _row;

    public EntryView() => DataContextChanged += (_, _) => Draw();

    /// <summary>The list's one item template: an EntryView, which draws whatever item it is given.</summary>
    internal static W.DataTemplate Template()
    {
        var t = new W.DataTemplate { VisualTree = new W.FrameworkElementFactory(typeof(EntryView)) };
        t.Seal();
        return t;
    }

    private void Draw()
    {
        if (_row is not null)
            _row.Changed -= Draw;
        _row = DataContext as RowItem;
        if (_row is not null)
            _row.Changed += Draw;
        Child = DataContext switch
        {
            HeadingItem h => Heading(h),
            SubItem s => Sub(s),
            RowItem r => Row(r),
            FoldItem f => Fold(f),
            SummaryItem m => Summary(m),
            _ => null,
        };
    }

    private static W.UIElement Heading(HeadingItem item)
    {
        var h = item.Heading;
        var line = new C.DockPanel { Margin = new W.Thickness(0, 10, 0, 4) };
        line.SetResourceReference(C.Panel.BackgroundProperty, PanelTokens.BgPane);   // the whole line takes the click
        if (h.Foldable)
        {
            var chevron = new S.Path
            {
                Width = 10, Height = 10, Margin = new W.Thickness(0, 0, 4, 0), VerticalAlignment = W.VerticalAlignment.Center,
                Data = W.Media.Geometry.Parse(h.Folded ? "M 3.5,2 L 6.5,5 L 3.5,8" : "M 2,3.5 L 5,6.5 L 8,3.5"),
                StrokeThickness = 1.5, StrokeStartLineCap = W.Media.PenLineCap.Round, StrokeEndLineCap = W.Media.PenLineCap.Round,
            };
            chevron.SetResourceReference(S.Shape.StrokeProperty, PanelTokens.TextMuted);
            C.DockPanel.SetDock(chevron, C.Dock.Left);
            line.Children.Add(chevron);
            line.Cursor = I.Cursors.Hand;
            line.ToolTip = h.Folded ? "Click to show these rows" : "Click to fold these rows";
            line.MouseLeftButtonDown += (_, e) =>
            {
                e.Handled = true;                                                  // a heading is never selected
                item.Host.Toggle(h.Section);
            };
        }
        var glyph = PanelLook.Glyph(h.Status, 14);
        glyph.Margin = new W.Thickness(0, 0, 6, 0);
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        line.Children.Add(glyph);
        line.Children.Add(Ink(Typed(new C.TextBlock
        {
            Text = $"{h.Title.ToUpperInvariant()} · {h.Rows} row{(h.Rows == 1 ? "" : "s")}", TextWrapping = W.TextWrapping.Wrap,
            VerticalAlignment = W.VerticalAlignment.Center,
        }, "type.overline"), StatusLook.Colour(h.Status)));
        if (!h.Foldable)
            line.MouseLeftButtonDown += (_, e) => e.Handled = true;
        return line;
    }

    private static W.UIElement Sub(SubItem item)
    {
        var line = new C.DockPanel { Margin = new W.Thickness(4, 6, 0, 3) };
        line.SetResourceReference(C.Panel.BackgroundProperty, PanelTokens.BgPane);
        var glyph = PanelLook.Glyph(item.Sub.Status, 11);                   // its place's glyph (the clock once stale)
        glyph.Margin = new W.Thickness(0, 1, 6, 0);
        glyph.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        line.Children.Add(glyph);
        var t = Muted(item.Sub.Title);
        t.FontWeight = W.FontWeights.SemiBold;
        line.Children.Add(t);
        line.MouseLeftButtonDown += (_, e) => e.Handled = true;            // a sub-heading is never selected
        return line;
    }

    private static W.UIElement Row(RowItem item)
    {
        var p = item.Row;
        var r = p.Row;
        var text = new C.StackPanel { Margin = new W.Thickness(8, 6, 8, 6) };

        // line 1: the glyph and the rule's name, the name with the row's whole width (nothing beside it: Revit trial,
        // a section in a column beside it squeezed the name to a word a line)
        var first = new C.DockPanel();
        var glyph = PanelLook.Glyph(p.Status, 14);
        glyph.Margin = new W.Thickness(0, 1, 6, 0);
        glyph.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        first.Children.Add(glyph);
        first.Children.Add(Typed(new C.TextBlock { Text = r.Name, FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
        text.Children.Add(first);

        // line 2: what the heading doesn't say, then the figures in full (never cut: the limit and how far off are a
        // failure's most important words), wrapped; a cause alone at most two lines (the whole in its detail)
        var words = ResultList.SecondLine(r);
        if (words.Length > 0)
        {
            var figures = r.Figures is not null || r.HowFar is not null;
            var cause = Typed(new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(20, 2, 0, 0) },
                              figures ? "type.figure" : Caption);
            if (!figures)
            {
                Ink(cause, PanelTokens.TextMuted);
                cause.TextTrimming = W.TextTrimming.CharacterEllipsis;
                cause.MaxHeight = 2 * 1.4 * PanelTokens.TypeOf(Caption).Size;
                cause.ToolTip = words;
            }
            text.Children.Add(cause);
        }

        // line 3: the section on its own line (muted, trimmed, the whole on hover), Show at its right
        if (r.Section is not null || r.Elements.Count > 0)
        {
            var third = new C.DockPanel { Margin = new W.Thickness(20, 3, 0, 0) };
            if (r.Elements.Count > 0)
            {
                var show = new C.Button
                {
                    Content = "Show", Padding = new W.Thickness(8, 0, 8, 0), Margin = new W.Thickness(8, 0, 0, 0),
                    VerticalAlignment = W.VerticalAlignment.Center, Focusable = false,
                    ToolTip = "Zoom to " + (r.Elements.Count == 1 ? "it" : $"its {r.Elements.Count} elements") + " in the model (Space)",
                };
                show.Click += (_, e) =>
                {
                    e.Handled = true;
                    item.Host.ShowRow(item);
                };
                C.DockPanel.SetDock(show, C.Dock.Right);
                third.Children.Add(show);
            }
            var sec = Muted(r.Section ?? "");
            sec.TextWrapping = W.TextWrapping.NoWrap;
            sec.TextTrimming = W.TextTrimming.CharacterEllipsis;
            sec.VerticalAlignment = W.VerticalAlignment.Center;
            sec.ToolTip = r.Section;
            third.Children.Add(sec);
            text.Children.Add(third);
        }

        if (item.Open)
            text.Children.Add(Detail(item));

        // the bar: the status colour, or muted stripes once stale (never a verdict's colour on a stale row)
        var bar = new S.Rectangle { Width = 4 };
        bar.SetResourceReference(S.Shape.FillProperty, p.Status == PanelStatus.Stale ? PanelLook.StaleHatch : StatusLook.Colour(p.Status));
        var dock = new C.DockPanel();
        C.DockPanel.SetDock(bar, C.Dock.Left);
        dock.Children.Add(bar);
        dock.Children.Add(text);
        W.Automation.AutomationProperties.SetName(dock, $"{StatusLook.Word(p.Status)}: {r.Name}");
        return dock;
    }

    /// <summary>The row's detail, as the panel showed it before the list (the full detail view is PR 4): its verdict,
    /// figures and reason in full, its section, its elements by name and the law's exact words.</summary>
    private static W.UIElement Detail(RowItem item)
    {
        var r = item.Row.Row;
        var d = new C.StackPanel { Margin = new W.Thickness(20, 6, 0, 2) };
        d.Children.Add(Typed(new C.TextBlock { Text = r.VerdictWords.ToUpperInvariant(), TextWrapping = W.TextWrapping.Wrap }, "type.overline"));
        if (r.Figures is not null)
            d.Children.Add(Typed(new C.TextBlock { Text = r.Figures + (r.HowFar is null ? "" : " · " + r.HowFar), TextWrapping = W.TextWrapping.Wrap }, "type.figure"));
        else if (r.HowFar is not null)
            d.Children.Add(Typed(new C.TextBlock { Text = r.HowFar, TextWrapping = W.TextWrapping.Wrap }, "type.figure"));
        if (r.Reason is not null && !r.ReasonIsFigures)
            d.Children.Add(Typed(new C.TextBlock { Text = r.Reason, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 2, 0, 0) }, Body));
        if (r.Section is not null)
            d.Children.Add(Muted(r.Section, top: 4));
        if (r.Elements.Count > 0)
        {
            var labels = r.Elements.Select(item.Host.Label).ToList();
            d.Children.Add(Muted("Elements: " + string.Join(", ", labels.Take(20)) + (labels.Count > 20 ? $", {labels.Count - 20} more" : ""), top: 4));
        }
        var law = Typed(new C.TextBlock { Text = "The law's words", Margin = new W.Thickness(0, 8, 0, 2) }, "type.overline");
        d.Children.Add(law);
        if (r.Quotes.Count == 0)
            d.Children.Add(Muted("The checker gave no quote with this row" + (r.Section is null ? "." : $": see {r.Section}.")));
        foreach (var quote in r.Quotes)
        {
            d.Children.Add(Typed(new C.TextBlock { Text = "“" + quote.Text + "”", TextWrapping = W.TextWrapping.Wrap }, "type.quote"));
            if (quote.Where is not null)
                d.Children.Add(Muted(quote.Where, bottom: 6));
        }
        d.Children.Add(Muted("Enter or double-click folds this; Ctrl+C copies the row.", top: 4));
        return d;
    }

    private static W.UIElement Summary(SummaryItem item)
    {
        var box = new C.Border { Child = item.Build() };
        box.SetResourceReference(BackgroundProperty, PanelTokens.BgPane);
        box.MouseLeftButtonDown += (_, e) => e.Handled = true;              // never selected
        return box;
    }

    private static W.UIElement Fold(FoldItem item)
    {
        var e = new C.Expander { Header = item.Title, IsExpanded = item.Open, Margin = new W.Thickness(0, 10, 0, 0) };
        void Fill()
        {
            e.Content ??= item.Build();
        }
        if (item.Open)
            Fill();
        e.Expanded += (_, _) =>
        {
            item.Open = true;
            item.Host.FoldChanged(item);
            Fill();
        };
        e.Collapsed += (_, _) =>
        {
            item.Open = false;
            item.Host.FoldChanged(item);
        };
        return e;
    }

    // ---- small pieces (as ResultsView's) --------------------------------------------------------------------

    private const string Body = "type.body";
    private const string Caption = "type.caption";

    internal static C.TextBlock Typed(C.TextBlock t, string token)
    {
        t.SetResourceReference(StyleProperty, token);
        return t;
    }

    internal static C.TextBlock Ink(C.TextBlock t, string token)
    {
        t.SetResourceReference(C.TextBlock.ForegroundProperty, token);
        return t;
    }

    internal static C.TextBlock Muted(string text, double top = 0, double bottom = 0) =>
        Ink(Typed(new C.TextBlock { Text = text, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, top, 0, bottom) }, Caption),
            PanelTokens.TextMuted);
}
