"""The in-Rhino checks queued for #23 (the neighbourhood map: context_in_rhino.py, context_tick_in_rhino.py, RHINO_QUEUE
7) and #19 (the start box lookup: RHINO_QUEUE 3, the street picks merged at aa18f7c), run WITHOUT Rhino.

How: apps/rhino_plugin/gordium_rhino.py and gordium_ui.py are imported unchanged against stand-ins for RhinoCommon,
Eto and scriptcontext (fakerhino.py, fake_eto.py: what they model is written at their top); the checker is answered
in process by design_checker.__main__.answer (what its serve loop calls); the lookup (design_checker.lookup_box)
and the neighbourhood (design_checker.context_box) run as the plugin runs them, in their own processes, on the
recorded answers (--fixture). Each claim is checked as the in-Rhino script checks it, never weakened; a claim that
only Rhino can prove is marked partial (or none) with what is left for Rhino.

Run from /home/user/wt/dryrun:
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$(ls -d packages/* | tr '\\n' ':') /home/user/venv/bin/python <this file>
Writes results_context_lookup.json (and raw_context_lookup.json) beside this file."""
import json
import os
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import WT, VENV, fresh_module, new_doc  # noqa: E402

import fake_eto  # noqa: E402
import fakerhino  # noqa: E402
import Rhino  # noqa: E402

OUT = os.path.join(HERE, "results_context_lookup.json")
RAW = os.path.join(HERE, "raw_context_lookup.json")
SHIM = os.path.join(HERE, "pyshim.sh")
WORK = os.path.join(HERE, "work")
os.makedirs(WORK, exist_ok=True)
ADDRESS = "106 Ithaca Rd, Ithaca, NY 14850"
RESULTS, RAWLOG = [], {}


def record(rid, group, where, title, needs, offline, ok, evidence, rhino_part, detail=None):
    RESULTS.append({"id": rid, "group": group, "where": where, "title": title, "needs": needs, "offline": offline,
                    "offline_ok": ok if ok is None else bool(ok), "evidence": evidence, "rhino_part": rhino_part})
    RAWLOG[rid] = detail
    print(("PASS " if ok else "N/A  " if ok is None else "FAIL ") + rid + ": " + title, flush=True)


def guarded(rid, group, where, title, needs, offline, rhino_part, fn):
    """Run one claim's check; an exception is a failed check (with its traceback in the raw log), never skipped."""
    try:
        ok, evidence, detail = fn()
    except Exception as e:
        ok, evidence, detail = False, "The headless check raised %s: %s" % (type(e).__name__, str(e)[:300]), \
            traceback.format_exc()
    record(rid, group, where, title, needs, offline, ok, evidence, rhino_part, detail)


# ---- helpers ported from apps/rhino_plugin/tests/context_in_rhino.py (the same reads, on the stand-in document) --

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


def footprints(g, doc, every=False):
    rg = Rhino.Geometry
    index = doc.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    objs = list(doc.Objects.FindByLayer(doc.Layers[index]) or []) if index >= 0 else []
    objs = [o for o in objs if isinstance(o.Geometry, rg.Curve)]
    return objs if every else [o for o in objs if o.Attributes.GetUserString(g.logic.CONTEXT_KEY)]


def notes_inside_square(g, doc):
    """As the in-Rhino script measures it, but a text's extent is a stand-in (each character 0.7 x its displayed
    height wide, each line 1.7 x high: test_context_box's generous rule), not Rhino's text layout."""
    rg = Rhino.Geometry
    index = next(i for i in g._context_layer_indexes(doc) if doc.Layers[i].FullPath.endswith("::Notes"))
    objs = list(doc.Objects.FindByLayer(doc.Layers[index]) or [])
    square = next(o for o in objs if (o.Attributes.Name or "").startswith("Context square"))
    outside, longest, kind, dim_scale, text_ft, just = [], 0, None, None, None, None
    scaling = bool(getattr(doc, "ModelSpaceAnnotationScalingEnabled", False))
    for o in objs:
        if o.Id == square.Id:
            continue
        geom = o.Geometry
        if isinstance(geom, rg.TextEntity):
            lines = geom.Text.split("\n")
            h = geom.TextHeight * (geom.DimensionScale if scaling else 1.0)
            w, t = max(map(len, lines)) * 0.7 * h, len(lines) * 1.7 * h
            pts = [geom.Plane.PointAt(u, v) for u in (0, w) for v in (0, t)]
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
            lines = (getattr(geom, "PlainText", None) or getattr(geom, "Text", "") or "").splitlines()
            longest = max(len(line) for line in lines) if lines else 0
            if isinstance(geom, rg.TextEntity):
                dim_scale, text_ft = geom.DimensionScale, round(g._feet_length(doc, geom.TextHeight), 3)
                just = geom.Justification
    return {"outside": outside, "longest_line": longest, "sources_kind": kind, "dimension_scale": dim_scale,
            "text_height_ft": text_ft, "justification": just, "notes": len(objs),
            "template_dimension_scale": doc.DimStyles.Current.DimensionScale}


def counts(layers):
    return {k.split("::")[-1]: v["objects"] for k, v in layers.items()}


# ================================================================================================================
# A. #23: context_in_rhino.py, claim by claim (16 claims)
# ================================================================================================================

