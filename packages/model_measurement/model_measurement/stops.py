"""Every reason a measurement can stop with (it gets no value, and the rule says NEEDS REVIEW), in one place.

The measuring code gives a reason only through `stop(key, ...)`, so this table is the whole list: the README
lists each one word for word and tests/test_stop_list.py has a case that gives each (both checked from here).
`code_of(words)` reads a reason back into its key and blanks (the site description names problems by key:
design_checker/site_json.py).
"""

import json
import re

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
    "two_streets": "the street lot lines given are on two streets: a corner lot (§325-19C), so which yards are front, "
                   "side and rear, and which street's frontage is the lot width, are open questions; answer Corner lot?",
    "one_street_or_two": "the street lot lines given turn {turn}° in all: do they face one street that bends, or two "
                         "streets at a corner? Answer Corner lot?, or name the street each lot line is on",
    "street_names_stale": "the street names saved for the street lot lines no longer match them (the lines were "
                          "picked again): pick the street side again",
    "all_street": "every lot line is on a street: which yards are front, side and rear is an open question for the "
                  "architects",
    # corner lots (§325-19C)
    "corner_unknown": "say whether this is a corner lot (two streets meet at it, §325-19C): enter corner lot yes or no",
    "corner_outside_residential": "a corner lot outside the residential districts: §325-19C gives two front yards only "
                                  "to corner lots in residential districts, so which street yard is a front yard and "
                                  "which a side yard is for a person to judge",
    "corner_one_street": "a corner lot, but the street lot lines given are all on one street: pick the lot lines on "
                         "both streets",
    "street_ids_needed": "which street lot lines are on which street isn't recorded: pick the street side so Gordium "
                         "knows which lines are which street (a corner lot's lot width is the frontage on one street, "
                         "§325-8A col. 7)",
    "street_lines_split": "the street lot lines recorded on one street aren't next to each other, or one lot line's "
                          "pieces are recorded on two streets: pick the street side again, one click on each street",
    "address_not_a_street": "the address street given isn't one run of the street lot lines on one street: pick the "
                            "lot line(s) on the street the address is on again",
    "rear_on_street": "the lot line opposite the address street is on a street too (a through lot, §325-8A(14)(d)): "
                      "which yards are rear and front is an open question for the architects",
    "no_side_line": "every side lot line is on a street (a lot on three streets): which yard is a side yard is an "
                    "open question for the architects",
    # side and rear lot lines
    "lines_unclear": "the side and rear lot lines can't be told apart (more than {limit} lot lines could be either: "
                     "too many readings to list)",
    "no_rear_line": "no reading of the lot lines gives two side lot lines and a rear lot line (a triangular lot, for "
                    "one): an open question for the architects",
    # the ground
    "no_ground": "the ground level isn't given: enter it (the grade plane)",
    "ground_unknown": "say whether the ground is flat",
    "ground_unclear": "the spot grades don't show the ground under the building (too few, or in a line): place "
                      "spot grades around the building",
    "ground_off_building": "the ground level ({ground} ft) doesn't meet the buildings (they run from {bottom} to "
                           "{top} ft): check the ground level",
    "buried_solid": "a solid lies wholly under the ground ({ground} ft; it runs from {bottom} to {top} ft) and isn't "
                    "joined directly under the building: check the ground level and where the solid is",
    "sloped_ground": "sloped ground: the grade plane (§325-3) needs the ground levels around the walls, which aren't "
                     "measured yet",
    "grade_off_walls": "spot grades no longer at the building's walls ({off} of {count} more than 2 ft from a wall, "
                       "{bare} walls without one): set the grade again",
    "grade_with_others": "with the other solids as part of the building, the grade plane needs spot grades at their "
                         "walls too (§325-3: each side of the building): place spot grades around every solid on "
                         "the Building layer",
    "grade_walls_unclear": "the building's walls can't be told apart in plan (no wall longer than 1 ft, a round or "
                           "finely faceted outline): set the grade as flat ground instead",
    "flat_sloped": "the ground falls about {fall} ft across the lot, but Gordium assumes it flat: height is measured "
                   "from the average ground level at the walls (the grade plane, §325-3), which Gordium can't set "
                   "yet: check height and stories against your survey",
    "flat_unknown": "Gordium assumes the ground flat, but couldn't read this lot's ground levels in full to show it "
                    "is: height is measured from the average ground level at the walls (the grade plane, §325-3): "
                    "check height and stories against your survey",
    "existing_grade": "measured from existing grade; the code's grade plane is finished ground level (§325-3): tick "
                      "No regrading near the house, or set the finished ground",
    # facts a massing model doesn't show, until they are entered
    "no_use": "choose the use",
    "no_district": "enter the lot's zoning district (zone)",
    "no_stories": "no floor blocks are drawn for the building, so its stories aren't drawn: draw each story as its "
                  "own solid standing on the one below (as Gordium's starting building is), or enter the number of "
                  "stories",
    "stories_below_floors": "the stories typed ({typed}) are fewer than the floor blocks drawn ({drawn}): check the "
                            "count, or the floors",
    "floors_apart": "parts of the building drawn one over another don't stand on each other (from {low} ft to "
                    "{high} ft): a floor not drawn, or a space open to below? draw the missing floor, or check the "
                    "blocks",
    "parts_overlap": "part of the building ({what}) starts partly inside the one below it (from {low} ft to {high} "
                     "ft): move it to stand on the one below, or join them",
    "part_raised": "part of the building ({what}) starts above the ground: it may be another story: draw its "
                   "stories as floor blocks, or check the count",
    "stories_below_one": "the stories typed ({typed}) are fewer than one: every building has at least a first story "
                         "(§325-3): check the count",
    "stories_above_drawn": "the stories typed ({typed}) are more than the drawing could hold ({what}, {height} ft "
                           "tall: at most {most}, at 7 ft a story, R305.1): check the count, or the drawing",
    "basement_part": "part of the building ({what}) is below the ground: whether a basement or cellar counts as a "
                     "story (§325-3) isn't measured yet: an open question for the architects",
    "floors_misaligned": "floors misaligned: a floor block sticks out past the one below it (one floor moved on its "
                         "own?): move the floors together, or draw the overhang as part of its floor",
    "basement_story": "a floor block below the ground: whether a basement or cellar counts as a story (§325-3) isn't "
                      "measured yet: an open question for the architects",
    "no_rooms": "enter bedrooms / parking spaces",
    "no_units": "enter the dwelling units, the rooms let for profit, and whether it is a conversion",
    "no_occupants": "enter the occupants (§325-3B OCCUPANT: in R-2c, every person with the right to occupy)",
    "no_building_units": "enter the dwelling units in the whole attached building, every lot it stands on",
    "no_occupant_split": "optional: enter the most occupants in any one dwelling unit (R-2c: settles a lot size that "
                         "depends on how the occupants are split)",
    "no_household": "enter who lives in the dwelling: the unrelated people in each unit, whether the owner lives there, "
                    "whether the household is a functional family unit (§325-3B)",
    # asked in the start box (Ben, 2026-10-30: a detached ADU is a building), so not among who lives there
    "no_adu": "say whether an accessory dwelling unit (ADU), attached or detached, is on the lot (§325-3B, §325-28)",
    "attached_counts_disagree": "{here} dwelling units on this lot but {building} in the attached building: part of "
                                "another building may be on this lot, or one of the counts or the use is off",
    "occupant_split_disagree": "the most occupants in one dwelling unit ({most}) is more than the occupants of every "
                               "unit on the lot together ({occupants}): check both counts",
    "occupant_counts_disagree": "{occupants} occupants on the lot, but {units} {unit_words} with at most {most} in any one "
                                "can hold only {held}, with no accessory dwelling unit on the lot: check {check} and "
                                "the accessory dwelling unit answer",
    "change_use_in_start_box": "change the use with Edit site… in the start box",
    "household_counts_disagree": "the count of unrelated people with minor dependent children included ({with_}) is "
                                 "lower than the count without them ({without}): check both counts",
    "no_home_occupation": "say whether a home occupation is planned and, if so, its floor area and its dwelling "
                          "unit's (§325-3B HOME OCCUPATION)",
    "no_primary_buildings": "enter the primary buildings on the lot (each separate building holding a home or other "
                            "permitted primary use, the main one included; not a garage, shed or accessory dwelling "
                            "unit) and whether every one holds the use entered (§325-8B(1))",
    "no_stream": "say whether any inlet wall or stream bank (at average water level) is within 20 ft of the lot and, if "
                 "so, how far the nearest new structure is from it (§325-26)",
    "stream_facts_disagree": "no stream or inlet is said to be within 20 ft of the lot, but a new structure is said to be "
                             "{distance} ft from one: check both answers",
    "no_garage_cars": "enter how many cars the lot's private garages hold, all together: every enclosed garage, attached "
                      "or detached (0 if there is none; a carport isn't enclosed) (chart p.2 notes 6 and 7)",
    "no_private_garages": "enter how many private garages are on the lot, an attached garage included (chart p.2 notes 6 "
                          "and 7: needed when the cars are over the limit)",
    "no_adu_kind": "say whether the accessory dwelling unit is attached (in or on the main building) or detached (its "
                   "own building) and, if detached, whether it is in an existing accessory building or new construction "
                   "(§325-3B, §325-28C(7))",
    "no_adus_on_parcel": "enter how many accessory dwelling units are on the parcel (§325-28C(1): one at most)",
    "no_adu_bedrooms": "enter the accessory dwelling unit's bedrooms (§325-28C(3): two at most)",
    "no_adu_floor_area": "enter the attached accessory dwelling unit's floor area and the main building's, the ADU "
                         "included (§325-28C(7)(a): 40% at most)",
    "no_south_hill": "say whether the lot is in the South Hill Overlay District (§325-8E, on the City's zoning map)",
    "no_abuts_r1": "say whether any R-1a or R-1b land is touching the lot (even at a corner), or across a street, alley, creek or other waterway, railroad or other right-of-way from it (§325-19E)",
    # the buildings
    "no_building": "no building on the Building layer",
    "geometry_error": "the drawing's geometry couldn't be worked out ({what}): check the building and lot outlines "
                      "for faces meeting at slivers",
    "same_id": "two building objects share the id {id}: one would be left out of the measurements",
    "empty_building": "a building object has nothing to measure (no faces): check it on the Building layer",
    "no_main_building": "more than one building: pick the main building",
    "no_adu_building": "pick the detached accessory dwelling unit's building (the solid it is in) with Pick the ADU's "
                       "building…",
    "no_detached_adu": "no detached accessory dwelling unit is said to be on the lot",
    "adu_not_found": "the solid picked as the accessory dwelling unit's building is no longer in the model: pick it again",
    "adu_is_main": "the solid picked as the accessory dwelling unit's building is the main building or touches it (part "
                   "of it, §325-18A): pick the ADU's own building, or say the ADU is attached",
    "adu_ground": "the spot grades don't give the ground at the accessory dwelling unit's own walls (§325-3 GRADE "
                  "PLANE): place spot grades around its building",
    "adu_stories_unclear": "the accessory dwelling unit's building, {height} ft tall, could hold up to {most} stories "
                           "(7 ft a story, R305.1): draw each story as its own solid standing on the one below",
    "no_accessory": "no accessory building on the lot (every solid is the main building or touches it)",
    "outside_lot": "a building isn't inside the lot: {what}",
    "open_solid": "a building isn't a closed solid: {what}",
    "open_mesh": "a building mesh isn't closed",
    "curved_surface": "a building has a curved surface (not measured yet)",
    "curved_edge": "a building has a curved edge (not measured yet)",
    "single_precision": "a building mesh's points may be single precision, too coarse this far from the origin to "
                        "measure to 0.01 ft (move it nearer the origin, or turn it into a solid)",
    "not_a_solid": "{kind} on the {layer} layer can't be measured yet (explode it or turn it into a solid)",
    # what the design tool says itself (the site description, design_checker/site_json.py): never the measuring's
    "inventory_incomplete": "the design tool didn't say everything on the lot was sent: anything not sent may be part "
                            "of a building, or another building (lot coverage counts every building on the lot, "
                            "§325-8A)",
    # a problem a design tool found and words itself (an object it couldn't send, said in the older Rhino plugin's own
    # words): it makes the building's measuring need review all the same. Never a reason the table has words for
    # (site_json refuses that: the reason's own code is sent), and never read back by code_of (TOOL_WORDS)
    "tool_words": "{words}",
    # a problem handed over as neither words nor a {code, args} pair a reason fills (a caller passing its own
    # objects): it is said, never dropped and never a crash, so what it stops needs review (words_of)
    "problem_unreadable": "a problem sent with the drawing can't be read ({what})",
    # what research settled and what is still open, read from the city's files (interpretations.py)
    "law_missing": "the city's files no longer have {what} (answered without naming the reading, or removed): the "
                   "measuring can't follow it",
    "reading_unknown": "a reading research lists ({reading}, {entry}) has no measuring code yet",
    # the height
    "eave_unclear": "no roof plane of the pitched roof's highest section lies over the walls: the wall plate can't "
                    "be found",
    "no_roof": "the roof's shape can't be read (no faces open to the sky)",
    "other_height": "another solid's height can't be read: {reason}",
    "too_many_roofs": "too many solids with open roof questions to list every reading: pick the main building's "
                      "parts, or ask the architects",
}


