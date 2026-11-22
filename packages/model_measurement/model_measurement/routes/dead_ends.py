"""Dead ends and corridor widths, from the corridors' shape (decision 6 of docs/decisions/2026-11-20_route_measurement.md).

    corridors(story, uses, routes) -> {room id: Corridor(width, dead_ends, readings, stop, width_stop, ...)}

**The legs** (decision 6, amended 2026-11-22 for corridors that jog, widen, step or have alcoves). The corridors a
route may cross (rooms marked `corridor` with `lockable: false`, decision 1a) joined by passages make one floor,
turned square (a wall not at right angles: needs review). A recess, or a bump, shallower than 12 in (two equal sides
under 12 in, such as a door's recess) is filled to find the legs (a bump still narrows the width). The floor is cut
on every corner's x and y into cells; each maximal rectangle is looked at both ways: a side of it is a wall where no
floor lies beyond it, or only floor under 12 in deep; it is a leg along a way where both its sides that way are walls
for 12 in or more (its own stretch, `proper`) and where its centre line, somewhere along that stretch, is at least
half its width less 12 in from every wall (else a nearer wall lies between: the side of a wider floor). Both ways:
its longer side (a square: needs review). Every part of the floor lies in a leg or within 12 in of one. Legs along
one way that overlap with their walls within 12 in on each side are one leg, its walls the outermost (a wall
stepping by under 12 in moves no centre line). Legs at right angles cross where their centre lines do, also where
one ends within 12 in on the other's floor (its centre line runs on across); legs along one way whose walls differ
by 12 in or more (a widening, a narrowing, a jog) are joined by steps at right angles, at the ends of the stretch
both run and at each crossing in it (never inside a leg at right angles to both, nor where both end against one
wall). A centre line runs past its last crossing or step only with its own stretch there; an end with nothing
joined is a closed end only if walled across the leg's whole width. An island (a hole, or an obstruction clear of
the walls, longer than its leg is wide): needs review. One corridor has one centre line at each place (review round
1): a narrower leg's doesn't run inside a wider one it steps to; two side by side, neither inside the other, each
run to the middle of the stretch both run; two on one line are one; two parallel ones in one stretch, or a loop of
them round floor alone, need review; two edges between one pair of nodes are one (a loop of no floor, its two sides
never two ways).

**Where a dead end ends.** The centre lines make a graph. Reaching an exit means reaching, along it, a door of an
exit (`exit_kind`, by `exit_id`) in a corridor's wall (put on the centre line where it is nearest the door's centre),
or through a door between two such corridors (a straight line across it); a route through a room, or through a
corridor a route may not cross, never counts. A dead end runs along the centre lines from a closed end (an end of
the graph with no exit there) to the nearest point from which routes in two directions each reach a distinct exit
without coming back: a point of a centre line cut there whose two sides reach two distinct exits, a crossing two of
whose ways do, or an exit door in the corridor itself. Where that point is a crossing, on to point C (NFPA 101 2012
A.7.5.1.5, "located at the centerline of the corridor"): along its own centre line, still out of its own stretch, to
the farthest centre line it crosses there of the crossing corridor (that leg and those joined to it by steps: a
widened corridor has two), never past an exit. No such point from a closed end: its dead end isn't bounded, needs
review.

**Open question 7.** A door into a room with another way out never ends a dead end. Where one would end it sooner,
each dead end has two named readings: without such doors (the defined value) and with them (a door into a room
whose other doors reach an exit, without coming back into these corridors, counts as a way to those exits).

**Widths.** A corridor's width is the narrowest clear width across its own legs' stretches in it: the leg's width
less what obstructions, columns and bumps block across it (each by its extent across the leg: the less favourable
side); where its floor needed a step, a leg made of several, or a centre line run on, it needs review (which
stretches give it, rather than its alcoves, isn't worked out). Each dead end is its own pair,
its length with its own least width: routes/__init__ gives the corridor one part per dead end until the branch's
`dead_end` part kind exists. A closed end is the farthest point of the real floor across the leg's whole width
(a recess filled to find the legs never moves it; walls only, so an obstruction never shortens a dead end). A dead
end's least width is one figure: the narrowest cross-section of the clear floor (the real floor less every
obstruction and hole, opened by 1/16 in so a hairline is no floor) across its legs' whole width, over its own
stretches and any recess at its closed end, cut at both ends of every slice between corner places (so a slanted
or rotated obstruction is measured at its widest), and at each step it walks, across the widths its two legs share
there (a jog's throat).
Lengths in inches.
"""

import heapq
import logging
import math
from dataclasses import dataclass, field, replace

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from model_measurement.routes.floor import SAME, Story, region
from model_measurement.routes.paths import StoryRoutes, _Leg
from model_measurement.routes.stops import Stop

SHALLOW = 12.0                 # in: a recess (or a bump) shallower than this is ignored in finding the legs
QUESTION = "door_ends_dead_end"    # open question 7: does a door into a room with another way out end a dead end?
WITHOUT, WITH = "without_door", "with_door"


@dataclass
class DeadEnd:
    start: tuple               # the closed end (plan, in)
    room: str                  # the corridor it starts in
    length: dict               # reading -> in
    width: dict                # reading -> in (the least clear width along it)
    line: dict                 # reading -> the centre line walked, [(x, y), ...] (plan, in)


@dataclass
class Corridor:
    room: str
    width: float | None = None             # in, the least clear width over its legs
    width_stop: str | None = None
    dead_ends: list = field(default_factory=list)
    stop: str | None = None                # why its dead ends aren't worked out
    centre_lines: list = field(default_factory=list)     # [((x, y), (x, y)), ...] plan, in

    def longest(self, reading) -> tuple:
        """The corridor's longest dead end's own pair under a reading (its length, its own least width); no dead end:
        (0, the corridor's width). Each dead end is its own pair (decision 6): routes/__init__ gives one corridor
        part per dead end."""
        mine = [d for d in self.dead_ends if d.room == self.room]
        if not mine:
            return 0.0, self.width
        top = max(mine, key=lambda d: d.length[reading])
        return top.length[reading], top.width[reading]


# --- turning a floor square -----------------------------------------------------------------------------------------

class _Frame:
    def __init__(self, angle):
        angle = (angle + math.pi / 4) % (math.pi / 2) - math.pi / 4     # a quarter turn changes nothing
        if abs(angle) <= 1e-12:
            angle = 0.0                                  # a plan drawn square stays exact (20'-0" is 20 ft)
        self.c, self.s = math.cos(angle), math.sin(angle)

    def to(self, p):
        return (p[0] * self.c + p[1] * self.s, -p[0] * self.s + p[1] * self.c)

    def back(self, p):
        return (p[0] * self.c - p[1] * self.s, p[0] * self.s + p[1] * self.c)


def _drop_collinear(pts):
    changed = True
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            if abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) <= 1e-9 * max(
                    math.dist(a, b) * math.dist(b, c), 1e-12) or math.dist(a, b) <= 1e-9:
                del pts[i]
                changed = True
                break
    return pts


def _square_ring(pts):
    """A ring (in the frame) made exactly square, or None: each side within 1/16 in of along x or along y, the
    sides alternating, every x and y within 1/16 in of another made one."""
    pts = _drop_collinear([tuple(p) for p in pts])
    n = len(pts)
    kinds = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
        if dy <= SAME and dx > SAME:
            kinds.append("h")
        elif dx <= SAME and dy > SAME:
            kinds.append("v")
        else:
            return None
    merged_pts, merged_kinds = [], []
    for i in range(n):                                 # a side made of two pieces along one line: one side
        if kinds[i] == kinds[i - 1]:
            continue
        merged_pts.append(pts[i])
        merged_kinds.append(kinds[i])
    if len(merged_pts) < 4 or len(merged_pts) % 2:
        return None
    return merged_pts, merged_kinds


