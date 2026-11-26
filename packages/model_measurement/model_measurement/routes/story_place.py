"""Where each story sits against the grade plane, worked out from the model: the three story facts the 2025 Building
Code of New York State's single-exit tables read (Table 1006.3.4(1) and (2)): `story_first_above_or_below_grade`,
`story_second_above_grade_plane` and `story_fourth_or_higher_above_grade_plane` (rule_format/parts.yaml).

    places(description, reader, levels, stories, ground) -> {level id: {"measures": {...}, "not_measured": {...},
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
- The stories placed are the levels with rooms, each with the range of its rooms' finished floor elevations and its
  level's own elevation (a sunken room widens it; an enclosed space with no room drawn in it stands on the level).
  Their floors must stack (one story's highest floor below the next one's lowest), else no place is measured (a split
  level). Every level of the model must be listed (`all_levels`: the Revit reader sends every one, one with nothing
  drawn on it too), else nothing is placed: an open parking story with nothing drawn would make the first rooms the
  second story. A level with no rooms (not at a story's floor) may be a story nobody drew rooms on (a garage, a
  lobby) or no story (a roof, a datum): both are tried, so a place is measured only where it is the same either way.
  A description not read whole (a room on no level read) places nothing.
- The ground is only what the architect stated: flat ground (one elevation: the grade plane and the finished ground
  everywhere), or spot grades outside the walls. Spot grades are samples: Gordium's reading is that the ground
  between two spots lies between their values (the usual surveying reading, shown with every figure measured from
  spots), so the average along the walls is at most the highest finished spot grade; every wall of each
  story's own outline (a courtyard's too) must have one outside that story, else nothing is measured (the ground
  floor's walls under an upper story's overhang keep their spots). A spot inside a story's outline is under it, not
  ground beside it. Outlines that come apart (two buildings) aren't placed: whose ground is whose isn't known. A
  spot is never item 2's "finished ground level at any point" (it may stand in an areaway or a window well: open
  question 4.6 of docs/questions_for_architects.md); only flat ground gives that point. The slope-away rule can only lower the grade plane, below any spot at the walls, so
  spots give no lower bound. No ground stated,
  or existing ground (not the finished ground the code measures from), or flat ground only assumed: nothing is
  measured.
- Each story is certainly above grade plane, or could be either (every threshold tested with 1/16 in to spare, so a
  floor on the line is "either"). A story is never proven a basement, on flat ground either: that needs the finished
  ground at every point beside the building, and every review round from 3 to 6 found another way the model can
  hold ground below the stated ground (an area well, a sill below it, a walk-out door, a double-height room over the
  floor next above). Proving a story above grade plane needs only the grade plane's top end, which the stated ground
  bounds. Below the top story, being above grade plane holds for
  every story above one that is (each test only gets easier higher up), so those readings are "the lowest b stories
  are basements"; the top story has no floor next above, so only its own floor decides it, whatever the stories
  under it are. Every reading is tried; a story under the grade plane above one that is above it isn't placed (the
  tables don't say what it is). A fact is measured only where it is the same in every reading; otherwise it is not
  measured and says which stories it could be. Never a guess: a wrong "first", "second" or "not fourth" could pass a
  story that one exit can't serve.
"""

import itertools
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
SPREAD = 48.0               # in: one level's floors this far apart may be two stories (a room drawn on a lower level
#                              with an offset): nothing placed; a sunken room is less
MOST_ROOMLESS = 8            # levels with no rooms tried both ways (2 ** 8 combinations); more: not placed
SPOTS_READING = ("Gordium's reading: the ground between two spot grades lies between their values (the usual "
                 "surveying reading), so the grade plane is at most the highest finished spot grade ({high}); the "
                 "slope-away rule (BCNYS 202 GRADE PLANE) can only lower it")
