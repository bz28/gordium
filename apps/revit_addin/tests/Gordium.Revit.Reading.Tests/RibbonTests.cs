using System.Buffers.Binary;
using System.IO.Compression;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The Gordium tab (RibbonPlan, RibbonIcons; design pass section 2.2): an architect's build shows exactly
/// Check project, Mark facts, Panel and About, the trial's test tools only with the trial switch; every button has a
/// one-line tooltip and at most three short lines more; every icon is a real PNG at 16 and 32 px in both themes.</summary>
public sealed class RibbonTests
{
    private static readonly string[] Architect = ["Check project", "Mark facts", "Panel", "About"];
    private static readonly string[] TestTools = ["Check box house", "Record scenes", "Read inside", "Record houses"];

    [Fact]
    public void Trial_off_shows_exactly_the_architect_s_buttons()
    {
        Assert.Equal(["Check", "Results", "Help"], RibbonPlan.Panels(trial: false).Select(p => p.Name));
        Assert.Equal(Architect, RibbonPlan.Buttons(trial: false).Select(b => b.Name));
        Assert.Equal(["Check project", "Mark facts"], RibbonPlan.Panels(false)[0].Buttons.Select(b => b.Name));
        Assert.Equal(["Panel"], RibbonPlan.Panels(false)[1].Buttons.Select(b => b.Name));
        Assert.Equal(["About"], RibbonPlan.Panels(false)[2].Buttons.Select(b => b.Name));
        Assert.DoesNotContain(RibbonPlan.Buttons(false), b => TestTools.Contains(b.Name) || b.ToolTip.StartsWith("Trial", StringComparison.Ordinal));
    }

    [Fact]
    public void Trial_on_adds_the_test_tools_in_a_trial_panel_last()
    {
        var panels = RibbonPlan.Panels(trial: true);
        Assert.Equal(["Check", "Results", "Help", "Trial"], panels.Select(p => p.Name));
        Assert.Equal(TestTools, panels[3].Buttons.Select(b => b.Name));
        Assert.Equal([.. Architect, .. TestTools], RibbonPlan.Buttons(true).Select(b => b.Name));
        // the ids stay the ones Revit already knows (a Quick Access Toolbar copy keeps working)
        Assert.Equal(["gordium_check_project", "gordium_mark_for_egress", "gordium_results_panel", "gordium_about",
                      "gordium_check_box_house", "gordium_record_scenes", "gordium_read_interior", "gordium_record_houses"],
                     RibbonPlan.Buttons(true).Select(b => b.Id));
    }

    [Theory]
    [InlineData(false, null, false)]
    [InlineData(false, "", false)]
    [InlineData(false, "0", false)]
    [InlineData(false, "true", false)]
    [InlineData(false, "11", false)]
    [InlineData(false, "1", true)]
    [InlineData(false, " 1 ", true)]
    [InlineData(true, null, true)]
    [InlineData(true, "0", true)]
    public void The_trial_switch_is_a_trial_build_or_GORDIUM_TRIAL_1(bool build, string? variable, bool on) =>
        Assert.Equal(on, RibbonPlan.TrialOn(build, variable));

    [Fact]
    public void Every_button_has_a_one_line_tooltip_and_at_most_three_short_lines_more()
    {
        foreach (var b in RibbonPlan.Buttons(trial: true))
        {
            Assert.False(string.IsNullOrWhiteSpace(b.ToolTip), b.Id);
            Assert.DoesNotContain('\n', b.ToolTip);
            Assert.True(b.ToolTip.Length <= 80, $"{b.Id}'s tooltip is {b.ToolTip.Length} characters");
            Assert.InRange(b.LongDescription.Count, 1, 3);
            foreach (var line in b.LongDescription)
            {
                Assert.False(string.IsNullOrWhiteSpace(line), b.Id);
                Assert.DoesNotContain('\n', line);
                Assert.True(line.Length <= 110, $"{b.Id}: \"{line}\" is {line.Length} characters");
            }
            Assert.Equal(b.LongDescription.Count, b.LongDescriptionText.Split('\n').Length);
            Assert.True(b.Text.Split('\n').Length <= 2, b.Id);
        }
        Assert.Equal(RibbonPlan.Buttons(true).Count(), RibbonPlan.Buttons(true).Select(b => b.Id).Distinct().Count());
    }

