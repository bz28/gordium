namespace Gordium.Revit.Reading;

// What the Revit layer reads from a model, as plain records: nothing here is a Revit type, so the reader's decisions
// (SiteReader) are built and tested on the Mac. The Revit layer (Windows, later) fills each record from the API
// named beside it, and decides nothing: it copies what Revit says. Every point is in Revit's internal coordinates
// and internal units (feet), exactly as the API gives it; the reader alone turns it into shared coordinates
// (RevitModel.InternalToShared). Where the API name is marked "to check", the Windows trial confirms that it gives
// what the record says (docs/revit/revit_reading_design.md, section 8).

/// <summary>One open Revit document (or a linked model's document, <see cref="RevitLink.Document"/>).</summary>
public sealed record RevitModel
{
    /// <summary>The file's name (<c>Document.Title</c>), for the description's <c>host.document</c>.</summary>
    public required string Document { get; init; }

    /// <summary>Revit's version (<c>Application.VersionNumber</c>), for <c>host.version</c>.</summary>
    public string Version { get; init; } = "";

    /// <summary>The project's length display unit (<c>Units.GetFormatOptions(SpecTypeId.Length).GetUnitTypeId()</c>),
    /// named for tracing only (<c>host.model_units</c>): Revit's internal unit is the foot whatever this says, so no
    /// point is ever converted.</summary>
    public string DisplayUnits { get; init; } = "Feet";

    /// <summary>How near two curve ends must be to count as joined (<c>Application.VertexTolerance</c>, feet).</summary>
    public double VertexTolerance { get; init; } = 0.0005233;

    /// <summary>Internal coordinates to the project's shared (survey) coordinates:
    /// <c>ActiveProjectLocation.GetTotalTransform()</c>, or its inverse (which way round is to check). Identity for a
    /// model with no shared coordinates set. Ignored for a linked model's document (its placement in the host is
    /// <see cref="RevitLink.Transform"/>).</summary>
    public Transform3 InternalToShared { get; init; } = Transform3.Identity;

    /// <summary>The document's phases in order, first to last (<c>Document.Phases</c>), by id.</summary>
    public IReadOnlyList<string> Phases { get; init; } = [];

    /// <summary>Every design option set (<c>DesignOption</c> elements grouped by their set).</summary>
    public IReadOnlyList<OptionSet> OptionSets { get; init; } = [];

    /// <summary>The option being edited (<c>DesignOption.GetActiveDesignOptionId</c>), or null for the main model.</summary>
    public string? ActiveOption { get; init; }

    /// <summary>The user worksets (<c>FilteredWorksetCollector</c>, <c>WorksetKind.UserWorkset</c>); empty when the
    /// model isn't workshared.</summary>
    public IReadOnlyList<WorksetRecord> UserWorksets { get; init; } = [];

    /// <summary>Every element of the document (<c>FilteredElementCollector(doc).WhereElementIsNotElementType()</c>),
    /// never a view's: hidden, isolated or cropped elements count. Property lines and picked lines go in
    /// <see cref="LotLines"/> too.</summary>
    public IReadOnlyList<RevitElement> Elements { get; init; } = [];

    /// <summary>Every element that can be a lot line: each property line, and each model line the architect could
    /// pick (<c>CurveElement</c>), with its curves.</summary>
    public IReadOnlyList<LotLineElement> LotLines { get; init; } = [];
}

public sealed record OptionSet(string Id, string Name, IReadOnlyList<DesignOptionRecord> Options);

/// <summary>A design option (<c>DesignOption.IsPrimary</c>).</summary>
public sealed record DesignOptionRecord(string Id, string Name, bool IsPrimary);

/// <summary>A user workset (<c>Workset.IsOpen</c>).</summary>
public sealed record WorksetRecord(string Id, string Name, bool IsOpen);

/// <summary>What the element is, as far as the reader's sorting needs.</summary>
public enum ElementKind
{
    /// <summary>A system family element (a wall, a floor), a DirectShape, any other element.</summary>
    Ordinary,

    /// <summary>A <c>FamilyInstance</c>, loadable or in-place (<see cref="RevitElement.IsInPlace"/>).</summary>
    FamilyInstance,

    /// <summary>A model group (<c>Group</c>): never read itself, its members are their own elements.</summary>
    Group,

    /// <summary>A curtain wall's host wall (<c>Wall.CurtainGrid</c> not null): its panels and mullions are their own
    /// elements; it sends its own faces only if it has any.</summary>
    CurtainWallHost,

