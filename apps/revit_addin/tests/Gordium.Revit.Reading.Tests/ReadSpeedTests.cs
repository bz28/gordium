using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The inside read's speed-ups (Snowdon Towers, read_steps 2026-11-22), each one that can't change what is
/// read: the box test that lets a solid's cut be skipped (Revit-free, <see cref="Box3.ApartFrom"/>), and the Revit
/// layer's hooks pinned in its source (it builds only on Windows with Revit).</summary>
public sealed class ReadSpeedTests
{
    private static string Addin(string file) =>
        File.ReadAllText(Path.Combine(Env.Repo, "apps", "revit_addin", "src", "Gordium.Revit.Addin", file)).Replace("\r\n", "\n");

    private static Box3 B(double x0, double y0, double z0, double x1, double y1, double z1) => new(new(x0, y0, z0), new(x1, y1, z1));

    [Fact]
    public void Boxes_are_apart_only_when_a_gap_wider_than_the_margin_lies_between_them_along_some_axis()
    {
        var band = B(0, 0, 0, 10, 10, 6.6);
        // a floor 3 ft above the band's top, one to the side, one below: apart, either way round
        foreach (var other in new[] { B(0, 0, 9.6, 10, 10, 10.6), B(12, 0, 0, 20, 10, 6), B(0, -30, 0, 10, -2, 6), B(0, 0, -5, 10, 10, -1.5) })
        {
            Assert.True(other.ApartFrom(band, 1.0));
            Assert.True(band.ApartFrom(other, 1.0));
        }
        // overlapping, touching, or apart by the margin or less: never apart (the solid is cut, as always)
        foreach (var other in new[] { B(5, 5, 5, 15, 15, 15), B(10, 0, 0, 20, 10, 6), B(0, 0, 6.6, 10, 10, 8), B(0, 0, 7.6, 10, 10, 8), B(10.5, 0, 0, 20, 10, 6) })
        {
            Assert.False(other.ApartFrom(band, 1.0));
            Assert.False(band.ApartFrom(other, 1.0));
        }
        // a gap wider than no margin at all is apart; a box inside the other is not
        Assert.True(B(10.5, 0, 0, 20, 10, 6).ApartFrom(band, 0));
        Assert.False(B(2, 2, 2, 3, 3, 3).ApartFrom(band, 1.0));
    }

    [Fact]
    public void A_box_with_a_coordinate_that_isnt_a_number_is_never_apart()
    {
        var band = B(0, 0, 0, 10, 10, 6.6);
        Assert.False(B(0, 0, double.NaN, 10, 10, double.NaN).ApartFrom(band, 1.0));
        Assert.False(band.ApartFrom(B(0, 0, double.NaN, 10, 10, double.NaN), 1.0));
    }

    [Fact]
    public void A_turned_solids_box_is_taken_round_all_8_corners_so_it_is_never_called_apart_when_it_reaches_the_band()
    {
        // a 10 x 1 ft beam turned 45° about its box's corner: round its 2 opposite corners alone the box would sit
        // more than a foot clear of the band (x up to -7.5), round all 8 it reaches x = -7.07, so the beam is cut
        var turn = Transform3.TurnThenMove(Math.PI / 4, new(0, 0, 0));
        var beam = Box3.Turned(new(0, 0, 0), new(1, 10, 1), turn);
        var band = B(-12, -1, 0, -7.5, 1, 2);
        var twoCorners = new BoxBuilder();
        twoCorners.Add(turn.Apply(new(0, 0, 0)));
        twoCorners.Add(turn.Apply(new(1, 10, 1)));
        Assert.True(twoCorners.Box!.Value.ApartFrom(band, 1.0));
        Assert.False(beam.ApartFrom(band, 1.0));
    }

