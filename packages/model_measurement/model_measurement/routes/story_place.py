"""Where each story sits against the grade plane, worked out from the model: the three story facts the 2025 Building
Code of New York State's single-exit tables read (Table 1006.3.4(1) and (2)): `story_first_above_or_below_grade`,
`story_second_above_grade_plane` and `story_fourth_or_higher_above_grade_plane` (rule_format/parts.yaml).

    places(description, reader, levels, ground) -> {level id: {"measures": {...}, "not_measured": {...},
                                                    "more": {...}}}

The law (BCNYS 2025, Chapter 2, quoted from the book):
- GRADE PLANE (p.48 lines 35-38): "A reference plane representing the average of finished ground level adjoining the
  building at exterior walls. Where the finished ground level slopes away from the exterior walls, the reference plane
  shall be established by the lowest points within the area between the building and the lot line or, where the lot
  line is more than 6 feet (1829 mm) from the building, between the building and a point 6 feet (1829 mm) from the
  building."
- STORY ABOVE GRADE PLANE (p.63 lines 12-16): "Any story having its finished floor surface entirely above grade
  plane, or in which the finished surface of the floor next above is: 1. More than 6 feet (1829 mm) above grade plane;
  2. More than 12 feet (3658 mm) above the finished ground level at any point; or 3. More than 6 feet (1829 mm) above
  the finished ground level for more than 50 percent of the total building perimeter."
- BASEMENT (p.34 line 53): "A story that is not a story above grade plane".
- Table 1006.3.4(2) (p.317): "First story above or below grade plane", "Second story above grade plane"; Table
  1006.3.4(1): "Basement, first, second or third story above grade plane" and "Fourth story above grade plane and
  higher".

How (docs/decisions/2026-11-25_story_facts_from_the_model.md):
- The stories are the levels with rooms, each with the range of its rooms' finished floor elevations and its level's
  own elevation (a sunken room widens it; an enclosed space with no room drawn in it stands on the level). Their floors must stack: one story's highest floor below the next one's lowest, else no place is
  measured (a split level). A level with no rooms between two that have rooms may be a story nobody drew: no place
  is measured.
- The ground is only what the architect stated: flat ground (one elevation: the grade plane and the finished ground
  everywhere), or spot grades at the walls. Spot grades are samples: Gordium's reading is that the ground between two
  spots lies between their values (the usual surveying reading, shown with every figure measured from spots), so the
  average along the walls is at most the highest spot within reach of them; every wall of the stories' outline must
  have one, else nothing is measured. The slope-away rule can only lower the grade plane, below any spot at the
  walls, so spots give no lower bound: a story is never proven a basement from spots, only from flat ground. No
  ground stated, or existing ground (not the finished ground the code measures from), or flat ground only assumed:
  nothing is measured.
- Each story is certainly above grade plane, certainly a basement, or could be either (every threshold tested with
  1/16 in to spare, so a floor on the line is "either"). Being above grade plane holds for every story above one
  that is, so the possible readings are "the lowest b stories are basements" for each b the ground allows. A fact is
  measured only where it is the same under every such b; otherwise it is not measured and says which stories it
  could be. Never a guess: a wrong "first", "second" or "not fourth" could pass a story that one exit can't serve.
"""

import math

from shapely.geometry import LineString, Point
from shapely.ops import unary_union

from model_measurement.interior.stops import Stop as InteriorStop
from model_measurement.routes.stops import Stop

FIRST = "story_first_above_or_below_grade"
SECOND = "story_second_above_grade_plane"
FOURTH = "story_fourth_or_higher_above_grade_plane"
FACTS = (FIRST, SECOND, FOURTH)
FT = 12.0                    # in
SAME = 1 / 16                # in: a figure this close to a threshold could be either side of it
SPOT_REACH = 24.0            # in: a spot grade this close to a wall (in plan) is the ground at that wall (the
#                              zoning reader's own reach, places/ithaca_city/measure.py SPOT_REACH)
WALL_LEAST = 12.0            # in: a wall of the outline shorter than this needs no spot of its own
SPOTS_READING = ("Gordium's reading: the ground between two spot grades lies between their values (the usual "
                 "surveying reading), so the grade plane is at most the highest spot at the walls ({high}); the "
                 "slope-away rule (BCNYS 202 GRADE PLANE) can only lower it")


# --- the ground the architect stated --------------------------------------------------------------------------------

