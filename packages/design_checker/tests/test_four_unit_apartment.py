"""The Building Code eval (test_data/test_sites/new_york/ithaca_city/four_unit_apartment): Gordium's two-story,
four-unit building, as the Revit reader reads it once built from revit_build_data.json and marked by eval_marks.yaml
(make_ny_build_data.interior_of), checked against its hand-worked expected.yaml: the Building Code governs, its rules
run on the routes' stories and spaces, the occupant-load rules say they need a figure not read yet, its group's
table rows give real verdicts (2026-11-23), and every flag is its own needs-review line. Never a pass the hand-work
doesn't give."""

import math
import sys

import pytest

from design_checker import code_scope, egress, present
from rule_format.rulebook import REPO, Context, load

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
import make_ny_build_data as build  # noqa: E402

FOLDER = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment"
VALUES = {"use": "multiple_family", "dwelling_units": 4}
ALLOWED = Context.for_jurisdiction(REPO / "regulations/jurisdictions/new_york/ithaca_city").allowed()


@pytest.fixture(scope="module")
def laws():
    return egress.laws("regulations/jurisdictions/new_york/ithaca_city")


@pytest.fixture(scope="module")
def got(laws):
    return egress.check(laws, build.interior_of(), VALUES, ALLOWED)


@pytest.fixture(scope="module")
def expected():
    return load(FOLDER / "expected.yaml")


def test_the_building_code_governs_it(got, expected):
    assert [s["title"] for s in got["sections"]] == ["Egress (NY State Building Code 2025)"]
    which = egress.which_code(got)
    assert {k: which[k] for k in ("code", "title", "why")} == expected["which_code"]
    assert which["code"] == code_scope.BUILDING


def test_every_rules_answer_is_the_hand_worked_one(got, expected):
    assert got["results"] == expected["results"]
    assert got["sections"][0]["state"] == expected["state"]


def test_the_story_figures_are_the_hand_worked_ones(got, expected):
    stories = got["interior"]["parts"]["story"]
    assert [s["id"] for s in stories] == ["L1", "L2"]
    for s in stories:
        assert s["measures"]["story_exit_count"] == expected["stories"]["story_exit_count"]
        assert s["measures"]["exit_remoteness_ratio"] == pytest.approx(41 / math.hypot(61, 31), abs=1e-9)
        assert round(s["measures"]["exit_remoteness_ratio"], 4) == expected["stories"]["exit_remoteness_ratio"]
    rows = [r for r in got["rows"] if r["rule"] == "general.bc_1007_1_1_remoteness"]
    assert [(r["id"], r["outcome"]) for r in rows] == [("L1", "pass"), ("L2", "pass")]
    assert all(p["measures"]["space_exit_count"] == expected["spaces"]["space_exit_count"]
               for p in got["interior"]["parts"]["space"])


def test_a_rule_reading_a_figure_not_measured_yet_says_so(got):
    rows = [i for i in got["items"] if i["rule"] == "general.bc_1006_3_3_story_exits"]
    assert len(rows) == 2 and all(i["status"] == present.REVIEW for i in rows)
    assert all("occupant load not measured" in i["reason"] for i in rows)   # its plain name (C4)


def test_each_flag_is_its_own_line_with_its_section(got):
    """24 of the rulebook's 32 flags show (2026-11-23; 1006.2.2's five rooms by use since review round 1; 1030.8's
    on its fact alone since round 2): those narrowed to a building of two or more groups, or to
    another group (F-1 and S-1's increase, H-5's, Group H's sprinkler system), are not applicable to a one-group R-2."""
    flags = [i for i in got["items"] if i["reason"].startswith("A person checks this")]
    assert len(flags) == 24 and all(i["status"] == present.REVIEW and i["code"]["section"] for i in flags)


def test_its_groups_rows_give_real_verdicts(got, expected):
    """Group R-2, no sprinkler system (2026-11-23): each story's travel within Table 1017.2's 200 ft (a verdict that
    waits on special_egress_spaces, review round 1), no dead end,
    and each apartment's one door fails Table 1006.2.1's R-2 row (Not Permitted without a sprinkler system); the
    stair enclosures are exits, so that row asks nothing of them."""
    for s in got["interior"]["parts"]["story"]:
        assert s["measures"]["egress_travel_distance"] <= expected["egress_travel_distance_at_most"]
    is_exit = {p["name"].split(" L")[0]: p["measures"]["space_is_exit"] for p in got["interior"]["parts"]["space"]}
    assert is_exit == expected["spaces"]["space_is_exit"]
    rows = {(r["name"], r["outcome"]) for r in got["rows"] if r["rule"] == "general.bc_table_1006_2_1_r2"}
    assert {o for n, o in rows if n.startswith("Apartment")} == {"fail"}
    assert {o for n, o in rows if n.startswith("Stair")} == {"pass"}