    [Fact]
    public void A_solids_cut_is_skipped_only_when_its_box_lies_more_than_a_foot_from_the_bands()
    {
        var source = Addin("RevitInterior.cs");
        foreach (var hook in new[]
                 {
                     // the skip: only a closed solid with a box, apart by more than the margin from the band's 8-corner box
                     "case BandPiece.Body { Box: { } box } when box.ApartFrom(bandAround, CutMargin):",
                     "private const double CutMargin = 1.0;",
                     "var (bandMin, bandMax, bandAround) = boxes;",
                     "Box3.Turned(P(b.Min), P(b.Max), T(b.Transform))",
                     "return Box3.Turned(P(b.Min), P(b.Max), T(b.Transform));",
                     // a solid Revit can't box is cut, as before; boxing it never throws into the walk
                     "internal sealed record Body(Solid Solid, Box3? Box) : BandPiece;",
                     "pieces.Add(new BandPiece.Body(s, BoxOf(s)));",
                     "            return null;                                         // never thrown on: the walk goes on as it did",
                     // every other solid still cut, as before
                     "cut = BooleanOperationsUtils.ExecuteBooleanOperation(s, band, BooleanOperationsType.Intersect);",
                 })
            Assert.Contains(hook, source);
        // the skip comes before the cut, and an open shell is still tested on its own box, as before
        var skip = source.IndexOf("case BandPiece.Body { Box: { } box }", StringComparison.Ordinal);
        var cut = source.IndexOf("case BandPiece.Body { Solid: var s }:", StringComparison.Ordinal);
        Assert.True(skip >= 0 && skip < cut, "the skip must come before the cut");
        Assert.Contains("corners.Max(c => c.Z) < bandMin.Z || corners.Min(c => c.Z) > bandMax.Z", source);
    }

    [Fact]
    public void A_levels_enclosed_areas_are_outlined_together_as_each_alone_would_be_else_one_by_one_as_before()
    {
        var source = Addin("RevitInterior.cs");
        var together = source.IndexOf("OutlinesTogether(Document doc, Phase phase, Level level,", StringComparison.Ordinal);
        var alone = source.IndexOf("private static List<Xyz>? OutlineOf(", StringComparison.Ordinal);
        Assert.True(together >= 0 && alone > together);
        var body = source[together..alone];
        // every circuit checked against the topology as it is, before anything changes, with OutlineOf's own check
        var check = body.IndexOf("Math.Abs(fresh[index].Area - area) > 1e-9 || fresh[index].IsRoomLocated", StringComparison.Ordinal);
        var start = body.IndexOf("st.Start();", StringComparison.Ordinal);
        Assert.True(check >= 0 && start > check, "the checks come before the sub-transaction starts");
        Assert.Contains("fresh[index].Area - area) > 1e-9 || fresh[index].IsRoomLocated)\n                return null;", source[alone..]);
        // one regeneration for the level, the boundary read as OutlineOf reads it, and always rolled back
        Assert.Equal(1, Count(body, "doc.Regenerate();"));
        Assert.Contains("SpatialElementBoundaryLocation = SpatialElementBoundaryLocation.Finish", body);
        Assert.Contains("loops is null || loops.Count == 0 || loops.Any(l => l.Any(s => s.GetCurve() is not Line))", body);
        Assert.Contains("if (st.HasStarted() && !st.HasEnded())\n                st.RollBack();", body);
        // a circuit Revit refuses a Room in: no outline and nothing bounding it, as OutlineOf gives
        Assert.Contains("result[index] = (null, []);\n                    continue;", body);
        // anything else refused: each outlined alone, as before
        Assert.Contains("return null;                                         // each outlined alone, as before", body);
        Assert.Contains("Outline = together is not null ? Outlined(together[k], out by) : OutlineOf(doc, phase, level, k, areas[before + k].Area, out by),", source);
        // it runs where the outlines always ran: inside the enclosed areas' own transaction, after the geometry kept
        var close = source.IndexOf("}   // the geometry kept is let go here, before anything changes the model", StringComparison.Ordinal);
        Assert.True(source.IndexOf("() => OutlinesTogether(doc, phase, level,", StringComparison.Ordinal) > close);
    }

    [Fact]
    public void The_bands_box_is_worked_out_once_per_band_at_the_first_element_that_needs_it()
    {
        var source = Addin("RevitInterior.cs");
        var near = source.IndexOf("private static List<NearbyElement>? Near(", StringComparison.Ordinal);
        var body = source[near..source.IndexOf("private static string Category(", near, StringComparison.Ordinal)];
        // worked out inside the loop, just before the first InBand (where each InBand worked it out), then kept
        var first = body.IndexOf("bandBoxes ??= BandBoxes.Of(band);", StringComparison.Ordinal);
        var loop = body.IndexOf("foreach (var e in found)", StringComparison.Ordinal);
        var inBand = body.IndexOf("InBand(e, band, bandBoxes, options)", StringComparison.Ordinal);
        Assert.True(loop >= 0 && first > loop && inBand > first);
        Assert.Contains("BandBoxes? bandBoxes = null;\n            foreach (var e in found)", body);
        // the same boxes as before: the two corners through the transform, and the box round all 8
        Assert.Contains("return new(b.Transform.OfPoint(b.Min), b.Transform.OfPoint(b.Max), Box3.Turned(P(b.Min), P(b.Max), T(b.Transform)));", source);
        Assert.DoesNotContain("band.GetBoundingBox()", source[source.IndexOf("InBand(Element e,", StringComparison.Ordinal)..]
            .Split("private sealed record BandBoxes")[0]);
    }

