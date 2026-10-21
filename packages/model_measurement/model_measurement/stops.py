"""Every reason a measurement can stop with (it gets no value, and the rule says NEEDS REVIEW), in one place.

The measuring code gives a reason only through `stop(key, ...)`, so this table is the whole list: the README
lists each one word for word and tests/test_stop_list.py has a case that gives each (both checked from here).
"""

STOPS = {
    # the law reads more than one way and the readings disagree (each reading's question is in the README's table)
    "readings_differ": "the readings give different values; {question}",
    # the file
    "unreadable_file": "can't read {path}",
    "units": "the model's units ({units}) aren't supported",
    # the lot outline
    "no_lot_layer": "no {layer} layer",
    "no_lot_outline": "no closed lot outline on the {layer} layer",
    "several_lot_outlines": "{count} closed outlines on the {layer} layer: pick the lot",
    "lot_not_found": "the lot picked isn't a closed outline on the Site layer: pick the lot again",
    "lot_block": "a block on the {layer} layer can't be read yet (explode it)",
    "no_lot": "no lot outline",
    "lot_not_a_loop": "the lot outline isn't one closed loop of lot lines",
    "lot_crosses_itself": "the lot outline crosses itself ({why})",
    "survey_unknown": "say whether the lot outline is from a survey",
    "not_surveyed": "the lot outline isn't from a survey: the lot area needs one (an open question for the architects)",
    # the street side
    "no_street": "the street side isn't given: pick the lot line on the street",
    "street_not_a_lot_line": "a street line given doesn't match a lot line: pick the street side again",
    "street_lines_apart": "the street lot lines given aren't next to each other",
    "all_street": "every lot line is on a street: which yards are front, side and rear is an open question for the "
                  "architects",
    # corner lots (§325-19C)
    "corner_unknown": "say whether this is a corner lot (two streets meet at it, §325-19C): enter corner lot yes or no",
    "corner_lot": "a corner lot: which yards are front, side and rear yards, and which street's frontage is the lot "
                  "width (§325-19C), are open questions for the architects",
    # side and rear lot lines
    "lines_unclear": "the side and rear lot lines can't be told apart (more than {limit} lot lines could be either: "
                     "too many readings to list)",
    "no_rear_line": "no reading of the lot lines gives two side lot lines and a rear lot line (a triangular lot, for "
                    "one): an open question for the architects",
    # the ground
    "no_ground": "the ground level isn't given: enter it (the grade plane)",
    "ground_unknown": "say whether the ground is flat",
    "ground_off_building": "the ground level ({ground} ft) doesn't meet the buildings (they run from {bottom} to "
                           "{top} ft): check the ground level",
    "buried_solid": "a solid lies wholly under the ground ({ground} ft; it runs from {bottom} to {top} ft) and isn't "
                    "joined directly under the building: check the ground level and where the solid is",
    "sloped_ground": "sloped ground: the grade plane (§325-3) needs the ground levels around the walls, which aren't "
                     "measured yet",
    # facts a massing model doesn't show, until they are entered
    "no_use": "choose the use",
    "no_district": "enter the lot's zoning district (zone)",
    "no_stories": "no floor blocks are drawn for the building, so its stories aren't drawn: draw each story as its "
                  "own solid standing on the one below (as Gordium's starting building is), or enter the number of "
                  "stories",
    "stories_plain_part": "part of the building ({what}) isn't drawn as floor blocks, so its stories can't be "
                          "counted: enter the number of stories of the whole building",
    "stories_below_floors": "the stories typed ({typed}) are fewer than the floor blocks drawn ({drawn}): check the "
                            "count, or the floors",
    "basement_part": "part of the building ({what}) is below the ground: whether a basement or cellar counts as a "
                     "story (§325-3) isn't measured yet: an open question for the architects",
    "floors_misaligned": "floors misaligned: a floor block sticks out past the one below it (one floor moved on its "
                         "own?): move the floors together, or draw the overhang as part of its floor",
    "basement_story": "a floor block below the ground: whether a basement or cellar counts as a story (§325-3) isn't "
                      "measured yet: an open question for the architects",
    "no_rooms": "enter bedrooms / parking spaces",
    # the buildings
    "no_building": "no building on the Building layer",
    "same_id": "two building objects share the id {id}: one would be left out of the measurements",
    "no_main_building": "more than one building: pick the main building",
    "outside_lot": "a building isn't inside the lot",
    "open_solid": "a building isn't a closed solid",
    "open_mesh": "a building mesh isn't closed",
    "curved_surface": "a building has a curved surface (not measured yet)",
    "curved_edge": "a building has a curved edge (not measured yet)",
    "single_precision": "a building mesh's points may be single precision, too coarse this far from the origin to "
                        "measure to 0.01 ft (move it nearer the origin, or turn it into a solid)",
    "not_a_solid": "{kind} on the {layer} layer can't be measured yet (explode it or turn it into a solid)",
    # the height
    "no_roof": "the roof's shape can't be read (no faces open to the sky)",
    "other_height": "another solid's height can't be read: {reason}",
    "too_many_roofs": "too many solids with open roof questions to list every reading: pick the main building's "
                      "parts, or ask the architects",
}


def stop(key: str, **values) -> str:
    """The reason for `key`, with its blanks filled in."""
    return STOPS[key].format(**values)