    /// <summary>A 3D CAD import (<c>ImportInstance</c>, not view-specific).</summary>
    CadImport,

    /// <summary>A <c>Toposolid</c>.</summary>
    Toposolid,

    /// <summary>A linked Revit model (<c>RevitLinkInstance</c>), with <see cref="RevitElement.Link"/>.</summary>
    LinkInstance,

    /// <summary>A coordination model (Navisworks, <c>CoordinationModelLinkUtils.IsCoordinationModelInstance</c>,
    /// Revit 2024 and later): drawn for show only, so Revit gives no geometry for it, yet it may hold a building.
    /// Left out as a linked model whose contents aren't known, wherever it stands.</summary>
    CoordinationModel,
}

/// <summary>Gordium's own marks on an element (proposed: a DirectShape carrying a Gordium parameter, as Rhino's
/// user text and layers).</summary>
public enum GordiumMark
{
    None,

    /// <summary>A floor block <c>start_site</c> drew; <see cref="RevitElement.FloorMark"/> holds "&lt;story&gt;;&lt;height&gt;".</summary>
    FloorBlock,

    /// <summary>One of the neighbourhood's objects (as Rhino's Gordium::Context layer).</summary>
    Context,

    /// <summary>A spot-grade marker (as a point on Rhino's Gordium::Grade), read at <see cref="RevitElement.Location"/>.</summary>
    SpotGrade,

    /// <summary>A finished-grade marker (as Gordium::Grade::Finished).</summary>
    FinishedGrade,
}

public enum CategoryType { Model, Annotation, Internal, AnalyticalModel }

/// <summary>One element.</summary>
public sealed record RevitElement
{
    /// <summary><c>Element.UniqueId</c>: the id the description sends.</summary>
    public required string UniqueId { get; init; }

    /// <summary>The category's built-in name (<c>BuiltInCategory</c>, such as <c>OST_Walls</c>): the reader sorts by
    /// it, never by the display name, which changes with Revit's language. Empty for an element with no category.</summary>
    public required string BuiltInCategory { get; init; }

    /// <summary>The category's display name (<c>Category.Name</c>, such as "Walls"): the description's <c>layer</c>,
    /// for the architect's reading only.</summary>
    public required string Category { get; init; }

    /// <summary><c>Category.CategoryType</c>. Only model elements are looked at, but a linked model and a CAD import
    /// whatever it says (whether "RVT Links" is a model category is to check).</summary>
    public CategoryType CategoryType { get; init; } = CategoryType.Model;

    /// <summary><c>Element.ViewSpecific</c>: drawn in one view only (a 2D CAD import, a detail): not looked at.</summary>
    public bool ViewSpecific { get; init; }

    /// <summary><c>Element.Name</c>, for <c>open_solid</c>'s words.</summary>
    public string? Name { get; init; }

    public ElementKind Kind { get; init; } = ElementKind.Ordinary;

    /// <summary><c>Family.IsInPlace</c>: only names it; an in-place family is sorted by its category like any other.</summary>
    public bool IsInPlace { get; init; }

    public GordiumMark Mark { get; init; } = GordiumMark.None;

    /// <summary>A floor block's mark, "&lt;story&gt;;&lt;height drawn, ft&gt;" (as Rhino's <c>gordium:floor</c>).</summary>
    public string? FloorMark { get; init; }

    /// <summary><c>Element.CreatedPhaseId</c>, or null when the element has no phase.</summary>
    public string? PhaseCreated { get; init; }

    /// <summary><c>Element.DemolishedPhaseId</c>, or null when it isn't demolished.</summary>
    public string? PhaseDemolished { get; init; }

    /// <summary><c>Element.DesignOption</c>'s id, or null for the main model.</summary>
    public string? DesignOption { get; init; }

    /// <summary><c>Element.WorksetId</c>, or null.</summary>
    public string? Workset { get; init; }

    /// <summary>Revit's own box, <c>Element.get_BoundingBox(null)</c>, or null when it gives none.</summary>
    public RevitBox? BoundingBox { get; init; }

    /// <summary><c>Element.get_Geometry(new Options { DetailLevel = Fine })</c>, no view, a family's
    /// <c>GeometryInstance</c> kept as one (<see cref="InstanceItem"/>) with its <c>GetInstanceGeometry()</c>; null
    /// when it returned null. Ignored when <see cref="GeometryFailed"/>.</summary>
    public IReadOnlyList<GeometryItem>? Geometry { get; init; }

