namespace Gordium.Revit.Reading;

/// <summary>A floor read as a site slab, with what its <see cref="Marks.SiteSlab"/> mark says: <see cref="Kind"/>
/// null when not stated (never set, or a word not in <see cref="SlabKinds"/>); <see cref="Word"/> what was typed.</summary>
public sealed record SiteSlab(RevitElement Floor, SlabKind? Kind, string? Word);

/// <summary>
/// Site slabs (reading design note, section 1, "Site slabs"): a Revit Floor is a building part (design note, section 1,
/// row 1), but a concrete pad, a patio, a driveway or a walk is drawn with the same Floor tool, and Chapter 325 counts
/// them differently: porches, decks, landings and ramps are "part of the building in both the determination of required
/// yards and lot coverage" (§325-18A); building area "shall not include parking areas and parking spaces", and
/// "terraces and patios shall be exempt from total lot coverage requirements" (§325-3B BUILDING AREA).
/// <para>The rule: a <b>site slab</b> is a Floor (a system floor, <see cref="ElementKind.Ordinary"/>, with no Gordium
/// mark of the outside reader's own) in the design checked whose plan box (Revit's own box) overlaps, by more than the
/// model's vertex tolerance both ways, the plan box of no wall and no roof in the design checked. Every other Floor is
/// part of the building, as before, whatever it is marked. Either way a wrong sorting is never a false pass: a floor
/// of the house read as a site slab, unmarked, makes lot coverage and the yards need review; a site slab read as part
/// of the house is measured as part of it, as every floor was before (at worst a failure to look at, never a pass).
/// Boxes are the cautious side of that: a patio near a diagonal wall or under the eaves is read as part of the house.
/// A floor with no box of its own is part of the building (read as before); a wall or roof with none can't hold one.</para>
/// <para>A site slab is read by its mark: a porch, deck, landing or ramp as a building (as every floor was); a patio,
/// terrace or walk, or parking or a driveway, and an unmarked one, as a left-out object whose <c>slab</c> says which
/// (site description, <c>left_out[].slab</c>), so it is never measured and the checker decides its rows.</para>
/// </summary>
public static class SiteSlabs
{
    /// <summary>The building parts a floor of the house sits under or on: walls and roofs, by built-in name.</summary>
    public static readonly IReadOnlySet<string> HouseParts = new HashSet<string> { "OST_Walls", "OST_Roofs" };

    /// <summary>Every site slab in the design checked, by UniqueId.</summary>
    public static IReadOnlyDictionary<string, SiteSlab> Find(RevitModel model)
    {
        var (floors, house) = Sort(model);
        var found = new Dictionary<string, SiteSlab>();
        foreach (var (f, box) in floors)
            if (!house.Any(h => Overlaps(box, h, model.VertexTolerance)))
            {
                var word = Marks.Text(Mark(f));
                found[f.UniqueId] = new SiteSlab(f, SlabKinds.Of(word), word);
            }
        return found;
    }

    /// <summary>The floors in the design checked marked with <see cref="Marks.SiteSlab"/> that aren't site slabs (they
    /// sit under or on a wall or roof): part of the building, their mark not read. The marking list says so.</summary>
    public static IReadOnlyList<RevitElement> MarkedInHouse(RevitModel model)
    {
        var slabs = Find(model);
        return model.Elements.Where(e => IsFloor(e) && Looked(model, e) && !slabs.ContainsKey(e.UniqueId)
                                         && Marks.Text(Mark(e)) is not null).ToList();
    }

    /// <summary>How far into the lot a slab must reach to be read (<c>host_core.left_out.ON_LOT_REACH</c>, ft): the
    /// check drops one that doesn't (objects.left_out), so the marking list never asks for it.</summary>
    public const double OnLotReach = 0.1;

    /// <summary>The site slabs the check reads, for the marking list: those whose plan box reaches into the lot (the
    /// one closed property line, as the reader finds it with no lot picked) by more than <see cref="OnLotReach"/>,
    /// averaged across (twice the area of the box inside the lot over its perimeter: <c>reaches_into_lot</c>'s test,
    /// on the box, which is never smaller than the slab, so a slab the check reads is never missed); and the others,
    /// which the check drops. With no lot found the check reads none: every slab is off the lot.</summary>
    public static (IReadOnlyList<SiteSlab> OnLot, IReadOnlyList<SiteSlab> OffLot, bool LotFound) OnLot(RevitModel model)
    {
        var all = Find(model).Values.ToList();
        var lot = LotReader.Read(model, null, Transform3.Identity, []);
        if (lot is null)
            return ([], all, false);
        var on = all.Where(s => Read.RevitBox(s.Floor, Transform3.Identity) is { } b && Reaches(lot.Ring, b)).ToList();
        return (on, all.Except(on).ToList(), true);
    }

