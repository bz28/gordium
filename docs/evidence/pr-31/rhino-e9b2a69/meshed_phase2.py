#! python3
"""Phase 2 (after Rhino idled): Front Shaded: is the house shaded now (face vs background), does it hide a real red
box behind it, and does the plugin's coloured piece show through it drawn whole (as at 001b757) and filtered (as at
e9b2a69)? Then my own conduit per stage. Closes the doc."""
import json
import sys
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

HERE = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
FR = HERE + "fill_frames/"
WT = open(HERE + "fill_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import close  # noqa: E402

log = {}
st = sc.sticky.pop("meshed_probe", None)
doc = st and st["doc"]
probe = None


class Probe(Rhino.Display.DisplayConduit):
    def __init__(self):
        super().__init__()
        self.stage, self.pieces, self.test, self.colour, self.alpha = None, [], True, None, 0.45

    def _draw(self, e, stage):
        if self.stage != stage:
            return
        d = e.Display
        d.EnableDepthTesting(self.test)
        d.EnableDepthWriting(False)
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


try:
    g = st["g"]
    o = g.overlay()
    kept = list(o.encroach)
    box = rg.BoundingBox.Empty
    for x in g._buildings(doc):
        box.Union(x.Geometry.GetBoundingBox(True))
    view = doc.Views.Find("Front", False)
    vp = view.ActiveViewport
    log["mode"] = vp.DisplayMode.EnglishName
    log["render_meshes"] = [len(x.GetMeshes(Rhino.Geometry.MeshType.Render)) for x in g._buildings(doc)]

    def cap(name=None):
        view.Redraw()
        b = view.CaptureToBitmap(vp.Size)
        if name:
            b.Save(FR + name + ".png")
        return b

    def face(plain, other):
        diffs = []
        for i in range(1, 10):
            for k in range(1, 10):
                p = rg.Point3d(box.Min.X + (box.Max.X - box.Min.X) * i / 10.0, box.Min.Y,
                               box.Min.Z + (box.Max.Z - box.Min.Z) * k / 10.0)
                q = vp.WorldToClient(p)
                a, b = plain.GetPixel(int(q.X), int(q.Y)), other.GetPixel(int(q.X), int(q.Y))
                diffs.append(max(abs(a.R - b.R), abs(a.G - b.G), abs(a.B - b.B)))
        return {"samples": len(diffs), "changed_over_24": sum(d > 24 for d in diffs),
                "median": sorted(diffs)[len(diffs) // 2]}

    o.encroach = []
    plain = cap("E0_meshed_plain")
    q = vp.WorldToClient(rg.Point3d(box.Center.X + 3, box.Min.Y, box.Center.Z + 3))
    q2 = vp.WorldToClient(rg.Point3d(box.Max.X + 30, box.Min.Y, box.Max.Z + 20))
    log["house_face_pixel"] = str(plain.GetPixel(int(q.X), int(q.Y)))
    log["background_pixel"] = str(plain.GetPixel(10, plain.Height - 30))
    o.encroach = kept
    log["plugin_new_filtered"] = face(plain, cap("E1_meshed_plugin_new"))
    real = g._seen_faces
    g._seen_faces = lambda oo, v, piece: piece
    try:
        log["plugin_old_whole_piece"] = face(plain, cap("E2_meshed_plugin_old_whole"))
    finally:
        g._seen_faces = real
    o.encroach = []
    probe = Probe()
    probe.pieces = [p for p, _, _ in kept]
    probe.colour = g.ui.HIGHLIGHT[g.logic.highlight(kept[0][1])]
    probe.Enabled = True
    rows = []
    for stage in ("PreDrawObjects", "PostDrawObjects", "DrawForeground", "DrawOverlay"):
        for test in (True, False):
            probe.stage, probe.test = stage, test
            r = face(plain, cap("F_%s_test%d" % (stage, test)))
            r.update({"stage": stage, "depth_test": test})
            rows.append(r)
    log["own_conduit"] = rows
    probe.Enabled = False
    o.encroach = kept
    # a real red box behind the house, part of it beside the house
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attrs.ObjectColor = System.Drawing.Color.Red
    behind = rg.Box(rg.BoundingBox(rg.Point3d(box.Min.X + 2, box.Max.Y + 5, 2),
                                   rg.Point3d(box.Max.X + 15, box.Max.Y + 10, box.Max.Z - 2)))
    o.encroach = []
    rid = doc.Objects.AddBrep(behind.ToBrep(), attrs)
    try:
        log["red_box_same_script"] = face(plain, cap("E3_red_box_same_script"))
    finally:
        doc.Objects.Delete(rid, True)
        o.encroach = kept
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if probe is not None:
        probe.Enabled = False
    if doc is not None:
        close(doc)
    log["done"] = True
    json.dump(log, open(HERE + "meshed2.json", "w", encoding="utf-8"), default=str, indent=1)
