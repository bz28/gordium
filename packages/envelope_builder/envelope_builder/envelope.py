"""The largest building the rules allow on a lot: the lot shrunk by every required yard, up to the height
limit. Plain code reading the zone's rules; no AI.

Every point inside the envelope meets every yard and height limit the rules set, under every reading of the
lot (a jog as a side or rear line, each reading of the lot depth). So it is drawn the cautious way: each lot
line is pushed in by the largest yard it could need, and the height is the lowest limit any rule sets.
Limits that aren't a shape (lot coverage) come back as numbers, never drawn.

Where the yard requirements come from: every comparison in a rule that applies, `<yard> >= <limit>` or
`building_height <= <limit>`, whose limit depends only on the lot (its area, width or depth), never on the
design. So `rear_yard >= max(min(0.25 * lot_depth, 50), 20)` counts; the height bonus's `front_yard >= 25 +
(building_height - 35)` doesn't (it changes with the design; the plain 35 ft limit stands).
"""

import ast
import itertools

from shapely import ops
from shapely.geometry import LineString, Polygon

from model_measurement.measure import Lot
from rule_format import formula
from rule_format.rulebook import MEASURE_KINDS

YARDS = {"front_yard": "front", "side_yard_smaller": "side", "side_yard_larger": "side", "rear_yard": "rear"}
LOT_MEASURES = {"lot_area", "lot_width", "lot_depth", "use"}
MINIMUM, MAXIMUM = (ast.GtE, ast.Gt), (ast.LtE, ast.Lt)
# Rounded corners are drawn as short straight pieces that sit inside the true circle. With 128 pieces per
# quarter circle they sit at most 0.00094 ft inside for a 50 ft yard; pushing every yard 0.001 ft further keeps
# the whole envelope legal (never a sliver inside a required yard).
QUAD_SEGS, MARGIN = 128, 0.001


def _limits(rule: dict) -> list[tuple[str, type, str]]:
    """(measure, comparison, limit formula) for each comparison of a yard, the height or the building area
    against a limit that depends only on the lot."""
    found = []
    for node in ast.walk(formula.parse(rule["check"]).body):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name):
            name, op, limit = node.left.id, type(node.ops[0]), ast.unparse(node.comparators[0])
            wanted = (name in YARDS and op in MINIMUM) or (name in ("building_height", "building_area") and op in MAXIMUM)
            if wanted and formula.names(limit) <= LOT_MEASURES:
                found.append((name, op, limit))
    return found


def _values(measured: dict, name: str):
    """Every value a measure could have: its value, or each of its readings when the readings disagree."""
    m = measured.get(name) or {}
    if m.get("value") is not None:
        return [m["value"]]
    return [r["value"] for r in m.get("readings") or []]


def _worst(limit: str, op, measured: dict):
    """The most demanding value a limit can take over every reading of the lot, or None if it can't be worked
    out (a lot measure it needs has no value and no readings)."""
    names = sorted(formula.names(limit) & LOT_MEASURES)
    choices = [_values(measured, n) for n in names]
    if any(not c for c in choices):
        return None
    got = []
    for combo in itertools.product(*choices):
        try:
            got.append(formula.evaluate(limit, dict(zip(names, combo)), MEASURE_KINDS))
        except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
            return None
    return max(got) if op in MINIMUM else min(got)


def _applies(rule: dict, measured: dict) -> bool:
    """A rule counts unless it surely doesn't apply (its condition is false with the facts known)."""
    if not rule.get("applies_when"):
        return True
    values = {k: m["value"] for k, m in measured.items()}
    try:
        return formula.evaluate(rule["applies_when"], values, MEASURE_KINDS | {"use": frozenset([values.get("use")])}) is not False
    except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
        return True


def envelope(site: dict, facts: dict, measured: dict, rules: list[dict]) -> dict:
    """{"outline": [[x, y], ...] or None, "holes", "base", "top", "yards": {front, side, rear}, "height",
    "coverage": {...} or None, "notes": [...]}: the buildable area and height, and why anything is missing."""
    notes, need = [], {"front": [], "side": [], "rear": [], "building_height": [], "building_area": []}
    out = {"outline": None, "holes": [], "base": facts.get("grade_elevation"), "top": None, "yards": {},
           "height": None, "coverage": None, "notes": notes}
    if facts.get("corner_lot") is not False:    # unknown, or a corner lot: its yards are open questions (§325-19C)
        notes.append("say whether this is a corner lot first" if facts.get("corner_lot") is None else
                     "a corner lot: which yards are front, side and rear is an open question; no envelope drawn")
        return out
    for rule in rules:
        if rule.get("kind") == "flag" or not rule.get("check") or not _applies(rule, measured):
            continue
        for name, op, limit in _limits(rule):
            worst = _worst(limit, op, measured)
            key = YARDS.get(name, name)
            if worst is None:
                notes.append(f"{rule['id']}: the limit {limit} can't be worked out for this lot")
            need[key].append(worst)
    if any(v is None for vs in need.values() for v in vs):
        return out
    yards = {k: max(need[k], default=0.0) for k in ("front", "side", "rear")}
    out["yards"] = yards
    if need["building_height"]:
        out["height"] = min(need["building_height"])
    if need["building_area"]:
        allowed = min(need["building_area"])
        have = (measured.get("building_area") or {}).get("value")
        out["coverage"] = {"allowed": allowed, "have": have, "over": None if have is None else have - allowed}

    if not site.get("lot") or site.get("problems"):
        notes.append("no lot outline to build on")
        return out
    lot = Lot(site, facts)
    if lot.problems or lot.street_problem:
        notes.append("; ".join(lot.problems) or lot.street_problem)
        return out
    front = lot.ordered_street()
    rest = [i for i in range(len(lot.edges)) if i not in front]
    readings = lot.readings() or [("", [], [], rest)]   # sides unclear: every other line takes the larger yard
    keep = lot.polygon
    def push(i, d):
        return LineString(lot.edges[i]).buffer(d + MARGIN, quad_segs=QUAD_SEGS) if d > 0 else Polygon()

    for _, left, right, back in readings:
        cut = [push(i, yards["front"]) for i in front] + [push(i, yards["side"]) for i in left + right]
        cut += [push(i, max(yards["side"], yards["rear"]) if not (left or right) else yards["rear"]) for i in back]
        keep = keep.difference(ops.unary_union(cut))
    if keep.is_empty:
        notes.append("the required yards leave no room to build")
        return out
    biggest = max(getattr(keep, "geoms", [keep]), key=lambda p: p.area)
    if len(getattr(keep, "geoms", [])) > 1:
        notes.append("the required yards split the lot; the largest piece is drawn")
    out["outline"] = [[x, y] for x, y in biggest.exterior.coords[:-1]]
    out["holes"] = [[[x, y] for x, y in h.coords[:-1]] for h in biggest.interiors]
    if out["base"] is not None and out["height"] is not None:
        out["top"] = out["base"] + out["height"]
    elif out["height"] is None:
        notes.append("no height limit applies")
    return out
