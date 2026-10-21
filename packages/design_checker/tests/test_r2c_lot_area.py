"""R-2c's lot size by occupants (chart p.3 note 4) through the whole checker, as the panel shows it: a lot too small
for even one occupant does not comply before the occupants are entered; a lot that could be big enough waits for
them, as a review row of its own asking for the occupants (never a pass); once entered, the row is decided."""

import copy
from pathlib import Path

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site

SMALL = [[5, 12], [25, 12], [25, 22], [5, 22]]       # a 20 x 10 ft house: fits every R-2c yard on the lots below


def _item(lot_w, lot_d, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = "R-2c", "one_family_detached"
    sc["lot"]["points"] = [[0, 0], [lot_w, 0], [lot_w, lot_d], [0, lot_d]]
    for b in sc["buildings"]:
        b["outline"] = SMALL
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, **facts}, extras=extras)
    return next(i for i in res["view"]["items"] if i["rule"] == "R-2c.lot_area_one_family_detached")


def test_a_lot_too_small_for_one_occupant_does_not_comply_with_nothing_entered():
    """40 x 60 = 2,400 sf: note 4's least is 2,500 sf (one occupant), so it fails whatever the occupants."""
    assert _item(40, 60)["status"] == present.FAILS


def test_a_lot_that_could_be_big_enough_waits_for_the_occupants():
    """40 x 100 = 4,000 sf: enough for up to 4 occupants (2,500 + 3 x 500), not 5: it asks for the occupants."""
    item = _item(40, 100)
    assert item["status"] == present.REVIEW, item
    assert item["needs"] == ["occupants"], item


@pytest.mark.parametrize("occupants, status", [(4, present.COMPLIES), (5, present.FAILS)])
def test_the_occupants_once_entered_decide_it(occupants, status):
    assert _item(40, 100, occupants=occupants)["status"] == status


