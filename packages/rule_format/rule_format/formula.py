"""The small, fixed formula language rules are written in.

Formulas use everyday math notation and are parsed with Python's own parser,
then checked against a strict whitelist. Anything not listed here is rejected.

    rear_yard >= max(min(0.25 * lot_depth, 50), 20)
    use in ["one_family_detached", "church"]
    parking_spaces >= (1 if sleeping_rooms <= 3 else 2)

Allowed: numbers, quoted text, measure names, + - * / (numbers only), comparisons
(< <= > >= between numbers; == != between anything), `in` / `not in` a [list],
and / or / not, `a if condition else b`, min() and max() of two or more numbers.

Numbers are worked out exactly, as the decimals they are written as (0.2 * 132 is 26.4, not the binary
26.400000000000002), and a comparison treats two numbers within AT_LIMIT of each other as equal: a design
exactly at a limit complies with "at least" / "at most" (and not with "more than" / "less than"), even when
its measurement carries float noise from the geometry. AT_LIMIT is a millionth of a foot (or a billionth of
the number, if larger): far below anything measurable, so a real violation always fails.
"""

import ast
import math
from fractions import Fraction
from functools import lru_cache

MAX_LENGTH = 500
FUNCTIONS = {"min": min, "max": max}
AT_LIMIT_ABSOLUTE = Fraction(1, 10 ** 6)       # two numbers this close count as equal (ft, sq ft, counts)
AT_LIMIT_RELATIVE = Fraction(1, 10 ** 9)       # ... or this close relative to the larger, for big numbers

_ARITHMETIC = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
               ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}


def _at_limit(a, b) -> Fraction:
    return max(AT_LIMIT_ABSOLUTE, AT_LIMIT_RELATIVE * max(abs(a), abs(b)))


_ORDERING = {ast.Lt: lambda a, b: b - a > _at_limit(a, b), ast.LtE: lambda a, b: a - b <= _at_limit(a, b),
             ast.Gt: lambda a, b: a - b > _at_limit(a, b), ast.GtE: lambda a, b: b - a <= _at_limit(a, b)}
_EQUALITY = {ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b}
_MEMBERSHIP = {ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
_ALLOWED = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.List, ast.Tuple,
            ast.BinOp, ast.UnaryOp, ast.USub, ast.Not, ast.BoolOp, ast.And, ast.Or,
            ast.Compare, ast.IfExp, ast.Call,
            *_ARITHMETIC, *_ORDERING, *_EQUALITY, *_MEMBERSHIP)
_CONDITIONS = (ast.Compare, ast.BoolOp)  # plus `not ...`: formulas that can only be true/false


class FormulaError(ValueError):
    """The formula is not valid in the formula language."""


class EvaluationError(ValueError):
    """The formula is valid but these values can't be evaluated (wrong type, divide by zero...)."""


class MissingMeasure(LookupError):
    """A needed measurement is absent or unusable (None, NaN, infinite). Checkers report 'needs review'."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


@lru_cache(maxsize=None)
def parse(text: str) -> ast.Expression:
    if not isinstance(text, str) or not text.strip():
        raise FormulaError(f"formula must be non-empty text: {text!r}")
    if len(text) > MAX_LENGTH:
        raise FormulaError(f"formula longer than {MAX_LENGTH} characters")
    try:
        tree = ast.parse(text, mode="eval")
        nodes = list(ast.walk(tree))
    except SyntaxError as e:
        raise FormulaError(f"cannot read formula {text!r}: {e.msg}") from None
    except (RecursionError, MemoryError):
        raise FormulaError(f"formula nested too deeply: {text[:40]!r}…") from None
    for node in nodes:
        if not isinstance(node, _ALLOWED):
            raise FormulaError(f"{type(node).__name__} is not allowed in formulas: {text!r}")
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float, str)
                                               or type(node.value) is not str and not _finite(node.value)):
            raise FormulaError(f"only finite numbers and quoted text are allowed: {text!r}")
        if isinstance(node, ast.Call) and not (
                isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS
                and len(node.args) >= 2 and not node.keywords):
            raise FormulaError(f"only min() / max() of two or more values can be called: {text!r}")
        if isinstance(node, ast.Compare):
            for op, right in zip(node.ops, node.comparators):
                if type(op) in _MEMBERSHIP and not isinstance(right, (ast.List, ast.Tuple)):
                    raise FormulaError(f"'in' needs a [list] on its right: {text!r}")
    return tree


NUMBER, TEXT, BOOL = "number", "text", "bool"       # the three kinds of value a formula works with
ANY_LIST = "list"                                     # an empty [list]: of no kind yet


class _Mismatch(Exception):
    """An operator given operands of kinds it doesn't take (wrong for every value)."""