class Said(str):
    """Words made of reasons, each kept as data beside them: `parts`, ((code, blanks, words), …) in order, and
    `seps`, the words between them. A stop is one part (its key, its blanks, its words); words joined with `joined`
    keep every part, so what a row asks is read from its codes (design_checker/ui_data.py), never from its words.
    Anything else done to the words (an f-string, a replace) gives plain words: they are then one part, "words"."""

    def __new__(cls, parts, seps=()):
        parts, seps = tuple(parts), tuple(seps)
        text = (parts[0][2] + "".join(s + p[2] for s, p in zip(seps, parts[1:]))) if parts else ""
        obj = super().__new__(cls, text)
        obj.parts, obj.seps = parts, seps
        return obj

    def __reduce__(self):
        return (Said, (self.parts, self.seps))


def reason_part(code: str, words: str, **blanks) -> Said:
    """Words as one part of a reason, under its own code (a row's own reason, not the measuring's)."""
    return Said([(code, blanks, str(words))])


def parts_of(words) -> tuple:
    """The parts of a reason: its own (Said), else the words as one "words" part; none for no words."""
    if isinstance(words, Said):
        return words.parts
    return (("words", {}, str(words)),) if words else ()


def joined(texts, sep: str = "; "):
    """`sep`.join(texts), every part of each kept (the measuring's "; "-joined reasons)."""
    texts = list(texts)
    parts, seps = [], []
    for t in texts:
        mine = parts_of(t)
        if not mine:
            return sep.join(str(x) for x in texts)       # an empty piece: plain words, as join gives them
        if parts:
            seps.append(sep)
        parts += mine
        seps += list(t.seps) if isinstance(t, Said) else []
    return Said(parts, seps) if parts else ""


