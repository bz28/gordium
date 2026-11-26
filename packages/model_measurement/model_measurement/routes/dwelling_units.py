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
- A group with a stair, ramp or ladder within it (or one not read, or not said to be none: it may be anywhere), or
  with a closet, toilet or storeroom, or a room not itself residential, opening onto two or more of its rooms, may
  hold the upper part of a unit whose door is downstairs, or two units sharing that room: not measured.
- A dwelling unit reaches the exits without passing through another (1016.2.1), so a group with one way out to a
  shared space is one unit: Gordium's reading, to confirm, said with every row reading the count (`rests_on`, RESTS_ON),
  which also says the count holds only if 1016.2.1 is met (a flag, a person's check, in every Group R-2 answer). It
  never holds a pass: a second unit drawn with no door of its own would break 1016.2.1 itself. A group with
  two or more such doors may be two units joined by a door (a lock-off): not measured. One with none reaches the
  exits only through another story (a unit on two stories) or not at all: not measured.
- Not measured either where the story's routes aren't read (a room or door not read, an enclosed space with no room
  drawn in it: it may be a unit), or a room has no `use` (it may be a corridor).
- A unit marked shared space would drop out of the count: a room taken as an exit that states a function (an exit has
  none), or a corridor or lobby stating residential that opens into no room of a dwelling unit (only into halls,
  exits, the outside, or a toilet or closet of its own), leaves it not measured. One so marked stating no function
  can't be told from a real corridor or exit: the words beside the count name it.
Never a guess: a count too low could pass a one-exit story Table 1006.3.4(1) allows only up to 4 units.
"""

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


def units_on(story, items: dict, is_exit, stair_in, links_read) -> int:
    """The dwelling units on the story (see the module's words). `items`: the description's rooms by id (their
    `function`); `is_exit(story, room id)`: whether the room is itself an exit (routes._is_exit, Stop where unclear);
    `stair_in(group)`: whether a stair, ramp or ladder may stand in the group (one not read may be anywhere);
    `links_read()`: raises Stop unless every door and opening the description gives for the story's rooms was read on
    it (routes.links_read_here: one drawn on another level would hide a unit's own door, two units counted one)."""
    if story.stops:
        raise Stop("story_not_measured", reasons="; ".join(story.stops))
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
    links = [set(d.sides) for d in story.doors.values()] + [{a, b} for a, b, _ in story.passages]
    for rid in sorted(set(story.rooms) - grouped):       # a shared room that may be a unit marked wrong would drop it
        room, function = story.rooms[rid], (items.get(rid) or {}).get("function")
        if rid not in hall_rooms and function is not None:   # an exit stating a function (a unit's door marked an exit)
            raise Stop("units_exit_function", name=room.name)
        if rid in hall_rooms and function == RESIDENTIAL and \
                not any(rid in sides and sides & unit_rooms for sides in links):   # a "hall" opening into no unit
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
