using Gordium.Revit.Reading;
using Gordium.Worker;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;
using I = System.Windows.Input;

namespace Gordium.Revit.Addin;

/// <summary>What one check put in the panel: the rows (or what to fill in first), with the project's labels for each
/// element, made on Revit's thread when the check ran (the panel never asks Revit anything itself).</summary>
/// <param name="Project">The project checked (its title).</param>
/// <param name="When">When it was checked.</param>
/// <param name="Model">The rows, or null when nothing was sent (<see cref="Missing"/> says why).</param>
/// <param name="Missing">What to fill in before anything is checked.</param>
/// <param name="MarksAdded">How many of Gordium's marks this run added to the project.</param>
/// <param name="Labels">Each element's label ("Windows id 341207"), by UniqueId; one not in the model is absent.</param>
/// <param name="Files">Where every row and the request and the answer are kept.</param>
/// <param name="ClearWords">What happened to the makers' clear openings this run (<c>ClearPrefills.Head</c>: filled as
/// drafts, or why they couldn't be written), "" when nothing.</param>
internal sealed record PanelContent(string Project, DateTime When, ResultModel? Model, IReadOnlyList<string> Missing,
                                    int MarksAdded, IReadOnlyDictionary<string, string> Labels, string Files,
                                    string ClearWords);

/// <summary>
/// The results panel itself (a WPF view in Revit's dockable pane, beside Properties), matching the agreed mockup:
/// the header with Check again, the worker's state and counts, then the worker's groups in its order (what does not
/// comply first, what complies folded), every row shown (a scrolling list, never cut). Each row: its verdict (its
/// status glyph and its words), its name, its figures and how far off, its reason, the law's section and a "Law"
/// expander with the law's exact words; clicking it selects and zooms to its elements. Plain WPF: every Revit call
/// goes through the callbacks, which queue it for Revit's thread (<see cref="PanelActions"/>). Every colour is a
/// token of the theme's dictionary (<see cref="PanelLook"/>), named with SetResourceReference so it follows Revit's
/// theme; every status is drawn as its glyph and said in words, never by colour alone (<see cref="StatusLook"/>).
/// </summary>
internal sealed class ResultsView : C.UserControl
{
    private readonly Action<ResultRow> _zoom;
    private readonly Action _checkAgain;
    private readonly Action _projectInformation;
    private readonly C.TextBlock _sub = Small("");
    private readonly C.Button _again;
    private readonly C.TextBlock _status = Small("");
    private readonly C.StackPanel _body = new() { Margin = new W.Thickness(12, 4, 12, 12) };
    private PanelContent? _content;
    private C.Border? _selected;

    internal ResultsView(Action<ResultRow> zoom, Action checkAgain, Action projectInformation, PanelTheme theme)
    {
        _zoom = zoom;
        _checkAgain = checkAgain;
        _projectInformation = projectInformation;
        PanelLook.Apply(this, theme);
        SetResourceReference(BackgroundProperty, PanelTokens.BgPane);
        SetResourceReference(ForegroundProperty, PanelTokens.Text);
        FontFamily = new M.FontFamily(PanelTokens.TypeOf(Body).Family);
        FontSize = PanelTokens.TypeOf(Body).Size;

        _again = new C.Button { Content = "Check again", Padding = new W.Thickness(10, 2, 10, 2), Margin = new W.Thickness(8, 0, 0, 0),
                                Visibility = W.Visibility.Collapsed, VerticalAlignment = W.VerticalAlignment.Center };
        _again.SetResourceReference(StyleProperty, "button.primary");
        _again.Click += (_, _) => _checkAgain();
        // compact header: the title and Check again on one line, when and which project under it
        var head = new C.StackPanel { Margin = new W.Thickness(12, 8, 12, 2) };
        var titleLine = new C.DockPanel();
        C.DockPanel.SetDock(_again, C.Dock.Right);
        titleLine.Children.Add(_again);
        titleLine.Children.Add(Typed(new C.TextBlock { Text = "Gordium: Check my project", VerticalAlignment = W.VerticalAlignment.Center,
                                                       TextTrimming = W.TextTrimming.CharacterEllipsis }, "type.title"));
        head.Children.Add(titleLine);
        head.Children.Add(_sub);
        _status.Visibility = W.Visibility.Collapsed;
        _status.FontStyle = W.FontStyles.Italic;
        head.Children.Add(_status);

        // one scrolling list for everything, the header included: rows are never out of reach at any pane size
        var all = new C.StackPanel();
        all.Children.Add(head);
        all.Children.Add(_body);
        Content = new C.ScrollViewer
        {
            VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled,
            Content = all,
        };
        _sub.Text = "Click Check project on the Gordium tab to check this project.";
    }

