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
    assert "if shown else []" in screen and screen.count("_dimension(d, e.Viewport,") == 1    # yards: plan; height: draw_scene
    assert 'height = getattr(o, "height_dim", None) if elevation and zoomed_in else None' in screen
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
    assert "_dimension(d, e.Viewport, best, color)" in screen     # the yards' dimensions: on screen, over the colours


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


def test_a_short_yards_dimension_is_never_drawn_more_than_a_quarter_inch_longer_than_its_label():
    """Review round 3, F5, and the independent round 5: exercised, not the constant. A yard that fails or needs
    review is dimensioned where it is shortest: every position offered is within DIM_NEAR_FT (1/4") of the yard as
    measured. Only at a bend in the lot line right in front of the wall, where no position that short lands square,
    is it up to BEND_SLACK_FT (6") longer (the label is the yard as measured, its closest point)."""
    import math
    from shapely.geometry import Polygon
    from design_checker.check import BEND_SLACK_FT, DIM_NEAR_FT, dim_candidates
    from model_measurement.measure import Lot
    shape = Lot(_plot(box(12, 27, 38, 65)), FACTS)
    skewed = Polygon([(10, 30), (30, 26), (30, 60), (10, 60)])          # nearest the street at its right end, 26 ft
    found = dim_candidates([[30, 0], [30, 26]], "front_yard", shape, skewed, RECT["edges"], worst=True)
    assert found and all(math.dist(*c) <= 26 + DIM_NEAR_FT + 1e-6 for c in found)
    roomy = dim_candidates([[30, 0], [30, 26]], "front_yard", shape, skewed, RECT["edges"], worst=False)
    assert all(math.dist(*c) <= 26 + BEND_SLACK_FT + 1e-6 for c in roomy) and len(roomy) > len(found) >= 1
    assert DIM_NEAR_FT <= 0.021 and BEND_SLACK_FT <= 0.5


def test_a_curved_wall_in_many_short_pieces_starts_its_dimension_on_the_wall():
    """Independent review of #29, round 5: straightness judged point by point made a 100-piece curved wall one
    chord, and the dimension started 1 ft in front of the wall. Runs now stay within STRAIGHT_FT of their chord."""
    from shapely.geometry import Point, Polygon
    from design_checker.check import dim_points
    from model_measurement.measure import Lot
    arc = [(12 + 26 * k / 100, 27 + 1 - ((26 * k / 100 - 13) / 13) ** 2) for k in range(101)]
    house = Polygon(arc + [(38, 65), (12, 65)])                          # sags back to y 28 at its middle
    end, start = dim_points([[12, 0], [12, 27]], "front_yard", Lot(_plot(box(12, 27, 38, 65)), FACTS), house,
                            RECT["edges"])
    assert house.exterior.distance(Point(start)) < 1e-6


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


# ---- the Rhino check of #29 at 6f9e3d1: labels on their line, in a clear spot, never inside the house --------------

def _screen(points, scale, origin=(500, 320), centre=(25, 46)):
    """Plan feet to screen pixels (y down), `scale` px per ft, the plan's `centre` at `origin`."""
    return [(origin[0] + (x - centre[0]) * scale, origin[1] - (y - centre[1]) * scale) for x, y in points]


def test_complying_dimensions_are_neutral_grey_never_green_and_the_legend_says_so():
    for dark in (False, True):
        r, g, b = logic.dim_rgb("complies", dark)
        assert max(r, g, b) - min(r, g, b) <= 10                 # grey: no hue
        rr, rg, rb = logic.dim_rgb("does_not_comply", dark)
        ar, ag, ab = logic.dim_rgb("needs_review", dark)
        assert rr > rg + 50 and rr > rb + 50 and ar > ab + 60 and ag > ab
    text = logic.legend_text()
    assert "complying ones neutral grey" in text and "green" not in text.lower()


