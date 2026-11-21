namespace Gordium.Revit.Reading;

/// <summary>
/// Each story's outlines for the escape routes' diagonal and areas (<c>story_outlines: [{level, outer, inner}]</c>,
/// decision 8 of docs/decisions/2026-11-20_route_measurement.md; design note section 10): <b>outer</b>, the outside
/// faces of the story's exterior walls, and <b>inner</b>, their inside faces. Read from what is drawn on the level, not
/// from the floor slab's edge (a slab may stop at the walls' core, their inside face or past them, and a firm's wall
/// type "Function" is a setting, not a fact):
/// <list type="bullet">
/// <item><b>outer</b> is the outside boundary of everything on the story put together: every room's floor, every
/// enclosed area with no Room that was outlined, and every wall's plan footprint (its faces that aren't vertical,
/// projected: a door cutting its bottom face is bridged by its top face).</item>
/// <item>The <b>exterior walls</b> are the walls with a piece of that outside boundary on their footprint; <b>inner</b>
/// is the outside boundary of the rooms, the outlined areas and every other wall put together: the exterior walls'
/// inside faces.</item>
/// </list>
/// Cautious: a story whose pieces don't close into one outline (two separate buildings), whose outline holds a hole
/// bigger than a sliver (a courtyard, or a space no Room or outline accounts for: its area can't be told), or whose
/// walls' geometry couldn't be read, has no outlines sent, with the reason; the diagonal and the story's areas then
/// need review. Never a guess.
/// </summary>
public static class StoryOutlines
{
    /// <summary>How far to each side of a boundary piece it is tried, ft: 1/16 in, the drawing-noise allowance (walls drawn
    /// face to face a hair apart are one solid).</summary>
    private const double Eps = InteriorReader.Sixteenth;

    /// <summary>A hole in a story's outline smaller than this, sq ft, is a sliver (the same bar as a door's far side:
    /// <see cref="RouteReader.SmallestBeyond"/>).</summary>
    private const double Sliver = RouteReader.SmallestBeyond;

    /// <summary>One story's outlines (shared plan points, anticlockwise), or why not.</summary>
    public sealed record Result(List<P2>? Outer, List<P2>? Inner, string? Why)
    {
        /// <summary>Where the boundary's pieces end without meeting another (shared plan points), when they don't close.</summary>
        public IReadOnlyList<P2> OpenEnds { get; init; } = [];
    }

    /// <param name="rooms">Each room's floor outline on the story (shared plan points).</param>
    /// <param name="spaces">Each enclosed area with no Room on it that was outlined.</param>
    /// <param name="walls">Each wall on the story, by id, its footprint as polygons (its non-vertical faces, projected).</param>
    public static Result Of(IReadOnlyList<List<P2>> rooms, IReadOnlyList<List<P2>> spaces, IReadOnlyDictionary<string, List<List<P2>>> walls)
    {
        if (rooms.Count == 0)
            return new(null, null, "no room's floor is read on it");
        var origin = rooms[0][0];
        List<P2> L(List<P2> p) => PlanGeometry.Local(p, origin);
        var spaceRooms = rooms.Concat(spaces).Select(L).ToList();
        var wallPolys = walls.ToDictionary(w => w.Key, w => w.Value.Select(L).ToList());
        var all = spaceRooms.Select(p => (Poly: p, Wall: (string?)null))
            .Concat(wallPolys.SelectMany(w => w.Value.Select(p => (Poly: p, Wall: (string?)w.Key)))).ToList();
        var outer = Boundary(all, out var exterior, out var why, out var open);
        var back = new P2(-origin.X, -origin.Y);
        if (outer is null)
            return new(null, null, "its outer outline: " + why) { OpenEnds = PlanGeometry.Local(open, back) };
        // the other walls, less what of them is inside an exterior wall (an end carried into it at a join): only the
        // parts inside the exterior walls' inner faces count
        var cut = wallPolys.Where(w => exterior.Contains(w.Key)).SelectMany(w => w.Value).Where(p => PlanGeometry.Clean(p) is { } c && PlanGeometry.IsConvex(c)).ToList();
        var inside = spaceRooms.Select(p => (Poly: p, Wall: (string?)null)).ToList();
        foreach (var w in wallPolys.Where(w => !exterior.Contains(w.Key)))
            foreach (var p in w.Value)
            {
                List<List<P2>>? pieces = PlanGeometry.Clean(p) is { } c && PlanGeometry.IsConvex(c) ? [c] : null;
                foreach (var e in cut)
                    pieces = pieces is null ? null : PlanGeometry.Subtract(pieces, e);
                if (pieces is null)
                    return new(null, null, "its inner outline: a wall's footprint isn't a simple outline");
                inside.AddRange(pieces.Where(q => PlanGeometry.Area(q) > 1e-9).Select(q => (Poly: q, Wall: (string?)w.Key)));
            }
        var inner = Boundary(inside, out _, out why, out open);
        if (inner is null)
            return new(null, null, "its inner outline: " + why) { OpenEnds = PlanGeometry.Local(open, back) };
        if (PlanGeometry.Area(inner) >= PlanGeometry.Area(outer) || PlanGeometry.OverlapArea(outer, inner) is not { } shared
            || shared < PlanGeometry.Area(inner) * (1 - 1e-9))
            return new(null, null, "its inner outline isn't inside its outer one");
        return new(PlanGeometry.Local(outer, back), PlanGeometry.Local(inner, back), null);
    }

