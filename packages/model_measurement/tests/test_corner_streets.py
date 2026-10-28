"""A corner lot's lot width is the frontage on one street (§325-8A col. 7), and which street lot lines are which street
is recorded, never guessed: `street_ids` (one per street line, from the street pick or the lookup). Each street's own
lines are one reading; a corner's pieces count only with the street they are recorded on. Not recorded for every
street line: the lot width needs review, asking for the street pick (#18 rounds b to e: no rule of angles for where a
street ends could be made safe; a corner rounded in fine pieces read two streets as one and passed).

Found first by #15's corner street-pick fix (7a16aa6): the sample's lot width read every split of its street lines,
"9'-7" to 158'-4 3/8"". Expected values are the lot lines' own lengths, added by hand."""

import math

from design_checker.check import sample_site
from model_measurement.measure import measure

JURISDICTION = "regulations/jurisdictions/new_york/ithaca_city"


def _site(ring):
    n = len(ring)
    edges = [[list(ring[i]), list(ring[(i + 1) % n])] for i in range(n)]
    return edges, {"units": "ft", "problems": [], "buildings": [],
                   "lot": {"id": "lot", "edges": [{"points": e, "curved": False} for e in edges]}}


def _facts(edges, street, ids=None, **extra):
    f = {"jurisdiction": JURISDICTION, "zone": "R-1b", "use": "one_family_detached", "corner_lot": True,
         "street_line": [edges[i] for i in street], "lot_surveyed": True, "ground_is_flat": True,
         "grade_elevation": 0, **extra}
    if ids is not None:
        f["street_ids"] = ids
    return f


def _widths(site, facts):
    w = measure(site, facts)["lot_width"]
    return sorted(round(r["value"], 2) for r in w.get("readings") or ([w] if w.get("value") is not None else []))


def test_the_sample_as_a_corner_lot_reads_each_streets_own_frontage():
    """106 Ithaca Rd on the tax map, read as a corner lot with its streets picked: Ithaca Rd is 8 lot-line pieces
    (75'-10"), the side street 2 pieces (23.96 + 67.92 = 91'-10 1/2"). Lot width: one street's frontage or the other's,
    never a part of Ithaca Rd (9'-7") nor both (158 ft)."""
    s = sample_site()
    edges, site = _site(s["lot"])
    ithaca, side = list(range(8)), [13, 14]
    assert round(sum(math.dist(*edges[i]) for i in ithaca), 2) == 75.84
    assert round(sum(math.dist(*edges[i]) for i in side), 2) == 91.87
    facts = dict(s["facts"], corner_lot=True, street_line=[edges[i] for i in ithaca + side],
                 street_ids=["Ithaca Rd"] * 8 + ["Side St"] * 2)
    assert _widths(site, facts) == [75.84, 91.87]


def test_a_40_ft_corner_lot_with_its_street_drawn_in_4_pieces_reads_40_ft():
    """A 40 x 100 corner lot, its front street drawn in 4 pieces of about 10 ft, the other street one 100 ft line: the
    lot width is the front street's whole frontage (40'-0 1/2") or 100'-0", never part of a street or both."""
    ring = [(0, 0), (10, 0.3), (20, 0), (30, 0.3), (40, 0), (40, 100), (0, 100)]
    edges, site = _site(ring)
    front = round(4 * math.hypot(10, 0.3), 2)
    assert _widths(site, _facts(edges, range(5), ["Front St"] * 4 + ["Side St"])) == [front, 100.0]


def test_a_lot_on_three_streets_reads_each_streets_own_frontage():
    """A 60 x 45 lot with streets on its 60, 45 and 60 ft sides: 60 or 45 ft (the middle street's own too), never
    105 ft (two streets)."""
    ring = [(0, 0), (60, 0), (60, 45), (0, 45)]
    edges, site = _site(ring)
    assert set(_widths(site, _facts(edges, range(3), ["A St", "B St", "C St"]))) == {45.0, 60.0}


def test_a_corner_rounded_in_fine_pieces_is_two_streets_when_recorded_so():
    """#18 round e, P0: a corner rounded in 22 fine chords (each joint about 4 degrees, so no joint looks like a
    corner) between a 30 ft street and a 60 ft one. Recorded (the arc's chords on the side street): 30 ft (+ the arc)
    and 60 ft, so a 50 ft lot width does not pass. Before: read as one 90 ft street and passed."""
    r = 25.0
    arc = [(30 + r * math.sin(math.radians(a)), r - r * math.cos(math.radians(a))) for a in
           [90 * k / 22 for k in range(23)]]
    ring = [(0, 0), *arc, (30 + r, 60 + r), (0, 60 + r)]
    edges, site = _site(ring)
    n = 1 + 22 + 1                       # the first street, the arc's chords, the side street
    ids = ["A St"] + ["B St"] * 23
    got = _widths(site, _facts(edges, range(n), ids))
    arc_len = sum(math.dist(arc[k], arc[k + 1]) for k in range(22))
    assert got == sorted([30.0, round(arc_len + 60.0, 2)]), got


def test_without_the_streets_recorded_the_lot_width_needs_review():
    """The same lots with no street_ids: which lines are which street isn't known, so the lot width has no value and
    asks for the street pick (never a guess from where the lines turn that could pass)."""
    ring = [(0, 0), (60, 0), (60, 45), (0, 45)]
    edges, site = _site(ring)
    w = measure(site, _facts(edges, range(3)))["lot_width"]
    assert w["value"] is None and not w.get("readings") and "pick the street side" in w["reason"], w


