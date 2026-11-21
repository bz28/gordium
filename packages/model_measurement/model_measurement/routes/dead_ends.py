"""Dead ends and corridor widths, from the corridors' shape (decision 6 of docs/decisions/2026-11-20_route_measurement.md).

    corridors(story, uses, routes) -> {room id: Corridor(width, dead_ends, readings, stop, width_stop, ...)}

**The legs.** The corridors a route may cross (rooms marked `corridor` with `lockable: false`, decision 1a) joined by
passages make one floor; it must be made of straight legs meeting at right angles (at any rotation), else its dead
ends and widths need review in this first version. A recess, or a bump, shallower than 12 in (two equal sides under
12 in, such as a door's recess) is ignored in finding the legs (a bump still narrows the width). The floor, turned
square, is cut on every corner's x and y into cells; its legs are its maximal rectangles, each running along its
longer side between the two walls there, its **centre line** midway between them. A leg's own stretch (`proper`) is
where both those walls are walls; a centre line runs on past it, into a crossing, to where it crosses another leg's,
and a leg's end beyond its last crossing is kept only if some of its own stretch is there. Two legs that overlap side
by side (a widening) or overlap without their centre lines crossing are not straight legs at right angles.

**Where a dead end ends.** The centre lines make a graph. Reaching an exit means reaching, along it, a door of an
exit (`exit_kind`, by `exit_id`) in a corridor's wall (put on the centre line where it is nearest the door's centre),
or through a door between two such corridors (a straight line across it); a route through a room, or through a
corridor a route may not cross, never counts. A dead end runs along the centre lines from a closed end (an end of
the graph with no exit there) to the nearest point from which routes in two directions each reach a distinct exit
without coming back: a point of a centre line cut there whose two sides reach two distinct exits, a crossing two of
whose ways do, or an exit door in the corridor itself. Measured to the crossing's centre line, the longer reading
(open question 2). No such point from a closed end: its dead end isn't bounded, needs review.

**Open question 7.** A door into a room with another way out never ends a dead end. Where one would end it sooner,
each dead end has two named readings: without such doors (the defined value) and with them (a door into a room
whose other doors reach an exit, without coming back into these corridors, counts as a way to those exits).

**Widths.** A dead end's least width is the narrowest clear width across its own legs' stretches along it: the
leg's width less what obstructions, columns and bumps block across it (each by its extent across the leg: the less
favourable side). A corridor's width is the same over its own legs' stretches in it. Several dead ends in one
corridor: until the branch's `dead_end` part kind, the corridor gives the cautious pair, its longest dead end with
the least width of any of its dead ends, under each reading alike. Lengths in inches.
"""

import heapq
import math
from dataclasses import dataclass, field, replace

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

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

    def pair(self, reading) -> tuple:
        """(the longest dead end, the least width of any of its dead ends) under a reading; no dead end: (0, the
        corridor's width)."""
        mine = [d for d in self.dead_ends if d.room == self.room]
        if not mine:
            return 0.0, self.width
        return max(d.length[reading] for d in mine), min(d.width[reading] for d in mine)


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


