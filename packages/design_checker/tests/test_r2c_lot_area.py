"""R-2c's lot size by occupants (chart p.3 note 4) through the whole checker, as the panel shows it: a lot too small
for even one occupant does not comply before the occupants are entered; a lot that could be big enough waits for
them, as a review row of its own asking for the occupants (never a pass); once entered, the row is decided."""

import copy

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
    complied. A semi-detached lot holds at least one unit, an attached building three: 400 sf fails, and a lot big
    enough for that least needs review until the count is right."""
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


def test_a_limit_that_depends_on_the_use_is_shown_for_the_stated_use():
    """Review round 1 (P2): R-2c's side yards and coverage depend on the use; the panel showed '—' as required."""
    items = _r2c("one_family_detached", 40, 100, "R-2c.side_yards", occupants=1)
    assert items and all(i["required"] not in ("", "—", None) for i in items), items
    cover = _r2c("one_family_detached", 40, 100, "R-2c.lot_coverage", occupants=1)
    assert cover and cover[0]["required"] not in ("", "—", None), cover