def _snap(values):
    values = sorted(values)
    out, group = {}, [values[0]]
    for v in values[1:]:
        if v - group[-1] <= SAME:
            group.append(v)
        else:
            for g in group:
                out[g] = sum(group) / len(group)
            group = [v]
    for g in group:
        out[g] = sum(group) / len(group)
    return out


def _square(poly, frame):
    """The polygon in the frame, exactly square (its rings' corners snapped), or None."""
    rings = []
    for ring in [poly.exterior, *poly.interiors]:
        got = _square_ring([frame.to(p) for p in list(ring.coords)[:-1]])
        if got is None:
            return None
        rings.append(got)
    xs = _snap([(p[0] + q[0]) / 2 for pts, kinds in rings for i, (p, k) in enumerate(zip(pts, kinds)) if k == "v"
                for q in [pts[(i + 1) % len(pts)]]])
    ys = _snap([(p[1] + q[1]) / 2 for pts, kinds in rings for i, (p, k) in enumerate(zip(pts, kinds)) if k == "h"
                for q in [pts[(i + 1) % len(pts)]]])
    out = []
    for pts, kinds in rings:
        n = len(pts)
        sides = []
        for i in range(n):
            p, q = pts[i], pts[(i + 1) % n]
            sides.append(("v", xs[(p[0] + q[0]) / 2]) if kinds[i] == "v" else ("h", ys[(p[1] + q[1]) / 2]))
        corners = []
        for i in range(n):                             # corner i: between side i - 1 and side i
            a, b = sides[i - 1], sides[i]
            x = a[1] if a[0] == "v" else b[1]
            y = a[1] if a[0] == "h" else b[1]
            corners.append((x, y))
        out.append(corners)
    got = Polygon(out[0], out[1:])
    return orient(got, 1.0) if got.is_valid and got.area > 0 else None


def _fill_shallow(poly):
    """The polygon with every recess and bump shallower than 12 in (two equal sides under 12 in) filled level."""
    def fill(pts):
        changed = True
        while changed and len(pts) > 4:
            changed = False
            n = len(pts)
            for i in range(n):
                v = [pts[(i + k) % n] for k in range(-1, 3)]           # v[0] .. v[3]: the sides v0v1, v1v2, v2v3
                a, b = math.dist(v[0], v[1]), math.dist(v[2], v[3])
                if a >= SHALLOW or b >= SHALLOW or abs(a - b) > SAME:
                    continue
                turn = [_turn(pts[(i + k - 1) % n], pts[(i + k) % n], pts[(i + k + 1) % n]) for k in range(-1, 3)]
                # v1, v2 turning the same way, v0 and v3 the other: a notch (recess or bump), its sides antiparallel
                if turn[1] * turn[2] > 0 and turn[0] * turn[1] < 0 and turn[3] * turn[2] < 0:
                    for idx in sorted([i % n, (i + 1) % n], reverse=True):
                        del pts[idx]
                    pts[:] = _drop_collinear(pts)
                    changed = True
                    break
        return pts

    ext = fill([tuple(p) for p in list(poly.exterior.coords)[:-1]])
    holes = [fill([tuple(p) for p in list(h.coords)[:-1]]) for h in poly.interiors]
    got = Polygon(ext, holes)
    return orient(got, 1.0)


def _turn(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])


# --- the legs --------------------------------------------------------------------------------------------------------

@dataclass
class _LegShape:
    rect: tuple                # x0, x1, y0, y1 (frame)
    horizontal: bool           # runs along x
    proper: list               # along intervals where both its walls are walls
    kept: tuple = (0.0, 0.0)   # the along range its centre line keeps
    family: int = -1           # legs joined by steps (one corridor widening, narrowing or jogging) share it
    members: int = 1           # how many rectangles it was made of (walls stepping by under 12 in)
    running: list = field(default_factory=list)   # along intervals where its centre line runs
    gone: list = field(default_factory=list)   # along intervals where its centre line doesn't run (a wider leg's)
    frame: object = None

    @property
    def line(self) -> float:   # the centre line's across coordinate
        x0, x1, y0, y1 = self.rect
        return (y0 + y1) / 2 if self.horizontal else (x0 + x1) / 2

    @property
    def span(self) -> tuple:   # along
        x0, x1, y0, y1 = self.rect
        return (x0, x1) if self.horizontal else (y0, y1)

    @property
    def across(self) -> tuple:
        x0, x1, y0, y1 = self.rect
        return (y0, y1) if self.horizontal else (x0, x1)

    def point(self, u) -> tuple:
        return (u, self.line) if self.horizontal else (self.line, u)

    def along(self, p) -> float:
        return p[0] if self.horizontal else p[1]


def _own(inside, i0, i1, j0, j1, nx, ny, xs, ys, horizontal) -> list:
    """The along intervals of the rectangle (cells i0..i1, j0..j1) where both its sides along `horizontal` are walls
    (its own stretch): a side is a wall where no floor lies beyond it, or only floor less than 12 in deep (a wall
    stepping back by under 12 in, a door's recess)."""
    def shallow_beyond(i, j, step):            # the floor beyond cell (i, j), the way `step`, is under 12 in deep
        k = j
        while 0 <= k + step < (ny if horizontal else nx) and (inside[i, k + step] if horizontal else
                                                                inside[k + step, i]):
            k += step
        if k == j:
            return True
        marks = ys if horizontal else xs
        edge = marks[j] if step < 0 else marks[j + 1]
        far = marks[k] if step < 0 else marks[k + 1]
        return abs(edge - far) < SHALLOW

    if horizontal:
        ok = [shallow_beyond(i, j0, -1) and shallow_beyond(i, j1 - 1, 1) for i in range(i0, i1)]
        marks = xs[i0:i1 + 1]
    else:
        ok = [shallow_beyond(j, i0, -1) and shallow_beyond(j, i1 - 1, 1) for j in range(j0, j1)]
        marks = ys[j0:j1 + 1]
    proper = []
    for k, good in enumerate(ok):
        if not good:
            continue
        if proper and abs(proper[-1][1] - marks[k]) <= 1e-9:
            proper[-1] = (proper[-1][0], marks[k + 1])
        else:
            proper.append((marks[k], marks[k + 1]))
    return proper


