using Gordium.Revit.Reading;
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
/// The results panel itself (a WPF view in Revit's dockable pane, beside Properties), matching the agreed mockup
/// (docs/revit/ui_design_pass.md section 2.4): the header with Check again, the worker's state and counts, the filter
/// chips and the search, then the results list: a virtualized ListBox (an entry is made only when it scrolls into
/// view), worst first (<see cref="ResultList"/>: does not comply, needs review, check by hand or not checked, then what
/// complies, folded), every row in exactly one place. A click selects a row and its elements in Revit without moving
/// the view; Show (or Space) zooms; Enter or a double click opens its detail (its law's words); Up/Down move; Ctrl+C
/// copies the row as the text file says it; Ctrl+F searches and Esc clears the search. Plain WPF: every Revit call
/// goes through the callbacks, which queue it for Revit's thread (<see cref="PanelActions"/>). Every colour is a
/// token of the theme's dictionary (<see cref="PanelLook"/>), named with SetResourceReference so it follows Revit's
/// theme; every status is drawn as its glyph and said in words, never by colour alone (<see cref="StatusLook"/>).
/// </summary>
internal sealed class ResultsView : C.UserControl, IListHost
{
    private readonly Action<ResultRow> _zoom;
    private readonly Action<ResultRow> _select;
    private readonly Action _checkAgain;
    private readonly Action _projectInformation;
    private readonly C.TextBlock _sub = Small("");
    private readonly C.Button _again;
    private readonly C.TextBlock _status = Small("");
    private readonly C.Border _bodyHost = new();
    private readonly C.StackPanel _missing = new() { Margin = new W.Thickness(12, 4, 12, 12) };
    private readonly C.ScrollViewer _missingScroll;
    private readonly C.Grid _results = new();
    private Func<W.UIElement>? _summary;                     // the state and the counts: the list's first entry
    private readonly C.WrapPanel _chips = new() { Margin = new W.Thickness(0, 4, 0, 0) };
    private readonly C.TextBox _search = new() { MinWidth = 120, Margin = new W.Thickness(0, 6, 0, 0) };
    private readonly C.TextBlock _searchHint = Small("Search rules, sections, elements (Ctrl+F)");
    private readonly C.TextBlock _shown = Small("");
    private readonly C.ListBox _list = new();
    private PanelContent? _content;

    // the list's state, kept across every redraw (a stale redraw, a new check): the filter, the folds, what is open
    private IReadOnlyList<ListRow> _placed = [];
    private IReadOnlyList<ListEntry> _entries = [];
    private List<ListItem> _items = [];
    private ListFilter _filter = ListFilter.All;
    private readonly HashSet<ListSection> _opened = [];
    private readonly HashSet<string> _openRows = new(StringComparer.Ordinal);
    private readonly HashSet<string> _openFolds = new(StringComparer.Ordinal);
    private string? _selectedId;
    private bool _quiet;                                      // a selection the panel makes itself: never sent to Revit

