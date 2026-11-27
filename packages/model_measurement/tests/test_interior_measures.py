"""Each interior measurement on small hand-worked cases, and every reason one can stop with.

Every expected number here is worked out by hand in the comment beside it (inches; areas in sq ft). The last tests
make every reason in interior/stops.py happen, each from a case of its own, so none is dead text.
"""

import copy
import math

import pytest

from model_measurement.interior import measure
from model_measurement.interior.stops import STOPS, Stop


def base():
    """One bedroom with a casement window, a straight stair, a level guard and an exit door (inches)."""
    return {
        "format": "gordium.interior/1", "units": "in",
        "rooms": [{"id": "b", "name": "Bedroom", "sleeping": True, "floor": [[0, 0], [120, 0], [120, 120], [0, 120]],
                   "floor_elevation": 0, "ceiling_height": 96}],
        "openings": [{"id": "w", "name": "Window", "room": "b", "escape": True, "operation": "casement",
                      "frame": {"left": 0, "right": 30, "bottom": 20, "top": 60},
                      "hinged": {"side": "left", "open_angle": 90, "sash_width": 30, "sash_thickness": 2,
                                 "hinge_offset": 0},
                      "ground_outside": 0}],
        "stairs": [{"id": "s", "name": "Stair", "bottom_elevation": 0,
                    "nosings": [[[10 * j, 0, 7 * (j + 1)], [10 * j, 36, 7 * (j + 1)]] for j in range(4)],
                    "sides": {"left": [[-5, 36], [40, 36]], "right": [[-5, 0], [40, 0]]},
                    "handrails": [],
                    "overhead": [[[-5, -5, 120], [40, -5, 120], [40, 41, 120], [-5, 41, 120]]]}],
        "guards": [{"id": "g", "name": "Guard", "walking_surface": 100, "top": 136,
                    "extent": {"left": 0, "right": 10},
                    "members": [{"left": 0, "right": 10, "bottom": 134, "top": 136}]}],
        "doors": [{"id": "d", "name": "Door", "exit": True, "operation": "side_hinged", "hinge_side": "left",
                   "stops": {"hinge": 0, "latch": 34}, "hinge_pin": [0, 1.75], "leaf_closed": [[0, 0], [35, 1.75]],
                   "threshold_top": 0, "head_stop_bottom": 80}],
    }


def one(desc, kind, n=0):
    return measure(desc)["parts"][kind][n]


def changed(path, value, kind_key=None):
    """base() with one value set; path like ("openings", 0, "hinged", "open_angle"). value None deletes it."""
    d = base()
    node = d
    for k in path[:-1]:
        node = node[k]
    if value is _DELETE:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return d


_DELETE = object()


# --- the base case, by hand ----------------------------------------------------------------------------------------

def test_the_base_case():
    got = measure(base())
    w = got["parts"]["emergency_escape_opening"][0]["measures"]
    # frame 30 x 40, casement at 90 degrees: its 2 in edge stands in the opening: 28 x 40 = 1120 / 144
    assert w == {"opening_net_clear_width": 28.0, "opening_net_clear_height": 40.0,
                 "opening_net_clear_area": pytest.approx(7.777778), "opening_sill_height": 20.0,
                 "opening_at_grade": True, "opening_is_door": False}      # a casement is a window
    s = got["parts"]["stair"][0]
    # risers 7 (x4), treads 10 (x3); headroom least at the top nosing: 120 - 28
    assert s["measures"] == {"stair_riser_height": 7.0, "stair_tread_depth": 10.0, "stair_headroom": 92.0,
                             "stair_clear_width": 36.0, "stair_riser_variation": 0.0}
    assert s["more"]["stair_handrail_sides"] == 0 and s["more"]["stair_clear_width_at_handrail"] == 36.0
    g = got["parts"]["guard"][0]["measures"]
    assert g == {"guard_height": 36.0, "guard_opening_sphere": 10.0}   # one opening 10 wide x 34 high
    d = got["parts"]["egress_door"][0]["measures"]
    assert d == {"door_clear_width": 32.25, "door_clear_height": 80.0,   # 34 - (0 + 1.75)
                 "door_side_hinged": True}
    assert got["problems"] == [] and got["not_checked"] == []


# --- escape openings ------------------------------------------------------------------------------------------------

def opening_measures(d):
    p = one(d, "emergency_escape_opening")
    return p["measures"], p["not_measured"], p["more"]


def test_a_casement_open_60_degrees_covers_more():
    # 30 cos 60 + 2 sin 60 = 15 + 1.732051 = 16.732051 covered: 13.267949 clear
    m, _, _ = opening_measures(changed(("openings", 0, "hinged", "open_angle"), 60))
    assert m["opening_net_clear_width"] == pytest.approx(30 - 15 - math.sqrt(3), abs=1e-6)


def test_a_casement_hinge_offset_covers_more():
    m, _, _ = opening_measures(changed(("openings", 0, "hinged", "hinge_offset"), 3))
    assert m["opening_net_clear_width"] == 25.0                       # 30 - 3 - 2


def test_a_right_hinged_casement():
    d = changed(("openings", 0, "hinged", "side"), "right")
    d["openings"][0]["frame"]["left"] = 10                            # frame 10..30: 20 - 2 = 18
    m, _, _ = opening_measures(d)
    assert m["opening_net_clear_width"] == 18.0


def test_past_90_degrees_only_the_thickness_counts():
    m, _, _ = opening_measures(changed(("openings", 0, "hinged", "open_angle"), 120))
    assert m["opening_net_clear_width"] == pytest.approx(30 - 2 * math.sin(math.radians(120)), abs=1e-6)


def sliding(sashes, **frame):
    d = base()
    o = d["openings"][0]
    del o["hinged"]
    o.update(operation="double_hung", sashes=sashes)
    o["frame"].update(frame)
    return d


def test_a_double_hung_less_its_open_sashes():
    # frame 0..30 x 20..60; sashes cover 38..60: clear 30 x 18 = 540 / 144 = 3.75
    m, _, _ = opening_measures(sliding([{"left": 0, "right": 30, "bottom": 40, "top": 60},
                                        {"left": 0, "right": 30, "bottom": 38, "top": 58}]))
    assert (m["opening_net_clear_height"], m["opening_net_clear_area"]) == (18.0, 3.75)


def test_sashes_leaving_two_openings_give_no_value():
    _, stopped, _ = opening_measures(sliding([{"left": 0, "right": 30, "bottom": 35, "top": 45}]))
    assert "2 pieces" in stopped["opening_net_clear_area"]


def test_sashes_leaving_an_l_shape_give_no_value():
    _, stopped, _ = opening_measures(sliding([{"left": 15, "right": 30, "bottom": 40, "top": 60}]))
    assert set(stopped) >= {"opening_net_clear_area", "opening_net_clear_width", "opening_net_clear_height",
                            "opening_sill_height", "opening_at_grade"}
    assert "isn't a rectangle" in stopped["opening_net_clear_width"]


def test_sashes_covering_it_all_leave_nothing():
    m, stopped, _ = opening_measures(sliding([{"left": 0, "right": 30, "bottom": 20, "top": 60}]))
    assert m == {"opening_net_clear_area": 0.0, "opening_net_clear_height": 0.0, "opening_net_clear_width": 0.0,
                 "opening_is_door": False}
    assert {k for k, why in stopped.items() if why != STOPS["not_measured_yet"]} == {
        "opening_sill_height", "opening_at_grade", "opening_door_hinged_or_sliding"}     # the last: a window


def test_a_sliding_window_with_no_sashes_given():
    _, stopped, _ = opening_measures(sliding([]))
    assert "sashes" in stopped["opening_net_clear_area"]


def test_a_fixed_window_has_no_clear_opening():
    d = changed(("openings", 0, "operation"), "fixed")
    m, stopped, _ = opening_measures(d)
    assert m["opening_net_clear_area"] == 0.0 and "doesn't open" in stopped["opening_sill_height"]


@pytest.mark.parametrize("operation", ["awning", "hopper", "pivot", "tilt_turn", "other"])
def test_other_operations_need_the_makers_opening(operation):
    _, stopped, _ = opening_measures(changed(("openings", 0, "operation"), operation))
    assert "maker's net clear opening" in stopped["opening_net_clear_area"]


def test_the_makers_opening_alone():
    d = changed(("openings", 0, "operation"), "awning")
    d["openings"][0]["stated_clear"] = {"width": 24, "height": 25, "bottom": 30}
    m, _, _ = opening_measures(d)
    assert m == {"opening_net_clear_width": 24.0, "opening_net_clear_height": 25.0,
                 "opening_net_clear_area": pytest.approx(600 / 144), "opening_sill_height": 30.0,
                 "opening_at_grade": True, "opening_is_door": False}


def test_the_makers_and_the_drawn_opening_agreeing_give_the_smaller():
    d = base()
    d["openings"][0]["stated_clear"] = {"width": 28.05, "height": 39.95, "bottom": 20.05}   # within 1/16 in
    m, _, _ = opening_measures(d)
    assert (m["opening_net_clear_width"], m["opening_net_clear_height"], m["opening_sill_height"]) == \
        (28.0, 39.95, 20.05)


def test_the_makers_and_the_drawn_opening_disagreeing_give_no_value():
    d = base()
    d["openings"][0]["stated_clear"] = {"width": 30, "height": 40, "bottom": 20}            # 2 in wider
    _, stopped, _ = opening_measures(d)
    assert "differ (width)" in stopped["opening_net_clear_area"]
    d["openings"][0]["operation"] = "fixed"
    _, stopped, _ = opening_measures(d)
    assert "one opens" in stopped["opening_net_clear_area"]


def test_a_stated_zero_opening_agrees_with_a_fixed_window():
    d = changed(("openings", 0, "operation"), "fixed")
    d["openings"][0]["stated_clear"] = {"width": 0, "height": 40, "bottom": 20}
    m, _, _ = opening_measures(d)
    assert m["opening_net_clear_area"] == 0.0


def test_grade_floor_is_within_44_in_either_way():
    for ground, at in ((-24, True), (-24.01, False), (64, True), (64.5, False)):   # bottom at 20
        m, _, _ = opening_measures(changed(("openings", 0, "ground_outside"), ground))
        assert m["opening_at_grade"] is at, ground


def test_ground_given_at_several_points():
    m, _, _ = opening_measures(changed(("openings", 0, "ground_outside"), [0, -10]))
    assert m["opening_at_grade"] is True
    _, stopped, _ = opening_measures(changed(("openings", 0, "ground_outside"), [0, -30]))
    assert "some points" in stopped["opening_at_grade"]
    _, stopped, _ = opening_measures(changed(("openings", 0, "ground_outside"), []))
    assert "ground level" in stopped["opening_at_grade"]


def test_an_area_well_whose_readings_agree():
    d = changed(("openings", 0, "ground_outside"), 30)
    d["openings"][0]["area_well"] = {"floor_elevation": 10, "width": 36, "projection": 36}
    m, _, more = opening_measures(d)
    assert m["opening_at_grade"] is True                              # 10 above the well floor, 10 below the ground
    assert more == {"area_well_area": 9.0, "area_well_width": 36.0, "area_well_projection": 36.0,
                    "area_well_depth": 20.0}


def test_a_broken_area_well():
    d = base()
    d["openings"][0]["area_well"] = {"width": 36, "projection": 36}
    _, stopped, _ = opening_measures(d)
    assert "well's floor elevation" in stopped["area_well_area"] and "well's floor" in stopped["opening_at_grade"]
    d["openings"][0]["area_well"] = "deep"
    _, stopped, _ = opening_measures(d)
    assert "area well" in stopped["area_well_depth"]


def test_the_sill_is_above_the_rooms_finished_floor():
    d = changed(("rooms", 0, "floor_elevation"), -6)
    m, _, _ = opening_measures(d)
    assert m["opening_sill_height"] == 26.0


def test_an_opening_in_a_room_not_given():
    p = one(changed(("openings", 0, "room"), "nowhere"), "emergency_escape_opening")
    assert p["within"] == "nowhere" and "isn't one of the rooms" in p["not_measured"]["opening_sill_height"]


def test_two_rooms_with_one_id():
    d = base()
    d["rooms"].append(copy.deepcopy(d["rooms"][0]))
    p = one(d, "emergency_escape_opening")
    assert "2 rooms have the id 'b'" in p["not_measured"]["opening_sill_height"]


def test_an_opening_with_no_room_is_still_checked():
    p = one(changed(("openings", 0, "room"), _DELETE), "emergency_escape_opening")
    assert "within" not in p                                          # the checker: "isn't within any room"


def test_an_escape_opening_in_a_room_that_isnt_a_bedroom_is_listed_not_checked():
    d = base()
    d["rooms"][0]["sleeping"] = False
    got = measure(d)
    assert got["parts"]["emergency_escape_opening"] == [] and got["parts"]["sleeping_room"] == []
    assert got["not_checked"][0]["id"] == "w"


def test_a_window_not_marked_escape_isnt_a_part():
    got = measure(changed(("openings", 0, "escape"), False))
    assert got["parts"]["emergency_escape_opening"] == []


@pytest.mark.parametrize("path, value, words", [
    (("openings", 0, "hinged"), _DELETE, "hinged sash"),
    (("openings", 0, "hinged", "open_angle"), 0, "between 0 and 180"),
    (("openings", 0, "hinged", "open_angle"), True, "isn't a length"),
    (("openings", 0, "hinged", "side"), "up", "not one of left, right"),
    (("openings", 0, "hinged", "hinge_offset"), _DELETE, "offset"),
    (("openings", 0, "frame"), _DELETE, "frame isn't given"),
    (("openings", 0, "frame"), {"left": 5, "right": 5, "bottom": 0, "top": 1}, "isn't a rectangle"),
    (("openings", 0, "frame"), [1, 2], "isn't a rectangle"),
    (("openings", 0, "operation"), "rolling", "not one of"),
    (("openings", 0, "operation"), _DELETE, "operation isn't given"),
])
def test_opening_data_problems_give_no_value(path, value, words):
    _, stopped, _ = opening_measures(changed(path, value))
    assert words in stopped["opening_net_clear_area"]


def test_stated_clear_problems():
    d = changed(("openings", 0, "operation"), "awning")
    d["openings"][0]["stated_clear"] = {"width": -1, "height": 20, "bottom": 30}
    _, stopped, _ = opening_measures(d)
    assert "can't be less than zero" in stopped["opening_net_clear_area"]
    d["openings"][0]["stated_clear"] = "big"
    _, stopped, _ = opening_measures(d)
    assert "the maker's clear opening" in stopped["opening_net_clear_area"]


@pytest.mark.parametrize("key", ["sash_width", "sash_thickness", "hinge_offset"])
def test_a_negative_hinged_size_never_enlarges_the_opening(key):
    """Review round 1: a negative thickness, offset or width shrank what the sash covers (26 in clear, not 24.5)."""
    _, stopped, _ = opening_measures(changed(("openings", 0, "hinged", key), -1.5))
    assert "can't be less than zero" in stopped["opening_net_clear_width"]


def test_a_negative_area_well_size_gives_no_value():
    d = base()
    d["openings"][0]["area_well"] = {"floor_elevation": 10, "width": -36, "projection": -36}
    _, stopped, more = opening_measures(d)
    assert more == {} and "can't be less than zero" in stopped["area_well_area"]


def test_an_opening_with_no_room_is_kept_even_beside_a_room_with_no_id():
    """Review round 1: sleeping(None) matched an id-less room that isn't a bedroom, so the opening was dropped."""
    d = base()
    d["rooms"].append({"name": "Hall", "sleeping": False, "floor": [[0, 0], [1, 0], [1, 1]], "floor_elevation": 0,
                       "ceiling_height": 96})
    del d["openings"][0]["room"]
    got = measure(d)
    assert [p["id"] for p in got["parts"]["emergency_escape_opening"]] == ["w"] and got["not_checked"] == []
    assert "isn't one of the rooms" in got["parts"]["emergency_escape_opening"][0]["not_measured"][
        "opening_sill_height"]


def test_a_fixed_window_with_only_a_makers_opening_gives_no_value():
    """Review round 1: fixed, no frame, a maker's 30 x 30 opening read as 6.25 sq ft."""
    d = changed(("openings", 0, "operation"), "fixed")
    del d["openings"][0]["frame"]
    d["openings"][0]["stated_clear"] = {"width": 30, "height": 30, "bottom": 24}
    _, stopped, _ = opening_measures(d)
    assert "fixed window doesn't open" in stopped["opening_net_clear_area"]


