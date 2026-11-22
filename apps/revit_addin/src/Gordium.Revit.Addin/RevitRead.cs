using System.IO;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.ExternalData;
using Gordium.Revit.Reading;
using Transform = Autodesk.Revit.DB.Transform;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Revit layer: one open document copied into the reader's plain records (Gordium.Revit.Reading/Records.cs),
/// each from the API member that record names. It decides nothing (no element is skipped, sorted or judged here:
/// that is SiteReader's, tested on the Mac); it copies what Revit says. It must run on Revit's own thread: a lot
/// line's <see cref="LotCurve.PointAt"/> calls back into the API, so the read and SiteReader's lot reading both run
/// there before anything is awaited (docs/revit/revit_reading_design.md).
/// </summary>
internal static class RevitRead
{
    /// <summary>Gordium's own marks on a DirectShape (design note, section 1: "a DirectShape carrying a Gordium
    /// mark"): <c>ApplicationId</c> is this, and <c>ApplicationDataId</c> says which mark.</summary>
    internal const string MarkApplication = "Gordium";

    internal const string FloorPrefix = "floor:";            // floor:<story>;<height drawn, ft>
    internal const string ContextMark = "context";
    internal const string SpotMark = "spot";
    internal const string FinishedMark = "finished";

    /// <summary>How deep links inside links are read (a linked model's own links).</summary>
    private const int LinkDepth = 4;

    internal static RevitModel Model(Document doc, string version, double vertexTolerance) =>
        Model(doc, version, vertexTolerance, depth: 0);

    private static RevitModel Model(Document doc, string version, double vertexTolerance, int depth)
    {
        var options = new Options { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };
        var elements = new List<RevitElement>();
        foreach (var e in new FilteredElementCollector(doc).WhereElementIsNotElementType().ToList())
            elements.Add(Element(doc, e, options, version, vertexTolerance, depth));
        return new RevitModel
        {
            Document = doc.Title,
            Version = version,
            DisplayUnits = doc.GetUnits().GetFormatOptions(SpecTypeId.Length).GetUnitTypeId().TypeId,
            VertexTolerance = vertexTolerance,
            InternalToShared = depth == 0 ? InternalToShared(doc) : Reading.Transform3.Identity,
            Phases = doc.Phases.Cast<Phase>().Select(p => Id(p.Id)!).ToList(),
            OptionSets = OptionSets(doc),
            ActiveOption = Id(DesignOption.GetActiveDesignOptionId(doc)),
            UserWorksets = doc.IsWorkshared
                ? new FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
                    .Select(w => new WorksetRecord(w.Id.IntegerValue.ToString(System.Globalization.CultureInfo.InvariantCulture), w.Name, w.IsOpen)).ToList()
                : [],
            Elements = elements,
            LotLines = LotLines(doc),
        };
    }

    /// <summary>Revit's internal coordinates to the shared ones. <c>ActiveProjectLocation.GetTotalTransform()</c>,
    /// which way round settled by Revit itself: the survey point's and the project base point's internal positions
    /// (<c>BasePoint.Position</c>) must land on their shared ones (<c>SharedPosition</c>) within a millionth of a foot;
    /// if neither way does, the read is refused rather than guessed (the design note's "to check", section 3).</summary>
    internal static Reading.Transform3 InternalToShared(Document doc)
    {
        var total = doc.ActiveProjectLocation.GetTotalTransform();
        var points = new[] { BasePoint.GetSurveyPoint(doc), BasePoint.GetProjectBasePoint(doc) };
        foreach (var t in new[] { total, total.Inverse })
            if (points.All(p => t.OfPoint(p.Position).DistanceTo(p.SharedPosition) < 1e-6))
                return T(t);
        throw new ReadRefusedException(
            "Revit's shared coordinates couldn't be told apart from its internal ones (the survey point and the project " +
            "base point don't agree with either way of the project location's transform): no description is sent");
    }

    private static IReadOnlyList<OptionSet> OptionSets(Document doc)
    {
        var options = new FilteredElementCollector(doc).OfClass(typeof(DesignOption)).Cast<DesignOption>().ToList();
        return options
            .GroupBy(o => o.get_Parameter(BuiltInParameter.OPTION_SET_ID)?.AsElementId() ?? ElementId.InvalidElementId)
            .Select(g => new OptionSet(Id(g.Key) ?? "", doc.GetElement(g.Key)?.Name ?? "",
                                       g.Select(o => new DesignOptionRecord(Id(o.Id)!, o.Name, o.IsPrimary)).ToList()))
            .ToList();
    }

