"""Live progress and Cancel (Look up, Draw, the check, the Zoning report): what the architect sees while Gordium works,
and that Cancel stops the work with nothing changed. The plain decisions are tested by behaviour here; the Rhino side
(the window, the panel's line, the box's line, the Draw rollback) is proven in Rhino by
apps/rhino_plugin/tests/progress_cancel_in_rhino.py, and pinned here by its source where CI can't run Rhino."""

import io
import json
import queue
import threading
import time
from pathlib import Path

import pytest

from design_checker import rhino_logic as logic
from design_checker.__main__ import serve
from design_checker.check import STEPS, check, start
from design_checker.lookup_box import _fixture_http, main as lookup_main
from model_measurement.project import load_facts
from rule_format.rulebook import REPO
from site_lookup.adapters.ithaca_city.lookup import STEPS as LOOKUP_STEPS, lookup
from host_source import host_path, host_text

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
MODEL = SITE / "spreadsheet_design_model.3dm"
RHINO = host_text("rhino", "plugin", purpose="wiring")
UI = host_text("rhino", "ui", purpose="wiring")


def part(src, start_at, end_at):
    return src[src.index(start_at):src.index(end_at, src.index(start_at) + 1)]


# ---- the job: work off Rhino's thread, and a Cancel whose answer is never used ------------------------------------

def test_a_job_runs_on_its_own_thread_and_says_each_step():
    seen = []

    def work(step):
        seen.append(threading.current_thread() is not threading.main_thread())
        step("Measuring the building…")
        return 42

    job = logic.Job(work, "Checking…")
    assert job.wait(5) and job.outcome() == ("done", 42) and seen == [True]
    assert job.step == "Measuring the building…"


def test_an_error_in_the_work_is_kept_for_rhinos_thread():
    job = logic.Job(lambda step: 1 / 0, "Checking…")
    assert job.wait(5)
    how, e = job.outcome()
    assert how == "error" and isinstance(e, ZeroDivisionError)


def test_cancel_stops_the_work_and_its_answer_is_never_used():
    go = threading.Event()
    stopped = []
    job = logic.Job(lambda step: (go.wait(5), "a late answer")[1], "Checking…", stop=lambda: stopped.append(1))
    assert not job.wait(0.05) and not job.finished()
    assert job.cancel() and stopped == [1] and job.finished()          # nothing more to wait for, at once
    assert job.step == logic.CANCELLING
    job.say("Writing the zoning report…")                              # a late step: not shown
    assert job.step == logic.CANCELLING
    go.set()
    job._thread.join(5)
    assert job.done and job.outcome() == ("cancelled", None)          # the answer arrived, and is dropped
    assert not job.cancel() and stopped == [1]                        # once only


def test_work_with_no_way_to_stop_it_is_never_cancelled():
    """Review round 2: cancelling work nothing can stop left its thread reading the checker's answers (it could take
    the next request's), and raised WorkCancelled where no caller expects it."""
    go = threading.Event()
    job = logic.Job(lambda step: (go.wait(5), "the answer")[1], "Starting Gordium's checker…")
    assert not job.cancellable() and not job.cancel() and not job.cancelled
    go.set()
    assert job.wait(5) and job.outcome() == ("done", "the answer")


def test_a_job_done_before_cancel_keeps_its_answer():
    stopped = []
    job = logic.Job(lambda step: "the answer", "Checking…", stop=lambda: stopped.append(1))
    job.wait(5)
    assert not job.cancel() and stopped == [] and job.outcome() == ("done", "the answer")


def test_the_progress_line_moves_and_counts_seconds():
    assert logic.progress_line(0) == "●○○  0 s"
    assert logic.progress_line(logic.SPIN_S * 1.5) == "○●○  0 s"
    assert logic.progress_line(logic.SPIN_S * 2.5) == "○○●  0 s"
    assert logic.progress_line(7.2, 45) == "%s  7 s (stops at 45 s)" % logic.SPINNER[int(7.2 / logic.SPIN_S) % 3]
    frames = {logic.progress_line(t / 10).split()[0] for t in range(0, 20)}
    assert frames == set(logic.SPINNER)


# ---- the checker's progress lines -------------------------------------------------------------------------------

def lines(*items):
    q = queue.Queue()
    for i in items:
        q.put(i)
    return q


def test_progress_lines_are_told_and_the_answer_is_returned():
    said = []
    got = logic.answer_for(lines('{"id": 3, "step": "Reading the model…"}\n', '{"id": 3, "step": "Checking the rules…"}\n',
                                 '{"id": 3, "ok": true, "result": 7}\n'), 3, 5, said.append)
    assert got == {"id": 3, "ok": True, "result": 7} and said == ["Reading the model…", "Checking the rules…"]


def test_another_requests_progress_line_is_out_of_step():
    with pytest.raises(logic.CheckerOutOfStep):
        logic.answer_for(lines('{"id": 2, "step": "Reading the model…"}\n', '{"id": 3, "ok": true}\n'), 3, 5)


def test_progress_lines_never_extend_the_time_limit():
    q = queue.Queue()

    def drip():                         # a step every 0.1 s, never an answer
        for _ in range(30):
            q.put('{"id": 1, "step": "Measuring the building…"}\n')
            time.sleep(0.1)

    threading.Thread(target=drip, daemon=True).start()
    began = time.monotonic()
    with pytest.raises(logic.CheckerOutOfStep):
        logic.answer_for(q, 1, 0.5)
    assert time.monotonic() - began < 2


def test_serve_sends_progress_lines_only_when_asked(monkeypatch):
    import design_checker.__main__ as main_module

    def fake_check(model, facts, report=None, problems=None, extras=None, step=None, today=None):
        if step is not None:            # (asked without "progress": no step function at all)
            step("Reading the model…")
            step("Measuring the building…")
        return {"fine": True, "told": step is not None}

    monkeypatch.setattr(main_module, "check", fake_check)
    out = io.StringIO()
    serve(io.StringIO('{"id": 1, "cmd": "check", "model": "m.3dm", "facts": {}, "progress": true}\n'
                      '{"id": 2, "cmd": "check", "model": "m.3dm", "facts": {}}\n'), out)
    got = [json.loads(line) for line in out.getvalue().splitlines()]
    assert got[:2] == [{"id": 1, "step": "Reading the model…"}, {"id": 1, "step": "Measuring the building…"}]
    assert got[2]["id"] == 1 and got[2]["ok"]
    assert len(got) == 4 and got[3]["id"] == 2 and got[3]["ok"]      # without "progress": the answer only
    assert got[2]["result"]["told"] and not got[3]["result"]["told"]


