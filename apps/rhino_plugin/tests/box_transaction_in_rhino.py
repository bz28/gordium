#! python3
"""The start box as one transaction, with the address lookup, in Rhino 8 (review round 1 of PR #19). Run in Rhino,
not in CI. Phases, by sc.sticky["gordium_txn_phase"]:
- "run" (default): a fresh document with the sample lot, as GordiumStart makes it. Look up A (106 Ithaca Rd,
  recorded answers): the lot and 14 spot grades drawn, the sample lot taken out. Cancel: the model exactly as before
  (same objects, same ids). Look up B (109 Ithaca Rd): only B's 6 spot grades. Then a lookup whose State parcels
  didn't answer (the City's outline as a guide only): no lot curve written, Draw off, "Draw my lot…" offered.
  Captures of each step (Top view); the box session is kept for the next phases.
- "box" (sc.sticky["gordium_windows_mode"] = "box", as capture.py sets it): the real start box in that guide state,
  for a window capture; it closes itself after 12 s (nothing saved). Writes <temp>/gordium_windows/ready.json.
- "close": Cancel the session (the sample lot back) and close the document.
Writes <temp>/gordium_txn/out.json and frames/*.png."""
import copy
import json
import os
import sys
import tempfile
import time
import traceback

import Eto.Forms as ef
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_txn") + "/"
READY = os.path.join(tempfile.gettempdir(), "gordium_windows", "ready.json")
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
os.makedirs(os.path.dirname(READY), exist_ok=True)
phase = "box" if sc.sticky.pop("gordium_windows_mode", None) == "box" else sc.sticky.pop("gordium_txn_phase", "run")
log = {"phase": phase}


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


def objects(doc):
    return sorted(str(o.Id) for o in doc.Objects)


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    view.Redraw()
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + "frames/" + name + ".png")


def look_up(g, doc, session, facts, saved_ui, address, fixture, edit=None):
    g.STATE["lookup_fixture"] = fixture
    facts = dict(facts, address=address)
    saved_ui = g._lookup_start(facts, saved_ui)
    started = time.time()
    while g._lookup_poll() is None and time.time() - started < 60:
        time.sleep(0.2)
    if edit is not None:                       # a service down, as the recorded answers can't say
        g.STATE["lookup"]["answer"] = edit(copy.deepcopy(g.STATE["lookup"]["answer"]))
    return g._lookup_done(doc, facts, saved_ui, session)


def city_parcels_only(answer):
    """The State's parcels didn't answer: the lot came from the City's (store: derived), so only a guide."""
    w = answer["writes"]
    answer["writes"] = dict(w, guide_ring=w["lot_ring"], lot_ring=None, street_line=None, spots=[], frame=None)
    answer["details"]["lot"]["source_keys"] = ["city_parcels"]
    answer["labels"] = dict(answer.get("labels") or {}, lot="City of Ithaca tax parcels")
    return answer


