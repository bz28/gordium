#! python3
"""Osnap curves on a locked Gordium::Envelope layer (Ben, 2026-10-21), in Rhino 8. Every claim is recorded (the run
goes on past a failing one) and the run fails at the end if any did. Run in Rhino, not in CI: the curves are worked
out in CI (packages/design_checker/tests/test_dimensions.py, the "feature 4" tests); what only Rhino can show is the
real objects, the lock, the snapping, Undo and the layer's visibility.
A fresh feet document, GordiumStart on 106 Ithaca Rd's recorded lookup (a tax-map lot).
1. After the check: a layer Gordium::Envelope, locked; on it the cautious buildable outline (closed, solid), the
   outline as drawn (closed, dashed linetype), and one required line per measured yard (dashed); each tagged
   Gordium's (gordium_envelope user text); the cautious outline lies 2'-0" inside the one as drawn.
2. Real curves Osnap can snap to: in the document, visible, on a locked layer, not reference geometry (snapping
   itself is interactive; Osnap snaps to locked objects).
3. A second check: the same number of curves (replaced, never doubled).
4. Undo recording is off while they are worked out and drawn (so Undo never stops on them).
5. "Show buildable envelope" off hides the layer, on shows it; a check with the layer hidden, and one with
   "Gordium" locked, still replace them (the same number, never piled up).
6. Never measured: none is a lot candidate or a building.
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
from test_docs_in_rhino import look_up_106  # noqa: E402

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
    return index, g._envelope_objects(doc, index)       # (hidden or locked too: FindByLayer may skip them)


doc = None
try:
    g = fresh_module()
    doc = TestDocs("osnap").__enter__().open("Large Objects - Feet")
    look_up_106(g, g.gordium_check)                      # GordiumStart: 106 Ithaca Rd looked up (recorded)
    k = 1.0 / g._scale(doc)
    index, found = curves(g, doc)
    whats = sorted(o.Attributes.GetUserString(g.logic.ENVELOPE_KEY) for o in found)
    log["curves"] = whats
    layer = doc.Layers[index] if index >= 0 else None
    claim("1 a Gordium::Envelope layer, locked", layer is not None and layer.IsLocked, index)
    cautious = [o for o in found if o.Attributes.GetUserString(g.logic.ENVELOPE_KEY) == "buildable outline (cautious)"]
    drawn = [o for o in found if o.Attributes.GetUserString(g.logic.ENVELOPE_KEY) == "buildable outline (as drawn, tax map)"]
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
    claim("2 real curves Osnap can snap to: in the document, visible, locked (not reference geometry)",
          found and all(not o.IsReference for o in found) and all(o.Visible for o in found)
          and layer is not None and layer.IsLocked, len(found))
    g.run_check(doc, report=False)
    _, again = curves(g, doc)
    claim("3 a second check replaces them, never doubles them", len(again) == len(found), [len(found), len(again)])
    # 3b. replacing them is no edit: with live mode's hooks on (a check turned them on), a check leaves the model
    # unchanged, so its results stay current (UX review 2026-10-27: they greyed out right after each Check)
    g.STATE["dirty"] = None
    g.run_check(doc, report=False)
    claim("3b a check's own redraw of them is no edit (the results stay current)",
          g.STATE.get("live") and g.STATE.get("dirty") is None, [g.STATE.get("live"), g.STATE.get("dirty")])
    # 4. none of it recorded for Undo: Undo recording is off while the curves are worked out and drawn
    real_curves, seen_undo = g.logic.envelope_curves, []

    def spy(plan):
        seen_undo.append(doc.UndoRecordingEnabled)
        return real_curves(plan)
    g.logic.envelope_curves = spy
    try:
        g.run_check(doc, report=False)
    finally:
        g.logic.envelope_curves = real_curves
    claim("4 Undo recording is off while they are replaced (the architect's Undo never stops on them)",
          seen_undo and not any(seen_undo), seen_undo)
    # 5. hidden, and under a locked "Gordium": still replaced, never piled up (review of feature 4, F1)
    g.set_envelope(False)
    hidden = not doc.Layers[index].IsVisible
    g.run_check(doc, report=False)
    _, while_hidden = curves(g, doc)
    g.set_envelope(True)
    claim("5 'Show buildable envelope' off hides the layer; on shows it", hidden and doc.Layers[index].IsVisible, hidden)
    root = doc.Layers[doc.Layers.FindByFullPath("Gordium", -1)]
    root.IsLocked = True
    try:
        g.run_check(doc, report=False)
        _, while_locked = curves(g, doc)
    finally:
        root.IsLocked = False
    claim("5 replaced, never piled up, with the layer hidden and with 'Gordium' locked",
          len(while_hidden) == len(found) and len(while_locked) == len(found),
          [len(found), len(while_hidden), len(while_locked)])
    ids = {o.Id for o in found}
    claim("6 never measured: none is a lot candidate or a building",
          not ids & {o.Id for o in g._lot_candidates(doc)} and not ids & {o.Id for o in g._buildings(doc)}, len(ids))
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
