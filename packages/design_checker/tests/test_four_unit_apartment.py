"""The Building Code eval (test_data/test_sites/new_york/ithaca_city/four_unit_apartment): Gordium's two-story,
four-unit building, as the Revit reader reads it once built from revit_build_data.json and marked by eval_marks.yaml
(make_ny_build_data.interior_of), checked against its hand-worked expected.yaml: the Building Code governs, its rules
run on the routes' stories and spaces, the occupant-load rules say they need a figure not read yet, its group's
table rows give real verdicts (2026-11-23), and every flag is its own needs-review line. Never a pass the hand-work
doesn't give."""

import copy
import math
import re
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
def routes():
    """The building's routes, measured once (a room's function changes no geometry)."""
    return egress.measure_routes(build.interior_of())


def _check(desc, routes):
    with pytest.MonkeyPatch.context() as m:
        m.setattr(egress, "measure_routes", lambda interior: copy.deepcopy(routes))
        return egress.check(egress.laws("regulations/jurisdictions/new_york/ithaca_city"), desc, VALUES, ALLOWED)


@pytest.fixture(scope="module")
def got(routes):
    return _check(build.interior_of(), routes)


@pytest.fixture(scope="module")
def before(routes):
    """The same building with no room function stated: as it was before section group 3."""
    desc = build.interior_of()
    for r in desc["rooms"]:
        r.pop("function", None)
    return _check(desc, routes)


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


def test_before_and_after_the_functions_only_rules_reading_an_occupant_load_change_and_only_from_needs_review(
        got, before):
    """The apartment before section group 3 (no function stated: 1006.2.1.1 needs review, its reason naming the
    missing Gordium: Function mark) and after (residential: it passes). Stating a function only settles a rule that
    reads an occupant load and needed review for want of one; it never turns a verdict over."""
    rule = "general.bc_1006_2_1_1_three_or_more_exits"
    assert before["results"][rule] == present.REVIEW and got["results"][rule] == "pass"
    rows = [i for i in before["items"] if i["rule"] == rule]
    assert len(rows) == 8 and sum("Gordium: Function" in i["reason"] for i in rows) == 4     # each apartment's
    assert [i["status"] for i in rows].count(present.REVIEW) == 4                            # the stairs are exits
    rules = {r["id"]: r for r in load(REPO / "regulations/jurisdictions/new_york/new_york_state_building"
                                      / "5_building_code_rules/drafted/general.yaml")["rules"]}
    changed = {k for k in got["results"] if got["results"][k] != before["results"].get(k)}
    assert rule in changed
    for k in changed:
        r = rules[k.split(":")[0]] if k.split(":")[0] in rules else None
        assert r is not None and re.search(r"(space|story)_occupant_load", str(
            [r.get(f) for f in ("check", "review_when", "applies_when")])), k
        assert before["results"][k] == present.REVIEW, (k, before["results"][k])


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
