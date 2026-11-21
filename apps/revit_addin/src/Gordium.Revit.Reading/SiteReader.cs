using System.Globalization;
using System.Text.Json.Nodes;

namespace Gordium.Revit.Reading;

/// <summary>What one read of the model gives: the site description, and what the panel and the report must name
/// beside the verdicts (the phase and the design options checked: a false-pass risk if the architect thinks another
/// was checked; design note, section 1).</summary>
/// <param name="Site">The <c>gordium.site/1</c> description, the same JSON the Rhino plugin sends.</param>
/// <param name="PhaseChecked">The last phase's id (the finished design), or null for a model with no phases.</param>
/// <param name="OptionsChecked">Each design option set's option checked, as "set: option".</param>
public sealed record ReadResult(JsonObject Site, string? PhaseChecked, IReadOnlyList<string> OptionsChecked);

/// <summary>A model the reader won't describe (a grade marker with no place, the terrain asked for): no
/// description, so no verdicts, never a guess.</summary>
public sealed class ReadRefusedException(string message) : Exception(message);

/// <summary>
/// The Revit reader: a model (<see cref="RevitModel"/>, filled from the Revit API by the Revit layer) turned into
/// the site description, with the decisions of docs/revit/revit_reading_design.md. It copies the Rhino reader's
/// decisions and invents none; which objects are left out and which touch the house it asks of the worker
/// (<see cref="ILeftOutAsker"/>, <c>objects.left_out</c>). The one rule behind every step (principle 4, never a
/// false pass): anything it can't read exactly is reported with a problem code, never guessed or dropped.
/// </summary>
public static class SiteReader
{
    /// <summary>The building categories (design note, section 1, row 1), by built-in name: one building each, but a
    /// floor outside the house not marked a porch, deck, landing or ramp (a site slab: <see cref="SiteSlabs"/>).</summary>
    public static readonly IReadOnlySet<string> BuildingCategories = new HashSet<string>
    {
        "OST_Walls", "OST_Floors", "OST_Roofs", "OST_Columns", "OST_StructuralColumns", "OST_Stairs",
        "OST_StairsRailing", "OST_Ramps", "OST_Doors", "OST_Windows", "OST_CurtainWallPanels",
        "OST_CurtainWallMullions",
    };

    /// <summary>Categories never looked at (design note, section 1: lines, levels, grids, reference planes, rooms,
    /// areas, views; no solid, so not a building). Property lines are read as the lot, never as a building.</summary>
    public static readonly IReadOnlySet<string> NotLookedAt = new HashSet<string>
    {
        "OST_Lines", "OST_Levels", "OST_Grids", "OST_CLines", "OST_Rooms", "OST_Areas", "OST_Views", "OST_Cameras",
        "OST_SiteProperty", "OST_SitePropertyLineSegment", "OST_VolumeOfInterest", "OST_Matchline", "OST_SectionBox",
        "OST_MEPSpaces", "OST_SharedBasePoint", "OST_ProjectBasePoint",
    };

    /// <summary>Categories whose elements can't be a structure (reading design note, section 1, "Objects standing
    /// apart"): trees and plants, and people and cars placed for show, aren't "constructed or erected on the ground"
    /// (§325-3B STRUCTURE), so one standing apart from the house keeps no yard waiting (<c>could_be_building: false</c>).
    /// Still left out (an object on the lot not measured: lot coverage needs review, as before).</summary>
    public static readonly IReadOnlySet<string> NotStructures = new HashSet<string> { "OST_Planting", "OST_Entourage" };

    /// <summary>More plan points than this and the box's corners are sent instead (as Rhino's <c>_plan_points</c>).</summary>
    public const int MaxPlanPoints = 50000;

    /// <summary>How near a left-out object's plan box must come to the lot's on every side to look like the ground
    /// (ft; <c>rhino_logic.looks_like_ground</c>'s reach).</summary>
    public const double GroundReach = 1.0;

    /// <summary>What a linked model is called when it is sent as an object that couldn't be.</summary>
    public const string LinkedModelKind = "a linked model";

    /// <summary>The status a loaded link's definition is sent with: its contents are the design
    /// (<c>host_core.left_out.BLOCK_CONTENTS_KNOWN</c>).</summary>
    public const string LinkKnown = "LinkedFileIsUpToDate";

    /// <summary>The status a family's or a CAD import's definition is sent with: not linked to a file.</summary>
    public const string NotLinked = "NotALinkedInstanceDefinition";

