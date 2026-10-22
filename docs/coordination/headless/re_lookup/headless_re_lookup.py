"""Re-lookup (RHINO_QUEUE 5: apps/rhino_plugin/tests/re_lookup_in_rhino.py) run WITHOUT Rhino, plus a 5th scenario
(an edited starting house, Cancel at the question).

How: apps/rhino_plugin/gordium_rhino.py and gordium_ui.py are imported unchanged from /home/user/wt/re-lookup
against stand-ins for RhinoCommon, Eto and scriptcontext (fakerhino.py, fake_eto.py, copied from
/home/user/wt/coordination/docs/coordination/headless/ and extended: undo records are RECORDED in doc.journal, with
every model change made while each was open). The checker is answered in process (design_checker.__main__.answer);
the lookup runs as the plugin runs it, in its own process, on the recorded answers (--fixture). Each in-Rhino claim
is checked as the in-Rhino script checks it, never weakened. Undo / Redo themselves are out of scope (Rhino only).

Run from /home/user/wt/re-lookup:
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(ls -d packages/* | tr '\\n' ':') /home/user/venv/bin/python <this file>
Writes results_re_lookup.json (and raw_re_lookup.json) beside this file."""
import copy
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import WT, fresh_module, new_doc  # noqa: E402

import fakerhino  # noqa: E402
import Rhino  # noqa: E402

OUT = os.path.join(HERE, "results_re_lookup.json")
RAW = os.path.join(HERE, "raw_re_lookup.json")
SHIM = os.path.join(HERE, "pyshim.sh")
GROUP = "relookup"
W = "re_lookup_in_rhino step %s"
RESULTS, RAWLOG = [], {}
RP_MODEL = ("Real RhinoCommon object and layer behaviour (Delete, ModifyAttributes onto the hidden holding layer, "
            "Transform keeping the id) is MODELLED by fakerhino.py, not proven.")


def record(rid, where, title, needs, offline, ok, evidence, rhino_part, detail=None):
    RESULTS.append({"id": rid, "group": GROUP, "where": where, "title": title, "needs": needs, "offline": offline,
                    "offline_ok": ok if ok is None else bool(ok), "evidence": evidence, "rhino_part": rhino_part})
    RAWLOG[rid] = detail
    print(("PASS " if ok else "N/A  " if ok is None else "FAIL ") + rid + ": " + title, flush=True)


def guarded(rid, where, title, needs, offline, rhino_part, fn):
    """One claim's check; an exception is a failed check (its traceback in the raw log), never skipped."""
    try:
        ok, evidence, detail = fn()
    except Exception as e:
        ok, evidence, detail = False, "The headless check raised %s: %s" % (type(e).__name__, str(e)[:300]), \
            traceback.format_exc()
    record(rid, where, title, needs, offline, ok, evidence, rhino_part, detail)


# ---- the in-Rhino script's helpers, on the stand-in document ---------------------------------------------------

def objects(doc):
    """Every object in the model: id -> its layer's full path (as re_lookup_in_rhino.objects)."""
    return {str(o.Id): doc.Layers[o.Attributes.LayerIndex].FullPath for o in doc.Objects}


def model(doc):
    """Stricter than objects(): every object's layer, name, box and user strings, and the live layers."""
    out = {}
    for o in doc.Objects:
        b = o.Geometry.GetBoundingBox(True)
        out[str(o.Id)] = (doc.Layers[o.Attributes.LayerIndex].FullPath, o.Attributes.Name,
                          tuple(round(v, 6) for v in (b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z)),
                          tuple(sorted(o.Attributes.strings.items())))
    return {"objects": out, "layers": sorted(x.FullPath for x in doc.Layers if not x.IsDeleted)}


def edit_site(g, doc, address, fixture, answer=None, extra=None):
    """Edit site… with the address typed and Look up pressed (scripted, as re_lookup_in_rhino.edit_site), plus the
    document's journal entries (model changes, undo records) made during it."""
    seen = {"asked": []}
    start = len(doc.journal)

    def on_confirm(doc_, facts, text, state):
        seen["objects"] = objects(doc)
        seen["guide_shown"] = g.STATE.get("lookup_guide") is not None

    def on_question(question, fresh, keep):
        seen["asked"].append([question, fresh, keep])
        return answer(fresh, keep) if answer else None

    g.STATE.update(on_confirm=on_confirm, on_reset_question=on_question, box_picks=["lookup"],
                   box_overrides=dict({"address": address}, **(extra or {})), lookup_fixture=fixture)
    try:
        g.edit_facts()
    finally:
        for k in ("on_confirm", "on_reset_question", "box_picks", "box_overrides", "lookup_fixture"):
            g.STATE.pop(k, None)
    seen["journal"] = doc.journal[start:]
    return seen


def undo_summary(journal):
    """Begin/End undo records in a journal slice, and which model changes fell inside / outside an open record."""
    begins = [e for e in journal if e[0] == "begin_undo"]
    ends = [e for e in journal if e[0] == "end_undo"]
    changes = [e for e in journal if e[0] not in ("begin_undo", "end_undo")]
    inside = [e for e in changes if e[2] is not None]
    outside = [e for e in changes if e[2] is None]
    kinds = {k: sum(1 for e in changes if e[0] == k) for k in ("add", "delete", "modify", "replace")}
    return {"begins": begins, "ends": ends, "changes": len(changes), "inside": len(inside), "outside": outside,
            "kinds": kinds,
            "records_used": sorted({e[2] for e in inside})}


# ================================================================================================================
# Steps 1-4: re_lookup_in_rhino.py, claim by claim
# ================================================================================================================

TRACKS = {
    "a": ("", "", "Track A: re_lookup_in_rhino.py as revised (2026-10-22, uncommitted in the re-lookup worktree), "
               "on the recorded answers as they are (96 Ithaca Rd faces Ithaca Rd and Mitchell St: a corner lot)."),
    "b": ("-b", "onestreet", "Track B (added, diagnostic): the same steps with the recorded lookup answers for 96 and "
          "109 changed by lookup_shim.py (GORDIUM_SHIM=onestreet) to say one street (Ithaca Rd) and not a corner lot, "
          "so the checker can draw a starting house and steps 2-4 can be evaluated. (Answering No in the box instead "
          "is not equivalent: rhino_logic.corner_answered drops the street lines when the answer flips, and the rear "
          "yard can then not be worked out.)"),
}


def use_track(g, shim):
    """Track B: the lookup subprocess through lookup_shim.py (as headless_context_lookup.py does for R-2a)."""
    os.environ["GORDIUM_SHIM"] = shim
    if shim:
        g._python = lambda: SHIM


