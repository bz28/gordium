"""Measuring the inside of a house for egress (escape openings, stairs, guards, the exit door), from a host-neutral
interior description. Plain code written by engineers, no AI (principle 6): same description, same numbers.

    measure(description) -> {"parts": {kind: [part, …] | None}, "problems": [...], "not_checked": [...], …}

`parts` is exactly what rule_format.parts.rows reads: each part {"id", "name", "within"?, "measures"}, measures
named as rule_format/parts.yaml names them, in inches and square feet. A kind not given in the description is None
(not read, so its rules need review), never an empty list; [] means the description says there are none. A
measure the description can't settle is left out of `measures` and its reason put in `not_measured` (a rule
reading it then needs review). Measures for rules not yet in parts.yaml are in `more` (and guards are their own
kind). The input format: docs/interior/interior_description_format.md; each measure's definition:
docs/interior/interior_measurements.md.
"""

import math

from model_measurement.interior.doors import measure_door
from model_measurement.interior.guards import measure_guard
from model_measurement.interior.openings import measure_opening
from model_measurement.interior.read import FORMAT, INCHES, Reader, name_of
from model_measurement.interior.rooms import floor_elevation, measure_room
from model_measurement.interior.stairs import measure_stair
from model_measurement.interior.stops import Stop

MEASURED_FORMAT = "gordium.interior_measured/1"
# kind → (the description's key, the words for a list of them, the flag each must carry, what the flag asks)
KINDS = {
    "sleeping_room": ("rooms", "rooms", "sleeping", "a sleeping room"),
    "emergency_escape_opening": ("openings", "openings", "escape", "an emergency escape and rescue opening"),
    "stair": ("stairs", "stairs", None, None),
    "egress_door": ("doors", "doors", "exit", "the required exit door"),
    "guard": ("guards", "guards", None, None),
}


def _given(description: dict, kind: str, problems: list):
    """The description's list for a kind, every entry a mapping carrying its flag; None (with a problem) if not."""
    key, words, flag, question = KINDS[kind]
    got = description.get(key)
    if got is None:
        problems.append(Stop("not_read", what=words, key=key).reason)
        return None
    if not isinstance(got, list):
        problems.append(Stop("not_a_list", key=key).reason)
        return None
    for n, item in enumerate(got, 1):
        if not isinstance(item, dict):
            problems.append(Stop("not_a_mapping", what=key[:-1], n=n).reason)
            return None
        if flag and not isinstance(item.get(flag), bool):
            problems.append(Stop("flag_missing", what=key[:-1], name=name_of(item), question=question, key=flag).reason)
            return None
    return got


def _part(item: dict, measured, within=None) -> dict:
    measures, more, stopped = measured[:3]
    # a last guard for every kind: a value that isn't a finite number is no value (read.FAR should make this unreachable)
    for got in (measures, more):
        for name in [n for n, v in got.items() if isinstance(v, float) and not math.isfinite(v)]:
            del got[name]
            stopped.setdefault(name, Stop("not_finite").reason)
    part = {"id": item.get("id"), "name": name_of(item)}
    if within is not None or "room" in item:
        part["within"] = within
    part.update(measures=measures, not_measured=stopped, more=more)
    return part


def measure(description) -> dict:
    out = {"format": MEASURED_FORMAT, "units": {"length": "in", "area": "sf"},
           "parts": {k: None for k in KINDS}, "problems": [], "not_checked": []}
    problems = out["problems"]
    if not isinstance(description, dict):
        problems.append(Stop("not_a_description").reason)
        return out
    if description.get("format") != FORMAT:
        problems.append(Stop("wrong_format", got=description.get("format")).reason)
        return out
    units = description.get("units")
    if not isinstance(units, str) or units not in INCHES:
        problems.append(Stop("units", units=units).reason)
        return out
    reader = Reader(units)
    parts = out["parts"]

    rooms = _given(description, "sleeping_room", problems)
    if rooms is not None:
        parts["sleeping_room"] = [_part(r, measure_room(r, reader)) for r in rooms if r["sleeping"]]
    every_room = description.get("rooms") if isinstance(description.get("rooms"), list) else None

    def same_id(room_id):
        """The rooms carrying this id: none for an id that isn't text (never a room without an id)."""
        if not isinstance(room_id, str):
            return []
        return [r for r in every_room or [] if isinstance(r, dict) and r.get("id") == room_id]

    def floor_of(room_id):
        if every_room is None:
            raise Stop("not_read", what="rooms", key="rooms")
        same = same_id(room_id)
        if not same:
            raise Stop("room_unknown")
        if len(same) > 1:
            raise Stop("room_twice", count=len(same), id=room_id)
        return floor_elevation(same[0], reader)

    def sleeping(room_id):
        """False only when the room is known, once, and said not to be a sleeping room."""
        same = same_id(room_id)
        return not (rooms is not None and len(same) == 1 and same[0]["sleeping"] is False)

    openings = _given(description, "emergency_escape_opening", problems)
    if openings is not None:
        parts["emergency_escape_opening"] = []
        for o in openings:
            if not o["escape"]:
                continue
            if not sleeping(o.get("room")):
                out["not_checked"].append({"kind": "emergency_escape_opening", "id": o.get("id"),
                                           "name": name_of(o), "why": "in a room that isn't a sleeping room"})
                continue
            parts["emergency_escape_opening"].append(_part(o, measure_opening(o, reader, floor_of), o.get("room")))

    stairs = _given(description, "stair", problems)
    flights = {}
    if stairs is not None:
        parts["stair"] = []
        for st in stairs:
            measured = measure_stair(st, reader)
            parts["stair"].append(_part(st, measured))
            if not isinstance(st.get("id"), str):
                continue                                         # no guard can name it (the checker flags it)
            if [s.get("id") for s in stairs].count(st.get("id")) > 1:
                flights[st.get("id")] = f"{len(stairs)} stairs given, more than one with this id"
            else:
                flight = measured[3]
                flights[st.get("id")] = (flight, st) if flight is not None else \
                    next(iter(measured[2].values()), "it couldn't be placed")

    doors = _given(description, "egress_door", problems)
    if doors is not None:
        parts["egress_door"] = [_part(d, measure_door(d, reader)) for d in doors if d["exit"]]

    guards = _given(description, "guard", problems)
    if guards is not None:
        if stairs is None and any(g.get("stair") is not None for g in guards):
            flights = {g.get("stair"): Stop("not_read", what="stairs", key="stairs").reason for g in guards
                       if isinstance(g.get("stair"), str)}
        parts["guard"] = [_part(g, measure_guard(g, reader, flights)) for g in guards]
    return out


def measure_file(path) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return measure(yaml.safe_load(f))


__all__ = ["measure", "measure_file", "MEASURED_FORMAT", "KINDS"]
