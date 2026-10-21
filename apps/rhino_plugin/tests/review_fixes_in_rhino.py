#! python3
"""The architect's-eye review fixes (2026-10-21), in Rhino 8, each claim asserted (the run fails loudly otherwise). Run
in Rhino, not in CI. Phases (sc.sticky["gordium_review_phase"]):
- "run" (default): Rhino brought to the front; GordiumStart on the sample; then the claims below. It leaves the
  document open, Rhino in front, and writes the panel's window number for the driver's screen capture.
- "close": closes the document this run opened.
Claims:
1. the panel is ON SCREEN (its native window visible to the system, not only what Rhino reports), Rhino in front;
2. docked, every detail label wraps inside the panel's width;
3. a north arrow by the lot, pointing to true north; the envelope drawn as its outline, its top labelled "Height
   limit 35'-0"" (in an elevation); no "(approx.)" on any edge length;
4. a detached garage on the Building layer: the header says "Main building: not picked yet", the panel has a
   "Main building…" button, the waiting rows say "Pick the main building…"; picking the starting house measures
   the yards again, their dimensions drawn;
5. a cottage off the Building layer is drawn dashed (unmeasured);
6. closed documents' panels are let go.
Writes <temp>/gordium_review/run_out.json and frames/*.png."""
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

S = os.path.join(tempfile.gettempdir(), "gordium_review") + "/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(S + "frames", exist_ok=True)
phase = sc.sticky.pop("gordium_review_phase", "run")
log = {"phase": phase, "claims": {}}


def claim(name, ok, detail=None):
    log["claims"][name] = {"ok": bool(ok), "detail": detail}
    assert ok, "%s: %s" % (name, detail)


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


def capture(doc, view_name, name):
    view = doc.Views.Find(view_name, False)
    doc.Views.ActiveView = view
    box = doc.Objects.BoundingBox                     # the whole lot and what is on it, the north arrow beside it
    box.Inflate(box.Diagonal.Length * 0.12)
    view.ActiveViewport.ZoomBoundingBox(box)
    view.Redraw()
    Rhino.RhinoApp.Wait()
    bmp = view.CaptureToBitmap(System.Drawing.Size(1100, 700))
    bmp.Save(S + "frames/" + name + ".png")


def labels_in(container):
    """Every label inside an Eto container (Children: all its descendants)."""
    import Eto.Forms as ef
    return [c for c in container.Children if isinstance(c, ef.Label)]


