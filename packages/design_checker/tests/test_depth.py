"""Depth-tested lines (Ben, 2026-10-21): "On-screen lines respect depth in perspective (hidden behind solids); visible
in plan." The rules (rhino_logic) and how the plugin's drawing follows them (gordium_rhino, read as source: the
drawing itself is checked in Rhino by apps/rhino_plugin/tests/depth_in_rhino.py)."""

import ast
import math

import pytest

from design_checker import rhino_logic as logic
from rule_format.rulebook import REPO

SRC = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")


def _body(name):
    tree = ast.parse(SRC)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(SRC, fn)


def test_lines_are_on_top_in_plan_and_depth_tested_in_every_other_view():
    assert logic.lines_on_top(True, -1.0)                 # Top
    assert not logic.lines_on_top(False, -0.6)            # Perspective
    assert not logic.lines_on_top(True, 0.0)              # Front, Right: elevations
    assert not logic.lines_on_top(True, -0.7)             # a parallel view tilted (an axonometric)


def test_a_level_dimensions_ticks_in_the_model_are_45_degrees_in_plan_at_each_ends_height():
    a, b = (0.0, 0.0, 0.1), (0.0, 12.0, 0.1)
    ticks = logic.model_ticks(a, b, 1.0)
    assert len(ticks) == 2
    for (p, q), end in zip(ticks, (a, b)):
        assert p[2] == q[2] == end[2]
        assert math.dist(p, q) == pytest.approx(1.0)
        assert ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2) == pytest.approx(end[:2])
        assert abs(q[0] - p[0]) == pytest.approx(abs(q[1] - p[1]))      # 45° to a line along y


def test_an_upright_dimensions_ticks_show_in_the_front_and_the_right_views_alike():
    a, b = (40.0, 20.0, 0.0), (40.0, 20.0, 35.0)
    for (p, q), end in zip(logic.model_ticks(a, b, 1.0), (a, b)):
        assert math.dist(p, q) == pytest.approx(1.0)
        assert [(p[k] + q[k]) / 2 for k in range(3)] == pytest.approx(list(end))
        assert abs(q[0] - p[0]) > 0.3 and abs(q[1] - p[1]) > 0.3 and abs(q[2] - p[2]) > 0.3   # seen from x and y
    assert logic.model_ticks((1, 1, 1), (1, 1, 1), 1.0) == []


def test_the_plugin_draws_its_lines_on_top_only_in_plan_and_puts_depth_testing_back():
    scene = _body("draw_scene")
    assert "on_top = logic.lines_on_top(e.Viewport.IsParallelProjection, e.Viewport.CameraDirection.Z)" in scene
    # each line group that goes on top is followed by putting depth testing back before anything else is drawn
    ups = [i for i in range(len(scene)) if scene.startswith("_on_top(d, on_top)", i)]
    downs = [i for i in range(len(scene)) if scene.startswith("_on_top(d, False)", i)]
    assert len(ups) == len(downs) >= 3 and all(u < dn for u, dn in zip(ups, downs))
    assert all(downs[k] < ups[k + 1] for k in range(len(ups) - 1))
    assert scene.rstrip().endswith("d.DrawMeshWires(main, BLUE, 3)") and downs[-1] < scene.index("if o.confirm is not None")
    assert "if not on_top:" in scene and "_scene_dims(o, e, d, dark, old)" in scene
    assert "d.EnableDepthTesting(not on)" in _body("_on_top")


def test_off_plan_the_dimensions_are_drawn_in_the_model_and_not_over_the_solids():
    screen = _body("draw_screen")
    assert "flat = logic.lines_on_top(" in screen
    assert "if shown and flat else []" in screen                 # the faint required lines: on screen in plan only
    assert "        if flat:\n            _dimension(d, e.Viewport, line, color)" in screen   # the yards' too
    height = screen[screen.index("if height is not None and elevation and zoomed_in:"):]
    assert "_dimension(" not in height.split("for point, text, edge in")[0]   # the height's: in the model
    dims = _body("_scene_dims")
    assert dims.count("_model_dimension(d, e.RhinoDoc,") == 2 and "logic.dims_shown(zoomed_in, elevation)" in dims
    assert "d.Draw2dLine" not in dims and "d.Draw2dLine" not in _body("_model_dimension")


def test_the_legend_and_the_guide_say_where_the_lines_hide():
    assert "in every other view they hide behind the solids" in logic.legend_text()
    guide = (REPO / "apps/rhino_plugin/QUICKSTART.md").read_text(encoding="utf-8")
    assert "in Perspective and the elevations they hide behind your solids" in guide
