"""Every reason a measurement can stop with (model_measurement/stops.py) is listed in the README word for word,
and has a case here, a small lot or model that gives it. The measuring code gives reasons only through that
table (checked below), so a new stop can't be added without its README line and its case."""

import ast
import math
import re
import sys
from pathlib import Path

import pytest
import rhino3dm as r

from model_measurement.measure import MAX_COMBINATIONS, MAX_UNCLEAR_EDGES, measure
from model_measurement.read_3dm import read_site
from model_measurement.stops import STOPS

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))           # the lots and models the other tests build
from test_measure import FACTS, RECT, box, floor, lot, prism, sloped_roof_box  # noqa: E402
from test_read_3dm import FACTS as FILE_FACTS  # noqa: E402
from test_read_3dm import box as file_box  # noqa: E402
from test_read_3dm import model, on, rect, write  # noqa: E402

CODE = HERE.parent / "model_measurement"
README = " ".join((HERE.parent / "README.md").read_text(encoding="utf-8").split())     # as one line: wrapping doesn't matter
# the blanks whose words are fixed by the code: the README must quote them as they are
FIXED_BLANKS = {"limit": str(MAX_UNCLEAR_EDGES)}


def fixed_words(template: str) -> list[str]:
    """The parts of a reason that never change (its blanks, like {layer}, left out)."""
    return [p.strip() for p in re.split(r"\{[a-z_]+\}", template) if len(p.strip()) > 3]


# ---- a case for each reason: (what it is, a function giving every reason a lot or model produces) ----------

def _said(site, facts):
    """Every problem and reason for a site, as one text."""
    reasons = [str(m.get("reason")) for m in measure(site, facts).values()]
    return " | ".join(site.get("problems", []) + [p for b in site["buildings"] for p in b["problems"]] + reasons)


def _file_with_layers(layers, build):
    def run(tmp_path):
        m = model(layers=layers)
        build(m)
        return _said(read_site(write(m, tmp_path), FILE_FACTS), FILE_FACTS)
    return run


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


def _gable_over_no_wall():
    """A tent: a gable whose roof planes come down to the ground, with no walls under them at all."""
    faces = [{"points": [[10, 25, 0], [35, 25, 0], [35, 65, 0], [10, 65, 0]]},
             {"points": [[10, 25, 0], [22.5, 25, 12], [22.5, 65, 12], [10, 65, 0]]},
             {"points": [[22.5, 25, 12], [35, 25, 0], [35, 65, 0], [22.5, 65, 12]]},
             {"points": [[10, 25, 0], [35, 25, 0], [22.5, 25, 12]]},
             {"points": [[10, 65, 0], [35, 65, 0], [22.5, 65, 12]]}]
    return {"id": "house", "faces": faces, "problems": []}


def _a_reading_without_code(tmp_path):
    """Research lists a reading the measuring code doesn't know yet: the measurement stops, never skips it."""
    from unittest import mock

    from model_measurement import interpretations
    real = interpretations.question

    def more(facts, entry, ids):
        q = real(facts, entry, ids)
        return {**q, "readings": q["readings"] + ("a_new_reading",)} if entry == "height_of_building" else q
    with mock.patch.object(interpretations, "question", more):
        house = box(10, 25, 35, 65, 0, 20)
        house["faces"] = [f for f in house["faces"] if not all(p[2] == 20 for p in f["points"])]
        house["faces"] += [{"points": [[10, 25, 20], [35, 25, 20], [35, 45, 30], [10, 45, 30]]},
                           {"points": [[10, 45, 30], [35, 45, 30], [35, 65, 20], [10, 65, 20]]}]
        return _plain(buildings=[house])(tmp_path)


STREETS3 = [[[0, 0], [50, 0]], [[50, 0], [50, 100]], [[50, 100], [0, 100]]]
ZIGZAG = lot([(0, 0), (50, 0), (50, 100), (45, 110), (40, 100), (35, 110), (30, 100), (25, 110), (20, 100),
              (15, 110), (10, 100), (0, 110)])     # nine back lines between the two side lines: too many
SHEDS = [sloped_roof_box(2 + 6 * i, 70, 6 + 6 * i, 74, 20, 30, f"shed {i}") for i in range(8)]

def _geos_error(tmp_path):
    """Any shapely / GEOS failure while measuring: a stop with its reason, never a crash (stress F14)."""
    import shapely
    from model_measurement import measure as m

    def broken(building):
        raise shapely.errors.GEOSException("TopologyException: side location conflict at 1 2")
    real, m._projection_now = m._projection_now, broken
    try:
        return _plain()(tmp_path)
    finally:
        m._projection_now = real


