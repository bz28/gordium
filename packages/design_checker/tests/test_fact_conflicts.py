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
from model_measurement.places.ithaca_city.measure import fact_conflicts
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
    # §325-26 (#44): no stream within 20 ft of the lot, yet a new structure 10 ft from one
    "stream_facts_disagree": ("one_family_detached", {**HOUSEHOLD, "stream_near_lot": False, "stream_distance": 10},
                              {**HOUSEHOLD, "stream_near_lot": True, "stream_distance": 25}),
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
    # (the use, when it is one of the answers, is set aside too but changed in the start box, not by this button)
    assert any(r["reason"] == why and r["needs"] == [n for n in names if n != "use"] for r in rows), rows


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



def test_occupant_counts_that_can_all_be_true_are_no_contradiction():
    """Review round 2: occupants are every unit's on the lot together (measures.yaml), so an accessory dwelling unit on
    the lot, or one not ruled out, is one more unit: a house of 2 and an ADU of 2 are 4, at most 2 in one. No unit
    stated is R-2c's own case ("no dwelling unit stated"). Neither is a contradiction; the plain impossible ones are."""
    house = {"use": "one_family_detached", "occupants": 4, "occupants_most_in_one_unit": 2}
    assert fact_conflicts({**house, "accessory_dwelling_unit": True}) == []
    assert fact_conflicts(house) == []                                       # an ADU not ruled out
    (why, names), = fact_conflicts({**house, "accessory_dwelling_unit": False})
    # review round 4: the 1 unit is the use's own (§325-3B), not a count entered: said so, and not offered to re-enter
    assert why == ("4 occupants on the lot, but 1 dwelling unit (what this use is, §325-3B) with at most 2 in any one "
                   "can hold only 2, with no accessory dwelling unit on the lot: check the use, the occupant counts and "
                   "the accessory dwelling unit answer")
    # review round 4 (P0): the use's own count is an answer too, so the use is set aside with them (R-1a.use complied)
    assert names == ("occupants", "occupants_most_in_one_unit", "accessory_dwelling_unit", "use")
    # two-family: two units by the use (§325-3B); 4 occupants with at most 2 in one fits exactly
    assert fact_conflicts({"use": "two_family", "occupants": 4, "occupants_most_in_one_unit": 2,
                           "accessory_dwelling_unit": False}) == []
    assert fact_conflicts({"use": "two_family", "occupants": 5, "occupants_most_in_one_unit": 2,
                           "accessory_dwelling_unit": False})
    semi = {"use": "one_family_semi_detached", "occupants": 3, "occupants_most_in_one_unit": 1,
            "accessory_dwelling_unit": False}
    assert fact_conflicts({**semi, "dwelling_units": 0}) == []
    assert fact_conflicts({**semi, "dwelling_units": 3}) == []                # 3 homes of 1: exactly 3
    assert fact_conflicts({**semi, "dwelling_units": 2})[0][1] == ("occupants", "occupants_most_in_one_unit",
                                                                   "accessory_dwelling_unit", "dwelling_units")


def test_the_no_adu_answer_behind_an_occupant_contradiction_never_lets_r1_occupancy_comply():
    """Review round 3 (P0): 4 occupants, at most 2 in one, no ADU, in a one-family house can't all be true; the "no
    ADU" answer may be the wrong one, and R-1's two-unrelated allowance reads it (§325-3B: owner-occupied, and with an
    ADU on the lot the open question): with it kept, the occupancy row complied."""
    facts = {**HOUSEHOLD, "unrelated_persons": 2, "unrelated_persons_with_children": 2, "occupants": 4,
             "occupants_most_in_one_unit": 2}
    for district in ("R-1a", "R-1b"):
        row = next(i for i in _items(district, "one_family_detached", facts)
                   if i.get("rule") == f"{district}.occupancy_one_family")
        assert row["status"] == present.REVIEW and "accessory dwelling unit answer" in row["reason"], row
        agreeing = {**facts, "occupants": 2}                         # 2 in one house, no ADU: complies
        row = next(i for i in _items(district, "one_family_detached", agreeing)
                   if i.get("rule") == f"{district}.occupancy_one_family")
        assert row["status"] == present.COMPLIES, row


@pytest.mark.parametrize("district, use, occupants", [("R-1a", "one_family_detached", 4), ("R-2a", "two_family", 5)])
def test_when_the_units_are_the_uses_own_the_use_is_set_aside_with_the_counts(district, use, occupants):
    """Review round 4 (P0): with no units entered, the count is the use's own (§325-3B: one-family 1, two-family 2), so the
    use is one of the answers that can't all be true (4 occupants of at most 2 fit a two-family house, not a one-family
    one): R-1a.use and the rows that apply by the use complied beside the "Lot facts disagree" row. Now no row reading
    the use complies, the use row says why, and with the counts agreeing (2 in one) the use row complies."""
    facts = {**HOUSEHOLD, "occupants": occupants, "occupants_most_in_one_unit": 2}
    rules = {r["id"]: r for r in load(rulebook_for(ITHACA, district))["rules"]}
    items = [i for i in _items(district, use, facts) if i.get("rule") in rules]
    reading = [i for i in items if "use" in _reads(rules[i["rule"]])]
    assert reading and all(i["status"] != present.COMPLIES for i in reading), [
        (i["rule"], i["status"]) for i in reading if i["status"] == present.COMPLIES]
    row = next(i for i in items if i["rule"] == f"{district}.use")
    assert "check the use, the occupant counts" in (row.get("reason") or ""), row
    fine = next(i for i in _items(district, use, {**facts, "occupants": 2}) if i.get("rule") == f"{district}.use")
    assert fine["status"] == present.COMPLIES, fine


@pytest.mark.parametrize("district", ["R-2c", "R-3a", "RU"])
def test_the_attached_counts_clash_sets_the_use_aside_too(district):
    """Review round 4 (P1): 4 units on this lot but 3 in the attached building clash only for an attached house, so the
    use is one of the answers: the use row needs review saying so (it complied); with the counts agreeing, no row carries
    the clash."""
    use, facts, agreeing = CASES["attached_counts_disagree"]
    row = next(i for i in _items(district, use, facts) if i.get("rule") == f"{district}.use")
    assert row["status"] == present.REVIEW and "or the use is off" in (row.get("reason") or ""), row
    assert not any("or the use is off" in (i.get("reason") or "") for i in _items(district, use, agreeing))


@pytest.mark.parametrize("district", ["R-2c", "R-3a", "RU"])
def test_the_use_row_set_aside_points_to_edit_site_in_the_start_box(district):
    """When contradictory answers set the use itself aside, the use row is still needs review (unchanged) and now says
    where to fix it: the start box's "Edit site…" button, since the use has no "Enter …" button. A contradiction
    that leaves the use alone (the unrelated-people counts) adds no such pointer."""
    use, facts, agreeing = CASES["attached_counts_disagree"]
    row = next(i for i in _items(district, use, facts) if i.get("rule") == f"{district}.use")
    assert row["status"] == present.REVIEW, row
    assert "Edit site…" in (row.get("reason") or "") and "start box" in row["reason"], row
    assert (row["reason"] or "").count("Edit site…") == 1, row
    other_use, other, _ = CASES["household_counts_disagree"]
    assert not any("Edit site…" in (i.get("reason") or "") for i in _items(district, other_use, other)
                   if i.get("rule") == f"{district}.use")