def steps_1_to_4(track="a"):
    sfx, shim, note = TRACKS[track]
    extra = None
    W = "re_lookup_in_rhino step %s" + ("" if track == "a" else " (track B: one-street answers)")
    g = fresh_module()
    use_track(g, shim)
    doc = new_doc()
    written = len(fakerhino.WRITTEN)
    RAWLOG["track" + sfx] = note

    # 1. the sample
    g.gordium_check()                              # an empty file: GordiumStart, the sample drawn
    facts = g.current_facts(doc)
    sample_lot, house = facts.get("lot_id"), g.RhinoTable(doc).massing()
    before = objects(doc)
    RAWLOG["step1" + sfx] = {"lot": sample_lot, "house": house, "ui": g._ui_state(doc), "said": g.STATE.get("said")}

    def c1():
        ok = g._find(doc, sample_lot) is not None and len(house) >= 2
        lot = g._find(doc, sample_lot)
        return ok, ("GordiumStart on an empty feet document drew the sample lot %s (\"%s\", on %s) and a starting "
                    "house of %d floors on %s; the file's drawn_address: \"%s\"." % (
                        sample_lot, lot.Attributes.Name if lot else None,
                        doc.Layers[lot.Attributes.LayerIndex].FullPath if lot else None, len(house), g.logic.MASSING,
                        g._ui_state(doc).get("drawn_address"))), {"lot": sample_lot, "house": house}
    guarded("relookup-1-sample" + sfx, W % 1, "The sample: its lot and a starting house", "rhino", "partial",
            RP_MODEL + " That the lot and floors are really drawn and framed in Rhino's views.", c1)

    # 2. a new address over what Gordium drew
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", extra=extra)
    RAWLOG["step2" + sfx] = {k: v for k, v in seen.items() if k != "objects"}
    after = objects(doc)
    facts = g.current_facts(doc)
    new_house = g.RhinoTable(doc).massing()
    ui_state = g._ui_state(doc)

    def c2a():
        during = seen.get("objects")
        ok = during == before
        return ok, ("While the box was open after Look up of 96 Ithaca Rd (recorded answers), the model held %d "
                    "objects, identical ids and layers to the %d before (missing %s, extra %s)." % (
                        len(during or {}), len(before), sorted(set(before) - set(during or {})),
                        sorted(set(during or {}) - set(before)))), None
    guarded("relookup-2-preview-untouched" + sfx, W % 2, "Look up changed nothing in the model while the box was open",
            "code", "covered", "None beyond the modelled object table: the check compares every object's id and "
                               "layer.", c2a)

    def c2b():
        ok = bool(seen.get("guide_shown"))
        return ok, ("STATE[\"lookup_guide\"] (the ring the display conduit draws dashed) was %s while the box was "
                    "open." % ("set" if ok else "NOT set")), seen.get("guide_shown")
    guarded("relookup-2-preview-dashed" + sfx, W % 2, "The looked-up lot was shown dashed while the box was open", "rhino",
            "partial", "That the conduit really draws STATE[\"lookup_guide\"] dashed in the viewport (drawing).", c2b)

    def c2c():
        return seen["asked"] == [], "Questions asked at Draw: %s." % (seen["asked"] or "none"), seen["asked"]
    guarded("relookup-2-no-question" + sfx, W % 2, "Draw asked nothing (all of it was Gordium's)", "code", "covered",
            "Nothing: the question goes through STATE[\"on_reset_question\"] in scripted runs; the real dialog is "
            "never shown here.", c2c)

    def c2d():
        left = sorted(({sample_lot} | set(house)) & set(after))
        return not left, ("After Draw, of the sample's lot and %d floors, still in the model: %s." % (
            len(house), left or "none")), left
    guarded("relookup-2-old-gone" + sfx, W % 2, "The sample's lot and house are gone", "rhino", "partial", RP_MODEL, c2d)

    lot = g._find(doc, facts.get("lot_id") or "")

    def c2e():
        ok = lot is not None and "96" in (lot.Attributes.Name or "") and \
            doc.Layers[lot.Attributes.LayerIndex].FullPath == g.LAYERS["lot"]
        return ok, ("The saved lot_id %s: \"%s\" on layer %s (LAYERS[\"lot\"] = %s)." % (
            facts.get("lot_id"), lot.Attributes.Name if lot else None,
            doc.Layers[lot.Attributes.LayerIndex].FullPath if lot else None, g.LAYERS["lot"])), None
    guarded("relookup-2-new-lot" + sfx, W % 2, "96's lot is drawn on Site", "rhino", "partial", RP_MODEL, c2e)

    def c2f():
        ok = len(new_house) >= 2 and not set(new_house) & set(house)
        return ok, ("The starting house after Draw: %d floors on %s, sharing %d ids with the sample's." % (
            len(new_house), g.logic.MASSING, len(set(new_house) & set(house)))), new_house
    guarded("relookup-2-new-house" + sfx, W % 2, "A new starting house is drawn for it", "rhino", "partial", RP_MODEL, c2f)

    def c2g():
        fp = g.RhinoTable(doc).fingerprint(new_house)
        ok = g.logic.same_address(ui_state.get("drawn_address"), "96 Ithaca Rd") and \
            ui_state.get("house_fingerprint") == fp
        return ok, ("The file's box state: drawn_address \"%s\"; house_fingerprint %s the fingerprint of the house now "
                    "drawn." % (ui_state.get("drawn_address"),
                                "equals" if ui_state.get("house_fingerprint") == fp else "DIFFERS FROM")), \
            {"drawn_address": ui_state.get("drawn_address"), "saved_fp": ui_state.get("house_fingerprint"), "fp": fp}
    guarded("relookup-2-file-says" + sfx, W % 2, "The file says what is drawn: 96, its house as Gordium drew it", "code",
            "covered", "Rhino's document strings saving through a real save and reopen (not done here).", c2g)

    u2 = undo_summary(seen["journal"])
    RAWLOG["step2_undo" + sfx] = u2
    RAWLOG["step2_said" + sfx] = [w for w in fakerhino.WRITTEN[written:] if "corner" in w or "starting building" in w
                                  or "buildable" in w][-4:]

    def c2h():
        ok = (len(u2["begins"]) == 1 and len(u2["ends"]) == 1 and u2["ends"][0][1] == u2["begins"][0][1]
              and u2["ends"][0][2] is True and not u2["outside"] and u2["changes"] > 0)
        # and the begin comes before every change, the end after
        j = seen["journal"]
        kinds = [e[0] for e in j]
        if ok:
            b, e = kinds.index("begin_undo"), kinds.index("end_undo")
            ok = all(b < i < e for i, k in enumerate(kinds) if k not in ("begin_undo", "end_undo"))
        return ok, ("During Edit site… Draw: BeginUndoRecord called %d time(s) (%s), EndUndoRecord %d time(s) (%s); "
                    "%d model changes (%d added, %d deleted, %d attribute edits: the hold onto the holding layer and marks), "
                    "%d inside the open record, %d outside it; floors on %s after: %d." % (
                        len(u2["begins"]), [(x[1], x[2]) for x in u2["begins"]], len(u2["ends"]),
                        [(x[1], x[2]) for x in u2["ends"]], u2["changes"], u2["kinds"]["add"],
                        u2["kinds"]["delete"], u2["kinds"]["modify"], u2["inside"], len(u2["outside"]),
                        g.logic.MASSING, len(new_house))), u2
    guarded("relookup-2-one-undo-record" + sfx, W % 2, "The reset, the new lot and the starting house redrawn are made "
            "inside one undo record (Begin/EndUndoRecord once each)", "rhino", "partial",
            "Only the calls are recorded (fakerhino journal). That Rhino really groups them as one Undo step is "
            "Rhino's.", c2h)

    record("relookup-2-undo" + sfx, W % 2, "One Undo puts the sample back exactly", "rhino", "none", None,
           "Out of scope headless: the stand-in records BeginUndoRecord/EndUndoRecord (see relookup-2-one-undo-record) "
           "but does not model Rhino's Undo.", "All of it: doc.Undo() in Rhino restores the sample's lot and house, "
           "ids and layers as before.")
    record("relookup-2-redo" + sfx, W % 2, "Redo draws 96 again", "rhino", "none", None,
           "Out of scope headless: Redo is Rhino's.", "All of it: doc.Redo() in Rhino brings 96's lot and house back.")

    # 3. the starting house edited: asked once; keep it
    if not new_house:                             # re_lookup_in_rhino.py would raise IndexError here too
        record("relookup-3-runs" + sfx, W % 3, "Step 3 can run: there is a starting-house floor to edit", "code",
               "covered", False, "No floor on %s after step 2 (the checker said: %s), so new_house[-1] raises "
               "IndexError: re_lookup_in_rhino.py stops here in Rhino as well; steps 3 and 4 are not evaluated on this "
               "track (see track B)." % (g.logic.MASSING, RAWLOG["step2_said" + sfx]),
               "None: this is the in-Rhino script's own data, not a Rhino behaviour.")
        return
    floor = g._find(doc, new_house[-1])
    moved = str(doc.Objects.Transform(floor, Rhino.Geometry.Transform.Translation(3, 0, 0), True))
    new_house = new_house[:-1] + [moved]          # (the same id when Rhino replaces it in place)
    seen = edit_site(g, doc, "109 Ithaca Rd, Ithaca, NY 14850", "109_ithaca_rd", lambda fresh, keep: keep[1],
                     extra=extra)
    RAWLOG["step3" + sfx] = {k: v for k, v in seen.items() if k != "objects"}
    asked = seen["asked"]

    def c3a():
        ok = len(asked) == 1 and asked[0][0].startswith("Start fresh for 109") and \
            asked[0][0].endswith("Your changes to the starting house will be removed.") and asked[0][2]
        return ok, ("One floor moved 3 ft, then Look up 109 Ithaca Rd and Draw: asked %d time(s): %s" % (
            len(asked), asked)), asked
    guarded("relookup-3-asked-once" + sfx, W % 3, "Asked once, naming the edited house", "rhino", "partial",
            "The real Eto dialog (_ask_reset's buttons and wording on screen); here STATE[\"on_reset_question\"] "
            "answers it.", c3a)

    facts = g.current_facts(doc)
    lot = g._find(doc, facts.get("lot_id") or "")
    kept = g.RhinoTable(doc).massing()

    def c3b():
        ok = sorted(kept) == sorted(new_house) and lot is not None and "109" in (lot.Attributes.Name or "")
        return ok, ("Keep my building: floors on %s after Draw %s the floors before (%d); the lot is \"%s\"." % (
            g.logic.MASSING, "are" if sorted(kept) == sorted(new_house) else "are NOT", len(kept),
            lot.Attributes.Name if lot else None)), {"kept": kept, "before": new_house}
    guarded("relookup-3-kept" + sfx, W % 3, "Keep my building: the floors kept, the lot is 109's", "rhino", "partial",
            RP_MODEL, c3b)
    RAWLOG["step3_undo" + sfx] = undo_summary(seen["journal"])

    # 4. the same address again: nothing changes
    before4 = objects(doc)
    strict4 = model(doc)
    seen = edit_site(g, doc, "109 Ithaca Rd, Ithaca, NY 14850", "109_ithaca_rd", extra=extra)
    RAWLOG["step4" + sfx] = {k: v for k, v in seen.items() if k != "objects"}

    def c4():
        now = objects(doc)
        ok = seen["asked"] == [] and now == before4
        return ok, ("109 again: asked %s; objects before %d, after %d, identical ids and layers: %s; stricter (names, "
                    "boxes, user strings, layers) identical: %s; undo records begun: %d." % (
                        seen["asked"] or "nothing", len(before4), len(now), now == before4, model(doc) == strict4,
                        len(undo_summary(seen["journal"])["begins"]))), seen["asked"]
    guarded("relookup-4-same-address" + sfx, W % 4, "The same address: no question and nothing in the model changes",
            "code", "covered", "None beyond the modelled object table.", c4)


