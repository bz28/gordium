"""The dwelling units on a story (Table 1006.3.4(1) "MAXIMUM NUMBER OF DWELLING UNITS"), worked out from the model:
routes/dwelling_units.py.

The property walk: a corridor along three suites, each one or two rooms, each stating the function residential,
business, or none, opening into the corridor by none, one or two doors, the neighbouring suites joined by a door or
not. The oracle, from DWELLING UNIT (202: "complete, independent living facilities") and 1016.2.1 (each dwelling unit
reaches the exits without passing through another): rooms joined without crossing the corridor are one group; a group
with a residential room and one door to the corridor is one unit (Gordium's reading); a group with no residential
room and a function stated for every room is none; any other group (no function stated, two or more doors, none) may
be some other count, so the story's count isn't measured."""

import itertools
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from routes_layouts import description, door, rect, room  # noqa: E402

from model_measurement.routes import UNITS_FACT, _is_exit, measure  # noqa: E402
from model_measurement.routes.dwelling_units import MARKED, QUOTE_1016_2_1, RESTS_ON, marked, units_on  # noqa: E402
from model_measurement.routes.floor import read  # noqa: E402
from model_measurement.routes.stops import STOPS, Stop  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
UNITS_KEYS = {"units_use_unknown", "units_function_unknown", "units_no_entrance", "units_entrances", "units_stair",
              "units_shared_room", "units_link_elsewhere", "units_link_unread", "units_exit_function",
              "units_hall_residential"}
MARK_KEYS = {"units_mark_unreadable", "units_mark_several", "units_mark_alike", "units_mark_apart",
             "units_mark_not_dwelling", "units_mark_on_exit", "units_mark_left_out", "units_mark_hall_function"}     # the unit marks' tests below
UNITS_KEYS |= MARK_KEYS
FUNCTIONS = ("residential", "business", None)


def layout(suites, joins):
    """`suites`: three (function, rooms 1 or 2, doors to the corridor 0, 1 or 2); suite i at x 12i to 12i+11.5,
    y 0-10 (a second room at y 10.5-15, behind the first, joined by a door); the corridor at y -6.5 to -0.5 with an
    exit door at its west end; `joins`: whether suites 0-1 and 1-2 have a door between them."""
    rooms = [room("c", rect(0, -6.5, 35.5, -0.5), use="corridor", lockable=False, pass_through=True)]
    doors = [door("x", (-0.25, -3.5), (0, 1), ("c", "outside"), exit_id="x")]
    for i, (function, n, entries) in enumerate(suites):
        x0 = 12 * i
        r = room(f"s{i}", rect(x0, 0, x0 + 11.5, 10), use="other", lockable=True, pass_through=False)
        if function:
            r["function"] = function
        rooms.append(r)
        if n == 2:
            back = room(f"b{i}", rect(x0, 10.5, x0 + 11.5, 15), use="other", lockable=False, pass_through=False)
            if function:
                back["function"] = function
            rooms.append(back)
            doors.append(door(f"bd{i}", (x0 + 5, 10.25), (1, 0), (f"s{i}", f"b{i}")))
        for k in range(entries):
            doors.append(door(f"e{i}{k}", (x0 + 3 + 5 * k, -0.25), (1, 0), (f"s{i}", "c")))
    for i, joined in enumerate(joins):
        if joined:
            doors.append(door(f"j{i}", (12 * i + 11.75, 5), (0, 1), (f"s{i}", f"s{i + 1}")))
    desc = description(rooms, doors)
    desc["stairs"] = []                                  # no stair, ramp or ladder: said, as a host says it
    desc["has_none"] = [{"kind": k, "source": "the test's corridor: none drawn"}
                        for k in ("ramp", "alternating_tread_device", "ships_ladder")]
    return desc


def count(desc):
    """The story's count as measure() works it out (the stairs read as it reads them), or its Stop."""
    from model_measurement.routes import _links_listed, _stair_in, _stair_points, links_read_here
    story = read(desc).stories["L1"]
    stairs = _stair_points(desc)
    try:
        return units_on(story, {r["id"]: r for r in desc["rooms"]}, _is_exit,
                        lambda g: any(_stair_in(st, g, story) for st in stairs),
                        lambda: links_read_here(story, _links_listed(desc), "units"))
    except Stop as s:
        return s


