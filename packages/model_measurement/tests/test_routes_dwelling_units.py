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
UNITS_KEYS = {"units_use_unknown", "units_function_unknown", "units_no_entrance", "units_entrances"}
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
    return description(rooms, doors)


def count(desc):
    story = read(desc).stories["L1"]
    try:
        return units_on(story, {r["id"]: r for r in desc["rooms"]}, _is_exit)
    except Stop as s:
        return s


def oracle(suites, joins):
    """The story's count, or None where a group may hold another number of units."""
    owner = [0, 1, 2]
    for i, joined in enumerate(joins):
        if joined:
            old = owner[i + 1]
            owner = [owner[i] if o == old else o for o in owner]
    total = 0
    for o in set(owner):
        members = [suites[i] for i in range(3) if owner[i] == o]
        functions = {f for f, _, _ in members}
        doors = sum(e for _, _, e in members)
        if "residential" not in functions:
            if None in functions:
                return None                              # no function stated: a unit or not
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
    for s in measure(build.interior_of())["parts"]["story"]:
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
    assert seen == UNITS_KEYS