# ================================================================================================================
# Track A: re_lookup_in_rhino.py as revised (uncommitted in /home/user/wt/re-lookup), step for step, claim for claim
# ================================================================================================================

def track_a():
    W = "re_lookup_in_rhino step %s"
    g = fresh_module()
    use_track(g, "")
    doc = new_doc()
    RAWLOG["track"] = TRACKS["a"][2]

    # 1. the sample
    g.gordium_check()
    facts = g.current_facts(doc)
    sample_lot, house = facts.get("lot_id"), g.RhinoTable(doc).massing()
    before = objects(doc)

    def c1():
        lot = g._find(doc, sample_lot)
        ok = lot is not None and len(house) >= 2
        return ok, ("GordiumStart on an empty feet document drew the sample lot \"%s\" on %s and a starting house of "
                    "%d floors on %s." % (lot.Attributes.Name if lot else None,
                                          doc.Layers[lot.Attributes.LayerIndex].FullPath if lot else None,
                                          len(house), g.logic.MASSING)), {"lot": sample_lot, "house": house}
    guarded("relookup-1-sample", W % 1, "1 the sample: its lot and a starting house", "rhino", "partial",
            RP_MODEL + " That the lot and floors are really drawn and framed in Rhino's views.", c1)

    # 2. a new address over what Gordium drew (96: a corner lot)
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")
    RAWLOG["step2"] = {k: v for k, v in seen.items() if k != "objects"}
    guarded("relookup-2-preview-untouched", W % 2, "2 Look up changed nothing in the model while the box was open",
            "code", "covered", "None beyond the modelled object table: every object's id and layer is compared.",
            lambda: (seen.get("objects") == before, "Objects before: %d; while the box was open after Look up: %d; "
                     "identical ids and layers: %s." % (len(before), len(seen.get("objects") or {}),
                                                         seen.get("objects") == before), None))
    guarded("relookup-2-preview-dashed", W % 2, "2 the looked-up lot was shown dashed while the box was open",
            "rhino", "partial", "That the conduit really draws STATE[\"lookup_guide\"] dashed (drawing).",
            lambda: (bool(seen.get("guide_shown")), "STATE[\"lookup_guide\"] was %s while the box was open." % (
                "set" if seen.get("guide_shown") else "NOT set"), None))
    after = objects(doc)
    facts = g.current_facts(doc)
    new_house = g.RhinoTable(doc).massing()
    ui_state = g._ui_state(doc)
    guarded("relookup-2-no-question", W % 2, "2 Draw asked nothing (all of it was Gordium's)", "code", "covered",
            "Nothing: the real dialog is never shown here (STATE[\"on_reset_question\"]).",
            lambda: (seen["asked"] == [], "Questions asked at Draw: %s." % (seen["asked"] or "none"), None))
    left = sorted(({sample_lot} | set(house)) & set(after))
    guarded("relookup-2-old-gone", W % 2, "2 the sample's lot and house are gone", "rhino", "partial", RP_MODEL,
            lambda: (not left, "Of the sample's lot and %d floors, still in the model: %s." % (
                len(house), left or "none"), left))
    lot = g._find(doc, facts.get("lot_id") or "")
    guarded("relookup-2-new-lot", W % 2, "2 96's lot is drawn on Site", "rhino", "partial", RP_MODEL,
            lambda: (lot is not None and "96" in (lot.Attributes.Name or "") and
                     doc.Layers[lot.Attributes.LayerIndex].FullPath == g.LAYERS["lot"],
                     "The saved lot: \"%s\" on %s." % (lot.Attributes.Name if lot else None,
                                                     doc.Layers[lot.Attributes.LayerIndex].FullPath if lot else None),
                     None))
    notes = (g.STATE.get("start") or {}).get("notes") or []
    guarded("relookup-2-no-house-corner", W % 2, "2 no starting house on 96, a corner lot (the architects' open "
            "question)", "code", "covered", "None: the checker's start answer is the real one.",
            lambda: (new_house == [] and any("corner lot" in n for n in notes),
                     "Floors on %s after Draw: %d; STATE[\"start\"][\"notes\"]: %s." % (
                         g.logic.MASSING, len(new_house), notes), notes))
    guarded("relookup-2-file-says", W % 2, "2 the file says what is drawn: 96, and no house of Gordium's", "code",
            "covered", "Rhino's document strings through a real save (not done here).",
            lambda: (g.logic.same_address(ui_state.get("drawn_address"), "96 Ithaca Rd")
                     and not ui_state.get("house_fingerprint"),
                     "The file's box state: drawn_address \"%s\", house_fingerprint %r." % (
                         ui_state.get("drawn_address"), ui_state.get("house_fingerprint")), None))
    u2 = undo_summary(seen["journal"])
    RAWLOG["step2_undo"] = u2

    def c2u():
        kinds = [e[0] for e in seen["journal"]]
        ok = (len(u2["begins"]) == 1 and len(u2["ends"]) == 1 and u2["ends"][0][1] == u2["begins"][0][1]
              and u2["ends"][0][2] is True and not u2["outside"] and u2["changes"] > 0)
        if ok:
            b, e = kinds.index("begin_undo"), kinds.index("end_undo")
            ok = all(b < i < e for i, k in enumerate(kinds) if k not in ("begin_undo", "end_undo"))
        return ok, ("BeginUndoRecord called %d time(s) %s, EndUndoRecord %d time(s) %s; %d model changes (%d added, "
                    "%d deleted, %d attribute edits), %d inside the open record, %d outside it." % (
                        len(u2["begins"]), [(x[1], x[2]) for x in u2["begins"]], len(u2["ends"]),
                        [(x[1], x[2]) for x in u2["ends"]], u2["changes"], u2["kinds"]["add"],
                        u2["kinds"]["delete"], u2["kinds"]["modify"], u2["inside"], len(u2["outside"]))), u2
    guarded("relookup-2-one-undo-record", W % 2, "2 (calls behind one Undo) the reset and the new lot are made inside "
            "one undo record: Begin/EndUndoRecord once each", "rhino", "partial",
            "Only the calls are recorded (fakerhino journal); that Rhino groups them as one Undo step is Rhino's.", c2u)
    record("relookup-2-undo", W % 2, "2 one Undo puts the sample back exactly", "rhino", "none", None,
           "Out of scope headless: Undo is not modelled (see relookup-2-one-undo-record for the calls).",
           "All of it: doc.Undo() in Rhino restores the sample's lot and house as before.")
    record("relookup-2-redo", W % 2, "2 Redo draws 96 again", "rhino", "none", None,
           "Out of scope headless: Redo is Rhino's.", "All of it: doc.Redo() in Rhino brings 96's lot back.")

    # 3. a new file: the sample's starting house edited, then 96 looked up: asked once; keep it
    g = fresh_module()
    use_track(g, "")
    doc = new_doc()
    g.gordium_check()
    house = g.RhinoTable(doc).massing()
    floor = g._find(doc, house[-1])
    moved = str(doc.Objects.Transform(floor, Rhino.Geometry.Transform.Translation(3, 0, 0), True))
    house = house[:-1] + [moved]
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", lambda fresh, keep: keep[1])
    RAWLOG["step3"] = {k: v for k, v in seen.items() if k != "objects"}
    asked = seen["asked"]
    guarded("relookup-3-asked-once", W % 3, "3 asked once, naming the edited house", "rhino", "partial",
            "The real Eto dialog (_ask_reset); here STATE[\"on_reset_question\"] answers it.",
            lambda: (len(asked) == 1 and asked[0][0].startswith("Start fresh for 96")
                     and asked[0][0].endswith("Your changes to the starting house will be removed.")
                     and bool(asked[0][2]), "In a new document, one sample floor moved 3 ft, Look up 96 and Draw: "
                     "asked %d time(s): %s" % (len(asked), asked), asked))
    facts = g.current_facts(doc)
    lot = g._find(doc, facts.get("lot_id") or "")
    kept = g.RhinoTable(doc).massing()
    guarded("relookup-3-kept", W % 3, "3 Keep my building: the floors kept, the lot is 96's", "rhino", "partial",
            RP_MODEL, lambda: (sorted(kept) == sorted(house) and lot is not None and "96" in (lot.Attributes.Name or ""),
                               "Floors after Draw %s the edited sample floors (%d); the lot is \"%s\"." % (
                                   "are" if sorted(kept) == sorted(house) else "are NOT", len(kept),
                                   lot.Attributes.Name if lot else None), {"kept": kept, "house": house}))
    RAWLOG["step3_undo"] = undo_summary(seen["journal"])

    # 4. the same address again: nothing changes
    before = objects(doc)
    strict = model(doc)
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")
    RAWLOG["step4"] = {k: v for k, v in seen.items() if k != "objects"}
    guarded("relookup-4-same-address", W % 4, "4 the same address: no question and nothing in the model changes",
            "code", "covered", "None beyond the modelled object table.",
            lambda: (seen["asked"] == [] and objects(doc) == before,
                     "96 again: asked %s; objects before %d, after %d, identical ids and layers: %s; stricter (names, "
                     "boxes, user strings, layers) identical: %s; undo records begun: %d." % (
                         seen["asked"] or "nothing", len(before), len(objects(doc)), objects(doc) == before,
                         model(doc) == strict, len(undo_summary(seen["journal"])["begins"])), seen["asked"]))


