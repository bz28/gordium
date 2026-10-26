"""Corner lots' streets, every way an architect or the tax map draws them, against an answer key that shares no code
with the measuring (#18 review round d).

A lot is built here from 2 to 4 streets along its street side (each straight, or gently curving: pieces turning at
most 4 degrees each, 20 in all), joined by sharp corners, cut corners (1 to 3 short pieces) or rounded corners (3 to
10 short pieces, each joint 5 to 25 degrees), then closed by lines that aren't streets. The generator knows each
street's true frontage (its own pieces, end to end) and which pieces are corner pieces. The law (§325-8A col. 7): a
corner lot's width is the frontage on one street, never a corner's pieces alone nor two streets added. So:
  - every street's true frontage is a lot width reading;
  - no reading is corner pieces alone;
  - the smallest reading is never more than the shortest true frontage (the cautious reading is never lost)."""

import math
import random

import pytest

from model_measurement.measure import measure

JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"


def _walk(start, heading, pieces):
    """The points along `pieces` [(length, turn before it in degrees, left positive)] from `start`, and the heading."""
    pts, (x, y) = [], start
    for length, turn in pieces:
        heading += turn
        x, y = x + length * math.cos(math.radians(heading)), y + length * math.sin(math.radians(heading))
        pts.append((x, y))
    return pts, heading


def design(rng: random.Random):
    """(ring of points, the street edges' indexes, [true frontage of each street], [[corner piece lengths]...])."""
    nstreets = rng.choice([2, 2, 3, 4])
    turn_total = 90.0
    pieces, kinds, frontages, corners = [], [], [], []
    for s in range(nstreets):
        # (the third and fourth streets shorter than the first and second, so the lot closes without crossing itself)
        length = rng.uniform(30, 90) if s < 2 else rng.uniform(25, 0.7 * frontages[s - 2])
        if rng.random() < 0.3:                       # gently curving: up to 4 degrees a joint, 20 in all
            k = rng.randint(3, 6)
            turns = [rng.uniform(-4, 4) for _ in range(k - 1)]
            while abs(sum(turns)) > 20:
                turns = [t / 2 for t in turns]
            parts = [(length / k, 0.0)] + [(length / k, t) for t in turns]
        else:
            k = rng.randint(1, 3)                    # a straight street drawn in 1 to 3 in-line pieces
            parts = [(length / k, 0.0)] * k
        frontages.append(sum(p[0] for p in parts))
        start_turn = 0.0
        if s > 0:                                     # the corner before this street
            kind = rng.choice(["sharp", "cut", "round"])
            if kind == "sharp":
                start_turn = turn_total
            elif kind == "cut":
                m = rng.randint(1, 3)
                share = [turn_total / (m + 1)] * (m + 1)
                cut = [(rng.uniform(2, 6), share[i]) for i in range(m)]
                pieces += cut
                corners.append([c[0] for c in cut])
                start_turn = share[-1]
            else:
                m = rng.randint(3, 10)
                while True:
                    joints = [rng.uniform(5, 25) for _ in range(m + 1)]
                    joints = [j * turn_total / sum(joints) for j in joints]
                    if all(5 <= j <= 25 for j in joints):
                        break
                    m = min(10, m + 1)
                curve = [(rng.uniform(1.5, 4), joints[i]) for i in range(m)]
                pieces += curve
                corners.append([c[0] for c in curve])
                start_turn = joints[-1]
        parts[0] = (parts[0][0], start_turn)
        pieces += parts
    pts, _ = _walk((0.0, 0.0), 0.0, pieces)
    ring = [(0.0, 0.0), *pts]
    streets = list(range(len(pieces)))
    # close the lot with lines that aren't streets: back to the start, past a point beyond it on the right
    end = ring[-1]
    if nstreets == 2:
        ring.append((0.0, end[1]))
    return ring, streets, frontages, corners


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


def _corner_sums(corners):
    out = set()
    for c in corners:
        for i in range(len(c)):
            for j in range(i + 1, len(c) + 1):
                out.add(round(sum(c[i:j]), 2))
    return out


@pytest.mark.parametrize("seed", range(60))
def test_every_streets_own_frontage_is_read_and_no_corner_piece_alone(seed):
    rng = random.Random(seed)
    ring, streets, frontages, corners = design(rng)
    got = widths(ring, streets)
    assert got, (seed, ring)
    rounded = [round(v, 2) for v in got]
    for f in frontages:
        assert any(abs(v - f) <= 0.02 for v in got), (seed, f, sorted(rounded))
    assert not (_corner_sums(corners) & set(rounded)), (seed, sorted(rounded), corners)
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
