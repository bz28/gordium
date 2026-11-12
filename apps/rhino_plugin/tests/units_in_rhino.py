#! python3
"""GordiumStart in Rhino's own templates, in every unit (run in Rhino, not in CI). For each template (millimeters,
meters, inches, feet) a fresh copy is opened through test_docs_in_rhino (closed when the run ends), the real GordiumStart command script
runs (the box accepted as an architect would: I confirm ticked), and this records the panel's results, the starting
house's size in feet and whether it is in view in every standard view. The results must be the same in every unit,
and the house visible everywhere. Writes <temp>/gordium_units/units_out.json and a capture per template and view.

How to run: in Rhino, RunPythonScript this file (it opens and leaves one document per template)."""
import json
import os
import runpy
import sys
import tempfile
import traceback
import types

import Rhino
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, look_up_106  # noqa: E402
import System

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(tempfile.gettempdir(), "gordium_units") + "/"
os.makedirs(OUT, exist_ok=True)
WANTED = ("Small Objects - Millimeters", "Large Objects - Millimeters", "Large Objects - Meters",
          "Small Objects - Inches", "Large Objects - Feet")


def run(name, docs):
    doc = docs.open(name)                      # a fresh copy of the template, the active document (or it raises)
    sc.sticky.setdefault("gordium_state", {})["auto_ok"] = True
    # the real command script, after typing 106 Ithaca Rd and pressing Look up (recorded): a new file waits for a
    # lookup since 2026-10-27 (the picks go in Gordium's state, the sticky dict, before the script loads it)
    look_up_106(types.SimpleNamespace(STATE=sc.sticky["gordium_state"]),
                lambda: runpy.run_path(WT + "/apps/rhino_plugin/gordium_start.py", run_name="__main__"))
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
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:                # its hooks, drawing and panel off before it is dropped
        loaded.off()
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
    with TestDocs("units") as docs:            # closes what it opens (the last stays active), and old leftovers
        out["leftovers_closed"] = docs.left_over
        for name in WANTED:
            try:
                out["runs"][name] = run(name, docs)
            except Exception:
                out["runs"][name] = {"trace": traceback.format_exc()}
    runs = [r for r in out["runs"].values() if "trace" not in r]
    first = runs[0] if runs else {}
    out["same_results"] = bool(runs) and len(runs) == len(out["runs"]) and all(r["summary"] == first.get("summary") and r["items"] == first.get("items") and
                              r["house_feet"] == first.get("house_feet") for r in runs)
    out["house_visible_everywhere"] = bool(runs) and all(all(r["visible"].values()) and r["visible"] for r in runs)
except Exception:
    out["trace"] = traceback.format_exc()
json.dump(out, open(OUT + "units_out.json", "w", encoding="utf-8"), indent=1, default=str)
