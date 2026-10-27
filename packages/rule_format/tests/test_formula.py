import re
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
])
def test_rejects_anything_outside_the_language(text):
    with pytest.raises(FormulaError):
        evaluate(text, {"lot_area": 1, "x": 1, "a": 1, "use": "one_family_detached"}, KINDS)


@pytest.mark.parametrize("text, known", [
    ("stories <= 3 or building_height <= 35", True),    # True or unknown: True, whatever the height is
    ("stories <= 0 and building_height <= 35", False),  # False and unknown: False
    ("0 > stories < building_height", False),           # a chain is an and: its false link decides it
    ("stories <= 0 or building_height <= 35", None),    # False or unknown: unknown
    ("stories <= 3 and building_height <= 35", None),   # True and unknown: unknown
    ("not building_height <= 35", None),
    ("stories < building_height", None),
    ("stories <= (1 if building_height > 30 else 1)", False),  # the same either way: known
    ("stories <= (3 if building_height > 30 else 2)", None),
    ("max(stories, building_height) >= 3", None),
])
@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -math.inf, True, 10**400, -5, "35"])
def test_a_missing_measure_is_unknown_and_follows_three_valued_logic(text, known, bad):
    """A missing or unusable measure is never hidden where it could change the result (MissingMeasure, so the rule
    needs review), and never makes a result unknown where it can't (Kleene: True or unknown is True; False and
    unknown is False)."""
    values = {"stories": 3, "building_height": bad}
    if known is None:
        with pytest.raises(MissingMeasure) as e:
            evaluate(text, values, KINDS)
        assert e.value.name == "building_height"
    else:
        assert evaluate(text, values, KINDS) is known


def test_three_valued_results_agree_with_every_value_the_missing_measure_could_take():
    """Exhaustive over formula shapes and substituted values: wherever the evaluation says True or False with a
    measure missing, every value that measure could take gives that same answer (so it is never a guess)."""
    import itertools
    atoms = ["a <= 3", "a >= 5", "b <= 4", "b > 2", "not a <= 3", "a < b", "1 <= a <= 6"]
    shapes = [f"{x} or {y}" for x, y in itertools.combinations(atoms, 2)]
    shapes += [f"{x} and {y}" for x, y in itertools.combinations(atoms, 2)]
    shapes += [f"({x} or {y}) and {z}" for x, y, z in itertools.permutations(atoms[:5], 3)]
    shapes += [f"not ({x} and {y})" for x, y in itertools.combinations(atoms, 2)]
    shapes += [f"{x} or ({y} and {z})" for x, y, z in itertools.permutations(atoms[:5], 3)]
    grid = [0, 1, 2, 3, 3.5, 4, 5, 6, 7.25, 10]
    for text in shapes:
        for missing in ("a", "b"):
            for known in grid:
                values = {"a": known, "b": known} | {missing: None}
                try:
                    got = evaluate(text, values, KINDS)
                except MissingMeasure:
                    continue
                every = {evaluate(text, values | {missing: v}, KINDS) for v in grid}
                assert every == {got}, (text, missing, known, got, every)


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


def test_a_number_used_as_true_false_is_refused_by_its_type_whatever_its_value():
    for value in (50, None):
        with pytest.raises(EvaluationError, match=r"'not' needs a true/false test"):
            evaluate("not lot_width", {"lot_width": value}, KINDS)


@pytest.mark.parametrize("text, problem", [
    ('use == 5', "== and != compare two numbers or two texts"),
    ("(a > 1) == (b < 2)", "== and != compare two numbers or two texts"),
    ("(a > 1) in [b > 1]", "a list holds numbers, or texts"),
    ("(1 if a > 1 else b > 2) or a > 1", "both branches of an if must give two numbers or two texts"),
    ("stories or building_height <= 35", "and/or need true/false tests"),
    ("(stories <= 3) + 1 > 0", "arithmetic needs numbers"),
    ("not stories", "'not' needs a true/false test"),
    ('use > 3', "<, <=, >, >= compare numbers"),
    ('use in [1, 2]', "'in' needs a number or text and a list of the same kind"),
    ("stories <= (1 if use else 2)", "an if needs a true/false test"),
    ("ghost > 1", "unknown measure 'ghost'"),
])
def test_an_ill_typed_formula_is_refused_before_any_value(text, problem):
    """Review of 0582c65 (P1): a formula that errors for every value is caught by its types, at validation."""
    from rule_format.formula import FormulaError, type_of
    with pytest.raises(FormulaError, match=re.escape(problem)):
        type_of(text, KINDS)


