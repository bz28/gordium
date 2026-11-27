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
    desc["story_outlines"] = [outline(-0.5, -7, 36, 18.5)]   # the diagonal 1007.1.1's distance is measured on
    if within is not None:                               # the building states whether a corridor is within a unit
        desc["building"] = {"corridors_within_dwelling_units": within}
    return desc


def outline(x0, y0, x1, y1) -> dict:
    """The story's outer and inner outlines, one rectangle (ft)."""
    return {"level": "L1", "outer": [list(p) for p in rect(x0, y0, x1, y1)],
            "inner": [list(p) for p in rect(x0 + 0.5, y0 + 0.5, x1 - 0.5, y1 - 0.5)]}


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
    got = b1["more"][EXITS_REACHED]
    assert got["two"] is True and got["doors"] == {"i1": ["x", "y"]}, got
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
    desc["rooms"].append(room("ah", rect(12, -12, 34, -7), use="corridor", pass_through=True))
    desc["doors"] += [door("aentry", (14, -6.75), (1, 0), ("ah", "c")),     # its back door far enough from x to be a
                      door("aback", (32, -12.25), (1, 0), ("ah", "outside"), exit_id="z")]   # second exit (1007.1.1)
    desc["story_outlines"] = [outline(-0.5, -12.5, 36, 18.5)]
    got = reached(desc)
    for b in ("b0", "b1", "b2"):
        if within is False:                              # stated: the hall is shared, its exit door one of two
            assert got[b]["two"] is True and got[b]["doors"] == {f"e{b[1]}": ["x", "z"]}, got[b]
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
    desc["story_outlines"] = [outline(-0.5, -7, 45, 18.5)]   # the stair inside the story's outline
    desc["doors"].append(door("dS", (35.75, -3.5), (0, 1), ("c", "S"), exit_id="S", kind="exit_enclosure"))
    if how != "no_door_out":
        desc["doors"].append(door("So", (44.25, -3.5), (0, 1), ("S", "outside"),
                                  **({"exit_id": "S"} if how == "door_out_marked" else {})))
    got = reached(desc)
    if how == "door_out_marked":
        assert got["b0"]["two"] is True and got["b0"]["doors"] == {"e0": ["S", "x"]}, got["b0"]
    else:
        assert got["b0"]["two"] is False and "no door out of its own marked an exterior exit door" in got["b0"]["why"]


def test_an_exit_not_counted_says_its_own_reason():
    """Review round 2 (PR 3): every exit left out was said to be a stair on its discharge level; a horizontal exit
    says it is one."""
    desc = corridor(split=True)
    desc["doors"].append(door("hx", (17.75, -3.5), (0, 1), ("c", "c2"), exit_id="H", kind="horizontal_exit"))
    got = reached(desc)["b0"]
    assert got["two"] is False and "H: a horizontal exit, not counted here" in got["why"], got
    assert "a stair or passageway" not in got["why"]


# --- merge review of #240: two exits count only where they are separate and distinct (BCNYS 1007.1.1) ---------------

def side_by_side():
    """The corridor with its two exterior exit doors 3 ft apart on its west wall (x and x2, both at discharge)."""
    d = corridor(exits=("x",))
    d["doors"][0]["plan"].update(clear_width=2.5, centre=[-0.25, -5.0])
    d["doors"].append(door("dx2", (-0.25, -2.0), (0, 1), ("c", "outside"), exit_id="x2", width=2.5))
    return d


def test_each_room_says_how_far_apart_the_exits_it_reaches_are():
    """BCNYS 1007.1.1 (p.318) places two exits "a distance apart equal to not less than one-half of the length of the
    maximum overall diagonal dimension of the building or area to be served" (one-third sprinklered, exception 2):
    the routes give each room's own figure, its exits' distance (straight.py: nearest edges) over the story's outer
    diagonal, and the law's rule decides (design_checker/escape_openings.py). The corridor's end exits: about 35 ft of
    a 44.5 ft diagonal. Two doors 3 ft apart (a false pass before the merge review, as two exits): under a tenth."""
    for got in (g for g in reached(corridor()).values() if g is not None):
        assert got["two"] is True and 0.75 < got["remoteness_ratio"] < 0.85, got
    for got in (g for g in reached(side_by_side()).values() if g is not None):
        assert got["two"] is True and got["remoteness_ratio"] < 0.1, got


def test_no_story_outline_leaves_the_exits_not_shown_apart():
    """The diagonal not measured: 1007.1.1's distance isn't known, so never two (a wrong two sets aside 1031.2's
    escape opening)."""
    d = corridor()
    d["story_outlines"] = []
    for got in (g for g in reached(d).values() if g is not None):
        assert got["two"] is False and "diagonal isn't measured" in got["why"], got


