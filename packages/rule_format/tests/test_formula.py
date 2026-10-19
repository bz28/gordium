import pytest

from rule_format.formula import FormulaError, MissingMeasure, evaluate, names, strings


@pytest.mark.parametrize("text, values, expected", [
    ("rear_yard >= max(min(0.25 * lot_depth, 50), 20)", {"rear_yard": 25, "lot_depth": 90}, True),
    ("rear_yard >= max(min(0.25 * lot_depth, 50), 20)", {"rear_yard": 21, "lot_depth": 90}, False),
    ("rear_yard >= max(min(0.25 * lot_depth, 50), 20)", {"rear_yard": 20, "lot_depth": 60}, True),
    ("building_area <= 0.25 * lot_area", {"building_area": 1855, "lot_area": 6674.7}, False),
    ('use in ["one_family_detached", "church"]', {"use": "church"}, True),
    ('use not in ["church"]', {"use": "church"}, False),
    ("parking_spaces >= (1 if sleeping_rooms <= 3 else 2)", {"parking_spaces": 1, "sleeping_rooms": 4}, False),
    ("not stories > 3", {"stories": 3}, True),
    ("-front_yard < 0", {"front_yard": 25}, True),
    ("0 < stories <= 3", {"stories": 3}, True),
])
def test_evaluate(text, values, expected):
    assert evaluate(text, values) is expected


@pytest.mark.parametrize("text", [
    "__import__('os')", "lot_area.real", "lot_area[0]", "lambda: 1", "open('x')",
    "max(lot_area, key=1)", "True", "None", "x if", "a ** 2", "[i for i in x]",
])
def test_rejects_anything_outside_the_language(text):
    with pytest.raises(FormulaError):
        evaluate(text, {"lot_area": 1, "x": [], "a": 1})


@pytest.mark.parametrize("text", [
    "stories <= 3 or building_height <= 35",   # 'or' must not hide a missing measure
    "stories <= 0 and building_height <= 35",  # nor 'and'
    "0 > stories < building_height",           # nor a chained comparison
])
def test_missing_measure_is_never_hidden(text):
    with pytest.raises(MissingMeasure) as e:
        evaluate(text, {"stories": 3, "building_height": None})
    assert e.value.name == "building_height"


def test_names_and_strings():
    f = 'use in ["church"] and max(lot_area, 1) > 0'
    assert names(f) == {"use", "lot_area"}
    assert strings(f) == {"church"}
