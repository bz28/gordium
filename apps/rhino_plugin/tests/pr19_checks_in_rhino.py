#! python3
"""PR #19's start box and live mode, in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in Rhino,
not in CI. Phases (sc.sticky["gordium_pr19_phase"]):
- "run" (default): from a fresh document with the sample's starting house and live mode on:
  1. one start box at a time: with a box open, the panel's Edit site… only says "Finish or cancel the open start
     box first", every gated panel action does nothing, the legend still runs, the panel's controls are off;
  3. no check while the box is open (live mode's idle re-check, simulated, refuses and keeps the pending edit), and
     exactly one after it closes;
  4. after closing with nothing selected, Zoom to stays off;
  5. with a pending edit, switching to another document re-checks that document.
- "box" (sc.sticky["gordium_windows_mode"] = "box", as capture.py sets it): the real start box open over the panel, for
  a capture of the greyed panel; it closes itself after 12 s. Writes <temp>/gordium_windows/ready.json.
- "close": closes the documents this run opened.
Writes <temp>/gordium_pr19/out.json; raises AssertionError on any failed claim."""
import json
import os
import sys
import tempfile
import time
import traceback

import Eto.Forms as ef
import Rhino
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402
from test_docs_in_rhino import look_up_106  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_pr19") + "/"
READY = os.path.join(tempfile.gettempdir(), "gordium_windows", "ready.json")
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
os.makedirs(os.path.dirname(READY), exist_ok=True)
phase = "box" if sc.sticky.pop("gordium_windows_mode", None) == "box" else sc.sticky.pop("gordium_pr19_phase", "run")
log = {"phase": phase, "claims": {}}


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


try:
    if phase == "run":
        g = fresh_module()
        docs = TestDocs("pr19").__enter__()
        doc = docs.open("Large Objects - Feet")
        g.STATE["on_confirm"] = lambda *a: None
        look_up_106(g, g.gordium_check)                                 # the sample, its starting house; live mode on
        parts = g.STATE.get("panel_parts")
        claim("a starting house and a panel", parts is not None and len(g._buildings(doc)) == 3)
        options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
        calls = []
        real_check = g.run_check

        def counting(d, report=True):
            calls.append(d.RuntimeSerialNumber if d is not None else None)
            return real_check(d, report)
        g.run_check = counting
        inside = {}

        def during(doc_, facts, text, state):             # the box is open now (the auto box's hook)
            said_before = len(g.STATE.get("said") or [])
            g._actions()["edit_site"]()                    # 1. Edit site… from the panel
            inside["refused"] = (g.STATE.get("said") or [])[said_before:]
            inside["gated"] = {}
            # every action the panel has (new ones exercised automatically) but the legend (it only shows something)
            # and Edit site… (checked above); the gate stops each before it runs, so no arguments are needed: an action
            # that got through would raise or act, and the claim fails
            inside["expected"] = sorted(set(g.PANEL_ACTIONS()) - {"legend", "edit_site"})
            for name in inside["expected"]:
                before = len(g.STATE.get("said") or [])
                try:
                    g._actions()[name]()
                except Exception as e:
                    inside["gated"][name] = "raised " + str(e)[:80]
                    continue
                inside["gated"][name] = (g.STATE.get("said") or [])[before:]
            shown = []
            real_legend = g.ui.legend
            g.ui.legend = lambda code=None: shown.append(code)   # the legend's dialog itself would block the script
            g._actions()["legend"]()
            g.ui.legend = real_legend
            inside["legend_ran"] = len(shown) == 1
            inside["greyed"] = [c.Enabled for c in parts.get("greyed") or []] + \
                [b.Enabled for b in parts.get("box_buttons") or []]
            g.STATE["dirty"] = time.time() - 5            # 3. an edit while the box is open, then live mode's idle
            g._idle(None, None)
            inside["checks_while_open"] = len(calls)
            inside["dirty_kept"] = bool(g.STATE.get("dirty"))

        g.STATE["on_confirm"] = during
        g.confirm(doc, g.current_facts(doc), options, "check")    # Edit site's box (auto: ticks and Draws)
        claim("1 a second box refused with the message",
              inside.get("refused") == [g.logic.BOX_BUSY], inside.get("refused"))
        claim("1 every gated panel action was exercised",
              sorted(inside["gated"]) == inside["expected"] and len(inside["expected"]) >= 11, inside["expected"])
        claim("1 every gated panel action only says so",
              all(v == [g.logic.BOX_BUSY] for v in inside["gated"].values()), inside["gated"])
        claim("1 the legend still runs", inside["legend_ran"])
        claim("1 the panel's controls are off while the box is open",
              inside["greyed"] and not any(inside["greyed"]), inside["greyed"])
        claim("3 no check while the box is open, the edit kept",
              inside["checks_while_open"] == 0 and inside["dirty_kept"], inside)
        g._idle(None, None)                               # the box has closed: live mode's next idle
        g._idle(None, None)                               # and the one after
        claim("3 exactly one check after it closes", len(calls) == 1, calls)
        parts["selected"] = None                          # 4. nothing selected, then a box opened and closed
        g.ui.set_box_open(parts, True)
        g.ui.set_box_open(parts, False)
        claim("4 Zoom to stays off with nothing selected", parts["zoom_button"].Enabled is False)
        zoom = parts["zoom_button"]                       # (.NET objects: compared with Equals, not Python identity)
        claim("4 the other controls are back on", all(c.Enabled for c in parts["greyed"] if not c.Equals(zoom)))
        # 5. another document comes to the front (opened: Rhino switches to it) and there is a pending edit; the first
        # document was checked after that edit, the one in front wasn't: the one in front is re-checked (a time shared
        # across documents would call the edit covered and skip it)
        other = docs.open("Large Objects - Feet")
        g.STATE["on_confirm"] = lambda *a: None
        look_up_106(g, g.gordium_check)                                 # a checked house in the one now in front
        front = Rhino.RhinoDoc.ActiveDoc
        claim("5 the new document is in front", front.RuntimeSerialNumber == other.RuntimeSerialNumber)
        g.STATE["dirty"] = time.time()                   # an edit after the front document's last check
        time.sleep(0.1)
        g.STATE.setdefault("checked_at", {})[doc.RuntimeSerialNumber] = time.time()   # the first: checked after it
        time.sleep(g.IDLE_SECONDS + 0.2)                 # the model still for longer than live mode waits
        del calls[:]
        g._idle(None, None)
        claim("5 the document in front is re-checked", calls == [other.RuntimeSerialNumber], calls)
        g.run_check = real_check
        sc.sticky["gordium_pr19"] = {"docs": [doc.RuntimeSerialNumber, other.RuntimeSerialNumber]}
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    elif phase == "box":
        g = sys.modules["gordium_rhino"]
        doc = Rhino.RhinoDoc.ActiveDoc
        options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})

        def shown(dialog):
            timer = ef.UITimer()
            timer.Interval = 12
            timer.Elapsed += g.logic.guard(lambda s, e: (timer.Stop(), dialog.Close(False)), "close the start box")
            timer.Start()
            parts = g.STATE.get("panel_parts") or {}
            json.dump({"title": dialog.Title, "greyed_off": not any(c.Enabled for c in parts.get("greyed") or []),
                       "at": time.time()}, open(READY, "w", encoding="utf-8"))

        g.STATE["auto_ok"] = False
        g.STATE["on_box_shown"] = shown
        g.confirm(doc, g.current_facts(doc), options, "check")
        g.STATE.pop("on_box_shown", None)
        g.STATE["auto_ok"] = True
    else:
        log["closed"] = [d.Path for d in leftovers() if "pr19" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
