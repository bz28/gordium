"""A property walk over New York's Building Code door size (section group 6a of
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: 1010.1.1, pp.322-323).

Every drafted rule reading a door's clear width or height is walked (worked out from the formulas, never listed),
over every occupancy group (and a building of two or more, and one whose group isn't stated), each door fact yes, no
and not measured (marked an exit, one side outside, one side a corridor, one side a room under 10 sq ft), the
building's corridors-within-dwelling-units fact yes, no and not stated, the leaves 1, 2 and not stated, and a grid
of widths and heights around every printed limit, the size not measured among them. The oracle is written from the
law here, never from the rules:

- **Strict** (a pass is allowed only here): the size is measured (the maker's stated clear opening: the hard
  condition) and at least the most 1010.1.1 may ask of the door: 80 in high; 32 in wide from one leaf, so the door
  is stated to have one leaf (a pair's one leaf isn't shown), and 41 1/2 in where the building may be Group I-2
  (stated, two or more groups, or not stated: a door may move beds).
- **Loosest** (a fail is allowed only here): the size is measured and under the least any exception that may apply
  allows: no width at all for a door that may be in a dwelling or sleeping unit of Groups R-2, R-3, I-1 or R-4
  (exceptions 1 and 6) or to a storage closet under 10 sq ft (3); 28 in to a Group I-3 resident sleeping unit (2);
  31.75 in within a Type B unit (7); 20 in for a compartment (8, 9: any door but one into an exit enclosure,
  passageway or horizontal exit); 78 in high within a unit (4), 76 in for a
  unit's exterior door (5). A door may be in a unit unless it is marked an exit into an enclosure, passageway or
  horizontal exit, or it is on a corridor the building states is in no unit; within one also unless it is outside
  or marked an exit.

So a door whose size rules pass is one the law can't fault on size, and one they fail is one no reading excuses."""

import ast
import itertools

import pytest

from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U"]
U = object()                                     # not measured, or not stated
TRI = (True, False, U)
WIDTHS = (U, 10, 19.5, 20, 24, 27.5, 28, 30, 31.7, 31.75, 31.9, 32, 34, 41.4, 41.5, 48)
HEIGHTS = (U, 70, 75.9, 76, 77, 77.9, 78, 79, 79.9, 80, 84)
WIDTH, HEIGHT = "moe_door_clear_width", "moe_door_clear_height"
SIDES = ("moe_door_exit", "moe_door_exterior", "moe_door_to_corridor", "moe_door_to_room_under_10_sf")


def _may(v):
    return v is True or v is U


def _not(v):
    return v is False


def may_be_in_unit(exit_, exterior, corridor, within):
    """In a dwelling or sleeping unit (as its door, inside it or to its outside), unless ruled out."""
    interior_exit = exit_ is True and exterior is False
    on_public_corridor = corridor is True and within is False
    return not interior_exit and not on_public_corridor


def may_be_within_unit(exit_, exterior, corridor, within):
    """Inside a unit (exception 4, 7): also not outside, not an exit."""
    return may_be_in_unit(exit_, exterior, corridor, within) and not exterior is True and not exit_ is True


def may_be_compartment(exit_, exterior, corridor):
    """Exception 8 says nothing of what the door opens onto (a fitting room or sauna off a corridor, a cabana
    outside, its door then marked an exit: review rounds 1 and 2); only a door into an exit enclosure, passageway or
    horizontal exit serves no compartment."""
    return not (exit_ is True and exterior is False)


def width_strict(group):
    return 41.5 if group in ("I-2", "mixed", U) else 32