UNPLACED = "not placed (under the grade plane above a story that is above it)"
MEZZANINE = "not placed (it may be a mezzanine, or the story one is part of: BCNYS 505.2)"
LEVELS_READING = ("Gordium's reading: a story stands where the model has a level for it (every level tried as a story "
                  "or not), or under the lowest level where that is more than 6 ft over the lowest ground stated (then "
                  "nothing is placed); a story with no level of its own below that isn't looked for")


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
        # spot grades are finished ground only where the host says so: Revit's "Finished spot grades", or ground the
        # architect states finished (Rhino's "No regrading near the house"); Revit's plain "Spot grades" are Rhino's
        # Grade layer's, the existing ground
        if facts.get("grade_from") != "finished_spots" and facts.get("grade_is") != "finished":
            return {"none": Stop("ground_spots_not_finished").reason}
        return {"spots": [list(p) for p in points]}
    if facts.get("ground_is_flat") is True and _number(facts.get("grade_elevation")):
        if facts.get("ground_assumed") is not None:          # the host's assumption, never the architect's word
            return {"none": Stop("ground_assumed", why=unsafe_flat or "assumed, not stated").reason}
        return {"flat": float(facts["grade_elevation"])}
    return {"none": Stop("no_ground").reason}


def _number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# --- the stories ----------------------------------------------------------------------------------------------------