def test_a_house_turned_against_its_lot_is_dimensioned_at_its_shortest_point_never_longer():
    """Review round 6, F1: a 40 ft wall turned 10° to the street is shortest at its corner; the corner was skipped
    and the first position offered was about 6" longer than the label. A short yard's every position is within
    1/4" of the yard as measured, the shortest first."""
    import math
    from shapely.geometry import Point, Polygon
    from design_checker.check import DIM_NEAR_FT, dim_candidates
    from model_measurement.measure import Lot
    t = math.radians(10)
    corner = (5.0, 20.0)
    house = Polygon([corner, (corner[0] + 40 * math.cos(t), corner[1] + 40 * math.sin(t)),
                     (corner[0] + 40 * math.cos(t) - 20 * math.sin(t), corner[1] + 40 * math.sin(t) + 20 * math.cos(t)),
                     (corner[0] - 20 * math.sin(t), corner[1] + 20 * math.cos(t))])
    measured = min(house.exterior.distance(Point(x, 0)) for x in range(0, 51))
    found = dim_candidates([[5, 0], list(corner)], "front_yard", Lot(_plot(box(12, 27, 38, 65)), FACTS), house,
                           RECT["edges"], worst=True)
    assert found and all(math.dist(*c) <= 20 + DIM_NEAR_FT + 1e-6 for c in found), [math.dist(*c) for c in found]
    assert math.dist(*found[0]) == pytest.approx(min(math.dist(*c) for c in found)) and measured <= 20 + 1e-6


TAG = 'min 10\'-0"'


