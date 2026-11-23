"""Routes on a story's floor: decision 2 of docs/decisions/2026-11-20_route_measurement.md, exactly.

The route from a point p to an exit is the shortest curve that (a) lies in the free floor of the rooms it may cross
(floor.py's zones), passing each door at its centre; (b) stays at least 12 in from every corner that sticks into the
floor, every obstruction corner and every door jamb (a true circle of 12-in radius: a ring). A route is defined only
from a point clear of every ring (on a ring's edge counts as clear): from inside one, `routes` stops (inside_ring),
and decision 3 (remote.py) covers those points by their cluster's bound. A point shut in by rings has no route; when
it has one with no clearance, the reason says the opening is too narrow for the clearance.

How it is computed. Every route passes a door centre between zones, so a route is a chain of legs, each in one zone
from a point or door centre to a door centre (decision 1). A leg is a shortest path among circles and polygon walls,
which is made only of straight lines tangent to rings and arcs along them (bending at no other place: a wall's own
corner always has its ring, and where a ring meets a wall or another ring the free floor turns away from the path).
So each leg is found exactly on a graph: its ends; the tangent points of every line from them to each ring and of
the four lines common to each pair of rings; each line kept only if it stays in the floor and out of every ring; and
the arcs between neighbouring tangent points on each ring, kept only if they stay in the floor and out of every other
ring. Dijkstra on it gives the leg, and Dijkstra over the door centres, from the exits, the chain. Two lengths within
1e-6 ft are a tie (decision 2): every tied route is kept, all together and never listed (`tied`: their union, each
piece on some tied route found from the distances to and from it, decision 5 as amended 2026-11-22), so the common
path can take the pair that shares most; `routes` lists them (for drawing and tests only: it stops past 64), and
`route` is any one. `travel` gives the length alone, from the same graph built once per zone, for sampling.

A route from an end-only room into the floor beyond its passage that comes back into the room stops (needs review).
A route from a room that opens only into the room it serves (floor.py's `served_by`, decision 1a as amended
2026-11-21, Gordium's reading) goes from the point to one of its doors in its own floor, then on as a route from that
door centre in the room it serves (its own doors and passages; a chain, in turn).

Lengths are inches; `Route.feet` gives feet.
"""

import bisect
import heapq
import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely import prepare
from shapely.geometry import LineString, Point

from model_measurement.routes.floor import CLEARANCE, SAME, Story, Zone, region
from model_measurement.routes.stops import Stop

FOOT = 12.0
TIE = 1e-6 * FOOT            # in: two route lengths this close are a tie (decision 2)
EPS = 1e-6                   # in: touching (a tangent line on its ring, a line along a wall)
MOST_TIES = 64
RING_WAYS_MOST = 1 << 15      # points whose ways onto a zone's graph are remembered (ring_ways)
LINES_MOST = 1 << 17          # lines from sampled points to targets whose clear() is remembered (clear_to)
ROOMS_AT_MOST = 1 << 16       # points whose rooms are remembered (rooms_at)


@dataclass
class Path:
    length: float
    pieces: list             # ("line", a, b) or ("arc", centre, radius, start angle, signed sweep)


@dataclass
class Route:
    length: float            # in
    pieces: list
    doors: tuple             # the doors passed, in order; the last is the exit's
    exit_id: str

    @property
    def feet(self) -> float:
        return self.length / FOOT


@dataclass
class Tight:
    """Every tied shortest curve between two places, held all together, never listed (decision 5, amended
    2026-11-22): `pieces`, each piece on some tied curve with its offset (the length from the start to the piece's
    start); `one`, the pieces of one of them; `length`, theirs."""
    length: float
    pieces: list
    one: list


@dataclass
class Tied:
    """Every tied shortest route from a point to an exit (or the nearest of several), as their union: `pieces`, each
    piece on some tied route with its offset (the travel distance from the point to the piece's start); `one`, one
    of the routes. Travel reads `length` (the same for every one); the common path the union."""
    length: float
    pieces: list
    one: Route


def _shift(pieces, by) -> list:
    return [(q, o + by) for q, o in pieces]


def _tight(adj, P, T, dT=None, dP=None) -> Tight | None:
    """The tied shortest walks on a graph from node P to node T, all together: a piece from u to v is on one when the
    distance to u, the piece and the distance from v add up to the shortest (within TIE)."""
    dT = _dijkstra(adj, T) if dT is None else dT
    if not math.isfinite(dT[P]):
        return None
    dP = _dijkstra(adj, P) if dP is None else dP
    length = dT[P]
    top = length + TIE
    pieces = []
    for u in range(len(adj)):
        if not dP[u] + dT[u] <= top:
            continue
        for v, w, piece in adj[u]:
            if dP[u] + w + dT[v] <= top and w > EPS * 1e-3:
                pieces.append((piece, dP[u]))
    return Tight(length, pieces, _down(adj, P, T, dT))


def _down(adj, n, T, dT) -> list:
    """One shortest walk from n to T (dT, the distances to T): each step one that keeps to the least, the node the
    Dijkstra from T reached n from among them (dT[n] is that node's distance plus the step, exactly), searched depth
    first so that two nodes at one place, joined by a step of no length, can't turn it round."""
    stack, came = [n], {n: None}
    while stack:
        u = stack.pop()
        if u == T:
            out = []
            while came[u] is not None:
                u, piece = came[u]
                out.append(piece)
            return _tidy(list(reversed(out)))
        for v, w, piece in adj[u]:
            if v not in came and w + dT[v] <= dT[u] + 1e-9 * max(1.0, dT[u]):
                came[v] = (u, piece)
                stack.append(v)
    raise RuntimeError("no shortest walk down")              # never: every node with a finite dT has its step


def _reverse_tight(t: Tight) -> Tight:
    return Tight(t.length, [(_reverse(q), t.length - o - _piece_length(q)) for q, o in t.pieces],
                 [_reverse(q) for q in reversed(t.one)])


def _show(p) -> tuple:
    return round(p[0] / FOOT, 3) + 0.0, round(p[1] / FOOT, 3) + 0.0


# --- one leg ---------------------------------------------------------------------------------------------------------

def _exit_words(story: Story, exits: dict, wanted) -> str:
    """The exits a route was looked for to, as the architect names them: by their doors' names ("the exit door D12",
    "an exit door (D01 or D12)"), never by the exit's id (the id stays in the data)."""
    names = sorted({story.doors[d].name for e in wanted for d in exits.get(e, ()) if d in story.doors})
    if not names:
        return "the exit asked for"
    return f"the exit door {names[0]}" if len(names) == 1 else f"an exit door ({' or '.join(names)})"


