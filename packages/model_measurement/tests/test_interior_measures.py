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
                 "opening_at_grade": True}
    s = got["parts"]["stair"][0]
    # risers 7 (x4), treads 10 (x3); headroom least at the top nosing: 120 - 28
    assert s["measures"] == {"stair_riser_height": 7.0, "stair_tread_depth": 10.0, "stair_headroom": 92.0,
                             "stair_clear_width": 36.0}
    assert s["more"]["stair_handrail_sides"] == 0 and s["more"]["stair_clear_width_at_handrail"] == 36.0
    g = got["parts"]["guard"][0]["measures"]
    assert g == {"guard_height": 36.0, "guard_opening_sphere": 10.0}   # one opening 10 wide x 34 high
    d = got["parts"]["egress_door"][0]["measures"]
    assert d == {"door_clear_width": 32.25, "door_clear_height": 80.0}  # 34 - (0 + 1.75)
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
    assert m == {"opening_net_clear_area": 0.0, "opening_net_clear_height": 0.0, "opening_net_clear_width": 0.0}
    assert set(stopped) == {"opening_sill_height", "opening_at_grade"}


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
                 "opening_at_grade": True}


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
    assert "stated_clear" in stopped["opening_net_clear_area"]


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
    assert more["stair_riser_variation"] == 0.5 and more["stair_tread_variation"] == 0.75
    assert more["stair_total_rise"] == 28.75 and more["stair_risers"] == 4


def test_the_bottom_riser_is_from_the_floor():
    d = flight([7, 7, 7, 7], [10, 10, 10])
    d["stairs"][0]["bottom_elevation"] = -1.5                          # the floor at the foot is 1.5 lower
    m, _, more = stair(d)
    assert m["stair_riser_height"] == 8.5 and more["stair_riser_variation"] == 1.5


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
                               "stair_clear_width": 36.0})


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
    assert "overhead" in stopped["stair_headroom"]
    _, stopped, _ = stair(changed(("stairs", 0, "overhead"), {"a": 1}))
    assert "isn't a list" in stopped["stair_headroom"]


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


def test_treads_shorter_than_the_walls_narrow_the_width_at_the_treads():
    d = base()
    d["stairs"][0]["nosings"] = [[[10 * j, 1, 7 * (j + 1)], [10 * j, 34, 7 * (j + 1)]] for j in range(4)]
    m, _, more = stair(d)
    assert m["stair_clear_width"] == 36.0 and more["stair_clear_width_at_handrail"] == 33.0


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
    ({"handrails": [{"side": "left", "inner_edge": [[0, -4], [30, -4]]}]}, "meet or cross",
     "stair_clear_width_at_handrail"),
])
def test_stair_data_problems_give_no_value(change, words, measure):
    d = base()
    d["stairs"][0].update(change)
    _, stopped, _ = stair(d)
    assert words in stopped[measure], stopped


def test_risers_are_measured_even_when_the_plan_cant_be():
    m, stopped, more = stair(changed(("stairs", 0, "nosings"), [[[0, 0, 7], [0, 36, 7]]]))
    assert m == {"stair_riser_height": 7.0} and more["stair_risers"] == 1
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
    assert more["stair_riser_variation"] == 0.0625                  # 7.03125 - 6.96875 (21 - 14.03125)
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


@pytest.mark.parametrize("first", [True, False])
def test_a_surface_too_large_to_measure_is_never_dropped(first):
    """Review round 4: a 60 in plane reaching 1e200 in made NaN heights, and min() let the other surface win."""
    huge = [[-5, -5, 60], [1e200, -5, 60], [1e200, 1e200, 60], [-5, 1e200, 60]]
    normal = [[-5, -5, 200], [40, -5, 200], [40, 41, 200], [-5, 41, 200]]
    d = base()
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
    d["doors"][0]["stops"]["hinge"] = 33                              # a hinge stop deeper than the open face
    assert door(d)[0]["door_clear_width"] == 31.0                     # min(34.25, 33) - 2


