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

- **The pockets** (clear floor shut in by rings: a route there exists only with no clearance). Their samples are
  left out of the two parts above and bounded through the clusters round them: those clusters' greatest routed
  edge sample, plus 1.5 in, plus the greatest sampled walk out of the pocket and the rings, plus 3 in.

Any other sample with no route, or a pocket or cluster with no routed clear edge round it, stops the figure (needs
review), the reason named; every edge arc is sampled at its ends at least, so a pocket shut in by rings is found from
its own arcs. Lengths in inches.
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
SHUT = "too_narrow"   # a point with a route only with no clearance: in a pocket shut in by rings


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


_H_MOST = 1 << 17     # own_h's remembered triangles (a story's farthest() calls meet the same ones again)
_H_SEEN: dict = {}


def own_h(tri) -> float:
    """The greatest distance from any point of the triangle to its nearest corner. It is reached at the circumcentre
    (when that is inside) or where a side's perpendicular bisector meets another side.

    Worked once per triangle (by its corners, exactly) and remembered: farthest() asks for a triangle's h when it is
    pushed, popped and kept, and every room's farthest() on a story cuts the same triangles."""
    key = tuple((float(p[0]), float(p[1])) for p in tri)
    got = _H_SEEN.get(key)
    if got is None:
        if len(_H_SEEN) >= _H_MOST:
            _H_SEEN.clear()
        got = _H_SEEN[key] = _own_h(key)
    return got


def _inside_by_far(tri, x, y):
    """Whether (x, y) is inside the triangle by more than 1e-6 in (True), outside it by more than 1e-6 in (False),
    or too near its edge to say (None). Each side's signed distance is worked to far better than 1e-6 in (its float
    error is about 1e-16 of the coordinates' size): a point more than 1e-6 in outside one side's line is more than
    1e-6 in from the triangle, so never in its 1e-9-in buffer; one more than 1e-6 in inside every side is in it."""
    (ax, ay), (bx, by), (cx, cy) = tri
    area2 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if not area2 or not all(map(math.isfinite, (area2, x, y))):
        return None
    sign, least = (1.0 if area2 > 0 else -1.0), math.inf
    for (px, py), (qx, qy) in (((ax, ay), (bx, by)), ((bx, by), (cx, cy)), ((cx, cy), (ax, ay))):
        n = math.hypot(qx - px, qy - py)
        if not n:
            return None
        least = min(least, sign * ((qx - px) * (y - py) - (qy - py) * (x - px)) / n)
    if least > 1e-6:
        return True
    if least < -1e-6:
        return False
    return None


def _own_h(tri) -> float:
    """own_h, worked: the same float operations as ever (the circumcentre; each perpendicular bisector against each
    side, its 2x2 determinant and solve through numpy's LAPACK, all nine in one call, which works each matrix exactly
    as one call per matrix does), so the same h to the last bit (test_routes_speed pins it on many triangles against
    the old one-at-a-time code). The circumcentre's buffer test is shapely's only near the triangle's edges."""
    a, b, c = (np.array(p, dtype=float) for p in tri)
    corners = (a, b, c)
    candidates = list(corners)
    d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
    if abs(d) > 0:
        ux = ((a @ a) * (b[1] - c[1]) + (b @ b) * (c[1] - a[1]) + (c @ c) * (a[1] - b[1])) / d
        uy = ((a @ a) * (c[0] - b[0]) + (b @ b) * (a[0] - c[0]) + (c @ c) * (b[0] - a[0])) / d
        inside = _inside_by_far(tri, float(ux), float(uy))
        if inside is None:
            inside = Polygon(tri).buffer(1e-9).covers(Point(ux, uy))
        if inside:
            candidates.append(np.array([ux, uy]))
    sides = ((a, b), (b, c), (c, a))
    m = np.empty((9, 2, 2))
    rhs = np.empty((9, 2))
    for i, (p, q) in enumerate(sides):                 # each perpendicular bisector against each side
        mid, n = (p + q) / 2, np.array([-(q - p)[1], (q - p)[0]])
        for j, (s, e) in enumerate(sides):
            m[3 * i + j] = np.array([e - s, -n]).T
            rhs[3 * i + j] = mid - s
    solvable = np.flatnonzero(~(np.abs(np.linalg.det(m)) < 1e-12))
    if len(solvable):
        us = np.linalg.solve(m[solvable], rhs[solvable][:, :, None])[:, 0, 0]
        for k, u in zip(solvable, us):
            if -1e-12 <= u <= 1 + 1e-12:
                s, e = sides[k % 3]
                candidates.append(s + u * (e - s))
    return max(min(np.hypot(*(x - k)) for k in corners) for x in candidates)


FAR = 1e-6           # in: a distance this far from the reach test's line is sure (its float error is ~1e-12 in)


