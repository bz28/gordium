using System.Text.Json.Nodes;
using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>Which side a door swings into (<c>doors[].swings_into</c>, BCNYS 1010.1.2.1), read only from the swing its
/// own plan symbol draws (<see cref="OpeningRecord.Swing"/>; RouteReader.SwingsInto), never from its facing or hand,
/// and left unstated, with a note, wherever that drawing doesn't settle it: a swing not drawn (a coarse view's or a
/// hidden subcategory's missing arcs are never read as a door that doesn't swing), drawn both ways, ending in the wall,
/// a door that slides, or rooms not found where it swings. The fake story's doors (RouteDrawing.cs): dA between office
/// A (its wall's face at y 9.5) and the corridor C (y 10); dS2 in the stair's west wall, outside at x -0.5, the stair at
/// x 0.</summary>
public sealed class DoorSwingTests
{
    private static JsonObject Door(InteriorReadResult r, string id) => FakeFloor.Part(r, "doors", id)!;

    private static string U(string id) => FakeFloor.Uid(id);

    private static string? Into(InteriorReadResult r, string id) => Door(r, id)["swings_into"]?.GetValue<string>();

    [Theory]
    [InlineData(+1, -1, "C")]
    [InlineData(+1, +1, "C")]
    [InlineData(-1, -1, "A")]
    [InlineData(-1, +1, "A")]
    public void A_door_swings_into_the_room_on_the_side_its_plan_symbol_draws_its_swing_whichever_jamb_it_hangs_on(int into, int hinge, string room)
    {
        foreach (var turn in new[] { Transform3.Identity, Transform3.TurnThenMove(Math.PI / 6, new Xyz(875_000.25, -12_345.5, 400.0)) })
        {
            var floor = new FakeFloor(turn);
            floor.Swing("dA", into, hinge);
            var read = InteriorReader.Read(floor.Model());
            Assert.Equal(U(room), Into(read, "dA"));
            Assert.Null(FakeFloor.Note(read, "dA", "doors.swings_into"));
        }
    }

    [Fact]
    public void Its_facing_and_hand_are_never_read_for_the_swing()
    {
        // the same drawn swing, the door's hand (its direction along the wall) turned the other way: the same side
        foreach (var into in new[] { +1, -1 })
        {
            var floor = new FakeFloor();
            floor.Swing("dA", into);
            var i = floor.OpeningIndex("dA");
            var along = floor.Openings[i].Along!.Value;
            floor.Openings[i] = floor.Openings[i] with { Along = new Xyz(-along.X, -along.Y, -along.Z) };
            Assert.Equal(U(into > 0 ? "C" : "A"), Into(InteriorReader.Read(floor.Model()), "dA"));
        }
    }

    [Theory]
    [InlineData(-1, "outside")]
    [InlineData(+1, "S")]
    public void A_door_to_outside_swings_outside_or_into_its_room(int into, string side)
    {
        var floor = new FakeFloor();
        floor.Swing("dS2", into);
        Assert.Equal(side == "outside" ? RouteReader.Outside : U(side), Into(InteriorReader.Read(floor.Model()), "dS2"));
    }

    [Fact]
    public void A_pair_whose_two_leaves_swing_the_same_way_swings_that_way()
    {
        var floor = new FakeFloor();
        floor.Swing("dA", +1, hinge: -1, radius: FakeFloor.Clear / 2);
        floor.Swing("dA", +1, hinge: +1, radius: FakeFloor.Clear / 2);
        Assert.Equal(U("C"), Into(InteriorReader.Read(floor.Model()), "dA"));
    }

