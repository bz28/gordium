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
    (x0, _), (x1, _) = west["required_lines"][0]
    assert x0 == pytest.approx(10) and x1 == pytest.approx(10)
    front = next(y for y in r["plan"]["yards"] if "Front yard" in y["label"])
    assert all(p[1] == pytest.approx(25) for p in front["required_lines"][0])           # R-1b front: 25 ft


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
        mid = [(y["required_lines"][0][0][k] + y["required_lines"][0][1][k]) / 2 for k in (0, 1)]
        on_line = min(y["points"], key=lambda p: ring.distance(Point(p[:2])))      # the dimension's lot-line end
        got.setdefault(name, []).append(round(Point(on_line[:2]).distance(Point(mid)), 3))
    assert got == {"Front yard": [27.0], "Side yard": [12.0, 12.0], "Rear yard": [32.0]}, got


def test_a_yards_words_keep_off_the_faint_required_lines():
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    lines = src[src.index("    o.plan_lines = [line for line, _, _ in o.yard_dims]"):][:300]
    assert "[line for line, _ in o.yard_required]" in lines        # an obstacle every label keeps off (F3)


FRONT = [(0, 0), (6, 0.3), (12, 0.5), (19, 0.6), (25, 0.6), (31, 0.5), (38, 0.3), (44, 0.15), (50, 0)]


def _pieced_lot():
    """A 50 × 100 lot whose street side is drawn as 8 short pieces bowing 0.6 ft (as the tax map draws a street)."""
    from test_measure import lot
    return lot(FRONT + [(50, 100), (0, 100)]), {**FACTS, "street_line": [[list(FRONT[k]), list(FRONT[k + 1])]
                                                                         for k in range(len(FRONT) - 1)]}


def test_each_yard_dimension_is_square_to_the_lot_line_piece_it_measures_to():
    """The Rhino check of #29: on the sample's street (8 tax-map pieces) the front yard's dimension was 3.9° off
    square: its lot end was a joint between pieces. Now each ends on a piece, at 90° to it, by construction."""
    import math
    from design_checker.check import check_site
    lot_, facts = _pieced_lot()
    r = check_site({"units": "ft", "lot": lot_, "buildings": [box(12, 27, 38, 65)], "problems": []},
                   {**facts, "jurisdiction": CITY})
    ring = [tuple(e["points"][0]) for e in lot_["edges"]]
    pieces = [(ring[k], ring[(k + 1) % len(ring)]) for k in range(len(ring))]
    assert len(r["plan"]["yards"]) == 4
    for y in r["plan"]["yards"]:
        end, start = y["points"]
        on = [pc for pc in pieces if abs(math.dist(pc[0], end) + math.dist(end, pc[1]) - math.dist(*pc)) < 1e-6]
        assert on, (y["label"], end)
        (u, w) = on[0]
        dot = (start[0] - end[0]) * (w[0] - u[0]) + (start[1] - end[1]) * (w[1] - u[1])
        assert abs(dot) / (math.dist(start, end) * math.dist(u, w)) < 1e-6, y["label"]        # 90°, exactly