# ================================================================================================================
# 6. The guide case (added): the lookup has only the City's outline. Driven through the box's real loop (not the
# scripted auto_ok path, which ends the box when Draw does not close it); only the Eto dialog (gordium_ui.start_box)
# is replaced by a scripted architect that records what each showing of the box offers.
# ================================================================================================================

def guide_case():
    WG = "scenario 6 (added): guide only"
    g = fresh_module()
    use_track(g, "guide")
    doc = new_doc()
    g.gordium_check()                              # the sample, Gordium's lot and house
    before = model(doc)
    ui_before, facts_before = copy.deepcopy(g._ui_state(doc)), copy.deepcopy(g.current_facts(doc))
    strings_before = dict(doc.Strings.d)
    address = "96 Ithaca Rd, Ithaca, NY 14850"
    shown = []                                     # each showing of the box: what it offered and what was there

    def start_box(state, options, mode):
        n = len(shown)
        rows = g.logic.box_rows(state)
        lot_row = [r for r in rows if r["key"] == "lot"]
        shown.append({"n": n, "actions": {r["key"]: [a[0] for a in r["actions"]] for r in rows},
                      "lot_row": lot_row[0] if lot_row else None, "draw_label": state.get("_draw_label"),
                      "objects": model(doc), "strings": dict(doc.Strings.d),
                      "guide": g.STATE.get("lookup_guide") is not None, "lot_missing": state.get("lot_missing"),
                      "lookup": state.get("lookup"), "address": state.get("address")})
        if n == 0:                                 # the architect types the address and presses Look up
            state["address"], state["address_source"] = address, g.logic.ENTERED
            return "pick:lookup"
        if n == 1:                                 # "Looking up…": the box closes itself when the answer is in
            import time
            started = time.time()
            while g._lookup_poll() is None and time.time() - started < g.logic.LOOKUP_LIMIT_S + 5:
                time.sleep(0.2)
            return "pick:lookup_done"
        if n == 2:                                 # the answer shown (the guide dashed): tick the district, Draw
            state["district_confirmed"] = True
            return "draw"
        return None                                # after the reset: Cancel

    g.STATE["auto_ok"] = False
    g.STATE["lookup_fixture"] = "96_ithaca_rd"
    g.ui.start_box = start_box
    start = len(doc.journal)
    try:
        g.edit_facts()
    finally:
        g.STATE.pop("lookup_fixture", None)
        g.STATE["auto_ok"] = True
    journal = doc.journal[start:]
    after = model(doc)
    ui_after, facts_after = g._ui_state(doc), g.current_facts(doc)
    RAWLOG["guide"] = {"shown": [{k: v for k, v in s.items() if k not in ("objects", "strings")} for s in shown],
                       "journal": journal}
    reopened = shown[3] if len(shown) > 3 else None
    sample_ids = set(before["objects"])

    def g1():
        ok = reopened is not None and len(shown) == 4
        return ok, ("The box was shown %d times: Look up, Looking up…, the answer, then %s after Draw." % (
            len(shown), "shown AGAIN (still open)" if ok else "NOT shown again")), [s["actions"] for s in shown]
    guarded("relookup-6-box-stays-open", WG, "Draw with a guide-only answer: the box stays open after the reset",
            "code", "covered", "The real Eto dialog shown again (here a scripted stand-in for gordium_ui.start_box).",
            g1)

    def g2():
        acts = (reopened or {}).get("actions", {}).get("lot", [])
        before_draw = shown[2]["actions"].get("lot", []) if len(shown) > 2 else None
        ok = reopened is not None and "draw_lot" in acts and bool(reopened["guide"])
        return ok, ("After Draw, the Lot row offers %s (\"Draw my lot…\" is draw_lot), the guide %s on screen; before "
                    "Draw (the answer shown) it offered %s." % (acts, "still shown" if reopened and reopened["guide"]
                                                                   else "NOT shown", before_draw)), reopened and \
            reopened["lot_row"]
    guarded("relookup-6-draw-my-lot", WG, "Draw my lot… is offered after the reset, over the dashed guide", "rhino",
            "partial", "That the button is really there and the guide really drawn dashed (Eto, the conduit).", g2)

    def g3():
        if reopened is None:
            return False, "The box was not shown again after Draw.", None
        objs = reopened["objects"]["objects"]
        lots = [k for k, v in objs.items() if v[0] == g.LAYERS["lot"]]
        live = {k: v for k, v in objs.items() if not v[0].startswith(g.logic.HOLDING_LAYER)}
        strings_same = reopened["strings"] == strings_before
        ok = (not lots) and strings_same and not (set(live) - sample_ids) and \
            not g.logic.same_address(g._ui_state(doc).get("drawn_address"), address)
        return ok, ("With the box open after Draw: lots on %s: %d; objects not on the holding layer: %d (the "
                    "sample's lot and floors held on %s: %d); new objects: %d; document strings unchanged since "
                    "before the box: %s." % (g.LAYERS["lot"], len(lots), len(live), g.logic.HOLDING_LAYER,
                                             len([k for k, v in objs.items()
                                                  if v[0].startswith(g.logic.HOLDING_LAYER)]),
                                             len(set(objs) - sample_ids), strings_same)), \
            {"lots": lots, "held": [k for k, v in objs.items() if v[0].startswith(g.logic.HOLDING_LAYER)]}
    guarded("relookup-6-no-lot-saved", WG, "No lot is drawn or saved before Draw my lot… (nothing in the file's "
            "strings changes)", "code", "covered", RP_MODEL, g3)

    def g4():
        same_model = after == before
        diff = sorted(set(before["objects"]) ^ set(after["objects"])) + sorted(
            k for k in set(before["objects"]) & set(after["objects"]) if before["objects"][k] != after["objects"][k])
        dui = sorted(k for k in set(ui_before) | set(ui_after) if ui_before.get(k) != ui_after.get(k))
        dfa = sorted(k for k in set(facts_before) | set(facts_after) if facts_before.get(k) != facts_after.get(k))
        ok = same_model and not dui and not dfa and dict(doc.Strings.d) == strings_before
        u = undo_summary(journal)
        return ok, ("After Cancel: objects %d before, %d after, every layer, name, box and user strings identical: "
                    "%s (differing: %s); live layers identical: %s; _ui_state changed keys: %s; current_facts changed "
                    "keys: %s; all document strings identical: %s; undo records begun %d, ended %s." % (
                        len(before["objects"]), len(after["objects"]), before["objects"] == after["objects"],
                        diff or "none", before["layers"] == after["layers"], dui or "none", dfa or "none",
                        dict(doc.Strings.d) == strings_before, len(u["begins"]),
                        [(x[1], x[2]) for x in u["ends"]])), {"diff": diff, "ui": dui, "facts": dfa,
                                                              "layers": [before["layers"], after["layers"]]}
    guarded("relookup-6-cancel-restores", WG, "Cancel after the reset puts everything back (model and file)", "rhino",
            "partial", RP_MODEL + " Also that Rhino's undo record, begun at Draw and ended on Cancel, leaves no "
            "stray Undo step.", g4)


