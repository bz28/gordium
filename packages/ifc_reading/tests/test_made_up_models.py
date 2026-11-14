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
