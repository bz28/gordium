using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;

namespace Gordium.Revit.Addin;

/// <summary>What the Setup form asks Revit (or the flow) to do: each queued for Revit's thread by
/// <see cref="SetupRun"/>, never a Revit call here.</summary>
internal sealed record SetupHandlers(
    Action<MarkDefinition, string> Choose,
    Action Save,
    Action Discard,
    Action<IReadOnlyList<Suggestion>> Accept,
    Action<IReadOnlyList<string>> Select,
    Action PickStreet,
    Action Anyway,
    Action ProjectInformation);

/// <summary>
/// The Setup form in the Gordium pane (docs/decisions/2026-11-22_setup_form.md): the project facts as a real form
/// (dropdowns for a known list, Yes/No toggles, a number, Pick on plan for the street edge), each with the law it
/// answers; then the facts inside the building as a checklist, a line per fact with its counts, Select them, and the
/// suggestions with what each is based on, done lines folded away. Every choice stays in the draft
/// (<see cref="SetupDraft"/>) until Save writes them, in one transaction; a suggestion is written only by its Accept.
/// Drawn from <see cref="SetupScreen"/> (Gordium.Revit.Reading decides everything); plain WPF in the panel's tokens.
/// </summary>
internal sealed class SetupView : C.StackPanel
{
    private const string Body = "type.body";
    private const string Caption = "type.caption";

    private readonly SetupScreen _screen;
    private readonly SetupDraft _draft;
    private readonly SetupHandlers _do;
    private readonly HashSet<string> _open;

    /// <param name="screen">What to show.</param>
    /// <param name="draft">The architect's choices not saved yet.</param>
    /// <param name="handlers">The actions.</param>
    /// <param name="notice">Why the form is shown now (a check refused), or null.</param>
    /// <param name="open">The headings and suggestion lists the architect opened (kept across every redraw).</param>
    internal SetupView(SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open)
    {
        _screen = screen;
        _draft = draft;
        _do = handlers;
        _open = open;
        Margin = new W.Thickness(12, 4, 12, 12);
        Head(notice);
        Facts();
        Checklist();
    }

    // ---- the head: what is left, and Check now anyway ----------------------------------------------------------

