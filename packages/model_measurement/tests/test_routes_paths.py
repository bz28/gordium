"""Decision 2's routes (routes/paths.py), on the route note's own tests
(docs/decisions/2026-11-20_route_measurement.md, "How we will know it is right"). Every figure here is written as a
literal: the note's (worked there two ways: tangent-and-arc formulas, and a brute force over 512-sided rings), or,
for a layout of this file's own, worked by hand in the comment beside it. None is taken from the code under test.
Tolerance 1e-3 ft. Feet in the layouts; the route code works in inches."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes.floor import read
from model_measurement.routes.paths import StoryRoutes
from model_measurement.routes.stops import STOPS, Stop

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import (FT, at, column_room, description, door, l_corridor, rect, room, room_on_corridor,  # noqa: E402
                            routes, story, table_room)

TOL = 1e-3


def feet(stories_routes, x, y, exits=None):
    return stories_routes.route(at(x, y), exits).feet


def to_door(route, centre) -> float:
    """The route's length (ft) from its start to the point where it passes that door centre (ft)."""
    s = 0.0
    for q in route.pieces:
        if q[0] == "line":
            a, b = q[1], q[2]
            s += math.dist(a, b)
        else:
            _, c, r, a0, sweep = q
            s += abs(sweep) * r
            b = (c[0] + r * math.cos(a0 + sweep), c[1] + r * math.sin(a0 + sweep))
        if math.dist(b, (centre[0] * FT, centre[1] * FT)) < 1e-6:
            return s / FT
    raise AssertionError("the route doesn't pass that door centre")


# --- test 1: an L-shaped corridor -------------------------------------------------------------------------------------

def test_1_the_l_corridor_curves_round_the_inside_corner_at_12_in():
    got = routes(l_corridor())
    assert feet(got, 40, 30) == pytest.approx(60.393, abs=TOL)       # 24.718 + arc 1.308 + 34.367


def test_1_the_clearance_lengthens_the_route():
    with_rings, without = routes(l_corridor()), routes(l_corridor(), clearance=0)
    assert feet(without, 40, 30) == pytest.approx(59.120, abs=TOL)   # no clearance: the note's figure
    assert feet(with_rings, 40, 30) > feet(without, 40, 30) + 1.2     # one corner adds 1.27 ft


def test_behind_a_corner_the_route_runs_inside_its_ring_to_the_corner():
    """From (34.5, 6.5), inside the ring of the inside corner (34, 6) and behind it: 0.707 + 34.381."""
    assert feet(routes(l_corridor()), 34.5, 6.5) == pytest.approx(35.088, abs=TOL)


def test_a_start_on_a_corner_goes_straight_never_no_route():
    assert feet(routes(l_corridor()), 34, 6) == pytest.approx(34.381, abs=TOL)


# --- test 2: a room with a column ---------------------------------------------------------------------------------

def test_2_behind_the_column_the_far_walls_middle_is_farther_than_its_corners():
    got = routes(column_room())
    middle = feet(got, 30, 5)
    assert middle == pytest.approx(30.931, abs=TOL)                   # over and under the column, equal
    for y in (0, 10):
        assert feet(got, 30, y) == pytest.approx(30.704, abs=TOL)
    assert middle > 30.704 + 0.2                                      # a corners-only answer would be 0.227 short


def test_two_exits_and_a_column_both_tied_ways_round_are_kept():
    """At (30, 5) the two ways round the column to A are equally short (the room is symmetric about y = 5): both
    are kept (decision 2: a tie), so the common path can take the one over the top (decision 5)."""
    got = routes(column_room(north_exit=True)).routes(at(30, 5), ["A"])
    assert [round(r.feet, 3) for r in got] == [30.931, 30.931]
    sides = sorted(max(y for q in r.pieces if q[0] == "line" for _, y in (q[1], q[2])) > 7 * FT for r in got)
    assert sides == [False, True]                                     # one under the column, one over


# --- the table, a jamb, test 4 -----------------------------------------------------------------------------------

def test_a_table_in_the_way_the_route_goes_round_it_12_in_off():
    got = routes(table_room())
    assert feet(got, 10, 0) == pytest.approx(22.043, abs=TOL)        # 8.958 + 0.450 + 3 + 0.439 + 9.196
    assert len(got.routes(at(10, 0))) == 2                            # round either side: a tie