    /// <summary>The status a coordination model's definition is sent with: what it holds isn't read, so it is not one
    /// of <c>host_core.left_out.BLOCK_CONTENTS_KNOWN</c> (contents_not_known: on the lot and touching).</summary>
    public const string CoordinationModelStatus = "CoordinationModelNotRead";

    /// <summary>The model as a site description, with the lot facts the architect saved (<c>lot_id</c>,
    /// <c>grade_from</c>, the street lines: in shared coordinates).</summary>
    public static async Task<ReadResult> DescribeAsync(RevitModel model, JsonObject facts, ILeftOutAsker asker,
                                                       CancellationToken cancel = default)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentNullException.ThrowIfNull(facts);
        ArgumentNullException.ThrowIfNull(asker);
        var read = new Read(model);
        var problems = new List<JsonObject>();
        var lot = LotReader.Read(model, facts["lot_id"]?.GetValue<string>(), read.ToShared, problems);
        foreach (var e in Fold(model.Elements))
            if (Looked(e) && OnLotNow(model, e))
                read.Element(e);

        if (read.LotInLink)
            problems.Add(Problem("lot_block", ("layer", LotReader.LotLayer)));
        var leftOut = new JsonArray();
        if (read.Candidates.Count > 0)
        {
            var objects = new JsonArray(read.Candidates.Select(c => (JsonNode)c.Sent).ToArray());
            var boxes = read.BuildingBoxes.Select(b => (JsonNode)new JsonArray(b.ToArray().Select(v => (JsonNode)v).ToArray())).ToList();
            if (read.BuildingBoxes.Count > 1)        // the box around all of them together (design note, section 4)
                boxes.Add(new JsonArray(read.BuildingBoxes.Aggregate((a, b) => a.Union(b)).ToArray().Select(v => (JsonNode)v).ToArray()));
            var lotSent = lot is null ? null : new JsonObject
            {
                ["ring"] = new JsonArray(lot.Ring.Select(p => (JsonNode)new JsonArray(p.X, p.Y)).ToArray()),
                ["box"] = new JsonArray(lot.Ring.Min(p => p.X), lot.Ring.Min(p => p.Y), lot.Ring.Max(p => p.X), lot.Ring.Max(p => p.Y)),
            };
            var decisions = await asker.AskAsync(lotSent, objects, new JsonArray(boxes.ToArray()), read.Definitions, cancel).ConfigureAwait(false);
            if (decisions.Count != read.Candidates.Count)
                throw new InvalidOperationException("objects.left_out answered for a different number of objects than sent");
            for (var i = 0; i < decisions.Count; i++)
            {
                var (c, d) = (read.Candidates[i], decisions[i]);
                if (d.Id != c.Id)
                    throw new InvalidOperationException($"objects.left_out's answer {i + 1} is for {d.Id}, not {c.Id}");
                if (!d.LeftOut)
                    continue;
                var entry = new JsonObject
                {
                    ["id"] = c.Id, ["layer"] = c.Layer, ["could_be_building"] = c.CouldBeBuilding, ["touching"] = d.Touching,
                    ["ground_like"] = d.Touching is not null && lot is not null && c.Box is { } b
                                      && LooksLikeGround(c.GroundKind, c.Closed, b, lot.Ring),
                    ["context"] = c.Context,
                };
                if (c.Slab is not null)          // a site slab (SiteSlabs): what it is marked, and its name to say so
                    entry["slab"] = c.Slab;
                // its name, so a row can say which: a slab's, and one standing apart's (it keeps the yards waiting)
                if ((c.Slab is not null || d.Touching is false) && c.Name is { Length: > 0 } name)
                    entry["name"] = name;
                leftOut.Add(entry);
            }
        }