def test_a_long_stage_says_itself_again_until_the_answer_which_is_always_last(monkeypatch):
    """UI polish change 15: the Revit add-in stops a check only when the worker says nothing for 60 s, so a request that
    asked for progress hears its current stage again every HEARTBEAT seconds while the stage runs; the beat stops before
    the answer, which stays the request's last line."""
    import design_checker.__main__ as main_module

    monkeypatch.setattr(main_module, "HEARTBEAT", 0.02)

    def slow_check(model, facts, report=None, problems=None, extras=None, step=None, today=None):
        step("Measuring the building…")
        time.sleep(0.2)                 # one long stage: ten beats or so
        return {"fine": True}

    monkeypatch.setattr(main_module, "check", slow_check)
    out = io.StringIO()
    serve(io.StringIO('{"id": 7, "cmd": "check", "model": "m.3dm", "facts": {}, "progress": true}\n'), out)
    got = [json.loads(line) for line in out.getvalue().splitlines()]
    assert got[-1]["id"] == 7 and got[-1]["ok"]                      # the answer, last
    beats = got[:-1]
    assert len(beats) >= 3                                           # the first line, then the stage again
    assert beats[0] == {"id": 7, "step": "Measuring the building…"}
    assert all(b == {"id": 7, "step": "Measuring the building…", "again": True} for b in beats[1:])
    assert not main_module._Steps({"id": 1}, io.StringIO())._beat.is_alive()   # a beat runs only inside a request
    # review round 2: a repeat is always the newest stage (read under the lock), never an older one after a newer
    out = io.StringIO()
    steps = main_module._Steps({"id": 8}, out)
    steps("Reading the model…")
    steps("Measuring the building…")
    steps.repeat()
    assert json.loads(out.getvalue().splitlines()[-1]) == {"id": 8, "step": "Measuring the building…", "again": True}


def test_a_host_that_shows_or_records_stages_skips_the_repeats(monkeypatch):
    """Review round 2: Rhino and the recorded sessions show and record each stage once; a repeat (marked "again")
    only says the worker is still working, so a session recorded on a long check replays the same."""
    import design_checker.host_core.worker_client as client

    src = Path(client.__file__).read_text(encoding="utf-8")
    assert 'if on_step is not None and not answer.get("again"):' in src


def test_a_check_and_a_start_say_each_stage_in_order(tmp_path):
    facts = load_facts(SITE / "spreadsheet_design_model_facts.yaml")
    said = []
    plain = check(MODEL, facts)
    told = check(MODEL, facts, tmp_path / "report.xlsx", step=said.append)
    assert said == [STEPS["read"], STEPS["measure"], STEPS["rules"], STEPS["report"]]
    assert told["summary"] == plain["summary"]                       # the steps never change the answer
    said.clear()
    check(MODEL, facts, step=said.append)
    assert STEPS["report"] not in said                               # no report asked: never "Writing…"
    said.clear()
    start(MODEL, {**facts, "lot_surveyed": True}, step=said.append)
    assert said == [STEPS["lot"], STEPS["largest"]]


# ---- the lookup's progress lines ----------------------------------------------------------------------------------

def test_the_lookup_says_each_stage_and_the_steps_never_change_its_answer():
    http, now = _fixture_http("106_ithaca_rd")
    said = []
    told = lookup("106 Ithaca Rd, Ithaca, NY 14850", http, now, step=said.append)
    http, now = _fixture_http("106_ithaca_rd")
    plain = lookup("106 Ithaca Rd, Ithaca, NY 14850", http, now)
    assert said == [LOOKUP_STEPS[k] for k in ("address", "parcel", "streets", "ground", "zoning", "overlays")]
    assert json.dumps(told, sort_keys=True, default=str) == json.dumps(plain, sort_keys=True, default=str)


def test_the_box_reads_the_latest_step_and_only_a_real_answer(capsys):
    lookup_main(["106 Ithaca Rd, Ithaca, NY 14850", "--fixture", "106_ithaca_rd"])
    out = capsys.readouterr().out
    rows = out.strip().splitlines()
    assert logic.lookup_step("\n".join(rows[:2])) == LOOKUP_STEPS["parcel"]
    assert logic.lookup_answer(out)["status"] == "found"
    # stopped half way (Cancel, a crash): the steps so far are never taken for an answer
    half = "\n".join(rows[:3])
    assert logic.lookup_answer(half, "106 Ithaca Rd")["status"] == "error"
    assert logic.lookup_answer("", "x") == {"status": "error", "query": "x", "detail": "the lookup printed no answer"}
    assert logic.lookup_step("") is None and logic.lookup_step("not json\n{\"step\": \"A…\"}\n{\"step\"") == "A…"


def test_the_box_line_names_the_address_the_step_and_the_time():
    line = logic.lookup_status("106 Ithaca Rd", "Reading the City zoning map…", 7.0)
    assert line.startswith("Looking up 106 Ithaca Rd · Reading the City zoning map…  ")
    assert line.endswith("7 s (stops at %d s)" % logic.LOOKUP_LIMIT_S)
    assert logic.lookup_status("106 Ithaca Rd", None, 0).startswith("Looking up 106 Ithaca Rd · Starting the lookup…")


def test_cancel_lookup_puts_the_box_back_as_it_was_before_look_up():
    before = {"says": "Shown dashed: 96 Ithaca Rd's lot.", "status": "found", "query": "96 Ithaca Rd"}
    saved = {"_lookup": {"looking": "200 Elm St"}, "_pending": {"address": "96 Ithaca Rd"}, "zone_source": "x"}
    after = logic.lookup_cancelled(saved, before)
    assert after["_lookup"]["says"] == "Look up of 200 Elm St cancelled: nothing changed. Shown dashed: 96 Ithaca " \
                                       "Rd's lot."
    assert {k: after["_lookup"][k] for k in ("status", "query")} == {"status": "found", "query": "96 Ithaca Rd"}
    # Look up and Cancel again: said once, never piled up (review round 1)
    again = logic.lookup_cancelled({"_lookup": {"looking": "300 Oak Ave"}}, after["_lookup"])
    assert again["_lookup"]["says"] == "Look up of 300 Oak Ave cancelled: nothing changed. Shown dashed: 96 Ithaca " \
                                       "Rd's lot."
    third = logic.lookup_cancelled({"_lookup": {"looking": "300 Oak Ave"}}, again["_lookup"])
    assert third["_lookup"]["says"] == again["_lookup"]["says"]
    assert after["_pending"] == {"address": "96 Ithaca Rd"} and after["zone_source"] == "x"   # the preview kept
    assert "looking" not in logic.lookup_cancelled(saved, None)["_lookup"]
    assert saved["_lookup"] == {"looking": "200 Elm St"}                                    # (a copy)
    rows = {r["key"]: r for r in logic.box_rows({"lookup": after["_lookup"]})}
    assert rows["address"]["actions"] == [("lookup", "Look up", True)] and rows["address"]["status"] is None


# ---- a background re-check: shown only if the model hasn't changed since it read it --------------------------------

def test_a_background_recheck_is_shown_only_for_the_model_it_read():
    assert logic.checked_while_still(10.0, None)
    assert logic.checked_while_still(10.0, 9.5)          # an edit before it read the model: covered
    assert not logic.checked_while_still(10.0, 10.0)
    assert not logic.checked_while_still(10.0, 12.0)     # edited while it ran: dropped, checked again


def test_a_cancelled_report_says_whether_the_file_changed():
    assert logic.report_cancelled("/r.xlsx", False) == logic.REPORT_CANCELLED
    assert "already been saved to /r.xlsx" in logic.report_cancelled("/r.xlsx", True)


