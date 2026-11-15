#! python3
"""The starting house on its own sublayers, its note and the cautious envelope (Ben, 2026-10-21), in Rhino 8. Every
claim is recorded (the run goes on past a failing one) and the run fails at the end if any did. Run in Rhino, not
in CI: the rules are tested in CI (packages/design_checker/tests/test_check.py, the "feature 5" tests).
A fresh feet document, GordiumStart on 106 Ithaca Rd's recorded lookup (a tax-map lot).
1. Each floor block on its own sublayer Gordium::Massing::Floor 1, 2, 3 (one block each, named Floor N, the whole
   house one group); Gordium::Massing::Roof made.
2. The check measures it as before: the building found, its stories counted (the Stories row is not "not
   checked"); one house has no Main building line (that line is for several buildings), and a picked floor's name is
   "the starting house".
3. The note: the panel's Starting house fact says the largest house that complies even if the tax-map lines are
   2'-0" off, what limited it with its number, and Use my survey… for the full size.
4. The envelope drawn is the cautious one: its outline at the base 2'-0" inside the buildable outline as drawn
   (the dashed curve on Gordium::Envelope).
5. Hide starting house hides every floor's sublayer (each set, not left to the parent); showing it shows
   them; none is left locked.
Writes <temp>/gordium_massing/out.json and a Perspective capture; closes its document."""
import json
import os
import sys
import tempfile
import traceback

import Rhino
import scriptcontext as sc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402
from test_docs_in_rhino import look_up_106  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_massing") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S, exist_ok=True)
log = {"claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def fresh_module():
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
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


doc = None
try:
    g = fresh_module()
    doc = TestDocs("massing").__enter__().open("Large Objects - Feet")
    look_up_106(g, g.gordium_check)                      # GordiumStart: 106 Ithaca Rd looked up (recorded)
    k = 1.0 / g._scale(doc)
    house = list(g._buildings(doc))
    layers = sorted((doc.Layers[o.Attributes.LayerIndex].FullPath, o.Attributes.Name) for o in house)
    log["floors"] = layers
    stories = len(house)
    claim("1 each floor block on its own sublayer Gordium::Massing::Floor N, named Floor N",
          stories >= 1 and layers == [(g.logic.massing_floor(n), "Floor " + str(n)) for n in range(1, stories + 1)],
          layers)
    groups = {tuple(o.Attributes.GetGroupList() or []) for o in house}
    claim("1 the house one group (a Move moves it whole)", len(groups) == 1 and list(groups)[0], [list(x) for x in groups])
    claim("1 Gordium::Massing::Roof made", doc.Layers.FindByFullPath(g.logic.MASSING_ROOF, -1) >= 0)
    items = {i["name"]: i for i in (g.STATE.get("last") or {}).get("items", [])}
    stories_row = next((i for n, i in items.items() if n.lower().startswith("stories")), None)
    log["stories_row"] = stories_row
    claim("2 the check measures it: the stories counted from the floors on their sublayers",
          stories_row is not None and str(stories) in str(stories_row.get("proposed")), stories_row)
    main = (g.STATE.get("last") or {}).get("header") or {}
    log["header"] = main
    # The name is the Main building line's, shown only when the file has several buildings (present.header: "Main
    # building: <name>" needs facts.main_building); with one house the panel has no such line. So: one house, no
    # line (not a stray "Main building: not picked yet"), and the name a picked house would carry is this house's.
    first = house[0]
    claim("2 one house: the panel has no Main building line; if one were picked it is named 'the starting house'",
          not main.get("main") and g.logic.building_name(doc.Layers[first.Attributes.LayerIndex].FullPath,
                                                         first.Attributes.Name, True) == "the starting house",
          [main.get("main"), doc.Layers[first.Attributes.LayerIndex].FullPath])
    note = (g.fact_sources(doc).get("starting_house") or {}).get("value") or ""
    log["note"] = note
    claim("3 the note: the largest house that complies even if the tax-map lines are 2'-0\" off, what limited it, "
          "and Use my survey… for the full size",
          "largest house that complies even if the tax-map lines are 2'-0\" off" in note and "limited by " in note
          and "Use my survey… for the full size" in note, note)
    o = g.overlay()
    env = (g.STATE.get("last") or {}).get("envelope") or {}
    base = o.envelope_lines[0] if o.envelope_lines else None
    if base is not None and env.get("outline"):
        import Rhino.Geometry as rg
        drawn = rg.PolylineCurve([g._model_point(doc, p, 0) for p in env["outline"] + env["outline"][:1]])
        gaps = []
        for p in base:
            q = rg.Point3d(p.X, p.Y, 0)
            ok, t = drawn.ClosestPoint(q)
            gaps.append(round(q.DistanceTo(drawn.PointAt(t)) / k, 3))
        log["envelope_gaps_ft"] = gaps
        claim("4 the envelope drawn is the cautious one: 2'-0\" inside the buildable outline as drawn",
              gaps and all(abs(x - 2.0) <= 0.05 for x in gaps), gaps)
    else:
        claim("4 the envelope drawn is the cautious one", False, {"lines": bool(base), "outline": bool(env.get("outline"))})
    floor_layers = [doc.Layers[doc.Layers.FindByFullPath(g.logic.massing_floor(n), -1)] for n in range(1, stories + 1)]
    g.hide_massing(True)
    off = [layer.IsVisible for layer in floor_layers]
    g.hide_massing(False)
    on = [layer.IsVisible for layer in floor_layers]
    unlocked = [not layer.IsLocked for layer in floor_layers]       # still the architect's to edit
    claim("5 Hide starting house hides every floor's sublayer, showing it shows them, none left locked",
          floor_layers and not any(off) and all(on) and all(unlocked), {"off": off, "on": on, "unlocked": unlocked})
    view = doc.Views.Find("Perspective", False)
    view.ActiveViewport.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    view.Redraw()
    view.CaptureToBitmap(view.ActiveViewport.Size).Save(S + "perspective.png")
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["passed"] = sum(c["ok"] for c in log["claims"].values())
    log["ok"] = bool(log["claims"]) and log["passed"] == len(log["claims"]) and "trace" not in log
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    if doc is not None:
        close(doc)
print("massing_in_rhino: %d of %d claims pass%s" % (log["passed"], len(log["claims"]),
                                                   "" if "trace" not in log else " (stopped: see trace)"))
assert log["ok"], [n for n, c in log["claims"].items() if not c["ok"]] or log.get("trace")
