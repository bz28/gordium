using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using S = System.Windows.Shapes;

namespace Gordium.Revit.PanePrototype.Proposed;

/// <summary>What the cause cards ask of the panel that shows them (the ResultsView). PROTOTYPE: by card group.</summary>
internal interface ICauseHost
{
    /// <summary>The worker's cause cards joined where they share one fix, ranked (CardGroups).</summary>
    IReadOnlyList<CardGroup> Groups { get; }

    bool AllShown { get; }

    void ShowAllCards(bool all);

    bool IsOpen(CardGroup group);

    void SetOpen(CardGroup group, bool open);

    void Act(CardGroup group, CardAction action);

    void ShowRoom(CauseCard card, CauseRoom room);

    void OpenRow(string id);

    IReadOnlyDictionary<string, string>? Labels { get; }

    IReadOnlyList<ListRow> Placed { get; }

    bool Stale { get; }

    LookedAt Looked { get; }

    void TickCard(CardGroup group, bool ticked);

    void TickRow(ListRow row, bool ticked);
}

/// <summary>
/// PROTOTYPE of the proposed "Fix these first": the worker's cause cards joined where they share one fix (the same
/// field on many elements, every Project Information fact, one kind of part Gordium couldn't measure) and ranked by
/// what one action clears (CardGroups); at most three shown, the rest behind "+N more". Each card: what to do, how
/// many results wait on it, where the fix is made, ONE primary button whose words are the same everywhere (Show, Set
/// in Properties, Open Project Information, Measure by hand, Decide), and "See the N results" (each opens its
/// detail; a joined card lists its causes in the worker's own words first). Nothing here makes or changes a verdict.
/// </summary>
internal static class CauseCardsView
{
    internal sealed record TickTag(bool Card, string Key);

    internal const string ProgressTag = "looked.progress";

    internal static W.FrameworkElement Build(ICauseHost host)
    {
        var all = host.Groups;
        var panel = new C.StackPanel { Margin = new W.Thickness(0, 2, 0, 6) };
        var title = EntryView.Ink(EntryView.Typed(new C.TextBlock { Text = "START HERE", VerticalAlignment = W.VerticalAlignment.Center },
                                                  "type.overline"), PanelTokens.TextMuted);
        panel.Children.Add(title);
        var rows = all.SelectMany(g => g.Rows).Distinct().Count();
        panel.Children.Add(EntryView.Muted($"{all.Count} fix{(all.Count == 1 ? "" : "es")} cover the {rows} results that need review or a hand check. Start with {(all.Count <= CardGroups.Top ? "these" : $"these {CardGroups.Top}")}: what you can fix in Revit comes first."));
        var shown = host.AllShown ? all : all.Take(CardGroups.Top).ToList();
        var n = 0;
        foreach (var g in shown)
            panel.Children.Add(Card(g, ++n, host));
        var more = all.Count - CardGroups.Top;
        if (more > 0)
        {
            var toggle = Link(host.AllShown ? "Show only the first 3" : $"+{more} more {(more == 1 ? "fix" : "fixes")} ({all.Skip(CardGroups.Top).SelectMany(g => g.Rows).Distinct().Count()} results)",
                              () => host.ShowAllCards(!host.AllShown));
            toggle.Margin = new W.Thickness(0, 4, 0, 0);
            panel.Children.Add(toggle);
        }
        var ticked = all.Count(g => host.Looked.Card(g.Key));
        var progress = EntryView.Muted($"Looked at: {ticked} of {all.Count} fixes · {host.Looked.Rows.Count} of {host.Placed.Count(LookedAt.Tickable)} results", top: 6);
        progress.Tag = ProgressTag;
        progress.ToolTip = LookedAt.Tip;
        panel.Children.Add(progress);
        panel.MouseLeftButtonDown += (_, e) => e.Handled = true;
        return panel;
    }