def _reverse(piece):
    if piece[0] == "line":
        return ("line", piece[2], piece[1])
    _, c, r, a, sweep = piece
    return ("arc", c, r, a + sweep, -sweep)


def _piece_length(piece) -> float:
    if piece[0] == "line":
        return math.dist(piece[1], piece[2])
    return abs(piece[4]) * piece[2]


class _Leg:
    """The shortest curves in one floor, among the rings (decision 2). `paths(p, t)` gives every tied curve from p
    to t with its pieces; `dist(p, t)` the length alone, fast, for sampling (decision 3): the graph among the rings
    and the targets is built once (`prepare`), and each point only adds its own tangent lines."""

    def __init__(self, floor, rings, corners, r):
        self.floor, self.r = floor, r
        self.cover = floor.buffer(EPS)
        prepare(self.cover)
        self.rings = np.array(rings, dtype=float).reshape(-1, 2) if r > 0 else np.zeros((0, 2))
        # with no clearance a route bends at the floor's corners; with it, every corner has its ring
        self.bends = [tuple(c) for c in corners] if r == 0 else []
        segs = []
        for poly in getattr(floor, "geoms", [floor]):
            if poly.geom_type != "Polygon":
                continue
            for ring in [poly.exterior, *poly.interiors]:
                pts = list(ring.coords)
                segs += [(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
        self.walls = np.array(segs, dtype=float).reshape(-1, 4)
        self._base = None
        self._facts = {}                 # each ring's facts for _arc_clear, worked once
        self._ring_ways = {}             # each point's ways onto the graph built once (ring_ways)
        self._lines = {}                 # clear(p, t) from sampled points to targets (clear_to)

    def covers(self, p) -> bool:
        return self.cover.covers(Point(p))

    def clear_to(self, p, t) -> bool:
        """`clear(p, t)` from a sampled point to a target, remembered (the story's travel and its common path, each
        exit's union, ask it of the same points and door centres)."""
        key = (p, t)
        got = self._lines.get(key)
        if got is None:
            if len(self._lines) >= LINES_MOST:
                self._lines.clear()
            got = self._lines[key] = self.clear(p, t)
        return got

    def inside(self, p) -> bool:
        """Whether p is inside a ring (closer than 12 in to a corner): no route is defined from there."""
        return bool(len(self.rings)) and bool((np.hypot(*(self.rings - p).T) < self.r - EPS).any())

    def clear(self, a, b) -> bool:
        if math.dist(a, b) <= EPS:
            return True
        if not self.cover.covers(LineString([a, b])):
            return False
        return not len(self.rings) or _seg_dist(self.rings, a, b).min() >= self.r - EPS

    def _tangents(self, p, k, c):
        """Where lines from p touch ring k, clear: (angle, the point or None when p is on the ring, length)."""
        r = self.r
        d = math.dist(p, c)
        if d < r - EPS:
            return []
        base = math.atan2(p[1] - c[1], p[0] - c[0])
        if d <= r + EPS:
            return [(base % (2 * math.pi), None, 0.0)]
        alpha, out = math.acos(r / d), []
        for ang in (base + alpha, base - alpha):
            q = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
            if self.clear(p, q):
                out.append((ang % (2 * math.pi), q, math.dist(p, q)))
        return out

    def tangents_to(self, p, ks) -> dict:
        """`_tangents(p, k, c)` for each ring k of ks (c its centre), {k: the same list}: the same tangent points by
        the same float operations, each line's floor test (`clear`'s covers) for all of them in one shapely call,
        then `clear`'s own ring test on each line the floor holds. The same answers as one `_tangents` per ring."""
        r = self.r
        out, lines = {}, []
        for k in ks:
            c = (float(self.rings[k][0]), float(self.rings[k][1]))
            d = math.dist(p, c)
            out[k] = []
            if d < r - EPS:
                continue
            base = math.atan2(p[1] - c[1], p[0] - c[0])
            if d <= r + EPS:
                out[k].append((base % (2 * math.pi), None, 0.0))
                continue
            alpha = math.acos(r / d)
            for ang in (base + alpha, base - alpha):
                lines.append((k, ang, (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))))
        for (k, ang, q), ok in zip(lines, self.clear_from(p, [q for _, _, q in lines])):
            if ok:
                out[k].append((ang % (2 * math.pi), q, math.dist(p, q)))
        return out

    def clear_from(self, a, ends) -> list:
        """`clear(a, b)` for each b of ends, the floor's covers test on every line in one shapely call."""
        return self.clear_lines([(a, b) for b in ends])

    def clear_lines(self, lines) -> list:
        """`clear(a, b)` for each (a, b) of lines, as `clear` works it: the same ends, the floor's covers test on every
        line longer than EPS in one shapely call, then the ring test on each line the floor holds."""
        got = [math.dist(a, b) <= EPS for a, b in lines]
        long = [i for i, short in enumerate(got) if not short]
        if long:
            held = shapely.covers(self.cover, shapely.linestrings([[lines[i][0], lines[i][1]] for i in long]))
            for i, ok in zip(long, held):
                a, b = lines[i]
                got[i] = bool(ok) and (not len(self.rings) or _seg_dist(self.rings, a, b).min() >= self.r - EPS)
        return got

    def _graph(self, points):
        """The graph among the rings and these points: (xy, adj, on, ids), `on[k]` ring k's nodes by angle."""
        r, rings = self.r, self.rings
        xy, adj = [], []

        def node(pt):
            xy.append((float(pt[0]), float(pt[1])))
            adj.append([])
            return len(xy) - 1

        def link(a, b, piece):
            w = _piece_length(piece)
            adj[a].append((b, w, piece))
            adj[b].append((a, w, _reverse(piece)))

        ids = [node(q) for q in points]
        on = [[] for _ in range(len(rings))]
        # each test of a line below is `clear`'s, many in one shapely call (clear_from, tangents_to, clear_lines),
        # and the nodes and links are made in the same order as ever
        for i, a in enumerate(ids):
            rest = ids[i + 1:]
            for b, ok in zip(rest, self.clear_from(xy[a], [xy[b] for b in rest])):
                if ok:
                    link(a, b, ("line", xy[a], xy[b]))
        touching = [self.tangents_to(xy[a], range(len(rings))) for a in ids]
        for k in range(len(rings)):
            for m, a in enumerate(ids):
                for ang, q, _ in touching[m][k]:
                    if q is None:
                        on[k].append((ang, a))
                    else:
                        n = node(q)
                        on[k].append((ang, n))
                        link(a, n, ("line", xy[a], q))
        common = []                                  # the four lines common to each pair of rings, in order
        for i in range(len(rings)):
            ci = (float(rings[i][0]), float(rings[i][1]))
            for j in range(i + 1, len(rings)):
                cj = (float(rings[j][0]), float(rings[j][1]))
                d = math.dist(ci, cj)
                if d <= EPS:
                    continue
                phi = math.atan2(cj[1] - ci[1], cj[0] - ci[0])
                pairs = [(phi + math.pi / 2, phi + math.pi / 2), (phi - math.pi / 2, phi - math.pi / 2)]
                if d > 2 * r + EPS:
                    beta = math.acos(2 * r / d)
                    pairs += [(phi + beta, phi + beta + math.pi), (phi - beta, phi - beta + math.pi)]
                for ai, aj in pairs:
                    qi = (ci[0] + r * math.cos(ai), ci[1] + r * math.sin(ai))
                    qj = (cj[0] + r * math.cos(aj), cj[1] + r * math.sin(aj))
                    common.append((i, j, ai, aj, qi, qj))
        for (i, j, ai, aj, qi, qj), ok in zip(common, self.clear_lines([(x[4], x[5]) for x in common])):
            if ok:
                ni, nj = node(qi), node(qj)
                on[i].append((ai % (2 * math.pi), ni))
                on[j].append((aj % (2 * math.pi), nj))
                link(ni, nj, ("line", qi, qj))
        for k in range(len(rings)):
            c = (float(rings[k][0]), float(rings[k][1]))
            on[k].sort()
            ring = on[k]
            if len(ring) < 2:
                continue
            for m, (a0, n0) in enumerate(ring):
                a1, n1 = ring[(m + 1) % len(ring)]
                sweep = (a1 - a0) % (2 * math.pi)
                if self._arc_clear(k, c, a0, sweep):
                    link(n0, n1, ("arc", c, r, a0, sweep))
        return xy, adj, on, ids

    def paths(self, p, t) -> list[Path]:
        if math.dist(p, t) <= EPS:
            return [Path(0.0, [])]
        bends = [b for b in self.bends if math.dist(b, p) > EPS and math.dist(b, t) > EPS]
        xy, adj, _, ids = self._graph([p, t] + bends)
        found = _tied(adj, ids[0], ids[1])
        if found is None:
            raise Stop("too_many_ties", most=MOST_TIES, x=_show(p)[0], y=_show(p)[1])
        out, seen = [], set()
        for pieces in found:
            pieces = _tidy(pieces)
            key = _signature(pieces)
            if key not in seen:
                seen.add(key)
                out.append(Path(sum(_piece_length(q) for q in pieces), pieces))
        return out

    def tight(self, p, t) -> Tight | None:
        """Every tied shortest curve from p to t on a graph of their own, all together (None: no curve)."""
        if math.dist(p, t) <= EPS:
            return Tight(0.0, [], [])
        bends = [b for b in self.bends if math.dist(b, p) > EPS and math.dist(b, t) > EPS]
        _, adj, _, ids = self._graph([p, t] + bends)
        return _tight(adj, ids[0], ids[1])

    def between_tight(self, a, b) -> Tight | None:
        """`between`, all together: every tied shortest curve from the target a to the target b on the graph built
        once (`prepare`), never listed."""
        a, b = tuple(map(float, a)), tuple(map(float, b))
        if math.dist(a, b) <= EPS:
            return Tight(0.0, [], [])
        _, _, dists, _, _, adj, ids = self._base
        return _tight(adj, ids[a], ids[b], dT=dists[b], dP=dists[a])

    def prepare(self, targets) -> None:
        """The graph among the rings and these targets (door centres), with each target's distance to every node:
        built once per zone, for the legs between door centres (`between`) and for sampling (`dist`)."""
        targets = [tuple(map(float, t)) for t in targets]
        if self._base is not None and self._base[0] == targets:
            return
        xy, adj, on, ids = self._graph(targets + self.bends)
        dists = {t: _dijkstra(adj, n) for t, n in zip(targets, ids)}
        self._base = (targets, on, dists, ids[len(targets):], xy, adj, dict(zip(targets, ids)))
        self._ways = None
        self._ring_ways = {}

    def between(self, a, b) -> list[Path]:
        """Every tied shortest curve from the target a to the target b (both given to `prepare`), on the graph
        built once: the same curves `paths(a, b)` finds on a graph of its own (other targets' nodes only add points
        on curves the floor already holds, never a shorter one)."""
        a, b = tuple(map(float, a)), tuple(map(float, b))
        if math.dist(a, b) <= EPS:
            return [Path(0.0, [])]
        _, _, dists, _, _, adj, ids = self._base
        D, P, T = dists[b], ids[a], ids[b]
        if not math.isfinite(D[P]):
            return []
        found = []

        def walk(v, so_far, pieces, seen):
            if len(found) > 4 * MOST_TIES:
                return
            if v == T:
                found.append(list(pieces))
                return
            for u, w, piece in adj[v]:
                if u in seen or so_far + w + D[u] > D[P] + TIE:
                    continue
                pieces.append(piece)
                walk(u, so_far + w, pieces, seen | {u})
                pieces.pop()

        walk(P, 0.0, [], {P})
        if len(found) > 4 * MOST_TIES:
            raise Stop("too_many_ties", most=MOST_TIES, x=_show(a)[0], y=_show(a)[1])
        out, seen = [], set()
        for pieces in found:
            pieces = _tidy(pieces)
            key = _signature(pieces)
            if key not in seen:
                seen.add(key)
                out.append(Path(sum(_piece_length(q) for q in pieces), pieces))
        return out

    def ring_ways(self, p, on) -> list:
        """Every way a curve from p (clear of every ring) reaches the graph by a tangent to a ring and round it to
        the first node there (`on`, each ring's nodes by angle), each way: (length, node, ring, tangent point or
        None, tangent angle, signed sweep from it). Worked once per point on the graph built once and remembered
        (the story's travel and its common path both sample the same points): `_ways_from` and the common path's
        `firsts` read the same list, each as it always worked it (the same float operations, in the same order)."""
        mine = self._base is not None and on is self._base[1]
        if mine and p in self._ring_ways:
            return self._ring_ways[p]
        out = []
        touching = self.tangents_to(p, [k for k in range(len(self.rings)) if on[k]])
        for k in range(len(self.rings)):
            ring = on[k]
            if not ring:
                continue
            c = (float(self.rings[k][0]), float(self.rings[k][1]))
            angles = [a for a, _ in ring]
            for ang, q, length in touching[k]:
                i = bisect.bisect_left(angles, ang)
                after, before = ring[i % len(ring)], ring[(i - 1) % len(ring)]
                # round the ring each way to the first node met
                up, down = (after[0] - ang) % (2 * math.pi), (ang - before[0]) % (2 * math.pi)
                if self._arc_clear(k, c, ang, up):
                    out.append((length + self.r * up, after[1], k, q, ang, up))
                if self._arc_clear(k, c, before[0], down):
                    out.append((length + self.r * down, before[1], k, q, ang, -down))
        if mine:
            if len(self._ring_ways) >= RING_WAYS_MOST:
                self._ring_ways.clear()
            self._ring_ways[p] = out
        return out

    def _ways_from(self, p) -> list:
        """Every way a curve from p reaches the graph other than straight to a target: to a corner (no clearance),
        or by a tangent to a ring and round it to the first node there, each way: [(length, node)]. Worked once per
        point, for every target."""
        if self._ways is not None and self._ways[0] == p:
            return self._ways[1]
        _, on, _, bend_ids, _, _, _ = self._base
        ways = [(math.dist(p, b), n) for b, n in zip(self.bends, bend_ids) if self.clear(p, b)]
        ways += [(length, n) for length, n, *_ in self.ring_ways(p, on)]
        self._ways = (p, ways)
        return ways

    def dist(self, p, t) -> float:
        """The length of the shortest curve from p (clear of every ring) to the target t (one given to `prepare`):
        inf if there is none. Such a curve goes straight to t, or to a corner (no clearance), or to a ring at a
        tangent point and round it to the first node there: every way it can leave a ring is a node of the graph."""
        D = self._base[2][tuple(map(float, t))]
        t = tuple(map(float, t))
        best = math.dist(p, t) if self.clear_to(p, t) else math.inf
        for length, n in self._ways_from(p):
            if length + D[n] < best:
                best = length + D[n]
        return best

    def _ring_facts(self, k, c) -> tuple:
        """What `_arc_clear` reads of ring k (centre c) that no arc changes, worked once per ring: each other ring
        whose circle meets it, as (phi, beta), the angle to its centre and the half-angle of the overlap (the same
        expressions, in the same order, as `_arc_clear` always worked them per arc); and the absolute angle of each
        place its circle crosses a wall (`_circle_wall_angles`, before `_circle_walls` takes a0 off)."""
        key = (k, c[0], c[1])
        facts = self._facts
        if key not in facts:
            active, r = self.rings, self.r
            meets = []
            for j in range(len(active)):
                if j == k:
                    continue
                d = math.dist(c, active[j])
                if d >= 2 * r - EPS:
                    continue
                meets.append((math.atan2(active[j][1] - c[1], active[j][0] - c[0]), math.acos(d / (2 * r))))
            facts[key] = (meets, _circle_wall_angles(self.walls, c, r))
        return facts[key]

    def _arc_clear(self, k, c, a0, sweep) -> bool:
        """Whether the arc of ring k from a0 through sweep stays out of every other ring and in the floor. Exactly as
        it was worked per arc, from the ring's facts worked once (`_ring_facts`): each other ring that meets it
        (`(phi - beta - a0) % 2 pi`, the same floats), then each stretch between the wall crossings (`(angle - a0) %
        2 pi`, the same floats `_circle_walls` gives) by its middle point, every one in the floor (all of them in
        one shapely call: the same covers test on the same points)."""
        r, slack = self.r, EPS / self.r
        if sweep <= slack:
            return True
        meets, walls = self._ring_facts(k, c)
        for phi, beta in meets:
            u = (phi - beta - a0) % (2 * math.pi)
            if u < sweep - slack or u + 2 * beta - 2 * math.pi > slack:
                return False
        cuts = sorted(x for x in ((t - a0) % (2 * math.pi) for t in walls) if slack < x < sweep - slack)
        marks = [0.0, *cuts, sweep]
        mids = [a0 + (x0 + x1) / 2 for x0, x1 in zip(marks, marks[1:])]
        return bool(shapely.covers(self.cover, shapely.points(
            [(c[0] + r * math.cos(mid), c[1] + r * math.sin(mid)) for mid in mids])).all())


def _dijkstra(adj, source) -> list:
    dist = [math.inf] * len(adj)
    dist[source] = 0.0
    heap = [(0.0, source)]
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        for u, w, _ in adj[v]:
            if d + w < dist[u]:
                dist[u] = d + w
                heapq.heappush(heap, (d + w, u))
    return dist


def _seg_dist(centres, a, b):
    """Distance from each centre to the segment ab."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    d = b - a
    s = np.clip(((centres - a) @ d) / (d @ d), 0.0, 1.0)
    return np.hypot(*(centres - (a + s[:, None] * d)).T)


def _circle_walls(walls, c, r, a0):
    """Where the circle crosses the walls: angles measured on from a0, in [0, 2 pi)."""
    return [(t - a0) % (2 * math.pi) for t in _circle_wall_angles(walls, c, r)]


def _circle_wall_angles(walls, c, r):
    """Where the circle crosses the walls: each place's own angle (atan2, before any a0 is taken off)."""
    if not len(walls):
        return []
    p, q = walls[:, :2] - c, walls[:, 2:] - c
    d = q - p
    A = (d * d).sum(1)
    B = 2 * (p * d).sum(1)
    C = (p * p).sum(1) - r * r
    disc = B * B - 4 * A * C
    out = []
    for k in np.nonzero((disc >= 0) & (A > 0))[0]:
        root = math.sqrt(disc[k])
        for s in ((-B[k] - root) / (2 * A[k]), (-B[k] + root) / (2 * A[k])):
            if -1e-12 <= s <= 1 + 1e-12:
                x, y = p[k] + s * d[k]
                out.append(math.atan2(y, x))
    return out


def _tied(adj, P, T) -> list[list]:
    """Every shortest walk from P to T (within TIE), as lists of pieces: Dijkstra from T, then every next
    step that keeps to the least."""
    dist = _dijkstra(adj, T)
    if not math.isfinite(dist[P]):
        return []
    out = []

    def walk(v, so_far, pieces, visited):
        if len(out) > 4 * MOST_TIES:
            return
        if v == T:
            if so_far <= dist[P] + TIE:
                out.append(list(pieces))
            return
        for u, w, piece in adj[v]:
            if u in visited or so_far + w + dist[u] > dist[P] + TIE:
                continue
            visited.add(u)
            pieces.append(piece)
            walk(u, so_far + w, pieces, visited)
            pieces.pop()
            visited.discard(u)

    walk(P, 0.0, [], {P})
    return None if len(out) > 4 * MOST_TIES else out


def _tidy(pieces) -> list:
    """Zero-length pieces dropped; arcs on one ring the same way, one after another, made one."""
    out = []
    for q in pieces:
        if _piece_length(q) <= EPS * 1e-3:
            continue
        if out and q[0] == "arc" and out[-1][0] == "arc" and out[-1][1] == q[1] and (out[-1][4] > 0) == (q[4] > 0):
            prev = out.pop()
            q = ("arc", q[1], q[2], prev[3], prev[4] + q[4])
        out.append(q)
    return out


def _ends(q):
    if q[0] == "line":
        return q[1], q[2]
    _, c, r, a, s = q
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a)), (c[0] + r * math.cos(a + s), c[1] + r * math.sin(a + s))


