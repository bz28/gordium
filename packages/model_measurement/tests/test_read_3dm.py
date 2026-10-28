"""Reading Rhino files: units, which object is the lot, solids and meshes, and what can't be read exactly."""

import pytest
import rhino3dm as r

from model_measurement.measure import measure
from model_measurement.read_3dm import ID_KEY, read_site


def model(units=r.UnitSystem.Feet, layers=("Site", "Building")):
    m = r.File3dm()
    m.Settings.ModelUnitSystem = units
    for name in layers:
        layer = r.Layer()
        layer.Name = name
        m.Layers.Add(layer)
    return m


def on(layer):
    a = r.ObjectAttributes()
    a.LayerIndex = layer
    return a


def rect(m, x0, y0, x1, y1, layer=0):
    pts = [r.Point3d(x0, y0, 0), r.Point3d(x1, y0, 0), r.Point3d(x1, y1, 0), r.Point3d(x0, y1, 0), r.Point3d(x0, y0, 0)]
    return m.Objects.AddPolyline(r.Polyline(pts), on(layer))


def box(m, x0, y0, x1, y1, z1, layer=1):
    return m.Objects.AddBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(x0, y0, 0, x1, y1, z1)), on(layer))


def write(m, tmp_path, name="m.3dm"):
    path = tmp_path / name
    m.Write(str(path), 8)
    return path


FACTS = {"street_line": [[[0, 0], [50, 0]]], "corner_lot": False, "lot_surveyed": True, "ground_is_flat": True, "grade_elevation": 0}


def test_a_lot_and_a_solid(tmp_path):
    m = model()
    rect(m, 0, 0, 50, 100)
    box(m, 10, 25, 35, 65, 30)
    site = read_site(write(m, tmp_path), FACTS)
    assert site["problems"] == [] and len(site["lot"]["edges"]) == 4 and len(site["buildings"][0]["faces"]) == 6
    assert measure(site, FACTS)["rear_yard"]["value"] == 35.0


def test_inches_become_feet(tmp_path):
    m = model(r.UnitSystem.Inches)
    rect(m, 0, 0, 600, 1200)
    box(m, 120, 300, 420, 780, 360)
    values = {k: v["value"] for k, v in measure(read_site(write(m, tmp_path), FACTS), FACTS).items()}
    assert values["lot_area"] == 5000 and values["front_yard"] == 25 and values["building_height"] == 30


def test_two_outlines_on_the_site_layer_need_the_lot_picked(tmp_path):
    m = model()
    lot_id = rect(m, 0, 0, 50, 100)
    rect(m, 10, 25, 35, 65)                  # a footprint outline, also closed
    box(m, 10, 25, 35, 65, 30)
    path = write(m, tmp_path)
    assert read_site(path, FACTS)["problems"] == ["2 closed outlines on the Site layer: pick the lot"]
    picked = read_site(path, {**FACTS, "lot_id": str(lot_id)})
    assert picked["problems"] == [] and picked["lot"]["id"] == str(lot_id)
    assert read_site(path, {**FACTS, "lot_id": "not-an-id"})["problems"] == [
        "the lot picked isn't a closed outline on the Site layer: pick the lot again"]


def test_no_site_layer_or_no_outline(tmp_path):
    assert read_site(write(model(layers=("Building",)), tmp_path), FACTS)["problems"][0] == "no Site layer"
    assert read_site(write(model(), tmp_path, "b.3dm"), FACTS)["problems"] == ["no closed lot outline on the Site layer"]


def test_a_copy_keeps_the_original_id(tmp_path):
    m = model()
    a = on(0)
    a.SetUserString(ID_KEY, "original-id")
    m.Objects.AddPolyline(r.Polyline([r.Point3d(*p, 0) for p in [(0, 0), (50, 0), (50, 100), (0, 0)]]), a)
    assert read_site(write(m, tmp_path), FACTS)["lot"]["id"] == "original-id"