def oracle(suites, joins):
    """The story's count, or None where a group may hold another number of units."""
    owner = [0, 1, 2]
    for i, joined in enumerate(joins):
        if joined:
            old = owner[i + 1]
            owner = [owner[i] if o == old else o for o in owner]
    for i, (function, n, _) in enumerate(suites):   # a room not itself residential opening onto two or more rooms
        links = (n == 2) + sum(1 for k in (i - 1, i) if 0 <= k < 2 and joins[k])    # of its group: maybe shared
        residential_group = any(f == "residential" for k, (f, _, _) in enumerate(suites) if owner[k] == owner[i])
        if function != "residential" and links >= 2 and residential_group:
            return None
    total = 0
    for o in set(owner):
        members = [suites[i] for i in range(3) if owner[i] == o]
        functions = {f for f, _, _ in members}
        doors = sum(e for _, _, e in members)
        if None in functions:
            return None                                  # no function stated: a unit, or a room shared between units
        if "residential" not in functions:
            continue                                     # business throughout: no dwelling unit
        if doors != 1:
            return None                                  # no door of its own, or two units joined by a door
        total += 1
    return total


@pytest.mark.parametrize("joins", list(itertools.product((False, True), repeat=2)), ids=str)
def test_the_walk_every_count_measured_is_the_oracles(joins):
    seen = set()
    one, two = itertools.product(FUNCTIONS, (1,), (0, 1, 2)), itertools.product(FUNCTIONS, (2,), (0, 1, 2))
    one = list(one)
    for suites in itertools.product(one, list(two), one):          # the middle suite two rooms, the others one
        got, want = count(layout(suites, joins)), oracle(suites, joins)
        if want is None:
            assert isinstance(got, Stop), (suites, joins, got)
        else:
            assert got == want, (suites, joins, got)
        seen.add(got if not isinstance(got, Stop) else None)
    assert {0, 1, None} <= seen and (3 in seen or any(joins)), seen                 # never vacuous


def test_a_room_with_no_use_given_may_be_a_corridor_joining_two_units():
    """Two residential suites opening into a room whose use isn't given (it may be a corridor): taken as a room,
    they would be one group with one door out, counted one unit; never measured."""
    desc = layout([("residential", 1, 1), ("residential", 1, 1), ("business", 1, 1)], (False, False))
    del desc["rooms"][0]["use"]
    got = count(desc)
    assert isinstance(got, Stop) and got.reason == STOPS["units_use_unknown"].format(name="c")


APARTMENT = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_check_site_request.json"


def test_the_four_unit_apartment_two_units_a_story_with_the_reading_beside_them():
    """As marked for the eval (each apartment's function residential, make_ny_build_data.interior_of): two units on
    each story, each one room with one door to the corridor; the count says the reading it stands on and 1016.2.1.
    As Revit sent it (no function marked): not measured."""
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_ny_build_data as build
    interior = build.interior_of()
    interior["stairs"] = [{"id": f"flight {x}", "nosings": [[[x, 13, 0], [x, 17, 0]]]} for x in (4.5, 55.5)]
    interior["has_none"] = [{"kind": k, "source": "the eval building: none drawn"}
                            for k in ("ramp", "alternating_tread_device", "ships_ladder")]
    for s in measure(interior)["parts"]["story"]:
        assert s["measures"][UNITS_FACT] == 2, s["name"]
        assert s["rests_on"][UNITS_FACT] == RESTS_ON
    assert "1016.2.1 (p.341)" in RESTS_ON and QUOTE_1016_2_1 in RESTS_ON
    for r in interior["rooms"]:                          # each apartment marked with its unit (Gordium: Unit)
        if r.get("function") == "residential":
            r["unit"] = r["name"]
    for s in measure(interior)["parts"]["story"]:
        assert s["measures"][UNITS_FACT] == 2, s["name"]
        assert s["architect_stated"][UNITS_FACT] == MARKED and UNITS_FACT not in s.get("rests_on", {})
    for s in measure(json.loads(APARTMENT.read_text(encoding="utf-8"))["interior"])["parts"]["story"]:
        assert UNITS_FACT not in s["measures"]
        assert s["not_measured"][UNITS_FACT].startswith(STOPS["units_function_unknown"].split("{")[0])


