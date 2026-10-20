"""The largest legal starting building: on 106 Ithaca Rd and on made-up lots it passes every outside (exterior)
rule of the real R-1b rulebook, it is as large as the rules allow (growing any side by 1 ft breaks a rule), and
its floor blocks are its stories."""

import math

import pytest
from shapely import affinity
from shapely.geometry import Polygon

from envelope_builder.start import largest_legal_building
from model_measurement.measure import measure
from model_measurement.project import load_facts
from model_measurement.read_3dm import read_site
from rule_format.rulebook import REPO, Context, load, outcome, rulebook_for

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
RULES = load(rulebook_for(ITHACA, "R-1b"))["rules"]
USES = {"use": Context.for_jurisdiction(ITHACA).uses}
INTERIOR = {"sleeping_rooms", "parking_spaces"}
SITE_106 = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
FACTS = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b", "use": "one_family_detached",
         "corner_lot": False, "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0}


def lot(points):
    n = len(points)
    return {"id": "lot", "edges": [{"points": [list(points[i]), list(points[(i + 1) % n])]} for i in range(n)]}


def solid(outline, z0, z1, id):
    n = len(outline)
    walls = [{"points": [[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1], [*outline[i], z1]]}
             for i in range(n)]
    return {"id": id, "faces": [{"points": [[x, y, z0] for x, y in outline]}, {"points": [[x, y, z1] for x, y in outline]},
                                *walls], "problems": []}


def floors_as_solids(start):
    """The floor blocks as GordiumStart draws them: each marked as one story."""
    return [{**solid([tuple(p) for p in f["outline"]], f["base"], f["top"], f"floor {i + 1}"), "floor": f["top"] - f["base"]}
            for i, f in enumerate(start["floors"])]


def results(site, facts):
    """Every exterior rule's result for the site as built."""
    m = measure(site, facts)
    values = {k: v["value"] for k, v in m.items()}
    exterior = [r for r in RULES if not (set(r.get("check", "") and __import__("rule_format").formula.names(r["check"])) & INTERIOR)]
    return {r["id"]: outcome(r, values, USES) for r in exterior}, m


def generated(points, facts=FACTS):
    site = {"units": "ft", "lot": lot(points), "buildings": [], "problems": []}
    start = largest_legal_building(site, facts, measure(site, facts), RULES)
    return start, {**site, "buildings": floors_as_solids(start)}


def rotate(points, degrees):
    poly = affinity.rotate(Polygon(points), degrees, origin=(0, 0))
    return [tuple(p) for p in list(poly.exterior.coords)[:-1]]


RECTANGLE = [(0, 0), (73, 0), (73, 90), (0, 90)]
JOGGED = [(0, 0), (73, 0), (73, 99.4), (10.5, 99.4), (10.5, 90.3), (0, 90.3)]   # 106 Ithaca Rd's shape, simplified


@pytest.mark.parametrize("name, points, street", [
    ("rectangle", RECTANGLE, [[0, 0], [73, 0]]),
    ("tilted 30 degrees", rotate(RECTANGLE, 30), None),
    ("wide and shallow", [(0, 0), (120, 0), (120, 70), (0, 70)], [[0, 0], [120, 0]]),
])
def test_the_starting_building_passes_every_exterior_rule(name, points, street):
    facts = {**FACTS, "street_line": [street or [list(points[0]), list(points[1])]]}
    start, site = generated(points, facts)
    assert start["floors"] and start["notes"] == [], start["notes"]
    got, m = results(site, facts)
    assert {k: v for k, v in got.items() if v not in ("pass", "not_applicable")} == {}, (name, got)
    assert m["stories"]["value"] == start["stories"] == 3                  # its floor blocks are its stories
    assert m["building_height"]["value"] == 35
    assert m["building_area"]["value"] <= 0.25 * Polygon(points).area


def test_on_a_jogged_lot_every_reading_of_the_lot_passes():
    """Which lines are side lot lines on a jogged lot is an open question, so the check says NEEDS REVIEW for the
    rear yard; the starting building is drawn so that every reading passes (never a guess either way)."""
    facts = {**FACTS, "street_line": [[[0, 0], [73, 0]]]}
    start, site = generated(JOGGED, facts)
    got, _ = results(site, facts)
    assert start["floors"] and "fail" not in got.values(), got


