"""Decision 1a as amended 2026-11-21 (docs/decisions/2026-11-20_route_measurement.md, test 20; Gordium's reading,
open question 11): a closet, storeroom or toilet that opens only into the room it serves is part of that room, so
its route leaves through it, never across any other end-only room and never through a room that can be locked.
Every figure is worked by hand in the comment beside it, never taken from the code under test. Feet in the layouts;
the route code works in inches. Tolerance 1e-3 ft."""

import sys
from pathlib import Path

import pytest

from model_measurement.routes import measure
from model_measurement.routes.floor import read
from model_measurement.routes.stops import Stop

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import FT, at, description, door, rect, room, routes, story  # noqa: E402

TOL = 1e-3
CORRIDOR = room("c", rect(0, 0, 40, 6))
EXIT = door("x", (15, -0.25), (1, 0), ("c", "outside"), exit_id="A")       # in the corridor's south wall


def kitchen_closet(kitchen=None, closet_use="closet", more_rooms=(), more_doors=()):
    """Test 20: a corridor 0 to 40 by 0 to 6, its exit centred at (15, -0.25); a kitchen 10 to 20 by 6.5 to 16.5,
    its door to the corridor centred at (15, 6.25); a closet 10 to 14 by 17 to 20 whose only door, centred at
    (12, 16.75), opens into the kitchen."""
    k = room("k", rect(10, 6.5, 20, 16.5), use="kitchen", lockable=False)
    k.update(kitchen or {})
    return description([CORRIDOR, k, room("cl", rect(10, 17, 14, 20), use=closet_use, lockable=True), *more_rooms],
                       [EXIT, door("kc", (15, 6.25), (1, 0), ("k", "c")),
                        door("clk", (12, 16.75), (1, 0), ("cl", "k")), *more_doors])


def test_20_a_closet_off_a_kitchen_leaves_through_the_kitchen():
    # by hand: from (12, 18) straight to the closet's door centre (12, 16.75): 1.25; straight across the kitchen to
    # its door centre (15, 6.25): sqrt(3^2 + 10.5^2) = 10.9202 (1.37 ft off the nearest jamb, (13.5, 16.5) and
    # (13.5, 6.5): clear of every ring); straight across the corridor to the exit (15, -0.25): 6.5. 18.670 ft.
    r = routes(kitchen_closet())
    assert r.story.served_by == {"cl": "k"}
    got = r.route(at(12, 18))
    assert got.feet == pytest.approx(18.670, abs=TOL)
    assert got.doors == ("clk", "kc", "x")
    assert r.travel(at(12, 18)) / FT == pytest.approx(18.670, abs=TOL)         # the fast way agrees


def test_20_the_closets_door_is_its_exit_access_door_and_the_figures_say_the_reading():
    m = measure(kitchen_closet())
    sp, closet = m["parts"]["story"][0], next(p for p in m["parts"]["space"] if p["id"] == "cl")
    assert closet["measures"]["space_exit_count"] == 1 and closet["more"]["exit_access"] == ["clk"]
    # by hand: from the closet's door centre across the kitchen and the corridor: 10.9202 + 6.5 = 17.420, the
    # story's greatest from a room's exit access door (the kitchen's own door gives 6.5)
    assert sp["measures"]["egress_travel_from_room_door"] == pytest.approx(17.420, abs=TOL)
    for part, measures in ((sp, ("egress_travel_distance", "common_path_of_travel", "egress_travel_from_room_door")),
                           (closet, ("space_exit_count", "space_common_path"))):
        for name in measures:
            assert name in part["measures"], (name, part["not_measured"].get(name))
            assert "Gordium's reading" in part["confirm"][name] and "cl through k" in part["confirm"][name]
    kitchen = next(p for p in m["parts"]["space"] if p["id"] == "k")
    assert "confirm" not in kitchen                                               # its own figures stand on the law


def test_no_confirm_where_no_room_is_served():
    d = kitchen_closet()
    d["doors"] = [x for x in d["doors"] if x["id"] != "clk"]
    d["rooms"] = [x for x in d["rooms"] if x["id"] != "cl"]
    assert "confirm" not in measure(d)["parts"]["story"][0]


@pytest.mark.parametrize("kitchen, words", [({"lockable": True}, "can be locked (`lockable: true`)"),
                                            ({"lockable": None}, "doesn't say whether it can be locked"),
                                            ({"use": None}, "doesn't give its `use`")])
