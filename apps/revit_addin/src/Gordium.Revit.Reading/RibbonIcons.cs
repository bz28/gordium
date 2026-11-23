using System.Buffers.Binary;
using System.IO.Compression;

namespace Gordium.Revit.Reading;

/// <summary>A point on an icon's 16-unit grid (0,0 top left; 16,16 bottom right).</summary>
public readonly record struct IconPoint(double X, double Y);

/// <summary>One stroke of an icon: a line through its points (closed back to the first when <paramref name="Closed"/>;
/// a single point is a dot), drawn in a colour token (<see cref="PanelTokens.Text"/> or <see cref="PanelTokens.Accent"/>).</summary>
public sealed record IconStroke(string Ink, IReadOnlyList<IconPoint> Points, bool Closed = false, double Weight = 1);

/// <summary>A ribbon icon as vector strokes, drawn in order (the accent over the outline).</summary>
public sealed record IconShape(string Name, IReadOnlyList<IconStroke> Strokes);

/// <summary>
/// The Gordium tab's icons (docs/revit/ui_design_pass.md section 2.2): simple strokes on one 16-unit grid, drawn here
/// to PNG at the two sizes Revit's ribbon uses (16 px small, 32 px large) in Revit's light and dark themes, from the
/// panel's colour tokens (the outline in <c>text</c>, the mark in <c>accent</c>; never the pass green, which is only
/// for what complies). Every outline and line has the same weight at a size (<see cref="StrokePx"/>); a tick and a dot are half again as heavy,
/// so the mark reads first and stays solid at 16 px. No icon font, no
/// downloaded image: the add-in draws these when Revit loads it, and swaps them when Revit's theme changes.
/// </summary>
public static class RibbonIcons
{
    public const string CheckProject = "check_project";
    public const string MarkFacts = "mark_facts";
    public const string Panel = "panel";
    public const string About = "about";
    public const string TrialTool = "trial_tool";

    /// <summary>The two sizes Revit's ribbon shows: Image (16) and LargeImage (32).</summary>
    public static IReadOnlyList<int> Sizes { get; } = [16, 32];

    /// <summary>A stroke's width in pixels at a size: 1 at 16 px, 2 at 32 px (every icon the same, one grid unit), so a
    /// straight line on a half unit fills whole pixels and stays sharp, as Revit's own icons are.</summary>
    public static double StrokePx(int size) => size switch
    {
        16 => 1,
        32 => 2,
        _ => throw new ArgumentOutOfRangeException(nameof(size), size, "Revit's ribbon icons are 16 or 32 px"),
    };

    private static IconPoint P(double x, double y) => new(x, y);

    private static IconStroke Line(params IconPoint[] points) => new(PanelTokens.Text, points);
    private static IconStroke Outline(params IconPoint[] points) => new(PanelTokens.Text, points, Closed: true);
    private static IconStroke Mark(params IconPoint[] points) => new(PanelTokens.Accent, points);
    /// <summary>A tick, half again as heavy as an outline, so the mark reads first (and a diagonal stays solid at 16 px).</summary>
    private static IconStroke Tick(params IconPoint[] points) => new(PanelTokens.Accent, points, Weight: 1.5);

    private static IconPoint[] Circle(double cx, double cy, double r, int n = 32) =>
        [.. Enumerable.Range(0, n).Select(i => P(cx + r * Math.Cos(2 * Math.PI * i / n), cy + r * Math.Sin(2 * Math.PI * i / n)))];

    /// <summary>Every icon, by name.</summary>
    public static IReadOnlyDictionary<string, IconShape> Shapes { get; } = new[]
    {
        // a check mark in a plan outline (an L-shaped floor plan)
        new IconShape(CheckProject,
        [
            Outline(P(2.5, 2.5), P(13.5, 2.5), P(13.5, 8.5), P(9.5, 8.5), P(9.5, 13.5), P(2.5, 13.5)),
            Tick(P(4.5, 7), P(6.5, 9), P(11, 4.5)),
        ]),
        // a tag with a tick
        new IconShape(MarkFacts,
        [
            Outline(P(1.5, 8), P(5.5, 3.5), P(14.5, 3.5), P(14.5, 12.5), P(5.5, 12.5)),
            new IconStroke(PanelTokens.Text, [P(5, 8)], Weight: 1.5),
            Tick(P(7.5, 8), P(9.5, 10), P(12.5, 6)),
        ]),
        // a window with a panel docked at its right, its rows in the accent
        new IconShape(Panel,
        [
            Outline(P(1.5, 2.5), P(14.5, 2.5), P(14.5, 13.5), P(1.5, 13.5)),
            Line(P(9.5, 2.5), P(9.5, 13.5)),
            Mark(P(11.5, 5.5), P(12.5, 5.5)),
            Mark(P(11.5, 8.5), P(12.5, 8.5)),
            Mark(P(11.5, 11.5), P(12.5, 11.5)),
        ]),
        // an i in a circle
        new IconShape(About,
        [
            Outline(Circle(7.5, 8, 6)),
            new IconStroke(PanelTokens.Accent, [P(7.5, 4.5)], Weight: 1.5),
            Mark(P(7.5, 7.5), P(7.5, 11.5)),
        ]),
        // a beaker: the trial's test tools
        new IconShape(TrialTool,
        [
            Line(P(5.5, 2.5), P(5.5, 6.5), P(2.5, 13.5), P(13.5, 13.5), P(10.5, 6.5), P(10.5, 2.5)),
            Line(P(4.5, 2.5), P(11.5, 2.5)),
            Mark(P(4.5, 10.5), P(11.5, 10.5)),
        ]),
    }.ToDictionary(s => s.Name, StringComparer.Ordinal);

