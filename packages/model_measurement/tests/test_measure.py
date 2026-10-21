"""Made-up lots with known answers: each measurement, and each case the law leaves unclear (never a guess)."""

import math

import pytest
from shapely.geometry import LineString, Polygon

from model_measurement.measure import measure

FACTS = {"street_line": [[[0, 0], [50, 0]]], "corner_lot": False, "lot_surveyed": True, "ground_is_flat": True,
         "grade_elevation": 0, "use": "one_family_detached", "stories": 2, "zone": "R-1b"}


def lot(points, curved=()):
    n = len(points)
    return {"id": "lot", "edges": [{"points": [list(points[i]), list(points[(i + 1) % n])], "curved": i in curved}
                                   for i in range(n)]}


def prism(outline, z0, z1, id="house"):
    """A solid: walls, floor and a flat roof over an outline."""
    n = len(outline)
    walls = [{"points": [[*outline[i], z0], [*outline[(i + 1) % n], z0], [*outline[(i + 1) % n], z1], [*outline[i], z1]]}
             for i in range(n)]
    return {"id": id, "faces": [{"points": [[x, y, z0] for x, y in outline]}, {"points": [[x, y, z1] for x, y in outline]},
                                *walls], "problems": []}


def box(x0, y0, x1, y1, z0=0, z1=30, id="house"):
    return prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, id)


RECT = lot([(0, 0), (50, 0), (50, 100), (0, 100)])          # street along y = 0


def site(lot_=RECT, *buildings, problems=()):
    return {"units": "ft", "lot": lot_, "buildings": list(buildings) or [box(10, 25, 35, 65)], "problems": list(problems)}


def values(m):
    return {k: v["value"] for k, v in m.items()}


def test_a_plain_rectangular_lot():
    m = measure(site(), FACTS)
    assert values(m) == {"use": "one_family_detached", "district": "R-1b", "lot_area": 5000.0, "lot_width": 50.0, "lot_depth": 100.0,
                         "building_area": 1000.0, "building_height": 30.0, "stories": 2, "front_yard": 25.0,
                         "side_yard_smaller": 10.0, "side_yard_larger": 15.0, "rear_yard": 35.0,
                         "sleeping_rooms": None, "parking_spaces": None}
    (ax, ay), (bx, by) = m["front_yard"]["points"]                              # the working: where it was measured
    assert ay == 0 and by == 25 and ax == bx and 10 <= ax <= 35
    assert m["sleeping_rooms"]["reason"] == m["parking_spaces"]["reason"] == "enter bedrooms / parking spaces"


def rotate(points, deg, about=(0, 0)):
    a = math.radians(deg)
    return [(about[0] + x * math.cos(a) - y * math.sin(a), about[1] + x * math.sin(a) + y * math.cos(a)) for x, y in points]


def test_a_tilted_lot_measures_the_same():
    corners = rotate([(0, 0), (50, 0), (50, 100), (0, 100)], 37)
    house = rotate([(10, 25), (35, 25), (35, 65), (10, 65)], 37)
    facts = {**FACTS, "street_line": [[list(corners[0]), list(corners[1])]]}
    m = measure(site(lot(corners), prism(house, 0, 30)), facts)
    for name, want in {"lot_area": 5000, "lot_width": 50, "lot_depth": 100, "building_area": 1000, "front_yard": 25,
                       "side_yard_smaller": 10, "side_yard_larger": 15, "rear_yard": 35}.items():
        assert m[name]["value"] == pytest.approx(want, abs=1e-6), name


def test_the_ground_level_is_where_height_starts():
    m = measure(site(RECT, box(10, 25, 35, 65, 2, 32)), {**FACTS, "grade_elevation": 2})
    assert m["building_height"]["value"] == 30.0


def test_a_curved_street_line_gives_two_readings_of_the_width():
    # a gently curved street (a 150 ft radius arc bulging 2.1 ft out: it turns 19 degrees in all)
    radius = 150
    sag = radius - math.sqrt(radius ** 2 - 25 ** 2)
    arc = [(x, -(math.sqrt(radius ** 2 - (x - 25) ** 2) - (radius - sag))) for x in range(0, 51)]
    edges = [{"points": [list(p) for p in arc], "curved": True},
             {"points": [[50, 0], [50, 100]]}, {"points": [[50, 100], [0, 100]]}, {"points": [[0, 100], [0, 0]]}]
    facts = {**FACTS, "street_line": [[[0, 0], [50, 0]]]}
    m = measure(site({"id": "lot", "edges": edges}), facts)
    assert m["lot_width"]["value"] is None and "curved street" in m["lot_width"]["reason"]
    assert [r["reading"] for r in m["lot_width"]["readings"]] == ["along the street line", "straight across, end to end (chord)"]
    # the street bulges away from the lot: the yard is the least distance from the curve to the house
    house = Polygon([(10, 25), (35, 25), (35, 65), (10, 65)])
    assert m["front_yard"]["value"] == round(LineString(arc).distance(house), 6)


def test_a_jog_gives_two_readings_of_the_side_lot_lines():
    # a 10 ft jog at the back left: is it a side lot line or part of the rear lot line?
    jog = lot([(0, 0), (50, 0), (50, 90), (8, 90), (0, 96)])
    m = measure(site(jog), FACTS)
    assert m["lot_depth"]["value"] is None
    assert sorted(r["value"] for r in m["lot_depth"]["readings"]) == [93.0, 98.0]
    assert "open question" in m["lot_depth"]["reason"]
    assert m["rear_yard"]["value"] == 25.0         # the nearest rear line is the same under both readings
    assert m["side_yard_smaller"]["value"] == 10.0


