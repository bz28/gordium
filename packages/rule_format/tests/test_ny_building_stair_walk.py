"""A property walk over New York's Building Code stair rules (section group 7c of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: Section 1011, pp.331-334).

Every drafted rule reading a stair's measures is walked (found from the formulas, never listed), over every occupancy
group (and a building of two or more, and one whose group isn't stated), the flight in an exit stair enclosure yes, no
and not worked out, spiral yes, no and not worked out, and a grid around every printed limit. The oracle is written
from the law here, never from the rules:
- strict, when a pass is allowed: risers 4 to 7 in (7 3/4 in in Group R-3, exception 3, which has no other condition
  there); treads at least 11 in; risers and treads within 3/8 in; headroom at least 80 in over the flight and past its
  bottom riser; width at least 44 in in a building with a 903.3.1.1 or 903.3.1.2 sprinkler system throughout (else
  1009.3's accessible means of egress may ask more between the handrails); handrails on both sides.
- loosest, when a fail is allowed: every exception that may apply taken. A flight not shown to stand in an exit
  stair enclosure may be within a dwelling unit, on a deck, patio or walkway, or a stepped aisle (1011.1's exception,
  Section 1030), which leaves every limit open; a spiral stairway follows 1011.10 (not brought in); exception 3's
  7 3/4 in and 10 in reach Group R-3, R-2 within a dwelling unit, and Group U; exception 5's 8 in and 9 in Group I-3;
  1011.3's floor-opening projection Group R-3, R-2 within a dwelling unit and U; 1011.2's 36 in under 50 occupants
  (the load the stairway serves isn't worked out) and 20 in at a chairlift (Group R-3, R-2 within a dwelling unit);
  1011.11's exceptions 3 and 5 at one or two risers. A group not stated, or two or more, may be any of these.
So a flight whose every stair rule passes is one the law can't fault on these measures, and one that fails is past
every exception that could reach it. Stairway capacity (1005.3.1, the load each stairway serves) is the stairway
capacity flag's, shown for every building."""

import itertools

import pytest

from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"]
UNSTATED = object()
TRI = (True, False, UNSTATED)
RISERS = (3.5, 3.9375, 4, 6.5, 7, 7.0625, 7.5, 7.75, 7.8125, 8, 8.0625, 9, 12)
SPREADS = (0, 0.375, 0.4375, 3)
TREADS = (6, 8.9375, 9, 9.5, 9.9375, 10, 10.5, 10.9375, 11, 14)
VARIATIONS = (0, 0.25, 0.375, 0.4375, 1)
HEADROOMS = (60, 77.9375, 78, 79.9375, 80, 98.5)
WIDTHS = (12, 19.9375, 20, 30, 35.9375, 36, 40, 43.9375, 44, 48, 60)
SIDES = (0, 1, 2)
RISER_COUNTS = (1, 2, 3, 9, UNSTATED)
SPRINKLERS = {"nfpa_13": (True, False), "nfpa_13r": (False, True), "none": (False, False), UNSTATED: None}
WALKED = {"general.bc_1011_2_stair_width", "general.bc_1011_3_stair_headroom", "general.bc_1011_5_2_riser_height",
          "general.bc_1011_5_2_tread_depth", "general.bc_1011_5_4_riser_uniformity",
          "general.bc_1011_5_4_tread_uniformity", "general.bc_1011_11_stair_handrails"}
WHERE = GROUPS + ["mixed", "unstated"]


def _may(v):
    return v is True or v is UNSTATED


def _open(enclosure):
    """Not shown in an exit stair enclosure: within a dwelling unit, a deck or walkway, a stepped aisle may be."""
    return enclosure is not True


def _group(where):
    return UNSTATED if where == "unstated" else where


def _any(group, *these):
    return group is UNSTATED or group == "mixed" or group in these


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def rules():
    return {r["id"]: r for r in load(RULEBOOK)["rules"]}


def _reads(r):
    out = set()
    for t in [r.get("applies_when"), r.get("check")] + [w["when"] for w in r.get("review_when") or []]:
        if t:
            out |= formula.names(t)
    return out


def _given(group, sprinkler=UNSTATED):
    g = {}
    if group is not UNSTATED:
        g["occupancy_group"] = group
    if sprinkler is not UNSTATED:
        g["sprinklered_903_3_1_1"], g["sprinklered_903_3_1_2"] = SPRINKLERS[sprinkler]
    return g


def _row(r, measures, given, ctx):
    m = {k: v for k, v in measures.items() if v is not UNSTATED}
    return parts.rows(r, {"stair": [{"id": "p", "measures": m}]}, given, ctx.allowed())[0]["outcome"]


def test_the_walk_finds_every_stair_rule(rules):
    got = {rid for rid, r in rules.items() if r["kind"] == "rule" and r.get("for_each") == "stair"
           and any(n.startswith("stair_") for n in _reads(r))}
    assert got == WALKED


