"""Common path of egress travel (decision 5 of docs/decisions/2026-11-20_route_measurement.md), measured on the routes
themselves (paths.py), until those to two distinct exits part for good.

    shared(a, b)                          -> the travel distance from the start to the last point two routes share
    at_point(story_routes, p)             -> CommonPath(length, exits, routes)
    story_figure(story_routes, rooms=None) -> remote.Remote: decision 3's bound, with the common path as the value

IBC 2009 1002.1: "Paths that merge are common paths of travel." From a point clear of every ring, Gordium takes its
shortest route to each distinct exit (by `exit_id`, never by door). For two routes the common path is the travel
distance from the point to the **last point the two routes share** (a door centre, a ring, a stretch walked
together), so a stretch where they meet again after parting counts, and two routes that share only the start give 0.
Where two routes to one exit are equally short (within 1e-6 ft: paths.py keeps every tied route), the one that shares
more is taken (the cautious side). The point's common path is the least over the pairs of distinct exits it has
routes to. One exit on the story (or one the point reaches): the common path is the travel distance.

The story's figure is worked exactly as decision 3's (remote.farthest, the same samples, triangles and cluster
margins): the law's figure changes no faster than you walk, and Gordium's routes are one pair a person could take, so
its figure at a sample is never less than the law's. Lengths in inches.
"""

import bisect
import heapq
import math
from dataclasses import dataclass, field
from itertools import combinations

from model_measurement.routes.paths import (EPS, MOST_TIES, TIE, Route, StoryRoutes, _piece_length, _show,
                                            _signature, _tidy)
from model_measurement.routes.remote import Remote, farthest
from model_measurement.routes.stops import Stop

TOL = EPS                      # in: two routes this close share the point (their pieces come from the same formulas)
UNREACHED = ("no_route", "too_narrow")      # a point with no route to this exit (it may still have one to others)


@dataclass
class CommonPath:
    length: float              # in
    exits: tuple               # the pair of exit ids that gave it (one, when the point reaches one exit)
    routes: list = field(default_factory=list)      # the two routes taken (the tie that shares more)


# --- where two routes meet -------------------------------------------------------------------------------------------

def _arc_ends(piece):
    _, c, r, a, s = piece
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a)), (c[0] + r * math.cos(a + s), c[1] + r * math.sin(a + s))


def _on_arc(piece, q) -> float | None:
    """How far along the arc q lies (in), or None if q isn't on it (within TOL)."""
    _, c, r, a0, sweep = piece
    if abs(math.dist(q, c) - r) > TOL:
        return None
    off = ((math.atan2(q[1] - c[1], q[0] - c[0]) - a0) * (1 if sweep >= 0 else -1)) % (2 * math.pi)
    slack = TOL / r
    if off <= abs(sweep) + slack:
        return min(off, abs(sweep)) * r
    if off >= 2 * math.pi - slack:
        return 0.0
    return None


def _on_line(piece, q) -> float | None:
    _, a, b = piece
    d = (b[0] - a[0], b[1] - a[1])
    n = math.hypot(*d)
    if n <= TOL:
        return 0.0 if math.dist(a, q) <= TOL else None
    t = ((q[0] - a[0]) * d[0] + (q[1] - a[1]) * d[1]) / n
    if t < -TOL or t > n + TOL:
        return None
    foot = (a[0] + d[0] * t / n, a[1] + d[1] * t / n)
    return min(max(t, 0.0), n) if math.dist(foot, q) <= TOL else None


def _along(piece, q):
    return _on_line(piece, q) if piece[0] == "line" else _on_arc(piece, q)


def _ends(piece):
    return (piece[1], piece[2]) if piece[0] == "line" else _arc_ends(piece)


