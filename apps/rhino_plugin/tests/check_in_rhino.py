#! python3
"""Run inside Rhino 8 (RunPythonScript), on a copy of a checked model (106 Ithaca Rd's spreadsheet_design_model
with its lot facts confirmed), after GordiumCheck. Checks what CI can't (the drawing and Rhino's own objects),
puts everything back, and prints PASS or what failed (also
written to gordium_check_in_rhino.txt in the temp folder). Never run it on a model you care about unsaved."""
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc

g = sys.modules["gordium_rhino"]
doc = Rhino.RhinoDoc.ActiveDoc
o = g.overlay()
saved = g.load_facts(doc)
st = sc.sticky["gordium_state"]
st["headless"] = True
problems, added = [], []


def expect(ok, what):
    if not ok:
        problems.append(what)


try:
    # a check that can't run clears the old result from the view
    g.run_check(doc, report=False)
    o.red = [rg.Sphere(rg.Point3d(0, 0, 0), 1).ToBrep()]
    g.save_facts(doc, {k: v for k, v in saved.items() if k != "zone"})
    expect(g.run_check(doc, report=False) is None and not o.red and o.envelope is None and
           "zone" in st["last"].get("error", ""), "a failed check left the old result")
    g.save_facts(doc, saved)

    # 2 ft toward the left side: only the failing side yard is drawn
    house = g._buildings(doc)[0]
    doc.Objects.Transform(house.Id, rg.Transform.Translation(-2, 0, 0), True)
    g.run_check(doc, report=False)
    labels = [d["label"] for d in st["last"]["dims"]]
    expect(labels == ["side yard smaller 8 ft, needs ≥ 10"], "dims: " + repr(labels))
    doc.Objects.Transform(g._buildings(doc)[0].Id, rg.Transform.Translation(2, 0, 0), True)

    # a block on the Building layer is reported: the building's rules need review
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = doc.Layers.FindName("Building").Index
    shed = rg.Box(rg.Plane.WorldXY, rg.Interval(70, 72), rg.Interval(80, 82), rg.Interval(0, 8)).ToBrep()
    idef = doc.InstanceDefinitions.Add("gordium_test_shed", "", rg.Point3d.Origin, [shed], [attrs])
    ref = doc.Objects.AddInstanceObject(idef, rg.Transform.Identity, attrs)
    added.append(ref)
    g.run_check(doc, report=False)
    rows = {r["Rule id"]: r["Error"] for r in st["last"]["rows"]}
    expect(rows.get("R-1b.lot_coverage") == "NEEDS REVIEW" and rows.get("R-1b.rear_yard") == "NEEDS REVIEW",
           "a block was dropped: " + repr(rows))
    doc.Objects.Delete(ref, True)
    added.remove(ref)
    doc.InstanceDefinitions.Delete(idef, True, True)

    # a SubD's red copy can be drawn
    sub = rg.SubD.CreateFromMesh(rg.Mesh.CreateFromBox(rg.BoundingBox(0, 0, 0, 1, 1, 1), 1, 1, 1))
    expect(isinstance(g._red_copy(sub), rg.Brep), "no red copy for a SubD")
except Exception:
    problems.append(traceback.format_exc())
finally:
    for i in added:
        doc.Objects.Delete(i, True)
    g.save_facts(doc, saved)
    st["headless"] = False
    g.run_check(doc, report=False)
    doc.Views.Redraw()
verdict = "PASS" if not problems else "FAILED:\n" + "\n".join(problems)
print(verdict)
with open(os.path.join(tempfile.gettempdir(), "gordium_check_in_rhino.txt"), "w") as f:   # for scripted runs
    f.write(verdict)
