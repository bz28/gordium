namespace Gordium.Revit.Reading;

// What the Revit layer reads from a model for the house's inside (docs/revit/revit_interior_reading_design.md,
// sections 2 and 4; section 7, step 3: rooms and marked escape windows), as plain records: nothing here is a Revit
// type, so the interior reader's decisions (InteriorReader) are built and tested without Revit. The Revit layer
// (Gordium.Revit.Addin/RevitInterior.cs) fills each record from the API named beside it and decides nothing. Every
// point is in Revit's internal coordinates and feet, as the API gives it; the reader alone turns it into shared
// coordinates (RevitModel.InternalToShared). The marks themselves are RevitModel.Marked's (step 2).

/// <summary>Everything the interior reader needs beyond the marks.</summary>
public sealed record InteriorRecords
{
    /// <summary>One record per Room the marks list (<see cref="RevitModel.Marked"/>), by <c>UniqueId</c>.</summary>
    public IReadOnlyList<RoomRecord> Rooms { get; init; } = [];

    /// <summary>One record per window and door the marks list, by <c>UniqueId</c>.</summary>
    public IReadOnlyList<OpeningRecord> Openings { get; init; } = [];

    /// <summary>Every enclosed area on every level, for the last phase (<c>Document.get_PlanTopology(level, phase)
    /// .Circuits</c>): an area with no Room in it may be a bedroom nobody placed a Room in (design note, section 2).
    /// Null when the Revit layer couldn't read them: then no room can be read.</summary>
    public IReadOnlyList<EnclosedArea>? EnclosedAreas { get; init; }

    /// <summary>Every linked Revit model (<c>RevitLinkInstance</c>).</summary>
    public IReadOnlyList<InteriorLink> Links { get; init; } = [];

    /// <summary>Every <c>Stairs</c> element (<c>OfCategory(OST_Stairs)</c>, the <c>Stairs</c> class), with its runs
    /// (step 4). Null when the Revit layer didn't read them: then no stair is read.</summary>
    public IReadOnlyList<StairRecord>? Stairs { get; init; }

    /// <summary>Everything else that could be a stair the reader doesn't walk (design note, section 2): any element in
    /// Stairs, Railings or Generic Models that isn't a <c>Stairs</c> or a <c>Railing</c> (an in-place family, a loadable
    /// family, a DirectShape), and every <c>MultistoryStairs</c>. While any is in the design checked, no stair is read.</summary>
    public IReadOnlyList<StairCandidate> StairCandidates { get; init; } = [];

    /// <summary>Every <c>Railing</c> (step 5: <c>OfCategory(OST_StairsRailing)</c>, the <c>Railing</c> class), with its
    /// parts and what is around it: a stair's handrails and the guards are read from them. Null when the Revit layer
    /// didn't read them: then no guard and no handrail is read.</summary>
    public IReadOnlyList<RailingRecord>? Railings { get; init; }

    /// <summary>Every element in Ramps (<c>OfCategory(OST_Ramps)</c>, step 6): a ramp drawn contradicts the architect's
    /// "this house has no ramps". Null when the Revit layer didn't read them: then that tick isn't sent.</summary>
    public IReadOnlyList<RampRecord>? Ramps { get; init; }

    /// <summary>How many coordination models are linked (<c>CoordinationModelLinkUtils.GetAllCoordinationModelInstanceIds</c>):
    /// what is in one isn't read, and a stair could be in it.</summary>
    public int CoordinationModels { get; init; }

    /// <summary>Every level (<c>OfClass(typeof(Level))</c>), for the stories of the escape routes (section 10). Null when
    /// the Revit layer didn't read them: then no <c>levels</c> are sent, and no story's routes are measured.</summary>
    public IReadOnlyList<LevelRecord>? Levels { get; init; }

    /// <summary>Every room separation line (<c>OfCategory(OST_RoomSeparationLines)</c>), by <c>UniqueId</c>: a room
    /// boundary segment drawn by one is where two rooms meet with no wall (a passage, section 10). Null when the Revit
    /// layer didn't read them: then no <c>passages</c> are sent, and no story's routes are measured.</summary>
    public IReadOnlyList<string>? SeparationLines { get; init; }