def part_a():
    W = "context_in_rhino claim %d"
    RP_LOCKS = ("Real Rhino 8 layer behaviour: here a parent's IsVisible giving sublayers its lock, a locked parent "
                "locking its sublayers' objects, and Delete/Select refusing locked objects are MODELLED (fakerhino.py), "
                "not proven.")
    g = fresh_module()
    doc = new_doc()
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": ADDRESS}, lookup_fixture="106_ithaca_rd")
    started = time.time()
    g.gordium_check()                    # an empty file: GordiumStart, the lookup, Draw, then the neighbourhood
    start_s = round(time.time() - started, 2)
    said = list(g.STATE.get("said", []))
    layers = context_layers(g, doc)
    last = g.STATE.get("last") or {}
    with_summary, with_items = last.get("view_summary"), [(i["name"], i["status"], i["proposed"]) for i in
                                                           last.get("items", [])]
    lots, buildings, problems = g._sorted_objects(doc)
    payload = g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))        # drawn again
    layers_redraw = context_layers(g, doc)
    sub = {k.split("::")[-1]: v for k, v in layers.items() if k.count("::") >= 2}
    RAWLOG["a_start"] = {"start_seconds": start_s, "said": said, "summary": with_summary, "items": with_items,
                         "layers": layers, "counts": (payload or {}).get("counts")}

    def c1():
        ok = (set(sub) >= {"Parcels", "Streets", "Buildings", "Notes"}
              and all(sub[n]["objects"] > 0 for n in ("Parcels", "Streets", "Buildings", "Notes"))
              and all(v["locked"] == g.logic.context_locked(k) and v["visible"]
                      and v["colour"] == g.CONTEXT_GREYS[k.split("::")[-1]] for k, v in layers.items()
                      if k.split("::")[-1] in g.CONTEXT_GREYS))
        return ok, ("GordiumStart with 106 Ithaca Rd looked up (recorded answers) drew %s on Gordium::Context's "
                    "sublayers in their greys; locked: %s; all visible; said: \"%s\"." % (
                        counts(layers), {k.split("::")[-1]: v["locked"] for k, v in layers.items()}, said[-1])), sub
    guarded("pr23-ctx-01", "pr23", W % 1, "The neighbourhood is drawn on its own grey layers, locked but for the "
            "footprints", "rhino", "partial", RP_LOCKS + " Also that the layers look grey in the viewport.", c1)

    def c2():
        notes = " ".join(sub["Notes"]["names"] + sub["Notes"]["texts"]).lower()
        ok = "north" in notes and "scale" in notes and "source" in notes
        return ok, "The Notes layer holds %d objects named %s." % (sub["Notes"]["objects"], sub["Notes"]["names"]), \
            sub["Notes"]
    guarded("pr23-ctx-02", "pr23", W % 2, "The notes: a north arrow, a scale bar and the sources", "code", "covered",
            "Only how they look on screen (drawing).", c2)

    ni = notes_inside_square(g, doc)
    RAWLOG["a_notes"] = ni

    def c3():
        ok = not ni["outside"] and ni["longest_line"] <= g.logic.NOTE_WIDTH and ni["sources_kind"] == "TextEntity"
        return ok, ("All %d notes measured inside the turned square (curves by their points, dots by their point, the "
                    "sources text by a generous 0.7h x 1.7h extent at its displayed size); the sources note is model "
                    "text, longest line %d characters (limit %d); outside: %s." % (
                        ni["notes"] - 1, ni["longest_line"], g.logic.NOTE_WIDTH, ni["outside"] or "none")), ni
    guarded("pr23-ctx-03", "pr23", W % 3, "Every note lies inside the neighbourhood square (the sources wrapped, at "
            "most 60 characters a line)", "rhino", "partial",
            "Rhino's real text layout: the sources note's true box (its own axes, turned with the square) inside the "
            "square; here the text's extent is a stand-in.", c3)

    def c4():
        ok = ni["dimension_scale"] == 1.0 and ni["text_height_ft"] is not None and \
            abs(ni["text_height_ft"] - g.logic.NOTE_HEIGHT_FT) < 0.01 and ni["justification"] == "BottomLeft"
        return ok, ("Made from a dimension style whose model-space scale is %g (the feet template's, modelled), the "
                    "Sources text came out at its own DimensionScale %g, TextHeight %g ft, bottom-left; the in-Rhino "
                    "line height as displayed (at most %.2f ft) is not measured here." % (
                        ni["template_dimension_scale"], ni["dimension_scale"], ni["text_height_ft"],
                        g.logic.NOTE_LINE_FT)), ni
    guarded("pr23-ctx-04", "pr23", W % 4, "The sources note is small: its own scale 1, 2.5 ft text, at most 4.25 ft "
            "a line as displayed", "rhino", "partial",
            "The displayed line height (Rhino's annotation scaling and text layout) at most 4.25 ft a line.", c4)

    feet = footprints(g, doc)
    parent = doc.Layers.FindByFullPath(g.logic.CONTEXT, -1)
    doc.Objects.UnselectAll()
    selectable = bool(feet) and doc.Objects.Select(feet[0].Id)
    doc.Objects.UnselectAll()
    fp = {"outlines": len(feet), "unlocked": not sub["Buildings"]["locked"],
          "parent_unlocked": parent >= 0 and not doc.Layers[parent].IsLocked, "selectable": selectable,
          "curves": all(isinstance(o.Geometry, Rhino.Geometry.Curve) for o in feet),
          "keys": all(o.Attributes.GetUserString(g.logic.GEOM_KEY) and o.Attributes.GetUserString(g.logic.PIECE_KEY)
                      and o.Attributes.GetUserString(g.logic.DRAWN_KEY) == str(o.Id) for o in feet)}

    def c5():
        ok = len(feet) > 0 and fp["unlocked"] and fp["parent_unlocked"] and fp["selectable"] and fp["curves"] and \
            fp["keys"]
        return ok, ("%d footprint outlines (closed polylines) on Gordium::Context::Buildings, that layer and its parent "
                    "unlocked, each with its fingerprint, piece id and own object id; one selected (modelled "
                    "selection)." % fp["outlines"]), fp
    guarded("pr23-ctx-05", "pr23", W % 5, "The building footprints are real, editable outlines on the unlocked "
            "Buildings layer", "rhino", "partial", "That Rhino really lets the architect select and drag one (lock "
            "inheritance from Gordium / Gordium::Context, real RhinoCommon attributes on AddCurve).", c5)

    def c6():
        return len(lots) == 1, ("The plugin's _sorted_objects over the whole document (%d objects): %d lot candidate, %d "
                                "building solids, problems %s." % (len(doc.Objects.by_id), len(lots), len(buildings),
                                                                   problems)), None
    guarded("pr23-ctx-06", "pr23", W % 6, "The checker never measures the context: one lot", "code", "covered",
            "Rhino's object enumeration (hidden/locked objects included) is assumed to list every object.", c6)

    g._clear_context(doc)
    g.run_check(doc, report=False)
    last = g.STATE.get("last") or {}
    without, without_items = last.get("view_summary"), [(i["name"], i["status"], i["proposed"]) for i in
                                                        last.get("items", [])]

    def c7():
        ok = bool(with_summary) and with_summary == without and with_items == without_items
        return ok, ("With the neighbourhood: \"%s\"; after the plugin's clear and a fresh run_check: \"%s\"; all %d "
                    "rows identical (name, status, proposed)." % (with_summary, without, len(with_items))), \
            {"with": with_items, "without": without_items}
    guarded("pr23-ctx-07", "pr23", W % 7, "The check is the same with and without the neighbourhood", "code",
            "covered", "Rhino's own export of the model copy (here the copy is written with rhino3dm).", c7)

    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    again = context_layers(g, doc)

    def c8():
        first, second = {k: v["objects"] for k, v in layers.items()}, {k: v["objects"] for k, v in again.items()}
        ok = first == second and {k: v["objects"] for k, v in layers_redraw.items()} == first
        return ok, ("First draw %s; redrawn twice (over a drawn one and after a clear): %s, %s." % (
            counts(layers), counts(layers_redraw), counts(again))), {"first": first, "again": second}
    guarded("pr23-ctx-08", "pr23", W % 8, "Drawn again it replaces, never doubles", "rhino", "partial",
            RP_LOCKS + " Rhino must really delete the old objects once their layers are opened.", c8)

    feet = footprints(g, doc)
    moved, other, lifted = feet[0], feet[1], feet[2]
    moved_id, other_guid = moved.Attributes.GetUserString(g.logic.PIECE_KEY), other.Id
    lifted_id = lifted.Attributes.GetUserString(g.logic.PIECE_KEY)
    t1 = doc.Objects.Transform(moved, Rhino.Geometry.Transform.Translation(g._model_length(doc, 10.0), 0, 0), True)
    t2 = doc.Objects.Transform(lifted, Rhino.Geometry.Transform.Translation(0, 0, g._model_length(doc, 3.0)), True)
    before = len(feet)
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    after = footprints(g, doc, every=True)
    kept = [o for o in after if o.Attributes.GetUserString(g.logic.PIECE_KEY) == moved_id]
    up = [o for o in after if o.Attributes.GetUserString(g.logic.PIECE_KEY) == lifted_id]
    edited = {"transformed": [t1 != fakerhino.EMPTY_GUID, t2 != fakerhino.EMPTY_GUID], "before": before,
              "after": len(after), "kept": len(kept),
              "lifted_kept_once": len(up) == 1 and bool(up[0].Attributes.GetUserString(g.logic.EDITED_KEY)),
              "kept_is_theirs": bool(kept) and bool(kept[0].Attributes.GetUserString(g.logic.EDITED_KEY))
              and not kept[0].Attributes.GetUserString(g.logic.CONTEXT_KEY),
              "unedited_replaced": doc.Objects.FindId(other_guid) is None}

    def c9():
        ok = all(edited["transformed"]) and edited["kept"] == 1 and edited["kept_is_theirs"] and \
            edited["after"] == before and edited["lifted_kept_once"] and edited["unedited_replaced"]
        return ok, ("One footprint dragged 10 ft, one lifted 3 ft, then redrawn: %d outlines before, %d after; the "
                    "dragged one kept once as the architect's (no Gordium source), the lifted one kept once, an "
                    "untouched one replaced (its object gone)." % (before, len(after))), edited
    guarded("pr23-ctx-09", "pr23", W % 9, "An edited footprint stays (the architect's), is not drawn twice; the "
            "others are replaced", "rhino", "partial", "A real drag in Rhino (Transform's id and attributes as Rhino "
            "keeps them) and the fingerprint as RhinoCommon reports attributes.", c9)

    feet = [o for o in footprints(g, doc) if not o.Attributes.GetUserString(g.logic.EDITED_KEY)]
    source, widened = feet[0], feet[1]
    source_id, widened_id = source.Attributes.GetUserString(g.logic.PIECE_KEY), widened.Attributes.GetUserString(
        g.logic.PIECE_KEY)
    copy_guid = doc.Objects.AddCurve(source.Geometry.DuplicateCurve(), source.Attributes.Duplicate())
    wide = widened.Attributes.Duplicate()
    wide.PlotWeightSource = Rhino.DocObjects.ObjectPlotWeightSource.PlotWeightFromObject
    wide.PlotWeight = 0.35
    doc.Objects.ModifyAttributes(widened, wide, True)
    before = len(footprints(g, doc, every=True))
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    after = footprints(g, doc, every=True)
    copy = doc.Objects.FindId(copy_guid)
    cw = {"copy_kept_as_theirs": copy is not None and bool(copy.Attributes.GetUserString(g.logic.EDITED_KEY))
          and not copy.Attributes.GetUserString(g.logic.CONTEXT_KEY),
          "copied_one_redrawn": len([o for o in after if o.Attributes.GetUserString(g.logic.PIECE_KEY) == source_id]) == 2,
          "width_kept_once": [o.Attributes.PlotWeight for o in after
                              if o.Attributes.GetUserString(g.logic.PIECE_KEY) == widened_id] == [0.35],
          "before": before, "after": len(after)}

    def c10():
        ok = cw["copy_kept_as_theirs"] and cw["copied_one_redrawn"] and cw["width_kept_once"] and cw["after"] == before
        return ok, ("A copy pasted in place and a footprint given a 0.35 print width, then redrawn: %d outlines before, "
                    "%d after; the copy kept as the architect's beside its redrawn original, the widened one kept once."
                    % (before, len(after))), cw
    guarded("pr23-ctx-10", "pr23", W % 10, "A copy pasted in place and a footprint given a print width are the "
            "architect's: kept, never doubled", "rhino", "partial", "Copy/paste and Properties in Rhino (the user "
            "text and attributes Rhino really carries on a pasted copy).", c10)

    lot = g._find(doc, g.current_facts(doc).get("lot_id") or "")
    centre = lot.Geometry.GetBoundingBox(True).Center
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.LayerIndex = doc.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    attrs.Name = "Extruded footprint"
    k = g._model_length(doc, 5.0)
    solid = doc.Objects.AddBrep(Rhino.Geometry.Brep.CreateFromBox(Rhino.Geometry.BoundingBox(
        centre.X - k, centre.Y - k, 0, centre.X + k, centre.Y + k, 2 * k)), attrs)
    g.run_check(doc, report=False)
    lots_now, _, _ = g._sorted_objects(doc)
    last = g.STATE.get("last") or {}
    row = [i for i in last.get("items", []) if i.get("name") == "Objects on the lot not included"]
    sc_ = {"state": last.get("state"), "summary": last.get("view_summary"), "row": row[0] if row else None,
           "lots": len(lots_now)}

    def c11():
        ok = last.get("state") == "needs_review" and bool(row) and row[0].get("status") == "needs_review" and \
            "neighbourhood layers" in (row[0].get("reason") or "") and len(lots_now) == 1
        return ok, ("A 10 x 10 x 10 ft solid on Gordium::Context::Buildings over the lot: the check \"%s\" (%s), row "
                    "\"Objects on the lot not included\" %s: \"%s\"; still one lot." % (
                        sc_["summary"], sc_["state"], row[0]["status"] if row else "missing",
                        (row[0].get("reason") or "")[:160] if row else "")), sc_
    guarded("pr23-ctx-11", "pr23", W % 11, "A solid on the neighbourhood layers over the lot makes the check need "
            "review, and is never measured", "code", "partial", "A real Rhino solid's plan points (vertices, edges, "
            "faces from RhinoCommon); here a box's corners stand in.", c11)
    doc.Objects.Delete(solid, True)

    g.show_context(False)
    off = context_layers(g, doc)
    g.show_context(True)
    on = context_layers(g, doc)
    tick = {"off": {k: (v["visible"], v["locked"]) for k, v in off.items()},
            "on": {k: (v["visible"], v["locked"]) for k, v in on.items()}}

    def c12():
        ok = all(not v["visible"] for v in off.values()) and all(v["visible"] for v in on.values()) and \
            all(v["locked"] == g.logic.context_locked(k) for d in (off, on) for k, v in d.items())
        return ok, ("show_context(False) hid all %d context layers, show_context(True) showed them; locks after both: "
                    "%s (only Parcels, Streets, Notes locked)." % (len(off), {k.split("::")[-1]: v["locked"]
                                                                            for k, v in on.items()})), tick
    guarded("pr23-ctx-12", "pr23", W % 12, "The panel tick hides it and shows it again, and only Parcels, Streets and "
            "Notes stay locked", "rhino", "partial", RP_LOCKS + " This is the very behaviour the round-4 fix answers: "
            "only Rhino 8 shows whether the locks really stay.", c12)

    top = doc.Layers.FindByFullPath("Gordium", -1)
    grade = doc.Layers[g._layer(doc, "Gordium::Grade")]
    before = len(footprints(g, doc))
    doc.Layers[top].IsLocked, grade.IsLocked = True, True
    said_before = len(g.STATE.get("said", []))
    g.draw_context(doc, g._ui_state(doc).get("lookup_frame"))
    locks = {k: v["locked"] for k, v in context_layers(g, doc).items()}
    lp = {"before": before, "after": len(footprints(g, doc)), "gordium_locked": doc.Layers[top].IsLocked,
          "grade_locked": doc.Layers[grade.Index].IsLocked, "locks": locks,
          "said": g.STATE.get("said", [])[said_before:],
          "refused": [x for x in doc.Objects.log[-2000:] if not x[2]][:5]}
    doc.Layers[top].IsLocked, doc.Layers[grade.Index].IsLocked = False, False

    def c13():
        ok = lp["after"] == lp["before"] > 0 and lp["gordium_locked"] and lp["grade_locked"] and \
            all(v == g.logic.context_locked(k) for k, v in locks.items()) and \
            not [t for t in lp["said"] if "could not remove" in t]
        return ok, ("With \"Gordium\" and \"Gordium::Grade\" locked, a redraw: %d footprints before, %d after; Gordium "
                    "locked %s, Grade locked %s afterwards; context locks %s; said \"%s\"." % (
                        lp["before"], lp["after"], lp["gordium_locked"], lp["grade_locked"],
                        {k.split("::")[-1]: v for k, v in locks.items()}, (lp["said"] or [""])[-1])), lp
    guarded("pr23-ctx-13", "pr23", W % 13, "With the Gordium layer and the architect's Gordium::Grade locked, a redraw "
            "replaces (never doubles) and puts both locks back", "rhino", "partial", RP_LOCKS + " Whether Rhino 8 "
            "really deletes under a locked \"Gordium\" opened parent-first, and really leaves Grade locked after the "
            "parent's IsVisible, is the round-5 question only Rhino answers.", c13)

    path = os.path.join(WORK, "saved.3dm")
    doc.Export(path)
    f = Rhino.FileIO.File3dm.Read(path)
    stored = [o.Attributes.GetUserString(g.logic.CONTEXT_KEY) or "" for o in f.Objects]
    notes_text = " ".join((getattr(o.Geometry, "PlainText", "") or "") for o in f.Objects
                          if (o.Attributes.Name or "") == "Sources")
    strings = {f.Strings.GetKey(i): f.Strings.GetValue(i) for i in range(f.Strings.Count)}
    from site_lookup.sources import ENDPOINTS
    live_only = {k for k, e in ENDPOINTS.items() if e.get("store") == "none"}
    blob = json.dumps(strings)
    sv = {"outlines": stored.count("state_buildings"), "credit": "footprints dated 2014" in " ".join(notes_text.split()),
          "sources": sorted(set(stored)), "strings": sorted(strings),
          "live_only_sources_in_file": sorted(s for s in set(stored) if s in live_only),
          "session_keys_in_file": [k for k in json.loads(strings.get("Gordium\\ui", "{}")) if k.startswith("_")],
          "map_words_in_file": "City zoning map says" in blob}

    def c14():
        ok = sv["outlines"] > 0 and sv["credit"] and set(sv["sources"]) <= {"", "gordium", "state_parcels",
                                                                             "state_streets", "state_buildings"} \
            and not sv["live_only_sources_in_file"] and not sv["session_keys_in_file"] and not sv["map_words_in_file"]
        return ok, ("Saved (rhino3dm) and read back: %d footprint outlines, \"footprints dated 2014\" on the Sources "
                    "note, object sources %s, document strings %s; no store:none source (%s), no session key, no "
                    "zoning map words." % (sv["outlines"], sv["sources"], sv["strings"], ", ".join(sorted(live_only)))), sv
    guarded("pr23-ctx-14", "pr23", W % 14, "A saved file keeps the footprints with their credit and date on the "
            "Sources note", "rhino", "partial", "Rhino's own save (doc.Export / File3dm) and model text in a real "
            ".3dm; here the document is written with rhino3dm, its text as a dot carrying the same words.", c14)

    theirs = len([o for o in footprints(g, doc, every=True) if o.Attributes.GetUserString(g.logic.EDITED_KEY)])
    index_before = doc.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    again = Rhino.RhinoDoc.OpenHeadless(path)
    index_after = again.Layers.FindByFullPath(g.logic.CONTEXT + "::Buildings", -1)
    g._clear_context(again)
    left = footprints(g, again, every=True)
    ro = {"buildings_index": [index_before, index_after], "theirs_before": theirs, "left": len(left),
          "gordiums_left": len([o for o in left if o.Attributes.GetUserString(g.logic.CONTEXT_KEY)]),
          "theirs_left": len([o for o in left if o.Attributes.GetUserString(g.logic.EDITED_KEY)])}

    def c15():
        ok = theirs > 0 and index_after < index_before and ro["gordiums_left"] == 0 and \
            ro["left"] == ro["theirs_left"] == theirs
        return ok, ("Reopened (the deleted holding layer gone, Buildings index %d -> %d); a clear left %d outlines, all "
                    "the architect's (%d before), none of Gordium's." % (index_before, index_after, ro["left"], theirs)), ro
    guarded("pr23-ctx-15", "pr23", W % 15, "A saved and reopened file, a layer deleted before it: a clear removes "
            "Gordium's untouched outlines, keeps only the architect's", "rhino", "partial", "A real Rhino reopen: "
            "that RhinoCommon reads the attributes back the same (colour, names, ids) so untouched fingerprints still "
            "match.", c15)

    first_frame = (g._context_record(doc) or {}).get("frame")
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": "109 Ithaca Rd, Ithaca, NY 14850"},
                   lookup_fixture="109_ithaca_rd", auto_ok=True)
    said_before = len(g.STATE.get("said", []))
    g.edit_facts()
    second_frame = (g._context_record(doc) or {}).get("frame")
    left = context_layers(g, doc)
    first_parcel = (first_frame or {}).get("parcel_id")
    sa = {"frame_changed": second_frame != first_frame, "left": counts(left), "said": g.STATE.get("said", [])[said_before:],
          "address": g.current_facts(doc).get("address")}

    def c16():
        ok = second_frame != first_frame and not any(first_parcel and first_parcel in " ".join(v["names"])
                                                     for v in left.values()) \
            and sum(v["objects"] for v in left.values()) != sum(v["objects"] for v in layers.values())
        return ok, ("Edit site… with 109 Ithaca Rd looked up: the frame changed, the context layers now hold %s (the "
                    "architect's kept outlines only), 106's parcel nowhere; said \"%s\"." % (
                        sa["left"], " / ".join(sa["said"][-2:]))), sa
    guarded("pr23-ctx-16", "pr23", W % 16, "A second address clears the first neighbourhood", "code", "partial",
            RP_LOCKS + " Also the real Edit site… box (Eto).", c16)


