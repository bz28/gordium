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
        assert m[name]["value"] is None and m[name]["reason"].startswith("a building isn't inside the lot: ")
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


def test_no_ground_level_stops_the_height_but_not_the_plan():
    """The grade decides height and stories (spec C3); yards and building area are measured where the building
    meets the ground, its own base, so they still are."""
    m = measure(site(), {**FACTS, "grade_elevation": None})
    assert m["building_height"]["value"] is None and m["building_height"]["reason"].startswith("the ground level isn't given")
    for name in ("building_area", "front_yard", "rear_yard"):
        assert m[name]["value"] is not None, name
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
    assert m["building_height"]["value"] is None and m["building_height"]["reason"].startswith("sloped ground")
    for name in ("building_area", "front_yard"):            # the plan: at the building's base
        assert m[name]["value"] is not None, name
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


# ---- stories from the shape: stacked floor blocks ----------------------------------------------------------

def floor(x0, y0, x1, y1, z0=0, z1=30, id="house", drawn=None):
    """A floor block GordiumStart drew: marked as one story, at the height it was drawn (`drawn`, if it has been
    stretched since)."""
    return {**box(x0, y0, x1, y1, z0=z0, z1=z1, id=id), "floor": z1 - z0 if drawn is None else drawn}


FLOORS = [floor(10, 25, 35, 65, z0=0, z1=11, id="floor 1"), floor(10, 25, 35, 65, z0=11, z1=22, id="floor 2"),
          floor(10, 25, 35, 65, z0=22, z1=33, id="floor 3")]


def test_stacked_floor_blocks_are_one_building_and_its_stories_are_counted():
    m = measure(site(RECT, *FLOORS), {**FACTS, "stories": None})
    assert m["stories"]["value"] == 3 and m["stories"]["objects"] == ["floor 1", "floor 2", "floor 3"]
    assert m["building_height"]["value"] == 33          # one building, to its roof: not "pick the main building"
    assert m["front_yard"]["value"] == 25
    assert set(m["front_yard"]["objects"]) == {"lot", "floor 1", "floor 2", "floor 3"}
    assert m["building_area"]["value"] == 25 * 40


def test_a_typed_count_that_disagrees_with_the_floors_drawn_is_a_question():
    m = measure(site(RECT, *FLOORS), {**FACTS, "stories": 2})["stories"]
    assert m["value"] is None and sorted(r["value"] for r in m["readings"]) == [2, 3]
    assert measure(site(RECT, *FLOORS), {**FACTS, "stories": 3})["stories"]["value"] == 3


def test_stacked_blocks_that_arent_gordiums_floors_never_override_the_typed_count():
    """A podium and an upper block, 17 ft each, holding 4 real floors: never "2 stories" (a false pass). Stories are
    counted only from floor blocks, never from plain solids: the count typed stands for the whole building, and
    with none typed it is asked for, saying no floor blocks are drawn."""
    podium = [box(10, 25, 35, 65, z0=0, z1=17, id="podium"), box(10, 25, 35, 65, z0=17, z1=34, id="upper")]
    m = measure(site(RECT, *podium), {**FACTS, "stories": 4})["stories"]
    assert m["value"] == 4 and 2 not in {r["value"] for r in m["readings"]}
    assert measure(site(RECT, *podium), {**FACTS, "stories": None})["stories"]["reason"].startswith(
        "no floor blocks are drawn")


def test_one_gordium_floor_block_is_one_story():
    assert measure(site(RECT, floor(10, 25, 35, 65, z0=0, z1=12, id="floor 1")), {**FACTS, "stories": None})[
        "stories"]["value"] == 1


def test_one_solid_without_floors_asks_for_floors_or_a_count():
    m = measure(site(RECT, box(10, 25, 35, 65)), {**FACTS, "stories": None})
    assert m["stories"]["value"] is None and "draw each story as its own solid" in m["stories"]["reason"]


def test_a_smaller_block_on_top_is_a_question_not_a_story():
    bulkhead = box(15, 30, 20, 35, z0=33, z1=41, id="bulkhead")
    m = measure(site(RECT, *FLOORS, bulkhead), {**FACTS, "stories": None})
    assert m["stories"]["value"] is None and "a bulkhead" in m["stories"]["reason"]
    assert sorted(r["value"] for r in m["stories"]["readings"]) == [3, 4]


def test_a_full_size_fourth_floor_is_counted():
    top = floor(10, 25, 35, 65, z0=33, z1=44, id="floor 4")
    assert measure(site(RECT, *FLOORS, top), {**FACTS, "stories": None})["stories"]["value"] == 4


def test_a_floor_moved_alone_is_floors_misaligned():
    moved = floor(13, 25, 38, 65, z0=11, z1=22, id="floor 2")            # floor 2 shifted 3 ft sideways on its own
    m = measure(site(RECT, FLOORS[0], moved, FLOORS[2]), {**FACTS, "stories": None})
    assert m["stories"]["value"] is None and m["stories"]["reason"].startswith("floors misaligned")


def test_a_gordium_floor_stretched_or_merged_is_no_longer_one_story():
    """Four 8.5 ft floors merged into one 34 ft block keep the first floor's mark: never "1 story" (a false pass)."""
    merged = floor(10, 25, 35, 65, z0=0, z1=34, id="floor 1", drawn=8.5)
    m = measure(site(RECT, merged), {**FACTS, "stories": None})["stories"]
    assert m["value"] is None and m["reason"].startswith("no floor blocks are drawn")
    stretched = [floor(10, 25, 35, 65, z0=0, z1=8.5, id="floor 1"), floor(10, 25, 35, 65, z0=8.5, z1=17, id="floor 2"),
                 floor(10, 25, 35, 65, z0=17, z1=34, id="floor 3", drawn=8.5)]
    m = measure(site(RECT, *stretched), {**FACTS, "stories": None})["stories"]
    assert m["value"] is None and sorted(r["value"] for r in m["readings"]) == [2, 3]


