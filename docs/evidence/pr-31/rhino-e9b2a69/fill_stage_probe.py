#! python3
"""Probe for #31: (A) in which conduit stage, with which depth settings, a coloured piece behind the house's front
face shows through it in Shaded Front; (B) orbit timing with colouring on/off (Shaded Perspective and Front), with
_seen_faces cache misses and time. Head from fill_wt.txt. Writes rhino_ui/fill_stage.json (+ frames)."""
import json
import os
import sys
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc

HERE = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(HERE + "fill_wt.txt", encoding="utf-8").read().strip()
OUT = HERE + "fill_stage.json"
FR = HERE + "fill_frames/"
os.makedirs(FR, exist_ok=True)
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

log = {"head": WT}


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


class Probe(Rhino.Display.DisplayConduit):
    """Draws the pieces in one stage, with chosen depth testing/writing and transparency."""
    def __init__(self):
        super().__init__()
        self.stage, self.pieces, self.test, self.write, self.alpha, self.colour = None, [], True, True, 0.0, None
        self.depth_mode = None

    def _draw(self, e, stage):
        if self.stage != stage:
            return
        d = e.Display
        try:
            self.depth_mode = str(d.DepthMode)
        except Exception as ex:
            self.depth_mode = "n/a: %s" % ex
        d.EnableDepthTesting(self.test)
        d.EnableDepthWriting(self.write)
        for p in self.pieces:
            d.DrawBrepShaded(p, Rhino.Display.DisplayMaterial(self.colour, self.alpha))
        d.EnableDepthTesting(True)
        d.EnableDepthWriting(True)

    def PreDrawObjects(self, e):
        self._draw(e, "PreDrawObjects")

    def PostDrawObjects(self, e):
        self._draw(e, "PostDrawObjects")

    def DrawForeground(self, e):
        self._draw(e, "DrawForeground")

    def DrawOverlay(self, e):
        self._draw(e, "DrawOverlay")


def capture(view, name=None):
    view.Redraw()
    bmp = view.CaptureToBitmap(view.ActiveViewport.Size)
    if name:
        bmp.Save(FR + name + ".png")
    return bmp


doc = None
probe = None
try:
    g = fresh_module()
    doc = TestDocs("fillstage").__enter__().open("Large Objects - Feet")
    g.gordium_check()
    g.set_labels(True)
    o = g.overlay()
    kept = list(o.encroach)
    log["encroach"] = [(info.get("row"), st) for _, st, info in kept]
    box = rg.BoundingBox.Empty
    for x in g._buildings(doc):
        box.Union(x.Geometry.GetBoundingBox(True))
    log["house_box_ft"] = [[round(v, 2) for v in (box.Min.X, box.Min.Y, box.Min.Z)],
                           [round(v, 2) for v in (box.Max.X, box.Max.Y, box.Max.Z)]]
    pb = [p.GetBoundingBox(True) for p, _, _ in kept]
    log["piece_boxes_ft"] = [[[round(v, 2) for v in (b.Min.X, b.Min.Y, b.Min.Z)],
                              [round(v, 2) for v in (b.Max.X, b.Max.Y, b.Max.Z)]] for b in pb]
    frame = o.box if o.box.IsValid else doc.Objects.BoundingBox
    view = doc.Views.Find("Front", False)
    vp = view.ActiveViewport
    vp.DisplayMode = Rhino.Display.DisplayModeDescription.FindByName("Shaded")
    vp.ZoomBoundingBox(frame)
    doc.Views.ActiveView = view

    def face_diff(plain, other):
        front_y = box.Min.Y
        diffs = []
        for i in range(1, 10):
            for k in range(1, 10):
                p = rg.Point3d(box.Min.X + (box.Max.X - box.Min.X) * i / 10.0, front_y,
                               box.Min.Z + (box.Max.Z - box.Min.Z) * k / 10.0)
                q = vp.WorldToClient(p)
                if 0 <= q.X < plain.Width and 0 <= q.Y < plain.Height:
                    a, b = plain.GetPixel(int(q.X), int(q.Y)), other.GetPixel(int(q.X), int(q.Y))
                    diffs.append(max(abs(a.R - b.R), abs(a.G - b.G), abs(a.B - b.B)))
        return {"samples": len(diffs), "changed_over_24": sum(dv > 24 for dv in diffs),
                "median_diff": sorted(diffs)[len(diffs) // 2] if diffs else None}

    # (A) the plugin itself: new (faces filtered), old (whole piece: _seen_faces bypassed)
    o.encroach = []
    plain = capture(view, "A0_plain")
    o.encroach = kept
    log["A_plugin_new"] = face_diff(plain, capture(view, "A1_plugin_new"))
    real_seen = g._seen_faces
    g._seen_faces = lambda oo, v, piece: piece
    try:
        log["A_plugin_old_whole_piece"] = face_diff(plain, capture(view, "A2_plugin_old_whole"))
    finally:
        g._seen_faces = real_seen
    # (A) my own conduit, each stage x depth test x transparency (depth writing off, as the plugin's see-through)
    o.encroach = []
    probe = Probe()
    probe.pieces = [p for p, _, _ in kept]
    probe.colour = g.ui.HIGHLIGHT[g.logic.highlight(kept[0][1])] if kept else None
    log["plugin_transparency"] = g.ui.HIGHLIGHT_TRANSPARENCY
    probe.Enabled = True
    rows = []
    for stage in ("PreDrawObjects", "PostDrawObjects", "DrawForeground", "DrawOverlay"):
        for test in (True, False):
            for alpha in (0.0, g.ui.HIGHLIGHT_TRANSPARENCY):
                for write in (False, True):
                    probe.stage, probe.test, probe.alpha, probe.write = stage, test, alpha, write
                    probe.depth_mode = None
                    name = "B_%s_test%d_write%d_a%02d" % (stage, test, write, int(alpha * 100))
                    r = face_diff(plain, capture(view, name if (alpha and not write) else None))
                    r.update({"stage": stage, "depth_test": test, "depth_write": write, "transparency": alpha,
                              "DepthMode": probe.depth_mode})
                    rows.append(r)
    log["B_stages"] = rows
    probe.Enabled = False
    probe.stage = None
    o.encroach = kept

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
    if probe is not None:
        probe.Enabled = False
    json.dump(log, open(OUT, "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
    log["done"] = True
    json.dump(log, open(OUT, "w", encoding="utf-8"), default=str, indent=1)
