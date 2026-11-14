using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>A left-out candidate: an element that could be a building and isn't measured, as sent to
/// <c>objects.left_out</c> (<see cref="Sent"/>), and what the description lists of it if it is left out.</summary>
internal sealed record Candidate(string Id, string Layer, bool Context, JsonObject Sent, Box3? Box, string GroundKind, bool Closed);

/// <summary>What the reader gathered from one element's geometry (design note, section 2).</summary>
internal sealed class Gathered
{
    public readonly List<JsonObject> Faces = [];
    public readonly List<JsonObject> Problems = [];
    public readonly BoxBuilder Box = new();
    public readonly List<(double X, double Y)> Plan = [];
    public bool HasFaces, Other, MissingPart, AnySolid, AnyMesh, AllClosed = true;

    public void Point(Xyz p)
    {
        if (!p.IsFinite)
            throw new ArgumentException("a point of the model isn't a number");
        Box.Add(p);
        Plan.Add((p.X, p.Y));
    }

    public void Problem(JsonObject p)
    {
        if (!Problems.Any(q => JsonNode.DeepEquals(q, p)))
            Problems.Add(p);
    }
}

/// <summary>One read of a model: each element sorted into a building, an object that couldn't be sent, a left-out
/// candidate, a grade point, or nothing.</summary>
internal sealed class Read(RevitModel model)
{
    public readonly Transform3 ToShared = model.InternalToShared;
    public readonly List<JsonObject> Buildings = [];
    public readonly List<JsonObject> Unsent = [];
    public readonly List<Box3> BuildingBoxes = [];
    public readonly List<Candidate> Candidates = [];
    public readonly JsonObject Definitions = new();
    public readonly List<Xyz> SpotGrades = [];
    public readonly List<Xyz> FinishedGrades = [];

    /// <summary>False whenever any user workset is closed (whether or not its elements can still be read: to
    /// check), or a linked model, at any depth, isn't loaded: the reader can't have looked at everything.</summary>
    public bool InventoryComplete = model.UserWorksets.All(w => w.IsOpen);

    public void Element(RevitElement e)
    {
        switch (e)
        {
            case { Mark: GordiumMark.SpotGrade or GordiumMark.FinishedGrade }:
                var at = e.Location is { IsFinite: true } p ? ToShared.Apply(p)
                    : throw new ReadRefusedException($"the grade marker {e.UniqueId} has no place to read: move it or delete it");
                (e.Mark == GordiumMark.SpotGrade ? SpotGrades : FinishedGrades).Add(at);
                break;
            case { Kind: ElementKind.LinkInstance }:
                Link(e);
                break;
            case { Mark: GordiumMark.Context }:
                Ordinary(e, context: true);
                break;
            case { Mark: GordiumMark.FloorBlock }:
            case var _ when SiteReader.BuildingCategories.Contains(e.BuiltInCategory):
                Building(e);
                break;
            case { Kind: ElementKind.FamilyInstance or ElementKind.CadImport }:
                Family(e);
                break;
            case { Kind: ElementKind.Toposolid }:
                Toposolid(e);
                break;
            default:
                Ordinary(e, context: false);
                break;
        }
    }

    // ---- buildings ----------------------------------------------------------------------------------------------

    /// <summary>A building-category element or a floor block: one building, the faces of all its solids (design
    /// note, sections 1 and 2). Never skipped for having nothing to send: then it is an object that couldn't be
    /// sent, so every building measure needs review (Rhino sends an empty solid on the Building layer as a building
    /// with no faces).</summary>
    private void Building(RevitElement e)
    {
        if (e.GeometryFailed)
        {
            Unsend(e, e.Category, RevitBox(e, ToShared));
            return;
        }
        var g = e.Geometry is null ? null : Walk(e.Geometry, ToShared, e);
        if (g is { Other: true })
        {
            Unsend(e, e.Category, Union(g.Box.Box, RevitBox(e, ToShared)));
            return;
        }
        if (g is null || !g.HasFaces)
        {
            if (e.Kind == ElementKind.CurtainWallHost)
                return;                  // its panels and mullions are their own elements; it has no faces of its own
            Unsend(e, $"a {e.Category} with no geometry", RevitBox(e, ToShared));
            return;
        }
        if (g.MissingPart)               // a nested family that gave nothing: the building may be bigger than its faces
            g.Problem(SiteReader.Problem("tool_words",
                ("words", "part of this element (a nested family) has no geometry to read, so it may be bigger than measured")));
        var b = new JsonObject
        {
            ["id"] = e.UniqueId, ["role"] = "building", ["layer"] = e.Category,
            ["floor"] = e.Mark == GordiumMark.FloorBlock ? FloorHeight(e.FloorMark) : null,
            ["faces"] = new JsonArray(g.Faces.Select(f => (JsonNode)f).ToArray()),
            ["problems"] = new JsonArray(g.Problems.Select(p => (JsonNode)p).ToArray()),
        };
        if (e.Name is { } name)
            b["name"] = name;
        Buildings.Add(b);
        if (Union(g.Box.Box, RevitBox(e, ToShared)) is { } box)
            BuildingBoxes.Add(box);
    }

