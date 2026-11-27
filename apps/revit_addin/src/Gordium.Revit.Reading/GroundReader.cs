using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>
/// The ground just outside each window (<c>openings[].ground_outside</c>; a door's isn't sent, its clear bottom not being,
/// docs/interior/interior_description_format.md), read from the Toposolids (and older topography surfaces) the
/// architect states show the finished ground (<see cref="Marks.ToposolidFinished"/>), so that the measuring works out
/// whether an escape opening's clear bottom is below grade and how deep its area well is at least
/// (model_measurement/interior/openings.py <c>ground_shows</c>; a mark set on the opening wins, and one the ground
/// contradicts needs review). The law: RCNYS R202 "GRADE. The finished ground level adjoining the building at all
/// exterior walls", so the ground is read <see cref="Adjoin"/> beyond the wall's outer face (clear of the face itself),
/// at each end of the opening (the wall opening it cuts) and at its middle, and the highest and lowest along its whole
/// width where they are neither (<see cref="Extremes"/>): shared coordinates.
///
/// Never a guess: nothing is sent unless every one of these holds, and why not is said for an escape opening.
/// <list type="bullet">
/// <item>The architect states the ground drawn is the finished one (a survey's existing ground is never read as it).</item>
/// <item>Which side of its wall is outside is known: its one room on one side only, no room or enclosed space drawn on
/// the other (as the escape routes tell a door to outside, <see cref="RouteReader.Sides"/>).</item>
/// <item>Out to <see cref="Reach"/> from the face, at each place along it, a finished ground is drawn, one ground only
/// (a subdivision over its own host is its top), nothing else stands over it anywhere outside it below the opening's
/// top (an area well drawn as a family, a step, a slab, a deck: what the finished grade is there isn't known), and the
/// ground nowhere rises more than 1/16 in above the ground at the face: a well cut into the ground, or ground sloping
/// toward the wall, leaves which ground adjoins the opening unclear (the well's floor at the face, the ground around it
/// farther out).</item>
/// </list>
/// Nothing drawn: no Toposolid or topography in the design checked, or the Revit layer not reading them, changes
/// nothing (no ground is sent, and nothing is said). A level's elevation alone is never the ground.
/// </summary>
public static class GroundReader
{
    /// <summary>How far beyond the wall's outer face the ground adjoining it is read (ft): 1 in, clear of the face.</summary>
    public const double Adjoin = 1.0 / 12;

    /// <summary>How far out from the face the ground is looked at (ft): 6 ft, GRADE PLANE's own distance beside the
    /// building (RCNYS R202), more than an area well's usual projection (at least 36 in, R319.4.1).</summary>
    public const double Reach = 6.0;

    /// <summary>How far the Revit layer widens the opening's box in plan to find what stands outside it (ft): more than
    /// <see cref="Reach"/> plus any wall's thickness.</summary>
    public const double Around = 10.0;

    /// <summary>How far under the opening's box the Revit layer looks (ft); a ground lower than that isn't read (what
    /// stands between wasn't looked at).</summary>
    public const double Below = 100.0;

    /// <summary>The distances out from the face the ground is read at (ft).</summary>
    public static IReadOnlyList<double> Out { get; } = [Adjoin, 1, 2, 3, 4, 5, Reach];

    private const double S = InteriorReader.Sixteenth;

    /// <summary>The finished grounds of the design checked, turned into shared coordinates, or why none can be read.
    /// Null when no ground is drawn in the design checked (or the Revit layer didn't read them): nothing changes.</summary>
    public sealed class Grounds
    {
        internal List<(GroundRecord Record, List<(Xyz A, Xyz B, Xyz C)> Triangles)> Each { get; } = [];
        public string? Why { get; internal set; }
    }

