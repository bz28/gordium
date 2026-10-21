"""R-3a.abutting_r1 (§325-19E) through the whole checker: the stricter limits reach only a lot that "directly
abuts land in either the R-1a or R-1b Zoning District", so whether it does is a stated fact (abuts_r1_district,
asked the cautious way: sharing a lot line, or across a street). Unknown: needs review, asking for it; no: not
applicable (no row: the panel lists only rules that apply); yes: needs review (the flag: the reviewer applies the
stricter limits). A one-family or two-family dwelling is exempt either way: nothing to ask."""

import copy

import pytest

from design_checker import present, rhino_logic, scenarios
from design_checker.check import check_site

RULE = "R-3a.abutting_r1"


def _item(use, **facts):
    sc = copy.deepcopy(scenarios.load(scenarios.FOLDER / "12_r3a_two_family_at_the_building_limits.yaml"))
    sc["use"] = use
    s, f, extras = scenarios.site(sc)
    res = check_site(s, {**f, **facts}, extras=extras)
    return next((i for i in res["view"]["items"] if i["rule"] == RULE), None)


def test_a_multiple_dwelling_waits_for_whether_the_lot_abuts_r1_land():
    item = _item("multiple_family")
    assert item["status"] == present.REVIEW, item
    assert item["needs"] == ["abuts_r1_district"], item
    assert rhino_logic.enter_words(item["needs"]) == "Enter whether the lot abuts R-1 land"


def test_a_lot_that_doesnt_abut_r1_land_is_not_reached_by_the_stricter_limits():
    assert _item("multiple_family", abuts_r1_district=False) is None
    assert _item("church", abuts_r1_district=False) is None


@pytest.mark.parametrize("use", ["multiple_family", "church"])
def test_a_lot_that_abuts_r1_land_needs_review(use):
    item = _item(use, abuts_r1_district=True)          # (so the "no" rows above are absent for the fact alone)
    assert item["status"] == present.REVIEW and not item.get("needs"), item


@pytest.mark.parametrize("abuts", [None, False, True])
def test_a_two_family_dwelling_is_exempt_whether_or_not_the_lot_abuts_r1_land(abuts):
    facts = {} if abuts is None else {"abuts_r1_district": abuts}
    assert _item("two_family", **facts) is None


def test_the_panel_asks_it_yes_or_no_and_a_skipped_answer_stays_unset():
    assert rhino_logic.STATED_FACTS["abuts_r1_district"][1] == "yes_no"
    assert rhino_logic.update_counts({}, {"abuts_r1_district": False}) == {"abuts_r1_district": False}
    assert rhino_logic.update_counts({"abuts_r1_district": True}, {"abuts_r1_district": None}) == \
        {"abuts_r1_district": True}