def test_4_from_the_rooms_corner_the_route_to_its_door_is_straight():
    """It passes the jamb's ring at 1.12 ft: a straight 18.236 ft to the door centre (10, 15.25)."""
    route = routes(room_on_corridor()).route(at(0, 0))
    assert route.doors[0] == "d"
    assert to_door(route, (10, 15.25)) == pytest.approx(18.236, abs=TOL)


def test_near_a_jamb_the_route_curves_round_its_ring():
    """From (0, 13.5) the straight line (10.152 ft) passes within 12 in of the jamb (8.5, 15): 10.543 ft."""
    route = routes(room_on_corridor()).route(at(0, 13.5))
    assert to_door(route, (10, 15.25)) == pytest.approx(10.543, abs=TOL)


def flush_jamb():
    """Test 10: a room 0 to 20 by 0 to 10, its exit door in the north wall flush with the east wall (centre
    (18.5, 10.25), jambs at x 17 and 20). The jamb (20, 10) is no corner of the floor (the east wall runs on into
    it), so only its own ring keeps the route off it."""
    return description([room("r", rect(0, 0, 20, 10), use="day_care")],
                       [door("x", (18.5, 10.25), (1, 0), ("r", "outside"), exit_id="A")])


def test_10_a_route_turning_just_past_a_door_keeps_12_in_off_its_jamb():
    # by hand: c = (20, 10), r = 1; p = (19.9, 8.9) is 1.10454 from c, the door centre 1.52069: tangents
    # sqrt(1.10454^2 - 1) = 0.46904 and sqrt(1.52069^2 - 1) = 1.14564; the directions from c are 264.806 and
    # 170.538 degrees, 94.268 apart, less acos(1/1.10454) = 25.129 and acos(1/1.52069) = 48.883: an arc of 20.256
    # degrees, 0.35354 ft. 0.46904 + 0.35354 + 1.14564 = 1.968 (the straight line, 1.945, passes 0.996 ft from c)
    assert feet(routes(flush_jamb()), 19.9, 8.9) == pytest.approx(1.968, abs=TOL)


# --- decision 1a: rooms a route may not cross ------------------------------------------------------------------------

def storeroom():
    """Test 5: a day-care room 0 to 40 by 0 to 10 with its own exit A (west, centre (-0.25, 5)); a storage room
    40.5 to 45 by 0 to 10 beyond its east door (centre (40.25, 5)), with exit B (centre (45.25, 5)) out of it."""
    return description([room("f", rect(0, 0, 40, 10), use="day_care"),
                        room("s", rect(40.5, 0, 45, 10), use="accessory_storage")],
                       [door("a", (-0.25, 5), (0, 1), ("f", "outside"), exit_id="A"),
                        door("fs", (40.25, 5), (0, 1), ("f", "s")),
                        door("b", (45.25, 5), (0, 1), ("s", "outside"), exit_id="B")])


def test_5_a_storeroom_shortcut_is_never_taken():
    # by hand: from (39, 5) straight along y = 5 to A's centre: 39.25 (every jamb 1.5 ft off the line); through the
    # storeroom to B it would be 1.25 + 5 = 6.25
    assert feet(routes(storeroom()), 39, 5) == pytest.approx(39.25, abs=TOL)
    # a start in the storeroom itself may leave by its own exit: 45.25 - 44 = 1.25
    assert feet(routes(storeroom()), 44, 5) == pytest.approx(1.25, abs=TOL)


def test_5_with_no_other_way_a_room_beyond_a_storeroom_has_no_route():
    d = storeroom()
    d["doors"] = d["doors"][1:]
    with pytest.raises(Stop) as stop:
        routes(d).route(at(39, 5))
    assert stop.value.key == "no_route"


def alcove():
    """Test 12: test 1's corridor with a storage alcove 20 to 34 by 6 to 12 in its inside corner, joined to it by
    separation lines along y = 6 and x = 34."""
    d = l_corridor()
    d["rooms"].append(room("al", rect(20, 6, 34, 12), use="accessory_storage"))
    d["passages"] = [{"rooms": ["c", "al"], "line": [[20, 6], [34, 6]]},
                     {"rooms": ["c", "al"], "line": [[34, 6], [34, 12]]}]
    return d


def test_12_a_storage_alcove_on_a_passage_isnt_crossed():
    assert feet(routes(alcove()), 40, 30) == pytest.approx(60.393, abs=TOL)    # test 1's route, round (34, 6)


