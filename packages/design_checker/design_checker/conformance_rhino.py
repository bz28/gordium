"""The conformance suite's Rhino side (conformance.py): each scene drawn as a .3dm, and the Rhino reference adapter,
which reads a .3dm with rhino3dm (no Rhino needed, so CI runs it) and sends what the Rhino command sends.

The adapter is what the Rhino command does at a check, done on a file: the lot and Building layers read by
read_site (the reader the command's exported copy goes through); the spot grades the command reads from
Gordium::Grade (gordium_rhino.check_facts); and every other object on the lot looked at, as the command's
_not_included, _touching and _ground_like do, with the same decisions (rhino_logic.could_be_building,
left_out_candidate, looks_like_ground, context_left_out; and which are on the lot and touching, asked of the
worker's objects.left_out as any host asks it). What it can't do on a file is what lives
only in a live document (the terrain sampled at the walls, objects the architect marked as the ground); no scene
needs either.
"""

import uuid

import rhino3dm as r

from model_measurement.read_3dm import FLOOR_KEY, TO_FEET, _id, read_site

from . import conformance as c
from . import protocol
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


def _mesh(s: dict, k: float):
    """The solid as a closed mesh of triangles (conformance.mesh_faces of its faces), corners shared, so it is
    closed: every edge between two triangles."""
    mesh, at = r.Mesh(), {}
    for f in c.mesh_faces(c._ring_faces(s["outline"], s["base"], s["top"])):
        ids = []
        for p in f["points"]:
            key = tuple(p)
            if key not in at:
                at[key] = len(at)
                mesh.Vertices.Add(p[0] * k, p[1] * k, p[2] * k)
            ids.append(at[key])
        mesh.Faces.AddFace(*ids)
    return mesh


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


def _definition(model, name: str, geometry, layers) -> r.InstanceReference:
    """A block's definition holding the geometry (each on its layer index, or with its attributes), and a
    placement of it where drawn. rhino3dm gives the definition and the objects inside it new ids on every build (an
    id set beforehand isn't kept); no reader uses them: readers skip a definition's objects, and read the placed
    block by its own id."""
    attrs = []
    for layer in layers:
        if isinstance(layer, r.ObjectAttributes):
            attrs.append(layer)
        else:
            attrs.append(r.ObjectAttributes())
            attrs[-1].LayerIndex = layer
    index = model.InstanceDefinitions.Add(name, "", "", "", r.Point3d(0, 0, 0), tuple(geometry), tuple(attrs))
    return r.InstanceReference(model.InstanceDefinitions.FindIndex(index).Id, r.Transform.Identity())


def _place_block(model, name: str, solid, attrs) -> None:
    """The solid as a block's definition (on the placed block's own layer), placed once with `attrs`."""
    model.Objects.AddInstanceObject(_definition(model, name, (solid,), (attrs.LayerIndex,)), attrs)


def _floor_attrs(model, s: dict):
    """A building solid's attributes on the Building layer, a floor block marked as GordiumStart marks it."""
    attrs = r.ObjectAttributes()
    attrs.LayerIndex = _layer(model, c.BUILDING_LAYER)
    if s["floor"] is not None:
        story = int(s["id"].rsplit("floor", 1)[1])
        attrs.SetUserString(FLOOR_KEY, f"{story};{s['floor']}")
    return attrs


