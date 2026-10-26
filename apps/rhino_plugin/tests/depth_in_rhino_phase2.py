#! python3
"""Phase 2 of depth_in_rhino.py, run after phase 1 has returned and Rhino has idled (the house now drawn shaded):
the pixel claims, each recorded, the run failing at the end if any did.
3. Perspective from the street: where the house hides the rear yard's dimension (a ray from the camera hits the
   house first) none of it shows; where nothing hides it, at least half its samples are its colour.
4. Front (Shaded): the height's dimension drawn in the model, depth-tested; the see-through envelope never hides it
   (80 % of its pixels in its colour).
5. Front: the house's front face looks the same with and without the coloured pieces (the rear yard's strip
   behind it is hidden by the house: 90 % of 81 samples within 24 per channel).
6. From behind: the strip shows its colour on the rear face (80 % of samples differ by more than 24).
7. Orbiting the shaded Perspective, a frame with the labels and colours on takes at most 1.2 x one with them off
   (median of 40 frames each; the Rhino job at e9b2a69: a per-camera face filter took 89 ms against 33).
Writes <temp>/gordium_depth/out.json (both phases' claims) and frames/*.png; closes the document."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_depth") + "/"
st = sc.sticky.pop("gordium_depth", None)
assert st is not None, "run depth_in_rhino.py first (phase 1), let Rhino idle, then this"
doc, g, log, frame, box, rear = st["doc"], st["g"], st["log"], st["frame"], st["box"], st["rear"]
o = g.overlay()


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


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


try:
    view = doc.Views.Find("Perspective", False)
    vp = view.ActiveViewport
    eye = vp.CameraLocation
    seen, bitmap = redraw_spied(g, doc, "Perspective", "3_perspective_shaded")
    status = next(st for line, text, st in o.yard_dims if text[2:].startswith("Rear yard"))
    want = g.ui.dim_color(status, g.ui.viewport_dark())
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
    want = g.ui.dim_color(hstatus, g.ui.viewport_dark())
    hits = []
    for k in range(2, 39):
        q = front_vp.WorldToClient(line.PointAt(k / 40.0))
        if 0 <= q.X < bitmap.Width and 0 <= q.Y < bitmap.Height:
            c = bitmap.GetPixel(int(q.X), int(q.Y))
            hits.append(max(abs(c.R - want.R), abs(c.G - want.G), abs(c.B - want.B)) <= 60)
    log["height_pixels"] = hits
    claim("4 the see-through envelope never hides it: most of its length shows in its colour (Shaded Front)",
          hits and sum(hits) >= 0.8 * len(hits), hits)
    # the coloured pieces (Rhino check of #31 at 001b757: the rear yard's strip, behind the house's front face,
    # coloured the whole front face amber in Front): the front face looks the same with and without them
    log["encroach"] = [(info.get("row"), st) for _, st, info in o.encroach]
    claim("5 the sample has a coloured piece to hide (the rear yard's strip)", bool(o.encroach), log["encroach"])
    kept = o.encroach
    o.encroach = []
    _, plain = redraw_spied(g, doc, "Front", "5_front_no_colour")
    o.encroach = kept
    _, coloured = redraw_spied(g, doc, "Front", "5_front_coloured")
    front_y = min(c.Y for c in box.GetCorners())           # the house's front face (the street side, Front's near
    diffs = []                                             # side), sampled inside its outline
    for i in range(1, 10):
        for k in range(1, 10):
            p = rg.Point3d(box.Min.X + (box.Max.X - box.Min.X) * i / 10.0, front_y,
                           box.Min.Z + (box.Max.Z - box.Min.Z) * k / 10.0)
            q = front_vp.WorldToClient(p)
            if 0 <= q.X < plain.Width and 0 <= q.Y < plain.Height:
                a, b = plain.GetPixel(int(q.X), int(q.Y)), coloured.GetPixel(int(q.X), int(q.Y))
                diffs.append(max(abs(a.R - b.R), abs(a.G - b.G), abs(a.B - b.B)))
    log["front_face_diffs"] = diffs
    claim("5 Front: the front face is not amber (the strip behind it is hidden): it looks as it does uncoloured",
          diffs and sum(dv <= 24 for dv in diffs) >= 0.9 * len(diffs), diffs)
    # and the strip still shows where it is seen (a hiding that hid everything would pass the claim above:
    # review of 8379b66, F3): from behind the house, its rear face is coloured
    persp = doc.Views.Find("Perspective", False).ActiveViewport
    rear_y = max(c.Y for c in box.GetCorners())
    persp.SetCameraLocations(box.Center, box.Center + rg.Vector3d(0, box.Diagonal.Length * 2.5, 0))
    o.encroach = []
    _, plain = redraw_spied(g, doc, "Perspective", "6_back_no_colour")
    o.encroach = kept
    _, coloured = redraw_spied(g, doc, "Perspective", "6_back_coloured")
    back = []
    for i in range(2, 9):
        for k in range(2, 9):
            p = rg.Point3d(box.Min.X + (box.Max.X - box.Min.X) * i / 10.0, rear_y,
                           box.Min.Z + (box.Max.Z - box.Min.Z) * k / 10.0)
            q = persp.WorldToClient(p)
            if 0 <= q.X < plain.Width and 0 <= q.Y < plain.Height:
                a, b = plain.GetPixel(int(q.X), int(q.Y)), coloured.GetPixel(int(q.X), int(q.Y))
                back.append(max(abs(a.R - b.R), abs(a.G - b.G), abs(a.B - b.B)))
    log["rear_face_diffs"] = back
    claim("6 from behind, the rear yard's strip shows its colour on the rear face (it is not hidden everywhere)",
          back and sum(dv > 24 for dv in back) >= 0.8 * len(back), back)
    # 7. orbit timing: labels and colours on against off (the Rhino job at e9b2a69)
    persp = doc.Views.Find("Perspective", False)
    pvp = persp.ActiveViewport
    pvp.ZoomBoundingBox(frame)
    doc.Views.ActiveView = persp
    timing = {}
    for on in (False, True):
        o.encroach = kept if on else []
        g.set_labels(on)
        ms = []
        persp.Redraw()
        for _ in range(40):
            pvp.Rotate(0.05, rg.Vector3d.ZAxis, frame.Center)
            t = time.perf_counter()
            persp.Redraw()
            persp.CaptureToBitmap(pvp.Size)
            ms.append((time.perf_counter() - t) * 1000)
        ms.sort()
        timing["on" if on else "off"] = {"median_ms": round(ms[len(ms) // 2], 1), "max_ms": round(ms[-1], 1)}
    log["orbit"] = timing
    claim("7 orbiting, a frame with the labels and colours on takes at most 1.2 x one with them off (median)",
          timing["on"]["median_ms"] <= 1.2 * timing["off"]["median_ms"], timing)
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    close(doc)
print("depth_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                 "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
