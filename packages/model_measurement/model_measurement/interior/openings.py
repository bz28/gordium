"""Emergency escape and rescue openings (R319): the net clear opening's area, height and width, the height of its
bottom above the floor, and whether it is a grade-floor opening; whether it is a door (and a side-hinged or sliding
one), read from its operation; an area well's size where one is given.

The clear opening is what is left of the frame's opening, seen straight on (perpendicular to the wall), with the
window or door fully open by its normal operation (R319.2.2: "the result of normal operation"):
  - a sliding window or door (double-hung, single-hung, horizontal slider, sliding door): the frame's opening less
    every sash in its fully open position, as drawn;
  - a hinged one (casement, side-hinged door): less the hinged sash where it stands at its open angle: from the
    jamb it covers o + max(0, w cos a) + t sin a of the width (o how far its hinge edge stands off the jamb when
    open, as its hardware sets it, 0 for a sash hinged at the jamb; w its width, t its thickness, a the angle);
  - a fixed one: no clear opening at all;
  - any other (awning, hopper, pivot, tilt-turn, other): the maker's stated net clear opening only.
The maker's stated clear opening (`stated_clear`) may be given for any; given with the drawn one, the two must
agree within 1/16 in (then the smaller opening counts), else no value. Definitions:
docs/interior/interior_measurements.md.
"""

import math

from shapely.geometry import box
from shapely.ops import unary_union

from model_measurement.interior.read import choice, name_of, number, tidy
from model_measurement.interior.stops import Stop, Words, given_as

SLIDING = ("double_hung", "single_hung", "horizontal_slider", "sliding_door")
HINGED = ("casement", "side_hinged_door")
MAKER_ONLY = ("awning", "hopper", "pivot", "tilt_turn", "other")
OPERATIONS = SLIDING + HINGED + ("fixed",) + MAKER_ONLY
AGREE = 1 / 16          # in: a maker's clear opening and the drawn one agree within this
GRADE_FLOOR = 44.0      # in: the definition of a grade-floor emergency escape and rescue opening
CLEAR = ("opening_net_clear_area", "opening_net_clear_height", "opening_net_clear_width")
NONE = "none"           # the opening doesn't open
BELOW = 1 / 16          # in: a sill this far under the floor is drawing noise (read as 0); more is a wrong floor
LADDER_DEPTH = 44.0     # in: the one area well depth the rules read (BCNYS 1031.5.2, RCNYS R319.4.2: "more than 44
#                         inches" needs a ladder or steps); a least depth past it settles every one of them
# the least depth handed to the rules stands on this reading (rule_format.parts.rows: a row that would comply on it
# needs review until it is confirmed; a fail keeps the reading beside it)
DEPTH_READING = ("Gordium's reading: an area well's floor is at or below the bottom of the clear opening it serves "
                 "(a clear opening whose bottom is under the well's floor isn't clear, and BCNYS 1031.5.1 and RCNYS "
                 "R319.4.1 ask the well to let the opening be fully opened), so the well is at least as deep as the "
                 "ground outside stands above that bottom: {least} in, from the ground the model gives (its floor "
                 "isn't drawn)")
# whether an opening is a door, read from its operation: these name a door or a window; fixed glass, pivot and
# tilt-turn units and `other` are made as doors and as windows, so they don't say
IS_DOOR = {"side_hinged_door": True, "sliding_door": True, "casement": False, "double_hung": False,
           "single_hung": False, "horizontal_slider": False, "awning": False, "hopper": False}


