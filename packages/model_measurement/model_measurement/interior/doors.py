"""The exit door (R318.2): its clear width and clear height.

R318.2: the clear width is "measured between the face of the door and the stop, with the door open 90 degrees";
the clear height "from the top of the threshold to the bottom of the stop". Drawn in the door's own plan and
elevation: u along the wall, n across it (toward the side the door swings into), z up. The leaf, drawn closed,
is turned 90 degrees about its hinge pin; its face toward the latch side is then the one the width is measured
from (with a butt hinge on the leaf's corner, the pin's u plus the leaf's thickness). Definitions:
docs/interior/interior_measurements.md.
"""

from model_measurement.interior.read import choice, tidy
from model_measurement.interior.stops import Stop

OPERATIONS = ("side_hinged", "sliding", "folding", "pocket", "other")
PIN_OFF = 1 / 16        # in: how far the hinge pin may stand back from the leaf's hinge corner (drawing noise)


def clear_width(d: dict, reader) -> float:
    operation = choice(d.get("operation"), OPERATIONS, "the door's operation")
    if operation != "side_hinged":
        raise Stop("not_side_hinged", operation=operation.replace("_", " "))
    side = choice(d.get("hinge_side"), ("left", "right"), "the door's hinge side")
    stops = d.get("stops")
    if not isinstance(stops, dict):
        raise Stop("missing", what="the door's stops (`stops`: hinge, latch)")
    hinge = reader.length(stops.get("hinge"), "the hinge-side stop")
    latch = reader.length(stops.get("latch"), "the latch-side stop")
    if (latch <= hinge) if side == "left" else (latch >= hinge):
        raise Stop("stops_wrong_way")
    pu, pn = reader.point(d.get("hinge_pin"), 2, "the door's hinge pin (u, n)")
    corners = reader.points(d.get("leaf_closed"), 2, "the door leaf's closed corners", 2)
    if len(corners) != 2:
        raise Stop("not_a_polyline", what="the door leaf's closed corners (two opposite corners)")
    near = min(n for _, n in corners)              # the leaf's face away from the side it swings into
    # the leaf turns about its pin, so the pin must hang it: at the leaf's hinge-side corner on the face it swings
    # toward (within 1/16 in, drawing noise), or beyond it, past the face or toward the latch side, which only
    # narrows the width. A pin drawn behind the leaf, or back toward the hinge jamb, would turn a leaf it doesn't
    # hold out of the opening
    edge = min(u for u, _ in corners) if side == "left" else max(u for u, _ in corners)
    far = max(n for _, n in corners)
    back = max(0.0, far - pn) + max(0.0, edge - pu if side == "left" else pu - edge)    # both widen: together
    if back > PIN_OFF + 1e-9:
        raise Stop("pin_off_leaf", off=tidy(back))
    # open 90 degrees about the pin, into +n: a point's u becomes pu - (n - pn) (hinge left) or pu + (n - pn)
    if side == "left":
        face = pu + (pn - near)
        width = latch - max(face, hinge)
    else:
        face = pu - (pn - near)
        width = min(face, hinge) - latch
    if width <= 0:
        raise Stop("not_positive", what="the door's clear width", value=tidy(width))
    return width


def clear_height(d: dict, reader) -> float:
    threshold = reader.length(d.get("threshold_top"), "the top of the threshold")
    head = reader.length(d.get("head_stop_bottom"), "the bottom of the head stop")
    if head - threshold <= 0:
        raise Stop("not_positive", what="the door's clear height", value=tidy(head - threshold))
    return head - threshold


def measure_door(d: dict, reader) -> tuple[dict, dict, dict]:
    measures, stopped = {}, {}
    for name, fn in (("door_clear_width", clear_width), ("door_clear_height", clear_height)):
        try:
            measures[name] = tidy(fn(d, reader))
        except Stop as s:
            stopped[name] = s.reason
    return measures, {}, stopped
