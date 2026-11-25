using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using I = System.Windows.Input;
using S = System.Windows.Shapes;

namespace Gordium.Revit.Addin;

/// <summary>What a list entry asks of the panel that shows it (the ResultsView): fold a place, zoom to a row's
/// elements, and a fold after the rows opened or closed. (A row's detail is its own view: DetailView.)</summary>
internal interface IListHost
{
    void Toggle(ListSection section);
    void ShowRow(RowItem row);
    void FoldChanged(FoldItem fold);

    /// <summary>Whether a row is ticked "looked at" (the architect's note, never a verdict).</summary>
    bool IsLooked(string id);

    /// <summary>A row's "looked at" tick changed.</summary>
    void TickRow(ListRow row, bool ticked);

    /// <summary>A "What to fix" group or card, or a "By code" node, opened or folded (UI polish PR 3).</summary>
    void ToggleOpen(string key);
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

/// <summary>A row (Enter or a double click opens its detail, DetailView, in place of the list).</summary>
internal sealed class RowItem(IListHost host, ListRow row) : ListItem(host)
{
    internal ListRow Row { get; } = row;
}

/// <summary>A "What to fix" group's heading (UI polish PR 3).</summary>
internal sealed class FixGroupItem(IListHost host, FixGroupEntry entry) : ListItem(host)
{
    internal FixGroupEntry Entry { get; } = entry;
}

/// <summary>One card of an open "What to fix" group.</summary>
internal sealed class FixCardItem(IListHost host, FixCardEntry entry) : ListItem(host)
{
    internal FixCardEntry Entry { get; } = entry;
}

/// <summary>One node of "By code".</summary>
internal sealed class CodeNodeItem(IListHost host, CodeNodeEntry entry) : ListItem(host)
{
    internal CodeNodeEntry Entry { get; } = entry;
}

/// <summary>The list's first entry: the worker's state and counts, made afresh each time it scrolls into view.</summary>
internal sealed class SummaryItem(IListHost host, Func<W.UIElement> build) : ListItem(host)
{
    internal Func<W.UIElement> Build { get; } = build;
}

/// <summary>The "Fix these first" cause cards (CauseCardsView), made afresh each time they scroll into view.</summary>
internal sealed class CausesItem(IListHost host, Func<W.UIElement> build) : ListItem(host)
{
    internal Func<W.UIElement> Build { get; } = build;
}

/// <summary>A fold after the rows (what wasn't read from the model, the details), its open state kept here so a
/// virtualized container made again shows it as the architect left it.</summary>
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
        (W.Style)((W.FrameworkElement)container).FindResource(item switch
        {
            RowItem => "list.row",
            FixGroupItem or FixCardItem or CodeNodeItem => "list.opener",   // reached and opened by the keyboard too
            _ => "list.heading",
        });
}

