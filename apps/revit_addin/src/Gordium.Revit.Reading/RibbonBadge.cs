using System.Globalization;

namespace Gordium.Revit.Reading;

/// <summary>What the ribbon's Check project button says about the last check shown (the UI design pass, change 13).</summary>
public enum BadgeKind
{
    /// <summary>Nothing checked yet, a check that didn't finish, or one that sent nothing (a fact to set first): the
    /// plain icon, no badge.</summary>
    NotChecked,
    /// <summary>Results that still stand for the model: a red count for what does not comply, an amber count for
    /// what needs review (by hand or not checked included).</summary>
    Counts,
    /// <summary>Every result complies or doesn't apply, the checker's overall state is "complies", and at least one
    /// result complies: the only badge drawn in the pass colour.</summary>
    Complies,
    /// <summary>No result fails or needs review, yet the checker doesn't say the check complies (every rule set
    /// aside, or no rows): an amber "?", never the pass colour.</summary>
    Unclear,
    /// <summary>The model changed after the check: a clock, never the counts as if they were current.</summary>
    Stale,
}

/// <summary>The badge on Check project and its tooltip: counts of the checker's own rows, never a figure of the
/// add-in's (the UI design pass, change 13).</summary>
/// <param name="Kind">What is drawn.</param>
/// <param name="Fails">Rows that do not comply (0 unless <see cref="BadgeKind.Counts"/>).</param>
/// <param name="Review">Rows that need review, those to check by hand or not checked included (0 unless
/// <see cref="BadgeKind.Counts"/>).</param>
/// <param name="ToolTip">The tooltip: the counts in words, or why there are none.</param>
public sealed record BadgeState(BadgeKind Kind, int Fails, int Review, string ToolTip);

/// <summary>
/// The ribbon's status badge (docs/revit/ui_design_pass.md, changes 13 to 15), Revit-free so it is tested: from what
/// the Gordium pane shows, what Check project's 32 px icon carries (a red count of what fails and an amber count of
/// what needs review, a clock once the model changed, a pass tick only when nothing fails or needs review and the
/// checker says the project complies) and the tooltip saying it in words. The add-in swaps the button's LargeImage
/// and ToolTip at runtime (BadgeButton). Every count is a count of the checker's rows as the pane places them
/// (<see cref="ResultList.Place"/>); a stale answer shows only the clock, never its counts as current.
/// </summary>
public static class RibbonBadge
{
    /// <summary>The badge for what the pane shows: <paramref name="model"/> null when nothing was checked (a fact to
    /// set first, <paramref name="missing"/> of them; a check that failed: <paramref name="failed"/>).</summary>
    public static BadgeState Of(ResultModel? model, DateTime checkedAt, int missing = 0, bool failed = false)
    {
        if (failed)
            return new(BadgeKind.NotChecked, 0, 0,
                       "Nothing is checked now: the last check didn't finish, or the project checked was closed. Click to check this project.");
        if (model is null)
            return new(BadgeKind.NotChecked, 0, 0, missing > 0
                ? $"Not checked yet: {Count(missing, "fact", "facts")} to set first; the Gordium pane lists {(missing == 1 ? "it" : "them")}. Click to check again."
                : NotCheckedTip);
        var at = checkedAt.ToString("HH:mm", CultureInfo.InvariantCulture);
        if (model.Stale is not null)
            return new(BadgeKind.Stale, 0, 0,
                       $"The model changed after the check at {at}: its results may not hold. Click to check again.");
        var placed = ResultList.Place(model);
        var fails = placed.Count(r => r.Section == ListSection.Fails);
        var review = placed.Count(r => r.Section is ListSection.Review or ListSection.ByHand);
        var byHand = placed.Count(r => r.Section == ListSection.ByHand);
        var complies = placed.Count(r => r.Section == ListSection.Complies && r.Row.Tone == Tone.Complies);
        var aside = placed.Count(r => r.Section == ListSection.Complies && r.Row.Tone != Tone.Complies);
        var said = new List<string>();
        if (fails > 0)
            said.Add($"{fails} {(fails == 1 ? "does" : "do")} not comply");
        if (review > 0)
            said.Add($"{review} need{(review == 1 ? "s" : "")} review" + (byHand > 0 ? $" ({byHand} by hand or not checked)" : ""));
        if (complies > 0)
            said.Add($"{complies} compl{(complies == 1 ? "ies" : "y")}");
        if (aside > 0)
            said.Add($"{aside} not applicable");
        var words = said.Count == 0 ? "no results" : string.Join(", ", said);
        if (fails > 0 || review > 0)
            return new(BadgeKind.Counts, fails, review,
                       $"Checked {at}: {words}. Click to check again; the Gordium pane shows them.");
        if (model.State == Gordium.Worker.Verdict.Complies && complies > 0)
            return new(BadgeKind.Complies, 0, 0, $"Checked {at}: {words}. Click to check again.");
        return new(BadgeKind.Unclear, 0, 0,
                   $"Checked {at}: {words}; the checker says {ResultText.StateWords(model.State).ToLowerInvariant()}. Open the Gordium pane.");
    }