def _line_line(p, q) -> list:
    (_, a1, b1), (_, a2, b2) = p, q
    d1, d2 = (b1[0] - a1[0], b1[1] - a1[1]), (b2[0] - a2[0], b2[1] - a2[1])
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    n1, n2 = math.hypot(*d1), math.hypot(*d2)
    if abs(cross) <= 1e-12 * max(n1 * n2, 1e-300):
        return []                                    # parallel: any meeting is an end on the other (taken apart)
    w = (a2[0] - a1[0], a2[1] - a1[1])
    t = (w[0] * d2[1] - w[1] * d2[0]) / cross
    return [(a1[0] + d1[0] * t, a1[1] + d1[1] * t)]


def _line_circle(line, c, r) -> list:
    _, a, b = line
    d = (b[0] - a[0], b[1] - a[1])
    n = math.hypot(*d)
    if n <= TOL:
        return []
    u = (d[0] / n, d[1] / n)
    t = (c[0] - a[0]) * u[0] + (c[1] - a[1]) * u[1]
    foot = (a[0] + u[0] * t, a[1] + u[1] * t)
    h = math.dist(foot, c)
    if abs(h - r) <= TOL:
        return [foot]                                # a tangent: it touches the ring at its foot
    if h > r:
        return []
    k = math.sqrt(r * r - h * h)
    return [(foot[0] - u[0] * k, foot[1] - u[1] * k), (foot[0] + u[0] * k, foot[1] + u[1] * k)]


def _circle_circle(c1, r1, c2, r2) -> list:
    d = math.dist(c1, c2)
    if d <= TOL or d > r1 + r2 + TOL or d < abs(r1 - r2) - TOL:
        return []
    a = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    m = (c1[0] + (c2[0] - c1[0]) * a / d, c1[1] + (c2[1] - c1[1]) * a / d)
    if h <= TOL:
        return [m]
    ox, oy = -(c2[1] - c1[1]) * h / d, (c2[0] - c1[0]) * h / d
    return [(m[0] + ox, m[1] + oy), (m[0] - ox, m[1] - oy)]


def _meetings(p, q) -> list:
    """Candidate points both pieces may hold: every end of each (an overlap's ends are among them), and where the two
    cross or touch. Each is kept only if it lies on both."""
    out = list(_ends(p)) + list(_ends(q))
    if p[0] == "line" and q[0] == "line":
        out += _line_line(p, q)
    elif p[0] == "line" or q[0] == "line":
        line, arc = (p, q) if p[0] == "line" else (q, p)
        out += _line_circle(line, arc[1], arc[2])
    elif math.dist(p[1], q[1]) > TOL or abs(p[2] - q[2]) > TOL:
        out += _circle_circle(p[1], p[2], q[1], q[2])
    return out


def _starts(pieces) -> list:
    s, out = 0.0, []
    for q in pieces:
        out.append(s)
        s += math.dist(q[1], q[2]) if q[0] == "line" else abs(q[4]) * q[2]
    return out


def shared(a, b) -> float:
    """The travel distance (in) from the start of two routes from one point to the last point they share. Both are
    shortest routes from that point, so the stretch of each up to a shared point is as long as the other's; the
    greater of the two is taken (the cautious side)."""
    sa, sb = _starts(a.pieces), _starts(b.pieces)
    best = 0.0
    for i, p in enumerate(a.pieces):
        for j, q in enumerate(b.pieces):
            for x in _meetings(p, q):
                u, v = _along(p, x), _along(q, x)
                if u is not None and v is not None:
                    best = max(best, sa[i] + u, sb[j] + v)
    return best


# --- every tied route, fast -----------------------------------------------------------------------------------------

