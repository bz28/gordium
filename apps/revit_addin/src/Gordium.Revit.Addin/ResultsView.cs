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
internal sealed record PanelContent(string Project, DateTime When, ResultModel? Model, IReadOnlyList<string> Missing,
                                    int MarksAdded, IReadOnlyDictionary<string, string> Labels, string Files);

/// <summary>
/// The results panel itself (a WPF view in Revit's dockable pane, beside Properties), matching the agreed mockup:
/// the header with Check again, the worker's state and counts, then the worker's groups in its order (what does not
/// comply first, what complies folded), every row shown (a scrolling list, never cut). Each row: its verdict, its
/// name, its figures and how far off, its reason, the law's section and a "Law" expander with the law's exact words;
/// clicking it selects and zooms to its elements. Plain WPF: every Revit call goes through the callbacks, which
/// queue it for Revit's thread (<see cref="PanelActions"/>).
/// </summary>
internal sealed class ResultsView : C.UserControl
{
    private readonly Action<ResultRow> _zoom;
    private readonly Action _checkAgain;
    private readonly Action _projectInformation;
    private readonly C.TextBlock _sub = Small("");
    private readonly C.Button _again;
    private readonly C.TextBlock _status = Small("");
    private readonly C.StackPanel _top = new();
    private readonly C.StackPanel _body = new() { Margin = new W.Thickness(10, 4, 10, 10) };
    private readonly C.TextBlock _footer = Small("");
    private PanelContent? _content;
    private C.Border? _selected;

    internal ResultsView(Action<ResultRow> zoom, Action checkAgain, Action projectInformation)
    {
        _zoom = zoom;
        _checkAgain = checkAgain;
        _projectInformation = projectInformation;
        SetResourceReference(BackgroundProperty, W.SystemColors.WindowBrushKey);
        SetResourceReference(ForegroundProperty, W.SystemColors.WindowTextBrushKey);
        FontSize = 12;

        _again = new C.Button { Content = "Check again", Padding = new W.Thickness(10, 2, 10, 2), Margin = new W.Thickness(8, 0, 0, 0),
                                Visibility = W.Visibility.Collapsed, VerticalAlignment = W.VerticalAlignment.Center };
        _again.Click += (_, _) => _checkAgain();
        var head = new C.StackPanel { Margin = new W.Thickness(10, 10, 10, 4) };
        head.Children.Add(new C.TextBlock { Text = "Gordium: Check my project", FontSize = 14, FontWeight = W.FontWeights.SemiBold });
        var subLine = new C.DockPanel { Margin = new W.Thickness(0, 2, 0, 4) };
        C.DockPanel.SetDock(_again, C.Dock.Right);
        subLine.Children.Add(_again);
        subLine.Children.Add(_sub);
        head.Children.Add(subLine);
        _status.Visibility = W.Visibility.Collapsed;
        _status.FontStyle = W.FontStyles.Italic;
        head.Children.Add(_status);
        head.Children.Add(_top);

        var scroll = new C.ScrollViewer
        {
            VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled,
            Content = _body,
        };
        _footer.Margin = new W.Thickness(10, 4, 10, 8);
        var root = new C.DockPanel();
        C.DockPanel.SetDock(head, C.Dock.Top);
        C.DockPanel.SetDock(_footer, C.Dock.Bottom);
        root.Children.Add(head);
        root.Children.Add(_footer);
        root.Children.Add(scroll);
        Content = root;
        _sub.Text = "Click Check my project on the Gordium tab to check this project.";
    }

    // ---- what the panel shows ------------------------------------------------------------------------------

