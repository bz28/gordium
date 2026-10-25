"""P0 (found by #21 review round 22): the side yards to the eaves are each to the lot line of their own side yard
to the walls, so an eave is held to the minimum its own side carries (§325-18B: eaves may project at most 2 ft
into a required yard).

The bug: where a district's two side minimums differ (R-3a, R-2b: 10 ft one side, 5 ft the other), the eaves side
yards were sorted narrower-first on their own, apart from the walls. Walls 9'-6" from the west line and 10'-0" from
the east: only the east side can carry the 10 ft minimum. Its eave reaches 3'-6" past the wall (6'-6" from the
line: 3'-6" into the 10 ft yard, more than the 2 ft allowed), but sorted on its own it was "the narrower side yard
to the eaves" and was read against the 5 ft side's limit (5 - 2 = 3): a false COMPLIES.

The fix, at the root (model_measurement._eaves_by_wall_side): side_yard_smaller_eaves is to the lot line of the
narrower side yard to the walls (side_yard_smaller's line), side_yard_larger_eaves to the other. Which side carries
the larger minimum is then a question only when the walls leave it open (both sides, or neither, at least that
minimum to the walls; or the tax map's 2 ft per line could swap them): every such assignment must pass, else needs
review. That part is the rule's (its review_when, RULE below, the form the hand rulebooks use), since only the rule
knows the district's minimums.

Every expected answer here is worked by hand from the design's own numbers by `law`, below, which shares no code
with the measuring or the checker."""

import itertools
import random
import sys
from pathlib import Path

import pytest

from design_checker import present
from design_checker.check import row_verdict
from model_measurement.measure import measure
from rule_format.rulebook import REPO, Context

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_every_reading import FACTS, LOT, floors  # noqa: E402

ALLOWED = {"use": Context.for_jurisdiction(REPO / FACTS["jurisdiction"]).uses}
WEST, EAST = "west", "east"


def side(record) -> str:
    """Which side lot line a side yard was measured to: its points start on the lot line (x = 0 west, x = 60 east)."""
    x = record["points"][0][0]
    assert x in (0.0, 60.0), record["points"]
    return WEST if x == 0.0 else EAST


def rules(small: float, large: float) -> dict:
    """The side yards and the eaves rows of a district whose side minimums are `small` and `large` (R-3a: 5 and 10),
    with the height bonus over 40 ft, written as the hand rulebooks write them (R-3a.side_yards, R-3a.yard_projections:
    the eaves at most 2 ft into each required yard; the review_when: which side carries the larger minimum is open).
    The height bonus is left out (the test roofs are under 40 ft; with it, each pitched roof's own height readings
    would leave every row needing review whatever its yards, which is not what is tested here)."""
    s, l = f"{small}", f"{large}"
    return {
        "side_yards": {"id": "T.side_yards", "kind": "rule", "check": f"side_yard_smaller >= {small} and side_yard_larger >= {large}"},
        "yard_projections": {
            "id": "T.yard_projections", "kind": "rule",
            "check": f"side_yard_smaller_eaves >= {s} - 2 and side_yard_larger_eaves >= {l} - 2",
            # which side carries the larger minimum is open (both sides' walls at least that far from their lines,
            # or neither), and the eaves fit one way only: needs review (one review_when for each way)
            "review_when": [
                {"when": f"(side_yard_smaller >= {l} or side_yard_larger < {l}) and side_yard_smaller_eaves >= {l} - 2"
                         f" and side_yard_larger_eaves >= {s} - 2 and side_yard_larger_eaves < {l} - 2",
                 "reason": "the narrower side may be the one that carries the larger minimum"},
                {"when": f"(side_yard_smaller >= {l} or side_yard_larger < {l}) and side_yard_larger_eaves >= {l} - 2"
                         f" and side_yard_smaller_eaves >= {s} - 2 and side_yard_smaller_eaves < {l} - 2",
                 "reason": "the narrower side may be the one that carries the larger minimum"}]},
        # the rule as it read before the fix (no review_when): with the eaves paired by side it no longer passes the
        # P0 design; the review_when is for the cases the walls leave open
        "yard_projections_plain": {
            "id": "T.yard_projections_plain", "kind": "rule",
            "check": f"side_yard_smaller_eaves >= {s} - 2 and side_yard_larger_eaves >= {l} - 2"},
    }