# ================================================================================================================
# 7. Review round 1 scenarios (added for ea7963b)
# ================================================================================================================

def _layer_path(doc, path):
    """A layer at a full path, made as an architect would make it (Layers.Add with its parent's id)."""
    parent = None
    for depth, name in enumerate(path.split("::")):
        full = "::".join(path.split("::")[:depth + 1])
        index = doc.Layers.FindByFullPath(full, -1)
        if index < 0:
            layer = Rhino.DocObjects.Layer()
            layer.Name = name
            if parent is not None:
                layer.ParentLayerId = doc.Layers[parent].Id
            index = doc.Layers.Add(layer)
        parent = index
    return parent


def scenario_a_surveyed_lot():
    """(a) A surveyed own lot, then 96 looked up and Start fresh."""
    WA = "scenario 7a (added): surveyed own lot, Start fresh"
    g = fresh_module()
    use_track(g, "")
    doc = new_doc()
    rg = Rhino.Geometry
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = _layer_path(doc, g.LAYERS["lot"])
    attrs.Name = "My lot (survey)"
    pts = [rg.Point3d(0, 0, 0), rg.Point3d(60, 0, 0), rg.Point3d(60, 120, 0), rg.Point3d(0, 120, 0)]
    own = str(doc.Objects.AddCurve(rg.PolylineCurve(pts + [pts[0]]), attrs))
    g.STATE.update(box_overrides={"lot_surveyed": True})     # the architect: "this lot is from my survey"
    try:
        g.gordium_check()                          # a lot, no facts: the box, confirmed, saved
    finally:
        g.STATE.pop("box_overrides", None)
    pre = {"lot_id": g.current_facts(doc).get("lot_id"), "lot_surveyed": g.current_facts(doc).get("lot_surveyed"),
           "lot_source": (g.fact_sources(doc).get("lot") or {})}
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", lambda fresh, keep: fresh[1])
    facts = g.current_facts(doc)
    lot_fact = g.fact_sources(doc).get("lot") or {}
    lot = g._find(doc, facts.get("lot_id") or "")
    area = g._feet_area(doc, g._area(lot.Geometry)) if lot is not None else None
    RAWLOG["7a"] = {"pre": pre, "asked": seen["asked"], "facts_lot": facts.get("lot_id"),
                    "lot_fact": lot_fact, "area": area}
    setup_ok = pre["lot_id"] == own and pre["lot_surveyed"] is True and \
        (pre["lot_source"].get("source") or "").startswith("your survey")

    guarded("relookup-7a-asked", WA, "The surveyed own lot is asked about once (\"your lot\"), Start fresh chosen",
            "rhino", "partial", "The real Eto dialog (here answered Start fresh by STATE[\"on_reset_question\"]).",
            lambda: (setup_ok and len(seen["asked"]) == 1 and "your lot" in seen["asked"][0][0].lower(),
                     "Before: lot %s, lot_surveyed %r, lot source %r. Asked %d time(s): %s" % (
                         "is the architect's own" if pre["lot_id"] == own else "is NOT the own lot",
                         pre["lot_surveyed"], pre["lot_source"].get("source"), len(seen["asked"]), seen["asked"]),
                     pre))
    guarded("relookup-7a-not-surveyed", WA, "After Start fresh the saved facts say lot_surveyed False", "code",
            "covered", "None beyond the stand-in document strings.",
            lambda: (facts.get("lot_surveyed") is False and lot is not None and facts.get("lot_id") != own,
                     "Saved facts: lot_surveyed %r; lot_id is %s (\"%s\")." % (
                         facts.get("lot_surveyed"), "the new lot" if facts.get("lot_id") != own else "STILL the own lot",
                         lot.Attributes.Name if lot else None), None))
    guarded("relookup-7a-lot-source", WA, "fact_sources(doc)[\"lot\"] is the new lot's area, from the tax map", "code",
            "covered", "Rhino's AreaMassProperties for the area (here the shoelace formula on the polyline).",
            lambda: (lot is not None and lot_fact.get("value") == g.logic.lot_size(area) and
                     (lot_fact.get("source") or "").startswith("the tax map"),
                     "fact_sources(doc)[\"lot\"] = %r; the new lot's area %.1f sf -> %r." % (
                         lot_fact, area or 0.0, g.logic.lot_size(area)), lot_fact))


