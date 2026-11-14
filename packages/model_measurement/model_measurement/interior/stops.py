"""Every reason an interior measurement can stop with (it gets no value, and a rule reading it says NEEDS REVIEW),
in one place.

The interior measuring code gives a reason only through `Stop(key, ...)`, so this table is the whole list:
docs/interior/interior_measurements.md lists each one and tests/test_interior_measures.py makes each happen.
"""

STOPS = {
    # the description as a whole
    "not_a_description": "the interior description isn't a mapping",
    "wrong_format": "the interior description's format isn't gordium.interior/1 (it says {got})",
    "units": "the interior description's units ({units}) aren't one of in, ft, mm, m",
    "not_read": "the {what} weren't read (no `{key}` in the description)",
    "not_a_list": "`{key}` in the description isn't a list",
    "not_a_mapping": "{what} #{n} isn't a mapping",
    "flag_missing": "{what} {name}: say whether it is {question} (`{key}`: true or false)",
    # values
    "missing": "{what} isn't given",
    "not_a_length": "{what} isn't a length (a number)",
    "negative": "{what} is {value} in: a size can't be less than zero",
    "not_a_point": "{what} isn't a list of {n} numbers",
    "not_an_outline": "{what} isn't an outline of at least 3 points that encloses an area",
    "not_a_polyline": "{what} isn't a line of at least 2 points",
    "not_a_rectangle_given": "{what} isn't a rectangle (left, right, bottom, top, with right > left and top > bottom)",
    "choice": "{what} is {got!r}, not one of {choices}",
    # rooms and ceilings
    "two_ceilings": "both a ceiling height and ceiling surfaces are given: give one",
    "no_ceiling": "the room's ceiling isn't given (a ceiling height, or the ceiling surfaces)",
    "low_ceiling": "part of the room's ceiling is {height} in above the floor, under 7 ft: which part of the floor "
                   "counts (R312.3) isn't measured yet",
    "surface_vertical": "{what} is vertical: give the underside of what is overhead",
    "surface_not_flat": "{what} isn't flat (a point is {off} in off its plane): give it as flat pieces",
    "surface_out_of_range": "{what} has coordinates too large to measure",
    "not_covered": "{what} doesn't cover the whole {region}: give everything above it",
    "nothing_overhead": "nothing above the flight is given: give what is above it (a ceiling, the floor above, a beam)",
    # escape openings
    "room_unknown": "the room the opening is in isn't one of the rooms given",
    "room_twice": "{count} rooms have the id {id!r}: which one the opening is in is unclear",
    "operation_needs_clear": "a{n} {operation} window's clear opening depends on how far it opens and its hardware: "
                             "give the maker's net clear opening (`stated_clear`)",
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
    "no_clear_opening": "the opening doesn't open (no clear opening), so it has no bottom",
    "no_ground": "the finished ground level outside the opening isn't given",
    "ground_mixed": "the ground outside the opening is within 44 in of its bottom at some points and not at others",
    "readings_differ": "the readings give different answers; {question}",
    # stairs
    "too_few_nosings": "the flight needs at least {n} nosings (each tread's leading edge, and the top one) for this",
    "nosing_not_level": "nosing {n} isn't level (its ends are {off} in apart in height)",
    "not_bottom_to_top": "the nosings don't go up from the bottom one at a time (riser {n} is {rise} in)",
    "winders": "the treads aren't rectangular (nosing {n}'s ends are {off} in apart along the run): winder treads "
               "are measured at the walkline, not yet",
    "nosings_not_forward": "the nosings don't move forward up the flight (tread {n} is {depth} in deep)",
    "side_not_along": "the {side} {what} doesn't run along the flight from its first nosing to its top one",
    "sides_cross": "the stair's sides meet or cross (clear width {width} in)",
    "handrails_cross": "at handrail height, a handrail meets or crosses the other side (clear width {width} in): "
                       "check each handrail's side",
    "handrail_side": "a handrail's side is {got!r}, not left or right",
    "handrail_part_way": "no {side} handrail runs the whole flight between the stair's sides (from above its "
                         "lowest nosing to above its top one, R320.5): whether that side has a handrail isn't "
                         "measured",
    # guards
    "guard_top_not_drawn": "the guard's members don't reach its stated top all along it (at its lowest the drawn "
                           "guard is {least} in high): which is its height is unclear",
    "guard_kind": "say whether the guard is along a stair (`stair`) or at a level walking surface "
                  "(`walking_surface`): give one",
    "guard_opening_shape": "an opening in the guard isn't a rectangle: the largest sphere through it isn't measured "
                           "yet",
    "stair_unknown": "the stair the guard is along isn't one of the stairs given (by its id)",
    "stair_unread": "the stair the guard is along couldn't be measured: {reason}",
    "stair_guard_openings": "a stair guard's openings (the 4 3/8 in sphere, the triangle at each step) aren't measured "
                            "yet",
    # doors
    "not_side_hinged": "R318.2 measures a side-hinged door open 90 degrees; this door is {operation}",
    "stops_wrong_way": "the latch-side stop isn't on the far side of the opening from the hinge side",
    "not_positive": "{what} is {value} in: not more than zero",
}


class Stop(Exception):
    """A measurement that gets no value, with its reason from the table."""

    def __init__(self, which: str, /, **blanks):
        self.key = which
        self.reason = STOPS[which].format(**blanks)
        super().__init__(self.reason)
