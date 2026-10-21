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
