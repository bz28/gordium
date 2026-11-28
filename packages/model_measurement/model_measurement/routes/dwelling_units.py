"""The dwelling units on a story, worked out from the model: `story_dwelling_units`, which Table 1006.3.4(1) of the
2025 Building Code of New York State reads ("MAXIMUM NUMBER OF DWELLING UNITS": 4 on a story with one exit, Group
R-2; p.317).

    units_on(story, items, is_exit, stair_in) -> int, or raises Stop (not measured, with its reason)

The law: DWELLING UNIT (202, p.41): "A single unit providing complete, independent living facilities for one or more
persons, including permanent provisions for living, sleeping, eating, cooking and sanitation." 1016.2.1 (p.341):
"each tenant space, dwelling unit and sleeping unit shall be provided with access to the required exits without
passing through adjacent tenant spaces, dwelling units and sleeping units."

How (docs/decisions/2026-11-25_story_facts_from_the_model.md, step 3):
- The shared spaces are the corridors and lobbies (a room's `use`) and the rooms that are exits (a stair enclosure,
  an exit passageway), and the outside. Every other room belongs to a group: rooms joined by doors or passages
  without crossing a shared space.
- A group is a dwelling unit where one of its rooms states the function residential (Table 1004.5, the room mark
  Gordium: Function) and every lived-in room (not a toilet, closet or storeroom) states one. A group whose lived-in
  rooms all state a listed other function (NOT_DWELLING) is no dwelling unit; one with a room stating none, or one not
  on the list (a typo, dormitory, institutional sleeping), may be one: not measured.
- A group with a stair, ramp or ladder within it (or one not read, or not said to be none, or said to be none where
  the building may have another story: it may be anywhere; routes._stair_points), or with a closet, toilet or
  storeroom, or a room not itself residential, opening onto two or more of its rooms, may hold the upper part of a
  unit whose door is downstairs, or two units sharing that room: not measured.
- A dwelling unit reaches the exits without passing through another (1016.2.1), so a group with one way out to a
  shared space is one unit: Gordium's reading, to confirm, said with every row reading the count (`rests_on`, RESTS_ON),
  which also says the count holds only if 1016.2.1 is met (a flag, a person's check, in every Group R-2 answer). It
  never holds a pass: a second unit drawn with no door of its own would break 1016.2.1 itself. A group with
  two or more such doors may be two units joined by a door (a lock-off): not measured. One with none reaches the
  exits only through another story (a unit on two stories) or not at all: not measured.
- Not measured either where the story's routes aren't read (a room or door not read, an enclosed space with no room
  drawn in it: it may be a unit), or a room has no `use` (it may be a corridor).
- A unit marked shared space would drop out of the count: a room taken as an exit that states a function (an exit has
  none), or a corridor or lobby stating a function a dwelling unit may have (residential, or one not on the list)
  that opens into no room of a dwelling unit (only into halls, exits, the outside, or a toilet or closet of its own),
  leaves it not measured. One so marked stating no function
  can't be told from a real corridor or exit: the words beside the count name it.
Never a guess: a count too low could pass a one-exit story Table 1006.3.4(1) allows only up to 4 units.

Where any room of the story carries the architect's unit mark (`rooms[].unit`, Revit's room mark Gordium: Unit: the
name of the dwelling unit the room belongs to), the marks replace the grouping above (`_marked`): each name is one
dwelling unit, said with the count as the architect's statement (`architect_stated`, MARKED). The marks need no
function, no single way out and no 1016.2.1 for the count, so the two limits above close: a shared room marked
residential no longer joins two units (with no unit mark, it stops the count until it is marked a unit or a corridor
or lobby), and a unit's room marked a corridor or lobby still counts by its mark (one the drawing takes as an exit
stops the count: the two disagree). Not measured where the marks
and the drawing disagree or don't settle it:
- a room whose mark isn't a name (not text or a whole number), or names two or more units ("1A, 1B"), or two names
  differing only in capitals or in where spaces stand ("Apt 1", "apt1": one unit or two?; spaces at the ends and
  repeated spaces are no new name);
- a unit whose rooms on the story come apart (not joined by doors or passages through its own rooms: two units given
  one name?), or whose lived-in rooms all state a listed other use (no dwelling unit), or a room the drawing takes as
  an exit (a stair enclosure) given a unit;
- a lived-in room with no mark that may be a dwelling unit's (any function but a listed other use, or none): a unit
  left unmarked, or a room shared between units not marked a corridor or lobby; a corridor or lobby with no mark
  stating such a function that opens into rooms of fewer than two named units (a shared residential lobby opens into
  two or more), or an exit with no mark stating any.
What is left is said with the count (MARKED: every room of a dwelling unit carries its unit's name): a unit none of
whose rooms is marked, all of them marked corridors, lobbies or exits, can't be told from shared halls where they
state no function, or a residential one and open into rooms of two or more named units (as a shared lobby does).
"""

