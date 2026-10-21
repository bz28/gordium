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
    assert "logic.sweep(LEFTOVERS)" in src and json.dumps("gordium_leftovers") in src

