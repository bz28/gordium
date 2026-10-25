#! python3
"""The context map in Rhino 8 (the neighbourhood around a looked-up lot). Run in Rhino, not in CI.

A fresh document from Rhino's feet template; GordiumStart with 106 Ithaca Rd typed and Look up pressed (recorded
answers by default, the live services with sc.sticky["gordium_context_live"] = True); then records: the context
layers (grey, visible, locked but for the footprints), how many objects each holds and every object's source, the
footprints as real editable outlines (Ben, 2026-10-21), how long the neighbourhood took, the check's summary (it must
be what it is without the context), a footprint the architect drags (kept as theirs, never drawn twice), a solid
on the neighbourhood layers over the lot (said, never measured), the panel tick off and on again, and what a saved
copy of the file holds (read back with File3dm: the footprints, their credit and date); then a second address
(Edit site…, 109 Ithaca Rd) and what is left of the first neighbourhood. Each claim is asserted (the run fails loudly otherwise). Writes
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


def _own_box(geom):
    """A text's box on its own axes: a copy turned from its plane onto the world's, boxed, then its corners put back
    (GetBoundingBox(geom.Plane) on turned text is no box of the letters: 116 x 113 ft for the 94 x 23 ft Sources
    note at 306 degrees, Rhino job's probe 2026-10-21)."""
    rg = Rhino.Geometry
    flat = geom.Duplicate()
    flat.Transform(rg.Transform.ChangeBasis(rg.Plane.WorldXY, geom.Plane))
    box = flat.GetBoundingBox(True)
    return box, [geom.Plane.PointAt(c.X, c.Y) for c in list(box.GetCorners())[:4]]


def footprints(g, doc, every=False):
    """The footprint outlines on the Buildings layer: Gordium's (with its source mark), or every one (edited too)."""
    index = doc.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    objs = list(doc.Objects.FindByLayer(doc.Layers[index]) or []) if index >= 0 else []
    objs = [o for o in objs if isinstance(o.Geometry, Rhino.Geometry.Curve)]
    return objs if every else [o for o in objs if o.Attributes.GetUserString(g.logic.CONTEXT_KEY)]


def notes_inside_square(g, doc):
    """Every object on the Notes layer, besides the square itself, measured inside the square by its own points: a
    text by the corners of its box in its own plane (turned with the square), a curve by its vertices, a dot by its
    point, each tested against the square's curve. (A world-aligned bounding box of a turned object pokes past a
    turned square's edge: the first run failed the scale bar that way.) Also the sources note's line height, feet."""
    rg = Rhino.Geometry
    index = next(i for i in g._context_layer_indexes(doc) if doc.Layers[i].FullPath.endswith("::Notes"))
    objs = list(doc.Objects.FindByLayer(doc.Layers[index]) or [])
    square = next(o for o in objs if (o.Attributes.Name or "").startswith("Context square"))
    outside, longest, kind, line_ft, dim_scale, text_ft = [], 0, None, None, None, None
    for o in objs:
        if o.Id == square.Id:
            continue
        geom = o.Geometry
        if isinstance(geom, rg.TextEntity):
            box, pts = _own_box(geom)
        elif isinstance(geom, rg.TextDot):
            pts = [geom.Point]
        else:
            ok, polyline = geom.TryGetPolyline()
            pts = list(polyline) if ok else [geom.PointAtStart, geom.PointAtEnd]
        if any(square.Geometry.Contains(rg.Point3d(p.X, p.Y, 0), rg.Plane.WorldXY, doc.ModelAbsoluteTolerance)
               != rg.PointContainment.Inside for p in pts):
            outside.append(o.Attributes.Name or type(geom).__name__)
        if (o.Attributes.Name or "") == "Sources":
            kind = type(geom).__name__
            text = getattr(geom, "PlainText", None) or getattr(geom, "Text", "") or ""
            lines = text.splitlines()
            longest = max(len(line) for line in lines) if lines else 0
            if isinstance(geom, rg.TextEntity) and lines:
                # as displayed: a bounding box is the unscaled text; with annotation scaling on, Rhino draws it at
                # the text's DimensionScale times that (the Rhino job's probe: the template's 12 made ~30 ft letters)
                box = _own_box(geom)[0]
                scaling = bool(getattr(doc, "ModelSpaceAnnotationScalingEnabled", False))
                shown = geom.DimensionScale if scaling else 1.0
                line_ft = round(g._feet_length(doc, box.Max.Y - box.Min.Y) * shown / len(lines), 2)
                dim_scale, text_ft = geom.DimensionScale, round(g._feet_length(doc, geom.TextHeight), 3)
    return {"outside": outside, "longest_line": longest, "sources_kind": kind, "line_height_ft": line_ft,
            "dimension_scale": dim_scale, "text_height_ft": text_ft, "notes": len(objs)}


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
    claim("1 the neighbourhood is drawn on its own grey layers, locked but for the footprints",
          set(sub) >= {"Parcels", "Streets", "Buildings", "Notes"}
          and all(sub[n]["objects"] > 0 for n in ("Parcels", "Streets", "Buildings", "Notes"))
          and all(v["locked"] == g.logic.context_locked(k) and v["visible"]
                  and v["colour"] == g.CONTEXT_GREYS[k.split("::")[-1]] for k, v in layers.items()
                  if k.split("::")[-1] in g.CONTEXT_GREYS), sub)
    notes = " ".join(sub["Notes"]["names"] + sub["Notes"]["texts"]).lower()
    claim("1 the notes: a north arrow, a scale bar and the sources",
          "north" in notes and "scale" in notes and "source" in notes, sub["Notes"])
    log["notes_inside"] = notes_inside_square(g, doc)
    claim("1 every note lies inside the neighbourhood square (the sources wrapped, at most 60 characters a line)",
          not log["notes_inside"]["outside"] and log["notes_inside"]["longest_line"] <= g.logic.NOTE_WIDTH
          and log["notes_inside"]["sources_kind"] == "TextEntity", log["notes_inside"])
    n = log["notes_inside"]
    claim("1 the sources note is small: its own scale 1, %.1f ft text, at most %.2f ft a line as displayed"
          % (g.logic.NOTE_HEIGHT_FT, g.logic.NOTE_LINE_FT),
          n["dimension_scale"] == 1.0 and n["text_height_ft"] is not None
          and abs(n["text_height_ft"] - g.logic.NOTE_HEIGHT_FT) < 0.01
          and n["line_height_ft"] is not None and 0 < n["line_height_ft"] <= g.logic.NOTE_LINE_FT + 0.01, n)
    feet = footprints(g, doc)
    parent = doc.Layers.FindByFullPath(g.logic.CONTEXT, -1)
    doc.Objects.UnselectAll()
    selectable = bool(feet) and doc.Objects.Select(feet[0].Id)       # a locked object (or locked parent) can't be
    doc.Objects.UnselectAll()
    log["footprints"] = {"outlines": len(feet), "unlocked": not sub["Buildings"]["locked"],
                         "parent_unlocked": parent >= 0 and not doc.Layers[parent].IsLocked,
                         "selectable": selectable,
                         "curves": all(isinstance(o.Geometry, Rhino.Geometry.Curve) for o in feet)}
    claim("2 the building footprints are real, editable outlines on the unlocked Buildings layer (Ben, 2026-10-21)",
          len(feet) > 0 and log["footprints"]["unlocked"] and log["footprints"]["parent_unlocked"]
          and log["footprints"]["selectable"] and log["footprints"]["curves"]
          and all(o.Attributes.GetUserString(g.logic.GEOM_KEY) and o.Attributes.GetUserString(g.logic.PIECE_KEY)
                  and o.Attributes.GetUserString(g.logic.DRAWN_KEY) == str(o.Id) for o in feet), log["footprints"])
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
    # the architect drags one footprint 10 ft; the neighbourhood is drawn again around the same lot
    feet = footprints(g, doc)
    moved, other, lifted = feet[0], feet[1], feet[2]
    moved_id, other_guid = moved.Attributes.GetUserString(g.logic.PIECE_KEY), other.Id
    lifted_id = lifted.Attributes.GetUserString(g.logic.PIECE_KEY)
    doc.Objects.Transform(moved, Rhino.Geometry.Transform.Translation(g._model_length(doc, 10.0), 0, 0), True)
    doc.Objects.Transform(lifted, Rhino.Geometry.Transform.Translation(0, 0, g._model_length(doc, 3.0)), True)  # up
    before = len(feet)
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    after = footprints(g, doc, every=True)
    kept = [o for o in after if o.Attributes.GetUserString(g.logic.PIECE_KEY) == moved_id]
    up = [o for o in after if o.Attributes.GetUserString(g.logic.PIECE_KEY) == lifted_id]
    log["edited"] = {"before": before, "after": len(after), "kept": len(kept),
                     "lifted_kept_once": len(up) == 1 and bool(up[0].Attributes.GetUserString(g.logic.EDITED_KEY)),
                     "kept_is_theirs": bool(kept) and bool(kept[0].Attributes.GetUserString(g.logic.EDITED_KEY))
                     and not kept[0].Attributes.GetUserString(g.logic.CONTEXT_KEY),
                     "unedited_replaced": doc.Objects.FindId(other_guid) is None}
    claim("3 an edited footprint stays (the architect's), is not drawn twice; the others are replaced",
          log["edited"]["kept"] == 1 and log["edited"]["kept_is_theirs"] and log["edited"]["after"] == before
          and log["edited"]["lifted_kept_once"] and log["edited"]["unedited_replaced"], log["edited"])
    # review of the editable outlines, round 2: a copy pasted in place (same points, same attributes, Gordium's keys
    # too) and a footprint whose print width the architect set are theirs: kept, the width one not drawn twice
    feet = [o for o in footprints(g, doc) if not o.Attributes.GetUserString(g.logic.EDITED_KEY)]
    source, widened = feet[0], feet[1]
    source_id = source.Attributes.GetUserString(g.logic.PIECE_KEY)
    widened_id = widened.Attributes.GetUserString(g.logic.PIECE_KEY)
    copy_guid = doc.Objects.AddCurve(source.Geometry.DuplicateCurve(), source.Attributes.Duplicate())
    wide = widened.Attributes.Duplicate()
    wide.PlotWeightSource = Rhino.DocObjects.ObjectPlotWeightSource.PlotWeightFromObject
    wide.PlotWeight = 0.35
    doc.Objects.ModifyAttributes(widened, wide, True)
    before = len(footprints(g, doc, every=True))
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    after = footprints(g, doc, every=True)
    copy = doc.Objects.FindId(copy_guid)
    log["copy_and_width"] = {
        "copy_kept_as_theirs": copy is not None and bool(copy.Attributes.GetUserString(g.logic.EDITED_KEY))
        and not copy.Attributes.GetUserString(g.logic.CONTEXT_KEY),
        "copied_one_redrawn": len([o for o in after if o.Attributes.GetUserString(g.logic.PIECE_KEY) == source_id]) == 2,
        "width_kept_once": [o.Attributes.PlotWeight for o in after
                            if o.Attributes.GetUserString(g.logic.PIECE_KEY) == widened_id] == [0.35],
        "before": before, "after": len(after)}
    claim("3 a copy pasted in place and a footprint given a print width are the architect's: kept, never doubled",
          log["copy_and_width"]["copy_kept_as_theirs"] and log["copy_and_width"]["copied_one_redrawn"]
          and log["copy_and_width"]["width_kept_once"] and log["copy_and_width"]["after"] == before,
          log["copy_and_width"])
    # a solid on the neighbourhood layers over the lot: never measured, so said
    lot = g._find(doc, g.current_facts(doc).get("lot_id") or "")
    centre = lot.Geometry.GetBoundingBox(True).Center
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = doc.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    attrs.Name = "Extruded footprint"
    k = g._model_length(doc, 5.0)
    solid = doc.Objects.AddBrep(Rhino.Geometry.Brep.CreateFromBox(Rhino.Geometry.BoundingBox(
        centre.X - k, centre.Y - k, 0, centre.X + k, centre.Y + k, 2 * k)), attrs)
    said_before = len(g.STATE.get("said", []))
    g.run_check(doc, report=False)
    log["solid_said"] = g.STATE.get("said", [])[said_before:]
    lots_now, _, _ = g._sorted_objects(doc)
    last = g.STATE.get("last") or {}
    row = [i for i in last.get("items", []) if i.get("name") == "Objects on the lot not included"]
    log["solid_check"] = {"state": last.get("state"), "row": row[0] if row else None}
    claim("3 a solid on the neighbourhood layers over the lot makes the check need review, and is never measured",
          last.get("state") == "needs_review" and bool(row) and row[0].get("status") == "needs_review"
          and "neighbourhood layers" in (row[0].get("reason") or "") and len(lots_now) == 1, log["solid_check"])
    doc.Objects.Delete(solid, True)
    for name in ("Top", "Perspective"):
        view = doc.Views.Find(name, False) or doc.Views.ActiveView
        doc.Views.ActiveView = view
        square = [o for o in doc.Objects if (o.Attributes.Name or "").startswith("Context square")]
        box = square[0].Geometry.GetBoundingBox(True) if square else None     # the whole neighbourhood square
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
    log["tick_off_locks"] = {k: v["locked"] for k, v in log["tick_off"].items()}
    g.show_context(True)
    log["tick_on"] = context_layers(g, doc)
    log["tick_on_locks"] = {k: v["locked"] for k, v in log["tick_on"].items()}
    # review round 4 (the Rhino job): a parent layer's IsVisible gave its sublayers its lock, so all came out unlocked
    claim("4 the panel tick hides it and shows it again, and only Parcels, Streets and Notes stay locked",
          all(not v["visible"] for v in log["tick_off"].values()) and all(v["visible"] for v in log["tick_on"].values())
          and all(locks[k] == g.logic.context_locked(k) for locks in (log["tick_off_locks"], log["tick_on_locks"])
                  for k in locks),
          {"off": {k: v["visible"] for k, v in log["tick_off"].items()},
           "on": {k: v["visible"] for k, v in log["tick_on"].items()},
           "off_locks": log["tick_off_locks"], "on_locks": log["tick_on_locks"]})
    # review round 5: with the architect's "Gordium" layer (and their Gordium::Grade) locked, a redraw must still
    # delete Gordium's own outlines (not draw a second set beside them) and put both locks back as they were
    top = doc.Layers.FindByFullPath("Gordium", -1)
    grade = doc.Layers[g._layer(doc, "Gordium::Grade")]
    before = len(footprints(g, doc))
    grade.IsLocked = True                        # the architect locks their grades, then "Gordium" (locking a
    doc.Layers[top].IsLocked = True              # sublayer of a locked layer wouldn't change its own lock)
    grade_own_before = doc.Layers[grade.Index].GetPersistentLocking()
    said_before = len(g.STATE.get("said", []))
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    # each layer's own lock (GetPersistentLocking): under a locked parent IsLocked reads True for every sublayer,
    # Buildings included, so it can't show the redraw kept their own locks (the Rhino job's probe at e631aae)
    own = {k: doc.Layers[doc.Layers.FindByFullPath(k, -1)].GetPersistentLocking() for k in context_layers(g, doc)}
    log["locked_parent"] = {"before": before, "after": len(footprints(g, doc)), "gordium_locked": doc.Layers[top].IsLocked,
                            "grade_locked": doc.Layers[grade.Index].IsLocked,
                            "grade_own_lock_before": grade_own_before,
                            "grade_own_lock": doc.Layers[grade.Index].GetPersistentLocking(), "own_locks": own,
                            "said": g.STATE.get("said", [])[said_before:]}
    doc.Layers[top].IsLocked = False             # the architect unlocks "Gordium": each layer as its own lock says
    after = {k: v["locked"] for k, v in context_layers(g, doc).items()}
    log["locked_parent"].update(locks_after_parent_unlocked=after,
                                grade_after_parent_unlocked=doc.Layers[grade.Index].IsLocked)
    doc.Layers[grade.Index].IsLocked = False
    lp = log["locked_parent"]
    claim("4 with the Gordium layer and the architect's Gordium::Grade locked, a redraw replaces (never doubles) and "
          "puts both locks back; unlocking Gordium leaves Parcels, Streets, Notes and Grade locked, Buildings not",
          lp["after"] == lp["before"] > 0 and lp["gordium_locked"] and lp["grade_locked"] and lp["grade_own_lock_before"]
          and lp["grade_own_lock"]
          and all(v == g.logic.context_locked(k) for k, v in own.items())
          and all(v == g.logic.context_locked(k) for k, v in after.items())
          and all(after[g.logic.CONTEXT + "::" + n] for n in ("Parcels", "Streets", "Notes"))
          and not after[g.logic.CONTEXT + "::Buildings"] and lp["grade_after_parent_unlocked"]
          and not [t for t in lp["said"] if "could not remove" in t], lp)
    path = S + "saved.3dm"
    doc.Export(path)
    f = Rhino.FileIO.File3dm.Read(path)
    stored = []
    for o in f.Objects:
        stored.append(o.Attributes.GetUserString(g.logic.CONTEXT_KEY) or "")
    log["saved_sources"] = sorted(set(stored))
    log["saved_strings"] = [f.Strings.GetKey(i) for i in range(f.Strings.Count)]
    blob = json.dumps([f.Strings.GetValue(i) for i in range(f.Strings.Count)])
    notes_text = " ".join((getattr(o.Geometry, "PlainText", "") or "") for o in f.Objects
                          if (o.Attributes.Name or "") == "Sources")
    log["saved_footprints"] = {"outlines": stored.count("state_buildings"), "credit": "footprints dated 2014" in
                               " ".join(notes_text.split())}
    claim("5 a saved file keeps the footprints (Ben, 2026-10-21) with their credit and date on the Sources note",
          log["saved_footprints"]["outlines"] > 0 and log["saved_footprints"]["credit"]
          and set(log["saved_sources"]) <= {"", "gordium", "state_parcels", "state_streets", "state_buildings"},
          log["saved_footprints"])
    # review of the editable outlines, round 3: the saved file reopened (Gordium deleted its holding layer, made
    # before the context layers when Look up held the sample lot, so their indexes move down: asserted, round 4): a
    # clear takes Gordium's untouched outlines, keeps only the architect's (the dragged, lifted, widened ones, the copy)
    theirs = len([o for o in footprints(g, doc, every=True) if o.Attributes.GetUserString(g.logic.EDITED_KEY)])
    index_before = doc.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    again = Rhino.RhinoDoc.OpenHeadless(path)
    try:
        index_after = again.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
        g._clear_context(again)
        left = footprints(g, again, every=True)
        log["reopened"] = {"buildings_index": [index_before, index_after], "theirs_before": theirs,
                           "left": len(left), "gordiums_left": len([o for o in left if o.Attributes.GetUserString(
                               g.logic.CONTEXT_KEY)]),
                           "theirs_left": len([o for o in left if o.Attributes.GetUserString(g.logic.EDITED_KEY)])}
    finally:
        again.Dispose()
    claim("5 a saved and reopened file, a layer deleted before it: a clear removes Gordium's untouched outlines, "
          "keeps only the architect's", theirs > 0 and index_after < index_before     # the shift happened (round 4)
          and log["reopened"]["gordiums_left"] == 0
          and log["reopened"]["left"] == log["reopened"]["theirs_left"] == theirs, log["reopened"])
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
