#! python3
"""The panel's Zoning report… button, in Rhino 8, end to end (Ben's test, 2026-10-20: it did nothing after
GordiumStart). Run in Rhino, not in CI:
1. a fresh document from Rhino's feet template; GordiumStart's flow (the sample lot, the starting house);
2. Zoning report… (gordium_rhino.open_report, exactly what the button calls);
3. records: the report file exists and was written now, the panel's message line says "Report saved to …", and
   what the command line said. Writes <temp>/gordium_report_button/out.json and a ready marker, then leaves the
   panel up so its window can be captured.
Run it again with sc.sticky["gordium_report_button"] = "close" to close its document (it always closes it itself
if anything fails)."""
import json
import os
import sys
import tempfile
import time
import traceback

import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_report_button") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # the repo
os.makedirs(S, exist_ok=True)
log = {}


def fresh_module():
    state = sc.sticky.setdefault("gordium_state", {})
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    old = sys.modules.get("gordium_rhino")
    if old is not None:
        try:
            old.off()
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


if sc.sticky.pop("gordium_report_button", None) == "close":
    log["closed"] = [d.Path for d in leftovers() if "report_button" in (d.Path or "") and close(d)]
    json.dump(log, open(S + "closed.json", "w"), indent=1)
else:
    docs = TestDocs("report_button").__enter__()
    doc = None
    try:
        log["leftovers_closed"] = docs.left_over
        g = fresh_module()
        doc = docs.open("Large Objects - Feet")
        g.STATE["on_confirm"] = lambda *a: None
        g.gordium_check()                                    # an empty model: GordiumStart's flow
        log["start_floors"] = len((g.STATE.get("start") or {}).get("floors") or [])
        path = g.report_path(doc)
        log["report_path"] = path
        log["report_before"] = os.path.exists(path)          # GordiumStart writes no report (the bug's cause)
        clicked = time.time()
        g.open_report()                                      # what Zoning report… calls
        log["report_exists"] = os.path.exists(path)
        log["report_written_now"] = os.path.exists(path) and os.path.getmtime(path) >= clicked - 1
        log["report_bytes"] = os.path.getsize(path) if os.path.exists(path) else 0
        log["said"] = g.STATE.get("said") or []
        parts = g.STATE.get("panel_parts") or {}
        log["panel_message"] = parts["message"].Text if parts.get("message") is not None else None
        log["ok"] = bool(log["report_written_now"] and (log["panel_message"] or "").startswith("Report saved to "))
    except Exception:
        log["trace"] = traceback.format_exc()
        if doc is not None:
            close(doc)                                       # never left behind on a failure
    finally:
        json.dump(log, open(S + "out.json", "w"), default=str, indent=1)
        json.dump({"ready": time.time()}, open(S + "ready.json", "w"))
