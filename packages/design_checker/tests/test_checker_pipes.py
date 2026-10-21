"""The plugin's checker pipes never block the caller (Rhino's thread): a checker that never reads or answers, even
with a request far larger than a pipe's buffer, gives a clear error within the time limit; a slow one is still
answered. And an earlier copy of the plugin can't stay attached: sweep undoes what it left, current_only makes
its handlers inert. (2026-10-21: an orphaned copy read the checker's pipe on Rhino's thread and froze Rhino.)"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "design_checker"))
import rhino_logic as logic  # noqa: E402

SILENT = "import time; time.sleep(60)"                       # never reads stdin, never answers
SLOW = ("import json, sys, time\n"
        "for line in sys.stdin:\n"
        "    time.sleep(1.5)\n"
        "    print(json.dumps({'id': json.loads(line)['id'], 'ok': True, 'result': 'late'}), flush=True)\n")


def start(code):
    return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, universal_newlines=True, encoding="utf-8")


def test_a_silent_checker_and_a_huge_request_never_block_the_caller():
    p = start(SILENT)
    try:
        sends, lines = logic.pipes(p)
        request = {"id": 1, "cmd": "check", "model": "x" * 2_000_000}    # far beyond a pipe's 64 KB buffer
        outcome = []

        def caller():                          # stands in for Rhino's thread; a blocked write would never return
            try:
                logic.exchange(sends, lines, request, 2)
                outcome.append("answered")
            except logic.CheckerOutOfStep as e:
                outcome.append(str(e))
        t = threading.Thread(target=caller, daemon=True)
        began = time.monotonic()
        t.start()
        t.join(6)
        assert not t.is_alive(), "the caller was blocked on the pipe"
        assert outcome and "no answer in 2 s" in outcome[0] and time.monotonic() - began < 4
    finally:
        p.kill()


def test_a_slow_checker_is_still_answered_in_order():
    p = start(SLOW)
    try:
        sends, lines = logic.pipes(p)
        a = logic.exchange(sends, lines, {"id": 1, "cmd": "check"}, 10)
        b = logic.exchange(sends, lines, {"id": 2, "cmd": "check"}, 10)
        assert (a["id"], a["result"], b["id"]) == (1, "late", 2)
    finally:
        p.kill()


def test_a_checker_that_stops_ends_the_wait_at_once():
    p = start("pass")
    sends, lines = logic.pipes(p)
    began = time.monotonic()
    assert logic.exchange(sends, lines, {"id": 1}, 30) is None      # stopped: None, not the 30 s limit
    assert time.monotonic() - began < 5


def test_sweep_undoes_everything_even_if_one_undo_fails():
    done = []
    leftovers = {"a": lambda: done.append("a"), "b": lambda: 1 / 0, "c": lambda: done.append("c")}
    assert logic.sweep(leftovers) == 2 and done == ["a", "c"] and leftovers == {}


def test_an_earlier_copys_handler_does_nothing():
    calls, current = [], [True]
    handler = logic.current_only(lambda *a: calls.append(a), lambda: current[0])
    handler(1)
    current[0] = False                                           # another copy was loaded
    handler(2)
    assert calls == [(1,)]


def test_the_plugin_never_touches_a_pipe_or_a_rhino_event_directly():
    """Every pipe goes through logic.pipes/exchange; every Rhino event through _on/_off (so it is registered for
    the next copy's sweep)."""
    import re
    src = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert not re.search(r"\.std(in|out)\.(write|read|readline|flush)|for line in .*stdout", src)
    assert not re.search(r"Rhino\.[\w.]+ [+-]= ", src)
    assert "logic.sweep(LEFTOVERS, STATE)" in src and json.dumps("gordium_leftovers") in src


def test_the_sweep_forgets_the_plugins_handles_but_keeps_what_the_architect_asked_for():
    """Review round 1 (P1): after a reload that keeps the plugin's state, the state must not say a detached hook
    is attached (live mode would look on while edits go unchecked, an old PASS staying on the panel)."""
    ran = []
    state = {k: object() for k in logic.HANDLES}
    state.update({"live": True, "repo": "/the/repo", "envelope_on": False, "labels_by_doc": {1: True}})
    leftovers = {"hook": lambda: ran.append("hook"), "worker": lambda: ran.append("worker")}
    assert logic.sweep(leftovers, state) == 2 and sorted(ran) == ["hook", "worker"]
    assert not any(k in state for k in logic.HANDLES)
    assert state == {"live": True, "repo": "/the/repo", "envelope_on": False, "labels_by_doc": {1: True}}
    assert {"hooks", "doc_hooks", "overlay", "worker", "worker_sends", "worker_lines"} <= set(logic.HANDLES)


def test_the_writer_thread_ends_when_its_checker_is_stopped_any_way():
    """Review round 1 (P3): a checker killed without the writer's sentinel (a restart, a sweep) used to leave its
    writer blocked for the rest of the Rhino session."""
    p = start(SILENT)
    logic.pipes(p)
    name = "gordium-writer-%d" % p.pid
    assert any(t.name == name for t in threading.enumerate())
    p.kill()
    p.wait()
    deadline = time.monotonic() + 5
    while any(t.name == name for t in threading.enumerate()) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not any(t.name == name for t in threading.enumerate())


def test_the_plugin_keeps_its_state_true_across_a_reload():
    """Review round 1 (P1, P2, P3) on the Rhino side, which CI can't run (no_freeze_in_rhino.py proves it there):
    the sweep is given STATE; live mode comes back after the module loads; the drawing is registered every time
    it is turned on; every checker restart goes through _stop_worker."""
    src = (Path(__file__).resolve().parents[3] / "apps/rhino_plugin/gordium_rhino.py").read_text(encoding="utf-8")
    assert "\nlogic.sweep(LEFTOVERS, STATE)\n" in src
    assert src.rstrip().endswith('if STATE.get("live"):                        # live mode was on before this copy '
                                 'loaded: its hooks back on\n    live(True)')
    overlay = src.split("def overlay(", 1)[1].split("\ndef ", 1)[0]
    created = overlay.split("if o is None:", 1)[1].split("\n    o.Enabled = True", 1)[0]
    assert overlay.index('LEFTOVERS["overlay"]') < overlay.index("o.Enabled = True")
    assert '\n    LEFTOVERS["overlay"]' in created and '\n        LEFTOVERS["overlay"]' not in created  # every enable
    worker = src.split("def _worker(", 1)[1].split("\ndef ", 1)[0]
    assert "_stop_worker()" in worker and ".terminate()" not in worker
    assert 'LEFTOVERS["worker"] = _stop_worker' in worker
