"""The Building Code's occupant loads from each room's stated function (2025 BCNYS 1004.5 and Table 1004.5; section group
3 of docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md): plain arithmetic over the route measuring's
areas and the frozen table of occupant load factors the rulebook keeps
(new_york_state_building/5_building_code_rules/drafted/records/occupant_load_factors.yaml, every factor quoted from
its row of Table 1004.5 and checked against the page images' second reading by rule_format's tests). No AI.

    apply(parts, description, factors, building) -> parts   (the same parts, occupant loads filled where they can be)

A room states its function (`function`, one of the table's ids: docs/interior/interior_description_format.md). The
area is the room's inside its walls (`space_floor_area`):
- a function with a **net** factor: area / factor, one value;
- a **gross** factor: two readings (the coordinator's decision, 2026-11-23: pass only if both pass): the room's own
  area / factor, and that area grossed up by the story's share of what no net room holds (202 FLOOR AREA, GROSS:
  within the exterior walls, without deduction for corridors, stairways, closets, interior walls), i.e. its area x
  (the story's gross floor area - the net rooms' areas) / (the gross rooms' areas), / factor.
1004.5.1 lets a design take more occupants, up to one per 7 sq ft: unless the building states it takes no increase
(`occupant_load_increased: false`), the upper reading is at least the area / 7.

A room that is itself an exit, a corridor, or a closet or toilet with no function stated holds no occupant load of
its own (202 FLOOR AREA, NET leaves closets and toilet rooms out; a gross factor's own area takes them in). An
accessory storage room is not one of them: Table 1004.5 gives it a factor of its own (300 gross), so with no function
stated it is a room like any other (review of group 3, 2026-11-24: on a story of net rooms only, its people would
otherwise be dropped). Any other room with no function, or a
function the table sends elsewhere (fixed seating, 1004.6; concentrated business, 1004.8; bowling centers; malls,
402.8.2), leaves its load, and its story's, not measured: never a guess. A room others egress through (1004.2:
`pass_through: true`, or one a closet, storeroom or toilet is served through, the routes' `served_through`, where
that room has an occupant load of its own or one not worked out) carries their loads too: its load is the
cumulative one only where no other room's path is known to pass through it, so such a room's load is left not
measured. A room the description marks a corridor is never a space; a function stated on one, or on a space that is
itself an exit, leaves its story's load not measured (said, never dropped). Stories are not added together (1004.2.3).
A corridor's load (section group 4: Table 1020.3) is two readings, none and the whole story's, only where the
building states no other level's occupants reach its corridors (`other_level_egress_into_corridors: false`), else not
worked out (_corridor_loads).

Where a space's or story's load isn't worked out (a room's function not stated, a room others pass through), it
still has a ceiling: no occupant can take less than the densest factor Table 1004.5 gives (one per 5 sq ft net,
standing space), so a story the building states has no area counted by seats, lanes or actual load, no occupied
outdoor areas and no mezzanine can't hold more than its floor area / 5 (_bounds;
docs/decisions/2026-11-26_occupant_load_upper_bound.md proves it from the law, with the facts it needs stated). The
ceiling is given as the part's `bounds`; a rule settles on it only where the law's words are provably the same for
every load from none up to it (rule_format.parts.rows), so it never decides a rule a load under it could decide
otherwise.
"""

import math

from model_measurement.routes.stops import STOPS
from rule_format.rulebook import load

