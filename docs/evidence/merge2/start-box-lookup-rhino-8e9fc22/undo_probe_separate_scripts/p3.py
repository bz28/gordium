#! python3
import Rhino, System, scriptcontext as sc, json, os, tempfile
doc = Rhino.RhinoDoc.ActiveDoc
ids = sc.sticky.get("probe_ids", [])
r = [doc.Objects.FindId(System.Guid(i)) is not None for i in ids]
for i in ids:
    doc.Objects.Delete(System.Guid(i), True)
json.dump(r, open(os.path.join(tempfile.gettempdir(), "probe3.json"), "w"))
