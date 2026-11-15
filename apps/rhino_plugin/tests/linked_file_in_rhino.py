#! python3
"""A linked block whose file changed or moved (#93), in Rhino 8, each claim asserted. Run in Rhino, not in CI; the
logic is tested in CI (test_left_out.py, test_present.py, test_host_conformance.py). A fresh feet document, 106 Ithaca
Rd looked up (recorded answers, no live call) and drawn, then a garage block linked to garage.3dm placed on the lot
on the Default layer, away from the house:
1. Up to date: the "not included" row has no linked-file sentence; the garage is not counted as touching.
2. garage.3dm edited on disk (Rhino 8.35 Mac says LinkedFileIsDifferent): the row says "Linked file 'garage.3dm' has changed since it was
   loaded: reload it (Edit ▸ Blocks ▸ Block Definitions ...; or type -BlockManager, Update, All)"; it counts as
   touching (no box). Then Rhino's own command "-BlockManager Update All" (the sentence's words, run as a command):
   up to date again, the next check has no sentence and places the garage (not touching).
3. garage.3dm moved to another folder (LinkedFileNotFound): the row says it "can't be found at <old path>: relink it
   (... Properties ▸ Filename: Browse to the file)". The definition then pointed at the new path (what Browse does,
   through RhinoCommon's ModifySourceArchive: the dialog itself needs Rhino in front): no sentence, placed again.
4. A link inside a linked file: outer.3dm holds a block linked to inner.3dm; the document links outer.3dm. inner.3dm
   edited: what Rhino reports for each definition and which file the sentence names. Then the inner definition alone
   updated (UpdateLinkedInstanceDefinition on it, what selecting it and pressing Update does), and, if that doesn't
   clear it, "-BlockManager Update All". Recorded, not asserted (it is the open question).
Writes <temp>/gordium_linked_file/out.json ("ok": true at the end). Leaves its document open: close it with
close_test_docs_in_rhino.py once Rhino has idled (a few seconds), see the end of the script."""
import json
import os
import shutil
import sys
import tempfile
import time
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_docs_in_rhino import TestDocs, look_up_106  # noqa: E402

S = os.path.join(tempfile.gettempdir(), "gordium_linked_file") + "/"
LINKS = S + "links/"
WT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
log = {"claims": {}, "steps": {}, "notes": []}
LINKED = Rhino.DocObjects.InstanceDefinitionUpdateType.Linked


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


def write_box(path, size, later=0):
    """A .3dm in feet holding one box `size` feet wide, deep and high; its time `later` seconds ahead."""
    f = Rhino.FileIO.File3dm()
    f.Settings.ModelUnitSystem = Rhino.UnitSystem.Feet
    f.Objects.AddBrep(rg.Box(rg.Plane.WorldXY, rg.Interval(0, size), rg.Interval(0, size),
                             rg.Interval(0, 8)).ToBrep())
    assert f.Write(path, 8), path
    if later:
        t = time.time() + later
        os.utime(path, (t, t))


def link(doc, name, path):
    """A block definition linked to `path` (as Insert ▸ Link does), its index."""
    idx = doc.InstanceDefinitions.Add(name, "", rg.Point3d.Origin, [rg.Point(rg.Point3d.Origin)])
    assert idx >= 0, name
    assert doc.InstanceDefinitions.ModifySourceArchive(idx, path, LINKED, True), path
    return idx


def status(doc, idx):
    return str(doc.InstanceDefinitions[idx].ArchiveFileStatus)


def statuses(doc):
    return {d.Name: [str(d.ArchiveFileStatus), d.SourceArchive] for d in doc.InstanceDefinitions if not d.IsDeleted}


def spot(g, doc, facts, size):
    """A point on the lot where a `size` ft square fits inside the lot, at least 10 ft from every building's box."""
    lot = g._find(doc, facts["lot_id"]).Geometry
    boxes = [o.Geometry.GetBoundingBox(True) for o in g._buildings(doc)]
    b = lot.GetBoundingBox(True)
    best = None
    for i in range(1, 40):
        for j in range(1, 40):
            p = rg.Point3d(b.Min.X + (b.Max.X - b.Min.X) * i / 40.0, b.Min.Y + (b.Max.Y - b.Min.Y) * j / 40.0, 0)
            corners = [p + rg.Vector3d(dx, dy, 0) for dx in (-2, size + 2) for dy in (-2, size + 2)]
            if not all(lot.Contains(c, rg.Plane.WorldXY, 0.01) == rg.PointContainment.Inside for c in corners):
                continue
            far = min(min(abs(c.X - min(max(c.X, bb.Min.X), bb.Max.X)) + abs(c.Y - min(max(c.Y, bb.Min.Y), bb.Max.Y))
                          for c in corners) for bb in boxes) if boxes else 99
            if far > 10 and (best is None or far > best[0]):
                best = (far, p)
    assert best, ("no spot on the lot", type(lot).__name__, lot.IsClosed, [b.Min, b.Max],
                  [[bb.Min, bb.Max] for bb in boxes], lot.Contains(b.Center, rg.Plane.WorldXY, 0.01))
    return best[1]


