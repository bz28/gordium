"""Where each story sits against the grade plane (model_measurement/routes/story_place.py): the property walk, the
real eval models, and every reason a place isn't measured.

The walk's oracle is written from the 2025 Building Code of New York State's own words (Chapter 2, GRADE PLANE p.48,
STORY ABOVE GRADE PLANE p.63, BASEMENT p.34), never from story_place.py: for each building it lists every world the
ground stated allows (a grade plane, the lowest finished ground at any point, the ground along more than half the
perimeter, and which floor height of a stepped floor counts as "the floor next above"), works each story's place out
in each world as the definitions say, and requires that every fact the measuring gives is the same in every world.
Flat ground stated is one world. Spot grades: the grade plane is anywhere at or below the highest spot within reach
of the walls (Gordium's reading: the ground between spots lies between their values; the slope-away rule can only
lower it, with no lower end), and the lowest finished ground anywhere at or below the lowest spot. No ground: any.
"""

import itertools
import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from model_measurement.interior.read import Reader
from model_measurement.routes import measure
from model_measurement.routes.floor import Story
from model_measurement.routes.story_place import FACTS, FIRST, FOURTH, SECOND, ground_of, places
from model_measurement.routes.stops import STOPS

REPO = Path(__file__).resolve().parents[3]
FT = 12.0
BOX = Polygon([(0, 0), (40 * FT, 0), (40 * FT, 30 * FT), (0, 30 * FT)])     # outer faces, inches
WALL_SPOTS = [(20, -1), (41, 15), (20, 31), (-1, 15)]                        # 1 ft outside each wall, feet
PLACE_KEYS = {"no_ground", "ground_existing", "ground_assumed", "ground_spots_not_read", "ground_no_outline",
              "ground_wall_bare", "place_no_rooms", "place_story_no_rooms", "place_floor_not_read",
              "place_level_not_read", "place_split_level", "place_level_no_rooms", "place_either"}


def building(floors, extra_levels=(), outline=BOX):
    """A description and its stories: `floors` a list of lists of room floor elevations (feet), one per story."""
    levels = [{"id": f"L{i}", "name": f"Level {i}", "elevation": min(f)} for i, f in enumerate(floors)]
    levels += [{"id": f"X{i}", "name": f"Datum {i}", "elevation": z} for i, z in enumerate(extra_levels)]
    rooms = [{"id": f"L{i}r{k}", "name": f"Room {i}.{k}", "level": f"L{i}", "floor_elevation": z}
             for i, f in enumerate(floors) for k, z in enumerate(f)]
    stories = {}
    for lv in levels:
        s = Story(lv["id"], lv["name"])
        s.outer = outline
        s.rooms = {r["id"]: None for r in rooms if r["level"] == lv["id"]}
        stories[lv["id"]] = s
    return {"units": "ft", "levels": levels, "rooms": rooms}, stories


def placed(floors, ground, **kw):
    desc, stories = building(floors, **kw)
    return places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, ground)


# --- the oracle, from the definitions ------------------------------------------------------------------------------

def _worlds(floors, ground):
    """(grade plane, lowest ground at any point, ground along more than half the perimeter or None) in feet."""
    zs = sorted({z for f in floors for z in f})
    marks = {z + d for z in zs for d in (0, -6, -12)} | {0.0}
    near = sorted({m + e for m in marks for e in (-0.01, 0, 0.01)} | {-1000.0})
    if "flat" in ground:
        g = ground["flat"]
        return [(g, g, g)]
    if "spots" in ground:
        high, low = max(p[2] for p in ground["spots"]), min(p[2] for p in ground["spots"])
        planes = [g for g in near if g <= high] + [high]
        lows = [m for m in near if m <= low] + [low]
    else:
        planes, lows = near, near
    return [(g, m, p) for g in planes for m in lows if m <= g for p in (m, None)]