class _Undescribed(Exception):
    """A measure with no description: nothing about it can be told."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


def _kind_type(kind) -> str | None:
    """A measure's description as a formula type: number, text or bool (None: no description)."""
    if kind == "number":
        return NUMBER
    if kind == "boolean":
        return BOOL
    if kind == "text" or isinstance(kind, (set, frozenset)):
        return TEXT
    return None


def result_type(rule: str, operands: list[str]) -> str:
    """THE type rules of the language, one place, used by both the rule-file check (type_of) and the evaluation:
    given an operator and its operands' kinds, the kind of its result, or _Mismatch. The language is kept small:
    true/false tests combine only with and / or / not (never ==, !=, in, arithmetic or an if's branches).

        arithmetic (+ - * /), minus, min(), max()    numbers            -> number
        <  <=  >  >=                                  two numbers        -> true/false
        ==  !=                                        two numbers, or two texts -> true/false
        in / not in [list]                            a number or text, and a list of that kind -> true/false
        not, and, or                                  true/false tests   -> true/false
        a if test else b                              a true/false test, and two numbers or two texts -> that kind
        [a, b, ...]                                   numbers, or texts  -> a list of that kind
    """
    def need(ok, why):
        if not ok:
            raise _Mismatch(why)

    if rule in ("arithmetic", "minus", "min/max"):
        need(all(t == NUMBER for t in operands),
             {"arithmetic": "arithmetic needs numbers", "minus": "a minus sign needs a number",
              "min/max": "min() and max() take numbers"}[rule])
        return NUMBER
    if rule == "ordering":
        need(operands == [NUMBER, NUMBER], "<, <=, >, >= compare numbers")
        return BOOL
    if rule == "equality":
        need(operands[0] in (NUMBER, TEXT) and operands[0] == operands[1],
             "== and != compare two numbers or two texts (true/false tests combine with and/or/not)")
        return BOOL
    if rule == "membership":
        need(operands[0] in (NUMBER, TEXT) and operands[1] in ("list of " + operands[0], ANY_LIST),
             "'in' needs a number or text and a list of the same kind")
        return BOOL
    if rule in ("not", "and/or"):
        need(all(t == BOOL for t in operands),
             "'not' needs a true/false test" if rule == "not" else "and/or need true/false tests")
        return BOOL
    if rule == "if":
        need(operands[0] == BOOL, "an if needs a true/false test")
        need(operands[1] in (NUMBER, TEXT) and operands[1] == operands[2],
             "both branches of an if must give two numbers or two texts")
        return operands[1]
    if rule == "list":
        need(all(t in (NUMBER, TEXT) for t in operands) and len(set(operands)) <= 1,
             "a list holds numbers, or texts, not a mix")
        return "list of " + operands[0] if operands else ANY_LIST
    raise _Mismatch(f"unsupported expression {rule}")