def check(g, begun, label):
    g.check_now()
    ex = begun[-1]["extras"]
    items = (g.STATE.get("last") or {}).get("items") or []
    row = next((i.get("reason") for i in items if "on the lot" in (i.get("reason") or "")
                and "measured (not on the Building layer)" in (i.get("reason") or "")), None)
    out = {"row": row, "not_included": ex.get("not_included"), "touching": ex.get("touching"),
           "advice": ex.get("left_out_advice"), "statuses": statuses(Rhino.RhinoDoc.ActiveDoc)}
    log["steps"][label] = out
    return out


def command(doc, macro):
    """Run Rhino's own command with its options, as Rhino's own "Update all linked blocks" macro does (RunScript: a
    macro with options; RhinoApp.ExecuteCommand takes a command name only and answers UnknownCommand to one)."""
    r = Rhino.RhinoApp.RunScript(macro, True)
    log["notes"].append("RunScript(%r) -> %s" % (macro, r))
    return r


docs = TestDocs("linkedfile").__enter__()
doc = None
try:
    shutil.rmtree(S, ignore_errors=True)
    os.makedirs(LINKS + "moved")
    g = fresh_module()
    begun = []
    begin = g._check_begin

    def spy(*a, **k):
        out = begin(*a, **k)
        begun.append(out)
        return out

    g._check_begin = spy
    doc = docs.open("Large Objects - Feet")
    look_up_106(g, g.gordium_check)
    facts = g.load_facts(doc)
    garage = LINKS + "garage.3dm"
    write_box(garage, 12)
    gi = link(doc, "garage", garage)
    at = spot(g, doc, facts, 12)
    gid = str(doc.Objects.AddInstanceObject(gi, rg.Transform.Translation(rg.Vector3d(at))))
    log["garage"] = {"id": gid, "at": [at.X, at.Y], "status": status(doc, gi)}
    claim("the garage block is linked and up to date", status(doc, gi).endswith("LinkedFileIsUpToDate"), log["garage"])

    a = check(g, begun, "1_up_to_date")
    claim("1. up to date: left out, no linked-file sentence, not touching", gid in (a["not_included"] or []) and
          "Linked file" not in (a["row"] or "") and gid not in (a["touching"] or []), a)

    write_box(garage, 20, later=120)
    log["after_edit_status"] = status(doc, gi)
    b = check(g, begun, "2_changed")
    claim("2. edited file: Rhino says it changed (LinkedFileIsNewer / IsDifferent)",
          log["after_edit_status"].endswith(("LinkedFileIsNewer", "LinkedFileIsDifferent")),
          log["after_edit_status"])
    claim("2. the row names garage.3dm and says to reload it with Rhino's menu words",
          "Linked file 'garage.3dm' has changed since it was loaded: reload it (Edit ▸ Blocks ▸ Block Definitions, "
          "select it, then Update; or type -BlockManager, Update, All) so Gordium can see where it is"
          in (b["row"] or ""), b["row"])
    claim("2. while changed, the garage counts as touching", gid in (b["touching"] or []), b["touching"])

    command(doc, "_-BlockManager _Update _All _Enter")
    log["after_update_status"] = status(doc, gi)
    claim("2. -BlockManager Update All: up to date again", log["after_update_status"].endswith("LinkedFileIsUpToDate"),
          log["after_update_status"])
    gb = doc.Objects.FindId(System.Guid(gid)).Geometry.GetBoundingBox(True)
    log["garage_box_after_update"] = [gb.Max.X - gb.Min.X, gb.Max.Y - gb.Min.Y]
    c = check(g, begun, "2_updated")
    claim("2. after Update: the edited (20 ft) garage is what is in the model",
          abs(log["garage_box_after_update"][0] - 20) < 0.01, log["garage_box_after_update"])
    claim("2. after Update: no sentence, the garage placed by its shape (not touching)",
          "Linked file" not in (c["row"] or "") and gid in (c["not_included"] or []) and
          gid not in (c["touching"] or []), c)

    moved = LINKS + "moved/garage.3dm"
    shutil.move(garage, moved)
    log["after_move_status"] = status(doc, gi)
    d = check(g, begun, "3_moved")
    claim("3. moved file: Rhino says LinkedFileNotFound", log["after_move_status"].endswith("LinkedFileNotFound"),
          log["after_move_status"])
    claim("3. the row says where it was looked for and to relink it with Browse",
          ("Linked file 'garage.3dm' can't be found at %s: relink it to where the file is now (Edit ▸ Blocks ▸ Block "
           "Definitions, select it, then Properties ▸ Filename: Browse to the file) so Gordium can see where it is"
           % garage) in (d["row"] or ""), d["row"])
    claim("3. while missing, the garage counts as touching", gid in (d["touching"] or []), d["touching"])
    ok = doc.InstanceDefinitions.ModifySourceArchive(gi, moved, LINKED, True)
    log["after_browse_status"] = status(doc, gi)
    e = check(g, begun, "3_relinked")
    claim("3. pointed at the new place (Browse): up to date, no sentence, placed (not touching)", ok and
          log["after_browse_status"].endswith("LinkedFileIsUpToDate") and "Linked file" not in (e["row"] or "")
          and gid not in (e["touching"] or []), e)

    # 4. a link inside a linked file (recorded, the open question)
    inner, outer = LINKS + "inner.3dm", LINKS + "outer.3dm"
    write_box(inner, 6)
    hd = Rhino.RhinoDoc.CreateHeadless(None)
    try:
        hd.ModelUnitSystem = Rhino.UnitSystem.Feet
        ii = link(hd, "inner", inner)
        hd.Objects.AddInstanceObject(ii, rg.Transform.Identity)
        assert hd.Write3dmFile(outer, Rhino.FileIO.FileWriteOptions()), outer
    finally:
        hd.Dispose()
    oi = link(doc, "outer", outer)
    at2 = spot(g, doc, facts, 12)
    oid = str(doc.Objects.AddInstanceObject(oi, rg.Transform.Translation(rg.Vector3d(at2))))
    log["nested"] = {"id": oid, "linked": statuses(doc)}
    n0 = check(g, begun, "4_nested_up_to_date")
    write_box(inner, 14, later=240)
    log["nested"]["after_inner_edit"] = statuses(doc)
    n1 = check(g, begun, "4_nested_inner_changed")
    log["nested"]["advice"] = (n1["advice"] or {}).get(oid)
    # the inner definition alone, as selecting it in Block Definitions and pressing Update does
    inner_defs = [d for d in doc.InstanceDefinitions if not d.IsDeleted and d.SourceArchive
                  and os.path.basename(d.SourceArchive) == "inner.3dm"]
    log["nested"]["inner_defs"] = [(d.Name, d.Index, str(d.ArchiveFileStatus), str(d.UpdateType)) for d in inner_defs]
    tried = []
    for d in inner_defs:
        tried.append(("UpdateLinkedInstanceDefinition(inner)", d.Name,
                      doc.InstanceDefinitions.UpdateLinkedInstanceDefinition(d.Index, d.SourceArchive, False, True)))
    log["nested"]["after_inner_update"] = statuses(doc)
    n2 = check(g, begun, "4_nested_after_inner_update")
    log["nested"]["inner_update_cleared"] = oid not in (n2["advice"] or {}) and oid not in (n2["touching"] or [])
    if not log["nested"]["inner_update_cleared"]:
        tried.append(("-BlockManager Update All", None, command(doc, "_-BlockManager _Update _All _Enter")))
        log["nested"]["after_update_all"] = statuses(doc)
        n3 = check(g, begun, "4_nested_after_update_all")
        log["nested"]["update_all_cleared"] = oid not in (n3["advice"] or {}) and oid not in (n3["touching"] or [])
    log["nested"]["tried"] = tried
    log["ok"] = True
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    try:                                   # nothing left stale on disk for Rhino to ask about later
        for d in (doc.InstanceDefinitions if doc is not None else []):
            if not d.IsDeleted and d.SourceArchive and not str(d.ArchiveFileStatus).endswith(
                    ("UpToDate", "NotALinkedInstanceDefinition")):
                log["notes"].append("left stale at the end: %s %s" % (d.Name, d.ArchiveFileStatus))
    except Exception:
        pass
    # The document is NOT closed here: Rhino 8.35 (Mac) rebuilds its block list after the script ends
    # (-[MRDocument _buildInstanceDefinitions]) and crashed when this script had closed the document holding the new
    # definitions (2026-11-13). Close it with a second script after Rhino has idled: close_test_docs_in_rhino.py.
    os.makedirs(S, exist_ok=True)
    json.dump(log, open(S + "out.json", "w", encoding="utf-8"), default=str, indent=1)