def drawn_clear(o: dict, reader, operation: str):
    """The clear opening from the frame and its sashes: (left, right, bottom, top), or NONE."""
    frame = reader.rectangle(o.get("frame"), "the opening's frame")
    if operation == "fixed":
        return NONE
    left, right, bottom, top = frame
    if operation in HINGED:
        h = o.get("hinged")
        if not isinstance(h, dict):
            raise Stop("missing", what="the hinged sash (its side, open angle, width, thickness and hinge "
                                     "offset)")
        side = choice(h.get("side"), ("left", "right"), "the hinged sash's side")
        angle = number(h.get("open_angle"), "the hinged sash's open angle")
        if not 0 < angle <= 180:
            raise Stop("hinge_angle", angle=angle)
        width = reader.size(h.get("sash_width"), "the hinged sash's width")
        thick = reader.size(h.get("sash_thickness"), "the hinged sash's thickness")
        if width < right - left - AGREE or thick <= 0:      # one sash closes the whole frame; it has a thickness
            raise Stop("sash_smaller_than_frame", width=tidy(width), thickness=tidy(thick), frame=tidy(right - left))
        offset = reader.size(h.get("hinge_offset"), "the hinged sash's offset from the jamb when open")
        a = math.radians(angle)
        covered = offset + max(0.0, width * math.cos(a)) + thick * math.sin(a)
        blocks = [box(left, bottom, left + covered, top) if side == "left"
                  else box(right - covered, bottom, right, top)]
    else:
        sashes = o.get("sashes")
        if not isinstance(sashes, list) or not sashes:
            raise Stop("no_sashes")
        blocks = []
        for n, s in enumerate(sashes, 1):
            l, r, b, t = reader.rectangle(s, f"open sash {n}")
            if l < left - AGREE or r > right + AGREE or b < bottom - AGREE or t > top + AGREE:
                raise Stop("sash_outside_frame", n=n)
            blocks.append(box(l, b, r, t))
    free = box(left, bottom, right, top).difference(unary_union(blocks))
    if free.is_empty or free.area <= 0:
        return NONE
    if free.geom_type != "Polygon":
        raise Stop("clear_in_pieces", count=len(free.geoms))
    if abs(free.area - free.envelope.area) > 1e-9 * max(1.0, free.envelope.area):
        raise Stop("clear_not_rectangle")
    l, b, r, t = free.bounds
    return l, r, b, t


def stated(o: dict, reader):
    s = o.get("stated_clear")
    if not isinstance(s, dict):
        raise Stop("missing", what="the maker's clear opening (its clear width, height, bottom and source)")
    width = reader.size(s.get("width"), "the maker's clear width")
    height = reader.size(s.get("height"), "the maker's clear height")
    bottom = reader.length(s.get("bottom"), "the maker's clear opening's bottom")
    if width == 0 or height == 0:
        return NONE
    return 0.0, width, bottom, bottom + height


def clear_opening(o: dict, reader):
    """(the clear opening, its bottoms). The opening is (left, right, bottom, top) in the wall's own elevation, or
    NONE; its bottoms are every bottom it could have (the drawn one and the maker's, where both are given and agree
    within 1/16 in), so grade-floor is read at each."""
    operation = choice(o.get("operation"), OPERATIONS, "the opening's operation")
    has_stated, has_frame = o.get("stated_clear") is not None, o.get("frame") is not None
    if operation in MAKER_ONLY or (not has_frame and has_stated):
        if not has_stated:
            raise Stop("operation_needs_clear", n="n" if operation[0] in "aeiou" else "", operation=
                       operation.replace("_", " "))
        maker = stated(o, reader)
        if operation == "fixed" and maker != NONE:
            raise Stop("clear_differs", which="a fixed window doesn't open, the maker's opening does")
        if has_frame and maker != NONE:
            capped = fits(maker, reader.rectangle(o.get("frame"), "the opening's frame"))
            return capped, sorted({maker[2], capped[2]})
        return maker, [] if maker == NONE else [maker[2]]
    if not has_frame:
        raise Stop("no_frame")
    drawn = drawn_clear(o, reader, operation)
    if not has_stated:
        return drawn, [] if drawn == NONE else [drawn[2]]
    maker = stated(o, reader)
    if drawn == NONE or maker == NONE:
        if drawn == maker:
            return NONE, []
        raise Stop("clear_differs", which="one opens, the other doesn't")
    dims = {"width": (drawn[1] - drawn[0], maker[1] - maker[0]), "height": (drawn[3] - drawn[2], maker[3] - maker[2]),
            "bottom": (drawn[2], maker[2])}
    off = [k for k, (a, b) in dims.items() if abs(a - b) > AGREE]
    if off:
        raise Stop("clear_differs", which=", ".join(off))
    width, height = min(dims["width"]), min(dims["height"])
    bottom = max(dims["bottom"])                  # the higher: the cautious sill height
    return (0.0, width, bottom, bottom + height), list(dims["bottom"])


