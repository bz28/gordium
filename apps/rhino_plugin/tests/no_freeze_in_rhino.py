#! python3
"""Rhino can never freeze on the checker, and a reloaded copy of the plugin can never stay attached, in Rhino 8,
each claim asserted (the run fails loudly otherwise). Run in Rhino, not in CI; opens one test copy and closes it.

2026-10-21: Rhino froze. 23 earlier copies of the plugin were still attached to Rhino's events (a test reload
cleared the plugin's state without turning it off, losing the handles), and one, from before the reader thread,
read the checker's pipe on Rhino's thread while the current copy's reader took the answer. This proves:
1. reloading twice the bad way (state cleared, no off()) leaves exactly one copy's handlers attached (each
   import detaches the previous copy's), and the earlier copy is inert;
2. a checker that never reads or answers, sent a 2 MB request, gives a clear error within the time limit;
3. a slow checker is still answered;
4. the real checker answers afterwards;
5. off() leaves none of the plugin's handlers attached (it used to re-attach the document hooks);
6. a reload that keeps the plugin's state (live mode and the drawing on) leaves one copy attached, the
   old drawing off, and an edit noticed and re-checked (review round 1: the state said detached hooks
   were attached, so edits went unchecked).
Writes <temp>/gordium_no_freeze/out.json."""
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_no_freeze") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}
SILENT = "import time; time.sleep(120)"
SLOW = ("import json, sys, time\n"
        "for line in sys.stdin:\n"
        "    time.sleep(1.5)\n"
        "    print(json.dumps({'id': json.loads(line)['id'], 'ok': True, 'result': 'late'}), flush=True)\n")
EVENTS = {"Idle": ("Rhino.RhinoApp", "m_idle_occured"), "AddRhinoObject": ("Rhino.RhinoDoc", "m_add_object"),
          "EndOpenDocument": ("Rhino.RhinoDoc", "m_end_open_document")}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def python_handlers():
    """How many Python handlers are attached to each event (pythonnet's dispatchers)."""
    F = System.Reflection.BindingFlags
    out = {}
    for event, (owner, field) in EVENTS.items():
        v = System.Type.GetType(owner + ", RhinoCommon").GetField(field, F.Static | F.NonPublic).GetValue(None)
        out[event] = 0 if v is None else sum(1 for d in v.GetInvocationList()
                                             if str(d.Method.DeclaringType).startswith("__System_EventHandler"))
    return out


def load_the_bad_way():
    """A reload as the old test helpers did it: the plugin's state cleared, modules dropped, NO off()."""
    state = sc.sticky.setdefault("gordium_state", {})
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    gordium_rhino.live(True)
    gordium_rhino.documents(True)
    return gordium_rhino


