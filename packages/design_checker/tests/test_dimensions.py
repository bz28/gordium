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
    assert "if shown else []" in screen and screen.count("_dimension(d, e.Viewport,") == 2   # yards, height
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
    assert "_dimension(d, e.Viewport, chosen, color)" in screen   # the yards' dimensions: on screen, over the colours


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


def test_a_label_sits_on_its_line_aligned_centred_and_outside_the_building():
    a, b = (100, 300), (100, 200)                                # a vertical dimension, lot end at the bottom
    q = logic.label_on_line(a, b, 80, away=(300, 250))           # the house to the right
    xs, ys = [p[0] for p in q], [p[1] for p in q]
    assert max(xs) <= 100 - logic.DIM_LABEL_GAP_PX + 1e-9        # beside the line, on the side away from the house
    assert max(ys) - min(ys) == pytest.approx(80) and max(xs) - min(xs) == pytest.approx(logic.DIM_LABEL_H_PX)
    assert (min(ys) + max(ys)) / 2 == pytest.approx(250)         # centred on the line (aligned: its long side along it)
    # an upright line reads bottom to top, from the right, whichever way it was given (review round 6, F4)
    assert logic.text_angle(a, b) == pytest.approx(-90) and logic.text_angle(b, a) == pytest.approx(-90)
    assert logic.text_angle((0, 0), (10, 0)) == pytest.approx(0) and logic.text_angle((10, 0), (0, 0)) == pytest.approx(0)


def test_a_dimension_slides_along_its_wall_to_a_clear_spot_else_its_label_goes_past_its_end_with_a_leader():
    cands = [((100, 300), (100, 200)), ((140, 300), (140, 200)), ((180, 300), (180, 200))]
    status = logic.rect_quad((60, 220, 70, 60))                  # covers the first position's label
    i, q, kind = logic.place_dimension(cands, 80, [status])
    assert (i, kind) == (1, "on") and not logic.shapes_hit(q, status)
    short = [((100, 230), (100, 200))]                           # 30 px long: shorter than its words
    i, q, kind = logic.place_dimension(short, 80, [], away=(300, 215))
    assert kind == "on" and min(p[1] for p in q) >= 200 + logic.DIM_LABEL_GAP_PX - 1e-9 and max(p[1] for p in q) > 230
    blocked = logic.rect_quad((40, 190, 58, 130))                # beside it is taken: past its outer end, a leader
    i, q, kind = logic.place_dimension(short, 80, [blocked], away=(300, 215))
    assert kind == "end" and min(p[1] for p in q) >= 230 + logic.DIM_LABEL_GAP_PX - 1e-9
    i, q, kind = logic.place_dimension(cands, None, [status])    # no words: only the line is placed (clear)
    assert (i, q, kind) == (0, None, "none") or not logic.shapes_hit(
        [(c[0] - 1, c[1]) for c in cands[i]] + [(c[0] + 1, c[1]) for c in cands[i][::-1]], status)


@pytest.mark.parametrize("scale", [4, 7, 12])
def test_the_four_yard_labels_of_a_plan_keep_clear_of_each_other_the_boxes_the_edge_labels_and_the_house(scale):
    """The sample's own scene, as the plugin places it: check.plan's positions for a house on a 50 × 100 lot, on a
    1000 × 640 view at three zooms, with the status box (top right), the notice bar (bottom), the lot edges'
    length labels and the house; each yard placed in turn, its label then an obstacle for the next."""
    from design_checker.check import check_site
    r = check_site(_plot(box(6, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})       # the west side yard fails
    yards = r["plan"]["yards"]
    house = _screen(r["plan"]["footprint"][0], scale)
    status = logic.rect_quad(logic.status_box(1000, ["Gordium · ✕ 1 does not comply · 2 need review · 7 comply",
                                                     "Draft rulebook · Lot lines: tax map, approximate (±2'-0\")"]))
    notice = logic.rect_quad((12, 640 - 30 - 64, 860, 30))
    edge_labels = [logic.rect_quad((x - 30, y - 10, 60, 20)) for x, y in _screen([(25, 100), (50, 50), (0, 50)], scale)]
    obstacles = [status, notice] + edge_labels
    away = (sum(p[0] for p in house) / len(house), sum(p[1] for p in house) / len(house))
    placed = []
    for y in yards:
        cands = [tuple(_screen(c["points"], scale)) for c in y["candidates"]]
        i, q, kind = logic.place_dimension(cands, logic.label_width(y["label"], 11), obstacles, house, away)
        assert q is not None
        assert not any(logic.shapes_hit(q, o) for o in obstacles), (y["label"], kind)
        assert not logic.shapes_hit(q, house), y["label"]
        obstacles.append(q)
        placed.append((y["label"], i, kind))
    assert len(placed) == 4


def test_each_required_line_has_its_min_tag():
    from design_checker.check import check_site
    r = check_site(_plot(box(12, 27, 38, 65)), {**FACTS, "jurisdiction": CITY})
    tags = {y["label"].split(" ")[1] + " " + y["label"].split(" ")[2]: y["required_tags"] for y in r["plan"]["yards"]}
    assert tags["Front yard"] == ["min 25'-0\""] and tags["Side yard,"] == ["min 10'-0\""] * 1
    for y in r["plan"]["yards"]:
        assert len(y["required_tags"]) == len(y["required_lines"]) == len(y["candidates"][0]["required_lines"])



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


def test_with_two_buildings_a_label_never_sits_inside_either_and_turns_away_from_its_own():
    """Review round 6, F2: only the first building's outline was checked, and the label's side was taken from all
    buildings' middle."""
    house = logic.rect_quad((200, 200, 200, 150))
    garage = logic.rect_quad((130, 200, 40, 60))                 # just beside the dimension, on its outer side
    owner, middle = logic.nearest_outline((200, 270), [garage, house])
    assert owner == house and middle == (300, 275)
    cands = [((120, 270), (200, 270))]                          # a west yard: from the house out to the lot line
    i, q, kind = logic.place_dimension(cands, 60, [], [house, garage], middle)
    assert q is not None and not logic.shapes_hit(q, garage) and not logic.shapes_hit(q, house)
