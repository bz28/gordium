"""The route measuring's speed-ups change how it computes, never what it returns (perf/route-measuring, 2026-11-23).
Each fast way is set here against the way it replaced (the old code, copied below as it was), exactly: the same
floats to the last bit and the same yes/no, on many cases, near the edges of each test too. Then the four-unit
apartment's route measures, timed, so the slowness can't come back unnoticed."""

import math
import random
import sys
import time
from pathlib import Path

import numpy as np
import pytest
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from model_measurement.routes import common_path, remote
from model_measurement.routes.paths import EPS, _seg_dist
from model_measurement.routes.common_path import TOL, _box, _touching

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import column_room, description, door, l_corridor, rect, room, routes, table_room  # noqa: E402,E501


# --- the old code, as it was -----------------------------------------------------------------------------------------

def old_own_h(tri) -> float:
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
    for p, q in ((a, b), (b, c), (c, a)):
        mid, n = (p + q) / 2, np.array([-(q - p)[1], (q - p)[0]])
        for s, e in ((a, b), (b, c), (c, a)):
            m = np.array([e - s, -n]).T
            if abs(np.linalg.det(m)) < 1e-12:
                continue
            u, _ = np.linalg.solve(m, mid - s)
            if -1e-12 <= u <= 1 + 1e-12:
                candidates.append(s + u * (e - s))
    return max(min(np.hypot(*(x - k)) for k in corners) for x in candidates)


def old_reached(tri, centres, r) -> bool:
    return bool((shapely.distance(Polygon(tri), shapely.points(centres)) < r - EPS).any())


def old_arc_clear(leg, k, c, a0, sweep) -> bool:
    from model_measurement.routes.paths import _circle_walls
    active = leg.rings
    r, slack = leg.r, EPS / leg.r
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
    cuts = sorted(x for x in _circle_walls(leg.walls, c, r, a0) if slack < x < sweep - slack)
    marks = [0.0, *cuts, sweep]
    for x0, x1 in zip(marks, marks[1:]):
        mid = a0 + (x0 + x1) / 2
        if not leg.cover.covers(Point(c[0] + r * math.cos(mid), c[1] + r * math.sin(mid))):
            return False
    return True


def old_clear(leg, a, b) -> bool:
    if math.dist(a, b) <= EPS:
        return True
    if not leg.cover.covers(LineString([a, b])):
        return False
    return not len(leg.rings) or _seg_dist(leg.rings, a, b).min() >= leg.r - EPS


def old_touching(a, b) -> list:
    out = []
    boxes = [_box(q) for q, _ in b]
    for i, (p, _) in enumerate(a):
        bp = _box(p)
        for j, bq in enumerate(boxes):
            if bp[0] > bq[2] + TOL or bq[0] > bp[2] + TOL or bp[1] > bq[3] + TOL or bq[1] > bp[3] + TOL:
                continue
            out.append((i, j))
    return out


# --- cases -----------------------------------------------------------------------------------------------------------

def triangles(n_random=3000, n_cut=6, seed=7) -> list:
    """Random triangles of every size (slivers, near-degenerate ones among them), and squares cut as farthest()
    cuts them (longest side halved: right triangles, the circumcentre on the hypotenuse, the buffer test's edge)."""
    rng = random.Random(seed)
    out = []
    for _ in range(n_random):
        o = (rng.uniform(-2000, 2000), rng.uniform(-2000, 2000))
        s = rng.choice([1e-3, 1, 3, 24, 300])
        out.append(tuple((o[0] + rng.uniform(0, s), o[1] + rng.uniform(0, s)) for _ in range(3)))
    for _ in range(n_cut):
        x, y, w = rng.uniform(0, 900), rng.uniform(0, 900), rng.choice([24.0, 23.5, 17.25])
        stack = [((x, y), (x + w, y), (x, y + w)), ((x + w, y + w), (x, y + w), (x + w, y))]
        while stack:
            t = stack.pop()
            out.append(t)
            if remote._longest(t) > 3.0:
                stack += remote._split(t)
    out += [((0, 0), (1, 0), (2, 0)), ((0, 0), (0, 0), (1, 1)), ((0, 0), (4, 0), (2, 1)),
            ((0, 0), (3, 0), (1.5, 1.5 * math.sqrt(3))), ((0, 0), (1, 0), (0.5, 1e-13))]
    return out


