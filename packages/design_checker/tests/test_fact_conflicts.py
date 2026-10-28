"""Never a pass on facts that contradict each other, in every district, through the whole checker as the panel shows it.

4 dwelling units on this lot but 3 in the whole attached building can't both be true for an attached house (the
building holds every unit on the lot). R-2c's three-to-six units row complied on the 3 beside the "Lot facts disagree"
row (#38's item-14 finding, the same pattern found here). Now every answer in a contradiction, the use too, is set
aside with the contradiction as its reason (measure.fact_conflicts, one list), so every row that reads one needs
review, saying why.

Expected results are the law's, not the code's: one of the answers is wrong and which can't be told, so no row reading
any of them may comply. Each case also states the same facts agreeing, where some of those rows do comply (not
vacuous)."""

import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site
from model_measurement.measure import fact_conflicts
from model_measurement.stops import STOPS
from rule_format import formula
from rule_format.rulebook import REPO, load, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
DISTRICTS = sorted(p.stem for p in (ITHACA / "5_zoning_rules").glob("*.yaml"))
SMALL = [[5, 12], [25, 12], [25, 22], [5, 22]]       # a 20 x 10 ft house: fits every district's yards on the lot below
# each contradiction the measuring knows (a "_disagree" stop): (use, the contradicting facts, the same facts agreeing)
CASES = {
    "attached_counts_disagree": ("one_family_attached",
                                 {"dwelling_units": 4, "attached_units_in_building": 3, "occupants": 1},
                                 {"dwelling_units": 3, "attached_units_in_building": 3, "occupants": 1}),
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
    assert "use" in names                    # the use is one of the answers (an attached house's counts clash)
    rules = {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}
    reading = {rid for rid, r in rules.items() if _reads(r) & set(names)}
    items = {i["rule"]: i for i in _items(district, use, facts) if i.get("rule") in reading}
    for rid, i in items.items():
        assert i["status"] != present.COMPLIES, (rid, i["status"], i.get("reason"))
        if i["status"] == present.REVIEW:                          # says why, in the measuring's own words
            assert why in (i.get("reason") or ""), (rid, i.get("reason"))
    # the "Lot facts disagree" row is still there, offering to re-enter the counts
    rows = [i for i in _items(district, use, facts) if str(i["id"]).startswith("facts.conflict")]
    assert any(r["reason"] == why and r["needs"] == ["dwelling_units", "attached_units_in_building"] for r in rows), rows


def test_r2cs_three_to_six_units_row_needs_review_on_the_clash_and_complies_once_the_counts_agree():
    """The false pass itself: R-2c.attached_units_per_building (3 to 6 units, §325-3B) complied on the stated 3."""
    use, facts, agreeing = CASES["attached_counts_disagree"]
    rid = "R-2c.attached_units_per_building"
    row = next(i for i in _items("R-2c", use, facts) if i.get("rule") == rid)
    assert row["status"] == present.REVIEW and "or one of the counts or the use is off" in row["reason"], row
    assert next(i for i in _items("R-2c", use, agreeing) if i.get("rule") == rid)["status"] == present.COMPLIES


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
