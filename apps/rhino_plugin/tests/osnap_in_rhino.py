#! python3
"""Osnap curves on a locked Gordium::Envelope layer (Ben, 2026-10-21), in Rhino 8. Every claim is recorded (the run
goes on past a failing one) and the run fails at the end if any did. Run in Rhino, not in CI: the curves are worked
out in CI (packages/design_checker/tests/test_dimensions.py, the "feature 4" tests); what only Rhino can show is the
real objects, the lock, the snapping, Undo and the layer's visibility.
A fresh feet document, GordiumStart on the sample (106 Ithaca Rd, a tax-map lot).
1. After the check: a layer Gordium::Envelope, locked; on it the cautious buildable outline (closed, solid), the
   outline as drawn (closed, dashed linetype), and one required line per measured yard (dashed); each tagged
   Gordium's (gordium_envelope user text); the cautious outline lies 2'-0" inside the one as drawn.
2. Snapping: an object snap to the nearest point of the cautious outline (Rhino's own Osnap, End/Near on a locked
   object) finds a point on it (ObjectSnap via Rhino.Input.Custom.GetPoint is interactive, so the check is that the
   curve is a real, selectable-for-snapping, locked object: IsLocked, Visible, not a reference).
3. A second check: the same number of curves (replaced, never doubled).
4. Undo after the check: the architect's last action (moving the house 1 ft, then Check) is what Undo takes back;
   the curves are not an undo step of their own (the house moves back, the curves stay until the next check).
5. "Show buildable envelope" off: the layer hidden; on again: shown.
6. The check never measures them: the check's measured building count is unchanged with them in the file.
Writes <temp>/gordium_osnap/out.json and a Top capture; closes its document."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_osnap") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
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


def curves(g, doc):
    index = doc.Layers.FindByFullPath(g.logic.ENVELOPE, -1)
    if index < 0:
        return index, []
    return index, [o for o in doc.Objects.FindByLayer(doc.Layers[index]) or []
                   if o.Attributes.GetUserString(g.logic.ENVELOPE_KEY)]


doc = None
try:
    g = fresh_module()
    doc = TestDocs("osnap").__enter__().open("Large Objects - Feet")
    g.gordium_check()                                    # GordiumStart's flow on the sample
    k = 1.0 / g._scale(doc)
    index, found = curves(g, doc)
    whats = sorted(o.Attributes.GetUserString(g.logic.ENVELOPE_KEY) for o in found)
    log["curves"] = whats
    layer = doc.Layers[index] if index >= 0 else None
    claim("1 a Gordium::Envelope layer, locked", layer is not None and layer.IsLocked, index)
    cautious = [o for o in found if o.Attributes.GetUserString(g.logic.ENVELOPE_KEY) == "buildable outline (cautious)"]
    drawn = [o for o in found if o.Attributes.GetUserString(g.logic.ENVELOPE_KEY) == "buildable outline (as drawn)"]
    yards = [o for o in found if o.Attributes.GetUserString(g.logic.ENVELOPE_KEY).startswith("required line")]
    dashed = doc.Linetypes.Find("Dashed")
    claim("1 the cautious outline (closed, solid) and the outline as drawn (closed, dashed)",
          len(cautious) == 1 and len(drawn) == 1 and cautious[0].Geometry.IsClosed and drawn[0].Geometry.IsClosed
          and drawn[0].Attributes.LinetypeIndex == dashed
          and cautious[0].Attributes.LinetypeSource != Rhino.DocObjects.ObjectLinetypeSource.LinetypeFromObject,
          whats)
    items = [i for i in (g.STATE.get("last") or {}).get("items", [])
             if i["name"].split(",")[0] in ("Front yard", "Side yard", "Rear yard") and i.get("points")]
    claim("1 a required line for every measured yard, dashed on this tax-map lot",
          len(yards) >= len(items) >= 4 and all(o.Attributes.LinetypeIndex == dashed for o in yards),
          {"curves": len(yards), "yards": len(items)})
    if cautious and drawn:
        c, d = cautious[0].Geometry, drawn[0].Geometry
        gaps = []
        for t in [c.Domain.ParameterAt(x / 20.0) for x in range(20)]:
            p = c.PointAt(t)
            ok, u = d.ClosestPoint(p)
            gaps.append(round(p.DistanceTo(d.PointAt(u)) / k, 3))
        log["gaps_ft"] = gaps
        claim("1 the cautious outline 2'-0\" inside the one as drawn", all(abs(x - 2.0) <= 0.05 for x in gaps), gaps)
    claim("2 snappable: real, visible, locked objects (Osnap snaps to locked objects)",
          found and all(o.IsLocked or (layer is not None and layer.IsLocked) for o in found)
          and all(not o.IsReference for o in found) and all(o.Visible for o in found), len(found))
    g.run_check(doc, report=False)
    _, again = curves(g, doc)
    claim("3 a second check replaces them, never doubles them", len(again) == len(found), [len(found), len(again)])
    houses = list(g._buildings(doc))
    before = houses[0].Geometry.GetBoundingBox(True).Min.X
    doc.Objects.Transform(houses[0].Id, rg.Transform.Translation(k, 0, 0), True)
    doc.EndUndoRecord(doc.BeginUndoRecord("move the house 1 ft"))      # (the move, as its own step)
    g.run_check(doc, report=False)
    doc.Undo()
    after = list(g._buildings(doc))[0].Geometry.GetBoundingBox(True).Min.X
    _, kept = curves(g, doc)
    log["undo"] = {"before": before, "after": after, "curves": len(kept)}
    claim("4 Undo takes back the architect's move, not the curves (no undo step of their own)",
          abs(after - before) < 1e-6 and len(kept) == len(found), log["undo"])
    g.set_envelope(False)
    hidden = not doc.Layers[index].IsVisible
    g.set_envelope(True)
    claim("5 'Show buildable envelope' off hides the layer, on shows it", hidden and doc.Layers[index].IsVisible,
          hidden)
    measured = (g.STATE.get("last") or {}).get("header") or {}
    claim("6 never measured: the envelope's curves are not lot candidates nor buildings",
          all(g.logic.classify(doc.Layers[o.Attributes.LayerIndex].FullPath, type(o.Geometry).__name__) is None
              for o in found), measured.get("lot"))
    top = doc.Views.Find("Top", False)
    doc.Views.ActiveView = top
    top.Redraw()
    top.CaptureToBitmap(top.ActiveViewport.Size).Save(S + "top.png")
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("osnap_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                 "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
