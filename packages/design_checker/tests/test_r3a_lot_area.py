"""R-3a's lot size by units (chart p.3 note 7) through the whole checker, as the panel shows it (#20 review
round 2): a lot too small for any number of units does not comply even before the units are entered; a lot that
could be big enough waits for them, as a review row of its own (never 'not checked', never a pass)."""

import copy

import pytest

from design_checker import present, scenarios
from design_checker.check import check_site

SMALL = [[5, 10], [40, 10], [40, 25], [5, 25]]       # a 35 x 15 ft house: fits every yard on the small lots below


def _item(lot_w, lot_d, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["use"] = "multiple_family"
    sc["lot"]["points"] = [[0, 0], [lot_w, 0], [lot_w, lot_d], [0, lot_d]]
    for b in sc["buildings"]:
        b["outline"] = SMALL
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, **facts}, extras=extras)
    item = next(i for i in res["view"]["items"] if i["rule"] == "R-3a.lot_area_multiple_family")
    return res, item


def test_a_lot_too_small_for_any_multiple_dwelling_does_not_comply_with_nothing_entered():
    """50 x 60 = 3,000 sf: note 7's least is 6,000 sf (new construction, 1-3 units, no rooms let), so it fails
    whatever the units, the rooms let and new or conversion are: does not comply, and the panel says so."""
    res, item = _item(50, 60)
    assert item["status"] == present.FAILS, item
    assert res["view"]["state"] == present.FAILS
    assert "R-3a.lot_area_multiple_family" not in {r["Rule id"] for r in res["interior"]}


def test_three_units_no_rooms_let_and_new_or_conversion_unknown_fails_both_ways():
    """50 x 119.98 = 5,999 sf with 3 units and no rooms let: 6,000 sf new, 7,000 sf by conversion: fails both."""
    _, item = _item(50, 119.98, dwelling_units=3, rooms_let_for_profit=0)
    assert item["status"] == present.FAILS, item


@pytest.mark.parametrize("facts", [{}, {"rooms_let_for_profit": 0, "conversion": False}])
def test_a_lot_that_could_be_big_enough_waits_for_the_units_as_its_own_review_row(facts):
    """50 x 130 = 6,500 sf: enough for 3 new units, not for 4: with the units not entered it needs review, a row
    of its own named for the lot area and asking for what it needs (never 'Parking', never not checked)."""
    res, item = _item(50, 130, **facts)
    assert item["status"] == present.REVIEW, item
    assert "Parking" not in item["name"] and "dwelling units" in (item["reason"] or ""), item
    # until the Rhino panel can ask for them (#15), the row says where to enter them (#20 round 3)
    assert item["hint"].startswith("Enter the dwelling units") and "facts file for now" in item["hint"], item
    assert "R-3a.lot_area_multiple_family" not in {r["Rule id"] for r in res["interior"]}