    internal ResultsView(Action<ResultRow> zoom, Action<ResultRow> select, Action checkAgain, Action projectInformation, PanelTheme theme)
    {
        _zoom = zoom;
        _select = select;
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
        titleLine.Children.Add(Typed(new C.TextBlock { Text = RibbonPlan.PaneTitle, VerticalAlignment = W.VerticalAlignment.Center,
                                                       TextTrimming = W.TextTrimming.CharacterEllipsis }, "type.title"));
        head.Children.Add(titleLine);
        head.Children.Add(_sub);
        _status.Visibility = W.Visibility.Collapsed;
        _status.FontStyle = W.FontStyles.Italic;
        _status.TextWrapping = W.TextWrapping.NoWrap;           // one line (its whole on hover): never pushes the list down
        _status.TextTrimming = W.TextTrimming.CharacterEllipsis;
        head.Children.Add(_status);

        // what to fill in first (nothing checked): one scrolling column
        _missingScroll = new C.ScrollViewer
        {
            VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled,
            Content = _missing,
        };

        // the results: only the compact toolbar (filter chips, search, what they show) pinned at the top; the state
        // and the counts are the list's first entry and scroll away with the rows (Revit trial, 106 Ithaca Rd: pinned,
        // they filled the whole docked pane, ~340 by 430 px, and the list got nothing). The list is in the Grid's star
        // row (a list inside a ScrollViewer is measured at full height and builds every row).
        _results.RowDefinitions.Add(new C.RowDefinition { Height = W.GridLength.Auto });
        _results.RowDefinitions.Add(new C.RowDefinition { Height = new W.GridLength(1, W.GridUnitType.Star) });
        var tools = Tools();
        C.Grid.SetRow(tools, 0);
        _results.Children.Add(tools);
        _list.SetResourceReference(StyleProperty, "list");
        _list.Margin = new W.Thickness(12, 4, 12, 8);
        _list.ItemTemplate = EntryView.Template();
        _list.ItemContainerStyleSelector = new EntryStyles();
        _list.SelectionChanged += (_, _) => Selected();
        _list.PreviewKeyDown += ListKeys;
        _list.MouseDoubleClick += (_, e) =>
        {
            if (Within<C.Button>(e.OriginalSource) is not null || Within<C.ListBoxItem>(e.OriginalSource)?.DataContext is not RowItem row)
                return;
            e.Handled = true;
            ToggleOpen(row);
        };
        W.Automation.AutomationProperties.SetName(_list, "Results");
        C.Grid.SetRow(_list, 1);
        _results.Children.Add(_list);
        PreviewKeyDown += PanelKeys;

        var all = new C.DockPanel();
        C.DockPanel.SetDock(head, C.Dock.Top);
        all.Children.Add(head);
        all.Children.Add(_bodyHost);
        Content = all;
        _bodyHost.Child = _missingScroll;
        _sub.Text = "Click Check project on the Gordium tab to check this project.";
    }

    /// <summary>The filter chips (the count bar's kinds) and the search box, with what they show.</summary>
    private C.StackPanel Tools()
    {
        var tools = new C.StackPanel { Margin = new W.Thickness(12, 0, 12, 0) };
        tools.Children.Add(_chips);
        var box = new C.Grid();
        _search.ToolTip = "Matches rule names, sections and element names (Esc clears)";
        W.Automation.AutomationProperties.SetName(_search, "Search the results");
        _search.TextChanged += (_, _) =>
        {
            _searchHint.Visibility = _search.Text.Length == 0 ? W.Visibility.Visible : W.Visibility.Collapsed;
            Relayout();
        };
        _search.PreviewKeyDown += SearchKeys;
        box.Children.Add(_search);
        _searchHint.IsHitTestVisible = false;
        _searchHint.Margin = new W.Thickness(7, 9, 0, 0);
        _searchHint.TextWrapping = W.TextWrapping.NoWrap;
        _searchHint.TextTrimming = W.TextTrimming.CharacterEllipsis;
        box.Children.Add(_searchHint);
        tools.Children.Add(box);
        _shown.Margin = new W.Thickness(0, 4, 0, 0);
        _shown.Visibility = W.Visibility.Collapsed;
        tools.Children.Add(_shown);
        return tools;
    }

    /// <summary>Revit's theme changed: the theme's brushes swapped, everything on screen recoloured in place.</summary>
    internal void UseTheme(PanelTheme theme) => PanelLook.Apply(this, theme);

    // ---- what the panel shows ------------------------------------------------------------------------------

    internal void Show(PanelContent content)
    {
        _content = content;
        _again.Visibility = W.Visibility.Visible;
        _again.IsEnabled = _checkAgainState.Enabled;             // a check still waiting keeps it greyed
        _sub.Text = $"Checked {content.When:HH:mm} · {content.Project}";
        Say(_checkAgainState.Status(ClearPrefills.PanelStatus(content.MarksAdded, content.ClearWords, stale: content.Model?.Stale is not null)));
        _summary = null;
        _missing.Children.Clear();
        if (content.Model is not { } model)
        {
            _placed = [];
            ShowMissing(content.Missing);
            _missing.Children.Add(Small(content.Files, top: 8));
            _bodyHost.Child = _missingScroll;
            Relayout();
            return;
        }
        var stale = model.Stale is not null;                     // stale: every status the clock, never a verdict's colour
        var folds = new List<FoldItem>();
        var parts = ResultRows.Layout(model);
        foreach (var part in parts)
            switch (part)
            {
                case PanelPart.Groups:
                    _placed = ResultList.Place(model);
                    break;
                case PanelPart.Inside:
                    folds.Add(new FoldItem(this, "What wasn't read from the model", () => Small(model.Inside)));
                    break;
                case PanelPart.Details:
                    folds.Add(new FoldItem(this, "Details", () =>
                    {
                        var d = new C.StackPanel();
                        d.Children.Add(Small(model.Checked, top: 2));
                        d.Children.Add(Small(content.Files, top: 4));
                        return d;
                    }));
                    break;
            }
        // made afresh each time its entry scrolls into view (a virtualized container is made again; an element has one parent)
        _summary = () => Summary(model, parts, stale);
        _folds = folds;
        Chips(stale);
        _bodyHost.Child = _results;
        Relayout();
    }