def test_a_corner_lot_leaves_side_and_rear_yards_for_the_architects():
    facts = {**FACTS, "corner_lot": True, "street_line": [[[0, 0], [50, 0]], [[50, 0], [50, 100]]]}
    m = measure(site(), facts)
    for name in ("lot_width", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "lot_depth"):
        assert m[name]["value"] is None and "corner lot" in m[name]["reason"]


def test_no_street_side_given():
    m = measure(site(), {**FACTS, "street_line": None})
    for name in ("lot_width", "lot_depth", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard"):
        assert m[name]["value"] is None and m[name]["reason"].startswith("the street side isn't given")
    assert m["lot_area"]["value"] == 5000 and m["building_height"]["value"] == 30


def test_a_street_line_that_isnt_a_lot_line():
    m = measure(site(), {**FACTS, "street_line": [[[0, 0], [40, 0]]]})
    assert m["front_yard"]["value"] is None and "doesn't match a lot line" in m["front_yard"]["reason"]


def test_a_building_outside_the_lot():
    m = measure(site(RECT, box(40, 25, 65, 65)), FACTS)
    for name in ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "building_area"):
        assert m[name]["value"] is None and m[name]["reason"] == "a building isn't inside the lot"
    assert m["building_height"]["value"] == 30


def test_two_buildings_need_the_main_one_picked():
    garage = box(30, 75, 48, 95, 0, 12, id="garage")
    m = measure(site(RECT, box(10, 25, 35, 65), garage), FACTS)
    assert m["building_area"]["value"] == 1000 + 360          # every building counts toward coverage
    for name in ("front_yard", "rear_yard", "building_height"):
        assert m[name]["value"] is None and m[name]["reason"] == "more than one building: pick the main building"
    picked = measure(site(RECT, box(10, 25, 35, 65), garage), {**FACTS, "main_building": "house"})
    assert picked["front_yard"]["value"] == 25          # the garage is farther from the street than the house
    # the garage is 5 ft from the rear line: a deck (part of the building) or an accessory building? Both read.
    assert picked["rear_yard"]["value"] is None
    assert sorted(r["value"] for r in picked["rear_yard"]["readings"]) == [5.0, 35.0, 35.0]
    # side yards are "between any building and the side lot line": the garage is 2 ft from the right side
    assert picked["side_yard_smaller"]["value"] is None
    assert sorted(r["value"] for r in picked["side_yard_smaller"]["readings"]) == [2.0, 10.0, 10.0]


def test_an_overhang_gives_two_readings_of_area_and_yards():
    # an upper floor sticking out 3 ft toward the street, from 10 ft up
    walls = box(10, 25, 35, 65, 0, 10)
    upper = box(10, 22, 35, 65, 10, 30, id="upper")
    house = {"id": "house", "faces": walls["faces"] + upper["faces"], "problems": []}
    m = measure(site(RECT, house), FACTS)
    assert m["building_area"]["value"] is None
    assert sorted(r["value"] for r in m["building_area"]["readings"]) == [1000.0, 1075.0]
    assert m["front_yard"]["value"] is None
    assert sorted(r["value"] for r in m["front_yard"]["readings"]) == [22.0, 25.0]
    assert m["rear_yard"]["value"] == 35.0                      # nothing sticks out at the back
    assert m["building_height"]["value"] == 30.0                # the underside of the upper floor isn't a roof


def test_a_pitched_roof_height_is_an_open_question():
    eave, ridge = 20, 30
    gable = [(10, 25, eave), (35, 25, eave), (35, 45, ridge), (10, 45, ridge)]   # one sloped half
    other = [(10, 45, ridge), (35, 45, ridge), (35, 65, eave), (10, 65, eave)]
    house = box(10, 25, 35, 65, 0, eave)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == eave for p in f["points"])]
    house["faces"] += [{"points": [list(p) for p in gable]}, {"points": [list(p) for p in other]}]
    m = measure(site(RECT, house), FACTS)
    assert m["building_height"]["value"] is None
    assert [r["value"] for r in m["building_height"]["readings"]] == [25.0, 30.0]
    assert "pitched roof" in m["building_height"]["reason"]


def test_no_ground_level():
    m = measure(site(), {**FACTS, "grade_elevation": None})
    for name in ("building_height", "building_area", "front_yard", "rear_yard"):
        assert m[name]["value"] is None and m[name]["reason"].startswith("the ground level isn't given")
    assert m["lot_depth"]["value"] == 100


def test_problems_reading_the_model_stop_every_lot_measurement():
    m = measure(site(problems=["2 closed outlines on the Site layer: pick the lot"]), FACTS)
    assert m["lot_area"]["value"] is None and m["lot_area"]["reason"] == "2 closed outlines on the Site layer: pick the lot"
    assert m["building_height"]["value"] == 30


def test_a_lot_that_isnt_closed_or_crosses_itself():
    open_lot = {"id": "lot", "edges": [{"points": [[0, 0], [50, 0]]}, {"points": [[50, 0], [50, 100]]},
                                       {"points": [[50, 100], [0, 100]]}]}
    assert "closed loop" in measure(site(open_lot), FACTS)["lot_area"]["reason"]
    bowtie = lot([(0, 0), (50, 100), (50, 0), (0, 100)])
    assert "crosses itself" in measure(site(bowtie), FACTS)["lot_area"]["reason"]


def test_a_building_with_a_problem_isnt_measured():
    bad = box(10, 25, 35, 65)
    bad["problems"] = ["a building has a curved surface (not measured yet)"]
    m = measure(site(RECT, bad), FACTS)
    assert m["building_height"]["value"] is None and m["front_yard"]["reason"] == "a building has a curved surface (not measured yet)"


def test_float_noise_never_moves_a_value_across_a_limit_by_more_than_a_millionth():
    nudged = box(10, 25.0000000001, 35, 65)
    assert measure(site(RECT, nudged), FACTS)["front_yard"]["value"] == 25.0