import re

from model_measurement.routes.floor import OUTSIDE
from model_measurement.routes.spaces import spaces
from model_measurement.routes.stops import Stop

NOT_LIVED_IN = ("toilet", "closet", "accessory_storage")
RESIDENTIAL = "residential"
# Table 1004.5's functions a dwelling unit's rooms can't all be (rooms.function, the interior format's list; tied to
# new_york_state_building's drafted/records/occupant_load_factors.yaml by test): every one but residential and the two
# sleeping ones (a dwelling unit's bedrooms may be marked so). A function not listed here (a typo, a value not on the
# table, dormitory, institutional sleeping) never rules a group out: not measured
NOT_DWELLING = frozenset({
    "accessory_storage_mechanical", "agricultural", "aircraft_hangar", "airport_baggage_claim",
    "airport_baggage_handling", "airport_concourse", "airport_waiting", "assembly_concentrated", "assembly_fixed_seats",
    "assembly_standing", "assembly_unconcentrated", "bowling_center", "business", "classroom", "commercial_kitchen",
    "concentrated_business", "courtroom", "day_care", "exercise_room", "exhibit_gallery_museum", "gaming_floor",
    "h5_fabrication", "industrial", "information_technology", "inpatient_treatment", "library_reading_room",
    "library_stack", "locker_room", "mall", "mercantile", "outpatient", "parking_garage", "pool_deck", "rink_pool",
    "stage_platform", "storage_stock_shipping", "vocational_shop", "warehouse"})
QUOTE_1016_2_1 = ("each tenant space, dwelling unit and sleeping unit shall be provided with access to the required "
                  "exits without passing through adjacent tenant spaces, dwelling units and sleeping units")
# said with every row reading the count (parts.yaml `rests_on`): the reading it stands on, and the rule that must hold
# for it (shown always, a person's check: general.bc_1016_2_1_multiple_tenants), never holding a pass
RESTS_ON = ("Gordium's reading, to confirm: each group of rooms with a residential room and one way out to the "
            "corridors, lobbies, exits or outside is one dwelling unit. It holds only if every room shared between "
            "dwelling units is marked a corridor or lobby (a shared vestibule or landing marked residential would join "
            "two units into one), no room of a dwelling unit is marked a corridor, lobby or exit (a unit so marked "
            "would be left out of the count), and BCNYS 1016.2.1 (p.341) is met: \"" + QUOTE_1016_2_1 + "\"")
UNIT = "unit"                                            # rooms[].unit: the architect's unit mark (Gordium: Unit)
# said with every row reading a count from the marks (parts.yaml `architect_stated`): the statement it stands on
MARKED = ("counted from the rooms' unit marks (Gordium: Unit), the architect's statement: each name given is one "
          "dwelling unit, and every room of a dwelling unit on the story carries its unit's name (a unit's room left "
          "unmarked and marked a corridor, lobby or exit can't be told from a room shared between units)")
# two or more units named in one mark ("1A, 1B", "1A and 1B", "1A/1B"): a room can't be in two units
_SEVERAL = re.compile(r"[,;&+/|]|\band\b", re.IGNORECASE)


def marked(story, items: dict) -> bool:
    """Whether any room of the story carries a unit mark (any value but none or blank text): then the marks count."""
    return any(_given((items.get(rid) or {}).get(UNIT)) for rid in story.rooms)


