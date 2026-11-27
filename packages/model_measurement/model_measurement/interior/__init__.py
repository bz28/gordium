"""Measuring the inside of a house for egress (escape openings, stairs, guards, the exit door), from a host-neutral
interior description. Plain code written by engineers, no AI (principle 6): same description, same numbers.

    measure(description) -> {"parts": {kind: [part, …] | None}, "problems": [...], "not_checked": [...], …}

`parts` is exactly what rule_format.parts.rows reads: each part {"id", "name", "within"?, "measures"}, measures
named as rule_format/parts.yaml names them, in inches and square feet. A kind not given in the description is None
(not read, so its rules need review), never an empty list; [] means the description says there are none. A
measure the description can't settle is left out of `measures` and its reason put in `not_measured` (a rule
reading it then needs review). Other values worked out are in `more`, not yet handed to the rules; a parts.yaml
measure kept there says so in `not_measured` (and guards are their own kind). The input format: docs/interior/interior_description_format.md; each measure's definition:
docs/interior/interior_measurements.md.

What the description says the house has none of (`has_none`, has_none.py) makes that kind's parts an empty list, or
gives each escape opening a measure that follows from it, and is said in `has_none` ({kind: its source and words}) so
the checker shows every rule it sets aside. A part kind no list or claim speaks of is left out of `parts` (not read).

An enclosed space with no room drawn in it (`unknown_spaces`) may be a sleeping room nobody drew: it is given as a
sleeping room marked `maybe` (rule_format.parts: every row about it needs review), so the rooms that are drawn are
still checked and a rule over every sleeping room never passes while one may be missing.
"""

import math

from model_measurement.interior.doors import measure_door
from model_measurement.interior import has_none as none_of
from model_measurement.interior.guards import measure_guard
from model_measurement.interior.openings import measure_opening
from model_measurement.interior.read import FORMAT, INCHES, Reader, name_of, yes_no
from model_measurement.interior.rooms import floor_elevation, measure_room
from model_measurement.interior.stairs import measure_stair
from model_measurement.interior.stops import STOPS, Stop, given_text

MEASURED_FORMAT = "gordium.interior_measured/1"
# kind → (the description's key, the words for a list of them, the flag each must carry, what the flag asks)
KINDS = {
    "sleeping_room": ("rooms", "rooms", "sleeping", "a sleeping room"),
    "emergency_escape_opening": ("openings", "openings", "escape", "an emergency escape and rescue opening"),
    "stair": ("stairs", "stairs", None, None),
    "egress_door": ("doors", "doors", "exit", "the required exit door"),
    "guard": ("guards", "guards", None, None),
}


def asked_field(problem: str) -> str | None:
    """The interior description's field a problem of the description's (`problems`) asks the architect to state, read
    back from its words exactly as `_given` makes them: a flag one of a kind's entries doesn't give ("door D01 doesn't
    say whether it is the required exit door (yes or no)": "doors[].exit"), or a kind's list the description doesn't
    give at all ("the stairs weren't read: ...": "stairs"). None for any other words (never a guess): a host names
    its own mark from the field (the Revit add-in's Marks.cs `Feeds`)."""
    if not isinstance(problem, str):
        return None
    for key, words, flag, question in KINDS.values():
        if problem == Stop("not_read", what=words, key=key).reason:
            return key
        if flag:
            for stop in ("flag_missing", "flag_not_yes_no"):
                before, after = STOPS[stop].split("{what}")
                before = before + key[:-1] + " "
                head, _, tail = after.partition("{got}")
                head = head.format(question=f"it is {question}")
                if problem.startswith(before) and len(problem) > len(before) + len(head) and (
                        problem.endswith(head) if not tail else head in problem and problem.endswith(tail)):
                    return f"{key}[].{flag}"
    return None


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
        if flag:
            try:
                yes_no(item, flag, f"{key[:-1]} {name_of(item)}", f"it is {question}", required=True)
            except Stop as s:
                problems.append(s.reason)
                return None
    return got


def _unknown_spaces(description: dict, problems: list):
    """The enclosed spaces with no room drawn in them (`unknown_spaces`, [] when not given: the rooms are every
    room); None (with a problem: then no room is read) when the list or an entry can't be read."""
    got = description.get("unknown_spaces")
    if got is None:
        return []
    if not isinstance(got, list):
        problems.append(Stop("not_a_list", key="enclosed spaces with no room drawn in them").reason)
        return None
    for n, item in enumerate(got, 1):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"].strip():
            problems.append(Stop("unknown_spaces_entry", n=n).reason)
            return None
    return got


