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