def test_each_reason_has_a_case():
    seen = set()
    for suites, key in ((("residential", 1, 0), "units_no_entrance"), (("residential", 1, 2), "units_entrances"),
                        ((None, 1, 1), "units_function_unknown")):
        got = count(layout([suites, ("business", 1, 1), ("business", 1, 1)], (False, False)))
        assert isinstance(got, Stop) and got.key == key, (suites, got)
        seen.add(key)
    seen.add("units_use_unknown")                        # test_a_room_with_no_use_given_may_be_a_corridor...
    seen |= {"units_stair", "units_shared_room"}         # the round 2 tests below
    seen |= {"units_link_elsewhere", "units_link_unread"}    # test_a_units_own_door_drawn_on_another_level...
    seen |= {"units_exit_function", "units_hall_residential"}   # test_a_unit_marked_an_exit_or_a_hall...
    seen |= MARK_KEYS                                    # the unit marks' tests at the end of this file
    assert seen == UNITS_KEYS


# --- review round 1 (PR 3): each finding's pin ---------------------------------------------------------------------

def test_an_opening_with_no_door_to_the_corridor_is_a_way_out():
    """Suite 0 open to the corridor by a passage (no door), joined by a door to suite 1, which has its own door: two
    ways out, so maybe two units (a lock-off). Before, the opening wasn't counted: one unit."""
    desc = layout([("residential", 1, 0), ("residential", 1, 1), ("business", 1, 1)], (True, False))
    desc["passages"] = [{"rooms": ["s0", "c"], "line": [[0, -0.5], [11.5, -0.5]]}]
    desc["rooms"][1]["floor"] = [list(p) for p in rect(0, -0.5, 11.5, 10)]           # s0 meets the corridor
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_entrances", got


@pytest.mark.parametrize("function", ["Residential", "residential ", "R-2", 7, ["residential"], "dormitory",
                                      "institutional_sleeping"])
def test_a_function_not_on_the_list_never_rules_a_unit_out(function):
    """Two of six one-room units with a function that isn't a listed other use: before, "no dwelling unit", the
    count 4 and the row passing with 6 units. Now not measured."""
    suites = [("residential", 1, 1)] * 3
    desc = layout(suites, (False, False))
    desc["rooms"][1]["function"] = function
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_function_unknown", (function, got)


def test_a_shared_vestibule_not_marked_a_corridor_is_never_counted_as_one_unit():
    """A vestibule (use other) with one door to the corridor and two units off it: one group, one way out, but two
    units, and 1016.2.1 met (nobody passes through another unit). With no function on the vestibule: not measured;
    marked residential, the reading said with the count names this case (every shared room marked a corridor or
    lobby)."""
    # s0 and s1 open into a room of use other (a vestibule) that opens outside
    desc = layout([("residential", 1, 0), ("residential", 1, 0), ("business", 1, 1)], (False, False))
    desc["rooms"].append(room("v", rect(0, 10.5, 23.5, 15), use="other", lockable=False, pass_through=True))
    desc["doors"] += [door("va", (5, 10.25), (1, 0), ("s0", "v")), door("vb", (17, 10.25), (1, 0), ("s1", "v")),
                      door("vc", (23.75, 12.75), (0, 1), ("v", "outside"))]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_function_unknown", got
    assert "shared between dwelling units is marked a corridor or lobby" in RESTS_ON
    assert "no room of a dwelling unit is marked a corridor, lobby or exit" in RESTS_ON   # review round 9


def test_the_listed_other_uses_are_table_1004_5_but_residential_and_sleeping():
    """NOT_DWELLING is every function in the frozen Table 1004.5 record but residential, dormitory and institutional
    sleeping, so the two can't drift."""
    import yaml
    from model_measurement.routes.dwelling_units import NOT_DWELLING
    record = REPO / ("regulations/jurisdictions/new_york/new_york_state_building/5_building_code_rules/drafted/"
                     "records/occupant_load_factors.yaml")
    table = set(yaml.safe_load(record.read_text(encoding="utf-8"))["functions"])
    assert NOT_DWELLING == table - {"residential", "dormitory", "institutional_sleeping"}


# --- review round 2 (PR 3) -----------------------------------------------------------------------------------------

def test_a_stair_in_a_group_or_not_read_never_counts_it_as_one_unit():
    """Suite 0 the upper floor of a two-story unit (its own stair down to its door, no door to the corridor), joined by
    a door to suite 1, a unit with its own door: one way out, but two units. A stair within the group, or stairs not
    read at all, leave the count not measured."""
    desc = layout([("residential", 1, 0), ("residential", 1, 1), ("business", 1, 1)], (True, False))
    assert count(desc) == 1                              # as drawn with no stair: the reading counts one
    desc["stairs"] = [{"id": "st", "nosings": [[[2, 2, 0], [2, 8, 0]], [[3, 2, 0.6], [3, 8, 0.6]]]}]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_stair", got
    del desc["stairs"]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_stair", got
    desc["stairs"] = []                                  # no stair, but a ramp not said to be none: may be anywhere
    desc["has_none"] = [c for c in desc["has_none"] if c["kind"] != "ramp"]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_stair", got
    with pytest.raises(TypeError):                       # no caller can leave the stair check out
        units_on(read(desc).stories["L1"], {}, _is_exit)
    with pytest.raises(TypeError):                       # nor the check that every door was read on the story
        units_on(read(desc).stories["L1"], {}, _is_exit, lambda g: False)