def legs():
    """Each zone's leg (its graph built) of the test layouts, rings and walls and all."""
    out = []
    for layout in (l_corridor, column_room, table_room):
        got = routes(layout())
        for zone in got.story.zones:
            engine = got._engine(zone)
            engine.prepare([got.story.doors[d].centre for d in zone.doors])
            out.append(engine)
    return out


# --- the speed-ups against the old code ------------------------------------------------------------------------------

def test_own_h_is_the_old_code_to_the_last_bit():
    """The nine determinants and solves in one numpy call, and the circumcentre's buffer test skipped far from the
    edges: the same h, exactly (and the remembered one is the same again)."""
    for t in triangles():
        want = old_own_h(t)
        got = remote._own_h(tuple((float(x), float(y)) for x, y in t))
        assert got == want and type(got) is type(want), t
        assert remote.own_h(t) == want and remote.own_h(t) == want, t


def test_the_buffer_test_is_skipped_only_far_from_the_edges():
    tri = ((0.0, 0.0), (10.0, 0.0), (0.0, 10.0))
    assert remote._inside_by_far(tri, 1.0, 1.0) is True
    assert remote._inside_by_far(tri, -1.0, 1.0) is False
    assert remote._inside_by_far(tri, 5.0, 5.0) is None            # on the hypotenuse: shapely says
    assert remote._inside_by_far(tri, 5.0, 5.0 + 1e-7) is None
    assert remote._inside_by_far(((0, 0), (1, 0), (2, 0)), 0.5, 0.0) is None          # no area: shapely says
    for t in triangles(n_random=500, n_cut=2):
        g = ((t[0][0] + t[1][0] + t[2][0]) / 3, (t[0][1] + t[1][1] + t[2][1]) / 3)
        for x, y in (g, t[0], (g[0] + 1e-3, g[1] - 2.0), (t[1][0] + 1e-5, t[1][1])):
            said = remote._inside_by_far(t, x, y)
            if said is not None:
                assert said == Polygon(t).buffer(1e-9).covers(Point(x, y)), (t, x, y)


def test_the_ring_reach_test_is_the_old_one():
    """A ring centre is measured by shapely only when it may reach the triangle: the same answer, centres at
    exactly r - EPS and just either side of it among them."""
    rng = random.Random(3)
    r = 12.0
    for t in triangles(n_random=1500, n_cut=2):
        g = ((t[0][0] + t[1][0] + t[2][0]) / 3, (t[0][1] + t[1][1] + t[2][1]) / 3)
        centres = [(g[0] + rng.uniform(-60, 60), g[1] + rng.uniform(-60, 60)) for _ in range(6)]
        a, b = t[0], t[1]                                  # on a side's normal, at r - EPS and either side of it
        n = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        mid, nn = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), (-(b[1] - a[1]) / n, (b[0] - a[0]) / n)
        for off in (r - EPS, r - EPS - 1e-9, r - EPS + 1e-9, -(r - EPS)):
            centres.append((mid[0] + nn[0] * off, mid[1] + nn[1] * off))
        centres = np.array(centres)
        assert remote._reached(t, centres, shapely.points(centres), r) == old_reached(t, centres, r), t