class _Prepared:
    """A zone's graph among its rings and door centres, built once, with each door centre's distance to every node:
    the same graph paths.py's `travel` uses, kept here with its pieces so a route's first leg is read from it."""

    def __init__(self, engine, centres):
        self.engine = engine
        self.targets = [tuple(map(float, t)) for t in centres]
        self.xy, self.adj, self.on, ids = engine._graph(self.targets)
        self.ids = dict(zip(self.targets, ids))
        self.dist = {t: _dijkstra(self.adj, n) for t, n in self.ids.items()}
        self._last = None

    def _onward(self, n, t, out, at):
        """Every tied walk on the graph from node n to target t (each within 1e-6 ft of the shortest, as paths.py's
        `_tied` keeps them)."""
        goal, D = self.ids[t], self.dist[t]
        top = D[n] + TIE

        def walk(v, so_far, pieces, seen):
            if len(out) > MOST_TIES:
                raise Stop("too_many_ties", most=MOST_TIES, x=at[0], y=at[1])
            if v == goal:
                out.append(list(pieces))
                return
            for u, w, piece in self.adj[v]:
                if u in seen or so_far + w + D[u] > top:
                    continue
                pieces.append(piece)
                walk(u, so_far + w, pieces, seen | {u})
                pieces.pop()

        walk(n, 0.0, [], {n})

    def firsts(self, p) -> list:
        """Every way a curve from p (clear of every ring) can reach the graph: by a tangent to a ring and round it to
        the first node there, each way (length, pieces, node). Worked once per point, for every target."""
        if self._last is not None and self._last[0] == p:
            return self._last[1]
        e, r = self.engine, self.engine.r
        out = []
        for k in range(len(e.rings)):
            ring = self.on[k]
            if not ring:
                continue
            c = (float(e.rings[k][0]), float(e.rings[k][1]))
            angles = [a for a, _ in ring]
            for ang, q, length in e._tangents(p, k, c):
                i = bisect.bisect_left(angles, ang)
                after, before = ring[i % len(ring)], ring[(i - 1) % len(ring)]
                lead = [("line", p, q)] if q is not None else []
                up, down = (after[0] - ang) % (2 * math.pi), (ang - before[0]) % (2 * math.pi)
                for n1, a0, sweep, piece in ((after[1], ang, up, ("arc", c, r, ang, up)),
                                             (before[1], before[0], down, ("arc", c, r, ang, -down))):
                    if e._arc_clear(k, c, a0, sweep):
                        out.append((length + r * sweep, lead + [piece], n1))
        self._last = (p, out)
        return out

    def legs(self, p, t) -> list:
        """(length, pieces) of every tied shortest curve from p (clear of every ring) to the target t, as
        `_Leg.dist` measures it: straight to t, or by a tangent to a ring and round it to the first node there."""
        D = self.dist[t]
        cands = [(lead_len + D[n], lead, n) for lead_len, lead, n in self.firsts(p) if math.isfinite(D[n])]
        if self.engine.clear(p, t):
            cands.append((math.dist(p, t), [("line", p, t)], None))
        if not cands:
            return []
        best = min(f[0] for f in cands)
        out = []
        for total, lead, n in cands:
            if total > best + TIE:
                continue
            if n is None:
                out.append((total, lead))
                continue
            walks = []
            self._onward(n, t, walks, _show(p))
            out += [(total, lead + w) for w in walks]
        return out


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


def tied_routes(routes: StoryRoutes, point, exit_id) -> list:
    """Every tied shortest route from a point to one exit, as `routes.routes(point, [exit_id])` gives them, its
    first leg read from the zone's graph built once (the slow way where a start is joined beyond its passages, or
    sits on the line between two rooms, or the clearance is 0)."""
    p = (float(point[0]), float(point[1]))
    rooms = routes.rooms_at(p)
    if routes.r <= 0 or len(rooms) != 1 or len(routes._starts(rooms[0])) != 1:
        return routes.routes(p, [exit_id])
    room, at = rooms[0], _show(p)
    wanted = routes._wanted([exit_id])
    dist, _, _ = routes._chain(wanted)
    routes._check_start(room, p, at)
    zone = routes._starts(room)[0][0]
    engine = routes._engine(zone)
    if not engine.covers(p):
        raise Stop("not_on_floor", x=at[0], y=at[1])
    cache = routes.__dict__.setdefault("_common_prepared", {})
    if zone.rooms not in cache:
        cache[zone.rooms] = _Prepared(engine, [routes.story.doors[d].centre for d in zone.doors])
    prepared = cache[zone.rooms]
    legs = []
    for d in zone.doors:
        if not math.isfinite(dist.get(d, math.inf)):
            continue
        t = tuple(map(float, routes.story.doors[d].centre))
        legs += [(length + dist[d], pieces, d) for length, pieces in prepared.legs(p, t)]
    if not legs:
        raise routes._no_route(p, at, [exit_id], wanted)
    best = min(x[0] for x in legs)
    out = []
    for total, pieces, d in sorted(legs, key=lambda x: x[0]):
        if total > best + TIE:
            break
        for rest, passed, eid in routes._chains_from(d, wanted, at):
            whole = _tidy(pieces + rest)
            out.append(Route(sum(_piece_length(q) for q in whole), whole, passed, eid))
            if len(out) > MOST_TIES:
                raise Stop("too_many_ties", most=MOST_TIES, x=at[0], y=at[1])
    seen, unique = set(), []
    for x in out:
        key = _signature(x.pieces)
        if key not in seen:
            seen.add(key)
            unique.append(x)
    return unique