def test_no_stairs_beside_another_floor_is_never_taken():
    """"No stairs" (an empty list) beside rooms on a second level: a stair left undrawn may stand in any group, so the
    count isn't measured (#279's refusal of the same claim for the house's stair rules, merged into the story facts);
    on one level the claim is taken as before."""
    desc = layout([("residential", 1, 1), ("residential", 1, 1), ("business", 1, 1)], (False, False))
    assert count(desc) == 2
    desc["levels"].append({"id": "L2", "name": "Level 2", "elevation": 10})
    desc["rooms"].append({**room("u", rect(0, 0, 11.5, 10), use="other", lockable=True, pass_through=False),
                          "level": "L2", "floor_elevation": 10, "function": "residential"})
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_stair", got

def test_a_closet_between_two_rooms_of_a_group_may_be_shared():
    """Two residential rooms (one with a door to the corridor) each opening into a closet that sits between them:
    the closet may be shared by two units; not measured. A closet opening into one room only changes nothing."""
    desc = layout([("residential", 1, 1), ("residential", 1, 0), ("business", 1, 1)], (False, False))
    desc["rooms"].append(room("k", rect(0, 10.5, 23.5, 15), use="closet", lockable=False, pass_through=False))
    desc["doors"] += [door("k0", (5, 10.25), (1, 0), ("s0", "k")), door("k1", (17, 10.25), (1, 0), ("s1", "k"))]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_shared_room", got
    desc["doors"] = [d for d in desc["doors"] if d["id"] != "k1"]
    desc["doors"].append(door("e10", (15, -0.25), (1, 0), ("s1", "c")))
    assert count(desc) == 2


@pytest.mark.parametrize("function", ["business", "accessory_storage_mechanical"])
def test_a_shared_room_of_another_use_between_two_rooms_of_a_group_may_be_shared(function):
    """Review round 4 (PR 3): a vestibule or laundry (use other, a non-residential function) with the group's one way
    out, two units opening into it: counted one unit; 1016.2.1 doesn't catch it (nobody passes through another unit).
    A room of another function between two rooms of a group now leaves the count not measured."""
    desc = layout([("residential", 1, 0), ("residential", 1, 0), ("business", 1, 1)], (False, False))
    desc["rooms"].append(room("v", rect(0, 10.5, 23.5, 15), use="other", lockable=False, pass_through=True,
                              function=function))
    desc["doors"] += [door("va", (5, 10.25), (1, 0), ("s0", "v")), door("vb", (17, 10.25), (1, 0), ("s1", "v")),
                      door("vc", (23.75, 12.75), (0, 1), ("v", "outside"))]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_shared_room", got


@pytest.mark.parametrize("use", ["closet", "toilet", "accessory_storage"])
def test_a_closet_marked_residential_between_two_rooms_may_be_shared(use):
    """Review round 5 (PR 3): a closet, toilet or storeroom marked residential, opening onto two units' rooms: still
    maybe shared (the room's own use, not only its function, stops the count)."""
    desc = layout([("residential", 1, 1), ("residential", 1, 0), ("business", 1, 1)], (False, False))
    desc["rooms"].append(room("k", rect(0, 10.5, 23.5, 15), use=use, lockable=False, pass_through=False,
                              function="residential"))
    desc["doors"] += [door("k0", (5, 10.25), (1, 0), ("s0", "k")), door("k1", (17, 10.25), (1, 0), ("s1", "k"))]
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_shared_room", got


def _hidden(desc, how):
    """The description with one door moved, or made unreadable, onto a second level L2 (so L1 itself reads whole)."""
    desc["levels"].insert(0, {"id": "L2", "name": "Level 2", "elevation": 0})
    desc["rooms"].append(room("u", rect(-30, 0, -20, 10), use="other", lockable=False, pass_through=False,
                              level="L2"))
    if how == "moved":
        next(d for d in desc["doors"] if d["id"] == "e10")["level"] = "L2"
    elif how == "unreadable":
        desc["doors"].append(dict(desc["doors"][0], id="z", level="L2", sides="s1"))
    else:                                                # a door listed only among the openings
        desc["openings"] = [{"id": "p", "room": "s1", "operation": "sliding_door", "escape": False}]
    return desc


