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
    assert "except logic.WorkCancelled:" in start_cmd and "say(logic.DRAW_CANCELLED)" in start_cmd
    edit = part(RHINO, "def edit_facts(", "def report_path(")
    assert "except logic.WorkCancelled:" in edit


def test_a_cancelled_check_leaves_nothing_shown_as_checked():
    cancelled = part(RHINO, "def _check_cancelled(", "# ---- live mode's re-check")
    assert "_clear(o)" in cancelled and "cancelled=True" in cancelled and '"checked_at"' not in cancelled
    report = part(RHINO, "def open_report(", "def _drop_report_part(")
    assert report.index("_drop_report_part(path)") < report.index("logic.report_cancelled(")
    assert report.index("logic.report_cancelled(") < report.index("ui.open_target(path)")


def test_the_wait_window_closes_when_the_job_is_done_or_cancelled():
    wait = part(UI, "def wait(", "def set_box_open(")
    assert "if job.wait(logic.WAIT_WINDOW_S" in wait and "if job.finished():" in wait
    assert "dialog.AbortButton = stop" in wait and "e.Cancel = not job.finished()" in wait
    box = part(UI, "def start_box(", "\ndef ")
    assert 'status["label"].Text = progress()' in box
    assert "lookup_cancel" in part(RHINO, "def _one_pick(", "def _pick_outcome(")
    loop = part(RHINO, "def _box_loop(", "# ---- the address lookup")
    assert 'before_lookup, ticked = ticked, {}' in loop and 'ticked = before_lookup' in loop


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
    assert 'STATE.pop("house_after_box", None)' in edit
    assert "house_after_box" not in part(RHINO, "def gordium_check(", "def _layer(")


def test_r1_p2_a_check_the_architect_starts_shows_its_line_in_the_panel():
    run = part(RHINO, "def run_check(", "def _check_begin(")
    assert "tick = lambda job: ui.follow(p, job)" in run
    follow = part(UI, "def follow(", "def wait(")
    assert "show(parts, None, checking=True, job=job)" in follow and "show_progress(parts, job)" in follow
    assert 'parts["progress_label"], parts["progress_job"] = None, job' in UI


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