def test_the_grade_plane_is_the_main_buildings_own_walls_never_a_detached_garages():
    """§325-3: the ground "on each side of the building". A garage uphill must not lower the house's height."""
    house = box(10, 25, 35, 65, 0, 41, id="house")
    garage = box(40, 75, 48, 90, 12, 22, id="garage")
    at_house = [[22, 24, 0], [22, 66, 0], [9, 45, 0], [36, 45, 0]]
    at_garage = [[44, 74, 12], [44, 91, 12], [39, 82, 12], [49, 82, 12]]
    facts = {**FACTS, "ground_is_flat": None, "grade_elevation": None, "main_building": "house"}
    h = measure(site(RECT, house, garage), {**facts, "grade_points": at_house + at_garage})["building_height"]
    by = {r["reading"]: r["value"] for r in h["readings"]}
    assert by["the main building only"] == 41.0                  # its own walls: was 35 with the garage averaged in
    assert h["value"] is None                                    # the readings differ: never a pass at 35
    # spots only at the house: the reading with the garage as part of the building has no ground at its walls
    h = measure(site(RECT, house, garage), {**facts, "grade_points": at_house})["building_height"]
    assert h["value"] is None and h["reason"].startswith("with the other solids as part of the building")


def test_a_wing_on_lower_ground_lowers_the_grade_plane_of_the_reading_that_includes_it():
    house = box(10, 25, 35, 65, 0, 34, id="house")
    wing = box(35, 30, 45, 50, -6, 20, id="wing")                 # touching, stepping down 6 ft
    spots = [[22, 24, 0], [22, 66, 0], [9, 45, 0], [36, 55, 0], [36, 28, 0],
             [40, 29, -6], [40, 51, -6], [46, 40, -6]]
    facts = {**FACTS, "ground_is_flat": None, "grade_elevation": None, "main_building": "house", "grade_points": spots}
    h = measure(site(RECT, house, wing), facts)["building_height"]
    by = {r["reading"]: r["value"] for r in h["readings"]}
    with_wing = next(v for k, v in by.items() if k.startswith("with every other solid"))
    assert by["the main building only"] == 34.0 and with_wing > 35.0      # lower ground at the wing's walls
    assert h["value"] is None                                    # was 34 under both readings: a false pass


def test_terrain_samples_under_an_attached_wing_are_ground_beneath_not_off_the_walls():
    """The plugin samples the terrain 1 ft outside each solid's own walls; where a wing joins the house those
    samples fall under the other solid. They are left out: height is still measured from the walls around."""
    house = box(10, 25, 35, 65, 0, 30, id="house")
    wing = box(35, 30, 45, 50, 0, 20, id="wing")
    house_walls = [[22, 24, 0], [22, 66, 0], [9, 45, 0], [36, 40, 0]]         # (36, 40) is under the wing
    wing_walls = [[40, 29, 0], [40, 51, 0], [46, 40, 0], [34, 40, 0]]         # (34, 40) is under the house
    extra = [[36, 27.5, 0], [36, 57.5, 0]]                                     # the house's east wall around the wing
    facts = {**FACTS, "ground_is_flat": None, "grade_elevation": None, "main_building": "house",
             "grade_points": house_walls + wing_walls + extra}
    h = measure(site(RECT, house, wing), facts)["building_height"]
    assert h["value"] == 30.0, h                       # was "with the other solids … needs spot grades": never checked


def test_two_building_objects_with_one_id_are_never_measured_as_one():
    """Stress test F4: two floor blocks sharing an id; one was dropped from the story count while the height
    still counted it. Nothing is ever dropped silently: every building measurement needs review, saying why."""
    m = measure(site(RECT, box(10, 25, 35, 65, 0, 10), box(10, 25, 35, 65, 10, 20)), FACTS)
    for name in ("building_height", "building_area", "front_yard", "rear_yard"):
        assert m[name]["value"] is None and "share the id house" in (m[name]["reason"] or ""), name
    ok = measure(site(RECT, box(10, 25, 35, 65, 0, 10, id="f1"), box(10, 25, 35, 65, 10, 20, id="f2")), FACTS)
    assert "share the id" not in str(ok)


def test_a_fourth_floor_block_sharing_an_id_never_lets_the_stories_comply():
    """Stress test: the starting house plus a 4th floor block on top with the id 'floor 2'. Every building
    measurement needed review except stories, which counted 3 (one 'floor 2' dropped): 4 floors > 3 allowed
    must never comply. Every measurement read from building objects needs review, naming the shared id."""
    fourth = floor(10, 25, 35, 65, z0=33, z1=44, id="floor 2")
    m = measure(site(RECT, *FLOORS, fourth), {**FACTS, "stories": None})
    assert m["stories"]["value"] is None and "share the id floor 2" in m["stories"]["reason"]
    lot_only = {"lot_area", "lot_width", "lot_depth", "district", "use", "sleeping_rooms", "parking_spaces"}
    read_from_buildings = [k for k in m if k not in lot_only]
    assert read_from_buildings and all(m[k]["value"] is None and "share the id" in (m[k]["reason"] or "")
                                       for k in read_from_buildings), {k: m[k]["value"] for k in read_from_buildings}


def test_on_existing_grade_with_no_ground_the_height_says_why_it_isnt_measured():
    """Found by PR #18: with the ground as it is (grade_is existing) and no ground level given, the height's
    reason began "measured from existing grade", though nothing was measured. The reason comes from what was
    measured: no ground level, so not measured."""
    m = measure(site(), {**FACTS, "grade_is": "existing", "grade_elevation": None})
    h = m["building_height"]
    assert h["value"] is None and "measured from existing grade" not in h["reason"]
    assert "ground level isn't given" in h["reason"] and "measured_as_is" not in h
    measured = measure(site(), {**FACTS, "grade_is": "existing"})["building_height"]      # measured: said so
    assert measured["value"] is None and "measured from existing grade" in measured["reason"]
    assert measured["measured_as_is"] == 30.0