def fits(maker, frame):
    """A maker's clear opening can't be bigger than the frame it is in, or reach outside it (1/16 in to spare, for
    drawing noise). Within that, the opening is cut back to the frame: no wider, no lower and no taller than it."""
    width, height = maker[1] - maker[0], maker[3] - maker[2]
    left, right, bottom, top = frame
    if width > right - left + AGREE or height > top - bottom + AGREE or maker[2] < bottom - AGREE \
            or maker[3] > top + AGREE:
        raise Stop("clear_outside_frame")
    low, high = max(maker[2], bottom), min(maker[3], top)
    return 0.0, min(width, right - left), low, high


def grounds(o: dict, reader) -> list[float]:
    g = o.get("ground_outside")
    if g is None:
        raise Stop("no_ground")
    if isinstance(g, list):
        if not g:
            raise Stop("no_ground")
        return [reader.length(v, "the ground outside the opening") for v in g]
    return [reader.length(g, "the ground outside the opening")]


def at_grade(bottom: float, levels: list[float]):
    """True if the bottom is within 44 in of every ground level given, False if of none; None if mixed."""
    near = [abs(bottom - g) <= GRADE_FLOOR + 1e-9 for g in levels]
    return True if all(near) else False if not any(near) else None


def measure_opening(o: dict, reader, floor_of) -> tuple[dict, dict, dict, dict]:
    """(measures, more, not_measured, confirm) for one escape opening. floor_of(room id): its finished floor elevation
    (Stop if the room isn't known). `confirm`, {measure: words}: a measure that stands on Gordium's reading
    (rule_format.parts.rows shows it with each row reading it; a row that would comply on it needs review)."""
    measures, more, stopped, confirm = {}, {}, {}, {}

    def stop_all(names, reason):
        for n in names:
            stopped[n] = reason

    bottoms = []
    try:
        clear, bottoms = clear_opening(o, reader)
    except Stop as s:
        stop_all(CLEAR + ("opening_sill_height", "opening_at_grade"), s.reason)
        clear = None
    if clear == NONE:
        measures.update({n: 0.0 for n in CLEAR})
        stop_all(("opening_sill_height", "opening_at_grade"), Stop("no_clear_opening").reason)
    elif clear is not None:
        left, right, bottom, top = clear
        measures["opening_net_clear_width"] = tidy(right - left)
        measures["opening_net_clear_height"] = tidy(top - bottom)
        measures["opening_net_clear_area"] = tidy((right - left) * (top - bottom) / 144)
        try:
            sill = bottom - floor_of(o.get("room"))
            if sill < -BELOW:             # an opening's bottom below its room's floor: the floor or the opening is wrong
                raise Stop("sill_below_floor", sill=tidy(sill))
            measures["opening_sill_height"] = tidy(max(sill, 0.0))
        except Stop as s:
            stopped["opening_sill_height"] = s.reason
        try:
            measures["opening_at_grade"] = grade_floor(o, reader, bottoms)
        except Stop as s:
            stopped["opening_at_grade"] = s.reason
    try:
        operation = choice(o.get("operation"), OPERATIONS, "the opening's operation")
        if operation not in IS_DOOR:
            raise Stop("operation_undecided", what="opening", operation=operation.replace("_", " "),
                       question="whether it is a door or a window")
        measures["opening_is_door"] = IS_DOOR[operation]
        if IS_DOOR[operation]:           # R319.3 asks it of a door only: both door operations are one or the other
            measures["opening_door_hinged_or_sliding"] = True
        else:
            stopped["opening_door_hinged_or_sliding"] = Stop("not_a_door").reason
    except Stop as s:
        stop_all(("opening_is_door", "opening_door_hinged_or_sliding"), s.reason)
    if o.get("area_well") is not None:
        try:
            more.update(area_well(o, reader))
        except Stop as s:
            stop_all(("area_well_area", "area_well_width", "area_well_projection", "area_well_depth"), s.reason)
    if "stated_well" in o:
        given, why, reading = stated_well(o, reader, more, bottoms if clear not in (None, NONE) else [])
        measures.update(given)
        stopped.update(why)
        confirm.update(reading)
        # an opening that is, or may be, below the ground (stated so, shown so, within 1/16 in of it, or a statement
        # the ground contradicts) with no well drawn may stand in a well whose floor isn't known, and either may be
        # "the finished ground level adjacent to the opening" (open question 4.6): a host that sends what it states of
        # the well (the Revit reader, its ground read from a Toposolid) gets a grade-floor answer only where below
        # grade is settled as no (to do: every host, which changes test house 5's second window)
        if o.get("area_well") is None and "opening_at_grade" in measures and measures.get("opening_below_grade") is not False:
            del measures["opening_at_grade"]
            stopped["opening_at_grade"] = Stop("grade_floor_well_unknown").reason
    return measures, more, stopped, confirm


