"""Ben's one-floor-moved cases on the sample lot, and a building that crosses a lot line (review round 4).

The starting house on 106 Ithaca Rd's 73 x 90 lot (from the tax map) sits 12 ft from each side line and 27 ft from
the street, 3 floor blocks. Moving any one floor block 5 ft east puts it 12 − 5 = 7 ft from the east line (10 ft
required): the side yard does not comply, whichever floor it is. Moving only the top floor 4 ft toward the street
puts it 27 − 4 = 23 ft back (25 required): the front yard does not comply."""

import sys

import pytest

from design_checker import present
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
from test_every_reading import floors, prism, rect, rows, run, status  # noqa: E402
from test_quickstart import _check, _moved, house  # noqa: E402,F401  (house: the module fixture)


@pytest.mark.parametrize("which", [0, 1, 2])
def test_one_floor_moved_5_ft_east_does_not_comply_on_the_east_side(house, which):
    got, facts = house
    items = _check(_moved(got["floors"], dx=5, which=which), facts)
    east = items["Side yard, East"]
    assert (east["status"], east["proposed"]) == (present.FAILS, "7'-0\"")


def test_only_the_top_floor_moved_4_ft_toward_the_street_does_not_comply_in_front(house):
    got, facts = house
    front = _check(_moved(got["floors"], dy=-4, which=2), facts)["Front yard"]
    assert (front["status"], front["proposed"]) == (present.FAILS, "23'-0\"")


def test_the_eaves_rule_names_the_yard_it_fails_in(house):
    """Review round 4 (found running the floor cases): the house moved 5 ft east fails the eaves rule on the east
    side (7 < 10 − 2), so its row says the side yard and 7'-0", never 'Eaves into front yard 27'-0"'."""
    got, facts = house
    items = _check(_moved(got["floors"], dx=5), facts, grade_is="finished")   # the height known (the bonus term)
    eaves =[i for n, i in items.items() if n.startswith("Eaves into")]
    assert len(eaves) == 1 and eaves[0]["status"] == present.FAILS
    assert (eaves[0]["name"], eaves[0]["proposed"]) == ("Eaves into side yard", "7'-0\"")


def test_a_building_crossing_the_side_lot_line_does_not_comply_and_says_so():
    """The house 50..65 on a 60 ft wide lot: it crosses the east lot line. The side yard there is 0: does not
    comply, 'crosses the lot line', never needs review or a pass."""
    res = run(floors(50, 30, 65, 70, 2))
    side = rows(res, "R-1b.side_yards")
    assert status(res, "R-1b.side_yards") == present.FAILS
    assert any(i["status"] == present.FAILS and "crosses the lot line" in (i["reason"] or "") for i in side)
    assert not any(i["status"] == present.COMPLIES for r in ("R-1b.side_yards", "R-1b.yard_projections")
                   for i in rows(res, r) if "crosses" in (i["reason"] or ""))


def test_a_building_crossing_the_street_line_does_not_comply_in_front():
    res = run(floors(15, -5, 45, 30, 2))
    front = rows(res, "R-1b.front_yard")[0]
    assert front["status"] == present.FAILS and "crosses the lot line" in front["reason"]


def test_a_building_wholly_off_the_lot_still_waits():
    """Wholly outside (no part on the lot): it can't be measured against the lot: needs review, as before."""
    res = run([prism(rect(70, 30, 90, 70), 0, 20, "house")])
    assert status(res, "R-1b.front_yard") == present.REVIEW


# ---- verification round (4d0a2e6): each building is placed on the lot on its own ------------------------------

def test_a_house_wholly_off_the_lot_never_complies_because_a_shed_is_on_it():
    """Case A (a false pass on 4d0a2e6: every row complied). The house past the rear line (y 150..190 on a 120 ft
    deep lot), a listed frame shed on the lot: the house can't be measured against the lot, so no yard complies."""
    res = run(floors(15, 150, 45, 190, 2) + [prism(rect(20, 90, 30, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True, stories=2)
    for rule in ("R-1b.front_yard", "R-1b.side_yards", "R-1b.rear_yard"):
        assert status(res, rule) != present.COMPLIES, rule


def test_a_shed_wholly_off_the_lot_never_complies_because_the_house_is_on_it():
    """Case B: the house on the lot, a listed shed off it (x 70..80 on a 60 ft wide lot): the accessory rule
    never complies."""
    res = run(floors(15, 30, 45, 70, 2) + [prism(rect(70, 90, 80, 100), 0, 10, "shed")],
              accessory_buildings=["shed"], accessory_frame=True)
    assert status(res, "R-1b.accessory_buildings") != present.COMPLIES


def test_only_the_line_actually_crossed_says_crosses():
    """A building 50..65 x 0..70: its front face lies exactly on the street line (inside the lot), and it crosses
    the east line. The east side row says it crosses the lot line; the front row (0 ft, does not comply) doesn't."""
    res = run(floors(50, 0, 65, 70, 2))
    front = rows(res, "R-1b.front_yard")[0]
    assert front["status"] == present.FAILS and "crosses the lot line" not in (front["reason"] or "")
    assert any("crosses the lot line" in (i["reason"] or "") for i in rows(res, "R-1b.side_yards"))