    public static Grounds? Of(RevitModel model)
    {
        var drawn = (model.Interior?.Grounds ?? [])
            .Where(g => SiteReader.InDesignChecked(model, g.PhaseDemolished, g.DesignOption)).ToList();
        if (drawn.Count == 0)
            return null;
        var set = new Grounds();
        if (Marks.YesNo(model.ProjectMarks.GetValueOrDefault(Marks.ToposolidFinished.Guid)) is not true)
        {
            set.Why = $"{Marks.ToposolidFinished.Name} isn't Yes on Project Information, so the ground drawn ({Named(drawn[0])}" +
                      (drawn.Count > 1 ? $" and {drawn.Count - 1} more" : "") + ") isn't read: it may be the existing ground of a survey, not the finished ground";
            return set;
        }
        var t = model.InternalToShared;
        foreach (var g in drawn)
        {
            if (g.Triangles is not { Count: > 0 } triangles)
            {
                set.Why = $"the geometry of the ground {Named(g)} couldn't be read, so no ground is read";
                return set;
            }
            set.Each.Add((g, triangles.Select(x => (t.Apply(x.A), t.Apply(x.B), t.Apply(x.C))).ToList()));
        }
        return set;
    }

    private static string Named(GroundRecord g) => $"{g.Kind} \"{g.Name ?? g.UniqueId}\"";

