namespace Gordium.Revit.Reading;

/// <summary>A plan point, in feet.</summary>
public readonly record struct P2(double X, double Y)
{
    public static P2 operator -(P2 a, P2 b) => new(a.X - b.X, a.Y - b.Y);
    public static P2 operator +(P2 a, P2 b) => new(a.X + b.X, a.Y + b.Y);

    public static double Cross(P2 a, P2 b) => a.X * b.Y - a.Y * b.X;
}

/// <summary>Exact plan geometry for the interior reader: polygon areas, and the overlap of two simple polygons as convex
/// pieces (each cut into triangles, every pair of triangles clipped: exact for any simple polygon, convex or not). Used
/// to tell what lies over or under a room's floor and to clip it to the room (design note, section 4). Callers move
/// their points near the origin first (<see cref="Local"/>): survey coordinates 875,000 ft out would cost the
/// products their precision.</summary>
public static class PlanGeometry
{
    /// <summary>The polygon's area, positive when its points run anticlockwise.</summary>
    public static double SignedArea(IReadOnlyList<P2> p)
    {
        double a = 0;
        for (var i = 0; i < p.Count; i++)
            a += P2.Cross(p[i], p[(i + 1) % p.Count]);
        return a / 2;
    }

    public static double Area(IReadOnlyList<P2> p) => Math.Abs(SignedArea(p));

    /// <summary>The points moved so that <paramref name="origin"/> is at 0, 0.</summary>
    public static List<P2> Local(IEnumerable<P2> p, P2 origin) => p.Select(q => q - origin).ToList();

    private static double Scale(IReadOnlyList<P2> p) =>
        Math.Max(1.0, p.Max(q => Math.Max(Math.Abs(q.X), Math.Abs(q.Y))));

    /// <summary>The polygon anticlockwise, with points repeated or standing on a straight run between their
    /// neighbours taken out; null when fewer than 3 are left (no area).</summary>
    public static List<P2>? Clean(IReadOnlyList<P2> polygon)
    {
        if (polygon.Count < 3)
            return null;
        var s = Scale(polygon);
        var tol = 1e-12 * s * s;
        var p = polygon.ToList();
        var changed = true;
        while (changed && p.Count >= 3)
        {
            changed = false;
            for (var i = 0; i < p.Count && p.Count >= 3; i++)
            {
                var a = p[(i + p.Count - 1) % p.Count];
                var b = p[i];
                var c = p[(i + 1) % p.Count];
                if (Math.Abs(P2.Cross(b - a, c - b)) <= tol || (b - a) is { X: 0, Y: 0 })
                {
                    p.RemoveAt(i);
                    changed = true;
                    i--;
                }
            }
        }
        if (p.Count < 3 || Math.Abs(SignedArea(p)) <= tol)
            return null;
        if (SignedArea(p) < 0)
            p.Reverse();
        return p;
    }

