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
    assert why == ("whether a door into a room with another way out ends a dead end is an open question (question 7): "
                   "under one reading it complies (the door ends the dead end), under the other it doesn't comply or "
                   "can't be told (the door doesn't end it)")
    assert parts.is_reading_words(why)


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
    assert why.startswith("whether a storage room's area is measured inside its walls or to their outer faces and "
                          "whether a story's area is measured inside its exterior walls or to their outer faces are "
                          "open questions (question 3): it complies if ")
    assert ("doesn't comply or can't be told if the storage rooms' area is measured to the walls' outer faces and the "
            "story's area is measured inside its walls") in why
    assert "_" not in why and " = " not in why and parts.is_reading_words(why)
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


# --- a measure standing on Gordium's reading (route note decision 1a, amended 2026-11-21: `confirm`) -----------------

SPRINKLERED_NEW = {**NEW_DAY_CARE, "sprinklered_9_7": True, "sprinkler_supervised_9_7": True}
WORDS = "Gordium's reading · confirm with the architects: a closet ... (cl through k; open question 11)"


def story_with(confirm, **measures):
    part = {"id": "L1", "measures": measures}
    if confirm is not None:
        part["confirm"] = confirm
    return {"story": [part]}


def row_of(rule, given, values, allowed):
    return parts.rows(rule, given, values, allowed)[0]


def test_a_fail_on_a_reading_to_confirm_keeps_its_reason_and_says_the_reading_in_its_own_field(maine):
    """Review round 1: a fail's words go in the row's `confirm`, never in its `reason` (which stays empty, so the
    line keeps its comparison)."""
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    row = row_of(rule, story_with({"common_path_of_travel_occupied": WORDS}, common_path_of_travel_occupied=140.0),
                 SPRINKLERED_NEW, allowed)
    assert (row["outcome"], row["reason"], row["confirm"]) == ("fail", None, [WORDS])


def test_a_pass_on_a_reading_to_confirm_is_never_a_pass(maine):
    """Review round 2 (principle 4): a figure that complies only under Gordium's reading needs review until the
    reading is confirmed, said so, as the checker does for a has-none reading (each_part.check_parts)."""
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    row = row_of(rule, story_with({"common_path_of_travel_occupied": WORDS}, common_path_of_travel_occupied=40.0),
                 SPRINKLERED_NEW, allowed)
    assert row["outcome"] == "needs_review"
    assert row["reason"] == "complies only if this reading is confirmed: " + WORDS
    assert parts.rule_result([row]) == "needs_review"


def test_a_reading_to_confirm_is_said_only_for_the_measures_a_rule_reads_and_has(maine):
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    # the words are for another measure: not said here
    row = row_of(rule, story_with({"egress_travel_distance": WORDS}, common_path_of_travel_occupied=40.0),
                 SPRINKLERED_NEW,
                 allowed)
    assert row["outcome"] == "pass" and "confirm" not in row
    # the measure isn't given: the row needs review for that, and no reading stands behind a value
    row = row_of(rule, story_with({"common_path_of_travel_occupied": WORDS}), SPRINKLERED_NEW, allowed)
    assert row["outcome"] == "needs_review" and "confirm" not in row
    # no `confirm`: as before
    row = row_of(rule, story_with(None, common_path_of_travel_occupied=40.0), SPRINKLERED_NEW, allowed)
    assert (row["outcome"], row["reason"]) == ("pass", None) and "confirm" not in row


def test_a_rule_that_doesnt_apply_says_no_reading(maine):
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    row = row_of(rule, story_with({"common_path_of_travel_occupied": WORDS}, common_path_of_travel_occupied=40.0),
                 NEW_DAY_CARE, allowed)
    assert row["outcome"] == "not_applicable" and "confirm" not in row   # unsprinklered: the 100-ft rule doesn't apply


# --- a figure standing on the architect's statement (route note decision 1b: `architect_stated`) ----------------

LEFT_OUT = "measured leaving out 1 space marked not occupied by the architect: abandoned"


def test_the_architects_statement_is_said_beside_the_row_and_never_holds_a_pass(maine):
    """Unlike Gordium's reading (`confirm`), the rooms the architect marks not occupied that a figure leaves out are
    the architect's own statement: a pass stays a pass, a fail a fail, each with the words beside it."""
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    for value, outcome in ((40.0, "pass"), (140.0, "fail")):
        part = {"id": "L1", "measures": {"common_path_of_travel_occupied": value},
                "architect_stated": {"common_path_of_travel_occupied": LEFT_OUT}}
        row = row_of(rule, {"story": [part]}, SPRINKLERED_NEW, allowed)
        assert (row["outcome"], row["architect_stated"]) == (outcome, [LEFT_OUT])
        assert "confirm" not in row
    # words for a measure the rule doesn't read, or with no value behind them: not said
    part = {"id": "L1", "measures": {"common_path_of_travel_occupied": 40.0},
            "architect_stated": {"egress_travel_distance_occupied": LEFT_OUT}}
    assert "architect_stated" not in row_of(rule, {"story": [part]}, SPRINKLERED_NEW, allowed)
    part = {"id": "L1", "measures": {}, "architect_stated": {"common_path_of_travel_occupied": LEFT_OUT}}
    row = row_of(rule, {"story": [part]}, SPRINKLERED_NEW, allowed)
    assert row["outcome"] == "needs_review" and "architect_stated" not in row


