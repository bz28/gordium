#! python3
"""The Check button (Ben, 2026-10-21), in Rhino 8, each claim asserted. Run in Rhino, not in CI; the rules are
tested in CI (packages/design_checker/tests/test_check_button.py) and the plugin's own code headless (coordination
headless/check_button/). A fresh feet document:
1. GordiumCheck on the empty file: the sample drawn and checked; the panel has Check first beside Edit site…, and
   "Check after every edit" unticked.
2. A floor moved 3 ft (Rhino's own Transform), then Rhino really idle for 3 s: no check ran; the panel's header says
   "Model changed since the last check — press Check", its rows show no marks ("—"), and the viewport's status box
   says the same. Screenshot.
3. The panel's Check pressed: one check, the rows current again.
4. "Check after every edit" ticked: saved in the file; a floor moved again: checked by itself within 3 s of real
   idle. Unticked again at the end (the file left as found).
It runs in phases, as the architect works: Rhino never raises its Idle event while a script runs (looping on
RhinoApp.Wait() inside it is not idle), and the plugin's idle handler is what greys the panel and runs the automatic
check (the Rhino job at ea88c18: docs/evidence/pr-27/rhino-ea88c18/). So this script only starts the run and ends;
each step then runs on a timer once no command is running, and steps 2 and 4 wait until Rhino has been idle (its
Idle event seen) for 3 s after the edit. Started from the Script Editor or RunPythonScript, it begins once that
command has ended. Writes <temp>/gordium_check_button/out.json ("done": true at the end, "ok" whether every claim
passed, "idle" Rhino's idle events seen in each wait) and Top captures; closes its document. A failure is never
raised into Rhino (from a timer that aborts it on the Mac): it is in out.json ("ok": false, "trace") and on the
command line."""
import json
import os
import sys
import tempfile
import time
import traceback

import Eto.Forms as ef
import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (its guard: no callback may raise into Rhino)

S = os.path.join(tempfile.gettempdir(), "gordium_check_button") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IDLE_WAIT_S = 3.0                       # Rhino really idle this long after an edit (the plugin greys at STALE_SECONDS)
PHASE_LIMIT_S = 60.0                    # a wait that never sees Rhino idle fails, never hangs
log = {"claims": {}, "idle": {}}
run = {"phase": "start", "since": time.time(), "idle_at": [], "doc": None, "docs": None}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def fresh_module():
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


def move_top_floor(g, doc):
    house = [o for o in doc.Objects if g.logic.on_layer(doc.Layers[o.Attributes.LayerIndex].FullPath, g.logic.MASSING)]
    o = house[-1]
    doc.Objects.Transform(o, Rhino.Geometry.Transform.Translation(3, 0, 0), True)
    doc.Views.Redraw()


def header_texts(parts):
    out = []
    for c in getattr(parts["header"], "Children", []) or []:
        t = getattr(c, "Text", None)
        if t:
            out.append(str(t))
    return out


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + name + ".png")


def edited(phase):
    """An edit made: the next phase waits for real idle after it."""
    run.update(phase=phase, since=time.time(), idle_at=[])


def idle_enough():
    """Whether Rhino has been idle (its Idle event seen) IDLE_WAIT_S after the edit, with at least one idle event
    after that moment, so the plugin's own idle handler has run past it too."""
    return time.time() - run["since"] >= IDLE_WAIT_S and any(t >= run["since"] + IDLE_WAIT_S for t in run["idle_at"])


def step_a():
    run["docs"] = TestDocs("checkbutton").__enter__()
    g = run["g"] = fresh_module()
    doc = run["doc"] = run["docs"].open("Large Objects - Feet")
    g.gordium_check()                               # an empty file: GordiumStart, the sample drawn and checked
    parts = run["parts"] = g.STATE.get("panel_parts") or {}
    buttons = [b.Text for b in parts.get("box_buttons") or []]
    auto = parts.get("auto_box")
    claim("1 Check first beside Edit site…, and Check after every edit unticked",
          buttons[:2] == ["Check", "Edit site…"] and auto is not None and auto.Checked is False,
          {"buttons": buttons, "auto": auto.Checked if auto else None})
    runs = run["runs"] = []
    real_run = g.run_check
    g.run_check = lambda *a, **k: (runs.append(1), real_run(*a, **k))[1]
    move_top_floor(g, doc)
    edited("b")


