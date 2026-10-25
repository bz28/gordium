#! python3
"""Re-lookup on a drawn site (Ben, 2026-10-21), in Rhino 8, each claim asserted (RHINO_QUEUE 5). Run in Rhino, not
in CI; the logic is tested in CI (packages/design_checker/tests/test_re_lookup.py). A fresh feet document:
1. GordiumStart on the empty file: the sample (106 Ithaca Rd), its lot and starting house.
2. Edit site…, "96 Ithaca Rd" typed, Look up (recorded answers): while the box is open nothing in the model has
   changed, the looked-up lot is shown dashed; Draw: the sample's lot and house gone, 96's lot drawn, no question
   asked (all of it was Gordium's). 96 is a corner lot, so no starting house is drawn on it (by design: which yards
   are front is the architects' open question). One Undo puts the sample back exactly; Redo again.
3. A new file: the sample's starting house edited (one floor moved), Edit site…, Look up 96: asked once, "Start
   fresh for 96 …? Your changes to the starting house will be removed.", the Keep answer "Keep my building and
   check it on 96 …'s lot"; Keep my building: the floors kept, the lot is 96's.
4. Edit site…, Look up 96 again: no question, nothing in the model changes.
5. A new file: the sample's lot made the architect's survey (as Use my survey… leaves it) and its starting house
   edited; Look up 96: a new address is a new site (Ben, 2026-10-25), so even Keep my building replaces their lot,
   and both the question ("Your surveyed lot will be replaced by 96 …'s lot.") and the Keep answer ("… (your
   surveyed lot will be replaced)") say so. Keep: the floors kept, the surveyed lot gone, 96's tax-map lot drawn
   (not marked as a survey). One Undo puts the surveyed lot and the edited house back exactly; Redo again.
Writes <temp>/gordium_re_lookup/out.json and Top captures; closes its document."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_re_lookup") + "/"
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


def objects(doc):
    """Every object in the model: id -> its layer's full path."""
    return {str(o.Id): doc.Layers[o.Attributes.LayerIndex].FullPath for o in doc.Objects}


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + name + ".png")


def edit_site(g, doc, address, fixture, answer=None):
    """Edit site… with the address typed and Look up pressed (scripted: the architect ticks the district and
    presses Draw); what the model and the box were while the box was open, and the question, if any."""
    seen = {"asked": []}

    def on_confirm(doc_, facts, text, state):
        seen["objects"] = objects(doc)
        seen["guide_shown"] = g.STATE.get("lookup_guide") is not None

    def on_question(question, fresh, keep):
        seen["asked"].append([question, fresh, keep])
        return answer(fresh, keep) if answer else None

    g.STATE.update(on_confirm=on_confirm, on_reset_question=on_question, box_picks=["lookup"],
                   box_overrides={"address": address}, lookup_fixture=fixture)
    try:
        g.edit_facts()
    finally:
        for k in ("on_confirm", "on_reset_question", "box_picks", "box_overrides", "lookup_fixture"):
            g.STATE.pop(k, None)
    return seen


