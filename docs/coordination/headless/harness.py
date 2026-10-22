"""Load gordium_rhino.py unchanged against the fakes (fakerhino, fake_eto), with the checker answered in process by
design_checker.__main__.answer (what its serve loop calls) and the lookup / context subprocesses run for real."""
import importlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fakerhino  # noqa: E402

WT = "/home/user/wt/dryrun"
VENV = "/home/user/venv/bin/python"
fakerhino.install()
import Rhino  # noqa: E402
import scriptcontext as sc  # noqa: E402


def fresh_module(headless=False):
    state = sc.sticky.setdefault("gordium_state", {})
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    if headless:
        state["headless"] = True
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino as g
    from design_checker.__main__ import answer
    g._python = lambda: VENV

    def ask(request):
        g.STATE["next_id"] = g.STATE.get("next_id", 0) + 1
        a = json.loads(json.dumps(answer(json.loads(json.dumps(dict(request, id=g.STATE["next_id"]))))))
        if not a.get("ok"):
            raise ValueError(a.get("error"))
        return a["result"]
    g.ask = ask
    return g


def new_doc():
    d = fakerhino.Doc()
    Rhino.RhinoDoc.ActiveDoc = d
    Rhino.RhinoDoc.open_docs.append(d)
    sc.doc = d
    return d
