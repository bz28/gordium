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
from rule_format.rulebook import REPO, load

sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
import make_ny_build_data as build  # noqa: E402

FOLDER = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment"
VALUES = {"use": "multiple_family", "dwelling_units": 4}


@pytest.fixture(scope="module")
def got():
    return egress.check(egress.laws("regulations/jurisdictions/new_york/ithaca_city"), build.interior_of(), VALUES,
                        {"use": set()})


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


def test_the_occupant_loads_come_from_each_rooms_function(got):
    """Section group 3 (2026-11-23): each apartment's stated function (residential, 200 gross) gives its occupant
    load as two readings, 690 / 200 from its own area and 690 / 7 while 1004.5.1's increase isn't ruled out; both at
    most 500, so 1006.2.1.1 needs no third exit; the stair enclosures are exits and hold no load."""
    for p in got["interior"]["parts"]["space"]:
        values = [r["value"] for r in (p.get("readings") or {}).get("space_occupant_load") or []]
        if p["name"].startswith("Apartment"):
            assert values == pytest.approx([690 / 200, 690 / 7])
        else:
            assert values == [] and "space_occupant_load" not in p["measures"]
    rows = [r for r in got["rows"] if r["rule"] == "general.bc_1006_2_1_1_three_or_more_exits"]
    assert len(rows) == 8 and {r["outcome"] for r in rows} == {"pass"}


def test_each_flag_is_its_own_line_with_its_section(got):
    """23 of the rulebook's 34 flags show (2026-11-23; 1006.2.2's five rooms by use since review round 1; the
    mixed-occupancy single-exit flags not applicable since section group 2; 1030.8's on its fact alone since round
    2): those narrowed to a building of two or more groups, or to another group (F-1 and S-1's increase, H-5's,
    Group H's sprinkler system), are not applicable to a one-group R-2."""
    flags = [i for i in got["items"] if i["reason"].startswith("A person checks this")]
    assert len(flags) == 23 and all(i["status"] == present.REVIEW and i["code"]["section"] for i in flags)


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
