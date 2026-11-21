"""Decision 5's common path (routes/common_path.py), on the route note's tests
(docs/decisions/2026-11-20_route_measurement.md, tests 4, 6 and 7). Every figure is a literal from the note, or worked
by hand in the comment beside it; none is taken from the code under test. Tolerance 1e-3 ft."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes import common_path
from model_measurement.routes.common_path import at_point, shared, story_figure
from model_measurement.routes.paths import Route
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


def test_6_two_exits_and_a_column_the_story_figure_holds_the_far_walls_middle():
    """The story's figure is at least 13.270 (at (30, 5)). The note expected it at most 13.520: decision 5's own
    definition gives more (points along the south wall, whose shortest routes to both exits go under the column
    together), recorded as a hole in the note, not tuned here."""
    got = story_figure(routes(column_room(north_exit=True)))
    assert ft(got.figure) >= 13.270 - TOL


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
