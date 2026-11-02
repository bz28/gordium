#! python3
"""Live mode hears edits that touch no object (the audit of main, 2026-10-29), in Rhino 8, each claim asserted. Run in
Rhino, not in CI; the rules are tested in CI (packages/design_checker/tests/test_check_button.py). Before, live mode
heard only objects added, deleted, replaced or re-attributed, so these left the last results showing as current. A
fresh feet document, GordiumCheck with 106 Ithaca Rd looked up (recorded answers), drawn and checked, then, each followed by real idle:
1. The model's units changed to inches WITHOUT scaling (every length now 12 times shorter): the results grey out
   ("Model changed since the last check — press Check"). Check.
2. The Gordium::Massing layer renamed (its floors no longer on a building layer): greyed. Check.
3. Only the Site layer's colour changed and the Massing layer hidden and shown again (what Gordium does to its own
   layers at every check): NOT greyed. The layer's name put back. Check.
4. A block of one box placed on the Building layer, checked, then the block's contents replaced (as BlockEdit does):
   greyed.
Runs in phases (Rhino never raises Idle while a script runs; see check_button_in_rhino.py). Writes
<temp>/gordium_live_more/out.json ("done": true at the end, "ok" whether every claim passed) and Top captures;
closes its document."""
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
from test_docs_in_rhino import TestDocs, close, look_up_106  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (its guard: no callback may raise into Rhino)

S = os.path.join(tempfile.gettempdir(), "gordium_live_more") + "/"
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



def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + name + ".png")


def edited(phase):
    run.update(phase=phase, since=time.time(), idle_at=[])


def idle_enough():
    return time.time() - run["since"] >= IDLE_WAIT_S and any(t >= run["since"] + IDLE_WAIT_S for t in run["idle_at"])


def greyed(g):
    o = g.overlay()
    rows = g._status_rows(o, g.stale(o)) if getattr(o, "message", None) else []
    return {"stale": bool(run["parts"].get("stale")), "dirty": g.STATE.get("dirty") is not None,
            "status": rows[0] if rows else None, "last": (g.STATE.get("last") or {}).get("view_summary")
            or (g.STATE.get("last") or {}).get("error")}


def checked_now(g, name):
    g.check_now()
    claim(name + ": Check makes the rows current again", not run["parts"].get("stale"), greyed(g))


def step_a():
    run["docs"] = TestDocs("livemore").__enter__()
    g = run["g"] = fresh_module()
    doc = run["doc"] = run["docs"].open("Large Objects - Feet")
    g.STATE["on_confirm"] = lambda *a: None
    look_up_106(g, g.gordium_check)                 # an empty file: 106 Ithaca Rd looked up (recorded), drawn, checked
    run["parts"] = g.STATE.get("panel_parts") or {}
    claim("0 checked, current", not run["parts"].get("stale") and g.STATE.get("live"), greyed(g))
    capture(doc, "0_checked")
    run["summary_feet"] = (g.STATE.get("last") or {}).get("view_summary")
    doc.AdjustModelUnitSystem(Rhino.UnitSystem.Inches, False)        # units changed, nothing scaled
    claim("1 the units are inches now", doc.ModelUnitSystem == Rhino.UnitSystem.Inches, str(doc.ModelUnitSystem))
    edited("b")


def step_b():
    g, doc = run["g"], run["doc"]
    got = greyed(g)
    capture(doc, "1_units_changed_greyed")
    claim("1 units changed without scaling: greyed, press Check", got["stale"] and got["dirty"], got)
    checked_now(g, "1")
    run["summary_inches"] = (g.STATE.get("last") or {}).get("view_summary")
    capture(doc, "1_checked_in_inches")
    doc.AdjustModelUnitSystem(Rhino.UnitSystem.Feet, False)          # back as it was (an edit too)
    g.check_now()
    layer = doc.Layers.FindByFullPath(g.logic.MASSING, -1)
    claim("2 the Massing layer is there", layer >= 0, layer)
    doc.Layers[layer].Name = "Massing renamed"
    run["massing"] = doc.Layers[layer].Id
    edited("c")


