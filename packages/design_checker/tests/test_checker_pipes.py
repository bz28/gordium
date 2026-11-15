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
from host_source import host_text

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
    src = host_text("rhino", "plugin", purpose="lint")
    assert not re.search(r"\.std(in|out)\.(write|read|readline|flush)|for line in .*stdout", src)
    assert not re.search(r"Rhino\.[\w.]+ [+-]= ", src)
    assert "logic.sweep(LEFTOVERS, STATE, _release)" in src and json.dumps("gordium_leftovers") in src


def test_clearing_the_notice_never_turns_the_document_hooks_back_on():
    """off() turns the document hooks off, then clears the notice; overlay() turns them back on when they're off,
    so clearing the notice through it left them attached after every off() (Rhino, 2026-10-21:
    no_freeze_in_rhino.py claim 5 counts the handlers)."""
    src = host_text("rhino", "plugin", purpose="wiring")
    for name in ("_clear_toast", "_toast_tick"):
        body = src.split("def %s(" % name, 1)[1].split("\ndef ", 1)[0]
        assert "= overlay()" not in body and 'STATE.get("overlay")' in body, name
    overlay = src.split("def overlay(", 1)[1].split("\ndef ", 1)[0]
    assert "documents(True)" in overlay           # why: the reason clearing must not go through it


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
    src = host_text("rhino", "plugin", purpose="wiring")
    assert "\nlogic.sweep(LEFTOVERS, STATE, _release)\nif STATE.get(\"live\"):" in src   # last: after _release
    assert src.rstrip().endswith('if STATE.get("live"):                        # live mode was on before this copy '
                                 'loaded: its hooks back on\n    live(True)\n'
                                 '# Rhino closing: the checker stopped with it (and any an earlier load left: SERVERS)\n'
                                 '_on(Rhino.RhinoApp, "Closing", _handler(System.EventHandler, lambda s, e: _stop_worker(), '
                                 '"stop the checker"))\n'
                                 '# Undo / Redo: what was drawn for the model before it is cleared, never left on screen '
                                 '(the Rhino job, demo e631aae)\n'
                                 '_on(Rhino.Commands.Command, "UndoRedo", _handler(System.EventHandler'
                                 '[Rhino.Commands.UndoRedoEventArgs], _undo_redo,\n'
                                 '                                                 "clear the drawing after Undo or '
                                 'Redo"))')       # (after the sweep: an earlier copy's is detached first)
    overlay = src.split("def overlay(", 1)[1].split("\ndef ", 1)[0]
    created = overlay.split("if o is None:", 1)[1].split("\n    o.Enabled = True", 1)[0]
    assert overlay.index('LEFTOVERS["overlay"]') < overlay.index("o.Enabled = True")
    assert '\n    LEFTOVERS["overlay"]' in created and '\n        LEFTOVERS["overlay"]' not in created  # every enable
    worker = src.split("def _worker(", 1)[1].split("\ndef ", 1)[0]
    assert "_stop_worker()" in worker and ".terminate()" not in worker
    assert 'LEFTOVERS["worker"] = _stop_worker' in worker


def test_the_sweep_releases_every_handle_before_forgetting_it():
    """Review round 2: a copy from before LEFTOVERS existed registered nothing there; forgetting its STATE handles
    without releasing them left its handlers, drawing, panel and checker attached for good. Every handle is
    released (while STATE still holds it) before it is forgotten; one release failing doesn't stop the others."""
    state = {k: "handle " + k for k in logic.HANDLES}
    state["live"] = True
    seen = []

    def release(key, value):
        seen.append((key, value, key in state))           # still in STATE when released
        if key == "overlay":
            raise RuntimeError("already gone")
    assert logic.sweep({}, state, release) == 0               # no LEFTOVERS at all (the old copy registered none)
    assert sorted(k for k, _, _ in seen) == sorted(logic.HANDLES)
    assert all(v == "handle " + k and held for k, v, held in seen)
    assert state == {"live": True}


def test_the_plugin_releases_each_kind_of_handle():
    src = host_text("rhino", "plugin", purpose="wiring")
    release = src.split("def _release(", 1)[1].split("\n\n\n", 1)[0]
    kinds = set(logic.HANDLES) - {"worker_lines"}             # a queue: nothing to release
    for key in kinds:                                         # every handle any copy keeps, this one's or not
        assert 'key == "%s"' % key in release, key
    assert "_unhook()" in release and "documents(False)" in release and "_stop_worker()" in release



def test_releasing_a_later_copys_panel_closes_its_form():
    """Round 3 on the freeze fix: rhino-ui and demo copies keep their panel as STATE["panel_parts"] = {"form": ...};
    updating from them must close that form, or its buttons keep calling the old copy."""
    import ast
    src = host_text("rhino", "plugin", purpose="wiring")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_release")
    ns = {}
    exec(compile(ast.Module([fn], []), "gordium_rhino", "exec"), ns)

    class Form:
        closed = False

        def Close(self):
            self.closed = True
    form = Form()
    ns["_release"]("panel_parts", {"form": form})
    assert form.closed
    ns["_release"]("panel_parts", None)                     # nothing there: nothing to do, never an error
    ns["_release"]("panel_parts", {})


