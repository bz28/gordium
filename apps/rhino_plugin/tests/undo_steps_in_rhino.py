#! python3
"""Every panel change is exactly one undo step, in Rhino 8 (run in Rhino, not in CI; CI's guard is
packages/design_checker/tests/test_undo_steps.py on a fake document). Ben, 2026-10-26: a change written outside any
undo record is skipped by Ctrl+Z, which undoes the architect's own earlier edit instead.

GordiumStart's flow on the sample (106 Ithaca Rd) in a fresh copy of the feet template, plus a second solid on the
Building layer (so there is a main building to pick) and a box on Default (something to add to the check). Then, for
each panel action that changes the file, outside any command (as the panel's buttons run):
  a. the architect's own edit first: one curve, in its own undo record;
  b. the action, through the panel's own gate (g._actions()), its prompts answered by stand-ins;
  c. claim "<action>: one step": exactly one undo record ended during the action, and the file changed (its name,
     logic.UNDO_WORDS[action], is what Edit > Undo shows: read by eye, RhinoCommon can't read a record's name back);
  d. one Rhino _Undo;
  e. claim "<action>: undone": the file is exactly as before b (the facts, the box's choices and the sources strings;
     every object's layer; the starting house layer's visibility);
  f. claim "<action>: nothing else": the architect's curve from a is still there;
  g. claim "<action>: checked again": the Undo marked the model changed (live mode re-checks it at the next idle).
Actions: survey, enter (Bedrooms: 2), main, add, ground, not_ground (after a ground mark of its own), massing, labels.
Writes <temp>/gordium_undo_steps/out.json ("done": true at the end); the command line says which claims fail."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_undo_steps") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}, "events": []}


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
    if getattr(e, "IsEndRecording", False):
        log["events"].append(int(getattr(e, "UndoSerialNumber", 0) or 0))


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
    serial = doc.BeginUndoRecord("the architect's own edit")
    mine = doc.Objects.AddCurve(rg.LineCurve(rg.Point3d(0, -300, 0), rg.Point3d(10, -300, 0)))
    doc.EndUndoRecord(serial)
    before = snapshot(g, doc)
    log["events"] = []
    g._actions()[name](*args)
    ended = list(log["events"])
    claim(name + ": one step", len(ended) == 1 and before != snapshot(g, doc),
          {"records_ended": ended, "named (by eye in Edit > Undo)": g.logic.UNDO_WORDS[name]})
    undone_at = time.time()
    Rhino.RhinoApp.RunScript("_Undo", False)
    after = snapshot(g, doc)
    claim(name + ": checked again", (g.STATE.get("dirty") or 0) >= undone_at, g.STATE.get("dirty"))
    claim(name + ": undone", after == before,
          {k: (before[k], after[k]) for k in before if before[k] != after[k]})
    claim(name + ": nothing else", doc.Objects.FindId(mine) is not None)


def main():
    g = fresh_module()
    handler = System.EventHandler[Rhino.Commands.UndoRedoEventArgs](g.logic.guard(event, "record an undo event"))
    Rhino.Commands.Command.UndoRedo += handler
    try:
        claim("outside any command", not Rhino.Commands.Command.InCommand())
        g._pick = lambda doc, prompt, objs, kind, *a: str(objs[-1].Id)
        g._count = lambda prompt: 2
        g._ask_yes_no_or_skip = lambda prompt: True
        doc = TestDocs("undo_steps").__enter__().open("Large Objects - Feet")
        g.gordium_check()                                       # the sample, as GordiumStart draws it
        building = doc.Layers.FindByFullPath("Building", -1)
        box(doc, 300, building)                                 # a second building: one to pick as the main one
        loose = box(doc, 320, doc.Layers.CurrentLayerIndex)     # not measured: one to add to the check
        g.run_check(doc, report=False)
        for name, args in (("survey", ()), ("enter", (["sleeping_rooms"],)), ("main", ()), ("add", ([loose],)),
                           ("ground", ([loose],)), ("massing", (True,)), ("labels", (True,))):
            one(g, doc, name, args)
        g._actions()["ground"]([loose])                         # a ground mark of its own, so "Not the ground" has one
        one(g, doc, "not_ground", ())
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