    /// <summary>Revit's theme changed: the theme's brushes swapped, everything on screen recoloured in place.</summary>
    internal void UseTheme(PanelTheme theme) => PanelLook.Apply(this, theme);

    // ---- what the panel shows ------------------------------------------------------------------------------

    internal void Show(PanelContent content)
    {
        _content = content;
        _selected = null;
        _again.Visibility = W.Visibility.Visible;
        _again.IsEnabled = _checkAgainState.Enabled;             // a check still waiting keeps it greyed
        _sub.Text = $"Checked {content.When:HH:mm} · {content.Project}";
        Say(_checkAgainState.Status(ClearPrefills.PanelStatus(content.MarksAdded, content.ClearWords, stale: content.Model?.Stale is not null)));
        _body.Children.Clear();
        if (content.Model is not { } model)
        {
            ShowMissing(content.Missing);
            _body.Children.Add(Small(content.Files, top: 8));
            return;
        }
        var stale = model.Stale is not null;                     // stale: every status the clock, never a verdict's colour
        foreach (var part in ResultRows.Layout(model))
            switch (part)
            {
                case PanelPart.Stale:
                    _body.Children.Add(Banner(PanelStatus.Stale, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                              Typed(new C.TextBlock { Text = model.Stale, FontWeight = W.FontWeights.SemiBold,
                                                                      TextWrapping = W.TextWrapping.Wrap }, Body), bottom: 6));
                    break;
                case PanelPart.State:
                    var state = StatusLook.Of(model.StateTone, stale);
                    _body.Children.Add(WithGlyph(state, Ink(Typed(new C.TextBlock
                    {
                        Text = ResultText.StateWords(model.State) + (model.Stale is null ? "" : " (before the model changed)"),
                        TextWrapping = W.TextWrapping.Wrap,
                    }, "type.state"), StatusLook.Colour(state)), size: 18));
                    break;
                case PanelPart.Counts:
                    // one wrap line per law, its short name first: as few lines as the width allows
                    foreach (var line in model.Counts)
                    {
                        var chips = new C.WrapPanel { Margin = new W.Thickness(0, 4, 0, 0) };
                        if (line.Title is not null)
                            chips.Children.Add(Ink(Typed(new C.TextBlock
                            {
                                Text = Short(line.Title), FontWeight = W.FontWeights.SemiBold,
                                Margin = new W.Thickness(0, 3, 6, 0), VerticalAlignment = W.VerticalAlignment.Center, ToolTip = line.Title,
                            }, Caption), PanelTokens.TextMuted));
                        foreach (var chip in line.Chips)
                            chips.Children.Add(Chip(chip, stale));
                        _body.Children.Add(chips);
                    }
                    break;
                case PanelPart.Groups:
                    foreach (var g in model.Groups)
                        _body.Children.Add(GroupBlock(g, stale));
                    break;
                case PanelPart.Inside:
                    _body.Children.Add(Fold("What wasn't read from the model", true, () => Small(model.Inside), top: 12));
                    break;
                case PanelPart.Details:
                    _body.Children.Add(Fold("Details", true, () =>
                    {
                        var d = new C.StackPanel();
                        d.Children.Add(Small(model.Checked, top: 2));
                        d.Children.Add(Small(content.Files, top: 4));
                        return d;
                    }, top: 6));
                    break;
            }
    }