def places(description: dict, reader, levels: dict, stories: dict, ground: dict | None, problems=()) -> dict:
    """Each story's three place facts (see the module's words). `levels`: {level id: name} as read; `stories`: the
    routes' Story by level id (their outer outlines, read); `ground`: ground_of's; `problems`: the description's own
    (floor.read's stops: a room on no level read, levels not read...), any of which leaves every place unmeasured."""
    out = {lid: {"measures": {}, "not_measured": {}, "more": {}} for lid in stories}
    if not stories:
        return out

    def none(reason):
        for got in out.values():
            for f in FACTS:
                got["not_measured"].setdefault(f, reason)
        return out

    if problems:                                         # a room or space not placed on a level may be a story's
        return none(Stop("place_description", reasons="; ".join(problems)).reason)
    floors, why = _floors(description, reader, stories)
    if why:
        return none(why)
    for lid in stories:
        if lid not in floors:                                # a level with no rooms (a roof): not a story placed
            for f in FACTS:
                out[lid]["not_measured"][f] = Stop("place_story_no_rooms", name=stories[lid].name).reason
    every = description.get("all_levels")               # every level of the model, one with nothing on it too
    if not isinstance(every, list):
        return none(Stop("place_levels_not_all").reason)
    elevation, names = {}, {}
    for item in every:
        try:
            if not isinstance(item.get("id"), str) or item["id"] in elevation:
                raise KeyError
            elevation[item["id"]] = reader.length(item.get("elevation"), "its elevation")
            names[item["id"]] = item["name"] if isinstance(item.get("name"), str) else item["id"]
        except (InteriorStop, KeyError, TypeError, AttributeError):
            name = item.get("name") if isinstance(item, dict) and isinstance(item.get("name"), str) else "?"
            return none(Stop("place_level_not_read", name=name).reason)
    if any(lid not in elevation for lid in stories):
        return none(Stop("place_levels_not_all").reason)
    for lid, (f_lo, f_hi) in list(floors.items()):       # the level's own floor too: an enclosed space with no
        z = elevation[lid]                               # room drawn in it is on it, its floor not given
        floors[lid] = (min(f_lo, z), max(f_hi, z))
    for lid, (f_lo, f_hi) in floors.items():
        if f_hi - f_lo > SPREAD:
            return none(Stop("place_story_spread", name=stories[lid].name, spread=f"{(f_hi - f_lo) / FT:g} ft").reason)
    order = sorted(floors, key=lambda lid: floors[lid][0])
    for a, b in zip(order, order[1:]):
        if floors[a][1] >= floors[b][0] - SAME:
            return none(Stop("place_split_level", a=stories[a].name, b=stories[b].name).reason)
    # a level with no rooms, not at a story's floor: a story nobody drew rooms on, or none (a roof, a datum)
    roomless = sorted(((z, lid) for lid, z in elevation.items() if lid not in floors), key=lambda e: e[0])
    inside = [lid for z, lid in roomless if any(floors[r][0] + SAME < z < floors[r][1] - SAME for r in order)]
    if inside:                                           # a level within a story's floors: a story drawn on another
        return none(Stop("place_level_inside_story", name=names[inside[0]]).reason)
    roomless = [(z, lid) for z, lid in roomless
                if not any(floors[r][0] - SAME <= z <= floors[r][1] + SAME for r in order)]
    # a level with rooms whose outline is at most 2/3 of the story below's (BCNYS 505.2.1's most), or not given, may
    # be a mezzanine: part of the story below (505.2), so not "the floor next above"; tried both ways, never placed
    mezzanines = [b for a, b in zip(order, order[1:]) if _maybe_mezzanine(stories[b], stories[a])]
    if len(roomless) + len(mezzanines) > MOST_ROOMLESS:
        return none(Stop("place_too_many_levels", count=len(roomless) + len(mezzanines)).reason)
    plane, why = _plane(ground, stories, description, reader)
    if why:
        return none(why)
    lowest = min(elevation.values())
    if lowest > plane["lowest"] + 6 * FT + SAME:         # a story with no level of its own may stand under the lowest
        return none(Stop("place_under_lowest", gap=f"{(lowest - plane['lowest']) / FT:g} ft").reason)   # (an undercroft)
    seen = {lid: [] for lid in order}                    # every reading's facts (or UNPLACED) for each story placed
    for lid in mezzanines:                               # a possible mezzanine, and the story it would be part of (its
        seen[lid].append(MEZZANINE)                      # occupants then that story's, 505.2): never placed
        seen[order[order.index(lid) - 1]].append(MEZZANINE)
    for chosen in itertools.product((False, True), repeat=len(roomless)):
        for kept in itertools.product((True, False), repeat=len(mezzanines)):
            dropped = {m for m, k in zip(mezzanines, kept) if not k}
            stack = sorted([(floors[lid], lid) for lid in order if lid not in dropped] +
                           [((z, z), lid) for (z, lid), on in zip(roomless, chosen) if on], key=lambda s: s[0][0])
            for i, facts in _readings(stack, plane):
                lid = stack[i][1]
                if lid in seen:
                    seen[lid].append(facts)
    shown = {"grade_plane_top_ft": round(plane["high"] / FT, 4),
             "floors_ft": {lid: [round(floors[lid][0] / FT, 4), round(floors[lid][1] / FT, 4)] for lid in order},
             "levels_maybe_stories": [names[lid] for _, lid in roomless],
             "levels_maybe_mezzanines": [names[lid] for lid in mezzanines]}
    shown["levels_reading"] = LEVELS_READING
    if plane.get("reading"):
        shown["reading"] = plane["reading"]
    maybe = ", ".join([names[lid] for _, lid in roomless] + [names[lid] for lid in mezzanines])
    for lid in order:
        got = out[lid]
        got["more"]["story_place"] = shown
        for f in FACTS:
            values = {e if isinstance(e, str) else e[f] for e in seen[lid]}
            if len(values) == 1 and not any(isinstance(v, str) for v in values):
                got["measures"][f] = values.pop()
                continue
            could = " or ".join(dict.fromkeys(e if isinstance(e, str) else e["said"] for e in seen[lid]))
            got["not_measured"][f] = (Stop("place_either_levels", name=stories[lid].name, could=could, levels=maybe)
                                      if maybe else Stop("place_either", name=stories[lid].name, could=could)).reason
    return out