    /// <summary>Check project's own tooltip, before any check (RibbonPlan's).</summary>
    public const string NotCheckedTip = "Check this project against its zoning and egress rules";

    private static string Count(int n, string one, string many) => $"{n} {(n == 1 ? one : many)}";

    /// <summary>A count as its pill says it: up to 99, then "99+" (the tooltip says the exact count).</summary>
    public static string Pill(int n) => n > 99 ? "99+" : n.ToString(CultureInfo.InvariantCulture);

    /// <summary>The status a badge is drawn in at 16 px (one dot: the worst there is), or null for none.</summary>
    public static PanelStatus? Dot(BadgeState badge)
    {
        ArgumentNullException.ThrowIfNull(badge);
        return badge.Kind switch
        {
            BadgeKind.Counts => badge.Fails > 0 ? PanelStatus.Fails : PanelStatus.Review,
            BadgeKind.Complies => PanelStatus.Complies,
            BadgeKind.Unclear => PanelStatus.Review,
            BadgeKind.Stale => PanelStatus.Stale,
            _ => null,
        };
    }

    // ---- drawing ------------------------------------------------------------------------------------------------

    // a 5 x 7 pixel font: the digits, "+" and "?" (each row's five pixels, left first)
    private static readonly Dictionary<char, string[]> Font = new()
    {
        ['0'] = [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
        ['1'] = ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
        ['2'] = [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
        ['3'] = ["####.", "....#", "....#", ".###.", "....#", "....#", "####."],
        ['4'] = ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
        ['5'] = ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
        ['6'] = ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."],
        ['7'] = ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
        ['8'] = [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
        ['9'] = [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
        ['+'] = [".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."],
        ['?'] = [".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."],
    };

    private const int PillHeight = 11;

    /// <summary>Check project's icon with its badge, at <paramref name="size"/> px (16 or 32) in a theme: straight
    /// RGBA, row by row, top first (as <see cref="RibbonIcons.Pixels"/>). At 32 px: the counts as pills at the top
    /// right (red for what fails, amber for what needs review, side by side, or when both don't fit the red at the
    /// top right and the amber at the bottom right, in the plan outline's notch), a pass tick, an amber "?" or a
    /// clock; at 16 px one dot of the worst. No badge: the plain icon.</summary>
    public static byte[] Pixels(BadgeState badge, int size, PanelTheme theme)
    {
        ArgumentNullException.ThrowIfNull(badge);
        var px = RibbonIcons.Pixels(RibbonIcons.CheckProject, size, theme);
        var colours = PanelTokens.Colours(theme);
        var ring = colours[PanelTokens.BgSurface];
        if (Dot(badge) is not { } worst)
            return px;
        if (size == 16)
        {
            Disc(px, size, 12, 4, 4.5, ring);
            Disc(px, size, 12, 4, 3.5, colours[StatusLook.Colour(worst)]);
            return px;
        }
        if (size != 32)
            throw new ArgumentOutOfRangeException(nameof(size), size, "Revit's ribbon icons are 16 or 32 px");
        switch (badge.Kind)
        {
            case BadgeKind.Counts:
                var pills = new List<(string Text, Rgb Ink)>();
                if (badge.Fails > 0)
                    pills.Add((Pill(badge.Fails), colours[PanelTokens.StatusFail]));
                if (badge.Review > 0)
                    pills.Add((Pill(badge.Review), colours[PanelTokens.StatusReview]));
                var widths = pills.Select(p => PillWidth(p.Text)).ToList();
                var sideBySide = widths.Sum() + widths.Count - 1 <= size;
                var right = size;
                for (var i = pills.Count - 1; i >= 0; i--)
                {
                    var left = sideBySide ? right - widths[i] : size - widths[i];
                    var y = sideBySide || i == 0 ? 0 : size - PillHeight;      // stacked: the second in the plan's notch, bottom right
                    DrawPill(px, size, left, y, pills[i].Text, pills[i].Ink, ring);
                    right = left - 1;
                }
                break;
            case BadgeKind.Unclear:
                DrawPill(px, size, size - PillWidth("?"), 0, "?", colours[PanelTokens.StatusReview], ring);
                break;
            case BadgeKind.Complies:
                Disc(px, size, 26, 6, 6.5, ring);
                Disc(px, size, 26, 6, 5.5, colours[PanelTokens.StatusPass]);
                Stroke(px, size, [(23.2, 6.2), (25.2, 8.2), (28.8, 4.2)], 0.9, ring);
                break;
            case BadgeKind.Stale:
                Disc(px, size, 26, 6, 6.5, ring);
                Disc(px, size, 26, 6, 5.5, colours[PanelTokens.StatusStale]);
                Stroke(px, size, [(26, 2.6), (26, 6), (28.4, 7.6)], 0.8, ring);
                break;
        }
        return px;
    }

    /// <summary>The badge's icon as a PNG file's bytes (as <see cref="RibbonIcons.Png"/>).</summary>
    public static byte[] Png(BadgeState badge, int size, PanelTheme theme) => RibbonIcons.EncodePng(Pixels(badge, size, theme), size);

    /// <summary>A pill's width in pixels: 3 of padding each side of its characters (5 wide, 1 apart), at least round.</summary>
    internal static int PillWidth(string text) => Math.Max(PillHeight, 6 + text.Length * 6 - 1);

    private static void DrawPill(byte[] px, int size, int left, int top, string text, Rgb ink, Rgb paper)
    {
        // the ring (the surface colour, a pixel round it, so the pill reads over the icon's strokes), then the pill
        RoundRect(px, size, left - 1, top - 1, PillWidth(text) + 2, PillHeight + 2, paper);
        RoundRect(px, size, left, top, PillWidth(text), PillHeight, ink);
        var x = left + (PillWidth(text) - (text.Length * 6 - 1)) / 2;
        foreach (var ch in text)
        {
            var rows = Font[ch];
            for (var j = 0; j < 7; j++)
                for (var i = 0; i < 5; i++)
                    if (rows[j][i] == '#')
                        Paint(px, size, x + i, top + 2 + j, paper, 1);
            x += 6;
        }
    }

    // a rectangle with fully round ends (radius half its height), anti-aliased by 8 x 8 samples a pixel
    private static void RoundRect(byte[] px, int size, int left, int top, int width, int height, Rgb ink)
    {
        var r = height / 2.0;
        Fill(px, size, (sx, sy) =>
        {
            var cx = Math.Clamp(sx, left + r, left + width - r);
            var cy = top + r;
            var dx = sx - cx;
            var dy = sy - cy;
            return dx * dx + dy * dy <= r * r;
        }, ink);
    }

    private static void Disc(byte[] px, int size, double cx, double cy, double r, Rgb ink) =>
        Fill(px, size, (sx, sy) => (sx - cx) * (sx - cx) + (sy - cy) * (sy - cy) <= r * r, ink);

    private static void Stroke(byte[] px, int size, (double X, double Y)[] points, double half, Rgb ink) =>
        Fill(px, size, (sx, sy) =>
        {
            for (var k = 0; k + 1 < points.Length; k++)
                if (Distance(sx, sy, points[k], points[k + 1]) <= half)
                    return true;
            return false;
        }, ink);

    private static void Fill(byte[] px, int size, Func<double, double, bool> inside, Rgb ink)
    {
        const int sub = 8;
        for (var y = 0; y < size; y++)
            for (var x = 0; x < size; x++)
            {
                var hits = 0;
                for (var j = 0; j < sub; j++)
                    for (var i = 0; i < sub; i++)
                        if (inside(x + (i + 0.5) / sub, y + (j + 0.5) / sub))
                            hits++;
                if (hits > 0)
                    Paint(px, size, x, y, ink, hits / (double)(sub * sub));
            }
    }

    private static void Paint(byte[] px, int size, int x, int y, Rgb ink, double a)
    {
        if (x < 0 || y < 0 || x >= size || y >= size)
            return;
        RibbonIcons.Over(px, (y * size + x) * 4, ink, a);
    }

    private static double Distance(double x, double y, (double X, double Y) a, (double X, double Y) b)
    {
        double dx = b.X - a.X, dy = b.Y - a.Y;
        var len2 = dx * dx + dy * dy;
        var t = len2 == 0 ? 0 : Math.Clamp(((x - a.X) * dx + (y - a.Y) * dy) / len2, 0, 1);
        double ex = x - (a.X + t * dx), ey = y - (a.Y + t * dy);
        return Math.Sqrt(ex * ex + ey * ey);
    }
}