def test_a_mesh_building(tmp_path):
    m = model()
    rect(m, 0, 0, 50, 100)
    mesh = r.Mesh.CreateFromBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(10, 25, 0, 35, 65, 30)),
                                 r.MeshingParameters.Default) if hasattr(r.Mesh, "CreateFromBrep") else None
    if mesh is None:                          # build the box's mesh by hand
        mesh = r.Mesh()
        for x, y, z in [(10, 25, 0), (35, 25, 0), (35, 65, 0), (10, 65, 0), (10, 25, 30), (35, 25, 30), (35, 65, 30), (10, 65, 30)]:
            mesh.Vertices.Add(x, y, z)
        for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            mesh.Faces.AddFace(*f)
    m.Objects.AddMesh(mesh, on(1))
    values = {k: v["value"] for k, v in measure(read_site(write(m, tmp_path), FACTS), FACTS).items()}
    assert values["building_area"] == 1000 and values["front_yard"] == 25 and values["building_height"] == 30


def test_a_curved_wall_is_reported_not_approximated(tmp_path):
    m = model()
    rect(m, 0, 0, 50, 100)
    m.Objects.AddBrep(r.Brep.CreateFromCylinder(r.Cylinder(r.Circle(r.Point3d(25, 45, 0), 10), 30), True, True), on(1))
    site = read_site(write(m, tmp_path), FACTS)
    assert "a building has a curved surface (not measured yet)" in site["buildings"][0]["problems"]
    assert measure(site, FACTS)["front_yard"]["value"] is None


def test_a_curved_lot_line_is_followed_and_marked(tmp_path):
    m = model()
    arc = r.ArcCurve.CreateFromArc(r.Arc(r.Point3d(0, 0, 0), r.Point3d(25, -8, 0), r.Point3d(50, 0, 0)))
    curve = r.PolyCurve()
    curve.Append(arc)
    for a, b in [((50, 0), (50, 100)), ((50, 100), (0, 100)), ((0, 100), (0, 0))]:
        curve.Append(r.LineCurve(r.Point3d(*a, 0), r.Point3d(*b, 0)))
    m.Objects.AddCurve(curve, on(0))
    site = read_site(write(m, tmp_path), FACTS)
    edges = site["lot"]["edges"]
    assert [e["curved"] for e in edges] == [True, False, False, False]
    assert len(edges[0]["points"]) > 16 and max(abs(p[1] + 8) for p in edges[0]["points"]) < 1e-9 + 8


def test_a_block_is_reported_and_its_definition_isnt_read_as_a_building(tmp_path):
    m = model()
    rect(m, 0, 0, 50, 100)
    box(m, 10, 25, 35, 65, 30)
    garage = r.Brep.CreateFromBoundingBox(r.BoundingBox(0, 0, 0, 18, 20, 12))
    index = m.InstanceDefinitions.Add("garage", "", "", "", r.Point3d(0, 0, 0), (garage,), (on(1),))
    definition = m.InstanceDefinitions.FindIndex(index)
    m.Objects.AddInstanceObject(r.InstanceReference(definition.Id, r.Transform.Translation(30, 75, 0)), on(1))
    site = read_site(write(m, tmp_path), FACTS)
    assert [b["id"] for b in site["buildings"]][-1] == "a block"
    assert len(site["buildings"]) == 2                    # the house, and the block reported (not its definition)
    assert measure(site, FACTS)["building_area"]["value"] is None


def test_a_solid_on_a_sublayer_counts_and_a_surface_is_reported(tmp_path):
    m = model()
    garage = r.Layer()
    garage.Name = "Garage"                    # a real sublayer: its name is "Garage", its full path "Building::Garage"
    garage.ParentLayerId = m.Layers.FindIndex(1).Id
    m.Layers.Add(garage)
    rect(m, 0, 0, 50, 100)
    box(m, 10, 25, 35, 65, 30)
    box(m, 30, 75, 48, 95, 12, layer=2)
    m.Objects.AddSurface(r.PlaneSurface(r.Plane.WorldXY(), r.Interval(1, 4), r.Interval(1, 4)), on(1))
    site = read_site(write(m, tmp_path), FACTS)
    assert len([b for b in site["buildings"] if b["faces"]]) == 2
    assert any("a Surface on the Building layer can't be measured yet" in p for b in site["buildings"]
               for p in b["problems"])


def test_a_block_placed_on_another_layer_with_building_objects_inside_is_reported(tmp_path):
    m = model(layers=("Site", "Building", "Default"))
    rect(m, 0, 0, 50, 100)
    box(m, 10, 25, 35, 65, 30)
    garage = r.Brep.CreateFromBoundingBox(r.BoundingBox(0, 0, 0, 18, 20, 12))
    index = m.InstanceDefinitions.Add("garage", "", "", "", r.Point3d(0, 0, 0), (garage,), (on(1),))   # solid on Building
    definition = m.InstanceDefinitions.FindIndex(index)
    m.Objects.AddInstanceObject(r.InstanceReference(definition.Id, r.Transform.Translation(30, 75, 0)), on(2))
    site = read_site(write(m, tmp_path), FACTS)
    assert [b["id"] for b in site["buildings"]] [-1] == "a block"