def _planar_roof(n):
    faces = []
    for i in range(n):
        for j in range(n):
            x0, x1, y0, y1 = i * 0.5, (i + 1) * 0.5, j * 0.5, (j + 1) * 0.5
            faces += [{"points": [[x0, y0, 30 + 0.5 * x0], [x1, y0, 30 + 0.5 * x1], [x1, y1, 30 + 0.5 * x1]]},
                      {"points": [[x0, y0, 30 + 0.5 * x0], [x1, y1, 30 + 0.5 * x1], [x0, y1, 30 + 0.5 * x0]]}]
    return faces


def test_plane_grouping_grows_about_in_step_with_the_faces():
    """Review rounds 3 and 4 of the mesh fix: refitting every corner at every join made grouping quadratic (55 s
    for 28,800 triangles), then copying the group's corner list at every join kept it near n^2.3 (115,200 faces:
    54 s). Deterministic: the corner blocks moved and corners gathered stay under 20 per face at 12,800 faces
    (about n log n). And by the clock, in the same run: 16 times the faces take under 25 times as long (in place:
    about 17; copying the list: about 31)."""
    import time
    from model_measurement.measure import _planes
    work = {}
    faces = _planar_roof(80)
    assert len(_planes(faces, work)) == 1
    assert work["blocks_moved"] + work["corners_gathered"] <= 20 * len(faces), work

    def clock(n):
        f = _planar_roof(n)
        start = time.perf_counter()
        assert len(_planes(f)) == 1
        return time.perf_counter() - start

    clock(20)
    small = clock(40)
    big = clock(160)
    small = (small + clock(40)) / 2
    assert big < 25 * small, f"16x the faces took {big / small:.1f}x as long"
    assert big < 120


@pytest.mark.parametrize("blocks", [
    [box(10, 25, 35, 65, 0, 10, id="b1"), box(10, 25, 35, 65, 10, 20, id="b2"), box(10, 25, 35, 65, 20, 30, id="b3"),
     box(10, 25, 35, 65, 30, 40, id="b2")],                                                     # plain solids
    FLOORS + [floor(10, 25, 35, 65, z0=33, z1=44, id="floor 2")],                               # floor blocks
])
def test_a_typed_story_count_never_stands_beside_solids_sharing_an_id(blocks):
    """Review of 0b56ec9 (P0): plain stacked solids, a typed 3 and a shared id: the stacking split the stack and
    the typed 3 stood with no reason (unique ids correctly said: typed 3, 4 blocks). Whatever was typed, stories
    needs review, naming the shared id."""
    m = measure(site(RECT, *blocks), {**FACTS, "stories": 3})
    shared = blocks[-1]["id"]
    assert m["stories"]["value"] is None and f"share the id {shared}" in m["stories"]["reason"]


@pytest.mark.parametrize("main", [None, "gone"])
def test_counted_floors_with_no_main_building_never_let_a_typed_count_stand(main):
    """Review round 2 of the stories fix (P0): four floor blocks and a garage, no main building (or one no longer
    in the model), typed 3: stories said 3 'stated by the architect' while the height said pick the main building.
    The drawing can be counted, so stories stop exactly as the height does."""
    garage = floor(40, 70, 48, 90, z0=0, z1=11, id="g1")
    fourth = floor(10, 25, 35, 65, z0=33, z1=44, id="floor 4")
    m = measure(site(RECT, *FLOORS, fourth, garage), {**FACTS, "stories": 3, "main_building": main})
    assert m["stories"]["value"] is None and "pick the main building" in m["stories"]["reason"]
    assert m["building_height"]["value"] is None and "pick the main building" in m["building_height"]["reason"]


def test_a_single_plain_solid_keeps_the_typed_count_stated_by_the_architect():
    """Nothing drawn can be counted (one solid, no floor marks): the typed count stands, labelled as stated."""
    m = measure(site(RECT, box(10, 25, 35, 65, 0, 40, id="h")), {**FACTS, "stories": 3})["stories"]
    assert m["value"] == 3 and "stated by the architect" in m["how"]


def test_a_plain_main_building_with_a_floor_block_wing_never_keeps_the_typed_count():
    """Review round 3 of the stories fix (P0): the main building picked is one plain solid, and a wing of four floor
    blocks stands beside it. The height reads both (main alone, and with the wing as part of it: §325-25), but
    stories kept the typed 2 as the value. Stories are read over the same candidate buildings: with the wing, the
    typed 2 is fewer than its 4 floor blocks, so it needs review, never 2."""
    main = box(10, 25, 35, 65, 0, 20, id="house")
    wing = [floor(35, 25, 45, 45, z0=i * 10, z1=(i + 1) * 10, id=f"w{i}") for i in range(4)]
    m = measure(site(RECT, main, *wing), {**FACTS, "stories": 2, "main_building": "house"})["stories"]
    assert m["value"] is None and "the stories typed (2) are fewer than the floor blocks drawn (4)" in m["reason"]


SEEDS = range(10)                       # fixed: 10 x 200 = 2,000 drawings, the same every run


