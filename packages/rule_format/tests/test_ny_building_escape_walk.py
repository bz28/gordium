"""A property walk over New York's Building Code emergency escape and rescue openings, where required (section group 8a
of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md: BCNYS 1031.2, p.359 lines 57-58 and p.360 lines
3-23).

Every drafted rule over sleeping rooms is walked (found from their formulas), over every occupancy group (and two or
more, and not stated), each sleeping room fact yes, no and not measured, its escape openings 0, 1 or not measured, its
story's exits 1, 2 or not measured, and the sprinkler systems stated none, one, or not stated. The oracle is written
from the page here, never from the rule:

- **Strict** (a pass allowed only here): the room is on the fourth story above grade plane or higher, or the building
  is stated Group R-2 and the room's occupants are shown to have access to two or more exits (item 1 asks Group R-2
  only in stories with one exit or access to one exit, as Tables 1006.3.4(1) and (2) permit; a story's two exits
  don't show it: review round 1). A marked opening alone isn't a pass while its area well and bars aren't checked
  (1031.5, 1031.6, section group 8c: review round 2; its size, sill and door kind are its own rows since 8b).
- **Loosest** (a fail allowed only here): a building stated Group R-3 or R-4, or Group R-2 with the room's story at
  one exit; no opening marked; below the fourth story; no door of the room to outside (exception 2: an exit door to a
  public way, yard, court or exterior egress balcony); and in Group R-2 or R-3 no sprinkler system stated (exception 5:
  a sprinklered building's basement sleeping rooms, whether the room is in a basement not shown).
- **Not applicable** only where the building is stated one group other than R-2, R-3 and R-4."""

import itertools

import pytest

from rule_format import formula, parts
from rule_format.rulebook import REPO, Context, load

NY = REPO / "regulations/jurisdictions/new_york/new_york_state_building"
RULEBOOK = NY / "5_building_code_rules/drafted/general.yaml"
GROUPS = ["A-1", "A-2", "A-3", "A-4", "A-5", "B", "E", "F-1", "F-2", "H-1", "H-2", "H-3", "H-4", "H-5", "I-1", "I-2",
          "I-3", "I-4", "M", "R-1", "R-2", "R-3", "R-4", "S-1", "S-2", "U", "mixed"]
U = object()
TRI = (True, False, U)
SPRINKLERS = ("sprinklered_903_3_1_1", "sprinklered_903_3_1_2", "sprinklered_903_3_1_3")
RULE = "general.bc_1031_2_escape_opening_where_required"


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


def test_the_walk_finds_the_sleeping_room_rules(rules):
    got = {r["id"] for r in rules if r.get("for_each") == "sleeping_room" or _reads(r) & {
        "sleeping_room_escape_openings", "sleeping_room_fourth_or_higher", "sleeping_room_story_one_exit",
        "sleeping_room_door_to_outside"}}
    assert got == {RULE}


def _given(group, sprinkler):
    g = {} if group is U else {"occupancy_group": group}
    if sprinkler == "none":
        g |= {k: False for k in SPRINKLERS}
    elif sprinkler == "nfpa_13":
        g |= {k: k.endswith("_1_1") for k in SPRINKLERS}
    return g


def _part(openings, fourth, exits, door):
    m = {k: v for k, v in (("sleeping_room_escape_openings", openings), ("sleeping_room_fourth_or_higher", fourth),
                           ("sleeping_room_story_one_exit", exits), ("sleeping_room_door_to_outside", door))
         if v is not U}
    return {"id": "r", "name": "Bedroom", "measures": m}


def _wrong(out, group, openings, fourth, exits, door, sprinkler):
    if out == "not_applicable":
        ok = group is not U and group not in ("R-2", "R-3", "R-4", "mixed")
        return None if ok else "set aside where 1031.2 may ask it"
    if group is not U and group not in ("R-2", "R-3", "R-4", "mixed"):
        return "not set aside where 1031.2 asks nothing"
    if out == "pass":
        ok = fourth is True or (group == "R-2" and exits is False)
        return None if ok else "passes short of the strict reading"
    if out == "fail":
        required = group in ("R-3", "R-4") or (group == "R-2" and exits is True)
        exception_5 = group in ("R-2", "R-3") and sprinkler != "none"
        ok = required and openings == 0 and fourth is False and door is False and not exception_5
        return None if ok else "fails within the loosest reading"
    return None