def test_20_a_kitchen_that_can_be_locked_or_isnt_said_still_blocks(kitchen, words):
    r = routes(kitchen_closet(kitchen))
    assert r.story.served_by == {}
    with pytest.raises(Stop) as stop:
        r.route(at(12, 18))
    assert stop.value.key == "no_route_host_blocked"
    assert "opens only into k" in stop.value.reason and words in stop.value.reason
    with pytest.raises(Stop) as stop:
        r.travel(at(12, 18))
    assert stop.value.key == "no_route_host_blocked"


def test_20_a_closet_off_a_classroom_behind_a_kitchen_never_crosses_the_kitchen():
    """The classroom (day care, not marked pass_through) opens only into the kitchen; the closet opens only into the
    classroom. The closet is part of the classroom, but the classroom's only way out crosses the kitchen: no route
    for either."""
    d = description([CORRIDOR, room("k", rect(10, 6.5, 20, 16.5), use="kitchen", lockable=False),
                     room("cr", rect(10, 17, 20, 27), use="day_care", lockable=False),
                     room("cl", rect(13, 27.5, 17, 30.5), use="closet", lockable=True)],
                    [EXIT, door("kc", (15, 6.25), (1, 0), ("k", "c")), door("crk", (15, 16.75), (1, 0), ("cr", "k")),
                     door("clcr", (15, 27.25), (1, 0), ("cl", "cr"))])
    r = routes(d)
    assert r.story.served_by == {"cl": "cr"}                    # a classroom is never taken as part of the kitchen
    with pytest.raises(Stop) as stop:
        r.route(at(15, 29))
    assert stop.value.key == "no_route_via_host" and "no route leaves cr" in stop.value.reason
    with pytest.raises(Stop) as stop:
        r.route(at(15, 20))
    assert stop.value.key == "no_route"


def storeroom_chain(middle_lockable=False):
    """A storeroom 14 (10 to 20 by 6.5 to 16.5, its door to the corridor centred at (15, 6.25)); storeroom 13 above
    it (10 to 20 by 17 to 27), its only door centred at (15, 16.75) into 14; a closet (13 to 17 by 27.5 to 30.5)
    whose only door, centred at (15, 27.25), opens into 13."""
    return description([CORRIDOR, room("s14", rect(10, 6.5, 20, 16.5), use="accessory_storage", lockable=False),
                        room("s13", rect(10, 17, 20, 27), use="accessory_storage", lockable=middle_lockable),
                        room("cl", rect(13, 27.5, 17, 30.5), use="closet", lockable=True)],
                       [EXIT, door("s14c", (15, 6.25), (1, 0), ("s14", "c")),
                        door("s13", (15, 16.75), (1, 0), ("s13", "s14")),
                        door("cls13", (15, 27.25), (1, 0), ("cl", "s13"))])


def test_20_a_storeroom_chain_leaves_through_each_room_it_opens_into():
    # by hand, all along x = 15 (every jamb 1.5 ft off the line): from (15, 26) to s13's door 9.25, across s14 to its
    # door 10.5, across the corridor 6.5: 26.25; from the closet's (15, 30): 2.75 more to s13's door... 2.75 + 10.5 +
    # 10.5 + 6.5 = 30.25
    r = routes(storeroom_chain())
    assert r.story.served_by == {"s13": "s14", "cl": "s13"}
    assert r.route(at(15, 26)).feet == pytest.approx(26.25, abs=TOL)
    got = r.route(at(15, 30))
    assert got.feet == pytest.approx(30.25, abs=TOL) and got.doors == ("cls13", "s13", "s14c", "x")
    assert r.travel(at(15, 30)) / FT == pytest.approx(30.25, abs=TOL)


def test_20_a_storeroom_that_can_be_locked_blocks_the_closet_off_it_but_keeps_its_own_route():
    r = routes(storeroom_chain(middle_lockable=True))
    assert r.story.served_by == {"s13": "s14"}                  # a start in a lockable room is allowed (decision 1a)
    assert r.route(at(15, 26)).feet == pytest.approx(26.25, abs=TOL)
    with pytest.raises(Stop) as stop:
        r.route(at(15, 30))
    assert stop.value.key == "no_route_host_blocked" and "opens only into s13, which can be locked" in stop.value.reason


