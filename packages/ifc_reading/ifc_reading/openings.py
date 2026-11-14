"""Windows and doors: the openings (anything that could be a bedroom's escape opening) and the doors (the exit door)
of the interior description. Every value comes from the model as stated, or is left out with its reason.

An opening's frame (its clear inside opening, in its own elevation: u along the wall from the window's origin, z
the absolute elevation) is read only for a rectangular, upright, single-panel window, from IFC4's parametric
window: OverallWidth and OverallHeight are "a bounding box, enclosing the window opening", placed at the window's
origin; the lining (IfcWindowLiningProperties.LiningThickness) stands inside it on every side. So the frame is the
opening less the lining's thickness all round. The README's "Openings" section says why, and what is never read.
"""

import numpy as np

from ifc_reading.model import EPS, FLAT, is_number, tidy
from ifc_reading.rooms import GORDIUM_SET

# IfcWindowPanelOperationEnum -> the description's operation (a single-panel window only)
WINDOW_OPERATION = {
    "SIDEHUNGRIGHTHAND": "casement", "SIDEHUNGLEFTHAND": "casement",
    "TILTANDTURNRIGHTHAND": "tilt_turn", "TILTANDTURNLEFTHAND": "tilt_turn",
    "TOPHUNG": "awning", "BOTTOMHUNG": "hopper",
    "PIVOTHORIZONTAL": "pivot", "PIVOTVERTICAL": "pivot",
    "SLIDINGHORIZONTAL": "horizontal_slider",
    "FIXEDCASEMENT": "fixed",
    "REMOVABLECASEMENT": "other", "OTHEROPERATION": "other",
    # SLIDINGVERTICAL: single- or double-hung, which IFC doesn't say (and their open sashes differ); NOTDEFINED
}
# IfcDoorTypeOperationEnum (IfcDoorStyleOperationEnum in IFC2x3) -> (the doors list's operation, the openings')
DOOR_OPERATION = {
    "SINGLE_SWING_LEFT": ("side_hinged", "side_hinged_door"), "SINGLE_SWING_RIGHT": ("side_hinged", "side_hinged_door"),
    "SLIDING_TO_LEFT": ("sliding", "sliding_door"), "SLIDING_TO_RIGHT": ("sliding", "sliding_door"),
    "DOUBLE_DOOR_SLIDING": ("sliding", "sliding_door"),
    "FOLDING_TO_LEFT": ("folding", None), "FOLDING_TO_RIGHT": ("folding", None),
    "DOUBLE_DOOR_FOLDING": ("folding", None),
}
SQUARE = 0.999      # a silhouette filling at least this much of its bounding box is a rectangle
NOT_READ = {
    "hinged": "how far a hinged sash opens, and where its hinge stands, aren't in IFC",
    "sashes": "where the sashes stand fully open isn't in IFC",
    "stated_clear": "the maker's net clear opening isn't in IFC",
    "ground_outside": "the finished ground outside isn't read from IFC",
}
AS_OPENING = "/opening"     # a door's id as an opening (its GlobalId is its id in the doors list)


def rooms_bounded(element) -> list:
    spaces = []
    for rel in getattr(element, "ProvidesBoundaries", []) or []:
        s = rel.RelatingSpace
        if s is not None and s.is_a("IfcSpace") and s not in spaces:
            spaces.append(s)
    return spaces


def _flag(model, element, sets_names):
    """The first flag the model states, as (true/false, "Set.Name", None); (None, None, None) if none; a flag that
    is there but isn't true/false (text "TRUE", "Yes", UNKNOWN) as (None, "Set.Name", why): never read as unmarked."""
    for s, name in sets_names:
        value, where = model.prop(element, [s], name)
        if isinstance(value, bool):
            return value, where, None
        if value is not None:
            return None, where, f"{where} is {value!r}, not true or false"
    return None, None, None


def _escape_from(escape, where, bad) -> str:
    """Where `escape` came from. Not marked as true is false: only an opening the architect marks is checked, and a
    sleeping room with none marked fails (a mark that can't be read included, never a pass)."""
    if bad:
        return f"{bad}: read as not marked (only an opening marked true is checked as an escape opening)"
    if where:
        return f"{where} is {str(escape).lower()}"
    return "not marked in the model (only an opening the architect marks is checked as an escape opening)"


def _room(element, missing):
    spaces = rooms_bounded(element)
    if len(spaces) == 1:
        return spaces[0]
    missing["room"] = ("no space boundary (IfcRelSpaceBoundary) names the room it opens from" if not spaces else
                       f"it bounds {len(spaces)} rooms ({', '.join(s.LongName or s.Name or s.GlobalId for s in spaces)})"
                       ": which one it opens from is unclear")
    return None


def _size(model, element, info):
    w, h = element.OverallWidth, element.OverallHeight
    if not (is_number(w) and is_number(h) and w > 0 and h > 0):
        return None
    w, h = float(w) * model.metres, float(h) * model.metres
    info["overall_width"], info["overall_height"] = tidy(w), tidy(h)
    return w, h


