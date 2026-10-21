#! python3
"""GordiumStart frames every view on the lot and the house only (review round 7), in Rhino 8. Run in Rhino, not in
CI. A fresh document from Rhino's millimeter template (which opens framed on a few millimeters at the origin), with a
box 2,000 ft away already in it; GordiumStart's flow; then, in every view: are the lot's corners and the house in
view, and is the far box out of it? Writes <temp>/gordium_zoom/out.json and a capture of each view; closes its
document at the end (keep another document open: Rhino keeps the last one's window)."""
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
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_zoom") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"views": {}}


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


docs = TestDocs("zoom").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Small Objects - Millimeters")
    far = g._model_point(doc, [2000.0, 2000.0])                 # 2,000 ft away, in the model's units
    size = g._model_length(doc, 10)
    doc.Objects.AddBrep(rg.Box(rg.Plane(far, rg.Vector3d.ZAxis), rg.Interval(0, size), rg.Interval(0, size),
                               rg.Interval(0, size)).ToBrep())
    g.STATE["on_confirm"] = lambda *a: None
    g.gordium_check()                                            # empty but for the far box: the start flow
    facts = g.current_facts(doc)
    lot = g._find(doc, facts.get("lot_id") or "")
    corners = [c for c in lot.Geometry.GetBoundingBox(True).GetCorners()][:4]
    house = rg.BoundingBox.Empty
    for o in g._buildings(doc):
        house.Union(o.Geometry.GetBoundingBox(True))
    log["house_found"] = house.IsValid
    for view in doc.Views:
        vp = view.ActiveViewport
        name = vp.Name
        log["views"][name] = {"lot_corners_in_view": all(vp.IsVisible(c) for c in corners),
                              "house_in_view": house.IsValid and vp.IsVisible(house.Center),
                              "far_box_out_of_view": not vp.IsVisible(far)}
        bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
        if bmp is not None:
            bmp.Save(S + name + ".png")
    log["ok"] = bool(log["views"]) and all(all(v.values()) for v in log["views"].values())
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        close(doc)
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
