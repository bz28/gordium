"""Every reason a route measurement can stop with (it gets no value, and a rule reading it says NEEDS REVIEW), in
one place.

The route code (floor.py, paths.py) gives a reason only through `Stop(key, ...)`, so this table is the whole list:
tests/test_routes_floor.py and tests/test_routes_paths.py make each one happen. Values read through the interior
reader (`interior/read.py`) stop with that table's reasons (`missing`, `not_a_length`, `not_an_outline` ...), which
come through here as the `{reason}` of the part they belong to. The design: docs/decisions/2026-11-20_route_measurement.md.
"""

STOPS = {
    # the description as a whole (every story's route measures need review)
    "description": "the interior description can't be read for routes: {reason}",
    "no_levels": "the description gives no `levels`: which story each room and door is on isn't known",
    "level_entry": "`levels` #{n} isn't a level (a mapping with a text `id`, a `name` and an `elevation`): {reason}",
    "level_twice": "{count} levels have the id {id!r}",
    "no_level": "the {what} {name} doesn't say which story it is on (`level`)",
    "level_unknown": "the {what} {name} is on level {level!r}, not one of the `levels` given",
    "key_left_out": "`{key}` isn't in the description: {words}",
    "id_twice": "{count} {what}s have the id {id!r}",
    # a story (its route measures need review)
    "room_not_read": "the room {name} isn't read: {reason}",
    "room_no_floor": "the room {name} has no floor outline (a curved wall is never read as its chord, which would "
                     "shorten routes): {reason}",
    "pass_through_refused": "the room {name} is marked `pass_through: true`, but {why}: a route never crosses it, "
                            "so the mark is refused and the room isn't read",
    "rooms_overlap": "the rooms {a} and {b} overlap ({area} sq in): which floor is which is unclear",
    "unknown_space": "the enclosed space {name} has no room drawn in it: it may hold the most remote point or a "
                     "route (open question 4)",
    "unknown_space_not_read": "the enclosed space #{n} isn't read: {reason}",
    "door_not_read": "the door {name} isn't read: {reason}",
    "door_narrow": "the door {name} is {width} in clear, under 24 in: its centre is inside its jambs' 12-in rings",
    "door_side": "the door {name} opens on {side!r}, which is {what}",
    "door_not_in_wall": "the door {name}'s opening doesn't sit in a wall of the room {room} (its face, at half the "
                        "wall's thickness from its centre, isn't on that room's outline within 1/16 in)",
    "door_same_side": "the door {name} has both its rooms on the same side of its wall",
    "door_within_zone": "the door {name} joins two parts of one floor already joined by a passage: a route could "
                        "pass beside its centre",
    "exit_stair_or_ramp": "the door {name} is an exit to an exterior stair or ramp: travel along it isn't measured "
                          "yet (decision 4)",
    "passage_not_read": "passage #{n} isn't read: {reason}",
    "passage_off": "passage #{n}'s line isn't on the outline of the room {room} (within 1/16 in)",
    "zone_in_pieces": "the rooms {rooms}, joined by passages, don't make one floor (they come apart in {count} "
                      "pieces): check the passages' lines against the rooms' outlines",
    "no_exit": "no door on the story is marked as an exit (`exit_kind`): exits are marked, never guessed",
    "outline_not_read": "the story's outline isn't read: {reason}",
    # paths (one route, or the story's routes)
    "story_not_measured": "the story's routes aren't measured: {reasons}",
    "not_on_floor": "the point ({x}, {y}) isn't on the story's floor (in no room, or in a hole or an obstruction)",
    "no_route": "the point ({x}, {y}) has no route to {exits} (a path 12 in clear of every corner, through door "
                "centres and rooms it may cross)",
    "route_reenters": "the shortest route found from ({x}, {y}) goes back into a 12-in ring it had left (or into "
                      "the room it started in): the route the definition allows is longer, and isn't measured yet",
    "too_many_ties": "more than {most} routes from ({x}, {y}) are equally short (within 1e-6 ft): which to take "
                     "isn't worked out",
    "exit_unknown": "no exit on the story has the exit id {exit_id!r}",
    "inside_ring": "the point ({x}, {y}) is within 12 in of a corner: no route is defined from there (decision 2); "
                   "the story's figure covers it by its ring cluster's bound (decision 3)",
    "too_narrow": "the point ({x}, {y}) is shut in: an opening too narrow for NFPA 7.6.1's 12-in clearance from both "
                  "sides",
    "door_centre_in_ring": "the door {name}'s centre is within 12 in of a corner other than its jambs: no route through "
                           "it is defined (decision 2)",
    # the most remote point (remote.py)
    "cluster_shut": "the rings round ({x}, {y}) have no clear edge with a route: the floor there is shut in (an "
                    "opening too narrow for NFPA 7.6.1's 12-in clearance from both sides)",
    "walk_shut": "the point ({x}, {y}), within 12 in of a corner, has no walk on the floor out to its rings' clear "
                 "edge",
}


class Stop(Exception):
    """A route measurement that gets no value, with its reason from the table."""

    def __init__(self, which: str, /, **blanks):
        self.key = which
        self.reason = STOPS[which].format(**blanks)
        super().__init__(self.reason)
