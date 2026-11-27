"""Every reason an interior measurement can stop with (it gets no value, and a rule reading it says NEEDS REVIEW),
in one place.

The interior measuring code gives a reason only through `Stop(key, ...)`, so this table is the whole list:
docs/interior/interior_measurements.md lists each one and tests/test_interior_measures.py makes each happen.
"""

STOPS = {
    # the description as a whole
    "not_a_description": "the interior sent from the model can't be read (it isn't a set of named entries)",
    "wrong_format": "the interior sent from the model is in a form Gordium doesn't read ({got}, not "
                    "gordium.interior/1)",
    "units": "the interior sent from the model gives its sizes in {units}, not in inches, feet, millimetres or "
             "metres",
    "not_read": "the {what} weren't read: the model doesn't say these are all the {what} (or that there are none)",
    "not_a_list": "the {key} sent from the model can't be read (they aren't a list)",
    "not_a_mapping": "{what} #{n} isn't a mapping",
    "flag_missing": "{what} doesn't say whether {question} (yes or no)",
    "flag_not_yes_no": "{what} gives whether {question} as {got}, not as a yes/no value",
    # an enclosed space the host found with no room drawn in it (`unknown_spaces`): its use isn't known
    "unknown_spaces_entry": "enclosed space #{n} with no room drawn in it can't be read (it has no id): the rooms "
                            "aren't read",
    "unknown_space": "an enclosed space with no room drawn in it: its use isn't known, so it may be a sleeping room "
                     "(draw a room in it and say whether it is a sleeping room)",
    # what the description says the house has none of (has_none.py): a claim not taken leaves its kind not read
    "has_none_not_a_list": "what the model says the house has none of can't be read (it isn't a list, each entry a "
                           "kind and its source): it isn't read",
    "has_none_entry": "entry #{n} of what the house has none of isn't a kind with its source: it isn't read",
    "has_none_listed": "the model says the house has no {kind}, but {key} have a list of their own in the model: say "
                       "there are none with an empty list of {key}, not as something the house has none of",
    "has_none_sleeping_room": "the model says the house has no sleeping rooms: a room that isn't a sleeping room says "
                              "so itself (sleeping room: no), not as something the house has none of",
    "has_none_kind": "the model says the house has none of {kind!r}, not a kind it can say that of (one of: {kinds}): "
                     "it isn't read",
    "has_none_no_source": "the model says the house has no {words} but not where that comes from (its source, "
                          "such as the sheet): it isn't taken, so their rules need review",
    "has_none_reading": "the model says the house has no {words}, but gives whether that rests on a reading of the law "
                        "as {got}, not as a yes/no value: it "
                        "isn't taken, so their rules need review",
    "has_none_twice": "the model says {count} times that the house has no {words}: it isn't taken, so their "
                      "rules need review",
    "has_none_keys": "the model says the house has no {words}, giving more than a kind, a source and, "
                     "optionally, a reading (also {keys}): it isn't taken, so their rules need review",
    "has_none_below_ground": "the model says the house has no basements, yet {what}: which is right is "
                             "unclear, so their rules need review",
    "has_none_room_within": "the model says the house has no sleeping lofts, yet {what}: which is right is "
                            "unclear, so their rules need review",
    "has_none_unknown_space": "the model says the house has no {words}, yet it gives {count} enclosed "
                              "space(s) whose use isn't known (no room drawn in them), any of which could be one: it isn't "
                              "taken, so their rules need review",
    "has_none_contradicted":"the model says the house has no {words}, yet it also gives {key}, and not an empty "
                             "list: which is right is unclear, so their rules need review",
    # "no stairs" (an empty list of stairs) against rooms on more than one floor (_stairs_against_floors)
    "stairs_none_several_floors": "the model says there are no stairs, yet its rooms are on more than one floor "
                                  "({what}): a stair or a ramp joins them, or each floor has its own way out at "
                                  "grade, which the model doesn't show, so 'no stairs' isn't taken and the stair "
                                  "rules need review",
    # values
    "missing": "{what} isn't given",
    "not_a_length": "{what} isn't a length (a number)",
    "too_far": "{what} is more than 1,000,000,000 in (about 15,800 miles) from the origin: not a place in a house",
    "not_finite": "it came out too large to be a number (from lengths far apart)",
    "not_measured_yet": "Gordium doesn't measure this yet",
    "in_more_not_rules": "Gordium works this out (shown with the extra values) but doesn't give it to the rules yet",
    "negative": "{what} is {value} in: a size can't be less than zero",
    "not_a_point": "{what} isn't a list of {n} numbers",
    "not_an_outline": "{what} isn't an outline of at least 3 points that encloses an area",
    "not_a_polyline": "{what} isn't a line of at least 2 points",
    "not_a_rectangle_given": "{what} isn't a rectangle (left, right, bottom, top, with right > left and top > bottom)",
    "choice": "{what} is {got!r}, not one of {choices}",
    "operation_undecided": "the {what}'s operation ({operation}) doesn't say {question}",
    # rooms and ceilings
    "two_ceilings": "both a ceiling height and ceiling surfaces are given: give one",
    "no_ceiling": "the room's ceiling isn't given (a ceiling height, or the ceiling surfaces)",
    "low_ceiling": "part of the room's ceiling is {height} in above the floor, under 7 ft: which part of the floor "
                   "counts (R312.3) isn't measured yet",
    "surface_vertical": "{what} is vertical: give the underside of what is overhead",
    "surface_not_flat": "{what} isn't flat (a point is {off} in off its plane): give it as flat pieces",
    "surface_out_of_range": "{what} has coordinates too large to measure",
    "shapes_failed": "{what}: the geometry library couldn't work out the shapes (edges so nearly parallel it can't "
                     "tell where they meet): check the drawing near there",
    "not_covered": "{what} doesn't cover the whole {region}: give everything above it",
    "nothing_overhead": "nothing above the flight is given: give what is above it (a ceiling, the floor above, a beam)",
    # escape openings
    "room_unknown": "the room the opening is in isn't one of the rooms given",
    "room_twice": "{count} rooms have the id {id!r}: which one the opening is in is unclear",
    "operation_needs_clear": "a{n} {operation} window's clear opening depends on how far it opens and its hardware: "
                             "give the maker's net clear opening (its clear width, height, bottom and source)",
    "no_frame": "the opening's frame isn't given (and no maker's clear opening)",
    "hinge_angle": "the hinged sash's open angle ({angle}°) isn't between 0 and 180",
    "no_sashes": "the open sashes of a sliding window aren't given",
    "clear_in_pieces": "the open sashes leave the opening in {count} pieces: which is the clear opening is unclear",
    "clear_not_rectangle": "the clear opening left by the open sashes isn't a rectangle",
    "clear_differs": "the maker's clear opening and the drawn one differ ({which}): which is right is unclear",
    "clear_outside_frame": "the maker's clear opening is bigger than its frame, or reaches outside it: which is right "
                           "is unclear",
    "sash_outside_frame": "open sash {n} reaches outside the frame: a sliding sash opens within it",
    "sash_smaller_than_frame": "the hinged sash ({width} in wide, {thickness} in thick) doesn't close the "
                               "{frame} in frame: the rest of the frame isn't an opening",
    "not_a_door": "the opening is a window: whether it is a side-hinged or sliding door is asked only of a door",
    "no_clear_opening": "the opening doesn't open (no clear opening), so it has no bottom",
    "sill_below_floor": "the opening's bottom is {sill} in from its room's floor, below it: check the room's floor elevation and the opening's position",
    "no_ground": "the finished ground level outside the opening isn't given",
    "ground_mixed": "the ground outside the opening is within 44 in of its bottom at some points and not at others",
    "readings_differ": "the readings give different answers; {question}",
    # stairs
    "spiral_not_said": "whether the flight is a spiral stairway isn't given (yes or no)",
    "spiral_not_straight": "the flight is said not to be a spiral stairway, but it isn't measured as a straight "
                           "flight ({reason}): its shape isn't known",
    "spiral_but_straight": "the flight is said to be a spiral stairway, but its nosings make a straight flight with "
                           "rectangular treads: which is right is unclear",
    "spiral_not_shown": "the flight is said to be a spiral stairway, but nothing measured shows R202's closed circular "
                        "form around a supporting column (a curved stair isn't one): its shape isn't known",
    "nosings_out_of_range": "the stair's nosings have coordinates too large to measure",
    "too_few_nosings": "the flight needs at least {n} nosings (each tread's leading edge, and the top one) for this",
    "nosing_not_level": "nosing {n} isn't level (its ends are {off} in apart in height)",
    "not_bottom_to_top": "the nosings don't go up from the bottom one at a time (riser {n} is {rise} in)",
    "winders": "the treads aren't rectangular (nosing {n}'s ends are {off} in apart along the run): winder treads "
               "are measured at the walkline, not yet",
    "nosings_not_forward": "the nosings don't move forward up the flight (tread {n} is {depth} in deep)",
    "side_not_along": "the {side} {what} doesn't run along the flight from its first nosing to its top one",
    "side_off_treads": "the stair's {side} side stands {off} in out beyond its treads' ends, more than a skirt or "
                       "stringer between them ({most} in): it doesn't bound this stair (draw it where the treads end, "
                       "or give that side as open)",
    "sides_cross": "the stair's sides meet or cross (clear width {width} in)",
    "treads_cross": "at the treads, a tread's end meets or crosses the other side (clear width {width} in): check "
                    "the nosings' ends and the stair's sides",
    "handrails_cross": "at handrail height, a handrail meets or crosses the other side (clear width {width} in): "
                       "check each handrail's side",
    "handrail_side": "a handrail's side is {got!r}, not left or right",
    "handrail_part_way": "no {side} handrail runs the whole flight between the stair's sides (from above its "
                         "lowest nosing to above its top one, R320.5): whether that side has a handrail isn't "
                         "measured",
    # guards
    "guard_top_not_drawn": "the guard's members don't reach its stated top all along it (at its lowest the drawn "
                           "guard is {least} in high): which is its height is unclear",
    "guard_kind": "say whether the guard is along a stair or at a level walking surface: give one",
    "guard_opening_shape": "an opening in the guard isn't a rectangle: the largest sphere through it isn't measured "
                           "yet",
    "stair_unknown": "the stair the guard is along isn't one of the stairs given (by its id)",
    "stair_unread": "the stair the guard is along couldn't be measured: {reason}",
    "guard_no_side": "both of the stair's sides are given as open: a guard along it stands on neither (give the "
                     "side the guard stands on as the guard's inside face, as that side of the stair)",
    "guard_off_side": "the guard's top line doesn't stand along a side of its stair ({off} in, in plan, from the "
                      "nearer side drawn, at its farthest; within {on} in is drawing noise): which side it protects "
                      "is unclear (a side with a guard is given as the guard's inside face, as that side of the stair)",
    "stair_guard_openings": "a stair guard's openings (the 4 3/8 in sphere, the triangle at each step) aren't measured "
                            "yet",
    # doors
    "not_side_hinged": "R318.2 measures a side-hinged door open 90 degrees; this door is {operation}",
    "stops_wrong_way": "the latch-side stop isn't on the far side of the opening from the hinge side",
    "leaf_no_thickness": "the door leaf's closed corners give it no thickness: a leaf is thicker than nothing",
    "leaf_not_closing": "the closed leaf stops {short} in short of the latch-side stop (within 1/16 in is drawing "
                        "noise): the leaf drawn doesn't close this opening",
    "leaf_behind_hinge_stop": "the closed leaf's hinge edge stands {back} in behind the hinge-side stop, more than a "
                              "stop laps a leaf ({most} in): the leaf drawn doesn't close this opening (a swing-clear "
                              "hinge isn't measured yet)",
    "pin_off_leaf": "the hinge pin stands {off} in back from the leaf's hinge-side corner (behind the face it "
                    "swings toward, or toward the hinge jamb; within 1/16 in is drawing noise): the leaf drawn isn't "
                    "hung on that pin",
    "door_stated_shape": "the door's maker's clear opening isn't a width, a height and a source: neither clear "
                         "size counts",
    "door_stated_keys": "the door's maker's clear opening gives more than its width, height and source (also "
                        "{keys}): neither clear size counts",
    "door_stated_no_source": "the door's maker's clear opening doesn't say where it comes from "
                             "(its source, such as the maker's catalogue): neither clear size counts",
    "door_drawn_unread": "the door's clear {what} is drawn but can't be measured from the drawing ({reason}): the "
                         "maker's stated one alone could be more than the door as drawn, so neither counts",
    "not_positive": "{what} is {value} in: not more than zero",
}