    [Fact]
    public void Check_project_s_long_description_says_what_is_read_where_results_appear_and_nothing_sent_while_a_fact_is_missing()
    {
        var check = RibbonPlan.Buttons(false).Single(b => b.Id == RibbonPlan.CheckProject);
        Assert.Equal("Check this project against its zoning and egress rules", check.ToolTip);
        Assert.Contains("Reads", check.LongDescription[0], StringComparison.Ordinal);
        Assert.Contains("Gordium panel", check.LongDescription[1], StringComparison.Ordinal);
        Assert.Contains("nothing is sent", check.LongDescription[2], StringComparison.Ordinal);
    }

    [Fact]
    public void Only_panel_and_about_are_usable_with_no_project_open()
    {
        Assert.Equal(["gordium_results_panel", "gordium_about"], RibbonPlan.Buttons(true).Where(b => b.AnyTime).Select(b => b.Id));
    }

    public static TheoryData<string, int, PanelTheme> EveryIcon()
    {
        var data = new TheoryData<string, int, PanelTheme>();
        foreach (var icon in RibbonPlan.Buttons(trial: true).Select(b => b.Icon).Distinct())
            foreach (var size in RibbonIcons.Sizes)
                foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
                    data.Add(icon, size, theme);
        return data;
    }

    [Theory]
    [MemberData(nameof(EveryIcon))]
    public void Every_icon_is_a_png_at_16_and_32_px_in_both_themes(string icon, int size, PanelTheme theme)
    {
        var (w, h, rgba) = Decode(RibbonIcons.Png(icon, size, theme));
        Assert.Equal(size, w);
        Assert.Equal(size, h);
        Assert.Equal(RibbonIcons.Pixels(icon, size, theme), rgba);
        var colours = PanelTokens.Colours(theme);
        // drawn in the outline ink and the accent (each at least half opaque somewhere), every pixel one of the two
        // inks or a blend of them where the accent crosses the outline
        var shown = Enumerable.Range(0, w * h).Where(i => rgba[i * 4 + 3] >= 128).Select(i => new Rgb(rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2])).ToHashSet();
        Assert.Contains(colours[PanelTokens.Text], shown);
        Assert.Contains(colours[PanelTokens.Accent], shown);
        Assert.All(Enumerable.Range(0, w * h).Where(i => rgba[i * 4 + 3] > 0), i =>
            Assert.True(Between(new Rgb(rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2]), colours[PanelTokens.Text], colours[PanelTokens.Accent]),
                        $"pixel {i}: neither ink nor a blend of the two"));
        for (var i = 0; i < size; i++)
            foreach (var (x, y) in new[] { (i, 0), (i, size - 1), (0, i), (size - 1, i) })
                Assert.True(rgba[(y * size + x) * 4 + 3] < 128, $"{icon} {size} {theme}: ink at the edge ({x},{y})");
        // most of the square is clear: an icon, not a block (its ink covers under half of it)
        var ink = Enumerable.Range(0, w * h).Sum(i => rgba[i * 4 + 3] / 255.0);
        Assert.True(ink < w * h / 2.0, $"{icon} {size} {theme}: ink covers {ink:0} of {w * h} pixels");
    }

    [Fact]
    public void Light_and_dark_differ_and_never_use_the_pass_green()
    {
        foreach (var icon in RibbonIcons.Shapes.Keys)
            foreach (var size in RibbonIcons.Sizes)
            {
                Assert.NotEqual(RibbonIcons.Pixels(icon, size, PanelTheme.Light), RibbonIcons.Pixels(icon, size, PanelTheme.Dark));
                foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
                {
                    var green = PanelTokens.Colours(theme)[PanelTokens.StatusPass];
                    var px = RibbonIcons.Pixels(icon, size, theme);
                    Assert.DoesNotContain(Enumerable.Range(0, size * size), i => px[i * 4 + 3] > 0 && new Rgb(px[i * 4], px[i * 4 + 1], px[i * 4 + 2]) == green);
                }
            }
        Assert.All(RibbonIcons.Shapes.Values.SelectMany(s => s.Strokes), s => Assert.Contains(s.Ink, new[] { PanelTokens.Text, PanelTokens.Accent }));
    }

    [Fact]
    public void Every_stroke_stays_on_the_grid_with_a_margin_and_the_same_weight()
    {
        foreach (var shape in RibbonIcons.Shapes.Values)
            foreach (var stroke in shape.Strokes)
            {
                Assert.NotEmpty(stroke.Points);
                Assert.All(stroke.Points, p => { Assert.InRange(p.X, 1.5, 14.5); Assert.InRange(p.Y, 1.5, 14.5); });
                Assert.InRange(stroke.Weight, 1, 1.5);                        // a dot a touch heavier, nothing thinner
            }
        Assert.Equal(1, RibbonIcons.StrokePx(16));
        Assert.Equal(2, RibbonIcons.StrokePx(32));
        Assert.Throws<ArgumentOutOfRangeException>(() => RibbonIcons.StrokePx(24));
        Assert.Throws<ArgumentOutOfRangeException>(() => RibbonIcons.Png("no_such_icon", 16, PanelTheme.Light));
    }

    [Fact]
    public void Every_icon_ink_stands_out_on_revit_s_panels_in_both_themes()
    {
        // WCAG 1.4.11 (a graphic at least 3:1), on the pane and a card, the token surfaces nearest Revit's ribbon
        foreach (var theme in new[] { PanelTheme.Light, PanelTheme.Dark })
        {
            var c = PanelTokens.Colours(theme);
            foreach (var ink in new[] { PanelTokens.Text, PanelTokens.Accent })
                foreach (var on in new[] { PanelTokens.BgPane, PanelTokens.BgSurface })
                    Assert.True(PanelTokens.Contrast(c[ink], c[on]) >= 3, $"{theme} {ink} on {on}");
        }
    }

    [Fact]
    public void The_png_crc_is_iso_3309_s()
    {
        // the standard check value of CRC-32: "123456789" gives CBF43926
        Assert.Equal(0xCBF43926u, RibbonIcons.Crc32("123456789"u8));
    }

    private static bool Between(Rgb c, Rgb a, Rgb b)
    {
        static bool In(byte v, byte x, byte y) => v >= Math.Min(x, y) && v <= Math.Max(x, y);
        return In(c.R, a.R, b.R) && In(c.G, a.G, b.G) && In(c.B, a.B, b.B);
    }

    /// <summary>A PNG read back, checking what a viewer checks: the signature, every chunk's CRC, an RGBA 8-bit header,
    /// rows with no filter.</summary>
    private static (int W, int H, byte[] Rgba) Decode(byte[] png)
    {
        Assert.Equal(new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A }, png[..8]);
        int at = 8, w = 0, h = 0;
        using var idat = new MemoryStream();
        var types = new List<string>();
        while (at < png.Length)
        {
            var len = BinaryPrimitives.ReadInt32BigEndian(png.AsSpan(at));
            var type = System.Text.Encoding.ASCII.GetString(png, at + 4, 4);
            var data = png.AsSpan(at + 8, len);
            Assert.Equal(BinaryPrimitives.ReadUInt32BigEndian(png.AsSpan(at + 8 + len)), RibbonIcons.Crc32(png.AsSpan(at + 4, len + 4)));
            types.Add(type);
            if (type == "IHDR")
            {
                w = BinaryPrimitives.ReadInt32BigEndian(data);
                h = BinaryPrimitives.ReadInt32BigEndian(data[4..]);
                Assert.Equal(8, data[8]);
                Assert.Equal(6, data[9]);
            }
            else if (type == "IDAT")
                idat.Write(data);
            at += 12 + len;
        }
        Assert.Equal("IHDR", types[0]);
        Assert.Equal("IEND", types[^1]);
        idat.Position = 0;
        using var z = new ZLibStream(idat, CompressionMode.Decompress);
        using var raw = new MemoryStream();
        z.CopyTo(raw);
        var rows = raw.ToArray();
        Assert.Equal(h * (1 + w * 4), rows.Length);
        var rgba = new byte[w * h * 4];
        for (var y = 0; y < h; y++)
        {
            Assert.Equal(0, rows[y * (1 + w * 4)]);
            Array.Copy(rows, y * (1 + w * 4) + 1, rgba, y * w * 4, w * 4);
        }
        return (w, h, rgba);
    }
}
