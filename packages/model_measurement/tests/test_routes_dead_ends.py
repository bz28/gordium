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
    length, width = c.longest(WITHOUT)
    assert ft(length) == 20.0 and ft(width) == 8.0                    # 16 + 4, exactly
    assert c.longest(WITH) == c.longest(WITHOUT)                            # no door in it: one reading
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
    assert [ft(v) for v in only(measure(d)).longest(WITHOUT)] == [2.0, 8.0]


def test_3_a_sixteenth_longer_is_longer():
    length, _ = only(measure(branch(beyond=16 + 1 / 192))).longest(WITHOUT)
    assert ft(length) == pytest.approx(20 + 1 / 192, abs=1e-9)        # 20'-0 1/16"


def test_3_ten_ft_wide_the_dead_end_is_25_ft_or_just_under():
    assert [ft(v) for v in only(measure(branch(10, 20))).longest(WITHOUT)] == [25.0, 10.0]
    length, width = only(measure(branch(10, 20 - 1 / 192))).longest(WITHOUT)
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
    length, width = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(20.0, abs=1e-9) and ft(width) == pytest.approx(8.0, abs=1e-9)


def test_a_recess_shallower_than_12_in_is_ignored():
    c = only(measure(branch(recess=True)))
    assert [ft(v) for v in c.longest(WITHOUT)] == [20.0, 8.0] and ft(c.width) == 8.0


def test_a_recess_in_a_dead_ends_end_wall_never_moves_its_closed_end():
    # an alcove 3 ft wide, 11 in deep, centred in the branch's end wall (x 22.5 to 25.5): filled to find the legs,
    # but the dead end runs to its back: 16 + 11/12 + 4 = 20.917 ft (review round 1: it was 20.0, a pass at 20 ft)
    d = branch()
    poly = [(0, 0), (60, 0), (60, 8), (28, 8), (28, 24), (25.5, 24), (25.5, 24 + 11 / 12), (22.5, 24 + 11 / 12),
            (22.5, 24), (20, 24), (20, 8), (0, 8)]
    d["rooms"][0]["floor"] = [list(p) for p in poly]
    length, width = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9) and ft(width) == 3.0     # the alcove's (round 3)
    # off centre (x 20.5 to 23.5, missing the centre line x = 24): the closed end is the farthest real floor across
    # the leg's whole width, so the same 20.917 ft (review round 2: it was 20.0)
    off = [(0, 0), (60, 0), (60, 8), (28, 8), (28, 24), (23.5, 24), (23.5, 24 + 11 / 12), (20.5, 24 + 11 / 12),
           (20.5, 24), (20, 24), (20, 8), (0, 8)]
    d["rooms"][0]["floor"] = [list(p) for p in off]
    length, _ = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9)
    # the same mirrored (the branch running south, its closed end at the leg's other end): the same figure
    d["rooms"][0]["floor"] = [[x, 8 - y] for x, y in reversed(poly)]
    length, _ = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9)


def test_an_obstruction_narrows_the_dead_ends_least_width():
    # a cabinet 1 ft deep along the branch's west wall: 10 - 1 = 9 ft clear; 2.5 x 9 = 22.5 < 24.995: no exception
    c = only(measure(branch(10, 20 - 1 / 192, cabinet=1)))
    length, width = c.longest(WITHOUT)
    assert ft(width) == pytest.approx(9.0, abs=1e-9) and ft(c.width) == pytest.approx(9.0, abs=1e-9)


def with_obstruction(desc, outline):
    desc["rooms"][0]["obstructions"] = [{"outline": [list(p) for p in outline], "kind": "furniture", "fixed": False}]
    return desc


def test_a_rotated_column_narrows_the_dead_end_at_its_widest():
    # review round 6, P0: a diamond column 4 ft across in a 14 ft branch leaves 10 ft at its widest, never the 12 ft
    # a cut midway between its corners finds; 29 ft against 2.5 x 10 = 25 fails the exception, against 30 it passed
    c = only(measure(with_obstruction(branch(14, 22), [(27, 23), (29, 25), (27, 27), (25, 25)])))
    length, width = c.longest(WITHOUT)
    assert ft(length) == pytest.approx(29.0, abs=1e-6)
    assert ft(width) == pytest.approx(10.0, abs=1e-6)


def test_a_slanted_cabinet_narrows_the_dead_end_at_its_deepest():
    # a triangle 5 ft deep off the 8 ft branch's west wall: 3 ft clear at its point, not the 5.5 ft midway
    c = only(measure(with_obstruction(branch(), [(20, 14), (25, 16), (20, 18)])))
    assert ft(c.longest(WITHOUT)[1]) == pytest.approx(3.0, abs=1e-6)


