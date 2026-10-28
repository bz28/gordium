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


GEOMETRIC = set(YARDS) | {"building_height", "building_area"}
FLIP = {ast.GtE: ast.LtE, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.Lt: ast.Gt}


class Unreadable(Exception):
    """A rule limits a yard, the height or the building area in a form the envelope can't read."""


def _comparison(node):
    """(measure, comparison, limit formula) for `measure op limit` or `limit op measure` (turned round), where the
    measure is a yard, the height or the building area and the limit depends only on the lot; else None."""
    if not (isinstance(node, ast.Compare) and len(node.ops) == 1):
        return None
    left, op, right = node.left, type(node.ops[0]), node.comparators[0]
    if not isinstance(left, ast.Name) and isinstance(right, ast.Name) and op in FLIP:
        left, op, right = right, FLIP[op], left
    if not isinstance(left, ast.Name):
        return None
    name, limit = left.id, ast.unparse(right)
    wanted = (name in YARDS and op in MINIMUM) or (name in ("building_height", "building_area") and op in MAXIMUM)
    return (name, op, limit) if wanted and formula.names(limit) <= LOT_MEASURES else None


def _needs(node, measured: dict) -> list:
    """The yard, height and building-area limits a box must meet for this formula to hold everywhere in it: all
    parts of an `and`; one alternative of an `or` whose limits can all be read (and whose other parts are known
    true for this lot). Parts about anything else (use, stories, parking) set nothing for the shape. Raises
    Unreadable when a yard, height or area limit is written in a form that can't be read."""
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    if not names & GEOMETRIC:
        return []
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return [c for v in node.values for c in _needs(v, measured)]
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        for v in node.values:
            try:
                needs = _needs(v, measured)
            except Unreadable:
                continue
            if all(_known_true(part, measured) for part in _other_parts(v)):
                return needs
        raise Unreadable(ast.unparse(node))
    found = _comparison(node)
    if found is None:
        raise Unreadable(ast.unparse(node))
    return [found]


def _other_parts(node) -> list:
    """The parts of an alternative that aren't about the shape (to be known true for this lot)."""
    parts = node.values if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And) else [node]
    return [p for p in parts if not {n.id for n in ast.walk(p) if isinstance(n, ast.Name)} & GEOMETRIC]


def _known_true(node, measured: dict) -> bool:
    values = {k: m["value"] for k, m in measured.items()}
    try:
        return formula.evaluate(ast.unparse(node), values, MEASURE_KINDS | {"use": frozenset([values.get("use")])}) is True
    except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
        return False


def _values(measured: dict, name: str):
    """Every value a measure could have: its value, or each of its readings when they are real alternatives (two
    or more). A single reading without a value (the lot as drawn, waiting for a survey) isn't a value: unknown."""
    m = measured.get(name) or {}
    if m.get("value") is not None:
        return [m["value"]]
    readings = [r["value"] for r in m.get("readings") or []]
    return readings if len(readings) > 1 else []


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


def envelope(site: dict, facts: dict, measured: dict, rules: list[dict], margin: float = MARGIN,
             sides: dict | None = None) -> dict:
    """{"outline": [[x, y], ...] or None, "holes", "base", "top", "yards": {front, side, rear}, "side_split", "height",
    "coverage": {...} or None, "notes": [...]}: the buildable area and height, and why anything is missing.

    `side_split`: {"smaller", "larger"} when the zone lets the two side yards differ (R-2b: one 5 ft, the other
    10 ft), else None. The envelope itself always keeps the larger on both sides (cautious: drawn and snapped to).
    `sides` is for the starting house only (start.py): {"left": ft, "right": ft, "x": {edge index: x}}, each side
    lot line pushed in by its own side's yard, the left side being the reading's side lines with the smaller x
    (x along the street, in the street's frame). Used only when every reading names both sides; else ignored."""
    notes, need = [], {"front": [], "side": [], "rear": [], "building_height": [], "building_area": []}
    split = {"side_yard_smaller": [], "side_yard_larger": []}
    out = {"outline": None, "holes": [], "base": facts.get("grade_elevation"), "top": None, "yards": {},
           "side_split": None, "height": None, "coverage": None, "notes": notes}
    if facts.get("corner_lot") is not False:    # unknown, or a corner lot: its yards are open questions (§325-19C)
        notes.append("say whether this is a corner lot first" if facts.get("corner_lot") is None else
                     "a corner lot: which yards are front, side and rear is an open question; no envelope drawn")
        return out
    level = facts.get("ground_is_flat") is True and facts.get("grade_elevation") is not None
    if not level:   # the height plane is from the grade plane: without one the plan is drawn, never a top
        out["base"] = None
        notes.append("the grade isn't set: the buildable area is drawn, the height limit isn't")
    for rule in rules:
        if rule.get("kind") == "flag" or not rule.get("check") or not _applies(rule, measured):
            continue
        body = formula.parse(rule["check"]).body
        # a side yard limit inside an `or` (two ways to comply) is never split: the panel's per-side rows read each
        # side's comparison on its own, so only a plain `and` of minimums is safe to put on one side (review round 1)
        plain = not any(isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) for n in ast.walk(body))
        try:
            limits = _needs(body, measured)
        except Unreadable as e:
            notes.append(f"{rule['id']}: a limit the envelope can't read ({e}); no envelope drawn")
            return out
        for name, op, limit in limits:
            worst = _worst(limit, op, measured)
            key = YARDS.get(name, name)
            if worst is None:
                notes.append(f"{rule['id']}: the limit {limit} can't be worked out for this lot")
            need[key].append(worst)
            if name in split:
                split[name].append(worst if plain else None)
    area = [v for v in need.pop("building_area")]
    if area and None not in area:            # coverage is numbers, never a shape; unknown without a surveyed lot
        have = (measured.get("building_area") or {}).get("value")
        out["coverage"] = {"allowed": min(area), "have": have, "over": None if have is None else have - min(area)}
    if any(v is None for vs in need.values() for v in vs):
        return out
    yards = {k: max(need[k], default=0.0) for k in ("front", "side", "rear")}
    out["yards"] = yards
    smaller = max(split["side_yard_smaller"], default=0.0) if None not in split["side_yard_smaller"] else None
    larger = max(split["side_yard_smaller"] + split["side_yard_larger"], default=0.0) \
        if None not in split["side_yard_smaller"] + split["side_yard_larger"] else None
    if smaller is not None and larger is not None and larger > smaller + 1e-9:   # the larger meets both)
        out["side_split"] = {"smaller": smaller, "larger": larger}
    if need["building_height"]:
        out["height"] = min(need["building_height"])

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
        return LineString(lot.edges[i]).buffer(d + margin, quad_segs=QUAD_SEGS) if d > 0 else Polygon()

    def mean_x(group):
        return sum(sides["x"][i] for i in group) / len(group)

    for _, left, right, back in readings:
        if sides is not None and left and right:      # the starting house's own split (a reading's two sides)
            a, b = (left, right) if mean_x(left) <= mean_x(right) else (right, left)    # a: the left, from the street
            cut = [push(i, yards["front"]) for i in front] + [push(i, sides["left"]) for i in a] + \
                  [push(i, sides["right"]) for i in b]
        else:
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
