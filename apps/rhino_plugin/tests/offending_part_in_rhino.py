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
1. A cantilever, amber. A 20 ft house where the starting house stood (its wall 12'-0 1/2" from the left line), its
   upper half (10 to 20 ft) reaching 6 ft out toward that line. The left side yard needs review (to the wall it
   complies, to the cantilever it doesn't): amber. Claims: the row needs review; its pieces amber only; a point in
   the cantilever (11 ft from the line, 15 ft up) is coloured; the point under it (11 ft, 5 ft up) is not.
2. A cantilever, red. The same house moved 5 ft toward the line (its wall 7'-0 1/2" from it), its cantilever 4 ft:
   short under every reading. Claims: the row does not comply; red and amber both drawn for it; in the
   cantilever (5 ft from the line, 15 ft up) red; under it (5 ft, 5 ft up) nothing; the house's own wall strip
   7.5 ft from the line, 5 ft up, red (within 8 ft: short however the line lies); 10 ft from it, amber.
3. A gable over the height limit. Walls to 30 ft, ridge 46 ft. Claims: the height row coloured in its colour; a
   point near the ridge (42 ft up) coloured by a height piece; the sky over the slope (44 ft up where the roof is
   38 ft, inside the uncut block) not; the height
   pieces' volume is the wedge above the limit, within 5 % (the uncut block would be twice it).
4. A curved vault over the limit (walls to 36 ft, a true arc to 42 ft): the height row needs review, never complies;
   coloured just inside each wall at 35.5 ft and under the crown at 41 ft; nothing below the limit; the coloured
   volume is the vault's own part above the limit, within 5 % (Rhino cuts the real solid to its own top).
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

S = os.path.join(tempfile.gettempdir(), "gordium_offending") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
log = {"claims": {}}
# the sample's left side yard, seen from the street: found by what it measures, the narrower side yard. Its row is
# named "Side yard, Southwest", or "Side yard, narrower" where the readings differ on which side is narrower (#18's
# readings of 106 do with the cantilever); a script looking for one name missed the other (demo 2c0a5c0 run).
SIDE_MEASURE = "side_yard_smaller"


def side_row(g, items):
    """The left side yard's row name and item: the row of the pieces drawn for the narrower side yard (else the row
    named for the southwest side, as before #18)."""
    rows = [info.get("row") for _, _, info in g.overlay().encroach if info.get("measure") == SIDE_MEASURE]
    name = next((r for r in rows if r in items), "Side yard, Southwest")
    return name, items.get(name) or {}


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

    # 1. the cantilever, amber (needs review)
    out = 6 * k
    items = scene("1", [(x0, z0), (x1, z0), (x1, z0 + 20 * k), (x0 - out, z0 + 20 * k), (x0 - out, z0 + 10 * k),
                        (x0, z0 + 10 * k)])
    SIDE, side = side_row(g, items)
    log["1"]["side_row"] = SIDE
    claim("1 the left side yard needs review (to the wall it complies, to the cantilever not)",
          side.get("status") == "needs_review", side)
    mine = {s for _, s, info in g.overlay().encroach if info.get("row") == SIDE}
    claim("1 its pieces are amber only", mine == {"needs_review"}, sorted(mine))
    wall = from_line(x0, ym)                             # the wall at mid-depth (the line is slanted)
    inside, under = at(wall - 1, 15), at(wall - 1, 5)
    log["1"].update(wall_ft=wall, inside=str(inside), under=str(under))
    claim("1 the cantilever is coloured (1 ft out from the wall, 15 ft up)",
          colour_at(g, doc, inside, row=SIDE) == ["needs_review"], colour_at(g, doc, inside))
    claim("1 the air under it is not (1 ft out from the wall, 5 ft up)", colour_at(g, doc, under) == [],
          colour_at(g, doc, under))
    capture(doc, "Perspective", "1_cantilever_amber_perspective")
    capture(doc, "Front", "1_cantilever_amber_front")

    # 2. the cantilever, red (does not comply): the house 5 ft nearer the line, a 4 ft cantilever
    out = 4 * k
    items = scene("2", [(x0, z0), (x1, z0), (x1, z0 + 20 * k), (x0 - out, z0 + 20 * k), (x0 - out, z0 + 10 * k),
                        (x0, z0 + 10 * k)], dx=-5 * k)
    SIDE, side = side_row(g, items)
    log["2"]["side_row"] = SIDE
    claim("2 the left side yard does not comply", side.get("status") == "does_not_comply", side)
    mine = {s for _, s, info in g.overlay().encroach if info.get("row") == SIDE}
    claim("2 red and amber both drawn for it", mine == {"does_not_comply", "needs_review"}, sorted(mine))
    start = x1 - 5 * k
    wall = from_line(x0 - 5 * k, ym)                     # the moved wall at mid-depth
    log["2"]["wall_ft"] = wall
    checks = {"in the cantilever (2 ft out from the wall, 15 ft up): red": (at(wall - 2, 15, start), ["does_not_comply"]),
              "under the cantilever (2 ft out, 5 ft up): nothing": (at(wall - 2, 5, start), []),
              "the house's own strip within 8 ft of the line (5 ft up): red": (at((wall + 8) / 2, 5, start),
                                                                               ["does_not_comply"]),
              "past 8 ft (10 ft from the line, 5 ft up): amber": (at(10, 5, start), ["needs_review"])}
    for what, (point, want) in checks.items():
        got = colour_at(g, doc, point, row=SIDE) if want else colour_at(g, doc, point)
        claim("2 " + what, got == want, {"point": str(point), "from_line_ft": round(from_line(point.X, point.Y), 3),
                                         "got": got})
    capture(doc, "Perspective", "2_cantilever_red_perspective")
    capture(doc, "Front", "2_cantilever_red_front")

    # 3. the gable over the height limit (back where the starting house stood)
    mid = (x0 + x1) / 2
    items = scene("3", [(x0, z0), (x1, z0), (x1, z0 + 30 * k), (mid, z0 + 46 * k), (x0, z0 + 30 * k)])
    height = items.get("Building height") or {}
    limit = ((g.STATE.get("last") or {}).get("envelope") or {}).get("top")
    claim("3 the height row needs colour", height.get("status") in ("does_not_comply", "needs_review"), height)
    tops = [(b, s) for b, s, info in g.overlay().encroach if info.get("why") == "height"]
    claim("3 its pieces in its colour", tops and {s for _, s in tops} == {height.get("status")},
          [s for _, s in tops])
    # the sky over the slope where the roof is 38 ft high (a quarter across): inside the uncut block (35 to 46 ft
    # over the strip where the roof is above the limit), outside the roof: coloured only if the cut failed
    ridge, sky = rg.Point3d(mid, ym, z0 + 42 * k), rg.Point3d(x0 + (x1 - x0) / 4, ym, z0 + 44 * k)
    claim("3 near the ridge (42 ft up) coloured", colour_at(g, doc, ridge, why="height") == [height.get("status")],
          colour_at(g, doc, ridge))
    claim("3 the sky over the slope (44 ft up where the roof is 38 ft) not", colour_at(g, doc, sky) == [],
          colour_at(g, doc, sky))
    volume = sum(rg.VolumeMassProperties.Compute(b).Volume for b, _ in tops) / k ** 3
    rise = 46 - (limit - z0 / k) if limit is not None else None
    wedge = 0.5 * ((x1 - x0) / k * rise / 16) * rise * (y1 - y0) / k if rise else None
    claim("3 the height pieces' volume is the wedge above the limit (within 5 %)",
          wedge and abs(volume - wedge) <= 0.05 * wedge, {"volume": volume, "wedge": wedge, "limit": limit})
    capture(doc, "Perspective", "3_gable_perspective")
    capture(doc, "Front", "3_gable_front")

    # 4. a curved vault over the limit (the coordinator's probe at fc0b023): walls to 36 ft, a true arc to 42 ft.
    # The checker reads only the flat faces (the vault is a curved surface: height needs review); Rhino cuts the
    # real solid from the limit to its own top
    wall, crown = 36 * k, 42 * k
    p3 = lambda x, z: rg.Point3d(x, y0, z)                              # noqa: E731
    prof = rg.PolyCurve()
    prof.Append(rg.LineCurve(p3(x0, z0), p3(x1, z0)))
    prof.Append(rg.LineCurve(p3(x1, z0), p3(x1, z0 + wall)))
    prof.Append(rg.ArcCurve(rg.Arc(p3(x1, z0 + wall), p3(mid, z0 + crown), p3(x0, z0 + wall))))
    prof.Append(rg.LineCurve(p3(x0, z0 + wall), p3(x0, z0)))
    vault = rg.Surface.CreateExtrusion(prof, rg.Vector3d(0, y1 - y0, 0)).ToBrep().CapPlanarHoles(
        doc.ModelAbsoluteTolerance)
    if vault.SolidOrientation == rg.BrepSolidOrientation.Inward:
        vault.Flip()
    claim("4 the vault house is one closed solid, its roof curved", vault.IsSolid and any(
        not f.IsPlanar(doc.ModelAbsoluteTolerance) for f in vault.Faces), vault.IsValid)
    replace_house(g, doc, vault)
    g.run_check(doc, report=False)
    items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
    height = items.get("Building height") or {}
    limit = ((g.STATE.get("last") or {}).get("envelope") or {}).get("top")
    claim("4 the height row needs review (the curved vault is not measured), never complies",
          height.get("status") == "needs_review", height)
    tops = [(b, s) for b, s, info in g.overlay().encroach if info.get("why") == "height"]
    lo = z0 + ((limit - z0 / k) if limit is not None else 35) * k      # the limit, in model units
    claim("4 coloured just inside each wall above the limit (+0.5 ft) and under the crown (41 ft)", all(
        colour_at(g, doc, p, why="height") == [height.get("status")] for p in (
            rg.Point3d(x0 + 0.5 * k, ym, lo + 0.5 * k), rg.Point3d(x1 - 0.5 * k, ym, lo + 0.5 * k),
            rg.Point3d(mid, ym, z0 + 41 * k))), [colour_at(g, doc, rg.Point3d(mid, ym, z0 + 41 * k))])
    claim("4 nothing coloured below the limit (1 ft under it, mid-plan)",
          colour_at(g, doc, rg.Point3d(mid, ym, lo - k)) == [], colour_at(g, doc, rg.Point3d(mid, ym, lo - k)))
    above = rg.Brep.CreateFromBox(rg.BoundingBox(rg.Point3d(x0 - k, y0 - k, lo), rg.Point3d(x1 + k, y1 + k, z0 + 50 * k)))
    cut = rg.Brep.CreateBooleanIntersection(vault, above, doc.ModelAbsoluteTolerance) or []
    want = sum(rg.VolumeMassProperties.Compute(b).Volume for b in cut) / k ** 3
    got = sum(rg.VolumeMassProperties.Compute(b).Volume for b, _ in tops) / k ** 3
    claim("4 the coloured volume is the vault's own part above the limit (within 5 %)",
          want and abs(got - want) <= 0.05 * want, {"volume": got, "above_limit": want})
    capture(doc, "Perspective", "4_vault_perspective")
    capture(doc, "Front", "4_vault_front")
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
