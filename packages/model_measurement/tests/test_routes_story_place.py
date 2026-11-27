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
              "place_level_not_read", "place_split_level", "place_either", "place_either_levels",
              "place_too_many_levels", "ground_buildings_apart", "place_levels_not_all", "place_description",
              "ground_spots_not_finished", "ground_disagrees", "ground_openings_not_read", "ground_disagrees_spots",
              "place_story_spread", "place_level_inside_story", "place_under_lowest", "place_levels_disagree",
              "place_not_a_story_not_read", "place_not_a_story_has_rooms"}    # the level mark: tests at the end


def building(floors, extra_levels=(), outline=BOX, not_stories=False):
    """A description and its stories: `floors` a list of lists of room floor elevations (feet), one per story;
    `not_stories`: the levels with no rooms (`extra_levels`) marked not a story (all_levels[].not_a_story)."""
    levels = [{"id": f"L{i}", "name": f"Level {i}", "elevation": min(f)} for i, f in enumerate(floors)]
    levels += [{"id": f"X{i}", "name": f"Datum {i}", "elevation": z} for i, z in enumerate(extra_levels)]
    rooms = [{"id": f"L{i}r{k}", "name": f"Room {i}.{k}", "level": f"L{i}", "floor_elevation": z}
             for i, f in enumerate(floors) for k, z in enumerate(f)]
    stories = {}
    for lv in levels:
        s = Story(lv["id"], lv["name"])
        s.outer = outline
        s.rooms = {r["id"]: _Room(outline) for r in rooms if r["level"] == lv["id"]}
        stories[lv["id"]] = s
    every = [dict(lv, **({"not_a_story": True} if not_stories and lv["id"].startswith("X") else {})) for lv in levels]
    return {"units": "ft", "levels": levels, "all_levels": every, "rooms": rooms}, stories


class _Room:
    """A room read, as the routes' floor gives it: its outline (here the story's whole floor)."""

    def __init__(self, outline):
        self.outline = outline if outline is not None else BOX


def placed(floors, ground, **kw):
    desc, stories = building(floors, **kw)
    return places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, ground)


# --- the oracle, from the definitions ------------------------------------------------------------------------------

def _worlds(floors, ground):
    """(grade plane, lowest ground at any point, ground along more than half the perimeter or None) in feet."""
    zs = sorted({z for f in floors for z in f})
    marks = {z + d for z in zs for d in (0, -6, -12)} | {0.0}
    near = sorted({m + e for m in marks for e in (-0.01, 0, 0.01)} | {-1000.0})
    if "flat" in ground:                                 # the grade plane at most the flat ground (lower ground beside
        g = ground["flat"]                               # the building, an areaway or a well, may lower it), the flat
        return [(x, m, p) for x in [v for v in near if v <= g] + [g]          # ground a known point of it
                for m in [v for v in near if v <= min(x, g)] + [min(x, g)] for p in (m, None)]
    if "spots" in ground:
        high, low = max(p[2] for p in ground["spots"]), min(p[2] for p in ground["spots"])
        planes = [g for g in near if g <= high] + [high]
        lows = [m for m in near if m <= low] + [low]
    else:
        planes, lows = near, near
    return [(g, m, p) for g in planes for m in lows if m <= g for p in (m, None)]


def _oracle(floors, world, pick):
    """Which stories are above grade plane in one world, `pick` choosing each stepped floor's height for "next
    above"; None for the top story whose floor isn't entirely above (a roof isn't a floor: tried both ways)."""
    g, m, p = world
    above = []
    for i, f in enumerate(floors):
        if min(f) > g:                                           # "finished floor surface entirely above grade plane"
            above.append(True)
            continue
        if i + 1 == len(floors):
            above.append(None)
            continue
        n = pick[i + 1]
        above.append(n > g + 6 or n > m + 12 or (p is not None and n > p + 6))
    return above


UNPLACED = (None, None, None)       # a story under the grade plane above one that is above it: the tables don't say


def _facts_in(above):
    """Each story's (first, second, fourth) from which stories are above grade plane."""
    out = []
    ups = [i for i, a in enumerate(above) if a]
    for i, a in enumerate(above):
        if a:
            n = sum(1 for k in ups if k <= i)
            out.append((n == 1, n == 2, n >= 4))
        elif any(k < i for k in ups):
            out.append(UNPLACED)
        else:
            first_up = min([k for k in ups if k > i], default=len(above))
            out.append((first_up - i == 1, False, False))
    return out


def oracle(floors, ground, extra=()):
    """Every combination of facts the stated ground allows, per story with rooms: [set of (first, second, fourth)].
    `extra`: levels with no rooms (feet): each one, unless at a story's floor, a story nobody drew rooms on or not."""
    seen = [set() for _ in floors]
    if any(min(f) < z < max(f) for z in extra for f in floors):
        return None                                      # a level within a story's floors: may be a story of its own
    extra = [z for z in extra if not any(min(f) <= z <= max(f) for f in floors)]
    for chosen in itertools.product((False, True), repeat=len(extra)):
        stack = sorted([(f, i) for i, f in enumerate(floors)] + [([z], None) for z, on in zip(extra, chosen) if on],
                       key=lambda s: min(s[0]))
        fl = [f for f, _ in stack]
        picks = list(itertools.product(*[sorted(set(f)) for f in fl]))
        for world in _worlds(fl, ground):
            for pick in picks:
                above = _oracle(fl, world, pick)
                for top in ((True, False) if above[-1] is None else (above[-1],)):
                    for (f, i), facts in zip(stack, _facts_in(above[:-1] + [top])):
                        if i is not None:
                            seen[i].add(facts)
    return seen