    /// <summary>A floor block's height as drawn, from its mark "&lt;story&gt;;&lt;height&gt;", or null when it can't be read
    /// (<c>read_3dm._floor_height</c>).</summary>
    internal static double? FloorHeight(string? mark)
    {
        var parts = mark?.Split(';');
        return parts is { Length: >= 2 } && double.TryParse(parts[1], System.Globalization.NumberStyles.Float,
                   System.Globalization.CultureInfo.InvariantCulture, out var h) && double.IsFinite(h) ? h : null;
    }

    private void Unsend(RevitElement e, string kind, Box3? box)
    {
        Unsent.Add(new JsonObject
        {
            ["id"] = e.UniqueId, ["layer"] = e.Category, ["kind"] = kind,
            ["problem"] = SiteReader.Problem("not_a_solid", ("kind", kind), ("layer", e.Category)),
        });
        if (box is { } b)
            BuildingBoxes.Add(b);         // anything near it may be part of it
    }

    // ---- everything else that could be a building ----------------------------------------------------------------

    /// <summary>Any other element: left out when it has a solid or a mesh with faces (closed or not), skipped when it
    /// has only lines and points or no geometry at all (nothing that could be a building); an object that couldn't
    /// be sent when reading its geometry failed or it holds geometry of a kind the reader doesn't know.</summary>
    private void Ordinary(RevitElement e, bool context)
    {
        if (e.GeometryFailed)
        {
            Unsend(e, e.Category, RevitBox(e, ToShared));
            return;
        }
        if (e.Geometry is null)
            return;
        var g = Walk(e.Geometry, ToShared, e);
        if (g.Other)
        {
            Unsend(e, e.Category, Union(g.Box.Box, RevitBox(e, ToShared)));
            return;
        }
        if (!g.HasFaces)
            return;
        // a nested family that gave nothing: no box covers all of it, so its place can't be told (touching: null)
        var box = g.MissingPart ? null : Union(g.Box.Box, RevitBox(e, ToShared));
        Candidates.Add(Make(e, g, box, null, context, g.AnyMesh && !g.AnySolid ? "Mesh" : "Brep", g.AllClosed));
    }

    /// <summary>A family instance (loadable or in-place) or a 3D CAD import off the building categories: left out
    /// whatever its geometry, even none (design note, section 1); what it holds, at every depth, sent as its
    /// definition, so a nested family that gives nothing leaves it with no box (touching: null).</summary>
    private void Family(RevitElement e)
    {
        var key = e.UniqueId;
        var parts = e.GeometryFailed ? new JsonArray(new JsonObject { ["box"] = null })
                                     : Parts(e.Geometry ?? [], ToShared, key, e);
        Definitions[key] = new JsonObject { ["status"] = SiteReader.NotLinked, ["parts"] = parts };
        var g = e.GeometryFailed || e.Geometry is null ? new Gathered() : Walk(e.Geometry, ToShared, e);
        Candidates.Add(Make(e, g, Union(g.Box.Box, RevitBox(e, ToShared)), key, false, "Family", true));
    }

