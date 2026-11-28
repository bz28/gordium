"""A property walk over New York's Building Code corridor width (section group 4 of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: 1020.3 and Table 1020.3, p.344; 1005.3.2, p.314).

Every drafted corridor rule and flag reading a corridor's width is walked (worked out from the formulas, never
listed), over every occupancy group (and a building of two or more, and one whose group isn't stated), the ambulatory
care facility fact yes, no and not stated, and a grid of widths and occupant loads around every printed limit. The
oracle is written from the law here, never from the rules:
- Table 1020.3's rule passes only where the corridor is at least the strictest width the table may ask of it (96 in
  in Group I-2, where beds may move; 72 in in Group E at 100 occupants or more, and in Group B where an ambulatory
  care facility is stated or not ruled out; else 36 in under 50 occupants, 44 in at 50 or more), and only in a
  building of one stated group; it fails only under that strictest width.
- 1020.3's capacity (1005.3.2, a rule since section group 5a) passes only where the corridor is at least 0.2 in
  per occupant here (the walk states no sprinkler or voice/alarm system, so exception 1's 0.15 never applies), and
  fails only short of 0.15 in (exception 1's, the least a stated building may take) with fixed seating ruled out.
So a corridor whose every line complies is one the law can't fault on width or capacity. With the
occupant load given as two readings, none and the whole story's (design_checker/occupant_load.py), the same holds at
the whole story's load."""

import itertools

import pytest

from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"]
UNSTATED = object()
# around every printed width (Table 1020.3: 24, 36, 44, 72, 96) and the capacity's 0.2 in per occupant
WIDTHS = (20, 23.5, 24, 30, 35.5, 36, 40, 43.5, 44, 50, 60, 71.5, 72, 80, 95.5, 96, 120, 200)
LOADS = (0, 10, 49, 49.5, 50, 99, 99.5, 100, 150, 220, 221, 300, 360, 480, 600, 1000)
AMBULATORY = (True, False, UNSTATED)
TABLE, CAPACITY = "general.bc_table_1020_3_corridor_width", "general.bc_1020_3_corridor_capacity"


def _may(v):
    return v is True or v is UNSTATED


def strictest(group, ambulatory, load_):
    """The widest Table 1020.3 may ask of the corridor (p.344, lines 27-33), from the table alone."""
    if group == "I-2":
        return 96                   # Group I-2 in areas where required for bed movement
    if group == "E" and load_ >= 100:
        return 72                   # In Group E with a corridor having an occupant load of 100 or more
    if group == "B" and _may(ambulatory):
        return 72                   # stretcher traffic in ambulatory care facilities (Group B, 304.1)
    return 36 if load_ < 50 else 44


def table_may_pass(group, ambulatory, width, load_):
    if group in ("mixed", UNSTATED):
        return False                # 1004.4: each portion by its own occupancy, a person's check
    return width >= strictest(group, ambulatory, load_)


def capacity_met(width, load_):
    return width >= 0.2 * load_     # 1005.3.2: the most it asks in any group


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(NY)


@pytest.fixture(scope="module")
def rules():
    return load(RULEBOOK)["rules"]


def _reads(r):
    out = set()
    for t in [r.get("applies_when"), r.get("check")] + [w["when"] for w in r.get("review_when") or []]:
        if t:
            out |= formula.names(t)
    return out


def walked(rules):
    return {r["id"]: r for r in rules if "corridor_width" in _reads(r)}


def _given(group, ambulatory, dwelling=UNSTATED):
    g = {}
    if group is not UNSTATED:
        g.update(occupancy_group=group, occupancy_group_i4=group == "I-4",
                 other_occupancy_present=group not in ("I-4",))
    if ambulatory is not UNSTATED:
        g["ambulatory_care_facility"] = ambulatory
    if dwelling is not UNSTATED:
        g["corridors_within_dwelling_units"] = dwelling     # section group 4b: Table 1020.3's 36 in within a unit
    return g


