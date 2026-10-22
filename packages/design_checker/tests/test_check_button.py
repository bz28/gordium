"""The Check button (Ben, 2026-10-21): no check after every edit by default. After an edit the results grey out and
the panel and the viewport say "Model changed since the last check — press Check"; the Check button checks; an
optional "Check after every edit" tick (off, saved with the file) brings back checking by itself.

The rules are rhino_logic's (should_recheck, out_of_date_line, auto_check, changed_after_box); the pins below hold
the plugin (gordium_rhino.py, gordium_ui.py) to them. What only Rhino shows (the button and tick on screen, the
greyed rows, idle timing) is apps/rhino_plugin/tests/check_button_in_rhino.py."""
import itertools
from pathlib import Path

import pytest

from design_checker import rhino_logic as logic

REPO = Path(__file__).resolve().parents[3]
RHINO = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
UI = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")


def body(src, name, until):
    return src[src.index(name):src.index(until, src.index(name) + len(name))]


@pytest.mark.parametrize("dirty, now, running, box, last", list(itertools.product(
    (None, 10.0), (10.2, 11.0), (False, True), (False, True), (None, 9.0, 10.5))))
def test_nothing_checks_by_itself_unless_asked(dirty, now, running, box, last):
    """Off (the default): never a check after an edit, whatever the timing. On: exactly as live mode was."""
    assert logic.should_recheck(dirty, now, running, box, 0.5, last, auto=False) is False
    on = logic.should_recheck(dirty, now, running, box, 0.5, last, auto=True)
    was = bool(dirty) and now - dirty >= 0.5 and not running and not box and not (last is not None and last >= dirty)
    assert on is was


def test_the_out_of_date_line_says_press_check_unless_a_check_is_coming():
    assert logic.out_of_date_line(False) == logic.CHANGED_SINCE == "Model changed since the last check — press Check"
    assert logic.out_of_date_line(True) == "Checking… (the model changed)"


def test_check_after_every_edit_is_off_unless_this_file_says_so():
    assert logic.auto_check(None) is False and logic.auto_check({}) is False
    assert logic.auto_check({"auto_check": True}) is True and logic.auto_check({"auto_check": False}) is False
    assert "auto_check" in logic.storable_ui({"auto_check": True})          # kept with the file


@pytest.mark.parametrize("before, now, drawn, want", [
    (None, 50.0, False, None),          # Cancel: the box's own edits rolled back, the results still current
    (40.0, 50.0, False, 40.0),          # Cancel, but the model had changed before the box: still out of date
    (None, 50.0, True, 50.0),           # Draw: what is left counts (Draw's own check covers its edits)
    (None, None, True, None),
])
def test_cancelling_a_start_box_never_greys_out_current_results(before, now, drawn, want):
    assert logic.changed_after_box(before, now, drawn) == want


# ---- the plugin does what the rules say ----------------------------------------------------------------------

def test_the_panel_has_the_check_button_first_and_the_tick_off():
    header = body(UI, "def _header(", "\ndef ")
    assert 'buttons = [button("Check", a["check"]), button("Edit site…", a["edit_site"])]' in header
    assert 'logic.out_of_date_line(parts.get("auto_check"))' in header and '"Checking…"' not in header
    tick = body(UI, "def _auto_box(", "\ndef ")
    assert "logic.AUTO_CHECK_LABEL" in tick and "box.Checked = False" in tick and 'actions["auto_check"]' in tick
    panel = body(UI, "def make_panel(", "\ndef ")
    assert "row(_auto_box(actions, parts))" in panel and "*ticks" in panel    # off while a start box is open
    assert '"check": check_now, "auto_check": set_auto_check' in body(RHINO, "def PANEL_ACTIONS(", "\ndef ")


def test_the_plugin_checks_by_itself_only_when_asked_and_says_press_check_otherwise():
    idle = body(RHINO, "def _idle(", "\ndef ")
    assert "auto=_auto(front))" in idle and "ui.set_auto_tick(p, _auto(front))" in idle
    rows = body(RHINO, "def _status_rows(", "\ndef ")
    assert "logic.out_of_date_line(_auto(Rhino.RhinoDoc.ActiveDoc))" in rows
    check = body(RHINO, "def check_now(", "\ndef ")
    assert "run_check(doc, report=False)" in check
    run = body(RHINO, "def run_check(", "\ndef _toast(")
    assert 'ui.set_auto_tick(STATE.get("panel_parts"), _auto(doc))' in run
    confirm = body(RHINO, "def confirm(", "\ndef _confirm(")
    assert 'logic.changed_after_box(changed_before, STATE.get("dirty"), result is not None)' in confirm
    assert confirm.index('changed_before = STATE.get("dirty")') < confirm.index("_confirm(doc, facts, options, mode)")
    saved = body(RHINO, "def set_auto_check(", "\ndef ")
    assert "auto_check=bool(on)" in saved and "_save_ui_state(doc" in saved
