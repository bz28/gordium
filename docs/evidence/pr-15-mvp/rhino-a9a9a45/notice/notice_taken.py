#! python3
"""The "no longer complies" notice never outlives the model it was about (the Rhino job at #28 92cf742: an earlier
scene's red notice stayed over the next house), in Rhino 8, each claim recorded. Run in Rhino, not in CI; the logic
is pinned in CI (packages/design_checker/tests/test_check.py, test_no_notice_outlives_the_model_it_was_about).
GordiumStart on the sample (106 Ithaca Rd), then:
1. The house moved 5 ft to the left (the Southwest side yard 7'-0 5/8" of 10'-0") and checked: the notice says the
   side yard no longer complies, and it is drawn in the Top view.
   In the framed Top view it is compact (at most rhino_logic.NOTICE_SHARES[0] of the view's width) and covers none
   of the model on screen.
1b. Zoomed in tight on the house (the lot and the yards fill the view): the notice isn't drawn over the model (no
   corner is clear), and the panel's message line says it.
2. Moved back and checked: nothing newly fails, and no notice is left (the earlier one is gone, not waiting out its
   6 s). Top capture.
3. Back in step 1's framing, moved left again and checked (the notice drawn again), then moved 1 ft more with no
   check: the model changed since the check, so the notice isn't drawn (as the rows show no marks). Top capture.
4. A fresh notice (moved back and checked, moved left and checked), then another document in front: no notice is
   left.
Where the notice was drawn is read from the drawing itself (gordium_rhino STATE["drawn"], kept by draw_screen per
view), never worked out again by the script.
Run from the Script Editor or RunPythonScript; it never waits for Rhino's idle (no step needs it: the checks are run
by the script, and "changed since the check" is the plugin's own clock). Writes <temp>/gordium_notice/out.json
("done": true, "ok") and Top captures; closes its documents."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_notice_taken") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    """Recorded, never stopping the run."""
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:                # its hooks, drawing and panel off before it is dropped
        loaded.off()
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


def top(doc):
    view = doc.Views.Find("Top", False)
    doc.Views.ActiveView = view
    return view


def capture(doc, name):
    view = top(doc)
    view.Redraw()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(S + name + ".png")


def move(g, doc, feet):
    ft = 1.0 / g._scale(doc)
    for o in g._buildings(doc):
        doc.Objects.Transform(o.Id, rg.Transform.Translation(feet * ft, 0, 0), True)


def notice(g, doc):
    """The notice the plugin holds, and where the Top view really drew it now (gordium_rhino.draw_screen keeps each
    view's placement in STATE["drawn"]: the drawing's own, never a copy of it)."""
    o = g.overlay()
    held = list(o.toast[0]) if getattr(o, "toast", None) else None
    view = top(doc)
    g.STATE.get("drawn", {}).pop(str(view.ActiveViewport.Id), None)     # never an earlier frame's record
    view.Redraw()
    view.CaptureToBitmap(System.Drawing.Size(view.ActiveViewport.Bounds.Width, view.ActiveViewport.Bounds.Height))
    # (the Rhino job at 6361a3f: on the Mac Redraw() only schedules the frame; a capture draws it now, the conduit too)
    rec = g.STATE.get("drawn", {}).get(str(view.ActiveViewport.Id)) or {}
    rec = rec if rec.get("complete") else {}                              # the whole frame drawn
    room = bool(rec and held) and g.logic.notice_place(rec["size"][0], rec["size"][1], ["✕ " + t for t in held],
                                                       rec.get("model"), rec.get("taken") or []) is not None
    return {"held": held, "drawn": rec.get("notice") is not None, "stale": g.stale(o), "box": rec.get("notice"),
            "model": rec.get("model"), "view": rec.get("size"), "room": room, "complete": bool(rec),
            "taken": rec.get("taken")}


def clear_of(box, model):
    """Whether a notice box (x, y, w, h) covers none of the model's screen box (x0, y0, x1, y1)."""
    x, y, w, h = box
    return not model or not (min(x + w, model[2]) > max(x, model[0]) and min(y + h, model[3]) > max(y, model[1]))


