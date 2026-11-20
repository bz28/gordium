"""A real house placed by its layout.yaml (test_data/real_houses/orangetown_ny_80_south_william/), so a host such as Revit
can draw it and read it back (model_measurement.interior.recordings: layout_problems, placed_drawing). The layout must
be self-consistent and house.yaml's: rooms and walls don't overlap, every enclosed area is exactly one room, each
house.yaml room is placed with its own inside dimensions and area, each marked window lies in a wall of its own room,
and the drawing a host gets from it measures, through the reader's eyes, as expected.yaml says. Each way a layout can
be wrong is pinned by changing one thing and seeing it refused."""

import copy

import pytest
import yaml
from shapely.geometry import LineString, Point, Polygon

from model_measurement.interior import measure
from model_measurement.interior import recordings as r

NAME = "orangetown_ny_80_south_william"
HOUSE = yaml.safe_load((r.REAL / NAME / "house.yaml").read_text(encoding="utf-8"))
EXPECTED = yaml.safe_load((r.REAL / NAME / "expected.yaml").read_text(encoding="utf-8"))
LAYOUT = r._layout(NAME)


@pytest.fixture
def layout(monkeypatch):
    """A copy of the layout the code reads, for one change."""
    lay = copy.deepcopy(LAYOUT)
    monkeypatch.setattr(r, "_layout", lambda name: lay)
    return lay


def level(lay, lid):
    return next(lv for lv in lay["levels"] if lv["id"] == lid)


def room(lay, rid):
    return next(x for lv in lay["levels"] for x in lv["rooms"] if x["id"] == rid)


def test_the_layout_has_no_problems():
    assert r.layout_problems(NAME) == []


def test_each_room_house_yaml_gives_is_placed_with_its_own_size_and_area():
    # exactly (to a millionth of a square inch): the placed rooms are the same inside dimensions, and the recordings are
    # compared with expected.yaml to a millionth
    for given in HOUSE["rooms"]:
        placed = Polygon(room(LAYOUT, given["id"])["floor"])
        if "floor" in given:
            assert placed.area == Polygon(given["floor"]).area, given["id"]
            assert placed.area == placed.envelope.area, given["id"]
    d = r.drawing(NAME)
    by_id = {x["id"]: x for x in d["rooms"]}
    for rid, part in EXPECTED["parts"]["sleeping_room"].items():
        assert Polygon(by_id[rid]["floor"]).area == pytest.approx(part["measures"]["sleeping_room_floor_area"], abs=1e-6)
        assert by_id[rid]["sleeping"] is True and by_id[rid]["floor_elevation"] == 0
        assert {z for piece in by_id[rid]["ceilings"] for *_, z in piece} == {8.0}
    assert {x["id"] for x in d["rooms"] if x["sleeping"]} == set(EXPECTED["parts"]["sleeping_room"])


def test_rooms_dont_overlap_and_lie_clear_of_the_walls():
    d = r.drawing(NAME)
    for lv in d["levels"]:
        rooms = [Polygon(x["floor"]) for x in d["rooms"] if x["floor_elevation"] == lv["elevation"]]
        walls = [Polygon([(a[0], a[1]), (b[0], a[1]), (b[0], b[1]), (a[0], b[1])]) for a, b in lv["walls"]]
        for i, a in enumerate(rooms):
            assert all(a.intersection(b).area < 1e-9 for b in rooms[i + 1:])
            assert all(a.intersection(w).area < 1e-9 for w in walls)
            assert Polygon(lv["outline"]).contains(a)


