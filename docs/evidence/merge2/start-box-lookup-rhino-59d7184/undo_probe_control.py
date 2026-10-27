#! python3
import json, os, tempfile
import Rhino, Rhino.Geometry as rg, scriptcontext as sc
out = os.path.join(tempfile.gettempdir(), "undo_probe.json")
r = {}
try:
    doc = Rhino.RhinoDoc.CreateHeadless(None) if False else None
    import System
    app = Rhino.RhinoDoc.ActiveDoc
    # open a fresh doc as the tests do
    doc = Rhino.RhinoDoc.Open("/dev/null", ) if False else app
    r["incommand"] = Rhino.Commands.Command.InCommand()
    ids = []
    for i in range(2):
        s = doc.BeginUndoRecord("probe %d" % i)
        ids.append(str(doc.Objects.AddCurve(rg.LineCurve(rg.Point3d(0, -900 - i, 0), rg.Point3d(10, -900 - i, 0)))))
        doc.EndUndoRecord(s)
    Rhino.RhinoApp.RunScript("_Undo", False)
    r["after_one_undo"] = [doc.Objects.FindId(System.Guid(i)) is not None for i in ids]
    Rhino.RhinoApp.RunScript("_Redo", False)
    r["after_redo"] = [doc.Objects.FindId(System.Guid(i)) is not None for i in ids]
    for i in ids:
        doc.Objects.Delete(System.Guid(i), True)
except Exception as e:
    import traceback; r["err"] = traceback.format_exc()
json.dump(r, open(out, "w"))