@pytest.mark.parametrize("sprinkler", ["none", "nfpa_13", "unstated"])
def test_no_sleeping_room_passes_short_of_1031_2_or_fails_within_it(rules, ctx, sprinkler):
    rule = {r["id"]: r for r in rules}[RULE]
    bad, seen = [], set()
    for group in GROUPS + [U]:
        given = _given(group, sprinkler)
        for openings, fourth, exits, door in itertools.product((0, 1, U), TRI, TRI, TRI):
            out = parts.rows(rule, {"sleeping_room": [_part(openings, fourth, exits, door)]}, given,
                             ctx.allowed())[0]["outcome"]
            seen.add(out)
            if why := _wrong(out, group, openings, fourth, exits, door, sprinkler):
                bad.append(("unstated" if group is U else group, openings, fourth, exits, door, out, why))
    assert not bad, (len(bad), bad[:5])
    assert {"pass", "needs_review", "not_applicable"} <= seen
    assert "fail" in seen


def test_no_sleeping_room_read_never_passes(rules, ctx):
    """A dwelling's sleeping rooms may not be drawn: none read is a review wherever 1031.2 may ask, never a pass."""
    rule = {r["id"]: r for r in rules}[RULE]
    for group in ("R-2", "R-3", "R-4", "mixed", U):
        assert parts.rows(rule, {"sleeping_room": []}, _given(group, "none"), ctx.allowed())[0]["outcome"] \
            == "needs_review", group
        assert parts.rows(rule, {"sleeping_room": None}, _given(group, "none"), ctx.allowed())[0]["outcome"] \
            == "needs_review", group


def test_a_marked_opening_alone_needs_review_until_its_area_well_and_bars_are_checked(rules, ctx):
    """Review round 2 of group 8a: 1031.2 asks for an opening "in accordance with this section"; until 1031.5 and 1031.6
    (area wells, bars: section group 8c) are checked, a sleeping room that 1031.2 may ask passes on a marked opening
    never (its size, sill and door kind are the opening's own rows, section group 8b)."""
    rule = {r["id"]: r for r in rules}[RULE]
    for group in ("R-2", "R-3", "R-4", "mixed", U):
        out = parts.rows(rule, {"sleeping_room": [_part(1, False, True, False)]}, _given(group, "none"),
                         ctx.allowed())[0]["outcome"]
        assert out == "needs_review", group



# ---- section group 8b (2026-11-26): each escape opening's size, sill and door kind (1031.3.1 to 1031.3.3, 1031.4) -------
# Each rule's own limit, written from p.360 lines 29-37 (never from the rules): (measures, within the law, past it):
# within = a pass of the limit is allowed; past = the limit surely fails (a looser reading can't save it).
def _area_cases():
    for area in (U, 4.9, 5, 5.69, 5.7, 6):
        for at in TRI:
            m = {k: v for k, v in (("opening_net_clear_area", area), ("opening_at_grade", at)) if v is not U}
            ok = area is not U and (area >= 5.7 or (at is True and area >= 5))
            bad = area is not U and area < 5.7 and not (at is not False and area >= 5)
            yield m, ok, bad


def _one(name, limit, most):
    for v in (U, limit - 0.5, limit, limit + 0.5):
        m = {} if v is U else {name: v}
        ok = v is not U and (v <= limit if most else v >= limit)
        bad = v is not U and (v > limit if most else v < limit)
        yield m, ok, bad


def _door_cases():
    for door in TRI:
        for kind in TRI:
            m = {k: v for k, v in (("opening_is_door", door), ("opening_door_hinged_or_sliding", kind)) if v is not U}
            yield m, door is False or kind is True, door is True and kind is False


# every combination of the room's four facts for a rule with few cases; for one with many (the area well's ladder and
# steps), a set reaching every branch of the oracle: required (below the fourth story, one exit, no door to outside,
# no other opening), each fact turned once, each not known once, all not known
ROOM_FACTS = list(itertools.product(TRI, TRI, TRI, TRI))
REQUIRED = (False, True, False, False)
ROOM_FACTS_FEW = [REQUIRED, (U, U, U, U), (True, True, False, False), (False, False, False, False),
                  (False, True, True, False), (False, True, False, True), (U, True, False, False),
                  (False, U, False, False), (False, True, U, False), (False, True, False, U)]


SIZE_RULES = {
    "general.bc_1031_3_1_escape_opening_min_area": _area_cases,
    "general.bc_1031_3_2_escape_opening_min_height": lambda: _one("opening_net_clear_height", 24, False),
    "general.bc_1031_3_2_escape_opening_min_width": lambda: _one("opening_net_clear_width", 20, False),
    "general.bc_1031_3_3_escape_opening_max_sill_height": lambda: _one("opening_sill_height", 44, True),
    "general.bc_1031_4_escape_door_swinging_or_sliding": _door_cases,
}


