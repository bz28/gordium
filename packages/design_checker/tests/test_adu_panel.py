"""A detached accessory dwelling unit from model to panel (§325-28C): the rules read the ADU's building measured on its
own, a row waiting for it says how to pick it, and its facts are asked only once an ADU is said to be on the lot.

Every expected value is worked by hand from the made-up R-1b lot: 50 x 100 ft, the street along y = 0, the side lot
lines x = 0 and x = 50, the rear lot line y = 100; the house 10..35 x 25..55, 30 ft tall (front yard 25 ft)."""

import sys

from design_checker import present
from design_checker import rhino_logic as logic
from design_checker.check import check_site
from rule_format.rulebook import REPO

sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_measure import FACTS, RECT, box  # noqa: E402

CITY = "regulations/jurisdictions/new_york/ithaca_city"
HOUSE = box(10, 25, 35, 55, id="house")
ADU_FACTS = {**FACTS, "jurisdiction": CITY, "main_building": "house", "accessory_dwelling_unit": True,
             "adu_detached": True, "adu_existing_building": False, "adus_on_parcel": 1, "adu_bedrooms": 2}
SIZE, SETBACKS, FRONT = ("Detached ADU: 800 sf footprint; two stories and 20 ft", "Detached ADU: 5 ft from the side "
                         "and rear lot lines", "Detached ADU: not in the primary front yard nor a required one")


def _rows(*buildings, **facts):
    view = check_site({"units": "ft", "lot": RECT, "buildings": list(buildings), "problems": []},
                      {**ADU_FACTS, **facts})["view"]
    return {i["name"]: i for i in view["items"]}


def test_not_picked_yet_the_rows_wait_and_point_to_the_pick():
    rows = _rows(HOUSE, box(30, 70, 45, 90, 0, 18, id="cottage"))
    for name in (SIZE, SETBACKS, FRONT):
        assert rows[name]["status"] == present.REVIEW and rows[name]["hint"] == present.PICK_ADU, rows[name]
    assert present.PICK_ADU_WHY in rows[SIZE]["reason"]


def test_picked_the_cottage_is_judged_on_its_own():
    """30..45 x 70..90, 18 ft: 300 sf, at most 2 stories (floor(18 / 7)); 70 ft back from the street (the house's
    front is at 25); side min(30, 5) = 5 ft, rear 100 - 90 = 10 ft. R-1b: 5 ft complies with §325-28 but not with
    §325-25C's 6 ft, the open question (R-1b.adu_detached_setbacks#1): needs review, never a pass."""
    rows = _rows(HOUSE, box(30, 70, 45, 90, 0, 18, id="cottage"), adu_building="cottage")
    assert rows[SIZE]["status"] == present.COMPLIES
    assert rows[FRONT]["status"] == present.COMPLIES
    assert rows[SETBACKS]["status"] == present.REVIEW
    six = _rows(HOUSE, box(29, 70, 44, 90, 0, 18, id="cottage"), adu_building="cottage")      # 6 ft from x = 50
    assert six[SETBACKS]["status"] == present.COMPLIES


def test_a_cottage_beside_the_house_nearer_the_street_fails():
    """38..48 x 20..40: 20 ft from the street, 5 ft nearer than the house's front (25): in the primary front yard,
    and inside R-1b's 25 ft required front yard too."""
    rows = _rows(HOUSE, box(38, 20, 48, 40, 0, 18, id="cottage"), adu_building="cottage")
    assert rows[FRONT]["status"] == present.FAILS


def test_too_big_fails_and_an_existing_building_too_big_needs_review():
    """12..48 x 72..94.5 = 36 x 22.5 = 810 sf, over 800 (clear of the house, which ends at y = 55)."""
    big = box(12, 72, 48, 94.5, 0, 18, id="cottage")
    assert _rows(HOUSE, big, adu_building="cottage")[SIZE]["status"] == present.FAILS
    assert _rows(HOUSE, big, adu_building="cottage", adu_existing_building=True)[SIZE]["status"] == present.REVIEW


def test_a_stale_adu_pick_is_dropped_like_the_main_buildings():
    kept = logic.drop_stale({"adu_building": "cottage", "main_building": "house"}, set(), {"house", "cottage"})
    assert kept["adu_building"] == "cottage"
    gone = logic.drop_stale({"adu_building": "cottage", "main_building": "house"}, set(), {"house"})
    assert "adu_building" not in gone and gone["main_building"] == "house"


def test_the_adus_facts_are_asked_only_once_an_adu_is_said_to_be_on_the_lot():
    names = {"accessory_dwelling_unit", "adu_bedrooms", "adus_on_parcel", "adu_detached", "adu_existing_building",
             "adu_floor_area", "primary_floor_area"}
    assert logic.needs_of(names, {}) == ["accessory_dwelling_unit"]
    after = logic.needs_of(names, {"accessory_dwelling_unit": True})
    assert {"adu_detached", "adus_on_parcel", "adu_bedrooms"} <= set(after) and "adu_existing_building" not in after
    assert {"adu_existing_building", "adu_floor_area", "primary_floor_area"} <= set(
        logic.needs_of(names, {"accessory_dwelling_unit": True, "adu_detached": True}))
    assert not set(logic.BOX_ASKS) & (names - {"accessory_dwelling_unit"})       # never asked up front
