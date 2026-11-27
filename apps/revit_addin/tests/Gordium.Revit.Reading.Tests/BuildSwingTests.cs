using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The model build's read-back of each door's swing (RouteReader.ReadBuildSwings, used by ModelBuild): what
/// the door's own plan symbol draws, never its family's facing or hand convention, held against the data; the flips
/// it asks for; and never "as the data" on what isn't read. The fake story (RouteDrawing.cs): dA in the wall between
/// office A (its face at y 9.5) and the corridor (y 10), centred at x 10.</summary>
public sealed class BuildSwingTests
{
    private static RouteReader.BuildSwing Read(FakeFloor floor, (double X, double Y) dir, (double X, double Y)? hinge)
    {
        var data = new Dictionary<string, (Xyz, Xyz?, Xyz)>
        {
            [FakeFloor.Uid("dA")] = (floor.Fake.Place(dir.X, dir.Y, 0) - floor.Fake.Place(0, 0, 0),
                                     hinge is { } h ? floor.Fake.Place(h.X, h.Y, 0) : null, floor.Fake.Place(10, 9.75, 0)),
        };
        return Assert.Single(RouteReader.ReadBuildSwings(floor.Model(), data));
    }

    [Theory]
    // drawn: swinging toward the corridor (+y) or the office (-y), hinged at the -x or +x jamb; the data: the same or
    // not, side and hinge each
    [InlineData(+1, -1, +1, -1, false, false)]
    [InlineData(+1, -1, -1, -1, true, false)]
    [InlineData(+1, -1, +1, +1, false, true)]
    [InlineData(-1, +1, +1, -1, true, true)]
    public void It_asks_for_the_flips_that_bring_what_is_drawn_to_the_data(int drawnInto, int drawnHinge, int dataInto, int dataHinge,
                                                                            bool facing, bool hand)
    {
        foreach (var turn in new[] { Transform3.Identity, Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0)) })
        {
            var floor = new FakeFloor(turn);
            floor.Swing("dA", drawnInto, drawnHinge);
            var r = Read(floor, (0, dataInto), (10 + dataHinge * 1.5, 9.75));
            Assert.Equal((facing, hand), (r.FlipFacing, r.FlipHand));
            Assert.Equal(!facing && !hand, r.AsTheData);
            Assert.NotNull(r.Side);
            Assert.NotNull(r.Hinge);
        }
    }

    [Fact]
    public void A_swing_not_read_is_never_flipped_and_never_as_the_data()
    {
        var floor = new FakeFloor();
        var i = floor.OpeningIndex("dA");
        floor.Openings[i] = floor.Openings[i] with { Swing = new SwingDrawing([]) };
        var r = Read(floor, (0, 1), (8.5, 9.75));
        Assert.Null(r.Side);
        Assert.False(r.FlipFacing || r.FlipHand || r.AsTheData);
        Assert.Contains("draws no swing", r.Why);
    }

    [Fact]
    public void A_data_hinge_at_the_doors_centre_is_never_matched_or_flipped_to()
    {
        // build review round 1: a hinge with no offset along the wall said nothing, yet was read as "no hinge given",
        // and the door was said to swing as the data; round 3: under turned coordinates too, where it is rounding noise
        foreach (var turn in new[] { Transform3.Identity, Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0)) })
            foreach (var drawn in new[] { -1, +1 })
            {
                var floor = new FakeFloor(turn);
                floor.Swing("dA", +1, hinge: drawn);
                foreach (var off in new[] { 0, 0.004, -0.004 })          // a hair off centre too (round 4): within 1/16 in
                {
                    var r = Read(floor, (0, 1), (10 + off, 9.75));
                    Assert.Equal(0, r.DataHinge);
                    Assert.False(r.AsTheData || r.FlipHand);
                    Assert.Contains("hinge is at the door's centre", r.Why);
                }
                var along = Read(floor, (1, 0), (8.5, 9.75));       // a swing along the wall says no side
                Assert.Null(along.DataSide);
                Assert.False(along.AsTheData || along.FlipFacing);
                Assert.Contains("runs along its wall", along.Why);
            }
    }

    [Fact]
    public void A_data_hinge_at_the_centre_is_never_matched_even_by_a_hinge_read_at_the_centre()
    {
        // build review round 2: the match itself refuses a data hinge of 0, whatever is read
        var r = new RouteReader.BuildSwing("d", 1, 0, 1, 0, null);
        Assert.False(r.AsTheData || r.FlipHand);
    }

    [Fact]
    public void A_swing_not_read_keeps_its_reason_beside_the_datas_own()
    {
        var floor = new FakeFloor();
        var i = floor.OpeningIndex("dA");
        floor.Openings[i] = floor.Openings[i] with { Swing = new SwingDrawing([]) };
        var r = Read(floor, (0, 1), (10, 9.75));
        Assert.Contains("draws no swing", r.Why);
        Assert.Contains("hinge is at the door's centre", r.Why);
    }

    [Fact]
    public void A_pairs_hinge_isnt_read_so_its_hand_is_never_flipped()
    {
        var floor = new FakeFloor();
        floor.Swing("dA", +1, hinge: -1, radius: FakeFloor.Clear / 2);
        floor.Swing("dA", +1, hinge: +1, radius: FakeFloor.Clear / 2);
        var pair = Read(floor, (0, 1), null);
        Assert.NotNull(pair.Side);
        Assert.Equal(pair.DataSide, pair.Side);
        Assert.Null(pair.Hinge);
        Assert.True(pair.AsTheData);                         // a double gives no hinge: its side alone
        var asked = Read(floor, (0, 1), (8.5, 9.75));        // a hinge asked of a pair: not read, so not as the data
        Assert.False(asked.FlipHand || asked.AsTheData);
    }
}
