"""The small, fixed formula language rules are written in.

Formulas use everyday math notation and are parsed with Python's own parser,
then checked against a strict whitelist. Anything not listed here is rejected.

    rear_yard >= max(min(0.25 * lot_depth, 50), 20)
    use in ["one_family_detached", "church"]
    parking_spaces >= (1 if sleeping_rooms <= 3 else 2)

Allowed: numbers, quoted text, measure names, + - * / (numbers only), comparisons
(< <= > >= between numbers; == != between anything), `in` / `not in` a [list],
and / or / not, `a if condition else b`, min() and max() of two or more numbers.
"""

import ast
import math
from functools import lru_cache

MAX_LENGTH = 500
FUNCTIONS = {"min": min, "max": max}

_ARITHMETIC = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
               ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
_ORDERING = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
             ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b}
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
                                               or type(node.value) is float and not math.isfinite(node.value)):
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


def evaluate(text: str, values: dict, kinds: dict[str, str] | None = None):
    """Evaluate a formula. Raises MissingMeasure or EvaluationError when it can't.

    kinds maps a measure name to "text" or "number"; a value of the other kind can't be used.
    """
    return _eval(parse(text).body, values, kinds or {})


def _number(x):
    if type(x) not in (int, float):
        raise EvaluationError(f"expected a number, got {x!r}")
    if not math.isfinite(x):
        raise EvaluationError(f"result is not a finite number: {x!r}")
    return x


def _kind(x):
    return "text" if type(x) is str else "number" if type(x) in (int, float) else None


def _measure(name, values, kinds):
    v = values.get(name)
    if v is None or type(v) is float and not math.isfinite(v):
        raise MissingMeasure(name)
    if _kind(v) is None or kinds.get(name, _kind(v)) != _kind(v):
        raise EvaluationError(f"{name} must be {kinds.get(name, 'a number or text')}, got {v!r}")
    return v


def _eval(node, values, kinds):
    match node:
        case ast.Constant(value=v):
            return v
        case ast.Name(id=name):
            return _measure(name, values, kinds)
        case ast.List(elts=items) | ast.Tuple(elts=items):
            return [_eval(i, values, kinds) for i in items]
        case ast.BinOp(left=l, op=op, right=r):
            a, b = _number(_eval(l, values, kinds)), _number(_eval(r, values, kinds))
            if isinstance(op, ast.Div) and b == 0:
                raise EvaluationError("division by zero")
            return _number(_ARITHMETIC[type(op)](a, b))
        case ast.UnaryOp(op=ast.USub(), operand=x):
            return -_number(_eval(x, values, kinds))
        case ast.UnaryOp(op=ast.Not(), operand=x):
            return not _boolean(_eval(x, values, kinds))
        case ast.BoolOp(op=op, values=parts):
            # Evaluate every part so a missing measure is never hidden by short-circuiting.
            results = [_boolean(_eval(p, values, kinds)) for p in parts]
            return all(results) if isinstance(op, ast.And) else any(results)
        case ast.Compare(left=l, ops=ops, comparators=rights):
            operands = [_eval(x, values, kinds) for x in (l, *rights)]
            # Check every link, so a bad value can't hide behind an earlier false one.
            results = [_compare(op, a, b) for op, a, b in zip(ops, operands, operands[1:])]
            return all(results)
        case ast.IfExp(test=t, body=a, orelse=b):
            return _eval(a, values, kinds) if _boolean(_eval(t, values, kinds)) else _eval(b, values, kinds)
        case ast.Call(func=ast.Name(id=f), args=args):
            return FUNCTIONS[f](*(_number(_eval(a, values, kinds)) for a in args))
    raise FormulaError(f"unsupported expression: {ast.dump(node)}")


def _compare(op, a, b):
    if type(op) in _ORDERING:
        return _ORDERING[type(op)](_number(a), _number(b))
    others = b if type(op) in _MEMBERSHIP else [b]
    if _kind(a) is None or any(_kind(x) != _kind(a) for x in others):
        raise EvaluationError(f"can't compare {a!r} with {b!r}: different kinds")
    return (_EQUALITY | _MEMBERSHIP)[type(op)](a, b)


def _boolean(x):
    if type(x) is not bool:
        raise EvaluationError(f"expected true/false, got {x!r}")
    return x
