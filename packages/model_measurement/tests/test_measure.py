"""Made-up lots with known answers: each measurement, and each case the law leaves unclear (never a guess)."""

import math

import pytest
from shapely.geometry import LineString, Polygon

from model_measurement.measure import measure

FACTS = {"street_line": [[[0, 0], [50, 0]]], "corner_lot": False, "grade_elevation": 0, "use": "one_family_detached",
         "stories": 2}


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
    assert values(m) == {"use": "one_family_detached", "lot_area": 5000.0, "lot_width": 50.0, "lot_depth": 100.0,
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
    assert m["front_yard"]["value"] == 15.0        # nearest of the two street lines
    for name in ("lot_width", "side_yard_smaller", "side_yard_larger", "rear_yard", "lot_depth"):
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
    for name in ("lot_width", "side_yard_smaller", "side_yard_larger", "rear_yard", "lot_depth"):
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


def test_a_corner_lot_with_only_one_street_line_asks_for_both():
    m = measure(site(), {**FACTS, "corner_lot": True})
    for name in ("front_yard", "lot_width", "rear_yard"):
        assert m[name]["value"] is None and "both streets" in m[name]["reason"], name


def test_a_corner_rounded_in_three_pieces_counts_as_turning():
    # 90 degrees in three straight pieces of 30: no single join turns much, the frontage turns fully
    pts = [(0, 0), (40, 0)]
    for a in (30, 60, 90):
        x, y = pts[-1]
        pts.append((x + 5.18 * math.cos(math.radians(a - 15)), y + 5.18 * math.sin(math.radians(a - 15))))
    x, y = pts[-1]
    pts += [(x, 100), (0, 100)]
    street = [[list(pts[i]), list(pts[i + 1])] for i in range(4)] + [[list(pts[4]), list(pts[5])]]
    m = measure(site(lot(pts), box(10, 25, 35, 65)), {**FACTS, "corner_lot": True, "street_line": street})
    assert m["front_yard"]["value"] is not None                # both streets given: no "pick both streets"
    assert m["rear_yard"]["value"] is None and "corner lot" in m["rear_yard"]["reason"]


def test_a_taller_part_drawn_as_its_own_solid_counts_for_the_height():
    house, tower = box(10, 25, 35, 65, 0, 30), box(10, 65, 20, 70, 0, 45, id="tower")
    m = measure(site(RECT, house, tower), {**FACTS, "main_building": "house"})
    assert m["building_height"]["value"] is None
    assert sorted(r["value"] for r in m["building_height"]["readings"]) == [30.0, 45.0]
    garage = box(30, 75, 48, 95, 0, 12, id="garage")             # a lower solid doesn't change the height
    assert measure(site(RECT, house, garage), {**FACTS, "main_building": "house"})["building_height"]["value"] == 30.0
