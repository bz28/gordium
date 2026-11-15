"""KIT's FZK-Haus (test_data/ifc_models/ac20_fzk_haus): what the reader makes of a real ArchiCAD IFC4 export.

Every expected value here was worked out by hand from the file's own STEP lines before the assertion was written
(the line references are next to each); none is taken from the reader's output.
"""

import copy
from pathlib import Path

import pytest
import yaml

ifcopenshell = pytest.importorskip("ifcopenshell")

from ifc_reading import read  # noqa: E402
from ifc_reading.__main__ import check, dump  # noqa: E402
from model_measurement.interior import measure  # noqa: E402

FOLDER = Path(__file__).parents[3] / "test_data" / "ifc_models" / "ac20_fzk_haus"
MODEL = FOLDER / "AC20-FZK-Haus.ifc"

BEDROOM = "347jFE2yX7IhCEIALmupEH"      # #20909 IFCSPACE '4', LongName 'Schlafzimmer'
KITCHEN = "17JZcMFrf5tOftUTidA0d3"      # #34763 IFCSPACE '6', LongName 'K\X2\00FC\X0\che'
OFFICE = "2RSCzLOBz4FAK$_wE8VckM"       # #21640 'Buero'
LIVING = "0Lt8gR_E9ESeGH5uY_g9e9"       # #33774 'Wohnen'
HALL = "3$f2p7VyLB7eox67SA_zKE"         # #34191 'Flur'
GALLERY = "2dQFggKBb1fOc1CqZDIDlx"      # #76214 'Galerie', on the Dachgeschoss (#35065, Elevation 2.7)
WINDOW_8 = "13aSY79zb8fP4HApEJ0z_e"     # #31818 IFCWINDOW 'EG-Fenster-8', 1.2 high, 2. wide
ROUND = "1zOBw0Gej5Wf0QAJfHnOc0"        # #66459 'OG-Fenster-2', type 'Rundfenster 13' (a round window)
FRONT_DOOR = "2jTRqchjf7oB0yhQ6462T0"   # #27013 IFCDOOR 'Haustuer'
INNER_DOOR_2 = "0pGAjlJMP3ifYPATVF5xAR"  # #19199 'Innentuer-2', Pset_DoorCommon.FireExit = .F.


@pytest.fixture(scope="module")
def house():
    return read(MODEL)


def by_id(parts, id_):
    [got] = [p for p in parts if p["id"] == id_]
    return got


def test_the_file_and_its_unit(house):
    src = house["source"]
    assert house["format"] == "gordium.interior/1" and house["units"] == "m"
    # #13 IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.)
    assert (src["schema"], src["length_unit"], src["metres_per_unit"]) == ("IFC4", "metre", 1.0)
    assert src["sha256"] == "70cc8ff245fc0894201d96496c031005a5cbd7a96b22d8a1b87c5a883fb77994"


def test_seven_rooms_and_which_are_sleeping_rooms(house):
    rooms = {r["id"]: r for r in house["rooms"]}
    assert len(rooms) == 7
    assert rooms[BEDROOM]["sleeping"] is True                          # Schlafzimmer: bedroom
    assert rooms[KITCHEN]["sleeping"] is False and rooms[LIVING]["sleeping"] is False
    assert rooms[HALL]["sleeping"] is False
    for unknown in (OFFICE, GALLERY):                                  # Buero, Galerie: could be slept in
        assert "sleeping" not in rooms[unknown]
        assert "the architect says" in rooms[unknown]["not_given"]["sleeping"]


def test_the_bedroom(house):
    bed = by_id(house["rooms"], BEDROOM)
    # base: placement #20909 -> z 0 (storey #477 at 0); BaseQuantities FinishFloorHeight 0. (#21090 family)
    assert bed["floor_elevation"] == 0.0
    # FinishCeilingHeight 2.5; the body (#20868, bounding box #20885 5.45 x 4.05 x 2.5) is level on top at 2.5
    assert bed["ceiling_height"] == 2.5
    # FootPrint #20897: 5.45 x 4.05 = 22.0725 m2, but NetFloorArea 21.410325 (ArchiCAD's 3% plaster cut): no floor
    assert "floor" not in bed
    assert "22.0725" in bed["not_given"]["floor"] and "21.410325" in bed["not_given"]["floor"]


def test_the_kitchen_floor_outline(house):
    kitchen = by_id(house["rooms"], KITCHEN)
    # FootPrint #34752 (0,0) (3.71,0) (3.71,4.395) (0,4.395) (0,3.5 on an edge) in placement #34672: origin
    # (0.3, 4.01), x axis (0,-1,0), so y axis (1,0,0): the corners are (0.3,4.01) (0.3,0.3) (4.695,0.3) (4.695,4.01)
    corners = {tuple(round(v, 9) for v in p) for p in kitchen["floor"]}
    assert corners == {(0.3, 4.01), (0.3, 0.3), (4.695, 0.3), (4.695, 4.01)}
    # 4.395 x 3.71 = 16.30545 m2 = its NetFloorArea, so the outline is kept
    assert "16.30545" in kitchen["ifc"]["floor_from"]


