"""Which room each flight of stairs stands in, for the 2025 Building Code of New York State's stair rules (section
group 7c): whether the flight is in an exit stair enclosure, so none of the dwelling-unit exceptions (1011.2, 1011.3,
1011.5.2, 1011.11) can apply to it.

A flight stands in the room whose floor lies directly under each of its nosings: of the rooms whose floor outline
covers the nosing's end in plan, the one with the highest floor at or below the nosing. A flight is in an exit
enclosure where every nosing end stands in a room the routes read as itself an exit (`space_is_exit`: a door marked
`exit_enclosure` or `exit_passageway` enters it). An interior exit stairway is an exit, separated from the rest of the
building by its enclosure, so a flight inside one is not within a dwelling unit, nor on a deck, patio or walkway, nor
a stepped aisle in an assembly room. A nosing over no room, or over a room whose exit isn't worked out, leaves the
flight unknown (Stop), never in an enclosure. Definitions: docs/interior/interior_measurements.md (`stair_in_exit_enclosure`).
"""

from shapely.geometry import Point

from model_measurement.interior.read import Reader, tidy
from model_measurement.interior.stairs import Flight, headroom_past_bottom
from model_measurement.interior.rooms import floor_elevation
from model_measurement.interior.stops import Stop as Unread
from model_measurement.routes.stops import Stop

TOUCH = 1 / 16          # in: a nosing's end on a room's outline (a wall's face) is in that room


def in_exit_enclosure(description: dict, spaces) -> dict:
    """{stair id: True, False or a Stop} for every stair of the description with an id. `spaces` are the routes'
    space parts (model_measurement.routes), one per room, by the room's id."""
    reader = Reader(description["units"])
    exits = {}
    for p in spaces or []:
        if p["measures"].get("space_is_exit") is not None:
            exits[p["id"]] = p["measures"]["space_is_exit"]
    rooms = []
    for r in description.get("rooms") or []:
        if not isinstance(r, dict) or not isinstance(r.get("id"), str):
            continue
        try:
            rooms.append((r, reader.outline(r.get("floor"), "the room's floor").buffer(TOUCH),
                          floor_elevation(r, reader)))
        except Unread:
            rooms.append((r, None, None))
    out = {}
    for st in description.get("stairs") or []:
        if isinstance(st, dict) and isinstance(st.get("id"), str):
            try:
                out[st["id"]] = _in_exit(st, rooms, exits, reader)
            except (Stop, Unread) as s:
                out[st["id"]] = s
    return out


def _in_exit(st: dict, rooms, exits: dict, reader) -> bool:
    unread = [r for r, floor, _ in rooms if floor is None]
    if unread:                           # its floor may be the one under a nosing: never guessed
        raise Stop("stair_room_unread", room=unread[0].get("name") or unread[0]["id"])
    given = st.get("nosings")
    if not isinstance(given, list) or not given:
        raise Stop("stair_no_nosings")
    for n, nosing in enumerate(given, 1):
        for x, y, z in reader.points(nosing, 3, f"nosing {n}", 2):
            here = Point(x, y)
            under = [(r, level) for r, floor, level in rooms if level <= z + TOUCH and floor.covers(here)]
            if not under:
                raise Stop("stair_over_no_room", n=n)
            top = max(level for _, level in under)
            for r, level in under:
                if level < top:
                    continue
                is_exit = exits.get(r["id"])
                if is_exit is None:
                    raise Stop("stair_room_exit_unknown", n=n, room=r.get("name") or r["id"])
                if not is_exit:
                    return False
    return True


def apply(stairs, description, spaces) -> None:
    """Give each measured flight (the interior measuring's stair parts) the Building Code's own two values:
    `stair_in_exit_enclosure` (above; its reason where it isn't worked out) and `stair_riser_count`, the risers the
    interior measuring counts (`more`'s `stair_risers`, worked out and tested since 2026-11-13). The house code's
    rules aren't given the count here: their results stay as recorded until they are re-recorded with it. And
    `stair_headroom_past_bottom` (interior/stairs.py headroom_past_bottom: 1011.3's stretch past the bottom riser), and
    `stair_handrail_each_side` (1011.11's "handrails on each side": both sides counted)."""
    if not stairs or not isinstance(description, dict):
        return
    try:
        where = in_exit_enclosure(description, spaces)
    except Unread as s:                                        # the description's units: every flight unknown
        where = {p["id"]: s for p in stairs}
    for p in stairs:
        got = where.get(p["id"], Stop("stair_no_nosings"))
        if isinstance(got, bool):
            p["measures"]["stair_in_exit_enclosure"] = got
            p["not_measured"].pop("stair_in_exit_enclosure", None)
        else:
            p["not_measured"]["stair_in_exit_enclosure"] = got.reason
        p["not_measured"].pop("stair_headroom_past_bottom", None)
        try:
            p["measures"]["stair_headroom_past_bottom"] = tidy(_past_bottom(description, p["id"]))
        except (Stop, Unread) as s:
            p["not_measured"]["stair_headroom_past_bottom"] = s.reason
        if isinstance(p["measures"].get("stair_handrail_sides"), int):        # 1011.11: "on each side"
            p["measures"]["stair_handrail_each_side"] = p["measures"]["stair_handrail_sides"] >= 2
            p["not_measured"].pop("stair_handrail_each_side", None)
        else:
            p["not_measured"]["stair_handrail_each_side"] = p["not_measured"].get(
                "stair_handrail_sides", "the flight's handrail sides aren't worked out")
        if isinstance(p.get("more", {}).get("stair_risers"), int):
            p["measures"]["stair_riser_count"] = p["more"]["stair_risers"]
            p["not_measured"].pop("stair_riser_count", None)


def _past_bottom(description: dict, sid: str) -> float:
    same = [st for st in description.get("stairs") or [] if isinstance(st, dict) and st.get("id") == sid]
    if len(same) != 1:
        raise Stop("stair_no_nosings")
    reader = Reader(description["units"])
    flight = Flight(same[0], reader)
    flight.plan()
    return headroom_past_bottom(same[0], flight, reader)