def test_every_window_lies_in_a_wall_of_its_own_room_at_its_sill():
    d = r.drawing(NAME)
    rooms = {x["id"]: x for x in d["rooms"]}
    assert sorted(w["id"] for w in d["windows"]) == sorted(o["id"] for o in HOUSE["openings"])
    for w in d["windows"]:
        o = next(o for o in HOUSE["openings"] if o["id"] == w["id"])
        assert w["room"] == o["room"] and w["escape"] is o["escape"] and w["operation"] == o["operation"]
        lv = next(lv for lv in d["levels"] if lv["elevation"] == w["level"])
        (x0, y0), (x1, y1) = lv["walls"][w["wall"]]
        ox, oy = w["outward"]
        half = w["width"] / 2
        ax, ay = -oy, ox                                     # along the wall
        ends = [(w["center"][0] + s * half * ax, w["center"][1] + s * half * ay) for s in (-1, 1)]
        # its inside face on the wall's face toward the room, both ends within the wall, the room's edge there
        for ex, ey in ends:
            assert x0 - 1e-9 <= ex <= x1 + 1e-9 and y0 - 1e-9 <= ey <= y1 + 1e-9, w["id"]
            assert Polygon(rooms[w["room"]]["floor"]).boundary.distance(Point(ex, ey)) < 1e-9, w["id"]
        # outward points out of the room, through the wall: its centre line half the thickness out
        assert w["at"] == pytest.approx([w["center"][0] + ox * w["wall_thickness"] / 2,
                                         w["center"][1] + oy * w["wall_thickness"] / 2])
        assert not Polygon(rooms[w["room"]]["floor"]).contains(Point(w["at"]))
        assert w["sill"] + w["height"] == pytest.approx(81 / 12)          # A-1: every header at 6'-9"
        assert w["clear"] is None                                          # no clear opening: nothing to measure
    sills = {w["id"]: round(w["sill"] * 12, 6) for w in d["windows"]}
    assert sills["b2a"] == 27 and sills["b4a"] == 19 and sills["x1"] == 19      # 3046: 4'-6" high; 3052: 5'-2"


def test_the_front_door_is_in_the_entrys_front_wall_on_the_main_floor():
    d = r.drawing(NAME)
    (door,) = d["doors"]
    assert (door["id"], door["exit"], door["operation"]) == ("front", True, "side_hinged")
    assert door["level"] == pytest.approx(-118.5 / 12) and door["room"] == "main_floor"
    assert (door["width"], door["height"], door["outward"], door["clear"]) == (3.0, 8.0, [0, -1], None)


def test_stairs_and_guards_are_placed_but_not_drawn():
    d = r.drawing(NAME)
    assert d["stairs"] == [] and d["guards"] == [] and d["not_drawn"] == ["guards", "stairs"]
    assert {g["id"] for g in LAYOUT["not_drawn"]["guards"]} == {g["id"] for g in HOUSE["guards"]}
    assert {s["id"] for s in LAYOUT["not_drawn"]["stairs"]} == {"main_stair", "basement_stair"}


def test_levels_walls_stop_under_the_level_above():
    d = r.drawing(NAME)
    zs = sorted(lv["elevation"] for lv in d["levels"])
    assert zs == pytest.approx([-226.5 / 12, -118.5 / 12, 0.0])
    for lv in d["levels"]:
        above = [z for z in zs if z > lv["elevation"]]
        if above:
            assert lv["elevation"] + lv["wall_height"] <= above[0] + 1e-9


def test_each_rooms_boundary_names_the_wall_along_each_edge():
    d = r.drawing(NAME)
    for x in d["rooms"]:
        loop = x["boundary"]
        assert all(a[1] == b[0] for a, b in zip(loop, loop[1:] + loop[:1])), x["id"]      # one closed loop
        assert Polygon([seg[0] for seg in loop]).area == pytest.approx(Polygon(x["floor"]).area)
        assert Polygon([seg[0] for seg in loop]).exterior.is_ccw
        lv = next(lv for lv in d["levels"] if lv["elevation"] == x["floor_elevation"])
        for a, b, k in loop:
            edge = LineString([a, b])
            if k is None:                                   # a room separation line: the edge lies on one
                assert any(edge.within(LineString(s).buffer(1e-9)) for s in lv["separations"]), (x["id"], a, b)
                continue
            (x0, y0), (x1, y1) = lv["walls"][k]             # a wall: the edge lies on its outline
            wall = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            assert edge.within(wall.exterior.buffer(1e-9)), (x["id"], a, b, k)
    bed2 = next(x for x in d["rooms"] if x["id"] == "bed2")
    assert [seg[2] for seg in bed2["boundary"]].count(None) == 1          # the alcove's separation line


def test_the_drawing_read_back_measures_as_expected():
    # what a host's reader sends for it: every sleeping room's area and ceiling, every window with no clear opening,
    # every escape window outside a sleeping room not checked
    d = r.drawing(NAME)
    interior = {"format": "gordium.interior/1", "units": "ft",
                "rooms": [{k: x[k] for k in ("id", "name", "sleeping", "floor", "floor_elevation", "ceilings")}
                          for x in d["rooms"]],
                "openings": [{k: w[k] for k in ("id", "name", "room", "escape", "operation")} for w in d["windows"]]}
    got = measure(interior)
    for p in got["parts"]["sleeping_room"]:
        assert p["measures"] == pytest.approx(EXPECTED["parts"]["sleeping_room"][p["id"]]["measures"])
    assert sorted(x["id"] for x in got["not_checked"]) == sorted(EXPECTED["not_checked"])
    for p in got["parts"]["emergency_escape_opening"]:
        assert set(EXPECTED["parts"]["emergency_escape_opening"][p["id"]]["not_measured"]) <= set(p["not_measured"])


