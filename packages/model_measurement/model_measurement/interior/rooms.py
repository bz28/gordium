"""Sleeping rooms: the floor area (sleeping_room_floor_area), and the least ceiling height it depends on.

R312.1 sets a habitable room's least floor area; R312.3 leaves out of it the parts under a sloping ceiling lower
than 5 ft or a furred ceiling lower than 7 ft. Which parts those are is not measured yet, so the floor area is given
only when no part of the ceiling is under 7 ft (then every part counts, whatever the ceiling's shape). Otherwise no
value: never the whole drawn area, which would be too much. Definitions: docs/interior/interior_measurements.md.
"""

from model_measurement.interior.geometry import Surface, least_gap
from model_measurement.interior.read import tidy
from model_measurement.interior.stops import Stop

SEVEN_FEET = 84.0


def floor_elevation(room: dict, reader) -> float:
    return reader.length(room.get("floor_elevation"), "the room's floor elevation")


def least_ceiling(room: dict, reader, floor) -> float:
    """The least height from the finished floor to the finished ceiling over the whole room, in inches."""
    has_height, has_surfaces = room.get("ceiling_height") is not None, room.get("ceilings") is not None
    if has_height and has_surfaces:
        raise Stop("two_ceilings")
    if has_height:
        return reader.size(room["ceiling_height"], "the room's ceiling height")
    if not has_surfaces:
        raise Stop("no_ceiling")
    pieces = room["ceilings"]
    if not isinstance(pieces, list) or not pieces:
        raise Stop("not_a_polyline", what="the room's ceilings")
    level = floor_elevation(room, reader)
    surfaces = [Surface(reader.points(p, 3, f"ceiling piece {n}", 3), f"ceiling piece {n}")
                for n, p in enumerate(pieces, 1)]
    return least_gap(surfaces, [(floor, lambda x, y: level)], "the ceiling", "room")


def measure_room(room: dict, reader) -> tuple[dict, dict, dict]:
    """(measures, more, not_measured) for one sleeping room."""
    measures, more, stopped = {}, {}, {}
    try:
        floor = reader.outline(room.get("floor"), "the room's floor outline")
    except Stop as s:
        stopped["sleeping_room_floor_area"] = stopped["floor_area_drawn"] = s.reason
        return measures, more, stopped
    more["floor_area_drawn"] = tidy(floor.area / 144)
    try:
        ceiling = least_ceiling(room, reader, floor)
    except Stop as s:
        stopped["least_ceiling_height"] = stopped["sleeping_room_floor_area"] = s.reason
        return measures, more, stopped
    more["least_ceiling_height"] = tidy(ceiling)
    if tidy(ceiling) >= SEVEN_FEET:
        measures["sleeping_room_floor_area"] = tidy(floor.area / 144)
    else:
        stopped["sleeping_room_floor_area"] = Stop("low_ceiling", height=tidy(ceiling)).reason
    return measures, more, stopped