def step_b():
    g, doc, parts, runs = run["g"], run["doc"], run["parts"], run["runs"]
    log["idle"]["2"] = {"events": len(run["idle_at"]), "waited_s": round(time.time() - run["since"], 1),
                        "stale_shown": g.STATE.get("stale_shown")}
    texts = header_texts(parts)
    rows = g._status_rows(g.overlay(), True)
    capture(doc, "2_changed_press_check")
    claim("2 an edit, then idle: no check ran", runs == [], len(runs))
    claim("2 the header says press Check and the rows are greyed",
          g.logic.CHANGED_SINCE in texts and parts.get("stale") is True, {"header": texts, "stale": parts.get("stale")})
    claim("2 the status box says it too", rows[0] == "Gordium · " + g.logic.CHANGED_SINCE, rows)

    g.check_now()
    claim("3 Check: one check, the rows current again", len(runs) == 1 and not parts.get("stale"), len(runs))
    capture(doc, "3_checked")

    parts.get("auto_box").Checked = True
    run["saved"] = g._ui_state(doc).get("auto_check")
    move_top_floor(g, doc)
    edited("c")


def step_c():
    g, runs = run["g"], run["runs"]
    log["idle"]["4"] = {"events": len(run["idle_at"]), "waited_s": round(time.time() - run["since"], 1)}
    claim("4 ticked: saved, and an edit is checked by itself", run["saved"] is True and len(runs) == 2,
          {"saved": run["saved"], "checks": len(runs)})
    capture(run["doc"], "4_checked_by_itself")
    run["parts"].get("auto_box").Checked = False
    log["ok"] = all(c["ok"] for c in log["claims"].values())
    run["phase"] = "end"


def finish():
    """The timer and idle watch stopped, the document closed, out.json written (once)."""
    if run.get("finished"):
        return
    run["finished"] = True
    try:
        run["timer"].Stop()
    except Exception:
        pass
    try:
        Rhino.RhinoApp.Idle -= run["idle"]
    except Exception:
        pass
    try:
        g = run.get("g")
        if g is not None and run["parts"].get("auto_box") is not None and run["parts"]["auto_box"].Checked:
            run["parts"]["auto_box"].Checked = False      # the file left as found, after a failure too
    except Exception:
        pass
    try:
        if run["doc"] is not None:
            close(run["doc"])
    except Exception:
        pass
    log.setdefault("ok", False)
    log["done"] = True
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    Rhino.RhinoApp.WriteLine("check_button_in_rhino: " + ("all claims pass" if log["ok"] else
                                                        "FAILED: see " + S + "out.json"))


def tick(sender, e):
    """Each timer tick (on Rhino's UI thread, between its idle events): the next step once no command is running
    and, for steps 2 and 4, once Rhino has been idle long enough after the edit. Any wait (for a command to end, or
    for Rhino to go idle) longer than PHASE_LIMIT_S fails the run: out.json is always written, never a hang."""
    if run.get("finished") or run.get("busy"):
        return
    run["busy"] = True
    try:
        phase = run["phase"]
        step = {"start": "1", "b": "2", "c": "4"}.get(phase, phase)
        late = time.time() - run["since"] > PHASE_LIMIT_S
        if Rhino.Commands.Command.InCommand():
            if late:
                claim("no command left running before step %s" % step, False,
                      {"waited_s": round(time.time() - run["since"], 1)})
            return
        if phase == "start":
            step_a()
        elif phase in ("b", "c"):
            if not idle_enough():
                if late:
                    claim("Rhino went idle after the edit (step %s)" % step, False,
                          {"idle_events": len(run["idle_at"]), "waited_s": round(time.time() - run["since"], 1)})
                return
            (step_b if phase == "b" else step_c)()
        if run["phase"] == "end":
            finish()
    except Exception:
        log["trace"] = traceback.format_exc()
        log["ok"] = False
        finish()
    finally:
        run["busy"] = False


def idle_seen(sender, e):
    run["idle_at"].append(time.time())


earlier = sc.sticky.get("gordium_check_button_run")
if earlier is not None and not earlier.get("finished"):     # an earlier run still waiting: stopped, never two runs
    earlier["finished"] = True                              # driving the plugin or writing out.json
    try:
        earlier["timer"].Stop()
    except Exception:
        pass
    try:
        Rhino.RhinoApp.Idle -= earlier["idle"]
    except Exception:
        pass
if os.path.exists(S + "out.json"):              # never an earlier run's result read as this one's
    os.remove(S + "out.json")
sc.sticky["gordium_check_button_run"] = run     # the timer and handlers outlive this script's own run
idle_handler = System.EventHandler(logic.guard(idle_seen, "count Rhino's idle events"))
run["idle"] = idle_handler
Rhino.RhinoApp.Idle += idle_handler
run["timer"] = ef.UITimer()
run["timer"].Interval = 0.25
run["timer"].Elapsed += logic.guard(tick, "run the next step of check_button_in_rhino")
run["timer"].Start()
Rhino.RhinoApp.WriteLine("check_button_in_rhino: runs once this command ends; wait for " + S +
                         "out.json to say \"done\": true")
