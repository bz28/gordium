"""A corner lot's streets are split only where the street lines may turn a corner (measure._street_runs), never
mid-street: one street drawn in many pieces is one street, and a corner lot's lot width is one street's frontage
(§325-8A col. 7), never two streets added together nor a piece of one.

Found by #15's corner street-pick fix (7a16aa6, PR #15 comment 6405421839): with the sample's whole streets kept,
its lot width read every split of the street lines, "9'-7" to 158'-4 3/8"" (needs review, but 158 ft is both
streets added). Expected values are the lot lines' own lengths, added by hand."""

import math

from design_checker.check import sample_site
from model_measurement.measure import measure


def _site(ring):
    n = len(ring)
    edges = [[list(ring[i]), list(ring[(i + 1) % n])] for i in range(n)]
    return edges, {"units": "ft", "problems": [], "buildings": [],
                   "lot": {"id": "lot", "edges": [{"points": e, "curved": False} for e in edges]}}


def _widths(site, facts):
    w = measure(site, facts)["lot_width"]
    return sorted(round(r["value"], 2) for r in w.get("readings") or [w])


def test_the_sample_as_a_corner_lot_reads_each_streets_own_frontage():
    """106 Ithaca Rd on the tax map, read as a corner lot: Ithaca Rd is 8 lot-line pieces (75'-10", each joint
    within 4 degrees), the side street 2 pieces (23.96 + 67.92 = 91'-10 1/2"), the corner between them 90 degrees.
    Lot width: one street's frontage or the other's, never a part of Ithaca Rd (9'-7") nor both (158 ft)."""
    s = sample_site()
    edges, site = _site(s["lot"])
    ithaca, side = list(range(8)), [13, 14]
    assert round(sum(math.dist(*edges[i]) for i in ithaca), 2) == 75.84
    assert round(sum(math.dist(*edges[i]) for i in side), 2) == 91.87
    facts = dict(s["facts"], corner_lot=True, street_line=[edges[i] for i in ithaca + side])
    facts.pop("street_ids", None)
    assert _widths(site, facts) == [75.84, 91.87]


def test_a_40_ft_corner_lot_with_its_street_drawn_in_4_pieces_reads_40_ft():
    """A 40 x 100 corner lot, its front street drawn in 4 pieces of about 10 ft (each joint turning a few degrees,
    as tax-map pieces do), the other street one 100 ft line: the lot width is the front street's whole frontage
    (40'-0 1/2") or 100'-0" (which street's frontage is the corner lot's width isn't settled), never 10, 20 or 30 ft
    (part of the front street) and never 140 ft (both)."""
    ring = [(0, 0), (10, 0.3), (20, 0), (30, 0.3), (40, 0), (40, 100), (0, 100)]
    edges, site = _site(ring)
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": edges[:5], "lot_surveyed": True,
             "ground_is_flat": True, "grade_elevation": 0}
    front = round(4 * math.hypot(10, 0.3), 2)                  # 40.02
    assert _widths(site, facts) == [front, 100.0]


def test_a_corner_rounded_into_short_pieces_may_split_at_any_of_its_joints():
    """Two streets meeting in a curve drawn as 6 pieces turning 15 degrees each (no single joint a corner, 90 in
    all): where one street ends is not clear. The lot width is never one value (needs review): either the
    measuring stops (no sure corner: "stated a corner lot, but the lines never turn one") or each joint of the
    curve is a reading, none adding the two streets together."""
    r = 12.0
    curve = [(40 + r * math.sin(math.radians(a)), r - r * math.cos(math.radians(a))) for a in range(0, 91, 15)]
    ring = [(0, 0), *curve, (40 + r, 100), (0, 100)]
    edges, site = _site(ring)
    street = edges[:len(curve) + 1]
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": street, "lot_surveyed": True,
             "ground_is_flat": True, "grade_elevation": 0}
    w = measure(site, facts)["lot_width"]
    total = sum(math.dist(*e) for e in street)
    assert w["value"] is None
    assert all(r["value"] < total - 1 for r in w.get("readings") or [])


def test_a_street_bending_between_15_and_30_degrees_is_read_both_ways():
    """A corner lot whose front street bends 20 degrees at one joint (more than a street's own 15, not a sure
    corner) before the 90 degree corner: the bend may be where the streets meet, so splitting there is a reading
    too (its frontage the first piece alone), beside the sure corner's."""
    bend = (30 + 20 * math.cos(math.radians(20)), 20 * math.sin(math.radians(20)))
    ring = [(0, 0), (30, 0), bend, (bend[0], 100), (0, 100)]
    edges, site = _site(ring)
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": edges[:3], "lot_surveyed": True,
             "ground_is_flat": True, "grade_elevation": 0}
    widths = _widths(site, facts)
    assert 30.0 in widths and 50.0 in widths, widths