@pytest.mark.parametrize("how", ["moved", "unreadable", "opening"])
def test_a_units_own_door_drawn_on_another_level_never_undercounts(how):
    """Review round 7 (PR 3): suite 1's own door to the corridor drawn on another level vanished from its story (the
    routes stop only the door's own story), so the lock-off pair 0-1 had one way out: one unit, where there may be two
    (1016.2.1 doesn't catch it: each has its own door). The same for a door whose rooms can't be read, or one listed
    only among the openings. Every door and opening the description gives for the story's rooms must be read on it."""
    base = layout([("residential", 1, 1), ("residential", 1, 1), ("business", 1, 1)], (True, False))
    assert count(base).key == "units_entrances"
    desc = _hidden(layout([("residential", 1, 1), ("residential", 1, 1), ("business", 1, 1)], (True, False)), how)
    got = count(desc)
    key = "units_link_unread" if how == "unreadable" else "units_link_elsewhere"
    assert isinstance(got, Stop) and got.key == key, (how, got)
    story = {s["id"]: s for s in measure(desc)["parts"]["story"]}["L1"]
    assert UNITS_FACT not in story["measures"] and UNITS_FACT not in story.get("rests_on", {}), how


@pytest.mark.parametrize("how", ["exit", "lobby", "corridor"])
def test_a_unit_marked_an_exit_or_a_hall_never_drops_out_of_the_count(how):
    """Review round 8 (PR 3): a one-room unit whose door was marked an exit passageway into it (Revit takes the room
    every door of which is so marked as the exit), or the unit itself marked a lobby or corridor, became shared space
    and dropped out of the count: 3 units counted 2. A room taken as an exit that states a function, or a residential
    hall opening only into halls, exits or the outside, leaves the count not measured; a corridor stating no function
    still counts 3."""
    desc = layout([("residential", 1, 1)] * 3, (False, False))
    assert count(desc) == 3
    if how == "exit":
        d = next(d for d in desc["doors"] if d["id"] == "e20")
        d["exit_kind"], d["exit_id"] = "exit_passageway", "s2"
    else:
        next(r for r in desc["rooms"] if r["id"] == "s2")["use"] = how
    got = count(desc)
    key = "units_exit_function" if how == "exit" else "units_hall_residential"
    assert isinstance(got, Stop) and got.key == key, (how, got)


@pytest.mark.parametrize("hall, back", [("corridor", "toilet"), ("lobby", "closet"), ("corridor", "toilet_res")])
def test_a_unit_marked_a_hall_with_its_own_toilet_never_drops_out_of_the_count(hall, back):
    """Review round 9 (PR 3): a two-room unit marked a hall whose back room is a toilet or closet: the toilet is a group
    of its own (nothing lived in), so the "hall" opened into a space and passed round 8's check; the unit dropped out
    (3 counted 2). A residential hall must open into a room of a dwelling unit; a residential corridor serving units
    beside a public toilet still counts."""
    desc = layout([("residential", 1, 1), ("residential", 1, 1), ("residential", 2, 1)], (False, False))
    s2 = next(r for r in desc["rooms"] if r["id"] == "s2")
    b2 = next(r for r in desc["rooms"] if r["id"] == "b2")
    s2["use"] = hall
    b2["use"] = back.split("_")[0]
    if not back.endswith("_res"):
        b2.pop("function")
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_hall_residential", (hall, back, got)
    assert "no room of a dwelling unit" in got.reason                    # review round 10: the words say why
    control = layout([("residential", 1, 1), ("residential", 1, 1), ("business", 1, 1)], (False, False))
    next(r for r in control["rooms"] if r["id"] == "c")["function"] = "residential"
    assert count(control) == 2


@pytest.mark.parametrize("function", ["Residential", "residential ", "R-2", "dormitory", "institutional_sleeping",
                                      ["residential"], {"a": 1}])     # (round 11: not text crashed)
