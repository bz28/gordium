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
  don't show it: review round 1). A marked opening alone isn't a pass until its size and sill are checked (1031.3 to
  1031.6, section group 8b: review round 2).
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


def test_a_marked_opening_alone_needs_review_until_its_size_is_checked(rules, ctx):
    """Review round 2 of group 8a: 1031.2 asks for an opening "in accordance with this section"; until 1031.3 to 1031.6
    (size, sill, area wells) are checked, a sleeping room that 1031.2 may ask passes on a marked opening never."""
    rule = {r["id"]: r for r in rules}[RULE]
    for group in ("R-2", "R-3", "R-4", "mixed", U):
        out = parts.rows(rule, {"sleeping_room": [_part(1, False, True, False)]}, _given(group, "none"),
                         ctx.allowed())[0]["outcome"]
        assert out == "needs_review", group

