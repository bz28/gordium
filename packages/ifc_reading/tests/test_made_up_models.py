"""Small made-up IFC4 models (built by tests/build_ifc.py with ifcopenshell's own API), one for each thing the
reader decides. Every expected value is worked out by hand in the comment next to it, in the model's own unit
first, then in metres (1 ft = 0.3048 m exactly).
"""

import pytest

pytest.importorskip("ifcopenshell")

from ifc_reading import read  # noqa: E402
from model_measurement.interior import measure  # noqa: E402

FT = 0.3048
QTY = {"NetFloorArea": 120.0, "FinishFloorHeight": 0.0, "FinishCeilingHeight": 8.0}


def one(parts, name):
    [got] = [p for p in parts if p["name"].startswith(name)]
    return got


def near(a, b):
    return abs(a - b) < 1e-9


def bedroom_house(build, unit="foot", scale=1.0, quantities=QTY, window=None, name="Bedroom 2", flags=None):
    """A 12 x 10 x 9 ft bedroom at the origin, a 3 x 4 ft window in its y = 10 ft wall, 2 ft along, sill 3 ft,
    lining 0.25 ft (every length times `scale` for a model in another unit)."""
    b = build.house(unit)
    q = {k: v * (scale ** 2 if "Area" in k else scale) for k, v in quantities.items()}
    bed = b.space(name, (0, 0, 0), (12 * scale, 10 * scale, 9 * scale), quantities=q, flags=flags)
    kw = dict(along=2 * scale, sill=3 * scale, width=3 * scale, height=4 * scale, lining=0.25 * scale, space=bed)
    kw.update(window or {})
    b.window("W1", (0, 10 * scale, 0), (1, 0, 0), **kw)
    return b


def test_a_feet_model_in_metres(build, tmp_path):
    d = read(bedroom_house(build).write(tmp_path / "h.ifc"))
    assert d["source"]["length_unit"] == "foot" and d["source"]["metres_per_unit"] == FT
    room = one(d["rooms"], "Bedroom 2")
    assert room["sleeping"] is True and room["floor_elevation"] == 0.0
    # 12 x 10 ft: (0,0) (3.6576,0) (3.6576,3.048) (0,3.048) m; 120 sq ft = 11.1483648 m2 = its NetFloorArea
    assert {tuple(p) for p in room["floor"]} == {(0.0, 0.0), (3.6576, 0.0), (3.6576, 3.048), (0.0, 3.048)}
    assert near(room["ceiling_height"], 8 * FT)                       # FinishCeilingHeight 8 ft = 2.4384 m
    w = one(d["openings"], "W1")
    assert w["room"] == room["id"] and w["operation"] == "casement"   # SIDEHUNGLEFTHAND
    # 3 x 4 ft at sill 3 ft, less 0.25 ft all round: u 0.25..2.75 ft, z 3.25..6.75 ft
    want = {"left": 0.25 * FT, "right": 2.75 * FT, "bottom": 3.25 * FT, "top": 6.75 * FT}
    assert set(w["frame"]) == set(want) and all(near(w["frame"][k], v) for k, v in want.items())
    assert near(w["ifc"]["opening_bottom_above_floor"], 3 * FT)


def test_the_same_house_in_millimetres_reads_the_same(build, tmp_path):
    ft = read(bedroom_house(build).write(tmp_path / "ft.ifc"))
    mm = read(bedroom_house(build, "millimetre", 304.8).write(tmp_path / "mm.ifc"))
    assert mm["source"]["metres_per_unit"] == 0.001
    for kind in ("rooms", "openings"):
        a, b = ft[kind][0], mm[kind][0]
        for key in ("floor_elevation", "ceiling_height"):
            if key in a:
                assert near(a[key], b[key])
        for key in ("left", "right", "bottom", "top"):
            if "frame" in a:
                assert near(a["frame"][key], b["frame"][key])
    a, b = sorted(map(tuple, ft["rooms"][0]["floor"])), sorted(map(tuple, mm["rooms"][0]["floor"]))
    assert len(a) == len(b) == 4 and all(near(p, q) for pa, pb in zip(a, b) for p, q in zip(pa, pb))


@pytest.mark.parametrize("drop, key", [("FinishFloorHeight", "floor_elevation"), ("FinishCeilingHeight", "ceiling_height"),
                                       ("NetFloorArea", "floor")])
def test_a_missing_quantity_leaves_its_value_out(build, tmp_path, drop, key):
    q = {k: v for k, v in QTY.items() if k != drop}
    room = read(bedroom_house(build, quantities=q).write(tmp_path / "h.ifc"))["rooms"][0]
    assert key not in room and drop in room["not_given"][key]
    if drop == "FinishFloorHeight":                                   # no finished floor: no height above it
        assert "ceiling_height" not in room


