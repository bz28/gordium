"""A space the architect marks not occupied (route note decision 1b, test 21): NFPA 101 measures travel and common
path from points "subject to occupancy" (7.6.1(1), A.3.3.47), so its figures (`egress_travel_distance_occupied`,
`common_path_of_travel_occupied`, and the room-door travel) leave such a room out, saying so; the 2009 IBC measures
from "the most remote point within a story" (1016.1), so its figures never do. Hand figures in feet, worked in the
docstrings; none is taken from the code under test."""

import copy
import sys
from pathlib import Path

import pytest

from model_measurement.routes import measure
from model_measurement.routes.floor import read

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import description, door, rect, room  # noqa: E402

TOL = 1e-3
NFPA = ("egress_travel_distance_occupied", "common_path_of_travel_occupied")
IBC = ("egress_travel_distance", "common_path_of_travel")
LEFT_OUT = "measured leaving out 1 space marked not occupied by the architect: abandoned"


def layout(marked=None, abandoned=True, corridor=None):
    """Test 21: a corridor 0 to 40 by 0 to 6, its exit in the south wall centred at (20, -0.25); an office (`other`,
    end-only) 15 to 25 by 6.5 to 16.5, its door to the corridor centred at (20, 6.25); an abandoned space (`other`)
    15 to 25 by 17 to 27 whose only door, centred at (20, 16.75), opens into the office (so its only way out crosses
    the office: no route, decision 1a). `marked`: the abandoned space's `not_occupied`, left out when None."""
    rooms = [room("c", rect(0, 0, 40, 6), **(corridor or {})), room("o", rect(15, 6.5, 25, 16.5), use="other")]
    doors = [door("x", (20, -0.25), (1, 0), ("c", "outside"), exit_id="A"), door("oc", (20, 6.25), (1, 0), ("o", "c"))]
    if abandoned:
        ab = room("abandoned", rect(15, 17, 25, 27), use="other")
        if marked is not None:
            ab["not_occupied"] = marked
        rooms.append(ab)
        doors.append(door("ao", (20, 16.75), (1, 0), ("abandoned", "o")))
    return description(rooms, doors)


def story_part(desc):
    return measure(desc)["parts"]["story"][0]


def test_21_unmarked_a_room_with_no_route_holds_both_books_figures():
    sp = story_part(layout())
    for name in IBC + NFPA + ("egress_travel_from_room_door",):
        assert name not in sp["measures"], name
        assert name in sp["not_measured"], name
    assert "architect_stated" not in sp


def test_21_marked_nfpa_measures_the_occupied_rooms_and_says_which_it_left_out():
    """By hand: the corridor's end (0, 6) to the exit centre (20, -0.25) is at least the straight line
    sqrt(20^2 + 6.25^2) = 20.954 ft (more round the exit's jamb ring); the office's far corner (15, 16.5) straight to
    its door centre (20, 6.25), sqrt(5^2 + 10.25^2) = 11.404 (1.24 and 1.46 ft off the jambs (18.5, 6.5) and
    (21.5, 6.5)), then straight down through the exit's centre, 6.5: 17.904. The room-door travel: the office's door
    centre straight down to the exit's, 6.5 exactly (1.5 ft off every jamb)."""
    sp = story_part(layout(marked=True))
    for name in IBC:                                   # the IBC's words have no carve-out: still needs review
        assert name not in sp["measures"] and name in sp["not_measured"], name
    travel, common = (sp["measures"][n] for n in NFPA)
    assert 20.954 - TOL <= travel < 22
    assert common == travel                            # one exit: the common path is the travel (decision 5)
    assert sp["measures"]["egress_travel_from_room_door"] == pytest.approx(6.5, abs=TOL)
    for name in NFPA + ("egress_travel_from_room_door",):
        assert sp["architect_stated"][name] == LEFT_OUT
    assert set(sp["architect_stated"]) == set(NFPA) | {"egress_travel_from_room_door"}   # never an IBC figure's
    for name in NFPA:
        assert sp["more"][name]["left_out"] == ["abandoned"]


def test_21_the_nfpa_figure_is_the_storys_without_the_room():
    """No route of the other rooms ever entered the abandoned space, so leaving out its points gives exactly the
    figures of the same story drawn without it (two separate measurings)."""
    marked, without = story_part(layout(marked=True)), story_part(layout(abandoned=False))
    for nfpa, ibc in zip(NFPA, IBC):
        assert marked["measures"][nfpa] == without["measures"][ibc] == without["measures"][nfpa]
    assert "architect_stated" not in without