class Words(str):
    """Words standing in for a value in a reason, shown as they are even where the reason quotes a value (!r)."""

    def __repr__(self):
        return str(self)


LISTED_MOST = 6                     # a list of more is said by its length, never item by item


def _item(x) -> str:
    """One item of a list as `counted` says it: text as itself (blank text "a blank name"), a number "a number",
    nothing "nothing", anything else as `said` says it."""
    if isinstance(x, str):
        return x if x.strip() else "a blank name"
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return "a number"
    return "nothing" if x is None else str(said(x))


def _in_words(items: list) -> str:
    words = [_item(x) for x in items]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def said(value, missing: str = "nothing"):
    """A value as a reason shows it, the one way every reason does: text as itself (quoted where the reason quotes
    it), a number as itself, and anything else in words, never Python's own (None, True, False, a list's brackets):
    nothing given is `missing` ("no form named", "no unit named"), a yes/no value "a yes/no value", any list "a list"
    (or "an empty list"), a mapping "a set of entries". Only `counted`, where a list is the right shape, says a list's
    items."""
    if isinstance(value, Words):
        return value
    if value is None:
        return Words(missing)
    if isinstance(value, bool):
        return Words("a yes/no value")
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return Words("a list" if value else "an empty list")
    if isinstance(value, dict):
        return Words("a set of entries")
    return Words("a value Gordium can't read")


