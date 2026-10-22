"""The envelope: its faces sit at the required yard distances (never inside a yard), its top at the height
limit, under every reading of the lot; limits that aren't a shape come back as numbers."""

import math

import pytest
from shapely.geometry import LineString, Polygon

from envelope_builder.envelope import MARGIN, envelope
from model_measurement.measure import measure

R1B = [
    {"id": "front", "check": "front_yard >= 25"},
    {"id": "sides", "check": "side_yard_smaller >= 10 and side_yard_larger >= 10"},
    {"id": "rear", "check": "rear_yard >= max(min(0.25 * lot_depth, 50), 20)"},
    {"id": "height", "check": "building_height <= 35 or building_height <= 38.5 and front_yard >= 25 + (building_height - 35)"},
    {"id": "coverage", "check": "building_area <= 0.25 * lot_area"},
    {"id": "other_use", "applies_when": 'use != "one_family_detached"', "check": "front_yard >= 40"},
    {"id": "a_flag", "kind": "flag", "check": "front_yard >= 99"},
]


def lot(points):
    n = len(points)
    return {"id": "lot", "edges": [{"points": [list(points[i]), list(points[(i + 1) % n])]} for i in range(n)]}


def box(x0, y0, x1, y1, z1=30):
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    walls = [{"points": [[*pts[i], 0], [*pts[(i + 1) % 4], 0], [*pts[(i + 1) % 4], z1], [*pts[i], z1]]} for i in range(4)]
    return {"id": "house", "faces": [{"points": [[x, y, 0] for x, y in pts]}, {"points": [[x, y, z1] for x, y in pts]},
                                     *walls], "problems": []}


FACTS = {"street_line": [[[0, 0], [73, 0]]], "corner_lot": False, "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0, "use": "one_family_detached"}


def build(points, facts=FACTS, house=None):
    site = {"lot": lot(points), "buildings": [house or box(10, 30, 63, 65)], "problems": []}
    return envelope(site, facts, measure(site, facts), R1B), site


def test_a_rectangle_gives_the_yards_and_the_height_limit():
    env, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)])
    assert env["yards"] == {"front": 25, "side": 10, "rear": 22.5} and env["height"] == 35 and env["top"] == 35
    shape = Polygon(env["outline"])
    x0, y0, x1, y1 = shape.bounds
    assert (x0, y0, x1, y1) == pytest.approx((10 + MARGIN, 25 + MARGIN, 63 - MARGIN, 67.5 - MARGIN), abs=1e-9)
    assert env["coverage"] == {"allowed": 1642.5, "have": 1855.0, "over": 212.5}
    assert not env["notes"]


def test_no_point_of_the_envelope_is_inside_a_required_yard():
    points = [(0, 0), (73, 0), (73, 90), (8, 90), (0, 99)]     # a jog at the back
    env, site = build(points, house=box(10, 30, 63, 60))
    shape = Polygon(env["outline"])
    front = LineString(points[:2])
    assert front.distance(shape) >= 25
    for side in (LineString(points[1:3]), LineString([points[4], points[0]])):
        assert side.distance(shape) >= 10
    # the rear requirement under every reading of the jog: 25% of the lot depth with the jog as a rear line
    # ((99 + 90) / 2 = 94.5) or as part of a side line ((99 + 12.04 + 90) / 2 = 100.52): the larger wins
    assert env["yards"]["rear"] == pytest.approx(0.25 * (99 + math.hypot(8, 9) + 90) / 2)
    assert LineString(points[2:4]).distance(shape) >= env["yards"]["rear"]
    assert LineString(points[3:5]).distance(shape) >= env["yards"]["side"]


def test_rounded_corners_never_cut_into_a_yard():
    # a lot with an inside corner: the envelope rounds around it, at least the yard away everywhere
    points = [(0, 0), (80, 0), (80, 50), (40, 50), (40, 100), (0, 100)]
    env, _ = build(points, {**FACTS, "street_line": [[[0, 0], [80, 0]]]}, box(5, 30, 30, 60))
    shape = Polygon(env["outline"])
    corner = LineString([(80, 50), (40, 50), (40, 100)])
    assert corner.distance(shape) >= 10                     # each of these lines is a side or rear line


def test_a_rule_that_doesnt_apply_or_a_flag_adds_nothing():
    env, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)])
    assert env["yards"]["front"] == 25                       # not 40 (other uses) or 99 (a flag)


def test_a_limit_that_cant_be_worked_out_draws_nothing_and_says_why():
    site = {"lot": lot([(0, 0), (73, 0), (73, 90), (0, 90)]), "buildings": [box(10, 30, 63, 65)], "problems": []}
    facts = {**FACTS, "street_line": None}                   # no street: no lot depth, no rear yard limit
    env = envelope(site, facts, measure(site, facts), R1B)
    assert env["outline"] is None
    assert any("rear" in n and "can't be worked out" in n for n in env["notes"])


def test_no_envelope_until_the_corner_lot_question_is_answered_or_on_a_corner_lot():
    for corner, words in ((None, "corner lot first"), (True, "no envelope drawn")):
        env, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)], {**FACTS, "corner_lot": corner})
        assert env["outline"] is None and any(words in n for n in env["notes"])


def test_the_envelope_depends_on_the_lot_not_the_design():
    a, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)], house=box(10, 30, 63, 65, 30))
    b, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)], house=box(20, 40, 50, 60, 37))
    assert a["outline"] == b["outline"] and a["top"] == b["top"] == 35


def test_a_yard_limit_written_another_way_is_read_or_stops_the_envelope():
    lot_ = [(0, 0), (73, 0), (73, 90), (0, 90)]
    site = {"lot": lot(lot_), "buildings": [box(10, 30, 63, 65)], "problems": []}
    m = measure(site, FACTS)
    turned = envelope(site, FACTS, m, [{"id": "f", "check": "25 <= front_yard"}])
    assert turned["yards"]["front"] == 25 and turned["outline"] is not None
    for check in ("side_yard_smaller + side_yard_larger >= 30", "side_yard_smaller >= max(10, 0.5 * building_height)"):
        env = envelope(site, FACTS, m, [{"id": "x", "check": check}])
        assert env["outline"] is None and any("can't read" in n for n in env["notes"]), check


def test_without_a_grade_the_buildable_area_is_drawn_but_never_a_height_plane():
    level, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)], FACTS)
    for flat, grade in ((False, 0.0), (None, 0.0), (True, None)):
        env, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)], {**FACTS, "ground_is_flat": flat, "grade_elevation": grade})
        assert env["outline"] == level["outline"]           # the yards don't depend on the grade
        assert env["top"] is None and env["base"] is None and any("grade isn't set" in n for n in env["notes"])


def test_no_coverage_numbers_from_a_lot_that_isnt_surveyed():
    env, _ = build([(0, 0), (73, 0), (73, 90), (0, 90)], {**FACTS, "lot_surveyed": False})
    assert env["coverage"] is None and env["outline"] is not None
