"""Corner lots' streets, every way an architect or the tax map draws them, against an answer key that shares no code
with the measuring (#18 review rounds d and e).

A lot is built here from 2 to 4 streets along its street side (each straight, or gently curving: pieces turning at
most 4 degrees each), joined by sharp corners, cut corners (1 to 3 short pieces), rounded corners (3 to 10 pieces,
joints 5 to 25 degrees), corners rounded in fine pieces (joints 0.5 to 4.5 degrees) or tangent arcs (half a chord's
turn at each end), or by a short street (5 to 40 ft) between two such corners. Each corner's pieces are recorded on the
street before or after it, as the street pick records them. The generator knows each street's true frontage: its own
pieces, the corner pieces recorded on it included. The law (§325-8A col. 7): a corner lot's width is the frontage on
one street. So:
  - with every street line's street recorded (street_ids): the readings are exactly the true frontages: each one a
    reading, none other, the smallest never above the shortest;
  - without: the lot width has no value and asks for the street pick (never a guess that could pass)."""

import math
import random

import pytest
from shapely.geometry import Polygon

from model_measurement.measure import measure

JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"


def _walk(start, heading, pieces):
    pts, (x, y) = [], start
    for length, turn in pieces:
        heading += turn
        x, y = x + length * math.cos(math.radians(heading)), y + length * math.sin(math.radians(heading))
        pts.append((x, y))
    return pts, heading