SUPPORT_USES = ("corridor", "closet", "toilet")   # no load of their own unless a function says (202 NET FLOOR AREA)
QUESTION = "occupant_load_area"
LOWER, UPPER = "room_area", "grossed_up_or_increased"
# a room's function is the architect's to set, on the room mark Revit gives it (Gordium: Function, rooms[].function:
# PR #191), so the panel asks for that mark (ui_data: "Set the room's function"), never for an occupant load to mark
FUNCTION_FIELD = "rooms[].function"
FUNCTION_ROOMS = "room_ids_without_function"   # a story's `more`: the rooms its function ask is set on (never its level)
FUNCTIONS_ONLY = "only_functions_wait"         # a story's `more`: true where its load waits on those functions alone
FUNCTION_STATED = "set the room's Table 1004.5 function (the room mark Gordium: Function)"
NOT_GIVEN = "the room's function (Table 1004.5) isn't stated, so its occupant load isn't worked out: " + FUNCTION_STATED
# the same words for a load Gordium (or a person) must work out and no mark carries (round 6): a room others pass
# through (their loads aren't summed yet), a function the table sends elsewhere; asked by hand, never as a model fix
LOAD_STATED = STOPS["stated_not_given"].format(what="the room's occupant load, worked out by hand")
STORY_STATED = STOPS["stated_not_given"].format(what="the story's occupant load, worked out by hand")
UNKNOWN = "the room's function {f!r} is none of Table 1004.5's (docs/interior/interior_description_format.md)"
ELSEWHERE = "the function {f} takes its occupant load from {where}, not a factor: " + LOAD_STATED
THROUGH = ("other rooms' egress passes through it (1004.2: their occupant loads add to its own), which isn't summed "
           "yet: ") + LOAD_STATED
SERVED = ("{names} egress{es} through it (1004.2: {their} occupant load adds to its own), which isn't summed yet: "
          + LOAD_STATED)
STORY_OPEN = "a room on the story has no occupant load worked out ({names}), so the story's isn't either"
# where a room is open for want of a stated function, the story's words ask for that function (the room mark: the
# panel's one "Set the room's function" card, selecting the rooms, never the story's level); where one is open for a
# function the table sends elsewhere, the story's load is by hand, in the routes' words (working that room's out is
# what settles the story's, whatever else is open); where every open room is so for the model's sake (its floor
# area, a function no table row has), a model fix (rounds 5, 7, 8 and 14; a room passed through or served through
# holds its own load in the story's sum, never open)
STORY_FUNCTION = ": " + FUNCTION_STATED
EXIT_FUNCTION = ("{name} is itself an exit (a door into it is an exit enclosure's or passageway's), yet states "
                 "the function {f!r}: an exit holds no occupant load of its own, so which it is isn't known")
IS_EXIT = ("it is itself an exit (an exit stair's enclosure, an exit passageway): it holds no occupant load of its own, "
           "so a rule that reads one for it is a person's check: ") + LOAD_STATED
NO_LOAD = ("a {use} with no function stated holds no occupant load of its own (202 FLOOR AREA, NET leaves closets and "
           "toilet rooms out), so a rule that reads one for it is a person's check: ") + LOAD_STATED   # never the
# Function mark, which Revit's tooltip says to leave blank on a closet or toilet (round 14)
STORY_NONE = ("no room on the story holds an occupant load of its own (its spaces are exits, closets or toilets): "
              + STORY_STATED)
GROSS_NOT_MEASURED = "the story's gross floor area isn't measured, so the gross-function rooms' share of it can't be"
AREAS_OVER = ("the story's rooms add up to more than its gross floor area (inside its exterior walls), so the "
              "gross-function rooms' share of it can't be: a room's outline may overlap another's or the walls")
# a corridor's load (section group 4): the story's bounds it only where no other level's occupants reach it
OTHER_LEVELS = "other_level_egress_into_corridors"   # the building block's fact (Revit: Gordium: Other levels reach corridors)
OTHER_LEVELS_FIELD = "building." + OTHER_LEVELS       # the field a host's mark answers, so the panel's ask is that mark
CORRIDOR_QUESTION, CORRIDOR_NONE, CORRIDOR_STORY = "corridor_occupants_served", "none", "whole_story"
CORRIDOR_BY_HAND = STOPS["stated_not_given"].format(what="the occupant load the corridor serves, worked out by hand")
CORRIDOR_NOT_RULED_OUT = ("the building doesn't say whether another level's occupants reach its corridors (an "
                          "unenclosed stairway or ramp, a mezzanine, stairs converging or discharging into one: "
                          "1004.2.2, 1004.2.3, 1005.6), so the story's occupant load doesn't bound the corridor's: say "
                          "on the building that none do (" + OTHER_LEVELS + " in the interior description; Revit: Gordium: "
                          "Other levels reach corridors), or " + CORRIDOR_BY_HAND)