    [Fact]
    public void An_unequal_pair_hung_opposite_ways_swings_both_ways_so_is_unstated()
    {
        // door swing review round 3: a 12.5 in leaf beside a 26 in one, the narrow one swinging the other way; its arc is
        // shorter than half the opening, yet it is a leaf's swing, and the door may swing against egress travel
        var floor = new FakeFloor();
        floor.Swing("dA", +1, hinge: -1, radius: 26.0 / 12);
        floor.Swing("dA", -1, hinge: +1, radius: 12.5 / 12);
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("on both sides of its wall", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void A_pairs_narrowest_leaf_drawn_a_little_short_still_counts()
    {
        // door swing review round 4: a 300 mm leaf (0.984 ft) and a 12 in leaf drawn to its 11.25 in panel, each beside
        // a wide one swinging the other way: never dropped, so never read as swinging one way
        foreach (var narrow in new[] { 0.984, 11.25 / 12 })
        {
            var floor = new FakeFloor();
            floor.Swing("dA", +1, hinge: -1, radius: 26.0 / 12);
            floor.Swing("dA", -1, hinge: +1, radius: narrow);
            var read = InteriorReader.Read(floor.Model());
            Assert.Null(Into(read, "dA"));
            Assert.Contains("on both sides of its wall", FakeFloor.Note(read, "dA", "doors.swings_into"));
        }
    }

    [Fact]
    public void No_swing_drawn_leaves_it_unstated_never_a_door_that_doesnt_swing()
    {
        // the arcs a coarse view, a hidden Plan Swing subcategory or a family's own visibility drops: the plan view the
        // Revit layer reads in gives none, and that is never read as "it doesn't swing"
        var floor = new FakeFloor();
        var i = floor.OpeningIndex("dA");
        floor.Openings[i] = floor.Openings[i] with { Swing = new SwingDrawing([]) };
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("draws no swing at Fine detail", FakeFloor.Note(read, "dA", "doors.swings_into"));
        Assert.Contains("never read as a door that doesn't swing", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void A_swing_not_read_says_why_and_is_left_unstated()
    {
        var floor = new FakeFloor();
        Assert.Contains("its plan symbol wasn't read", FakeFloor.Note(InteriorReader.Read(floor.Model()), "dA", "doors.swings_into"));
        var i = floor.OpeningIndex("dA");
        floor.Openings[i] = floor.Openings[i] with { Swing = new SwingDrawing([], "the model is read-only, so no plan view could be made to read its swing") };
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.StartsWith("the model is read-only", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void Swings_drawn_both_ways_leave_it_unstated()
    {
        // a double-acting door, or a pair hung opposite ways
        var floor = new FakeFloor();
        floor.Swing("dA", +1, hinge: -1);
        floor.Swing("dA", -1, hinge: +1);
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("on both sides of its wall", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void An_arc_that_isnt_a_leafs_swing_from_a_jamb_is_not_read_as_one()
    {
        var floor = new FakeFloor();
        floor.Swing("dA", +1, radius: 0.25);                                  // a handle's arc: far too short for a leaf
        floor.AddArc("dA", new SwingArc(floor.Fake.Place(10, 13, 0), FakeFloor.Clear, floor.Fake.Place(11, 14, 0)));   // centred off the wall
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("none of the 2 arcs its plan symbol draws is a leaf's swing from a jamb", FakeFloor.Note(read, "dA", "doors.swings_into"));
        // and with the leaf's own swing drawn too, that one is read
        floor.Swing("dA", +1);
        Assert.Equal(U("C"), Into(InteriorReader.Read(floor.Model()), "dA"));
    }

    [Fact]
    public void An_arc_hinged_in_the_wall_away_from_a_jamb_is_not_a_swing()
    {
        // a centre-pivot door's arc: centred in the wall at the middle of the opening, half the door's width, drawn on
        // one side (door swing review round 1: only the jamb test turns it away)
        var floor = new FakeFloor();
        floor.AddArc("dA", new SwingArc(floor.Fake.Place(10, 9.75, 0), FakeFloor.Frame / 2, floor.Fake.Place(10, 9.75 + FakeFloor.Frame / 2, 0)));
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("none of the 1 arcs its plan symbol draws is a leaf's swing from a jamb", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void A_swing_that_ends_within_its_wall_leaves_it_unstated()
    {
        var floor = new FakeFloor();
        floor.AddArc("dA", new SwingArc(floor.Fake.Place(10 - FakeFloor.Clear / 2, 9.75, 0), FakeFloor.Clear, floor.Fake.Place(10, 9.8, 0)));
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("ends within its wall", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void A_door_that_slides_has_no_swing_read()
    {
        var floor = new FakeFloor();
        floor.Swing("dA", +1);
        var i = floor.MarkedIndex("dA");
        var type = new Dictionary<Guid, MarkValue>(floor.Marked[i].Type!) { [Marks.Operation.Guid] = new(true, Text: "Sliding door") };
        floor.Marked[i] = floor.Marked[i] with { Type = type };
        var read = InteriorReader.Read(floor.Model());
        Assert.Equal("sliding", Door(read, "dA")["operation"]!.GetValue<string>());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("its operation is sliding", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    [Fact]
    public void A_side_whose_room_isnt_found_where_it_swings_leaves_it_unstated()
    {
        // the door's swing drawn into office B's side of the wall, which neither of its rooms is on: not dA's sides
        var floor = new FakeFloor();
        floor.Swing("dA", +1);
        var i = floor.RoomIndex("C");
        var loop = floor.Rooms[i].Boundary![0];
        floor.Rooms[i] = floor.Rooms[i] with
        {
            Boundary = [[.. loop.Select(s => s with { Start = Shift(floor, s.Start), End = Shift(floor, s.End) })]],
        };
        var read = InteriorReader.Read(floor.Model());
        Assert.Null(Into(read, "dA"));
        Assert.Contains("aren't found one on each side of its wall where it swings", FakeFloor.Note(read, "dA", "doors.swings_into"));
    }

    private static Xyz Shift(FakeFloor floor, Xyz p)
    {
        // the corridor drawn 1 ft farther north (its south edge off the wall's face): no room just beyond that face
        var s = floor.Fake.InternalToShared.Apply(p);
        return floor.Fake.Place(s.X, s.Y + 1, s.Z);
    }
}