# ---- the Rhino side, pinned by its source (progress_cancel_in_rhino.py proves it in Rhino) --------------------------

def test_every_answer_is_awaited_off_rhinos_thread():
    ask = part(RHINO, "def ask(", "def _ask_job(")
    job = part(RHINO, "def _ask_job(", "def _answer(")
    assert "ui.wait(job, cancel" in ask and "logic.exchange" not in ask
    # every exchange is inside the job's work, on its own thread
    assert RHINO.count("logic.exchange(") == job.count("logic.exchange(") == 2 and "def work(step):" in job
    assert "logic.Job(work," in job
    assert "progress=True" in job and "stop=_stop_worker if cancel else None" in job
    answer = part(RHINO, "def _answer(", "# ---- the model")
    assert 'if how == "cancelled":\n        raise logic.WorkCancelled()' in answer


def test_live_mode_rechecks_in_the_background_and_drops_a_stale_answer():
    idle = part(RHINO, "def _idle(", "def documents(")
    assert "_check_live(doc)" in idle and "run_check(" not in idle
    finish = part(RHINO, "def _live_finish(", "def _settle_live(")
    assert 'logic.checked_while_still(begun["at"], STATE.get("dirty"))' in finish
    assert finish.index("checked_while_still") < finish.index("_check_apply(")
    assert 'doc.RuntimeSerialNumber != begun["doc"]' in finish and "_box_open()" in finish
    for caller in ("def _ask_waiting(", "def run_check(", "def open_report(", "def confirm("):
        assert "_settle_live()" in part(RHINO, caller, "\ndef "), caller


def test_draw_works_out_the_starting_house_before_anything_is_saved_or_committed():
    drawn = part(RHINO, "def _drawn(", "def hide_massing(")
    assert drawn.index('STATE["start_plan"] = planned or _plan_house(') < drawn.index("_save_ui_state(doc, ui_state)") < \
        drawn.index("doc.Strings.SetString") < drawn.index("logic.draw_then_commit(session, save)")
    plan = part(RHINO, "def _plan_house(", "def _draw_starting_house(")
    assert "ask(request, cancel=True)" in plan
    house = part(RHINO, "def _draw_starting_house(", "def _doc_name(")
    assert 'plan["key"] == _start_key(request)' in house and "start = ask(request)  " in house   # no Cancel
    start_cmd = part(RHINO, "def gordium_start(", "def _draw_starting_house(")
    assert "except logic.WorkCancelled as stopped:" in start_cmd and \
        "say(getattr(stopped, \"said\", logic.DRAW_CANCELLED))" in start_cmd
    edit = part(RHINO, "def edit_facts(", "def report_path(")
    assert "except logic.WorkCancelled as stopped:" in edit


def test_a_cancelled_check_leaves_nothing_shown_as_checked():
    cancelled = part(RHINO, "def _check_cancelled(", "# ---- live mode's re-check")
    assert "_clear(o)" in cancelled and "cancelled=True" in cancelled and '"checked_at"' not in cancelled
    report = part(RHINO, "def open_report(", "def _drop_report_part(")
    assert report.index("logic.report_cancelled(") < report.index("ui.open_target(path)")
    # review round 2: whoever asked for the report (GordiumCheck too), no half-written copy is left, and only once
    # the stopped checker is gone
    run = part(RHINO, "def run_check(", "def _check_begin(")
    cancelled = run[run.index("except logic.WorkCancelled:"):run.index("except Exception as e:")]
    assert "if report:" in cancelled and "_drop_report_part(report_path(doc))" in cancelled
    stop = part(RHINO, "def _stop_worker(", "def ask(")
    assert stop.index("p.kill()") < stop.index("p.wait(timeout=2)")


def test_the_wait_window_closes_when_the_job_is_done_or_cancelled():
    wait = part(UI, "def wait(", "def set_box_open(")
    assert "if job.wait(logic.WAIT_WINDOW_S" in wait and "while not job.finished():" in wait
    assert "ef.Keys.Escape and cancellable" in wait and "e.Cancel = not job.finished()" in wait
    assert wait.index("finally:") < wait.index("form.Close")             # closed on every way out of the loop
    box = part(UI, "def start_box(", "\ndef ")
    assert 'status["label"].Text = progress()' in box
    assert "lookup_cancel" in part(RHINO, "def _one_pick(", "def _pick_outcome(")
    loop = part(RHINO, "def _box_loop(", "# ---- the address lookup")
    assert 'ticked = logic.ticks_after_pick(what, ticked, (saved_ui.get("_lookup") or {}).get("status"),' in loop
    assert "logic.box_moved(facts_before, ui_before, facts, saved_ui))" in loop
    assert "before_lookup" not in loop


# ---- Rhino run of aea73b8 (#32) and a3eb1d7 (#33): a frozen wait window, and Draw again after a Cancel ------------

def test_the_wait_window_never_depends_on_a_modal_session_or_a_timer():
    """In Rhino (Mac) a wait window froze at its first frame ("○●○ 0 s") with a closed dialog still painted behind
    it, right after a modal dialog was ended from a timer: its timer never ran. The wait is now a plain window that
    the waiting loop itself keeps current while Rhino runs (RhinoApp.Wait between passes): no ShowModal, no UITimer,
    nothing to deadlock on, whatever modal state Rhino is in."""
    wait = part(UI, "def wait(", "def set_box_open(")
    assert "ShowModal" not in wait and "UITimer" not in wait and "ef.Dialog" not in wait
    loop = wait[wait.index("while not job.finished():"):wait.index("finally:")]
    assert loop.index("Rhino.RhinoApp.Wait()") < loop.index("step.Text = job.step") < \
        loop.index("line.Text = logic.progress_line(job.elapsed(), limit)")   # set by the loop, every pass
    assert "form.Show()" in wait and "form.Topmost = True" in wait


def test_nothing_starts_a_second_piece_of_work_while_gordium_waits():
    said = []
    ran = []
    acts = logic.busy_actions({"report": lambda: ran.append("report"), "legend": lambda: ran.append("legend")},
                              lambda: True, said.append)
    acts["report"]()
    acts["legend"]()                                   # only shows something: allowed
    assert ran == ["legend"] and said == [logic.WORKING]
    calm = logic.busy_actions({"report": lambda: ran.append("report")}, lambda: False, said.append)
    calm["report"]()
    assert ran == ["legend", "report"]
    actions = part(RHINO, "def _actions(", "def PANEL_ACTIONS(")
    assert 'logic.busy_actions(logic.gate_actions(PANEL_ACTIONS(), _box_open, say)' in actions
    assert 'STATE.get("asking") is not None' in actions
    ask = part(RHINO, "def ask(", "def _ask_job(")
    assert ask.index('if STATE.get("asking") is not None:') < ask.index("raise RuntimeError(logic.WORKING)") < \
        ask.index("_settle_live()") < ask.index("_ask_job(")