    /// <summary>The outside boundary of the polygons put together, anticlockwise; null with why when it isn't one loop
    /// with no hole bigger than a sliver. <paramref name="touching"/>: the walls with a piece of it on their footprint.</summary>
    internal static List<P2>? Boundary(List<(List<P2> Poly, string? Wall)> polys, out HashSet<string> touching, out string? why,
                                       out List<P2> openEnds)
    {
        touching = new HashSet<string>(StringComparer.Ordinal);
        why = null;
        openEnds = [];
        var cleaned = new List<(List<P2> Poly, string? Wall)>();
        foreach (var (poly, wall) in polys)
            if (PlanGeometry.Clean(poly) is { } c && PlanGeometry.IsSimple(c))
                cleaned.Add((c, wall));
            else if (PlanGeometry.Area(poly) > Sliver)
            {
                why = "a piece of it isn't a simple outline";
                return null;
            }
        var edges = cleaned.SelectMany((p, i) => p.Poly.Select((a, k) => (A: a, B: p.Poly[(k + 1) % p.Poly.Count], Of: i))).ToList();
        var pieces = new List<(P2 A, P2 B, int Of)>();
        foreach (var e in edges)
        {
            var d = e.B - e.A;
            var len = Math.Sqrt(d.X * d.X + d.Y * d.Y);
            if (len <= Eps)
                continue;
            var cuts = new List<double> { 0, 1 };
            foreach (var f in edges)
            {
                if (f.Of == e.Of)
                    continue;                                // its own polygon's edges meet it only at its ends
                foreach (var p in new[] { f.A, f.B })
                    if (Distance(p, e.A, e.B, out var t) <= Eps && t > 0 && t < 1)
                        cuts.Add(t);
                if (Crossing(e.A, e.B, f.A, f.B) is { } u)
                    cuts.Add(u);
            }
            cuts.Sort();
            for (var k = 0; k + 1 < cuts.Count; k++)
            {
                if ((cuts[k + 1] - cuts[k]) * len <= Eps)
                    continue;
                P2 p = At(e.A, d, cuts[k]), q = At(e.A, d, cuts[k + 1]), m = At(e.A, d, (cuts[k] + cuts[k + 1]) / 2);
                var n = new P2(-d.Y / len * Eps * 2, d.X / len * Eps * 2);
                bool In(P2 x) => cleaned.Any(c => Inside(x, c.Poly));
                bool left = In(m + n), right = In(m - n);
                if (left == right)
                    continue;
                pieces.Add(left ? (p, q, e.Of) : (q, p, e.Of));
            }
        }
        foreach (var piece in pieces)
            if (cleaned[piece.Of].Wall is { } w)
                touching.Add(w);
        // pieces of two polygons along one line are one piece: kept once
        var unique = new List<(P2 A, P2 B)>();
        foreach (var (a, b, _) in pieces)
            if (!unique.Any(u => Close(u.A, a) && Close(u.B, b)))
                unique.Add((a, b));
        var loops = Chain(unique);
        if (loops is null)
        {
            // where pieces end with no piece starting there (and start with none ending there): to be found in the model
            openEnds = unique.Where(p => !unique.Any(q => Close(q.A, p.B))).Select(p => p.B)
                .Concat(unique.Where(p => !unique.Any(q => Close(q.B, p.A))).Select(p => p.A)).ToList();
            why = "its pieces don't join into closed loops";
            return null;
        }
        var areas = loops.Select(PlanGeometry.SignedArea).ToList();
        var outers = Enumerable.Range(0, loops.Count).Where(i => areas[i] > Sliver).ToList();
        var holes = Enumerable.Range(0, loops.Count).Where(i => areas[i] < -Sliver).ToList();
        if (outers.Count != 1)
        {
            why = outers.Count == 0 ? "nothing closes it" : $"it is {outers.Count} separate pieces, not one outline";
            return null;
        }
        if (holes.Count > 0)
        {
            why = $"it holds {holes.Count} hole{(holes.Count == 1 ? "" : "s")} no room or wall accounts for (the largest " +
                  $"{-areas[holes.OrderBy(i => areas[i]).First()]:0.##} sq ft: a courtyard, or a space whose area can't be told)";
            return null;
        }
        return PlanGeometry.Clean(loops[outers[0]]);
    }