    /// <summary>A Toposolid: left out (a closed solid that could be a building until the architect says it is the
    /// ground); never labelled as looking like the ground in the first reader.</summary>
    private void Toposolid(RevitElement e)
    {
        var g = e.GeometryFailed || e.Geometry is null ? new Gathered() : Walk(e.Geometry, ToShared, e);
        var box = g.MissingPart || g.Other ? null : Union(g.Box.Box, RevitBox(e, ToShared));
        Candidates.Add(Make(e, g, box, null, false, "Toposolid", true));
    }

    private static Candidate Make(RevitElement e, Gathered g, Box3? box, string? definition, bool context, string kind, bool closed)
    {
        var sent = new JsonObject { ["id"] = e.UniqueId, ["box"] = box is { } b ? Numbers(b.ToArray()) : null };
        var points = g.Plan.Count is > 0 and <= SiteReader.MaxPlanPoints ? g.Plan
            : box is { } c ? [(c.Min.X, c.Min.Y), (c.Max.X, c.Min.Y), (c.Max.X, c.Max.Y), (c.Min.X, c.Max.Y)]
            : null;
        if (points is not null)
            sent["points"] = new JsonArray(points.Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray());
        if (definition is not null)
            sent["definition"] = definition;
        return new Candidate(e.UniqueId, e.Category, context, sent, box, kind, closed);
    }

    /// <summary>What a family holds, each piece a part as host_core reads it: a solid or mesh with faces, its box; a
    /// nested family, its own definition (<paramref name="key"/>/n), with a box only when it gives geometry; a piece
    /// of a kind the reader doesn't know, no box.</summary>
    private JsonArray Parts(IReadOnlyList<GeometryItem> items, Transform3 t, string key, RevitElement e)
    {
        var parts = new JsonArray();
        for (var i = 0; i < items.Count; i++)
        {
            switch (items[i])
            {
                case SolidItem { Faces.Count: > 0 } or MeshItem { Triangles.Count: > 0 }:
                    parts.Add(new JsonObject { ["box"] = Numbers(Walk([items[i]], t, e).Box.Box?.ToArray()) });
                    break;
                case OtherItem or InstanceItem { Items: null }:
                    parts.Add(new JsonObject { ["box"] = null });
                    break;
                case InstanceItem { Items: { } inner }:
                    var nested = $"{key}/{i}";
                    Definitions[nested] = new JsonObject { ["status"] = SiteReader.NotLinked, ["parts"] = Parts(inner, t, nested, e) };
                    var g = Walk(inner, t, e);
                    parts.Add(new JsonObject { ["box"] = Numbers(g.Box.Box?.ToArray()), ["definition"] = nested });
                    break;
            }
        }
        return parts;
    }

    // ---- linked models ------------------------------------------------------------------------------------------

    /// <summary>A linked Revit model (proposed, design note, section 1). Not loaded: it can't be looked inside, so the
    /// reader hasn't looked at everything (<c>inventory_complete: false</c>). Loaded and holding any building-category
    /// element at any depth of links inside links, or a closed workset of its own: an object that couldn't be sent
    /// (wherever it is placed), so every building measure needs review. Otherwise left out, like a family, what it
    /// holds sent as its definition. Inside a link every element counts, whatever its phase or design option: the
    /// link's own phase mapping isn't read (to check), and more is only more cautious.</summary>
    private void Link(RevitElement e)
    {
        if (e.Link is not { Status: "Loaded", Document: { } doc } link)
        {
            InventoryComplete = false;
            return;
        }
        var key = e.UniqueId;
        var inside = new Inside();
        var parts = LookInside(doc, ToShared.After(link.Transform), key, inside);
        var box = Union(inside.Box.Box, RevitBox(e, ToShared));
        if (inside.Unloaded)
            InventoryComplete = false;
        if (inside.HoldsBuilding || inside.ClosedWorkset)
        {
            Unsend(e, SiteReader.LinkedModelKind, box);
            return;
        }
        Definitions[key] = new JsonObject { ["status"] = SiteReader.LinkKnown, ["parts"] = parts };
        var g = new Gathered();
        foreach (var p in inside.Plan)
            g.Plan.Add(p);
        Candidates.Add(Make(e, g, inside.MissingPart ? null : box, key, false, "Link", true));
    }

    private sealed class Inside
    {
        public bool HoldsBuilding, ClosedWorkset, Unloaded, MissingPart;
        public readonly BoxBuilder Box = new();
        public readonly List<(double X, double Y)> Plan = [];
    }