def test_an_outline_bigger_than_its_net_area_is_left_out(build, tmp_path):
    room = read(bedroom_house(build, quantities=dict(QTY, NetFloorArea=116.4)).write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor" not in room and "bigger than its stated net floor area" in room["not_given"]["floor"]


def test_a_finished_floor_above_the_slab(build, tmp_path):
    # flooring 0.1 ft: the floor is at 0.1 ft; the ceiling 8 ft above it (the space's top, 9 ft, is higher)
    room = read(bedroom_house(build, quantities=dict(QTY, FinishFloorHeight=0.1)).write(tmp_path / "h.ifc"))["rooms"][0]
    assert near(room["floor_elevation"], 0.1 * FT) and near(room["ceiling_height"], 8 * FT)
    w = read(bedroom_house(build, quantities=dict(QTY, FinishFloorHeight=0.1)).write(tmp_path / "h2.ifc"))["openings"][0]
    assert near(w["ifc"]["opening_bottom_above_floor"], 2.9 * FT)


def test_a_ceiling_no_higher_than_the_space(build, tmp_path):
    # FinishCeilingHeight 9.5 ft but the space is only 9 ft tall: 9 ft
    room = read(bedroom_house(build, quantities=dict(QTY, FinishCeilingHeight=9.5)).write(tmp_path / "h.ifc"))["rooms"][0]
    assert near(room["ceiling_height"], 9 * FT)


@pytest.mark.parametrize("name, flag, expected", [("Kitchen", True, True), ("Bedroom 2", False, None),
                                                  ("Storage", False, False)])
def test_the_gordium_flag(build, tmp_path, name, flag, expected):
    room = read(bedroom_house(build, name=name, flags={"Sleeping": flag}).write(tmp_path / "h.ifc"))["rooms"][0]
    assert room.get("sleeping") is expected


@pytest.mark.parametrize("window, why", [
    ({"panels": ("SIDEHUNGLEFTHAND", "SIDEHUNGRIGHTHAND")}, "2 panels"),
    ({"mullion": True}, "divider"),
    ({"upright": False}, "isn't upright"),
    ({"lining": None}, "LiningThickness"),
])
def test_no_frame_when_it_cant_be_told(build, tmp_path, window, why):
    w = read(bedroom_house(build, window=window).write(tmp_path / "h.ifc"))["openings"][0]
    assert "frame" not in w and why in w["not_given"]["frame"]


def test_no_frame_when_the_stated_size_isnt_the_opening(build, tmp_path):
    b = bedroom_house(build)
    [w] = b.f.by_type("IfcWindow")
    w.OverallWidth = 4.0                       # says 4 ft; the opening it fills (and its body) is 3 ft
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert "frame" not in got and "doesn't cover" in got["not_given"]["frame"]


@pytest.mark.parametrize("operation, expected", [("SIDEHUNGRIGHTHAND", "casement"), ("TOPHUNG", "awning"),
                                                 ("BOTTOMHUNG", "hopper"), ("SLIDINGHORIZONTAL", "horizontal_slider"),
                                                 ("FIXEDCASEMENT", "fixed"), ("SLIDINGVERTICAL", None),
                                                 ("NOTDEFINED", None)])
def test_window_operations(build, tmp_path, operation, expected):
    w = read(bedroom_house(build, window={"panels": (operation,)}).write(tmp_path / "h.ifc"))["openings"][0]
    assert w.get("operation") == expected
    if expected is None:
        assert operation in w["not_given"]["operation"]


@pytest.mark.parametrize("psets, expected, source", [
    ({}, False, "not marked"),
    ({"Pset_WindowCommon": {"FireExit": True}}, True, "Pset_WindowCommon.FireExit is true"),
    ({"Pset_WindowCommon": {"FireExit": False}}, False, "Pset_WindowCommon.FireExit is false"),
    ({"Gordium_Egress": {"EscapeOpening": True}, "Pset_WindowCommon": {"FireExit": False}}, False,
     "states it differently"),                # review round 4: two marks that disagree are not a mark
])
def test_an_escape_opening_only_when_marked(build, tmp_path, psets, expected, source):
    w = read(bedroom_house(build, window={"psets": psets}).write(tmp_path / "h.ifc"))["openings"][0]
    assert w["escape"] is expected and source in w["ifc"]["escape_from"]


def test_the_room_only_from_a_space_boundary(build, tmp_path):
    b = bedroom_house(build, window={"space": None})
    w = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert "room" not in w and "no space boundary" in w["not_given"]["room"]
    other = b.space("Bath", (20, 0, 0), (5, 5, 9))
    b.boundary(b.f.by_type("IfcSpace")[0], b.f.by_type("IfcWindow")[0])
    b.boundary(other, b.f.by_type("IfcWindow")[0])
    w = read(b.write(tmp_path / "h2.ifc"))["openings"][0]
    assert "room" not in w and "bounds 2 rooms" in w["not_given"]["room"]


def test_a_fixed_escape_window_measures_no_opening(build, tmp_path):
    # the one measure IFC alone settles: a fixed window marked as the escape opening has no clear opening (fails)
    b = bedroom_house(build, window={"panels": ("FIXEDCASEMENT",), "psets": {"Gordium_Egress": {"EscapeOpening": True}}})
    d = read(b.write(tmp_path / "h.ifc"))
    [o] = measure(d)["parts"]["emergency_escape_opening"]
    assert o["measures"] == {"opening_net_clear_area": 0.0, "opening_net_clear_height": 0.0,
                             "opening_net_clear_width": 0.0}


def test_a_casement_escape_window_measures_nothing(build, tmp_path):
    b = bedroom_house(build, window={"psets": {"Gordium_Egress": {"EscapeOpening": True}}})
    [o] = measure(read(b.write(tmp_path / "h.ifc")))["parts"]["emergency_escape_opening"]
    assert o["measures"] == {} and "hinged sash" in o["not_measured"]["opening_net_clear_area"]


def test_doors(build, tmp_path):
    b = bedroom_house(build)
    bed = b.f.by_type("IfcSpace")[0]
    b.door("Front", (5, 0, 0), "SINGLE_SWING_RIGHT", spaces=[bed], psets={"Gordium_Egress": {"ExitDoor": True}})
    b.door("Patio", (8, 0, 0), "SLIDING_TO_LEFT", spaces=[bed], psets={"Pset_DoorCommon": {"FireExit": False}})
    b.door("Closet", (1, 0, 0), "DOUBLE_SWING_LEFT")
    d = read(b.write(tmp_path / "h.ifc"))
    front, patio, closet = (one(d["doors"], n) for n in ("Front", "Patio", "Closet"))
    assert (front["exit"], front["operation"]) == (True, "side_hinged")
    assert (patio["exit"], patio["operation"]) == (False, "sliding")
    assert "exit" not in closet and "operation" not in closet
    # the two outside doors are openings too (each bounds one room); the closet door bounds none
    assert {o["name"] for o in d["openings"]} == {"W1", "Front", "Patio"}
    assert one(d["openings"], "Front")["operation"] == "side_hinged_door"
    assert one(d["openings"], "Patio")["operation"] == "sliding_door"
    # a door's not marked flag kills the whole doors list: needs review, never a quiet pass
    assert measure(d)["parts"]["egress_door"] is None


def test_stair_flight_numbers_and_where_each_came_from(build, tmp_path):
    b = bedroom_house(build)
    b.flight("F1", risers=14, treads=13, riser=0.6, tread=0.9)
    b.flight("F2", pset={"NumberOfRiser": 7, "RiserHeight": 0.625})
    d = read(b.write(tmp_path / "h.ifc"))
    assert "stairs" not in d
    f1, f2 = d["source"]["stair_flights"]
    # 0.6 ft = 0.18288 m, 0.9 ft = 0.27432 m
    assert (f1["risers"], f1["treads"]) == (14, 13) and near(f1["riser_height"], 0.18288)
    assert near(f1["tread_length"], 0.27432) and f1["source"]["riser_height"] == "IfcStairFlight.RiserHeight"
    assert f2["risers"] == 7 and near(f2["riser_height"], 0.625 * FT) and "treads" not in f2
    assert f2["source"] == {"risers": "Pset_StairFlightCommon.NumberOfRiser",
                            "riser_height": "Pset_StairFlightCommon.RiserHeight"}


def test_no_frame_when_the_opening_it_fills_is_bigger_than_stated(build, tmp_path):
    b = bedroom_house(build)
    [w] = b.f.by_type("IfcWindow")
    w.OverallWidth = 2.5                       # says 2.5 ft; the opening it fills is 3 ft: which is right is unclear
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert "frame" not in got and "isn't its stated" in got["not_given"]["frame"]


def test_a_quantity_in_its_own_unit(build, tmp_path):
    """Review round 1: a metre model whose NetFloorArea is stated in square feet and FinishCeilingHeight in feet
    (each quantity may carry its own unit): 120 sq ft = 11.1483648 m2, so the 12 m2 outline is refused; 7.5 ft =
    2.286 m, under the 3 m space."""
    b = build.house("metre")
    s = b.space("Bedroom", (0, 0, 0), (4, 3, 3), quantities={"NetFloorArea": 120.0, "FinishFloorHeight": 0.0,
                                                             "FinishCeilingHeight": 7.5})
    sqft = b.run("unit.add_conversion_based_unit", name="square foot")
    ft = b.run("unit.add_conversion_based_unit", name="foot")
    for q in b.f.by_type("IfcQuantityArea") + b.f.by_type("IfcQuantityLength"):
        q.Unit = sqft if q.Name == "NetFloorArea" else ft if q.Name == "FinishCeilingHeight" else None
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor" not in room and "11.1483648" in room["not_given"]["floor"]
    assert near(room["ceiling_height"], 7.5 * FT)
    assert s.LongName == "Bedroom"


def test_a_quantity_in_a_unit_of_the_wrong_kind_is_left_out(build, tmp_path):
    b = build.house("metre")
    b.space("Bedroom", (0, 0, 0), (4, 3, 3), quantities={"NetFloorArea": 12.0, "FinishFloorHeight": 0.0,
                                                         "FinishCeilingHeight": 2.5})
    ft = b.run("unit.add_conversion_based_unit", name="foot")
    [area] = [q for q in b.f.by_type("IfcQuantityArea") if q.Name == "NetFloorArea"]
    area.Unit = ft
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor" not in room and "isn't a area unit" in room["not_given"]["floor"]


def test_a_stair_property_in_its_own_unit(build, tmp_path):
    b = bedroom_house(build, "metre", FT)                 # a metre model
    fl = b.flight("F1", pset={"RiserHeight": 7.0})
    inch = b.run("unit.add_conversion_based_unit", name="inch")
    [p] = [p for p in b.f.by_type("IfcPropertySingleValue") if p.Name == "RiserHeight"]
    p.Unit = inch
    got = read(b.write(tmp_path / "h.ifc"))["source"]["stair_flights"][0]
    assert near(got["riser_height"], 7 * 0.0254) and fl.Name == "F1"


@pytest.mark.parametrize("value", ["TRUE", "Yes"])
def test_a_flag_that_isnt_true_or_false(build, tmp_path, value):
    """Review round 1: a Sleeping flag stored as text is never left to the name (a laundry flagged as slept in
    would otherwise read as not a sleeping room)."""
    room = read(bedroom_house(build, name="Laundry", flags={"Sleeping": value}).write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and repr(value) in room["not_given"]["sleeping"]
    b = bedroom_house(build, window={"psets": {"Gordium_Egress": {"EscapeOpening": value}}})
    b.door("Front", (5, 0, 0), psets={"Gordium_Egress": {"ExitDoor": value}})
    d = read(b.write(tmp_path / "h2.ifc"))
    w = d["openings"][0]
    assert w["escape"] is False and repr(value) in w["ifc"]["escape_from"]
    door = one(d["doors"], "Front")
    assert "exit" not in door and repr(value) in door["not_given"]["exit"]


@pytest.mark.parametrize("kind", ["IfcPropertyEnumeratedValue", "IfcPropertyListValue"])
def test_a_flag_stored_another_way_is_never_skipped(build, tmp_path, kind):
    """Review round 2: a Sleeping flag stored as an enumerated or list value (a yes/no pick-list) was skipped, and
    the name decided ("Laundry" -> not a sleeping room). Now the room is unknown."""
    b = bedroom_house(build, name="Laundry")
    space = b.f.by_type("IfcSpace")[0]
    value = b.f.create_entity("IfcBoolean", True)
    item = (b.f.create_entity(kind, Name="Sleeping", EnumerationValues=[value]) if kind.endswith("EnumeratedValue")
            else b.f.create_entity(kind, Name="Sleeping", ListValues=[value]))
    pset = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name="Gordium_Egress", HasProperties=[item])
    b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[space],
                      RelatingPropertyDefinition=pset)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and kind in room["not_given"]["sleeping"]


