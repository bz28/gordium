"""The exit door (R318.2): its clear width and clear height, and whether it is side-hinged.

Each clear size is the drawn one, or the maker's stated one (`stated_clear`), or, given both, the less favourable
(the smaller) of the two: never more than either (decision 2, docs/revit/revit_interior_reading_design.md section
8). Each says which it came from, and why, in the part's `from`. A door drawn but not measurable from its drawing
gets no value even with a maker's size (that size alone could be more than the door as drawn), and a maker's size
given but malformed gives neither measure a value (it is never dropped, which could leave the larger drawn one).

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
# whether a door is side-hinged, read straight from its operation (R318.2: "a side-hinged door"); `other` doesn't say
SIDE_HINGED = {"side_hinged": True, "sliding": False, "folding": False, "pocket": False}
PIN_OFF = 1 / 16        # in: how far the hinge pin may stand back from the leaf's hinge corner (drawing noise)
# in: how far a closed leaf's hinge edge may stand behind the hinge-side stop's face: the stop laps the leaf by its
# own projection off the jamb, 1/2 to 3/4 in for a door stop
STOP_LAP = 0.75
STOP_LAP_WORDS = "3/4"


# what draws each clear size: given any of these, the size is measured from the drawing (and must be measurable)
DRAWN = {"width": ("stops", "hinge_pin", "leaf_closed"), "height": ("threshold_top", "head_stop_bottom")}
STATED_KEYS = ("width", "height", "source")


def _hinged_only(d: dict) -> None:
    """R318.2's clear width is measured with a side-hinged door open 90 degrees: no other door has one, drawn or
    stated."""
    operation = choice(d.get("operation"), OPERATIONS, "the door's operation")
    if operation != "side_hinged":
        raise Stop("not_side_hinged", operation=operation.replace("_", " "))


def clear_width(d: dict, reader) -> float:
    _hinged_only(d)
    side = choice(d.get("hinge_side"), ("left", "right"), "the door's hinge side")
    stops = d.get("stops")
    if not isinstance(stops, dict):
        raise Stop("missing", what="the door's stops (hinge side and latch side)")
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
    if far - near <= 0:                            # a leaf drawn flat: its thickness, which narrows the width, lost
        raise Stop("leaf_no_thickness")
    # the closed leaf closes this opening: it reaches the latch-side stop (within 1/16 in). A leaf drawn elsewhere
    # with its pin (in the wall, a wrong origin) would turn open clear of the opening and read its full width
    reach = max(u for u, _ in corners) if side == "left" else min(u for u, _ in corners)
    short = (latch - reach) if side == "left" else (reach - latch)
    if short > PIN_OFF + 1e-9:
        raise Stop("leaf_not_closing", short=tidy(short))
    # and at its hinge side it stands no farther behind the hinge-side stop than the stop laps it (STOP_LAP): a leaf
    # drawn running farther back (into the wall, pin and all) would turn open behind the stop and read the
    # stop-to-stop width. A swing-clear hinge, which does that on purpose, isn't measured yet
    behind = (hinge - edge) if side == "left" else (edge - hinge)
    if behind > STOP_LAP + 1e-9:
        raise Stop("leaf_behind_hinge_stop", back=tidy(behind), most=STOP_LAP_WORDS)
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


def side_hinged(d: dict) -> bool:
    """True for a side-hinged door, False for a sliding, folding or pocket one; `other` gives no value."""
    operation = choice(d.get("operation"), OPERATIONS, "the door's operation")
    if operation not in SIDE_HINGED:
        raise Stop("operation_undecided", what="door", operation=operation, question="whether it is side-hinged")
    return SIDE_HINGED[operation]


def stated_clear(d: dict, reader):
    """The maker's stated clear opening, {width, height, source} (inches), or None when not given. Given but
    malformed (not a mapping, a key it doesn't know, no source, a size missing, not a length, or not more than
    zero): Stop, never a default."""
    s = d.get("stated_clear")
    if s is None:
        return None
    if not isinstance(s, dict):
        raise Stop("door_stated_shape")
    unknown = sorted(str(k) for k in s if k not in STATED_KEYS)
    if unknown:
        raise Stop("door_stated_keys", keys=", ".join(unknown))
    source = s.get("source")
    if not isinstance(source, str) or not source.strip():
        raise Stop("door_stated_no_source")
    got = {"source": source.strip()}
    for key in ("width", "height"):
        what = f"the maker's stated clear {key}"
        got[key] = reader.size(s.get(key), what)
        if got[key] <= 0:
            raise Stop("not_positive", what=what, value=tidy(got[key]))
    return got


def _clear(key: str, fn, d: dict, reader, maker) -> tuple[float, dict]:
    """(the clear width or height, where it came from): drawn, stated, or the less favourable of both."""
    if isinstance(maker, Stop):
        raise maker
    if key == "width":
        _hinged_only(d)
    if maker is None:
        return tidy(fn(d, reader)), {"used": "drawn", "why": "drawn; no maker's clear opening given"}
    stated = tidy(maker[key])
    told = {"stated": stated, "source": maker["source"]}
    if all(d.get(k) is None for k in DRAWN[key]):
        return stated, dict(used="stated", **told, why=f"the maker's stated clear {key}; none drawn")
    try:
        drawn = tidy(fn(d, reader))
    except Stop as s:
        raise Stop("door_drawn_unread", what=key, reason=s.reason) from None
    told["drawn"] = drawn
    if stated < drawn:
        return stated, dict(used="stated", **told, why=f"the maker's stated clear {key} is smaller than the drawn "
                                                         "one: the less favourable counts")
    if drawn < stated:
        return drawn, dict(used="drawn", **told, why=f"the drawn clear {key} is smaller than the maker's stated "
                                                      "one: the less favourable counts")
    return drawn, dict(used="both", **told, why=f"the drawn and the maker's stated clear {key} are the same")


def measure_door(d: dict, reader) -> tuple[dict, dict, dict, dict]:
    """(measures, more, not_measured, from): `from` says, for each clear size measured, which it came from."""
    measures, stopped, came = {}, {}, {}
    try:
        measures["door_side_hinged"] = side_hinged(d)
    except Stop as s:
        stopped["door_side_hinged"] = s.reason
    try:
        maker = stated_clear(d, reader)
    except Stop as s:
        maker = s
    for name, key, fn in (("door_clear_width", "width", clear_width), ("door_clear_height", "height", clear_height)):
        try:
            measures[name], came[name] = _clear(key, fn, d, reader, maker)
        except Stop as s:
            stopped[name] = s.reason
    return measures, {}, stopped, came
