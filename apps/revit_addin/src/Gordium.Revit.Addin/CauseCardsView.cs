using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using S = System.Windows.Shapes;

namespace Gordium.Revit.Addin;

/// <summary>What the cause cards ask of the panel that shows them (the ResultsView).</summary>
internal interface ICauseHost
{
    /// <summary>The cards shown and every card (for "+N more causes").</summary>
    IReadOnlyList<CauseCard> AllCards { get; }

    /// <summary>Whether every card is shown ("+N more causes" opened).</summary>
    bool AllShown { get; }

    /// <summary>"+N more causes" or "Fewer causes" clicked.</summary>
    void ShowAllCards(bool all);

    /// <summary>Whether a card is open on its rows.</summary>
    bool IsOpen(CauseCard card);

    /// <summary>A card opened or closed.</summary>
    void SetOpen(CauseCard card, bool open);

    /// <summary>The card's button (CauseCards.Action).</summary>
    void Act(CauseCard card, CardAction action);

    /// <summary>Show one room the card names (select and zoom).</summary>
    void ShowRoom(CauseCard card, CauseRoom room);

    /// <summary>A row of a card: its detail opened.</summary>
    void OpenRow(string id);

    /// <summary>The project's element names, by UniqueId (what the card's elements are called).</summary>
    IReadOnlyDictionary<string, string>? Labels { get; }

    /// <summary>The rows placed (a card's rows by id), and whether the results are stale.</summary>
    IReadOnlyList<ListRow> Placed { get; }

    bool Stale { get; }

    /// <summary>The "looked at" ticks, and a tick changed.</summary>
    LookedAt Looked { get; }

    void TickCard(CauseCard card, bool ticked);

    void TickRow(ListRow row, bool ticked);
}

/// <summary>
/// "Fix these first" (docs/revit/ui_design_pass.md section 2.4, PR 6): at the top of the needs-review part, at most
/// three of the worker's cause cards (the rest behind "+N more causes"), each its words, how many rows it holds, the
/// mark to set where it names one, its one button (Show; Show and open Properties; Open Project Information; Check by
/// hand; Decide), "looked at", and its rows, which open their details. Every decision is CauseCards' and LookedAt's
/// (Revit-free, tested); every colour a token; every status its glyph. Nothing here makes or changes a verdict.
/// </summary>
internal static class CauseCardsView
{
    /// <summary>The tag of a tick, so a tick made elsewhere (the row in the list, the detail) is shown here too.</summary>
    internal sealed record TickTag(bool Card, string Key);

    /// <summary>The tag of the progress line.</summary>
    internal const string ProgressTag = "looked.progress";

