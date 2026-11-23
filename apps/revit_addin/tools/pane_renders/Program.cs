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

namespace Gordium.Revit.PaneRenders;

using Gordium.Revit.Addin;

/// <summary>
/// Off-screen renders of the Gordium pane (the add-in's own view files), step by step through an architect's first run,
/// from the checker's real answers: the house (106 Ithaca Rd as Revit read it in the trial: the reader tests' answer)
/// and the childcare centre (Children's Odyssey), light and dark; and what each screen shows (words, buttons, fixes).
/// Usage: <c>Gordium.Revit.PaneRenders &lt;out dir&gt;</c>.
/// </summary>
internal static class Program
{
    private static readonly WorkerAbout About = new("1.3", "gordium.site/1", new string('f', 64), new Dictionary<string, string>());
    private static readonly StringBuilder Numbers = new();
    private static string _out = "";

    [STAThread]
    private static int Main(string[] args)
    {
        _out = args[0];
        Directory.CreateDirectory(_out);
        var here = AppContext.BaseDirectory;
        var fix = Path.Combine(here, "fixtures");
        var answers = Path.Combine(here, "answers");
        var options = Options(Path.Combine(fix, "setup_options.json"));
        var house = Load(Path.Combine(answers, "ithaca_106_house_check_answer.json"));
        var houseAfter = Load(Path.Combine(answers, "ithaca_106_house_after_check_answer.json"));
        var childcare = Load(Path.Combine(answers, "children_odyssey_check_answer.json"));
        foreach (var (n, r) in new[] { ("house", house), ("childcare", childcare) })
        {
            var cs = ResultRows.Build(r, "New Construction", [], null).Causes;
            Console.WriteLine($"{n}: {cs.Count} cause cards");
            foreach (var g in Fixes.Of(cs, Labels(r)))
                Console.WriteLine($"   tier {g.Tier} {g.Action}, {g.Rows.Count} results, {g.Members.Count} cards | {g.Title}");
        }
        Numbers.AppendLine("step\ttheme\theight\twords\tbuttons\tfixes shown\tfixes in all\tcause cards");
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
            foreach (var make in new Func<PanelTheme, List<string>, Pane>[] { (t, a) => new Pane(t, a) })
            {
                var dark = theme == PanelTheme.Dark;
                // a: first open, before any check
                Step(make(theme, []), "01_welcome", 430, dark, _ => { });
                // the house (106 Ithaca Rd) and the childcare centre (Children's Odyssey)
                foreach (var (tag, title, setupFile, answer) in new[] { ("house", "106 Ithaca Rd", "setup_ithaca106.json", house), ("childcare", "Children's Odyssey", "setup_childcare.json", childcare) })
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
                        p.OpenFirstFix();
                        ScrollToCards(p.View);
                    });
                    // the pane as narrow as Revit docks it in the trial (narrower than at 340: Revit draws the same words wider): the fix's button stays one
                    // line and its link wraps under it, never squeezed to a letter a line (Revit 2027 trial, 2026-11-23)
                    if (!dark)
                        Step(make(theme, []), $"06_card_open_{tag}_narrow", 900, dark, p =>
                        {
                            p.Show(title, when, rows, labels);
                            p.OpenFirstFix();
                            ScrollToCards(p.View);
                            Settle(p.View);
                            var tall = FindAll<Button>(p.View).Where(b => b.IsVisible && b.Content is string && b.ActualHeight > 40).ToList();   // a button of words, not a wrapped link
                            Check(tall.Count == 0, $"{tag} narrow: no button taller than a line ({tall.Count})");
                        }, width: 280);
                    // the form shown again (its facts read again after Save): one foot, no error
                    if (!dark)
                        Step(make(theme, []), $"03_setup_again_{tag}", 430, dark, p =>
                        {
                            p.Setup(title, filled, draft);
                            p.Setup(title, filled, draft);
                            Check(true, $"{tag}: the Setup form shown twice");
                        });
                    // f: a row's detail (the first card's first row)
                    Step(make(theme, []), $"07_detail_{tag}", 900, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.OpenRow(p.FirstFixRows[0]);
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
                        CheckWords.CheckerStopped("the worker exited with code 1") + @" (logged to C:\Users\you\AppData\Local\Gordium\trial\results.jsonl)"));
                    Step(make(theme, []), "11_stale_house", 430, dark, p =>
                    {
                        p.Show(title, when, rows, labels);
                        p.Stale();
                    });
                }
            }
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

    private static void Step(Pane pane, string name, int height, bool dark, Action<Pane> act, int width = 340)
    {
        var window = new Window
        {
            Content = pane.View, Width = width, Height = height, WindowStyle = WindowStyle.None, ShowInTaskbar = false,
            Left = -20000, Top = -20000, ShowActivated = false, SizeToContent = SizeToContent.Manual,
        };
        window.Show();
        act(pane);
        Settle(pane.View);
        var file = $"{name}_built{(height == 430 ? "" : "_" + height)}{(dark ? "_dark" : "")}.png";
        Render(pane.View, Path.Combine(_out, file));
        var (words, buttons) = Measure(pane.View);
        var welcome = FindAll<TextBlock>(pane.View).Any(t => t.IsVisible && TextOf(t) == PaneWords.WelcomeTitle);
        Check(welcome == name is "01_welcome" or "09_just_runs_house", $"{file}: the welcome {(welcome ? "shows" : "doesn't show")} (only before the first results, never over them)");
        var (shown, total, cards) = pane.Cards;
        Numbers.AppendLine($"{name}\t{(dark ? "dark" : "light")}\t{height}\t{words}\t{buttons}\t{shown}\t{total}\t{cards}");
        Console.WriteLine($"{file}: {words} words, {buttons} buttons, fixes {shown}/{total} of {cards} cause cards");
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