STACKS = [[[0]], [[0], [10]], [[0], [10], [20], [30]], [[-10], [0], [10], [20], [30]], [[-4], [6], [16]],
          [[-8], [2], [12], [22]], [[-10, -9], [0], [10]], [[0, -0.6], [10, 9.5]], [[-6], [3.5], [14]],
          [[-14], [-4], [6], [16], [26]], [[2], [13]], [[-12], [-2]], [[0], [6], [12], [18], [24]], [[-10], [0]],
          [[-14], [-4], [6]]]
EXTRAS = [(), (0,), (-4,), (35,), (5, 30)]        # levels with no rooms: a garage under, a datum, a roof, a gap
GROUNDS = ([{"flat": z} for z in (-8, -6, -4, -2, -0.5, 0, 0.5, 2, 3.5, 4, 6, 7, 10)]
           + [{"spots": [[x, y, z] for (x, y), z in zip(WALL_SPOTS, zs)]}
              for zs in ((0, 0, 0, 0), (-1, 0, 1, 0), (-6, -2, 0, -4), (2, 2, 4, 3), (-12, 0, 0, -10), (5, 6, 7, 8),
                         (-13, 0, 0, -13), (-14, 0, 0, -10))])


@pytest.mark.parametrize("floors", STACKS, ids=lambda f: "_".join(str(min(x)) for x in f))
def test_every_place_measured_is_the_same_in_every_world_the_ground_stated_allows(floors):
    """The property: a fact measured is the oracle's one value; a fact the oracle can't settle is never measured,
    with or without levels that have no rooms. And flat ground with no such level settles every story whose floors
    are clear of the thresholds, where the lowest one is above the ground (the measuring is no lazier than it must
    be there; a basement is never proven)."""
    for extra in EXTRAS:
        for ground in GROUNDS + [None]:
            got = placed(floors, ground or {"none": "none stated"}, extra_levels=extra)
            seen = oracle(floors, ground or {}, extra)
            for i, lid in enumerate(f"L{k}" for k in range(len(floors))):
                for k, fact in enumerate((FIRST, SECOND, FOURTH)):
                    if seen is None:                         # the oracle can't place it: never measured
                        assert fact not in got[lid]["measures"], (floors, extra, ground, lid, fact)
                        continue
                    values = {s[k] for s in seen[i]}
                    if fact in got[lid]["measures"]:
                        assert values == {got[lid]["measures"][fact]}, (floors, extra, ground, lid, fact, values)
                    else:
                        assert fact in got[lid]["not_measured"], (floors, extra, ground, lid, fact)
            clear = all(len(set(f)) == 1 and all(abs(f[0] - ground["flat"] - d) > 0.1 for d in (0, 6))
                        for f in floors) if ground and "flat" in ground else False
            # a story is never proven a basement: flat ground settles a stack whose lowest story is above it
            if clear and not extra and ground["flat"] < floors[0][0] <= ground["flat"] + 6:   # (higher: a story may
                # stand under the lowest level, with no level of its own)       # a top story at or below grade has no
                assert all(f in got[f"L{i}"]["measures"]                    # floor above to test
                           for i in range(len(floors) - 1) for f in FACTS), (floors, ground)


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


def _apartment_places(ground, every=True):
    """The apartment as Revit sent it, with every level listed (`all_levels`, as the reader sends it since this PR:
    the recorded request predates it; its two levels are all it has)."""
    interior = json.loads(APARTMENT.read_text(encoding="utf-8"))["interior"]
    if every:
        interior["all_levels"] = [dict(lv) for lv in interior["levels"]]
    got = measure(interior, ground=ground)
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


def test_the_four_unit_apartment_on_ground_5_ft_up():
    """Ground stated flat at 5 ft: Level 1's floor at 0 is under it and its floor next above (10 ft) only 5 ft over
    it; whether ground beside it is lower somewhere (its stair doors out are at 0: an areaway) the model can't rule
    out, and a basement is never proven. Level 1 is the first story above or below either way; Level 2 the first or
    the second: not placed."""
    s = _apartment_places({"flat": 5.0})
    assert s["Level 1"]["measures"][FIRST] is True
    assert FIRST not in s["Level 2"]["measures"] and SECOND not in s["Level 2"]["measures"]