def given_text(value, missing: str):
    """Text the model gave where a word of Gordium's belongs (the interior's format, its units), quoted so stray
    spaces show (' gordium.interior/1 '); nothing given, or blank text, is `missing` ("no form named"), never an
    empty gap; anything else as `said` shows it. One helper for the interior's reading and the route reading's."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return Words(missing)
    if isinstance(value, str):
        return Words(repr(value))
    return said(value, missing)


def counted(value, one: str, many: str):
    """A list given where a set number belongs (the one place a list is the right shape), as how many and which: "1
    side: r", "3 rooms: a, b and c" (more than LISTED_MOST: how many alone); anything else as `given_as` shows it
    (the text 'x', a set of entries)."""
    if isinstance(value, (list, tuple)):
        n = len(value)
        head = f"{n} {one if n == 1 else many}"
        return Words(head + f": {_in_words(list(value))}" if 0 < n <= LISTED_MOST else head)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Words(f"the number {value}")             # never read as a count: "gives the number 1, not 2 sides"
    return given_as(value)


def items(value) -> str:
    """A list's items in words ("a blank name and r", "a number and nothing"): its items, where its length is right
    and an item isn't."""
    return Words(_in_words(list(value)))


def given_as(value):
    """A value given where a yes/no one belongs, in words: "the text 'yes'", "1", "a list"."""
    return Words(f"the text {value!r}") if isinstance(value, str) else said(value)


class Stop(Exception):
    """A measurement that gets no value, with its reason from the table (every blank shown as `said` shows it)."""

    def __init__(self, which: str, /, **blanks):
        self.key = which
        self.reason = STOPS[which].format(**{k: said(v) for k, v in blanks.items()})
        super().__init__(self.reason)