    /// <summary>A law's short name for its count line: "Zoning" from "Zoning (City of Ithaca)" (the whole on hover).</summary>
    private static string Short(string title) => title.IndexOf(" (", StringComparison.Ordinal) is var i and > 0 ? title[..i] : title;

    /// <summary>The model changed since the check: everything shown greyed (ResultRows.Stale), with why, once.</summary>
    internal void MarkStale()
    {
        if (_content is not { Model: { Stale: null } model } content)
            return;
        Show(content with { Model = ResultRows.Stale(model, content.When), MarksAdded = 0, ClearWords = "" });
    }

    /// <summary>A check that failed: every row of the last check taken down, and why.</summary>
    internal void Failed(string words)
    {
        _content = null;
        _selected = null;
        _body.Children.Clear();
        _sub.Text = "Not checked";
        Say(words);
    }

    /// <summary>A line under the header (a click's result, a problem); empty hides it.</summary>
    internal void Say(string words)
    {
        _status.Text = words;
        _status.Visibility = words.Length == 0 ? W.Visibility.Collapsed : W.Visibility.Visible;
    }

    private const string Checking = CheckAgainState.Checking;

    /// <summary>Whether a Check again waits or runs: kept across every redraw (a greyed redraw after an edit).</summary>
    private readonly CheckAgainState _checkAgainState = new();

    /// <summary>While a check runs: Check again greyed, and why. The rows stay as they are (stale ones stale) until
    /// the new answer is shown.</summary>
    internal void Busy(bool busy)
    {
        if (busy)
        {
            _checkAgainState.Start();
            Say(Checking);
        }
        else
            Say(_checkAgainState.Stop(_status.Text));        // what the check's redraw had to say, or a failure's words
        _again.IsEnabled = _checkAgainState.Enabled;
    }