def test_21_with_no_room_marked_both_books_give_the_same_figures():
    sp = story_part(layout(abandoned=False))
    for nfpa, ibc in zip(NFPA, IBC):
        assert sp["measures"][nfpa] == sp["measures"][ibc]
        assert sp["more"][nfpa] == sp["more"][ibc]
    assert story_part(layout(marked=False)) == story_part(layout())     # false is occupied: as if never marked


def test_21_a_marked_corridor_is_still_crossed_and_only_its_points_are_left_out():
    """The corridor marked too: the office's route still crosses it (the mark never stops a room being crossed), and
    the NFPA figure is the office's alone: at least its far corner's 17.904 (by hand, above), and under the
    corridor's end's 20.954."""
    sp = story_part(layout(marked=True, corridor={"not_occupied": True}))
    travel = sp["measures"]["egress_travel_distance_occupied"]
    assert 17.904 - TOL <= travel < 20.954
    assert sp["architect_stated"]["egress_travel_distance_occupied"] == \
        "measured leaving out 2 spaces marked not occupied by the architect: abandoned, c"
    assert sp["measures"]["egress_travel_from_room_door"] == pytest.approx(6.5, abs=TOL)


def test_21_every_room_marked_leaves_no_point_to_measure_from():
    d = layout(marked=True, corridor={"not_occupied": True})
    for r in d["rooms"]:
        r["not_occupied"] = True
    sp = story_part(d)
    for name in NFPA:
        assert name not in sp["measures"]
        assert "every room on the story is marked not occupied" in sp["not_measured"][name]


def test_21_the_ibc_figure_keeps_a_marked_room_that_has_a_route():
    """The abandoned space 0 to 10 by 6.5 to 16.5 opening on the corridor (door centred at (5, 6.25)), marked. By
    hand: from its far corner (0, 16.5) to its door centre at least sqrt(5^2 + 10.25^2) = 11.404, then from (5, 6.25)
    to the exit centre (20, -0.25) at least the straight line sqrt(15^2 + 6.5^2) = 16.348: the IBC figure is at least
    27.752; the NFPA figure (the corridor's end and the office, as above) is under 22."""
    d = layout(abandoned=False)
    d["rooms"].append(dict(room("abandoned", rect(0, 6.5, 10, 16.5), use="other"), not_occupied=True))
    d["doors"].append(door("ac", (5, 6.25), (1, 0), ("abandoned", "c")))
    sp = story_part(d)
    assert sp["measures"]["egress_travel_distance"] >= 27.752 - TOL
    assert 20.954 - TOL <= sp["measures"]["egress_travel_distance_occupied"] < 22
    assert sp["measures"]["egress_travel_from_room_door"] < 16.348   # the abandoned space's door left out
    assert "egress_travel_distance" not in sp["architect_stated"]


@pytest.mark.parametrize("change, words", [
    ({"sleeping": True}, "it is a sleeping room"),
    ({"use": "day_care"}, "it is a day_care room"),
])
def test_21_a_room_whose_use_is_occupancy_cant_be_marked_not_occupied(change, words):
    d = layout(abandoned=False)
    d["rooms"][1].update(change, not_occupied=True)
    stops = read(d).stories["L1"].stops
    assert any("o is marked not occupied, but " + words in s for s in stops), stops


def test_21_a_mark_that_isnt_true_or_false_isnt_read():
    d = layout(marked="yes")
    stops = read(d).stories["L1"].stops
    assert any("abandoned isn't read" in s and "Whether it is not occupied is given as the text 'yes'" in s for s in stops), stops


def test_21_the_mark_changes_nothing_but_the_start_points():
    """The same description with the mark: the rooms crossable, the spaces and corridors measured, as without it."""
    a, b = read(layout(marked=True)).stories["L1"], read(layout()).stories["L1"]
    assert {k: (r.crossable, r.end_only_why) for k, r in a.rooms.items()} == \
        {k: (r.crossable, r.end_only_why) for k, r in b.rooms.items()}
    assert a.rooms["abandoned"].not_occupied and not b.rooms["abandoned"].not_occupied
    ma, mb = measure(layout(marked=True))["parts"], measure(layout())["parts"]
    assert copy.deepcopy(ma["space"]) == mb["space"] and ma["corridor"] == mb["corridor"]
