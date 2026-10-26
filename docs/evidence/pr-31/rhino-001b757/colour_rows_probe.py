#! python3
"""Which rows colour the house on the sample (#31 001b757's Front shows the whole house amber): GordiumStart on an
empty feet document, then every coloured piece the plugin holds (overlay().encroach): its status, what it is for (row,
why) and its box in feet; plus the rows that need colour. Writes colour_rows.json ("done": true); closes its
document. Head from colour_wt.txt."""
import json
import sys
import traceback

import scriptcontext as sc

H = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(H + "colour_wt.txt", encoding="utf-8").read().strip()
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402

out, opened, g = {"head": WT}, [], None
try:
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None and hasattr(loaded, "off"):
        loaded.off()
    state = sc.sticky.setdefault("gordium_state", {})
    state.pop("worker", None)
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path:
        sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino as g
    doc = TestDocs("colour_rows").__enter__().open("Large Objects - Feet")
    opened.append(doc)
    g.gordium_check()
    k = 1.0 / g._scale(doc)
    pieces = []
    for entry in g.overlay().encroach:
        b, status = entry[0], entry[1]
        info = entry[2] if len(entry) > 2 else {}
        box = b.GetBoundingBox(True)
        pieces.append({"status": status, "info": info, "box_ft": [round(v / k, 2) for v in (
            box.Min.X, box.Min.Y, box.Min.Z, box.Max.X, box.Max.Y, box.Max.Z)]})
    out["pieces"] = pieces
    house = None
    for o in g._buildings(doc):
        bb = o.Geometry.GetBoundingBox(True)
        house = [round(v / k, 2) for v in (bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z)]
    out["house_box_ft"] = house
    out["rows_needing_colour"] = [(i["name"], i["status"]) for i in (g.STATE.get("last") or {}).get("items", [])
                                  if i["status"] in ("does_not_comply", "needs_review") and i.get("group") == "building"]
except Exception:
    out["trace"] = traceback.format_exc()
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    try:
        if g is not None:
            g._stop_worker()
    except Exception:
        pass
    out["done"] = True
    json.dump(out, open(H + "colour_rows.json", "w", encoding="utf-8"), indent=1, default=str)