@pytest.mark.parametrize("first, second, kept", [(200.0, 100.0, False), (100.0, 200.0, False), (120.0, 120.0, True)])
def test_two_quantity_sets_must_agree(build, tmp_path, first, second, kept):
    """Review round 2: NetFloorArea stated in two sets (Qto_SpaceBaseQuantities and IFC2x3's BaseQuantities) that
    disagree: which is right is unclear, so no outline, whichever comes first (the 12 x 10 ft outline is 120 sq ft)."""
    b = bedroom_house(build, quantities=dict(QTY, NetFloorArea=first))
    space = b.f.by_type("IfcSpace")[0]
    q = b.run("pset.add_qto", product=space, name="BaseQuantities")
    b.run("pset.edit_qto", qto=q, properties={"NetFloorArea": second})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert ("floor" in room) is kept
    if not kept:
        assert "more than once, differently" in room["not_given"]["floor"]


def test_a_set_of_property_sets_in_one_relation(build, tmp_path):
    """Review round 2: IFC4 lets one IfcRelDefinesByProperties hold a set of property sets (a tuple to
    ifcopenshell); reading a window's predefined sets crashed on it."""
    b = bedroom_house(build)
    [w] = b.f.by_type("IfcWindow")
    mark = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name="Gordium_Egress", HasProperties=[
        b.f.create_entity("IfcPropertySingleValue", Name="EscapeOpening",
                          NominalValue=b.f.create_entity("IfcBoolean", True))])
    other = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name="Other", HasProperties=[
        b.f.create_entity("IfcPropertySingleValue", Name="Note", NominalValue=b.f.create_entity("IfcLabel", "x"))])
    rel = b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[w],
                            RelatingPropertyDefinition=mark)
    path = b.write(tmp_path / "h.ifc")       # ifcopenshell's API won't write a set here: edit the file's line
    text = path.read_text(encoding="utf-8")
    line = next(t for t in text.splitlines() if t.startswith(f"#{rel.id()}="))
    assert line.endswith(f",#{mark.id()});")
    path.write_text(text.replace(line, line[:-len(f"#{mark.id()});")] + f"(#{mark.id()},#{other.id()}));"),
                    encoding="utf-8")
    got = read(path)["openings"][0]
    assert got["escape"] is True and "frame" in got


def _two_sets(b, element, name, first, second):
    """Two property sets of the same name on one element, each stating `name` (a real export can carry both)."""
    for value in (first, second):
        item = value if not isinstance(value, bool) else \
            b.f.create_entity("IfcPropertySingleValue", Name=name, NominalValue=b.f.create_entity("IfcBoolean", value))
        pset = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name="Gordium_Egress", HasProperties=[item])
        b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[element],
                          RelatingPropertyDefinition=pset)


@pytest.mark.parametrize("order", [(False, True), (True, False), (False, "enum")])
def test_a_flag_stated_twice_must_agree(build, tmp_path, order):
    """Review round 3: a flag stated twice, differently, was read as the first statement ("Laundry", Sleeping
    false then true -> not a sleeping room). Now: the room is unknown, the window not marked, the door's exit
    not given."""
    b = bedroom_house(build, name="Laundry")
    [space], [window] = b.f.by_type("IfcSpace"), b.f.by_type("IfcWindow")
    door = b.door("Front", (5, 0, 0))

    def stated(name, value):
        if value != "enum":
            return value
        return b.f.create_entity("IfcPropertyEnumeratedValue", Name=name,
                                 EnumerationValues=[b.f.create_entity("IfcBoolean", True)])

    _two_sets(b, space, "Sleeping", *(stated("Sleeping", v) for v in order))
    _two_sets(b, window, "EscapeOpening", *(stated("EscapeOpening", v) for v in order))
    _two_sets(b, door, "ExitDoor", *(stated("ExitDoor", v) for v in order))
    d = read(b.write(tmp_path / "h.ifc"))
    room, w, dr = d["rooms"][0], one(d["openings"], "W1"), one(d["doors"], "Front")
    assert "sleeping" not in room and "statements that differ" in room["not_given"]["sleeping"]
    assert w["escape"] is False and "statements that differ" in w["ifc"]["escape_from"]
    assert "exit" not in dr and "statements that differ" in dr["not_given"]["exit"]


def test_the_elements_own_flag_overrides_its_types(build, tmp_path):
    # IFC's inheritance: a window type marked as not escape openings, the one window of it the architect marks
    b = bedroom_house(build, window={"psets": {"Gordium_Egress": {"EscapeOpening": True}}})
    [w] = b.f.by_type("IfcWindow")
    t = b.f.by_type("IfcWindowType")[0]
    t.HasPropertySets = list(t.HasPropertySets) + [b.f.create_entity(
        "IfcPropertySet", GlobalId=b.guid(), Name="Gordium_Egress", HasProperties=[b.f.create_entity(
            "IfcPropertySingleValue", Name="EscapeOpening", NominalValue=b.f.create_entity("IfcBoolean", False))])]
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert got["escape"] is True and "Gordium_Egress.EscapeOpening is true" in got["ifc"]["escape_from"]
    assert w.Name == "W1"


@pytest.mark.parametrize("on_type", [True, False])
def test_two_marks_must_agree(build, tmp_path, on_type):
    """Review round 4: Gordium_Egress.EscapeOpening true (on the window's type, or the window) and the window's
    own Pset_WindowCommon.FireExit false: settled by name order (escape true). Now the window's own mark wins
    over its type's, and two marks at the same level must agree, else not marked, with both named."""
    b = bedroom_house(build, window={"psets": {"Pset_WindowCommon": {"FireExit": False}} if on_type else
                                     {"Pset_WindowCommon": {"FireExit": False}, "Gordium_Egress": {"EscapeOpening": True}}})
    if on_type:
        t = b.f.by_type("IfcWindowType")[0]
        t.HasPropertySets = list(t.HasPropertySets) + [b.f.create_entity(
            "IfcPropertySet", GlobalId=b.guid(), Name="Gordium_Egress", HasProperties=[b.f.create_entity(
                "IfcPropertySingleValue", Name="EscapeOpening", NominalValue=b.f.create_entity("IfcBoolean", True))])]
    door = b.door("Front", (5, 0, 0), psets={"Gordium_Egress": {"ExitDoor": True}, "Pset_DoorCommon": {"FireExit": False}})
    d = read(b.write(tmp_path / "h.ifc"))
    w = d["openings"][0]
    assert w["escape"] is False
    if on_type:                                       # the window's own FireExit false overrides its type
        assert w["ifc"]["escape_from"] == "Pset_WindowCommon.FireExit is false"
    else:
        assert "states it differently" in w["ifc"]["escape_from"] and "FireExit" in w["ifc"]["escape_from"]
    dr = one(d["doors"], "Front")
    assert "exit" not in dr and "states it differently" in dr["not_given"]["exit"]
    assert door.Name == "Front"


def test_two_marks_that_agree(build, tmp_path):
    b = bedroom_house(build, window={"psets": {"Pset_WindowCommon": {"FireExit": True},
                                               "Gordium_Egress": {"EscapeOpening": True}}})
    w = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert w["escape"] is True
    assert w["ifc"]["escape_from"] == "Gordium_Egress.EscapeOpening and Pset_WindowCommon.FireExit is true"


