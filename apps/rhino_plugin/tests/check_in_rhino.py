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
problems, added, hidden = [], [], []


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

    # a hidden building still counts (never a pass by hiding it)
    house = g._buildings(doc)[0]
    doc.Objects.Hide(house.Id, True)
    hidden.append(house.Id)
    g.run_check(doc, report=False)
    rows = {r["Rule id"]: r["Error"] for r in st["last"].get("rows", [])}
    doc.Objects.Show(house.Id, True)
    expect(rows.get("R-1b.lot_coverage") == "FAIL", "a hidden house was left out: " + repr(rows))

    # saved facts that can't be read: a plain refusal, and checks keep running afterwards
    doc.Strings.SetString(g.SECTION, g.ENTRY, "{bad")
    expect(g.run_check(doc, report=False) is None and st.get("running") is False and "can't be read" in
           st["last"].get("error", ""), "unreadable facts: " + repr(st.get("last")))
    g.save_facts(doc, saved)

    # a lot that is no longer in the model is asked again (its street line goes with it)
    g.save_facts(doc, dict(saved, lot_id="00000000-0000-0000-0000-000000000000"))
    stale = g.current_facts(doc)
    expect("lot_id" not in stale and "street_line" in g.logic.missing(stale), "stale lot kept: " + repr(stale))
    g.save_facts(doc, saved)

    # an extrusion main building can be outlined in the confirm dialog
    ext = rg.Extrusion.Create(rg.PolylineCurve([rg.Point3d(0, 0, 0), rg.Point3d(1, 0, 0), rg.Point3d(1, 1, 0),
                                                rg.Point3d(0, 0, 0)]), 3, True)
    expect(isinstance(g._drawable(ext), rg.Brep), "an extrusion can't be outlined")

    # another document in front: nothing of this one's result stays listed
    g.run_check(doc, report=False)
    g._new_document(None, None)
    expect("rows" not in st["last"] and o.message is None and not o.red, "results kept for another document")

    # saved facts that are valid JSON but not lot facts: the same plain refusal
    doc.Strings.SetString(g.SECTION, g.ENTRY, "5")
    try:
        g.current_facts(doc)
        problems.append("facts '5' were accepted")
    except ValueError:
        pass
    g.save_facts(doc, saved)

    # saved facts with a value of the wrong kind: the same plain refusal (checked like a facts file)
    doc.Strings.SetString(g.SECTION, g.ENTRY, '{"zone": "R-1b", "grade_elevation": "abc"}')
    try:
        g.current_facts(doc)
        problems.append("facts with grade_elevation 'abc' were accepted")
    except ValueError:
        pass
    g.save_facts(doc, saved)

    # confirming facts never shows an earlier result, even one stamped for another document
    g.run_check(doc, report=False)
    o.doc = -1
    st["auto_ok"] = True
    g.confirm(doc, saved, {"uses": {}, "zones": ["R-1b"]})
    st.pop("auto_ok", None)
    expect(o.message is None and not o.red and o.envelope is None, "confirm showed an earlier result")

    # a checker that fails (an old one that doesn't know a request) never makes saved facts look unreadable
    class Stub:
        def __init__(self):
            import io
            self.stdin, self.stdout = io.StringIO(), io.StringIO('{"ok": false, "error": "unknown command"}\n')

        def poll(self):
            return None
    real, code = st.get("worker"), st.get("worker_code")
    st["worker"], st["worker_code"] = Stub(), g.logic.code_fingerprint(g.os.path.join(g.REPO, "packages"))
    try:
        g.current_facts(doc)
        problems.append("a failing checker's answer was accepted")
    except RuntimeError:
        pass
    except ValueError:
        problems.append("a failing checker made the saved facts look unreadable")
    finally:
        st["worker"], st["worker_code"] = real, code
    expect(g.load_facts(doc).get("sleeping_rooms") == saved.get("sleeping_rooms"), "saved facts changed")

    # Esc at a prompt cancels the whole edit: nothing is saved
    g.save_facts(doc, saved)
    real_ask = g._ask_zone
    try:
        g._ask_zone = lambda *a: (g.Rhino.Commands.Result.Cancel, "")       # Esc at the first prompt
        expect(g.change_facts(doc, saved, {"zones": ["R-1b"], "uses": {}}) is None, "Esc didn't cancel the edit")
    finally:
        g._ask_zone = real_ask
    expect(g.load_facts(doc) == saved, "a cancelled edit changed the saved facts")

    # a pick prompt never takes what is already selected, only lets candidates be clicked, and asks once
    class FakeGet:
        made = []

        def __init__(self):
            self.preselect, self.filter = True, None
            FakeGet.made.append(self)

        def SetCommandPrompt(self, text):
            pass

        def EnablePreSelect(self, on, ignore_unacceptable):
            self.preselect = on

        def SetCustomGeometryFilter(self, f):
            self.filter = f

        def Get(self):              # Rhino hands back a selected object at once when pre-selection is on
            return g.Rhino.Input.GetResult.Object if self.preselect else g.Rhino.Input.GetResult.Nothing

        def Object(self, i):
            class Ref:
                ObjectId = lot_curve.Id
            return Ref()
    lot_curve = g._sorted_objects(doc)[0][0]
    doc.Objects.Select(lot_curve.Id)            # the lot left selected by the lot prompt
    real_new = g._new_get_object
    try:
        g._new_get_object = FakeGet
        got = g._pick(doc, "Click the main building", g._sorted_objects(doc)[1])
        expect(got is None and len(FakeGet.made) == 1 and not FakeGet.made[0].preselect
               and FakeGet.made[0].filter is not None, "a pick prompt took the selection or asked again")
    finally:
        g._new_get_object = real_new
        doc.Objects.UnselectAll()

    # an import into this model is an edit: its result stays until the re-check
    g.run_check(doc, report=False)

    class Opened:
        Merge, Reference = True, False
    g._opened(None, Opened())
    expect("rows" in st["last"] and o.message is not None, "an import cleared this model's result")

    # drawn only in the document checked
    class View:
        class RhinoDoc:
            RuntimeSerialNumber = -1
    expect(not g._here(o, View()), "drawn in another document's viewport")

    # GordiumOff, then GordiumLive: another document still clears the drawing
    g.off()
    expect(o.message is None and not o.red and o.envelope is None, "GordiumOff left the result")
    g.toggle_live()
    g.run_check(doc, report=False)
    expect(st.get("doc_hooks") is not None, "no document hooks after GordiumOff then GordiumLive")

    # a SubD's red copy can be drawn
    sub = rg.SubD.CreateFromMesh(rg.Mesh.CreateFromBox(rg.BoundingBox(0, 0, 0, 1, 1, 1), 1, 1, 1))
    expect(isinstance(g._red_copy(sub), rg.Brep), "no red copy for a SubD")
except Exception:
    problems.append(traceback.format_exc())
finally:
    for i in added:
        doc.Objects.Delete(i, True)
    for i in hidden:
        doc.Objects.Show(i, True)
    g.save_facts(doc, saved)
    st["headless"] = False
    g.run_check(doc, report=False)
    doc.Views.Redraw()
verdict = "PASS" if not problems else "FAILED:\n" + "\n".join(problems)
print(verdict)
with open(os.path.join(tempfile.gettempdir(), "gordium_check_in_rhino.txt"), "w") as f:   # for scripted runs
    f.write(verdict)
