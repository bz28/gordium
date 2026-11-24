using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;
using S = System.Windows.Shapes;

namespace Gordium.Revit.Addin;

/// <summary>What the Setup form asks Revit (or the flow) to do: each queued for Revit's thread by
/// <see cref="SetupRun"/>, never a Revit call here.</summary>
internal sealed record SetupHandlers(
    Action<MarkDefinition, string> Choose,
    Action<MarkDefinition, string> Type,
    Action Save,
    Action Discard,
    Action<IReadOnlyList<Suggestion>> Accept,
    Action<IReadOnlyList<string>> Select,
    Action PickStreet,
    Action Anyway,
    Action ProjectInformation,
    Action Redraw);

/// <summary>
/// The Setup form in the Gordium pane (docs/decisions/2026-11-22_setup_form.md; UI polish changes 1 to 8, Ben
/// approved 2026-11-23): only the things the check needs, as numbered steps above the fold ("Set 6 things to check
/// this project", "0 of 6 set"), each with one help line and the law behind ⓘ; a step's circle turns ✓ once set
/// (never an amber "needed": status colours are for results); every optional fact in one fold, "More facts
/// (optional)"; one sticky footer, "Save and check" with "Check without them" and one line on what Save writes. Every
/// choice stays in the draft (<see cref="SetupDraft"/>) until Save writes them, in one transaction; a suggestion is
/// written only by its Accept. Drawn from <see cref="SetupScreen"/> and <see cref="SetupSteps"/> (Gordium.Revit.Reading
/// decides everything); plain WPF in the panel's tokens.
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
    /// <param name="open">The folds the architect opened (kept across every redraw).</param>
    internal SetupView(SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open)
    {
        _screen = screen;
        _draft = draft;
        _do = handlers;
        _open = open;
        Margin = new W.Thickness(12, 4, 12, 16);
        Head(notice);
        Steps();
        More();
        Footer = MakeFooter();
    }

    /// <summary>The steps as drawn (the tests and the renders read them).</summary>
    internal IReadOnlyList<SetupTask> Shown => _screen.Steps;

    // ---- the head: what is left, as a task (never a warning) -------------------------------------------------------

    private void Head(string? notice)
    {
        if (notice is { Length: > 0 })
            Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                Words(notice, Body, wrap: true), bottom: 8));
        var card = new C.StackPanel();
        card.Children.Add(Words(_screen.Headline, "type.title", wrap: true));
        card.Children.Add(Muted(PaneWords.SetupWhy, top: 3));
        var steps = _screen.Steps;
        if (steps.Count > 0)
        {
            card.Children.Add(Words(SetupSteps.Progress(steps), Caption, semibold: true, top: 8));
            card.Children.Add(ProgressBar(steps.Count(s => s.Done), steps.Count));
        }
        foreach (var p in _screen.FixFirst)
            card.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, Words(p, Caption, wrap: true), bottom: 0, top: 8));
        Children.Add(Card(card, top: 4));
    }

    /// <summary>"4 of 6 set" as a bar of segments, one per step, the set ones in the marked colour (never the pass green).</summary>
    private static W.UIElement ProgressBar(int done, int total)
    {
        var grid = new C.Grid { Margin = new W.Thickness(0, 4, 0, 0), Height = 5 };
        for (var i = 0; i < total; i++)
        {
            grid.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(1, W.GridUnitType.Star) });
            var seg = new C.Border { CornerRadius = new W.CornerRadius(2), Margin = new W.Thickness(i == 0 ? 0 : 2, 0, 0, 0) };
            seg.SetResourceReference(C.Border.BackgroundProperty, i < done ? PanelTokens.Marked : PanelTokens.Line);
            C.Grid.SetColumn(seg, i);
            grid.Children.Add(seg);
        }
        W.Automation.AutomationProperties.SetName(grid, $"{done} of {total} set");
        return grid;
    }

    // ---- the numbered steps --------------------------------------------------------------------------------------

    private void Steps()
    {
        var n = 0;
        foreach (var section in _screen.Steps.GroupBy(s => s.Section))
        {
            Children.Add(Overline(section.Key, top: 14));
            if (section.Key == SetupSteps.Building)
                Children.Add(Muted("The NY Building Code governs this building: these two facts decide most of its egress limits.", top: 0, bottom: 2));
            foreach (var step in section)
                Children.Add(Step(++n, step));
        }
        var already = SetupSteps.AlreadySet(_screen);
        if (already.Count > 0)
            Children.Add(Muted("Already set: " + PaneWords.And(already.Select(l => SetupSteps.Title(l).ToLowerInvariant()).ToList()) + ".", top: 8));
        var nothing = _screen.Lines.Where(SetupSteps.NothingDrawn).ToList();
        if (nothing.Count > 0)
            Children.Add(Muted("Nothing to mark yet for " + PaneWords.And(nothing.Select(l => l.Title.ToLowerInvariant()).ToList()) +
                               $": none is drawn. Egress waits until the {_screen.Noun}'s rooms, windows and doors are drawn.", top: 8));
    }

    private W.UIElement Step(int number, SetupTask step)
    {
        var body = new C.StackPanel();
        var title = new C.DockPanel();
        if (step.Done)
        {
            var set = Muted("Set");
            C.DockPanel.SetDock(set, C.Dock.Right);
            title.Children.Add(set);
        }
        title.Children.Add(Words(step.Title, Body, semibold: true));
        body.Children.Add(title);
        if (step.Field is { } f)
            FieldBody(body, f);
        else if (step.Line is { } l)
            LineBody(body, l);
        var row = new C.DockPanel { Margin = new W.Thickness(0, 9, 0, 0), Tag = StepTag };
        var circle = Circle(number, step.Done);
        C.DockPanel.SetDock(circle, C.Dock.Left);
        row.Children.Add(circle);
        row.Children.Add(body);
        W.Automation.AutomationProperties.SetName(row, $"Step {number}: {step.Title}{(step.Done ? ", set" : "")}");
        return row;
    }

    /// <summary>A step row's tag (the renders count the steps by it).</summary>
    internal const string StepTag = "setup.step";

    /// <summary>A step's circle: its number, or ✓ once set (in the marked colour, never the pass green).</summary>
    private static W.FrameworkElement Circle(int number, bool done)
    {
        var b = new C.Border { Width = 20, Height = 20, CornerRadius = new W.CornerRadius(10), Margin = new W.Thickness(0, 0, 10, 0), VerticalAlignment = W.VerticalAlignment.Top };
        if (done)
        {
            b.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.MarkedFill);
            var tick = new S.Path { Data = M.Geometry.Parse("M 5.5,10 L 8.5,13 L 14.5,7"), StrokeThickness = 1.6, StrokeStartLineCap = M.PenLineCap.Round, StrokeEndLineCap = M.PenLineCap.Round };
            tick.SetResourceReference(S.Shape.StrokeProperty, PanelTokens.Marked);
            b.Child = tick;
        }
        else
        {
            b.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgHover);
            var t = Words(number.ToString(System.Globalization.CultureInfo.InvariantCulture), Caption, semibold: true);
            t.HorizontalAlignment = W.HorizontalAlignment.Center;
            t.VerticalAlignment = W.VerticalAlignment.Center;
            b.Child = Ink(t, PanelTokens.TextMuted);
        }
        return b;
    }

    // ---- a project fact ------------------------------------------------------------------------------------------

    /// <summary>A step's field: its control, its problem, its one help line with the law behind ⓘ.</summary>
    private void FieldBody(C.StackPanel box, SetupField f)
    {
        var chosen = _draft.Chosen(f.Mark);
        var shown = chosen ?? f.CurrentChoice?.Value ?? f.Current;
        box.Children.Add(Control(f, shown, chosen));
        if (f.Mark == Marks.OccupancyGroups && !SetupSteps.Done(f, _draft) && GroupSuggestion.For(_draft.Chosen(Marks.Use) ?? UseHeld()) is { } g)
            box.Children.Add(Suggested(g));
        if (f.Problem is not null && chosen is null)
            box.Children.Add(Ink(Words(f.Problem, Caption, wrap: true, top: 3), PanelTokens.StatusReview));
        box.Children.Add(HelpLine(SetupSteps.Help(f, shown), f.Law));
    }

    private string? UseHeld() => _screen.Fields.FirstOrDefault(x => x.Mark == Marks.Use)?.Current;

    /// <summary>The suggested group, with its basis on hover, chosen only by Accept (still written only on Save).</summary>
    private W.UIElement Suggested(GroupSuggestion g)
    {
        var row = new C.WrapPanel { Margin = new W.Thickness(0, 4, 0, 0) };
        var words = Muted(g.Words);
        words.VerticalAlignment = W.VerticalAlignment.Center;
        words.Margin = new W.Thickness(0, 0, 8, 0);
        row.Children.Add(words);
        var accept = Button($"Accept {g.Group}", primary: false, "Chooses it here; it is written only when you click Save");
        accept.Click += (_, _) => _do.Choose(Marks.OccupancyGroups, g.Group);
        row.Children.Add(accept);
        var why = CauseCardsView.Link("Why?", () => { });
        why.ToolTip = Tip(g.Basis);
        why.Margin = new W.Thickness(8, 0, 0, 0);
        why.VerticalAlignment = W.VerticalAlignment.Center;
        row.Children.Add(why);
        return row;
    }

    /// <summary>The field's control: a dropdown, a two-way switch (Yes / No, Survey / Tax map), a box, or Pick on plan.</summary>
    private W.UIElement Control(SetupField f, string? shown, string? chosen)
    {
        switch (f.Kind)
        {
            case FieldKind.Choice:
            {
                var combo = new C.ComboBox { Margin = new W.Thickness(0, 4, 0, 0), MaxDropDownHeight = 280, IsEditable = false };
                W.Automation.AutomationProperties.SetName(combo, SetupSteps.Title(f.Mark, f.Label));
                foreach (var c in f.Choices)
                    combo.Items.Add(new C.ComboBoxItem { Content = c.Label, Tag = c.Value });
                var at = f.Choices.ToList().FindIndex(c => c.Value == shown);
                combo.SelectedIndex = at;
                // only the architect's own pick is a choice: setting the shown value above is not
                combo.SelectionChanged += (_, _) =>
                {
                    if (combo.SelectedItem is C.ComboBoxItem { Tag: string value })
                        _do.Choose(f.Mark, value);
                };
                // nothing chosen: says so in the box (never a value shown that isn't the mark's or the architect's)
                var hint = Muted(f.Mark == Marks.Zone ? "Choose the district" : f.Mark == Marks.Use ? "Choose the use"
                                 : f.Mark == Marks.OccupancyGroups ? "Choose the group" : f.Mark == Marks.SprinklerSystem ? "Choose the system" : "Choose one");
                hint.IsHitTestVisible = false;
                hint.Margin = new W.Thickness(8, 9, 24, 0);
                hint.Visibility = at < 0 ? W.Visibility.Visible : W.Visibility.Collapsed;
                var grid = new C.Grid();
                grid.Children.Add(combo);
                grid.Children.Add(hint);
                return grid;
            }
            case FieldKind.YesNo:
                return Segmented(f, SetupSteps.Choices(f), shown, stretch: f.Required);
            case FieldKind.StreetPick:
            {
                var row = new C.WrapPanel { Margin = new W.Thickness(0, 4, 0, 0) };
                var pick = Button(f.Current is null && chosen is null ? "Pick on plan" : "Pick again", primary: false,
                                  "Click the lot edge along the street in a site or floor plan that shows the property line");
                pick.Click += (_, _) => _do.PickStreet();
                pick.Margin = new W.Thickness(0, 0, 10, 0);
                row.Children.Add(pick);
                var state = Words(SetupSteps.StreetState(f, _draft, _screen.StreetWords), Body);
                state.VerticalAlignment = W.VerticalAlignment.Center;
                row.Children.Add(f.Problem is not null && chosen is null ? Ink(state, PanelTokens.StatusReview) : state);
                return row;
            }
            case FieldKind.Number:
            case FieldKind.Feet:
            case FieldKind.Text:
            default:
            {
                var number = f.Kind is FieldKind.Number or FieldKind.Feet;
                var text = new C.TextBox
                {
                    Text = shown ?? "", Margin = new W.Thickness(0, 4, 0, 0), MaxWidth = number ? 90 : double.PositiveInfinity,
                    HorizontalAlignment = number ? W.HorizontalAlignment.Left : W.HorizontalAlignment.Stretch,
                };
                W.Automation.AutomationProperties.SetName(text, f.Label);
                // the draft follows every keystroke, with no redraw (Save's words follow): a click on Save right after
                // typing writes what was typed; Enter draws the form again
                text.TextChanged += (_, _) =>
                {
                    _do.Type(f.Mark, text.Text);
                    SaveWords();
                };
                text.KeyDown += (_, e) =>
                {
                    if (e.Key == System.Windows.Input.Key.Enter && text.Text.Trim().Length > 0)
                        _do.Choose(f.Mark, text.Text);
                };
                return text;
            }
        }
    }

    /// <summary>A two-way switch: one button per choice, the one shown pressed; neither pressed is not stated.</summary>
    private W.UIElement Segmented(SetupField f, IReadOnlyList<FieldChoice> choices, string? shown, bool stretch)
    {
        var grid = new C.Grid { Margin = new W.Thickness(0, 4, 0, 0) };
        if (!stretch)
            grid.HorizontalAlignment = W.HorizontalAlignment.Right;
        for (var i = 0; i < choices.Count; i++)
        {
            grid.ColumnDefinitions.Add(new C.ColumnDefinition { Width = stretch ? new W.GridLength(1, W.GridUnitType.Star) : W.GridLength.Auto });
            var c = choices[i];
            var t = new C.Primitives.ToggleButton
            {
                Content = c.Label, IsChecked = shown == c.Value, MinWidth = stretch ? 0 : 48, Padding = new W.Thickness(10, 3, 10, 3),
                Margin = new W.Thickness(i == 0 ? 0 : 2, 0, 0, 0),
            };
            W.Automation.AutomationProperties.SetName(t, $"{SetupSteps.Title(f.Mark, f.Label)}: {c.Label}");
            t.Click += (_, _) => _do.Choose(f.Mark, c.Value);
            C.Grid.SetColumn(t, i);
            grid.Children.Add(t);
        }
        return grid;
    }

    /// <summary>One short help line (≤ 1 line at 340 px), the law's whole words behind ⓘ on hover.</summary>
    private static W.UIElement HelpLine(string? help, string law)
    {
        var row = new C.DockPanel { Margin = new W.Thickness(0, 3, 0, 0) };
        var info = Muted("ⓘ");
        info.ToolTip = Tip(law);
        info.Margin = new W.Thickness(6, 0, 0, 0);
        info.VerticalAlignment = W.VerticalAlignment.Top;
        W.Automation.AutomationProperties.SetName(info, "The law behind it");
        C.DockPanel.SetDock(info, C.Dock.Right);
        row.Children.Add(info);
        row.Children.Add(Muted(help ?? "", wrap: true));
        return row;
    }

    // ---- a fact inside the building ------------------------------------------------------------------------------

    private void LineBody(C.StackPanel box, ChecklistLine l)
    {
        var actions = new C.WrapPanel { Margin = new W.Thickness(0, 4, 0, 0) };
        if (l.Unset.Count > 0)
        {
            var select = Button($"Select {l.Unset.Count}", primary: false,
                                l.PerType ? "Selects every element of the types not set: set it once per type with Edit Type in Properties"
                                          : "Selects them in Revit: set them together in Properties");
            select.Click += (_, _) => _do.Select(l.Unset);
            select.Margin = new W.Thickness(0, 0, 8, 0);
            actions.Children.Add(select);
        }
        if (l.Suggestions.Count > 0)
        {
            var all = Button($"Accept {l.Suggestions.Count} {(l.Suggestions.Count == 1 ? "suggestion" : "suggestions")}", primary: false,
                             "Writes every suggestion as one undo step: Why? lists what each is based on");
            all.Click += (_, _) => _do.Accept(l.Suggestions);
            all.Margin = new W.Thickness(0, 0, 8, 0);
            actions.Children.Add(all);
        }
        if (actions.Children.Count > 0)
            box.Children.Add(actions);
        // the count, what Gordium suggests, and "Why?" at its end (the reasons and each suggestion's basis on demand)
        var whyKey = "why:" + l.Key;
        var count = Muted(SetupSteps.LineCount(l) + (SetupSteps.SuggestsLine(l) is { } s ? " " + s : "") + " ", top: 3, wrap: true);
        var why = new W.Documents.Hyperlink(new W.Documents.Run(_open.Contains(whyKey) ? "Hide why" : "Why?"));
        why.SetResourceReference(W.Documents.TextElement.ForegroundProperty, PanelTokens.Accent);
        why.Click += (_, _) => Toggle(whyKey);
        count.Inlines.Add(why);
        box.Children.Add(count);
        if (!_open.Contains(whyKey))
            return;
        var more = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
        more.Children.Add(Muted(l.WhyAsked, wrap: true));
        if (!l.Done)
            more.Children.Add(Muted(l.IfBlank, top: 3, wrap: true));
        foreach (var sug in l.Suggestions)
            more.Children.Add(SuggestionRow(sug));
        foreach (var n in l.Notes)
            more.Children.Add(Muted(n, top: 3, wrap: true));
        box.Children.Add(more);
    }

    private void Toggle(string key)
    {
        if (!_open.Remove(key))
            _open.Add(key);
        _do.Redraw();
    }

    private W.UIElement SuggestionRow(Suggestion s)
    {
        var row = new C.DockPanel { Margin = new W.Thickness(0, 5, 0, 0) };
        var accept = Button("Accept", primary: false, $"Writes {s.Mark.Name} = {s.Words} on {s.Label} (one undo step)");
        accept.Padding = new W.Thickness(8, 1, 8, 1);
        accept.VerticalAlignment = W.VerticalAlignment.Top;
        C.DockPanel.SetDock(accept, C.Dock.Right);
        accept.Click += (_, _) => _do.Accept([s]);
        row.Children.Add(accept);
        var words = new C.StackPanel { Margin = new W.Thickness(0, 0, 6, 0) };
        words.Children.Add(Words($"{s.Label}: {s.Words}", Caption, semibold: true, wrap: true));
        words.Children.Add(Muted("Based on: " + s.Basis, wrap: true));
        row.Children.Add(words);
        return row;
    }

    // ---- More facts (optional) -----------------------------------------------------------------------------------

    private void More()
    {
        var fields = SetupSteps.MoreFields(_screen);
        var lines = SetupSteps.MoreLines(_screen);
        if (fields.Count == 0 && lines.Count == 0)
            return;
        var inside = new C.StackPanel { Margin = new W.Thickness(0, 4, 0, 0) };
        foreach (var group in fields.GroupBy(f => f.Group))
        {
            inside.Children.Add(Overline(group.Key.ToUpperInvariant(), top: 10));
            foreach (var f in group)
                inside.Children.Add(MoreField(f));
        }
        if (lines.Count > 0)
        {
            inside.Children.Add(Overline(SetupSteps.InModel, top: 10));
            foreach (var l in lines)
            {
                var box = new C.StackPanel { Margin = new W.Thickness(0, 6, 0, 0) };
                box.Children.Add(Words(l.Title, Body, semibold: true));
                LineBody(box, l);
                inside.Children.Add(box);
            }
        }
        var info = CauseCardsView.Link("Open Project Information", () => _do.ProjectInformation());
        info.Margin = new W.Thickness(0, 10, 0, 0);
        info.HorizontalAlignment = W.HorizontalAlignment.Left;
        inside.Children.Add(info);
        inside.Children.Add(Muted("Each answer is saved to Project Information when you click Save. Blank is fine: Gordium says what it couldn't decide.", top: 6, wrap: true));
        var head = new C.StackPanel();
        head.Children.Add(Words(SetupSteps.MoreTitle, Body, semibold: true));
        if (!_open.Contains(MoreKey))
            head.Children.Add(Muted(SetupSteps.MoreSummary(_screen), top: 2, wrap: true));
        var fold = new C.Expander { Header = head, IsExpanded = _open.Contains(MoreKey), Content = inside };
        fold.Expanded += (_, _) => _open.Add(MoreKey);
        fold.Collapsed += (_, _) => _open.Remove(MoreKey);
        Children.Add(Card(fold, top: 18));
    }

    internal const string MoreKey = "more";

    /// <summary>An optional fact on one line where it fits (a question and its Yes / No), else its label over its control.</summary>
    private W.UIElement MoreField(SetupField f)
    {
        var chosen = _draft.Chosen(f.Mark);
        var shown = chosen ?? f.CurrentChoice?.Value ?? f.Current;
        var box = new C.StackPanel { Margin = new W.Thickness(0, 6, 0, 0) };
        var label = SetupSteps.Question(f) ?? f.Label;
        if (f.Kind is FieldKind.YesNo or FieldKind.Number or FieldKind.Feet)
        {
            var row = new C.DockPanel();
            var control = f.Kind == FieldKind.YesNo ? Segmented(f, f.Choices, shown, stretch: false) : Control(f, shown, chosen);
            if (control is C.TextBox box1)
            {
                box1.Width = 70;
                box1.Margin = new W.Thickness(0);
                box1.VerticalAlignment = W.VerticalAlignment.Center;
            }
            ((W.FrameworkElement)control).Margin = new W.Thickness(8, 0, 0, 0);
            C.DockPanel.SetDock(control, C.Dock.Right);
            row.Children.Add(control);
            var words = Words(label, Body, wrap: true);
            words.VerticalAlignment = W.VerticalAlignment.Center;
            words.ToolTip = Tip(f.Law);
            row.Children.Add(words);
            box.Children.Add(row);
        }
        else
        {
            var words = Words(label, Body, wrap: true);
            words.ToolTip = Tip(f.Law);
            box.Children.Add(words);
            box.Children.Add(Control(f, shown, chosen));
        }
        if (f.Problem is not null && chosen is null)
            box.Children.Add(Ink(Words(f.Problem, Caption, wrap: true, top: 2), PanelTokens.StatusReview));
        return box;
    }

    // ---- the footer: one primary action -------------------------------------------------------------------------

    private C.Button? _save;
    private C.TextBlock? _footWords;

    /// <summary>The form's one action, for the pane to pin at its foot (never scrolled away): Save and check (greyed
    /// until a choice), Check without them, Undo changes, and one line on what Save writes.</summary>
    internal C.Border Footer { get; private set; } = new();

    private C.Border MakeFooter()
    {
        var p = new C.StackPanel();
        var line = new C.WrapPanel();                           // the links under Save in a narrow pane
        var save = Button(PaneWords.SaveAndCheck(0), primary: true,
                          $"Writes what you chose to Project Information as one undo step ({SetupWrites.FactsTransaction}), then checks");
        _save = save;
        save.Click += (_, _) => _do.Save();
        save.Margin = new W.Thickness(0, 0, 12, 4);
        line.Children.Add(save);
        if (!_screen.Ready)                                     // nothing missing: nothing to check without
        {
            var anyway = CauseCardsView.Link(PaneWords.CheckWithout, () => _do.Anyway());
            anyway.ToolTip = "Check with what is set now: each fact still missing makes the rules it decides need review, never a pass";
            anyway.VerticalAlignment = W.VerticalAlignment.Center;
            anyway.Margin = new W.Thickness(0, 0, 12, 4);
            line.Children.Add(anyway);
        }
        if (Changes() > 0)
        {
            var undo = CauseCardsView.Link("Undo changes", () => _do.Discard());
            undo.ToolTip = "Forget the choices not saved: the fields show what Project Information holds";
            undo.VerticalAlignment = W.VerticalAlignment.Center;
            undo.Margin = new W.Thickness(0, 0, 0, 4);
            line.Children.Add(undo);
        }
        p.Children.Add(line);
        _footWords = Muted("", top: 2, wrap: true);
        p.Children.Add(_footWords);
        SaveWords();
        var foot = new C.Border { Child = p, BorderThickness = new W.Thickness(0, 1, 0, 0), Padding = new W.Thickness(12, 10, 12, 10) };
        foot.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        foot.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        return foot;
    }

    private int Changes() => PaneWords.Unsaved(_screen, _draft);      // the footer's count too

    /// <summary>The Save button's words and whether it can be clicked, from the draft now (a box typed in updates it
    /// without the form being drawn again, so the click on Save is never lost to a redraw).</summary>
    private void SaveWords()
    {
        if (_save is null)
            return;
        var changes = Changes();
        _save.Content = PaneWords.SaveAndCheck(changes);
        W.Automation.AutomationProperties.SetName(_save, (string)_save.Content);
        _save.IsEnabled = changes > 0;
        if (_footWords is not null)
            _footWords.Text = PaneWords.SetupFooter(_screen, _draft);
    }

    // ---- small pieces --------------------------------------------------------------------------------------------

    private static C.Border Card(W.UIElement content, double top)
    {
        var b = new C.Border
        {
            Child = content, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(6),
            Padding = new W.Thickness(12, 10, 12, 12), Margin = new W.Thickness(0, top, 0, 0),
        };
        b.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        b.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        return b;
    }

    private static C.TextBlock Tip(string words) => new() { Text = words, TextWrapping = W.TextWrapping.Wrap, MaxWidth = 360 };

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

    private static C.TextBlock Muted(string text, double top = 0, double bottom = 0, bool wrap = true)
    {
        var t = EntryView.Muted(text, top, bottom);
        t.TextWrapping = wrap ? W.TextWrapping.Wrap : W.TextWrapping.NoWrap;
        return t;
    }

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

    private static C.Border Banner(PanelStatus status, string fill, string outline, W.UIElement words, double bottom, double top = 0)
    {
        var b = new C.Border
        {
            Child = WithGlyph(status, words, 16), BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Padding = new W.Thickness(8, 5, 8, 5), Margin = new W.Thickness(0, top, 0, bottom),
        };
        b.SetResourceReference(C.Border.BackgroundProperty, fill);
        b.SetResourceReference(C.Border.BorderBrushProperty, outline);
        return b;
    }
}
