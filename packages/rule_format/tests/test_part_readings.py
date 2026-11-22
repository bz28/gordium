"""A part's measures given as named readings (decisions 6 and 8 of docs/decisions/2026-11-20_route_measurement.md):
parts.rows decides a rule under every combination of the readings it reads, question by question, as the checker's
zoning readings are (design_checker/check.py readings_of): pass only if every combination passes, fail only if every
one fails, else needs review naming the readings. A part with no readings is decided exactly as before."""

import copy

import pytest

from rule_format import parts
from rule_format.rulebook import REPO, Context, load

MAINE = REPO / "regulations/jurisdictions/maine/maine_state"
RULES = MAINE / "5_building_code_rules/drafted/general.yaml"
NEW_DAY_CARE = {"nfpa_day_care_occupancy": True, "day_care_existing": False, "sprinklered_9_7": False,
                "sprinkler_supervised_9_7": False}
Q7 = "door_ends_dead_end"


@pytest.fixture(scope="module")
def maine():
    return {r["id"]: r for r in load(RULES)["rules"]}, Context.for_jurisdiction(MAINE).allowed()


def dead_end(*lengths):
    return {"corridor": [{"id": "c", "measures": {}, "readings": {"corridor_dead_end_length": [
        {"value": v, "named": {Q7: a}} for v, a in zip(lengths, ("without_door", "with_door"))]}}]}


def outcome(rule, given, values, allowed):
    got = parts.rows(rule, given, values, allowed)
    return got[0]["outcome"], got[0]["reason"]


def test_one_reading_passing_and_one_failing_needs_review_naming_them(maine):
    rules, allowed = maine
    result, why = outcome(rules["general.nfpa_16_2_5_2_dead_end"], dead_end(30.0, 5.0), NEW_DAY_CARE, allowed)
    assert result == "needs_review"                                   # 30 > 20 fails, 5 passes (test 8)
    assert "door_ends_dead_end = without_door" in why and "complies if door_ends_dead_end = with_door" in why


def test_both_readings_passing_pass_and_both_failing_fail(maine):
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_2_dead_end"]
    assert outcome(rule, dead_end(18.0, 5.0), NEW_DAY_CARE, allowed)[0] == "pass"
    assert outcome(rule, dead_end(30.0, 25.0), NEW_DAY_CARE, allowed)[0] == "fail"


def test_a_part_with_no_readings_is_decided_as_before(maine):
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_2_dead_end"]
    plain = {"corridor": [{"id": "c", "measures": {"corridor_dead_end_length": 30.0}}]}
    assert outcome(rule, plain, NEW_DAY_CARE, allowed) == ("fail", None)
    # a value given wins over readings of it (the readings are only for a measure with no value)
    both = dead_end(5.0, 5.0)
    both["corridor"][0]["measures"]["corridor_dead_end_length"] = 30.0
    assert outcome(rule, both, NEW_DAY_CARE, allowed)[0] == "fail"


def test_readings_that_cant_be_read_need_review(maine):
    rules, allowed = maine
    bad = dead_end(30.0, 5.0)
    bad["corridor"][0]["readings"]["corridor_dead_end_length"][0]["value"] = "thirty"
    assert outcome(rules["general.nfpa_16_2_5_2_dead_end"], bad, NEW_DAY_CARE, allowed)[0] == "needs_review"


def areas(inside_story, outer_story, inside_storage, outer_storage):
    return {"story": [{"id": "L1", "measures": {}, "readings": {
        "story_building_area": [{"value": inside_story, "named": {"story_area_face": "inside"}},
                                {"value": outer_story, "named": {"story_area_face": "outer_faces"}}],
        "story_accessory_area": [{"value": inside_storage, "named": {"accessory_area_face": "inside"}},
                                 {"value": outer_storage, "named": {"accessory_area_face": "outer_faces"}}]}}]}


def test_15_the_10_percent_rule_is_worked_under_all_four_pairs_of_readings(maine):
    """Test 15: 508.2.1's check (made a rule here: the IBC's is a flag until its copy is verified) with both areas
    as readings. Story 5000 sf inside, 5151 to the outer faces; storage 490 inside, 535.811 to its outer faces
    (test 9): two pairs pass, two fail (the outer storage over the inside story among the fails): needs review.
    Storage 490 / 500: all four pass (500 <= 500.0, 10 percent of the inside story). 520 / 540: all four fail."""
    rules, allowed = maine
    rule = copy.deepcopy(rules["general.ibc_508_2_1_accessory_area"])
    rule["kind"] = "rule"
    result, why = outcome(rule, areas(5000, 5151, 490, 535.811), {}, allowed)
    assert result == "needs_review"
    assert "accessory_area_face = outer_faces, story_area_face = inside" in why
    assert outcome(rule, areas(5000, 5151, 490, 500), {}, allowed)[0] == "pass"
    assert outcome(rule, areas(5000, 5151, 520, 540), {}, allowed)[0] == "fail"


def test_15_the_rule_as_a_flag_still_needs_review_whatever_the_readings(maine):
    rules, allowed = maine
    assert outcome(rules["general.ibc_508_2_1_accessory_area"], areas(5000, 5151, 490, 500), {},
                   allowed)[0] == "needs_review"


def test_two_values_under_one_answer_need_review(maine):
    rules, allowed = maine
    twice = dead_end(5.0, 6.0)
    for r in twice["corridor"][0]["readings"]["corridor_dead_end_length"]:
        r["named"] = {Q7: "with_door"}                              # one answer, two values: not worked out
    assert outcome(rules["general.nfpa_16_2_5_2_dead_end"], twice, NEW_DAY_CARE, allowed)[0] == "needs_review"
