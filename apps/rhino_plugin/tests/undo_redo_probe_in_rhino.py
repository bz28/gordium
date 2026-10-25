#! python3
"""Which kind of change breaks Redo of an undo record begun outside a command (RHINO_QUEUE: the Redo after a
re-lookup's Draw did nothing at demo e631aae). Run in Rhino 8, not in CI; Gordium's own code is not loaded.

Each case, in a fresh copy of Rhino's feet template and outside any command (as the panel's Edit site… runs):
BeginUndoRecord, one curve added plus the case's extra change, EndUndoRecord, Rhino's _Undo, then _Redo. A case
passes when Undo removes the curve and Redo brings it back. The extras are what a re-lookup's Draw does inside its
one record (gordium_rhino._draw_prepare to edit_facts): document strings written (the facts, the box's choices,
the sources), an object's attribute user strings set, a layer added then deleted (the hidden holding layer), an
object moved onto a hidden layer then deleted (held, then gone at commit), a layer's visibility set directly, and a
Rhino command run inside the record (frame_site's _-Zoom). Rhino's undo events are recorded for each.
Writes <temp>/gordium_undo_probe/out.json ("done": true at the end)."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (its guard: no callback may raise into Rhino)

S = os.path.join(tempfile.gettempdir(), "gordium_undo_probe") + "/"
os.makedirs(S, exist_ok=True)
log = {"cases": {}, "events": []}
rg = Rhino.Geometry


def event(sender, e):
    log["events"].append(dict({k: bool(getattr(e, k, False)) for k in (
        "IsBeginRecording", "IsEndRecording", "IsBeginUndo", "IsEndUndo", "IsBeginRedo", "IsEndRedo",
        "IsPurgeRecord")}, serial=int(getattr(e, "UndoSerialNumber", 0) or 0), case=log.get("case")))


def curve(doc, x=0.0, layer=None):
    attrs = Rhino.DocObjects.ObjectAttributes()
    if layer is not None:
        attrs.LayerIndex = layer
    return doc.Objects.AddCurve(rg.LineCurve(rg.Point3d(x, 0, 0), rg.Point3d(x + 10, 0, 0)), attrs)


def strings(doc):
    doc.Strings.SetString("gordium_probe", "facts", "{\"lot\": 1}")


def user_strings(doc):
    o = doc.Objects.FindId(curve(doc, 20))
    attrs = o.Attributes.Duplicate()
    attrs.SetUserString("gordium_added_by", "probe")
    doc.Objects.ModifyAttributes(o, attrs, True)


def layer_added_then_deleted(doc):
    layer = Rhino.DocObjects.Layer()
    layer.Name = "Gordium probe holding"
    index = doc.Layers.Add(layer)
    doc.Layers.Delete(index, True)


def held_then_deleted(doc, keep):
    """`keep` made before the record began, as the sample's lot and house are before a Draw's record."""
    layer = Rhino.DocObjects.Layer()
    layer.Name = "Gordium probe held"
    index = doc.Layers.Add(layer)
    doc.Layers[index].IsVisible = False
    attrs = keep.Attributes.Duplicate()
    attrs.LayerIndex = index
    doc.Objects.ModifyAttributes(keep, attrs, True)
    doc.Objects.Delete(keep, True)
    doc.Layers.Delete(index, True)


def visibility(doc):
    doc.Layers[doc.Layers.CurrentLayerIndex].IsVisible = True


def command_inside(doc):
    Rhino.RhinoApp.RunScript("_-Zoom _All _Extents", False)


CASES = [("baseline", None), ("document strings", strings), ("attribute user strings", user_strings),
         ("layer added then deleted", layer_added_then_deleted), ("held then deleted", held_then_deleted),
         ("layer visibility set", visibility), ("a command inside the record", command_inside),
         ("all of them", None)]


def all_of_them(doc, keep):
    for f in (strings, user_strings, layer_added_then_deleted, visibility, command_inside):
        f(doc)
    held_then_deleted(doc, keep)


def one(docs, name, extra):
    log["case"] = name
    doc = docs.open("Large Objects - Feet")
    try:
        before = doc.Objects.FindId(curve(doc, 40))   # an object that exists before the record (the sample's lot)
        in_command = bool(Rhino.Commands.Command.InCommand())
        serial = doc.BeginUndoRecord("Gordium probe: " + name)
        added = curve(doc)
        if name == "all of them":
            all_of_them(doc, before)
        elif extra is held_then_deleted:
            extra(doc, before)
        elif extra is not None:
            extra(doc)
        ended = doc.EndUndoRecord(serial)
        undo = bool(Rhino.RhinoApp.RunScript("_Undo", False))
        gone = doc.Objects.FindId(added) is None
        redo = bool(Rhino.RhinoApp.RunScript("_Redo", False))
        back = doc.Objects.FindId(added) is not None
        log["cases"][name] = {"ok": gone and back, "serial": int(serial), "ended": bool(ended),
                              "in_command": in_command, "undo_ran": undo,
                              "undone": gone, "redo_ran": redo, "redone": back}
    except Exception:
        log["cases"][name] = {"ok": False, "trace": traceback.format_exc()}
    finally:
        close(doc)


def main():
    handler = System.EventHandler[Rhino.Commands.UndoRedoEventArgs](logic.guard(event, "record an undo event"))
    Rhino.Commands.Command.UndoRedo += handler
    docs = TestDocs("undo_probe").__enter__()
    try:
        for name, extra in CASES:
            one(docs, name, extra)
        log["ok"] = all(c.get("ok") for c in log["cases"].values())
    finally:
        Rhino.Commands.Command.UndoRedo -= handler
        log["done"] = True
        json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
        Rhino.RhinoApp.WriteLine("undo_redo_probe: " + ", ".join(
            "%s %s" % (n, "ok" if c.get("ok") else "REDO FAILS") for n, c in log["cases"].items()))


def run_outside_a_command():
    """As the panel runs: now if no command is running, else at the next idle once this one has ended. Nothing
    may raise into Rhino from the idle (on the Mac that aborts it)."""
    if not Rhino.Commands.Command.InCommand():
        main()
        return

    def once(sender, e):
        Rhino.RhinoApp.Idle -= idle
        try:
            main()
        except Exception:
            Rhino.RhinoApp.WriteLine("undo_redo_probe FAILED: see " + S + "out.json")
    idle = System.EventHandler(logic.guard(once, "run outside a command"))
    Rhino.RhinoApp.Idle += idle
    Rhino.RhinoApp.WriteLine("undo_redo_probe: runs when this command ends; wait for " + S +
                             "out.json to say \"done\": true")


run_outside_a_command()