def rounded_corner_lot():
    """Streets along y = 0 and x = 50 meeting through a 10 ft radius curve, tangent to both."""
    arc = [(40 + 10 * math.sin(math.radians(a)), 10 - 10 * math.cos(math.radians(a))) for a in range(0, 91, 5)]
    edges = [{"points": [[0, 0], [40, 0]]}, {"points": [list(p) for p in arc], "curved": True},
             {"points": [[50, 10], [50, 100]]}, {"points": [[50, 100], [25, 100]]}, {"points": [[25, 100], [0, 100]]},
             {"points": [[0, 100], [0, 0]]}]
    street = [[[0, 0], [40, 0]], [list(arc[0]), list(arc[-1])], [[50, 10], [50, 100]]]
    return {"id": "lot", "edges": edges}, street


def test_a_corner_lot_with_a_rounded_corner_leaves_side_and_rear_yards_for_the_architects():
    corner, street = rounded_corner_lot()
    m = measure(site(corner), {**FACTS, "corner_lot": True, "street_line": street})
    for name in ("lot_width", "front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard", "lot_depth"):
        assert m[name]["value"] is None and "corner lot" in m[name]["reason"], name


def test_a_porch_or_deck_drawn_as_its_own_solid_counts_for_the_front_and_rear_yards():
    porch = box(15, 20, 30, 30, 0, 3, id="porch")       # 20 ft from the street; the house is 30 ft back
    deck = box(15, 65, 30, 85, 0, 3, id="deck")         # 15 ft from the rear line; the house is 35 ft
    m = measure(site(RECT, box(10, 30, 35, 65), porch, deck), {**FACTS, "main_building": "house"})
    assert m["front_yard"]["value"] is None and 20.0 in [r["value"] for r in m["front_yard"]["readings"]]
    assert m["rear_yard"]["value"] is None and 15.0 in [r["value"] for r in m["rear_yard"]["readings"]]
    assert "porch or deck" in m["front_yard"]["reason"]


def test_a_lot_with_every_line_on_a_street_gives_a_reason_not_a_crash():
    every = [[[0, 0], [50, 0]], [[50, 0], [50, 100]], [[50, 100], [0, 100]], [[0, 100], [0, 0]]]
    m = measure(site(), {**FACTS, "street_line": every})
    for name in ("lot_width", "front_yard", "rear_yard", "lot_depth"):
        assert m[name]["value"] is None and m[name]["reason"].startswith("every lot line is on a street")


def test_whether_it_is_a_corner_lot_is_stated_never_guessed():
    m = measure(site(), {**FACTS, "corner_lot": None})
    for name in ("lot_width", "front_yard", "side_yard_smaller", "rear_yard", "lot_depth"):
        assert m[name]["value"] is None and m[name]["reason"].startswith("say whether this is a corner lot"), name
    # two street lines that bend only a little, stated as one street: measured as one frontage
    bend = lot([(0, 0), (50, 0), (99, 10), (99, 110), (0, 100)])
    one = measure(site(bend, box(10, 25, 35, 65)), {**FACTS, "street_line": [[[0, 0], [50, 0]], [[50, 0], [99, 10]]]})
    assert one["lot_width"]["value"] == round(50 + math.hypot(49, 10), 6)


def test_a_corner_lot_with_only_one_street_given_measures_no_yard():
    # one street that bends 11.5 degrees is given; the second street (x = 99) isn't: nothing is measured to it
    bend = lot([(0, 0), (50, 0), (99, 10), (99, 110), (0, 100)])
    m = measure(site(bend, box(30, 40, 97, 80)), {**FACTS, "corner_lot": True,
                                                   "street_line": [[[0, 0], [50, 0]], [[50, 0], [99, 10]]]})
    for name in ("front_yard", "lot_width", "rear_yard"):
        assert m[name]["value"] is None and "corner lot" in m[name]["reason"], name


def test_a_taller_part_drawn_as_its_own_solid_counts_for_the_height():
    house, tower = box(10, 25, 35, 65, 0, 30), box(10, 65, 20, 70, 0, 45, id="tower")
    m = measure(site(RECT, house, tower), {**FACTS, "main_building": "house"})
    assert m["building_height"]["value"] is None
    assert sorted({r["value"] for r in m["building_height"]["readings"]}) == [30.0, 45.0]
    garage = box(30, 75, 48, 95, 0, 12, id="garage")             # a lower solid doesn't change the height
    assert measure(site(RECT, house, garage), {**FACTS, "main_building": "house"})["building_height"]["value"] == 30.0


def sloped_roof_box(x0, y0, x1, y1, low, high, id):
    """A box whose roof slopes from `low` (at y0) to `high` (at y1) in one plane."""
    base = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    top = {(x0, y0): low, (x1, y0): low, (x1, y1): high, (x0, y1): high}
    walls = [{"points": [[*base[i], 0], [*base[(i + 1) % 4], 0], [*base[(i + 1) % 4], top[base[(i + 1) % 4]]],
                         [*base[i], top[base[i]]]]} for i in range(4)]
    return {"id": id, "faces": [{"points": [[x, y, 0] for x, y in base]},
                                {"points": [[x, y, top[(x, y)]] for x, y in base]}, *walls], "problems": []}


def test_a_roof_with_a_drainage_slope_is_flat_and_measured_to_its_highest_point():
    m = measure(site(RECT, sloped_roof_box(10, 25, 35, 65, 29.8, 30, "house")), FACTS)   # 1/4 inch per foot
    assert m["building_height"]["value"] == 30.0


