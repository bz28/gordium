"""#38's floor areas (kind "area") asked in #37's start box: typed square feet, never rounded and never guessed at.
Before the demo merge of 2026-10-27 the box parsed every typed answer as a count, so 500.4 sq ft was refused with "a
whole number" (its rules stayed needs review, never a pass, but the architect could not answer it)."""

import pytest

from design_checker import rhino_logic as logic


@pytest.mark.parametrize("text, value", [("500.4", 500.4), ("500", 500), ("0", 0), (" 12.25 ", 12.25), ("", None)])
def test_an_area_is_kept_as_typed(text, value):
    got = logic.parse_answer("area", text)
    assert got == value and type(got) is type(value)


@pytest.mark.parametrize("text", ["-3", "1,200", "500,4", "1e3", "nan", "inf", "5.", "lots", "1.2.3"])
def test_an_area_not_plainly_a_number_is_refused(text):
    with pytest.raises(ValueError, match="square feet"):
        logic.parse_answer("area", text)
    assert logic.answers_note([("home_occupation_area", "area", text)])[1] is True


def test_every_area_the_box_asks_is_typed_and_kept():
    """Each area fact the box can ask goes through answers_applied as typed (a decimal stays a decimal)."""
    areas = [k for k in logic.BOX_ASKS if logic.STATED_FACTS[k][1] == "area"]
    assert areas
    for key in areas:
        assert logic.parse_answer("area", "500.4") == 500.4
