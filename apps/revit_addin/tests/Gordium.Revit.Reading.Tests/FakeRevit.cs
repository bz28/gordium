using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Fake Revit records, built the way the Revit layer would fill them from a real model: every point in
/// Revit's internal coordinates (<see cref="Place"/> turns the shared coordinates a scene is written in into them),
/// a solid as faces (each with its loops and grid of points) and edges, Revit's own box axis-aligned in internal
/// coordinates.</summary>
internal sealed class FakeRevit(Transform3 internalToShared)
{
    public Transform3 InternalToShared { get; } = internalToShared;

    private readonly Transform3 _toInternal = Inverse(internalToShared);

    /// <summary>A point given in shared coordinates, where Revit holds it (internal).</summary>
    public Xyz Place(double x, double y, double z) => _toInternal.Apply(new Xyz(x, y, z));

    public static Transform3 Inverse(Transform3 t)
    {
        // rigid: the inverse turn is the transpose, then the origin moved back
        Xyz x = t.BasisX, y = t.BasisY, z = t.BasisZ;
        var bx = new Xyz(x.X, y.X, z.X);
        var by = new Xyz(x.Y, y.Y, z.Y);
        var bz = new Xyz(x.Z, y.Z, z.Z);
        var o = t.Origin;
        var back = -1 * (o.X * bx + o.Y * by + o.Z * bz);
        return new Transform3(back, bx, by, bz);
    }

    /// <summary>A prism over a plan outline (shared coordinates), from <paramref name="z0"/> to <paramref name="z1"/>:
    /// floor, roof and one wall per outline edge. <paramref name="curvedEdge"/> bows that edge into an arc through
    /// <paramref name="through"/> (its wall a CylindricalFace, the floor and roof each with an arc edge);
    /// <paramref name="open"/> leaves out the floor and roof (their edges then have one face each).</summary>
    public SolidItem Prism(IReadOnlyList<(double X, double Y)> outline, double z0, double z1, int? curvedEdge = null,
                           (double X, double Y)? through = null, bool open = false)
    {
        var n = outline.Count;
        var faces = new List<FaceRecord>();
        var edges = new List<EdgeRecord>();
        List<(double X, double Y)> Along(int i) => i == curvedEdge
            ? ArcPoints(outline[i], through!.Value, outline[(i + 1) % n], 8)
            : [outline[i], outline[(i + 1) % n]];
        LoopCurve Curve(int i, double z) => new(Place(outline[i].X, outline[i].Y, z), i != curvedEdge);
        if (z1 > z0 || open)
        {
            for (var i = 0; i < n; i++)
            {
                var along = Along(i);
                var samples = new List<Xyz>();
                foreach (var (x, y) in Spread(along, 7))
                    for (var k = 0; k < 7; k++)
                        samples.Add(Place(x, y, z0 + (z1 - z0) * k / 6));
                var a = outline[i];
                var b = outline[(i + 1) % n];
                var loop = new List<LoopCurve>
                {
                    new(Place(a.X, a.Y, z0), i != curvedEdge), new(Place(b.X, b.Y, z0), true),
                    new(Place(b.X, b.Y, z1), i != curvedEdge), new(Place(a.X, a.Y, z1), true),
                };
                faces.Add(new FaceRecord(i == curvedEdge ? "CylindricalFace" : "PlanarFace", [loop], samples));
                edges.Add(new EdgeRecord([Place(a.X, a.Y, z0), Place(a.X, a.Y, z1)], true));
            }
        }
        foreach (var z in new[] { z0, z1 })
            for (var i = 0; i < n; i++)
                edges.Add(new EdgeRecord(Along(i).Select(p => Place(p.X, p.Y, z)).ToList(), !open && z1 > z0));
        if (!open)
            foreach (var z in z1 > z0 ? new[] { z0, z1 } : [z0])
                faces.Add(new FaceRecord("PlanarFace", [Enumerable.Range(0, n).Select(i => Curve(i, z)).ToList()], []));
        return new SolidItem(faces, edges);
    }