def _signature(pieces) -> tuple:
    return tuple(round(v, 4) for q in pieces for e in _ends(q) for v in e)


# --- a story's routes ------------------------------------------------------------------------------------------------

class StoryRoutes:
    """Every route on one story (decisions 1, 1a, 2 and 4). `clearance` is the rings' radius (12 in; 0 gives the
    no-clearance figure the eval compares a hand path with)."""

    def __init__(self, story: Story, clearance: float = CLEARANCE):
        if story.stops:
            raise Stop("story_not_measured", reasons="; ".join(story.stops))
        self.story, self.r = story, clearance
        self._engines, self._legs, self._chains, self._regions = {}, {}, {}, {}
        self._start_cache, self._plain, self._onward_cache = {}, None, {}
        self.exits = {}
        for d in story.exits():
            self.exits.setdefault(d.exit_id, []).append(d.id)

    # one zone's legs
    def _engine(self, zone: Zone) -> _Leg:
        key = zone.rooms
        if key not in self._engines:
            self._engines[key] = _Leg(zone.floor, zone.rings if self.r > 0 else [], zone.corners, self.r)
        return self._engines[key]

    def _leg(self, zone: Zone, a, b) -> list[Path]:
        key = (zone.rooms, a, b)
        if key not in self._legs:
            self._legs[key] = self._engine(zone).paths(a, b)
        return self._legs[key]

    # the chain from each door centre to the exits wanted
    def _chain(self, wanted: frozenset):
        """Dijkstra over door centres from the exits in `wanted`: (distance, next steps) per door. An exit's door is
        an end, never passed through."""
        if wanted in self._chains:
            return self._chains[wanted]
        doors = self.story.doors
        edges = {}
        for zone in self.story.zones:
            engine = self._engine(zone)
            engine.prepare([doors[d].centre for d in zone.doors])     # one graph per zone, every door centre on it
            for i, a in enumerate(zone.doors):
                for b in zone.doors[i + 1:]:
                    leg = engine.between_tight(doors[a].centre, doors[b].centre)    # all together, never listed
                    if leg is not None:
                        edges.setdefault(a, []).append((b, zone, leg))
                        edges.setdefault(b, []).append((a, zone, _reverse_tight(leg)))
        dist = {d: math.inf for d in doors}
        heap = []
        for d in doors.values():
            if d.exit_kind and d.exit_id in wanted:
                dist[d.id] = 0.0
                heap.append((0.0, d.id))
        heapq.heapify(heap)
        while heap:
            dv, v = heapq.heappop(heap)
            if dv > dist[v]:
                continue
            for u, _, leg in edges.get(v, []):
                if doors[u].exit_kind:
                    continue                                 # another exit: an end, never passed through
                w = leg.length
                if dv + w < dist[u]:
                    dist[u] = dv + w
                    heapq.heappush(heap, (dv + w, u))
        steps = {}
        for v in doors:
            if not math.isfinite(dist[v]) or doors[v].exit_kind:
                continue
            steps[v] = [(u, zone, leg) for u, zone, leg in edges.get(v, [])
                        if leg.length + dist[u] <= dist[v] + TIE]
        self._chains[wanted] = (dist, steps, edges)
        return self._chains[wanted]

    def _chains_from(self, door_id, wanted, at, passed_by=frozenset()) -> list[tuple]:
        """Every tied chain from a door centre to an exit: (pieces, doors passed, exit id). A chain never passes a
        door twice (`passed_by`), so no cycle of zero-length steps can recurse."""
        dist, steps, _ = self._chain(wanted)
        door = self.story.doors[door_id]
        if door.exit_kind and door.exit_id in wanted:
            return [([], (door_id,), door.exit_id)]
        out = []
        for u, zone, _ in steps.get(door_id, []):
            if u in passed_by or u == door_id:
                continue
            engine = self._engine(zone)
            paths = engine.between(self.story.doors[door_id].centre, self.story.doors[u].centre)
            for rest, passed, exit_id in self._chains_from(u, wanted, at, passed_by | {door_id}):
                for q in paths:
                    out.append((q.pieces + rest, (door_id,) + passed, exit_id))
                    if len(out) > MOST_TIES:
                        raise Stop("too_many_ties", most=MOST_TIES, x=at[0], y=at[1])
        return out

    def _wanted(self, exit_ids) -> frozenset:
        wanted = frozenset(self.exits if exit_ids is None else exit_ids)
        for e in wanted:
            if e not in self.exits:
                raise Stop("exit_unknown", exit_id=e)
        return wanted

    def rooms_at(self, p) -> list:
        """The rooms read whose outline holds p (two on the line between rooms)."""
        if not hasattr(self, "_grown"):                  # each outline grown by EPS once, prepared
            self._grown = [(r, r.outline.buffer(EPS)) for r in self.story.rooms.values() if r is not None]
            for _, g in self._grown:
                prepare(g)
            self._grown_all = np.array([g for _, g in self._grown], dtype=object)
            self._rooms_at = {}
        if not self._grown:
            return []
        key = (float(p[0]), float(p[1]))
        got = self._rooms_at.get(key)
        if got is None:              # one shapely call for every room: the same covers test, outlines and point
            held = shapely.covers(self._grown_all, Point(p))
            if len(self._rooms_at) >= ROOMS_AT_MOST:
                self._rooms_at.clear()
            got = self._rooms_at[key] = tuple(r for (r, _), ok in zip(self._grown, held) if ok)
        return list(got)                # each caller its own list, as ever

    def rings_for(self, room) -> list:
        """The centres of every ring a route from this room meets (its zone's, or for an end-only room those of its
        own floor and of each floor it is joined to for a start in it)."""
        out = []
        for zone, _ in self._starts(room):
            out += [c for c in zone.rings if all(math.dist(c, q) > SAME for q in out)]
        return out

    def _check_start(self, room, p, at) -> None:
        if self.r > 0 and any(self._engine(zone).inside(p) for zone, _ in self._starts(room)):
            raise Stop("inside_ring", x=at[0], y=at[1])

    def _no_route(self, p, at, exit_ids, wanted, room=None):
        """No route: say so, and say it is an opening too narrow for the clearance when one with none exists; for a
        room that opens only into one end-only room, say why its route can't go through it, or (only when the room
        it serves has no route on from any of its doors) that the room it serves has none either. The no-clearance
        retry comes first: a point with a route only with no clearance is shut in (a pocket, decision 3)."""
        story = self.story
        exits = "any exit" if exit_ids is None else _exit_words(story, self.exits, wanted)
        if self.r > 0:
            if self._plain is None:
                self._plain = StoryRoutes(self.story, 0.0)
            try:
                self._plain.route(p, exit_ids)
            except Stop:
                pass
            else:
                return Stop("too_narrow", x=at[0], y=at[1])
        if room is not None and room.id in story.not_served:
            return Stop("no_route_host_blocked", x=at[0], y=at[1], exits=exits, name=room.name,
                        why=story.not_served[room.id])
        if room is not None and room.id in story.served_by and all(
                self.tied_onward(room, d, wanted, at, frozenset()) is None for d in self._region([room.id]).doors):
            return Stop("no_route_via_host", x=at[0], y=at[1], exits=exits, name=room.name,
                        host=story.rooms[story.served_by[room.id]].name)
        return Stop("no_route", x=at[0], y=at[1], exits=exits)

    def routes(self, point, exit_ids=None) -> list[Route]:
        """Every shortest route (ties within 1e-6 ft) from a point (inches), clear of every ring, to the nearest of
        the exits named by exit id (all the story's exits if none are named)."""
        p = (float(point[0]), float(point[1]))
        at = _show(p)
        wanted = self._wanted(exit_ids)
        dist, _, _ = self._chain(wanted)
        rooms = self.rooms_at(p)
        if not rooms:
            raise Stop("not_on_floor", x=at[0], y=at[1])
        best_of_rooms = None
        for room in rooms:
            self._check_start(room, p, at)
            found = self._from_room(room, p, wanted, dist, at)
            if found is None:
                raise self._no_route(p, at, exit_ids, wanted, room)    # a start in either room may need it
            if best_of_rooms is None or found[0].length > best_of_rooms[0].length + TIE:
                best_of_rooms = found                       # a point on two rooms' line: the longer (cautious)
        return best_of_rooms

    def route(self, point, exit_ids=None) -> Route:
        """One shortest route (any of the tied ones: their length is the same), never listing them."""
        return self.tied(point, exit_ids).one

    # --- every tied route, all together, never listed (decision 5, amended 2026-11-22) ---------------------------

    def tied(self, point, exit_ids=None) -> Tied:
        """Every shortest route (ties within 1e-6 ft) from a point (inches), clear of every ring, to the nearest of
        the exits named, as their union (`Tied`), worked as `routes` works them but never listing one."""
        p = (float(point[0]), float(point[1]))
        at = _show(p)
        wanted = self._wanted(exit_ids)
        dist, _, _ = self._chain(wanted)
        rooms = self.rooms_at(p)
        if not rooms:
            raise Stop("not_on_floor", x=at[0], y=at[1])
        best = None
        for room in rooms:
            self._check_start(room, p, at)
            found = self._tied_from_room(room, p, wanted, dist, at)
            if found is None:
                raise self._no_route(p, at, exit_ids, wanted, room)
            if best is None or found.length > best.length + TIE:
                best = found                                 # a point on two rooms' line: the longer (cautious)
        return best

    def _tight_leg(self, zone: Zone, a, b) -> Tight | None:
        key = ("tight", zone.rooms, a, b)
        if key not in self._legs:
            self._legs[key] = self._engine(zone).tight(a, b)
        return self._legs[key]

    def chain_union(self, door_id, wanted) -> tuple:
        """Every tied chain from a door centre to the nearest exit in `wanted`, all together: (pieces with offsets
        from the door centre, one chain's pieces, its doors, its exit id). The doors on some tied chain are those
        whose distance from this door and to the exit add up (the chain's Dijkstra, `_chain`); each step between two
        of them adds its tied curves (`between_tight`). Worked once per door and set of exits."""
        key = (door_id, wanted)
        cache = self.__dict__.setdefault("_union_cache", {})
        if key in cache:
            return cache[key]
        dist, steps, _ = self._chain(wanted)
        doors = self.story.doors
        door = doors[door_id]
        if door.exit_kind and door.exit_id in wanted:
            cache[key] = ([], [], (door_id,), door.exit_id)
            return cache[key]
        pieces, seen, todo = [], {door_id}, [door_id]
        while todo:
            v = todo.pop()
            if doors[v].exit_kind:
                continue                                     # an exit: an end, never passed through
            for u, _, leg in steps.get(v, []):
                if u == v:
                    continue
                pieces += _shift(leg.pieces, dist[door_id] - dist[v])
                if u not in seen:
                    seen.add(u)
                    todo.append(u)
        one, passed, v = [], (door_id,), door_id
        while not (doors[v].exit_kind and doors[v].exit_id in wanted):
            u, _, leg = next(x for x in steps[v] if x[0] not in passed)
            one += leg.one
            passed += (u,)
            v = u
        cache[key] = (pieces, one, passed, doors[v].exit_id)
        return cache[key]

    def _tied_from_room(self, room, p, wanted, dist, at, seen=frozenset()) -> Tied | None:
        """`_from_room`, all together: the union of every tied route from p, a point in this room."""
        story = self.story
        if room.id in story.served_by:
            return None if room.id in seen else self._tied_through_host(room, p, wanted, at, seen)
        starts = self._starts(room)
        if not any(self._engine(zone).covers(p) for zone, _ in starts):
            raise Stop("not_on_floor", x=at[0], y=at[1])
        own = set(starts[0][0].doors)
        legs = []
        for zone, leaving in starts:
            if not self._engine(zone).covers(p):
                continue
            for d in zone.doors:
                if leaving is not None and d in own:
                    continue                                 # its own doors: by its own floor alone
                if not math.isfinite(dist.get(d, math.inf)):
                    continue
                leg = self._tight_leg(zone, p, story.doors[d].centre)
                if leg is None:
                    continue
                if leaving is not None:
                    _leaves_once_all(leg, leaving, p)
                legs.append((leg.length + dist[d], leg, d))
        return self.join(legs, wanted)

    def join(self, legs, wanted) -> Tied | None:
        """The tied routes made of a first leg to a door ((length in all, leg, door) each) and the chains on from
        it, all together."""
        if not legs:
            return None
        best = min(x[0] for x in legs)
        pieces, one = [], None
        for total, leg, d in sorted(legs, key=lambda x: x[0]):
            if total > best + TIE:
                break
            rest, rest_one, passed, exit_id = self.chain_union(d, wanted)
            pieces += leg.pieces + _shift(rest, leg.length)
            if one is None:
                whole = _tidy(leg.one + rest_one)
                one = Route(sum(_piece_length(q) for q in whole), whole, passed, exit_id)
        return Tied(best, pieces, one)

    def tied_onward(self, room, door_id, wanted, at, seen) -> Tied | None:
        """`_onward`, all together: the tied routes on from a door centre of a room that opens only into the room it
        serves, as a start in that room (worked once per door and set of exits); None where there are none."""
        key = ("tied", room.id, door_id, wanted)
        if key not in self._onward_cache:
            host = self.story.rooms[self.story.served_by[room.id]]
            if host.id not in self.story.doors[door_id].sides:
                self._onward_cache[key] = None
                return None
            dist, _, _ = self._chain(wanted)
            self._onward_cache[key] = self._tied_from_room(host, tuple(self.story.doors[door_id].centre), wanted,
                                                           dist, at, seen | {room.id})
        return self._onward_cache[key]

    def _tied_through_host(self, room, p, wanted, at, seen) -> Tied | None:
        """`_through_host`, all together."""
        own = self._region([room.id])
        if not self._engine(own).covers(p):
            raise Stop("not_on_floor", x=at[0], y=at[1])
        legs = []
        for d in own.doors:
            onward = self.tied_onward(room, d, wanted, at, seen)
            if onward is None:
                continue
            leg = self._tight_leg(own, p, self.story.doors[d].centre)
            if leg is not None:
                legs.append((leg.length + onward.length, leg, d, onward))
        if not legs:
            return None
        best = min(x[0] for x in legs)
        pieces, one = [], None
        for total, leg, d, onward in sorted(legs, key=lambda x: x[0]):
            if total > best + TIE:
                break
            pieces += leg.pieces + _shift(onward.pieces, leg.length)
            if one is None:
                whole = _tidy(leg.one + onward.one.pieces)
                one = Route(sum(_piece_length(q) for q in whole), whole, (d,) + onward.one.doors, onward.one.exit_id)
        return Tied(best, pieces, one)

    def travel(self, point, exit_ids=None) -> float:
        """The length (inches) of the shortest route from a point clear of every ring to the nearest exit named,
        as `route(...).length` gives it, from each zone's graph built once (decision 3 samples with it)."""
        p = (float(point[0]), float(point[1]))
        at = _show(p)
        wanted = self._wanted(exit_ids)
        dist, _, _ = self._chain(wanted)
        rooms = self.rooms_at(p)
        if not rooms:
            raise Stop("not_on_floor", x=at[0], y=at[1])
        worst = -math.inf
        for room in rooms:
            self._check_start(room, p, at)
            starts = self._starts(room)
            if room.id in self.story.served_by:              # through the room it serves (decision 1a)
                worst = max(worst, self._served_travel(room, p, wanted, at, exit_ids))
                continue
            if len(starts) > 1:                              # an end-only room joined beyond its passages
                worst = max(worst, self.tied(p, exit_ids).length)
                continue
            zone = starts[0][0]
            engine = self._engine(zone)
            if not engine.covers(p):
                raise Stop("not_on_floor", x=at[0], y=at[1])
            doors = [d for d in zone.doors if math.isfinite(dist.get(d, math.inf))]
            engine.prepare([self.story.doors[d].centre for d in zone.doors])
            best = min((engine.dist(p, self.story.doors[d].centre) + dist[d] for d in doors), default=math.inf)
            if not math.isfinite(best):
                raise self._no_route(p, at, exit_ids, wanted, room)
            worst = max(worst, best)
        return worst

    def simple(self, room) -> bool:
        """Whether a route from this room is found in one floor alone (no passage joined, no room it serves): the
        fast ways (`travel`, common_path.tied) read that floor's graph built once."""
        return len(self._starts(room)) == 1 and room.id not in self.story.served_by

    def _onward(self, room, door_id, wanted, at, seen) -> list:
        """The routes on from a door centre of a room that opens only into the room it serves: those from that
        centre as a start in the room it serves (worked once per door and set of exits). A door into a room this one
        serves in turn (a closet off it) leads no way out: none."""
        key = (room.id, door_id, wanted)
        if key not in self._onward_cache:
            host = self.story.rooms[self.story.served_by[room.id]]
            if host.id not in self.story.doors[door_id].sides:
                self._onward_cache[key] = []
                return []
            dist, _, _ = self._chain(wanted)
            self._onward_cache[key] = self._from_room(host, tuple(self.story.doors[door_id].centre), wanted, dist, at,
                                                      seen | {room.id}) or []
        return self._onward_cache[key]

    def _served_travel(self, room, p, wanted, at, exit_ids) -> float:
        """`travel` from a room that opens only into the room it serves, from its own floor's graph built once."""
        own = self._region([room.id])
        engine = self._engine(own)
        if not engine.covers(p):
            raise Stop("not_on_floor", x=at[0], y=at[1])
        engine.prepare([self.story.doors[d].centre for d in own.doors])
        best = math.inf
        for d in own.doors:
            onward = self.tied_onward(room, d, wanted, at, frozenset())
            if onward is not None:
                best = min(best, engine.dist(p, self.story.doors[d].centre) + onward.length)
        if not math.isfinite(best):
            raise self._no_route(p, at, exit_ids, wanted, room)
        return best

    def _through_host(self, room, p, wanted, at, seen):
        """The shortest routes from p in a room that opens only into the room it serves: to one of its doors in its
        own floor, then on from that door centre (`_onward`)."""
        own = self._region([room.id])
        if not self._engine(own).covers(p):
            raise Stop("not_on_floor", x=at[0], y=at[1])
        legs = []
        for d in own.doors:
            onward = self._onward(room, d, wanted, at, seen)
            if not onward:
                continue
            for path in self._leg(own, p, self.story.doors[d].centre):
                legs.append((path.length + onward[0].length, path, d, onward))
        if not legs:
            return None
        best = min(x[0] for x in legs)
        out = []
        for total, path, d, onward in sorted(legs, key=lambda x: x[0]):
            if total > best + TIE:
                break
            for rest in onward:
                if path.length + rest.length > best + TIE:
                    continue
                pieces = _tidy(path.pieces + rest.pieces)
                out.append(Route(sum(_piece_length(q) for q in pieces), pieces, (d,) + rest.doors, rest.exit_id))
                if len(out) > MOST_TIES:
                    raise Stop("too_many_ties", most=MOST_TIES, x=at[0], y=at[1])
        return out

    def _region(self, room_ids) -> Zone:
        key = tuple(sorted(room_ids))
        if key not in self._regions:
            self._regions[key] = region(self.story, key)
        return self._regions[key]

    def _starts(self, room) -> list:
        """The floors a route from this room walks first: (zone, the room when it is left by a passage, or None)."""
        if room.id in self._start_cache:
            return self._start_cache[room.id]
        story = self.story
        if room.crossable:
            starts = [(story.zone_of[room.id], None)]
        else:
            starts = [(self._region([room.id]), None)]
            beyond = []
            for a, b, _ in story.passages:
                zone = story.zone_of.get(b if a == room.id else a if b == room.id else None)
                if zone is not None and all(z is not zone for z in beyond):
                    beyond.append(zone)
            starts += [(self._region([room.id, *zone.rooms]), room) for zone in beyond]
        self._start_cache[room.id] = starts
        return starts

    def _from_room(self, room, p, wanted, dist, at, seen=frozenset()):
        """The shortest routes from p, a point in this room: in its zone; or, in an end-only room, in the room
        alone to its own doors, and joined to each crossable zone beyond its passages to that zone's doors (a
        route may leave it that way, never come back in: decision 1); or, in a room that opens only into the room
        it serves, through that room (decision 1a). `seen`: the rooms a route has come through (never twice)."""
        story = self.story
        if room.id in story.served_by:
            return None if room.id in seen else self._through_host(room, p, wanted, at, seen)
        starts = self._starts(room)
        if not any(self._engine(zone).covers(p) for zone, _ in starts):
            raise Stop("not_on_floor", x=at[0], y=at[1])
        own = set(starts[0][0].doors)
        legs = []
        for zone, leaving in starts:
            if not self._engine(zone).covers(p):
                continue
            for d in zone.doors:
                if leaving is not None and d in own:
                    continue                                 # its own doors: by its own floor alone
                if not math.isfinite(dist.get(d, math.inf)):
                    continue
                for path in self._leg(zone, p, story.doors[d].centre):
                    if leaving is not None:
                        _leaves_once(path, leaving, p)
                    legs.append((path.length + dist[d], path, d))
        if not legs:
            return None
        best = min(x[0] for x in legs)
        out = []
        for total, path, d in sorted(legs, key=lambda x: x[0]):
            if total > best + TIE:
                break
            for rest, passed, exit_id in self._chains_from(d, wanted, at):
                pieces = _tidy(path.pieces + rest)
                out.append(Route(sum(_piece_length(q) for q in pieces), pieces, passed, exit_id))
                if len(out) > MOST_TIES:
                    raise Stop("too_many_ties", most=MOST_TIES, x=at[0], y=at[1])
        return out