@pytest.mark.parametrize("x0, y0, n", [(152.2131319706377, 194.70395691601078, 8),
                                       (40000.1, 50000.9, 16), (20000.5, 22000.25, 16)])   # near and far from 0
def test_a_meshed_gable_read_from_a_file_is_one_roof_per_slope(tmp_path, x0, y0, n):
    # a real meshed gable house drawn with single-precision points: their rounding noise (larger far from the
    # origin) must not split a slope (wrong eave, or a false "something above")
    w, depth, eave, ridge = 22.731880258796153, 30.007429476637732, 17.724593436290334, 32.33899205293994
    m = model()
    lot = [(x0 - 20, y0 - 30), (x0 + w + 20, y0 - 30), (x0 + w + 20, y0 + depth + 30), (x0 - 20, y0 + depth + 30)]
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x, y, 0) for x, y in lot + lot[:1]]), on(0))
    mesh, index = r.Mesh(), {}

    def vertex(x, y, z):                       # shared corners, so the mesh is closed
        if (x, y, z) not in index:
            mesh.Vertices.Add(x, y, z)
            index[(x, y, z)] = len(mesh.Vertices) - 1
        return index[(x, y, z)]

    def quad(a, b, c, d):
        mesh.Faces.AddFace(vertex(*a), vertex(*b), vertex(*c), vertex(*d))

    mid = y0 + depth / 2
    floor_ys = [y0 + j * (depth / 2) / n for j in range(n + 1)] + [mid + j * (depth / 2) / n for j in range(1, n + 1)]
    floor_xs = [x0 + i * w / n for i in range(n + 1)]
    for xa, xb in zip(floor_xs, floor_xs[1:]):                                          # floor, in a matching grid
        for ya, yb in zip(floor_ys, floor_ys[1:]):
            quad((xa, ya, 0), (xa, yb, 0), (xb, yb, 0), (xb, ya, 0))
    for ya, yb in ((y0, mid), (mid, y0 + depth)):
        za, zb = (eave, ridge) if ya == y0 else (ridge, eave)
        for i in range(n):
            for j in range(n):
                xa, xb = x0 + i * w / n, x0 + (i + 1) * w / n
                y1, y2 = ya + j * (yb - ya) / n, ya + (j + 1) * (yb - ya) / n
                z1, z2 = za + j * (zb - za) / n, za + (j + 1) * (zb - za) / n
                quad((xa, y1, z1), (xb, y1, z1), (xb, y2, z2), (xa, y2, z2))
    xs = [x0 + i * w / n for i in range(n + 1)]
    for y, z0 in ((y0, eave), (y0 + depth, eave)):                                   # long walls, in strips
        for xa, xb in zip(xs, xs[1:]):
            quad((xa, y, 0), (xb, y, 0), (xb, y, z0), (xa, y, z0))
    ys = [y0 + j * (depth / 2) / n for j in range(n + 1)] + [mid + j * (depth / 2) / n for j in range(1, n + 1)]
    zs = [eave + j * (ridge - eave) / n for j in range(n + 1)] + [ridge - j * (ridge - eave) / n for j in range(1, n + 1)]
    for x in (x0, x0 + w):                                                            # gable ends, in strips
        for (ya, za), (yb, zb) in zip(zip(ys, zs), zip(ys[1:], zs[1:])):
            quad((x, ya, 0), (x, yb, 0), (x, yb, zb), (x, ya, za))
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[list(lot[0]), list(lot[1])]]}
    h = measure(read_site(write(m, tmp_path), facts), facts)["building_height"]
    assert "rises above" not in (h["reason"] or "")
    # midway between eave and ridge (pitched_roof_midpoint); no overhang, so every eave reading agrees
    assert {round(r["value"], 3) for r in h["readings"]} == {round((eave + ridge) / 2, 3)}


