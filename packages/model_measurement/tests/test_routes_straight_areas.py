"""Decisions 7 and 8 (routes/straight.py, routes/areas.py): remoteness, the diagonal and the story's areas, on the
route note's tests 4 (two exits in a rectangle), 7 (one stair, two doors) and 9 (storage on the line)
(docs/decisions/2026-11-20_route_measurement.md). Every figure is worked by hand in the comment beside it; none is
taken from the code under test. Feet in the layouts; the code works in inches and square inches."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes import areas, straight
from model_measurement.routes.stops import Stop

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import FT, description, door, rect, room, story  # noqa: E402

SF = FT * FT


def outlined(desc, outer, inner):
    desc["story_outlines"] = [{"level": "L1", "outer": [list(p) for p in outer], "inner": [list(p) for p in inner]}]
    return desc


def rectangle(doors):
    """A room 0 to 40 by 0 to 20 inside walls 6 in thick (outer faces -0.5 to 40.5 by -0.5 to 20.5)."""
    return outlined(description([room("r", rect(0, 0, 40, 20), use="day_care")], doors),
                    rect(-0.5, -0.5, 40.5, 20.5), rect(0, 0, 40, 20))


# --- test 4: two exits in a rectangle -----------------------------------------------------------------------------

def two_exits():
    return rectangle([door("a", (-0.25, 15), (0, 1), ("r", "outside"), exit_id="A"),
                      door("b", (30, -0.25), (1, 0), ("r", "outside"), exit_id="B")])


def test_4_remoteness_is_between_the_nearest_edges_of_the_clear_openings():
    # A's opening x -0.5 to 0, y 13.5 to 16.5; B's x 28.5 to 31.5, y -0.5 to 0: nearest corners (0, 13.5) and
    # (28.5, 0): sqrt(28.5^2 + 13.5^2) = 31.536; door centres: sqrt(30.25^2 + 15.25^2) = 33.877
    got = straight.remoteness(story(two_exits()))
    assert got.length / FT == pytest.approx(31.536, abs=1e-3) and set(got.exits) == {"A", "B"}
    assert got.centres / FT == pytest.approx(33.877, abs=1e-3)


def test_4_the_diagonal_is_corner_to_corner_of_the_outer_outline():
    got = straight.diagonal(story(two_exits()))
    assert got.length / FT == pytest.approx(math.sqrt(41 ** 2 + 21 ** 2), abs=1e-9)        # 46.065
    _, _, ratio = straight.ratio(story(two_exits()))
    assert ratio == pytest.approx(31.536 / 46.065, abs=1e-4)                                # 0.6846


def test_the_two_farthest_apart_exits_count():
    # a third exit C in the east wall centred at (40.25, 10): A to C, x 0 to 40, y 11.5 to 13.5: 40.050;
    # B to C: (31.5, 0) to (40, 8.5): 12.021; A to B 31.536: A and C count
    d = two_exits()
    d["doors"].append(door("c", (40.25, 10), (0, 1), ("r", "outside"), exit_id="C"))
    got = straight.remoteness(story(d))
    assert set(got.exits) == {"A", "C"} and got.length / FT == pytest.approx(math.hypot(40, 2), abs=1e-9)


# --- test 7: one stair, two doors ----------------------------------------------------------------------------------

def one_stair_two_doors():
    """A corridor 0 to 90 by 0 to 8 whose only exit is one stair enclosure entered by two doors 80 ft apart
    (centres (5, 8.25) and (85, 8.25)), both `exit_enclosure` with one `exit_id`."""
    return outlined(description([room("c", rect(0, 0, 90, 8))],
                                [door("s1", (5, 8.25), (1, 0), ("c", "outside"), exit_id="S", kind="exit_enclosure"),
                                 door("s2", (85, 8.25), (1, 0), ("c", "outside"), exit_id="S",
                                      kind="exit_enclosure")]),
                    rect(-0.5, -0.5, 90.5, 8.5), rect(0, 0, 90, 8))


def test_7_two_doors_into_one_stair_are_one_exit_so_no_remoteness():
    with pytest.raises(Stop) as stop:
        straight.remoteness(story(one_stair_two_doors()))
    assert stop.value.key == "too_few_exits" and "1 distinct exit" in stop.value.reason


def test_two_doors_of_one_exit_their_closest_pair_counts():
    # exit S's doors at x 5 and 85 on the north wall; exit A west (-0.25, 4): A's opening x -0.5 to 0, y 2.5 to 5.5;
    # the door at (5, 8.25): x 3.5 to 6.5, y 8 to 8.5: (0, 5.5) to (3.5, 8): sqrt(3.5^2 + 2.5^2) = 4.301
    d = one_stair_two_doors()
    d["doors"].append(door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"))
    got = straight.remoteness(story(d))
    assert got.length / FT == pytest.approx(math.hypot(3.5, 2.5), abs=1e-9) and got.doors == ("a", "s1")


def test_no_outline_no_diagonal():
    d = two_exits()
    del d["story_outlines"]
    with pytest.raises(Stop) as stop:
        straight.diagonal(story(d))
    assert stop.value.key == "outline_needed" and "story outlines" in stop.value.reason


def test_an_outer_outline_short_of_the_story_gives_no_ratio():
    """An outer outline that doesn't hold every room and exit door (drawn short, a wing only) would shrink the
    diagonal, so close exits would read as placed apart (BCNYS 1007.1.1, a false pass): no ratio, the outline's reason
    said. Drawn to the walls' outer faces, or within half an inch of them, it gives one."""
    assert straight.ratio(story(two_exits()))[2] == pytest.approx(31.536 / math.hypot(41, 21), abs=1e-3)
    for outer, ok in ((rect(-0.5, -0.5, 40.5, 20.5), True), (rect(-0.46, -0.46, 40.46, 20.46), True),
                      (rect(0, 0, 40, 20), False), (rect(0.45, 0.45, 39.55, 19.55), False), (rect(-0.5, -0.5, 30, 20.5), False)):
        d = outlined(two_exits(), outer, rect(0, 0, 40, 20))
        if ok:
            assert straight.ratio(story(d))[2] > 0, outer
            continue
        with pytest.raises(Stop) as stop:
            straight.ratio(story(d))
        assert stop.value.key == "outline_short", outer
    # the routes' story part: not measured, with the reason (so 1007.1.1's rule needs review)
    from model_measurement.routes import measure
    d = outlined(two_exits(), rect(0.45, 0.45, 39.55, 19.55), rect(0, 0, 40, 20))
    sp = measure(d)["parts"]["story"][0]
    assert "exit_remoteness_ratio" not in sp["measures"]
    assert "doesn't hold all of it" in sp["not_measured"]["exit_remoteness_ratio"]


