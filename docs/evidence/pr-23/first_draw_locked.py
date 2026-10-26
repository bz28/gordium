#! python3
"""#23 at e997f0e, the optional extra: the neighbourhood's FIRST draw in a file whose "Gordium" layer is already
locked gives the same locks as a redraw: each layer's own lock (GetPersistentLocking) Parcels, Streets, Notes on,
Buildings and Context off; after unlocking Gordium, Parcels, Streets, Notes locked and Buildings not. A fresh feet
document with a locked "Gordium" layer made first; GordiumStart with 106 Ithaca Rd looked up (recorded answers).
Writes first_draw_locked.json ("done": true); closes its document."""
import json
import sys
import traceback

import Rhino
import scriptcontext as sc

T = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = T + "extract_e997f0e"
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

out, opened, g = {}, [], None


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None and hasattr(loaded, "off"):
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        try:
            w.terminate()
        except Exception:
            pass
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


docs = TestDocs("first_draw_locked").__enter__()
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)
    top = g._layer(doc, "Gordium")
    doc.Layers[top].IsLocked = True                     # the architect locked "Gordium" before the first draw
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": "106 Ithaca Rd, Ithaca, NY 14850"},
                   lookup_fixture="106_ithaca_rd")
    g.gordium_check()                                   # an empty file: GordiumStart, the lookup, the neighbourhood
    idx = g._context_layer_indexes(doc)
    out["layers"] = [doc.Layers[i].FullPath for i in idx]
    out["objects"] = sum(len(list(doc.Objects.FindByLayer(doc.Layers[i]) or [])) for i in idx)
    out["gordium_locked"] = doc.Layers[top].IsLocked
    out["own_locks"] = {doc.Layers[i].FullPath: doc.Layers[i].GetPersistentLocking() for i in idx}
    doc.Layers[top].IsLocked = False
    out["locks_after_parent_unlocked"] = {doc.Layers[i].FullPath: doc.Layers[i].IsLocked for i in idx}
    want = {"Gordium::Context": False, "Gordium::Context::Parcels": True, "Gordium::Context::Streets": True,
            "Gordium::Context::Buildings": False, "Gordium::Context::Notes": True}
    out["expected"] = want
    out["ok"] = (out["objects"] > 0 and out["gordium_locked"]
                 and all(out["own_locks"].get(k) == v for k, v in want.items())
                 and all(out["locks_after_parent_unlocked"].get(k) == v for k, v in want.items()))
    out["said"] = (g.STATE.get("said") or [])[-4:]
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    try:
        if g is not None:
            g._stop_worker()
    except Exception:
        pass
    out["done"] = True
    json.dump(out, open(T + "first_draw_locked.json", "w", encoding="utf-8"), indent=1, default=str)
