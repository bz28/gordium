#! python3
import json, os, tempfile
import Rhino, Rhino.Geometry as rg, scriptcontext as sc, System
doc = Rhino.RhinoDoc.ActiveDoc
lot = None
for o in doc.Objects:
    if doc.Layers[o.Attributes.LayerIndex].FullPath == "Site" and isinstance(o.Geometry, rg.Curve):
        lot = o; break
bb = lot.Geometry.GetBoundingBox(True)
r = {"lot_bbox": [[bb.Min.X, bb.Min.Y], [bb.Max.X, bb.Max.Y]]}
cx, cy = bb.Min.X + 0.15 * (bb.Max.X - bb.Min.X), bb.Min.Y + 0.15 * (bb.Max.Y - bb.Min.Y)
attrs = Rhino.DocObjects.ObjectAttributes(); attrs.LayerIndex = doc.Layers.FindByFullPath("Default", -1); attrs.Name = "shed"
b = rg.Box(rg.Plane.WorldXY, rg.Interval(cx, cx + 8), rg.Interval(cy, cy + 8), rg.Interval(0, 8)).ToBrep()
r["shed"] = str(doc.Objects.AddBrep(b, attrs))
a2 = Rhino.DocObjects.ObjectAttributes(); a2.LayerIndex = doc.Layers.FindByFullPath("Default", -1); a2.Name = "terrain"
mx, my = (bb.Min.X + bb.Max.X) / 2, (bb.Min.Y + bb.Max.Y) / 2
mesh = rg.Mesh.CreateFromPlane(rg.Plane.WorldXY, rg.Interval(mx - 40, mx + 40), rg.Interval(my - 40, my + 40), 4, 4)
r["terrain"] = str(doc.Objects.AddMesh(mesh, a2))
json.dump(r, open(os.path.join(tempfile.gettempdir(), "extras.json"), "w"))
doc.Views.Redraw()