def test_another_solid_whose_height_cant_be_read_is_never_dropped():
    house = box(10, 25, 35, 65, 0, 30)
    flat_slab = {"id": "slab", "faces": [{"points": [[30, 75, 0], [45, 75, 0], [45, 90, 0]]}], "problems": []}
    m = measure(site(RECT, house, flat_slab), {**FACTS, "main_building": "house"})
    assert m["building_height"]["value"] is None and m["building_height"]["reason"].startswith("another solid's height")
    wing = sloped_roof_box(10, 65, 20, 75, 44.8, 45, "wing")            # a 45 ft wing with a drainage slope
    m = measure(site(RECT, house, wing), {**FACTS, "main_building": "house"})
    assert m["building_height"]["value"] is None
    assert sorted({r["value"] for r in m["building_height"]["readings"]}) == [30.0, 45.0]


def test_a_mansard_is_for_the_architects_and_a_flat_roof_over_a_lower_pitched_wing_is_flat():
    # a mansard: walls to 20 ft, sides sloping in 2 ft up to a level deck at 30 ft ("the highest level of a ...
    # mansard roof")
    low = [(10, 25), (35, 25), (35, 65), (10, 65)]
    deck = [(12, 27), (33, 27), (33, 63), (12, 63)]
    walls = [{"points": [[*low[i], 0], [*low[(i + 1) % 4], 0], [*low[(i + 1) % 4], 20], [*low[i], 20]]} for i in range(4)]
    sides = [{"points": [[*low[i], 20], [*low[(i + 1) % 4], 20], [*deck[(i + 1) % 4], 30], [*deck[i], 30]]} for i in range(4)]
    mansard = {"id": "house", "problems": [], "faces": [{"points": [[x, y, 0] for x, y in low]},
                                                         {"points": [[x, y, 30] for x, y in deck]}, *walls, *sides]}
    m = measure(site(RECT, mansard), FACTS)["building_height"]
    # a level deck and sloped sides at the top: a mansard (to its highest level, 30) or a hip roof with a deck
    # (to its average height, 25)? The architects decide; every reading is listed, and both questions named
    assert m["value"] is None and "mansard" in m["reason"] and "average height of a pitched roof" in m["reason"]
    assert sorted(r["value"] for r in m["readings"]) == [25.0, 30.0, 30.0]
    # a flat 30 ft house with a lower gable (eave 8, ridge 14) in the same solid: the highest section is flat
    house = box(10, 25, 35, 65, 0, 30)
    gable = [{"points": [[35, 30, 8], [45, 30, 8], [45, 40, 14], [35, 40, 14]]},
             {"points": [[35, 40, 14], [45, 40, 14], [45, 50, 8], [35, 50, 8]]}]
    house["faces"] += gable
    assert measure(site(RECT, house), FACTS)["building_height"]["value"] == 30.0


def test_a_pitched_house_with_a_low_garage_names_the_roof_question_once():
    eave, ridge = 20, 30
    house = box(10, 25, 35, 65, 0, eave)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == eave for p in f["points"])]
    house["faces"] += [{"points": [[10, 25, eave], [35, 25, eave], [35, 45, ridge], [10, 45, ridge]]},
                       {"points": [[10, 45, ridge], [35, 45, ridge], [35, 65, eave], [10, 65, eave]]}]
    garage = box(30, 75, 48, 95, 0, 12, id="garage")
    reason = measure(site(RECT, house, garage), {**FACTS, "main_building": "house"})["building_height"]["reason"]
    assert reason.count("the readings give different values") == 1
    assert "pitched roof" in reason and "§325-25" not in reason    # the 12 ft garage changes no reading


def test_a_gable_with_a_level_ridge_strip_is_not_decided_as_flat():
    eave, ridge = 20, 30
    house = box(10, 25, 35, 65, 0, eave)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == eave for p in f["points"])]
    house["faces"] += [{"points": [[10, 25, eave], [35, 25, eave], [35, 44.75, ridge], [10, 44.75, ridge]]},
                       {"points": [[10, 44.75, ridge], [35, 44.75, ridge], [35, 45.25, ridge], [10, 45.25, ridge]]},
                       {"points": [[10, 45.25, ridge], [35, 45.25, ridge], [35, 65, eave], [10, 65, eave]]}]
    m = measure(site(RECT, house), FACTS)["building_height"]
    assert m["value"] is None and 25.0 in [r["value"] for r in m["readings"]]


def test_the_height_reason_names_only_the_questions_that_change_it():
    flat = box(10, 25, 35, 65, 0, 30)
    pitched_garage = box(36, 70, 48, 95, 0, 20, id="garage")
    pitched_garage["faces"] = [f for f in pitched_garage["faces"] if not all(p[2] == 20 for p in f["points"])]
    pitched_garage["faces"] += [{"points": [[36, 70, 20], [48, 70, 20], [48, 82.5, 40], [36, 82.5, 40]]},
                                {"points": [[36, 82.5, 40], [48, 82.5, 40], [48, 95, 20], [36, 95, 20]]}]
    m = measure(site(RECT, flat, pitched_garage), {**FACTS, "main_building": "house"})["building_height"]
    assert "pitched roof" in m["reason"] and "§325-25" in m["reason"]     # both change the number (30 or 40)
    low_garage = box(30, 75, 48, 95, 0, 12, id="garage")
    m = measure(site(RECT, flat, low_garage), {**FACTS, "main_building": "house"})["building_height"]
    assert m["value"] == 30.0                                             # the garage changes nothing


