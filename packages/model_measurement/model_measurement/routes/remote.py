"""The story's travel figure (decision 3 of docs/decisions/2026-11-20_route_measurement.md): an upper bound, proved,
on the greatest route length over the whole floor, from samples.

    farthest(story_routes) -> Remote(figure, greatest, at, floor_bound, near_rings_bound, clusters, part, samples)

Two parts, the figure the greater:

- **The clear floor F** (at least 12 in from every corner, where routes are defined). Each room's floor is cut into
  triangles, every corner of the floor among theirs, every triangle corner in F a sample. A route can't grow faster
  than you walk, so in a triangle no ring reaches every point is within h (its farthest from all three corners) of a
  corner by a straight line inside it: its bound is its greatest corner plus its own h. Such a triangle is dropped
  only when that bound can't beat the best sample found so far, else cut (longest side halved) down to 3 in. A
  triangle a ring reaches is never dropped: it is cut to 3 in, every clear corner taken, and its clear points are
  bounded through E (below): 3 in to E, then 1.5 in along it, so the greatest E sample plus 4.5 in.
- **The clusters** (one ring, or rings that overlap), for the points inside them, where no route is defined. E, the
  rings' clear edges (each ring's circle on the floor and clear of every other ring), is found exactly from the
  circles and sampled at most 3 in apart along each arc, ends included. A cluster's bound is its greatest edge
  sample, plus 1.5 in, plus its margin: 12 in for a lone ring whose floor is all in sight of its corner (every floor
  edge meeting the ring passes through its corner), else the greatest sampled walk on the floor (no clearance) out
  to its edge samples, over the corners of 3-in triangles covering it, plus 3 in.

Every sample with no route stops the figure (needs review), the reason named; an edge arc shut in by rings is
sampled at its ends at least, so a pocket shut in by rings is found from its own arcs. Lengths in inches.
"""

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from model_measurement.routes.floor import _reflex
from model_measurement.routes.paths import EPS, StoryRoutes, _circle_walls, _Leg, _show
from model_measurement.routes.stops import Stop

START = 24.0          # in: the triangles' longest side to begin with
FINE = 3.0            # in: the longest side they are cut to
SPACING = 3.0         # in: the most between E's samples along an arc
NEAR = FINE + SPACING / 2     # in: a clear point of a triangle a ring reaches, to E and along it
SIDES = 64            # the polygons that cover a cluster's rings for its walk-out samples


@dataclass
class Cluster:
    rings: list               # the ring centres
    edge_greatest: float      # the greatest route over its clear edge's samples
    edge_at: tuple
    margin: float             # the walk out to that edge, at most
    how: str                  # "lone ring in sight of its corner" or "walk out sampled"
    bound: float              # edge_greatest + 1.5 in + margin


@dataclass
class Remote:
    figure: float             # the rules' figure: the greatest bound
    greatest: float           # the greatest sample
    at: tuple                 # where
    floor_bound: float        # the clear floor's triangles no ring reaches
    near_rings_bound: float | None    # the clear points of triangles a ring reaches (greatest E sample + 4.5 in)
    clusters: list = field(default_factory=list)
    part: str = ""            # which part gave the figure
    samples: int = 0


def _longest(tri) -> float:
    a, b, c = tri
    return max(math.dist(a, b), math.dist(b, c), math.dist(c, a))


def own_h(tri) -> float:
    """The greatest distance from any point of the triangle to its nearest corner. It is reached at the circumcentre
    (when that is inside) or where a side's perpendicular bisector meets another side."""
    a, b, c = (np.array(p, dtype=float) for p in tri)
    corners = (a, b, c)
    candidates = list(corners)
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    poly = Polygon(tri)
    if abs(d) > 0:
        ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
        uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
        if poly.buffer(1e-9).covers(Point(ux, uy)):
            candidates.append(np.array([ux, uy]))
    for p, q in ((a, b), (b, c), (c, a)):              # each perpendicular bisector against each side
        mid, n = (p + q) / 2, np.array([-(q - p)[1], (q - p)[0]])
        for s, e in ((a, b), (b, c), (c, a)):
            m = np.array([e - s, -n]).T
            if abs(np.linalg.det(m)) < 1e-12:
                continue
            u, _ = np.linalg.solve(m, mid - s)
            if -1e-12 <= u <= 1 + 1e-12:
                candidates.append(s + u * (e - s))
    return max(min(np.hypot(*(x - k)) for k in corners) for x in candidates)


def droppable(tri, values, best) -> bool:
    """Decision 3: a triangle no ring reaches is dropped only when its greatest corner value plus its own h can't
    beat the best found so far (test 19)."""
    return max(values) + own_h(tri) <= best