def upper_story(outer):
    """An upper story (no door to outside): a corridor 0 to 60 by 0 to 20, two exit stairs north of it (S1 0 to 10,
    S2 36.5 to 46.5, by 20.5 to 28), each entered by one door; walls 6 in, the story's inner outline 0 to 60 by 0 to
    28. Its exits are just under half its diagonal apart, measured to the walls' outer faces."""
    rooms = [room("c", rect(0, 0, 60, 20), use="corridor", pass_through=True),
             room("S1", rect(0, 20.5, 10, 28), use="other", lockable=True),
             room("S2", rect(36.5, 20.5, 46.5, 28), use="other", lockable=True)]
    doors = [door("a", (5, 20.25), (1, 0), ("c", "S1"), exit_id="S1", kind="exit_enclosure"),
             door("b", (41.5, 20.25), (1, 0), ("c", "S2"), exit_id="S2", kind="exit_enclosure")]
    return outlined(description(rooms, doors), outer, rect(0, 0, 60, 28))


def test_an_outline_at_the_walls_inside_faces_gives_no_ratio():
    """Review of #281: an outer outline drawn at the walls' inside faces holds every room but is a wall short at each
    end, so exits just under 1007.1.1's half read as over it (0.496 to 0.506 here, an upper story whose exits are stair
    doors: no door to outside pins the outline to the outer face). The outer outline must be at least 3.5 in (the
    thinnest exterior wall) beyond each wall side of the inner one, and the inner one must hold every room: else no
    ratio."""
    true = straight.ratio(story(upper_story(rect(-0.5, -0.5, 60.5, 28.5))))
    assert true[2] < 0.5, true[2]
    inside = story(upper_story(rect(0, 0, 60, 28)))
    assert straight.remoteness(inside).length / straight.diagonal(inside).length > 0.5      # its own: over half
    with pytest.raises(Stop) as stop:
        straight.ratio(inside)
    assert stop.value.key == "outline_not_outer" and "3.5 in" in stop.value.reason
    # the inner outline drawn inside the rooms too (both a wall short): the rooms outside it
    d = upper_story(rect(0, 0, 60, 28))
    d["story_outlines"][0]["inner"] = [list(p) for p in rect(0.5, 0.5, 59.5, 27.5)]
    with pytest.raises(Stop) as stop:
        straight.ratio(story(d))
    assert stop.value.key == "outline_short", stop.value.reason
    # two rooms of one name outside the outlines: named once
    d = upper_story(rect(0, 0, 60, 28))
    d["rooms"][1]["name"] = d["rooms"][2]["name"] = "Stair"
    d["story_outlines"][0]["inner"] = [list(p) for p in rect(0.5, 0.5, 59.5, 27.5)]
    with pytest.raises(Stop) as stop:
        straight.ratio(story(d))
    assert stop.value.reason.count("Stair") == 1, stop.value.reason
    # an inner outline that can't be read: that reason, not "drawn at the inside faces"
    d = upper_story(rect(-0.5, -0.5, 60.5, 28.5))
    d["story_outlines"][0]["inner"] = [[0, 0], [1, 0]]
    with pytest.raises(Stop) as stop:
        straight.ratio(story(d))
    assert stop.value.key == "outline_needed", stop.value.reason
    # one long side only drawn at its inside face: refused too
    d = upper_story(rect(-0.5, -0.5, 60.5, 28.5))
    d["story_outlines"][0]["outer"] = [list(p) for p in rect(-0.5, -0.5, 60.5, 28)]
    with pytest.raises(Stop) as stop:
        straight.ratio(story(d))
    assert stop.value.key == "outline_not_outer", stop.value.reason
    # a wall's end kept where it is, as Revit's reader does where two walls in line stand apart (a step up to 0.64 ft
    # in the Children's Odyssey's ring): its short side brings the faces together, never a refusal (cold review)
    for step in (0.1, 0.3, 0.64):
        d = upper_story(rect(-0.5, -0.5, 60.5, 28.5))
        d["story_outlines"][0]["outer"] = [[-0.5, -0.5], [60.5, -0.5], [60.5, 28.5], [30, 28.5], [30, 28.5 + step],
                                           [-0.5, 28.5 + step]]
        d["story_outlines"][0]["inner"] = [[0, 0], [60, 0], [60, 28], [30, 28], [30, 28 + step], [0, 28 + step]]
        assert straight.ratio(story(d))[2] > 0, step
    # walls 4 in thick, drawn so (the outer outline 4 in outside the inner one): taken
    assert straight.ratio(story(upper_story(rect(-1 / 3, -1 / 3, 60 + 1 / 3, 28 + 1 / 3))))[2] > 0


