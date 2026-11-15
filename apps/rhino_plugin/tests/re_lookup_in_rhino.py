#! python3
"""Re-lookup on a drawn site (Ben, 2026-10-21), in Rhino 8, each claim asserted (RHINO_QUEUE 5). Run in Rhino, not
in CI; the logic is tested in CI (packages/design_checker/tests/test_re_lookup.py). A fresh feet document:
1. GordiumStart on the empty file: the sample (106 Ithaca Rd), its lot and starting house.
2. Edit site…, "96 Ithaca Rd" typed, Look up (recorded answers): while the box is open nothing in the model has
   changed, the looked-up lot is shown dashed; Draw: the sample's lot and house gone, 96's lot drawn, no question
   asked (all of it was Gordium's). 96 is a corner lot, so no starting house is drawn on it (by design: which yards
   are front is the architects' open question). Rhino's Undo puts the sample back exactly; Redo draws 96's lot
   again; a second Undo, the sample again, a second Redo, 96. After each: the file's saved facts, box choices and
   sources are those of the model on screen, nothing of the other model is left drawn (no dashed lookup outline, no
   lot outline or marks of the last check), and the model is checked again (live mode).
3. A new file: the sample's starting house edited (one floor moved), Edit site…, Look up 96: asked once, "Start
   fresh for 96 …? Your changes to the starting house will be removed.", the Keep answer "Keep my building and
   check it on 96 …'s lot"; Keep my building: the floors kept, the lot is 96's.
4. Edit site…, Look up 96 again: no question, nothing in the model changes. Then Edit site… with another address
   typed and not looked up (Ben, 2026-10-25): Draw does nothing and says "Press Look up to find 109 Ithaca Rd, …
   first."; the model and the file are as they were (never a label saved on 96's lot). Edit site… again on 96's own
   address: Draw goes through and checks the model as it is (typing an address and then the original back in one
   box is proven in CI: test_re_lookup.py).
5. A new file: the sample's lot made the architect's survey (as Use my survey… leaves it) and its starting house
   edited; Look up 96: a new address is a new site (Ben, 2026-10-25), so even Keep my building replaces their lot,
   and both the question ("Your surveyed lot will be replaced by 96 …'s lot.") and the Keep answer ("… (your
   surveyed lot will be replaced)") say so. Keep: the floors kept, the surveyed lot gone, 96's tax-map lot drawn
   (not marked as a survey). Undo puts the surveyed lot and the edited house back exactly; Redo, 96's lot and the
   kept house again; after each, the file's saved strings follow, nothing stale is drawn, and a re-check is owed.
Before each re-lookup a Rhino command (_Line) runs, as there always is in Rhino between a start and a later Edit
site…: records one script writes outside any command one after another are all taken back by one _Undo (Lane C's
control at 59d7184), so without it the sample's own record went with the re-lookup's. Step 2 also claims the
re-lookup's Draw is one undo record and that one Undo takes back exactly that record (by serial).
It runs as the architect works: outside any command (started from the Script Editor or RunPythonScript, it waits
for that command to end, then runs at the next idle, as the panel's Edit site… button runs), Undo and Redo as
Rhino's own _Undo and _Redo commands. Rhino's undo events during the run and each Draw's undo record (its serial,
whether a command was running) are written to out.json ("undo_events", "undo_records") for the root cause if a
claim fails. Writes <temp>/gordium_re_lookup/out.json ("done": true at the end) and Top captures; closes its
document."""
import json
import os
import time
import sys
import tempfile
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402
from test_docs_in_rhino import look_up_106  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "packages", "design_checker", "design_checker"))
import rhino_logic as logic  # noqa: E402  (its guard: no callback may raise into Rhino)

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


REDRAWN = "Gordium::Envelope"   # the Osnap curves every check redraws with Undo recording off (osnap_in_rhino, 4)


def objects(doc):
    """Every object in the model: id -> its layer's full path; not the curves on REDRAWN, which show the latest check,
    never an undo step (as autocomplete_in_rhino's objects)."""
    out = {}
    for o in doc.Objects:
        path = doc.Layers[o.Attributes.LayerIndex].FullPath
        if path != REDRAWN and not path.startswith(REDRAWN + "::"):
            out[str(o.Id)] = path
    return out


