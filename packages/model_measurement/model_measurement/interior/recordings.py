"""Interior conformance for a host that reads a house's inside itself (the Revit add-in): the hand-worked houses drawn
in the host from their own data, read by its reader, recorded, and the recording's measures compared with the
house's expected.yaml (docs/revit/revit_interior_reading_design.md, section 6). Measuring is this package's own code;
the host only describes.

    python -m model_measurement.interior.recordings draw            # each house to draw, one JSON line, in feet
    python -m model_measurement.interior.recordings check <file>    # a recording's problems, as a JSON list ([]: passes)

A recording is test_data/interior_houses/recorded/<host>/<house>.json:
    {"host", "house", "step", "recorded": {"by", "date", "tool"}, "ids": {<house id>: <host id>}, "interior": {...},
     "notes": [...], "evidence": {...}}

Each building step has a scope (SCOPE): every measure of a kind in scope must equal the reference (expected.yaml's
value where it gives one, else what the measuring code gives on the hand-written house.yaml: expected.yaml is never
edited to fit a host); every other measure must come back not measured, never a value; and a kind not in the step at
all must not be read. A recording differing either way fails.
"""

import json
import math
import sys
from pathlib import Path

import yaml
from shapely.geometry import Point, Polygon

from model_measurement.interior import measure
from model_measurement.interior.read import INCHES

REPO = Path(__file__).resolve().parents[4]
HOUSES = REPO / "test_data" / "interior_houses"
RECORDED = HOUSES / "recorded"

# Section 7, step 3 (rooms and marked escape windows): the measures read. A sleeping room's floor area, the floor drawn
# and the least ceiling height; an escape opening's clear opening, sill height and whether it is a door (and a hinged
# or sliding one). Not in this step: grade-floor (no Toposolid is drawn: no ground), the area well, patio cover and
# projection measures, being in an addition, operable, opening to a yard, fully openable, below grade (the measuring
# code doesn't work these out yet); stairs, doors and guards (later steps).
ROOMS_AND_WINDOWS = {
    "sleeping_room": {"sleeping_room_floor_area", "floor_area_drawn", "least_ceiling_height"},
    "emergency_escape_opening": {"opening_net_clear_width", "opening_net_clear_height", "opening_net_clear_area",
                                 "opening_sill_height", "opening_is_door", "opening_door_hinged_or_sliding"},
}
# Step 4 (stairs: straight component runs, the cross-check): a flight's risers, treads, headroom and clear width above
# the handrail. Not in this step: the width at the handrail and the handrail sides (handrails are railings, read with
# the guards in step 5: no `handrails` is sent, so both are not measured).
STAIRS = {"stair_riser_height", "stair_riser_variation", "stair_total_rise", "stair_risers", "stair_tread_depth",
          "stair_tread_variation", "stair_headroom", "stair_clear_width"}