def test_106_ithaca_rd_its_levels_and_spot_grades():
    """The Revit eval's own levels (Level 1 at 0, Roof at 35 with no rooms) and its four spot grades at 0, 1 ft
    outside each wall of the 53 by 35 ft outline (revit_build_data.json), with one room drawn over the outline (the
    eval draws none: its egress waits): Level 1 is the first story above or below grade in every world (a one-story
    house: its roof isn't a floor; the Roof level, sent only in all_levels, tried as a story and not), never the
    second or the fourth."""
    build = json.loads((ITHACA_RD / "revit_build_data.json").read_text(encoding="utf-8"))
    (x0, y0), (x1, y1) = build["floors"][0]["outline"][0], build["floors"][0]["outline"][2]
    outline = Polygon([(x0 * FT, y0 * FT), (x1 * FT, y0 * FT), (x1 * FT, y1 * FT), (x0 * FT, y1 * FT)])
    every = [{"id": lv["name"], "name": lv["name"], "elevation": lv["elevation_ft"]} for lv in build["levels"]]
    levels = every[:1]                    # the reader sends in levels only a level with something drawn on it
    desc = {"units": "ft", "levels": levels, "all_levels": every,
            "rooms": [{"id": "r", "name": "House", "level": "Level 1", "floor_elevation": 0}]}
    s = Story("Level 1", "Level 1")
    s.outer, s.rooms = outline, {"r": None}
    stories = {"Level 1": s}
    spots = {"spots": [list(p["at"]) for p in build["spot_grades"]]}
    facts = json.loads(json.dumps(__import__("yaml").safe_load(
        (ITHACA_RD / "spreadsheet_design_model_facts.yaml").read_text(encoding="utf-8"))["lot_facts"]))
    for ground in (spots, ground_of(facts)):
        got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, ground)
        assert {k: got["Level 1"]["measures"][k] for k in FACTS} == {FIRST: True, SECOND: False, FOURTH: False}
        assert got["Level 1"]["more"]["story_place"]["levels_maybe_stories"] == ["Roof"]


# --- every reason ---------------------------------------------------------------------------------------------------

def test_ground_of_takes_only_ground_the_architect_stated():
    assert ground_of({"ground_is_flat": True, "grade_elevation": 3}) == {"flat": 3.0}
    assert ground_of({"grade_points": [[0, 0, 1]], "grade_from": "finished_spots"}) == {"spots": [[0, 0, 1]]}
    assert ground_of({"grade_points": [[0, 0, 1]], "grade_is": "finished"}) == {"spots": [[0, 0, 1]]}
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
    said("ground_spots_not_finished", ground_of({"grade_points": [[0, 0, 1]]})["none"])
    desc, stories = building([[0], [10]])
    desc["openings"] = [{"id": "w", "ground_outside": 2}]
    said("ground_disagrees", _reason(places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})))
    desc["openings"] = [{"id": "w", "ground_outside": "low"}]
    said("ground_openings_not_read", _reason(places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})))
    spots = {"spots": [[x, y, 0] for x, y in WALL_SPOTS]}
    said("ground_openings_not_read", _reason(places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, spots)))
    desc["openings"] = [{"id": "w", "ground_outside": 7}]
    said("ground_disagrees_spots", _reason(places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, spots)))
    said("ground_assumed", ground_of({"ground_is_flat": True, "grade_elevation": 0, "ground_assumed": "flat"})["none"])
    said("ground_spots_not_read", _reason(placed([[0]], {"spots": [[1, 2]]})))
    said("ground_no_outline", _reason(placed([[0]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS]}, outline=None)))
    said("ground_wall_bare", _reason(placed([[0]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS[:3]]})))
    said("place_story_no_rooms", _reason(placed([[0]], {"flat": 0}, extra_levels=(30,)), "X0"))
    said("place_either_levels", _reason(placed([[10], [20]], {"flat": 0}, extra_levels=(0,))))
    desc, stories = building([[0]])
    del desc["all_levels"]
    said("place_levels_not_all", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    desc, stories = building([[0]])
    said("place_description", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0},
                                             ["the room R is on level 'L9', not one of the model's levels"])))
    said("place_too_many_levels", _reason(placed([[0]], {"flat": 0}, extra_levels=tuple(range(10, 100, 10)))))
    two = BOX.union(Polygon([(60 * FT, 0), (80 * FT, 0), (80 * FT, 20 * FT), (60 * FT, 20 * FT)]))
    said("ground_buildings_apart", _reason(placed([[0]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS]}, outline=two)))
    said("place_split_level", _reason(placed([[0, 3], [2]], {"flat": 0})))
    said("place_story_spread", _reason(placed([[0, 12], [24]], {"flat": 0})))
    said("place_under_lowest", _reason(placed([[0], [10], [20]], {"flat": -10})))
    said("place_level_inside_story", _reason(placed([[0, 3], [10]], {"flat": 0}, extra_levels=(1.5,))))
    said("place_either", placed([[-4], [6]], {"spots": [[x, y, 0] for x, y in WALL_SPOTS]})["L1"]["not_measured"][FIRST])
    desc, stories = building([[0]])
    desc["rooms"][0]["floor_elevation"] = "low"
    said("place_floor_not_read", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    desc, stories = building([[0]])
    desc["all_levels"][0]["elevation"] = None
    said("place_level_not_read", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    desc, stories = building([[0]])
    desc["rooms"] = []
    said("place_no_rooms", _reason(places(desc, Reader("ft"), {"L0": "Level 0"}, stories, {"flat": 0})))
    seen |= {"place_not_a_story_not_read", "place_not_a_story_has_rooms"}    # the level mark's tests at the end
    desc, stories = building([[-20], [1]])
    desc["levels"][1]["elevation"] = -1                # the stories' levels say -1 ft, every level's list 1 ft
    said("place_levels_disagree", _reason(places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})))
    assert seen == PLACE_KEYS