def scripted_box(g, doc, script, limit=8):
    """Edit site… through the box's real loop, the Eto dialog replaced by `script(n, state)` -> the action (None:
    Cancel). Returns each showing's record."""
    shown = []

    def start_box(state, options, mode):
        n = len(shown)
        shown.append({"n": n, "zone": state.get("zone"), "address": state.get("address"),
                      "district_confirmed": state.get("district_confirmed"), "draw_label": state.get("_draw_label"),
                      "objects": model(doc)})
        return script(n, state) if n < limit else None

    g.STATE["auto_ok"] = False
    g.ui.start_box = start_box
    try:
        g.edit_facts()
    finally:
        g.STATE["auto_ok"] = True
    return shown


def wait_lookup(g):
    import time
    started = time.time()
    while g._lookup_poll() is None and time.time() - started < g.logic.LOOKUP_LIMIT_S + 5:
        time.sleep(0.2)


def scenario_b_retyped():
    """(b) 96 looked up, then the drawn address 106 retyped before Draw."""
    WB = "scenario 7b (added): 96 looked up, 106 retyped before Draw"
    g = fresh_module()
    use_track(g, "r2a")       # the City zoning stand-in says R-2a for 96, so a district put back is visible
    doc = new_doc()
    g.gordium_check()                              # the sample (R-1b)
    before = model(doc)
    facts0, ui0 = copy.deepcopy(g.current_facts(doc)), copy.deepcopy(g._ui_state(doc))
    asked = []
    g.STATE["on_reset_question"] = lambda q, f, k: asked.append(q)
    g.STATE["lookup_fixture"] = "96_ithaca_rd"
    start = len(doc.journal)

    def script(n, state):
        if n == 0:
            state["address"], state["address_source"] = "96 Ithaca Rd, Ithaca, NY 14850", g.logic.ENTERED
            return "pick:lookup"
        if n == 1:
            wait_lookup(g)
            return "pick:lookup_done"
        if n == 2:                                 # the preview shown: the drawn address typed back, Draw
            state["address"], state["address_source"] = "106 Ithaca Rd, Ithaca, NY 14850", g.logic.ENTERED
            state["district_confirmed"] = True
            return "draw"
        state["district_confirmed"] = True         # shown again (the district to tick again): ticked, Draw
        return "draw"
    try:
        shown = scripted_box(g, doc, script)
    finally:
        for k in ("on_reset_question", "lookup_fixture"):
            g.STATE.pop(k, None)
    journal = doc.journal[start:]
    after, facts1, ui1 = model(doc), g.current_facts(doc), g._ui_state(doc)
    RAWLOG["7b"] = {"shown": [{k: v for k, v in s.items() if k != "objects"} for s in shown], "asked": asked,
                    "journal": journal, "zone_before": facts0.get("zone"), "zone_after": facts1.get("zone")}
    preview_zone = shown[2]["zone"] if len(shown) > 2 else None

    guarded("relookup-7b-preview-district", WB, "(setup) the preview of 96 showed a different district (R-2a stand-in)",
            "code", "covered", "None.",
            lambda: (len(shown) > 2 and preview_zone != facts0.get("zone"),
                     "The sample's district %r; the box after Look up of 96 showed %r." % (facts0.get("zone"),
                                                                                           preview_zone), None))
    guarded("relookup-7b-nothing-redrawn", WB, "Retyped to the drawn 106 before Draw: nothing is redrawn, the sample "
            "stays", "rhino", "partial", RP_MODEL,
            lambda: (after == before and not asked and not undo_summary(journal)["begins"] and
                     facts1.get("lot_id") == facts0.get("lot_id") and
                     g.logic.same_address(ui1.get("drawn_address"), "106 Ithaca Rd"),
                     "Box shown %d times; objects before %d, after %d, all identical (layer, name, box, user strings): "
                     "%s; questions asked: %s; undo records begun: %d; lot_id unchanged: %s; drawn_address %r." % (
                         len(shown), len(before["objects"]), len(after["objects"]), after == before, asked or "none",
                         len(undo_summary(journal)["begins"]), facts1.get("lot_id") == facts0.get("lot_id"),
                         ui1.get("drawn_address")), None))
    guarded("relookup-7b-district-back", WB, "The district is back to the sample's", "code", "covered", "None.",
            lambda: (facts1.get("zone") == facts0.get("zone") and len(shown) > 3 and
                     shown[3]["zone"] == facts0.get("zone"),
                     "Saved district %r (sample's %r); the box shown after Draw said %r (showings: %s)." % (
                         facts1.get("zone"), facts0.get("zone"), shown[3]["zone"] if len(shown) > 3 else None,
                         [(s["n"], s["zone"], s["address"]) for s in shown]), None))