def _split(tri):
    a, b, c = tri
    sides = [(math.dist(a, b), (a, b, c)), (math.dist(b, c), (b, c, a)), (math.dist(c, a), (c, a, b))]
    _, (p, q, o) = max(sides, key=lambda x: x[0])
    m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    return [(p, m, o), (m, q, o)]


def _triangles(region, longest) -> list:
    out = []
    for g in getattr(shapely.constrained_delaunay_triangles(region), "geoms", []):
        if g.area <= 0:
            continue
        stack = [tuple(map(tuple, list(g.exterior.coords)[:3]))]
        while stack:
            t = stack.pop()
            if _longest(t) > longest:
                stack += _split(t)
            else:
                out.append(t)
    return out


def _clear_arcs(floor, rings, r, walls):
    """Each ring's circle on the floor and clear of every other ring: [(ring index, start angle, sweep)]."""
    cover = floor.buffer(EPS)
    shapely.prepare(cover)
    out = []
    for k, c in enumerate(rings):
        cuts = [x for x in _circle_walls(walls, c, r, 0.0)]
        for j, o in enumerate(rings):
            d = math.dist(c, o)
            if j != k and 0 < d < 2 * r:
                phi, beta = math.atan2(o[1] - c[1], o[0] - c[0]), math.acos(d / (2 * r))
                cuts += [(phi - beta) % (2 * math.pi), (phi + beta) % (2 * math.pi)]
        cuts = sorted(set(round(x, 12) for x in cuts)) or [0.0]
        for i, a0 in enumerate(cuts):
            sweep = (cuts[(i + 1) % len(cuts)] - a0) % (2 * math.pi) or 2 * math.pi
            mid = a0 + sweep / 2
            q = (c[0] + r * math.cos(mid), c[1] + r * math.sin(mid))
            if all(math.dist(q, o) >= r - EPS for j, o in enumerate(rings) if j != k) and cover.covers(Point(q)):
                out.append((k, a0, sweep))
    return out


def _groups(rings, r) -> list[list[int]]:
    top = list(range(len(rings)))

    def find(i):
        while top[i] != i:
            i = top[i]
        return i

    for i in range(len(rings)):
        for j in range(i + 1, len(rings)):
            if math.dist(rings[i], rings[j]) < 2 * r - EPS:
                top[find(i)] = find(j)
    out = {}
    for i in range(len(rings)):
        out.setdefault(find(i), []).append(i)
    return list(out.values())


def _walls(floor):
    segs = []
    for poly in getattr(floor, "geoms", [floor]):
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)
            segs += [(*pts[i], *pts[i + 1]) for i in range(len(pts) - 1)]
    return np.array(segs, dtype=float).reshape(-1, 4)


def _in_sight(c, walls, r) -> bool:
    """Whether every floor edge meeting the ring at c passes through c (its floor all in sight of its corner)."""
    from model_measurement.routes.paths import _seg_dist
    centre = np.array([c])
    for x0, y0, x1, y1 in walls:
        d = _seg_dist(centre, (x0, y0), (x1, y1))[0]
        if d < r - EPS and d > 1e-6:
            return False
    return True


class _Walk:
    """The shortest walk on a floor, with no clearance, from a point to the nearest of some targets."""

    def __init__(self, floor, targets):
        polys = [orient(p, 1.0) for p in getattr(floor, "geoms", [floor])]
        corners = [v for p in polys for v in _reflex(p)]
        self.leg = _Leg(floor, [], corners, 0.0)
        self.nodes = [tuple(t) for t in targets] + corners
        xy, adj, _, ids = self.leg._graph(self.nodes)
        dist = [math.inf] * len(adj)
        heap = []
        for n in ids[:len(targets)]:
            dist[n] = 0.0
            heap.append((0.0, n))
        heapq.heapify(heap)
        while heap:
            d, v = heapq.heappop(heap)
            if d > dist[v]:
                continue
            for u, w, _ in adj[v]:
                if d + w < dist[u]:
                    dist[u] = d + w
                    heapq.heappush(heap, (d + w, u))
        self.dist = [dist[n] for n in ids]

    def __call__(self, p) -> float:
        return min((math.dist(p, n) + d for n, d in zip(self.nodes, self.dist)
                    if math.isfinite(d) and self.leg.clear(p, n)), default=math.inf)