def _seg_far(px, py, ax, ay, bx, by) -> float:
    """The distance from (px, py) to the segment ab, in plain floats (within ~1e-12 in of the true one)."""
    dx, dy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else min(1.0, max(0.0, (wx * dx + wy * dy) / length2))
    return math.hypot(wx - t * dx, wy - t * dy)


def _tri_dist(tri, x, y) -> float:
    """(x, y)'s distance to the closed triangle, worked here in floats: 0 inside it, else the least distance to its
    three sides. Not shapely's figure to the bit, but within ~1e-12 in of the true distance (coordinates of a few
    thousand inches), so far within FAR."""
    (ax, ay), (bx, by), (cx, cy) = tri
    s1 = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
    s2 = (cx - bx) * (y - by) - (cy - by) * (x - bx)
    s3 = (ax - cx) * (y - cy) - (ay - cy) * (x - cx)
    if (s1 > 0 and s2 > 0 and s3 > 0) or (s1 < 0 and s2 < 0 and s3 < 0):
        return 0.0
    return min(_seg_far(x, y, ax, ay, bx, by), _seg_far(x, y, bx, by, cx, cy), _seg_far(x, y, cx, cy, ax, ay))


def _reached(tri, centres, ring_points, r) -> bool:
    """Whether a ring reaches the triangle: some centre closer than r - EPS to it by shapely's distance, exactly as
    ever, with shapely asked only where its answer could differ from a sure one. A centre farther than R + r - EPS
    + FAR from the triangle's centroid (R: its farthest corner from it) is surely farther than r - EPS from the
    triangle. Each other centre's distance is worked here to within ~1e-12 in (`_tri_dist`): one more than FAR under
    r - EPS is surely under it by shapely's figure too (the triangle reached); with none, those more than FAR over
    it surely aren't, and only the centres within FAR of the line are measured by shapely (test_routes_speed sets
    this against shapely's distance on every centre)."""
    (ax, ay), (bx, by), (cx, cy) = tri
    gx, gy = (ax + bx + cx) / 3, (ay + by + cy) / 3
    big = max(math.hypot(ax - gx, ay - gy), math.hypot(bx - gx, by - gy), math.hypot(cx - gx, cy - gy))
    line = r - EPS
    near = np.flatnonzero(np.hypot(centres[:, 0] - gx, centres[:, 1] - gy) <= big + line + FAR)
    unsure = []
    for k in near:
        d = _tri_dist(tri, float(centres[k, 0]), float(centres[k, 1]))
        if d < line - FAR:
            return True
        if abs(d - line) <= FAR:
            unsure.append(k)
    if not unsure:
        return False
    return bool((shapely.distance(Polygon(tri), ring_points[unsure]) < line).any())


_REACH_MOST = 1 << 17   # triangles whose ring reach is remembered, per set of rings
_REACH: dict = {}


