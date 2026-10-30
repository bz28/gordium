"""A detached accessory dwelling unit's building (§325-28C), the solid the architect picks (adu_building): measured on
its own, never as the main building, never twice (it leaves §325-25's accessory measurements and the count of primary
buildings), and never left unjudged (said not to be a detached ADU, it is an ordinary accessory building again).

Every expected value is worked by hand from the made-up lot: 50 x 100 ft, the street along y = 0, the side lot lines
x = 0 and x = 50, the rear lot line y = 100; the house 10..35 x 25..55, 30 ft tall."""

import sys
from pathlib import Path

import pytest

from model_measurement.measure import ADU_MEASURES, TAX_MAP_SLACK, measure
from model_measurement.project import fact_problems
from model_measurement.stops import stop

sys.path.insert(0, str(Path(__file__).parent))
from test_measure import FACTS, RECT, box  # noqa: E402

HOUSE = box(10, 25, 35, 55, id="house")
ADU = box(30, 70, 45, 90, 0, 18, id="adu")          # 15 x 20 ft, 18 ft tall, flat roof
DETACHED = {"accessory_dwelling_unit": True, "adu_detached": True, "adu_building": "adu", "main_building": "house"}


def _m(*buildings, lot_=RECT, **facts):
    return measure({"units": "ft", "lot": lot_, "buildings": list(buildings), "problems": []}, {**FACTS, **facts})


def _v(m, *names):
    return tuple(m[n]["value"] for n in names)


def test_the_picked_building_is_measured_on_its_own():
    m = _m(HOUSE, ADU, **DETACHED)
    # footprint 15 x 20 = 300 sf; 18 ft tall from the ground at 0; a plain 18 ft solid holds at most floor(18 / 7) = 2
    # stories; from the street 70 ft (y = 70); side: min(30 - 0, 50 - 45) = 5 ft; rear: 100 - 90 = 10 ft
    assert _v(m, "adu_footprint", "adu_height", "adu_stories") == (300.0, 18.0, 2)
    assert _v(m, "adu_front_yard", "adu_side_yard", "adu_rear_yard") == (70.0, 5.0, 10.0)
    assert m["adu_stories"]["how"].startswith("at most 2")
    # the house is still the main building and its yards are to the house alone: front 25, rear 100 - 55 = 45
    assert _v(m, "front_yard", "rear_yard", "side_yard_smaller") == (25.0, 45.0, 10.0)
    # the ADU's building is never judged again as an ordinary accessory building, nor counted as a primary one
    assert _v(m, "accessory_buildings", "primary_buildings") == (0, 1)
    assert m["accessory_side_yard"]["reason"] == stop("no_accessory")
    # coverage still counts every building: 25 x 30 + 300 = 1,050 sf
    assert m["building_area"]["value"] == 1050.0


def test_said_not_to_be_a_detached_adu_it_is_an_ordinary_accessory_building_again():
    for no in ({"accessory_dwelling_unit": False}, {"adu_detached": False}):
        m = _m(HOUSE, ADU, **{**DETACHED, **no})
        assert _v(m, "accessory_buildings", "accessory_side_yard", "accessory_rear_yard") == (1, 5.0, 10.0), no
        assert all(m[n]["value"] is None and m[n]["reason"] == stop("no_detached_adu") for n in ADU_MEASURES), no


def test_another_accessory_building_keeps_its_own_measurements():
    shed = box(2, 80, 8, 86, 0, 8, id="shed")            # 2 ft from the west side line, 14 ft from the rear
    m = _m(HOUSE, ADU, shed, **DETACHED, accessory_buildings=["shed"])
    assert _v(m, "accessory_buildings", "accessory_side_yard", "accessory_rear_yard") == (1, 2.0, 14.0)
    assert _v(m, "adu_side_yard", "adu_rear_yard") == (5.0, 10.0)


def test_nothing_picked_or_a_pick_that_cant_be_the_adu_waits_saying_why():
    m = _m(HOUSE, ADU, main_building="house", accessory_dwelling_unit=True, adu_detached=True)
    assert all(m[n]["reason"] == stop("no_adu_building") for n in ADU_MEASURES)
    assert m["accessory_buildings"]["value"] == 1          # not picked: an ordinary accessory building meanwhile
    m = _m(HOUSE, ADU, **{**DETACHED, "adu_building": "gone"})
    assert all(m[n]["reason"] == stop("adu_not_found") for n in ADU_MEASURES)
    # touching the house (within 0.1 ft) it is part of the main building (§325-18A), never a detached ADU
    touching = box(35, 30, 45, 50, 0, 18, id="adu")
    m = _m(HOUSE, touching, **DETACHED)
    assert all(m[n]["reason"] == stop("adu_is_main") for n in ADU_MEASURES)
    assert m["side_yard_smaller"]["value"] == 5.0            # the house's yard is to the part touching it: 50 - 45
    m = _m(HOUSE, ADU, **{**DETACHED, "adu_building": "house"})
    assert all(m[n]["reason"] == stop("adu_is_main") for n in ADU_MEASURES)


