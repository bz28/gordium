namespace Gordium.Revit.Reading;

/// <summary>
/// Each story's outlines for the escape routes' diagonal and areas (<c>story_outlines: [{level, outer, inner}]</c>,
/// decision 8 of docs/decisions/2026-11-20_route_measurement.md; design note section 10).
/// <list type="bullet">
/// <item><b>outer</b> is the exterior walls' outer faces by Revit's own room logic (<see cref="GrossArea"/>: a Room
/// placed in a ring of room separation lines drawn round the building, its boundary at the finished faces read, all
/// rolled back): doors and windows don't break a room's boundary, and interior walls never touch this one.</item>
/// <item><b>inner</b> is that outline with each side moved in by the thickness of the wall Revit says bounds it there
/// (<c>BoundarySegment.ElementId</c>, <c>Wall.Width</c>), the corners where the moved sides meet: exact for straight
/// walls of one thickness along each side, since a wall's inner face is its outer face moved by its thickness. Read
/// from the rooms instead it would lose what no room covers inside the walls (a shaft, a chase).</item>
/// </list>
/// Cautious: a ring Room Revit doesn't close, more than one building outline (separate buildings), a loop with a
/// curved side, a side not bounded by a wall (an area boundary line: its thickness unknown), or two walls of
/// different thickness along one straight side: no outlines are sent, with the reason; the diagonal and the story's
/// areas then need review.
/// </summary>
public static class StoryOutlines
{
    private const double Eps = InteriorReader.Sixteenth;

    /// <summary>The longest side with no bounding element read as a wall's end, ft (no wall is thicker); anything longer
    /// with no element (an area or separation line across an opening) leaves the outlines out.</summary>
    public const double WallEnd = 2.0;

    /// <summary>One story's outlines (shared plan points, anticlockwise), or why not.</summary>
    public sealed record Result(List<P2>? Outer, List<P2>? Inner, string? Why);