    /// <summary>Whether no two edges that aren't neighbours touch or cross (a simple polygon).</summary>
    public static bool IsSimple(IReadOnlyList<P2> p)
    {
        var n = p.Count;
        if (n < 3)
            return false;
        for (var i = 0; i < n; i++)
            for (var j = i + 1; j < n; j++)
            {
                if (j == i + 1 || (i == 0 && j == n - 1))
                    continue;
                if (SegmentsMeet(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n]))
                    return false;
            }
        return true;
    }

    private static int Side(P2 a, P2 b, P2 c, double tol)
    {
        var x = P2.Cross(b - a, c - a);
        return x > tol ? 1 : x < -tol ? -1 : 0;
    }

    private static bool SegmentsMeet(P2 a, P2 b, P2 c, P2 d)
    {
        var s = Math.Max(1.0, new[] { a, b, c, d }.Max(q => Math.Max(Math.Abs(q.X), Math.Abs(q.Y))));
        var tol = 1e-12 * s * s;
        int d1 = Side(c, d, a, tol), d2 = Side(c, d, b, tol), d3 = Side(a, b, c, tol), d4 = Side(a, b, d, tol);
        if (d1 * d2 < 0 && d3 * d4 < 0)
            return true;
        bool On(P2 p, P2 q, P2 r) =>        // r on segment pq, given collinear
            Math.Min(p.X, q.X) - 1e-12 * s <= r.X && r.X <= Math.Max(p.X, q.X) + 1e-12 * s
            && Math.Min(p.Y, q.Y) - 1e-12 * s <= r.Y && r.Y <= Math.Max(p.Y, q.Y) + 1e-12 * s;
        return (d1 == 0 && On(c, d, a)) || (d2 == 0 && On(c, d, b)) || (d3 == 0 && On(a, b, c)) || (d4 == 0 && On(a, b, d));
    }

    /// <summary>The polygon cut into triangles (ear clipping), each anticlockwise; null when it isn't a simple polygon
    /// with an area.</summary>
    public static List<P2[]>? Triangulate(IReadOnlyList<P2> polygon)
    {
        var p = Clean(polygon);
        if (p is null || !IsSimple(p))
            return null;
        var s = Scale(p);
        var tol = 1e-12 * s * s;
        var tris = new List<P2[]>();
        var guard = 0;
        while (p.Count > 3)
        {
            if (guard++ > 10_000)
                return null;
            var cut = false;
            for (var i = 0; i < p.Count; i++)
            {
                var a = p[(i + p.Count - 1) % p.Count];
                var b = p[i];
                var c = p[(i + 1) % p.Count];
                if (P2.Cross(b - a, c - b) <= tol)
                    continue;                                       // not convex here
                var ear = true;
                foreach (var q in p)
                {
                    if (q == a || q == b || q == c)
                        continue;
                    if (Side(a, b, q, tol) >= 0 && Side(b, c, q, tol) >= 0 && Side(c, a, q, tol) >= 0)
                    {
                        ear = false;
                        break;
                    }
                }
                if (!ear)
                    continue;
                tris.Add([a, b, c]);
                p.RemoveAt(i);
                cut = true;
                break;
            }
            if (!cut)
                return null;
        }
        tris.Add([p[0], p[1], p[2]]);
        return tris;
    }

    /// <summary>A convex polygon clipped by a convex one (both anticlockwise), Sutherland–Hodgman.</summary>
    public static List<P2> ClipConvex(IReadOnlyList<P2> subject, IReadOnlyList<P2> clip)
    {
        var output = subject.ToList();
        for (var i = 0; i < clip.Count && output.Count > 0; i++)
        {
            var a = clip[i];
            var b = clip[(i + 1) % clip.Count];
            var input = output;
            output = [];
            for (var j = 0; j < input.Count; j++)
            {
                var p = input[j];
                var q = input[(j + 1) % input.Count];
                var dp = P2.Cross(b - a, p - a);
                var dq = P2.Cross(b - a, q - a);
                if (dp >= 0)
                    output.Add(p);
                if ((dp >= 0) != (dq >= 0))
                {
                    var t = dp / (dp - dq);
                    output.Add(new P2(p.X + t * (q.X - p.X), p.Y + t * (q.Y - p.Y)));
                }
            }
        }
        return output;
    }

    /// <summary>Where two simple polygons overlap, as convex pieces with an area (anticlockwise); null when either
    /// isn't a simple polygon with an area.</summary>
    public static List<List<P2>>? Overlap(IReadOnlyList<P2> a, IReadOnlyList<P2> b)
    {
        var ta = Triangulate(a);
        var tb = Triangulate(b);
        if (ta is null || tb is null)
            return null;
        var s = Math.Max(Scale(a), Scale(b));
        var tiny = 1e-10 * s * s;
        var pieces = new List<List<P2>>();
        foreach (var x in ta)
            foreach (var y in tb)
            {
                var piece = ClipConvex(x, y);
                if (piece.Count >= 3 && SignedArea(piece) > tiny)
                    pieces.Add(piece);
            }
        return pieces;
    }

    /// <summary>The area two simple polygons share; null when either isn't one.</summary>
    public static double? OverlapArea(IReadOnlyList<P2> a, IReadOnlyList<P2> b) =>
        Overlap(a, b) is { } pieces ? pieces.Sum(Area) : null;
}
