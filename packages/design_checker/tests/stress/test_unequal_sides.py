"""The stress test for two side minimums that differ (R-3a, R-2b: 10 ft one side, 5 ft the other), the case the
R-1b oracle can't see: its two minimums are equal, so which side is which never matters to it, and #21 review
round 22's P0 (the side yards to the eaves sorted narrower-first apart from the walls; an eave 3'-6" into the 10 ft
yard read against the 5 ft side's limit) went through every stress run.

Random designs made the way an architect makes them (move the house sideways, stretch it, put a pitched roof on it,
drag each eave out to its own depth), on the lots with two side lines, surveyed and tax-map. Gordium's own
measurements are checked against an eaves rule written the way the hand rulebooks write it (EAVES, below; no
height bonus, so the roof's height readings don't hold every row back), and against the oracle's own answer
(oracle.unequal_sides_verdict: each side's walls and eaves to its own lot line, from the design description, every
reading of the overhang, each tax-map line up to 2 ft off). Gordium may say complies only where the oracle says
PASS, and does not comply only where it says FAIL.

    GORDIUM_STRESS_DESIGNS=400 pytest packages/design_checker/tests/stress/test_unequal_sides.py

runs a longer sample; `--runslow` runs FULL."""

import os
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate  # noqa: E402
import oracle  # noqa: E402

from design_checker import present  # noqa: E402
from design_checker.check import row_verdict  # noqa: E402
from model_measurement.measure import measure  # noqa: E402
from rule_format.rulebook import REPO, Context  # noqa: E402

DESIGNS = int(os.environ.get("GORDIUM_STRESS_DESIGNS", "150"))
FULL = 1000
SEED = int(os.environ.get("GORDIUM_STRESS_SEED", "20261025"))
LOTS = ("sample_tax", "sample_survey", "narrow")
SMALL, LARGE = 5, 10
ALLOWED = {"use": Context.for_jurisdiction(REPO / generate.JURISDICTION).uses}


def _rule(small, large):
    s, l = small, large                                             # noqa: E741
    way = "(side_yard_smaller >= {l} or side_yard_larger < {l})".format(l=l)
    return {"id": "TEST.unequal_side_eaves", "kind": "rule",
            "check": f"side_yard_smaller_eaves >= {s} - 2 and side_yard_larger_eaves >= {l} - 2",
            "review_when": [
                {"when": f"{way} and side_yard_smaller_eaves >= {l} - 2 and side_yard_larger_eaves >= {s} - 2"
                         f" and side_yard_larger_eaves < {l} - 2", "reason": "which side is open"},
                {"when": f"{way} and side_yard_larger_eaves >= {l} - 2 and side_yard_smaller_eaves >= {s} - 2"
                         f" and side_yard_smaller_eaves < {l} - 2", "reason": "which side is open"}]}


EAVES = _rule(SMALL, LARGE)


def random_case(rng: random.Random) -> dict:
    """A lot with two side lines and the edits: the house moved sideways and its east face dragged, so each wall ends
    up 7.5 to 12.5 ft from its side line (where which side can carry the 10 ft minimum is decided, or left open), a gable
    roof with its eaves on the side walls (or, one time in ten, on the front and rear), each eave dragged to its
    own depth."""
    q = lambda x: round(x * 4) / 4                                                 # noqa: E731
    name = rng.choice(LOTS)
    width = generate.lot(name)["points"][1][0]
    outline = generate.starting_design(name)["parts"][0]["outline"]
    xs = [x for x, _ in outline]
    west, east = q(rng.uniform(7.5, 12.5)), q(rng.uniform(7.5, 12.5))
    dx = west - min(xs)
    edits = [{"op": "move_house", "dx": dx, "dy": 0.0},
             {"op": "stretch", "face": _east_face(outline), "amount": (width - east) - (max(xs) + dx)}]
    axis = _axis_across(outline) if rng.random() < 0.9 else 1 - _axis_across(outline)
    edits.append({"op": "add_roof", "kind": "roof", "axis": axis, "over": 0.0,
                  "fascia": rng.choice([0.0, 0.0, 0.5]), "inset": 0.0, "rise": q(rng.uniform(6, 12))})
    edits.append({"op": "overhangs", "over": rng.choice([0.0, 0.5, q(rng.uniform(0, 5)), q(rng.uniform(2, 5))]),
                  "over2": rng.choice([0.0, 0.5, q(rng.uniform(0, 5)), q(rng.uniform(2, 5))])})
    return {"lot": name, "edits": edits, "confirmed": rng.random() < 0.85}


