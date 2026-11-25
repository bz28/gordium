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
    "description": "the model can't be read for escape routes: {reason}",
    "no_levels": "the model gives no levels: which story each room and door is on isn't known",
    "level_entry": "level #{n} can't be read (a level has an id, a name and an elevation): {reason}",
    "level_twice": "{count} levels have the id {id!r}",
    "no_level": "the {what} {name} doesn't say which story (level) it is on",
    "level_unknown": "the {what} {name} is on level {level!r}, not one of the model's levels",
    "key_left_out": "the model doesn't give its {key}: {words}",
    "id_twice": "{count} {what}s have the id {id!r}",
    # a story (its route measures need review)
    "room_not_read": "the room {name} isn't read: {reason}",
    "room_no_floor": "the room {name} has no floor outline (a curved wall is never read as its chord, which would "
                     "shorten routes): {reason}",
    "pass_through_refused": "the room {name} is marked as a room an exit route may pass through, but {why}: a route never crosses it, "
                            "so the mark is refused and the room isn't read",
    "not_occupied_refused": "the room {name} is marked not occupied, but it is {why}, whose use is "
                            "occupancy: the mark is refused and the room isn't read",
    "none_occupied": "every room on the story is marked not occupied by the architect: no point subject to "
                     "occupancy to measure from (NFPA 101 7.6.1(1))",
    "rooms_overlap": "the rooms {a} and {b} overlap ({area} sq in): which floor is which is unclear",
    "unknown_space": "the enclosed space {name} has no room drawn in it: it may hold the most remote point or a "
                     "route (open question 4)",
    "unknown_space_not_read": "the enclosed space #{n} isn't read: {reason}",
    "door_not_read": "the door {name} isn't read: {reason}",
    "door_sides": "the door gives {got}, not 2 sides (two rooms, or a room and outside)",
    "door_side_items": "the door's sides are {items}: each must be a room id or 'outside'",
    "door_narrow": "the door {name} is {width} in clear, under 24 in: its centre is inside its jambs' 12-in rings",
    "door_side": "a side of the door {name} is {side!r}, which is {what}",
    "door_not_in_wall": "the door {name}'s opening doesn't sit in a wall of the room {room} (its face, at half the "
                        "wall's thickness from its centre, isn't on that room's outline within 1/16 in)",
    "door_same_side": "the door {name} has both its rooms on the same side of its wall",
    "door_within_zone": "the door {name} joins two parts of one floor already joined by a passage: a route could "
                        "pass beside its centre",
    "exit_stair_or_ramp": "the door {name} is an exit to an exterior stair or ramp: travel along it isn't measured "
                          "yet (decision 4)",
    "passage_not_read": "passage #{n} isn't read: {reason}",
    "passage_rooms": "the passage gives {got}, not 2 rooms",
    "passage_room_items": "the passage's rooms are {items}: each must be a room id",
    "passage_to_itself": "the passage joins the room {room} to itself",
    "passage_off": "passage #{n}'s line isn't on the outline of the room {room} (within 1/16 in)",
    "zone_in_pieces": "the rooms {rooms}, joined by passages, don't make one floor (they come apart in {count} "
                      "pieces): check the passages' lines against the rooms' outlines",
    "no_exit": "no door on the story is marked as an exit: exits are marked, never guessed",
    "outline_not_read": "the story's outline isn't read: {reason}",
    # paths (one route, or the story's routes)
    "story_not_measured": "the story's routes aren't measured: {reasons}",
    "not_on_floor": "a point measured from isn't on the story's floor (in no room, or in a hole or an obstruction)",
    "no_route": "part of the floor has no route to {exits} (a path 12 in clear of every corner, through door "
                "centres and rooms it may cross)",
    "no_route_host_blocked": "the room {name} has no route to {exits}: it {why}",
    "no_route_via_host": "the room {name} has no route to {exits}: it opens only into {host}, which "
                         "it serves (Gordium's reading, decision 1a), and no route leaves {host} either",
    "route_reenters": "the shortest route found from a point goes back into a 12-in ring it had left (or into "
                      "the room it started in): the route the definition allows is longer, and isn't measured yet",
    "too_many_ties": "more than {most} routes from one point are equally short (within 1e-6 ft): too many to list "
                     "(only a listing asks: every measure reads the tied routes all together, decision 5)",
    "exit_unknown": "no exit on the story has the exit id {exit_id!r}",
    "inside_ring": "a point measured from is within 12 in of a corner: no route is defined from there (decision 2); "
                   "the story's figure covers it by its ring cluster's bound (decision 3)",
    "too_narrow": "part of the floor is shut in: an opening too narrow for NFPA 7.6.1's 12-in clearance from both "
                  "sides",
    "doors_same_centre": "the doors {a} and {b} have the same centre (within 1/16 in): a door listed twice?",
    "door_centre_in_ring": "the door {name}'s centre is within 12 in of a corner other than its jambs: no route through "
                           "it is defined (decision 2)",
    # the most remote point (remote.py)
    "cluster_shut": "the 12-in rings round some corners have no clear edge with a route: the floor there is shut in (an "
                    "opening too narrow for NFPA 7.6.1's 12-in clearance from both sides)",
    "nothing_to_sample": "the story has no clear floor to sample (every room's floor is under obstructions or "
                         "within 12 in of a corner): its travel figure isn't measured",
    "walk_shut": "a point within 12 in of a corner has no walk on the floor out to its rings' clear "
                 "edge",
    # dead ends and corridor widths (dead_ends.py)
    "corridor_not_legs": "the corridor's centre lines can't be worked out ({why}): its dead ends and width aren't "
                         "measured (decision 6)",
    "corridor_width_stepped": "the corridor's walls step, widen or jog: which of its stretches give its width, rather "
                              "than its alcoves', isn't worked out (decision 6, amended 2026-11-22)",
    "corridor_end_only": "the corridor {name} can't be crossed ({why}, decision 1a): routes along it never count, so "
                         "its dead ends aren't worked out",
    "door_off_legs": "the door {name} isn't on any of the corridor's legs: where it meets the centre line isn't known",
    "dead_end_unbounded": "from one of its closed ends no point of the corridors has routes along them to two "
                          "distinct exits: where its dead end ends isn't defined",
    # remoteness and the diagonal (straight.py)
    "too_few_exits": "the story has {count} distinct exit(s) (counted by the exit each exit door leads into): "
                     "remoteness needs two",
    "outline_needed": "the story's outline isn't read, so its diagonal and areas aren't measured: {reason}",
    # the parts handed to the rules (__init__.py)
    "stated_not_given": "stated by the architect ({what}), and Gordium has no mark for it in the model yet",
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
    "exit_side_unclear": "the room {name} is beside the exit door {door}, whose exit ({exit_id!r}) is neither room it "
                         "joins: whether the room is the exit (a stair enclosure) or a space it serves isn't known",
    # areas (areas.py)
    "area_room_not_read": "the room {name} isn't read, so what it adds to the story's areas isn't known",
    "area_no_use": "the room {name} has no use given: which of the story's areas it counts in isn't known",
    "area_unknown_space": "the story has an enclosed space with no room drawn in it ({name}): which area it counts in "
                          "isn't known",
    "area_rooms_overlap": "the rooms {a} and {b} overlap: an area counted twice",
    # each door's own part (doors.py, section group 6a): its sizes only from the maker's stated clear opening
    "door_no_stated_clear": "the door {name} has no maker's stated clear opening (its type's clear width and height, "
                            "confirmed): its size is never taken from the door's own size or its leaf",
    "door_clear_not_read": "the door {name}'s clear opening isn't read: {reason}",
    "door_clear_disagree": "the door {name}'s {where} gives a clear {size} of {other} in and its maker's stated "
                           "clear opening {stated} in: which is the door's isn't clear",
    "door_leaves_not_given": "the door {name} doesn't say how many leaves it has (one, or a pair with no mullion), and "
                             "Gordium has no mark for it in the model yet",
    "door_leaves_not_read": "the door {name} gives its leaves as {got}, not 1 or 2",
    "door_exit_kind_not_read": "the door {name} gives its kind of exit as {got}, not one Gordium reads",
    "door_sides_not_read": "the door {name}'s sides (the two rooms, or a room and outside, it joins) aren't read",
    "door_side_no_use": "a side of the door {name} is the room {room}, which has no use given: whether it is a "
                        "corridor isn't known",
    "egress_side_unclear": "which way egress travel goes through the door {name} isn't worked out: travel may cross it "
                           "both ways (two rooms that both lead out through it, a room others' routes cross, an exit "
                           "stair that may discharge through it, an outdoor area whose way out is back inside)",
    "door_swing_not_given": "the door {name} doesn't say which side it swings into, and Gordium has no mark for it in "
                            "the model yet",
    "door_swing_not_read": "the door {name} says it swings into {got}, not one of the two sides it joins",
    "door_not_on_routes": "the door {name} isn't one the routes read (its story's routes need review, or it isn't "
                          "placed): which way egress travel goes through it isn't known",
    "door_operation_not_given": "the door {name} doesn't say how it operates (side-hinged, sliding, folding, pocket)",
    "door_operation_other": "the door {name}'s operation is given as other: whether it is a pivoted or balanced door "
                            "(swinging) or another kind isn't known",
    "door_side_room_not_read": "a side of the door {name} is the room {room}, which isn't read: its floor area isn't "
                               "known",
}


class Stop(Exception):
    """A route measurement that gets no value, with its reason from the table (every blank shown as the interior's
    reasons show it: interior.stops.said)."""

    def __init__(self, which: str, /, **blanks):
        from model_measurement.interior.stops import said
        self.key = which
        self.reason = STOPS[which].format(**{k: said(v) for k, v in blanks.items()})
        super().__init__(self.reason)