def test_a_well_typed_formula_has_its_type():
    from rule_format.formula import type_of
    assert type_of("rear_yard >= max(min(0.25 * lot_depth, 50), 20)", KINDS) == "bool"
    assert type_of('use in ["church"] and (1 if stories > 2 else 2) <= 3', KINDS) == "bool"
    assert type_of("max(a, b) / 2", KINDS) == "number"


@pytest.mark.parametrize("text, values", [
    ("lot_area >= 1 and (use == 5 or building_height < 5)", {"lot_area": 10, "building_height": 1}),
    ("stories or building_height <= 35", {"building_height": 3}),
    ("(stories <= 3) + 1 > 0 or a > 0", {"a": 1}),
    ("a / b > 1 or stories <= 3", {"a": 1, "b": 0, "stories": 1}),
    ("stories / b > 1 or a > 0", {"b": 0, "a": 1}),
])
def test_an_error_every_value_would_give_is_never_hidden_under_an_unknown(text, values):
    """Review of 0582c65 (P1, P2): with the measure missing, Kleene must not resolve a formula that would raise for
    every value of it (wrong types, division by a known zero): it raises (needs review), as complete data does."""
    with pytest.raises(EvaluationError):
        evaluate(text, values, KINDS | {"use": frozenset({"church"})})


def test_known_answers_agree_with_every_substitution_including_ill_typed_atoms_and_division():
    """Exhaustive: for formula shapes mixing well-typed and ill-typed atoms, division and if/else, wherever the
    evaluation with a measure missing gives an answer, every value of that measure gives that same answer and
    never an error; and wherever it raises an error, some value raises it too."""
    import itertools
    kinds = KINDS | {"use": frozenset({"a", "ab"})}
    atoms = ["a <= 3", "b > 2", "a / b > 1", "a / (b - 4) >= 0", '(1 if a > 2 else 0) <= b', 'use == "a"',
             "max(a, b) >= 4", "-a < -2"]
    shapes = [f"{x} or {y}" for x, y in itertools.combinations(atoms, 2)]
    shapes += [f"{x} and {y}" for x, y in itertools.combinations(atoms, 2)]
    shapes += [f"not ({x} or {y})" for x, y in itertools.combinations(atoms, 2)]
    grid = {"a": [0, 1, 2, 3, 4, 5, 7.5], "b": [0, 1, 2, 3, 4, 5, 7.5], "use": ["a", "ab"]}

    def answer(text, values):
        try:
            return evaluate(text, values, kinds)
        except EvaluationError:
            return "error"

    for text in shapes:
        for missing in ("a", "b", "use"):
            for base in itertools.product(*(grid[n] for n in ("a", "b", "use"))):
                values = dict(zip(("a", "b", "use"), base)) | {missing: None}
                try:
                    got = evaluate(text, values, kinds)
                except MissingMeasure:
                    continue
                except EvaluationError:
                    assert "error" in {answer(text, values | {missing: v}) for v in grid[missing]}, (text, values)
                    continue
                every = {answer(text, values | {missing: v}) for v in grid[missing]}
                assert every == {got}, (text, missing, values, got, every)


