using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;


namespace Gordium.Revit.Ux2Prototype;

/// <summary>Draws every proposed screen off-screen, light and dark, at the docked pane's 340 px, to PNG.
/// Usage: <c>Gordium.Revit.Ux2Prototype &lt;out dir&gt;</c>.</summary>
internal static class Program
{
    /// <summary>A docked pane's usual height in the trial (Ben's screenshot: the pane is 760 px tall at 1536 x 960):
    /// a dashed line marks it, so a render shows what is below the fold.</summary>
    private const int Fold = 740;

    [STAThread]
    private static int Main(string[] args)
    {
        var outDir = args[0];
        Directory.CreateDirectory(outDir);
        Screens.Data = JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "screens.json"))).RootElement;
        var screens = new (string Name, Func<FrameworkElement> Make, int Width, bool Themes)[]
        {
            ("01_welcome", Screens.Welcome, 340, true),
            ("02_setup_apartment", () => Screens.Setup(false), 340, true),
            ("03_setup_filled_apartment", () => Screens.Setup(true), 340, true),
            ("03b_setup_more_facts_open", Screens.SetupMoreOpen, 340, true),
            ("04_picking_street_edge", Screens.Picking, 340, true),
            ("04b_pick_confirm_dialog", Screens.PickConfirm, 460, false),
            ("05_checking", () => Screens.Checking(34), 340, true),
            ("05b_checking_long", () => Screens.Checking(52), 340, true),
            ("06_results_what_to_fix_apartment", () => Screens.ResultsFix(false), 340, true),
            ("06b_results_what_to_fix_house", Screens.ResultsHouse, 340, true),
            ("07_fix_open_answer_here", () => Screens.ResultsFix(true), 340, true),
            ("08_detail", () => Screens.Detail(false), 340, true),
            ("08b_detail_why_open", () => Screens.Detail(true), 340, true),
            ("09_by_code", () => Screens.ByCode(false), 340, true),
            ("09b_by_code_chapter_open", () => Screens.ByCode(true), 340, true),
            ("10_what_changed_house", Screens.WhatChanged, 340, true),
            ("11_error_timeout", Screens.ErrorTimeout, 340, true),
            ("11b_error_states_all", Screens.ErrorSheet, 340, true),
            ("12_stale", Screens.Stale, 340, true),
            ("13_selection_strip", Screens.Selection, 340, true),
            ("14_ribbon_badge", Screens.Badges, 340, true),
            ("15_summary_by_code", Screens.Summary, 720, false),
        };
        foreach (var dark in new[] { false, true })
        {
            T.Set(dark);
            foreach (var (name, make, width, themes) in screens)
            {
                if (dark && !themes)
                    continue;
                var view = make();
                var file = Path.Combine(outDir, $"{name}_proposed{(dark ? "_dark" : "")}.png");
                var h = Render(view, width, file, width == 340);
                Console.WriteLine($"{Path.GetFileName(file)}: {width} x {h}");
            }
        }
        return 0;
    }

    private static int Render(FrameworkElement view, int width, string file, bool fold)
    {
        TextOptions.SetTextFormattingMode(view, TextFormattingMode.Display);
        TextOptions.SetTextRenderingMode(view, TextRenderingMode.ClearType);
        var host = new System.Windows.Controls.Grid { Width = width, Background = T.Pane };
        host.Children.Add(view);
        host.Measure(new Size(width, double.PositiveInfinity));
        var height = Math.Max(fold ? 520 : 100, (int)Math.Ceiling(host.DesiredSize.Height));
        if (fold && height > Fold)
        {
            // the fold: where a docked pane of the usual height stops showing (what is below needs a scroll)
            var line = new System.Windows.Shapes.Line { X1 = 0, X2 = width, Y1 = Fold, Y2 = Fold, Stroke = Brushes.Magenta, StrokeThickness = 1, StrokeDashArray = [4, 3], IsHitTestVisible = false };
            var tag = new System.Windows.Controls.TextBlock { Text = "fold (740 px)", Foreground = Brushes.Magenta, FontSize = 9, Margin = new Thickness(width - 62, Fold - 12, 0, 0) };
            var overlay = new System.Windows.Controls.Canvas { IsHitTestVisible = false };
            overlay.Children.Add(line);
            overlay.Children.Add(tag);
            System.Windows.Controls.Canvas.SetTop(tag, 0);
            host.Children.Add(overlay);
        }
        host.Measure(new Size(width, height));
        host.Arrange(new Rect(0, 0, width, height));
        host.UpdateLayout();
        var bmp = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
        bmp.Render(host);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(bmp));
        using var f = File.Create(file);
        enc.Save(f);
        return height;
    }
}
