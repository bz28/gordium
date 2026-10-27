#! python3
"""Demo smoke step 6 (the Rhino job): the R-3a eaves design of test_eaves_by_side (sceptic A), drawn in Rhino as an
architect draws it. A 60 x 120 ft lot on the Site layer (the street along y = 0), two 10 ft floors with walls 9'-6"
from the west line and 10'-0" from the east (y 30 to 70), and a gable roof as its own solid on them, its level
underside reaching 0'-6" past the west wall and 3'-6" past the east (eaves 9'-0" and 6'-6" from the lines). Facts:
R-3a, one-family detached, surveyed lot, flat ground. Checked once as drawn, then with the eave candidates the check
names confirmed (as test_eaves_by_side does), and checked again. Records each eaves row and side-yard row, and Top.
Head from eaves_wt.txt; writes eaves_r3a.json ("done": true); closes its document."""
import json
import os
import sys
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC/run1/"
WT = open(H + "eaves_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

out = {"head": WT}
doc = None
g = None


def rows(result):
    """The panel's rows that name a side yard or eaves: name, status, proposed, required, rule, reason."""
    got = []
    for i in (result or {}).get("view", {}).get("items", []):
        name = str(i.get("name") or "")
        if "ide yard" in name or "ave" in name or "rojection" in str(i.get("rule")):
            got.append({k: i.get(k) for k in ("name", "status", "proposed", "required", "delta", "rule", "reason",
                                              "hint")})
            got[-1]["eave_candidates"] = (i.get("detail") or {}).get("eave_candidates")
    return got


def face(pts):
    return rg.Brep.CreateFromCornerPoints(*[rg.Point3d(*p) for p in pts], doc.ModelAbsoluteTolerance)


try:
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
    import gordium_rhino as g
    doc = TestDocs("eaves_r3a").__enter__().open("Large Objects - Feet")
    lot_a = Rhino.DocObjects.ObjectAttributes()
    lot_a.LayerIndex = g._layer(doc, g.LAYERS["lot"])
    lot_pts = [rg.Point3d(x, y, 0) for x, y in ((0, 0), (60, 0), (60, 120), (0, 120), (0, 0))]
    lot = doc.Objects.AddPolyline(rg.Polyline(lot_pts), lot_a)
    west, east, ow, oe = 9.5, 10.0, 0.5, 3.5
    x0, x1, y0, y1 = west, 60 - east, 30.0, 70.0
    for k in range(2):                                      # two 10 ft stories, marked as GordiumStart marks floors
        b = Rhino.DocObjects.ObjectAttributes()
        b.LayerIndex = g._layer(doc, g.LAYERS["building"])
        b.Name = "floor %d" % (k + 1)
        b.SetUserString(g.logic.FLOOR_KEY, "%d;10.0" % (k + 1))
        doc.Objects.AddBrep(g._prism(doc, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], k * 10.0, (k + 1) * 10.0), b)
    xa, xb = x0 - ow, x1 + oe                               # the roof: level soffit, ridge over its middle
    xm, base, ridge = (xa + xb) / 2, 20.0, 26.0
    faces = [face([(xa, y0, base), (xb, y0, base), (xb, y1, base), (xa, y1, base)]),
             face([(xa, y0, base), (xm, y0, ridge), (xm, y1, ridge), (xa, y1, base)]),
             face([(xm, y0, ridge), (xb, y0, base), (xb, y1, base), (xm, y1, ridge)]),
             rg.Brep.CreateFromCornerPoints(rg.Point3d(xa, y0, base), rg.Point3d(xb, y0, base),
                                            rg.Point3d(xm, y0, ridge), doc.ModelAbsoluteTolerance),
             rg.Brep.CreateFromCornerPoints(rg.Point3d(xa, y1, base), rg.Point3d(xb, y1, base),
                                            rg.Point3d(xm, y1, ridge), doc.ModelAbsoluteTolerance)]
    joined = rg.Brep.JoinBreps(faces, doc.ModelAbsoluteTolerance)
    roof = joined[0]
    out["roof_solid"] = bool(roof.IsSolid)
    r = Rhino.DocObjects.ObjectAttributes()
    r.LayerIndex = g._layer(doc, g.LAYERS["building"])
    r.Name = "roof"
    doc.Objects.AddBrep(roof, r)
    facts = {"jurisdiction": g.JURISDICTION, "zone": "R-3a", "use": "one_family_detached", "corner_lot": False,
             "street_line": [[[0, 0], [60, 0]]], "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0,
             "lot_id": str(lot)}
    g.save_facts(doc, facts)
    res = g.run_check(doc, report=False)
    out["as_drawn"] = {"error": (g.STATE.get("last") or {}).get("error"), "rows": rows(res)}
    cands = []
    for row in out["as_drawn"]["rows"]:
        for c in row.get("eave_candidates") or []:
            if c not in cands:
                cands.append(c)
    out["candidates"] = cands
    facts["eaves_confirmed"] = [{"overhang": c, "value": True, "source": "entered by you",
                                 "confirmed_by": "the architect", "date": "2026-10-26"} for c in cands]
    g.save_facts(doc, facts)
    res = g.run_check(doc, report=False)
    out["eaves_confirmed"] = {"error": (g.STATE.get("last") or {}).get("error"), "rows": rows(res)}
    top = doc.Views.Find("Top", False)
    doc.Views.ActiveView = top
    box = rg.BoundingBox(rg.Point3d(-8, -8, 0), rg.Point3d(68, 128, 0))
    top.ActiveViewport.ZoomBoundingBox(box)
    top.Redraw()
    top.CaptureToBitmap(top.ActiveViewport.Size)
    if hasattr(g, "settle_labels"):
        g.settle_labels()
    top.Redraw()
    top.CaptureToBitmap(top.ActiveViewport.Size).Save(H + "eaves/eaves_r3a_top.png")
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    try:
        if g is not None:
            g._stop_worker()
            g.off()
    except Exception:
        pass
    if doc is not None:
        close(doc)
    out["done"] = True
    json.dump(out, open(H + "eaves/eaves_r3a.json", "w", encoding="utf-8"), indent=1, default=str)