def _oracle(floors, world, pick):
    """Each story's (number, above) in one world, `pick` choosing each stepped floor's height for "next above"."""
    g, m, p = world
    above = []
    for i, f in enumerate(floors):
        if min(f) > g:                                           # "finished floor surface entirely above grade plane"
            above.append(True)
            continue
        if i + 1 == len(floors):
            above.append(None)                                   # the roof next above: not drawn, either way
            continue
        n = pick[i + 1]
        above.append(n > g + 6 or n > m + 12 or (p is not None and n > p + 6))
    return above


def _facts_in(floors, above):
    """Each story's three facts from which stories are above grade plane (None: either: both tried by the caller)."""
    out = []
    ups = [i for i, a in enumerate(above) if a]
    for i, a in enumerate(above):
        if a:
            n = sum(1 for k in ups if k <= i)
            out.append({FIRST: n == 1, SECOND: n == 2, FOURTH: n >= 4})
        else:
            first_up = min(ups) if ups else len(above)
            below = sum(1 for k in range(i, first_up) if not above[k])
            out.append({FIRST: below == 1, SECOND: False, FOURTH: False})
    return out


def oracle(floors, ground):
    """Every combination of facts the stated ground allows, per story: [set of (first, second, fourth)]."""
    seen = [set() for _ in floors]
    picks = list(itertools.product(*[sorted(set(f)) for f in floors]))
    for world in _worlds(floors, ground):
        for pick in picks:
            above = _oracle(floors, world, pick)
            for top in ((True, False) if above[-1] is None else (above[-1],)):
                got = _facts_in(floors, above[:-1] + [top])
                for i, f in enumerate(got):
                    seen[i].add((f[FIRST], f[SECOND], f[FOURTH]))
    return seen


STACKS = [[[0]], [[0], [10]], [[0], [10], [20], [30]], [[-10], [0], [10], [20], [30]], [[-4], [6], [16]],
          [[-8], [2], [12], [22]], [[-10, -9], [0], [10]], [[0, -0.6], [10, 9.5]], [[-6], [3.5], [14]],
          [[-14], [-4], [6], [16], [26]], [[2], [13]], [[-12], [-2]], [[0], [6], [12], [18], [24]]]
GROUNDS = ([{"flat": z} for z in (-8, -6, -4, -2, -0.5, 0, 0.5, 2, 3.5, 4, 6, 7, 10)]
           + [{"spots": [[x, y, z] for (x, y), z in zip(WALL_SPOTS, zs)]}
              for zs in ((0, 0, 0, 0), (-1, 0, 1, 0), (-6, -2, 0, -4), (2, 2, 4, 3), (-12, 0, 0, -10), (5, 6, 7, 8))])


@pytest.mark.parametrize("floors", STACKS, ids=lambda f: "_".join(str(min(x)) for x in f))
def test_every_place_measured_is_the_same_in_every_world_the_ground_stated_allows(floors):
    """The property: a fact measured is the oracle's one value; a fact the oracle can't settle is never measured. And
    flat ground settles every story whose floors are clear of the thresholds, where the top one is above the ground
    (the measuring is no lazier than it must be there)."""
    for ground in GROUNDS + [None]:
        got = placed(floors, ground or {"none": "none stated"})
        seen = oracle(floors, ground or {})
        for i, lid in enumerate(f"L{k}" for k in range(len(floors))):
            for k, fact in enumerate((FIRST, SECOND, FOURTH)):
                values = {s[k] for s in seen[i]}
                if fact in got[lid]["measures"]:
                    assert values == {got[lid]["measures"][fact]}, (floors, ground, lid, fact, values)
                else:
                    assert fact in got[lid]["not_measured"], (floors, ground, lid, fact)
        if ground and "flat" in ground and all(len(set(f)) == 1 for f in floors) and \
                all(abs(f[0] - ground["flat"] - d) > 0.1 for f in floors for d in (0, 6)) and                 floors[-1][0] > ground["flat"]:            # a top story at or below grade has no floor above to test
            assert all(f in got[f"L{i}"]["measures"] for i in range(len(floors) - 1) for f in FACTS), (floors, ground)


