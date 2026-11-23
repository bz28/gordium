using System.IO;
using System.Text.Json;
using Gordium.Revit.Reading;
using Gordium.Worker;
using W = System.Windows;
using C = System.Windows.Controls;
using M = System.Windows.Media;
using S = System.Windows.Shapes;
using I = System.Windows.Media.Imaging;

namespace Gordium.Revit.PanePrototype.Proposed;

/// <summary>
/// PROTOTYPE: the proposed designs beyond the pane's journey, drawn off-screen: the ribbon's status badge, the pane
/// answering "what about the element I selected", a printable compliance summary, and two ILLUSTRATIVE in-model
/// overlays drawn over real pictures (a Revit screenshot of the 106 Ithaca Rd trial model; the childcare centre's own
/// life-safety sheet). Every figure is the checker's (from the answers); positions on the pictures are placed by hand.
/// </summary>
internal static class Extras
{
    private static string _out = "";
    private static string _pictures = "";

    internal static void All(string outDir, string pictures, CheckResult house, CheckResult childcare,
                             IReadOnlyDictionary<string, string> houseLabels, IReadOnlyDictionary<string, string> childcareLabels)
    {
        _out = outDir;
        _pictures = pictures;
        Ribbon();
        Selection(childcare, childcareLabels);
        PermitSummary(house);
        if (File.Exists(Path.Combine(pictures, "revit_106_screenshot.png")))
        {
            InRevit106(house, "today", Path.Combine(outDir, "05_results_house_today_dark.png"), overlay: false);
            InRevit106(house, "proposed", Path.Combine(outDir, "05_results_house_proposed_dark.png"), overlay: true);
        }
        if (File.Exists(Path.Combine(pictures, "childcare_life_safety_plan.png")))
            ChildcareRoutes(childcare);
    }

    // ---- helpers ------------------------------------------------------------------------------------------------

