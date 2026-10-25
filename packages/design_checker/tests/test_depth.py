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
    assert downs[-1] < scene.index("if o.confirm is not None") < scene.index("d.DrawMeshWires(main, BLUE, 3)")
    assert "if not on_top:" in scene and "_scene_dims(o, e, d, dark, old)" in scene
    assert "d.EnableDepthTesting(not on)" in _body("_on_top")


def test_whatever_a_frame_does_depth_testing_and_writing_are_put_back():
    """A step that raises is caught by the conduit's guard; without the finally, depth testing stayed off for the
    rest of Rhino's frame (review round 1, F3)."""
    tree = ast.parse(_body("draw_scene"))
    (fn,) = tree.body
    (t,) = [n for n in fn.body if isinstance(n, ast.Try)]
    assert fn.body[-1] is t                      # everything the frame draws is inside the try
    done = ast.unparse(t.finalbody)
    assert "_on_top(e.Display, False)" in done and "_see_through(e.Display, False)" in done
    assert "DrawBrepShaded" in ast.unparse(t.body) and "_on_top(d, on_top)" in ast.unparse(t.body)


def test_the_see_through_fills_write_no_depth_so_lines_behind_them_still_show():
    """The envelope, the yards' fill and the coloured parts are see-through: drawn without writing depth, so a
    dimension behind them is not hidden (review round 1, F2); depth writing is back on after each."""
    scene = _body("draw_scene")
    assert "d.EnableDepthWriting(not on)" in _body("_see_through")
    for fill in ("d.DrawBrepShaded(o.yards_zone", "d.DrawBrepShaded(o.envelope", "d.DrawBrepShaded(g, Rhino.Display"):
        at = scene.index(fill)
        before, after = scene[:at], scene[at:]
        assert before.rindex("_see_through(d, True)") > before.rfind("_see_through(d, False)"), fill
        lines = [i for i in (after.find(k) for k in ("d.DrawBrepWires", "d.DrawPolyline", "d.DrawPatterned",
                                                       "d.DrawLine", "d.DrawPoint")) if i > 0]
        assert after.index("_see_through(d, False)") < min(lines), fill      # back on before any line is drawn


def test_the_yard_dimensions_stand_just_above_the_lots_own_level():
    """Off plan they are depth-tested: at z 0 a lot drawn higher, or the ground under it, hid them (round 1, F1)."""
    assert logic.dim_level(412.0) == pytest.approx(412.1) and logic.dim_level(None) == pytest.approx(0.1)
    plan = _body("_draw_plan")
    assert "z = logic.dim_level(_lot_level(doc, facts))" in plan          # the one lot-level helper (round 2)
    assert plan.count(", z), _model_point(doc,") == 2 and ", 0.1)" not in plan


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