def _legs(poly) -> list[_LegShape]:
    """The maximal rectangles of a square polygon, each a leg along its longer side (Stop if one isn't a leg)."""
    xs = sorted({round(x, 9) for ring in [poly.exterior, *poly.interiors] for x, _ in ring.coords})
    ys = sorted({round(y, 9) for ring in [poly.exterior, *poly.interiors] for _, y in ring.coords})
    nx, ny = len(xs) - 1, len(ys) - 1
    cx = np.array([(xs[i] + xs[i + 1]) / 2 for i in range(nx)])
    cy = np.array([(ys[j] + ys[j + 1]) / 2 for j in range(ny)])
    gx, gy = np.meshgrid(cx, cy, indexing="ij")
    inside = shapely.contains_xy(poly, gx, gy)                  # inside[i, j]
    legs = []
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
                    legs.append((i0, i1, j0, j1))
    out = []
    for i0, i1, j0, j1 in legs:
        x0, x1, y0, y1 = xs[i0], xs[i1], ys[j0], ys[j1]
        w, h = x1 - x0, y1 - y0
        if abs(w - h) <= SAME:
            raise Stop("corridor_not_legs", why=f"a part of it {_ft(w)} ft square runs neither way")
        horizontal = w > h
        if horizontal:
            ok = [(j0 == 0 or not inside[i, j0 - 1]) and (j1 == ny or not inside[i, j1]) for i in range(i0, i1)]
            marks = xs[i0:i1 + 1]
        else:
            ok = [(i0 == 0 or not inside[i0 - 1, j]) and (i1 == nx or not inside[i1, j]) for j in range(j0, j1)]
            marks = ys[j0:j1 + 1]
        proper = []
        for k, good in enumerate(ok):
            if not good:
                continue
            if proper and abs(proper[-1][1] - marks[k]) <= 1e-9:
                proper[-1] = (proper[-1][0], marks[k + 1])
            else:
                proper.append((marks[k], marks[k + 1]))
        if not proper:
            raise Stop("corridor_not_legs", why="a part of it has no walls on its two long sides")
        out.append(_LegShape((x0, x1, y0, y1), horizontal, proper))
    return out


def _ft(x) -> str:
    return f"{x / 12:.2f}".rstrip("0").rstrip(".")


def _overlap(a: _LegShape, b: _LegShape) -> float:
    ax0, ax1, ay0, ay1 = a.rect
    bx0, bx1, by0, by1 = b.rect
    return max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(0.0, min(ay1, by1) - max(ay0, by0))


def _crossings(legs) -> list:
    """(i, j, point) for each two legs whose centre lines cross (Stop for two that overlap otherwise)."""
    out = []
    for i, a in enumerate(legs):
        for j in range(i + 1, len(legs)):
            b = legs[j]
            if _overlap(a, b) <= SAME * SAME:
                continue
            if a.horizontal == b.horizontal:
                raise Stop("corridor_not_legs", why="two of its stretches run side by side (a widening or a step)")
            h, v = (a, b) if a.horizontal else (b, a)
            x, y = v.line, h.line
            if not (h.span[0] - SAME <= x <= h.span[1] + SAME and v.span[0] - SAME <= y <= v.span[1] + SAME):
                raise Stop("corridor_not_legs", why="two of its stretches meet without their centre lines crossing")
            out.append((i, j, (x, y)))
    return out


def _proper_in(leg, a, b) -> float:
    return sum(max(0.0, min(b, q) - max(a, p)) for p, q in leg.proper)


# --- the graph -------------------------------------------------------------------------------------------------------

class _Graph:
    def __init__(self):
        self.xy, self.edges, self.adj = [], [], []     # edges: (u, v, length, leg index or None, (a, b) along)

    def node(self, p) -> int:
        for k, q in enumerate(self.xy):
            if math.dist(p, q) <= SAME:
                return k
        self.xy.append(tuple(p))
        self.adj.append([])
        return len(self.xy) - 1

    def edge(self, u, v, leg, along):
        if u == v:
            return
        k = len(self.edges)
        self.edges.append((u, v, math.dist(self.xy[u], self.xy[v]), leg, along))
        self.adj[u].append(k)
        self.adj[v].append(k)

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
        blocked, end = 0.0, -math.inf
        for v0, v1 in spans:
            if v1 > end:
                blocked += v1 - max(v0, end)
                end = v1
        least = min(least, w1 - w0 - blocked)
    return least