def _drawing(rnd):
    """A random drawing, and, worked out from the blocks themselves (not by measure.py), each stack's floors:
    stacks side by side (floor blocks or plain solids, one to five high: a plain main building beside floor-block
    wings among them), shared ids, a main building picked, missing or stale, any typed count."""
    blocks, stacks = [], []
    for k in range(rnd.randint(1, 3)):
        x0 = 5 + 12 * k
        high, marked = rnd.randint(1, 5), rnd.random() < 0.6
        ids = [f"s{k}b{i}" for i in range(high)]
        gap = rnd.randrange(1, high - 1) if marked and high > 2 and rnd.random() < 0.2 else None   # a floor deleted
        for i, bid in enumerate(ids):
            if i == gap:
                continue
            blocks.append(floor(x0, 25, x0 + 12, 60, z0=i * 10, z1=(i + 1) * 10, id=bid) if marked else
                          box(x0, 25, x0 + 12, 60, z0=i * 10, z1=(i + 1) * 10, id=bid))
        ids = [b for i, b in enumerate(ids) if i != gap]
        stacks.append({"ids": ids, "countable": marked, "floors": high, "tall": not marked, "below": False,
                       "gap": gap is not None,
                       "blocks": 0 if marked else high})          # plain solids stacked: each may be a story
    if rnd.random() < 0.35:            # a plain wing behind the first stack: a porch slab, a tall wing, a walk-out
        z0, z1 = rnd.choice([(0, 3), (0, 6), (0, 7), (0, 8), (0, 12), (0, 32), (-10, 10.5),   # on the ground
                             (12, 18), (4, 10), (0.05, 6), (-0.5, 6.4), (-3, 0)])      # raised, or below the ground
        blocks.append(box(5, 60, 17, 70, z0, z1, id="wing"))
        # left out only if it stands on the ground and is under 7 ft (R305.1): it fits inside the first story
        stacks.append({"ids": ["wing"], "countable": False, "floors": 0, "tall": not (z0 == 0 and z1 - z0 < 7),
                       "below": z0 < 0, "blocks": 0, "raised": z0 > 0})
    if rnd.random() < 0.2:             # a room over the first stack's roof, or beside its edge, a little apart
        top = 10 * len(stacks[0]["ids"]) + (10 if stacks[0].get("gap") else 0)
        x = rnd.choice([7, 17.1, 17.0])                    # over the roof, just past its edge, at its edge
        dz = rnd.choice([0.05, 0.5, 3])
        blocks.append(box(x, 30, x + 6, 40, top + dz, top + dz + 7, id="room"))
        stacks.append({"ids": ["room"], "countable": False, "floors": 0, "tall": True, "below": False,
                       "blocks": 0, "raised": True})
    if rnd.random() < 0.2:
        rnd.choice(blocks)["id"] = rnd.choice(blocks)["id"]
    pick = rnd.choice([None, "stale"] + [b["id"] for b in blocks])
    return blocks, stacks, pick, rnd.choice([None, 1, 2, 3, 4, 5])


def test_stories_never_take_a_value_below_any_candidate_buildings_floors():
    """Property, over 2,000 drawings: a story count is a value only if no id is shared, a main building is known,
    and it is at least the floors of every candidate building the height reads (the main one alone, and with every
    other solid), worked out from the blocks; a typed count stands as the value only when no drawn object anywhere
    can be counted."""
    import random
    for seed in SEEDS:
        rnd = random.Random(seed)
        for _ in range(200):
            blocks, stacks, pick, typed = _drawing(rnd)
            m = measure(site(RECT, *blocks), {**FACTS, "stories": typed, "main_building": pick})["stories"]
            if m["value"] is None:
                continue
            ids = [b["id"] for b in blocks]
            assert len(set(ids)) == len(ids), (seed, ids, m)
            main = next((s for s in stacks if pick in s["ids"]), stacks[0] if len(stacks) == 1 else None)
            starting = [s for s in stacks if s["countable"]]        # Gordium's own floor blocks (a gap: two of them)
            if main is None and pick is None and sum(2 if s.get("gap") else 1 for s in starting) == 1:
                main = starting[0]                                  # no pick: the starting house, assumed
            assert main is not None, (seed, stacks, pick, m)       # no main building: never a value
            assert not any(s.get("gap") for s in stacks), (seed, stacks, m)   # floors over a gap: a question
            assert not any(s.get("raised") for s in stacks), (seed, stacks, m)  # a raised plain part: a question
            for members in ([main], stacks):    # each candidate building: the main one alone, and with every part
                assert not any(s["below"] for s in members), (seed, stacks, m)     # a basement or cellar: asks
                most = max((s["floors"] for s in members if s["countable"]), default=None)
                if most is None or any(s["tall"] for s in members):   # stories not all drawn: only the count typed
                    assert typed is not None and m["value"] == typed >= (most or 0), (seed, stacks, pick, typed, m)
                    assert all(typed >= s["blocks"] for s in members), (seed, stacks, pick, typed, m)
                else:
                    assert m["value"] >= most, (seed, stacks, pick, typed, m)


@pytest.mark.parametrize("typed", [1, 2])
def test_a_plain_house_with_a_three_floor_wing_against_its_rear_wall_never_complies_below_three(typed):
    """Stress test F6 (stress-tests d32d437): a plain-solid house and a wing of three floor blocks against its rear
    wall, a typed 1 or 2: stories complied. Read over the height's candidate buildings it is the typed count alone
    and three with the wing: needs review, never a count below three."""
    house = box(10, 25, 35, 55, 0, 20, id="house")
    wing = [floor(10, 55, 35, 65, z0=i * 11, z1=(i + 1) * 11, id=f"w{i}") for i in range(3)]
    m = measure(site(RECT, house, *wing), {**FACTS, "stories": typed, "main_building": "house"})["stories"]
    assert m["value"] is None and "fewer than the floor blocks drawn (3)" in m["reason"]


def test_height_and_stories_report_over_the_same_candidate_buildings():
    """One list of candidate buildings (_assemblies) is read by both: their readings start with the same words."""
    from model_measurement.measure import _assemblies
    main = box(10, 25, 35, 65, 0, 20, id="house")
    wing = [floor(35, 25, 45, 45, z0=i * 10, z1=(i + 1) * 10, id=f"w{i}") for i in range(4)]
    m = measure(site(RECT, main, *wing), {**FACTS, "stories": 4, "main_building": "house"})
    words = [c["words"] for c in _assemblies({"id": "x"}, [{"id": "y"}])]

    def over(record):
        return {next(w for w in words if r["reading"].startswith(w)) for r in record["readings"]
                if any(r["reading"].startswith(w) for w in words)}
    assert over(m["building_height"]) == over(m["stories"]) == set(words)


