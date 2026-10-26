#! python3
"""Rhino 8's own layer locks, without Gordium (run in Rhino, not in CI): what the fake layer table in
packages/design_checker/tests/test_context_box.py assumes, and what the neighbourhood's locks need. Each case on its
own fresh layers "LockProbe_<case>" (the top) and "...::Sub", or, for the nested cases, "...::Mid::Sub" with Mid
left unlocked (as Gordium::Context sits between "Gordium" and Parcels), in a fresh feet document. Each row records
Sub's (and Mid's) IsLocked and own lock (GetPersistentLocking) after every step.
1. is_locked: Sub locked by IsLocked; the top locked, then unlocked (grade_lock_probe.json's first row at e997f0e,
   again).
2. persistent_then_is_locked: Sub given SetPersistentLocking(True), then IsLocked; the top locked, then unlocked
   (that probe's second row, again).
3. persistent_alone: Sub given SetPersistentLocking(True) only, the top unlocked: does it record an own lock at all?
   Read the "sub set" row's "own". (Its rows after the top's lock and unlock answer it only if case 4 shows a
   recorded own lock survives the top being locked again.)
4. relock: the top locked, Sub given its own lock (locked if it isn't, then SetPersistentLocking(True), as Gordium's
   _set_own_lock does), the top unlocked (Sub locked?), then
   locked and unlocked again: does locking a parent clear a recorded own lock? (The fake's two readings, "keeps" and
   "resets".)
5. nested_is_locked, nested_relock: cases 1 and 4 with Mid between the top and Sub.
6. layer_command, nested_layer_command (last: they type a command): Sub locked by IsLocked; the top locked and
   unlocked by Rhino's own -_Layer command, as the architect does it from the command line: does the command record
   Sub's own lock, where RhinoCommon's IsLocked on the top doesn't (case 1)? If it does, a neighbourhood drawn while
   "Gordium" is unlocked keeps Parcels, Streets and Notes locked when the architect locks and unlocks "Gordium" by
   the command; if not, they come out unlocked (plain Rhino, as Grade in case 1). The Layers panel's lock icon is
   not probed here (it may take another route): check it by hand.
   BEFORE RUNNING: type `-_Layer`, `_Lock`, a layer's name and Enter by hand once, and check the command has ended
   (if it asks for more, change the macro in command() to match, or the script waits at the command line). out.json
   is written after every case, with "case" naming the one under way, so a stuck command loses nothing before it.
Writes <temp>/gordium_lock_probe/out.json ("done": true at the end); closes its document."""
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
CASES = ("is_locked", "persistent_then_is_locked", "persistent_alone", "relock", "nested_is_locked", "nested_relock",
         "layer_command", "nested_layer_command")
out, doc = {"done": False}, None


def save():
    json.dump(out, open(S + "out.json", "w", encoding="utf-8"), indent=1)


def layer(name, parent=None):
    new = Rhino.DocObjects.Layer()
    new.Name = name
    if parent is not None:
        new.ParentLayerId = doc.Layers[parent].Id
    return doc.Layers.Add(new)


def state(sub, mid):
    row = {"sub_locked": bool(doc.Layers[sub].IsLocked), "sub_own": bool(doc.Layers[sub].GetPersistentLocking())}
    if mid is not None:
        row.update(mid_locked=bool(doc.Layers[mid].IsLocked), mid_own=bool(doc.Layers[mid].GetPersistentLocking()))
    return row


def command(text):
    """Rhino's own command, scripted as typed (whether it ran)."""
    return bool(Rhino.RhinoApp.RunScript(text, False))


def lock_top(top, name, locked, by_command):
    if by_command:
        return command('-_Layer %s "%s" _Enter' % ("_Lock" if locked else "_Unlock", name))
    doc.Layers[top].IsLocked = locked
    return True


def probe(case):
    name = "LockProbe_" + case
    top = layer(name)
    mid = layer("Mid", top) if case.startswith("nested") else None
    sub = layer("Sub", mid if mid is not None else top)
    by_command = case.endswith("layer_command")
    rows = []
    if case == "persistent_then_is_locked":
        doc.Layers[sub].SetPersistentLocking(True)
        doc.Layers[sub].IsLocked = True
    elif case in ("is_locked", "nested_is_locked") or by_command:
        doc.Layers[sub].IsLocked = True
    elif case == "persistent_alone":
        doc.Layers[sub].SetPersistentLocking(True)
    rows.append(["sub set", state(sub, mid)])
    if case.endswith("relock"):
        doc.Layers[top].IsLocked = True
        if not doc.Layers[sub].IsLocked:        # as Gordium's _set_own_lock gives a layer its own lock
            doc.Layers[sub].IsLocked = True
        doc.Layers[sub].SetPersistentLocking(True)
        rows.append(["top locked, sub's own lock set", state(sub, mid)])
        doc.Layers[top].IsLocked = False
        rows.append(["top unlocked", state(sub, mid)])
    ran = lock_top(top, name, True, by_command)
    rows.append(["top locked", state(sub, mid), {"ran": ran, "top_locked": bool(doc.Layers[top].IsLocked)}])
    ran = lock_top(top, name, False, by_command)
    rows.append(["top unlocked", state(sub, mid), {"ran": ran, "top_locked": bool(doc.Layers[top].IsLocked)}])
    return rows


try:
    docs = TestDocs("lock_probe").__enter__()
    doc = docs.open("Large Objects - Feet")
    for case in CASES:
        out["case"] = case
        save()                                  # before the case: a stuck command still leaves the cases before it
        try:
            out[case] = probe(case)
        except Exception:
            out[case] = {"trace": traceback.format_exc()}
        save()
    out.pop("case", None)
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    try:
        if doc is not None:
            close(doc)
    except Exception:
        pass
    out["done"] = True
    try:
        save()
    except Exception:
        pass
