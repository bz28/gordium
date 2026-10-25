#! python3
"""The "no longer complies" notice never outlives the model it was about (the Rhino job at #28 92cf742: an earlier
scene's red notice stayed over the next house), in Rhino 8, each claim recorded. Run in Rhino, not in CI; the logic
is pinned in CI (packages/design_checker/tests/test_check.py, test_no_notice_outlives_the_model_it_was_about).
GordiumStart on the sample (106 Ithaca Rd), then:
1. The house moved 5 ft to the left (the Southwest side yard 7'-0 5/8" of 10'-0") and checked: the notice says the
   side yard no longer complies, and it is drawn in the Top view.
1b. Zoomed in tight on the house: the notice is compact (at most rhino_logic.NOTICE_SHARE of the view's width) and
   covers none of the model on screen, or isn't drawn at all; the panel's message line says it either way.
2. Moved back and checked: nothing newly fails, and no notice is left (the earlier one is gone, not waiting out its
   6 s). Top capture.
3. Moved left again and checked (the notice again), then moved 1 ft more with no check: the model changed since the
   check, so the notice isn't drawn (as the rows show no marks). Top capture.
4. Another document in front: no notice is left.
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

S = os.path.join(tempfile.gettempdir(), "gordium_notice") + "/"
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
    """The notice the plugin holds, and whether it would be drawn in the Top view now."""
    o = g.overlay()
    held = list(o.toast[0]) if getattr(o, "toast", None) else None
    drawn = g._notice_box(o, top(doc).ActiveViewport, [], g.stale(o))
    return {"held": held, "drawn": drawn[0] if drawn else None, "stale": g.stale(o)}


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
    claim("1 moved 5 ft left and checked: the notice says the side yard no longer complies, and is drawn",
          n1["held"] and "Side yard, Southwest" in n1["held"][0] and "no longer complies" in n1["held"][0]
          and n1["drawn"], n1)
    view = top(doc)                                      # 1b zoomed in tight on the house: never a bar over it
    box = rg.BoundingBox.Empty
    for o in g._buildings(doc):
        box.Union(o.Geometry.GetBoundingBox(True))
    view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    vp = view.ActiveViewport
    tight = g._notice_box(g.overlay(), vp, [], g.stale(g.overlay()))
    model = g._model_on_screen(g.overlay(), vp)
    message = str(g.STATE["panel_parts"]["message"].Text) if (g.STATE.get("panel_parts") or {}).get("message") else None
    capture(doc, "1b_zoomed_in")
    log["1b"] = {"notice": tight, "model": model, "view": [vp.Bounds.Width, vp.Bounds.Height], "panel": message}
    claim("1b zoomed in tight: the notice is compact and covers none of the model, or isn't drawn (the panel says it)",
          (tight is None or (tight[3] <= vp.Bounds.Width * g.logic.NOTICE_SHARE + 1 and not (
              model and min(tight[1] + tight[3], model[2]) > max(tight[1], model[0])
              and min(tight[2] + tight[4], model[3]) > max(tight[2], model[1]))))
          and bool(message) and "no longer complies" in message, log["1b"])
    view.ActiveViewport.ZoomExtents()
    move(g, doc, 5)
    g.run_check(doc, report=False)
    n2 = log["2"] = notice(g, doc)
    capture(doc, "2_back_no_notice")
    claim("2 moved back and checked: no notice left of the earlier model", n2["held"] is None and n2["drawn"] is None,
          n2)
    move(g, doc, -5)
    g.run_check(doc, report=False)
    again = notice(g, doc)
    move(g, doc, -1)                                     # an edit, no check
    time.sleep(0.5)                                      # past the plugin's moment (ui.STALE_SECONDS)
    n3 = log["3"] = dict(notice(g, doc), before_edit=again)
    capture(doc, "3_changed_no_notice")
    claim("3 the model changed since the check: the notice isn't drawn over it",
          again["drawn"] and n3["stale"] and n3["drawn"] is None, n3)
    other = docs.open("Small Objects - Millimeters")     # another document in front (the first stays open)
    opened.append(other)
    n4 = log["4"] = {"held": list(g.overlay().toast[0]) if getattr(g.overlay(), "toast", None) else None,
                     "held_before": n3["held"]}
    claim("4 another document in front: no notice left", n3["held"] and n4["held"] is None, n4)
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