def test_no_check_starts_while_a_start_box_is_open():
    """A check asked for while the box is open waits until it closes (Edit site's own check runs after its box)."""
    assert not logic.allowed("check", True) and logic.allowed("check", False)
    assert not logic.should_recheck(10.0, 20.0, False, True, 0.5)            # live mode: the box open
    for fn in ("def run_check(", "def _check_live("):
        body = part(RHINO, fn, "\ndef ")
        assert body.index('logic.allowed("check", _box_open())') < body.index("_check_begin(")
    edit = part(RHINO, "def edit_facts(", "def report_path(")
    assert edit.index("_end_undo(doc)") < edit.index("run_check(doc, report=False)")   # after the box, never in it


def test_a_cancelled_gordiumstart_leaves_nothing_behind():
    """Rhino run of aea73b8: after a cancelled Draw, GordiumStart again drew no house: the sample lot put down before
    the box (outside the box's session) stayed, with no facts, and was taken for the architect's own lot. Since the
    start flow (Ben, 2026-10-27) an empty file gets an empty box and nothing is put down before it; the take-back stays
    for anything that is."""
    start = part(RHINO, "def gordium_start(", "def _take_back_sample(")
    assert "_add_lot(doc, sample)" not in start and "sample_site" not in start
    assert start.index("drawn = True") < start.index("save_facts(doc, facts)")
    fin = start[start.index("    finally:"):]
    assert "if put_down is not None and not drawn:" in fin and "_take_back_sample" in fin
    back = part(RHINO, "def _take_back_sample(", "def _start_request(")
    assert "table.delete(lot_id)" in back and "doc.Strings.Delete(SECTION, UI_ENTRY)" in back
    assert "_save_ui_state(doc, json.loads(ui_before))" in back and "remove_layer_if_empty" in back


# ---- review round 1: each confirmed finding, pinned ----------------------------------------------------------------

def test_r1_p1_nothing_is_drawn_as_checked_while_a_background_recheck_runs():
    """Live mode clears the pending edit when it starts the re-check; the result on screen is of the model before the
    edit, so it is out of date for as long as the re-check runs (it was drawn as current: a false pass on screen)."""
    assert logic.result_stale(None, 5.0, 20.0, 0.3, rechecking=True)
    assert not logic.result_stale(None, 5.0, 20.0, 0.3, rechecking=False)
    assert logic.result_stale(10.0, 5.0, 10.5, 0.3, rechecking=False)          # edited, not checked since
    assert not logic.result_stale(10.0, 5.0, 10.1, 0.3, rechecking=False)      # (only after a moment)
    assert not logic.result_stale(10.0, 11.0, 12.0, 0.3, rechecking=False)     # checked since the edit
    stale = part(RHINO, "def stale(", "def draw_scene(")
    assert 'STATE.get("live_check") is not None' in stale and "logic.result_stale(" in stale


def test_r1_p2_only_a_box_whose_caller_draws_the_house_asks_for_one():
    assert logic.plans_house("start", False, False)
    assert logic.plans_house("check", True, True)                  # Edit site…, a new address drawn clean
    assert not logic.plans_house("check", True, False)             # GordiumCheck's box: never draws a house
    assert not logic.plans_house("check", False, True)
    drawn = part(RHINO, "def _drawn(", "def hide_massing(")
    assert 'logic.plans_house(mode, STATE.get("redraw_house"), STATE.get("house_after_box"))' in drawn
    edit = part(RHINO, "def edit_facts(", "def report_path(")
    assert edit.index('STATE["house_after_box"] = True') < edit.index("facts = confirm(")
    # review round 2: a flag an earlier box (GordiumCheck's) left set never draws a house over the architect's model
    assert edit.index('STATE.pop("redraw_house", None)') < edit.index("facts = confirm(")
    assert 'STATE.pop("house_after_box", None)' in edit
    assert "house_after_box" not in part(RHINO, "def gordium_check(", "def _layer(")


def test_r1_p2_a_check_the_architect_starts_shows_its_line_in_the_panel():
    run = part(RHINO, "def run_check(", "def _check_begin(")
    assert "tick = lambda job: ui.follow(p, job)" in run
    follow = part(UI, "def follow(", "def wait(")
    assert "show(parts, None, checking=True, job=job)" in follow and "show_progress(parts, job)" in follow
    assert 'parts["progress_label"], parts["progress_job"] = None, job' in UI


def test_r2_p2_waiting_for_a_background_recheck_never_starts_or_drops_another():
    settle = part(RHINO, "def _settle_live(", "# ---- \"now fails\"")
    assert "while STATE.get(\"live_check\") is not None:" in settle and 'STATE["asking"] = job' in settle
    assert settle.index('STATE["asking"] = job') < settle.index("ui.wait(job") < settle.index('STATE.pop("asking"')
    assert 'STATE["live_check"]["job"] is job' in settle
    finish = part(RHINO, "def _live_finish(", "def _settle_live(")
    assert finish.index('not running["job"].finished()') < finish.index('STATE.pop("live_check", None)')


def test_r2_p3_a_dropped_answer_keeps_the_screen_out_of_date_until_the_next_check():
    finish = part(RHINO, "def _live_finish(", "def _settle_live(")
    assert 'STATE["recheck_owed"] = True' in finish
    assert 'bool(STATE.get("recheck_owed"))' in part(RHINO, "def stale(", "def draw_scene(")
    assert 'STATE.pop("recheck_owed", None)' in part(RHINO, "def _check_apply(", "def _check_failed(")


def test_r1_p3_a_cancelled_background_recheck_clears_the_screen_at_once():
    finish = part(RHINO, "def _live_finish(", "def _settle_live(")
    cancelled = finish[finish.index("except logic.WorkCancelled:"):finish.index("except Exception as e:")]
    assert "_check_cancelled(doc, o)" in cancelled and "doc.Views.Redraw()" in cancelled


def test_r1_p3_a_background_recheck_never_waits_on_rhinos_thread_for_the_facts():
    live = part(RHINO, "def _check_live(", "def _live_tick(")
    assert "_read_facts(doc)" in live and "facts_first=facts" in live and "current_facts(" not in live
    job = part(RHINO, "def _ask_job(", "def _answer(")
    assert '{"cmd": "facts", "facts": facts_first' in job and '"error": UNREADABLE}' in job
    assert job.index('logic.exchange(sends, lines, first') < job.index("logic.exchange(sends, lines, request")


# ---- review of 9a4eee2 (the wait no longer modal): edits, another document, Esc and commands during a wait ----------