    private void Head(string? notice)
    {
        if (notice is { Length: > 0 })
            Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                Words(notice, Body, wrap: true), bottom: 6));
        var headline = Words(_screen.Headline, "type.title", wrap: true);
        if (_screen.Ready)
            Children.Add(headline);
        else
            Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, headline, bottom: 4));
        Children.Add(Muted("Gordium writes only what you choose, when you click Save or Accept: one undo step each (Ctrl+Z). " +
                           "When everything needed is set, the check runs by itself.", top: 2, bottom: 6));
        var anyway = Button("Check now anyway", primary: false,
            "Check with what is set now: each fact still missing makes the rules it decides need review, never a pass");
        anyway.HorizontalAlignment = W.HorizontalAlignment.Left;
        anyway.Click += (_, _) => _do.Anyway();
        Children.Add(anyway);
    }

    // ---- the project facts -------------------------------------------------------------------------------------

    private void Facts()
    {
        Children.Add(Overline("PROJECT FACTS · ON PROJECT INFORMATION", top: 14));
        foreach (var group in _screen.Fields.GroupBy(f => f.Group))
        {
            var fields = group.ToList();
            var panel = new C.StackPanel();
            foreach (var f in fields)
                panel.Children.Add(Field(f));
            if (group.Key == SetupFacts.NeededGroup)
            {
                Children.Add(Words(group.Key, "type.title", top: 6));
                Children.Add(panel);
                continue;
            }
            var set = fields.Count(f => f.IsSet || _draft.Chosen(f.Mark) is not null);
            Children.Add(Fold("group:" + group.Key, $"{group.Key} ({set} of {fields.Count} set)", panel, top: 6));
        }
        var changes = _screen.Fields.Count(f => _draft.Chosen(f.Mark) is { } c && c != f.Current);
        var line = new C.WrapPanel { Margin = new W.Thickness(0, 10, 0, 0) };
        var save = Button(changes == 0 ? "Save" : $"Save {changes} {(changes == 1 ? "change" : "changes")}", primary: true,
                          $"Writes what you chose to Project Information, as one undo step ({SetupWrites.FactsTransaction})");
        save.IsEnabled = changes > 0;
        save.Click += (_, _) => _do.Save();
        line.Children.Add(save);
        if (changes > 0)
        {
            var discard = Button("Discard", primary: false, "Forget the choices not saved: the fields show what Project Information holds");
            discard.Margin = new W.Thickness(6, 0, 0, 0);
            discard.Click += (_, _) => _do.Discard();
            line.Children.Add(discard);
        }
        var info = Button("Project Information", primary: false, "Open Revit's Project Information (every field, Gordium's among them)");
        info.Margin = new W.Thickness(6, 0, 0, 0);
        info.Click += (_, _) => _do.ProjectInformation();
        line.Children.Add(info);
        Children.Add(line);
    }

    private W.UIElement Field(SetupField f)
    {
        var box = new C.StackPanel { Margin = new W.Thickness(0, 6, 0, 2) };
        var chosen = _draft.Chosen(f.Mark);
        var shown = chosen ?? f.Current;
        var title = new C.WrapPanel();
        title.Children.Add(Words(f.Label, Body, semibold: true));
        if (f.Required && !f.IsSet && chosen is null)
            title.Children.Add(Ink(Words("  needed", Caption), PanelTokens.StatusReview));
        if (chosen is not null && chosen != f.Current)
            title.Children.Add(Ink(Words("  not saved yet", Caption), PanelTokens.Accent));
        box.Children.Add(title);
        switch (f.Kind)
        {
            case FieldKind.Choice:
            {
                var combo = new C.ComboBox { Margin = new W.Thickness(0, 3, 0, 0), MaxDropDownHeight = 260, IsEditable = false };
                W.Automation.AutomationProperties.SetName(combo, f.Label);
                foreach (var c in f.Choices)
                    combo.Items.Add(new C.ComboBoxItem { Content = c.Label, Tag = c.Value, ToolTip = c.Value });
                var at = f.Choices.ToList().FindIndex(c => c.Value == shown);
                combo.SelectedIndex = at;
                // only the architect's own pick is a choice: setting the shown value above is not
                combo.SelectionChanged += (_, _) =>
                {
                    if (combo.SelectedItem is C.ComboBoxItem { Tag: string value })
                        _do.Choose(f.Mark, value);
                };
                // nothing chosen: says so in the box (never a value shown that isn't the mark's or the architect's)
                var hint = Muted(f.Mark == Marks.Zone ? "Choose the district" : f.Mark == Marks.Use ? "Choose the use" : "Choose one");
                hint.IsHitTestVisible = false;
                hint.Margin = new W.Thickness(7, 6, 24, 0);
                hint.Visibility = at < 0 ? W.Visibility.Visible : W.Visibility.Collapsed;
                var grid = new C.Grid();
                grid.Children.Add(combo);
                grid.Children.Add(hint);
                box.Children.Add(grid);
                break;
            }
            case FieldKind.YesNo:
            {
                var row = new C.StackPanel { Orientation = C.Orientation.Horizontal, Margin = new W.Thickness(0, 3, 0, 0) };
                foreach (var word in new[] { "Yes", "No" })
                {
                    var t = new C.Primitives.ToggleButton { Content = word, IsChecked = shown == word, MinWidth = 54, Margin = new W.Thickness(0, 0, 4, 0) };
                    W.Automation.AutomationProperties.SetName(t, $"{f.Label}: {word}");
                    t.Click += (_, _) => _do.Choose(f.Mark, word);
                    row.Children.Add(t);
                }
                if (shown is null)
                    row.Children.Add(Muted("not stated", top: 4));
                box.Children.Add(row);
                break;
            }
            case FieldKind.Number:
            case FieldKind.Text:
            {
                var text = new C.TextBox { Text = shown ?? "", Margin = new W.Thickness(0, 3, 0, 0), MaxWidth = f.Kind == FieldKind.Number ? 90 : double.PositiveInfinity,
                                           HorizontalAlignment = f.Kind == FieldKind.Number ? W.HorizontalAlignment.Left : W.HorizontalAlignment.Stretch };
                W.Automation.AutomationProperties.SetName(text, f.Label);
                // a choice on leaving the box or Enter, only when the text differs from what is shown
                void Commit()
                {
                    if (text.Text.Trim() != (shown ?? ""))
                        _do.Choose(f.Mark, text.Text);
                }
                text.LostKeyboardFocus += (_, _) => Commit();
                text.KeyDown += (_, e) =>
                {
                    if (e.Key == System.Windows.Input.Key.Enter)
                        Commit();
                };
                box.Children.Add(text);
                break;
            }
            case FieldKind.StreetPick:
            {
                var row = new C.DockPanel { Margin = new W.Thickness(0, 3, 0, 0) };
                var pick = Button(f.Current is null ? "Pick on plan" : "Pick again", primary: false,
                                  "Click the lot edge along the street in a site or floor plan that shows the property line");
                C.DockPanel.SetDock(pick, C.Dock.Right);
                pick.Click += (_, _) => _do.PickStreet();
                row.Children.Add(pick);
                row.Children.Add(Words(f.Current is null ? "Not picked" : f.Problem is null ? "Picked (kept on Project Information)" : "Can't be read",
                                       Body, top: 3));
                box.Children.Add(row);
                break;
            }
        }
        if (f.Problem is not null)
            box.Children.Add(Ink(Words(f.Problem, Caption, wrap: true, top: 2), PanelTokens.StatusReview));
        // the law it answers: two lines, the whole on hover
        var law = Muted(f.Law, top: 2);
        law.TextTrimming = W.TextTrimming.CharacterEllipsis;
        law.MaxHeight = 2 * 1.4 * PanelTokens.TypeOf(Caption).Size;
        law.ToolTip = new C.TextBlock { Text = f.Law, TextWrapping = W.TextWrapping.Wrap, MaxWidth = 360 };
        box.Children.Add(law);
        return box;
    }

    // ---- the checklist -----------------------------------------------------------------------------------------

    private void Checklist()
    {
        Children.Add(Overline($"INSIDE THE {_screen.Noun.ToUpperInvariant()}", top: 16));
        foreach (var p in _screen.FixFirst)
            Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, Words(p, Caption, wrap: true), bottom: 4));
        var todo = _screen.Lines.Where(l => !l.Done).OrderByDescending(l => l.Needed).ToList();
        var done = _screen.Lines.Where(l => l.Done).ToList();
        foreach (var l in todo)
            Children.Add(Line(l));
        if (done.Count > 0)
        {
            var folded = new C.StackPanel();
            foreach (var l in done)
                folded.Children.Add(Line(l));
            Children.Add(Fold("done", $"Done ({done.Count})", folded, top: 8));
        }
    }

    private W.UIElement Line(ChecklistLine l)
    {
        var box = new C.StackPanel { Margin = new W.Thickness(0, 8, 0, 4) };
        W.UIElement count = Words(l.Count, Body, semibold: true, wrap: true);
        if (l.Done)
        {
            var tick = Ink(Words("✓ ", Body, semibold: true), PanelTokens.Marked);
            var row = new C.DockPanel();
            C.DockPanel.SetDock(tick, C.Dock.Left);
            row.Children.Add(tick);
            row.Children.Add(count);
            box.Children.Add(row);
        }
        else
            box.Children.Add(l.Needed ? WithGlyph(PanelStatus.Review, count, 14) : count);
        if (!l.Done)
        {
            var what = (l.Needed ? "Needed: " : "") + l.IfBlank;
            box.Children.Add(Muted(what, top: 2));
        }
        var why = Muted("Why Gordium asks: " + l.WhyAsked, top: 2);
        box.Children.Add(why);
        var actions = new C.WrapPanel { Margin = new W.Thickness(0, 4, 0, 0) };
        if (l.Unset.Count > 0)
        {
            var select = Button($"Select {(l.PerType ? "their" : "the")} {l.Unset.Count}", primary: false,
                                l.PerType ? "Selects every element of the types not set: set it once per type with Edit Type in Properties"
                                          : "Selects them in Revit: set them together in Properties");
            select.Click += (_, _) => _do.Select(l.Unset);
            actions.Children.Add(select);
        }
        if (l.Suggestions.Count > 0)
        {
            var all = Button($"Accept {l.Suggestions.Count} {(l.Suggestions.Count == 1 ? "suggestion" : "suggestions")}", primary: false,
                             "Writes every suggestion listed below, as one undo step: read what each is based on first");
            all.Margin = new W.Thickness(6, 0, 0, 0);
            all.Click += (_, _) => _do.Accept(l.Suggestions);
            actions.Children.Add(all);
        }
        if (actions.Children.Count > 0)
            box.Children.Add(actions);
        if (l.Suggestions.Count > 0)
        {
            var list = new C.StackPanel();
            foreach (var s in l.Suggestions)
                list.Children.Add(SuggestionRow(s));
            box.Children.Add(Fold("suggest:" + l.Key, $"Suggestions ({l.Suggestions.Count}): what each is based on", list, top: 4));
        }
        if (l.Notes.Count > 0)
        {
            var notes = new C.StackPanel();
            foreach (var n in l.Notes)
                notes.Children.Add(Muted(n, top: 2));
            box.Children.Add(Fold("notes:" + l.Key, $"What Gordium holds ({l.Notes.Count})", notes, top: 4));
        }
        return box;
    }

    private W.UIElement SuggestionRow(Suggestion s)
    {
        var row = new C.DockPanel { Margin = new W.Thickness(0, 4, 0, 2) };
        var accept = Button("Accept", primary: false, $"Writes {s.Mark.Name} = {s.Words} on {s.Label} (one undo step)");
        accept.Padding = new W.Thickness(8, 1, 8, 1);
        accept.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(accept, C.Dock.Right);
        accept.Click += (_, _) => _do.Accept([s]);
        row.Children.Add(accept);
        var words = new C.StackPanel { Margin = new W.Thickness(0, 0, 6, 0) };
        words.Children.Add(Words($"{s.Label}: {s.Words}", Caption, semibold: true, wrap: true));
        words.Children.Add(Muted("Based on: " + s.Basis));
        row.Children.Add(words);
        return row;
    }

    // ---- small pieces ------------------------------------------------------------------------------------------

    private C.Expander Fold(string key, string header, W.UIElement content, double top)
    {
        var e = new C.Expander { Header = header, IsExpanded = _open.Contains(key), Content = content, Margin = new W.Thickness(0, top, 0, 0) };
        e.Expanded += (_, _) => _open.Add(key);
        e.Collapsed += (_, _) => _open.Remove(key);
        return e;
    }

    private static C.Button Button(string words, bool primary, string tip)
    {
        var b = new C.Button { Content = words, Padding = new W.Thickness(10, 2, 10, 2), ToolTip = tip, Margin = new W.Thickness(0, 2, 0, 2) };
        if (primary)
            b.SetResourceReference(StyleProperty, "button.primary");
        W.Automation.AutomationProperties.SetName(b, words);
        return b;
    }

    private static C.TextBlock Words(string text, string token, bool semibold = false, bool wrap = false, double top = 0)
    {
        var t = EntryView.Typed(new C.TextBlock { Text = text, Margin = new W.Thickness(0, top, 0, 0) }, token);
        if (semibold)
            t.FontWeight = W.FontWeights.SemiBold;
        if (wrap)
            t.TextWrapping = W.TextWrapping.Wrap;
        return t;
    }

    private static C.TextBlock Ink(C.TextBlock t, string token) => EntryView.Ink(t, token);

    private static C.TextBlock Muted(string text, double top = 0, double bottom = 0) => EntryView.Muted(text, top, bottom);

    private static C.TextBlock Overline(string text, double top)
    {
        var t = Ink(Words(text, "type.overline", top: top), PanelTokens.TextMuted);
        t.Margin = new W.Thickness(0, top, 0, 2);
        return t;
    }

    private static C.DockPanel WithGlyph(PanelStatus status, W.UIElement words, double size)
    {
        var glyph = PanelLook.Glyph(status, size);
        glyph.Margin = new W.Thickness(0, 1, 6, 0);
        glyph.VerticalAlignment = W.VerticalAlignment.Top;
        var line = new C.DockPanel { LastChildFill = true };
        C.DockPanel.SetDock(glyph, C.Dock.Left);
        line.Children.Add(glyph);
        line.Children.Add(words);
        return line;
    }

    private static C.Border Banner(PanelStatus status, string fill, string outline, W.UIElement words, double bottom)
    {
        var b = new C.Border
        {
            Child = WithGlyph(status, words, 16), BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Padding = new W.Thickness(8, 5, 8, 5), Margin = new W.Thickness(0, 0, 0, bottom),
        };
        b.SetResourceReference(C.Border.BackgroundProperty, fill);
        b.SetResourceReference(C.Border.BorderBrushProperty, outline);
        return b;
    }
}
