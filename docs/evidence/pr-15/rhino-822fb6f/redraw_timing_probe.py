#! python3
"""How long a frame takes with Gordium's drawing (the label placement search included), on the sample with the side
yard failing: Top zoomed in and out step by step, and Perspective orbited, each frame drawn in full there and then
(CaptureToBitmap at the view's size), with on-screen labels on and off. Head from timing_wt.txt. Writes
redraw_timing.json ("done": true); closes its document."""
import json
import sys
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(H + "timing_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

out, opened, g = {"head": WT}, [], None


def frames(view, steps, move):
    """ms per frame over `steps` frames, `move(i)` changing the view before each."""
    times = []
    for i in range(steps):
        move(i)
        t = time.time()
        view.Redraw()
        view.CaptureToBitmap(view.ActiveViewport.Size)
        times.append((time.time() - t) * 1000)
    times.sort()
    return {"frames": steps, "median_ms": round(times[len(times) // 2], 1), "max_ms": round(times[-1], 1),
            "mean_ms": round(sum(times) / len(times), 1)}


try:
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None and hasattr(loaded, "off"):
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    state.pop("worker", None)
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino as g
    doc = TestDocs("redraw_timing").__enter__().open("Large Objects - Feet")
    opened.append(doc)
    g.gordium_check()
    ft = 1.0 / g._scale(doc)
    for o in g._buildings(doc):                          # the house 5 ft to the left: the side yard fails
        doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * ft, 0, 0), True)
    g.run_check(doc, report=False)
    top, persp = doc.Views.Find("Top", False), doc.Views.Find("Perspective", False)
    for labels in (False, True):
        g.set_labels(labels)
        if labels and hasattr(g, "settle_labels"):
            g.settle_labels()                            # the coordinator's ask (822fb6f): placed once before zooming
        key = "labels_on" if labels else "labels_off"
        doc.Views.ActiveView = top
        top.ActiveViewport.ZoomExtents()

        def zoom(i, vp=top.ActiveViewport):
            vp.Magnify(0.9 if (i // 10) % 2 else 1.1, False)
        doc.Views.ActiveView = persp
        persp.ActiveViewport.ZoomExtents()

        def orbit(i, vp=persp.ActiveViewport):
            vp.Rotate(0.05, rg.Vector3d.ZAxis, vp.CameraTarget)
        doc.Views.ActiveView = top
        out[key] = {"top_zoom": frames(top, 40, zoom)}
        doc.Views.ActiveView = persp
        out[key]["perspective_orbit"] = frames(persp, 40, orbit)
    if hasattr(g, "settle_labels"):                      # labels on: the view stops; the timer's ticks place them
        doc.Views.ActiveView = top
        top.ActiveViewport.ZoomExtents()
        g.settle_labels()
        stops = []
        for k in range(8):
            top.ActiveViewport.Magnify(1.25 if k < 4 else 0.8, False)
            top.Redraw()
            before = top.CaptureToBitmap(top.ActiveViewport.Size)
            ticks = []
            done = False
            for _ in range(500):
                t = time.perf_counter()
                done = g.settle_labels(g.LABEL_STEP_S)
                ticks.append((time.perf_counter() - t) * 1000)
                if done:
                    break
            top.Redraw()
            after = top.CaptureToBitmap(top.ActiveViewport.Size)
            if k == 2:
                before.Save(H + "timing_stop_before_settle.png")
                after.Save(H + "timing_stop_after_settle.png")
            stops.append({"ticks": len(ticks), "slowest_tick_ms": round(max(ticks), 2),
                          "total_ms": round(sum(ticks), 1), "settled": bool(done)})
        out["stops"] = stops
        out["slowest_tick_ms"] = max(x["slowest_tick_ms"] for x in stops)
        out["label_step_s"] = g.LABEL_STEP_S
    out["view_px"] = [top.ActiveViewport.Size.Width, top.ActiveViewport.Size.Height]
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    try:
        if g is not None:
            g._stop_worker()
    except Exception:
        pass
    out["done"] = True
    json.dump(out, open(H + "redraw_timing.json", "w", encoding="utf-8"), indent=1, default=str)