def _leaves_once(path: Path, room, p) -> None:
    """A route from an end-only room into the floor beyond its passage never comes back into the room."""
    inside = room.outline.buffer(-SAME)
    line = _polyline(path.pieces)
    if line is None:
        return
    got = line.intersection(inside)
    parts = [g for g in getattr(got, "geoms", [got]) if not g.is_empty and g.length > EPS]
    # a start in the room must leave it at once; a start at a door centre in its wall (a route on from a room it
    # serves, decision 1a) comes in through that door first, and must never come back once it has left
    starts_in = room.outline.buffer(SAME).covers(Point(p))
    if len(parts) > 1 or (parts and starts_in and line.project(Point(parts[0].coords[0])) > 2 * SAME):
        raise Stop("route_reenters", x=_show(p)[0], y=_show(p)[1])


def _leaves_once_all(leg: Tight, room, p) -> None:
    """`_leaves_once` for every tied curve at once: a curve from a start in an end-only room into the floor beyond its
    passage never comes back into the room. Walked piece by piece in the order of their offsets, each place on the
    curves knows whether a curve reaching it has already been inside the room (a start in the room has); a piece that
    comes into the room (meets its inside in a part not starting at its own start, or starting outside it) where a
    curve reaching its start has been inside, or that meets it twice, is a curve coming back in."""
    inside = room.outline.buffer(-SAME)
    grown = inside.buffer(2 * SAME)
    been = [(tuple(p), 0.0, room.outline.buffer(SAME).covers(Point(p)))]     # (place, offset, been inside there)
    for piece, offset in sorted(leg.pieces, key=lambda x: x[1]):
        start, end = _ends(piece)
        before = [f for q, o, f in been if math.dist(q, start) <= 1e-4 and abs(o - offset) <= 1e-4]
        was_in = any(before) if before else True             # a place no curve is seen reaching: the cautious side
        line = _polyline([piece])
        parts = []
        if line is not None:
            got = line.intersection(inside)
            parts = [g for g in getattr(got, "geoms", [got]) if not g.is_empty and g.length > EPS]
        enters = bool(parts) and (not grown.covers(Point(start)) or line.project(Point(parts[0].coords[0])) > 2 * SAME)
        if len(parts) > 1 or (enters and was_in):
            raise Stop("route_reenters", x=_show(p)[0], y=_show(p)[1])
        been.append((end, offset + _piece_length(piece), was_in or bool(parts)))


def _polyline(pieces):
    pts = []
    for q in pieces:
        if q[0] == "line":
            seg = [q[1], q[2]]
        else:
            _, c, r, a, s = q
            n = max(2, int(abs(s) / math.radians(0.5)) + 1)
            seg = [(c[0] + r * math.cos(a + s * k / (n - 1)), c[1] + r * math.sin(a + s * k / (n - 1)))
                   for k in range(n)]
        pts += seg if not pts else seg[1:]
    return LineString(pts) if len(pts) >= 2 else None