def _legs(poly) -> list[_LegShape]:
    """The straight stretches of a square polygon: each maximal rectangle with a stretch where both its long sides are
    walls (its own stretch), a leg along its longer side; a square one with an own stretch both ways runs neither
    way (Stop). A maximal rectangle with no own stretch (two walls that never face each other across it) is no leg;
    every part of the floor must lie in some leg (else Stop). Then legs side by side whose walls differ by less than
    12 in on each side (a wall stepping in or out by under 12 in) are one leg: its walls the outermost, its own
    stretches theirs together."""
    xs = sorted({round(x, 9) for ring in [poly.exterior, *poly.interiors] for x, _ in ring.coords})
    ys = sorted({round(y, 9) for ring in [poly.exterior, *poly.interiors] for _, y in ring.coords})
    nx, ny = len(xs) - 1, len(ys) - 1
    cx = np.array([(xs[i] + xs[i + 1]) / 2 for i in range(nx)])
    cy = np.array([(ys[j] + ys[j + 1]) / 2 for j in range(ny)])
    gx, gy = np.meshgrid(cx, cy, indexing="ij")
    inside = shapely.contains_xy(poly, gx, gy)                  # inside[i, j]
    rects = []
    for j0 in range(ny):
        col = np.ones(nx, dtype=bool)
        for j1 in range(j0 + 1, ny + 1):
            col &= inside[:, j1 - 1]
            if not col.any():
                break
            i = 0
            while i < nx:
                if not col[i]:
                    i += 1
                    continue
                i0 = i
                while i < nx and col[i]:
                    i += 1
                i1 = i
                down = j0 > 0 and inside[i0:i1, j0 - 1].all()
                up = j1 < ny and inside[i0:i1, j1].all()
                if not (down or up):
                    rects.append((i0, i1, j0, j1))
    out, covered = [], np.zeros_like(inside)
    for i0, i1, j0, j1 in rects:
        x0, x1, y0, y1 = xs[i0], xs[i1], ys[j0], ys[j1]
        w, h = x1 - x0, y1 - y0
        # the way(s) its two walls face each other over 12 in or more (less is a door's lip or a wall's end), with no
        # nearer wall between them
        got = [_LegShape((x0, x1, y0, y1), hz, own) for hz in (True, False)
               for own in [_own(inside, i0, i1, j0, j1, nx, ny, xs, ys, hz)] if any(q - p >= SHALLOW for p, q in own)]
        got = [g for g in got if _faces(poly, g)]
        if len(got) == 2:
            if abs(w - h) <= SAME:
                raise Stop("corridor_not_legs", why=f"a part of it {_ft(w)} ft square runs neither way")
            got = [g for g in got if g.horizontal == (w > h)]
        if not got:
            continue                                        # no two walls face each other across it: no leg
        leg = got[0]
        covered[i0:i1, j0:j1] = True
        out.append(leg)
    if (inside & ~covered).any():                          # a corner of floor in no leg: within 12 in of one (a lip,
        near = unary_union([box(m.rect[0], m.rect[2], m.rect[1], m.rect[3]) for m in out]).buffer(
            SHALLOW, join_style=2)                         # a wall's end), else not worked out
        for i, j in zip(*np.nonzero(inside & ~covered)):
            if not near.covers(box(xs[i], ys[j], xs[i + 1], ys[j + 1])):
                raise Stop("corridor_not_legs", why="a part of it lies between no two walls facing each other")
    return _bundle(out)


def _islands(members, frame, legs) -> None:
    """A hole, or an obstruction clear of every wall, longer than the leg holding it is wide: the corridor runs round
    both sides of it, two passages the legs' centre lines don't follow (Stop). A column or a table narrower than
    that is in the way, never an island: it narrows the width."""
    for m in members:
        walls = m.outline.boundary
        for o in [*m.holes, *[o for o in m.obstructions if o.distance(walls) > SAME]]:
            x0, y0, x1, y1 = Polygon([frame.to(c) for c in o.exterior.coords]).bounds
            mid = ((x0 + x1) / 2, (y0 + y1) / 2)
            held = [leg for leg in legs if _in_rect(leg, mid)]
            if held and max(x1 - x0, y1 - y0) > min(leg.across[1] - leg.across[0] for leg in held) + SAME:
                raise Stop("corridor_not_legs", why="it runs round both sides of an island (a hole, or an obstruction "
                                                    "clear of the walls, longer than the corridor is wide)")


def _faces(poly, leg) -> bool:
    """Whether the leg's two walls face each other across it: somewhere along its own stretch its centre line is at
    least half its width, less 12 in, from every wall (else a nearer wall lies between them and the rectangle is the
    side of a wider floor, never a stretch of corridor)."""
    w0, w1 = leg.across
    need = (w1 - w0) / 2 - SHALLOW
    if need <= 0:
        return True
    near = poly.boundary.buffer(need, quad_segs=16)
    for p, q in leg.proper:
        line = LineString([leg.point(p), leg.point(q)])
        if line.difference(near).length > SAME:
            return True
    return False


def _bundle(legs) -> list[_LegShape]:
    """Legs along one line whose walls differ by less than 12 in on each side, overlapping along: one leg (a step in
    or out of a wall shallower than 12 in moves no centre line, as a recess under 12 in moves none)."""
    top = list(range(len(legs)))

    def find(k):
        while top[k] != k:
            top[k] = top[top[k]]
            k = top[k]
        return k

    for i, a in enumerate(legs):
        for j in range(i + 1, len(legs)):
            b = legs[j]
            if a.horizontal != b.horizontal:
                continue
            if min(a.span[1], b.span[1]) - max(a.span[0], b.span[0]) <= SAME:
                continue
            if abs(a.across[0] - b.across[0]) < SHALLOW and abs(a.across[1] - b.across[1]) < SHALLOW:
                top[find(i)] = find(j)
    groups = {}
    for k in range(len(legs)):
        groups.setdefault(find(k), []).append(legs[k])
    out = []
    for members in groups.values():
        if len(members) == 1:
            out.append(members[0])
            continue
        lo, hi = min(m.span[0] for m in members), max(m.span[1] for m in members)
        w0, w1 = min(m.across[0] for m in members), max(m.across[1] for m in members)
        if any(m.across[0] - w0 >= SHALLOW or w1 - m.across[1] >= SHALLOW for m in members):
            raise Stop("corridor_not_legs", why="the walls of one of its stretches step by 12 in or more in all")
        hz = members[0].horizontal
        rect = (lo, hi, w0, w1) if hz else (w0, w1, lo, hi)
        proper = []
        for p, q in sorted(iv for m in members for iv in m.proper):
            if proper and p <= proper[-1][1] + 1e-9:
                proper[-1] = (proper[-1][0], max(proper[-1][1], q))
            else:
                proper.append((p, q))
        out.append(_LegShape(rect, hz, proper, members=len(members)))
    return out


def _ft(x) -> str:
    return f"{x / 12:.2f}".rstrip("0").rstrip(".")


def _overlap(a: _LegShape, b: _LegShape) -> float:
    ax0, ax1, ay0, ay1 = a.rect
    bx0, bx1, by0, by1 = b.rect
    return max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(0.0, min(ay1, by1) - max(ay0, by0))


def _joins(legs, floor) -> tuple:
    """How the legs' centre lines meet. Crossings: (i, j, point) for two legs at right angles that overlap, their
    centre lines crossing there (Stop if they don't). Steps: (i, j, lo, hi) for two legs along one way that overlap
    or meet end to end (a widening, a narrowing or a jog): their centre lines are joined at right angles, at the ends
    of the stretch [lo, hi] where both run and at every crossing of either inside it."""
    crossings, steps = [], []
    for i, a in enumerate(legs):
        for j in range(i + 1, len(legs)):
            b = legs[j]
            if a.horizontal == b.horizontal:
                lo, hi = max(a.span[0], b.span[0]), min(a.span[1], b.span[1])
                touch = min(a.across[1], b.across[1]) - max(a.across[0], b.across[0])
                if hi - lo >= -SAME and touch > SAME and (hi - lo > SAME or touch > SAME):
                    steps.append((i, j, min(lo, hi), max(lo, hi)))
                continue
            h, v = (a, b) if a.horizontal else (b, a)
            x, y = v.line, h.line
            if _overlap(a, b) <= SAME * SAME:
                # an end opening, within 12 in (past a lip or a wall's end), on the other leg: its centre line runs on
                # straight across that floor to the other's
                for k, (p, q) in ((0, (v, h)), (1, (h, v))):
                    run = _run_on(floor, p, q)
                    if run is not None:
                        crossings.append((i, j, (x, y)))
                        break
                continue
            if not (h.span[0] - SAME <= x <= h.span[1] + SAME and v.span[0] - SAME <= y <= v.span[1] + SAME):
                raise Stop("corridor_not_legs", why="two of its stretches meet without their centre lines crossing")
            crossings.append((i, j, (x, y)))
    return crossings, steps


