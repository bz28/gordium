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
    assert 'logic.out_of_date_line(parts.get("auto_check"), parts.get("checked_before", True))' in header
    # "Checking…" alone only while a check really runs (#32's progress line); out of date, the line says what comes
    assert header.count('"Checking…"') == 1 and \
        header.index("elif out_of_date and (checking or job is not None):") < header.index('"Checking…"')
    tick = body(UI, "def _auto_box(", "\ndef ")
    assert "logic.AUTO_CHECK_LABEL" in tick and "box.Checked = False" in tick and 'actions["auto_check"]' in tick
    panel = body(UI, "def make_panel(", "\ndef ")
    assert "row(_auto_box(actions, parts))" in panel and "*ticks" in panel    # off while a start box is open
    assert '"check": check_now, "auto_check": set_auto_check' in body(RHINO, "def PANEL_ACTIONS(", "\ndef ")


def test_the_plugin_checks_by_itself_only_when_asked_and_says_press_check_otherwise():
    idle = body(RHINO, "def _idle(", "\ndef ")
    assert "auto=_auto(front))" in idle and "ui.set_auto_tick(p, _auto(front))" in idle
    rows = body(RHINO, "def _status_rows(", "\ndef ")
    assert "logic.out_of_date_line(_auto(front), not never)" in rows
    check = body(RHINO, "def check_now(", "\ndef ")
    assert "run_check(doc, report=False)" in check
    run = body(RHINO, "def run_check(", "\ndef _toast(")
    assert "_sync_ticks(doc)" in run and "ui.set_auto_tick(p, _auto(doc))" in body(RHINO, "def _sync_ticks(", "\ndef ")
    confirm = body(RHINO, "def confirm(", "\ndef _confirm(")
    assert 'logic.changed_after_box(changed_before, STATE.get("dirty"), result is not None,' in confirm
    assert "failed=failed)" in confirm and confirm.index("failed = True") < confirm.index("result = _confirm(")
    assert confirm.index("result = _confirm(") < confirm.index("failed = False") < confirm.index("finally:")
    assert confirm.index('changed_before = STATE.get("dirty")') < confirm.index("_confirm(doc, facts, options, mode)")
    saved = body(RHINO, "def set_auto_check(", "\ndef ")
    assert "auto_check=bool(on)" in saved and "_save_ui_state(doc" in saved


# ---- review round 1 -------------------------------------------------------------------------------------------

def test_an_edits_time_is_never_moved_earlier():
    """P1: ticking Check after every edit (and closing a start box) moved the edit's time back by IDLE_SECONDS, so a
    check that finished just before the edit counted as covering it and the old marks showed as current."""
    for name, until in (("def set_auto_check(", "\ndef "), ("def confirm(", "\ndef _confirm(")):
        assert "time.time() - IDLE_SECONDS" not in body(RHINO, name, until), name
    # with the edit's own time kept, a check from before it never covers it
    assert logic.should_recheck(10.1, 10.7, False, False, 0.5, last_at=10.0, auto=True) is True


def test_a_document_come_to_the_front_is_checked_once_whatever_the_tick():
    """P2: switching to (or opening) a document set the edit mark, so with the tick off it was never checked and
    the panel said "Model changed since the last check"."""
    assert logic.should_check_front(True, False, False) is True
    assert logic.should_check_front(True, True, False) is False and logic.should_check_front(True, False, True) is False
    assert logic.should_check_front(False, False, False) is False
    new = body(RHINO, "def _new_document(", "\ndef ")
    assert 'STATE["check_front"] = True' in new and 'STATE["dirty"] = None' in new
    assert "_sync_ticks(Rhino.RhinoDoc.ActiveDoc)" in new and new.index("_sync_ticks(") < new.index("ui.show(")
    idle = body(RHINO, "def _idle(", "\ndef ")
    assert 'logic.should_check_front(STATE.get("check_front"), busy, _box_open())' in idle    # (#32: or any answer
    assert "_check_live(front)" in idle                                                         # awaited; background)


