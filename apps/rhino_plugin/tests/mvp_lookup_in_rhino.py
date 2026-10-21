#! python3
"""The MVP screens after a real lookup (#15 merged into #19, e5fb0be), in Rhino 8, each claim asserted. A fresh feet
document; GordiumStart with "106 Ithaca Rd" typed and Look up pressed (recorded answers), then Draw. Claims: the box
has no Ground row (flat ground); while the box is open the panel's controls are off; the lookup's lot is the tax map
with its plan turn from north, so the side yards read Southwest/Northeast; the panel is Rhino's docked panel;
"Ground: assumed flat"; every Delta in words and never kinder than its row. Writes <temp>/gordium_mvp_lookup/out.json
and a Top capture; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_mvp_lookup") + "/"
os.makedirs(S, exist_ok=True)
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


def fresh_module():
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


docs = TestDocs("mvplookup").__enter__()
doc = None
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    g.panel()                       # the panel first: "controls off while the box is open" needs one to grey
    seen = {}

    def on_confirm(doc_, facts, text, state):
        seen["keys"] = [r["key"] for r in g.logic.box_rows(state)]
        p = g.STATE.get("panel_parts")
        seen["greyed"] = None if p is None else [c.Enabled for c in p.get("greyed") or []]
        seen["box_open"] = g._box_open()

    g.STATE.update(on_confirm=on_confirm, box_picks=["lookup"], box_overrides={"address": "106 Ithaca Rd, Ithaca, NY 14850"},
                   lookup_fixture="106_ithaca_rd")
    g.gordium_check()
    log["box"] = seen
    claim("the start box has no Ground row (flat ground assumed)", "ground" not in (seen.get("keys") or ["ground"]),
          seen.get("keys"))
    claim("while the box is open, the panel's controls are off", isinstance(seen.get("greyed"), list) and
          len(seen["greyed"]) > 0 and not any(seen["greyed"]), seen)
    facts = g.current_facts(doc)
    log["facts"] = {k: facts.get(k) for k in ("address", "zone", "lot_surveyed", "plan_north_deg", "ground_assumed",
                                              "grade_elevation", "corner_lot")}
    claim("the lookup's lot: the tax map, with its turn from north", facts.get("lot_surveyed") is False and
          isinstance(facts.get("plan_north_deg"), (int, float)), log["facts"])
    last = g.STATE.get("last") or {}
    items = last.get("items") or []
    names = [i["name"] for i in items]
    log["items"] = [(i["name"], i["status"], i.get("proposed"), i.get("delta"), i.get("colour")) for i in items]
    claim("side yards by true compass, as the lookup places the lot", "Side yard, Southwest" in names and
          "Side yard, Northeast" in names, names)
    p = g.STATE.get("panel_parts") or {}
    form = p.get("form")
    log["panel"] = {"docked_host": bool(getattr(form, "host", None)), "placed": p.get("placed"),
                    "visible": bool(getattr(form, "Visible", False))}
    claim("the panel is Rhino's docked panel, shown", log["panel"]["docked_host"] and log["panel"]["visible"],
          log["panel"])
    head = last.get("header") or {}
    log["header"] = head
    claim("flat ground said in the header", "assumed flat" in str(head.get("grade") or "") and
          facts.get("ground_assumed") == "flat", head.get("grade"))
    rows = [i for i in items if i.get("margin") or i.get("delta")]
    bad = [(i["name"], i["status"], i.get("delta")) for i in rows
           if ("to spare" in (i.get("delta") or "") and i["status"] != "complies")
           or (i["status"] == "does_not_comply" and "short" not in (i.get("delta") or "") and i.get("delta"))]
    claim("every Delta in words, never kinder than its row", rows and all(
        not (i.get("delta") or "").startswith(("+", "−")) or i["delta"].endswith(("to spare", "short", "if confirmed"))
        for i in rows) and not bad, {"bad": bad, "rows": [(i["name"], i["status"], i.get("delta")) for i in rows]})
    view = doc.Views.Find("Top", False) or doc.Views.ActiveView
    bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 640))
    if bmp is not None:
        bmp.Save(S + "106_after_lookup_top.png")
    log["ok"] = True
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        try:
            close(doc)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