def _maybe_mezzanine(story, below) -> bool:
    """Whether a level with rooms may be a mezzanine of the story below (BCNYS 505.2: "considered a portion of the
    story below"; 505.2.1: at most 1/3, or 2/3 in some buildings, of the room or space it is in): its rooms' floor
    area at most 2/3 of the story below's (its outline, the larger reading), or either not known (a room not read, no
    outline). Its own outline is no guide: a mezzanine stands within the story's exterior walls."""
    rooms = list(story.rooms.values())
    if not rooms or any(r is None for r in rooms) or below.outer is None:
        return True
    return unary_union([r.outline for r in rooms]).area <= below.outer.area * 2 / 3 + 1


def _readings(stack, plane):
    """(index, facts or UNPLACED) for each story of `stack` [((lowest, highest floor), id)] in every reading the
    ground allows: below the top, the lowest b stories basements; the top story either way its own floor allows."""
    hi, low_point = plane["high"], plane["point"]
    n = len(stack)
    above = []
    for i, ((f_lo, f_hi), _) in enumerate(stack):
        nxt = stack[i + 1][0] if i + 1 < n else None
        above.append(_certainly_above(f_lo, nxt, hi, low_point))
    under = n - 1                                        # the stories below the top: monotone upward
    b_least = 0                                          # a basement is never proven (review rounds 3 to 6)
    b_most = next((i for i in range(under) if above[i]), under)
    tops = [True] if above[-1] else [True, False]
    for b in range(b_least, max(b_least, b_most) + 1):
        for top in tops:
            vec = [i >= b for i in range(under)] + [top]
            for i, facts in enumerate(_facts_of(vec)):
                yield i, facts


def _facts_of(vec: list) -> list:
    """Each story's facts from which stories are above grade plane (True), bottom first; UNPLACED for a story under
    the grade plane above one that is above it."""
    out = []
    for i, up in enumerate(vec):
        if up:
            k = sum(vec[:i + 1])
            nth = {1: "first", 2: "second", 3: "third"}.get(k, f"{k}th")
            out.append({FIRST: k == 1, SECOND: k == 2, FOURTH: k >= 4, "said": f"the {nth} story above grade plane"})
        elif any(vec[:i]):
            out.append(UNPLACED)
        else:
            first_up = next((k for k in range(i, len(vec)) if vec[k]), len(vec))
            k = first_up - i
            nth = {1: "first", 2: "second", 3: "third"}.get(k, f"{k}th")
            out.append({FIRST: k == 1, SECOND: False, FOURTH: False, "said": f"the {nth} story below grade plane"})
    return out


def _certainly_above(f_lo, nxt, g_hi, ground_low) -> bool:
    """Above grade plane at every grade plane the ground allows (each "more than" with SAME to spare)."""
    if f_lo > g_hi + SAME:                                   # its floor entirely above grade plane
        return True
    if nxt is None:                                          # the floor next above: none drawn (a roof isn't one)
        return False
    if nxt[0] > g_hi + 6 * FT + SAME:                        # item 1
        return True
    return ground_low is not None and nxt[0] > ground_low + 12 * FT + SAME      # item 2: a known point of ground


def _stated_ground(description, reader) -> list | None:
    """Every finished ground level the description states at an opening (`ground_outside`: one value or a list) and
    every area well's floor, in inches; None where one is given but can't be read."""
    out = []
    openings = (description or {}).get("openings") if isinstance(description, dict) else None
    if openings is not None and not isinstance(openings, list):
        return None                                      # openings that aren't a list: their ground isn't read
    for o in openings or []:
        if not isinstance(o, dict):
            return None                                  # an opening that isn't one: its ground isn't read
        given = o.get("ground_outside")
        well = o.get("area_well")
        try:
            for v in (given if isinstance(given, list) else [] if given is None else [given]):
                out.append(reader.length(v, "the ground outside an opening"))
            if isinstance(well, dict) and well.get("floor_elevation") is not None:
                out.append(reader.length(well["floor_elevation"], "an area well's floor"))
        except InteriorStop:
            return None
    return out


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