def _random_formula(rnd, depth, want="bool"):
    """A random expression over the whole grammar (numbers, two text measures, true/false, lists and tuples, every
    operator, min/max of 1 to 4 values, if, ordering, equality and mixed chains, in / not in), grown towards a kind
    (`want`) but often given operands of a random kind, and every operator tried on every kind: so many are
    well-typed and deep, and many are wrong in every way type_of must refuse."""
    if rnd.random() < 0.15:
        want = rnd.choice(["number", "text", "bool"])            # an operand of any kind: often ill-typed

    def g(kind):
        return _random_formula(rnd, depth - 1, kind)
    if depth == 0 or rnd.random() < 0.15:
        return rnd.choice({"number": ["a", "b", "0", "1", "2.5", "35", "0.25"],
                           "text": ["u", "v", '"x"', '"y"', '"w"'],
                           "bool": ["(a > 1)", '(u == "x")', "(b <= 2.5)", '(v != "w")'] + _YES_NO}[want])
    any_kind = rnd.choice(["number", "text", "bool"])
    chained = rnd.choice(["number", "number", any_kind])

    def seq(kind, low, high):
        return ", ".join(g(kind) for _ in range(rnd.randint(low, high)))
    shapes = {
        "number": [lambda: f"({g('number')} {rnd.choice('+-*/')} {g('number')})", lambda: f"(-{g('number')})",
                   lambda: f"{rnd.choice(['min', 'max'])}({seq('number', 1, 4)})",
                   lambda: f"({g('number')} if {g('bool')} else {g('number')})"],
        "text": [lambda: f"({g('text')} if {g('bool')} else {g('text')})"],
        "bool": [lambda: f"(not {g('bool')})",
                 lambda: "(" + f" {rnd.choice(['and', 'or'])} ".join(g("bool") for _ in range(rnd.randint(2, 3))) + ")",
                 lambda: "(" + g(chained) + "".join(f" {rnd.choice(['<', '<=', '>', '>=', '==', '!='])} {g(chained)}"
                                                    for _ in range(rnd.randint(1, 3))) + ")",   # mixed chains, any kind
                 lambda: f"({g(any_kind)} {rnd.choice(['==', '!='])} {g(any_kind)})",
                 lambda: f"({g(any_kind)} {rnd.choice(['in', 'not in'])} [{seq(any_kind, 0, 3)}])",
                 lambda: f"({g(any_kind)} {rnd.choice(['in', 'not in'])} ({seq(any_kind, 2, 3)}))",   # a tuple
                 lambda: f"({g('bool')} if {g('bool')} else {g('bool')})"],
    }
    return rnd.choice(shapes[want])()


_YES_NO = []                    # yes/no measures, where the language has them (none here)
_KINDS = {"a": "number", "b": "number", "u": frozenset({"x", "z"}), "v": frozenset({"w", "x"})}
_TEXT_VALUES = {"u": ["x", "z"], "v": ["w", "x"]}


class _Strict:
    """A value of one kind for the reference evaluator: its operators take only their own kind and raise
    TypeError on any other (so true/false is never compared, put in a list or used in arithmetic)."""

    def __init__(self, kind, value):
        self.kind, self.value = kind, value

    def _same(self, other, *kinds):
        if not isinstance(other, _Strict) or other.kind != self.kind or self.kind not in kinds:
            raise TypeError(f"{self.kind} with {getattr(other, 'kind', other)}")
        return other.value

    def __add__(self, o): return _Strict("n", self.value + self._same(o, "n"))
    def __sub__(self, o): return _Strict("n", self.value - self._same(o, "n"))
    def __mul__(self, o): return _Strict("n", self.value * self._same(o, "n"))
    def __truediv__(self, o): return _Strict("n", self.value / self._same(o, "n"))   # ZeroDivisionError at 0

    def __neg__(self):
        if self.kind != "n":
            raise TypeError("minus of " + self.kind)
        return _Strict("n", -self.value)

    def __bool__(self):
        if self.kind != "b":
            raise TypeError("a " + self.kind + " as true/false")
        return self.value

    def __hash__(self):
        return 0


def _close(a, b):
    """Two numbers within the language's own AT_LIMIT of each other (a millionth, or a billionth of the larger)."""
    from fractions import Fraction
    return abs(a - b) <= max(Fraction(1, 10 ** 6), Fraction(1, 10 ** 9) * max(abs(a), abs(b)))