def test_a_cut_corner_counts_with_the_street_it_is_recorded_on():
    """A corner cut off (55 ft street, a 5 x 5 cut, 95 ft street), the cut recorded on the first street: 62.07 or
    95 ft. Never the cut alone (7'-1") nor both streets."""
    ring = [(0, 0), (55, 0), (60, 5), (60, 100), (0, 100)]
    edges, site = _site(ring)
    assert _widths(site, _facts(edges, range(3), ["A St", "A St", "B St"])) == [62.07, 95.0]


def test_one_streets_lines_in_two_runs_are_not_read():
    """A street's lines recorded in two runs with another street between (a mistake in the pick): not read; the
    lot width asks for the street pick again."""
    ring = [(0, 0), (60, 0), (60, 45), (0, 45)]
    edges, site = _site(ring)
    w = measure(site, _facts(edges, range(3), ["A St", "B St", "A St"]))["lot_width"]
    assert w["value"] is None and "pick the street side" in w["reason"], w


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
    """A corner lot whose front street is 5 pieces of 12 ft turning 8 degrees at each joint, then a 90 degree corner,
    recorded as one street and a side street: the side yards are measured (the address readings are the two streets)
    and the front street's lot width is its whole 60 ft."""
    pts = [(0.0, 0.0)]
    for k in range(5):
        a = math.radians(8 * k)
        pts.append((pts[-1][0] + 12 * math.cos(a), pts[-1][1] + 12 * math.sin(a)))
    ring = [*pts, (pts[-1][0], 100.0), (0.0, 100.0)]
    edges, site = _site(ring)
    site["buildings"] = _box(15, 25, 40, 70)
    facts = _facts(edges, range(6), ["A St"] * 5 + ["B St"])
    m = measure(site, facts)
    assert m["side_yard_smaller"].get("readings") or m["side_yard_smaller"]["value"] is not None
    assert "too many readings" not in (m["side_yard_smaller"].get("reason") or "")
    assert 60.0 in _widths(site, facts)


def test_without_the_streets_recorded_no_yard_is_measured_from_the_street_lines():
    """#18 round f, P0: a corner lot with one street line picked (the other street at x = 50 not) and no street_ids:
    the lines given may all be one street's, so no yard is measured from them, the front yard too (before: 30 ft to
    the one line given complied, the house 3 ft from the street not picked). Every yard and the lot depth ask for the
    street pick."""
    ring = [(0, 0), (50, 0), (50, 100), (0, 100)]
    edges, site = _site(ring)
    site["buildings"] = _box(10, 30, 47, 70)
    m = measure(site, _facts(edges, [0]))
    for name in ("front_yard", "front_yard_eaves", "side_yard_smaller", "side_yard_larger", "rear_yard", "lot_depth",
                 "lot_width"):
        assert m[name]["value"] is None and not m[name].get("readings"), name
        assert "pick the street side" in m[name]["reason"], (name, m[name]["reason"])


def test_names_saved_for_other_lines_are_said_to_be_stale():
    """street_ids that don't match the street lines one for one (saved before the lines were picked again): set
    aside, and said so, never read."""
    ring = [(0, 0), (60, 0), (60, 45), (0, 45)]
    edges, site = _site(ring)
    w = measure(site, _facts(edges, range(3), ["A St"]))["lot_width"]
    assert w["value"] is None and "no longer match" in w["reason"], w


def test_on_the_tax_map_a_short_piece_recorded_on_its_street_stays_on_it():
    """#18 round f, P2: a 0.3 ft cut corner recorded on Oak St, on a tax-map lot: the outline cleaning (0.25 ft) would
    merge it into Elm's line; a change of recorded street is kept as a corner, so the readings are Oak's (with the
    cut) and Elm's, never "not recorded"."""
    ring = [(0, 0), (59.8, 0), (60, 0.2), (60, 100), (0, 100)]
    edges, site = _site(ring)
    facts = _facts(edges, range(3), ["Elm St", "Oak Ave", "Oak Ave"], lot_surveyed=False)   # the cut on Oak
    got = _widths(site, facts)
    assert got == sorted([59.8, round(99.8 + math.hypot(0.2, 0.2), 2)]), got


def test_an_address_street_picked_in_part_is_its_whole_street():
    """#18 independent round 1, R1: South St drawn in 2 pieces, East St 1; the address street given as South St's
    first piece only. The rest of South St was read as part of a side lot line: lot depth 135.52 ft, said as certain.
    Any of a street's recorded lines names the whole street: lot depth 120 ft, as with both pieces (the lot runs
    from y = 0 at the street's ends to y = 120). An address across two streets is no street: needs review."""
    edges, site = _site([(0, 0), (30, -8), (60, 0), (60, 120), (0, 120)])
    ids = ["South St", "South St", "East St"]
    for addr in ([edges[0]], [edges[1]], edges[:2]):
        assert measure(site, _facts(edges, range(3), ids, address_street_line=addr))["lot_depth"]["value"] == 120.0
    across = measure(site, _facts(edges, range(3), ids, address_street_line=edges[1:3]))["lot_depth"]
    assert across["value"] is None and "isn't one run of the street lot lines on one street" in across["reason"]


def test_a_street_recorded_in_two_runs_says_so_never_not_recorded():
    """#18 independent round 1, R2: ids recorded for every street line, but one street's lines not next to each
    other (A St, B St, A St): needs review, saying what is wrong, never "isn't recorded" (they are)."""
    edges, site = _site([(0, 0), (60, 0), (60, 45), (0, 45)])
    w = measure(site, _facts(edges, range(3), ["A St", "B St", "A St"]))["lot_width"]
    assert w["value"] is None and not w.get("readings")
    assert "aren't next to each other" in w["reason"] and "isn't recorded" not in w["reason"]