def test_the_build_data_is_made_from_the_building(tmp_path):
    assert build.main(["--check"]) == 0                      # revit_build_data.json is apartment.yaml's, current


# ---- PR #181 review (2026-11-24): a space that is itself an exit is not one 1006.2.1 or 1007.1 counts ---------------

SPACE_EXIT_RULES = ("general.bc_1006_2_1_two_exits", "general.bc_1006_2_1_1_three_or_more_exits",
                    "general.bc_1007_1_1_space_remoteness", "general.bc_1007_1_2_space_three_or_more")


@pytest.mark.parametrize("sprinkler_system", ["none", "nfpa_13"])
def test_an_exit_stair_is_never_held_to_the_exits_of_the_spaces_it_serves(sprinkler_system):
    """Group I-4's two-exit rule failed each stair enclosure (one door, no sprinkler system) and needed review with
    one: 1006.2.1 and 1007.1 ask for the exits of the spaces exit access serves, never of an exit itself (202 EXIT;
    the routes mark a room entered by an exit-enclosure door as space_is_exit). The same building as Group I-4."""
    import copy
    interior = copy.deepcopy(build.interior_of())
    interior["building"] = {**(interior.get("building") or {}), "occupancy_groups": ["I-4"],
                            "sprinkler_system": sprinkler_system}
    got = egress.check(egress.laws("regulations/jurisdictions/new_york/ithaca_city"), interior, VALUES, ALLOWED)
    stairs = [r for r in got["rows"] if r["rule"] in SPACE_EXIT_RULES and r["name"].startswith("Stair")]
    assert {r["rule"] for r in stairs} >= {"general.bc_1006_2_1_two_exits"}
    assert {(r["rule"], r["outcome"]) for r in stairs} == {(r["rule"], "pass") for r in stairs}


# the five Project Information Yes/No marks Revit sends for the Building Code's Chapter 10 (Marks.cs: Fixed assembly
# seating, Special egress spaces, Merchandise pads, Egress balcony increase, Atrium), by their building block keys
CH10_BUILDING_MARKS = ("assembly_fixed_seating", "special_egress_spaces", "merchandise_pads",
                       "egress_balcony_increase_taken", "building_has_atrium")


@pytest.mark.parametrize("stated", [False, True])
def test_the_five_chapter_10_marks_stated_move_only_the_rules_that_read_them(got, laws, stated):
    """The apartment as built, with the five marks set: No moves exactly the ten rules that wait on them (travel's
    54 ft within Table 1017.2's 200 ft now passes; each flag of a space the building states it hasn't is not
    applicable), and Yes leaves every rule as it was with them blank (needs review: a person checks those spaces),
    never a pass. Left blank they are not sent (the add-in's BuildingFacts), so `got` is the unset reading."""
    interior = build.interior_of()
    interior["building"] = {**interior["building"], **{k: stated for k in CH10_BUILDING_MARKS}}
    now = egress.check(laws, interior, VALUES, ALLOWED)
    moved = {k: (got["results"][k], now["results"][k]) for k in got["results"] if got["results"][k] != now["results"][k]}
    if stated:
        assert moved == {}
        return
    assert moved == {"general.bc_table_1017_2_a_e_f1_m_r_s1": ("needs_review", "pass"),
                     **{f"general.{r}": ("needs_review", "not_applicable") for r in (
                         "bc_1006_2_2_1_boiler_rooms", "bc_1006_2_2_2_refrigeration_machinery_rooms",
                         "bc_1006_2_2_3_refrigerated_rooms", "bc_1006_2_2_4_electrical_rooms",
                         "bc_1006_2_2_5_vehicular_ramps", "bc_table_1017_2_note_a", "bc_1017_2_1_balcony_increase",
                         "bc_1017_3_2_3_atrium", "bc_1030_8_fixed_seating_common_path")}}
