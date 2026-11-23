"""A space that is itself an exit (routes/__init__.py _is_exit, 2026-11-23): a stair enclosure entered by a door marked
an exit is not a room, area or space the exits serve (BCNYS 1006.2), so the Building Code's space rules read
`space_is_exit` and ask nothing of it. The format gives an enclosure's doors the enclosure's room as their `exit_id`
(docs/interior/interior_description_format.md); an exit whose id is neither room the door joins leaves it unknown,
never guessed."""

import sys
from pathlib import Path

from model_measurement.routes import measure
from model_measurement.routes.stops import STOPS

sys.path.insert(0, str(Path(__file__).parent))           # the layouts beside this file (pytest's importlib mode)
from routes_layouts import description, door, rect, room  # noqa: E402


def stair_off_corridor(exit_id="st"):
    """A room 0 to 20 by 0 to 15 with one door onto a corridor 15.5 to 23.5 running 0 to 40; a stair enclosure 40.5
    to 50 by 15.5 to 23.5 at the corridor's east end, entered by an exit door (exit_enclosure, `exit_id`), with its
    own door outside (not marked); an exterior exit at the corridor's west end."""
    rooms = [room("r", rect(0, 0, 20, 15), use="workroom"), room("c", rect(0, 15.5, 40, 23.5)),
             room("st", rect(40.5, 15.5, 50, 23.5), use="other")]
    doors = [door("d", (10, 15.25), (1, 0), ("r", "c")),
             door("w", (-0.25, 19.5), (0, 1), ("c", "outside"), exit_id="W"),
             door("e", (40.25, 19.5), (0, 1), ("c", "st"), exit_id=exit_id, kind="exit_enclosure"),
             door("o", (50.25, 19.5), (0, 1), ("st", "outside"))]
    return description(rooms, doors)


def _spaces(d):
    return {p["id"]: p for p in measure(d)["parts"]["space"]}


def test_a_stair_enclosure_entered_by_its_exit_door_is_an_exit_and_the_room_is_not():
    got = _spaces(stair_off_corridor())
    assert got["st"]["measures"]["space_is_exit"] is True
    assert got["r"]["measures"]["space_is_exit"] is False            # no exit door of its own


def test_a_room_beside_an_exit_door_into_the_other_room_is_a_space():
    """The corridor's side of the enclosure door: the exit is the other room (the enclosure), so the corridor isn't
    a space part at all (it is a corridor); a room in its place is a space, not an exit."""
    d = stair_off_corridor()
    d["rooms"][1]["use"] = "lobby"
    d["rooms"][1]["pass_through"] = True
    got = _spaces(d)
    assert got["c"]["measures"]["space_is_exit"] is False
    assert got["st"]["measures"]["space_is_exit"] is True


def test_an_exit_whose_id_is_no_room_it_joins_leaves_it_unknown():
    """exit_id "stair-1" (a stair's own id, which the format allows): which side is the enclosure isn't known, so
    neither room is said to be one or not; the room with no exit door is still a space."""
    got = _spaces(stair_off_corridor(exit_id="stair-1"))
    words = STOPS["exit_side_unclear"].split("{")[0]
    assert "space_is_exit" not in got["st"]["measures"]
    assert got["st"]["not_measured"]["space_is_exit"].startswith(words)
    assert "stair-1" in got["st"]["not_measured"]["space_is_exit"]
    assert got["r"]["measures"]["space_is_exit"] is False