@pytest.mark.parametrize("join", ["passage", "door", "adjoining"])
def test_two_exit_stair_rooms_joined_to_each_other_are_one_exit(join):
    """BCNYS 1007.1.1 (p.318): "Interlocking or scissor stairways shall be counted as one exit stairway": two exit
    enclosures that open into each other (a passage or a door between them), or that adjoin with only a wall between
    (the usual drawing of a scissor stair), are one exit, so the bedrooms reaching only them don't reach two (an upper
    story: no door to outside)."""
    d = corridor(exits=())
    d["story_outlines"] = [outline(-0.5, -7, 44.5, 18.5)]
    d["rooms"] += [room("S1", rect(36, -6.5, 44, -3.6), use="other", lockable=True),
                   room("S2", rect(36, -3.4, 44, -0.5), use="other", lockable=True)]
    d["doors"] += [door("d1", (35.75, -5), (0, 1), ("c", "S1"), exit_id="S1", kind="exit_enclosure", width=2.5),
                   door("d2", (35.75, -2), (0, 1), ("c", "S2"), exit_id="S2", kind="exit_enclosure", width=2.5)]
    if join == "passage":
        d["passages"].append({"rooms": ["S1", "S2"], "line": [[36, -3.5], [44, -3.5]]})
        d["rooms"][-2]["floor"] = [list(p) for p in rect(36, -6.5, 44, -3.5)]
        d["rooms"][-1]["floor"] = [list(p) for p in rect(36, -3.5, 44, -0.5)]
    elif join == "door":
        d["doors"].append(door("d12", (40, -3.5), (1, 0), ("S1", "S2"), thickness=0.2))
    # adjoining: a wall between them and no way through, a scissor stair drawn as two rooms
    for b, got in reached(d).items():
        if got is None:
            continue
        assert got["two"] is False and "one exit" in got["why"], (b, got)


def test_a_scissor_stair_and_a_third_exit_are_measured_from_the_stairs_nearest_door():
    """Fix review (a false pass): two adjoining stair rooms S1|S2 are one exit (1007.1.1), so with a third exit X the
    pair is X and that one stair, measured from its door nearest X (S1's, 3 ft), never from S2's far door: about a
    twentieth of the diagonal, not the half 1007.1.1 asks."""
    d = corridor(exits=())                                   # an upper story, no door to outside
    d["rooms"] += [room("S1", rect(0, -15, 17.5, -7), use="other", lockable=True),
                   room("S2", rect(17.7, -15, 35.5, -7), use="other", lockable=True),
                   room("X", rect(-9, -4, -0.5, 5), use="other", lockable=True)]
    d["doors"] += [door("d1", (2, -6.75), (1, 0), ("c", "S1"), exit_id="S1", kind="exit_enclosure", width=2.5),
                   door("d2", (33, -6.75), (1, 0), ("c", "S2"), exit_id="S2", kind="exit_enclosure", width=2.5),
                   door("dX", (-0.25, -2), (0, 1), ("c", "X"), exit_id="X", kind="exit_enclosure", width=2.5)]
    d["story_outlines"] = [outline(-9.5, -15.5, 36, 18.5)]
    for got in (g for g in reached(d).values() if g is not None):
        assert got["two"] is True and got["remoteness_ratio"] < 0.1, got


def test_an_outline_that_doesnt_hold_the_story_never_shows_exits_apart():
    """Fix review: an outer outline smaller than the story (a wing, a slip) would shrink the diagonal and make close
    exits look apart: not two."""
    d = side_by_side()
    d["story_outlines"] = [outline(0, -7, 10, 0)]
    for got in (g for g in reached(d).values() if g is not None):
        assert got["two"] is False and "doesn't hold all its rooms" in got["why"], got


def test_the_rooms_figure_is_its_worst_doors():
    """Every way out of the room must reach two exits placed apart: with one door reaching the corridor's far exits
    and another reaching only a close pair, the room's ratio is the close pair's."""
    from model_measurement.routes import _apart, _is_exit
    from routes_layouts import story
    d = side_by_side()
    d["doors"].append(door("dy", (35.75, -3.5), (0, 1), ("c", "outside"), exit_id="y"))
    s = story(d)
    exits = {r for r in s.rooms if _is_exit(s, r)}
    links = [tuple(x.sides) for x in s.doors.values()]
    _, far = _apart(s, exits, links, {"e0": ["x", "y"]})
    _, both = _apart(s, exits, links, {"e0": ["x", "y"], "e1": ["x", "x2"]})
    assert far > 0.75 and both < 0.1, (far, both)


def test_an_outline_a_few_inches_short_of_the_walls_never_shows_exits_apart():
    """Confirming review: with the east exit moved onto the south wall the exits are 0.484 of the true diagonal apart
    (under 1007.1.1's half); an outer outline drawn about 5 in short of the rooms (11 in inside the walls' outer faces,
    so the exit doors' openings stick out) would make it 0.515. The outline must hold every room and exit door to
    within half an inch, so it is refused: not two."""
    d = corridor()
    next(x for x in d["doors"] if x["id"] == "dy")["plan"].update(centre=[23.0, -6.75], along=[1, 0])
    assert all(g["remoteness_ratio"] < 0.5 for g in reached(d).values() if g is not None)
    d["story_outlines"] = [outline(0.45, -6.05, 35.05, 17.55)]
    for got in (g for g in reached(d).values() if g is not None):
        assert got["two"] is False and "doesn't hold all its rooms" in got["why"], got
