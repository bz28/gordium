#! python3
"""GordiumPanel (the command Rhino's startup list runs), in Rhino 8, each claim asserted (the run fails loudly
otherwise). Run in Rhino, not in CI. With Gordium off, on a fresh test document, it runs gordium_panel.py as the
command does, then: the panel is registered; no checker was started and no check ran; the model is untouched;
opening the Gordium panel shows its "run GordiumStart or GordiumCheck" line, never an empty container. Not
checked here (needs a Rhino restart): the startup list itself running it at launch.
Writes <temp>/gordium_startup/out.json; closes its document."""
import json
import os
import runpy
import sys
import tempfile
import traceback

import Eto.Forms as ef
import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_startup") + "/"
APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


doc = None
try:
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
        loaded.off()
        loaded._stop_worker()
    doc = TestDocs("startup").__enter__().open("Large Objects - Feet")
    before = (doc.Objects.Count, doc.Modified, doc.Strings.Count)
    sc.sticky.setdefault("gordium_state", {})["last"] = None    # no check result before it runs
    runpy.run_path(os.path.join(APP, "gordium_panel.py"), run_name="__main__")      # what the command runs
    g = sys.modules["gordium_rhino"]
    dock = System.Guid(g.DOCK_ID)
    claim("the panel is registered", sc.sticky.get("gordium_dock_registered") and
          sc.sticky["gordium_dock"].GUID.Equals(dock))
    last = g.STATE.get("last") or {}
    claim("no checker started, no check ran", g.STATE.get("worker") is None and "summary" not in last,
          {"worker": str(g.STATE.get("worker")), "last": last})
    claim("the model untouched", (doc.Objects.Count, doc.Modified, doc.Strings.Count) == before,
          {"before": before, "after": (doc.Objects.Count, doc.Modified, doc.Strings.Count)})
    g.ui.open_dock(dock)                                  # as Rhino does when it restores a Gordium tab
    Rhino.RhinoApp.Wait()
    host = g.logic.dock_host(sc.sticky.get("gordium_dock_hosts") or {}, doc.RuntimeSerialNumber)
    text = getattr(getattr(host, "Content", None), "Text", None)
    log["shows"] = text
    claim("the reopened tab is filled, not empty", Rhino.UI.Panels.IsPanelVisible(dock) and host is not None and
          isinstance(host.Content, ef.Label) and text.startswith("Gordium: run GordiumStart or GordiumCheck"), text)
    Rhino.UI.Panels.ClosePanel(dock)
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    if doc is not None:
        close(doc)
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