    private static List<List<P2>>? Chain(List<(P2 A, P2 B)> pieces)
    {
        var left = new List<(P2 A, P2 B)>(pieces);
        var loops = new List<List<P2>>();
        while (left.Count > 0)
        {
            var loop = new List<P2> { left[0].A };
            var at = left[0].B;
            left.RemoveAt(0);
            for (var guard = 0; !Close(at, loop[0]); guard++)
            {
                var next = left.FindIndex(p => Close(p.A, at));
                if (next < 0 || guard > pieces.Count)
                    return null;
                loop.Add(at);
                at = left[next].B;
                left.RemoveAt(next);
            }
            loops.Add(loop);
        }
        return loops;
    }

    private static bool Close(P2 a, P2 b) => Math.Abs(a.X - b.X) <= Eps && Math.Abs(a.Y - b.Y) <= Eps;

    private static P2 At(P2 a, P2 d, double t) => new(a.X + d.X * t, a.Y + d.Y * t);

    private static double Distance(P2 p, P2 a, P2 b, out double t)
    {
        var d = b - a;
        var len2 = d.X * d.X + d.Y * d.Y;
        t = len2 > 0 ? ((p.X - a.X) * d.X + (p.Y - a.Y) * d.Y) / len2 : 0;
        var c = new P2(a.X + d.X * Math.Clamp(t, 0, 1), a.Y + d.Y * Math.Clamp(t, 0, 1));
        return Math.Sqrt((p.X - c.X) * (p.X - c.X) + (p.Y - c.Y) * (p.Y - c.Y));
    }

    /// <summary>Where segment ab properly crosses cd, as a fraction along ab; null when it doesn't.</summary>
    private static double? Crossing(P2 a, P2 b, P2 c, P2 d)
    {
        var r = b - a;
        var s = d - c;
        var den = P2.Cross(r, s);
        if (Math.Abs(den) < 1e-12)
            return null;
        var t = P2.Cross(c - a, s) / den;
        var u = P2.Cross(c - a, r) / den;
        return t > 1e-9 && t < 1 - 1e-9 && u > 1e-9 && u < 1 - 1e-9 ? t : null;
    }

    private static bool Inside(P2 p, List<P2> poly)
    {
        var inside = false;
        for (var i = 0; i < poly.Count; i++)
        {
            P2 a = poly[i], b = poly[(i + 1) % poly.Count];
            if ((a.Y > p.Y) != (b.Y > p.Y) && p.X < a.X + (p.Y - a.Y) * (b.X - a.X) / (b.Y - a.Y))
                inside = !inside;
        }
        return inside;
    }
}
