"""Whether a story's rooms exit directly outside (BCNYS 1006.3.4 item 2, p.317: "Rooms, areas and spaces complying
with Section 1006.2.1 with exits that discharge directly to the exterior at the level of exit discharge, are
permitted to have one exit or access to a single exit"), worked out from the model: routes.rooms_exit_outside.

The property walk: a row of three rooms along an outside wall, each with a door to the outside marked as an exterior
exit door at discharge, one not marked, one onto an exterior stair, or none, and each pair either walled (a door
between them, or none) or open (a passage). The oracle, from item 2's words: a room or open area with its own exit
straight outside qualifies; the story relies on item 2 only if every one does (yes), cannot if one has no door
outside at all (no), and isn't known where a door outside isn't marked (an exit is marked, never guessed) or the
story's routes aren't read."""

import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from routes_layouts import description, door, rect, room  # noqa: E402

from model_measurement.routes import OUTSIDE_FACT, measure  # noqa: E402
from model_measurement.routes.stops import STOPS  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
OUTSIDE_KEYS = {"outside_no_rooms", "outside_door_not_marked"}
KINDS = ("marked", "unmarked", "stair", "none")
SIDES = ("door", "passage", "wall")


def row(kinds, joins, uses=("other", "other", "other")):
    """Three 10 by 10 ft rooms side by side (x 0-10, 10.5-20.5, 21-31; a 6 in wall between), each door to the
    outside on the south wall (y = -0.25), `joins` between rooms 0-1 and 1-2 (a door, a passage with no wall: then
    the rooms touch, or a plain wall)."""
    rooms, doors, passages, x = [], [], [], 0.0
    xs = []
    for i, (kind, use) in enumerate(zip(kinds, uses)):
        x0 = x
        x1 = x0 + 10
        xs.append((x0, x1))
        rooms.append(room(f"r{i}", rect(x0, 0, x1, 10), use=use, lockable=False, pass_through=use == "corridor"))
        if kind != "none":
            d = door(f"o{i}", ((x0 + x1) / 2, -0.25), (1, 0), (f"r{i}", "outside"),
                     exit_id=None if kind == "unmarked" else f"o{i}",
                     kind="exterior_stair_or_ramp" if kind == "stair" else "exterior_at_discharge")
            doors.append(d)
        x = x1 + (0.5 if i < 2 and joins[i] != "passage" else 0)
    for i, j in enumerate(joins):
        if j == "door":
            doors.append(door(f"d{i}", (xs[i][1] + 0.25, 5), (0, 1), (f"r{i}", f"r{i + 1}")))
        elif j == "passage":
            passages.append(((f"r{i}", f"r{i + 1}"), [(xs[i][1], 0), (xs[i][1], 10)]))
    desc = description(rooms, doors, passages)
    desc["story_outlines"] = [{"level": "L1", "outer": [[-0.5, -0.5], [x + 0.5, -0.5], [x + 0.5, 10.5], [-0.5, 10.5]],
                               "inner": [[0, 0], [x, 0], [x, 10], [0, 10]]}]
    return desc


def _story(desc):
    return measure(desc)["parts"]["story"][0]


def oracle(kinds, joins):
    """True, False, or None (not known), from item 2's words, for a story whose rooms are all occupied spaces."""
    if "stair" in kinds:                                 # travel along an exterior stair isn't read: the story isn't
        return None
    if "marked" not in kinds:                            # no exit marked on the story: its routes aren't read
        return None
    areas, cur = [], [0]
    for i, j in enumerate(joins):
        if j == "passage":
            cur.append(i + 1)
        else:
            areas.append(cur)
            cur = [i + 1]
    areas.append(cur)
    has = [{kinds[i] for i in a} for a in areas]
    if any(h <= {"none"} for h in has):
        return False
    if all("marked" in h for h in has):
        return True
    return None


@pytest.mark.parametrize("joins", list(itertools.product(SIDES, repeat=2)), ids="-".join)
def test_the_walk_every_value_measured_is_the_oracles_and_every_other_needs_review(joins):
    seen = set()
    for kinds in itertools.product(KINDS, repeat=3):
        sp = _story(row(kinds, joins))
        want = oracle(kinds, joins)
        seen.add(sp["measures"].get(OUTSIDE_FACT))
        if want is None:
            assert OUTSIDE_FACT not in sp["measures"], (kinds, joins, sp["measures"].get(OUTSIDE_FACT))
            assert OUTSIDE_FACT in sp["not_measured"], (kinds, joins)
        else:
            assert sp["measures"].get(OUTSIDE_FACT) is want, (kinds, joins, sp["not_measured"].get(OUTSIDE_FACT))
    assert True in seen and (False in seen or joins == ("passage", "passage")), seen     # never vacuous


def test_a_closet_its_room_serves_is_part_of_that_room():
    """A closet opening only into room 0 (its door the closet's only one): taken as part of room 0, which has its own
    exit outside, so the story still relies on item 2; the same closet given its own use as a workroom (not served)
    has no door outside: no."""
    for use, want in (("closet", True), ("workroom", False)):
        desc = row(("marked", "marked", "marked"), ("wall", "wall"))
        desc["rooms"].append(room("k", rect(0, 10.5, 5, 15), use=use, lockable=False, pass_through=False))
        desc["doors"].append(door("dk", (2.5, 10.25), (1, 0), ("r0", "k")))
        sp = _story(desc)
        assert sp["measures"].get(OUTSIDE_FACT) is want, (use, sp["not_measured"].get(OUTSIDE_FACT))


def test_an_unknown_space_or_a_room_not_read_is_never_a_yes():
    desc = row(("marked", "marked", "marked"), ("wall", "wall"))
    desc["unknown_spaces"] = [{"id": "u", "name": "Space 9", "level": "L1", "outline": [[0, 11], [5, 11], [5, 15]]}]
    sp = _story(desc)
    assert OUTSIDE_FACT not in sp["measures"]
    assert sp["not_measured"][OUTSIDE_FACT].startswith(STOPS["story_not_measured"].split("{")[0])


APARTMENT = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"


def test_the_four_unit_apartment_its_apartments_reach_the_outside_only_by_the_corridor_and_stairs():
    """Level 1: the apartments and the corridor have no door to the outside (the stair enclosures, themselves exits,
    have the doors out, and are left out): no. Level 2 the same."""
    got = measure(json.loads(APARTMENT.read_text(encoding="utf-8"))["interior"])
    assert [s["measures"][OUTSIDE_FACT] for s in got["parts"]["story"]] == [False, False]


def test_each_reason_has_a_case():
    seen = set()
    desc = row(("marked", "unmarked", "marked"), ("wall", "wall"))
    reason = _story(desc)["not_measured"][OUTSIDE_FACT]
    assert reason == STOPS["outside_door_not_marked"].format(name="r1", door="o1")
    seen.add("outside_door_not_marked")
    only_exit = description([room("s", rect(0, 0, 10, 10), use="other")],
                            [door("in", (10.25, 5), (0, 1), ("s", "outside"), exit_id="s", kind="exit_enclosure")])
    sp = _story(only_exit)
    assert sp["not_measured"][OUTSIDE_FACT] == STOPS["outside_no_rooms"], sp["not_measured"]
    seen.add("outside_no_rooms")
    assert seen == OUTSIDE_KEYS
