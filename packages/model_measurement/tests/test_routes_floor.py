"""The route additions to the interior description, read (routes/floor.py): every key left out is "not read",
never a default (docs/decisions/2026-11-20_route_measurement.md, "What the description holds today", and decisions
1a and 10), and each reason in routes/stops.py that reading gives happens from a case of its own."""

import copy
import sys
from pathlib import Path

import pytest

from model_measurement.routes.floor import read
from model_measurement.routes.paths import StoryRoutes
from model_measurement.routes.remote import farthest
from model_measurement.routes.stops import STOPS, Stop
sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import description, door, l_corridor, rect, room, room_on_corridor, story


def _without(desc, *path):
    d = copy.deepcopy(desc)
    node = d
    for k in path[:-1]:
        node = node[k]
    del node[path[-1]]
    return d


def _with(desc, value, *path):
    d = copy.deepcopy(desc)
    node = d
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    return d


def test_the_base_layout_reads_with_nothing_to_review():
    s = story(room_on_corridor())
    assert s.stops == [] and [z.rooms for z in s.zones] == [("c",)]
    assert s.rooms["c"].crossable and not s.rooms["r"].crossable


# --- each key left out ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path, words", [
    (("levels",), "no levels"),
    (("rooms", 0, "level"), "doesn't say which story"),
    (("doors", 0, "level"), "doesn't say which story"),
    (("passages",), "the model doesn't give its passages"),
])
def test_a_key_left_out_leaves_every_story_not_measured(path, words):
    floor = read(_without(room_on_corridor(), *path))
    assert any(words in s for s in floor.stops), floor.stops
    # every story carries it: none is measured (review round 1: a number that left out the unread room)
    for s in floor.stories.values():
        assert any(words in r for r in s.stops), s.stops
        with pytest.raises(Stop) as stop:
            StoryRoutes(s)
        assert stop.value.key == "story_not_measured" and words in stop.value.reason


def test_an_end_only_room_with_no_level_gives_its_story_no_number():
    d = room_on_corridor()
    del d["rooms"][0]["level"]                       # the day-care room (end-only) not placed
    for s in read(d).stories.values():
        with pytest.raises(Stop):
            farthest(StoryRoutes(s))


def test_two_doors_with_one_centre_need_review():
    d = room_on_corridor()
    d["doors"].append(door("d2", (10, 15.25), (1, 0), ("r", "c")))
    assert any("have the same centre" in r for r in story(d).stops)


def test_an_unknown_space_with_no_level_leaves_every_story_not_measured():
    d = room_on_corridor()
    d["unknown_spaces"] = [{"id": "u", "name": "Enclosed area"}]
    assert any("doesn't say which story" in s for s in read(d).stops)


@pytest.mark.parametrize("path, words", [
    (("rooms", 0, "holes"), "its holes (an empty list for none)"),
    (("rooms", 0, "obstructions"), "what stands on its floor"),
    (("rooms", 0, "floor"), "no floor outline"),
    (("doors", 0, "plan"), "the door's plan"),
    (("doors", 0, "sides"), "the door's sides"),
    (("doors", 1, "exit_id"), "which exit the exit door leads into"),
])
def test_a_key_left_out_leaves_its_story_not_measured(path, words):
    floor = read(_without(room_on_corridor(), *path))
    assert floor.stops == []
    assert any(words in s for s in floor.stories["L1"].stops), floor.stories["L1"].stops


@pytest.mark.parametrize("key", ["kind", "fixed", "outline"])
def test_an_obstruction_key_left_out_leaves_its_story_not_measured(key):
    d = room_on_corridor()
    d["rooms"][0]["obstructions"] = [{"outline": [list(p) for p in rect(1, 1, 2, 2)], "kind": "casework",
                                      "fixed": True}]
    assert story(d).stops == []
    del d["rooms"][0]["obstructions"][0][key]
    assert any("isn't read" in s for s in story(d).stops)


def test_an_exit_id_with_no_exit_kind_isnt_read():
    s = story(_without(room_on_corridor(), "doors", 1, "exit_kind"))
    assert any("the kind of exit the door is" in r for r in s.stops)


def test_no_story_outlines_leaves_the_diagonal_and_areas_not_measured_but_routes_are():
    s = story(_without(room_on_corridor(), "story_outlines"))
    assert s.stops == [] and "story outlines" in s.outline_stop


@pytest.mark.parametrize("key", ["use", "lockable", "pass_through"])
def test_a_crossing_key_left_out_makes_the_room_end_only(key):
    s = story(_without(room_on_corridor(), "rooms", 1, key))
    assert s.stops == [] and not s.rooms["c"].crossable and s.rooms["c"].end_only_why


# --- decision 1a: which rooms a route may cross ------------------------------------------------------------------------

