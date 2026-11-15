"""The stream distance is asked in feet and kept as typed (never rounded: 19.96 ft typed as 20 would pass §325-26's
20 ft); a negative or non-number distance is refused, as the floor areas are."""

import pytest

from design_checker import rhino_logic as logic


def test_a_distance_is_kept_as_typed():
    assert logic.update_counts({}, {"stream_distance": 19.96})["stream_distance"] == 19.96
    assert logic.STATED_FACTS["stream_distance"][1] == "length"


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), "20"])
def test_a_bad_distance_is_refused(bad):
    with pytest.raises(ValueError, match="feet"):
        logic.update_counts({}, {"stream_distance": bad})


def test_every_stated_fact_has_a_prompt_kind_the_plugin_asks():
    """PR4 review round 1: a new kind must reach the plugin's prompt, or a distance would be asked as yes / no."""
    assert {kind for _, kind, _ in logic.STATED_FACTS.values()} <= {"count", "yes_no", "area", "length"}


def test_contradictory_stream_answers_are_a_lot_facts_row_asking_both():
    """PR4 review round 2: the "no" and the distance under 20 ft are shown as lot facts that disagree, with both
    asked again (the distance may be the typo), as the household counts are."""
    from model_measurement.project import fact_conflict_rows
    city = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city"}     # each lot is its own place's
    rows = fact_conflict_rows({**city, "stream_near_lot": False, "stream_distance": 5})
    assert [facts for _, facts in rows] == [("stream_near_lot", "stream_distance")]
    assert "check both answers" in rows[0][0]
    assert fact_conflict_rows({**city, "stream_near_lot": False, "stream_distance": 20}) == []
    assert fact_conflict_rows({**city, "stream_near_lot": True, "stream_distance": 5}) == []
