"""Decision 6's dead ends and corridor widths (routes/dead_ends.py), on the route note's tests 3, 8, 11, 16 and 17
(docs/decisions/2026-11-20_route_measurement.md). Every figure is a literal from the note, or worked by hand in the
comment beside it; none is taken from the code under test. Feet in the layouts; the code works in inches."""

import math
import sys
from pathlib import Path

import pytest

from model_measurement.routes import dead_ends
from model_measurement.routes.dead_ends import WITH, WITHOUT, corridors
from model_measurement.routes.paths import StoryRoutes

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import FT, description, door, l_corridor, rect, room, story  # noqa: E402


def measure(desc, uses=None):
    s = story(desc)
    uses = uses or {r["id"]: r.get("use") for r in desc["rooms"]}
    return corridors(s, uses, StoryRoutes(s) if not s.stops else None)


def branch(width=8.0, beyond=16.0, recess=False, cabinet=None):
    """Test 3: a corridor `width` wide, 0 to 60, an exit at each end; a branch as wide at x 20 to 20 + width, its end
    wall `beyond` past the corridor's wall. `recess`: a door's recess 6 in deep, 4 ft wide, in the corridor's south
    wall. `cabinet`: (depth) a cabinet along the branch's west wall."""
    w = width
    south = [(0, 0), (40, 0), (40, -0.5), (44, -0.5), (44, 0), (60, 0)] if recess else [(0, 0), (60, 0)]
    poly = south + [(60, w), (20 + w, w), (20 + w, w + beyond), (20, w + beyond), (20, w), (0, w)]
    obs = [rect(20, w + 2, 20 + cabinet, w + 6)] if cabinet else []
    return description([room("c", poly, obstructions=obs)],
                       [door("a", (-0.25, w / 2), (0, 1), ("c", "outside"), exit_id="A"),
                        door("b", (60.25, w / 2), (0, 1), ("c", "outside"), exit_id="B")])


def ft(x):
    return x / FT


def only(got, rid="c"):
    c = got[rid]
    assert c.stop is None and c.width_stop is None, (c.stop, c.width_stop)
    return c


# --- test 3: at the limit ----------------------------------------------------------------------------------------

def test_3_a_branch_8_ft_wide_16_ft_deep_is_a_dead_end_of_20_ft_exactly():
    c = only(measure(branch()))
    length, width = c.pair(WITHOUT)
    assert ft(length) == 20.0 and ft(width) == 8.0                    # 16 + 4, exactly
    assert c.pair(WITH) == c.pair(WITHOUT)                            # no door in it: one reading
    assert ft(c.width) == 8.0
    assert len(c.dead_ends) == 1                                      # the branch's centre line ends at the crossing


def test_two_ways_to_one_exit_never_end_a_dead_end():
    d = branch()
    d["doors"][1]["exit_id"] = "A"                                   # both ends of the corridor: one exit
    got = measure(d)["c"]
    assert got.stop is not None and "no point of the corridors" in got.stop


def test_an_exit_door_in_the_corridor_itself_ends_a_dead_end():
    # the east end closed at x = 60; exit B in the south wall centred at x = 58: the dead end is the 2 ft beyond it
    d = description([room("c", rect(0, 0, 60, 8))],
                    [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"),
                     door("b", (58, -0.25), (1, 0), ("c", "outside"), exit_id="B")])
    assert [ft(v) for v in only(measure(d)).pair(WITHOUT)] == [2.0, 8.0]


def test_3_a_sixteenth_longer_is_longer():
    length, _ = only(measure(branch(beyond=16 + 1 / 192))).pair(WITHOUT)
    assert ft(length) == pytest.approx(20 + 1 / 192, abs=1e-9)        # 20'-0 1/16"


def test_3_ten_ft_wide_the_dead_end_is_25_ft_or_just_under():
    assert [ft(v) for v in only(measure(branch(10, 20))).pair(WITHOUT)] == [25.0, 10.0]
    length, width = only(measure(branch(10, 20 - 1 / 192))).pair(WITHOUT)
    assert ft(length) == pytest.approx(25 - 1 / 192, abs=1e-9) and ft(width) == 10.0     # 24'-11 15/16"


def test_3_turned_30_degrees_the_figures_are_the_same():
    d = branch()
    a = math.radians(30)

    def turn(p):
        return [p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a)]

    d["rooms"][0]["floor"] = [turn(p) for p in d["rooms"][0]["floor"]]
    for x in d["doors"]:
        x["plan"]["centre"] = turn(x["plan"]["centre"])
        x["plan"]["along"] = turn(x["plan"]["along"])
    length, width = only(measure(d)).pair(WITHOUT)
    assert ft(length) == pytest.approx(20.0, abs=1e-9) and ft(width) == pytest.approx(8.0, abs=1e-9)


