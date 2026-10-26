#! python3
"""Phase 1: open a feet doc, GordiumStart on the sample, Front Shaded zoomed; then return so Rhino idles (render
meshes). Phase 2 (meshed_phase2.py) measures and closes the doc."""
import json
import sys
import traceback

import Rhino
import scriptcontext as sc

HERE = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(HERE + "fill_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

log = {}
doc = None
try:
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
    import gordium_rhino as g
    doc = TestDocs("meshed").__enter__().open("Large Objects - Feet")
    g.gordium_check()
    o = g.overlay()
    for name in ("Front", "Perspective"):
        vp = doc.Views.Find(name, False).ActiveViewport
        vp.DisplayMode = Rhino.Display.DisplayModeDescription.FindByName("Shaded")
        vp.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    doc.Views.ActiveView = doc.Views.Find("Front", False)
    doc.Views.Redraw()
    sc.sticky["meshed_probe"] = {"doc": doc, "g": g}
    log["ok"] = True
except Exception:
    log["trace"] = traceback.format_exc()
    if doc is not None:
        close(doc)
finally:
    log["done"] = True
    json.dump(log, open(HERE + "meshed1.json", "w", encoding="utf-8"), default=str, indent=1)