def test_an_answer_for_a_model_no_longer_in_front_is_never_shown_as_current():
    """Rhino runs during the wait, so the architect can edit or bring another file to the front: the answer, about
    the model as it was read, is then dropped (its own document says why, with Retry, and is checked again); a report
    written meanwhile is said to be of the model as it was; a house worked out meanwhile is never drawn."""
    ask = part(RHINO, "def ask(", "def _edited(")  # (ask, then _edited)
    assert ask.index("_watch_edits(True)") < ask.index("ui.wait(") < ask.index("_watch_edits(False)")
    watch = part(RHINO, "def _watch_edits(", "def _changed_during(")
    for event in ("AddRhinoObject", "DeleteRhinoObject", "UndeleteRhinoObject", "ReplaceRhinoObject",
                  "ModifyObjectAttributes"):
        assert event in watch
    changed = part(RHINO, "def _changed_during(", "def _ask_job(")
    assert "front.RuntimeSerialNumber != doc_serial" in changed and "logic.checked_while_still(read_at" in changed
    run = part(RHINO, "def run_check(", "def _check_begin(")
    assert run.index('if _changed_during(begun["doc"], begun["at"]):') < \
        run.index("_check_outdated(doc, o, report, begun, result)") \
        < run.index("return _check_apply(")
    outdated = part(RHINO, "def _check_outdated(", "def _check_cancelled(")
    assert outdated.index("front.RuntimeSerialNumber != doc.RuntimeSerialNumber") < outdated.index("ui.show(")
    assert "_check_apply" not in outdated and 'STATE["recheck_owed"] = True' in outdated
    assert "logic.outdated_report_message(" in outdated
    plan = part(RHINO, "def _plan_house(", "def _draw_starting_house(")
    assert plan.index("ask(request, cancel=True)") < plan.index("_changed_during(") < plan.index("logic.ModelChanged()")
    report = part(RHINO, "def open_report(", "def _drop_report_part(")
    assert report.index('get("outdated")') < report.index("ui.open_target(path)")
    assert issubclass(logic.ModelChanged, logic.WorkCancelled) and logic.ModelChanged.said == logic.DRAW_OUTDATED


def test_esc_stops_the_work_only_from_the_wait_window_and_commands_wait_their_turn():
    """Coordinator's decision (2026-10-26, Ben may override): Esc cancels Gordium's work only with the wait window in
    front (or Cancel clicked); an Esc elsewhere keeps Rhino's own meaning (end a command, clear a selection) and never
    silently cancels a check or a Draw. The window says so."""
    wait = part(UI, "def wait(", "def set_box_open(")
    assert "EscapeKeyPressed" not in wait                                   # never Rhino-wide
    assert "form.KeyDown += logic.guard(key" in wait and "e.Key == ef.Keys.Escape and cancellable" in wait
    assert "layout.AddRow(row(stop, hint))" in wait and logic.STOP_HINT == "Esc or Cancel to stop"
    # Esc is promised only while the window has the keyboard (Rhino run of 65c07d7: the Mac gave it no focus)
    assert "hint = label(logic.STOP_HINT_CLICK" in wait and "take_keyboard(form)" in wait
    assert "hint.Text = logic.STOP_HINT if focused else logic.STOP_HINT_CLICK" in wait
    keys = part(UI, "def take_keyboard(", "def has_keyboard(")
    assert "form.Focus()" in keys and "MakeKeyAndOrderFront" in keys
    assert "IsKeyWindow" in part(UI, "def has_keyboard(", "def wait(")
    assert "EscapeKeyPressed" not in RHINO
    for fn in ("def gordium_check(", "def gordium_start(", "def edit_facts(", "def off("):
        body = part(RHINO, fn, "\ndef ")
        gate = body.index('if STATE.get("asking") is not None:')
        assert gate < 700 and body.index("say(logic.WORKING)", gate) < body.index("return", gate), fn   # first thing


# ---- review of 5567b94 ---------------------------------------------------------------------------------------------

def test_every_kind_of_edit_is_noted_and_the_wait_never_leaves_work_behind():
    watch = part(RHINO, "def _watch_edits(", "def _changed_during(")
    for event in ("LayerTableEvent", "InstanceDefinitionTableEvent", "DocumentPropertiesChanged"):
        assert '("%s",' % event in watch, event                     # layers, blocks, units sort lot and building
    ask = part(RHINO, "def ask(", "def _edited(")
    assert ask.index("try:") < ask.index("_watch_edits(True)")       # inside the try: asking always cleared
    fin = ask[ask.index("finally:"):]
    assert fin.index('STATE.pop("asking", None)') < fin.index("if not job.finished():") < fin.index("_stop_worker()")
    house = part(RHINO, "def _draw_starting_house(", "def _doc_name(")
    fallback = house[house.index("start = ask(request)  "):]
    assert fallback.index("_changed_during(doc.RuntimeSerialNumber, read_at)") < fallback.index("logic.HOUSE_OUTDATED")
    # its message promises the house drawn by hand is checked: live mode and the document hooks on (review of e101ec5)
    early = fallback[fallback.index("logic.HOUSE_OUTDATED"):fallback.index("return None")]
    assert "live(True)" in early and "documents(True)" in early
    assert "Zoning report… was pressed" not in logic.REPORT_OUTDATED     # GordiumCheck says it too


def test_commands_ask_the_checker_before_they_read_the_model():
    """Review of 0702d50: Rhino runs during a wait, so whatever a command read of the model before one may be out of
    date after it (a building drawn meanwhile got a starting house beside it; another file came to the front)."""
    start = part(RHINO, "def gordium_start(", "def _take_back_sample(")
    assert start.index('ask({"cmd": "options"') < start.index("doc = Rhino.RhinoDoc.ActiveDoc") < \
        start.index("if _buildings(doc):")
    assert start.count("ask(") == 1            # (an empty file no longer asks for the sample: the start flow)
    own = start[start.index("    else:                               # the architect's own lot"):start.index("drawn = False")]
    assert own.index("current_facts(doc)") < own.index("except logic.NotInFront:") < own.index("if _buildings(doc):")
    for fn, end in (("def gordium_check(", "def _layer("), ("def edit_facts(", "def report_path(")):
        body = part(RHINO, fn, end)
        assert body.index('ask({"cmd": "options"') < body.index("doc = Rhino.RhinoDoc.ActiveDoc"), fn
        assert body.index("current_facts(doc)") < body.index("except logic.NotInFront:") < body.index("confirm("), fn
    front = part(RHINO, "def _still_front(", "def _edited(")
    assert "front.RuntimeSerialNumber == doc.RuntimeSerialNumber" in front


def test_the_saved_facts_are_matched_to_the_model_as_it_is_after_their_wait():
    """Cold check of 15d0894: current_facts listed the lots and buildings, then waited on the checker (load_facts),
    then dropped stale ids against the list from before the wait."""
    facts = part(RHINO, "def current_facts(", "def save_facts(")
    assert facts.index("load_facts(doc)") < facts.index("_sorted_objects(doc)") < facts.index("logic.drop_stale(")



# ---- independent review of #32 (aea73b8..6ba061b): five confirmed, pinned --------------------------------------------

def test_ir1_an_outdated_check_never_says_a_report_was_written_when_it_wasnt():
    said = logic.outdated_report_message("/x/r.xlsx", "Permission denied", True)
    assert said == logic.report_message("/x/r.xlsx", False, "Permission denied", stale=True)
    assert "is of the model as it was" not in said
    assert logic.outdated_report_message("/x/r.xlsx", None, False) == logic.REPORT_OUTDATED.format(path="/x/r.xlsx")
    outdated = part(RHINO, "def _check_outdated(", "def _check_cancelled(")
    assert 'logic.outdated_report_message(report_path(doc), (result or {}).get("report_error")' in outdated


