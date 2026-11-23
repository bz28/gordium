using System.IO;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Gordium.Revit.Reading;
using Gordium.Worker;

namespace Gordium.Revit.PanePrototype;

/// <summary>PROTOTYPE: one pane to draw, today's or the proposed (both take the same steps of the journey).</summary>
internal interface IPane
{
    FrameworkElement View { get; }

    string Name { get; }

    void Setup(string title, SetupScreen screen, SetupDraft draft);

    void Progress(CheckStage stage, DateTime since);

    void Show(string project, DateTime when, ResultModel model, IReadOnlyDictionary<string, string> labels);

    IReadOnlyList<string> FirstCardRows { get; }

    void OpenFirstCard();

    void OpenRow(string id);

    /// <summary>Cards shown at first, cards in all, and the actions they ask for.</summary>
    (int Shown, int Total, int Actions) Cards { get; }

    void Stale();

    void Failed(string words);
}

/// <summary>
/// PROTOTYPE, render-only (Ben, 2026-11-22: design first, approval before anything ships): draws the Gordium pane
/// off-screen, step by step through an architect's first run, today's and the proposed, from the checker's real
/// answers, and counts what each step shows (words on screen, buttons, cards). Usage:
/// <c>Gordium.Revit.PanePrototype &lt;fixtures dir&gt; &lt;childcare answer&gt; &lt;out dir&gt; [&lt;pictures dir&gt;]</c> (the pictures: a Revit screenshot, the childcare sheet and the ribbon icons, kept outside the repo).
/// </summary>
internal static class Program
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());
    private static readonly StringBuilder Numbers = new();
    private static string _out = "";

    [STAThread]
    private static int Main(string[] args)
    {
        var fix = args[0];
        var childcareAnswer = args[1];
        _out = args[2];
        Directory.CreateDirectory(_out);
        var options = Options(Path.Combine(fix, "options.json"));
        var house = Load(Path.Combine(fix, "house_106.json"));
        var houseAfter = Load(Path.Combine(fix, "house_106_after.json"));
        var childcare = Load(childcareAnswer);
        foreach (var (n, r) in new[] { ("house", house), ("childcare", childcare) })
        {
            var cs = ResultRows.Build(r, "New Construction", [], null).Causes;
            Console.WriteLine($"{n}: {cs.Count} cards");
            var lb = Labels(r);
            for (var k = 0; k < cs.Count; k++)
                Console.WriteLine($"   today #{k + 1} {CauseCards.Action(cs[k], lb)} | {cs[k].Words[..Math.Min(70, cs[k].Words.Length)]}");
            foreach (var g in Proposed.CardGroups.Of(cs, Labels(r)))
                Console.WriteLine($"   T{g.Tier} {g.Action} rows {g.Rows.Count} members {g.Members.Count} | {g.Title}");
        }
        // the proposed grouping's promises, checked on both real answers (a prototype's checks; the shipped version
        // would pin each with a reader test that fails on revert)
        foreach (var (n, r) in new[] { ("house", house), ("childcare", childcare), ("house after", houseAfter) })
        {
            var cs = ResultRows.Build(r, "New Construction", [], null).Causes;
            var gs = Proposed.CardGroups.Of(cs, Labels(r));
            Check(cs.All(c => gs.Count(g => g.Members.Contains(c)) == 1), $"{n}: every cause card is in exactly one fix");
            Check(gs.SelectMany(g => g.Rows).ToHashSet().SetEquals(cs.SelectMany(c => c.Items)), $"{n}: the fixes' results are exactly the cards' results (none hidden, none added)");
            Check(gs.All(g => g.Rows.SequenceEqual(g.Members.SelectMany(m => m.Items).Distinct())), $"{n}: a fix's results are its causes' results");
            var again = Proposed.CardGroups.Of(cs.ToList(), Labels(r));
            Check(gs.Select(g => g.Key).SequenceEqual(again.Select(g => g.Key)), $"{n}: the ranking is the same every time");
            Check(gs.Zip(gs.Skip(1)).All(p => p.First.Tier < p.Second.Tier || p.First.Tier == p.Second.Tier && (p.First.Rows.Count > p.Second.Rows.Count
                  || p.First.Rows.Count == p.Second.Rows.Count && p.First.FirstIndex < p.Second.FirstIndex)), $"{n}: ranked by where the fix is made, then results cleared, then the checker's order");
        }
        if (Failures > 0)
            return Failures;
        if (args.Length > 3 && args[3] == "groups")
            return 0;
        Numbers.AppendLine("step\tpane\ttheme\theight\twords\tbuttons\tcards shown\tcards in all");
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
            foreach (var make in new Func<PanelTheme, List<string>, IPane>[] { (t, a) => new Addin.TodayPane(t, a), (t, a) => new Proposed.ProposedPane(t, a) })
            {
                var dark = theme == PanelTheme.Dark;
                // a: first open, before any check
                Step(make(theme, []), "01_welcome", 430, dark, _ => { });
                // the house (106 Ithaca Rd) and the childcare centre (Children's Odyssey)
                foreach (var (tag, title, setupFile, answer) in new[] { ("house", "106 Ithaca Rd", "ithaca106.json", house), ("childcare", "Children's Odyssey", "childcare.json", childcare) })
                {
                    if (dark && tag == "childcare")
                        continue;                       // dark: the house only
                    var (setupTitle, model, sides) = Fixture(Path.Combine(fix, setupFile));
                    var blank = SetupScreen.Build(model, sides, options, new SetupDraft());
                    // b: Check project with facts missing: the Setup form
                    Step(make(theme, []), $"02_setup_{tag}", 430, dark, p => p.Setup(title, blank, new SetupDraft()));
                    // c: the form filled in, then the check running
                    var draft = Filled(blank, tag);
                    var filled = SetupScreen.Build(model, sides, options, draft);
                    Step(make(theme, []), $"03_setup_filled_{tag}", 430, dark, p => p.Setup(title, filled, draft));
                    Step(make(theme, []), $"04_checking_{tag}", 430, dark, p =>
                    {
                        p.Setup(title, filled, draft);
                        p.Progress(CheckStage.Checking, DateTime.Now.AddSeconds(-4));
                    });
                    // d: the results' top
                    var labels = Labels(answer);
                    var rows = ResultRows.Build(answer, "New Construction", [], null);
                    var when = new DateTime(2026, 11, 22, 14, 32, 0);
                    foreach (var h in new[] { 430, 900 })
                        Step(make(theme, []), $"05_results_{tag}", h, dark, p => p.Show(title, when, rows, labels));
                    // e: the first card opened on its rows
                    Step(make(theme, []), $"06_card_open_{tag}", 900, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.OpenFirstCard();
                        ScrollToCards(p.View);
                    });
                    // f: a row's detail (the first card's first row)
                    Step(make(theme, []), $"07_detail_{tag}", 900, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.OpenRow(p.FirstCardRows[0]);
                    });
                    if (tag != "house")
                        continue;
                    // g: after the fix (the lot facts set) and Check again: what changed
                    var afterLabels = Labels(houseAfter);
                    Step(make(theme, []), "08_what_changed_house", 430, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.Show(title, when.AddMinutes(9), ResultRows.Build(houseAfter, "New Construction", [], null), afterLabels);
                    });
                    // h: a project with nothing missing that just runs: Check project straight to checking
                    Step(make(theme, []), "09_just_runs_house", 430, dark, p => p.Progress(CheckStage.Checking, DateTime.Now.AddSeconds(-6)));
                    // the error state, and stale
                    Step(make(theme, []), "10_error_house", 430, dark, p => p.Failed(
                        "Nothing was checked: InvalidOperationException: the worker stopped (exit code 1) (logged to C:\\Users\\you\\AppData\\Local\\Gordium\\addin\\2027\\current\\check.log)"));
                    Step(make(theme, []), "11_stale_house", 430, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.Stale();
                    });
                }
            }
        Proposed.Extras.All(_out, args.Length > 3 ? args[3] : "", house, childcare, Labels(house), Labels(childcare));
        File.WriteAllText(Path.Combine(_out, "numbers.tsv"), Numbers.ToString());
        Console.WriteLine(Numbers.ToString());
        Console.WriteLine(Failures == 0 ? "ALL CHECKS OK" : $"{Failures} CHECKS FAILED");
        return Failures;
    }

    /// <summary>The form as an architect fills it in: the facts a check needs chosen (nothing written: a draft).</summary>
    private static SetupDraft Filled(SetupScreen blank, string tag)
    {
        var draft = new SetupDraft();
        foreach (var f in blank.Fields.Where(f => f.Required && f.Current is null))
        {
            var pick = f.Mark == Marks.Zone ? (tag == "house" ? "R-1b" : f.Choices.FirstOrDefault()?.Value)
                : f.Mark == Marks.Use ? (tag == "house" ? "one_family_detached" : f.Choices.FirstOrDefault(c => c.Value.Contains("day_care"))?.Value ?? f.Choices.FirstOrDefault()?.Value)
                : f.Kind == FieldKind.YesNo ? "Yes" : f.Choices.FirstOrDefault()?.Value;
            if (pick is not null && f.Kind != FieldKind.StreetPick)
                draft.Choose(f.Mark, pick);
        }
        return draft;
    }

    internal static int Failures;

    private static void Check(bool ok, string what)
    {
        Console.WriteLine((ok ? "ok   " : "FAIL ") + what);
        if (!ok)
            Failures++;
    }

    private static void Step(IPane pane, string name, int height, bool dark, Action<IPane> act)
    {
        var window = new Window
        {
            Content = pane.View, Width = 340, Height = height, WindowStyle = WindowStyle.None, ShowInTaskbar = false,
            Left = -20000, Top = -20000, ShowActivated = false, SizeToContent = SizeToContent.Manual,
        };
        window.Show();
        act(pane);
        Settle(pane.View);
        var file = $"{name}_{pane.Name}{(height == 430 ? "" : "_" + height)}{(dark ? "_dark" : "")}.png";
        Render(pane.View, Path.Combine(_out, file));
        var (words, buttons) = Measure(pane.View);
        var welcome = FindAll<TextBlock>(pane.View).Any(t => t.IsVisible && TextOf(t) == "Welcome to Gordium");
        if (pane.Name == "proposed")
            Check(welcome == name is "01_welcome" or "09_just_runs_house", $"{file}: the welcome {(welcome ? "shows" : "doesn't show")} (only before the first results, never over them)");
        var (shown, total, _) = pane.Cards;
        Numbers.AppendLine($"{name}\t{pane.Name}\t{(dark ? "dark" : "light")}\t{height}\t{words}\t{buttons}\t{shown}\t{total}");
        Console.WriteLine($"{file}: {words} words, {buttons} buttons, cards {shown}/{total}");
        window.Close();
    }

    internal static void Settle(FrameworkElement v)
    {
        for (var i = 0; i < 3; i++)
        {
            v.UpdateLayout();
            System.Windows.Threading.Dispatcher.CurrentDispatcher.Invoke(() => { }, System.Windows.Threading.DispatcherPriority.ApplicationIdle);
        }
    }

    /// <summary>Scrolls the pane's list so its "Fix these first" entry is at the top.</summary>
    private static void ScrollToCards(FrameworkElement view)
    {
        Settle(view);
        var list = FindAll<ListBox>(view).FirstOrDefault();
        if (list is null)
            return;
        var at = Enumerable.Range(0, list.Items.Count).FirstOrDefault(i => list.Items[i].GetType().Name is "CausesItem");
        if (at <= 0)
            return;
        var sv = FindAll<ScrollViewer>(list).First();
        list.ScrollIntoView(list.Items[at]);
        list.UpdateLayout();
        if (list.ItemContainerGenerator.ContainerFromIndex(at - 1) is FrameworkElement box)
            sv.ScrollToVerticalOffset(sv.VerticalOffset + box.TranslatePoint(new Point(0, 0), sv).Y);
        list.UpdateLayout();
    }

    /// <summary>The words an architect sees on screen (every visible text inside the pane's frame) and the buttons.</summary>
    internal static (int Words, int Buttons) Measure(FrameworkElement view)
    {
        var frame = new Rect(0, 0, view.ActualWidth, view.ActualHeight);
        bool OnScreen(FrameworkElement e)
        {
            if (!e.IsVisible || e.ActualHeight < 1)
                return false;
            try
            {
                var r = e.TransformToAncestor(view).TransformBounds(new Rect(0, 0, e.ActualWidth, e.ActualHeight));
                // clipped by a scroll viewer: count only what its viewport shows
                for (DependencyObject? p = VisualTreeHelper.GetParent(e); p is not null && p != view; p = VisualTreeHelper.GetParent(p))
                    if (p is ScrollContentPresenter sp)
                        r.Intersect(sp.TransformToAncestor(view).TransformBounds(new Rect(0, 0, sp.ActualWidth, sp.ActualHeight)));
                return !r.IsEmpty && r.Height >= 4 && r.IntersectsWith(frame);
            }
            catch (InvalidOperationException)
            {
                return false;
            }
        }
        var words = FindAll<TextBlock>(view).Where(OnScreen).Sum(t => Regex.Matches(TextOf(t), @"\S+").Count);
        var buttons = FindAll<System.Windows.Controls.Primitives.ButtonBase>(view).Count(b => OnScreen(b) && b is not CheckBox);
        return (words, buttons);
    }

    private static string TextOf(TextBlock t) =>
        t.Text is { Length: > 0 } x ? x : new System.Windows.Documents.TextRange(t.ContentStart, t.ContentEnd).Text;

    internal static CheckResult Load(string path)
    {
        var doc = JsonDocument.Parse(File.ReadAllText(path, Encoding.UTF8));
        return (CheckResult)typeof(CheckResult).GetMethod("Parse", BindingFlags.NonPublic | BindingFlags.Static)!
            .Invoke(null, [new WorkerAnswer(doc.RootElement.GetProperty("result"), About)])!;
    }

    /// <summary>Each element a name, as the answer gives it (what Revit would label it).</summary>
    internal static Dictionary<string, string> Labels(CheckResult r)
    {
        var labels = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var i in r.Items)
        {
            var raw = i.Raw;
            if (raw.TryGetProperty("part", out var p) && p.ValueKind == JsonValueKind.Object && p.TryGetProperty("id", out var id) && id.ValueKind == JsonValueKind.String
                && p.TryGetProperty("name", out var n) && n.ValueKind == JsonValueKind.String && !id.GetString()!.Contains(' '))
                labels.TryAdd(id.GetString()!, n.GetString()!.Split(" › ")[^1]);
            if (raw.TryGetProperty("causes", out var cs) && cs.ValueKind == JsonValueKind.Array)
                foreach (var c in cs.EnumerateArray())
                    if (c.TryGetProperty("rooms", out var rs) && rs.ValueKind == JsonValueKind.Array)
                        foreach (var room in rs.EnumerateArray())
                            labels[room.GetProperty("id").GetString()!] = room.GetProperty("name").GetString()!;
            if (raw.TryGetProperty("objects", out var os) && os.ValueKind == JsonValueKind.Array)
                foreach (var o in os.EnumerateArray())
                    labels.TryAdd(o.GetString()!, i.Name == "Lot coverage" ? "Building: House" : "Lot line " + (labels.Count + 1));
        }
        return labels;
    }

    internal static void Render(FrameworkElement v, string file)
    {
        v.UpdateLayout();
        var bmp = new RenderTargetBitmap((int)Math.Ceiling(v.ActualWidth), (int)Math.Ceiling(v.ActualHeight), 96, 96, PixelFormats.Pbgra32);
        bmp.Render(v);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(bmp));
        using var f = File.Create(file);
        enc.Save(f);
    }

    internal static IEnumerable<T> FindAll<T>(DependencyObject root) where T : DependencyObject
    {
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            var c = VisualTreeHelper.GetChild(root, i);
            if (c is T t)
                yield return t;
            foreach (var d in FindAll<T>(c))
                yield return d;
        }
    }

    // ---- the Setup fixtures (the unmarked models' records, as the Setup renders of PR #164 read them) ------------

    private static PlaceOptions Options(string file)
    {
        var j = JsonDocument.Parse(File.ReadAllText(file)).RootElement;
        var uses = j.GetProperty("uses").EnumerateObject().Select(p => (p.Name, p.Value.GetString()!)).ToList();
        var district = j.GetProperty("district_uses").EnumerateObject().ToDictionary(d => d.Name, d => (IReadOnlyList<UseChoice>)d.Value.EnumerateArray()
            .Select(u => new UseChoice(u.GetProperty("id").GetString()!, u.GetProperty("name").GetString()!,
                                       u.GetProperty("permitted").ValueKind switch { JsonValueKind.True => true, JsonValueKind.False => false, _ => null },
                                       u.GetProperty("note").ValueKind == JsonValueKind.String ? u.GetProperty("note").GetString() : null)).ToList());
        return new PlaceOptions(j.GetProperty("zones").EnumerateArray().Select(z => z.GetString()!).ToList(), uses, district);
    }

    private static MarkValue? Yes(JsonElement m, string key) =>
        m.TryGetProperty(key, out var v) && v.ValueKind is JsonValueKind.True or JsonValueKind.False ? new MarkValue(true, v.GetBoolean() ? 1 : 0) : null;

    private static MarkValue? Word(JsonElement m, string key, Func<string, string>? map = null) =>
        m.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? new MarkValue(true, Text: map is null ? v.GetString() : map(v.GetString()!)) : null;

    private static (string, RevitModel, List<OpeningSides>) Fixture(string file)
    {
        var j = JsonDocument.Parse(File.ReadAllText(file)).RootElement;
        var marked = new List<MarkedElement>();
        foreach (var e in j.GetProperty("elements").EnumerateArray())
        {
            var m = e.GetProperty("marks");
            var inst = new Dictionary<Guid, MarkValue>();
            void Put(MarkDefinition d, MarkValue? v)
            {
                if (v is not null)
                    inst[d.Guid] = v;
            }
            var cat = e.GetProperty("cat").GetString()!;
            if (cat == "OST_Rooms")
            {
                Put(Marks.SleepingRoom, Yes(m, "sleeping"));
                Put(Marks.Use, Word(m, "use"));
                Put(Marks.CanBeLocked, Yes(m, "lockable"));
                Put(Marks.PassThrough, Yes(m, "pass_through"));
            }
            else
                Put(Marks.Exit, Word(m, "exit", k => ExitKinds.Table.WordFor(k)));
            string? S(string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
            double? D(string k) => e.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : null;
            marked.Add(new MarkedElement
            {
                UniqueId = e.GetProperty("id").GetString()!, BuiltInCategory = cat, Name = S("name"), Number = S("number"), Family = S("family"),
                TypeUniqueId = S("type"), TypeWidth = D("w"), TypeHeight = D("h"), Placement = cat == "OST_Rooms" ? RoomPlacement.Placed : null,
                Instance = inst,
            });
        }
        var sides = j.GetProperty("sides").EnumerateArray().Select(s => new OpeningSides(s.GetProperty("id").GetString()!,
            s.GetProperty("from").ValueKind == JsonValueKind.String ? s.GetProperty("from").GetString() : null,
            s.GetProperty("to").ValueKind == JsonValueKind.String ? s.GetProperty("to").GetString() : null, "L1", "Level 1", 0)).ToList();
        return (j.GetProperty("title").GetString()!, new RevitModel { Document = file, Marked = marked, ProjectMarks = new Dictionary<Guid, MarkValue>() }, sides);
    }
}