def step_c():
    g, doc = run["g"], run["doc"]
    got = greyed(g)
    capture(doc, "2_layer_renamed_greyed")
    claim("2 a layer renamed: greyed, press Check", got["stale"] and got["dirty"], got)
    checked_now(g, "2")
    site = doc.Layers.FindByFullPath("Site", -1)
    doc.Layers[site].Color = System.Drawing.Color.FromArgb(200, 30, 30)
    massing = doc.Layers.FindId(run["massing"])
    massing.IsVisible = False
    massing.IsVisible = True
    edited("d")


def step_d():
    g, doc = run["g"], run["doc"]
    got = greyed(g)
    claim("3 a colour and a hide and show only: NOT greyed", not got["stale"] and not got["dirty"], got)
    doc.Layers.FindId(run["massing"]).Name = "Massing"
    g.check_now()
    building = doc.Layers.FindByFullPath("Building", -1)
    if building < 0:
        layer = Rhino.DocObjects.Layer()
        layer.Name = "Building"
        building = doc.Layers.Add(layer)
    box = Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY, Rhino.Geometry.Interval(0, 10),
                             Rhino.Geometry.Interval(0, 10), Rhino.Geometry.Interval(0, 10)).ToBrep()
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = building
    index = doc.InstanceDefinitions.Add("gordium_live_more_block", "", Rhino.Geometry.Point3d.Origin, [box], [attrs])
    run["block"] = index
    place = Rhino.DocObjects.ObjectAttributes()
    place.LayerIndex = building
    doc.Objects.AddInstanceObject(index, Rhino.Geometry.Transform.Translation(30, 30, 0), place)
    g.check_now()
    claim("4 checked with the block placed", not run["parts"].get("stale"), greyed(g))
    bigger = Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY, Rhino.Geometry.Interval(0, 40),
                                Rhino.Geometry.Interval(0, 40), Rhino.Geometry.Interval(0, 40)).ToBrep()
    doc.InstanceDefinitions.ModifyGeometry(index, [bigger], [attrs])
    edited("e")


def step_e():
    g, doc = run["g"], run["doc"]
    got = greyed(g)
    capture(doc, "4_block_edited_greyed")
    claim("4 a block's contents edited: greyed, press Check", got["stale"] and got["dirty"], got)
    log["summaries"] = {"feet": run.get("summary_feet"), "inches": run.get("summary_inches")}
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
        pass
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
    Rhino.RhinoApp.WriteLine("live_more_in_rhino: " + ("all claims pass" if log["ok"] else
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
        step = phase
        late = time.time() - run["since"] > PHASE_LIMIT_S
        if Rhino.Commands.Command.InCommand():
            if late:
                claim("no command left running before step %s" % step, False,
                      {"waited_s": round(time.time() - run["since"], 1)})
            return
        if phase == "start":
            step_a()
        elif phase in ("b", "c", "d", "e"):
            if not idle_enough():
                if late:
                    claim("Rhino went idle after the edit (step %s)" % step, False,
                          {"idle_events": len(run["idle_at"]), "waited_s": round(time.time() - run["since"], 1)})
                return
            {"b": step_b, "c": step_c, "d": step_d, "e": step_e}[phase]()
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


earlier = sc.sticky.get("gordium_live_more_run")
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
sc.sticky["gordium_live_more_run"] = run     # the timer and handlers outlive this script's own run
idle_handler = System.EventHandler(logic.guard(idle_seen, "count Rhino's idle events"))
run["idle"] = idle_handler
Rhino.RhinoApp.Idle += idle_handler
run["timer"] = ef.UITimer()
run["timer"].Interval = 0.25
run["timer"].Elapsed += logic.guard(tick, "run the next step of live_more_in_rhino")
run["timer"].Start()
Rhino.RhinoApp.WriteLine("live_more_in_rhino: runs once this command ends; wait for " + S +
                         "out.json to say \"done\": true")
