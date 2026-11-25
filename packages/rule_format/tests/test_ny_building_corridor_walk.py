"""A property walk over New York's Building Code corridor width (section group 4 of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: 1020.3 and Table 1020.3, p.344; 1005.3.2, p.314).

Every drafted corridor rule reading a corridor's width is walked (worked out from the formulas, never listed), over
every occupancy group (and a building of two or more, and one whose group isn't stated), the ambulatory care facility
fact yes, no and not stated, and a grid of widths and occupant loads around every printed limit. The oracle is
written from the law here, never from the rules: a corridor passes only where it is at least the strictest width
Table 1020.3 may ask of it (96 in in Group I-2, where beds may move; 72 in in Group E at 100 occupants or more, and in
Group B where an ambulatory care facility is stated or not ruled out; else 36 in under 50 occupants, 44 in at 50 or
more) and at least 0.2 in per occupant (1005.3.2's factor, the one that may apply in every group), and only in a
building of one stated group. A fail is only ever under that strictest width. With the occupant load given as two
readings, none and the whole story's (design_checker/occupant_load.py), a pass holds at the whole story's load."""

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
LOADS = (0, 10, 49, 49.5, 50, 99, 99.5, 100, 150, 220, 300, 360, 480, 600, 1000)
AMBULATORY = (True, False, UNSTATED)


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


def may_pass(group, ambulatory, width, load_):
    if group in ("mixed", UNSTATED):
        return False                # 1004.4: each portion by its own occupancy, a person's check
    return width >= strictest(group, ambulatory, load_) and width >= 0.2 * load_


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
    return [r for r in rules if r["kind"] == "rule" and "corridor_width" in _reads(r)]


def _given(group, ambulatory):
    g = {}
    if group is not UNSTATED:
        g.update(occupancy_group=group, occupancy_group_i4=group == "I-4",
                 other_occupancy_present=group not in ("I-4",))
    if ambulatory is not UNSTATED:
        g["ambulatory_care_facility"] = ambulatory
    return g


def _row(r, part, given, ctx):
    return parts.rows(r, {"corridor": [{"id": "p", **part}]}, given, ctx.allowed())[0]["outcome"]


def test_the_walk_finds_the_corridor_width_rule(rules):
    assert [r["id"] for r in walked(rules)] == ["general.bc_table_1020_3_corridor_width"]


@pytest.mark.parametrize("where", GROUPS + ["mixed", "unstated"])
def test_no_corridor_passes_short_of_the_strictest_width_or_its_capacity(ctx, rules, where):
    group = UNSTATED if where == "unstated" else where
    bad = []
    for r in walked(rules):
        reads = _reads(r)
        for amb, w, n in itertools.product(AMBULATORY, WIDTHS, LOADS):
            if "ambulatory_care_facility" not in reads and amb is not UNSTATED:
                continue
            got = _row(r, {"measures": {"corridor_width": w, "corridor_occupant_load": n}}, _given(group, amb), ctx)
            if got == "pass" and not may_pass(group, amb, w, n):
                bad.append((r["id"], where, amb, w, n))
            if got == "fail" and w >= strictest(group, amb, n):
                bad.append((r["id"], where, amb, w, n, "fails at or past the strictest width"))
    assert not bad, f"{len(bad)} wrong answers, e.g. {bad[:5]}"


@pytest.mark.parametrize("where", ["B", "E", "I-2", "R-2"])
def test_given_as_none_and_the_whole_story_a_pass_holds_at_the_whole_story(ctx, rules, where):
    """The corridor's load as design_checker/occupant_load.py gives it: two readings, none and its story's. A pass
    must hold at the story's load (the most it can serve); a fail must hold at none."""
    for r in walked(rules):
        for amb, w, n in itertools.product((True, False), WIDTHS, LOADS):
            part = {"measures": {"corridor_width": w}, "not_measured": {"corridor_occupant_load": "two readings"},
                    "readings": {"corridor_occupant_load": [
                        {"value": 0, "named": {"corridor_occupants_served": "none"}},
                        {"value": n, "named": {"corridor_occupants_served": "whole_story"}}]}}
            got = _row(r, part, _given(where, amb), ctx)
            if got == "pass":
                assert may_pass(where, amb, w, n), (where, amb, w, n)
            if got == "fail":
                assert w < strictest(where, amb, 0) and w < strictest(where, amb, n), (where, amb, w, n)


def test_a_corridor_whose_load_is_not_given_never_passes(ctx, rules):
    """Where another level's occupants may reach the corridor, its load is not given (occupant_load.py): never a
    pass, whatever the width."""
    for r in walked(rules):
        for w in WIDTHS:
            got = _row(r, {"measures": {"corridor_width": w},
                           "not_measured": {"corridor_occupant_load": "not ruled out"}},
                       _given("R-2", False), ctx)
            assert got != "pass", w
