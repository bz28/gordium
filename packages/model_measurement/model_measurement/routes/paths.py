"""Routes on a story's floor: decision 2 of docs/decisions/2026-11-20_route_measurement.md, exactly.

The route from a point p to an exit is the shortest curve that (a) lies in the free floor of the rooms it may cross
(floor.py's zones), passing each door at its centre; (b) stays at least 12 in from every corner that sticks into the
floor, every obstruction corner and every door jamb (a true circle of 12-in radius: a ring); except that (c) inside
a ring that contains p, or the door centre it passes, it may run within that ring until it leaves it.

How it is computed. Every route passes a door centre between zones, so a route is a chain of legs, each in one zone
from a point or door centre to a door centre (decision 1). A leg is a shortest path among circles and polygon walls,
which is made only of straight lines tangent to rings and arcs along them (bending at no other place: a wall's own
corner always has its ring, and where a ring meets a wall or another ring the free floor turns away from the path).
So each leg is found exactly on a graph: its ends; the corners whose rings are lifted (c); the tangent points of
every line from those points to each ring and of the four lines common to each pair of rings; each line kept only
if it stays in the floor and out of every ring; and the arcs between neighbouring tangent points on each ring, kept
only if they stay in the floor and out of every other ring. Dijkstra on it gives the leg, and Dijkstra over the door
centres, from the exits, the chain. Two lengths within 1e-6 ft are a tie (decision 2): every tied route is kept, so
the common path (a later step) can take the one that shares more (decision 5).

A ring lifted for a leg must be the leg's start or end piece only: a route that left it and came back in is longer
under the definition, so it stops (needs review) rather than give a short figure; so does a route from an end-only
room that goes back into it.

Lengths are inches; `Route.feet` gives feet.
"""

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
    """The shortest curves in one floor from p to t, among the rings (decision 2)."""

    def __init__(self, floor, rings, corners, r):
        self.floor, self.r = floor, r
        self.cover = floor.buffer(EPS)
        prepare(self.cover)
        self.rings = np.array(rings, dtype=float).reshape(-1, 2)
        self.corners = [tuple(c) for c in corners]
        segs = []
        for poly in getattr(floor, "geoms", [floor]):
            if poly.geom_type != "Polygon":
                continue
            for ring in [poly.exterior, *poly.interiors]:
                pts = list(ring.coords)
                segs += [(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
        self.walls = np.array(segs, dtype=float).reshape(-1, 4)

    def covers(self, p) -> bool:
        return self.cover.covers(Point(p))

    def paths(self, p, t) -> list[Path]:
        r = self.r
        if math.dist(p, t) <= EPS:
            return [Path(0.0, [])]
        if r > 0 and len(self.rings):
            near = (np.hypot(*(self.rings - p).T) < r - EPS) | (np.hypot(*(self.rings - t).T) < r - EPS)
        else:
            near = np.zeros(len(self.rings), dtype=bool)
        lifted = self.rings[near]
        active = self.rings[~near] if r > 0 else self.rings[:0]
        bends = [c for c in self.corners
                 if (not len(active) or np.hypot(*(active - c).T).min() >= r - EPS)
                 and math.dist(c, p) > EPS and math.dist(c, t) > EPS]
        xy, adj = [], []

        def node(pt):
            xy.append((float(pt[0]), float(pt[1])))
            adj.append([])
            return len(xy) - 1

        def link(a, b, piece):
            w = _piece_length(piece)
            adj[a].append((b, w, piece))
            adj[b].append((a, w, _reverse(piece)))

        def clear(a, b) -> bool:
            if math.dist(a, b) <= EPS:
                return True
            if not self.cover.covers(LineString([a, b])):
                return False
            return not len(active) or _seg_dist(active, a, b).min() >= r - EPS

        P, T = node(p), node(t)
        points = [P, T] + [node(b) for b in bends]
        on = [[] for _ in range(len(active))]
        for i, a in enumerate(points):
            for b in points[i + 1:]:
                if clear(xy[a], xy[b]):
                    link(a, b, ("line", xy[a], xy[b]))
        for k, c in enumerate(active):
            c = (float(c[0]), float(c[1]))
            for a in points:
                d = math.dist(xy[a], c)
                if d < r - EPS:
                    continue
                base = math.atan2(xy[a][1] - c[1], xy[a][0] - c[0])
                if d <= r + EPS:
                    on[k].append((base % (2 * math.pi), a))
                    continue
                alpha = math.acos(r / d)
                for ang in (base + alpha, base - alpha):
                    q = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
                    if clear(xy[a], q):
                        n = node(q)
                        on[k].append((ang % (2 * math.pi), n))
                        link(a, n, ("line", xy[a], q))
        for i in range(len(active)):
            ci = (float(active[i][0]), float(active[i][1]))
            for j in range(i + 1, len(active)):
                cj = (float(active[j][0]), float(active[j][1]))
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
                    if clear(qi, qj):
                        ni, nj = node(qi), node(qj)
                        on[i].append((ai % (2 * math.pi), ni))
                        on[j].append((aj % (2 * math.pi), nj))
                        link(ni, nj, ("line", qi, qj))
        for k in range(len(active)):
            c = (float(active[k][0]), float(active[k][1]))
            ring = sorted(on[k])
            if len(ring) < 2:
                continue
            for m, (a0, n0) in enumerate(ring):
                a1, n1 = ring[(m + 1) % len(ring)]
                sweep = (a1 - a0) % (2 * math.pi)
                if self._arc_clear(k, active, c, a0, sweep):
                    link(n0, n1, ("arc", c, r, a0, sweep))
        found = _tied(adj, P, T)
        if found is None:
            raise Stop("too_many_ties", most=MOST_TIES, x=_show(p)[0], y=_show(p)[1])
        out, seen = [], set()
        for pieces in found:
            pieces = _tidy(pieces)
            key = _signature(pieces)
            if key in seen:
                continue
            seen.add(key)
            path = Path(sum(_piece_length(q) for q in pieces), pieces)
            for c in lifted:
                _check_lifted(path, (float(c[0]), float(c[1])), r, p, t)
            out.append(path)
        return out

    def _arc_clear(self, k, active, c, a0, sweep) -> bool:
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
    """Every shortest walk from P to T (within TIE), as lists of pieces: Dijkstra from T, then every next step
    that keeps to the least."""
    dist = [math.inf] * len(adj)
    dist[T] = 0.0
    heap = [(0.0, T)]
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        for u, w, _ in adj[v]:
            if d + w < dist[u]:
                dist[u] = d + w
                heapq.heappush(heap, (d + w, u))
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


def _inside_spans(pieces, c, r) -> list[tuple]:
    """Where along the path (as lengths from its start) it is strictly inside the ring at c."""
    spans, s0 = [], 0.0
    for q in pieces:
        n = _piece_length(q)
        if q[0] == "line":
            a, b = np.array(q[1]), np.array(q[2])
            d, f = b - a, a - np.array(c)
            A, B, C = d @ d, 2 * (f @ d), f @ f - r * r
            disc = B * B - 4 * A * C
            if A > 0 and disc > 0:
                u0, u1 = (-B - math.sqrt(disc)) / (2 * A), (-B + math.sqrt(disc)) / (2 * A)
                lo, hi = max(u0, 0.0), min(u1, 1.0)
                if hi - lo > 0:
                    spans.append((s0 + lo * n, s0 + hi * n))
        else:
            _, cc, rr, a, sweep = q
            d = math.dist(cc, c)
            if d < 2 * r:
                phi, beta = math.atan2(c[1] - cc[1], c[0] - cc[0]), math.acos(d / (2 * r))
                sign = 1 if sweep > 0 else -1
                # along the arc, angle a + sign * x for x in [0, |sweep|]: inside where it is within beta of phi
                for k in (-1, 0, 1):
                    mid = (sign * (phi - a)) % (2 * math.pi) + 2 * math.pi * k
                    lo, hi = max(mid - beta, 0.0), min(mid + beta, abs(sweep))
                    if hi - lo > 0:
                        spans.append((s0 + lo * rr, s0 + hi * rr))
        s0 += n
    spans.sort()
    merged = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1] + EPS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return [(lo, hi) for lo, hi in merged if hi - lo > EPS]


def _check_lifted(path: Path, c, r, p, t) -> None:
    """A ring lifted for a leg (it holds p or t) may hold only the leg's start piece (p's) and end piece (t's). The
    path starts inside it if it holds p and ends inside it if it holds t, so those pieces are its first and last
    spans inside: any more is a way back in."""
    spans = _inside_spans(path.pieces, c, r)
    allowed = (math.dist(p, c) < r - EPS) + (math.dist(t, c) < r - EPS)
    if len(spans) > allowed:
        raise Stop("route_reenters", x=_show(p)[0], y=_show(p)[1])


# --- a story's routes ------------------------------------------------------------------------------------------------

class StoryRoutes:
    """Every route on one story (decisions 1, 1a, 2 and 4). `clearance` is the rings' radius (12 in; 0 gives the
    no-clearance figure the eval compares a hand path with)."""

    def __init__(self, story: Story, clearance: float = CLEARANCE):
        if story.stops:
            raise Stop("story_not_measured", reasons="; ".join(story.stops))
        self.story, self.r = story, clearance
        self._engines, self._legs, self._chains, self._regions = {}, {}, {}, {}
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

    def routes(self, point, exit_ids=None) -> list[Route]:
        """Every shortest route (ties within 1e-6 ft) from a point (inches) to the nearest of the exits named by
        exit id (all the story's exits if none are named)."""
        p = (float(point[0]), float(point[1]))
        at = _show(p)
        wanted = frozenset(self.exits if exit_ids is None else exit_ids)
        for e in wanted:
            if e not in self.exits:
                raise Stop("exit_unknown", exit_id=e)
        dist, _, _ = self._chain(wanted)
        rooms = [r for r in self.story.rooms.values() if r is not None and r.outline.buffer(EPS).covers(Point(p))]
        if not rooms:
            raise Stop("not_on_floor", x=at[0], y=at[1])
        best_of_rooms = None
        for room in rooms:
            found = self._from_room(room, p, wanted, dist, at)
            if found is None:
                continue
            if best_of_rooms is None or found[0].length > best_of_rooms[0].length + TIE:
                best_of_rooms = found                       # a point on two rooms' line: the longer (cautious)
        if best_of_rooms is None:
            raise Stop("no_route", x=at[0], y=at[1], exits="any exit" if exit_ids is None else
                       "the exit " + ", ".join(sorted(wanted)))
        return best_of_rooms

    def route(self, point, exit_ids=None) -> Route:
        return self.routes(point, exit_ids)[0]

    def _region(self, room_ids) -> Zone:
        key = tuple(sorted(room_ids))
        if key not in self._regions:
            self._regions[key] = region(self.story, key)
        return self._regions[key]

    def _from_room(self, room, p, wanted, dist, at):
        """The shortest routes from p, a point in this room: in its zone; or, in an end-only room, in the room
        alone to its own doors, and joined to each crossable zone beyond its passages to that zone's doors (a
        route may leave it that way, never come back in: decision 1)."""
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