def grade_floor(o: dict, reader, bottoms: list[float]) -> bool:
    """Whether the opening's bottom is within 44 in of the finished ground level adjacent to it. In an area well
    "adjacent" reads two ways (the well's floor, or the ground around the well): both are measured, and they must
    agree. Where the drawn and the maker's bottom both stand (agreeing within 1/16 in), each must give the same
    answer, else no value (whichever is right is the less favourable)."""
    readings = {"the ground around it": grounds(o, reader)}
    if o.get("area_well") is not None:
        well = o["area_well"]
        floor = reader.length(well.get("floor_elevation") if isinstance(well, dict) else None,
                              "the area well's floor elevation")
        readings["the area well's floor"] = [floor]
    each = [{k: at_grade(b, v) for k, v in readings.items()} for b in bottoms]
    if len({tuple(a.values()) for a in each}) > 1:
        raise Stop("clear_differs", which="the bottom, for grade-floor")
    answers = each[0]
    if None in answers.values():
        raise Stop("ground_mixed")
    if len(set(answers.values())) > 1:
        raise Stop("readings_differ", question="is the finished ground level adjacent to an opening in an area well "
                   "the well's floor or the ground around the well? (" + "; ".join(
                       f"{k}: {'within' if v else 'not within'} 44 in" for k, v in answers.items()) + ")")
    return answers.popitem()[1]


def area_well(o: dict, reader) -> dict:
    well = o["area_well"]
    if not isinstance(well, dict):
        raise Stop("missing", what="the area well's floor elevation, width and projection")
    width = reader.size(well.get("width"), "the area well's width")
    projection = reader.size(well.get("projection"), "the area well's projection")
    floor = reader.length(well.get("floor_elevation"), "the area well's floor elevation")
    depth = max(grounds(o, reader)) - floor          # deepest: R319.4.2's ladder turns on the depth
    return {"area_well_area": tidy(width * projection / 144), "area_well_width": tidy(width),
            "area_well_projection": tidy(projection), "area_well_depth": tidy(depth)}


# ---- what the architect states of the opening and its area well (`stated_well`; in Revit, the window's or door's own
# marks: a well isn't in Revit's vocabulary), and what the ground given outside it shows ---------------------------------

# the description's key -> (the measure it gives, what it says in a reason, its kind: yes_no; size, a length that can't
# be less than zero, in inches; area, in square feet; word, the ladder's), and the marks its reasons name, in plain
# words (in Revit, Gordium: Below grade and the Gordium: Well marks on the window or door)
STATED_WELL = {
    "below_grade": ("opening_below_grade", "whether the bottom of its clear opening is below the adjacent grade",
                    "yes_no", "its below-grade mark"),
    "area": ("area_well_area", "its area well's horizontal area", "area", "its area well marks"),
    "width": ("area_well_width", "its area well's width along the wall", "size", "its area well marks"),
    "projection": ("area_well_projection", "its area well's projection out from the wall", "size",
                   "its area well marks"),
    "depth": ("area_well_depth", "its area well's vertical depth", "size", "its area well marks"),
    "ladder": (None, "what its area well has to climb out by (a ladder, steps or none)", "word",
               "its area well marks"),
    "ladder_width": ("area_well_ladder_width", "the inside width of its area well's ladder or steps", "size",
                     "its area well marks"),
    "ladder_projection": ("area_well_ladder_projection", "how far its area well ladder's rungs stand out from the wall",
                          "size", "its area well marks"),
    "rung_spacing": ("area_well_rung_spacing", "the spacing of its area well ladder's rungs", "size",
                     "its area well marks"),
    "step_tread": ("area_well_step_tread", "the tread depth of its area well's steps", "size", "its area well marks"),
    "step_riser": ("area_well_step_riser", "the riser height of its area well's steps", "size",
                   "its area well marks"),
    "full_height": ("area_well_ladder_full_height", "whether its area well's ladder or steps run its full height",
                    "yes_no", "its area well marks"),
    "ladder_encroachment": ("area_well_ladder_encroachment",
                            "how far its area well's ladder or steps reach into the well's required dimensions", "size",
                            "its area well marks"),
    "other_encroachment": ("area_well_other_encroachment",
                           "how far anything else in its area well reaches into the well's required dimensions", "size",
                           "its area well marks"),
}
# `ladder`'s words -> (area_well_ladder, area_well_steps). A ladder or steps the opening blocks when open is no ladder
# 1031.5.2 accepts ("The ladder or steps shall not be obstructed by the emergency escape and rescue opening when the
# window or door is in the open position."), but steps are still steps
LADDER_WORDS = {"ladder": (True, False), "steps": (True, True), "ladder_blocked": (False, False),
                "steps_blocked": (False, True), "none": (False, False)}
