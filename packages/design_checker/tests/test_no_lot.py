"""A model with no lot, or a lot that can't be read, is a proper answer, never a crash (principle 4: never a false
pass). Found 2026-11-23: the Children's Odyssey (a Maine model, no Ithaca lot drawn) sent to check_site with its
problems coded as the site description codes them ({code, args}) raised "sequence item 0: expected str instance,
dict found" where the measuring joined the lot's problems into one reason (ithaca_city/measure.py), so Revit showed
an error and nothing checked.

Now every problem becomes words one way (model_measurement.stops.words_of): each rule that needs the lot says, in
plain words, why the lot can't be read and needs review; the rules that don't need the lot still run."""
import sys

import pytest

from design_checker.check import check_site, rulebook_for
from model_measurement.places.ithaca_city.measure import UNITS
from model_measurement.stops import stop
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS, REPO, load

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, RECT, box, lot  # noqa: E402

HOUSE = box(10, 25, 40, 75, 0, 30)
NOT_A_LOOP = {"id": "lot", "edges": [{"points": [[0, 0], [50, 0]], "curved": False},
                                     {"points": [[50, 0], [50, 100]], "curved": False},
                                     {"points": [[50, 100], [0, 100]], "curved": False}]}
BOW_TIE = lot([(0, 0), (50, 100), (50, 0), (0, 100)])

# (what is wrong with the lot, the lot, the site's problems, words the reason must hold)
CASES = {
    "no lot, nothing said": (None, [], stop("no_lot")),
    "no lot outline, coded (the Odyssey)": (None, [{"code": "no_lot_outline", "args": {"layer": "Property Lines"}}],
                                            stop("no_lot_outline", layer="Property Lines")),
    "no lot outline, in words": (None, [stop("no_lot_outline", layer="Property Lines")],
                                 stop("no_lot_outline", layer="Property Lines")),
    "two outlines, coded": (None, [{"code": "several_lot_outlines", "args": {"count": 2, "layer": "Site"}}],
                            stop("several_lot_outlines", count=2, layer="Site")),
    "a problem no reason has": (None, [{"code": "not_a_reason", "args": {}}], "can't be read"),
    "a problem that isn't one": (None, [42], "can't be read"),
    "lot lines not one loop": (NOT_A_LOOP, [], stop("lot_not_a_loop")),
    "lot crosses itself": (BOW_TIE, [], "the lot outline crosses itself"),
}


def _lot_measures() -> set[str]:
    """The measures the lot decides: those a site with a good lot gives and a site with no lot can't."""
    good = check_site({"units": "ft", "lot": RECT, "buildings": [HOUSE], "problems": []}, dict(FACTS))
    gone = check_site({"units": "ft", "lot": None, "buildings": [HOUSE], "problems": []}, dict(FACTS))
    found = {k for k in UNITS if good["measurements"][k]["value"] is not None
             and gone["measurements"][k]["value"] is None}
    assert {"lot_area", "lot_width", "building_area", "front_yard", "rear_yard"} <= found   # never vacuous
    return found


LOT_MEASURES = _lot_measures()


@pytest.mark.parametrize("zone", ["R-1b", "B-1a"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_no_lot_or_a_broken_one_is_an_answer_and_every_lot_rule_needs_review(case, zone):
    lot_, problems, words = CASES[case]
    facts = {**FACTS, "zone": zone}
    result = check_site({"units": "ft", "lot": lot_, "buildings": [HOUSE], "problems": problems}, facts)  # no crash
    measured = result["measurements"]
    for k in LOT_MEASURES:                      # each lot measure: no value, the lot's own words why
        assert measured[k]["value"] is None and words in measured[k]["reason"], (k, measured[k])
    assert all(isinstance(p, str) for p in result["problems"])       # said in words in the report too
    rules = {r["id"]: r for r in load(rulebook_for(REPO / facts["jurisdiction"], zone))["rules"]}
    lot_rows = [row for row in result["rows"]
                if set().union(*(formula.names(rules[row["Rule id"]][k]) for k in ("applies_when", "check")
                                 if rules[row["Rule id"]].get(k))) & LOT_MEASURES]
    assert lot_rows, "a district with no rule on the lot would make this test vacuous"
    # never a pass, never a fail on a lot that isn't there: a row naming the lot is decided only where its answer is
    # the same whatever the lot turns out to be (R-1b.height: a 30 ft house is under 35 ft, the bonus's yards
    # aside), worked out here with every lot measure unknown; every other one needs review
    values = {k: m["value"] for k, m in measured.items() if k not in LOT_MEASURES}
    review = [row for row in lot_rows if row["Error"] == "NEEDS REVIEW"]
    for row in lot_rows:
        if row["Error"] != "NEEDS REVIEW":
            rule = rules[row["Rule id"]]
            for k in ("applies_when", "check"):
                if rule.get(k):
                    formula.evaluate(rule[k], values, MEASURE_KINDS)     # MissingMeasure: decided on a lot not read
    assert {"lot_area", "lot_width", "building_area", "front_yard"} <= {
        n for row in review for n in formula.names(rules[row["Rule id"]]["check"])}, "the lot rules wait on the lot"
    assert all(words in row["Why"] for row in review
               if formula.names(rules[row["Rule id"]]["check"]) & {"lot_area", "lot_width", "front_yard"})
    assert result["view"]["state"] != "complies"
    # the rules that don't need the lot still run: the stories are decided from the building alone
    assert measured["stories"]["value"] == 2
    assert any(row["Error"] in ("PASS", "FAIL") for row in result["rows"] if row not in lot_rows)


def test_a_coded_building_problem_is_said_in_words():
    coded = {**HOUSE, "problems": [{"code": "tool_words", "args": {"words": "a block (Garage)"}}]}
    result = check_site({"units": "ft", "lot": RECT, "buildings": [coded], "problems": []}, dict(FACTS))
    assert result["measurements"]["building_height"]["value"] is None
    assert "a block (Garage)" in result["measurements"]["building_height"]["reason"]
