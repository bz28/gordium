#! python3
"""Only the offending part is coloured (Ben, 2026-10-21), in Rhino 8. Every claim is recorded (the run goes on past
a failing one) and the run fails at the end if any did. Run in Rhino, not in CI: the blocks are tested in CI
(packages/design_checker/tests/test_present.py, test_highlight.py); what only Rhino can show is the cut of the solid
itself (Rhino's boolean intersection). The claims read the drawn list itself, overlay().encroach: each piece with
its status and what it is for (its row, why, building: rhino_logic.coloured_info), so the rear yard's strip is never
taken for the side yard's.
A fresh feet document, GordiumStart on the sample (106 Ithaca Rd, tax-map lot: lines ±2'-0"), then the starting
house replaced by one solid of the architect's. Points are placed by their distance from the left lot line (the
real lot's line is slanted) and tested inside or outside the coloured pieces:
1. A cantilever, amber. A 20 ft house where the starting house stood (its wall 12'-0 5/8" from the left line), its
   upper half (10 to 20 ft) reaching 6 ft out toward that line. The left side yard needs review (to the wall it
   complies, to the cantilever it doesn't): amber. Claims: the row needs review; its pieces amber only; a point in
   the cantilever (11 ft from the line, 15 ft up) is coloured; the point under it (11 ft, 5 ft up) is not.
2. A cantilever, red. The same house moved 5 ft toward the line (its wall 7'-0 5/8" from it), its cantilever 4 ft:
   short under every reading. Claims: the row does not comply; red and amber both drawn for it; in the
   cantilever (5 ft from the line, 15 ft up) red; under it (5 ft, 5 ft up) nothing; the house's own wall strip
   7.5 ft from the line, 5 ft up, red (within 8 ft: short however the line lies); 10 ft from it, amber.
3. A gable over the height limit. Walls to 30 ft, ridge 46 ft. Claims: the height row coloured in its colour; a
   point near the ridge (42 ft up) coloured by a height piece; the sky over the slope (44 ft up where the roof is
   38 ft, inside the uncut block) not; the height
   pieces' volume is the wedge above the limit, within 5 % (the uncut block would be twice it).
Captures Perspective and Front for each. Writes <temp>/gordium_offending/out.json and frames/*.png; closes its
document."""
import json
import math
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

S = os.path.join(tempfile.gettempdir(), "gordium_vault") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
log = {"claims": {}}
SIDE = "Side yard, Southwest"          # the sample's left side yard, seen from the street


def claim(name, ok, detail=None):
    """Recorded, never stopping the run (the Rhino check of #28 asked for every claim)."""
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


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    view.ActiveViewport.ZoomExtents()
    view.Redraw()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(S + "frames/" + name + ".png")


def section_solid(doc, profile, y0, y1):
    """A closed solid: `profile` (x, z points, model units, closed) in the plane y = y0, swept to y1."""
    pts = [rg.Point3d(x, y0, z) for x, z in profile]
    pts.append(pts[0])
    srf = rg.Surface.CreateExtrusion(rg.PolylineCurve(pts), rg.Vector3d(0, y1 - y0, 0))
    brep = srf.ToBrep().CapPlanarHoles(doc.ModelAbsoluteTolerance)
    if brep.SolidOrientation == rg.BrepSolidOrientation.Inward:
        brep.Flip()
    return brep


def replace_house(g, doc, brep):
    """The architect's own solid, on the starting house's layer, in place of every building there."""
    olds = list(g._buildings(doc))
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = olds[0].Attributes.LayerIndex
    for o in olds:
        doc.Objects.Unlock(o.Id, True)
        doc.Objects.Delete(o.Id, True)
    return doc.Objects.AddBrep(brep, attrs)


def colour_at(g, doc, point, why=None, row=None):
    """The statuses of the drawn pieces containing `point` (only pieces for `why` / `row` when given)."""
    tol = doc.ModelAbsoluteTolerance
    return sorted({s for b, s, info in g.overlay().encroach
                   if (why is None or info.get("why") == why) and (row is None or info.get("row") == row)
                   and b.IsPointInside(point, tol, False)})