LADDER_MEASURES = ("area_well_ladder", "area_well_steps")


def well_field(key: str) -> str:
    """The description's field a stated measure comes from (a host's mark answers it: design_checker.panel_data)."""
    return f"openings[].stated_well.{key}"


# {measure: (the field that states it, the marks its reasons name)}: what panel_data names in a mark's cause
WELL_FIELDS = {**{m: (well_field(k), mark) for k, (m, _, _, mark) in STATED_WELL.items() if m},
               **{m: (well_field("ladder"), STATED_WELL["ladder"][3]) for m in LADDER_MEASURES}}


def stated_well(o: dict, reader, more: dict, bottoms=()) -> tuple[dict, dict, dict]:
    """(measures, not_measured, confirm) from what the architect states of the opening and its area well
    (`stated_well`, a host's marks), and what the ground given outside it (`ground_outside`) shows. Each one given is
    handed to the rules as the architect's statement; one left out is not stated (its reason names the mark that
    states it), never 0 or no. Where the drawn well (`area_well`, kept in `more`) gives the same measure, the two must
    agree within 1/16 in (1/16 sq ft for the area), else neither is used; a stated area over the stated width times
    projection can't be. With no drawn well, the ground given measures what isn't stated (`ground_shows`): below grade
    where it stands more than 1/16 in above the clear opening's bottom (`bottoms`, every bottom it could have), not
    below where every bottom stands more than 1/16 in above it, else no value; and, below grade, the well's least depth
    (the ground over the highest bottom), handed to the rules only past 44 in and on Gordium's reading (`confirm`:
    DEPTH_READING). A statement wins over the ground, unless the two disagree by more than 1/16 in: then neither is
    used. Not below grade can't stand beside a drawn well, a ground given above a bottom, or a ground given where no
    bottom is known; below grade can't stand beside a ground given below every bottom; a stated depth can't be less
    than the least depth. What reaches into the well's required dimensions is two facts of its own, which both codes'
    size rules read (BCNYS 1031.5.1, RCNYS R319.4.1). A key the format doesn't know, or `stated_well` not a mapping,
    refuses every stated measure (a mistyped key must never read as settled)."""
    name = name_of(o)
    s = o.get("stated_well")
    if not isinstance(s, dict) or (extra := sorted(str(k) for k in s if k not in STATED_WELL)):
        what = "it isn't a mapping" if not isinstance(s, dict) else ("it gives " + ", ".join(extra) +
                                                                      ", which the format doesn't know")
        return {}, {m: Stop("well_stated_unread", name=name, what=Words(what)).reason for m in WELL_FIELDS}, {}

    def stop(which, key, **more_blanks):
        _, words, _, mark = STATED_WELL[key]
        return Stop(which, name=name, what=Words(words), mark=Words(mark), **more_blanks)

    # what the ground given shows, used only with no drawn well (whose own floor and depth are the drawing's)
    shown, top, low, high = ("none", None, None, None) if o.get("area_well") is not None else ground_shows(o, reader, bottoms)
    least = tidy(top - high) if shown == "below" else None
    measures, stopped, confirm = {}, {}, {}
    for key, (measure, words, kind, _) in STATED_WELL.items():
        if kind == "word":
            continue
        got = s.get(key)
        try:
            if key == "below_grade":
                measures[measure] = _below_grade(got, shown, top, o, reader, bottoms, lambda w, **b: stop(w, key, **b),
                                                 low=low, high=high)
                continue
            if got is None:
                drawn = more.get(measure)
                if isinstance(drawn, (int, float)) and not isinstance(drawn, bool):
                    raise stop("well_drawn_not_stated", key)
                if key == "depth" and least is not None:
                    if least > LADDER_DEPTH + AGREE:      # deeper than 44 in whatever its floor (at or below the bottom)
                        measures[measure] = least
                        confirm[measure] = DEPTH_READING.format(least=f"{least:g}")
                        continue
                    raise stop("well_depth_least", key, least=Words(f"{least:g}"))
                raise stop("well_not_stated", key)
            if kind == "yes_no":
                if not isinstance(got, bool):
                    raise stop("well_stated_not_read", key, got=given_as(got))
                measures[measure] = got
                continue
            try:
                value = reader.size(got, words) if kind == "size" else _area(reader, got, words)
            except Stop as bad:
                raise stop("well_stated_bad", key, reason=Words(bad.reason)) from None
            drawn = more.get(measure)
            if isinstance(drawn, (int, float)) and not isinstance(drawn, bool) and abs(drawn - value) > AGREE:
                unit = " sq ft" if kind == "area" else " in"
                raise stop("well_disagree", key, drawn=Words(f"{tidy(drawn):g}{unit}"),
                           stated=Words(f"{tidy(value):g}{unit}"))
            if key == "depth" and least is not None and value < least - AGREE:
                raise stop("well_depth_disagree", key, stated=Words(f"{tidy(value):g}"), least=Words(f"{least:g}"))
            measures[measure] = tidy(value)
        except Stop as s_:
            stopped[measure] = s_.reason
    area, w, p = (measures.get(k) for k in ("area_well_area", "area_well_width", "area_well_projection"))
    if area is not None and w is not None and p is not None and area > w * p / 144 + AGREE:
        # a well within its width and projection holds no more than their rectangle: one of the three is wrong
        why = stop("well_area_over_size", "area", width=w, projection=p, rectangle=tidy(w * p / 144)).reason
        for m in ("area_well_area", "area_well_width", "area_well_projection"):
            measures.pop(m)
            stopped[m] = why
    word = s.get("ladder")
    climb = LADDER_MEASURES
    try:
        if word is None:
            raise stop("well_not_stated", "ladder")
        if not isinstance(word, str) or word not in LADDER_WORDS:
            raise stop("well_stated_not_read", "ladder", got=Words(f"{given_as(word)}, not one of " +
                                                                 ", ".join(LADDER_WORDS)))
        if word == "none":
            # nothing to climb, so no ladder or steps reach into the well (parts.yaml: 0 where there are none); a
            # reach stated besides, other than 0 (or one that can't be read), leaves which is right unclear
            if s.get("ladder_encroachment") is not None and measures.get("area_well_ladder_encroachment") != 0:
                climb = LADDER_MEASURES + ("area_well_ladder_encroachment",)
                reach = measures.get("area_well_ladder_encroachment")
                raise stop("well_no_ladder_reaches", "ladder_encroachment",
                           got=Words(f"{reach:g} in" if reach is not None else "a value Gordium can't read"))
            measures["area_well_ladder_encroachment"] = 0.0
            stopped.pop("area_well_ladder_encroachment", None)
        measures.update(zip(LADDER_MEASURES, LADDER_WORDS[word]))
    except Stop as s_:
        for m in climb:
            measures.pop(m, None)
            stopped[m] = s_.reason
    return measures, stopped, confirm