def undo_event(sender, e):
    """Rhino's undo events, in order (what began, ended, was undone, redone or purged)."""
    log["undo_events"].append(dict({k: bool(getattr(e, k, False)) for k in (
        "IsBeginRecording", "IsEndRecording", "IsBeginUndo", "IsEndUndo", "IsBeginRedo", "IsEndRedo",
        "IsPurgeRecord")}, serial=int(getattr(e, "UndoSerialNumber", 0) or 0), at=log.get("at")))


def watch_draws(g):
    """Each Draw's undo record as the plugin began it: its serial (0: Rhino said a command was already recording)
    and whether a command was running."""
    begin = g._begin_undo

    def recorded(doc_, words):
        begin(doc_, words)
        log["undo_records"].append({"words": words, "serial": (g.STATE.get("undo") or (None, None))[1],
                                    "in_command": bool(Rhino.Commands.Command.InCommand()), "at": log.get("at")})
    g._begin_undo = recorded


def rhino(command, at):
    """Rhino's own command, as the architect types it (Undo, Redo): whether it ran. Undo and Redo run in the document
    (RhinoApp.ExecuteCommand, as Cmd+Z runs _Undo): RunScript("_Undo") does nothing while no Rhino window is on
    screen, and RhinoDoc.Undo() drops the step it undid (side_yards_in_rhino, 2026-11-12)."""
    log["at"] = at
    log["command_at"] = time.time()
    if command in ("Undo", "Redo"):
        ran = Rhino.RhinoApp.ExecuteCommand(Rhino.RhinoDoc.ActiveDoc, "_" + command) == Rhino.Commands.Result.Success
    else:
        ran = bool(Rhino.RhinoApp.RunScript("_" + command, False))
    log.setdefault("commands", []).append([at, command, ran])
    return ran


def separate(doc, at):
    """A Rhino command between two Gordium steps (_Line), as there always is in Rhino: whether it ran and drew
    exactly one line (else the Undo claims after it could be the harness's again)."""
    known = {o.Id for o in doc.Objects}
    ran = rhino("Line 0,-300,0 10,-300,0", at)
    made = [o.Id for o in doc.Objects if o.Id not in known]
    claim(at + ": the command between ran", ran and len(made) == 1, {"ran": ran, "made": len(made)})


def records(since, kind):
    """The undo serials Rhino reported since event `since`: ended ("IsEndRecording") or taken back ("IsBeginUndo")."""
    return sorted({e["serial"] for e in log["undo_events"][since:] if e[kind]})


def saved(g, doc):
    """What the file says (the facts, the box's choices, the sources), as saved in its strings: an Undo must put it
    back with the model, or the re-check would measure the sample against 96's facts."""
    return {k: doc.Strings.GetValue(g.SECTION, k) for k in (g.ENTRY, g.UI_ENTRY, g.SOURCES_ENTRY)}


def differs(now, expected):
    """Each saved entry that differs: what it says now and what it should say."""
    return {k: {"now": v, "expected": expected.get(k)} for k, v in now.items() if v != expected.get(k)}


def recheck_owed(g, doc):
    """After Rhino's Undo or Redo, the model is checked again: a re-check is still owed at the next idle
    (rhino_logic.should_recheck, as live mode's _idle asks it), or one has finished since the command began. Never
    left cleared with no check to come (review round 2, P1: an Undo right after a check)."""
    last = g.logic.last_check_at(g.STATE.get("checked_at"), doc.RuntimeSerialNumber)
    owed = g.logic.should_recheck(g.STATE.get("dirty"), time.time() + 1, False, False, g.IDLE_SECONDS, last)
    done = last is not None and last >= log["command_at"]
    return (owed or done) and bool(g.STATE.get("live")), {"dirty": g.STATE.get("dirty"), "last_check": last,
                                                         "live": g.STATE.get("live"), "owed": owed, "done": done}