def gable_mesh(x0, y0, n, double):
    """A closed meshed gable house (walls, floor and roof in matching strips), and its sizes."""
    w, depth, eave, ridge = 22.731880258796153, 30.007429476637732, 17.724593436290334, 32.33899205293994
    mesh, index = r.Mesh(), {}
    mesh.Vertices.UseDoublePrecisionVertices = double

    def vertex(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in index:
            (mesh.Vertices.AddPoint3d if double else mesh.Vertices.Add)(x, y, z)
            index[key] = len(mesh.Vertices) - 1
        return index[key]

    def quad(a, b, c, d):
        mesh.Faces.AddFace(vertex(*a), vertex(*b), vertex(*c), vertex(*d))

    mid = y0 + depth / 2
    ys = [y0 + j * (depth / 2) / n for j in range(n + 1)] + [mid + j * (depth / 2) / n for j in range(1, n + 1)]
    zs = [eave + j * (ridge - eave) / n for j in range(n + 1)] + [ridge - j * (ridge - eave) / n for j in range(1, n + 1)]
    xs = [x0 + i * w / n for i in range(n + 1)]
    for xa, xb in zip(xs, xs[1:]):
        for (ya, za), (yb, zb) in zip(zip(ys, zs), zip(ys[1:], zs[1:])):
            quad((xa, ya, 0), (xa, yb, 0), (xb, yb, 0), (xb, ya, 0))          # floor
            quad((xa, ya, za), (xb, ya, za), (xb, yb, zb), (xa, yb, zb))      # roof
    for y in (y0, y0 + depth):
        for xa, xb in zip(xs, xs[1:]):
            quad((xa, y, 0), (xb, y, 0), (xb, y, eave), (xa, y, eave))
    for x in (x0, x0 + w):
        for (ya, za), (yb, zb) in zip(zip(ys, zs), zip(ys[1:], zs[1:])):
            quad((x, ya, 0), (x, yb, 0), (x, yb, zb), (x, ya, za))
    return mesh, w, depth, eave, ridge


def measured_gable(tmp_path, x0, y0, n, double):
    mesh, w, depth, eave, ridge = gable_mesh(x0, y0, n, double)
    m = model()
    lot = [(x0 - 20, y0 - 30), (x0 + w + 20, y0 - 30), (x0 + w + 20, y0 + depth + 30), (x0 - 20, y0 + depth + 30)]
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x, y, 0) for x, y in lot + lot[:1]]), on(0))
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[list(lot[0]), list(lot[1])]]}
    return measure(read_site(write(m, tmp_path), facts), facts)["building_height"], eave, ridge


def test_a_meshed_gable_on_ithaca_survey_coordinates_is_read_on_its_full_precision_points(tmp_path):
    h, eave, ridge = measured_gable(tmp_path, 870000.3, 900000.7, 32, double=True)     # NY State Plane, in ft
    # midway between eave and ridge (pitched_roof_midpoint); no overhang, so every eave reading agrees
    assert {round(r["value"], 3) for r in h["readings"]} == {round((eave + ridge) / 2, 3)}


def test_a_single_precision_mesh_that_far_out_is_reported_not_measured(tmp_path):
    h, _, _ = measured_gable(tmp_path, 870000.3, 900000.7, 8, double=False)
    assert h["value"] is None and "may be single precision" in h["reason"]


def test_a_floor_blocks_mark_survives_the_file():
    """GordiumStart marks each floor block "<story>;<height drawn>"; the copy sent to the checker keeps it."""
    import tempfile
    from pathlib import Path
    from model_measurement.read_3dm import FLOOR_KEY
    m = model()
    rect(m, 0, 0, 50, 100)
    a = on(1)
    a.SetUserString(FLOOR_KEY, "1;11.5")
    m.Objects.AddBrep(r.Brep.CreateFromBoundingBox(r.BoundingBox(10, 25, 0, 35, 65, 11.5)), a)
    box(m, 10, 25, 35, 65, 30)
    site = read_site(write(m, Path(tempfile.mkdtemp())), FACTS)
    assert sorted(b["floor"] or 0 for b in site["buildings"]) == [0, 11.5]


def test_the_rhino_side_uses_the_same_keys():
    from design_checker import rhino_logic
    from model_measurement import read_3dm
    assert (rhino_logic.ID_KEY, rhino_logic.FLOOR_KEY) == (read_3dm.ID_KEY, read_3dm.FLOOR_KEY)