# ================================================================================================================
# A2. #23: context_tick_in_rhino.py (10 claims): the panel's own checkbox, its handler run as a click's
# ================================================================================================================

def the_tick(parts):
    for row in parts.get("greyed") or []:
        items = [it.Control for it in getattr(row, "Items", None) or []]
        if any(isinstance(c, fake_eto.CheckBox) and c.Text == "Show neighbourhood" for c in items):
            return row, items
    return None, []


def part_tick():
    W = "context_tick claim %d"
    RP = ("Eto in Rhino: the real CheckBox (a click), the docked panel's layout and greying; here Eto is a "
          "stand-in whose CheckBox fires CheckedChanged on a change.")
    g = fresh_module()
    doc = new_doc()
    # the docked panel's path: Rhino registers the dock and hands the panel a host (both Rhino's; stood in here)
    import scriptcontext as sc
    host = fake_eto.Widget()
    g.register_dock = lambda: "dock-id"
    sc.sticky["gordium_dock_hosts"] = {doc.RuntimeSerialNumber: host}
    g.STATE.update(box_picks=["lookup"], box_overrides={"address": ADDRESS}, lookup_fixture="106_ithaca_rd",
                   on_confirm=lambda *a: None)
    g.gordium_check()
    parts = g.STATE.get("panel_parts") or {}
    layers = lambda: [doc.Layers[i].IsVisible for i in g._context_layer_indexes(doc)]  # noqa: E731
    start = layers()
    row, boxes = the_tick(parts)
    guarded("pr23-tick-01", "pr23", W % 1, "The panel is Rhino's docked panel", "rhino", "partial",
            "Rhino 8's docked panel itself (RegisterPanel, the emitted .NET panel type, the dock host): nothing of it "
            "runs here.", lambda: (bool(getattr(parts.get("form"), "host", None)) and parts["form"].host is host,
                                   "With Rhino's dock registration stood in (an id and a host for this document), "
                                   "panel() built the panel through ui.DockHost on that host.", None))
    guarded("pr23-tick-02", "pr23", W % 2, "The tick is on a row of its own", "rhino", "partial", RP,
            lambda: (row is not None and len(boxes) == 1,
                     "ui.make_panel's greyed rows: the \"Show neighbourhood\" row holds %d control(s): %s." % (
                         len(boxes), [getattr(b, "Text", type(b).__name__) for b in boxes]), None))
    tick = boxes[0] if boxes else None
    guarded("pr23-tick-03", "pr23", W % 3, "The neighbourhood is drawn and the tick starts on", "rhino", "partial", RP,
            lambda: (bool(start) and all(start) and tick is not None and tick.Checked is True,
                     "After GordiumStart (106, recorded): %d context layers, all visible; tick Checked=%s." % (
                         len(start), tick.Checked if tick else None), start))
    tick.Checked = False
    after_off = layers()
    guarded("pr23-tick-04", "pr23", W % 4, "Unticking through the panel hides every neighbourhood layer", "rhino",
            "partial", RP + " Layer visibility is modelled.",
            lambda: (not any(after_off) and g.logic.context_shown(g._ui_state(doc)) is False,
                     "Checked=False on the panel's checkbox ran its handler: visible %s; the file's setting "
                     "show_context=%s; said \"%s\"." % (after_off, g._ui_state(doc).get("show_context"),
                                                       (g.STATE.get("said") or [""])[-1]), after_off))
    path = os.path.join(WORK, "tick_saved.3dm")
    doc.Export(path)
    saved = Rhino.FileIO.File3dm.Read(path)
    kept = json.loads(saved.Strings.GetValue(g.SECTION, g.UI_ENTRY) or "{}")
    guarded("pr23-tick-05", "pr23", W % 5, "The tick is kept in the file: a saved copy has it off", "rhino", "partial",
            "Rhino's own save of the document strings (here written and read back with rhino3dm).",
            lambda: (kept.get("show_context") is False, "The saved copy's Gordium\\ui: show_context=%s, show_labels=%s."
                     % (kept.get("show_context"), kept.get("show_labels")), kept))
    g.STATE.pop("panel_parts", None)
    rebuilt = g.panel()
    _, again = the_tick(rebuilt)
    guarded("pr23-tick-06", "pr23", W % 6, "A rebuilt panel starts the tick as last set (off)", "rhino", "partial", RP,
            lambda: (bool(again) and again[0].Checked is False, "panel() rebuilt: the tick Checked=%s." % (
                [b.Checked for b in again],), None))
    again[0].Checked = True
    after_on = layers()
    guarded("pr23-tick-07", "pr23", W % 7, "Ticking through the panel shows them again", "rhino", "partial",
            RP + " Layer visibility is modelled.",
            lambda: (all(after_on) and g.logic.context_shown(g._ui_state(doc)) is True,
                     "Checked=True: visible %s; said \"%s\"." % (after_on, (g.STATE.get("said") or [""])[-1]), after_on))
    inside = {}
    options = g.ask({"cmd": "options", "jurisdiction": g.JURISDICTION})

    def during(doc_, facts, text, state):
        p = g.STATE.get("panel_parts") or {}
        _, b = the_tick(p)
        inside["enabled"] = b[0].Enabled if b else None
        said = len(g.STATE.get("said") or [])
        b[0].Checked = False
        inside["said"] = (g.STATE.get("said") or [])[said:]
        inside["layers"] = layers()
        b[0].Checked = True
    g.STATE["on_confirm"] = during
    g.confirm(doc, g.current_facts(doc), options, "check")
    _, after = the_tick(g.STATE.get("panel_parts") or {})
    guarded("pr23-tick-08", "pr23", W % 8, "While a start box is open the tick is off (greyed)", "rhino", "partial", RP,
            lambda: (inside.get("enabled") is False, "Inside Edit site…'s box: the tick Enabled=%s." %
                     inside.get("enabled"), inside))
    guarded("pr23-tick-09", "pr23", W % 9, "And a change to it then does nothing", "rhino", "partial", RP,
            lambda: (all(inside.get("layers") or [False]) and bool(inside.get("said")) and
                     g.logic.BOX_BUSY in inside["said"],
                     "Unticked inside the box: layers still visible %s; said %s." % (inside.get("layers"),
                                                                                    inside.get("said")), inside))
    guarded("pr23-tick-10", "pr23", W % 10, "After the box closes the tick is back on", "rhino", "partial", RP,
            lambda: (bool(after) and after[0].Enabled is True and all(layers()),
                     "After the box: tick Enabled=%s, layers visible %s." % ([b.Enabled for b in after], layers()),
                     None))