def _run_on(floor, p: _LegShape, q: _LegShape):
    """Where p's centre line, run on straight past an end of p's rectangle, crosses q's (q at right angles to p): only
    when that end opens on floor reaching q's rectangle within 12 in, q's span holds p's line, and the run lies on the
    floor; else None."""
    lo, hi = q.across                     # where q's rectangle lies along p
    if not (q.span[0] - SAME <= p.line <= q.span[1] + SAME):
        return None
    for end, way in ((0, -1), (1, 1)):
        u = p.span[end]
        gap = (lo - u) if way > 0 else (u - hi)
        if not (-SAME <= gap <= SHALLOW + SAME) or _walled(floor, p, u, way):
            continue
        target = q.line
        run = LineString([p.point(u), p.point(target)])
        if floor.buffer(SAME).covers(run):
            return target
    return None


def _find(top, k) -> int:
    while top[k] != k:
        top[k] = top[top[k]]
        k = top[k]
    return k


def _less(intervals, out) -> list:
    """The intervals with every interval of `out` taken away (pieces under 1/16 in dropped)."""
    got = []
    for a, b in intervals:
        pieces = [(a, b)]
        for c, d in out:
            pieces = [q for x, y in pieces for q in ((x, min(y, c)), (max(x, d), y)) if q[1] - q[0] > SAME]
        got += pieces
    return got


def _in_rect(leg, p) -> bool:
    x0, x1, y0, y1 = leg.rect
    return x0 - SAME <= p[0] <= x1 + SAME and y0 - SAME <= p[1] <= y1 + SAME


def _proper_in(leg, a, b) -> float:
    return sum(max(0.0, min(b, q) - max(a, p)) for p, q in leg.proper)


# --- the graph -------------------------------------------------------------------------------------------------------

class _Graph:
    def __init__(self):
        self.xy, self.edges, self.adj = [], [], []     # edges: (u, v, length, leg index or None, (a, b) along)
        self.steps = {}                                # edge id -> (leg i, leg j, along): a step between two legs

    def node(self, p) -> int:
        for k, q in enumerate(self.xy):
            if math.dist(p, q) <= SAME:
                return k
        self.xy.append(tuple(p))
        self.adj.append([])
        return len(self.xy) - 1

    def edge(self, u, v, leg, along) -> bool:
        """Join u and v (False, and nothing added, where they are one node or already joined: two edges between one
        pair of nodes would be a loop of no floor, its two sides read as two ways)."""
        if u == v or any(v in self.edges[k][:2] for k in self.adj[u]):
            return False
        k = len(self.edges)
        self.edges.append((u, v, math.dist(self.xy[u], self.xy[v]), leg, along))
        self.adj[u].append(k)
        self.adj[v].append(k)
        return True

    def reach(self, start, att, cut_node=None, cut_edge=None) -> set:
        seen, stack, got = {start}, [start], set()
        while stack:
            n = stack.pop()
            for s in att.get(n, []):
                got |= s
            for k in self.adj[n]:
                if k == cut_edge:
                    continue
                u, v = self.edges[k][:2]
                w = v if u == n else u
                if w == cut_node or w in seen:
                    continue
                seen.add(w)
                stack.append(w)
        return got

    def component(self, start) -> set:
        seen, stack = {start}, [start]
        while stack:
            n = stack.pop()
            for k in self.adj[n]:
                u, v = self.edges[k][:2]
                w = v if u == n else u
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        return seen


def _two_ways(ways) -> bool:
    """Routes in two different directions each reach a distinct exit."""
    ways = [w for w in ways if w]
    return any(len(ways[i] | ways[j]) >= 2 for i in range(len(ways)) for j in range(i + 1, len(ways)))


def _dead_ends(g: _Graph, att: dict) -> dict:
    """{closed end node: (length, [edge ids walked]) or None (no point from it ends it)} under these attachments."""
    ends = {}
    node_end = {n: _two_ways([g.reach(g.edges[k][1] if g.edges[k][0] == n else g.edges[k][0], att, cut_node=n)
                              for k in g.adj[n]] + list(att.get(n, []))) for n in range(len(g.xy))}
    edge_end = [u != v and _two_ways([g.reach(u, att, cut_edge=k), g.reach(v, att, cut_edge=k)])
                for k, (u, v, *_) in enumerate(g.edges)]
    for leaf in range(len(g.xy)):
        if len(g.adj[leaf]) != 1 or att.get(leaf):
            continue
        dist, came = {leaf: 0.0}, {leaf: None}
        heap = [(0.0, leaf)]
        while heap:
            d, n = heapq.heappop(heap)
            if d > dist[n]:
                continue
            for k in g.adj[n]:
                u, v, w = g.edges[k][:3]
                m = v if u == n else u
                if d + w < dist.get(m, math.inf):
                    dist[m], came[m] = d + w, k
                    heapq.heappush(heap, (d + w, m))
        best = None
        for n, d in dist.items():
            if node_end[n] and (best is None or d < best[0]):
                best = (d, n)
        for k, (u, v, *_) in enumerate(g.edges):
            if edge_end[k]:
                for n in (u, v):
                    if n in dist and (best is None or dist[n] < best[0]):
                        best = (dist[n], n)
        if best is None:
            ends[leaf] = None
            continue
        walked, n = [], best[1]
        while came[n] is not None:
            k = came[n]
            walked.append(k)
            u, v = g.edges[k][:2]
            n = u if v == n else v
        ends[leaf] = (best[0], list(reversed(walked)))
    return ends


# --- widths ---------------------------------------------------------------------------------------------------------

def _clear(leg: _LegShape, a, b, blocks) -> float:
    """The least clear width across the leg between along a and b: its width less what the blocks cover across it
    there (each block by its extent across the leg, the less favourable side)."""
    w0, w1 = leg.across
    mine = []
    for x0, y0, x1, y1 in blocks:
        u0, u1, v0, v1 = (x0, x1, y0, y1) if leg.horizontal else (y0, y1, x0, x1)
        v0, v1 = max(v0, w0), min(v1, w1)
        if u1 > a and u0 < b and v1 > v0:
            mine.append((max(u0, a), min(u1, b), v0, v1))
    if not mine:
        return w1 - w0
    marks = sorted({a, b, *[m[0] for m in mine], *[m[1] for m in mine]})
    least = w1 - w0
    for p, q in zip(marks, marks[1:]):
        if q - p <= 1e-9:
            continue
        spans = sorted((v0, v1) for u0, u1, v0, v1 in mine if u0 < q and u1 > p)
        blocked, end = 0.0, w0
        for v0, v1 in spans:
            if v0 - end < SAME:            # a hairline gap (to a wall or between blocks) is no floor
                v0 = min(v0, end)
            if v1 > end:
                blocked += v1 - max(v0, end)
                end = v1
        if 0 < w1 - end < SAME:
            blocked += w1 - end
        least = min(least, w1 - w0 - blocked)
    return least


