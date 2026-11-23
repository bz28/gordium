using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;
using I = System.Windows.Input;

namespace Gordium.Revit.Addin;

/// <summary>What a cause card asks Revit (on its thread, through PanelActions): select its elements and zoom to
/// them, and, for a mark, bring up Properties; What names them in the panel's line.</summary>
internal sealed record CardRequest(CauseCard Card, CardAction Action, IReadOnlyList<string> Elements, string What);

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
/// <param name="Ids">Each element's Revit id by UniqueId (a result's detail shows it in Show's tooltip, for Select by ID).</param>
/// <param name="NotStated">A check sent anyway (the Setup form's "Check now anyway"): each fact left out, in words
/// (SetupWords.SentWithout), shown first, with Set up the facts.</param>
/// <param name="Key">The document checked by identity (DocKeys.Of), never its title (a Save As changes it): what a
/// check is compared with and its ticks carried by; null for the Setup form (UI changes 13-15, review round 2).</param>
internal sealed record PanelContent(string Project, DateTime When, ResultModel? Model, IReadOnlyList<string> Missing,
                                    int MarksAdded, IReadOnlyDictionary<string, string> Labels, string Files,
                                    string ClearWords, IReadOnlyDictionary<string, long>? Ids = null,
                                    IReadOnlyList<string>? NotStated = null, string? Key = null);

/// <summary>
/// The results panel itself (a WPF view in Revit's dockable pane, beside Properties), matching the agreed mockup
/// (docs/revit/ui_design_pass.md section 2.4): the header with Check again, the worker's state and counts, the filter
/// chips and the search, then the results list: a virtualized ListBox (an entry is made only when it scrolls into
/// view), worst first (<see cref="ResultList"/>: does not comply, needs review, check by hand or not checked, then what
/// complies, folded), every row in exactly one place. A click selects a row and its elements in Revit without moving
/// the view; Show (or Space) zooms; Enter or a double click opens its detail in place of the list (DetailView: why,
/// what to do, the figures, the law's words with Open the law, the elements by name; Back returns to the same row and
/// scroll position); Up/Down move; Ctrl+C
/// copies the row as the text file says it; Ctrl+F searches and Esc clears the search. Plain WPF: every Revit call
/// goes through the callbacks, which queue it for Revit's thread (<see cref="PanelActions"/>). Every colour is a
/// token of the theme's dictionary (<see cref="PanelLook"/>), named with SetResourceReference so it follows Revit's
/// theme; every status is drawn as its glyph and said in words, never by colour alone (<see cref="StatusLook"/>).
/// </summary>
internal sealed class ResultsView : C.UserControl, IListHost, IDetailHost, ICauseHost
{
    private readonly Action<ResultRow> _zoom;
    private readonly Action<CardRequest> _card;
    private readonly Action<ResultRow> _select;
    private readonly Action _checkAgain;
    private readonly Action _projectInformation;
    private readonly Action _setUp;
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
    private C.Grid? _searchBox;
    private readonly C.TextBlock _searchHint = Small("Search rules, sections, elements (Ctrl+F)");
    private readonly C.TextBlock _shown = Small("");
    private readonly C.ListBox _list = new();
    // UI changes 13-15: every write of _content goes through this one setter, which raises Shown (PaneExtras follows
    // it for the ribbon badge, the selection strip and the summary); never write _contentValue but here
    private PanelContent? _contentValue;
    private PanelContent? _content
    {
        get => _contentValue;
        set
        {
            _contentValue = value;
            Shown?.Invoke(this, value);
        }
    }

    // the list's state, kept across every redraw (a stale redraw, a new check): the filter, the folds, what is open
    private IReadOnlyList<ListRow> _placed = [];
    private IReadOnlyList<ListEntry> _entries = [];
    private List<ListItem> _items = [];
    private ListFilter _filter = ListFilter.All;
    private readonly HashSet<ListSection> _opened = [];
    private readonly HashSet<string> _openCounts = new(StringComparer.Ordinal);   // laws whose "+N more" is open
    private readonly HashSet<string> _openFolds = new(StringComparer.Ordinal);
    private string? _selectedId;
    private string? _detailId;                                // the row whose detail is shown, or null for the list
    private double _listOffset;                               // where the list was scrolled when the detail opened
    private bool _quiet;                                      // a selection the panel makes itself: never sent to Revit

    // PR 6: the cause cards, the "looked at" ticks, and what changed since the check before
    private bool _allCards;                                   // "+N more causes" opened
    private readonly HashSet<string> _openCards = new(StringComparer.Ordinal);
    private LookedAt _looked = new();
    private CheckChange? _change;
    private (string Project, DateTime When)? _shownCheck;     // the check shown (a stale redraw is the same check)
    // per project: the last check that arrived current (what the next is compared with), and the last check's ticks
    private readonly Dictionary<string, (DateTime When, ResultModel Model)> _compared = new(StringComparer.Ordinal);
    private readonly Dictionary<string, (ResultModel Model, LookedAt Looked, IReadOnlyDictionary<string, string> Labels)> _ticked = new(StringComparer.Ordinal);

    internal ResultsView(Action<ResultRow> zoom, Action<ResultRow> select, Action checkAgain, Action projectInformation,
                         Action<CardRequest> card, Action setUp, PanelTheme theme)
    {
        _zoom = zoom;
        _card = card;
        _select = select;
        _checkAgain = checkAgain;
        _projectInformation = projectInformation;
        _setUp = setUp;
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
        // the panel's one channel for problems and what to do about them, which comes last ("...: click Check again"):
        // wrapped, at most three lines (so it never pushes the list off), the last trimmed, the whole on hover
        _status.TextWrapping = W.TextWrapping.Wrap;
        _status.TextTrimming = W.TextTrimming.CharacterEllipsis;
        _status.MaxHeight = 3 * 1.4 * PanelTokens.TypeOf(Caption).Size;
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
            OpenDetail(row.Row.Row.Id);
        };
        W.Automation.AutomationProperties.SetName(_list, "Results");
        C.Grid.SetRow(_list, 1);
        _results.Children.Add(_list);
        PreviewKeyDown += PanelKeys;

