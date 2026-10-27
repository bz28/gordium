#! python3
"""The MVP list's visible changes, in Rhino 8, each claim asserted (the run fails loudly otherwise). Run in Rhino,
not in CI. From a fresh document: GordiumStart on the sample, then:
- flat ground (item 5): the start box has no Ground row; the lot facts say the ground is assumed flat; Building height
  and Stories comply, their rows reading "… · assuming flat ground";
- labels off by default (item 1): the document's setting is off and the panel's tick unticked; a failing yard (the
  house moved 5 ft to the left, QUICKSTART test 6's failing yard) still has its shortfall label; ticking turns the labels on, saved in the document;
- the panel (items 2, 3): no code-edition line in its header (it is in the legend's text), the column is "Delta" and
  its cells say "to spare" / "short".
Captures: Top view with labels off (the failing shortfall only) and on; the panel. Writes <temp>/gordium_mvp/out.json
and frames/*.png; closes its document. Phase "close" (sc.sticky["gordium_mvp_phase"]) closes it if a run left it."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_mvp") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
phase = sc.sticky.pop("gordium_mvp_phase", "run")
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


def capture(doc, name):
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    doc.Views.ActiveView = view
    view.Redraw()
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    bmp.Save(S + "frames/" + name + ".png")


def panel_rows(g):
    p = g.STATE.get("panel_parts") or {}
    rows = []
    for group in p.get("groups") or []:
        for k in range(group.Children.Count):
            rows.append([str(v) for v in group.Children[k].Values])
    return rows


doc = None
try:
    if phase == "run":
        g = fresh_module()
        docs = TestDocs("mvp").__enter__()
        doc = docs.open("Large Objects - Feet")
        seen = {}

        def on_confirm(doc_, facts, text, state):
            seen["rows"] = [r["key"] for r in g.logic.box_rows(state)]
        g.STATE["on_confirm"] = on_confirm
        g.gordium_check()                                    # GordiumStart's flow on the sample
        claim("5 no Ground row in the start box", "ground" not in seen.get("rows", []) and "lot" in seen["rows"],
              seen.get("rows"))
        facts = g.current_facts(doc)
        claim("5 the ground is assumed flat, finished", facts.get("ground_assumed") == "flat" and
              facts.get("grade_is") == "finished", {k: facts.get(k) for k in ("ground_assumed", "grade_is")})
        items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
        claim("5 stories comply; the height is at the limit (it needs review on this lot: the open question of "
              "which back lines are rear lines)", items["Stories"]["status"] == "complies" and
              items["Building height"]["margin"] == "at limit" and items["Building height"]["status"] in
              ("complies", "needs_review"),
              {n: (items[n]["status"], items[n]["margin"]) for n in ("Building height", "Stories")})
        rows = panel_rows(g)
        claim("5 the rows say assuming flat ground",
              any("Building height · assuming flat ground" in r[0] for r in rows) and
              any("Stories · assuming flat ground" in r[0] for r in rows), [r[0] for r in rows][:12])
        parts = g.STATE.get("panel_parts")
        claim("1 labels off by default (the document's setting, the tick)",
              g.STATE["labels_by_doc"].get(doc.RuntimeSerialNumber) is False and parts["labels_box"].Checked is False)
        head = (g.STATE.get("last") or {}).get("header") or {}
        lines = g.logic.panel_header(head)
        claim("2 no code-edition line in the panel header",
              "Ch. 325" in (head.get("code") or "") and not any("Ch. 325" in t for t in lines["above"] + lines["below"]))
        claim("2 the legend names it", ("Checked against: " + head["code"]) in g.logic.legend_text(head["code"]))
        claim("3 the column is Delta", [c.HeaderText for c in parts["tree"].Columns][3] == "Delta",
              [c.HeaderText for c in parts["tree"].Columns])
        claim("3 Delta in words", any(r[3].endswith(" to spare") for r in rows), [r[3] for r in rows])
        # a failing yard: the house 5 ft to the left (the left side yard short under every reading); labels off
        ft = 1.0 / g._scale(doc)
        for o in g._buildings(doc):
            doc.Objects.Transform(o.Id, rg.Transform.Translation(-5 * ft, 0, 0), True)
        g.run_check(doc, report=False)
        rows = panel_rows(g)
        rear = next(r for r in rows if "Side yard, Southwest" in r[0])
        claim("3 a shortfall says short", rear[3].endswith(" short"), rear)
        o = g.overlay()
        # (the drawing shows a failing yard's number with its ✕; what it needs is the panel's and the notice's).
        # Top drawn last first: o.placed is the last view's (capture redraws Top)
        capture(doc, "1_labels_off_failing_shortfall_only")
        failing = [pl[5] for j, pl in (getattr(o, "placed", None) or {}).items()
                   if isinstance(j, int) and pl[5] and o.yard_dims[j][2] == "does_not_comply"]
        claim("1 labels off: a failing yard's number still shown, with its ✕",
              failing and all(g.logic.yard_label_shown(False, "does_not_comply") for _ in failing) and
              failing[0].startswith("✕ "), failing)
        claim("1 labels off: the others not", not g.logic.yard_label_shown(False, "complies"))
        g.set_labels(True)                                   # the panel's tick
        ui_state = g._ui_state(doc)
        claim("1 the tick turns them on, saved in the document",
              ui_state.get("show_labels") is True and g.STATE["labels_by_doc"][doc.RuntimeSerialNumber] is True)
        capture(doc, "1_labels_on")
        g.set_labels(False)
        log["ok"] = all(c["ok"] for c in log["claims"].values())
        sc.sticky["gordium_mvp_doc"] = doc.RuntimeSerialNumber
    else:
        log["closed"] = [d.Path for d in leftovers() if "mvp" in (d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
