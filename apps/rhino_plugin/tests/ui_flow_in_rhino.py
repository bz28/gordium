#! python3
"""The approved UI, in Rhino 8, in the order an architect meets it (docs/design/rhino_ui_spec.md; run in Rhino,
not in CI). From a new empty document:
1. GordiumCheck: the prefilled start box is the first thing (its fields recorded), then the site, the envelope
   and the largest legal starting building
2. Realistic edits, each re-checked as live mode does, then fixed: stretch the rear wall back, raise the roof,
   widen past the side yard, move one floor on its own, add a solid on the lot that isn't on the Building layer,
   place spot grades at the walls and then move the house
Each step records the summary, the panel's rows (as the panel shows them), the notice, and viewport captures
(Perspective and Top). Writes <temp>/gordium_ui_flow/flow_out.json and frames/NN_*.png.

How to run: in Rhino, open a new empty document (feet), then RunPythonScript this file (or rhinocode script)."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

S = os.path.join(tempfile.gettempdir(), "gordium_ui_flow") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # the repo
FRAMES = S + "frames/"
if not os.path.isdir(FRAMES):
    os.makedirs(FRAMES)
steps = []
log = {"steps": steps}


def fresh_module():
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    old = sys.modules.get("gordium_rhino")
    if old is not None:
        try:
            old.off()
        except Exception:
            pass
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


def capture(doc, name, box, view_name="Perspective"):
    view = doc.Views.Find(view_name, False) or doc.Views.ActiveView
    doc.Views.ActiveView = view
    view.Maximized = True
    if box is not None:
        view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    bmp = view.CaptureToBitmap(System.Drawing.Size(1280, 720))
    path = FRAMES + name + ".png"
    bmp.Save(path)
    return path


def panel_rows(g):
    """The rows exactly as the panel's TreeGridView holds them (mark, item, proposed, required, margin)."""
    p = g.STATE.get("panel_parts")
    if p is None:
        return None
    out = []
    for group in p.get("groups") or []:
        out.append(["GROUP", str(group.Values[0])])
        for k in range(group.Children.Count):
            out.append([str(v) for v in group.Children[k].Values])
    return out


def record(g, doc, name, caption, box, toasts_before):
    last = g.STATE.get("last") or {}
    steps.append({"name": name, "caption": caption, "frames": [capture(doc, name, box),
                                                              capture(doc, name + "_top", box, "Top")],
                  "summary": last.get("view_summary"), "state": last.get("state"), "error": last.get("error"),
                  "toasts": g.STATE.get("toasts", [])[toasts_before:], "header": last.get("header"),
                  "encroach": last.get("encroach"), "plan_encroach": last.get("plan_encroach"),
                  "envelope_notes": (last.get("envelope") or {}).get("notes"),
                  "envelope_outline": bool((last.get("envelope") or {}).get("outline")),
                  "items": [(i["name"], i["status"], i["proposed"], i["required"], i["margin"], i.get("reason"))
                            for i in last.get("items", [])],
                  "panel": panel_rows(g)})


