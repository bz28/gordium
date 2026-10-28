#! python3
"""QUICKSTART's "Test it yourself", in Rhino 8 (apps/rhino_plugin/QUICKSTART.md; the same numbers are checked in
code by packages/design_checker/tests/test_quickstart.py). Run in Rhino, not in CI.

From a fresh document (Rhino's feet template): GordiumStart's flow on the sample lot, then each test's edit made in
the model, checked as live mode checks it, compared with what the guide says, captured (Top view), and undone.
Test 14 starts again in a millimeter template and compares every row with the feet run. The sample is 106 Ithaca
Rd's real tax-map lot (the street along the bottom of Top view: "back" is +y, "left" is -x). Every test must match
(the run fails loudly otherwise). Writes <temp>/gordium_quickstart/out.json (each test: expected, got, match) and
frames/NN_*.png; closes its documents.
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
from test_docs_in_rhino import look_up_106  # noqa: E402

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
    look_up_106(g, g.gordium_check)                                         # GordiumStart's flow on an empty file (flat ground)
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

    def stretch(targets, axis, at, by, low=False):
        """Move one face out by `by` ft (the high side along `axis`, or the low side): a scale about the opposite
        side, as a Gumball drag of that face does to a box."""
        lo = min(p[axis] for p in ring) * ft
        hi = max(p[axis] for p in ring) * ft
        fixed = hi if low else lo
        plane = rg.Plane(rg.Point3d(fixed if axis == 0 else 0, fixed if axis == 1 else 0, 0), rg.Vector3d.ZAxis)
        f = (hi - lo + by * ft) / (hi - lo)
        return rg.Transform.Scale(plane, f if axis == 0 else 1, f if axis == 1 else 1, 1)

    check(doc, 0, "The starting house", {
        "Front yard": {"proposed": "27'-0 3/4\""}, "Side yard, Southwest": {"proposed": "12'-0 5/8\""},
        "Side yard, Northeast": {"proposed": "27'-4 1/4\""}, "Rear yard": {"status": "needs_review"},
        "Lot coverage": {"proposed": "19.1%", "status": "complies"}, "Lot area": {"status": "complies"},
        "Building height": {"proposed": "35'-0\"", "status": "complies", "margin": "at limit"},   # the bonus's question doesn't matter
        "Stories": {"status": "complies"}})
    tests.append({"n": 1, "test": "1 Labels (checked by mvp_checks_in_rhino.py)", "expected": {}, "got": {},
                  "match": True})
    t = rg.Transform.Translation(north * 5)
    xf(ids, t)
    check(doc, 2, "2 Move back 5 ft", {"Front yard": {"proposed": "32'-0 5/8\"", "status": "complies"},
                                       "Rear yard": {"status": "needs_review"}})
    undo(ids, t)
    t = rg.Transform.Translation(north * 6)
    xf(ids, t)
    check(doc, 3, "3 Move back 6 ft", {"Rear yard": {"status": "needs_review", "proposed": "21'-6 1/8\""}})
    undo(ids, t)
    t = rg.Transform.Translation(north * 7)       # short under some readings only (the depth's ±4'-0"): review
    xf(ids, t)
    check(doc, 3, "3 Move back 7 ft", {"Rear yard": {"status": "needs_review", "proposed": "20'-6 1/8\"",
                                                     "delta": "up to 7'-11 1/4\" short"}})
    undo(ids, t)
    t = rg.Transform.Translation(north * 10)
    xf(ids, t)
    check(doc, 3, "3 Move back 10 ft", {"Rear yard": {"status": "does_not_comply", "proposed": "17'-6 1/8\"",
                                                      "delta": "at least 0'-7 1/4\" short"}})
    undo(ids, t)
    t = stretch(ids, 1, None, 17)
    xf(ids, t)
    check(doc, 4, "4 Pull the rear wall 17 ft", {"Lot coverage": {"status": "does_not_comply", "proposed": "27.8%"}})
    undo(ids, t)
    base = g.STATE["start"]["floors"][-1]
    roof = rg.Transform.Scale(rg.Plane(rg.Point3d(0, 0, base["base"] * ft), rg.Vector3d.ZAxis), 1, 1,
                              (base["top"] - base["base"] + 4) / (base["top"] - base["base"]))
    xf(top_floor, roof)
    check(doc, 5, "5 Raise the roof 4 ft", {"Building height": {"status": "does_not_comply", "proposed": "39'-0\"",
                                                                "delta": "−4'-0\" short"}})
    undo(top_floor, roof)
    t = stretch(ids, 0, None, 3, low=True)
    xf(ids, t)
    check(doc, 6, "6 The left side wall 3 ft out", {"Side yard, Southwest": {"status": "needs_review", "proposed": "9'-0 5/8\"",
                                                                         "delta": "up to 2'-11 3/8\" short"}})
    undo(ids, t)
    t = stretch(ids, 0, None, 5, low=True)
    xf(ids, t)
    check(doc, 6, "6 The left side wall 5 ft out", {"Side yard, Southwest": {"status": "does_not_comply",
                                                                         "proposed": "7'-0 5/8\"",
                                                                         "delta": "at least 0'-11 1/4\" short"}})
    undo(ids, t)
    check(doc, 7, "7 Undo: back to the start", {"Front yard": {"proposed": "27'-0 3/4\""},
                                                "Lot coverage": {"proposed": "19.1%", "status": "complies"}})

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

    lo_x, hi_x = min(p[0] for p in ring), max(p[0] for p in ring)   # 10. the height bonus: waits for the question
    narrow = rg.Transform.Scale(rg.Plane(rg.Point3d((lo_x + hi_x) / 2 * ft, 0, 0), rg.Vector3d.ZAxis),
                                (hi_x - lo_x - 6) / (hi_x - lo_x), 1, 1)
    back = rg.Transform.Translation(north * 3)
    roof3 = rg.Transform.Scale(rg.Plane(rg.Point3d(0, 0, base["base"] * ft), rg.Vector3d.ZAxis), 1, 1,
                               (base["top"] - base["base"] + 3) / (base["top"] - base["base"]))   # the guide's 3 ft
    xf(top_floor, roof3)
    xf(ids, narrow)
    xf(ids, back)
    check(doc, 10, "10 The height bonus waits", {"Building height": {"status": "needs_review",
                                                                     "reason": "side and rear lot lines"}})
    undo(ids, back)
    undo(ids, narrow)
    undo(top_floor, roof3)
    t = rg.Transform.Translation(north * 5)                     # 11. Delta in words (test 2's front yard)
    xf(ids, t)
    check(doc, 11, "11 Delta in words", {"Front yard": {"delta": "at least 5'-0 5/8\" to spare"}})
    undo(ids, t)

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
    check(doc, 13, "13 A survey: to the limits", {"Side yard, Southwest": {"proposed": "10'-0\"", "status": "complies"}})
    tests[-1]["match"] = tests[-1]["match"] and round(log["survey_width"] * 12) == 39 * 12 + 10   # 39'-10" wide

    # 14. other units: a millimeter template, the same start, the same rows as the feet run's starting house
    doc2 = docs.open("Small Objects - Millimeters")
    opened.append(doc2)
    g.STATE["on_confirm"] = lambda *a: None
    look_up_106(g, g.gordium_check)
    rows_mm = items()
    same = all(rows_mm.get(name, {}).get(f) == want for name, fields in tests[0]["got"].items()
               for f, want in fields.items())
    tests.append({"n": 14, "test": "14 Millimeter template: same results", "expected": tests[0]["got"],
                  "got": {name: {f: rows_mm.get(name, {}).get(f) for f in fields}
                          for name, fields in tests[0]["got"].items()}, "match": same})
    capture(doc2, "14_millimeters")
    log["all_match"] = all(t["match"] for t in tests)
    assert log["all_match"], [t["test"] for t in tests if not t["match"]]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
