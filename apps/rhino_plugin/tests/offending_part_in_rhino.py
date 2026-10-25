#! python3
"""Only the offending part is coloured (Ben, 2026-10-21), in Rhino 8, each claim asserted (the run fails loudly
otherwise). Run in Rhino, not in CI: the blocks are tested in CI (packages/design_checker/tests/test_present.py,
test_highlight.py); what only Rhino can show is the cut of the solid itself (Rhino's boolean intersection).
A fresh feet document, GordiumStart on the sample (106 Ithaca Rd, tax-map lot: lines ±2'-0"), then the starting
house replaced by one solid of the architect's:
1. A cantilever. A 20 ft house where the starting house stood, its upper half (10 to 20 ft) reaching 6 ft out
   toward the left lot line (one closed solid, L-shaped in section). The left side yard is measured to the
   cantilever and does not comply. Claims: the side yard fails; every red and amber piece is the cantilever's
   own (each piece's bottom at 10 ft, never the ground under it: the uncut block would start at 0); red and amber
   both drawn; nothing coloured past the cantilever (each piece inside the solid's own box).
2. A gable roof over the height limit. The same footprint, walls to 30 ft, the ridge at 46 ft (average 38 ft,
   over the 35 ft limit). Claims: the height row is coloured (red or amber, its status's colour); every piece
   starts at the limit (35 ft above the lot); the pieces' volume is the roof's wedge above the limit (half the
   block's: the uncut block is twice it), within 5 %; the eaves (wall tops at 30 ft) are not coloured.
Captures Perspective and Front for each. Writes <temp>/gordium_offending/out.json and frames/*.png; closes its
document."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_offending") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


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


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    view.ActiveViewport.ZoomExtents()
    view.Redraw()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(S + "frames/" + name + ".png")


def section_solid(doc, profile, y0, y1):
    """A closed solid: `profile` (x, z points, feet, closed) in the plane y = y0, swept to y1."""
    pts = [rg.Point3d(x, y0, z) for x, z in profile]
    pts.append(pts[0])
    srf = rg.Surface.CreateExtrusion(rg.PolylineCurve(pts), rg.Vector3d(0, y1 - y0, 0))
    brep = srf.ToBrep().CapPlanarHoles(doc.ModelAbsoluteTolerance)
    if brep.SolidOrientation == rg.BrepSolidOrientation.Inward:
        brep.Flip()
    return brep


def replace_house(g, doc, brep):
    """The architect's own solid, on the starting house's layer, in place of every Gordium floor."""
    olds = list(g._buildings(doc))
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = olds[0].Attributes.LayerIndex
    for o in olds:
        doc.Objects.Unlock(o.Id, True)
        doc.Objects.Delete(o.Id, True)
    return doc.Objects.AddBrep(brep, attrs)


def pieces(g):
    return [(b, s) for b, s in g.overlay().encroach]


doc = None
try:
    g = fresh_module()
    tests = TestDocs("offending")
    doc = tests.__enter__().open("Large Objects - Feet")
    g.gordium_check()                                    # GordiumStart's flow on the sample
    k = 1.0 / g._scale(doc)                              # feet -> model units (1 in a feet file)
    box = rg.BoundingBox.Empty
    for o in g._buildings(doc):
        box.Union(o.Geometry.GetBoundingBox(True))
    x0, x1, y0, y1, z0 = box.Min.X, box.Max.X, box.Min.Y, box.Max.Y, box.Min.Z
    log["house_box_ft"] = [x0 / k, x1 / k, y0 / k, y1 / k, z0 / k]

    # 1. the cantilever
    out = 6 * k
    profile = [(x0, z0), (x1, z0), (x1, z0 + 20 * k), (x0 - out, z0 + 20 * k), (x0 - out, z0 + 10 * k), (x0, z0 + 10 * k)]
    solid = section_solid(doc, profile, y0, y1)
    claim("1 the cantilevered house is one closed solid", solid.IsSolid, solid.IsValid)
    replace_house(g, doc, solid)
    g.run_check(doc, report=False)
    items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
    west = items.get("Side yard, Southwest") or {}
    claim("1 the left side yard is measured to the cantilever and does not comply",
          west.get("status") == "does_not_comply", west)
    got = pieces(g)
    log["cantilever"] = [(s, [round(v / k, 3) for v in (b.GetBoundingBox(True).Min.X, b.GetBoundingBox(True).Min.Z,
                                                        b.GetBoundingBox(True).Max.X, b.GetBoundingBox(True).Max.Z)])
                         for b, s in got]
    claim("1 red and amber both drawn", {s for _, s in got} == {"does_not_comply", "needs_review"}, log["cantilever"])
    proud = 0.1 * k
    claim("1 every coloured piece is the cantilever's own: its bottom at 10 ft, never the ground under it",
          got and all(b.GetBoundingBox(True).Min.Z >= z0 + 10 * k - proud for b, _ in got), log["cantilever"])
    claim("1 nothing coloured outside the solid", all(
        b.GetBoundingBox(True).Min.X >= x0 - out - proud and b.GetBoundingBox(True).Max.Z <= z0 + 20 * k + proud
        for b, _ in got), log["cantilever"])
    capture(doc, "Perspective", "1_cantilever_perspective")
    capture(doc, "Front", "1_cantilever_front")

    # 2. the gable roof over the height limit
    mid = (x0 + x1) / 2
    profile = [(x0, z0), (x1, z0), (x1, z0 + 30 * k), (mid, z0 + 46 * k), (x0, z0 + 30 * k)]
    replace_house(g, doc, section_solid(doc, profile, y0, y1))
    g.run_check(doc, report=False)
    items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
    height = items.get("Building height") or {}
    env = (g.STATE.get("last") or {}).get("envelope") or {}
    limit = env.get("top")
    log["height"] = {"row": height, "limit_ft": limit}
    claim("2 the height row needs colour (it does not comply, or needs review)",
          height.get("status") in ("does_not_comply", "needs_review"), height)
    got = [(b, s) for b, s in pieces(g) if s == height.get("status")]
    claim("2 the roof is coloured in the height row's colour", bool(got), [s for _, s in pieces(g)])
    claim("2 every piece starts at the height limit, never at the eaves (30 ft)",
          limit is not None and all(b.GetBoundingBox(True).Min.Z >= limit * k - proud for b, _ in got),
          [round(b.GetBoundingBox(True).Min.Z / k, 3) for b, _ in got])
    volume = sum(rg.VolumeMassProperties.Compute(b).Volume for b, _ in got) / k ** 3
    rise = 46 - (limit - z0 / k) if limit is not None else None          # ft of roof above the limit
    width = (x1 - x0) / k * rise / 16 if rise else None                   # the roof's width at the limit
    wedge = 0.5 * width * rise * (y1 - y0) / k if rise else None
    log["height"].update(volume=volume, wedge=wedge)
    claim("2 the coloured volume is the roof's wedge above the limit (within 5 %; the uncut block is twice it)",
          wedge and abs(volume - wedge) <= 0.05 * wedge, {"volume": volume, "wedge": wedge})
    capture(doc, "Perspective", "2_gable_perspective")
    capture(doc, "Front", "2_gable_front")
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
