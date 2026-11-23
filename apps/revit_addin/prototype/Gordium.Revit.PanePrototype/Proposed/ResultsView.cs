using Gordium.Revit.Reading;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;
using I = System.Windows.Input;

namespace Gordium.Revit.PanePrototype.Proposed;

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
internal sealed record PanelContent(string Project, DateTime When, ResultModel? Model, IReadOnlyList<string> Missing,
                                    int MarksAdded, IReadOnlyDictionary<string, string> Labels, string Files,
                                    string ClearWords, IReadOnlyDictionary<string, long>? Ids = null,
                                    IReadOnlyList<string>? NotStated = null);

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
    private PanelContent? _content;

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
    private readonly Dictionary<string, (ResultModel Model, LookedAt Looked)> _ticked = new(StringComparer.Ordinal);

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
        all.Children.Add(_bodyHost);
        Content = all;
        _bodyHost.Child = _missingScroll;
        _sub.Text = "Not checked yet";
        _again.Visibility = W.Visibility.Collapsed;          // PROTOTYPE: the welcome's Check project is the one action
        Welcome();
    }

    /// <summary>PROTOTYPE: whether a check's results were ever shown in this pane (the welcome shows until then).</summary>
    private bool _everShown;

    /// <summary>PROTOTYPE: the first-run welcome, in the pane (never a dialog), until the first check's results arrive;
    /// never over results (Show replaces the body). Three lines: what Gordium does, that it never says pass without
    /// the facts, and how to start.</summary>
    private void Welcome(string? checking = null)
    {
        _missing.Children.Clear();
        if (checking is not null)
            _missing.Children.Add(Banner(PanelStatus.Review, PanelTokens.BgSurface, PanelTokens.Line, Progressing(checking), bottom: 10));
        var card = new C.StackPanel();
        card.Children.Add(Typed(new C.TextBlock { Text = "Welcome to Gordium", TextWrapping = W.TextWrapping.Wrap }, "type.title"));
        foreach (var (lead, words) in new[]
                 {
                     ("What it does. ", "Checks this project, rule by rule, against its city's zoning and the state's egress code, with the law's exact words."),
                     ("Never a false pass. ", "What Gordium can't measure or wasn't told is marked needs review, never complies."),
                     ("To start: ", "click Check project. If a fact it needs is missing, it asks for it here first."),
                 })
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

    /// <summary>PROTOTYPE: the check's progress as a card: what is happening, in plain words, and that Revit is free.</summary>
    private W.UIElement Progressing(string line)
    {
        var p = new C.StackPanel();
        p.Children.Add(Typed(new C.TextBlock { Text = "Checking " + (_checkingProject ?? "this project") + "…", FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
        p.Children.Add(Small(line, top: 2));
        var bar = new C.ProgressBar { IsIndeterminate = false, Value = 60, Height = 4, Margin = new W.Thickness(0, 6, 0, 0), BorderThickness = new W.Thickness(0) };
        bar.SetResourceReference(C.Control.ForegroundProperty, PanelTokens.Accent);
        bar.SetResourceReference(C.Control.BackgroundProperty, PanelTokens.Line);
        p.Children.Add(bar);
        return p;
    }

    private string? _checkingProject;

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
        box.Visibility = W.Visibility.Collapsed;               // PROTOTYPE: opened by Search (or Ctrl+F)
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
        if (_shownCheck == (content.Project, content.When))
            return;
        _shownCheck = (content.Project, content.When);
        _openCards.Clear();
        _allCards = false;
        _groups = null;
        if (content.Model is not { } model)
        {
            _change = null;
            _looked = new LookedAt();
            return;
        }
        var key = content.Project;
        _change = _compared.TryGetValue(key, out var before) ? CheckChanges.Between(before.Model, before.When, model) : null;
        if (model.Stale is null)
            _compared[key] = (content.When, model);
        _looked = _ticked.TryGetValue(key, out var t) ? LookedAt.Carry(t.Looked, t.Model, model) : new LookedAt();
        _ticked[key] = (model, _looked);
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
                    // PROTOTYPE: plain words and the way out in the banner itself
                    var sw = new C.StackPanel();
                    sw.Children.Add(Typed(new C.TextBlock { Text = $"The model changed after this check ({_content?.When:HH:mm})", FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
                    sw.Children.Add(Small("Any result below may have changed: they are greyed until you check again.", top: 2));
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
                    // PROTOTYPE: the state, then one plain sentence counted from the rows placed, then where to start
                    var fails = _placed.Count(r => r.Section == ListSection.Fails);
                    var review = _placed.Count(r => r.Section == ListSection.Review);
                    var byHand = _placed.Count(r => r.Section == ListSection.ByHand);
                    var ok = _placed.Count(r => r.Section == ListSection.Complies && r.Status == PanelStatus.Complies);
                    var st = StatusLook.Of(model.StateTone, false);
                    summary.Children.Add(WithGlyph(st, Ink(Typed(new C.TextBlock { Text = ResultText.StateWords(model.State), TextWrapping = W.TextWrapping.Wrap }, "type.state"), StatusLook.Colour(st)), size: 18));
                    summary.Children.Add(Typed(new C.TextBlock
                    {
                        Text = fails > 0 ? (Groups.Count > 0 ? "Start with what fails, just below; then fix 1." : "Start with what fails, just below.")
                             : Groups.Count > 0 ? "Nothing fails. Start with fix 1 below." : "",
                        TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 2, 0, 2),
                    }, Body));
                    break;
                case PanelPart.State:
                    var state = StatusLook.Of(model.StateTone, stale);
                    summary.Children.Add(WithGlyph(state, Ink(Typed(new C.TextBlock
                    {
                        Text = ResultText.StateWords(model.State) + (model.Stale is null ? "" : " (before the model changed)"),
                        TextWrapping = W.TextWrapping.Wrap,
                    }, stale ? "type.title" : "type.state"), StatusLook.Colour(state)), size: stale ? 16 : 18));   // stale: smaller, its "(before the model changed)" on one line
                    break;
                case PanelPart.Counts:
                    // the compact count bar (CountBar): one line per law, its short name and its most important
                    // counts (every failure), the rest behind "+N more" (opened in place), all of them in the tooltip
                    // PROTOTYPE: the filters above carry the counts; the worker's count by law is one fold away
                    var byLaw = _openCounts.Contains("__by_law") || stale;
                    if (!stale)
                    {
                        var fold = CauseCardsView.Link(byLaw ? "Hide the counts by law" : "Counts by law (" + string.Join(", ", model.Counts.Select(c => CountBar.Short(c.Title)).Where(t => t is not null)) + ")", () =>
                        {
                            if (!_openCounts.Remove("__by_law"))
                                _openCounts.Add("__by_law");
                            Relayout();
                        });
                        fold.Margin = new W.Thickness(0, 2, 0, 0);
                        summary.Children.Add(fold);
                    }
                    if (byLaw)
                        foreach (var line in model.Counts)
                            summary.Children.Add(CountLineView(line, stale, CountBar.Keep));
                    if (_change is { } change)
                        summary.Children.Add(ChangeLine(change));
                    break;
            }
        return summary;
    }

    /// <summary>What changed since the check before (CheckChanges), one line under the counts: the worker's verdicts
    /// only, by row id; plain (never a status colour: it says what changed, not whether it passes), the whole on hover.</summary>
    private C.Border ChangeLine(CheckChange change)
    {
        // PROTOTYPE: what changed as a short list, each result with the glyph of its new verdict (the worker's), the
        // rest counted; the whole sentence on hover
        var p = new C.StackPanel();
        p.Children.Add(Ink(Typed(new C.TextBlock { Text = $"WHAT CHANGED SINCE THE LAST CHECK · {change.Rows.Count} verdict{(change.Rows.Count == 1 ? "" : "s")}", TextWrapping = W.TextWrapping.Wrap }, "type.overline"), PanelTokens.TextMuted));
        foreach (var r in change.Rows.Take(4))
        {
            var tone = r.After switch
            {
                Gordium.Worker.Verdict.DoesNotComply => Tone.Fails,
                Gordium.Worker.Verdict.Complies => Tone.Complies,
                Gordium.Worker.Verdict.NotApplicable => Tone.Neutral,
                _ => Tone.Review,
            };
            var w = Typed(new C.TextBlock { Text = r.Words, TextWrapping = W.TextWrapping.Wrap }, Caption);
            var line = WithGlyph(StatusLook.Of(tone, false), w, size: 11, gap: 5);
            line.Margin = new W.Thickness(0, 3, 0, 0);
            p.Children.Add(line);
        }
        var rest = change.Rows.Count - Math.Min(4, change.Rows.Count);
        var more = new List<string>();
        if (rest > 0) more.Add($"{rest} more changed verdict{(rest == 1 ? "" : "s")}");
        if (change.Said > 0) more.Add($"{change.Said} more say something new");
        if (more.Count > 0)
            p.Children.Add(Small("And " + string.Join("; ", more) + " (hover for all).", top: 3));
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
        // PROTOTYPE: the error as one plain sentence; the technical words go to the clipboard, not the screen
        var card = new C.StackPanel();
        card.Children.Add(Typed(new C.TextBlock { Text = "Gordium couldn't finish this check", FontWeight = W.FontWeights.SemiBold, TextWrapping = W.TextWrapping.Wrap }, Body));
        card.Children.Add(Typed(new C.TextBlock { Text = "Nothing was checked, so nothing here passes or fails. Your model wasn't changed.", TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, 4, 0, 0) }, Body));
        var buttons = new C.WrapPanel { Margin = new W.Thickness(0, 8, 0, 0) };
        var again = CauseCardsView.Primary("Try again", () => _checkAgain());
        again.Margin = new W.Thickness(0, 0, 8, 0);
        buttons.Children.Add(again);
        var copy = CauseCardsView.Secondary("Copy details for support", () => W.Clipboard.SetText(words));
        copy.ToolTip = words;
        buttons.Children.Add(copy);
        card.Children.Add(buttons);
        _missing.Children.Add(Banner(PanelStatus.Review, PanelTokens.StatusReviewFill, PanelTokens.StatusReview, card, bottom: 6));
        Say("");
    }

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
        if (_content is null)
        {
            _sub.Text = "Checking: no results yet";
            Welcome(_checkAgainState.Line);
            Say("");
        }
        else if (ShowsSetup && _setupFoot is not null)
        {
            _setupFoot.Child = Progressing(_checkAgainState.Line);
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
        if (_content is null && _sub.Text == "Checking this project: no results yet")
            _sub.Text = _failed ? "Not checked" : "Click Check project on the Gordium tab to check this project.";
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
                Show(content with { Model = ResultRows.Stale(model, content.When, CheckWords.CancelledStale(content.When)), MarksAdded = 0, ClearWords = "" });
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
    private C.Border? _setupFoot;

    /// <summary>PROTOTYPE: the Setup form's one action, pinned at the pane's foot (today Save is below every fact
    /// group, off a docked pane's screen): how many needed facts are chosen, Save and check, and Check without them.</summary>
    private C.Border SetupFooter(SetupScreen screen, SetupDraft draft, SetupHandlers handlers)
    {
        var needed = screen.Fields.Where(f => f.Required).ToList();
        var chosen = needed.Count(f => f.IsSet || draft.Chosen(f.Mark) is not null);
        var changes = screen.Fields.Count(f => draft.Chosen(f.Mark) is { } c && c != f.Current);
        var p = new C.StackPanel();
        var street = needed.Any(f => f.Kind == FieldKind.StreetPick && !f.IsSet && draft.Chosen(f.Mark) is null);
        p.Children.Add(Typed(new C.TextBlock
        {
            Text = $"{screen.Needed.Count} {(screen.Needed.Count == 1 ? "fact" : "facts")} needed" + (changes > 0 ? $"; {changes} chosen, not saved yet" : "; none chosen yet") +
                   (street ? ". The street edge is picked on the plan (Pick on plan, above)." : "."),
            TextWrapping = W.TextWrapping.Wrap,
        }, Caption));
        var line = new C.DockPanel { Margin = new W.Thickness(0, 6, 0, 0), LastChildFill = false };
        var save = CauseCardsView.Primary(changes == 0 ? "Save and check" : $"Save {changes} {(changes == 1 ? "fact" : "facts")} and check", handlers.Save);
        save.IsEnabled = changes > 0;
        save.ToolTip = $"Writes only what you chose to Project Information, as one undo step ({SetupWrites.FactsTransaction}), then checks";
        C.DockPanel.SetDock(save, C.Dock.Left);
        line.Children.Add(save);
        var anyway = CauseCardsView.Link("Check without them", handlers.Anyway);
        anyway.ToolTip = "Check with what is set now: each fact still missing makes the rules it decides need review, never a pass";
        anyway.VerticalAlignment = W.VerticalAlignment.Center;
        anyway.Margin = new W.Thickness(12, 0, 0, 0);
        C.DockPanel.SetDock(anyway, C.Dock.Left);
        line.Children.Add(anyway);
        p.Children.Add(line);
        var foot = new C.Border { Child = p, BorderThickness = new W.Thickness(0, 1, 0, 0), Padding = new W.Thickness(12, 8, 12, 10) };
        foot.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        foot.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        _setupFoot = foot;
        return foot;
    }

    /// <summary>The Setup form in place of the results: "what to fill in" for a cancelled check to go back to (its
    /// content has no rows, as the missing state's: CheckFlow.Had says Missing).</summary>
    internal void ShowSetup(string project, SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open)
    {
        _content = new PanelContent(project, DateTime.Now, null, [], 0, new Dictionary<string, string>(), "", "");
        _failed = false;
        _detailId = null;
        _placed = [];
        _summary = null;
        _again.Visibility = _everShown ? W.Visibility.Visible : W.Visibility.Collapsed;
        _again.IsEnabled = _checkAgainState.Enabled;
        _sub.Text = $"Before the first check · {project}";
        _checkingProject = project;
        Say(_checkAgainState.Status(""));
        _setupScroll = new C.ScrollViewer
        {
            VerticalScrollBarVisibility = C.ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = C.ScrollBarVisibility.Disabled,
        };
        RedrawSetup(screen, draft, handlers, notice, open, force: true);
        var page = new C.DockPanel();
        var foot = SetupFooter(screen, draft, handlers);
        C.DockPanel.SetDock(foot, C.Dock.Bottom);
        page.Children.Add(foot);
        page.Children.Add(_setupScroll);
        _setupPage = page;
        _bodyHost.Child = page;
        Relayout();
    }

    /// <summary>The form drawn again at the same scroll position; only while it is shown (never over results).</summary>
    internal void RedrawSetup(SetupScreen screen, SetupDraft draft, SetupHandlers handlers, string? notice, HashSet<string> open, bool force = false)
    {
        if (_setupScroll is null || !force && !ReferenceEquals(_bodyHost.Child, _setupScroll))
            return;
        var offset = _setupScroll.VerticalOffset;
        _setup = new SetupView(screen, draft, handlers, notice, open);
        _setupScroll.Content = _setup;
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
            // PROTOTYPE: each filter says how many results it shows (counted from the rows placed)
            var n = chip.Filter switch
            {
                ListFilter.Fails => _placed.Count(r => r.Section == ListSection.Fails),
                ListFilter.Review => _placed.Count(r => r.Section is ListSection.Review or ListSection.ByHand),
                ListFilter.Complies => _placed.Count(r => r.Section == ListSection.Complies),
                _ => _placed.Count,
            };
            W.UIElement words = Typed(new C.TextBlock { Text = $"{chip.Words} {n}", VerticalAlignment = W.VerticalAlignment.Center }, Caption);
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
        var search = new C.Primitives.ToggleButton
        {
            Content = Typed(new C.TextBlock { Text = "Search" }, Caption), Padding = new W.Thickness(7, 1, 8, 1), Margin = new W.Thickness(0, 0, 4, 4),
            ToolTip = "Search rules, sections and elements (Ctrl+F)", IsChecked = _searchBox?.Visibility == W.Visibility.Visible,
        };
        search.Click += (_, _) =>
        {
            if (_searchBox is not null)
                _searchBox.Visibility = search.IsChecked == true ? W.Visibility.Visible : W.Visibility.Collapsed;
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
            _search.Focus();
            _search.SelectAll();
            e.Handled = true;
        }
    }

    /// <summary>Ctrl+C: the row as the text file writes it (stale: when it was checked), on the clipboard.</summary>
    private void Copy(RowItem row) => Copy(row.Row);

    private void Copy(ListRow row)
    {
        var text = ResultList.CopyText(row.Row, _content?.Labels, _content?.Model?.Stale is null ? null : _content.When);
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
        var detail = Details.Of(rows[index], index, rows.Count, _content?.Labels, stale, _content?.Ids);
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

    /// <summary>PROTOTYPE: the worker's cards joined where they share one fix, ranked (CardGroups).</summary>
    public IReadOnlyList<CardGroup> Groups => _groups ??= CardGroups.Of(AllCards, Labels);

    private IReadOnlyList<CardGroup>? _groups;

    public bool AllShown => _allCards;

    public void ShowAllCards(bool all)
    {
        _allCards = all;
        Relayout();
    }

    public bool IsOpen(CardGroup group) => _openCards.Contains(group.Key);

    public void SetOpen(CardGroup group, bool open)
    {
        if (open)
            _openCards.Add(group.Key);
        else
            _openCards.Remove(group.Key);
        Relayout();
    }

    /// <summary>A card's one button: Show or Set in Properties (its elements selected, on Revit's thread), Open
    /// Project Information, or the card opened on its results (measure by hand, decide).</summary>
    public void Act(CardGroup group, CardAction action)
    {
        var first = group.Members[0];
        switch (action)
        {
            case CardAction.Show or CardAction.ShowAndProperties:
                _card(new CardRequest(first, action, group.Elements.Where(e => Labels?.ContainsKey(e) == true).ToList(), Short(group.Title)));
                break;
            case CardAction.ProjectInformation:
                _projectInformation();
                Say(CardGroups.Note(group, Labels) ?? "");
                break;
            case CardAction.ByHand or CardAction.Decide:
                if (!IsOpen(group))
                    SetOpen(group, true);
                break;
        }
    }

    public void ShowRoom(CauseCard card, CauseRoom room) => _card(new CardRequest(card, CardAction.Show, [room.Id], room.Name));

    public void OpenRow(string id) => OpenDetail(id);

    public IReadOnlyDictionary<string, string>? Labels => _content?.Labels;

    public IReadOnlyList<ListRow> Placed => _placed;

    public bool Stale => _content?.Model?.Stale is not null;

    public LookedAt Looked => _looked;

    public void TickCard(CardGroup group, bool ticked)
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
                            line.Text = $"Looked at: {Groups.Count(g => _looked.Card(g.Key))} of {Groups.Count} fixes · {_looked.Rows.Count} of {_placed.Count(LookedAt.Tickable)} results";
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
            Child = WithGlyph(status, Typed(new C.TextBlock { Text = chip.Words.Replace(" to review", " need review") }, Caption), size: 10, gap: 4),
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
