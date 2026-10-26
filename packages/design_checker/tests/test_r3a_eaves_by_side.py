"""The hand R-3a rulebook and #18's P0 fix (each side's eaves to its own lot line; test_eaves_by_side.py): R-3a's
side minimums differ (10 ft one side, 5 ft the other), so R-3a.yard_projections must hold each side's eave to the
minimum its side carries, and needs review where the walls leave open which side that is (its review_when).

The two reproductions of the false pass (#21 review round 22) run through the whole checker with the hand R-3a
rulebook, as in the demo. Then every two-side case against the law worked by hand (test_eaves_by_side.law, which
shares no code with the measuring or the checker): never complies, nor fails, where the law doesn't."""

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

RULES = {r["id"]: r for r in load(rulebook_for(REPO / E.FACTS["jurisdiction"], "R-3a"))["rules"]}
PROJECTIONS = RULES["R-3a.yard_projections"]


def checked(west, east, ow, oe, **facts):
    got, f = E.measured(west, east, ow, oe, **facts)
    return check_site(E.site(E.house(west, east, ow, oe)), {**f, "zone": "R-3a"}), got, f


def test_p0_sceptic_a_design_does_not_comply_with_r3a_yard_projections():
    """Walls 9'-6" west and 10'-0" east, eaves 9'-0" and 6'-6" from the lines (eaves confirmed): the east side must
    be the 10 ft one (the west walls are under 10 ft) and its eave is 3'-6" into it. The demo said COMPLIES for
    R-3a.side_yards and R-3a.yard_projections; the law: the side yards comply, the eaves don't."""
    res, got, _ = checked(9.5, 10.0, 0.5, 3.5)
    assert E.side(got["side_yard_larger_eaves"]) == E.EAST and got["side_yard_larger_eaves"]["value"] == 6.5
    assert status(res, "R-3a.side_yards") == present.COMPLIES
    assert status(res, "R-3a.yard_projections") == present.FAILS
    (row,) = [i for i in res["view"]["items"] if i.get("rule") == "R-3a.yard_projections"]
    assert (row["name"], row["proposed"], row["required"]) == ("Eaves into side yard", "6'-6\"", "8'-0\"")


def test_p0_sceptic_b_design_does_not_comply_with_r3a_yard_projections():
    """Walls 10'-0" west and 9'-0" east, the roof 3'-6" past the west wall (6'-6" from the west line): the west side
    must be the 10 ft one; its eave is 3'-6" into it."""
    res, _, _ = checked(10.0, 9.0, 3.5, 0.0)
    assert status(res, "R-3a.yard_projections") == present.FAILS


def test_either_side_may_be_the_10_ft_one_the_eave_fitting_one_way_needs_review():
    """Walls 12 and 15 ft (either side may be the 10 ft one), the west eave 7 ft from its line: it fits only if the
    west is the 5 ft side. Needs review (the review_when), never complies; it says why."""
    res, got, facts = checked(12.0, 15.0, 5.0, 0.0)
    assert status(res, "R-3a.yard_projections") == present.REVIEW
    # the panel: that side's eave, and the rule's own question, never "Eaves into front yard" and the roof's height
    # (every height reading under 40 ft: it changes nothing; #20 review round 1, two sceptics)
    (row,) = [i for i in res["view"]["items"] if i.get("rule") == "R-3a.yard_projections"]
    assert row["name"] == "Eaves into side yard", row["name"]
    assert row["reason"].startswith("Which side yard is the 10 ft one"), row["reason"]
    assert "pitched roof" not in row["reason"], row["reason"]
    # the rule itself, the roof's height readings aside (each well under 40 ft: no bonus), is the review_when's
    flat = {**{k: dict(v) for k, v in got.items()}, "building_height": {**got["building_height"], "value": 26.0}}
    assert row_verdict(PROJECTIONS, flat, E.ALLOWED, facts) == present.REVIEW
    assert row_verdict({k: v for k, v in PROJECTIONS.items() if k != "review_when"}, flat, E.ALLOWED, facts) == \
        present.COMPLIES          # without the review_when it would comply: the review_when is what holds it


@pytest.mark.parametrize("west, east, ow, oe, surveyed",
                         [(*d[:4], s) for d in E._designs(3, 24) if d[4:] == (5, 10) for s in (True, False)])
def test_r3a_eaves_never_comply_or_fail_where_the_law_does_not(west, east, ow, oe, surveyed):
    """Each two-side case (5 and 10 ft) with R-3a's own rule: COMPLIES only where the law complies for every lot the
    survey or the tax map allows (2 ft per line), FAILS only where it fails for every one."""
    got, facts = E.measured(west, east, ow, oe, surveyed=surveyed)
    shifts = (0.0,) if surveyed else E.SHIFTS
    answers = {E.law(west + dw, east + de, west - ow + dw, east - oe + de, 5, 10)
               for dw, de in itertools.product(shifts, repeat=2)}
    said = row_verdict(PROJECTIONS, got, E.ALLOWED, facts)
    if said == present.COMPLIES:
        assert answers == {"complies"}, (west, east, ow, oe, answers)
    if said == present.FAILS:
        assert answers == {"fails"}, (west, east, ow, oe, answers)