# Each step's houses and, per house, the measures of each kind in scope (a kind present is read; a kind absent must be
# left out). House 3's tall riser can't be drawn inside a Revit component run (its risers are equal by construction),
# so it is drawn where a tall riser arises in Revit: the floor at the head 1 1/2 in above the run's top. The reader
# measures the last riser as drawn, to that floor (R318.7.5.1: "measured vertically between leading edges of the
# adjacent treads"; Ben, 2026-11-20, Q1), so its stair measures are the hand-worked ones: 12 risers of 7 1/2 in and
# one of 9 in (at the head, not the 7th: the same tallest, smallest and total), riser height 9, variation 1.5, total
# rise 99 in, 13 risers; never 7.5 in, never a pass.
# Step 5 (doors, then guards; house 4): the exit door's clear width and height (from the maker's stated clear opening
# the architect confirmed on its type: door families aren't measured from their drawing) and whether it is
# side-hinged; a stair's handrails (the width at the handrail, the sides with one); a level guard's height and the
# largest sphere through it.
DOORS = {"door_clear_width", "door_clear_height", "door_side_hinged"}
HANDRAILS = {"stair_clear_width_at_handrail", "stair_handrail_sides"}
GUARDS = {"guard_height", "guard_opening_sphere"}
# House 4's loft is drawn clear of its bedroom (its floor over the bedroom would be the bedroom's ceiling, which the
# hand-worked house doesn't give: one 16 ft ceiling), so its rooms' measures are step 3's. Its bedroom's awning window
# has no maker's clear opening: every clear measure comes back not measured, as worked by hand. House 5's sliding exit
# door has no clear width worked by hand (R318.2 measures a side-hinged door), so no maker's clear opening, which needs
# both sizes, is made up for it: only whether it is side-hinged is in scope, its height expected not measured.
# House 3 isn't drawn again: its guard is along a stair, which this step doesn't read (a railing along a stair that
# isn't a handrail against a wall leaves `guards` out), and its stair is measured in step 4 already.
STEPS = {
    3: {"1_ranch_compliant": ROOMS_AND_WINDOWS, "2_two_story_small_window": ROOMS_AND_WINDOWS,
        "5_basement_window_well": ROOMS_AND_WINDOWS},
    4: {"2_two_story_small_window": {**ROOMS_AND_WINDOWS, "stair": STAIRS},
        "3_tall_riser": {**ROOMS_AND_WINDOWS, "stair": STAIRS}},
    5: {"1_ranch_compliant": {**ROOMS_AND_WINDOWS, "egress_door": DOORS},
        "2_two_story_small_window": {**ROOMS_AND_WINDOWS, "stair": STAIRS | HANDRAILS, "egress_door": DOORS},
        "4_loft": {**ROOMS_AND_WINDOWS, "stair": STAIRS | HANDRAILS, "guard": GUARDS},
        "5_basement_window_well": {**ROOMS_AND_WINDOWS, "egress_door": {"door_side_hinged"}},
        "6_door_stated_clear": {**ROOMS_AND_WINDOWS, "egress_door": DOORS}},
    # Step 6 (the architect's "this house has none of" ticks): each list the hand-worked house gives empty (houses 1
    # and 6 `stairs: []`; 1, 2, 5 and 6 `guards: []`; 4 `doors: []`) is ticked in the drawing (NONE_LISTS, `has_none`)
    # and must come back as that empty list: in scope with no measures. No hand-worked house has a `has_none` claim, so
    # none is ticked and none may come back (recording_problems compares them). House 5's stair isn't drawn (as in step
    # 5), but no guard is: "no guards" is the house's own. House 3 has no empty list: it stays step 4.
    6: {"1_ranch_compliant": {**ROOMS_AND_WINDOWS, "egress_door": DOORS, "stair": set(), "guard": set()},
        "2_two_story_small_window": {**ROOMS_AND_WINDOWS, "stair": STAIRS | HANDRAILS, "egress_door": DOORS,
                                     "guard": set()},
        "4_loft": {**ROOMS_AND_WINDOWS, "stair": STAIRS | HANDRAILS, "guard": GUARDS, "egress_door": set()},
        "5_basement_window_well": {**ROOMS_AND_WINDOWS, "egress_door": {"door_side_hinged"}, "guard": set()},
        "6_door_stated_clear": {**ROOMS_AND_WINDOWS, "egress_door": DOORS, "stair": set(), "guard": set()}},
}
# the lists the format has itself, each the part kind it gives: an empty one is the house having none (step 6's ticks)
NONE_LISTS = {"stairs": "stair", "doors": "egress_door", "guards": "guard"}
STEP = max(STEPS)
# each house at the latest step that draws it: its recording must be of that step
HOUSE_STEP = {house: step for step in sorted(STEPS) for house in STEPS[step]}
STEP_HOUSES = tuple(sorted(HOUSE_STEP))
TOL = 1e-6                      # the houses' own tolerance (test_interior_houses: to a millionth)


def scope(name: str) -> dict:
    """{kind: measures in scope} for the house at its step."""
    return STEPS[HOUSE_STEP[name]][name]


def _house(name: str) -> dict:
    return yaml.safe_load((HOUSES / name / "house.yaml").read_text(encoding="utf-8"))


def _expected(name: str) -> dict:
    return yaml.safe_load((HOUSES / name / "expected.yaml").read_text(encoding="utf-8"))


# ---- the comparison ---------------------------------------------------------------------------------------------

def _values(part: dict) -> dict:
    return {**part.get("more", {}), **part.get("measures", {})}


def reference(name: str) -> dict:
    """{kind: {house id: {"within": id, "values": {measure: value}, "not_measured": set}}} for the kinds in scope:
    expected.yaml's values and not-measured, with what the measuring code gives on house.yaml for every other in-scope
    measure (expected.yaml lists every measure of `measures`, but only some of `more`)."""
    expected, got = _expected(name)["parts"], measure(_house(name))["parts"]
    out = {}
    for kind in scope(name):
        want = expected.get(kind) or {}
        mine = {p["id"]: p for p in got[kind] or []}
        if set(mine) != set(want):
            raise AssertionError(f"{name}: the measuring code's {kind} {sorted(mine)} aren't expected.yaml's {sorted(want)}")
        out[kind] = {}
        for pid, w in want.items():
            values = {**_values(mine[pid]), **(w.get("more") or {}), **(w.get("measures") or {})}
            stopped = set(w.get("not_measured") or [])
            out[kind][pid] = {"within": w.get("within"), "values": {k: v for k, v in values.items() if k not in stopped},
                              "not_measured": stopped}
    return out