def farthest(routes: StoryRoutes, exit_ids=None) -> Remote:
    """The story's travel figure (decision 3): Stop when any sample has no route (the reason named)."""
    r = routes.r
    cache = {}
    found = {"best": -math.inf, "at": None}

    def value(p):
        key = (round(p[0], 9), round(p[1], 9))
        if key not in cache:
            got = routes.travel(p, exit_ids)
            cache[key] = got
            if got > found["best"]:
                found.update(best=got, at=p)
        return cache[key]

    floor_bound, near, clusters = -math.inf, None, []
    for room in [x for x in routes.story.rooms.values() if x is not None]:
        cut = room.holes + room.obstructions
        floor = room.outline.difference(unary_union(cut)) if cut else room.outline
        if floor.is_empty:
            continue
        rings = [tuple(map(float, c)) for c in routes.rings_for(room)] if r > 0 else []
        centres = np.array(rings, dtype=float).reshape(-1, 2)
        walls = _walls(floor)
        arcs = _clear_arcs(floor, rings, r, walls) if rings else []
        edge = {k: [] for k in range(len(rings))}
        for k, a0, sweep in arcs:
            c = rings[k]
            n = max(1, math.ceil(r * sweep / SPACING))
            for i in range(n + 1):
                ang = a0 + sweep * i / n
                p = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
                edge[k].append((value(p), p))
        edge_best = max((v for got in edge.values() for v, _ in got), default=-math.inf)

        # the clear floor
        heap, kept = [], []

        def push(tri):
            poly = Polygon(tri)
            reached = bool(len(centres)) and bool((shapely.distance(poly, shapely.points(centres)) < r - EPS).any())
            if reached:
                if _longest(tri) > FINE:
                    for t in _split(tri):
                        push(t)
                    return
                clear = [p for p in tri if not len(centres) or np.hypot(*(centres - p).T).min() >= r - EPS]
                for p in clear:
                    value(p)
                nonlocal_near.append(tri)
                return
            values = [value(p) for p in tri]
            heapq.heappush(heap, (-(max(values) + own_h(tri)), id(tri), tri, values))

        nonlocal_near = []
        for tri in _triangles(floor, START):
            push(tri)
        while heap:
            _, _, tri, values = heapq.heappop(heap)
            if droppable(tri, values, found["best"]):
                continue
            if _longest(tri) <= FINE:
                kept.append(max(values) + own_h(tri))
                continue
            for t in _split(tri):
                push(t)
        floor_bound = max(floor_bound, max(kept, default=-math.inf))
        if nonlocal_near and math.isfinite(edge_best):
            near = max(near if near is not None else -math.inf, edge_best + NEAR)

        # the clusters
        for group in _groups(rings, r):
            disks = unary_union([Point(rings[k]).buffer(r, 64) for k in group])
            if disks.intersection(floor).area <= 1e-6:
                continue
            samples = [(v, p) for k in group for v, p in edge[k]]
            if not samples:
                c = rings[group[0]]
                raise Stop("cluster_shut", x=_show(c)[0], y=_show(c)[1])
            top_v, top_p = max(samples)
            if len(group) == 1 and _in_sight(rings[group[0]], walls, r):
                margin, how = r, "lone ring in sight of its corner"
            else:
                margin, how = _walk_margin(floor, [rings[k] for k in group], r, [p for _, p in samples]), \
                    "walk out sampled"
            clusters.append(Cluster([rings[k] for k in group], top_v, top_p, margin, how,
                                    top_v + SPACING / 2 + margin))
    parts = [("the clear floor", max(floor_bound, found["best"]))]
    if near is not None:
        parts.append(("the clear floor next to the rings", near))
    parts += [(f"the ring cluster at {_show(c.rings[0])}", c.bound) for c in clusters]
    part, figure = max(parts, key=lambda x: x[1])
    return Remote(figure, found["best"], found["at"], max(floor_bound, found["best"]), near, clusters, part,
                  len(cache))


def _walk_margin(floor, rings, r, targets) -> float:
    """The greatest walk on the floor, with no clearance, from a point inside these rings to the nearest of their
    edge samples, over the corners of 3-in triangles covering them, plus 3 in (a walk can't grow faster than you
    walk, and every point of a triangle is within 3 in of a corner by a straight line inside it)."""
    R = r / math.cos(math.pi / SIDES)
    cover = unary_union([Polygon([(c[0] + R * math.cos(2 * math.pi * i / SIDES), c[1] + R * math.sin(2 * math.pi * i
                                                                                                      / SIDES))
                                  for i in range(SIDES)]) for c in rings]).intersection(floor)
    walk = _Walk(floor, targets)
    points = {(round(p[0], 9), round(p[1], 9)): p for t in _triangles(cover, FINE) for p in t}
    worst = 0.0
    for p in points.values():
        w = walk(p)
        if not math.isfinite(w):
            raise Stop("walk_shut", x=_show(p)[0], y=_show(p)[1])
        worst = max(worst, w)
    return worst + FINE