def test_never_checked_says_so_not_since_the_last_check():
    assert logic.out_of_date_line(False, checked_before=False) == logic.NEVER_CHECKED
    assert logic.out_of_date_line(False, checked_before=True) == logic.CHANGED_SINCE
    assert logic.out_of_date_line(True, checked_before=False) == "Checking… (the model changed)"


def test_gordium_start_says_who_checks_the_building_they_draw():
    """P2: "draw one and Gordium will check it" was false with the tick off."""
    assert logic.draw_one_hint(False) == "draw one, then press Check in the Gordium panel"
    assert logic.draw_one_hint(True) == "draw one and Gordium will check it"
    assert "Gordium will check it\")" not in RHINO and RHINO.count("logic.draw_one_hint(_auto(doc))") == 2


def test_every_new_or_refilled_panel_shows_the_documents_tick():
    """P3: a rebuilt panel and the check-error path left the tick off for a document that has it on."""
    assert body(RHINO, "def panel(", "\ndef ").count("ui.set_auto_tick(p, _auto(doc))") == 2
    assert "_sync_ticks(doc)" in body(RHINO, "def run_check(", "\ndef _toast(")


# ---- review round 2 -------------------------------------------------------------------------------------------

def _idle_tree():
    import ast
    src = body(RHINO, "def _idle(", "\ndef ")
    return ast.parse(src).body[0]


def test_the_viewport_greys_after_an_edit_whether_or_not_the_panel_is_open():
    """P0: round 1's document-switch block ended in a return that made the stale branch's redraw unreachable, so
    after an edit the viewport kept the old marks (✓ on a yard just broken) as if current. The viewport works out
    "out of date" as it draws: the stale branch must redraw, and not only when the panel is open."""
    import ast
    fn = _idle_tree()
    for node in ast.walk(fn):                       # nothing ever follows a return in a block
        for field in ("body", "orelse"):
            block = getattr(node, field, None)
            if isinstance(block, list):
                for k, st in enumerate(block[:-1]):
                    assert not isinstance(st, ast.Return), ast.unparse(block[k + 1])
    stale = next(n for n in ast.walk(fn) if isinstance(n, ast.If)
                 and any("stale_shown" in ast.unparse(s) for s in n.body))
    assert "Visible" not in ast.unparse(stale.test)          # greying never waits for the panel
    last = stale.body[-1]
    assert isinstance(last, ast.Expr) and ast.unparse(last) == "_redraw()"


def test_gordiumlive_turns_the_tick_never_the_edit_hooks_off():
    """Round 2: GordiumLive turned the edit hooks off, so edits went unnoticed and old marks stayed as if current.
    It now flips Check after every edit; edits are always noticed."""
    toggle = body(RHINO, "def toggle_live(", "\ndef ")
    assert "set_auto_check(not _auto(doc))" in toggle and "live(not" not in toggle and "live(False)" not in toggle


def test_the_architects_docs_say_press_check():
    """P2: QUICKSTART and README still said Gordium re-checks by itself half a second after every edit."""
    for name in ("QUICKSTART.md", "README.md"):
        text = (REPO / "apps/rhino_plugin" / name).read_text(encoding="utf-8")
        flat = " ".join(text.split())
        assert logic.CHANGED_SINCE in flat and logic.AUTO_CHECK_LABEL in flat, name
        assert "Half a second after you stop, Gordium re-checks" not in flat, name
        assert "With live mode on (the default), it re-checks after every edit" not in flat, name


# ---- review round 3 -------------------------------------------------------------------------------------------

def test_edits_are_noticed_whichever_command_drew_the_results():
    """P1: only GordiumCheck and GordiumStart turned edit noticing on; after GordiumFacts / Edit site… an edit never
    greyed the results (old marks shown as current) and the tick did nothing."""
    run = body(RHINO, "def _check_apply(", "\ndef _toast(")       # (#32 split run_check)
    at = run.index('STATE.setdefault("checked_at", {})[doc.RuntimeSerialNumber] = begun["at"]')
    assert run.index('if not STATE.get("live"):', at) < run.index("live(True)", at) < run.index("ui.show(panel(), view)")
    assert 'if not STATE.get("live"):' in body(RHINO, "def set_auto_check(", "\ndef ")