def _unknown(space: dict) -> dict:
    """An enclosed space whose use isn't known, as a sleeping room that may not be one (`maybe`, rule_format.parts:
    every row about it needs review, never a pass or a fail): nothing of it is measured."""
    from rule_format.parts import measure_kinds
    why = Stop("unknown_space").reason
    return {"id": space["id"], "name": name_of(space), "measures": {},
            "not_measured": {m: why for m in measure_kinds("sleeping_room")}, "more": {}, "maybe": why}


def _part(item: dict, measured, within=None) -> dict:
    measures, more, stopped = measured[:3]
    # a last guard for every kind: a value that isn't a finite number is no value (read.FAR keeps this unreachable)
    for got in (measures, more):
        for name in [n for n, v in got.items() if isinstance(v, float) and not math.isfinite(v)]:
            del got[name]
            stopped.setdefault(name, Stop("not_finite").reason)
    part = {"id": item.get("id"), "name": name_of(item)}
    if within is not None or "room" in item:
        part["within"] = within
    part.update(measures=measures, not_measured=stopped, more=more)
    return part


def _door(item: dict, measured) -> dict:
    """An exit door's part, with `from`: for each clear size it has, whether it came from the drawing, the maker's
    stated size, or both (the less favourable), with each value and the maker's source."""
    part = _part(item, measured)
    part["from"] = {name: came for name, came in measured[3].items() if name in part["measures"]}
    return part


def measure(description) -> dict:
    out = {"format": MEASURED_FORMAT, "units": {"length": "in", "area": "sf"},
           "parts": {k: None for k in KINDS}, "problems": [], "not_checked": [], "has_none": {}}
    problems = out["problems"]
    if not isinstance(description, dict):
        problems.append(Stop("not_a_description").reason)
        return out
    if description.get("format") != FORMAT:
        problems.append(Stop("wrong_format", got=given_text(description.get("format"), "no form named")).reason)
        return out
    units = description.get("units")
    if not isinstance(units, str) or units not in INCHES:
        problems.append(Stop("units", units=given_text(units, "no unit named")).reason)
        return out
    reader = Reader(units)
    parts = out["parts"]
    claims, refused = none_of.read(description)
    problems += refused

    rooms = _given(description, "sleeping_room", problems)
    spaces = _unknown_spaces(description, problems) if rooms is not None else None
    if rooms is not None and spaces is not None:
        parts["sleeping_room"] = [_part(r, measure_room(r, reader)) for r in rooms if r["sleeping"]] \
            + [_unknown(s) for s in spaces]
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
            measured = measure_opening(o, reader, floor_of)
            part = _part(o, measured, o.get("room"))
            if measured[3]:                                   # measures standing on Gordium's reading, to confirm
                part["confirm"] = {m: words for m, words in measured[3].items() if m in part["measures"]}
            parts["emergency_escape_opening"].append(part)

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
        parts["egress_door"] = [_door(d, measure_door(d, reader)) for d in doors if d["exit"]]

    guards = _given(description, "guard", problems)
    if guards is not None:
        if stairs is None and any(g.get("stair") is not None for g in guards):
            flights = {g.get("stair"): Stop("not_read", what="stairs", key="stairs").reason for g in guards
                       if isinstance(g.get("stair"), str)}
        parts["guard"] = [_part(g, measure_guard(g, reader, flights)) for g in guards]
    _claimed(parts, claims)
    out["has_none"] = claims
    _not_measured_yet(parts)
    return out


def _claimed(parts: dict, claims: dict) -> None:
    """Each claim taken: its part kinds an empty list, and its measures on every escape opening measured (each part
    says, in `stated`, which claim gave it which measure)."""
    for kind, claim in claims.items():
        for k in claim["parts"]:
            parts[k] = []
        for each, given in (("emergency_escape_opening", claim["openings"]), ("stair", claim["stairs"])):
            for part in parts.get(each) or []:
                for name, value in given.items():
                    part["measures"][name] = value
                    part["not_measured"].pop(name, None)
                    part.setdefault("stated", {})[name] = kind


def _not_measured_yet(parts: dict) -> None:
    """A measure parts.yaml lists for a kind that this code doesn't work out yet gets a reason, never silent
    absence: a rule reading it then needs review. (parts.yaml can gain measures before the measuring code does.)
    Guards are their own kind here, outside parts.yaml."""
    from rule_format.parts import measure_kinds
    for kind, got in parts.items():
        if kind == "guard" or not got:
            continue
        for part in got:
            for name in measure_kinds(kind):
                if name not in part["measures"] and name not in part["not_measured"]:
                    # worked out already but kept in `more` (not yet handed to the rules), or not worked out at all
                    part["not_measured"][name] = Stop("in_more_not_rules" if name in part["more"]
                                                      else "not_measured_yet").reason


def measure_file(path) -> dict:
    import yaml
    with open(path, encoding="utf-8") as f:
        return measure(yaml.safe_load(f))


__all__ = ["measure", "measure_file", "MEASURED_FORMAT", "KINDS"]
