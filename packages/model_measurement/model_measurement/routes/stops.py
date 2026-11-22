"""Every reason a route measurement can stop with (it gets no value, and a rule reading it says NEEDS REVIEW), in
one place.

The route code (floor.py, paths.py, remote.py, common_path.py, dead_ends.py, straight.py, areas.py) gives a reason
only through `Stop(key, ...)`, so this table is the whole list: the route tests (tests/test_routes_*.py) make each
one happen. Values read through the interior reader (`interior/read.py`) stop with that table's reasons (`missing`,
`not_a_length`, `not_an_outline` ...), which come through here as the `{reason}` of the part they belong to. The
design: docs/decisions/2026-11-20_route_measurement.md.
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
    "not_occupied_refused": "the room {name} is marked `not_occupied: true`, but it is {why}, whose use is "
                            "occupancy: the mark is refused and the room isn't read",
    "none_occupied": "every room on the story is marked `not_occupied` by the architect: no point subject to "
                     "occupancy to measure from (NFPA 101 7.6.1(1))",
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
    "no_route_host_blocked": "the point ({x}, {y}) has no route to {exits}: its room {name} {why}",
    "no_route_via_host": "the point ({x}, {y}) has no route to {exits}: its room {name} opens only into {host}, which "
                         "it serves (Gordium's reading, decision 1a), and no route leaves {host} either",
    "route_reenters": "the shortest route found from ({x}, {y}) goes back into a 12-in ring it had left (or into "
                      "the room it started in): the route the definition allows is longer, and isn't measured yet",
    "too_many_ties": "more than {most} routes from ({x}, {y}) are equally short (within 1e-6 ft): too many to list "
                     "(only a listing asks: every measure reads the tied routes all together, decision 5)",
    "exit_unknown": "no exit on the story has the exit id {exit_id!r}",
    "inside_ring": "the point ({x}, {y}) is within 12 in of a corner: no route is defined from there (decision 2); "
                   "the story's figure covers it by its ring cluster's bound (decision 3)",
    "too_narrow": "the point ({x}, {y}) is shut in: an opening too narrow for NFPA 7.6.1's 12-in clearance from both "
                  "sides",
    "doors_same_centre": "the doors {a} and {b} have the same centre (within 1/16 in): a door listed twice?",
    "door_centre_in_ring": "the door {name}'s centre is within 12 in of a corner other than its jambs: no route through "
                           "it is defined (decision 2)",
    # the most remote point (remote.py)
    "cluster_shut": "the rings round ({x}, {y}) have no clear edge with a route: the floor there is shut in (an "
                    "opening too narrow for NFPA 7.6.1's 12-in clearance from both sides)",
    "nothing_to_sample": "the story has no clear floor to sample (every room's floor is under obstructions or "
                         "within 12 in of a corner): its travel figure isn't measured",
    "walk_shut": "the point ({x}, {y}), within 12 in of a corner, has no walk on the floor out to its rings' clear "
                 "edge",
    # dead ends and corridor widths (dead_ends.py)
    "corridor_not_legs": "the corridor's centre lines can't be worked out ({why}): its dead ends and width aren't "
                         "measured (decision 6)",
    "corridor_width_stepped": "the corridor's walls step, widen or jog: which of its stretches give its width, rather "
                              "than its alcoves', isn't worked out (decision 6, amended 2026-11-22)",
    "corridor_end_only": "the corridor {name} can't be crossed ({why}, decision 1a): routes along it never count, so "
                         "its dead ends aren't worked out",
    "door_off_legs": "the door {name} isn't on any of the corridor's legs: where it meets the centre line isn't known",
    "dead_end_unbounded": "from the closed end at ({x}, {y}) no point of the corridors has routes along them to two "
                          "distinct exits: where its dead end ends isn't defined",
    # remoteness and the diagonal (straight.py)
    "too_few_exits": "the story has {count} distinct exit(s) (by `exit_id`): remoteness needs two",
    "outline_needed": "the story's outline isn't read, so its diagonal and areas aren't measured: {reason}",
    # the parts handed to the rules (__init__.py)
    "stated_not_given": "stated by the architect ({what}), and the description has no mark for it yet",
    "not_measured_yet": "Gordium doesn't measure this yet",
    "readings": "given as two readings for open question {question} of the route note ({words}): a rule reading it "
                "complies only if it complies under both, fails only if it fails under both, else needs review",
    "room_not_measured": "the room {name} isn't read: {reason}",
    "maybe_kind": "the enclosed space {name} has no room drawn in it: it may be a {kind}",
    "exit_access_unclear": "the room {name} is joined by passages to other rooms a route may cross: which of its doors "
                           "lead out without coming back into it isn't worked out",
    "passage_in_ring": "the passage from the room {name} has its middle within 12 in of a corner: whether a route "
                       "leaves by it isn't worked out",
    "no_room_doors": "the story has no room besides its corridors: no room door to measure from",
    "no_exit_access": "the room {name} has no door from which a route reaches an exit without coming back into it",
    # areas (areas.py)
    "area_room_not_read": "the room {name} isn't read, so what it adds to the story's areas isn't known",
    "area_no_use": "the room {name} has no `use`: which of the story's areas it counts in isn't known",
    "area_unknown_space": "the story has an enclosed space with no room drawn in it ({name}): which area it counts in "
                          "isn't known",
    "area_rooms_overlap": "the rooms {a} and {b} overlap: an area counted twice",
}


class Stop(Exception):
    """A route measurement that gets no value, with its reason from the table."""

    def __init__(self, which: str, /, **blanks):
        self.key = which
        self.reason = STOPS[which].format(**blanks)
        super().__init__(self.reason)