def test_its_height_is_from_its_own_ground():
    """Spot grades: the house's walls at 0, the ADU's walls at -2 (lower ground). §325-3 GRADE PLANE: the ground at
    ITS walls, so the ADU (from -2 up to 16) is 16 - (-2) = 18 ft tall, never 16 ft from the house's ground."""
    adu = box(30, 70, 45, 90, -2, 16, id="adu")
    spots = [[22, 24, 0], [22, 56, 0], [9, 40, 0], [36, 40, 0],
             [37, 69, -2], [37, 91, -2], [29, 80, -2], [46, 80, -2]]
    m = _m(HOUSE, adu, **DETACHED, grade_points=spots, ground_is_flat=None, grade_elevation=None)
    # (the house alone, from its own walls' ground: 30 ft; read with every other solid as part of it, as any
    # building standing apart is, it has a reading of its own: unchanged by the pick)
    assert ("the main building only", 30.0) in [(r["reading"], r["value"]) for r in m["building_height"]["readings"]]
    assert m["adu_height"]["value"] == 18.0


def test_it_waits_for_the_ground_whenever_the_main_building_does():
    for facts, why in (({"ground_is_flat": None}, stop("ground_unknown")),
                       ({"ground_is_flat": False}, stop("sloped_ground"))):
        m = _m(HOUSE, ADU, **DETACHED, **facts)
        assert m["adu_height"]["reason"] == m["adu_stories"]["reason"] == why, facts
        assert m["adu_footprint"]["value"] == 300.0              # the plan doesn't need the ground's level
    m = _m(HOUSE, ADU, **DETACHED, grade_is="existing")
    assert m["adu_height"]["reason"] == m["adu_stories"]["reason"] == stop("existing_grade")
    assert (m["adu_height"]["measured_as_is"], m["adu_stories"]["measured_as_is"]) == (18.0, 2)


def test_flat_ground_assumed_decides_its_height_only_where_the_lookup_shows_the_lot_level():
    """The Rhino MVP assumes the ground flat (ground_assumed); the main building's height and stories then need
    review unless the looked-up ground falls under 0.5 ft (flat_assumption_unsafe), and so do the ADU's: else its
    20 ft and two-story limits would pass on ground never read. The flat reading (18 ft; at most floor(18 / 7) = 2
    stories) is kept to show, never to decide."""
    assumed = {**DETACHED, "ground_assumed": "flat"}
    for fall, why in ((14.2, stop("flat_sloped", fall="14.2")), (0.5, stop("flat_sloped", fall="0.5")),
                      (None, stop("flat_unknown"))):
        m = _m(HOUSE, ADU, **assumed, **({} if fall is None else {"ground_fall": fall}))
        for name, as_is in (("adu_height", 18.0), ("adu_stories", 2)):
            assert m[name]["value"] is None and m[name]["reason"] == why, (fall, name, m[name])
            assert m[name]["measured_as_is"] == as_is, (fall, name)
        assert m["building_height"]["reason"] == why                      # the main building's, the same
        assert m["adu_footprint"]["value"] == 300.0                       # the plan doesn't need the ground
    level = _m(HOUSE, ADU, **assumed, ground_fall=0.4)                    # shown level: flat decides
    assert _v(level, "adu_height", "adu_stories") == (18.0, 2)


def test_a_tall_plain_solid_asks_for_its_floors():
    m = _m(HOUSE, box(30, 70, 45, 90, 0, 22, id="adu"), **DETACHED)          # floor(22 / 7) = 3: could hold three
    assert m["adu_stories"]["value"] is None
    assert m["adu_stories"]["reason"] == stop("adu_stories_unclear", height="22", most="3")
    low = _m(HOUSE, box(30, 70, 45, 90, 0, 6, id="adu"), **DETACHED)       # every building has a first story
    assert low["adu_stories"]["value"] == 1


