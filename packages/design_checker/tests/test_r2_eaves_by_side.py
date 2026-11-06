"""The hand R-2b and R-2c rulebooks and #18's P0 fix (each side's eaves to its own lot line; test_eaves_by_side.py):
their side minimums differ (R-2b, and R-2c for a detached or two-family dwelling or another use: 10 ft one side,
5 ft the other; an R-2c zero-lot-line house: 15 and 10), so yard_projections must hold each side's eave to the
minimum its side carries, and needs review where the walls leave open which side that is (its review_when).

Each district's rule against the law worked by hand (test_eaves_by_side.law, which shares no code with the
measuring or the checker): never complies, nor fails, where the law doesn't, surveyed or on the tax map."""

import itertools
import sys
from pathlib import Path

import pytest

from design_checker import present
from design_checker.check import check_site, row_verdict
from rule_format.rulebook import REPO, load, rulebook_for

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_eaves_by_side as E  # noqa: E402
from test_every_reading import status  # noqa: E402


def one_height(got):
    """The measurements with the roof's height readings (which eave a pitched roof's height is taken from) set to
    the highest: every one is well under 35 ft, so no reading raises a yard (no bonus) and the eaves rows turn on
    the yards alone, which is what is tested here (without this nearly every row needs review for the height)."""
    h = got["building_height"]
    assert max(r["value"] for r in h.get("readings") or [h]) < 35
    return {**got, "building_height": {**h, "value": max(r["value"] for r in h.get("readings") or [h])}}


def rule(zone):
    return {r["id"]: r for r in load(rulebook_for(REPO / E.FACTS["jurisdiction"], zone))["rules"]}[f"{zone}.yard_projections"]


def test_p0_sceptic_b_design_does_not_comply_with_r2b_yard_projections():
    """#21 review round 22, sceptic B's design in R-2b: walls 10'-0" west and 9'-0" east, the roof 3'-6" past the
    west wall (6'-6" from the west line). Only the west side can be the 10 ft one; its eave is 3'-6" into it."""
    got, facts = E.measured(10.0, 9.0, 3.5, 0.0)
    res = check_site(E.site(E.house(10.0, 9.0, 3.5, 0.0)), {**facts, "zone": "R-2b"})
    assert status(res, "R-2b.side_yards") == present.COMPLIES
    assert status(res, "R-2b.yard_projections") == present.FAILS


@pytest.mark.parametrize("zone, use, west, east, over_west", [
    ("R-2b", "one_family_detached", 12.0, 15.0, 5.0), ("R-2c", "one_family_detached", 12.0, 15.0, 5.0),
    ("R-2c", "two_family", 12.0, 15.0, 5.0), ("R-2c", "one_family_detached_zero_lot_line", 16.0, 18.0, 4.0)])
def test_either_side_may_carry_the_larger_minimum_the_eave_fitting_one_way_needs_review(zone, use, west, east, over_west):
    """Both sides' walls at least the larger minimum from their lines (10 ft; a zero-lot-line house's 15), the west
    eave fitting only if the west is the smaller-minimum side (7 ft from its line against 10 - 2; 12 against 15 - 2):
    needs review. Without the review_when the row would comply: it is what holds it."""
    got, facts = E.measured(west, east, over_west, 0.0)
    got = one_height({**got, "use": {**got["use"], "value": use}})
    small, large = (10, 15) if use.endswith("zero_lot_line") else (5, 10)
    assert E.law(west, east, west - over_west, east, small, large) == "review"
    projections = rule(zone)
    assert row_verdict(projections, got, E.ALLOWED, facts) == present.REVIEW
    assert row_verdict({k: v for k, v in projections.items() if k != "review_when"}, got, E.ALLOWED, facts) == \
        present.COMPLIES


@pytest.mark.parametrize("zone, use, small, large", [
    ("R-2b", "one_family_detached", 5, 10), ("R-2c", "one_family_detached", 5, 10), ("R-2c", "two_family", 5, 10),
    ("R-2c", "one_family_detached_zero_lot_line", 10, 15)])