    /// <summary>The ground outside the opening (shared, ft): at one end, the middle and the other end, and the highest
    /// and lowest along its width where they are neither; or null with why. <paramref name="evidence"/> takes every
    /// sample read.</summary>
    internal static JsonArray? Outside(RevitModel model, Grounds set, OpeningRecord rec, string? room, string what,
                                     Dictionary<string, InteriorReader.RoomPlan> plans,
                                     List<(EnclosedArea Area, string Id, List<P2>? Outline)> unknown, JsonObject evidence,
                                     out string? why)
    {
        why = set.Why;
        if (why is not null)
            return null;
        if (room is null || !plans.TryGetValue(room, out var mine))
        {
            why = "its room's floor isn't read, so which side of its wall is outside isn't known";
            return null;
        }
        if (RouteReader.Place(model, rec, out why, what: what) is not { } p)
            return null;
        bool In(InteriorReader.RoomPlan r, P2 q) => RouteReader.StrictlyInside(q, r.Outer) && !r.Holes.Any(h => RouteReader.StrictlyInside(q, h));
        var reach = p.Thickness / 2 + Adjoin;
        P2 Probe(int s) => new(p.Centre.X + s * reach * p.Normal.X, p.Centre.Y + s * reach * p.Normal.Y);
        var sides = new[] { 1, -1 }.Where(s => In(mine, Probe(s))).ToList();
        if (sides.Count != 1)
        {
            why = "its own room isn't found on just one side of its wall, so which side is outside isn't known";
            return null;
        }
        var outward = new P2(-sides[0] * p.Normal.X, -sides[0] * p.Normal.Y);
        var t = model.InternalToShared;
        // the ends of the opening along its wall: the opening it cuts (its rough opening), else its type's width
        var uc = p.Centre.X * p.Along.X + p.Centre.Y * p.Along.Y;
        double lo, hi;
        if (rec.WallOpening is { Count: > 0 } cut)
        {
            var u = cut.Select(t.Apply).Select(q => q.X * p.Along.X + q.Y * p.Along.Y).ToList();
            (lo, hi) = (u.Min(), u.Max());
        }
        else if (rec.TypeWidth is > 0 and var w)
            (lo, hi) = (uc - w / 2, uc + w / 2);
        else
        {
            why = "neither the opening it cuts in its wall nor its type's width is read, so where its ends are isn't known";
            return null;
        }
        var top = rec.Placed!.Select(t.Apply).Max(q => q.Z);
        var level = mine.Record.LevelId;
        if (rec.Around is null)
        {
            why = "what stands outside it couldn't be looked for, so the ground there isn't read";
            return null;
        }
        // what may stand over the ground outside it: never the opening itself, its own wall or a ground; an element with
        // no box can't be placed, so it may stand anywhere
        var around = rec.Around.Where(e => e.UniqueId != rec.UniqueId && e.UniqueId != rec.Host
                                           && set.Each.All(g => g.Record.UniqueId != e.UniqueId)
                                           && !NotStanding.Contains(e.BuiltInCategory)
                                           && InteriorReader.InDesign(model, e)).ToList();
        if (around.FirstOrDefault(e => e.Box is null) is { } boxless)
        {
            why = $"{InteriorReader.Named(boxless)} near it has no box to place it by, so what stands outside it isn't known";
            return null;
        }
        var bottom = rec.Placed!.Select(t.Apply).Min(q => q.Z) - Below;
        var samples = new JsonArray();
        evidence["ground"] = new JsonObject { ["samples"] = samples };
        var faces = new List<double>();
        var lowest = double.PositiveInfinity;
        P2 At(double a, double d) => new(p.Centre.X + (a - uc) * p.Along.X + (p.Thickness / 2 + d) * outward.X,
                                         p.Centre.Y + (a - uc) * p.Along.Y + (p.Thickness / 2 + d) * outward.Y);
        foreach (var a in new[] { lo, (lo + hi) / 2, hi })
        {
            double? atFace = null;
            foreach (var d in Out)
            {
                var off = p.Thickness / 2 + d;
                var at = new P2(p.Centre.X + (a - uc) * p.Along.X + off * outward.X, p.Centre.Y + (a - uc) * p.Along.Y + off * outward.Y);
                var where = Where(d);
                if (plans.Values.FirstOrDefault(r => r.Record.LevelId == level && In(r, at)) is { } there)
                {
                    why = $"room {there.Record.UniqueId} is drawn {where}, so the ground there isn't read";
                    return null;
                }
                // an enclosed area with no Room there is a space, never outside; one on its level that couldn't be outlined
                // may be it (a sliver too small to be one excepted, as the escape routes read a door's far side)
                if (unknown.Any(x => (x.Area.LevelId == level || x.Area.LevelId is null)
                                     && (x.Outline is { } outline ? RouteReader.StrictlyInside(at, outline) : x.Area.Area >= RouteReader.SmallestBeyond)))
                {
                    why = $"an enclosed area with no Room may be {where}, so the ground there isn't read";
                    return null;
                }
                if (Ground(set, at, where, out var by, out why) is not { } z)
                    return null;
                samples.Add(new JsonObject { ["along"] = a - uc, ["out"] = d, ["z"] = z, ["ground"] = by });
                if (z < bottom)
                {
                    why = I($"the ground {where} is more than {Below:0} ft under it, below where what stands outside it was looked for");
                    return null;
                }
                lowest = Math.Min(lowest, z);
                if (atFace is not { } face)
                    atFace = z;
                else if (z > face + S)
                {
                    why = I($"the ground rises {(z - face) * 12:0.##} in from its wall's face to {d:0.##} ft out (an area well cut into the ground, or ground sloping toward the wall), so which ground adjoins it isn't clear");
                    return null;
                }
            }
            faces.Add(atFace!.Value);
        }
        // the ground adjoining it over the whole of its width, exactly (review round 1: a bump or a dip between the three
        // places could stand over its bottom, or more than 44 in from it, unseen): planar on each triangle, so along the
        // line 1 in out its highest and lowest are at the ends or where the line crosses a triangle's edge; each one
        // higher or lower than the three is sent too
        if (Extremes(set, At(lo, Adjoin), At(hi, Adjoin), Where(Adjoin), out why) is not { } along)
            return null;
        evidence["ground"]!["along_face"] = new JsonObject { ["low"] = along.Low, ["high"] = along.High };
        lowest = Math.Min(lowest, along.Low);
        // anything whose box reaches over the ground anywhere outside it, from the line 1 in out to 6 ft, over its width,
        // above the lowest ground found there and below its top (never only at the places read)
        P2[] outside = [At(lo, Adjoin), At(hi, Adjoin), At(hi, Reach), At(lo, Reach)];
        if (around.FirstOrDefault(e => Over(model, e, outside, lowest, top)) is { } over)
        {
            why = $"{InteriorReader.Named(over)} stands over the ground outside it, so what the finished grade is there isn't known";
            return null;
        }
        var sent = new List<double>(faces);
        if (along.High > faces.Max() + 1e-9)
            sent.Add(along.High);
        if (along.Low < faces.Min() - 1e-9)
            sent.Add(along.Low);
        return new JsonArray(sent.Select(z => (JsonNode?)z).ToArray());
    }