def test_growing_any_side_by_one_foot_breaks_a_rule():
    facts = {**FACTS, "street_line": [[[0, 0], [73, 0]]]}
    start, site = generated(RECTANGLE, facts)
    x0, y0, x1, y1 = Polygon(start["floors"][0]["outline"]).bounds
    for grown in ([x0 - 1, y0, x1, y1], [x0, y0 - 1, x1, y1], [x0, y0, x1 + 1, y1], [x0, y0, x1, y1 + 1]):
        a, b, c, d = grown
        outline = [(a, b), (c, b), (c, d), (a, d)]
        bigger = {**site, "buildings": [{**solid(outline, f["base"], f["top"], f"floor {i}"), "floor": f["top"] - f["base"]}
                                        for i, f in enumerate(start["floors"])]}
        got, _ = results(bigger, facts)
        assert "fail" in got.values(), (grown, got)


def test_106_ithaca_rd_starting_building_fits_the_architects_lot():
    facts = load_facts(SITE_106 / "model_facts.yaml")
    facts = {k: v for k, v in facts.items() if k not in ("stories", "sleeping_rooms", "parking_spaces")}
    site = {**read_site(SITE_106 / "model.3dm", facts), "buildings": []}
    start = largest_legal_building(site, facts, measure(site, facts), RULES)
    assert len(start["floors"]) == 3 and start["height"] == 35
    lot_area = Polygon([e["points"][0] for e in site["lot"]["edges"]]).area
    assert start["area"] <= 0.25 * lot_area
    assert any("not from a survey" in n or "isn't from a survey" in n for n in start["notes"])   # said, never hidden
    built = {**site, "buildings": floors_as_solids(start)}
    got, m = results(built, {**facts, "lot_surveyed": True})
    assert {k: v for k, v in got.items() if v == "fail"} == {}
    assert m["stories"]["value"] == 3
    assert m["front_yard"]["value"] == pytest.approx(25, abs=0.01)       # at the front yard line, not pushed back


def test_no_buildable_area_is_said_not_drawn():
    tiny = [(0, 0), (20, 0), (20, 20), (0, 20)]
    start, _ = generated(tiny, {**FACTS, "street_line": [[[0, 0], [20, 0]]]})
    assert start["floors"] == [] and start["notes"]


def test_limits_come_from_the_rules_not_the_code():
    """Other numbers give another building: in a copy of the rules, the front yard 30, the side yards 12, the rear
    yard minimum 30 and the height 30."""
    import envelope_builder.start as s
    changed = [{**r, "check": r["check"].replace(">= 25", ">= 30").replace("<= 35", "<= 30").replace(">= 10", ">= 12")
                .replace(", 20)", ", 30)")} if r.get("check") else r for r in RULES]
    site = {"units": "ft", "lot": lot(RECTANGLE), "buildings": [], "problems": []}
    facts = {**FACTS, "street_line": [[[0, 0], [73, 0]]]}
    start = s.largest_legal_building(site, facts, measure(site, facts), changed)
    assert start["height"] == 30
    xs = [p[0] for p in start["floors"][0]["outline"]]
    ys = [p[1] for p in start["floors"][0]["outline"]]
    assert min(ys) == pytest.approx(30, abs=0.01)
    assert min(xs) >= 12 - 0.01 and max(xs) <= 73 - 12 + 0.01 and max(xs) - min(xs) >= 73 - 24 - 1 / 12 - 0.01
    assert max(ys) <= 90 - 30 + 0.01


@pytest.mark.parametrize("bend", [0.5, -0.5, 3, -3])    # into the lot, and away from it
def test_a_street_drawn_with_a_bend_still_gets_a_full_starting_building(bend):
    """Not a sliver: as wide as the side yards allow, and as large as the coverage limit allows."""
    bent = [(0, 0), (36.5, bend), (73, 0), (73, 90), (0, 90)]
    facts = {**FACTS, "street_line": [[[0, 0], [36.5, bend]], [[36.5, bend], [73, 0]]]}
    start, site = generated(bent, facts)
    assert start["floors"], start["notes"]
    got, _ = results(site, facts)
    assert "fail" not in got.values(), got
    outline = Polygon(start["floors"][0]["outline"])
    xs = [p[0] for p in start["floors"][0]["outline"]]
    assert max(xs) - min(xs) >= 73 - 20 - 1, xs
    assert outline.area >= 0.25 * Polygon(bent).area - 60, outline.area


