"""How results, limits and measured values read on a permit sheet. Display only: no word or number here ever decides
a result (the check's status does). Plain code, no AI.

Numbers are never rounded toward compliance (the checker's own rule, design_checker.present.PRECISION): a value that
must be at least a limit rounds down, one that must be at most a limit rounds up, and the limit the other way.
Lengths print to 1/8 in, in feet and inches from a foot up (2'-8"), in inches below it (7 1/2"); areas to 0.01 sq ft.
"""

import ast
import math

from design_checker import present
from rule_format import formula, parts
from rule_format.rulebook import _kinds

# the four results a sheet prints, word for word, never shortened (plan: "Never a false pass")
RESULT = {present.COMPLIES: "COMPLIES", present.FAILS: "DOES NOT COMPLY", present.REVIEW: "NEEDS REVIEW"}
WAITING = "WAITING"
# most cautious first: what a window's or a sheet's one result is, over several
CAUTION = [present.FAILS, present.REVIEW, present.NOT_CHECKED, present.COMPLIES]
SIGN = {ast.GtE: "min", ast.Gt: "more than", ast.LtE: "max", ast.Lt: "less than"}
MIRROR = {ast.GtE: ast.LtE, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.Lt: ast.Gt}
NOT_MEASURED = "not measured"


class Refused(ValueError):
    """The sheets can't be printed truthfully from what was given: nothing is written, and this says why."""


def result_words(status: str, waiting: str | None = None) -> str:
    """COMPLIES, DOES NOT COMPLY, NEEDS REVIEW, or WAITING: <the check's own reason, in capitals>. Anything else is
    refused, never printed as something kinder."""
    if status in RESULT:
        return RESULT[status]
    if status == present.NOT_CHECKED and isinstance(waiting, str) and waiting.strip():
        return f"{WAITING}: {waiting.strip().upper()}"
    raise Refused(f"a result the sheets don't know how to print: {status!r}"
                  + (" (a 'not checked' item that isn't waiting)" if status == present.NOT_CHECKED else ""))


def worst(statuses) -> str:
    """The most cautious of several results; none at all is NEEDS REVIEW, never complies."""
    got = [s for s in statuses]
    return min(got, key=CAUTION.index) if got else present.REVIEW


# ---- numbers ---------------------------------------------------------------------------------------------------------

def _eighths(inches: float, direction: str) -> int:
    x = inches * 8
    if abs(x - round(x)) < 1e-6:
        return int(round(x))
    return math.floor(x) if direction == "down" else math.ceil(x) if direction == "up" else int(round(x))


def length(inches: float, direction: str = "nearest") -> str:
    """7 1/2", 2'-8", 6'-8 1/8": to 1/8 in, rounded in `direction` (down, up or nearest)."""
    n = _eighths(abs(inches), direction if inches >= 0 else {"down": "up", "up": "down"}.get(direction, direction))
    ft, rest = divmod(n, 96)
    inch, eighth = divmod(rest, 8)
    frac = ""
    if eighth:
        g = math.gcd(eighth, 8)
        frac = f"{eighth // g}/{8 // g}"
    sign = "-" if inches < 0 and n else ""
    if ft == 0:
        return sign + (f"{inch} {frac}\"" if inch and frac else f"{frac}\"" if frac else f"{inch}\"")
    return sign + f"{ft}'-{inch}{' ' + frac if frac else ''}\""


def area(sf: float, direction: str = "nearest") -> str:
    """5.78 sq ft: to 0.01 sq ft, rounded in `direction`."""
    k = sf * 100
    v = (math.floor(k + 1e-9) if direction == "down" else math.ceil(k - 1e-9) if direction == "up" else round(k)) / 100
    return f"{v:,.2f}".rstrip("0").rstrip(".") + " sq ft"


def unit_of(kind: str, measure: str) -> str:
    """A part measure's unit (parts.yaml): in, sf, yes_no, count, text…; "" when the registry doesn't say."""
    return ((parts.registry().get(kind) or {}).get("measures", {}).get(measure) or {}).get("unit", "")


def value(v, unit: str, direction: str = "nearest") -> str:
    """One value as a sheet prints it; None is "not measured"."""
    if v is None:
        return NOT_MEASURED
    if type(v) is bool:
        return "yes" if v else "no"
    if isinstance(v, (int, float)) and math.isfinite(v):
        if unit == "in":
            return length(float(v), direction)
        if unit == "sf":
            return area(float(v), direction)
        if unit == "count":
            return str(int(v)) if float(v).is_integer() else f"{v:g}"
        return f"{v:g}"
    return str(v)