def test_a_recess_shallower_than_12_in_is_ignored():
    c = only(measure(branch(recess=True)))
    assert [ft(v) for v in c.pair(WITHOUT)] == [20.0, 8.0] and ft(c.width) == 8.0


def test_an_obstruction_narrows_the_dead_ends_least_width():
    # a cabinet 1 ft deep along the branch's west wall: 10 - 1 = 9 ft clear; 2.5 x 9 = 22.5 < 24.995: no exception
    c = only(measure(branch(10, 20 - 1 / 192, cabinet=1)))
    length, width = c.pair(WITHOUT)
    assert ft(width) == pytest.approx(9.0, abs=1e-9) and ft(c.width) == pytest.approx(9.0, abs=1e-9)


# --- test 11: a dead end that branches ---------------------------------------------------------------------------

def test_11_a_dead_end_that_branches_runs_on_past_the_crossing_whose_other_way_is_closed():
    """Corridor 0 to 60 by 0 to 8, an exit each end; a stem x 26 to 34 reaching 10 ft past its wall; at its end a
    leg 8 ft wide (y 18 to 26) running 15 ft each side of x = 30, both ends closed: 15 + (4 + 10 + 4) = 33."""
    poly = [(0, 0), (60, 0), (60, 8), (34, 8), (34, 18), (45, 18), (45, 26), (15, 26), (15, 18), (26, 18), (26, 8),
            (0, 8)]
    got = only(measure(description([room("c", poly)],
                                   [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"),
                                    door("b", (60.25, 4), (0, 1), ("c", "outside"), exit_id="B")])))
    assert sorted(ft(d.length[WITHOUT]) for d in got.dead_ends) == [33.0, 33.0]
    assert [ft(v) for v in got.pair(WITHOUT)] == [33.0, 8.0]


# --- test 8: a classroom door in a dead end (open question 7) ------------------------------------------------------

def classroom_in_dead_end():
    """A branch 8 ft wide (x 20 to 28), its end wall 26 ft beyond an 8-ft corridor with an exit at each end; a
    classroom (x 28.5 to 48.5, y 24 to 34) with its door 5 ft from the end (centre (28.25, 29)) and its own exterior
    exit C (centre (48.75, 29))."""
    poly = [(0, 0), (60, 0), (60, 8), (28, 8), (28, 34), (20, 34), (20, 8), (0, 8)]
    return description([room("c", poly), room("k", rect(28.5, 24, 48.5, 34), use="day_care")],
                       [door("a", (-0.25, 4), (0, 1), ("c", "outside"), exit_id="A"),
                        door("b", (60.25, 4), (0, 1), ("c", "outside"), exit_id="B"),
                        door("kd", (28.25, 29), (0, 1), ("c", "k")),
                        door("kx", (48.75, 29), (0, 1), ("k", "outside"), exit_id="C")])


def test_8_a_door_into_a_room_with_another_way_out_gives_two_readings():
    c = only(measure(classroom_in_dead_end()))
    assert ft(c.pair(WITHOUT)[0]) == 30.0                             # 26 + 4: the defined value
    assert ft(c.pair(WITH)[0]) == 5.0                                 # to the door, 5 ft from the end
    assert ft(c.pair(WITHOUT)[1]) == 8.0 and ft(c.pair(WITH)[1]) == 8.0


def test_8_a_door_into_a_room_with_no_other_way_out_ends_nothing():
    d = classroom_in_dead_end()
    d["doors"] = [x for x in d["doors"] if x["id"] != "kx"]
    c = only(measure(d))
    assert ft(c.pair(WITH)[0]) == 30.0 and ft(c.pair(WITHOUT)[0]) == 30.0


def test_8_a_room_whose_other_way_out_cant_be_reached_inside_it_ends_nothing():
    # casework right across the classroom at x 38 to 39: its exit C is beyond it, so no route from the door reaches C
    d = classroom_in_dead_end()
    d["rooms"][1]["obstructions"] = [{"outline": [list(p) for p in rect(38, 24, 39, 34)], "kind": "casework",
                                      "fixed": True}]
    c = only(measure(d))
    assert ft(c.pair(WITH)[0]) == 30.0


# --- test 16: a locked corridor ------------------------------------------------------------------------------------

def locked_side_corridor():
    """A corridor 8 ft wide from a closed end at x = 0; 15 ft along, a side corridor (x 11 to 19, y 8 to 20) with
    `lockable: true` joined by a passage, exit B at its end; the corridor goes on to a crossing (x 26 to 34, y -30 to
    38) whose centre line is 30 ft from the closed end, exits A (north) and C (south)."""
    poly = [(0, 0), (26, 0), (26, -30), (34, -30), (34, 38), (26, 38), (26, 8), (0, 8)]
    return description([room("m", poly), room("s", rect(11, 8, 19, 20), lockable=True)],
                       [door("a", (30, 38.25), (1, 0), ("m", "outside"), exit_id="A"),
                        door("c", (30, -30.25), (1, 0), ("m", "outside"), exit_id="C"),
                        door("b", (15, 20.25), (1, 0), ("s", "outside"), exit_id="B")],
                       passages=[(("m", "s"), [(11, 8), (19, 8)])])


