#! python3
import json, os, sys, tempfile, traceback
import Rhino, scriptcontext as sc
WT = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/laneC2/x_rl"
out = os.path.join(tempfile.gettempdir(), "real_setup.json")
try:
    sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
    from test_docs_in_rhino import TestDocs
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
    doc = TestDocs("real_rl").__enter__().open("Large Objects - Feet")
    g.gordium_check()
    g.STATE["lookup_fixture"] = "96_ithaca_rd"
    g.STATE["auto_ok"] = False
    sc.sticky["real_before"] = sorted(str(o.Id) for o in doc.Objects)
    json.dump({"doc": doc.Name, "objs": doc.Objects.Count}, open(out, "w"))
except Exception:
    json.dump({"err": traceback.format_exc()}, open(out, "w"))
