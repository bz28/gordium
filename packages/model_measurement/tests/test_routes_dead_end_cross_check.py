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
    door_cells = [c for c in door_cells if len(c[0])]
    t = _split(inside, dist, door_cells)
    return 0.0 if t is None else t / SLACK - 2 * H - widest / 2


def _split(inside, dist, door_cells):
    """The least t at which the walk has a choice (t_split), or None: the floor not yet walked (dist >= t) holds
    exits' doors in two pieces, or one exit's door is walked (dist < t) while another's is still ahead. Worked in one
    sweep, adding the floor's cells from the farthest in (the part not yet walked growing as t falls), pieces joined
    as they meet."""
    owner = {}
    for e, c in enumerate(door_cells):
        for i, j in zip(*c):
            owner.setdefault((i, j), set()).add(e)
    # an exit's door reached while another's is still ahead: from just past the nearest door cell
    reach = [float(dist[c].min()) for c in door_cells]
    far = [float(dist[c].max()) for c in door_cells]
    best = None
    for e, r in enumerate(reach):
        if math.isfinite(r) and any(far[k] > r for k in range(len(door_cells)) if k != e):
            best = r if best is None else min(best, r)
    cells = [(dist[i, j], i, j) for i, j in zip(*np.nonzero(inside & np.isfinite(dist)))]
    cells.sort(reverse=True)
    top, exits_of, present = {}, {}, set()

    def find(x):
        while top[x] != x:
            top[x] = top[top[x]]
            x = top[x]
        return x

    pieces = 0                                       # pieces of the unwalked floor holding an exit's door
    for d, i, j in cells:
        x = (i, j)
        top[x] = x
        exits_of[x] = set(owner.get(x, ()))
        if exits_of[x]:
            pieces += 1
        for q in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if q in top:
                a, b = find(x), find(q)
                if a != b:
                    if exits_of[a] and exits_of[b]:
                        pieces -= 1
                    top[a] = b
                    exits_of[b] |= exits_of[a]
        # at t = d (this cell and all farther not yet walked): a choice if two pieces hold doors of distinct exits
        if pieces >= 2:
            held = [exits_of[r] for r in {find(c) for c in owner if c in top} if exits_of[r]]
            if len(held) >= 2 and len(set().union(*held)) >= 2:
                best = d if best is None else min(best, d)
    return best


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


# --- the fuzz (review round 2): staircases, one-sided steps of every size, many branches and exits ------------------

STEP_SIZES = [0.5, 0.5, 1.0, 1.5, 2.0, 3.0]          # ft: under 12 in, and 1 to 3 ft