def test_a_hairline_between_a_cabinet_and_the_wall_is_no_floor():
    # review round 6, P3: a cabinet 1/32 in off the branch's west wall leaves 4 ft clear, not 4 ft 1/32 in
    c = only(measure(with_obstruction(branch(), rect(20 + 1 / 384, 14, 24, 18))))
    assert c.longest(WITHOUT)[1] == pytest.approx(48.0, abs=1e-6)
    assert c.width == pytest.approx(48.0, abs=1e-6)


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
    assert [ft(v) for v in got.longest(WITHOUT)] == [33.0, 8.0]


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
    assert ft(c.longest(WITHOUT)[0]) == 30.0                             # 26 + 4: the defined value
    assert ft(c.longest(WITH)[0]) == 5.0                                 # to the door, 5 ft from the end
    assert ft(c.longest(WITHOUT)[1]) == 8.0 and ft(c.longest(WITH)[1]) == 8.0


def test_8_a_door_into_a_room_with_no_other_way_out_ends_nothing():
    d = classroom_in_dead_end()
    d["doors"] = [x for x in d["doors"] if x["id"] != "kx"]
    c = only(measure(d))
    assert ft(c.longest(WITH)[0]) == 30.0 and ft(c.longest(WITHOUT)[0]) == 30.0


def test_8_a_room_whose_other_way_out_cant_be_reached_inside_it_ends_nothing():
    # casework right across the classroom at x 38 to 39: its exit C is beyond it, so no route from the door reaches C
    d = classroom_in_dead_end()
    d["rooms"][1]["obstructions"] = [{"outline": [list(p) for p in rect(38, 24, 39, 34)], "kind": "casework",
                                      "fixed": True}]
    c = only(measure(d))
    assert ft(c.longest(WITH)[0]) == 30.0


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
    assert [ft(v) for v in only(got, "m").longest(WITHOUT)] == [30.0, 8.0]
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
    assert [ft(v) for v in c.longest(WITHOUT)] == [30.0, 14.0]           # the longest, with its own width


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
    assert [ft(v) for v in only(measure(two_corridors_and_a_door()), "w").longest(WITHOUT)] == [20.0, 8.0]


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


def slot(width_ft):
    """Test 3's branch (8 ft wide, end wall 16 ft past the corridor) with a slot `width_ft` wide and 11 in deep in
    its end wall at x 23.75 onward."""
    d = branch()
    w = width_ft
    d["rooms"][0]["floor"] = [list(p) for p in [(0, 0), (60, 0), (60, 8), (28, 8), (28, 24), (23.75 + w, 24),
                                                (23.75 + w, 24 + 11 / 12), (23.75, 24 + 11 / 12), (23.75, 24),
                                                (20, 24), (20, 8), (0, 8)]]
    return d


def test_a_recess_that_lengthens_a_dead_end_counts_in_its_least_width():
    # a slot 0.5 ft wide: the dead end runs to its back, 20.917 ft, and its least width is the slot's, 0.5 ft
    # (exception 3: 20.917 < 2.5 x 0.5 = 1.25 is not met). Review round 3: it was the branch's 8 ft.
    length, width = only(measure(slot(0.5))).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9) and ft(width) == pytest.approx(0.5, abs=1e-9)


def test_a_hairline_sliver_in_the_end_wall_neither_lengthens_nor_narrows_a_dead_end():
    # 1/32 in wide (under the 1/16 in tolerance): 20 ft by 8 ft, as with no slot
    length, width = only(measure(slot(1 / 384))).longest(WITHOUT)
    assert ft(length) == pytest.approx(20.0, abs=1e-9) and ft(width) == 8.0


def end_wall(*notches):
    """Test 3's branch with these notches in its end wall (y 24): each (x0, x1, depth ft), a notch with steps given
    as [(x0, x1, depth), ...] nested, outermost first."""
    d = branch()
    top = [(28, 24)]
    for steps in notches:
        pts = []
        for x0, x1, depth in steps:
            pts.append((x0, x1, depth))
        # walk east to west along the end wall, into each step and back out
        (ox0, ox1, od) = pts[0]
        seq = [(ox1, 24), (ox1, 24 + od)]
        for x0, x1, depth in pts[1:]:
            seq += [(x1, 24 + od), (x1, 24 + depth), (x0, 24 + depth), (x0, 24 + od)]
        seq += [(ox0, 24 + od), (ox0, 24)]
        top += seq
    top += [(20, 24)]
    d["rooms"][0]["floor"] = [list(p) for p in [(0, 0), (60, 0), (60, 8), (28, 8)] + top + [(20, 8), (0, 8)]]
    return d


