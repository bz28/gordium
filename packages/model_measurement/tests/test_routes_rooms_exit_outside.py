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

from model_measurement.routes import OUTSIDE_FACT, measure, rooms_exit_outside  # noqa: E402
from model_measurement.routes.floor import read  # noqa: E402
from model_measurement.routes.stops import STOPS, Stop  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
OUTSIDE_KEYS = {"outside_no_rooms", "outside_door_not_marked", "outside_way_unclear"}
KINDS = ("marked", "unmarked", "stair", "none")
SIDES = ("door", "passage", "wall")


def row(kinds, joins, uses=("other", "other", "other"), corridor=None):
    """Three 10 by 10 ft rooms side by side (x 0-10, 10.5-20.5, 21-31; a 6 in wall between), each door to the
    outside on the south wall (y = -0.25), `joins` between rooms 0-1 and 1-2 (a door, a passage with no wall: then
    the rooms touch, or a plain wall). `corridor`: None, or which rooms open into a corridor along their north side
    (y 10.5-16.5), itself with a marked exit door outside at its west end."""
    rooms, doors, passages, x = [], [], [], 0.0
    xs = []
    for i, (kind, use) in enumerate(zip(kinds, uses)):
        x0 = x
        x1 = x0 + 10
        xs.append((x0, x1))
        rooms.append(room(f"r{i}", rect(x0, 0, x1, 10), use=use, lockable=False, pass_through=False))
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
    top = 10
    if corridor is not None:
        rooms.append(room("c", rect(0, 10.5, x, 16.5), use="corridor", lockable=False, pass_through=True))
        doors.append(door("oc", (-0.25, 13.5), (0, 1), ("c", "outside"), exit_id="oc"))
        for i in corridor:
            doors.append(door(f"e{i}", ((xs[i][0] + xs[i][1]) / 2, 10.25), (1, 0), (f"r{i}", "c")))
        top = 16.5
    desc = description(rooms, doors, passages)
    desc["story_outlines"] = [{"level": "L1", "outer": [[-0.5, -0.5], [x + 0.5, -0.5], [x + 0.5, top + 0.5],
                                                        [-0.5, top + 0.5]],
                               "inner": [[0, 0], [x, 0], [x, top], [0, top]]}]
    return desc


def _story(desc):
    """The story's fact as the route measuring sets it (measured, or its reason), from the floor read alone: the
    walks don't need the routes' travel figures (measure() runs the same function; the apartment test goes through
    it)."""
    story = read(desc).stories["L1"]
    try:
        return {"measures": {OUTSIDE_FACT: rooms_exit_outside(story)}, "not_measured": {}}
    except Stop as s:
        return {"measures": {}, "not_measured": {OUTSIDE_FACT: s.reason}}


def oracle(kinds, joins, corridor=None):
    """True, False, or None (not known), from item 2's words read as rooms, areas and spaces: rooms joined by a door
    or with no wall are one space (its occupants reach its exit through it, 1016.2); a corridor opening into one
    space only is a vestibule of it, one into two or more is shared. Each space needs its own exit straight
    outside (yes); a space reaching the outside only through a shared corridor can't rely on item 2 (no)."""
    if "stair" in kinds:                                 # travel along an exterior stair isn't read: the story isn't
        return None
    if "marked" not in kinds and corridor is None:       # no exit marked on the story: its routes aren't read
        return None
    owner = list(range(3))
    for i, j in enumerate(joins):
        if j in ("door", "passage"):
            old, new = owner[i + 1], owner[i]
            owner = [new if o == old else o for o in owner]
    spaces = {o: {i for i in range(3) if owner[i] == o} for o in set(owner)}
    touched = {owner[i] for i in (corridor or ())}
    shared = len(touched) >= 2
    verdicts = []
    for o, members in spaces.items():
        has = {kinds[i] for i in members}
        if "marked" in has or (corridor is not None and touched == {o}):     # its own door, or its vestibule's
            verdicts.append(True)
        elif "unmarked" in has:
            verdicts.append(None)
        elif shared and o in touched:
            verdicts.append(False)
        else:
            verdicts.append(None)
    if False in verdicts:
        return False
    return None if None in verdicts else True


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
    assert True in seen, seen                                                                  # never vacuous


@pytest.mark.parametrize("joins", list(itertools.product(("door", "wall"), repeat=2)), ids="-".join)
def test_the_walk_with_a_corridor(joins):
    """The same row with a corridor along it, each room opening into it or not: the corridor shared by two or more
    spaces, a vestibule of one, or opening into none."""
    seen = set()
    for opens in itertools.product((False, True), repeat=3):
        corridor = [i for i in range(3) if opens[i]]
        for kinds in itertools.product(("marked", "unmarked", "none"), repeat=3):
            sp = _story(row(kinds, joins, corridor=corridor))
            want = oracle(kinds, joins, corridor)
            seen.add(sp["measures"].get(OUTSIDE_FACT))
            if want is None:
                assert OUTSIDE_FACT not in sp["measures"], (kinds, joins, corridor, sp["measures"].get(OUTSIDE_FACT))
            else:
                assert sp["measures"].get(OUTSIDE_FACT) is want, (kinds, joins, corridor,
                                                                  sp["not_measured"].get(OUTSIDE_FACT))
    assert True in seen and (False in seen or "wall" not in joins), seen           # never vacuous


def test_a_room_reached_through_another_of_its_space_is_part_of_it():
    """Review round 1 (PR 2): a bedroom off a living room with its own door out, a workroom off a shop, a closet off a
    room whose use isn't given (so not taken as served, decision 1a), a toilet off a lockable room: each is part of the
    space whose exit its occupants reach through it (1016.2), never a space without an exit ("no" removed the item 2
    review, so a one-exit story failed outright)."""
    for use, host in (("other", {}), ("workroom", {}), ("closet", {"use": None}), ("toilet", {"lockable": True}),
                      ("other", {"sleeping": True})):
        desc = row(("marked", "marked", "marked"), ("wall", "wall"))
        desc["rooms"][0].update(host)
        desc["rooms"].append(room("k", rect(0, 10.5, 5, 15), use=use, lockable=False, pass_through=False,
                                  sleeping=use == "other"))
        desc["doors"].append(door("dk", (2.5, 10.25), (1, 0), ("r0", "k")))
        sp = _story(desc)
        assert sp["measures"].get(OUTSIDE_FACT) is not False, (use, host, sp["not_measured"].get(OUTSIDE_FACT))


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
    alone = _story(row(("marked", "none", "marked"), ("wall", "wall")))["not_measured"][OUTSIDE_FACT]
    assert alone == STOPS["outside_way_unclear"].format(name="r1")
    seen.add("outside_way_unclear")
    assert seen == OUTSIDE_KEYS
