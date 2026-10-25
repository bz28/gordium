#! python3
"""Rhino 8's own layer locks, without Gordium (run in Rhino, not in CI): what the fake layer table in
packages/design_checker/tests/test_context_box.py assumes, and what the neighbourhood's locks need. Each case on its
own fresh layers "LockProbe_<case>" and "LockProbe_<case>::Sub" in a fresh feet document; each row records the sublayer's
IsLocked and its own lock (GetPersistentLocking) after every step.
1. is_locked: Sub locked by IsLocked; the parent locked, then unlocked (grade_lock_probe.json's first row at e997f0e,
   again).
2. persistent_then_is_locked: Sub given SetPersistentLocking(True), then IsLocked; the parent locked, then unlocked
   (that probe's second row, again).
3. persistent_alone: Sub given SetPersistentLocking(True) only, its parent unlocked: does it record an own lock at
   all? (The fake assumes not; the earlier probe set IsLocked straight after it, so it could not tell.)
4. relock: the parent locked, Sub given its own lock (SetPersistentLocking(True)), the parent unlocked (Sub locked?),
   then locked and unlocked again: does locking a parent clear a recorded own lock? (The fake's two readings,
   "keeps" and "resets".)
5. layer_command: Sub locked by IsLocked; the parent locked and unlocked by Rhino's own -_Layer command, as the
   architect does it from the Layers panel or the command line: does Rhino's command record Sub's own lock, where
   RhinoCommon's IsLocked on the parent doesn't (case 1)? If it does, a neighbourhood drawn while "Gordium" is
   unlocked keeps Parcels, Streets and Notes locked when the architect locks and unlocks "Gordium"; if not, they
   come out unlocked (plain Rhino, as Grade in case 1).
Writes <temp>/gordium_lock_probe/out.json ("done": true); closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Rhino

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_lock_probe") + "/"
os.makedirs(S, exist_ok=True)
out, doc = {}, None


def layer(name, parent=None):
    new = Rhino.DocObjects.Layer()
    new.Name = name
    if parent is not None:
        new.ParentLayerId = doc.Layers[parent].Id
    return doc.Layers.Add(new)


def state(sub):
    return {"locked": bool(doc.Layers[sub].IsLocked), "own": bool(doc.Layers[sub].GetPersistentLocking())}


def command(text):
    """Rhino's own command, scripted as typed (whether it ran)."""
    return bool(Rhino.RhinoApp.RunScript(text, False))


docs = TestDocs("lock_probe").__enter__()
try:
    doc = docs.open("Large Objects - Feet")
    for case in ("is_locked", "persistent_then_is_locked", "persistent_alone", "relock", "layer_command"):
        name = "LockProbe_" + case
        top = layer(name)
        sub = layer("Sub", top)
        rows = []
        if case in ("is_locked", "layer_command"):
            doc.Layers[sub].IsLocked = True
        elif case == "persistent_then_is_locked":
            doc.Layers[sub].SetPersistentLocking(True)
            doc.Layers[sub].IsLocked = True
        elif case == "persistent_alone":
            doc.Layers[sub].SetPersistentLocking(True)
        rows.append(["sub set", state(sub)])
        if case == "relock":
            doc.Layers[top].IsLocked = True
            doc.Layers[sub].SetPersistentLocking(True)
            rows.append(["parent locked, sub's own lock set", state(sub)])
            doc.Layers[top].IsLocked = False
            rows.append(["parent unlocked", state(sub)])
        if case == "layer_command":
            rows.append(["-_Layer lock ran", command('-_Layer _Lock "%s" _Enter' % name)])
            rows.append(["parent locked by the command", state(sub), bool(doc.Layers[top].IsLocked)])
            rows.append(["-_Layer unlock ran", command('-_Layer _Unlock "%s" _Enter' % name)])
            rows.append(["parent unlocked by the command", state(sub), bool(doc.Layers[top].IsLocked)])
        else:
            doc.Layers[top].IsLocked = True
            rows.append(["parent locked", state(sub)])
            doc.Layers[top].IsLocked = False
            rows.append(["parent unlocked", state(sub)])
        out[case] = rows
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    try:
        if doc is not None:
            close(doc)
    except Exception:
        pass
    out["done"] = True
    json.dump(out, open(S + "out.json", "w", encoding="utf-8"), indent=1)