def _section_width(clear, leg, a, b) -> float:
    """The narrowest cross-section of the clear floor (the real floor less every obstruction and hole) across the
    leg's whole width between along a and b: sliced between each pair of corner places along the axis (of the
    walls, the recesses, the obstructions and the holes there), each slice's clear width across (its free pieces
    added), the least of them."""
    w0, w1 = leg.across
    lo, hi = min(a, b), max(a, b)
    if hi - lo <= 1e-9:
        return math.inf
    band = box(lo, w0, hi, w1) if leg.horizontal else box(w0, lo, w1, hi)
    piece = clear.intersection(band)
    marks = {lo, hi}
    for g in getattr(piece, "geoms", [piece]):
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        for ring in [g.exterior, *g.interiors]:
            marks |= {leg.along(c) for c in ring.coords if lo <= leg.along(c) <= hi}
    marks = sorted(marks)
    least = math.inf
    for p, q in zip(marks, marks[1:]):
        if q - p <= 1e-9:
            continue
        # within a slice every edge is straight, so the clear width changes linearly along it and is least at one of
        # its ends: cut just inside each end (a cut exactly on a mark can run along an edge), and at the middle
        d = min(1e-6, (q - p) / 4)
        for m in (p + d, (p + q) / 2, q - d):
            cut = LineString([(m, w0 - 1), (m, w1 + 1)] if leg.horizontal else [(w0 - 1, m), (w1 + 1, m)])
            least = min(least, cut.intersection(piece).length)
    return least


def _dead_end_stretches(leg, a, b) -> list:
    """The along ranges of a walked edge that are the dead end's own: the leg's own stretch (both walls walls), and
    any part beyond the leg's rectangle (a recess at the closed end); never a crossing's floor."""
    lo, hi = min(a, b), max(a, b)
    out = [(max(lo, p), min(hi, q)) for p, q in leg.proper]
    s0, s1 = leg.span
    out += [(lo, min(hi, s0)), (max(lo, s1), hi)]
    return [(p, q) for p, q in out if q - p > 1e-9]


def _least_width(legs, g, walked, floors, floor_of, start_floor, start) -> float:
    """A dead end's least width (one function, review round 5): the narrowest cross-section of the clear floor
    within the dead end's band, over its own stretches from its closed end (recess included) to its far end, each
    leg with its own floor. A dead end of no length (or walked only in crossings): the leg it starts in."""
    widths = []
    for k in walked:
        _, _, _, li, (a, b) = g.edges[k]
        if k in g.steps:                                 # a step walked: the part of the two widths they share there
            i, j, u = g.steps[k]
            w0, w1 = max(legs[i].across[0], legs[j].across[0]), min(legs[i].across[1], legs[j].across[1])
            throat = _LegShape(legs[i].rect, legs[i].horizontal, [])
            throat.rect = (u - SAME, u + SAME, w0, w1) if legs[i].horizontal else (w0, w1, u - SAME, u + SAME)
            widths.append(_section_width(floors[floor_of[i]].clear, throat, u - SAME, u + SAME))
            continue
        if li is None:
            continue
        leg, clear = legs[li], floors[floor_of[li]].clear
        widths += [_section_width(clear, leg, p, q) for p, q in _dead_end_stretches(leg, a, b)]
    if not widths:
        floor = floors[start_floor]
        for li in floor.legs:
            leg = legs[li]
            x0, x1, y0, y1 = leg.rect
            if x0 - SAME <= start[0] <= x1 + SAME and y0 - SAME <= start[1] <= y1 + SAME:
                widths += [_section_width(floor.clear, leg, p, q) for p, q in leg.proper]
    widths = [w for w in widths if math.isfinite(w)]
    return min(widths) if widths else 0.0


# --- the whole story -------------------------------------------------------------------------------------------------

@dataclass
class _Floor:
    """One floor of corridors joined by passages, turned square."""
    rooms: list
    frame: _Frame
    legs: list                 # indices into the story's legs
    blocks: list               # (x0, y0, x1, y1) in the frame: what narrows its width (the corridor's width)
    clear: object = None       # the real floor less every obstruction and hole, in the frame (the dead ends' width)
    plain: bool = True         # straight legs at right angles only (no step, no group of legs, no centre line run on)


def corridors(story: Story, uses: dict, routes: StoryRoutes | None) -> dict:
    """Every corridor room on the story (a room marked `corridor`, read): its width and dead ends, or why not. Never
    raises out of the story: anything unexpected becomes each corridor's needs-review reason (and is logged)."""
    try:
        return _corridors(story, uses, routes)
    except Stop:
        raise
    except Exception as e:                                 # never a crash of the whole story
        logging.getLogger(__name__).exception("dead ends not worked out")
        why = Stop("corridor_not_legs", why=f"working them out failed: {type(e).__name__}: {e}").reason
        out = {}
        for k, r in story.rooms.items():
            if r is not None and uses.get(k) == "corridor":
                out[k] = Corridor(k, stop=why, width_stop=why)
        return out


def _corridors(story: Story, uses: dict, routes: StoryRoutes | None) -> dict:
    """Every corridor room on the story (a room marked `corridor`, read): its width and dead ends, or why not.
    `routes` (the story's StoryRoutes) is needed for the dead ends; without it, only the widths."""
    rooms = {k: r for k, r in story.rooms.items() if r is not None and uses.get(k) == "corridor"}
    out = {k: Corridor(k) for k in rooms}
    if not rooms:
        return out
    if story.stops:
        why = Stop("story_not_measured", reasons="; ".join(story.stops)).reason
        for c in out.values():
            c.stop = c.width_stop = why
        return out
    top = {k: k for k in rooms}

    def find(k):
        while top[k] != k:
            k = top[k]
        return k

    for a, b, _ in story.passages:           # crossable corridors joined by passages make one floor
        if a in top and b in top and rooms[a].crossable and rooms[b].crossable:
            top[find(a)] = find(b)
    groups = {}
    for k in sorted(rooms):
        groups.setdefault(find(k), []).append(k)

    g, legs, floors, floor_of = _Graph(), [], {}, {}
    for key, members in groups.items():
        crossable = rooms[members[0]].crossable
        if not crossable:
            out[members[0]].stop = Stop("corridor_end_only", name=rooms[members[0]].name,
                                        why=rooms[members[0]].end_only_why).reason
        try:
            # a corridor a route can't cross: its width from its own floor, never on the dead ends' graph
            floor = _group(story, [rooms[m] for m in members], g if crossable else _Graph(), legs)
        except Stop as s:
            for m in members:
                out[m].width_stop = s.reason
                out[m].stop = out[m].stop or s.reason
            continue
        for m in members:
            _width(out[m], rooms[m], floor, legs, g if crossable else None)
        if crossable:
            floors[key] = floor
            for li in floor.legs:
                floor_of[li] = key
    if not floors or routes is None:
        return out
    in_floor = {m: key for key, f in floors.items() for m in f.rooms}
    try:
        ways_out = _ways_out(story, routes, set(in_floor))
    except Stop as s:
        for m in in_floor:
            out[m].stop = out[m].stop or s.reason
        return out
    att = {WITHOUT: {}, WITH: {}}
    for door in story.doors.values():
        mine = [k for k in door.face if k in in_floor]
        if not mine:
            continue
        nodes = [_attach(g, legs, floor_of, in_floor[k], floors[in_floor[k]].frame, door) for k in mine]
        if any(n is None for n in nodes):
            for k in mine:
                out[k].stop = out[k].stop or Stop("door_off_legs", name=door.name).reason
            continue
        if door.exit_kind:
            for reading in att.values():
                reading.setdefault(nodes[0], []).append({door.exit_id})
        elif len(nodes) == 2:                            # a door between two corridors: straight across it
            g.edge(nodes[0], nodes[1], None, (0.0, 0.0))
        else:
            other = next((s for s in door.sides if s not in in_floor), None)
            ways = ways_out.get((door.id, other), set())
            if ways:
                att[WITH].setdefault(nodes[0], []).append(ways)
    found = {reading: _dead_ends(g, a) for reading, a in att.items()}
    owner = {n: _owner(g, n, floor_of) for n in range(len(g.xy))}
    for leaf, got in found[WITHOUT].items():
        key = owner[leaf]
        if key is None:                                    # a closed end on no leg: never a guess
            why = Stop("corridor_not_legs", why="a closed end of its centre lines lies on no stretch").reason
            for n in g.component(leaf):
                for m in (floors[owner[n]].rooms if owner[n] is not None else []):
                    out[m].stop = out[m].stop or why
            for m in in_floor:
                if in_floor[m] in {owner[n] for n in g.component(leaf)}:
                    out[m].stop = out[m].stop or why
            continue
        floor = floors[key]
        start = g.xy[leaf]
        # the room holding the closed end (a point on the leg's axis, which may lie off the floor beside a recess
        # in the end wall: then the nearest of the floor's rooms, within the 12 in a recess can reach)
        near = min(floor.rooms, key=lambda m: rooms[m].outline.distance(Point(start)))
        room = near if rooms[near].outline.distance(Point(start)) <= SHALLOW + 2 * SAME else None
        if got is None or room is None:
            why = (Stop("dead_end_unbounded", x=_show(start)[0], y=_show(start)[1]).reason if got is None else
                   Stop("door_off_legs", name=f"at the closed end ({_show(start)[0]}, {_show(start)[1]})").reason)
            for n in g.component(leaf):
                if owner[n] is not None:
                    for m in floors[owner[n]].rooms:
                        out[m].stop = out[m].stop or why
            continue
        de = DeadEnd(start, room, {}, {}, {})
        for reading in (WITHOUT, WITH):
            length, walked = got if reading == WITHOUT else (found[WITH].get(leaf) or (0.0, []))
            length, walked = _to_point_c(g, legs, leaf, length, walked, att[reading])
            length, line = _to_gone_lines(g, legs, leaf, length, walked, _walked_line(g, leaf, walked))
            de.length[reading] = length
            de.width[reading] = _least_width(legs, g, walked, floors, floor_of, key, floor.frame.to(start))
            de.line[reading] = line
        out[room].dead_ends.append(de)
    return out