def test_a_level_beyond_the_stories_with_rooms_is_no_gap():
    got = placed([[0], [10]], {"flat": 0}, extra_levels=(30, 45))
    assert got["L0"]["measures"][FIRST] is True and got["L1"]["measures"][SECOND] is True


def test_a_levels_own_elevation_is_part_of_its_floor():
    """Level 1's rooms at 10 ft but its level at 4 ft (an enclosed space with no room drawn in it stands there):
    Level 0's floor next above may be only 4 ft up, so Level 0 may be a basement and Level 1 the first or second."""
    desc, stories = building([[0], [10]])
    assert places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})["L1"]["measures"][SECOND] is True
    desc["levels"][1]["elevation"] = desc["all_levels"][1]["elevation"] = 4
    got = places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})
    assert SECOND not in got["L1"]["measures"]


def test_a_floor_on_a_threshold_is_either():
    """Level 1's floor next above exactly 6 ft above the grade plane: "more than 6 feet" isn't met, but within 1/16 in
    it could be: never measured on the line."""
    got = placed([[0], [6]], {"flat": 0})
    assert FIRST not in got["L1"]["measures"]
    assert got["L0"]["measures"][FIRST] is True              # the first above, or the first below: either way


# --- review round 1 (2026-11-25): each finding's pin --------------------------------------------------------------

def test_a_level_with_no_rooms_under_the_lowest_story_may_be_a_story():
    """A garage or lobby level with no rooms drawn, at 0 on flat ground at 0, under rooms at 10 and 20: if it is a
    story, the rooms' levels are the second and third. Before, it was ignored and Level 0 measured the first (a
    false pass for Group A's one exit on a second story)."""
    got = placed([[10], [20]], {"flat": 0}, extra_levels=(0,))
    assert FIRST not in got["L0"]["measures"] and SECOND not in got["L1"]["measures"]
    assert "Datum 0" in got["L0"]["not_measured"][FIRST]


def test_a_datum_under_the_slab_may_be_a_story():
    """A level with no rooms 4 ft under a slab on flat ground: if it is a story, a basement is never proven, so it
    may be the first story above grade plane, and the slab's story the second: neither the slab's place nor the
    one above it is placed. (A level the architect marks as no story settles it: the level mark's tests at the end.)"""
    got = placed([[0], [10]], {"flat": 0}, extra_levels=(-4,))
    assert FIRST not in got["L0"]["measures"] and SECOND not in got["L1"]["measures"]
    assert placed([[0], [10]], {"flat": 0})["L1"]["measures"][SECOND] is True       # with no such level


def test_the_top_story_under_the_grade_plane_is_never_placed_above_it():
    """A walk-out on a slope: spots at -13 ft and 0 ft, floors at -10 and 0. Level 0 is above grade plane by item 2
    (its floor above is more than 12 ft over the low spot); Level 1, the top, has no floor above, and its floor may
    be under the grade plane (at 0): it isn't the second story above for certain. Before, it was measured so."""
    spots = {"spots": [[20, -1, -13], [41, 15, 0], [20, 31, 0], [-1, 15, -13]]}
    got = placed([[-10], [0]], spots)
    assert SECOND not in got["L1"]["measures"] and FIRST not in got["L1"]["measures"]


def test_a_spot_grade_inside_the_building_is_not_ground_beside_it():
    """A spot 1.5 ft inside the south wall at -26 ft was taken as finished ground (item 2's known point), making a
    deep basement the first story above."""
    walls = [[x, y, 0] for x, y in WALL_SPOTS]
    without = placed([[-14], [-4], [6]], {"spots": walls})
    with_inside = placed([[-14], [-4], [6]], {"spots": walls + [[20, 1.5, -26]]})
    for lid in ("L0", "L1", "L2"):
        assert with_inside[lid]["measures"] == without[lid]["measures"], lid
    assert FIRST not in with_inside["L0"]["measures"]


def test_two_buildings_never_share_their_ground():
    """Two separate outlines (building B's spots far lower): never placed."""
    two = BOX.union(Polygon([(60 * FT, 0), (80 * FT, 0), (80 * FT, 20 * FT), (60 * FT, 20 * FT)]))
    spots = [[x, y, 0] for x, y in WALL_SPOTS] + [[70, -1, -13], [81, 10, -13], [70, 21, -13], [59, 10, -13]]
    got = placed([[-4], [6]], {"spots": spots}, outline=two)
    assert not set(FACTS) & set(got["L0"]["measures"])
    assert got["L0"]["not_measured"][FIRST] == STOPS["ground_buildings_apart"].format(count=2)


def test_a_courtyards_walls_need_spots_too():
    """A courtyard (an inner ring of the outline) is ground adjoining exterior walls: with no spot in it, the grade
    plane isn't known (its ground could be higher than every spot outside)."""
    ring = BOX.difference(Polygon([(15 * FT, 10 * FT), (25 * FT, 10 * FT), (25 * FT, 20 * FT), (15 * FT, 20 * FT)]))
    spots = [[x, y, 0] for x, y in WALL_SPOTS]
    assert _reason(placed([[0], [10]], {"spots": spots}, outline=ring)) == STOPS["ground_wall_bare"].format(count=8)
    court = spots + [[20, 11, 0], [24, 15, 0], [20, 19, 0], [16, 15, 0]]
    assert placed([[0], [10]], {"spots": court}, outline=ring)["L1"]["measures"][SECOND] is True