docs, opened = None, []
try:
    g = fresh_module()
    docs = TestDocs("notice").__enter__()
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)
    g.gordium_check()                                    # GordiumStart's flow on the sample
    move(g, doc, -5)
    g.run_check(doc, report=False)
    n1 = log["1"] = notice(g, doc)
    capture(doc, "1_framed")                             # (the Rhino job: the framed view at step 1)
    claim("1 moved 5 ft left and checked: the notice says the side yard no longer complies, drawn compact and "
          "clear of the model in the framed Top view",
          n1["held"] and "Side yard, Southwest" in n1["held"][0] and "no longer complies" in n1["held"][0]
          and n1["drawn"] and n1["box"][2] <= n1["view"][0] * g.logic.NOTICE_SHARES[0] + 1
          and clear_of(n1["box"], n1["model"]), n1)
    view = top(doc)                                      # 1b zoomed in tight on the house: never a bar over it
    framing = Rhino.DocObjects.ViewportInfo(view.ActiveViewport)    # step 1's framing, put back after
    box = rg.BoundingBox.Empty
    for o in g._buildings(doc):
        box.Union(o.Geometry.GetBoundingBox(True))
    view.ActiveViewport.ZoomBoundingBox(box)
    n1b = notice(g, doc)
    vp = view.ActiveViewport
    tight, model = n1b["box"], n1b["model"]
    message = str(g.STATE["panel_parts"]["message"].Text) if (g.STATE.get("panel_parts") or {}).get("message") else None
    capture(doc, "1b_zoomed_in")
    log["1b"] = {"notice": tight, "model": model, "view": [vp.Bounds.Width, vp.Bounds.Height], "panel": message}
    claim("1b zoomed in tight: the notice is compact and covers none of the model, or isn't drawn (the panel says it)",
          n1b["complete"] and ((tight is None and not n1b["room"]) or (
              tight is not None and tight[2] <= vp.Bounds.Width * g.logic.NOTICE_SHARES[0] + 1 and clear_of(tight, model)))
          and bool(message) and "no longer complies" in message, log["1b"])
    view.ActiveViewport.SetViewProjection(framing, True)  # back to step 1's framing (the Rhino job at 27c8e5d:
    #                                                      after ZoomExtents the lot filled the view: no corner for step 3)
    move(g, doc, 5)
    g.run_check(doc, report=False)
    n2 = log["2"] = notice(g, doc)
    capture(doc, "2_back_no_notice")
    claim("2 moved back and checked: no notice left of the earlier model", n2["complete"] and n2["held"] is None
          and not n2["drawn"], n2)
    move(g, doc, -5)
    g.run_check(doc, report=False)
    again = notice(g, doc)
    move(g, doc, -1)                                     # an edit, no check
    time.sleep(0.5)                                      # past the plugin's moment (ui.STALE_SECONDS)
    n3 = log["3"] = dict(notice(g, doc), before_edit=again)
    capture(doc, "3_changed_no_notice")
    claim("3 the model changed since the check: the notice isn't drawn over it",
          again["drawn"] and n3["complete"] and n3["stale"] and not n3["drawn"]
          and again["view"] == n1["view"] and again["model"] and n1["model"]
          and max(abs(p - q) for p, q in zip(again["model"], n1["model"])) < 2, n3)    # step 1's framing back
    move(g, doc, 6)                                      # 4: a fresh notice of its own (step 3's edit ended its
    g.run_check(doc, report=False)                       # notice: a changed model's notice is never shown)
    move(g, doc, -5)
    g.run_check(doc, report=False)
    fresh = list(g.overlay().toast[0]) if getattr(g.overlay(), "toast", None) else None
    other = docs.open("Small Objects - Millimeters")     # another document in front (the first stays open)
    opened.append(other)
    n4 = log["4"] = {"held": list(g.overlay().toast[0]) if getattr(g.overlay(), "toast", None) else None,
                     "held_before": fresh}
    claim("4 another document in front: no notice left", bool(fresh) and n4["held"] is None, n4)
    log["ok"] = all(c["ok"] for c in log["claims"].values()) and len(log["claims"]) == 5
except Exception:
    log["trace"] = traceback.format_exc()
    log["ok"] = False
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    log["done"] = True
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
