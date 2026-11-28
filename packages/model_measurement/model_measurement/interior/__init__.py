"""Measuring the inside of a house for egress (escape openings, stairs, guards, the exit door), from a host-neutral
interior description. Plain code written by engineers, no AI (principle 6): same description, same numbers.

    measure(description, whole=None, stated_stories=None)
        -> {"parts": {kind: [part, …] | None}, "problems": [...], "not_checked": [...], "refused"?: {kind: why}, …}

`parts` is exactly what rule_format.parts.rows reads: each part {"id", "name", "within"?, "measures"}, measures
named as rule_format/parts.yaml names them, in inches and square feet. A kind not given in the description is None
(not read, so its rules need review), never an empty list; [] means the description says there are none, unless
that is refused beside what it shows ("no stairs" beside more than one floor: _stairs_against_floors; the stairs
are then None and `refused` says why, {"stair": the reason}). A
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
from model_measurement.interior.read import FORMAT, INCHES, Reader, name_of, tidy, yes_no
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


SAME_FLOOR = 0.5      # in: rooms' floors this close are one floor (a threshold's change in level, never a step)
LANDING_STEP = 8.25   # in: RCNYS R318.3.1's exception and R318.3.2, the most a door's outside landing may be below
#                       it; a floor farther above any ground given is reached by a stair or a ramp (or its own way
#                       out at grade, not shown)
# the house code's (RCNYS) landing bounds, (most below the floor, most above): the Building Code's are tighter
# (BUILDING_LANDING), and a check under it passes those (egress._stairs_and_guards)
GROUND_ABOVE = 1.5    # in: R318.3.1, the inside floor at most 1 1/2 in below the threshold, and no landing above it
#                       (a landing over the threshold is a riser, R202 STAIR): ground higher above the floor than this
#                       puts the landing below grade, so a ramp or a stairway to grade (R318.3.1's last sentence)


def _level_id(value):
    """A level's id as the description gives it: text with something in it, or a whole number (never a yes/no)."""
    return value if isinstance(value, str) and value.strip() or type(value) is int else None


HOUSE_LANDING = (LANDING_STEP, GROUND_ABOVE)
# BCNYS 1010.1.4: a door's floor or landing at the same elevation on each side, within 1/2 in (exception 4); its
# looser steps (exceptions 2, 3 and 6: 7 and 7 3/4 in) each turn on what the model doesn't show (a door off an
# accessible route and not swinging over the landing, units not required Accessible, Type A or B, an equipment
# space), so the strict 1/2 in; 1010.1.6: thresholds at most 1/2 in. Gordium's reading: within 1/2 in either way
BUILDING_LANDING = (0.5, 0.5)
_INCHES = {8.25: "8 1/4", 1.5: "1 1/2", 0.5: "1/2"}


def _inches(v: float) -> str:
    return _INCHES.get(v, f"{v:g}")