def test_a_roof_reaching_past_the_walls_reads_the_footprint_both_ways():
    """The walls 30..45 x 70..90 to 10 ft; a gable roof solid standing on them, 1 ft past the walls at each eave
    (30..45 x 69..91), ridge 16 ft. The footprint isn't defined: 15 x 22 = 330 sf eaves included, 15 x 20 = 300 sf
    left out."""
    walls = box(30, 70, 45, 90, 0, 10, id="adu")
    base = [(30, 69), (45, 69), (45, 91), (30, 91)]
    roof = {"id": "adu roof", "problems": [], "faces": [
        {"points": [[x, y, 10] for x, y in base]},
        {"points": [[30, 69, 10], [45, 69, 10], [45, 80, 16], [30, 80, 16]]},
        {"points": [[30, 91, 10], [45, 91, 10], [45, 80, 16], [30, 80, 16]]},
        {"points": [[30, 69, 10], [30, 80, 16], [30, 91, 10]]},
        {"points": [[45, 69, 10], [45, 80, 16], [45, 91, 10]]}]}
    m = _m(HOUSE, walls, roof, **DETACHED)
    f = m["adu_footprint"]
    assert f["value"] is None and sorted(r["value"] for r in f["readings"]) == [300.0, 330.0]
    assert "footprint" in f["reason"]
    assert m["adu_rear_yard"]["value"] == 9.0                # to the eave: 100 - 91, seen from above


def test_its_distances_wait_for_the_lot_lines_and_cross_or_leave_the_lot_by_name():
    m = _m(HOUSE, ADU, **DETACHED, corner_lot=None)
    assert all(m[n]["reason"] == stop("corner_unknown") for n in ("adu_front_yard", "adu_side_yard", "adu_rear_yard"))
    assert m["adu_footprint"]["value"] == 300.0
    off = _m(HOUSE, box(60, 70, 70, 90, 0, 18, id="adu"), **DETACHED)
    assert off["adu_side_yard"]["reason"] == stop("outside_lot", what="the ADU's building")
    across = _m(HOUSE, box(40, 70, 55, 90, 0, 18, id="adu"), **DETACHED)       # 5 ft over the east side line
    assert across["adu_side_yard"]["crossings"] == [{"who": "the ADU's building", "lines": ["side"]}]
    assert across["adu_footprint"]["crossings"] == across["adu_side_yard"]["crossings"]


def test_a_corner_lot_measures_the_front_to_the_nearer_street():
    facts = {**DETACHED, "corner_lot": True, "street_line": [[[0, 0], [50, 0]], [[50, 0], [50, 100]]],
             "street_ids": ["South St", "East St"], "address_street_line": [[[0, 0], [50, 0]]]}
    m = _m(HOUSE, ADU, **facts)
    assert m["adu_front_yard"]["value"] == 5.0              # 50 - 45 to East St (70 to South St)


def test_on_a_tax_map_lot_its_distances_carry_the_lot_lines_slack():
    assert all(TAX_MAP_SLACK[n] == 2.0 for n in ("adu_front_yard", "adu_side_yard", "adu_rear_yard"))


@pytest.mark.parametrize("facts, said", [
    ({"adu_building": 3}, "adu_building must be text"),
    ({"adu_detached": "yes"}, "adu_detached must be yes or no (true / false)"),
    ({"adu_existing_building": 1}, "adu_existing_building must be yes or no (true / false)"),
    ({"adus_on_parcel": 0}, "adus_on_parcel must be a whole number, 1 or more"),
    ({"adu_bedrooms": -1}, "adu_bedrooms must be a whole number, 0 or more"),
    ({"adu_bedrooms": 1.5}, "adu_bedrooms must be a whole number, 0 or more"),
    ({"adu_floor_area": -5}, "adu_floor_area must be a number of square feet, 0 or more"),
    ({"primary_floor_area": "900"}, "primary_floor_area must be a number of square feet, 0 or more"),
])
def test_bad_values_are_refused(facts, said):
    assert fact_problems(facts) == [said]


def test_stated_values_are_measured_as_stated_and_blanks_stop():
    got = _m(HOUSE, adu_detached=False, adus_on_parcel=1, adu_bedrooms=2, adu_floor_area=480.5,
             primary_floor_area=1500)
    assert _v(got, "adu_detached", "adus_on_parcel", "adu_bedrooms", "adu_floor_area", "primary_floor_area") == (
        False, 1, 2, 480.5, 1500)
    blank = _m(HOUSE)
    assert blank["adu_bedrooms"]["reason"] == stop("no_adu_bedrooms")
    assert blank["adus_on_parcel"]["reason"] == stop("no_adus_on_parcel")
    assert blank["adu_floor_area"]["reason"] == blank["primary_floor_area"]["reason"] == stop("no_adu_floor_area")
    assert blank["adu_detached"]["reason"] == blank["adu_existing_building"]["reason"] == stop("no_adu_kind")
    assert fact_problems({"adu_building": "x", "adu_detached": True, "adu_existing_building": False,
                          "adus_on_parcel": 1, "adu_bedrooms": 0, "adu_floor_area": 0, "primary_floor_area": 0}) == []