    /// <summary>An icon drawn at <paramref name="size"/> px in a theme: straight RGBA, row by row, top first.</summary>
    public static byte[] Pixels(string name, int size, PanelTheme theme)
    {
        if (!Shapes.TryGetValue(name, out var shape))
            throw new ArgumentOutOfRangeException(nameof(name), name, "no such icon");
        var colours = PanelTokens.Colours(theme);
        var scale = size / 16.0;
        var px = new byte[size * size * 4];
        const int sub = 8;                                   // 8 x 8 samples a pixel: smooth edges
        foreach (var stroke in shape.Strokes)
        {
            var ink = colours[stroke.Ink];
            var half = StrokePx(size) * stroke.Weight / 2;
            var pts = stroke.Points.Select(p => (X: p.X * scale, Y: p.Y * scale)).ToList();
            var segs = new List<((double X, double Y) A, (double X, double Y) B)>();
            for (var i = 0; i + 1 < pts.Count; i++)
                segs.Add((pts[i], pts[i + 1]));
            if (stroke.Closed && pts.Count > 2)
                segs.Add((pts[^1], pts[0]));
            if (pts.Count == 1)
                segs.Add((pts[0], pts[0]));
            for (var y = 0; y < size; y++)
                for (var x = 0; x < size; x++)
                {
                    var hits = 0;
                    for (var j = 0; j < sub; j++)
                        for (var i = 0; i < sub; i++)
                        {
                            var sx = x + (i + 0.5) / sub;
                            var sy = y + (j + 0.5) / sub;
                            if (segs.Any(s => Distance(sx, sy, s.A, s.B) <= half))
                                hits++;
                        }
                    if (hits > 0)
                        Over(px, (y * size + x) * 4, ink, hits / (double)(sub * sub));
                }
        }
        return px;
    }

    /// <summary>An icon as a PNG file's bytes (8-bit RGBA, 96 dpi).</summary>
    public static byte[] Png(string name, int size, PanelTheme theme) => EncodePng(Pixels(name, size, theme), size);

    private static double Distance(double x, double y, (double X, double Y) a, (double X, double Y) b)
    {
        double dx = b.X - a.X, dy = b.Y - a.Y;
        var len2 = dx * dx + dy * dy;
        var t = len2 == 0 ? 0 : Math.Clamp(((x - a.X) * dx + (y - a.Y) * dy) / len2, 0, 1);
        double ex = x - (a.X + t * dx), ey = y - (a.Y + t * dy);
        return Math.Sqrt(ex * ex + ey * ey);
    }

    /// <summary>Paints <paramref name="ink"/> at coverage <paramref name="a"/> over the pixel (straight alpha).</summary>
    internal static void Over(byte[] px, int at, Rgb ink, double a)
    {
        var da = px[at + 3] / 255.0;
        var oa = a + da * (1 - a);
        double Mix(byte src, byte dst) => (src * a + dst * da * (1 - a)) / oa;
        px[at] = (byte)Math.Round(Mix(ink.R, px[at]));
        px[at + 1] = (byte)Math.Round(Mix(ink.G, px[at + 1]));
        px[at + 2] = (byte)Math.Round(Mix(ink.B, px[at + 2]));
        px[at + 3] = (byte)Math.Round(oa * 255);
    }

    internal static byte[] EncodePng(byte[] rgba, int size)
    {
        using var file = new MemoryStream();
        file.Write([0x89, (byte)'P', (byte)'N', (byte)'G', 0x0D, 0x0A, 0x1A, 0x0A]);
        var header = new byte[13];
        BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(0), size);
        BinaryPrimitives.WriteInt32BigEndian(header.AsSpan(4), size);
        header[8] = 8;                                       // 8 bits a channel
        header[9] = 6;                                       // RGBA
        Chunk(file, "IHDR", header);
        var dpi = new byte[9];                               // 96 dpi = 3780 pixels a metre, so WPF reads it at 96
        BinaryPrimitives.WriteInt32BigEndian(dpi.AsSpan(0), 3780);
        BinaryPrimitives.WriteInt32BigEndian(dpi.AsSpan(4), 3780);
        dpi[8] = 1;
        Chunk(file, "pHYs", dpi);
        using (var raw = new MemoryStream())
        {
            using (var z = new ZLibStream(raw, CompressionLevel.Optimal, leaveOpen: true))
                for (var y = 0; y < size; y++)
                {
                    z.WriteByte(0);                          // no filter
                    z.Write(rgba, y * size * 4, size * 4);
                }
            Chunk(file, "IDAT", raw.ToArray());
        }
        Chunk(file, "IEND", []);
        return file.ToArray();
    }

    private static void Chunk(Stream file, string type, byte[] data)
    {
        var head = new byte[8];
        BinaryPrimitives.WriteInt32BigEndian(head, data.Length);
        for (var i = 0; i < 4; i++)
            head[4 + i] = (byte)type[i];
        file.Write(head);
        file.Write(data);
        var crc = new byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(crc, Crc32([.. head.AsSpan(4).ToArray(), .. data]));
        file.Write(crc);
    }

    private static readonly uint[] CrcTable = [.. Enumerable.Range(0, 256).Select(n =>
    {
        var c = (uint)n;
        for (var k = 0; k < 8; k++)
            c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
        return c;
    })];

    /// <summary>PNG's CRC-32 (ISO 3309), over a chunk's type and data.</summary>
    internal static uint Crc32(ReadOnlySpan<byte> bytes)
    {
        var c = 0xFFFFFFFFu;
        foreach (var b in bytes)
            c = CrcTable[(c ^ b) & 0xFF] ^ (c >> 8);
        return c ^ 0xFFFFFFFFu;
    }
}
