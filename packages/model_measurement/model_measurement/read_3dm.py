"""Read a Rhino file into the plain geometry `measure()` works on, with rhino3dm (Rhino's own file library,
no Rhino needed). The Rhino command uses this same reader: it exports the lot and buildings to a small .3dm
and hands it over, so a file on disk and a live model are measured by one code path.

Which objects: the lot is the closed outline on the lot layer ("Site"), or the one the architect picked
(`lot_id` in the lot facts) when there are several; buildings are the solids and meshes on the building layer
("Building"). Anything that can't be read exactly (a curved wall, a solid that isn't closed, two candidate lot
outlines) is reported as a problem, never guessed.
"""

import math
import struct
from pathlib import Path

import rhino3dm as r

LAYERS = {"lot": "Site", "building": "Building"}
TO_FEET = {r.UnitSystem.Feet: 1.0, r.UnitSystem.Inches: 1 / 12, r.UnitSystem.Millimeters: 1 / 304.8,
           r.UnitSystem.Centimeters: 1 / 30.48, r.UnitSystem.Meters: 1 / 0.3048}
ARC_STEP = 0.25           # ft: a curved lot line is followed with points this far apart (at most)
ID_KEY = "gordium:id"     # the original object's id, when the Rhino command exported a copy


def _id(obj) -> str:
    return obj.Attributes.GetUserString(ID_KEY) or str(obj.Attributes.Id)


def _xyz(p, s):
    return [p.X * s, p.Y * s, p.Z * s]


def _straight(c):
    """The corner points of a curve made only of straight pieces, or None if any piece is curved."""
    if isinstance(c, r.PolylineCurve):
        return [c.Point(i) for i in range(c.PointCount)]
    if c.IsLinear():
        return [c.PointAtStart, c.PointAtEnd]
    polyline = c.TryGetPolyline()
    return [polyline[i] for i in range(polyline.Count)] if polyline is not None and polyline.Count >= 2 else None


def _edges(curve, s):
    """A closed curve as lot lines: each straight piece is one line; each curved piece is followed closely."""
    pieces = [curve.SegmentCurve(i) for i in range(curve.SegmentCount)] if isinstance(curve, r.PolyCurve) else [curve]
    edges = []
    for c in pieces:
        pts = _straight(c)
        if pts is not None:
            edges += [{"points": [_xyz(a, s)[:2], _xyz(b, s)[:2]], "curved": False}
                      for a, b in zip(pts, pts[1:]) if a.DistanceTo(b) > 0]
            continue
        t0, t1 = c.Domain.T0, c.Domain.T1
        rough = sum(c.PointAt(t0 + (t1 - t0) * k / 64).DistanceTo(c.PointAt(t0 + (t1 - t0) * (k + 1) / 64))
                    for k in range(64)) * s
        n = max(16, math.ceil(rough / ARC_STEP))
        edges.append({"points": [_xyz(c.PointAt(t0 + (t1 - t0) * k / n), s)[:2] for k in range(n + 1)],
                      "curved": True})
    return edges


def _brep_faces(brep, s):
    """Each face of a solid as a flat polygon (outer loop, holes). A curved face or curved edge can't be
    measured exactly yet, so it is reported, never approximated."""
    verts = [brep.Vertices[i].Location for i in range(len(brep.Vertices))]
    faces, problems = [], []
    for i in range(len(brep.Faces)):
        f = brep.Faces[i]
        if not f.IsPlanar():
            problems.append("a building has a curved surface (not measured yet)")
            continue
        loops = [f.Loops[k] for k in range(len(f.Loops))]
        trims = [[loop.Trims[k] for k in range(loop.TrimCount)] for loop in loops]
        if any(not brep.Edges[t.EdgeIndex].IsLinear() for ts in trims for t in ts):
            problems.append("a building has a curved edge (not measured yet)")
            continue
        rings = [(loop.LoopType, [_xyz(verts[t.StartVertexIndex], s) for t in ts]) for loop, ts in zip(loops, trims)]
        outer = [ring for kind, ring in rings if kind == r.BrepLoopType.Outer]
        faces.append({"points": outer[0] if outer else rings[0][1],
                      "holes": [ring for kind, ring in rings if kind == r.BrepLoopType.Inner]})
    return faces, sorted(set(problems))


FLOAT_SAFE = 2.0 ** 17      # ft from the origin: beyond this, single-precision points are coarser than 0.01 ft


def _single(x: float) -> bool:
    """Whether a number is exactly a single-precision value (as a mesh point stored only in single precision is)."""
    return struct.unpack("f", struct.pack("f", x))[0] == x