    private static W.UIElement Card(CardGroup g, int number, ICauseHost host)
    {
        var status = StatusLook.Of(Tone.Review, host.Stale);                // results in review: never green
        var body = new C.StackPanel { Margin = new W.Thickness(10, 8, 10, 8) };

        var first = new C.DockPanel();
        var badge = new C.Border { Width = 18, Height = 18, CornerRadius = new W.CornerRadius(9), Margin = new W.Thickness(0, 0, 8, 0), VerticalAlignment = W.VerticalAlignment.Top };
        badge.SetResourceReference(C.Border.BackgroundProperty, StatusLook.Colour(status));
        var num = new C.TextBlock { Text = number.ToString(), FontSize = 11, FontWeight = W.FontWeights.SemiBold, HorizontalAlignment = W.HorizontalAlignment.Center, VerticalAlignment = W.VerticalAlignment.Center };
        num.SetResourceReference(C.TextBlock.ForegroundProperty, PanelTokens.BgSurface);
        badge.Child = num;
        C.DockPanel.SetDock(badge, C.Dock.Left);
        first.Children.Add(badge);
        first.Children.Add(EntryView.Typed(new C.TextBlock
        {
            Text = g.Title, TextWrapping = W.TextWrapping.Wrap, TextTrimming = W.TextTrimming.CharacterEllipsis,
            FontWeight = W.FontWeights.SemiBold, MaxHeight = 3 * 1.4 * PanelTokens.TypeOf("type.body").Size, ToolTip = g.Title,
        }, "type.body"));
        body.Children.Add(first);
        var countLine = new C.DockPanel { Margin = new W.Thickness(26, 2, 0, 0) };
        var tick = Tick(new TickTag(true, g.Key), host.Looked.Card(g.Key), t => host.TickCard(g, t));
        C.DockPanel.SetDock(tick, C.Dock.Right);
        countLine.Children.Add(tick);
        countLine.Children.Add(EntryView.Muted(g.Count));
        body.Children.Add(countLine);
        if (CardGroups.Note(g, host.Labels) is { } note)
            body.Children.Add(Indented(EntryView.Muted(note, top: 3)));

        var open = host.IsOpen(g);
        var buttons = new C.DockPanel { Margin = new W.Thickness(26, 7, 0, 0), LastChildFill = false };
        if (g.Action != CardAction.None)
        {
            var act = Primary(CardGroups.ButtonWords(g.Action), () => host.Act(g, g.Action));
            act.Margin = new W.Thickness(0, 0, 10, 0);
            C.DockPanel.SetDock(act, C.Dock.Left);
            buttons.Children.Add(act);
        }
        var see = Link(open ? "Hide results" : $"See the {g.Rows.Count} result{(g.Rows.Count == 1 ? "" : "s")}", () => host.SetOpen(g, !open));
        see.VerticalAlignment = W.VerticalAlignment.Center;
        C.DockPanel.SetDock(see, C.Dock.Left);
        buttons.Children.Add(see);
        body.Children.Add(buttons);
        if (open)
            body.Children.Add(Rows(g, host));

        var bar = new S.Rectangle { Width = 4 };
        bar.SetResourceReference(S.Shape.FillProperty, status == PanelStatus.Stale ? PanelLook.StaleHatch : StatusLook.Colour(status));
        var dock = new C.DockPanel();
        C.DockPanel.SetDock(bar, C.Dock.Left);
        dock.Children.Add(bar);
        dock.Children.Add(body);
        var frame = new C.Border { Child = dock, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4), Margin = new W.Thickness(0, 6, 0, 0) };
        frame.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        frame.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        W.Automation.AutomationProperties.SetName(frame, $"Cause: {g.Title}. {g.Count}");
        return frame;
    }

    /// <summary>An open card: a joined card's causes (the worker's words, each with how many results), the rooms
    /// a cause names (each with Show), then every result it is for, each opening its detail.</summary>
    private static W.UIElement Rows(CardGroup g, ICauseHost host)
    {
        var list = new C.StackPanel { Margin = new W.Thickness(26, 6, 0, 0) };
        if (g.Members.Count > 1)
        {
            list.Children.Add(Overline($"The {g.Members.Count} {g.Noun}, in Gordium's checker's words"));
            foreach (var m in g.Members)
                list.Children.Add(EntryView.Muted($"• {CardGroups.Capital(m.Words)} ({m.Items.Count} result{(m.Items.Count == 1 ? "" : "s")})", bottom: 2));
        }
        foreach (var card in g.Members.Where(m => m.Rooms.Count > 0))
        {
            list.Children.Add(Overline($"The {card.Rooms.Count} room{(card.Rooms.Count == 1 ? "" : "s")}"));
            foreach (var room in card.Rooms)
            {
                var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 4) };
                if (host.Labels?.ContainsKey(room.Id) == true)
                {
                    var show = Secondary("Show", () => host.ShowRoom(card, room));
                    show.VerticalAlignment = W.VerticalAlignment.Top;
                    show.Margin = new W.Thickness(6, 0, 0, 0);
                    C.DockPanel.SetDock(show, C.Dock.Right);
                    line.Children.Add(show);
                }
                var said = new C.StackPanel();
                said.Children.Add(EntryView.Typed(new C.TextBlock { Text = room.Name, TextWrapping = W.TextWrapping.Wrap, FontWeight = W.FontWeights.SemiBold }, "type.body"));
                if (room.Why is not null)
                    said.Children.Add(EntryView.Muted(CardGroups.Capital(room.Why)));
                line.Children.Add(said);
                list.Children.Add(line);
            }
        }
        list.Children.Add(Overline($"The {g.Rows.Count} result{(g.Rows.Count == 1 ? "" : "s")} waiting on this"));
        var placed = host.Placed.ToDictionary(p => p.Row.Id, StringComparer.Ordinal);
        foreach (var id in g.Rows)
        {
            if (!placed.TryGetValue(id, out var row))
                continue;
            var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 3) };
            var glyph = PanelLook.Glyph(row.Status, 11);
            glyph.Margin = new W.Thickness(0, 3, 5, 0);
            glyph.VerticalAlignment = W.VerticalAlignment.Top;
            C.DockPanel.SetDock(glyph, C.Dock.Left);
            line.Children.Add(glyph);
            var link = Link(row.Row.Name, () => host.OpenRow(id));
            link.ToolTip = "Open it: why, what to do, the law's words";
            line.Children.Add(link);
            list.Children.Add(line);
        }
        return list;
    }

    internal static C.CheckBox Tick(TickTag tag, bool ticked, Action<bool> changed, string words = "Looked at")
    {
        var box = new C.CheckBox { IsChecked = ticked, Tag = tag, ToolTip = LookedAt.Tip, VerticalAlignment = W.VerticalAlignment.Center, Focusable = true };
        if (words.Length > 0)
            box.Content = words;
        W.Automation.AutomationProperties.SetName(box, words.Length > 0 ? words : "Looked at");
        box.Click += (_, e) =>
        {
            e.Handled = true;
            changed(box.IsChecked == true);
        };
        return box;
    }

    private static C.TextBlock Overline(string words) =>
        EntryView.Ink(EntryView.Typed(new C.TextBlock { Text = words.ToUpperInvariant(), Margin = new W.Thickness(0, 6, 0, 3), TextWrapping = W.TextWrapping.Wrap }, "type.overline"),
                      PanelTokens.TextMuted);

    private static W.FrameworkElement Indented(W.FrameworkElement e)
    {
        e.Margin = new W.Thickness(26 + e.Margin.Left, e.Margin.Top, e.Margin.Right, e.Margin.Bottom);
        return e;
    }

    /// <summary>The card's one action: the panel's primary style (one style per kind of control, everywhere).</summary>
    internal static C.Button Primary(string words, Action click)
    {
        var b = new C.Button { Content = words, Padding = new W.Thickness(10, 2, 10, 3) };
        b.SetResourceReference(W.FrameworkElement.StyleProperty, "button.primary");
        W.Automation.AutomationProperties.SetName(b, words);
        b.Click += (_, e) =>
        {
            e.Handled = true;
            click();
        };
        return b;
    }

    /// <summary>A secondary action on one thing (Show a room, Show an element): the plain button style.</summary>
    internal static C.Button Secondary(string words, Action click)
    {
        var b = new C.Button { Content = words, Padding = new W.Thickness(8, 1, 8, 1) };
        W.Automation.AutomationProperties.SetName(b, words);
        b.Click += (_, e) =>
        {
            e.Handled = true;
            click();
        };
        return b;
    }

    /// <summary>Going somewhere in the pane (a result's detail, more fixes): a link, never a button.</summary>
    internal static C.Button Link(string words, Action click)
    {
        var link = new C.Button
        {
            Content = new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap, TextDecorations = W.TextDecorations.Underline },
            Padding = new W.Thickness(0), BorderThickness = new W.Thickness(0), Background = System.Windows.Media.Brushes.Transparent,
            HorizontalContentAlignment = W.HorizontalAlignment.Left, HorizontalAlignment = W.HorizontalAlignment.Left, Cursor = W.Input.Cursors.Hand,
        };
        link.SetResourceReference(C.Control.ForegroundProperty, PanelTokens.Accent);
        W.Automation.AutomationProperties.SetName(link, words);
        link.Click += (_, e) =>
        {
            e.Handled = true;
            click();
        };
        return link;
    }
}
