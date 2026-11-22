using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;

namespace Gordium.Revit.Addin;

/// <summary>What the detail asks of the panel that shows it (the ResultsView).</summary>
internal interface IDetailHost
{
    /// <summary>Back to the list, at the same row and scroll position.</summary>
    void Back();

    /// <summary>The previous (−1) or next (+1) row the list shows.</summary>
    void Step(int step);

    /// <summary>Zoom to the row's elements (all), or to one of them.</summary>
    void ShowElements(string? uid);

    /// <summary>Open the law at its page (the worker's link).</summary>
    void OpenLaw(LawLink link);

    /// <summary>Check the project again.</summary>
    void CheckAgain();
}

/// <summary>
/// A result's detail (docs/revit/ui_design_pass.md section 2.4, PR 4), drawn from its <see cref="ResultDetail"/>: Back
/// and the row's position, the verdict and rule, why, what to do (each step a button where the panel can do it), the
/// figures against their limits and how far off (the worker's words), the law's exact words with Open the law, and the
/// elements by their names with Show. Every colour a token (SetResourceReference), every status its glyph and word.
/// It makes no decision: <see cref="Details"/> does, Revit-free and tested.
/// </summary>
internal static class DetailView
{
    internal static W.FrameworkElement Build(ResultDetail d, IDetailHost host, bool canStepBack, bool canStepOn)
    {
        var page = new C.StackPanel { Margin = new W.Thickness(12, 4, 12, 12) };

        // Back, then the row's place among the rows shown and Previous / Next
        var top = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 8) };
        var back = Button("‹ Back", "Back to the results, where you were (Backspace or Esc)", host.Back);
        C.DockPanel.SetDock(back, C.Dock.Left);
        top.Children.Add(back);
        var next = Button("›", "Next row (Alt+Down)", () => host.Step(1));
        next.IsEnabled = canStepOn;
        var prev = Button("‹", "Previous row (Alt+Up)", () => host.Step(-1));
        prev.IsEnabled = canStepBack;
        foreach (var b in new[] { next, prev })
        {
            b.Margin = new W.Thickness(4, 0, 0, 0);
            C.DockPanel.SetDock(b, C.Dock.Right);
            top.Children.Add(b);
        }
        var where = EntryView.Muted(d.Position);
        where.HorizontalAlignment = W.HorizontalAlignment.Right;
        where.VerticalAlignment = W.VerticalAlignment.Center;
        where.Margin = new W.Thickness(8, 0, 4, 0);
        top.Children.Add(where);
        page.Children.Add(top);

        if (d.Stale is not null)
            page.Children.Add(Box(PanelStatus.Stale, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                  Body(d.Stale, semi: true)));

        // the verdict, the rule and its section
        var verdict = new C.DockPanel { Margin = new W.Thickness(0, 4, 0, 2) };
        var glyph = PanelLook.Glyph(d.Status, 16);
        glyph.Margin = new W.Thickness(0, 0, 6, 0);
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        verdict.Children.Add(glyph);
        verdict.Children.Add(EntryView.Ink(EntryView.Typed(new C.TextBlock
        {
            Text = d.VerdictWords.ToUpperInvariant(), TextWrapping = W.TextWrapping.Wrap, VerticalAlignment = W.VerticalAlignment.Center,
        }, "type.overline"), StatusLook.Colour(d.Status)));
        page.Children.Add(verdict);
        page.Children.Add(EntryView.Typed(new C.TextBlock { Text = d.Name, TextWrapping = W.TextWrapping.Wrap }, "type.title"));
        if (d.Section is not null)
            page.Children.Add(EntryView.Muted(d.Section, top: 2));

        if (d.Why is not null)
        {
            page.Children.Add(Heading("Why"));
            page.Children.Add(Body(d.Why));
        }

        if (d.Steps.Count > 0)
        {
            page.Children.Add(Heading("What to do"));
            var n = 0;
            foreach (var step in d.Steps)
            {
                var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 6) };
                var num = EntryView.Muted($"{++n}.");
                num.Width = 16;
                num.TextWrapping = W.TextWrapping.NoWrap;
                C.DockPanel.SetDock(num, C.Dock.Left);
                line.Children.Add(num);
                var words = new C.StackPanel();
                words.Children.Add(Body(step.Words));
                if (Act(step.Action, d, host) is { } act)
                {
                    act.HorizontalAlignment = W.HorizontalAlignment.Left;
                    act.Margin = new W.Thickness(0, 3, 0, 0);
                    words.Children.Add(act);
                }
                line.Children.Add(words);
                page.Children.Add(line);
            }
        }

        if (d.Figures.Count > 0 || d.HowFar is not null)
        {
            page.Children.Add(Heading("Measured against the limit"));
            foreach (var f in d.Figures)
                page.Children.Add(Figure(f));
            if (d.HowFar is not null)
                page.Children.Add(Pair("How far", d.HowFar, null));
        }

        page.Children.Add(Heading("The law's words"));
        if (d.NoQuote is not null)
            page.Children.Add(EntryView.Muted(d.NoQuote));
        foreach (var q in d.Quotes)
        {
            var quote = new C.StackPanel();
            quote.Children.Add(EntryView.Typed(new C.TextBlock { Text = "“" + q.Text + "”", TextWrapping = W.TextWrapping.Wrap }, "type.quote"));
            if (q.Where is not null)
                quote.Children.Add(EntryView.Muted(q.Where, top: 2));
            var rule = new C.Border
            {
                Child = quote, BorderThickness = new W.Thickness(3, 0, 0, 0), Padding = new W.Thickness(8, 2, 0, 2),
                Margin = new W.Thickness(0, 0, 0, 8),
            };
            rule.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
            page.Children.Add(rule);
        }
        foreach (var link in d.Links)
        {
            var open = Button("Open the law: " + link.Citation, link.Url, () => host.OpenLaw(link));
            open.HorizontalAlignment = W.HorizontalAlignment.Left;
            open.Margin = new W.Thickness(0, 0, 0, 4);
            page.Children.Add(open);
        }
        if (d.Links.Count == 0)
            page.Children.Add(EntryView.Muted("No link to the source was sent with this row: find it by the section and page above."));

        if (d.Elements.Count > 0)
        {
            var head = new C.DockPanel { Margin = new W.Thickness(0, 14, 0, 4) };
            if (d.Elements.Count(e => e.InModel) > 1)
            {
                var all = Button("Show all", "Zoom to every one of them in the model", () => host.ShowElements(null));
                C.DockPanel.SetDock(all, C.Dock.Right);
                head.Children.Add(all);
            }
            var h = Heading("Elements");
            h.Margin = new W.Thickness(0);
            h.VerticalAlignment = W.VerticalAlignment.Center;
            head.Children.Add(h);
            page.Children.Add(head);
            foreach (var e in d.Elements)
            {
                var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 4) };
                if (e.InModel)
                {
                    var show = Button("Show", e.ShowTip, () => host.ShowElements(e.Uid));
                    C.DockPanel.SetDock(show, C.Dock.Right);
                    line.Children.Add(show);
                }
                var name = e.InModel ? Body(e.Name) : EntryView.Muted(e.Name);
                name.VerticalAlignment = W.VerticalAlignment.Center;
                line.Children.Add(name);
                page.Children.Add(line);
            }
        }
        page.Children.Add(EntryView.Muted("Backspace or Esc: back to the results. Ctrl+C copies the row.", top: 12));

        var scroll = new C.ScrollViewer
        {
            Content = page, VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled, Focusable = true,
        };
        W.Automation.AutomationProperties.SetName(scroll, $"Detail: {StatusLook.Word(d.Status)}: {d.Name}");
        return scroll;
    }

    /// <summary>A step's button, where the panel can do the step (none for words only, or a link not sent).</summary>
    private static C.Button? Act(DetailAction action, ResultDetail d, IDetailHost host) => action switch
    {
        DetailAction.ShowElements => Button(d.Elements.Count(e => e.InModel) == 1 ? "Show" : "Show all", "Zoom to them in the model (Space)",
                                            () => host.ShowElements(null)),
        DetailAction.OpenLaw when d.Links.Count > 0 => Button("Open the law", d.Links[0].Url, () => host.OpenLaw(d.Links[0])),
        DetailAction.CheckAgain => Primary(Button("Check again", "Check this project again: only the check changes a verdict", host.CheckAgain)),
        _ => null,
    };

    private static W.UIElement Figure(FigureLine f)
    {
        var box = new C.StackPanel { Margin = new W.Thickness(0, 0, 0, 6) };
        if (f.What is not null)
            box.Children.Add(EntryView.Muted(f.What));
        box.Children.Add(Pair(f.Measured is null ? "Measured" : f.How == "measured" ? "Measured" : "Stated", f.Measured ?? "not measured", null));
        box.Children.Add(Pair("Limit", f.Limit, null));
        return box;
    }

    /// <summary>"Measured   20 in": a label and its figure in the figure type, aligned.</summary>
    private static C.DockPanel Pair(string label, string value, string? tip)
    {
        var line = new C.DockPanel { Margin = new W.Thickness(0, 1, 0, 1) };
        var l = EntryView.Muted(label);
        l.Width = 72;
        l.TextWrapping = W.TextWrapping.NoWrap;
        C.DockPanel.SetDock(l, C.Dock.Left);
        line.Children.Add(l);
        line.Children.Add(EntryView.Typed(new C.TextBlock { Text = value, TextWrapping = W.TextWrapping.Wrap, ToolTip = tip }, "type.figure"));
        return line;
    }

    private static C.TextBlock Heading(string words) =>
        EntryView.Ink(EntryView.Typed(new C.TextBlock { Text = words.ToUpperInvariant(), Margin = new W.Thickness(0, 14, 0, 4) }, "type.overline"),
                      PanelTokens.TextMuted);

    private static C.TextBlock Body(string words, bool semi = false)
    {
        var t = EntryView.Typed(new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap }, "type.body");
        if (semi)
            t.FontWeight = W.FontWeights.SemiBold;
        return t;
    }

    private static C.Button Button(string words, string tip, Action click)
    {
        // the words wrap (a long citation is never cut), left-aligned in the button
        var b = new C.Button
        {
            Content = new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap }, Padding = new W.Thickness(8, 1, 8, 1),
            ToolTip = tip, VerticalAlignment = W.VerticalAlignment.Center, HorizontalContentAlignment = W.HorizontalAlignment.Left,
        };
        W.Automation.AutomationProperties.SetName(b, words);
        b.Click += (_, e) =>
        {
            e.Handled = true;
            click();
        };
        return b;
    }

    private static C.Button Primary(C.Button b)
    {
        b.SetResourceReference(W.FrameworkElement.StyleProperty, "button.primary");
        return b;
    }

    private static C.Border Box(PanelStatus status, string fill, string outline, W.UIElement words)
    {
        var line = new C.DockPanel();
        var glyph = PanelLook.Glyph(status, 16);
        glyph.Margin = new W.Thickness(0, 0, 6, 0);
        glyph.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        line.Children.Add(glyph);
        line.Children.Add(words);
        var b = new C.Border
        {
            Child = line, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Padding = new W.Thickness(10, 8, 10, 8), Margin = new W.Thickness(0, 0, 0, 8),
        };
        b.SetResourceReference(C.Border.BackgroundProperty, fill);
        b.SetResourceReference(C.Border.BorderBrushProperty, outline);
        return b;
    }
}