        var all = new C.DockPanel();
        C.DockPanel.SetDock(head, C.Dock.Top);
        all.Children.Add(head);
        C.DockPanel.SetDock(SelectionSlot, C.Dock.Top);         // the selection strip's slot (UI change 14: PaneExtras)
        all.Children.Add(SelectionSlot);
        all.Children.Add(_bodyHost);
        Content = all;
        _bodyHost.Child = _missingScroll;
        _sub.Text = PaneWords.NotCheckedYet;
        _again.Visibility = PaneWords.HeaderCheckAgain(PaneShows.Welcome, _everShown) ? W.Visibility.Visible : W.Visibility.Collapsed;
        Welcome();
    }

    /// <summary>Whether a check's results were ever shown in this pane (the welcome shows until then: PaneWords.WelcomeShows).</summary>
    private bool _everShown;

    /// <summary>The empty body (the intuitive pane, change 1): the check's progress card while one runs, and the
    /// first-run welcome while no results were ever shown here (PaneWords.WelcomeShows); never over results or the
    /// Setup form (those replace the body). In the pane, never a dialog.</summary>
    private void Welcome(string? checking = null)
    {
        _missing.Children.Clear();
        if (checking is not null)
            _missing.Children.Add(Banner(PanelStatus.Review, PanelTokens.BgSurface, PanelTokens.Line, Progressing(checking), bottom: 10));
        if (!PaneWords.WelcomeShows(PaneShows.Welcome, _everShown))
            return;
        var card = new C.StackPanel { Tag = WelcomeTag };
        card.Children.Add(Typed(new C.TextBlock { Text = PaneWords.WelcomeTitle, TextWrapping = W.TextWrapping.Wrap }, "type.title"));
        foreach (var (lead, words) in PaneWords.WelcomeLines)
        {
            var t = Typed(new C.TextBlock { TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 6, 0, 0) }, Body);
            t.Inlines.Add(new W.Documents.Run(lead) { FontWeight = W.FontWeights.SemiBold });
            t.Inlines.Add(new W.Documents.Run(words));
            card.Children.Add(t);
        }
        if (checking is null)
        {
            var go = CauseCardsView.Primary("Check project", () => _checkAgain());
            go.HorizontalAlignment = W.HorizontalAlignment.Left;
            go.Margin = new W.Thickness(0, 10, 0, 0);
            card.Children.Add(go);
            card.Children.Add(Small("Also on the Gordium tab of the ribbon.", top: 4));
        }
        var frame = new C.Border { Child = card, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4), Padding = new W.Thickness(12, 10, 12, 12) };
        frame.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        frame.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        _missing.Children.Add(frame);
    }

    /// <summary>The welcome card's tag (the tests find it by it).</summary>
    internal const string WelcomeTag = "pane.welcome";

    /// <summary>The check's progress as a card (the intuitive pane, change 12): what is happening, in plain words, and
    /// that Revit is free; the bar moves on its own (no stage is measured as a share of the whole).</summary>
    private W.UIElement Progressing(string line)
    {
        var p = new C.StackPanel();
        p.Children.Add(Typed(new C.TextBlock { Text = PaneWords.Checking(_checkingProject), FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
        _progressLine = Small(line, top: 2);
        p.Children.Add(_progressLine);
        var bar = new C.ProgressBar { IsIndeterminate = true, Height = 4, Margin = new W.Thickness(0, 6, 0, 0), BorderThickness = new W.Thickness(0) };
        bar.SetResourceReference(C.Control.ForegroundProperty, PanelTokens.Accent);
        bar.SetResourceReference(C.Control.BackgroundProperty, PanelTokens.Line);
        p.Children.Add(bar);
        return p;
    }

    private string? _checkingProject;

    /// <summary>The progress card's line, ticked with the checker's seconds.</summary>
    private C.TextBlock? _progressLine;

    private const string CheckingNoResults = "Checking: no results yet";

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
        _searchBox = box;
        box.Visibility = W.Visibility.Collapsed;               // opened by Search or Ctrl+F (the intuitive pane, change 7)
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
        NewCheck(content);
        _content = content;
        _failed = false;
        _again.Visibility = W.Visibility.Visible;
        _again.IsEnabled = _checkAgainState.Enabled;             // a check still waiting keeps it greyed
        _everShown |= content.Model is not null;
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
        if (_detailId is { } open)                               // a detail open: shown again from this answer if its
            OpenDetail(open, keepOffset: true);                  // row is still listed (stale: saying so), else the list
    }

    /// <summary>A check of <paramref name="content"/>'s project that isn't the one shown (a stale redraw or a cancelled
    /// check's restore is the same check): what changed since the project's check before (CheckChanges: not compared
    /// when this answer arrived stale, nor is it then what the next one is compared with), and the ticks carried over
    /// (LookedAt.Carry: only to what is still the same). A check with no rows (a fact missing) has neither.</summary>
    private void NewCheck(PanelContent content)
    {
        if (_shownCheck == (content.Key ?? content.Project, content.When))
            return;
        _shownCheck = (content.Key ?? content.Project, content.When);
        _openCards.Clear();
        _allCards = false;
        _groups = null;
        if (content.Model is not { } model)
        {
            _change = null;
            _looked = new LookedAt();
            return;
        }
        // by the document's identity, never its title (a Save As renames it); none known: nothing compared or carried
        var key = content.Key;
        _change = key is not null && _compared.TryGetValue(key, out var before) ? CheckChanges.Between(before.Model, before.When, model) : null;
        if (key is not null && model.Stale is null)
            _compared[key] = (content.When, model);
        // the fixes' ticks too (by fix key, made with each check's own element names), where the fix is the same;
        // by the document's identity (none known: nothing carried)
        _looked = key is not null && _ticked.TryGetValue(key, out var t)
            ? LookedAt.Carry(t.Looked, t.Model, model, t.Labels, content.Labels) : new LookedAt();
        if (key is not null)
            _ticked[key] = (model, _looked, content.Labels);
    }

    /// <summary>The list's first entry: the stale notice (when stale), the worker's state (grey once stale, never
    /// green) and its counts, one wrap line per law. It scrolls away with the rows.</summary>
    private W.UIElement Summary(ResultModel model, IReadOnlyList<PanelPart> parts, bool stale)
    {
        var summary = new C.StackPanel { Margin = new W.Thickness(0, 2, 0, 2) };
        if (_content?.NotStated is { Count: > 0 } notStated)
        {
            // checked anyway: what was left out first, each making its rules need review, and the way back to Setup
            var words = new C.StackPanel();
            words.Children.Add(Typed(new C.TextBlock
            {
                Text = $"Checked without {notStated.Count} {(notStated.Count == 1 ? "fact" : "facts")}: the rules they decide need review",
                FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap,
            }, Body));
            foreach (var n in notStated)
                words.Children.Add(Small("• " + n, top: 2));
            words.Children.Add(SetUpButton());
            summary.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, words, bottom: 6));
        }
        foreach (var part in parts)
            switch (part)
            {
                case PanelPart.Stale:
                    // plain words and the way out in the banner itself (the intuitive pane, change 11); the worker's
                    // or the add-in's own stale words (a cancelled check's) on hover
                    var sw = new C.StackPanel { ToolTip = model.Stale };
                    var why = model.StaleKind ?? StaleReason.ModelChanged;
                    sw.Children.Add(Typed(new C.TextBlock { Text = PaneWords.StaleTitle(why, _content?.When ?? DateTime.Now), FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
                    sw.Children.Add(Small(PaneWords.StaleWords(why), top: 2));
                    var sa = CauseCardsView.Primary("Check again", () => _checkAgain());
                    sa.HorizontalAlignment = W.HorizontalAlignment.Left;
                    sa.Margin = new W.Thickness(0, 6, 0, 0);
                    sw.Children.Add(sa);
                    summary.Children.Add(Banner(PanelStatus.Stale, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, sw, bottom: 6));
                    break;
                case PanelPart.Code when model.Code is { } code:
                    // which code and why, the worker's words: plain when decided (never green), needs review when not,
                    // the clock once stale; the law's quoted words on hover; at most two lines (the whole on hover)
                    var codeStatus = code.Status(stale);
                    var codeWords = Typed(new C.TextBlock
                    {
                        Text = code.Words, TextWrapping = W.TextWrapping.Wrap, TextTrimming = W.TextTrimming.CharacterEllipsis,
                        MaxHeight = 2 * 1.4 * PanelTokens.TypeOf(Caption).Size, VerticalAlignment = W.VerticalAlignment.Center,
                    }, Caption);
                    Ink(codeWords, codeStatus is { } cs ? StatusLook.Colour(cs) : PanelTokens.TextMuted);
                    W.UIElement codeLine = codeStatus is { } s2 ? WithGlyph(s2, codeWords, size: 12) : codeWords;
                    var codeBox = new C.Border
                    {
                        Child = codeLine, Margin = new W.Thickness(0, 0, 0, 4),
                        ToolTip = string.Join("\n\n", new[] { code.Words, code.Tooltip }.Where(t => t is not null)),
                    };
                    W.Automation.AutomationProperties.SetName(codeBox, code.Words);
                    summary.Children.Add(codeBox);
                    break;
                case PanelPart.State when !stale:
                    // the state, then where to start (the intuitive pane, change 7): what fails, then fix 1
                    var fails = PaneWords.FilterCount(_placed, ListFilter.Fails);
                    var st = StatusLook.Of(model.StateTone, stale);
                    summary.Children.Add(WithGlyph(st, Ink(Typed(new C.TextBlock { Text = ResultText.StateWords(model.State), TextWrapping = W.TextWrapping.Wrap }, "type.state"), StatusLook.Colour(st)), size: 18));
                    summary.Children.Add(Typed(new C.TextBlock
                    {
                        Text = PaneWords.StartHere(fails, Groups.Count),
                        TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 2, 0, 2),
                    }, Body));
                    break;
                case PanelPart.State:
                    var state = StatusLook.Of(model.StateTone, stale);
                    summary.Children.Add(WithGlyph(state, Ink(Typed(new C.TextBlock
                    {
                        Text = model.Stale is null ? ResultText.StateWords(model.State)
                            : PaneWords.StaleState(ResultText.StateWords(model.State), model.StaleKind ?? StaleReason.ModelChanged),
                        TextWrapping = W.TextWrapping.Wrap,
                    }, stale ? "type.title" : "type.state"), StatusLook.Colour(state)), size: stale ? 16 : 18));   // stale: smaller, its "(before ...)" on one line
                    break;
                case PanelPart.Counts:
                    // the compact count bar (CountBar): one line per law, its short name and its most important
                    // counts (every failure), the rest behind "+N more" (opened in place), all of them in the tooltip
                    // (the intuitive pane, change 7) the filters above carry the counts, so the count by law is one fold
                    // away, open once stale (the clock on every count says the results may not hold)
                    var byLaw = _openCounts.Contains(ByLaw) || stale;
                    if (!stale)
                    {
                        var fold = CauseCardsView.Link(PaneWords.CountsByLaw(model.Counts.Select(c => CountBar.Short(c.Title)), byLaw), () =>
                        {
                            if (!_openCounts.Remove(ByLaw))
                                _openCounts.Add(ByLaw);
                            Relayout();
                        });
                        fold.Margin = new W.Thickness(0, 2, 0, 0);
                        summary.Children.Add(fold);
                    }
                    if (byLaw)
                        foreach (var line in model.Counts)
                            summary.Children.Add(CountLineView(line, stale, CountBar.Keep));
                    if (_change is { } change)
                        summary.Children.Add(ChangeLine(change, stale));
                    break;
            }
        return summary;
    }

    /// <summary>The fold key of the count by law.</summary>
    private const string ByLaw = "pane.counts_by_law";

    /// <summary>What changed since the check before (CheckChanges; the intuitive pane, change 9), under the counts: a
    /// short list, each result with its new verdict's glyph (the worker's; green only for its complies), the rest
    /// counted; the whole sentence on hover.</summary>
    private static C.Border ChangeLine(CheckChange change, bool stale)
    {
        var p = new C.StackPanel();
        if (!PaneWords.ChangeIsList(change))                   // no verdict changed: the worker's one line, as it says
            p.Children.Add(Typed(new C.TextBlock { Text = change.Words, TextWrapping = W.TextWrapping.Wrap }, Caption));
        else
        {
            p.Children.Add(Ink(Typed(new C.TextBlock { Text = PaneWords.ChangeHeading(change), TextWrapping = W.TextWrapping.Wrap }, "type.overline"), PanelTokens.TextMuted));
            foreach (var r in PaneWords.ChangesShown(change))
            {
                var w = Typed(new C.TextBlock { Text = r.Words, TextWrapping = W.TextWrapping.Wrap }, Caption);
                var line = WithGlyph(PaneWords.ChangeStatus(r, stale), w, size: 11, gap: 5);     // stale: the clock, never green
                line.Margin = new W.Thickness(0, 3, 0, 0);
                p.Children.Add(line);
            }
            if (PaneWords.ChangesMore(change) is { } more)
                p.Children.Add(Small(more, top: 3));
        }
        var b = new C.Border
        {
            Child = p, BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4),
            Padding = new W.Thickness(8, 5, 8, 6), Margin = new W.Thickness(0, 6, 0, 0), ToolTip = change.Words,
        };
        b.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        b.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        W.Automation.AutomationProperties.SetName(b, change.Words);
        return b;
    }

    /// <summary>A law's line of the count bar (CountBar.Row): its short name, the counts kept, "+N" (opens every
    /// count in place; all of them in the tooltip). A line that wraps at the pane's width is made again keeping one
    /// count fewer (CountBar.Row still shows every failure), so each law stays one line at the docked width.</summary>
    private C.WrapPanel CountLineView(CountLine line, bool stale, int keep)
    {
        var key = line.Title ?? "";
        var opened = _openCounts.Contains(key);
        var row = CountBar.Row(line, open: opened, keep: keep);
        var chips = new C.WrapPanel { Margin = new W.Thickness(0, 4, 0, 0), ToolTip = row.Tooltip };
        if (row.Title is not null)
            chips.Children.Add(Ink(Typed(new C.TextBlock
            {
                Text = row.Title, FontWeight = W.FontWeights.SemiBold,
                Margin = new W.Thickness(0, 3, 4, 0), VerticalAlignment = W.VerticalAlignment.Center,
            }, Caption), PanelTokens.TextMuted));
        foreach (var chip in row.Shown)
            chips.Children.Add(Chip(chip, stale));
        if (row.More is not null || opened)
        {
            var toggle = new C.Button
            {
                Content = Typed(new C.TextBlock { Text = opened ? "fewer" : row.More }, Caption),
                Padding = new W.Thickness(4, 0, 4, 0), Margin = new W.Thickness(0, 2, 0, 0), Focusable = false,
                ToolTip = opened ? "Show only the most important counts" : row.Tooltip,
            };
            W.Automation.AutomationProperties.SetName(toggle, opened ? $"Fewer {row.Title} counts" : $"{row.MoreWords}: {row.Title}");
            toggle.Click += (_, e) =>
            {
                e.Handled = true;
                if (!_openCounts.Remove(key))
                    _openCounts.Add(key);
                Relayout();
            };
            chips.Children.Add(toggle);
        }
        if (!opened && keep > 0)
            chips.SizeChanged += (_, _) =>
            {
                // wrapped: the first and last child on different lines; made again with one count fewer
                if (chips.Children.Count < 2 || chips.Parent is not C.Panel parent)
                    return;
                var first = chips.Children[0].TranslatePoint(new W.Point(0, 0), chips).Y;
                var last = chips.Children[^1].TranslatePoint(new W.Point(0, 0), chips).Y;
                if (last - first < 8)
                    return;
                var at = parent.Children.IndexOf(chips);
                parent.Children.RemoveAt(at);
                parent.Children.Insert(at, CountLineView(line, stale, keep - 1));
            };
        return chips;
    }

    /// <summary>The folds after the rows (what wasn't read, the details), shown when the list shows every row.</summary>
    private List<FoldItem> _folds = [];

    /// <summary>The model changed since the check: everything shown greyed (ResultRows.Stale), with why, once.</summary>
    internal void MarkStale()
    {
        if (_content is not { Model: { Stale: null } model } content)
            return;
        Show(content with { Model = ResultRows.Stale(model, content.When), MarksAdded = 0, ClearWords = "" });
    }

    /// <summary>A check that failed: every row of the last check taken down, and why (held while a check runs: its
    /// progress line stays).</summary>
    internal void Failed(string words)
    {
        _failed = true;
        _content = null;
        _detailId = null;
        _placed = [];
        _summary = null;
        _missing.Children.Clear();
        _bodyHost.Child = _missingScroll;
        Relayout();
        _sub.Text = "Not checked";
        if (words.Length == 0)
        {
            _sub.Text = _everShown ? "Not checked" : PaneWords.NotCheckedYet;
            Say("");
            Welcome();                                          // a cancelled first check: back to the empty pane
            return;
        }
        // the error as one plain sentence (the intuitive pane, change 10); the technical words (the exception, the
        // log's path) go to the clipboard and the tooltip, not the screen
        var card = new C.StackPanel { Tag = ErrorTag, ToolTip = words };
        card.Children.Add(Typed(new C.TextBlock { Text = PaneWords.ErrorTitle, FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
        card.Children.Add(Typed(new C.TextBlock { Text = PaneWords.ErrorWords, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 4, 0, 0) }, Body));
        var buttons = new C.WrapPanel { Margin = new W.Thickness(0, 8, 0, 0) };
        var again = CauseCardsView.Primary(PaneWords.TryAgain, () => _checkAgain());
        again.Margin = new W.Thickness(0, 0, 8, 0);
        buttons.Children.Add(again);
        var copy = CauseCardsView.Secondary(PaneWords.CopyDetails, () =>
        {
            try
            {
                W.Clipboard.SetText(words);
            }
            catch (System.Runtime.InteropServices.ExternalException)
            {
                // another program holds the clipboard: the details stay in the tooltip
            }
        });
        copy.ToolTip = words;
        buttons.Children.Add(copy);
        card.Children.Add(buttons);
        _missing.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, card, bottom: 6));
        Say("");
    }

    /// <summary>The error card's tag (the tests find it by it).</summary>
    internal const string ErrorTag = "pane.error";

    /// <summary>Whether the last thing shown was a failure (the error state).</summary>
    private bool _failed;

    /// <summary>What the panel shows now (CheckFlow.Had): what a cancelled check goes back to.</summary>
    internal PanelHad Had => CheckFlow.Had(_content is not null, _content?.Model is not null, _failed);

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

    /// <summary>Ticks the checking line's seconds while the checker works (Revit's thread is free then).</summary>
    private W.Threading.DispatcherTimer? _ticks;

    /// <summary>A click on Check again, queued for Revit's thread: greyed and "Checking..." until Revit takes it
    /// (a double click never queues two). The rows stay as they are (stale ones stale).</summary>
    internal void Busy(bool busy)
    {
        if (!busy)
        {
            EndProgress();
            return;
        }
        _checkAgainState.Start();
        Say(Checking);
        _again.IsEnabled = _checkAgainState.Enabled;
    }

    /// <summary>A check at <paramref name="stage"/> (CheckFlow), begun at <paramref name="since"/>: its progress line
    /// (CheckWords.Progress), the button Cancel. The earlier results stay as they are until the answer (stale ones
    /// stale, never green; an edit greys them as ever); with none, the header says no results yet. While the checker
    /// works the line counts its seconds (Revit's thread is free then; during the read nothing is drawn).</summary>
    internal void Progress(CheckStage stage, DateTime since)
    {
        _checkAgainState.Running(CheckWords.Progress(stage, DateTime.Now - since) ?? Checking);
        Say(_checkAgainState.Line);
        _again.Content = CheckWords.Button(stage);
        _again.Visibility = W.Visibility.Visible;
        _again.IsEnabled = _checkAgainState.Enabled;
        // the progress as a card where the architect is looking (the intuitive pane, change 12): in the empty body
        // (with the welcome under it on a first run), or in the Setup form's foot; over results, the line as before
        if (_content is null)
        {
            _sub.Text = CheckingNoResults;
            Welcome(_checkAgainState.Line);
            Say("");
        }
        else if (ShowsSetup)
        {
            var foot = new C.Border { Child = Progressing(_checkAgainState.Line), BorderThickness = new W.Thickness(0, 1, 0, 0), Padding = new W.Thickness(12, 8, 12, 10) };
            foot.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
            foot.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
            _setupFoot.Child = foot;
            Say("");
        }
        _ticks?.Stop();
        if (stage != CheckStage.Checking)
            return;
        _ticks = new W.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        _ticks.Tick += (_, _) =>
        {
            if (!_checkAgainState.IsRunning)
                return;
            var showing = _status.Text == _checkAgainState.Line;
            _checkAgainState.Running(CheckWords.Checking(DateTime.Now - since));
            if (showing)
                Say(_checkAgainState.Line);
            if (_progressLine is not null)
                _progressLine.Text = _checkAgainState.Line;
        };
        _ticks.Start();
    }

    /// <summary>The check ended (shown, failed, cancelled) or never began: the button Check again, usable, and the
    /// line a redraw held meanwhile (or a failure's words) shown.</summary>
    internal void EndProgress()
    {
        _ticks?.Stop();
        _ticks = null;
        Say(_checkAgainState.Stop(_status.Text));        // what the check's redraw had to say, or a failure's words
        _again.Content = CheckWords.CheckAgain;
        _again.IsEnabled = _checkAgainState.Enabled;
        _progressLine = null;
        if (ShowsSetup && _setup is not null)
            _setupFoot.Child = _setup.Footer;                   // the form's own foot back
        if (_content is null && _sub.Text == CheckingNoResults)
        {
            _sub.Text = _failed ? "Not checked" : PaneWords.NotCheckedYet;
            if (!_failed)
                Welcome();                                      // the progress card gone, the welcome as it was
        }
        if (_content is null && !_failed)
            _again.Visibility = PaneWords.HeaderCheckAgain(PaneShows.Welcome, _everShown) ? W.Visibility.Visible : W.Visibility.Collapsed;
    }

    /// <summary>A cancelled check: back to what the panel showed before it (CheckFlow.Cancel's <paramref name="had"/>):
    /// the earlier results, marked stale (never shown as the new ones: CheckWords.CancelledStale), the earlier list of
    /// what to fill in, or the empty or error state; then why (<paramref name="why"/>, or CheckWords.Cancelled).</summary>
    internal void Restore(PanelHad had, string? why)
    {
        // what is actually restored (CheckFlow.Restored), and its words: never "the results below" with none below
        var restored = CheckFlow.Restored(had, Had);
        switch (restored)
        {
            case PanelHad.Results when _content is { Model: { } model } content:
                Show(content with { Model = ResultRows.Stale(model, content.When, CheckWords.CancelledStale(content.When), StaleReason.Cancelled), MarksAdded = 0, ClearWords = "" });
                break;
            case PanelHad.Missing:
                break;                                      // what to fill in, as it was
            default:
                Failed("");                                 // the empty or error state: no rows
                if (restored == PanelHad.Nothing)
                    _failed = false;
                break;
        }
        Say(why ?? CheckWords.Cancelled(restored));
    }

    private void ShowMissing(IReadOnlyList<string> missing)
    {
        _missing.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview,
                                     Typed(new C.TextBlock { Text = "Nothing was checked: fill these in first", TextWrapping = W.TextWrapping.Wrap },
                                           "type.title"), bottom: 6));
        foreach (var m in missing)
            _missing.Children.Add(new C.TextBlock { Text = "• " + m, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 0, 0, 6) });
        _missing.Children.Add(SetUpButton());
    }

    /// <summary>"Set up the facts": the Setup form for the project shown.</summary>
    private C.Button SetUpButton()
    {
        var open = new C.Button
        {
            Content = "Set up the facts", Padding = new W.Thickness(10, 3, 10, 3), Margin = new W.Thickness(0, 4, 0, 4),
            HorizontalAlignment = W.HorizontalAlignment.Left,
        };
        open.Click += (_, _) => _setUp();
        return open;
    }

    // ---- the Setup form (SetupView; docs/decisions/2026-11-22_setup_form.md) ---------------------------------

    private SetupView? _setup;
    private C.ScrollViewer? _setupScroll;

    /// <summary>Whether the Setup form is what the pane shows.</summary>
    internal bool ShowsSetup => _setupPage is not null && ReferenceEquals(_bodyHost.Child, _setupPage);

    private C.DockPanel? _setupPage;
    private readonly C.Border _setupFoot = new();

    /// <summary>The Setup form in place of the results: "what to fill in" for a cancelled check to go back to (its
    /// content has no rows, as the missing state's: CheckFlow.Had says Missing).</summary>
    internal void ShowSetup(string project, SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open)
    {
        _content = new PanelContent(project, DateTime.Now, null, [], 0, new Dictionary<string, string>(), "", "");
        _failed = false;
        _detailId = null;
        _placed = [];
        _summary = null;
        _again.Visibility = PaneWords.HeaderCheckAgain(PaneShows.Setup, _everShown) ? W.Visibility.Visible : W.Visibility.Collapsed;
        _again.IsEnabled = _checkAgainState.Enabled;
        _sub.Text = _everShown ? $"Setup · {project}" : $"Before the first check · {project}";
        _checkingProject = project;
        Say(_checkAgainState.Status(""));
        _setupScroll = new C.ScrollViewer
        {
            VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled,
        };
        // the form scrolls; its one action (SetupView.Footer) is pinned at the pane's foot (the intuitive pane, change 3)
        var page = new C.DockPanel();
        if (_setupFoot.Parent is C.Panel before)
            before.Children.Remove(_setupFoot);                 // the form shown again (the facts read again): one foot
        C.DockPanel.SetDock(_setupFoot, C.Dock.Bottom);
        page.Children.Add(_setupFoot);
        page.Children.Add(_setupScroll);
        _setupPage = page;
        _bodyHost.Child = page;
        RedrawSetup(screen, draft, handlers, notice, open, force: true);
        Relayout();
    }

    /// <summary>The form drawn again at the same scroll position; only while it is shown (never over results).</summary>
    internal void RedrawSetup(SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open, bool force = false)
    {
        if (_setupScroll is null || !force && !ShowsSetup)
            return;
        var offset = _setupScroll.VerticalOffset;
        _setup = new SetupView(screen, draft, handlers, notice, open);
        _setupScroll.Content = _setup;
        if (!_checkAgainState.IsRunning)                        // while a check runs, its progress holds the foot
            _setupFoot.Child = _setup.Footer;
        _setupScroll.ScrollToVerticalOffset(offset);
    }

    // ---- the list ------------------------------------------------------------------------------------------

    /// <summary>The filter chips, one pressed: the count bar's kinds (ResultList.Chips), each with its glyph (the
    /// clock once stale).</summary>
    private void Chips(bool stale)
    {
        _chips.Children.Clear();
        foreach (var chip in ResultList.Chips(_placed, stale))
        {
            // each filter says how many results it shows (the intuitive pane, change 7)
            W.UIElement words = Typed(new C.TextBlock { Text = $"{chip.Words} {PaneWords.FilterCount(_placed, chip.Filter)}", VerticalAlignment = W.VerticalAlignment.Center }, Caption);
            var button = new C.Primitives.ToggleButton
            {
                Content = chip.Status is { } s ? WithGlyph(s, words, size: 11) : words, IsChecked = chip.Filter == _filter,
                Padding = new W.Thickness(7, 1, 8, 1), Margin = new W.Thickness(0, 0, 4, 4),
                ToolTip = chip.Filter switch
                {
                    ListFilter.All => "Every result",
                    ListFilter.Fails => "Only what does not comply",
                    ListFilter.Review => "What needs review, is to check by hand, or isn't checked",
                    _ => "Only what complies or doesn't apply",
                },
            };
            var filter = chip.Filter;
            button.Click += (_, _) =>
            {
                _filter = filter;
                foreach (var b in _chips.Children.OfType<C.Primitives.ToggleButton>().Where(b => !Equals(b.Tag, SearchTag)))
                    b.IsChecked = ReferenceEquals(b, button);
                Relayout();
            };
            _chips.Children.Add(button);
        }
        var search = new C.Primitives.ToggleButton
        {
            Content = Typed(new C.TextBlock { Text = "Search" }, Caption), Padding = new W.Thickness(7, 1, 8, 1), Margin = new W.Thickness(0, 0, 4, 4),
            ToolTip = "Search rules, sections and elements (Ctrl+F)", IsChecked = _searchBox?.Visibility == W.Visibility.Visible, Tag = SearchTag,
        };
        W.Automation.AutomationProperties.SetName(search, "Search");
        search.Click += (_, _) =>
        {
            ShowSearch(search.IsChecked == true);
            if (search.IsChecked == true)
                _search.Focus();
        };
        _chips.Children.Add(search);
    }

    /// <summary>The list again, from the rows placed, the filter, the search and the folds; the selected row kept
    /// when it is still shown.</summary>
    private void Relayout()
    {
        var labels = _content?.Labels;
        var stale = _content?.Model?.Stale is not null;
        var layout = ResultList.WithCauses(ResultList.Layout(_placed, _filter, _search.Text, labels, stale, _opened),
                                           _summary is not null && AllCards.Count > 0, _filter, _search.Text);
        _entries = _summary is null ? layout : ResultList.WithSummary(layout);
        var items = new List<ListItem>(_entries.Count + 2);
        RowItem? selected = null;
        foreach (var e in _entries)
            switch (e)
            {
                case ListSummary:
                    items.Add(new SummaryItem(this, _summary!));
                    break;
                case ListCauses:
                    items.Add(new CausesItem(this, () => CauseCardsView.Build(this)));
                    break;
                case ListHeading h:
                    items.Add(new HeadingItem(this, h));
                    break;
                case ListSubheading s:
                    items.Add(new SubItem(this, s));
                    break;
                case ListRowEntry r:
                    var row = new RowItem(this, r.Row);
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
            ? ResultList.Terms(_search.Text).Count > 0 ? $"No result matches “{_search.Text.Trim()}” here." : "No result here."
            : $"Showing {rows} of {PaneWords.Results(_placed.Count)}.";
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
                OpenDetail(row.Row.Row.Id);
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
        if (_detail is not null && ReferenceEquals(_bodyHost.Child, _detail) && DetailKey(e))
        {
            e.Handled = true;
            return;
        }
        if (e.Key == I.Key.F && (I.Keyboard.Modifiers & I.ModifierKeys.Control) != 0 && ReferenceEquals(_bodyHost.Child, _results))
        {
            ShowSearch(true);
            _search.Focus();
            _search.SelectAll();
            e.Handled = true;
        }
    }

    /// <summary>The search box shown or folded (Search on the filters' line, or Ctrl+F); a folded box keeps no words.</summary>
    private void ShowSearch(bool show)
    {
        if (_searchBox is null)
            return;
        _searchBox.Visibility = show ? W.Visibility.Visible : W.Visibility.Collapsed;
        foreach (var t in _chips.Children.OfType<C.Primitives.ToggleButton>().Where(t => Equals(t.Tag, SearchTag)))
            t.IsChecked = show;
        if (!show && _search.Text.Length > 0)
            _search.Clear();
    }

    private const string SearchTag = "pane.search";

    /// <summary>Ctrl+C: the row as the text file writes it (stale: when it was checked), on the clipboard.</summary>
    private void Copy(RowItem row) => Copy(row.Row);

    private void Copy(ListRow row)
    {
        var text = ResultList.CopyText(row.Row, _content?.Labels, _content?.Model?.Stale is null ? null : _content.When,
                                       _content?.Model?.StaleKind ?? StaleReason.ModelChanged);
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

    // ---- the detail (IDetailHost) ---------------------------------------------------------------------------

    private W.FrameworkElement? _detail;

    /// <summary>The detail's keys: Backspace, Esc or Alt+Left back; Alt+Up / Alt+Down the previous or next row; Space
    /// shows the elements (not on a button: Space presses it); Ctrl+C copies the row. Any other is the control's own.</summary>
    private bool DetailKey(I.KeyEventArgs e)
    {
        var mods = I.Keyboard.Modifiers;
        var key = e.Key == I.Key.System ? e.SystemKey : e.Key;
        switch (key)
        {
            case I.Key.Back or I.Key.Escape when mods == I.ModifierKeys.None:
            case I.Key.Left when mods == I.ModifierKeys.Alt:
                Back();
                return true;
            case I.Key.Up or I.Key.Down when mods == I.ModifierKeys.Alt:
                Step(key == I.Key.Down ? 1 : -1);
                return true;
            case I.Key.Space when mods == I.ModifierKeys.None && e.OriginalSource is not C.Primitives.ButtonBase:
                ShowElements(null);
                return true;
            case I.Key.C when mods == I.ModifierKeys.Control && DetailRow() is { } row:
                Copy(row);
                return true;
        }
        return false;
    }

    /// <summary>The row whose detail is open, as the list shows it now, or null.</summary>
    private ListRow? DetailRow() =>
        _detailId is { } id ? _entries.OfType<ListRowEntry>().Select(e => e.Row).FirstOrDefault(r => r.Row.Id == id) : null;

    /// <summary>Enter or a double click: row <paramref name="id"/>'s detail in place of the list (the list kept as it
    /// is, its scroll position remembered); a row the list no longer shows (a new check without it) leaves the list.</summary>
    private void OpenDetail(string id, bool keepOffset = false)
    {
        var (rows, index) = Details.Among(_entries, id);
        if (index < 0)
        {
            _detailId = null;
            _bodyHost.Child = _content?.Model is null ? _missingScroll : _results;
            return;
        }
        if (!keepOffset && _detailId is null && Find<C.ScrollViewer>(_list) is { } sv)
            _listOffset = sv.VerticalOffset;
        _detailId = id;
        _selectedId = id;
        var stale = _content?.Model?.Stale is not null ? _content.When : (DateTime?)null;
        var detail = Details.Of(rows[index], index, rows.Count, _content?.Labels, stale, _content?.Ids, _content?.Model?.StaleKind ?? StaleReason.ModelChanged);
        _detail = DetailView.Build(detail, this, canStepBack: index > 0, canStepOn: index < rows.Count - 1);
        _bodyHost.Child = _detail;
        _detail.Focus();
    }

    /// <summary>Back to the list, at the same row, selected and focused, and the same scroll position.</summary>
    public void Back()
    {
        if (_detailId is not { } id)
            return;
        _detailId = null;
        _bodyHost.Child = _results;
        _results.UpdateLayout();
        if (Find<C.ScrollViewer>(_list) is { } sv)
            sv.ScrollToVerticalOffset(_listOffset);
        var at = _items.FindIndex(i => i is RowItem r && r.Row.Row.Id == id);
        if (at < 0)
            return;
        _quiet = true;                                            // already selected in Revit
        try
        {
            _list.SelectedIndex = at;
        }
        finally
        {
            _quiet = false;
        }
        _list.UpdateLayout();
        (_list.ItemContainerGenerator.ContainerFromIndex(at) as C.ListBoxItem)?.Focus();
    }

    /// <summary>The previous or next row's detail, its elements selected in Revit (the view unmoved).</summary>
    public void Step(int step)
    {
        if (_detailId is not { } id)
            return;
        var (rows, index) = Details.Among(_entries, id);
        var to = index + step;
        if (index < 0 || to < 0 || to >= rows.Count)
            return;
        OpenDetail(rows[to].Row.Id, keepOffset: true);
        _select(rows[to].Row);
    }

    /// <summary>Show: zoom to the row's elements, or to one of them.</summary>
    public void ShowElements(string? uid)
    {
        if (DetailRow() is not { } row)
            return;
        if (row.Row.Elements.Count == 0)
        {
            Say($"{row.Row.Name} names no element in the model to show.");
            return;
        }
        _zoom(uid is null ? row.Row : row.Row with { Elements = [uid] });
    }

    /// <summary>Open the law: the worker's link, in the architect's browser or PDF reader.</summary>
    public void OpenLaw(LawLink link)
    {
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(link.Url) { UseShellExecute = true });
            Say($"Opened {link.Citation}.");
        }
        catch (Exception x) when (x is System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            Say($"Couldn't open {link.Citation} ({x.Message}): its address is {link.Url}");
        }
    }

    public void CheckAgain() => _checkAgain();

    private static T? Find<T>(W.DependencyObject root) where T : W.DependencyObject
    {
        for (var i = 0; i < M.VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var c = M.VisualTreeHelper.GetChild(root, i);
            if (c is T t)
                return t;
            if (Find<T>(c) is { } d)
                return d;
        }
        return null;
    }

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

    // ---- the cause cards and the looked-at ticks (ICauseHost, PR 6) ----------------------------------------

    public IReadOnlyList<CauseCard> AllCards => _content?.Model?.Causes ?? [];

    /// <summary>The worker's cards joined where they share one fix, ranked (Fixes.Of; the intuitive pane, change 4).</summary>
    public IReadOnlyList<Fix> Groups => _groups ??= Fixes.Of(AllCards, Labels);

    private IReadOnlyList<Fix>? _groups;

    public bool AllShown => _allCards;

    public void ShowAllCards(bool all)
    {
        _allCards = all;
        Relayout();
    }

    public bool IsOpen(Fix group) => _openCards.Contains(group.Key);

    public void SetOpen(Fix group, bool open)
    {
        if (open)
            _openCards.Add(group.Key);
        else
            _openCards.Remove(group.Key);
        Relayout();
    }

    /// <summary>A card's one button: Show or Set in Properties (its elements selected, on Revit's thread), Open
    /// Project Information, or the card opened on its results (measure by hand, decide).</summary>
    public void Act(Fix group, CardAction action)
    {
        var first = group.Members[0];
        switch (action)
        {
            case CardAction.Show or CardAction.ShowAndProperties:
                _card(new CardRequest(first, action, Fixes.ShowIds(group, Labels), Short(group.Title)));
                break;
            case CardAction.ProjectInformation:
                _projectInformation();
                Say(Fixes.Note(group) ?? "");
                break;
            case CardAction.ByHand or CardAction.Decide:
                if (!IsOpen(group))
                    SetOpen(group, true);
                break;
        }
    }

    public void ShowRoom(CauseCard card, CauseRoom room) => _card(new CardRequest(card, CardAction.Show, [room.Id], room.Name));

    public void OpenRow(string id) => OpenDetail(id);

    /// <summary>Every write of the pane's content (its one setter): a check's (stale once the model changed), the
    /// Setup form's (no rows, nothing to set), or null when its rows are taken down (UI changes 13 to 15: PaneExtras).</summary>
    internal static event Action<ResultsView, PanelContent?>? Shown;

    /// <summary>The selection strip's place, under the header (UI change 14: PaneExtras fills it).</summary>
    internal C.Border SelectionSlot { get; } = new();

    /// <summary>A result opened from the selection strip (UI change 14): its detail, after clearing a filter, a search
    /// or the fold that hides it in the list.</summary>
    internal void OpenResult(string id)
    {
        if (!_entries.OfType<ListRowEntry>().Any(e => e.Row.Row.Id == id))
        {
            _filter = ListFilter.All;
            _opened.Add(ListSection.Complies);
            _search.Text = "";
            Chips(_content?.Model?.Stale is not null);
            Relayout();
        }
        OpenDetail(id);
    }

    public IReadOnlyDictionary<string, string>? Labels => _content?.Labels;

    public IReadOnlyList<ListRow> Placed => _placed;

    public bool Stale => _content?.Model?.Stale is not null;

    public LookedAt Looked => _looked;

    public void TickCard(Fix group, bool ticked)
    {
        _looked.SetCard(group.Key, ticked);
        RefreshTicks();
    }

    public void TickRow(ListRow row, bool ticked)
    {
        _looked.SetRow(row, ticked);
        RefreshTicks();
    }

    public bool IsLooked(string id) => _looked.Row(id);

    /// <summary>The open detail's row's tick.</summary>
    public bool DetailLooked => DetailRow() is { } r && _looked.Row(r.Row.Id);

    public void TickDetail(bool ticked)
    {
        if (DetailRow() is { } r)
            TickRow(r, ticked);
    }

    /// <summary>Every tick and progress line on screen shown as the ticks are now (a tick in a card's rows, in the list
    /// and in the detail is one tick), without making the list again (its scroll and selection stay).</summary>
    private void RefreshTicks()
    {
        foreach (var root in new W.DependencyObject?[] { _list, _detail })
            if (root is not null)
                foreach (var e in Descendants(root))
                    switch (e)
                    {
                        case C.CheckBox { Tag: CauseCardsView.TickTag t } box:
                            box.IsChecked = t.Card ? _looked.Card(t.Key) : _looked.Row(t.Key);
                            break;
                        case C.TextBlock { Tag: CauseCardsView.ProgressTag } line:
                            line.Text = Fixes.Progress(_looked, Groups, _placed);        // the same words as when drawn
                            break;
                    }
    }

    private static IEnumerable<W.DependencyObject> Descendants(W.DependencyObject root)
    {
        for (var i = 0; i < M.VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var c = M.VisualTreeHelper.GetChild(root, i);
            yield return c;
            foreach (var d in Descendants(c))
                yield return d;
        }
    }

    /// <summary>A cause's words up to its first ": " (the names after it are on the card), for the panel's line.</summary>
    private static string Short(string words) =>
        words.IndexOf(": ", StringComparison.Ordinal) is var at and > 0 ? words[..at] : words;

    // ---- small pieces --------------------------------------------------------------------------------------

    private const string Body = "type.body";
    private const string Caption = "type.caption";

    /// <summary>The text with its type token's style (size, weight, family).</summary>
    private static C.TextBlock Typed(C.TextBlock t, string token) => EntryView.Typed(t, token);

    /// <summary>The text in a colour token.</summary>
    private static C.TextBlock Ink(C.TextBlock t, string token) => EntryView.Ink(t, token);

    /// <summary>The status's glyph, then the words that say it: shape and word together, never colour alone.</summary>
    private static C.DockPanel WithGlyph(PanelStatus status, W.UIElement words, double size, double gap = 6)
    {
        var glyph = PanelLook.Glyph(status, size);
        glyph.Margin = new W.Thickness(0, 0, gap, 0);
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
            Padding = new W.Thickness(8, 5, 8, 5), Margin = new W.Thickness(0, 0, 0, bottom),
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
            Child = WithGlyph(status, Typed(new C.TextBlock { Text = PaneWords.Count(chip.Words) }, Caption), size: 10, gap: 4),
            BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(8), Padding = new W.Thickness(5, 1, 6, 1),
            Margin = new W.Thickness(0, 2, 3, 0),
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