def _row(r, part, given, ctx):
    return parts.rows(r, {"corridor": [{"id": "p", **part}]}, given, ctx.allowed())[0]["outcome"]


def _wrong(table, capacity, group, amb, w, n_pass, n_fail):
    """What the law says is wrong with a corridor's two answers: `n_pass` the load a pass must hold at, `n_fail` the
    load a fail must hold at (the same where the load is one number)."""
    bad = []
    if table == "pass" and not table_may_pass(group, amb, w, n_pass):
        bad.append("table passes short of the strictest width")
    if table == "fail" and w >= strictest(group, amb, n_fail):
        bad.append("table fails at or past the strictest width")
    if capacity == "pass" and not capacity_met(w, n_pass):
        bad.append("capacity passes short of 0.2 in per occupant")
    if capacity == "fail" and w >= 0.15 * n_fail:
        bad.append("capacity fails at or past 0.15 in per occupant")
    if capacity == "not_applicable":
        bad.append("capacity set aside: it applies to every corridor")
    return bad


def test_the_walk_finds_the_corridor_width_rule_and_capacity_flag(rules):
    got = walked(rules)
    assert set(got) == {TABLE, CAPACITY}
    assert got[TABLE]["kind"] == "rule" and got[CAPACITY]["kind"] == "rule"      # a rule since section group 5a


@pytest.mark.parametrize("where", GROUPS + ["mixed", "unstated"])
def test_no_corridor_complies_short_of_the_strictest_width_or_its_capacity(ctx, rules, where):
    group = UNSTATED if where == "unstated" else where
    r = walked(rules)
    bad = []
    for amb, dwell, w, n in itertools.product(AMBULATORY, (True, False, UNSTATED), WIDTHS, LOADS):
        m = {"measures": {"corridor_width": w, "corridor_occupant_load": n}}
        given = _given(group, amb, dwell)
        found = _wrong(_row(r[TABLE], m, given, ctx), _row(r[CAPACITY], m, given, ctx), group, amb, w, n, n)
        bad += [(where, amb, w, n, f) for f in found]
    assert not bad, f"{len(bad)} wrong answers, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", ["B", "E", "I-2", "R-2", "A-3"])
def test_given_as_none_and_the_whole_story_a_corridor_complies_only_at_the_whole_story(ctx, rules, where):
    """The corridor's load as design_checker/occupant_load.py gives it: two readings, none and its story's. A pass
    (or a capacity set aside) must hold at the story's load, the most it can serve; a fail must hold at none."""
    r = walked(rules)
    bad = []
    for amb, w, n in itertools.product((True, False), WIDTHS, LOADS):
        m = {"measures": {"corridor_width": w}, "not_measured": {"corridor_occupant_load": "two readings"},
             "readings": {"corridor_occupant_load": [
                 {"value": 0, "named": {"corridor_occupants_served": "none"}},
                 {"value": n, "named": {"corridor_occupants_served": "whole_story"}}]}}
        given = _given(where, amb)
        found = _wrong(_row(r[TABLE], m, given, ctx), _row(r[CAPACITY], m, given, ctx), where, amb, w, n, 0)
        bad += [(where, amb, w, n, f) for f in found]
    assert not bad, f"{len(bad)} wrong answers, e.g. {bad[:5]}"


def test_a_corridor_whose_load_is_not_given_never_passes(ctx, rules):
    """Where another level's occupants may reach the corridor, its load is not given (occupant_load.py): the table's
    rule never passes and neither does the capacity rule, whatever the width."""
    r = walked(rules)
    for w in WIDTHS:
        m = {"measures": {"corridor_width": w}, "not_measured": {"corridor_occupant_load": "not ruled out"}}
        given = _given("R-2", False)
        assert _row(r[TABLE], m, given, ctx) != "pass", w
        assert _row(r[CAPACITY], m, given, ctx) != "pass", w