    private JsonArray LookInside(RevitModel doc, Transform3 t, string key, Inside inside)
    {
        inside.ClosedWorkset |= doc.UserWorksets.Any(w => !w.IsOpen);
        var parts = new JsonArray();
        foreach (var el in doc.Elements.Where(SiteReader.Looked))
        {
            if (el.Kind == ElementKind.LinkInstance)
            {
                if (el.Link is not { Status: "Loaded", Document: { } inner } link)
                {
                    inside.Unloaded = inside.MissingPart = true;
                    parts.Add(new JsonObject { ["box"] = null });
                    continue;
                }
                var nested = $"{key}/{el.UniqueId}";
                var deeper = new Inside();
                var t2 = t.After(link.Transform);
                Definitions[nested] = new JsonObject { ["status"] = SiteReader.LinkKnown, ["parts"] = LookInside(inner, t2, nested, deeper) };
                inside.HoldsBuilding |= deeper.HoldsBuilding;
                inside.ClosedWorkset |= deeper.ClosedWorkset;
                inside.Unloaded |= deeper.Unloaded;
                inside.MissingPart |= deeper.MissingPart;
                var nb = Union(deeper.Box.Box, RevitBox(el, t));
                inside.Box.Add(nb);
                inside.Plan.AddRange(deeper.Plan);
                parts.Add(new JsonObject { ["box"] = Numbers(nb?.ToArray()), ["definition"] = nested });
                continue;
            }
            if (el.Mark == GordiumMark.FloorBlock || SiteReader.BuildingCategories.Contains(el.BuiltInCategory))
            {
                inside.HoldsBuilding = true;
                continue;
            }
            if (el.Mark is GordiumMark.SpotGrade or GordiumMark.FinishedGrade)
                continue;
            var anyGeometry = el.Kind is ElementKind.FamilyInstance or ElementKind.CadImport or ElementKind.Toposolid;
            if (el.GeometryFailed)
            {
                inside.MissingPart = true;
                parts.Add(new JsonObject { ["box"] = null });
                continue;
            }
            var g = el.Geometry is null ? new Gathered() : Walk(el.Geometry, t, el);
            if (!g.HasFaces && !anyGeometry && !g.Other)
                continue;                                        // lines and points only: nothing that could be a building
            var empty = anyGeometry && !g.HasFaces;              // a family with nothing in it: its place can't be told
            var box = g.MissingPart || g.Other || empty ? null : Union(g.Box.Box, RevitBox(el, t));
            inside.MissingPart |= box is null;
            inside.Box.Add(box);
            inside.Plan.AddRange(g.Plan);
            parts.Add(new JsonObject { ["box"] = Numbers(box?.ToArray()) });
        }
        return parts;
    }

    // ---- geometry -----------------------------------------------------------------------------------------------

    /// <summary>The faces of an element's geometry, with what can't be sent exactly reported (design note, section
    /// 2): a flat face whose every edge is a line is sent (its largest loop in its plane the outline, the others its
    /// holes); a curved face is left out with <c>curved_surface</c>, a flat face with a curved edge with
    /// <c>curved_edge</c> (never triangulated); a solid with an edge on only one face is <c>open_solid</c>; a mesh's
    /// triangles are sent, with <c>open_mesh</c> unless it is known to be closed; an empty solid, curves and points
    /// are skipped; a nested family is read through; any other kind of piece is noted (<see cref="Gathered.Other"/>).
    /// Every point the reader reads goes into the element's box and plan points.</summary>
    internal static Gathered Walk(IReadOnlyList<GeometryItem> items, Transform3 t, RevitElement e, Gathered? into = null)
    {
        var g = into ?? new Gathered();
        foreach (var item in items)
        {
            switch (item)
            {
                case SolidItem { Faces.Count: 0 }:
                    break;                                       // an empty solid: nothing to send
                case SolidItem s:
                    g.HasFaces = g.AnySolid = true;
                    if (s.Edges.Any(x => !x.HasSecondFace))
                    {
                        g.AllClosed = false;
                        g.Problem(SiteReader.Problem("open_solid", ("what", e.Name ?? e.UniqueId)));
                    }
                    foreach (var edge in s.Edges)
                        foreach (var p in edge.Along)
                            g.Point(t.Apply(p));
                    foreach (var f in s.Faces)
                        Face(f, t, g);
                    break;
                case MeshItem { Triangles.Count: 0 }:
                    break;
                case MeshItem m:
                    g.HasFaces = g.AnyMesh = true;
                    if (m.IsClosed != true)
                    {
                        g.AllClosed = false;
                        g.Problem(SiteReader.Problem("open_mesh"));
                    }
                    var v = m.Vertices.Select(t.Apply).ToList();
                    foreach (var p in v)
                        g.Point(p);
                    foreach (var (a, b, c) in m.Triangles)
                    {
                        if (new[] { a, b, c }.Any(k => k < 0 || k >= v.Count))
                            throw new ArgumentException($"a mesh of {e.UniqueId} has a triangle with no such vertex");
                        g.Faces.Add(new JsonObject { ["points"] = Ring([v[a], v[b], v[c]]) });
                    }
                    break;
                case InstanceItem { Items: null }:
                    g.MissingPart = true;
                    break;
                case InstanceItem { Items: { } inner }:
                    Walk(inner, t, e, g);
                    break;
                case LineworkItem:
                    break;
                default:
                    g.Other = true;
                    break;
            }
        }
        return g;
    }

