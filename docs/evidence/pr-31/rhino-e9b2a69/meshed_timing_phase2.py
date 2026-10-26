#! python3
import json, sys, time, traceback
import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
HERE = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
FR = HERE + "fill_frames/M"
WT = open(HERE + "fill_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import close
log = {}
st = sc.sticky.pop("meshed_probe", None)
doc = st and st["doc"]
def capture(view, name=None):
    view.Redraw()
    bmp = view.CaptureToBitmap(view.ActiveViewport.Size)
    if name:
        bmp.Save(FR + name + ".png")
    return bmp
try:
    g = st["g"]
    o = g.overlay()
    kept = list(o.encroach)
    real_seen = g._seen_faces
    frame = o.box if o.box.IsValid else doc.Objects.BoundingBox
    # (C) orbit timing, colouring on/off, Shaded Perspective and Front
    calls = {"n": 0, "ms": 0.0, "max_ms": 0.0}

    def timed_seen(oo, v, piece):
        t = time.perf_counter()
        try:
            return real_seen(oo, v, piece)
        finally:
            dt = (time.perf_counter() - t) * 1000
            calls["n"] += 1
            calls["ms"] += dt
            calls["max_ms"] = max(calls["max_ms"], dt)
    timing = {}
    for vname in ("Perspective", "Front"):
        v = doc.Views.Find(vname, False)
        vvp = v.ActiveViewport
        vvp.DisplayMode = Rhino.Display.DisplayModeDescription.FindByName("Shaded")
        if vname == "Perspective":
            vvp.ZoomBoundingBox(frame)
        doc.Views.ActiveView = v
        for colour in (False, True):
            o.encroach = kept if colour else []
            o.__dict__.pop("seen_faces", None)
            calls.update({"n": 0, "ms": 0.0, "max_ms": 0.0})
            g._seen_faces = timed_seen
            ms = []
            try:
                capture(v)
                for _ in range(40):
                    vvp.Rotate(0.05, rg.Vector3d.ZAxis, frame.Center)
                    t = time.perf_counter()
                    v.Redraw()
                    v.CaptureToBitmap(vvp.Size)
                    ms.append((time.perf_counter() - t) * 1000)
                capture(v, "C_%s_colour%d_end" % (vname, colour))
            finally:
                g._seen_faces = real_seen
            s = sorted(ms)
            timing["%s_colour_%s" % (vname, "on" if colour else "off")] = {
                "frames": len(ms), "median_ms": round(s[len(s) // 2], 1), "mean_ms": round(sum(s) / len(s), 1),
                "max_ms": round(s[-1], 1), "seen_faces_calls": calls["n"],
                "seen_faces_total_ms": round(calls["ms"], 1), "seen_faces_max_ms": round(calls["max_ms"], 1),
                "cache_size_after": len(o.__dict__.get("seen_faces", {}))}
    log["C_orbit"] = timing
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        close(doc)
    log["done"] = True
    json.dump(log, open(HERE + "meshed_timing.json", "w", encoding="utf-8"), default=str, indent=1)