CORRIDOR_OTHER_LEVELS = ("another level's occupants reach the building's corridors (an unenclosed stairway or ramp, a "
                         "mezzanine, stairs converging or discharging into one: 1004.2.2, 1004.2.3, 1005.6), so the "
                         "story's occupant load doesn't bound the corridor's: " + CORRIDOR_BY_HAND)
CORRIDOR_NO_STORY = "the story's occupant load isn't worked out, so the corridor's isn't either: " + CORRIDOR_BY_HAND
# the story's load waits on its rooms' functions (the model gives the rest): the corridor's ask is those functions, the
# room mark Gordium: Function on the rooms that lack one (its `more`: FUNCTION_ROOMS), never a load worked out by hand
CORRIDOR_NO_FUNCTION = ("the story's occupant load isn't worked out until its rooms' functions are set, so the "
                        "corridor's isn't either" + STORY_FUNCTION)
CORRIDOR_READINGS = ("given as two readings (none, the least it can serve; {load:.1f}, the whole story's, the most it "
                     "can serve): the routes don't split a story's occupants between its corridors, so a rule "
                     "reading it complies only if it complies at the whole story's load, fails only if it fails at "
                     "none")
CORRIDOR_FUNCTION = ("{name}'s use is corridor, yet it states the function {f!r}: a corridor holds no occupant load of "
                     "its own (Table 1004.5 has no corridor row), so which it is isn't known")


# ---- the ceiling on a load not worked out (docs/decisions/2026-11-26_occupant_load_upper_bound.md) ----------------
# the building facts it needs, each the building block's own (code_scope.FACTS) and each stated no: an area whose
# load no floor area bounds (Table 1004.5's rows with no factor: fixed seats in any use, 1004.6; bowling lanes; a
# concentrated business use, NY 1004.8's "actual occupant load as approved"; a mall, 402.8.2), outdoor areas whose
# people add to the building's (1004.7), or a mezzanine whose people add to a room on an adjacent level (1004.2.2)
NOT_BY_AREA, OUTDOOR, MEZZANINES = "loads_not_by_area", "occupied_outdoor_areas", "mezzanines"
NO_FACTS = (NOT_BY_AREA, OUTDOOR, MEZZANINES)
BOUND = "at_most"                 # a part's `bounds[measure]`: {BOUND: n, "why"} proven; IF_STATED: what stating
IF_STATED = "if_stated"           # the facts would prove ({BOUND: n, "why", "facts": [...]}), never a value
BOUND_WHY = ("the story's {area:,.0f} sq ft at the densest Table 1004.5 allows, one occupant per {d:g} sq ft as for "
             "standing space, whatever the rooms' functions (the building states no area counted by seats, lanes or "
             "actual load, no occupied outdoor areas and no mezzanine)")
# a row the ceiling would settle once the building states these facts (rule_format.parts.rows' `bound_facts`): each
# fact asked for, in words (panel_data's cause, the pane's ask), before the rooms' functions
BOUND_FACT_WHY = ("{what}: not stated for the project. Once {once}, the story's floor area alone can settle this: no "
                  "room holds more than one occupant per 5 sq ft, whatever its function")
BOUND_FACT_ONCE = {NOT_BY_AREA: "the building states it has no area counted by seats, lanes or actual load",
                   OUTDOOR: "the building states its occupants use no outdoor areas",
                   MEZZANINES: "the building states it has no mezzanine"}