def ground_shows(o: dict, reader, bottoms) -> tuple[str, float | str | None, float | None, float | None]:
    """What the ground given outside the opening (`ground_outside`) shows of its clear opening's bottom, as (what,
    ground, low, high): `bottoms`, every bottom it could have (low and high their least and greatest), else, with none,
    the bounds the description gives (`clear_bottom_between`: a door's, its threshold not drawn). ("none", None) no
    ground given; ("unread", why) a ground that can't be read; ("no_bottom", top) no bottom known; ("bounds_bad", why)
    bounds that can't be read; ("below", top) the ground stands more than 1/16 in above a bottom (bounds: above the
    highest); ("above", top) every bottom stands more than 1/16 in above it (bounds: the lowest does); ("near", top)
    within 1/16 in; ("between", top) between the bounds. `top`, the highest ground given, in inches: grade is the
    finished ground "adjoining the building" (RCNYS R202 GRADE), so the ground over any part of the opening's bottom
    puts it below grade there."""
    if o.get("ground_outside") is None:
        return "none", None, None, None
    try:
        top = max(grounds(o, reader))
    except Stop as s:
        return "unread", s.reason, None, None
    if not bottoms:
        try:
            bounds = bottom_bounds(o, reader)
        except Stop as s:
            return "bounds_bad", s.reason, None, None
        if bounds is None:
            return "no_bottom", top, None, None
        low, high = bounds
        if high < top - AGREE:
            return "below", top, low, high
        if low > top + AGREE:
            return "above", top, low, high
        return "between", top, low, high
    low, high = min(bottoms), max(bottoms)
    if any(b < top - AGREE for b in bottoms):
        return "below", top, low, high
    if all(b > top + AGREE for b in bottoms):
        return "above", top, low, high
    return "near", top, low, high