def site(buildings, lot=LOT):
    n = len(lot)
    return {"units": "ft", "problems": [], "buildings": buildings,
            "lot": {"id": "lot", "edges": [{"points": [list(lot[i]), list(lot[(i + 1) % n])], "curved": False}
                                           for i in range(n)]}}


def house(west: float, east: float, over_west: float, over_east: float, width: float = 60.0) -> list:
    """Two stories 30 to 70 ft back, walls `west` ft from the west line and `east` from the east, and a gable roof
    drawn as its own solid on them, its level underside reaching `over_west` and `over_east` past those walls (the
    eaves; no fascia), the ridge over the middle of the roof."""
    x0, x1 = west, width - east
    xa, xb = x0 - over_west, x1 + over_east
    xm, base, ridge, y0, y1 = (xa + xb) / 2, 20, 26, 30, 70
    faces = [[(xa, y0, base), (xb, y0, base), (xb, y1, base), (xa, y1, base)],
             [(xa, y0, base), (xm, y0, ridge), (xm, y1, ridge), (xa, y1, base)],
             [(xm, y0, ridge), (xb, y0, base), (xb, y1, base), (xm, y1, ridge)],
             [(xa, y0, base), (xb, y0, base), (xm, y0, ridge)], [(xa, y1, base), (xb, y1, base), (xm, y1, ridge)]]
    roof = {"id": "roof", "faces": [{"points": [list(p) for p in f]} for f in faces], "problems": []}
    return floors(x0, y0, x1, y1, 2) + [roof]


def measured(west, east, over_west, over_east, surveyed=True, confirmed=True):
    facts = dict(FACTS, lot_surveyed=surveyed)
    built = house(west, east, over_west, over_east)
    got = measure(site(built), facts)
    if confirmed:
        cands = got["side_yard_smaller"].get("eave_candidates") or []
        facts["eaves_confirmed"] = [{"overhang": c, "value": True, "source": "entered by you",
                                     "confirmed_by": "the architect", "date": "2026-10-21"} for c in cands]
        got = measure(site(built), facts)
    return got, facts


def verdict(rule, got, facts):
    return row_verdict(rule, got, ALLOWED, facts)


# ---- the law, by hand ------------------------------------------------------------------------------------------

def law(west, east, eave_west, eave_east, small, large) -> str:
    """§325-18B with the chart's two side minimums, from the design's numbers alone: "complies", "fails" or
    "review". A side carries the larger minimum only if its walls are at least that far from its line; if both
    sides could, or neither can, each way is a reading. Under each reading every eave is at most 2 ft into its
    side's required yard (at least that side's minimum less 2 ft from its line). Complies if every reading does,
    fails if none does, else review (the every-reading rule)."""
    ways = [w for w, wall in (("west", west), ("east", east)) if wall >= large]
    if len(ways) != 1:
        ways = ["west", "east"]
    ok = []
    for big in ways:
        need_w, need_e = (large, small) if big == "west" else (small, large)
        ok.append(eave_west >= need_w - 2 and eave_east >= need_e - 2)
    return "complies" if all(ok) else "fails" if not any(ok) else "review"


SAYS = {"complies": present.COMPLIES, "fails": present.FAILS, "review": present.REVIEW}


# ---- the two reproductions ------------------------------------------------------------------------------------