try:
    if phase == "run":
        g = fresh_module()
        docs = TestDocs("txn").__enter__()
        doc = docs.open("Large Objects - Feet")
        options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
        g.STATE["zones"] = options["zones"]
        sample = g.ask({"cmd": "sample_site"})
        sample_lot = str(g._add_lot(doc, sample))       # as GordiumStart does on an empty file
        g._save_ui_state(doc, dict(g._ui_state(doc), from_sample=True, replaceable_lot=sample_lot))
        facts = dict(sample["facts"], address=sample["address"], lot_id=sample_lot)
        saved_ui = g._ui_state(doc)
        before = objects(doc)
        log["before"] = {"objects": len(before), "sample_lot": sample_lot}

        layers_before = sorted(layer.FullPath for layer in doc.Layers if not layer.IsDeleted)
        # A: the real box (confirm, run_box), its lookup, then Cancel
        g.STATE.update(box_picks=["lookup"], box_overrides={"address": "106 Ithaca Rd, Ithaca, NY 14850"},
                       lookup_fixture="106_ithaca_rd", box_cancel_after_picks=True,
                       on_confirm=None)
        result = g.confirm(doc, facts, options, "start")
        g.STATE.update(box_picks=[], box_cancel_after_picks=False)
        g._highlight(doc, facts)
        capture(doc, "2_cancel_back_to_sample")
        log["after_cancel"] = {"result": result, "objects_same": objects(doc) == before,
                               "sample_lot_there": g._find(doc, sample_lot) is not None,
                               "sample_on_site": g._find(doc, sample_lot) is not None and
                               doc.Layers[g._find(doc, sample_lot).Attributes.LayerIndex].FullPath == g.LAYERS["lot"],
                               "spot_grades": len(g._grade_points(doc)),
                               "layers_same": sorted(layer.FullPath for layer in doc.Layers if not layer.IsDeleted)
                               == layers_before}
        # the lookup's state before that Cancel, for the capture: the same lookup in a session we hold
        session = g.logic.BoxSession(g.RhinoTable(doc))
        fa, sa = look_up(g, doc, session, facts, saved_ui, "106 Ithaca Rd, Ithaca, NY 14850", "106_ithaca_rd")
        g._highlight(doc, fa)
        capture(doc, "1_lookup_A_106")
        log["after_A"] = {"objects": len(objects(doc)), "sample_held": g._find(doc, sample_lot) is not None and
                          doc.Layers[g._find(doc, sample_lot).Attributes.LayerIndex].FullPath == g.logic.HOLDING_LAYER,
                          "spot_grades": len(g._grade_points(doc)), "lots": len(g._lot_candidates(doc))}
        # B: look up 109 in the same session: only 109's spot grades, the sample still held
        fb, sb = look_up(g, doc, session, fa, sa, "109 Ithaca Rd, Ithaca, NY 14850", "109_ithaca_rd")
        g._highlight(doc, fb)
        capture(doc, "3_lookup_B_109")
        log["after_B"] = {"spot_grades": len(g._grade_points(doc)), "lot": fb.get("lot_id") in objects(doc),
                          "lots": len(g._lot_candidates(doc))}
        session.rollback()
        log["after_B_cancel"] = {"objects_same": objects(doc) == before}
        # Rhino "closes" mid-session (no Cancel, no Draw): the next GordiumStart's recovery puts the model back
        session = g.logic.BoxSession(g.RhinoTable(doc))
        look_up(g, doc, session, facts, g._ui_state(doc), "106 Ithaca Rd, Ithaca, NY 14850", "106_ithaca_rd")
        g._recover(doc)
        log["after_crash_recovery"] = {"objects_same": objects(doc) == before,
                                       "sample_on_site": doc.Layers[g._find(doc, sample_lot).Attributes.LayerIndex]
                                       .FullPath == g.LAYERS["lot"]}
        # the guide case, from the sample
        session = g.logic.BoxSession(g.RhinoTable(doc))
        fc, sc_ui = look_up(g, doc, session, facts, g._ui_state(doc), "106 Ithaca Rd, Ithaca, NY 14850",
                            "106_ithaca_rd", city_parcels_only)
        g._highlight(doc, fc)
        g.overlay().confirm = (None, [], None)          # the box is open: its guide is drawn
        capture(doc, "4_city_outline_guide")
        state = g._box_state(doc, fc, options, sc_ui, "start")
        rows = {r["key"]: r for r in g.logic.box_rows(state)}
        log["guide"] = {"guide_shown": g.STATE.get("lookup_guide") is not None, "lot_id": fc.get("lot_id"),
                        "lot_actions": rows["lot"]["actions"], "lot_text": rows["lot"]["text"],
                        "lot_review": rows["lot"]["review"], "draw_reason": g.logic.draw_reason(
                            dict(state, district_confirmed=True)), "objects_added": len(session.added)}
        sc.sticky["gordium_txn"] = {"facts": fc, "saved_ui": sc_ui, "options": options, "doc": doc.RuntimeSerialNumber,
                                    "before": before, "session": session}
        log["ok"] = (log["after_cancel"]["objects_same"] and log["after_cancel"]["sample_on_site"] and
                     log["after_cancel"]["layers_same"] and log["after_A"]["sample_held"] and
                     log["after_A"]["lots"] == 1 and log["after_B"]["spot_grades"] == 6 and
                     log["after_B_cancel"]["objects_same"] and log["after_crash_recovery"]["objects_same"] and
                     log["guide"]["lot_id"] is None and
                     log["guide"]["guide_shown"])
    elif phase == "box":
        g = sys.modules["gordium_rhino"]
        t = sc.sticky["gordium_txn"]
        doc = next(d for d in __import__("Rhino").RhinoDoc.OpenDocuments() if d.RuntimeSerialNumber == t["doc"])
        state = g._box_state(doc, t["facts"], t["options"], t["saved_ui"], "start")

        def shown(dialog):
            timer = ef.UITimer()
            timer.Interval = 12
            timer.Elapsed += g.logic.guard(lambda s, e: (timer.Stop(), dialog.Close(False)), "close the start box")
            timer.Start()
            json.dump({"title": dialog.Title, "at": time.time()}, open(READY, "w", encoding="utf-8"))

        state["_on_shown"] = shown
        g.ui.start_box(state, t["options"], "start")
    else:
        g = sys.modules["gordium_rhino"]
        t = sc.sticky.pop("gordium_txn", None)
        doc = next((d for d in __import__("Rhino").RhinoDoc.OpenDocuments()
                    if t and d.RuntimeSerialNumber == t["doc"]), None)
        if doc is not None:
            t["session"].rollback()
            log["restored"] = objects(doc) == t["before"]
            g.STATE.pop("lookup_guide", None)
            g.overlay().confirm = None
        log["closed"] = [d.Path for d in leftovers() if "txn" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