def test_a_low_shed_with_its_own_roof_question_changes_nothing_and_isnt_asked_about():
    eave, ridge = 20, 30
    house = box(10, 25, 35, 65, 0, eave)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == eave for p in f["points"])]
    house["faces"] += [{"points": [[10, 25, eave], [35, 25, eave], [35, 45, ridge], [10, 45, ridge]]},
                       {"points": [[10, 45, ridge], [35, 45, ridge], [35, 65, eave], [10, 65, eave]]}]
    shed = box(36, 75, 48, 95, 0, 8, id="shed")                      # walls 8, a mansard-like top at 12
    shed["faces"] = [f for f in shed["faces"] if not all(p[2] == 8 for p in f["points"])]
    deck = [(38, 77), (46, 77), (46, 93), (38, 93)]
    low = [(36, 75), (48, 75), (48, 95), (36, 95)]
    shed["faces"] += [{"points": [[x, y, 12] for x, y in deck]}]
    shed["faces"] += [{"points": [[*low[i], 8], [*low[(i + 1) % 4], 8], [*deck[(i + 1) % 4], 12], [*deck[i], 12]]}
                      for i in range(4)]
    m = measure(site(RECT, house, shed), {**FACTS, "main_building": "house"})["building_height"]
    assert "pitched roof" in m["reason"] and "mansard" not in m["reason"] and "§325-25" not in m["reason"]


def test_a_flat_other_solid_gives_no_duplicate_roof_readings():
    m = measure(site(RECT, box(10, 25, 35, 65, 0, 30), box(10, 65, 20, 70, 0, 45, id="tower")),
                {**FACTS, "main_building": "house"})["building_height"]
    assert [r["value"] for r in m["readings"]] == [30.0, 45.0]
    assert not any("read low" in r["reading"] for r in m["readings"])


def test_only_the_questions_of_solids_that_can_change_the_height_are_named():
    house = box(10, 25, 35, 65, 0, 10)
    shed = box(36, 75, 48, 95, 0, 8, id="shed")                      # a mansard-like top at 12: never the tallest
    shed["faces"] = [f for f in shed["faces"] if not all(p[2] == 8 for p in f["points"])]
    deck, low = [(38, 77), (46, 77), (46, 93), (38, 93)], [(36, 75), (48, 75), (48, 95), (36, 95)]
    shed["faces"] += [{"points": [[x, y, 12] for x, y in deck]}]
    shed["faces"] += [{"points": [[*low[i], 8], [*low[(i + 1) % 4], 8], [*deck[(i + 1) % 4], 12], [*deck[i], 12]]}
                      for i in range(4)]
    tower = box(10, 66, 20, 72, 0, 30, id="tower")                   # a gable tower: eave 30, ridge 40
    tower["faces"] = [f for f in tower["faces"] if not all(p[2] == 30 for p in f["points"])]
    tower["faces"] += [{"points": [[10, 66, 30], [20, 66, 30], [20, 69, 40], [10, 69, 40]]},
                       {"points": [[10, 69, 40], [20, 69, 40], [20, 72, 30], [10, 72, 30]]}]
    m = measure(site(RECT, house, shed, tower), {**FACTS, "main_building": "house"})["building_height"]
    assert m["value"] is None and "average height of a pitched roof" in m["reason"]
    assert "mansard" not in m["reason"]


def test_something_above_the_main_roof_is_for_the_architects():
    house = box(10, 25, 35, 65, 0, 30)
    chimney = box(12, 27, 15, 30, 30, 34)
    house["faces"] = [f for f in house["faces"] if not (all(p[2] == 30 for p in f["points"]))] + [
        {"points": [[10, 25, 30], [35, 25, 30], [35, 65, 30], [10, 65, 30]]}] + [
        f for f in chimney["faces"] if not all(p[2] == 30 for p in f["points"])]
    m = measure(site(RECT, house), FACTS)["building_height"]
    assert m["value"] is None and "rises above the main roof" in m["reason"]
    assert sorted(r["value"] for r in m["readings"]) == [30.0, 34.0]
    # with a low garage too, the question isn't lost
    garage = box(30, 75, 48, 95, 0, 12, id="garage")
    m = measure(site(RECT, house, garage), {**FACTS, "main_building": "house"})["building_height"]
    assert m["value"] is None and "rises above the main roof" in m["reason"]


def test_a_lot_not_from_a_survey_and_sloped_ground_need_review():
    m = measure(site(), {**FACTS, "lot_surveyed": False})
    assert m["lot_area"]["value"] is None and "survey" in m["lot_area"]["reason"]
    assert m["lot_area"]["readings"][0]["value"] == 5000.0
    m = measure(site(), {**FACTS, "ground_is_flat": False})
    for name in ("building_height", "building_area", "front_yard"):
        assert m[name]["value"] is None and m[name]["reason"].startswith("sloped ground"), name
    m = measure(site(), {**FACTS, "ground_is_flat": None, "lot_surveyed": None})
    assert m["building_height"]["reason"] == "say whether the ground is flat"
    assert m["lot_area"]["reason"] == "say whether the lot outline is from a survey"


def test_a_pitched_house_with_a_chimney_is_read_as_pitched_without_it():
    eave, ridge = 20, 30
    house = box(10, 25, 35, 65, 0, eave)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == eave for p in f["points"])]
    house["faces"] += [{"points": [[10, 25, eave], [35, 25, eave], [35, 45, ridge], [10, 45, ridge]]},
                       {"points": [[10, 45, ridge], [35, 45, ridge], [35, 65, eave], [10, 65, eave]]}]
    chimney = box(20, 44, 23, 47, ridge, 34, id="c")
    house["faces"] += [f for f in chimney["faces"] if not all(p[2] == ridge for p in f["points"])]
    m = measure(site(RECT, house), FACTS)["building_height"]
    assert m["value"] is None and {25.0, 30.0, 34.0} <= {r["value"] for r in m["readings"]}
    assert "average height of a pitched roof" in m["reason"] and "rises above the main roof" in m["reason"]


