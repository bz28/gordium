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

# Section 7, step 3 (rooms and marked escape windows): the houses drawn, and the measures read. A sleeping room's
# floor area, the floor drawn and the least ceiling height; an escape opening's clear opening, sill height and whether
# it is a door (and a hinged or sliding one). Not in this step: grade-floor (no Toposolid is drawn: no ground), the
# area well, patio cover and projection measures, being in an addition, operable, opening to a yard, fully openable,
# below grade (the measuring code doesn't work these out yet); stairs, doors and guards (later steps).
STEP = 3
STEP_HOUSES = ("1_ranch_compliant", "2_two_story_small_window", "5_basement_window_well")
SCOPE = {
    "sleeping_room": {"sleeping_room_floor_area", "floor_area_drawn", "least_ceiling_height"},
    "emergency_escape_opening": {"opening_net_clear_width", "opening_net_clear_height", "opening_net_clear_area",
                                 "opening_sill_height", "opening_is_door", "opening_door_hinged_or_sliding"},
}
TOL = 1e-6                      # the houses' own tolerance (test_interior_houses: to a millionth)


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
    for kind in SCOPE:
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
    if name not in STEP_HOUSES:
        return [f"{where}: not a house of step {STEP} ({', '.join(STEP_HOUSES)})"]
    problems = []
    if rec.get("step") != STEP:
        problems.append(f"{where}: recorded for step {rec.get('step')}, not step {STEP}")
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
                problems.append(f"{where}: {kind} read ({len(parts)} parts): not in step {STEP}, so it must be left out "
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
                        problems.append(f"{where}: {hid} {m} = {values[m]!r}: not in step {STEP}, so it must be not "
                                        f"measured, never a value")
                elif m in w["values"]:
                    if m not in values:
                        problems.append(f"{where}: {hid} {m} not measured ({p['not_measured'].get(m)}), expected "
                                        f"{w['values'][m]!r}")
                    elif not _same(values[m], w["values"][m]):
                        problems.append(f"{where}: {hid} {m} = {values[m]!r}, expected {w['values'][m]!r}")
                elif m in values:
                    problems.append(f"{where}: {hid} {m} = {values[m]!r}, expected not measured")
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
    drawn yet (refused)."""
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
        levels.setdefault(fe, []).append(room)
    out_levels = []
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
    return {"house": name, "units": "ft", "exterior_wall": EXTERIOR_WALL, "ceiling_thickness": CEILING_THICKNESS,
            "levels": out_levels, "rooms": rooms, "windows": windows,
            "not_drawn": sorted(k for k in ("stairs", "doors", "guards") if house.get(k))}


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