    /// <summary>The list's first entry: the stale notice (when stale), the worker's state (grey once stale, never
    /// green) and its counts, one wrap line per law. It scrolls away with the rows.</summary>
    private static W.UIElement Summary(ResultModel model, IReadOnlyList<PanelPart> parts, bool stale)
    {
        var summary = new C.StackPanel { Margin = new W.Thickness(0, 2, 0, 2) };
        foreach (var part in parts)
            switch (part)
            {
                case PanelPart.Stale:
                    summary.Children.Add(Banner(PanelStatus.Stale, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                                Typed(new C.TextBlock { Text = model.Stale, FontWeight = W.FontWeights.SemiBold,
                                                                        TextWrapping = W.TextWrapping.Wrap }, Body), bottom: 6));
                    break;
                case PanelPart.State:
                    var state = StatusLook.Of(model.StateTone, stale);
                    summary.Children.Add(WithGlyph(state, Ink(Typed(new C.TextBlock
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
                        summary.Children.Add(chips);
                    }
                    break;
            }
        return summary;
    }

    /// <summary>The folds after the rows (what wasn't read, the details), shown when the list shows every row.</summary>
    private List<FoldItem> _folds = [];

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
        _placed = [];
        _summary = null;
        _missing.Children.Clear();
        _bodyHost.Child = _missingScroll;
        Relayout();
        _sub.Text = "Not checked";
        Say(words);
    }

    /// <summary>A line under the header (a click's result, a problem); empty hides it.</summary>
    internal void Say(string words)
    {
        _status.Text = words;
        _status.ToolTip = words.Length == 0 ? null : words;
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
        _missing.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                     Typed(new C.TextBlock { Text = "Nothing was checked: fill these in first", TextWrapping = W.TextWrapping.Wrap },
                                           "type.title"), bottom: 6));
        foreach (var m in missing)
            _missing.Children.Add(new C.TextBlock { Text = "• " + m, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 0, 0, 6) });
        var open = new C.Button
        {
            Content = "Open Project Information", Padding = new W.Thickness(10, 3, 10, 3), Margin = new W.Thickness(0, 4, 0, 4),
            HorizontalAlignment = W.HorizontalAlignment.Left,
        };
        open.Click += (_, _) => _projectInformation();
        _missing.Children.Add(open);
        _missing.Children.Add(Small("Fill in the Gordium marks there, then click Check again (a street edge is asked for by a click when you do)."));
    }

    // ---- the list ------------------------------------------------------------------------------------------

    /// <summary>The filter chips, one pressed: the count bar's kinds (ResultList.Chips), each with its glyph (the
    /// clock once stale).</summary>
    private void Chips(bool stale)
    {
        _chips.Children.Clear();
        foreach (var chip in ResultList.Chips(_placed, stale))
        {
            W.UIElement words = Typed(new C.TextBlock { Text = chip.Words, VerticalAlignment = W.VerticalAlignment.Center }, Caption);
            var button = new C.Primitives.ToggleButton
            {
                Content = chip.Status is { } s ? WithGlyph(s, words, size: 11) : words, IsChecked = chip.Filter == _filter,
                Padding = new W.Thickness(7, 1, 8, 1), Margin = new W.Thickness(0, 0, 4, 4),
                ToolTip = chip.Filter switch
                {
                    ListFilter.All => "Every row",
                    ListFilter.Fails => "Only what does not comply",
                    ListFilter.Review => "What needs review, is to check by hand, or isn't checked",
                    _ => "Only what complies or doesn't apply",
                },
            };
            var filter = chip.Filter;
            button.Click += (_, _) =>
            {
                _filter = filter;
                foreach (var b in _chips.Children.OfType<C.Primitives.ToggleButton>())
                    b.IsChecked = ReferenceEquals(b, button);
                Relayout();
            };
            _chips.Children.Add(button);
        }
    }

    /// <summary>The list again, from the rows placed, the filter, the search and the folds; the selected row kept
    /// when it is still shown.</summary>
    private void Relayout()
    {
        var labels = _content?.Labels;
        var stale = _content?.Model?.Stale is not null;
        var layout = ResultList.Layout(_placed, _filter, _search.Text, labels, stale, _opened);
        _entries = _summary is null ? layout : ResultList.WithSummary(layout);
        var items = new List<ListItem>(_entries.Count + 2);
        RowItem? selected = null;
        foreach (var e in _entries)
            switch (e)
            {
                case ListSummary:
                    items.Add(new SummaryItem(this, _summary!));
                    break;
                case ListHeading h:
                    items.Add(new HeadingItem(this, h));
                    break;
                case ListSubheading s:
                    items.Add(new SubItem(this, s));
                    break;
                case ListRowEntry r:
                    var row = new RowItem(this, r.Row, _openRows.Contains(r.Row.Row.Id));
                    if (r.Row.Row.Id == _selectedId)
                        selected = row;
                    items.Add(row);
                    break;
            }
        var narrowed = _filter != ListFilter.All || ResultList.Terms(_search.Text).Count > 0;
        if (!narrowed && _placed.Count > 0)
            foreach (var f in _folds)
            {
                f.Open = _openFolds.Contains(f.Title);
                items.Add(f);
            }
        _items = items;
        _quiet = true;
        try
        {
            _list.ItemsSource = items;
            _list.SelectedItem = selected;
        }
        finally
        {
            _quiet = false;
        }
        var rows = _entries.Count(e => e is ListRowEntry);
        _shown.Text = !narrowed ? "" : rows == 0
            ? ResultList.Terms(_search.Text).Count > 0 ? $"No row matches “{_search.Text.Trim()}” here." : "No row here."
            : $"Showing {rows} of {_placed.Count} rows.";
        _shown.Visibility = _shown.Text.Length == 0 ? W.Visibility.Collapsed : W.Visibility.Visible;
    }

    /// <summary>A row the architect selected (a click, Up or Down): its elements selected in Revit, the view unmoved.</summary>
    private void Selected()
    {
        if (_list.SelectedItem is not RowItem row)
        {
            if (!_quiet && _list.SelectedItem is not null)
                _list.SelectedItem = null;                       // a heading is never the selection
            return;
        }
        _selectedId = row.Row.Row.Id;                            // kept while a filter or a search hides it
        if (!_quiet)
            _select(row.Row.Row);
    }

    private RowItem? SelectedRow => _list.SelectedItem as RowItem;

    /// <summary>Selects entry <paramref name="index"/> (a row), brings it into view and gives it the keyboard focus.</summary>
    private void FocusEntry(int index)
    {
        if (index < 0 || index >= _items.Count)
            return;
        _list.SelectedIndex = index;
        _list.ScrollIntoView(_items[index]);
        _list.UpdateLayout();
        (_list.ItemContainerGenerator.ContainerFromIndex(index) as C.ListBoxItem)?.Focus();
    }

    private void ListKeys(object sender, I.KeyEventArgs e)
    {
        // only a key on a row, or on the list itself: never one meant for a fold after the rows (Space on Details)
        if (!ResultList.ListTakesKey(onRow: Within<C.ListBoxItem>(e.OriginalSource)?.DataContext is RowItem,
                                     onList: ReferenceEquals(e.OriginalSource, _list)))
            return;
        var ctrl = (I.Keyboard.Modifiers & I.ModifierKeys.Control) != 0;
        switch (e.Key)
        {
            case I.Key.Down or I.Key.Up when !ctrl:
                FocusEntry(ResultList.Next(_entries, _list.SelectedIndex, e.Key == I.Key.Down ? 1 : -1));
                e.Handled = true;
                break;
            case I.Key.Enter when SelectedRow is { } row:
                ToggleOpen(row);
                e.Handled = true;
                break;
            case I.Key.Space when SelectedRow is { } row:
                ShowRow(row);
                e.Handled = true;
                break;
            case I.Key.C when ctrl && SelectedRow is { } row:
                Copy(row);
                e.Handled = true;
                break;
        }
    }

    private void SearchKeys(object sender, I.KeyEventArgs e)
    {
        if (e.Key == I.Key.Escape)
        {
            if (_search.Text.Length > 0)
                _search.Clear();
            else
                FocusEntry(_list.SelectedIndex >= 0 ? _list.SelectedIndex : ResultList.Next(_entries, -1, 1));   // back to the list
            e.Handled = true;
        }
        else if (e.Key == I.Key.Down)
        {
            FocusEntry(_list.SelectedIndex >= 0 ? _list.SelectedIndex : ResultList.Next(_entries, -1, 1));   // into the list
            e.Handled = true;
        }
    }

    private void PanelKeys(object sender, I.KeyEventArgs e)
    {
        if (e.Key == I.Key.F && (I.Keyboard.Modifiers & I.ModifierKeys.Control) != 0 && ReferenceEquals(_bodyHost.Child, _results))
        {
            _search.Focus();
            _search.SelectAll();
            e.Handled = true;
        }
    }

    /// <summary>Ctrl+C: the row as the text file writes it (stale: when it was checked), on the clipboard.</summary>
    private void Copy(RowItem row)
    {
        var text = ResultList.CopyText(row.Row.Row, _content?.Labels, _content?.Model?.Stale is null ? null : _content.When);
        try
        {
            W.Clipboard.SetText(text);
            Say("Copied: " + (text.Length > 100 ? text[..100] + "…" : text));
        }
        catch (Exception x) when (x is System.Runtime.InteropServices.COMException or InvalidOperationException)
        {
            Say($"Couldn't copy (the clipboard is in use: {x.Message}); try again.");
        }
    }

    // ---- what a list entry asks (IListHost) ----------------------------------------------------------------

    /// <summary>A heading clicked: the complies place shown or folded again (no other place is ever folded:
    /// ResultList.Layout).</summary>
    public void Toggle(ListSection section)
    {
        if (section != ListSection.Complies)
            return;
        if (!_opened.Remove(section))
            _opened.Add(section);
        Relayout();
    }

    /// <summary>Show (or Space): the row selected and its elements zoomed to.</summary>
    public void ShowRow(RowItem row)
    {
        _quiet = true;                                            // the zoom selects them too: one request, not two
        try
        {
            _list.SelectedItem = row;
            _selectedId = row.Row.Row.Id;
        }
        finally
        {
            _quiet = false;
        }
        if (row.Row.Row.Elements.Count == 0)
        {
            Say($"{row.Row.Row.Name} names no element in the model to show.");
            return;
        }
        _zoom(row.Row.Row);
    }

    /// <summary>Enter or a double click: the row's detail (its law's words) opened or folded, kept across redraws.</summary>
    public void ToggleOpen(RowItem row)
    {
        var open = !row.Open;
        if (open)
            _openRows.Add(row.Row.Row.Id);
        else
            _openRows.Remove(row.Row.Row.Id);
        row.SetOpen(open);
    }

    /// <summary>An element as the project labels it ("Windows id 341207"), or that it isn't in the model now.</summary>
    public string Label(string uid) => _content?.Labels.GetValueOrDefault(uid) ?? "not in this model now";

    /// <summary>A fold after the rows opened or closed: kept across redraws.</summary>
    public void FoldChanged(FoldItem fold)
    {
        if (fold.Open)
            _openFolds.Add(fold.Title);
        else
            _openFolds.Remove(fold.Title);
    }

    private static T? Within<T>(object? source) where T : W.DependencyObject
    {
        for (var d = source as W.DependencyObject; d is not null; d = d is W.Media.Visual or W.Media.Media3D.Visual3D ? M.VisualTreeHelper.GetParent(d) : W.LogicalTreeHelper.GetParent(d))
            if (d is T t)
                return t;
        return null;
    }

    // ---- small pieces --------------------------------------------------------------------------------------

    private const string Body = "type.body";
    private const string Caption = "type.caption";

    /// <summary>The text with its type token's style (size, weight, family).</summary>
    private static C.TextBlock Typed(C.TextBlock t, string token) => EntryView.Typed(t, token);

    /// <summary>The text in a colour token.</summary>
    private static C.TextBlock Ink(C.TextBlock t, string token) => EntryView.Ink(t, token);

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
}