# ---- section group 8c (2026-11-26): area wells, their ladders and steps (1031.5 to 1031.5.2.2, p.360 lines 38-53) --------
# Each case's within/past are written from the page: a well is asked of an opening whose bottom is below the adjacent
# grade; 9 sq ft, 36 in out and wide to its walls, nothing in them but the ladder or steps 1031.5.2 requires (a well
# over 44 in deep), and those no more than 6 in (1031.5.1's exception; review rounds 1 to 3); short, past;
# fully openable; a ladder or steps past 44 in deep; the ladder 12 in, 3 in, 18 in, full
# height; the steps 12 in, treads over 5 in, risers 18 in, full height (a ladder or steps is asked only past 44 in deep
# in the loosest reading).
def _well(**m):
    return {k: v for k, v in m.items() if v is not U}


# review rounds 2 and 3 of 8c: how far the ladder or steps, and anything else, reach into the required dimensions are
# their own facts (never read from area_well_ladder, which says no for an obstructed ladder too); only a required
# ladder or steps (a well over 44 in deep) may take up to 6 in
LADDER_IN = (U, 0, 6, 7)
OTHER_IN = (U, 0, 1)
DEPTHS = (U, 44, 45)


def _clear(other, ladder, depth):
    """Within the law: nothing else in the required dimensions, and the ladder none, or a required one 6 in at most."""
    return other is not U and other <= 0 and ladder is not U and (
        ladder <= 0 or (depth is not U and depth > 44 and ladder <= 6))


def _crowded(other, ladder, depth):
    """Past it whatever else is known: something else in them, a ladder past 6 in, or one in a shallow well."""
    return (other is not U and other > 0) or (ladder is not U and ladder > 6) or (
        ladder is not U and ladder > 0 and depth is not U and depth <= 44)


def _clear_cases():
    for other in OTHER_IN:
        for ladder in LADDER_IN:
            for depth in DEPTHS:
                yield _well(area_well_other_encroachment=other, area_well_ladder_encroachment=ladder,
                            area_well_depth=depth), _clear(other, ladder, depth), _crowded(other, ladder, depth)


def _required_cases():
    for below in TRI:
        for area in (U, 8, 9):
            for clear, within, crowded in _clear_cases():
                ok = below is False or (area is not U and area >= 9 and within)
                past = below is True and ((area is not U and area < 9) or crowded)
                yield {**_well(opening_below_grade=below, area_well_area=area), **clear}, ok, past


def _side_cases(name):
    def cases():
        for below in TRI:
            for v in (U, 35, 36):
                for clear, within, crowded in _clear_cases():
                    m = {**_well(opening_below_grade=below, **{name: v}), **clear}
                    ok = below is False or (v is not U and v >= 36 and within)
                    past = below is True and ((v is not U and v < 36) or crowded)
                    yield m, ok, past
    return cases


def _full_cases():
    for below in TRI:
        for full in TRI:
            yield _well(opening_below_grade=below, opening_fully_openable=full), below is False or full is True, \
                below is True and full is False


def _ladder_needed_cases():
    for below in TRI:
        for depth in (U, 44, 45):
            for ladder in TRI:
                m = _well(opening_below_grade=below, area_well_depth=depth, area_well_ladder=ladder)
                ok = below is False or (depth is not U and depth <= 44) or ladder is True
                yield m, ok, below is True and depth is not U and depth > 44 and ladder is False


GOOD_LADDER = {"area_well_ladder_width": 12, "area_well_ladder_projection": 3, "area_well_rung_spacing": 18,
               "area_well_ladder_full_height": True}
BAD_LADDER = {"area_well_ladder_width": 11, "area_well_ladder_projection": 2, "area_well_rung_spacing": 19,
              "area_well_ladder_full_height": False}
GOOD_STEPS = {"area_well_ladder_width": 12, "area_well_step_tread": 6, "area_well_step_riser": 18,
              "area_well_ladder_full_height": True}
BAD_STEPS = {"area_well_ladder_width": 11, "area_well_step_tread": 5, "area_well_step_riser": 19,
             "area_well_ladder_full_height": False}


def _one_off(good, bad):
    """The good set, and each measure in turn bad or not measured (the others good)."""
    yield dict(good), False
    for k in good:
        yield {**good, k: bad[k]}, True
        yield {x: v for x, v in good.items() if x != k}, None


