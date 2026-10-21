#! python3
"""The context map in Rhino 8 (the neighbourhood around a looked-up lot). Run in Rhino, not in CI.

A fresh document from Rhino's feet template; GordiumStart with 106 Ithaca Rd typed and Look up pressed (recorded
answers by default, the live services with sc.sticky["gordium_context_live"] = True); then records: the context
layers (locked, grey, visible), how many objects each holds and every object's source, the live footprints on
screen, how long the neighbourhood took, the check's summary (it must be what it is without the context), the
panel tick off and on again, and what a saved copy of the file holds (read back with File3dm: no object, user
text or document string from a store: none source); then a second address (Edit site…, 109 Ithaca Rd) and what is
left of the first neighbourhood. Each claim is asserted (the run fails loudly otherwise). Writes
<temp>/gordium_context/out.json and frames/*.png (Top and Perspective); closes its documents (keep another
document open while it runs)."""
import json
import os
import sys
import tempfile
import time
import traceback

import Rhino
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, close  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_context") + "/"
FRAMES = S + "frames/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.makedirs(FRAMES, exist_ok=True)
LIVE = bool(sc.sticky.pop("gordium_context_live", False))
ADDRESS, FIXTURE = "106 Ithaca Rd, Ithaca, NY 14850", "106_ithaca_rd"
log = {"live": LIVE, "claims": {}}


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


def context_layers(g, doc):
    out = {}
    for i in g._context_layer_indexes(doc):
        layer = doc.Layers[i]
        objs = list(doc.Objects.FindByLayer(layer) or [])
        out[layer.FullPath] = {"locked": layer.IsLocked, "visible": layer.IsVisible, "objects": len(objs),
                               "colour": (layer.Color.R, layer.Color.G, layer.Color.B),
                               "names": sorted({o.Attributes.Name or "" for o in objs})[:12],
                               "texts": sorted({getattr(o.Geometry, "Text", "") or "" for o in objs})[:12],
                               "sources": sorted({o.Attributes.GetUserString(g.logic.CONTEXT_KEY) or "" for o in objs})}
    return out


def notes_inside_square(g, doc):
    """Every object on the Notes layer, besides the square itself, measured inside the square: the corners of its
    bounding box in its own plane (a text's plane, turned with the square; the world's for the rest), each tested
    against the square's curve. A world-aligned box of a turned text would poke past a turned square's edge."""
    rg = Rhino.Geometry
    index = next(i for i in g._context_layer_indexes(doc) if doc.Layers[i].FullPath.endswith("::Notes"))
    objs = list(doc.Objects.FindByLayer(doc.Layers[index]) or [])
    square = next(o for o in objs if (o.Attributes.Name or "").startswith("Context square"))
    outside, longest, kind = [], 0, None
    for o in objs:
        if o.Id == square.Id:
            continue
        geom = o.Geometry
        plane = geom.Plane if isinstance(geom, rg.TextEntity) else rg.Plane.WorldXY
        box = geom.GetBoundingBox(plane)
        for c in list(box.GetCorners())[:4]:
            pt = plane.PointAt(c.X, c.Y)
            if square.Geometry.Contains(rg.Point3d(pt.X, pt.Y, 0), rg.Plane.WorldXY,
                                        doc.ModelAbsoluteTolerance) != rg.PointContainment.Inside:
                outside.append(o.Attributes.Name or type(geom).__name__)
                break
        if (o.Attributes.Name or "") == "Sources":
            kind = type(geom).__name__
            text = getattr(geom, "PlainText", None) or getattr(geom, "Text", "") or ""
            longest = max(len(line) for line in text.splitlines()) if text else 0
    return {"outside": outside, "longest_line": longest, "sources_kind": kind, "notes": len(objs)}