try:
    g = fresh_module()
    doc = Rhino.RhinoDoc.ActiveDoc
    log["start_objects"] = doc.Objects.Count
    shown = {}

    def on_confirm(doc_, facts, text, state):
        shown["state"] = {k: v for k, v in state.items() if not k.startswith("_")}
        lot = g._find(doc_, facts.get("lot_id") or "")
        box = lot.Geometry.GetBoundingBox(True)
        box.Inflate(box.Diagonal.Length * 0.15)
        shown["box"] = box
        steps.append({"name": "01_box", "caption": "The prefilled start box appears first",
                      "frames": [capture(doc_, "01_box", box)], "box": shown["state"]})

    g.STATE["on_confirm"] = on_confirm
    g.gordium_check()                                   # an empty model: the start flow
    lot_box = shown["box"]
    lot_box.Union(rg.Point3d(lot_box.Center.X, lot_box.Center.Y, 40 / g._scale(doc)))
    record(g, doc, "02_building", "OK: the site, the envelope and the largest legal building", lot_box, 0)
    log["start"] = {k: v for k, v in (g.STATE.get("start") or {}).items() if k != "floors"}

    floors = g.STATE["start"]["floors"]
    ring = floors[0]["outline"]
    P = [g._model_point(doc, p) for p in ring]
    front_left, front_right, rear_right = P[3], P[0], P[1]
    across = rg.Vector3d(front_right - front_left)
    deep = rg.Vector3d(rear_right - front_right)
    width, depth = across.Length, deep.Length
    across.Unitize()
    deep.Unitize()
    plane = rg.Plane(front_left, across, deep)
    ft = 1.0 / g._scale(doc)

    def apply(ids, xform):
        for i in ids:
            doc.Objects.Transform(i, xform, True)
        doc.Views.Redraw()

    def edit(xform_of, label, caption, fix_caption, n):
        ids = [o.Id for o in g._buildings(doc)]
        before = len(g.STATE.get("toasts", []))
        xform, which = xform_of()
        targets = ids if which is None else [i for i in ids if doc.Objects.FindId(i).Attributes.Name == which]
        apply(targets, xform)
        g.run_check(doc, report=False)                  # what live mode runs half a second after the edit
        record(g, doc, "%02d_%s" % (n, label), caption, lot_box, before)
        before = len(g.STATE.get("toasts", []))
        apply(targets, xform.TryGetInverse()[1])
        g.run_check(doc, report=False)
        record(g, doc, "%02d_%s_fixed" % (n, label), fix_caption, lot_box, before)

    edit(lambda: (rg.Transform.Scale(plane, 1, (depth + 6 * ft) / depth, 1), None), "rear_wall",
         "Stretch the rear wall back 6 ft", "Pull the rear wall back in", 3)
    top = floors[-1]
    base_plane = rg.Plane(rg.Point3d(0, 0, top["base"] * ft), rg.Vector3d.ZAxis)
    edit(lambda: (rg.Transform.Scale(base_plane, 1, 1, (top["top"] - top["base"] + 3) / (top["top"] - top["base"])),
                  "Floor 3"), "roof", "Raise the roof 3 ft", "Bring the roof back down", 5)
    edit(lambda: (rg.Transform.Scale(plane, (width + 4 * ft) / width, 1, 1), None), "widen",
         "Widen the house 4 ft past the side yard", "Pull the side wall back in", 7)
    edit(lambda: (rg.Transform.Translation(across * 3 * ft), "Floor 2"), "one_floor",
         "Move one floor on its own, 3 ft sideways", "Move it back", 9)

    # a solid on the lot that isn't on the Building layer: the check says it isn't measured
    before = len(g.STATE.get("toasts", []))
    shed_box = rg.Box(rg.Plane(P[1] + deep * (6 * ft) + across * (-10 * ft), rg.Vector3d.ZAxis),   # behind the house
                      rg.Interval(0, 4 * ft), rg.Interval(0, 4 * ft), rg.Interval(0, 8 * ft))
    shed = doc.Objects.AddBrep(shed_box.ToBrep())
    g.run_check(doc, report=False)
    record(g, doc, "11_extra_solid", "A shed drawn on the default layer: not measured, so the check needs review",
           lot_box, before)
    doc.Objects.Delete(shed, True)
    g.run_check(doc, report=False)
    record(g, doc, "11_extra_solid_fixed", "The shed removed", lot_box, len(g.STATE.get("toasts", [])))

    # spot grades at the walls (level ground at 0): height is measured; then the house moves and they're off
    layer = g._layer(doc, g.GRADE_LAYER)
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = layer
    mids = [(P[k] + P[(k + 1) % 4]) / 2 for k in range(4)]
    centre = (P[0] + P[2]) / 2
    for m in mids:
        out = rg.Vector3d(m - centre)
        out.Unitize()
        doc.Objects.AddPoint(m + out * 1 * ft, a)
    facts = g.current_facts(doc)
    facts["grade_from"], facts["grade_is"] = "spot", "finished"      # finished ground placed at the walls
    facts.pop("ground_is_flat", None)
    facts.pop("grade_elevation", None)
    g.save_facts(doc, facts)
    g.run_check(doc, report=False)
    record(g, doc, "12_spot_grades", "Spot grades placed at the walls: the grade is set", lot_box,
           len(g.STATE.get("toasts", [])))
    ids = [o.Id for o in g._buildings(doc)]
    move = rg.Transform.Translation(deep * 8 * ft)
    before = len(g.STATE.get("toasts", []))
    apply(ids, move)
    g.run_check(doc, report=False)
    record(g, doc, "13_house_moved", "The house moved 8 ft back: the spot grades are no longer at its walls",
           lot_box, before)
    apply(ids, move.TryGetInverse()[1])
    g.run_check(doc, report=False)
    record(g, doc, "13_house_moved_fixed", "Moved back to the spot grades", lot_box, len(g.STATE.get("toasts", [])))
    # with the grade set, raising the roof is measured: over 35 ft, and red only above the limit
    edit(lambda: (rg.Transform.Scale(base_plane, 1, 1, (top["top"] - top["base"] + 3) / (top["top"] - top["base"])),
                  "Floor 3"), "roof_graded", "With the grade set: raise the roof 3 ft", "Bring it back down", 14)
except Exception:
    log["trace"] = traceback.format_exc()
json.dump(log, open(S + "flow_out.json", "w"), default=str, indent=1)