    /// <summary>Each level's gross building area (<see cref="GrossArea"/>), by the level's <c>UniqueId</c>, for the story's
    /// outlines (section 10). Null when the Revit layer didn't read them: then no outline is sent.</summary>
    public IReadOnlyDictionary<string, GrossArea>? GrossAreas { get; init; }

    /// <summary>Every ground the model draws (<see cref="GroundRecord"/>): each <c>Toposolid</c> and each older
    /// <c>TopographySurface</c>, in any phase or design option (the reader keeps the design checked's). The ground at
    /// each window is read from them (<see cref="GroundReader"/>). Null when the Revit layer didn't read them:
    /// then no ground is read, as with none drawn.</summary>
    public IReadOnlyList<GroundRecord>? Grounds { get; init; }

    /// <summary>What the Revit layer looked at and what Revit said (each level's enclosed areas, an error), for the
    /// trial's log only: never read by a decision.</summary>
    public IReadOnlyList<string> Diagnostics { get; init; } = [];
}

/// <summary>A ground drawn in the model: a <c>Toposolid</c> (Revit 2024 and later) or an older
/// <c>TopographySurface</c>, as triangles (internal coordinates, feet): a Toposolid's every face (<c>get_Geometry</c>,
/// Fine: its solids' faces, <c>Face.Triangulate()</c>), a topography surface's mesh (<c>Mesh.get_Triangle</c>). The
/// ground at a plan point is the highest of its triangles over it.</summary>
/// <param name="UniqueId"><c>Element.UniqueId</c>.</param>
/// <param name="Kind">"Toposolid" or "TopographySurface", for the words.</param>
/// <param name="Name">Its type's name, for the words.</param>
/// <param name="Triangles">Its triangles, or null when its geometry couldn't be read (a face Revit gave no triangles
/// for, <c>get_Geometry</c> refused, or a piece of another kind): then no ground is read from the model.</param>
/// <param name="PhaseDemolished"><c>Element.DemolishedPhaseId</c>.</param>
/// <param name="DesignOption"><c>Element.DesignOption</c>'s id.</param>
/// <param name="Host">A Toposolid subdivision's host Toposolid (<c>Toposolid.HostTopoId</c>), by <c>UniqueId</c>, or
/// null: a subdivision lies on its host (a path, a lawn), so over it the subdivision's top is the ground.</param>
/// <param name="PhaseCreated"><c>Element.CreatedPhaseId</c>, or null: the phases may show which ground is the
/// finished one (<see cref="GroundReader.PhasesShow"/>).</param>
public sealed record GroundRecord(string UniqueId, string Kind, string? Name, IReadOnlyList<GroundTriangle>? Triangles,
                                  string? PhaseDemolished = null, string? DesignOption = null, string? Host = null,
                                  string? PhaseCreated = null);

/// <summary>A triangle of a ground's surface, its three corners (internal coordinates, feet).</summary>
public sealed record GroundTriangle(Xyz A, Xyz B, Xyz C);

/// <summary>A level's building outline, the exterior walls' outer faces as Revit's room logic gives them (section 10):
/// room separation lines drawn as a rectangle 20 ft round the level's walls, a Room placed in the ring, its boundary at
/// the finished faces read (<c>GetBoundarySegments</c>: each loop's segments and the element bounding each, by
/// <c>UniqueId</c>), the rectangle's loop dropped, all rolled back. <see cref="WallWidths"/>: each bounding wall's full
/// thickness (<c>Wall.Width</c>). <see cref="Why"/>: why there is none (the ring Room not enclosed, Revit refused).</summary>
public sealed record GrossArea(IReadOnlyList<IReadOnlyList<BoundarySegmentRecord>>? Loops, IReadOnlyDictionary<string, double> WallWidths,
                               string? Why = null);

/// <summary>A level (<c>Level</c>): its <c>UniqueId</c>, <c>Name</c> and <c>ProjectElevation</c> (internal).</summary>
public sealed record LevelRecord(string UniqueId, string Name, double Elevation);