@pytest.mark.parametrize("hall", ["lobby", "corridor"])
def test_a_unit_marked_a_hall_stating_an_unlisted_function_never_drops_out(hall, function):
    """Review round 10 (PR 3): the hall check fired only on the exact word residential; a unit marked a hall stating a
    function not on the list (a typo, R-2, dormitory) dropped out (3 counted 2). Any function a dwelling unit may have
    stops it; a corridor stating a listed other use (business), or none, still counts 3."""
    desc = layout([("residential", 1, 1)] * 3, (False, False))
    s2 = next(r for r in desc["rooms"] if r["id"] == "s2")
    s2.update(use=hall, function=function)
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_hall_residential", (hall, function, got)
    control = layout([("residential", 1, 1)] * 3, (False, False))
    next(r for r in control["rooms"] if r["id"] == "c")["function"] = "business"
    assert count(control) == 3


def test_a_residential_corridor_beside_units_stating_no_function_says_to_mark_them():
    """Review round 11 (PR 3): a real corridor marked residential whose apartments state no function yet was told it
    "may be a dwelling unit marked a hall"; the actionable reason is the apartments' missing function."""
    desc = layout([(None, 1, 1)] * 3, (False, False))
    next(r for r in desc["rooms"] if r["id"] == "c")["function"] = "residential"
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_function_unknown", got


# --- the unit marks (Gordium: Unit, rooms[].unit): they replace the grouping where any room of the story has one ---

MARKS = (None, "A", "B")
WALK_ROOMS = ("s0", "s1", "b1", "s2")                    # the middle suite two rooms (s1, and b1 behind it)


def mark_oracle(marks, functions, joins):
    """The count from the marks, written apart from dwelling_units._marked: None where it may be another number,
    "inferred" where no room is marked. `marks`: each room's unit (WALK_ROOMS' order); `functions`: each suite's (b1
    takes s1's)."""
    if not any(marks):
        return "inferred"
    unit = dict(zip(WALK_ROOMS, marks))
    function = {"s0": functions[0], "s1": functions[1], "b1": functions[1], "s2": functions[2]}
    links = [("s1", "b1")] + [(f"s{i}", f"s{i + 1}") for i in range(2) if joins[i]]
    for rid in WALK_ROOMS:                               # a room with no mark that may be a unit's
        if unit[rid] is None and function[rid] != "business":
            return None
    names = {n for n in unit.values() if n}
    for n in names:
        rooms = {r for r in WALK_ROOMS if unit[r] == n}
        reached = {min(rooms)}
        for _ in range(4):
            reached |= {b for a, b in links if a in reached and b in rooms} | \
                {a for a, b in links if b in reached and a in rooms}
        if reached != rooms:
            return None                                  # one name on rooms apart: two units?
        if all(function[r] == "business" for r in rooms):
            return None                                  # a unit of no dwelling use
    return len(names)


def _items(desc, marks, functions):
    items = {r["id"]: dict(r) for r in desc["rooms"]}
    function = {"s0": functions[0], "s1": functions[1], "b1": functions[1], "s2": functions[2]}
    for rid, m in zip(WALK_ROOMS, marks):
        items[rid].pop("function", None)
        if function[rid]:
            items[rid]["function"] = function[rid]
        if m is not None:
            items[rid]["unit"] = m
    return items


def _count(story, desc, items):
    from model_measurement.routes import _links_listed, _stair_in, _stair_points, links_read_here
    stairs = _stair_points(desc)
    try:
        return units_on(story, items, _is_exit, lambda g: any(_stair_in(st, g, story) for st in stairs),
                        lambda: links_read_here(story, _links_listed(desc), "units"))
    except Stop as s:
        return s


def _room(desc, rid):
    return next(r for r in desc["rooms"] if r["id"] == rid)


@pytest.mark.parametrize("joins", list(itertools.product((False, True), repeat=2)), ids=str)
def test_the_marks_walk_every_count_measured_is_the_oracles(joins):
    """Every unit mark (none, A, B) on each of four rooms, every function per suite (residential, business, none), the
    suites joined or not: the count is the oracle's (the names given), or not measured where it may be another
    number; with no mark, the grouping counts (the walk above)."""
    desc = layout([("residential", 1, 1), ("residential", 2, 1), ("residential", 1, 1)], joins)
    story = read(desc).stories["L1"]
    seen = set()
    for marks in itertools.product(MARKS, repeat=4):
        for functions in itertools.product(FUNCTIONS, repeat=3):
            items = _items(desc, marks, functions)
            got, want = _count(story, desc, items), mark_oracle(marks, functions, joins)
            if want == "inferred":
                assert not marked(story, items)
                continue
            assert marked(story, items)
            if want is None:
                assert isinstance(got, Stop) and got.key in MARK_KEYS, (marks, functions, joins, got)
            else:
                assert got == want, (marks, functions, joins, got)
            seen.add(got if not isinstance(got, Stop) else got.key)
    assert {1, 2, "units_mark_left_out", "units_mark_not_dwelling", "units_mark_apart"} <= seen, seen


