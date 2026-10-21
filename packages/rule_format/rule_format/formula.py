"""The small, fixed formula language rules are written in.

Formulas use everyday math notation and are parsed with Python's own parser,
then checked against a strict whitelist. Anything not listed here is rejected.

    rear_yard >= max(min(0.25 * lot_depth, 50), 20)
    use in ["one_family_detached", "church"]
    parking_spaces >= (1 if sleeping_rooms <= 3 else 2)

Allowed: numbers, quoted text, measure names, + - * / (numbers only), comparisons
(< <= > >= between numbers; == != between anything), `in` / `not in` a [list],
and / or / not, `a if condition else b`, min() and max() of two or more numbers.
A yes/no measure is used on its own: `adu_separate_entrance`, `not accessory_in_front_yard`.

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


def _kind_type(kind) -> str | None:
    """A measure's description as a formula type: number, text or bool (None: no description)."""
    if kind == "number":
        return "number"
    if kind == "boolean":
        return "bool"
    if kind == "text" or isinstance(kind, (set, frozenset)):
        return "text"
    return None


def type_of(text: str, kinds: dict) -> str:
    """The formula's type (number, text, bool), worked out from the measures' descriptions without any values:
    raises FormulaError where it is ill-typed for every value (a number compared with text, a number used as
    true/false, true/false in arithmetic, a measure with no description). Rule files are checked with it, so
    no frozen rule can be ill-typed; the evaluation checks the same at run time as a defence."""
    return _type(parse(text).body, kinds, text)


def _type(node, kinds, text):
    def bad(why):
        raise FormulaError(f"{why}: {text!r}")
    match node:
        case ast.Constant(value=v):
            return "text" if type(v) is str else "number"
        case ast.Name(id=name):
            t = _kind_type(kinds.get(name))
            if t is None:
                bad(f"unknown measure '{name}'")
            return t
        case ast.List(elts=items) | ast.Tuple(elts=items):
            types = {_type(i, kinds, text) for i in items}
            if len(types) > 1:
                bad("a list mixes kinds of values")
            return "list of " + (types.pop() if types else "number")
        case ast.BinOp(left=l, right=r):
            if _type(l, kinds, text) != "number" or _type(r, kinds, text) != "number":
                bad("arithmetic needs numbers")
            return "number"
        case ast.UnaryOp(op=ast.USub(), operand=x):
            if _type(x, kinds, text) != "number":
                bad("a minus sign needs a number")
            return "number"
        case ast.UnaryOp(op=ast.Not(), operand=x):
            if _type(x, kinds, text) != "bool":
                bad("'not' needs a true/false test")
            return "bool"
        case ast.BoolOp(values=parts):
            if any(_type(x, kinds, text) != "bool" for x in parts):
                bad("and/or need true/false tests")
            return "bool"
        case ast.Compare(left=l, ops=ops, comparators=rights):
            types = [_type(x, kinds, text) for x in (l, *rights)]
            for op, a, b in zip(ops, types, types[1:]):
                if type(op) in _ORDERING and (a != "number" or b != "number"):
                    bad("<, <=, >, >= compare numbers")
                if type(op) in _EQUALITY and a != b:
                    bad(f"== and != compare values of one kind ({a} vs {b})")
                if type(op) in _MEMBERSHIP and b != "list of " + a:
                    bad(f"'in' needs a list of the same kind ({a})")
            return "bool"
        case ast.IfExp(test=t, body=a, orelse=b):
            if _type(t, kinds, text) != "bool":
                bad("an if needs a true/false test")
            ta, tb = _type(a, kinds, text), _type(b, kinds, text)
            if ta != tb:
                bad("both branches of an if must give one kind of value")
            return ta
        case ast.Call(args=args):
            if any(_type(a, kinds, text) != "number" for a in args):
                bad("min() and max() take numbers")
            return "number"
    bad(f"unsupported expression {type(node).__name__}")


