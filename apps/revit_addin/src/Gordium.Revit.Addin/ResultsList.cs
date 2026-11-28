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

    /// <summary>The questions card's answers, chosen and not saved (UI polish changes 22, 23).</summary>
    SetupDraft Answers { get; }

    /// <summary>A question answered in the draft: the card's Save words follow.</summary>
    void Answered();

    /// <summary>Save and check again.</summary>
    void SaveAnswers(IReadOnlyList<ProjectQuestion> questions);

    /// <summary>Open Project Information (Revit's own dialog).</summary>
    void OpenProjectInformation();
}

/// <summary>One item of the list's ItemsSource: what <see cref="EntryView"/> draws.</summary>
internal abstract class ListItem
{
    protected ListItem(IListHost host) => Host = host;

    internal IListHost Host { get; }

    /// <summary>What a screen reader says for this item and its tooltip, set on its list item (the container the
    /// keyboard focuses) by <see cref="EntryStyles"/>; null: the item's own words inside say it.</summary>
    internal virtual string? Spoken => null;

    internal virtual string? Tip => null;
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

    internal override string? Spoken => ResultViewList.Spoken(Entry);
}

/// <summary>One card of an open "What to fix" group.</summary>
internal sealed class FixCardItem(IListHost host, FixCardEntry entry) : ListItem(host)
{
    internal FixCardEntry Entry { get; } = entry;

    internal override string? Spoken => ResultViewList.Spoken(Entry);

    internal override string? Tip => ResultViewList.Tip(Entry);
}

/// <summary>One node of "By code".</summary>
internal sealed class CodeNodeItem(IListHost host, CodeNodeEntry entry) : ListItem(host)
{
    internal CodeNodeEntry Entry { get; } = entry;

    internal override string? Spoken => ResultViewList.Spoken(Entry);

    internal override string? Tip => ResultViewList.Tip(Entry);
}

/// <summary>One question of the questions card (UI polish changes 22, 23).</summary>
internal sealed class QuestionItem(IListHost host, QuestionEntry entry) : ListItem(host)
{
    internal QuestionEntry Entry { get; } = entry;

    internal override string? Spoken => ResultViewList.Spoken(Entry);

    internal override string? Tip => Entry.Question.Card.Why is { } why ? $"{Entry.Question.Card.Headline}\n\nWhy: {why}" : null;
}

/// <summary>"+ N more questions".</summary>
internal sealed class MoreQuestionsItem(IListHost host, MoreQuestionsEntry entry) : ListItem(host)
{
    internal MoreQuestionsEntry Entry { get; } = entry;

    internal override string? Spoken => ResultViewList.Spoken(Entry);
}

/// <summary>The questions card's foot: the scope note, Save and check again, Open Project Information.</summary>
internal sealed class AnswerFootItem(IListHost host, AnswerFootEntry entry) : ListItem(host)
{
    internal AnswerFootEntry Entry { get; } = entry;