@pytest.mark.parametrize("how", ["window_own", "style"])
def test_every_partitioning_stated_counts(build, tmp_path, how):
    """Review round 5: with a type, only the type's PartitioningType was read. A window whose type says
    NOTDEFINED (or is an IfcWindowStyle, IFC2x3's type, which states its partitioning as OperationType; built
    here in an IFC4 file, which IFC4 itself forbids, since the reader reads it the same either way) and whose own
    PartitioningType is DOUBLE_PANEL_VERTICAL, with one panel record, read as one casement framed across both
    panels. Now any partitioning stated, by the type or the window, that isn't single leaves both out."""
    b = bedroom_house(build)
    [w] = b.f.by_type("IfcWindow")
    t = b.f.by_type("IfcWindowType")[0]
    if how == "window_own":
        t.PartitioningType = "NOTDEFINED"
        w.PartitioningType = "DOUBLE_PANEL_VERTICAL"
    else:
        style = b.f.create_entity("IfcWindowStyle", GlobalId=b.guid(), Name="a style", ConstructionType="NOTDEFINED",
                                  OperationType="DOUBLE_PANEL_VERTICAL", ParameterTakesPrecedence=False,
                                  Sizeable=False, HasPropertySets=t.HasPropertySets)
        for rel in b.f.by_type("IfcRelDefinesByType"):
            if rel.RelatingType == t:
                rel.RelatingType = style
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert "frame" not in got and "operation" not in got
    assert "DOUBLE_PANEL_VERTICAL" in got["not_given"]["frame"] and "DOUBLE_PANEL_VERTICAL" in got["ifc"]["partitioning"]


def test_a_negative_flooring_height_is_no_floor(build, tmp_path):
    """Review round 5: FinishFloorHeight -1.5 ft put the finished floor below the slab, so the 9 ft space's top
    was 10.5 ft above it and a stated 10 ft ceiling was kept: taller than the space."""
    room = read(bedroom_house(build, quantities=dict(QTY, FinishFloorHeight=-1.5, FinishCeilingHeight=10.0))
                .write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor_elevation" not in room and "negative" in room["not_given"]["floor_elevation"]
    assert "ceiling_height" not in room


@pytest.mark.parametrize("ceiling", [0.0, -2.0])
def test_a_ceiling_at_or_below_the_floor_is_unknown(build, tmp_path, ceiling):
    room = read(bedroom_house(build, quantities=dict(QTY, FinishCeilingHeight=ceiling))
                .write(tmp_path / "h.ifc"))["rooms"][0]
    assert "ceiling_height" not in room and "above the floor" in room["not_given"]["ceiling_height"]


def test_a_mark_from_the_type_names_the_type(build, tmp_path):
    """Review round 5: a door type marked FireExit true makes every door of it an exit; the source said only
    "Pset_DoorCommon.FireExit is true", the same as a mark on one door. Now it names the type."""
    b = bedroom_house(build)
    door = b.door("Front", (5, 0, 0))
    t = b.run("root.create_entity", ifc_class="IfcDoorType", name="Entry door")
    b.run("type.assign_type", related_objects=[door], relating_type=t)
    b.pset(t, "Pset_DoorCommon", {"FireExit": True})
    w = b.f.by_type("IfcWindowType")[0]
    b.pset(w, "Pset_WindowCommon", {"FireExit": True})
    d = read(b.write(tmp_path / "h.ifc"))
    dr = one(d["doors"], "Front")
    assert dr["exit"] is True and dr["ifc"]["exit_from"].startswith("Pset_DoorCommon.FireExit (from its type Entry door #")
    assert "(from its type type of W1 #" in d["openings"][0]["ifc"]["escape_from"]


@pytest.mark.parametrize("order", [("Bedroom", "Living"), ("Living", "Bedroom")])
def test_every_classification_is_read(build, tmp_path, order):
    """Review round 6: two classifications with no code shared one key, so the last stored won: "Room 3"
    classed Bedroom and Living read as not a sleeping room in one order. Both are read: unknown either way."""
    b = bedroom_house(build, name="Room 3")
    [space] = b.f.by_type("IfcSpace")
    for name in order:
        ref = b.f.create_entity("IfcClassificationReference", Name=name)
        b.f.create_entity("IfcRelAssociatesClassification", GlobalId=b.guid(), RelatedObjects=[space],
                          RelatingClassification=ref)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room
    assert "'Bedroom'" in room["not_given"]["sleeping"] and "'Living'" in room["not_given"]["sleeping"]


@pytest.mark.parametrize("attribute", ["Name", "LongName", "ElementType"])
def test_the_space_types_names_are_read(build, tmp_path, attribute):
    """Review round 6: a space named Kitchen, typed by an IfcSpaceType named Bedroom, read as not a sleeping room
    (the type, which says what kind of space it is, was ignored). Now unknown."""
    b = bedroom_house(build, name="Kitchen")
    [space] = b.f.by_type("IfcSpace")
    t = b.run("root.create_entity", ifc_class="IfcSpaceType", name="Type 1")
    setattr(t, attribute, "Bedroom")
    b.run("type.assign_type", related_objects=[space], relating_type=t)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and f"type {attribute} 'Bedroom'" in room["not_given"]["sleeping"]


def test_the_check_fails_when_it_finds_no_models(tmp_path, monkeypatch, capsys):
    """Review round 6: --check with no models (installed away from the repo) printed "all current"."""
    import ifc_reading.__main__ as cli
    monkeypatch.setattr(cli, "MODELS", tmp_path)
    assert cli.check() == 1 and "nothing was checked" in capsys.readouterr().out


@pytest.mark.parametrize("on_type", [False, True])
def test_a_bedroom_word_in_a_description_is_doubt(build, tmp_path, on_type):
    """Review round 6: "Bedroom" in the Description of a space named Kitchen was ignored (not a sleeping room).
    A Description is free text, so other words in it say nothing; a sleeping or ask word makes it unknown."""
    b = bedroom_house(build, name="Kitchen")
    [space] = b.f.by_type("IfcSpace")
    target = space
    if on_type:
        target = b.run("root.create_entity", ifc_class="IfcSpaceType", name="Kitchen")
        b.run("type.assign_type", related_objects=[space], relating_type=target)
    target.Description = "Bedroom (kitchen to be removed)"
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and "Description 'Bedroom (kitchen to be removed)'" in room["not_given"]["sleeping"]


def test_other_words_in_a_description_say_nothing(build, tmp_path):
    b = bedroom_house(build, name="Kitchen")
    b.f.by_type("IfcSpace")[0].Description = "Oak floor, new cabinets"
    assert read(b.write(tmp_path / "h.ifc"))["rooms"][0]["sleeping"] is False


@pytest.mark.parametrize("pset, name", [("Pset_SpaceOccupancyRequirements", "OccupancyType"),
                                        ("Pset_SpaceCommon", "Category")])
def test_the_stated_use_is_a_name(build, tmp_path, pset, name):
    """Review round 7: a space named Kitchen whose stated use is Bedroom read as not a sleeping room."""
    b = bedroom_house(build, name="Kitchen")
    b.pset(b.f.by_type("IfcSpace")[0], pset, {name: "Bedroom"})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and f"{pset}.{name} 'Bedroom'" in room["not_given"]["sleeping"]


@pytest.mark.parametrize("own", [False, True])
def test_base_quantities_from_the_type_name_it(build, tmp_path, own):
    """Review round 7: a NetFloorArea stated on the space type (IFC4: type-driven, the space's own overrides) was
    read with no word that it was the type's. Now the source names the type, and the space's own value wins."""
    b = bedroom_house(build, quantities=dict(QTY, NetFloorArea=100.0) if own else {})
    [space] = b.f.by_type("IfcSpace")
    t = b.run("root.create_entity", ifc_class="IfcSpaceType", name="Bedrooms")
    b.run("type.assign_type", related_objects=[space], relating_type=t)
    q = b.run("pset.add_qto", product=t, name="Qto_SpaceBaseQuantities")
    b.run("pset.edit_qto", qto=q, properties=dict(QTY, FinishCeilingHeight=7.0))
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    if own:      # the space's 100 sq ft (smaller than its 120 sq ft outline) wins over the type's 120: refused
        assert "floor" not in room and "9.290304" in room["not_given"]["floor"]        # 100 sq ft
        assert near(room["ceiling_height"], 8 * FT)
    else:
        # IFC4: Qto_SpaceBaseQuantities is type-driven, so the type's net area is the room's (review round 10 asked
        # otherwise; its sceptics split, and IFC's reading stands); the source names the type
        assert "floor" in room and "(from its type Bedrooms #" in room["ifc"]["floor_from"]
        assert near(room["ceiling_height"], 7 * FT) and "(from its type Bedrooms #" in room["ifc"]["ceiling_from"]


def test_a_sleeping_flag_from_the_type_names_the_type(build, tmp_path):
    b = bedroom_house(build, name="Laundry")
    [space] = b.f.by_type("IfcSpace")
    t = b.run("root.create_entity", ifc_class="IfcSpaceType", name="Utility")
    b.run("type.assign_type", related_objects=[space], relating_type=t)
    b.pset(t, "Gordium_Egress", {"Sleeping": False})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert room["sleeping"] is False and "(from its type Utility #" in room["ifc"]["sleeping_from"]


@pytest.mark.parametrize("position", ["LEFT", "TOP"])
def test_a_lone_panel_beside_something_is_not_single(build, tmp_path, position):
    """Review round 7: one panel record placed LEFT (something to its right), partitioning NOTDEFINED, read as one
    casement framed across the whole window."""
    b = bedroom_house(build)
    b.f.by_type("IfcWindowType")[0].PartitioningType = "NOTDEFINED"
    b.f.by_type("IfcWindowPanelProperties")[0].PanelPosition = position
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert "frame" not in got and "operation" not in got and position in got["not_given"]["frame"]


@pytest.mark.parametrize("how", ["enumerated", "list", "two_sets"])
def test_a_stated_use_that_isnt_text_is_doubt(build, tmp_path, how):
    """Review round 8: a stated use stored as an enumerated or list value, or stated twice differently, was dropped
    silently, so a Kitchen whose use is Bedroom read as not a sleeping room."""
    b = bedroom_house(build, name="Kitchen")
    [space] = b.f.by_type("IfcSpace")
    label = b.f.create_entity("IfcLabel", "Bedroom")
    if how == "two_sets":                     # two sets of the same name: Bedroom in one, Kitchen in the other
        props = [b.f.create_entity("IfcPropertySingleValue", Name="OccupancyType",
                                   NominalValue=b.f.create_entity("IfcLabel", use)) for use in ("Bedroom", "Kitchen")]
    elif how == "enumerated":
        props = [b.f.create_entity("IfcPropertyEnumeratedValue", Name="OccupancyType", EnumerationValues=[label])]
    else:
        props = [b.f.create_entity("IfcPropertyListValue", Name="OccupancyType", ListValues=[label])]
    for prop in props:
        p = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name="Pset_SpaceOccupancyRequirements",
                              HasProperties=[prop])
        b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[space],
                          RelatingPropertyDefinition=p)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and "not a name" in room["not_given"]["sleeping"]