    /// <summary>A prism over a plan outline as a closed mesh (<c>Mesh.IsClosed</c> true): its floor, roof and walls,
    /// in conformance._ring_faces's order, each a fan of triangles from its first corner, as conformance.mesh_faces
    /// splits them (the way scene 18's roof is drawn).</summary>
    public MeshItem ClosedMesh(IReadOnlyList<(double X, double Y)> outline, double z0, double z1)
    {
        var n = outline.Count;
        var faces = new List<List<Xyz>>
        {
            outline.Select(p => Place(p.X, p.Y, z0)).ToList(),
            outline.Select(p => Place(p.X, p.Y, z1)).ToList(),
        };
        for (var i = 0; i < n; i++)
        {
            var (a, b) = (outline[i], outline[(i + 1) % n]);
            faces.Add([Place(a.X, a.Y, z0), Place(b.X, b.Y, z0), Place(b.X, b.Y, z1), Place(a.X, a.Y, z1)]);
        }
        var v = new List<Xyz>();
        var t = new List<(int, int, int)>();
        foreach (var f in faces)
        {
            var at = v.Count;
            v.AddRange(f);
            for (var k = 1; k < f.Count - 1; k++)
                t.Add((at, at + k, at + k + 1));
        }
        return new MeshItem(v, t, true);
    }

    /// <summary>A flat open mesh over a plan box at height z, cells × cells squares (two triangles each).</summary>
    public MeshItem Grid((double X, double Y) lo, (double X, double Y) hi, double z, int cells)
    {
        var v = new List<Xyz>();
        for (var j = 0; j <= cells; j++)
            for (var i = 0; i <= cells; i++)
                v.Add(Place(lo.X + (hi.X - lo.X) * i / cells, lo.Y + (hi.Y - lo.Y) * j / cells, z));
        var t = new List<(int, int, int)>();
        for (var j = 0; j < cells; j++)
            for (var i = 0; i < cells; i++)
            {
                var a = j * (cells + 1) + i;
                t.Add((a, a + 1, a + cells + 2));
                t.Add((a, a + cells + 2, a + cells + 1));
            }
        return new MeshItem(v, t, null);
    }

    /// <summary>Revit's own box of geometry: axis-aligned in internal coordinates, as <c>get_BoundingBox</c> gives it.
    /// Null when the geometry has no point (an empty solid), as Revit gives no box for it.</summary>
    public static RevitBox? BoxOf(IEnumerable<GeometryItem> items)
    {
        var b = new BoxBuilder();
        foreach (var p in AllPoints(items))
            b.Add(p);
        return b.Box is { } x ? new RevitBox(x.Min, x.Max) : null;
    }

    private static IEnumerable<Xyz> AllPoints(IEnumerable<GeometryItem> items)
    {
        foreach (var item in items)
            switch (item)
            {
                case SolidItem s:
                    foreach (var e in s.Edges)
                        foreach (var p in e.Along)
                            yield return p;
                    break;
                case MeshItem m:
                    foreach (var p in m.Vertices)
                        yield return p;
                    break;
                case InstanceItem { Items: { } inner }:
                    foreach (var p in AllPoints(inner))
                        yield return p;
                    break;
            }
    }

    /// <summary>A lot line along a plan polyline (shared coordinates), closed, each piece a Line, but the pieces
    /// <paramref name="arcs"/> names (edge index: the arc's start, end, centre and radius, as conformance.lot_arcs).
    /// <paramref name="open"/>: finished open, every piece but the last (as conformance.open_lots), so its ends don't
    /// meet: Revit lets a property line be finished so (design note, section 4).</summary>
    public LotLineElement PropertyLine(string id, IReadOnlyList<(double X, double Y)> ring,
                                      IReadOnlyDictionary<int, JsonObject>? arcs = null, bool open = false)
    {
        var curves = new List<LotCurve>();
        for (var i = 0; i < (open ? ring.Count - 1 : ring.Count); i++)
        {
            var (a, b) = (ring[i], ring[(i + 1) % ring.Count]);
            if (arcs is not null && arcs.TryGetValue(i, out var arc))
            {
                var c = (arc["center"]![0]!.GetValue<double>(), arc["center"]![1]!.GetValue<double>());
                var m = (arc["through"]![0]!.GetValue<double>(), arc["through"]![1]!.GetValue<double>());
                var (a0, sweep, r) = Sweep(a, m, b, c);
                curves.Add(new LotCurve(Place(a.X, a.Y, 0), Place(b.X, b.Y, 0), false, Math.Abs(sweep) * r,
                    t => Place(c.Item1 + r * Math.Cos(a0 + sweep * t), c.Item2 + r * Math.Sin(a0 + sweep * t), 0)));
            }
            else
                curves.Add(new LotCurve(Place(a.X, a.Y, 0), Place(b.X, b.Y, 0), true));
        }
        return new LotLineElement(id, true, curves);
    }

