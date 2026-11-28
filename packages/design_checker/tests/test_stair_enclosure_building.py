"""The stair test building end to end (test_data/test_sites/new_york/stair_enclosure/: an R-2 building's exit stair
enclosure with a two-flight switchback stair, compliant and with known failures, section group 7 of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): the Building Code check, run on each variant as a
host sends it, gives the compliant one no fail, and the failing one a fail on exactly the Section 1011 rules it was
built to break, on exactly the flights that break them (8 in risers on both, 76 in headroom on flight 2, one handrail
on flight 2). Each flight stands in the exit enclosure its doors enter, so no dwelling-unit exception reaches it."""

import pytest
import yaml

from design_checker import egress
from rule_format.rulebook import REPO, Context

HERE = REPO / "test_data/test_sites/new_york/stair_enclosure"
VALUES = {"use": "multiple_family", "dwelling_units": 4}
LAWS = "regulations/jurisdictions/new_york/ithaca_city"


@pytest.fixture(scope="module")
def checked():
    allowed = Context.for_jurisdiction(REPO / LAWS).allowed()
    laws = egress.laws(LAWS)
    out = {}
    for variant in ("compliant", "failing"):
        d = yaml.safe_load((HERE / f"stair_enclosure_{variant}.yaml").read_text(encoding="utf-8"))
        out[variant] = egress.check(laws, d, VALUES, allowed)
    return out


def _stair_rows(got):
    return {(r["rule"], r["id"]): r["outcome"] for r in got["rows"] if r["rule"].startswith("general.bc_1011_")}


def test_the_building_code_checks_both_and_every_flight_is_in_the_exit_enclosure(checked):
    for got in checked.values():
        assert [s["title"] for s in got["sections"]] == ["Egress (NY State Building Code 2025)"]
        stairs = {p["id"]: p for p in got["interior"]["parts"]["stair"]}
        assert set(stairs) == {"f1", "f2"}
        assert all(p["measures"]["stair_in_exit_enclosure"] is True and p["measures"]["stair_riser_count"] == 9
                   for p in stairs.values())


def test_the_compliant_stair_fails_nothing(checked):
    got = checked["compliant"]
    assert [k for k, o in got["results"].items() if o == "fail"] == []
    rows = _stair_rows(got)
    for f in ("f1", "f2"):
        for rule in ("general.bc_1011_3_stair_headroom", "general.bc_1011_5_2_riser_height",
                     "general.bc_1011_5_2_tread_depth", "general.bc_1011_5_4_riser_uniformity",
                     "general.bc_1011_11_stair_handrails"):
            assert rows[(rule, f)] == "pass", (rule, f)
        # 44 in but no sprinkler system: 1009.3 may ask more of a stair in an accessible means of egress; the
        # treads' variation isn't given to the rules; landings and the rest of 1011 are flags
        for rule in ("general.bc_1011_2_stair_width", "general.bc_1011_5_4_tread_uniformity",
                     "general.bc_1011_6_stair_landings", "general.bc_1011_1_stairways_general"):
            assert rows[(rule, f)] == "needs_review", (rule, f)


def test_the_failing_stair_fails_exactly_what_it_was_built_to_break(checked):
    got = checked["failing"]
    fails = {k for k, o in got["results"].items() if o == "fail"}
    assert fails == {"general.bc_1011_5_2_riser_height", "general.bc_1011_3_stair_headroom",
                     "general.bc_1011_11_stair_handrails"}
    failed_rows = {k for k, o in _stair_rows(got).items() if o == "fail"}
    assert failed_rows == {("general.bc_1011_5_2_riser_height", "f1"), ("general.bc_1011_5_2_riser_height", "f2"),
                           ("general.bc_1011_3_stair_headroom", "f2"), ("general.bc_1011_11_stair_handrails", "f2")}
    # everything else about the stair as the compliant one's
    same = {k: o for k, o in _stair_rows(checked["compliant"]).items() if k not in failed_rows}
    assert {k: o for k, o in _stair_rows(got).items() if k not in failed_rows} == same


def test_marked_in_no_exit_enclosure_its_failures_need_review_never_pass(checked):
    """With its doors' exit marks taken off, the routes can't tell an enclosure (the flights' room isn't worked out),
    so a dwelling-unit exception may reach each flight: what failed needs review, and nothing passes that failed."""
    d = yaml.safe_load((HERE / "stair_enclosure_failing.yaml").read_text(encoding="utf-8"))
    for door in d["doors"]:
        door.pop("exit_kind")
        door.pop("exit_id")
    got = egress.check(egress.laws(LAWS), d, VALUES, Context.for_jurisdiction(REPO / LAWS).allowed())
    rows = _stair_rows(got)
    for key in (("general.bc_1011_5_2_riser_height", "f1"), ("general.bc_1011_3_stair_headroom", "f2"),
                ("general.bc_1011_11_stair_handrails", "f2")):
        assert rows[key] == "needs_review", key