def _stairs_against_floors(whole, reader, stated_stories=None, landing=HOUSE_LANDING) -> str | None:
    """Why "no stairs" (an empty list of stairs) can't be taken beside what the description shows, or None. A stair
    or a ramp joins floors, or each floor has its own way out at grade, which the model doesn't show, so where the
    building may have more than one floor the claim needs review, never a stair rule set aside:
    - its rooms, enclosed spaces with no room drawn (`unknown_spaces`) or stories' exterior walls (`story_outlines`)
      are on two or more `level`s (as the Building Code's description and the Revit add-in place them), named from
      `levels` where it names them;
    - a level given that can't be read (it may be another floor);
    - its floors are more than 1/2 in apart (a room's `floor_elevation`, as a house's gives them; a room with none,
      and an enclosed space, at its level's height in `levels`; a change of floor that size is a step, or a ramp),
      or a floor or level height given can't be read (it may be on another floor);
    - a ground given outside the openings (`ground_outside`) is farther from a floor than a landing allows
      (`landing`: below the highest floor and above the lowest; HOUSE_LANDING, 8 1/4 in below and 1 1/2 in above,
      R318.3.1 and R318.3.2; BUILDING_LANDING, 1/2 in either way, BCNYS 1010.1.4 and 1010.1.6): only an upper floor
      drawn, a floor sunk below the ground, or sloped ground a landing can't meet. Which ground the way out is on
      isn't known, so every ground given must allow no stair; a ground given that can't be read may be any, so it
      refuses too (with no floor given, grounds farther apart than both bounds together, which no floor can meet);
    - the check gives two or more stories (`stated_stories`: a count, or (count, whose words with {n}),
      design_checker.egress._stated_stories).
    Rooms with neither level nor floor given show nothing against it (not given is never a second floor)."""
    count, said = stated_stories if isinstance(stated_stories, tuple) else \
        (stated_stories, "the check gives the building {n} stories")
    if (type(count) is int or type(count) is float and math.isfinite(count)) and count >= 2:   # any whole number
        n = str(count) if type(count) is int else f"{count:g}"
        return Stop("stairs_none_several_floors", what=said.format(n=n)).reason
    if not isinstance(whole, dict):
        return None
    rooms = [r for r in whole.get("rooms") if isinstance(r, dict)] if isinstance(whole.get("rooms"), list) else []
    spaces = [u for u in whole.get("unknown_spaces") if isinstance(u, dict)] \
        if isinstance(whole.get("unknown_spaces"), list) else []
    # each story's exterior walls (`story_outlines`, the Building Code's description): a story drawn with no room
    # placed yet is a floor too (the merge with #231's stair rules: upper walls drawn, rooms not yet)
    outlines = [o for o in whole.get("story_outlines") if isinstance(o, dict)] \
        if isinstance(whole.get("story_outlines"), list) else []
    odd = next((p for p in rooms + spaces + outlines if p.get("level") is not None and _level_id(p["level"]) is None),
               None)
    if odd is not None:                    # a level given that can't be read may be another floor (round 3)
        return Stop("stairs_none_several_floors", what=f"{name_of(odd)}'s level can't be read, so it may be on "
                                                       "another floor").reason
    on_rooms = {_level_id(r.get("level")) for r in rooms} - {None}
    levels = on_rooms | ({_level_id(u.get("level")) for u in spaces + outlines} - {None})
    listed = {}                        # the description's levels by id (`levels`: {id, name, elevation})
    for lv in whole.get("levels") if isinstance(whole.get("levels"), list) else []:
        if isinstance(lv, dict) and _level_id(lv.get("id")) is not None:
            listed[lv["id"]] = lv
    if len(levels) > 1:

        def named(level_id):
            lv = listed.get(level_id) or {}
            name = lv.get("name") if isinstance(lv.get("name"), str) and lv["name"].strip() else str(level_id)
            z = lv.get("elevation")
            return (0, z, name) if type(z) in (int, float) and math.isfinite(z) else (1, 0, name)
        order = [n for _, _, n in sorted(named(lv) for lv in levels)]
        shown = " and ".join(order) if len(order) <= 3 else ", ".join(order[:3]) + f" and {len(order) - 3} more"
        who = "its rooms are" if levels == on_rooms else \
            "its rooms, and enclosed spaces with no room drawn, are" if not outlines else \
            "its rooms, enclosed spaces with no room drawn and stories' exterior walls are"
        return Stop("stairs_none_several_floors", what=f"{who} on {len(order)} levels ({shown})").reason
    floors = []
    # a room with no floor given, or an enclosed space, stands at its level's height where `levels` gives one (rounds
    # 3 and 4): a height given that can't be read may be another floor, as a room's floor that can't be
    for p in spaces + [r for r in rooms if r.get("floor_elevation") is None]:
        lv = listed.get(_level_id(p.get("level"))) if _level_id(p.get("level")) is not None else None
        if lv is None or lv.get("elevation") is None:
            continue
        try:
            floors.append((reader.length(lv["elevation"], "a level's elevation"), name_of(p)))
        except Stop:
            return Stop("stairs_none_several_floors", what=f"the height of {name_of(p)}'s level can't be read, so "
                                                           "it may be on another floor").reason
    for r in rooms:
        if r.get("floor_elevation") is None:
            continue
        try:
            floors.append((floor_elevation(r, reader), name_of(r)))
        except Stop:
            return Stop("stairs_none_several_floors", what=f"{name_of(r)}'s floor height can't be read, so it may "
                                                           "be on another floor").reason
    if floors:
        (low, low_name), (high, high_name) = min(floors), max(floors)
        if high - low > SAME_FLOOR:
            return Stop("stairs_none_several_floors", what=f"its rooms' floors are at different heights ({low_name}'s "
                                                           f"at {tidy(low):g} in, {high_name}'s at {tidy(high):g} "
                                                           "in)").reason
        below, above = landing
        grounds = _grounds(whole, reader)
        if grounds is None:
            return Stop("stairs_none_several_floors", what="the ground outside an opening can't be read, so it may "
                                                           "be farther from the floor than a landing can meet").reason
        if grounds and high - min(grounds) > below:            # the highest floor's way out, as any floor's
            return Stop("stairs_none_several_floors", what=f"its floor ({high_name}'s, at {tidy(high):g} in) is "
                                                           f"more than {_inches(below)} in above the ground outside "
                                                           f"an opening (at {tidy(min(grounds)):g} in)").reason
        if grounds and max(grounds) - low > above:
            return Stop("stairs_none_several_floors", what=f"its lowest floor ({low_name}'s, at {tidy(low):g} in) is "
                                                           f"more than {_inches(above)} in below the ground outside "
                                                           f"an opening (at {tidy(max(grounds)):g} in)").reason
        return None
    grounds = _grounds(whole, reader)          # no floor height given: ground farther apart than any one floor can
    if grounds is None:                        # meet needs a stair or a ramp; one that can't be read may be any
        return Stop("stairs_none_several_floors", what="the ground outside an opening can't be read, so it may "
                                                       "be farther from the floor than a landing can meet").reason
    if grounds and max(grounds) - min(grounds) > sum(landing):
        return Stop("stairs_none_several_floors", what=f"the ground outside its openings is {tidy(min(grounds)):g} "
                                                       f"in at one and {tidy(max(grounds)):g} in at another, more "
                                                       f"than any one floor can meet ({_inches(landing[0])} in "
                                                       f"above, {_inches(landing[1])} in below)").reason
    return None