@pytest.mark.parametrize("changes, crossable", [
    ({"use": "corridor", "lockable": False, "pass_through": False}, True),
    ({"use": "corridor", "lockable": True, "pass_through": False}, False),
    ({"use": "day_care", "lockable": False, "pass_through": True}, True),
    ({"use": "day_care", "lockable": False, "pass_through": False}, False),
    ({"use": "lobby", "lockable": False, "pass_through": False}, False),      # test 14: no exception by its use
    ({"use": "lobby", "lockable": False, "pass_through": True}, True),
    ({"use": "other", "lockable": False, "pass_through": True}, True),
    ({"use": "kitchen", "lockable": False, "pass_through": False}, False),
    ({"use": "accessory_storage", "lockable": False, "pass_through": False}, False),
])
def test_which_rooms_a_route_may_cross(changes, crossable):
    d = room_on_corridor()
    d["rooms"][1].update(changes)
    assert story(d).rooms["c"].crossable is crossable


@pytest.mark.parametrize("changes, why", [
    ({"use": "accessory_storage"}, "a accessory_storage room"),     # test 14's storage room marked pass_through
    ({"use": "kitchen"}, "a kitchen room"),
    ({"use": "toilet"}, "a toilet room"),
    ({"use": "closet"}, "a closet room"),
    ({"use": "workroom"}, "a workroom room"),
    ({"sleeping": True}, "a sleeping room"),
    ({"lockable": True}, "it can be locked"),
])
def test_pass_through_on_an_end_only_room_is_refused_and_its_story_needs_review(changes, why):
    d = room_on_corridor()
    d["rooms"][1].update(changes, pass_through=True)
    s = story(d)
    assert any("is marked as a room an exit route may pass through" in r and why in r for r in s.stops), s.stops
    assert s.rooms["c"] is None


# --- decision 10: what always needs review -------------------------------------------------------------------------

def test_an_unknown_space_on_the_story_needs_review_even_with_its_outline():
    d = room_on_corridor()
    d["unknown_spaces"] = [{"id": "u", "name": "Enclosed area", "level": "L1",
                            "outline": [list(p) for p in rect(50, 0, 51, 1)]}]
    assert any("has no room drawn in it" in r for r in story(d).stops)


def test_a_door_onto_an_unknown_space_needs_review():
    d = room_on_corridor()
    d["unknown_spaces"] = [{"id": "u", "name": "Enclosed area", "level": "L1"}]
    d["doors"][0]["sides"] = ["r", "u"]
    assert any("an enclosed space with no room drawn in it" in r for r in story(d).stops)


def test_a_door_onto_a_room_not_read_needs_review():
    d = _with(room_on_corridor(), "nowhere", "rooms", 0, "use")
    assert any("a room that isn't read" in r for r in story(d).stops)


def test_a_door_under_24_in_needs_review():
    d = _with(room_on_corridor(), 22 / 12, "doors", 0, "plan", "clear_width")
    assert any("under 24 in" in r for r in story(d).stops)
    assert story(_with(room_on_corridor(), 2.0, "doors", 0, "plan", "clear_width")).stops == []


def test_an_exit_to_an_exterior_stair_needs_review():
    d = _with(room_on_corridor(), "exterior_stair_or_ramp", "doors", 1, "exit_kind")
    assert any("exterior stair or ramp" in r for r in story(d).stops)


def test_no_exit_on_the_story_needs_review():
    d = l_corridor()
    del d["doors"][0]["exit_kind"], d["doors"][0]["exit_id"]
    assert STOPS["no_exit"] in story(d).stops


def test_a_door_not_in_a_wall_of_its_room_needs_review():
    d = _with(room_on_corridor(), [10, 16.25], "doors", 0, "plan", "centre")
    assert any("doesn't sit in a wall" in r for r in story(d).stops)


# --- each reason reading gives, from a case of its own --------------------------------------------------------------

def _no_levels():
    return _without(room_on_corridor(), "levels")


def _two_levels_one_id():
    d = room_on_corridor()
    d["levels"].append(dict(d["levels"][0]))
    return d


def _overlap():
    d = room_on_corridor()
    d["rooms"].append(room("o", rect(5, 5, 25, 10), use="day_care"))
    return d


def _door_same_side():
    d = room_on_corridor()
    d["rooms"].append(room("q", rect(8, 10, 12, 15), use="day_care"))     # inside r, below the same wall
    d["doors"][0]["sides"] = ["r", "q"]
    return d


def _passage_off():
    d = room_on_corridor()
    d["passages"] = [{"rooms": ["r", "c"], "line": [[0, 0], [1, 0]]}]
    return d


