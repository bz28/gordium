#! python3
"""Demo smoke (origin/demo (sixth update), loaded from its extracted copy): GordiumStart on an empty file -> the sample lot
-> Draw -> the starting house -> the house moved 5 ft toward the street (the front yard fails) -> Zoning report…
(written; its workbook opens on the Check sheet). Phase in sticky["demo_smoke_phase"]: "run" (default) or "close".
Writes <temp>/gordium_demo_smoke/{run,close}.json and *_view.png; ready.json for the driver's window captures."""
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

WT = open("/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/624e933b-7d2e-463f-9744-6e95edbe5cbe/scratchpad/demo6_runs/smoke/wt.txt", encoding="utf-8").read().strip()
OUT = os.path.join(tempfile.gettempdir(), "gordium_demo_smoke") + "/"
os.makedirs(OUT, exist_ok=True)
phase = sc.sticky.pop("demo_smoke_phase", "run")
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close, leftovers  # noqa: E402

log = {"phase": phase, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    box = doc.Objects.BoundingBox
    box.Inflate(box.Diagonal.Length * 0.12)
    view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    Rhino.RhinoApp.Wait()
    view.CaptureToBitmap(System.Drawing.Size(1000, 640)).Save(OUT + name + "_view.png")


def settle(g):
    end = time.time() + 20
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        if not g.STATE.get("dirty") and not g.STATE.get("running"):
            break
        time.sleep(0.1)


try:
    if phase == "run":
        import AppKit
        AppKit.NSApplication.SharedApplication.ActivateIgnoringOtherApps(True)
        loaded = sys.modules.get("gordium_rhino")
        if loaded is not None:
            try:
                loaded.off()
            except Exception:
                pass
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
        log["loaded_from"] = g.__file__
        claim("0 Gordium loaded from the demo copy", g.__file__.startswith(WT), g.__file__)
        doc = TestDocs("demo_smoke").open("Large Objects - Feet")      # an empty file
        claim("1 the file starts empty", doc.Objects.Count == 0, doc.Objects.Count)
        g.STATE["on_confirm"] = lambda *a: None
        g.gordium_start() if hasattr(g, "gordium_start") else g.gordium_check()   # GordiumStart: the sample, Draw
        settle(g)
        start = g.STATE.get("start") or {}
        house = [o for o in g._buildings(doc)]
        log["after_draw"] = {"objects": doc.Objects.Count, "house_parts": len(house),
                             "floors": len(start.get("floors") or [])}
        claim("2 Draw puts down the sample lot and the starting house", house and start.get("floors"), log["after_draw"])
        items = {i["name"]: i for i in g.STATE["panel_parts"]["view"]["items"]}
        claim("2 the panel lists the rows", "Front yard" in items, sorted(items)[:12])
        capture(doc, "Perspective", "1_drawn")
        before = items["Front yard"]["status"]
        ft = 1.0 / g._scale(doc)
        xform = rg.Transform.Translation(rg.Vector3d(0, -5 * ft, 0))   # the street side is along the bottom
        for o in house:
            doc.Objects.Transform(o.Id, xform, True)
        settle(g)
        g.run_check(doc, report=False)
        settle(g)
        items = {i["name"]: i for i in g.STATE["panel_parts"]["view"]["items"]}
        fy = items["Front yard"]
        log["front"] = {"before": before, "after": fy["status"], "reason": fy.get("reason"), "hint": fy.get("hint"),
                        "proposed": fy.get("proposed"), "required": fy.get("required")}
        claim("3 moved 5 ft toward the street, the front yard fails", fy["status"] == "does_not_comply", log["front"])
        p = g.STATE["panel_parts"]
        p["selected"] = fy["id"]
        g.ui.show(p, p["view"])
        Rhino.RhinoApp.Wait()
        capture(doc, "Top", "2_front_yard_fails")
        opened = []
        real_sub = g.subprocess

        class Recorded:                                  # `open <report>` recorded, not launched on Ben's screen;
            def __getattr__(self, name):                 # every other call as it is
                return getattr(real_sub, name)

            def run(self, args, *a, **k):
                if list(args)[:1] == ["open"]:
                    opened.append(args[1])
                    import types
                    return types.SimpleNamespace(returncode=0, stderr="", stdout="")
                return real_sub.run(args, *a, **k)

        g.subprocess = Recorded()
        real_spawn = getattr(g.ui, "spawn", None)        # later heads open through ui.spawn (no console on Windows)

        def spawn(args, run=False, **k):
            if list(args)[:1] == ["open"]:
                opened.append(args[1])
                import types
                return types.SimpleNamespace(returncode=0, stderr="", stdout="")
            return real_spawn(args, run, **k)

        if real_spawn is not None:
            g.ui.spawn = spawn
        try:
            g._actions()["report"]()
            settle(g)
        finally:
            g.subprocess = real_sub
            if real_spawn is not None:
                g.ui.spawn = real_spawn
        log["report"] = {"opened": opened, "said": (g.STATE.get("said") or [])[-3:]}
        path = next((x for x in opened if str(x).endswith(".xlsx")), None)
        sheet = None
        if path and os.path.exists(path):
            import zipfile
            import re
            with zipfile.ZipFile(path) as z:
                wb = z.read("xl/workbook.xml").decode("utf-8")
            names = re.findall(r'<sheet [^>]*name="([^"]+)"', wb)
            active = re.search(r'activeTab="(\d+)"', wb)
            sheet = names[int(active.group(1)) if active else 0] if names else None
            log["report"].update(sheets=names, active=sheet)
        claim("4 Zoning report… writes the workbook and opens it", bool(path and os.path.exists(path)), log["report"])
        claim("4 it opens on the Check sheet", sheet == "Check", sheet)
        log["ok"] = all(c["ok"] for c in log["claims"].values())
    else:
        log["closed"] = [str(d.Path) for d in leftovers() if "demo_smoke" in os.path.basename(d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    json.dump(log, open(OUT + phase + ".json", "w", encoding="utf-8"), default=str, indent=1)
    json.dump({"at": time.time(), "phase": phase}, open(OUT + "ready.json", "w", encoding="utf-8"))