    internal void Show(PanelContent content)
    {
        _content = content;
        _selected = null;
        _again.Visibility = W.Visibility.Visible;
        _again.IsEnabled = true;
        _sub.Text = $"Checked {content.When:HH:mm} · {content.Project}";
        Say(content.MarksAdded == 0 ? "" : $"Added {content.MarksAdded} Gordium marks to this project.");
        _top.Children.Clear();
        _body.Children.Clear();
        _footer.Text = content.Files;
        if (content.Model is not { } model)
        {
            ShowMissing(content.Missing);
            return;
        }
        _top.Children.Add(new C.TextBlock
        {
            Text = ResultText.StateWords(model.State), FontSize = 13, FontWeight = W.FontWeights.SemiBold,
            Foreground = Ink(StateTone(model.State)), Margin = new W.Thickness(0, 2, 0, 2),
        });
        foreach (var line in model.Counts)
        {
            if (line.Title is not null)
                _top.Children.Add(Small(line.Title, top: 4));
            var chips = new C.WrapPanel();
            foreach (var chip in line.Chips)
                chips.Children.Add(Chip(chip));
            _top.Children.Add(chips);
        }
        _top.Children.Add(Small(model.Checked, top: 4));

        foreach (var g in model.Groups)
            _body.Children.Add(GroupBlock(g));
        if (model.Inside.Length > 0)
            _body.Children.Add(Fold("What wasn't read from the model", false, () => Small(model.Inside)));
    }

    /// <summary>A check that failed: every row of the last check taken down, and why.</summary>
    internal void Failed(string words)
    {
        _content = null;
        _selected = null;
        _top.Children.Clear();
        _body.Children.Clear();
        _sub.Text = "Not checked";
        _footer.Text = "";
        Say(words);
    }

    /// <summary>A line under the header (a click's result, a problem); empty hides it.</summary>
    internal void Say(string words)
    {
        _status.Text = words;
        _status.Visibility = words.Length == 0 ? W.Visibility.Collapsed : W.Visibility.Visible;
    }

    private const string Checking = "Checking...";

    /// <summary>While a check runs: Check again greyed, and why.</summary>
    internal void Busy(bool busy)
    {
        _again.IsEnabled = !busy;
        if (busy)
            Say(Checking);
        else if (_status.Text == Checking)
            Say("");                                         // the check stopped without a result (no project open)
    }

