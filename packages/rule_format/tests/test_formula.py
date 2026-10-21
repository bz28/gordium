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


# ---- at the limit complies: exact decimals, and float noise from the geometry is not a violation -------------

@pytest.mark.parametrize("text, values, expected", [
    ("rear_yard >= 0.2 * lot_depth", {"rear_yard": 26.4, "lot_depth": 132}, True),       # 0.2*132 in floats: 26.400000000000002
    ("rear_yard >= 0.2 * lot_depth", {"rear_yard": 26.39, "lot_depth": 132}, False),
    ("rear_yard >= 0.2 * lot_depth", {"rear_yard": 26.4 - 1e-5, "lot_depth": 132}, False),  # a hundred-thousandth short
    ("building_area <= 0.35 * lot_area", {"building_area": 1750.7, "lot_area": 5002}, True),
    ("building_area <= 0.35 * lot_area", {"building_area": 1750.71, "lot_area": 5002}, False),
    ("building_height <= 35 + 0.1 * 30", {"building_height": 38.0}, True),
    ("building_height <= 35 + 0.1 * 30", {"building_height": 38.01}, False),
    ("rear_yard >= 0.1 + 0.2", {"rear_yard": 0.3}, True),
    ("rear_yard >= 26.4", {"rear_yard": 26.399999999999995}, True),                       # geometry's float noise
    ("rear_yard > 26.4", {"rear_yard": 26.4}, False),                                     # "more than": not at the limit
    ("rear_yard < 26.4", {"rear_yard": 26.400000000000002}, False),
    ("rear_yard > 26.4", {"rear_yard": 26.41}, True),
])
def test_a_design_exactly_at_a_limit_complies_and_anything_measurably_over_fails(text, values, expected):
    assert evaluate(text, values, KINDS) is expected


def test_at_the_limit_complies_for_every_whole_depth_and_area():
    """For every whole lot depth and area, a design measured exactly at the limit (as the float nearest it, the
    way the geometry hands it over) complies, and one a hundredth over fails."""
    from fractions import Fraction
    for n in range(1, 3001):
        for share, text, over in ((Fraction("0.2"), "rear_yard >= 0.2 * lot_depth", -0.01),
                                  (Fraction("0.25"), "rear_yard >= max(min(0.25 * lot_depth, 50), 0)", -0.01),
                                  (Fraction("0.35"), "building_area <= 0.35 * lot_area", 0.01)):
            name = "rear_yard" if "rear" in text else "building_area"
            at = float(share * n) if "50" not in text else float(min(share * n, 50))
            other = {"lot_depth": n, "lot_area": n}
            assert evaluate(text, {name: at, **other}, KINDS) is True, (text, n)
            assert evaluate(text, {name: at + over, **other}, KINDS) is False, (text, n)
            assert evaluate(text, {name: 0.2 * n if "0.2 " in text else 0.35 * n if "0.35" in text else at, **other},
                            KINDS) is True, (text, n)                      # the float product itself, too


def test_numbers_come_back_as_plain_python_would_give_them():
    assert evaluate("0.2 * lot_depth", {"lot_depth": 132}, KINDS) == 26.4
    assert type(evaluate("0.2 * lot_depth", {"lot_depth": 132}, KINDS)) is float
    assert type(evaluate("max(a, 2)", {"a": 1}, KINDS)) is int
    assert type(evaluate("max(a, 2)", {"a": 1.0}, KINDS)) is float
    assert evaluate("a / 4", {"a": 2}, KINDS) == 0.5


def test_a_margin_at_the_limit_is_zero_exactly_where_the_comparison_complies():
    from rule_format.formula import margin
    limit = evaluate("0.2 * lot_depth", {"lot_depth": 132}, KINDS)
    assert margin(26.4, limit, True) == 0.0 and margin(26.400000000000002, 26.4, False) == 0.0
    assert margin(26.39, limit, True) == pytest.approx(-0.01) and margin(1750.71, 1750.7, False) == pytest.approx(-0.01)
    assert margin(30, 27.5, True) == 2.5 and margin(1700, 1750.7, False) == pytest.approx(50.7)
    for n in range(1, 2001):
        at = 0.2 * n
        assert (margin(at, evaluate("0.2 * lot_depth", {"lot_depth": n}, KINDS), True) == 0.0) is \
            evaluate("rear_yard >= 0.2 * lot_depth", {"rear_yard": at, "lot_depth": n}, KINDS)


@pytest.mark.parametrize("text, direction", [
    # the eaves rule: the requirement only grows with the height (the §325-16C bonus), so it is truest at h = 0
    ("front_yard_eaves >= 25 + max(building_height - 35, 0) - 2", -1),
    ("front_yard_eaves >= 25 + max(building_height - 35, 0) - 2 and rear_yard_eaves >= 3", -1),
    ("building_height <= 35", -1),
    ("building_height >= 40", 1),
    ("not building_height <= 35", 1),
    ("2 * building_height > front_yard", 1),
    ("front_yard >= building_height / 2", -1),
    ("front_yard >= 25", 0),                                      # doesn't use it
    # not proven: equality, a product of two measures, an if-else, two directions at once, a chain
    ("building_height == 30", None),
    ("front_yard >= building_height * lot_depth", None),
    ("front_yard >= (10 if building_height > 35 else 5)", None),
    ("building_height <= 35 and building_height >= 20", None),
    ("20 <= building_height <= 35", None),
    ("front_yard >= 0 * building_height", None),
    ("front_yard >= -1 * building_height", None),
])
def test_how_a_conditions_truth_moves_as_a_measure_grows(text, direction):
    """Review round 12 (decided 2026-10-21): a rule that fails for every value an unmeasured number could take
    does not comply; that rests on this proof from the formula's structure, never on sampling."""
    from rule_format.formula import truth_direction
    assert truth_direction(text, "building_height") == direction