def test_on_a_lot_that_widens_toward_the_rear_the_building_stays_at_the_front_yard_line():
    widening = [(0, 0), (60, 0), (62, 150), (-2, 150)]
    start, _ = generated(widening, {**FACTS, "street_line": [[[0, 0], [60, 0]]]})
    assert min(p[1] for p in start["floors"][0]["outline"]) == pytest.approx(25, abs=0.01)


def _arc_lot(radius=60, rear=170, spread=35, segments=4):
    """A cul-de-sac pie lot: the street an arc of a circle, the lot widening toward the rear."""
    arc = [(radius * math.sin(math.radians(a)), -radius * math.cos(math.radians(a)) + radius)
           for a in [-30 + 60 * k / segments for k in range(segments + 1)]]
    back = [(rear * math.sin(math.radians(a)), rear * math.cos(math.radians(a))) for a in (spread, -spread)]
    return arc + back, [[list(arc[k]), list(arc[k + 1])] for k in range(segments)]


@pytest.mark.parametrize("name", ["sides at 45 degrees", "stepped", "cul-de-sac pie"])
def test_a_lot_whose_sides_lean_outward_still_gets_a_full_building_at_the_front_yard_line(name):
    """The front yard is cut with rounded corners, so the buildable area dips below the front yard line where the
    side lines lean outward; the building still sits on the front yard line, not on a corner tip."""
    if name == "cul-de-sac pie":
        points, street = _arc_lot()
    else:
        points = ([(0, 0), (60, 0), (210, 150), (-150, 150)] if name == "sides at 45 degrees" else
                  [(0, 0), (60, 0), (160, 100), (160, 200), (-100, 200), (-100, 100)])
        street = [[list(points[0]), list(points[1])]]
    facts = {**FACTS, "street_line": street}
    start, site = generated(points, facts)
    assert start["floors"], start["notes"]
    got, m = results(site, facts)
    assert "fail" not in got.values(), got
    assert start["area"] >= 0.10 * Polygon(points).area      # a real building, not a corner-tip sliver
    if name != "cul-de-sac pie":
        assert m["front_yard"]["value"] == pytest.approx(25, abs=0.01)


CANT = "Gordium can't generate a starting building on this lot shape yet"


@pytest.mark.parametrize("points, street", [
    ([(0, 0), (20, 0), (20, 40), (60, 40), (60, 140), (-40, 140), (-40, 40), (0, 40)], [[0, 0], [20, 0]]),   # flag lot
    ([(0, 0), (18, 0), (18, 30), (70, 30), (70, 130), (-50, 130), (-50, 30), (0, 30)], [[0, 0], [18, 0]]),   # 18 ft neck
    ([(0, 0), (20, 0), (20, 40), (560, 600), (-540, 600), (0, 40)], [[0, 0], [20, 0]]),     # a deep wedge
])
def test_a_flag_lot_gets_no_building_and_is_told_to_draw_one(points, street):
    """The side yards close the frontage, so no rectangle sits on the front yard line: Gordium places nothing
    (never a wrong building) and says so, and the architect draws one for Gordium to check."""
    start, _ = generated(points, {**FACTS, "street_line": [street]})
    assert start["floors"] == [] and any(n.startswith(CANT) for n in start["notes"]), start["notes"]


def test_a_building_that_would_break_a_rule_is_never_placed(monkeypatch):
    """The proof: whatever the search finds is measured and checked with the checker's rules before it is
    returned. Here the search is made to hand back a rectangle 10 ft too deep, over the coverage limit."""
    import envelope_builder.start as s
    real = s._footprint

    def too_wide(*a, **k):
        f = real(*a, **k)
        return f and (f[0], f[1], f[2], f[3] + 10)
    monkeypatch.setattr(s, "_footprint", too_wide)
    start, _ = generated(RECTANGLE, {**FACTS, "street_line": [[[0, 0], [73, 0]]]})
    assert start["floors"] == [] and start["notes"] and start["notes"][-1].startswith(CANT), start["notes"]
    assert "coverage" in start["notes"][-1]                                # says which rule it would break


