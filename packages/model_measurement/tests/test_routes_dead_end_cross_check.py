"""A brute-force cross-check of decision 6's dead ends (routes/dead_ends.py), independent of its centre lines: on
generated corridors (narrowings, widenings, jogs, T's, extra branches), every dead end Gordium gives is never
shorter than a lower bound worked here on a grid of the floor, and every closed end the generator made has a dead
end, or the corridor stops (needs review).

**The bound.** Walk out from a closed end's wall, the walked part of the floor growing with the walk (every point
within t of the wall, along the floor). The walk has a choice of two directions at the first t where the floor not
yet walked falls apart into pieces holding distinct exits, or an exit's door is reached while another exit is still
ahead: t_split. At point C (on the crossing corridor's centre line, decision 6), the cross-section through C is all
within half that corridor's width w of C, so all walked by t = D(C) + w/2, and it parts the two directions: t_split
<= D(C) + w/2 <= the dead end + w/2. So the dead end >= t_split - w/2, w here the widest corridor of the layout. The
grid's distances are real walks on cell centres (16 neighbours: never shorter than the floor's, at most 2.7 percent
longer, plus a cell either end), so t_split >= t_grid / 1.027 - 2 cells. Review round 1 (2026-11-22): a narrow leg's
centre line ran on inside a wider one's, two parallel lines made a loop, and the loop's two sides were read as two
ways: a dead end of 16 ft where this bound is 38."""

import math
import random
import sys
from collections import deque
from pathlib import Path

import heapq
import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from model_measurement.routes.dead_ends import WITHOUT, corridors
from model_measurement.routes.paths import StoryRoutes

sys.path.insert(0, str(Path(__file__).parent))
from routes_layouts import FT, description, door, room, story  # noqa: E402

H = 0.5                                     # ft: the grid's cell
SLACK = 1.027                               # a 16-neighbour walk is at most this much longer than the straight line
STEPS = [(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)
         if (dx, dy) != (0, 0) and math.gcd(abs(dx), abs(dy)) == 1]


def layout(seed):
    """A corridor 0 to 60 along x, `w` wide, exits at both ends (or the east one in the south wall); maybe widened
    or narrowed over part of it; a branch north of 1 to 3 stretches (each the same, wider, narrower or jogged), closed,
    maybe ending in a T; maybe a second, unrelated branch. Coordinates on a half-foot grid, so walls fall on the grid's
    cell edges. Returns (description, the floor, where each closed end lies [a box], the exits' openings, the widest
    width)."""
    rnd = random.Random(seed)
    w = rnd.choice([6.0, 8.0, 10.0])
    rects = [(0, 0, 60, w)]
    widest = w
    kind = rnd.choice(["plain", "widened", "narrowed"])
    if kind == "widened":
        x1 = rnd.choice([10.0, 15.0, 20.0])
        d = rnd.choice([2.0, 4.0, 5.5])
        rects.append((x1, 0, x1 + rnd.choice([20.0, 25.0]), w + d))
        widest = w + d
    elif kind == "narrowed":
        rects = [(0, 0, 40, w + 6), (40, 0, 60, w)]
        widest = w + 6
    ends = []
    x, y = rnd.choice([22.0, 26.0, 30.0]), w + (6.0 if kind == "narrowed" else 0.0)
    bw = rnd.choice([6.0, 8.0])
    if kind == "widened" and rects[1][0] < x < rects[1][2]:
        y = rects[1][3]
    for k in range(rnd.choice([1, 2, 3])):
        change = rnd.choice(["same", "wider", "narrower", "jog"]) if k else "same"
        if change == "wider":
            bw = min(bw + rnd.choice([2.0, 4.0]), 14.0)
        elif change == "narrower":
            bw = max(bw - rnd.choice([2.0, 3.0]), 4.0)
        elif change == "jog":
            x += rnd.choice([-3.0, 3.0])
        top = y + rnd.choice([6.0, 10.0, 14.0])
        rects.append((x - bw / 2, y - (0.0 if k == 0 else 0.0), x + bw / 2, top))
        widest = max(widest, bw)
        y = top
    if rnd.random() < 0.3:                              # a T at its end: two closed ends
        arm = rnd.choice([10.0, 14.0])
        rects.append((x - arm, y, x + arm, y + bw))
        ends += [box(x - arm, y, x - arm + bw, y + bw), box(x + arm - bw, y, x + arm, y + bw)]
    else:
        ends.append(box(*rects[-1]))
    if rnd.random() < 0.4:                              # an unrelated branch, south of the corridor, closed
        bx = rnd.choice([8.0, 50.0])
        rects.append((bx - 3, -rnd.choice([8.0, 12.0]), bx + 3, 0))
        ends.append(box(*rects[-1]))
    floor = unary_union([box(*r) for r in rects])
    if floor.geom_type != "Polygon":
        return None
    poly = [list(c) for c in floor.exterior.coords[:-1]]
    east = rnd.random() < 0.25
    doors = [door("a", (-0.25, w / 2), (0, 1), ("c", "outside"), exit_id="A"),
             door("b", (45, -0.25), (1, 0), ("c", "outside"), exit_id="B") if east else
             door("b", (60.25, w / 2), (0, 1), ("c", "outside"), exit_id="B")]
    exits = [LineString([(0, w / 2 - 1.5), (0, w / 2 + 1.5)]),
             LineString([(43.5, 0), (46.5, 0)]) if east else LineString([(60, w / 2 - 1.5), (60, w / 2 + 1.5)])]
    return description([room("c", poly)], doors), floor, ends, exits, widest