@pytest.mark.parametrize("surveyed", [True, False])
def test_r2_eaves_never_comply_or_fail_where_the_law_does_not(zone, use, small, large, surveyed):
    """Every two-side case for the district's minimums: COMPLIES only where the law complies for every lot the
    survey or the tax map allows (2 ft per line), FAILS only where it fails for every one."""
    projections = rule(zone)
    seen = set()
    for west, east, ow, oe, s, l in E._designs(24, 30):
        if (s, l) != (small, large):
            continue
        got, facts = E.measured(west, east, ow, oe, surveyed=surveyed)
        got = one_height({**got, "use": {**got["use"], "value": use}})
        shifts = (0.0,) if surveyed else E.SHIFTS
        answers = {E.law(west + dw, east + de, west - ow + dw, east - oe + de, small, large)
                   for dw, de in itertools.product(shifts, repeat=2)}
        said = row_verdict(projections, got, E.ALLOWED, facts)
        seen.add(said)
        if said == present.COMPLIES:
            assert answers == {"complies"}, (west, east, ow, oe, answers)
        if said == present.FAILS:
            assert answers == {"fails"}, (west, east, ow, oe, answers)
    assert {present.FAILS, present.COMPLIES} <= seen, seen        # the cases decide both ways, not just review


# ---- what the panel names (#18 review rounds 4-5, with this rulebook) -------------------------------------------

def _one_height(monkeypatch):
    """The checker's measuring (Ithaca's, the lots' own place's) with the roof's height settled at its highest
    reading (all under 35 ft: no bonus)."""
    from model_measurement.places.ithaca_city import measure as C
    real = C.measure

    def settled(site, facts):
        got = real(site, facts)
        h = got["building_height"]
        got["building_height"] = {**h, "value": max(r["value"] for r in h.get("readings") or [h]), "readings": [],
                                  "reason": ""}
        return got
    monkeypatch.setattr(C, "measure", settled)


def test_a_semi_detached_0_ft_side_review_names_that_side_eave(monkeypatch):
    """Semi-detached, walls 12 and 15 ft, the west eave 7 ft from its line: the narrower side may be the attached
    (0 ft) side or need 10 ft (R-2c's note 15 review, whose reason has a "; " of its own). The row is that side's eave
    against the 10 ft side's 8'-0", never "Eaves into front yard 30'-0" vs 8'-0"" (#18 round 5)."""
    _one_height(monkeypatch)
    got, facts = E.measured(12.0, 15.0, 5.0, 0.0)
    res = check_site(E.site(E.house(12.0, 15.0, 5.0, 0.0)), {**facts, "zone": "R-2c", "use": "one_family_semi_detached"})
    (row,) = [i for i in res["view"]["items"] if i.get("rule") == "R-2c.yard_projections"]
    assert row["status"] == present.REVIEW
    assert (row["name"], row["proposed"], row["required"]) == ("Eaves into side yard", "7'-0\"", "8'-0\""), row


def test_an_attached_lot_size_review_is_never_shown_as_at_least_units():
    """One-family attached, 1 dwelling unit here of 3 in the building: the lot size review (which reading of the
    building the lot holds) is about the lot area, never "1 vs 3" units with "To comply: increase it by 2" (the
    review's "units below the building's" sits in an "or"; the rule asks units to equal it, not be at least it)."""
    got, facts = E.measured(12.0, 15.0, 0.0, 0.0)
    res = check_site(E.site(E.house(12.0, 15.0, 0.0, 0.0)),
                     {**facts, "zone": "R-2c", "use": "one_family_attached", "dwelling_units": 1,
                      "attached_units_in_building": 3, "occupants": 2})
    (row,) = [i for i in res["view"]["items"] if i.get("rule") == "R-2c.lot_area_one_family_attached"]
    assert row["name"] == "Lot area" and not row.get("hint"), row