def _upright(m) -> bool:
    return bool(np.allclose(m[:3, 2], (0, 0, 1), atol=EPS) and abs(m[2, 0]) < EPS)


def read_window(model, window, floors: dict) -> dict:
    """One IfcWindow as an opening. floors: {space id: its finished floor elevation, where known}."""
    o = {"id": window.GlobalId, "name": window.Name or window.GlobalId}
    missing, info = {}, {"entity": window.is_a(), "step_id": window.id(), "global_id": window.GlobalId}
    room = _room(window, missing)
    if room is not None:
        o["room"] = room.GlobalId
    escape, where, bad = _flag(model, window, [(GORDIUM_SET, "EscapeOpening"), ("Pset_WindowCommon", "FireExit")])
    o["escape"] = bool(escape)
    info["escape_from"] = _escape_from(escape, where, bad)

    m = model.placement(window)
    size = _size(model, window, info)
    if _upright(m):
        info["opening_bottom"] = tidy(m[2, 3])
        if room is not None and floors.get(room.GlobalId) is not None:
            info["opening_bottom_above_floor"] = tidy(m[2, 3] - floors[room.GlobalId])

    panels = model.predefined(window, "IfcWindowPanelProperties")
    kinds = [p.OperationType for p in panels]
    info["panels"] = kinds
    t = model.type_of(window)
    partitioning = getattr(t, "PartitioningType", None) if t is not None else getattr(window, "PartitioningType", None)
    if partitioning:
        info["partitioning"] = partitioning
    single = len(panels) == 1 and partitioning in (None, "SINGLE_PANEL", "NOTDEFINED")
    if not single:
        why = (f"the window has {len(panels)} panels ({', '.join(kinds)})" if len(panels) > 1 else
               f"the window is partitioned {partitioning}" if partitioning not in (None, "SINGLE_PANEL", "NOTDEFINED")
               else "the window's panel (IfcWindowPanelProperties) isn't given")
        if len(panels) > 1 or partitioning not in (None, "SINGLE_PANEL", "NOTDEFINED"):
            why += ": a window of more than one panel isn't measured yet"
        missing["operation"] = missing["frame"] = why
    else:
        operation = WINDOW_OPERATION.get(kinds[0])
        if operation is None:
            missing["operation"] = (f"the panel's operation is {kinds[0]}" + (": single- or double-hung, which IFC "
                                    "doesn't say" if kinds[0] == "SLIDINGVERTICAL" else ""))
        else:
            o["operation"] = operation
        frame, why = _frame(model, window, m, size)
        if frame is None:
            missing["frame"] = why
        else:
            o["frame"] = frame
            info["frame_from"] = why
    for k, why in NOT_READ.items():
        missing.setdefault(k, why)
    o["not_given"] = missing
    o["ifc"] = info
    return o


def _frame(model, window, m, size):
    if size is None:
        return None, "the window's OverallWidth and OverallHeight aren't given"
    if not _upright(m):
        return None, "the window isn't upright in a wall (a roof window, or turned): not read yet"
    linings = model.predefined(window, "IfcWindowLiningProperties")
    if len(linings) != 1 or not is_number(linings[0].LiningThickness) or linings[0].LiningThickness < 0:
        return None, "the window's lining thickness (IfcWindowLiningProperties.LiningThickness) isn't given"
    lining = linings[0]
    for divider, offset in (("MullionThickness", "FirstMullionOffset"), ("TransomThickness", "FirstTransomOffset")):
        if getattr(lining, offset, None) is not None:
            return None, f"the window's lining has a divider ({offset}): a window of more than one panel isn't measured yet"
    thick = float(lining.LiningThickness) * model.metres
    w, h = size
    if 2 * thick >= min(w, h):
        return None, f"the lining ({tidy(thick)} m) leaves no opening in the {tidy(w)} x {tidy(h)} m window"
    shape, why = _rectangle(model, window, m, w, h)
    if shape is None:
        return None, why
    z0 = float(m[2, 3])
    frame = {"left": tidy(thick), "right": tidy(w - thick), "bottom": tidy(z0 + thick), "top": tidy(z0 + h - thick)}
    return frame, (f"OverallWidth {tidy(w)} m x OverallHeight {tidy(h)} m at the window's origin ({tidy(z0)} m), "
                   f"less LiningThickness {tidy(thick)} m all round; {why}")