@pytest.mark.parametrize("typed, porch, expect", [(None, False, None), (3, False, 3), (2, False, None),
                                                   (None, True, 3)])
def test_a_plain_solid_joined_to_a_floor_stack_leaves_its_stories_to_the_count_typed(typed, porch, expect):
    """#18 round 15 (P0): three 11 ft floor blocks with a plain 32 ft solid against them. The solid's stories
    aren't drawn: with no count typed, needs review; 3 typed covers the whole building; 2 typed is fewer than the
    floors drawn (a question). A 3 ft porch slab can't hold a story (7 ft, R305.1): the floors drawn are the count."""
    floors = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    other = box(10, 15, 35, 25, 0, 3, id="porch") if porch else box(35, 25, 45, 45, 0, 32, id="wing")
    m = measure(site(RECT, *floors, other), {**FACTS, "stories": typed, "main_building": "f0"})["stories"]
    assert m["value"] == expect, m
    if typed is None and not porch:
        assert "part of the building (wing) isn't drawn as floor blocks" in m["reason"]
    if typed == 2:
        assert "the stories typed (2) are fewer than the floor blocks drawn (3)" in m["reason"]


def test_the_faces_open_to_the_sky_are_found_point_by_point():
    """The open-to-the-sky test runs all its point checks at once; it finds the same faces as checking each sample
    point against each other face's grown outline one by one (random overlapping boxes and sloped roofs)."""
    import random
    from model_measurement.measure import TOL, _normal_z, _open_to_the_sky, _plan, _plane_z, _samples
    rnd = random.Random(7)
    for _ in range(60):
        faces = []
        for k in range(rnd.randint(1, 4)):
            x, y, z0 = rnd.uniform(0, 20), rnd.uniform(0, 20), rnd.choice([0, 0, 10])
            make = rnd.choice([lambda: box(x, y, x + rnd.uniform(4, 15), y + rnd.uniform(4, 15), z0, z0 + 10, f"b{k}"),
                               lambda: sloped_roof_box(x, y, x + 10, y + 12, z0 + 10, z0 + 16, f"b{k}")])
            faces += make()["faces"]
        flat = [(f, _plan(f)) for f in faces if _normal_z(f["points"]) > 0.001]
        expect = []
        for i, (f, shape) in enumerate(flat):
            if shape.area <= 1e-9:
                continue
            for p in _samples(shape):
                z = _plane_z(f, p.x, p.y)
                if not any((h := _plane_z(g, p.x, p.y)) is not None and h > z + TOL
                           for j, (g, s) in enumerate(flat) if j != i and s.buffer(TOL).contains(p)):
                    expect.append(f)
                    break
        assert [id(f) for f in _open_to_the_sky(faces)] == [id(f) for f in expect]


@pytest.mark.parametrize("typed", [None, 2, 3, 4])
def test_a_walk_out_wing_reaching_below_the_ground_asks_whatever_was_typed(typed):
    """#18 round 16: a plain wing from 10 ft below the ground to 10.5 ft above, beside three floor blocks: whether
    its lower level is a basement or cellar (§325-3) is open, so stories need review whatever was typed."""
    floors = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    m = measure(site(RECT, *floors, box(35, 25, 45, 45, -10, 10.5, id="wing")),
                {**FACTS, "stories": typed, "main_building": "f0"})["stories"]
    assert m["value"] is None and "part of the building (wing) is below the ground" in m["reason"]


def test_a_plain_house_and_a_plain_garage_take_the_count_typed():
    """The common R-1 drawing: a house and a 10 ft garage, each one plain solid, 2 stories typed: 2."""
    m = measure(site(RECT, box(10, 25, 35, 65, 0, 24, id="house"), box(36, 70, 46, 90, 0, 10, id="garage")),
                {**FACTS, "stories": 2, "main_building": "house"})["stories"]
    assert m["value"] == 2


@pytest.mark.parametrize("typed, expect", [(3, 3), (2, None), (None, None)])
def test_a_plain_20_ft_wing_beside_three_floor_blocks_takes_the_count_typed_only_if_it_covers_them(typed, expect):
    floors = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    m = measure(site(RECT, *floors, box(35, 25, 45, 45, 0, 20, id="wing")),
                {**FACTS, "stories": typed, "main_building": "f0"})["stories"]
    assert m["value"] == expect, m
    if typed == 2:
        assert "fewer than the floor blocks drawn" in m["reason"]
    if typed is None:
        assert "isn't drawn as floor blocks" in m["reason"] and "floors are drawn" not in m["reason"]


@pytest.mark.parametrize("typed, expect", [(1, None), (2, None), (3, 3)])
def test_a_wing_of_two_stacked_plain_solids_beside_three_floor_blocks_takes_only_a_count_that_covers_them(typed, expect):
    """#14 round 4 (P0): a 40 ft wing of two plain solids stacked was counted by its blocks with the typed count
    folded in: 1 or 2 typed beside 3 floor blocks came out 3, saying "as stated by the architect". Plain solids,
    stacked or not, are never counted: 1 or 2 typed is fewer than the 3 floor blocks (needs review); 3 typed is
    the architect's statement for the whole building."""
    floors = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    wing = [box(35, 25, 45, 45, 0, 20, id="w0"), box(35, 25, 45, 45, 20, 40, id="w1")]
    m = measure(site(RECT, *floors, *wing), {**FACTS, "stories": typed, "main_building": "f0"})["stories"]
    assert m["value"] == expect, m
    if typed == 1:                      # fewer than the wing's two stacked solids, each maybe a story
        assert "fewer than the solids stacked on w0 (2)" in m["reason"]
    elif expect is None:
        assert "fewer than the floor blocks drawn (3)" in m["reason"]
    else:
        assert "for the whole building" in m["how"] or any("for the whole building" in r["reading"] for r in m["readings"])


