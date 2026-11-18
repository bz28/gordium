"""The panel's header fits the panel when a check could not run (Retry) or was cancelled (Check again).

The Rhino capture C7 (gordium_archive/video/captures/C7_worker_killed/02_panel_check_could_not_run_retry.png, the
checker killed during a check) showed the Retry button cut off at the floating panel's right edge, only "Re" in view:
it sat beside "⚠ Check could not run", a label as wide as the panel's content (PANEL_WIDTH - 48), so the two together
were wider than the panel. Cancelled's "Check again" sat the same way.

This lays the real header out (gordium_ui.show, with test_box_width's stand-ins for Eto and Rhino, which record the
controls and rows) and sizes each row the way Eto does (test_box_width.width: a label at its Width, a button at its
text's width plus its frame). Every row must fit the panel's content width (the panel less its 10 px padding each
side), floating and docked, at the panel's normal width (PANEL_WIDTH, 400) and the narrow width the in-Rhino width
check uses (380), and wider."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_box_width import ui, width  # noqa: E402, F401  (ui: the stand-in fixture)

PADDING = 10                         # make_panel: layout.Padding = ed.Padding(10)
WIDTHS = (380, 400, 540)             # narrow (panel_width_in_rhino.py's), the panel's own, wide


class _Host:
    """A DockHost stand-in: Rhino's docked panel, `Width` px wide."""

    def __init__(self, width):
        self.Width = width


# a check's header that asks for every button the header can hold: several buildings (Main building…), a lot not
# from a survey (Pick survey lot lines…), ground not set (Set grade…), beside Check and Edit site…
EVERY_BUTTON = {"header": {"main": "Measuring the largest of 2 buildings", "actions": ["Pick survey lot lines…",
                                                                                      "Set grade…"]},
                "items": [], "groups": [], "summary": "1 does not comply"}
VIEWS = {"no check yet": None, "every button": EVERY_BUTTON}


def _header(ui, panel_px, docked, view=None, **state):
    gordium_ui, _ = ui
    actions = {k: (lambda: None) for k in ("retry", "check", "edit_site", "main", "survey", "grade")}
    form = type("Form", (), {"host": _Host(panel_px)})() if docked else object()
    gordium_ui.DOCKED = docked
    parts = {"form": form, "tree": gordium_ui.ef.TreeGridView(), "actions": actions, "by_id": {}, "expanded": {},
             "selected": None, "header": gordium_ui.ef.DynamicLayout(), "detail": gordium_ui.ef.DynamicLayout(),
             "view": view}
    gordium_ui.show(parts, None, **state)
    return parts["header"]


def _buttons(layout):
    out = []
    for cells in layout.rows:
        for c in cells:
            items = [i.control for i in c.__dict__.get("Items", [])] if type(c).__name__ == "StackLayout" else [c]
            out += [x.__dict__.get("Text") for x in items if type(x).__name__ == "Button"]
    return out


STATES = {
    "could not run": ({"error": "the Gordium checker stopped (see gordium_worker.log in the temp folder)"}, "Retry"),
    "cancelled": ({"cancelled": True}, "Check again"),
    "checked": ({}, "Check"),
}


@pytest.mark.parametrize("docked", [False, True], ids=["floating", "docked"])
@pytest.mark.parametrize("panel_px", WIDTHS)
@pytest.mark.parametrize("view", sorted(VIEWS))
@pytest.mark.parametrize("state", sorted(STATES))
def test_every_header_row_fits_the_panel(ui, state, view, panel_px, docked):
    """Each header row (the headline, the reason, Retry / Check again, and the rows of Check, Edit site… and the
    buttons a check can add) no wider than the panel's content, so no button is cut off at its edge."""
    gordium_ui, _ = ui
    if not docked and panel_px == 540:
        pytest.skip("the floating window is PANEL_WIDTH wide; 540 is a docked width")
    kwargs, again = STATES[state]
    header = _header(ui, panel_px, docked, VIEWS[view], **kwargs)
    shown = _buttons(header)
    assert again in shown, "the state's own button is laid out"
    if VIEWS[view] is not None:
        assert {"Main building…", "Pick survey lot lines…", "Set grade…"} <= set(shown), shown
    inner = panel_px - 2 * PADDING
    wide = [(round(sum(width(c) for c in cells)), [type(c).__name__ for c in cells]) for cells in header.rows
            if sum(width(c) for c in cells) > inner]
    assert not wide, f"rows wider than the panel's {inner} px content: {wide}"


def test_the_model_finds_the_capture_s_clipped_row(ui):
    """The row C7 caught, built as it was (the headline beside Retry), is wider than the 400 px panel's content: the
    model above would have caught the bug."""
    gordium_ui, _ = ui
    gordium_ui.DOCKED = False
    was = gordium_ui.row(gordium_ui._wide("⚠ Check could not run", "needs_review", bold=True, size=15),
                         gordium_ui.button("Retry", lambda: None))
    assert width(was) > gordium_ui.PANEL_WIDTH - 2 * PADDING
