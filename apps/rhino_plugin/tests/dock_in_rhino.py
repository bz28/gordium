#! python3
"""The Gordium panel docked in Rhino's own panels, in Rhino 8, each claim asserted (the run fails loudly
otherwise). Run in Rhino, not in CI. GordiumStart on the sample, then:
1. the panel is a docked Rhino panel (Rhino's panel system shows it), not a floating window, holding the rows;
2. (the start-box gate's greying lives in #19, above this branch: checked once the two meet);
3. a reload of the plugin refills the same docked panel (never a second one) with the new copy's controls;
4. GordiumOff closes it; the next command opens it again, filled.
Phase "run" leaves the document open for a screenshot of its window; phase "close"
(sc.sticky["gordium_dock_phase"]) turns Gordium off and closes it. Writes <temp>/gordium_dock/<phase>_out.json."""
import json
import os
import sys
import tempfile
import traceback

import Eto.Forms as ef
import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_dock") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
phase = sc.sticky.pop("gordium_dock_phase", "run")
log = {"phase": phase, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def load(keep_state=False):
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None and not keep_state:
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    if not keep_state:
        state.clear()
        state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino
    return gordium_rhino


def rows(p):
    out = []
    for group in p.get("groups") or []:
        for k in range(group.Children.Count):
            out.append(str(group.Children[k].Values[0]))
    return out


try:
    if phase == "run":
        g = load()
        doc = TestDocs("dock").__enter__().open("Large Objects - Feet")
        g.gordium_check()                                    # GordiumStart's flow on the sample
        dock = System.Guid(g.DOCK_ID)
        p = g.STATE["panel_parts"]
        host = p["form"].host
        claim("1 docked in Rhino's panels, not a floating window",
              Rhino.UI.Panels.IsPanelVisible(dock) and isinstance(p["form"], g.ui.DockHost) and
              not isinstance(p["form"], ef.Form) and host.GetType().FullName == "GordiumDock.Panel",
              str(host.GetType().FullName))
        log["placed"] = p.get("placed")
        window, doc_window = host.ParentWindow, Rhino.UI.RhinoEtoApp.MainWindowForDocument(doc)
        log["parent"] = str(getattr(window, "Title", None))
        if log["placed"] == "docked":           # beside Rhino's panels (Properties or Layers showing)
            claim("1 docked in the document's own window", log["parent"] == doc.Name, log["parent"])
        else:                                   # no dock showing: Rhino floats it; sized to the panel, at the right
            b, d = window.Bounds, doc_window.Bounds
            log["floating"] = {"window": [b.X, b.Y, b.Width, b.Height], "document": [d.X, d.Y, d.Width, d.Height]}
            claim("1 floating (no dock showing): the panel's size, at the document window's right edge",
                  log["placed"] == "floating" and window.ClientSize.Width >= g.ui.PANEL_WIDTH and
                  window.ClientSize.Height >= 420 and abs((b.X + b.Width) - (d.X + d.Width)) <= 60, log["floating"])
        claim("1 its document's panel", g.logic.dock_host(sc.sticky["gordium_dock_hosts"],
                                                          doc.RuntimeSerialNumber).Equals(host))
        log["rows"] = rows(p)
        aligns = set()

        def walk(c):
            if isinstance(c, ef.Label):
                aligns.add(str(c.TextAlignment))
            for k in ("Content", "Controls"):
                v = getattr(c, k, None)
                if v is not None and not isinstance(v, str):
                    try:
                        for x in (v if hasattr(v, "__iter__") else [v]):
                            walk(x)
                    except TypeError:
                        walk(v)
        walk(p["header"])
        walk(p["detail"])
        claim("1 its text left aligned (the docked panel had turned it right aligned)", aligns == {"Left"}, sorted(aligns))
        claim("1 holding the rows", any("Rear yard" in r for r in log["rows"]) and
              any("Side yard" in r for r in log["rows"]), log["rows"][:8])
        first_tree = p["tree"]
        g = load(keep_state=True)                            # a reload (an update, Rhino reloading the script)
        g.run_check(doc, report=False)
        g.panel()
        p = g.STATE["panel_parts"]
        claim("3 a reload refills the same docked panel with the new copy's controls",
              p["form"].host.Equals(host) and p["tree"] is not first_tree and
              len(sc.sticky["gordium_dock_hosts"]) >= 1 and any("Rear yard" in r for r in rows(p)))
        g.off()
        claim("4 GordiumOff closes it", not Rhino.UI.Panels.IsPanelVisible(dock))
        g.STATE["auto_ok"] = True
        g.run_check(doc, report=False)
        p = g.panel()
        claim("4 the next command opens it again, filled", Rhino.UI.Panels.IsPanelVisible(dock) and
              any("Rear yard" in r for r in rows(p)))
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    else:
        g = sys.modules.get("gordium_rhino")
        if g is not None:
            g.off()
        log["closed"] = [str(d.Path) for d in leftovers() if "dock" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