# ---- each way a layout can be wrong is refused ----------------------------------------------------------------------

def test_a_bedroom_placed_an_inch_off_overlaps_and_isnt_enclosed(layout):
    for p in room(layout, "bed3")["floor"]:
        p[0] += 1
    problems = r.layout_problems(NAME)
    assert any("room bed3 overlaps wall east" in p for p in problems)
    assert any("room bed3 isn't an area its walls" in p for p in problems)
    with pytest.raises(ValueError, match="can't be drawn"):
        r.drawing(NAME)


def test_a_bedroom_not_house_yamls_size_is_refused(layout):
    room(layout, "master")["floor"][1][0] -= 1
    room(layout, "master")["floor"][2][0] -= 1
    level(layout, "second_floor")["walls"]["master_east"][0] -= 1
    assert any("room master: placed 161 x 204, house.yaml's is 162 x 204" in p for p in r.layout_problems(NAME))


def test_a_wall_left_out_leaves_an_area_with_no_room_or_two_rooms_in_one(layout):
    del level(layout, "second_floor")["walls"]["wic_divider"]
    problems = r.layout_problems(NAME)
    assert any("is no room" in p for p in problems)
    assert any("room wic_master_1 isn't an area" in p for p in problems)


def test_an_area_enclosed_with_no_room_is_refused(layout):
    sf = level(layout, "second_floor")
    sf["rooms"] = [x for x in sf["rooms"] if x["id"] != "linen"]
    assert any("(22.67 sq ft, around x" in p and "is no room" in p for p in r.layout_problems(NAME))


def test_the_alcoves_separation_line_is_needed(layout):
    level(layout, "second_floor")["separations"] = []
    problems = r.layout_problems(NAME)
    assert any("room bed2 isn't an area" in p for p in problems) and any("is no room" in p for p in problems)


def test_overlapping_walls_are_refused(layout):
    level(layout, "basement")["walls"]["south"][0] = 0         # its end run into the west wall's corner
    assert any("walls west and south overlap" in p for p in r.layout_problems(NAME))


def test_a_window_in_another_rooms_wall_is_refused(layout):
    w = next(w for w in level(layout, "second_floor")["windows"] if w["id"] == "b2a")
    w["along"] = 120                                           # along the north wall, but over the master bedroom
    assert any("opening b2a: not whole in a face of its room bed2 on wall north (in master)" in p
               for p in r.layout_problems(NAME))


def test_a_window_past_its_rooms_corner_is_refused(layout):
    w = next(w for w in level(layout, "second_floor")["windows"] if w["id"] == "m2")
    w["along"] = 160                                           # 142 to 178: past the master's corner at 168
    assert any("opening m2: not whole in a face of its room master" in p for p in r.layout_problems(NAME))


def test_windows_overlapping_in_a_wall_are_refused(layout):
    next(w for w in level(layout, "second_floor")["windows"] if w["id"] == "m2")["along"] = 90
    assert any("openings m1 and m2 overlap in wall north" in p for p in r.layout_problems(NAME))


def test_an_opening_house_yaml_gives_must_be_placed_once(layout):
    sf = level(layout, "second_floor")
    sf["windows"] = [w for w in sf["windows"] if w["id"] != "x2"]
    assert "opening x2 placed 0 times, not once" in r.layout_problems(NAME)
    level(layout, "main_floor")["doors"] = []
    assert "door front placed 0 times, not once" in r.layout_problems(NAME)


def test_a_house_yaml_room_left_unplaced_is_refused(layout):
    sf = level(layout, "second_floor")
    sf["rooms"] = [x for x in sf["rooms"] if x["id"] != "bonus"]
    assert "room bonus (house.yaml) isn't placed" in r.layout_problems(NAME)


def test_a_room_not_in_house_yaml_needs_its_own_name_and_sleeping(layout):
    del room(layout, "garage")["sleeping"]
    assert any("room garage isn't in house.yaml" in p for p in r.layout_problems(NAME))