def test_a_sloped_ceiling_is_left_out(house):
    gallery = by_id(house["rooms"], GALLERY)
    assert gallery["floor_elevation"] == 2.7                           # Dachgeschoss Elevation 2.7
    assert "isn't level" in gallery["not_given"]["ceiling_height"]


def test_the_bedroom_window(house):
    w = by_id(house["openings"], WINDOW_8)
    # #76772 IFCRELSPACEBOUNDARY(..., #20909, #31818, ...): it opens from the bedroom
    assert w["room"] == BEDROOM
    assert w["escape"] is False                                        # no FireExit, no Gordium_Egress
    # OverallHeight 1.2, OverallWidth 2.; placement chain #477 (z 0) -> wall #31422 (z 0) -> opening #31493
    # (z 0.8) -> window #31799 (z 0): its opening's bottom is 0.8 (ArchiCAD's own 'Brüstungshöhe' says 0.8)
    assert (w["ifc"]["overall_width"], w["ifc"]["overall_height"]) == (2.0, 1.2)
    assert w["ifc"]["opening_bottom"] == 0.8 and w["ifc"]["opening_bottom_above_floor"] == 0.8
    # two IfcWindowPanelProperties (#24193, #24195): a pair of casements, not measured yet: no frame, no operation
    assert "frame" not in w and "operation" not in w
    assert "2 panels" in w["not_given"]["frame"]


def test_a_round_window_gets_no_frame(house):
    w = by_id(house["openings"], ROUND)
    # 1.0 x 1.0 overall, but BaseQuantities Area 0.785082789239 (a circle): its bounding box isn't its opening
    assert "frame" not in w and "isn't rectangular" in w["not_given"]["frame"]


def test_doors(house):
    doors = {d["id"]: d for d in house["doors"]}
    assert len(doors) == 5
    assert doors[INNER_DOOR_2]["exit"] is False                        # Pset_DoorCommon.FireExit .F.
    assert doors[INNER_DOOR_2]["operation"] == "side_hinged"           # type SINGLE_SWING_LEFT
    assert "exit" not in doors[FRONT_DOOR]                             # the model doesn't say
    for d in doors.values():
        assert not {"stops", "hinge_pin", "leaf_closed", "threshold_top", "head_stop_bottom"} & set(d)
    # the front door bounds only the hall: it is also an opening, under its own id
    opening = by_id(house["openings"], FRONT_DOOR + "/opening")
    assert opening["room"] == HALL and opening["escape"] is False


def test_stairs_and_guards_are_not_read(house):
    assert "stairs" not in house and "guards" not in house
    assert [s["name"] for s in house["source"]["stairs_seen"]] == ["Wendeltreppe"]    # #14502
    assert house["source"]["stair_flights"] == []


def test_every_id_is_unique(house):
    ids = [p["id"] for k in ("rooms", "openings", "doors") for p in house[k]]
    assert len(ids) == len(set(ids))


def test_measured_every_unsettled_kind_needs_review(house):
    got = measure(house)
    parts = got["parts"]
    assert parts["sleeping_room"] is None                              # the office says nothing more
    assert parts["stair"] is None and parts["guard"] is None and parts["egress_door"] is None
    assert parts["emergency_escape_opening"] == []                     # nothing marked
    assert any("Buero" in p for p in got["problems"])


def test_measured_once_the_architect_marks_it(house, tmp_path):
    """The same house with the architect's flags added (Gordium_Egress): the office and gallery aren't sleeping
    rooms, bedroom window 8 is the escape opening, the front door the exit door."""
    import ifcopenshell.api as api
    f = ifcopenshell.open(str(MODEL))

    def flag(guid, values):
        p = api.run("pset.add_pset", f, product=f.by_guid(guid), name="Gordium_Egress")
        api.run("pset.edit_pset", f, pset=p, properties=values)

    flag(OFFICE, {"Sleeping": False})
    flag(GALLERY, {"Sleeping": False})
    flag(WINDOW_8, {"EscapeOpening": True})
    for d in f.by_type("IfcDoor"):
        flag(d.GlobalId, {"ExitDoor": d.GlobalId == FRONT_DOOR})
    f.write(str(tmp_path / "marked.ifc"))
    got = measure(read(tmp_path / "marked.ifc"))["parts"]
    [bed] = got["sleeping_room"]
    assert bed["id"] == BEDROOM
    assert "sleeping_room_floor_area" not in bed["measures"]          # its outline is bigger than its net area
    [opening] = got["emergency_escape_opening"]
    assert (opening["id"], opening["within"]) == (WINDOW_8, BEDROOM)
    assert opening["measures"] == {}                                   # a pair of casements: nothing measured
    assert "opening_net_clear_area" in opening["not_measured"]
    [door] = got["egress_door"]
    assert door["id"] == FRONT_DOOR and door["measures"] == {}


def test_the_committed_description_is_current(house):
    want = (FOLDER / "AC20-FZK-Haus_interior.yaml").read_text(encoding="utf-8")
    assert dump(house) == want
    assert check() == 0
    assert yaml.safe_load(want)["source"]["file"] == MODEL.name
    assert copy.deepcopy(house) == yaml.safe_load(want)