def toward(sign_op, for_proposed: bool) -> str:
    """Rounding that never favours compliance: a measured value that must be at least the limit rounds down, at most
    up; the limit itself the other way (stricter)."""
    at_least = sign_op in (ast.GtE, ast.Gt)
    if for_proposed:
        return "down" if at_least else "up"
    return "up" if at_least else "down"


def measure_words(m: str) -> str:
    """A measure's name as an architect says it: opening_net_clear_area → net clear area."""
    for head in ("opening_", "stair_", "door_", "sleeping_room_", "exterior_door_", "handrail_", "guard_"):
        if m.startswith(head):
            m = m[len(head):]
            break
    return m.replace("_", " ")


# ---- a rule's limit and a part's values, for the code-analysis table ------------------------------------------------

def _comparisons(check: str):
    """The check's parts every one of which must hold (an `and` chain), each (measure, op, limit node) when it is
    `measure <op> limit` (or mirrored), else None for that part; None when the check can't be read."""
    try:
        body = formula.parse(check).body
    except Exception:
        return None

    def every(node):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            return [n for v in node.values for n in every(v)]
        return [node]
    out = []
    for node in every(body):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in SIGN:
            left, op, right = node.left, type(node.ops[0]), node.comparators[0]
            if not isinstance(left, ast.Name) and isinstance(right, ast.Name):
                left, op, right = right, MIRROR[op], left
            out.append((left.id, op, right) if isinstance(left, ast.Name) else None)
        elif isinstance(node, ast.Name):
            out.append((node.id, "yes", None))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) and isinstance(node.operand, ast.Name):
            out.append((node.operand.id, "no", None))
        else:
            out.append(None)
    return out


def in_words(text: str) -> str:
    """A formula with each measure name said in words (riser height - riser variation >= 7): shown, never run."""
    try:
        names = formula.names(text)
    except Exception:
        return text
    for n in sorted(names, key=len, reverse=True):
        text = text.replace(n, measure_words(n))
    return text


def compared(check) -> set[str]:
    """The measures the check compares with a limit (or needs yes/no): what a schedule column is about."""
    got = _comparisons(check) if isinstance(check, str) else None
    return {c[0] for c in got or [] if c}


def required_and_proposed(rule: dict, values: dict, allowed: dict | None = None) -> tuple[str, str]:
    """(what the rule requires, what the part has), as a sheet prints them: "5.7 sq ft min", "5.13 sq ft". Worked out
    from the rule's own formula with the part's values; display only. A check of another shape prints the formula
    itself, and a limit that can't be worked out (a value it needs is missing) prints its formula in words."""
    check, kind = rule.get("check"), rule.get("for_each")
    if not isinstance(check, str):
        return "see the code's words (no formula: a person decides)", ""
    got = _comparisons(check)
    if not got or any(c is None for c in got):
        return f"per formula: {in_words(check)}", "; ".join(
            f"{measure_words(m)} {value(values.get(m), unit_of(kind, m))}" for m in sorted(values)) or ""
    kinds = _kinds(allowed or {}, parts.measure_kinds(kind))
    need, have = [], []
    named = len(got) > 1
    for m, op, right in got:
        unit = unit_of(kind, m)
        label = f"{measure_words(m)} " if named else ""
        if op in ("yes", "no"):
            need.append(f"{label}{op}")
            have.append(f"{label}{value(values.get(m), unit)}")
            continue
        try:
            limit = formula.evaluate(ast.unparse(right), values, kinds)
        except Exception:
            limit = None
        if type(limit) in (int, float):
            shown = value(limit, unit, toward(op, False))
            need.append(f"{label}{shown} {SIGN[op]}" if op in (ast.GtE, ast.LtE) else f"{label}{SIGN[op]} {shown}")
        else:
            text = in_words(ast.unparse(right))
            need.append(f"{label}{SIGN[op]} {text}" + (f" {'sq ft' if unit == 'sf' else unit}" if unit in ("in", "sf")
                                                      else ""))
        have.append(f"{label}{value(values.get(m), unit, toward(op, True))}")
    return "; ".join(need), "; ".join(have)