/// <summary>A planar side face of a door's host wall (<c>HostObjectUtils.GetSideFaces</c>, exterior and interior), as a
/// plane: a point on it (<c>PlanarFace.Origin</c>) and its normal (<c>FaceNormal</c>), internal. The room boundary at
/// the finished faces runs along these, so the door's place in the middle of its wall is read from them.</summary>
public sealed record WallFace(Xyz Point, Xyz Normal);

/// <summary>An enclosed area on a level (a <c>PlanCircuit</c>).</summary>
/// <param name="Level">The level's name (<c>Level.Name</c>), for the words.</param>
/// <param name="Area">Its area (<c>PlanCircuit.Area</c>, sq ft).</param>
/// <param name="HasRoom"><c>PlanCircuit.IsRoomLocated</c>.</param>
/// <param name="PointInside"><c>PlanCircuit.GetPointInside()</c> at the level's elevation (internal): for the words,
/// and to find a Room of the design checked it lies in (a Room in a design option Revit's main-model circuits don't
/// count, <see cref="InteriorReader.UnknownAreas"/>). Null when Revit can't give one (a sliver between overlapping
/// walls: the Children's Odyssey model, 2026-11-20, threw "Could not obtain valid UV point"): such an area lies in
/// no Room, so with no Room of its own it stays a space whose use isn't known, never dropped, never a crash.</param>
/// <param name="LevelId">The level's <c>UniqueId</c>: its "no rooms on this level" mark, and the rooms on it.</param>
/// <param name="Outline">For an area with no Room: its outline (the outer boundary loop, at the finished faces, of a Room
/// the Revit layer places in it for the moment and takes back, <c>SubTransaction</c> rolled back), each segment's start,
/// internal; null when it couldn't be read (Revit refused, a curved segment, a model it can't change): then a door
/// whose far side Revit gives no room on, on that level, can't be said to open to outside (escape routes, section 10).</param>
public sealed record EnclosedArea(string Level, double Area, bool HasRoom, Xyz? PointInside, string? LevelId = null,
                                  IReadOnlyList<Xyz>? Outline = null);

/// <summary>A linked Revit model, for the interior: whether its contents are known, where it reaches, and whether it
/// holds rooms, windows or doors (design note, section 4: a link's rooms or windows leave that kind not read; a loaded
/// link reaching a room's plan leaves that room's floor and ceilings out).</summary>
/// <param name="UniqueId">The link instance's <c>UniqueId</c>.</param>
/// <param name="Name">Its name, for the words.</param>
/// <param name="Loaded"><c>RevitLinkType.GetLinkedFileStatus()</c> is Loaded and <c>GetLinkDocument()</c> isn't null.</param>
/// <param name="Box">The link instance's box (<c>get_BoundingBox(null)</c>), or null when Revit gives none.</param>
/// <param name="Rooms">Rooms in the linked document (0 when not loaded: not known, see <paramref name="Loaded"/>).</param>
/// <param name="WindowsAndDoors">Windows and doors in it.</param>
/// <param name="HasLinks">The linked document holds links of its own (their contents aren't read).</param>
/// <param name="Stairs">Elements in the linked document's Stairs, Railings and Generic Models categories.</param>
/// <param name="Ramps">Elements in the linked document's Ramps category (step 6).</param>
public sealed record InteriorLink(string UniqueId, string Name, bool Loaded, RevitBox? Box, int Rooms, int WindowsAndDoors,
                                  bool HasLinks, int Stairs = 0, int Ramps = 0);

/// <summary>An element in Ramps (step 6), for the words and the design checked.</summary>
public sealed record RampRecord(string UniqueId, string? Name, string? PhaseDemolished = null, string? DesignOption = null);

/// <summary>A Room's own geometry and what stands in, under and over it.</summary>
public sealed record RoomRecord
{
    /// <summary><c>Room.UniqueId</c>.</summary>
    public required string UniqueId { get; init; }

    /// <summary>Its level's name (<c>Room.Level.Name</c>), for the words.</summary>
    public string? Level { get; init; }

