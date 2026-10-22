#! python3
"""The Check button (Ben, 2026-10-21), in Rhino 8, each claim asserted. Run in Rhino, not in CI; the rules are
tested in CI (packages/design_checker/tests/test_check_button.py) and the plugin's own code headless (coordination
headless/check_button/). A fresh feet document:
1. GordiumCheck on the empty file: the sample drawn and checked; the panel has Check first beside Edit site…, and
   "Check after every edit" unticked.
2. A floor moved 3 ft (Rhino's own Transform), then Rhino idle for 3 s: no check ran; the panel's header says "Model
   changed since the last check — press Check", its rows show no marks ("—"), and the viewport's status box says
   the same. Screenshot.
3. The panel's Check pressed: one check, the rows current again.
4. "Check after every edit" ticked: saved in the file; a floor moved again: checked by itself within 3 s of idle.
   Unticked again at the end (the file left as found).
Writes <temp>/gordium_check_button/out.json and Top captures; closes its document."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_check_button") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


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


def idle(seconds):
    """Let Rhino run its idle loop for a while (the plugin's idle handler runs there)."""
    end = time.time() + seconds
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        time.sleep(0.05)


def move_top_floor(g, doc):
    house = [o for o in doc.Objects if g.logic.on_layer(doc.Layers[o.Attributes.LayerIndex].FullPath, g.logic.MASSING)]
    o = house[-1]
    doc.Objects.Transform(o, Rhino.Geometry.Transform.Translation(3, 0, 0), True)
    doc.Views.Redraw()


def header_texts(parts):
    out = []
    for c in getattr(parts["header"], "Children", []) or []:
        t = getattr(c, "Text", None)
        if t:
            out.append(str(t))
    return out


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + name + ".png")


docs = TestDocs("checkbutton").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.gordium_check()                               # an empty file: GordiumStart, the sample drawn and checked
    parts = g.STATE.get("panel_parts") or {}
    buttons = [b.Text for b in parts.get("box_buttons") or []]
    auto = parts.get("auto_box")
    claim("1 Check first beside Edit site…, and Check after every edit unticked",
          buttons[:2] == ["Check", "Edit site…"] and auto is not None and auto.Checked is False,
          {"buttons": buttons, "auto": auto.Checked if auto else None})

    runs = []
    real_run = g.run_check
    g.run_check = lambda *a, **k: (runs.append(1), real_run(*a, **k))[1]
    move_top_floor(g, doc)
    idle(3)
    texts = header_texts(parts)
    rows = g._status_rows(g.overlay(), True)
    capture(doc, "2_changed_press_check")
    claim("2 an edit, then idle: no check ran", runs == [], len(runs))
    claim("2 the header says press Check and the rows are greyed",
          g.logic.CHANGED_SINCE in texts and parts.get("stale") is True, {"header": texts, "stale": parts.get("stale")})
    claim("2 the status box says it too", rows[0] == "Gordium · " + g.logic.CHANGED_SINCE, rows)

    g.check_now()
    claim("3 Check: one check, the rows current again", len(runs) == 1 and not parts.get("stale"), len(runs))
    capture(doc, "3_checked")

    auto.Checked = True
    saved = g._ui_state(doc).get("auto_check")
    move_top_floor(g, doc)
    idle(3)
    claim("4 ticked: saved, and an edit is checked by itself", saved is True and len(runs) == 2,
          {"saved": saved, "checks": len(runs)})
    auto.Checked = False
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
    raise                               # a failed claim fails the run loudly (the standing rule)
finally:
    try:
        if doc is not None:
            close(doc)
    except Exception:
        pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
