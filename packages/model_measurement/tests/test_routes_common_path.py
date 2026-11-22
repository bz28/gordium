"""Decision 5's common path (routes/common_path.py), on the route note's tests
(docs/decisions/2026-11-20_route_measurement.md, tests 4, 6 and 7). Every figure is a literal from the note, or worked
by hand in the comment beside it; none is taken from the code under test. Tolerance 1e-3 ft."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes import common_path
from model_measurement.routes.common_path import at_point, shared, story_figure
from model_measurement.routes.paths import Route, Tied
from model_measurement.routes.remote import farthest
from model_measurement.routes.stops import Stop

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import FT, at, column_room, description, door, rect, room, room_on_corridor, routes  # noqa: E402

TOL = 1e-3


def ft(x):
    return x / FT


def l_room():
    """Test 6: legs 0 to 30 by 0 to 10 and 20 to 30 by 10 to 40, exit doors centred at (22, 40.25) and (28, 40.25),
    each its own exit."""
    return description([room("l", [(0, 0), (30, 0), (30, 40), (20, 40), (20, 10), (0, 10)], use="day_care")],
                       [door("a", (22, 40.25), (1, 0), ("l", "outside"), exit_id="A"),
                        door("b", (28, 40.25), (1, 0), ("l", "outside"), exit_id="B")])


def open_room():
    """Test 4: an open room 0 to 20 by 0 to 15, its west door (centre (-0.25, 7.5)) exit A, its east door (centre
    (20.25, 7.5)) exit B."""
    return description([room("r", rect(0, 0, 20, 15), use="day_care")],
                       [door("a", (-0.25, 7.5), (0, 1), ("r", "outside"), exit_id="A"),
                        door("b", (20.25, 7.5), (0, 1), ("r", "outside"), exit_id="B")])


# --- the note's figures ------------------------------------------------------------------------------------------

def test_6_both_routes_round_the_inside_corner_share_its_tangent_and_arc():
    got = at_point(routes(l_room()), at(0, 0))
    assert ft(got.length) == pytest.approx(23.263, abs=TOL)          # tangent 22.338 + arc together 0.925
    assert set(got.exits) == {"A", "B"}


def test_6_the_rooms_common_path_is_a_number_never_needs_review():
    got = story_figure(routes(l_room()))
    assert ft(got.figure) >= 23.263 - TOL and math.isfinite(got.figure)


def test_4_two_doors_seen_directly_part_at_the_start():
    # from (10, 2) both door centres are seen in straight lines, 12 in clear of every jamb: they share only the start
    assert at_point(routes(open_room()), at(10, 2)).length == pytest.approx(0.0, abs=1e-9)


def test_4_a_rooms_one_door_on_a_corridor_both_routes_part_at_the_door_centre():
    got = at_point(routes(room_on_corridor()), at(0, 0))
    assert ft(got.length) == pytest.approx(18.236, abs=TOL)          # the straight line to (10, 15.25)


def test_6_two_exits_and_a_column_the_tie_is_broken_toward_more_shared():
    """At (30, 5) both routes reach the ring at (17, 7) by one tangent (13.115) and go round it together until B's
    leaves (0.155): 13.270. Just below y = 5 the route to A goes under: they part at the start (0); just above, a
    little less than 13.270."""
    got = routes(column_room(north_exit=True))
    assert ft(at_point(got, at(30, 5)).length) == pytest.approx(13.270, abs=TOL)
    assert at_point(got, at(30, 4.99)).length == pytest.approx(0.0, abs=1e-9)
    above = ft(at_point(got, at(30, 5.01)).length)
    assert 13.0 < above < 13.270


def test_6_two_exits_and_a_column_along_the_south_wall_both_routes_go_under_together():
    """By hand: from (x, 0) both routes take the tangent to the ring at (13, 3) on its south side and go round it
    until A's leaves on the tangent to its door centre (-0.25, 5): sqrt(d^2 - 1) + the arc between the two tangent
    points, d the distance to (13, 3): 16.547 at x = 29.2, 16.746 at 29.4. At 29.5, past where B's shortest way
    flips to over the column (x 29.422 to 29.426, the brute force's bracket), they part at the start: 0."""
    got = routes(column_room(north_exit=True))
    assert ft(at_point(got, at(29.2, 0)).length) == pytest.approx(16.547, abs=TOL)
    assert ft(at_point(got, at(29.4, 0)).length) == pytest.approx(16.746, abs=TOL)
    assert at_point(got, at(29.5, 0)).length == pytest.approx(0.0, abs=1e-9)


def test_6_two_exits_and_a_column_the_story_figure_is_between_its_bounds():
    """The greatest pointwise common path is 16.769 ft (16.767 to 16.772) at the flip on the south wall (the note's
    test 6, corrected 2026-11-21: it said at most 13.520). The story's figure bounds the law's greatest, never above
    the greatest sample plus 4.5 in: between 13.270 and 16.772 + 0.375 = 17.147."""
    got = story_figure(routes(column_room(north_exit=True)))
    assert 13.270 - TOL <= ft(got.figure) <= 17.147 + TOL


# --- the definition's parts ---------------------------------------------------------------------------------------

def _route(*pieces):
    return Route(0.0, list(pieces), ("x",), "X")               # shared() reads the pieces only


def test_a_stretch_where_two_routes_meet_again_after_parting_counts():
    """Two routes from (0, 0): one by (10, 0), one by (0, 10), meeting again at (10, 10) and parting there. The
    last shared point is (10, 10), 20 along each: the common path is 20, not 0 (where they first part)."""
    a = _route(("line", (0.0, 0.0), (10.0, 0.0)), ("line", (10.0, 0.0), (10.0, 10.0)), ("line", (10.0, 10.0), (20.0, 10.0)))
    b = _route(("line", (0.0, 0.0), (0.0, 10.0)), ("line", (0.0, 10.0), (10.0, 10.0)), ("line", (10.0, 10.0), (10.0, 20.0)))
    assert shared(a, b) == pytest.approx(20.0, abs=1e-9)


def test_two_routes_that_share_a_stretch_share_to_its_far_end():
    a = _route(("line", (0.0, 0.0), (10.0, 0.0)), ("line", (10.0, 0.0), (20.0, 5.0)))
    b = _route(("line", (0.0, 0.0), (4.0, 0.0)), ("line", (4.0, 0.0), (10.0, 0.0)), ("line", (10.0, 0.0), (20.0, -5.0)))
    assert shared(a, b) == pytest.approx(10.0, abs=1e-9)
    assert shared(a, _route(("line", (0.0, 0.0), (4.0, 0.0)))) == pytest.approx(4.0, abs=1e-9)   # its own end


def test_a_line_touching_a_ring_shares_the_point_it_touches():
    # the line y = 12 from x = -10 to 10 touches the circle of radius 12 about (0, 0) at (0, 12): 10 along the line,
    # 12 * pi / 2 = 18.850 along the arc from angle 0; the greater is taken
    a = _route(("line", (-10.0, 12.0), (10.0, 12.0)))
    b = _route(("arc", (0.0, 0.0), 12.0, 0.0, math.pi))
    assert shared(a, b) == pytest.approx(6 * math.pi, abs=1e-9)


def test_two_rings_24_in_apart_share_the_point_where_they_touch():
    # circles of radius 12 about (0, 0) and (24, 0) touch at (12, 0): each arc passes it halfway, 12 * pi / 2 along
    a = _route(("arc", (0.0, 0.0), 12.0, -math.pi / 2, math.pi))
    b = _route(("arc", (24.0, 0.0), 12.0, math.pi / 2, math.pi))
    assert shared(a, b) == pytest.approx(6 * math.pi, abs=1e-9)


def test_two_routes_round_one_ring_share_the_shorter_arc():
    # both round the circle of radius 12 about (0, 0) from angle 0, one 30 degrees, the other 90: 12 * pi / 6
    a = _route(("arc", (0.0, 0.0), 12.0, 0.0, math.pi / 6))
    b = _route(("arc", (0.0, 0.0), 12.0, 0.0, math.pi / 2))
    assert shared(a, b) == pytest.approx(2 * math.pi, abs=1e-9)


def third_exit():
    """Test 4's room on its corridor, with a third exit C: a door in its south wall centred at (10, -0.25)."""
    d = room_on_corridor()
    d["doors"].append(door("s", (10, -0.25), (1, 0), ("r", "outside"), exit_id="C"))
    return d


def test_the_least_over_the_pairs_of_distinct_exits_counts():
    # from (0, 0): A and B share to the corridor door (18.236), but C is seen directly, parting at the start: 0
    assert at_point(routes(third_exit()), at(0, 0)).length == pytest.approx(0.0, abs=1e-9)


def two_rooms_apart():
    """Two rooms with no door between them, each with its own exit: from a point in one, the other exit has no
    route."""
    return description([room("w", rect(0, 0, 10, 10), use="day_care"), room("e", rect(10.5, 0, 20, 10), use="day_care")],
                       [door("a", (-0.25, 5), (0, 1), ("w", "outside"), exit_id="A"),
                        door("b", (20.25, 5), (0, 1), ("e", "outside"), exit_id="B")])


def test_a_point_that_reaches_one_exit_has_its_travel_distance_as_its_common_path():
    # from (10, 5)... (9, 5): straight to (-0.25, 5), 9.25 ft, the jambs' rings 1.5 ft off the line
    got = at_point(routes(two_rooms_apart()), at(9, 5))
    assert ft(got.length) == pytest.approx(9.25, abs=TOL) and got.exits == ("A",)


def test_one_exit_on_the_story_its_common_path_is_the_travel_figure():
    one = description([room("r", rect(0, 0, 20, 10), use="day_care")],
                      [door("x", (-0.25, 5), (0, 1), ("r", "outside"), exit_id="A")])
    got = routes(one)
    assert story_figure(got).figure == farthest(got).figure
    assert ft(at_point(got, at(20, 0)).length) == pytest.approx(math.hypot(20.25, 5), abs=TOL)   # 20.858


def test_a_point_with_no_route_to_any_exit_stops():
    with pytest.raises(Stop) as stop:
        at_point(routes(two_rooms_apart()), at(30, 5))
    assert stop.value.key == "not_on_floor"


def test_a_stop_other_than_no_route_is_never_swallowed():
    with pytest.raises(Stop) as stop:
        at_point(routes(l_room()), at(20.5, 10.5))                 # within 12 in of the inside corner
    assert stop.value.key == "inside_ring"


def test_the_sampler_reads_only_the_rooms_asked_for():
    got = routes(two_rooms_apart())
    west = story_figure(got, rooms={"w"})
    assert ft(west.greatest) <= math.hypot(10.25, 5) + TOL           # 11.404: its far corners, never the east room's
    assert common_path._CommonPathSampler(got, {"w"}).story.rooms.keys() == {"w"}


@pytest.mark.parametrize("layout", [lambda: column_room(north_exit=True), l_room, third_exit])
def test_the_fast_tied_routes_are_the_slow_ones(layout):
    """common_path.tied reads a route's first leg from each zone's graph built once; on a 2-ft grid of every room it
    gives the same union of tied routes as paths.py's `tied` (the same length, to 1e-6 in, and the same pieces), and
    every route paths.py's `routes` lists lies wholly in it (decision 5, amended 2026-11-22), or the same reason for
    none."""
    got = routes(layout())
    for room_ in got.story.rooms.values():
        x0, y0, x1, y1 = room_.outline.bounds
        for i in range(0, int((x1 - x0) / FT) + 1, 2):
            for j in range(0, int((y1 - y0) / FT) + 1, 2):
                p = (x0 + i * FT, y0 + j * FT)
                for e in got.exits:
                    ways = []
                    for find in (lambda q, ex: got.tied(q, ex), lambda q, ex: common_path.tied(got, q, ex[0])):
                        try:
                            ways.append(find(p, [e]))
                        except Stop as s:
                            ways.append(s.key)
                    if isinstance(ways[0], str) or isinstance(ways[1], str):
                        assert ways[0] == ways[1], (p, e, ways)
                        continue
                    slow, fast = ways
                    assert fast.length == pytest.approx(slow.length, abs=1e-6), (p, e)
                    assert _within(fast, slow) and _within(slow, fast), (p, e)     # one union, however split
                    for listed in got.routes(p, [e]):
                        whole = Tied(listed.length, [(q, o) for q, o in zip(listed.pieces, _offsets(listed))], listed)
                        assert common_path.farthest_shared(whole, fast)[0] == pytest.approx(listed.length, abs=1e-6)


def _within(a, b) -> bool:
    """Every piece of the union a lies on the union b (checked at its ends and three points between), at the same
    travel distance (its offset)."""
    from model_measurement.routes.common_path import _along
    from model_measurement.routes.paths import _piece_length
    for q, o in a.pieces:
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = _point(q, f)
            if not any((u := _along(r, x)) is not None and abs(o + f * _piece_length(q) - (o2 + u)) <= 1e-6
                       for r, o2 in b.pieces):
                return False
    return True


def _point(q, f):
    if q[0] == "line":
        return (q[1][0] + (q[2][0] - q[1][0]) * f, q[1][1] + (q[2][1] - q[1][1]) * f)
    _, c, r, a0, sweep = q
    return (c[0] + r * math.cos(a0 + sweep * f), c[1] + r * math.sin(a0 + sweep * f))


def _offsets(route) -> list:
    from model_measurement.routes.paths import _piece_length
    out, s = [], 0.0
    for q in route.pieces:
        out.append(s)
        s += _piece_length(q)
    return out


# --- tests 21 and 22: ties, all together (decision 5, amended 2026-11-22) ------------------------------------------

def row_of_columns():
    """Test 21: a corridor 0 to 60 by 0 to 10 with ten columns 1 ft square (x 6 + 5m to 7 + 5m, y 6 to 7), exits A
    (centre (-0.25, 5)) and B (centre (-0.25, 1.5)) in its west wall; a room 60.5 to 70.5 by 0 to 10 east of it, its
    one door centred at (60.25, 5)."""
    cols = [rect(6 + 5 * m, 6, 7 + 5 * m, 7) for m in range(10)]
    return description([room("c", rect(0, 0, 60, 10), holes=cols), room("e", rect(60.5, 0, 70.5, 10), use="day_care")],
                       [door("a", (-0.25, 5), (0, 1), ("c", "outside"), exit_id="A"),
                        door("b", (-0.25, 1.5), (0, 1), ("c", "outside"), exit_id="B"),
                        door("d", (60.25, 5), (0, 1), ("c", "e"))])


def test_21_one_route_along_a_row_of_rings_is_one_route():
    """From (70, 5): 9.75 to the door centre, then along y = 5, exactly 12 in below the columns' 20 south corners
    (tangent to every ring), 60.5 to A: 70.25; to B straight from the door centre, sqrt(60.5^2 + 3.5^2) = 60.601:
    70.351. They part at the door centre: the common path is 9.75. From (58, 5) they part at the start: 0. The listing
    found the one route to A once for each set of the tangent points it could be split at and stopped past 64."""
    got = routes(row_of_columns())
    assert ft(got.route(at(70, 5), ["A"]).length) == pytest.approx(70.25, abs=TOL)
    assert ft(got.route(at(70, 5), ["B"]).length) == pytest.approx(9.75 + math.hypot(60.5, 3.5), abs=TOL)
    here = at_point(got, at(70, 5))
    assert ft(here.length) == pytest.approx(9.75, abs=TOL) and here.exits == ("A", "B")
    assert [round(ft(v), 6) for v in here.at] == [60.25, 5.0]                     # where they part: the door centre
    assert [round(ft(x.length), 3) for x in here.routes] == [70.25, 70.351]       # the two routes drawn, through it
    assert at_point(got, at(58, 5)).length == 0.0


def diamonds():
    """Test 22: a room 0 to 10 by 0 to 10; through door centres at x = 10.25 + 6m (m = 0 to 14), fourteen rooms 5.5
    ft long, then a room 94.5 to 114.5 by 0 to 10 with exits A (114.75, 7.5) and B (114.75, 2.5); at even m one door
    centred on y = 5, at odd m two, at y 2.5 and 7.5."""
    xs = [10.25 + 6 * m for m in range(15)]
    names = ["s"] + [f"r{m}" for m in range(14)] + ["f"]
    rooms = ([room("s", rect(0, 0, 10, 10), use="day_care")] +
             [room(f"r{m}", rect(xs[m] + 0.25, 0, xs[m + 1] - 0.25, 10)) for m in range(14)] +
             [room("f", rect(94.5, 0, 114.5, 10))])
    doors = [door(f"d{m}_{y}", (xs[m], y), (0, 1), (names[m], names[m + 1]))
             for m in range(15) for y in ([5] if m % 2 == 0 else [2.5, 7.5])]
    doors += [door("a", (114.75, 7.5), (0, 1), ("f", "outside"), exit_id="A"),
              door("b", (114.75, 2.5), (0, 1), ("f", "outside"), exit_id="B")]
    return description(rooms, doors)


def test_22_128_tied_routes_are_never_listed():
    """From (1, 5): 9.25 to the first door, then seven pairs of rooms each crossed through either middle door, 6.5 ft
    a leg (sqrt(6^2 + 2.5^2)), 13 a pair: 2^7 = 128 tied routes to each exit, all reaching the last door (94.25, 5)
    at 100.25 ft, where they part: the common path is 100.25, the travel 100.25 + sqrt(20.5^2 + 2.5^2) = 120.902.
    Listing them stops past 64; the union never lists one."""
    got = routes(diamonds())
    here = at_point(got, at(1, 5))
    assert ft(here.length) == pytest.approx(100.25, abs=TOL)
    assert [round(ft(v), 6) for v in here.at] == [94.25, 5.0]
    for e in ("A", "B"):
        assert ft(got.route(at(1, 5), [e]).length) == pytest.approx(100.25 + math.hypot(20.5, 2.5), abs=TOL)
    with pytest.raises(Stop) as stop:
        got.routes(at(1, 5), ["A"])                                               # listing them: too many
    assert stop.value.key == "too_many_ties"