RESTS = "Gordium's reading, to confirm: ... This count holds only if BCNYS 1016.2.1 (p.341) is met"


def test_a_figure_resting_on_another_requirement_is_said_beside_the_row_and_never_holds_a_pass(maine):
    """`rests_on` (the dwelling units on a story stand on 1016.2.1, a person's check shown in the same answer): a pass
    stays a pass and a fail a fail, each with the words beside it; words for a measure the row doesn't read, or with
    no value behind them, aren't said."""
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    for value, outcome in ((40.0, "pass"), (140.0, "fail")):
        part = {"id": "L1", "measures": {"common_path_of_travel_occupied": value},
                "rests_on": {"common_path_of_travel_occupied": RESTS}}
        row = row_of(rule, {"story": [part]}, SPRINKLERED_NEW, allowed)
        assert (row["outcome"], row["rests_on"]) == (outcome, [RESTS])
        assert "confirm" not in row
    part = {"id": "L1", "measures": {"common_path_of_travel_occupied": 40.0},
            "rests_on": {"egress_travel_distance_occupied": RESTS}}
    assert "rests_on" not in row_of(rule, {"story": [part]}, SPRINKLERED_NEW, allowed)
    part = {"id": "L1", "measures": {}, "rests_on": {"common_path_of_travel_occupied": RESTS}}
    assert "rests_on" not in row_of(rule, {"story": [part]}, SPRINKLERED_NEW, allowed)


def test_a_mixed_result_says_its_open_question_in_words_never_a_tag(maine):
    """The reason an architect reads (the Revit pane's cause card and row): the question's own title and number
    from the open questions list (docs/decisions/2026-11-20_route_measurement.md), never "tag = answer"."""
    rules, allowed = maine
    rule = rules["general.nfpa_16_2_5_2_dead_end"]
    # neither reading complies (one fails, one can't be told): said so, never "complies if none"
    both = [{Q7: "with_door"}, {Q7: "without_door"}]
    assert parts.reading_words(both, [], both) == (
        "whether a door into a room with another way out ends a dead end is an open question (question 7): under "
        "either reading it doesn't comply or can't be told (the door ends the dead end; the door doesn't end it)")
    # a tag the list doesn't have yet is still words
    assert parts.question_words(["some_new_question"]) == "“some new question” is an open question"
    assert "_" not in parts.reading_words([{"q_x": "a_b"}, {"q_x": "c"}], [{"q_x": "a_b"}], [{"q_x": "c"}])
    # every tag the route measuring names its readings by has its words and number
    from model_measurement.routes import areas, dead_ends
    for tag in (dead_ends.QUESTION, areas.STORY_AREA_QUESTION, areas.ACCESSORY_AREA_QUESTION):
        assert {"question", "number", "answers"} <= set(parts.READING_QUESTIONS[tag])
    assert set(parts.READING_QUESTIONS[dead_ends.QUESTION]["answers"]) == {dead_ends.WITH, dead_ends.WITHOUT}
    assert outcome(rule, dead_end(30.0, 5.0), NEW_DAY_CARE, allowed)[0] == "needs_review"


def test_the_rules_own_review_is_said_only_where_it_holds_under_every_reading(maine):
    """A row needing review under every reading because the rule's own review_when holds whatever the answer says that
    reason, not the question (the story facts' merge, 2026-11-28: parts._own_reviews). An entry holding under only some
    readings never stands for the row: the question is said, as before (round 2 of its review: `any` for `all`)."""
    rules, allowed = maine
    rule = copy.deepcopy(rules["general.nfpa_16_2_5_2_dead_end"])
    each = [{"when": "corridor_dead_end_length >= 30", "reason": "Held at 30 only."},
            {"when": "corridor_dead_end_length < 30", "reason": "Held at 25 only."}]
    result, why = outcome({**rule, "review_when": each}, dead_end(30.0, 25.0), NEW_DAY_CARE, allowed)
    assert result == "needs_review" and parts.is_reading_words(why), why
    both = each + [{"when": "corridor_dead_end_length > 1", "reason": "Held whatever the answer."}]
    assert outcome({**rule, "review_when": both}, dead_end(30.0, 25.0), NEW_DAY_CARE, allowed) == \
        ("needs_review", "Held whatever the answer.")