def test_a_soffit_is_never_a_roof():
    # a 29 ft box with a 30 ft roof slab overhanging 2 ft all round: the height is simply 30
    walls = box(10, 25, 35, 65, 0, 29)
    slab = box(8, 23, 37, 67, 29, 30, id="slab")
    house = {"id": "house", "problems": [], "faces": [f for f in walls["faces"] if not all(p[2] == 29 for p in f["points"])]
             + [f for f in slab["faces"] if not all(p[2] == 29 for p in f["points"])]
             + [{"points": [[8, 23, 29], [37, 23, 29], [37, 67, 29], [8, 67, 29]],
                 "holes": [[[10, 25, 29], [35, 25, 29], [35, 65, 29], [10, 65, 29]]]}]}
    m = measure(site(RECT, house), FACTS)["building_height"]
    assert m["value"] == 30.0 and m["reason"] is None and "flat roof" in m["how"]


def test_a_higher_pitched_part_is_read_as_pitched_too():
    eave, ridge = 20, 30
    house = box(10, 25, 35, 65, 0, eave)
    house["faces"] = [f for f in house["faces"] if not all(p[2] == eave for p in f["points"])]
    house["faces"] += [{"points": [[10, 25, eave], [35, 25, eave], [35, 45, ridge], [10, 45, ridge]]},
                       {"points": [[10, 45, ridge], [35, 45, ridge], [35, 65, eave], [10, 65, eave]]}]
    tower = box(12, 40, 18, 50, ridge, 30)                          # a small gable part, eave 30 ridge 40
    house["faces"] += [{"points": [[12, 40, 30], [18, 40, 30], [18, 45, 40], [12, 45, 40]]},
                       {"points": [[12, 45, 40], [18, 45, 40], [18, 50, 30], [12, 50, 30]]}]
    m = measure(site(RECT, house), FACTS)["building_height"]
    assert {25.0, 30.0, 35.0, 40.0} <= {r["value"] for r in m["readings"]}


def test_a_hip_roof_over_a_soffit_drawn_as_one_face_is_read_as_pitched():
    # walls 30 x 30 to 20 ft; a hip roof from a 36 x 36 eave at 20 ft up to a point at 30 ft; the soffit under
    # the overhang drawn as one level 36 x 36 face at 20 ft (larger than any roof slope, but covered by them)
    walls = box(10, 25, 40, 55, 0, 20)
    faces = [f for f in walls["faces"] if not all(p[2] == 20 for p in f["points"])]
    eave = [(7, 22), (43, 22), (43, 58), (7, 58)]
    apex = [25, 40, 30]
    faces += [{"points": [[*eave[i], 20], [*eave[(i + 1) % 4], 20], apex]} for i in range(4)]
    faces += [{"points": [[x, y, 20] for x, y in eave]}]
    m = measure(site(RECT, {"id": "house", "faces": faces, "problems": []}), FACTS)["building_height"]
    assert sorted({r["value"] for r in m["readings"]}) == [25.0, 30.0]
    assert "pitched roof" in m["reason"] and "rises above" not in m["reason"]


def test_a_chimney_through_a_hole_in_the_roof_is_still_above_the_roof():
    walls = box(10, 25, 40, 55, 0, 30)
    faces = [f for f in walls["faces"] if not all(p[2] == 30 for p in f["points"])]
    faces += [{"points": [[10, 25, 30], [40, 25, 30], [40, 55, 30], [10, 55, 30]],
               "holes": [[[24, 39, 30], [26, 39, 30], [26, 41, 30], [24, 41, 30]]]}]
    chimney = box(24, 39, 26, 41, 30, 36, id="c")
    faces += [f for f in chimney["faces"] if not all(p[2] == 30 for p in f["points"])]
    m = measure(site(RECT, {"id": "house", "faces": faces, "problems": []}), FACTS)["building_height"]
    assert m["value"] is None and "rises above the main roof" in m["reason"]
    assert {r["value"] for r in m["readings"]} == {30.0, 36.0}


def test_where_the_model_sits_up_or_down_changes_nothing():
    eave = [(7, 22), (43, 22), (43, 58), (7, 58)]
    for shift in (0.0, -30.0, 7.0):                   # the apex at 30, at 0, at 37
        walls = box(10, 25, 40, 55, 0, 20)
        faces = [{"points": [[x, y, z + shift] for x, y, z in f["points"]]} for f in walls["faces"]
                 if not all(p[2] == 20 for p in f["points"])]
        apex = [25, 40, 30 + shift]
        faces += [{"points": [[*eave[i], 20 + shift], [*eave[(i + 1) % 4], 20 + shift], apex]} for i in range(4)]
        faces += [{"points": [[x, y, 20 + shift] for x, y in eave]}]
        m = measure(site(RECT, {"id": "house", "faces": faces, "problems": []}),
                    {**FACTS, "grade_elevation": shift})["building_height"]
        assert sorted({r["value"] for r in m["readings"]}) == [25.0, 30.0], shift


def test_a_thin_roof_ring_around_a_tall_part_is_open_to_the_sky():
    # a 1 ft roof ring at 30 ft around a 40 x 40 hole with a 50 ft part standing in it: every grid point of the
    # ring's bounds lies in the hole, under the tall part; only the ring itself (holes kept) is open
    from model_measurement.measure import _open_to_the_sky
    ring = {"points": [[0, 0, 30], [42, 0, 30], [42, 42, 30], [0, 42, 30]],
            "holes": [[[1, 1, 30], [41, 1, 30], [41, 41, 30], [1, 41, 30]]]}
    tall = {"points": [[1, 1, 50], [41, 1, 50], [41, 41, 50], [1, 41, 50]]}
    assert ring in _open_to_the_sky([ring, tall])


