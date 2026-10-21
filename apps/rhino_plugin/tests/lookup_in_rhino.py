#! python3
"""The address lookup in the start box, in Rhino 8 (PR #19). Run in Rhino, not in CI.

For each of 106, 109 and 96 Ithaca Rd: a fresh document from Rhino's feet template; GordiumStart with the
address typed and Look up pressed (the lookup runs in its own process: recorded answers by default, the live
services with sc.sticky["gordium_lookup_live"] = True); records what the box then shows (each row, its source,
its amber line, the box's one amber line), what was written into the model (the lot curve, the spot grades),
the starting house and the panel's summary, and a Top-view capture. Writes <temp>/gordium_lookup/out.json and
frames/*.png; closes its documents (keep another document open while it runs). With
sc.sticky["gordium_lookup_only"] = "106_ithaca_rd" it runs that one and leaves its document open for a capture."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_lookup") + "/"
FRAMES = S + "frames/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(FRAMES, exist_ok=True)
LIVE = bool(sc.sticky.pop("gordium_lookup_live", False))
CASES = [("106 Ithaca Rd, Ithaca, NY 14850", "106_ithaca_rd"), ("109 Ithaca Rd, Ithaca, NY 14850", "109_ithaca_rd"),
         ("96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")]
ONLY = sc.sticky.pop("gordium_lookup_only", None)    # one address, its document left open for the window capture
if ONLY:                                              # (then closed by the caller through the document's window)
    CASES = [c for c in CASES if c[1] == ONLY]
log = {"live": LIVE, "cases": [], "only": ONLY}


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


docs = TestDocs("lookup").__enter__()
opened = []
try:
    for address, fixture in CASES:
        g = fresh_module()
        doc = docs.open("Large Objects - Feet")
        opened.append(doc)
        case = {"address": address}
        log["cases"].append(case)
        seen = {}

        def on_confirm(doc_, facts, text, state, seen=seen):
            seen["rows"] = [{k: r.get(k) for k in ("key", "text", "review", "check", "matches", "status")}
                            for r in g.logic.box_rows(state)]
            seen["amber"] = g.logic.uncertain(state)
            seen["corner_lot"] = state.get("corner_lot")
            seen["zone"] = (state.get("zone"), state.get("zone_source"), state.get("district_confirmed"))

        g.STATE.update(on_confirm=on_confirm, box_picks=["lookup"], box_overrides={"address": address},
                       lookup_fixture=None if LIVE else fixture)
        g.gordium_check()                               # an empty file: GordiumStart, with the lookup
        case["box"] = seen
        facts = g.current_facts(doc)
        lot = g._find(doc, facts.get("lot_id") or "")
        case["lot_name"] = lot.Attributes.Name if lot else None
        case["lot_area_sf"] = round(g._feet_area(doc, Rhino.Geometry.AreaMassProperties.Compute(lot.Geometry).Area),
                                    1) if lot else None
        case["spot_grades"] = len(g._grade_points(doc))
        case["facts"] = {k: facts.get(k) for k in ("address", "zone", "corner_lot", "lot_surveyed", "unsettled",
                                                   "grade_from", "grade_is")}
        case["starting_house"] = {k: v for k, v in (g.STATE.get("start") or {}).items() if k != "floors"}
        last = g.STATE.get("last") or {}
        case["summary"] = last.get("view_summary")
        case["items"] = [(i["name"], i["status"], i["proposed"], i.get("reason")) for i in last.get("items", [])]
        sources = g.fact_sources(doc)
        case["saved_sources"] = {k: (v.get("value"), v.get("source"), v.get("confirmed_by")) for k, v in sources.items()}
        ui = g._ui_state(doc)
        case["saved_lookup_keys"] = sorted(k for k in ui if k.startswith("lookup"))
        view = doc.Views.Find("Top", False) or doc.Views.ActiveView
        bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
        if bmp is not None:
            bmp.Save(FRAMES + fixture + ".png")
    log["ok"] = all(c.get("summary") for c in log["cases"])
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    for d in ([] if ONLY and "trace" not in log else opened):
        try:
            close(d)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    json.dump({"ready": True}, open(S + "ready.json", "w", encoding="utf-8"))
