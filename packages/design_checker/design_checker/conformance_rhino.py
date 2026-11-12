"""The conformance suite's Rhino side (conformance.py): each scene drawn as a .3dm, and the Rhino reference adapter,
which reads a .3dm with rhino3dm (no Rhino needed, so CI runs it) and sends what the Rhino command sends.

The adapter is what the Rhino command does at a check, done on a file: the lot and Building layers read by
read_site (the reader the command's exported copy goes through); the spot grades the command reads from
Gordium::Grade (gordium_rhino.check_facts); and every other object on the lot looked at, as the command's
_not_included, _touching and _ground_like do, with the same decisions (rhino_logic.could_be_building,
left_out_candidate, reaches_into_lot, looks_like_ground, context_left_out). What it can't do on a file is what lives
only in a live document (the terrain sampled at the walls, objects the architect marked as the ground); no scene
needs either.
"""

import uuid

import rhino3dm as r

from model_measurement.read_3dm import FLOOR_KEY, TO_FEET, _id, read_site

from . import conformance as c
from . import rhino_logic as logic
from . import site_json

HOST = "rhino3dm"
GRADE_LAYER = "Gordium::Grade"          # gordium_rhino.GRADE_LAYER: spot grades, point objects


def model_path(scene: dict, step: str = c.STEPS[0]):
    return c.MODELS / f"{scene['name']}{'' if step == c.STEPS[0] else '.after'}.3dm"


def _units(scene: dict) -> str:
    return (scene.get("model") or {}).get("units", "Feet")


def _layer(model, path: str) -> int:
    """The index of the layer at this full path ("Gordium::Grade"), made (with its parents) if new."""
    names = [layer.FullPath for layer in model.Layers]
    if path in names:
        return names.index(path)
    parent, _, name = path.rpartition("::")
    layer = r.Layer()
    layer.Name = name
    layer.Id = uuid.uuid5(c.NAMESPACE, f"layer/{path}")      # the same on every build, as every object's id
    if parent:
        layer.ParentLayerId = model.Layers.FindIndex(_layer(model, parent)).Id
    return model.Layers.Add(layer)


def _on(model, path: str, scene: dict, local: str | None = None):
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = _layer(model, path)
    if local is not None:
        attrs.Id = c.object_id(scene, local)
    return attrs


def _outline(points, z, k: float, arcs=None):
    """A closed outline at height z (model units, k per ft): straight lines, each edge `arcs` names ({edge: a
    point}) an arc through that point."""
    n = len(points)
    curve = r.PolyCurve()
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        if arcs and i in arcs:
            mid = arcs[i]
            curve.Append(r.ArcCurve.CreateFromArc(r.Arc(r.Point3d(a[0] * k, a[1] * k, z), r.Point3d(mid[0] * k, mid[1] * k, z),
                                                        r.Point3d(b[0] * k, b[1] * k, z))))
        else:
            curve.Append(r.LineCurve(r.Point3d(a[0] * k, a[1] * k, z), r.Point3d(b[0] * k, b[1] * k, z)))
    return curve


def _solid(s: dict, k: float):
    arcs = {s["curved"]["edge"]: s["curved"]["through"]} if s.get("curved") else None
    return r.Extrusion.Create(_outline(s["outline"], s["base"] * k, k, arcs), (s["top"] - s["base"]) * k,
                              not s.get("open")).ToBrep(True)


def _terrain(o: dict, k: float):
    """A flat open mesh over the object's outline's box at its base height, `cells` × `cells` squares."""
    (x0, y0), (x1, y1) = [min(p[0] for p in o["outline"]), min(p[1] for p in o["outline"])], \
        [max(p[0] for p in o["outline"]), max(p[1] for p in o["outline"])]
    n = o["mesh"]["cells"]
    mesh = r.Mesh()
    for j in range(n + 1):
        for i in range(n + 1):
            mesh.Vertices.Add((x0 + (x1 - x0) * i / n) * k, (y0 + (y1 - y0) * j / n) * k, o["base"] * k)
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            mesh.Faces.AddFace(a, a + 1, a + n + 2, a + n + 1)
    return mesh