def test_ir2_every_reader_of_the_facts_stops_when_its_file_is_no_longer_in_front():
    facts = part(RHINO, "def current_facts(", "def save_facts(")
    assert facts.index("load_facts(doc)") < facts.index("if not _still_front(doc):") < \
        facts.index("raise logic.NotInFront(logic.NOT_IN_FRONT)") < facts.index("_sorted_objects(doc)")
    said, ran = [], []
    acts = logic.front_actions({"enter": lambda: (_ for _ in ()).throw(logic.NotInFront(logic.NOT_IN_FRONT)),
                                "zoom": lambda: ran.append(1)}, said.append)
    assert acts["enter"]() is logic.REFUSED and said == [logic.NOT_IN_FRONT]
    acts["zoom"]()
    assert ran == [1]
    assert "logic.front_actions(logic.busy_actions(" in part(RHINO, "def _actions(", "def PANEL_ACTIONS(")
    for fn in ("def edit_facts(", "def gordium_check(", "def gordium_start("):
        body = part(RHINO, fn, "\ndef ")
        handler = body.index("except logic.NotInFront:")
        assert body.index("say(logic.NOT_IN_FRONT)", handler) < body.index("return None", handler), fn


def test_ir3_no_undo_step_of_gordiums_is_held_open_while_it_waits():
    """Rhino runs during a wait: an undo step held open across it would take the architect's own edits into
    Gordium's. A new address's house is worked out before the step opens; ask() ends any step this script holds."""
    prepare = part(RHINO, "def _draw_prepare(", "def _begin_undo(")
    assert prepare.index('STATE["start_plan"] = _plan_reset_house(') < prepare.index("_begin_undo(doc,")
    ask = part(RHINO, "def ask(", "def _ask_job(")
    assert ask.index('held = STATE.get("undo")') < ask.index("_end_undo(") < ask.index("_settle_live()")
    plan = part(RHINO, "def _plan_reset_house(", "def _export_lot(")
    assert "logic.apply_reset(dry, _DrySession()" in plan and "ask(request, cancel=True)" in plan
    assert plan.index("ask(request") < plan.index("logic.ModelChanged()")
    dry = part(RHINO, "class _DryTable", "class _DrySession")
    assert "def add_lot(self, ring, name):" in dry and "self.ring = ring" in dry and "return DRY_LOT" in dry
    key = part(RHINO, "def _start_key(", "DRY_LOT = ")
    assert 'k != "lot_id"' in key


def test_ir5_a_refused_checkbox_puts_its_tick_back():
    acts = logic.busy_actions({"labels": lambda on: "done"}, lambda: True, lambda text: None)
    assert acts["labels"](True) is logic.REFUSED
    tick = part(UI, "def _tick(", "def _massing_box(")
    assert "if action(bool(box.Checked)) is logic.REFUSED:" in tick and "box.Checked = not box.Checked" in tick
    for name in ("massing", "labels", "envelope"):
        assert '_tick(box, actions["%s"]' % name in UI, name


# ---- cold review of f51ed45 ----------------------------------------------------------------------------------------

def test_the_planned_house_is_worked_out_from_the_same_state_draw_uses():
    """P1: the dry plan used the box's old state, the real Draw the state rebuilt for the new lot (corner answer,
    survey, ground fall, address): the keys never matched, and the fallback split Draw's undo step."""
    prepare = part(RHINO, "def _draw_prepare(", "def _begin_undo(")
    assert "fresh_state = _reset_state(doc, facts, options, saved_ui, mode, state)" in prepare
    plan = part(RHINO, "def _plan_reset_house(", "def _export_lot(")
    assert "_apply_box(doc, f, _reset_state(doc, f, options, s, mode, state), s)" in plan
    assert 'logic.plans_house(mode, redraw and mode == "check", STATE.get("house_after_box"))' in plan
    drawn = part(RHINO, "def _drawn(", "def hide_massing(")
    assert 'logic.plans_house(mode, STATE.get("redraw_house"), STATE.get("house_after_box"))' in drawn
    # the reset's own fields come from what the reset left (fresh), the architect's choices from the box (shown)
    shown = {"zone": "R-1b", "district_confirmed": True, "corner_lot": None, "address": "1 Old St"}
    fresh = {"corner_lot": False, "address": "96 Ithaca Rd", "lot_surveyed": False, "ground_fall": 4}
    state = logic.after_reset_state(shown, fresh)
    assert state["corner_lot"] is False and state["address"] == "96 Ithaca Rd" and state["zone"] == "R-1b"


def test_whatever_gordium_draws_after_a_wait_is_in_an_undo_step_of_its_own():
    ask = part(RHINO, "def ask(", "def _ask_waiting(")
    assert 'resume = (doc, STATE.get("undo_words"))' in ask and "draws_after" not in ask   # whoever asked (review of 2781a5d)
    assert ask.index("_end_undo(doc)") < ask.index("return _ask_waiting(") < ask.index("_begin_undo(resume[0]")
    assert "ask(request, cancel=True)" in part(RHINO, "def _plan_house(", "def _draw_starting_house(")   # (the City-outline Draw's plan: resumed too)
    assert 'STATE["undo_words"] = words' in part(RHINO, "def _begin_undo(", "def _end_undo(")


def test_a_check_whose_file_left_the_front_is_out_of_date_never_could_not_run():
    run = part(RHINO, "def run_check(", "def _check_begin(")
    handler = run.index("except logic.NotInFront as e:")
    assert handler < run.index("_check_outdated(doc, o, report,", handler) < run.index("except Exception as e:")
    assert "{\"report_error\": str(e)}" in run    # the check never began: no report written, said so


def test_a_box_open_refusal_also_puts_the_tick_back():
    acts = logic.gate_actions({"labels": lambda on: "done"}, lambda: True, lambda text: None)
    assert acts["labels"](True) is logic.REFUSED


# ---- independent review of 6ba061b..2781a5d ------------------------------------------------------------------------

def test_r2_unreadable_facts_never_skip_the_front_check():
    """P1: load_facts raised ValueError (unreadable) before the front check; the callers turned it into {} and
    opened the box on a file no longer in front. The check runs on every way out."""
    facts = part(RHINO, "def current_facts(", "def save_facts(")
    try_at = facts.index("    try:\n        facts = load_facts(doc)")
    assert try_at < facts.index("    finally:") < facts.index("if not _still_front(doc):") < \
        facts.index("raise logic.NotInFront(logic.NOT_IN_FRONT)")


def test_r2_every_command_that_opens_a_box_ends_its_undo_step_before_the_check():
    """Cold review of d7a5675: GordiumCheck's box could reset (an undo step begun) and nothing ended the step; ask now
    begins it again after every wait, so it would stay open for the architect's own edits."""
    for fn, end in (("def gordium_check(", "def _layer("), ("def edit_facts(", "def report_path(")):
        body = part(RHINO, fn, end)
        assert body.index("confirm(") < body.index("_end_undo(doc)") < body.index("run_check(doc"), fn
        assert body.rindex("finally:", 0, body.index("_end_undo(doc)")) > body.index("confirm("), fn
    start = part(RHINO, "def gordium_start(", "def _take_back_sample(")
    assert "_end_undo(doc)" in start[start.index("    finally:"):]



# ---- review of #32's Cancel lookup (2026-10-28): a district tick never moves to a district changed meanwhile ------

LIVE = "suggested by Gordium · City zoning map, used live"