def _silhouette(tris, m):
    """The triangles' outline seen straight on in the element's own elevation (x along it, z up), as a shape."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    local = (tris - m[:3, 3]) @ m[:3, :3]                      # rotate into the element's axes
    flat = [Polygon(t[:, [0, 2]]) for t in local]
    return unary_union([p for p in flat if p.is_valid and p.area > 1e-12]).buffer(0)


def _rectangle(model, window, m, w, h):
    """Whether the window (its body, and the opening it fills where there is one) is the W x H rectangle at its
    origin: a round or arched window's bounding box isn't its opening."""
    tris = model.triangles(window)
    if tris is None:
        return None, "the window has no body shape, so whether it is rectangular can't be told"
    body = _silhouette(tris, m)
    x0, z0, x1, z1 = body.bounds
    if body.area < SQUARE * (x1 - x0) * (z1 - z0):
        return None, (f"the window isn't rectangular (its outline fills {tidy(body.area / ((x1 - x0) * (z1 - z0)))} of "
                      "its bounding box): its clear opening isn't read yet")
    if x0 > FLAT or z0 > FLAT or x1 < w - FLAT or z1 < h - FLAT:
        return None, (f"the window's body ({tidy(x1 - x0)} x {tidy(z1 - z0)} m) doesn't cover its stated "
                      f"{tidy(w)} x {tidy(h)} m opening at its origin")
    fills = getattr(window, "FillsVoids", None) or []
    if not fills:
        return True, "a rectangular body covering it (no opening element to check against)"
    void = model.triangles(fills[0].RelatingOpeningElement)
    if void is None:
        return True, "a rectangular body covering it (its opening element has no shape)"
    cut = _silhouette(void, m)
    a0, b0, a1, b1 = cut.bounds
    if cut.area < SQUARE * (a1 - a0) * (b1 - b0):
        return None, "the opening the window fills isn't rectangular: its clear opening isn't read yet"
    if max(abs(a0), abs(b0), abs(a1 - w), abs(b1 - h)) > FLAT:
        return None, (f"the opening the window fills ({tidy(a0)} to {tidy(a1)} m along, {tidy(b0)} to {tidy(b1)} m "
                      f"up) isn't its stated {tidy(w)} x {tidy(h)} m at its origin: which is right is unclear")
    return True, "a rectangular body, and the opening it fills matches"


def door_operation(model, door):
    op = getattr(door, "OperationType", None)
    if op in (None, "NOTDEFINED"):
        t = model.type_of(door)
        op = getattr(t, "OperationType", None) if t is not None else None
    return op


def read_door_opening(model, door, floors: dict):
    """An exterior IfcDoor (it bounds one room) or one marked as an escape opening, as an opening; else None."""
    escape, where, bad = _flag(model, door, [(GORDIUM_SET, "EscapeOpening")])
    if len(rooms_bounded(door)) != 1 and escape is not True:
        return None
    # the same door is in the doors list under its GlobalId, and every id in a description is unique
    o = {"id": f"{door.GlobalId}{AS_OPENING}", "name": door.Name or door.GlobalId}
    missing, info = {}, {"entity": door.is_a(), "step_id": door.id(), "global_id": door.GlobalId}
    room = _room(door, missing)
    if room is not None:
        o["room"] = room.GlobalId
    o["escape"] = bool(escape)
    info["escape_from"] = _escape_from(escape, where, bad)
    op = door_operation(model, door)
    info["operation_type"] = op
    mapped = DOOR_OPERATION.get(op, (None, None))[1]
    if mapped:
        o["operation"] = mapped
    else:
        missing["operation"] = f"the door's operation is {op}: not read as an escape opening's yet"
    _size(model, door, info)
    m = model.placement(door)
    if _upright(m):
        info["opening_bottom"] = tidy(m[2, 3])
    missing["frame"] = "a door's clear opening (its frame and stops) isn't read from IFC yet"
    for k, why in NOT_READ.items():
        missing.setdefault(k, why)
    o["not_given"] = missing
    o["ifc"] = info
    return o


def read_door(model, door) -> dict:
    """One IfcDoor for the doors list (the exit door)."""
    d = {"id": door.GlobalId, "name": door.Name or door.GlobalId}
    missing, info = {}, {"entity": door.is_a(), "step_id": door.id(), "global_id": door.GlobalId}
    exit_, where, bad = _flag(model, door, [(GORDIUM_SET, "ExitDoor"), ("Pset_DoorCommon", "FireExit")])
    if exit_ is None:
        missing["exit"] = bad or ("the model doesn't say whether it is the required exit door (Gordium_Egress.ExitDoor or "
                           "Pset_DoorCommon.FireExit)")
    else:
        d["exit"] = exit_
        info["exit_from"] = f"{where} is {str(exit_).lower()}"
    op = door_operation(model, door)
    info["operation_type"] = op
    mapped = DOOR_OPERATION.get(op, (None, None))[0]
    if mapped:
        d["operation"] = mapped
    else:
        missing["operation"] = f"the door's operation is {op}: not read yet"
    _size(model, door, info)
    m = model.placement(door)
    if _upright(m):
        info["opening_bottom"] = tidy(m[2, 3])
    reason = "where the door's stops, hinge pin and closed leaf stand isn't in IFC"
    for k in ("hinge_side", "stops", "hinge_pin", "leaf_closed"):
        missing[k] = reason
    missing["threshold_top"] = "the threshold's top isn't read from IFC"
    missing["head_stop_bottom"] = "the head stop's bottom isn't in IFC (the lining isn't the stop)"
    d["not_given"] = missing
    d["ifc"] = info
    return d