def test_flooring_up_to_the_top_is_no_floor(build, tmp_path):
    """Review round 8: 10 ft of flooring in a 9 ft space put the floor above the ceiling; the window's height above
    the floor came out negative."""
    d = read(bedroom_house(build, quantities=dict(QTY, FinishFloorHeight=10.0)).write(tmp_path / "h.ifc"))
    room = d["rooms"][0]
    assert "floor_elevation" not in room and "at or above the space's top" in room["not_given"]["floor_elevation"]
    assert "opening_bottom_above_floor" not in d["openings"][0]["ifc"]


@pytest.mark.parametrize("own", [False, True])
def test_a_flights_lengths_from_its_type(build, tmp_path, own):
    """Review round 8: a riser height on the flight's type didn't say so, and the flight's own differing value was
    refused instead of winning."""
    b = build.house("foot")
    f = b.flight("F1", pset={"RiserHeight": 0.6} if own else None)
    t = b.run("root.create_entity", ifc_class="IfcStairFlightType", name="Std flight")
    b.run("type.assign_type", related_objects=[f], relating_type=t)
    b.pset(t, "Pset_StairFlightCommon", {"RiserHeight": 0.65})
    [fl] = read(b.write(tmp_path / "h.ifc"))["source"]["stair_flights"]
    if own:
        assert near(fl["riser_height"], 0.6 * FT) and fl["source"]["riser_height"] == "Pset_StairFlightCommon.RiserHeight"
    else:
        assert near(fl["riser_height"], 0.65 * FT) and "(from its type Std flight #" in fl["source"]["riser_height"]


def _length_unit_to(b, unit):
    [project] = b.f.by_type("IfcProject")
    ctx = project.UnitsInContext
    ctx.Units = [u for u in ctx.Units if getattr(u, "UnitType", None) != "LENGTHUNIT"] + [unit]


def test_a_unit_whose_size_isnt_stated_is_refused(build, tmp_path):
    """Review round 9: an IfcContextDependentUnit "inch" (no size in metres) was scaled by 1: every length read as
    metres, a 62.5 sq ft bedroom as 96875 sq ft."""
    b = bedroom_house(build)
    dims = b.f.create_entity("IfcDimensionalExponents", 1, 0, 0, 0, 0, 0, 0)
    _length_unit_to(b, b.f.create_entity("IfcContextDependentUnit", Dimensions=dims, UnitType="LENGTHUNIT",
                                         Name="inch"))
    with pytest.raises(ValueError, match="can't be converted to metres"):
        read(b.write(tmp_path / "h.ifc"))


def test_a_conversion_to_an_unknown_unit_is_refused(build, tmp_path):
    b = bedroom_house(build)
    dims = b.f.create_entity("IfcDimensionalExponents", 1, 0, 0, 0, 0, 0, 0)
    odd = b.f.create_entity("IfcContextDependentUnit", Dimensions=dims, UnitType="LENGTHUNIT", Name="module")
    factor = b.f.create_entity("IfcMeasureWithUnit", b.f.create_entity("IfcLengthMeasure", 25.4), odd)
    _length_unit_to(b, b.f.create_entity("IfcConversionBasedUnit", Dimensions=dims, UnitType="LENGTHUNIT",
                                         Name="inch", ConversionFactor=factor))
    with pytest.raises(ValueError, match="conversion factor"):
        read(b.write(tmp_path / "h.ifc"))


def test_a_quantity_in_a_unit_whose_size_isnt_stated_is_left_out(build, tmp_path):
    b = bedroom_house(build)
    dims = b.f.create_entity("IfcDimensionalExponents", 1, 0, 0, 0, 0, 0, 0)
    odd = b.f.create_entity("IfcContextDependentUnit", Dimensions=dims, UnitType="LENGTHUNIT", Name="module")
    [q] = [q for q in b.f.by_type("IfcQuantityLength") if q.Name == "FinishCeilingHeight"]
    q.Unit = odd
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "ceiling_height" not in room and "can't be converted" in room["not_given"]["ceiling_height"]


def test_only_the_projects_own_units(build, tmp_path):
    """Review round 9: units were counted across every unit assignment but scaled from the project's: a project
    with none and a library in millimetres read as millimetre at 1 metre per unit."""
    b = bedroom_house(build)
    lib_unit = b.f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")
    library = b.f.create_entity("IfcProjectLibrary", GlobalId=b.guid(), Name="lib",
                                UnitsInContext=b.f.create_entity("IfcUnitAssignment", [lib_unit]))
    b.f.create_entity("IfcRelDeclares", GlobalId=b.guid(), RelatingContext=b.f.by_type("IfcProject")[0],
                      RelatedDefinitions=[library])
    d = read(b.write(tmp_path / "h.ifc"))                       # the project's foot, not the library's millimetre
    assert d["source"]["length_unit"] == "foot" and d["source"]["metres_per_unit"] == FT
    b.f.by_type("IfcProject")[0].UnitsInContext = None
    with pytest.raises(ValueError, match="states no units"):
        read(b.write(tmp_path / "h2.ifc"))


def test_the_elements_own_panel_replaces_its_types(build, tmp_path):
    """Review round 9: a window's own panel record was added to its type's, so a window overriding its type's one
    panel read as two (not measured, for the wrong reason)."""
    b = bedroom_house(build)
    [w] = b.f.by_type("IfcWindow")
    own = b.f.create_entity("IfcWindowPanelProperties", GlobalId=b.guid(), OperationType="TOPHUNG", PanelPosition="MIDDLE")
    b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[w], RelatingPropertyDefinition=own)
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert got["operation"] == "awning" and got["ifc"]["panels"] == ["TOPHUNG"] and "panels_from" not in got["ifc"]