    /// <summary>Its level's <c>UniqueId</c> (<c>Room.Level</c>), or null: a level marked "no rooms on this level"
    /// with a Room on it is a conflict, and an enclosed area lying in this room has it.</summary>
    public string? LevelId { get; init; }

    /// <summary>Its level's elevation in internal coordinates (<c>Room.Level.ProjectElevation</c>, to check), or null.</summary>
    public double? LevelElevation { get; init; }

    /// <summary><c>Room.BaseOffset</c>.</summary>
    public double? BaseOffset { get; init; }

    /// <summary>The room's boundary at the finished wall faces (<c>Room.GetBoundarySegments</c> with
    /// <c>SpatialElementBoundaryLocation.Finish</c>), each loop's segments in order; null when Revit gave none.</summary>
    public IReadOnlyList<IReadOnlyList<BoundarySegmentRecord>>? Boundary { get; init; }

    /// <summary>Every element whose solid crosses the room's plan from just above its floor to just below its level's
    /// computation height (<c>ElementIntersectsSolidFilter</c> with the boundary extruded): a wall, a column standing
    /// inside the room that doesn't bound it. Null when it couldn't be looked for.</summary>
    public IReadOnlyList<NearbyElement>? Inside { get; init; }

    /// <summary>The floors (<c>OST_Floors</c>, <c>OST_StructuralFoundation</c>) whose box reaches the room's plan within
    /// a foot of its floor, with their faces. Null when it couldn't be looked for.</summary>
    public IReadOnlyList<NearbyElement>? Under { get; init; }

    /// <summary>Every element whose box reaches over the room's plan above its floor, with its faces: what the ceilings
    /// are read from. Null when it couldn't be looked for.</summary>
    public IReadOnlyList<NearbyElement>? Over { get; init; }
}

/// <summary>One segment of a room's boundary (<c>BoundarySegment</c>): its ends, whether its curve is a <c>Line</c>,
/// and the element bounding it there (<c>BoundarySegment.ElementId</c>: a wall, a room separation line), by
/// <c>UniqueId</c> (null when none, or in a linked model).</summary>
public sealed record BoundarySegmentRecord(Xyz Start, Xyz End, bool IsLine, string? Element);

/// <summary>An element near a room: its category, what hosts it, and its faces (where asked).</summary>
/// <param name="UniqueId"><c>Element.UniqueId</c>.</param>
/// <param name="BuiltInCategory">Its category's built-in name (<c>OST_Walls</c>), empty for none.</param>
/// <param name="Name">For the words.</param>
/// <param name="Host">A family instance's host (<c>FamilyInstance.Host</c>), by <c>UniqueId</c>, or null.</param>
/// <param name="Faces">Its solids' faces (<c>get_Geometry</c>, Fine, a family's instance geometry included), or null
/// when not asked (<see cref="RoomRecord.Inside"/>).</param>
/// <param name="GeometryFailed"><c>get_Geometry</c> threw, gave something other than solids, meshes or curves, an
/// instance with no geometry, or held a face Revit gives no edges or triangles for.</param>
/// <param name="Box">Its box (<c>get_BoundingBox(null)</c>), internal, where asked (a flight's surroundings).</param>
/// <param name="PhaseDemolished"><c>Element.DemolishedPhaseId</c>, where asked.</param>
/// <param name="DesignOption"><c>Element.DesignOption</c>'s id, where asked.</param>
public sealed record NearbyElement(string UniqueId, string BuiltInCategory, string? Name = null, string? Host = null,
                                   IReadOnlyList<SurfaceRecord>? Faces = null, bool GeometryFailed = false,
                                   RevitBox? Box = null, string? PhaseDemolished = null, string? DesignOption = null)
{
    /// <summary>Over a room (<see cref="RoomRecord.Over"/>): the faces of what of the element lies in the room's band, from
    /// just above its floor to 80 in up (each of its solids intersected with that slab over the room's box,
    /// <c>BooleanOperationsUtils.ExecuteBooleanOperation</c>, Intersect; empty when none of it does). Null when not
    /// asked. The room's obstructions are read from these alone (escape routes, section 10).</summary>
    public IReadOnlyList<SurfaceRecord>? Banded { get; init; }

    /// <summary>The intersection couldn't be made (Revit refused, a mesh, a face it gives no edges for): what of the
    /// element is in the band isn't known.</summary>
    public bool BandFailed { get; init; }

    /// <summary>How many of its solids are open shells (faces with no volume: imported surfaces, a DirectShape from an
    /// open Brep) whose box reaches the band: Revit can't cut them, so what of the element is in the band isn't
    /// known (review round 4).</summary>
    public int OpenShells { get; init; }
}