def _pieces(mp):
    """A passage's rooms that don't join (a guard: the passage's line check keeps it from happening): the geometry
    library made to give two pieces."""
    from shapely.geometry import MultiPolygon, Polygon
    mp.setattr("model_measurement.routes.floor.unary_union",
               lambda pieces: MultiPolygon([Polygon(rect(0, 0, 1, 1)), Polygon(rect(5, 5, 6, 6))]))


def _door_within_zone():
    d = room_on_corridor()
    d["rooms"][0].update(use="corridor", pass_through=False)
    d["passages"] = [{"rooms": ["r", "c"], "line": [[19, 15.5], [20, 15.5]]}]
    d["rooms"][0]["floor"] = [list(p) for p in [(0, 0), (20, 0), (20, 15.5), (19, 15.5), (19, 15), (0, 15)]]
    return d


FLOOR_CASES = {
    "description": lambda: _with(room_on_corridor(), "cubits", "units"),
    "flag_text": lambda: _with(room_on_corridor(), "no", "rooms", 0, "lockable"),
    "no_levels": _no_levels,
    "level_entry": lambda: _with(room_on_corridor(), [{"id": "L1", "name": "Level 1"}], "levels"),
    "level_twice": _two_levels_one_id,
    "no_level": lambda: _without(room_on_corridor(), "rooms", 0, "level"),
    "level_unknown": lambda: _with(room_on_corridor(), "L9", "rooms", 0, "level"),
    "key_left_out": lambda: _without(room_on_corridor(), "passages"),
    "id_twice": lambda: _with(room_on_corridor(), "r", "rooms", 1, "id"),
    "room_not_read": lambda: _without(room_on_corridor(), "rooms", 0, "holes"),
    "room_no_floor": lambda: _without(room_on_corridor(), "rooms", 0, "floor"),
    "pass_through_refused": lambda: _with(_with(room_on_corridor(), True, "rooms", 1, "pass_through"), "closet",
                                          "rooms", 1, "use"),
    "rooms_overlap": _overlap,
    "unknown_space": lambda: _with(room_on_corridor(), [{"id": "u", "level": "L1"}], "unknown_spaces"),
    "unknown_space_not_read": lambda: _with(room_on_corridor(), [{"id": "u", "level": "L1", "outline": [[0, 0]]}],
                                            "unknown_spaces"),
    "door_not_read": lambda: _without(room_on_corridor(), "doors", 0, "plan"),
    "door_narrow": lambda: _with(room_on_corridor(), 1.5, "doors", 0, "plan", "clear_width"),
    "door_side": lambda: _with(room_on_corridor(), ["r", "nowhere"], "doors", 0, "sides"),
    "door_not_in_wall": lambda: _with(room_on_corridor(), [10, 16.25], "doors", 0, "plan", "centre"),
    "door_same_side": _door_same_side,
    "door_within_zone": _door_within_zone,
    "exit_stair_or_ramp": lambda: _with(room_on_corridor(), "exterior_stair_or_ramp", "doors", 1, "exit_kind"),
    "passage_not_read": lambda: _with(room_on_corridor(), [{"rooms": ["r"], "line": [[0, 15], [1, 15]]}],
                                      "passages"),
    "passage_off": _passage_off,
    "zone_in_pieces": room_on_corridor,
    "no_exit": lambda: _without(_without(l_corridor(), "doors", 0, "exit_kind"), "doors", 0, "exit_id"),
    "doors_same_centre": lambda: _with(room_on_corridor(), room_on_corridor()["doors"]
                                       + [door("d2", (10, 15.25), (1, 0), ("r", "c"))], "doors"),
    "door_centre_in_ring": lambda: _with(room_on_corridor(), [{"outline": [list(q) for q in rect(9.6, 15.6, 10.4, 16)],
                                                                "kind": "furniture", "fixed": False}],
                                         "rooms", 1, "obstructions"),
    "outline_not_read": lambda: _with(room_on_corridor(), [{"level": "L1", "outer": [[0, 0]], "inner": [[0, 0]]}],
                                      "story_outlines"),
}


@pytest.mark.parametrize("key", sorted(FLOOR_CASES))
def test_each_reading_stop_happens_and_is_said(key, monkeypatch):
    made, init = [], Stop.__init__

    def recording(self, which, /, **blanks):
        init(self, which, **blanks)
        made.append((which, self.reason))

    monkeypatch.setattr(Stop, "__init__", recording)
    if key == "zone_in_pieces":
        _pieces(monkeypatch)
    floor = read(FLOOR_CASES[key]())
    reasons = [r for w, r in made if w == key]
    assert reasons, f"{key} didn't happen"
    said = floor.stops + [r for s in floor.stories.values() for r in s.stops + [s.outline_stop or ""]]
    assert any(r in x for r in reasons for x in said), (key, said)