def _to_point_c(g, legs, leaf, length, walked, att) -> tuple:
    """A dead end that ends where its own centre line crosses another's runs on, along its own centre line and still
    out of its own stretch (inside the crossing corridor's floor), to the farthest centre line at right angles to it
    that it crosses there: NFPA 101 A.7.5.1.5 measures to "point C, located at the centerline of the corridor", and
    where the crossing corridor widens or its walls step, it has more than one; the farthest is the cautious one
    (open question 2). It never runs past an exit."""
    if not walked:
        return length, walked
    n = leaf
    for k in walked:
        u, v = g.edges[k][:2]
        n = v if u == n else u
    li = g.edges[walked[-1]][3]
    if li is None or not _crosses_at(g, legs, n, li):
        return length, walked
    families = _crosses_at(g, legs, n, li)             # the crossing corridor: its legs, and those stepping from them
    best, run, came, extra = (length, list(walked)), list(walked), walked[-1], 0.0
    while not att.get(n):
        nxt = [k for k in g.adj[n] if k != came and g.edges[k][3] == li]
        if not nxt:
            break
        k = nxt[0]
        u, v, w, _, (m0, m1) = g.edges[k]
        if _proper_in(legs[li], min(m0, m1), max(m0, m1)) > SAME:
            break                                          # its own walls again: past the crossing corridor
        n, came, extra = (v if u == n else u), k, extra + w
        run.append(k)
        if _crosses_at(g, legs, n, li) & families:
            best = (length + extra, list(run))
    return best


def _to_gone_lines(g, legs, leaf, length, walked, line) -> tuple:
    """Point C on a centre line that doesn't run where the dead end crosses it (the crossing corridor's own centre
    line, running on both sides of a widening in it: one corridor has one centre line at each place, the widened
    stretch's): the dead end runs on, straight along its own centre line and still out of its own stretch, to the farthest such line of
    the crossing corridor (its family) that its leg's rectangle reaches. (length, the line walked)."""
    if not walked:
        return length, line
    li = g.edges[walked[-1]][3]
    if li is None:
        return length, line
    d = legs[li]
    end = d.frame.to(line[-1])
    u0, before = d.along(end), d.along(d.frame.to(line[-2]))
    way = 1 if u0 >= before else -1
    families = _crosses_at(g, legs, _node_at(g, line[-1]), li)
    best = 0.0
    for m in legs:
        if m.family not in families or m.horizontal == d.horizontal or m.frame is not d.frame:
            continue
        # a widening in its middle: its centre line runs on both sides (never past its end into a wider stretch)
        if not any(a - SAME <= d.line <= b + SAME and m.kept[0] < a - SAME and b + SAME < m.kept[1] for a, b in m.gone):
            continue
        c = m.line
        if way * (c - u0) <= SAME or not (d.span[0] - SAME <= c <= d.span[1] + SAME):
            continue
        if _proper_in(d, min(u0, c), max(u0, c)) > SAME:
            continue
        best = max(best, abs(c - u0))
    if best <= 0:
        return length, line
    return length + best, line + [d.frame.back(d.point(u0 + way * best))]


def _node_at(g, p) -> int:
    return min(range(len(g.xy)), key=lambda k: math.dist(g.xy[k], p))


def _crosses_at(g, legs, n, li) -> set:
    """The families (legs joined by steps) of the legs at right angles to leg li whose centre lines pass through n."""
    return {legs[g.edges[k][3]].family for k in g.adj[n]
            if g.edges[k][3] is not None and legs[g.edges[k][3]].horizontal != legs[li].horizontal}


def _show(p):
    return round(p[0] / 12, 3) + 0.0, round(p[1] / 12, 3) + 0.0


def _walked_line(g, leaf, walked) -> list:
    pts, n = [g.xy[leaf]], leaf
    for k in walked:
        u, v = g.edges[k][:2]
        n = v if u == n else u
        pts.append(g.xy[n])
    return pts


def _owner(g, n, floor_of):
    for k in g.adj[n]:
        li = g.edges[k][3]
        if li is not None:
            return floor_of.get(li)
    return None


def _width(corridor: Corridor, room, floor: _Floor, legs, g) -> None:
    """The least clear width over the legs' own stretches in this room, and the centre lines drawn in it. Where the
    corridors' floor isn't plain straight legs at right angles (a wall stepping, a widening, a jog, a centre line run
    on past a lip): needs review (decision 6, amended 2026-11-22)."""
    if g is not None:
        corridor.centre_lines = [(g.xy[u], g.xy[v]) for u, v, _, li, _ in g.edges
                                 if li in floor.legs and u != v
                                 and room.outline.buffer(2 * SAME).covers(LineString([g.xy[u], g.xy[v]]).centroid)]
    if not floor.plain:
        corridor.width_stop = Stop("corridor_width_stepped").reason
        return
    widths = []
    for li in floor.legs:
        leg = legs[li]
        for p, q in leg.proper:
            piece = _rect_back(floor.frame, leg, p, q).intersection(room.outline)
            if piece.area <= SAME * SAME:
                continue
            lo, hi = _along_bounds(floor.frame, leg, piece)
            if min(hi, q) - max(lo, p) > 1e-9:
                widths.append(_clear(leg, max(lo, p), min(hi, q), floor.blocks))
    if widths:
        corridor.width = min(widths)
    else:
        corridor.width_stop = Stop("corridor_not_legs", why="none of its legs' own stretches is in it").reason


def _rect_back(frame, leg, p, q) -> Polygon:
    w0, w1 = leg.across
    corners = [(p, w0), (q, w0), (q, w1), (p, w1)] if leg.horizontal else [(w0, p), (w1, p), (w1, q), (w0, q)]
    return Polygon([frame.back(c) for c in corners])