# --- a point ---------------------------------------------------------------------------------------------------------

def at_point(routes: StoryRoutes, point) -> CommonPath:
    """The common path from a point clear of every ring (decision 5)."""
    tied, first = {}, None
    for e in sorted(routes.exits):
        try:
            tied[e] = tied_routes(routes, point, e)
        except Stop as s:
            if s.key not in UNREACHED:
                raise
            first = first or s
    if not tied:
        raise first if first is not None else Stop("no_route", x=_show(point)[0], y=_show(point)[1], exits="any exit")
    if len(tied) == 1:                                   # one exit: the common path is the travel distance
        (e, got), = tied.items()
        return CommonPath(got[0].length, (e,), [got[0]])
    best = None
    for e1, e2 in combinations(sorted(tied), 2):
        most = max(((shared(x, y), x, y) for x in tied[e1] for y in tied[e2]), key=lambda t: t[0])
        if best is None or most[0] < best.length:
            best = CommonPath(most[0], (e1, e2), [most[1], most[2]])
    return best


# --- the story's figure ----------------------------------------------------------------------------------------------

class _Rooms:
    """The rooms farthest() walks, in an order that finds a large figure early (rooms a route can't cross first,
    the largest first; corridors and other crossable rooms last), so the triangles that can't beat it are dropped
    sooner. The order changes nothing else: every triangle is dropped only on its own proved bound."""

    def __init__(self, story, rooms):
        got = [(k, v) for k, v in story.rooms.items() if (rooms is None or k in rooms) and v is not None]
        got.sort(key=lambda kv: (kv[1].crossable, -kv[1].outline.area, kv[0]))
        self.rooms = dict(got)


class _CommonPathSampler:
    """What remote.farthest reads (`r`, `story.rooms`, `rings_for`, `travel`), with the common path as the value."""

    def __init__(self, routes: StoryRoutes, rooms=None):
        self.r, self._routes = routes.r, routes
        self.story = _Rooms(routes.story, rooms)

    def rings_for(self, room):
        return self._routes.rings_for(room)

    def travel(self, point, exit_ids=None):
        cache = self._routes.__dict__.setdefault("_common_values", {})
        key = (round(point[0], 9), round(point[1], 9))
        if key not in cache:
            cache[key] = at_point(self._routes, point).length
        return cache[key]


def story_figure(routes: StoryRoutes, rooms=None) -> Remote:
    """The greatest common path over the story's floor (or these rooms' only), as decision 3's bound: the clear floor's
    greatest sample plus 3 in (4.5 in next to the rings), each ring cluster's greatest clear-edge sample plus 1.5 in
    plus its margin (the walk out is shared by both routes). One exit on the story: the travel figure itself."""
    if len(routes.exits) < 2:
        return farthest(_TravelOnly(routes, rooms) if rooms is not None else routes)
    return farthest(_CommonPathSampler(routes, rooms))


class _TravelOnly(_CommonPathSampler):
    def travel(self, point, exit_ids=None):
        return self._routes.travel(point, exit_ids)