def _same(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= TOL
    return a == b


def recording_problems(rec: dict) -> list[str]:
    """Why a recording fails this step's interior conformance ([] when it passes)."""
    if not isinstance(rec, dict):
        return ["a recording is a JSON object"]
    name, host = rec.get("house"), rec.get("host")
    where = f"{host}/{name}"
    if name not in HOUSE_STEP:
        return [f"{where}: not a house of any step ({', '.join(STEP_HOUSES)})"]
    problems = []
    step, SCOPE = HOUSE_STEP[name], scope(name)
    if rec.get("step") != step:
        problems.append(f"{where}: recorded for step {rec.get('step')}, not step {step} (the latest step that draws it)")
    made = rec.get("recorded")
    if not isinstance(made, dict) or not all(isinstance(made.get(k), str) and made.get(k) for k in ("by", "date", "tool")):
        problems.append(f"{where}: says how it was recorded (recorded: by, date, tool)")
    ids = rec.get("ids")
    if not isinstance(ids, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in ids.items()):
        return problems + [f"{where}: no id map (ids: house id -> the host's id)"]
    back = {}
    for house_id, host_id in ids.items():
        if host_id in back:
            problems.append(f"{where}: {back[host_id]} and {house_id} recorded as the same element {host_id}")
        back[host_id] = house_id
    got = measure(rec.get("interior"))
    ref = reference(name)
    for kind, parts in got["parts"].items():
        if kind not in SCOPE:
            if parts is not None:
                problems.append(f"{where}: {kind} read ({len(parts)} parts): not in step {step}, so it must be left out "
                                f"(not read), never a list")
            continue
        if parts is None:
            problems.append(f"{where}: {kind} not read ({'; '.join(got['problems'])})")
            continue
        mine = {}
        for p in parts:
            hid = back.get(p["id"])
            if hid is None:
                problems.append(f"{where}: {kind} {p['id']} isn't in the id map")
                continue
            mine[hid] = p
        want = ref[kind]
        for missing in sorted(set(want) - set(mine)):
            problems.append(f"{where}: {kind} {missing} wasn't measured")
        for extra in sorted(set(mine) - set(want)):
            problems.append(f"{where}: {kind} {extra} measured, but the house has no such {kind}")
        for hid in sorted(set(want) & set(mine)):
            p, w = mine[hid], want[hid]
            within = back.get(p["within"]) if p.get("within") is not None else None
            if within != w["within"]:
                problems.append(f"{where}: {hid} is within {within}, expected {w['within']}")
            values = _values(p)
            for m in sorted(set(values) | set(w["values"]) | w["not_measured"]):
                if m not in SCOPE[kind]:
                    if m in values:
                        problems.append(f"{where}: {hid} {m} = {values[m]!r}: not in step {step}, so it must be not "
                                        f"measured, never a value")
                elif m in w["values"]:
                    if m not in values:
                        problems.append(f"{where}: {hid} {m} not measured ({p['not_measured'].get(m)}), expected "
                                        f"{w['values'][m]!r}")
                    elif not _same(values[m], w["values"][m]):
                        problems.append(f"{where}: {hid} {m} = {values[m]!r}, expected {w['values'][m]!r}")
                elif m in values:
                    problems.append(f"{where}: {hid} {m} = {values[m]!r}, expected not measured")
    # what the house has none of (step 6): the claims sent and taken must be exactly the hand-worked house's own
    house_none = sorted(measure(_house(name))["has_none"])
    interior = rec.get("interior") if isinstance(rec.get("interior"), dict) else {}
    sent = interior.get("has_none") or []
    sent_kinds = sorted(str(e.get("kind")) if isinstance(e, dict) else repr(e) for e in sent) \
        if isinstance(sent, list) else [repr(sent)]
    if sent_kinds != house_none or sorted(got["has_none"]) != house_none:
        problems.append(f"{where}: has none of {sent_kinds} (taken: {sorted(got['has_none'])}), expected {house_none}")
    house_not_checked = sorted(x["id"] for x in measure(_house(name))["not_checked"])
    not_checked = sorted(back.get(x["id"], str(x["id"])) for x in got["not_checked"])
    if not_checked != house_not_checked:
        problems.append(f"{where}: escape openings not checked (in a room that isn't a sleeping room) are "
                        f"{not_checked}, expected {house_not_checked}")
    return problems


def recordings(host: str | None = None) -> dict:
    """{host: {house: recording}} from recorded/<host>/<house>.json (a file that isn't JSON: {"refused": why})."""
    out = {}
    for path in sorted(RECORDED.glob("*/*.json")):
        if host is not None and path.parent.name != host:
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            rec = {"refused": f"not JSON ({e})"}
        out.setdefault(path.parent.name, {})[path.stem] = rec
    return out


def coverage_problems(recorded: dict) -> list[str]:
    """A host with any recording has one for every house of the step: it can't leave out the hard ones."""
    return [f"{host}: no recording for {', '.join(sorted(set(STEP_HOUSES) - set(by)))}"
            for host, by in sorted(recorded.items()) if set(STEP_HOUSES) - set(by)]


# ---- the houses to draw -----------------------------------------------------------------------------------------

EXTERIOR_WALL = 0.5             # ft: the exterior walls' thickness (their inside faces stand on the rooms' outline)
CEILING_THICKNESS = 1 / 12      # ft: a ceiling piece drawn as a thin solid, its underside the piece


def _ft(units: str):
    times, per = INCHES[units]
    return lambda v: v * times / per / 12


def _edges(poly):
    pts = list(poly.exterior.coords)[:-1]
    return [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]


def _shared(a, b):
    """The stretch two straight edges share (both horizontal or both vertical on one line), or None."""
    (ax0, ay0), (ax1, ay1) = a
    (bx0, by0), (bx1, by1) = b
    if ay0 == ay1 == by0 == by1:
        lo, hi = max(min(ax0, ax1), min(bx0, bx1)), min(max(ax0, ax1), max(bx0, bx1))
        return [[lo, ay0], [hi, ay0]] if hi > lo else None
    if ax0 == ax1 == bx0 == bx1:
        lo, hi = max(min(ay0, ay1), min(by0, by1)), min(max(ay0, ay1), max(by0, by1))
        return [[ax0, lo], [ax0, hi]] if hi > lo else None
    return None


def drawing(name: str) -> dict:
    """A house as a host draws it, in feet, from its house.yaml (and, for an escape window's maker's clear opening, what
    the measuring code works out from its frame and sash: what a maker would publish): each level's rooms, the
    exterior walls around them (their inside faces on the rooms' outline), a wall filling any gap between rooms, a
    room separation line wherever two rooms meet, each room's ceiling as thin solids whose undersides are its
    ceiling, and each window in an outside wall of its room. Rooms whose plan isn't a rectangle on the axes aren't
    drawn yet (refused). From step 5: each door (_doors), each stair's handrails (_stair) and each level guard (_guard);
    a room within another's height (a loft) drawn clear of it."""
    house = _house(name)
    ft = _ft(house["units"])
    measured = {p["id"]: p for p in measure(house)["parts"]["emergency_escape_opening"] or []}
    rooms, levels = [], {}
    for r in house["rooms"]:
        floor = [[ft(x), ft(y)] for x, y in r["floor"]]
        poly = Polygon(floor)
        if abs(poly.area - poly.envelope.area) > 1e-9:
            raise ValueError(f"{name}: room {r['id']} isn't a rectangle on the axes")
        fe = ft(r["floor_elevation"])
        if "ceilings" in r:
            ceilings = [[[ft(x), ft(y), ft(z)] for x, y, z in piece] for piece in r["ceilings"]]
        else:
            ceilings = [[[x, y, fe + ft(r["ceiling_height"])] for x, y in floor]]
        room = {"id": r["id"], "name": r["name"], "sleeping": r["sleeping"], "floor": floor, "floor_elevation": fe,
                "ceilings": ceilings}
        rooms.append(room)
    notes = []
    # a room drawn within another's height (a loft: its floor over the other's, above its floor and under its
    # ceiling) is drawn clear of it, moved in plan (x only): drawn over it, its floor slab would be the other room's
    # ceiling there, which the hand-worked house doesn't give (house 4: the bedroom's one 16 ft ceiling). A room's
    # measures don't depend on where it stands
    for room in rooms:
        under = [o for o in rooms if o is not room and o["floor_elevation"] < room["floor_elevation"]
                 < max(z for piece in o["ceilings"] for _, _, z in piece)
                 and Polygon(o["floor"]).intersection(Polygon(room["floor"])).area > 0]
        if under:
            dx = max(x for o in rooms for x, _ in o["floor"]) + EXTERIOR_WALL + ROOM_GAP - min(x for x, _ in room["floor"])
            room["floor"] = [[x + dx, y] for x, y in room["floor"]]
            room["ceilings"] = [[[x + dx, y, z] for x, y, z in piece] for piece in room["ceilings"]]
            notes.append(f"room {room['id']}: within the height of {', '.join(o['id'] for o in under)} (a loft), so drawn "
                         f"{dx:g} ft clear of it: drawn over it, its floor would be the other room's ceiling there")
    for room in rooms:
        levels.setdefault(room["floor_elevation"], []).append(room)
    out_levels = []
    elevations = sorted(levels)
    for fe, here in sorted(levels.items()):
        polys = [Polygon(r["floor"]) for r in here]
        x0, y0 = min(p.bounds[0] for p in polys), min(p.bounds[1] for p in polys)
        x1, y1 = max(p.bounds[2] for p in polys), max(p.bounds[3] for p in polys)
        xs = sorted({x for p in polys for x, _ in p.exterior.coords} | {x0, x1})
        ys = sorted({y for p in polys for _, y in p.exterior.coords} | {y0, y1})
        fillers = []
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                c = Point((xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2)
                if not any(p.contains(c) for p in polys):
                    fillers.append([[xs[i], ys[j]], [xs[i + 1], ys[j + 1]]])
        separations = []
        for i in range(len(here)):
            for j in range(i + 1, len(here)):
                for a in _edges(polys[i]):
                    for b in _edges(polys[j]):
                        if (s := _shared(a, b)) is not None:
                            separations.append(s)
        # the walls stop at the top of the ceilings, never above: a basement's walls reaching past the level over it
        # would enclose an area on that level too (trial run 3, 2026-11-20: house 5's walls, up a foot past its
        # ceiling, closed an area on Level 1, where the hand-worked house has none)
        top = max(z for r in here for piece in r["ceilings"] for _, _, z in piece) + CEILING_THICKNESS
        # nor past the next level up (house 4's bedroom, 16 ft high, under its loft's level at 9 ft): walls through a
        # level enclose an area on it, with no Room (trial run 3, as above)
        above = [z for z in elevations if z > fe]
        if above and top > above[0]:
            top = above[0]
        out_levels.append({"elevation": fe, "box": [[x0, y0], [x1, y1]], "fillers": fillers,
                           "separations": separations, "wall_height": top - fe})
    windows = []
    by_room = {}
    for o in house.get("openings") or []:
        by_room.setdefault(o["room"], []).append(o)
    for room in rooms:
        here = by_room.get(room["id"], [])
        if not here:
            continue
        level = next(lv for lv in out_levels if lv["elevation"] == room["floor_elevation"])
        (bx0, by0), (bx1, by1) = level["box"]
        (rx0, ry0), (rx1, ry1) = Polygon(room["floor"]).bounds[:2], Polygon(room["floor"]).bounds[2:]
        sides = [((rx0, ry0), (rx1, ry0), (0, -1), ry0 == by0), ((rx0, ry0), (rx0, ry1), (-1, 0), rx0 == bx0),
                 ((rx0, ry1), (rx1, ry1), (0, 1), ry1 == by1), ((rx1, ry0), (rx1, ry1), (1, 0), rx1 == bx1)]
        side = next((s for s in sides if s[3]), None)
        if side is None:
            raise ValueError(f"{name}: room {room['id']} has windows but no outside wall")
        (sx0, sy0), (sx1, sy1), outward, _ = side
        for k, o in enumerate(here, 1):
            t = k / (len(here) + 1)
            fe = room["floor_elevation"]
            part = measured.get(o["id"])
            if "frame" in o:
                f = o["frame"]
                width, height, bottom = ft(f["right"] - f["left"]), ft(f["top"] - f["bottom"]), ft(f["bottom"])
            elif "stated_clear" in o:
                s = o["stated_clear"]
                width, height, bottom = ft(s["width"]), ft(s["height"]), ft(s["bottom"])
            else:
                raise ValueError(f"{name}: opening {o['id']} has neither a frame nor a maker's clear opening")
            clear = None
            if part is not None and "opening_net_clear_width" in part["measures"] \
                    and "opening_sill_height" in part["measures"]:
                m = part["measures"]
                clear_bottom = fe + m["opening_sill_height"] / 12
                clear = {"width": m["opening_net_clear_width"] / 12, "height": m["opening_net_clear_height"] / 12,
                         "offset": round(clear_bottom - bottom, 9) + 0.0,     # float noise off
                         "source": (o.get("stated_clear") or {}).get("source")
                         or "the maker's net clear opening (made up: worked out from house.yaml's frame and sash)"}
            windows.append({"id": o["id"], "name": o.get("name") or o["id"], "room": room["id"],
                            "escape": o["escape"], "operation": o["operation"], "width": width, "height": height,
                            "sill": bottom - fe, "level": fe,
                            "center": [sx0 + t * (sx1 - sx0), sy0 + t * (sy1 - sy0)], "outward": list(outward),
                            "clear": clear})
    stairs = []
    x_clear = max(lv["box"][1][0] for lv in out_levels) + EXTERIOR_WALL + STAIR_GAP
    handrails = HANDRAILS <= scope(name).get("stair", set())
    if "stair" in scope(name):
        for st in house.get("stairs") or []:
            drawn, note = _stair(name, st, ft, house, x_clear, handrails)
            stairs.append(drawn)
            notes += note
            x_clear = drawn["extent"][1] + STAIR_GAP
    doors = _doors(name, house, ft, rooms, out_levels, windows) if "egress_door" in scope(name) else []
    guards = []
    if "guard" in scope(name):
        for g in house.get("guards") or []:
            if g.get("stair") is not None:
                raise ValueError(f"{name}: guard {g['id']} is along a stair, which isn't drawn yet")
            drawn = _guard(name, g, ft, x_clear)
            guards.append(drawn)
            x_clear = drawn["extent"][1] + STAIR_GAP
    not_drawn = set()
    if house.get("doors") and not doors:
        not_drawn.add("doors")
    if house.get("guards") and not guards:
        not_drawn.add("guards")
    if not stairs and house.get("stairs"):
        not_drawn.add("stairs")
    if stairs and not handrails and any(st.get("handrails") for st in house["stairs"]):
        not_drawn.add("handrails")
    # step 6: the "this house has none of" ticks to set: each list in scope the house gives empty, then each claim of
    # its own has_none (the reader sends each back only when nothing of the kind is drawn)
    has_none = [key for key, kind in NONE_LISTS.items() if house.get(key) == [] and kind in scope(name)] \
        + [c["kind"] for c in house.get("has_none") or []]
    return {"house": name, "step": HOUSE_STEP[name], "units": "ft", "exterior_wall": EXTERIOR_WALL,
            "ceiling_thickness": CEILING_THICKNESS, "levels": out_levels, "rooms": rooms, "windows": windows,
            "stairs": stairs, "doors": doors, "guards": guards, "rail": RAIL, "handrail_top": HANDRAIL_TOP,
            "notes": notes, "not_drawn": sorted(not_drawn), "has_none": has_none}


ROOM_GAP = 10.0                 # ft: a room drawn clear of the room it is within the height of (a loft)
RAIL = 1.5 / 12                 # ft: a drawn rail's width (and height): a handrail, a guard's rails and balusters' depth
HANDRAIL_TOP = 3.0              # ft: a drawn handrail's top over the line of nosings (R318.7.8: 34 to 38 in)
DOOR_WIDTH = 3.0                # ft: a door drawn with no stops (a sliding door): the family's width
DOOR_HEIGHT = 80 / 12           # ft: and its height with no threshold or head stop drawn


def _doors(name: str, house: dict, ft, rooms: list, levels: list, windows: list) -> list:
    """Each door in an outside wall with no window in it (a room that isn't a sleeping room's first), spread along it:
    its family's size from its drawing (stop to stop, threshold to head stop), else a 3 ft x 6 ft 8 in door; and, where
    the measuring code works out both its clear width and height, those as the maker's clear opening the architect
    confirmed on its type (what a maker would publish, never more than the less favourable of drawn and stated). Where
    a door stands doesn't change its measures (the reader sends no drawn stops, pin or leaf: door families don't model
    them consistently)."""
    given = house.get("doors") or []
    if not given:
        return []
    measured = {p["id"]: p for p in measure(house)["parts"]["egress_door"] or []}
    taken = {(w["level"], tuple(w["outward"]), w["room"]) for w in windows}
    choice = None
    for room in sorted(rooms, key=lambda r: r["sleeping"]):
        level = next(lv for lv in levels if lv["elevation"] == room["floor_elevation"])
        (bx0, by0), (bx1, by1) = level["box"]
        (rx0, ry0, rx1, ry1) = Polygon(room["floor"]).bounds
        for (a, b), outward, outside in (((rx0, ry0), (rx1, ry0)), (0, -1), ry0 == by0), \
                (((rx0, ry0), (rx0, ry1)), (-1, 0), rx0 == bx0), (((rx0, ry1), (rx1, ry1)), (0, 1), ry1 == by1), \
                (((rx1, ry0), (rx1, ry1)), (1, 0), rx1 == bx1):
            if outside and not any(t[0] == room["floor_elevation"] and t[1] == outward for t in taken):
                choice = (room, a, b, outward)
                break
        if choice:
            break
    if choice is None:
        raise ValueError(f"{name}: no outside wall without a window for its doors")
    room, (ax, ay), (bx, by), outward = choice
    out = []
    for k, d in enumerate(given, 1):
        t = k / (len(given) + 1)
        stops = d.get("stops")
        width = ft(abs(stops["latch"] - stops["hinge"])) if stops else DOOR_WIDTH
        height = ft(d["head_stop_bottom"] - d["threshold_top"]) \
            if d.get("head_stop_bottom") is not None and d.get("threshold_top") is not None else DOOR_HEIGHT
        part = measured.get(d["id"])
        clear = None
        if part is not None and {"door_clear_width", "door_clear_height"} <= set(part["measures"]):
            m = part["measures"]
            clear = {"width": m["door_clear_width"] / 12, "height": m["door_clear_height"] / 12,
                     "source": "the maker's clear opening (made up: the less favourable of house.yaml's drawn and "
                               "stated clear opening, as the measuring code works it out)"}
        out.append({"id": d["id"], "name": d.get("name") or d["id"], "exit": d["exit"], "operation": d["operation"],
                    "width": width, "height": height, "level": room["floor_elevation"], "room": room["id"],
                    "center": [ax + t * (bx - ax), ay + t * (by - ay)], "outward": list(outward), "clear": clear})
    span = math.hypot(bx - ax, by - ay)
    if any(d["width"] > span / (len(given) + 1) for d in out):
        raise ValueError(f"{name}: its doors don't fit along the wall chosen for them")
    return out


def _guard(name: str, g: dict, ft, x_clear: float) -> dict:
    """A guard at a level walking surface as a Revit railing draws it, in feet, clear of the house (where it stands
    doesn't change its measures): its path along +x from the face of a wall at its left end to the face of a post (a
    short wall) at its right, along the edge of a floor on the walking side (y below the path); its rails (the members
    running its whole extent, the top one its top rail) and its balusters (every other member: equal, equally spaced),
    each height above the walking surface, the balusters' first left edge along it. Anything else is refused."""
    walk, top = ft(g["walking_surface"]), ft(g["top"])
    left, right = ft(g["extent"]["left"]), ft(g["extent"]["right"])
    members = [{k: ft(m[k]) for k in ("left", "right", "bottom", "top")} for m in g["members"]]
    rails = [m for m in members if abs(m["left"] - left) < 1e-9 and abs(m["right"] - right) < 1e-9]
    balusters = sorted((m for m in members if m not in rails), key=lambda m: m["left"])
    tops = [m for m in rails if abs(m["top"] - top) < 1e-9]
    if len(tops) != 1:
        raise ValueError(f"{name}: guard {g['id']} hasn't one top rail reaching its top")
    widths = {round(m["right"] - m["left"], 9) for m in balusters}
    heights = {(round(m["bottom"], 9), round(m["top"], 9)) for m in balusters}
    steps = {round(b["left"] - a["left"], 9) for a, b in zip(balusters, balusters[1:])}
    if not balusters or len(widths) != 1 or len(heights) != 1 or len(steps) > 1:
        raise ValueError(f"{name}: guard {g['id']}'s balusters aren't equal and equally spaced")
    length = right - left
    y = 0.0
    x0 = x_clear
    post = 4 / 12
    reach = 1.0
    bal = balusters[0]
    return {"id": g["id"], "name": g.get("name") or g["id"], "level": walk, "start": [x0, y], "end": [x0 + length, y],
            "length": length, "top": top - walk,
            "top_rail": {"bottom": tops[0]["bottom"] - walk, "top": tops[0]["top"] - walk},
            "rails": [{"bottom": m["bottom"] - walk, "top": m["top"] - walk} for m in rails if m is not tops[0]],
            "balusters": {"first": bal["left"] - left, "width": bal["right"] - bal["left"],
                          "spacing": balusters[1]["left"] - bal["left"] if len(balusters) > 1 else 0.0,
                          "count": len(balusters),
                          "bottom": bal["bottom"] - walk, "top": bal["top"] - walk},
            "floor": [[x0 - post, y - 3.0], [x0 + length + post, y - 3.0], [x0 + length + post, y], [x0 - post, y]],
            "slab": SLAB,
            "end_walls": [{"line": [[x0 - post / 2, y - reach], [x0 - post / 2, y + reach]], "thickness": post},
                          {"line": [[x0 + length + post / 2, y - reach], [x0 + length + post / 2, y + reach]],
                           "thickness": post}],
            "wall_top": top - walk + 1.0, "extent": [x0 - post, x0 + length + post]}


STAIR_GAP = 10.0                # ft: each stair drawn this far clear of the house and of the stair before it
STAIR_WALL = 0.5                # ft: a side wall's thickness (its face on the house's side line)
STRIP = 3.0                     # ft: how far the floor at a flight's foot and head reaches out from it
SLAB = 1.0                      # ft: their thickness
HEADROOM_WALL = 7.0             # ft: the side walls rise this far above the top nosing (the reader looks up 80 in)


def _stair(name: str, st: dict, ft, house: dict, x_clear: float, handrails: bool = False) -> tuple[dict, list[str]]:
    """One flight as a Revit component stair draws it, in feet, moved in plan (x only) to stand clear of the house:
    its risers (equal: a component run's are), tread depth and width, the centre line from its first riser to its last
    (the run's location path), the floor at its foot and head as thin slabs, each side that is a wall as the line of
    the wall's face (a side that is a guard is a railing: step 5, not drawn), and what is overhead as thin solids whose
    undersides are the house's pieces. Measures are the same wherever it stands; only a straight flight along an axis,
    with equal treads and equal risers but at most one (drawn at the head: see STEPS), can be drawn (else refused)."""
    nos = [[[ft(v) for v in end] for end in n] for n in st["nosings"]]
    base = ft(st["bottom_elevation"])
    zs = [base] + [n[0][2] for n in nos]
    if any(abs(n[0][2] - n[1][2]) > 1e-9 for n in nos):
        raise ValueError(f"{name}: stair {st['id']} has a nosing that isn't level")
    risers = [b - a for a, b in zip(zs, zs[1:])]
    common = max(set(round(r, 9) for r in risers), key=lambda r: sum(1 for x in risers if abs(x - r) < 1e-9))
    other = [r for r in risers if abs(r - common) > 1e-9]
    if len(other) > 1 or any(r < common for r in other):
        raise ValueError(f"{name}: stair {st['id']}'s risers can't be drawn as a component run (equal risers, at most one taller)")
    extra = sum(other) - len(other) * common
    (p1, p2), (q1, _) = nos[0], nos[1]
    if abs(p1[0] - p2[0]) < 1e-9:                    # nosing along y: the run goes along x
        axis, across = 0, 1
    elif abs(p1[1] - p2[1]) < 1e-9:
        axis, across = 1, 0
    else:
        raise ValueError(f"{name}: stair {st['id']} doesn't run along an axis")
    sign = 1 if q1[axis] > p1[axis] else -1
    s = [n[0][axis] for n in nos]
    treads = [sign * (b - a) for a, b in zip(s, s[1:])]
    ends = {(min(n[0][across], n[1][across]), max(n[0][across], n[1][across])) for n in nos}
    if max(treads) - min(treads) > 1e-9 or len(ends) != 1 or any(abs(n[0][axis] - n[1][axis]) > 1e-9 for n in nos):
        raise ValueError(f"{name}: stair {st['id']} hasn't equal rectangular treads")
    (lo, hi), = ends
    tread, width = treads[0], hi - lo

    stuff = [p for n in nos for p in n] + [[x, y, 0] for side in (st.get("sides") or {}).values() if side != "open"
                                           for x, y in side] + [p for piece in st.get("overhead") or [] for p in piece]
    dx = x_clear - min(p[0] for p in stuff)

    def at(sv, av):                                   # (along the run, across it) -> plan, moved clear
        xy = [0.0, 0.0]
        xy[axis], xy[across] = sv, av
        return [xy[0] + dx, xy[1]]

    first, top = s[0], s[-1]
    mid = (lo + hi) / 2
    foot = [at(first - sign * STRIP, lo), at(first, lo), at(first, hi), at(first - sign * STRIP, hi)]
    head = [at(top, lo), at(top + sign * STRIP, lo), at(top + sign * STRIP, hi), at(top, hi)]
    walls, open_sides = [], []
    guards = [g for g in house.get("guards") or [] if g.get("stair") == st["id"]]
    for side, line in (st.get("sides") or {}).items():
        if line == "open":
            continue
        pts = [[ft(x), ft(y)] for x, y in line]
        if any(all(abs(ft(g["top_line"][0][across]) - p[across]) < 1e-9 for p in pts) for g in guards):
            open_sides.append(side)                   # a guard's inside: a railing, step 5
            continue
        a = pts[0][across]
        if any(abs(p[across] - a) > 1e-9 for p in pts):
            raise ValueError(f"{name}: stair {st['id']}'s {side} side isn't straight along the run")
        out = [0.0, 0.0]
        out[across] = 1.0 if a > mid else -1.0
        span = sorted(p[axis] for p in pts)
        walls.append({"side": side, "face": [at(span[0], a), at(span[-1], a)], "outward": out})
    overhead = [[[x + dx, y, z] for x, y, z in ([ft(v) for v in p] for p in piece)] for piece in st.get("overhead") or []]
    # the floor the flight arrives at, drawn the way a real model has it when the house allows: one floor, its
    # underside an overhead piece of the house (a slab SLAB thick under the head's floor), reaching from that piece
    # past the head, with the stairwell as an opening in it (its edge on the last riser's line) between the piece and
    # the head. House 2: the upper floor over the foot of its stair (9 ft), its top at the head (10 ft).
    upper = None
    under = [pc for pc in overhead if all(abs(p[2] - (zs[-1] - SLAB)) < 1e-9 for p in pc)]
    if len(under) == 1:
        piece = under[0]
        vals = [p[axis] - (dx if axis == 0 else 0) for p in piece]           # along the run, in the house's own frame
        near_s, far = (min(vals), max(vals)) if sign > 0 else (max(vals), min(vals))
        if sign * far < sign * top and sign * near_s <= sign * first:       # over the foot, short of the head
            wide = width / 2 + STAIR_WALL
            upper = {"outer": [at(near_s, mid - wide), at(top + sign * STRIP, mid - wide), at(top + sign * STRIP, mid + wide),
                               at(near_s, mid + wide)],
                     "hole": [at(far, lo), at(top, lo), at(top, hi), at(far, hi)], "top": zs[-1]}
            overhead.remove(piece)
    xs = [p[0] for p in foot + head] + [p[0] for w in walls for p in w["face"]] + [p[0] for pc in overhead for p in pc]
    if upper:
        xs += [p[0] for p in upper["outer"]]
    # each handrail (step 5) as a railing on the stair whose top rail is its handrail (RAIL square, its top HANDRAIL_TOP
    # over the nosings): its plan path RAIL / 2 outward of the house's inner edge, from the first riser to the last
    rails = []
    if handrails:
        for h in st.get("handrails") or []:
            edge = [[ft(x), ft(y)] for x, y in h["inner_edge"]]
            a = edge[0][across]
            if any(abs(p[across] - a) > 1e-9 for p in edge):
                raise ValueError(f"{name}: stair {st['id']}'s {h['side']} handrail isn't straight along the run")
            out_a = a + (RAIL / 2 if a > mid else -RAIL / 2)
            rails.append({"side": h["side"], "inner": [at(first, a), at(top, a)], "path": [at(first, out_a), at(top, out_a)]})
    notes = []
    if extra > 1e-9:
        notes.append(f"stair {st['id']}: a component run's risers are equal, so the {extra * 12:g} in more of its "
                     f"taller riser is drawn at the head (the floor there {extra * 12:g} in above the run's top)")
    return {"id": st["id"], "name": st.get("name") or st["id"], "base": base, "risers": len(risers), "riser": common,
            "tread": tread, "width": width,
            "path": [at(first, mid), at(first + sign * tread * (len(risers) - 1), mid)],
            "head_above_run": extra, "head_top": zs[-1], "foot": {"plan": foot, "top": base},
            "head": None if upper else {"plan": head, "top": zs[-1]}, "upper_floor": upper, "slab": SLAB, "walls": walls, "wall_thickness": STAIR_WALL,
            "wall_top": zs[-1] + HEADROOM_WALL, "open_sides": sorted(open_sides), "overhead": overhead, "handrails": rails,
            "extent": [min(xs), max(xs)]}, notes


def main(argv) -> int:
    if argv[:1] == ["draw"]:
        for name in STEP_HOUSES:
            sys.stdout.write(json.dumps(drawing(name), allow_nan=False) + "\n")
        return 0
    if argv[:1] == ["check"] and len(argv) == 2:
        try:
            rec = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        except ValueError as e:
            sys.stdout.write(json.dumps([f"not JSON ({e})"]) + "\n")
            return 0
        sys.stdout.write(json.dumps(recording_problems(rec)) + "\n")
        return 0
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
