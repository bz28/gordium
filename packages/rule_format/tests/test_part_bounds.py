"""A part's ceilings on measures it has no value for (parts.under_bounds: `bounds`, given by the checker's occupant
loads, design_checker/occupant_load.py): a rule is decided on a ceiling only where each of its formulas is provably
monotone in the measure and has the same truth at none and at the ceiling, so it gives that answer for every value the
measure can take. Anything else (a formula the proof can't follow, a rule that answers differently somewhere between,
a ceiling that isn't a number) leaves the row as it was: never a pass a value under the ceiling could deny.

Every rule here is SYNTHETIC: made up for these tests; the numbers only look like egress numbers."""

import pytest

from rule_format import parts

THREE_EXITS = "space_is_exit or (space_occupant_load <= 500 or space_exit_count >= 3)"


def rule(check, **more):
    return {"id": "t.bound", "kind": "rule", "for_each": "space", "when_none": "needs_review", "check": check, **more}


def space(bound=None, if_stated=None, **measures):
    got = {"id": "s1", "name": "Hall", "measures": {"space_is_exit": False, "space_exit_count": 2, **measures}}
    if bound is not None or if_stated is not None:
        entry = {} if bound is None else {"at_most": bound, "why": "the story's area at the densest factor"}
        if if_stated is not None:
            entry["if_stated"] = {"at_most": if_stated, "why": "w", "facts": ["mezzanines"]}
        got["bounds"] = {"space_occupant_load": entry}
    return {"space": [got]}


def row(r, given):
    got = parts.rows(r, given, {}, {})
    assert len(got) == 1
    return got[0]


def test_a_monotone_rule_passing_at_its_ceiling_passes_and_says_why():
    got = row(rule(THREE_EXITS), space(360))
    assert got["outcome"] == "pass"
    assert got["reason"] == ("complies at any value up to the most it can be (its occupant load can be at most 360: "
                             "the story's area at the densest factor)")


def test_a_ceiling_over_the_threshold_settles_nothing():
    assert row(rule(THREE_EXITS), space(501))["outcome"] == "needs_review"
    assert row(rule(THREE_EXITS), space(None))["outcome"] == "needs_review"     # no proven ceiling: no answer
    assert row(rule(THREE_EXITS), space())["outcome"] == "needs_review"         # none at all: as before


@pytest.mark.parametrize("check", [
    "space_occupant_load <= 10 or space_occupant_load >= 300",       # true at 0 and at 400, false at 100
    "space_occupant_load == 0 or space_exit_count >= 3",             # an == the proof can't follow
    "space_exit_count >= (2 if space_occupant_load <= 500 else 3)",  # an if-else the proof can't follow
])
def test_a_rule_the_proof_cant_show_monotone_is_never_decided_on_a_ceiling(check):
    """The false pass this guards against: the first check passes at none and at the ceiling of 400, yet fails for
    a load of 100. Evaluating only the two ends would pass it."""
    got = row(rule(check), space(400))
    assert got["outcome"] == "needs_review", check


def test_a_review_condition_that_turns_on_between_the_ends_keeps_it_in_review():
    r = rule("space_occupant_load <= 500", review_when=[{"when": "space_occupant_load > 49", "reason": "r"}])
    assert row(r, space(360))["outcome"] == "needs_review"             # false at none, true at 360
    assert row(r, space(40))["outcome"] == "pass"                      # false at both ends: false everywhere


def test_applies_when_on_the_ceiling_must_agree_too():
    r = rule("space_exit_count >= 3", applies_when="space_occupant_load > 500", when_none="not_applicable")
    assert row(r, space(360))["outcome"] == "not_applicable"           # never over 500
    assert row(r, space(600))["outcome"] == "needs_review"             # applies only somewhere between


def test_a_ceiling_that_isnt_a_number_is_none():
    for bad in (True, "360", float("nan"), float("inf"), -1):
        assert row(rule(THREE_EXITS), space(bad))["outcome"] == "needs_review", bad


def test_a_value_given_wins_over_the_ceiling():
    assert row(rule(THREE_EXITS), space(360, space_occupant_load=600))["outcome"] == "fail"


def test_a_ceiling_the_facts_would_prove_names_them_and_keeps_the_row_in_review():
    got = row(rule(THREE_EXITS), space(540, if_stated=360))
    assert got["outcome"] == "needs_review" and got["bound_facts"] == ["mezzanines"]
    assert "bound_facts" not in row(rule(THREE_EXITS), space(540, if_stated=520))     # it wouldn't settle it


def test_a_part_that_may_not_be_of_its_kind_is_never_passed_on_a_ceiling():
    given = space(360)
    given["space"][0]["maybe"] = "it may be a corridor"
    assert row(rule(THREE_EXITS), given)["outcome"] == "needs_review"
