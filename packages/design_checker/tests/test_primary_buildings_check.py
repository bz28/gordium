"""§325-8B(1) through the whole checker, as the panel shows it: a house and a building standing apart that could hold
a home (a big garage or a second house). Gordium can't tell which, so the lot-area row for each primary building
waits for the architect's count (never a pass); stated, it is decided. Expected figures by hand: R-1b, 6,000 sf for
each one-family house; the lot is 60 x 150 = 9,000 sf."""

import copy

from design_checker import present, scenarios
from design_checker.check import check_site

RULE = "R-1b.lot_area_each_primary_building"


def _rows(lot=(60, 150), **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = "R-1b", "one_family_detached"
    w, d = lot
    sc["lot"]["points"] = [[0, 0], [w, 0], [w, d], [0, d]]
    sc["buildings"] = [{"id": "house", "outline": [[15, 25], [45, 25], [45, 60], [15, 60]], "base": 0, "floors": [10, 10]},
                       {"id": "back", "outline": [[15, 100], [45, 100], [45, 125], [15, 125]], "base": 0, "floors": [10]}]
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, "main_building": "house_floor1", **facts}, extras=extras)
    return {i["rule"]: i for i in res["view"]["items"]}


def test_a_second_building_that_could_be_a_house_waits_for_the_count():
    """9,000 sf holds one house (6,000) but not two (12,000): the count decides, so the row asks for it."""
    item = _rows()[RULE]
    assert item["status"] == present.REVIEW, item
    assert "primary_buildings" in item["needs"], item


def test_once_counted_the_row_is_decided():
    assert _rows(primary_buildings=2, primary_buildings_same_use=True)[RULE]["status"] == present.FAILS
    assert RULE not in _rows(primary_buildings=1)               # one primary building: not applicable, not shown
    # the one-house lot-area row is unchanged: 9,000 sf of 6,000
    assert _rows(primary_buildings=1)["R-1b.lot_area_one_family_detached"]["status"] == present.COMPLIES


def test_a_garage_listed_as_an_accessory_building_is_not_a_second_house():
    assert RULE not in _rows(accessory_buildings=["back_floor1"])


def test_the_working_names_the_figure_for_the_stated_use():
    """The required lot area's working reads as a sum an architect can follow: the stated use picks its figure, so
    the panel says 2 × 6000 = 12,000 sf, not the whole "6000 if use == ... else 7500" choice."""
    calc = _rows(primary_buildings=2, primary_buildings_same_use=True)[RULE]["detail"]["calc"]
    assert calc == "Required: primary buildings 2 × 6000 = 12,000 sf", calc


def test_two_primary_buildings_bring_the_shared_yard_and_south_hill_rows():
    """Two houses (stated): §325-7B needs review (questions §5.17); the South Hill row asks whether the lot is in the
    overlay, and once it is, a second primary structure does not comply. One house: neither row is shown, and the
    overlay is never asked."""
    two = _rows(primary_buildings=2, primary_buildings_same_use=True)
    assert two["R-1b.yards_not_shared"]["status"] == present.REVIEW
    assert two["R-1b.south_hill_overlay"]["status"] == present.REVIEW
    assert two["R-1b.south_hill_overlay"]["needs"] == ["south_hill_overlay"]
    assert _rows(primary_buildings=2, south_hill_overlay=True)["R-1b.south_hill_overlay"]["status"] == present.FAILS
    one = _rows(primary_buildings=1)
    assert "R-1b.yards_not_shared" not in one
    assert one["R-1b.south_hill_overlay"]["status"] == present.COMPLIES and not one["R-1b.south_hill_overlay"]["needs"]


def _ru(lot_w, lot_d):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["district"], sc["use"] = "RU", "two_family"
    sc["lot"]["points"] = [[0, 0], [lot_w, 0], [lot_w, lot_d], [0, lot_d]]
    sc["buildings"] = [{"id": "house", "outline": [[40, 40], [80, 40], [80, 80], [40, 80]], "base": 0, "floors": [10, 10]},
                       {"id": "back", "outline": [[40, 150], [70, 150], [70, 175], [40, 175]], "base": 0, "floors": [10]}]
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, "main_building": "house_floor1"}, extras=extras)
    return {i["rule"]: i for i in res["view"]["items"]}["RU.primary_structures"]


def test_ru_two_possible_buildings_on_a_big_lot_never_read_as_not_complying():
    """Review round 1 (PR2): on a 75,000 sf RU lot, two primary buildings need review for the ILPC's and the
    Planning Board's approval (note 3), so the row's words never say "does not comply" at the two-building reading;
    on a 50,000 sf lot two don't comply, and the row says so first."""
    big = _ru(250, 300)
    assert big["status"] == present.REVIEW and "does not comply" not in big["reason"], big["reason"]
    small = _ru(200, 250)
    assert small["status"] == present.REVIEW and "does not comply under that reading" in small["reason"], small["reason"]


def test_a_count_that_could_change_the_row_is_asked_even_on_a_big_lot():
    """Review round 1 (PR2, F2): with a building standing apart that could be a house, Gordium doesn't decide the
    lot-area row from the readings' ends; it asks the count (needs review), never a pass, as the docs now say."""
    item = _rows(lot=(200, 300), primary_buildings_same_use=True)[RULE]      # 60,000 sf: enough for 1 or 2
    assert item["status"] == present.REVIEW and "primary_buildings" in item["needs"], item


def test_a_use_row_cited_by_two_rules_has_one_name():
    """The full suite (test_present.test_no_two_sections_share_a_link): the lot-area row for each primary building
    cites the chart's use row, as the use rule does; one link, one name: "Use column"."""
    seen = {}
    for item in _rows(primary_buildings=2, primary_buildings_same_use=True).values():
        for c in item["detail"].get("cited") or []:
            seen.setdefault(c["link"], set()).add(c["citation"])
    assert all(len(names) == 1 for names in seen.values()), {k: v for k, v in seen.items() if len(v) > 1}
