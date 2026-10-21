#! python3
"""Red/amber highlighting in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in Rhino, not in CI.
GordiumStart on the sample (a tax-map lot: lot lines ±2'-0"), then the house moved 5 ft west, so the west side yard
is 7'-0" against the 10'-0" required. The lot line may really be up to 2 ft either way, so the yard line is
really 8 to 12 ft from the wall's drawn line:
- red: over under every reading, 1 ft wide (7 + 2 = 9 < 10);
- amber: the rest of the doubt, 4 ft wide (within 12 ft, less the red);
- before the move nothing is coloured red (the start house complies); the colours drawn are the status colours.
Captures Top and Perspective. Writes <temp>/gordium_highlight/run_out.json and frames/*.png; phase "close"
(sc.sticky["gordium_highlight_phase"]) closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_highlight") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
phase = sc.sticky.pop("gordium_highlight_phase", "run")
log = {"phase": phase, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:                # its hooks, drawing and panel off before it is dropped
        loaded.off()
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


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    if view_name == "Perspective":
        view.ActiveViewport.ZoomExtents()
    view.Redraw()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(S + "frames/" + name + ".png")


try:
    if phase == "run":
        g = fresh_module()
        doc = TestDocs("highlight").__enter__().open("Large Objects - Feet")
        g.gordium_check()                                    # GordiumStart's flow on the sample
        items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        claim("the sample is a tax-map lot, the west side yard 12'-0\" of 10'-0\"",
              items["Side yard, West"]["proposed"] == "12'-0\"" and items["Side yard, West"]["required"] == "10'-0\"",
              items["Side yard, West"])
        claim("the start house: nothing red", not any(s == "does_not_comply" for _, s in g.overlay().encroach),
              [s for _, s in g.overlay().encroach])
        ft = 1.0 / g._scale(doc)
        for o in g._buildings(doc):
            doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * ft, 0, 0), True)
        g.run_check(doc, report=False)
        items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        west = items["Side yard, West"]
        claim("moved: the west side yard 7'-0\", does not comply", west["proposed"] == "7'-0\"" and
              west["status"] == "does_not_comply", west)
        regions = [(s, b.GetBoundingBox(True)) for b, s in g.overlay().encroach]
        log["regions"] = [(s, round((bb.Max.X - bb.Min.X) * g._scale(doc), 2)) for s, bb in regions]
        red = [bb for s, bb in regions if s == "does_not_comply"]
        amber = [bb for s, bb in regions if s == "needs_review"]
        width = lambda bb: (bb.Max.X - bb.Min.X) * g._scale(doc)        # noqa: E731  (feet)
        claim("red: 1 ft wide, at the wall", len(red) == 1 and abs(width(red[0]) - 1.0) < 0.05, log["regions"])
        claim("amber: 4 ft wide, beside the red", len(amber) >= 1 and
              any(abs(width(a) - 4.0) < 0.05 and abs(a.Min.X - red[0].Max.X) < 0.01 * ft for a in amber),
              log["regions"])
        claim("each colour from the result", [g.logic.highlight(s) for s in ("does_not_comply", "needs_review")] ==
              ["red", "amber"])
        capture(doc, "Top", "4_red_amber_top")
        capture(doc, "Perspective", "4_red_amber_perspective")
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    else:
        log["closed"] = [str(d.Path) for d in leftovers() if "highlight" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
