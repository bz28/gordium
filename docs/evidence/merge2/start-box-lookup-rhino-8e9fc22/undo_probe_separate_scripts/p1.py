#! python3
import Rhino, Rhino.Geometry as rg, scriptcontext as sc, json, os, tempfile
doc = Rhino.RhinoDoc.ActiveDoc
ids = []
for i in range(2):
    s = doc.BeginUndoRecord("probe %d" % i)
    ids.append(str(doc.Objects.AddCurve(rg.LineCurve(rg.Point3d(0, -900 - i, 0), rg.Point3d(10, -900 - i, 0)))))
    doc.EndUndoRecord(s)
sc.sticky["probe_ids"] = ids