/// <summary>Something in Stairs, Railings or Generic Models the reader doesn't walk as a stair.</summary>
/// <param name="UniqueId"><c>Element.UniqueId</c>.</param>
/// <param name="BuiltInCategory">Its category's built-in name.</param>
/// <param name="Name">For the words.</param>
/// <param name="PhaseDemolished"><c>Element.DemolishedPhaseId</c>.</param>
/// <param name="DesignOption"><c>Element.DesignOption</c>'s id.</param>
/// <param name="Kind">What Revit says it is, in the architect's words ("an in-place family", "a loadable family", "a
/// DirectShape", "a multistory stair", "a stair not made of components", "another element").</param>
/// <param name="Box">Its box (<c>get_BoundingBox(null)</c>), internal, or null when Revit gives none.</param>
/// <param name="NestedIn">For a family instance nested in another (a window's grille, a shared component), the
/// family instances it is nested in, innermost first (<c>FamilyInstance.SuperComponent</c>, to the top), each with
/// its category and box; empty when it isn't nested.</param>
/// <param name="InstanceMarks">Gordium's marks on the element itself (<c>Gordium: Not a stair</c>), by GUID.</param>
public sealed record StairCandidate(string UniqueId, string BuiltInCategory, string? Name, string Kind,
                                    string? PhaseDemolished = null, string? DesignOption = null, RevitBox? Box = null,
                                    IReadOnlyList<NestHost>? NestedIn = null,
                                    IReadOnlyDictionary<Guid, MarkValue>? InstanceMarks = null);

/// <summary>A family instance another is nested in (<c>FamilyInstance.SuperComponent</c>).</summary>
/// <param name="UniqueId"><c>Element.UniqueId</c>.</param>
/// <param name="BuiltInCategory">Its category's built-in name (<c>OST_Windows</c>).</param>
/// <param name="Box">Its box (<c>get_BoundingBox(null)</c>), internal, or null.</param>
public sealed record NestHost(string UniqueId, string BuiltInCategory, RevitBox? Box);

/// <summary>A component stair (<c>Stairs</c>), with each of its runs: one flight each (design note, section 4).</summary>
public sealed record StairRecord
{
    /// <summary><c>Element.UniqueId</c>.</summary>
    public required string UniqueId { get; init; }

    /// <summary>Its type's name and Mark, for the words.</summary>
    public string? Name { get; init; }

    /// <summary><c>Stairs.IsByComponent</c>: false for a stair sketched the old way (then no stair is read).</summary>
    public bool IsByComponent { get; init; }

    /// <summary><c>Stairs.MultistoryStairsId</c>'s id, or null: one of a multistory stair (then no stair is read).</summary>
    public string? MultistoryStairsId { get; init; }

    /// <summary>Gordium's marks on the stair itself, by GUID: <c>Gordium: Not a stair</c> Yes on one is a conflict.</summary>
    public IReadOnlyDictionary<Guid, MarkValue> InstanceMarks { get; init; } = new Dictionary<Guid, MarkValue>();

    public string? PhaseCreated { get; init; }
    public string? PhaseDemolished { get; init; }
    public string? DesignOption { get; init; }

    /// <summary><c>Stairs.BaseElevation</c>, internal: what each run's base and top elevations are relative to.</summary>
    public double? BaseElevation { get; init; }

    /// <summary>The typed values the drawn risers and treads are checked against: <c>Stairs.ActualRiserHeight</c>,
    /// <c>Stairs.ActualTreadDepth</c>.</summary>
    public double? ActualRiserHeight { get; init; }