def mapped(words, fn):
    """fn over the words, each part's words through fn too where that gives the same words (a phrase replaced
    inside a part); else the new words as one "words" part, never a part misplaced."""
    if not isinstance(words, Said):
        return fn(words)
    whole = fn(str(words))
    each = Said([(c, b, fn(w)) for c, b, w in words.parts], words.seps)
    return each if str(each) == whole else reason_part("words", whole)


def stop(key: str, **values) -> str:
    """The reason for `key`, with its blanks filled in (a Said: its key and blanks kept beside its words)."""
    return Said([(key, values, STOPS[key].format(**values))])


try:                                       # a reason written to YAML is its words (the measuring's own output)
    import yaml as _yaml
    for _dumper in (_yaml.SafeDumper, _yaml.Dumper):
        _dumper.add_representer(Said, lambda d, s: d.represent_str(str(s)))
except ImportError:                        # pragma: no cover
    pass


def words_of(problem) -> str:
    """A problem in words: words as they are; a coded one ({"code": key, "args": {...}}, as the site description
    names problems: design_checker/site_json.py) as stop(key, **args) words it. Anything else (a code no reason
    has, blanks that don't fit, another kind of value) is said as problem_unreadable, so whatever it stops still
    needs review: never a crash, never dropped, never a pass. THE one way a problem becomes words."""
    if isinstance(problem, str):
        return problem
    if isinstance(problem, dict) and set(problem) == {"code", "args"} and problem["code"] in STOPS \
            and isinstance(problem["args"], dict) and sorted(problem["args"]) == sorted(set(blanks(problem["code"]))) \
            and all(isinstance(v, (str, int, float)) for v in problem["args"].values()):
        return stop(problem["code"], **problem["args"])
    try:
        what = json.dumps(problem, sort_keys=True, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        what = repr(problem)
    return stop("problem_unreadable", what=what if len(what) <= 120 else what[:117] + "...")


def said(problems) -> str:
    """Problems and reasons joined into one reason ("a; b"), each in words (words_of), every stop's parts kept
    (joined)."""
    return joined([words_of(p) for p in problems or []])


def in_words(site: dict) -> dict:
    """A site with every problem in words (words_of): the site's own, each building's and each unsent object's.
    A copy; the site given is left as it is. The measuring and the check read problems as words only."""
    out = dict(site)
    if isinstance(out.get("problems"), list):
        out["problems"] = [words_of(p) for p in out["problems"]]
    if isinstance(out.get("buildings"), list):
        out["buildings"] = [{**b, "problems": [words_of(p) for p in b["problems"]]}
                            if isinstance(b, dict) and isinstance(b.get("problems"), list) else b
                            for b in out["buildings"]]
    if isinstance(out.get("unsent"), list):
        out["unsent"] = [{**u, "problem": words_of(u["problem"])} if isinstance(u, dict) and "problem" in u else u
                         for u in out["unsent"]]
    return out


BLANK = re.compile(r"\{([a-z_]+)\}")


def blanks(key: str) -> list[str]:
    """The blanks of `key`'s reason, in order ("several_lot_outlines" -> ["count", "layer"])."""
    return BLANK.findall(STOPS[key])


def _pattern(template: str) -> re.Pattern:
    """A reason's words as a pattern: its fixed words exactly, each blank any text (as little as will do)."""
    parts = BLANK.split(template)          # fixed words, blank, fixed words, blank, ...
    return re.compile("".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.*?)" for i, p in enumerate(parts)) + r"\Z",
                      re.DOTALL)


