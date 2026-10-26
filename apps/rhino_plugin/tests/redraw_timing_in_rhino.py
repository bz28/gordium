#! python3
"""How the plan labels behave while the view moves and when it stops, in Rhino 8, each claim asserted (the run fails
loudly otherwise). Run in Rhino, not in CI. Based on the Rhino job's timing probe (docs/evidence/pr-15/rhino-5b46c99).
The sample with the house 5 ft to the left (the side yard fails); Top zoomed in and out step by step and Perspective
orbited, each frame drawn there and then (CaptureToBitmap at the view's size), labels off and on. Claims:
1 a moving frame's label work: the median frame with labels on at most 16 ms more than with them off;
2 no label drawn while the view moves breaks a HARD rule (logic.label_breaks_hard on the frame's own record: on
  screen, off the buildings, the boxes, the dimensions, 3 px off its own line, and off the labels drawn before it);
3 when the view stops, every label is placed in ONE pass (settle_labels()) taking at most 80 ms;
4 the frame after that pass is settled: every label drawn where it was placed (none carried, none missing).
Writes <temp>/gordium_redraw_timing/out.json and two captures (a stop, before and after its pass); closes its
document."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino.Geometry as rg
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_redraw_timing") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"head": WT, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


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


def broken(g, rec, rest=False):
    """Each label in a frame's record that breaks a HARD rule there, with the rule (the labels drawn before it count
    as placed: the record lists them in the order drawn). At `rest` a label said to be forced (no spot on screen
    keeps every rule) is let through: it is drawn anyway, never dropped; while moving it is never drawn."""
    out, before = [], []
    view, dims = rec["size"], [tuple(map(tuple, d_)) for d_ in rec.get("dims", [])]
    for lab in rec["labels"]:
        box, line = tuple(lab[1][:4]), tuple(map(tuple, lab[3]))
        why = g.logic.label_breaks_hard(line, box, view, rec.get("hard_boxes", []), dims, rec.get("hard_shapes", []),
                                        before)
        if why and not (rest and lab[6]):
            out.append((lab[0], why, [round(v, 1) for v in box]))
        before.append(box)
    return out


g, opened = None, []
try:
    g = fresh_module()
    doc = TestDocs("redraw_timing").__enter__().open("Large Objects - Feet")
    opened.append(doc)
    g.gordium_check()
    ft = 1.0 / g._scale(doc)
    for o in g._buildings(doc):                          # the house 5 ft to the left: the side yard fails
        doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * ft, 0, 0), True)
    g.run_check(doc, report=False)
    top, persp = doc.Views.Find("Top", False), doc.Views.Find("Perspective", False)
    vid = str(top.ActiveViewport.Id)
    moving_broken, moving_labels = [], 0

    def frames(view, steps, move, watch=False):
        """ms per frame over `steps` frames, `move(i)` changing the view before each; with `watch`, every label
        the frame drew checked against the HARD rules (claim 2)."""
        global moving_labels
        times = []
        for i in range(steps):
            move(i)
            g.STATE.get("drawn", {}).pop(vid, None)
            t = time.time()
            view.Redraw()
            view.CaptureToBitmap(view.ActiveViewport.Size)
            times.append((time.time() - t) * 1000)
            rec = g.STATE.get("drawn", {}).get(vid) or {}
            if watch and rec.get("complete"):
                moving_labels += len(rec["labels"])
                moving_broken.extend(broken(g, rec))
        times.sort()
        return {"frames": steps, "median_ms": round(times[len(times) // 2], 1), "max_ms": round(times[-1], 1)}

    for labels in (False, True):
        g.set_labels(labels)
        doc.Views.ActiveView = top
        top.ActiveViewport.ZoomExtents()
        if labels:                                       # at rest first: placed once, then carried while zooming
            top.Redraw()
            top.CaptureToBitmap(top.ActiveViewport.Size)
            g.settle_labels()

        def zoom(i, vp=top.ActiveViewport):
            vp.Magnify(0.9 if (i // 10) % 2 else 1.1, False)

        def orbit(i, vp=persp.ActiveViewport):
            vp.Rotate(0.05, rg.Vector3d.ZAxis, vp.CameraTarget)
        key = "labels_on" if labels else "labels_off"
        log[key] = {"top_zoom": frames(top, 40, zoom, watch=labels)}
        doc.Views.ActiveView = persp
        persp.ActiveViewport.ZoomExtents()
        log[key]["perspective_orbit"] = frames(persp, 40, orbit)
    extra = log["labels_on"]["top_zoom"]["median_ms"] - log["labels_off"]["top_zoom"]["median_ms"]
    claim("1 a moving frame's label work at most 16 ms (median, labels on less off)", extra <= 16,
          {"extra_ms": round(extra, 1), "on": log["labels_on"], "off": log["labels_off"]})
    claim("2 no label drawn while the view moves breaks a HARD rule", moving_labels > 0 and not moving_broken,
          {"labels_checked": moving_labels, "broken": moving_broken[:20]})

    doc.Views.ActiveView = top                           # stops: one move, then the pass the timer makes at rest
    top.ActiveViewport.ZoomExtents()
    top.Redraw()
    top.CaptureToBitmap(top.ActiveViewport.Size)
    g.settle_labels()
    stops = []
    for k in range(8):
        top.ActiveViewport.Magnify(1.25 if k < 4 else 0.8, False)
        g.STATE.get("drawn", {}).pop(vid, None)
        top.Redraw()
        before = top.CaptureToBitmap(top.ActiveViewport.Size)       # the moving frame: asks for the labels
        t = time.perf_counter()
        done = g.settle_labels()
        pass_ms = (time.perf_counter() - t) * 1000
        g.STATE.get("drawn", {}).pop(vid, None)
        top.Redraw()
        after = top.CaptureToBitmap(top.ActiveViewport.Size)
        rec = g.STATE.get("drawn", {}).get(vid) or {}
        if k == 2:
            before.Save(S + "stop_before_pass.png")
            after.Save(S + "stop_after_pass.png")
        stops.append({"one_pass": bool(done), "pass_ms": round(pass_ms, 1), "settled": bool(rec.get("settled")),
                      "labels": len(rec.get("labels", [])),
                      "broken_at_rest": broken(g, rec, rest=True) if rec else None})
    log["stops"] = stops
    claim("3 every stop placed in ONE pass of at most 80 ms",
          all(s_["one_pass"] and s_["pass_ms"] <= 80 for s_ in stops), stops)
    claim("4 the frame after the pass is settled, its labels keeping every HARD rule",
          all(s_["settled"] and s_["labels"] > 0 and not s_["broken_at_rest"] for s_ in stops), stops)
    log["view_px"] = [top.ActiveViewport.Size.Width, top.ActiveViewport.Size.Height]
    log["label_settle_s"] = g.logic.LABEL_SETTLE_S
except Exception:
    log["trace"] = traceback.format_exc()
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
    log["done"] = True
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), indent=1, default=str)