def test_the_plan_states_the_walks_own_grid():
    """Review round 1 of group 4a (P3): the plan's status line says how big this walk is; it must be this file's own
    grid, so a width or load added here can't leave it stale."""
    plan = (REPO / "docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md").read_text(encoding="utf-8")
    assert f"{len(WIDTHS)} widths by {len(LOADS)} loads" in plan


# ---- section group 4b: Table 1020.2, the corridor's fire-resistance rating (p.344, lines 7-18; 1020.2, p.343) -------

A_U = ("A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "M", "S-1", "S-2", "U")
SYSTEMS = {"nfpa_13": (True, False, False), "nfpa_13r": (False, True, False), "nfpa_13d": (False, False, True),
           "none": (False, False, False), UNSTATED: None}
RATINGS = (0, 0.25, 0.5, 0.75, 1, 2)
RATING_LOADS = (0, 10, 10.5, 11, 30, 30.5, 31, 100)


def required(group, system, load_):
    """The rating Table 1020.2 asks, read strictly from the table alone: None for Not Permitted. Note c's
    "903.3.1.1 or 903.3.1.2 where allowed" read as NFPA 13 only outside Group R (13R only where allowed, which isn't
    checked), a cell naming no system as NFPA 13 only, note d's 903.3.1.3 for Groups R-3 and R-4 only."""
    s13, s13r, s13d = system == "nfpa_13", system == "nfpa_13r", system == "nfpa_13d"
    if group in ("H-1", "H-2", "H-3"):
        return 1 if s13 else None
    if group in ("H-4", "H-5"):
        return 0 if load_ <= 30 else 1 if s13 else None
    if group in A_U:
        return 0 if load_ <= 30 or s13 else 1
    if group in ("R-1", "R-2", "R-3", "R-4"):
        if load_ <= 10:
            return 0
        if s13 or s13r:
            return 0.5                                  # note c: 13R is allowed for Group R (903.3.1.2's own group)
        # note d: 903.3.1.3 in Group R-3, and in Group R-4 only in Condition 1 (903.2.8.2, p.271), not stated: the
        # strict reading has no R-4 cell for 13D (review round 1 of group 4b)
        return 1 if group == "R-3" and s13d else None
    if group == "I-2":
        return 0 if s13 else None
    if group in ("I-1", "I-3"):
        return 1 if s13 else None
    if group == "I-4":
        return 0 if s13 else 1
    raise AssertionError(group)


def loosest(group, system, load_, dwelling):
    """The least rating any reading of the table, its notes and 1020.2's exceptions may ask, for a fail to hold
    (None: Not Permitted under every reading): 13R or 13D where a cell may allow it, exceptions 1, 3 and 4 (Groups E,
    S-2, B), exception 2 (a corridor within a dwelling or sleeping unit in Groups I-1 and R, while stated or not ruled
    out) and note b (408.8, Group I-3) lift the rating to none."""
    s13, s13r, s13d = system == "nfpa_13", system == "nfpa_13r", system == "nfpa_13d"
    if group in ("B", "E", "S-2") or (group in ("I-1", "R-1", "R-2", "R-3", "R-4") and _may(dwelling)):
        return 0
    if group in ("H-1", "H-2", "H-3"):
        return 1 if s13 or s13r else None
    if group in ("H-4", "H-5"):
        return 0 if load_ <= 30 else 1 if s13 or s13r else None
    if group in A_U:
        return 0 if load_ <= 30 or s13 or s13r or s13d else 1
    if group in ("R-1", "R-2", "R-3", "R-4"):
        return 1 if group == "R-4" and s13d and load_ > 10 else required(group, system, load_)   # Condition 1
    if group == "I-2":
        return 0 if s13 or s13r or s13d else None
    if group == "I-3":
        return 0 if s13 or s13r else None
    if group == "I-1":
        return 1 if s13 or s13r else None
    if group == "I-4":
        return 0 if s13 or s13r or s13d else 1
    raise AssertionError(group)


def rating_rules(rules):
    """Table 1020.2's row rules: every rule reading a corridor's rating, and the rows named for the table (Group I-2's
    asks no rating, only a sprinkler system)."""
    return [r for r in rules if r["kind"] == "rule" and ("corridor_fire_rating_hours" in _reads(r)
                                                         or r["id"].startswith("general.bc_table_1020_2_"))]


def _rating_given(group, system, dwelling):
    g = _given(group, UNSTATED, dwelling)
    if SYSTEMS[system] is not None:
        g.update(zip(("sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "sprinklered_903_3_1_3"), SYSTEMS[system]))
    return g


def test_the_rating_walk_finds_one_rule_per_printed_row_of_table_1020_2(rules):
    assert sorted(r["id"] for r in rating_rules(rules)) == sorted(
        f"general.bc_table_1020_2_{k}" for k in ("h1_h2_h3", "h4_h5", "a_b_e_f_m_s_u", "r", "i2", "i1_i3", "i4"))


@pytest.mark.parametrize("where", GROUPS + ["mixed", "unstated"])
def test_no_corridor_rating_passes_short_of_the_table_or_fails_within_an_exception(ctx, rules, where):
    """Every row's rule, every sprinkler system (and none stated), the dwelling-unit fact three ways, ratings and loads
    around each printed limit: a pass only where the strict reading's rating is met in a building of one stated group
    and stated system; a fail only where even the loosest reading isn't met."""
    group = UNSTATED if where == "unstated" else where
    bad = []
    for r in rating_rules(rules):
        for system, dwell, n, h in itertools.product(SYSTEMS, (True, False, UNSTATED), RATING_LOADS, RATINGS):
            m = {"measures": {"corridor_fire_rating_hours": h, "corridor_occupant_load": n}}
            got = _row(r, m, _rating_given(group, system, dwell), ctx)
            one = group not in ("mixed", UNSTATED)
            # a system not stated: a pass must hold under every system, a fail under every one
            each = [k for k in SYSTEMS if k is not UNSTATED] if system is UNSTATED else [system]
            if got == "pass":
                needs = [required(group, k, n) for k in each] if one else [None]
                if None in needs or h < max(needs):
                    bad.append((r["id"], where, system, dwell, n, h, "passes short of the table"))
            if got == "fail":
                leasts = [loosest(group, k, n, dwell) for k in each] if one else [0]
                least = None if all(x is None for x in leasts) else min(x for x in leasts if x is not None)
                if least is not None and h >= least:
                    bad.append((r["id"], where, system, dwell, n, h, "fails within a reading that allows it"))
    assert not bad, f"{len(bad)} wrong answers, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", ["B", "R-2", "H-4", "I-4"])
def test_a_rating_with_the_load_as_none_and_the_whole_story_holds_at_the_whole_story(ctx, rules, where):
    """The corridor's load as occupant_load.py gives it: a pass must hold at the story's load, a fail at none."""
    bad = []
    for r in rating_rules(rules):
        for system, n, h in itertools.product(("nfpa_13", "nfpa_13r", "none"), RATING_LOADS, RATINGS):
            m = {"measures": {"corridor_fire_rating_hours": h}, "not_measured": {"corridor_occupant_load": "two"},
                 "readings": {"corridor_occupant_load": [
                     {"value": 0, "named": {"corridor_occupants_served": "none"}},
                     {"value": n, "named": {"corridor_occupants_served": "whole_story"}}]}}
            got = _row(r, m, _rating_given(where, system, False), ctx)
            need = required(where, system, n)
            if got == "pass" and (need is None or h < need):
                bad.append((r["id"], system, n, h, "pass"))
            least = loosest(where, system, 0, False)
            if got == "fail" and least is not None and h >= least:
                bad.append((r["id"], system, n, h, "fail"))
    assert not bad, bad[:5]


def test_a_rating_not_stated_passes_only_where_the_table_asks_none(ctx, rules):
    """No host states a corridor's rating yet: a row passes only where it asks none (30 or fewer occupants, or NFPA
    13, in Group M), and never where it asks a rating."""
    r = next(x for x in rating_rules(rules) if x["id"].endswith("a_b_e_f_m_s_u"))
    unstated = {"measures": {"corridor_occupant_load": 31}, "not_measured": {"corridor_fire_rating_hours": "stated"}}
    assert _row(r, unstated, _rating_given("M", "none", False), ctx) == "needs_review"
    assert _row(r, unstated, _rating_given("M", "nfpa_13", False), ctx) == "pass"
    small = {"measures": {"corridor_occupant_load": 30}, "not_measured": {"corridor_fire_rating_hours": "stated"}}
    # Chapter 4 part a: passing on the corridor's load alone, only where the building rules out a mall (402.8.2.1)
    no_mall = {"special_egress_spaces": False}
    assert _row(r, small, _rating_given("M", "none", False) | no_mall, ctx) == "pass"
    assert _row(r, small, _rating_given("M", "none", False), ctx) == "needs_review"



# ---- section group 5a: 1005.3.2's factors on a corridor (p.314 lines 14-22; 1020.3, p.344) -------------------------

LESS = ("A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "I-1", "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4",
        "S-1", "S-2", "U")                                    # exception 1: "other than Group H and I-2"
CAP_WIDTHS = (36, 43.5, 44, 44.2, 58, 60, 80)
CAP_LOADS = (0, 220, 221, 290, 294, 300, 400)


def factors(group, s13, s13r, voice, seating):
    """(the factor a pass must meet, the factor a fail must miss), from 1005.3.2 alone: 0.2 in per occupant; 0.15 in
    exception 1's buildings (a 903.3.1.1 or 903.3.1.2 system and a 907.5.2.2 voice/alarm system, other than Groups H
    and I-2); smoke-protected or open-air seating's own (lower) factors where fixed seating may be there. An unstated
    fact may be either way."""
    def may(v):
        return v is True or v is UNSTATED
    # 903.3.1.2 (13R) counts only where it's allowed, in Group R (review round 1 of group 5a); a building of two or
    # more groups may be all portions other than H and I-2 (1004.4)
    sure_less = group in LESS and (s13 is True or (s13r is True and group in ("R-1", "R-2", "R-3", "R-4")))         and voice is True
    may_less = (group in LESS or group in (UNSTATED, "mixed")) and (may(s13) or may(s13r)) and may(voice)
    return (0.15 if sure_less else 0.2), (0 if may(seating) else 0.15 if may_less else 0.2)


@pytest.mark.parametrize("where", ["B", "E", "H-2", "I-2", "R-2", "A-3", "mixed", "unstated"])
def test_the_corridor_capacity_passes_only_at_the_factor_and_fails_only_past_the_least(ctx, rules, where):
    group = UNSTATED if where == "unstated" else where
    r = walked(rules)[CAPACITY]
    bad = []
    ways = (True, False, UNSTATED)
    for s13, s13r, voice, seating in itertools.product(ways, ways, ways, ways):
        given = _given(group, UNSTATED)
        for k, v in (("sprinklered_903_3_1_1", s13), ("sprinklered_903_3_1_2", s13r),
                     ("emergency_voice_alarm_system", voice), ("assembly_fixed_seating", seating)):
            if v is not UNSTATED:
                given[k] = v
        need, least = factors(group, s13, s13r, voice, seating)
        for w, n in itertools.product(CAP_WIDTHS, CAP_LOADS):
            got = _row(r, {"measures": {"corridor_width": w, "corridor_occupant_load": n}}, given, ctx)
            if got == "pass" and w < need * n - 1e-9:
                bad.append((where, s13, s13r, voice, seating, w, n, "pass"))
            if got == "fail" and w >= least * n - 1e-9:
                bad.append((where, s13, s13r, voice, seating, w, n, "fail"))
    assert not bad, f"{len(bad)} wrong answers, e.g. {bad[:5]}"