TOOL_WORDS = "tool_words"     # any words at all: sent by its code, never guessed from words (code_of skips it)
PATTERNS = {key: _pattern(template) for key, template in STOPS.items() if key != TOOL_WORDS}


def _fixed(key: str) -> int:
    """How many of a reason's characters are fixed words (its blanks left out)."""
    return len(BLANK.sub("", STOPS[key]))


def code_of(words: str) -> tuple[str, dict]:
    """(key, blanks) of a reason given in words, the reverse of `stop`: stop(key, **blanks) gives `words` back.
    Where two reasons could give the words, the one with more fixed words is meant ("no closed lot outline on the
    Site layer" is no_lot_outline, though "no {layer} layer" could give it too, with a layer named "closed lot
    outline on the Site"). Words no reason gives, or two reasons give equally, are a plain error (ValueError), never
    a guess: the site description names every problem by its key, and a wrong key would be a different problem.
    The design tool's own words (TOOL_WORDS) are never read back from words: any words would do, so they are only
    ever sent by that code."""
    found = sorted(((key, m.groupdict()) for key, rx in PATTERNS.items() for m in [rx.match(words)] if m),
                   key=lambda kb: -_fixed(kb[0]))
    if not found or (len(found) > 1 and _fixed(found[0][0]) == _fixed(found[1][0])):
        raise ValueError(f"{'no' if not found else 'more than one'} measuring reason gives the words {words!r}"
                         + (f" ({', '.join(k for k, _ in found)})" if found else ""))
    return found[0]