def test_a_makers_opening_bigger_than_its_frame_gives_no_value():
    """Review round 1: an awning's maker's opening was never compared with its frame (16 sq ft in a 6 sq ft frame)."""
    d = changed(("openings", 0, "operation"), "awning")
    d["openings"][0]["stated_clear"] = {"width": 31, "height": 20, "bottom": 30}       # frame 0..30 x 20..60
    _, stopped, _ = opening_measures(d)
    assert "bigger than its frame" in stopped["opening_net_clear_area"]
    d["openings"][0]["stated_clear"] = {"width": 24, "height": 20, "bottom": 50}       # top 70, above the frame's 60
    _, stopped, _ = opening_measures(d)
    assert "bigger than its frame" in stopped["opening_net_clear_area"]
    d["openings"][0]["stated_clear"] = {"width": 24, "height": 20, "bottom": 30}       # inside: measured
    m, _, _ = opening_measures(d)
    assert m["opening_net_clear_area"] == pytest.approx(480 / 144)


def test_drawn_and_makers_bottoms_straddling_44_in_give_no_grade_floor():
    """Review round 1: the higher of two agreeing bottoms was used, which below the ground is the nearer one."""
    d = changed(("openings", 0, "ground_outside"), 64.03)        # drawn bottom 20: 44.03 below the ground
    d["openings"][0]["stated_clear"] = {"width": 28, "height": 39.95, "bottom": 20.05}   # 43.98 below
    m, stopped, _ = opening_measures(d)
    assert "opening_at_grade" not in m and "for grade-floor" in stopped["opening_at_grade"]
    assert m["opening_sill_height"] == 20.05                      # the cautious (higher) sill still stands


@pytest.mark.parametrize("value", [["s"], {"a": 1}, 3])
def test_ids_that_arent_text_never_crash(value):
    """Review round 1: a list or mapping as a stair's id, or as the stair a guard names, raised TypeError."""
    d = changed(("stairs", 0, "id"), value)
    assert one(d, "stair")["id"] == value
    d = stair_guard([[0, 36, 41], [30, 36, 64]], stair=value)
    assert "isn't one of the stairs" in guard(d)[1]["guard_height"]
    del d["stairs"]
    assert "guard_height" in guard(d)[1]


# --- rooms ----------------------------------------------------------------------------------------------------------

def room(d):
    p = one(d, "sleeping_room")
    return p["measures"], p["not_measured"], p["more"]


def test_a_room_with_a_ceiling_exactly_7_ft():
    m, _, _ = room(changed(("rooms", 0, "ceiling_height"), 84))
    assert m == {"sleeping_room_floor_area": 100.0}                   # 120 x 120 / 144


def test_a_room_with_a_ceiling_under_7_ft():
    m, stopped, more = room(changed(("rooms", 0, "ceiling_height"), 83.9))
    assert m == {} and "R312.3" in stopped["sleeping_room_floor_area"] and more["floor_area_drawn"] == 100.0


def ceilings(*pieces):
    d = changed(("rooms", 0, "ceiling_height"), _DELETE)
    d["rooms"][0]["ceilings"] = list(pieces)
    return d


def test_a_sloped_ceiling_is_least_at_its_low_side():
    # rises from 90 at x = 0 to 120 at x = 120: least 90
    m, _, more = room(ceilings([[0, 0, 90], [120, 0, 120], [120, 120, 120], [0, 120, 90]]))
    assert more["least_ceiling_height"] == 90.0 and m["sleeping_room_floor_area"] == 100.0


def test_a_ceiling_reaching_past_the_room_is_read_only_over_it():
    # the slope continues down to 60 at x = -60, outside the room: over the room it is 90 at the least
    _, _, more = room(ceilings([[-60, 0, 60], [120, 0, 120], [120, 120, 120], [-60, 120, 60]]))
    assert more["least_ceiling_height"] == pytest.approx(80.0)        # 60 + 30 x (60 / 180) at x = 0
    m, _, _ = room(ceilings([[-60, 0, 60], [120, 0, 120], [120, 120, 120], [-60, 120, 60]]))
    assert m == {}


def test_a_ceiling_not_covering_the_room():
    _, stopped, _ = room(ceilings([[0, 0, 96], [60, 0, 96], [60, 120, 96], [0, 120, 96]]))
    assert "doesn't cover the whole room" in stopped["sleeping_room_floor_area"]


@pytest.mark.parametrize("piece, words", [
    ([[0, 0, 96], [120, 0, 96], [120, 0, 50]], "vertical"),
    ([[0, 0, 96], [120, 0, 96], [120, 120, 100], [0, 120, 96]], "isn't flat"),
    ([[0, 0, 96], [120, 0, 96]], "outline"),
])
def test_bad_ceiling_pieces(piece, words):
    _, stopped, _ = room(ceilings(piece))
    assert words in stopped["sleeping_room_floor_area"]


def test_room_problems():
    _, stopped, _ = room(changed(("rooms", 0, "ceiling_height"), _DELETE))
    assert "ceiling isn't given" in stopped["sleeping_room_floor_area"]
    d = base()
    d["rooms"][0]["ceilings"] = [[[0, 0, 96], [120, 0, 96], [120, 120, 96]]]
    _, stopped, _ = room(d)
    assert "both" in stopped["sleeping_room_floor_area"]
    _, stopped, _ = room(changed(("rooms", 0, "floor"), [[0, 0], [10, 10], [0, 10], [10, 0]]))   # a bow tie
    assert "outline" in stopped["sleeping_room_floor_area"]
    _, stopped, _ = room(ceilings())
    assert "ceilings" in stopped["sleeping_room_floor_area"]


# --- stairs ---------------------------------------------------------------------------------------------------------

def stair(d):
    p = one(d, "stair")
    return p["measures"], p["not_measured"], p["more"]


def nosings(risers, treads, width=36):
    """Nosings for risers [r1, r2, ...] (from the floor at 0) and treads [t1, ...] (len = len(risers) - 1)."""
    out, z, s = [], 0.0, 0.0
    for n, r in enumerate(risers):
        z += r
        out.append([[s, 0, z], [s, width, z]])
        if n < len(treads):
            s += treads[n]
    return out


def flight(risers, treads, **extra):
    d = base()
    d["stairs"][0]["nosings"] = nosings(risers, treads)
    d["stairs"][0].update(extra)
    return d


def test_riser_and_tread_extremes():
    m, _, more = stair(flight([7, 7.5, 7, 7.25], [10, 9.5, 10.25]))
    assert m["stair_riser_height"] == 7.5 and m["stair_tread_depth"] == 9.5
    assert m["stair_riser_variation"] == 0.5 and more["stair_tread_variation"] == 0.75
    assert more["stair_total_rise"] == 28.75 and more["stair_risers"] == 4


def test_spiral_is_taken_only_where_the_nosings_agree():
    # R202: a spiral's treads radiate from a column; a straight flight with rectangular treads is not one
    d = flight([7, 7, 7, 7], [10, 10, 10])
    m, stopped, _ = stair(d)
    assert "stair_spiral" not in m and "isn't given" in stopped["stair_spiral"]          # not said: not known
    d["stairs"][0]["spiral"] = False
    assert stair(d)[0]["stair_spiral"] is False
    d["stairs"][0]["spiral"] = True                                                      # said spiral, drawn straight
    m, stopped, _ = stair(d)
    assert "stair_spiral" not in m and "which is right is unclear" in stopped["stair_spiral"]
    del d["stairs"][0]["nosings"]                       # said spiral, nothing measured: never true (review round 1)
    m, stopped, _ = stair(d)
    assert "stair_spiral" not in m and "closed circular form" in stopped["stair_spiral"]
    d["stairs"][0]["spiral"] = False                                                     # said straight, shape unread
    m, stopped, _ = stair(d)
    assert "stair_spiral" not in m and "isn't measured as a straight flight" in stopped["stair_spiral"]
    d["stairs"][0]["spiral"] = "no"                                                      # not true or false
    assert "stair_spiral" not in stair(d)[0]


def test_the_bottom_riser_is_from_the_floor():
    d = flight([7, 7, 7, 7], [10, 10, 10])
    d["stairs"][0]["bottom_elevation"] = -1.5                          # the floor at the foot is 1.5 lower
    m, _, more = stair(d)
    assert m["stair_riser_height"] == 8.5 and m["stair_riser_variation"] == 1.5


def test_a_flight_running_any_direction():
    """The base flight turned 30 degrees and moved: the same numbers."""
    d = base()
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))

    def turn(x, y):
        return [x * c - y * s + 100, x * s + y * c - 50]

    st = d["stairs"][0]
    st["nosings"] = [[turn(*p[:2]) + [p[2]] for p in n] for n in st["nosings"]]
    st["sides"] = {k: [turn(*p) for p in v] for k, v in st["sides"].items()}
    st["overhead"] = [[turn(*p[:2]) + [p[2]] for p in o] for o in st["overhead"]]
    m, _, _ = stair(d)
    assert m == pytest.approx({"stair_riser_height": 7.0, "stair_tread_depth": 10.0, "stair_headroom": 92.0,
                               "stair_clear_width": 36.0, "stair_riser_variation": 0.0})


def test_nosings_given_top_down_or_turned_around_still_read_up():
    d = base()
    d["stairs"][0]["nosings"] = [[n[1], n[0]] for n in d["stairs"][0]["nosings"]]   # each nosing's ends swapped
    m, _, _ = stair(d)
    assert m["stair_clear_width"] == 36.0 and m["stair_tread_depth"] == 10.0


def test_headroom_under_a_beam():
    # a beam's underside at 90 over s 15..20: the nosing line there is 7 + 0.7 x 20 = 21 at the most: 90 - 21 = 69
    d = base()
    d["stairs"][0]["overhead"].append([[15, -5, 90], [20, -5, 90], [20, 41, 90], [15, 41, 90]])
    m, _, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(69.0)


def test_headroom_under_a_sloped_soffit():
    # soffit z = 100 + 0.5 s; nosing line z = 7 + 0.7 s; gap 93 - 0.2 s, least at s = 30: 87
    d = base()
    d["stairs"][0]["overhead"] = [[[-5, -5, 97.5], [40, -5, 120], [40, 41, 120], [-5, 41, 97.5]]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(87.0)


def test_headroom_with_one_tall_riser_follows_the_nosings():
    # risers 7, 7, 10, 7 (top nosing 31 at s 30): flat ceiling at 110: least 110 - 31 = 79
    d = flight([7, 7, 10, 7], [10, 10, 10])
    d["stairs"][0]["overhead"][0] = [[-5, -5, 110], [40, -5, 110], [40, 41, 110], [-5, 41, 110]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == 79.0


def test_headroom_not_covering_the_flight():
    d = base()
    d["stairs"][0]["overhead"] = [[[-5, -5, 120], [25, -5, 120], [25, 41, 120], [-5, 41, 120]]]
    _, stopped, _ = stair(d)
    assert "doesn't cover the whole flight" in stopped["stair_headroom"]


def test_headroom_problems():
    _, stopped, _ = stair(changed(("stairs", 0, "overhead"), []))
    assert "nothing above" in stopped["stair_headroom"]
    _, stopped, _ = stair(changed(("stairs", 0, "overhead"), _DELETE))
    assert "what is above the flight isn't given" in stopped["stair_headroom"]
    _, stopped, _ = stair(changed(("stairs", 0, "overhead"), {"a": 1}))
    assert "aren't a list" in stopped["stair_headroom"]


def test_handrails_narrow_the_width_below_them():
    d = base()
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[0, 32.5], [30, 32.5]]},
                                   {"side": "right", "inner_edge": [[0, 4], [30, 4]]}]
    m, _, more = stair(d)
    assert m["stair_clear_width"] == 36.0
    assert more["stair_clear_width_at_handrail"] == 28.5 and more["stair_handrail_sides"] == 2   # 32.5 - 4


def test_a_handrail_on_part_of_the_flight_still_counts_where_it_is():
    d = base()
    d["stairs"][0]["handrails"] = [{"side": "right", "inner_edge": [[10, 4], [20, 4]]}]
    _, _, more = stair(d)
    assert more["stair_clear_width_at_handrail"] == 32.0


def test_a_handrail_off_the_flight_never_counts_as_a_side():
    # both handrails lie wholly past the top nosing (s = 30): counted, they would make a 1-side stair read as 2,
    # and the width at the handrail would be held to 27 in instead of 31 1/2 (R318.7.1)
    d = base()
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[200, 33], [300, 33]]},
                                   {"side": "right", "inner_edge": [[200, 3], [300, 3]]}]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more
    assert "runs the whole flight" in stopped["stair_handrail_sides"]
    assert more["stair_clear_width_at_handrail"] == 36.0          # they narrow nothing on the flight


def test_a_handrail_part_way_gives_no_side_count():
    # a 2 in stub on each side: not a handrail "installed" on that side (R320.5: the full length of the flight)
    d = base()
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[0, 33], [2, 33]]},
                                   {"side": "right", "inner_edge": [[0, 3], [2, 3]]}]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more and "left" in stopped["stair_handrail_sides"]
    assert more["stair_clear_width_at_handrail"] == 30.0          # where they run, they still narrow it
    # one side the whole flight, the other part way: still no count (1 would be wrong too, 2 too favourable)
    d["stairs"][0]["handrails"][0]["inner_edge"] = [[0, 33], [30, 33]]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more and "right" in stopped["stair_handrail_sides"]


def test_a_handrail_outside_the_stairs_sides_never_counts():
    """Review round 6: only checked along the run, rails 14 in past each wall (in the next room) made 2 sides."""
    d = base()
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[0, 50], [30, 50]]},
                                   {"side": "right", "inner_edge": [[0, -14], [30, -14]]}]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more and "between the stair's sides" in stopped["stair_handrail_sides"]
    # one real rail inside the left wall, the other past the right wall: 2 would be too favourable, 1 wrong too
    d["stairs"][0]["handrails"][0]["inner_edge"] = [[0, 33], [30, 33]]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more and "right" in stopped["stair_handrail_sides"]
    # inside the walls, the whole flight: both count
    d["stairs"][0]["handrails"][1]["inner_edge"] = [[0, 3], [30, 3]]
    assert stair(d)[2]["stair_handrail_sides"] == 2


def test_a_mislabelled_handrail_keeps_the_width_above_it():
    """Review round 6: a left handrail drawn right of the right wall threw away the clear width (36) too."""
    d = base()
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[0, -2], [30, -2]]}]
    m, stopped, more = stair(d)
    assert m["stair_clear_width"] == 36.0
    assert "a handrail meets or crosses" in stopped["stair_clear_width_at_handrail"]
    assert "stair_handrail_sides" in stopped and "stair_clear_width_at_handrail" not in more


def test_treads_shorter_than_the_walls_narrow_the_width_at_the_treads():
    # a 1 in and a 1 1/2 in skirt between the tread ends and the walls (at most a stringer's 1 1/2 in)
    d = base()
    d["stairs"][0]["nosings"] = [[[10 * j, 1, 7 * (j + 1)], [10 * j, 34.5, 7 * (j + 1)]] for j in range(4)]
    m, _, more = stair(d)
    assert m["stair_clear_width"] == 36.0 and more["stair_clear_width_at_handrail"] == 33.5


def _landing_wider_on_the_open_side(top_width):
    """The base stair with its left side open and the top nosing (the landing's edge) top_width wide."""
    d = changed(("stairs", 0, "sides", "left"), "open")
    d["stairs"][0]["nosings"][3] = [[30, 0, 28], [30, top_width, 28]]
    d["stairs"][0]["overhead"] = [[[-5, -5, 120], [40, -5, 120], [40, 60, 120], [-5, 60, 120]]]
    return d


@pytest.mark.parametrize("top_width", [36, 48])
def test_a_tread_never_widens_toward_a_wider_nosing_above(top_width):
    """Review round 7: tread ends were drawn straight from one nosing to the next, so a landing edge 48 in wide made
    the 36 in top tread (s 20..30) read 42 in wide halfway. Each tread holds its own width back to the next nosing:
    with the right side jogging in to 6 at s 25, the clear width there is 36 - 6 = 30 (it read 36)."""
    d = _landing_wider_on_the_open_side(top_width)
    d["stairs"][0]["sides"]["right"] = [[-5, 0], [24.9, 0], [25, 6], [40, 6]]
    m, _, more = stair(d)
    assert m["stair_clear_width"] == 30.0 and more["stair_clear_width_at_handrail"] == 30.0
    # a handrail part way, on the right at 6 over s 25..33, narrows the top tread the same way: 36 - 6 (it read 36)
    d = _landing_wider_on_the_open_side(top_width)
    d["stairs"][0]["handrails"] = [{"side": "right", "inner_edge": [[25, 6], [33, 6]]}]
    _, _, more = stair(d)
    assert more["stair_clear_width_at_handrail"] == 30.0


def test_a_handrail_past_a_treads_end_never_counts_for_an_open_side():
    """Review round 7: a left handrail running 30 to 38 across the flight on an open side stands past the 36 in top
    tread's end at s 30 (36.89 there) but inside the 48 in landing edge it was drawn toward: it counted as a side."""
    d = _landing_wider_on_the_open_side(48)
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[-1, 30], [35, 38]]}]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more and "left" in stopped["stair_handrail_sides"]