def test_the_oracle_catches_a_wrong_place():
    """The walk fails on a measuring that counts from the grade plane's top end only (the spots' highest point as
    the grade plane), the mistake the coordinator's review named: a basement read as the first story above."""
    floors, ground = [[-4], [6], [16]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS]}
    seen = oracle(floors, ground)
    assert {s[0] for s in seen[1]} == {True, False}      # Level 1 may be the first or the second story above
    got = placed(floors, ground)
    assert FIRST not in got["L1"]["measures"]


# --- the real eval models ------------------------------------------------------------------------------------------

APARTMENT = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"
ITHACA_RD = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"


def _apartment_places(ground):
    got = measure(json.loads(APARTMENT.read_text(encoding="utf-8"))["interior"], ground=ground)
    return {s["name"]: s for s in got["parts"]["story"]}


def test_the_four_unit_apartment_as_sent_has_no_ground_so_no_place():
    for s in _apartment_places(None).values():
        assert not set(FACTS) & set(s["measures"])
        assert s["not_measured"][FIRST] == STOPS["no_ground"]


@pytest.mark.parametrize("ground", [{"flat": 0.0},
                                    {"spots": [[30, -1.5, 0], [61.5, 15, 0], [30, 31.5, 0], [-1.5, 15, 0]]}])
def test_the_four_unit_apartment_on_its_flat_ground_is_first_and_second_above_grade(ground):
    """apartment.yaml: "flat ground at 0"; Level 1 at 0, Level 2 10 ft up: Level 1's floor next above is more than
    6 ft above the grade plane (item 1), so it is the first story above; Level 2's floor is entirely above."""
    s = _apartment_places(ground)
    assert {k: s["Level 1"]["measures"][k] for k in FACTS} == {FIRST: True, SECOND: False, FOURTH: False}
    assert {k: s["Level 2"]["measures"][k] for k in FACTS} == {FIRST: False, SECOND: True, FOURTH: False}
    if "spots" in ground:
        assert "Gordium's reading" in s["Level 1"]["more"]["story_place"]["reading"]


def test_the_four_unit_apartment_on_ground_5_ft_up_has_a_basement_and_a_first_story_above():
    s = _apartment_places({"flat": 5.0})
    assert s["Level 1"]["measures"][FIRST] is True and s["Level 2"]["measures"][FIRST] is True
    assert s["Level 2"]["measures"][SECOND] is False


def test_106_ithaca_rd_its_levels_and_spot_grades():
    """The Revit eval's own levels (Level 1 at 0, Roof at 35 with no rooms) and its four spot grades at 0, 1 ft
    outside each wall of the 53 by 35 ft outline (revit_build_data.json), with one room drawn over the outline (the
    eval draws none: its egress waits): Level 1 is the first story above or below grade in every world (a one-story
    house: its roof isn't a floor), never the second or the fourth; the Roof isn't a story placed."""
    build = json.loads((ITHACA_RD / "revit_build_data.json").read_text(encoding="utf-8"))
    (x0, y0), (x1, y1) = build["floors"][0]["outline"][0], build["floors"][0]["outline"][2]
    outline = Polygon([(x0 * FT, y0 * FT), (x1 * FT, y0 * FT), (x1 * FT, y1 * FT), (x0 * FT, y1 * FT)])
    levels = [{"id": lv["name"], "name": lv["name"], "elevation": lv["elevation_ft"]} for lv in build["levels"]]
    desc = {"units": "ft", "levels": levels,
            "rooms": [{"id": "r", "name": "House", "level": "Level 1", "floor_elevation": 0}]}
    stories = {}
    for lv in levels:
        s = Story(lv["id"], lv["name"])
        s.outer, s.rooms = outline, ({"r": None} if lv["id"] == "Level 1" else {})
        stories[lv["id"]] = s
    spots = {"spots": [list(p["at"]) for p in build["spot_grades"]]}
    facts = json.loads(json.dumps(__import__("yaml").safe_load(
        (ITHACA_RD / "spreadsheet_design_model_facts.yaml").read_text(encoding="utf-8"))["lot_facts"]))
    for ground in (spots, ground_of(facts)):
        got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, ground)
        assert {k: got["Level 1"]["measures"][k] for k in FACTS} == {FIRST: True, SECOND: False, FOURTH: False}
        assert got["Roof"]["not_measured"][FIRST] == STOPS["place_story_no_rooms"].format(name="Roof")


