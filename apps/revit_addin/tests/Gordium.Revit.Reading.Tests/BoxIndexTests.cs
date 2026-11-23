using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The model's element boxes listed once per read (<see cref="BoxIndex"/>): it only narrows what Revit's own
/// box filter is run on, so it must keep every element that filter could pass (every box that comes within the pad,
/// every element with no box), and put what passes back in the model's order.</summary>
public sealed class BoxIndexTests
{
    private static Box3 B(double x0, double y0, double z0, double x1, double y1, double z1) => new(new(x0, y0, z0), new(x1, y1, z1));

    private static BoxIndex Index() => new([
        (7, B(0, 0, 0, 10, 10, 1)),            // a floor under the box asked about
        (3, B(50, 50, 0, 60, 60, 10)),         // far off
        (9, null),                             // no box: Revit's box can't be told, so always kept
        (4, B(10.5, 0, 0, 12, 10, 8)),         // half a foot beside it: within the pad
        (1, B(0, 0, 30, 10, 10, 31)),          // a roof far over it
        (8, B(double.NaN, 0, 0, double.NaN, 1, 1)), // a box that isn't all numbers: always kept
        (5, B(2, 2, 2, 3, 3, 3)),              // inside it
    ]);

    [Fact]
    public void Every_element_whose_box_comes_within_the_pad_or_that_has_no_box_is_kept_in_the_models_order()
    {
        var asked = B(0, 0, 1, 10, 10, 9);
        Assert.Equal([7, 9, 4, 8, 5], Index().Candidates(asked, 1.0, 100));
        // with no pad, the box half a foot beside is left out; touching is kept
        Assert.Equal([7, 9, 8, 5], Index().Candidates(asked, 0, 100));
    }

    [Fact]
    public void A_box_Revits_filter_passes_is_never_left_out()
    {
        // every box that meets the box asked about (Revit's test) is a candidate, whatever the pad
        var rnd = new Random(7);
        double R() => Math.Round(rnd.NextDouble() * 40 - 20, 1);
        var elements = Enumerable.Range(0, 400).Select(i =>
        {
            double x = R(), y = R(), z = R();
            return ((long)i, (Box3?)B(x, y, z, x + Math.Abs(R()) / 4, y + Math.Abs(R()) / 4, z + Math.Abs(R()) / 4));
        }).ToList();
        var index = new BoxIndex(elements);
        for (var k = 0; k < 200; k++)
        {
            double x = R(), y = R(), z = R();
            var asked = B(x, y, z, x + Math.Abs(R()) / 2, y + Math.Abs(R()) / 2, z + Math.Abs(R()) / 2);
            var meets = elements.Where(e => !e.Item2!.Value.ApartFrom(asked, 0)).Select(e => e.Item1).ToList();
            var kept = index.Candidates(asked, 1.0, int.MaxValue)!;
            Assert.All(meets, m => Assert.Contains(m, kept));
        }
    }

    [Fact]
    public void Too_many_candidates_gives_none_so_the_whole_model_is_looked_through_as_before()
    {
        Assert.Null(Index().Candidates(B(-100, -100, -100, 100, 100, 100), 1.0, 6));
        Assert.Equal(7, Index().Candidates(B(-100, -100, -100, 100, 100, 100), 1.0, 7)!.Count);
    }

    [Fact]
    public void What_passes_is_put_back_in_the_models_order_and_an_element_not_listed_is_never_placed_on_a_guess()
    {
        Assert.Equal([7, 4, 1, 5], Index().InOrder(new long[] { 5, 1, 4, 7 }, k => k));
        Assert.Throws<KeyNotFoundException>(() => Index().InOrder(new long[] { 5, 2 }, k => k));
    }
}
