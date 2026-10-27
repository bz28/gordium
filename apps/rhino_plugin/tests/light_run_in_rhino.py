#! python3
"""Queue item 12, light run: one real address per residential district (test_data/test_sites/new_york/ithaca_city/
light_run/expected.yaml), each taken through the real start flow in Rhino 8 and compared with the result worked out
by hand from the law. Needs the address lookup (#19 start-box-lookup) in the checkout: run it on a branch that has
it (the demo branch). Live lookups: it asks the City's and the State's services, as an architect's Draw does.

For each site, a fresh feet document:
  1. GordiumStart with the address typed and Look up pressed, then Draw (the scripted picks the in-Rhino tests use).
     Claims: the zone, the lot area drawn (to 0.5 sf of `drawn_area_sf`) and corner lot are the expected ones.
  2. After Draw: no row does not comply; every needs-review row carries a reason. Every row is recorded, for a person
     to compare with `largest_house` (which rule limits the starting house) and `lot_size`.
  3. The nudge: the house's solids moved toward the street until their least distance to the street lines (measured
     here, from the solids) is the nudge's `proposed_ft`; the check again. Claim: the nudge's rule does not comply
     and no other row does; the rows are recorded with their proposed and required values.
Writes <temp>/gordium_light_run/out.json (each site's facts, rows and claims) and a Top capture per site.
Not yet run in Rhino (Lane C). A failed claim is recorded and the run goes on to the next site."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_light_run") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
EXPECTED = os.path.join(WT, "test_data/test_sites/new_york/ithaca_city/light_run/expected.yaml")
log = {"sites": {}}


def fresh_module():
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


def load_expected(g):
    """The expected results, read by the repo's own Python (Rhino's may not have PyYAML), as scenarios_in_rhino does."""
    import subprocess
    code = "import json, sys, yaml; print(json.dumps(yaml.safe_load(open(sys.argv[1], encoding='utf-8'))))"
    out = g.ui.spawn([g._python(), "-c", code, EXPECTED], run=True, cwd=WT, stdout=subprocess.PIPE, check=True,
                     universal_newlines=True, encoding="utf-8").stdout
    return json.loads(out)


def lot_area(doc, g):
    layer = doc.Layers.FindByFullPath(g.LAYERS["lot"], -1)
    areas = [Rhino.Geometry.AreaMassProperties.Compute(o.Geometry).Area for o in doc.Objects
             if o.Attributes.LayerIndex == layer and isinstance(o.Geometry, rg.Curve) and o.Geometry.IsClosed]
    return max(areas) if areas else None


def front_distance(doc, g, facts):
    """The house's least distance to the street line in plan, from its own vertices (independent of the panel)."""
    pts = [rg.Point3d(v.Location.X, v.Location.Y, 0) for o in massing(doc, g) for v in o.Geometry.Vertices]
    return min(ln.DistanceTo(p, True) for ln in street_lines(facts) for p in pts) if pts else None


def rows(g):
    return list((g.STATE.get("last") or {}).get("items") or [])


def row_for(items, rule):
    return [i for i in items if i.get("rule") == rule]


def massing(doc, g):
    layer = doc.Layers.FindByFullPath(g.LAYERS["building"], -1)
    return [o for o in doc.Objects if o.Attributes.LayerIndex == layer and o.ObjectType == Rhino.DocObjects.ObjectType.Brep]


def street_lines(facts):
    return [rg.Line(rg.Point3d(a[0], a[1], 0), rg.Point3d(b[0], b[1], 0)) for a, b in facts["street_line"]]


def toward_street(doc, g, facts):
    """The unit vector from the house's plan centre to the nearest point of any street line."""
    pts = [rg.Point3d(v.Location.X, v.Location.Y, 0) for o in massing(doc, g) for v in o.Geometry.Vertices]
    c = rg.Point3d(sum(p.X for p in pts) / len(pts), sum(p.Y for p in pts) / len(pts), 0)
    near = min((ln.ClosestPoint(c, True) for ln in street_lines(facts)), key=lambda q: q.DistanceTo(c))
    v = near - c
    v.Unitize()
    return v


def one_site(g, docs, district, site):
    out = {"claims": {}}

    def claim(name, ok, detail=None):
        out["claims"][name] = {"ok": bool(ok), "detail": detail}

    doc = docs.open("Large Objects - Feet")
    try:
        g.STATE.update(box_picks=["lookup"], box_overrides={"address": site["address"]})
        g.gordium_start()
        facts = g.current_facts(doc)
        out["facts"] = {k: facts.get(k) for k in ("address", "zone", "lot_surveyed", "corner_lot", "street_line")}
        lot = site["lot"]
        claim("zone", facts.get("zone") == site["zone"]["expect"], facts.get("zone"))
        claim("corner lot: no", facts.get("corner_lot") is False, facts.get("corner_lot"))
        items = rows(g)
        out["drawn"] = [(i.get("rule"), i["name"], i["status"], i.get("proposed"), i.get("required"), i.get("reason"))
                        for i in items]
        drawn_area = lot_area(doc, g)
        # drawn_area_sf: the area of the outline as stored (corners to 0.01 ft), which is what Rhino draws; the
        # lookup's own area_sf is from the unrounded outline and can differ by about 1 sf
        claim("lot area as drawn from the tax map's corners (to 0.5 sf)", drawn_area is not None and
              abs(drawn_area - lot["drawn_area_sf"]) <= 0.5, drawn_area)
        claim("after Draw no row does not comply", not [i for i in items if i["status"] == "does_not_comply"],
              [i["name"] for i in items if i["status"] == "does_not_comply"])
        claim("every needs-review row says why", all(i.get("reason") for i in items if i["status"] == "needs_review"),
              [i["name"] for i in items if i["status"] == "needs_review" and not i.get("reason")])
        nudge = site["expected"]["nudge"]
        front = row_for(items, nudge["rule"])
        have = front_distance(doc, g, facts)
        out["front_before"] = {"row": front[0].get("proposed") if front else None, "measured_here": have}
        if have is not None:
            move = rg.Transform.Translation(toward_street(doc, g, facts) * (have - nudge["proposed_ft"]))
            for o in massing(doc, g):
                doc.Objects.Transform(o.Id, move, True)
            g.run_check(doc, report=False)
            after = rows(g)
            out["nudged"] = [(i.get("rule"), i["name"], i["status"], i.get("proposed"), i.get("required")) for i in after]
            out["front_after_measured_here"] = front_distance(doc, g, facts)
            hit = row_for(after, nudge["rule"])
            claim("the nudge fails exactly its rule", hit and hit[0]["status"] == "does_not_comply" and not [
                i for i in after if i["status"] == "does_not_comply" and i.get("rule") != nudge["rule"]],
                [(i.get("rule"), i["status"]) for i in after if i["status"] == "does_not_comply"])
        else:
            claim("the house is on the Building layer (to work out the nudge)", False, front)
        view = doc.Views.Find("Top", False) or doc.Views.ActiveView
        bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
        if bmp is not None:
            bmp.Save(S + district + "_top.png")
    except Exception:
        out["trace"] = traceback.format_exc()
    finally:
        try:
            close(doc)
        except Exception:
            pass
    return out


docs = TestDocs("lightrun").__enter__()
try:
    g = fresh_module()
    expected = load_expected(g)
    for district, site in expected["sites"].items():
        log["sites"][district] = one_site(g, docs, district, site)
except Exception:
    log["trace"] = traceback.format_exc()
json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