# --- test 9: storage on the line -----------------------------------------------------------------------------------

def storage_story(storage_depth=24.5):
    """Inside the exterior walls 0 to 100 by 0 to 50 (5000 sf; outer faces -0.5 to 100.5 by -0.5 to 50.5, 5151 sf).
    A storage room 0 to 20 by 0 to `storage_depth` in the south-west corner; day-care rooms 20.5 to 100 by 0 to 50
    and 0 to 20 by (storage_depth + 0.5) to 50; walls 6 in."""
    s = storage_depth
    return outlined(description([room("s", rect(0, 0, 20, s), use="accessory_storage"),
                                 room("d1", rect(20.5, 0, 100, 50), use="day_care"),
                                 room("d2", rect(0, s + 0.5, 20, 50), use="day_care")],
                                [door("a", (-0.25, 40), (0, 1), ("d2", "outside"), exit_id="A")]),
                    rect(-0.5, -0.5, 100.5, 50.5), rect(0, 0, 100, 50))


USES = {"s": "accessory_storage", "d1": "day_care", "d2": "day_care"}


def test_9_the_story_area_two_readings():
    got = areas.building_area(story(storage_story()))
    assert [(r.answer, r.value / SF) for r in got] == [("inside", 5000.0), ("outer_faces", 101 * 51)]


