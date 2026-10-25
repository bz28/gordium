#! python3
"""Depth-tested lines (Ben, 2026-10-21: "On-screen lines respect depth in perspective (hidden behind solids); visible
in plan"), in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in Rhino, not in CI: the rules are
tested in CI (packages/design_checker/tests/test_depth.py). A fresh feet document, GordiumStart on the sample (106
Ithaca Rd), Show on-screen labels on.
1. Top (plan): the lines go on top (the plugin's _on_top called with True), the yard dimensions drawn on screen.
2. Perspective, Shaded, the camera at the street looking at the house: no line goes on top; the yard dimensions are
   drawn in the model (draw_scene's _model_dimension), none on screen.
3. The pixels say so: along the rear yard's dimension (behind the house from the street), every sample the house
   hides (a ray from the camera hits the house first) is not the dimension's colour, and of the samples nothing
   hides at least half are (within 60 in each channel).
4. Front (elevation, Shaded): the height's dimension drawn in the model, depth-tested; the see-through envelope
   in front of it never hides it (at least 80 % of its pixels in its colour).
Captures Top and Perspective (Shaded). Writes <temp>/gordium_depth/out.json and frames/*.png; closes its document."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_depth") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    """Recorded, never stopping the run (every claim is reported; the run fails at the end if any did)."""
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
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


def redraw_spied(g, doc, view_name, capture=None):
    """One redraw of a view, recording the plugin's _on_top calls and which way each dimension was drawn."""
    seen = {"on_top": [], "screen": 0, "model": 0}
    real = (g._on_top, g._dimension, g._model_dimension)

    def on_top(d, on):
        seen["on_top"].append(bool(on))
        return real[0](d, on)

    def screen(*a):
        seen["screen"] += 1
        return real[1](*a)

    def model(*a):
        seen["model"] += 1
        return real[2](*a)
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    g._on_top, g._dimension, g._model_dimension = on_top, screen, model
    bitmap = None
    try:
        view.Redraw()
        bitmap = view.CaptureToBitmap(view.ActiveViewport.Size)
        if capture:
            bitmap.Save(S + "frames/" + capture + ".png")
    finally:
        g._on_top, g._dimension, g._model_dimension = real
    return seen, bitmap


doc = None
try:
    g = fresh_module()
    doc = TestDocs("depth").__enter__().open("Large Objects - Feet")
    g.gordium_check()                                    # GordiumStart's flow on the sample
    g.set_labels(True)
    o = g.overlay()
    claim("the sample is drawn with its yard dimensions", len(o.yard_dims) >= 4, len(o.yard_dims))

    frame = o.box if o.box.IsValid else doc.Objects.BoundingBox
    for name in ("Top", "Front"):                        # at working zoom: dimensions give way zoomed out
        doc.Views.Find(name, False).ActiveViewport.ZoomBoundingBox(frame)
    seen, _ = redraw_spied(g, doc, "Top", "1_top")
    log["top"] = seen
    claim("1 Top: the lines go on top", True in seen["on_top"], seen)
    claim("1 Top: the yard dimensions drawn on screen, not in the model",
          seen["screen"] == len(o.yard_dims) and seen["model"] == 0, seen)

    view = doc.Views.Find("Perspective", False)
    vp = view.ActiveViewport
    vp.DisplayMode = Rhino.Display.DisplayModeDescription.FindByName("Shaded")
    box = rg.BoundingBox.Empty
    for x in g._buildings(doc):
        box.Union(x.Geometry.GetBoundingBox(True))
    rear = next(line for line, text, _ in o.yard_dims if text[2:].startswith("Rear yard"))
    front = next(line for line, text, _ in o.yard_dims if text[2:].startswith("Front yard"))
    street = front.From if front.From.DistanceTo(rear.From) > front.To.DistanceTo(rear.From) else front.To
    away = street - box.Center
    away.Z = 0
    away.Unitize()
    eye = box.Center + away * (box.Diagonal.Length * 1.6) + rg.Vector3d(0, 0, box.Max.Z - box.Center.Z)
    vp.SetCameraLocations(box.Center, eye)               # at the street, looking at the house
    seen, bitmap = redraw_spied(g, doc, "Perspective", "2_perspective_shaded")
    log["perspective"] = seen
    claim("2 Perspective: no line goes on top", True not in seen["on_top"], seen)
    claim("2 Perspective: the yard dimensions drawn in the model, none on screen",
          seen["model"] == len(o.yard_dims) and seen["screen"] == 0, seen)

    status = next(st for line, text, st in o.yard_dims if text[2:].startswith("Rear yard"))
    want = g.ui.status_color(status, g.ui.viewport_dark())
    breps = [g._drawable(x.Geometry) for x in g._buildings(doc)]
    breps = [b for b in breps if isinstance(b, rg.Brep)]
    hidden, open_ = [], []
    for k in range(1, 40):
        p = rear.PointAt(k / 40.0)
        q = vp.WorldToClient(p)
        if not (0 <= q.X < bitmap.Width and 0 <= q.Y < bitmap.Height):
            continue
        ray = rg.Line(eye, p)
        blocked = any(rg.Intersect.Intersection.CurveBrep(ray.ToNurbsCurve(), b, doc.ModelAbsoluteTolerance)[2]
                      for b in breps if b is not None)
        c = bitmap.GetPixel(int(q.X), int(q.Y))
        match = max(abs(c.R - want.R), abs(c.G - want.G), abs(c.B - want.B)) <= 60
        (hidden if blocked else open_).append(match)
    log["pixels"] = {"hidden": hidden, "open": open_}
    claim("3 where the house hides the rear yard's dimension, none of it shows", hidden and not any(hidden),
          log["pixels"])
    claim("3 where nothing hides it, it shows", not open_ or sum(open_) >= len(open_) / 2.0, log["pixels"])

    front_vp = doc.Views.Find("Front", False).ActiveViewport
    front_vp.DisplayMode = Rhino.Display.DisplayModeDescription.FindByName("Shaded")
    seen, bitmap = redraw_spied(g, doc, "Front", "4_front_shaded")
    log["front"] = seen
    claim("4 Front: the height's dimension drawn in the model, depth-tested",
          seen["model"] == 1 and seen["screen"] == 0 and True not in seen["on_top"], seen)
    line, _, hstatus, _ = o.height_dim
    want = g.ui.status_color(hstatus, g.ui.viewport_dark())
    hits = []
    for k in range(2, 39):
        q = front_vp.WorldToClient(line.PointAt(k / 40.0))
        if 0 <= q.X < bitmap.Width and 0 <= q.Y < bitmap.Height:
            c = bitmap.GetPixel(int(q.X), int(q.Y))
            hits.append(max(abs(c.R - want.R), abs(c.G - want.G), abs(c.B - want.B)) <= 60)
    log["height_pixels"] = hits
    claim("4 the see-through envelope never hides it: most of its length shows in its colour (Shaded Front)",
          hits and sum(hits) >= 0.8 * len(hits), hits)
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("depth_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                 "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