    /// <inheritdoc cref="ActualRiserHeight"/>
    public double? ActualTreadDepth { get; init; }

    /// <summary>Its runs (<c>GetStairsRuns</c>), in Revit's order.</summary>
    public IReadOnlyList<RunRecord> Runs { get; init; } = [];

    /// <summary>Its own landings, supports and railings (<c>GetStairsLandings</c>, <c>GetStairsSupports</c>,
    /// <c>GetAssociatedRailings</c>), by <c>UniqueId</c>.</summary>
    public IReadOnlyList<string> Landings { get; init; } = [];

    /// <inheritdoc cref="Landings"/>
    public IReadOnlyList<string> Supports { get; init; } = [];

    /// <inheritdoc cref="Landings"/>
    public IReadOnlyList<string> Railings { get; init; } = [];
}

/// <summary>One run of a component stair (<c>StairsRun</c>): what its flight is read from, and what is around it.</summary>
public sealed record RunRecord
{
    /// <summary><c>Element.UniqueId</c>: the flight's id.</summary>
    public required string UniqueId { get; init; }

    /// <summary><c>StairsRun.StairsRunStyle</c> by name (<c>Straight</c>, <c>Winder</c>, <c>Spiral</c>, <c>Sketched</c>).</summary>
    public string Style { get; init; } = "";

    /// <summary><c>StairsRun.BaseElevation</c> and <c>TopElevation</c>: relative to the stair's base.</summary>
    public double? BaseElevation { get; init; }

    /// <inheritdoc cref="BaseElevation"/>
    public double? TopElevation { get; init; }

    /// <summary><c>StairsRun.ActualRisersNumber</c> and <c>ActualTreadsNumber</c>.</summary>
    public int? RisersNumber { get; init; }

    /// <inheritdoc cref="RisersNumber"/>
    public int? TreadsNumber { get; init; }

    /// <summary><c>StairsRun.BeginsWithRiser</c>, <c>EndsWithRiser</c>.</summary>
    public bool BeginsWithRiser { get; init; }

    /// <inheritdoc cref="BeginsWithRiser"/>
    public bool EndsWithRiser { get; init; }

    /// <summary>The run's path in plan (<c>GetStairsPath()</c>'s curves' ends, in order), internal: the direction up it.</summary>
    public IReadOnlyList<Xyz> Path { get; init; } = [];

    /// <summary>The run's own solids' faces (<c>get_Geometry</c>, Fine); null when it couldn't be read.</summary>
    public IReadOnlyList<SurfaceRecord>? Faces { get; init; }

    /// <summary>Its geometry held a mesh or a face Revit gives no edges or triangles for, or threw.</summary>
    public bool GeometryFailed { get; init; }

    /// <summary>Every model element whose box meets the run's box widened 2 ft in plan, from 2 ft under its base up
    /// (with its faces, box, phase and option): the floors at its foot and head, its sides, what is overhead. Null
    /// when it couldn't be looked for.</summary>
    public IReadOnlyList<NearbyElement>? Near { get; init; }

    /// <summary>What the Revit layer looked at (the faces found, the run's numbers), for the trial's log only.</summary>
    public IReadOnlyList<string> Diagnostics { get; init; } = [];
}

/// <summary>A railing (<c>Railing</c>, step 5): its path, its base, what hosts it, and each of its parts (the railing's
/// own geometry: balusters, posts and the rails that aren't continuous; its top rail; its handrails).</summary>
public sealed record RailingRecord
{
    /// <summary><c>Element.UniqueId</c>.</summary>
    public required string UniqueId { get; init; }

    /// <summary>Its type's name and Mark, for the words.</summary>
    public string? Name { get; init; }

    /// <summary>Its host (<c>Railing.HostId</c> when <c>HasHost</c>), by <c>UniqueId</c>, or null.</summary>
    public string? Host { get; init; }

    public string? PhaseDemolished { get; init; }
    public string? DesignOption { get; init; }

    /// <summary>Its path (<c>Railing.GetPath()</c>), each curve's ends and whether it is a <c>Line</c>, internal.</summary>
    public IReadOnlyList<PathCurve> Path { get; init; } = [];