def _other_block(model, o: dict, k: float, scene: dict, attrs) -> None:
    """One of `others` drawn as a block on its layer: its solid; or, with `empty`, only an empty solid (no faces,
    so no box: a family instance with no geometry); with `nested_empty`, its solid and a block inside it holding
    only an empty solid; with `holds_buildings`, the building solids whose `in_block` names it, on the Building
    layer inside it."""
    if o.get("holds_buildings"):
        inside = [s for s in c.solids(scene) if s["in_block"] == o["id"]]
        ref = _definition(model, o["id"], [_solid(s, k) for s in inside], [_floor_attrs(model, s) for s in inside])
    elif o.get("empty"):
        ref = _definition(model, o["id"], (r.Brep(),), (attrs.LayerIndex,))
    elif o.get("nested_empty"):
        nested = _definition(model, f"{o['id']}_part", (r.Brep(),), (attrs.LayerIndex,))
        ref = _definition(model, o["id"], (_solid(o, k), nested), (attrs.LayerIndex, attrs.LayerIndex))
    else:
        ref = _definition(model, o["id"], (_solid(o, k),), (attrs.LayerIndex,))
    model.Objects.AddInstanceObject(ref, attrs)


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
        elif n in c.open_lots(scene):   # every line but the last: its ends don't meet
            model.Objects.AddPolyline(r.Polyline([r.Point3d(x * k, y * k, 0) for x, y in ring]), attrs)
        else:
            model.Objects.AddPolyline(r.Polyline([r.Point3d(x * k, y * k, 0) for x, y in ring + ring[:1]]), attrs)
    group = None
    if scene.get("group"):              # rhino3dm's Groups.Add gives nothing back: the new group is the last
        model.Groups.Add(r.Group())
        group = len(model.Groups) - 1
    for s in c.solids(scene):
        if s["in_block"]:               # drawn inside its block (one of `others`), below
            continue
        attrs = _floor_attrs(model, s)
        attrs.Id = c.object_id(scene, s["id"])
        if group is not None:           # one group of every building solid (a model group, in Revit)
            attrs.AddToGroup(group)
        if s["block"]:                  # the solid as a block's definition, placed once on the Building layer
            _place_block(model, s["id"], _solid(s, k), attrs)
        elif s["mesh"]:
            model.Objects.AddMesh(_mesh(s, k), attrs)
        else:
            model.Objects.AddBrep(_solid(s, k), attrs)
    for o in c.others(scene):
        attrs = _on(model, o["layer"], scene, o["id"])
        if o.get("mesh"):
            model.Objects.AddMesh(_terrain(o, k), attrs)
        elif o.get("block") or o.get("holds_buildings"):
            _other_block(model, o, k, scene, attrs)
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
    locals_ = c.lot_ids(scene) + [s["id"] for s in c.solids(scene) if not s["in_block"]] + \
        [o["id"] for o in c.others(scene)]
    return {c.object_id(scene, local): local for local in locals_}


# ---- the reference adapter ------------------------------------------------------------------------------------

def _kind(g) -> str:
    """The geometry's type name as RhinoCommon names it (rhino_logic's decisions are written in those names)."""
    return "InstanceReferenceGeometry" if isinstance(g, r.InstanceReference) else type(g).__name__


def _box(model, g):
    """A geometry's 3D box, ((x0, y0, x1, y1), (z0, z1)), or None when it has none that covers all of it: what the
    file says of it (_seen), judged by host_core.left_out.no_box_reasons, the decision every host's left-out
    objects get (used here for the lot, the buildings and a block's plan points). A placed block's box is its
    definition's objects' boxes moved by its placement (rhino3dm gives a block itself no box), blocks inside blocks
    too; none for a block, at any depth, whose definition isn't in the file, is empty, holds a part with none, or
    is linked to a file (any update type but Static).

    A linked block is the one place the adapter and live Rhino see different things. A saved .3dm holds a Linked
    definition with no objects, and a LinkedAndEmbedded one with the copy last read, whether or not the file is
    still there; live Rhino reads the file, and when it isn't found (Rhino 8.35, Mac, 2026-11-12) gives the
    definition one text label at the centre of the last known shape (a valid box of a single point) and the status
    LinkedFileNotFound, which the command takes as no box (rhino_logic.block_contents_known). A file can't say
    whether the linked file is found and unchanged, so the adapter gives every linked block no box: on the lot
    and touching, the cautious side of the command's answer, and the same as it when the file is missing."""
    definitions = {}
    seen = dict(_seen(model, g, definitions), id="-")
    if logic.no_box_reasons([seen], definitions)[0]["why"] is not None:
        return None
    x0, y0, z0, x1, y1, z1 = seen["box"]
    return (x0, y0, x1, y1), (z0, z1)


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


