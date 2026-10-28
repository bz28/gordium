#! python3
"""Every panel change is exactly one undo step, in Rhino 8 (run in Rhino, not in CI; CI's guard is
packages/design_checker/tests/test_undo_steps.py on a fake document). Ben, 2026-10-26: a change written outside any
undo record is skipped by Ctrl+Z, which undoes the architect's own earlier edit instead.

GordiumStart's flow on the sample (106 Ithaca Rd) in a fresh copy of the feet template, plus a second solid on the
Building layer (so there is a main building to pick) and a box on Default (something to add to the check). Then, for
each panel action that changes the file, outside any command (as the panel's buttons run):
  a. the architect's own edit first: one curve drawn with Rhino's _Line command (its own undo record, as in Rhino);
  b. the action, through the panel's own gate (g._actions()), its pick and the row's dialog answered by stand-ins;
  c. claim "<action>: one step": exactly one undo record ended during the action, and the file changed (its name,
     logic.UNDO_WORDS[action], is what Edit > Undo shows: read by eye, RhinoCommon can't read a record's name back);
  d. one Rhino _Undo;
  e. claim "<action>: undone": the file is exactly as before b (the facts, the box's choices and the sources strings;
     every object's layer; the starting house layer's visibility);
  f. claim "<action>: nothing else": the architect's curve from a is still there, and "only its own record undone": the
     _Undo took back exactly the record ended in b (by serial, from Rhino's undo events);
  g. claim "<action>: checked again": the Undo marked the model changed (live mode re-checks it at the next idle).
Actions: survey, enter (Bedrooms: 2), main, add, ground, not_ground (after a ground mark of its own), massing, labels,
context (Show neighbourhood off: its layers hidden and the setting saved, one step), auto_check (Check after every
edit on: the setting saved, one step).
Then, observed only (out.json "two_in_a_row", not a claim): two panel changes in a row with no command between and
one _Undo, which records it takes back. Last, the control: an edit and an action deliberately in one record; its
claim passes only if one _Undo takes the edit back too (so the claims above can tell a merged step from a good one).
Writes <temp>/gordium_undo_steps/out.json ("done": true at the end); the command line says which claims fail.
Run through rhinocode on 2026-10-28, its _Undo took nothing back (every "undone" list empty, so the "undone", "only
its own record" and "checked again" claims failed, while every "one step" and "nothing else" claim passed); why is
not known yet (the script was not inside a command), so those claims are judged by a person's Cmd+Z for now."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs  # noqa: E402
from test_docs_in_rhino import look_up_106  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_undo_steps") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}, "events": [], "undone": []}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
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


def event(sender, e):
    serial = int(getattr(e, "UndoSerialNumber", 0) or 0)
    if getattr(e, "IsEndRecording", False):
        log["events"].append(serial)
    if getattr(e, "IsBeginUndo", False):
        log["undone"].append(serial)           # which records one _Undo really takes back


def architects_edit(doc):
    """The architect's own earlier edit, as they make it: a Rhino command (_Line), its own undo record. (Records
    written one after another by one script, outside any command, are all taken back by one _Undo: Lane C's
    control at 59d7184, undo_probe_control. The panel's own records are what is under test, so the edit before it
    must be a command, as in Rhino.)"""
    known = {o.Id for o in doc.Objects}
    Rhino.RhinoApp.RunScript("_Line 0,-300,0 10,-300,0", False)
    made = [o.Id for o in doc.Objects if o.Id not in known]
    return made[0] if len(made) == 1 else None


def snapshot(g, doc):
    """What a panel change can write: the three Gordium strings, every object's layer, each layer's visibility."""
    strings = {k: doc.Strings.GetValue(g.SECTION, k) for k in (g.ENTRY, g.UI_ENTRY, g.SOURCES_ENTRY)}
    objects = {str(o.Id): o.Attributes.LayerIndex for o in doc.Objects}
    layers = {layer.FullPath: bool(layer.IsVisible) for layer in doc.Layers if not layer.IsDeleted}
    return {"strings": strings, "objects": objects, "layers": layers}


def box(doc, x, layer):
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = layer
    b = rg.Box(rg.Plane.WorldXY, rg.Interval(x, x + 8), rg.Interval(-200, -192), rg.Interval(0, 8)).ToBrep()
    return str(doc.Objects.AddBrep(b, attrs))


def one(g, doc, name, args):
    mine = architects_edit(doc)
    claim(name + ": the architect's edit made", mine is not None)
    before = snapshot(g, doc)
    log["events"], log["undone"] = [], []
    g._actions()[name](*args)
    ended = list(log["events"])
    claim(name + ": one step", len(ended) == 1 and before != snapshot(g, doc),
          {"records_ended": ended, "named (by eye in Edit > Undo)": g.logic.UNDO_WORDS[name]})
    undone_at = time.time()
    Rhino.RhinoApp.RunScript("_Undo", False)
    after = snapshot(g, doc)
    claim(name + ": only its own record undone", log["undone"] == ended[-1:], {"undone": log["undone"],
                                                                             "its record": ended})
    claim(name + ": checked again", (g.STATE.get("dirty") or 0) >= undone_at, g.STATE.get("dirty"))
    claim(name + ": undone", after == before,
          {k: (before[k], after[k]) for k in before if before[k] != after[k]})
    claim(name + ": nothing else", mine is not None and doc.Objects.FindId(mine) is not None)


def control(g, doc):
    """The control: the architect's edit and the action deliberately in ONE record (an outer record held across
    both: the action's own step is then Rhino's 0). One _Undo then takes the edit back too, so "nothing else" must
    fail here; if it didn't, the claims above couldn't tell a merged step from a good one."""
    outer = doc.BeginUndoRecord("control: the edit and the action merged")
    mine = doc.Objects.AddCurve(rg.LineCurve(rg.Point3d(0, -310, 0), rg.Point3d(10, -310, 0)))
    g._actions()["labels"](False)
    doc.EndUndoRecord(outer)
    log["undone"] = []
    Rhino.RhinoApp.RunScript("_Undo", False)
    claim("control: a merged record is caught (the edit went with the action)",
          doc.Objects.FindId(mine) is None, {"undone": log["undone"], "merged record": outer})


def main():
    g = fresh_module()
    handler = System.EventHandler[Rhino.Commands.UndoRedoEventArgs](g.logic.guard(event, "record an undo event"))
    Rhino.Commands.Command.UndoRedo += handler
    try:
        claim("outside any command", not Rhino.Commands.Command.InCommand())
        g._pick = lambda doc, prompt, objs, kind, *a: str(objs[-1].Id)
        g.ui.row_dialog = lambda title, fields, check: {f["key"]: "2" for f in fields}   # the row's dialog: 2, OK
        doc = TestDocs("undo_steps").__enter__().open("Large Objects - Feet")
        look_up_106(g, g.gordium_check)                                       # the sample, as GordiumStart draws it
        building = doc.Layers.FindByFullPath("Building", -1)
        box(doc, 300, building)                                 # a second building: one to pick as the main one
        loose = box(doc, 320, doc.Layers.CurrentLayerIndex)     # not measured: one to add to the check
        g.run_check(doc, report=False)
        for name, args in (("survey", ()), ("enter", (["sleeping_rooms"],)), ("main", ()), ("add", ([loose],)),
                           ("ground", ([loose],)), ("massing", (True,)), ("labels", (True,)), ("context", (False,)),
                           ("auto_check", (True,))):
            one(g, doc, name, args)
        g._actions()["ground"]([loose])                         # a ground mark of its own, so "Not the ground" has one
        one(g, doc, "not_ground", ())
        # observed, not claimed (a script can't tell its own grouping from Rhino's; a person checks it by hand): two
        # panel changes in a row with no command between, then one _Undo: which records it takes back
        architects_edit(doc)
        log["events"], log["undone"] = [], []
        g._actions()["labels"](True)
        g._actions()["massing"](False)
        ended = list(log["events"])
        log["undone"] = []
        Rhino.RhinoApp.RunScript("_Undo", False)
        log["two_in_a_row"] = {"records": ended, "undone_by_one_undo": list(log["undone"])}
        architects_edit(doc)                                    # (a command between: the control's merge is its own)
        control(g, doc)                                         # last: its _Undo may take more than its own record
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    except Exception:
        log["ok"] = False
        log["trace"] = traceback.format_exc()
    finally:
        Rhino.Commands.Command.UndoRedo -= handler
        log["done"] = True
        json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
        failing = [n for n, c in log["claims"].items() if not c["ok"]]
        Rhino.RhinoApp.WriteLine("undo_steps: %d claims, %s" % (len(log["claims"]), "FAILING: " + ", ".join(failing)
                                 if failing or not log["ok"] else "all pass"))


if os.path.exists(S + "out.json"):          # never an earlier run's result read as this one's
    os.remove(S + "out.json")
main()