def width_loosest(group, exit_, exterior, corridor, small, within):
    least = 32
    in_unit = may_be_in_unit(exit_, exterior, corridor, within)
    if group in ("R-2", "R-3", "I-1", "R-4", "mixed", U) and in_unit:
        least = 0                                # exceptions 1 and 6: the width doesn't apply
    if _may(small):
        least = 0                                # exception 3: a storage closet under 10 sq ft
    if group in ("I-3", "mixed", U):
        least = min(least, 28)                   # exception 2
    if may_be_within_unit(exit_, exterior, corridor, within):
        least = min(least, 31.75)                # exception 7: within a Type B unit
    if may_be_compartment(exit_, exterior, corridor):
        least = min(least, 20)                   # exceptions 8 and 9
    return least


def height_loosest(exit_, exterior, corridor, within):
    least = 80
    if may_be_within_unit(exit_, exterior, corridor, within):
        least = 78                               # exception 4
    if _may(exterior):
        least = 76                               # exception 5: a unit's exterior door other than its required exit
    return least


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
    return {r["id"]: r for r in rules if _reads(r) & {WIDTH, HEIGHT}}


def _given(group, within):
    g = {}
    if group is not U:
        g.update(occupancy_group=group, occupancy_group_i4=group == "I-4", other_occupancy_present=group != "I-4")
    if within is not U:
        g["corridors_within_dwelling_units"] = within
    return g


def _part(sides, leaves, width, height):
    m = {k: v for k, v in zip(SIDES, sides) if v is not U}
    if leaves is not U:
        m["moe_door_leaves"] = leaves
    if width is not U:
        m[WIDTH] = width
    if height is not U:
        m[HEIGHT] = height
    return {"id": "p", "measures": m}


def _row(rule, part, given, ctx):
    return parts.rows(rule, {"means_of_egress_door": [part]}, given, ctx.allowed())[0]["outcome"]


def test_the_walk_finds_the_width_and_height_rules(rules):
    got = walked(rules)
    assert set(got) == {"general.bc_1010_1_1_door_width", "general.bc_1010_1_1_door_height"}
    for r in got.values():
        assert r["for_each"] == "means_of_egress_door" and "applies_when" not in r   # every door, every group


def _width_wrong(outcome, group, sides, leaves, width, within):
    exit_, exterior, corridor, small = sides
    if outcome == "pass" and (width is U or leaves != 1 or width < width_strict(group)):
        return "passes short of the strict reading"
    if outcome == "fail" and (width is U or width >= width_loosest(group, exit_, exterior, corridor, small, within)):
        return "fails within the loosest reading"
    if outcome == "not_applicable":
        return "set aside: 1010.1.1 asks it of every door"
    return None


def _height_wrong(outcome, sides, height, within):
    exit_, exterior, corridor, _ = sides
    if outcome == "pass" and (height is U or height < 80):
        return "passes short of 80 in"
    if outcome == "fail" and (height is U or height >= height_loosest(exit_, exterior, corridor, within)):
        return "fails within the loosest reading"
    if outcome == "not_applicable":
        return "set aside: 1010.1.1 asks it of every door"
    return None


ALL = GROUPS + ["mixed", U]
WIDTH_RULE, HEIGHT_RULE = "general.bc_1010_1_1_door_width", "general.bc_1010_1_1_door_height"


def group_classes(rule):
    """The groups the rule can't tell apart, each class with one to walk: a rule that reads the group only by
    membership in printed lists (`occupancy_group in [...]`, `== "X"`) answers alike for two groups in the same
    lists, so walking one walks both (the oracle is still asked of every group). A rule reading it any other way,
    or not at all, gets one class per group, or one class."""
    texts = [rule.get("applies_when"), rule.get("check")] + [w["when"] for w in rule.get("review_when") or []]
    lists = []
    for text in filter(None, texts):
        for node in ast.walk(ast.parse(text, mode="eval")):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "occupancy_group":
                for op, right in zip(node.ops, node.comparators):
                    if isinstance(op, (ast.In, ast.NotIn)) and isinstance(right, (ast.List, ast.Tuple)):
                        lists.append(frozenset(e.value for e in right.elts))
                    elif isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(right, ast.Constant):
                        lists.append(frozenset([right.value]))
                    else:
                        return {g: [g] for g in ALL}
    uses = sum(1 for text in filter(None, texts) for n in ast.walk(ast.parse(text, mode="eval"))
               if isinstance(n, ast.Name) and n.id == "occupancy_group")
    if uses != len(lists):                       # read somewhere other than a plain comparison: no collapsing
        return {g: [g] for g in ALL}
    out = {}
    for g in ALL:
        key = "unstated" if g is U else tuple(g in s for s in lists)
        out.setdefault(key, []).append(g)
    return {members[0]: members for members in out.values()}


