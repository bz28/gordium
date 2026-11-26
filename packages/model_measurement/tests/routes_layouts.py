"""Small story layouts for the route tests, written in feet as the route note writes them
(docs/decisions/2026-11-20_route_measurement.md, "How we will know it is right": walls 6 in thick, so a door's
centre sits 0.25 ft outside its room; doors 36 in clear)."""

from model_measurement.routes.floor import read
from model_measurement.routes.paths import StoryRoutes

FT = 12.0          # the route code works in inches


def room(rid, outline, use="corridor", lockable=False, pass_through=False, holes=(), obstructions=(), **more):
    r = {"id": rid, "name": rid, "sleeping": False, "level": "L1", "floor": [list(p) for p in outline],
         "floor_elevation": 0, "ceiling_height": 9, "use": use, "lockable": lockable, "pass_through": pass_through,
         "holes": [list(map(list, h)) for h in holes],
         "obstructions": [{"outline": [list(p) for p in o], "kind": "furniture", "fixed": False} for o in obstructions]}
    r.update(more)
    return r


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def door(did, centre, along, sides, width=3.0, thickness=0.5, exit_id=None, kind="exterior_at_discharge", **more):
    d = {"id": did, "name": did, "exit": False, "level": "L1",
         "plan": {"centre": list(centre), "along": list(along), "clear_width": width, "wall_thickness": thickness},
         "sides": list(sides)}
    if exit_id is not None:
        d["exit_kind"], d["exit_id"] = kind, exit_id
    d.update(more)
    return d


def description(rooms, doors, passages=()):
    return {"format": "gordium.interior/1", "units": "ft", "levels": [{"id": "L1", "name": "Level 1", "elevation": 0}],
            "rooms": rooms, "doors": doors, "passages": [{"rooms": list(a), "line": [list(p) for p in line]}
                                                         for a, line in passages],
            "story_outlines": []}


def story(desc):
    floor = read(desc)
    assert not floor.stops, floor.stops
    return floor.stories["L1"]


def routes(desc, clearance=12.0) -> StoryRoutes:
    s = story(desc)
    assert not s.stops, s.stops
    return StoryRoutes(s, clearance)


def at(x, y):
    return (x * FT, y * FT)


# --- the note's layouts ---------------------------------------------------------------------------------------------

def l_corridor():
    """Test 1: legs 0 to 40 by 0 to 6 and 34 to 40 by 6 to 30; the exit door centred at (-0.25, 3)."""
    return description([room("c", [(0, 0), (40, 0), (40, 30), (34, 30), (34, 6), (0, 6)])],
                       [door("x", (-0.25, 3), (0, 1), ("c", "outside"), exit_id="A")])


def column_room(north_exit=False):
    """Test 2: a room 0 to 30 by 0 to 10, a 4-ft column 13 to 17 by 3 to 7, the exit door centred at (-0.25, 5);
    with `north_exit`, exit B: a 36-in door in the north wall centred at (2, 10.25)."""
    doors = [door("a", (-0.25, 5), (0, 1), ("r", "outside"), exit_id="A")]
    if north_exit:
        doors.append(door("b", (2, 10.25), (1, 0), ("r", "outside"), exit_id="B"))
    return description([room("r", rect(0, 0, 30, 10), use="day_care", holes=[rect(13, 3, 17, 7)])], doors)


def table_room():
    """The table: a room 0 to 20 by 0 to 20, a table 7 to 13 by 8.5 to 11.5, the exit door centred at (10, 20.25)."""
    return description([room("r", rect(0, 0, 20, 20), use="day_care", obstructions=[rect(7, 8.5, 13, 11.5)])],
                       [door("x", (10, 20.25), (1, 0), ("r", "outside"), exit_id="A")])


def room_on_corridor():
    """Test 4: a room 0 to 20 by 0 to 15, its one 36-in door centred at (10, 15.25) on a corridor 15.5 to 23.5
    running -20 to 40, an exit at each end."""
    return description([room("r", rect(0, 0, 20, 15), use="day_care"), room("c", rect(-20, 15.5, 40, 23.5))],
                       [door("d", (10, 15.25), (1, 0), ("r", "c")),
                        door("w", (-20.25, 19.5), (0, 1), ("c", "outside"), exit_id="A"),
                        door("e", (40.25, 19.5), (0, 1), ("c", "outside"), exit_id="B")])