# --- every reason ---------------------------------------------------------------------------------------------------

def test_ground_of_takes_only_ground_the_architect_stated():
    assert ground_of({"ground_is_flat": True, "grade_elevation": 3}) == {"flat": 3.0}
    assert ground_of({"grade_points": [[0, 0, 1]], "grade_from": "spot"}) == {"spots": [[0, 0, 1]]}
    assert ground_of({}) == {"none": STOPS["no_ground"]}
    assert ground_of({"grade_is": "existing", "grade_points": [[0, 0, 1]]}) == {"none": STOPS["ground_existing"]}
    got = ground_of({"ground_is_flat": True, "grade_elevation": 0, "ground_assumed": "flat"}, "the lot slopes 3 ft")
    assert got == {"none": STOPS["ground_assumed"].format(why="the lot slopes 3 ft")}
    for bad in (True, float("nan"), "0", None):
        assert "none" in ground_of({"ground_is_flat": True, "grade_elevation": bad})


def _reason(got, lid="L0"):
    return got[lid]["not_measured"][FIRST]


def test_each_reason_a_place_isnt_measured():
    seen = set()

    def said(key, reason):
        head = STOPS[key].split("{")[0]
        assert reason.startswith(head), (key, reason)
        seen.add(key)

    said("no_ground", _reason(placed([[0], [10]], ground_of({}))))
    said("ground_existing", ground_of({"grade_is": "existing"})["none"])
    said("ground_assumed", ground_of({"ground_is_flat": True, "grade_elevation": 0, "ground_assumed": "flat"})["none"])
    said("ground_spots_not_read", _reason(placed([[0]], {"spots": [[1, 2]]})))
    said("ground_no_outline", _reason(placed([[0]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS]}, outline=None)))
    said("ground_wall_bare", _reason(placed([[0]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS[:3]]})))
    said("place_story_no_rooms", _reason(placed([[0]], {"flat": 0}, extra_levels=(30,)), "X0"))
    said("place_level_no_rooms", _reason(placed([[0], [20]], {"flat": 0}, extra_levels=(10,))))
    said("place_split_level", _reason(placed([[0, 6], [5]], {"flat": 0})))
    said("place_either", placed([[-4], [6]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS]})["L1"]["not_measured"][FIRST])
    desc, stories = building([[0]])
    desc["rooms"][0]["floor_elevation"] = "low"
    said("place_floor_not_read", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    desc, stories = building([[0]])
    desc["levels"][0]["elevation"] = None
    said("place_level_not_read", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    desc, stories = building([[0]])
    desc["rooms"] = []
    said("place_no_rooms", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    assert seen == PLACE_KEYS


def test_a_level_beyond_the_stories_with_rooms_is_no_gap():
    got = placed([[0], [10]], {"flat": 0}, extra_levels=(-5, 30))
    assert got["L0"]["measures"][FIRST] is True and got["L1"]["measures"][SECOND] is True


def test_a_levels_own_elevation_is_part_of_its_floor():
    """Level 1's rooms at 10 ft but its level at 4 ft (an enclosed space with no room drawn in it stands there):
    Level 0's floor next above may be only 4 ft up, so Level 0 may be a basement and Level 1 the first or second."""
    desc, stories = building([[0], [10]])
    assert places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})["L1"]["measures"][SECOND] is True
    desc["levels"][1]["elevation"] = 4
    got = places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})
    assert SECOND not in got["L1"]["measures"]


def test_a_floor_on_a_threshold_is_either():
    """Level 1's floor next above exactly 6 ft above the grade plane: "more than 6 feet" isn't met, but within 1/16 in
    it could be: never measured on the line."""
    got = placed([[0], [6]], {"flat": 0})
    assert FIRST not in got["L1"]["measures"]
    assert got["L0"]["measures"][FIRST] is True              # the first above, or the first below: either way
