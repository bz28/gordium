"""The Building Code eval (test_data/test_sites/new_york/ithaca_city/four_unit_apartment): Gordium's two-story,
four-unit building, as the Revit reader reads it once built from revit_build_data.json and marked by eval_marks.yaml
(make_ny_build_data.interior_of), checked against its hand-worked expected.yaml: the Building Code governs, its rules
run on the routes' stories and spaces, the occupant-load rules say they need a figure not read yet, and every flag
is its own needs-review line. Never a pass the hand-work doesn't give."""

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


def test_a_rule_reading_a_figure_not_measured_yet_says_so(got):
    rows = [i for i in got["items"] if i["rule"] == "general.bc_1006_3_3_story_exits"]
    assert len(rows) == 2 and all(i["status"] == present.REVIEW for i in rows)
    assert all("story occupant load not measured" in i["reason"] for i in rows)


def test_each_flag_is_its_own_line_with_its_section(got):
    flags = [i for i in got["items"] if i["reason"].startswith("A person checks this")]
    assert len(flags) == 23 and all(i["status"] == present.REVIEW and i["code"]["section"] for i in flags)


def test_the_build_data_is_made_from_the_building(tmp_path):
    assert build.main(["--check"]) == 0                      # revit_build_data.json is apartment.yaml's, current