def _ref_compare(op, x, y):
    if op in ("<", "<=", ">", ">="):
        b, a = x._same(y, "n"), x.value
        return {"<": a < b and not _close(a, b), "<=": a <= b or _close(a, b),
                ">": a > b and not _close(a, b), ">=": a >= b or _close(a, b)}[op]
    if op in ("==", "!="):
        same = x.value == x._same(y, "n", "t")
        return same if op == "==" else not same
    if not isinstance(y, list) or any(i.kind != x.kind for i in y) or x.kind not in ("n", "t"):
        raise TypeError("in")
    found = any(i.value == x.value for i in y)
    return found if op == "in" else not found


def _reference(text, values, kinds):
    """An independent evaluator of complete data (no unknowns), written apart from formula.py: Python's own
    evaluation over _Strict values (exact Fractions for numbers), with and/or/not, chains, lists, min/max and if
    rewritten to strict, every-part-evaluated forms. Raises TypeError on any mix of kinds."""
    import ast
    from fractions import Fraction
    names = {}
    for n, v in values.items():
        names[n] = _Strict("n", Fraction(repr(v)) if type(v) is float else Fraction(v)) if kinds[n] == "number" \
            else _Strict("b", v) if kinds[n] == "boolean" else _Strict("t", v)

    def lit(v):
        return _Strict("t", v) if type(v) is str else _Strict("n", Fraction(repr(v)) if type(v) is float else Fraction(v))

    def every(op, *xs):
        flags = [bool(x) for x in xs]          # every part checked to be true/false
        return _Strict("b", all(flags) if op == "and" else any(flags))

    def chain(first, *pairs):
        operands, ops = [first] + list(pairs[1::2]), pairs[::2]
        return _Strict("b", all([_ref_compare(o, x, y) for o, x, y in zip(ops, operands, operands[1:])]))

    def extreme(f, *xs):
        if any(x.kind != "n" for x in xs):
            raise TypeError("min/max of " + ",".join(x.kind for x in xs))
        return _Strict("n", f(x.value for x in xs))

    def negate(x):
        return _Strict("b", not bool(x))

    def pick(test, yes, no):
        chosen = yes() if bool(test) else no()
        if chosen.kind not in ("n", "t"):
            raise TypeError("an if giving " + chosen.kind)
        return chosen

    def items(*xs):
        return list(xs)
    OPS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
           ast.In: "in", ast.NotIn: "not in"}

    class Rewrite(ast.NodeTransformer):
        def visit_Constant(self, node):
            return ast.Call(ast.Name("_lit", ast.Load()), [node], [])

        def visit_BoolOp(self, node):
            self.generic_visit(node)
            return ast.Call(ast.Name("_every", ast.Load()),
                            [ast.Constant("and" if isinstance(node.op, ast.And) else "or")] + node.values, [])

        def visit_UnaryOp(self, node):
            self.generic_visit(node)
            if isinstance(node.op, ast.Not):
                return ast.Call(ast.Name("_negate", ast.Load()), [node.operand], [])
            return node

        def visit_Compare(self, node):
            self.generic_visit(node)
            args = [node.left]
            for op, right in zip(node.ops, node.comparators):
                args += [ast.Constant(OPS[type(op)]), right]
            return ast.Call(ast.Name("_chain", ast.Load()), args, [])

        def visit_Call(self, node):
            self.generic_visit(node)
            return ast.Call(ast.Name("_extreme", ast.Load()), [ast.Name(node.func.id, ast.Load())] + node.args, [])

        def visit_IfExp(self, node):
            self.generic_visit(node)
            lam = lambda body: ast.Lambda(ast.arguments([], [], None, [], [], None, []), body)
            return ast.Call(ast.Name("_pick", ast.Load()), [node.test, lam(node.body), lam(node.orelse)], [])

        def visit_List(self, node):
            self.generic_visit(node)
            return ast.Call(ast.Name("_items", ast.Load()), node.elts, [])
        visit_Tuple = visit_List

    tree = ast.fix_missing_locations(Rewrite().visit(ast.parse(text, mode="eval")))
    env = {"_lit": lit, "_every": every, "_chain": chain, "_extreme": extreme, "_negate": negate, "_pick": pick,
           "_items": items, "min": min, "max": max, "__builtins__": {}} | names
    out = eval(compile(tree, "<reference>", "eval"), env)
    return float(out.value) if out.kind == "n" else out.value