def densest(factors: dict) -> float | None:
    """The fewest square feet per occupant any function of Table 1004.5 gives, or 1004.5.1's increase allows (its
    7): no room's occupant load, worked out from its area, can be more than its area divided by this."""
    got = [e["factor"] for e in factors["functions"].values() if isinstance(e.get("factor"), (int, float))
           and not isinstance(e.get("factor"), bool) and e["factor"] > 0]
    cap = factors.get("increase_cap")
    if isinstance(cap, (int, float)) and not isinstance(cap, bool) and cap > 0:
        got.append(cap)
    return min(got) if got else None


def _area(part: dict, name: str):
    v = part["measures"].get(name)
    if name in (part.get("not_measured") or {}) or isinstance(v, bool) or not isinstance(v, (int, float)) \
            or not v == v or v < 0 or v == float("inf"):
        return None
    return v


def _bounds(story: dict, mine: list, rooms: dict, factors: dict, building: dict | None, corridor_ids=()) -> None:
    """The ceiling on the story's occupant load, and on each of its spaces' (a space's load, its intervening rooms'
    added by 1004.2.1, is part of its story's; 1004.2.3 adds no other story's), set as `bounds` on each that has no
    value or readings: {BOUND: n, "why"} where the building states each of NO_FACTS no, and {IF_STATED: {BOUND: n,
    "why", "facts"}} where stating the ones not yet stated would. n is the story's floor area (the larger of its gross
    floor area and its spaces' areas added) divided by the densest factor, rounded up (an occupant load is a number of
    persons). None at all where a room's stated function has no factor or isn't the table's, where the story's or a
    space's area isn't measured, or where the building states one of NO_FACTS yes."""
    b = building if isinstance(building, dict) else {}
    d = densest(factors)
    gross = _area(story, "story_gross_floor_area")
    areas = [_area(p, "space_floor_area") for p in mine]
    if d is None or gross is None or any(a is None for a in areas):
        return
    for rid in [p["id"] for p in mine] + list(corridor_ids):    # a function stated on a corridor counts too
        fn = (rooms.get(rid) or {}).get("function")
        if fn is None:
            continue
        f = ((factors["functions"].get(fn) if isinstance(fn, str) else None) or {}).get("factor")
        if isinstance(f, bool) or not isinstance(f, (int, float)) or f <= 0:
            return
    missing = []
    for fact in NO_FACTS:
        if b.get(fact) is True:
            return
        if b.get(fact) is not False:                  # not stated, or not yes or no: never "none"
            missing.append(fact)
    area = max(gross, sum(areas))
    n = math.ceil(area / d - 1e-9)
    entry = {BOUND: n, "why": BOUND_WHY.format(area=area, d=d)}
    got = entry if not missing else {IF_STATED: {**entry, "facts": missing}}
    for part, name in [(story, "story_occupant_load")] + [(p, "space_occupant_load") for p in mine]:
        if name in part["measures"] or (part.get("readings") or {}).get(name):
            continue
        part.setdefault("bounds", {})[name] = {k: dict(v) if isinstance(v, dict) else v for k, v in got.items()}


def factors_of(path) -> dict:
    """{function id: {"factor": number or None, "area": "gross"|"net"|None, "elsewhere": section or None}} and the
    1004.5.1 cap, from the rulebook's frozen table."""
    data = load(path)
    return {"functions": data["functions"], "increase_cap": data["increase_cap"]["sq_ft_per_occupant"]}


UNREAD_ROOMS = ("a room of the description can't be read (not a room, an id that isn't text, or an id two rooms "
                "share), so which room each occupant load is isn't known and no story's total is: never one with a "
                "room left out")