def test_a_panel_lining_and_door_operation_from_the_type_name_it(build, tmp_path):
    b = bedroom_house(build)
    door = b.door("Front", (5, 0, 0), operation="NOTDEFINED")
    t = b.run("root.create_entity", ifc_class="IfcDoorType", name="Entry")
    t.OperationType = "SINGLE_SWING_LEFT"
    b.run("type.assign_type", related_objects=[door], relating_type=t)
    d = read(b.write(tmp_path / "h.ifc"))
    w, dr = d["openings"][0], one(d["doors"], "Front")
    assert w["ifc"]["panels_from"].startswith("from its type type of W1 #")
    assert "LiningThickness" in w["ifc"]["frame_from"] and "(from its type type of W1 #" in w["ifc"]["frame_from"]
    assert dr["ifc"]["operation_type"] == "SINGLE_SWING_LEFT"
    assert dr["ifc"]["operation_type_from"].startswith("IfcDoorType.OperationType (from its type Entry #")


def test_an_unreadable_stair_count_says_why(build, tmp_path):
    b = build.house("foot")
    f = b.flight("F1")
    prop = b.f.create_entity("IfcPropertyEnumeratedValue", Name="NumberOfRiser",
                             EnumerationValues=[b.f.create_entity("IfcCountMeasure", 14)])
    p = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name="Pset_StairFlightCommon", HasProperties=[prop])
    b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[f], RelatingPropertyDefinition=p)
    [fl] = read(b.write(tmp_path / "h.ifc"))["source"]["stair_flights"]
    assert "risers" not in fl and "not a number" in fl["not_given"]["risers"]


@pytest.mark.parametrize("where", ["name", "use", "spatial_zone"])
def test_a_bedroom_zone_is_doubt(build, tmp_path, where):
    """Review round 10: a studio drawn as one space "Living", grouped in a zone "Bedroom" (or one whose stated use
    is Bedroom), read as not a sleeping room."""
    b = bedroom_house(build, name="Living")
    [space] = b.f.by_type("IfcSpace")
    if where == "spatial_zone":
        z = b.run("root.create_entity", ifc_class="IfcSpatialZone", name="Bedroom")
        b.f.create_entity("IfcRelReferencedInSpatialStructure", GlobalId=b.guid(), RelatedElements=[space],
                          RelatingStructure=z)
    else:
        z = b.run("root.create_entity", ifc_class="IfcZone", name="Bedroom" if where == "name" else "Zone 1")
        b.run("group.assign_group", products=[space], group=z)
        if where == "use":
            b.pset(z, "Pset_SpaceOccupancyRequirements", {"OccupancyType": "Bedroom"})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and "Bedroom" in room["not_given"]["sleeping"] and "Zone" in room["not_given"]["sleeping"]


def test_a_zone_named_otherwise_says_nothing(build, tmp_path):
    b = bedroom_house(build, name="Living")
    z = b.run("root.create_entity", ifc_class="IfcZone", name="Apartment 1")
    b.run("group.assign_group", products=b.f.by_type("IfcSpace"), group=z)
    assert read(b.write(tmp_path / "h.ifc"))["rooms"][0]["sleeping"] is False


def test_an_area_unit_that_cant_be_converted_says_so(build, tmp_path):
    b = bedroom_house(build)
    ctx = b.f.by_type("IfcProject")[0].UnitsInContext
    dims = b.f.create_entity("IfcDimensionalExponents", 2, 0, 0, 0, 0, 0, 0)
    ctx.Units = [u for u in ctx.Units if getattr(u, "UnitType", None) != "AREAUNIT"] + [
        b.f.create_entity("IfcContextDependentUnit", Dimensions=dims, UnitType="AREAUNIT", Name="tsubo")]
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor" not in room and "area unit 'tsubo' can't be converted" in room["not_given"]["floor"]


def _raised_bedroom(build):
    """The bedroom on a floor 10 ft up: its window sill 3 ft above that floor."""
    b = build.house("foot")
    bed = b.space("Bedroom", (0, 0, 10), (12, 10, 9), quantities=QTY)
    b.window("W1", (0, 10, 10), (1, 0, 0), along=2, sill=3, width=3, height=4, lining=0.25, space=bed)
    return b


# the library case: since review round 14 its shapes are refused (test_a_library_refuses_shapes_even_in_radians)
@pytest.mark.parametrize("how", ["nested_unit"])
def test_shapes_and_placements_in_one_scale(build, tmp_path, how):
    """Review round 11: the geometry engine picked its own unit scale. With a project library holding its own
    units, or a foot defined through another foot, it left shapes in feet-as-metres while placements were in
    metres: the floor of a room 10 ft up read 10 m, a 3 ft sill -6 m above it."""
    b = _raised_bedroom(build)
    if how == "library":
        lib_unit = b.f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
        library = b.f.create_entity("IfcProjectLibrary", GlobalId=b.guid(), Name="lib",
                                    UnitsInContext=b.f.create_entity("IfcUnitAssignment", [lib_unit]))
        b.f.create_entity("IfcRelDeclares", GlobalId=b.guid(), RelatingContext=b.f.by_type("IfcProject")[0],
                          RelatedDefinitions=[library])
    else:
        ctx = b.f.by_type("IfcProject")[0].UnitsInContext
        [foot] = [u for u in ctx.Units if getattr(u, "UnitType", None) == "LENGTHUNIT"]
        outer = b.f.create_entity("IfcConversionBasedUnit", Dimensions=foot.Dimensions, UnitType="LENGTHUNIT",
                                  Name="foot", ConversionFactor=b.f.create_entity(
                                      "IfcMeasureWithUnit", b.f.create_entity("IfcLengthMeasure", 1.0), foot))
        ctx.Units = [u for u in ctx.Units if u != foot] + [outer]
    d = read(b.write(tmp_path / "h.ifc"))
    assert near(d["rooms"][0]["floor_elevation"], 10 * FT)
    assert near(d["openings"][0]["ifc"]["opening_bottom_above_floor"], 3 * FT)


@pytest.mark.parametrize("where", ["description", "zone"])
def test_the_architects_false_settles_a_description_or_zone_word(build, tmp_path, where):
    """Review round 11: a bedroom word in a Description or zone kept the room unknown even after the architect's
    Gordium_Egress.Sleeping false, with the reason asking the architect for the flag already given."""
    b = bedroom_house(build, name="Hall", flags={"Sleeping": False})
    [space] = b.f.by_type("IfcSpace")
    if where == "description":
        space.Description = "next to bedroom 2"
    else:
        z = b.run("root.create_entity", ifc_class="IfcZone", name="Bedroom wing")
        b.run("group.assign_group", products=[space], group=z)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert room["sleeping"] is False and room["ifc"]["sleeping_from"] == "Gordium_Egress.Sleeping is false"


@pytest.mark.parametrize("exact", [False, None])
def test_informative_window_parameters_give_no_frame(build, tmp_path, exact):
    """Review round 11: a window type whose lining and panel records are only informative (ParameterTakesPrecedence
    false, or unset) still gave a frame from them; an informative lining thinner than the real one gives a frame
    larger than the opening."""
    b = bedroom_house(build)
    b.f.by_type("IfcWindowType")[0].ParameterTakesPrecedence = exact
    got = read(b.write(tmp_path / "h.ifc"))["openings"][0]
    assert "frame" not in got and "operation" not in got and "only informative" in got["not_given"]["frame"]


def _blank(b, element, set_name, name):
    prop = b.f.create_entity("IfcPropertySingleValue", Name=name)          # NominalValue unset
    p = b.f.create_entity("IfcPropertySet", GlobalId=b.guid(), Name=set_name, HasProperties=[prop])
    b.f.create_entity("IfcRelDefinesByProperties", GlobalId=b.guid(), RelatedObjects=[element],
                      RelatingPropertyDefinition=p)


def test_a_flag_stated_with_no_value_blocks_the_types(build, tmp_path):
    """Review round 12: a property the element states with no value was skipped, so its type's applied: a window
    whose own EscapeOpening is blank was marked an escape opening from its type, a space whose own Sleeping is
    blank read not sleeping from its type."""
    b = bedroom_house(build, name="Kitchen")
    [space], [w] = b.f.by_type("IfcSpace"), b.f.by_type("IfcWindow")
    b.pset(b.f.by_type("IfcWindowType")[0], "Gordium_Egress", {"EscapeOpening": True})
    _blank(b, w, "Gordium_Egress", "EscapeOpening")
    st = b.run("root.create_entity", ifc_class="IfcSpaceType", name="ST")
    b.run("type.assign_type", related_objects=[space], relating_type=st)
    b.pset(st, "Gordium_Egress", {"Sleeping": False})
    _blank(b, space, "Gordium_Egress", "Sleeping")
    d = read(b.write(tmp_path / "h.ifc"))
    assert d["openings"][0]["escape"] is False and "stated with no value" in d["openings"][0]["ifc"]["escape_from"]
    room = d["rooms"][0]
    assert "sleeping" not in room and "stated with no value" in room["not_given"]["sleeping"]


