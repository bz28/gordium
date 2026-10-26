"""Corner lots' streets, every way an architect or the tax map draws them, against an answer key that shares no code
with the measuring (#18 review rounds d and e).

A lot is built here from 2 to 4 streets along its street side (each straight, or gently curving: pieces turning at
most 4 degrees each, 20 in all), joined by sharp corners, cut corners (1 to 3 short pieces) or rounded corners (3 to
10 short pieces, each joint 5 to 25 degrees), or by a short street (5 to 40 ft) between two such corners that turn 90
degrees together (a street crossing at a skew, the middle side of a hexagon: from the street lines alone, as like a
cut corner as a street). Then it is closed by lines that aren't streets. The generator knows each street's true
frontage (its own pieces, end to end) and each corner's pieces. The law (§325-8A col. 7): a corner lot's width is
the frontage on one street, never two streets added. So, the cautious way:
  - every street's true frontage is a lot width reading, the short ones too (a run that may be a short street or
    part of a corner is read both ways: never fewer readings);
  - no reading is corner pieces alone shorter than MIN_STREET (5 ft: no street is that short);
  - the smallest reading is never more than the shortest true frontage."""

import math
import random

import pytest

from model_measurement.measure import measure

JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"
MIN_STREET = 5.0


def _walk(start, heading, pieces):
    """The points along `pieces` [(length, turn before it in degrees, left positive)] from `start`, and the heading."""
    pts, (x, y) = [], start
    for length, turn in pieces:
        heading += turn
        x, y = x + length * math.cos(math.radians(heading)), y + length * math.sin(math.radians(heading))
        pts.append((x, y))
    return pts, heading