    /// <summary>What is never something standing over the ground: a Room's or an area's box, lines, levels, views
    /// (<see cref="SiteReader.NotLookedAt"/>), and room separation lines, as every reader leaves them out (review
    /// round 1: an L-shaped room's box covers the ground outside a wall).</summary>
    private static readonly IReadOnlySet<string> NotStanding =
        new HashSet<string>(SiteReader.NotLookedAt.Append("OST_RoomSeparationLines"), StringComparer.Ordinal);

    /// <summary>The lowest and highest finished ground along the plan segment <paramref name="a"/> to
    /// <paramref name="b"/>, exactly: at its ends and wherever it crosses a triangle's edge (the ground is planar
    /// between); null, with why, where any of those has no one ground (<see cref="Ground"/>).</summary>
    internal static (double Low, double High)? Extremes(Grounds set, P2 a, P2 b, string where, out string? why)
    {
        var d = b - a;
        var at = new List<double> { 0, 1 };
        foreach (var (_, triangles) in set.Each)
            foreach (var (p, q, r) in triangles)
                foreach (var (u, v) in new[] { (p, q), (q, r), (r, p) })
                    if (Crossing(a, d, u, v) is { } x)
                        at.Add(x);
        double low = double.PositiveInfinity, high = double.NegativeInfinity;
        foreach (var x in at.Distinct())
        {
            if (Ground(set, new P2(a.X + x * d.X, a.Y + x * d.Y), where, out _, out why) is not { } z)
                return null;
            (low, high) = (Math.Min(low, z), Math.Max(high, z));
        }
        why = null;
        return (low, high);
    }

    /// <summary>Where along the segment <paramref name="a"/> + x <paramref name="d"/> (x from 0 to 1) it crosses the
    /// edge <paramref name="u"/> to <paramref name="v"/> in plan, or null (apart, or parallel: a parallel edge's ends
    /// are other edges' crossings). Worked out about <paramref name="a"/>, for survey-scale coordinates.</summary>
    private static double? Crossing(P2 a, P2 d, Xyz u, Xyz v)
    {
        double wx = u.X - a.X, wy = u.Y - a.Y, ex = v.X - u.X, ey = v.Y - u.Y;
        var den = d.X * ey - d.Y * ex;
        if (Math.Abs(den) < 1e-15)
            return null;
        var x = (wx * ey - wy * ex) / den;
        var s = (wx * d.Y - wy * d.X) / den;
        const double Edge = 1e-9;
        return x < -Edge || x > 1 + Edge || s < -Edge || s > 1 + Edge ? null : Math.Clamp(x, 0, 1);
    }

    private static string Where(double d) => d <= Adjoin + 1e-9 ? "just outside it" : I($"{d:0.##} ft outside it");

    /// <summary>The finished ground's top at a plan point (shared): the highest triangle over it; null, with why, where
    /// no ground is drawn there, or two grounds are (a subdivision over its own host excepted: its top counts).</summary>
    internal static double? Ground(Grounds set, P2 at, string where, out string? by, out string? why)
    {
        by = why = null;
        var hits = new List<(GroundRecord G, double Z)>();
        foreach (var (g, triangles) in set.Each)
        {
            double? best = null;
            foreach (var (a, b, c) in triangles)
                if (Height(a, b, c, at) is { } z && (best is null || z > best))
                    best = z;
            if (best is { } found)
                hits.Add((g, found));
        }
        if (hits.Count == 0)
        {
            why = $"no finished ground is drawn {where} (past the Toposolid's edge, or cut out of it)";
            return null;
        }
        var highest = hits.MaxBy(h => h.Z);
        foreach (var (g, z) in hits.Where(h => h.G != highest.G))
        {
            if (Hosts(set, g, highest.G))
                continue;                                    // a subdivision on its host: its top is the ground
            why = $"two grounds are drawn {where} ({Named(highest.G)} at {Feet(highest.Z)}, {Named(g)} at {Feet(z)}), so which is the ground isn't known";
            return null;
        }
        by = highest.G.UniqueId;
        return highest.Z;
    }