def bound(floor, end, exits, widest) -> float:
    """t_split from `end` (the start of a dead end: any point of its centre line will do, D(C) being measured from
    it), on the grid, turned into the lower bound (ft)."""
    x0, y0, x1, y1 = floor.bounds
    nx, ny = int(round((x1 - x0) / H)), int(round((y1 - y0) / H))
    cx = x0 + H * (np.arange(nx) + 0.5)
    cy = y0 + H * (np.arange(ny) + 0.5)
    gx, gy = np.meshgrid(cx, cy, indexing="ij")
    inside = shapely.contains_xy(floor, gx, gy)
    dist = np.full(inside.shape, np.inf)
    heap = []
    near_end = shapely.distance(shapely.points(gx, gy), end) <= H * 0.75
    for i, j in zip(*np.nonzero(inside & near_end)):
        dist[i, j] = 0.0
        heap.append((0.0, i, j))
    heapq.heapify(heap)
    while heap:
        d, i, j = heapq.heappop(heap)
        if d > dist[i, j]:
            continue
        for dx, dy in STEPS:
            a, b = i + dx, j + dy
            if not (0 <= a < nx and 0 <= b < ny and inside[a, b]):
                continue
            if abs(dx) + abs(dy) > 1 and not all(inside[i + sx, j + sy] for sx in range(min(0, dx), max(0, dx) + 1)
                                                 for sy in range(min(0, dy), max(0, dy) + 1)):
                continue                                 # every cell the step crosses is floor
            nd = d + H * math.hypot(dx, dy)
            if nd < dist[a, b]:
                dist[a, b] = nd
                heapq.heappush(heap, (nd, a, b))
    door_cells = [np.nonzero(inside & (shapely.distance(shapely.points(gx, gy), e) <= H * 0.75)) for e in exits]

    def split(t) -> bool:
        ahead = inside & (dist >= t)
        reached = [bool((dist[c] < t).any()) for c in door_cells]
        left = [bool(ahead[c].any()) for c in door_cells]
        if all(reached) or any(r and any(l for k, l in enumerate(left) if k != n) for n, r in enumerate(reached)):
            return True                                  # an exit's door reached, another still ahead (or both)
        seen, comp = {}, 0
        for n, c in enumerate(door_cells):
            for i, j in zip(*c):
                if ahead[i, j] and (i, j) not in seen:
                    comp += 1
                    todo = deque([(i, j)])
                    seen[(i, j)] = comp
                    while todo:
                        a, b = todo.popleft()
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            q = (a + dx, b + dy)
                            if 0 <= q[0] < nx and 0 <= q[1] < ny and ahead[q] and q not in seen:
                                seen[q] = comp
                                todo.append(q)
        owners = [{seen[(i, j)] for i, j in zip(*c) if (i, j) in seen} for c in door_cells]
        return len(owners) == 2 and all(owners) and not (owners[0] & owners[1])

    lo, hi = 0.0, float(np.nanmax(np.where(np.isfinite(dist), dist, 0))) + H
    if not split(hi):
        return 0.0
    for _ in range(30):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if split(mid) else (mid, hi)
    return hi / SLACK - 2 * H - widest / 2


SEEDS = range(150)


@pytest.mark.parametrize("seed", SEEDS)
def test_no_dead_end_is_shorter_than_the_brute_force_bound(seed):
    got = layout(seed)
    if got is None:
        pytest.skip("the generated rectangles don't make one floor")
    desc, floor, ends, exits, widest = got
    s = story(desc)
    c = corridors(s, {"c": "corridor"}, StoryRoutes(s))["c"]
    if c.stop is not None:
        return                                           # needs review: never a false pass
    for end in ends:
        mine = [d for d in c.dead_ends if end.buffer(1.0).covers(shapely.Point(d.start[0] / FT, d.start[1] / FT))]
        assert mine, (seed, "a closed end with no dead end", end.bounds)
    for d in c.dead_ends:
        start = shapely.Point(d.start[0] / FT, d.start[1] / FT)
        low = bound(floor, start, exits, widest)
        assert d.length[WITHOUT] / FT >= low - 1e-6, (seed, start.coords[0], d.length[WITHOUT] / FT, low)


def test_the_bound_catches_the_round_1_loop():
    """The bound on review round 1's first case is about 38 ft: the 16 ft the loop gave would fail it."""
    floor = unary_union([box(0, 0, 60, 8), box(20, 8, 32, 30), box(20, 30, 26, 46)])
    exits = [LineString([(0, 2.5), (0, 5.5)]), LineString([(60, 2.5), (60, 5.5)])]
    low = bound(floor, shapely.Point(23, 46), exits, 12.0)
    assert 16.0 < low <= 45.0                            # 45: the dead end, measured (test 24a)
