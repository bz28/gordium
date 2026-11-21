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
1e-6 ft are a tie (decision 2): every tied route is kept, so the common path (a later step) can take the one that
shares more (decision 5). `travel` gives the length alone, from the same graph built once per zone, for sampling.

A route from an end-only room into the floor beyond its passage that comes back into the room stops (needs review).

Lengths are inches; `Route.feet` gives feet.
"""

import bisect
import heapq
import math
from dataclasses import dataclass

import numpy as np
from shapely import prepare
from shapely.geometry import LineString, Point

from model_measurement.routes.floor import CLEARANCE, SAME, Story, Zone, region
from model_measurement.routes.stops import Stop

FOOT = 12.0
TIE = 1e-6 * FOOT            # in: two route lengths this close are a tie (decision 2)
EPS = 1e-6                   # in: touching (a tangent line on its ring, a line along a wall)
MOST_TIES = 64


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


def _show(p) -> tuple:
    return round(p[0] / FOOT, 3) + 0.0, round(p[1] / FOOT, 3) + 0.0


# --- one leg ---------------------------------------------------------------------------------------------------------

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

    def covers(self, p) -> bool:
        return self.cover.covers(Point(p))

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
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                if self.clear(xy[a], xy[b]):
                    link(a, b, ("line", xy[a], xy[b]))
        for k, c in enumerate(rings):
            c = (float(c[0]), float(c[1]))
            for a in ids:
                for ang, q, _ in self._tangents(xy[a], k, c):
                    if q is None:
                        on[k].append((ang, a))
                    else:
                        n = node(q)
                        on[k].append((ang, n))
                        link(a, n, ("line", xy[a], q))
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
                    if self.clear(qi, qj):
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

    def prepare(self, targets) -> None:
        """The graph among the rings and these targets (door centres), with each target's distance to every node."""
        targets = [tuple(map(float, t)) for t in targets]
        if self._base is not None and self._base[0] == targets:
            return
        xy, adj, on, ids = self._graph(targets + self.bends)
        dists = {t: _dijkstra(adj, n) for t, n in zip(targets, ids)}
        self._base = (targets, on, dists, ids[len(targets):])

    def dist(self, p, t) -> float:
        """The length of the shortest curve from p (clear of every ring) to the target t (one given to `prepare`):
        inf if there is none. Such a curve goes straight to t, or to a corner (no clearance), or to a ring at a
        tangent point and round it to the first node there: every way it can leave a ring is a node of the graph."""
        _, on, dists, bend_ids = self._base
        t = tuple(map(float, t))
        D = dists[t]
        best = math.dist(p, t) if self.clear(p, t) else math.inf
        for b, n in zip(self.bends, bend_ids):
            if math.isfinite(D[n]) and math.dist(p, b) + D[n] < best and self.clear(p, b):
                best = math.dist(p, b) + D[n]
        for k in range(len(self.rings)):
            ring = on[k]
            if not ring:
                continue
            c = (float(self.rings[k][0]), float(self.rings[k][1]))
            angles = [a for a, _ in ring]
            for ang, _, length in self._tangents(p, k, c):
                if length >= best:
                    continue
                i = bisect.bisect_left(angles, ang)
                after, before = ring[i % len(ring)], ring[(i - 1) % len(ring)]
                # round the ring each way to the first node met
                for (a1, n1), a0, sweep in ((after, ang, (after[0] - ang) % (2 * math.pi)),
                                            (before, before[0], (ang - before[0]) % (2 * math.pi))):
                    got = length + self.r * sweep + D[n1]
                    if got < best and self._arc_clear(k, c, a0, sweep):
                        best = got
        return best

    def _arc_clear(self, k, c, a0, sweep) -> bool:
        active = self.rings
        r, slack = self.r, EPS / self.r
        if sweep <= slack:
            return True
        for j in range(len(active)):
            if j == k:
                continue
            d = math.dist(c, active[j])
            if d >= 2 * r - EPS:
                continue
            phi, beta = math.atan2(active[j][1] - c[1], active[j][0] - c[0]), math.acos(d / (2 * r))
            u = (phi - beta - a0) % (2 * math.pi)
            if u < sweep - slack or u + 2 * beta - 2 * math.pi > slack:
                return False
        cuts = sorted(x for x in _circle_walls(self.walls, c, r, a0) if slack < x < sweep - slack)
        marks = [0.0, *cuts, sweep]
        for x0, x1 in zip(marks, marks[1:]):
            mid = a0 + (x0 + x1) / 2
            if not self.cover.covers(Point(c[0] + r * math.cos(mid), c[1] + r * math.sin(mid))):
                return False
        return True


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
                out.append((math.atan2(y, x) - a0) % (2 * math.pi))
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
        self._start_cache, self._plain = {}, None
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
            for i, a in enumerate(zone.doors):
                for b in zone.doors[i + 1:]:
                    paths = self._leg(zone, doors[a].centre, doors[b].centre)
                    if paths:
                        edges.setdefault(a, []).append((b, zone, paths))
                        edges.setdefault(b, []).append((a, zone, [Path(q.length, [_reverse(x) for x in
                                                                                  reversed(q.pieces)])
                                                                  for q in paths]))
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
            for u, _, paths in edges.get(v, []):
                if doors[u].exit_kind:
                    continue                                 # another exit: an end, never passed through
                w = paths[0].length
                if dv + w < dist[u]:
                    dist[u] = dv + w
                    heapq.heappush(heap, (dv + w, u))
        steps = {}
        for v in doors:
            if not math.isfinite(dist[v]) or doors[v].exit_kind:
                continue
            steps[v] = [(u, paths) for u, _, paths in edges.get(v, [])
                        if paths[0].length + dist[u] <= dist[v] + TIE]
        self._chains[wanted] = (dist, steps, edges)
        return self._chains[wanted]

    def _chains_from(self, door_id, wanted, at) -> list[tuple]:
        """Every tied chain from a door centre to an exit: (pieces, doors passed, exit id)."""
        dist, steps, _ = self._chain(wanted)
        door = self.story.doors[door_id]
        if door.exit_kind and door.exit_id in wanted:
            return [([], (door_id,), door.exit_id)]
        out = []
        for u, paths in steps.get(door_id, []):
            for rest, passed, exit_id in self._chains_from(u, wanted, at):
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
        return [r for r in self.story.rooms.values() if r is not None and r.outline.buffer(EPS).covers(Point(p))]

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

    def _no_route(self, p, at, exit_ids, wanted):
        """No route: say so, and say it is an opening too narrow for the clearance when one with none exists."""
        if self.r > 0:
            if self._plain is None:
                self._plain = StoryRoutes(self.story, 0.0)
            try:
                self._plain.route(p, exit_ids)
            except Stop:
                pass
            else:
                return Stop("too_narrow", x=at[0], y=at[1])
        return Stop("no_route", x=at[0], y=at[1], exits="any exit" if exit_ids is None else
                    "the exit " + ", ".join(sorted(wanted)))

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
                raise self._no_route(p, at, exit_ids, wanted)    # a start in either room may need it
            if best_of_rooms is None or found[0].length > best_of_rooms[0].length + TIE:
                best_of_rooms = found                       # a point on two rooms' line: the longer (cautious)
        return best_of_rooms

    def route(self, point, exit_ids=None) -> Route:
        return self.routes(point, exit_ids)[0]

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
            if len(starts) > 1:                              # an end-only room joined beyond its passages
                worst = max(worst, self.route(p, exit_ids).length)
                continue
            zone = starts[0][0]
            engine = self._engine(zone)
            if not engine.covers(p):
                raise Stop("not_on_floor", x=at[0], y=at[1])
            doors = [d for d in zone.doors if math.isfinite(dist.get(d, math.inf))]
            engine.prepare([self.story.doors[d].centre for d in zone.doors])
            best = min((engine.dist(p, self.story.doors[d].centre) + dist[d] for d in doors), default=math.inf)
            if not math.isfinite(best):
                raise self._no_route(p, at, exit_ids, wanted)
            worst = max(worst, best)
        return worst

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

    def _from_room(self, room, p, wanted, dist, at):
        """The shortest routes from p, a point in this room: in its zone; or, in an end-only room, in the room
        alone to its own doors, and joined to each crossable zone beyond its passages to that zone's doors (a
        route may leave it that way, never come back in: decision 1)."""
        story = self.story
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
    if len(parts) > 1 or (parts and line.project(Point(parts[0].coords[0])) > 2 * SAME):
        raise Stop("route_reenters", x=_show(p)[0], y=_show(p)[1])


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