def test_12_a_start_in_the_alcove_leaves_it_by_its_passages():
    """Decision 1: a start in an end-only room is joined, for its routes only, to the crossable zone beyond its
    passages. From (30, 9) the route leaves the alcove over y = 6 and curves round the ring of the alcove's corner
    (20, 6), which sticks into the corridor-and-alcove floor."""
    # by hand: c = (20, 6); p is sqrt(109) = 10.4403 from c, the door centre (-0.25, 3) sqrt(419.0625) = 20.4710:
    # tangents 10.3923 and 20.4466; the directions from c are 16.699 and -171.573 degrees, 188.272 apart clockwise
    # (round the south side), less acos(1/10.4403) = 84.504 and acos(1/20.4710) = 87.200: an arc of 16.569 degrees,
    # 0.2892 ft. 10.3923 + 0.2892 + 20.4466 = 31.128
    assert feet(routes(alcove()), 30, 9) == pytest.approx(31.128, abs=TOL)


def test_a_route_that_goes_back_into_its_end_only_room_isnt_measured():
    """Decision 1: a route may leave an end-only room by its passage, never come back in. A walk from (30, 9) in the
    alcove out over y = 6, back into the alcove and out again is refused; one that leaves once is taken."""
    from model_measurement.routes import paths
    alcove_room = story(alcove()).rooms["al"]
    out_and_back = paths.Path(0.0, [("line", at(30, 9), at(30, 5)), ("line", at(30, 5), at(28, 8)),
                                    ("line", at(28, 8), at(26, 5))])
    with pytest.raises(Stop) as stop:
        paths._leaves_once(out_and_back, alcove_room, at(30, 9))
    assert stop.value.key == "route_reenters"
    paths._leaves_once(paths.Path(0.0, [("line", at(30, 9), at(30, 5)), ("line", at(30, 5), at(10, 3))]),
                       alcove_room, at(30, 9))


def test_the_end_only_check_is_made_on_every_leg_through_a_passage(monkeypatch):
    from model_measurement.routes import paths
    seen = []
    monkeypatch.setattr(paths, "_leaves_once", lambda path, room, p: seen.append(room.id))
    routes(alcove()).route(at(30, 9))
    assert seen and set(seen) == {"al"}


def wing_and_lobby():
    """Test 14: a lobby 0 to 20 by 0 to 20 (no `pass_through`) with exit A (centre (-0.25, 10)); a wing 20.5 to 40
    by 0 to 20 opening on it (door centre (20.25, 10)) and on a corridor 40.5 to 48.5 by 0 to 20 (door centre
    (40.25, 10)) whose exit B is centred at (48.75, 10)."""
    return description([room("lobby", rect(0, 0, 20, 20), use="lobby"), room("wing", rect(20.5, 0, 40, 20),
                                                                                use="day_care"),
                        room("k", rect(40.5, 0, 48.5, 20))],
                       [door("a", (-0.25, 10), (0, 1), ("lobby", "outside"), exit_id="A"),
                        door("wl", (20.25, 10), (0, 1), ("lobby", "wing")),
                        door("wk", (40.25, 10), (0, 1), ("wing", "k")),
                        door("b", (48.75, 10), (0, 1), ("k", "outside"), exit_id="B")])


def test_14_a_lobby_is_crossed_only_when_marked_pass_through():
    # by hand: from (21, 10) along y = 10 (jambs 1.5 ft off): the way round, 19.25 + 8.5 = 27.75; through the lobby
    # it would be 0.75 + 20.5 = 21.25
    assert feet(routes(wing_and_lobby()), 21, 10) == pytest.approx(27.75, abs=TOL)
    d = wing_and_lobby()
    d["rooms"][0]["pass_through"] = True
    assert feet(routes(d), 21, 10) == pytest.approx(21.25, abs=TOL)


def test_14_with_no_way_round_a_wing_beyond_a_lobby_has_no_route():
    d = wing_and_lobby()
    d["doors"] = [x for x in d["doors"] if x["id"] != "b"]
    with pytest.raises(Stop) as stop:
        routes(d).route(at(21, 10))
    assert stop.value.key == "no_route"


