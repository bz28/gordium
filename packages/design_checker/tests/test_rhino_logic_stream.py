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