def test_a_stepped_recess_takes_its_narrowest_section():
    # a mouth 3 ft wide, 4 in deep (x 22.5 to 25.5), and in it a slot 0.5 ft wide (x 23.75 to 24.25) to 11 in: the
    # dead end runs to the slot's back, 20.917 ft, and its least width is the slot's 0.5 ft, never the mouth's 3 ft
    d = end_wall([(22.5, 25.5, 4 / 12), (23.75, 24.25, 11 / 12)])
    length, width = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9) and ft(width) == pytest.approx(0.5, abs=1e-9)


def test_an_alcove_beside_a_separate_narrow_slot_takes_the_alcoves_width():
    # an alcove 3 ft wide, 11 in deep (x 20.5 to 23.5) and a separate slot 0.5 ft wide, 4 in deep (x 25 to 25.5):
    # 20.917 ft long; each slice adds the clear floor across it, so the least width is the alcove's 3 ft (round 5:
    # one width function over the clear floor, no longer the separate slot's 0.5)
    d = end_wall([(25, 25.5, 4 / 12)], [(20.5, 23.5, 11 / 12)])
    length, width = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9) and ft(width) == pytest.approx(3.0, abs=1e-9)


def alcove_10_ft(blocker=None, hole=None):
    """A corridor 0 to 60 by 0 to 10, exits at both ends; a branch 10 ft wide (x 20 to 30) whose end wall is 20 ft
    past the corridor's wall (y 30), and in it an alcove 10 ft wide... the whole branch end: an alcove 10 ft wide,
    11 in deep (y 30 to 30.917). `blocker` / `hole`: casework / a column (x0, y0, x1, y1) in the alcove."""
    poly = [(0, 0), (60, 0), (60, 10), (30, 10), (30, 30), (29, 30), (29, 30 + 11 / 12), (21, 30 + 11 / 12), (21, 30),
            (20, 30), (20, 10), (0, 10)]
    return description([room("c", poly, obstructions=[rect(*blocker)] if blocker else (),
                             holes=[rect(*hole)] if hole else ())],
                       [door("a", (-0.25, 5), (0, 1), ("c", "outside"), exit_id="A"),
                        door("b", (60.25, 5), (0, 1), ("c", "outside"), exit_id="B")])


@pytest.mark.parametrize("kind", ["blocker", "hole"])
def test_casework_or_a_column_in_an_end_alcove_narrows_the_dead_end(kind):
    # the alcove is 8 ft wide (x 21 to 29); casework or a column x 22 to 29 leaves 1 ft clear in it: the least width
    # is 1 ft (the dead end, 20 + 11/12 + 5 = 25.917 ft, then needs width over 10.37 for exception 3: not met)
    got = only(measure(alcove_10_ft(**{kind: (22, 30, 29, 30 + 11 / 12)})))
    length, width = got.longest(WITHOUT)
    assert ft(length) == pytest.approx(20 + 11 / 12 + 5, abs=1e-9)           # an obstruction never shortens it
    assert ft(width) == pytest.approx(1.0, abs=1e-9)


def test_walls_narrowing_an_end_alcove_narrow_the_dead_end():
    # the alcove walled down to 1 ft (x 21 to 22): its least width 1 ft
    d = alcove_10_ft()
    d["rooms"][0]["floor"] = [list(p) for p in [(0, 0), (60, 0), (60, 10), (30, 10), (30, 30), (22, 30),
                                                (22, 30 + 11 / 12), (21, 30 + 11 / 12), (21, 30), (20, 30), (20, 10),
                                                (0, 10)]]
    length, width = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(20 + 11 / 12 + 5, abs=1e-9) and ft(width) == pytest.approx(1.0, abs=1e-9)


def test_an_obstruction_in_the_leg_itself_narrows_the_dead_end():
    # casework 2 ft deep along the branch's west wall at y 15 to 18: 10 - 2 = 8 ft clear there
    length, width = only(measure(alcove_10_ft(blocker=(20, 15, 22, 18)))).longest(WITHOUT)
    assert ft(width) == pytest.approx(8.0, abs=1e-9)


def test_a_deep_mouth_with_a_short_slot_still_takes_the_slots_width():
    # a mouth 3 ft wide, 8 in deep, a slot 0.5 ft wide to 11 in in it: sliced at every corner, the slot's 0.5 ft
    d = end_wall([(22.5, 25.5, 8 / 12), (23.75, 24.25, 11 / 12)])
    length, width = only(measure(d)).longest(WITHOUT)
    assert ft(length) == pytest.approx(16 + 11 / 12 + 4, abs=1e-9) and ft(width) == pytest.approx(0.5, abs=1e-9)
