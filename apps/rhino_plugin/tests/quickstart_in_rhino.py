#! python3
"""QUICKSTART's "Test it yourself", in Rhino 8 (apps/rhino_plugin/QUICKSTART.md; the same numbers are checked in
code by packages/design_checker/tests/test_quickstart.py). Run in Rhino, not in CI.

From a fresh document (Rhino's feet template): GordiumStart's flow on the sample lot, then each test's edit made in
the model, checked as live mode checks it, compared with what the guide says, captured (Top view), and undone.
Test 14 starts again in a millimeter template and compares every row with the feet run. Writes
<temp>/gordium_quickstart/out.json (each test: expected, got, match) and frames/NN_*.png; closes its documents.
Keep another document open while it runs (Rhino keeps the last document's window)."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_quickstart") + "/"
FRAMES = S + "frames/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(FRAMES, exist_ok=True)
tests = []
log = {"tests": tests}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:                # its hooks, drawing and panel off before it is dropped
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


g = fresh_module()
docs = TestDocs("quickstart").__enter__()
opened = []


def items():
    return {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(FRAMES + name + ".png")


def check(doc, n, title, expected):
    """expected: {item name: {field: value}}, as the guide says it. Records what the panel has."""
    g.run_check(doc, report=False)
    got_items = items()
    got, ok = {}, True
    for name, fields in expected.items():
        row = got_items.get(name) or {}
        got[name] = {f: row.get(f) for f in fields}
        for f, want in fields.items():
            have = row.get(f)
            if not (have == want or (f in ("reason",) and want in (have or ""))):
                ok = False
    tests.append({"n": n, "test": title, "expected": expected, "got": got, "match": ok,
                  "summary": (g.STATE.get("last") or {}).get("view_summary"),
                  "toasts": g.STATE.get("toasts", [])[-1:]})
    capture(doc, "%02d_%s" % (n, title.split(":")[0].replace(" ", "_")[:30]))
    return ok


def setfacts(doc, **kw):
    facts = g.current_facts(doc)
    for k, v in kw.items():
        if v is None:
            facts.pop(k, None)
        else:
            facts[k] = v
    g.save_facts(doc, facts)


try:
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)
    g.STATE["on_confirm"] = lambda *a: None
    g.gordium_check()                                         # GordiumStart's flow on an empty file
    ft = 1.0 / g._scale(doc)
    ring = g.STATE["start"]["floors"][0]["outline"]
    log["house"] = ring
    floors = sorted(g._buildings(doc), key=lambda o: o.Attributes.Name or "")
    ids = [o.Id for o in floors]
    top_floor = [o.Id for o in floors if o.Attributes.Name == "Floor 3"]
    north, east = rg.Vector3d(0, ft, 0), rg.Vector3d(ft, 0, 0)

    def xf(targets, t):
        for i in targets:
            doc.Objects.Transform(i, t, True)

    def undo(targets, t):
        xf(targets, t.TryGetInverse()[1])

    def stretch(targets, axis, at, by):
        """Move one face: everything at or past `at` (model units, along `axis`) by `by` ft: a scale about the
        opposite side, as a Gumball drag of that face does to a box."""
        lo = min(p[axis] for p in ring) * ft
        hi = max(p[axis] for p in ring) * ft
        plane = rg.Plane(rg.Point3d(lo if axis == 0 else 0, lo if axis == 1 else 0, 0), rg.Vector3d.ZAxis)
        f = (hi - lo + by * ft) / (hi - lo)
        return rg.Transform.Scale(plane, f if axis == 0 else 1, f if axis == 1 else 1, 1)

    check(doc, 0, "The starting house", {
        "Front yard": {"proposed": "27'-0\""}, "Side yard, East": {"proposed": "12'-0\""},
        "Rear yard": {"proposed": "32'-9\""}, "Lot coverage": {"proposed": "22.6%", "status": "complies"},
        "Building height": {"proposed": "35'-0\"", "status": "needs_review"}})

    setfacts(doc, grade_is="finished")                         # 1. No regrading near the house, ticked
    check(doc, 1, "1 No regrading ticked", {"Building height": {"status": "complies", "margin": "at limit"},
                                            "Stories": {"status": "complies"}})
    t = rg.Transform.Translation(north * 5)
    xf(ids, t)
    check(doc, 2, "2 Move back 5 ft", {"Front yard": {"proposed": "32'-0\""},
                                       "Rear yard": {"proposed": "27'-9\"", "status": "complies"}})
    undo(ids, t)
    t = rg.Transform.Translation(north * 11)
    xf(ids, t)
    check(doc, 3, "3 Move back 11 ft", {"Rear yard": {"status": "needs_review", "proposed": "21'-9\"",
                                                      "required": "22'-6\"", "reason": "at best 23'-9\""}})
    undo(ids, t)
    t = rg.Transform.Translation(north * 14)
    xf(ids, t)
    check(doc, 3, "3 Move back 14 ft", {"Rear yard": {"status": "does_not_comply", "proposed": "18'-9\"",
                                                      "margin": "−3'-9\""}})
    undo(ids, t)
    t = stretch(ids, 1, None, 10)
    xf(ids, t)
    check(doc, 4, "4 Pull the rear wall 10 ft", {"Lot coverage": {"status": "does_not_comply", "proposed": "30.1%"}})
    undo(ids, t)
    base = g.STATE["start"]["floors"][-1]
    roof = rg.Transform.Scale(rg.Plane(rg.Point3d(0, 0, base["base"] * ft), rg.Vector3d.ZAxis), 1, 1,
                              (base["top"] - base["base"] + 4) / (base["top"] - base["base"]))
    xf(top_floor, roof)
    check(doc, 5, "5 Raise the roof 4 ft", {"Building height": {"status": "does_not_comply", "proposed": "39'-0\"",
                                                                "reason": "Front yard 27'-0\", needs ≥ 29'-0\""}})
    undo(top_floor, roof)
    t = stretch(ids, 0, None, 5)
    xf(ids, t)
    check(doc, 6, "6 Widen 5 ft to the east", {"Side yard, East": {"status": "does_not_comply", "proposed": "7'-0\"",
                                                                   "margin": "−3'-0\""},
                                               "Lot coverage": {"status": "needs_review", "proposed": "24.87%"}})
    undo(ids, t)
    check(doc, 7, "7 Undo: back to the start", {"Rear yard": {"proposed": "32'-9\"", "status": "complies"},
                                                "Lot coverage": {"proposed": "22.6%", "status": "complies"}})

    rear = max(p[1] for p in ring)                             # 8. a garage on the Default layer, behind the house
    garage = doc.Objects.AddBrep(rg.Box(rg.Plane(rg.Point3d(40 * ft, (rear + 6) * ft, 0), rg.Vector3d.ZAxis),
                                        rg.Interval(0, 12 * ft), rg.Interval(0, 20 * ft),
                                        rg.Interval(0, 10 * ft)).ToBrep())
    check(doc, 8, "8 A garage on the Default layer", {"Objects on the lot not included": {"status": "needs_review"},
                                                      "Lot coverage": {"status": "needs_review"}})
    doc.Objects.Delete(garage, True)
    floor2 = [o.Id for o in floors if o.Attributes.Name == "Floor 2"]
    t = rg.Transform.Translation(east * 3)
    xf(floor2, t)
    check(doc, 9, "9 One floor moved on its own", {"Stories": {"status": "needs_review", "reason": "floors misaligned"}})
    undo(floor2, t)

    lo_x, hi_x = min(p[0] for p in ring), max(p[0] for p in ring)   # 10. the height bonus, done right
    narrow = rg.Transform.Scale(rg.Plane(rg.Point3d((lo_x + hi_x) / 2 * ft, 0, 0), rg.Vector3d.ZAxis),
                                (hi_x - lo_x - 6) / (hi_x - lo_x), 1, 1)
    back = rg.Transform.Translation(north * 3)
    xf(top_floor, roof)
    xf(ids, narrow)
    xf(ids, back)
    check(doc, 10, "10 The height bonus done right", {"Building height": {"status": "complies", "required": "38'-6\""},
                                                      "Front yard": {"required": "28'-0\"", "margin": "+2'-0\""},
                                                      "Side yard, West": {"required": "13'-0\""}})
    undo(ids, back)
    undo(ids, narrow)
    undo(top_floor, roof)

    layer = g._layer(doc, g.FINISHED_LAYER)                    # 11. finished spot grades at the walls, then a move
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = layer
    spots = [doc.Objects.AddPoint(g._model_point(doc, p), a)
             for p in ([36.5, 26.5, 0.0], [36.5, 57.75, 0.0], [11.5, 42.1, 0.0], [61.5, 42.1, 0.0])]   # walls y 27..57.25
    setfacts(doc, grade_from="finished_spots", grade_is="finished", ground_is_flat=None, grade_elevation=None)
    check(doc, 11, "11 Spot grades at the walls", {"Building height": {"status": "complies"}})
    t = rg.Transform.Translation(north * 5)
    xf(ids, t)
    check(doc, 11, "11 then the house moves 5 ft",
          {"Building height": {"status": "needs_review", "reason": "spot grades no longer at the building's walls"}})
    undo(ids, t)
    for s in spots:
        doc.Objects.Delete(s, True)
    setfacts(doc, grade_from=None, ground_is_flat=True, grade_elevation=0.0)

    setfacts(doc, corner_lot=True)                              # 12. a corner lot
    check(doc, 12, "12 Corner lot Yes", {"Front yard": {"status": "needs_review"}})
    setfacts(doc, corner_lot=False)

    for o in g._buildings(doc):                                 # 13. a survey: a new starting house to the limits
        doc.Objects.Delete(o, True)
    setfacts(doc, lot_surveyed=True)
    path = os.path.join(tempfile.gettempdir(), "gordium_qs_survey.3dm")
    g.export(doc, path)
    start = g.ask({"cmd": "start", "model": path, "facts": g.check_facts(doc, g.current_facts(doc)),
                   "floor_to_floor": g.logic.FLOOR_TO_FLOOR, "design_buffer": 0.0})
    xs = [p[0] for p in start["floors"][0]["outline"]]
    log["survey_width"] = max(xs) - min(xs)
    g.add_floors(doc, start)
    check(doc, 13, "13 A survey: to the limits", {"Side yard, West": {"proposed": "10'-0\"", "margin": "at limit",
                                                                      "status": "complies"}})
    tests[-1]["match"] = tests[-1]["match"] and abs(log["survey_width"] - 53.0) < 1e-6

    # 14. other units: a millimeter template, the same start, the same rows as the feet run's starting house
    doc2 = docs.open("Small Objects - Millimeters")
    opened.append(doc2)
    g.STATE["on_confirm"] = lambda *a: None
    g.gordium_check()
    rows_mm = items()
    same = all(rows_mm.get(name, {}).get(f) == want for name, fields in tests[0]["got"].items()
               for f, want in fields.items())
    tests.append({"n": 14, "test": "14 Millimeter template: same results", "expected": tests[0]["got"],
                  "got": {name: {f: rows_mm.get(name, {}).get(f) for f in fields}
                          for name, fields in tests[0]["got"].items()}, "match": same})
    capture(doc2, "14_millimeters")
    log["all_match"] = all(t["match"] for t in tests)
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