def scenario_c_garage():
    """(c) A garage on Building::Garage, then 96 looked up."""
    WC = "scenario 7c (added): a garage on Building::Garage"
    g = fresh_module()
    use_track(g, "")
    doc = new_doc()
    g.gordium_check()                              # the sample, lot and house as Gordium drew them
    lot = g._find(doc, g.current_facts(doc).get("lot_id"))
    c = lot.Geometry.GetBoundingBox(True)
    rg = Rhino.Geometry
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = _layer_path(doc, g.LAYERS["building"] + "::Garage")
    attrs.Name = "Garage"
    garage = str(doc.Objects.AddBrep(rg.Brep.CreateFromBox(rg.BoundingBox(c.Min.X + 2, c.Min.Y + 2, 0, c.Min.X + 14,
                                                                          c.Min.Y + 22, 10)), attrs))
    before = model(doc)
    seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")      # answered Cancel (None)
    RAWLOG["7c"] = {"asked": seen["asked"], "garage": garage}
    asked = seen["asked"]
    guarded("relookup-7c-asked", WC, "Asked once, naming \"the buildings you drew\" (Keep my building offered)", "rhino",
            "partial", "The real Eto dialog; and that a real Rhino solid on Building::Garage is listed by _buildings.",
            lambda: (len(asked) == 1 and "the buildings you drew" in asked[0][0].lower() and bool(asked[0][2]),
                     "A 12 x 20 x 10 ft solid on %s, then Look up 96 and Draw: asked %d time(s): %s" % (
                         g.LAYERS["building"] + "::Garage", len(asked), asked), asked))
    guarded("relookup-7c-cancel", WC, "Cancel at that question: the garage and everything else as before", "rhino",
            "partial", RP_MODEL, lambda: (model(doc) == before and g._find(doc, garage) is not None,
                                         "After Cancel: model identical %s; garage present %s." % (
                                             model(doc) == before, g._find(doc, garage) is not None), None))


def _block(g, doc, placed_on, name):
    """A block whose definition holds one 12 x 20 x 10 ft solid on Building, placed on `placed_on`, on the lot."""
    rg = Rhino.Geometry
    lot = g._find(doc, g.current_facts(doc).get("lot_id"))
    c = lot.Geometry.GetBoundingBox(True)
    solid_attrs = Rhino.DocObjects.ObjectAttributes()
    solid_attrs.LayerIndex = _layer_path(doc, g.LAYERS["building"])
    index = doc.InstanceDefinitions.Add(name, "", rg.Point3d(0, 0, 0),
                                        [rg.Brep.CreateFromBox(rg.BoundingBox(0, 0, 0, 12, 20, 10))], [solid_attrs])
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = _layer_path(doc, placed_on)
    attrs.Name = name
    return str(doc.Objects.AddInstanceObject(index, rg.Transform.Translation(c.Min.X + 2, c.Min.Y + 2, 0), attrs))


def scenario_d_block():
    """(d) A block on Building, and a block holding a Building solid placed on Site; then 96, Start fresh."""
    for key, placed_on, words in (("d1", "Building", "a block placed on Building"),
                                  ("d2", "Site", "a block holding a Building solid, placed on Site")):
        WD = "scenario 7%s (added): %s" % (key, words)
        g = fresh_module()
        use_track(g, "")
        doc = new_doc()
        g.gordium_check()                          # the sample, lot and house as Gordium drew them
        block = _block(g, doc, g.LAYERS["building"] if placed_on == "Building" else g.LAYERS["lot"], "Garage " + key)
        o = g._find(doc, block)
        seen_by_checker = [str(x.Id) for x in g._buildings(doc)] + list(g._sorted_objects(doc)[2])
        listed = g.RhinoTable(doc).buildings()
        seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", lambda fresh, keep: fresh[1])
        asked = seen["asked"]
        RAWLOG["7" + key] = {"asked": asked, "listed": listed, "checker": seen_by_checker,
                             "kind": type(o.Geometry).__name__ if o else None}
        guarded("relookup-7%s-asked" % key, WD, "Asked once, naming \"the buildings you drew\"", "rhino", "partial",
                "A real Rhino block (InstanceObject, InstanceDefinition.GetObjects, the definition objects' layers) "
                "is MODELLED by fakerhino.py.",
                lambda: (len(asked) == 1 and "the buildings you drew" in asked[0][0].lower(),
                         "%s (%s, %s); RhinoTable.buildings() listed it: %s; then Look up 96 and Draw: asked %d "
                         "time(s): %s" % (words, type(o.Geometry).__name__ if o else None,
                                          isinstance(o, Rhino.DocObjects.InstanceObject), block in listed,
                                          len(asked), asked), asked))
        guarded("relookup-7%s-cleared" % key, WD, "On Start fresh the block is cleared", "rhino", "partial",
                RP_MODEL + " Deleting a real block placement in Rhino.",
                lambda: (g._find(doc, block) is None and not any(
                    isinstance(x, Rhino.DocObjects.InstanceObject) for x in doc.Objects),
                    "After Start fresh: the block %s in the model; block placements left: %d; lot now \"%s\"." % (
                        "is NOT" if g._find(doc, block) is None else "IS STILL",
                        sum(isinstance(x, Rhino.DocObjects.InstanceObject) for x in doc.Objects),
                        (g._find(doc, g.current_facts(doc).get("lot_id") or "") or
                         types_ns(Attributes=types_ns(Name=None))).Attributes.Name), None))


def types_ns(**k):
    import types
    return types.SimpleNamespace(**k)


