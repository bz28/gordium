"""Whether a sleeping room's occupants have access to two or more separate and distinct exits, from its routes
(model_measurement/routes `_exits_reached`, the space part's `more["exits_reached"]`), which BCNYS 1031.2 item 1 reads
("Group R-2 occupancies located in stories with only one exit or access to only one exit as permitted by Tables
1006.3.4(1) and 1006.3.4(2)", p.339): 1006.3 (p.295) "All spaces located on a story ... shall have access to the
required number of separate and distinct exits"; 202 COMMON PATH OF EGRESS TRAVEL (p.17) "to that point where the
occupants have separate and distinct access to two exits or exit access doorways".

A corridor with an exit at each end and bedrooms off it: every bedroom reaches both (two). A wall across the
corridor, or a bedroom whose way out reaches one exit only, or one with a passage out, or a door of its own that is
an exit: not two. A wrong "two" sets aside the escape opening 1031.2 asks, so every doubt is "not two"."""

import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from routes_layouts import description, door, rect, room  # noqa: E402

from model_measurement.routes import EXITS_REACHED, measure  # noqa: E402


def corridor(split=False, exits=("x", "y"), bedroom_exit=False, served=False, passage=False, within=False):
    """A corridor 0-35.5 by -6.5 to -0.5 ft, exits at its west (x) and east (y) ends (each a door to outside at
    discharge), three bedrooms off it (b0-b2, 12 ft apart); `split`: a wall at x 17.75 cuts it in two (c and c2);
    `served`: b1 opens only into a living room routes may cross (marked pass-through), which opens into the corridor."""
    rooms = []
    if split:
        rooms += [room("c", rect(0, -6.5, 17.5, -0.5), use="corridor", pass_through=True),
                  room("c2", rect(18, -6.5, 35.5, -0.5), use="corridor", pass_through=True)]
    else:
        rooms.append(room("c", rect(0, -6.5, 35.5, -0.5), use="corridor", pass_through=True))
    east = "c2" if split else "c"
    doors = []
    if "x" in exits:
        doors.append(door("dx", (-0.25, -3.5), (0, 1), ("c", "outside"), exit_id="x"))
    if "y" in exits:
        doors.append(door("dy", (35.75, -3.5), (0, 1), (east, "outside"), exit_id="y"))
    passages = []
    for i in range(3):
        x0 = 12 * i
        side = "c2" if split and i == 2 else "c"
        if served and i == 1:
            rooms.append(room("b1", rect(x0, 8.5, x0 + 11.5, 18), use="other", lockable=True, sleeping=True))
            rooms.append(room("l1", rect(x0, 0, x0 + 11.5, 8), use="other", lockable=False, pass_through=True))
            doors += [door("e1", (x0 + 3, -0.25), (1, 0), ("l1", side)), door("i1", (x0 + 6, 8.25), (1, 0), ("b1", "l1"))]
            continue
        rooms.append(room(f"b{i}", rect(x0, 0, x0 + 11.5, 10), use="other", lockable=True, sleeping=True))
        if passage and i == 0:
            passages.append((("b0", "c"), [(0, -0.5), (11.5, -0.5)]))
            rooms[-1]["floor"] = [list(p) for p in rect(0, -0.5, 11.5, 10)]
        else:
            doors.append(door(f"e{i}", (x0 + 3, -0.25), (1, 0), (f"b{i}", side)))
    if bedroom_exit:
        doors.append(door("bx", (12.25 + 11.5, 5), (0, 1), ("b1", "outside"), exit_id="z"))
    desc = description(rooms, doors, passages)
    if within is not None:                               # the building states whether a corridor is within a unit
        desc["building"] = {"corridors_within_dwelling_units": within}
    return desc


def reached(desc) -> dict:
    out = measure(desc)
    return {p["id"]: p["more"].get(EXITS_REACHED) for p in out["parts"]["space"]}


def test_bedrooms_off_a_corridor_with_an_exit_at_each_end_reach_two():
    got = reached(corridor())
    for b in ("b0", "b1", "b2"):
        assert got[b]["two"] is True and got[b]["doors"] == {f"e{b[1]}": ["x", "y"]}, got[b]


def test_a_wall_across_the_corridor_leaves_each_bedroom_one_exit():
    """Two exits on the story, but each half of the corridor reaches one: access to only one exit, never two."""
    got = reached(corridor(split=True))
    for b in ("b0", "b1", "b2"):
        assert got[b]["two"] is False and "reaches one exit" in got[b]["why"], got[b]


def test_one_exit_on_the_story_is_never_two():
    got = reached(corridor(exits=("x",)))
    assert all(got[b]["two"] is False for b in ("b0", "b1", "b2")), got


@pytest.mark.parametrize("how", ["passage", "bedroom_exit"])
def test_a_passage_out_or_a_door_of_its_own_that_is_an_exit_is_not_worked_out(how):
    got = reached(corridor(**{how: True}))
    b = "b0" if how == "passage" else "b1"
    assert got[b]["two"] is False and got[b]["why"], got[b]


def test_a_bedroom_through_a_living_room_reaches_two_through_it():
    """A bedroom opening only into a living room routes may cross, which opens into the corridor (a unit's bedroom):
    its routes run on through the living room to both exits; the living room, crossed by routes, isn't worked out
    (not a sleeping room either)."""
    out = measure(corridor(served=True))
    b1 = next(p for p in out["parts"]["space"] if p["id"] == "b1")
    assert b1["more"][EXITS_REACHED] == {"two": True, "doors": {"i1": ["x", "y"]}}, b1["more"][EXITS_REACHED]
    l1 = next(p for p in out["parts"]["space"] if p["id"] == "l1")
    assert EXITS_REACHED not in l1["more"]


