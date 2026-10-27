#! python3
import Rhino, Rhino.Geometry as rg, scriptcontext as sc, System
doc = Rhino.RhinoDoc.ActiveDoc
for o in list(doc.Objects):
    if o.Name == "terrain":
        doc.Objects.Delete(o, True)
a2 = Rhino.DocObjects.ObjectAttributes(); a2.LayerIndex = doc.Layers.FindByFullPath("Default", -1); a2.Name = "terrain"
mesh = rg.Mesh.CreateFromPlane(rg.Plane.WorldXY, rg.Interval(-20, 100), rg.Interval(-20, 125), 6, 6)
doc.Objects.AddMesh(mesh, a2)
doc.Views.Redraw()