def check_case(case: dict) -> dict | None:
    """Gordium's verdict and the oracle's for one case, or None when the oracle doesn't cover it."""
    design, done = generate.build(case["lot"], case["edits"])
    if not any(e["op"] == "overhangs" for e in done):
        return None
    tax = not design["lot"]["surveyed"]
    want = oracle.unequal_sides_verdict(design, SMALL, LARGE, tolerance=tax, eaves_confirmed=case.get("confirmed"))
    if want is None:
        return None
    facts = generate.gordium_facts(design)
    site = generate.gordium_site(design)
    got = measure(site, facts)
    if case.get("confirmed"):              # the architect confirms each overhang Gordium asks about is an eave
        facts["eaves_confirmed"] = [{"overhang": c, "value": True, "source": "entered by you", "confirmed_by": "the "
                                     "architect", "date": "2026-10-25"}
                                    for c in got["side_yard_smaller"].get("eave_candidates") or []]
        got = measure(site, facts)
    said = row_verdict(EAVES, got, ALLOWED, facts)
    bad = (said == present.COMPLIES and want != oracle.PASS) or (said == present.FAILS and want != oracle.FAIL)
    return {"said": said, "want": want, "bad": bad, "case": case}


def run_sample(n: int, seed: int) -> list:
    rng = random.Random(seed)
    return [c for c in (check_case(random_case(rng)) for _ in range(n)) if c]


def _assert_clean(results):
    bad = [r for r in results if r["bad"]]
    assert not bad, f"{len(bad)} of {len(results)}: " + "; ".join(f"{r['said']} vs oracle {r['want']}: {r['case']}"
                                                                   for r in bad[:5])
    said = {r["said"] for r in results}
    assert {present.COMPLIES, present.FAILS} <= said, said      # the sample decides both ways: it can bite


@pytest.mark.parametrize("walls, eaves, want", [
    ((9.5, 10.0), (9.0, 6.5), oracle.FAIL),          # only the east can be the 10 ft side; its eave 3'-6" into it
    ((10.0, 9.0), (6.5, 9.0), oracle.FAIL),          # only the west can; its eave 3'-6" into it
    ((9.5, 10.0), (9.0, 8.0), oracle.PASS),          # the east eave exactly 2 ft into the 10 ft yard
    ((12.0, 15.0), (7.0, 15.0), oracle.UNDECIDED),   # either side may be the 10 ft one; fits only one way
    ((12.0, 15.0), (8.0, 8.0), oracle.PASS),         # fits both ways
    ((12.0, 15.0), (2.9, 15.0), oracle.FAIL),        # over 2 ft into even the 5 ft yard
    ((7.0, 9.0), (7.0, 9.0), oracle.UNDECIDED),      # neither side can carry 10 ft: either way, fits one
])
def test_the_oracles_two_side_rule_worked_by_hand(walls, eaves, want):
    """The oracle checked first: §325-18B with 5 and 10 ft side minimums, each case worked by hand (west, east)."""
    w, e = dict(zip(("west", "east"), walls)), dict(zip(("west", "east"), eaves))
    assert oracle.unequal_sides_eaves(w, e, SMALL, LARGE) == want