def test_the_walk_two_only_where_every_way_out_reaches_two_distinct_exits():
    """Every mix of the story's exits (none, west, east, both), a wall across the corridor or not, and the middle
    bedroom served through a living room or not: a bedroom is two exactly where its half of the corridor holds both
    exits (an oracle from the layout, written apart from the routes)."""
    seen = set()
    for exits, split, served in itertools.product([(), ("x",), ("y",), ("x", "y")], (False, True), (False, True)):
        got = reached(corridor(split=split, exits=exits, served=served))
        for i in range(3):
            west = not split or i < 2                    # b0, b1 on the west half when split; b2 on the east
            east = not split or i == 2
            want = ("x" in exits and west) + ("y" in exits and east) >= 2
            g = got[f"b{i}"] or {"two": False}             # no exit on the story: its routes aren't measured
            assert g["two"] is want, (exits, split, served, i, g)
            seen.add(want)
    assert seen == {True, False}


def test_an_exit_reached_only_through_another_units_room_never_counts():
    """1016.2.1: no route through an adjacent dwelling unit. The corridor cut in two (b0's half reaches exit x only),
    and a neighbour's living room, which routes may cross (marked pass-through), opening into both halves: its routes
    reach exit y through it, but that room is another space's, so b0 still reaches one exit. Two units joined by a
    door (a lock-off), each with its own door to the corridor, aren't worked out (two ways out of one space)."""
    desc = corridor(split=True)
    desc["rooms"].append(room("nb", rect(12, -12, 24, -7), use="other", lockable=False, pass_through=True))
    desc["doors"] += [door("n1", (14, -6.75), (1, 0), ("nb", "c")), door("n2", (21, -6.75), (1, 0), ("nb", "c2"))]
    out = measure(desc)
    story = out["parts"]["story"][0]
    assert story["measures"]["egress_travel_distance"] > 0           # the routes walk through nb (they reach y)
    got = {p["id"]: p["more"].get(EXITS_REACHED) for p in out["parts"]["space"]}
    assert got["b0"]["two"] is False and got["b0"]["doors"] == {"e0": ["x"]}, got["b0"]
    # a lock-off: b0 and b1 joined by a door, each with its own door to the whole corridor
    desc = corridor()
    desc["doors"].append(door("j", (11.75, 5), (0, 1), ("b0", "b1")))
    got = reached(desc)
    assert got["b0"]["two"] is False and "2 ways out" in got["b0"]["why"], got["b0"]


# --- review round 1 (PR 3): each finding's pin ----------------------------------------------------------------------

@pytest.mark.parametrize("within", [None, True, False])
def test_a_corridor_is_shared_only_where_the_building_states_none_is_within_a_unit(within):
    """A neighbour's own hall marked a corridor, with its own exit door, off a public corridor with one exit: unless
    the building states no corridor is within a dwelling unit, that hall may be inside the neighbour's unit, so its
    exit never counts (1016.2.1); and with no such statement no corridor is crossed at all (not two)."""
    desc = corridor(exits=("x",), within=within)
    desc["rooms"].append(room("ah", rect(12, -12, 24, -7), use="corridor", pass_through=True))
    desc["doors"] += [door("aentry", (14, -6.75), (1, 0), ("ah", "c")),
                      door("aback", (18, -12.25), (1, 0), ("ah", "outside"), exit_id="z")]
    got = reached(desc)
    for b in ("b0", "b1", "b2"):
        if within is False:                              # stated: the hall is shared, its exit door one of two
            assert got[b] == {"two": True, "doors": {f"e{b[1]}": ["x", "z"]}}, got[b]
        else:
            assert got[b]["two"] is False and "states none is within a dwelling unit" in got[b]["why"], got[b]
    assert reached(corridor(within=None))["b0"]["two"] is False         # the plain corridor: not stated, not two


@pytest.mark.parametrize("how", ["no_door_out", "door_out_unmarked", "door_out_marked"])
def test_a_stair_entered_on_the_level_it_discharges_is_no_second_exit_unless_its_own_door_out_is_marked(how):
    """A stair enclosure off a corridor whose only exit door to outside is the front door: on that level the stair
    may discharge back through the corridor (1028.1), so its door is no second exit there, nor where its own door out
    isn't marked an exterior exit door; marked, it is one (`_egress_sides`' own test)."""
    desc = corridor(exits=("x",))
    desc["rooms"].append(room("S", rect(36, -6.5, 44, -0.5), use="other", lockable=True))
    desc["doors"].append(door("dS", (35.75, -3.5), (0, 1), ("c", "S"), exit_id="S", kind="exit_enclosure"))
    if how != "no_door_out":
        desc["doors"].append(door("So", (44.25, -3.5), (0, 1), ("S", "outside"),
                                  **({"exit_id": "S"} if how == "door_out_marked" else {})))
    got = reached(desc)
    if how == "door_out_marked":
        assert got["b0"] == {"two": True, "doors": {"e0": ["S", "x"]}}, got["b0"]
    else:
        assert got["b0"]["two"] is False and "not surely leading this story out" in got["b0"]["why"], got["b0"]