    /// <summary><c>get_Geometry</c> threw.</summary>
    public bool GeometryFailed { get; init; }

    /// <summary>A grade marker's point (<c>LocationPoint.Point</c>).</summary>
    public Xyz? Location { get; init; }

    /// <summary>For a linked model.</summary>
    public RevitLink? Link { get; init; }
}

/// <summary><c>BoundingBoxXYZ</c>: its corners in its own <c>Transform</c>.</summary>
public sealed record RevitBox(Xyz Min, Xyz Max, Transform3? Transform = null);

/// <summary>A linked Revit model, <c>RevitLinkInstance</c>.</summary>
/// <param name="Status">The link's <c>LinkedFileStatus</c> by name (<c>RevitLinkType.GetLinkedFileStatus()</c>):
/// only "Loaded" says its contents are known. A link nested as an overlay is not loaded in the host (to check).</param>
/// <param name="Transform">Where the linked model is placed (<c>GetTotalTransform()</c>): its internal coordinates
/// to the host's internal coordinates.</param>
/// <param name="Document">The linked document (<c>GetLinkDocument()</c>), null when not loaded.</param>
public sealed record RevitLink(string Status, Transform3 Transform, RevitModel? Document);

/// <summary>One piece of an element's geometry.</summary>
public abstract record GeometryItem;

/// <summary>A <c>Solid</c>: its faces and its edges.</summary>
public sealed record SolidItem(IReadOnlyList<FaceRecord> Faces, IReadOnlyList<EdgeRecord> Edges) : GeometryItem;

/// <summary>A <c>Face</c>.</summary>
/// <param name="Type">The face's class name: <c>PlanarFace</c>, <c>CylindricalFace</c>, <c>ConicalFace</c>,
/// <c>RuledFace</c>, <c>RevolvedFace</c>, <c>HermiteFace</c>. Only a PlanarFace can be sent.</param>
/// <param name="Loops"><c>GetEdgesAsCurveLoops()</c>: each loop's curves in order.</param>
/// <param name="Samples">A 7 × 7 grid of points over the face (<c>Face.Evaluate</c> over its own range: to
/// check), used only to tell where it stands in plan, never sent as a face.</param>
public sealed record FaceRecord(string Type, IReadOnlyList<IReadOnlyList<LoopCurve>> Loops, IReadOnlyList<Xyz> Samples);

/// <summary>One curve of a face's loop: its start point, and whether it is a <c>Line</c>.</summary>
public sealed record LoopCurve(Xyz Start, bool IsLine);

/// <summary>An <c>Edge</c>: points along it (<c>Edge.Tessellate()</c>) and whether it has a second face
/// (<c>Edge.GetFace(1)</c> not null: to check that an open shell gives null).</summary>
public sealed record EdgeRecord(IReadOnlyList<Xyz> Along, bool HasSecondFace);

/// <summary>A <c>Mesh</c>: its vertices and triangles; <paramref name="IsClosed"/> null when Revit can't say (to check).</summary>
public sealed record MeshItem(IReadOnlyList<Xyz> Vertices, IReadOnlyList<(int A, int B, int C)> Triangles, bool? IsClosed) : GeometryItem;

/// <summary>A curve or a point in the geometry: never a building, skipped.</summary>
public sealed record LineworkItem : GeometryItem;

/// <summary>A <c>GeometryInstance</c> (a nested family): <c>GetInstanceGeometry()</c>, already placed; null when it
/// gives nothing.</summary>
public sealed record InstanceItem(IReadOnlyList<GeometryItem>? Items) : GeometryItem;

/// <summary>Any other geometry object (not a solid, mesh, curve, point or instance), by its class name.</summary>
public sealed record OtherItem(string TypeName) : GeometryItem;

/// <summary>An element that can be a lot line: a property line (<c>PropertyLine</c>: its curves from
/// <c>GetBoundary()</c> in Revit 2027, from its geometry in 2026, to check) or a model line.</summary>
public sealed record LotLineElement(string UniqueId, bool IsPropertyLine, IReadOnlyList<LotCurve> Curves);

/// <summary>One curve of a lot line: its ends; whether it is a <c>Line</c>; its length (<c>Curve.Length</c>); and,
/// for any other curve, a point at a normalised parameter 0..1 (<c>Curve.Evaluate(t, true)</c>).</summary>
public sealed record LotCurve(Xyz Start, Xyz End, bool IsLine, double Length = 0, Func<double, Xyz>? PointAt = null);
