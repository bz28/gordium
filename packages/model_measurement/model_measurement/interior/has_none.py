"""What the interior description says the house has none of (`has_none`): "no ramps", "no sleeping lofts", each with
where that comes from. Plain code, no AI. Design: docs/decisions/2026-11-16_interior_absent_parts.md.

    claims, problems = read(description)   # {kind: {"source", "reading", "words", "parts", "openings", "stairs"}}

Absence is only ever stated, never inferred: a kind the description says nothing about stays not read (its rules
need review). A claim that can't be trusted (no source, an unknown kind, said twice, or contradicted by a list of
that kind in the same description) is a problem, and its kind stays not read: never "not applicable". A claim
marked `reading: true` rests on a reading of the law (an unfinished attic is not a habitable attic), not on the
drawings alone: it is taken, and the checker shows it as one to confirm (needs review), never as settled.
"""

import math

from shapely.errors import GEOSException
from shapely.geometry import Polygon
from shapely.ops import unary_union

from model_measurement.interior.stops import Stop, given_as, said

KEY = "has_none"
# every kind a description may say the house has none of:
#   words     the plural, as the panel says it ("the description says the house has no <words>")
#   list      the description's list of parts of that kind, which a claim must not contradict (None: there is none)
#   parts     the part kinds (rule_format/parts.yaml) that become an empty list: the rules' "none" row
#   openings  measures every escape opening then gets (each a pure consequence: no patio cover, so no opening into one)
#   stairs    the same for every stair measured (no sleeping loft, so no stair serves one)
KINDS = {
    "basement": {"words": "basements", "list": "basements", "parts": ("basement",)},
    "habitable_attic": {"words": "habitable attics", "list": "habitable_attics", "parts": ("habitable_attic",)},
    # R319.1's "the room a sleeping loft is open to" (loft_room) exists only where a sleeping loft does
    "sleeping_loft": {"words": "sleeping lofts", "list": "sleeping_lofts", "parts": ("sleeping_loft", "loft_room"),
                      "stairs": {"stair_serves_sleeping_loft": False}},
    "ramp": {"words": "ramps", "list": "ramps", "parts": ("ramp",)},
    "alternating_tread_device": {"words": "alternating tread devices", "list": "alternating_tread_devices",
                                 "parts": ("alternating_tread_device",)},
    "ships_ladder": {"words": "ship's ladders", "list": "ships_ladders", "parts": ("ships_ladder",)},
    "patio_cover": {"words": "patio covers", "list": "patio_covers", "openings": {"opening_into_patio_cover": False}},
    # about the openings, not the house: a house may well have a porch that is over none of them
    "deck_porch_or_cantilever_over_escape_opening": {
        "words": "decks, porches or cantilevers over an escape opening", "list": None,
        "openings": {"opening_under_projection": False}},
}
# the kinds the description already lists: an empty list says there are none
LISTED = {"sleeping_room": "rooms", "emergency_escape_opening": "openings", "stair": "stairs",
          "egress_door": "doors", "guard": "guards"}
# the kinds that are spaces: an enclosed space whose use isn't known (`unknown_spaces`) could be one of them
SPACES = ("basement", "habitable_attic", "sleeping_loft")
SAID = "the model says the house has no {words}"
ENTRY_KEYS = {"kind", "source", "reading"}


def words(kind: str) -> str:
    """"the model says the house has no ramps"."""
    return SAID.format(words=KINDS[kind]["words"])


