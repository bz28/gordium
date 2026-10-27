#! python3
"""Puts the Gordium windows on show for a capture (run in Rhino after ui_flow_in_rhino.py, not in CI):
- mode "panel" (the default): selects an item in the panel so its detail shows; writes <temp>/gordium_windows/
  ready.json
- mode "box": opens the real start box (Edit site…) and writes ready.json once it is on screen; it closes itself
  after 12 s (nothing is saved)
Capture only Rhino's own windows, by window id (screencapture -l<id>), never the whole screen.
Set the mode in sticky["gordium_windows_mode"] before running, or leave it for "panel"."""
import json
import os
import sys
import tempfile
import time

import Eto.Forms as ef
import Rhino
import scriptcontext as sc

OUT = os.path.join(tempfile.gettempdir(), "gordium_windows")
if not os.path.isdir(OUT):
    os.makedirs(OUT)
g = sys.modules["gordium_rhino"]
doc = Rhino.RhinoDoc.ActiveDoc
mode = sc.sticky.pop("gordium_windows_mode", "panel")


def ready(**info):
    json.dump(dict(info, mode=mode, at=time.time()), open(os.path.join(OUT, "ready.json"), "w", encoding="utf-8"))


try:
    if mode == "panel":
        p = g.STATE.get("panel_parts")
        items = (p.get("view") or {}).get("items") or [] if p else []
        want = sc.sticky.pop("gordium_windows_item", None)    # an item by name, else the first problem
        pick = next((i for i in items if i["name"] == want), None) if want else None
        pick = pick or next((i for i in items if i["status"] in ("does_not_comply", "needs_review") and i.get("detail")),
                            None)
        if pick is not None:
            p["selected"] = pick["id"]
            g.ui.show(p, p["view"])
        ready(selected=pick["id"] if pick else None)
    else:
        def shown(dialog):
            timer = ef.UITimer()
            timer.Interval = 12
            timer.Elapsed += g.logic.guard(lambda s, e: (timer.Stop(), dialog.Close(False)), "close the start box")
            timer.Start()
            ready(title=dialog.Title)

        g.STATE["auto_ok"] = False
        g.STATE["on_box_shown"] = shown
        options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
        g.confirm(doc, g.current_facts(doc), options, "start")
        g.STATE.pop("on_box_shown", None)
except Exception:
    import traceback
    ready(trace=traceback.format_exc())
