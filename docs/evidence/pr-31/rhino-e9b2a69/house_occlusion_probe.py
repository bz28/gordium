#! python3
"""Does the sample's house hide what is behind it in Shaded Front? A real red box behind it (in the doc, deleted
before close), the house's objects described, the Shaded mode's transparency settings. Writes house_occ.json."""
import json
import os
import sys
import traceback

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System

HERE = "/private/tmp/claude-501/-Users-benzhao-Documents-Gordium/bdb07cc0-1635-44d8-9b5a-34b881c6c09f/scratchpad/rhino_ui/"
WT = open(HERE + "fill_wt.txt", encoding="utf-8").read().strip()
OUT = HERE + "house_occ.json"
FR = HERE + "fill_frames/"
sys.path.insert(0, WT + "/apps/rhino_plugin/tests")
from test_docs_in_rhino import TestDocs, close  # noqa: E402
log = {}


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


def attr(obj, name):
    try:
        return str(getattr(obj, name))
    except Exception as ex:
        return "n/a"


doc = None
try:
    g = fresh_module()
    doc = TestDocs("houseocc").__enter__().open("Large Objects - Feet")
    g.gordium_check()
    o = g.overlay()
    houses = []
    box = rg.BoundingBox.Empty
    for x in g._buildings(doc):
        box.Union(x.Geometry.GetBoundingBox(True))
        layer = doc.Layers[x.Attributes.LayerIndex]
        mat = x.GetMaterial(True)
        houses.append({"type": x.Geometry.GetType().Name, "object_type": str(x.ObjectType),
                       "layer": layer.FullPath, "material_source": str(x.Attributes.MaterialSource),
                       "material_transparency": mat.Transparency if mat else None,
                       "layer_material_index": layer.RenderMaterialIndex,
                       "solid": attr(x.Geometry, "IsSolid"),
                       "faces": attr(getattr(x.Geometry, "Faces", None), "Count")})
    log["houses"] = houses
    dm = Rhino.Display.DisplayModeDescription.FindByName("Shaded")
    da = dm.DisplayAttributes
    log["shaded_mode"] = {k: attr(da, k) for k in ("ShadingEnabled", "ObjectTransparency" , "ShowSurfaceEdges",
                                                      "XRayAllObjects", "UseSingleColorForCurves")}
    view = doc.Views.Find("Front", False)
    vp = view.ActiveViewport
    vp.DisplayMode = dm
    vp.ZoomBoundingBox(o.box if o.box.IsValid else doc.Objects.BoundingBox)
    doc.Views.ActiveView = view
    log["found_shaded"] = [dm.EnglishName, str(dm.Id)]
    log["modes"] = [(m.EnglishName, str(m.Id)) for m in Rhino.Display.DisplayModeDescription.GetDisplayModes()]
    log["front_mode_after_set"] = [vp.DisplayMode.EnglishName, str(vp.DisplayMode.Id)]
    pv = doc.Views.Find("Perspective", False).ActiveViewport
    log["perspective_mode"] = pv.DisplayMode.EnglishName
    g.off()                                    # Gordium's drawing off: Rhino's own drawing only
    view.Redraw()
    plain = view.CaptureToBitmap(vp.Size)
    plain.Save(FR + "D0_house_only.png")
    behind = rg.Box(rg.BoundingBox(rg.Point3d(box.Min.X + 2, box.Max.Y + 5, 2),
                                   rg.Point3d(box.Max.X + 15, box.Max.Y + 10, box.Max.Z - 2)))
    attrs = Rhino.DocObjects.ObjectAttributes()
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attrs.ObjectColor = System.Drawing.Color.Red
    idx = doc.Materials.Add()
    m = doc.Materials[idx]
    m.DiffuseColor = System.Drawing.Color.Red
    m.CommitChanges()
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
    attrs.MaterialIndex = idx
    rid = doc.Objects.AddBrep(behind.ToBrep(), attrs)
    try:
        view.Redraw()
        withbox = view.CaptureToBitmap(vp.Size)
        withbox.Save(FR + "D1_red_box_behind_house.png")
        diffs = []
        for i in range(2, 9):
            for k in range(2, 9):
                p = rg.Point3d(box.Min.X + (box.Max.X - box.Min.X) * i / 10.0, box.Min.Y,
                               box.Min.Z + (box.Max.Z - box.Min.Z) * k / 10.0)
                q = vp.WorldToClient(p)
                a, b = plain.GetPixel(int(q.X), int(q.Y)), withbox.GetPixel(int(q.X), int(q.Y))
                diffs.append(max(abs(a.R - b.R), abs(a.G - b.G), abs(a.B - b.B)))
        log["red_box_behind"] = {"samples": len(diffs), "changed_over_24": sum(d > 24 for d in diffs),
                                 "median": sorted(diffs)[len(diffs) // 2]}
        q = vp.WorldToClient(rg.Point3d(box.Center.X, box.Min.Y, box.Center.Z))
        q2 = vp.WorldToClient(rg.Point3d(box.Max.X + 8, box.Min.Y, box.Center.Z))
        log["outside_house_pixel_with_box"] = str(withbox.GetPixel(int(q2.X), int(q2.Y)))
        q3 = vp.WorldToClient(rg.Point3d(box.Center.X + 3, box.Min.Y, box.Center.Z + 3))
        log["house_face_pixel_plain"] = str(plain.GetPixel(int(q3.X), int(q3.Y)))
        log["house_face_pixel_with_box"] = str(withbox.GetPixel(int(q3.X), int(q3.Y)))
        log["house_centre_pixel"] = str(plain.GetPixel(int(q.X), int(q.Y)))
    finally:
        doc.Objects.Delete(rid, True)
except Exception:
    log["trace"] = traceback.format_exc()
finally:
    if doc is not None:
        close(doc)
    log["done"] = True
    json.dump(log, open(OUT, "w", encoding="utf-8"), default=str, indent=1)
