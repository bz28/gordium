"""Every reason the measuring can stop with is listed in the README, word for word, and is reached by a case.

The reasons are read from the code itself (each sentence put into a problems list, a `why_...` or `reason`, a
street problem, or `_missing`), so a new stop can't be added without its line in the README and its case here:
CASES pairs each reason with a small lot or model that gives it."""

import ast
import sys
from pathlib import Path

import pytest
import rhino3dm as r

from model_measurement.measure import measure
from model_measurement.read_3dm import read_site

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))           # the lots and models the other tests build
from test_measure import FACTS, RECT, box, lot, sloped_roof_box  # noqa: E402
from test_read_3dm import FACTS as FILE_FACTS  # noqa: E402
from test_read_3dm import box as file_box  # noqa: E402
from test_read_3dm import model, on, rect, write  # noqa: E402

CODE = HERE.parent / "model_measurement"
README = " ".join((HERE.parent / "README.md").read_text().split())     # as one line: wrapping doesn't matter


def _pieces(node):
    """The fixed words of a reason: a plain string, or the longest fixed part of an f-string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, ast.JoinedStr):
        yield max((v.value for v in node.values if isinstance(v, ast.Constant)), key=len, default="")
    elif isinstance(node, (ast.IfExp, ast.BoolOp, ast.List, ast.Tuple, ast.BinOp)):
        for child in ast.iter_child_nodes(node):
            yield from _pieces(child)


def _targets(node):
    """The expressions in `node` that hold a reason, if any."""
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "append" and ast.unparse(f.value).endswith(("problems", "trouble")):
            return node.args
        if isinstance(f, ast.Name) and f.id == "_missing":
            return node.args[1:2]
    if isinstance(node, ast.Assign):
        names = [ast.unparse(t) for t in node.targets]
        if any(n.startswith("why") or n.endswith(("reason", "street_problem")) for n in names):
            return [node.value]
    if isinstance(node, ast.Dict):
        return [v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value == "problems"]
    return []


def stop_reasons() -> list[str]:
    found = []
    for name in ("read_3dm.py", "measure.py"):
        for node in ast.walk(ast.parse((CODE / name).read_text())):
            for target in _targets(node):
                found += [p.strip(" :(") for p in _pieces(target) if " " in p.strip()]
    return sorted(set(found))


# ---- a case for each reason: (what it is, a function giving every reason a lot or model produces) ----------

def _said(site, facts):
    """Every problem and reason for a site, as one text."""
    reasons = [str(m.get("reason")) for m in measure(site, facts).values()]
    return " | ".join(site.get("problems", []) + [p for b in site["buildings"] for p in b["problems"]] + reasons)


def _plain(lot_=RECT, buildings=None, **facts):
    def run(tmp_path):
        return _said({"units": "ft", "lot": lot_, "buildings": [box(10, 25, 35, 65)] if buildings is None else buildings,
                      "problems": []}, {**FACTS, **facts})
    return run


def _file(build, facts=None):
    def run(tmp_path):
        m = model()
        build(m)
        f = {**FILE_FACTS, **(facts or {})}
        return _said(read_site(write(m, tmp_path), f), f)
    return run


def _unreadable_file(tmp_path):
    path = tmp_path / "broken.3dm"
    path.write_bytes(b"not a Rhino file")
    return _said(read_site(path, FILE_FACTS), FILE_FACTS)


def _units(tmp_path):
    m = model(units=r.UnitSystem.Miles)
    rect(m, 0, 0, 50, 100)
    return _said(read_site(write(m, tmp_path), FILE_FACTS), FILE_FACTS)


def _block_on_site(m):
    rect(m, 0, 0, 50, 100)
    file_box(m, 10, 25, 35, 65, 30)
    index = m.InstanceDefinitions.Add("fence", "", "", "", r.Point3d(0, 0, 0), (r.LineCurve(r.Point3d(0, 0, 0), r.Point3d(1, 0, 0)),), (on(0),))
    m.Objects.AddInstanceObject(r.InstanceReference(m.InstanceDefinitions.FindIndex(index).Id, r.Transform.Identity()), on(0))


def _mesh(points, faces):
    mesh = r.Mesh()
    for p in points:
        mesh.Vertices.Add(*p)
    for f in faces:
        mesh.Faces.AddFace(*f)
    return mesh


BOX_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]


def _box_points(x0, y0, x1, y1, z1):
    return [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]


def _open_mesh(m):
    rect(m, 0, 0, 50, 100)
    m.Objects.AddMesh(_mesh(_box_points(10, 25, 35, 65, 30), BOX_FACES[:5]), on(1))   # no side: not closed


def _far_mesh(m):
    x, y = 200000, 300000                     # past 2^17 ft; whole feet are exact in single precision
    pts = [(x, y, 0), (x + 50, y, 0), (x + 50, y + 100, 0), (x, y + 100, 0), (x, y, 0)]
    m.Objects.AddPolyline(r.Polyline([r.Point3d(*p) for p in pts]), on(0))
    m.Objects.AddMesh(_mesh(_box_points(x + 10, y + 25, x + 35, y + 65, 30), BOX_FACES), on(1))


def _open_brep(m):
    rect(m, 0, 0, 50, 100)
    sheet = r.PlaneSurface(r.Plane.WorldXY(), r.Interval(10, 35), r.Interval(25, 65))
    m.Objects.AddBrep(r.Brep.CreateFromSurface(sheet), on(1))      # one face: not a closed solid


def _cylinder(m):
    rect(m, 0, 0, 50, 100)
    m.Objects.AddBrep(r.Brep.CreateFromCylinder(r.Cylinder(r.Circle(r.Point3d(25, 45, 0), 10), 30), True, True), on(1))


def _surface(m):
    rect(m, 0, 0, 50, 100)
    file_box(m, 10, 25, 35, 65, 30)
    m.Objects.AddSurface(r.PlaneSurface(r.Plane.WorldXY(), r.Interval(1, 4), r.Interval(1, 4)), on(1))


def _walls_only(x0, y0, x1, y1, id="house"):
    """A building with walls and a floor but nothing over it: no roof to read."""
    b = box(x0, y0, x1, y1, id=id)
    b["faces"] = [f for f in b["faces"] if not all(p[2] == 30 for p in f["points"])]
    return b


ZIGZAG = lot([(0, 0), (50, 0), (50, 100), (40, 110), (30, 100), (20, 110), (10, 100), (0, 110)])
SHEDS = [sloped_roof_box(2 + 6 * i, 70, 6 + 6 * i, 74, 20, 30, f"shed {i}") for i in range(8)]

CASES = {
    "a building has a curved edge (not measured yet)": _file(_cylinder),
    "a building has a curved surface (not measured yet)": _file(_cylinder),
    "a building isn't a closed solid": _file(_open_brep),
    "a building isn't inside the lot": _plain(buildings=[box(40, 25, 60, 65)]),
    "a building mesh isn't closed": _file(_open_mesh),
    "a building mesh's points may be single precision, too coarse this far from the origin to measure to 0.01 ft "
    "(move it nearer the origin, or turn it into a solid)": _file(_far_mesh, {"street_line": [[[200000, 300000], [200050, 300000]]]}),
    "a corner lot: which yards are front, side and rear yards, and which street's frontage is the lot width "
    "(§325-19C), are open questions for the architects": _plain(corner_lot=True),
    "a street line given doesn't match a lot line: pick the street side again": _plain(street_line=[[[0, 5], [50, 5]]]),
    "another solid's height can't be read": _plain(buildings=[box(10, 25, 35, 65), _walls_only(38, 70, 48, 90, "shed")],
                                                   main_building="house"),
    "can't read": _unreadable_file,
    "closed outlines on the": _file(lambda m: (rect(m, 0, 0, 50, 100), rect(m, 60, 0, 90, 30), file_box(m, 10, 25, 35, 65, 30))),
    "every lot line is on a street: which yards are front, side and rear is an open question for the architects":
        _plain(street_line=[[[0, 0], [50, 0]], [[50, 0], [50, 100]], [[50, 100], [0, 100]], [[0, 100], [0, 0]]],
               corner_lot=False),
    "layer can't be measured yet (explode it or turn it into a solid)": _file(_surface),
    "layer can't be read yet (explode it)": _file(_block_on_site),
    "more than one building: pick the main building": _plain(buildings=[box(10, 25, 35, 65), box(38, 70, 48, 90, id="shed")]),
    "no building on the Building layer": _plain(buildings=[]),
    "no closed lot outline on the": _file(lambda m: file_box(m, 10, 25, 35, 65, 30)),
    "say whether the ground is flat": _plain(ground_is_flat=None),
    "say whether this is a corner lot (two streets meet at it, §325-19C): enter corner lot yes or no": _plain(corner_lot=None),
    "sloped ground: the grade plane (§325-3) needs the ground levels around the walls, which aren't measured yet":
        _plain(ground_is_flat=False),
    "the ground level isn't given: enter it (the grade plane)": _plain(grade_elevation=None),
    "the lot outline crosses itself": _plain(lot([(0, 0), (50, 0), (0, 100), (50, 100)])),
    "the lot outline isn't one closed loop of lot lines":
        _plain({"id": "lot", "edges": [{"points": [[0, 0], [50, 0]], "curved": False},
                                       {"points": [[50, 0], [50, 100]], "curved": False},
                                       {"points": [[50, 100], [0, 100]], "curved": False}]}),
    "the lot picked isn't a closed outline on the Site layer: pick the lot again":
        _file(lambda m: (rect(m, 0, 0, 50, 100), file_box(m, 10, 25, 35, 65, 30)), {"lot_id": "not-in-the-model"}),
    "the model's units": _units,
    "the roof's shape can't be read (no faces open to the sky)": _plain(buildings=[_walls_only(10, 25, 35, 65)]),
    "the side and rear lot lines can't be told apart": _plain(ZIGZAG),
    "the street lot lines given aren't next to each other":
        _plain(street_line=[[[0, 0], [50, 0]], [[50, 100], [0, 100]]], corner_lot=False),
    "the street side isn't given: pick the lot line on the street": _plain(street_line=[]),
    "too many solids with open roof questions to list every reading: pick the main building's parts, or ask the architects":
        _plain(buildings=[sloped_roof_box(10, 25, 35, 65, 20, 30, "house"), *SHEDS], main_building="house"),
}


def test_the_reasons_are_found_in_the_code():
    assert "the side and rear lot lines can't be told apart" in stop_reasons() and len(stop_reasons()) > 25


def test_every_stop_is_listed_in_the_readme():
    missing = [r for r in stop_reasons() if r not in README]
    assert not missing, "add to the README's list of what stops a measurement: " + "; ".join(missing)


def test_every_stop_has_a_case():
    assert sorted(CASES) == stop_reasons()


@pytest.mark.parametrize("reason", sorted(CASES))
def test_each_stop_is_given_by_its_case(reason, tmp_path):
    assert reason in CASES[reason](tmp_path)