def test_look_up_and_cancel_lookup_keep_the_ticks_as_the_box_shows_them():
    """The district, use, address and corner answer stay usable while a lookup runs. Cancel lookup put back every
    tick and source from before Look up, so a district ticked on R-1b and changed to R-3a during the lookup came
    back ticked on R-3a with the lookup's "suggested" source: Draw on for a district never confirmed, and a false
    source saved into the file. Look up and Cancel lookup now keep the ticks as the box shows them; only a lookup's
    answer replaces them (the district confirmed again)."""
    now = {"district_confirmed": False, "zone_source": logic.ENTERED, "use_source": LIVE, "address_source": LIVE,
           "corner_source": LIVE, "checked": ["street"]}
    assert logic.ticks_after_pick("pick:lookup_cancel", now) == now        # never the ticks from before Look up
    assert logic.ticks_after_pick("pick:lookup", now) == now               # the box shows the architect's own
    fresh = {"district_confirmed": False}           # replaced: the district confirmed again, never the file's tick
    assert logic.ticks_after_pick("pick:lookup_done", now, "found", False) == fresh == \
        logic.ticks_after_pick("pick:use_saved", now, "found", False)
    for status in ("not_found", "offline", "outside_city", "timeout", "error", None):    # filled nothing: as shown
        assert logic.ticks_after_pick("pick:lookup_done", now, status, False) == now, status
        assert logic.ticks_after_pick("pick:lookup_done", now, status, True) == fresh, status   # unless it moved
    assert logic.ticks_after_pick("pick:use_saved", now, "offline", False) == now        # a saved one refused
    assert logic.ticks_after_pick("pick:lookup_done", now, "offline") == fresh           # (not known: replaced)
    # what moves the box: a field, the doubts, or an earlier preview put back (round 4: drop_pending)
    pending = {"address": "106 Ithaca Rd"}
    assert not logic.box_moved({"zone": "R-1b"}, {"_pending": pending}, {"zone": "R-1b"}, {"_pending": pending})
    assert logic.box_moved({"zone": "R-1b"}, {}, {"zone": "R-3a"}, {})
    assert logic.box_moved({}, {"doubts": {"lot": "a"}}, {}, {})
    assert logic.box_moved({}, {"_pending": pending}, {}, {})
    assert logic.ticks_after_pick("pick:street", now) == now and logic.ticks_after_pick("pick:lookup", None) == {}
    assert logic.box_ticks(dict(now, zone="R-3a", _draw_label="Draw")) == now


def _run_box_loop(script, confirmed_at_draw=None, answer="found", box_pick=None, facts=None, saved_ui=None):
    """gordium_rhino._box_loop itself, run with the box replaced by `script`: one (change, what) per showing of the
    box, `change` applied to what the box shows as the architect would (ui.start_box's keep()). Returns each state
    the box was shown with."""
    import ast
    tree = ast.parse(RHINO)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_box_loop")
    shown, steps = [], list(script)

    def start_box(state, options, mode):
        shown.append(dict(state))
        change, what = steps.pop(0)
        state.update(change)
        return what

    def box_state(doc, facts, options, saved_ui, mode):     # the box as the file and the session's choices say it
        return {"zone": facts["zone"], "zone_source": saved_ui.get("zone_source", LIVE),
                "district_confirmed": facts["zone"] == confirmed_at_draw     # (_box_state: a Draw's, unchanged,
                and not saved_ui.get("_reconfirm"),                          # unless a lookup filled the box)
                "use": "one_family", "use_source": LIVE, "address": "106 Ithaca Rd", "address_source": LIVE,
                "corner_lot": False, "corner_source": LIVE, "checked": list(saved_ui.get("checked") or []),
                "doubts": {"lot": "The tax map's outline may be off."}}

    def apply_box(doc, facts, state, saved_ui):
        return dict(facts, zone=state["zone"]), dict(logic.saved_sources(saved_ui, state),
                                                     checked=list(state.get("checked") or []))

    ns = {"STATE": {}, "logic": logic, "GUIDE_KEEPS": (), "ui": type("UI", (), {"start_box": staticmethod(start_box)}),
          "_box_state": box_state, "_apply_box": apply_box,
          "_box_pick": box_pick or (lambda doc, what, facts, saved_ui, session: (
              (facts, dict(saved_ui, _lookup={"status": answer}, **({"_reconfirm": True} if answer == "found" else {})))
              if what == "lookup_done" else (facts, saved_ui)))}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), host_path("rhino", "plugin").name, "exec"), ns)
    assert ns["_box_loop"](None, facts or {"zone": "R-1b"}, {}, "check", saved_ui or {}, None) is None
    return shown


def test_the_box_loop_after_cancel_lookup_never_ticks_a_district_changed_meanwhile():
    """The reviewer's case, through the box loop itself: R-1b ticked, Look up, the district changed to R-3a while it
    runs and the tick taken off (entered by you), Cancel lookup. The box then showed R-3a ticked, "suggested by
    Gordium · City zoning map, used live", and Draw on."""
    shown = _run_box_loop([({"district_confirmed": True}, "pick:lookup"),
                           ({"zone": "R-3a", "district_confirmed": False, "zone_source": logic.ENTERED},
                            "pick:lookup_cancel"),
                           ({}, None)])
    after = shown[-1]
    assert (after["zone"], after["district_confirmed"], after["zone_source"]) == ("R-3a", False, logic.ENTERED)
    # the district unchanged: the tick shows all along, and stays after Cancel lookup
    shown = _run_box_loop([({"district_confirmed": True}, "pick:lookup"), ({}, "pick:lookup_cancel"), ({}, None)])
    assert [s["district_confirmed"] for s in shown] == [False, True, True]
    # "I checked this" ticked, Look up, taken off while it runs, Cancel lookup: it stays off (review round 1: the
    # doubt counted as settled though the architect had withdrawn the tick)
    shown = _run_box_loop([({"checked": ["lot"]}, "pick:lookup"), ({"checked": []}, "pick:lookup_cancel"),
                           ({}, None)])
    assert shown[1]["checked"] == ["lot"] and shown[-1]["checked"] == []
    assert logic.unsettled({"doubts": shown[-1]["doubts"], "checked": shown[-1]["checked"]})   # still a doubt
    # Edit site… (R-1b confirmed at an earlier Draw): unticked during the lookup, stays off; left ticked, stays on
    shown = _run_box_loop([({}, "pick:lookup"), ({"district_confirmed": False}, "pick:lookup_cancel"), ({}, None)],
                          confirmed_at_draw="R-1b")
    assert [s["district_confirmed"] for s in shown] == [True, True, False]
    shown = _run_box_loop([({}, "pick:lookup"), ({}, "pick:lookup_cancel"), ({}, None)], confirmed_at_draw="R-1b")
    assert shown[-1]["district_confirmed"] is True
    # ticked during the lookup, a pick, taken off, Cancel lookup in a later showing: off, as the architect left it
    # (review round 2)
    shown = _run_box_loop([({"district_confirmed": True}, "pick:lookup"), ({"district_confirmed": True}, "pick:street"),
                           ({"district_confirmed": False}, "pick:street"), ({}, "pick:lookup_cancel"), ({}, None)])
    assert [s["district_confirmed"] for s in shown] == [False, True, True, False, False]
    # Edit site…: taken off, Look up, R-3a picked during the lookup, Cancel lookup: the box never showed the tick
    # again, so R-3a is never confirmed (review round 3, P0: the box showed the earlier Draw's tick while looking,
    # and it was kept on R-3a)
    shown = _run_box_loop([({"district_confirmed": False}, "pick:lookup"),
                           ({"zone": "R-3a", "zone_source": logic.ENTERED}, "pick:lookup_cancel"), ({}, None)],
                          confirmed_at_draw="R-1b")
    assert [(s["zone"], s["district_confirmed"]) for s in shown] == [("R-1b", True), ("R-1b", False),
                                                                    ("R-3a", False)]
    # a lookup's answer that filled the box replaces them: the district confirmed again
    shown = _run_box_loop([({"district_confirmed": True}, "pick:lookup"), ({}, "pick:lookup_done"), ({}, None)])
    assert shown[-1]["district_confirmed"] is False
    # Edit site…: taken off, Look up, and the lookup finds nothing (offline, not found, too slow): the box is as the
    # architect left it, never the earlier Draw's tick shown again (review round 3's sceptics)
    for status in ("offline", "not_found", "timeout"):
        shown = _run_box_loop([({"district_confirmed": False}, "pick:lookup"), ({}, "pick:lookup_done"), ({}, None)],
                              confirmed_at_draw="R-1b", answer=status)
        assert [s["district_confirmed"] for s in shown] == [True, False, False], status