def test_p0_hand_r3a_design_walls_9_6_and_10_0_the_east_eave_3_6_into_the_10_ft_yard_fails():
    """Sceptic A's design (R-3a, 5 and 10 ft): 60 x 120 lot, walls 9'-6" from the west line and 10'-0" from the east,
    eaves 0'-6" and 3'-6" past them (9'-0" and 6'-6" from the lines). The west walls are under 10 ft, so the east side
    is the one that must be 10 ft; its eave at 6'-6" is 3'-6" into it (limit 8'-0"): the law says it fails.
    Before the fix: side_yard_smaller_eaves 6.5 (the EAST side) against 5 - 2 = 3, larger 9.0 (west) against 8:
    COMPLIES."""
    got, facts = measured(9.5, 10.0, 0.5, 3.5)
    assert (got["side_yard_smaller"]["value"], side(got["side_yard_smaller"])) == (9.5, WEST)
    assert (got["side_yard_larger"]["value"], side(got["side_yard_larger"])) == (10.0, EAST)
    assert (got["side_yard_smaller_eaves"]["value"], side(got["side_yard_smaller_eaves"])) == (9.0, WEST)
    assert (got["side_yard_larger_eaves"]["value"], side(got["side_yard_larger_eaves"])) == (6.5, EAST)
    r = rules(5, 10)
    assert law(9.5, 10.0, 9.0, 6.5, 5, 10) == "fails"
    assert verdict(r["yard_projections"], got, facts) == present.FAILS
    assert verdict(r["yard_projections_plain"], got, facts) == present.FAILS
    assert verdict(r["side_yards"], got, facts) == present.COMPLIES


def test_p0_r2b_design_walls_10_and_9_the_west_eave_3_6_into_the_10_ft_yard_fails():
    """Sceptic B's design (R-2b, 5 and 10 ft): walls 10'-0" from the west line and 9'-0" from the east, a roof slab
    reaching 3'-6" past the west wall (6'-6" from the west line). The east walls are under 10 ft, so the west side
    must be 10 ft; its eave is 3'-6" into it: fails. Before the fix the west eave was sorted as the narrower
    side yard to the eaves (6.5 against 3) and the east as the wider (9 against 8): COMPLIES."""
    got, facts = measured(10.0, 9.0, 3.5, 0.0)
    assert (got["side_yard_smaller_eaves"]["value"], side(got["side_yard_smaller_eaves"])) == (9.0, EAST)
    assert (got["side_yard_larger_eaves"]["value"], side(got["side_yard_larger_eaves"])) == (6.5, WEST)
    assert law(10.0, 9.0, 6.5, 9.0, 5, 10) == "fails"
    r = rules(5, 10)
    assert verdict(r["yard_projections"], got, facts) == present.FAILS
    assert verdict(r["yard_projections_plain"], got, facts) == present.FAILS


def test_both_sides_able_to_carry_10_ft_the_eave_fitting_one_way_only_needs_review():
    """Walls 12 ft west and 15 ft east (either side can be the 10 ft one), the west eave 5 ft past its wall (7 ft
    from the line), none on the east. West the 5 ft side: 7 >= 3 and 15 >= 8, complies; west the 10 ft side:
    7 < 8. One reading passes, the other doesn't: needs review, never complies."""
    got, facts = measured(12.0, 15.0, 5.0, 0.0)
    assert law(12.0, 15.0, 7.0, 15.0, 5, 10) == "review"
    r = rules(5, 10)
    assert verdict(r["yard_projections"], got, facts) == present.REVIEW


def test_equal_walls_read_each_side_as_the_narrower():
    """Walls 12 ft from both lines (which is narrower is no fact at all), eaves 1 ft west and 5 ft east (11 and 7
    from the lines): both pairings are readings. Either side may be the 10 ft one, and the east eave fits only if
    it is the 5 ft side: review. With the east eave 9'-6" past (2'-6" from the line) it fits neither way: the law
    says fails; the two pairings are separate readings of two measurements, which the checker may also combine
    across (each the west eave), so it may say needs review: never complies."""
    got, facts = measured(12.0, 12.0, 1.0, 5.0)
    for name in ("side_yard_smaller_eaves", "side_yard_larger_eaves"):
        assert got[name]["value"] is None
        assert sorted((r["value"], side(r)) for r in got[name]["readings"]) == [(7.0, EAST), (11.0, WEST)]
    assert law(12.0, 12.0, 11.0, 7.0, 5, 10) == "review"
    assert verdict(rules(5, 10)["yard_projections"], got, facts) == present.REVIEW
    got, facts = measured(12.0, 12.0, 1.0, 9.5)
    assert law(12.0, 12.0, 11.0, 2.5, 5, 10) == "fails"
    assert verdict(rules(5, 10)["yard_projections"], got, facts) in (present.FAILS, present.REVIEW)


