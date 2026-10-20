"""The largest legal starting building on a lot: the footprint the architect starts designing from.

Plain code reading the zone's rules (no AI, no hard-coded numbers): the footprint sits inside every required yard
(the envelope), its area stays at or under every lot-coverage limit, and it is drawn as stacked floor blocks, one
per story, up to the height limit and the story limit. Another zone's rules give that zone's building.

The shape: a rectangle square to the street, set right at the front yard line and as wide as the side yards
allow, then as deep as the coverage limit and the rear yard allow, its sides in whole inches (rounded down). On
the 73'-0" x 90'-0" lot: 53'-0" x 30'-11" = 1,639 sf, 24.94% of the lot, under the 25% limit. So growing it on any side breaks a rule: the
front yard, a side yard, or (in depth) the coverage limit or the rear yard.

Where a limit can't be worked out for the lot, it says so, and the generator takes the strictest reading it can
(the envelope already takes the largest yard any reading of the lot could need). Lot coverage on a lot that isn't
from a survey is sized from the lot as drawn, and said so: the check itself still says NEEDS REVIEW until the
architect confirms the survey.
"""

import ast
import math

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box

from model_measurement.measure import Lot
from rule_format import formula

from .envelope import LOT_MEASURES, _applies, _worst, envelope

STEP = 0.1        # ft: how finely the footprint's depth is searched
SAFETY = 0.01     # ft: pulled in when a corner falls between samples
INCH = 1 / 12     # the footprint's sides are whole inches, rounded down (never toward a limit)


def _story_limit(rules: list[dict], measured: dict):
    """The lowest `stories <= N` (or `< N`) any rule that applies sets, whose limit depends only on the lot."""
    found = []
    for rule in rules:
        if rule.get("kind") == "flag" or not rule.get("check") or not _applies(rule, measured):
            continue
        for node in ast.walk(formula.parse(rule["check"]).body):
            if (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name)
                    and node.left.id == "stories" and isinstance(node.ops[0], (ast.LtE, ast.Lt))):
                limit = ast.unparse(node.comparators[0])
                if formula.names(limit) <= LOT_MEASURES:
                    worst = _worst(limit, ast.LtE, measured)
                    if worst is not None:     # whole stories: at most N, or under N
                        found.append(math.ceil(worst) - 1 if isinstance(node.ops[0], ast.Lt) else math.floor(worst))
    return min(found) if found else None


def _as_drawn(measured: dict) -> tuple[dict, bool]:
    """The measurements with the lot area as drawn when it is waiting for a survey (one reading, no value)."""
    lot_area = measured.get("lot_area") or {}
    readings = lot_area.get("readings") or []
    if lot_area.get("value") is None and len(readings) == 1:
        return {**measured, "lot_area": {**lot_area, "value": readings[0]["value"]}}, True
    return measured, False


def _frame(lot: Lot):
    """(angle, origin): the street's direction, so x runs along the street and y into the lot."""
    chain = lot.ordered_street()
    a, b = lot.edges[chain[0]][0], lot.edges[chain[-1]][-1]
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    inside = lot.polygon.representative_point()
    # turn so the street runs along x; flip if the lot then lies below the street
    turned = affinity.rotate(LineString([a, b]), -angle, origin=a, use_radians=True)
    point = affinity.rotate(inside, -angle, origin=a, use_radians=True)
    if point.y < turned.coords[0][1]:
        angle += math.pi
    return angle, a


def _x_range(shape: Polygon, y: float, around: float):
    """The stretch of a level line through the shape at height y that contains x = `around` (or the longest)."""
    x0, _, x1, _ = shape.bounds
    cut = shape.intersection(LineString([(x0 - 1, y), (x1 + 1, y)]))
    pieces = [g for g in getattr(cut, "geoms", [cut]) if isinstance(g, LineString) and not g.is_empty]
    if not pieces:
        return None
    spans = [sorted([c[0] for c in g.coords]) for g in pieces]
    hit = [s for s in spans if s[0] <= around <= s[-1]]
    s = hit[0] if hit else max(spans, key=lambda s: s[-1] - s[0])
    return s[0], s[-1]


def _footprint(shape: Polygon, around: float, allowed, front_line: float, front_limit: float,
               front_from: float = -math.inf, stride: int = 1):
    """(x0, x1, front, depth): the largest rectangle square to the street inside the buildable area, at or under
    the coverage limit. The fronts tried run from the bottom of the buildable area up to `front_limit`: the front
    yard line (`front_line`, always tried exactly), or on a bent or curved street the deepest point of that line
    plus one STEP. From each, the width only narrows going back, so it grows deeper until coverage or the rear
    stops it; the largest wins, the widest on a tie. So when a front exists at the front yard line, the building
    sits on it, never slides back for a wider rear, and the search stays short. (A flag lot, where none exists, is
    searched over its whole buildable area by the caller: fronts a foot apart first (`stride`), then every
    level near the best (`front_from`), so a deep lot stays quick.)"""
    y0, y1 = shape.bounds[1], shape.bounds[3]
    n = max(1, int(math.ceil((y1 - y0) / STEP)))
    levels = sorted({y0 + (y1 - y0) * k / n for k in range(n + 1)} | ({front_line} if y0 <= front_line <= y1 else set()))
    n = len(levels) - 1
    spans = [_x_range(shape, y, around) for y in levels]
    best, best_key = None, (0.0, 0.0)   # the largest area, then the widest (square to the side yards)
    for i, first in enumerate(spans):
        if i % stride or levels[i] < front_from - 1e-9:
            continue
        if levels[i] > front_limit + 1e-9:
            break                       # behind the front yard line (or its strip, on a bent street)
        if first is None or first[1] - first[0] <= 0:
            continue
        width = first[1] - first[0]
        if allowed is not None and best_key[0] >= allowed - 1e-6 and width <= best_key[1] + 1e-9:
            continue                    # the coverage limit is reached: only a wider front could still win
        if width * (y1 - levels[i]) < best_key[0] - 1e-6 or (                 # can't be larger,
                width * (y1 - levels[i]) <= best_key[0] + 1e-6 and width <= best_key[1] + 1e-9):  # nor as large and wider
            continue
        lo, hi = first
        for j in range(i + 1, n + 1):
            span = spans[j]
            if span is None or min(hi, span[1]) - max(lo, span[0]) <= 0:
                break
            lo, hi = max(lo, span[0]), min(hi, span[1])
            depth = levels[j] - levels[i]
            area = (hi - lo) * depth
            if allowed is not None and area >= allowed:
                area, depth = allowed, allowed / (hi - lo)
            key = (round(area, 6), hi - lo)
            if key > best_key:
                best, best_key = (lo, hi, levels[i], depth), key
            if allowed is not None and area >= allowed:
                break
    return best


