#! python3
"""check_button_in_rhino.py's claims (head from cb_wt.txt), run in phases so Rhino really goes idle between them:
RhinoApp.Wait() inside a running script never raises Rhino's Idle event, so the plugin's idle handler (which greys
the panel and runs the automatic check) never ran in the one-script version. Phase from cb_phase.txt:
  a: a fresh feet document, GordiumCheck (the sample drawn and checked), claim 1; a floor moved 3 ft. Script ends.
  b: (after real idle) claims 2. Ends (the panel and the viewport captured from outside).
  b2: Check pressed, claim 3; "Check after every edit" ticked; a floor moved. Ends.
  c: (after real idle) claim 4; the tick undone; the document closed.
Each phase writes cb_phases/<phase>.json ("done": true); claims accumulate in cb_phases/claims.json."""
import json
import os
import sys
import time
import traceback

import Rhino
import scriptcontext as sc
import System

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(H + "cb_wt.txt", encoding="utf-8").read().strip()
PHASE = open(H + "cb_phase.txt", encoding="utf-8").read().strip()
S = H + "cb_phases/"
os.makedirs(S, exist_ok=True)
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

KEEP = sc.sticky.setdefault("cb_phases", {})
claims = json.load(open(S + "claims.json", encoding="utf-8")) if PHASE != "a" and os.path.exists(S + "claims.json") else {}
log = {"phase": PHASE}


def claim(name, ok, detail=None):
    claims[name] = {"ok": bool(ok), "detail": detail}


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


def move_top_floor(g, doc):
    house = [o for o in doc.Objects if g.logic.on_layer(doc.Layers[o.Attributes.LayerIndex].FullPath, g.logic.MASSING)]
    doc.Objects.Transform(house[-1], Rhino.Geometry.Transform.Translation(3, 0, 0), True)
    doc.Views.Redraw()


def header_texts(parts):
    return [str(c.Text) for c in getattr(parts["header"], "Children", []) or [] if getattr(c, "Text", None)]


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + name + ".png")


try:
    if PHASE == "a":
        docs = TestDocs("checkbutton_phases").__enter__()
        g = fresh_module()
        doc = docs.open("Large Objects - Feet")
        KEEP.update(doc=doc.RuntimeSerialNumber, runs=[])
        g.gordium_check()
        parts = g.STATE.get("panel_parts") or {}
        buttons = [b.Text for b in parts.get("box_buttons") or []]
        auto = parts.get("auto_box")
        claim("1 Check first beside Edit site…, and Check after every edit unticked",
              buttons[:2] == ["Check", "Edit site…"] and auto is not None and auto.Checked is False,
              {"buttons": buttons, "auto": auto.Checked if auto else None})
        real_run = g.run_check
        runs = KEEP["runs"]
        g.run_check = lambda *a, **k: (runs.append(time.time()), real_run(*a, **k))[1]
        move_top_floor(g, doc)
        KEEP["edited_at"] = time.time()
    else:
        g = sys.modules["gordium_rhino"]
        doc = Rhino.RhinoDoc.FromRuntimeSerialNumber(KEEP["doc"])
        parts = g.STATE.get("panel_parts") or {}
        auto = parts.get("auto_box")
        runs = KEEP["runs"]
        log["idle"] = {"since_edit_s": round(time.time() - KEEP["edited_at"], 1), "stale_shown": g.STATE.get("stale_shown"),
                       "dirty": g.STATE.get("dirty"), "checks": len(runs)}
    if PHASE == "b":
        texts = header_texts(parts)
        rows = g._status_rows(g.overlay(), True)
        capture(doc, "2_changed_press_check")
        claim("2 an edit, then idle: no check ran", runs == [], len(runs))
        claim("2 the header says press Check and the rows are greyed",
              g.logic.CHANGED_SINCE in texts and parts.get("stale") is True, {"header": texts, "stale": parts.get("stale")})
        claim("2 the status box says it too", rows[0] == "Gordium · " + g.logic.CHANGED_SINCE, rows)
    if PHASE == "b2":                    # (after the outside capture of the panel and the viewport)
        g.check_now()
        claim("3 Check: one check, the rows current again", len(runs) == 1 and not parts.get("stale"), len(runs))
        capture(doc, "3_checked")
        auto.Checked = True
        KEEP["saved_auto"] = g._ui_state(doc).get("auto_check")
        move_top_floor(g, doc)
        KEEP["edited_at"] = time.time()
    if PHASE == "c":
        claim("4 ticked: saved, and an edit is checked by itself", KEEP.get("saved_auto") is True and len(runs) == 2,
              {"saved": KEEP.get("saved_auto"), "checks": len(runs)})
        capture(doc, "4_checked_by_itself")
        auto.Checked = False
        close(doc)
        sc.sticky.pop("cb_phases", None)
except Exception:
    log["trace"] = traceback.format_exc()
    try:
        if doc is not None:
            close(doc)
    except Exception:
        pass
finally:
    json.dump(claims, open(S + "claims.json", "w", encoding="utf-8"), default=str, indent=1)
    log["done"] = True
    json.dump(log, open(S + PHASE + ".json", "w", encoding="utf-8"), default=str, indent=1)