def ground_of(facts: dict | None, unsafe_flat: str | None = None) -> dict:
    """The ground the story places are worked out from, from the check's lot facts (feet): {"flat": elevation},
    {"spots": [[x, y, z], ...]}, or {"none": reason}. `unsafe_flat`: why flat ground the host only assumed can't be
    used (the zoning measuring's own flat_assumption_unsafe), or None."""
    facts = facts or {}
    if facts.get("grade_is") == "existing":
        return {"none": Stop("ground_existing").reason}
    points = facts.get("grade_points")
    if points:
        return {"spots": [list(p) for p in points]}
    if facts.get("ground_is_flat") is True and _number(facts.get("grade_elevation")):
        if facts.get("ground_assumed") is not None:          # the host's assumption, never the architect's word
            return {"none": Stop("ground_assumed", why=unsafe_flat or "assumed, not stated").reason}
        return {"flat": float(facts["grade_elevation"])}
    return {"none": Stop("no_ground").reason}


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# --- the stories ----------------------------------------------------------------------------------------------------

def places(description: dict, reader, levels: dict, stories: dict, ground: dict | None) -> dict:
    """Each story's three place facts (see the module's words). `levels`: {level id: name} as read; `stories`: the
    routes' Story by level id (their outer outlines, read); `ground`: ground_of's."""
    out = {lid: {"measures": {}, "not_measured": {}, "more": {}} for lid in stories}
    if not stories:
        return out

    def none(reason):
        for got in out.values():
            for f in FACTS:
                got["not_measured"].setdefault(f, reason)
        return out

    floors, why = _floors(description, reader, stories)
    if why:
        return none(why)
    for lid in stories:
        if lid not in floors:                                # a level with no rooms (a roof): not a story placed
            for f in FACTS:
                out[lid]["not_measured"][f] = Stop("place_story_no_rooms", name=stories[lid].name).reason
    elevation = {}
    for item in description.get("levels") or []:
        try:
            elevation[item["id"]] = reader.length(item.get("elevation"), "its elevation")
        except (InteriorStop, KeyError, TypeError):
            return none(Stop("place_level_not_read", name=levels.get(item.get("id"), "?")).reason)
    for lid, (f_lo, f_hi) in list(floors.items()):       # the level's own floor too: an enclosed space with no
        z = elevation[lid]                               # room drawn in it is on it, its floor not given
        floors[lid] = (min(f_lo, z), max(f_hi, z))
    order =sorted(floors, key=lambda lid: floors[lid][0])
    for a, b in zip(order, order[1:]):
        if floors[a][1] >= floors[b][0] - SAME:
            return none(Stop("place_split_level", a=stories[a].name, b=stories[b].name).reason)
    lo, hi = floors[order[0]][0], floors[order[-1]][1]
    gaps = [lid for lid in levels if lid not in floors and lid in elevation and lo + SAME < elevation[lid] < hi - SAME]
    if gaps:
        return none(Stop("place_level_no_rooms", name=levels[gaps[0]]).reason)
    plane, why = _plane(ground, reader, stories)
    if why:
        return none(why)
    g_lo, g_hi, ground_low, flat = plane["low"], plane["high"], plane["point"], plane["flat"]
    above, basement = [], []
    for i, lid in enumerate(order):
        f_lo, f_hi = floors[lid]
        nxt = floors[order[i + 1]] if i + 1 < len(order) else None
        above.append(_certainly_above(f_lo, nxt, g_hi, ground_low))
        basement.append(flat is not None and _certainly_basement(f_hi, nxt, flat))
    # above grade plane holds upward, so: b basements for every b from those proven to those not proven above
    b_least = next((i for i, v in enumerate(basement) if not v), len(order))
    b_most = next((i for i, v in enumerate(above) if v), len(order))
    counts = range(b_least, max(b_least, b_most) + 1)
    shown = {"grade_plane_ft": [None if g_lo == -math.inf else round(g_lo / FT, 4), round(g_hi / FT, 4)],
             "basements_possible": list(counts),
             "floors_ft": {lid: [round(floors[lid][0] / FT, 4), round(floors[lid][1] / FT, 4)] for lid in order}}
    if plane.get("reading"):
        shown["reading"] = plane["reading"]
    for i, lid in enumerate(order):
        got = out[lid]
        got["more"]["story_place"] = shown
        each = [_facts(i, b) for b in counts]
        for f in FACTS:
            values = {e[f] for e in each}
            if len(values) == 1:
                got["measures"][f] = values.pop()
            else:
                got["not_measured"][f] = Stop("place_either", name=stories[lid].name,
                                              could=" or ".join(dict.fromkeys(_said(i, b) for b in counts))).reason
    return out