# ================================================================================================================
# B. #19: RHINO_QUEUE 3 (R-2a lookup -> pick R-1b -> tick -> Draw; label refreshes; reopened next day: no "checked")
#    and the street picks merged at aa18f7c
# ================================================================================================================

def find(dialog, cls, pred=lambda c: True):
    return [c for c in fake_eto.controls(dialog.Content) if isinstance(c, cls) and pred(c)]


def zone_widgets(dialog):
    zone = find(dialog, fake_eto.DropDown, lambda d: any(i.Text == "R-1b" for i in d.Items))[0]
    holder = [s for s in find(dialog, fake_eto.StackLayout) if any(it.Control is zone for it in s.Items)][0]
    source = holder.Items[1].Control
    confirm = holder.Items[2].Control
    draw = find(dialog, fake_eto.Button, lambda b: b.Text in ("Draw", "Check"))[0]
    return zone, source, confirm, draw


def drive_box(steps, poll_limit=90):
    """The scripted architect: each shown box runs the next step (a function of the dialog)."""
    seen = []

    def user(dialog):
        if not steps:
            raise AssertionError("a box opened that the script did not expect")
        step = steps.pop(0)
        seen.append(step.__name__)
        step(dialog)
        started = time.time()
        while dialog.Visible and time.time() - started < poll_limit:     # a lookup box waits for its answer
            ticking = [t for t in fake_eto.TIMERS if t.running]
            if not ticking:
                break
            for t in ticking:
                t.Elapsed.fire(t, None)
            time.sleep(0.2)
    fake_eto.USER[:] = [user]
    return seen


