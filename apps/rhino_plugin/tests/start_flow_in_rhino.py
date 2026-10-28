#! python3
"""The whole start flow, in Rhino 8, in the order an architect meets it (run in Rhino, not in CI):
1. New empty document -> GordiumCheck -> the prefilled box is the first thing (captured, then OK)
2. The largest legal building appears, checked
3. Edits an architect makes, each followed by the re-check live mode runs, and then fixed:
   stretch the rear wall back - raise the roof above 35ft - widen the house past the side setback
Each step: viewport capture, the corner status, the newly-failing note (toast) if any, the red objects.
Writes <temp>/gordium_start_flow/flow_out.json and frames/NN.png.

How to run: in Rhino, make a new empty document first (File > New, no template), then RunPythonScript this
file. (The current demo pictures are in docs/demo/.)"""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import look_up_106  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_start_flow") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # the repo
FRAMES = S + "frames/"
if not os.path.isdir(FRAMES):
    os.makedirs(FRAMES)
steps = []
log = {"steps": steps}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:                # its hooks, drawing and panel off before it is dropped
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    old = sys.modules.get("gordium_rhino")
    if old is not None:
        try:
            old._unhook()
            old.documents(False)
            o = old.STATE.get("overlay")
            if o is not None:
                o.Enabled = False
        except Exception:
            pass
    for name in ("gordium_rhino", "rhino_logic"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


def capture(doc, name, box=None):
    view = doc.Views.Find("Perspective", False) or doc.Views.ActiveView
    doc.Views.ActiveView = view
    view.Maximized = True
    if box is not None:
        view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    bmp = view.CaptureToBitmap(System.Drawing.Size(1280, 720))
    path = FRAMES + name + ".png"
    bmp.Save(path)
    return path


def record(g, doc, name, caption, box, toasts_before):
    last = g.STATE.get("last") or {}
    new_toasts = g.STATE.get("toasts", [])[toasts_before:]
    steps.append({"frame": capture(doc, name, box), "caption": caption, "summary": last.get("summary"),
                  "error": last.get("error"), "toasts": new_toasts, "red": last.get("red"),
                  "rows": [(r["Rule id"], r["Error"], r.get("Provisional")) for r in last.get("rows", [])],
                  "interior": last.get("interior")})


try:
    g = fresh_module()
    doc = Rhino.RhinoDoc.ActiveDoc
    log["start_objects"] = doc.Objects.Count
    shown = {}

    def on_confirm(doc_, facts, text, *box_state):
        shown["text"] = text             # Look up only shows what it found: nothing is drawn until Draw (#26)
        shown["objects_before_draw"] = doc_.Objects.Count
        steps.append({"frame": capture(doc_, "01_box"), "caption": "The prefilled box appears first",
                      "box_text": text, "objects_before_draw": doc_.Objects.Count})

    g.STATE["on_confirm"] = on_confirm
    look_up_106(g, g.gordium_check)                                   # an empty model: the start flow
    assert shown.get("objects_before_draw") == log["start_objects"], "Look up drew into the model before Draw"
    lot = g._find(doc, g.load_facts(doc).get("lot_id") or "")
    assert lot is not None, "Draw drew no lot"
    lot_box = lot.Geometry.GetBoundingBox(True)
    lot_box.Inflate(lot_box.Diagonal.Length * 0.15)
    lot_box.Union(rg.Point3d(lot_box.Center.X, lot_box.Center.Y, 40 / g._scale(doc)))
    record(g, doc, "02_building", "OK: the largest legal building appears", lot_box, 0)
    log["start"] = {k: v for k, v in (g.STATE.get("start") or {}).items() if k != "floors"}

    floors = g.STATE["start"]["floors"]
    ring = floors[0]["outline"]                         # front-right, rear-right, rear-left, front-left (feet)
    P = [g._model_point(doc, p) for p in ring]
    front_left, front_right, rear_right = P[3], P[0], P[1]
    across = rg.Vector3d(front_right - front_left)
    deep = rg.Vector3d(rear_right - front_right)
    width, depth = across.Length, deep.Length
    across.Unitize()
    deep.Unitize()
    plane = rg.Plane(front_left, across, deep)
    ft = 1.0 / g._scale(doc)

    def edit(xform_of, label, caption, fix_caption, n):
        ids = [o.Id for o in g._buildings(doc)]
        before = len(g.STATE.get("toasts", []))
        xform, which = xform_of()
        targets = ids if which is None else [i for i in ids if doc.Objects.FindId(i).Attributes.Name == which]
        for i in targets:
            doc.Objects.Transform(i, xform, True)
        doc.Views.Redraw()
        g.run_check(doc, report=False)                  # what live mode runs half a second after the edit
        record(g, doc, "%02d_%s" % (n, label), caption, lot_box, before)
        inverse = xform.TryGetInverse()[1]
        before = len(g.STATE.get("toasts", []))
        for i in targets:
            doc.Objects.Transform(i, inverse, True)
        doc.Views.Redraw()
        g.run_check(doc, report=False)
        record(g, doc, "%02d_%s_fixed" % (n, label), fix_caption, lot_box, before)

    edit(lambda: (rg.Transform.Scale(plane, 1, (depth + 6 * ft) / depth, 1), None), "rear_wall",
         "Stretch the rear wall back 6 ft", "Push the rear wall back to where it was", 3)
    top = floors[-1]
    base_plane = rg.Plane(rg.Point3d(0, 0, top["base"] * ft), rg.Vector3d.ZAxis)
    edit(lambda: (rg.Transform.Scale(base_plane, 1, 1, (top["top"] - top["base"] + 3) / (top["top"] - top["base"])),
                  "Floor 3"), "roof", "Raise the roof 3 ft, to 38 ft", "Bring the roof back down to 35 ft", 5)
    edit(lambda: (rg.Transform.Scale(plane, (width + 4 * ft) / width, 1, 1), None), "widen",
         "Widen the house 4 ft past the side setback", "Pull the side wall back in", 7)
except Exception:
    log["trace"] = traceback.format_exc()
json.dump(log, open(S + "flow_out.json", "w", encoding="utf-8"), default=str, indent=1)
