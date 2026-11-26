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
# (and NOT APPLICABLE: rules the interior description sets aside by saying the house has none of a kind, printed so
# they are never hidden; never a pass)
RESULT = {present.COMPLIES: "COMPLIES", present.FAILS: "DOES NOT COMPLY", present.REVIEW: "NEEDS REVIEW",
          present.NOT_APPLICABLE: "NOT APPLICABLE"}
WAITING = "WAITING"
# most cautious first: what a window's or a sheet's one result is, over several (not applicable is the least: it
# never makes a result kinder than one it sits beside, and a law with nothing else is needs review, egress.py)
CAUTION = [present.FAILS, present.REVIEW, present.NOT_CHECKED, present.COMPLIES, present.NOT_APPLICABLE]
SIGN = {ast.GtE: "min", ast.Gt: "more than", ast.LtE: "max", ast.Lt: "less than"}
MIRROR = {ast.GtE: ast.LtE, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.Lt: ast.Gt}
NOT_MEASURED = "not measured"


class Refused(ValueError):
    """The sheets can't be printed truthfully from what was given: nothing is written, and this says why."""


def result_words(status: str, waiting: str | None = None) -> str:
    """COMPLIES, DOES NOT COMPLY, NEEDS REVIEW, NOT APPLICABLE, or WAITING: <the check's own reason, in capitals>.
    Anything else is refused, never printed as something kinder."""
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


def _finite(v) -> bool:
    """A number a sheet can print in feet and inches or sq ft: finite, and still finite at 1/8 in or 0.01 sq ft (an
    integer too big for a float, or 1e308 times 8, is not)."""
    try:
        return math.isfinite(float(v)) and math.isfinite(float(v) * 100)
    except OverflowError:
        return False


def value(v, unit: str, direction: str = "nearest") -> str:
    """One value as a sheet prints it; None is "not measured"."""
    if v is None:
        return NOT_MEASURED
    if type(v) is bool:
        return "yes" if v else "no"
    if isinstance(v, (int, float)) and _finite(v):
        if unit == "in":
            return length(float(v), direction)
        if unit == "sf":
            return area(float(v), direction)
        if unit == "count":
            return str(int(v)) if float(v).is_integer() else f"{v:g}"
        return f"{v:g}"
    try:
        return str(v)
    except ValueError:                                  # an integer too long for Python to write out
        return "a number too large to print"


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

# the parts of a check a sheet's columns aren't about, by the measures they read, each set aside with its own short
# words: an area well's size rules also read what reaches into the well (RCNYS R319.4.1's exception: only the ladder or
# steps a well over 44 in deep requires, 6 in at most), which the "Required" column says in words, never as a formula
ASIDE = (({"area_well_other_encroachment", "area_well_ladder_encroachment", "area_well_depth", "area_well_ladder"},
          "nothing else in its required dimensions but the ladder or steps a well over 44 in deep requires, clear of "
          "the open window (6 in at most)"),)


# the set-aside measures' own words on a sheet (area_well_ladder is a ladder or steps the open window doesn't obstruct)
ASIDE_WORDS = {"area_well_ladder": "ladder or steps clear of the open window"}


def _aside_value(m: str, v, unit: str) -> str:
    """A set-aside measure's value, rounded the way that never favours compliance: a reach (at most) up, the depth
    (more than 44 in decides) down, said "over" where it is past 44 in but rounds to it."""
    if m == "area_well_depth":
        shown = value(v, unit, toward(ast.Gt, True))
        # the checker's own comparison (formula: two numbers within its tolerance are equal), never a raw v > 44
        try:
            over = isinstance(v, (int, float)) and formula.evaluate(
                "area_well_depth > 44", {"area_well_depth": v},
                _kinds({}, parts.measure_kinds("emergency_escape_opening"))) is True
        except (formula.MissingMeasure, formula.EvaluationError):
            over = False                          # a value the checker can't use (negative, not finite): as it is
        return f"over {shown}" if over and shown == value(44, unit) else shown
    return value(v, unit, toward(ast.LtE, True))


def _aside(node) -> str | None:
    """The words a part of a check is set aside with, or None."""
    try:
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    except Exception:
        return None
    return next((words for measures, words in ASIDE if names and names <= measures), None)


def _comparisons(check: str, aside: list | None = None):
    """The check's parts every one of which must hold (an `and` chain), each (measure, op, limit node) when it is
    `measure <op> limit` (or mirrored), else None for that part; None when the check can't be read. A part ASIDE
    names goes into `aside` (its words, once) instead, where a list is given."""
    try:
        body = formula.parse(check).body
    except Exception:
        return None

    def every(node):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            return [n for v in node.values for n in every(v)]
        return [node]
    out, parts = [], every(body)
    # set aside only beside what the column is about: a check all of whose parts ASIDE names (R319.4.2's
    # area_well_ladder) is read as it is
    if aside is not None and all(_aside(node) for node in parts):
        aside = None
    for node in parts:
        if aside is not None and (words := _aside(node)):
            if words not in aside:
                aside.append(words)
            out.append(("", "aside", node))          # its measures still shown in the Proposed column
            continue
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
    got = _comparisons(check, []) if isinstance(check, str) else None
    return {c[0] for c in got or [] if c and c[1] != "aside"}


def required_and_proposed(rule: dict, values: dict, allowed: dict | None = None) -> tuple[str, str]:
    """(what the rule requires, what the part has), as a sheet prints them: "5.7 sq ft min", "5.13 sq ft". Worked out
    from the rule's own formula with the part's values; display only. A check of another shape prints the formula
    itself, and a limit that can't be worked out (a value it needs is missing) prints its formula in words."""
    check, kind = rule.get("check"), rule.get("for_each")
    if not isinstance(check, str):
        return "see the code's words (no formula: a person decides)", ""
    aside = []
    got = _comparisons(check, aside)
    if not got or any(c is None for c in got):
        return f"per formula: {in_words(check)}", "; ".join(
            f"{measure_words(m)} {value(values.get(m), unit_of(kind, m))}" for m in sorted(values)) or ""
    kinds = _kinds(allowed or {}, parts.measure_kinds(kind))
    need, have = [], []
    shown_aside = sorted({n.id for c in got if c[1] == "aside" for n in ast.walk(c[2]) if isinstance(n, ast.Name)})
    got = [c for c in got if c[1] != "aside"]
    named = len(got) > 1 or bool(shown_aside)          # the main value keeps its name beside the set-aside ones
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
    # the measures set aside, as the part has them (the value that may decide a fail is never hidden)
    # rounded the way that never favours compliance: a reach (at most) up, the depth (more than 44 in) down
    reach = values.get("area_well_ladder_encroachment")
    if type(reach) in (int, float) and reach == 0:             # nothing reaches in: the ladder and depth decide nothing
        shown_aside = [m for m in shown_aside if m not in ("area_well_ladder", "area_well_depth")]
    have += [f"{ASIDE_WORDS.get(m, measure_words(m))} {_aside_value(m, values.get(m), unit_of(kind, m))}"
             for m in shown_aside]
    return "; ".join(need + aside), "; ".join(have)