def part_b():
    W3 = "RHINO_QUEUE 3"
    RP = ("The real start box (Eto Dialog, DropDown, CheckBox, Label) in Rhino: here the box's own code "
          "(gordium_ui.start_box) runs against stand-in widgets that fire their change events.")
    g = fresh_module()
    g.STATE["auto_ok"] = False                      # the box itself, driven by a scripted architect
    g._python = lambda: SHIM
    os.environ["GORDIUM_SHIM"] = "r2a"              # the recorded answers, the City zoning stand-in saying R-2a
    doc = new_doc()
    g.STATE["lookup_fixture"] = "106_ithaca_rd"
    obs = {}

    def type_and_look_up(d):
        address = find(d, fake_eto.TextBox)[0]
        address.Text = ADDRESS
        find(d, fake_eto.Button, lambda b: b.Text == "Look up")[0].Click.fire()

    def waiting(d):                                  # "Looking up…": the box closes itself when the answer is in
        obs["looking_draw"] = zone_widgets(d)[3].Enabled

    def pick_r1b_tick_draw(d):
        zone, source, confirm, draw = zone_widgets(d)
        reason = find(d, fake_eto.Label, lambda x: x.Text == "Pick the district to continue.")
        amber = [x.Text for x in find(d, fake_eto.Label) if "R-2a" in (x.Text or "")]
        obs["after_lookup"] = {"zone": zone.SelectedValue.Text if zone.SelectedValue else None,
                               "source": source.Text, "confirm": confirm.Checked, "draw": draw.Enabled,
                               "reason": reason[0].Text if reason else None, "r2a_lines": amber}
        zone.SelectedIndex = [i.Text for i in zone.Items].index("R-1b")
        obs["after_pick"] = {"source": source.Text, "draw": draw.Enabled, "reason": reason[0].Text if reason else None}
        confirm.Checked = True
        obs["after_tick"] = {"draw": draw.Enabled, "reason": reason[0].Text if reason else None}
        draw.Click.fire()
    seen = drive_box([type_and_look_up, waiting, pick_r1b_tick_draw])
    g.gordium_start()
    facts = g.current_facts(doc)
    sources = g.fact_sources(doc)
    last = g.STATE.get("last") or {}
    obs["drawn"] = {"zone": facts.get("zone"), "zone_source": (sources.get("zone") or {}).get("source"),
                    "confirmed_by": (sources.get("zone") or {}).get("confirmed_by"), "summary": last.get("view_summary"),
                    "code": (last.get("header") or {}).get("code"), "boxes": seen}
    RAWLOG["b_r2a"] = obs
    a, p, t = obs.get("after_lookup") or {}, obs.get("after_pick") or {}, obs.get("after_tick") or {}
    guarded("pr19-q3-1", "pr19", W3, "After an R-2a lookup the box sets no district, says R-2a has no rules, and keeps "
            "Draw off", "rhino", "partial", RP,
            lambda: (a.get("zone") is None and a.get("source") == "not set" and a.get("draw") is False
                     and a.get("reason") == "Pick the district to continue." and bool(a.get("r2a_lines")),
                     "106 looked up with the zoning stand-in saying R-2a: district dropdown %s, its label \"%s\", Draw "
                     "enabled=%s, reason \"%s\", amber line \"%s\"." % (a.get("zone"), a.get("source"), a.get("draw"),
                                                                       a.get("reason"), (a.get("r2a_lines") or [""])[0][:110]),
                     a))
    guarded("pr19-q3-2", "pr19", W3, "Picking R-1b refreshes the district's label at once (and Draw waits for the "
            "tick)", "rhino", "partial", RP,
            lambda: (p.get("source") == "entered by you" and p.get("draw") is False
                     and p.get("reason") == "Confirm the district to continue.",
                     "R-1b picked in the dropdown: the label now \"%s\", Draw enabled=%s, reason \"%s\"." % (
                         p.get("source"), p.get("draw"), p.get("reason")), p))
    guarded("pr19-q3-3", "pr19", W3, "Ticking \"This is the lot's district\" turns Draw on", "rhino", "partial", RP,
            lambda: (t.get("draw") is True and t.get("reason") == "",
                     "Ticked: Draw enabled=%s, reason \"%s\"." % (t.get("draw"), t.get("reason")), t))
    d = obs["drawn"]
    guarded("pr19-q3-4", "pr19", W3, "Draw keeps R-1b as the architect's and the lot is checked against R-1b", "code",
            "partial", RP,
            lambda: (d["zone"] == "R-1b" and d["zone_source"] == g.logic.ENTERED and d["summary"] is not None
                     and d["boxes"] == ["type_and_look_up", "waiting", "pick_r1b_tick_draw"],
                     "Saved facts: zone %s, source \"%s\" (confirmed by %s); the starting house checked: \"%s\"." % (
                         d["zone"], d["zone_source"], d["confirmed_by"], d["summary"]), d))

    # reopened the next day: Edit site… shows the district's saved source, never the lookup's "(checked …)" words
    path = os.path.join(WORK, "r2a_saved.3dm")
    doc.Export(path)
    reopened = fakerhino.open_3dm(path)
    Rhino.RhinoDoc.ActiveDoc = reopened
    real_day = g.logic.city_day
    g.logic.city_day = lambda now=None: "2026-10-23"           # the next day
    rows = {}

    def look_and_cancel(dlg):
        zone, source, confirm, draw = zone_widgets(dlg)
        rows.update(zone=zone.SelectedValue.Text if zone.SelectedValue else None, source=source.Text,
                    confirm=confirm.Checked, labels=[x.Text for x in find(dlg, fake_eto.Label)])
        find(dlg, fake_eto.Button, lambda b: b.Text == "Cancel")[0].Click.fire()
    drive_box([look_and_cancel])
    g.edit_facts()
    g.logic.city_day = real_day
    text = " ".join(str(x) for x in rows.get("labels") or [])
    strings = json.dumps(reopened.Strings.d.get(("Gordium", "ui")) or "")
    RAWLOG["b_reopen"] = {"rows": rows, "ui": strings}

    # the same for a lookup whose district Gordium has (R-1b, suggested): this session shows "(checked <day>)"
    os.environ["GORDIUM_SHIM"] = ""
    g2 = fresh_module()
    g2.STATE["auto_ok"] = False
    g2._python = lambda: SHIM
    doc2 = new_doc()
    g2.STATE["lookup_fixture"] = "106_ithaca_rd"
    seen2 = {}

    def tick_draw(dlg):
        zone, source, confirm, draw = zone_widgets(dlg)
        seen2["session"] = source.Text
        confirm.Checked = True
        draw.Click.fire()
    drive_box([type_and_look_up, waiting, tick_draw])
    g2.gordium_start()
    path2 = os.path.join(WORK, "r1b_saved.3dm")
    doc2.Export(path2)
    re2 = fakerhino.open_3dm(path2)
    Rhino.RhinoDoc.ActiveDoc = re2
    g2.logic.city_day = lambda now=None: "2026-10-23"

    def look2(dlg):
        seen2["reopened"] = zone_widgets(dlg)[1].Text
        seen2["labels"] = " ".join(x.Text or "" for x in find(dlg, fake_eto.Label))
        find(dlg, fake_eto.Button, lambda b: b.Text == "Cancel")[0].Click.fire()
    drive_box([look2])
    g2.edit_facts()
    RAWLOG["b_reopen_r1b"] = seen2
    guarded("pr19-q3-5", "pr19", W3, "The file reopened the next day shows no \"checked today\" (no lookup date) on "
            "the district", "rhino", "partial", RP + " Also Rhino's real save and reopen of the file.",
            lambda: (rows.get("zone") == "R-1b" and rows.get("source") == "entered by you"
                     and "(checked " not in text and " says " not in text and "_zone_said" not in strings
                     and "(checked 2026-10-20)" in (seen2.get("session") or "")
                     and "(checked " not in seen2.get("reopened", "(checked ")
                     and "(checked " not in seen2.get("labels", "(checked ") and " says " not in seen2.get("labels", ""),
                     "R-2a case reopened with the clock on 2026-10-23: Edit site… shows R-1b \"%s\" (no \"(checked "
                     "<day>)\" or \"says\" anywhere in the box). R-1b case: in its session \"%s\", reopened \"%s\"." % (
                         rows.get("source"), seen2.get("session"), seen2.get("reopened")),
                     {"r2a": rows, "r1b": seen2}))
    os.environ["GORDIUM_SHIM"] = ""