# --- review round 2 (2026-11-25): each finding's pin --------------------------------------------------------------

def test_a_story_with_nothing_drawn_is_never_missing():
    """The Revit reader sent only levels with something drawn on them: an open parking story at 0 under the apartment
    (its first rooms at 10 ft) never arrived, and the rooms' level measured the first story above. Now every level
    is listed (all_levels, RouteReader.cs) and, without that list, nothing is placed."""
    desc, stories = building([[10], [20]], extra_levels=(0,))
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert FIRST not in got["L0"]["measures"]
    del desc["all_levels"]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert not set(FACTS) & set(got["L0"]["measures"])
    s = _apartment_places({"flat": 0.0}, every=False)
    assert s["Level 2"]["not_measured"][SECOND] == STOPS["place_levels_not_all"]


def _overhang(spots):
    """B at -10 ft and G at 0 ft, 40 by 30 ft; U at 8 ft, 60 by 40 ft, overhanging 10 ft north, east and west."""
    small = BOX
    big = Polygon([(-10 * FT, 0), (50 * FT, 0), (50 * FT, 40 * FT), (-10 * FT, 40 * FT)])
    desc, stories = building([[-10], [0], [8]])
    stories["L2"].outer = big
    return places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"spots": spots}), small


def test_spots_at_the_ground_floors_walls_under_an_overhang_count():
    """Ground 8 ft up at the ground floor's north, east and west walls (under the overhang) and 0 at the overhang's
    edges: the grade plane may be well above 0, so G may be a basement and B the second story below. Before, the
    spots under the overhang fell inside the outlines' union and were dropped: B measured the first."""
    spots = [[20, -1, 0], [41, 15, 8], [20, 31, 8], [-1, 15, 8],                  # 1 ft outside G's walls
             [20, 41, 0], [51, 20, 0], [-11, 20, 0], [45, -1, 0], [-5, -1, 0]]    # outside the overhang's edges
    got, _ = _overhang(spots)
    assert FIRST not in got["L0"]["measures"]
    assert got["L0"]["more"]["story_place"]["grade_plane_top_ft"] == 8


def test_a_low_spot_is_never_item_2s_ground_at_any_point():
    """A spot 2 ft out at -13 ft (it may stand in an areaway): it no longer proves the story at -10 above grade plane
    by item 2, so the story at -20 isn't measured the first below (open question 4.6)."""
    spots = [[x, y, 0] for x, y in WALL_SPOTS] + [[10, -2, -13]]
    got = placed([[-20], [-10], [0], [10]], {"spots": spots})
    assert FIRST not in got["L0"]["measures"]


def test_a_room_on_no_level_read_places_nothing():
    """measure(): the apartment with Level 1 left out of levels (its rooms on a level not read): nothing placed."""
    interior = json.loads(APARTMENT.read_text(encoding="utf-8"))["interior"]
    interior["all_levels"] = [dict(lv) for lv in interior["levels"]][1:]
    interior["levels"] = interior["levels"][1:]
    got = measure(interior, ground={"flat": 0.0})
    for s in got["parts"]["story"]:
        assert not set(FACTS) & set(s["measures"]), s["name"]


# --- review round 3 (2026-11-25): each finding's pin --------------------------------------------------------------

@pytest.mark.parametrize("opening", [{"id": "w", "ground_outside": -8},
                                     {"id": "w", "ground_outside": [0, -8]},
                                     {"id": "w", "ground_outside": 0, "area_well": {"floor_elevation": -8}}])
def test_lower_ground_at_an_opening_never_proves_a_basement_on_flat_ground(opening):
    """Flat ground at 0 but finished ground 8 ft down at a window (or a well's floor): Level 1's floor at 5 ft is more
    than 12 ft over that point (item 2), so Level 0 may be a story above grade plane. Before, Level 0 was proven a
    basement and Level 2 the second story (a one-exit Group B story passing where the third is Not Permitted)."""
    desc, stories = building([[-8], [5], [15]])
    desc["openings"] = [opening]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert FIRST not in got["L1"]["measures"] and SECOND not in got["L2"]["measures"]


def test_revits_plain_spot_grades_are_existing_ground():
    """Revit's "Spot grades" (grade_from spot, no grade_is) are the existing ground, as Rhino's Grade layer: fill
    could make the stories over them basements. Only finished spot grades place a story."""
    spots = [[x, y, 0] for x, y in WALL_SPOTS]
    assert "none" in ground_of({"grade_from": "spot", "grade_points": spots})
    assert "none" in ground_of({"grade_points": spots})
    assert ground_of({"grade_from": "finished_spots", "grade_points": spots}) == {"spots": spots}


# --- review round 4 (2026-11-25) ----------------------------------------------------------------------------------

def test_spot_grades_never_bound_the_grade_plane_below_finished_ground_stated_higher():
    """Spots at 0 at every wall but finished ground stated 7 ft up at a window: the grade plane may be well above the
    highest spot (here 5 ft), making Level 0 the second story below. Before, Level 0 measured the first."""
    desc, stories = building([[-12], [-2], [8]])
    desc["openings"] = [{"id": "w", "ground_outside": 7}]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories,
                 {"spots": [[x, y, 0] for x, y in WALL_SPOTS]})
    assert FIRST not in got["L0"]["measures"]
    assert got["L0"]["not_measured"][FIRST] == STOPS["ground_disagrees_spots"].format(high="0 ft", stated="7 ft")