def test_a_failing_yard_on_a_parallel_wall_is_dimensioned_at_the_walls_middle_not_its_corner():
    """Review round 7, F2: within the 1/4" tier every position is as short as the yard; shortest-first pushed a
    failing yard to the corner shared with the next one. There it stays nearest the middle."""
    from design_checker.check import check_site
    r = check_site(_plot(box(6, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})        # the west yard fails (6 ft)
    west = next(y for y in r["plan"]["yards"] if "Side yard, West" in y["label"])
    assert west["status"] == present.FAILS
    assert west["points"][1] == [pytest.approx(6), pytest.approx(46)]                  # the middle of the west wall


# ---- the Rhino check of #29 at f6642a9: every label inside the view; what is wrong placed first; short words ----


# ---- the drawing's way (Rhino checks of #29, round 4: "drawing-style dimension lines") -----------------------------

def _scene(view, scale, centre=(25, 46)):
    """check.plan's own yards for a house failing its west side yard on a 50 × 100 lot, on screen: `view` (w, h),
    `scale` px per ft, the plan's `centre` in the middle of the view."""
    from design_checker.check import check_site
    r = check_site(_plot(box(6, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})
    origin = (view[0] / 2, view[1] / 2)
    to = lambda pts: _screen(pts, scale, origin, centre)            # noqa: E731
    return r["plan"]["yards"], to(r["plan"]["footprint"][0]), to


def test_a_dimension_shows_only_its_number_marked_only_when_wrong():
    """On the drawing: the number only; ✕ or ? before it when the yard fails or needs review. Its name, what it
    needs and "(approx.)" are the panel's and the notice's."""
    assert logic.dim_number("✕", "7'-0 5/8\"", "does_not_comply") == "✕ 7'-0 5/8\""
    assert logic.dim_number("?", "26'-11 3/4\"", "needs_review") == "? 26'-11 3/4\""
    assert logic.dim_number("✓", "32'-4 1/4\"", "complies") == "32'-4 1/4\""
    yards, _, _ = _scene((1000, 640), 8)
    for y in yards:
        assert "yard" not in y["number"].lower() and "needs" not in y["number"] and "approx" not in y["number"]


def test_failing_and_in_review_yards_alone_carry_min_tags():
    from design_checker.check import check_site
    r = check_site(_plot(box(6, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})
    for y in r["plan"]["yards"]:
        if y["status"] in (present.FAILS, present.REVIEW):
            assert y["required_tags"] and all(t.startswith("min ") for t in y["required_tags"])
        else:
            assert y["required_tags"] == [] and y["required_lines"]          # the dashed line, no words


def test_the_elevations_height_limit_label_sits_past_its_lines_end_off_the_building():
    """The Rhino check of #28 at fc0b023: the "Height limit 35'-0"" label covered the coloured vault."""
    house = (300, 200, 500, 420)                                  # the building's box on screen
    spot = logic.limit_label_spot(((250, 220), (560, 220)), house, 140, 30, view=(1000, 640))
    assert spot is not None and spot[0] + 140 <= 250 and spot[0] + 140 <= house[0]   # left of the line and house
    edge = logic.limit_label_spot(((20, 220), (560, 220)), house, 140, 30, view=(1000, 640))
    assert edge is not None and edge[0] >= 560                    # no room on the left: past the right end


def test_the_limit_label_keeps_off_what_is_already_drawn():
    house = (300, 200, 500, 420)
    taken = [(100, 205, 160, 30)]                                 # the height's number on the left
    spot = logic.limit_label_spot(((250, 220), (560, 220)), house, 140, 30, view=(1000, 640), taken=taken)
    assert spot is not None and spot[0] >= 560                    # past the right end instead


def _scene_at(view, scale, centre):
    """check.plan's own yards for the sample-like failing scene (the west side yard fails), on a `view` (w, h)
    screen, `scale` px per ft, the plan's `centre` in the view's middle; the status box top right."""
    yards, house, to = _scene(view, scale, centre)
    status = logic.rect_quad(logic.status_box(view[0], ["Gordium · ✕ 1 does not comply · 2 need review",
                                                        "Draft rulebook · Lot lines: tax map"]))
    return yards, house, to, status


# ---- one placer for every plan label (rhino-ui's place_dim_label; the Rhino job at #29 fc6fbd6) ------------------

def _items(yards, to):
    """The labels draw_screen hands the placer for the scene's yards: each yard's number only, a failing or in-review
    yard's "min" tags on its required lines (its first position: check.plan's best)."""
    items = []
    for k, y in enumerate(yards):
        best = y["candidates"][0] if y.get("candidates") else {"points": y["points"]}
        items.append({"key": ("yard", k, y["number"]), "text": y["number"], "line": tuple(to(best["points"])),
                      "size": 11, "status": y["status"]})
        for j, (r, tag) in enumerate(zip(y["required_lines"], y["required_tags"])):
            items.append({"key": ("tag", k, j, tag), "text": tag, "line": tuple(to(r)), "size": logic.TAG_SIZE,
                          "status": y["status"]})
    return items


@pytest.mark.parametrize("view,scale,centre", [((656, 668), 6, (25, 46)), ((656, 668), 9, (25, 46)),
                                               ((656, 668), 12, (22, 50)), ((1000, 640), 8, (25, 46))])
def test_the_numbers_are_placed_by_the_one_placer_failing_first_off_the_status_box_and_the_house(view, scale, centre):
    """The Rhino check of #29 at fc6fbd6 (docked Top 656 × 668): #29's own placer and notice fallback put the notice
    across the model and the failing number on its coloured band. Every number and "min" tag now goes through
    logic.LabelRun (place_dim_label's HARD rules): the failing one placed first, each in view, none over the status
    box nor the house (unless forced, which is said), none over another."""
    yards, house, to = _scene(view, scale, centre)
    status = logic.status_box(view[0], ["Gordium · ✕ 1 does not comply · 2 need review",
                                        "Draft rulebook · Lot lines: tax map"])
    items = _items(yards, to)
    spots = logic.place_labels(items, view, keep=[status], dims=[i["line"] for i in items if i["key"][0] == "yard"],
                               shapes=[house])
    assert set(spots) == {i["key"] for i in items}                 # every number and tag placed: never dropped
    order = sorted(spots.values(), key=lambda g: g["order"])
    first = next(i for i in items if i["status"] == present.FAILS)
    assert spots[first["key"]]["order"] == 0                       # the failing yard's number first
    boxes = []
    for key, got in spots.items():
        box = (got["left"], got["top"], got["w"], got["h"])
        assert 0 <= box[0] and box[0] + box[2] <= view[0] and 0 <= box[1] and box[1] + box[3] <= view[1], key
        if not got["forced"]:
            assert not logic.shapes_hit(logic.rect_quad(box), logic.rect_quad(status)), key
            assert not logic.shapes_hit(logic.rect_quad(box), house), key
            assert not any(logic.shapes_hit(logic.rect_quad(box), logic.rect_quad(b)) for b in boxes), key
        boxes.append(box)
    assert order


def test_the_plugin_places_numbers_and_tags_with_the_one_placer_only():
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    screen = src[src.index("def draw_screen("):src.index("def _label_timer(")]
    assert 'items.append({"key": key, "text": number,' in screen               # a yard's number only
    assert 'key = ("tag", k, j, tag)' in screen                                  # its "min" tags: labels too
    assert "logic.LabelRun(" in src and "place_dimension" not in src and "tag_spot" not in src
    assert 'for c in (y.get("candidates") or [])[:1]]' in src     # the line at its best position only (86c01ea F5)
    source = (REPO / "packages/design_checker/design_checker/rhino_logic.py").read_text(encoding="utf-8")
    for gone in ("def place_dimension(", "def number_spot(", "def tag_spot(", "def number_box(", "NUMBER_SCALES"):
        assert gone not in source                                    # one placer: #29's own is gone
    assert source.count("def notice_place(") == 1 and source.count("def notice_spot(") == 1


# ---- feature 4: Osnap curves on a locked Gordium::Envelope layer (Ben, 2026-10-21) ------------------------------

def test_the_curves_to_snap_to_are_the_outline_and_every_yard_line_cautious_on_a_tax_map_lot():
    from shapely.geometry import LineString, Polygon
    from design_checker.check import check_site
    survey = check_site(_plot(box(12, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})["plan"]
    curves = logic.envelope_curves(survey)
    assert [c["what"] for c in curves][0] == "buildable outline" and not any(c["dashed"] for c in curves)
    lines = [c for c in curves if c["what"].startswith("required line")]
    assert len(lines) == 4                                        # front, two sides, rear: each in full
    front = next(c for c in lines if "Front" in c["what"])
    assert all(abs(p[1] - 25) < 1e-6 for p in front["points"]) and LineString(front["points"]).length == pytest.approx(50)
    tax = check_site(_plot(box(12, 27, 38, 65)), {**FACTS, "jurisdiction": CITY, "lot_surveyed": False})["plan"]
    curves = logic.envelope_curves(tax)
    cautious, drawn = curves[0], curves[1]
    assert (cautious["what"], cautious["dashed"], drawn["dashed"]) == ("buildable outline (cautious)", False, True)
    inner, outer = Polygon(cautious["points"]), Polygon(drawn["points"])
    assert outer.contains(inner) and outer.exterior.distance(inner.exterior) == pytest.approx(2.0)   # 2'-0" in
    assert all(c["dashed"] for c in curves[2:])


def test_the_envelope_layer_is_never_measured():
    assert logic.classify("Gordium::Envelope", "PolylineCurve") is None
    assert logic.classify("Gordium::Envelope", "Brep") is None
    # a block holding building parts there is still a problem (review of feature 4, F7: it was silently skipped)
    assert logic.classify("Gordium::Envelope", "InstanceReference", holds_building=True)
    assert logic.envelope_curves(None) == []


def test_the_plugin_replaces_them_each_check_whatever_the_layers_state_and_out_of_undo():
    """Review of feature 4: F1 (a hidden layer or a locked "Gordium": the deletes failed, a new set piled up each
    check), F6 (recorded for Undo inside GordiumCheck), F9 (a drawing failure failed the check), F11 (Show buildable
    envelope did nothing while a start box was open, and only in the active document)."""
    import ast
    from rule_format.rulebook import REPO
    src = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    fns = {n.name: ast.get_source_segment(src, n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)}
    body = fns["_envelope_curves"]
    assert "doc.UndoRecordingEnabled = False " in body and "UndoRecordingIsActive" not in body          # F6
    assert body.index("doc.UndoRecordingEnabled = False") < body.index("doc.Objects.AddPolyline(") \
        < body.index("doc.UndoRecordingEnabled = was")
    assert "doc.Objects.Delete(old, True, True)" in body                     # ignoring hidden and locked (F1)
    assert body.index("left = len(_envelope_objects(doc, index))") < body.index("if left:") \
        < body.index("doc.Objects.AddPolyline(")                             # none added over a set not deleted
    objects = fns["_envelope_objects"]
    assert "settings.HiddenObjects = True" in objects and "settings.LockedObjects = True" in objects
    assert "attrs.SetUserString(logic.ENVELOPE_KEY, c[\"what\"])" in body
    show = fns["_show_envelope_layer"]
    assert "layer.IsVisible = bool(STATE.get(\"envelope_on\", True))" in show and "_set_own_lock(doc, layer, True)" in show
    for name in ("set_envelope", "toggle_envelope"):                         # F11: every document, box open or not
        assert fns[name].index("_envelope_everywhere()") < fns[name].index("run_check(")
    assert "for d in Rhino.RhinoDoc.OpenDocuments() or []:" in fns["_envelope_everywhere"]
    run = fns["run_check"]
    assert "logic.guard(lambda: _envelope_curves(doc, result.get(\"plan\"), sent)," in run          # F9
    assert "_envelope_curves(doc, None, facts)" in run
    fail = run[run.index("_envelope_curves(doc, None, facts)") - 200:run.index("_envelope_curves(doc, None, facts)") + 200]
    assert 'dirty = STATE.get("dirty")' in fail and 'STATE["dirty"] = dirty' in fail      # round 4, F1
    # the layer made with Undo off, and none made by a failed check (review of dd44f1b, F1); left ones hidden and said
    assert body.index("doc.UndoRecordingEnabled = False") < body.index("index = _layer(doc, logic.ENVELOPE)")
    assert body.index("if plan is None and doc.Layers.FindByFullPath(logic.ENVELOPE, -1) < 0:") < body.index("_layer(")
    assert body.index("if left:") < body.index("layer.IsVisible = False") < body.index("return left")
    src_check = (REPO / "packages/design_checker/design_checker/check.py").read_text(encoding="utf-8")
    yl = src_check[src_check.index("def full_yard_lines("):src_check.index("def plan(")]
    assert "lines.buffer(limit, quad_segs=QUAD_SEGS))" in yl and "join_style" not in yl


def test_an_unknown_survey_is_the_tax_maps_and_a_tight_lot_is_never_drawn_as_surveyed():
    """Review of feature 4, F2 and F3: lot_surveyed missing read as a survey (no cautious outline, the as-drawn one
    solid); a narrow envelope with nothing left 2'-0" in drew solid lines too."""
    from design_checker.check import cautious_outline, from_tax_map
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert from_tax_map({}) and from_tax_map({"lot_surveyed": None}) and not from_tax_map({"lot_surveyed": True})
    assert cautious_outline(square, {}) and cautious_outline(square, {"lot_surveyed": True}) is None
    assert cautious_outline([[0, 0], [3, 0], [3, 30], [0, 30]], {}) == []       # 3 ft wide: nothing 2'-0" in
    dumbbell = [[0, 0], [10, 0], [10, 10], [6, 10], [6, 13], [10, 13], [10, 23], [0, 23], [0, 13], [4, 13], [4, 10],
                [0, 10]]
    assert len(cautious_outline(dumbbell, {})) == 2                            # two pieces, each kept
    from shapely.geometry import Polygon
    ell = [[0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20]]               # an inside corner at (10, 10)
    (inner,) = cautious_outline(ell, {})
    assert Polygon(inner).exterior.distance(Polygon(ell).exterior) == pytest.approx(2.0, abs=1e-3)
    from shapely.geometry import Point
    far = max(Polygon(ell).exterior.distance(Point(p)) for p in inner)       # every point of it 2'-0" in: at the
    assert far == pytest.approx(2.0, abs=1e-2)                               # inside corner too (round, not 2'-10")
    tight = logic.envelope_curves({"lot_from_tax_map": True, "buildable_cautious": [], "buildable": square,
                                   "yard_lines": [{"points": [[0, 1], [10, 1]], "name": "Front yard"}]})
    assert [c["dashed"] for c in tight] == [True, True] and "tax map" in tight[0]["what"]


def test_every_yard_gets_its_snap_line_a_lot_depth_limit_both_ends_and_curved_lines_in_full():
    """Review of feature 4: F4 (a limit waiting on the lot depth gave no line), F5 (the lot taken from each edge's
    first point: a curved line's middle missing), F8 (a band touching at a point: a collection whose boundary is
    None)."""
    from shapely.geometry import LineString
    from design_checker.check import full_yard_lines
    from model_measurement.measure import Lot
    bow = [[x, -10 * (1 - ((x - 25) / 25) ** 2)] for x in range(0, 51, 5)]        # the street side bulges 10 ft
    lot = {"id": "lot", "edges": [{"points": bow}, {"points": [[50, 0], [50, 100]]}, {"points": [[50, 100], [0, 100]]},
                     {"points": [[0, 100], [0, 0]]}]}
    site = {"units": "ft", "lot": lot, "buildings": [], "problems": []}
    shape = Lot(site, {"street_line": [[[0, 0], [50, 0]]]})
    item = {"measure": "front_yard", "name": "Front yard", "status": "complies", "limit_ft": 5,
            "points": [[25, -10], [25, 20]]}
    (front,) = full_yard_lines(shape, lot, [item])
    line = LineString(front["points"])
    assert line.length > 50 and min(p[1] for p in front["points"]) < -4         # follows the bulge, in full
    span = dict(item, limit_ft=None, limit_span_ft=[5, 8])
    assert sorted(y["limit_ft"] for y in full_yard_lines(shape, lot, [span])) == [5, 8]
