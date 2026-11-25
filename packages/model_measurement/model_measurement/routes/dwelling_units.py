"""The dwelling units on a story, worked out from the model: `story_dwelling_units`, which Table 1006.3.4(1) of the
2025 Building Code of New York State reads ("MAXIMUM NUMBER OF DWELLING UNITS": 4 on a story with one exit, Group
R-2; p.317).

    units_on(story, items) -> int, or raises Stop (not measured, with its reason)

The law: DWELLING UNIT (202, p.41): "A single unit providing complete, independent living facilities for one or more
persons, including permanent provisions for living, sleeping, eating, cooking and sanitation." 1016.2.1 (p.341):
"each tenant space, dwelling unit and sleeping unit shall be provided with access to the required exits without
passing through adjacent tenant spaces, dwelling units and sleeping units."

How (docs/decisions/2026-11-25_story_facts_from_the_model.md, step 3):
- The shared spaces are the corridors and lobbies (a room's `use`) and the rooms that are exits (a stair enclosure,
  an exit passageway), and the outside. Every other room belongs to a group: rooms joined by doors or passages
  without crossing a shared space.
- A group is a dwelling unit where one of its rooms states the function residential (Table 1004.5, the room mark
  Gordium: Function). A group whose rooms that could be lived in (not a toilet, closet or storeroom) all state
  another function is no dwelling unit; one where such a room states none may be one: not measured.
- A dwelling unit reaches the exits without passing through another (1016.2.1), so a group with one door to a shared
  space is one unit: Gordium's reading, to confirm, said with every row reading the count (`rests_on`, RESTS_ON),
  which also says the count holds only if 1016.2.1 is met (a flag, a person's check, in every Group R-2 answer). It
  never holds a pass: a second unit drawn with no door of its own would break 1016.2.1 itself. A group with
  two or more such doors may be two units joined by a door (a lock-off): not measured. One with none reaches the
  exits only through another story (a unit on two stories) or not at all: not measured.
- Not measured either where the story's routes aren't read (a room or door not read, an enclosed space with no room
  drawn in it: it may be a unit), or a room has no `use` (it may be a corridor).
Never a guess: a count too low could pass a one-exit story Table 1006.3.4(1) allows only up to 4 units.
"""

from model_measurement.routes.floor import OUTSIDE
from model_measurement.routes.spaces import spaces
from model_measurement.routes.stops import Stop

NOT_LIVED_IN = ("toilet", "closet", "accessory_storage")
RESIDENTIAL = "residential"
QUOTE_1016_2_1 = ("each tenant space, dwelling unit and sleeping unit shall be provided with access to the required "
                  "exits without passing through adjacent tenant spaces, dwelling units and sleeping units")
# said with every row reading the count (parts.yaml `rests_on`): the reading it stands on, and the rule that must hold
# for it (shown always, a person's check: general.bc_1016_2_1_multiple_tenants), never holding a pass
RESTS_ON = ("Gordium's reading, to confirm: each group of rooms with one door to the corridors, exits or outside is "
            "one dwelling unit. This count holds only if BCNYS 1016.2.1 (p.341) is met: \"" + QUOTE_1016_2_1 + "\"")


def units_on(story, items: dict, is_exit) -> int:
    """The dwelling units on the story (see the module's words). `items`: the description's rooms by id (their
    `function`); `is_exit(story, room id)`: whether the room is itself an exit (routes._is_exit, Stop where unclear)."""
    if story.stops:
        raise Stop("story_not_measured", reasons="; ".join(story.stops))
    for rid, room in sorted(story.rooms.items()):
        if room.use is None:                             # it may be a corridor joining two units into one group
            raise Stop("units_use_unknown", name=room.name)
    found, halls = spaces(story, is_exit)
    grouped = set().union(*found) if found else set()
    shared = (set(story.rooms) - grouped) | {OUTSIDE}    # the corridors, lobbies and exits, and the outside
    count = 0
    for g in found:
        names = ", ".join(sorted(story.rooms[r].name for r in g))
        lived = [r for r in g if story.rooms[r].use not in NOT_LIVED_IN]
        functions = [(items.get(r) or {}).get("function") for r in lived]
        if not lived or (all(functions) and RESIDENTIAL not in functions):
            continue                                     # no dwelling unit: nothing lived in, or another function
        if RESIDENTIAL not in functions:
            raise Stop("units_function_unknown", name=names)
        entrances = sorted((d for d in story.doors.values()
                            if set(d.sides) & g and set(d.sides) - g and set(d.sides) - g <= shared),
                           key=lambda d: d.id)
        if not entrances:
            raise Stop("units_no_entrance", name=names)
        if len(entrances) > 1:
            raise Stop("units_entrances", name=names, count=len(entrances),
                       doors=", ".join(d.name for d in entrances))
        count += 1
    return count