@pytest.mark.parametrize("inner", ["IfcZone", "IfcSpatialZone"])
def test_a_bedroom_zone_holding_the_spaces_zone_is_doubt(build, tmp_path, inner):
    b = bedroom_house(build, name="Living")
    [space] = b.f.by_type("IfcSpace")
    z1 = b.run("root.create_entity", ifc_class=inner, name="Z1")
    if inner == "IfcZone":
        b.run("group.assign_group", products=[space], group=z1)
    else:
        b.f.create_entity("IfcRelReferencedInSpatialStructure", GlobalId=b.guid(), RelatedElements=[space],
                          RelatingStructure=z1)
    outer = b.run("root.create_entity", ifc_class="IfcZone", name="Bedroom")
    b.run("group.assign_group", products=[z1], group=outer)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and "'Bedroom'" in room["not_given"]["sleeping"]


def test_a_types_false_doesnt_settle_this_rooms_description(build, tmp_path):
    """Review round 12 (sceptic's note): a space type's Sleeping false, said once for every room of it, settled a
    "Bedroom 3" in one room's Description. Only the space's own false does."""
    b = bedroom_house(build, name="Kitchen")
    [space] = b.f.by_type("IfcSpace")
    space.Description = "Bedroom 3"
    st = b.run("root.create_entity", ifc_class="IfcSpaceType", name="ST")
    b.run("type.assign_type", related_objects=[space], relating_type=st)
    b.pset(st, "Gordium_Egress", {"Sleeping": False})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "sleeping" not in room and "Bedroom 3" in room["not_given"]["sleeping"]


@pytest.mark.parametrize("name, expected", [("Office", None), ("Bath Gast", None), ("Laundry", False), ("1", False)])
def test_a_types_false_doesnt_settle_the_rooms_own_name(build, tmp_path, name, expected):
    """Review round 13: a space type's Sleeping false settled an ask word ("Office") or an unknown word beside a
    not-sleeping one in the room's own name. It settles the type's words only; a room whose own name says
    nothing, or only not-sleeping words, takes it."""
    b = bedroom_house(build, name=name)
    [space] = b.f.by_type("IfcSpace")
    space.Name = None
    st = b.run("root.create_entity", ifc_class="IfcSpaceType", name="Study")
    b.run("type.assign_type", related_objects=[space], relating_type=st)
    b.pset(st, "Gordium_Egress", {"Sleeping": False})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert room.get("sleeping") is expected
    if expected is None:
        assert "said once for every room of its type" in room["not_given"]["sleeping"]


def test_a_blank_never_outvotes_a_real_statement(build, tmp_path):
    """Review round 13: since round 12 a blank counted as a statement that disagreed: the architect's
    EscapeOpening true beside a blank FireExit read not marked, ExitDoor true beside a blank FireExit unknown,
    and a "Bedroom 2" with a blank Sleeping (and no type) unknown. A blank only blocks its type's value."""
    b = bedroom_house(build, window={"psets": {"Gordium_Egress": {"EscapeOpening": True}}})
    [space], [w] = b.f.by_type("IfcSpace"), b.f.by_type("IfcWindow")
    _blank(b, w, "Pset_WindowCommon", "FireExit")
    door = b.door("Front", (5, 0, 0), psets={"Gordium_Egress": {"ExitDoor": True}})
    _blank(b, door, "Pset_DoorCommon", "FireExit")
    _blank(b, space, "Gordium_Egress", "Sleeping")
    d = read(b.write(tmp_path / "h.ifc"))
    assert d["openings"][0]["escape"] is True
    assert one(d["doors"], "Front")["exit"] is True
    assert d["rooms"][0]["sleeping"] is True


def _degrees(b):
    rad = b.f.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")
    dims = b.f.create_entity("IfcDimensionalExponents", 0, 0, 0, 0, 0, 0, 0)
    deg = b.f.create_entity("IfcConversionBasedUnit", Dimensions=dims, UnitType="PLANEANGLEUNIT", Name="DEGREE",
                            ConversionFactor=b.f.create_entity(
                                "IfcMeasureWithUnit", b.f.create_entity("IfcPlaneAngleMeasure", 0.017453292519943295), rad))
    ctx = b.f.by_type("IfcProject")[0].UnitsInContext
    ctx.Units = [u for u in ctx.Units if getattr(u, "UnitType", None) != "PLANEANGLEUNIT"] + [deg]