def test_the_walks_collapse_keeps_the_groups_the_law_tells_apart(rules):
    """The width rule's classes must keep apart every group 1010.1.1 treats differently (Group I-2's beds; I-3's
    28 in; R-2, R-3, I-1 and R-4's units; a building of two or more groups; not stated)."""
    classes = group_classes(walked(rules)[WIDTH_RULE])
    where = {g: rep for rep, members in classes.items() for g in members}
    for a, b in (("I-2", "B"), ("I-3", "B"), ("R-2", "B"), ("R-2", "R-1"), ("I-1", "B"), ("mixed", "B"), (U, "B"),
                 ("I-2", "mixed"), ("I-3", "R-2")):
        assert where[a] is not where[b], (a, b)
    assert where["R-3"] == where["R-2"] == where["R-4"] == where["I-1"]
    assert set(where) == {g if g is not U else U for g in ALL}


@pytest.mark.parametrize("rep", [g for g in ALL], ids=lambda g: "unstated" if g is U else g)
def test_no_door_width_passes_short_of_the_law_or_fails_within_it(rules, ctx, rep):
    rule = walked(rules)[WIDTH_RULE]
    classes = group_classes(rule)
    if rep not in classes:
        pytest.skip("walked with its class's first group")
    bad, seen = [], set()
    for within in TRI:
        given = _given(rep, within)
        for sides in itertools.product(TRI, TRI, TRI, TRI):
            for leaves in (1, 2, U):
                for w in WIDTHS:
                    out = _row(rule, _part(sides, leaves, w, U), given, ctx)
                    seen.add(out)
                    for group in classes[rep]:
                        if why := _width_wrong(out, group, sides, leaves, w, within):
                            bad.append((group, within, sides, leaves, w, out, why))
    assert not bad, (len(bad), bad[:5])
    assert {"needs_review", "fail", "pass"} <= seen


def test_no_door_height_passes_short_of_the_law_or_fails_within_it(rules, ctx):
    rule = walked(rules)[HEIGHT_RULE]
    classes = group_classes(rule)
    bad, seen = [], set()
    for rep, members in classes.items():
        for within in TRI:
            given = _given(rep, within)
            for sides in itertools.product(TRI, TRI, TRI, TRI):
                for h in HEIGHTS:
                    out = _row(rule, _part(sides, U, U, h), given, ctx)
                    seen.add(out)
                    if why := _height_wrong(out, sides, h, within):
                        bad.append((members, within, sides, h, out, why))
    assert not bad, (len(bad), bad[:5])
    assert {"needs_review", "fail", "pass"} <= seen


def test_the_hard_condition_a_door_with_no_stated_clear_opening_never_passes(rules, ctx):
    """The sizes come only from the maker's stated clear opening (model_measurement/routes/doors.py): a door with
    none has neither, and every row then needs review, whatever else is known (never a pass, never a fail)."""
    got = walked(rules)
    best = (True, False, True, False)                        # into an exit from a corridor: no exception loosens it
    for rule in got.values():
        for group in ("B", "R-2", "I-2", "mixed", U):
            for within in TRI:
                out = _row(rule, _part(best, 1, U, U), _given(group, within), ctx)
                assert out == "needs_review", (rule["id"], group, within, out)