    internal override string? Spoken => ResultViewList.Spoken(Entry);
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
    public override W.Style SelectStyle(object item, W.DependencyObject container)
    {
        var c = (W.FrameworkElement)container;
        // the words on the list item itself, the element the keyboard focuses and a screen reader reads (review round
        // 5); set every time, so a container reused for another item never keeps the last one's words
        if (item is ListItem { Spoken: { } spoken } li)
        {
            W.Automation.AutomationProperties.SetName(c, spoken);
            c.ToolTip = li.Tip;
        }
        else
        {
            c.ClearValue(W.Automation.AutomationProperties.NameProperty);
            c.ClearValue(W.FrameworkElement.ToolTipProperty);
        }
        return (W.Style)c.FindResource(item switch
        {
            RowItem => "list.row",
            FixGroupItem or FixCardItem or CodeNodeItem or QuestionItem or MoreQuestionsItem or AnswerFootItem => "list.opener",   // reached and opened by the keyboard too
            _ => "list.heading",
        });
    }
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
            QuestionItem q => QuestionView(q),
            MoreQuestionsItem m => MoreQuestionsView(m),
            AnswerFootItem f => AnswerFootView(f),
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
        var line = Opener(item.Host, e.Key, canOpen: true, e.Open, e.Status, 14, new W.Thickness(0, 16, 0, 4));   // 16 between sections (change 44)
        var see = Typed(new C.TextBlock { Text = e.Open ? "Hide" : e.Group.SeeWords, Margin = new W.Thickness(8, 0, 0, 0) }, "type.caption");
        Ink(see, PanelTokens.Accent);
        C.DockPanel.SetDock(see, C.Dock.Right);
        line.Children.Add(see);
        // the kind of work, as its icon (change 46), in the text's colour: never a status colour
        if (ResultViewList.IconOf(e.Group.Kind) is { } kind)
        {
            var icon = PanelLook.Icon(kind, 14);
            icon.Margin = new W.Thickness(0, 1, 6, 0);
            icon.VerticalAlignment = W.VerticalAlignment.Top;
            C.DockPanel.SetDock(icon, C.Dock.Left);
            line.Children.Add(icon);
        }
        var words = new C.StackPanel();
        words.Children.Add(Ink(Typed(new C.TextBlock { Text = e.Group.Title, TextWrapping = W.TextWrapping.Wrap, FontWeight = W.FontWeights.SemiBold }, "type.body"),
                               e.Status == PanelStatus.NotChecked ? PanelTokens.TextMuted : PanelTokens.Text));
        if (e.Group.Sub is { } sub)
            words.Children.Add(Ink(Typed(new C.TextBlock { Text = sub, TextWrapping = W.TextWrapping.Wrap }, "type.caption"), PanelTokens.TextMuted));
        line.Children.Add(words);
        // its words for a screen reader are on its list item (EntryStyles: ResultViewList.Spoken)
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
        var head = Typed(new C.TextBlock { Text = e.Card.Title, TextTrimming = W.TextTrimming.CharacterEllipsis }, "type.body");
        line.ToolTip = ResultViewList.Tip(e);
        line.Children.Add(head);
        // its words for a screen reader are on its list item (EntryStyles: ResultViewList.Spoken)
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
        var title = ResultViewList.Title(n);
        words.Children.Add(Ink(Typed(new C.TextBlock
        {
            Text = title, TextWrapping = W.TextWrapping.Wrap,
            FontWeight = e.Depth == 0 ? W.FontWeights.SemiBold : W.FontWeights.Normal,
        }, "type.body"), n.Greyed ? PanelTokens.TextMuted : PanelTokens.Text));
        if (n.Note is { } note)                                  // which code governs, the law's quoted words on hover
            words.Children.Add(Ink(Typed(new C.TextBlock { Text = note, TextWrapping = W.TextWrapping.Wrap, ToolTip = n.NoteTooltip }, "type.caption"), PanelTokens.TextMuted));
        words.Children.Add(Ink(Typed(new C.TextBlock { Text = n.Line, TextWrapping = W.TextWrapping.Wrap }, "type.caption"), PanelTokens.TextMuted));
        if (n.Scope is { } scope)                                // the scope note, once, under the book it is said of
        {
            var scopeNote = ScopeNote(scope);
            scopeNote.Margin = new W.Thickness(0, 4, 0, 2);
            words.Children.Add(scopeNote);
        }
        line.Children.Add(words);
        // which code governs and the law's words: said and shown on its list item (EntryStyles: ResultViewList.Spoken,
        // Tip, review round 5), and on hover here
        line.ToolTip = ResultViewList.Tip(e);
        return line;
    }

    // ---- UI polish changes 22 to 24: the questions asked in the card --------------------------------------------

    /// <summary>One question: its words, "N results" (opens to them), and its field's control (a dropdown, Yes / No, a
    /// box) or why there is none. A choice goes to the draft only: nothing is written until Save.</summary>
    private static W.UIElement QuestionView(QuestionItem item)
    {
        var e = item.Entry;
        var q = e.Question;
        var box = new C.StackPanel { Margin = new W.Thickness(28, 8, 4, 2) };
        var head = new C.DockPanel();
        var count = Typed(new C.TextBlock
        {
            Text = PaneWords.Results(q.Affects), Margin = new W.Thickness(8, 0, 0, 0), Cursor = I.Cursors.Hand,
            ToolTip = e.Open ? "Hide the results waiting on it" : $"See the {PaneWords.Results(q.Affects)} waiting on it ({ProjectQuestions.Affects(q.Affects)})",
        }, "type.caption");
        Ink(count, PanelTokens.Accent);
        count.MouseLeftButtonDown += (_, a) =>
        {
            a.Handled = true;
            item.Host.ToggleOpen(e.Key);
        };
        C.DockPanel.SetDock(count, C.Dock.Right);
        head.Children.Add(count);
        head.Children.Add(Typed(new C.TextBlock { Text = q.Card.Headline, TextWrapping = W.TextWrapping.Wrap }, Body));
        box.Children.Add(head);
        if (q.Field is { } f)
        {
            var chosen = item.Host.Answers.Chosen(f.Mark);
            box.Children.Add(AnswerControl(item, f, chosen ?? f.CurrentChoice?.Value ?? f.Current));
            if (f.Problem is not null && chosen is null)
                box.Children.Add(Ink(Typed(new C.TextBlock { Text = f.Problem, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 3, 0, 0) }, Caption), PanelTokens.StatusReview));
        }
        else
            box.Children.Add(Muted(ProjectQuestions.NoField, top: 2));
        return box;
    }

    /// <summary>A question's control, as the Setup form's (the same field, the same allowed values).</summary>
    private static W.UIElement AnswerControl(QuestionItem item, SetupField f, string? shown)
    {
        var host = item.Host;
        var name = item.Entry.Question.Card.Headline;
        switch (f.Kind)
        {
            case FieldKind.Choice:
            {
                var combo = new C.ComboBox { Margin = new W.Thickness(0, 4, 0, 0), MaxDropDownHeight = 280, IsEditable = false };
                W.Automation.AutomationProperties.SetName(combo, name);
                foreach (var c in f.Choices)
                    combo.Items.Add(new C.ComboBoxItem { Content = c.Label, Tag = c.Value });
                var at = f.Choices.ToList().FindIndex(c => c.Value == shown);
                combo.SelectedIndex = at;
                var hint = Muted("Choose…");
                hint.IsHitTestVisible = false;
                hint.Margin = new W.Thickness(8, 9, 24, 0);
                hint.Visibility = at < 0 ? W.Visibility.Visible : W.Visibility.Collapsed;
                // only the architect's own pick is a choice: setting the shown value above is not
                combo.SelectionChanged += (_, _) =>
                {
                    if (combo.SelectedItem is not C.ComboBoxItem { Tag: string value })
                        return;
                    host.Answers.Choose(f.Mark, value);
                    hint.Visibility = W.Visibility.Collapsed;
                    host.Answered();
                };
                var grid = new C.Grid();
                grid.Children.Add(combo);
                grid.Children.Add(hint);
                return grid;
            }
            case FieldKind.YesNo:
            {
                var row = new C.StackPanel { Orientation = C.Orientation.Horizontal, Margin = new W.Thickness(0, 4, 0, 0) };
                var buttons = new List<C.Primitives.ToggleButton>();
                foreach (var c in f.Choices)
                {
                    var t = new C.Primitives.ToggleButton
                    {
                        Content = c.Label, IsChecked = shown == c.Value, MinWidth = 48, Padding = new W.Thickness(10, 2, 10, 2),
                        Margin = new W.Thickness(buttons.Count == 0 ? 0 : 2, 0, 0, 0),
                    };
                    W.Automation.AutomationProperties.SetName(t, $"{name}: {c.Label}");
                    var value = c.Value;
                    t.Click += (_, _) =>
                    {
                        host.Answers.Choose(f.Mark, value);
                        foreach (var b in buttons)
                            b.IsChecked = ReferenceEquals(b, t);
                        host.Answered();
                    };
                    buttons.Add(t);
                    row.Children.Add(t);
                }
                return row;
            }
            default:
            {
                var number = f.Kind is FieldKind.Number or FieldKind.Feet;
                var text = new C.TextBox
                {
                    Text = shown ?? "", Margin = new W.Thickness(0, 4, 0, 0), MinWidth = number ? 90 : 0, MaxWidth = number ? 120 : double.PositiveInfinity,
                    HorizontalAlignment = number ? W.HorizontalAlignment.Left : W.HorizontalAlignment.Stretch,
                };
                // a length (or an area, #193) is typed in the project's unit, said beside the box as the Setup form's label
                // says it (review round 1: "20" in a metric project is 20 m), and feet (square feet) when Gordium can't read it
                var unit = f.Kind == FieldKind.Feet ? f.LengthUnit : null;
                W.Automation.AutomationProperties.SetName(text, unit is null ? name : $"{name}, in {unit.Words}");
                // the draft follows every keystroke (an emptied box chooses nothing), Save's words with it
                text.TextChanged += (_, _) =>
                {
                    if (text.Text.Trim().Length == 0)
                        host.Answers.Forget(f.Mark);
                    else
                        host.Answers.Choose(f.Mark, text.Text);
                    host.Answered();
                };
                if (unit is null)
                    return text;
                var row = new C.StackPanel { Orientation = C.Orientation.Horizontal };
                row.Children.Add(text);
                var symbol = Muted(ProjectQuestions.UnitWords(unit));
                symbol.Margin = new W.Thickness(6, 6, 0, 0);
                row.Children.Add(symbol);
                return row;
            }
        }
    }

    private static W.UIElement MoreQuestionsView(MoreQuestionsItem item)
    {
        var e = item.Entry;
        var t = Typed(new C.TextBlock { Text = ProjectQuestions.MoreWords(e.Hidden, e.Open), Margin = new W.Thickness(28, 6, 0, 2), Cursor = I.Cursors.Hand }, Caption);
        Ink(t, PanelTokens.Accent);
        t.MouseLeftButtonDown += (_, a) =>
        {
            a.Handled = true;
            item.Host.ToggleOpen(e.Key);
        };
        return t;
    }

    /// <summary>The scope note (change 24), what Save does, Save and check again, Open Project Information.</summary>
    private static W.UIElement AnswerFootView(AnswerFootItem item)
    {
        var e = item.Entry;
        var box = new C.StackPanel { Margin = new W.Thickness(28, 10, 4, 8) };
        if (e.Scope is { } scope)
            box.Children.Add(ScopeNote(scope));
        box.Children.Add(Muted(ProjectQuestions.NothingSaved, top: e.Scope is null ? 0 : 8));
        var n = ProjectQuestions.Unsaved(e.Questions, item.Host.Answers);
        var save = new C.Button
        {
            Content = ProjectQuestions.SaveWords(n), IsEnabled = n > 0, Tag = item, Padding = new W.Thickness(12, 3, 12, 3),
            Margin = new W.Thickness(0, 6, 0, 0), HorizontalAlignment = W.HorizontalAlignment.Left,
            ToolTip = "Writes your answers to Project Information as one step (Ctrl+Z undoes it), then checks the project again",
        };
        save.SetResourceReference(StyleProperty, "button.primary");
        save.Click += (_, a) =>
        {
            a.Handled = true;
            item.Host.SaveAnswers(e.Questions);
        };
        box.Children.Add(save);
        var pi = CauseCardsView.Link("Open Project Information", item.Host.OpenProjectInformation);
        pi.HorizontalAlignment = W.HorizontalAlignment.Left;
        pi.Margin = new W.Thickness(0, 6, 0, 0);
        box.Children.Add(pi);
        box.MouseLeftButtonDown += (_, a) => a.Handled = true;              // never selected
        return box;
    }

    /// <summary>The scope note: an information box (the accent's selection fill, never a status colour), its icon.</summary>
    internal static C.Border ScopeNote(string words)
    {
        var line = new C.DockPanel();
        var icon = Typed(new C.TextBlock { Text = "ⓘ" }, Body);
        icon.Margin = new W.Thickness(0, 0, 8, 0);
        icon.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(icon, C.Dock.Left);
        line.Children.Add(icon);
        line.Children.Add(Typed(new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap }, Caption));
        var b = new C.Border { Child = line, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4), Padding = new W.Thickness(8, 6, 8, 6), Tag = ScopeTag };
        b.SetResourceReference(BackgroundProperty, PanelTokens.BgSelected);
        b.SetResourceReference(BorderBrushProperty, PanelTokens.Accent);
        W.Automation.AutomationProperties.SetName(b, words);
        return b;
    }

    /// <summary>The scope note's tag (the renders find it by it).</summary>
    internal const string ScopeTag = "pane.scope";

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