def _along_bounds(frame, leg, piece) -> tuple:
    vals = [leg.along(frame.to(c)) for part in getattr(piece, "geoms", [piece]) if hasattr(part, "exterior")
            for c in part.exterior.coords]
    return min(vals), max(vals)


def _group(story, members, g, legs_all) -> _Floor:
    """One floor of corridors joined by passages: its legs (added to legs_all) and centre lines (added to g, in plan)."""
    ids = {m.id for m in members}
    lines = [seg for a, b, seg in story.passages if a in ids and b in ids]
    whole = unary_union([m.outline for m in members] + [seg.buffer(SAME, cap_style="flat") for seg in lines])
    # slivers thinner than 1/16 in (a hairline gap in a wall) are no floor: they neither lengthen nor narrow anything
    whole = whole.buffer(-SAME / 2, join_style=2).buffer(SAME / 2, join_style=2)
    if whole.geom_type != "Polygon":
        raise Stop("corridor_not_legs", why="its rooms joined by passages don't make one floor")
    edges = list(zip(whole.exterior.coords[:-1], whole.exterior.coords[1:]))
    a, b = max(edges, key=lambda e: math.dist(*e))
    frame = _Frame(math.atan2(b[1] - a[1], b[0] - a[0]))
    square = _square(whole, frame)
    if square is None:
        raise Stop("corridor_not_legs", why="its walls don't all meet at right angles")
    filled = _fill_shallow(square)
    legs = _legs(filled)
    _islands(members, frame, legs)
    crossings, steps = _joins(legs, filled)
    # plain: straight legs at right angles, as decision 6 first had them (else the corridor's width needs review)
    plain = all(leg.members == 1 for leg in legs) and not any(
        _overlap(legs[i], legs[j]) <= SAME * SAME for i, j, _ in crossings)
    base = len(legs_all)
    # each leg's centre line, cut at its crossings and steps, its ends past the last cut kept only with its own stretch
    at = {i: [] for i in range(len(legs))}
    for i, j, p in crossings:
        at[i].append(legs[i].along(p))
        at[j].append(legs[j].along(p))
    step_at, fam = [], list(range(len(legs)))
    gone = {i: [] for i in range(len(legs))}           # along intervals where a leg's centre line doesn't run
    for i, j, lo, hi in steps:
        # an end of the stretch where both legs end against one wall: each a closed end there, never joined
        ends = {u for u in (lo, hi) if not all(any(abs(u - e) <= SAME and _walled(filled, legs[k], e, way)
                                                   for e, way in ((legs[k].span[0], -1), (legs[k].span[1], 1)))
                                               for k in (i, j))}
        where = ends | {u for u in at[i] + at[j] if lo - SAME <= u <= hi + SAME}
        if all(any(leg.horizontal != legs[i].horizontal and _in_rect(leg, legs[i].point(u))
                   and _in_rect(leg, legs[j].point(u)) for leg in legs) for u in (lo, (lo + hi) / 2, hi)):
            continue                                       # side by side inside a leg at right angles: it joins them
        if hi - lo > SAME:
            # one corridor has one centre line at each place: where a narrower leg runs inside a wider one (a
            # widening, a narrowing), the wider's alone; where two run side by side, neither inside the other (a
            # jog that overlaps), each to the middle of the stretch both run, joined there
            (a0, a1), (b0, b1) = legs[i].across, legs[j].across
            inner = i if a0 >= b0 - SAME and a1 <= b1 + SAME else j if b0 >= a0 - SAME and b1 <= a1 + SAME else None
            if inner is not None:
                gone[inner].append((lo, hi))
                where = ends
            else:
                m = (lo + hi) / 2
                for k in (i, j):
                    low = legs[k].span[0] < lo - SAME
                    if low == (legs[k].span[1] > hi + SAME):
                        raise Stop("corridor_not_legs", why="two of its stretches run side by side")
                    gone[k].append((m, hi) if low else (lo, m))
                where = {m}
        # never inside a leg at right angles to the two: its centre line joins them there
        where = {u for u in where if not any(leg.horizontal != legs[i].horizontal and _in_rect(leg, legs[i].point(u))
                                             and _in_rect(leg, legs[j].point(u)) for leg in legs)}
        step_at.append((i, j, sorted(where)))
        if where:
            fam[_find(fam, i)] = _find(fam, j)
        at[i] += where
        at[j] += where
    # a crossing where either centre line doesn't run is no crossing: the cuts made again from the rest
    at = {i: [] for i in range(len(legs))}
    for i, j, p in crossings:
        if not any(any(a + SAME < legs[k].along(p) < b - SAME for a, b in _less(gone[k], legs[k].proper))
                   for k in (i, j)):
            at[i].append(legs[i].along(p))
            at[j].append(legs[j].along(p))
    for i, j, where in step_at:
        at[i] += where
        at[j] += where
    mine, runs = [], []
    for i, leg in enumerate(legs):
        lo, hi = leg.span
        cuts = sorted(at[i])
        if cuts:
            if _proper_in(leg, lo, cuts[0]) <= SAME:
                lo = cuts[0]
            if _proper_in(leg, cuts[-1], hi) <= SAME:
                hi = cuts[-1]
        # an end kept at its rectangle's end with no cut there: a closed end (the floor beyond it walled across the
        # leg's whole width), run on to the real floor's end (a recess under 12 in was filled to find the legs, never
        # to move a closed end); floor beyond an end no other centre line reaches: not worked out
        for end, way in ((0, -1), (1, 1)):
            u = (lo, hi)[end]
            if abs(u - leg.span[end]) > 1e-9 or any(abs(c - u) <= SAME for c in cuts):
                continue
            if not _walled(filled, leg, u, way):
                raise Stop("corridor_not_legs", why="one of its stretches ends on floor no other stretch's centre "
                                                    "line reaches")
            if end == 0:
                lo = _to_real_end(square, leg, lo, -1)
            else:
                hi = _to_real_end(square, leg, hi, 1)
        leg.kept = (lo, hi)
        leg.family = base + _find(fam, i)
        leg.gone = _less(gone[i], leg.proper)
        leg.frame = frame
        legs_all.append(leg)
        # never a second centre line on the same line: what an earlier leg's already runs along is its
        same = [(a, b) for hz, line, _, a, b in runs if hz == leg.horizontal and abs(line - leg.line) <= SAME]
        pieces = _less(_less([(lo, hi)], leg.gone), same)
        # nor one beside another in the same stretch (their widths overlapping): two parallel centre lines in one
        # corridor make a loop, whose two sides would be read as two ways
        for hz, line, across, a, b in runs:
            if hz != leg.horizontal or abs(line - leg.line) <= SAME:
                continue
            if min(across[1], leg.across[1]) - max(across[0], leg.across[0]) <= SAME:
                continue
            if any(min(b, d) - max(a, c) > SAME for c, d in pieces):
                raise Stop("corridor_not_legs", why="two of its centre lines run side by side in one stretch")
        runs += [(leg.horizontal, leg.line, leg.across, a, b) for a, b in pieces]
        leg.running = pieces                               # where its centre line runs (gone and doubled taken away)
        for a, b in pieces:
            marks = sorted({a, b, *[c for c in cuts if a <= c <= b]})
            nodes = [g.node(frame.back(leg.point(u))) for u in marks]
            mine += nodes
            for (u, v), (m0, m1) in zip(zip(nodes, nodes[1:]), zip(marks, marks[1:])):
                g.edge(u, v, base + i, (m0, m1))
    for i, j, where in step_at:                            # the steps: straight across, at right angles
        for u in where:
            if not (legs[i].kept[0] - SAME <= u <= legs[i].kept[1] + SAME and
                    legs[j].kept[0] - SAME <= u <= legs[j].kept[1] + SAME):
                continue
            if not all(any(a - SAME <= u <= b + SAME for a, b in legs[k].running) for k in (i, j)):
                continue                                   # a step only between two centre lines that run there
            a, b = g.node(frame.back(legs[i].point(u))), g.node(frame.back(legs[j].point(u)))
            seg = LineString([g.xy[a], g.xy[b]])
            if any(n not in (a, b) and seg.distance(Point(q)) <= SAME for n, q in enumerate(g.xy)):
                raise Stop("corridor_not_legs", why="a step between two of its centre lines passes a third")
            k = len(g.edges)
            if g.edge(a, b, None, (0.0, 0.0)):
                g.steps[k] = (base + i, base + j, u)
            plain = False
    if mine and not set(mine) <= g.component(mine[0]):
        raise Stop("corridor_not_legs", why="its legs' centre lines don't all meet")
    for n in range(len(g.xy)):                             # every place on the graph lies on a centre line
        if g.adj[n] and not any(g.edges[k][3] is not None for k in g.adj[n]):
            raise Stop("corridor_not_legs", why="a step of its centre lines ends on none")
    # a loop of centre lines round floor alone (no wall inside it) would be read as two ways: never one corridor's
    mine_edges = [LineString([g.xy[u], g.xy[v]]) for u, v, _, li, _ in g.edges
                  if u != v and (u in mine or v in mine)]
    whole_floor = Polygon([frame.back(c) for c in filled.exterior.coords],
                          [[frame.back(c) for c in r.coords] for r in filled.interiors]).buffer(SAME)
    for face in getattr(polygonize(unary_union(mine_edges)), "geoms", []):
        if face.area > SAME * SAME and whole_floor.covers(face):
            raise Stop("corridor_not_legs", why="two of its centre lines run round floor with no wall inside")
    # what narrows the width: obstructions, columns, and the bumps filled in finding the legs
    blocks = []
    for m in members:
        for o in m.obstructions + m.holes:
            blocks.append(Polygon([frame.to(c) for c in o.exterior.coords]).bounds)
    bumps = filled.difference(square)
    for piece in getattr(bumps, "geoms", [bumps]):
        if not piece.is_empty and piece.area > SAME * SAME:
            blocks.append(piece.bounds)
    cut = [Polygon([frame.to(c) for c in o.exterior.coords]) for m in members for o in m.obstructions + m.holes]
    clear = square.difference(unary_union(cut)) if cut else square
    # opened by 1/16 in as the walls were: a hairline between an obstruction and a wall is no floor (opening only
    # removes floor, so a width can only come out narrower)
    clear = clear.buffer(-SAME / 2, join_style=2).buffer(SAME / 2, join_style=2).intersection(square)
    return _Floor(sorted(ids), frame, list(range(base, base + len(legs))), blocks, clear, plain)


