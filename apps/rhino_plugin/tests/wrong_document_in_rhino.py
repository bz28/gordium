#! python3
"""GordiumStart with several documents open (run in Rhino, not in CI): the situation of Ben's first try, when
many test documents were open. Opens a feet and a meters document, then a fresh millimeters one in front, runs the
real GordiumStart command script there, and records for every open document what it holds on Gordium::Massing,
the layer's state and the house's box (model units and feet), and whether the house is in view. The house must be
in the document in front, and only there. Writes <temp>/gordium_wrong_doc/out.json."""
import json
import os
import runpy
import sys
import tempfile
import traceback

import Rhino
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs  # noqa: E402

WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT = os.path.join(tempfile.gettempdir(), "gordium_wrong_doc") + "/"
os.makedirs(OUT, exist_ok=True)
out = {}


def fresh_modules():
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


def massing(doc):
    index = doc.Layers.FindByFullPath("Gordium::Massing", -1)
    if index < 0:
        return {"layer": None, "objects": 0}
    layer = doc.Layers[index]
    objs = list(doc.Objects.FindByLayer(layer) or [])
    box = Rhino.Geometry.BoundingBox.Empty
    for o in objs:
        box.Union(o.Geometry.GetBoundingBox(True))
    k = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Feet)
    return {"layer": {"visible": layer.IsVisible, "locked": layer.IsLocked}, "objects": len(objs),
            "box_model": [round(v, 1) for v in (box.Min.X, box.Min.Y, box.Min.Z, box.Max.X, box.Max.Y, box.Max.Z)]
            if box.IsValid else None,
            "box_feet": [round(v * k, 2) for v in (box.Min.X, box.Min.Y, box.Min.Z, box.Max.X, box.Max.Y, box.Max.Z)]
            if box.IsValid else None,
            "in_view": {v.MainViewport.Name: bool(box.IsValid and v.ActiveViewport.IsVisible(box)) for v in doc.Views}}


try:
    fresh_modules()
    with TestDocs("wrong_doc") as docs:
        out["leftovers_closed"] = docs.left_over
        docs.open("Large Objects - Feet")
        docs.open("Large Objects - Meters")
        front = docs.open("Small Objects - Millimeters")          # the one the architect is looking at
        out["front"] = front.Path
        sc.sticky.setdefault("gordium_state", {})["auto_ok"] = True
        runpy.run_path(WT + "/apps/rhino_plugin/gordium_start.py", run_name="__main__")
        out["docs"] = {os.path.basename(d.Path or "untitled"): massing(d) for d in Rhino.RhinoDoc.OpenDocuments()}
        out["active_after"] = Rhino.RhinoDoc.ActiveDoc.Path
        front_name = os.path.basename(front.Path)
        out["house_only_in_front"] = (out["docs"][front_name]["objects"] == 3 and
                                      all(v["objects"] == 0 for n, v in out["docs"].items() if n != front_name))
except Exception:
    out["trace"] = traceback.format_exc()
json.dump(out, open(OUT + "out.json", "w"), indent=1, default=str)