def test_r2_a_report_not_written_after_a_file_switch_is_said_with_one_full_stop():
    said = logic.outdated_report_message("/x/r.xlsx", logic.NOT_IN_FRONT, True)
    assert ".." not in said and said.startswith("Zoning report not saved")


def test_a_second_lookup_that_finds_nothing_never_keeps_a_tick_on_the_district_it_puts_back(monkeypatch):
    """Review round 4 of #32 (P0): Edit site… on R-3a (entered by you); Look up finds 106 Ithaca Rd and suggests
    R-1b; the architect ticks it; a second Look up answers offline (or not found, or too slow). That answer puts the
    first preview back (drop_pending: R-3a, entered by you), and the kept ticks landed on it: R-3a ticked "suggested
    by Gordium · City zoning map", Draw on. A lookup's answer that moved the box empties the ticks."""
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent))
    from test_lookup_box import ZONES, looked_up
    for second in ("offline", "not_found", "timeout"):
        answers = [looked_up("106_ithaca_rd"), {"status": second, "query": "106 Ithaca Rd"}]

        def box_pick(doc, what, facts, saved_ui, session):
            if what == "lookup":
                return facts, dict(saved_ui, _lookup={"looking": "106 Ithaca Rd"})
            if what == "lookup_done":
                facts, saved_ui, _ = logic.preview_lookup(answers.pop(0), facts, saved_ui, ZONES)
            return facts, saved_ui

        shown = _run_box_loop([({}, "pick:lookup"), ({}, "pick:lookup_done"),
                               ({"district_confirmed": True}, "pick:lookup"), ({}, "pick:lookup_done"), ({}, None)],
                              box_pick=box_pick, facts={"zone": "R-3a", "address": "1 Other St"},
                              saved_ui={"zone_source": logic.ENTERED})
        assert shown[2]["zone"] == "R-1b" and shown[3]["district_confirmed"] is True        # ticked on R-1b
        last = shown[-1]
        assert (last["zone"], last["district_confirmed"]) == ("R-3a", False), (second, last)
        assert last["zone_source"] == logic.ENTERED, (second, last)
        # the same with R-3a confirmed at an earlier Draw and taken off before the first Look up: never ticked
        # again from the file when the preview is put back (sceptic of round 4)
        answers[:] = [looked_up("106_ithaca_rd"), {"status": second, "query": "106 Ithaca Rd"}]
        shown = _run_box_loop([({"district_confirmed": False}, "pick:lookup"), ({}, "pick:lookup_done"),
                               ({}, "pick:lookup"), ({}, "pick:lookup_done"), ({}, None)],
                              box_pick=box_pick, facts={"zone": "R-3a", "address": "1 Other St"},
                              saved_ui={"zone_source": logic.ENTERED}, confirmed_at_draw="R-3a")
        assert (shown[-1]["zone"], shown[-1]["district_confirmed"]) == ("R-3a", False), (second, shown[-1])
        # the district unchanged by the preview (same district): the "suggested" source and the tick given on it
        # go when the preview is put back (sceptic of round 4)
        answers[:] = [looked_up("106_ithaca_rd"), {"status": second, "query": "106 Ithaca Rd"}]
        shown = _run_box_loop([({}, "pick:lookup"), ({}, "pick:lookup_done"),
                               ({"district_confirmed": True}, "pick:lookup"), ({}, "pick:lookup_done"), ({}, None)],
                              box_pick=box_pick, facts={"zone": "R-1b", "address": "106 Ithaca Rd"},
                              saved_ui={"zone_source": logic.ENTERED})
        assert shown[2]["zone"] == "R-1b" and shown[2]["zone_source"] != logic.ENTERED      # the preview's
        assert (shown[-1]["district_confirmed"], shown[-1]["zone_source"]) == (False, logic.ENTERED), (second,
                                                                                                    shown[-1])


def test_a_background_check_of_the_file_in_front_covers_the_edits_before_it_so_cancel_stays_cancelled():
    """Demo 7 Rhino run (2026-10-28, progress_cancel claim 5): with Check after every edit on, an edit, then the
    background check of the file come to the front (check_front) read the model, edit included; Cancel; and at the
    next idle a second check started at once, because the edit still counted as unchecked. A check that reads the model
    covers every edit made before it, as live mode's own re-check does (it clears the mark as it starts): Cancel then
    stays cancelled until the next edit (and the panel says so: never a result shown as current)."""
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location("_test_check_harness", pathlib.Path(__file__).with_name("test_check.py"))
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    _plugin_functions = harness._plugin_functions
    started = []
    front = type("Doc", (), {"RuntimeSerialNumber": 7,
                             "Strings": type("S", (), {"GetValue": staticmethod(lambda section, key: "{}")})()})()
    ns = _plugin_functions(["_idle"], _box_open=lambda: False, _auto=lambda doc: True, IDLE_SECONDS=0.5,
                           SECTION="gordium", ENTRY="lot_facts", _redraw=lambda: None,
                           _check_live=lambda doc: started.append(doc))
    ns["Rhino"].RhinoDoc.ActiveDoc = front
    now = ns["time"].time()
    ns["STATE"].update(check_front=True, dirty=now - 2.0)      # the file came to the front; an edit since
    ns["_idle"](None, None)
    assert started == [front]                                   # the file in front checked, the edit with it
    ns["STATE"]["running"] = False                              # ... and that check cancelled (nothing running)
    ns["_idle"](None, None)
    assert started == [front], "Cancel was undone: a second check started for an edit the first one had read"
    ns["STATE"]["dirty"] = ns["time"].time() - 1.0              # a new edit: checked again, as live mode does
    ns["_idle"](None, None)
    assert started == [front, front]