@pytest.mark.parametrize("z0, z1", [(32.9, 39.4), (33.05, 39.55), (-0.5, 6.4)])
@pytest.mark.parametrize("typed", [None, 3])
def test_a_short_part_off_the_ground_is_never_left_out_of_the_stories(z0, z1, typed):
    """#14 final check (P0): a 6.5 ft room on the roof of three 11 ft floor blocks (0.1 ft into the roof, or 0.05
    ft above it), or a short part from 0.5 ft below the ground, was dropped as too low to hold a story, so 3 floors
    counted 3. §325-3's STORY has no least height: only a part on the ground and under 7 ft is left out. The roof
    room leaves the count to the architect; the part below the ground asks the basement question."""
    floors = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    part = box(12, 30, 20, 40, z0, z1, id="room") if z0 > 0 else box(35, 25, 45, 45, z0, z1, id="room")
    m = measure(site(RECT, *floors, part), {**FACTS, "stories": typed, "main_building": "f0"})["stories"]
    if z0 < 0:
        assert m["value"] is None and "part of the building (room) is below the ground" in m["reason"]
    elif z0 > 33:                       # floating over the roof: a raised plain part (round 7), never the typed count
        assert m["value"] is None and "starts above the ground" in m["reason"]
    elif z0 > 0:                        # round 6: sunk into the roof asks too, as touching and floating do
        assert m["value"] is None and "starts above the ground" in m["reason"]
    elif typed is None:
        assert m["value"] is None and "part of the building (room) isn't drawn as floor blocks" in m["reason"]
    else:
        assert m["value"] == 3


@pytest.mark.parametrize("fourth", [False, True])
def test_a_floor_block_over_a_deleted_floor_is_still_counted_and_asks(fourth):
    """Stress F10 (P0): floor 2 deleted, floor 1 at 0 to 11 ft 8 in and floor 3 at 23 ft 4 in to 35 ft. Floor 3 was
    left out as a separate building, so with a 9 ft plain wing and 1 typed, stories complied; with a fourth floor
    on floor 3 and 2 typed, too. Floor blocks over one another in plan are the building's floors: the gap is a
    question (a floor not drawn, or a space open to below), never a smaller count."""
    h = 35 / 3
    blocks = [floor(10, 25, 35, 65, z0=0, z1=h, id="floor 1"), floor(10, 25, 35, 65, z0=2 * h, z1=3 * h, id="floor 3")]
    if fourth:
        blocks.append(floor(10, 25, 35, 65, z0=3 * h, z1=4 * h, id="floor 4"))
    blocks.append(box(35, 25, 45, 45, 0, 9, id="wing"))
    m = measure(site(RECT, *blocks), {**FACTS, "stories": 2 if fourth else 1, "main_building": "floor 1"})["stories"]
    assert m["value"] is None and "parts of the building drawn one over another don't stand on each other" in m["reason"]


@pytest.mark.parametrize("shape, typed", [("podium", 1), ("roof room", 3)])
def test_a_plain_solid_over_or_under_floor_blocks_with_a_gap_asks(shape, typed):
    """Round 6 (P0): a plain podium (0 to 9 ft) under a floor block (20 to 30 ft), 1 typed, complied with 1; a room
    0.05 ft above the roof of three floor blocks, 3 typed, complied with 3; touching, both asked. Every solid one
    over another in plan is one building whatever the gap, and a real gap between its levels asks."""
    if shape == "podium":
        blocks = [box(10, 25, 35, 65, 0, 9, id="podium"), floor(10, 25, 35, 65, z0=20, z1=30, id="floor")]
        main = "podium"                 # (the floor block picked: the ground doesn't meet it, which asks too)
    else:
        blocks = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
        blocks.append(box(12, 30, 20, 40, 33.05, 39.55, id="room"))
        main = "f0"
    m = measure(site(RECT, *blocks), {**FACTS, "stories": typed, "main_building": main})["stories"]
    assert m["value"] is None and ("don't stand on each other" if shape == "podium" else          # round 7: the room
                                   "starts above the ground") in m["reason"]                     # is a raised part


def test_an_l_shaped_house_of_two_floor_blocks_at_one_level_is_no_gap():
    """Round 6 (P2): two one-story floor blocks overlapping in plan at the same level (an L-shaped house) got a
    floors_apart question. They are one building's floor at one level: 1 typed, 1. (Two-story L-shapes whose
    blocks touch across the levels are joined by _stacks and asked as misaligned floors, as before.)"""
    a = floor(10, 25, 30, 65, z0=0, z1=10, id="a")
    b = floor(25, 25, 45, 40, z0=0, z1=10, id="b")
    m = measure(site(RECT, a, b), {**FACTS, "stories": 1, "main_building": "a"})["stories"]
    assert m["value"] == 1, m


def _moved(block, dx, dy, dz):
    """A copy of a solid moved by (dx, dy, dz) feet."""
    import copy
    out = copy.deepcopy(block)
    for f in out["faces"]:
        for pt in [*f["points"], *(q for h in f.get("holes") or [] for q in h)]:
            pt[0] += dx
            pt[1] += dy
            pt[2] += dz
    return out


def _lifted(block, dz):
    return _moved(block, 0, 0, dz)