def kitchen_and_pantry(own_exit=True):
    """Test 17: a kitchen 0 to 20 by 0 to 10 with its own exit A (centre (-0.25, 5)), joined by a separation line
    along x = 20 to a pantry 20 to 26 by 0 to 10 whose exit B is centred at (26.25, 5)."""
    doors = [door("b", (26.25, 5), (0, 1), ("p", "outside"), exit_id="B")]
    if own_exit:
        doors.append(door("a", (-0.25, 5), (0, 1), ("k", "outside"), exit_id="A"))
    return description([room("k", rect(0, 0, 20, 10), use="kitchen"),
                        room("p", rect(20, 0, 26, 10), use="accessory_storage")],
                       doors, passages=[(("k", "p"), [(20, 0), (20, 10)])])


def test_17_a_kitchen_leaves_by_its_own_door_never_through_its_pantry():
    # by hand: from (19, 5) along y = 5 to A: 19.25; through the pantry to B it would be 7.25
    route = routes(kitchen_and_pantry()).route(at(19, 5))
    assert route.feet == pytest.approx(19.25, abs=TOL) and route.exit_id == "A"


def test_17_with_no_door_of_its_own_a_kitchen_has_no_route():
    with pytest.raises(Stop) as stop:
        routes(kitchen_and_pantry(own_exit=False)).route(at(19, 5))
    assert stop.value.key == "no_route"


def sleeping_room():
    """Test 13: a sleeping room 0 to 60 by 0 to 20, its corridor door at the west end (centre (-0.25, 10)), a closet
    60.5 to 64 by 8 to 12 at the far end (door centre (60.25, 10)); the corridor -8.5 to -0.5 by 0 to 20 has exit
    A in its north wall (centre (-4.5, 20.25))."""
    return description([room("bed", rect(0, 0, 60, 20), use="other", sleeping=True),
                        room("closet", rect(60.5, 8, 64, 12), use="closet"), room("k", rect(-8.5, 0, -0.5, 20))],
                       [door("bk", (-0.25, 10), (0, 1), ("k", "bed")),
                        door("cl", (60.25, 10), (0, 1), ("bed", "closet")),
                        door("a", (-4.5, 20.25), (1, 0), ("k", "outside"), exit_id="A")])


def test_13_from_a_sleeping_rooms_far_end_the_route_leaves_by_its_corridor_door():
    # by hand: from (60, 10) along y = 10 to the corridor door's centre: 60.25 ft (the closet leads nowhere)
    route = routes(sleeping_room()).route(at(60, 10))
    assert route.doors[0] == "bk" and "cl" not in route.doors
    assert to_door(route, (-0.25, 10)) == pytest.approx(60.25, abs=TOL)


# --- what always gives needs review ------------------------------------------------------------------------------

def test_a_story_with_anything_to_review_gives_no_route_only_the_reasons():
    d = room_on_corridor()
    d["unknown_spaces"] = [{"id": "u", "name": "Enclosed area", "level": "L1"}]
    with pytest.raises(Stop) as stop:
        StoryRoutes(story(d))
    assert stop.value.key == "story_not_measured" and "no room drawn in it" in stop.value.reason


def test_a_point_off_the_floor_has_no_route():
    with pytest.raises(Stop) as stop:
        routes(column_room()).route(at(15, 5))                            # inside the column
    assert stop.value.key == "not_on_floor"


def alcove_too_narrow():
    """A room 0 to 20 by 0 to 10 with a niche 20 in wide and 2 ft deep in its north wall: the niche's mouth corners'
    rings (20 in apart, 12 in each) close it."""
    w = 10 / 12
    return description([room("r", [(0, 0), (20, 0), (20, 10), (10 + w, 10), (10 + w, 12), (10 - w, 12),
                                   (10 - w, 10), (0, 10)], use="day_care")],
                       [door("x", (-0.25, 5), (0, 1), ("r", "outside"), exit_id="A")])


def test_a_point_shut_in_by_rings_has_no_route_never_a_number():
    """At (10, 11.5) the niche's back is 1.5 ft deep, 1.20 ft from each mouth corner: outside both rings, and the
    rings overlap across the mouth, so no curve 12 in clear of both gets out (decision 2): no route (decision 10)."""
    got = routes(alcove_too_narrow())
    with pytest.raises(Stop) as stop:
        got.route(at(10, 11.5))
    assert stop.value.key == "no_route"
    # inside a ring in the niche's mouth, the route may run within it until it leaves (c): 11.634 by the code's
    # definition; checked here only to be a number
    assert got.route(at(10, 10.5)).feet > 9.75


def test_an_unknown_exit_id_is_said():
    with pytest.raises(Stop) as stop:
        routes(l_corridor()).route(at(1, 1), ["Z"])
    assert stop.value.key == "exit_unknown"


