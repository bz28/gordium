#! python3
"""Without Gordium: does a sublayer locked by IsLocked = True keep its lock through its parent being locked, then
unlocked? And when locked by SetPersistentLocking(True) too? (#23 e997f0e claim 4: the test locks Gordium::Grade by
IsLocked.) Writes grade_lock_probe.json ("done": true); closes its document."""
import json
import sys
import traceback

import Rhino

T = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
sys.path.insert(0, T + "extract_e997f0e/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

out, opened = {}, []
docs = TestDocs("grade_lock_probe").__enter__()
try:
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)

    def layer(name, parent=None):
        l = Rhino.DocObjects.Layer()
        l.Name = name
        if parent is not None:
            l.ParentLayerId = doc.Layers[parent].Id
        return doc.Layers.Add(l)

    for how in ("IsLocked", "SetPersistentLocking"):
        top = layer("Top_" + how)
        sub = layer("Grade", top)
        if how == "IsLocked":
            doc.Layers[sub].IsLocked = True
        else:
            doc.Layers[sub].SetPersistentLocking(True)
            doc.Layers[sub].IsLocked = True
        row = {"own_after_lock": doc.Layers[sub].GetPersistentLocking(), "locked_after_lock": doc.Layers[sub].IsLocked}
        doc.Layers[top].IsLocked = True
        row["own_under_locked_parent"] = doc.Layers[sub].GetPersistentLocking()
        doc.Layers[top].IsLocked = False
        row["locked_after_parent_unlocked"] = doc.Layers[sub].IsLocked
        out[how] = row
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    out["done"] = True
    json.dump(out, open(T + "grade_lock_probe.json", "w", encoding="utf-8"), indent=1)