def test_a_pair_never_passes_on_its_openings_width(rules, ctx):
    r = walked(rules)["general.bc_1010_1_1_door_width"]
    door = (False, False, True, False)
    assert _row(r, _part(door, 2, 72, U), _given("B", False), ctx) == "needs_review"
    assert _row(r, _part(door, U, 72, U), _given("B", False), ctx) == "needs_review"
    assert _row(r, _part(door, 1, 72, U), _given("B", False), ctx) == "pass"
    assert _row(r, _part(door, 2, 19, U), _given("B", False), ctx) == "fail"   # a leaf is never wider than the opening


# ---- section group 6b (2026-11-25): the direction of swing, 1010.1.2.1 (p.323) --------------------------------------
# Strict (a pass allowed only here): the door isn't swinging (1010.1.2.1 asks only swinging doors), or it swings with
# egress travel, or it serves under 50 at the most it can serve and the building is one stated group other than H.
# Loosest (a fail allowed only here): it is swinging, swings against egress travel, and serves 50 or more at the
# least it can serve, or the building is stated Group H.
SWING_RULE = "general.bc_1010_1_2_1_direction_of_swing"
H_GROUPS = ("H-1", "H-2", "H-3", "H-4", "H-5")
LOADS = (U, 0, 49.99, 50, 120, (0, 49.99), (0, 50), (0, 500), (50, 500))


def _swing_part(swinging, swings, load, exterior=False, exit_=False):
    m = {k: v for k, v in (("moe_door_swinging", swinging), ("moe_door_swings_with_egress", swings),
                           ("moe_door_exterior", exterior), ("moe_door_exit", exit_)) if v is not U}
    part = {"id": "p", "measures": m}
    if isinstance(load, tuple):
        part["readings"] = {"moe_door_occupant_load": [{"value": v, "named": {"door_occupants_served": n}}
                                                        for v, n in zip(load, ("none", "whole_building"))]}
    elif load is not U:
        m["moe_door_occupant_load"] = load
    return part


def _swing_wrong(out, group, swinging, swings, load, exterior=False, exit_=False, outdoor=False):
    low = high = None
    if isinstance(load, tuple):
        low, high = load
    elif load is not U:
        low = high = load
    patio = exterior is not False and exit_ is not True and outdoor is not False
    if out == "pass":
        # round 2: a door to outside that isn't an exit may be an occupied outdoor area's way in (1004.7)
        patio = exterior is not False and exit_ is not True and outdoor is not False
        ok = swinging is False or (swings is True and not patio) or (
            high is not None and high < 50 and group is not U and group != "mixed" and group not in H_GROUPS)
        return None if ok else "passes short of the strict reading"
    if out == "fail":
        ok = swinging is True and swings is False and not patio and (
            (low is not None and low >= 50) or group in H_GROUPS)
        return None if ok else "fails within the loosest reading"
    if out == "not_applicable":
        return "set aside: it applies to every door"
    return None


def test_no_door_swing_passes_short_of_the_law_or_fails_within_it(rules, ctx):
    rule = {r["id"]: r for r in rules}[SWING_RULE]
    classes = group_classes(rule)
    assert len(classes) >= 3                                 # H, mixed or unstated, the rest kept apart
    bad, seen = [], set()
    for rep, members in classes.items():
        for outdoor in TRI:
            given = _given(rep, U) | ({} if outdoor is U else {"occupied_outdoor_areas": outdoor})
            for swinging, swings, exterior, exit_ in itertools.product(TRI, TRI, TRI, TRI):
                for load in LOADS:
                    part = _swing_part(swinging, swings, load, exterior, exit_)
                    out = parts.rows(rule, {"means_of_egress_door": [part]}, given, ctx.allowed())[0]["outcome"]
                    seen.add(out)
                    for g in members:
                        if why := _swing_wrong(out, g, swinging, swings, load, exterior, exit_, outdoor):
                            bad.append((g, outdoor, swinging, swings, exterior, exit_, load, out, why))
    assert not bad, (len(bad), bad[:5])
    assert {"pass", "fail", "needs_review"} <= seen