def test_a_lower_roof_partly_under_an_overhang_is_open_to_the_sky():
    # a 20 x 40 lower roof at 10 ft whose middle is under an upper slab at 20 ft (not touching, no hole): the
    # middle point is covered, the rest of the roof isn't
    from model_measurement.measure import _open_to_the_sky
    low = {"points": [[0, 0, 10], [20, 0, 10], [20, 40, 10], [0, 40, 10]]}
    slab = {"points": [[-5, 15, 20], [25, 15, 20], [25, 25, 20], [-5, 25, 20]]}
    assert low in _open_to_the_sky([low, slab])


def _meshed_house(n):
    """A 25 x 40 ft, 30 ft high house whose top and bottom are each an n x n grid of triangles (as imported)."""
    faces = []
    for z in (0.0, 30.0):
        for i in range(n):
            for j in range(n):
                x0, y0, x1, y1 = 10 + i * 25 / n, 25 + j * 40 / n, 10 + (i + 1) * 25 / n, 25 + (j + 1) * 40 / n
                faces += [{"points": [[x0, y0, z], [x1, y0, z], [x1, y1, z]]},
                          {"points": [[x0, y0, z], [x1, y1, z], [x0, y1, z]]}]
    walls = box(10, 25, 35, 65, 0, 30)["faces"]
    faces += [f for f in walls if not all(p[2] in (0, 30) for p in f["points"])]
    return site(RECT, {"id": "house", "faces": faces, "problems": []})


def test_a_meshed_building_is_measured_quickly():
    """Measuring time grows about in step with a mesh's faces, never with their square (an imported house has
    thousands of faces: a step that compares every face with every other would take minutes). Timed against the
    same work on a mesh a quarter the size, in the same run and around it, so a slow or busy machine doesn't
    matter: four times the faces must take under 8 times as long (in step: about 4; every face against every
    other: about 16). 60 s is only a ceiling for a hang. (A fixed 10 s limit failed on a slow Windows runner.)"""
    import time

    def clock(n):
        start = time.perf_counter()
        m = measure(_meshed_house(n), FACTS)
        took = time.perf_counter() - start
        assert m["building_height"]["value"] == 30.0
        return took

    clock(10)                                               # warm up (imports, first-call caches)
    before = clock(10)
    big = clock(20)
    small = (before + clock(10)) / 2                        # around the big one: the same machine load
    assert big < 8 * small, f"4x the faces took {big / small:.1f}x as long ({small:.2f}s -> {big:.2f}s)"
    assert big < 60


def meshed_box_top(n, z, x0=10, y0=25, x1=35, y1=65):
    faces = []
    for i in range(n):
        for j in range(n):
            a, b = x0 + i * (x1 - x0) / n, y0 + j * (y1 - y0) / n
            c, d = x0 + (i + 1) * (x1 - x0) / n, y0 + (j + 1) * (y1 - y0) / n
            faces += [{"points": [[a, b, z], [c, b, z], [c, d, z]]}, {"points": [[a, b, z], [c, d, z], [a, d, z]]}]
    return faces


def test_a_meshed_roof_with_a_chimney_still_asks_about_the_chimney():
    walls = box(10, 25, 35, 65, 0, 30)["faces"]
    faces = [f for f in walls if not all(p[2] == 30 for p in f["points"])] + meshed_box_top(30, 30)
    chimney = box(20, 40, 23, 43, 30, 35, id="c")
    faces += [f for f in chimney["faces"] if not all(p[2] == 30 for p in f["points"])]
    m = measure(site(RECT, {"id": "house", "faces": faces, "problems": []}), FACTS)["building_height"]
    assert m["value"] is None and "rises above the main roof" in m["reason"]
    assert sorted({r["value"] for r in m["readings"]}) == [30.0, 35.0]


def test_a_meshed_gable_is_read_like_a_whole_one():
    eave, ridge, n = 20, 30, 4
    walls = box(10, 25, 35, 65, 0, eave)["faces"]
    faces = [f for f in walls if not all(p[2] == eave for p in f["points"])]
    for (ya, za), (yb, zb) in (((25, eave), (45, ridge)), ((45, ridge), (65, eave))):
        for i in range(n):
            for j in range(n):
                xa, xb = 10 + i * 25 / n, 10 + (i + 1) * 25 / n
                y1, y2 = ya + j * (yb - ya) / n, ya + (j + 1) * (yb - ya) / n
                z1, z2 = za + j * (zb - za) / n, za + (j + 1) * (zb - za) / n
                faces += [{"points": [[xa, y1, z1], [xb, y1, z1], [xb, y2, z2]]},
                          {"points": [[xa, y1, z1], [xb, y2, z2], [xa, y2, z2]]}]
    m = measure(site(RECT, {"id": "house", "faces": faces, "problems": []}), FACTS)["building_height"]
    assert sorted({r["value"] for r in m["readings"]}) == [25.0, 30.0]


def test_a_gently_curved_roof_is_not_one_plane():
    # a 20 ft wide roof curving with a 2000 ft radius (0.025 ft off flat across it), in 40 strips: never one plane,
    # and no group's corners stray beyond 0.01 ft of the plane fitted over that group, whatever order the faces
    # come in (a plane is fitted over its whole group, so one triangle's rounding noise can't tilt it)
    import numpy as np
    from model_measurement.measure import TOL, _planes
    radius, faces = 2000.0, []
    xs = [i * 20 / 40 for i in range(41)]
    z = [math.sqrt(radius ** 2 - (x - 10) ** 2) - radius + 30 for x in xs]
    for i in range(40):
        faces.append({"points": [[xs[i], 0, z[i]], [xs[i + 1], 0, z[i + 1]], [xs[i + 1], 20, z[i + 1]]]})
        faces.append({"points": [[xs[i], 0, z[i]], [xs[i + 1], 20, z[i + 1]], [xs[i], 20, z[i]]]})
    for order in (faces, faces[::-1]):
        groups = _planes(order)
        assert len(groups) > 1
        for group in groups:
            pts = np.array([q for f in group for q in f["points"]], dtype=float)
            c = pts.mean(0)
            n = np.linalg.eigh((pts - c).T @ (pts - c))[1][:, 0]
            assert np.abs((pts - c) @ n).max() <= TOL