    private static void Face(FaceRecord f, Transform3 t, Gathered g)
    {
        foreach (var loop in f.Loops)
            foreach (var c in loop)
                g.Point(t.Apply(c.Start));
        foreach (var p in f.Samples)
            g.Point(t.Apply(p));
        if (f.Type != "PlanarFace")
        {
            g.Problem(SiteReader.Problem("curved_surface"));
            return;
        }
        if (f.Loops.Any(l => l.Any(c => !c.IsLine)))
        {
            g.Problem(SiteReader.Problem("curved_edge"));
            return;
        }
        var loops = f.Loops.Select(l => l.Select(c => t.Apply(c.Start)).ToList()).ToList();
        if (loops.Count == 0 || loops.Any(l => l.Count < 3))
        {
            g.Problem(SiteReader.Problem("tool_words", ("words", "a flat face has a loop of fewer than 3 corners")));
            return;
        }
        var outer = loops.OrderByDescending(Area).First();      // the largest loop in the face's plane (to check)
        var face = new JsonObject { ["points"] = Ring(outer) };
        var holes = loops.Where(l => !ReferenceEquals(l, outer)).ToList();
        if (holes.Count > 0)
            face["holes"] = new JsonArray(holes.Select(h => (JsonNode)Ring(h)).ToArray());
        g.Faces.Add(face);
    }

    /// <summary>A flat loop's area (half its Newell vector's length): the same in any coordinates.</summary>
    internal static double Area(List<Xyz> loop)
    {
        double x = 0, y = 0, z = 0;
        for (var i = 0; i < loop.Count; i++)
        {
            Xyz a = loop[i], b = loop[(i + 1) % loop.Count];
            x += (a.Y - b.Y) * (a.Z + b.Z);
            y += (a.Z - b.Z) * (a.X + b.X);
            z += (a.X - b.X) * (a.Y + b.Y);
        }
        return Math.Sqrt(x * x + y * y + z * z) / 2;
    }

    private static JsonArray Ring(IEnumerable<Xyz> pts) =>
        new(pts.Select(p => (JsonNode)new JsonArray(p.X, p.Y, p.Z)).ToArray());

    /// <summary>Revit's own box for the element, its 8 corners turned by its own transform then by
    /// <paramref name="t"/> (design note, section 3), or null when Revit gives none.</summary>
    internal static Box3? RevitBox(RevitElement e, Transform3 t)
    {
        if (e.BoundingBox is not { } b)
            return null;
        if (!b.Min.IsFinite || !b.Max.IsFinite)
            throw new ArgumentException($"the box of {e.UniqueId} isn't numbers");
        return Box3.Turned(b.Min, b.Max, b.Transform is null ? t : t.After(b.Transform));
    }

    private static Box3? Union(Box3? a, Box3? b) => a is { } x ? (b is { } y ? x.Union(y) : x) : b;

    private static JsonArray? Numbers(double[]? v) => v is null ? null : new JsonArray(v.Select(x => (JsonNode)x).ToArray());
}