def test_a_route_that_would_come_back_into_a_lifted_ring_isnt_measured(monkeypatch):
    """A leg whose shortest curve, with a ring lifted for its start, leaves that ring and comes back in is longer
    under the definition: it stops rather than give the short figure (here a ring at the point's own corner made
    to look entered twice)."""
    from model_measurement.routes import paths
    monkeypatch.setattr(paths, "_inside_spans", lambda pieces, c, r: [(0.0, 1.0), (5.0, 6.0)])
    with pytest.raises(Stop) as stop:
        routes(l_corridor()).route(at(34.5, 6.5))
    assert stop.value.key == "route_reenters"


def test_where_a_path_is_inside_a_ring_is_exact():
    from model_measurement.routes import paths
    # a line through the ring at the origin (r 12 in) from (-20, 5): inside where |x| < sqrt(144 - 25) = 10.9087,
    # that is from 20 - 10.9087 = 9.0913 to 20 + 10.9087 = 30.9087 along it
    [(lo, hi)] = paths._inside_spans([("line", (-20.0, 5.0), (40.0, 5.0))], (0.0, 0.0), 12.0)
    assert (lo, hi) == (pytest.approx(9.0913, abs=1e-4), pytest.approx(30.9087, abs=1e-4))
    # an arc of the ring at (20, 0) from (8, 0) a quarter turn clockwise: inside the origin's ring while within
    # acos(20 / 24) = 33.557 degrees of (8, 0): 0.585686 rad x 12 = 7.0282 in
    [(lo, hi)] = paths._inside_spans([("arc", (20.0, 0.0), 12.0, math.pi, -math.pi / 2)], (0.0, 0.0), 12.0)
    assert (lo, hi) == (pytest.approx(0.0, abs=1e-9), pytest.approx(7.0282, abs=1e-4))


def test_a_path_leaving_its_starts_ring_and_coming_back_is_refused():
    from model_measurement.routes import paths
    # from (6, 0), inside the ring at the origin: out along y = 0, then back across the ring toward (-30, 6)
    back = paths.Path(0.0, [("line", (6.0, 0.0), (30.0, 0.0)), ("line", (30.0, 0.0), (-30.0, 6.0))])
    with pytest.raises(Stop):
        paths._check_lifted(back, (0.0, 0.0), 12.0, (6.0, 0.0), (-30.0, 6.0))
    paths._check_lifted(paths.Path(0.0, back.pieces[:1]), (0.0, 0.0), 12.0, (6.0, 0.0), (30.0, 0.0))


def test_an_arc_is_kept_only_where_it_stays_in_the_floor_and_out_of_other_rings():
    """Round a ring at (120, 120) in (radius 12): another ring at (138, 120) covers its arc within acos(18 / 24) =
    41.4 degrees of east; a wall 100 to 140 by 126 to 128 crosses it between 30 and 41.8 degrees (and between 138.2
    and 150)."""
    import numpy as np
    from shapely.geometry import Polygon
    from model_measurement.routes import paths
    floor = Polygon([(0, 0), (240, 0), (240, 240), (0, 240)], [[(100, 126), (140, 126), (140, 128), (100, 128)]])
    active = np.array([(120.0, 120.0), (138.0, 120.0)])
    leg = paths._Leg(floor, active, [], 12.0)
    deg = math.radians
    assert leg._arc_clear(0, active, (120.0, 120.0), deg(160), deg(100))        # the west side: clear
    assert leg._arc_clear(0, active, (120.0, 120.0), deg(45), deg(90))          # over the wall's top: clear
    assert not leg._arc_clear(0, active, (120.0, 120.0), deg(-45), deg(40))     # into the other ring
    assert not leg._arc_clear(0, active, (120.0, 120.0), deg(140), deg(5))      # through the wall's west end


def test_too_many_tied_routes_is_said(monkeypatch):
    from model_measurement.routes import paths
    monkeypatch.setattr(paths, "MOST_TIES", 1)
    with pytest.raises(Stop) as stop:
        routes(table_room()).routes(at(10, 0))
    assert stop.value.key == "too_many_ties"


PATH_KEYS = {"story_not_measured", "not_on_floor", "no_route", "route_reenters", "too_many_ties", "exit_unknown"}


def test_every_reason_has_a_case():
    from test_routes_floor import FLOOR_CASES
    assert set(FLOOR_CASES) | PATH_KEYS == set(STOPS)