def test_a_floating_panel_is_placed_once_never_on_every_check():
    """Round 1: panel() resized and moved the floating panel to the right edge on every check (live mode: after
    every edit), so the architect couldn't move it. The real panel(), run twice with stand-ins for Rhino: the
    window is placed the first time only."""
    import ast
    import types
    src = host_text("rhino", "plugin", purpose="wiring")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "panel")
    fits = []
    host = object()
    form = types.SimpleNamespace(host=host, Visible=True, Close=lambda: None)
    ui = types.SimpleNamespace(open_dock=lambda dock: None, DockHost=lambda dock, h: None,
                               make_panel=lambda actions, dock_host, **kw: {"form": form},   # (+ context_on, PR #23)
                               fit_floating=lambda h, window: fits.append(h) or "floating",
                               set_auto_tick=lambda parts, on: None)      # the Check button's tick, as the file has it
    doc = types.SimpleNamespace(RuntimeSerialNumber=1)
    rhino = types.SimpleNamespace(RhinoDoc=types.SimpleNamespace(ActiveDoc=doc),
                                  UI=types.SimpleNamespace(RhinoEtoApp=types.SimpleNamespace(
                                      MainWindowForDocument=lambda d: None)))
    ns = {"STATE": {}, "LEFTOVERS": {}, "ui": ui, "logic": logic, "Rhino": rhino, "_actions": lambda: None, "_sync_ticks": lambda doc: None,
          "register_dock": lambda: "dock", "sc": types.SimpleNamespace(sticky={"gordium_dock_hosts": {1: host}}),
          "_context_on": lambda doc: True,       # PR #23: the panel starts its Show neighbourhood tick as the file has it
          "_auto": lambda doc: False}            # the Check button: Check after every edit, as the file has it
    exec(compile(ast.Module([fn], []), "gordium_rhino", "exec"), ns)
    first = ns["panel"]()
    second = ns["panel"]()
    assert first is second and first["placed"] == "floating"
    assert fits == [host]                                    # placed once; the second check leaves it where it is
    assert logic.place_panel_now(None) and not logic.place_panel_now("floating")
    assert not logic.place_panel_now("docked")


def _bad_calls(src: str) -> list:
    """Every call in `src` to one of its own top-level functions that its definition can't take: bound against a
    stub with the same signature (positional and keyword arguments, defaults), so a misspelt keyword or a wrong
    number of arguments is found. Only calls that unpack *args or **kwargs are left out (their arity is unknown)."""
    import ast
    import inspect
    tree = ast.parse(src)
    stubs = {}
    for f in (n for n in tree.body if isinstance(n, ast.FunctionDef)):
        stub = ast.FunctionDef(name=f.name, args=f.args, body=[ast.Pass()], decorator_list=[], returns=None,
                               type_params=[])
        stub.args = ast.arguments(posonlyargs=f.args.posonlyargs, args=f.args.args, vararg=f.args.vararg,
                                  kwonlyargs=f.args.kwonlyargs, kw_defaults=[None if d is None else ast.Constant(0)
                                                                            for d in f.args.kw_defaults],
                                  kwarg=f.args.kwarg, defaults=[ast.Constant(0) for _ in f.args.defaults])
        for a in stub.args.posonlyargs + stub.args.args + stub.args.kwonlyargs:
            a.annotation = None
        for a in (stub.args.vararg, stub.args.kwarg):
            if a is not None:
                a.annotation = None
        space = {}
        exec(compile(ast.fix_missing_locations(ast.Module([stub], [])), "<stub>", "exec"), space)
        stubs[f.name] = inspect.signature(space[f.name])
    bad = []
    for call in (c for c in ast.walk(tree) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)):
        sig = stubs.get(call.func.id)
        if sig is None or any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
            continue
        try:
            sig.bind(*[None] * len(call.args), **{k.arg: None for k in call.keywords})
        except TypeError as e:
            bad.append((call.func.id, call.lineno, str(e)))
    return bad


def test_a_call_with_a_misspelt_keyword_or_too_many_arguments_is_found():
    """enter-needs review round 2: the arity check skipped every call with keywords."""
    assert _bad_calls("def run_check(doc, report=True):\n    pass\nrun_check(reprt=False)\n")
    assert _bad_calls("def f(a, *, b=1):\n    pass\nf(1, 2)\n")
    assert not _bad_calls("def run_check(doc, report=True):\n    pass\nrun_check(1, report=False)\n")
    assert not _bad_calls("def f(*a, **k):\n    pass\nf(1, 2, x=3)\n")


def test_the_plugin_has_no_two_top_level_definitions_with_one_name():
    """enter-needs review round 1: a second `_yes_no(prompt)` replaced the existing `_yes_no(prompt, current)`, so
    Edit site…'s "Corner lot?" prompt raised TypeError. No top-level name is defined twice, and every call to one of
    the plugin's own top-level functions binds to its definition (positional and keyword arguments)."""
    import ast
    src = host_text("rhino", "plugin", purpose="lint")
    tree = ast.parse(src)
    defs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    names = [n.name for n in defs]
    assert len(names) == len(set(names)), sorted(n for n in set(names) if names.count(n) > 1)
    assert not _bad_calls(src), _bad_calls(src)


