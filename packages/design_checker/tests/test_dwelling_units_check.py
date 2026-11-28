"""The dwelling units on a story (model_measurement/routes/dwelling_units.py) through the Building Code check: the
count rests on Gordium's reading that each group of rooms with one door to the corridors, exits or outside is one
dwelling unit, which holds only if BCNYS 1016.2.1 is met (p.341: "each tenant space, dwelling unit and sleeping unit
shall be provided with access to the required exits without passing through adjacent tenant spaces, dwelling units
and sleeping units"). The count never holds a pass back, so wherever it lets Table 1006.3.4(1)'s row pass, the
answer must also ask a person about 1016.2.1 (its flag), and the row's own line must say the reading.

The building: the four-unit apartment (as the Revit reader reads it once marked) with its east stair's doors unmarked
(one exit a story; the east stair a storeroom), stated Group R-2 of dwelling units, flat ground at 0."""

import copy
import itertools
import sys

import pytest

from design_checker import egress
from model_measurement.routes.dwelling_units import QUOTE_1016_2_1
from rule_format import parts
from rule_format.rulebook import REPO, Context, load

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
import make_ny_build_data as build  # noqa: E402

PLACE = "regulations/jurisdictions/new_york/ithaca_city"
ROW = "general.bc_table_1006_3_4_1__r2_dwelling_units"
FLAG = "general.bc_1016_2_1_multiple_tenants"
UNITS = "story_dwelling_units"
VALUES = {"use": "multiple_family", "dwelling_units": 4}
RULES = REPO / "regulations/jurisdictions/new_york/new_york_state_building/5_building_code_rules/drafted/general.yaml"


def _check(interior):
    allowed = Context.for_jurisdiction(REPO / PLACE).allowed()
    return egress.check(egress.laws(PLACE), copy.deepcopy(interior), VALUES, allowed, ground={"flat": 0.0})


def test_the_r2_row_passes_on_the_measured_count_saying_the_reading_and_1016_2_1_is_asked():
    """One exit a story, 2 units each (measured), 53.95 ft of travel, an NFPA 13 system and escape openings: Table
    1006.3.4(1) allows it; the row's line says the reading and 1016.2.1, and the 1016.2.1 flag is in the answer."""
    interior = build.interior_of()
    got = _check({**interior, **_one_exit_building(interior, "nfpa_13")})
    assert got["results"][ROW] == "pass"
    rows = [r for r in got["rows"] if r["rule"] == ROW]
    assert [r["outcome"] for r in rows] == ["pass", "pass"]
    assert all(any("1016.2.1 (p.341)" in w and QUOTE_1016_2_1 in w for w in r["rests_on"]) for r in rows)
    lines = [i for i in got["items"] if i.get("rule") == ROW]
    assert lines and all(QUOTE_1016_2_1 in str(i) for i in lines)          # the panel's line says it too
    assert got["results"][FLAG] == "needs_review"


def _one_exit_building(interior, sprinkler):
    """The one-exit apartment's keys (the fixture's, with `sprinkler`), for a walk over its settings."""
    i = copy.deepcopy(interior)
    names = {r["id"]: r["name"].upper() for r in i["rooms"]}
    for d in i["doors"]:
        if d.get("exit_id") and "EAST" in names.get(d["exit_id"], ""):
            d.pop("exit_kind"), d.pop("exit_id")
    for r in i["rooms"]:
        if "STAIR EAST" in r["name"].upper():
            r["function"] = "accessory_storage_mechanical"
    i["building"] = {**i["building"], "occupancy_groups": ["R-2"], "sprinkler_system": sprinkler,
                     "assembly_fixed_seating": False, "special_egress_spaces": False, "occupant_load_increased": False,
                     "r2_sleeping_units": False, "emergency_escape_openings_1031": True,
                     "corridors_within_dwelling_units": False,
                     "underground_building": False}    # 405.7.1 (main's Chapter 4): no floor 30 ft below discharge
    i["stairs"] = [{"id": "flight west", "nosings": [[[4.5, 13, 0], [4.5, 17, 0]]]}]    # within the west enclosure
    i["has_none"] = [{"kind": k, "source": "the eval building: none drawn"}
                     for k in ("ramp", "alternating_tread_device", "ships_ladder")]
    return {k: i[k] for k in ("doors", "rooms", "building", "stairs", "has_none")}