def test_arc_clear_is_the_old_one_on_every_ring():
    """The other rings' angles and the wall crossings worked once per ring: the same yes or no for arcs from
    every angle, of every sweep, on every ring of the layouts."""
    rng = random.Random(5)
    seen = 0
    for leg in legs():
        for k in range(len(leg.rings)):
            c = (float(leg.rings[k][0]), float(leg.rings[k][1]))
            for _ in range(400):
                a0, sweep = rng.uniform(0, 2 * math.pi), rng.choice([1e-9, 0.01, 0.3, 1.5, 3.0, 2 * math.pi])
                assert leg._arc_clear(k, c, a0, sweep) == old_arc_clear(leg, k, c, a0, sweep), (k, a0, sweep)
                seen += 1
            for _, on in ((None, leg._base[1][k]),):          # the graph's own arcs, between its ring nodes
                for m, (a0, _) in enumerate(on):
                    a1 = on[(m + 1) % len(on)][0]
                    sweep = (a1 - a0) % (2 * math.pi)
                    assert leg._arc_clear(k, c, a0, sweep) == old_arc_clear(leg, k, c, a0, sweep)
    assert seen > 1000                                   # every layout ring, many arcs each


def test_the_tangents_and_clear_lines_are_the_old_ones():
    rng = random.Random(9)
    for leg in legs():
        x0, y0, x1, y1 = leg.floor.bounds
        for _ in range(60):
            p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
            ks = list(range(len(leg.rings)))
            assert leg.tangents_to(p, ks) == {k: leg._tangents(p, k, (float(leg.rings[k][0]),
                                                                       float(leg.rings[k][1]))) for k in ks}
            ends = [(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(8)] + [p, (p[0] + 1e-7, p[1])]
            assert leg.clear_from(p, ends) == [bool(old_clear(leg, p, b)) for b in ends]
            assert [bool(x) for x in leg.clear_from(p, ends)] == [bool(leg.clear(p, b)) for b in ends]


def test_the_box_pairs_are_the_old_loops_in_the_old_order():
    rng = random.Random(11)
    for _ in range(40):
        def piece():
            if rng.random() < 0.5:
                a = (rng.uniform(0, 100), rng.uniform(0, 100))
                return ("line", a, (a[0] + rng.uniform(-20, 20), a[1] + rng.uniform(-20, 20)))
            return ("arc", (rng.uniform(0, 100), rng.uniform(0, 100)), 12.0, 0.0, 1.0)
        a = [(piece(), 0.0) for _ in range(rng.randint(0, 30))]
        b = [(piece(), 0.0) for _ in range(rng.randint(0, 30))]
        b += [(("line", (a[0][0][1][0] + 2 * 12.0 + TOL, 0.0), (500.0, 0.0)), 0.0)] if a and a[0][0][0] == "arc" else []
        assert list(_touching(a, b)) == old_touching(a, b)
    old = common_path.CELLS
    try:                                                   # cut into blocks of a's pieces: the same pairs
        common_path.CELLS = 7
        assert list(_touching(a, b)) == old_touching(a, b)
    finally:
        common_path.CELLS = old


def test_rooms_at_is_each_rooms_own_covers_test():
    got = routes(column_room())
    got.rooms_at((0.0, 0.0))
    for x in np.linspace(-20, 400, 37):
        for y in np.linspace(-20, 300, 23):
            p = (float(x), float(y))
            assert got.rooms_at(p) == [r for r, g in got._grown if g.covers(Point(p))]


def test_the_reach_tests_own_distance_is_within_far_of_shapelys():
    """`_tri_dist` decides the reach test only more than FAR (1e-6 in) from its line: it is within 1e-9 in of
    shapely's distance, on every kind of triangle, centres inside, on and outside it."""
    rng = random.Random(13)
    for t in triangles(n_random=800, n_cut=1):
        g = ((t[0][0] + t[1][0] + t[2][0]) / 3, (t[0][1] + t[1][1] + t[2][1]) / 3)
        for x, y in [g, t[0], ((t[0][0] + t[1][0]) / 2, (t[0][1] + t[1][1]) / 2)] +                 [(g[0] + rng.uniform(-40, 40), g[1] + rng.uniform(-40, 40)) for _ in range(4)]:
            assert abs(remote._tri_dist(t, x, y) - Polygon(t).distance(Point(x, y))) < 1e-9, (t, x, y)


def old_ways_from(leg, p) -> list:
    """`_ways_from` as it was: each ring's tangents, then round it each way to the first node met."""
    import bisect
    _, on, _, bend_ids, _, _, _ = leg._base
    ways = [(math.dist(p, b), n) for b, n in zip(leg.bends, bend_ids) if old_clear(leg, p, b)]
    for k in range(len(leg.rings)):
        ring = on[k]
        if not ring:
            continue
        c = (float(leg.rings[k][0]), float(leg.rings[k][1]))
        angles = [a for a, _ in ring]
        for ang, _, length in leg._tangents(p, k, c):
            i = bisect.bisect_left(angles, ang)
            after, before = ring[i % len(ring)], ring[(i - 1) % len(ring)]
            for (a1, n1), a0, sweep in ((after, ang, (after[0] - ang) % (2 * math.pi)),
                                        (before, before[0], (ang - before[0]) % (2 * math.pi))):
                if old_arc_clear(leg, k, c, a0, sweep):
                    ways.append((length + leg.r * sweep, n1))
    return ways


def test_the_remembered_ways_and_lines_are_the_old_ones():
    """Each point's ways onto a zone's graph (`ring_ways`, read by travel and the common path) and its lines to
    the door centres (`clear_to`), worked once and remembered: the same as the old code works them, asked once or
    twice."""
    rng = random.Random(17)
    for leg in legs():
        x0, y0, x1, y1 = leg.floor.bounds
        targets = leg._base[0]
        for _ in range(40):
            p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
            want = old_ways_from(leg, p)
            assert leg._ways_from(p) == want
            leg._ways = None
            assert leg._ways_from(p) == want                     # from the remembered ring ways
            for t in targets:
                assert bool(leg.clear_to(p, t)) == bool(old_clear(leg, p, t)) == bool(leg.clear_to(p, t))


def test_the_story_figure_reads_the_same_common_path_length():
    """The story's figure asks each sample's common path without drawing its two routes: the same length."""
    rng, pairs = random.Random(19), 0
    from model_measurement.routes.stops import Stop
    two_exits = description([room("c", rect(0, 0, 40, 6))],                 # test 19's corridor, an exit each end
                            [door("a", (-0.25, 3), (0, 1), ("c", "outside"), exit_id="A"),
                             door("b", (40.25, 3), (0, 1), ("c", "outside"), exit_id="B")])
    for desc in (two_exits, l_corridor(), column_room(north_exit=True), table_room()):
        got = routes(desc)
        x0, y0, x1, y1 = unary_union([r.outline for r in got.story.rooms.values() if r is not None]).bounds
        for _ in range(25):
            p = (rng.uniform(x0, x1), rng.uniform(y0, y1))
            try:
                want = common_path.at_point(got, p)
            except Stop as s:
                with pytest.raises(Stop) as again:
                    common_path._at_point(got, p, drawn=False)
                assert again.value.reason == s.reason
                continue
            fast = common_path._at_point(got, p, drawn=False)
            assert (fast.length, fast.exits, fast.at) == (want.length, want.exits, want.at)
            pairs += len(want.exits) == 2
    assert pairs > 10                                    # points with two exits' routes among them


# --- the apartment, timed --------------------------------------------------------------------------------------------

def test_the_four_unit_apartments_route_measures_take_seconds_not_minutes():
    """The four-unit apartment (test_data/test_sites/new_york/ithaca_city/four_unit_apartment): its route measures
    took about 100 s of CPU before these speed-ups and take about 8 s now (Ben's Windows laptop). The bound is 30 s
    of CPU time, generous because a laptop that has just been busy runs slower (the same code measured 24 s right
    after a 15-s busy loop), and still far under the old 100 s, so a slowness that comes back is seen."""
    from rule_format.rulebook import REPO
    from model_measurement.routes import measure
    sys.path.insert(0, str(REPO / "apps/revit_addin/tools/evals"))
    import make_ny_build_data as build
    interior = build.interior_of()
    start = time.process_time()
    got = measure(interior)
    took = time.process_time() - start
    assert [s["id"] for s in got["parts"]["story"]] == ["L1", "L2"]
    assert all("egress_travel_distance" in s["measures"] for s in got["parts"]["story"])
    assert took < 30, f"{took:.1f} s of CPU"


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
