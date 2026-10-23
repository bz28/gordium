"""The Check button (Ben, 2026-10-21), with the plugin's own code and no Rhino: gordium_rhino.py and gordium_ui.py are
imported unchanged against the stand-ins in ../ (fakerhino, fake_eto); the checker answers in process. Rhino's edit
events are fired as Rhino fires them after an edit (the stand-in table does not fire them itself), and Rhino's idle
is called directly (time moved on by setting the edit's time in the past, as waiting would).

Run from a checkout of the branch:
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(ls -d packages/* | tr '\\n' ':') GORDIUM_WT=$PWD \\
    /home/user/venv/bin/python <this file>
Writes results_check_button.json beside itself."""
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from harness import fresh_module, new_doc  # noqa: E402

import fake_eto  # noqa: E402
import Rhino  # noqa: E402
import scriptcontext as sc  # noqa: E402

RESULTS = []


def record(rid, title, ok, evidence, rhino_part, needs="rhino", offline="partial"):
    RESULTS.append({"id": rid, "group": "check_button", "where": "check_button_in_rhino", "title": title,
                    "needs": needs, "offline": offline, "offline_ok": bool(ok), "evidence": evidence,
                    "rhino_part": rhino_part})
    print(("PASS " if ok else "FAIL ") + rid + ": " + title, flush=True)


def check(rid, title, rhino_part, fn, **k):
    try:
        ok, evidence = fn()
    except Exception as e:
        ok, evidence = False, "raised %s: %s | %s" % (type(e).__name__, e, traceback.format_exc()[-600:])
    record(rid, title, ok, evidence, rhino_part, **k)


def texts(x, out=None):
    """Every piece of text in a fake Eto layout (labels, buttons), in order."""
    out = [] if out is None else out
    if isinstance(x, (list, tuple)):
        for y in x:
            texts(y, out)
        return out
    t = x.__dict__.get("Text") if hasattr(x, "__dict__") else None
    if isinstance(t, str) and t:
        out.append(t)
    for attr in ("rows", "Items"):
        for y in (x.__dict__.get(attr) if hasattr(x, "__dict__") else None) or []:
            texts(getattr(y, "Control", y), out)
    return out


def edited(g, doc):
    """The architect moves the top floor 3 ft (Rhino replaces the object and fires its edit events)."""
    house = g.RhinoTable(doc).massing() if hasattr(g.RhinoTable(doc), "massing") else \
        [str(o.Id) for o in doc.Objects if doc.Layers[o.Attributes.LayerIndex].FullPath == g.logic.MASSING]
    o = g._find(doc, house[-1])
    doc.Objects.Transform(o, Rhino.Geometry.Transform.Translation(3, 0, 0), True)
    # Rhino then raises ReplaceRhinoObject, whose handler (attached by live(True): STATE["hooks"]) is _changed; the
    # stand-in's .NET delegate wrapper does not call through, so the handler is called as Rhino's event would
    assert g.STATE.get("hooks"), "live mode's edit handlers are not attached"
    g._changed(None, None)


def idle_after_wait(g):
    """Rhino's idle, 5 s after the edit: the edit and the last check both moved 5 s into the past, in order (the
    check before the edit)."""
    for serial in list((g.STATE.get("checked_at") or {})):
        g.STATE["checked_at"][serial] -= 10.0
    if g.STATE.get("last"):
        g.STATE["last"]["at"] = g.STATE["last"].get("at", 0) - 10.0
    if g.STATE.get("dirty"):
        g.STATE["dirty"] -= 5.0
    g._idle(None, None)


def checked_at(g, doc):
    return (g.STATE.get("checked_at") or {}).get(doc.RuntimeSerialNumber)


