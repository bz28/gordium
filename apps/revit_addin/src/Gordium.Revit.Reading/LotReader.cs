using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>The lot (design note, section 4): the picked lot (<c>lot_id</c> in the facts: one property line, or
/// several lines' <c>UniqueId</c>s joined by "+", in the order picked), else the one closed property line. Only a
/// closed outline is ever a lot: lines whose ends don't meet in one loop would have the checker close them with an
/// edge nobody drew. A lot line with a curve that has no ends makes the lot unread (<see cref="UnboundPicked"/>,
/// <see cref="UnboundPropertyLine"/>).</summary>
internal static class LotReader
{
    /// <summary>The most a curved lot line's points are apart (ft): <c>read_3dm.ARC_STEP</c>, the conformance
    /// suite's reading of "points closely along it".</summary>
    public const double ArcStep = 0.25;

    /// <summary>The fewest pieces a curved lot line is cut into (as <c>read_3dm._edges</c>).</summary>
    public const int MinArcPieces = 16;

    /// <summary>The layer named in the lot's problems: Revit's category for property lines.</summary>
    public const string LotLayer = "Property Lines";

    internal sealed record Lot(JsonObject Json, List<(double X, double Y)> Ring);

    /// <summary>Why the lot isn't read when a lot line holds a curve with no ends (<see cref="LotLineElement.Unbound"/>:
    /// a full circle or ellipse drawn as one curve). It can't be read as lot lines, and it is never left out: a property
    /// line without one of its curves could close into a lot that isn't the drawn one, or leave another property line
    /// read as "the one".</summary>
    public const string UnboundPicked =
        "a lot line picked has a curve with no ends (a full circle or ellipse drawn as one curve), which Gordium can't " +
        "read as lot lines: redraw it as arcs and pick the lot again";

    /// <summary>The same, with nothing picked: such a property line may be the lot, so no other is taken as the one.</summary>
    public const string UnboundPropertyLine =
        "a property line has a curve with no ends (a full circle or ellipse drawn as one curve), which Gordium can't " +
        "read as lot lines, so which property line is the lot can't be told: redraw it as arcs, or pick the lot";

    public static Lot? Read(RevitModel model, string? lotId, Transform3 toShared, List<JsonObject> problems)
    {
        var tol = model.VertexTolerance;
        if (!string.IsNullOrEmpty(lotId))
        {
            var lines = lotId.Split('+').Select(id => model.LotLines.FirstOrDefault(l => l.UniqueId == id)).ToList();
            if (lines.Any(l => l is { Unbound: > 0 }))
            {
                problems.Add(SiteReader.Problem("tool_words", ("words", UnboundPicked)));
                return null;
            }
            var loop = lines.Any(l => l is null) ? null : Loop(lines.SelectMany(l => l!.Curves).ToList(), tol);
            if (loop is null)
            {
                problems.Add(SiteReader.Problem("lot_not_found"));
                return null;
            }
            return Make(lotId, loop, toShared);
        }
        if (model.LotLines.Any(l => l.IsPropertyLine && l.Unbound > 0))
        {
            problems.Add(SiteReader.Problem("tool_words", ("words", UnboundPropertyLine)));
            return null;
        }
        var closed = model.LotLines.Where(l => l.IsPropertyLine)
                                   .Select(l => (Line: l, Loop: Loop(l.Curves.ToList(), tol)))
                                   .Where(x => x.Loop is not null).ToList();
        if (closed.Count == 1)
            return Make(closed[0].Line.UniqueId, closed[0].Loop!, toShared);
        problems.Add(closed.Count == 0
            ? SiteReader.Problem("no_lot_outline", ("layer", LotLayer))
            : SiteReader.Problem("several_lot_outlines", ("count", closed.Count.ToString(System.Globalization.CultureInfo.InvariantCulture)), ("layer", LotLayer)));
        return null;
    }

    /// <summary>The curves as one closed loop, each in the way it runs round (reversed: true when it runs end to
    /// start), or null when they don't all join, end to start within <paramref name="tol"/>, into one loop.</summary>
    internal static List<(LotCurve Curve, bool Reversed)>? Loop(List<LotCurve> curves, double tol)
    {
        if (curves.Count == 0)
            return null;
        var left = new List<LotCurve>(curves);
        var loop = new List<(LotCurve, bool)> { (left[0], false) };
        var start = left[0].Start;
        var end = left[0].End;
        left.RemoveAt(0);
        while (left.Count > 0)
        {
            if (end.DistanceTo(start) <= tol)
                return null;                                     // closed before every curve was used: not one loop
            var k = left.FindIndex(c => c.Start.DistanceTo(end) <= tol);
            var reversed = false;
            if (k < 0)
            {
                k = left.FindIndex(c => c.End.DistanceTo(end) <= tol);
                reversed = true;
            }
            if (k < 0)
                return null;                                     // a gap: not a closed outline
            var c = left[k];
            left.RemoveAt(k);
            loop.Add((c, reversed));
            end = reversed ? c.Start : c.End;
        }
        return end.DistanceTo(start) <= tol ? loop : null;
    }

    private static Lot Make(string id, List<(LotCurve Curve, bool Reversed)> loop, Transform3 t)
    {
        var edges = new JsonArray();
        var ring = new List<(double, double)>();
        foreach (var (c, reversed) in loop)
        {
            var pts = Points(c);
            if (reversed)
                pts.Reverse();
            var plan = pts.Select(p => t.Apply(p)).Select(p => (p.X, p.Y)).ToList();
            if (c.IsLine && plan[0] == plan[1])
                continue;                                        // a line of no length is no lot line
            edges.Add(new JsonObject
            {
                ["points"] = new JsonArray(plan.Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray()),
                ["curved"] = !c.IsLine,
            });
            foreach (var p in plan)
                if (ring.Count == 0 || ring[^1] != p)
                    ring.Add(p);
        }
        if (ring.Count > 1 && ring[0] == ring[^1])
            ring.RemoveAt(ring.Count - 1);
        return new Lot(new JsonObject { ["id"] = id, ["edges"] = edges }, ring);
    }

    /// <summary>A straight line is its two ends; any other curve is points along it at even steps of its parameter,
    /// at least <see cref="MinArcPieces"/> pieces and no more than <see cref="ArcStep"/> of its length each, its ends
    /// exactly its own (never its chord).</summary>
    internal static List<Xyz> Points(LotCurve c)
    {
        if (!c.Start.IsFinite || !c.End.IsFinite)
            throw new ArgumentException("a lot line has an end that isn't a number");
        if (c.IsLine)
            return [c.Start, c.End];
        if (c.PointAt is null || !double.IsFinite(c.Length) || c.Length <= 0)
            throw new ArgumentException("a curved lot line needs its length and a point at each parameter (Curve.Evaluate)");
        var n = Math.Max(MinArcPieces, (int)Math.Ceiling(c.Length / ArcStep));
        var pts = new List<Xyz>(n + 1) { c.Start };
        for (var k = 1; k < n; k++)
        {
            var p = c.PointAt((double)k / n);
            if (!p.IsFinite)
                throw new ArgumentException("a curved lot line gave a point that isn't a number");
            pts.Add(p);
        }
        pts.Add(c.End);
        return pts;
    }
}