def part_streets():
    W = "aa18f7c street pick"
    RP = ("Rhino's own clicks (RhinoGet.GetPoint / GetString at the command line): here _get_point is fed the click "
          "points and the street name prompt is stood in.")
    g = fresh_module()
    doc = new_doc()
    g.STATE.update(box_picks=[], on_confirm=lambda *a: None)
    g.gordium_check()                             # the sample (its street Ithaca Rd), drawn and checked
    facts0, saved0 = g.current_facts(doc), g._ui_state(doc)
    lines0, ids0 = facts0.get("street_line") or [], facts0.get("street_ids")
    lot = g._find(doc, facts0["lot_id"])
    ring = [(p.X, p.Y) for p in lot.Geometry.points]

    def mid(a, b):
        return Rhino.Geometry.Point3d((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0)

    def clicks(points):
        it = iter(points)

        def get_point(prompt):
            p = next(it, None)
            return ("Success", p) if p is not None else ("Nothing", None)
        g._get_point = get_point

    session = g.logic.BoxSession(g.RhinoTable(doc))
    street = lines0[len(lines0) // 2]
    others = [(a, b) for a, b in zip(ring, ring[1:]) if not any(
        abs(a[0] - s[0][0]) < 0.5 and abs(a[1] - s[0][1]) < 0.5 and abs(b[0] - s[1][0]) < 0.5 and
        abs(b[1] - s[1][1]) < 0.5 or abs(a[0] - s[1][0]) < 0.5 and abs(a[1] - s[1][1]) < 0.5 and
        abs(b[0] - s[0][0]) < 0.5 and abs(b[1] - s[0][1]) < 0.5 for s in lines0)]
    RAWLOG["streets_sample"] = {"lines": len(lines0), "ids": ids0, "street_name": saved0.get("street_name"),
                                "others": len(others)}

    clicks([mid(*street)])
    f1, s1 = g._box_pick(doc, "street", dict(facts0, corner_lot=False), dict(saved0), session)
    guarded("pr19-street-1", "pr19", W, "A single street pick on the sample keeps Ithaca Rd on every street line",
            "code", "partial", RP,
            lambda: (len(f1.get("street_line") or []) == len(lines0) == 8 and f1.get("street_ids") == ["Ithaca Rd"] * 8
                     and s1.get("street_name") == "Ithaca Rd" and s1.get("street_source") == g.logic.ENTERED,
                     "Sample: %d street lines all \"Ithaca Rd\"; one click on line %d: %d lines, names %s, box name "
                     "\"%s\" (%s)." % (len(lines0), len(lines0) // 2, len(f1.get("street_line") or []),
                                       sorted(set(f1.get("street_ids") or [None]), key=str), s1.get("street_name"),
                                       s1.get("street_source")), {"facts": f1.get("street_ids")}))

    clicks([mid(*street), mid(*others[0]), None])
    f2, s2 = g._box_pick(doc, "street", dict(facts0, corner_lot=True), dict(saved0), session)
    guarded("pr19-street-2", "pr19", W, "On a corner lot every line clicked is a street line, Enter when done, with "
            "no one name for them", "code", "partial", RP,
            lambda: (len(f2.get("street_line") or []) == 2 and not f2.get("street_ids"),
                     "Corner lot: two lines clicked then Enter: %d street lines, names %s." % (
                         len(f2.get("street_line") or []), f2.get("street_ids")), f2.get("street_line")))

    def esc(prompt):
        return ("Cancel", None)
    g._get_point = esc
    f3, s3 = g._box_pick(doc, "street", dict(facts0, corner_lot=False), dict(saved0), session)
    guarded("pr19-street-3", "pr19", W, "Esc at the street pick changes nothing", "code", "partial", RP,
            lambda: (f3 == dict(facts0, corner_lot=False) and s3 == saved0,
                     "Esc at the first click: facts and the box's choices unchanged (%d lines, \"%s\")." % (
                         len(f3.get("street_line") or []), s3.get("street_name")), None))

    class GetString:                              # Rhino's GetString: the architect types "Hudson St"
        def SetCommandPrompt(self, *a):
            pass

        def AcceptNothing(self, *a):
            pass

        def GetLiteralString(self):
            return "String"

        def StringResult(self):
            return "Hudson St"
    Rhino.Input.Custom = type("Custom", (), {"GetString": GetString})
    Rhino.Input.GetResult = type("GetResult", (), {"Cancel": "Cancel", "String": "String"})
    clicks([mid(*others[0])])
    f4, s4 = g._box_pick(doc, "street", dict(facts0, corner_lot=False), dict(saved0), session)
    guarded("pr19-street-4", "pr19", W, "A lot line not on Ithaca Rd, its street typed, is that one line with that "
            "name only", "code", "partial", RP,
            lambda: (len(f4.get("street_line") or []) == 1 and f4.get("street_ids") == ["Hudson St"]
                     and s4.get("street_name") == "Hudson St",
                     "A side line clicked, \"Hudson St\" typed: %d street line, names %s." % (
                         len(f4.get("street_line") or []), f4.get("street_ids")), None))

    # a lookup that replaces the sample's lot: the sample's "Ithaca Rd" never stays unless the lookup names it
    out = {}
    for shim, key in (("nostreet", "unnamed"), ("", "named")):
        os.environ["GORDIUM_SHIM"] = shim
        gx = fresh_module()
        gx._python = lambda: SHIM
        dx = new_doc()

        def on_confirm(doc_, facts, text, state, key=key):
            out[key] = {"street_name": state.get("street_name"), "street_source": state.get("street_source"),
                        "lines": len(facts.get("street_line") or []), "ids": facts.get("street_ids")}
        gx.STATE.update(box_picks=["lookup"], box_overrides={"address": ADDRESS}, lookup_fixture="106_ithaca_rd",
                        on_confirm=on_confirm)
        gx.gordium_check()
        ui_saved = gx._ui_state(dx)
        out[key]["saved_name"], out[key]["saved_source"] = ui_saved.get("street_name"), ui_saved.get("street_source")
        out[key]["fact"] = gx.fact_sources(dx).get("street")          # what the panel and the report show
        out[key]["file"] = "Ithaca Rd" in json.dumps([ui_saved.get("street_name"), ui_saved.get("_street_name"),
                                                      out[key]["fact"], gx.current_facts(dx).get("street_ids")])
    os.environ["GORDIUM_SHIM"] = ""
    RAWLOG["streets_lookup"] = out
    u, n = out.get("unnamed", {}), out.get("named", {})
    guarded("pr19-street-5", "pr19", W, "A lookup that replaces the sample lot never keeps the sample's \"Ithaca Rd\"",
            "code", "partial", "The real box shows it in Rhino; here the box's state is read through the plugin's own "
            "on_confirm hook and the file's saved choices.",
            # since re-lookup (#26) Look up only previews: the open box still shows what is drawn (the sample's
            # street) until Draw, by design; the claim is about what the looked-up lot is saved with at Draw
            lambda: (u.get("saved_name") is None and not u.get("file")
                     and bool(n.get("saved_name")) and (n.get("fact") or {}).get("source") != "the State tax map (the sample's lookup)",
                     "GordiumStart on an empty file (the sample, \"Ithaca Rd\"), then 106 looked up with no street side in "
                     "the answer: box street name %s, saved %s, \"Ithaca Rd\" in the saved street name, street fact "
                     "or street ids: %s. With the street side: \"%s\" from \"%s\"." % (
                         u.get("street_name"), u.get("saved_name"), u.get("file"), n.get("street_name"),
                         n.get("street_source")), out))
    sample_source = "the State tax map (the sample's lookup)"
    guarded("pr19-street-6", "pr19", W, "Nor does it keep the sample's street source on the looked-up lot's street "
            "line", "code", "covered", "Nothing: this is the box's logic (rhino_logic.lookup_choices) and the facts "
            "file it writes.",
            lambda: (u.get("saved_source") != sample_source and (u.get("fact") or {}).get("source") != sample_source,
                     "The same unnamed run: the saved street source \"%s\"; saved at Draw as the street fact %s, on "
                     "the 8 street lines the lookup drew around 106 (not the sample's)." % (
                         u.get("saved_source"), u.get("fact")), out))


def main():
    for part in (part_a, part_tick, part_b, part_streets):
        try:
            part()
        except Exception:
            RAWLOG[part.__name__ + "_crashed"] = traceback.format_exc()
            print(traceback.format_exc(), flush=True)
            record(part.__name__ + "-setup", "pr23" if part in (part_a, part_tick) else "pr19", part.__name__,
                   "The headless run of this part could not finish its setup", "code", "none", False,
                   "Crashed before every claim was checked: " + traceback.format_exc().strip().splitlines()[-1][:200],
                   "All of it.", None)
    json.dump(RESULTS, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(RAWLOG, open(RAW, "w", encoding="utf-8"), indent=1, default=str, ensure_ascii=False)
    n = {k: sum(1 for r in RESULTS if r["offline"] == k) for k in ("covered", "partial", "none")}
    print("offline:", n, "passed:", sum(1 for r in RESULTS if r["offline_ok"] is True),
          "failed:", sum(1 for r in RESULTS if r["offline_ok"] is False))


if __name__ == "__main__":
    main()