    /// <summary>Whether a plan box reaches into a lot outline by more than <see cref="OnLotReach"/>, averaged across:
    /// the outline clipped to the box (the box is convex, so clipping any outline by it is exact).</summary>
    internal static bool Reaches(List<(double X, double Y)> ring, Box3 box)
    {
        var part = ring.ToList();
        bool In(int edge, (double X, double Y) p) => edge switch
        {
            0 => p.X >= box.Min.X, 1 => p.X <= box.Max.X, 2 => p.Y >= box.Min.Y, _ => p.Y <= box.Max.Y,
        };
        (double X, double Y) Cut(int edge, (double X, double Y) a, (double X, double Y) b)
        {
            var t = edge switch
            {
                0 => (box.Min.X - a.X) / (b.X - a.X), 1 => (box.Max.X - a.X) / (b.X - a.X),
                2 => (box.Min.Y - a.Y) / (b.Y - a.Y), _ => (box.Max.Y - a.Y) / (b.Y - a.Y),
            };
            return (a.X + t * (b.X - a.X), a.Y + t * (b.Y - a.Y));
        }
        for (var edge = 0; edge < 4 && part.Count > 0; edge++)
        {
            var next = new List<(double X, double Y)>();
            for (var i = 0; i < part.Count; i++)
            {
                var (a, b) = (part[i], part[(i + 1) % part.Count]);
                if (In(edge, b))
                {
                    if (!In(edge, a))
                        next.Add(Cut(edge, a, b));
                    next.Add(b);
                }
                else if (In(edge, a))
                    next.Add(Cut(edge, a, b));
            }
            part = next;
        }
        if (part.Count < 3)
            return false;
        double area = 0, perimeter = 0;
        for (var i = 0; i < part.Count; i++)
        {
            var (a, b) = (part[i], part[(i + 1) % part.Count]);
            area += a.X * b.Y - b.X * a.Y;
            perimeter += Math.Sqrt((b.X - a.X) * (b.X - a.X) + (b.Y - a.Y) * (b.Y - a.Y));
        }
        // |shoelace| = 2 × area; a sliver of a slab (no wider than twice the reach) inside the lot at all is kept: the
        // check's own test also reads a thin one by how deep it stands, which the averaged width can't see
        var sliver = Math.Min(box.Max.X - box.Min.X, box.Max.Y - box.Min.Y) <= 2 * OnLotReach;
        return perimeter > 0 && (Math.Abs(area) / perimeter > OnLotReach || sliver && Math.Abs(area) > 0);
    }

    private static MarkValue? Mark(RevitElement e) =>
        e.InstanceMarks.TryGetValue(Marks.SiteSlab.Guid, out var v) ? v : null;

    private static bool IsFloor(RevitElement e) =>
        e.BuiltInCategory == Marks.Floors && e.Kind == ElementKind.Ordinary && e.Mark == GordiumMark.None;

    private static bool Looked(RevitModel model, RevitElement e) => SiteReader.Looked(e) && SiteReader.OnLotNow(model, e);

    private static (List<(RevitElement Floor, Box3 Box)> Floors, List<Box3> House) Sort(RevitModel model)
    {
        var floors = new List<(RevitElement, Box3)>();
        var house = new List<Box3>();
        foreach (var e in model.Elements.Where(e => Looked(model, e)))
        {
            if (Read.RevitBox(e, Transform3.Identity) is not { } box)
                continue;
            if (IsFloor(e))
                floors.Add((e, box));
            else if (HouseParts.Contains(e.BuiltInCategory))
                house.Add(box);
        }
        return (floors, house);
    }

    /// <summary>Whether two boxes overlap in plan by more than <paramref name="tolerance"/> both ways (touching at an
    /// edge is not overlapping: a patio poured against the wall's outer face is outside the house).</summary>
    internal static bool Overlaps(Box3 a, Box3 b, double tolerance) =>
        Math.Min(a.Max.X, b.Max.X) - Math.Max(a.Min.X, b.Min.X) > tolerance
        && Math.Min(a.Max.Y, b.Max.Y) - Math.Max(a.Min.Y, b.Min.Y) > tolerance;
}
