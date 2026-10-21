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

    A missing or unusable measure is unknown, and unknowns follow three-valued (Kleene) logic: True or unknown is
    True, False and unknown is False (the result is the same whatever the measure turns out to be), and anything
    else that depends on an unknown is unknown, raised as MissingMeasure. So a missing measure can never be hidden
    where it could change the result, and never makes a result unknown where it can't.
    """
    body = parse(text).body
    result = _eval(body, values, kinds)
    if isinstance(result, _Unknown):
        raise MissingMeasure(result.name)
    return _plain(result, _floats_in(body, values))


class _Unknown:
    """A value that depends on a missing or unusable measure (the first one named), and what kind of value that
    measure holds ("number", or text): a number compared with a text measure is wrong whatever its value."""

    def __init__(self, name, kind=None):
        self.name, self.kind = name, kind


def _as_number(x):
    """x as a number, or the unknown it is; an unknown text measure where a number belongs is an error."""
    if isinstance(x, _Unknown):
        if x.kind is not None and x.kind != "number":
            raise EvaluationError(f"{x.name} isn't a number")
        return x
    return _number(x)


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
        raise EvaluationError(f"expected a number, got {x!r}")
    if not _finite(x):
        raise EvaluationError(f"not a finite number: {x!r}")
    return x


def _kind(x):
    return "text" if type(x) is str else "number" if type(x) in (int, float, Fraction) else None


def _measure(name, values, kinds):
    """Usable only if present and fitting its description: a finite, non-negative number,
    or one of the allowed text values. Anything else (including no description) is unusable."""
    v, kind = values.get(name), kinds.get(name)
    if kind == "number" and type(v) in (int, float) and _finite(v) and v >= 0:
        return _exact(v)
    if isinstance(kind, (set, frozenset)) and _kind(v) == "text" and v in kind:
        return v
    return _Unknown(name, "number" if kind == "number" else "text" if isinstance(kind, (set, frozenset)) else None)


def _eval(node, values, kinds):
    match node:
        case ast.Constant(value=v):
            return _exact(v)
        case ast.Name(id=name):
            return _measure(name, values, kinds)
        case ast.List(elts=items) | ast.Tuple(elts=items):
            out = [_eval(i, values, kinds) for i in items]
            return _unknown(*out) or out
        case ast.BinOp(left=l, op=op, right=r):
            a, b = _as_number(_eval(l, values, kinds)), _as_number(_eval(r, values, kinds))
            if u := _unknown(a, b):
                return u
            if isinstance(op, ast.Div) and b == 0:
                raise EvaluationError("division by zero")
            return _number(_ARITHMETIC[type(op)](a, b))
        case ast.UnaryOp(op=ast.USub(), operand=x):
            a = _as_number(_eval(x, values, kinds))
            return a if isinstance(a, _Unknown) else -a
        case ast.UnaryOp(op=ast.Not(), operand=x):
            a = _eval(x, values, kinds)
            return a if isinstance(a, _Unknown) else not _boolean(a)
        case ast.BoolOp(op=op, values=parts):
            # Every part is evaluated (a value that can't be evaluated is never hidden); unknowns are Kleene's.
            results = [_eval(p, values, kinds) for p in parts]
            known = [_boolean(r) for r in results if not isinstance(r, _Unknown)]
            decisive = isinstance(op, ast.Or)        # True decides an or, False an and
            if decisive in known:
                return decisive
            return _unknown(*results) or (not decisive)
        case ast.Compare(left=l, ops=ops, comparators=rights):
            operands = [_eval(x, values, kinds) for x in (l, *rights)]
            # A chain is an and of its links: every link checked, so a bad value can't hide behind a false one.
            links = [_link(op, a, b) for op, a, b in zip(ops, operands, operands[1:])]
            if False in [x for x in links if not isinstance(x, _Unknown)]:
                return False
            return _unknown(*links) or True
        case ast.IfExp(test=t, body=a, orelse=b):
            test = _eval(t, values, kinds)
            if not isinstance(test, _Unknown):
                return _eval(a, values, kinds) if _boolean(test) else _eval(b, values, kinds)
            yes, no = _eval(a, values, kinds), _eval(b, values, kinds)     # the same either way: known
            if not _unknown(yes, no) and _kind(yes) == _kind(no) and yes == no:
                return yes
            return test
        case ast.Call(func=ast.Name(id=f), args=args):
            out = [_as_number(_eval(a, values, kinds)) for a in args]
            if u := _unknown(*out):
                return u
            return FUNCTIONS[f](*out)
    raise FormulaError(f"unsupported expression: {ast.dump(node)}")


def _link(op, a, b):
    """One comparison of a chain: true, false, or the unknown it depends on (after checking an unknown's kind
    fits: a number ordered against a text measure is an error whatever the text)."""
    if type(op) in _ORDERING:
        a, b = _as_number(a), _as_number(b)
    if u := _unknown(a, b):
        return u
    return _compare(op, a, b)


def _compare(op, a, b):
    if type(op) in _ORDERING:
        return _ORDERING[type(op)](_number(a), _number(b))
    others = b if type(op) in _MEMBERSHIP else [b]
    if _kind(a) is None or any(_kind(x) != _kind(a) for x in others):
        raise EvaluationError(f"can't compare {a!r} with {b!r}: different kinds")
    return (_EQUALITY | _MEMBERSHIP)[type(op)](a, b)


def _boolean(x):
    if type(x) is not bool:
        raise EvaluationError(f"expected true/false, got {_plain(x, x.denominator != 1) if isinstance(x, Fraction) else x!r}")
    return x


def margin(proposed, required, at_least: bool) -> float:
    """How far a measured value is on the complying side of its limit: proposed − required for "at least"
    (>=, >), required − proposed for "at most" (<=, <); negative when it falls short. Worked out exactly, as
    comparisons are, and 0.0 when the two are equal within AT_LIMIT: so a margin shown as "at the limit" and a
    comparison that says it complies can never disagree."""
    a, b = _exact(_number(proposed)), _exact(_number(required))
    if abs(a - b) <= _at_limit(a, b):
        return 0.0
    return float(a - b if at_least else b - a)