docs = TestDocs("relookup").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    # 1. the sample
    g.gordium_check()                              # an empty file: GordiumStart, the sample drawn
    facts = g.current_facts(doc)
    sample_lot, house = facts.get("lot_id"), g.RhinoTable(doc).massing()
    before = objects(doc)
    claim("1 the sample: its lot and a starting house", g._find(doc, sample_lot) is not None and len(house) >= 2,
          {"lot": sample_lot, "house": house})
    capture(doc, "1_sample")

    # 2. a new address over what Gordium drew
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")
    log["step2"] = {k: v for k, v in seen.items() if k != "objects"}
    claim("2 Look up changed nothing in the model while the box was open", seen.get("objects") == before,
          {"before": len(before), "during": len(seen.get("objects") or {})})
    claim("2 the looked-up lot was shown dashed while the box was open", seen.get("guide_shown"), seen)
    after = objects(doc)
    facts = g.current_facts(doc)
    new_house = g.RhinoTable(doc).massing()
    ui_state = g._ui_state(doc)
    claim("2 Draw asked nothing (all of it was Gordium's)", seen["asked"] == [], seen["asked"])
    claim("2 the sample's lot and house are gone", not ({sample_lot} | set(house)) & set(after),
          sorted(({sample_lot} | set(house)) & set(after)))
    lot = g._find(doc, facts.get("lot_id") or "")
    claim("2 96's lot is drawn on Site", lot is not None and "96" in (lot.Attributes.Name or "") and
          doc.Layers[lot.Attributes.LayerIndex].FullPath == g.LAYERS["lot"],
          lot.Attributes.Name if lot else None)
    # 96 Ithaca Rd is a corner lot (Ithaca Rd and Mitchell St): no starting house is drawn on one, by design (which
    # yards are front, side and rear is the architects' open question, §325-19C; envelope.py says so)
    claim("2 no starting house on 96, a corner lot (the architects' open question)", new_house == [] and
          any("corner lot" in n for n in (g.STATE.get("start") or {}).get("notes") or []),
          (g.STATE.get("start") or {}).get("notes"))
    claim("2 the file says what is drawn: 96, and no house of Gordium's",
          g.logic.same_address(ui_state.get("drawn_address"), "96 Ithaca Rd") and not ui_state.get("house_fingerprint"),
          {k: ui_state.get(k) for k in ("drawn_address", "house_fingerprint")})
    capture(doc, "2_drawn_96")
    doc.Undo()
    undone = objects(doc)
    claim("2 one Undo puts the sample back exactly", undone == before,
          {"missing": sorted(set(before) - set(undone)), "extra": sorted(set(undone) - set(before))})
    doc.Redo()
    claim("2 Redo draws 96 again", objects(doc) == after, len(objects(doc)))

    # 3. a new file: the sample's starting house edited, then 96 looked up: asked once; keep it
    close(doc)
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.gordium_check()
    house = g.RhinoTable(doc).massing()
    floor = g._find(doc, house[-1])
    moved = str(doc.Objects.Transform(floor, Rhino.Geometry.Transform.Translation(3, 0, 0), True))
    house = house[:-1] + [moved]                   # (the same id when Rhino replaces it in place)
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", lambda fresh, keep: keep[1])
    log["step3"] = {k: v for k, v in seen.items() if k != "objects"}
    asked = seen["asked"]
    claim("3 asked once, naming the edited house", len(asked) == 1 and asked[0][0].startswith("Start fresh for 96")
          and asked[0][0].endswith("Your changes to the starting house will be removed.") and asked[0][2],
          asked)
    claim("3 the Keep answer names 96's lot (the sample's lot was Gordium's: nothing of theirs replaced)",
          asked[0][2][0].startswith("Keep my building and check it on 96 Ithaca R") and asked[0][2][0].endswith(
              "'s lot"), asked[0][2])
    facts = g.current_facts(doc)
    lot = g._find(doc, facts.get("lot_id") or "")
    kept = g.RhinoTable(doc).massing()
    claim("3 Keep my building: the floors kept, the lot is 96's", sorted(kept) == sorted(house) and
          lot is not None and "96" in (lot.Attributes.Name or ""), {"kept": kept})
    capture(doc, "3_kept_on_96")

    # 4. the same address again: nothing changes
    before = objects(doc)
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")
    log["step4"] = {k: v for k, v in seen.items() if k != "objects"}
    claim("4 the same address: no question and nothing in the model changes",
          seen["asked"] == [] and objects(doc) == before, seen["asked"])

    # 5. a new file: the architect's surveyed lot and an edited house, then 96 looked up: Keep replaces the lot too
    close(doc)
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.gordium_check()
    facts = g.current_facts(doc)
    survey_lot = facts.get("lot_id")
    facts["lot_surveyed"] = True                   # as Use my survey… leaves it (pick_survey): theirs, a survey
    g.save_facts(doc, facts)
    g._save_ui_state(doc, g.logic.settle(g._ui_state(doc), "lot"))
    house = g.RhinoTable(doc).massing()
    floor = g._find(doc, house[-1])
    moved = str(doc.Objects.Transform(floor, Rhino.Geometry.Transform.Translation(3, 0, 0), True))
    house = house[:-1] + [moved]
    before = objects(doc)
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", lambda fresh, keep: keep[1])
    log["step5"] = {k: v for k, v in seen.items() if k != "objects"}
    asked = seen["asked"]
    claim("5 asked once; the question says their surveyed lot will be replaced by 96's",
          len(asked) == 1 and asked[0][0].startswith("Start fresh for 96") and
          "Your changes to the starting house will be removed." in asked[0][0] and
          asked[0][0].endswith("'s lot.") and "Your surveyed lot will be replaced by 96 Ithaca R" in asked[0][0],
          asked)
    claim("5 the Keep answer says their surveyed lot will be replaced",
          asked and asked[0][2] and asked[0][2][0].startswith("Keep my building and check it on 96 Ithaca R") and
          asked[0][2][0].endswith("'s lot (your surveyed lot will be replaced)"), asked and asked[0][2])
    facts = g.current_facts(doc)
    lot = g._find(doc, facts.get("lot_id") or "")
    after = objects(doc)
    claim("5 Keep my building: the floors kept, the surveyed lot replaced by 96's tax-map lot",
          sorted(g.RhinoTable(doc).massing()) == sorted(house) and survey_lot not in after and lot is not None and
          "96" in (lot.Attributes.Name or "") and facts.get("lot_surveyed") is False,
          {"kept": g.RhinoTable(doc).massing(), "lot": lot.Attributes.Name if lot else None,
           "surveyed": facts.get("lot_surveyed")})
    capture(doc, "5_kept_on_96_survey_replaced")
    doc.Undo()
    undone = objects(doc)
    claim("5 one Undo puts the surveyed lot and the edited house back exactly", undone == before,
          {"missing": sorted(set(before) - set(undone)), "extra": sorted(set(undone) - set(before))})
    doc.Redo()
    claim("5 Redo draws 96 again, the building kept", objects(doc) == after, len(objects(doc)))
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