    /// <summary>The outlines from the level's gross area (internal points turned to shared by <paramref name="t"/>).</summary>
    public static Result Of(GrossArea? gross, Transform3 t)
    {
        if (gross is null)
            return new(null, null, "the building's outline of the level wasn't read");
        if (gross.Why is { } why)
            return new(null, null, "the building's outline: " + why);
        if (gross.Loops is not { Count: > 0 } loops)
            return new(null, null, "the building's outline has no boundary");
        if (loops.Any(l => l.Any(s => !s.IsLine)))
            return new(null, null, "the building's outline has a curved side, which isn't read exactly");
        var plans = loops.Select(l => l.Select(s => (A: P(t.Apply(s.Start)), B: P(t.Apply(s.End)), s.Element)).ToList()).ToList();
        var areas = plans.Select(l => PlanGeometry.SignedArea(l.Select(s => s.A).ToList())).ToList();
        var order = Enumerable.Range(0, plans.Count).OrderByDescending(i => Math.Abs(areas[i])).ToList();
        // the ring Room meets the building once; another loop is a second building (or a part apart)
        var others = order.Skip(1).Where(i => Math.Abs(areas[i]) > RouteReader.SmallestBeyond).ToList();
        if (others.Count > 0)
            return new(null, null, $"Revit's outline of the building is {others.Count + 1} separate pieces, not one outline");
        var sides = plans[order[0]];
        if (areas[order[0]] < 0)
            sides = Enumerable.Reverse(sides).Select(s => (A: s.B, B: s.A, s.Element)).ToList();
        // one straight side may be several segments (a wall split, two walls in line): taken together where in line
        var merged = new List<(P2 A, P2 B, string? Wall, double? Width)>();
        foreach (var (a, b, element) in sides)
        {
            if (Length(b - a) <= Eps)
                continue;
            double? width = element is not null && gross.WallWidths.TryGetValue(element, out var w) ? w
                // a short side Revit gives no element for is a wall's end showing between two walls (a step where two
                // walls in line stand a hair apart, a jamb's end at an opening: the Children's Odyssey's ring, 2026-11-21):
                // its line is kept where it is, the walls either side moved in
                : element is null && Length(b - a) <= WallEnd ? 0 : null;
            if (merged.Count > 0 && InLine(merged[^1].A, merged[^1].B, b))
            {
                var last = merged[^1];
                if (last.Width != width)
                    return new(null, null, "two walls of different thickness (or a side no wall bounds) run along one straight side " +
                                           $"at {Xy(a)}: where the inside face steps isn't read");
                merged[^1] = (last.A, b, last.Wall, last.Width);
            }
            else
                merged.Add((a, b, element, width));
        }
        if (merged.Count > 2 && InLine(merged[^1].A, merged[^1].B, merged[0].B) && merged[^1].Width == merged[0].Width)
        {
            merged[0] = (merged[^1].A, merged[0].B, merged[0].Wall, merged[0].Width);
            merged.RemoveAt(merged.Count - 1);
        }
        // a wall's end shows between two walls, never next to another end
        for (var i = 0; i < merged.Count; i++)
            if (merged[i].Width == 0 && (merged[(i + merged.Count - 1) % merged.Count].Width is not > 0 || merged[(i + 1) % merged.Count].Width is not > 0))
                return new(null, null, $"a short side at {Xy(merged[i].A)} that no element bounds isn't between two walls");
        if (merged.FindIndex(s => s.Width is null) is var open and >= 0)
            return new(null, null, $"a side of the building's outline at {Xy(merged[open].A)} isn't bounded by a wall" +
                                   (merged[open].Wall is { } by ? $" ({by})" : "") + ", so how thick the wall is there isn't known");
        var outer = merged.Select(s => s.A).ToList();
        // each side moved in (to its left: the loop is anticlockwise) by its wall's thickness; corners where they meet
        var moved = merged.Select(s =>
        {
            var u = Unit(s.B - s.A);
            var n = new P2(-u.Y * s.Width!.Value, u.X * s.Width.Value);
            return (A: s.A + n, B: s.B + n);
        }).ToList();
        var inner = new List<P2>();
        for (var i = 0; i < moved.Count; i++)
        {
            var (prev, next) = (moved[(i + moved.Count - 1) % moved.Count], moved[i]);
            if (Meet(prev.A, prev.B, next.A, next.B) is not { } corner)
                return new(null, null, $"the inside faces at {Xy(merged[i].A)} don't meet");
            inner.Add(corner);
        }
        var o = PlanGeometry.Clean(outer);
        var n2 = PlanGeometry.Clean(inner);
        if (o is null || n2 is null || !PlanGeometry.IsSimple(o) || !PlanGeometry.IsSimple(n2) || PlanGeometry.Area(n2) >= PlanGeometry.Area(o))
            return new(null, null, "the inside faces don't make a simple outline inside the outer one (a wall thicker than a side is long)");
        return new(o, n2, null);
    }

    private static P2 P(Xyz p) => new(p.X, p.Y);

    private static double Length(P2 v) => Math.Sqrt(v.X * v.X + v.Y * v.Y);

    private static P2 Unit(P2 v) => new(v.X / Length(v), v.Y / Length(v));

    private static string Xy(P2 p) => string.Create(System.Globalization.CultureInfo.InvariantCulture, $"({p.X:0.###}, {p.Y:0.###})");

    /// <summary>Whether c lies on the line through a and b, beyond b in the same direction (within 1/16 in).</summary>
    private static bool InLine(P2 a, P2 b, P2 c)
    {
        var d = b - a;
        var len = Length(d);
        return len > Eps && Math.Abs(P2.Cross(d, c - a)) / len <= Eps && (c.X - b.X) * d.X + (c.Y - b.Y) * d.Y > 0;
    }

    /// <summary>Where the lines through ab and cd meet; null when they are parallel.</summary>
    private static P2? Meet(P2 a, P2 b, P2 c, P2 d)
    {
        var r = b - a;
        var s = d - c;
        var den = P2.Cross(r, s);
        if (Math.Abs(den) < 1e-12)
            return null;
        var t = P2.Cross(c - a, s) / den;
        return new P2(a.X + r.X * t, a.Y + r.Y * t);
    }
}