def is_condition(text: str) -> bool:
    """True if the formula can only produce true/false (a comparison, and/or, or not), or is a
    single measure name (true/false only if that measure is a yes/no one: see bare_name)."""
    body = parse(text).body
    return (isinstance(body, _CONDITIONS) or isinstance(body, ast.UnaryOp) and isinstance(body.op, ast.Not)
            or isinstance(body, ast.Name))


def bare_name(text: str) -> str | None:
    """The measure name if the whole formula is one measure (a yes/no test on its own), else None."""
    body = parse(text).body
    return body.id if isinstance(body, ast.Name) else None


def names(text: str) -> set[str]:
    """Measure names used in a formula (function names excluded)."""
    tree = parse(text)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called


def strings(text: str) -> set[str]:
    """Quoted text values used in a formula (e.g. use names)."""
    return {n.value for n in ast.walk(parse(text)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def compared_strings(text: str) -> list[tuple[str | None, str]]:
    """(the measure it is compared with, or None; the quoted value) for each quoted text value in a formula:
    'use in ["a", "b"] and district == "R-1b"' -> [("use", "a"), ("use", "b"), ("district", "R-1b")]."""
    tree, out, seen = parse(text), [], set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        names = [o.id for o in operands if isinstance(o, ast.Name)]
        for o in operands:
            values = o.elts if isinstance(o, (ast.List, ast.Tuple, ast.Set)) else [o]
            for v in values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    seen.add(id(v))
                    out.append((names[0] if len(names) == 1 else None, v.value))
    out += [(None, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in seen]
    return out


def numbers(text: str) -> list[float]:
    """Number constants written in a formula (each must come from the rule's sources)."""
    return [n.value for n in ast.walk(parse(text)) if isinstance(n, ast.Constant) and type(n.value) in (int, float)]


def evaluate(text: str, values: dict, kinds: dict):
    """Evaluate a formula. Raises MissingMeasure or EvaluationError when it can't.

    kinds describes every measure the formula may use: "number" (a non-negative number:
    lengths, areas, counts), "boolean" (a yes/no fact: True or False), or the set of text values
    allowed (e.g. the city's use names).
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
    """A value that depends on a missing or unusable measure (the first one named), with the type the expression
    has (number, text or bool; None if the measure has no description): an error every value would give (a
    number compared with text, a number used as true/false) is raised, never hidden under the unknown."""

    def __init__(self, name, kind=None):
        self.name, self.kind = name, kind


def _typed(x, want: str, what: str):
    """x, checked to be of type `want` (known, or an unknown of that type); an error otherwise."""
    if isinstance(x, _Unknown):
        if x.kind is not None and x.kind != want:
            raise EvaluationError(f"{what} needs a {'true/false test' if want == 'bool' else want}: "
                                  f"{x.name} gives a {x.kind}")
        return x
    return _number(x) if want == "number" else _boolean(x) if want == "bool" else x


def _as_number(x):
    """x as a number, or the unknown it is; an unknown of another type where a number belongs is an error."""
    return _typed(x, "number", "arithmetic")


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


def _kind(x):
    return "text" if type(x) is str else "number" if type(x) in (int, float, Fraction) else None


def _measure(name, values, kinds):
    """Usable only if present and fitting its description: a finite, non-negative number,
    or one of the allowed text values. Anything else (including no description) is unusable."""
    v, kind = values.get(name), kinds.get(name)
    if kind == "number" and type(v) in (int, float) and _finite(v) and v >= 0:
        return _exact(v)
    if kind == "boolean" and type(v) is bool:
        return v
    if isinstance(kind, (set, frozenset)) and _kind(v) == "text" and v in kind:
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
            return _unknown(*out) or out
        case ast.BinOp(left=l, op=op, right=r):
            a, b = _as_number(_eval(l, values, kinds)), _as_number(_eval(r, values, kinds))
            if isinstance(op, ast.Div) and not isinstance(b, _Unknown) and b == 0:
                raise EvaluationError("division by zero")         # whatever the numerator is
            if isinstance(op, ast.Div) and isinstance(b, _Unknown):
                raise MissingMeasure(b.name)    # it could be zero: no answer can be sure without it
            if u := _unknown(a, b):
                return _Unknown(u.name, "number")
            return _number(_ARITHMETIC[type(op)](a, b))
        case ast.UnaryOp(op=ast.USub(), operand=x):
            a = _as_number(_eval(x, values, kinds))
            return a if isinstance(a, _Unknown) else -a
        case ast.UnaryOp(op=ast.Not(), operand=x):
            a = _typed(_eval(x, values, kinds), "bool", "'not'")
            return a if isinstance(a, _Unknown) else not a
        case ast.BoolOp(op=op, values=parts):
            # Every part is evaluated (a value that can't be evaluated is never hidden); unknowns are Kleene's.
            results = [_typed(_eval(p, values, kinds), "bool", "and/or") for p in parts]
            known = [r for r in results if not isinstance(r, _Unknown)]
            decisive = isinstance(op, ast.Or)        # True decides an or, False an and
            if decisive in known:
                return decisive
            u = _unknown(*results)
            return _Unknown(u.name, "bool") if u else (not decisive)
        case ast.Compare(left=l, ops=ops, comparators=rights):
            operands = [_eval(x, values, kinds) for x in (l, *rights)]
            # A chain is an and of its links: every link checked, so a bad value can't hide behind a false one.
            links = [_link(op, a, b) for op, a, b in zip(ops, operands, operands[1:])]
            if False in [x for x in links if not isinstance(x, _Unknown)]:
                return False
            u = _unknown(*links)
            return _Unknown(u.name, "bool") if u else True
        case ast.IfExp(test=t, body=a, orelse=b):
            test = _typed(_eval(t, values, kinds), "bool", "an if")
            if not isinstance(test, _Unknown):
                return _eval(a, values, kinds) if test else _eval(b, values, kinds)
            yes, no = _eval(a, values, kinds), _eval(b, values, kinds)     # the same either way: known
            if not _unknown(yes, no) and _kind(yes) == _kind(no) and yes == no:
                return yes
            kind = next((x.kind for x in (yes, no) if isinstance(x, _Unknown)), None) or \
                next((_kind(x) if _kind(x) != "text" else "text" for x in (yes, no) if not isinstance(x, _Unknown)), None)
            return _Unknown(test.name, "bool" if type(yes) is bool else kind)
        case ast.Call(func=ast.Name(id=f), args=args):
            out = [_as_number(_eval(a, values, kinds)) for a in args]
            if u := _unknown(*out):
                return _Unknown(u.name, "number")
            return FUNCTIONS[f](*out)
    raise FormulaError(f"unsupported expression: {ast.dump(node)}")


def _link(op, a, b):
    """One comparison of a chain: true, false, or the unknown it depends on (after checking the types fit: a
    number ordered against text, or compared for equality with it, is an error whatever the values are)."""
    if type(op) in _ORDERING:
        a, b = _as_number(a), _as_number(b)
    if u := _unknown(a, b):
        kinds_ = {x.kind if isinstance(x, _Unknown) else ("bool" if type(x) is bool else _kind(x))
                  for x in ([a] + (b if isinstance(b, list) else [b]))}
        if None not in kinds_ and len(kinds_) > 1:
            raise EvaluationError(f"can't compare {_shown(a) if not isinstance(a, _Unknown) else a.name} with "
                                  f"{_shown(b) if not isinstance(b, _Unknown) else b.name}: different kinds")
        return _Unknown(u.name, "bool")
    return _compare(op, a, b)


def _compare(op, a, b):
    if type(op) in _ORDERING:
        return _ORDERING[type(op)](_number(a), _number(b))
    others = b if type(op) in _MEMBERSHIP else [b]
    if _kind(a) is None or any(_kind(x) != _kind(a) for x in others):
        raise EvaluationError(f"can't compare {_shown(a)!r} with {_shown(b)!r}: different kinds")
    return (_EQUALITY | _MEMBERSHIP)[type(op)](a, b)


def _boolean(x):
    if type(x) is not bool:
        raise EvaluationError(f"expected true/false, got {_shown(x)!r}")
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