def test_a_shared_vestibule_marked_residential_no_longer_joins_two_units():
    """The grouping's first disclosed limit: a vestibule marked residential, two units off it, counted one unit. With
    the units marked, the vestibule with no mark stops the count (mark it a lobby, or a unit); a lobby with no
    function, 2."""
    desc = layout([("residential", 1, 0), ("residential", 1, 0), ("business", 1, 1)], (False, False))
    desc["rooms"].append(room("v", rect(0, 10.5, 23.5, 15), use="other", lockable=False, pass_through=True,
                              function="residential"))
    desc["doors"] += [door("va", (5, 10.25), (1, 0), ("s0", "v")), door("vb", (17, 10.25), (1, 0), ("s1", "v")),
                      door("vc", (23.75, 12.75), (0, 1), ("v", "outside"))]
    assert count(desc) == 1                              # the grouping: one group, one way out (the limit)
    _room(desc, "s0")["unit"], _room(desc, "s1")["unit"] = "1", "2"
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_mark_left_out", got
    _room(desc, "v")["use"] = "lobby"                     # a lobby stating residential, opening into both units
    assert count(desc) == 2                              # (its occupant load needs that function): shared, 2
    _room(desc, "v").pop("function")                     # stating none: a hall, 2
    assert count(desc) == 2
    story = {s["id"]: s for s in measure(desc)["parts"]["story"]}["L1"]
    assert story["measures"][UNITS_FACT] == 2
    assert story["architect_stated"][UNITS_FACT] == MARKED and UNITS_FACT not in story.get("rests_on", {})


@pytest.mark.parametrize("how", ["exit", "lobby", "corridor"])
def test_a_marked_unit_room_marked_a_hall_or_exit_still_counts(how):
    """The second disclosed limit: a unit's room marked a corridor or lobby with no function dropped out (3 counted 2).
    Marked with its unit it counts; marked an exit (a stair enclosure) and a unit, the two disagree: not measured."""
    desc = layout([("residential", 1, 1)] * 3, (False, False))
    for i in range(3):
        _room(desc, f"s{i}")["unit"] = f"Apt {i + 1}"
    s2 = _room(desc, "s2")
    s2.pop("function")
    if how == "exit":
        d = next(d for d in desc["doors"] if d["id"] == "e20")
        d["exit_kind"], d["exit_id"] = "exit_passageway", "s2"
        got = count(desc)
        assert isinstance(got, Stop) and got.key == "units_mark_on_exit", got
    else:
        s2["use"] = how
        assert count(desc) == 3
        s2.pop("unit")                                   # unmarked, it is a hall: the marks count the two named
        assert count(desc) == 2


@pytest.mark.parametrize("mark, key", [("1A, 1B", "units_mark_several"), ("1A and 1B", "units_mark_several"),
                                       ("1A/1B", "units_mark_several"), (["1A"], "units_mark_unreadable"),
                                       (True, "units_mark_unreadable"), (1.5, "units_mark_unreadable"),
                                       ("apt  1", "units_mark_alike"), ("APT 1", "units_mark_alike"),
                                       ("Apt1", "units_mark_alike")])    # (review round 4: spaces, not only case)
def test_a_mark_naming_two_units_or_none_or_alike_names_is_not_measured(mark, key):
    """A room marked with two units, a mark that isn't a name, or two names differing only in capitals or in where spaces stand (spaces at the ends and repeated spaces are no new name):
    the marks don't settle the count. A whole number is a name, and spacing at the ends is no new name (s1 and s2
    joined by a door: one unit's two rooms)."""
    desc = layout([("residential", 1, 1)] * 3, (False, True))
    for i, m in enumerate(("Apt 1", "Apt 2", mark)):
        _room(desc, f"s{i}")["unit"] = m
    got = count(desc)
    assert isinstance(got, Stop) and got.key == key, (mark, got)
    for m, want in ((3, 3), (" Apt 2 ", 2), ("Apt 3", 3), ("", "units_mark_left_out")):
        _room(desc, "s2")["unit"] = m
        got = count(desc)
        assert (got.key if isinstance(got, Stop) else got) == want, (m, got)