    /// <summary>The arc from a through m to b about centre c: its start angle, its sweep (signed: anticlockwise
    /// positive) and its radius.</summary>
    internal static (double A0, double Sweep, double R) Sweep((double X, double Y) a, (double X, double Y) m,
                                                            (double X, double Y) b, (double X, double Y) c)
    {
        double Ang((double X, double Y) p) => Math.Atan2(p.Y - c.Y, p.X - c.X);
        double Ccw(double from, double to) => ((to - from) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI);
        var a0 = Ang(a);
        double toEnd = Ccw(a0, Ang(b)), toMid = Ccw(a0, Ang(m));
        var sweep = toMid <= toEnd ? toEnd : toEnd - 2 * Math.PI;
        return (a0, sweep, Math.Sqrt((a.X - c.X) * (a.X - c.X) + (a.Y - c.Y) * (a.Y - c.Y)));
    }

    /// <summary>n + 1 points along the arc from a through m to b.</summary>
    internal static List<(double X, double Y)> ArcPoints((double X, double Y) a, (double X, double Y) m,
                                                         (double X, double Y) b, int n)
    {
        double d = 2 * (a.X * (b.Y - m.Y) + b.X * (m.Y - a.Y) + m.X * (a.Y - b.Y));
        double sa = a.X * a.X + a.Y * a.Y, sb = b.X * b.X + b.Y * b.Y, sm = m.X * m.X + m.Y * m.Y;
        var c = ((sa * (b.Y - m.Y) + sb * (m.Y - a.Y) + sm * (a.Y - b.Y)) / d,
                 (sa * (m.X - b.X) + sb * (a.X - m.X) + sm * (b.X - a.X)) / d);
        var (a0, sweep, r) = Sweep(a, m, b, c);
        var pts = Enumerable.Range(0, n + 1).Select(k => (c.Item1 + r * Math.Cos(a0 + sweep * k / n),
                                                           c.Item2 + r * Math.Sin(a0 + sweep * k / n))).ToList();
        pts[0] = a;
        pts[^1] = b;
        return pts;
    }

    private static IEnumerable<(double X, double Y)> Spread(List<(double X, double Y)> along, int count)
    {
        // count points evenly along a polyline (by piece, then within it)
        for (var k = 0; k < count; k++)
        {
            var t = (double)k / (count - 1) * (along.Count - 1);
            var i = Math.Min((int)t, along.Count - 2);
            var f = t - i;
            yield return (along[i].X + (along[i + 1].X - along[i].X) * f, along[i].Y + (along[i + 1].Y - along[i].Y) * f);
        }
    }

    // ---- elements ---------------------------------------------------------------------------------------------

    public static RevitElement Directshape(string id, IReadOnlyList<GeometryItem> geometry, GordiumMark mark = GordiumMark.None,
                                           string? floorMark = null) => new()
    {
        UniqueId = id, BuiltInCategory = "OST_GenericModel", Category = "Generic Models", Mark = mark,
        FloorMark = floorMark, Name = id, Geometry = geometry, BoundingBox = BoxOf(geometry),
    };

    public static RevitElement Wall(string id, IReadOnlyList<GeometryItem> geometry) => Part(id, "OST_Walls", "Walls", geometry);

    /// <summary>A system element (a wall, a floor, a roof, a mullion) of that category.</summary>
    public static RevitElement Part(string id, string category, string name, IReadOnlyList<GeometryItem> geometry) => new()
    {
        UniqueId = id, BuiltInCategory = category, Category = name, Name = id, Geometry = geometry,
        BoundingBox = BoxOf(geometry),
    };

    public static RevitElement Family(string id, IReadOnlyList<GeometryItem> inside, string category = "OST_GenericModel",
                                      string name = "Generic Models") => new()
    {
        UniqueId = id, BuiltInCategory = category, Category = name, Kind = ElementKind.FamilyInstance, Name = id,
        Geometry = [new InstanceItem(inside)], BoundingBox = inside.Count > 0 ? BoxOf(inside) : null,
    };

    public static RevitElement LinkOf(string id, RevitModel doc, string status = "Loaded", Transform3? at = null) => new()
    {
        UniqueId = id, BuiltInCategory = "OST_RvtLinks", Category = "RVT Links", Kind = ElementKind.LinkInstance,
        Link = new RevitLink(status, at ?? Transform3.Identity, status == "Loaded" ? doc : null),
    };
}