def readable_rooms(description) -> tuple[dict, bool]:
    """The description's rooms by id, and whether every room was read: a room that isn't a mapping, or whose id
    isn't text or is two rooms', is never indexed (an id of any other kind can't be a key, and two can't share one)
    and makes the second False."""
    given = (description or {}).get("rooms") if isinstance(description, dict) else None
    if not isinstance(given, list):
        return {}, given is None
    ids = [r.get("id") if isinstance(r, dict) else None for r in given]
    texts = [i for i in ids if isinstance(i, str)]
    shared = {i for i in texts if texts.count(i) > 1}
    rooms = {r["id"]: r for r in given if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"] not in shared}
    return rooms, len(rooms) == len(given)


# Seating served by aisles (BCNYS 1030.7, p.354, lines 50-51: "Where aisles are provided for seating, the distance shall
# be measured along the aisles and aisle accessways without travel over or on the seats"), fixed seats or loose ones
# alike (1030.9: every occupied portion of a room or space used for assembly purposes that contains seats, tables,
# displays, similar fixtures or equipment has aisles; 1030.13.1: aisle accessways for seating at tables). The seats
# aren't drawn, so the routes measure a story's travel and a space's common path straight across them. Table 1004.5's
# rows under its "Assembly" heading (p.312, lines 20-27) name a room used for assembly purposes; its other rows a room
# may be one of (303.1 "awaiting transportation", 303.4's courtrooms, gymnasiums, indoor swimming pools, libraries and
# terminal waiting areas, 303.5's rinks and pools with spectator seating, 303.2's theaters' stages) may or may not be.
ASSEMBLY_FUNCTIONS = ("gaming_floor", "exhibit_gallery_museum", "assembly_fixed_seats", "assembly_concentrated",
                      "assembly_standing", "assembly_unconcentrated", "bowling_center")
ASSEMBLY_LIKE_FUNCTIONS = ("courtroom", "library_reading_room", "exercise_room", "rink_pool", "pool_deck",
                           "stage_platform", "airport_waiting")
SEATING_STORY, SEATING_SPACE = "story_assembly_seating_possible", "space_assembly_seating_possible"


def _may_seat(room: dict, functions: dict, is_exit=None) -> bool:
    """Whether a room may hold seating served by aisles: a function under Table 1004.5's Assembly heading or one that may
    be an assembly use, no function stated (but a corridor, closet or toilet with none, or a room that is itself an
    exit with none), or a function that is none of the table's. Only a room stating another of the table's functions
    is ruled out (a residential, business or mercantile room). A room that is itself an exit yet states a function is
    one whose use isn't known (EXIT_FUNCTION), so it may seat people (review round 3)."""
    fn = room.get("function")
    if is_exit is True:
        return fn is not None
    if fn is None:
        return room.get("use") not in SUPPORT_USES
    if not isinstance(fn, str) or fn not in functions:
        return True
    return fn in ASSEMBLY_FUNCTIONS or fn in ASSEMBLY_LIKE_FUNCTIONS


def assembly_seating(parts: dict, description: dict, factors: dict, building: dict | None = None) -> dict:
    """story_assembly_seating_possible on each story, and space_assembly_seating_possible (its story's) on each of the
    story's spaces: true where a room on the story may hold seating served by aisles (_may_seat), so the travel and
    common-path rows need review there (1030.7: measured along the aisles, never over the seats the routes measure
    across); false only where every room on the story states one of Table 1004.5's other functions, but its exits and
    its corridors, closets and toilets, which state none. True where an exit or a corridor on the story states a
    function: its use and its function clash, so which it is isn't known (EXIT_FUNCTION, CORRIDOR_FUNCTION; review
    rounds 3 and 4). True on every story where a room can't be read or placed on a story, or the description lists an
    enclosed space with no room drawn in it (its use isn't known): never false on a room unseen. True on every story,
    too, where the building is stated Group A (an assembly use, 303.1 to 303.6) and no room but such a clashing one
    states an Assembly function or one that may be an assembly use: its assembly room isn't shown, so any room may be
    it (review round 1). The story knows its rooms (it is in the model), so a floor the model leaves out doesn't matter
    here."""
    rooms, every = readable_rooms(description)
    unknown = description.get("unknown_spaces") if isinstance(description, dict) else None
    spaces = [p for p in parts.get("space") or [] if isinstance(p, dict)]
    corridors = [c for c in parts.get("corridor") or [] if isinstance(c, dict)]
    placed = {p.get("id") for p in spaces + corridors}
    unseen = not every or bool(unknown) or any(r not in placed for r in rooms)
    # an exit or a corridor stating a function: its use isn't known, and it shows no assembly room
    aside = ({p.get("id") for p in spaces if p["measures"].get("space_is_exit") is True}
             | {c.get("id") for c in corridors})
    clash = {i for i in aside if (rooms.get(i) or {}).get("function") is not None}
    groups = building.get("occupancy_groups") if isinstance(building, dict) else None
    shown = any(r.get("function") in ASSEMBLY_FUNCTIONS + ASSEMBLY_LIKE_FUNCTIONS for i, r in rooms.items()
                if isinstance(r.get("function"), str) and i not in clash)
    if isinstance(groups, list) and any(isinstance(g, str) and g.startswith("A-") for g in groups) and not shown:
        unseen = True
    functions = factors["functions"]
    for story in parts.get("story") or []:
        mine = [p for p in spaces if p.get("within") == story["id"]]
        here = {p.get("id") for p in mine} | {c.get("id") for c in corridors if c.get("within") == story["id"]}
        possible = unseen or bool(here & clash) or any(
            _may_seat(rooms.get(p.get("id")) or {}, functions, p["measures"].get("space_is_exit")) for p in mine)
        _set(story, SEATING_STORY, possible)
        for p in mine:
            _set(p, SEATING_SPACE, possible)
    stories = {s.get("id") for s in parts.get("story") or []}
    for p in spaces:                                # a space no story holds: its story's rooms aren't known
        if p.get("within") not in stories:
            _set(p, SEATING_SPACE, True)
    return parts


def _set(part: dict, name: str, value: bool) -> None:
    """The value, and the routes' "not measured yet" for it taken away (a measure with a reason is never read)."""
    part.setdefault("measures", {})[name] = value
    if isinstance(part.get("not_measured"), dict):
        part["not_measured"].pop(name, None)


def apply(parts: dict, description: dict, factors: dict, building: dict | None, stated: dict | None = None) -> dict:
    """`stated`: every building fact the rules read (the description's block over the check's values), for the
    assembly seating's occupancy groups; `building` alone otherwise."""
    assembly_seating(parts, description, factors, building if stated is None else stated)
    rooms, every = readable_rooms(description)
    increase_ruled_out = isinstance(building, dict) and building.get("occupant_load_increased") is False
    cap = factors["increase_cap"]
    spaces = parts.get("space") or []
    corridors = {c["id"]: c for c in parts.get("corridor") or [] if isinstance(c, dict) and "id" in c}
    for story in parts.get("story") or []:
        if not every:                                    # a room left out: no load is known, never a smaller one
            for p in [p for p in spaces if p.get("within") == story["id"]]:
                p["not_measured"]["space_occupant_load"] = UNREAD_ROOMS
            story["not_measured"]["story_occupant_load"] = UNREAD_ROOMS
            _corridor_loads(story, [c for c in corridors.values() if c.get("within") == story["id"]], building)
            continue
        mine = [p for p in spaces if p.get("within") == story["id"]]
        gross = story["measures"].get("story_gross_floor_area")
        loads, open_, lacking = [], [], []
        plan = []
        odd = [CORRIDOR_FUNCTION.format(name=c.get("name") or cid, f=rooms[cid]["function"])   # never dropped
               for cid, c in corridors.items() if c.get("within") == story["id"]
               and (rooms.get(cid) or {}).get("function") is not None]
        for p in mine:
            room = rooms.get(p["id"]) or {}
            fn = room.get("function")
            area = p["measures"].get("space_floor_area")
            if p["measures"].get("space_is_exit") or (fn is None and room.get("use") in SUPPORT_USES):
                if p["measures"].get("space_is_exit") and fn is not None:      # a mark against a function: said
                    odd.append(EXIT_FUNCTION.format(name=p.get("name") or p["id"], f=fn))
                p["not_measured"]["space_occupant_load"] = (IS_EXIT if p["measures"].get("space_is_exit") else
                                                            NO_LOAD.format(use=room["use"].replace("_", " ")))
                plan.append((p, None, None))
                continue
            entry = factors["functions"].get(fn) if isinstance(fn, str) else None
            if area is None or entry is None or entry.get("factor") is None:
                why = ("the room's floor area isn't measured" if area is None else NOT_GIVEN if fn is None else
                       UNKNOWN.format(f=fn) if entry is None else ELSEWHERE.format(f=fn, where=entry["elsewhere"]))
                p["not_measured"]["space_occupant_load"] = why
                open_.append((p.get("name") or p["id"], why))
                if why == NOT_GIVEN:                      # the rooms the story's function ask is set on (round 14)
                    lacking.append(p["id"])
                continue
            plan.append((p, entry, area))
        net_area = sum(a for _, e, a in plan if e and e["area"] == "net")
        gross_area = sum(a for _, e, a in plan if e and e["area"] == "gross")
        share = ((gross - net_area) / gross_area) if (gross is not None and gross_area > 0 and gross >= net_area +
                                                     gross_area) else None
        no_load = {id(p) for p, e, _ in plan if e is None}          # exits, and support rooms with no function
        host_of = {p["id"]: (p.get("more") or {}).get("served_through") for p in mine}
        served = {}     # room id -> the rooms served through it, or through a room served through it (a chain: a
        for p in mine:  # closet off a storeroom off a kitchen), each with a load or one not worked out
            if id(p) in no_load:
                continue
            host, seen = host_of.get(p["id"]), set()
            while host is not None and host not in seen:
                seen.add(host)
                served.setdefault(host, []).append(p.get("name") or p["id"])
                host = host_of.get(host)
        no_share = GROSS_NOT_MEASURED if gross is None else AREAS_OVER
        for p, e, a in plan:
            if e is None:
                if p["id"] in served:                 # a closet others are served through: theirs is its load
                    names = served[p["id"]]
                    p["not_measured"]["space_occupant_load"] = SERVED.format(
                        names=", ".join(names), es="" if len(names) > 1 else "es",
                        their="their" if len(names) > 1 else "its")
                continue
            low = a / e["factor"]
            high = (a * share / e["factor"]) if e["area"] == "gross" and share is not None else \
                (None if e["area"] == "gross" else low)
            if high is not None and not increase_ruled_out:
                high = max(high, a / cap)
            room = rooms.get(p["id"]) or {}
            if room.get("pass_through") or p["id"] in served:
                names = served.get(p["id"]) or []
                p["not_measured"]["space_occupant_load"] = THROUGH if room.get("pass_through") else SERVED.format(
                    names=", ".join(names), es="" if len(names) > 1 else "es", their="their" if len(names) > 1 else "its")
                loads.append((low, high))
                continue
            loads.append((low, high))
            _give(p, "space_occupant_load", low, high, no_share)
        if open_ or odd:
            if lacking:                               # the story's ask for a function names these rooms, not the level
                story.setdefault("more", {}).setdefault("story_occupant_load", {})[FUNCTION_ROOMS] = lacking
            if lacking and not odd and all(w == NOT_GIVEN for _, w in open_):
                # only functions wait: setting them works the story's load out (a corridor's ask is them alone)
                story["more"]["story_occupant_load"][FUNCTIONS_ONLY] = True
            story["not_measured"]["story_occupant_load"] = "; ".join(
                ([STORY_OPEN.format(names=", ".join(n for n, _ in open_))
                  + (STORY_FUNCTION if any(w == NOT_GIVEN for _, w in open_) else
                     ": " + STORY_STATED if any(w.endswith(LOAD_STATED) for _, w in open_) else "")]
                 if open_ else []) + odd)
        elif loads:
            low = sum(x for x, _ in loads)
            high = None if any(h is None for _, h in loads) else sum(h for _, h in loads)
            if high is not None and not increase_ruled_out and gross is not None:
                high = max(high, gross / cap)
            _give(story, "story_occupant_load", low, high, no_share)
        else:
            story["not_measured"]["story_occupant_load"] = STORY_NONE
        _bounds(story, mine, rooms, factors, building,
                [cid for cid, c in corridors.items() if c.get("within") == story["id"]])
        _corridor_loads(story, [c for c in corridors.values() if c.get("within") == story["id"]], building)
    return parts


def _corridor_loads(story: dict, mine: list, building: dict | None) -> None:
    """Each corridor's occupant load (1020.3, Table 1020.3; 1005.3.2): the occupants whose egress the corridor
    serves, which the routes don't split between a story's corridors. It is bounded by the story's own load only
    where no other level's occupants can reach the corridor: 1004.2.3 adds no other story's load "other than for
    the egress components designed for convergence in accordance with Section 1005.6", and 1004.2.2 adds a
    mezzanine's to the room or space below it, so the bound holds only where the building states that no
    unenclosed stairway or ramp, mezzanine, convergence or exit discharge brings another level's occupants into
    a corridor (`other_level_egress_into_corridors: false`). Then two readings: none (the least it can serve) and
    the whole story's (its upper reading): a rule reading it passes only at the whole story's load and fails only
    at none, else needs review. Otherwise not worked out, with why (never the story's load as if it were the
    corridor's)."""
    if not mine:
        return
    bounded = isinstance(building, dict) and building.get(OTHER_LEVELS) is False
    load = story["measures"].get("story_occupant_load")
    if load is None:
        got = [r["value"] for r in (story.get("readings") or {}).get("story_occupant_load") or []
               if isinstance(r.get("value"), (int, float))]
        load = max(got) if got else None
    for c in mine:
        c["measures"].pop("corridor_occupant_load", None)
        if not bounded:
            c["not_measured"]["corridor_occupant_load"] = (CORRIDOR_OTHER_LEVELS if isinstance(building, dict) and
                                                           building.get(OTHER_LEVELS) is True else
                                                           CORRIDOR_NOT_RULED_OUT)
        elif load is None:
            held = (story.get("more") or {}).get("story_occupant_load") or {}
            lacking = held.get(FUNCTION_ROOMS) if held.get(FUNCTIONS_ONLY) is True else None
            c["not_measured"]["corridor_occupant_load"] = CORRIDOR_NO_FUNCTION if lacking else CORRIDOR_NO_STORY
            if lacking:                               # the rooms the function ask is set on (never the corridor)
                c.setdefault("more", {}).setdefault("corridor_occupant_load", {})[FUNCTION_ROOMS] = list(lacking)
        else:
            c.setdefault("readings", {})["corridor_occupant_load"] = [
                {"value": 0, "named": {CORRIDOR_QUESTION: CORRIDOR_NONE}},
                {"value": load, "named": {CORRIDOR_QUESTION: CORRIDOR_STORY}}]
            c["not_measured"]["corridor_occupant_load"] = CORRIDOR_READINGS.format(load=load)


def _give(part: dict, name: str, low: float, high: float | None, no_share: str) -> None:
    """One value where the readings agree; two named readings where they differ; none where the upper one can't
    be worked out (the gross share isn't known: `no_share` says why)."""
    if high is None:
        part["not_measured"][name] = no_share
        return
    part["not_measured"].pop(name, None)
    if abs(high - low) < 1e-9:
        part["measures"][name] = low
        return
    part.setdefault("readings", {})[name] = [{"value": low, "named": {QUESTION: LOWER}},
                                             {"value": high, "named": {QUESTION: UPPER}}]
    part["not_measured"][name] = (f"given as two readings ({low:.1f} from the room's own area; {high:.1f} grossed "
                                  f"up by the story's corridors, stairs and walls, or at one occupant per 7 sq ft "
                                  f"where 1004.5.1's increase isn't ruled out): a rule reading it complies only if it "
                                  f"complies under both, fails only if it fails under both")