def _grounds(whole: dict, reader):
    """Every ground given outside an opening (`ground_outside`, one value or a list), in inches ([] where none is
    given); None where one given can't be read: then any ground may be there, so "no stairs" is never taken beside
    it (every ground must allow no stair, above or below the floor)."""
    got = []
    for o in whole.get("openings") if isinstance(whole.get("openings"), list) else []:
        if not isinstance(o, dict) or o.get("ground_outside") is None:
            continue
        for g in o["ground_outside"] if isinstance(o["ground_outside"], list) else [o["ground_outside"]]:
            try:
                got.append(reader.length(g, "the ground outside an opening"))
            except Stop:
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


def measure(description, whole=None, stated_stories=None, landing=HOUSE_LANDING) -> dict:
    """The description measured (the module's account). An empty list of stairs is read against the floors
    (_stairs_against_floors): those of `whole`, where the description given isn't the whole one (the Building
    Code's stairs and guards are measured on a description with its rooms left out; None: the description itself),
    and `stated_stories`, the stories the check gives (a count, or (count, whose words with {n}); None: none);
    `landing`: how far (in) the ground may be below and above a floor with no stair (HOUSE_LANDING, the Residential
    Code's; BUILDING_LANDING for the Building Code's)."""
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
    claims, claims_refused = none_of.read(description)
    problems += claims_refused

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
    against = None
    if stairs == []:                                  # "no stairs": never beside rooms on more than one floor
        against = _stairs_against_floors(description if whole is None else whole, reader, stated_stories,
                                         landing)
        if against:
            problems.append(against)
            out.setdefault("refused", {})["stair"] = against     # the rows say "no stairs" wasn't taken, and why
            stairs = None
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
            why = against or Stop("not_read", what="stairs", key="stairs").reason   # "none" refused: says why
            flights = {g.get("stair"): why for g in guards if isinstance(g.get("stair"), str)}
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