def largest_legal_building(site: dict, facts: dict, measured: dict, rules: list[dict]) -> dict:
    """{"floors": [{"outline": [[x, y], ...], "base": z, "top": z}, ...], "stories", "height", "area",
    "coverage_allowed", "notes"}: the starting building, or no floors and the notes that say why."""
    out = {"floors": [], "stories": None, "height": None, "area": None, "coverage_allowed": None, "notes": []}
    notes = out["notes"]
    sized, drawn = _as_drawn(measured)       # coverage on a lot not yet surveyed: from the lot as drawn (said below)
    # the rectangle's sides lie on straight yard lines, so the exact region is used (no rounding margin): the yards
    # come out at their limits, 25'-0" and 10'-0", not a hair over
    env = envelope(site, facts, sized, rules, margin=0.0)
    notes += env["notes"]
    if not env["outline"]:
        notes.append("no buildable area to start from")
        return out
    if env["height"] is None or env["base"] is None:
        notes.append("no height limit or ground level: the building's height can't be set")
        return out
    allowed = env["coverage"]["allowed"] if env["coverage"] else None
    if drawn and allowed is not None:
        notes.append("lot coverage sized from the lot as drawn, which isn't from a survey: the check says NEEDS "
                     "REVIEW for coverage until the survey is confirmed")
    stories = _story_limit(rules, sized)
    if stories is None or stories < 1:
        notes.append("no story limit applies: drawn as one story up to the height limit")
        stories = 1

    lot = Lot(site, facts)
    angle, origin = _frame(lot)
    buildable = affinity.rotate(Polygon(env["outline"], env["holes"]), -angle, origin=origin, use_radians=True)
    street = [affinity.rotate(Point(p), -angle, origin=origin, use_radians=True).y
              for i in lot.ordered_street() for p in lot.edges[i]]
    bend = max(street) - min(street)
    front_line = max(street) + env["yards"]["front"]          # the front yard line, in the street's frame
    found = _footprint(buildable, buildable.centroid.x, allowed, front_line,
                       front_line + (STEP if bend > 1e-9 else 0.0))
    if found is None and buildable.bounds[1] > front_line + 1e-9:
        # a flag lot or a narrow neck: the side yards close the frontage, so the buildable area only starts behind
        # the front yard line; the building goes where the buildable area begins, and the note says why
        around, top = buildable.centroid.x, buildable.bounds[3]
        coarse = _footprint(buildable, around, allowed, front_line, top, stride=int(round(1.0 / STEP)))
        found = coarse and (_footprint(buildable, around, allowed, front_line, coarse[2] + 1.0, coarse[2] - 1.0)
                            or coarse)
        if found is not None:
            setback = found[2] - max(street)
            notes.append("the side yards close the lot's frontage (a flag lot or a narrow neck): the starting building "
                         f"sits behind the front yard line, where the largest rectangle fits, {setback:.1f} ft from the "
                         "street")
    if found is None:
        notes.append("no rectangle square to the street fits inside the required yards")
        return out
    lo, hi, y0, depth = found
    best = box(lo, y0, hi, y0 + depth)
    while not best.within(buildable.buffer(1e-9)) and best.bounds[2] - best.bounds[0] > 2 * SAFETY:
        best = box(best.bounds[0] + SAFETY, y0, best.bounds[2] - SAFETY, y0 + depth)   # a corner between slices
    if not best.within(buildable.buffer(1e-9)):
        notes.append("no rectangle square to the street fits inside the required yards")
        return out
    x0, _, x1, y1b = best.bounds                 # whole inches, rounded down, centred where it was
    width = math.floor((x1 - x0) / INCH + 1e-6) * INCH
    depth = math.floor((y1b - y0) / INCH + 1e-6) * INCH
    x0 += ((x1 - x0) - width) / 2
    best = box(x0, y0, x0 + width, y0 + depth)
    outline = affinity.rotate(best, angle, origin=origin, use_radians=True)
    ring = [[x, y] for x, y in list(outline.exterior.coords)[:-1]]
    base, top = env["base"], env["base"] + env["height"]
    story = env["height"] / stories
    out["floors"] = [{"outline": ring, "base": base + i * story, "top": top if i == stories - 1 else base + (i + 1) * story}
                     for i in range(stories)]
    out.update(stories=stories, height=env["height"], area=outline.area, coverage_allowed=allowed)
    return out