def test_16_a_locked_side_corridor_never_ends_a_dead_end():
    got = measure(locked_side_corridor())
    assert [ft(v) for v in only(got, "m").pair(WITHOUT)] == [30.0, 8.0]
    assert got["s"].stop is not None and "can't be crossed" in got["s"].stop
    assert ft(got["s"].width) == 8.0                                  # its width is still its own


# --- test 17: an H-plan corridor ----------------------------------------------------------------------------------

def h_plan():
    """Left leg 14 ft wide (x 0 to 14, y 14 to 70), right leg 8 ft wide (x 60 to 68, y 22 to 70), a bar 8 ft wide
    (y 40 to 48) between them; an exit at the top of each leg. Dead ends: the left leg's foot, 44 - 14 = 30 ft by
    14 ft; the right's, 44 - 22 = 22 ft by 8 ft."""
    poly = [(0, 14), (14, 14), (14, 40), (60, 40), (60, 22), (68, 22), (68, 70), (60, 70), (60, 48), (14, 48),
            (14, 70), (0, 70)]
    return description([room("c", poly)],
                       [door("a", (7, 70.25), (1, 0), ("c", "outside"), exit_id="A"),
                        door("b", (64, 70.25), (1, 0), ("c", "outside"), exit_id="B")])


def test_17_each_dead_end_has_its_own_length_and_least_width_and_the_corridor_the_cautious_pair():
    c = only(measure(h_plan()))
    pairs = sorted((ft(d.length[WITHOUT]), ft(d.width[WITHOUT])) for d in c.dead_ends)
    assert pairs == [(22.0, 8.0), (30.0, 14.0)]                       # 30 < 2.5 x 14 = 35; 22 > 20, not < 20
    assert [ft(v) for v in c.pair(WITHOUT)] == [30.0, 8.0]            # until `dead_end` exists: fails


# --- doors between corridors, and what needs review ----------------------------------------------------------------

def two_corridors_and_a_door():
    """Test 3's corridor cut in two by a door at x = 30 (rooms x 0 to 29.75 and 30.25 to 60), its branch on the
    west one: the dead end reaches exit B only through the door."""
    poly = [(0, 0), (29.75, 0), (29.75, 8), (28, 8), (28, 24), (20, 24), (20, 8), (0, 8)]
    return description([room("w", poly), room("e", rect(30.25, 0, 60, 8))],
                       [door("a", (-0.25, 4), (0, 1), ("w", "outside"), exit_id="A"),
                        door("b", (60.25, 4), (0, 1), ("e", "outside"), exit_id="B"),
                        door("x", (30, 4), (0, 1), ("w", "e"))])


def test_a_door_between_two_corridors_carries_the_way_across():
    assert [ft(v) for v in only(measure(two_corridors_and_a_door()), "w").pair(WITHOUT)] == [20.0, 8.0]


def test_one_exit_along_the_corridors_leaves_a_dead_end_unbounded():
    got = measure(l_corridor())["c"]
    assert got.stop is not None and "no point of the corridors" in got.stop
    assert ft(got.width) == 6.0


@pytest.mark.parametrize("poly, why", [
    ([(0, 0), (60, 0), (60, 8), (10, 8), (0, 4)], "right angles"),                     # a slanted wall
    ([(0, 0), (60, 0), (60, 10), (30, 10), (30, 8), (0, 8)], "side by side"),            # a widening
    ([(0, 0), (8, 0), (8, 8), (0, 8)], "runs neither way"),                              # a square
])
def test_a_corridor_not_made_of_straight_legs_at_right_angles_needs_review(poly, why):
    d = description([room("c", poly)], [door("a", (-0.25, 2), (0, 1), ("c", "outside"), exit_id="A")])
    got = measure(d)["c"]
    assert why in got.stop and got.stop == got.width_stop and got.dead_ends == []


def test_a_story_with_anything_to_review_measures_no_corridor():
    d = branch()
    d["doors"][0]["plan"]["clear_width"] = 1.5                       # a door under 24 in
    got = corridors(story(d), {"c": "corridor"}, None)["c"]
    assert got.stop and got.width_stop and got.width is None


def test_a_door_that_cant_be_put_on_the_centre_lines_needs_review(monkeypatch):
    monkeypatch.setattr(dead_ends, "_attach", lambda *a, **k: None)
    got = measure(branch())["c"]
    assert got.stop is not None and "isn't on any of the corridor's legs" in got.stop