# ---- every two-side case, against the law by hand ------------------------------------------------------------

CASES = [(5, 10), (10, 15), (0, 10)]


def _designs(seed: int, n: int):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        small, large = rnd.choice(CASES)
        west, east = (round(rnd.uniform(max(small - 1, 2.5), large + 4), 1) for _ in range(2))
        ow, oe = (round(rnd.choice([0.0, rnd.uniform(0, 4.5)]), 1) for _ in range(2))
        out.append((west, east, min(ow, west - 0.5), min(oe, east - 0.5), small, large))
    # the edges: each wall at either minimum, each eave at either limit, the walls equal
    for small, large in CASES:
        for west, east in ((large, large), (large - 0.5, large), (large, max(small, 2.5)), (large + 2, large + 2)):
            for ow, oe in itertools.product((0.0, 2.0, 2.5), repeat=2):
                out.append((west, east, min(ow, west - 0.5), min(oe, east - 0.5), small, large))
    return out


@pytest.mark.parametrize("west, east, ow, oe, small, large", _designs(18, 40))
def test_surveyed_lot_every_two_side_case_matches_the_law_worked_by_hand(west, east, ow, oe, small, large):
    """A surveyed lot, the eaves confirmed (one reading of the walls): the eaves row is exactly the law's answer.
    One allowance, always the cautious way: walls exactly as far from both lines with unequal eaves are read both
    ways (either side the narrower), so the row may ask for review where the law gives an answer."""
    got, facts = measured(west, east, ow, oe)
    want = law(west, east, round(west - ow, 6), round(east - oe, 6), small, large)
    said = verdict(rules(small, large)["yard_projections"], got, facts)
    if west == east and ow != oe:
        assert said in (SAYS[want], present.REVIEW), (west, east, ow, oe)
    else:
        assert said == SAYS[want], (west, east, ow, oe)


SHIFTS = (-2.0, -1.0, 0.0, 1.0, 2.0)


@pytest.mark.parametrize("west, east, ow, oe, small, large", _designs(325, 30))
def test_tax_map_lot_never_complies_or_fails_against_a_lot_the_tax_map_allows(west, east, ow, oe, small, large):
    """On the tax map each lot line may be up to 2 ft off either way, the walls and the eave on that side moving
    together. The eaves row may say complies only if the law says so for every such lot, and fails only if it fails
    for every one (in between it needs review)."""
    got, facts = measured(west, east, ow, oe, surveyed=False)
    answers = {law(west + dw, east + de, west - ow + dw, east - oe + de, small, large)
               for dw, de in itertools.product(SHIFTS, repeat=2)}
    said = verdict(rules(small, large)["yard_projections"], got, facts)
    if said == present.COMPLIES:
        assert answers == {"complies"}, (west, east, ow, oe, answers)
    if said == present.FAILS:
        assert answers == {"fails"}, (west, east, ow, oe, answers)


@pytest.mark.parametrize("west, east, ow, oe", [(9.5, 10.0, 0.5, 3.5), (10.0, 9.0, 3.5, 0.0), (12.0, 15.0, 5.0, 0.0)])
def test_unconfirmed_eaves_never_comply_where_the_law_does_not(west, east, ow, oe):
    """Not yet confirmed as eaves, the overhangs are read both ways (eave or not: the walls move): never COMPLIES
    where the law, with them eaves, does not."""
    got, facts = measured(west, east, ow, oe, confirmed=False)
    assert law(west, east, west - ow, east - oe, 5, 10) != "complies"
    assert verdict(rules(5, 10)["yard_projections"], got, facts) != present.COMPLIES