def _place_block(model, name: str, solid, attrs) -> None:
    """The solid as a block's definition (on the placed block's own layer), placed once with `attrs`. rhino3dm
    gives the definition and the object inside it new ids on every build (an id set beforehand isn't kept); no
    reader uses them: readers skip a definition's objects, and read the placed block by its own id."""
    inside = r.ObjectAttributes()
    inside.LayerIndex = attrs.LayerIndex
    index = model.InstanceDefinitions.Add(name, "", "", "", r.Point3d(0, 0, 0), (solid,), (inside,))
    definition = model.InstanceDefinitions.FindIndex(index)
    model.Objects.AddInstanceObject(r.InstanceReference(definition.Id, r.Transform.Identity()), attrs)


def build(scene: dict) -> r.File3dm:
    """The scene as drawn, before its edit: the lot outline(s) on Site, each building solid on Building (floor
    blocks marked), the other solids on their layers, spot grades on Gordium::Grade; every object and layer with its
    fixed id (conformance.object_id; a block's definition and what is inside it excepted), in the scene's units."""
    model = r.File3dm()
    model.Settings.ModelUnitSystem = getattr(r.UnitSystem, _units(scene))
    k = c.FEET[_units(scene)]
    _layer(model, c.SITE_LAYER)
    _layer(model, c.BUILDING_LAYER)
    arcs = {i: arc["through"] for i, arc in c.lot_arcs(scene).items()}
    for n, (local, ring) in enumerate(zip(c.lot_ids(scene), c.lots(scene))):
        attrs = _on(model, c.SITE_LAYER, scene, local)
        if n == 0 and arcs:
            model.Objects.AddCurve(_outline(ring, 0, k, arcs), attrs)
        else:
            model.Objects.AddPolyline(r.Polyline([r.Point3d(x * k, y * k, 0) for x, y in ring + ring[:1]]), attrs)
    for s in c.solids(scene):
        attrs = _on(model, c.BUILDING_LAYER, scene, s["id"])
        if s["floor"] is not None:
            story = int(s["id"].rsplit("floor", 1)[1])
            attrs.SetUserString(FLOOR_KEY, f"{story};{s['floor']}")
        if s["block"]:                  # the solid as a block's definition, placed once on the Building layer
            _place_block(model, s["id"], _solid(s, k), attrs)
        else:
            model.Objects.AddBrep(_solid(s, k), attrs)
    for o in c.others(scene):
        attrs = _on(model, o["layer"], scene, o["id"])
        if o.get("mesh"):
            model.Objects.AddMesh(_terrain(o, k), attrs)
        elif o.get("block"):
            _place_block(model, o["id"], _solid(o, k), attrs)
        else:
            model.Objects.AddBrep(_solid(o, k), attrs)
    for n, p in enumerate(c.spot_grades(scene)):
        model.Objects.AddPoint(r.Point3d(p[0] * k, p[1] * k, p[2] * k), _on(model, GRADE_LAYER, scene, f"grade_{n + 1}"))
    return model


def edited(scene: dict, before) -> r.File3dm:
    """The scene after its edit, made the way an architect makes it: the model as saved, each building object
    moved in place (it keeps its id; nothing is redrawn), everything else left where it was."""
    dx, dy = scene["then"]["move"]
    k = c.FEET[_units(scene)]
    model = r.File3dm.Read(str(before))
    names = [layer.FullPath for layer in model.Layers]
    for o in model.Objects:
        if logic.on_layer(names[o.Attributes.LayerIndex], c.BUILDING_LAYER) and not o.Attributes.IsInstanceDefinitionObject:
            o.Geometry.Translate(r.Vector3d(dx * k, dy * k, 0))
    return model


def write_models(scene: dict) -> None:
    c.MODELS.mkdir(parents=True, exist_ok=True)
    build(scene).Write(str(model_path(scene)), 8)
    if scene.get("then"):
        edited(scene, model_path(scene)).Write(str(model_path(scene, c.STEPS[1])), 8)


def ids(scene: dict) -> dict:
    """{Rhino object id: the scene's id}, for every object the scene draws."""
    locals_ = c.lot_ids(scene) + [s["id"] for s in c.solids(scene)] + [o["id"] for o in c.others(scene)]
    return {c.object_id(scene, local): local for local in locals_}


# ---- the reference adapter ------------------------------------------------------------------------------------

def _kind(g) -> str:
    """The geometry's type name as RhinoCommon names it (rhino_logic's decisions are written in those names)."""
    return "InstanceReferenceGeometry" if isinstance(g, r.InstanceReference) else type(g).__name__


