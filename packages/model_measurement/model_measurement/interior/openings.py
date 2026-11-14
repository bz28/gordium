"""Emergency escape and rescue openings (R319): the net clear opening's area, height and width, the height of its
bottom above the floor, and whether it is a grade-floor opening; an area well's size where one is given.

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

from model_measurement.interior.read import choice, number, tidy
from model_measurement.interior.stops import Stop

SLIDING = ("double_hung", "single_hung", "horizontal_slider", "sliding_door")
HINGED = ("casement", "side_hinged_door")
MAKER_ONLY = ("awning", "hopper", "pivot", "tilt_turn", "other")
OPERATIONS = SLIDING + HINGED + ("fixed",) + MAKER_ONLY
AGREE = 1 / 16          # in: a maker's clear opening and the drawn one agree within this
GRADE_FLOOR = 44.0      # in: the definition of a grade-floor emergency escape and rescue opening
CLEAR = ("opening_net_clear_area", "opening_net_clear_height", "opening_net_clear_width")
NONE = "none"           # the opening doesn't open


def drawn_clear(o: dict, reader, operation: str):
    """The clear opening from the frame and its sashes: (left, right, bottom, top), or NONE."""
    frame = reader.rectangle(o.get("frame"), "the opening's frame")
    if operation == "fixed":
        return NONE
    left, right, bottom, top = frame
    if operation in HINGED:
        h = o.get("hinged")
        if not isinstance(h, dict):
            raise Stop("missing", what="the hinged sash (`hinged`: side, open_angle, sash_width, sash_thickness, "
                                     "hinge_offset)")
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
        raise Stop("missing", what="the maker's clear opening (`stated_clear`: width, height, bottom)")
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
            fits(maker, reader.rectangle(o.get("frame"), "the opening's frame"))
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
    """A maker's clear opening can't be bigger than the frame it is in, or reach outside it (1/16 in to spare)."""
    width, height = maker[1] - maker[0], maker[3] - maker[2]
    left, right, bottom, top = frame
    if width > right - left + AGREE or height > top - bottom + AGREE or maker[2] < bottom - AGREE \
            or maker[3] > top + AGREE:
        raise Stop("clear_outside_frame")


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


def measure_opening(o: dict, reader, floor_of) -> tuple[dict, dict, dict]:
    """(measures, more, not_measured) for one escape opening. floor_of(room id): its finished floor elevation (Stop
    if the room isn't known)."""
    measures, more, stopped = {}, {}, {}

    def stop_all(names, reason):
        for n in names:
            stopped[n] = reason

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
            measures["opening_sill_height"] = tidy(bottom - floor_of(o.get("room")))
        except Stop as s:
            stopped["opening_sill_height"] = s.reason
        try:
            measures["opening_at_grade"] = grade_floor(o, reader, bottoms)
        except Stop as s:
            stopped["opening_at_grade"] = s.reason
    if o.get("area_well") is not None:
        try:
            more.update(area_well(o, reader))
        except Stop as s:
            stop_all(("area_well_area", "area_well_width", "area_well_projection", "area_well_depth"), s.reason)
    return measures, more, stopped


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