def _corner(rng, kind, turn):
    """A corner turning `turn` degrees: (its pieces [(length, turn before)], the turn before the next street)."""
    if kind == "cut":
        m = rng.randint(1, 3)
        share = turn / (m + 1)
        return [(rng.uniform(2, 6), share) for _ in range(m)], share
    if kind == "round":                                   # joints 5 to 25 degrees
        n = max(2, math.ceil(turn / 25))
        n = rng.randint(n, max(n, min(11, int(turn // 5))))
        share = turn / n
        return [(rng.uniform(1.5, 4), share) for _ in range(n - 1)], share
    if kind == "fine":                                    # a corner rounded in fine pieces: 0.5 to 4.5 degrees
        n = rng.randint(math.ceil(turn / 4.5), math.ceil(turn / 4.5) + 8)
        share = turn / n
        return [(rng.uniform(0.5, 2), share) for _ in range(n - 1)], share
    if kind == "tangent":                                 # a polyline arc tangent to both streets: half-turns at ends
        n = rng.randint(4, 12)
        step = turn / n
        return [(rng.uniform(1, 3), step / 2 if i == 0 else step) for i in range(n)], step / 2
    return [], turn                                      # sharp


KINDS = ["sharp", "cut", "round", "fine", "tangent"]


def _design(rng):
    nstreets = rng.choice([2, 2, 3, 4])
    pieces, owner, frontage = [], [], []           # each piece's street, each street's true frontage
    for s in range(nstreets):
        length = rng.uniform(30, 90) if s < 2 else rng.uniform(25, max(26, 0.7 * frontage[s - 2]))
        if rng.random() < 0.3:                      # gently curving
            k = rng.randint(3, 6)
            parts = [(length / k, 0.0)] + [(length / k, rng.uniform(-4, 4)) for _ in range(k - 1)]
        else:
            k = rng.randint(1, 3)
            parts = [(length / k, 0.0)] * k
        frontage.append(0.0)
        start = 0.0
        if s > 0:
            if rng.random() < 0.25:                 # a short street between two corners turning 90 together
                t1 = rng.uniform(20, 70)
                p1, last = _corner(rng, rng.choice(KINDS), t1)
                side = rng.choice([s - 1, s])       # the first corner's pieces on the street before, or the short one
                for q in p1:
                    pieces.append(q)
                    owner.append(s - 1 if side == s - 1 else ("short", s))
                pieces.append((rng.uniform(5, 40), last))
                owner.append(("short", s))
                p2, start = _corner(rng, rng.choice(KINDS), 90 - t1)
                on = rng.choice([("short", s), s])
                for q in p2:
                    pieces.append(q)
                    owner.append(on)
            else:
                p, start = _corner(rng, rng.choice(KINDS), 90.0)
                on = rng.choice([s - 1, s])
                for q in p:
                    pieces.append(q)
                    owner.append(on)
        parts[0] = (parts[0][0], start)
        for q in parts:
            pieces.append(q)
            owner.append(s)
    pts, _ = _walk((0.0, 0.0), 0.0, pieces)
    ring = [(0.0, 0.0), *pts]
    if nstreets == 2:
        ring.append((0.0, ring[-1][1]))
    names = [f"street {o}" if isinstance(o, int) else f"short street {o[1]}" for o in owner]
    true = {}
    for (length, _), name in zip(pieces, names):
        true[name] = true.get(name, 0.0) + length
    return ring, len(pieces), names, sorted(true.values())


def design(rng):
    while True:
        out = _design(rng)
        if Polygon(out[0]).is_valid:
            return out


def _box(ring):
    """A small two-story house inside the lot (its floor blocks), or none if it doesn't fit."""
    poly = Polygon(ring)
    c = poly.representative_point()
    pts = [(c.x - 2, c.y - 2), (c.x + 2, c.y - 2), (c.x + 2, c.y + 2), (c.x - 2, c.y + 2)]
    if not poly.contains(Polygon(pts)):
        return []
    out = []
    for k in range(2):
        z0, z1 = 10 * k, 10 * (k + 1)
        walls = [{"points": [[*pts[i], z0], [*pts[(i + 1) % 4], z0], [*pts[(i + 1) % 4], z1], [*pts[i], z1]]}
                 for i in range(4)]
        out.append({"id": f"floor {k + 1}", "floor": 10.0, "problems": [],
                    "faces": [{"points": [[x, y, z0] for x, y in pts]}, {"points": [[x, y, z1] for x, y in pts]}, *walls]})
    return out


def _measure(ring, nstreet, ids, surveyed=True, house=False):
    n = len(ring)
    edges = [[list(ring[i]), list(ring[(i + 1) % n])] for i in range(n)]
    site = {"units": "ft", "problems": [], "buildings": _box(ring) if house else [],
            "lot": {"id": "lot", "edges": [{"points": e, "curved": False} for e in edges]}}
    facts = {"jurisdiction": JURISDICTION, "zone": "R-1b", "use": "one_family_detached", "corner_lot": True,
             "street_line": edges[:nstreet], "lot_surveyed": surveyed, "ground_is_flat": True, "grade_elevation": 0}
    if ids is not None:
        facts["street_ids"] = ids
    return measure(site, facts)


@pytest.mark.parametrize("seed", range(100))
def test_with_the_streets_recorded_every_true_frontage_is_a_reading_and_nothing_else(seed):
    """Surveyed: the readings are exactly the true frontages."""
    ring, nstreet, names, true = design(random.Random(seed))
    w = _measure(ring, nstreet, names)["lot_width"]
    got = sorted(r["value"] for r in w.get("readings") or ([w] if w.get("value") is not None else []))
    assert len(got) == len(true) and all(abs(a - b) <= 0.02 for a, b in zip(got, true)), (seed, got, true)


@pytest.mark.parametrize("seed", range(50))
def test_on_the_tax_map_every_true_frontage_is_still_a_reading(seed):
    """From the tax map (the outline cleaned within 0.25 ft, pieces merged): each true frontage is a reading or the
    lot width needs review, never a reading above the shortest true frontage alone."""
    ring, nstreet, names, true = design(random.Random(seed))
    w = _measure(ring, nstreet, names, surveyed=False)["lot_width"]
    got = sorted(r["value"] for r in w.get("readings") or ([w] if w.get("value") is not None else []))
    if got:
        assert all(any(abs(a - b) <= 0.3 for a in got) for b in true), (seed, got, true)
        assert min(got) <= min(true) + 0.3, (seed, got, true)
    else:
        assert w["value"] is None and w.get("reason"), (seed, w)


@pytest.mark.parametrize("seed", range(100))
def test_without_the_streets_recorded_nothing_from_the_street_lines_ever_passes(seed):
    """No street_ids: the lot width and every yard measured from the street lines wait for the street pick (the
    lines given may be one street's), with a house on the lot."""
    ring, nstreet, names, true = design(random.Random(seed))
    m = _measure(ring, nstreet, None, house=True)
    for name in ("lot_width", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "lot_depth"):
        assert m[name]["value"] is None and not m[name].get("readings"), (seed, name, m[name])
        assert "pick the street side" in m[name]["reason"], (seed, name, m[name]["reason"])