def _box(model, g, depth=0):
    """A geometry's 3D box, ((x0, y0, x1, y1), (z0, z1)), or None when it has none to give. A placed block's is
    its definition's objects' boxes moved by its placement (rhino3dm gives a block itself no box), blocks inside
    blocks too. None for a block, at any depth, whose definition isn't in the file, is empty, holds a part with
    none, or is linked to a file (any update type but Static), or whose box covers no ground (a point or a line:
    rhino_logic.plan_box_has_area), as gordium_rhino._whole_box gives none.

    A linked block is the one place the adapter and live Rhino see different things. A saved .3dm holds a Linked
    definition with no objects, and a LinkedAndEmbedded one with the copy last read, whether or not the file is
    still there; live Rhino reads the file, and when it isn't found (Rhino 8.35, Mac, 2026-11-12) gives the
    definition one text label at the centre of the last known shape (a valid box of a single point) and the status
    LinkedFileNotFound, which the command takes as no box (rhino_logic.block_contents_known). A file can't say
    whether the linked file is found and unchanged, so the adapter gives every linked block no box: on the lot
    and touching, the cautious side of the command's answer, and the same as it when the file is missing."""
    if isinstance(g, r.InstanceReference):
        definition = model.InstanceDefinitions.FindId(g.ParentIdefId)
        if definition is None or depth > 32 or definition.UpdateType != r.InstanceDefinitionUpdateType.Static:
            return None
        boxes = []
        for object_id in definition.GetObjectIds():
            o = model.Objects.FindId(object_id)
            box = _box(model, o.Geometry, depth + 1) if o is not None else None
            if box is None:
                return None
            (x0, y0, x1, y1), (z0, z1) = box
            b = g.Xform.TransformBoundingBox(r.BoundingBox(x0, y0, z0, x1, y1, z1))
            boxes.append(((b.Min.X, b.Min.Y, b.Max.X, b.Max.Y), (b.Min.Z, b.Max.Z)))
        if not boxes:
            return None
        plan = (min(b[0][0] for b in boxes), min(b[0][1] for b in boxes), max(b[0][2] for b in boxes),
                max(b[0][3] for b in boxes))
        return (plan, (min(b[1][0] for b in boxes), max(b[1][1] for b in boxes))) if logic.plan_box_has_area(plan) \
            else None
    b = g.GetBoundingBox()
    return ((b.Min.X, b.Min.Y, b.Max.X, b.Max.Y), (b.Min.Z, b.Max.Z)) if b.IsValid else None


def _plan_points(model, g):
    """Points of an object in plan, enough to outline it (gordium_rhino._plan_points): a curve's points along it; a
    mesh's vertices; a solid's vertices, points along its edges and over its faces (a dome's surface gives its
    outline); anything else (a block), its box's corners in order round it (bigger than it: the cautious
    direction), as for a mesh of over 50,000 vertices. None when it has nothing to outline it by."""
    pts = []
    if isinstance(g, r.Curve):
        poly = g.TryGetPolyline()
        if poly is not None and poly.Count >= 2:
            pts = [poly[i] for i in range(poly.Count)]
        else:
            t0, t1 = g.Domain.T0, g.Domain.T1
            pts = [g.PointAt(t0 + (t1 - t0) * k / 64) for k in range(65)]
    elif isinstance(g, r.Mesh):
        pts = [g.Vertices[i] for i in range(len(g.Vertices))]
    else:
        brep = g.ToBrep(True) if isinstance(g, r.Extrusion) else g if isinstance(g, r.Brep) else None
        if brep is not None:
            pts = [brep.Vertices[i].Location for i in range(len(brep.Vertices))]
            for i in range(len(brep.Edges)):
                e = brep.Edges[i]
                t0, t1 = e.Domain.T0, e.Domain.T1
                pts += [e.PointAt(t0 + (t1 - t0) * j / 8) for j in range(9)]
            for i in range(len(brep.Faces)):
                f = brep.Faces[i]
                u, v = f.Domain(0), f.Domain(1)
                pts += [f.PointAt(u.T0 + (u.T1 - u.T0) * a / 6, v.T0 + (v.T1 - v.T0) * b / 6)
                        for a in range(7) for b in range(7)]
    if not pts or len(pts) > 50000:
        box = _box(model, g)
        if box is None:
            return None
        x0, y0, x1, y1 = box[0]
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(p.X, p.Y) for p in pts]


