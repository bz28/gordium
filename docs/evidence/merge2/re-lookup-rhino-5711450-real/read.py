#! python3
# READ-ONLY: no document change, no undo record.
import json, os, tempfile, sys
import Rhino, scriptcontext as sc
doc = Rhino.RhinoDoc.ActiveDoc
g = sys.modules.get("gordium_rhino")
st = sc.sticky.get("gordium_state", {})
r = {"doc": doc.Name, "count": doc.Objects.Count}
r["layers_vis"] = {l.FullPath: bool(l.IsVisible) for l in doc.Layers if (not l.IsDeleted) and l.FullPath.startswith("Gordium::Massing")}
r["curves"] = sum(1 for o in doc.Objects if o.Geometry.ObjectType.ToString() == "Curve")
r["names"] = sorted(str(o.Name) for o in doc.Objects)
try:
    r["labels_on"] = bool(st.get("labels_by_doc", {}).get(doc.RuntimeSerialNumber))
    r["labels_by_doc"] = {str(k): v for k, v in st.get("labels_by_doc", {}).items()}
except Exception as e:
    r["labels_err"] = repr(e)
last = st.get("last") or {}
r["check_header"] = (last.get("header") or {}).get("place")
r["check_items"] = [(i.get("name"), i.get("status")) for i in last.get("items", [])][:14]
r["dirty"] = st.get("dirty")
try:
    ui = g._ui_state(doc)
    r["ui_auto_check"] = ui.get("auto_check"); r["ui_labels"] = ui.get("labels")
except Exception as e:
    r["ui_err"] = repr(e)
json.dump(r, open(os.path.join(tempfile.gettempdir(), "real_read.json"), "w"), default=str, indent=1)