def test_a_single_precision_mesh_reads_as_the_numbers_typed(tmp_path):
    """Stress test: a mesh made with Vertices.Add holds single-precision points; 27 ft drawn in millimetres
    (8229.6 mm) was read as 26.999999 ft, so a design exactly at a limit failed. Near the origin its points are
    read as the shortest decimals they store (what was typed): 27 ft exactly."""
    from rule_format.rulebook import outcome
    m = model(units=r.UnitSystem.Millimeters)
    mm = 304.8
    rect(m, 0, 0, 50 * mm, 100 * mm)
    mesh = r.Mesh()
    for x, y, z in [(10, 25, 0), (35, 25, 0), (35, 65, 0), (10, 65, 0), (10, 25, 27), (35, 25, 27), (35, 65, 27), (10, 65, 27)]:
        mesh.Vertices.Add(x * mm, y * mm, z * mm)
    for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
        mesh.Faces.AddFace(*f)
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[[0, 0], [50 * mm / mm, 0]]]}
    got = measure(read_site(write(m, tmp_path), facts), facts)
    height = got["building_height"]["value"]
    assert abs(height - 27) < 1e-9, height
    assert outcome({"id": "h", "kind": "rule", "check": "building_height <= 27"}, {"building_height": height}, {}) == "pass"
    assert abs(got["front_yard"]["value"] - 25) < 1e-9 and abs(got["building_area"]["value"] - 1000) < 1e-6


@pytest.mark.parametrize("x0, y0", [(40000.1, 50000.9), (20000.5, 22000.25), (152.2131319706377, 194.70395691601078)])
def test_a_single_precision_meshed_gable_is_two_roof_planes_near_and_far(tmp_path, x0, y0):
    """A computed single-precision gable, its points read as their shortest decimals: each slope is one plane at
    every distance. 40,000 ft out those decimals move each point by up to half a float32 step (0.002 ft), and
    planes grouped from one small triangle's normal split a slope in two (256 + 256 + 512, read by PR #18 as a
    second eave); planes fitted over their whole group don't. The 40,000 ft case pins the grouping; 20,000 and
    152 ft are regression guards."""
    from model_measurement import measure as M
    mesh, w, depth, eave, ridge = gable_mesh(x0, y0, 16, double=False)
    m = model()
    lot = [(x0 - 20, y0 - 30), (x0 + w + 20, y0 - 30), (x0 + w + 20, y0 + depth + 30), (x0 - 20, y0 + depth + 30)]
    m.Objects.AddPolyline(r.Polyline([r.Point3d(x, y, 0) for x, y in lot + lot[:1]]), on(0))
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[list(lot[0]), list(lot[1])]]}
    faces = read_site(write(m, tmp_path), facts)["buildings"][0]["faces"]
    slopes = [g for g in M._planes(faces) if 0.2 < abs(M._unit_normal(g[0]["points"])[2]) < 0.99]
    assert sorted(len(g) for g in slopes) == [512, 512]



@pytest.mark.parametrize("units, k, x0, y0, what", [
    (r.UnitSystem.Feet, 1.0, 2000, 3000, "front_yard"),
    (r.UnitSystem.Millimeters, 304.8, 1000, 0, "building_height"),
])
def test_a_typed_single_precision_box_reads_exactly_anywhere_below_far(tmp_path, units, k, x0, y0, what):
    """Review of 44c2466: a 1,024 ft gate brought back false fails between 1,024 and 131,072 ft (a 15.7 ft yard read
    15.699951; 35.1 ft in millimetres read 35.100002). What tells typed from computed is the numbers themselves:
    every coordinate is the single-precision value of a short decimal. Such a box reads exactly, and at its limit
    complies."""
    from rule_format.rulebook import outcome
    m = model(units=units)
    rect(m, x0 * k, y0 * k, (x0 + 50) * k, (y0 + 100) * k)
    yard, height = (15.7, 30) if what == "front_yard" else (25, 35.1)
    mesh = r.Mesh()
    for x, y, z in [(10, yard, 0), (35, yard, 0), (35, 65, 0), (10, 65, 0),
                    (10, yard, height), (35, yard, height), (35, 65, height), (10, 65, height)]:
        mesh.Vertices.Add((x0 + x) * k, (y0 + y) * k, z * k)
    for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
        mesh.Faces.AddFace(*f)
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[[x0, y0], [x0 + 50, y0]]]}
    got = measure(read_site(write(m, tmp_path), facts), facts)
    limit = yard if what == "front_yard" else height
    assert abs(got[what]["value"] - limit) < 1e-9, got[what]["value"]
    sign = ">=" if what == "front_yard" else "<="
    assert outcome({"id": "x", "kind": "rule", "check": f"{what} {sign} {limit}"}, {what: got[what]["value"]}, {}) == "pass"



