#! python3
"""The context map in Rhino 8 (the neighbourhood around a looked-up lot). Run in Rhino, not in CI.

A fresh document from Rhino's feet template; GordiumStart with 106 Ithaca Rd typed and Look up pressed (recorded
answers by default, the live services with sc.sticky["gordium_context_live"] = True); then records: the context
layers (locked, grey, visible), how many objects each holds and every object's source, the live footprints on
screen, how long the neighbourhood took, the check's summary (it must be what it is without the context), the
panel tick off and on again, and what a saved copy of the file holds (read back with File3dm: no object, user
text or document string from a store: none source). Writes <temp>/gordium_context/out.json and frames/*.png;
closes its documents (keep another document open while it runs)."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_context") + "/"
FRAMES = S + "frames/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(FRAMES, exist_ok=True)
LIVE = bool(sc.sticky.pop("gordium_context_live", False))
ADDRESS, FIXTURE = "106 Ithaca Rd, Ithaca, NY 14850", "106_ithaca_rd"
log = {"live": LIVE}


def fresh_module():
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


def context_layers(g, doc):
    out = {}
    for i in g._context_layer_indexes(doc):
        layer = doc.Layers[i]
        objs = list(doc.Objects.FindByLayer(layer) or [])
        out[layer.FullPath] = {"locked": layer.IsLocked, "visible": layer.IsVisible, "objects": len(objs),
                               "sources": sorted({o.Attributes.GetUserString(g.logic.CONTEXT_KEY) or "" for o in objs})}
    return out


docs = TestDocs("context").__enter__()
opened = []
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": ADDRESS}, lookup_fixture=None if LIVE else FIXTURE)
    said_before = len(g.STATE.get("said", []))
    started = time.time()
    g.gordium_check()                                  # an empty file: GordiumStart with the lookup, then the context
    log["start_seconds"] = round(time.time() - started, 2)
    log["said"] = g.STATE.get("said", [])[said_before:]
    log["layers"] = context_layers(g, doc)
    guides = g.STATE.get("context_guides") or {}
    log["footprints_on_screen"] = len(guides.get("lines") or [])
    last = g.STATE.get("last") or {}
    log["summary"] = last.get("view_summary")
    log["items"] = [(i["name"], i["status"], i["proposed"]) for i in last.get("items", [])]
    lots, buildings, problems = g._sorted_objects(doc)
    log["checker_sees"] = {"lot_candidates": len(lots), "buildings": len(buildings), "problems": problems}
    t = time.time()
    payload = g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))      # drawn again: replaces, never doubles
    log["redraw_seconds"] = round(time.time() - t, 2)
    log["counts"] = (payload or {}).get("counts")
    log["layers_after_redraw"] = context_layers(g, doc)
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    view.ActiveViewport.ZoomBoundingBox(guides.get("box") or view.ActiveViewport.GetFrustumBoundingBox())
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 1000))
    if bmp is not None:
        bmp.Save(FRAMES + "106_context.png")
    g.show_context(False)
    log["tick_off"] = context_layers(g, doc)
    g.show_context(True)
    log["tick_on"] = context_layers(g, doc)
    path = S + "saved.3dm"
    doc.Export(path)
    f = Rhino.FileIO.File3dm.Read(path)
    names = [layer.FullPath for layer in f.AllLayers]
    stored = []
    for o in f.Objects:
        a = o.Attributes
        stored.append(a.GetUserString(g.logic.CONTEXT_KEY) or "")
    log["saved_sources"] = sorted(set(stored))
    log["saved_strings"] = [f.Strings.GetKey(i) for i in range(f.Strings.Count)]
    blob = json.dumps([f.Strings.GetValue(i) for i in range(f.Strings.Count)])
    log["saved_has_footprints"] = "state_buildings" in set(stored) or "2014" in blob
    log["ok"] = bool(log["summary"]) and log["checker_sees"]["lot_candidates"] == 1 and not log["saved_has_footprints"]
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    json.dump({"ready": True}, open(S + "ready.json", "w", encoding="utf-8"))