@pytest.mark.parametrize("sprinkler,residential", list(itertools.product(("none", "nfpa_13r", "nfpa_13"), (0, 1, 2))))
def test_wherever_a_measured_count_lets_the_r2_row_pass_1016_2_1_is_asked_in_the_same_answer(sprinkler,
                                                                                             residential):
    """The pin: over the sprinkler system and how many apartments state their function (none, one, both), every
    passing Table 1006.3.4(1) row whose story's count was measured comes with the 1016.2.1 flag needing review in the
    same answer, and the count's reading in the row."""
    interior = build.interior_of()
    interior.update(_one_exit_building(interior, sprinkler))
    apartments = [r for r in interior["rooms"] if "APARTMENT" in r["name"].upper()]
    for k, r in enumerate(sorted(apartments, key=lambda r: r["name"])):
        if k % 2 >= residential:                         # the first `residential` of each story's pair keep it
            r.pop("function", None)
    got = _check(interior)
    measured = {s["id"] for s in got["interior"]["parts"]["story"] if UNITS in s["measures"]}
    passing = [r for r in got["rows"] if r["rule"] == ROW and r["outcome"] == "pass"]
    for r in passing:
        assert r["id"] in measured or UNITS not in r["values"] or r["values"][UNITS] is None, r
        if r["values"].get(UNITS) is not None:
            assert got["results"][FLAG] == "needs_review", (sprinkler, residential)
            assert any(QUOTE_1016_2_1 in w for w in r.get("rests_on") or []), r
    if sprinkler == "nfpa_13" and residential == 2:
        assert passing, "the walk must reach a pass on a measured count"
    if sprinkler == "nfpa_13r":                          # never on a 13R system alone (its limits aren't known)
        assert not passing, passing


def test_the_1016_2_1_flag_is_never_set_aside_in_group_r2():
    """The flag the count rests on applies whatever the building states: no applies_when, or one true for Group R-2
    under every setting (so no building fact can drop the question while the count passes the row)."""
    rule = next(r for r in load(RULES)["rules"] if r["id"] == FLAG)
    assert rule["kind"] == "flag" and not rule.get("applies_when"), rule.get("applies_when")


def test_counted_from_the_unit_marks_the_row_says_the_marks_not_the_reading():
    """Each apartment marked with its unit (Revit's room mark Gordium: Unit): the count is the marks' (2 a story), the
    row's line says it stands on them (the architect's statement), and no longer Gordium's grouping reading; a marked
    room the drawing takes as an exit stops it (needs review, never a pass)."""
    from model_measurement.routes.dwelling_units import MARKED
    interior = build.interior_of()
    interior.update(_one_exit_building(interior, "nfpa_13"))
    for r in interior["rooms"]:
        if "APARTMENT" in r["name"].upper():
            r["unit"] = r["name"]
    got = _check(interior)
    rows = [r for r in got["rows"] if r["rule"] == ROW]
    assert [r["outcome"] for r in rows] == ["pass", "pass"] and all(r["values"][UNITS] == 2 for r in rows)
    assert all(MARKED in r["architect_stated"] and not r.get("rests_on") for r in rows)
    assert all(MARKED in str(i) for i in got["items"] if i.get("rule") == ROW)
    stair = next(r for r in interior["rooms"] if "STAIR WEST" in r["name"].upper() and r["level"].endswith("1"))
    stair["unit"] = "Apartment 1"
    got = _check(interior)
    assert got["results"][ROW] == "needs_review"
    why = {s["id"]: s["not_measured"].get(UNITS, "") for s in got["interior"]["parts"]["story"]}
    assert "is taken as an exit" in why[stair["level"]] and "marked unit 'Apartment 1'" in why[stair["level"]], why


@pytest.mark.parametrize("stories", [None, 2])
def test_a_13r_system_alone_never_passes_the_one_exit_row(stories):
    """The pass path the measured count opens, closed where it rests on a stated NFPA 13R system: note a asks a building
    sprinklered per 903.3.1.1 or 903.3.1.2, and 903.3.1.2 permits 13R only four stories or fewer above grade plane with
    a Group R-2 roof under 45 ft above the lowest fire department access, a height the model doesn't show (stated
    stories, two here, don't settle it). So the same one-exit apartment that passes with NFPA 13 needs review with 13R
    and never passes, saying why (the coordinator's decision, 2026-11-28)."""
    interior = build.interior_of()
    keys = _one_exit_building(interior, "nfpa_13r")
    if stories is not None:
        keys["building"]["stories_above_grade_plane"] = stories
    got = _check({**interior, **keys})
    rows = [r for r in got["rows"] if r["rule"] == ROW]
    assert got["results"][ROW] == "needs_review" and rows
    assert all(r["outcome"] == "needs_review" and r["values"][UNITS] == 2 for r in rows), rows
    # the row says the rule's own reason, all three of 903.3.1.2's conditions, not the occupant-load open question
    # its readings leave (whatever the answer, 13R still needs review: parts._own_reviews)
    for r in rows:
        assert r["reason"].startswith("One exit, allowed by note a only through an NFPA 13R system (903.3.1.2)"), r
        assert all(w in r["reason"] for w in ("four stories or fewer above grade plane", "less than 45 feet above",
                                               "30 feet or less below")), r["reason"]
        assert not parts.is_reading_words(r["reason"]), r["reason"]
    assert all("only through an NFPA 13R system" in str(i) for i in got["items"] if i.get("rule") == ROW)
    sprinklered = _check({**interior, **_one_exit_building(interior, "nfpa_13")})
    assert sprinklered["results"][ROW] == "pass"                 # the same building with NFPA 13: the pass stands
