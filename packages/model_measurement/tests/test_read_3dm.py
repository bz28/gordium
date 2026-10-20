"""Reading Rhino files: units, which object is the lot, solids and meshes, and what can't be read exactly."""

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


FACTS = {"street_line": [[[0, 0], [50, 0]]], "grade_elevation": 0}


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
    m = model(layers=("Site", "Building", "Building::Garage"))
    rect(m, 0, 0, 50, 100)
    box(m, 10, 25, 35, 65, 30)
    box(m, 30, 75, 48, 95, 12, layer=2)
    m.Objects.AddSurface(r.PlaneSurface(r.Plane.WorldXY(), r.Interval(1, 4), r.Interval(1, 4)), on(1))
    site = read_site(write(m, tmp_path), FACTS)
    assert len([b for b in site["buildings"] if b["faces"]]) == 2
    assert any("a Surface on the Building layer can't be measured yet" in p for b in site["buildings"]
               for p in b["problems"])