def nothing_stale(g):
    """Nothing of another model left drawn: no dashed lookup outline, no editing outline, no lot outline or marks of
    the last check (cleared by the plugin when Rhino undoes or redoes, until the next check)."""
    o = g.STATE.get("overlay")
    shown = {"lookup_guide": g.STATE.get("lookup_guide") is not None,
             "editing_outline": o is not None and o.confirm is not None,
             "check_lot_outline": o is not None and o.lot_outline is not None,
             "check_marks": o is not None and bool(o.red or o.encroach or o.yard_dims or o.plan_lines)}
    return not any(shown.values()), shown


def type_only(g, doc, address):
    """Edit site… with `address` typed and Draw pressed, no Look up (scripted): (what the plugin said, whether Draw
    went through: the plugin's _drawn, the Draw's own save, ran)."""
    start = len(g.STATE.get("said") or [])
    ran = []
    drawn = g._drawn

    def recorded(*a, **k):
        ran.append(True)
        return drawn(*a, **k)
    g._drawn = recorded
    g.STATE.update(box_picks=[], box_overrides={"address": address}, lookup_fixture="96_ithaca_rd")   # never live
    try:
        g.edit_facts()
    finally:
        g._drawn = drawn
        for k in ("box_picks", "box_overrides", "lookup_fixture"):
            g.STATE.pop(k, None)
    return (g.STATE.get("said") or [])[start:], bool(ran)


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