# --- review round 5 (2026-11-25) ----------------------------------------------------------------------------------

def test_an_upper_story_drawn_on_a_lower_level_is_never_one_story():
    """Rooms at 0 and 12 ft on Level 0 (the second story's drawn there with an offset): before, one story, so the
    story at 36 ft measured not the fourth (a one-exit R-2 story passing). Now nothing is placed."""
    got = placed([[0, 12], [24], [36]], {"flat": 0}, extra_levels=(12,))
    assert FOURTH not in got["L2"]["measures"]
    got = placed([[0, 3], [10]], {"flat": 0}, extra_levels=(1.5,))
    assert not set(FACTS) & set(got["L0"]["measures"])


def test_a_higher_spot_farther_from_the_walls_raises_the_grade_planes_top_end():
    """Spots 100 ft at every wall but 120 ft 10 ft out: the ground between them may rise to 120 ft along the walls
    (Gordium's reading), so the grade plane may be about 110 ft. Before, its top end was 100 ft and the story at 86 ft
    measured the first below."""
    outline = Polygon([(0, 0), (100 * FT, 0), (100 * FT, 20 * FT), (0, 20 * FT)])
    spots = [[1, -1, 100], [101, 21, 100], [50, -1, 100], [50, 21, 100], [-1, 10, 100], [101, 10, 100],
             [50, -10, 120], [50, 30, 120]]
    got = placed([[86], [96], [107]], {"spots": spots}, outline=outline)
    assert FIRST not in got["L0"]["measures"]
    assert got["L0"]["more"]["story_place"]["grade_plane_top_ft"] == 120


@pytest.mark.parametrize("what", ["door", "stair"])
def test_a_walk_out_door_or_a_stairs_foot_under_flat_ground_proves_no_basement(what):
    """Flat ground at 0, a room at -9 ft with a door to the outside (or a stair whose foot is at -9 ft): the ground
    there may be as low as the floor (an areaway: question 4.6), so the story at -9 may be above grade plane by
    item 2 and the one at 4 ft the second."""
    desc, stories = building([[-9], [4]])
    if what == "door":
        desc["doors"] = [{"id": "d", "sides": ["L0r0", "outside"]}]
    else:
        desc["stairs"] = [{"id": "s", "bottom_elevation": -9}]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert FIRST not in got["L1"]["measures"] and SECOND not in got["L1"]["measures"]


# --- review round 6 (2026-11-25): a basement is never proven ------------------------------------------------------

@pytest.mark.parametrize("case", ["sill", "space_door", "double_height"])
def test_no_basement_is_proven_on_flat_ground(case):
    """Round 6's three ways the model can hold ground below the stated flat ground or a floor next above higher than
    the next story's: a window sill under the ground with no well given, a door to the outside from an enclosed space
    with no room, a double-height room over the story. Each "proved" a basement and measured a real fourth story not
    the fourth. Now no basement is proven at all."""
    desc, stories = building([[-11], [1.5], [11.5], [21.5], [31.5]])
    if case == "sill":
        desc["openings"] = [{"id": "w", "room": "L0r0", "frame": {"left": 0, "right": 3, "bottom": -10, "top": -7}}]
    elif case == "space_door":
        desc["unknown_spaces"] = [{"id": "u1", "level": "L0"}]
        desc["doors"] = [{"id": "d1", "level": "L0", "sides": ["u1", "outside"]}]
    else:
        desc["rooms"][0]["ceiling_height"] = 25
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert FOURTH not in got["L3"]["measures"] and FIRST not in got["L1"]["measures"]


# --- review round 7 (2026-11-25) ----------------------------------------------------------------------------------

def test_a_spot_under_an_overhang_far_from_the_walls_raises_the_top_end():
    """Spots at 4 ft under the overhang, 5 ft from the ground floor's walls: outside the building at ground level, but
    dropped from the grade plane's top end (left at 0), so Level 0 measured the first story below. Every finished spot
    counts now."""
    spots = [[20, -1, 0], [41, 1, 0], [1, 31, 0], [-1, 1, 0], [39, 31, 0],
             [20, 41, 0], [51, 20, 0], [-11, 20, 0], [45, -1, 0], [-5, -1, 0],
             [45, 15, 4], [20, 35, 4], [-5, 15, 4]]
    got, _ = _overhang(spots)
    assert FIRST not in got["L0"]["measures"]
    assert got["L0"]["more"]["story_place"]["grade_plane_top_ft"] == 4