def test_a_ground_level_that_doesnt_meet_the_building_stops_height_area_and_yards():
    for grade in (812, 30, 31, -50):          # above the top, at it, just over it, under the lowest point
        m = measure(site(), {**FACTS, "grade_elevation": grade})
        for name in ("building_height", "building_area", "front_yard", "side_yard_smaller", "rear_yard"):
            assert m[name]["value"] is None and "doesn't meet the buildings" in m[name]["reason"], (grade, name)
    basement = measure(site(), {**FACTS, "grade_elevation": 4})      # a basement 4 ft below the ground
    assert basement["building_height"]["value"] == 26.0 and basement["front_yard"]["value"] == 25.0


def test_stacked_solids_and_a_basement_drawn_as_its_own_solid_meet_the_ground():
    ground_floor, upper = box(10, 25, 35, 65, 0, 10, id="house"), box(10, 25, 35, 65, 10, 30, id="upper")
    m = measure(site(RECT, ground_floor, upper), {**FACTS, "main_building": "house"})
    assert (m["building_area"]["value"], m["front_yard"]["value"], m["rear_yard"]["value"]) == (1000.0, 25.0, 35.0)
    assert "doesn't meet" not in str(m["building_height"]["reason"])
    house, basement = box(10, 25, 35, 65, 10, 40, id="house"), box(10, 25, 35, 65, 0, 10, id="basement")
    m = measure(site(RECT, house, basement), {**FACTS, "main_building": "house", "grade_elevation": 10})
    assert m["front_yard"]["value"] == 25.0 and "doesn't meet" not in str(m["building_height"]["reason"])


def test_a_solid_buried_beside_the_building_is_never_dropped():
    house, tower = box(10, 25, 25, 65, 812, 842, id="house"), box(26, 25, 35, 65, 0, 45, id="tower")
    m = measure(site(RECT, house, tower), {**FACTS, "main_building": "house", "grade_elevation": 812})
    assert m["building_height"]["value"] is None and "wholly under the ground" in m["building_height"]["reason"]
    garage = box(32, 70, 45, 90, 0, 10, id="garage")                   # buried by a ground level of 20
    m = measure(site(RECT, box(10, 25, 30, 65, 0, 30), garage), {**FACTS, "main_building": "house", "grade_elevation": 20})
    assert m["building_height"]["value"] is None and "wholly under the ground" in m["building_height"]["reason"]


def test_a_solid_under_the_house_but_not_joined_to_it_is_never_dropped():
    facts = {**FACTS, "main_building": "house", "grade_elevation": 812}
    house = box(10, 25, 35, 65, 812, 842, id="house")
    for left_behind in (box(20, 40, 25, 50, 0, 45, id="tower"), box(20, 40, 25, 50, 30, 34, id="bulkhead")):
        m = measure(site(RECT, house, left_behind), facts)
        assert m["building_height"]["value"] is None and "wholly under the ground" in m["building_height"]["reason"]
    basement, sub = box(10, 25, 35, 65, 802, 812, id="basement"), box(15, 30, 30, 60, 792, 802, id="sub-basement")
    m = measure(site(RECT, house, basement, sub), facts)
    assert m["building_height"]["value"] == 30.0 and m["front_yard"]["value"] == 25.0


def test_two_building_objects_with_one_id_are_never_measured_as_one():
    """Stress test F4: two floor blocks sharing an id; one was dropped from the story count while the height
    still counted it. Nothing is ever dropped silently: every building measurement needs review, saying why."""
    m = measure(site(RECT, box(10, 25, 35, 65, 0, 10), box(10, 25, 35, 65, 10, 20)), FACTS)
    for name in ("building_height", "building_area", "front_yard", "rear_yard"):
        assert m[name]["value"] is None and "share the id house" in (m[name]["reason"] or ""), name
    ok = measure(site(RECT, box(10, 25, 35, 65, 0, 10, id="f1"), box(10, 25, 35, 65, 10, 20, id="f2")), FACTS)
    assert "share the id" not in str(ok)


def _planar_roof(n):
    faces = []
    for i in range(n):
        for j in range(n):
            x0, x1, y0, y1 = i * 0.5, (i + 1) * 0.5, j * 0.5, (j + 1) * 0.5
            faces += [{"points": [[x0, y0, 30 + 0.5 * x0], [x1, y0, 30 + 0.5 * x1], [x1, y1, 30 + 0.5 * x1]]},
                      {"points": [[x0, y0, 30 + 0.5 * x0], [x1, y1, 30 + 0.5 * x1], [x0, y1, 30 + 0.5 * x0]]}]
    return faces


def test_plane_grouping_grows_about_in_step_with_the_faces():
    """Review round 3 of the mesh fix: refitting every corner at every join made grouping quadratic (a 28,800-
    triangle roof took 55 s). A joined plane is now one 3 x 3 fit from the groups' moments: four times the faces
    take under 10 times as long (quadratic: about 16), measured in the same run, and the roof is one plane."""
    import time
    from model_measurement.measure import _planes

    def clock(n):
        faces = _planar_roof(n)
        start = time.perf_counter()
        groups = _planes(faces)
        took = time.perf_counter() - start
        assert len(groups) == 1
        return took

    clock(20)
    small = clock(40)
    big = clock(80)
    small = (small + clock(40)) / 2
    assert big < 10 * small, f"4x the faces took {big / small:.1f}x as long"
    assert big < 60