def _rule_of(node, op=None) -> str:
    """Which of the type rules an expression (or one comparison of a chain, `op`) follows."""
    op = op if op is not None else getattr(node, "op", None)
    if isinstance(node, ast.BinOp):
        return "arithmetic"
    if isinstance(node, ast.UnaryOp):
        return "minus" if isinstance(op, ast.USub) else "not"
    if isinstance(node, ast.BoolOp):
        return "and/or"
    if isinstance(node, ast.Call):
        return "min/max"
    if isinstance(node, ast.IfExp):
        return "if"
    if isinstance(node, (ast.List, ast.Tuple)):
        return "list"
    return ("ordering" if type(op) in _ORDERING else "equality" if type(op) in _EQUALITY else "membership")


def type_of(text: str, kinds: dict) -> str:
    """The formula's kind (number, text, bool), worked out from the measures' descriptions without any values,
    by the language's type rules (result_type). Raises FormulaError where it is wrong for every value (a number
    compared with text, a number used as true/false, true/false compared or in arithmetic) or names a measure with
    no description. Rule files are checked with it, so no frozen rule can be ill-typed; evaluate() checks it too,
    before any value is looked at, so no error every value would give can hide behind a missing measure."""
    try:
        return _type(parse(text).body, kinds)
    except _Undescribed as e:
        raise FormulaError(f"unknown measure '{e.name}' in {text!r}") from None
    except _Mismatch as e:
        raise FormulaError(f"{e}: {text!r}") from None


def _type(node, kinds) -> str:
    match node:
        case ast.Constant(value=v):
            return TEXT if type(v) is str else NUMBER
        case ast.Name(id=name):
            t = _kind_type(kinds.get(name))
            if t is None:
                raise _Undescribed(name)
            return t
        case ast.Compare(left=l, ops=ops, comparators=rights):
            types = [_type(x, kinds) for x in (l, *rights)]
            for op, a, b in zip(ops, types, types[1:]):
                result_type(_rule_of(node, op), [a, b])
            return BOOL
        case ast.List(elts=parts) | ast.Tuple(elts=parts) | ast.Call(args=parts) | ast.BoolOp(values=parts):
            return result_type(_rule_of(node), [_type(x, kinds) for x in parts])
        case ast.BinOp(left=l, right=r):
            return result_type("arithmetic", [_type(l, kinds), _type(r, kinds)])
        case ast.UnaryOp(operand=x):
            return result_type(_rule_of(node), [_type(x, kinds)])
        case ast.IfExp(test=t, body=a, orelse=b):
            return result_type("if", [_type(t, kinds), _type(a, kinds), _type(b, kinds)])
    raise _Mismatch(f"unsupported expression {type(node).__name__}")


def is_condition(text: str) -> bool:
    """True if the formula can only produce true/false (a comparison, and/or, or not)."""
    body = parse(text).body
    return isinstance(body, _CONDITIONS) or isinstance(body, ast.UnaryOp) and isinstance(body.op, ast.Not)


def names(text: str) -> set[str]:
    """Measure names used in a formula (function names excluded)."""
    tree = parse(text)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called