def test_a_two_story_units_own_stair_doesnt_stop_the_marks_count():
    """The grouping stops where a stair may stand in a group (the upper floor of a unit whose door is downstairs);
    the marks name the unit, so a stair within it changes no count: the story counts the units with a room on it."""
    desc = layout([("residential", 2, 1), ("residential", 1, 1), ("business", 1, 1)], (False, False))
    desc["stairs"] = [{"id": "own", "nosings": [[[3, 12, 0], [3, 14, 0]]]}]          # in b0, the unit's own stair
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_stair", got
    for rid, name in (("s0", "1"), ("b0", "1"), ("s1", "2")):
        _room(desc, rid)["unit"] = name
    assert count(desc) == 2


def test_with_no_mark_the_grouping_and_its_words_stay():
    desc = layout([("residential", 1, 1)] * 3, (False, False))
    story = {s["id"]: s for s in measure(desc)["parts"]["story"]}["L1"]
    assert story["measures"][UNITS_FACT] == 3 and story["rests_on"][UNITS_FACT] == RESTS_ON
    assert UNITS_FACT not in story.get("architect_stated", {})
    for blank in ("", "   ", None):                      # a blank mark is no mark
        for r in desc["rooms"]:
            r["unit"] = blank
        assert count(desc) == 3 and not marked(read(desc).stories["L1"], {r["id"]: r for r in desc["rooms"]})


@pytest.mark.parametrize("hall", ["lobby", "corridor"])
@pytest.mark.parametrize("function", ["residential", "R-2", None, "business"])
def test_an_unmarked_hall_stating_a_units_function_must_open_into_two_named_units(hall, function):
    """Review rounds 1 and 2 (PR 1): a one-room unit marked a lobby or corridor, stating residential, no unit mark,
    joined by a door to one marked unit: the grouping's hall check lets a hall opening into a unit's room through, so
    the marks counted 2 of 3. Under the marks a hall stating a function a unit may have is shared only where it opens
    into rooms of two or more named units (a building's residential lobby: its occupant load needs that function);
    into one, it stops the count. One stating none, or a listed other use, is a hall (2 counted: the limit said)."""
    desc = layout([("residential", 1, 1)] * 3, (False, True))
    _room(desc, "s0")["unit"], _room(desc, "s1")["unit"] = "A", "B"
    s2 = _room(desc, "s2")
    s2["use"] = hall
    s2.pop("function")
    if function is not None:
        s2["function"] = function
    got = count(desc)
    if function in ("residential", "R-2"):
        assert isinstance(got, Stop) and got.key == "units_mark_hall_function", (hall, function, got)
    else:
        assert got == 2, (hall, function, got)
    if function in ("residential", "R-2"):               # into two named units (A's and B's rooms): shared
        desc = layout([("residential", 1, 1)] * 3, (True, True))
        _room(desc, "s0")["unit"], _room(desc, "s2")["unit"] = "A", "B"
        _room(desc, "s1").update(use=hall, function=function)
        assert count(desc) == 2, (hall, function)        # (a studio so marked can't be told apart: the words say so)
        assert "marked a corridor, lobby or exit can't be told from a room shared between units" in MARKED


def test_an_entry_lobby_stating_residential_into_no_unit_stops_with_words_that_dont_ask_a_mark_check():
    """Review round 3 (PR 1): an entry lobby between the corridor and the outside, stating residential (its occupant
    load needs a function), opens into no unit's room: it stops the marks' count (it may be a unit marked a lobby), and
    the reason no longer tells the architect to check marks that can't clear it."""
    desc = layout([("residential", 1, 1)] * 3, (False, False))
    for i in range(3):
        _room(desc, f"s{i}")["unit"] = f"U{i}"
    desc["rooms"].append(room("L", rect(-6.5, -6.5, -0.5, -0.5), use="lobby", lockable=False, pass_through=True,
                              function="residential"))
    x = next(d for d in desc["doors"] if d["id"] == "x")
    x["sides"] = ["L", "outside"]
    x["plan"]["centre"] = [-6.75, -3.5]
    desc["doors"].append(door("cl", (-0.25, -3.5), (0, 1), ("c", "L")))
    got = count(desc)
    assert isinstance(got, Stop) and got.key == "units_mark_hall_function", got
    assert "check the units' marks" not in got.reason and "mark its unit if it is one" in got.reason
    _room(desc, "L").pop("function")                     # stating none: a hall, the three units counted
    assert count(desc) == 3