def _mesh_faces(mesh, s):
    """A mesh's faces (quads split into triangles), on the full-precision points the file holds, and its
    problems: a mesh stored only in single precision far from the origin (survey coordinates) can't be measured
    to 0.01 ft, so it is reported, never measured on rounded points."""
    v = mesh.Vertices
    points = [v.Point3dAt(k) for k in range(len(v))]
    problems = []
    far = any(max(abs(p.X), abs(p.Y), abs(p.Z)) * s > FLOAT_SAFE for p in points)
    if far and all(_single(c) for p in points for c in (p.X, p.Y, p.Z)):   # only single-precision points held
        problems.append("a building mesh is stored in single precision too far from the origin to measure to 0.01 ft "
                        "(move it nearer the origin, or turn it into a solid)")
    faces = []
    for i in range(len(mesh.Faces)):
        a, b, c, d = mesh.Faces[i]
        pts = [_xyz(points[k], s) for k in ((a, b, c) if c == d else (a, b, c, d))]
        faces += [{"points": pts}] if len(pts) == 3 else [{"points": [pts[0], pts[1], pts[2]]},
                                                          {"points": [pts[0], pts[2], pts[3]]}]
    return faces, problems


def _block_holds(model, ref, names, layer, depth=0) -> bool:
    """Whether a placed block holds, at any depth of blocks inside blocks, an object on the layer (or below it)."""
    definition = model.InstanceDefinitions.FindId(ref.ParentIdefId)
    if definition is None or depth > 32:
        return depth > 32                       # a loop of blocks: report rather than miss
    for object_id in definition.GetObjectIds():
        o = model.Objects.FindId(object_id)
        if o is None:
            continue
        name = names[o.Attributes.LayerIndex]
        if name == layer or name.startswith(layer + "::"):
            return True
        if isinstance(o.Geometry, r.InstanceReference) and _block_holds(model, o.Geometry, names, layer, depth + 1):
            return True
    return False


def read_site(path: Path, facts: dict, layers: dict = LAYERS) -> dict:
    """The lot and buildings in a .3dm, in feet: {"units", "lot", "buildings", "problems"}."""
    model = r.File3dm.Read(str(path))
    if model is None:
        return {"units": "ft", "lot": None, "buildings": [], "problems": [f"can't read {path}"]}
    s = TO_FEET.get(model.Settings.ModelUnitSystem)
    if s is None:
        return {"units": "ft", "lot": None, "buildings": [],
                "problems": [f"the model's units ({model.Settings.ModelUnitSystem}) aren't supported"]}
    names = [layer.FullPath for layer in model.Layers]

    def inside(name, layer):            # a layer and its sublayers ("Building::Garage")
        return name == layer or name.startswith(layer + "::")

    placed = [o for o in model.Objects if not o.Attributes.IsInstanceDefinitionObject]   # not a block's definition
    on = {k: [o for o in placed if inside(names[o.Attributes.LayerIndex], v)] for k, v in layers.items()}
    problems = [] if layers["lot"] in names else [f"no {layers['lot']} layer"]
    # a block's objects keep their own layers wherever the block is placed: a block holding anything on the
    # lot or building layer (at any depth) is reported, never read at its definition's place or dropped
    blocks = {k: False for k in layers}
    for o in placed:
        if isinstance(o.Geometry, r.InstanceReference):
            for k, v in layers.items():
                blocks[k] |= inside(names[o.Attributes.LayerIndex], v) or _block_holds(model, o.Geometry, names, v)
    if blocks["lot"]:
        problems.append(f"a block on the {layers['lot']} layer can't be read yet (explode it)")

    closed = [o for o in on["lot"] if isinstance(o.Geometry, r.Curve) and o.Geometry.IsClosed]
    picked = [o for o in closed if _id(o) == facts.get("lot_id")]
    lot = None
    if facts.get("lot_id") and not picked:
        problems.append("the lot picked isn't a closed outline on the Site layer: pick the lot again")
    elif picked or len(closed) == 1:
        o = (picked or closed)[0]
        lot = {"id": _id(o), "edges": _edges(o.Geometry, s)}
    elif not closed:
        problems.append(f"no closed lot outline on the {layers['lot']} layer")
    else:
        problems.append(f"{len(closed)} closed outlines on the {layers['lot']} layer: pick the lot")

    buildings, unread = [], set()
    for o in on["building"]:
        g = o.Geometry
        if isinstance(g, r.Extrusion):
            g = g.ToBrep(True)
        if isinstance(g, (r.Curve, r.Point, r.PointCloud, r.TextDot, r.AnnotationBase, r.Hatch)):
            continue                            # drawing aids, not building
        if isinstance(g, r.InstanceReference):
            continue                            # reported below, with blocks placed on any layer
        if not isinstance(g, (r.Brep, r.Mesh)):
            unread.add(f"a {type(g).__name__}")
        elif isinstance(g, r.Brep):
            faces, trouble = _brep_faces(g, s)
            if not g.IsSolid:
                trouble.append("a building isn't a closed solid")
            buildings.append({"id": _id(o), "faces": faces, "problems": trouble})
        elif isinstance(g, r.Mesh):
            faces, trouble = _mesh_faces(g, s)
            buildings.append({"id": _id(o), "faces": faces,
                              "problems": trouble + ([] if g.IsClosed else ["a building mesh isn't closed"])})
    if blocks["building"]:
        unread.add("a block")
    for kind in sorted(unread):                 # never dropped silently: the coverage and yards would be wrong
        buildings.append({"id": kind, "faces": [], "problems": [
            f"{kind} on the {layers['building']} layer can't be measured yet (explode it or turn it into a solid)"]})
    return {"units": "ft", "lot": lot, "buildings": buildings, "problems": problems}
