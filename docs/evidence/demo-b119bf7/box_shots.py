#! python3
"""The start box for R-1b and R-3b (one-family detached, as the worker sends them), each shown ~8 s so it can be
captured from outside; writes <temp>/gordium_box_shots/<zone>.json (width, height, location) while it shows, then
out.json with done."""
import json, os, sys, tempfile, traceback
import Eto.Forms as ef
import scriptcontext as sc
WT = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/demo7_rhino"
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa
S = os.path.join(tempfile.gettempdir(), "gordium_box_shots") + "/"
os.makedirs(S, exist_ok=True)
for f in os.listdir(S):
    os.remove(S + f)
log = {}
doc = None
try:
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
        loaded.off()
    st = sc.sticky.setdefault("gordium_state", {})
    w = st.pop("worker", None)
    if w is not None:
        w.terminate()
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    st.clear()
    st.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino as g
    doc = TestDocs("box_shots").__enter__().open("Large Objects - Feet")
    options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})
    for zone in ("R-1b", "R-3b"):
        state = g._box_state(doc, {"zone": zone, "use": "one_family_detached", "jurisdiction": g.JURISDICTION},
                             options, {}, "start")

        def shown(dialog, zone=zone):
            d = {"width": int(dialog.Width), "height": int(dialog.Height), "x": int(dialog.Location.X),
                 "y": int(dialog.Location.Y), "questions": len(state.get("follow_ups") or [])}
            log[zone] = d
            json.dump(d, open(S + zone + ".json", "w"))
            dialog.BringToFront()
            t = ef.UITimer()
            t.Interval = 8
            t.Elapsed += lambda s, e: (t.Stop(), dialog.Close(False))
            t.Start()

        state["_on_shown"] = shown
        g.ui.start_box(state, options, "start")
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        close(doc)
    log["done"] = True
    json.dump(log, open(S + "out.json", "w"), indent=1)