    private void ShowMissing(IReadOnlyList<string> missing)
    {
        _body.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                  Typed(new C.TextBlock { Text = "Nothing was checked: fill these in first", TextWrapping = W.TextWrapping.Wrap },
                                        "type.title"), bottom: 6));
        foreach (var m in missing)
            _body.Children.Add(new C.TextBlock { Text = "• " + m, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 0, 0, 6) });
        var open = new C.Button
        {
            Content = "Open Project Information", Padding = new W.Thickness(10, 3, 10, 3), Margin = new W.Thickness(0, 4, 0, 4),
            HorizontalAlignment = W.HorizontalAlignment.Left,
        };
        open.Click += (_, _) => _projectInformation();
        _body.Children.Add(open);
        _body.Children.Add(Small("Fill in the Gordium marks there, then click Check again (a street edge is asked for by a click when you do)."));
    }

    private W.UIElement GroupBlock(ResultGroup g, bool stale)
    {
        var status = StatusLook.Of(g.Tone, stale);
        var header = WithGlyph(status, Ink(Typed(new C.TextBlock
        {
            Text = $"{g.Title.ToUpperInvariant()} ({g.Count})", FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap,
        }, Caption), StatusLook.Colour(status)), size: 14);
        return Fold(header, g.Folded, () =>
        {
            var inner = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
            if (g.Lines.Count == 0)
                foreach (var r in g.Rows)
                    inner.Children.Add(RowBlock(r, stale));
            else
                foreach (var l in g.Lines)
                    inner.Children.Add(Fold(WithGlyph(StatusLook.Of(l.Tone, stale), new C.TextBlock { Text = l.Title, TextWrapping = W.TextWrapping.Wrap }, size: 14),
                                            l.Folded, () =>
                    {
                        var rows = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
                        foreach (var r in l.Rows)
                            rows.Children.Add(RowBlock(r, stale));
                        return rows;
                    }, indent: 12));
            return inner;
        }, top: 12);
    }

    private W.UIElement RowBlock(ResultRow r, bool stale)
    {
        var status = StatusLook.Of(r.Tone, stale);
        var text = new C.StackPanel { Margin = new W.Thickness(8, 6, 8, 2) };
        text.Children.Add(WithGlyph(status, Typed(new C.TextBlock { Text = r.VerdictWords.ToUpperInvariant() }, "type.overline"), size: 14));
        text.Children.Add(Typed(new C.TextBlock { Text = r.Name, FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
        if (r.Figures is not null)
            text.Children.Add(Typed(new C.TextBlock { Text = r.Figures + (r.HowFar is null ? "" : " · " + r.HowFar), TextWrapping = W.TextWrapping.Wrap }, "type.figure"));
        else if (r.HowFar is not null)
            text.Children.Add(Typed(new C.TextBlock { Text = r.HowFar, TextWrapping = W.TextWrapping.Wrap }, "type.figure"));
        if (r.Reason is not null && !r.ReasonIsFigures)
            text.Children.Add(Small(r.Reason, top: 1));

        C.Border? self = null;                               // the row's frame, made below: what a click highlights
        var stack = new C.StackPanel();
        stack.Children.Add(text);
        var foot = new C.WrapPanel { Margin = new W.Thickness(8, 0, 8, 4) };
        if (r.Section is not null)
            foot.Children.Add(Small(r.Section, right: 10));
        var labels = r.Elements.Select(uid => _content?.Labels.GetValueOrDefault(uid) ?? "not in this model now").ToList();
        if (r.Elements.Count > 0)
        {
            var link = Ink(Typed(new C.TextBlock
            {
                Text = "Show in model", TextDecorations = W.TextDecorations.Underline,
                Cursor = I.Cursors.Hand, ToolTip = string.Join("\n", labels.Take(20)) + (labels.Count > 20 ? $"\n{labels.Count - 20} more" : ""),
            }, Caption), PanelTokens.Accent);
            foot.Children.Add(link);
            link.MouseLeftButtonUp += (_, e) => { e.Handled = true; Pick(self, r); };
            text.Cursor = I.Cursors.Hand;
            text.ToolTip = "Click to select and zoom to it in the model";
        }
        stack.Children.Add(foot);
        stack.Children.Add(Fold("Law" + (r.Quotes.Count > 1 ? $" ({r.Quotes.Count} quotes)" : ""), false, () =>
        {
            var q = new C.StackPanel { Margin = new W.Thickness(0, 2, 0, 4) };
            if (r.Quotes.Count == 0)
                q.Children.Add(Small("The checker gave no quote with this row" + (r.Section is null ? "." : $": see {r.Section}.")));
            foreach (var quote in r.Quotes)
            {
                q.Children.Add(Typed(new C.TextBlock { Text = "“" + quote.Text + "”", TextWrapping = W.TextWrapping.Wrap }, "type.quote"));
                if (quote.Where is not null)
                    q.Children.Add(Small(quote.Where, bottom: 6));
            }
            return q;
        }, indent: 8));

        // the bar: the status colour, or muted stripes once stale (never a verdict's colour on a stale row)
        var bar = new System.Windows.Shapes.Rectangle { Width = 4 };
        bar.SetResourceReference(System.Windows.Shapes.Shape.FillProperty,
                                 status == PanelStatus.Stale ? PanelLook.StaleHatch : StatusLook.Colour(status));
        var dock = new C.DockPanel();
        C.DockPanel.SetDock(bar, C.Dock.Left);
        dock.Children.Add(bar);
        dock.Children.Add(stack);
        var border = new C.Border
        {
            Child = dock, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Margin = new W.Thickness(0, 0, 0, 6),
        };
        Frame(border, selected: false);
        border.MouseEnter += (_, _) =>
        {
            if (!ReferenceEquals(_selected, border))
                border.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgHover);
        };
        border.MouseLeave += (_, _) =>
        {
            if (!ReferenceEquals(_selected, border))
                Frame(border, selected: false);
        };
        self = border;
        if (r.Elements.Count > 0)
            text.MouseLeftButtonUp += (_, _) => Pick(border, r);
        return border;
    }

    /// <summary>A row's frame: a card on the pane, or selected (its background and the accent outline).</summary>
    private static void Frame(C.Border border, bool selected)
    {
        border.SetResourceReference(C.Border.BackgroundProperty, selected ? PanelTokens.BgSelected : PanelTokens.BgSurface);
        border.SetResourceReference(C.Border.BorderBrushProperty, selected ? PanelTokens.Accent : PanelTokens.Line);
    }

    private void Pick(C.Border? border, ResultRow r)
    {
        if (_selected is not null)
            Frame(_selected, selected: false);
        _selected = border;
        if (border is not null)
            Frame(border, selected: true);
        _zoom(r);
    }

    // ---- small pieces --------------------------------------------------------------------------------------

    private const string Body = "type.body";
    private const string Caption = "type.caption";

    /// <summary>The text with its type token's style (size, weight, family).</summary>
    private static C.TextBlock Typed(C.TextBlock t, string token)
    {
        t.SetResourceReference(StyleProperty, token);
        return t;
    }

    /// <summary>The text in a colour token.</summary>
    private static C.TextBlock Ink(C.TextBlock t, string token)
    {
        t.SetResourceReference(C.TextBlock.ForegroundProperty, token);
        return t;
    }

    /// <summary>The status's glyph, then the words that say it: shape and word together, never colour alone.</summary>
    private static C.DockPanel WithGlyph(PanelStatus status, W.UIElement words, double size)
    {
        var glyph = PanelLook.Glyph(status, size);
        glyph.Margin = new W.Thickness(0, 0, 6, 0);
        var line = new C.DockPanel { LastChildFill = true };
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        line.Children.Add(glyph);
        line.Children.Add(words);
        return line;
    }

    /// <summary>A banner: a glyph and its words on a fill, outlined.</summary>
    private static C.Border Banner(PanelStatus status, string fill, string outline, W.UIElement words, double bottom)
    {
        var b = new C.Border
        {
            Child = WithGlyph(status, words, size: 16), BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Padding = new W.Thickness(10, 8, 10, 8), Margin = new W.Thickness(0, 0, 0, bottom),
        };
        b.SetResourceReference(C.Border.BackgroundProperty, fill);
        b.SetResourceReference(C.Border.BorderBrushProperty, outline);
        return b;
    }

    /// <summary>One count as the worker said it, with its status's glyph, on its status's fill.</summary>
    private static C.Border Chip(CountChip chip, bool stale)
    {
        var status = StatusLook.Of(chip.Tone, stale);
        var b = new C.Border
        {
            Child = WithGlyph(status, Typed(new C.TextBlock { Text = chip.Words }, Caption), size: 11),
            BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(8), Padding = new W.Thickness(6, 1, 7, 1),
            Margin = new W.Thickness(0, 2, 4, 0),
        };
        b.SetResourceReference(C.Border.BackgroundProperty, StatusLook.ChipBackground(status));
        b.SetResourceReference(C.Border.BorderBrushProperty, StatusLook.Colour(status));
        return b;
    }

    /// <summary>Small muted words: the caption type in text.muted (a colour token, never a faded opacity, so its
    /// contrast is the one tested).</summary>
    private static C.TextBlock Small(string text, double top = 0, double right = 0, double bottom = 0) =>
        Ink(Typed(new C.TextBlock { Text = text, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, top, right, bottom) }, Caption),
            PanelTokens.TextMuted);

    private static C.Expander Fold(object header, bool folded, Func<W.UIElement> build, double top = 0, double indent = 0)
    {
        var e = new C.Expander { Header = header, IsExpanded = !folded, Margin = new W.Thickness(indent, top, 0, 0) };
        // built when first opened: a folded group of hundreds of rows costs nothing until then
        void Fill()
        {
            if (e.Content is null)
                e.Content = build();
        }
        if (!folded)
            Fill();
        e.Expanded += (_, _) => Fill();
        return e;
    }
}