def test_in_the_primary_front_yard_when_nearer_the_street_than_the_main_building():
    """FRONT YARD (§325-3B): between the main building and the front lot line, its depth the least distance from the
    front lot line to the front of the main building: here 25 ft (the house's front wall at y = 25)."""
    assert _m(HOUSE, ADU, **DETACHED)["adu_in_primary_front_yard"]["value"] is False       # 70 ft back
    beside = box(38, 20, 48, 40, 0, 18, id="adu")          # 20 ft from the street: 5 ft nearer than the house
    assert _m(HOUSE, beside, **DETACHED)["adu_in_primary_front_yard"]["value"] is True
    level = box(38, 25, 48, 40, 0, 18, id="adu")           # level with the house's front: on the yard's edge only
    assert _m(HOUSE, level, **DETACHED)["adu_in_primary_front_yard"]["value"] is False


def test_a_corner_lot_reads_each_street_as_the_primary_one():
    """South St (y = 0) and East St (x = 50). The ADU 30..45 x 70..90: 70 ft from South St (house 25: no), 5 ft from
    East St (house 50 - 35 = 15: yes). Which is primary is open (325-28C#1): both readings, no value."""
    facts = {**DETACHED, "corner_lot": True, "street_line": [[[0, 0], [50, 0]], [[50, 0], [50, 100]]],
             "street_ids": ["South St", "East St"], "address_street_line": [[[0, 0], [50, 0]]]}
    got = _m(HOUSE, ADU, **facts)["adu_in_primary_front_yard"]
    assert got["value"] is None and sorted(r["value"] for r in got["readings"]) == [False, True]
    assert "325-28C#1" in got["reason"]
    away = box(2, 80, 12, 95, 0, 18, id="adu")              # 80 from South St, 38 from East St: no either way
    assert _m(HOUSE, away, **facts)["adu_in_primary_front_yard"]["value"] is False
    unnamed = _m(HOUSE, ADU, **{**facts, "street_ids": None})["adu_in_primary_front_yard"]
    assert unnamed["value"] is None and unnamed["reason"]


def test_a_corner_lot_whose_streets_cant_be_told_apart_waits(monkeypatch):
    """Never both streets read as one: the ADU 5 ft from East St, the house 25 ft from South St, would be "nearer the
    street than the house" (5 < 15) only by mixing the two. (The lot lines' own checks stop such a lot first; this
    holds even if they didn't.)"""
    import inspect

    import model_measurement.measure as measure_module
    real = measure_module._street_groups

    def unknown_here(*a):           # unknown only to this measurement: every other one still reads the streets
        return None if inspect.stack()[1].function == "_in_primary_front_yard" else real(*a)
    monkeypatch.setattr(measure_module, "_street_groups", unknown_here)
    facts = {**DETACHED, "corner_lot": True, "street_line": [[[0, 0], [50, 0]], [[50, 0], [50, 100]]],
             "street_ids": ["South St", "East St"], "address_street_line": [[[0, 0], [50, 0]]]}
    got = _m(HOUSE, ADU, **facts)["adu_in_primary_front_yard"]
    assert got["value"] is None and got["reason"] == stop("street_lines_split")     # the names given, not one run
    assert _m(HOUSE, ADU, **facts)["adu_side_yard"]["value"] == 30.0     # the rest as usual: x = 0 (East St is a street)


def test_in_the_front_yard_waits_for_the_main_building():
    off = box(60, 25, 80, 55, id="house")                  # the main building wholly off the lot
    got = _m(off, ADU, **DETACHED)["adu_in_primary_front_yard"]
    assert got["value"] is None and got["reason"] == stop("outside_lot", what="the main building")


def test_where_the_front_of_the_main_building_is_is_read_every_way():
    """The house's walls 10..35 x 25..55 to 10 ft; its gable roof 2 ft past the walls at each eave (y 23..57). An ADU
    whose front is at y = 24 is nearer the street than the walls (25) but not than the eave (23): the answer depends
    on where the front of the main building is, so both readings and the question are said."""
    walls = box(10, 25, 35, 55, 0, 10, id="house")
    base = [(10, 23), (35, 23), (35, 57), (10, 57)]
    roof = {"id": "house roof", "problems": [], "faces": [
        {"points": [[x, y, 10] for x, y in base]},
        {"points": [[10, 23, 10], [35, 23, 10], [35, 40, 16], [10, 40, 16]]},
        {"points": [[10, 57, 10], [35, 57, 10], [35, 40, 16], [10, 40, 16]]},
        {"points": [[10, 23, 10], [10, 40, 16], [10, 57, 10]]},
        {"points": [[35, 23, 10], [35, 40, 16], [35, 57, 10]]}]}
    adu = box(38, 24, 48, 40, 0, 18, id="adu")
    got = _m(walls, roof, adu, **DETACHED)["adu_in_primary_front_yard"]
    assert got["value"] is None and {r["value"] for r in got["readings"]} == {False, True}
    assert "front of the main building" in got["reason"]