def _library(b):
    library = b.f.create_entity("IfcProjectLibrary", GlobalId=b.guid(), Name="lib", UnitsInContext=b.f.create_entity(
        "IfcUnitAssignment", [b.f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")]))
    b.f.create_entity("IfcRelDeclares", GlobalId=b.guid(), RelatingContext=b.f.by_type("IfcProject")[0],
                      RelatedDefinitions=[library])


@pytest.mark.parametrize("library", [False, True])
def test_angles_in_degrees(build, tmp_path, library):
    """Angles in degrees (as ArchiCAD writes, FZK-Haus among them) read as degrees. But with a project library the
    geometry engine finds no units and reads them as radians (a 90 degree turn came out 117); its angle-unit
    setting changes nothing, so then shapes are refused, with the reason."""
    b = _raised_bedroom(build)
    _degrees(b)
    if library:
        _library(b)
    d = read(b.write(tmp_path / "h.ifc"))
    room, w = d["rooms"][0], d["openings"][0]
    if library:
        assert "floor_elevation" not in room and "misreads its angles" in room["not_given"]["floor_elevation"]
        assert "frame" not in w and "misreads its angles" in w["not_given"]["frame"]
    else:
        assert near(room["floor_elevation"], 10 * FT) and "frame" in w


def test_no_angle_unit_refuses_shapes(build, tmp_path):
    """Review round 14: with no angle unit stated, the geometry engine turned a revolved shape the other way (+90
    degrees came out -90). Real exporters state one; a file that doesn't has its shapes refused."""
    b = _raised_bedroom(build)
    ctx = b.f.by_type("IfcProject")[0].UnitsInContext
    ctx.Units = [u for u in ctx.Units if getattr(u, "UnitType", None) != "PLANEANGLEUNIT"]
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor_elevation" not in room and "0 angle units" in room["not_given"]["floor_elevation"]


def test_a_library_refuses_shapes_even_in_radians(build, tmp_path):
    """Sceptic, review round 14: with a project library the engine also turned radians the other way."""
    b = _raised_bedroom(build)
    _library(b)
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor_elevation" not in room and "2 contexts" in room["not_given"]["floor_elevation"]


def test_a_degree_defined_through_a_degree_refuses_shapes(build, tmp_path):
    """Sceptic, review round 14: a degree defined as 1 degree (itself from radians) was read as radians."""
    b = _raised_bedroom(build)
    _degrees(b)
    ctx = b.f.by_type("IfcProject")[0].UnitsInContext
    [deg] = [u for u in ctx.Units if getattr(u, "UnitType", None) == "PLANEANGLEUNIT"]
    outer = b.f.create_entity("IfcConversionBasedUnit", Dimensions=deg.Dimensions, UnitType="PLANEANGLEUNIT",
                              Name="DEGREE", ConversionFactor=b.f.create_entity(
                                  "IfcMeasureWithUnit", b.f.create_entity("IfcPlaneAngleMeasure", 1.0), deg))
    ctx.Units = [u for u in ctx.Units if u != deg] + [outer]
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor_elevation" not in room and "defined directly" in room["not_given"]["floor_elevation"]


def _ifc2x3_bedroom(tmp_path, degrees):
    """An IFC2x3 file (no IfcContext in that schema): one project, metres, a 4 x 3 x 3 m Bedroom."""
    import ifcopenshell.api as api
    import ifcopenshell.api.owner.settings as owner
    f = api.run("project.create_file", version="IFC2X3")
    po = f.create_entity("IfcPersonAndOrganization", f.create_entity("IfcPerson", FamilyName="x"),
                         f.create_entity("IfcOrganization", Name="o"))
    app = f.create_entity("IfcApplication", po.TheOrganization, "1", "a", "a")
    keep = owner.get_user, owner.get_application
    owner.get_user, owner.get_application = (lambda f: po), (lambda f: app)
    try:
        r = lambda u, **k: api.run(u, f, **k)
        project = r("root.create_entity", ifc_class="IfcProject", name="P")
        rad = f.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")
        angle = f.create_entity("IfcConversionBasedUnit", Dimensions=f.create_entity(
            "IfcDimensionalExponents", 0, 0, 0, 0, 0, 0, 0), UnitType="PLANEANGLEUNIT", Name="DEGREE",
            ConversionFactor=f.create_entity("IfcMeasureWithUnit", f.create_entity(
                "IfcPlaneAngleMeasure", 0.017453292519943295), rad)) if degrees else rad
        r("unit.assign_unit", units=[r("unit.add_si_unit", unit_type="LENGTHUNIT"),
                                     r("unit.add_si_unit", unit_type="AREAUNIT"), angle])
        model = r("context.add_context", context_type="Model")
        body = r("context.add_context", context_type="Model", context_identifier="Body", target_view="MODEL_VIEW",
                 parent=model)
        storey = r("root.create_entity", ifc_class="IfcBuildingStorey")
        r("aggregate.assign_object", products=[storey], relating_object=project)
        r("geometry.edit_object_placement", product=storey)
        s = r("root.create_entity", ifc_class="IfcSpace", name="1")
        s.LongName, s.InteriorOrExteriorSpace = "Bedroom", "INTERNAL"
        r("aggregate.assign_object", products=[s], relating_object=storey)
        r("geometry.edit_object_placement", product=s)
        r("geometry.assign_representation", product=s, representation=r(
            "geometry.add_wall_representation", context=body, length=4, height=3, thickness=3))
        q = r("pset.add_qto", product=s, name="BaseQuantities")
        r("pset.edit_qto", qto=q, properties={"NetFloorArea": 12.0, "FinishFloorHeight": 0.0, "FinishCeilingHeight": 2.5})
    finally:
        owner.get_user, owner.get_application = keep
    path = tmp_path / "x3.ifc"
    f.write(str(path))
    return path


@pytest.mark.parametrize("degrees", [True, False])
def test_an_ifc2x3_file_reads_its_shapes(tmp_path, degrees):
    """Review round 14: IfcContext is IFC4's, so an IFC2x3 file counted 0 contexts and every shape was refused
    ("0 contexts (a project library ...)"). It counts its project (and any project libraries) now."""
    pytest.importorskip("ifcopenshell")
    room = read(_ifc2x3_bedroom(tmp_path, degrees))["rooms"][0]
    assert room["floor_elevation"] == 0.0 and near(room["ceiling_height"], 2.5)


@pytest.mark.parametrize("lean", [1e-6, -1e-6])
def test_a_wall_out_by_drawing_noise_is_still_a_wall(build, tmp_path, lean):
    """Review round 15: faces were sorted into floor and ceiling by any tilt over 1e-9, so a side wall 1e-6 m out
    of plumb over 3 m counted as floor (or ceiling) and the level floor was refused as "a step or a slope"."""
    b = build.house("metre")
    f = b.f
    s = f.create_entity("IfcSpace", GlobalId=b.guid(), Name="1", LongName="Bedroom")
    b.run("aggregate.assign_object", products=[s], relating_object=b.storey)
    b.place(s, (0, 0, 0))
    pt = lambda *c: f.createIfcCartesianPoint([float(x) for x in c])  # noqa: E731
    bot = [pt(0, 0, 0), pt(4, 0, 0), pt(4, 3, 0), pt(0, 3, 0)]
    top = [pt(0, 0, 3), pt(4 + lean, 0, 3), pt(4 + lean, 3, 3), pt(0, 3, 3)]
    face = lambda pts: f.createIfcFace([f.createIfcFaceOuterBound(f.createIfcPolyLoop(pts), True)])  # noqa: E731
    faces = [face(bot[::-1]), face(top)] + [face([bot[i], bot[(i + 1) % 4], top[(i + 1) % 4], top[i]])
                                             for i in range(4)]
    brep = f.createIfcFacetedBrep(f.createIfcClosedShell(faces))
    s.Representation = f.createIfcProductDefinitionShape(
        None, None, [f.createIfcShapeRepresentation(b.body, "Body", "Brep", [brep])])
    q = b.run("pset.add_qto", product=s, name="Qto_SpaceBaseQuantities")
    b.run("pset.edit_qto", qto=q, properties={"NetFloorArea": 12.0, "FinishFloorHeight": 0.0,
                                               "FinishCeilingHeight": 2.5})
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "floor" in room, room.get("not_given")
    assert room["floor_elevation"] == 0.0 and room["ceiling_height"] == 2.5


def test_a_stepped_floor_has_no_one_height_to_measure_from(build, tmp_path):
    """Review round 16: with half the floor 0.5 m up, the finished floor was taken at the lower half, so the ceiling
    read 2.9 m where over the raised half it is 2.5 m. A stepped underside now leaves the floor's elevation, and so
    the ceiling height, out."""
    b = build.house("metre")
    s = b.space("Bedroom", (0, 0, 0), (4, 3, 3),
                quantities={"NetFloorArea": 12.0, "FinishFloorHeight": 0.0, "FinishCeilingHeight": 2.9})
    side = [(0, 0), (2, 0), (2, 0.5), (4, 0.5), (4, 3), (0, 3)]     # (x, z): the step at x = 2
    verts = [(x, 0.0, z) for x, z in side] + [(x, 3.0, z) for x, z in side]
    faces = [list(range(6)), list(range(11, 5, -1))] + [[i, 6 + i, 6 + (i + 1) % 6, (i + 1) % 6] for i in range(6)]
    s.Representation = None
    b.run("geometry.assign_representation", product=s, representation=b.run(
        "geometry.add_mesh_representation", context=b.body, vertices=[verts], faces=[faces]))
    room = read(b.write(tmp_path / "h.ifc"))["rooms"][0]
    assert "ceiling_height" not in room and "floor_elevation" not in room and "floor" not in room
    assert "isn't at one level (0.0 to 0.5 m)" in room["not_given"]["floor_elevation"]


def test_an_ifc2x3_flight_keeps_its_riser_count(tmp_path):
    """Review round 17: IFC2x3 names the attribute NumberOfRiser; only IFC4's NumberOfRisers was read, so the
    count vanished with no reason."""
    import ifcopenshell
    import ifcopenshell.guid as guid
    f = ifcopenshell.file(schema="IFC2X3")
    units = [f.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE"),
             f.create_entity("IfcSIUnit", UnitType="PLANEANGLEUNIT", Name="RADIAN")]
    f.create_entity("IfcProject", GlobalId=guid.new(), Name="P",
                    UnitsInContext=f.create_entity("IfcUnitAssignment", Units=units))
    f.create_entity("IfcStairFlight", GlobalId=guid.new(), Name="flight", NumberOfRiser=16, NumberOfTreads=15)
    f.write(str(tmp_path / "s.ifc"))
    flight = read(tmp_path / "s.ifc")["source"]["stair_flights"][0]
    assert flight["risers"] == 16 and flight["source"]["risers"] == "IfcStairFlight.NumberOfRiser"


@pytest.mark.parametrize("typed, read_as", [("DOUBLE_DOOR_SINGLE_SWING", None), ("SINGLE_SWING_LEFT", "side_hinged")])
def test_a_door_and_its_type_must_agree_on_how_it_opens(build, tmp_path, typed, read_as):
    """Review round 17: a door saying single swing whose type says double door read as one side-hinged leaf; IFC4
    says the door's own operation is only for a door without a type. Now a disagreement leaves it out."""
    b = build.house("metre")
    room = b.space("Bedroom", (0, 0, 0), (4, 4, 2.5))
    d = b.door("front", (0, 0, 0), operation="SINGLE_SWING_LEFT", width=1.8, height=2.1, spaces=[room])
    t = b.run("root.create_entity", ifc_class="IfcDoorType", name="the type")
    t.OperationType = typed
    b.run("type.assign_type", related_objects=[d], relating_type=t)
    desc = read(b.write(tmp_path / "h.ifc"))
    door = desc["doors"][0]
    assert door.get("operation") == read_as
    if read_as is None:
        assert "states SINGLE_SWING_LEFT but its type states DOUBLE_DOOR" in door["not_given"]["operation"]
        assert "operation" not in desc["openings"][0]