    private void ShowMissing(IReadOnlyList<string> missing)
    {
        _top.Children.Add(new C.TextBlock
        {
            Text = "Nothing was checked: fill these in first", FontSize = 13, FontWeight = W.FontWeights.SemiBold,
            Foreground = Ink(Tone.Review), TextWrapping = W.TextWrapping.Wrap,
        });
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

    private W.UIElement GroupBlock(ResultGroup g)
    {
        var header = new C.TextBlock
        {
            Text = $"{g.Title.ToUpperInvariant()} ({g.Count})", FontWeight = W.FontWeights.SemiBold, FontSize = 11.5,
            Foreground = Ink(g.Tone), TextWrapping = W.TextWrapping.Wrap,
        };
        return Fold(header, g.Folded, () =>
        {
            var inner = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
            if (g.Lines.Count == 0)
                foreach (var r in g.Rows)
                    inner.Children.Add(RowBlock(r));
            else
                foreach (var l in g.Lines)
                    inner.Children.Add(Fold(new C.TextBlock { Text = l.Title, TextWrapping = W.TextWrapping.Wrap, Foreground = Ink(l.Tone) }, l.Folded, () =>
                    {
                        var rows = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
                        foreach (var r in l.Rows)
                            rows.Children.Add(RowBlock(r));
                        return rows;
                    }, indent: 12));
            return inner;
        }, top: 10);
    }

    private W.UIElement RowBlock(ResultRow r)
    {
        var text = new C.StackPanel { Margin = new W.Thickness(8, 5, 8, 2) };
        text.Children.Add(new C.TextBlock { Text = r.VerdictWords.ToUpperInvariant(), FontSize = 10, FontWeight = W.FontWeights.SemiBold, Foreground = Ink(r.Tone) });
        text.Children.Add(new C.TextBlock { Text = r.Name, FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap });
        if (r.Figures is not null)
            text.Children.Add(new C.TextBlock { Text = r.Figures + (r.HowFar is null ? "" : " · " + r.HowFar), TextWrapping = W.TextWrapping.Wrap });
        else if (r.HowFar is not null)
            text.Children.Add(new C.TextBlock { Text = r.HowFar, TextWrapping = W.TextWrapping.Wrap });
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
            var link = new C.TextBlock
            {
                Text = "Show in model", Foreground = Ink(Tone.Neutral), TextDecorations = W.TextDecorations.Underline,
                Cursor = I.Cursors.Hand, ToolTip = string.Join("\n", labels.Take(20)) + (labels.Count > 20 ? $"\n{labels.Count - 20} more" : ""),
                FontSize = 11,
            };
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
                q.Children.Add(new C.TextBlock { Text = "“" + quote.Text + "”", TextWrapping = W.TextWrapping.Wrap, FontStyle = W.FontStyles.Italic });
                if (quote.Where is not null)
                    q.Children.Add(Small(quote.Where, bottom: 6));
            }
            return q;
        }, indent: 8));

        var bar = new System.Windows.Shapes.Rectangle { Width = 4, Fill = Ink(r.Tone) };
        var dock = new C.DockPanel();
        C.DockPanel.SetDock(bar, C.Dock.Left);
        dock.Children.Add(bar);
        dock.Children.Add(stack);
        var border = new C.Border
        {
            Child = dock, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            BorderBrush = Ink(Tone.Neutral, 0x55), Margin = new W.Thickness(0, 0, 0, 6), Background = M.Brushes.Transparent,
        };
        self = border;
        if (r.Elements.Count > 0)
            text.MouseLeftButtonUp += (_, _) => Pick(border, r);
        return border;
    }

    private void Pick(C.Border? border, ResultRow r)
    {
        if (_selected is not null)
            _selected.BorderBrush = Ink(Tone.Neutral, 0x55);
        _selected = border;
        if (border is not null)
            border.BorderBrush = Accent;
        _zoom(r);
    }

    // ---- small pieces --------------------------------------------------------------------------------------

    private static readonly M.SolidColorBrush Accent = Frozen(M.Color.FromRgb(0x1E, 0x6F, 0xD9));

    private static M.SolidColorBrush Frozen(M.Color c)
    {
        var b = new M.SolidColorBrush(c);
        b.Freeze();
        return b;
    }

    private static M.Color ColorOf(Tone t) => t switch
    {
        Tone.Fails => M.Color.FromRgb(0xC6, 0x28, 0x28),
        Tone.Review => M.Color.FromRgb(0xB2, 0x6A, 0x00),
        Tone.Complies => M.Color.FromRgb(0x2E, 0x7D, 0x32),
        _ => M.Color.FromRgb(0x75, 0x75, 0x75),
    };

    private static M.SolidColorBrush Ink(Tone t, byte alpha = 0xFF)
    {
        var c = ColorOf(t);
        return Frozen(M.Color.FromArgb(alpha, c.R, c.G, c.B));
    }

    /// <summary>The state's colour: green only for complies; not checked or needs review amber.</summary>
    private static Tone StateTone(Verdict v) => v switch
    {
        Verdict.DoesNotComply => Tone.Fails,
        Verdict.Complies => Tone.Complies,
        _ => Tone.Review,
    };

    private static C.Border Chip(CountChip chip) => new()
    {
        Child = new C.TextBlock { Text = chip.Words, FontSize = 11.5 },
        Background = Ink(chip.Tone, 0x26), BorderBrush = Ink(chip.Tone), BorderThickness = new W.Thickness(1),
        CornerRadius = new W.CornerRadius(10), Padding = new W.Thickness(8, 2, 8, 2), Margin = new W.Thickness(0, 3, 6, 0),
    };

    private static C.TextBlock Small(string text, double top = 0, double right = 0, double bottom = 0)
    {
        var t = new C.TextBlock { Text = text, FontSize = 11, TextWrapping = W.TextWrapping.Wrap, Opacity = 0.8,
                                  Margin = new W.Thickness(0, top, right, bottom) };
        return t;
    }

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
