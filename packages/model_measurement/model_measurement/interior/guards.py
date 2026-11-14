"""Guards (R321.1): the guard's height and the largest sphere that passes through it.

Guard is not a part kind in rule_format/parts.yaml yet, so these are measured for a later rule (proposed in the PR).
  - a guard at a level walking surface (a loft's edge, a landing, a balcony): its height is its top above the
    walking surface; its members (rails, balusters, posts, panels) are drawn in its own elevation, and the largest
    sphere that passes is the largest circle that fits an opening between them (each must be a rectangle);
  - a guard along a stair: its height is its top above the line connecting the nosings, least over the flight;
    its openings (R321.1.3's 4 3/8 in sphere and the triangle at each step) aren't measured yet.
Definitions: docs/interior/interior_measurements.md.
"""

from shapely.geometry import box
from shapely.ops import unary_union

from model_measurement.interior.read import tidy
from model_measurement.interior.stairs import along, at
from model_measurement.interior.stops import Stop


def level_guard(g: dict, reader) -> tuple[dict, dict]:
    measures, stopped = {}, {}
    walk = reader.length(g.get("walking_surface"), "the guard's walking surface")
    top = reader.length(g.get("top"), "the top of the guard")
    if top - walk <= 0:
        raise Stop("not_positive", what="the guard's height", value=tidy(top - walk))
    if not top_drawn(g, reader, top):
        raise Stop("guard_top_not_drawn")
    measures["guard_height"] = tidy(top - walk)
    try:
        measures["guard_opening_sphere"] = tidy(largest_sphere(g, reader, walk, top))
    except Stop as s:
        stopped["guard_opening_sphere"] = s.reason
    return measures, stopped


def top_drawn(g: dict, reader, top: float) -> bool:
    """Whether some member (the top rail) reaches the guard's stated top: its height is the drawn guard's."""
    members = g.get("members")
    if not isinstance(members, list):
        raise Stop("missing", what="the guard's members (`members`: rails, balusters, posts, panels)")
    tops = [reader.rectangle(m, f"guard member {n}")[3] for n, m in enumerate(members, 1)]
    return any(t >= top - 1e-9 for t in tops)


def largest_sphere(g: dict, reader, walk: float, top: float) -> float:
    """The diameter of the largest sphere that passes through the guard between the walking surface and its top.
    The guard's ends (`extent`) stand against something solid (a wall, a newel post); the walking surface is solid."""
    extent = g.get("extent")
    if not isinstance(extent, dict):
        raise Stop("missing", what="the guard's extent (`extent`: left, right)")
    left = reader.length(extent.get("left"), "the guard's left end")
    right = reader.length(extent.get("right"), "the guard's right end")
    if right <= left:
        raise Stop("not_positive", what="the guard's length", value=tidy(right - left))
    members = g.get("members")
    if not isinstance(members, list):
        raise Stop("missing", what="the guard's members (`members`: rails, balusters, posts, panels)")
    blocks = []
    for n, m in enumerate(members, 1):
        l, r, b, t = reader.rectangle(m, f"guard member {n}")
        blocks.append(box(l, b, r, t))
    free = box(left, walk, right, top).difference(unary_union(blocks)) if blocks else box(left, walk, right, top)
    pieces = [] if free.is_empty else list(getattr(free, "geoms", [free]))
    best = 0.0
    for piece in pieces:
        if piece.area <= 0:
            continue
        l, b, r, t = piece.bounds
        if t >= top - 1e-9:
            raise Stop("guard_open_at_top")
        if abs(piece.area - piece.envelope.area) > 1e-9 * max(1.0, piece.envelope.area):
            raise Stop("guard_opening_shape")
        best = max(best, min(r - l, t - b))
    return best


def stair_guard(g: dict, reader, flights: dict) -> tuple[dict, dict]:
    """flights: stair id → its placed Flight, or the reason it couldn't be measured."""
    stair = g.get("stair")
    if not isinstance(stair, str) or stair not in flights:
        raise Stop("stair_unknown")
    flight = flights[stair]
    if isinstance(flight, str):
        raise Stop("stair_unread", reason=flight)
    pts = reader.points(g.get("top_line"), 3, "the guard's top line", 2)
    line = along(flight, [(x, y) for x, y, _ in pts], "top line", "guard's")
    # its height along the run, from the same points in elevation: s → z
    sz = sorted((flight.s_of(x, y), z) for x, y, z in pts)
    start, end = flight.s[0], flight.s[-1]
    if at(line, start) is None or at(line, end) is None:
        raise Stop("side_not_along", side="guard's", what="top line")
    breaks = sorted({start, end, *flight.s, *(s for s, _ in sz if start <= s <= end)})
    height = min(at(sz, s) - flight.nosing_z(s) for s in breaks)
    if height <= 0:
        raise Stop("not_positive", what="the guard's height", value=tidy(height))
    return {"guard_height": tidy(height)}, {"guard_opening_sphere": Stop("stair_guard_openings").reason}


def measure_guard(g: dict, reader, flights: dict) -> tuple[dict, dict, dict]:
    on_stair, on_level = g.get("stair") is not None, g.get("walking_surface") is not None
    try:
        if on_stair == on_level:
            raise Stop("guard_kind")
        measures, stopped = stair_guard(g, reader, flights) if on_stair else level_guard(g, reader)
    except Stop as s:
        return {}, {}, {"guard_height": s.reason, "guard_opening_sphere": s.reason}
    return measures, {}, stopped