        return new ReadResult(new JsonObject
        {
            ["schema"] = "gordium.site/1",
            ["units"] = "ft",
            ["host"] = new JsonObject
            {
                ["name"] = "revit", ["version"] = model.Version, ["document"] = model.Document,
                ["model_units"] = model.DisplayUnits,
            },
            ["lot"] = lot?.Json,
            ["buildings"] = new JsonArray(read.Buildings.Select(b => (JsonNode)b).ToArray()),
            ["unsent"] = new JsonArray(read.Unsent.Select(u => (JsonNode)u).ToArray()),
            ["left_out"] = leftOut,
            ["grade"] = Grade(read, facts),
            ["inventory_complete"] = read.InventoryComplete,
            ["problems"] = new JsonArray(problems.Select(p => (JsonNode)p).ToArray()),
        }, model.Phases.Count > 0 ? model.Phases[^1] : null, OptionsChecked(model));
    }

    // ---- which elements: looked at, and on the lot in the design checked ---------------------------------------

    /// <summary>Whether the element is looked at at all: a model element, not drawn in one view only, not a
    /// category with no building in it, not a model group (its members are read on their own).</summary>
    /// <remarks>A linked model, a coordination model or a CAD import is looked at whatever type Revit gives its category (whether "RVT
    /// Links" is a model category is to check): skipping one would skip a house it holds.</remarks>
    internal static bool Looked(RevitElement e) =>
        (e.CategoryType == CategoryType.Model || e.Kind is ElementKind.LinkInstance or ElementKind.CadImport or ElementKind.CoordinationModel)
        && !e.ViewSpecific && !NotLookedAt.Contains(e.BuiltInCategory) && e.Kind != ElementKind.Group;

    /// <summary>Shared nested families (sub-components) read as part of the family they sit in (design note, section
    /// 1, "Nested families"): Revit lists each as its own element, outside its host's geometry, where Rhino reads a
    /// nested block as part of its block. So each sub-component, at any depth, is added to its host's geometry as one
    /// nested instance and not read on its own: what it gives, placed as Revit places it (its geometry is already in
    /// the model's coordinates); nothing that could be a building (no face: an empty family, lines only) as a nested
    /// family that gives nothing, so its host's place can't be told (touching: null), as a family on its own with
    /// nothing in it; and one whose geometry can't be read makes its host's unreadable. Never folded, so read on
    /// their own as before (more is only more cautious): a sub-component that is a building part (a building category, a floor block, or marked a porch, deck,
    /// landing, ramp, garage, shed or carport: IsBuildingPart) (a window in a kit family is a building wherever it sits, and a linked model holding one still holds a
    /// building: review round 1); one whose host isn't in the list; and one whose chain of hosts never reaches an
    /// element that isn't a sub-component (a loop: Revit can't make one, but nothing is ever dropped for it).</summary>
    internal static IReadOnlyList<RevitElement> Fold(IReadOnlyList<RevitElement> elements)
    {
        var byId = new Dictionary<string, RevitElement>();
        foreach (var e in elements)
            byId.TryAdd(e.UniqueId, e);
        var folded = elements.Where(e => e.SuperComponent is { } h && byId.ContainsKey(h) && FoldsInto(e, byId)).ToList();
        if (folded.Count == 0)
            return elements.Select(Coarser).ToList();
        var subs = folded.GroupBy(e => e.SuperComponent!).ToDictionary(g => g.Key, g => g.ToList());
        // inBuilding: e is a building part, or sits in one at any depth (review round 2: only the direct host was
        // looked at, so a part two levels down still sent its coarser drawing as the building's faces)
        RevitElement With(RevitElement e, bool inBuilding)
        {
            if (!subs.TryGetValue(e.UniqueId, out var held))
                return e;
            var geometry = new List<GeometryItem>(e.Geometry ?? []);
            var failed = e.GeometryFailed;
            var building = inBuilding || IsBuildingPart(e);
            var coarser = new List<GeometryItem>();
            // in a building, a part's coarser drawing (and its own parts', at any depth) is carried up to be weighed
            // against the building's Fine faces, never sent as faces (review rounds 1, 2); elsewhere it is read as
            // part of the part
            foreach (var sub in held.Select(s => building ? With(s, true) : Coarser(With(s, false))))
            {
                if (building && sub.CoarserGeometry is { Count: > 0 } subCoarser)
                    coarser.Add(new InstanceItem(subCoarser));
                failed |= sub.GeometryFailed;
                geometry.Add(new InstanceItem(sub.Geometry is { } g && AnyFace(g) || sub.Geometry is { } o && AnyOther(o) ? sub.Geometry : null));
            }
            return coarser.Count == 0 ? e with { Geometry = geometry, GeometryFailed = failed }
                : e with { Geometry = geometry, GeometryFailed = failed, CoarserGeometry = [.. e.CoarserGeometry ?? [], .. coarser] };
        }
        var gone = folded.Select(e => e.UniqueId).ToHashSet();
        return elements.Where(e => !gone.Contains(e.UniqueId)).Select(e => Coarser(With(e, false))).ToList();
    }

    /// <summary>A family's geometry at the coarser detail levels (Medium and Coarse), read as part of it (reading
    /// design note, section 8, "Detail level"), for any element but a building part (a building's faces are sent from
    /// Fine alone: ElementReader.Building weighs its coarser geometry itself): added to its geometry as one nested
    /// instance, so a part drawn only at a coarser level makes its box, its footprint and its definition's parts
    /// bigger, never smaller. It only ever enlarges a known shape: a family with no face at Fine is left as it is (no
    /// box, touching unknown), never given a place by its coarser drawing alone.</summary>
    public static RevitElement Coarser(RevitElement e)
    {
        if (IsBuildingPart(e) || Drawn(e.CoarserGeometry) is not { Count: > 0 } more || e.Geometry is not { } fine || !AnyFace(fine))
            return e;
        return e with { Geometry = [.. fine, new InstanceItem(more)], CoarserGeometry = null };
    }

    /// <summary>What a coarser detail level actually draws: its items with every nested family that gives nothing
    /// there (at any depth) left out, since a part shown at Fine only is already read from Fine and draws nothing to
    /// add (review round 1); a piece of a kind the reader doesn't know is kept. Null for none.</summary>
    public static IReadOnlyList<GeometryItem>? Drawn(IReadOnlyList<GeometryItem>? items)
    {
        if (items is null)
            return null;
        var kept = new List<GeometryItem>();
        foreach (var i in items)
            if (i is InstanceItem inst)
            {
                if (Drawn(inst.Items) is { Count: > 0 } inner)
                    kept.Add(new InstanceItem(inner));
            }
            else
                kept.Add(i);
        return kept.Count > 0 ? kept : null;
    }

    /// <summary>Whether a sub-component is folded into its host: it isn't a building part (a building category, a
    /// floor block, or marked a porch, deck, landing, ramp, garage, shed or carport: IsBuildingPart), its host is in the list, and its chain of hosts has no loop. The chain ends at the first element
    /// that is read on its own (one with no host in the list, or a building part), which every folded part above
    /// it reaches.</summary>
    private static bool FoldsInto(RevitElement e, Dictionary<string, RevitElement> byId)
    {
        if (IsBuildingPart(e) || e.SuperComponent is not { } first || first == e.UniqueId || !byId.ContainsKey(first))
            return false;
        var seen = new HashSet<string> { e.UniqueId };
        var at = e;
        while (at.SuperComponent is { } h && h != at.UniqueId && byId.TryGetValue(h, out var host))
        {
            if (!seen.Add(h))
                return false;            // a loop (Revit can't make one): every element in it read on its own
            if (IsBuildingPart(host))
                return true;             // never folded itself: the chain ends here
            at = host;
        }
        return true;
    }

    /// <summary>Whether the element is read as a building (the reader's switch and <see cref="Fold"/>/<see cref="Coarser"/>
    /// ask this one predicate, so they can't drift: review round 2): a floor block, a building category, or an element
    /// marked a porch, deck, landing, ramp, garage, shed or carport (<see cref="Marks.SiteObject"/>; never a context
    /// object or another Gordium marker, whose mark isn't read). A building's faces are Fine's alone, its coarser
    /// drawing weighed (it may be bigger than measured), never added as faces.</summary>
    internal static bool IsBuildingPart(RevitElement e) =>
        e.Mark == GordiumMark.FloorBlock || BuildingCategories.Contains(e.BuiltInCategory)
        || e.Mark == GordiumMark.None && Read.SiteObject(e) is SiteObjectKind.Building;

    private static bool AnyFace(IEnumerable<GeometryItem> items) => items.Any(i => i switch
    {
        SolidItem s => s.Faces.Count > 0,
        MeshItem m => m.Triangles.Count > 0,
        InstanceItem { Items: { } inner } => AnyFace(inner),
        _ => false,
    });

    private static bool AnyOther(IEnumerable<GeometryItem> items) => items.Any(i => i switch
    {
        OtherItem => true,
        InstanceItem { Items: { } inner } => AnyOther(inner),
        _ => false,
    });

    /// <summary>Whether the element is on the lot in the design checked (proposed, design note, section 1):
    /// <list type="bullet">
    /// <item><b>Phases.</b> The last phase is checked. Left out only what is gone by then: an element demolished in
    /// any of the document's phases (demolished in the last one, temporary in it, or demolished before it). An
    /// element with no phase, or a phase the document doesn't list, is kept: never a list of statuses to keep, which
    /// would drop an element whose status isn't on it.</item>
    /// <item><b>Design options.</b> The main model, and from every option set one option: the one being edited if
    /// it is in that set, else the set's primary. An option the reader can't place (no set holds it, or its set has
    /// no primary) is kept: an extra object can only make the check more cautious.</item>
    /// </list></summary>
    internal static bool OnLotNow(RevitModel model, RevitElement e) => InDesignChecked(model, e.PhaseDemolished, e.DesignOption);

    /// <summary><see cref="OnLotNow(RevitModel, RevitElement)"/>'s rule for any element: by when it is demolished and
    /// its design option (the interior's rooms, windows and doors use the same one place: interior note, section 4).</summary>
    internal static bool InDesignChecked(RevitModel model, string? phaseDemolished, string? designOption)
    {
        if (phaseDemolished is { } gone && model.Phases.Contains(gone))
            return false;
        return designOption is not { } option || Chosen(model, option) is not { } chosen || chosen.Id == option;
    }

    /// <summary>The option checked from the set that holds <paramref name="option"/>, or null when no set holds
    /// it or the set has neither the option being edited nor a primary.</summary>
    private static DesignOptionRecord? Chosen(RevitModel model, string option)
    {
        var set = model.OptionSets.FirstOrDefault(s => s.Options.Any(o => o.Id == option));
        return set?.Options.FirstOrDefault(o => o.Id == model.ActiveOption) ?? set?.Options.FirstOrDefault(o => o.IsPrimary);
    }

    private static List<string> OptionsChecked(RevitModel model) =>
        model.OptionSets.Select(s => $"{s.Name}: " + ((s.Options.FirstOrDefault(o => o.Id == model.ActiveOption)
                                                        ?? s.Options.FirstOrDefault(o => o.IsPrimary))?.Name
                                                       ?? "every option (the set has no primary)")).ToList();

    // ---- the ground ------------------------------------------------------------------------------------------

    /// <summary>The grade: the source the facts name (<c>grade_from</c>), never whichever markers happen to exist;
    /// no points read means none sent (as <c>gordium_rhino.check_facts</c>). Terrain isn't read yet.</summary>
    private static JsonObject Grade(Read read, JsonObject facts)
    {
        var from = facts["grade_from"]?.GetValue<string>();
        List<Xyz>? points = from switch
        {
            null => null,
            "spot" => read.SpotGrades,
            "finished_spots" => read.FinishedGrades,
            "terrain" => throw new ReadRefusedException(
                "the ground is set to come from a Toposolid, which the Revit reader doesn't sample yet: set spot grades or a flat ground"),
            _ => throw new ReadRefusedException($"grade_from is {from}: one of spot, finished_spots or terrain"),
        };
        if (points is null || points.Count == 0)
            return new JsonObject { ["source"] = "none", ["points"] = new JsonArray() };
        return new JsonObject
        {
            ["source"] = from,
            ["points"] = new JsonArray(points.Select(p => (JsonNode)new JsonArray(p.X, p.Y, p.Z)).ToArray()),
        };
    }

    /// <summary><c>rhino_logic.looks_like_ground</c>, copied: an open mesh or surface (never a closed solid, a family,
    /// a link) whose plan box spans the lot's, give or take <see cref="GroundReach"/>. Only a label for the panel's
    /// "This is the ground"; nothing is ever left out on it.</summary>
    internal static bool LooksLikeGround(string kind, bool closed, Box3 box, List<(double X, double Y)> ring)
    {
        if (closed || kind is not ("Mesh" or "Brep"))
            return false;
        double a0 = ring.Min(p => p.X), b0 = ring.Min(p => p.Y), a1 = ring.Max(p => p.X), b1 = ring.Max(p => p.Y);
        return box.Min.X <= a0 + GroundReach && box.Min.Y <= b0 + GroundReach
               && box.Max.X >= a1 - GroundReach && box.Max.Y >= b1 - GroundReach;
    }

    internal static JsonObject Problem(string code, params (string Key, string Value)[] args)
    {
        var a = new JsonObject();
        foreach (var (k, v) in args)
            a[k] = v;
        return new JsonObject { ["code"] = code, ["args"] = a };
    }

    internal static string Number(double v) => v.ToString("R", CultureInfo.InvariantCulture);
}
