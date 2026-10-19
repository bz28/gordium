"""The small, fixed formula language rules are written in.

Formulas use everyday math notation and are parsed with Python's own parser,
then checked against a strict whitelist. Anything not listed here is rejected.

    rear_yard >= max(min(0.25 * lot_depth, 50), 20)
    use in ["one_family_detached", "church"]
    1 if sleeping_rooms <= 3 else 2

Allowed: numbers, quoted text, lists, measure names, + - * /, comparisons
(< <= > >= == != in, not in), and / or / not, `a if cond else b`, min(), max().
"""

import ast
from functools import lru_cache

FUNCTIONS = {"min": min, "max": max}

_BINOPS = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
           ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b}
_CMPOPS = {ast.Lt: lambda a, b: a < b, ast.LtE: lambda a, b: a <= b,
           ast.Gt: lambda a, b: a > b, ast.GtE: lambda a, b: a >= b,
           ast.Eq: lambda a, b: a == b, ast.NotEq: lambda a, b: a != b,
           ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b}
_ALLOWED = (ast.Expression, ast.Constant, ast.Name, ast.Load, ast.List, ast.Tuple,
            ast.BinOp, ast.UnaryOp, ast.USub, ast.Not, ast.BoolOp, ast.And, ast.Or,
            ast.Compare, ast.IfExp, ast.Call, *_BINOPS, *_CMPOPS)


class FormulaError(ValueError):
    """The formula is not valid in the formula language."""


class MissingMeasure(LookupError):
    """A measure the formula needs was not provided. Checkers report this as 'needs review'."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


@lru_cache(maxsize=None)
def parse(text: str) -> ast.Expression:
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"cannot read formula {text!r}: {e.msg}") from None
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise FormulaError(f"{type(node).__name__} is not allowed in formulas: {text!r}")
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS) or node.keywords:
                raise FormulaError(f"only {sorted(FUNCTIONS)} can be called: {text!r}")
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, float, str)):
            raise FormulaError(f"only numbers and quoted text are allowed: {text!r}")
    return tree


def names(text: str) -> set[str]:
    """Measure names used in a formula (function names excluded)."""
    tree = parse(text)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called


def strings(text: str) -> set[str]:
    """Quoted text values used in a formula (e.g. use names)."""
    return {n.value for n in ast.walk(parse(text)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def evaluate(text: str, values: dict):
    """Evaluate a formula. Raises MissingMeasure if a needed value is absent or None."""
    return _eval(parse(text).body, values)


def _eval(node, values):
    match node:
        case ast.Constant(value=v):
            return v
        case ast.Name(id=name):
            if values.get(name) is None:
                raise MissingMeasure(name)
            return values[name]
        case ast.List(elts=items) | ast.Tuple(elts=items):
            return [_eval(i, values) for i in items]
        case ast.BinOp(left=l, op=op, right=r):
            return _BINOPS[type(op)](_eval(l, values), _eval(r, values))
        case ast.UnaryOp(op=ast.USub(), operand=x):
            return -_eval(x, values)
        case ast.UnaryOp(op=ast.Not(), operand=x):
            return not _eval(x, values)
        case ast.BoolOp(op=op, values=parts):
            # Evaluate every part so a missing measure is never hidden by short-circuiting.
            results = [_eval(p, values) for p in parts]
            return all(results) if isinstance(op, ast.And) else any(results)
        case ast.Compare(left=l, ops=ops, comparators=rights):
            operands = [_eval(x, values) for x in (l, *rights)]
            return all(_CMPOPS[type(op)](a, b) for op, a, b in zip(ops, operands, operands[1:]))
        case ast.IfExp(test=t, body=a, orelse=b):
            return _eval(a, values) if _eval(t, values) else _eval(b, values)
        case ast.Call(func=ast.Name(id=f), args=args):
            return FUNCTIONS[f](*(_eval(a, values) for a in args))
    raise FormulaError(f"unsupported expression: {ast.dump(node)}")