def main():
    doc = None
    log.update(undo_events=[], undo_records=[])
    handler = System.EventHandler[Rhino.Commands.UndoRedoEventArgs](logic.guard(undo_event, "record an undo event"))
    Rhino.Commands.Command.UndoRedo += handler
    try:
        docs = TestDocs("relookup").__enter__()
        g = fresh_module()
        watch_draws(g)
        doc = docs.open("Large Objects - Feet")
        # 1. the sample
        look_up_106(g, g.gordium_check)                              # an empty file: GordiumStart, the sample drawn
        facts = g.current_facts(doc)
        sample_lot, house = facts.get("lot_id"), g.RhinoTable(doc).massing()
        claim("1 the sample: its lot and a starting house", g._find(doc, sample_lot) is not None and len(house) >= 2,
              {"lot": sample_lot, "house": house})
        capture(doc, "1_sample")
        # a command between the sample and the re-lookup, as there always is in Rhino: records written one after
        # another by one script outside any command are all taken back by one _Undo (Lane C's control at 59d7184),
        # which took the sample's own GordiumStart record back with the re-lookup's (19ed22f: 3 floors "missing")
        separate(doc, "1 a command between")
        before = objects(doc)
        said_before = saved(g, doc)
        marks = len(log["undo_events"])

        # 2. a new address over what Gordium drew
        seen = edit_site(g, doc, "96 Ithaca Rd, Ithaca, NY 14850", "96_ithaca_rd")
        log["step2"] = {k: v for k, v in seen.items() if k != "objects"}
        claim("2 Look up changed nothing in the model while the box was open", seen.get("objects") == before,
              {"before": len(before), "during": len(seen.get("objects") or {})})
        claim("2 the looked-up lot was shown dashed while the box was open", seen.get("guide_shown"), seen)
        after = objects(doc)
        said_after = saved(g, doc)
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
        draw_records = records(marks, "IsEndRecording")
        claim("2 the re-lookup's Draw is one undo record", len(draw_records) == 1, draw_records)
        marks = len(log["undo_events"])
        ran = rhino("Undo", "2 undo")
        undone = objects(doc)
        took = records(marks, "IsBeginUndo")
        claim("2 one Undo takes back exactly that record", took == draw_records, {"undone": took,
                                                                                  "draw": draw_records})
        claim("2 one Undo puts the sample back exactly", ran and undone == before,
              {"ran": ran, "missing": sorted(set(before) - set(undone)), "extra": sorted(set(undone) - set(before))})
        claim("2 after Undo the file says the sample again (facts, choices, sources)", saved(g, doc) == said_before,
              differs(saved(g, doc), said_before))
        clean, shown = nothing_stale(g)
        claim("2 after Undo nothing of 96 is left on screen", clean, shown)
        owed, why = recheck_owed(g, doc)
        claim("2 after Undo the sample is checked again (live mode)", owed, why)
        ran = rhino("Redo", "2 redo")
        redone = objects(doc)
        claim("2 Redo draws 96's lot again (and no house: a corner lot), the sample gone", ran and redone == after,
              {"ran": ran, "missing": sorted(set(after) - set(redone)), "extra": sorted(set(redone) - set(after))})
        capture(doc, "2_after_redo")
        claim("2 after Redo the file says 96 again (facts, choices, sources)", saved(g, doc) == said_after,
              differs(saved(g, doc), said_after))
        clean, shown = nothing_stale(g)
        claim("2 after Redo nothing of the sample is left on screen", clean, shown)
        owed, why = recheck_owed(g, doc)
        claim("2 after Redo 96 is checked again (live mode)", owed, why)
        ran = rhino("Undo", "2 undo again")
        again = objects(doc)
        claim("2 a second Undo puts the sample back again", ran and again == before,
              {"ran": ran, "missing": sorted(set(before) - set(again)), "extra": sorted(set(again) - set(before))})
        claim("2 after the second Undo the file says the sample again", saved(g, doc) == said_before,
              differs(saved(g, doc), said_before))
        clean, shown = nothing_stale(g)
        claim("2 after the second Undo nothing of 96 is left on screen", clean, shown)
        owed, why = recheck_owed(g, doc)
        claim("2 after the second Undo the sample is checked again (live mode)", owed, why)
        ran = rhino("Redo", "2 redo again")              # 96 drawn, as step 2 left it, before the file is closed
        again = objects(doc)
        claim("2 a second Redo draws 96's lot again", ran and again == after,
              {"ran": ran, "missing": sorted(set(after) - set(again)), "extra": sorted(set(again) - set(after))})
        claim("2 after the second Redo the file says 96 again", saved(g, doc) == said_after,
              differs(saved(g, doc), said_after))
        clean, shown = nothing_stale(g)
        claim("2 after the second Redo nothing of the sample is left on screen", clean, shown)
        owed, why = recheck_owed(g, doc)
        claim("2 after the second Redo 96 is checked again (live mode)", owed, why)

        # 3. a new file: the sample's starting house edited, then 96 looked up: asked once; keep it
        close(doc)
        g = fresh_module()
        watch_draws(g)
        doc = docs.open("Large Objects - Feet")
        look_up_106(g, g.gordium_check)
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
        # an address typed and not looked up: Draw does nothing and says why (Ben, 2026-10-25)
        before, said_before = objects(doc), saved(g, doc)
        typed = "109 Ithaca Rd, Ithaca, NY 14850"
        said, ran = type_only(g, doc, typed)
        claim("4 an address typed and not looked up: Draw says to look it up first, nothing changes",
              ("Press Look up to find " + typed + " first.") in said and not ran and objects(doc) == before and
              saved(g, doc) == said_before, {"said": said, "ran": ran,
                                             "strings": differs(saved(g, doc), said_before)})
        own = g.current_facts(doc).get("address")
        said, ran = type_only(g, doc, own)
        claim("4 the lot's own address (the box opened again on it): Draw goes through and checks it as it is",
              ran and not [t for t in said if "Look up" in t] and objects(doc) == before and
              g.logic.same_address(g.current_facts(doc).get("address"), own), {"said": said, "ran": ran, "own": own})

        # 5. a new file: the architect's surveyed lot and an edited house, then 96 looked up: Keep replaces the lot too
        close(doc)
        g = fresh_module()
        watch_draws(g)
        doc = docs.open("Large Objects - Feet")
        look_up_106(g, g.gordium_check)
        facts = g.current_facts(doc)
        survey_lot = facts.get("lot_id")
        facts["lot_surveyed"] = True                   # as Use my survey… leaves it (pick_survey): theirs, a survey
        g.save_facts(doc, facts)
        g._save_ui_state(doc, g.logic.settle(g._ui_state(doc), "lot"))
        house = g.RhinoTable(doc).massing()
        floor = g._find(doc, house[-1])
        moved = str(doc.Objects.Transform(floor, Rhino.Geometry.Transform.Translation(3, 0, 0), True))
        house = house[:-1] + [moved]
        separate(doc, "5 a command between")     # (as in step 1: the start's own record apart)
        before = objects(doc)
        said_before = saved(g, doc)              # after the survey and the edit: what Undo must give back
        marks = len(log["undo_events"])
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
        said_after = saved(g, doc)
        claim("5 Keep my building: the floors kept, the surveyed lot replaced by 96's tax-map lot",
              sorted(g.RhinoTable(doc).massing()) == sorted(house) and survey_lot not in after and lot is not None and
              "96" in (lot.Attributes.Name or "") and facts.get("lot_surveyed") is False,
              {"kept": g.RhinoTable(doc).massing(), "lot": lot.Attributes.Name if lot else None,
               "surveyed": facts.get("lot_surveyed")})
        capture(doc, "5_kept_on_96_survey_replaced")
        draw_records = records(marks, "IsEndRecording")
        claim("5 the re-lookup's Draw is one undo record", len(draw_records) == 1, draw_records)
        marks = len(log["undo_events"])
        ran = rhino("Undo", "5 undo")
        took = records(marks, "IsBeginUndo")
        claim("5 one Undo takes back exactly that record", took == draw_records, {"undone": took,
                                                                                  "draw": draw_records})
        undone = objects(doc)
        claim("5 one Undo puts the surveyed lot and the edited house back exactly", ran and undone == before,
              {"ran": ran, "missing": sorted(set(before) - set(undone)), "extra": sorted(set(undone) - set(before))})
        claim("5 after Undo the file says the surveyed lot again (facts, choices, sources)",
              saved(g, doc) == said_before, differs(saved(g, doc), said_before))
        clean, shown = nothing_stale(g)
        claim("5 after Undo nothing of 96 is left on screen", clean, shown)
        owed, why = recheck_owed(g, doc)
        claim("5 after Undo the surveyed lot is checked again (live mode)", owed, why)
        ran = rhino("Redo", "5 redo")
        redone = objects(doc)
        claim("5 Redo draws 96's lot again with the kept house, the surveyed lot gone", ran and redone == after,
              {"ran": ran, "missing": sorted(set(after) - set(redone)), "extra": sorted(set(redone) - set(after))})
        claim("5 after Redo the file says 96 again (facts, choices, sources)", saved(g, doc) == said_after,
              differs(saved(g, doc), said_after))
        clean, shown = nothing_stale(g)
        claim("5 after Redo nothing of the surveyed lot is left on screen", clean, shown)
        owed, why = recheck_owed(g, doc)
        claim("5 after Redo 96 is checked again (live mode)", owed, why)
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    except Exception:
        log["ok"] = False
        log["trace"] = traceback.format_exc()
        raise                               # a failed claim fails the run loudly (the standing rule)
    finally:
        Rhino.Commands.Command.UndoRedo -= handler
        try:
            if doc is not None:
                close(doc)
        except Exception:
            pass
        log["done"] = True
        json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)


def run_as_the_architect():
    """main() outside any command, as the panel's Edit site… runs: now if no command is running, else at the next
    idle once this one (RunPythonScript, the Script Editor's run) has ended. From the idle nothing may raise into
    Rhino (on the Mac that aborts it): a failure is in out.json ("ok": false, "trace") and on the command line."""
    if os.path.exists(S + "out.json"):          # never an earlier run's result read as this one's
        os.remove(S + "out.json")
    def guarded():
        try:
            main()
        except Exception:
            Rhino.RhinoApp.WriteLine("re_lookup_in_rhino FAILED: see " + S + "out.json")
        else:
            Rhino.RhinoApp.WriteLine("re_lookup_in_rhino: " + ("all claims pass" if log.get("ok") else "FAILED"))
    if not Rhino.Commands.Command.InCommand():
        main()
        return

    def once(sender, e):
        Rhino.RhinoApp.Idle -= idle
        guarded()
    idle = System.EventHandler(logic.guard(once, "run outside a command"))
    Rhino.RhinoApp.Idle += idle
    Rhino.RhinoApp.WriteLine("re_lookup_in_rhino: runs when this command ends (outside any command); wait for "
                             + S + "out.json to say \"done\": true")


run_as_the_architect()
