#! python3
"""The architect's answer key, drawn and checked in Rhino 8 (test_data/test_sites/new_york/ithaca_city/scenarios/;
run in Rhino, not in CI). Each scenario is drawn the way an architect draws it: the lot as a closed polyline on
the Site layer, each story a floor block on the Building layer (marked as GordiumStart marks its floors), other
solids on Default, spot grades as points on Gordium::Grade. Then the same check live mode runs; then the
scenario's edit (the house moved) and the check again. Records each step's panel view, plan and viewport
captures (Top and Perspective) to <temp>/gordium_scenarios/rhino_out.json and frames/.

Compare with the answer key (in the repo's .venv):  python -m design_checker.scenarios rhino <rhino_out.json>

How to run: open a new empty document (feet) that you don't mind being cleared (every object in it is deleted
before each scenario, and it is never saved), then RunPythonScript this file."""
import json
import os
import subprocess
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

S = os.path.join(tempfile.gettempdir(), "gordium_scenarios") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # the repo
FRAMES = S + "frames/"
if not os.path.isdir(FRAMES):
    os.makedirs(FRAMES)
log = {"scenarios": {}}


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
    state.update({"repo": WT, "extra_paths": []})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


def dump(g, path):
    """The scenario as JSON, from the same generator the code test uses (design_checker.scenarios)."""
    packages = os.path.join(WT, "packages")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(os.path.join(packages, n) for n in sorted(os.listdir(packages))
                                        if os.path.isdir(os.path.join(packages, n)))
    out = subprocess.check_output([g._python(), "-m", "design_checker.scenarios", "dump", path], cwd=WT, env=env,
                                  universal_newlines=True)
    return json.loads(out)


def capture(doc, name, box, view_name):
    view = doc.Views.Find(view_name, False) or doc.Views.ActiveView
    doc.Views.ActiveView = view
    view.Maximized = True
    view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    path = FRAMES + name + ".png"
    view.CaptureToBitmap(System.Drawing.Size(1280, 720)).Save(path)
    return path


def panel_rows(g):
    p = g.STATE.get("panel_parts")
    if p is None:
        return None
    out = []
    for group in p.get("groups") or []:
        out.append(["GROUP", str(group.Values[0])])
        for k in range(group.Children.Count):
            out.append([str(v) for v in group.Children[k].Values])
    return out


def draw(g, doc, data):
    """Every object of the scenario, drawn as an architect would; returns (lot, building ids)."""
    for o in list(doc.Objects):
        doc.Objects.Delete(o, True)
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = g._layer(doc, g.LAYERS["lot"])
    pts = [rg.Point3d(x, y, 0) for x, y in data["scenario"]["lot"]["points"]]
    lot = doc.Objects.AddPolyline(rg.Polyline(pts + pts[:1]), a)
    ids = []
    for s in data["solids"]["buildings"]:
        b = Rhino.DocObjects.ObjectAttributes()
        b.LayerIndex = g._layer(doc, g.LAYERS["building"])
        b.Name = s["name"]
        if s.get("floor") is not None:
            b.SetUserString(g.logic.FLOOR_KEY, s["name"].split()[-1] + ";" + repr(s["floor"]))
        ids.append(doc.Objects.AddBrep(g._prism(doc, s["outline"], s["base"], s["top"]), b))
    for s in data["solids"]["others"]:
        d = Rhino.DocObjects.ObjectAttributes()
        d.LayerIndex = g._layer(doc, "Default")
        d.Name = s["name"]
        doc.Objects.AddBrep(g._prism(doc, s["outline"], s["base"], s["top"]), d)
    grade = data["scenario"].get("grade") or {}
    for x, y, z in grade.get("points") or []:
        p = Rhino.DocObjects.ObjectAttributes()
        p.LayerIndex = g._layer(doc, g.GRADE_LAYER)
        doc.Objects.AddPoint(rg.Point3d(x, y, z), p)
    facts = {k: v for k, v in data["facts"].items() if k != "grade_points"}
    facts["lot_id"] = str(lot)
    g.save_facts(doc, facts)
    doc.Views.Redraw()
    return lot, ids


def step(g, doc, name, label, box):
    result = g.run_check(doc, report=False)
    last = g.STATE.get("last") or {}
    return {"step": label, "error": last.get("error"), "view": (result or {}).get("view"),
            "plan": (result or {}).get("plan"), "summary": last.get("view_summary"), "panel": panel_rows(g),
            "frames": [capture(doc, name + "_top", box, "Top"), capture(doc, name, box, "Perspective")]}


try:
    g = fresh_module()
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc.Path and "scratchpad" not in doc.Path and "gordium" not in doc.Path.lower():
        raise RuntimeError("refusing to clear " + doc.Path + ": open a new empty document first")
    folder = os.path.join(WT, "test_data/test_sites/new_york/ithaca_city/scenarios")
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".yaml"):
            continue
        name = f[:-5]
        data = dump(g, os.path.join(folder, f))
        lot, ids = draw(g, doc, data)
        box = doc.Objects.FindId(lot).Geometry.GetBoundingBox(True)
        box.Union(rg.Point3d(box.Center.X, box.Center.Y, 40))
        box.Inflate(8)
        steps = [step(g, doc, name, "as drawn", box)]
        then = data["scenario"].get("then")
        if then and then.get("move"):
            move = rg.Transform.Translation(then["move"][0], then["move"][1], 0)
            for i in ids:
                doc.Objects.Transform(i, move, True)
            steps.append(step(g, doc, name + "_moved", "after the edit", box))
        log["scenarios"][name] = steps
except Exception:
    log["trace"] = traceback.format_exc()
json.dump(log, open(S + "rhino_out.json", "w"), default=str, indent=1)