CASES = {
    "unreadable_file": _unreadable_file,
    "units": _units,
    "no_lot_layer": _file_with_layers(("Building",), lambda m: file_box(m, 10, 25, 35, 65, 30, layer=0)),
    "no_lot_outline": _file(lambda m: file_box(m, 10, 25, 35, 65, 30)),
    "several_lot_outlines": _file(lambda m: (rect(m, 0, 0, 50, 100), rect(m, 60, 0, 90, 30), file_box(m, 10, 25, 35, 65, 30))),
    "lot_not_found": _file(lambda m: (rect(m, 0, 0, 50, 100), file_box(m, 10, 25, 35, 65, 30)), {"lot_id": "not-in-the-model"}),
    "lot_block": _file(_block_on_site),
    "no_lot": _plain(None),
    "lot_not_a_loop": _plain({"id": "lot", "edges": [{"points": [[0, 0], [50, 0]], "curved": False},
                                                     {"points": [[50, 0], [50, 100]], "curved": False},
                                                     {"points": [[50, 100], [0, 100]], "curved": False}]}),
    "lot_crosses_itself": _plain(lot([(0, 0), (50, 0), (0, 100), (50, 100)])),
    "survey_unknown": _plain(lot_surveyed=None),
    "not_surveyed": _plain(lot_surveyed=False),
    "no_street": _plain(street_line=[]),
    "street_not_a_lot_line": _plain(street_line=[[[0, 5], [50, 5]]]),
    "street_lines_apart": _plain(street_line=[[[0, 0], [50, 0]], [[50, 100], [0, 100]]], corner_lot=False),
    "two_streets": _plain(street_line=[[[0, 0], [50, 0]], [[50, 0], [50, 100]]], street_ids=["A St", "B Ave"],
                          corner_lot=False),
    "one_street_or_two": _plain(street_line=[[[0, 0], [50, 0]], [[50, 0], [50, 100]]], corner_lot=False),
    "street_names_stale": _plain(street_line=[[[0, 0], [50, 0]]], street_ids=["A St", "A St"], corner_lot=False),
    "all_street": _plain(street_line=[[[0, 0], [50, 0]], [[50, 0], [50, 100]], [[50, 100], [0, 100]], [[0, 100], [0, 0]]],
                         corner_lot=False),
    "corner_unknown": _plain(corner_lot=None),
    "corner_one_street": _plain(corner_lot=True, street_line=STREETS3[:2], street_ids=["A St", "A St"]),
    "street_ids_needed": _plain(corner_lot=True, street_line=STREETS3[:2]),
    "street_lines_split": _plain(corner_lot=True, street_line=STREETS3, street_ids=["A St", "B St", "A St"]),
    "address_not_a_street": _plain(corner_lot=True, street_line=STREETS3[:2], street_ids=["A St", "B St"],
                                   address_street_line=[[[0, 0], [0, 100]]]),
    "rear_on_street": _plain(corner_lot=True, street_line=STREETS3, street_ids=["A St", "B St", "C St"],
                             address_street_line=STREETS3[:1]),
    "no_side_line": _plain(corner_lot=True, street_line=STREETS3, street_ids=["A St", "B St", "C St"],
                           address_street_line=STREETS3[1:2]),
    "law_missing": _plain(jurisdiction="regulations/jurisdictions/nowhere/no_city"),
    "reading_unknown": _a_reading_without_code,
    "eave_unclear": _plain(buildings=[_gable_over_no_wall()]),
    "no_accessory": _plain(),
    "lines_unclear": _plain(ZIGZAG),
    "no_rear_line": _plain(lot([(0, 0), (50, 0), (25, 100)]), buildings=[box(20, 10, 30, 30)]),
    "no_ground": _plain(grade_elevation=None),
    "ground_off_building": _plain(grade_elevation=812),
    "ground_unclear": _plain(ground_is_flat=None, grade_elevation=None, buildings=[
        floor(10, 25, 35, 65, z0=1, z1=12, id="floor 1")], grade_points=[[60, 0, 0], [61, 1, 0.0]]),
    "buried_solid": _plain(buildings=[box(10, 25, 25, 65, 812, 842, id="house"), box(26, 25, 35, 65, 0, 45, id="tower")],
                           grade_elevation=812, main_building="house"),
    "readings_differ": _plain(lot([(0, 0), (50, 0), (50, 90), (8, 90), (0, 96)])),     # a jog: side or rear line
    "no_use": _plain(use=None),
    "no_district": _plain(zone=None),
    "no_stories": _plain(stories=None, buildings=[]),              # nothing drawn: the count isn't known
    "stories_below_one": _plain(stories=0, buildings=[box(10, 25, 35, 65, 0, 30)]),
    "stories_above_drawn": _plain(stories=5, buildings=[box(10, 25, 35, 65, 0, 30)]),     # 30 ft: at most 4
    "stories_below_floors": _plain(stories=1, main_building="floor 1", buildings=[
        floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"), floor(10, 25, 35, 65, z0=11, z1=22, id="floor 2"),
        box(35, 25, 45, 45, 0, 32, id="wing")]),
    "floors_apart": _plain(stories=2, buildings=[floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"),
                                                 floor(10, 25, 35, 65, z0=22, z1=33, id="floor 3")],
                           main_building="floor 1"),
    "parts_overlap": _plain(stories=2, main_building="floor 1", buildings=[
        floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"), floor(10, 25, 35, 65, z0=10.5, z1=21.5, id="floor 2")]),
    "part_raised": _plain(stories=3, main_building="floor 1", buildings=[
        floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"), box(35.1, 25, 45, 45, 25, 35, id="room")]),
    "basement_part": _plain(main_building="floor 1", buildings=[
        floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"), box(35, 25, 45, 45, -10, 10.5, id="wing")]),
    "floors_misaligned": _plain(stories=None, buildings=[floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"),
                                                         floor(13, 25, 38, 65, z0=11, z1=22, id="floor 2")]),
    "basement_story": _plain(stories=None, buildings=[floor(10, 25, 35, 65, z0=-9, z1=0, id="basement"),
                                                      floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"),
                                                      floor(10, 25, 35, 65, z0=11, z1=22, id="floor 2")]),
    "no_rooms": _plain(),
    "no_units": _plain(),
    "no_occupants": _plain(),
    "no_occupant_split": _plain(),
    "no_building_units": _plain(),
    "no_abuts_r1": _plain(),
    "no_household": _plain(),
    "no_home_occupation": _plain(),
    "no_primary_buildings": _plain(),
    "no_south_hill": _plain(),
    "no_garage_cars": _plain(),
    "no_private_garages": _plain(),
    "no_stream": _plain(),
    "stream_facts_disagree": _plain(stream_near_lot=False, stream_distance=5),
    "household_counts_disagree": _plain(unrelated_persons=3, unrelated_persons_with_children=1),
    "attached_counts_disagree": _plain(use="one_family_attached", dwelling_units=4, attached_units_in_building=3),
    "change_use_in_start_box": _plain(use="one_family_attached", dwelling_units=4, attached_units_in_building=3),
    "occupant_split_disagree": _plain(occupants=2, occupants_most_in_one_unit=3),
    "occupant_counts_disagree": _plain(use="two_family", occupants=10, occupants_most_in_one_unit=1,
                                      accessory_dwelling_unit=False),
    "ground_unknown": _plain(ground_is_flat=None),
    "grade_off_walls": _plain(grade_points=[[22, 24, 0], [22, 66, 0], [9, 45, 0], [60, 45, 0]]),
    "existing_grade": _plain(grade_is="existing"),
    "grade_with_others": _plain(buildings=[box(10, 25, 35, 65, id="house"), box(40, 75, 48, 90, 0, 12, id="shed")],
                                grade_points=[[22, 24, 0], [22, 66, 0], [9, 45, 0], [36, 45, 0], [44, 74.5, 0]],
                                main_building="house",          # one spot grade at the shed: not at all its walls
                                ground_is_flat=None, grade_elevation=None),
    "grade_walls_unclear": _plain(buildings=[prism([(22 + 8 * math.cos(k * math.pi / 32), 45 + 8 * math.sin(k * math.pi / 32))
                                                    for k in range(64)], 0, 30)],      # a round tower: 0.8 ft sides
                                  grade_points=[[22, 36, 0]]),
    "sloped_ground": _plain(ground_is_flat=False),
    "no_building": _plain(buildings=[]),
    "geometry_error": _geos_error,
    "same_id": _plain(buildings=[box(10, 25, 35, 65, 0, 10), box(10, 25, 35, 65, 10, 20)]),   # both "house"
    "no_main_building": _plain(buildings=[box(10, 25, 35, 65), box(38, 70, 48, 90, id="shed")]),
    "empty_building": _plain(buildings=[{"id": "house", "faces": [], "problems": []}]),
    "outside_lot": _plain(buildings=[box(60, 25, 80, 65)]),      # wholly off the lot (crossing it is measured)
    "open_solid": _file(_open_brep),
    "open_mesh": _file(_open_mesh),
    "curved_surface": _file(_cylinder),
    "curved_edge": _file(_cylinder),
    "single_precision": _file(_far_mesh, {"street_line": [[[200000, 300000], [200050, 300000]]]}),
    "not_a_solid": _file(_surface),
    "no_roof": _plain(buildings=[_walls_only(10, 25, 35, 65)]),
    "other_height": _plain(buildings=[box(10, 25, 35, 65), _walls_only(38, 70, 48, 90, "shed")], main_building="house"),
    "too_many_roofs": _plain(buildings=[sloped_roof_box(10, 25, 35, 65, 20, 30, "house"), *SHEDS], main_building="house"),
}


def quoted(template: str) -> re.Pattern:
    """The reason as the README quotes it: the whole sentence in quotes, each blank filled by a word or two
    (`<file>`, `2`, `Site`, `a block`)."""
    for blank, words in FIXED_BLANKS.items():
        template = template.replace("{" + blank + "}", words)
    parts = re.split(r"\{[a-z_]+\}", template)
    return re.compile('"' + '[^" ]+(?: [^" ]+)?'.join(re.escape(p) for p in parts) + '"')


def test_every_stop_is_listed_in_the_readme():
    missing = [STOPS[k] for k in STOPS if not quoted(STOPS[k]).search(README)]
    assert not missing, "add to the README's list of what stops a measurement: " + "; ".join(missing)


def test_every_stop_has_a_case():
    assert sorted(CASES) == sorted(STOPS)


@pytest.mark.parametrize("key", sorted(STOPS))
def test_each_stop_is_given_by_its_case(key, tmp_path):
    said = CASES[key](tmp_path)
    assert all(w in said for w in fixed_words(STOPS[key])), (STOPS[key], said)


def _reason_parts(node) -> list:
    """The expressions in `node` that become a reason: a problems list, a `why_...`, `reason` or street problem,
    the reason of `_missing` or `_record`."""
    if isinstance(node, ast.Call):
        f, name = node.func, ast.unparse(node.func)
        if isinstance(f, ast.Attribute) and f.attr == "append" and ast.unparse(f.value).endswith(("problems", "trouble")):
            return list(node.args)
        if name == "_missing":
            return node.args[1:] + [k.value for k in node.keywords]
        if name == "_record":
            return node.args[7:] + [k.value for k in node.keywords if k.arg == "reason"]
    if isinstance(node, ast.Assign):
        names = [ast.unparse(t) for t in node.targets]
        if any(n.split(".")[-1].startswith("why") or n.endswith(("reason", "problems", "street_problem")) for n in names):
            return [node.value]
    if isinstance(node, ast.Dict):
        return [v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant) and k.value == "problems"]
    return []


def _written_out(node, bound, seen=frozenset()) -> list:
    """Words in a reason that don't come from stop(): a string with letters outside any stop(...) call, found
    where the reason is made or in what a name in it was set to (a constant, a table like ASK[...])."""
    if isinstance(node, ast.Call) and ast.unparse(node.func) == "stop":
        return []
    if isinstance(node, ast.JoinedStr) or isinstance(node, ast.Constant) and isinstance(node.value, str) \
            and re.search("[a-z] [a-z]", node.value):          # words, not a key like "lot"
        return [ast.unparse(node)]
    if isinstance(node, ast.Name) and node.id in bound and node.id not in seen:
        return [w for value in bound[node.id] for w in _written_out(value, bound, seen | {node.id})]
    return [w for child in ast.iter_child_nodes(node) for w in _written_out(child, bound, seen)]


def test_the_measuring_gives_reasons_only_from_the_table():
    """Whatever becomes a reason comes from stop(), followed through names: a reason written into the code
    would be missed by the README and the cases. (conftest.py also checks every reason the tests make.)"""
    found = []
    for name in ("read_3dm.py", "measure.py"):
        tree = ast.parse((CODE / name).read_text(encoding="utf-8"))
        bound = {}                      # module-level names (constants, tables); a local why_... is checked itself
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bound.setdefault(target.id, []).append(node.value)
        for node in ast.walk(tree):
            found += [f"{name}:{node.lineno} {w}" for part in _reason_parts(node) for w in _written_out(part, bound)]
    assert not found, "put these reasons in stops.py and use stop(): " + "; ".join(found)


def test_the_limits_the_readme_names_are_the_code_s():
    assert f"more than {MAX_COMBINATIONS} combinations of readings" in README
    assert f"more than {MAX_UNCLEAR_EDGES} lot lines could be either" in README