def bottom_bounds(o: dict, reader) -> tuple[float, float] | None:
    """The lowest and highest its clear opening's bottom could be (`clear_bottom_between`, in inches: a door's, its
    threshold not drawn), None where not given; Stop where they aren't two elevations, the lower first."""
    given = o.get("clear_bottom_between")
    if given is None:
        return None
    if not isinstance(given, list) or len(given) != 2:
        raise Stop("bottom_between_bad", got=given_as(given))
    low = reader.length(given[0], "the lowest its clear opening's bottom could be")
    high = reader.length(given[1], "the highest its clear opening's bottom could be")
    if high < low:
        raise Stop("bottom_between_bad", got=Words(f"{tidy(low):g} in over {tidy(high):g} in"))
    return low, high


def _below_grade(got, shown, top, o, reader, bottoms, stop, low=None, high=None) -> bool:
    """Whether the opening is below grade: the architect's statement, else what the ground given shows; a statement
    the ground contradicts by more than 1/16 in gives no value (Stop), naming both."""
    if got is None:
        if shown == "below":
            return True
        if shown == "above":
            return False
        if shown == "near":
            raise stop("well_ground_near", ground=Words(f"{tidy(top):g}"))
        if shown == "between":
            raise stop("well_ground_between", ground=Words(f"{tidy(top):g}"), low=Words(f"{tidy(low):g}"),
                       high=Words(f"{tidy(high):g}"))
        if shown == "bounds_bad":
            raise stop("well_bottom_unread", reason=Words(top))
        if shown == "no_bottom":
            raise stop("well_ground_no_bottom")
        if shown == "unread":
            raise stop("well_ground_unread", reason=Words(top))
        raise stop("well_not_stated")
    if not isinstance(got, bool):
        raise stop("well_stated_not_read", got=given_as(got))
    if got is False and (said := _drawn_below(o, reader, bottoms)):
        raise stop("well_below_disagree", shown=Words(said))
    if got is True and shown == "above":
        raise stop("well_above_disagree", ground=Words(f"{tidy(top):g}"), gap=Words(f"{tidy(low - top):g}"))
    return got


def _drawn_below(o: dict, reader, bottoms) -> str | None:
    """What the drawing shows of an opening below the ground, or None: a drawn area well, or a ground given outside it
    more than 1/16 in above a bottom its clear opening could have (ground_shows), or one that can't be compared."""
    if o.get("area_well") is not None:
        return "a drawn area well"
    shown, top, _, _ = ground_shows(o, reader, bottoms)
    if shown == "unread":
        return "a ground outside it Gordium can't read"
    if shown == "no_bottom":
        return "a ground outside it, while its clear opening's bottom isn't known"
    if shown == "bounds_bad":
        return "a ground outside it, while where its clear opening's bottom lies can't be read"
    return f"the ground outside it at {tidy(top):g} in, above its clear opening's bottom" if shown == "below" else None


def _area(reader, value, what: str) -> float:
    """An area in the description's units squared (square feet where `units` is ft), as square feet; never less than
    zero."""
    got = number(value, what)
    if got < 0:
        raise Stop("negative_area", what=what, value=tidy(got))
    per = reader.times / reader.per                  # inches in one of the description's units
    return got * per * per / 144
