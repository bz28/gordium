#! python3
"""Two panel and viewport details, in Rhino 8 (review rounds 10-11 of PR #15). Run in Rhino, not in CI.
1. The panel's message line: Zoning report… writes "Report saved to …"; the next check (an edit) clears it.
2. No lot label under the status box: Top view framed so the lot's top edge sits where the status box is; its
   length label is drawn below the box, not under it (capture frames/top_status_box.png).
Writes <temp>/gordium_message_line/out.json; closes its document (keep another document open while it runs)."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_message_line") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
log = {}


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


docs = TestDocs("message_line").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.STATE["on_confirm"] = lambda *a: None
    look_up_106(g, g.gordium_check)                                    # the sample lot and its starting house
    parts = g.STATE.get("panel_parts") or {}
    g.open_report()
    log["after_report"] = parts["message"].Text
    ids = [o.Id for o in g._buildings(doc)]
    move = rg.Transform.Translation(0, 2 / g._scale(doc), 0)
    for i in ids:
        doc.Objects.Transform(i, move, True)
    g.run_check(doc, report=False)                       # what live mode runs after an edit
    log["after_edit_check"] = parts["message"].Text
    log["message_cleared"] = log["after_report"].startswith("Report saved to ") and log["after_edit_check"] == ""
    view = doc.Views.Find("Top", False)
    doc.Views.ActiveView = view
    lot = g._find(doc, g.current_facts(doc).get("lot_id") or "")
    box = lot.Geometry.GetBoundingBox(True)
    view.ActiveViewport.ZoomBoundingBox(box)             # the lot's top edge right under the status box
    view.Redraw()
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    bmp.Save(S + "frames/top_status_box.png")
    log["capture"] = S + "frames/top_status_box.png"
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        close(doc)
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
