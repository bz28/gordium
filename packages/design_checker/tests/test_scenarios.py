"""The architect's answer key (test_data/test_sites/new_york/ithaca_city/scenarios/), checked in code. The same
scenarios are drawn and checked in Rhino by apps/rhino_plugin/tests/scenarios_in_rhino.py."""
import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site

PATHS = scenarios.paths()


def test_there_are_ten_scenarios_each_with_working_and_a_citation():
    assert len(PATHS) == 10
    for p in PATHS:
        sc = scenarios.load(p)
        for block in [sc["expected"], (sc.get("then") or {}).get("expected") or {}]:
            for rule, want in block.items():
                assert want["status"] in scenarios.CAUTION and want.get("working") and want.get("cites"), (p.name, rule)


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_gordium_gives_the_answer_key_or_a_disagreement_already_investigated(path):
    sc = scenarios.load(path)
    known = sc.get("disagreements") or {}
    for step in scenarios.run(sc):
        for r in step["rows"]:
            if r["match"]:
                assert r["rule"] not in known, f"{r['rule']} now matches: drop it from disagreements"
                continue
            assert r["rule"] in known, f"{path.stem} {step['step']}: {r['rule']} {r['why']}"
            assert known[r["rule"]]["gordium"] == r["gordium"], f"{r['rule']}: Gordium now says {r['gordium']}"
            assert known[r["rule"]].get("finding") and known[r["rule"]].get("question_for_architects")


@pytest.mark.parametrize("path", PATHS, ids=[p.stem for p in PATHS])
def test_never_a_false_pass(path):
    """Where the answer key says a rule does not comply, Gordium never says it complies: no exceptions."""
    sc = scenarios.load(path)
    for step in scenarios.run(sc):
        for r in step["rows"]:
            assert not (r["expected"] == present.FAILS and r["gordium"] == present.COMPLIES), (path.stem, r)


def _items(name):
    s, f, extras = scenarios.site(scenarios.load(scenarios.FOLDER / name))
    return {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}


def test_a_rule_with_two_ways_to_comply_says_how_each_falls_short_and_both_fixes():
    h = _items("04_height_bonus_some_yards_increased.yaml")["Building height"]
    assert h["status"] == present.FAILS
    assert h["reason"] == ("Does not comply either way the rule allows: Building height 37'-0\", needs ≤ 35'-0\"; "
                           "or Rear yard 30'-0\", needs ≥ 32'-0\"")
    assert h["hint"] == ("To comply: lower the building 2'-0\", or move the building 2'-0\" farther from the rear "
                         "lot line.")


def test_when_the_readings_disagree_the_row_shows_their_span_not_a_dash():
    v = _items("10_one_floor_moved_on_its_own.yaml")
    assert v["Side yard, narrower"]["proposed"] == "12'-0\" to 15'-0\""
    assert v["Lot coverage"]["proposed"] == "16.7% to 18.4%"          # 1,200 and 1,320 of 7,200 sf, rounded up


def _garage(touching: bool):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "06_detached_garage_not_on_the_building_layer.yaml"))
    if touching:                                   # a porch drawn on the wrong layer, against the front wall
        sc["others"] = [{"id": "porch", "outline": [[20, 22], [40, 22], [40, 30], [20, 30]], "base": 0, "top": 10}]
    s, f, extras = scenarios.site(sc)
    return {i["name"]: i for i in check_site(s, f, extras=extras)["view"]["items"]}


def test_a_solid_left_out_makes_coverage_need_review_and_one_touching_the_building_the_yards_too():
    detached = _garage(False)
    assert detached["Lot coverage"]["status"] == present.REVIEW
    assert "lot coverage counts every building" in detached["Lot coverage"]["reason"]
    assert detached["Front yard"]["status"] == present.COMPLIES          # a detached garage: the yards stand
    attached = _garage(True)
    for name in ("Front yard", "Rear yard", "Building height", "Stories"):
        assert attached[name]["status"] == present.REVIEW, name
        assert "touching the building" in attached[name]["reason"]