def test_a_nosing_drawn_as_a_point_is_no_nosing():
    """Review round 7: a nosing with both ends at one point gave a width of 0 'because a handrail crosses', with
    no handrail on the stair. It isn't a nosing across the stair: the flight isn't placed."""
    d = base()
    d["stairs"][0]["nosings"][1] = [[10, 18, 14], [10, 18, 14]]
    m, stopped, _ = stair(d)
    assert "stair_clear_width" not in m and "nosing 2" in stopped["stair_clear_width"]
    assert m["stair_riser_height"] == 7.0                               # its height is still read


def test_treads_past_a_side_say_so_not_a_handrail():
    """Review round 7: tread ends beyond a wall (a tread 40..50 between walls at 0 and 36) were blamed on a
    handrail, with none drawn. The width above the treads (36) still stands."""
    # round 9: the right wall at 0 must stand at the tread ends, so the crossing is drawn with the right side open:
    # tread 1 ends at 34.6 under the left wall (36, a skirt of 1.4); tread 2 starts at 35, past it (into the wall)
    d = base()
    d["stairs"][0]["sides"]["right"] = "open"
    d["stairs"][0]["nosings"][0] = [[0, 0, 7], [0, 34.6, 7]]
    d["stairs"][0]["nosings"][1] = [[10, 35, 14], [10, 40, 14]]
    m, stopped, more = stair(d)
    assert m["stair_clear_width"] == 1.0 and "stair_clear_width_at_handrail" not in more     # 36 - 35
    assert "a tread's end meets or crosses" in stopped["stair_clear_width_at_handrail"]
    assert "handrail meets" not in stopped["stair_clear_width_at_handrail"]


@pytest.mark.parametrize("left, right, ends, width", [
    (40, 0, (0, 30), None),           # treads 30 wide between walls 40 apart: before, a clear width of 40
    (136, -100, (0, 36), None),       # walls drawn 100 in off the treads: before, 236
    (37.5, 0, (0, 36), 37.5),         # a 1 1/2 in stringer between the treads and the left wall, wall to wall
    (37.5625, 0, (0, 36), None),      # 1/16 in more than a stringer
    (36, -1.5, (0, 36), 37.5),
    (30, 0, (0, 36), 30.0),           # the treads run past the wall, into it: the wall bounds them
])
def test_a_side_must_stand_at_the_tread_ends(left, right, ends, width):
    """Round 9: a drawn side was never checked against the treads, so a wall drawn anywhere still bounded the
    stair, and a guard or handrail drawn with it counted."""
    d = base()
    d["stairs"][0]["nosings"] = [[[10 * j, ends[0], 7 * (j + 1)], [10 * j, ends[1], 7 * (j + 1)]] for j in range(4)]
    d["stairs"][0]["sides"] = {"left": [[-5, left], [40, left]], "right": [[-5, right], [40, right]]}
    d["stairs"][0]["overhead"] = [[[-5, -200, 120], [40, -200, 120], [40, 200, 120], [-5, 200, 120]]]
    m, stopped, _ = stair(d)
    assert m.get("stair_clear_width") == width, stopped
    if width is None:
        assert "out beyond its treads' ends" in stopped["stair_clear_width"]


def test_a_guard_and_handrail_on_a_side_drawn_far_off_never_count():
    """Round 9: the round-8 guard check compared the guard with the drawn side only, so the side and the guard drawn
    together 500 in off still gave a guard height (34.78); a handrail at 300 in counted as the left handrail."""
    d = stair_guard([[-5, 536, 41], [40, 536, 69]])
    d["stairs"][0]["sides"]["left"] = [[-5, 536], [40, 536]]
    m, stopped = guard(d)
    assert "guard_height" not in m and "out beyond its treads' ends" in stopped["guard_height"]
    d["stairs"][0]["handrails"] = [{"side": "left", "inner_edge": [[-5, 300], [40, 300]]}]
    _, stopped, more = stair(d)
    assert "stair_handrail_sides" not in more and "out beyond" in stopped["stair_handrail_sides"]