def _seen(model, g, definitions) -> dict:
    """What a file says of one object, as host_core.left_out reads it (gordium_rhino._seen): its box, and for a
    placed block its definition's id (None when the file hasn't it), with what that definition holds and its status
    put into `definitions` once. rhino3dm gives a block itself no box, so its box is its definition's parts' boxes
    moved by its placement and joined, any part with none left out, as live Rhino joins them. A file can't say
    whether a linked block's file is found and unchanged (_box), so every definition but a Static one gets a
    status that isn't BLOCK_CONTENTS_KNOWN: no box, the cautious side of the command's answer (_box)."""
    if not isinstance(g, r.InstanceReference):
        b = g.GetBoundingBox()
        return {"box": [b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z] if b.IsValid else None}
    definition = model.InstanceDefinitions.FindId(g.ParentIdefId)
    key = None if definition is None else str(g.ParentIdefId)
    if key is not None and key not in definitions:
        entry = definitions[key] = {"status": None, "parts": []}            # before its parts: once
        static = definition.UpdateType == r.InstanceDefinitionUpdateType.Static
        entry["status"] = "NotALinkedInstanceDefinition" if static else \
            "unknown in a saved file (%s)" % str(definition.UpdateType).split(".")[-1]
        for object_id in definition.GetObjectIds():
            o = model.Objects.FindId(object_id)
            entry["parts"].append(_seen(model, o.Geometry, definitions) if o is not None else {"box": None})
    boxes = []
    for part in (definitions[key]["parts"] if key is not None else []):
        if part["box"] is not None:
            x0, y0, z0, x1, y1, z1 = part["box"]
            b = g.Xform.TransformBoundingBox(r.BoundingBox(x0, y0, z0, x1, y1, z1))
            boxes.append([b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z])
    box = [min(b[0] for b in boxes), min(b[1] for b in boxes), min(b[2] for b in boxes),
           max(b[3] for b in boxes), max(b[4] for b in boxes), max(b[5] for b in boxes)] if boxes else None
    return {"box": box, "definition": key}


def _left_out(model, lot, buildings, s: float) -> list[dict]:
    """Everything else on the lot that could be a building (gordium_rhino._not_included, with _touching,
    _ground_like and rhino_logic.context_left_out): each one a left-out object. Which are on the lot and touching
    is the worker's session command objects.left_out (host_core.left_out), asked as any host asks it, with what
    the file says of each object (_seen) and of the lot and the buildings. One whose place can't be told (a block
    with nothing in it to measure, a linked block) counts as on the lot and touching: never left off the list."""
    if lot is None:
        return []
    names = [layer.FullPath for layer in model.Layers]
    (x0, y0, x1, y1), _ = _box(model, lot.Geometry)
    boxes = []
    for b in buildings:
        box = _box(model, b.Geometry)
        if box is not None:
            (a0, b0, a1, b1), (c0, c1) = box
            boxes.append([a0, b0, c0, a1, b1, c1])
    kept, objects, definitions = [], [], {}
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
        seen = dict(_seen(model, g, definitions), id=_id(o))
        points = _plan_points(model, g)
        if points is not None:
            seen["points"] = [list(p) for p in points]
        kept.append((o, layer, g, solid, seen["box"]))
        objects.append(seen)
    answer = protocol.run("objects.left_out", {
        "lot": {"ring": [list(p) for p in _plan_points(model, lot.Geometry)], "box": [x0, y0, x1, y1]},
        "objects": objects, "definitions": definitions, "buildings": boxes, "feet_per_unit": s,
        "want": ["left_out", "touching"]})
    if answer.get("refused"):                  # host_core refused what the file said: never read as nothing left out
        raise ValueError("objects.left_out refused: " + "; ".join(f"{k}: {v}" for k, v in answer["refused"].items()))
    out = []
    for (o, layer, g, solid, box), on, near in zip(kept, answer["left_out"], answer["touching"]):
        if not on["left_out"]:
            continue
        out.append({"id": _id(o), "layer": layer, "could_be_building": True, "touching": near["touching"],
                    "ground_like": near["touching"] is not None
                    and logic.looks_like_ground(_kind(g), solid, (box[0], box[1], box[3], box[4]), (x0, y0, x1, y1)),
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
