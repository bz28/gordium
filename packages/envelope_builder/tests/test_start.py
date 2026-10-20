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
    return [solid([tuple(p) for p in f["outline"]], f["base"], f["top"], f"floor {i + 1}")
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
        bigger = {**site, "buildings": [solid(outline, f["base"], f["top"], f"floor {i}")
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


def test_no_buildable_area_is_said_not_drawn():
    tiny = [(0, 0), (20, 0), (20, 20), (0, 20)]
    start, _ = generated(tiny, {**FACTS, "street_line": [[[0, 0], [20, 0]]]})
    assert start["floors"] == [] and start["notes"]


def test_limits_come_from_the_rules_not_the_code():
    """Another zone's numbers give another building: double every yard and halve the height in a copy of the rules."""
    import envelope_builder.start as s
    changed = [{**r, "check": r["check"].replace(">= 25", ">= 30").replace("<= 35", "<= 30")} if r.get("check") else r
               for r in RULES]
    site = {"units": "ft", "lot": lot(RECTANGLE), "buildings": [], "problems": []}
    facts = {**FACTS, "street_line": [[[0, 0], [73, 0]]]}
    start = s.largest_legal_building(site, facts, measure(site, facts), changed)
    assert start["height"] == 30
    assert min(p[1] for p in start["floors"][0]["outline"]) == pytest.approx(30, abs=0.01)