    /// <summary>Its base level's elevation (<c>STAIRS_RAILING_BASE_LEVEL_PARAM</c>'s <c>Level.ProjectElevation</c>) and its
    /// base offset (<c>STAIRS_RAILING_HEIGHT_OFFSET</c>), or null.</summary>
    public double? BaseLevelElevation { get; init; }

    /// <inheritdoc cref="BaseLevelElevation"/>
    public double? BaseOffset { get; init; }

    /// <summary>Gordium's marks on its type (<c>Gordium: Top rail is handrail</c>), by GUID.</summary>
    public IReadOnlyDictionary<Guid, MarkValue> TypeMarks { get; init; } = new Dictionary<Guid, MarkValue>();

    /// <summary>Gordium's marks on the railing itself, by GUID: <c>Gordium: Not a stair</c> Yes on one is a conflict.</summary>
    public IReadOnlyDictionary<Guid, MarkValue> InstanceMarks { get; init; } = new Dictionary<Guid, MarkValue>();

    /// <summary>Its parts: the railing itself, its top rail (<c>Railing.TopRail</c>) and its handrails
    /// (<c>GetHandRails</c>).</summary>
    public IReadOnlyList<RailingPart> Parts { get; init; } = [];

    /// <summary>Every model element whose box meets the railing's box widened 2 ft (with its faces, box, phase and
    /// option): the floor it stands on and what it ends against. Null when it couldn't be looked for.</summary>
    public IReadOnlyList<NearbyElement>? Near { get; init; }

    /// <summary>What the Revit layer looked at, for the trial's log only.</summary>
    public IReadOnlyList<string> Diagnostics { get; init; } = [];
}

/// <summary>A curve of a railing's path.</summary>
public sealed record PathCurve(Xyz Start, Xyz End, bool IsLine);

/// <summary>What a part of a railing is.</summary>
public enum RailingPartKind { Railing, TopRail, Handrail }

/// <summary>One part of a railing, by <c>UniqueId</c>, with each of its solids' faces (a baluster, a rail: one solid
/// each), or null with <paramref name="GeometryFailed"/> when they couldn't be read (a mesh, Revit refused).</summary>
public sealed record RailingPart(string UniqueId, RailingPartKind Kind, IReadOnlyList<IReadOnlyList<SurfaceRecord>>? Solids,
                                 bool GeometryFailed = false);

/// <summary>A face of a solid (<c>Face</c>), or a mesh read as one.</summary>
/// <param name="Planar">A <c>PlanarFace</c> (anything else, a curved face or a mesh, is not read exactly).</param>
/// <param name="Normal"><c>PlanarFace.FaceNormal</c> (internal); zero for any other face.</param>
/// <param name="Loops"><c>GetEdgesAsCurveLoops()</c>: each loop's curves in order.</param>
/// <param name="Points">Points on it, for where it stands: a planar face's loop points; any other face's
/// <c>Triangulate()</c> vertices.</param>
public sealed record SurfaceRecord(bool Planar, Xyz Normal, IReadOnlyList<IReadOnlyList<LoopCurve>> Loops, IReadOnlyList<Xyz> Points);

/// <summary>A window's or door's placement: what the escape opening's room, sill and clear opening are read from and
/// checked against.</summary>
public sealed record OpeningRecord
{
    /// <summary><c>Element.UniqueId</c>.</summary>
    public required string UniqueId { get; init; }

    /// <summary><c>FamilyInstance.get_FromRoom(last phase)</c>'s <c>UniqueId</c>, or null.</summary>
    public string? FromRoom { get; init; }

    /// <summary><c>FamilyInstance.get_ToRoom(last phase)</c>'s <c>UniqueId</c>, or null.</summary>
    public string? ToRoom { get; init; }

    /// <summary>The host (<c>FamilyInstance.Host</c>): a wall's <c>UniqueId</c>, or null.</summary>
    public string? Host { get; init; }

    /// <summary>Whether the host is a wall (<c>Wall</c>).</summary>
    public bool HostIsWall { get; init; }

