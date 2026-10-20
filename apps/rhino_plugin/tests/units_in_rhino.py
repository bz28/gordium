#! python3
"""GordiumStart in Rhino's own templates, in every unit (run in Rhino, not in CI). For each template (millimeters,
meters, inches, feet) a fresh copy is opened as a new document (never saved), the real GordiumStart command script
runs (the box accepted as an architect would: I confirm ticked), and this records the panel's results, the starting
house's size in feet and whether it is in view in every standard view. The results must be the same in every unit,
and the house visible everywhere. Writes <temp>/gordium_units/units_out.json and a capture per template and view.

How to run: in Rhino, RunPythonScript this file (it opens and leaves one document per template)."""
import glob
import json
import os
import runpy
import shutil
import sys
import tempfile
import time
import traceback

import Rhino
import scriptcontext as sc
import System

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(tempfile.gettempdir(), "gordium_units") + "/"
os.makedirs(OUT, exist_ok=True)
WANTED = ("Small Objects - Millimeters", "Large Objects - Millimeters", "Large Objects - Meters",
          "Small Objects - Inches", "Large Objects - Feet")


def templates():
    folder = Rhino.ApplicationSettings.FileSettings.TemplateFolder
    found = {}
    for path in glob.glob(os.path.join(folder, "*.3dm")) + glob.glob(
            "/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources/en.lproj/"
            "Template Files/*.3dm"):
        name = os.path.splitext(os.path.basename(path))[0]
        if name in WANTED and name not in found:
            found[name] = path
    return found


def run(name, path):
    copy = OUT + name.replace(" ", "_") + "_%d.3dm" % int(time.time() * 1000)   # a new file: never one already open
    shutil.copy(path, copy)
    Rhino.RhinoDoc.Open(copy)
    doc = Rhino.RhinoDoc.ActiveDoc
    if os.path.realpath(doc.Path or "") != os.path.realpath(copy):      # never measure another document by mistake
        raise RuntimeError("the opened copy is not the active document: " + str(doc.Path))
    sc.sticky.setdefault("gordium_state", {})["auto_ok"] = True
    runpy.run_path(WT + "/apps/rhino_plugin/gordium_start.py", run_name="__main__")
    g = sys.modules["gordium_rhino"]
    house = Rhino.Geometry.BoundingBox.Empty
    for o in g._buildings(doc):
        house.Union(o.Geometry.GetBoundingBox(True))
    k = g._scale(doc)
    last = g.STATE.get("last") or {}
    visible, frames = {}, []
    for view_name in ("Top", "Front", "Right", "Perspective"):
        view = doc.Views.Find(view_name, False)
        if view is None:
            continue
        visible[view_name] = bool(house.IsValid and view.ActiveViewport.IsVisible(house))
        path_png = OUT + name.replace(" ", "_") + "_" + view_name + ".png"
        view.Redraw()
        view.CaptureToBitmap(System.Drawing.Size(900, 540)).Save(path_png)
        frames.append(path_png)
    return {"units": str(doc.ModelUnitSystem), "summary": last.get("view_summary"), "error": last.get("error"),
            "items": [[i["name"], i["status"], i["proposed"]] for i in last.get("items", [])],
            "house_feet": [round(v * k, 3) for v in (house.Min.X, house.Min.Y, house.Min.Z, house.Max.X, house.Max.Y,
                                                      house.Max.Z)] if house.IsValid else None,
            "visible": visible, "frames": frames}


def fresh_modules():
    """This copy's code as it is on disk now (the same steps as the other in-Rhino tests): a module loaded
    earlier in the session would otherwise keep running."""
    state = sc.sticky.setdefault("gordium_state", {})
    worker = state.pop("worker", None)
    if worker is not None:
        worker.terminate()
    old = sys.modules.get("gordium_rhino")
    if old is not None:
        try:
            old.off()
        except Exception:
            pass
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui", "_gordium_load"):
        sys.modules.pop(name, None)
    state.clear()


out = {"runs": {}}
try:
    fresh_modules()
    for name, path in sorted(templates().items()):
        try:
            out["runs"][name] = run(name, path)
        except Exception:
            out["runs"][name] = {"trace": traceback.format_exc()}
    runs = [r for r in out["runs"].values() if "trace" not in r]
    first = runs[0] if runs else {}
    out["same_results"] = bool(runs) and len(runs) == len(out["runs"]) and all(r["summary"] == first.get("summary") and r["items"] == first.get("items") and
                              r["house_feet"] == first.get("house_feet") for r in runs)
    out["house_visible_everywhere"] = bool(runs) and all(all(r["visible"].values()) and r["visible"] for r in runs)
except Exception:
    out["trace"] = traceback.format_exc()
json.dump(out, open(OUT + "units_out.json", "w"), indent=1, default=str)