    private static RevitElement Element(Document doc, Element e, Options options, string version, double tolerance, int depth)
    {
        var category = e.Category;
        IReadOnlyList<GeometryItem>? geometry = null, coarser = null;
        var failed = false;
        try
        {
            var g = e.get_Geometry(options);
            geometry = g is null ? null : Items(g);
            if (e is FamilyInstance)
            {
                var more = new List<GeometryItem>();
                foreach (var level in new[] { ViewDetailLevel.Medium, ViewDetailLevel.Coarse })
                    if (e.get_Geometry(new Options { DetailLevel = level, IncludeNonVisibleObjects = false }) is { } other)
                        more.AddRange(Items(other));
                coarser = more.Count > 0 ? more : null;
            }
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or InvalidOperationException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            failed = true;
        }
        var box = e.get_BoundingBox(null);
        var (mark, floorMark) = Mark(e);
        RevitLink? link = null;
        if (e is RevitLinkInstance li)
        {
            var type = doc.GetElement(li.GetTypeId()) as RevitLinkType;
            var linked = li.GetLinkDocument();
            link = new RevitLink(type?.GetLinkedFileStatus().ToString() ?? "Unknown", T(li.GetTotalTransform()),
                                 linked is null || depth >= LinkDepth ? null : Model(linked, version, tolerance, depth + 1));
        }
        return new RevitElement
        {
            UniqueId = e.UniqueId,
            BuiltInCategory = category is null ? "" : category.BuiltInCategory.ToString(),
            Category = category?.Name ?? "",
            CategoryType = category?.CategoryType switch
            {
                Autodesk.Revit.DB.CategoryType.Annotation => Reading.CategoryType.Annotation,
                Autodesk.Revit.DB.CategoryType.Internal => Reading.CategoryType.Internal,
                Autodesk.Revit.DB.CategoryType.AnalyticalModel => Reading.CategoryType.AnalyticalModel,
                _ => Reading.CategoryType.Model,
            },
            ViewSpecific = e.ViewSpecific,
            Name = e.Name,
            Kind = Kind(doc, e),
            IsInPlace = e is FamilyInstance fi && fi.Symbol?.Family?.IsInPlace == true,
            SuperComponent = e is FamilyInstance sub && sub.SuperComponent is { } host ? host.UniqueId : null,
            Mark = mark,
            FloorMark = floorMark,
            // an element's own marks, for Gordium: Site slab is (SiteSlabs) and Site object is (ElementReader.SiteObject);
            // read on floors and the site-object categories only, so no other element pays
            InstanceMarks = OwnMarks(e, category),
            PhaseCreated = Id(e.CreatedPhaseId),
            PhaseDemolished = Id(e.DemolishedPhaseId),
            DesignOption = Id(e.DesignOption?.Id),
            Workset = e.WorksetId is { } w && w != WorksetId.InvalidWorksetId
                ? w.IntegerValue.ToString(System.Globalization.CultureInfo.InvariantCulture) : null,
            BoundingBox = box is null ? null : new RevitBox(P(box.Min), P(box.Max), box.Transform is { } bt ? T(bt) : null),
            Geometry = failed ? null : geometry,
            CoarserGeometry = failed ? null : coarser,
            GeometryFailed = failed,
            Location = e.Location is LocationPoint lp ? P(lp.Point) : MarkerPoint(e, mark),
            Link = link,
        };
    }

    private static ElementKind Kind(Document doc, Element e) => e switch
    {
        RevitLinkInstance when CoordinationModelLinkUtils.IsCoordinationModelInstance(doc, e) => ElementKind.CoordinationModel,
        RevitLinkInstance => ElementKind.LinkInstance,
        FamilyInstance => ElementKind.FamilyInstance,
        Group => ElementKind.Group,
        Wall { CurtainGrid: not null } => ElementKind.CurtainWallHost,
        ImportInstance => ElementKind.CadImport,
        Toposolid => ElementKind.Toposolid,
        _ when CoordinationModelLinkUtils.IsCoordinationModelInstance(doc, e) => ElementKind.CoordinationModel,
        _ => ElementKind.Ordinary,
    };