def test_no_two_yard_dimensions_start_at_the_same_point_each_from_the_middle_of_its_wall():
    """The Rhino check of #29: on a house parallel to its lot, every dimension started at a corner shared with the
    next yard's, and the labels piled up there. Each now starts at the middle of the wall facing its lot line."""
    from design_checker.check import check_site
    r = check_site(_plot(box(12, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})
    starts = [tuple(round(c, 6) for c in y["points"][1]) for y in r["plan"]["yards"]]
    assert sorted(starts) == sorted([(25.0, 27.0), (12.0, 46.0), (38.0, 46.0), (25.0, 65.0)]), starts
    for y in r["plan"]["yards"]:          # the measured pair is kept beside it (the label is the yard as measured)
        assert y["measured_points"] and y["label"]


def test_a_skewed_wall_starts_its_dimension_at_the_middle_of_its_nearest_part():
    from design_checker.check import dim_points
    from model_measurement.measure import Lot
    from shapely.geometry import Polygon
    site = _plot(box(12, 27, 38, 65))
    shape = Lot(site, FACTS)
    house = Polygon([(10, 30), (30, 26), (30, 60), (10, 60)])     # its front wall rises 4 ft over 20 ft
    end, start = dim_points([[30, 0], [30, 26]], "front_yard", shape, house, RECT["edges"])
    assert start[1] - 26 <= 0.1 + 1e-9 and 29 < start[0] < 30      # within 0.1 ft of the yard, off the corner
    assert end == [pytest.approx(start[0]), pytest.approx(0.0)]      # square onto the street


def test_a_limit_read_two_ways_draws_a_required_line_at_each_end_of_its_range():
    from design_checker.check import required_lines
    lines, why = required_lines([[0, 40], [6, 40]], {"limit_ft": None, "limit_span_ft": [26.0, 30.0]}, RECT["edges"])
    assert [round(line[0][0], 6) for line in lines] == [26.0, 30.0] and why is None
    lines, why = required_lines([[0, 40], [6, 40]], {"limit_ft": None}, RECT["edges"])
    assert lines == [] and why == "its limit is not a length in feet"


def test_a_dimension_is_drawn_on_a_halo_above_the_highlight():
    """The Rhino check of #29: the failing side yard's dimension ran inside the red and amber and could not be told
    apart. Each stroke now lies on a thin halo drawn first; dimensions are drawn on screen (DrawForeground), after
    the model's colours (PostDrawObjects)."""
    import ast
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_dimension")
    body = ast.get_source_segment(src, fn)
    assert "for ink, width in ((halo, 2 + 2 * logic.HALO_PX), (color, 2)):" in body       # the halo, then the line
    assert "halo = ui.halo(ui.viewport_dark())" in body and logic.HALO_PX >= 1
    overlay = src[src.index("class Overlay("):src.index("def _here(")]
    assert overlay.index("def PostDrawObjects") < overlay.index("def DrawForeground")
    assert '"draw_scene"' in overlay.split("def DrawForeground")[0] and '"draw_screen"' in overlay.split("def DrawForeground")[1]
    screen = src[src.index("def draw_screen("):src.index("def _status_rows(")]
    assert "_dimension(d, e.Viewport, line, color)" in screen     # the yards' dimensions: on screen, over the colours


def test_the_yard_labels_keep_off_each_other_the_status_box_and_the_notice():
    """Four dimensions of a plan on a 1000 × 640 view, each label placed (logic.place_label, as label_box does) with
    the status box (top right) and the "no longer complies" notice (bottom left) already taken: no two overlap,
    and none covers either box."""
    status = logic.status_box(1000, ["Gordium · ✕ 1 does not comply · 2 need review", "Draft rulebook · tax map"])
    notice = (12, 640 - 30 - 64, 860, 30)
    taken = [status, notice]
    dims = [((500, 560), (500, 470)), ((120, 320), (230, 320)), ((770, 320), (880, 320)), ((500, 170), (500, 80))]
    walls = [((230, 170), (770, 170)), ((770, 170), (770, 470)), ((770, 470), (230, 470)), ((230, 470), (230, 170))]
    placed = []
    for line in dims:
        w = logic.label_width("✕ Side yard, Southwest 7'-0 5/8\", needs 10'-0\" (approx.)", 11)
        left, top, clear = logic.place_label(line, w, 20, dims + walls, taken, view=(1000, 640))
        assert clear, line
        box = (left, top, w, 20)
        assert not any(left < a + c and a < left + w and top < b + e and b < top + 20 for a, b, c, e in taken), box
        taken.append(box)
        placed.append(box)
    assert len(placed) == 4


def test_a_gables_footprint_point_mid_wall_never_moves_the_dimension_off_the_walls_middle():
    """Review round 3, F1: a gable's footprint (its roof planes seen from above) keeps a point under the ridge in
    the middle of each gable wall; the dimension started at a quarter point. Straight runs are one wall now."""
    from design_checker.check import dim_points
    from model_measurement.measure import Lot
    from shapely.geometry import Polygon
    shape = Lot(_plot(box(12, 27, 38, 65)), FACTS)
    gable = Polygon([(12, 27), (25, 27), (38, 27), (38, 65), (25, 65), (12, 65)])
    end, start = dim_points([[38, 0], [38, 27]], "front_yard", shape, gable, RECT["edges"])
    assert start == [pytest.approx(25), pytest.approx(27)] and end == [pytest.approx(25), pytest.approx(0)]


def test_a_bend_in_the_lot_line_in_front_of_the_wall_still_gets_a_square_dimension():
    """Review round 3, F3: the street bends at (25, 1) straight in front of the wall's middle; the square foot
    misses both pieces there, so the start moves along the wall's near part until one lands square on a piece."""
    import math
    from design_checker.check import check_site
    from test_measure import lot
    street = [(0, 0), (25, 1), (50, 0)]
    lot_ = lot(street + [(50, 100), (0, 100)])
    facts = {**FACTS, "street_line": [[list(street[0]), list(street[1])], [list(street[1]), list(street[2])]]}
    r = check_site({"units": "ft", "lot": lot_, "buildings": [box(12, 27, 38, 65)], "problems": []},
                   {**facts, "jurisdiction": CITY})
    front = next(y for y in r["plan"]["yards"] if "Front yard" in y["label"])
    end, start = front["points"]
    on = [pc for pc in zip(street, street[1:])
          if abs(math.dist(pc[0], end) + math.dist(end, pc[1]) - math.dist(*pc)) < 1e-6]
    square = [abs((start[0] - end[0]) * (w[0] - u[0]) + (start[1] - end[1]) * (w[1] - u[1]))
              / (math.dist(start, end) * math.dist(u, w)) < 1e-6 for u, w in on]
    assert any(square), (end, start)                                 # square to the piece it ends on
    assert math.dist(start, end) <= 26 + 0.5                         # a little longer than the yard at most


def test_a_yard_with_no_required_line_says_why_on_its_label():
    """Review round 3, F2: the reason lived only in the data."""
    from design_checker.check import plan
    items = [{"points": [[0, 40], [6, 40]], "status": "needs_review", "mark": "?", "name": "Side yard, West",
              "proposed": "6'-0\"", "required": "—", "measure": "side_yard_smaller", "limit_ft": None}]
    (y,) = plan({"lot": RECT, "buildings": []}, {"outline": [], "holes": []}, {"items": items}, {})["yards"]
    assert y["required_lines"] == [] and y["label"].endswith(" · no required line: its limit is not a length in feet")


def test_the_drawn_start_is_never_more_than_a_quarter_inch_past_the_yard_as_measured():
    """Review round 3, F5: within 1/4" (0.02 ft) the drawing can't look like room the label doesn't give."""
    from design_checker.check import DIM_NEAR_FT
    assert DIM_NEAR_FT <= 0.021


def test_a_turned_gable_read_in_single_precision_is_still_four_walls():
    """Review round 4, F1: a model's mesh points are single precision, so a turned gable's mid-wall point sits about
    1e-6 ft off its wall; an angle test (1e-9) split the wall again. Straightness is judged in feet."""
    import math
    import struct
    from shapely.geometry import Polygon
    from design_checker.check import _wall_runs
    f32 = lambda v: struct.unpack("f", struct.pack("f", v))[0]          # noqa: E731
    a = math.radians(17)
    pts = [(12, 27), (25, 27), (38, 27), (38, 65), (25, 65), (12, 65)]
    turned = [(f32(400 + x * math.cos(a) - y * math.sin(a)), f32(300 + x * math.sin(a) + y * math.cos(a)))
              for x, y in pts]
    assert len(_wall_runs(Polygon(turned))) == 4


def test_a_zero_minimum_says_so_not_that_the_dimension_has_no_length():
    from design_checker.check import required_lines
    lines, why = required_lines([[0, 40], [6, 40]], {"limit_ft": 0.0}, RECT["edges"])
    assert lines == [] and why == "the minimum is 0 ft (on the lot line)"
