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
    # moving the whole house forward would take the 2 ft from the front yard, which the bonus needs too
    assert h["hint"] == "To comply: lower the building 2'-0\", or make the rear yard 2'-0\" deeper, keeping the other yards."


def test_when_the_readings_disagree_the_row_keeps_its_side_and_shows_the_span_in_the_limits_unit():
    v = _items("10_one_floor_moved_on_its_own.yaml")
    assert v["Side yard, East"]["proposed"] == "12'-0\" to 15'-0\""   # still named: the shortest reading's line
    assert v["Side yard, East"]["points"]
    assert v["Lot coverage"]["proposed"] == "16.7% to 18.4%"          # 1,200 and 1,320 of 7,200 sf, rounded up
    assert v["Lot coverage"]["required"] == "25%"                    # the limit in the same unit, never sf


def test_a_design_using_the_height_bonus_shows_the_bonus_limit_and_the_raised_yards():
    v = _items("03_height_bonus_every_yard_increased.yaml")
    h = v["Building height"]
    assert (h["status"], h["required"], h["margin"], h["hint"]) == (present.COMPLIES, "38'-6\"", "+1'-6\"", None)
    assert "Front yard ≥ 27'-0\"; Side yards ≥ 12'-0\"; Rear yard ≥ 32'-0\"" in h["reason"]
    for name, req in (("Front yard", "27'-0\""), ("Side yard, West", "12'-0\""), ("Rear yard", "32'-0\"")):
        assert (v[name]["required"], v[name]["margin"]) == (req, "at limit"), name   # not "+2'-0"": the bonus needs it


def test_a_fix_is_never_rounded_short():
    c = _items("05_coverage_one_square_foot_over.yaml")["Lot coverage"]
    assert c["hint"] == "To comply: reduce the footprint by at least 1 sf."     # 1 sf over, never "0.01%"
    assert present._gap(-0.01, "ft") == "0'-0 1/8\""                            # up, never down to nothing
    assert present._gap(-2.0001, "ft") == "2'-0 1/8\""


def test_the_tax_map_worst_case_applies_to_the_lot_area_too():
    v = _items("08_tax_map_lot_front_yard_within_two_feet.yaml")
    assert v["Lot area"]["status"] == present.COMPLIES
    assert "worst case (lot area 6,844 sf)" in v["Lot area"]["reason"]          # 58 × 118
    assert v["Front yard"]["status"] == present.REVIEW                         # 26 ft: at worst 24 ft


def test_chart_quotes_are_the_districts_own_cell_never_a_whole_row():
    quotes = [q["text"] for q in _items("05_coverage_one_square_foot_over.yaml")["Lot area"]["detail"]["quotes"]]
    assert "Minimum Lot Size · One-family dwelling, detached · R-1B: “6,000 sf”" in quotes
    assert not any("10,000 sf 6,000 sf 5,000 sf" in q or q.startswith("R-1A R-1B") for q in quotes)


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