def test_where_single_precision_cant_hold_the_typed_decimal_the_box_reads_within_one_step(tmp_path):
    """A documented limit, not a fix: in millimetres 3,000 ft out the street side is at y = 3,015.7 ft =
    919,208.36 mm, where a single-precision step is 0.0625 mm, so the stored 919,208.375 can't tell .36 from .40:
    the yard reads within that one step (2e-4 ft) of 15.7, never further (a raw reading would too)."""
    m = model(units=r.UnitSystem.Millimeters)
    k, x0, y0 = 304.8, 2000, 3000
    rect(m, x0 * k, y0 * k, (x0 + 50) * k, (y0 + 100) * k)
    mesh = r.Mesh()
    for x, y, z in [(10, 15.7, 0), (35, 15.7, 0), (35, 65, 0), (10, 65, 0),
                    (10, 15.7, 30), (35, 15.7, 30), (35, 65, 30), (10, 65, 30)]:
        mesh.Vertices.Add((x0 + x) * k, (y0 + y) * k, z * k)
    for f in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
        mesh.Faces.AddFace(*f)
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[[x0, y0], [x0 + 50, y0]]]}
    got = measure(read_site(write(m, tmp_path), facts), facts)
    assert abs(got["front_yard"]["value"] - 15.7) <= 0.0625 / 304.8



@pytest.mark.parametrize("x0, y0", [(300, 400), (2000, 3000)])
def test_a_typed_box_with_a_computed_apex_reads_its_typed_walls_exactly(tmp_path, x0, y0):
    """Round 2 of 44c2466's review: one computed vertex (a hip apex at 10/3 ft) vetoed reading the mesh's typed
    decimals, so typed walls read 15.700012 / 15.699951 and failed at their limit. Each value is read on its own."""
    from rule_format.rulebook import outcome
    m = model()
    rect(m, x0, y0, x0 + 50, y0 + 100)
    mesh = r.Mesh()
    corners = [(10, 15.7, 0), (35, 15.7, 0), (35, 65, 0), (10, 65, 0), (10, 15.7, 30), (35, 15.7, 30), (35, 65, 30),
               (10, 65, 30), (22.5, 40.35, 30 + 10 / 3)]
    for x, y, z in corners:
        mesh.Vertices.Add(x0 + x, y0 + y, z)
    for f in [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
        mesh.Faces.AddFace(*f)
    for a, b in ((4, 5), (5, 6), (6, 7), (7, 4)):               # a hip roof to the computed apex
        mesh.Faces.AddFace(a, b, 8)
    m.Objects.AddMesh(mesh, on(1))
    facts = {**FACTS, "street_line": [[[x0, y0], [x0 + 50, y0]]]}
    got = measure(read_site(write(m, tmp_path), facts), facts)
    assert abs(got["front_yard"]["value"] - 15.7) < 1e-9, got["front_yard"]["value"]
    assert outcome({"id": "x", "kind": "rule", "check": "front_yard >= 15.7"}, {"front_yard": got["front_yard"]["value"]}, {}) == "pass"


def test_a_genuinely_different_slope_is_still_its_own_plane():
    """Tolerant to rounding noise, not to real shape: two halves of a 20 ft roof whose slopes differ by 1 in 100
    (0.1 ft over each half) stay two planes."""
    from model_measurement.measure import _planes
    faces = []
    for i in range(20):
        for half, rise in ((0, 0.25), (10, 0.26)):
            x0, x1 = half + i * 0.5, half + (i + 1) * 0.5
            z0 = 30 + (x0 - half) * rise + (2.5 if half else 0)
            z1 = 30 + (x1 - half) * rise + (2.5 if half else 0)
            faces += [{"points": [[x0, 0, z0], [x1, 0, z1], [x1, 20, z1]]},
                      {"points": [[x0, 0, z0], [x1, 20, z1], [x0, 20, z0]]}]
    groups = _planes(faces)
    # a triangle at the crease may go either way (0.5 ft from it, the slopes differ by 0.005 ft): never one plane
    assert len(groups) == 2 and min(len(g) for g in groups) >= 38, sorted(len(g) for g in groups)