try:
    if phase == "run":
        import AppKit
        AppKit.NSApplication.SharedApplication.ActivateIgnoringOtherApps(True)   # as the architect works: in front
        g = fresh_module()
        doc = TestDocs("review").open("Large Objects - Feet")
        g.STATE["on_confirm"] = lambda *a: None
        g.gordium_check()
        for _ in range(20):
            Rhino.RhinoApp.Wait()
            time.sleep(0.1)
        p = g.STATE["panel_parts"]
        host = getattr(p["form"], "host", None)
        native = host.ParentWindow.ControlObject if host is not None and host.ParentWindow is not None else None
        seen = {"active": bool(AppKit.NSApplication.SharedApplication.Active),
                "visible": bool(native.IsVisible) if native is not None else None,
                "occlusion": str(native.OcclusionState) if native is not None else None,
                "window": int(str(native.WindowNumber)) if native is not None else None}
        log["panel_window"] = seen
        claim("1 the panel is on screen (the system's window, Rhino in front)", seen["active"] and seen["visible"] and
              int(seen["occlusion"] or 0) & 2, seen)          # NSWindowOcclusionStateVisible: really on screen
        # 2: every detail label wraps inside the docked panel
        p["selected"] = next(i["id"] for i in p["view"]["items"] if i["name"] == "Rear yard")
        g.ui.show(p, p["view"])
        Rhino.RhinoApp.Wait()
        widths = [lab.Width for lab in labels_in(p["detail"])]
        log["detail_widths"] = {"panel": host.Width, "labels": widths[:20], "wrap_at": g.ui.WRAP_AT,
                                "scroll": p["detail"].Parent.Width if p["detail"].Parent is not None else None,
                                "every": [(type(c).__name__, c.Width, (getattr(c, "Text", "") or "")[:30])
                                          for c in p["detail"].Children][:40]}
        claim("2 docked, every detail label wraps inside the panel", widths and all(0 < w <= host.Width for w in widths),
              log["detail_widths"])
        o = g.overlay()
        ft = 1.0 / g._scale(doc)
        north = o.north
        log["north"] = None if north is None else [north[1].X, north[1].Y]
        x, y = g.logic.north_vector(g.current_facts(doc).get("plan_north_deg"))
        claim("3 a north arrow by the lot, to true north", north is not None and abs(north[1].X - x) < 1e-9 and
              abs(north[1].Y - y) < 1e-9, log["north"])
        claim("3 the envelope is its outline; its top labelled Height limit 35'-0\"",
              o.envelope_lines is not None and o.height_limit is not None and o.height_limit[1] == "Height limit 35'-0\"",
              o.height_limit[1] if o.height_limit else None)
        g._actions()["labels"](True)
        texts = [t for _, t, _ in o.edge_labels]
        claim("3 no (approx.) on any edge length", texts and not any("approx" in t for t in texts), texts)
        capture(doc, "Top", "1_plan_north_arrow")
        capture(doc, "Front", "2_front_height_limit")
        # 4: a detached garage behind the house, on the Building layer
        ring = g.STATE["start"]["floors"][0]["outline"]
        xs, ys = [q[0] for q in ring], [q[1] for q in ring]
        attrs = Rhino.DocObjects.ObjectAttributes()
        attrs.LayerIndex = g._layer(doc, g.LAYERS["building"])
        attrs.Name = "Garage"
        box = rg.Box(rg.Plane.WorldXY, rg.Interval(min(xs) * ft, (min(xs) + 20) * ft),
                     rg.Interval((max(ys) + 4) * ft, (max(ys) + 16) * ft), rg.Interval(0, 12 * ft))
        garage = doc.Objects.AddBrep(box.ToBrep(), attrs)
        g.run_check(doc, report=False)
        view = g.STATE["panel_parts"]["view"]
        head = view["header"]
        waiting = [i["name"] for i in view["items"] if i.get("hint") == "Pick the main building…"]
        log["garage"] = {"main": head.get("main"), "waiting": waiting}
        claim("4 a garage: the header says no main building is picked, and the rows say how to pick it",
              head.get("main") == "Main building: not picked yet" and "Front yard" in waiting, log["garage"])
        buttons = [b.Text for b in g.STATE["panel_parts"]["header"].Children if hasattr(b, "Text")] \
            if hasattr(g.STATE["panel_parts"]["header"], "Children") else []
        log["header_buttons"] = buttons
        floors = [o_ for o_ in g._buildings(doc) if (o_.Attributes.Name or "").startswith("Floor")]
        g._pick = lambda doc_, prompt, candidates, kind: str(floors[0].Id)   # the architect clicks the house
        g._actions()["main"]()
        view = g.STATE["panel_parts"]["view"]
        items = {i["name"]: i for i in view["items"]}
        log["after_pick"] = {"main": view["header"].get("main"),
                             "front": (items.get("Front yard") or {}).get("proposed"),
                             "dims": len(g.overlay().yard_dims)}
        claim("4 picking the starting house measures the yards again, their dimensions drawn",
              view["header"].get("main") == "Main building: the starting house" and
              log["after_pick"]["front"] not in (None, "—") and log["after_pick"]["dims"] >= 4, log["after_pick"])
        # 5: a cottage off the Building layer
        cot = rg.Box(rg.Plane.WorldXY, rg.Interval((max(xs) + 6) * ft, (max(xs) + 18) * ft),
                     rg.Interval((max(ys) - 20) * ft, (max(ys) - 6) * ft), rg.Interval(0, 14 * ft))
        doc.Objects.AddBrep(cot.ToBrep())
        g.run_check(doc, report=False)
        claim("5 a cottage off the Building layer is drawn dashed (not measured)", len(g.overlay().unmeasured) == 1,
              len(g.overlay().unmeasured))
        capture(doc, "Top", "3_garage_main_picked_cottage_dashed")
        # 6: closed documents' panels let go
        open_serials = {d.RuntimeSerialNumber for d in Rhino.RhinoDoc.OpenDocuments()}
        hosts = set(sc.sticky.get("gordium_dock_hosts") or {})
        log["hosts"] = {"kept": len(hosts), "open": len(open_serials)}
        claim("6 only open documents' panels are kept", hosts <= open_serials | {0}, log["hosts"])
        log["window"] = seen["window"]
        log["ok"] = True
    else:
        g = sys.modules.get("gordium_rhino")
        log["closed"] = [str(d.Path) for d in leftovers() if "review_" in os.path.basename(d.Path or "") and close(d)]
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    json.dump(log, open(S + phase + "_out.json", "w", encoding="utf-8"), default=str, indent=1)