def test_a_pin_off_the_leafs_corner():
    # pin 0.25 beyond the leaf's swing face: the face turns 2.0 into the opening
    d = changed(("doors", 0, "hinge_pin"), [0, 2.0])
    assert door(d)[0]["door_clear_width"] == 32.0


def test_a_hinge_stop_deeper_than_the_open_leaf():
    d = changed(("doors", 0, "stops"), {"hinge": 3, "latch": 34})
    assert door(d)[0]["door_clear_width"] == 31.0                     # 34 - max(1.75, 3)


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
    ([], "isn't a mapping"),
    ({"format": "gordium.site/1"}, "format isn't gordium.interior/1"),
    ({"format": "gordium.interior/1", "units": "cubits"}, "units (cubits)"),
    ({"format": "gordium.interior/1"}, "units (None)"),
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
    assert got["parts"][kind] is None and any(f"no `{key}`" in p for p in got["problems"])
    d[key] = "lots"
    got = measure(d)
    assert got["parts"][kind] is None and any("isn't a list" in p for p in got["problems"])
    d[key] = [3]
    assert measure(d)["parts"][kind] is None


@pytest.mark.parametrize("key, flag, kind", [("rooms", "sleeping", "sleeping_room"),
                                             ("openings", "escape", "emergency_escape_opening"),
                                             ("doors", "exit", "egress_door")])
def test_a_flag_not_given_reads_none_of_that_kind(key, flag, kind):
    d = base()
    del d[key][0][flag]
    got = measure(d)
    assert got["parts"][kind] is None and any(f"(`{flag}`: true or false)" in p for p in got["problems"])


def test_rooms_not_read_still_measures_the_openings_but_not_their_sills():
    d = base()
    del d["rooms"]
    p = one(d, "emergency_escape_opening")
    assert "opening_net_clear_area" in p["measures"] and "rooms weren't read" in p["not_measured"]["opening_sill_height"]


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
    "missing": _set(("doors", 0, "threshold_top"), _DELETE),
    "not_a_length": _set(("doors", 0, "threshold_top"), "low"),
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
    "no_ground": _set(("openings", 0, "ground_outside"), _DELETE),
    "ground_mixed": _set(("openings", 0, "ground_outside"), [0, -30]),
    "readings_differ": _with(base, lambda d: d["openings"][0].update(
        area_well={"floor_elevation": 10, "width": 36, "projection": 36}, ground_outside=80)),
    "too_few_nosings": _stair(nosings=[[[0, 0, 7], [0, 36, 7]]]),
    "nosing_not_level": _stair(nosings=[[[0, 0, 7], [0, 36, 8]]]),
    "not_bottom_to_top": _stair(nosings=[[[0, 0, -7], [0, 36, -7]]]),
    "winders": _stair(nosings=[[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [12, 36, 14]]]),
    "nosings_not_forward": _stair(nosings=[[[0, 0, 7], [0, 36, 7]], [[10, 0, 14], [10, 36, 14]],
                                           [[5, 0, 21], [5, 36, 21]]]),
    "side_not_along": _stair(sides={"left": [[-5, 36], [20, 36]], "right": [[-5, 0], [40, 0]]}),
    "sides_cross": _stair(sides={"left": [[-5, 0], [40, 0]], "right": [[-5, 36], [40, 36]]}),
    "handrail_side": _stair(handrails=[{"side": "up", "inner_edge": [[0, 4], [30, 4]]}]),
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
    "not_side_hinged": _set(("doors", 0, "operation"), "sliding"),
    "stops_wrong_way": _set(("doors", 0, "stops"), {"hinge": 34, "latch": 0}),
    "not_positive": _set(("doors", 0, "head_stop_bottom"), 0),
}


def test_every_stop_has_a_case():
    assert set(STOP_CASES) == set(STOPS)


@pytest.mark.parametrize("key", sorted(STOP_CASES))
def test_each_stop_happens_and_reaches_the_output(key, monkeypatch):
    made, init = [], Stop.__init__

    def recording(self, which, /, **blanks):
        init(self, which, **blanks)
        made.append((which, self.reason))

    monkeypatch.setattr(Stop, "__init__", recording)
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
