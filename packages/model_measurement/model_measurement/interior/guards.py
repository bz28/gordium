"""Guards (R321.1): the guard's height and the largest sphere that passes through it.

Guard is not a part kind in rule_format/parts.yaml yet, so these are measured for a later rule (proposed in the PR).
  - a guard at a level walking surface (a loft's edge, a landing, a balcony): its height is its top above the
    walking surface; its members (rails, balusters, posts, panels) are drawn in its own elevation, and the largest
    sphere that passes is the largest circle that fits an opening between them (each must be a rectangle);
  - a guard along a stair: its height is its top above the line connecting the nosings, least over the flight;
    it must stand along a side of the stair (its top line on that side's line, within 1/16 in), else no value;
    its openings (R321.1.3's 4 3/8 in sphere and the triangle at each step) aren't measured yet.
Definitions: docs/interior/interior_measurements.md.
"""

from shapely.geometry import box
from shapely.ops import unary_union

from model_measurement.interior.read import tidy
from model_measurement.interior.stairs import LEVEL, along, at, side_lines
from model_measurement.interior.stops import Stop

# in: how far a stair guard's top line may be, in plan, from the side of the stair it stands along: drawing noise
# only (the same 1/16 in a nosing's ends may be off, stairs.LEVEL), since both are drawn on the same line
ON_SIDE = LEVEL
ON_SIDE_WORDS = "1/16"


def level_guard(g: dict, reader) -> tuple[dict, dict]:
    measures, stopped = {}, {}
    walk = reader.length(g.get("walking_surface"), "the guard's walking surface")
    top = reader.length(g.get("top"), "the top of the guard")
    if top - walk <= 0:
        raise Stop("not_positive", what="the guard's height", value=tidy(top - walk))
    least = drawn_top(g, reader, walk, top)
    if least < top - 1e-9:
        raise Stop("guard_top_not_drawn", least=tidy(least - walk))
    measures["guard_height"] = tidy(top - walk)
    try:
        measures["guard_opening_sphere"] = tidy(largest_sphere(g, reader, walk, top))
    except Stop as s:
        stopped["guard_opening_sphere"] = s.reason
    return measures, stopped


def drawn_top(g: dict, reader, walk: float, top: float) -> float:
    """The drawn guard's top where it is lowest along its length: at each point between its ends, the highest
    member there that starts below the stated top (counted no higher than it). The guard's height is the stated
    top only if the members reach it all along."""
    extent, members = g.get("extent"), g.get("members")
    if not isinstance(extent, dict):
        raise Stop("missing", what="the guard's extent (`extent`: left, right)")
    if not isinstance(members, list):
        raise Stop("missing", what="the guard's members (`members`: rails, balusters, posts, panels)")
    left = reader.length(extent.get("left"), "the guard's left end")
    right = reader.length(extent.get("right"), "the guard's right end")
    if right <= left:
        raise Stop("not_positive", what="the guard's length", value=tidy(right - left))
    rects = [reader.rectangle(m, f"guard member {n}") for n, m in enumerate(members, 1)]
    cuts = sorted({left, right, *(u for r in rects for u in r[:2] if left < u < right)})
    lowest = top
    for a, b in zip(cuts, cuts[1:]):                 # the highest member over each stretch between cuts
        mid = (a + b) / 2
        # a member counts only within the guard, below its stated top: one wholly above it is no part of it
        here = [r[3] for r in rects if r[0] <= mid <= r[1] and r[2] < top]
        lowest = min(lowest, min(max(here), top) if here else walk)      # nothing there: no guard at all
    return lowest


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
        if abs(piece.area - piece.envelope.area) > 1e-9 * max(1.0, piece.envelope.area):
            raise Stop("guard_opening_shape")
        best = max(best, min(r - l, t - b))
    return best


def stair_guard(g: dict, reader, flights: dict) -> tuple[dict, dict]:
    """flights: stair id → (its placed Flight, its description), or the reason it couldn't be measured."""
    stair = g.get("stair")
    if not isinstance(stair, str) or stair not in flights:
        raise Stop("stair_unknown")
    if isinstance(flights[stair], str):
        raise Stop("stair_unread", reason=flights[stair])
    flight, st = flights[stair]
    pts = reader.points(g.get("top_line"), 3, "the guard's top line", 2)
    line = along(flight, [(x, y) for x, y, _ in pts], "top line", "guard's")
    # its height along the run, from the same points in elevation: s → z
    sz = sorted((flight.s_of(x, y), z) for x, y, z in pts)
    start, end = flight.span()
    if at(line, start) is None or at(line, end) is None:
        raise Stop("side_not_along", side="guard's", what="top line")
    on_side(line, flight, side_lines(st, flight, reader))
    breaks = sorted({start, end, *flight.s, *(s for s, _ in flight.line()),
                     *(s for s, _ in sz if start <= s <= end)})
    height = min(at(sz, s) - flight.nosing_z(s) for s in breaks)
    if height <= 0:
        raise Stop("not_positive", what="the guard's height", value=tidy(height))
    return {"guard_height": tidy(height)}, {"guard_opening_sphere": Stop("stair_guard_openings").reason}


def on_side(line, flight, sides: dict) -> None:
    """Stop unless the guard stands along a side of its stair: its top line, in plan, within ON_SIDE of a side
    drawn as a line (a side with a guard is given as the guard's inside face) all along the flight. A guard drawn
    anywhere else (off to one side, along nothing) protects no side of this stair, so it gets no height. Both lines
    are straight between their points, so how far apart they are is greatest at a point of one of them, or at an
    end of the flight: checked exactly there."""
    drawn = {side: s for side, s in sides.items() if s != "open"}
    if not drawn:
        raise Stop("guard_no_side")
    start, end = flight.span()
    far = {}
    for side, side_line in drawn.items():
        cuts = {start, end, *(s for s, _ in [*line, *side_line] if start <= s <= end)}
        far[side] = max(abs(at(line, s) - at(side_line, s)) for s in cuts)
    if min(far.values()) > ON_SIDE + 1e-9:
        raise Stop("guard_off_side", off=tidy(min(far.values())), on=ON_SIDE_WORDS)


def measure_guard(g: dict, reader, flights: dict) -> tuple[dict, dict, dict]:
    on_stair, on_level = g.get("stair") is not None, g.get("walking_surface") is not None
    try:
        if on_stair == on_level:
            raise Stop("guard_kind")
        measures, stopped = stair_guard(g, reader, flights) if on_stair else level_guard(g, reader)
    except Stop as s:
        return {}, {}, {"guard_height": s.reason, "guard_opening_sphere": s.reason}
    return measures, {}, stopped