    internal static W.FrameworkElement Build(ICauseHost host)
    {
        var all = host.AllCards;
        var panel = new C.StackPanel { Margin = new W.Thickness(0, 2, 0, 6) };
        var head = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 4) };
        var title = EntryView.Ink(EntryView.Typed(new C.TextBlock { Text = "FIX THESE FIRST", VerticalAlignment = W.VerticalAlignment.Center },
                                                  "type.overline"), PanelTokens.TextMuted);
        C.DockPanel.SetDock(title, C.Dock.Left);
        head.Children.Add(title);
        panel.Children.Add(head);
        var progress = EntryView.Muted(host.Looked.Progress(all, host.Placed));
        progress.Tag = ProgressTag;
        progress.ToolTip = LookedAt.Tip;
        panel.Children.Add(progress);
        foreach (var card in CauseCards.Shown(all, host.AllShown))
            panel.Children.Add(Card(card, host));
        if (CauseCards.MoreWords(all) is { } more)
        {
            var toggle = Button(host.AllShown ? "Fewer causes" : more,
                                host.AllShown ? $"Show only the first {CauseCards.Top}" : "Show every cause the checker grouped the rows by",
                                () => host.ShowAllCards(!host.AllShown));
            toggle.HorizontalAlignment = W.HorizontalAlignment.Left;
            toggle.Margin = new W.Thickness(0, 2, 0, 0);
            panel.Children.Add(toggle);
        }
        panel.MouseLeftButtonDown += (_, e) => e.Handled = true;             // never a list selection
        return panel;
    }

    private static W.UIElement Card(CauseCard card, ICauseHost host)
    {
        var status = StatusLook.Of(Tone.Review, host.Stale);                // a cause is of rows in review: never green
        var body = new C.StackPanel { Margin = new W.Thickness(8, 6, 8, 7) };

        // its words, at most three lines (the whole on hover and in the rows below)
        var words = EntryView.Typed(new C.TextBlock
        {
            Text = card.Words, TextWrapping = W.TextWrapping.Wrap, TextTrimming = W.TextTrimming.CharacterEllipsis,
            FontWeight = W.FontWeights.SemiBold, MaxHeight = 3 * 1.4 * PanelTokens.TypeOf("type.body").Size, ToolTip = card.Words,
        }, "type.body");
        var first = new C.DockPanel();
        var glyph = PanelLook.Glyph(status, 12);
        glyph.Margin = new W.Thickness(0, 2, 6, 0);
        glyph.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        first.Children.Add(glyph);
        first.Children.Add(words);
        body.Children.Add(first);

        // how many rows, and the looked-at tick
        var count = new C.DockPanel { Margin = new W.Thickness(18, 3, 0, 0) };
        var tick = Tick(new TickTag(true, card.Key), host.Looked.Card(card.Key), t => host.TickCard(card, t));
        C.DockPanel.SetDock(tick, C.Dock.Right);
        count.Children.Add(tick);
        var n = EntryView.Muted(card.Count);
        n.VerticalAlignment = W.VerticalAlignment.Center;
        count.Children.Add(n);
        body.Children.Add(count);

        if (CauseCards.Note(card, host.Labels) is { } note)
            body.Children.Add(Indented(EntryView.Muted(note, top: 3)));

        // its one action, then its rows
        var open = host.IsOpen(card);
        var buttons = new C.WrapPanel { Margin = new W.Thickness(18, 5, 0, 0) };
        var action = CauseCards.Action(card, host.Labels);
        if (action != CardAction.None)
        {
            var act = Button(CauseCards.ButtonWords(action), Tip(card, action, host.Labels), () => host.Act(card, action));
            act.Margin = new W.Thickness(0, 0, 6, 4);
            buttons.Children.Add(act);
        }
        var rows = Button((open ? "Hide rows" : "Rows") + $" ({card.Items.Count})", open ? "Fold its rows" : "List its rows (each opens its detail)",
                          () => host.SetOpen(card, !open));
        rows.Margin = new W.Thickness(0, 0, 0, 4);
        buttons.Children.Add(rows);
        body.Children.Add(buttons);
        if (open)
            body.Children.Add(Rows(card, host));

        var bar = new S.Rectangle { Width = 4 };
        bar.SetResourceReference(S.Shape.FillProperty, status == PanelStatus.Stale ? PanelLook.StaleHatch : StatusLook.Colour(status));
        var dock = new C.DockPanel();
        C.DockPanel.SetDock(bar, C.Dock.Left);
        dock.Children.Add(bar);
        dock.Children.Add(body);
        var frame = new C.Border { Child = dock, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4), Margin = new W.Thickness(0, 4, 0, 2) };
        frame.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        frame.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        W.Automation.AutomationProperties.SetName(frame, $"Cause: {card.Words}. {card.Count}");
        return frame;
    }

    /// <summary>An open card: the rooms it names (each with why and Show), then its rows, each its tick and a link to
    /// its detail.</summary>
    private static W.UIElement Rows(CauseCard card, ICauseHost host)
    {
        var list = new C.StackPanel { Margin = new W.Thickness(18, 4, 0, 0) };
        if (card.Rooms.Count > 0)
        {
            list.Children.Add(Overline($"The {card.Rooms.Count} room{(card.Rooms.Count == 1 ? "" : "s")}"));
            foreach (var room in card.Rooms)
            {
                var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 4) };
                if (host.Labels?.ContainsKey(room.Id) == true)
                {
                    var show = Button("Show", $"Select and zoom to {room.Name}", () => host.ShowRoom(card, room));
                    show.VerticalAlignment = W.VerticalAlignment.Top;
                    show.Margin = new W.Thickness(6, 0, 0, 0);
                    C.DockPanel.SetDock(show, C.Dock.Right);
                    line.Children.Add(show);
                }
                var said = new C.StackPanel();
                said.Children.Add(EntryView.Typed(new C.TextBlock { Text = room.Name, TextWrapping = W.TextWrapping.Wrap, FontWeight = W.FontWeights.SemiBold }, "type.body"));
                if (room.Why is not null)
                    said.Children.Add(EntryView.Muted(room.Why));
                line.Children.Add(said);
                list.Children.Add(line);
            }
        }
        list.Children.Add(Overline($"Its {card.Items.Count} row{(card.Items.Count == 1 ? "" : "s")}"));
        var placed = host.Placed.ToDictionary(p => p.Row.Id, StringComparer.Ordinal);
        foreach (var id in card.Items)
        {
            if (!placed.TryGetValue(id, out var row))
                continue;
            var line = new C.DockPanel { Margin = new W.Thickness(0, 0, 0, 3) };
            if (LookedAt.Tickable(row))
            {
                var tick = Tick(new TickTag(false, id), host.Looked.Row(id), t => host.TickRow(row, t), words: "");
                tick.VerticalAlignment = W.VerticalAlignment.Top;
                tick.Margin = new W.Thickness(0, 2, 6, 0);
                W.Automation.AutomationProperties.SetName(tick, "Looked at: " + row.Row.Name);
                C.DockPanel.SetDock(tick, C.Dock.Left);
                line.Children.Add(tick);
            }
            var glyph = PanelLook.Glyph(row.Status, 11);
            glyph.Margin = new W.Thickness(0, 3, 5, 0);
            glyph.VerticalAlignment = W.VerticalAlignment.Top;
            C.DockPanel.SetDock(glyph, C.Dock.Left);
            line.Children.Add(glyph);
            var link = new C.Button
            {
                Content = new C.TextBlock { Text = row.Row.Name, TextWrapping = W.TextWrapping.Wrap },
                Padding = new W.Thickness(0), BorderThickness = new W.Thickness(0), Background = W.Media.Brushes.Transparent,
                HorizontalContentAlignment = W.HorizontalAlignment.Left, HorizontalAlignment = W.HorizontalAlignment.Left,
                ToolTip = "Open its detail: why, what to do, the law's words", Cursor = W.Input.Cursors.Hand,
            };
            link.SetResourceReference(C.Control.ForegroundProperty, PanelTokens.Accent);
            W.Automation.AutomationProperties.SetName(link, "Open " + row.Row.Name);
            link.Click += (_, e) =>
            {
                e.Handled = true;
                host.OpenRow(id);
            };
            line.Children.Add(link);
            list.Children.Add(line);
        }
        return list;
    }

    private static string Tip(CauseCard card, CardAction action, IReadOnlyDictionary<string, string>? labels)
    {
        var shown = CauseCards.InModel(card, labels);
        var names = string.Join(", ", shown.Take(5).Select(u => labels![u])) + (shown.Count > 5 ? $" and {shown.Count - 5} more" : "");
        return action switch
        {
            CardAction.Show => $"Select and zoom to {names}",
            CardAction.ShowAndProperties => $"Select {names} and bring up Properties",
            CardAction.ProjectInformation => "Open Manage › Project Information",
            CardAction.ByHand => "List its rows: check each by hand against the law's words in its detail",
            _ => "List its rows and what a person decides",
        };
    }

    /// <summary>A "looked at" tick: the architect's own note, never a verdict (its tooltip says so).</summary>
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
        EntryView.Ink(EntryView.Typed(new C.TextBlock { Text = words.ToUpperInvariant(), Margin = new W.Thickness(0, 4, 0, 3) }, "type.overline"),
                      PanelTokens.TextMuted);

    private static W.FrameworkElement Indented(W.FrameworkElement e)
    {
        e.Margin = new W.Thickness(18 + e.Margin.Left, e.Margin.Top, e.Margin.Right, e.Margin.Bottom);
        return e;
    }

    private static C.Button Button(string words, string tip, Action click)
    {
        var b = new C.Button
        {
            Content = new C.TextBlock { Text = words, TextWrapping = W.TextWrapping.Wrap }, Padding = new W.Thickness(8, 1, 8, 1),
            ToolTip = tip, HorizontalContentAlignment = W.HorizontalAlignment.Left,
        };
        W.Automation.AutomationProperties.SetName(b, words);
        b.Click += (_, e) =>
        {
            e.Handled = true;
            click();
        };
        return b;
    }
}
