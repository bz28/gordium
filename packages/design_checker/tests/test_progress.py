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
from site_lookup.lookup import STEPS as LOOKUP_STEPS, lookup

SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
MODEL = SITE / "spreadsheet_design_model.3dm"
RHINO = (REPO / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
UI = (REPO / "apps/rhino_plugin/gordium_ui.py").read_text(encoding="utf-8")


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

    def fake_check(model, facts, report=None, problems=None, extras=None, step=None):
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
    for caller in ("def ask(", "def run_check(", "def open_report(", "def confirm("):
        assert "_settle_live()" in part(RHINO, caller, "\ndef "), caller


def test_draw_works_out_the_starting_house_before_anything_is_saved_or_committed():
    drawn = part(RHINO, "def _drawn(", "def hide_massing(")
    assert drawn.index('STATE["start_plan"] = _plan_house(') < drawn.index("_save_ui_state(doc, ui_state)") < \
        drawn.index("doc.Strings.SetString") < drawn.index("logic.draw_then_commit(session, save)")
    plan = part(RHINO, "def _plan_house(", "def _draw_starting_house(")
    assert "ask(request, cancel=True)" in plan
    house = part(RHINO, "def _draw_starting_house(", "def _doc_name(")
    assert 'plan["key"] == _start_key(request)' in house and "start = ask(request)  " in house   # committed: no Cancel
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
    assert 'before_lookup, ticked = ticked, {}' in loop and 'ticked = before_lookup' in loop


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


def test_a_cancelled_gordiumstart_takes_back_the_sample_it_put_down():
    """Rhino run of aea73b8: after a cancelled Draw, GordiumStart again drew no house: the sample lot put down before
    the box (outside the box's session) stayed, with no facts, and was taken for the architect's own lot."""
    start = part(RHINO, "def gordium_start(", "def _take_back_sample(")
    assert start.index("put_down = (doc.Strings.GetValue(SECTION, UI_ENTRY)") < start.index("_add_lot(doc, sample)")
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
    assert run.index('if _changed_during(begun["doc"], begun["at"]):') < run.index("_check_outdated(doc, o, report)") \
        < run.index("return _check_apply(")
    outdated = part(RHINO, "def _check_outdated(", "def _check_cancelled(")
    assert outdated.index("front.RuntimeSerialNumber != doc.RuntimeSerialNumber") < outdated.index("ui.show(")
    assert "_check_apply" not in outdated and 'STATE["recheck_owed"] = True' in outdated
    assert "logic.REPORT_OUTDATED" in outdated
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
    assert "layout.AddRow(row(stop, label(logic.STOP_HINT" in wait and logic.STOP_HINT == "Esc or Cancel to stop"
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
    fallback = house[house.index("start = ask(request)"):]
    assert fallback.index("_changed_during(doc.RuntimeSerialNumber, read_at)") < fallback.index("logic.HOUSE_OUTDATED")
    # its message promises the house drawn by hand is checked: live mode and the document hooks on (review of e101ec5)
    early = fallback[fallback.index("logic.HOUSE_OUTDATED"):fallback.index("return None")]
    assert "live(True)" in early and "documents(True)" in early
    assert "Zoning report… was pressed" not in logic.REPORT_OUTDATED     # GordiumCheck says it too


def test_commands_ask_the_checker_before_they_read_the_model():
    """Review of 0702d50: Rhino runs during a wait, so whatever a command read of the model before one may be out of
    date after it (a building drawn meanwhile got a starting house beside it; another file came to the front)."""
    start = part(RHINO, "def gordium_start(", "def _take_back_sample(")
    assert start.index('ask({"cmd": "options"') < start.index('ask({"cmd": "sample_site"})') < \
        start.index("doc = Rhino.RhinoDoc.ActiveDoc") < start.index("if _buildings(doc):")
    assert start.count("ask(") == 2 and 'facts["lot_id"] = sample_lot' in start
    own = start[start.index("    else:                               # the architect's own lot"):start.index("drawn = False")]
    assert own.index("current_facts(doc)") < own.index("_still_front(doc)") < own.index("if _buildings(doc):")
    for fn, end in (("def gordium_check(", "def _layer("), ("def edit_facts(", "def report_path(")):
        body = part(RHINO, fn, end)
        assert body.index('ask({"cmd": "options"') < body.index("doc = Rhino.RhinoDoc.ActiveDoc"), fn
        assert body.index("current_facts(doc)") < body.index("_still_front(doc)") < body.index("confirm("), fn
    front = part(RHINO, "def _still_front(", "def _edited(")
    assert "front.RuntimeSerialNumber == doc.RuntimeSerialNumber" in front
    assert RHINO.count("not _still_front(doc):") == RHINO.count("say(logic.NOT_IN_FRONT)") == 3   # each caller says it


def test_the_saved_facts_are_matched_to_the_model_as_it_is_after_their_wait():
    """Cold check of 15d0894: current_facts listed the lots and buildings, then waited on the checker (load_facts),
    then dropped stale ids against the list from before the wait."""
    facts = part(RHINO, "def current_facts(", "def save_facts(")
    assert facts.index("load_facts(doc)") < facts.index("_sorted_objects(doc)") < facts.index("logic.drop_stale(")
    start = part(RHINO, "def gordium_start(", "def _take_back_sample(")
    assert start.index("System.Guid.Empty") < start.index('facts["lot_id"] = sample_lot')