def test_no_command_text_still_promises_live_re_checking():
    """P3: install.py, gordium_check.py, gordium_off.py and docs/methods.md still said live re-checking."""
    for path in ("apps/rhino_plugin/install.py", "apps/rhino_plugin/gordium_check.py",
                 "apps/rhino_plugin/gordium_off.py", "docs/methods.md"):
        text = (REPO / path).read_text(encoding="utf-8")
        assert "live re-checking" not in text and "turn on live mode" not in text and "stop live mode" not in text, path
        assert "Live checking is on" not in text, path


def test_the_rhino_check_runs_its_idle_steps_across_real_idle():
    """The Rhino job at ea88c18 (docs/evidence/pr-27/rhino-ea88c18/): Rhino never raises its Idle event while a script
    runs, so check_button_in_rhino.py's wait (a loop on RhinoApp.Wait() inside the script) never let the plugin's idle
    handler grey the panel or check by itself, and claim 2 failed on a correct plugin. Now the script only starts the
    run: each step runs from a timer once no command is running, steps 2 and 4 only after Rhino's own Idle event has
    been seen 3 s past the edit, and a wait that never sees it fails (never hangs)."""
    script = (REPO / "apps/rhino_plugin/tests/check_button_in_rhino.py").read_text(encoding="utf-8")
    assert "RhinoApp.Wait()" not in script.split('"""', 2)[2]                 # (the docstring says why)
    assert "Rhino.RhinoApp.Idle += idle_handler" in script and "ef.UITimer()" in script
    tick = body(script, "def tick(", "\ndef ")
    assert "Command.InCommand()" in tick and "idle_enough()" in tick and "PHASE_LIMIT_S" in tick
    assert tick.index("late = ") < tick.index("InCommand()")      # a command left running fails too (review round 1)
    in_command = tick[tick.index("InCommand()"):]
    in_command = in_command[:in_command.index("return")]
    assert "if late:" in in_command and 'claim("no command left running' in in_command
    start = script.index('earlier = sc.sticky.get("gordium_check_button_run")')   # an earlier waiting run stopped
    stop = script[start:script.index('os.remove(S + "out.json")')]                 # before this run's out.json
    assert all(s in stop for s in ('earlier["finished"] = True', 'earlier["timer"].Stop()',
                                   'Rhino.RhinoApp.Idle -= earlier["idle"]'))
    step_b = body(script, "def step_b(", "\ndef ")                 # counted after the tick, before the edit
    assert (step_b.index('auto_box").Checked = True') < step_b.index('run["checks_at_tick"] = len(runs)')
            < step_b.rindex("move_top_floor("))
    step_c = body(script, "def step_c(", "\ndef ")
    assert 'run["checks_at_tick"] == 1' in step_c and "len(runs) == 2" in step_c   # the edit's own check
    enough = body(script, "def idle_enough(", "\ndef ")
    assert 'run["idle_at"]' in enough and "IDLE_WAIT_S" in enough
    assert (REPO / "docs/evidence/pr-27/rhino-ea88c18/phased_run_claims.json").exists()


def test_a_start_box_that_ends_in_an_error_leaves_the_results_greyed():
    """The headless check-15 (it failed on 2974913 too): a start box that ended in an error (its rollback stopped
    partway) was treated as a Cancel, so the model counted as unchanged and the results stayed shown as current over
    a model that may differ. An error keeps every edit seen during the box: the results grey out."""
    assert logic.changed_after_box(None, 20.0, False, failed=True) == 20.0        # an edit, then the error
    assert logic.changed_after_box(10.0, 20.0, False, failed=True) == 20.0        # the latest edit's time
    assert logic.changed_after_box(10.0, None, False, failed=True) == 10.0        # changed before the box: still
    assert logic.changed_after_box(None, None, False, failed=True) is None        # nothing touched: nothing to grey
    assert logic.changed_after_box(None, 20.0, False) is None                     # a Cancel, as before