def _left_out(model, lot, buildings, s: float) -> list[dict]:
    """Everything else on the lot that could be a building (gordium_rhino._not_included, with _touching,
    _ground_like and rhino_logic.context_left_out): each one a left-out object. One whose place can't be told (a
    block with nothing in it to measure, a linked block: _box) counts as on the lot and touching: never left off
    the list."""
    if lot is None:
        return []
    names = [layer.FullPath for layer in model.Layers]
    ring = _plan_points(model, lot.Geometry)
    reach = logic.ON_LOT_REACH / s                             # ft -> model units
    (lot_box, _), gap = _box(model, lot.Geometry), 0.1 / s
    boxes = [box for box in (_box(model, b.Geometry) for b in buildings) if box is not None]
    out = []
    for o in model.Objects:
        if o.Attributes.IsInstanceDefinitionObject:
            continue
        layer, g = names[o.Attributes.LayerIndex], o.Geometry
        solid = (isinstance(g, r.Brep) and g.IsSolid) or (isinstance(g, r.Mesh) and g.IsClosed) or \
            (isinstance(g, r.Extrusion) and g.ToBrep(True).IsSolid)
        faces = len(g.Faces) if isinstance(g, (r.Brep, r.Mesh)) else 0
        if not logic.could_be_building(_kind(g), solid, faces) or logic.on_layer(layer, c.BUILDING_LAYER) \
                or not logic.left_out_candidate(layer):
            continue
        box, points = _box(model, g), _plan_points(model, g)
        if box is None or points is None:
            touching = None                                  # not known: counts as touching
        else:
            (x0, y0, x1, y1), (z0, z1) = box
            if not logic.box_near_lot(box[0], lot_box, reach) or not logic.reaches_into_lot(ring, points, reach, box[0]):
                continue
            touching = any(x0 <= b[2] + gap and b[0] - gap <= x1 and y0 <= b[3] + gap and b[1] - gap <= y1
                           and z0 <= bz[1] + gap and bz[0] - gap <= z1 for b, bz in boxes)
        out.append({"id": _id(o), "layer": layer, "could_be_building": True, "touching": touching,
                    "ground_like": box is not None and logic.looks_like_ground(_kind(g), solid, box[0], lot_box),
                    "context": bool(logic.context_left_out({_id(o): layer}))})
    return out


def describe_file(path, facts: dict) -> dict:
    """A .3dm as the Rhino command sends it: a gordium.site/1 description, everything on the lot looked at."""
    site = read_site(path, facts)
    model = r.File3dm.Read(str(path))
    s = TO_FEET[model.Settings.ModelUnitSystem]
    names = [layer.FullPath for layer in model.Layers]
    placed = [o for o in model.Objects if not o.Attributes.IsInstanceDefinitionObject]
    points = [[p.X * s, p.Y * s, p.Z * s] for p in (o.Geometry.Location for o in placed
              if names[o.Attributes.LayerIndex] == GRADE_LAYER and isinstance(o.Geometry, r.Point))] \
        if facts.get("grade_from") == "spot" else []
    grade = {"source": "spot", "points": points} if points else {"source": "none", "points": []}
    lot = next((o for o in placed if site["lot"] is not None and _id(o) == site["lot"]["id"]), None)
    buildings = [o for o in placed if logic.on_layer(names[o.Attributes.LayerIndex], c.BUILDING_LAYER)]
    host = {"name": HOST, "version": r.__version__, "document": path.name,
            "model_units": str(model.Settings.ModelUnitSystem).split(".")[-1]}
    return site_json.from_read_site(site, grade, host, inventory_complete=True,
                                    left_out=_left_out(model, lot, buildings, s))


def describe(scene: dict, step: str = c.STEPS[0]) -> dict:
    return describe_file(model_path(scene, step), c.facts(scene))


def record(scene: dict) -> dict:
    """The reference adapter's recording of a scene, in the form any host records (conformance.recording_problems)."""
    return {"host": HOST, "scene": scene["name"], "ids": ids(scene),
            "recorded": {"by": "python -m design_checker.conformance --write", "tool": f"rhino3dm {r.__version__}"},
            "steps": {step: describe(scene, step) for step in c.steps(scene)}}
