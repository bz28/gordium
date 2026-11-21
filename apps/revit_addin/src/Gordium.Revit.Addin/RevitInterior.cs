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
        InternalToShared = RevitRead.InternalToShared(doc),        // the one place the turn is settled (the outside reader's)
        UserWorksets = doc.IsWorkshared
            ? new FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
                .Select(w => new WorksetRecord(w.Id.IntegerValue.ToString(CultureInfo.InvariantCulture), w.Name, w.IsOpen)).ToList()
            : [],
        Interior = Read(doc),
    };

    internal static InteriorRecords Read(Document doc)
    {
        var phase = doc.Phases.Cast<Phase>().LastOrDefault();
        var rooms = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType()
            .OfType<Room>().Select(r => RoomOf(doc, r)).ToList();
        var openings = new[] { BuiltInCategory.OST_Windows, BuiltInCategory.OST_Doors }
            .SelectMany(c => new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType().OfType<FamilyInstance>())
            .Select(fi => OpeningOf(doc, fi, phase)).ToList();
        var diagnostics = new List<string>();
        // the design options (for the trial's log): what is read is the main model and, of each set, the option being
        // edited or else its primary; Revit's enclosed areas (plan circuits) are the main model's own
        var active = DesignOption.GetActiveDesignOptionId(doc);
        diagnostics.Add("design options: " + string.Join("; ", new FilteredElementCollector(doc).OfClass(typeof(DesignOption)).Cast<DesignOption>()
            .Select(o => $"{doc.GetElement(o.get_Parameter(BuiltInParameter.OPTION_SET_ID)?.AsElementId() ?? ElementId.InvalidElementId)?.Name}: " +
                         $"{o.Name}{(o.IsPrimary ? " (primary)" : "")}{(o.Id == active ? " (being edited)" : "")}")));
        var (stairs, candidates) = StairsOf(doc, diagnostics);
        var railings = RailingsOf(doc, diagnostics);
        int coordination;
        try
        {
            coordination = Autodesk.Revit.DB.ExternalData.CoordinationModelLinkUtils.GetAllCoordinationModelInstanceIds(doc).Count;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            diagnostics.Add($"coordination models couldn't be listed ({x.GetType().Name}: {x.Message}): counted as one");
            coordination = 1;                                         // what can't be listed could hold a stair
        }
        return new InteriorRecords
        {
            Rooms = rooms,
            Openings = openings,
            EnclosedAreas = phase is null ? null : Areas(doc, phase, diagnostics),
            Links = Links(doc),
            Stairs = stairs,
            StairCandidates = candidates,
            Railings = railings,
            Ramps = RampsOf(doc, diagnostics),
            CoordinationModels = coordination,
            Levels = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                .Select(l => new LevelRecord(l.UniqueId, l.Name, l.ProjectElevation)).ToList(),
            SeparationLines = SeparationLinesOf(doc, diagnostics),
            GrossAreas = phase is null ? null : GrossAreasOf(doc, phase, diagnostics),
            Diagnostics = diagnostics,
        };
    }

    /// <summary>Every room separation line (escape routes, section 10: where two rooms meet with no wall), by
    /// <c>UniqueId</c>; null when they couldn't be listed (then no passage is sent).</summary>
    private static List<string>? SeparationLinesOf(Document doc, List<string> diagnostics)
    {
        try
        {
            var lines = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_RoomSeparationLines)
                .WhereElementIsNotElementType().Select(e => e.UniqueId).ToList();
            diagnostics.Add($"room separation lines: {lines.Count}");
            return lines;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                       or Autodesk.Revit.Exceptions.ArgumentException)
        {
            diagnostics.Add($"the room separation lines couldn't be read ({x.GetType().Name}: {x.Message})");
            return null;
        }
    }

    /// <summary>Each level's exterior walls' outer faces, by Revit's own room logic (<see cref="RingOf"/>; the story's
    /// outlines, section 10), for each level with a placed Room, inside a transaction always rolled back. Each level's
    /// result says why when there is none; null when the document can't be changed for the moment.</summary>
    private static Dictionary<string, GrossArea>? GrossAreasOf(Document doc, Phase phase, List<string> diagnostics)
    {
        // Revit works a plan's enclosed areas out again only when a transaction is committed: so a transaction group,
        // its transactions committed and the whole group then rolled back (the model unchanged); that needs no
        // transaction open already
        if (doc.IsReadOnly || doc.IsModifiable)
        {
            diagnostics.Add("outer outlines: not read (the document is read-only or already in a transaction)");
            return null;
        }
        var walls = new FilteredElementCollector(doc).OfClass(typeof(Wall)).Cast<Wall>().Where(w => !w.ViewSpecific).ToList();
        var planType = new FilteredElementCollector(doc).OfClass(typeof(ViewFamilyType)).Cast<ViewFamilyType>().ToList()
            .FirstOrDefault(v => v.ViewFamily == ViewFamily.FloorPlan);
        var levels = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>().ToList();
        var rooms = new FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_Rooms).WhereElementIsNotElementType().OfType<Room>()
            .Where(r => r.Location is LocationPoint && r.Area > 0).ToList();
        var result = new Dictionary<string, GrossArea>(StringComparer.Ordinal);
        foreach (var level in levels)
        {
            if (!rooms.Any(r => r.LevelId == level.Id))
                continue;
            using var group = new TransactionGroup(doc, ResultRows.AreasTransaction);
            group.Start();
            try
            {
                result[level.UniqueId] = RingOf(doc, phase, level, walls.Where(w => w.LevelId == level.Id).ToList(), planType, diagnostics);
            }
            finally
            {
                group.RollBack();                            // every transaction in it taken back: the model as it was
            }
        }
        return result;
    }

    /// <summary>A transaction whose warnings are dismissed (no dialog in a read), its errors rolling it back.</summary>
    private static void Quiet(Transaction t)
    {
        var o = t.GetFailureHandlingOptions();
        o.SetFailuresPreprocessor(new DismissWarnings());
        o.SetClearAfterRollback(true);
        t.SetFailureHandlingOptions(o);
    }

    private sealed class DismissWarnings : IFailuresPreprocessor
    {
        public FailureProcessingResult PreprocessFailures(FailuresAccessor a)
        {
            foreach (var f in a.GetFailureMessages().Where(f => f.GetSeverity() == FailureSeverity.Warning).ToList())
                a.DeleteWarning(f);
            return FailureProcessingResult.Continue;
        }
    }

    /// <summary>The level's exterior walls' outer faces by Revit's own room logic: room separation lines drawn as a
    /// rectangle 20 ft beyond the level's walls, a Room placed in the ring between it and the building, its boundary at
    /// the finished faces read (doors and windows don't break a room's boundary; interior walls never touch this one),
    /// the rectangle's loop dropped. The lines and the Room are each made in a committed transaction (Revit works a
    /// plan's enclosed areas out again only on a commit) inside the transaction group <see cref="GrossAreasOf"/> rolls
    /// back. Each loop's corners and area, and each side with what bounds it, are logged.</summary>
    private static GrossArea RingOf(Document doc, Phase phase, Level level, List<Wall> walls, ViewFamilyType? planType, List<string> diagnostics)
    {
        GrossArea No(string why) => new(null, new Dictionary<string, double>(), why);
        var boxes = walls.Select(w => w.get_BoundingBox(null)).OfType<BoundingBoxXYZ>().ToList();
        if (boxes.Count == 0)
            return No("no wall stands on the level");
        if (planType is null)
            return No("the model has no floor plan view type to draw the ring's lines in");
        const double Beyond = 20;
        double x0 = boxes.Min(b => b.Min.X) - Beyond, y0 = boxes.Min(b => b.Min.Y) - Beyond, x1 = boxes.Max(b => b.Max.X) + Beyond, y1 = boxes.Max(b => b.Max.Y) + Beyond;
        var z = level.ProjectElevation;
        try
        {
            HashSet<ElementId> lines;
            using (var draw = new Transaction(doc, "Gordium: the ring's lines (taken back)"))
            {
                Quiet(draw);
                draw.Start();
                // the level's own floor plan when it has one (else one made for the moment), in the phase rooms are read in
                var view = new FilteredElementCollector(doc).OfClass(typeof(ViewPlan)).Cast<ViewPlan>().ToList()
                    .FirstOrDefault(v => !v.IsTemplate && v.ViewType == ViewType.FloorPlan && v.GenLevel?.Id == level.Id)
                    ?? ViewPlan.Create(doc, planType.Id, level.Id);
                view.get_Parameter(BuiltInParameter.VIEW_PHASE)?.Set(phase.Id);
                var sketch = SketchPlane.Create(doc, level.Id);
                var ring = new CurveArray();
                XYZ[] corners = [new(x0, y0, z), new(x1, y0, z), new(x1, y1, z), new(x0, y1, z)];
                for (var i = 0; i < 4; i++)
                    ring.Append(Line.CreateBound(corners[i], corners[(i + 1) % 4]));
                lines = doc.Create.NewRoomBoundaryLines(sketch, ring, view).Cast<ModelCurve>().Select(c => c.Id).ToHashSet();
                if (draw.Commit() != TransactionStatus.Committed)
                    return No("Revit didn't keep the ring's lines");
            }
            var circuits = doc.get_PlanTopology(level, phase)?.Circuits?.Cast<PlanCircuit>().ToList() ?? [];
            var ringCircuit = circuits.OrderByDescending(c => c.Area).FirstOrDefault();
            var expected = (x1 - x0) * (y1 - y0);
            diagnostics.Add($"outer outline of {level.Name}: {lines.Count} separation lines drawn round ({x0:0.#}, {y0:0.#})-({x1:0.#}, {y1:0.#}), " +
                            $"{circuits.Count} enclosed areas, the largest {ringCircuit?.Area:0.#} sq ft (the rectangle {expected:0.#})");
            Room room;
            using (var place = new Transaction(doc, "Gordium: the ring's Room (taken back)"))
            {
                Quiet(place);
                place.Start();
                if (ringCircuit is not null && !ringCircuit.IsRoomLocated && ringCircuit.Area > expected / 2)
                {
                    room = doc.Create.NewRoom(phase);
                    doc.Create.NewRoom(room, ringCircuit);
                }
                else
                    room = doc.Create.NewRoom(level, new UV(x0 + Beyond / 2, y0 + Beyond / 2));   // the ring's point, 10 ft outside the walls
                if (place.Commit() != TransactionStatus.Committed)
                    return No("Revit didn't keep the ring's Room");
            }
            diagnostics.Add($"outer outline of {level.Name}: the ring Room {(room.Area > 0 ? "closed" : "not closed")}, {room.Area:0.#} sq ft");
            if (room.Area <= 0)
                return No($"the Room placed round the building isn't enclosed (Revit gives it no area; the largest enclosed area {ringCircuit?.Area:0.#} sq ft)");
            var loops = room.GetBoundarySegments(new SpatialElementBoundaryOptions { SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish });
            var widths = new Dictionary<string, double>(StringComparer.Ordinal);
            var building = loops.Where(l => !l.All(seg => lines.Contains(seg.ElementId))).Select(loop => (IReadOnlyList<BoundarySegmentRecord>)loop.Select(seg =>
            {
                var c = seg.GetCurve();
                var by = doc.GetElement(seg.ElementId);
                if (by is Wall w)
                    widths[w.UniqueId] = w.Width;
                return new BoundarySegmentRecord(P(c.GetEndPoint(0)), P(c.GetEndPoint(1)), c is Line, by?.UniqueId);
            }).ToList()).ToList();
            diagnostics.Add($"outer outline of {level.Name}: the ring Room has {loops.Count} loops; the building's: " +
                            string.Join("; ", building.Select(l =>
                            {
                                var p = l.Select(seg => seg.Start).ToList();
                                var area = Math.Abs(p.Select((a, i) => a.X * p[(i + 1) % p.Count].Y - p[(i + 1) % p.Count].X * a.Y).Sum()) / 2;
                                return $"{l.Count} corners, {area:0.#} sq ft";
                            })));
            // each side and what bounds it, so a side the reader can't use can be found in the model
            foreach (var l in loops.Where(l => !l.All(seg => lines.Contains(seg.ElementId))))
                diagnostics.Add($"outer outline of {level.Name}, sides: " + string.Join(" ", l.Select(seg =>
                {
                    var c = seg.GetCurve();
                    var by = doc.GetElement(seg.ElementId);
                    return $"({c.GetEndPoint(0).X:0.###},{c.GetEndPoint(0).Y:0.###})-({c.GetEndPoint(1).X:0.###},{c.GetEndPoint(1).Y:0.###}) " +
                           $"{by?.Category?.BuiltInCategory.ToString().Replace("OST_", "") ?? "none"} {by?.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString()};";
                })));
            return new GrossArea(building, widths);
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            diagnostics.Add($"outer outline of {level.Name}: Revit refused ({x.GetType().Name}: {x.Message})");
            return No($"Revit refused ({x.Message})");
        }
    }

    /// <summary>The door's host wall's side faces (<c>HostObjectUtils.GetSideFaces</c>, exterior then interior), each a
    /// plane; null when the host isn't a wall, a side has no face, a face isn't planar (a curved wall) or Revit refuses
    /// (a curtain wall): then the door's place in its wall isn't read.</summary>
    private static List<WallFace>? SidesOf(Element? host)
    {
        if (host is not Wall wall)
            return null;
        try
        {
            var sides = new List<WallFace>();
            foreach (var side in new[] { ShellLayerType.Exterior, ShellLayerType.Interior })
            {
                var refs = HostObjectUtils.GetSideFaces(wall, side);
                if (refs is null || refs.Count == 0)
                    return null;
                foreach (var r in refs)
                {
                    if (wall.GetGeometryObjectFromReference(r) is not PlanarFace f)
                        return null;
                    sides.Add(new WallFace(P(f.Origin), P(f.FaceNormal)));
                }
            }
            return sides;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return null;
        }
    }

    // ---- stairs (step 4) ---------------------------------------------------------------------------------------

    private static readonly Options Fine = new() { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };

    /// <summary>Every component stair with its runs, and everything else in Stairs, Railings and Generic Models (and
    /// every multistory stair) as something that could be a stair the reader doesn't walk. View-specific elements (a
    /// stair path, a tag) aren't model elements and aren't listed.</summary>
    private static (List<StairRecord>? Stairs, List<StairCandidate> Candidates) StairsOf(Document doc, List<string> diagnostics)
    {
        var stairs = new List<StairRecord>();
        var candidates = new List<StairCandidate>();
        try
        {
            foreach (var e in Models(doc, BuiltInCategory.OST_Stairs))
            {
                if (e is Stairs s)
                    stairs.Add(StairOf(doc, s, diagnostics));
                else
                    candidates.Add(Candidate(e));
            }
            foreach (var e in Models(doc, BuiltInCategory.OST_StairsRailing).Where(e => e is not Railing))
                candidates.Add(Candidate(e));
            foreach (var e in Models(doc, BuiltInCategory.OST_GenericModel))
                candidates.Add(Candidate(e));
            foreach (var m in new FilteredElementCollector(doc).OfClass(typeof(MultistoryStairs)).ToList())
                candidates.Add(new StairCandidate(m.UniqueId, m.Category?.BuiltInCategory.ToString() ?? "OST_MultistoryStairs", m.Name,
                                                  "a multistory stair", Id(m.DemolishedPhaseId), Id(m.DesignOption?.Id)));
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                       or Autodesk.Revit.Exceptions.ArgumentException)
        {
            diagnostics.Add($"the stairs couldn't be read ({x.GetType().Name}: {x.Message})");
            return (null, candidates);
        }
        diagnostics.Add($"stairs: {stairs.Count} component stairs ({stairs.Sum(s => s.Runs.Count)} runs), {candidates.Count} other elements that could be one " +
                        $"({candidates.Count(StairReader.InsideWindowOrDoor)} of them generic models nested inside a window or door, not a stair); " +
                        "nested and not inside their window or door: " + string.Join(", ", candidates
                            .Where(c => c.NestedIn is { Count: > 0 } && !StairReader.InsideWindowOrDoor(c)).Take(10)
                            .Select(c => $"{c.Name} in {string.Join(" in ", c.NestedIn!.Select(h => h.BuiltInCategory.Replace("OST_", "")))}")));
        return (stairs, candidates);
    }

    /// <summary>Every model element in Ramps (step 6: a ramp drawn contradicts "this house has no ramps"); null when
    /// they couldn't be listed.</summary>
    private static List<RampRecord>? RampsOf(Document doc, List<string> diagnostics)
    {
        try
        {
            var ramps = Models(doc, BuiltInCategory.OST_Ramps)
                .Select(e => new RampRecord(e.UniqueId, e.Name, Id(e.DemolishedPhaseId), Id(e.DesignOption?.Id))).ToList();
            diagnostics.Add($"ramps: {ramps.Count} elements in Ramps");
            return ramps;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                       or Autodesk.Revit.Exceptions.ArgumentException)
        {
            diagnostics.Add($"the ramps couldn't be read ({x.GetType().Name}: {x.Message})");
            return null;
        }
    }

    private static IEnumerable<Element> Models(Document doc, BuiltInCategory c) =>
        new FilteredElementCollector(doc).OfCategory(c).WhereElementIsNotElementType().Where(e => !e.ViewSpecific).ToList();

    private static StairCandidate Candidate(Element e) => new(
        e.UniqueId, e.Category?.BuiltInCategory.ToString() ?? "", e.Name,
        e switch
        {
            FamilyInstance { Symbol.Family.IsInPlace: true } => "an in-place family",
            FamilyInstance => "a loadable family",
            DirectShape => "a DirectShape",
            Stairs => "a stair not made of components",
            _ => $"another element ({e.GetType().Name})",
        },
        Id(e.DemolishedPhaseId), Id(e.DesignOption?.Id), BoxOf(e), NestedIn(e), RevitMarks.Values(e));

    /// <summary>The family instances <paramref name="e"/> is nested in, innermost first (<c>FamilyInstance.SuperComponent</c>
    /// to the top), each with its category and box; empty when it isn't nested.</summary>
    private static List<NestHost> NestedIn(Element e)
    {
        var chain = new List<NestHost>();
        var seen = new HashSet<ElementId>();
        for (var up = (e as FamilyInstance)?.SuperComponent; up is not null && seen.Add(up.Id) && chain.Count < 32;
             up = (up as FamilyInstance)?.SuperComponent)
            chain.Add(new NestHost(up.UniqueId, up.Category?.BuiltInCategory.ToString() ?? "", BoxOf(up)));
        return chain;
    }

    private static StairRecord StairOf(Document doc, Stairs s, List<string> diagnostics)
    {
        var type = doc.GetElement(s.GetTypeId());
        var mark = s.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString();
        var name = string.Join(" ", new[] { type?.Name, mark }.Where(x => !string.IsNullOrWhiteSpace(x)));
        var byComponent = Stairs.IsByComponent(doc, s.Id);
        var record = new StairRecord
        {
            UniqueId = s.UniqueId,
            Name = name.Length > 0 ? name : null,
            IsByComponent = byComponent,
            MultistoryStairsId = Id(s.MultistoryStairsId),
            InstanceMarks = RevitMarks.Values(s),
            PhaseCreated = Id(s.CreatedPhaseId),
            PhaseDemolished = Id(s.DemolishedPhaseId),
            DesignOption = Id(s.DesignOption?.Id),
        };
        if (!byComponent)
            return record;
        string[] Uids(IEnumerable<ElementId> ids) => ids.Select(id => doc.GetElement(id)?.UniqueId).OfType<string>().ToArray();
        var (ownFaces, _) = Faces(s, Fine);
        diagnostics.Add($"stair {s.Id.Value} \"{name}\": base {s.BaseElevation:0.######}, top {s.TopElevation:0.######}, " +
                        $"riser {s.ActualRiserHeight * 12:0.######} in, tread {s.ActualTreadDepth * 12:0.######} in, " +
                        $"risers {s.ActualRisersNumber}, the stair element's own geometry {ownFaces?.Count ?? -1} faces");
        return record with
        {
            BaseElevation = s.BaseElevation,
            ActualRiserHeight = s.ActualRiserHeight,
            ActualTreadDepth = s.ActualTreadDepth,
            Runs = s.GetStairsRuns().Select(id => doc.GetElement(id)).OfType<StairsRun>().Select(r => RunOf(doc, s, r)).ToList(),
            Landings = Uids(s.GetStairsLandings()),
            Supports = Uids(s.GetStairsSupports()),
            Railings = Uids(s.GetAssociatedRailings()),
        };
    }

    /// <summary>A run: its own faces, path and numbers, and everything around it (its box widened 2 ft in plan, from 2
    /// ft under it up), each with its faces, box, phase and option, logged enough that a failing run explains itself.</summary>
    private static RunRecord RunOf(Document doc, Stairs stairs, StairsRun run)
    {
        var words = new List<string>();
        var path = new List<Xyz>();
        try
        {
            var curves = run.GetStairsPath().ToList();
            if (curves.Count > 0)
            {
                path.Add(P(curves[0].GetEndPoint(0)));
                path.AddRange(curves.Select(c => P(c.GetEndPoint(1))));
            }
        }
        catch (Autodesk.Revit.Exceptions.InvalidOperationException x)
        {
            words.Add($"no path: {x.Message}");
        }
        var (faces, failed) = Faces(run, Fine);
        var box = run.get_BoundingBox(null);
        List<NearbyElement>? near = null;
        if (box is not null)
            near = Near(doc, run.Id, new Outline(new XYZ(box.Min.X - 2, box.Min.Y - 2, box.Min.Z - 2),
                                                  new XYZ(box.Max.X + 2, box.Max.Y + 2, box.Max.Z + 1000)), null);
        var up = faces?.Count(f => f.Planar && f.Normal.Z > 1 - 1e-6) ?? -1;
        words.Add($"run {run.Id.Value} {run.StairsRunStyle}: base {run.BaseElevation:0.######}, top {run.TopElevation:0.######} (relative), " +
                  $"risers {run.ActualRisersNumber}, treads {run.ActualTreadsNumber}, begins/ends with riser {run.BeginsWithRiser}/{run.EndsWithRiser}, " +
                  $"width {run.ActualRunWidth * 12:0.######} in; path {string.Join(" ", path.Select(p => $"({p.X:0.####},{p.Y:0.####},{p.Z:0.####})"))}");
        words.Add($"its geometry: {faces?.Count ?? -1} faces ({up} facing up, {faces?.Count(f => !f.Planar) ?? -1} curved), failed {failed}; " +
                  $"box {box?.Min.X:0.###},{box?.Min.Y:0.###},{box?.Min.Z:0.###} to {box?.Max.X:0.###},{box?.Max.Y:0.###},{box?.Max.Z:0.###}");
        words.Add("tread tops (z, internal): " + string.Join(" ", (faces ?? []).Where(f => f.Planar && f.Normal.Z > 1 - 1e-6)
            .Select(f => f.Points.Count == 0 ? "?" : $"{f.Points.Average(p => p.Z):0.######}").Distinct()));
        words.Add($"around it: {near?.Count.ToString(CultureInfo.InvariantCulture) ?? "not looked for"} elements: " +
                  string.Join(", ", (near ?? []).Select(e => $"{e.BuiltInCategory.Replace("OST_", "")} {e.Name} ({e.Faces?.Count ?? -1} faces)")));
        return new RunRecord
        {
            UniqueId = run.UniqueId,
            Style = run.StairsRunStyle.ToString(),
            BaseElevation = run.BaseElevation,
            TopElevation = run.TopElevation,
            RisersNumber = run.ActualRisersNumber,
            TreadsNumber = run.ActualTreadsNumber,
            BeginsWithRiser = run.BeginsWithRiser,
            EndsWithRiser = run.EndsWithRiser,
            Path = path,
            Faces = failed ? null : faces,
            GeometryFailed = failed || faces is null,
            Near = near,
            Diagnostics = words,
        };
    }

    private static string? Id(ElementId? id) =>
        id is null || id == ElementId.InvalidElementId ? null : id.Value.ToString(CultureInfo.InvariantCulture);

    // ---- railings (step 5) -------------------------------------------------------------------------------------

    /// <summary>Every <c>Railing</c> (not view-specific), with its path, base, host, type marks, its parts (itself, its
    /// top rail, its handrails) each as its solids' faces, and what is around it. Null when they couldn't be read.</summary>
    private static List<RailingRecord>? RailingsOf(Document doc, List<string> diagnostics)
    {
        try
        {
            var list = Models(doc, BuiltInCategory.OST_StairsRailing).OfType<Railing>().Select(r => RailingOf(doc, r)).ToList();
            diagnostics.Add($"railings: {list.Count}");
            return list;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                       or Autodesk.Revit.Exceptions.ArgumentException)
        {
            diagnostics.Add($"the railings couldn't be read ({x.GetType().Name}: {x.Message})");
            return null;
        }
    }

    private static RailingRecord RailingOf(Document doc, Railing r)
    {
        var words = new List<string>();
        var type = doc.GetElement(r.GetTypeId());
        var path = new List<PathCurve>();
        try
        {
            foreach (var c in r.GetPath())
                path.Add(new PathCurve(P(c.GetEndPoint(0)), P(c.GetEndPoint(1)), c is Line));
        }
        catch (Autodesk.Revit.Exceptions.InvalidOperationException x)
        {
            words.Add($"no path: {x.Message}");
        }
        var levelId = r.get_Parameter(BuiltInParameter.STAIRS_RAILING_BASE_LEVEL_PARAM)?.AsElementId();
        var level = (levelId is null ? null : doc.GetElement(levelId) as Level) ?? doc.GetElement(r.LevelId) as Level;
        var offsetParam = r.get_Parameter(BuiltInParameter.STAIRS_RAILING_HEIGHT_OFFSET);
        double? offset = offsetParam is { HasValue: true, StorageType: StorageType.Double } ? offsetParam.AsDouble() : null;
        var elements = new List<(Element E, RailingPartKind Kind)> { (r, RailingPartKind.Railing) };
        if (r.TopRail != ElementId.InvalidElementId && doc.GetElement(r.TopRail) is { } top)
            elements.Add((top, RailingPartKind.TopRail));
        foreach (var id in r.GetHandRails())
            if (doc.GetElement(id) is { } h)
                elements.Add((h, RailingPartKind.Handrail));
        var parts = new List<RailingPart>();
        var boxes = new List<BoundingBoxXYZ>();
        foreach (var (e, kind) in elements)
        {
            var (solids, failed) = Solids(e, Fine);
            parts.Add(new RailingPart(e.UniqueId, kind, failed ? null : solids, failed || solids is null));
            var box = e.get_BoundingBox(null);
            if (box is not null)
                boxes.Add(box);
            var pts = (solids ?? []).SelectMany(s => s).SelectMany(f => f.Points).ToList();
            words.Add($"{kind} {e.Id.Value} {e.Category?.BuiltInCategory}: {solids?.Count ?? -1} solids " +
                      $"({string.Join(",", (solids ?? []).Select(s => s.Count))} faces, {(solids ?? []).Sum(s => s.Count(f => !f.Planar))} curved), failed {failed}" +
                      (pts.Count == 0 ? "" : $"; x {pts.Min(p => p.X):0.####}..{pts.Max(p => p.X):0.####}, y {pts.Min(p => p.Y):0.####}..{pts.Max(p => p.Y):0.####}, " +
                                             $"z {pts.Min(p => p.Z):0.####}..{pts.Max(p => p.Z):0.####}"));
            foreach (var s in (solids ?? []).Take(40))
            {
                var sp = s.SelectMany(f => f.Points).ToList();
                if (sp.Count > 0)
                    words.Add($"  solid: x {sp.Min(p => p.X):0.#####}..{sp.Max(p => p.X):0.#####}, y {sp.Min(p => p.Y):0.#####}..{sp.Max(p => p.Y):0.#####}, " +
                              $"z {sp.Min(p => p.Z):0.#####}..{sp.Max(p => p.Z):0.#####}, {s.Count} faces");
            }
        }
        List<NearbyElement>? near = null;
        if (boxes.Count > 0)
        {
            near = Near(doc, r.Id, new Outline(new XYZ(boxes.Min(b => b.Min.X) - 2, boxes.Min(b => b.Min.Y) - 2, boxes.Min(b => b.Min.Z) - 2),
                                                new XYZ(boxes.Max(b => b.Max.X) + 2, boxes.Max(b => b.Max.Y) + 2, boxes.Max(b => b.Max.Z) + 2)), null)
                ?.Where(e => !elements.Any(x => x.E.UniqueId == e.UniqueId)).ToList();
        }
        var host = r.HasHost ? doc.GetElement(r.HostId) : null;
        var mark = r.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString();
        var name = string.Join(" ", new[] { type?.Name, mark }.Where(x => !string.IsNullOrWhiteSpace(x)));
        words.Insert(0, $"railing {r.Id.Value} \"{name}\": host {host?.Category?.BuiltInCategory} {host?.Id.Value}, base level {level?.Name} " +
                        $"{level?.ProjectElevation:0.######}, base offset {offset:0.######}; path " +
                        string.Join(" ", path.Select(c => $"({c.Start.X:0.####},{c.Start.Y:0.####},{c.Start.Z:0.####})-({c.End.X:0.####},{c.End.Y:0.####},{c.End.Z:0.####}){(c.IsLine ? "" : " curved")}")) +
                        $"; around it {near?.Count.ToString(CultureInfo.InvariantCulture) ?? "not looked for"}: " +
                        string.Join(", ", (near ?? []).Select(e => $"{e.BuiltInCategory.Replace("OST_", "")} {e.Name}")));
        return new RailingRecord
        {
            UniqueId = r.UniqueId,
            Name = name.Length > 0 ? name : null,
            Host = host?.UniqueId,
            PhaseDemolished = Id(r.DemolishedPhaseId),
            DesignOption = Id(r.DesignOption?.Id),
            Path = path,
            BaseLevelElevation = level?.ProjectElevation,
            BaseOffset = offset,
            TypeMarks = type is null ? new Dictionary<Guid, MarkValue>() : RevitMarks.Values(type),
            InstanceMarks = RevitMarks.Values(r),
            Parts = parts,
            Near = near,
            Diagnostics = words,
        };
    }

    /// <summary>Each solid of the element's geometry (a family's instance geometry included) as its faces, solids with
    /// no face (Revit's empty ones) left out; and whether anything couldn't be read as faces (a mesh, a throw, or a face Revit gives no edges or
    /// triangles for).</summary>
    private static (List<IReadOnlyList<SurfaceRecord>>? Solids, bool Failed) Solids(Element e, Options options)
    {
        var solids = new List<IReadOnlyList<SurfaceRecord>>();
        var failed = false;
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                switch (o)
                {
                    case Solid s when s.Faces.Size > 0:
                        var read = s.Faces.Cast<Face>().Select(Surface).ToList();
                        if (read.Any(f => f is null))
                            failed = true;               // a face Revit can't give: the element's geometry failed
                        else
                            solids.Add(read.Select(f => f!).ToList());
                        break;
                    case GeometryInstance gi when gi.GetInstanceGeometry() is { } inner:
                        Walk(inner);
                        break;
                    case Mesh:
                        failed = true;
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
        return (solids, failed);
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
            t = new Transaction(doc, ResultRows.AreasTransaction);
            t.Start();
        }
        try
        {
            var areas = new List<EnclosedArea>();
            // every collector listed before the model changes (an outline places a Room for the moment: a live
            // iterator then throws, "changes made to the Element table", the Children's Odyssey read, 2026-11-21)
            foreach (var level in new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>().ToList())
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
                // first every circuit of the level read, the model unchanged
                var listed = circuits.Cast<PlanCircuit>().ToList();
                foreach (var c in listed)
                {
                    // Revit refuses a point inside a degenerate circuit (a sliver between overlapping walls: the
                    // Children's Odyssey model, 2026-11-20): the area is kept with no point, never dropped
                    Xyz? point = null;
                    try
                    {
                        var inside = c.GetPointInside();
                        point = new Xyz(inside.U, inside.V, level.ProjectElevation);
                    }
                    catch (Autodesk.Revit.Exceptions.InvalidOperationException)
                    {
                    }
                    areas.Add(new EnclosedArea(level.Name, c.Area, c.IsRoomLocated, point, level.UniqueId));
                }
                // then each one with no Room outlined, one sub-transaction each, rolled back; the circuit taken afresh
                // from the level's topology each time (by its place in the list, its area checked), never one held
                // across a change
                for (var k = 0; k < listed.Count; k++)
                    if (!areas[before + k].HasRoom)
                    {
                        areas[before + k] = areas[before + k] with { Outline = OutlineOf(doc, phase, level, k, areas[before + k].Area, out var by) };
                        // an area Revit gives no point in (a sliver) is located by what bounds it, for the log
                        if (areas[before + k].PointInside is null)
                            diagnostics.Add($"enclosed area {k} on {level.Name} ({areas[before + k].Area:0.####} sq ft, no point inside): " +
                                            (by.Count > 0 ? "bounded by " + string.Join(", ", by) : "Revit gave no boundary for a Room in it") +
                                            (areas[before + k].Outline is { } o ? "; outline " + string.Join(" ", o.Select(q => $"({q.X:0.####},{q.Y:0.####})")) : ""));
                    }
                diagnostics.Add($"enclosed areas on {level.Name}: {areas.Count - before} " +
                                $"({areas.Skip(before).Count(a => !a.HasRoom)} with no Room: " +
                                string.Join(", ", areas.Skip(before).Where(a => !a.HasRoom)
                                    .Select(a => a.PointInside is { } p
                                        ? $"{a.Area:0.#} sq ft at ({p.X:0.##}, {p.Y:0.##}) internal"
                                        : $"{a.Area:0.#} sq ft, no point inside")) + ")");
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

    /// <summary>An enclosed area's outline: a Room placed in it for the moment (<c>NewRoom(phase)</c>, then
    /// <c>NewRoom(room, circuit)</c>) inside a <c>SubTransaction</c> that is always rolled back, its outer boundary loop at
    /// the finished faces (the loop of largest area), each segment's start. Null when the document can't be changed for
    /// the moment, Revit refuses, or a segment is curved: the reader then never calls a door's far side on that level
    /// outside (escape routes, section 10).</summary>
    private static List<Xyz>? OutlineOf(Document doc, Phase phase, Level level, int index, double area, out List<string> by)
    {
        by = [];
        if (!doc.IsModifiable)
            return null;
        using var st = new SubTransaction(doc);
        try
        {
            var fresh = doc.get_PlanTopology(level, phase)?.Circuits?.Cast<PlanCircuit>().ToList();
            if (fresh is null || index >= fresh.Count || Math.Abs(fresh[index].Area - area) > 1e-9 || fresh[index].IsRoomLocated)
                return null;                                     // not the same circuit: never outlined on a guess
            var circuit = fresh[index];
            st.Start();
            var room = doc.Create.NewRoom(phase);
            doc.Create.NewRoom(room, circuit);
            doc.Regenerate();
            var loops = room.GetBoundarySegments(new SpatialElementBoundaryOptions { SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish });
            by = (loops ?? []).SelectMany(l => l).Select(s => doc.GetElement(s.ElementId)).OfType<Element>()
                .Select(e => $"{e.Category?.Name} {e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)?.AsString() ?? e.Id.Value.ToString(CultureInfo.InvariantCulture)}")
                .Distinct().ToList();
            if (loops is null || loops.Count == 0 || loops.Any(l => l.Any(s => s.GetCurve() is not Line)))
                return null;
            static double Area(IList<BoundarySegment> l)
            {
                var p = l.Select(s => s.GetCurve().GetEndPoint(0)).ToList();
                return Math.Abs(p.Select((a, i) => a.X * p[(i + 1) % p.Count].Y - p[(i + 1) % p.Count].X * a.Y).Sum()) / 2;
            }
            return loops.OrderByDescending(Area).First().Select(s => P(s.GetCurve().GetEndPoint(0))).ToList();
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return null;
        }
        finally
        {
            if (st.HasStarted() && !st.HasEnded())
                st.RollBack();
        }
    }

    private static List<InteriorLink> Links(Document doc)
    {
        var links = new List<InteriorLink>();
        foreach (var li in new FilteredElementCollector(doc).OfClass(typeof(RevitLinkInstance)).Cast<RevitLinkInstance>().ToList())
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
                                       linked is not null && new FilteredElementCollector(linked).OfClass(typeof(RevitLinkInstance)).GetElementCount() > 0,
                                       Count(BuiltInCategory.OST_Stairs, BuiltInCategory.OST_StairsRailing, BuiltInCategory.OST_GenericModel),
                                       Count(BuiltInCategory.OST_Ramps)));
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
            LevelId = level?.UniqueId,
            LevelElevation = elevation,
            BaseOffset = offset,
            Boundary = boundary,
        };
        if (boundary is not { Count: > 0 } || elevation is null || offset is null || loops is null)
            return record;
        var floor = elevation.Value + offset.Value;
        // every loop's extent (Revit doesn't promise the outer loop first: a room round a column has two)
        var xs = loops.SelectMany(l => l).SelectMany(s => new[] { s.GetCurve().GetEndPoint(0), s.GetCurve().GetEndPoint(1) }).ToList();
        double x0 = xs.Min(p => p.X), y0 = xs.Min(p => p.Y), x1 = xs.Max(p => p.X), y1 = xs.Max(p => p.Y);
        return record with
        {
            Inside = Inside(doc, room, loops, floor, level!),
            Under = Near(doc, room.Id, new Outline(new XYZ(x0, y0, floor - InteriorReader.SlabBand), new XYZ(x1, y1, floor + InteriorReader.SlabBand)),
                         [BuiltInCategory.OST_Floors, BuiltInCategory.OST_StructuralFoundation]),
            Over = Near(doc, room.Id, new Outline(new XYZ(x0, y0, floor), new XYZ(x1, y1, floor + 1000)), null,
                        Band(x0, y0, x1, y1, floor)),
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
                .Select(e => new NearbyElement(e.UniqueId, Category(e), e.Name, (e as FamilyInstance)?.Host?.UniqueId,
                                               PhaseDemolished: Id(e.DemolishedPhaseId), DesignOption: Id(e.DesignOption?.Id)))
                .ToList();
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return null;
        }
    }

    /// <summary>The room's band (escape routes, section 10): a slab over the room's box from 1/16 in above its floor
    /// to 80 in up (<see cref="RouteReader.Headroom"/>); null when Revit can't make it.</summary>
    private static Solid? Band(double x0, double y0, double x1, double y1, double floor)
    {
        try
        {
            var z = floor + Sixteenth;
            var loop = CurveLoop.Create(new List<Curve>
            {
                Line.CreateBound(new XYZ(x0, y0, z), new XYZ(x1, y0, z)), Line.CreateBound(new XYZ(x1, y0, z), new XYZ(x1, y1, z)),
                Line.CreateBound(new XYZ(x1, y1, z), new XYZ(x0, y1, z)), Line.CreateBound(new XYZ(x0, y1, z), new XYZ(x0, y0, z)),
            });
            return GeometryCreationUtilities.CreateExtrusionGeometry([loop], XYZ.BasisZ, RouteReader.Headroom - Sixteenth);
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException)
        {
            return null;
        }
    }

    /// <summary>A solid that isn't closed: no volume, or an edge with no second face (as <c>RevitRead</c>'s edges are
    /// read, <c>Edge.GetFace(1)</c>; round 5); an edge that can't be asked counts as open.</summary>
    internal static bool Open(Solid s)
    {
        if (s.Volume <= 1e-12)
            return true;
        try
        {
            foreach (Edge edge in s.Edges)
                if (edge.GetFace(1) is null)
                    return true;
            return false;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException
                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return true;
        }
    }

    /// <summary>What of the element lies in the band: each of its solids (a family's instance geometry included)
    /// intersected with it, the result's faces; failed when Revit refuses, the element holds a mesh, an instance with no
    /// geometry or a kind not read, or a face of the result can't be read; and how many open shells (see
    /// <see cref="Open"/>: no volume, or an edge with one face) reach the band.</summary>
    private static (List<SurfaceRecord> Faces, bool Failed, int OpenShells) InBand(Element e, Solid band, Options options)
    {
        var faces = new List<SurfaceRecord>();
        var failed = false;
        var open = 0;
        var bandBox = band.GetBoundingBox();
        XYZ bandMin = bandBox.Transform.OfPoint(bandBox.Min), bandMax = bandBox.Transform.OfPoint(bandBox.Max);
        // every kind of geometry has its own branch: nothing is dropped by default (review round 4)
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                switch (o)
                {
                    case Solid { Faces.Size: 0 }:
                        break;                                   // an empty solid: nothing drawn
                    case Solid s when Open(s):
                        // an open shell (imported surfaces, a DirectShape from an open Brep: no volume, or an edge with
                        // one face), which can't be cut; counted unless its box lies wholly outside the band
                        var sb = s.GetBoundingBox();
                        var corners = new[] { sb.Min, sb.Max, new XYZ(sb.Min.X, sb.Max.Y, sb.Min.Z), new XYZ(sb.Max.X, sb.Min.Y, sb.Max.Z) }
                            .Select(sb.Transform.OfPoint).ToList();
                        if (corners.Max(c => c.X) < bandMin.X || corners.Min(c => c.X) > bandMax.X
                            || corners.Max(c => c.Y) < bandMin.Y || corners.Min(c => c.Y) > bandMax.Y
                            || corners.Max(c => c.Z) < bandMin.Z || corners.Min(c => c.Z) > bandMax.Z)
                            break;
                        open++;
                        break;
                    case Solid s:
                        var cut = BooleanOperationsUtils.ExecuteBooleanOperation(s, band, BooleanOperationsType.Intersect);
                        if (cut is null)
                            break;                               // none of it in the band
                        foreach (Face f in cut.Faces)
                            if (Surface(f) is { } face)
                                faces.Add(face);
                            else
                                failed = true;
                        break;
                    case GeometryInstance gi:
                        if (gi.GetInstanceGeometry() is { } inner)
                            Walk(inner);
                        else
                            failed = true;
                        break;
                    case GeometryElement nested:
                        Walk(nested);
                        break;
                    case Curve or PolyLine or Point:
                        break;                                   // lines and points: no body to stand in the way
                    default:
                        failed = true;                           // a mesh, or a kind not read
                        break;
                }
            }
        }
        try
        {
            if (e.get_Geometry(options) is { } g)
                Walk(g);
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException
                                       or Autodesk.Revit.Exceptions.ArgumentException)
        {
            return ([], true, 0);
        }
        return (faces, failed, open);
    }

    /// <summary>The model elements (not view-specific) whose box meets <paramref name="box"/>, of the categories given
    /// (any for null), with their faces; with <paramref name="band"/>, also what of each lies in it.</summary>
    private static List<NearbyElement>? Near(Document doc, ElementId skip, Outline box, BuiltInCategory[]? categories, Solid? band = null)
    {
        try
        {
            var options = new Options { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };
            var found = new FilteredElementCollector(doc).WhereElementIsNotElementType().WherePasses(new BoundingBoxIntersectsFilter(box)).ToList();
            var list = new List<NearbyElement>();
            foreach (var e in found)
            {
                if (e.Id == skip || e.ViewSpecific || e.Category is not { CategoryType: Autodesk.Revit.DB.CategoryType.Model } cat)
                    continue;
                if (categories is not null && !categories.Contains(cat.BuiltInCategory))
                    continue;
                var (faces, failed) = Faces(e, options);
                var near = new NearbyElement(e.UniqueId, cat.BuiltInCategory.ToString(), e.Name, (e as FamilyInstance)?.Host?.UniqueId,
                                             faces, failed, BoxOf(e), Id(e.DemolishedPhaseId), Id(e.DesignOption?.Id));
                if (band is not null)
                {
                    var (banded, bandFailed, openShells) = InBand(e, band, options);
                    near = near with { Banded = banded, BandFailed = bandFailed, OpenShells = openShells };
                }
                list.Add(near);
            }
            return list;
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.ArgumentException)
        {
            return null;
        }
    }

    private static string Category(Element e) => e.Category is { } c ? c.BuiltInCategory.ToString() : "";

    private static RevitBox? BoxOf(Element e) =>
        e.get_BoundingBox(null) is { } b ? new RevitBox(P(b.Min), P(b.Max), b.Transform is { IsIdentity: false } bt ? T(bt) : null) : null;

    /// <summary>Every face of the element's solids (a family's instance geometry included), and whether anything in its
    /// geometry couldn't be read as faces (a mesh, <c>get_Geometry</c> throwing, an instance with no geometry, a kind
    /// not read, or a face Revit gives no edges or triangles for: then no faces at all).</summary>
    private static (List<SurfaceRecord>? Faces, bool Failed) Faces(Element e, Options options)
    {
        var faces = new List<SurfaceRecord>();
        var failed = false;
        var unreadable = false;
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                switch (o)
                {
                    case Solid s:
                        foreach (Face f in s.Faces)
                        {
                            // a face Revit gives no edges or triangles for (seen on real families: the Pacific
                            // Continental sample, 2026-11-20) can't be read: the element's geometry counts as failed,
                            // the cautious side, never a crash and never skipped
                            if (Surface(f) is { } face)
                                faces.Add(face);
                            else
                                unreadable = true;
                        }
                        break;
                    case GeometryInstance gi:
                        if (gi.GetInstanceGeometry() is { } inner)
                            Walk(inner);
                        else
                            failed = true;           // an instance with no geometry to read (round 5: as InBand)
                        break;
                    case GeometryElement nested:
                        Walk(nested);
                        break;
                    case Curve or PolyLine or Point:
                        break;                       // lines and points: no body
                    default:
                        failed = true;               // a mesh over a room isn't read exactly, nor a kind not read
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
        // a face Revit couldn't give: none of the element's faces is passed on (its others alone could put a wall's
        // far face where its near one is, review round 1), only that its geometry failed
        return unreadable ? (null, true) : (faces, failed);
    }

    /// <summary>A face as the reader's record, or null when Revit can't give its edges or its triangles.</summary>
    private static SurfaceRecord? Surface(Face f)
    {
        try
        {
            if (f.GetEdgesAsCurveLoops() is not { } edges)
                return null;
            var loops = edges
                .Select(l => (IReadOnlyList<LoopCurve>)l.Select(c => new LoopCurve(P(c.GetEndPoint(0)), c is Line)).ToList()).ToList();
            if (f is PlanarFace pf)
                return new SurfaceRecord(true, P(pf.FaceNormal), loops, loops.SelectMany(l => l.Select(c => c.Start)).ToList());
            if (f.Triangulate() is not { Vertices: { Count: > 0 } vertices })
                return null;
            return new SurfaceRecord(false, new Xyz(0, 0, 0), loops, vertices.Select(P).ToList());
        }
        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException or Autodesk.Revit.Exceptions.InvalidOperationException)
        {
            return null;
        }
    }

    // ---- a window or door ---------------------------------------------------------------------------------------

    private static OpeningRecord OpeningOf(Document doc, FamilyInstance fi, Phase? phase)
    {
        var type = doc.GetElement(fi.GetTypeId());
        var level = doc.GetElement(fi.LevelId) as Level;
        var (width, height) = TypeSize(type);
        var options = new Options { DetailLevel = ViewDetailLevel.Fine, IncludeNonVisibleObjects = false };
        var (faces, failed) = Faces(fi, options);
        var cut = fi.Host is Wall wall ? Cut(wall, fi, options) : (null, null, ["its host isn't a wall"], false);
        return new OpeningRecord
        {
            UniqueId = fi.UniqueId,
            FromRoom = phase is null ? null : fi.get_FromRoom(phase)?.UniqueId,
            ToRoom = phase is null ? null : fi.get_ToRoom(phase)?.UniqueId,
            Host = fi.Host?.UniqueId,
            HostIsWall = fi.Host is Wall,
            LevelElevation = level?.ProjectElevation,
            LevelId = level?.UniqueId,
            WallSides = SidesOf(fi.Host),
            SillHeight = fi.get_Parameter(BuiltInParameter.INSTANCE_SILL_HEIGHT_PARAM) is { HasValue: true } s ? s.AsDouble() : null,
            Location = fi.Location is LocationPoint lp ? P(lp.Point) : null,
            Along = P(fi.HandOrientation),
            TypeWidth = width,
            TypeHeight = height,
            TypeLengths = type is null ? new Dictionary<string, double>() : Lengths(type),
            Placed = failed || faces is null || faces.Count == 0 ? null : faces.SelectMany(f => f.Points).ToList(),
            WallOpening = cut.Points,
            WallOpeningBy = cut.By,
            WallOpeningUnread = cut.Unread,
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
        return (Get(BuiltInParameter.WINDOW_WIDTH, BuiltInParameter.DOOR_WIDTH, BuiltInParameter.FAMILY_WIDTH_PARAM),
                Get(BuiltInParameter.WINDOW_HEIGHT, BuiltInParameter.DOOR_HEIGHT, BuiltInParameter.FAMILY_HEIGHT_PARAM));
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
    private static (List<Xyz>? Points, string? By, List<string> Words, bool Unread) Cut(Wall wall, FamilyInstance fi, Options options)
    {
        var words = new List<string>();
        var faces = new List<(Face Face, List<Xyz> Points, ICollection<ElementId> By)>();
        var unreadable = 0;
        void Walk(GeometryElement g)
        {
            foreach (var o in g)
            {
                if (o is Solid s)
                {
                    foreach (Face f in s.Faces)
                    {
                        // a face Revit gives no edges for, or that throws (as Surface: the Pacific Continental sample,
                        // 2026-11-20), can't be read: it may be the one this window cut, so the cut is unread below
                        try
                        {
                            if (f.GetEdgesAsCurveLoops() is { } loops)
                                faces.Add((f, loops.SelectMany(l => l.Select(c => P(c.GetEndPoint(0)))).ToList(),
                                           wall.GetGeneratingElementIds(f)));
                            else
                                unreadable++;
                        }
                        catch (Exception x) when (x is Autodesk.Revit.Exceptions.ApplicationException
                                                       or Autodesk.Revit.Exceptions.InvalidOperationException)
                        {
                            unreadable++;
                        }
                    }
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
            return (null, null, words, true);
        }
        if (unreadable > 0)
        {
            // never the faces that could be read alone: the bottom of the cut could be on the one that couldn't
            words.Add($"{unreadable} of the wall's faces couldn't be read (Revit gave no edges for them, or refused): " +
                      "the opening this window cuts is unread");
            return (null, null, words, true);
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
            return (named, "the wall's faces Revit says this window generated (GetGeneratingElementIds)", words, false);
        // nothing else stands in for it: HostObject.FindInserts listed no inserts at all even on walls the windows did
        // cut (trial run 6, Revit 2027.4), so it is no evidence either way and isn't used
        words.Add("no face of the wall names this window as generating it: the window cut nothing found");
        return (null, null, words, false);
    }

    internal static Xyz P(XYZ p) => new(p.X, p.Y, p.Z);

    private static Reading.Transform3 T(Transform t) => new(P(t.Origin), P(t.BasisX), P(t.BasisY), P(t.BasisZ));
}