def _value(v):
    """A plain finite number as a float, or None where it can't be read (text, true/false, NaN, infinite, too big)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        v = float(v)
    except OverflowError:
        return None
    return v if math.isfinite(v) else None


def _rooms(description: dict) -> list[dict]:
    return [r for r in description.get("rooms") or [] if isinstance(r, dict)]


def _name(part: dict):
    return part.get("name") or part.get("id")


def below_ground(description: dict) -> str | None:
    """What in the description shows a space below the ground, or may, which a "no basements" claim can't stand
    beside (the first found), or None. Only what it states: an opening with an area well (the format's "for an
    opening below the ground"), or a room's floor or a stair's foot below the highest ground given outside any opening
    (the ground at the room's own openings, or anywhere else: a walk-out below the uphill ground is one to confirm
    too); a ground, floor or foot given that can't be read could be either, so it refuses too. It never says there is a
    basement (grade plane is an average, measured elsewhere): it only refuses the claim, so the rules need review.
    Where no ground is given at all, nothing is compared."""
    grounds = []
    for o in description.get("openings") or []:
        if not isinstance(o, dict):
            continue
        if o.get("area_well") is not None:
            return f"opening {_name(o)} has an area well"
        if "stated_well" in o:
            # what the architect states of the opening (a host's marks, openings.stated_well): below grade, or a well
            # given at all, shows a space below the ground; a statement that can't be read could say either
            s = o["stated_well"]
            if not isinstance(s, dict) or s.get("below_grade") not in (None, True, False):
                return f"what opening {_name(o)} states of its area well can't be read"
            if s.get("below_grade") is True:
                return f"opening {_name(o)} is stated to be below the adjacent grade"
            if any(s.get(k) is not None for k in ("area", "width", "projection", "depth")):
                return f"opening {_name(o)} is stated to have an area well"
        ground = o.get("ground_outside")
        if ground is None:
            continue
        got = [_value(g) for g in (ground if isinstance(ground, list) else [ground])]
        if not got or None in got:
            return f"the ground outside opening {_name(o)} can't be read"
        grounds += got
    if not grounds:
        return None
    top = max(grounds)
    for what, key, parts in (("the floor of room", "floor_elevation", _rooms(description)),
                             ("the foot of stair", "bottom_elevation",
                              [s for s in description.get("stairs") or [] if isinstance(s, dict)])):
        for part in parts:
            if part.get(key) is None:        # not drawn (a room that isn't a sleeping room needn't be): not compared
                continue
            level = _value(part.get(key))
            if level is None:
                return f"{what} {_name(part)} can't be read, to compare with the ground outside the openings"
            if level < top:
                return f"{what} {_name(part)} is below the ground outside an opening"
    return None


def _top(room: dict, floor: float):
    """The highest the room's finished ceiling reaches, or None where any of it can't be read."""
    height = room.get("ceiling_height")
    if height is not None:
        h = _value(height)
        return None if h is None else floor + h
    pieces = room.get("ceilings")
    if not isinstance(pieces, list) or not pieces:
        return None
    read = []
    for piece in pieces:
        if not isinstance(piece, list) or not piece:
            return None
        pts = []
        for p in piece:
            if not isinstance(p, (list, tuple)) or len(p) != 3 or None in (xyz := [_value(v) for v in p]):
                return None
            pts.append(xyz)
        read.append(pts)
    # the room's ceiling is the lowest piece over each place: a piece wholly over lower ones isn't its ceiling anywhere
    # (a host's reader sends every underside over the room, the floor above's rooms' ceilings over its own: Orangetown
    # read from Revit, whose main floor's own ceiling is under the second floor's). Only such a piece is left out; a
    # piece that can't be drawn in plan always counts (the highest point of what is left counts, as before)
    shapes = []
    for pts in read:
        try:
            plan = Polygon([(x, y) for x, y, _ in pts]) if len(pts) >= 3 else None
            plan = plan if plan is not None and plan.is_valid and plan.area > 0 else None
        except (GEOSException, ValueError):
            plan = None
        shapes.append((plan, min(z for *_, z in pts), max(z for *_, z in pts)))
    tops = []
    unions = {}             # the pieces under a height, unioned once: every piece starting there has the same ones
    for i, (plan, low, high) in enumerate(shapes):
        # strictly lower only: a piece at the same height hides nothing (and many coincident pieces unioned together
        # lost coverage in GEOS, Orangetown's Revit recording: a hidden piece read as uncovered). The pieces under
        # depend on `low` alone (a piece is never under itself: it doesn't end below where it starts), so one union
        # of exactly the same pieces, in the same order, serves every piece starting at that height
        hidden = False
        if plan is not None:
            if low not in unions:
                under = [q for q, _, qh in shapes if q is not None and qh < low]
                try:
                    unions[low] = unary_union(under) if under else None
                except GEOSException:
                    unions[low] = GEOSException
            below = unions[low]
            if below is not None and below is not GEOSException:
                try:
                    hidden = plan.difference(below).area <= plan.area * 1e-9
                except GEOSException:
                    hidden = False
        if not hidden:
            tops.append(high)
    return max(tops)


def _plan(room: dict):
    """The room's floor outline in plan, or None where it can't be read."""
    points = room.get("floor")
    if not isinstance(points, list) or len(points) < 3:
        return None
    xy = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 2 or None in (got := [_value(v) for v in p]):
            return None
        xy.append(got)
    try:
        poly = Polygon(xy)
    except (TypeError, ValueError, GEOSException):
        return None
    return poly if poly.is_valid and poly.area > 0 else None


def room_within(description: dict) -> str | None:
    """A room the description draws within another room's height (its floor over the other's floor in plan, above
    it and below that room's ceiling: a floor level within a room, as a loft is), or one whose floor or ceiling can't
    be read to tell, which a "no sleeping lofts" claim can't stand beside (the first found), or None. A room upstairs
    is at or above the ceiling of the room below, so it never is. A partial check: a loft over a low room, open to a
    taller room beside it, is over no room it is within, and a room drawn with no floor at all isn't compared. Only
    refuses the claim: it never says the room is a loft."""
    # a room drawn with neither (the format asks a floor only of a sleeping room) isn't drawn to compare
    rooms = [r for r in _rooms(description) if r.get("floor") is not None or r.get("floor_elevation") is not None]
    if len(rooms) < 2:
        return None
    read = []
    for r in rooms:
        plan, floor = _plan(r), _value(r.get("floor_elevation"))
        if plan is None or floor is None:
            return f"room {_name(r)}'s floor can't be read, to tell whether it is within another room"
        read.append((r, plan, floor))
    tops = {}                   # each room's ceiling worked out once, however many rooms stand over it
    for r, plan, floor in read:
        for k, (other, under, below) in enumerate(read):
            if other is r or not below < floor or plan.intersection(under).area <= 0:
                continue
            if k not in tops:
                tops[k] = _top(other, below)
            top = tops[k]
            if top is None:
                return f"room {_name(other)}'s ceiling can't be read, to tell whether room {_name(r)} is within it"
            if floor < top:
                return f"room {_name(r)}'s floor is over room {_name(other)}'s and below its ceiling"
    return None


def read(description: dict) -> tuple[dict, list[str]]:
    """({kind: {"source", "reading", "words", "parts", "openings", "stairs"}} for every claim that can be trusted, [the problem with each
    one that can't]). No `has_none` is no claim."""
    given = description.get(KEY)
    if given is None:
        return {}, []
    if not isinstance(given, list):
        return {}, [Stop("has_none_not_a_list").reason]
    problems, seen = [], {}
    for n, entry in enumerate(given, 1):
        kind = entry.get("kind") if isinstance(entry, dict) else None
        if not isinstance(entry, dict) or not isinstance(kind, str):
            problems.append(Stop("has_none_entry", n=n).reason)
            continue
        if kind == "sleeping_room":     # `rooms: []` is a house not drawn yet, never "no sleeping rooms"
            problems.append(Stop("has_none_sleeping_room").reason)
            continue
        if kind in LISTED:
            problems.append(Stop("has_none_listed", kind=kind.replace("_", " ") + "s",
                                 key=LISTED[kind].replace("_", " ")).reason)
            continue
        if kind not in KINDS:
            problems.append(Stop("has_none_kind", kind=kind, kinds=", ".join(k.replace("_", " ") for k in KINDS)).reason)
            continue
        if extra := sorted(set(entry) - ENTRY_KEYS, key=str):    # a mistyped `reading` must never read as settled
            problems.append(Stop("has_none_keys", words=KINDS[kind]["words"], keys=", ".join(str(said(k)) for k in extra)).reason)
            seen.setdefault(kind, []).append(None)
            continue
        source, reading = entry.get("source"), entry.get("reading", False)
        if not isinstance(source, str) or not source.strip():
            problems.append(Stop("has_none_no_source", words=KINDS[kind]["words"]).reason)
            seen.setdefault(kind, []).append(None)          # still counted: a kind said twice is refused
            continue
        if type(reading) is not bool:
            problems.append(Stop("has_none_reading", words=KINDS[kind]["words"], got=given_as(reading)).reason)
            seen.setdefault(kind, []).append(None)
            continue
        seen.setdefault(kind, []).append((" ".join(source.split()), reading))
    claims = {}
    for kind, sources in seen.items():
        if len(sources) > 1:
            problems.append(Stop("has_none_twice", words=KINDS[kind]["words"], count=len(sources)).reason)
            continue
        if sources[0] is None:
            continue
        listed = KINDS[kind]["list"]
        if listed is not None and listed in description and description[listed] != []:
            problems.append(Stop("has_none_contradicted", words=KINDS[kind]["words"], key=listed.replace("_", " ")).reason)
            continue
        spaces = description.get("unknown_spaces")
        if kind in SPACES and spaces is not None and spaces != []:
            # a space whose use isn't known may be the basement, attic or loft said to be none
            problems.append(Stop("has_none_unknown_space", words=KINDS[kind]["words"],
                                 count=len(spaces) if isinstance(spaces, list) else "some").reason)
            continue
        if kind == "basement" and (below := below_ground(description)):
            problems.append(Stop("has_none_below_ground", what=below).reason)
            continue
        if kind == "sleeping_loft" and (inside := room_within(description)):
            problems.append(Stop("has_none_room_within", what=inside).reason)
            continue
        k = KINDS[kind]
        claims[kind] = {"source": sources[0][0], "reading": sources[0][1], "words": words(kind),
                        "parts": list(k.get("parts", ())), "openings": dict(k.get("openings", {})),
                        "stairs": dict(k.get("stairs", {}))}
    return claims, problems


__all__ = ["KEY", "KINDS", "LISTED", "read", "words"]