def fuzz_layout(seed):
    """A corridor along x, its two walls each stepping in or out at random places by a random size (one-sided); one to
    three branches north or south at random places and widths, each a staircase of one to four stretches whose two
    walls step independently (a narrowing, a widening, a jog), maybe ending in a T; two or three exits (the ends, or a
    door in the corridor's wall). Half-foot grid. Returns what `layout` does, or None (not one floor)."""
    rnd = random.Random(10_000 + seed)
    length = rnd.choice([50.0, 60.0, 70.0])
    w = rnd.choice([5.0, 6.0, 8.0, 10.0])
    rects, widest = [], w
    cuts = sorted(rnd.sample([x * 5.0 for x in range(1, int(length / 5))], rnd.choice([0, 1, 2, 3])))
    xs = [0.0] + cuts + [length]
    south, north = 0.0, w
    pieces = []
    for x0, x1 in zip(xs, xs[1:]):
        rects.append((x0, south, x1, north))
        pieces.append((x0, x1, south, north))
        widest = max(widest, north - south)
        side = rnd.choice(["south", "north"])
        d = rnd.choice(STEP_SIZES) * rnd.choice([-1, 1])
        if side == "north":
            north = max(south + 4.0, north + d)
        else:
            south = min(north - 4.0, south + d)
    branches = []
    for _ in range(rnd.choice([1, 1, 2, 3])):
        x0, x1, s0, n0 = rnd.choice(pieces)
        if x1 - x0 < 6:
            continue
        bw = rnd.choice([4.0, 5.0, 6.0, 8.0, 10.0])
        left = rnd.choice([v * 0.5 for v in range(int(x0 * 2), int((x1 - min(bw, x1 - x0)) * 2) + 1)])
        right = min(left + bw, x1)
        up = rnd.random() < 0.6
        y = n0 if up else s0
        for k in range(rnd.choice([1, 2, 3, 4])):
            if k:
                for _side in range(rnd.choice([1, 1, 2])):
                    d = rnd.choice(STEP_SIZES) * rnd.choice([-1, 1])
                    if rnd.random() < 0.5:
                        left = min(right - 3.0, left + d)
                    else:
                        right = max(left + 3.0, right + d)
            run = rnd.choice([4.0, 6.0, 8.0, 12.0])
            top = y + run if up else y - run
            rects.append((left, min(y, top), right, max(y, top)))
            widest = max(widest, right - left)
            y = top
        if rnd.random() < 0.25:
            arm, t = rnd.choice([6.0, 10.0]), right - left
            rects.append((left - arm, min(y, y + (t if up else -t)), right + arm, max(y, y + (t if up else -t))))
            widest = max(widest, t)
        branches.append(rects[-1])
    floor = unary_union([box(*r) for r in rects])
    if floor.geom_type != "Polygon" or floor.interiors:
        return None
    poly = [list(c) for c in floor.exterior.coords[:-1]]
    doors, exits = [], []
    a0, a1 = pieces[0][2], pieces[0][3]
    b0, b1 = pieces[-1][2], pieces[-1][3]
    choices = [("a", (-0.25, (a0 + a1) / 2), (0, 1), LineString([(0, (a0 + a1) / 2 - 1.5), (0, (a0 + a1) / 2 + 1.5)])),
               ("b", (length + 0.25, (b0 + b1) / 2), (0, 1),
                LineString([(length, (b0 + b1) / 2 - 1.5), (length, (b0 + b1) / 2 + 1.5)]))]
    x0, x1, s0, n0 = rnd.choice(pieces)
    if x1 - x0 >= 5:
        xm = rnd.choice([v * 0.5 for v in range(int((x0 + 2) * 2), int((x1 - 2) * 2) + 1)])
        choices.append(("m", (xm, s0 - 0.25), (1, 0), LineString([(xm - 1.5, s0), (xm + 1.5, s0)])))
    picked = rnd.sample(choices, rnd.choice([2, 2, 3])) if len(choices) == 3 else choices
    for did, centre, along, opening in picked:
        if not floor.boundary.buffer(1e-6).covers(opening) or min(a1 - a0, b1 - b0) < 3.5:
            continue
        doors.append(door(did, centre, along, ("c", "outside"), exit_id=did.upper()))
        exits.append(opening)
    if len(doors) < 2:
        return None
    return description([room("c", poly)], doors), floor, [], exits, widest


FUZZ = range(int(__import__("os").environ.get("GORDIUM_FUZZ_SEEDS", "150")))


@pytest.mark.parametrize("seed", FUZZ)
def test_the_fuzz_never_crashes_and_no_dead_end_is_shorter_than_the_bound(seed):
    got = fuzz_layout(seed)
    if got is None:
        pytest.skip("not one floor, or no two exits")
    desc, floor, _, exits, widest = got
    s = story(desc)
    if s.stops:
        pytest.skip("the story itself needs review: " + "; ".join(s.stops))
    c = corridors(s, {"c": "corridor"}, StoryRoutes(s))["c"]
    if c.stop is not None:
        assert "failed" not in c.stop, c.stop                    # an unexpected error: a crash caught, still a bug
        return
    for d in c.dead_ends:
        start = shapely.Point(d.start[0] / FT, d.start[1] / FT)
        low = bound(floor, start, exits, widest)
        assert d.length[WITHOUT] / FT >= low - 1e-6, (seed, start.coords[0], d.length[WITHOUT] / FT, low)
