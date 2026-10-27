#! python3
"""Demo 6 quick check: for R-2a and R-3b, GordiumStart on an empty file with the start box set to that district
(box_overrides), Draw (the starting house), Check; the occupancy / home occupation rows need review."""
import json, os, sys, tempfile, time, traceback
import Rhino, scriptcontext as sc, System
WT = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/demo6_rhino_fd924dd"
OUT = os.path.join(tempfile.gettempdir(), "gordium_demo6_districts") + "/"
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402
log = {"claims": {}, "runs": {}}

def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}

def settle(g):
    end = time.time() + 60
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        if not g.STATE.get("dirty") and not g.STATE.get("running") and g.STATE.get("asking") is None:
            break
        time.sleep(0.1)

try:
    import AppKit
    AppKit.NSApplication.SharedApplication.ActivateIgnoringOtherApps(True)
    state = sc.sticky.setdefault("gordium_state", {})
    loaded = sys.modules.get("gordium_rhino")
    if loaded is not None:
        try: loaded.off()
        except Exception: pass
    w = state.pop("worker", None)
    if w is not None:
        w.terminate()
    for name in ("gordium_rhino", "rhino_logic", "gordium_ui"):
        sys.modules.pop(name, None)
    state.clear()
    state.update({"repo": WT, "extra_paths": [], "auto_ok": True})
    app = WT + "/apps/rhino_plugin"
    if app in sys.path: sys.path.remove(app)
    sys.path.insert(0, app)
    import gordium_rhino as g
    for zone in ("R-2a", "R-3b"):
        doc = TestDocs("demo6_" + zone).open("Large Objects - Feet")
        try:
            shown = {}
            g.STATE["box_overrides"] = {"zone": zone}
            g.STATE["on_confirm"] = lambda d, f, desc, st: shown.update(zone=st.get("zone"), use=st.get("use"))
            t0 = time.time()
            g.gordium_start()
            settle(g)
            facts = g.current_facts(doc)
            house = list(g._buildings(doc))
            g._actions()["check"]()          # the panel's Check button
            settle(g)
            items = g.STATE["panel_parts"]["view"]["items"]
            rows = [{"name": i["name"], "status": i["status"], "id": i.get("id"), "needs": i.get("needs"),
                     "reason": (i.get("reason") or "")[:160]} for i in items]
            occ = [r for r in rows if any(k in (r["id"] or "") + r["name"].lower() for k in
                                          ("occupan", "unrelated", "home_occ", "home occ", "household", "family unit"))]
            log["runs"][zone] = {"seconds": round(time.time() - t0, 1), "zone_saved": facts.get("zone"),
                                 "house_parts": len(house), "summary": g.STATE["panel_parts"]["view"].get("summary"),
                                 "occupancy_rows": occ, "rows": rows}
            claim(zone + ": Draw drew the starting house in " + zone, facts.get("zone") == zone and house,
                  {"zone": facts.get("zone"), "parts": len(house)})
            claim(zone + ": occupancy / home occupation rows present", len(occ) > 0, [r["name"] for r in occ])
            claim(zone + ": every one of them needs review (never complies)",
                  occ and all(r["status"] == "needs_review" for r in occ), [(r["name"], r["status"]) for r in occ])
            try:
                view = doc.Views.Find("Top", False); doc.Views.ActiveView = view
                view.ActiveViewport.ZoomBoundingBox(doc.Objects.BoundingBox); view.Redraw(); Rhino.RhinoApp.Wait()
                view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(OUT + zone + "_top.png")
            except Exception:
                pass
        finally:
            g.STATE.pop("box_overrides", None)
            close(doc)
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    log["done"] = True
    json.dump(log, open(OUT + "out.json", "w", encoding="utf-8"), default=str, indent=1)
