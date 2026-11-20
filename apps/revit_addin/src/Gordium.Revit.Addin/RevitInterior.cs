using System.Globalization;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Gordium.Revit.Reading;
using Transform = Autodesk.Revit.DB.Transform;

namespace Gordium.Revit.Addin;

/// <summary>
/// The Revit layer of the interior reader (docs/revit/revit_interior_reading_design.md, section 7, step 3): it copies
/// each room's boundary and what stands in, under and over it, each window's and door's placement, every enclosed
/// area on every level and every link into the reader's records (Gordium.Revit.Reading/InteriorRecords.cs), each from
/// the API member the record names. It decides nothing: what is sent, and what is left out and why, is
/// <see cref="InteriorReader"/>'s, tested without Revit. It runs on Revit's own thread.
/// </summary>
internal static class RevitInterior
{
    /// <summary>1/16 in, in feet.</summary>
    private const double Sixteenth = 1.0 / 16 / 12;

    /// <summary>The model with its marks (RevitMarks.Model) and its inside, ready for <see cref="InteriorReader.Read"/>.</summary>
    internal static RevitModel Model(Document doc) => RevitMarks.Model(doc) with
    {
        InternalToShared = InternalToShared(doc),
        UserWorksets = doc.IsWorkshared
            ? new FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
                .Select(w => new WorksetRecord(w.Id.IntegerValue.ToString(CultureInfo.InvariantCulture), w.Name, w.IsOpen)).ToList()
            : [],
        Interior = Read(doc),
    };

    /// <summary>Revit's internal coordinates to the shared ones: <c>ActiveProjectLocation.GetTotalTransform()</c>, the
    /// way round on which the survey point and the project base point land on their shared positions (as the outside
    /// reader settles it); refused when neither does, never guessed.</summary>
    internal static Reading.Transform3 InternalToShared(Document doc)
    {
        var total = doc.ActiveProjectLocation.GetTotalTransform();
        var points = new[] { BasePoint.GetSurveyPoint(doc), BasePoint.GetProjectBasePoint(doc) };
        foreach (var t in new[] { total, total.Inverse })
            if (points.All(p => t.OfPoint(p.Position).DistanceTo(p.SharedPosition) < 1e-6))
                return T(t);
        throw new InvalidOperationException(
            "Revit's shared coordinates couldn't be told apart from its internal ones (the survey point and the project " +
            "base point agree with neither way of the project location's transform): the inside isn't read");
    }

    internal static InteriorRecords Read(Document doc)
    {
        var phase = doc.Phases.Cast<Phase>().LastOrDefault();
        var rooms = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()
            .OfType<Room>().Select(r => RoomOf(doc, r)).ToList();
        var openings = new[] { BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors }
            .SelectMany(c => new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType().OfType<FamilyInstance>())
            .Select(fi => OpeningOf(doc, fi, phase)).ToList();
        var diagnostics = new List<string>();
        return new InteriorRecords
        {
            Rooms = rooms,
            Openings = openings,
            EnclosedAreas = phase is null ? null : Areas(doc, phase, diagnostics),
            Links = Links(doc),
            Diagnostics = diagnostics,
        };
    }

    // ---- enclosed areas and links -------------------------------------------------------------------------------