def fake_worker(g, code):
    """A stand-in checker as the current one (same code fingerprint, so ask() doesn't replace it)."""
    p = subprocess.Popen([g._python(), "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, universal_newlines=True, encoding="utf-8")
    g.STATE["worker_sends"], g.STATE["worker_lines"] = g.logic.pipes(p)
    g.STATE["worker"] = p
    g.STATE["worker_code"] = g.logic.code_fingerprint(os.path.join(g.REPO, "packages"))
    return p


g = None
doc = None
try:
    old = sys.modules.get("gordium_rhino")
    if old is not None:
        try:
            old.off()
        except Exception:                    # an older copy's off() (the next import's sweep detaches it anyway)
            pass
    for undo in list((sc.sticky.get("gordium_leftovers") or {}).values()):   # whatever a previous run registered
        try:
            undo()
        except Exception:
            pass
    log["baseline"] = base = python_handlers()
    g1 = load_the_bad_way()
    log["one_copy"] = python_handlers()
    g2 = load_the_bad_way()
    g = g2
    log["two_reloads"] = after = python_handlers()
    claim("1 one copy attached after two bad reloads (baseline + 1)",
          all(after[e] == base[e] + 1 for e in EVENTS), {"baseline": base, "after": after})
    claim("1 the earlier copy is inert", g1._is_current() is False and g2._is_current() is True)

    g.logic.ASK_LIMITS_S["probe"] = 3
    p = fake_worker(g, SILENT)
    began = time.time()
    try:
        g.ask({"cmd": "probe", "model": "x" * 2000000})
        err = None
    except RuntimeError as e:
        err = str(e)
    took = time.time() - began
    claim("2 a silent checker and a 2 MB request: a clear error within the limit",
          err is not None and "gave no answer in 3 s" in err and took < 5, {"error": err, "seconds": round(took, 2)})
    try:
        p.wait(timeout=5)                    # kill() was sent; the OS reaps it a moment later
    except subprocess.TimeoutExpired:
        pass
    claim("2 the silent checker was stopped", p.poll() is not None and "worker" not in g.STATE)

    p = fake_worker(g, SLOW)
    began = time.time()
    answer = g.ask({"cmd": "probe"})
    claim("3 a slow checker is still answered", answer == "late", {"answer": answer,
                                                                      "seconds": round(time.time() - began, 2)})
    g._stop_worker()
    try:
        g.ask({"cmd": "no_such_command"})
        real = "answered ok?"
    except ValueError as e:                  # the real checker's own "unknown command" answer
        real = "ValueError: " + str(e)
    claim("4 the real checker answers afterwards", real.startswith("ValueError"), real)
    g._stop_worker()
    g.off()
    log["after_off"] = python_handlers()
    claim("5 off() leaves nothing attached", log["after_off"] == base, {"baseline": base, "after_off": log["after_off"]})

    # 6 (review round 1): a reload that KEEPS the plugin's state, with live mode and the drawing on
    doc = TestDocs("nofreeze").__enter__().open("Large Objects - Feet")
    g = load_the_bad_way()
    g.STATE["auto_ok"] = True
    g.gordium_check()                                    # GordiumCheck: live mode on, the drawing, the panel
    first_overlay = g.STATE["overlay"]
    for name in ("gordium_rhino", "rhino_logic"):
        sys.modules.pop(name, None)
    import gordium_rhino as g3                           # the state kept: a reload as Rhino or an update does it
    g = g3
    g.overlay()                                          # what any drawing call does: the document hooks back on
    log["kept_state_reload"] = kept = python_handlers()
    claim("6 a reload that keeps the state: one copy's handlers attached (baseline + 1)",
          all(kept[e] == base[e] + 1 for e in EVENTS) and g.STATE.get("live") is True, {"baseline": base, "after": kept})
    claim("6 the old drawing is off; the new one is on and registered",
          not first_overlay.Enabled and g.STATE["overlay"] is not first_overlay and g.STATE["overlay"].Enabled and
          "overlay" in g.LEFTOVERS)
    g.STATE["dirty"] = None
    log["buildings"] = len(list(g._buildings(doc)))
    added = doc.Objects.AddPoint(Rhino.Geometry.Point3d(0, 0, 0))   # an edit any document has (an object added)
    claim("6 an edit is noticed by the new copy's live hook", g.STATE.get("dirty") is not None,
          {"buildings": log["buildings"]})
    doc.Objects.Delete(added, True)
    g.STATE["dirty"] = time.time() - 2 * g.IDLE_SECONDS  # as if Rhino went idle after the edit
    g.STATE["last"] = None
    g._idle(None, None)
    claim("6 and re-checked", bool(g.STATE.get("last")), g.STATE.get("last"))
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    # every step runs and the results are always written, even when one step fails (a broken copy's off())
    steps = []
    if g is not None:
        steps += [lambda: g.logic.ASK_LIMITS_S.pop("probe", None), g._stop_worker, g.off]
    if doc is not None:
        steps.append(lambda: close(doc))
    for step in steps:
        try:
            step()
        except Exception:
            log.setdefault("cleanup_errors", []).append(traceback.format_exc()[-400:])
    for undo in list((sc.sticky.get("gordium_leftovers") or {}).values()):   # anything still registered
        try:
            undo()
        except Exception:
            pass
    log["left_attached"] = python_handlers()
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