def test_20_a_closet_with_a_second_door_of_its_own_is_never_routed_through_the_kitchen():
    """The closet 20.5 to 24 by 6.5 to 10 opens into the kitchen (door centred at (20.25, 8.25)) and onto the
    corridor (door centred at (22.25, 6.25)): it has a way out of its own."""
    d = description([CORRIDOR, room("k", rect(10, 6.5, 20, 16.5), use="kitchen", lockable=False),
                     room("cl", rect(20.5, 6.5, 24, 10), use="closet", lockable=True)],
                    [EXIT, door("kc", (15, 6.25), (1, 0), ("k", "c")), door("clk", (20.25, 8.25), (0, 1), ("cl", "k")),
                     door("clc", (22.25, 6.25), (1, 0), ("cl", "c"))])
    r = routes(d)
    assert r.story.served_by == {} and r.story.not_served == {}
    assert r.route(at(23, 9)).doors == ("clc", "x")


@pytest.mark.parametrize("use", ["other", "kitchen", "workroom", "day_care"])
def test_20_only_a_closet_storeroom_or_toilet_is_taken_as_part_of_the_room_it_opens_into(use):
    """An electrical room (`other`), a kitchen, a workroom or a classroom opening only into the kitchen is not the
    kitchen's: its only way out crosses the kitchen, so it has no route."""
    r = routes(kitchen_closet(closet_use=use))
    assert r.story.served_by == {}
    with pytest.raises(Stop) as stop:
        r.route(at(12, 18))
    assert stop.value.key == "no_route"


@pytest.mark.parametrize("use", ["toilet", "accessory_storage"])
def test_20_a_toilet_or_a_storeroom_off_the_kitchen_leaves_through_it(use):
    assert routes(kitchen_closet(closet_use=use)).route(at(12, 18)).feet == pytest.approx(18.670, abs=TOL)


def test_20_a_closet_joined_by_a_passage_keeps_decision_1a():
    """A closet open to the kitchen by a separation line (no door) is not covered by the reading: no route."""
    d = kitchen_closet()
    d["doors"] = [x for x in d["doors"] if x["id"] != "clk"]
    for r in d["rooms"]:
        if r["id"] == "cl":
            r["floor"] = [list(p) for p in rect(10, 16.5, 14, 20)]
    d["passages"] = [{"rooms": ["cl", "k"], "line": [[10, 16.5], [14, 16.5]]}]
    r = routes(d)
    assert r.story.served_by == {}
    with pytest.raises(Stop):
        r.route(at(12, 18))


def test_20_a_room_served_through_a_storeroom_open_to_the_corridor_is_never_called_a_reentry():
    """A storeroom 10 to 20 by 6 to 16 open to the corridor by a separation line along y = 6; a closet (13 to 17
    by 16.5 to 19.5) whose only door, centred at (15, 16.25), opens into it. The route on from the closet's door
    centre starts in the storeroom's wall, so it comes into the storeroom through that door before it leaves by the
    passage: that is no coming back. By hand, along x = 15: from (15, 19) 2.75 to the door centre, then 16.5 to the
    exit: 19.25."""
    d = description([CORRIDOR, room("s", rect(10, 6, 20, 16), use="accessory_storage", lockable=False),
                     room("cl", rect(13, 16.5, 17, 19.5), use="closet", lockable=True)],
                    [EXIT, door("cls", (15, 16.25), (1, 0), ("cl", "s"))],
                    passages=[(("s", "c"), [(10, 6), (20, 6)])])
    r = routes(d)
    assert r.story.served_by == {"cl": "s"}
    assert r.route(at(15, 19)).feet == pytest.approx(19.25, abs=TOL)


def test_a_closets_route_measured_over_the_story_is_a_number():
    """The story's travel figure is a number, at least the closet's far corner's route (by hand: from (10, 20), clear
    of every ring, straight to the closet's door centre sqrt(2^2 + 3.25^2) = 3.816, then 10.920 + 6.5: 21.236; the
    corridor's far corner (40, 6) is farther, sqrt(25^2 + 6.25^2) = 25.769 ft in a straight line, and longer round the exit jamb (16.5, 0): the story's
    greatest is at least that)."""
    sp = measure(kitchen_closet())["parts"]["story"][0]
    assert sp["measures"]["egress_travel_distance"] >= 25.769 - TOL


def test_the_floor_reads_use_and_lockable_onto_each_room():
    s = story(kitchen_closet())
    assert (s.rooms["k"].use, s.rooms["k"].lockable) == ("kitchen", False)
    assert (s.rooms["cl"].use, s.rooms["cl"].lockable) == ("closet", True)
    assert read(kitchen_closet()).stops == []