def _corner(rng, kind, turn):
    """A corner turning `turn` degrees: (its pieces [(length, turn before)], the turn before the next street)."""
    if kind == "cut":
        m = rng.randint(1, max(1, min(3, int(turn // 5) - 1)))
        share = turn / (m + 1)
        return [(rng.uniform(2, 4.9), share) for _ in range(m)], share
    if kind == "round":
        joints_n = max(2, min(11, round(turn / rng.uniform(8, 20))))
        while turn / joints_n > 25:
            joints_n += 1
        while joints_n > 2 and turn / joints_n < 5:
            joints_n -= 1
        share = turn / joints_n
        return [(rng.uniform(1.5, 4), share) for _ in range(joints_n - 1)], share
    return [], turn                                         # sharp


def design(rng: random.Random):
    """(ring of points, the street edges' indexes, [true frontage of each street], [[corner piece lengths]...]): a lot
    whose outline doesn't cross itself (drawn again until it doesn't)."""
    from shapely.geometry import Polygon
    while True:
        out = _design(rng)
        if Polygon(out[0]).is_valid:
            return out


def _design(rng: random.Random):
    nstreets = rng.choice([2, 2, 3, 4])
    pieces, frontages, corners = [], [], []
    for s in range(nstreets):
        # (the third and fourth streets shorter than the first and second, so the lot closes without crossing itself)
        length = rng.uniform(30, 90) if s < 2 else rng.uniform(25, 0.7 * frontages[s - 2] if frontages else 60)
        if rng.random() < 0.3:                       # gently curving: up to 4 degrees a joint, 20 in all
            k = rng.randint(3, 6)
            turns = [rng.uniform(-4, 4) for _ in range(k - 1)]
            while abs(sum(turns)) > 20:
                turns = [t / 2 for t in turns]
            parts = [(length / k, 0.0)] + [(length / k, t) for t in turns]
        else:
            k = rng.randint(1, 3)                    # a straight street drawn in 1 to 3 in-line pieces
            parts = [(length / k, 0.0)] * k
        start_turn = 0.0
        if s > 0:                                     # the corner before this street
            kind = rng.choice(["sharp", "cut", "round", "skew", "skew"])
            if kind == "skew":
                # a short street between two corners turning 32 to 90 degrees together, each a street's end: a
                # sharp joint of more than 15 degrees (a bend), or a cut or rounded corner of more than 30
                total = rng.uniform(32, 90)
                t1 = rng.uniform(16, total - 16)
                side = lambda t: rng.choice(["sharp", "cut", "round"]) if t > 31 else "sharp"   # noqa: E731
                p1, last = _corner(rng, side(t1), t1)
                short = rng.uniform(5.5, 40)
                pieces += p1 + [(short, last)]
                frontages.append(short)
                if p1:
                    corners.append([c[0] for c in p1])
                p2, start_turn = _corner(rng, side(total - t1), total - t1)
                pieces += p2
                if p2:
                    corners.append([c[0] for c in p2])
            else:
                p, start_turn = _corner(rng, kind, 90.0)
                pieces += p
                if p:
                    corners.append([c[0] for c in p])
        frontages.append(sum(q[0] for q in parts))
        parts[0] = (parts[0][0], start_turn)
        pieces += parts
    pts, _ = _walk((0.0, 0.0), 0.0, pieces)
    ring = [(0.0, 0.0), *pts]
    if nstreets == 2:
        ring.append((0.0, ring[-1][1]))
    return ring, list(range(len(pieces))), frontages, corners


def _site(ring):
    n = len(ring)
    edges = [[list(ring[i]), list(ring[(i + 1) % n])] for i in range(n)]
    return edges, {"units": "ft", "problems": [], "buildings": [],
                   "lot": {"id": "lot", "edges": [{"points": e, "curved": False} for e in edges]}}


def widths(ring, streets):
    edges, site = _site(ring)
    facts = {"jurisdiction": JURISDICTION, "zone": "R-1b", "use": "one_family_detached", "corner_lot": True,
             "street_line": [edges[i] for i in streets], "lot_surveyed": True, "ground_is_flat": True,
             "grade_elevation": 0}
    w = measure(site, facts)["lot_width"]
    return [r["value"] for r in w.get("readings") or ([w] if w.get("value") is not None else [])]


def _short_corner_sums(corners):
    """Every run of one corner's pieces shorter than MIN_STREET: never a street's frontage."""
    out = set()
    for c in corners:
        for i in range(len(c)):
            for j in range(i + 1, len(c) + 1):
                if sum(c[i:j]) < MIN_STREET:
                    out.add(round(sum(c[i:j]), 2))
    return out


@pytest.mark.parametrize("seed", range(80))
def test_every_streets_own_frontage_is_read_and_no_corner_piece_alone(seed):
    rng = random.Random(seed)
    ring, streets, frontages, corners = design(rng)
    got = widths(ring, streets)
    assert got, (seed, ring)
    rounded = [round(v, 2) for v in got]
    for f in frontages:
        assert any(abs(v - f) <= 0.02 for v in got), (seed, round(f, 2), sorted(rounded))
    assert not (_short_corner_sums(corners) & set(rounded)), (seed, sorted(rounded), corners)
    assert min(got) <= min(frontages) + 0.02, (seed, sorted(rounded), frontages)


def test_a_street_between_two_rounded_corners_is_read_on_its_own():
    """Round d's P1: a 33 ft street between two corners rounded in 15 degree pieces reads its own 33 ft frontage
    (before: the smallest reading was 56.57 ft, and a lot width of at least 50 said it passed under every reading)."""
    curve = [(3.0, 15.0)] * 5                       # 5 pieces, 6 joints of 15 degrees: 90 in all
    pieces = [(60.0, 0.0)] + curve + [(33.0, 15.0)] + curve + [(60.0, 15.0)]
    pts, _ = _walk((0.0, 0.0), 0.0, pieces)
    ring = [(0.0, 0.0), *pts]
    got = widths(ring, list(range(len(pieces))))
    assert any(abs(v - 33.0) <= 0.02 for v in got) and min(got) <= 33.02, sorted(got)


def test_a_short_street_at_a_skew_is_read_on_its_own():
    """Round e: a 20 ft street crossing between two 45 degree corners (as like a cut corner as a street): its own
    20 ft frontage is a reading, beside the readings with it joined to either street."""
    pieces = [(60.0, 0.0), (20.0, 45.0), (50.0, 45.0)]
    pts, _ = _walk((0.0, 0.0), 0.0, pieces)
    ring = [(0.0, 0.0), *pts, (0.0, pts[-1][1])]
    got = widths(ring, [0, 1, 2])
    assert any(abs(v - 20.0) <= 0.02 for v in got), sorted(got)
    assert any(abs(v - 80.0) <= 0.02 for v in got) and any(abs(v - 70.0) <= 0.02 for v in got), sorted(got)
