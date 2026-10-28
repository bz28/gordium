"""Never a pass on facts that contradict each other, in every district, through the whole checker as the panel shows it.

#38 (found by the item-14 agent): in R-1b, two unrelated-people counts that disagreed (1 without the minor dependent
children, 0 with them) left the occupancy row saying "complies": only the count R-3 and RU read was set aside, and the
overall result stayed needs review only because a separate "Lot facts disagree" row existed. Now every fact in a
contradiction is set aside with the contradiction as its reason (measure.fact_conflicts, one list), so every row that
reads one of them needs review, saying why.

Expected results are the law's, not the code's: a contradiction means one of the answers is wrong and which one
can't be told, so no row that reads either answer may comply. Each case also states the same facts with the
contradiction resolved, where some of those rows do comply: the case is one that would pass if the contradiction
were ignored (not vacuous)."""

import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site
from model_measurement.measure import fact_conflicts
from model_measurement.stops import STOPS
from rule_format import formula
from rule_format.rulebook import REPO, load, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DISTRICTS = ["R-1a", "R-1b", "R-2a", "R-2b", "R-2c", "R-3a", "R-3aa", "R-3b", "RU"]
SMALL = [[5, 12], [25, 12], [25, 22], [5, 22]]       # a 20 x 10 ft house: fits every district's yards on the lot below
# The facts around each contradiction say everything else (owner lives there, no ADU, not a functional family unit,
# a 3-unit attached building), so a row reading the contradicting facts could only be held back by them.
HOUSEHOLD = {"owner_occupied": True, "accessory_dwelling_unit": False, "functional_family_unit": False,
             "home_occupation": False}
# each contradiction the measuring knows (a "_disagree" stop): (use, the contradicting facts, the same facts agreeing)
CASES = {
    "household_counts_disagree": ("one_family_detached",
                                  {**HOUSEHOLD, "unrelated_persons": 1, "unrelated_persons_with_children": 0},
                                  {**HOUSEHOLD, "unrelated_persons": 1, "unrelated_persons_with_children": 1}),
    "attached_counts_disagree": ("one_family_attached",
                                 {**HOUSEHOLD, "unrelated_persons": 0, "unrelated_persons_with_children": 0,
                                  "dwelling_units": 4, "attached_units_in_building": 3, "occupants": 1},
                                 {**HOUSEHOLD, "unrelated_persons": 0, "unrelated_persons_with_children": 0,
                                  "dwelling_units": 3, "attached_units_in_building": 3, "occupants": 1}),
    # R-2c notes 4-6 (#38 review round 1): 2 units of at most 1 occupant can't hold 10; the most in one unit can't be
    # more than all of them
    "occupant_counts_disagree": ("one_family_semi_detached",
                                 {**HOUSEHOLD, "dwelling_units": 2, "occupants": 10, "occupants_most_in_one_unit": 1},
                                 {**HOUSEHOLD, "dwelling_units": 2, "occupants": 10, "occupants_most_in_one_unit": 5}),
    "occupant_split_disagree": ("one_family_semi_detached",
                                {**HOUSEHOLD, "dwelling_units": 2, "occupants": 2, "occupants_most_in_one_unit": 3},
                                {**HOUSEHOLD, "dwelling_units": 2, "occupants": 2, "occupants_most_in_one_unit": 2}),
}


def _items(district, use, facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = district, use
    sc["lot"]["points"] = [[0, 0], [200, 0], [200, 300], [0, 300]]
    for b in sc["buildings"]:
        b["outline"] = SMALL
    s, f, extras = scenarios.site(sc)
    return check_site(s, {**f, **facts}, extras=extras)["view"]["items"]


def _reads(rule):
    return set().union(*(formula.names(t) for t in [rule.get("applies_when"), rule.get("check")] +
                         [w["when"] for w in rule.get("review_when") or []] if t))


def test_every_contradiction_the_measuring_knows_has_a_case():
    """A contradiction added later is tested here too: each "_disagree" stop is one of the cases."""
    assert sorted(CASES) == sorted(k for k in STOPS if k.endswith("_disagree"))


@pytest.mark.parametrize("key", sorted(CASES))
@pytest.mark.parametrize("district", DISTRICTS)
def test_no_row_reading_contradicting_facts_complies(district, key):
    use, facts, agreeing = CASES[key]
    conflicts = fact_conflicts({"use": use, **facts})
    assert len(conflicts) == 1 and fact_conflicts({"use": use, **agreeing}) == [], conflicts
    (why, names), = conflicts
    rules = {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}
    reading = {rid for rid, r in rules.items() if _reads(r) & set(names)}
    # (no rule reads them in some districts, e.g. R-1 has no attached houses: then only the conflict row is checked)
    items = {i["rule"]: i for i in _items(district, use, facts) if i.get("rule") in reading}
    for rid, i in items.items():
        assert i["status"] != present.COMPLIES, (rid, i["status"], i.get("reason"))
        if i["status"] == present.REVIEW:                          # says why, in the measuring's own words
            assert why in (i.get("reason") or ""), (rid, i.get("reason"))
    # the "Lot facts disagree" row is still there, offering to re-enter both answers
    rows = [i for i in _items(district, use, facts) if str(i["id"]).startswith("facts.conflict")]
    assert any(r["reason"] == why and r["needs"] == list(names) for r in rows), rows


@pytest.mark.parametrize("key", sorted(CASES))
def test_each_case_would_comply_somewhere_once_the_answers_agree(key):
    """Not vacuous: with the answers agreeing, some row that reads them complies in some district."""
    use, _, agreeing = CASES[key]
    names = set(fact_conflicts({"use": use, **CASES[key][1]})[0][1])
    complies = []
    for district in DISTRICTS:
        rules = {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}
        complies += [i["rule"] for i in _items(district, use, agreeing)
                     if i.get("rule") in rules and _reads(rules[i["rule"]]) & names and i["status"] == present.COMPLIES]
    assert complies, key