def test_a_tenth_of_a_foot_any_way_never_changes_one_story_count_into_another():
    """Metamorphic (rounds 6 and 7): moving any one solid by up to 0.1 ft up, down or sideways (touching, a
    small gap, a small overlap, in plan or in height) never turns a story count into a different count, from
    drawings that give a count and drawings that need review alike: the result is the same, or needs review.
    Fixed seeds; the drawings of the property test."""
    import random
    rnd = random.Random(11)
    checked = 0
    for _ in range(260):
        blocks, stacks, pick, typed = _drawing(rnd)
        facts = {**FACTS, "stories": typed, "main_building": pick}
        before = measure(site(RECT, *blocks), facts)["stories"]["value"]
        i = rnd.randrange(len(blocks))
        steps = [(0, 0, d) for d in (-0.1, -0.05, 0.05, 0.1)] + [(d, 0, 0) for d in (-0.1, 0.1)] + \
            [(0, d, 0) for d in (-0.1, 0.1)] + [(0.1, 0.1, 0.05)]
        for dx, dy, dz in rnd.sample(steps, 2):
            moved = blocks[:i] + [_moved(blocks[i], dx, dy, dz)] + blocks[i + 1:]
            after = measure(site(RECT, *moved), facts)["stories"]["value"]
            checked += 1
            assert after is None or before is None or after == before, \
                (blocks[i]["id"], (dx, dy, dz), before, after, stacks, pick, typed)
    assert checked > 300