def test_a_mezzanine_drawn_on_its_own_level_never_proves_the_story_below_above():
    """A small level at 7 ft over a story at -1 ft and a basement at -10 ft, flat ground at 0: as a story, its floor
    is the floor next above (more than 6 ft over the grade plane, item 1) and proved the -1 ft story above; as a
    mezzanine (505.2: part of the story below) it isn't, and the -1 ft story's own floor leaves it open. Tried both
    ways; a possible mezzanine is never placed itself."""
    desc, stories = building([[-10], [-1], [7]])
    stories["L2"].rooms = {k: _Room(Polygon([(0, 0), (10 * FT, 0), (10 * FT, 10 * FT), (0, 10 * FT)]))
                           for k in stories["L2"].rooms}             # its own outline the building's: within the walls
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert FIRST not in got["L0"]["measures"]
    assert not set(FACTS) & set(got["L2"]["measures"])
    assert got["L0"]["more"]["story_place"]["levels_maybe_mezzanines"] == ["Level 2"]


# --- review round 8 (2026-11-26) ----------------------------------------------------------------------------------

def test_the_story_under_a_possible_mezzanine_is_never_placed():
    """A level at 10 ft half the size of the one at 0: possibly its mezzanine, whose occupants would then be the lower
    story's (505.2), so the lower story's one-exit row could pass on too few occupants. Neither is placed."""
    desc, stories = building([[0], [10]])
    stories["L1"].rooms = {k: _Room(Polygon([(0, 0), (20 * FT, 0), (20 * FT, 30 * FT), (0, 30 * FT)]))
                           for k in stories["L1"].rooms}
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert not set(FACTS) & set(got["L0"]["measures"]) and not set(FACTS) & set(got["L1"]["measures"])


@pytest.mark.parametrize("ground", [{"flat": -10}, {"spots": [[x, y, -10] for x, y in WALL_SPOTS]}])
def test_a_story_may_stand_under_the_lowest_level(ground):
    """The lowest level 10 ft over the ground: an undercroft drawn from Level 0 with an offset (no level of its own)
    would be the first story above grade plane and Level 1 the third. Nothing is placed."""
    got = placed([[0], [10], [20]], ground)
    assert not set(FACTS) & set(got["L0"]["measures"]) and not set(FACTS) & set(got["L1"]["measures"])


# --- review round 9 (2026-11-26) ----------------------------------------------------------------------------------

def test_ground_under_an_overhang_counts_toward_the_lowest_ground():
    """The ground floor's walls at 0 under the overhang, 2 ft beyond its edges, the ground floor at 7 ft: more than 6 ft
    over the ground at its own walls (a story may stand under it). Before, the spots under the overhang were left out
    of the lowest ground (2 ft) and the ground floor measured the first story above."""
    small, big = BOX, Polygon([(-10 * FT, 0), (50 * FT, 0), (50 * FT, 40 * FT), (-10 * FT, 40 * FT)])
    desc, stories = building([[7], [17]])
    stories["L1"].outer = big
    spots = [[20, -1, 2], [41, 15, 0], [20, 31, 0], [-1, 15, 0], [20, 41, 2], [51, 20, 2], [-11, 20, 2], [45, -1, 2],
             [-5, -1, 2]]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"spots": spots})
    assert not set(FACTS) & set(got["L0"]["measures"])
    assert got["L0"]["not_measured"][FIRST] == STOPS["place_under_lowest"].format(gap="7 ft")


def test_a_possible_mezzanine_is_said_so():
    """The reason a story under a possible mezzanine isn't placed names the mezzanine, never "levels with no rooms"."""
    desc, stories = building([[20], [30]])
    stories["L1"].rooms = {k: _Room(Polygon([(0, 0), (20 * FT, 0), (20 * FT, 30 * FT), (0, 30 * FT)]))
                           for k in stories["L1"].rooms}
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 18})
    assert "mezzanine" in got["L0"]["not_measured"][FIRST]
    assert "levels with no rooms" not in got["L0"]["not_measured"][FIRST]
    assert "Gordium's reading: a story stands where the model has a level" in \
        got["L0"]["more"]["story_place"]["levels_reading"]


# --- review round 10 (2026-11-26) ---------------------------------------------------------------------------------

def test_a_mezzanine_within_the_buildings_walls_is_judged_by_its_rooms():
    """A mezzanine's level outline is the building's own (it stands within the exterior walls), so the outline test
    never flagged it: judged by its rooms' area now, and a level whose rooms aren't read may be one."""
    desc, stories = building([[-10], [-1], [7]])
    stories["L2"].rooms = {k: _Room(Polygon([(0, 0), (10 * FT, 0), (10 * FT, 10 * FT), (0, 10 * FT)]))
                           for k in stories["L2"].rooms}
    assert stories["L2"].outer == stories["L1"].outer
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert FIRST not in got["L0"]["measures"] and got["L0"]["more"]["story_place"]["levels_maybe_mezzanines"] == \
        ["Level 2"]
    stories["L2"].rooms = {k: None for k in stories["L2"].rooms}
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert got["L0"]["more"]["story_place"]["levels_maybe_mezzanines"] == ["Level 2"]


@pytest.mark.parametrize("ground", [{"flat": 0}, {"spots": [[x, y, 0] for x, y in WALL_SPOTS]}])
@pytest.mark.parametrize("opening", [{"id": "w1", "ground_outside": -3},
                                     {"id": "w1", "ground_outside": 0, "area_well": {"floor_elevation": -3}}])