    /// <summary>Every enclosed area (<c>PlanCircuit</c>) on every level for the last phase; null when Revit couldn't
    /// give one level's (then no room can be read). Revit works out a level's plan topology only in a document it can
    /// change ("Accessing plan topology requires that document is modifiable", the API's own remark): a level never
    /// worked out yet (one with nothing on it: trial run 2, 2026-11-20) threw in a read-only moment. So it is read
    /// inside a transaction that is rolled back, changing nothing in the model.</summary>
    private static List<EnclosedArea>? Areas(Document doc, Phase phase, List<string> diagnostics)
    {
        Transaction? t = null;
        if (!doc.IsModifiable && !doc.IsReadOnly)
        {
            t = new Transaction(doc, "Gordium: read the enclosed areas (rolled back)");
            t.Start();
        }
        try
        {
            var areas = new List<EnclosedArea>();
            foreach (var level in new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>())
            {
                PlanTopology topology;
                try
                {
                    topology = doc.get_PlanTopology(level, phase);
                }
                catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException)
                {
                    diagnostics.Add($"enclosed areas on {level.Name}: Revit refused ({x.GetType().Name}: {x.Message}), modifiable {doc.IsModifiable}");
                    return null;
                }
                if (topology?.Circuits is not { } circuits)
                {
                    diagnostics.Add($"enclosed areas on {level.Name}: Revit gave no {(topology is null ? "plan topology" : "circuits")}");
                    return null;
                }
                var before = areas.Count;
                foreach (PlanCircuit c in circuits)
                {
                    var inside = c.GetPointInside();
                    areas.Add(new EnclosedArea(level.Name, c.Area, c.IsRoomLocated,
                                               new Xyz(inside.U, inside.V, level.ProjectElevation)));
                }
                diagnostics.Add($"enclosed areas on {level.Name}: {areas.Count - before} " +
                                $"({areas.Skip(before).Count(a => !a.HasRoom)} with no Room)");
            }
            return areas;
        }
        finally
        {
            if (t is not null)
            {
                t.RollBack();
                t.Dispose();
            }
        }
    }

    private static List<InteriorLink> Links(Document doc)
    {
        var links = new List<InteriorLink>();
        foreach (var li in new FilteredElementCollector(doc).OfClass(typeof(RevitLinkInstance)).Cast<RevitLinkInstance>())
        {
            var type = doc.GetElement(li.GetTypeId()) as RevitLinkType;
            var linked = li.GetLinkDocument();
            var loaded = linked is not null && type?.GetLinkedFileStatus() == LinkedFileStatus.Loaded;
            var box = li.get_BoundingBox(null);
            int Count(params BuiltInCategory[] cats) => linked is null ? 0
                : cats.Sum(c => new FilteredElementCollector(linked).OfCategory(c).WhereElementIsNotElementType().GetElementCount());
            links.Add(new InteriorLink(li.UniqueId, li.Name, loaded,
                                       box is null ? null : new RevitBox(P(box.Min), P(box.Max), box.Transform is { } bt ? T(bt) : null),
                                       Count(BuiltInCategory.OST_Rooms), Count(BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors),
                                       linked is not null && new FilteredElementCollector(linked).OfClass(typeof(RevitLinkInstance)).GetElementCount() > 0));
        }
        return links;
    }

    // ---- a room -------------------------------------------------------------------------------------------------

    private static RoomRecord RoomOf(Document doc, Room room)
    {
        var level = room.Level;
        IList<IList<BoundarySegment>>? loops = null;
        try
        {
            loops = room.GetBoundarySegments(new SpatialElementBoundaryOptions
            {
                SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish,
            });
        }
        catch (Autodesk.Revit.Exceptions.ApplicationException)
        {
        }
        var boundary = loops?.Select(loop => (IReadOnlyList<BoundarySegmentRecord>)loop.Select(s =>
        {
            var c = s.GetCurve();
            var by = s.ElementId == ElementId.InvalidElementId || s.LinkElementId != ElementId.InvalidElementId
                ? null : doc.GetElement(s.ElementId)?.UniqueId;
            return new BoundarySegmentRecord(P(c.GetEndPoint(0)), P(c.GetEndPoint(1)), c is Line, by);
        }).ToList()).ToList();
        double? elevation = level?.ProjectElevation;
        double? offset = room.Location is null ? null : room.BaseOffset;
        var record = new RoomRecord
        {
            UniqueId = room.UniqueId,
            Level = level?.Name,
            LevelElevation = elevation,
            BaseOffset = offset,
            Boundary = boundary,
        };
        if (boundary is not { Count: > 0 } || elevation is null || offset is null || loops is null)
            return record;
        var floor = elevation.Value + offset.Value;
        var outer = loops[0];
        var xs = outer.SelectMany(s => new[] { s.GetCurve().GetEndPoint(0), s.GetCurve().GetEndPoint(1) }).ToList();
        double x0 = xs.Min(p => p.X), y0 = xs.Min(p => p.Y), x1 = xs.Max(p => p.X), y1 = xs.Max(p => p.Y);
        return record with
        {
            Inside = Inside(doc, room, loops, floor, level!),
            Under = Near(doc, room, new Outline(new XYZ(x0, y0, floor - InteriorReader.SlabBand), new XYZ(x1, y1, floor + InteriorReader.SlabBand)),
                         [BuiltInCategory.OST_Floors, BuiltInCategory.OST_StructuralFoundation]),
            Over = Near(doc, room, new Outline(new XYZ(x0, y0, floor), new XYZ(x1, y1, floor + 1000)), null),
        };
    }

    /// <summary>What crosses the room's plan from just above its floor to just below its level's room computation
    /// height (<c>LEVEL_ROOM_COMPUTATION_HEIGHT</c>, where Revit works out room outlines): every outline loop extruded,
    /// and each element whose solid meets it (<c>ElementIntersectsSolidFilter</c>). Null when it can't be looked for.</summary>
    private static List<NearbyElement>? Inside(Document doc, Room room, IList<IList<BoundarySegment>> loops, double floor, Level level)
    {
        try
        {
            var height = level.get_Parameter(BuiltInParameter.LEVEL_ROOM_COMPUTATION_HEIGHT)?.AsDouble() ?? 4.0;
            var top = Math.Max(height - Sixteenth, 2 * Sixteenth);
            var profile = new List<CurveLoop>();
            var lift = Transform.CreateTranslation(new XYZ(0, 0, floor + Sixteenth - loops[0][0].GetCurve().GetEndPoint(0).Z));
            foreach (var loop in loops)
            {
                var curveLoop = new CurveLoop();
                foreach (var s in loop)
                    curveLoop.Append(s.GetCurve().CreateTransformed(lift));
                profile.Add(curveLoop);
            }
            var solid = GeometryCreationUtilities.CreateExtrusionGeometry(profile, XYZ.BasisZ, top - Sixteenth);
            return new FilteredElementCollector(doc).WhereElementIsNotElementType()
                .WherePasses(new ElementIntersectsSolidFilter(solid))
                .Where(e => e.Id != room.Id)
                .Select(e => new NearbyElement(e.UniqueId, Category(e), e.Name, (e as FamilyInstance)?.Host?.UniqueId))
                .ToList();
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return null;
        }
    }

    /// <summary>The model elements (not view-specific) whose box meets <paramref name="box"/>, of the categories given
    /// (any for null), with their faces.</summary>
    private static List<NearbyElement>? Near(Document doc, Room room, Outline box, BuiltInCategory[]? categories)
    {
        try
        {
            var options = new Options { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };
            var found = new FilteredElementCollector(doc).WhereElementIsNotElementType().WherePasses(new BoundingBoxIntersectsFilter(box));
            var list = new List<NearbyElement>();
            foreach (var e in found)
            {
                if (e.Id == room.Id || e.ViewSpecific || e.Category is not { CategoryType: Autodesk.Revit.DB.CategoryType.Model } cat)
                    continue;
                if (categories is not null && !categories.Contains(cat.BuiltInCategory))
                    continue;
                var (faces, failed) = Faces(e, options);
                list.Add(new NearbyElement(e.UniqueId, cat.BuiltInCategory.ToString(), e.Name, (e as FamilyInstance)?.Host?.UniqueId,
                                           faces, failed));
            }
            return list;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException)
        {
            return null;
        }
    }

    private static string Category(Element e) => e.Category is { } c ? c.BuiltInCategory.ToString() : "";

    /// <summary>Every face of the element's solids (a family's instance geometry included), and whether anything in its
    /// geometry couldn't be read as faces (a mesh, or <c>get_Geometry</c> throwing).</summary>
    private static (List<SurfaceRecord>? Faces, bool Failed) Faces(Element e, Options options)
    {
        var faces = new List<SurfaceRecord>();
        var failed = false;
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                switch (o)
                {
                    case Solid s:
                        foreach (Face f in s.Faces)
                            faces.Add(Surface(f));
                        break;
                    case GeometryInstance gi when gi.GetInstanceGeometry() is { } inner:
                        Walk(inner);
                        break;
                    case Mesh:
                        failed = true;               // a mesh over a room isn't read exactly
                        break;
                }
            }
        }
        try
        {
            if (e.get_Geometry(options) is { } g)
                Walk(g);
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return (null, true);
        }
        return (faces, failed);
    }

    private static SurfaceRecord Surface(Face f)
    {
        var loops = f.GetEdgesAsCurveLoops()
            .Select(l => (IReadOnlyList<LoopCurve>)l.Select(c => new LoopCurve(P(c.GetEndPoint(0)), c is Line)).ToList()).ToList();
        if (f is PlanarFace pf)
            return new SurfaceRecord(true, P(pf.FaceNormal), loops, loops.SelectMany(l => l.Select(c => c.Start)).ToList());
        return new SurfaceRecord(false, new Xyz(0, 0, 0), loops, f.Triangulate().Vertices.Select(P).ToList());
    }

    // ---- a window or door ---------------------------------------------------------------------------------------

    private static OpeningRecord OpeningOf(Document doc, FamilyInstance fi, Phase? phase)
    {
        var type = doc.GetElement(fi.GetTypeId());
        var level = doc.GetElement(fi.LevelId) as Level;
        var (width, height) = TypeSize(type);
        var options = new Options { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };
        var (faces, failed) = Faces(fi, options);
        var cut = fi.Host is Wall wall ? Cut(wall, fi, options) : (null, null, ["its host isn't a wall"]);
        return new OpeningRecord
        {
            UniqueId = fi.UniqueId,
            FromRoom = phase is null ? null : fi.get_FromRoom(phase)?.UniqueId,
            ToRoom = phase is null ? null : fi.get_ToRoom(phase)?.UniqueId,
            Host = fi.Host?.UniqueId,
            HostIsWall = fi.Host is Wall,
            LevelElevation = level?.ProjectElevation,
            SillHeight = fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM) is { HasValue: true } s ? s.AsDouble() : null,
            Location = fi.Location is LocationPoint lp ? P(lp.Point) : null,
            Along = P(fi.HandOrientation),
            TypeWidth = width,
            TypeHeight = height,
            TypeLengths = type is null ? new Dictionary<string, double>() : Lengths(type),
            Placed = failed || faces is null || faces.Count == 0 ? null : faces.SelectMany(f => f.Points).ToList(),
            WallOpening = cut.Points,
            WallOpeningBy = cut.By,
            Diagnostics = cut.Words,
        };
    }

    /// <summary>A window or door type's own Width and Height, or null where it has none.</summary>
    internal static (double? Width, double? Height) TypeSize(Element? type)
    {
        double? Get(params BuiltInParameter[] ps)
        {
            foreach (var p in ps)
                if (type?.get_Parameter(p) is { HasValue: true, StorageType: StorageType.Double } v)
                    return v.AsDouble();
            return null;
        }
        return (Get(BuiltInParameter.WINDOW_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM),
                Get(BuiltInParameter.WINDOW_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM));
    }

    /// <summary>Every length parameter on the type, by name (the first of a name only).</summary>
    private static Dictionary<string, double> Lengths(Element type)
    {
        var lengths = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (Parameter p in type.Parameters)
            if (p.HasValue && p.StorageType == StorageType.Double && p.Definition is { } d && d.GetDataType() == SpecTypeId.Length)
                lengths.TryAdd(d.Name, p.AsDouble());
        return lengths;
    }

    /// <summary>The points of the faces of the host wall that this window or door cut (the faces whose
    /// <c>Element.GetGeneratingElementIds</c> name it: shown to work on houses 1, 2 and 5 in Revit 2027.4, trial run 6),
    /// how they were found, and what was looked at (the boxes and the ids generating the wall's faces, for a future
    /// failure's log). Never the window's own geometry or its Sill Height; nothing found is none.</summary>
    private static (List<Xyz>? Points, string? By, List<string> Words) Cut(Wall wall, FamilyInstance fi, Options options)
    {
        var words = new List<string>();
        var faces = new List<(Face Face, List<Xyz> Points, ICollection<ElementId> By)>();
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                if (o is Solid s)
                {
                    foreach (Face f in s.Faces)
                        faces.Add((f, f.GetEdgesAsCurveLoops().SelectMany(l => l.Select(c => P(c.GetEndPoint(0)))).ToList(),
                                   wall.GetGeneratingElementIds(f)));
                }
                else if (o is GeometryInstance gi && gi.GetInstanceGeometry() is { } inner)
                    Walk(inner);
            }
        }
        try
        {
            if (wall.get_Geometry(options) is { } g)
                Walk(g);
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException)
        {
            words.Add($"the wall's geometry couldn't be read ({x.GetType().Name}: {x.Message})");
            return (null, null, words);
        }
        var fb = fi.get_BoundingBox(null);
        var wb = wall.get_BoundingBox(null);
        words.Add($"window box z {fb?.Min.Z:0.####}..{fb?.Max.Z:0.####}, wall box z {wb?.Min.Z:0.####}..{wb?.Max.Z:0.####} (internal ft), " +
                  $"family placement {fi.Symbol?.Family?.FamilyPlacementType}");
        words.Add($"host (FamilyInstance.Host) {fi.Host?.Id.Value}, wall {wall.Id.Value} {wall.UniqueId}: {faces.Count} faces; ids generating them: " + string.Join(", ",
            faces.SelectMany(f => f.By).Distinct().Select(id => wall.Document.GetElement(id) is { } e
                ? $"{e.Category?.BuiltInCategory.ToString() ?? "?"} {id.Value}{(id == fi.Id ? " (this window)" : "")}" : $"{id.Value}")));
        var named = faces.Where(f => f.By.Contains(fi.Id)).SelectMany(f => f.Points).ToList();
        if (named.Count > 0)
            return (named, "the wall's faces Revit says this window generated (GetGeneratingElementIds)", words);
        // nothing else stands in for it: HostObject.FindInserts listed no inserts at all even on walls the windows did
        // cut (trial run 6, Revit 2027.4), so it is no evidence either way and isn't used
        words.Add("no face of the wall names this window as generating it: the window cut nothing found");
        return (null, null, words);
    }

    internal static Xyz P(XYZ p) => new(p.X, p.Y, p.Z);

    private static Reading.Transform3 T(Transform t) => new(P(t.Origin), P(t.BasisX), P(t.BasisY), P(t.BasisZ));
}