def main():
    RP_PANEL = "The real Eto panel in Rhino 8: the button and tick on screen, a click, the greyed rows' look."
    g = fresh_module()
    doc = new_doc()
    host = fake_eto.Widget()
    g.register_dock = lambda: "dock-id"
    sc.sticky["gordium_dock_hosts"] = {doc.RuntimeSerialNumber: host}
    g.STATE.update(box_picks=[], on_confirm=lambda *a: None)
    g.gordium_check()                            # an empty file: GordiumStart, the sample drawn and checked
    parts = g.STATE.get("panel_parts") or {}
    buttons = parts.get("box_buttons") or []
    ticks = [it.Control for row in parts.get("greyed") or [] for it in getattr(row, "Items", None) or []
             if isinstance(getattr(it, "Control", None), fake_eto.CheckBox)]
    auto = next((t for t in ticks if t.Text == g.logic.AUTO_CHECK_LABEL), None)
    check("check-1", "The panel has a Check button, first beside Edit site…", RP_PANEL,
          lambda: ([b.Text for b in buttons][:2] == ["Check", "Edit site…"], "Header buttons: %s." % [b.Text for b in buttons]))
    check("check-2", "The tick 'Check after every edit' is there and off", RP_PANEL,
          lambda: (auto is not None and auto.Checked is False,
                   "Ticks: %s; Check after every edit Checked=%s." % ([t.Text for t in ticks], auto and auto.Checked)))

    first = checked_at(g, doc)
    runs = []
    real_run = g.run_check

    def counted(*a, **k):                        # every check the plugin runs, counted (it runs as written)
        runs.append(a)
        return real_run(*a, **k)
    g.run_check = counted
    redraws = []
    real_redraw = g._redraw
    g._redraw = lambda: (redraws.append(1), real_redraw())[1]
    edited(g, doc)
    idle_after_wait(g)
    head = texts(parts["header"].rows)
    rows = g._status_rows(g.overlay(), True)
    check("check-3", "After an edit nothing checks by itself", "Rhino's own idle and edit events (fired here as "
          "Rhino fires them).", lambda: (runs == [] and g.STATE.get("dirty"),
                                          "Checks run after the edit and an idle 5 s later: %d; the model counts as "
                                          "changed: %s." % (len(runs), bool(g.STATE.get("dirty")))))
    check("check-4", "The panel says 'Model changed since the last check — press Check' and the rows are greyed",
          RP_PANEL, lambda: (g.logic.CHANGED_SINCE in head and parts.get("stale") is True,
                             "Header: %s; rows greyed (no marks, '—'): %s." % (head[:3], parts.get("stale"))))
    check("check-5", "The viewport's status box says it too, with no status mark, and the viewport is redrawn so its "
          "marks grey out", "The status box drawn in the viewport, and the marks greyed on screen.",
          lambda: (rows[0] == "Gordium · " + g.logic.CHANGED_SINCE and len(redraws) >= 1 and g.stale(g.overlay()),
                   "Status box: %s; viewport redraws after the edit: %d; the overlay counts as out of date: %s." % (
                       rows, len(redraws), g.stale(g.overlay()))))
    buttons[0].Click.fire(buttons[0], None)          # Check
    second = checked_at(g, doc)
    runs_after_check = len(runs)
    head2 = texts(parts["header"].rows)
    check("check-6", "Pressing Check checks the model as it is now; the rows are current again", RP_PANEL,
          lambda: (runs_after_check == 1 and not parts.get("stale") and g.logic.CHANGED_SINCE not in head2,
                   "Checks run: %d; header: %s; greyed: %s." % (runs_after_check, head2[:2], parts.get("stale"))))

    auto.Checked = True                              # Check after every edit: on
    saved = g._ui_state(doc).get("auto_check")
    edited(g, doc)
    head3 = texts(parts["header"].rows)
    idle_after_wait(g)
    runs_auto = len(runs) - runs_after_check
    check("check-7", "Ticked, it is saved in the file and every edit is checked by itself", RP_PANEL,
          lambda: (saved is True and runs_auto == 1,
                   "Saved auto_check=%s; checks run by itself after the edit: %d." % (saved, runs_auto)))
    path = os.path.join(HERE, "saved.3dm")
    doc.Export(path)
    kept = json.loads(Rhino.FileIO.File3dm.Read(path).Strings.GetValue(g.SECTION, g.UI_ENTRY) or "{}")
    g2 = fresh_module()                              # Rhino restarted, the file opened again
    Rhino.RhinoDoc.ActiveDoc = doc
    g2.register_dock = lambda: "dock-id"
    g2.run_check(doc, report=False)
    p2 = g2.STATE.get("panel_parts") or {}
    auto2 = next((it.Control for row in p2.get("greyed") or [] for it in getattr(row, "Items", None) or []
                  if getattr(getattr(it, "Control", None), "Text", "") == g2.logic.AUTO_CHECK_LABEL), None)
    check("check-8", "The tick is kept with the file and comes back ticked", "Rhino's own save and reopen.",
          lambda: (kept.get("auto_check") is True and auto2 is not None and auto2.Checked is True,
                   "Saved copy auto_check=%s; reopened tick Checked=%s." % (kept.get("auto_check"), auto2 and auto2.Checked)))
    auto2.Checked = False

    # a start box cancelled: its own edits rolled back, the results still current (never greyed for them)
    before_box = g2.STATE.get("dirty")
    options = g2.ask({"cmd": "options", "jurisdiction": g2.JURISDICTION})

    def inside(doc_, facts, text, state):
        g2._changed(None, None)                               # an edit the box made (rolled back on Cancel)
    g2.STATE.update(on_confirm=inside, box_cancel_after_picks=False)
    g2.STATE["auto_ok"] = True
    real_drawn = g2._drawn
    g2._drawn = lambda *a, **k: None             # the scripted box closes as Cancel (nothing saved)
    try:
        result = g2.confirm(doc, g2.current_facts(doc), options, "check")
    finally:
        g2._drawn = real_drawn
    check("check-9", "Cancelling a start box never greys out current results", "Rhino's events during a real box.",
          lambda: (result is None and g2.STATE.get("dirty") == before_box,
                   "Box result %s; the model counts as changed: %s (was %s before the box)." % (
                       result, g2.STATE.get("dirty"), before_box)))
    # review round 1, P1: an edit right after a check, then the tick turned on: the edit is still checked (its time
    # is never moved earlier, so the check from before it never counts as covering it). Real time, no shifting.
    g2.live(True)                                    # as GordiumCheck leaves it: edits noticed
    runs2 = []
    real2 = g2.run_check
    g2.run_check = lambda *a, **k: (runs2.append(1), real2(*a, **k))[1]
    g2.check_now()                                   # a check finishes now
    edited(g2, doc)                                  # an edit a moment later
    auto2.Checked = True                             # and the tick turned on at once
    time.sleep(0.7)
    g2._idle(None, None)
    check("check-10", "An edit right after a check, then the tick on: the edit is still checked", "Rhino's real idle "
          "timing.", lambda: (len(runs2) == 2, "Checks run: %d (the Check, then the edit's own)." % len(runs2)))
    auto2.Checked = False

    # review round 1, P2: another document to the front is checked once (it is not an edit), the tick off
    other = new_doc()                                # an empty file: no lot facts, nothing to check
    g2._new_document(None, None)
    g2._idle(None, None)
    head_other = texts((g2.STATE.get("panel_parts") or {}).get("header").rows)
    Rhino.RhinoDoc.ActiveDoc = doc                   # back to the checked file
    before_switch = len(runs2)
    g2._new_document(None, None)
    g2._idle(None, None)
    head_back = texts((g2.STATE.get("panel_parts") or {}).get("header").rows)
    check("check-11", "Switching to another file checks it once, whatever the tick, and never says 'Model changed'",
          "Rhino's real document events.", lambda: (
              len(runs2) == before_switch + 1 and g2.logic.CHANGED_SINCE not in head_other + head_back
              and any("press Check" in t for t in head_other),
              "An empty file in front: header %s; back to the checked file: %d check(s) ran, header %s." % (
                  head_other[:2], len(runs2) - before_switch, head_back[:2])))
    # review round 2: the viewport greys even with the panel closed; GordiumLive flips the tick, never the hooks
    import gordium_ui as gui
    real_show = gui.show
    gui.show = lambda *a, **k: None                  # the panel closed: nothing of it is refreshed
    p2 = g2.STATE.get("panel_parts") or {}
    form = p2.get("form")
    g2.STATE["panel_parts"] = None
    drawn = []
    real_redraw2 = g2._redraw
    g2._redraw = lambda: (drawn.append(1), real_redraw2())[1]
    g2.check_now()
    edited(g2, doc)
    idle_after_wait(g2)
    g2.STATE["panel_parts"] = p2
    gui.show = real_show
    check("check-12", "With the panel closed, the viewport still greys after an edit", "The viewport's look in Rhino.",
          lambda: (len(drawn) >= 1 and g2.stale(g2.overlay()), "Redraws after the edit with no panel: %d; out of "
                   "date: %s." % (len(drawn), g2.stale(g2.overlay()))))
    was = g2._auto(doc)
    g2.toggle_live()
    check("check-13", "GordiumLive flips Check after every edit, and edits are still noticed", "The command in Rhino.",
          lambda: (g2._auto(doc) is (not was) and bool(g2.STATE.get("hooks")),
                   "Check after every edit: %s -> %s; edit hooks attached: %s." % (was, g2._auto(doc),
                                                                                  bool(g2.STATE.get("hooks")))))
    g2.toggle_live()
    # review round 3, P1: a fresh session whose first command is Edit site… (GordiumFacts): edits are still noticed
    g3 = fresh_module()
    Rhino.RhinoDoc.ActiveDoc = doc
    g3.register_dock = lambda: "dock-id"
    g3.STATE.update(box_picks=[], on_confirm=lambda *a: None)
    live_before = bool(g3.STATE.get("live"))
    g3.edit_facts()                                  # the start box, Draw (scripted), then its own check
    hooked = bool(g3.STATE.get("hooks"))
    if hooked:                                       # without the hooks Rhino's edit reaches nothing: a FAIL below
        edited(g3, doc)
        idle_after_wait(g3)
    rows3 = g3._status_rows(g3.overlay(), g3.stale(g3.overlay()))
    check("check-14", "A session started with Edit site… still greys the results after an edit", "Rhino's real "
          "commands and events.", lambda: (not live_before and hooked and rows3[0] == "Gordium · " + g3.logic.CHANGED_SINCE,
                                          "Edit hooks before: %s, after Edit site…'s check: %s; status box after an "
                                          "edit: %s." % (live_before, hooked, rows3)))
    # demo review (#26 with #27): a box that ends in an error (its rollback stopped partway) leaves the model
    # counted as changed, so the results grey out, never shown as current
    g3.check_now()
    real_confirm = g3._confirm

    def broken(*a, **k):
        g3._changed(None, None)                      # the box changed the model...
        raise RuntimeError("rollback stopped partway")   # ...then failed
    g3._confirm = broken
    try:
        g3.confirm(doc, g3.current_facts(doc), g3.ask({"cmd": "options", "jurisdiction": g3.JURISDICTION}), "check")
        raised = False
    except RuntimeError:
        raised = True
    finally:
        g3._confirm = real_confirm
    idle_after_wait(g3)
    rows4 = g3._status_rows(g3.overlay(), g3.stale(g3.overlay()))
    check("check-15", "A start box that ends in an error leaves the results greyed, never shown as current",
          "A real Rhino error inside the box.", lambda: (raised and bool(g3.STATE.get("dirty")) and
                                                        rows4[0] == "Gordium · " + g3.logic.CHANGED_SINCE,
                                                        "Raised: %s; changed mark: %s; status box: %s." % (
                                                            raised, bool(g3.STATE.get("dirty")), rows4)))
    out = os.path.join(HERE, "results_check_button.json")
    json.dump(RESULTS, open(out, "w"), indent=1)
    print(json.dumps({"claims": len(RESULTS), "passed": sum(r["offline_ok"] for r in RESULTS)}))


if __name__ == "__main__":
    main()