def _random_lot(rng):
    """A made-up lot: 3 to 8 corners around a centre (convex or not), 30 to 250 ft across, the first edge the street."""
    while True:
        n = rng.randint(3, 8)
        angles = sorted(rng.uniform(0, 2 * math.pi) for _ in range(n))
        radii = [rng.uniform(15, 125) for _ in range(n)]
        pts = [(round(r * math.cos(a), 2), round(r * math.sin(a), 2)) for a, r in zip(angles, radii)]
        if len(set(pts)) == n and Polygon(pts).is_valid and Polygon(pts).area > 100:
            return pts


def test_on_any_lot_shape_a_generated_building_never_fails_a_rule():
    """The guarantee, over 60 random lot shapes (convex or not): a building is placed only when every rule it
    touches passes or needs review; otherwise none is, and the note says so."""
    import random
    rng = random.Random(14)
    placed = 0
    for _ in range(60):
        points = _random_lot(rng)
        facts = {**FACTS, "street_line": [[list(points[0]), list(points[1])]]}
        start, site = generated(points, facts)
        if not start["floors"]:
            assert start["notes"], points
            continue
        placed += 1
        got, _ = results(site, facts)
        empty, _ = results({**site, "buildings": []}, facts)       # what the lot itself fails, with no building
        assert not [k for k, v in got.items() if v == "fail" and empty[k] != "fail"], (points, got)
    assert placed >= 10                       # tested on real buildings, not only on refusals


@pytest.mark.parametrize("width, depth, skew", [(60, 100, 0), (73, 90, 0), (100, 150, 0), (60, 120, 8),
                                                (80, 110, -6), (120, 70, 5)])
def test_every_usual_four_sided_lot_gets_a_full_building(width, depth, skew):
    """Convex four-sided lots (the R-1b kind): always a building, on the front yard line, passing every rule."""
    points = [(0, 0), (width, 0), (width + skew, depth), (skew, depth)]
    facts = {**FACTS, "street_line": [[[0, 0], [width, 0]]]}
    start, site = generated(points, facts)
    assert start["floors"] and start["notes"] == [], start["notes"]
    got, m = results(site, facts)
    assert "fail" not in got.values(), got
    assert m["front_yard"]["value"] == pytest.approx(25, abs=0.01)


def _search_steps(monkeypatch, points, street):
    """How much searching the generator does: its inner loop's steps (each rounds one area once)."""
    import builtins

    import envelope_builder.start as s
    count = [0]

    def counting(*a):
        count[0] += 1
        return builtins.round(*a)
    monkeypatch.setattr(s, "round", counting, raising=False)
    start, _ = generated(points, {**FACTS, "street_line": [street]})
    monkeypatch.undo()
    assert start["floors"], start["notes"]
    return count[0]


@pytest.mark.parametrize("widens", [0, 1 / 40])          # straight, and widening toward the rear
def test_a_deep_lot_takes_work_in_step_with_its_depth(monkeypatch, widens):
    """Doubling a lot's depth at most about doubles the search (a search that grows with the square would be 4x).
    Counted, not timed, so it holds on any machine."""
    def lot_of(deep):
        return [(0, 0), (100, 0), (100 + deep * widens, deep), (-deep * widens, deep)]
    a = _search_steps(monkeypatch, lot_of(600), [[0, 0], [100, 0]])
    b = _search_steps(monkeypatch, lot_of(1200), [[0, 0], [100, 0]])
    assert 0 < b < 2.5 * a, (a, b)


def test_a_lot_that_breaks_a_lot_rule_itself_still_gets_its_building():
    """A 45 ft wide lot is narrower than R-1b's lot width: that's the lot's own (the check still shows it), not
    the building's, so the building is still placed, and it breaks nothing else."""
    narrow = [(0, 0), (45, 0), (45, 150), (0, 150)]
    facts = {**FACTS, "street_line": [[[0, 0], [45, 0]]]}
    start, site = generated(narrow, facts)
    assert start["floors"], start["notes"]
    got, _ = results(site, facts)
    assert [k for k, v in got.items() if v == "fail"] == ["R-1b.lot_width_one_family_detached"], got