def test_lower_ground_stated_at_an_opening_is_the_lowest_ground(ground, opening):
    """The lowest level 8 ft over ground stated at a window (or a well's floor): a story may stand under it."""
    desc, stories = building([[5], [15]])
    desc["openings"] = [opening]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, ground)
    assert not set(FACTS) & set(got["L0"]["measures"]) and not set(FACTS) & set(got["L1"]["measures"])
    assert got["L0"]["not_measured"][FIRST] == STOPS["place_under_lowest"].format(gap="8 ft")


# --- the level mark "not a story" (Gordium: Not a story, all_levels[].not_a_story) ----------------------------------

@pytest.mark.parametrize("floors", STACKS, ids=lambda f: "_".join(str(min(x)) for x in f))
def test_levels_marked_not_a_story_place_as_if_they_werent_there(floors):
    """Every stack, every set of levels with no rooms (a garage under, a datum, a roof, a gap, one within a story's
    floors), every ground: marked not a story, each place measured is exactly the one measured with those levels
    gone (which the walk above checks against the oracle), and nothing more: never tried as a story, never a gap."""
    for extra in EXTRAS + [(1.5,)]:
        for ground in GROUNDS + [None]:
            g = ground or {"none": "none stated"}
            got, alone = placed(floors, g, extra_levels=extra, not_stories=True), placed(floors, g)
            for lid in (f"L{k}" for k in range(len(floors))):
                assert got[lid]["measures"] == alone[lid]["measures"], (floors, extra, ground, lid)
                if extra and got[lid]["measures"]:
                    assert got[lid]["more"]["story_place"]["levels_not_stories"] == \
                        sorted(f"Datum {i}" for i in range(len(extra)))


def test_a_datum_marked_not_a_story_settles_the_slab_and_the_story_above():
    """The case step 1 left for this mark: a datum 4 ft under a slab on flat ground unsettled both stories (it may be
    a story); marked not a story, the slab is the first story above grade plane and the next the second. Unmarked,
    or marked false or null, it is still tried both ways."""
    got = placed([[0], [10]], {"flat": 0}, extra_levels=(-4,), not_stories=True)
    assert got["L0"]["measures"][FIRST] is True and got["L1"]["measures"][SECOND] is True
    for said in (False, None):
        desc, stories = building([[0], [10]], extra_levels=(-4,))
        desc["all_levels"][-1]["not_a_story"] = said
        got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
        assert FIRST not in got["L0"]["measures"] and SECOND not in got["L1"]["measures"], said


@pytest.mark.parametrize("said", ["yes", 1, 0, [True], "true"])
def test_a_not_a_story_mark_that_isnt_true_or_false_places_nothing(said):
    desc, stories = building([[0], [10]], extra_levels=(-4,))
    desc["all_levels"][-1]["not_a_story"] = said
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert not got["L0"]["measures"] and not got["L1"]["measures"]
    assert _reason(got).startswith(STOPS["place_not_a_story_not_read"].split("{")[0]), said


@pytest.mark.parametrize("what", ["rooms", "space"])
def test_a_level_marked_not_a_story_with_rooms_or_a_space_on_it_places_nothing(what):
    """The mark and the drawing disagree: rooms drawn on the level, or an enclosed space with no room (a room nobody
    drew) on it. Which is right isn't known, so no story is placed."""
    if what == "rooms":
        desc, stories = building([[0], [10]])
        desc["all_levels"][1]["not_a_story"] = True
    else:
        desc, stories = building([[0], [10]], extra_levels=(20,), not_stories=True)
        desc["unknown_spaces"] = [{"id": "u", "level": "X0", "outline": []}]
    got = places(desc, Reader("ft"), {k: s.name for k, s in stories.items()}, stories, {"flat": 0})
    assert not got["L0"]["measures"] and not got["L1"]["measures"]
    assert _reason(got).startswith(STOPS["place_not_a_story_has_rooms"].split("{")[0]), what


@pytest.mark.parametrize("openings", [5, True, {"w": {"id": "w", "ground_outside": 2}}, [[{"id": "w", "ground_outside": 2}]],
                                      [{"id": "w", "ground_outside": 2}, "x"]])
def test_openings_that_arent_a_list_of_openings_leave_the_place_not_known(openings):
    """Cold review of the room-id fix: openings given as a number, a mapping, or with an entry that isn't an opening
    can't be read for the ground beside them: the stories' places are not measured, never measured past a ground
    stated higher at an opening, and never a crash."""
    desc, stories = building([[0], [10]])
    desc["openings"] = openings
    got = places(desc, Reader("ft"), {"L0": "", "L1": ""}, stories, {"flat": 0})
    assert FIRST not in got["L0"]["measures"]
    assert _reason(got).startswith(STOPS["ground_openings_not_read"].split("{")[0])


@pytest.mark.parametrize("well", [5, "deep", [-2], {}, {"floor_elevation": None}, {"width": 40}])
def test_an_area_well_whose_floor_cant_be_read_leaves_the_place_not_known(well):
    """Cold round 2 of the room-id fix: an area well given at an opening is the lowest ground there; one whose floor
    can't be read leaves the stories' places not measured, never placed as if there were no well."""
    desc, stories = building([[5]])
    desc["openings"] = [{"id": "w", "area_well": well}]
    got = places(desc, Reader("ft"), {"L0": ""}, stories, {"flat": 0})
    assert FIRST not in got["L0"]["measures"]
    assert _reason(got).startswith(STOPS["ground_openings_not_read"].split("{")[0])