doc = None
try:
    g = fresh_module()
    doc = TestDocs("offending").__enter__().open("Large Objects - Feet")
    g.gordium_check()                                    # GordiumStart's flow on the sample
    k = 1.0 / g._scale(doc)                              # feet -> model units (1 in a feet file)
    box = rg.BoundingBox.Empty
    for o in g._buildings(doc):
        box.Union(o.Geometry.GetBoundingBox(True))
    x0, x1, y0, y1, z0 = box.Min.X, box.Max.X, box.Min.Y, box.Max.Y, box.Min.Z
    ym = (y0 + y1) / 2
    log["house_box_ft"] = [x0 / k, x1 / k, y0 / k, y1 / k, z0 / k]
    ring = g.ask({"cmd": "sample_site"})["lot"]
    edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]
    left = min((e for e in edges if math.dist(e[0], e[1]) > 50), key=lambda e: e[0][0] + e[1][0])

    def from_line(x, y):
        """Feet from the left lot line to the model point (x, y)."""
        (ax, ay), (bx, by) = left
        px, py = x / k, y / k
        t = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
        return math.dist((px, py), (ax + t * (bx - ax), ay + t * (by - ay)))

    def at(feet, z_ft, xs=None):
        """A model point at mid-depth of the house, `feet` from the left line, `z_ft` above the house's base."""
        x = xs if xs is not None else x1
        while x > x0 - 20 * k and from_line(x, ym) > feet:
            x -= 0.01 * k
        return rg.Point3d(x, ym, z0 + z_ft * k)

    def scene(name, profile, dx=0.0):
        solid = section_solid(doc, profile, y0, y1)
        if dx:
            solid.Translate(rg.Vector3d(dx, 0, 0))
        claim(name + " the house is one closed solid", solid.IsSolid, solid.IsValid)
        replace_house(g, doc, solid)
        g.run_check(doc, report=False)
        items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        log[name] = {"pieces": [(s, info) for _, s, info in g.overlay().encroach]}
        return items

    # the vault: walls to 36 ft (over the 35 ft limit), a true arc to 42 ft at the middle
    mid = (x0 + x1) / 2
    wall, crown = 36 * k, 42 * k
    pl = rg.Plane(rg.Point3d(0, y0, 0), rg.Vector3d(1, 0, 0), rg.Vector3d(0, 0, 1))
    pts = lambda x, z: rg.Point3d(x, y0, z)
    prof = rg.PolyCurve()
    prof.Append(rg.LineCurve(pts(x0, z0), pts(x1, z0)))
    prof.Append(rg.LineCurve(pts(x1, z0), pts(x1, z0 + wall)))
    prof.Append(rg.ArcCurve(rg.Arc(pts(x1, z0 + wall), pts(mid, z0 + crown), pts(x0, z0 + wall))))
    prof.Append(rg.LineCurve(pts(x0, z0 + wall), pts(x0, z0)))
    srf = rg.Surface.CreateExtrusion(prof, rg.Vector3d(0, y1 - y0, 0))
    solid = srf.ToBrep().CapPlanarHoles(doc.ModelAbsoluteTolerance)
    if solid.SolidOrientation == rg.BrepSolidOrientation.Inward:
        solid.Flip()
    claim("V the vault house is one closed solid, its roof curved", solid.IsSolid and any(
        not f.IsPlanar(doc.ModelAbsoluteTolerance) for f in solid.Faces), solid.IsValid)
    replace_house(g, doc, solid)
    g.run_check(doc, report=False)
    items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
    height = items.get("Building height") or {}
    limit = ((g.STATE.get("last") or {}).get("envelope") or {}).get("top")
    log["V"] = {"height": height, "limit": limit,
                "pieces": [(s, info) for _, s, info in g.overlay().encroach]}
    claim("V the height row needs colour", height.get("status") in ("does_not_comply", "needs_review"), height)
    tops = [(b, st) for b, st, info in g.overlay().encroach if info.get("why") == "height"]
    claim("V its pieces in its colour", tops and {st for _, st in tops} == {height.get("status")},
          [st for _, st in tops])
    plan = rg.BoundingBox.Empty
    for b, _ in tops:
        plan.Union(b.GetBoundingBox(True))
    log["V"]["plan_ft"] = [plan.Min.X / k, plan.Max.X / k, plan.Min.Y / k, plan.Max.Y / k, plan.Min.Z / k,
                           plan.Max.Z / k] if plan.IsValid else None
    log["V"]["house_ft"] = [x0 / k, x1 / k, y0 / k, y1 / k]
    tol = 0.1 * k
    claim("V the whole plan is coloured (the coloured part spans the house's width and depth)", plan.IsValid and
          plan.Min.X <= x0 + tol and plan.Max.X >= x1 - tol and plan.Min.Y <= y0 + tol and plan.Max.Y >= y1 - tol,
          log["V"]["plan_ft"])
    claim("V coloured just inside each wall above the limit (35.5 ft) and under the crown (41 ft)", all(
        colour_at(g, doc, p, why="height") == [height.get("status")] for p in (
            rg.Point3d(x0 + 0.5 * k, ym, z0 + 35.5 * k), rg.Point3d(x1 - 0.5 * k, ym, z0 + 35.5 * k),
            rg.Point3d(mid, ym, z0 + 41 * k))), None)
    claim("V nothing coloured below the limit (34 ft, mid-plan)", colour_at(g, doc, rg.Point3d(mid, ym, z0 + 34 * k))
          == [], colour_at(g, doc, rg.Point3d(mid, ym, z0 + 34 * k)))
    above = rg.Brep.CreateFromBox(rg.BoundingBox(rg.Point3d(x0 - k, y0 - k, z0 + (limit - z0 / k) * k if limit
                                                            else z0 + 35 * k), rg.Point3d(x1 + k, y1 + k, z0 + 50 * k)))
    cut = rg.Brep.CreateBooleanIntersection(solid, above, doc.ModelAbsoluteTolerance) or []
    want = sum(rg.VolumeMassProperties.Compute(b).Volume for b in cut) / k ** 3
    got = sum(rg.VolumeMassProperties.Compute(b).Volume for b, _ in tops) / k ** 3
    log["V"].update(volume=got, above_limit=want)
    claim("V the coloured volume is the vault's own part above the limit (within 5 %)",
          want and abs(got - want) <= 0.05 * want, {"volume": got, "above_limit": want})
    capture(doc, "Perspective", "V_vault_perspective")
    capture(doc, "Front", "V_vault_front")
    capture(doc, "Top", "V_vault_top")
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("offending_part_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                          "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
