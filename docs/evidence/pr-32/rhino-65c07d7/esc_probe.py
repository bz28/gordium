#! python3
"""#32 Esc probe (the Rhino job): a fresh feet document, GordiumStart's sample checked with the real checker, then
a check with the slow checker (12 s) and its wait window; the job outside presses Esc once (with the document window
or the wait window in front). Records whether that check ended cancelled and how long it took. Head from
esc_wt.txt; writes esc_probe.json ("done": true); closes its document."""
import json
import os
import sys
import time
import traceback

import scriptcontext as sc

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(H + "esc_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

SLOW = 12.0
out = {"head": WT}
doc = None
g = None
try:
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
    import gordium_rhino as g
    doc = TestDocs("escprobe").__enter__().open("Large Objects - Feet")
    g.gordium_check()
    g.live(False)
    g._stop_worker()
    g.STATE["worker_command"] = [g._python(), "-u", os.path.join(WT, "apps/rhino_plugin/tests/slow_checker.py"),
                                 str(SLOW)]
    g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
    json.dump({"waiting_from": time.time()}, open(H + "esc_waiting.json", "w", encoding="utf-8"))
    import Eto.Forms as ef
    import Rhino
    mode = open(H + "esc_mode.txt", encoding="utf-8").read().strip()
    raised = {"mode": mode, "n": 0}

    def windows():
        return [(w.Title, bool(w.HasFocus), bool(w.Visible)) for w in ef.Application.Instance.Windows]

    def tick(s, e):
        try:
            raised["n"] += 1
            if raised["n"] == 1:                     # 2 s into the wait: the window asked for, to the front
                if mode == "wait":
                    for w in ef.Application.Instance.Windows:
                        if w.Title == "Gordium" and w.Visible:
                            w.BringToFront()
                            w.Focus()
                else:
                    mw = Rhino.UI.RhinoEtoApp.MainWindowForDocument(doc)
                    mw.BringToFront()
                    mw.Focus()
                    doc.Views.ActiveView = doc.Views.Find("Top", False)
            elif raised["n"] == 2:                   # what has focus now: then the job outside presses Esc
                raised["windows"] = windows()
                json.dump(raised, open(H + "esc_raised.json", "w", encoding="utf-8"), default=str)
                timer.Stop()
        except Exception:
            raised["error"] = traceback.format_exc()
            json.dump(raised, open(H + "esc_raised.json", "w", encoding="utf-8"), default=str)
            timer.Stop()
    timer = ef.UITimer()
    timer.Interval = 1.5
    timer.Elapsed += tick
    timer.Start()
    began = time.time()
    result = g.run_check(doc, report=False)
    out["took_s"] = round(time.time() - began, 2)
    out["result_none"] = result is None
    out["cancelled"] = bool((g.STATE.get("last") or {}).get("cancelled"))
    out["last"] = g.STATE.get("last")
    out["raised"] = raised
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    try:
        if g is not None:
            g.STATE.pop("worker_command", None)
            g._stop_worker()
            g.off()
    except Exception:
        pass
    if doc is not None:
        close(doc)
    out["done"] = True
    json.dump(out, open(H + "esc_probe.json", "w", encoding="utf-8"), indent=1, default=str)
