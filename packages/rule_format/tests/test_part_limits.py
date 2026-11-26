"""A per-part rule's `limit` (section group 8d of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): the
part's own requirement, which code holds to each part to tell which comply (design_checker/escape_openings.py counts a
sleeping room's compliant escape openings for BCNYS 1031.2). It must never drift from the rule's check: the check is
exactly "(<limit>) or <set-aside>", and each review band reading the limit's measures says "not (<limit>)"; a rule
that edits one side only is refused (rule_format/parts.py limit_problems)."""

import copy

from rule_format.parts import limit_problems, rule_problems
from rule_format.rulebook import REPO, load

RULEBOOK = REPO / "regulations/jurisdictions/new_york/new_york_state_building/5_building_code_rules/drafted/general.yaml"


def _escape_rules():
    return [r for r in load(RULEBOOK)["rules"] if r.get("for_each") == "emergency_escape_opening"]


def test_every_escape_opening_rule_has_a_limit_in_its_one_shape():
    rules = _escape_rules()
    assert len(rules) == 12
    for r in rules:
        assert isinstance(r.get("limit"), str) and r["limit"], r["id"]
        assert limit_problems(r) == [] and rule_problems(r) == [], r["id"]


def test_editing_one_side_only_is_refused():
    """The coordinator's condition 1 (2026-11-26): a check or a band that drifts from its limit could pass what the
    limit fails, so each one-sided edit is a problem."""
    r = next(x for x in _escape_rules() if x["id"] == "general.bc_1031_3_1_escape_opening_min_area")
    looser = copy.deepcopy(r)
    looser["check"] = looser["check"].replace(">= 5.7", ">= 5.6", 1)            # the check alone
    assert limit_problems(looser)
    stricter = copy.deepcopy(r)
    stricter["limit"] = stricter["limit"].replace(">= 5.7", ">= 6", 1)           # the limit alone
    assert limit_problems(stricter)
    band = copy.deepcopy(r)
    band["review_when"][0]["when"] = band["review_when"][0]["when"].replace(">= 5.7", ">= 5.6", 1)   # a band alone
    assert limit_problems(band)
    building = copy.deepcopy(r)                                                    # a limit reading a building value
    building["limit"] = building["limit"] + " or sprinklered_903_3_1_1"
    building["check"] = f"({building['limit']}) or " + r["check"].split(") or ", 1)[1]
    assert limit_problems(building)
    leaky = copy.deepcopy(r)                                                       # the set-aside reading the limit's own
    leaky["check"] = r["check"] + " or opening_net_clear_area >= 1"
    assert limit_problems(leaky)
    assert limit_problems({**r, "limit": ""}) and limit_problems({**r, "limit": "opening_net_clear_area >="})


def test_shapes_that_let_a_rule_need_review_where_its_limit_holds_are_refused():
    """Review round 1 of 8d: the shape is checked on the parsed formulas, never by text: (a) an if-else after the
    limit, (b) "not (not (L))", (c) a band "not (L) or ...", (d) a band not gated by "not (L)", (e) a limit reading a fact
    the rule reads elsewhere (a room's, copied onto the part) are each refused."""
    r = next(x for x in _escape_rules() if x["id"] == "general.bc_1031_3_2_escape_opening_min_height")
    L, rest = r["limit"], r["check"].split(") or ", 1)[1]
    cases = {
        "a": {"check": f"({L}) or opening_room_fourth_or_higher if opening_room_door_to_outside else opening_room_one_exit"},
        "b": {"review_when": [{"when": f"not (not ({L})) and opening_room_one_exit", "reason": "x"}]},
        "c": {"review_when": [{"when": f"not ({L}) or opening_net_clear_width > 0", "reason": "x"}]},
        "d": {"review_when": [{"when": "opening_room_one_exit and not opening_operable", "reason": "x"}]},
        "e": {"limit": f"{L} or opening_room_door_to_outside", "check": f"({L} or opening_room_door_to_outside) or {rest}"},
    }
    for name, change in cases.items():
        bad = {**copy.deepcopy(r), **change}
        if "limit" in change:
            bad["review_when"] = [{**b, "when": b["when"].replace(f"not ({L})", f"not ({change['limit']})")}
                                  for b in bad["review_when"]]
        assert limit_problems(bad), name



def test_the_room_facts_copied_onto_an_opening_are_marked_from_its_room():
    """Review round 1 of 8d: the facts escape_openings.link copies from the sleeping room are marked `from`, so a
    limit can't read them (5e above); every opening_room_ fact is one."""
    from rule_format.parts import registry
    m = registry()["emergency_escape_opening"]["measures"]
    room = {k for k in m if k.startswith("opening_room_")}
    assert room and all(m[k].get("from") == "sleeping_room" for k in room)
    assert not [k for k, d in m.items() if "from" in d and k not in room]


def test_a_limit_reading_a_copied_room_fact_is_refused_on_its_own():
    """Review round 2 of 8d: a limit reading a fact copied from the room (marked `from`) is refused even where the
    rule reads it nowhere else (a compliance that leans on another opening's would be circular)."""
    r = next(x for x in _escape_rules() if x["id"] == "general.bc_1031_3_2_escape_opening_min_height")
    L = "opening_net_clear_height >= 24 or opening_room_other_compliant"
    bad = {**copy.deepcopy(r), "limit": L, "check": f"({L}) or opening_room_fourth_or_higher", "review_when": []}
    assert any("own figures" in p for p in limit_problems(bad))


def test_a_limit_rule_whose_applies_when_reads_the_part_is_refused():
    r = next(x for x in _escape_rules() if x["id"] == "general.bc_1031_3_2_escape_opening_min_height")
    assert not limit_problems(r)
    assert any("applies_when" in p for p in limit_problems({**copy.deepcopy(r), "applies_when": "opening_below_grade"}))


def test_from_must_name_another_part_kind():
    from rule_format.parts import load_registry, registry_problems
    kinds = copy.deepcopy(load_registry())
    kinds["emergency_escape_opening"]["measures"]["opening_room_one_exit"]["from"] = "attic"
    problems = registry_problems(kinds, set())
    assert any("'from' must name another part kind" in p for p in problems)