    private static W.FrameworkElement Themed(W.FrameworkElement child, PanelTheme theme)
    {
        var root = new C.Border { Child = child };
        PanelLook.Apply(root, theme);
        root.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgPane);
        root.SetResourceReference(C.Control.ForegroundProperty, PanelTokens.Text);
        W.Documents.TextElement.SetFontFamily(root, new M.FontFamily("Segoe UI"));
        W.Documents.TextElement.SetFontSize(root, 12);
        return root;
    }

    private static void Save(W.FrameworkElement e, double width, double height, string name)
    {
        e.Measure(new W.Size(width, height));
        e.Arrange(new W.Rect(0, 0, width, height));
        e.UpdateLayout();
        var bmp = new I.RenderTargetBitmap((int)width, (int)height, 96, 96, M.PixelFormats.Pbgra32);
        bmp.Render(e);
        var enc = new I.PngBitmapEncoder();
        enc.Frames.Add(I.BitmapFrame.Create(bmp));
        using var f = File.Create(Path.Combine(_out, name));
        enc.Save(f);
        Console.WriteLine("extra: " + name);
    }

    private static C.TextBlock Text(string words, double size = 12, bool semi = false, string? ink = null, double top = 0)
    {
        var t = new C.TextBlock { Text = words, FontSize = size, TextWrapping = W.TextWrapping.Wrap, Margin = new W.Thickness(0, top, 0, 0) };
        if (semi)
            t.FontWeight = W.FontWeights.SemiBold;
        if (ink is not null)
            t.SetResourceReference(C.TextBlock.ForegroundProperty, ink);
        return t;
    }

    private static I.BitmapImage Picture(string file)
    {
        var b = new I.BitmapImage();
        b.BeginInit();
        b.CacheOption = I.BitmapCacheOption.OnLoad;
        b.UriSource = new Uri(Path.GetFullPath(file));
        b.EndInit();
        b.Freeze();
        return b;
    }

    // ---- the ribbon: Check project with the last check's state as a badge --------------------------------------

    private static void Ribbon()
    {
        var row = new C.StackPanel { Orientation = C.Orientation.Horizontal, Margin = new W.Thickness(12) };
        foreach (var (state, badge, tone, tip) in new (string, string?, PanelStatus?, string)[]
                 {
                     ("Not checked yet", null, null, "Check this project against its zoning and egress rules"),
                     ("Checked 14:32", "1|77", PanelStatus.Fails, "Checked 14:32: 1 fails, 77 need review. Click to check again; the pane shows them."),
                     ("Model changed", "◷", PanelStatus.Stale, "The model changed after the check at 14:32: the results may not hold. Click to check again."),
                 })
        {
            var panel = new C.StackPanel { Margin = new W.Thickness(0, 0, 18, 0), Width = 210 };
            var group = new C.Border { BorderThickness = new W.Thickness(1), Padding = new W.Thickness(8, 6, 8, 2), CornerRadius = new W.CornerRadius(2) };
            group.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
            group.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
            var buttons = new C.StackPanel { Orientation = C.Orientation.Horizontal };
            foreach (var (icon, words) in new[] { ("check_project", "Check\nproject"), ("mark_facts", "Set up\nfacts"), ("panel", "Panel") })
            {
                var b = new C.StackPanel { Width = 58 };
                var grid = new C.Grid { Width = 32, Height = 32, HorizontalAlignment = W.HorizontalAlignment.Center };
                var file = Path.Combine(_pictures, "icons", $"{icon}_32_Light.png");
                if (File.Exists(file))
                    grid.Children.Add(new C.Image { Source = Picture(file), Width = 32, Height = 32 });
                if (icon == "check_project" && badge is not null)
                {
                    var pills = new C.StackPanel { Orientation = C.Orientation.Horizontal, HorizontalAlignment = W.HorizontalAlignment.Right,
                                                   VerticalAlignment = W.VerticalAlignment.Top, Margin = new W.Thickness(0, -6, -30, 0) };
                    var parts = badge.Split('|');
                    for (var k = 0; k < parts.Length; k++)
                    {
                        var dot = new C.Border { CornerRadius = new W.CornerRadius(7), Padding = new W.Thickness(4, 0, 4, 1), Margin = new W.Thickness(1, 0, 0, 0) };
                        dot.SetResourceReference(C.Border.BackgroundProperty, StatusLook.Colour(k == 0 ? tone!.Value : PanelStatus.Review));
                        var t = Text(parts[k], 10, semi: true);
                        t.SetResourceReference(C.TextBlock.ForegroundProperty, PanelTokens.BgSurface);
                        dot.Child = t;
                        pills.Children.Add(dot);
                    }
                    grid.Children.Add(pills);
                }
                b.Children.Add(grid);
                var w = Text(words, 11);
                w.TextAlignment = W.TextAlignment.Center;
                b.Children.Add(w);
                buttons.Children.Add(b);
            }
            var stack = new C.StackPanel();
            stack.Children.Add(buttons);
            var label = Text("Gordium", 10, ink: PanelTokens.TextMuted, top: 4);
            label.TextAlignment = W.TextAlignment.Center;
            stack.Children.Add(label);
            group.Child = stack;
            panel.Children.Add(group);
            panel.Children.Add(Text(state, 11, semi: true, top: 6));
            panel.Children.Add(Text("Tooltip: " + tip, 11, ink: PanelTokens.TextMuted, top: 2));
            row.Children.Add(panel);
        }
        Save(Themed(row, PanelTheme.Light), 720, 190, "12_ribbon_badge_proposed.png");
    }

    // ---- select an element in Revit: the pane says which results are about it --------------------------------

    private static void Selection(CheckResult childcare, IReadOnlyDictionary<string, string> labels)
    {
        var model = ResultRows.Build(childcare, "New Construction", [], null);
        var placed = ResultList.Place(model);
        var raws = childcare.Items.ToDictionary(i => i.Id, i => i.Raw, StringComparer.Ordinal);
        // the element most results are about (each row's own objects, the worker's)
        var about = new Dictionary<string, List<ListRow>>(StringComparer.Ordinal);
        var byId = placed.ToDictionary(p => p.Row.Id, StringComparer.Ordinal);
        void Add(string uid, string row)
        {
            if (!labels.ContainsKey(uid) || !byId.TryGetValue(row, out var lr))
                return;
            var l = about.TryGetValue(uid, out var x) ? x : about[uid] = [];
            if (!l.Contains(lr))
                l.Add(lr);
        }
        // the rows about an element: those whose own objects name it, and those of a cause card naming it
        foreach (var p in placed)
            if (raws.TryGetValue(p.Row.Id, out var raw) && raw.TryGetProperty("objects", out var os) && os.ValueKind == JsonValueKind.Array)
                foreach (var o in os.EnumerateArray())
                    if (o.GetString() is { } uid)
                        Add(uid, p.Row.Id);
        foreach (var card in model.Causes)
            foreach (var uid in card.Elements)
                foreach (var row in card.Items)
                    Add(uid, row);
        if (about.Count == 0)
            return;
        var (picked, rows) = about.Where(kv => !labels[kv.Key].StartsWith("Level", StringComparison.Ordinal)).DefaultIfEmpty(about.First())
                                  .OrderByDescending(kv => labels[kv.Key] == "STORAGE (13)").ThenByDescending(kv => kv.Value.Count).ThenBy(kv => kv.Key, StringComparer.Ordinal).First() is var kv2 ? (kv2.Key, kv2.Value) : default;
        var page = new C.StackPanel { Margin = new W.Thickness(12, 8, 12, 12) };
        page.Children.Add(Text("Gordium", 13, semi: true));
        page.Children.Add(Text("Checked 14:32 · Children's Odyssey", 11, ink: PanelTokens.TextMuted));
        var box = new C.Border { BorderThickness = new W.Thickness(1), CornerRadius = new W.CornerRadius(4), Padding = new W.Thickness(10, 8, 10, 8), Margin = new W.Thickness(0, 10, 0, 0) };
        box.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSelected);
        box.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Accent);
        var inner = new C.StackPanel();
        inner.Children.Add(Text("SELECTED IN REVIT", 10, semi: true, ink: PanelTokens.TextMuted));
        inner.Children.Add(Text(labels[picked], 13, semi: true, top: 2));
        var fails = rows.Count(r => r.Status == PanelStatus.Fails);
        var review = rows.Count(r => r.Status == PanelStatus.Review);
        var said = new List<string>();
        if (fails > 0) said.Add($"{fails} fail");
        if (review > 0) said.Add($"{review} need review");
        if (rows.Count - fails - review > 0) said.Add($"{rows.Count - fails - review} other");
        inner.Children.Add(Text($"{rows.Count} results mention it: " + string.Join(", ", said), 12, top: 2));
        foreach (var r in rows.Take(8))
        {
            var line = new C.DockPanel { Margin = new W.Thickness(0, 5, 0, 0) };
            var g = PanelLook.Glyph(r.Status, 12);
            g.Margin = new W.Thickness(0, 1, 6, 0);
            g.VerticalAlignment = W.VerticalAlignment.Top;
            C.DockPanel.SetDock(g, C.Dock.Left);
            line.Children.Add(g);
            line.Children.Add(Text(r.Row.Name, 12, ink: PanelTokens.Accent));
            inner.Children.Add(line);
        }
        if (rows.Count > 8)
            inner.Children.Add(Text($"+{rows.Count - 8} more", 11, ink: PanelTokens.TextMuted, top: 4));
        var clear = new C.Button { Content = "Show every result", Padding = new W.Thickness(8, 1, 8, 1), Margin = new W.Thickness(0, 8, 0, 0), HorizontalAlignment = W.HorizontalAlignment.Left };
        inner.Children.Add(clear);
        box.Child = inner;
        page.Children.Add(box);
        page.Children.Add(Text("Select anything in the model (a door, a room, a window) and this box lists what Gordium found about it. Click elsewhere to clear it.", 11, ink: PanelTokens.TextMuted, top: 8));
        Save(Themed(page, PanelTheme.Light), 340, 430, "13_selected_element_childcare_proposed.png");
    }

    // ---- a printable compliance summary for the permit set ------------------------------------------------------

    private static void PermitSummary(CheckResult house)
    {
        var doc = new C.StackPanel { Margin = new W.Thickness(48, 40, 48, 40) };
        doc.Children.Add(Text("Zoning compliance summary", 20, semi: true));
        doc.Children.Add(Text("106 Ithaca Rd · City of Ithaca, NY · district R-1b · one-family dwelling, detached", 12, top: 2));
        doc.Children.Add(Text("Prepared with Gordium from the Revit model on 2026-11-22 14:32. A summary for the architect's own review, not a permit or an approval: " +
                              "every result marked needs review is for the architect to resolve before relying on it.", 10, ink: PanelTokens.TextMuted, top: 4));
        var table = new C.Grid { Margin = new W.Thickness(0, 14, 0, 0) };
        foreach (var w in new[] { 140.0, 80, 70, 105, 325 })
            table.ColumnDefinitions.Add(new C.ColumnDefinition { Width = new W.GridLength(w) });
        var r = 0;
        void Cell(int col, W.UIElement e)
        {
            C.Grid.SetRow(e, r);
            C.Grid.SetColumn(e, col);
            table.Children.Add(e);
        }
        table.RowDefinitions.Add(new C.RowDefinition());
        foreach (var (i, h) in new[] { "Rule", "Proposed", "Required", "Result", "The law's words (City of Ithaca Code ch. 325)" }.Select((h, i) => (i, h)))
            Cell(i, Text(h, 10, semi: true, ink: PanelTokens.TextMuted));
        foreach (var item in house.Items.Where(i => i.Raw.TryGetProperty("proposed", out var pr) && pr.ValueKind == JsonValueKind.String).Take(11))
        {
            r++;
            table.RowDefinitions.Add(new C.RowDefinition());
            var raw = item.Raw;
            string S(string k) => raw.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
            var status = item.Status switch { Verdict.DoesNotComply => PanelStatus.Fails, Verdict.Complies => PanelStatus.Complies, _ => PanelStatus.Review };
            Cell(0, Text(item.Name, 11, top: 6));
            Cell(1, Text(S("proposed"), 11, top: 6));
            Cell(2, Text((S("sign") is { Length: > 0 } sg && S("required") != "permitted" ? sg + " " : "") + S("required"), 11, top: 6));
            var verdict = new C.StackPanel { Orientation = C.Orientation.Horizontal, Margin = new W.Thickness(0, 6, 0, 0) };
            verdict.Children.Add(PanelLook.Glyph(status, 11));
            verdict.Children.Add(Text(" " + StatusLook.Word(status), 11, ink: StatusLook.Colour(status)));
            Cell(3, verdict);
            var quote = "";
            if (raw.TryGetProperty("detail", out var d) && d.ValueKind == JsonValueKind.Object && d.TryGetProperty("quotes", out var cited) && cited.ValueKind == JsonValueKind.Array)
                foreach (var c in cited.EnumerateArray())
                    if (c.TryGetProperty("text", out var q) && q.ValueKind == JsonValueKind.String)
                    {
                        var where = c.TryGetProperty("where", out var wh) && wh.ValueKind == JsonValueKind.String ? " (" + wh.GetString() + ")" : "";
                        quote = "“" + q.GetString() + "”" + where;
                        break;
                    }
            var qt = Text(quote.Length > 170 ? quote[..170] + "…" : quote, 10, top: 6);
            qt.FontFamily = new M.FontFamily("Georgia");
            Cell(4, qt);
        }
        doc.Children.Add(table);
        doc.Children.Add(Text("Each row links to the city's exact words at its page in the digital copy. Egress results (NY Residential Code 2025) follow on the next page.", 10, ink: PanelTokens.TextMuted, top: 14));
        var page = new C.Border { Child = doc, Background = M.Brushes.White };
        var root = Themed(page, PanelTheme.Light);
        Save(root, 816, 1056, "14_permit_summary_house_proposed.png");
    }

    // ---- in Revit: the pane docked in the real window, and an ILLUSTRATIVE overlay on the canvas ---------------

    /// <summary>The Revit 2027 trial screenshot of 106 Ithaca Rd (guide_106, Floor Plan Level 1, dark theme, the
    /// Gordium pane docked at the left, tabbed with Properties), with the pane's render placed over its pane and, for
    /// the proposed, the checker's zoning figures drawn on the canvas as temporary graphics would draw them.</summary>
    private static void InRevit106(CheckResult house, string which, string pane, bool overlay)
    {
        var shot = Picture(Path.Combine(_pictures, "revit_106_screenshot.png"));
        var canvas = new C.Canvas { Width = shot.PixelWidth, Height = shot.PixelHeight };
        canvas.Children.Add(new C.Image { Source = shot, Width = shot.PixelWidth, Height = shot.PixelHeight });
        if (File.Exists(pane))
        {
            // the pane's area in the screenshot: under its title bar, above the Properties / Gordium tabs
            var img = new C.Image { Source = Picture(pane), Width = 343, Height = 406, Stretch = M.Stretch.Fill };
            C.Canvas.SetLeft(img, 0);
            C.Canvas.SetTop(img, 212);
            canvas.Children.Add(img);
        }
        if (overlay)
            Overlay106(canvas, house);
        var root = Themed(canvas, PanelTheme.Dark);
        Save(root, shot.PixelWidth, shot.PixelHeight, $"16_in_revit_house_{which}.png");
    }

    private static void Overlay106(C.Canvas canvas, CheckResult house)
    {
        // the plan's scale, from the screenshot: the 73 x 90 ft lot is the dashed outline (955,253)-(1313,693); the
        // street is its south edge (the model's y = 0)
        static W.Point P(double x, double y) => new(955 + x * 358.0 / 73, 693 - y * 440.0 / 90);
        string Get(string name, string key) => house.Items.FirstOrDefault(i => i.Name == name) is { } it && it.Raw.TryGetProperty(key, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "?";
        void Line(W.Point a, W.Point b, string brush, double thick = 1.5, bool dashed = true)
        {
            var l = new S.Line { X1 = a.X, Y1 = a.Y, X2 = b.X, Y2 = b.Y, StrokeThickness = thick };
            if (dashed)
                l.StrokeDashArray = [5, 3];
            l.SetResourceReference(S.Shape.StrokeProperty, brush);
            canvas.Children.Add(l);
        }
        void Label(double x, double y, string words, PanelStatus status)
        {
            var chip = new C.Border { CornerRadius = new W.CornerRadius(3), Padding = new W.Thickness(5, 1, 6, 2), BorderThickness = new W.Thickness(1) };
            chip.SetResourceReference(C.Border.BackgroundProperty, StatusLook.ChipBackground(status));
            chip.SetResourceReference(C.Border.BorderBrushProperty, StatusLook.Colour(status));
            var row = new C.StackPanel { Orientation = C.Orientation.Horizontal };
            row.Children.Add(PanelLook.Glyph(status, 11));
            row.Children.Add(Text(" " + words, 11, ink: PanelTokens.Text));
            chip.Child = row;
            C.Canvas.SetLeft(chip, x);
            C.Canvas.SetTop(chip, y);
            canvas.Children.Add(chip);
        }
        // the building's footprint: lot coverage does not comply (the checker's figures)
        var a = P(10, 65);
        var b = P(63, 30);
        var foot = new S.Rectangle { Width = b.X - a.X, Height = b.Y - a.Y, StrokeThickness = 3 };
        foot.SetResourceReference(S.Shape.StrokeProperty, PanelTokens.StatusFail);
        foot.SetResourceReference(S.Shape.FillProperty, PanelTokens.StatusFailFill);
        foot.Opacity = 0.85;
        C.Canvas.SetLeft(foot, a.X);
        C.Canvas.SetTop(foot, a.Y);
        canvas.Children.Add(foot);
        Label(a.X + 8, a.Y + 60, $"Lot coverage {Get("Lot coverage", "proposed")} · needs ≤ {Get("Lot coverage", "required")} · {Get("Lot coverage", "how_far")}", PanelStatus.Fails);
        // the required yards (dashed), each labelled with the checker's measured and required, in its verdict
        Line(P(0, 25), P(73, 25), PanelTokens.StatusPass);
        Label(P(0, 25).X + 4, P(0, 25).Y + 4, $"Front yard {Get("Front yard", "proposed")} · needs ≥ {Get("Front yard", "required")}", PanelStatus.Complies);
        Line(P(0, 67.5), P(73, 67.5), PanelTokens.StatusPass);
        Label(P(0, 90).X + 4, P(0, 90).Y + 6, $"Rear yard {Get("Rear yard", "proposed")} · needs ≥ {Get("Rear yard", "required")}", PanelStatus.Complies);
        Line(P(10, 0), P(10, 90), PanelTokens.StatusPass, dashed: true);
        Line(P(63, 0), P(63, 90), PanelTokens.StatusPass, dashed: true);
        Label(P(63, 50).X + 8, P(63, 50).Y + 40, $"Side yards {Get("Side yard, East", "proposed")} · at the limit", PanelStatus.Complies);
        var street = Text("STREET (the edge you picked)", 11, semi: true, ink: PanelTokens.TextMuted);
        C.Canvas.SetLeft(street, P(20, 0).X);
        C.Canvas.SetTop(street, P(0, 0).Y + 8);
        canvas.Children.Add(street);
        // the legend: what this is, and that nothing is in the model
        var legend = new C.Border { CornerRadius = new W.CornerRadius(4), Padding = new W.Thickness(10, 6, 10, 8), BorderThickness = new W.Thickness(1), Width = 360 };
        legend.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        legend.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        var lg = new C.StackPanel();
        lg.Children.Add(Text("ILLUSTRATIVE MOCKUP, drawn over a screenshot", 11, semi: true, ink: PanelTokens.StatusReview));
        lg.Children.Add(Text("Gordium's overlay: temporary graphics, nothing written to the model, gone when the pane closes. " +
                             "Colours are the checker's verdicts only: green only where it says complies.", 11, top: 2));
        legend.Child = lg;
        C.Canvas.SetLeft(legend, 1130);
        C.Canvas.SetTop(legend, 860);
        canvas.Children.Add(legend);
    }

    /// <summary>The childcare centre's own life-safety sheet (the architect's drawing, from the eval), with the rooms
    /// the checker found no route from marked needs review and an ILLUSTRATIVE path for the longest route it found.</summary>
    private static void ChildcareRoutes(CheckResult childcare)
    {
        var sheet = Picture(Path.Combine(_pictures, "childcare_life_safety_plan.png"));
        var canvas = new C.Canvas { Width = sheet.PixelWidth, Height = sheet.PixelHeight };
        canvas.Children.Add(new C.Image { Source = sheet, Width = sheet.PixelWidth, Height = sheet.PixelHeight });
        void Room(double x, double y, double w, double h, string name, bool above = false)
        {
            var r = new S.Rectangle { Width = w, Height = h, StrokeThickness = 3, RadiusX = 3, RadiusY = 3 };
            r.SetResourceReference(S.Shape.StrokeProperty, PanelTokens.StatusReview);
            r.SetResourceReference(S.Shape.FillProperty, PanelTokens.StatusReviewFill);
            r.Opacity = 0.75;
            C.Canvas.SetLeft(r, x);
            C.Canvas.SetTop(r, y);
            canvas.Children.Add(r);
            var chip = new C.Border { CornerRadius = new W.CornerRadius(3), Padding = new W.Thickness(5, 1, 6, 2), BorderThickness = new W.Thickness(1) };
            chip.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
            chip.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.StatusReview);
            var row = new C.StackPanel { Orientation = C.Orientation.Horizontal };
            row.Children.Add(PanelLook.Glyph(PanelStatus.Review, 12));
            row.Children.Add(Text($" {name}: no route to an exit found", 12, ink: PanelTokens.Text));
            chip.Child = row;
            C.Canvas.SetLeft(chip, x);
            C.Canvas.SetTop(chip, above ? y - 26 : y + h + 4);
            canvas.Children.Add(chip);
        }
        Room(1385, 455, 70, 75, "STORAGE (13)");
        Room(602, 438, 52, 74, "SPRINKLERED ABANDONED SPACE");
        Room(1300, 430, 78, 62, "SPRINKLERED ABANDONED SPACE", above: true);
        // the rows waiting on them, the checker's words (the first card's)
        var card = ResultRows.Build(childcare, "New Construction", [], null).Causes.FirstOrDefault();
        if (card is not null)
        {
            var note = new C.Border { CornerRadius = new W.CornerRadius(3), Padding = new W.Thickness(8, 4, 8, 5), BorderThickness = new W.Thickness(1), Width = 520 };
            note.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
            note.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.StatusReview);
            var ns = new C.StackPanel();
            ns.Children.Add(Text($"Fix 1 · {card.Items.Count} results need review until these rooms have a route", 12, semi: true));
            ns.Children.Add(Text("STORAGE (13): " + (card.Rooms.FirstOrDefault(r => r.Name.StartsWith("STORAGE"))?.Why ?? ""), 11, top: 2));
            note.Child = ns;
            C.Canvas.SetLeft(note, 1080);
            C.Canvas.SetTop(note, 800);
            canvas.Children.Add(note);
        }
        var legend = new C.Border { CornerRadius = new W.CornerRadius(4), Padding = new W.Thickness(10, 6, 10, 8), BorderThickness = new W.Thickness(1), Width = 420 };
        legend.SetResourceReference(C.Border.BackgroundProperty, PanelTokens.BgSurface);
        legend.SetResourceReference(C.Border.BorderBrushProperty, PanelTokens.Line);
        var lg = new C.StackPanel();
        lg.Children.Add(Text("ILLUSTRATIVE MOCKUP, drawn over the architect's life-safety sheet", 12, semi: true, ink: PanelTokens.StatusReview));
        lg.Children.Add(Text("In Revit this would be temporary graphics on the floor plan while the result is open: nothing written to the model. " +
                             "Amber is needs review, never green. The outlines are placed by hand on the sheet here; the rooms and words are the checker's.", 11, top: 2));
        legend.Child = lg;
        C.Canvas.SetLeft(legend, 40);
        C.Canvas.SetTop(legend, 40);
        canvas.Children.Add(legend);
        Save(Themed(canvas, PanelTheme.Light), sheet.PixelWidth, sheet.PixelHeight, "15_in_model_routes_childcare_proposed.png");
    }
}
