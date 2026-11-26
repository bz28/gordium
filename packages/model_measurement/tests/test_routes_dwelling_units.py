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
from model_measurement.routes.dwelling_units import QUOTE_1016_2_1, RESTS_ON, units_on  # noqa: E402
from model_measurement.routes.floor import read  # noqa: E402
from model_measurement.routes.stops import STOPS, Stop  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
UNITS_KEYS = {"units_use_unknown", "units_function_unknown", "units_no_entrance", "units_entrances", "units_stair",
              "units_shared_room"}
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
    from model_measurement.routes import _stair_in, _stair_points
    story = read(desc).stories["L1"]
    stairs = _stair_points(desc)
    try:
        return units_on(story, {r["id"]: r for r in desc["rooms"]}, _is_exit,
                        lambda g: any(_stair_in(st, g, story) for st in stairs))
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