def _ladder_cases():
    # below grade yes or not known (no, every other rule already walks: it passes), and the ladder-or-steps pairs that
    # reach each branch (a ladder; steps; neither; not known either way)
    for below in (True, U):
        for ladder, steps in ((True, False), (True, U), (True, True), (False, False), (U, False)):
            for depth in (U, 44, 50):
                for dims, short in _one_off(GOOD_LADDER, BAD_LADDER):
                    m = _well(opening_below_grade=below, area_well_ladder=ladder, area_well_steps=steps,
                              area_well_depth=depth, **dims)
                    ok = below is False or ladder is False or steps is True or short is False
                    past = below is True and ladder is True and steps is False and short is True and \
                        depth is not U and depth > 44
                    yield m, ok, past


def _steps_cases():
    for below in (True, U):
        for steps in TRI:
            for depth in (U, 44, 50):
                for dims, short in _one_off(GOOD_STEPS, BAD_STEPS):
                    m = _well(opening_below_grade=below, area_well_steps=steps, area_well_depth=depth, **dims)
                    ok = below is False or steps is False or short is False
                    past = below is True and steps is True and short is True and depth is not U and depth > 44
                    yield m, ok, past


SIZE_RULES.update({
    "general.bc_1031_5_area_well_required": _required_cases,
    "general.bc_1031_5_1_area_well_min_projection": _side_cases("area_well_projection"),
    "general.bc_1031_5_1_area_well_min_width": _side_cases("area_well_width"),
    "general.bc_1031_5_1_area_well_allows_full_opening": _full_cases,
    "general.bc_1031_5_2_area_well_ladder_over_44": _ladder_needed_cases,
    "general.bc_1031_5_2_1_area_well_ladder": _ladder_cases,
    "general.bc_1031_5_2_2_area_well_steps": _steps_cases,
})


def test_the_size_walk_finds_every_rule_over_escape_openings(rules):
    got = {r["id"] for r in rules if r.get("for_each") == "emergency_escape_opening"}
    assert got == set(SIZE_RULES)


@pytest.mark.parametrize("sprinkler", ["none", "nfpa_13", "unstated"])
@pytest.mark.parametrize("rid", sorted(SIZE_RULES))
def test_no_escape_opening_passes_short_of_its_limit_or_fails_where_1031_2_may_not_ask_it(rules, ctx, rid, sprinkler):
    rule = {r["id"]: r for r in rules}[rid]
    # the rule reads the group only in lists of R-2, R-3, R-4 and mixed, so one group outside them walks every such one
    import re
    # every quoted name in its formulas (review round 2: a single-letter group like "H" too)
    named = set(re.findall(r'"([^"]*)"', " ".join([rule["applies_when"], rule["check"]] + [w["when"] for w in rule["review_when"]])))
    assert named <= {"R-2", "R-3", "R-4", "mixed"}, named
    bad_rows, seen = [], set()
    for group in ("B", "I-1", "R-1", "R-2", "R-3", "R-4", "mixed", U):
        given = _given(group, sprinkler)
        cases = list(SIZE_RULES[rid]())
        for m, ok, past in cases:
            for fourth, one_exit, door, other in (ROOM_FACTS if len(cases) <= 20 else ROOM_FACTS_FEW):
                room = {k: v for k, v in (("opening_room_fourth_or_higher", fourth), ("opening_room_one_exit", one_exit),
                                          ("opening_room_door_to_outside", door),
                                          ("opening_room_has_other_openings", other)) if v is not U}
                got = parts.rows(rule, {"emergency_escape_opening": [{"id": "o", "within": "r", "measures": {**m, **room}}],
                                        "sleeping_room": [{"id": "r", "measures": {}}]}, given, ctx.allowed())
                out = got[0]["outcome"]
                seen.add(out)
                single_other = group is not U and group not in ("R-2", "R-3", "R-4", "mixed")
                if out == "not_applicable":
                    why = None if single_other else "set aside where 1031.2 may ask it"
                elif single_other:
                    why = "not set aside where 1031.2 asks nothing"
                elif out == "pass":
                    why = None if ok or fourth is True or (group == "R-2" and one_exit is False) else "passes short"
                elif out == "fail":
                    required = group in ("R-3", "R-4") or (group == "R-2" and one_exit is True)
                    exc5 = group in ("R-2", "R-3") and sprinkler != "none"
                    why = None if past and required and fourth is False and door is False and not exc5 and other is False \
                        else "fails within the loosest reading"
                else:
                    why = None
                if why:
                    bad_rows.append(("unstated" if group is U else group, sprinkler, m, fourth, one_exit, door, out, why))
    assert not bad_rows, (len(bad_rows), bad_rows[:4])
    assert {"pass", "needs_review", "not_applicable"} <= seen and ("fail" in seen or sprinkler == "nfpa_13")

