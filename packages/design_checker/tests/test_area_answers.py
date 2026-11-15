"""#38's floor areas (kind "area") asked in #37's start box: typed square feet, never rounded and never guessed at.
Before the demo merge of 2026-10-27 the box parsed every typed answer as a count, so 500.4 sq ft was refused with "a
whole number" (its rules stayed needs review, never a pass, but the architect could not answer it)."""

import pytest

from design_checker import rhino_logic as logic


@pytest.mark.parametrize("text, value", [("500.4", 500.4), ("500", 500), ("0", 0), (" 12.25 ", 12.25), ("", None),
                                        ("1,200", 1200), ("1,200.5", 1200.5)])
def test_an_area_is_kept_as_typed(text, value):
    got = logic.parse_answer("area", text)
    assert got == value and type(got) is type(value)


@pytest.mark.parametrize("text", ["-3", "500,4", "2,5", "12,00", "1e3", "nan", "inf", "5.", "lots", "1.2.3"])
def test_an_area_not_plainly_a_number_is_refused(text):
    with pytest.raises(ValueError, match="square feet"):
        logic.parse_answer("area", text)
    assert logic.answers_note([("home_occupation_area", "area", text)])[1] is True


def test_every_area_fact_is_asked_in_the_row_dialog_and_kept_as_typed():
    """Each area fact is a use detail (since facts-up-front, #45: asked in the panel's row dialog, not the start box)
    and the dialog keeps it as typed (a decimal stays a decimal); a refused entry changes nothing."""
    areas = [k for k in logic.STATED_FACTS if logic.STATED_FACTS[k][1] == "area"]
    assert areas
    for key in areas:
        assert key in logic.DEFERRED_FACTS and key not in logic.BOX_ASKS
        got = logic.row_answers_applied({}, [key], {key: "500.4"})
        assert got == {key: 500.4} and type(got[key]) is float
        with pytest.raises(ValueError, match="square feet"):
            logic.row_answers_applied({key: 10}, [key], {key: "500,4"})