def _plane(ground, stories, description=None, reader=None) -> tuple:
    """The grade plane's top end in inches and what else the ground gives: {high, point (a known point of finished
    ground for item 2: the flat ground's elevation, never a spot), reading}, or why not. Finished ground the
    description states at an opening (`ground_outside`) or an area well's floor above the stated ground contradicts it
    (nothing placed); lower ground anywhere never matters, since a basement is never proven."""
    ground = ground or {"none": Stop("no_ground").reason}
    if "none" in ground:
        return None, ground["none"]
    if "flat" in ground:
        z = ground["flat"] * FT
        given = _stated_ground(description, reader)
        if given is None:
            return None, Stop("ground_openings_not_read").reason
        if any(g > z + SAME for g in given):
            return None, Stop("ground_disagrees", flat=f"{ground['flat']:g} ft", high=f"{max(given) / FT:g} ft").reason
        # the grade plane at most the flat ground (an areaway, a well, a walk-out door may be lower: never a basement
        # proven); the flat ground itself a known point of finished ground (item 2)
        return {"high": z, "point": z, "lowest": min([z] + given)}, None     # lower ground stated at an opening too
    spots = [p for p in ground.get("spots") or []
             if isinstance(p, (list, tuple)) and len(p) == 3 and all(_number(v) for v in p)]
    if not spots or len(spots) != len(ground.get("spots") or []):
        return None, Stop("ground_spots_not_read").reason
    if any(s.outer is None for s in stories.values() if s.rooms):
        return None, Stop("ground_no_outline").reason
    # the outlines are read in inches (the interior reader), the spots are in feet: both in inches here
    outlines = [s.outer.buffer(0) for s in stories.values() if s.rooms]
    footprint = unary_union(outlines)
    parts = list(getattr(footprint, "geoms", [footprint]))
    if len(parts) != 1:
        return None, Stop("ground_buildings_apart", count=len(parts)).reason
    at = [(Point(x * FT, y * FT), z * FT) for x, y, z in spots]
    # each story's own walls (a courtyard's too), each with a spot within reach outside that story: the ground floor's
    # walls under an upper story's overhang keep their spots (inside the overhang's outline, outside their own)
    used, bare = [], 0
    for outline in outlines:
        rings = [outline.exterior, *outline.interiors]
        walls = [LineString([a, b]) for r in rings for a, b in zip(r.coords, r.coords[1:]) if math.dist(a, b) >= WALL_LEAST]
        inside = outline.buffer(-SAME)
        near = [z for p, z in at if not inside.contains(p) and any(w.distance(p) <= SPOT_REACH for w in walls)]
        bare += sum(1 for w in walls if not any(w.distance(p) <= SPOT_REACH and not inside.contains(p) for p, _ in at))
        bare += 0 if walls else 1
        used += near
    if bare or not used:
        return None, Stop("ground_wall_bare", count=bare or 1).reason
    # every spot outside the building counts toward the top end: under the reading, ground between a wall's spot and
    # a higher one farther out may rise toward it
    high = max(z for _, z in at)                         # every spot, under the building too: only ever higher
    stated = _stated_ground(description, reader)         # finished ground stated at an opening: above every spot,
    if stated is None:                                   # the spots don't bound the grade plane (nothing placed)
        return None, Stop("ground_openings_not_read").reason
    if any(g > high + SAME for g in stated):
        return None, Stop("ground_disagrees_spots", high=f"{high / FT:g} ft", stated=f"{max(stated) / FT:g} ft").reason
    # item 2's "finished ground level at any point": never a spot (it may stand in an areaway or a window well,
    # whose floor as "ground" is an open question: docs/questions_for_architects.md 4.6), only flat ground
    # the lowest ground beside the building: every spot outside some story's outline (the ground floor's walls under
    # an overhang included); one under every story is under the building, not beside it
    beside = [z for p, z in at if not all(o.buffer(-SAME).contains(p) for o in outlines)] or [z for _, z in at]
    return {"high": high, "point": None, "lowest": min(beside + stated),
            "reading": SPOTS_READING.format(high=f"{high / FT:g} ft")}, None