@pytest.mark.parametrize("where", WHERE)
def test_risers(ctx, rules, where):
    r, group, bad = rules["general.bc_1011_5_2_riser_height"], _group(where), []
    for enc, sp, tall, spread in itertools.product(TRI, TRI, RISERS, SPREADS):
        low = tall - spread
        most = 7.75 if group == "R-3" else 7
        strict = low >= 4 and tall <= most
        loosest_most = 7
        if _any(group, "R-3", "U") or (_any(group, "R-2") and _open(enc)):
            loosest_most = 7.75
        if _any(group, "I-3"):
            loosest_most = 8
        unbounded = _may(sp) or _open(enc)
        fail_ok = not unbounded and (tall > loosest_most or low < 4)
        got = _row(r, {"stair_riser_height": tall, "stair_riser_variation": spread, "stair_spiral": sp,
                       "stair_in_exit_enclosure": enc}, _given(group), ctx)
        if (got == "pass" and not strict) or (got == "fail" and not fail_ok) or got == "not_applicable":
            bad.append((where, enc, sp, tall, spread, got))
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", WHERE)
def test_treads(ctx, rules, where):
    r, group, bad = rules["general.bc_1011_5_2_tread_depth"], _group(where), []
    for enc, sp, t in itertools.product(TRI, TRI, TREADS):
        least = 11
        if _any(group, "R-3", "U") or (_any(group, "R-2") and _open(enc)):
            least = 10
        if _any(group, "I-3"):
            least = 9
        if _may(sp) or _open(enc):
            least = 0
        got = _row(r, {"stair_tread_depth": t, "stair_spiral": sp, "stair_in_exit_enclosure": enc}, _given(group),
                   ctx)
        if (got == "pass" and t < 11) or (got == "fail" and t >= least) or got == "not_applicable":
            bad.append((where, enc, sp, t, got))
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


@pytest.mark.parametrize("which", ["riser", "tread"])
def test_uniformity(ctx, rules, which):
    r, bad = rules[f"general.bc_1011_5_4_{which}_uniformity"], []
    for enc, sp, v in itertools.product(TRI, TRI, VARIATIONS):
        unbounded = _open(enc) or (which == "tread" and _may(sp))       # exception 2: consistently shaped winders
        got = _row(r, {f"stair_{which}_variation": v, "stair_spiral": sp, "stair_in_exit_enclosure": enc}, {}, ctx)
        if (got == "pass" and v > 0.375) or (got == "fail" and (unbounded or v <= 0.375)) or got == "not_applicable":
            bad.append((which, enc, sp, v, got))
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", WHERE)
def test_headroom(ctx, rules, where):
    r, group, bad = rules["general.bc_1011_3_stair_headroom"], _group(where), []
    for enc, sp, h, past in itertools.product(TRI, TRI, HEADROOMS, HEADROOMS):
        low = min(h, past)
        limit = 78 if _may(sp) else 80
        unbounded = _any(group, "R-3", "U") or _open(enc)          # exception 2 (within an R-2 unit: _open)
        got = _row(r, {"stair_headroom": h, "stair_headroom_past_bottom": past, "stair_spiral": sp,
                       "stair_in_exit_enclosure": enc}, _given(group), ctx)
        if (got == "pass" and low < 80) or (got == "fail" and (unbounded or low >= limit)) or got == "not_applicable":
            bad.append((where, enc, sp, h, past, got))
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", WHERE)
def test_width(ctx, rules, where):
    r, group, bad = rules["general.bc_1011_2_stair_width"], _group(where), []
    for enc, sp, sprinkler, w in itertools.product(TRI, TRI, SPRINKLERS, WIDTHS):
        strict = w >= 44 and sprinkler in ("nfpa_13", "nfpa_13r")
        least = 36
        if _any(group, "R-3") or _open(enc):
            least = 20                                              # exception 3: a chairlift
        if _may(sp) or _open(enc):
            least = 0                                               # 1011.10; a stepped aisle (Section 1030)
        got = _row(r, {"stair_clear_width": w, "stair_spiral": sp, "stair_in_exit_enclosure": enc},
                   _given(group, sprinkler), ctx)
        if (got == "pass" and not strict) or (got == "fail" and w >= least) or got == "not_applicable":
            bad.append((where, enc, sp, sprinkler, w, got))
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", WHERE)
def test_handrails(ctx, rules, where):
    r, group, bad = rules["general.bc_1011_11_stair_handrails"], _group(where), []
    for enc, sp, n, count in itertools.product(TRI, TRI, SIDES, RISER_COUNTS):
        excused = (n == 1 and _may(sp)) or _open(enc) or count is UNSTATED or count <= 2
        got = _row(r, {"stair_handrail_sides": n, "stair_handrail_each_side": n >= 2, "stair_spiral": sp,
                       "stair_riser_count": count, "stair_in_exit_enclosure": enc}, _given(group), ctx)
        if (got == "pass" and n < 2) or (got == "fail" and (n >= 2 or excused)) or got == "not_applicable":
            bad.append((where, enc, sp, n, count, got))
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


@pytest.mark.parametrize("rid", sorted(WALKED))
def test_a_flight_with_nothing_measured_never_passes_or_fails(ctx, rules, rid):
    for where in WHERE:
        assert _row(rules[rid], {}, _given(_group(where), "nfpa_13"), ctx) == "needs_review", (rid, where)


def test_the_two_flags_always_need_review_for_each_flight(ctx, rules):
    for rid in ("general.bc_1011_1_stairways_general", "general.bc_1011_6_stair_landings"):
        assert rules[rid]["kind"] == "flag" and rules[rid]["for_each"] == "stair"
        assert _row(rules[rid], {"stair_in_exit_enclosure": True}, _given("B", "nfpa_13"), ctx) == "needs_review"