def _given(value) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _name(value, room_name):
    """The unit a mark names (spacing made single), None for no mark; Stop where it isn't one name."""
    if not _given(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise Stop("units_mark_unreadable", name=room_name, got=repr(value))
    text = " ".join(str(value).split())
    if _SEVERAL.search(text):
        raise Stop("units_mark_several", name=room_name, got=text)
    return text


def _marked(story, items: dict, is_exit) -> int:
    """The count from the unit marks (see the module's words)."""
    exits = {rid for rid in story.rooms if is_exit(story, rid)}
    names, by_unit = {}, {}
    for rid, room in sorted(story.rooms.items()):
        name = _name((items.get(rid) or {}).get(UNIT), room.name)
        if name is None:
            continue
        if rid in exits:                                 # a stair enclosure or exit passageway is shared, never a unit's
            raise Stop("units_mark_on_exit", name=room.name, unit=name)
        names[rid] = name
        by_unit.setdefault(name, set()).add(rid)
    alike = {}
    for name in by_unit:
        alike.setdefault("".join(name.casefold().split()), []).append(name)   # "Apt1", "apt 1": one or two?
    for same in alike.values():
        if len(same) > 1:
            raise Stop("units_mark_alike", names=", ".join(sorted(same)))
    links = [tuple(d.sides) for d in story.doors.values()] + [(a, b) for a, b, _ in story.passages]
    for name, rooms in sorted(by_unit.items()):
        reached, todo = set(), [min(rooms)]              # its rooms joined through its own rooms only
        while todo:
            r = todo.pop()
            if r not in reached:
                reached.add(r)
                todo += [y if x == r else x for x, y in links if r in (x, y) and {x, y} <= rooms]
        if reached != rooms:
            raise Stop("units_mark_apart", unit=name,
                       rooms=", ".join(sorted(story.rooms[r].name for r in rooms - reached)))
        lived = [r for r in rooms if story.rooms[r].use not in NOT_LIVED_IN]
        if lived and all(isinstance(f, str) and f in NOT_DWELLING
                         for f in ((items.get(r) or {}).get("function") for r in lived)):
            raise Stop("units_mark_not_dwelling", unit=name)
    found, halls = spaces(story, lambda _s, rid: rid in exits)
    hall_rooms = set().union(*[h for h, _ in halls]) if halls else set()
    for rid, room in sorted(story.rooms.items()):        # a room with no mark that may be a dwelling unit's
        function = (items.get(rid) or {}).get("function")
        if rid in names or rid in exits or rid in hall_rooms or room.use in NOT_LIVED_IN or \
                (isinstance(function, str) and function in NOT_DWELLING):
            continue
        raise Stop("units_mark_left_out", name=room.name)
    for rid in sorted(exits | hall_rooms):               # a unit's room marked a hall or exit, with no unit mark
        if rid in names:
            continue
        room, function = story.rooms[rid], (items.get(rid) or {}).get("function")
        if rid in exits and function is not None:
            raise Stop("units_exit_function", name=room.name)
        # a hall stating a function a unit may have (a lobby states one: its occupant load needs it) is shared only
        # where it opens into rooms of two or more named units; opening into one or none, it may be a unit's room left
        # unmarked (a studio marked a lobby beside one unit)
        if rid in hall_rooms and function is not None and \
                not (isinstance(function, str) and function in NOT_DWELLING) and \
                len({names[x] for sides in links if rid in sides for x in sides if x in names}) < 2:
            raise Stop("units_mark_hall_function", name=room.name)
    return len(by_unit)


def units_on(story, items: dict, is_exit, stair_in, links_read) -> int:
    """The dwelling units on the story (see the module's words). `items`: the description's rooms by id (their
    `function`); `is_exit(story, room id)`: whether the room is itself an exit (routes._is_exit, Stop where unclear);
    `stair_in(group)`: whether a stair, ramp or ladder may stand in the group (one not read may be anywhere);
    `links_read()`: raises Stop unless every door and opening the description gives for the story's rooms was read on
    it (routes.links_read_here: one drawn on another level would hide a unit's own door, two units counted one)."""
    if story.stops:
        raise Stop("story_not_measured", reasons="; ".join(story.stops))
    if marked(story, items):                             # the architect's unit marks replace the grouping (doors
        return _marked(story, items, is_exit)            # change no count by marks: one hidden only stops it)
    links_read()
    for rid, room in sorted(story.rooms.items()):
        if room.use is None:                             # it may be a corridor joining two units into one group
            raise Stop("units_use_unknown", name=room.name)
    found, halls = spaces(story, is_exit)
    grouped = set().union(*found) if found else set()
    shared = (set(story.rooms) - grouped) | {OUTSIDE}    # the corridors, lobbies and exits, and the outside
    hall_rooms = set().union(*[h for h, _ in halls]) if halls else set()
    unit_rooms = {r for g in found for r in g          # the rooms of groups holding a lived-in residential room
                  if any(story.rooms[x].use not in NOT_LIVED_IN and (items.get(x) or {}).get("function") == RESIDENTIAL
                         for x in g)}
    unsaid = {r for g in found for r in g              # groups with a lived-in room stating no function: they stop
              if any(story.rooms[x].use not in NOT_LIVED_IN and          # below with their own reason
                     not isinstance((items.get(x) or {}).get("function"), str) for x in g)}
    links = [set(d.sides) for d in story.doors.values()] + [{a, b} for a, b, _ in story.passages]
    for rid in sorted(set(story.rooms) - grouped):       # a shared room that may be a unit marked wrong would drop it
        room, function = story.rooms[rid], (items.get(rid) or {}).get("function")
        if rid not in hall_rooms and function is not None:   # an exit stating a function (a unit's door marked an exit)
            raise Stop("units_exit_function", name=room.name)
        if rid in hall_rooms and function is not None and \
                not (isinstance(function, str) and function in NOT_DWELLING) and \
                not any(rid in sides and sides & (unit_rooms | unsaid) for sides in links):   # opening into no unit
            raise Stop("units_hall_residential", name=room.name)
    count = 0
    for g in found:
        names = ", ".join(sorted(story.rooms[r].name for r in g))
        lived = [r for r in g if story.rooms[r].use not in NOT_LIVED_IN]
        functions = [(items.get(r) or {}).get("function") for r in lived]
        if not lived or (RESIDENTIAL not in functions and all(isinstance(f, str) and f in NOT_DWELLING
                                                              for f in functions)):
            continue                                     # no dwelling unit: nothing lived in, or a listed other use
        if RESIDENTIAL not in functions or not all(isinstance(f, str) and f for f in functions):
            raise Stop("units_function_unknown", name=names)   # (a room with none may be a shared vestibule)
        # its ways out to the shared spaces: doors and openings with no door alike
        links = [(d.name, set(d.sides)) for d in story.doors.values()] + \
            [(f"the opening between {story.rooms[a].name} and {story.rooms[b].name}", {a, b})
             for a, b, _ in story.passages if a in story.rooms and b in story.rooms]
        entrances = sorted((name for name, sides in links if sides & g and sides - g and sides - g <= shared))
        if not entrances:
            raise Stop("units_no_entrance", name=names)
        if len(entrances) > 1:
            raise Stop("units_entrances", name=names, count=len(entrances), doors=", ".join(entrances))
        if stair_in(g):                                  # a way to another story: the upper part of a unit whose door
            raise Stop("units_stair", name=names)        # is downstairs may share this group's one way out
        for r in g:                                      # a closet, toilet or storeroom, or a room of another
            if story.rooms[r].use in NOT_LIVED_IN or \
                    (items.get(r) or {}).get("function") != RESIDENTIAL:     # function (a shared vestibule, laundry,
                #                                                              mail room), between two parts of it may
                #                                                              be shared by two units
                others = {x for _, sides in links if r in sides for x in sides} - {r}
                if len(others & g) >= 2:
                    raise Stop("units_shared_room", name=names, room=story.rooms[r].name)
        count += 1
    return count