def test_a_level_whose_ceiling_isnt_house_yamls_is_refused(layout):
    level(layout, "second_floor")["ceiling"] = 97
    assert any("room master: its level gives ceiling_height 97, house.yaml 96" in p for p in r.layout_problems(NAME))


def test_each_slab_fits_the_gap_under_its_level():
    # review round 1: a 12 in slab under the second floor cut 1 1/2 in into the main floor's cited 9'-0" ceiling
    d = r.drawing(NAME)
    levels = sorted(d["levels"], key=lambda lv: lv["elevation"])
    ceiling = {lv["elevation"] / 12: lv["ceiling"] / 12 for lv in LAYOUT["levels"]}     # the cited ceilings, in ft
    for below, lv in zip(levels, levels[1:]):
        # the slab's underside at or over the cited ceiling below: (elevation above - slab) >= elevation + ceiling
        assert lv["elevation"] - lv["slab"] >= below["elevation"] + ceiling[below["elevation"]] - 1e-9
    assert [round(lv["slab"] * 12, 6) for lv in levels] == [4, 12, 10.5]     # A-2 4" slab; the gaps the framing leaves


def test_a_slab_thicker_than_its_gap_is_refused(layout):
    level(layout, "second_floor")["slab"] = 12
    assert any("second_floor: its slab doesn't fit the 10.5" in p for p in r.layout_problems(NAME))
    del level(layout, "second_floor")["slab"]
    del level(layout, "basement")["slab"]
    assert "basement: the lowest level gives no slab thickness" in r.layout_problems(NAME)


def test_each_window_pair_is_its_sizes_and_the_pair_gap_apart():
    pairs = [("m1", "m2"), ("b2a", "b2b"), ("b3a", "b3b"), ("b4a", "b4b"), ("x1", "x2")]
    windows = {w["id"]: w for lv in LAYOUT["levels"] for w in lv.get("windows") or []}
    for a, b in pairs:
        assert windows[a]["wall"] == windows[b]["wall"]
        width = LAYOUT["sizes"][windows[a]["size"]]["width"]
        assert abs(windows[b]["along"] - windows[a]["along"]) == width + LAYOUT["pair_gap"], (a, b)
    assert any("pair_gap" in x["what"] for x in LAYOUT["assumptions"])


def test_a_door_outside_its_wall_is_refused(layout):
    next(x for x in level(layout, "main_floor")["doors"] if x["id"] == "front")["along"] = 300
    assert "door front: not whole in a room's face of wall entry_front" in r.layout_problems(NAME)


def test_a_door_taller_than_its_ceiling_is_refused(layout):
    next(x for x in level(layout, "main_floor")["doors"] if x["id"] == "front")["height"] = 110
    assert "door front: taller than its level's ceiling" in r.layout_problems(NAME)


def test_a_window_head_over_the_ceiling_is_refused(layout):
    layout["head"] = 100
    assert "opening m1: doesn't fit under its level's ceiling" in r.layout_problems(NAME)


def test_a_separation_off_every_rooms_edge_is_refused(layout):
    level(layout, "second_floor")["separations"].append([[20, 20], [40, 20]])
    assert any("separation [[20, 20], [40, 20]] isn't on a room's edge" in p for p in r.layout_problems(NAME))


def test_an_opening_or_door_not_in_house_yaml_is_refused(layout):
    level(layout, "second_floor")["windows"].append({"id": "zz", "wall": "north", "along": 140, "size": "3046"})
    level(layout, "main_floor")["doors"].append({"id": "dd", "wall": "garage_south", "along": 300, "width": 36, "height": 80})
    problems = r.layout_problems(NAME)
    assert "opening zz placed but not in house.yaml" in problems and "door dd placed but not in house.yaml" in problems


def test_a_wall_with_no_thickness_and_a_slanted_room_edge_are_refused(layout):
    level(layout, "basement")["walls"]["thin"] = [300, 100, 300, 120]
    room(layout, "garage")["floor"][1] = [497, 244]
    problems = r.layout_problems(NAME)
    assert "basement: wall thin has no thickness" in problems
    assert "main_floor: room garage has an edge that isn't along x or d" in problems


def test_a_layout_not_in_the_format_or_house_yamls_units_is_refused(layout):
    layout["units"] = "ft"
    assert r.layout_problems(NAME) == [f"{NAME}: layout.yaml isn't gordium.layout/1 in house.yaml's units"]