/// <summary>
/// One entry of the results list, drawn in code from its item (the DataTemplate's only element: the list is a
/// virtualized ListBox, so an entry is made only when it scrolls into view, and a container is reused for another
/// item, when this redraws). Every colour is a token (SetResourceReference), every status its glyph and its words.
/// </summary>
public sealed class EntryView : C.Border
{
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
        Child = DataContext switch
        {
            HeadingItem h => Heading(h),
            SubItem s => Sub(s),
            RowItem r => Row(r),
            FoldItem f => Fold(f),
            SummaryItem m => Summary(m),
            CausesItem c => Causes(c),
            FixGroupItem g => FixGroupView(g),
            FixCardItem c => FixCardView(c),
            CodeNodeItem n => CodeNodeView(n),
            _ => null,
        };
    }

    // ---- UI polish PR 3: the two views' entries -------------------------------------------------------------

    /// <summary>A line the whole of which opens or folds <paramref name="key"/> (a chevron when it can), its glyph
    /// and words; never selected.</summary>
    private static C.DockPanel Opener(IListHost host, string key, bool canOpen, bool open, PanelStatus status, double glyph,
                                      W.Thickness margin)
    {
        var line = new C.DockPanel { Margin = margin };
        line.SetResourceReference(C.Panel.BackgroundProperty, PanelTokens.BgPane);   // the whole line takes the click
        var chevron = new S.Path
        {
            Width = 10, Height = 10, Margin = new W.Thickness(0, 0, 4, 0), VerticalAlignment = W.VerticalAlignment.Top,
            Data = W.Media.Geometry.Parse(open ? "M 2,3.5 L 5,6.5 L 8,3.5" : "M 3.5,2 L 6.5,5 L 3.5,8"),
            StrokeThickness = 1.5, StrokeStartLineCap = W.Media.PenLineCap.Round, StrokeEndLineCap = W.Media.PenLineCap.Round,
            Visibility = canOpen ? W.Visibility.Visible : W.Visibility.Hidden,
        };
        chevron.SetResourceReference(S.Shape.StrokeProperty, PanelTokens.TextMuted);
        C.DockPanel.SetDock(chevron, C.Dock.Left);
        line.Children.Add(chevron);
        var g = PanelLook.Glyph(status, glyph);
        g.Margin = new W.Thickness(0, 0, 6, 0);
        g.VerticalAlignment = W.VerticalAlignment.Top;
        g.ToolTip = StatusLook.Word(status);
        C.DockPanel.SetDock(g, C.Dock.Left);
        line.Children.Add(g);
        if (canOpen)
        {
            line.Cursor = I.Cursors.Hand;
            line.MouseLeftButtonDown += (_, e) =>
            {
                e.Handled = true;
                host.ToggleOpen(key);
            };
        }
        return line;
    }

    private static W.UIElement FixGroupView(FixGroupItem item)
    {
        var e = item.Entry;
        var line = Opener(item.Host, e.Key, canOpen: true, e.Open, e.Status, 14, new W.Thickness(0, 10, 0, 4));
        var see = Typed(new C.TextBlock { Text = e.Open ? "Hide" : e.Group.SeeWords, Margin = new W.Thickness(8, 0, 0, 0) }, "type.caption");
        Ink(see, PanelTokens.Accent);
        C.DockPanel.SetDock(see, C.Dock.Right);
        line.Children.Add(see);
        var words = new C.StackPanel();
        words.Children.Add(Ink(Typed(new C.TextBlock { Text = e.Group.Title, TextWrapping = W.TextWrapping.Wrap, FontWeight = W.FontWeights.SemiBold }, "type.body"),
                               e.Status == PanelStatus.NotChecked ? PanelTokens.TextMuted : PanelTokens.Text));
        if (e.Group.Sub is { } sub)
            words.Children.Add(Ink(Typed(new C.TextBlock { Text = sub, TextWrapping = W.TextWrapping.Wrap }, "type.caption"), PanelTokens.TextMuted));
        line.Children.Add(words);
        W.Automation.AutomationProperties.SetName(line, $"{e.Group.Title}, {StatusLook.Word(e.Status)}, {e.Group.SeeWords}");
        return line;
    }

    private static W.UIElement FixCardView(FixCardItem item)
    {
        var e = item.Entry;
        var line = Opener(item.Host, e.Key, canOpen: true, e.Open, e.Status, 11, new W.Thickness(14, 2, 0, 2));
        var count = Typed(new C.TextBlock { Text = PaneWords.Results(e.Card.Rows.Count), Margin = new W.Thickness(8, 0, 0, 0) }, "type.caption");
        Ink(count, PanelTokens.TextMuted);
        C.DockPanel.SetDock(count, C.Dock.Right);
        line.Children.Add(count);
        // the headline on one line (change 25), the checker's words behind it on hover ("Why?")
        var head = Typed(new C.TextBlock { Text = e.Card.Headline, TextTrimming = W.TextTrimming.CharacterEllipsis }, "type.body");
        line.ToolTip = e.Card.Why is { } why ? $"{e.Card.Headline}\n\nWhy: {why}" : e.Card.Headline;
        line.Children.Add(head);
        W.Automation.AutomationProperties.SetName(line, $"{e.Card.Headline}, {PaneWords.Results(e.Card.Rows.Count)}");
        return line;
    }

    private static W.UIElement CodeNodeView(CodeNodeItem item)
    {
        var e = item.Entry;
        var n = e.Node;
        var top = e.Depth == 0 ? 10 : 2;
        var line = Opener(item.Host, e.Key, e.CanOpen, e.Open, e.Status, e.Depth == 0 ? 14 : 11,
                          new W.Thickness(14 * e.Depth, top, 0, 2));
        var words = new C.StackPanel();
        var title = n.Number is { Length: > 0 } number && n.Level != CodeLevel.Others ? $"{number} {n.Title}" : n.Title;
        words.Children.Add(Ink(Typed(new C.TextBlock
        {
            Text = title, TextWrapping = W.TextWrapping.Wrap,
            FontWeight = e.Depth == 0 ? W.FontWeights.SemiBold : W.FontWeights.Normal,
        }, "type.body"), n.Greyed ? PanelTokens.TextMuted : PanelTokens.Text));
        if (n.Note is { } note)
            words.Children.Add(Ink(Typed(new C.TextBlock { Text = note, TextWrapping = W.TextWrapping.Wrap }, "type.caption"), PanelTokens.TextMuted));
        words.Children.Add(Ink(Typed(new C.TextBlock { Text = n.Line, TextWrapping = W.TextWrapping.Wrap }, "type.caption"), PanelTokens.TextMuted));
        line.Children.Add(words);
        W.Automation.AutomationProperties.SetName(line, $"{title}, {StatusLook.Word(e.Status)}, {n.Line}");
        return line;
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
            line.ToolTip = h.Folded ? "Click to show these results" : "Click to fold these results";
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
            Text = $"{h.Title.ToUpperInvariant()} · {PaneWords.Results(h.Rows)}", TextWrapping = W.TextWrapping.Wrap,
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

        // line 3: the section on its own line (muted, trimmed, the whole on hover), Show at its right, and before it
        // the "looked at" tick of a row in review or to check by hand (the architect's note: never a verdict)
        var tickable = LookedAt.Tickable(p);
        if (r.Section is not null || r.Elements.Count > 0 || tickable)
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
            if (tickable)
            {
                var tick = CauseCardsView.Tick(new CauseCardsView.TickTag(false, r.Id), item.Host.IsLooked(r.Id), t => item.Host.TickRow(p, t));
                tick.Margin = new W.Thickness(8, 0, 0, 0);
                tick.Focusable = false;                                            // the row's keys stay the list's
                W.Automation.AutomationProperties.SetName(tick, "Looked at: " + r.Name);
                C.DockPanel.SetDock(tick, C.Dock.Right);
                third.Children.Add(tick);
            }
            var sec = Muted(r.Section ?? "");
            sec.TextWrapping = W.TextWrapping.NoWrap;
            sec.TextTrimming = W.TextTrimming.CharacterEllipsis;
            sec.VerticalAlignment = W.VerticalAlignment.Center;
            sec.ToolTip = r.Section;
            third.Children.Add(sec);
            text.Children.Add(third);
        }

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

    private static W.UIElement Summary(SummaryItem item)
    {
        var box = new C.Border { Child = item.Build() };
        box.SetResourceReference(BackgroundProperty, PanelTokens.BgPane);
        box.MouseLeftButtonDown += (_, e) => e.Handled = true;              // never selected
        return box;
    }

    private static W.UIElement Causes(CausesItem item)
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
