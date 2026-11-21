"""An independent check of routes/paths.py: the same routes found a second, cruder way, written here apart from
the route code (it shares none of it, not even the floor: each floor is built here from the layout's own numbers).

Each ring is replaced by a regular 64-sided polygon, once inside the circle (the polygon's corners on it) and once
outside it (its sides touching it). A route that avoids the outside polygons avoids the circle, so its length is
at least the true route's; the true route avoids the inside polygons, so the shortest route round those is at most
the true one's. Both are found by the plain visibility graph (every corner of the floor that is left, every pair
that sees each other, Dijkstra). The exact route must fall between them, and they must be within 0.01 ft of each
other, so this pins the exact figure to within that band on four layouts and twenty starting points.
"""

import heapq
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import at, column_room, l_corridor, routes, table_room  # noqa: E402

R = 12.0          # in
SIDES = 64


def ft(*pts):
    return [(x * 12.0, y * 12.0) for x, y in pts]


def brute(free: Polygon, centres, p, t, outside: bool) -> float:
    """Shortest walk from p to t (inches) in `free` round 64-gons standing in for the rings; the rings holding p or
    t are left out (they may be walked inside), and their corners are corners like any other."""
    radius = R / math.cos(math.pi / SIDES) if outside else R
    active = [c for c in centres if math.dist(c, p) >= R and math.dist(c, t) >= R]
    gons = [Polygon([(cx + radius * math.cos(2 * math.pi * k / SIDES), cy + radius * math.sin(2 * math.pi * k / SIDES))
                     for k in range(SIDES)]) for cx, cy in active]
    region = free.difference(unary_union(gons)) if gons else free
    polys = list(getattr(region, "geoms", [region]))
    nodes, walls = [p, t], []
    for poly in polys:
        for ring in [poly.exterior, *poly.interiors]:
            pts = list(ring.coords)
            nodes += pts[:-1]
            walls += [(*pts[k], *pts[k + 1]) for k in range(len(pts) - 1)]
    xy = np.array(nodes)
    w = np.array(walls)
    inside = region.buffer(1e-7)
    shapely.prepare(inside)
    m = len(xy)
    see = np.zeros((m, m), dtype=bool)

    def orient(ax, ay, bx, by, cx, cy):
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

    for i in range(m):
        a = xy[i]
        b = xy[i + 1:]
        if not len(b):
            break
        ax, ay = a
        bx, by = b[:, 0:1], b[:, 1:2]
        cx, cy, dx, dy = w[:, 0], w[:, 1], w[:, 2], w[:, 3]
        o1, o2 = orient(ax, ay, bx, by, cx, cy), orient(ax, ay, bx, by, dx, dy)
        o3, o4 = orient(cx, cy, dx, dy, ax, ay), orient(cx, cy, dx, dy, bx, by)
        tiny = 1e-9
        crosses = ((o1 * o2) < -tiny) & ((o3 * o4) < -tiny)
        ok = ~crosses.any(axis=1)
        # a line through two corners of one polygon (a chord) crosses no side: it is inside that polygon when it
        # passes nearer its centre than its sides do (the polygon's inradius)
        inner = radius * math.cos(math.pi / SIDES)
        for c in active:
            d = b - a
            s = np.clip(((np.array(c) - a) * d).sum(1) / np.maximum((d * d).sum(1), 1e-12), 0.0, 1.0)
            near = np.hypot(*(a + s[:, None] * d - np.array(c)).T)
            ok &= near >= inner - 1e-7
        for f in (0.2, 0.5, 0.8):
            s = a + f * (b - a)
            ok &= shapely.contains_xy(inside, s[:, 0], s[:, 1])
        see[i, i + 1:] = ok
    see |= see.T
    dist = np.full(m, math.inf)
    dist[0] = 0.0
    heap = [(0.0, 0)]
    while heap:
        d, v = heapq.heappop(heap)
        if d > dist[v]:
            continue
        if v == 1:
            return d
        for u in np.nonzero(see[v])[0]:
            nd = d + math.dist(xy[v], xy[u])
            if nd < dist[u]:
                dist[u] = nd
                heapq.heappush(heap, (nd, u))
    return math.inf


def half_door(x0, y0, x1, y1):
    return Polygon(ft((x0, y0), (x1, y0), (x1, y1), (x0, y1)))


LAYOUTS = {
    # test 1's corridor, its door's half in the west wall; rings: the inside corner and the two jambs
    "l_corridor": (l_corridor, lambda: unary_union([Polygon(ft((0, 0), (40, 0), (40, 30), (34, 30), (34, 6), (0, 6))),
                                                   half_door(-0.25, 1.5, 0.01, 4.5)]),
                   ft((34, 6), (0, 1.5), (0, 4.5)), (-0.25, 3),
                   [(40, 30), (37, 20), (34.5, 6.5), (10, 1), (39, 0.5)]),
    # test 2's room less its column; rings: the column's corners and the two jambs
    "column": (column_room, lambda: unary_union([Polygon(ft((0, 0), (30, 0), (30, 10), (0, 10))),
                                                half_door(-0.25, 3.5, 0.01, 6.5)]).difference(
                   Polygon(ft((13, 3), (17, 3), (17, 7), (13, 7)))),
               ft((13, 3), (17, 3), (17, 7), (13, 7), (0, 3.5), (0, 6.5)), (-0.25, 5),
               [(30, 5), (30, 0), (25, 8), (13.5, 7.5), (20, 4.2)]),
    # the table room; rings: the table's corners and the two jambs
    "table": (table_room, lambda: unary_union([Polygon(ft((0, 0), (20, 0), (20, 20), (0, 20))),
                                              half_door(8.5, 19.99, 11.5, 20.25)]).difference(
                  Polygon(ft((7, 8.5), (13, 8.5), (13, 11.5), (7, 11.5)))),
              ft((7, 8.5), (13, 8.5), (13, 11.5), (7, 11.5), (8.5, 20), (11.5, 20)), (10, 20.25),
              [(10, 0), (3, 2), (18, 5), (12, 13), (10, 8)]),
    # the note's "two exits and a column", to exit B in the north wall: from behind the column the route crosses
    # from a column corner's ring to the far side of B's jamb ring (a crossing tangent)
    "column_to_b": (lambda: column_room(north_exit=True),
                    lambda: unary_union([Polygon(ft((0, 0), (30, 0), (30, 10), (0, 10))),
                                         half_door(-0.25, 3.5, 0.01, 6.5), half_door(0.5, 9.99, 3.5, 10.25)]).difference(
                        Polygon(ft((13, 3), (17, 3), (17, 7), (13, 7)))),
                    ft((13, 3), (17, 3), (17, 7), (13, 7), (0, 3.5), (0, 6.5), (0.5, 10), (3.5, 10)), (2, 10.25),
                    [(30, 5), (30, 0), (25, 1), (16, 2), (8, 3)], ["B"]),
}


@pytest.mark.parametrize("name", sorted(LAYOUTS))
def test_the_exact_routes_fall_between_the_two_polygon_brute_forces(name):
    layout, floor, centres, door, starts, *exits = LAYOUTS[name]
    exact = routes(layout())
    free, t = floor(), (door[0] * 12.0, door[1] * 12.0)
    for x, y in starts:
        p = at(x, y)
        got = exact.route(p, *exits).length
        low, high = brute(free, centres, p, t, outside=False), brute(free, centres, p, t, outside=True)
        assert high - low < 0.01 * 12, (name, (x, y), low, high)          # the band is narrow enough to mean it
        assert low - 1e-3 <= got <= high + 1e-3, (name, (x, y), low / 12, got / 12, high / 12)