    /// <summary>The categories whose elements' own marks are read (<see cref="OwnMarks"/>): floors (Site slab is) and
    /// those <see cref="Marks.SiteObject"/> is bound to (a name Revit doesn't have is skipped, never a crash).</summary>
    private static readonly HashSet<BuiltInCategory> MarkedOnElement =
    [
        BuiltInCategory.OST_Floors,
        .. Marks.SiteObject.Categories.Select(c => Enum.TryParse<BuiltInCategory>(c, out var b) ? b : BuiltInCategory.INVALID)
            .Where(b => b != BuiltInCategory.INVALID),
    ];

    private static Dictionary<Guid, MarkValue> OwnMarks(Element e, Category? category) =>
        category is not null && MarkedOnElement.Contains(category.BuiltInCategory) ? RevitMarks.Values(e) : new Dictionary<Guid, MarkValue>();

    /// <summary>The floors, walls and roofs of the document without their geometry (Revit's own box only), each as
    /// <see cref="Element"/> copies it otherwise: what <see cref="SiteSlabs"/> sorts by, for the marking list, which
    /// must name exactly the site slabs the reader reads; and the elements of the site-object categories
    /// (<see cref="Marks.SiteObjectCategories"/>), for the marking list's site-object rows.</summary>
    internal static List<RevitElement> HouseOutline(Document doc)
    {
        var list = new List<RevitElement>();
        var siteObjects = MarkedOnElement.Where(c => c != BuiltInCategory.OST_Floors);
        foreach (var c in new[] { BuiltInCategory.OST_Floors, BuiltInCategory.OST_Walls, BuiltInCategory.OST_Roofs }.Concat(siteObjects))
            foreach (var e in new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType().ToList())
            {
                var box = e.get_BoundingBox(null);
                var (mark, floorMark) = Mark(e);
                list.Add(new RevitElement
                {
                    UniqueId = e.UniqueId,
                    BuiltInCategory = c.ToString(),
                    Category = e.Category?.Name ?? "",
                    ViewSpecific = e.ViewSpecific,
                    Name = e.Name,
                    Kind = Kind(doc, e),
                    // the marking list says a sub-component's own mark isn't read (it is read as part of its host)
                    SuperComponent = e is FamilyInstance sub && sub.SuperComponent is { } host ? host.UniqueId : null,
                    Mark = mark,
                    FloorMark = floorMark,
                    InstanceMarks = OwnMarks(e, e.Category),
                    PhaseCreated = Id(e.CreatedPhaseId),
                    PhaseDemolished = Id(e.DemolishedPhaseId),
                    DesignOption = Id(e.DesignOption?.Id),
                    BoundingBox = box is null ? null : new RevitBox(P(box.Min), P(box.Max), box.Transform is { } bt ? T(bt) : null),
                });
            }
        return list;
    }

    private static (GordiumMark, string?) Mark(Element e)
    {
        if (e is not DirectShape ds || ds.ApplicationId != MarkApplication || ds.ApplicationDataId is not { } data)
            return (GordiumMark.None, null);
        if (data.StartsWith(FloorPrefix, StringComparison.Ordinal))
            return (GordiumMark.FloorBlock, data[FloorPrefix.Length..]);
        return data switch
        {
            ContextMark => (GordiumMark.Context, null),
            SpotMark => (GordiumMark.SpotGrade, null),
            FinishedMark => (GordiumMark.FinishedGrade, null),
            _ => (GordiumMark.None, null),       // a mark this add-in doesn't know: not a mark, read as any element
        };
    }

    /// <summary>A Gordium grade marker drawn as a DirectShape (no <c>LocationPoint</c>): the one point it holds.
    /// None or several: no location, so the reader refuses the marker rather than guess.</summary>
    private static Xyz? MarkerPoint(Element e, GordiumMark mark)
    {
        if (mark is not (GordiumMark.SpotGrade or GordiumMark.FinishedGrade) || e.get_Geometry(new Options()) is not { } g)
            return null;
        var points = g.OfType<Autodesk.Revit.DB.Point>().ToList();
        return points.Count == 1 ? P(points[0].Coord) : null;
    }