def strings(text: str) -> set[str]:
    """Quoted text values used in a formula (e.g. use names)."""
    return {n.value for n in ast.walk(parse(text)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def evaluate(text: str, values: dict, kinds: dict):
    """Evaluate a formula. Raises MissingMeasure or EvaluationError when it can't.

    kinds describes every measure the formula may use: "number" (a non-negative number:
    lengths, areas, counts) or the set of text values allowed (e.g. the city's use names).
    Fails closed: a measure with no description, or a value that doesn't fit, is unusable.
    Worked out exactly (see the module docstring); a number comes back as a float (an int where plain Python
    arithmetic would have given one).

    First the formula's types are checked against the measures' descriptions (result_type, the same rules the
    rule files are checked by): one that is wrong for every value is an EvaluationError before any value is looked
    at, and a measure with no description is missing. Then a missing or unusable measure is unknown, and unknowns
    follow three-valued (Kleene) logic: True or unknown is True, False and unknown is False (the result is the same
    whatever the measure turns out to be), and anything else that depends on an unknown is unknown, raised as
    MissingMeasure. Every part is worked out, so an error a value gives (division by zero) is never hidden. A
    division by an unknown is MissingMeasure: it could be by zero.
    """
    body = parse(text).body
    try:
        _type(body, kinds)
    except _Undescribed as e:
        raise MissingMeasure(e.name) from None
    except _Mismatch as e:
        raise EvaluationError(str(e)) from None
    result = _eval(body, values, kinds)
    if isinstance(result, _Unknown):
        raise MissingMeasure(result.name)
    return _plain(result, _floats_in(body, values))


class _Unknown:
    """A value that depends on a missing or unusable measure (the first one named), and its kind (by the type
    rules, as every value's)."""

    def __init__(self, name, kind):
        self.name, self.kind = name, kind


def _value_type(x) -> str:
    """A value's kind, for the type rules: the same kinds type_of works with."""
    if isinstance(x, _Unknown):
        if x.kind is None:
            raise MissingMeasure(x.name)
        return x.kind
    if type(x) is bool:
        return BOOL
    if type(x) in (int, float, Fraction):
        return NUMBER
    if type(x) is str:
        return TEXT
    if isinstance(x, list):
        return result_type("list", [_value_type(i) for i in x])
    raise EvaluationError(f"not a value: {_shown(x)!r}")


def _checked(rule: str, operands: list):
    """The result kind of `rule` on these operand values, by the type rules (a defence: type_of has checked
    them); EvaluationError if they don't fit."""
    try:
        return result_type(rule, [_value_type(x) for x in operands])
    except _Mismatch as e:
        raise EvaluationError(str(e)) from None


def _shown(x):
    """A value as written in a message: an exact number as a plain one (50, 0.25), anything else as it is."""
    if isinstance(x, Fraction):
        return _plain(x, x.denominator != 1)
    if isinstance(x, list):
        return [_shown(i) for i in x]
    return x


def _unknown(*xs):
    return next((x for x in xs if isinstance(x, _Unknown)), None)


def _exact(x):
    """A number as the decimal it is written as (a float by its shortest repr: 0.2 -> 1/5), else as it is."""
    if type(x) is float:
        return Fraction(repr(x))
    if type(x) is int:
        return Fraction(x)
    return x


def _floats_in(body, values) -> bool:
    """Whether plain Python would have given a float: a float number or measurement, or a division, anywhere."""
    return any(isinstance(n, ast.Constant) and type(n.value) is float
               or isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
               or isinstance(n, ast.Name) and type(values.get(n.id)) is float for n in ast.walk(body))


def _plain(x, floats: bool):
    """A result as callers use it: an exact number back to a float, or to an int where plain Python gave one."""
    if isinstance(x, Fraction):
        return int(x) if not floats and x.denominator == 1 else float(x)
    if isinstance(x, list):
        return [_plain(i, floats) for i in x]
    return x


def _finite(x) -> bool:
    try:
        return math.isfinite(x)
    except OverflowError:  # an integer too large to be a real measurement
        return False


def _number(x):
    if type(x) not in (int, float, Fraction):
        raise EvaluationError(f"expected a number, got {_shown(x)!r}")
    if not _finite(x):
        raise EvaluationError(f"not a finite number: {_shown(x)!r}")
    return x


def _measure(name, values, kinds):
    """Usable only if present and fitting its description: a finite, non-negative number,
    or one of the allowed text values. Anything else is unknown, of the kind its description gives."""
    v, kind = values.get(name), kinds.get(name)
    if kind == "number" and type(v) in (int, float) and _finite(v) and v >= 0:
        return _exact(v)
    if isinstance(kind, (set, frozenset)) and type(v) is str and v in kind:
        return v
    return _Unknown(name, _kind_type(kind))


def _eval(node, values, kinds):
    match node:
        case ast.Constant(value=v):
            return _exact(v)
        case ast.Name(id=name):
            return _measure(name, values, kinds)
        case ast.List(elts=items) | ast.Tuple(elts=items):
            out = [_eval(i, values, kinds) for i in items]
            kind = _checked("list", out)
            return _Unknown(u.name, kind) if (u := _unknown(*out)) else out
        case ast.BinOp(left=l, op=op, right=r):
            a, b = _eval(l, values, kinds), _eval(r, values, kinds)
            _checked("arithmetic", [a, b])
            if isinstance(op, ast.Div) and not isinstance(b, _Unknown) and b == 0:
                raise EvaluationError("division by zero")         # whatever the numerator is
            if isinstance(op, ast.Div) and isinstance(b, _Unknown):
                raise MissingMeasure(b.name)    # it could be zero: no answer can be sure without it
            if u := _unknown(a, b):
                return _Unknown(u.name, NUMBER)
            return _number(_ARITHMETIC[type(op)](a, b))
        case ast.UnaryOp(op=op, operand=x):
            a = _eval(x, values, kinds)
            kind = _checked(_rule_of(node), [a])
            if isinstance(a, _Unknown):
                return _Unknown(a.name, kind)
            return -a if isinstance(op, ast.USub) else not a
        case ast.BoolOp(op=op, values=parts):
            # Every part is worked out (an error is never hidden); unknowns follow Kleene's logic.
            results = [_eval(p, values, kinds) for p in parts]
            _checked("and/or", results)
            known = [r for r in results if not isinstance(r, _Unknown)]
            decisive = isinstance(op, ast.Or)        # True decides an or, False an and
            if decisive in known:
                return decisive
            u = _unknown(*results)
            return _Unknown(u.name, BOOL) if u else (not decisive)
        case ast.Compare(left=l, ops=ops, comparators=rights):
            operands = [_eval(x, values, kinds) for x in (l, *rights)]
            # A chain is an and of its links: every link checked, so a bad value can't hide behind a false one.
            links = [_link(node, op, a, b) for op, a, b in zip(ops, operands, operands[1:])]
            if False in [x for x in links if not isinstance(x, _Unknown)]:
                return False
            u = _unknown(*links)
            return _Unknown(u.name, BOOL) if u else True
        case ast.IfExp(test=t, body=a, orelse=b):
            test = _eval(t, values, kinds)
            if not isinstance(test, _Unknown):         # only the branch taken is worked out, as plain logic does
                chosen = _eval(a if test is True else b, values, kinds)
                _checked("if", [test, chosen, chosen])
                return chosen
            yes, no = _eval(a, values, kinds), _eval(b, values, kinds)
            kind = _checked("if", [test, yes, no])
            if not _unknown(yes, no) and yes == no:   # the same either way: known
                return yes
            return _Unknown(test.name, kind)
        case ast.Call(func=ast.Name(id=f), args=args):
            out = [_eval(a, values, kinds) for a in args]
            _checked("min/max", out)
            if u := _unknown(*out):
                return _Unknown(u.name, NUMBER)
            return FUNCTIONS[f](*out)
    raise FormulaError(f"unsupported expression: {ast.dump(node)}")


def _link(node, op, a, b):
    """One comparison of a chain: true, false, or the unknown it depends on, its kinds checked by the type
    rules first (whatever is unknown)."""
    _checked(_rule_of(node, op), [a, b])
    if _unknown(a, b):
        return _Unknown(_unknown(a, b).name, BOOL)
    if type(op) in _ORDERING:
        return _ORDERING[type(op)](a, b)
    return (_EQUALITY | _MEMBERSHIP)[type(op)](a, b)


def margin(proposed, required, at_least: bool) -> float:
    """How far a measured value is on the complying side of its limit: proposed − required for "at least"
    (>=, >), required − proposed for "at most" (<=, <); negative when it falls short. Worked out exactly, as
    comparisons are, and 0.0 when the two are equal within AT_LIMIT: so a margin shown as "at the limit" and a
    comparison that says it complies can never disagree."""
    a, b = _exact(_number(proposed)), _exact(_number(required))
    if abs(a - b) <= _at_limit(a, b):
        return 0.0
    return float(a - b if at_least else b - a)