    /// <summary>The instance's level's elevation (<c>Level.ProjectElevation</c> of its <c>LevelId</c>), internal, or null.</summary>
    public double? LevelElevation { get; init; }

    /// <summary>The instance's level's <c>UniqueId</c> (<c>LevelId</c>), or null: the story a door is on (section 10).</summary>
    public string? LevelId { get; init; }

    /// <summary>The host wall's side faces (<c>HostObjectUtils.GetSideFaces</c>, both sides), or null when the host
    /// isn't a wall or any side face isn't planar or couldn't be read (a curved wall, a curtain wall): a door's centre
    /// and its wall's thickness are read from them (section 10).</summary>
    public IReadOnlyList<WallFace>? WallSides { get; init; }

    /// <summary>Its Sill Height (<c>INSTANCE_SILL_HEIGHT_PARAM</c>), or null when it has none.</summary>
    public double? SillHeight { get; init; }

    /// <summary>The instance's point (<c>LocationPoint.Point</c>), internal, or null.</summary>
    public Xyz? Location { get; init; }

    /// <summary><c>FamilyInstance.HandOrientation</c>: along the wall.</summary>
    public Xyz? Along { get; init; }

    /// <summary>The type's own Width and Height (<c>WINDOW_WIDTH</c> / <c>WINDOW_HEIGHT</c> on the type, else
    /// <c>FAMILY_WIDTH_PARAM</c> / <c>FAMILY_HEIGHT_PARAM</c>), or null when the type has none (a family sized per
    /// window, or size parameters of other names).</summary>
    public double? TypeWidth { get; init; }

    /// <inheritdoc cref="TypeWidth"/>
    public double? TypeHeight { get; init; }

    /// <summary>Every length parameter on the type, by name (<c>Parameter.Definition.Name</c>, <c>AsDouble()</c>): a
    /// maker's clear-opening parameter the stamp names is checked against its value now.</summary>
    public IReadOnlyDictionary<string, double> TypeLengths { get; init; } = new Dictionary<string, double>();

    /// <summary>Every point of the window's own drawn geometry as placed (<c>get_Geometry</c>, Fine: its solids' edge
    /// points), internal; null when it gives none.</summary>
    public IReadOnlyList<Xyz>? Placed { get; init; }

    /// <summary>Every point of the faces of the host wall that this window cut (<c>Element.GetGeneratingElementIds</c>
    /// of the wall's faces naming this window), internal; null when the host isn't a wall or no such face was found:
    /// the bottom of the wall opening, which the sill line is checked against (design note, section 4).</summary>
    public IReadOnlyList<Xyz>? WallOpening { get; init; }

    /// <summary>How the wall opening's faces were found, for the evidence: the wall's faces whose
    /// <c>GetGeneratingElementIds</c> name the window (<c>HostObject.FindInserts</c> isn't used: it listed no inserts
    /// even on walls the windows cut, trial run 6). Null when none was found.</summary>
    public string? WallOpeningBy { get; init; }

    /// <summary>The host wall's geometry, or one of its faces, couldn't be read (<c>get_Geometry</c> refused, or a face
    /// Revit gives no edges for): the opening this window cuts is unread, never looked for on the faces that could be
    /// read alone (its bottom could be on the one that couldn't). <see cref="WallOpening"/> is then null.</summary>
    public bool WallOpeningUnread { get; init; }

    /// <summary>Every model element (not view-specific) whose box (<c>get_BoundingBox(null)</c>) meets the instance's
    /// own box widened <see cref="GroundReader.Around"/> in plan and reaching <see cref="GroundReader.Below"/> under it:
    /// what could stand over the ground just outside it (an area well drawn as a family, a step, a slab, a deck), each
    /// with its box, category, phase and option (no faces). Its own box, its host wall and the grounds are among them;
    /// the reader sets those apart. Null when it couldn't be looked for: then no ground is read at the opening.</summary>
    public IReadOnlyList<NearbyElement>? Around { get; init; }

    /// <summary>What the Revit layer looked at for this window (the wall's faces, the ids that generated them), for the
    /// trial's log only: never read by a decision.</summary>
    public IReadOnlyList<string> Diagnostics { get; init; } = [];
}