docs = TestDocs("context").__enter__()
opened = []
try:
    g = fresh_module()
    doc = docs.open("Large Objects - Feet")
    opened.append(doc)
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": ADDRESS}, lookup_fixture=None if LIVE else FIXTURE)
    said_before = len(g.STATE.get("said", []))
    started = time.time()
    g.gordium_check()                                  # an empty file: GordiumStart with the lookup, then the context
    log["start_seconds"] = round(time.time() - started, 2)
    log["said"] = g.STATE.get("said", [])[said_before:]
    log["layers"] = context_layers(g, doc)
    guides = g.STATE.get("context_guides") or {}
    log["footprints_on_screen"] = len(guides.get("lines") or [])
    last = g.STATE.get("last") or {}
    log["summary"] = last.get("view_summary")
    log["items"] = [(i["name"], i["status"], i["proposed"]) for i in last.get("items", [])]
    lots, buildings, problems = g._sorted_objects(doc)
    log["checker_sees"] = {"lot_candidates": len(lots), "buildings": len(buildings), "problems": problems}
    t = time.time()
    payload = g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))      # drawn again: replaces, never doubles
    log["redraw_seconds"] = round(time.time() - t, 2)
    log["counts"] = (payload or {}).get("counts")
    log["layers_after_redraw"] = context_layers(g, doc)
    layers = log["layers"]
    sub = {k.split("::")[-1]: v for k, v in layers.items() if k.count("::") >= 2}
    claim("1 the neighbourhood is drawn on its own locked, grey layers: parcels, streets, notes",
          set(sub) >= {"Parcels", "Streets", "Notes"} and all(sub[n]["objects"] > 0 for n in ("Parcels", "Streets", "Notes"))
          and all(v["locked"] and v["visible"] and v["colour"] == g.CONTEXT_GREYS[n] for n, v in sub.items()
                  if n in g.CONTEXT_GREYS), sub)
    notes = " ".join(sub["Notes"]["names"] + sub["Notes"]["texts"]).lower()
    claim("1 the notes: a north arrow, a scale bar and the sources",
          "north" in notes and "scale" in notes and "source" in notes, sub["Notes"])
    log["notes_inside"] = notes_inside_square(g, doc)
    claim("1 every note lies inside the neighbourhood square (the sources wrapped, at most 60 characters a line)",
          not log["notes_inside"]["outside"] and log["notes_inside"]["longest_line"] <= g.logic.NOTE_WIDTH
          and log["notes_inside"]["sources_kind"] == "TextEntity", log["notes_inside"])
    claim("2 the building footprints are on screen (live: claim 5 checks they are never saved)",
          log["footprints_on_screen"] > 0, {"on_screen": log["footprints_on_screen"]})
    claim("3 the checker never measures the context: one lot", log["checker_sees"]["lot_candidates"] == 1,
          log["checker_sees"])
    with_context = log["summary"]
    g._clear_context(doc)
    g.run_check(doc, report=False)
    without = (g.STATE.get("last") or {}).get("view_summary")
    log["summary_without_context"] = without
    claim("3 the check is the same with and without the neighbourhood", with_context and with_context == without,
          {"with": with_context, "without": without})
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    claim("3 drawn again it replaces, never doubles",
          {k: v["objects"] for k, v in context_layers(g, doc).items()} == {k: v["objects"] for k, v in layers.items()},
          {"first": {k: v["objects"] for k, v in layers.items()},
           "again": {k: v["objects"] for k, v in context_layers(g, doc).items()}})
    for name in ("Top", "Perspective"):
        view = doc.Views.Find(name, False) or doc.Views.ActiveView
        doc.Views.ActiveView = view
        box = guides.get("box")
        if name == "Top" and box is not None and box.IsValid:
            view.ActiveViewport.ZoomBoundingBox(box)
        else:
            view.ActiveViewport.ZoomExtents()
        view.Redraw()
        bmp = view.CaptureToBitmap(System.Drawing.Size(1000, 760))
        if bmp is not None:
            bmp.Save(FRAMES + "106_context_%s.png" % name.lower())
    g.show_context(False)
    log["tick_off"] = context_layers(g, doc)
    g.show_context(True)
    log["tick_on"] = context_layers(g, doc)
    claim("4 the panel tick hides it and shows it again",
          all(not v["visible"] for v in log["tick_off"].values()) and all(v["visible"] for v in log["tick_on"].values()),
          {"off": {k: v["visible"] for k, v in log["tick_off"].items()},
           "on": {k: v["visible"] for k, v in log["tick_on"].items()}})
    path = S + "saved.3dm"
    doc.Export(path)
    f = Rhino.FileIO.File3dm.Read(path)
    stored = []
    for o in f.Objects:
        stored.append(o.Attributes.GetUserString(g.logic.CONTEXT_KEY) or "")
    log["saved_sources"] = sorted(set(stored))
    log["saved_strings"] = [f.Strings.GetKey(i) for i in range(f.Strings.Count)]
    blob = json.dumps([f.Strings.GetValue(i) for i in range(f.Strings.Count)])
    log["saved_has_footprints"] = "state_buildings" in set(stored) or "2014" in blob
    claim("5 a saved file keeps no live-only (store: none) source", not log["saved_has_footprints"],
          log["saved_sources"])
    # a second address: Edit site…, 109 Ithaca Rd looked up (recorded); the first neighbourhood must go
    first_frame = (g._context_record(doc) or {}).get("frame")
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": "109 Ithaca Rd, Ithaca, NY 14850"},
                   lookup_fixture=None if LIVE else "109_ithaca_rd", auto_ok=True)
    g.edit_facts()
    second_frame = (g._context_record(doc) or {}).get("frame")
    left = context_layers(g, doc)
    log["after_second"] = {"frame_changed": second_frame != first_frame, "layers": left,
                           "said": g.STATE.get("said", [])[-4:]}
    first_parcel = (first_frame or {}).get("parcel_id")
    claim("6 a second address clears the first neighbourhood",
          second_frame != first_frame and not any(first_parcel and first_parcel in " ".join(v["names"])
                                                  for v in left.values())
          and sum(v["objects"] for v in left.values()) != sum(v["objects"] for v in layers.values()),
          log["after_second"])
    log["ok"] = all(c["ok"] for c in log["claims"].values())
except Exception:
    log["trace"] = traceback.format_exc()
    raise
finally:
    for d in opened:
        try:
            close(d)
        except Exception:
            pass
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
    json.dump({"ready": True}, open(S + "ready.json", "w", encoding="utf-8"))