def _walled(filled, leg, u, way) -> bool:
    """Whether the floor ends at u, the way `way`, across the leg's whole width (no floor in a strip 1/16 in deep
    beyond it)."""
    w0, w1 = leg.across
    lo, hi = sorted((u, u + way * SAME))
    strip = box(lo, w0 + SAME, hi, w1 - SAME) if leg.horizontal else box(w0 + SAME, lo, w1 - SAME, hi)
    return filled.intersection(strip).area <= SAME * SAME


def _to_real_end(square, leg, u, way) -> float:
    """A closed end's place on the leg's axis: the farthest point of the real (unfilled) floor beyond u, the way
    `way`, within the leg's whole width (a recess under 12 in filled to find the legs, wherever it is in the end
    wall, counts: it is part of the dead end), or u itself. Walls only: an obstruction never shortens a dead end. A
    sliver thinner than 1/16 in is no floor (the floor was opened by 1/16 in)."""
    w0, w1 = leg.across
    reach = SHALLOW + 2 * SAME
    lo_, hi_ = sorted((u, u + way * reach))
    band = box(lo_, w0, hi_, w1) if leg.horizontal else box(w0, lo_, w1, hi_)
    got = band.intersection(square)
    best = u
    for part in getattr(got, "geoms", [got]):
        if part.is_empty or part.area <= 0:
            continue
        ends = [leg.along(c) for c in part.exterior.coords]
        if min(abs(e - u) for e in ends) > SAME:              # floor not opening off the end wall
            continue
        far = max(ends, key=lambda e: way * e)
        if way * far > way * best:
            best = far
    return best


def _attach(g, legs, floor_of, key, frame, door):
    """The node where a door in a corridor's wall meets the centre lines: the nearest point of the kept centre line
    of a leg whose rectangle (grown by half the wall) holds the door's centre."""
    c = frame.to(door.centre)
    reach = door.thickness / 2 + SAME
    best = None
    for li, leg in enumerate(legs):
        if floor_of.get(li) != key:
            continue
        x0, x1, y0, y1 = leg.rect
        if not (x0 - reach <= c[0] <= x1 + reach and y0 - reach <= c[1] <= y1 + reach):
            continue
        u = min(max(leg.along(c), leg.kept[0]), leg.kept[1])
        if any(a + SAME < u < b - SAME for a, b in leg.gone):
            continue                                       # its centre line doesn't run there: a wider leg's does
        d = math.dist(leg.point(u), c)
        if best is None or d < best[0]:
            best = (d, li, u)
    if best is None:
        return None
    _, li, u = best
    p = frame.back(legs[li].point(u))
    for n, q in enumerate(g.xy):
        if math.dist(p, q) <= SAME:
            return n
    for k, (a, b, w, eli, (m0, m1)) in enumerate(g.edges):      # split the edge of that leg holding it
        if eli == li and a != b and min(m0, m1) - SAME <= u <= max(m0, m1) + SAME:
            n = g.node(p)
            g.adj[a].remove(k)
            g.adj[b].remove(k)
            g.edges[k] = (a, a, 0.0, None, (0.0, 0.0))            # retired
            g.edge(a, n, eli, (m0, u))
            g.edge(n, b, eli, (u, m1))
            return n
    return None


def _ways_out(story: Story, routes: StoryRoutes, corridor_ids: set) -> dict:
    """{(door id, room id): the exit ids its room reaches by its other doors, without coming back into these
    corridors} for each door from one of them into a room (open question 7's other reading). Only routes that
    exist count (the rings kept): a way out missed only makes this reading longer, never a pass it shouldn't be."""
    keep = [z for z in story.zones if not set(z.rooms) & corridor_ids]
    sub = replace(story, zones=keep, zone_of={k: z for k, z in story.zone_of.items() if z in keep})
    other = StoryRoutes(sub, routes.r)
    other._engines = routes._engines                  # the zones' graphs, built once
    chains = {e: other._chain(frozenset([e]))[0] for e in other.exits}
    out = {}
    for door in story.doors.values():
        if door.exit_kind or not any(k in corridor_ids for k in door.face):
            continue
        for rid in door.face:
            if rid in corridor_ids:
                continue
            room = story.rooms[rid]
            if room.crossable:
                ways = {e for e, dist in chains.items() if math.isfinite(dist.get(door.id, math.inf))}
            else:
                own = region(story, [rid])
                leg = _Leg(own.floor, own.rings if routes.r > 0 else [], own.corners, routes.r)
                ways = set()
                for d in own.doors:
                    if d == door.id or any(k in corridor_ids for k in story.doors[d].face):
                        continue
                    reached = ({story.doors[d].exit_id} if story.doors[d].exit_kind else
                               {e for e, dist in chains.items() if math.isfinite(dist.get(d, math.inf))})
                    if reached and leg.tight(door.centre, story.doors[d].centre) is not None:
                        ways |= reached
            out[(door.id, rid)] = ways
    return out