def _r2c(use, lot_w, lot_d, rule, outline=SMALL, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = "R-2c", use
    sc["lot"]["points"] = [[0, 0], [lot_w, 0], [lot_w, lot_d], [0, lot_d]]
    for b in sc["buildings"]:
        b["outline"] = outline
    s, f, extras = scenarios.site(sc)
    items = check_site(s, {**f, **facts}, extras=extras)["view"]["items"]
    return [i for i in items if i["rule"] == rule]


@pytest.mark.parametrize("use, rule", [("one_family_semi_detached", "R-2c.lot_area_one_family_semi_detached"),
                                       ("one_family_attached", "R-2c.lot_area_one_family_attached")])
def test_a_lot_with_no_dwelling_units_stated_never_complies(use, rule):
    """Review round 1 (P0): 2,000 (1,500) sf x units made 0 sf required with 0 units entered, so a 20 x 20 ft lot
    complied. A semi-detached or attached lot holds at least one unit: 400 sf fails, and a lot big enough for one
    unit's least needs review until the count is right."""
    small = _r2c(use, 20, 20, rule, outline=[[5, 5], [15, 5], [15, 12], [5, 12]], dwelling_units=0, occupants=0)
    assert [i["status"] for i in small] == [present.FAILS], small
    big = _r2c(use, 60, 100, rule, dwelling_units=0, occupants=0)
    assert [i["status"] for i in big] == [present.REVIEW], big


def test_occupants_all_in_one_unit_are_never_assumed_away():
    """Review round 1 (P1): a two-family house with 4 occupants needs 4,800 sf spread 2 and 2 but 5,200 sf if all
    four are in one unit; the split isn't stated, so 48 x 100 = 4,800 sf needs review, never complies."""
    item = _r2c("two_family", 48, 100, "R-2c.lot_area_two_family", occupants=4)
    assert [i["status"] for i in item] == [present.REVIEW], item
    assert [i["status"] for i in _r2c("two_family", 52, 100, "R-2c.lot_area_two_family", occupants=4)] == [
        present.COMPLIES]


def test_the_most_occupants_in_one_unit_settles_a_two_family_lot_and_is_asked_only_when_it_could():
    """Coordinator follow-up: an ordinary two-family house (one occupant in each unit) on 40 x 100 = 4,000 sf needed
    review with the split unknown. The most occupants in one unit, optional, settles it both ways; it is asked only
    by a row that needs review, never by one already decided."""
    rule = "R-2c.lot_area_two_family"
    unknown = _r2c("two_family", 40, 100, rule, occupants=2)
    assert [(i["status"], i["needs"]) for i in unknown] == [(present.REVIEW, ["occupants_most_in_one_unit"])], unknown
    assert [i["status"] for i in _r2c("two_family", 40, 100, rule, occupants=2, occupants_most_in_one_unit=1)] == [
        present.COMPLIES]
    assert [i["status"] for i in _r2c("two_family", 40, 100, rule, occupants=2, occupants_most_in_one_unit=2)] == [
        present.FAILS]                                                     # both in one unit: 4,400 sf
    decided = _r2c("two_family", 30, 100, rule, occupants=2)               # 3,000 sf: short however they are split
    assert [(i["status"], i["needs"]) for i in decided] == [(present.FAILS, [])], decided


def test_the_most_occupants_in_one_unit_is_one_or_more():
    from design_checker.rhino_logic import update_counts
    from model_measurement.project import fact_problems
    assert update_counts({}, {"occupants_most_in_one_unit": 1}) == {"occupants_most_in_one_unit": 1}
    with pytest.raises(ValueError):
        update_counts({}, {"occupants_most_in_one_unit": 0})
    assert any("1 or more" in p for p in fact_problems({"occupants_most_in_one_unit": 0}))


def test_a_limit_that_depends_on_the_use_is_shown_for_the_stated_use():
    """Review round 1 (P2): R-2c's side yards and coverage depend on the use; the panel showed '—' as required."""
    items = _r2c("one_family_detached", 40, 100, "R-2c.side_yards", occupants=1)
    assert items and all(i["required"] not in ("", "—", None) for i in items), items
    cover = _r2c("one_family_detached", 40, 100, "R-2c.lot_coverage", occupants=1)
    assert cover and cover[0]["required"] not in ("", "—", None), cover


def test_a_row_house_on_its_own_lot_is_checked_under_both_lot_readings():
    """Review rounds 2 and 3: a row house on its own 20 x 100 = 2,000 sf lot (one unit, one occupant) is enough for
    its own unit (1,500 sf) but not for a building of three (4,500 sf); whose lot the chart means is an open question
    (both readings recorded), so the row needs review, never a definite pass or fail. 1,400 sf is short either way.
    The building's 3 to 6 units are their own row, on their own stated fact."""
    from rule_format.rulebook import REPO, load
    rules = load(REPO / "regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-2c.yaml")["rules"]
    attached = next(r for r in rules if r["id"] == "R-2c.lot_area_one_family_attached")
    assert {g["id"] for x in attached["research"] for g in x["readings"]} >= {"per_row_house_lot", "building_lot"}
    lot = _r2c("one_family_attached", 20, 100, "R-2c.lot_area_one_family_attached",
               outline=[[2, 30], [18, 30], [18, 50], [2, 50]], dwelling_units=1, occupants=1)
    assert [i["status"] for i in lot] == [present.REVIEW], lot
    short = _r2c("one_family_attached", 20, 70, "R-2c.lot_area_one_family_attached",
                 outline=[[2, 30], [18, 30], [18, 50], [2, 50]], dwelling_units=1, occupants=1)
    assert [i["status"] for i in short] == [present.FAILS], short
    rule = "R-2c.attached_units_per_building"
    unknown = _r2c("one_family_attached", 20, 100, rule, outline=[[2, 30], [18, 30], [18, 50], [2, 50]])
    assert [(i["status"], i["needs"]) for i in unknown] == [(present.REVIEW, ["attached_units_in_building"])], unknown
    for units, status in ((4, present.COMPLIES), (2, present.FAILS), (7, present.FAILS)):
        got = _r2c("one_family_attached", 20, 100, rule, outline=[[2, 30], [18, 30], [18, 50], [2, 50]],
                   attached_units_in_building=units)
        assert [i["status"] for i in got] == [status], (units, got)


def test_an_optional_fact_that_cant_settle_the_row_is_neither_asked_nor_given_as_the_reason():
    """Review round 2 (P2): three units on a semi-detached lot needs review whatever the split, so the row says why
    (at most two units) and asks for nothing; the unset optional fact used to replace that reason and be asked."""
    item = _r2c("one_family_semi_detached", 30, 100, "R-2c.lot_area_one_family_semi_detached", occupants=2,
                dwelling_units=3)
    assert [(i["status"], i["needs"]) for i in item] == [(present.REVIEW, [])], item
    assert "at most two dwelling units" in (item[0]["reason"] or ""), item


def test_every_counted_facts_prompt_accepts_exactly_what_its_checks_accept():
    """Review round 2 (P2): the Enter prompt accepted 0 for the most occupants in one unit, which update_counts
    refused with an exception out of the button. One minimum per fact, used by the prompt, update_counts and the
    facts check; a refused answer is a message in the panel, never an exception."""
    from design_checker import rhino_logic as logic
    from model_measurement.project import FACT_FIELDS, fact_problems
    counts = [k for k, (_, kind, _) in logic.STATED_FACTS.items() if kind == "count"]
    for k in counts:
        least = logic.minimum(k)
        assert logic.update_counts({}, {k: least}) == {k: least}
        with pytest.raises(ValueError):
            logic.update_counts({}, {k: least - 1})
        assert k in FACT_FIELDS and fact_problems({k: least}) == [] and fact_problems({k: least - 1}), k
    plugin = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "_count(prompt, logic.minimum(key))" in plugin and "gi.SetLowerLimit(least, False)" in plugin
    enter = plugin[plugin.index("def enter_rooms("):plugin.index("\ndef ", plugin.index("def enter_rooms(") + 1)]
    assert "except ValueError" in enter and enter.index("except ValueError") < enter.index("save_facts(")


def test_round_4s_case_one_unit_of_a_six_unit_building_never_complies():
    """Review round 4 (P0): one unit of a stated six-unit building on 4,500 sf complied (the building's-lot reading
    used a floor of three units, not the building's six; and the other lots' occupants aren't stated)."""
    got = _r2c("one_family_attached", 45, 100, "R-2c.lot_area_one_family_attached", dwelling_units=1, occupants=1,
               attached_units_in_building=6)
    assert [i["status"] for i in got] == [present.REVIEW], got


def test_more_units_on_the_lot_than_in_the_building_is_never_a_pass_and_the_panel_says_the_counts_disagree():
    """Review round 5 (P1): 4 units on a lot next to a stated 3-unit building passed (>= instead of ==)."""
    items = _r2c("one_family_attached", 60, 100, "R-2c.lot_area_one_family_attached", dwelling_units=4, occupants=1,
                 attached_units_in_building=3)
    assert [i["status"] for i in items] == [present.REVIEW], items
    assert "More units on this lot than in the attached building" in (items[0]["reason"] or ""), items
    note = _r2c("one_family_attached", 60, 100, None, dwelling_units=4, occupants=1, attached_units_in_building=3)
    assert [i["reason"] for i in note if str(i["id"]).startswith("facts.conflict")] == [
        "4 dwelling units on this lot but 3 in the attached building: part of another building may be on this lot, "
        "or one of the counts is off"]