def test_the_p0_design_does_not_comply():
    """#21 review round 22's design on a surveyed lot: walls 9'-6" from one side line and 10'-0" from the other, the
    eave on the 10 ft side 3'-6" past its wall (into the required 10 ft yard by 3'-6"), the eaves confirmed. The
    oracle: FAIL; so must Gordium be (before #18's fix it said complies)."""
    lt = generate.lot("sample_survey")                       # 73 ft wide
    floors = generate.starting_design("sample_survey")["parts"]
    xs = [x for p in floors for x, _ in p["outline"]]
    width = max(xs) - min(xs)
    move = 9.5 - min(xs)
    stretch = (lt["points"][1][0] - 10.0) - (max(xs) + move)    # the east wall 10 ft from the east line
    edits = [{"op": "move_house", "dx": move, "dy": 0.0},
             {"op": "stretch", "face": _east_face(floors[0]["outline"]), "amount": stretch},
             {"op": "add_roof", "kind": "roof", "axis": _axis_across(floors[0]["outline"]), "over": 0.0, "fascia": 0.0,
              "inset": 0.0, "rise": 8.0}]
    roof = next(p for p in generate.build("sample_survey", edits)[0]["parts"] if p["kind"] == "roof")
    east_is_p1 = roof["corners"][1][0] > roof["corners"][0][0]
    over = {"over": 0.5, "over2": 3.5} if east_is_p1 else {"over": 3.5, "over2": 0.5}     # 3'-6" on the east
    case = {"lot": "sample_survey", "edits": edits + [{"op": "overhangs", **over}], "confirmed": True}
    got = check_case(case)
    design = generate.build("sample_survey", case["edits"])[0]
    walls = oracle.side_worlds(design, eaves_confirmed=True)[0]
    assert {k: round(v, 6) for k, v in walls[0].items()} == {"east": 10.0, "west": 9.5}, walls
    assert {k: round(v, 6) for k, v in walls[1].items()} == {"east": 6.5, "west": 9.0}, walls
    assert got is not None and width > 0
    assert got["want"] == oracle.FAIL, got
    assert got["said"] == present.FAILS, got


def _case(lot, west, east, over_west, over_east, confirmed=True):
    """The starting house on `lot` with its walls `west` and `east` ft from the side lines and its two eaves those
    depths past them (a gable roof across, its eaves on the side walls)."""
    lt = generate.lot(lot)
    outline = generate.starting_design(lot)["parts"][0]["outline"]
    xs = [x for x, _ in outline]
    dx = west - min(xs)
    edits = [{"op": "move_house", "dx": dx, "dy": 0.0},
             {"op": "stretch", "face": _east_face(outline), "amount": (lt["points"][1][0] - east) - (max(xs) + dx)},
             {"op": "add_roof", "kind": "roof", "axis": _axis_across(outline), "over": 0.0, "fascia": 0.0,
              "inset": 0.0, "rise": 8.0}]
    roof = next(p for p in generate.build(lot, edits)[0]["parts"] if p["kind"] == "roof")
    east_is_p1 = roof["corners"][1][0] > roof["corners"][0][0]
    over = {"over": over_west, "over2": over_east} if east_is_p1 else {"over": over_east, "over2": over_west}
    return {"lot": lot, "edits": edits + [{"op": "overhangs", **over}], "confirmed": confirmed}


def test_the_oracle_tries_the_tax_map_shift_where_a_side_becomes_able_to_carry_10_ft():
    """#22 review round 1: on the tax map (each line up to 2 ft off), walls 9'-3" west and 12'-0" east, the west eave
    2'-3" past its wall. At +9" the west walls are exactly 10 ft from the line, so either side may be the 10 ft one,
    and with the west the 10 ft one its eave, 7'-9" from the line, is over 2 ft in. Sampling only -2, -1, 0, 1, 2 ft
    missed that world and said PASS; the answer is UNDECIDED."""
    design = generate.build("sample_tax", _case("sample_tax", 9.25, 12.0, 2.25, 0.0)["edits"])[0]
    assert oracle.unequal_sides_verdict(design, SMALL, LARGE, tolerance=True, eaves_confirmed=True) == \
        oracle.UNDECIDED


def _east_face(outline):
    """The index of the outline edge facing east (its outward normal +x)."""
    for k in range(len(outline)):
        a, b, (nx, ny) = generate._face(outline, k)
        if nx > 0.9:
            return k
    raise AssertionError(outline)


def _axis_across(outline):
    """The add_roof axis whose eaves (the p0-p1 ends) face the side lines (x)."""
    for k in (0, 1):
        c = outline[k:] + outline[:k]
        if abs(c[1][0] - c[0][0]) > abs(c[1][1] - c[0][1]):
            return k
    raise AssertionError(outline)


def test_unequal_side_minimums_eaves_never_comply_or_fail_against_the_oracle():
    _assert_clean(run_sample(DESIGNS, SEED))


@pytest.mark.slow
def test_unequal_side_minimums_eaves_never_comply_or_fail_against_the_oracle_full():
    _assert_clean(run_sample(FULL, SEED + 1))
