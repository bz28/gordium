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

    /// <summary>Go to the questions card ("Answer N questions about the project") in What to fix.</summary>
    void Answer();

    /// <summary>Whether the row is ticked "looked at" (the architect's note, never a verdict), and the tick changed.</summary>
    bool DetailLooked { get; }

    void TickDetail(bool ticked);
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
    internal static W.FrameworkElement Build(ResultDetail d, IDetailHost host, bool canStepBack, bool canStepOn) =>
        d.Page is { } p ? BuildPage(d, p, host, canStepBack, canStepOn) : BuildOld(d, host, canStepBack, canStepOn);

    /// <summary>The callout's tag (the renders and tests find it by it).</summary>
    internal const string CalloutTag = "detail.callout";

    /// <summary>The checker's words behind "Why?" (folded until clicked).</summary>
    internal const string WhyTag = "detail.why";

    /// <summary>
    /// The page as the UI polish lays it out (changes 28 to 32, Ben approved 2026-11-23): Back and the result's place;
    /// the verdict, the name and one cite; a callout with a one-line headline, its one button and "Why?" (the checker's
    /// own words, folded); "What to do" as plain numbered steps; "Measured against the limit" only when something was
    /// measured; "What the code says" with the first quote, "Open the code at p.N" and the rest folded; the elements;
    /// "Mark as looked at" at the foot. Every word is <see cref="DetailPages"/>' (tested there).
    /// </summary>
    private static W.FrameworkElement BuildPage(ResultDetail d, DetailPage p, IDetailHost host, bool canStepBack, bool canStepOn)
    {
        var page = new C.StackPanel { Margin = new W.Thickness(12, 4, 12, 12) };
        page.Children.Add(TopBar(d, host, canStepBack, canStepOn));
        if (d.Stale is not null)
            page.Children.Add(Box(PanelStatus.Stale, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, Body(d.Stale, semi: true)));

        // the verdict, the name and one cite (change 32)
        page.Children.Add(Verdict(d));
        page.Children.Add(EntryView.Typed(new C.TextBlock { Text = d.Name, TextWrapping = W.TextWrapping.Wrap }, "type.title"));
        if (p.Cite.Length > 0)
            page.Children.Add(EntryView.Muted(p.Cite, top: 2));

        // the callout (change 28): one line of what is needed, its one button, "Why?" opening the checker's own words
        if (p.Headline is not null)
        {
            var inside = new C.StackPanel();
            inside.Children.Add(Body(p.Headline));
            var buttons = new C.WrapPanel { Margin = new W.Thickness(0, 8, 0, 0) };
            if (p.ActionWords is { } words)
            {
                var act = Primary(Button(words, p.Action == CalloutAction.Answer
                    ? "The questions are asked in What to fix: answer them there, then Save and check again"
                    : "Zoom to them in the model (Space)", p.Action == CalloutAction.Answer ? host.Answer : () => host.ShowElements(null)));
                act.Padding = new W.Thickness(12, 3, 12, 3);
                act.Margin = new W.Thickness(0, 0, 10, 0);
                buttons.Children.Add(act);
            }
            C.StackPanel? why = null;
            if (d.Why is not null)
            {
                why = new C.StackPanel { Visibility = W.Visibility.Collapsed, Tag = WhyTag, Margin = new W.Thickness(0, 6, 0, 0) };
                why.Children.Add(Heading(DetailPages.WhyHeading, top: 2));
                why.Children.Add(Body(PaneWords.Capital(d.Why)));
                var open = why;
                C.Button? link = null;
                link = CauseCardsView.Link("Why?", () =>
                {
                    var shown = open.Visibility != W.Visibility.Visible;
                    open.Visibility = shown ? W.Visibility.Visible : W.Visibility.Collapsed;
                    if (link!.Content is C.TextBlock t)
                        t.Text = shown ? "Hide why" : "Why?";
                });
                link.ToolTip = "The checker's own words for why this result is as it is";
                link.VerticalAlignment = W.VerticalAlignment.Center;
                buttons.Children.Add(link);
            }
            if (buttons.Children.Count > 0)
                inside.Children.Add(buttons);
            if (why is not null)
                inside.Children.Add(why);
            var status = d.Status is PanelStatus.Fails ? (PanelTokens.StatusFailFill, PanelTokens.StatusFail)
                : d.Status is PanelStatus.Stale or PanelStatus.NotChecked or PanelStatus.NotApplicable ? (PanelTokens.BgSurface, PanelTokens.Line)
                : (PanelTokens.StatusReviewFill, PanelTokens.StatusReview);
            var callout = new C.Border
            {
                Child = inside, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
                Padding = new W.Thickness(10, 8, 10, 8), Margin = new W.Thickness(0, 10, 0, 0), Tag = CalloutTag,
            };
            callout.SetResourceReference(C.Border.BackgroundProperty, status.Item1);
            callout.SetResourceReference(C.Border.BorderBrushProperty, status.Item2);
            page.Children.Add(callout);
        }

        // what to do, plain numbered steps (change 29: the one button is the callout's)
        if (p.Steps.Count > 0)
        {
            page.Children.Add(Heading("What to do"));
            for (var i = 0; i < p.Steps.Count; i++)
            {
                var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 4) };
                var num = EntryView.Muted($"{i + 1}.");
                num.Width = 16;
                num.TextWrapping = W.TextWrapping.NoWrap;
                C.DockPanel.SetDock(num, C.Dock.Left);
                line.Children.Add(num);
                line.Children.Add(Body(p.Steps[i]));
                page.Children.Add(line);
            }
        }

        // measured against the limit, only when something was measured (change 31)
        if (p.ShowMeasured)
        {
            page.Children.Add(Heading("Measured against the limit"));
            foreach (var f in d.Figures)
                page.Children.Add(Figure(f));
            if (d.HowFar is not null)
                page.Children.Add(Pair("How far", d.HowFar, null));
            if (d.Bar is { } bar)
                page.Children.Add(Bar(bar, d.Status));
        }

        // what the code says: the first quote, Open the code at its page, the rest folded (change 30)
        page.Children.Add(Heading("What the code says"));
        if (p.FirstQuote is { } first)
            page.Children.Add(Quote(first));
        else if (d.NoQuote is not null)
            page.Children.Add(EntryView.Muted(d.NoQuote));
        if (p.Open is { } link0)
        {
            var open = Button(p.OpenWords!, link0.Url, () => host.OpenLaw(link0));
            open.HorizontalAlignment = W.HorizontalAlignment.Left;
            open.Margin = new W.Thickness(0, 0, 0, 4);
            page.Children.Add(open);
        }
        if (p.NoLink is not null)
            page.Children.Add(EntryView.Muted(p.NoLink));
        if (p.MoreWords is { } more)
        {
            var rest = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
            foreach (var q in p.MoreQuotes)
                rest.Children.Add(Quote(q));
            foreach (var l in p.OtherLinks)
            {
                var b = Button(DetailPages.OpenWords(l) + $" ({l.Citation})", l.Url, () => host.OpenLaw(l));
                b.HorizontalAlignment = W.HorizontalAlignment.Left;
                b.Margin = new W.Thickness(0, 0, 0, 4);
                rest.Children.Add(b);
            }
            page.Children.Add(new C.Expander { Header = more, Content = rest, Margin = new W.Thickness(0, 4, 0, 0) });
        }

        Elements(page, d, host);

        // the foot: the architect's own note (never a verdict), and the one key worth saying
        var foot = new C.DockPanel { Margin = new W.Thickness(0, 14, 0, 0) };
        var keys = EntryView.Muted("Ctrl+C copies");
        keys.ToolTip = "Backspace or Esc: back to the results. Alt+Up / Alt+Down: the previous or next result. Space: show it in the model.";
        keys.VerticalAlignment = W.VerticalAlignment.Center;
        C.DockPanel.SetDock(keys, C.Dock.Right);
        foot.Children.Add(keys);
        if (d.Tickable)
        {
            var tick = CauseCardsView.Tick(new CauseCardsView.TickTag(false, d.Id), host.DetailLooked, host.TickDetail, DetailPages.LookedLabel);
            tick.HorizontalAlignment = W.HorizontalAlignment.Left;
            foot.Children.Add(tick);
        }
        page.Children.Add(foot);
        return Scroll(page, d);
    }

    private static C.DockPanel TopBar(ResultDetail d, IDetailHost host, bool canStepBack, bool canStepOn)
    {
        var top = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 8) };
        var back = Button("‹ Back", "Back to the results, where you were (Backspace or Esc)", host.Back);
        C.DockPanel.SetDock(back, C.Dock.Left);
        top.Children.Add(back);
        var next = Button("›", "Next result (Alt+Down)", () => host.Step(1));
        next.IsEnabled = canStepOn;
        var prev = Button("‹", "Previous result (Alt+Up)", () => host.Step(-1));
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
        return top;
    }

    private static C.DockPanel Verdict(ResultDetail d)
    {
        var verdict = new C.DockPanel { Margin = new W.Thickness(0, 4, 0, 2) };
        var glyph = PanelLook.Glyph(d.Status, 16);
        glyph.Margin = new W.Thickness(0, 0, 6, 0);
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        verdict.Children.Add(glyph);
        verdict.Children.Add(EntryView.Ink(EntryView.Typed(new C.TextBlock
        {
            Text = d.VerdictWords.ToUpperInvariant(), TextWrapping = W.TextWrapping.Wrap, VerticalAlignment = W.VerticalAlignment.Center,
        }, "type.overline"), StatusLook.Colour(d.Status)));
        return verdict;
    }

    private static C.Border Quote(LawQuote q)
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
        return rule;
    }

    private static void Elements(C.StackPanel page, ResultDetail d, IDetailHost host)
    {
        if (d.Elements.Count == 0)
            return;
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

    private static C.ScrollViewer Scroll(C.StackPanel page, ResultDetail d)
    {
        var scroll = new C.ScrollViewer
        {
            Content = page, VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto,
            HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled, Focusable = true,
        };
        W.Automation.AutomationProperties.SetName(scroll, $"Detail: {StatusLook.Word(d.Status)}: {d.Name}");
        return scroll;
    }

    /// <summary>The page as it was before the UI polish (an answer without the two views: an older checker).</summary>
    private static W.FrameworkElement BuildOld(ResultDetail d, IDetailHost host, bool canStepBack, bool canStepOn)
    {
        var page = new C.StackPanel { Margin = new W.Thickness(12, 4, 12, 12) };

        // Back, then the row's place among the rows shown and Previous / Next
        var top = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 8) };
        var back = Button("‹ Back", "Back to the results, where you were (Backspace or Esc)", host.Back);
        C.DockPanel.SetDock(back, C.Dock.Left);
        top.Children.Add(back);
        var next = Button("›", "Next result (Alt+Down)", () => host.Step(1));
        next.IsEnabled = canStepOn;
        var prev = Button("‹", "Previous result (Alt+Up)", () => host.Step(-1));
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
        if (d.Tickable)
        {
            // the architect's own "looked at" (LookedAt): never a verdict, and it says so on hover
            var tick = CauseCardsView.Tick(new CauseCardsView.TickTag(false, d.Id), host.DetailLooked, host.TickDetail);
            tick.HorizontalAlignment = W.HorizontalAlignment.Left;
            tick.Margin = new W.Thickness(0, 6, 0, 0);
            page.Children.Add(tick);
        }

        if (d.Why is not null)
        {
            page.Children.Add(Heading(d.Status == PanelStatus.Review ? "Why it needs review" : "Why"));
            page.Children.Add(Body(PaneWords.Capital(d.Why)));
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
                // the generic step ("Resolve what the reason above says...") is the fix this result waits on, by its
                // number and title, with the fix's own button (Fixes.Step: the same words as on its card)
                if (host is ICauseHost causes && Fixes.For(causes.Groups, d.Id) is { } wait && Fixes.Step(d, causes.Groups, step) is not null)
                {
                    var fix = wait.Fix;
                    words.Children.Add(Body($"Fix {wait.Number}: {fix.Title}.", semi: true));
                    words.Children.Add(Body(Fixes.Note(fix)));
                    if (fix.Action != CardAction.None)
                    {
                        var go = CauseCardsView.Primary(Fixes.ButtonWords(fix.Action), () => causes.Act(fix, fix.Action));
                        go.HorizontalAlignment = W.HorizontalAlignment.Left;
                        go.Margin = new W.Thickness(0, 3, 0, 0);
                        words.Children.Add(go);
                    }
                    line.Children.Add(words);
                    page.Children.Add(line);
                    continue;
                }
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
        if (d.Bar is { } bar)
        {
            if (d.Figures.Count == 0 && d.HowFar is null)
                page.Children.Add(Heading("Measured against the limit"));
            page.Children.Add(Bar(bar, d.Status));
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
            page.Children.Add(EntryView.Muted("No link to the source was sent with this result: find it by the section and page above."));

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
        page.Children.Add(EntryView.Muted("Backspace or Esc: back to the results. Ctrl+C copies this result.", top: 12));

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
        DetailAction.CheckAgain => Button("Check again", "Check this project again: only the check changes a verdict", host.CheckAgain),   // one primary per screen: the header's (the intuitive pane, change 5)
        _ => null,
    };

    /// <summary>The measured-vs-limit bar (MeasureBar): a track the longer of the two lengths spans, filled to the length
    /// found, a mark at the limit, in the row's status colour (amber for a row in review; the clock's hatching once
    /// stale: never green unless the worker said it complies); the worker's words for both under it. The numbers only
    /// place the marks: no figure is shown that isn't the worker's.</summary>
    private static W.UIElement Bar(MeasureBar bar, PanelStatus status)
    {
        var box = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 6) };
        var track = new C.Grid { Height = 12, Margin = new W.Thickness(0, 0, 0, 3) };
        var back = new C.Border { BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(2) };
        back.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgHover);
        back.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        track.Children.Add(back);
        var fill = new C.Grid { Margin = new W.Thickness(1) };
        fill.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(bar.MeasuredAt, W.GridUnitType.Star) });
        fill.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(Math.Max(0, 1 - bar.MeasuredAt), W.GridUnitType.Star) });
        var found = new System.Windows.Shapes.Rectangle();
        found.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, status == PanelStatus.Stale ? PanelLook.StaleHatch : StatusLook.Colour(status));
        fill.Children.Add(found);
        track.Children.Add(fill);
        var limit = new C.Grid();
        limit.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(bar.LimitAt, W.GridUnitType.Star) });
        limit.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(Math.Max(0, 1 - bar.LimitAt), W.GridUnitType.Star) });
        var mark = new System.Windows.Shapes.Rectangle { Width = 3, HorizontalAlignment = W.HorizontalAlignment.Right, Margin = new W.Thickness(0, -2, -1, -2) };
        mark.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, PanelTokens.Text);
        limit.Children.Add(mark);
        track.Children.Add(limit);
        box.Children.Add(track);
        var side = bar.Side switch
        {
            LimitSide.AtLeast => "the limit: the length must reach it",
            LimitSide.AtMost => "the limit: the length must stay within it",
            _ => "the limit",
        };
        box.Children.Add(EntryView.Muted($"Bar: the length found; the dark mark is {side}."));
        box.Children.Add(EntryView.Typed(new C.TextBlock { Text = bar.Words, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 2, 0, 0) }, "type.figure"));
        W.Automation.AutomationProperties.SetName(box, "Measured against the limit: " + bar.Words);
        return box;
    }

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

    private static C.TextBlock Heading(string words, double top = 14) =>
        EntryView.Ink(EntryView.Typed(new C.TextBlock { Text = words.ToUpperInvariant(), Margin = new W.Thickness(0, top, 0, 4) }, "type.overline"),
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
