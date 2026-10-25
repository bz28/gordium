"""Drawing-style dimensions (Ben, 2026-10-21): per yard a dimension from the building's nearest point to its lot line,
labelled with the measured distance and coloured by status, with the required line faint across it; a vertical
dimension for the height in the elevations. The plan's numbers (check.plan) and the screen rules (rhino_logic)."""

import sys
from pathlib import Path

import pytest

from design_checker import present
from design_checker import rhino_logic as logic

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "model_measurement" / "tests"))
from test_measure import FACTS, RECT, box, sloped_roof_box  # noqa: E402

CITY = "regulations/jurisdictions/new_york/ithaca_city"


def _plot(*buildings):
    return {"units": "ft", "lot": RECT, "buildings": list(buildings), "problems": []}


def test_the_required_line_crosses_the_dimension_at_the_limit_from_the_lot_line():
    from design_checker.check import required_line
    edges = RECT["edges"]
    assert sorted(required_line([[0, 40], [6, 40]], 10, edges)) == [[10, 34], [10, 46]]    # 10 ft in from the west line
    # the points the other way round (building first): still measured from the lot line, never from the wall
    assert sorted(required_line([[6, 40], [0, 40]], 10, edges)) == [[10, 34], [10, 46]]
    assert required_line([[0, 40], [6, 40]], None, edges) is None                  # no limit in feet: none
    assert required_line([[3, 3], [3, 3]], 10, edges) is None                      # no length: none


def test_each_measured_yard_carries_its_required_line_at_its_own_limit():
    from design_checker.check import check_site
    r = check_site(_plot(box(6, 25, 35, 65)), {**FACTS, "jurisdiction": CITY})    # west wall 6 ft: needs 10
    west = next(y for y in r["plan"]["yards"] if "Side yard, West" in y["label"])
    assert west["status"] == present.FAILS and west["label"].startswith("✕ Side yard, West 6'-0\"")
    (x0, _), (x1, _) = west["required_line"]
    assert x0 == pytest.approx(10) and x1 == pytest.approx(10)
    front = next(y for y in r["plan"]["yards"] if "Front yard" in y["label"])
    assert all(p[1] == pytest.approx(25) for p in front["required_line"])           # R-1b front: 25 ft


def test_the_items_carry_their_limit_in_feet_and_only_in_feet():
    from design_checker.check import check_site
    r = check_site(_plot(box(10, 25, 35, 65)), {**FACTS, "jurisdiction": CITY})
    items = {i["name"]: i for i in r["view"]["items"]}
    assert items["Side yard, West"]["limit_ft"] == pytest.approx(10)
    assert items["Building height"]["limit_ft"] == pytest.approx(35)
    assert items["Lot coverage"]["limit_ft"] is None                              # a percentage: no line


def test_the_height_is_dimensioned_up_from_the_grade_plane_beside_the_building():
    from design_checker.check import check_site
    r = check_site(_plot(box(10, 25, 35, 65, 0, 38)), {**FACTS, "jurisdiction": CITY, "stories": 3})
    h = r["plan"]["height"]
    assert (h["base"], h["top"], h["limit"], h["status"]) == (0, 38, 35, present.FAILS)
    assert h["at"] == [39, 21] and h["label"].startswith("✕ Building height 38'-0\", needs ")


def test_a_height_read_two_ways_is_dimensioned_to_the_larger_reading():
    from design_checker.check import height_dim
    site = _plot(sloped_roof_box(10, 25, 35, 65, 30, 40, "house"))
    item = {"measure": "building_height", "status": present.REVIEW, "mark": "?", "name": "Building height",
            "proposed": "? 35'-0\"", "limit_ft": 35}
    measured = {"building_height": {"value": None, "readings": [{"value": 35.0}, {"value": 40.0}]}}
    h = height_dim(site, {"base": 2}, {"items": [item]}, measured)
    assert (h["base"], h["top"], h["limit"]) == (2, 42, 37)
    assert height_dim(site, {"base": None}, {"items": [item]}, measured) is None   # no grade: no dimension


def test_each_end_has_an_architects_tick_at_45_degrees_to_its_line():
    import math
    for a, b in (((0, 0), (40, 0)), ((0, 0), (0, 40)), ((5, 5), (35, 25))):
        ticks = logic.dim_ticks(a, b, size=10)
        assert len(ticks) == 2
        line = math.atan2(b[1] - a[1], b[0] - a[0])
        for (x0, y0), (x1, y1), end in zip(*zip(*ticks), (a, b)):
            assert math.dist((x0, y0), (x1, y1)) == pytest.approx(10)
            assert ((x0 + x1) / 2, (y0 + y1) / 2) == pytest.approx(end)              # centred on its end
            turn = math.degrees(math.atan2(y1 - y0, x1 - x0) - line) % 180
            assert turn == pytest.approx(45)
    assert logic.dim_ticks((3, 3), (3, 3)) == []


def test_dimensions_give_way_zoomed_out_and_never_lie_flat_in_an_elevation():
    assert logic.dims_shown(True) and logic.dims_shown(True, elevation=False)
    assert not logic.dims_shown(False)                      # zoomed out to the neighbourhood: none
    assert not logic.dims_shown(True, elevation=True)       # Front / Right: the yards' lines would lie on the ground


def test_the_plugin_draws_the_dimensions_by_these_rules():
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    screen = src[src.index("def draw_screen("):src.index("def _status_rows(")]
    assert "shown = logic.dims_shown(zoomed_in, elevation)" in screen
    assert "if shown else []" in screen and screen.count("_dimension(d, e.Viewport,") == 2
    assert "if height is not None and elevation and zoomed_in:" in screen
    assert "logic.dim_ticks(" in src[src.index("def _dimension("):src.index("def draw_screen(")]


def test_a_yard_raised_by_the_height_bonus_draws_its_required_line_at_the_raised_minimum():
    """Scenario 03 (the §325-16C bonus raises every yard): each row says the raised minimum (front 27'-0", sides
    12'-0", rear 32'-0"), and the faint line sits there, never at the un-raised 25/10/30 (review round 1, F1)."""
    from shapely.geometry import LineString, Point
    from design_checker import scenarios
    from design_checker.check import check_site
    sc = scenarios.load(scenarios.FOLDER / "03_height_bonus_every_yard_increased.yaml")
    s, f, extras = scenarios.site(sc)
    r = check_site(s, f, extras=extras)
    ring = LineString([tuple(p[:2]) for e in s["lot"]["edges"] for p in e["points"]])
    got = {}
    for y in r["plan"]["yards"]:
        name = " ".join(y["label"][2:].split(" ")[:2]).rstrip(",")
        mid = [(y["required_line"][0][k] + y["required_line"][1][k]) / 2 for k in (0, 1)]
        on_line = min(y["points"], key=lambda p: ring.distance(Point(p[:2])))      # the dimension's lot-line end
        got.setdefault(name, []).append(round(Point(on_line[:2]).distance(Point(mid)), 3))
    assert got == {"Front yard": [27.0], "Side yard": [12.0, 12.0], "Rear yard": [32.0]}, got


def test_a_yards_words_keep_off_the_faint_required_lines():
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    lines = src[src.index("    o.plan_lines = [line for line, _, _ in o.yard_dims]"):][:300]
    assert "[line for line, _ in o.yard_required]" in lines        # an obstacle every label keeps off (F3)