def _facts(i: int, b: int) -> dict:
    """Story i (0 the lowest with rooms) when the lowest b stories are basements."""
    if i < b:
        return {FIRST: b - i == 1, SECOND: False, FOURTH: False}
    n = i - b + 1
    return {FIRST: n == 1, SECOND: n == 2, FOURTH: n >= 4}


def _said(i: int, b: int) -> str:
    n = b - i if i < b else i - b + 1
    nth = {1: "first", 2: "second", 3: "third"}.get(n, f"{n}th")
    return f"the {nth} story {'below' if i < b else 'above'} grade plane"


def _certainly_above(f_lo, nxt, g_hi, ground_low) -> bool:
    """Above grade plane at every grade plane the ground allows (each "more than" with SAME to spare)."""
    if f_lo > g_hi + SAME:                                   # its floor entirely above grade plane
        return True
    if nxt is None:                                          # the floor next above: none drawn (a roof isn't one)
        return False
    if nxt[0] > g_hi + 6 * FT + SAME:                        # item 1
        return True
    return ground_low is not None and nxt[0] > ground_low + 12 * FT + SAME      # item 2: a known point of ground


def _certainly_basement(f_hi, nxt, flat) -> bool:
    """Not above grade plane, on flat ground at `flat` (the grade plane and the ground at every point)."""
    if nxt is None or f_hi > flat - SAME:                    # its floor could be above; nothing next above to test
        return False
    return nxt[1] < flat + 6 * FT - SAME                    # items 1 and 3 (and so item 2) fail


def _floors(description, reader, stories) -> tuple:
    """{level id: (lowest, highest finished floor of its rooms)} for every level with rooms, or why not."""
    floors = {}
    for item in description.get("rooms") or []:
        if not isinstance(item, dict) or item.get("level") not in stories:
            continue
        try:
            z = reader.length(item.get("floor_elevation"), "its floor's elevation")
        except InteriorStop as s:
            name = item.get("name") if isinstance(item.get("name"), str) else "?"
            return None, Stop("place_floor_not_read", name=name, reason=s.reason).reason
        lo, hi = floors.get(item["level"], (z, z))
        floors[item["level"]] = (min(lo, z), max(hi, z))
    if not floors:
        return None, Stop("place_no_rooms").reason
    return floors, None


def _plane(ground, reader, stories) -> tuple:
    """The grade plane's range in inches {low, high, point (a known point of finished ground, or None), flat (its
    elevation on flat ground, else None), reading}, or why not."""
    ground = ground or {"none": Stop("no_ground").reason}
    if "none" in ground:
        return None, ground["none"]
    if "flat" in ground:
        z = ground["flat"] * FT
        return {"low": z, "high": z, "point": z, "flat": z}, None
    spots = [p for p in ground.get("spots") or []
             if isinstance(p, (list, tuple)) and len(p) == 3 and all(_number(v) for v in p)]
    if not spots or len(spots) != len(ground.get("spots") or []):
        return None, Stop("ground_spots_not_read").reason
    outlines = [s.outer for s in stories.values() if s.outer is not None]
    if any(s.outer is None for s in stories.values() if s.rooms):
        return None, Stop("ground_no_outline").reason
    # the outlines are read in inches (the interior reader), the spots are in feet: both in inches here
    footprint = unary_union([o.buffer(0) for o in outlines])
    rings = [g.exterior for g in getattr(footprint, "geoms", [footprint])]
    walls = [LineString([a, b]) for r in rings for a, b in zip(r.coords, r.coords[1:]) if math.dist(a, b) >= WALL_LEAST]
    at = [(Point(x * FT, y * FT), z * FT) for x, y, z in spots]
    near = [(p, z) for p, z in at if any(w.distance(p) <= SPOT_REACH for w in walls)]
    bare = [w for w in walls if not any(w.distance(p) <= SPOT_REACH for p, _ in near)]
    if not walls or bare:
        return None, Stop("ground_wall_bare", count=len(bare) or 1).reason
    high, low = max(z for _, z in near), min(z for _, z in near)
    return {"low": -math.inf, "high": high, "point": low, "flat": None,
            "reading": SPOTS_READING.format(high=f"{high / FT:g} ft")}, None