def test_9_storage_under_10_percent_inside_its_walls_over_it_to_their_outer_faces():
    """Inside: 20 x 24.5 = 490 sf (under 500, 10 percent of 5000, and 515.1 of 5151). To the outer faces: the room
    grown by the story's thickest wall (the exterior walls' corners, sqrt(0.5^2 + 0.5^2) = 0.7071 ft from the inner
    outline), 24.5 + 0.7071 = 25.2071 north and 20.7071 east, clipped to the outer outline less the other rooms:
    -0.5 to 20.5 by -0.5 to 25 (535.5 sf), and three wall stubs past the junctions, each 0.5 by 0.2071 (0.1036 sf):
    x -0.5 to 0 and 20 to 20.5 for y 25 to 25.2071, and x 20.5 to 20.7071 for y -0.5 to 0 (the exterior wall below
    the east room): 535.811 sf, over both 500 and 515.1. So two of the four pairs pass and two fail."""
    inside, outer = areas.accessory_area(story(storage_story()), USES)
    assert inside.value / SF == pytest.approx(490.0, abs=1e-9)
    assert outer.value / SF == pytest.approx(535.5 + 3 * 0.5 * (math.sqrt(0.5) - 0.5), abs=1e-6)
    story_area = [r.value / SF for r in areas.building_area(story(storage_story()))]
    outcomes = {(a.answer, b): a.value / SF <= 0.10 * b for a in (inside, outer) for b in story_area}
    assert sorted(outcomes.values()) == [False, False, True, True]          # needs review: neither all nor none


def test_9_storage_over_10_percent_even_inside_its_walls_and_of_the_outer_area_fails_every_pair():
    inside, outer = areas.accessory_area(story(storage_story(26)), USES)
    assert inside.value / SF == pytest.approx(520.0, abs=1e-9)               # 20 x 26 > 515.1
    assert all(a.value / SF > 0.10 * b for a in (inside, outer) for b in (5000, 5151))


def test_the_day_care_net_area_is_the_day_care_rooms_inside_their_walls():
    # 79.5 x 50 + 20 x 25 = 3975 + 500 = 4475 sf
    assert areas.day_care_net_area(story(storage_story()), USES) / SF == pytest.approx(4475.0, abs=1e-9)
    # with the north-west room a corridor (not day care, Table 1004.1.1's "net" leaves corridors out): 3975
    assert areas.day_care_net_area(story(storage_story()), USES | {"d2": "corridor"}) / SF == pytest.approx(3975.0)


@pytest.mark.parametrize("change, key", [
    (lambda d, u: u.update(d2=None), "area_no_use"),
    (lambda d, u: d.setdefault("unknown_spaces", []).append({"id": "q", "name": "Q", "level": "L1"}),
     "area_unknown_space"),
    (lambda d, u: d["rooms"][2].update(floor=[list(p) for p in rect(0, 20, 20, 50)]), "area_rooms_overlap"),
    (lambda d, u: d["rooms"][2].pop("floor"), "area_room_not_read"),
])
def test_an_area_that_counts_uses_needs_review_while_a_use_isnt_known(change, key):
    from model_measurement.routes.floor import read
    d, u = storage_story(), dict(USES)
    change(d, u)
    s = read(d).stories["L1"]
    for measure in (areas.day_care_net_area, areas.accessory_area):
        with pytest.raises(Stop) as stop:
            measure(s, u, ["Q"] if key == "area_unknown_space" else [])
        assert stop.value.key == key
