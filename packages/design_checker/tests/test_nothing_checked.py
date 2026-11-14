"""A check that checked nothing never says the design complies (principle 4: never a false pass). Both overall
answers of a check, the panel's state (present.state, the worker's `view.state`) and the corner summary
(check.summary), say "needs review" when no row was decided: no counted item at all, or every one "not checked"
(a rule waiting on a fact about the inside, a rule not in this release). Not "not applicable": a rule that doesn't
apply is left out of the rows, and the rest of the design is still checked.

Every real rulebook today has rules that apply to every design (the yards, height, lot coverage), so a real check
always decides some row; these pin the answer for a rulebook or a design where that isn't so, with the real
items a real check gives for the rules that wait."""
import sys

from design_checker import present
from design_checker.check import check_site, rulebook_for, summary
from rule_format.rulebook import REPO, load

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, box, lot  # noqa: E402

SITE = {"units": "ft", "lot": lot([(0, 0), (50, 0), (50, 100), (0, 100)]),
        "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}


def _real_check():
    facts = dict(FACTS)                    # no bedrooms or parking spaces given: the parking rule waits on them
    result = check_site(SITE, facts)
    by_id = {r["id"]: r for r in load(rulebook_for(REPO / facts["jurisdiction"], facts["zone"]))["rules"]}
    return result, by_id, facts


def test_a_real_check_has_a_rule_waiting_on_the_inside_and_complies_otherwise():
    result, _, _ = _real_check()           # the setting the next tests take their real rows from
    assert result["interior"], "R-1b's parking rule waits on the bedrooms and parking spaces"
    assert any(i["status"] == present.NOT_CHECKED for i in result["view"]["items"])


def test_every_counted_item_not_checked_is_never_complies():
    result, by_id, facts = _real_check()
    v = present.view([], result["interior"], by_id, result["measurements"], facts)   # only the rows that wait
    counted = present._building_items(v["items"])
    assert counted and all(i["status"] == present.NOT_CHECKED for i in counted)
    assert v["state"] == present.REVIEW


def test_no_counted_item_is_never_complies():
    assert present.state([]) == present.REVIEW
    not_covered = [{"group": "not_covered", "status": present.NOT_CHECKED}]   # not in Gordium yet: never counted
    assert present.state(not_covered) == present.REVIEW


def test_one_complying_item_beside_a_not_checked_one_needs_review():
    # Ben, 2026-11-09: a row still waiting (a fact to answer, a rule not in this release) holds the whole design at
    # needs review, whatever else complies (test_headline_waits_on_facts.py has the real checks)
    items = [{"group": "building", "status": present.COMPLIES},
             {"group": "not_checked", "status": present.NOT_CHECKED}]
    assert present.state(items) == present.REVIEW
    assert present.state(items[:1]) == present.COMPLIES


def test_the_summary_of_no_rows_is_never_a_pass():
    s = summary([])
    assert s["state"] == "review" and s["state"] not in ("pass", "complies")
    assert summary([{"Error": "PASS", "Requirement": "Front yard"}])["state"] == "pass"