@pytest.mark.parametrize("x, z0, z1", [(35.1, 25, 35), (35, 22, 32)])
def test_a_room_raised_beside_the_roof_edge_asks(x, z0, z1):
    """Round 7 (P1): a room floating at 25 to 35 ft beside a 2-floor house's roof edge (x 35.1, no overlap in
    plan), or at its edge (x 35, 22 to 32 ft), let 2 typed stand, while over the roof it asked. A plain part
    starting above the ground asks, whatever its plan relation."""
    floors = [floor(10, 25, 35, 65, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(2)]
    m = measure(site(RECT, *floors, box(x, 30, x + 8, 40, z0, z1, id="room")),
                {**FACTS, "stories": 2, "main_building": "f0"})["stories"]
    assert m["value"] is None and "part of the building (room) starts above the ground" in m["reason"]


def test_the_stories_read_each_candidate_building_from_its_own_grade_plane():
    """#18 round 18's candidate grades, one definition: with spot grades only at the house's walls and a wing of
    floor blocks beside it, the "with every other solid" candidate's grade plane can't be found, so the stories
    need review for that reason, as the height does (before, the stories read the house's grade for both)."""
    house = [floor(10, 25, 35, 65, z0=10 * i, z1=10 * (i + 1), id=f"h{i}") for i in range(2)]
    wing = [floor(40, 75, 48, 90, z0=0, z1=10, id="w0")]
    facts = {**FACTS, "stories": 2, "main_building": "h0", "ground_is_flat": None, "grade_elevation": None,
             "grade_points": [[22, 24, 0], [22, 66, 0], [9, 45, 0], [36, 45, 0]]}
    m = measure(site(RECT, *house, *wing), facts)
    assert m["stories"]["value"] is None and m["stories"]["reason"] == m["building_height"]["reason"]
    assert "spot grades at their walls too" in m["stories"]["reason"]


def test_each_candidate_buildings_ground_is_checked_against_its_own_solids():
    """#18 round 19 (P0), one definition: the ground is checked against each candidate building, not only the
    whole site. A house drawn 5 ft above the ground beside a wing on it: the site's solids meet the ground, the
    house alone doesn't, so its stories (2 typed) and height need review, never the typed count."""
    house = box(10, 25, 35, 65, 5, 30, id="house")
    wing = box(35, 25, 45, 45, 0, 10, id="wing")
    m = measure(site(RECT, house, wing), {**FACTS, "stories": 2, "main_building": "house"})
    for name in ("stories", "building_height"):
        assert m[name]["value"] is None and "doesn't meet the buildings" in m[name]["reason"], (name, m[name])


def test_the_starting_house_is_the_main_building_when_none_is_picked():
    """Architect review in Rhino (P1-2): adding a detached garage to the starting house blanked height, stories and
    yards with "pick the main building". When exactly one building is Gordium's starting house (its floor blocks),
    it is the main building, said as assumed; the garage is read as a possible accessory building. Two such houses,
    or a pick that names something else, still ask."""
    house = [floor(10, 25, 35, 55, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    garage = box(38, 70, 48, 90, 0, 10, id="garage")
    m = measure(site(RECT, *house, garage), {**FACTS, "stories": 3})
    for name in ("building_height", "stories", "front_yard", "rear_yard"):
        r = m[name]
        assert r["value"] is not None or r["readings"], (name, r)
        assert "pick the main building" not in (r.get("reason") or "")
        assert r.get("main_assumed") is True and "assumed" not in r["how"], (name, r)     # a marker, not words
    height = m["building_height"]
    assert {r["value"] for r in height["readings"]} >= {10.0} and \
        any(r["reading"].startswith("if garage were the main building") for r in height["readings"])
    assert "(main_building)" in height["reason"] and any(
        r["reading"].startswith("if garage were the main building") for r in m["stories"]["readings"])
    other = [floor(36, 70, 48, 90, z0=0, z1=11, id="g0")]
    m = measure(site(RECT, *house, *other), {**FACTS, "stories": 3})
    assert "pick the main building" in m["building_height"]["reason"]



def test_a_building_outside_the_lot_is_named_and_waits_only_what_it_touches():
    """Architect review in Rhino (P2-12): "a building isn't inside the lot" named none, and blanked every yard even
    when the main building was inside. It names the building; coverage (every building) waits; the yards are
    measured from a main building inside the lot, the other solid in their "any solid" reading."""
    m = measure(site(RECT, box(10, 25, 35, 65, id="house"), box(45, 70, 60, 80, id="shed")),
                {**FACTS, "main_building": "house"})
    assert m["building_area"]["value"] is None and m["building_area"]["reason"] == "a building isn't inside the lot: 1 other building"
    assert m["building_area"]["objects"] == ["shed"]
    for name in ("front_yard", "side_yard_smaller", "rear_yard"):
        assert m[name]["value"] is not None or m[name]["readings"], (name, m[name])
    m = measure(site(RECT, box(40, 25, 65, 65, id="house")), FACTS)
    assert m["front_yard"]["reason"] == "a building isn't inside the lot: the building"


def test_an_assumed_starting_house_never_passes_a_height_the_other_buildings_pick_would_fail():
    """Review of the main-building default (P2): with spot grades the grade plane kept its own pick and still asked;
    made to share the default naively, a plain building on lower ground, 40 ft from its own walls, would never be
    read as the main building, so the assumed house (33 ft) would pass. Each other building is read as the main
    one from its own grade plane: 40 ft is among the readings, so it never passes."""
    house = [floor(10, 25, 35, 55, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    other = box(40, 70, 48, 90, -8, 32, id="other")
    points = [[22, 24, 0], [22, 56, 0], [9, 40, 0], [36, 40, 0],
              [44, 69, -8], [44, 91, -8], [39, 80, -8], [49, 80, -8]]
    facts = {**FACTS, "stories": 3, "ground_is_flat": None, "grade_elevation": None, "grade_points": points}
    m = measure(site(RECT, *house, other), facts)
    h = m["building_height"]
    assert h["value"] is None and h.get("main_assumed"), h
    assert max(r["value"] for r in h["readings"]) >= 40 - 0.01, h["readings"]
    assert any(r["reading"].startswith("if other were the main building") for r in h["readings"])


def test_a_house_off_the_ground_asks_whether_or_not_the_spot_grades_sit_at_its_walls():
    """Stress F15 (P3): on a sloped lot, floor 1 raised 3.25 ft (nothing reaches the ground): every yard needs
    review ("doesn't meet"). Pull the west wall in 1.94 ft and the spot grades no longer sit at the walls, so that
    stop wasn't read and the floating house's yards complied. Whether the building reaches the ground is now read
    from the spot grades' ground under its footprint: both drawings give the same yard verdicts."""
    points = [[22, 24, 0.0], [22, 66, 2.0], [9, 45, 1.0], [36, 45, 1.0]]       # a slope from the street up
    facts = {**FACTS, "ground_is_flat": None, "grade_elevation": None, "grade_points": points}
    verdicts = []
    for west in (10, 11.94):
        house = [floor(west, 25, 35, 65, z0=3.25 + 11 * i, z1=3.25 + 11 * (i + 1), id=f"f{i}") for i in range(3)]
        m = measure(site(RECT, *house), {**facts, "stories": 3})
        verdicts.append({n: m[n]["value"] for n in ("front_yard", "side_yard_smaller", "side_yard_larger", "rear_yard")})
        assert all(v is None for v in verdicts[-1].values()), (west, verdicts[-1])
        assert all("doesn't meet the buildings" in m[n]["reason"] for n in ("front_yard", "rear_yard")), west
    assert verdicts[0] == verdicts[1]


def test_too_many_roofs_with_the_main_building_assumed_keeps_its_own_stop():
    """Round 2 of the main-building fixes (P1): with eight pitched-roof sheds (too many roof readings to list)
    _with_others gave its stop, and reading each shed as the main one then crashed on it. The stop stands."""
    house = [floor(2, 2, 20, 20, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    sheds = [sloped_roof_box(24 + 13 * (k % 2), 4 + 12 * (k // 2), 34 + 13 * (k % 2), 14 + 12 * (k // 2), 8, 12, f"s{k}")
             for k in range(8)]
    m = measure(site(RECT, *house, *sheds), {**FACTS, "stories": 3})
    h = m["building_height"]
    assert h["value"] is None and not h["readings"] and "too many" in h["reason"], h


def test_only_a_possible_principal_building_is_read_as_the_main_one():
    """Round 2 (P2): with the main building assumed, a deck slab, a balcony or a small shed was read as the main
    building on its own, asking a spurious main-building question. Only a solid that could be a principal
    building (enclosed, 7 ft or more, at least 70 sf: a habitable room, R304.1) is."""
    house = [floor(10, 25, 35, 55, z0=11 * i, z1=11 * (i + 1), id=f"f{i}") for i in range(3)]
    deck = box(10, 55, 35, 65, 0, 2, id="deck")
    porch = box(10, 20, 35, 25, 0, 1, id="porch")
    shed = box(40, 80, 46, 86, 0, 8, id="shed")                      # 36 sf: too small for a room
    m = measure(site(RECT, *house, deck, porch, shed), {**FACTS, "stories": 3})
    for name in ("building_height", "stories"):
        assert not any("were the main building" in r["reading"] for r in m[name]["readings"]), (name, m[name])
        assert "(main_building)" not in (m[name]["reason"] or "")
    garage = box(38, 70, 48, 90, 0, 10, id="garage")                 # 200 sf, 10 ft: it could be
    m = measure(site(RECT, *house, garage), {**FACTS, "stories": 3})
    assert any("if garage were the main building" in r["reading"] for r in m["building_height"]["readings"])



@pytest.mark.parametrize("points", [[[22, 24, 0.0], [22, 200, 8.0]],                     # two points, one far off
                                    [[22, 24, 0.0], [22.05, 45, 3.0], [22, 66, 0.0]]])   # near a line: a wild plane
def test_a_floating_house_is_found_however_few_or_lined_up_the_spot_grades(points):
    """Round 2 (P2): with two spot grades (their mean) or three nearly in a line (a wild plane), the ground fit
    missed a house drawn 3.25 ft above the ground. Then the nearest spot grade's level is used: clearly above it
    everywhere, the ground doesn't meet the buildings."""
    facts = {**FACTS, "ground_is_flat": None, "grade_elevation": None, "grade_points": points, "stories": 3}
    house = [floor(10, 25, 35, 65, z0=3.25 + 11 * i, z1=3.25 + 11 * (i + 1), id=f"f{i}") for i in range(3)]
    m = measure(site(RECT, *house), facts)
    assert m["front_yard"]["value"] is None and "doesn't meet the buildings" in m["front_yard"]["reason"]