def _grid(text):
    """Values for each measure: the formula's own numbers and every number its constant parts work out to, each
    with values just inside and just outside AT_LIMIT either side, the points between them, and 0."""
    import ast
    from fractions import Fraction
    found = {Fraction(0), Fraction(1)}
    for node in ast.walk(ast.parse(text, mode="eval")):
        if isinstance(node, ast.expr) and not any(isinstance(n, ast.Name) and n.id not in ("min", "max")
                                                  for n in ast.walk(node)):
            try:
                v = evaluate(ast.unparse(node), {}, {})
            except Exception:
                continue
            if type(v) in (int, float):
                found.add(Fraction(repr(float(v))))
    near = set()
    for c in sorted(found):
        near |= {c, c + Fraction(1, 10 ** 7), c - Fraction(1, 10 ** 7), c + Fraction(1, 10 ** 5), c - Fraction(1, 10 ** 5)}
    ordered = sorted(found)
    near |= {(x + y) / 2 for x, y in zip(ordered, ordered[1:])}
    numbers = sorted(float(x) for x in near if x >= 0)
    if len(numbers) > 7:                       # keep the run short: the thresholds first, then a spread
        keep = [float(c) for c in ordered if c >= 0][:4]
        numbers = sorted(set(keep + numbers[::max(1, len(numbers) // 4)]))[:8]
    grid = {"a": numbers, "b": numbers} | _TEXT_VALUES
    return grid | {n: [True, False] for n in _YES_NO}


def test_the_type_rules_and_three_valued_logic_are_sound_over_the_whole_grammar():
    """Generative (fixed seeds, thousands of random formulas of depth up to 4, random missing measures), checked
    against an independent strict reference evaluator (_reference: not formula.py's code or type table):
    (a) for every formula type_of accepts and every complete set of values (a grid around the formula's own and
    derived thresholds, just inside and outside AT_LIMIT), the reference never finds a type error and gives the
    same answer as evaluate() (a division by zero is an error in both); so a type table that allows too much
    fails here; (b) whenever an evaluation with measures missing gives an answer, every way of filling them in
    gives that same answer, never an error. No message ever shows a value as Fraction(...)."""
    import itertools
    import random
    from rule_format.formula import FormulaError, type_of
    kinds = _KINDS | {n: "boolean" for n in _YES_NO}

    def run(text, values):
        try:
            return ("value", evaluate(text, values, kinds))
        except MissingMeasure:
            return ("missing", None)
        except (EvaluationError, FormulaError) as e:
            assert "Fraction(" not in str(e), (text, e)
            return ("error", str(e))

    accepted = resolved = 0
    for seed in range(4):
        rnd = random.Random(seed)
        for _ in range(1000):
            text = _random_formula(rnd, rnd.randint(1, 4), rnd.choice(["bool", "bool", "number"]))
            if len(text) > 500:                      # longer than a formula may be (MAX_LENGTH)
                continue
            try:
                type_of(text, kinds)
                typed = True
            except FormulaError:
                typed = False
            grid = _grid(text)
            if typed:
                accepted += 1
                names = sorted(n for n in grid if n in text)
                for combo in itertools.product(*(grid[n] for n in names)):
                    values = {n: grid[n][0] for n in grid} | dict(zip(names, combo))
                    got = run(text, values)
                    try:
                        want = ("value", _reference(text, values, kinds))
                    except ZeroDivisionError:
                        want = ("error", "division by zero")
                    assert got == want, (text, values, got, want)
            for _ in range(2):
                missing = rnd.sample(sorted(grid), rnd.randint(1, 2))
                base = {n: rnd.choice(v) for n, v in grid.items()}
                got = run(text, {**base, **{n: None for n in missing}})
                if got[0] != "value":
                    continue
                resolved += 1
                for fill in itertools.product(*(grid[n] for n in missing)):
                    assert run(text, {**base, **dict(zip(missing, fill))}) == got, (text, missing, base, fill, got)
    assert accepted > 300 and resolved > 300, (accepted, resolved)        # the test really exercises both