    [Fact]
    public void An_elements_nearby_record_is_made_once_per_read_and_the_box_it_is_found_in_still_decides()
    {
        var source = Addin("RevitInterior.cs");
        var near = source.IndexOf("private static List<NearbyElement>? Near(", StringComparison.Ordinal);
        var body = source[near..source.IndexOf("private static string Category(", near, StringComparison.Ordinal)];
        // the element being looked round from, and the categories asked for, are still told apart per look round
        var skip = body.IndexOf("if (e.Id == skip)\n                    continue;", StringComparison.Ordinal);
        var model = body.IndexOf("var model = ModelKept.Get(key.Element, () => e.ViewSpecific || e.Category is not { CategoryType: Autodesk.Revit.DB.CategoryType.Model } c", StringComparison.Ordinal);
        var categories = body.IndexOf("if (categories is not null && !categories.Contains(cat))", StringComparison.Ordinal);
        var record = body.IndexOf("var near = NearKept.Get(key, () =>", StringComparison.Ordinal);
        Assert.True(skip >= 0 && model > skip && categories > model && record > categories);
        // the record made as before: every field from the element, its faces through the faces memo
        Assert.Contains("return new NearbyElement(e.UniqueId, cat.ToString(), e.Name, (e as FamilyInstance)?.Host?.UniqueId,\n" +
                        "                                             faces, failed, BoxOf(e), Id(e.DemolishedPhaseId), Id(e.DesignOption?.Id));", body);
        // the band is still cut per box, on the record kept
        Assert.Contains("near = near with { Banded = banded, BandFailed = bandFailed, OpenShells = openShells };", body);
        Assert.Contains("ReadMemo<GeometryKey, NearbyElement> NearKept = new();", source);
    }

    [Fact]
    public void Revits_own_box_filter_decides_what_is_near_on_the_box_indexs_candidates_or_on_the_whole_model()
    {
        var source = Addin("RevitInterior.cs");
        var collect = source[source.IndexOf("private static List<Element> Collect(", StringComparison.Ordinal)..source.IndexOf("private static BoxIndex IndexOf(", StringComparison.Ordinal)];
        foreach (var hook in new[]
                 {
                     // only with the read's scope open (the model unchanged), and never with more than a quarter of the model
                     "if (IndexKept.IsOpen)",
                     "index.Candidates(new Box3(P(box.MinimumPoint), P(box.MaximumPoint)), IndexPad, index.Count / 4) is { } candidates",
                     // Revit's filters on the candidates, put back in the model's order
                     "new FilteredElementCollector(doc, candidates.Select(k => new ElementId(k)).ToList()).WhereElementIsNotElementType()\n" +
                     "                    .WherePasses(new BoundingBoxIntersectsFilter(box));",
                     "return index.InOrder(then is null ? some : some.WherePasses(then), e => e.Id.Value);",
                     // else the whole model, as before
                     "var all = new FilteredElementCollector(doc).WhereElementIsNotElementType().WherePasses(new BoundingBoxIntersectsFilter(box));",
                 })
            Assert.Contains(hook, collect);
        Assert.Contains("private const double IndexPad = 1.0;", source);
        // the index lists what Revit's box filter passes for a box round any model, each with its box round all 8 corners
        Assert.Contains(".WherePasses(new BoundingBoxIntersectsFilter(new Outline(new XYZ(-Everywhere, -Everywhere, -Everywhere), new XYZ(Everywhere, Everywhere, Everywhere))))", source);
        Assert.Contains("e.get_BoundingBox(null) is { } b ? Box3.Turned(P(b.Min), P(b.Max), b.Transform is { } t ? T(t) : Reading.Transform3.Identity) : null;", source);
        // every look round goes through Collect: the rooms' insides, Near's and what stands outside an opening (GroundReader)
        Assert.Contains("var found = ReadSteps.Time(step + \".collect\", () => Collect(doc, box));", source);
        Assert.Contains("foreach (var e in Collect(doc, outline))", source);
        Assert.Equal(3, Count(source, "Collect(doc, "));
    }

    private static int Count(string text, string what)
    {
        var n = 0;
        for (var i = text.IndexOf(what, StringComparison.Ordinal); i >= 0; i = text.IndexOf(what, i + what.Length, StringComparison.Ordinal))
            n++;
        return n;
    }
}