def test_random_sides_count_only_at_the_tread_ends():
    """Round 9, property check: 1,500 random flights whose sides stand anywhere from the tread ends to far off,
    straight or bent, with a guard on the left side. Whenever a width or a guard height is given, each drawn side
    stands no more than 1 1/2 in beyond its treads' ends at every sampled point."""
    import random
    rnd = random.Random(9)
    given = 0
    for _ in range(1500):
        n = rnd.randint(2, 5)
        run = 10 * (n - 1)
        ends = [(rnd.choice([0, rnd.uniform(-1, 1)]), rnd.choice([36, rnd.uniform(35, 37)])) for _ in range(n)]
        sides = {}
        for k, base_a, sign in (("left", 36, 1), ("right", 0, -1)):
            off = [base_a + sign * rnd.choice([0, rnd.uniform(0, 1.6), rnd.uniform(0, 600), rnd.uniform(-3, 0)])
                   for _ in range(3)]
            sides[k] = [[-5, off[0]], [run / 2, off[1]], [run + 5, off[2]]]
        d = stair_guard([[p[0], p[1], 7 * (1 + max(0, min(p[0], run)) / 10) + 36] for p in sides["left"]])
        d["stairs"][0].update(
            nosings=[[[10 * j, ends[j][0], 7 * (j + 1)], [10 * j, ends[j][1], 7 * (j + 1)]] for j in range(n)],
            sides=sides,
            overhead=[[[-20, -900, 400], [run + 20, -900, 400], [run + 20, 900, 400], [-20, 900, 400]]])
        m, _, _ = stair(d)
        g, _ = guard(d)
        if "stair_clear_width" not in m and "guard_height" not in g:
            continue
        given += 1

        def side_a(k, s):
            pts = sides[k]
            for (s1, a1), (s2, a2) in zip(pts, pts[1:]):
                if s1 <= s <= s2:
                    return a1 + (s - s1) / (s2 - s1) * (a2 - a1)

        for s in [rnd.uniform(0, run) for _ in range(300)]:
            j = min(int(s // 10), n - 1)
            assert side_a("left", s) - ends[j][1] <= 1.5 + 1e-9
            assert ends[j][0] - side_a("right", s) <= 1.5 + 1e-9
    assert given > 100


def test_a_wall_over_the_far_end_of_an_askew_top_nosing_narrows_the_width():
    """Round 10: widths were read only up to the top nosing's middle. With it drawn 1/16 in askew (allowed), its
    right end at s 30.031, the last tread runs there on the right, and a wall jutting in to 4 at s 30.02 was missed:
    36, not 36 - 4."""
    d = base()
    d["stairs"][0]["nosings"][3] = [[30.03125, 0, 28], [29.96875, 36, 28]]
    d["stairs"][0]["sides"]["right"] = [[-5, 0], [30.01, 0], [30.02, 4], [40, 4]]
    m, _, _ = stair(d)
    assert m["stair_clear_width"] == pytest.approx(32.0)


def test_a_tread_starts_at_its_nosings_nearer_end():
    """Round 10: each tread now runs from its nosing's nearer end (a nosing askew within 1/16 in). Nosing 2's left
    end stands at s 9.969 and that tread is 34 wide; the left wall bulges out to 37.4 at s 9.98, already over it:
    3.4 in beyond its end, more than a stringer. Read from the nosing's middle (s 10), the bulge fell on tread 1
    (36 wide, 1.4 in off) and the wall was taken as the stair's side."""
    d = base()
    d["stairs"][0]["nosings"][1] = [[10.03125, 0, 14], [9.96875, 34, 14]]
    d["stairs"][0]["nosings"][2] = [[20, 0, 21], [20, 34, 21]]
    d["stairs"][0]["nosings"][3] = [[30, 0, 28], [30, 34, 28]]
    d["stairs"][0]["sides"]["left"] = [[-5, 36], [9.97, 36], [9.98, 37.4], [9.99, 35.5], [40, 35.5]]
    _, stopped, _ = stair(d)
    assert "out beyond its treads' ends" in stopped["stair_clear_width"]


@pytest.mark.parametrize("far", [math.inf, None])
def test_nosings_too_large_to_measure_give_no_value_never_nan_or_a_crash(far, monkeypatch):
    """Round 11: nosing ends 1.8e308 apart overflowed the run direction to NaN, which every check let through: a NaN
    tread depth was reported, then the geometry library raised and lost the whole house. Round 12: refused as they
    are read (too_far); with that bound lifted, the flight's own check still refuses them."""
    import json
    if far:
        monkeypatch.setattr("model_measurement.interior.read.FAR", far)
    d = base()
    d["stairs"][0]["nosings"] = [[[10 * j, -9e307, 7 * (j + 1)], [10 * j, 9e307, 7 * (j + 1)]] for j in range(3)]
    out = measure(d)
    json.dumps(out, allow_nan=False)                                  # no NaN anywhere
    p = out["parts"]["stair"][0]
    assert "stair_tread_depth" not in p["measures"] and "stair_headroom" not in p["measures"]
    assert ("too large to measure" if far else "15,800 miles") in p["not_measured"]["stair_headroom"]


def _huge_stair_overhead_only_over_36_in(half):
    d = base()
    d["stairs"][0]["sides"] = {"left": "open", "right": "open"}
    d["stairs"][0]["nosings"][1] = [[10, -half, 14], [10, half, 14]]
    d["stairs"][0]["overhead"] = [[[-5, -5, 120], [40, -5, 120], [40, 41, 120], [-5, 41, 120]]]
    return d


@pytest.mark.parametrize("far", [math.inf, None])
def test_an_overflowing_area_is_never_read_as_covered(far, monkeypatch):
    """Round 12: a nosing 2e307 wide made the flight's area infinite, and `inf <= inf` passed the coverage check: a
    headroom of 92 over a flight covered only on 36 in of it. A 1e154 room floor did the same for its ceiling. Now
    such lengths are refused as read. With that bound lifted the coverage check still refuses the room's infinite
    area; the stair's tread is lost to rounding inside the geometry library before any area is worked out, which is
    why the bound, not a later check, is the fix."""
    m, stopped, _ = stair(_huge_stair_overhead_only_over_36_in(1e307))
    assert "stair_headroom" not in m, m
    if far:
        monkeypatch.setattr("model_measurement.interior.read.FAR", far)
    d = base()
    d["rooms"][0].pop("ceiling_height")
    d["rooms"][0].update(floor=[[0, 0], [1e154, 0], [1e154, 1e154], [0, 1e154]],
                         ceilings=[[[0, 0, 96], [120, 0, 96], [120, 120, 96], [0, 120, 96]]])
    p = one(d, "sleeping_room")
    assert "least_ceiling_height" not in p["more"] and "sleeping_room_floor_area" not in p["measures"]


@pytest.mark.parametrize("far", [math.inf, None])
def test_a_flight_too_wide_to_cut_never_crashes(far, monkeypatch):
    """Round 12: a nosing 2e308 wide (each end finite) left nothing to read overhead, and min() of no gaps raised
    out of measure()."""
    if far:
        monkeypatch.setattr("model_measurement.interior.read.FAR", far)
    d = _huge_stair_overhead_only_over_36_in(1e308)
    m, stopped, _ = stair(d)
    assert "stair_headroom" not in m and "stair_headroom" in stopped


HUGE_CASES = {
    "door_clear_height": lambda d: d["doors"][0].update(threshold_top=-1.7e308, head_stop_bottom=1.7e308),
    "guard_height": lambda d: d["guards"][0].update(walking_surface=-1.7e308, top=1.7e308, members=[
        {"left": 0, "right": 10, "bottom": 1e308, "top": 1.7e308}]),
    "sleeping_room_floor_area": lambda d: d["rooms"][0].update(floor=[[0, 0], [1e154, 0], [1e154, 1e154],
                                                                      [0, 1e154]]),
    "opening_net_clear_area": lambda d: d["openings"][0].update(operation="awning", frame=None, stated_clear={
        "width": 1e200, "height": 1e200, "bottom": 30}),
    "stair_riser_height": lambda d: d["stairs"][0].update(bottom_elevation=-1.7e308, nosings=[
        [[10 * j, 0, 1e308], [10 * j, 36, 1e308]] for j in range(4)]),
}


@pytest.mark.parametrize("far", [math.inf, None])
@pytest.mark.parametrize("name", sorted(HUGE_CASES))
def test_lengths_far_apart_never_give_infinity_or_nan(name, far, monkeypatch):
    """Round 12: two huge but finite lengths subtracted or multiplied gave inf or NaN measures (the output wasn't
    even valid JSON). Now refused as read (too_far); with that bound lifted, the last guard leaves them out."""
    import json
    if far:
        monkeypatch.setattr("model_measurement.interior.read.FAR", far)
    d = base()
    HUGE_CASES[name](d)
    out = measure(d)
    json.dumps(out, allow_nan=False)
    parts = [p for ps in out["parts"].values() for p in ps or []]
    assert not any(name in p["measures"] or name in p["more"] for p in parts)
    assert any(name in p["not_measured"] for p in parts)


def test_a_guard_too_far_off_gives_no_sphere():
    """Round 12 (a sceptic's case): a guard 1.7e308 in tall with a 10 in gap under its one member read a sphere of
    0 (a solid guard): the geometry library lost the gap to rounding. Lengths that far are now refused as read."""
    d = base()
    d["guards"][0].update(walking_surface=0, top=1.7e308, members=[{"left": 0, "right": 10, "bottom": 8.5e307,
                                                                    "top": 1.7e308}])
    m, stopped = guard(d)
    assert "guard_opening_sphere" not in m and "15,800 miles" in stopped["guard_opening_sphere"]


def test_a_house_a_long_way_from_the_origin_still_measures():
    """The bound is far: a whole description moved 10,000,000 in (158 miles) off its origin measures the same."""
    def moved(v, key=None):
        if isinstance(v, list) and v and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v) \
                and len(v) in (2, 3):
            return [v[0] + 1e7, v[1] + 1e7] + v[2:]
        if isinstance(v, list):
            return [moved(x) for x in v]
        if isinstance(v, dict):
            return {k: moved(x, k) for k, x in v.items()}
        return v
    d = base()
    d["stairs"] = moved(d["stairs"])
    assert stair(d)[0] == stair(base())[0]


def _rotated_flight(theta, ox, oy, askew):
    """A square 36 in flight of 4 nosings, turned by theta about (ox, oy), the second nosing's left end askew."""
    c, s = math.cos(theta), math.sin(theta)

    def xy(u, v):
        return [ox + u * c - v * s, oy + u * s + v * c]

    nos = [[xy(10 * j, 0) + [7 * (j + 1)], xy(10 * j + (askew if j == 1 else 0), 36) + [7 * (j + 1)]]
           for j in range(4)]
    d = base()
    d["stairs"][0].update(nosings=nos, sides={"left": "open", "right": "open"}, handrails=[],
                          overhead=[[xy(-20, -20) + [300], xy(60, -20) + [300], xy(60, 60) + [300],
                                     xy(-20, 60) + [300]]])
    return d


def test_a_rotated_flight_with_an_askew_nosing_never_crashes():
    """Round 10: unioned in plan, the treads' near-parallel edges on a turned flight made the geometry library fail
    (TopologyException) 25 times in 2,000, and the exception lost the whole house. Now the band is drawn in the
    flight's own frame: every flight gives its headroom (300 - 28 at the top nosing)."""
    import random
    rnd = random.Random(3)
    d = base()
    d["stairs"][0].update(
        nosings=[[[3.609671806592651, -34.438607528785695, 7], [-28.287722147056215, -17.74860276648186, 7]],
                 [[8.16159034834538, -25.739128946302444, 14], [-23.725179759743668, -9.028820236099826, 14]]],
        sides={"left": "open", "right": "open"}, handrails=[],
        overhead=[[[-100, -100, 300], [100, -100, 300], [100, 100, 300], [-100, 100, 300]]])
    m, stopped, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(286.0), stopped
    for _ in range(2000):
        m, stopped, _ = stair(_rotated_flight(rnd.uniform(0, 2 * math.pi), rnd.uniform(-50, 50),
                                              rnd.uniform(-50, 50), 1 / 64))
        assert m["stair_headroom"] == pytest.approx(272.0), stopped


def test_random_flights_are_never_wider_than_drawn():
    """Review round 7, property check: 400 random flights (tread ends that change from tread to tread, open or
    slanting walled sides, handrails part way and slanting). Read by hand at many points along the run, each tread
    a rectangle back to the next nosing, the widths measured are never more than the least drawn."""
    import random
    rnd = random.Random(7)
    for _ in range(400):
        n = rnd.randint(2, 5)
        ends = [(rnd.choice([0, rnd.uniform(-6, 6)]), rnd.choice([36, rnd.uniform(30, 42)])) for _ in range(n)]
        run = 10 * (n - 1)
        walls = {"left": rnd.choice(["open", (rnd.uniform(34, 44), rnd.uniform(34, 44))]),
                 "right": rnd.choice(["open", (rnd.uniform(-8, 2), rnd.uniform(-8, 2))])}
        rails = []
        for _ in range(rnd.randint(0, 3)):
            a0, s0 = rnd.uniform(-10, 46), rnd.uniform(-3, run)
            far = (rnd.uniform(s0 + 0.5, run + 3), a0 + rnd.uniform(-6, 6))
            rails.append((rnd.choice(["left", "right"]), (s0, a0), far))
        d = base()
        d["stairs"][0].update(
            nosings=[[[10 * j, ends[j][0], 7 * (j + 1)], [10 * j, ends[j][1], 7 * (j + 1)]] for j in range(n)],
            sides={k: v if v == "open" else [[-5, v[0]], [run + 5, v[1]]] for k, v in walls.items()},
            handrails=[{"side": k, "inner_edge": [list(p), list(q)]} for k, p, q in rails],
            overhead=[[[-20, -20, 200], [run + 20, -20, 200], [run + 20, 60, 200], [-20, 60, 200]]])
        m, _, more = stair(d)

        def side(k, s, with_rails):
            tread = ends[min(int(s // 10), n - 1)][0 if k == "right" else 1]
            got = [tread] if walls[k] == "open" else [walls[k][0] + (s + 5) / (run + 10) * (walls[k][1] - walls[k][0])]
            if with_rails:
                got += [tread] + [p[1] + (s - p[0]) / (q[0] - p[0]) * (q[1] - p[1])
                                  for r, p, q in rails if r == k and p[0] <= s <= q[0]]
            return min(got) if k == "left" else max(got)

        points = [rnd.uniform(0, run) for _ in range(200)] + [10 * j - 1e-7 for j in range(1, n)]
        for s in points:
            if "stair_clear_width" in m:
                assert m["stair_clear_width"] <= side("left", s, False) - side("right", s, False) + 1e-6
            if "stair_clear_width_at_handrail" in more:
                assert more["stair_clear_width_at_handrail"] <= side("left", s, True) - side("right", s, True) + 1e-6


def test_a_narrowing_wall():
    # the left wall runs from 36 at s = -5 to 30 at s = 40: at the top nosing (s = 30) it is at 36 - 6 x 35/45
    d = changed(("stairs", 0, "sides", "left"), [[-5, 36], [40, 30]])
    m, _, _ = stair(d)
    assert m["stair_clear_width"] == pytest.approx(36 - 6 * 35 / 45)


def test_a_wall_jutting_in_midway():
    d = changed(("stairs", 0, "sides", "left"), [[-5, 36], [14, 36], [15, 33], [16, 36], [40, 36]])
    m, _, _ = stair(d)
    assert m["stair_clear_width"] == 33.0


def test_an_open_side_is_bounded_by_the_tread_ends():
    d = changed(("stairs", 0, "sides", "right"), "open")
    d["stairs"][0]["nosings"] = [[[10 * j, 2, 7 * (j + 1)], [10 * j, 36, 7 * (j + 1)]] for j in range(4)]
    m, _, _ = stair(d)
    assert m["stair_clear_width"] == 34.0


@pytest.mark.parametrize("change, words, measure", [
    ({"nosings": [[[0, 0, 7], [0, 36, 7.1]], [[10, 0, 14], [10, 36, 14]]]}, "isn't level", "stair_riser_height"),
    ({"nosings": [[[0, 0, 7], [0, 36, 7]], [[10, 0, 7], [10, 36, 7]]]}, "riser 2 is 0", "stair_riser_height"),
    ({"nosings": [[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [12, 36, 14]]]}, "winder", "stair_tread_depth"),
    ({"nosings": [[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [10, 36, 14]], [[5, 0, 21], [5, 36, 21]]]},
     "forward", "stair_tread_depth"),
    ({"nosings": [[[0, 0, 7], [0, 36, 7]]]}, "at least 2", "stair_tread_depth"),
    ({"nosings": []}, "at least 1", "stair_riser_height"),
    ({"nosings": [[[0, 0, 7]]]}, "line of at least 2", "stair_riser_height"),
    ({"nosings": [[[0, 0, 7], [0, 0, 7]], [[10, 0, 14], [10, 36, 14]]]}, "its two ends", "stair_tread_depth"),
    ({"nosings": [[[0, 0, 7], [0, 36, 7], [0, 40, 7]]]}, "its two ends", "stair_riser_height"),
    ({"bottom_elevation": None}, "bottom elevation isn't given", "stair_riser_height"),
    ({"sides": None}, "sides", "stair_clear_width"),
    ({"sides": {"left": [[-5, 36], [20, 36]], "right": [[-5, 0], [40, 0]]}}, "left side doesn't run",
     "stair_clear_width"),
    ({"sides": {"left": [[-5, 36], [20, 36], [10, 36], [40, 36]], "right": [[-5, 0], [40, 0]]}},
     "left side doesn't run", "stair_clear_width"),
    ({"sides": {"left": [[-5, 0], [40, 0]], "right": [[-5, 36], [40, 36]]}}, "meet or cross", "stair_clear_width"),
    ({"handrails": None}, "handrails", "stair_clear_width_at_handrail"),
    ({"handrails": [{"side": "middle", "inner_edge": [[0, 4], [30, 4]]}]}, "not left or right",
     "stair_clear_width"),
    ({"handrails": ["rail"]}, "handrail #1 isn't a mapping", "stair_clear_width"),
    ({"handrails": [{"side": "left", "inner_edge": [[0, -4], [30, -4]]}]}, "a handrail meets or crosses",
     "stair_clear_width_at_handrail"),
])
def test_stair_data_problems_give_no_value(change, words, measure):
    d = base()
    d["stairs"][0].update(change)
    _, stopped, _ = stair(d)
    assert words in stopped[measure], stopped


def test_risers_are_measured_even_when_the_plan_cant_be():
    m, stopped, more = stair(changed(("stairs", 0, "nosings"), [[[0, 0, 7], [0, 36, 7]]]))
    assert m == {"stair_riser_height": 7.0, "stair_riser_variation": 0.0} and more["stair_risers"] == 1
    assert "stair_riser_height" not in stopped and "stair_tread_depth" in stopped


# --- guards ---------------------------------------------------------------------------------------------------------

def guard(d):
    p = one(d, "guard")
    return p["measures"], p["not_measured"]


def test_balusters_and_rails():
    # extent 0..20, height 100..136; bottom rail 102..104; top rail 134..136; balusters 1.5 wide at 4.5 and 9.5,
    # 14.5: gaps 4.5, 3.5, 3.5, 4.0 (between 104 and 134, 30 tall); under the bottom rail 2 tall: largest 4.5
    d = base()
    d["guards"][0]["extent"] = {"left": 0, "right": 20}
    d["guards"][0]["members"] = [{"left": 0, "right": 20, "bottom": 134, "top": 136},
                                 {"left": 0, "right": 20, "bottom": 102, "top": 104}] + \
        [{"left": u, "right": u + 1.5, "bottom": 104, "top": 134} for u in (4.5, 9.5, 14.5)]
    m, _ = guard(d)
    assert m == {"guard_height": 36.0, "guard_opening_sphere": 4.5}


def test_a_member_wholly_above_the_guard_never_reaches_its_top():
    """Review round 6: a rail drawn at 300..301 over a panel to 133 gave the guard its stated 36 in, not 33."""
    d = base()
    d["guards"][0]["members"] = [{"left": 0, "right": 10, "bottom": 100, "top": 133},
                                 {"left": 0, "right": 10, "bottom": 300, "top": 301}]
    m, stopped = guard(d)
    assert m == {} and "is 33.0 in high" in stopped["guard_height"]


def test_a_solid_panel_lets_nothing_through():
    d = base()
    d["guards"][0]["members"] = [{"left": 0, "right": 10, "bottom": 100, "top": 136}]
    assert guard(d)[0]["guard_opening_sphere"] == 0.0


def test_a_guard_whose_top_rail_runs_part_way():
    """Review round 3: one member reaching the top (a post, a short rail) gave the whole guard that height."""
    d = base()
    d["guards"][0]["members"] = [{"left": 0, "right": 5, "bottom": 134, "top": 136},
                                 {"left": 5, "right": 10, "bottom": 128, "top": 130}]
    m, stopped = guard(d)
    assert m == {} and "is 30.0 in high" in stopped["guard_height"]
    d["guards"][0]["members"] = [{"left": 0, "right": 10, "bottom": 128, "top": 130},
                                 {"left": 200, "right": 202, "bottom": 100, "top": 136}]   # a post past its end
    assert "is 30.0 in high" in guard(d)[1]["guard_height"]
    d["guards"][0]["members"] = [{"left": 0, "right": 5, "bottom": 134, "top": 136},
                                 {"left": 4, "right": 10, "bottom": 134, "top": 136}]     # two rails, overlapping
    assert guard(d)[0] == {"guard_height": 36.0, "guard_opening_sphere": 10.0}       # one opening 10 x 34


@pytest.mark.parametrize("members", [[{"left": 0, "right": 10, "bottom": 100, "top": 130}], []])
def test_a_guard_height_is_the_drawn_guards(members):
    """Review round 2: the height came from the stated top though no member reached it (drawn 30 in, read 36)."""
    d = base()
    d["guards"][0]["members"] = members
    m, stopped = guard(d)
    assert m == {} and "don't reach its stated top all along" in stopped["guard_height"]


def test_a_sliding_sash_outside_its_frame_gives_no_value():
    """Review round 2: a sash drawn wholly above the frame left the whole frame clear (12.5 sq ft)."""
    _, stopped, _ = opening_measures(sliding([{"left": 0, "right": 30, "bottom": 60, "top": 90}]))
    assert "reaches outside the frame" in stopped["opening_net_clear_area"]
    m, _, _ = opening_measures(sliding([{"left": 0, "right": 30.05, "bottom": 40, "top": 60.05}]))   # within 1/16
    assert m["opening_net_clear_height"] == 20.0


@pytest.mark.parametrize("key, value", [("sash_width", 2), ("sash_thickness", 0)])
def test_a_hinged_sash_that_doesnt_close_its_frame_gives_no_value(key, value):
    """Review round 2: a 2 in sash in a 30 in frame read as 27.9 in clear at 45 degrees (the rest is fixed)."""
    _, stopped, _ = opening_measures(changed(("openings", 0, "hinged", key), value))
    assert "doesn't close" in stopped["opening_net_clear_width"]


def test_a_tilted_nosing_is_read_at_its_worst_end():
    """Review round 2: a nosing's ends were averaged, so a riser 1/32 in taller at one end read as the mean."""
    d = flight([7, 7, 7, 7], [10, 10, 10])
    n = d["stairs"][0]["nosings"]
    n[1] = [[10.03125, 0, 14.03125], [9.96875, 36, 13.96875]]      # nosing 2 tilted 1/32 in each way
    m, _, more = stair(d)
    assert m["stair_riser_height"] == 7.03125                       # 14.03125 - 7
    assert m["stair_riser_variation"] == 0.0625                  # 7.03125 - 6.96875 (21 - 14.03125)
    assert m["stair_tread_depth"] == 9.96875 and more["stair_tread_variation"] == 0.0625
    n[1] = [[10, 0, 14], [10, 36, 13.9375]]                         # one end 1/16 in low: the riser above it
    m, _, _ = stair(d)
    assert m["stair_riser_height"] == 7.0625                        # 21 - 13.9375


def test_a_surface_point_below_its_fitted_plane_counts():
    """Review round 2: a ceiling point 0.05 in under the fitted plane (83.97 in) read as 84.02: area given."""
    _, stopped, more = room(ceilings([[0, 0, 84.05], [60, 0, 83.97], [120, 0, 84.05], [120, 120, 84.05],
                                      [0, 120, 84.05]]))
    assert more["least_ceiling_height"] <= 83.97 and "R312.3" in stopped["sleeping_room_floor_area"]


def test_a_makers_opening_within_the_frames_slack_is_cut_back_to_the_frame():
    """Review round 3: a maker's opening 1/20 in wider and lower than its frame read as is (20 in, sill 44)."""
    d = changed(("openings", 0, "operation"), "awning")
    d["openings"][0]["frame"] = {"left": 0, "right": 19.95, "bottom": 44.05, "top": 80}
    d["openings"][0]["stated_clear"] = {"width": 20, "height": 35.97, "bottom": 44}
    d["openings"][0]["ground_outside"] = 0.03                        # 43.97 below the maker's bottom, 44.02 the frame's
    m, stopped, _ = opening_measures(d)
    assert (m["opening_net_clear_width"], m["opening_sill_height"]) == (19.95, 44.05)
    assert m["opening_net_clear_height"] == pytest.approx(35.92)     # 44.05 .. 79.97
    assert "for grade-floor" in stopped["opening_at_grade"]


def test_the_nosing_line_stands_at_a_nosings_end_nearer_the_foot():
    """Review round 3: a nosing's run position was its ends' mean, so the line (and headroom) sat 1/32 in low."""
    # nosings at s 0, 10, 20 (z 7, 14, 21); the middle one's ends at s 10 and 10.0625; a ceiling at 80 to s 10
    d = flight([7, 7, 7], [10, 10])
    d["stairs"][0]["nosings"][1] = [[10, 0, 14], [10.0625, 36, 14]]
    d["stairs"][0]["overhead"] = [[[-5, -5, 80], [10, -5, 80], [10, 41, 80], [-5, 41, 80]],
                                  [[10, -5, 120], [40, -5, 120], [40, 41, 120], [10, 41, 120]]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == 66.0                               # 80 - 14 at s = 10, not 66.0218


def test_headroom_is_read_at_every_bend_of_the_nosing_line():
    """Review round 4: pieces cut at each nosing's middle hid the line's bend at its nearer end (82.5125, not 82.5).
    Nosings at z 10, 20, 21 (s 0, 10, 20), the middle one's ends at s 10 and 10.0625; the overhead rises 0.5 in per
    inch along the run from 97.5 at s = 0: the gap 87.5 - 0.5 s to s = 10 (82.5 at the bend), then rising."""
    d = base()
    d["stairs"][0]["bottom_elevation"] = 3
    d["stairs"][0]["nosings"] = [[[0, 0, 10], [0, 36, 10]], [[10, 0, 20], [10.0625, 36, 20]],
                                 [[20, 0, 21], [20, 36, 21]]]
    d["stairs"][0]["overhead"] = [[[-5, -5, 95], [40, -5, 117.5], [40, 41, 117.5], [-5, 41, 95]]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(82.5)


def test_headroom_covers_a_tread_wider_than_the_next():
    """Review round 6: the shape between neighbouring nosings cut the corner of a flared starter step (48 in, the
    rest 36), so a beam over its wide end (z 40, s 6..9.9) was never read: 28.33, not 40 - 13.93 = 26.07."""
    d = base()
    d["stairs"][0]["nosings"][0] = [[0, -6, 7], [0, 42, 7]]
    d["stairs"][0]["overhead"] = [[[-10, -10, 120], [40, -10, 120], [40, 50, 120], [-10, 50, 120]],
                                  [[6, 37, 40], [9.9, 37, 40], [9.9, 42, 40], [6, 42, 40]]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(40 - (7 + 0.99 * 7))


@pytest.mark.parametrize("x0, x36", [(29.9375, 30), (30, 29.9375)])
def test_headroom_covers_both_ends_of_an_askew_top_nosing(x0, x36):
    """Review round 7: the area checked ended at each nosing's middle along the run, so a top nosing drawn 1/16 in
    askew (allowed) left its far end out, and a header at 60 from x 29.99 on read 92 (the ceiling), not 60 - 28."""
    d = base()
    d["stairs"][0]["nosings"][3] = [[x0, 0, 28], [x36, 36, 28]]
    d["stairs"][0]["overhead"] = [[[-5, -5, 120], [29.99, -5, 120], [29.99, 41, 120], [-5, 41, 120]],
                                  [[29.99, -5, 60], [45, -5, 60], [45, 41, 60], [29.99, 41, 60]]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(32.0)


@pytest.mark.parametrize("first", [True, False])
def test_a_surface_too_large_to_measure_is_never_dropped(first, monkeypatch):
    """Review round 4: a 60 in plane reaching 1e200 in made NaN heights, and min() let the other surface win."""
    huge = [[-5, -5, 60], [1e200, -5, 60], [1e200, 1e200, 60], [-5, 1e200, 60]]
    normal = [[-5, -5, 200], [40, -5, 200], [40, 41, 200], [-5, 41, 200]]
    d = base()
    _, stopped, _ = stair(d)
    d["stairs"][0]["overhead"] = [huge, normal] if first else [normal, huge]
    assert "15,800 miles" in stair(d)[1]["stair_headroom"]                 # round 12: refused as read
    monkeypatch.setattr("model_measurement.interior.read.FAR", math.inf)   # and the check behind it still holds
    d["stairs"][0]["overhead"] = [huge, normal] if first else [normal, huge]
    _, stopped, _ = stair(d)
    assert "too large to measure" in stopped["stair_headroom"]
    _, stopped, _ = room(ceilings(*([huge, normal] if first else [normal, huge])))
    assert "too large to measure" in stopped["sleeping_room_floor_area"]


def test_a_surface_too_large_is_refused_where_it_is_read():
    from model_measurement.interior.geometry import Surface
    with pytest.raises(Stop, match="too large to measure"):
        Surface([(-5, -5, 60), (1e200, -5, 60), (1e200, 1e200, 60), (-5, 1e200, 60)], "the ceiling")


def test_a_gap_that_isnt_a_number_never_drops_out_of_the_least():
    from shapely.geometry import box
    from model_measurement.interior import geometry

    class Odd:                                     # a surface whose height somewhere isn't a number
        plan = box(0, 0, 10, 10)

        def z(self, x, y):
            return float("nan") if x > 5 else 100.0

    with pytest.raises(Stop, match="too large to measure"):
        geometry.least_gap([Odd()], [(box(0, 0, 10, 10), lambda x, y: 0.0)], "the ceiling", "room")


def test_a_stair_guard_reads_the_same_cautious_line():
    # risers 7, 9, 5 (nosings at z 7, 16, 21); the middle nosing's ends at s 10 and 10.0625; the guard's top
    # rises from 41 at s 0 to 55 at s 20: least above the line at the middle nosing's nearer end, 48 - 16
    d = stair_guard([[0, 36, 41], [20, 36, 55]])
    d["stairs"][0]["nosings"] = nosings([7, 9, 5], [10, 10])
    d["stairs"][0]["nosings"][1] = [[10, 0, 16], [10.0625, 36, 16]]
    d["stairs"][0]["sides"] = {"left": [[-5, 36], [30, 36]], "right": [[-5, 0], [30, 0]]}
    m, _ = guard(d)
    assert m["guard_height"] == pytest.approx(32.0)


def test_a_length_infinite_only_once_in_inches_is_not_a_length():
    """Review round 3: 1e308 ft is finite as written and infinite in inches: it came out as an infinite width."""
    d = base()
    d["units"] = "ft"
    d["doors"][0]["stops"] = {"hinge": 0, "latch": 1e308}
    assert "isn't a length" in door(d)[1]["door_clear_width"]


def test_an_integer_too_big_for_a_float_is_not_a_length():
    _, stopped = door(changed(("doors", 0, "head_stop_bottom"), 10 ** 400))
    assert "isn't a length" in stopped["door_clear_height"]


def test_an_l_shaped_opening():
    d = base()
    d["guards"][0]["members"].append({"left": 0, "right": 5, "bottom": 100, "top": 120})
    assert "isn't a rectangle" in guard(d)[1]["guard_opening_sphere"]


@pytest.mark.parametrize("change, words, measure", [
    ({"extent": None}, "extent", "guard_opening_sphere"),
    ({"extent": {"left": 5, "right": 5}}, "length", "guard_opening_sphere"),
    ({"members": None}, "members", "guard_opening_sphere"),
    ({"top": 100}, "height", "guard_height"),
    ({"stair": "s"}, "give one", "guard_height"),
    ({"walking_surface": None}, "give one", "guard_height"),
])
def test_guard_data_problems(change, words, measure):
    d = base()
    d["guards"][0].update(change)
    _, stopped = guard(d)
    assert words in stopped[measure], stopped


def stair_guard(top_line, stair="s"):
    d = base()
    d["guards"][0] = {"id": "g", "name": "Stair guard", "stair": stair, "top_line": top_line}
    return d


def test_a_stair_guard_measured_from_the_nosing_line():
    # nosings at s 0..30, z 7..28; top 34 above at the bottom, 36 at the top: least 34
    m, stopped = guard(stair_guard([[0, 36, 41], [30, 36, 64]]))
    assert m == {"guard_height": 34.0} and "4 3/8" in stopped["guard_opening_sphere"]


def test_a_stair_guard_with_a_dip():
    # top line kinked down to 7 + 0.7 x 15 + 30 = 47.5 at s = 15: 30 above the nosing line there
    m, _ = guard(stair_guard([[0, 36, 41], [15, 36, 47.5], [30, 36, 64]]))
    assert m["guard_height"] == 30.0


@pytest.mark.parametrize("top_line, stair, words", [
    ([[0, 36, 41], [20, 36, 60]], "s", "doesn't run"),
    ([[0, 36, 41], [30, 36, 64]], "elsewhere", "isn't one of the stairs"),
    ([[0, 36, 0], [30, 36, 0]], "s", "height"),
])
def test_stair_guard_problems(top_line, stair, words):
    _, stopped = guard(stair_guard(top_line, stair))
    assert words in stopped["guard_height"]


def test_a_guard_along_a_stair_that_couldnt_be_placed():
    d = stair_guard([[0, 36, 41], [30, 36, 64]])
    d["stairs"][0]["nosings"] = [[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [12, 36, 14]]]   # winders
    _, stopped = guard(d)
    assert "couldn't be measured" in stopped["guard_height"]


def test_a_guard_along_a_stair_not_read_or_shared():
    d = stair_guard([[0, 36, 41], [30, 36, 64]])
    del d["stairs"]
    assert "stairs weren't read" in guard(d)[1]["guard_height"]
    d = stair_guard([[0, 36, 41], [30, 36, 64]])
    d["stairs"].append(copy.deepcopy(d["stairs"][0]))
    assert "more than one with this id" in guard(d)[1]["guard_height"]


def test_a_stair_guard_far_off_to_the_side_gets_no_height():
    """Round 8 (decided by Ben): a guard drawn 500 in off to the side of its stair protects none of it. Before, its
    top above the nosing line was still read as the guard's height (34 in here): a false pass for R321."""
    m, stopped = guard(stair_guard([[0, 536, 41], [30, 536, 64]]))
    assert "guard_height" not in m
    assert "doesn't stand along a side" in stopped["guard_height"] and "500.0 in" in stopped["guard_height"]


@pytest.mark.parametrize("a, ok", [(36 + 1 / 16, True), (36 - 1 / 16, True), (36 + 1 / 8, False),
                                   (36 - 1 / 8, False), (0, True), (1 / 16, True), (-1 / 8, False), (18, False)])
def test_a_stair_guard_must_be_on_a_side_within_drawing_noise(a, ok):
    # the base stair's sides: left at a = 36, right at a = 0; 1/16 in either way is drawing noise, 1/8 in isn't
    m, stopped = guard(stair_guard([[0, a, 41], [30, a, 64]]))
    assert ("guard_height" in m) == ok, stopped
    if ok:
        assert m["guard_height"] == 34.0


def test_a_stair_guard_bending_away_from_its_side_midway():
    # on the left side (a = 36) at both ends, 3 in out at s = 15 (a point of the guard's own line)
    _, stopped = guard(stair_guard([[0, 36, 41], [15, 39, 52.5], [30, 36, 64]]))
    assert "3.0 in" in stopped["guard_height"]


def test_a_side_bending_away_from_a_straight_guard():
    # the left side juts out to a = 40 at s = 15 (a point of the side's line); the guard stays at a = 36: 4 in off
    d = stair_guard([[0, 36, 41], [30, 36, 64]])
    d["stairs"][0]["sides"]["left"] = [[-5, 36], [15, 40], [40, 36]]
    assert "4.0 in" in guard(d)[1]["guard_height"]


def test_a_stair_guard_along_an_open_side_or_none():
    # the left side given as open (the format: a side with a guard is the guard's inside face): the guard at the
    # tread ends (a = 36) is 36 in from the one side drawn (the right, a = 0)
    d = stair_guard([[0, 36, 41], [30, 36, 64]])
    d["stairs"][0]["sides"]["left"] = "open"
    assert "36.0 in" in guard(d)[1]["guard_height"]
    d["stairs"][0]["sides"]["right"] = "open"
    assert "stands on neither" in guard(d)[1]["guard_height"]
    d["stairs"][0]["sides"] = None
    assert "sides" in guard(d)[1]["guard_height"]


def test_random_stair_guards_only_on_a_side_and_never_taller_than_drawn():
    """Round 8, property check: 1,000 random stair guards (straight or bent top lines, near a side or not; slanting
    or bent sides, open or drawn). Whenever a height is given, the guard is within 1/16 in of a drawn side at every
    sampled point along the flight, and its height is never more than its top above the nosing line there."""
    import random
    rnd = random.Random(8)
    given = 0
    for _ in range(1000):
        n = rnd.randint(2, 5)
        run = 10 * (n - 1)
        sides = {}
        for k, a in (("left", 36), ("right", 0)):
            if rnd.random() < 0.2:
                sides[k] = "open"
            else:
                bend = rnd.choice([0, 0, rnd.uniform(-0.1, 0.1), rnd.uniform(-3, 3)])
                sides[k] = [[-5, a + rnd.choice([0, rnd.uniform(-0.1, 0.1)])], [run / 2, a + bend],
                            [run + 5, a + rnd.choice([0, rnd.uniform(-0.1, 0.1)])]]
        on = rnd.choice(["left", "right"])
        base_a = 36 if on == "left" else 0
        k = rnd.randint(2, 4)
        ss = [0] + sorted(rnd.uniform(0.5, run - 0.5) for _ in range(k - 2)) + [run]
        off = rnd.choice([0, 1 / 32, 1 / 16, 0.07, 1, 500])
        top = [[s, base_a + rnd.uniform(-off, off), 7 * (1 + s / 10) + rnd.uniform(30, 40)] for s in ss]
        d = stair_guard(top)
        d["stairs"][0]["nosings"] = nosings([7] * n, [10] * (n - 1))
        d["stairs"][0]["sides"] = sides
        d["stairs"][0]["overhead"] = [[[-20, -20, 400], [run + 20, -20, 400], [run + 20, 60, 400], [-20, 60, 400]]]
        m, _ = guard(d)
        if "guard_height" not in m:
            continue
        given += 1

        def interp(pts, s):
            for (s1, a1), (s2, a2) in zip(pts, pts[1:]):
                if s1 <= s <= s2:
                    return a1 + (s - s1) / (s2 - s1) * (a2 - a1)

        samples = [rnd.uniform(0, run) for _ in range(200)] + ss
        drawn = [v for v in sides.values() if v != "open"]
        for s in samples:
            ga = interp([(p[0], p[1]) for p in top], s)
            assert min(abs(ga - interp([tuple(q) for q in v], s)) for v in drawn) <= 1 / 16 + 1e-9
            nosing = 7 * (1 + min(s, run) / 10)
            assert m["guard_height"] <= interp([(p[0], p[2]) for p in top], s) - nosing + 1e-6
    assert given > 100                        # the check has teeth: many guards were measured


# --- the exit door --------------------------------------------------------------------------------------------------

def door(d):
    p = one(d, "egress_door")
    return p["measures"], p["not_measured"]


def test_a_right_hinged_door():
    # pin at 36, 1.75 (the leaf's corner); hinge stop at 36: face open at 36 - 1.75 = 34.25; latch stop 2: 32.25
    d = base()
    d["doors"][0].update(hinge_side="right", stops={"hinge": 36, "latch": 2}, hinge_pin=[36, 1.75],
                         leaf_closed=[[1, 0], [36, 1.75]])
    assert door(d)[0]["door_clear_width"] == 32.25
    d["doors"][0]["stops"]["hinge"] = 35.25                           # lapping the leaf by 3/4 in: the face rules
    assert door(d)[0]["door_clear_width"] == 32.25
    d["doors"][0].update(hinge_pin=[36, 0.25], leaf_closed=[[1, 0], [36, 0.25]])   # a 1/4 in leaf: the stop rules
    assert door(d)[0]["door_clear_width"] == 33.25                    # min(35.75, 35.25) - 2
    d["doors"][0]["stops"]["hinge"] = 33                              # 3 in in front of the leaf's edge: no stop
    assert "3.0 in behind" in door(d)[1]["door_clear_width"]


def test_a_pin_off_the_leafs_corner():
    # pin 0.25 beyond the leaf's swing face: the face turns 2.0 into the opening
    d = changed(("doors", 0, "hinge_pin"), [0, 2.0])
    assert door(d)[0]["door_clear_width"] == 32.0


def test_a_hinge_stop_deeper_than_the_open_leaf():
    # round 9: a hinge stop may lap the leaf by 3/4 in (the face still turns to 1.75: 34 - 1.75); 3 in is no stop
    d = changed(("doors", 0, "stops"), {"hinge": 0.75, "latch": 34})
    assert door(d)[0]["door_clear_width"] == 32.25
    d = changed(("doors", 0, "stops"), {"hinge": 3, "latch": 34})
    assert "3.0 in behind the hinge-side stop" in door(d)[1]["door_clear_width"]


@pytest.mark.parametrize("pin, width", [
    ([0, -500], None),               # far behind the leaf: before, the leaf "turned" clear out of the opening (34)
    ([-10, 1.75], None),             # back toward the hinge jamb, 10 in off the leaf: before, 34
    ([0, 1.75 - 1 / 8], None),       # 1/8 in behind the swing face: more than drawing noise
    ([-1 / 8, 1.75], None),
    ([0, 1.75 - 1 / 16], 32.3125),   # 1/16 in behind: drawing noise; the face turns to 1.6875: 34 - 1.6875
    ([-1 / 16, 1.75], 32.3125),
    ([0, 500], None),                # far beyond the face: the turned leaf closes the opening (not more than zero)
    ([5, 1.75], 27.25),              # toward the latch: only narrower (34 - 6.75)
])
def test_a_hinge_pin_must_hang_the_leaf(pin, width):
    """Round 8: the leaf is turned about its pin, so a pin drawn away from the leaf (behind it, or back toward the
    hinge jamb) turned it out of the opening and gave the full stop-to-stop width: too favourable."""
    m, stopped = door(changed(("doors", 0, "hinge_pin"), pin))
    assert m.get("door_clear_width") == width, stopped
    if width is None and pin[1] != 500:
        assert "isn't hung on that pin" in stopped["door_clear_width"]


def test_a_right_hinged_pin_back_toward_its_jamb():
    d = base()
    d["doors"][0].update(hinge_side="right", stops={"hinge": 36, "latch": 2}, hinge_pin=[46, 1.75],
                         leaf_closed=[[1, 0], [36, 1.75]])
    assert "isn't hung" in door(d)[1]["door_clear_width"]        # before: min(44.25, 36) - 2 = 34, not 32.25


@pytest.mark.parametrize("pin, leaf, hand, words", [
    ([0, 0], [[0, 0], [35, 0]], "left", "no thickness"),               # drawn flat: before, 34 (not 32.25)
    ([-40, 1.75], [[-40, 0], [-5, 1.75]], "left", "39.0 in short"),    # leaf and pin in the wall: before, 34
    ([80, 1.75], [[45, 0], [80, 1.75]], "right", "45.0 in short"),     # the same, right hand: before, 34
    ([-40, 1.75], [[-40, 0], [34, 1.75]], "left", "40.0 in behind"),   # round 9: reaching the latch, run into the wall
    ([74, 1.75], [[0, 0], [74, 1.75]], "right", "40.0 in behind"),     # the same, right hand: before, 34
    ([-0.75, 1.75], [[-0.75, 0], [34, 1.75]], "left", 33.0),           # a stop's 3/4 in lap: 34 - (-0.75 + 1.75)
    ([-0.8125, 1.75], [[-0.8125, 0], [34, 1.75]], "left", "0.8125 in behind"),
    ([0, 1.75], [[0, 0], [34 - 1 / 16, 1.75]], "left", None),          # 1/16 in short: drawing noise
    ([0, 1.75], [[0, 0], [34 - 1 / 8, 1.75]], "left", "0.125 in short"),
    ([34, 1.75], [[1 / 8, 0], [34, 1.75]], "right", "0.125 in short"),
])
def test_a_door_leaf_must_close_its_own_opening(pin, leaf, hand, words):
    """Round 8: nothing checked the leaf itself. A flat leaf lost its thickness, and a leaf drawn (with its pin) in
    the wall turned open clear of the opening: both read the full stop-to-stop width."""
    d = base()
    stops = {"hinge": 0, "latch": 34} if hand == "left" else {"hinge": 34, "latch": 0}
    d["doors"][0].update(hinge_side=hand, stops=stops, hinge_pin=pin, leaf_closed=leaf)
    m, stopped = door(d)
    if words is None or isinstance(words, float):
        assert m["door_clear_width"] == (words or 32.25)         # the base: 34 - 1.75
    else:
        assert "door_clear_width" not in m and words in stopped["door_clear_width"], stopped


def test_headroom_covers_the_near_end_of_an_askew_wider_top_nosing():
    """Round 8: the top nosing had no strip of its own, so where it is wider than the one below (a landing edge,
    open side) and askew, its nearer end lay outside the area: a beam over it read 92 (the ceiling), not 40 - 28."""
    d = base()
    d["stairs"][0]["sides"]["left"] = "open"
    d["stairs"][0]["nosings"][3] = [[30.03, 0, 28], [29.97, 48, 28]]
    d["stairs"][0]["overhead"] = [[[-5, -5, 120], [45, -5, 120], [45, 60, 120], [-5, 60, 120]],
                                  [[29.9, 47.95, 40], [29.98, 47.95, 40], [29.98, 60, 40], [29.9, 60, 40]]]
    m, _, _ = stair(d)
    assert m["stair_headroom"] == pytest.approx(12.0)


def test_random_leaves_only_measured_where_they_close_the_opening():
    """Round 8, property check: 2,000 random leaves and pins moved together (flat or not, in the wall, part way,
    across the opening), either hand. Whenever a width is given, the leaf is thicker than nothing, reaches the
    latch-side stop within 1/16 in, and the width is never more than that leaf hung at its corner gives."""
    import random
    rnd = random.Random(808)
    given = 0
    for _ in range(2000):
        side = rnd.choice(["left", "right"])
        thick = rnd.choice([0, 1 / 32, rnd.uniform(1, 2.5)])
        shift = rnd.choice([0, 0, rnd.uniform(-1 / 8, 1 / 8), rnd.uniform(-50, 50)])
        width_leaf = rnd.choice([34 + rnd.uniform(-1 / 8, 1 / 8), rnd.uniform(5, 40)])
        if side == "left":
            edge, hinge, latch = shift, 0, 34
            far_edge = edge + width_leaf
        else:
            edge, hinge, latch = 34 + shift, 34, 0
            far_edge = edge - width_leaf
        d = base()
        d["doors"][0].update(hinge_side=side, stops={"hinge": hinge, "latch": latch}, hinge_pin=[edge, thick],
                             leaf_closed=[[edge, 0], [far_edge, thick]])
        m, _ = door(d)
        if "door_clear_width" not in m:
            continue
        given += 1
        assert thick > 0
        assert (latch - far_edge if side == "left" else far_edge - latch) <= 1 / 16 + 1e-9
        hand = latch - max(edge + thick, hinge) if side == "left" else min(edge - thick, hinge) - latch
        assert m["door_clear_width"] <= hand + 1e-6               # tidy rounds to a millionth
    assert given > 200


def test_random_hinge_pins_never_give_more_than_the_leaf_hung_at_its_corner():
    """Round 8, property check: 2,000 random pins and leaves, either hand. Whenever a width is given, it is never
    more than the leaf hung at its own corner gives, by more than the 1/16 in of drawing noise."""
    import random
    rnd = random.Random(88)
    given = 0
    for _ in range(2000):
        side = rnd.choice(["left", "right"])
        thick = rnd.uniform(1, 2.5)
        edge = rnd.uniform(-2, 2) if side == "left" else rnd.uniform(34, 38)
        width_leaf = rnd.uniform(30, 38)
        far_edge = edge + width_leaf if side == "left" else edge - width_leaf
        hinge, latch = (rnd.uniform(-3, 3), rnd.uniform(32, 38)) if side == "left" else \
            (rnd.uniform(33, 39), rnd.uniform(-2, 4))
        spread = rnd.choice([0.03, 0.0625, 0.2, 5, 500])
        pin = [edge + rnd.uniform(-spread, spread), thick + rnd.uniform(-spread, spread)]
        d = base()
        d["doors"][0].update(hinge_side=side, stops={"hinge": hinge, "latch": latch}, hinge_pin=pin,
                             leaf_closed=[[edge, 0], [far_edge, thick]])
        m, _ = door(d)
        if "door_clear_width" not in m:
            continue
        given += 1
        hand = latch - max(edge + thick, hinge) if side == "left" else min(edge - thick, hinge) - latch
        assert m["door_clear_width"] <= hand + 1 / 16 + 1e-9
    assert given > 200


@pytest.mark.parametrize("path, value, words, measure", [
    (("doors", 0, "operation"), "pocket", "this door is pocket", "door_clear_width"),
    (("doors", 0, "hinge_side"), None, "hinge side isn't given", "door_clear_width"),
    (("doors", 0, "stops"), {"hinge": 34, "latch": 0}, "far side", "door_clear_width"),
    (("doors", 0, "stops"), None, "stops", "door_clear_width"),
    (("doors", 0, "hinge_pin"), [0], "list of 2 numbers", "door_clear_width"),
    (("doors", 0, "leaf_closed"), [[0, 0], [1, 1], [2, 2]], "two opposite corners", "door_clear_width"),
    (("doors", 0, "stops"), {"hinge": 0, "latch": 1}, "clear width", "door_clear_width"),
    (("doors", 0, "head_stop_bottom"), 0, "clear height", "door_clear_height"),
    (("doors", 0, "threshold_top"), "low", "isn't a length", "door_clear_height"),
])
def test_door_data_problems(path, value, words, measure):
    _, stopped = door(changed(path, value))
    assert words in stopped[measure], stopped


# the maker's stated clear opening (decision 2): the base door is drawn 32.25 wide (latch 34 - leaf face 1.75)
# and 80 high (80 - 0)
SRC = "maker's catalogue, p. 4"


def stated_door(width=32.25, height=80, **change):
    d = base()
    d["doors"][0]["stated_clear"] = {"width": width, "height": height, "source": SRC}
    d["doors"][0].update(change)
    return d


def door_from(d):
    p = one(d, "egress_door")
    return p["measures"], p["not_measured"], p["from"]


def test_drawn_alone_says_so():
    m, _, came = door_from(base())
    assert (m["door_clear_width"], m["door_clear_height"]) == (32.25, 80.0)
    assert {k: v["used"] for k, v in came.items()} == {"door_clear_width": "drawn", "door_clear_height": "drawn"}
    assert "no maker's clear opening" in came["door_clear_width"]["why"]


def test_the_makers_smaller_width_counts():
    m, _, came = door_from(stated_door(width=31.5, height=81))     # width 31.5 < 32.25; height 80 < 81
    assert (m["door_clear_width"], m["door_clear_height"]) == (31.5, 80.0)
    assert came["door_clear_width"] == {"used": "stated", "stated": 31.5, "drawn": 32.25, "source": SRC,
                                        "why": "the maker's stated clear width is smaller than the drawn one: the "
                                               "less favourable counts"}
    assert came["door_clear_height"]["used"] == "drawn" and came["door_clear_height"]["stated"] == 81.0


def test_the_drawn_smaller_height_counts_and_the_makers_smaller_height_too():
    m, _, came = door_from(stated_door(width=33, height=79))       # width 32.25 < 33; height 79 < 80
    assert (m["door_clear_width"], m["door_clear_height"]) == (32.25, 79.0)
    assert came["door_clear_width"]["used"] == "drawn" and came["door_clear_height"]["used"] == "stated"


def test_drawn_and_stated_the_same():
    m, _, came = door_from(stated_door())
    assert (m["door_clear_width"], m["door_clear_height"]) == (32.25, 80.0)
    assert {v["used"] for v in came.values()} == {"both"}


def test_the_makers_opening_alone():
    d = stated_door(width=34, height=81)
    for k in ("stops", "hinge_pin", "leaf_closed", "threshold_top", "head_stop_bottom"):
        del d["doors"][0][k]
    m, stopped, came = door_from(d)
    assert (m["door_clear_width"], m["door_clear_height"]) == (34.0, 81.0)
    assert came["door_clear_width"] == {"used": "stated", "stated": 34.0, "source": SRC,
                                        "why": "the maker's stated clear width; none drawn"}
    assert "door_clear_width" not in stopped


def test_the_makers_size_alone_on_one_measure_only():
    d = stated_door(width=34, height=81)
    del d["doors"][0]["threshold_top"], d["doors"][0]["head_stop_bottom"]     # the height not drawn: stated
    m, _, came = door_from(d)
    assert (m["door_clear_width"], m["door_clear_height"]) == (32.25, 81.0)
    assert came["door_clear_width"]["used"] == "drawn" and came["door_clear_height"]["used"] == "stated"


@pytest.mark.parametrize("key, measure", [("stops", "door_clear_width"), ("hinge_pin", "door_clear_width"),
                                          ("leaf_closed", "door_clear_width"), ("threshold_top", "door_clear_height"),
                                          ("head_stop_bottom", "door_clear_height")])
def test_a_door_drawn_in_part_never_falls_back_to_the_makers_size(key, measure):
    """Drawn but not measurable (one part of the drawing missing): the maker's size alone could be more than the
    door as drawn, so no value, never the stated one."""
    d = stated_door(width=40, height=90)
    del d["doors"][0][key]
    m, stopped, came = door_from(d)
    assert measure not in m and measure not in came
    assert "is drawn but can't be measured from the drawing" in stopped[measure]


def test_a_drawn_door_that_doesnt_measure_never_takes_the_makers_size():
    d = stated_door(width=40, height=90, stops={"hinge": 34, "latch": 0})       # stops the wrong way round
    m, stopped, _ = door_from(d)
    assert "door_clear_width" not in m and "far side" in stopped["door_clear_width"]
    assert m["door_clear_height"] == 80.0


def test_a_sliding_door_has_no_clear_width_even_stated():
    d = stated_door(width=34, height=81, operation="sliding")
    for k in ("stops", "hinge_pin", "leaf_closed"):
        del d["doors"][0][k]
    m, stopped, came = door_from(d)
    assert "door_clear_width" not in m and "this door is sliding" in stopped["door_clear_width"]
    assert m["door_clear_height"] == 80.0 and came["door_clear_height"]["used"] == "drawn"


@pytest.mark.parametrize("stated, words", [
    ("34 x 80", "isn't a width, a height and a source"),
    ({"width": 34, "height": 80}, "doesn't say where it comes from"),
    ({"width": 34, "height": 80, "source": "  "}, "doesn't say where it comes from"),
    ({"width": 34, "height": 80, "source": 4}, "doesn't say where it comes from"),
    ({"width": 34, "height": 80, "source": SRC, "bottom": 0}, "(also bottom)"),
    ({"widht": 34, "height": 80, "source": SRC}, "(also widht)"),
    ({"height": 80, "source": SRC}, "the maker's stated clear width isn't given"),
    ({"width": 34, "source": SRC}, "the maker's stated clear height isn't given"),
    ({"width": "wide", "height": 80, "source": SRC}, "the maker's stated clear width isn't a length"),
    ({"width": True, "height": 80, "source": SRC}, "the maker's stated clear width isn't a length"),
    ({"width": -34, "height": 80, "source": SRC}, "a size can't be less than zero"),
    ({"width": 34, "height": 0, "source": SRC}, "the maker's stated clear height is 0.0 in: not more than zero"),
])
def test_a_malformed_makers_size_gives_neither_measure(stated, words):
    """Refused, never defaulted and never dropped: dropping it would leave the drawn size, which may be larger."""
    d = base()
    d["doors"][0]["stated_clear"] = stated
    m, stopped, came = door_from(d)
    assert "door_clear_width" not in m and "door_clear_height" not in m and came == {}
    assert words in stopped["door_clear_width"] and words in stopped["door_clear_height"], stopped
    assert m["door_side_hinged"] is True


def test_the_makers_size_in_the_descriptions_units():
    d = stated_door()
    d["units"] = "mm"
    for door_ in d["doors"]:
        door_["stops"] = {k: v * 25.4 for k, v in door_["stops"].items()}
        door_["hinge_pin"] = [v * 25.4 for v in door_["hinge_pin"]]
        door_["leaf_closed"] = [[v * 25.4 for v in c] for c in door_["leaf_closed"]]
        door_["threshold_top"], door_["head_stop_bottom"] = 0, 80 * 25.4
        door_["stated_clear"].update(width=800, height=2000)          # 31.496 in, 78.740 in
    m, _, came = door_from(d)
    assert m["door_clear_width"] == pytest.approx(800 / 25.4) and came["door_clear_width"]["used"] == "stated"
    assert m["door_clear_height"] == pytest.approx(2000 / 25.4) and came["door_clear_height"]["used"] == "stated"


@pytest.mark.parametrize("seed", range(5))
def test_random_doors_are_never_more_than_drawn_or_stated(seed):
    import random
    rng = random.Random(seed)
    for _ in range(100):
        sw, sh = rng.uniform(28, 36), rng.uniform(76, 84)
        m, _, came = door_from(stated_door(width=sw, height=sh))
        assert m["door_clear_width"] <= min(32.25, sw) + 1e-6 and m["door_clear_height"] <= min(80, sh) + 1e-6
        assert m["door_clear_width"] == pytest.approx(min(32.25, sw), abs=1e-6)
        assert m["door_clear_height"] == pytest.approx(min(80, sh), abs=1e-6)


# --- the description ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("units, scale", [("in", 1), ("ft", 1 / 12), ("mm", 25.4), ("m", 0.0254)])
def test_units(units, scale):
    """The base case, every length written in another unit: the same inches."""
    def scaled(x):
        if isinstance(x, bool) or isinstance(x, str):
            return x
        if isinstance(x, (int, float)):
            return x * scale
        if isinstance(x, list):
            return [scaled(v) for v in x]
        if isinstance(x, dict):
            return {k: v if k in ("open_angle",) else scaled(v) for k, v in x.items()}
        return x

    d = base()
    for key in ("rooms", "openings", "stairs", "guards", "doors"):
        d[key] = scaled(d[key])
    d["units"] = units
    got, want = measure(d)["parts"], measure(base())["parts"]
    for kind in want:
        for g, w in zip(got[kind], want[kind]):
            assert g["measures"] == pytest.approx(w["measures"], abs=1e-6), kind
            assert set(g["not_measured"]) == set(w["not_measured"]), kind


@pytest.mark.parametrize("desc, words", [
    ([], "isn't a set of named entries"),
    ({"format": "gordium.site/1"}, "('gordium.site/1', not gordium.interior/1)"),
    ({"format": "gordium.interior/1", "units": "cubits"}, "gives its sizes in 'cubits', not in inches"),
    ({"format": "gordium.interior/1"}, "gives its sizes in no unit named, not in inches"),
])
def test_a_description_that_cant_be_read_reads_nothing(desc, words):
    got = measure(desc)
    assert all(v is None for v in got["parts"].values()) and words in got["problems"][0]


@pytest.mark.parametrize("key, kind", [("rooms", "sleeping_room"), ("openings", "emergency_escape_opening"),
                                       ("stairs", "stair"), ("doors", "egress_door"), ("guards", "guard")])
def test_a_list_not_given_is_not_read(key, kind):
    d = base()
    del d[key]
    got = measure(d)
    assert got["parts"][kind] is None and any(f"the {key} weren't read" in p for p in got["problems"])
    d[key] = "lots"
    got = measure(d)
    assert got["parts"][kind] is None and any("aren't a list" in p for p in got["problems"])
    d[key] = [3]
    assert measure(d)["parts"][kind] is None


@pytest.mark.parametrize("key, flag, kind", [("rooms", "sleeping", "sleeping_room"),
                                             ("openings", "escape", "emergency_escape_opening"),
                                             ("doors", "exit", "egress_door")])
def test_a_flag_not_given_reads_none_of_that_kind(key, flag, kind):
    d = base()
    del d[key][0][flag]
    got = measure(d)
    assert got["parts"][kind] is None and any(p.endswith("(yes or no)") for p in got["problems"])
    from model_measurement.interior import asked_field
    assert [asked_field(p) for p in got["problems"]] == [f"{key}[].{flag}"]           # the field, as data


def test_rooms_not_read_still_measures_the_openings_but_not_their_sills():
    d = base()
    del d["rooms"]
    p = one(d, "emergency_escape_opening")
    assert "opening_net_clear_area" in p["measures"] and "rooms weren't read" in p["not_measured"]["opening_sill_height"]


def test_an_unknown_space_is_a_sleeping_room_that_may_not_be_one_and_the_drawn_rooms_are_still_measured():
    d = base()
    d["unknown_spaces"] = [{"id": "a1", "name": "Enclosed area on L1 (331.4 sq ft)"}]
    got = measure(d)
    bedroom, space = got["parts"]["sleeping_room"]
    assert bedroom["id"] == "b" and bedroom["measures"]["sleeping_room_floor_area"] == 100.0 and "maybe" not in bedroom
    assert space["id"] == "a1" and space["name"] == "Enclosed area on L1 (331.4 sq ft)"
    assert space["maybe"] == STOPS["unknown_space"] and space["measures"] == {}
    assert set(space["not_measured"].values()) == {STOPS["unknown_space"]} and space["not_measured"]
    assert got["problems"] == []
    # none given is none: the rooms are every room, as before
    assert [p["id"] for p in measure(base())["parts"]["sleeping_room"]] == ["b"]


@pytest.mark.parametrize("spaces", ["a1", [1], [{"id": ""}], [{"id": 3}]])
def test_unknown_spaces_that_cant_be_read_leave_every_room_not_read(spaces):
    d = base()
    d["unknown_spaces"] = spaces
    got = measure(d)
    assert got["parts"]["sleeping_room"] is None and got["problems"]


@pytest.mark.parametrize("kind", ["basement", "habitable_attic", "sleeping_loft"])
def test_a_space_whose_use_isnt_known_refuses_no_basements_attics_or_lofts(kind):
    d = base()
    d["has_none"] = [{"kind": kind, "source": "A-1"}]
    assert kind in measure(d)["has_none"]
    d["unknown_spaces"] = [{"id": "a1"}]
    got = measure(d)
    assert kind not in got["has_none"] and any("whose use isn't known" in p for p in got["problems"])
    # a claim that isn't about a space still stands
    d["has_none"] = [{"kind": "ramp", "source": "A-1"}]
    assert "ramp" in measure(d)["has_none"]


def test_a_part_with_no_id_is_passed_on_for_the_checker_to_name():
    d = base()
    del d["stairs"][0]["id"]
    assert one(d, "stair")["id"] is None


def _set(path, value):
    return lambda: changed(path, value)


def _with(builder, *steps):
    """builder() then each step(d) in turn."""
    def make():
        d = builder()
        for step in steps:
            step(d)
        return d
    return make


def _stair(**change):
    return _with(base, lambda d: d["stairs"][0].update(change))


def _guard(**change):
    return _with(base, lambda d: d["guards"][0].update(change))


def _awning(d):
    d["openings"][0]["operation"] = "awning"


# one description per reason: measuring it must make that reason happen
STOP_CASES = {
    "not_a_description": lambda: [],
    "wrong_format": lambda: {"format": "x"},
    "units": lambda: {"format": "gordium.interior/1", "units": "cubits"},
    "not_read": _set(("doors",), _DELETE),
    "not_a_list": _set(("doors",), "front"),
    "not_a_mapping": _set(("doors",), [1]),
    "flag_missing": _set(("doors", 0, "exit"), _DELETE),
    "flag_not_yes_no": _set(("doors", 0, "exit"), "yes"),
    "unknown_spaces_entry": _set(("unknown_spaces",), [{"name": "no id"}]),
    "unknown_space": _set(("unknown_spaces",), [{"id": "a1", "name": "Area on L1"}]),
    "has_none_unknown_space": _with(base, lambda d: d.update(has_none=[{"kind": "habitable_attic", "source": "A-1"}],
                                                             unknown_spaces=[{"id": "a1"}])),
    "missing": _set(("doors", 0, "threshold_top"), _DELETE),
    "not_a_length": _set(("doors", 0, "threshold_top"), "low"),
    "too_far": _set(("doors", 0, "threshold_top"), 1e10),
    "not_measured_yet": _with(base),
    "operation_undecided": _set(("doors", 0, "operation"), "other"),
    "not_a_door": _with(base),                       # a casement: a window
    "has_none_not_a_list": _set(("has_none",), "ramps"),
    "has_none_entry": _set(("has_none",), [1]),
    "has_none_listed": _set(("has_none",), [{"kind": "stair", "source": "A-2"}]),
    "has_none_below_ground": _with(base, lambda d: d.update(has_none=[{"kind": "basement", "source": "A-1"}]),
                                   lambda d: d["openings"][0].update(ground_outside=12)),
    "has_none_room_within": _with(base, lambda d: d.update(has_none=[{"kind": "sleeping_loft", "source": "A-3"}]),
                                  lambda d: d["rooms"].append(_loft(50))),
    "has_none_sleeping_room": _set(("has_none",), [{"kind": "sleeping_room", "source": "A-2"}]),
    "has_none_kind": _set(("has_none",), [{"kind": "elevator", "source": "A-2"}]),
    "has_none_no_source": _set(("has_none",), [{"kind": "ramp", "source": " "}]),
    "has_none_reading": _set(("has_none",), [{"kind": "ramp", "source": "A-2", "reading": "yes"}]),
    "has_none_keys": _set(("has_none",), [{"kind": "ramp", "source": "A-2", "reding": True}]),
    "has_none_twice": _set(("has_none",), [{"kind": "ramp", "source": "A-2"}, {"kind": "ramp", "source": "A-4"}]),
    "has_none_contradicted": _with(base, lambda d: d.update(has_none=[{"kind": "ramp", "source": "A-2"}],
                                                            ramps=[{"id": "r1"}])),
    "in_more_not_rules": _with(base, lambda d: d["openings"][0].update(
        area_well={"floor_elevation": 10, "width": 36, "projection": 36})),
    "not_finite": _with(base, lambda d: d["doors"][0].update(threshold_top=-1.7e308, head_stop_bottom=1.7e308)),
    "not_a_point": _set(("doors", 0, "hinge_pin"), [0]),
    "negative": _set(("openings", 0, "hinged", "sash_thickness"), -1),
    "clear_outside_frame": _with(base, _awning, lambda d: d["openings"][0].update(
        stated_clear={"width": 31, "height": 20, "bottom": 30})),
    "not_an_outline": _set(("rooms", 0, "floor"), [[0, 0], [1, 1]]),
    "not_a_polyline": _set(("stairs", 0, "nosings"), [[[0, 0, 7]]]),
    "not_a_rectangle_given": _set(("openings", 0, "frame"), [1]),
    "choice": _set(("openings", 0, "operation"), "rolling"),
    "two_ceilings": _with(base, lambda d: d["rooms"][0].update(ceilings=[[[0, 0, 96], [120, 0, 96], [0, 120, 96]]])),
    "no_ceiling": _set(("rooms", 0, "ceiling_height"), _DELETE),
    "low_ceiling": _set(("rooms", 0, "ceiling_height"), 80),
    "surface_vertical": _stair(overhead=[[[0, 0, 96], [30, 0, 96], [30, 0, 50]]]),
    "surface_out_of_range": _stair(overhead=[[[-5, -5, 60], [1e200, -5, 60], [1e200, 1e200, 60], [-5, 1e200, 60]]]),
    "surface_not_flat": _stair(overhead=[[[-5, -5, 120], [40, -5, 120], [40, 41, 130], [-5, 41, 120]]]),
    "shapes_failed": _stair(),          # made to fail by STOP_SETUP
    "not_covered": _stair(overhead=[[[-5, -5, 120], [10, -5, 120], [10, 41, 120], [-5, 41, 120]]]),
    "nothing_overhead": _stair(overhead=[]),
    "room_unknown": _set(("openings", 0, "room"), "nowhere"),
    "room_twice": _with(base, lambda d: d["rooms"].append(copy.deepcopy(d["rooms"][0]))),
    "operation_needs_clear": _with(base, _awning),
    "no_frame": _set(("openings", 0, "frame"), _DELETE),
    "hinge_angle": _set(("openings", 0, "hinged", "open_angle"), 200),
    "no_sashes": _set(("openings", 0, "operation"), "double_hung"),
    "clear_in_pieces": lambda: sliding([{"left": 0, "right": 30, "bottom": 35, "top": 45}]),
    "clear_not_rectangle": lambda: sliding([{"left": 15, "right": 30, "bottom": 40, "top": 60}]),
    "clear_differs": _with(base, lambda d: d["openings"][0].update(stated_clear={"width": 30, "height": 40,
                                                                               "bottom": 20})),
    "no_clear_opening": _set(("openings", 0, "operation"), "fixed"),
    "sill_below_floor": _set(("rooms", 0, "floor_elevation"), 30),
    "no_ground": _set(("openings", 0, "ground_outside"), _DELETE),
    "ground_mixed": _set(("openings", 0, "ground_outside"), [0, -30]),
    "readings_differ": _with(base, lambda d: d["openings"][0].update(
        area_well={"floor_elevation": 10, "width": 36, "projection": 36}, ground_outside=80)),
    "nosings_out_of_range": _stair(nosings=[[[10 * j, -9e307, 7 * (j + 1)], [10 * j, 9e307, 7 * (j + 1)]]
                                           for j in range(3)]),
    "spiral_not_said": base,
    "spiral_not_straight": _stair(spiral=False, nosings=[[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [12, 36, 14]]]),
    "spiral_but_straight": _stair(spiral=True),
    "spiral_not_shown": _stair(spiral=True, nosings=[[[0, 0, 7], [0, 36, 7]]]),
    "too_few_nosings": _stair(nosings=[[[0, 0, 7], [0, 36, 7]]]),
    "nosing_not_level": _stair(nosings=[[[0, 0, 7], [0, 36, 8]]]),
    "not_bottom_to_top": _stair(nosings=[[[0, 0, -7], [0, 36, -7]]]),
    "winders": _stair(nosings=[[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [12, 36, 14]]]),
    "nosings_not_forward": _stair(nosings=[[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [10, 36, 14]],
                                           [[5, 0, 21], [5, 36, 21]]]),
    "side_not_along": _stair(sides={"left": [[-5, 36], [20, 36]], "right": [[-5, 0], [40, 0]]}),
    "sides_cross": _stair(sides={"left": [[-5, 0], [40, 0]], "right": [[-5, 36], [40, 36]]}),
    "treads_cross": _stair(sides={"left": [[-5, 36], [40, 36]], "right": "open"},
                           nosings=[[[0, 0, 7], [0, 34.6, 7]], [[10, 35, 14], [10, 40, 14]],
                                    [[20, 0, 21], [20, 36, 21]], [[30, 0, 28], [30, 36, 28]]]),
    "side_off_treads": _stair(sides={"left": [[-5, 40], [40, 40]], "right": [[-5, 0], [40, 0]]}),
    "leaf_behind_hinge_stop": _with(base, lambda d: d["doors"][0].update(hinge_pin=[-40, 1.75],
                                                                         leaf_closed=[[-40, 0], [34, 1.75]])),
    "handrails_cross": _stair(handrails=[{"side": "left", "inner_edge": [[0, -2], [30, -2]]}]),
    "handrail_side": _stair(handrails=[{"side": "up", "inner_edge": [[0, 4], [30, 4]]}]),
    "handrail_part_way": _stair(handrails=[{"side": "left", "inner_edge": [[10, 32], [20, 32]]}]),
    "guard_kind": _guard(stair="s"),
    "guard_top_not_drawn": _guard(members=[]),
    "sash_outside_frame": lambda: sliding([{"left": 0, "right": 30, "bottom": 60, "top": 90}]),
    "sash_smaller_than_frame": _set(("openings", 0, "hinged", "sash_width"), 2),
    "guard_opening_shape": _guard(members=[{"left": 0, "right": 10, "bottom": 134, "top": 136},
                                           {"left": 0, "right": 5, "bottom": 100, "top": 120}]),
    "stair_unknown": lambda: stair_guard([[0, 36, 41], [30, 36, 64]], "elsewhere"),
    "stair_unread": _with(lambda: stair_guard([[0, 36, 41], [30, 36, 64]]),
                          lambda d: d["stairs"][0].update(nosings=[[[0, 0, 7], [0, 36, 7]]])),
    "stair_guard_openings": lambda: stair_guard([[0, 36, 41], [30, 36, 64]]),
    "guard_off_side": lambda: stair_guard([[0, 536, 41], [30, 536, 64]]),
    "guard_no_side": _with(lambda: stair_guard([[0, 36, 41], [30, 36, 64]]),
                           lambda d: d["stairs"][0].update(sides={"left": "open", "right": "open"})),
    "pin_off_leaf": _set(("doors", 0, "hinge_pin"), [0, -500]),
    "leaf_no_thickness": _with(base, lambda d: d["doors"][0].update(hinge_pin=[0, 0], leaf_closed=[[0, 0], [35, 0]])),
    "leaf_not_closing": _with(base, lambda d: d["doors"][0].update(hinge_pin=[-40, 1.75],
                                                                   leaf_closed=[[-40, 0], [-5, 1.75]])),
    "not_side_hinged": _set(("doors", 0, "operation"), "sliding"),
    "stops_wrong_way": _set(("doors", 0, "stops"), {"hinge": 34, "latch": 0}),
    "not_positive": _set(("doors", 0, "head_stop_bottom"), 0),
    "door_stated_shape": _set(("doors", 0, "stated_clear"), "34 x 80"),
    "door_stated_keys": _set(("doors", 0, "stated_clear"), {"width": 34, "height": 80, "source": "A", "bottom": 0}),
    "door_stated_no_source": _set(("doors", 0, "stated_clear"), {"width": 34, "height": 80}),
    "door_drawn_unread": _with(base, lambda d: d["doors"][0].update(
        stated_clear={"width": 34, "height": 80, "source": "A"}, head_stop_bottom=None)),
    # what the architect states of an escape opening and its area well (stated_well, test_interior_stated_well.py)
    "negative_area": _set(("openings", 0, "stated_well"), {"area": -9}),
    "well_not_stated": _set(("openings", 0, "stated_well"), {}),
    "well_stated_not_read": _set(("openings", 0, "stated_well"), {"below_grade": "yes"}),
    "well_stated_bad": _set(("openings", 0, "stated_well"), {"width": -36}),
    "well_disagree": _with(base, lambda d: d["openings"][0].update(
        area_well={"floor_elevation": -10, "width": 36, "projection": 36}, stated_well={"width": 40})),
    "well_area_over_size": _set(("openings", 0, "stated_well"), {"area": 2000, "width": 36, "projection": 36}),
    "well_no_ladder_reaches": _set(("openings", 0, "stated_well"), {"ladder": "none", "ladder_encroachment": 3}),
    "well_stated_unread": _set(("openings", 0, "stated_well"), {"depht": 50}),
    "well_drawn_not_stated": _with(base, lambda d: d["openings"][0].update(
        area_well={"floor_elevation": -10, "width": 36, "projection": 36}, stated_well={})),
    "well_below_disagree": _with(base, lambda d: d["openings"][0].update(ground_outside=30,
                                                                          stated_well={"below_grade": False})),
    # what the ground given shows against the clear bottom (20 in): test_interior_ground_well.py
    "well_above_disagree": _set(("openings", 0, "stated_well"), {"below_grade": True}),
    "grade_floor_well_unknown": _with(base, lambda d: d["openings"][0].update(ground_outside=30, stated_well={})),
    "well_ground_between": _with(base, lambda d: d["openings"][0].update(
        frame=None, ground_outside=10, clear_bottom_between=[0, 20], stated_well={})),
    "well_bottom_unread": _with(base, lambda d: d["openings"][0].update(
        frame=None, ground_outside=10, clear_bottom_between=[20, 0], stated_well={})),
    "bottom_between_bad": _with(base, lambda d: d["openings"][0].update(
        frame=None, ground_outside=10, clear_bottom_between=[0], stated_well={})),
    "well_ground_near": _with(base, lambda d: d["openings"][0].update(ground_outside=20, stated_well={})),
    "well_ground_no_bottom": _with(base, lambda d: d["openings"][0].update(frame=None, ground_outside=30,
                                                                            stated_well={})),
    "well_ground_unread": _with(base, lambda d: d["openings"][0].update(ground_outside="high", stated_well={})),
    "well_depth_least": _with(base, lambda d: d["openings"][0].update(ground_outside=50, stated_well={})),
    "well_depth_disagree": _with(base, lambda d: d["openings"][0].update(ground_outside=50,
                                                                          stated_well={"depth": 10})),
}


def _geometry_fails(*_args, **_kw):
    from shapely.errors import GEOSException
    raise GEOSException("TopologyException: a stand-in")


# a reason no drawing reliably makes (the geometry library failing): it is made to happen
def _no_bound(mp):
    mp.setattr("model_measurement.interior.read.FAR", math.inf)


STOP_SETUP = {"shapes_failed": lambda mp: mp.setattr("model_measurement.interior.stairs.unary_union", _geometry_fails),
              # reasons behind the read-time bound (read.FAR): the bound lifted, each still happens
              "surface_out_of_range": _no_bound, "nosings_out_of_range": _no_bound, "not_finite": _no_bound}


def test_every_stop_has_a_case():
    assert set(STOP_CASES) == set(STOPS)


@pytest.mark.parametrize("key", sorted(STOP_CASES))
def test_each_stop_happens_and_reaches_the_output(key, monkeypatch):
    made, init = [], Stop.__init__

    def recording(self, which, /, **blanks):
        init(self, which, **blanks)
        made.append((which, self.reason))

    monkeypatch.setattr(Stop, "__init__", recording)
    STOP_SETUP.get(key, lambda mp: None)(monkeypatch)
    got = measure(STOP_CASES[key]())
    reasons = [r for w, r in made if w == key]
    assert reasons, f"{key} didn't happen"
    # the reason is in the output (a part's not_measured, or the description's problems), never swallowed
    text = repr(got)
    assert any(r in text for r in reasons), key


def test_the_doc_lists_every_reason_word_for_word():
    from pathlib import Path
    doc = (Path(__file__).parents[3] / "docs" / "interior" / "interior_measurements.md").read_text(encoding="utf-8")
    rows = dict(line.split(" | ", 1) for line in (r.strip("| ").replace("\\|", "|") for r in doc.splitlines())
                if line.startswith("`") and " | " in line and line.split(" | ")[0].strip("`") in STOPS)
    listed = {k.strip("`"): v for k, v in rows.items()}
    assert listed == STOPS


def test_every_measure_parts_yaml_lists_is_measured_or_has_a_reason():
    """parts.yaml can list a measure before this code works it out (#96 added area wells, patio covers and more to
    escape openings): it then gets the not_measured_yet reason, so a rule reading it needs review, never silence."""
    from rule_format.parts import measure_kinds
    got = measure(base())
    for kind, parts in got["parts"].items():
        if kind == "guard":
            continue
        for p in parts or []:
            for name in measure_kinds(kind):
                assert name in p["measures"] or name in p["not_measured"], (kind, p["id"], name)
            for name, why in p["not_measured"].items():
                if why == STOPS["not_measured_yet"]:
                    assert name in measure_kinds(kind) and name not in p["measures"] and name not in p["more"], name
                if why == STOPS["in_more_not_rules"]:
                    assert name in measure_kinds(kind) and name in p["more"] and name not in p["measures"], name


def test_a_measured_area_well_is_said_to_be_measured_not_missing():
    """The four area-well values are worked out (kept in `more`); their reason says so, not 'not measured yet'."""
    d = base()
    d["openings"][0]["area_well"] = {"floor_elevation": 10, "width": 36, "projection": 36}
    p = one(d, "emergency_escape_opening")
    for name in ("area_well_area", "area_well_depth"):
        assert name in p["more"] and p["not_measured"][name] == STOPS["in_more_not_rules"], name


def test_a_sill_below_its_rooms_floor_is_no_value():
    """A wrong floor elevation must not make a low sill: 20 in bottom over a 30 in floor is -10 in, which would pass
    the 44 in maximum. It gets no value (needs review); within 1/16 in under the floor it is drawing noise, read as 0."""
    _, stopped, _ = opening_measures(changed(("rooms", 0, "floor_elevation"), 30))
    assert "below it" in stopped["opening_sill_height"]
    m, stopped, _ = opening_measures(changed(("rooms", 0, "floor_elevation"), 20 + 1 / 32))
    assert m["opening_sill_height"] == 0.0 and "opening_sill_height" not in stopped


# --- facts the description holds, as measures (docs/decisions/2026-11-16_interior_absent_parts.md, item 5) -----------

@pytest.mark.parametrize("operation, side_hinged", [("side_hinged", True), ("sliding", False), ("folding", False),
                                                    ("pocket", False), ("other", None), (_DELETE, None)])
def test_a_door_is_side_hinged_only_by_its_operation(operation, side_hinged):
    """door_side_hinged straight from `operation`; `other`, or no operation, gives no value (never a guess)."""
    p = one(changed(("doors", 0, "operation"), operation), "egress_door")
    if side_hinged is None:
        assert "door_side_hinged" not in p["measures"] and p["not_measured"]["door_side_hinged"]
    else:
        assert p["measures"]["door_side_hinged"] is side_hinged


@pytest.mark.parametrize("operation, is_door", [
    ("side_hinged_door", True), ("sliding_door", True), ("casement", False), ("double_hung", False),
    ("single_hung", False), ("horizontal_slider", False), ("awning", False), ("hopper", False),
    ("fixed", None), ("pivot", None), ("tilt_turn", None), ("other", None), (_DELETE, None)])
def test_an_opening_is_a_door_only_by_its_operation(operation, is_door):
    """opening_is_door from `operation` alone; fixed, pivot, tilt-turn and other units are made as doors and as
    windows, and a missing operation says nothing: no value. A door is side-hinged or sliding (R319.3)."""
    p = one(changed(("openings", 0, "operation"), operation), "emergency_escape_opening")
    if is_door is None:
        assert "opening_is_door" not in p["measures"] and "opening_door_hinged_or_sliding" not in p["measures"]
        assert p["not_measured"]["opening_is_door"] != STOPS["not_measured_yet"]
    else:
        assert p["measures"]["opening_is_door"] is is_door
        assert p["measures"].get("opening_door_hinged_or_sliding") is (True if is_door else None)
        if not is_door:
            assert p["not_measured"]["opening_door_hinged_or_sliding"] == STOPS["not_a_door"]


def test_opening_operable_is_not_measured_yet():
    """It follows from `operation`, but R319.6's rule would then pass every new house's bedrooms, where R319.6
    doesn't apply (decision item 5): not given until that rule is fixed."""
    p = one(base(), "emergency_escape_opening")
    assert "opening_operable" not in p["measures"]
    assert p["not_measured"]["opening_operable"] == STOPS["not_measured_yet"]


# --- what the description says the house has none of (has_none) -----------------------------------------------------

def _claims(*entries, **lists):
    d = base()
    d["has_none"] = list(entries)
    d.update(lists)
    return d


def test_silence_reads_no_kind_it_doesnt_list():
    got = measure(base())
    assert got["has_none"] == {}
    for kind in ("ramp", "sleeping_loft", "loft_room", "basement", "habitable_attic", "alternating_tread_device",
                 "ships_ladder"):
        assert got["parts"].get(kind) is None, kind          # not read: never "none"
    p = got["parts"]["emergency_escape_opening"][0]
    assert "opening_into_patio_cover" not in p["measures"] and "opening_under_projection" not in p["measures"]
    assert "stair_serves_sleeping_loft" not in got["parts"]["stair"][0]["measures"]


def test_each_claim_empties_its_kinds_or_gives_its_measures():
    got = measure(_claims({"kind": "ramp", "source": "A-2"}, {"kind": "sleeping_loft", "source": "A-3"},
                          {"kind": "patio_cover", "source": "A-4", "reading": True},
                          {"kind": "deck_porch_or_cantilever_over_escape_opening", "source": "A-3"}))
    assert got["problems"] == []
    assert got["parts"]["ramp"] == [] and got["parts"]["sleeping_loft"] == [] and got["parts"]["loft_room"] == []
    assert got["parts"].get("basement") is None                        # not claimed: still not read
    w = got["parts"]["emergency_escape_opening"][0]
    assert w["measures"]["opening_into_patio_cover"] is False and w["measures"]["opening_under_projection"] is False
    assert w["stated"] == {"opening_into_patio_cover": "patio_cover",
                           "opening_under_projection": "deck_porch_or_cantilever_over_escape_opening"}
    s = got["parts"]["stair"][0]
    assert s["measures"]["stair_serves_sleeping_loft"] is False and "stair_serves_sleeping_loft" not in s["not_measured"]
    assert got["has_none"]["ramp"]["source"] == "A-2" and got["has_none"]["ramp"]["reading"] is False
    assert got["has_none"]["patio_cover"]["reading"] is True
    assert got["has_none"]["ramp"]["words"] == "the model says the house has no ramps"


@pytest.mark.parametrize("entries, lists, words", [
    ([{"kind": "ramp", "source": "A-2"}], {"ramps": [{"id": "r1"}]}, "yet it also gives ramps, and not an empty list"),
    ([{"kind": "ramp", "source": "A-2"}], {"ramps": "a ramp"}, "yet it also gives ramps, and not an empty list"),
    ([{"kind": "ramp"}], {}, "not where that comes from"),
    ([{"kind": "ramp", "source": ""}], {}, "not where that comes from"),
    ([{"kind": "ramp", "source": "A-2"}], {"ramps": None}, "yet it also gives ramps, and not an empty list"),
    ([{"kind": "ramp", "source": "A-2", "reading": 1}], {}, "gives whether that rests on a reading of the law as 1, not as a yes/no value"),
    ([{"kind": "ramp", "source": "A-2", "reding": True}], {}, "a reading (also reding)"),
    ([{"kind": "ramp", "source": "A-2"}, {"kind": "ramp", "source": "A-2", "reding": True}], {}, "2 times"),
    ([{"kind": "ramp", "source": "A-2"}, {"kind": "ramp", "source": "A-4"}], {}, "2 times"),
    ([{"kind": "ramp", "source": "A-2"}, {"kind": "ramp"}], {}, "2 times"),
    ([{"kind": "ramps", "source": "A-2"}], {}, "not a kind it can say"),
    ([{"kind": "stair", "source": "A-2"}], {}, "an empty list of stairs"),
    ([{"kind": "sleeping_room", "source": "A-2"}], {}, "(sleeping room: no)"),
    (["ramp"], {}, "entry #1"),
])
def test_a_claim_that_cant_be_trusted_is_a_problem_and_its_kind_stays_not_read(entries, lists, words):
    got = measure(_claims(*entries, **lists))
    assert got["parts"].get("ramp") is None and "ramp" not in got["has_none"]
    assert any(words in p for p in got["problems"]), got["problems"]


def test_a_claim_with_an_empty_list_of_its_kind_is_no_contradiction():
    got = measure(_claims({"kind": "ramp", "source": "A-2"}, ramps=[]))
    assert got["parts"]["ramp"] == [] and got["problems"] == []


def test_has_none_not_a_list_reads_no_claim():
    d = base()
    d["has_none"] = {"kind": "ramp", "source": "A-2"}
    got = measure(d)
    assert got["parts"].get("ramp") is None and got["has_none"] == {} and got["problems"]


@pytest.mark.parametrize("change, refused", [
    (lambda d: None, None),                                                       # on the ground: taken
    (lambda d: d["openings"][0].update(ground_outside=12), "room Bedroom is below the ground outside an opening"),
    (lambda d: d["openings"][0].update(ground_outside=[-12, 6]), "below the ground outside an opening"),  # higher end
    # a room with no openings of its own, below the ground at another room's opening (review round 5)
    (lambda d: d["rooms"].append({**d["rooms"][0], "id": "low", "name": "Rec room", "floor_elevation": -48}),
     "room Rec room is below the ground outside an opening"),
    # a stair's foot below every ground given (review round 5)
    (lambda d: d["stairs"][0].update(bottom_elevation=-100), "stair Stair is below the ground outside an opening"),
    (lambda d: [o.pop("ground_outside") for o in d["openings"]], None),          # no ground given: nothing compared
    # a ground, floor or stair foot that can't be read could be below the ground: refused, never a crash (round 6)
    (lambda d: d["openings"][0].update(ground_outside=float("inf")), "the ground outside opening Window can't be read"),
    (lambda d: d["openings"][0].update(ground_outside=10 ** 400), "the ground outside opening Window can't be read"),
    (lambda d: d["openings"][0].update(ground_outside=[0, "6"]), "the ground outside opening Window can't be read"),
    (lambda d: d["rooms"][0].update(floor_elevation=-10 ** 400), "the floor of room Bedroom can't be read"),
    (lambda d: d["stairs"][0].update(bottom_elevation=float("nan")), "the foot of stair Stair can't be read"),
    (lambda d: d["openings"][0].update(ground_outside=-30), None),               # ground below the floor: taken
    (lambda d: d["openings"][0].update(area_well={"floor_elevation": -10, "width": 40, "projection": 36}),
     "has an area well"),
])
def test_a_no_basements_claim_cant_stand_beside_a_space_below_the_ground(change, refused):
    """The description itself shows a space below the ground (an area well, the format's "for an opening below the
    ground", or a room's floor below the ground outside its opening): "no basements" beside it is refused, and the
    basement rules need review (review round 4). Only refused, never "there is a basement"."""
    d = _claims({"kind": "basement", "source": "A-1"})
    change(d)
    got = measure(d)
    if refused is None:
        assert got["parts"]["basement"] == [] and "basement" in got["has_none"]
    else:
        assert got["parts"].get("basement") is None and "basement" not in got["has_none"]
        assert any(refused in p for p in got["problems"]), got["problems"]


@pytest.mark.parametrize("change", [
    lambda d: d["rooms"][0].update(id=["b"]),
    lambda d: d["openings"][0].update(room=["b"]),
])
def test_a_no_basements_claim_beside_an_id_that_isnt_text_doesnt_stop_the_measuring(change):
    """A room id, or an opening's room, that isn't text measures as it would without the claim (review round 5:
    it raised TypeError)."""
    d = _claims({"kind": "basement", "source": "A-1"})
    change(d)
    measure(d)


def _loft(floor_elevation=100):
    """A sleeping room over part of base()'s bedroom (floor 0, ceiling 96 in): inside its volume at 50, as 4_loft
    draws a loft; at 96 or more it is a room upstairs."""
    return {"id": "l", "name": "Loft", "sleeping": True, "floor": [[0, 0], [60, 0], [60, 60], [0, 60]],
            "floor_elevation": floor_elevation, "ceiling_height": 84}


@pytest.mark.parametrize("change, refused", [
    (lambda d: None, None),                                                       # one room: taken
    (lambda d: d["rooms"].append(_loft(50)), "room Loft's floor is over room Bedroom's and below its ceiling"),
    # a room that isn't a sleeping room, drawn with no floor at all (Orangetown's basement): not compared
    (lambda d: d["rooms"].append({"id": "x", "name": "Basement", "sleeping": False}), None),
    (lambda d: d["rooms"].append(_loft(96)), None),                               # upstairs: taken
    (lambda d: d["rooms"].append({**_loft(50), "floor": [[200, 0], [260, 0], [260, 60], [200, 60]]}), None),  # beside
    # a ceiling given as pieces: the highest point counts
    (lambda d: (d["rooms"][0].pop("ceiling_height"), d["rooms"][0].update(
        ceilings=[[[0, 0, 40], [120, 0, 40], [120, 120, 120], [0, 120, 120]]]), d["rooms"].append(_loft(100))),
     "room Loft's floor is over room Bedroom's and below its ceiling"),
    # read from a host: every underside over the room below, its own ceiling and the floor above's rooms' ceilings
    # over it (Orangetown's main floor read from Revit): the room upstairs is over its ceiling, so taken
    (lambda d: (d["rooms"][0].pop("ceiling_height"), d["rooms"][0].update(
        ceilings=[[[0, 0, 96], [120, 0, 96], [120, 120, 96], [0, 120, 96]],
                  [[0, 0, 192], [60, 0, 192], [60, 60, 192], [0, 60, 192]]]), d["rooms"].append(_loft(100))), None),
    # but a higher piece reaching past the lower one is the room's ceiling there: refused
    (lambda d: (d["rooms"][0].pop("ceiling_height"), d["rooms"][0].update(
        ceilings=[[[0, 0, 96], [120, 0, 96], [120, 60, 96], [0, 60, 96]],
                  [[0, 0, 192], [120, 0, 192], [120, 120, 192], [0, 120, 192]]]), d["rooms"].append(_loft(100))),
     "room Loft's floor is over room Bedroom's and below its ceiling"),
    # the room below's ceiling can't be read: it could be above the loft, so refused
    (lambda d: (d["rooms"][0].pop("ceiling_height"), d["rooms"].append(_loft(100))),
     "room Bedroom's ceiling can't be read"),
    # a ceiling piece partly given as text: never read from the pieces that can be (review round 6)
    (lambda d: (d["rooms"][0].pop("ceiling_height"), d["rooms"][0].update(
        ceilings=[[[0, 0, 40], [120, 0, 40], [120, 60, 40]], [[0, 60, "120"], [120, 60, "120"], [0, 120, "120"]]]),
        d["rooms"].append(_loft(60))), "room Bedroom's ceiling can't be read"),
    # a floor that can't be read can't be told not to be within another room (review round 6)
    (lambda d: d["rooms"].append({**_loft(50), "floor": [[0, 0, 0], [60, 0, 0], [60, 60, 0]]}),
     "room Loft's floor can't be read"),
    (lambda d: d["rooms"].append({**_loft(50), "floor": [[0, 0], [60, 60], [60, 0], [0, 60]]}),   # self-crossing
     "room Loft's floor can't be read"),
    (lambda d: (d["rooms"].append(_loft(50)), d["rooms"][0].update(floor_elevation="0")),
     "room Bedroom's floor can't be read"),
    (lambda d: d["rooms"].append({**_loft(50), "floor_elevation": float("nan")}), "room Loft's floor can't be read"),
    (lambda d: d["rooms"].append({**_loft(50), "floor_elevation": 10 ** 400}), "room Loft's floor can't be read"),
    (lambda d: d["rooms"].append({**_loft(50), "floor": [[0, 0], [10 ** 400, 0], [60, 60]]}),
     "room Loft's floor can't be read"),
])
def test_a_no_sleeping_lofts_claim_cant_stand_beside_a_room_drawn_within_another(change, refused):
    """The format draws a sleeping loft as a room whose floor is within another room's volume: "no sleeping lofts"
    beside one is refused, and the loft rules need review (review round 5). Only refused, never "there is a loft"."""
    d = _claims({"kind": "sleeping_loft", "source": "A-3"})
    change(d)
    got = measure(d)
    if refused is None:
        assert got["parts"]["sleeping_loft"] == [] and "sleeping_loft" in got["has_none"], got["problems"]
    else:
        assert got["parts"].get("sleeping_loft") is None and got["parts"].get("loft_room") is None
        assert "sleeping_loft" not in got["has_none"]
        assert all("stair_serves_sleeping_loft" not in (s.get("stated") or {}) for s in got["parts"]["stair"] or [])
        assert any(refused in p for p in got["problems"]), got["problems"]
