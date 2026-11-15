"""How many primary buildings stand on the lot (primary_buildings: §325-3B PRIMARY STRUCTURE, §325-8B(1)), read from
made-up lots and from a real .3dm file. Expected counts are worked out by hand from what is drawn: the main building
is one; a solid standing apart from it is a second only if it could hold a home (enclosed, a story tall, a
habitable room's 70 sf) and isn't listed as an accessory building; where the drawing can't tell, both ends are
readings and there is no value (never a guess)."""

import sys
from pathlib import Path

from model_measurement.places.ithaca_city.measure import measure
from model_measurement.read_3dm import read_site

sys.path.insert(0, str(Path(__file__).parent))
from test_measure import FACTS, RECT, box, lot  # noqa: E402
from test_read_3dm import FACTS as FILE_FACTS  # noqa: E402
from test_read_3dm import box as file_box  # noqa: E402
from test_read_3dm import model, rect, write  # noqa: E402

BIG = lot([(0, 0), (100, 0), (100, 200), (0, 200)])          # room for two houses (street along y = 0)
WIDE = {**FACTS, "street_line": [[[0, 0], [100, 0]]]}
HOUSE = box(10, 25, 40, 65, 0, 30, id="house")


def count(*buildings, lot_=BIG, **facts):
    m = measure({"units": "ft", "lot": lot_, "buildings": list(buildings), "problems": []}, {**WIDE, **facts})
    return m["primary_buildings"]


def ends(rec):
    return sorted(r["value"] for r in rec["readings"])


def test_one_house_is_one_primary_building():
    rec = count(HOUSE)
    assert rec["value"] == 1 and not rec["readings"] and rec["reason"] is None


def test_a_shed_too_small_or_too_low_for_a_home_is_not_counted():
    shed = box(70, 150, 78, 158, 0, 9, id="shed")                 # 64 sf: under a habitable room's 70 sf
    deck = box(60, 100, 90, 140, 0, 3, id="deck")                 # 1,200 sf but 3 ft high: under a 7 ft story
    rec = count(HOUSE, shed, deck, main_building="house")
    assert rec["value"] == 1 and not rec["readings"]


def test_a_garage_touching_the_house_is_part_of_it():
    garage = box(40, 25, 62, 47, 0, 12, id="garage")             # shares the house's east wall
    assert count(HOUSE, garage)["value"] == 1


def test_a_building_standing_apart_that_could_hold_a_home_is_read_both_ways():
    """A 20 x 22 ft, 12 ft high garage 15 ft behind the house: a garage (1 primary building) or a second house (2).
    The drawing can't tell, so there is no value until the architect says."""
    garage = box(10, 80, 30, 102, 0, 12, id="garage")
    rec = count(HOUSE, garage, main_building="house")
    assert rec["value"] is None and ends(rec) == [1, 2]
    assert "enter the primary buildings on the lot" in rec["reason"]
    assert rec["objects"] == ["garage"]


def test_listed_as_an_accessory_building_it_isnt_counted():
    garage = box(10, 80, 30, 102, 0, 12, id="garage")
    rec = count(HOUSE, garage, accessory_buildings=["garage"])
    assert rec["value"] == 1 and not rec["readings"]


def test_two_houses_and_a_third_read_from_one_to_three():
    second = box(55, 25, 85, 65, 0, 30, id="second")
    third = box(30, 120, 60, 160, 0, 24, id="third")
    rec = count(HOUSE, second, third, main_building="house")
    assert rec["value"] is None and ends(rec) == [1, 3]


def test_the_architects_count_stands():
    second = box(55, 25, 85, 65, 0, 30, id="second")
    assert count(HOUSE, second, main_building="house", primary_buildings=2)["value"] == 2
    assert count(HOUSE, second, main_building="house", primary_buildings=1)["value"] == 1   # "the other is a garage"
    assert count(HOUSE, primary_buildings=2)["value"] == 2       # one drawn, another standing there (stated)


def test_no_main_building_picked_means_no_count():
    second = box(55, 25, 85, 65, 0, 30, id="second")
    rec = count(HOUSE, second)
    assert rec["value"] is None and not rec["readings"] and "pick the main building" in rec["reason"]


def test_no_building_means_no_count():
    rec = count()
    assert rec["value"] is None and not rec["readings"] and rec["reason"]


def test_read_from_a_rhino_file(tmp_path):
    """The same count from a .3dm written with rhino3dm (Rhino's own file library): a house and, 40 ft behind it, a
    second building of 30 x 30 x 20 ft; then a 6 x 6 ft shed instead."""
    m = model()
    rect(m, 0, 0, 100, 200)
    house = file_box(m, 10, 25, 40, 65, 30)
    file_box(m, 10, 105, 40, 135, 20)
    site = read_site(write(m, tmp_path), FILE_FACTS)
    facts = {**FILE_FACTS, "street_line": [[[0, 0], [100, 0]]], "main_building": str(house)}
    rec = measure(site, facts)["primary_buildings"]
    assert rec["value"] is None and ends(rec) == [1, 2]
    m2 = model()
    rect(m2, 0, 0, 100, 200)
    house2 = file_box(m2, 10, 25, 40, 65, 30)
    file_box(m2, 60, 150, 66, 156, 8)
    site2 = read_site(write(m2, tmp_path, "shed.3dm"), FILE_FACTS)
    rec2 = measure(site2, {**facts, "main_building": str(house2)})["primary_buildings"]
    assert rec2["value"] == 1 and not rec2["readings"]