def scenario_e_use_retyped():
    """(e) 96 looked up (R-2a stand-in), Use changed, 106 retyped, Draw: the box again; tick, Draw."""
    WE = "scenario 7e (added): Use changed, 106 retyped, Draw"
    g = fresh_module()
    use_track(g, "r2a")
    doc = new_doc()
    g.gordium_check()                              # the sample (R-1b, one-family detached)
    facts0 = copy.deepcopy(g.current_facts(doc))
    zone_fact0 = copy.deepcopy(g.fact_sources(doc).get("zone"))
    new_use = "two_family"
    g.STATE["lookup_fixture"] = "96_ithaca_rd"
    asked = []
    g.STATE["on_reset_question"] = lambda q, f, k: asked.append(q)

    def script(n, state):
        if n == 0:
            state["address"], state["address_source"] = "96 Ithaca Rd, Ithaca, NY 14850", g.logic.ENTERED
            return "pick:lookup"
        if n == 1:
            wait_lookup(g)
            return "pick:lookup_done"
        if n == 2:                                 # Use changed (as the box's keep() records it), 106 typed back
            state["use"], state["use_source"] = new_use, g.logic.ENTERED
            state["address"], state["address_source"] = "106 Ithaca Rd, Ithaca, NY 14850", g.logic.ENTERED
            state["district_confirmed"] = True
            return "draw"
        state["district_confirmed"] = True         # the box again: ticked, Draw
        return "draw"
    try:
        shown = scripted_box(g, doc, script)
    finally:
        for k in ("on_reset_question", "lookup_fixture"):
            g.STATE.pop(k, None)
    facts1, sources = g.current_facts(doc), g.fact_sources(doc)
    RAWLOG["7e"] = {"shown": [{k: v for k, v in s.items() if k != "objects"} for s in shown], "asked": asked,
                    "use_fact": sources.get("use"), "zone_fact": sources.get("zone")}
    rule_tick = g.logic.district_confirmed("check", zone_fact0, facts0.get("zone"))   # the box's own tick for it
    guarded("relookup-7e-box-again", WE, "Draw after the retype: the box comes back, its tick the box's own (no "
            "session tick carried)", "code", "covered",
            "The real Eto dialog shown again (here the scripted stand-in for gordium_ui.start_box).",
            lambda: (len(shown) == 4 and shown[2]["zone"] != facts0.get("zone") and
                     shown[3]["zone"] == facts0.get("zone") and shown[3]["district_confirmed"] == rule_tick,
                     "Showings (n, district, address, ticked): %s. The 4th is the box again after the first Draw, "
                     "district %r ticked=%r; the box's own rule (rhino_logic.district_confirmed: a district confirmed "
                     "at an earlier Draw and unchanged starts ticked; the sample's R-1b was, source %r) gives %r." % (
                         [(s_["n"], s_["zone"], s_["address"], s_["district_confirmed"]) for s_ in shown],
                         shown[3]["zone"] if len(shown) > 3 else None,
                         shown[3]["district_confirmed"] if len(shown) > 3 else None,
                         (zone_fact0 or {}).get("source"), rule_tick), None))
    guarded("relookup-7e-use-entered", WE, "The saved use fact's source is \"entered by you\"", "code", "covered",
            "None.", lambda: (facts1.get("use") == new_use and (sources.get("use") or {}).get("source") ==
                              g.logic.ENTERED,
                              "Saved use %r; fact_sources(doc)[\"use\"] = %r." % (facts1.get("use"), sources.get("use")),
                              None))
    guarded("relookup-7e-district", WE, "The district is R-1b", "code", "covered", "None.",
            lambda: (facts1.get("zone") == "R-1b" and (sources.get("zone") or {}).get("value") == "R-1b",
                     "Saved district %r; fact_sources(doc)[\"zone\"] = %r; questions asked: %s." % (
                         facts1.get("zone"), sources.get("zone"), asked or "none"), None))


def steps_1_to_4_track_b():
    steps_1_to_4("b")


# ================================================================================================================
# 5. An edited starting house, Cancel at the question: the model and the file's box strings as before
# ================================================================================================================

def step_5():
    g = fresh_module()
    use_track(g, TRACKS["b"][1])                   # a house is needed to edit: the one-street answers (track B)
    extra = None
    doc = new_doc()
    g.gordium_check()                              # the sample
    edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd", extra=extra)   # Gordium's lot and house
    house = g.RhinoTable(doc).massing()
    floor = g._find(doc, house[-1])
    doc.Objects.Transform(floor, Rhino.Geometry.Transform.Translation(3, 0, 0), True)     # edited by the architect
    before = model(doc)
    ui_before, facts_before = copy.deepcopy(g._ui_state(doc)), copy.deepcopy(g.current_facts(doc))
    strings_before = dict(doc.Strings.d)
    seen = edit_site(g, doc, "109 Ithaca Rd, Ithaca, NY 14850", "109_ithaca_rd", answer=None,   # Cancel: None
                     extra=extra)
    after = model(doc)
    ui_after, facts_after = g._ui_state(doc), g.current_facts(doc)
    strings_after = dict(doc.Strings.d)
    changed_strings = sorted(str(k) for k in set(strings_before) | set(strings_after)
                             if strings_before.get(k) != strings_after.get(k))
    RAWLOG["step5"] = {"asked": seen["asked"], "journal": seen["journal"], "changed_strings": changed_strings,
                       "ui_before": ui_before, "ui_after": ui_after}

    def c5a():
        ok = len(seen["asked"]) == 1 and seen["asked"][0][0].startswith("Start fresh for 109")
        return ok, "Asked %d time(s): %s; answered Cancel (None)." % (len(seen["asked"]), seen["asked"]), seen["asked"]
    guarded("relookup-5-asked", "scenario 5 (added)", "Edited house, new address: the question is asked once",
            "rhino", "partial", "The real Eto dialog's Cancel button (here the answer is scripted as None).", c5a)

    def c5b():
        ok = after == before
        diff = sorted(set(before["objects"]) ^ set(after["objects"])) + sorted(
            k for k in set(before["objects"]) & set(after["objects"]) if before["objects"][k] != after["objects"][k])
        return ok, ("After Cancel at the question: %d objects before, %d after; every object's layer, name, box and "
                    "user strings identical: %s (differing: %s); live layers identical: %s; undo records begun: %d; "
                    "model changes recorded during the box: %d." % (
                        len(before["objects"]), len(after["objects"]), before["objects"] == after["objects"],
                        diff or "none", before["layers"] == after["layers"],
                        len(undo_summary(seen["journal"])["begins"]), undo_summary(seen["journal"])["changes"])), \
            {"layers_before": before["layers"], "layers_after": after["layers"], "diff": diff}
    guarded("relookup-5-model-unchanged", "scenario 5 (added)", "Cancel at the question: the model is exactly as "
            "before", "rhino", "partial", RP_MODEL, c5b)

    def c5c():
        ok = ui_after == ui_before and facts_after == facts_before
        dui = sorted(k for k in set(ui_before) | set(ui_after) if ui_before.get(k) != ui_after.get(k))
        dfa = sorted(k for k in set(facts_before) | set(facts_after) if facts_before.get(k) != facts_after.get(k))
        return ok, ("_ui_state(doc) changed keys: %s; current_facts(doc) changed keys: %s; document strings that "
                    "changed at all (for information): %s." % (dui or "none", dfa or "none",
                                                              changed_strings or "none")), \
            {"ui": dui, "facts": dfa, "strings": changed_strings}
    guarded("relookup-5-file-unchanged", "scenario 5 (added)", "Cancel at the question: nothing new saved in the "
            "file's strings for the box (_ui_state and current_facts as before)", "code", "covered",
            "Rhino's document strings through a real save (not done here).", c5c)


def main():
    print("code under test:", WT, flush=True)
    for part in (track_a, steps_1_to_4_track_b, step_5, guide_case, scenario_a_surveyed_lot,
                 scenario_b_retyped, scenario_c_garage, scenario_d_block, scenario_e_use_retyped):
        try:
            part()
        except Exception:
            RAWLOG[getattr(part, "__name__", "part") + "_crashed"] = traceback.format_exc()
            print(traceback.format_exc(), flush=True)
            record(part.__name__ + "-setup", part.__name__, "The headless run of this part could not finish", "code",
                   "none", False, "Crashed before every claim was checked: " +
                   traceback.format_exc().strip().splitlines()[-1][:200], "All of it.", None)
    os.environ["GORDIUM_SHIM"] = ""
    json.dump(RESULTS, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(RAWLOG, open(RAW, "w", encoding="utf-8"), indent=1, default=str, ensure_ascii=False)
    print("code under test:", WT)
    print("passed:", sum(1 for r in RESULTS if r["offline_ok"] is True),
          "failed:", sum(1 for r in RESULTS if r["offline_ok"] is False),
          "out of scope:", sum(1 for r in RESULTS if r["offline_ok"] is None))


if __name__ == "__main__":
    main()
