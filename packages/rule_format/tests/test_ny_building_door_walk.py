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
  31.75 in within a Type B unit (7); 20 in for a compartment (8, 9); 78 in high within a unit (4), 76 in for a
  unit's exterior door (5). A door may be in a unit unless it is marked an exit into an enclosure, passageway or
  horizontal exit, or it is on a corridor the building states is in no unit; within one (and a compartment's)
  also unless it is outside or marked an exit; a compartment's unless it is on a corridor.

So a door whose size rules pass is one the law can't fault on size, and one they fail is one no reading excuses."""

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
    return not exit_ is True and not exterior is True and not corridor is True


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


@pytest.mark.parametrize("group", GROUPS + ["mixed", U], ids=lambda g: "unstated" if g is U else g)
def test_no_door_size_passes_short_of_the_law_or_fails_within_it(rules, ctx, group):
    got = walked(rules)
    width, height = got["general.bc_1010_1_1_door_width"], got["general.bc_1010_1_1_door_height"]
    bad, seen = [], set()
    for within in TRI:
        given = _given(group, within)
        for sides in itertools.product(TRI, TRI, TRI, TRI):
            for leaves in (1, 2, U):
                for w in WIDTHS:
                    out = _row(width, _part(sides, leaves, w, U), given, ctx)
                    seen.add(out)
                    if why := _width_wrong(out, group, sides, leaves, w, within):
                        bad.append(("width", within, sides, leaves, w, out, why))
            for h in HEIGHTS:
                out = _row(height, _part(sides, U, U, h), given, ctx)
                if why := _height_wrong(out, sides, h, within):
                    bad.append(("height", within, sides, h, out, why))
    assert not bad, (len(bad), bad[:5])
    assert "needs_review" in seen and "fail" in seen
    assert "pass" in seen


def test_the_hard_condition_a_door_with_no_stated_clear_opening_never_passes(rules, ctx):
    """The sizes come only from the maker's stated clear opening (model_measurement/routes/doors.py): a door with
    none has neither, and every row then needs review, whatever else is known (never a pass, never a fail)."""
    got = walked(rules)
    best = (False, False, True, False)                       # on a corridor: no exception could loosen it
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
    assert _row(r, _part(door, 2, 31, U), _given("B", False), ctx) == "fail"   # a leaf is never wider than the opening