def _least_width(legs, g, walked, floors, floor_of, start_floor, start) -> float:
    """The narrowest clear width along the walked edges' own stretches (each leg with its own floor's blocks); a dead
    end of no length (or walked only in crossings): the leg it starts in (`start`, in its floor's frame)."""
    widths = []
    for k in walked:
        _, _, _, li, (a, b) = g.edges[k]
        if li is None:
            continue
        leg, blocks = legs[li], floors[floor_of[li]].blocks
        lo, hi = min(a, b), max(a, b)
        for p, q in leg.proper:
            s, e = max(lo, p), min(hi, q)
            if e - s > 1e-9:
                widths.append(_clear(leg, s, e, blocks))
    if not widths:
        floor = floors[start_floor]
        for li in floor.legs:
            leg = legs[li]
            x0, x1, y0, y1 = leg.rect
            if x0 - SAME <= start[0] <= x1 + SAME and y0 - SAME <= start[1] <= y1 + SAME:
                widths += [_clear(leg, p, q, floor.blocks) for p, q in leg.proper]
    return min(widths) if widths else 0.0


# --- the whole story -------------------------------------------------------------------------------------------------

@dataclass
class _Floor:
    """One floor of corridors joined by passages, turned square."""
    rooms: list
    frame: _Frame
    legs: list                 # indices into the story's legs
    blocks: list               # (x0, y0, x1, y1) in the frame: what narrows its width


def corridors(story: Story, uses: dict, routes: StoryRoutes | None) -> dict:
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
        floor = floors[key]
        start = g.xy[leaf]
        room = next((m for m in floor.rooms if rooms[m].outline.buffer(2 * SAME).covers(Point(start))), None)
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
            de.length[reading] = length
            de.width[reading] = _least_width(legs, g, walked, floors, floor_of, key, floor.frame.to(start))
            de.line[reading] = _walked_line(g, leaf, walked)
        out[room].dead_ends.append(de)
    return out


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
    """The least clear width over the legs' own stretches in this room, and the centre lines drawn in it."""
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
    if g is not None:
        corridor.centre_lines = [(g.xy[u], g.xy[v]) for u, v, _, li, _ in g.edges
                                 if li in floor.legs and u != v
                                 and room.outline.buffer(2 * SAME).covers(LineString([g.xy[u], g.xy[v]]).centroid)]


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
    crossings = _crossings(legs)
    base = len(legs_all)
    # each leg's centre line, cut at its crossings, its ends past the last crossing kept only with its own stretch
    at = {i: [] for i in range(len(legs))}
    for i, j, p in crossings:
        at[i].append(p)
        at[j].append(p)
    mine = []
    for i, leg in enumerate(legs):
        lo, hi = leg.span
        cuts = sorted(leg.along(p) for p in at[i])
        if cuts:
            if _proper_in(leg, lo, cuts[0]) <= SAME:
                lo = cuts[0]
            if _proper_in(leg, cuts[-1], hi) <= SAME:
                hi = cuts[-1]
        leg.kept = (lo, hi)
        legs_all.append(leg)
        marks = sorted({lo, hi, *[c for c in cuts if lo <= c <= hi]})
        nodes = [g.node(frame.back(leg.point(u))) for u in marks]
        mine += nodes
        for (u, v), (m0, m1) in zip(zip(nodes, nodes[1:]), zip(marks, marks[1:])):
            g.edge(u, v, base + i, (m0, m1))
    if mine and not set(mine) <= g.component(mine[0]):
        raise Stop("corridor_not_legs", why="its legs' centre lines don't all meet")
    # what narrows the width: obstructions, columns, and the bumps filled in finding the legs
    blocks = []
    for m in members:
        for o in m.obstructions + m.holes:
            blocks.append(Polygon([frame.to(c) for c in o.exterior.coords]).bounds)
    bumps = filled.difference(square)
    for piece in getattr(bumps, "geoms", [bumps]):
        if not piece.is_empty and piece.area > SAME * SAME:
            blocks.append(piece.bounds)
    return _Floor(sorted(ids), frame, list(range(base, base + len(legs))), blocks)


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
                    if reached and leg.paths(door.centre, story.doors[d].centre):
                        ways |= reached
            out[(door.id, rid)] = ways
    return out
