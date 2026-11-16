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

from model_measurement.interior.stops import Stop

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
SAID = "the description says the house has no {words}"
ENTRY_KEYS = {"kind", "source", "reading"}


def words(kind: str) -> str:
    """"the description says the house has no ramps"."""
    return SAID.format(words=KINDS[kind]["words"])


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _rooms(description: dict) -> list[dict]:
    return [r for r in description.get("rooms") or [] if isinstance(r, dict)]


def _name(part: dict):
    return part.get("name") or part.get("id")


def below_ground(description: dict) -> str | None:
    """What in the description shows a space below the ground, which a "no basements" claim can't stand beside (the
    first found), or None. Only what it states: an opening with an area well (the format's "for an opening below the
    ground"), or a room's floor or a stair's foot below the highest ground given outside any opening (the ground at
    the room's own openings, or anywhere else: a walk-out below the uphill ground is one to confirm too). It never
    says there is a basement (grade plane is an average, measured elsewhere): it only refuses the claim, so the
    rules need review. Where no ground is given at all, nothing is compared."""
    grounds = []
    for o in description.get("openings") or []:
        if not isinstance(o, dict):
            continue
        if o.get("area_well") is not None:
            return f"opening {_name(o)} has an area well"
        ground = o.get("ground_outside")
        grounds += [g for g in (ground if isinstance(ground, list) else [ground]) if _number(g)]
    if not grounds:
        return None
    top = max(grounds)
    for r in _rooms(description):
        if _number(r.get("floor_elevation")) and r["floor_elevation"] < top:
            return f"the floor of room {_name(r)} is below the ground outside an opening"
    for s in description.get("stairs") or []:
        if isinstance(s, dict) and _number(s.get("bottom_elevation")) and s["bottom_elevation"] < top:
            return f"the foot of stair {_name(s)} is below the ground outside an opening"
    return None


def _top(room: dict):
    """The highest the room's finished ceiling reaches, or None where it can't be read."""
    floor = room.get("floor_elevation")
    if not _number(floor):
        return None
    if _number(room.get("ceiling_height")):
        return floor + room["ceiling_height"]
    zs = [p[2] for piece in room.get("ceilings") or [] if isinstance(piece, list)
          for p in piece if isinstance(p, (list, tuple)) and len(p) == 3 and _number(p[2])]
    return max(zs) if zs else None


def _plan(room: dict):
    try:
        poly = Polygon([(x, y) for x, y in room.get("floor")])
    except (TypeError, ValueError, GEOSException):
        return None
    return poly if poly.is_valid and poly.area > 0 else None


def open_into(description: dict) -> str | None:
    """A room the description draws inside another room's volume (its floor over the other's in plan, above the
    other's floor and below its ceiling, or a ceiling that can't be read: a floor level within a room, open to it, as the format draws a loft), which
    a "no sleeping lofts" claim can't stand beside (the first found), or None. A room upstairs is at or above the
    ceiling of the room below, so it never is. Only refuses the claim: it never says the room is a loft."""
    rooms = [(r, _plan(r)) for r in _rooms(description)]
    for r, plan in rooms:
        if plan is None or not _number(r.get("floor_elevation")):
            continue
        for other, under in rooms:
            if other is r or under is None or not _number(other.get("floor_elevation")):
                continue
            top = _top(other)            # a ceiling that can't be read could be above it: refused too
            if other["floor_elevation"] < r["floor_elevation"] and (top is None or r["floor_elevation"] < top) \
                    and plan.intersection(under).area > 0:
                return f"room {_name(r)}'s floor is within room {_name(other)}, open to it"
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
            problems.append(Stop("has_none_listed", kind=kind, key=LISTED[kind]).reason)
            continue
        if kind not in KINDS:
            problems.append(Stop("has_none_kind", kind=kind, kinds=", ".join(KINDS)).reason)
            continue
        if extra := sorted(set(entry) - ENTRY_KEYS, key=str):    # a mistyped `reading` must never read as settled
            problems.append(Stop("has_none_keys", words=KINDS[kind]["words"], keys=", ".join(map(str, extra))).reason)
            seen.setdefault(kind, []).append(None)
            continue
        source, reading = entry.get("source"), entry.get("reading", False)
        if not isinstance(source, str) or not source.strip():
            problems.append(Stop("has_none_no_source", words=KINDS[kind]["words"]).reason)
            seen.setdefault(kind, []).append(None)          # still counted: a kind said twice is refused
            continue
        if type(reading) is not bool:
            problems.append(Stop("has_none_reading", words=KINDS[kind]["words"]).reason)
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
            problems.append(Stop("has_none_contradicted", words=KINDS[kind]["words"], key=listed).reason)
            continue
        if kind == "basement" and (below := below_ground(description)):
            problems.append(Stop("has_none_below_ground", what=below).reason)
            continue
        if kind == "sleeping_loft" and (inside := open_into(description)):
            problems.append(Stop("has_none_room_within", what=inside).reason)
            continue
        k = KINDS[kind]
        claims[kind] = {"source": sources[0][0], "reading": sources[0][1], "words": words(kind),
                        "parts": list(k.get("parts", ())), "openings": dict(k.get("openings", {})),
                        "stairs": dict(k.get("stairs", {}))}
    return claims, problems


__all__ = ["KEY", "KINDS", "LISTED", "read", "words"]
