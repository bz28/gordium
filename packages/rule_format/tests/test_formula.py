import math

import pytest

from rule_format.formula import EvaluationError, FormulaError, MissingMeasure, evaluate, is_condition, names, strings

NUMBERS = ["rear_yard", "lot_depth", "lot_area", "lot_width", "building_area", "building_height",
           "stories", "front_yard", "parking_spaces", "sleeping_rooms", "a", "b", "x"]
KINDS = {n: "number" for n in NUMBERS} | {"use": frozenset({"one_family_detached", "church", "a", "ab"})}


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
    assert evaluate(text, values, KINDS) is expected


@pytest.mark.parametrize("text", [
    "__import__('os')", "lot_area.real", "lot_area[0]", "lambda: 1", "open('x')",
    "max(lot_area, key=1)", "max(lot_area)", "min()", "True", "None", "x if", "a ** 2",
    "[i for i in x]", 'use in "one_family_detached"', "", "1" + "+1" * 300,
    "-" * 100_000 + "1", "not " * 5_000 + "x",
    "rear_yard <= 1e999",                                       # infinity written as a number
    "rear_yard <= 1" + "0" * 400,                               # integer too large to be real
], ids=lambda t: t if len(t) <= 60 else f"{t[:20]}...({len(t)} chars)")   # Windows caps a test's name at 32,767
def test_rejects_anything_outside_the_language(text):
    with pytest.raises(FormulaError):
        evaluate(text, {"lot_area": 1, "x": 1, "a": 1, "use": "one_family_detached"}, KINDS)


@pytest.mark.parametrize("text", [
    "stories <= 3 or building_height <= 35",   # 'or' must not hide a missing measure
    "stories <= 0 and building_height <= 35",  # nor 'and'
    "0 > stories < building_height",           # nor a chained comparison
])
@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -math.inf, True, 10**400, -5, "35"])
def test_missing_or_unusable_measure_is_never_hidden(text, bad):
    with pytest.raises(MissingMeasure) as e:
        evaluate(text, {"stories": 3, "building_height": bad}, KINDS)
    assert e.value.name == "building_height"


@pytest.mark.parametrize("text, values", [
    ("use > 3", {"use": "church"}),                              # text vs number
    ("lot_area / lot_width > 1", {"lot_area": 1, "lot_width": 0}),  # division by zero
    ('use * 999999999999 == "x"', {"use": "ab"}),                # arithmetic on text
    ("not stories", {"stories": 3}),                             # 'not' of a number
    ("stories and lot_area > 1", {"stories": 3, "lot_area": 5}),  # 'and' of a number
    ("lot_area * 1e308 * 10 > 1", {"lot_area": 5}),            # arithmetic overflows to infinity
    ('use in ["a", 1]', {"use": "a"}),                          # list mixes text and numbers
])
def test_values_that_cannot_be_evaluated(text, values):
    with pytest.raises(EvaluationError):
        evaluate(text, values, KINDS)


@pytest.mark.parametrize("text, expected", [
    ("rear_yard >= 20", True), ("a > 1 and b > 1", True), ("not a > 1", True),
    ("rear_yard - 20", False), ("rear_yard >= 20, lot_depth > 0", False), ("max(a, b)", False),
])
def test_is_condition(text, expected):
    assert is_condition(text) is expected


def test_names_and_strings():
    f = 'use in ["church"] and max(lot_area, 1) > 0'
    assert names(f) == {"use", "lot_area"}
    assert strings(f) == {"church"}


@pytest.mark.parametrize("values, kinds", [
    ({"rear_yard": -5}, {"rear_yard": "number"}),                 # negative length from a failed measurement
    ({"rear_yard": "5"}, {"rear_yard": "number"}),                # text where a number belongs
    ({"use": "castle"}, {"use": frozenset({"church"})}),          # not one of the city's use names
    ({"use": 5}, {"use": "text"}),                                # number where text belongs
])
def test_unusable_measurements_are_missing(values, kinds):
    name = next(iter(values))
    with pytest.raises(MissingMeasure):
        evaluate(f"{name} == {name}", values, kinds)


def test_fails_closed_without_measure_descriptions():
    with pytest.raises(TypeError):
        evaluate("rear_yard <= 50", {"rear_yard": 5})                  # descriptions are required
    with pytest.raises(MissingMeasure):
        evaluate("rear_yard <= 50", {"rear_yard": 5}, {})              # undescribed measure = unusable
    with pytest.raises(MissingMeasure):
        evaluate('use == "church"', {"use": "church"}, {"use": "text"})  # text with no allowed list