def test_a_corner_rounded_into_short_pieces_beside_a_sharp_corner_may_split_inside_the_curve():
    """Street A (40 ft), a corner rounded into 6 pieces turning 14 degrees each, street B up the side, and a sharp
    90 degree corner onto a third line: the rounded run turns 84 degrees in all (6 pieces of 14, each within one
    street's 15), so where A ends is open and A's own frontage (40 ft, the split where the curve starts) must stay a
    reading (#18 review: without the rounded-run rule it was gone, hiding a 40 ft lot width)."""
    r = 12.0
    curve = [(40 + r * math.sin(math.radians(a)), r - r * math.cos(math.radians(a))) for a in range(0, 85, 14)]
    ring = [(0, 0), *curve, (52, 100), (0, 100)]
    edges, site = _site(ring)
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": edges[:len(ring) - 1],
             "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0}
    widths = _widths(site, facts)
    assert 40.0 in widths
    assert min(widths) >= 40.0, widths      # never one piece of the curve alone (#18 round c)


def test_a_lot_on_three_streets_reads_each_streets_own_frontage():
    """#18 review (coordinator round): a 60 x 45 lot with streets on its 60, 45 and 60 ft sides (edges 0, 1, 2). The
    lot width is one street's frontage: 60 or 45 ft (the middle street's own too), never 105 ft (two streets)."""
    ring = [(0, 0), (60, 0), (60, 45), (0, 45)]
    edges, site = _site(ring)
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": edges[:3], "lot_surveyed": True,
             "ground_is_flat": True, "grade_elevation": 0}
    widths = _widths(site, facts)
    assert set(widths) == {45.0, 60.0} and max(widths) <= 60.0, widths


def _box(x0, y0, x1, y1):
    """A two-story box house (the floor blocks), as the architect draws one."""
    out = []
    for k in range(2):
        z0, z1 = 10 * k, 10 * (k + 1)
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        walls = [{"points": [[*pts[i], z0], [*pts[(i + 1) % 4], z0], [*pts[(i + 1) % 4], z1], [*pts[i], z1]]}
                 for i in range(4)]
        out.append({"id": f"floor {k + 1}", "floor": 10.0, "problems": [],
                    "faces": [{"points": [[x, y, z0] for x, y in pts]}, {"points": [[x, y, z1] for x, y in pts]}, *walls]})
    return out


def test_a_gently_curving_street_in_pieces_keeps_its_side_and_rear_readings():
    """#18 round c: a corner lot whose front street is 5 pieces of 12 ft turning 8 degrees at each joint (32 in all:
    where it ends is open), then a 90 degree corner. The street is the stretch before or after a possible split,
    never a middle piece alone: the address readings stay under the cap, so the side yards are still measured, and
    no lot width reading is a middle piece alone (the first and last pieces are the streets either side of the
    curve: 8 degrees a joint, 32 in all, is a rounded corner)."""
    pts = [(0.0, 0.0)]
    for k in range(5):
        a = math.radians(8 * k)
        pts.append((pts[-1][0] + 12 * math.cos(a), pts[-1][1] + 12 * math.sin(a)))
    ring = [*pts, (pts[-1][0], 100.0), (0.0, 100.0)]
    edges, site = _site(ring)
    site["buildings"] = _box(15, 25, 40, 70)
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": edges[:6], "lot_surveyed": True,
             "ground_is_flat": True, "grade_elevation": 0}
    m = measure(site, facts)
    assert m["side_yard_smaller"].get("readings") or m["side_yard_smaller"]["value"] is not None
    assert "too many readings" not in (m["side_yard_smaller"].get("reason") or "")
    words = [r["reading"] for r in m["lot_width"].get("readings") or []]
    assert words and not any(w.endswith(f"(lot line {k})") for w in words for k in (2, 3, 4)), words


def test_a_chamfer_is_never_a_street_alone():
    """#18 round c: a corner cut off (55 ft street, a 5 x 5 chamfer, 95 ft street): the chamfer is part of either
    street, never a street of its own (7'-1" frontage): 55, 62.07, 95 or 102.07 ft."""
    ring = [(0, 0), (55, 0), (60, 5), (60, 100), (0, 100)]
    edges, site = _site(ring)
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "corner_lot": True, "street_line": edges[:3], "lot_surveyed": True,
             "ground_is_flat": True, "grade_elevation": 0}
    assert set(_widths(site, facts)) == {55.0, 62.07, 95.0, 102.07}