    /// <summary>Whether <paramref name="host"/> is <paramref name="sub"/>'s host, or its host's, and so on.</summary>
    private static bool Hosts(Grounds set, GroundRecord host, GroundRecord sub)
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        for (var h = sub.Host; h is not null && seen.Add(h); h = set.Each.FirstOrDefault(x => x.Record.UniqueId == h).Record?.Host)
            if (h == host.UniqueId)
                return true;
        return false;
    }

    /// <summary>The height of the triangle over a plan point, or null where the point isn't over it (its edges
    /// included) or it stands on edge. Worked out about the point, so survey-scale coordinates keep their
    /// precision.</summary>
    internal static double? Height(Xyz a, Xyz b, Xyz c, P2 at)
    {
        double ax = a.X - at.X, ay = a.Y - at.Y, bx = b.X - at.X, by = b.Y - at.Y, cx = c.X - at.X, cy = c.Y - at.Y;
        var area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
        if (Math.Abs(area) < 1e-12)
            return null;                                     // on edge in plan: a wall of the solid, no top here
        // the point's barycentric weights: (0,0) inside the triangle, each weight 0 or more (edges included)
        var wa = (bx * cy - cx * by) / area;
        var wb = (cx * ay - ax * cy) / area;
        var wc = (ax * by - bx * ay) / area;
        const double Edge = -1e-9;
        if (wa < Edge || wb < Edge || wc < Edge)
            return null;
        return wa * a.Z + wb * b.Z + wc * c.Z;
    }

    /// <summary>Whether the element's box (shared, around all 8 corners: only ever bigger) meets the plan rectangle
    /// <paramref name="outside"/> (four corners in order) and reaches above <paramref name="ground"/> (the lowest
    /// ground found there), below the opening's top: something that may stand over the ground outside it.</summary>
    private static bool Over(RevitModel model, NearbyElement e, P2[] outside, double ground, double top)
    {
        var b = e.Box!;
        var box = Box3.Turned(b.Min, b.Max, model.InternalToShared.After(b.Transform ?? Transform3.Identity));
        if (box.Max.Z <= ground + S || box.Min.Z >= top)
            return false;
        // the two shapes meet unless one of the four directions (the plan's two, the rectangle's two) sets them apart;
        // worked out about the rectangle's first corner, for survey-scale coordinates
        var o = outside[0];
        P2[] square = [new(box.Min.X - o.X, box.Min.Y - o.Y), new(box.Max.X - o.X, box.Min.Y - o.Y),
                       new(box.Max.X - o.X, box.Max.Y - o.Y), new(box.Min.X - o.X, box.Max.Y - o.Y)];
        var rect = outside.Select(c => c - o).ToArray();
        foreach (var axis in new[] { new P2(1, 0), new P2(0, 1), rect[1] - rect[0], rect[3] - rect[0] })
        {
            var size = Math.Sqrt(axis.X * axis.X + axis.Y * axis.Y);
            if (size < 1e-12)
                continue;
            double Along(P2 c) => (c.X * axis.X + c.Y * axis.Y) / size;
            if (square.Max(Along) + S < rect.Min(Along) || rect.Max(Along) + S < square.Min(Along))
                return false;
        }
        return true;
    }

    private static string Feet(double z) => I($"{z:0.###} ft");

    private static string I(FormattableString s) => s.ToString(CultureInfo.InvariantCulture);
}