    private static List<GeometryItem> Items(GeometryElement g)
    {
        var items = new List<GeometryItem>();
        foreach (var o in g)
            items.Add(o switch
            {
                Solid s => Solid(s),
                Mesh m => MeshOf(m),
                GeometryInstance gi => new InstanceItem(gi.GetInstanceGeometry() is { } ig ? Items(ig) : null),
                Autodesk.Revit.DB.Curve or Autodesk.Revit.DB.Point or PolyLine => new LineworkItem(),
                _ => new OtherItem(o.GetType().Name),
            });
        return items;
    }

    private static SolidItem Solid(Solid s)
    {
        var faces = new List<FaceRecord>();
        foreach (Face f in s.Faces)
            faces.Add(new FaceRecord(f.GetType().Name,
                f.GetEdgesAsCurveLoops().Select(loop => (IReadOnlyList<LoopCurve>)loop.Select(c => new LoopCurve(P(c.GetEndPoint(0)), c is Line)).ToList()).ToList(),
                Samples(f)));
        var edges = new List<EdgeRecord>();
        foreach (Edge e in s.Edges)
            edges.Add(new EdgeRecord(e.Tessellate().Select(P).ToList(), e.GetFace(1) is not null));
        return new SolidItem(faces, edges);
    }

    /// <summary>A 7 × 7 grid of points over the face's own parameter range (<c>Face.Evaluate</c>): where it stands
    /// in plan, never sent as a face.</summary>
    private static List<Xyz> Samples(Face f)
    {
        var b = f.GetBoundingBox();
        var points = new List<Xyz>(49);
        for (var i = 0; i < 7; i++)
            for (var j = 0; j < 7; j++)
                points.Add(P(f.Evaluate(new UV(b.Min.U + (b.Max.U - b.Min.U) * i / 6.0, b.Min.V + (b.Max.V - b.Min.V) * j / 6.0))));
        return points;
    }

    private static MeshItem MeshOf(Mesh m)
    {
        var triangles = new List<(int, int, int)>(m.NumTriangles);
        for (var i = 0; i < m.NumTriangles; i++)
        {
            var t = m.get_Triangle(i);
            triangles.Add(((int)t.get_Index(0), (int)t.get_Index(1), (int)t.get_Index(2)));
        }
        return new MeshItem(m.Vertices.Select(P).ToList(), triangles, m.IsClosed);
    }

    /// <summary>Every property line (its boundary, <c>PropertyLine.GetBoundary()</c>, Revit 2027) and every model
    /// line the architect could pick (<c>CurveElement</c>). A curve with no ends (<c>Curve.IsBound</c> false: a full
    /// circle or ellipse drawn as one curve; <c>GetEndPoint</c> throws on it) is only counted
    /// (<see cref="LotLineElement.Unbound"/>), never read; LotReader decides what it means.</summary>
    internal static List<LotLineElement> LotLines(Document doc)
    {
        var lines = new List<LotLineElement>();
        foreach (var pl in new FilteredElementCollector(doc).OfClass(typeof(PropertyLine)).Cast<PropertyLine>().ToList())
            lines.Add(LotLine(pl.UniqueId, true, pl.GetBoundary().SelectMany(loop => loop).ToList()));
        foreach (var ce in new FilteredElementCollector(doc).OfClass(typeof(CurveElement)).Cast<CurveElement>().ToList())
            if (ce.CurveElementType == CurveElementType.ModelCurve && ce.GeometryCurve is { } c)
                lines.Add(LotLine(ce.UniqueId, false, [c]));
        return lines;
    }

    private static LotLineElement LotLine(string id, bool isPropertyLine, List<Curve> curves) =>
        new(id, isPropertyLine, curves.Where(c => c.IsBound).Select(Curve).ToList(), curves.Count(c => !c.IsBound));

    private static LotCurve Curve(Curve c) =>
        new(P(c.GetEndPoint(0)), P(c.GetEndPoint(1)), c is Line, c.Length, t => P(c.Evaluate(t, true)));

    private static Xyz P(XYZ p) => new(p.X, p.Y, p.Z);

    private static Reading.Transform3 T(Transform t) => new(P(t.Origin), P(t.BasisX), P(t.BasisY), P(t.BasisZ));

    private static string? Id(ElementId? id) =>
        id is null || id == ElementId.InvalidElementId ? null : id.Value.ToString(System.Globalization.CultureInfo.InvariantCulture);
}