def _reach_memo(centres, r) -> dict:
    """The reach answers remembered for these rings (by their centres, exactly, and r): every farthest() over a
    story's rooms cuts the same triangles against the same rings."""
    key = (centres.tobytes(), r)
    got = _REACH.get(key)
    if got is None or len(got) >= _REACH_MOST:
        if len(_REACH) >= 64:
            _REACH.clear()
        got = _REACH[key] = {}
    return got


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
    """The story's travel figure (decision 3). A sample with a route only with no clearance is in a pocket, bounded
    through its clusters; Stop when any other sample has no route, or a pocket or cluster has no routed edge."""
    r = routes.r
    cache = {}
    found = {"best": -math.inf, "at": None}

    def value(p):
        """The route's length from a clear point, or None for a point shut in by rings (a route exists with no
        clearance): a pocket, bounded through the cluster that shuts it in (below)."""
        key = (round(p[0], 9), round(p[1], 9))
        if key not in cache:
            try:
                got = routes.travel(p, exit_ids)
            except Stop as s:
                if s.key != SHUT:
                    raise
                cache[key] = None
                shut.append((p, s))
                return None
            cache[key] = got
            if got > found["best"]:
                found.update(best=got, at=p)
        return cache[key]

    floor_bound, near, clusters, shut = -math.inf, None, [], []
    for room in [x for x in routes.story.rooms.values() if x is not None]:
        cut = room.holes + room.obstructions
        floor = room.outline.difference(unary_union(cut)) if cut else room.outline
        if floor.is_empty:
            continue
        rings = [tuple(map(float, c)) for c in routes.rings_for(room)] if r > 0 else []
        centres = np.array(rings, dtype=float).reshape(-1, 2)
        ring_points = shapely.points(centres) if len(centres) else None       # made once per room, not per triangle
        reach = _reach_memo(centres, r)
        walls = _walls(floor)
        arcs = _clear_arcs(floor, rings, r, walls) if rings else []
        edge = {k: [] for k in range(len(rings))}
        shut_before = len(shut)
        for k, a0, sweep in arcs:
            c = rings[k]
            n = max(1, math.ceil(r * sweep / SPACING))
            for i in range(n + 1):
                ang = a0 + sweep * i / n
                p = (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
                got = value(p)
                if got is not None:                  # an arc facing a pocket has no route: not the routed edge
                    edge[k].append((got, p))
        edge_best = max((v for got in edge.values() for v, _ in got), default=-math.inf)

        # the clear floor
        heap, kept = [], []

        def push(tri):
            reached = False
            if len(centres):
                reached = reach.get(tri)
                if reached is None:
                    reached = reach[tri] = _reached(tri, centres, ring_points, r)
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
            if any(v is None for v in values):       # in a pocket: bounded through its cluster
                return
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

        # the pockets: clear floor shut in by rings, each bounded through the clusters round it
        pockets = _pockets(floor, rings, r, [p for p, _ in shut[shut_before:]]) if len(shut) > shut_before else []
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
        for pocket, first in pockets:
            clusters.append(_pocket_bound(floor, pocket, first, rings, r, edge, _groups(rings, r)))
    if not math.isfinite(found["best"]):
        raise Stop("nothing_to_sample")
    parts = [("the clear floor", max(floor_bound, found["best"]))]
    if near is not None:
        parts.append(("the clear floor next to the rings", near))
    parts += [(f"the ring cluster at {_show(c.rings[0])}", c.bound) for c in clusters]
    part, figure = max(parts, key=lambda x: x[1])
    return Remote(figure, found["best"], found["at"], max(floor_bound, found["best"]), near, clusters, part,
                  len(cache))


def _pockets(floor, rings, r, shut_points) -> list:
    """The pockets holding these shut-in points: each a piece of the floor less the rings (the rings taken as
    polygons inside their circles, so a piece holds all of its clear floor), [(piece, a point in it)]."""
    inner = unary_union([Polygon([(c[0] + r * math.cos(2 * math.pi * i / SIDES), c[1] + r * math.sin(2 * math.pi * i
                                                                                                     / SIDES))
                                  for i in range(SIDES)]) for c in rings])
    rest = floor.difference(inner)
    pieces = [g for g in getattr(rest, "geoms", [rest]) if g.area > 0]
    out = []
    for p in shut_points:
        piece = next((g for g in pieces if g.buffer(EPS).covers(Point(p))), None)
        if piece is None:
            raise Stop("walk_shut", x=_show(p)[0], y=_show(p)[1])
        if all(q is not piece for q, _ in out):
            out.append((piece, p))
    return out


def _pocket_bound(floor, pocket, first, rings, r, edge, groups) -> Cluster:
    """A pocket's bound: the greatest route on the routed clear edge of the clusters round it, plus 1.5 in, plus the
    greatest walk on the floor with no clearance from any point of the pocket or of those clusters' rings to that
    edge (sampled over 3-in triangles, plus 3 in). An upper bound on the figure Gordium gives a pocket's points
    (the walk out, then that edge point's route: open question 10). No routed edge round it: Stop (shut in)."""
    near = [g for g in groups if any(Point(rings[k]).buffer(r + EPS, 64).intersects(pocket) for k in g)]
    samples = [(v, p) for g in near for k in g for v, p in edge[k]]
    if not samples:
        raise Stop("cluster_shut", x=_show(first)[0], y=_show(first)[1])
    top_v, top_p = max(samples)
    cover = unary_union([pocket] + [Point(rings[k]).buffer(r / math.cos(math.pi / SIDES), SIDES // 4)
                                    for g in near for k in g]).intersection(floor)
    walk = _Walk(floor, [p for _, p in samples])
    points = {(round(p[0], 9), round(p[1], 9)): p for t in _triangles(cover, FINE) for p in t}
    if not points:
        raise Stop("walk_shut", x=_show(first)[0], y=_show(first)[1])
    worst = 0.0
    for p in points.values():
        w = walk(p)
        if not math.isfinite(w):
            raise Stop("walk_shut", x=_show(p)[0], y=_show(p)[1])
        worst = max(worst, w)
    margin = worst + FINE
    return Cluster([rings[k] for g in near for k in g], top_v, top_p, margin, "pocket shut in by rings",
                   top_v + SPACING / 2 + margin)


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
    if not points:                                   # nothing sampled is never a margin of 3 in
        raise Stop("walk_shut", x=_show(rings[0])[0], y=_show(rings[0])[1])
    worst = 0.0
    for p in points.values():
        w = walk(p)
        if not math.isfinite(w):
            raise Stop("walk_shut", x=_show(p)[0], y=_show(p)[1])
        worst = max(worst, w)
    return worst + FINE
