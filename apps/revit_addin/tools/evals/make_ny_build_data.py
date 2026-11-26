"""Writes the New York eval's build data (the Revit add-in's build_model_request.json reads it: ModelBuild.cs, its
format BuildData.cs) for its two buildings, from the repository's own description files. Nothing is measured off a
drawing and nothing is invented: every value comes from a field of a source file, named in the element's `source`;
what a source doesn't give is left out, or, where Revit can't draw without it, listed under `assumptions` with why
and what it changes.

  - test_data/real_houses/orangetown_ny_80_south_william/revit_build_data.json: the Orangetown house, from its
    layout.yaml (the plans' dimension strings, each wall's own comment its citation) and house.yaml (each room's and
    window's `cite`), through the placing the Revit recording already drew (model_measurement.interior.recordings
    .placed_drawing, checked by layout_problems), so the model is the one the recorded reading came from.
  - test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/revit_build_data.json: 106 Ithaca Rd as the architects'
    spreadsheet describes it (spreadsheet_design.yaml's cells; the same design as spreadsheet_design_model.3dm).
  - test_data/test_sites/new_york/ithaca_city/four_unit_apartment/revit_build_data.json: Gordium's own two-story,
    four-unit eval building for the Building Code of New York State (apartment.yaml: not a real project), with
    `interior_of` (the interior description the Revit reader gives for it, which the Python eval checks).

    python make_ny_build_data.py            # writes both
    python make_ny_build_data.py --check    # says which committed file differs from a fresh one (exit 1), writes none
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
ORANGETOWN = "orangetown_ny_80_south_william"
HOUSE_DIR = REPO / "test_data/real_houses" / ORANGETOWN
SITE_DIR = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
APARTMENT_DIR = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment"
OUT = {"orangetown": HOUSE_DIR / "revit_build_data.json", "106_ithaca_rd": SITE_DIR / "revit_build_data.json",
       "four_unit_apartment": APARTMENT_DIR / "revit_build_data.json"}
TOOL = "apps/revit_addin/tools/evals/make_ny_build_data.py"
LEVEL_NAMES = {"second_floor": "Second floor", "main_floor": "Main floor", "basement": "Basement"}


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix() if p.is_relative_to(REPO) else p.as_posix()


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _r(v: float) -> float:
    """Feet to a millionth (the drawing's own numbers are inches over 12: kept exact to far below Revit's tolerance)."""
    return round(v, 9)


def _ring(points) -> list:
    pts = [[_r(x), _r(y)] for x, y in points]
    return pts + [pts[0]]


def layout_comments(text: str) -> dict:
    """Each wall's own comment in layout.yaml (its citation: the dimension string it comes from), by (level id, wall
    name). YAML drops comments, so they are read from the text: a level opens with `  - id: <level>`, its walls are
    the lines `      <name>: [x0, d0, x1, d1]  # <comment>` under `    walls:`."""
    out, level, in_walls = {}, None, False
    for line in text.splitlines():
        if m := re.match(r"^  - id: (\w+)\s*$", line):
            level, in_walls = m.group(1), False
        elif re.match(r"^    walls:\s*$", line):
            in_walls = True
        elif re.match(r"^    \w", line):
            in_walls = False
        elif in_walls and (m := re.match(r"^      (\w+): \[[^\]]*\]\s*#\s*(.*\S)\s*$", line)):
            out[(level, m.group(1))] = m.group(2)
    return out


# the header paragraph of layout.yaml that gives each level's chains: a wall with no comment of its own is cited by it
HEADERS = {"second_floor": "# The chains (A-3", "main_floor": "# A-2 main floor:", "basement": "# A-2 basement:"}


def layout_headers(text: str) -> dict:
    """Each level's header paragraph in layout.yaml (its dimension chains), by level id: the line HEADERS names and
    the lines continuing it (indented under it)."""
    lines, out = text.splitlines(), {}
    for level, start in HEADERS.items():
        k = next(i for i, line in enumerate(lines) if line.startswith(start))
        para = [lines[k][2:].strip()]
        for line in lines[k + 1:]:
            if not line.startswith("#   "):
                break
            para.append(line[1:].strip())
        out[level] = " ".join(para)
    return out


def on_outline(rect, outline) -> bool:
    """Whether a wall (its plan rectangle's two corners, feet) has a face on the level's outer outline: an exterior
    wall, decided from where it stands, never from its comment's wording."""
    from shapely.geometry import Polygon, box

    (x0, y0), (x1, y1) = rect
    shared = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)).boundary.intersection(Polygon(outline).exterior)
    return shared.length > 1e-6


def orangetown() -> dict:
    from model_measurement.interior import recordings

    layout_file, house_file = HOUSE_DIR / "layout.yaml", HOUSE_DIR / "house.yaml"
    lay = yaml.safe_load(layout_file.read_text(encoding="utf-8"))
    house = yaml.safe_load(house_file.read_text(encoding="utf-8"))
    comments = layout_comments(layout_file.read_text(encoding="utf-8"))
    headers = layout_headers(layout_file.read_text(encoding="utf-8"))
    drawn = recordings.placed_drawing(ORANGETOWN)          # refused if layout_problems finds anything
    by_elev = {lv["elevation"]: lv for lv in drawn["levels"]}
    lay_levels = {recordings._ft("in")(lv["elevation"]): lv for lv in lay["levels"]}
    house_rooms = {r["id"]: r for r in house["rooms"]}
    house_open = {o["id"]: o for o in house.get("openings") or []}
    house_doors = {d["id"]: d for d in house.get("doors") or []}

    levels, walls, windows, doors, rooms, floors, ceilings, separations = [], [], [], [], [], [], [], []
    wall_ids = {}                                        # (elevation, index in the level) -> wall id
    for z, lv in sorted(by_elev.items(), reverse=True):
        src = lay_levels[z]
        name = LEVEL_NAMES[src["id"]]
        levels.append({"name": name, "elevation_ft": _r(z),
                       "source": f"layout.yaml levels[{src['id']}].elevation: {src['cite']['elevation']}"})
        for k, ((x0, y0), (x1, y1)) in enumerate(lv["walls"]):
            wall_name = list(src["walls"])[k]
            comment = comments.get((src["id"], wall_name))
            cited = comment or f"no comment of its own; the level's chains (layout.yaml header): {headers[src['id']]}"
            along_x = x1 - x0 >= y1 - y0                 # as HouseDraw draws a layout wall: along its longer side
            start, end = ([x0, (y0 + y1) / 2], [x1, (y0 + y1) / 2]) if along_x else ([(x0 + x1) / 2, y0], [(x0 + x1) / 2, y1])
            wid = len(walls) + 1
            wall_ids[(z, k)] = wid
            walls.append({"id": wid, "level": name, "start": [_r(v) for v in start], "end": [_r(v) for v in end],
                          "thickness_in": _r((y1 - y0 if along_x else x1 - x0) * 12), "status": "New",
                          "smoke_partition": False, "fire_rating": None, "height_ft": _r(lv["wall_height"]),
                          "exterior": on_outline(((x0, y0), (x1, y1)), lv["outline"]),
                          "source": f"layout.yaml levels[{src['id']}].walls.{wall_name} {src['walls'][wall_name]} (in): "
                                    f"{cited}; its height to the top of the level's ceilings (placed_drawing); "
                                    "exterior when a face of it lies on the level's outline (its walls and rooms together)"})
        floors.append({"level": name, "outline": _ring(lv["outline"]), "thickness_in": _r(lv["slab"] * 12),
                       "source": f"layout.yaml levels[{src['id']}]: the level's walls and rooms together; its thickness "
                                 + (f"layout.yaml levels[{src['id']}].slab: {src['cite']['slab']}" if "slab" in src else
                                    "the gap the layout leaves between the ceiling below and this floor (layout.yaml "
                                    "assumptions: 'Each floor slab drawn as thick as the gap the layout leaves under it')")})
        for (a, b) in lv["separations"]:
            separations.append({"level": name, "start": [_r(v) for v in a], "end": [_r(v) for v in b],
                                "source": f"layout.yaml levels[{src['id']}].separations (the assumption 'Bedroom 2's "
                                          "entry alcove ... a room separation line between it and the bedroom')"})
    room_level = {r["id"]: lv["id"] for lv in lay["levels"] for r in lv["rooms"]}
    lay_by_id = {lv["id"]: lv for lv in lay["levels"]}
    for n, r in enumerate(drawn["rooms"], start=1):
        lid = room_level[r["id"]]
        given = house_rooms.get(r["id"])
        if given is not None:
            why = f"house.yaml rooms[{r['id']}]: name and sleeping; " + (
                f"its floor {given['cite']['floor']}" if "floor" in given.get("cite", {}) else
                f"its floor is layout.yaml's (house.yaml: {given.get('absent', {}).get('floor', 'no floor given')})")
        else:
            why = f"layout.yaml levels[{lid}].rooms[{r['id']}]: its name and sleeping are the layout's own"
        floor = r["floor"]
        room = {"number": str(n), "name": r["name"], "level": LEVEL_NAMES[lid], "tag_point": [_r(v) for v in r["point"]],
                "boundary": _ring(floor), "sleeping": r["sleeping"], "house_id": r["id"],
                "source": f"{why}; placed by layout.yaml levels[{lid}].rooms[{r['id']}].floor"}
        if given is not None and "floor" in given:
            xs, ys = [p[0] for p in given["floor"]], [p[1] for p in given["floor"]]
            room["area_sf"] = _r((max(xs) - min(xs)) * (max(ys) - min(ys)) / 144)
        rooms.append(room)
        for piece in r["ceilings"]:
            ceilings.append({"name": r["name"], "outline": _ring([p[:2] for p in piece]), "underside_ft": _r(piece[0][2]),
                             "thickness_in": _r(drawn["ceiling_thickness"] * 12),
                             "source": f"layout.yaml levels[{lid}].ceiling: {lay_by_id[lid]['cite']['ceiling']}"
                                       " (a thin solid whose underside is the ceiling, as the Revit recording drew it)"})
    sizes = lay["sizes"]
    lay_windows = {w["id"]: w for lv in lay["levels"] for w in lv.get("windows") or []}
    for w in drawn["windows"]:
        p, o = lay_windows[w["id"]], house_open[w["id"]]
        size = sizes[p["size"]]
        windows.append({"center": [_r(v) for v in w["at"]], "width_in": _r(w["width"] * 12), "height_in": _r(w["height"] * 12),
                        "sill_in": _r(w["sill"] * 12), "host_wall": wall_ids[(w["level"], w["wall"])],
                        "house_id": w["id"], "escape": o["escape"], "operation": o["operation"],
                        "source": f"layout.yaml windows[{w['id']}]: {p['cite']}; size {p['size']}: {size['cite']}"
                                  + (" (ASSUMED: layout.yaml sizes)" if size.get("assumed") else "")
                                  + f"; sill: layout.yaml head {lay['head']} in (A-1 header note) less its height; "
                                    f"house.yaml openings[{w['id']}]: escape {o['cite'].get('escape', '(see house.yaml)')}"})
    lay_doors = {d["id"]: d for lv in lay["levels"] for d in lv.get("doors") or []}
    for d in drawn["doors"]:
        p, given = lay_doors[d["id"]], house_doors[d["id"]]
        doors.append({"center": [_r(v) for v in d["at"]], "width_in": _r(d["width"] * 12), "height_in": _r(d["height"] * 12),
                      "kind": "single", "host_wall": wall_ids[(d["level"], d["wall"])], "house_id": d["id"],
                      "exit": given["exit"], "operation": given["operation"],
                      "source": f"layout.yaml doors[{d['id']}]: {p['cite']}; house.yaml doors[{d['id']}]: exit "
                                f"{given['cite']['exit']}; operation {given['cite']['operation']}. No swing_dir or hinge: "
                                f"house.yaml absent.hinge_side ({given['absent']['hinge_side']})"})
    xs = [x for f in floors for x, _ in f["outline"]]
    ys = [y for f in floors for _, y in f["outline"]]
    lot = [[min(xs) - 20, min(ys) - 30], [max(xs) + 20, min(ys) - 30], [max(xs) + 20, max(ys) + 30], [min(xs) - 20, max(ys) + 30]]
    return {
        "project": "80 South William Street (Lot 2), Orangetown NY: the house as layout.yaml places it (the NY Revit eval)",
        "units": "feet", "type_suffix": "Orangetown A-1 to A-5", "levels": levels, "walls": walls, "doors": doors,
        "windows": windows, "rooms": rooms, "floors": floors, "ceilings": ceilings, "separations": separations,
        "lot": {"outline": _ring(lot),
                "source": "EVAL STAND-IN, not from the drawings: a rectangle 20 ft clear of the house's sides and 30 ft "
                          "front and back. Check my project sends nothing without a property line and a street edge "
                          "(ProjectFacts), and the repository has no survey of Lot 2. Every zoning row of the check is "
                          "Ithaca's, which doesn't apply in Orangetown, and is left out of the comparison; no egress "
                          "rule reads the lot (egress.check reads the interior and the dwelling units only)"},
        "plan": "x east from the house's west outer face, y north from its south-most face (the garage front), feet "
                "(layout.yaml's x, and d turned: y = (508 in - d) / 12); z 0 the second floor's finished floor",
        "made_from": {"tool": TOOL, "sources": [{"file": _rel(f), "sha256": _sha(f)} for f in (layout_file, house_file)]},
        "not_drawn": {
            "stairs": "house.yaml has no stairs: 'No floor-to-floor height is dimensioned, so no riser height or nosing "
                      "elevation can be placed, and no tread depth is dimensioned' (layout.yaml not_drawn.stairs places "
                      "them only). Every stair rule stays needs review (evaluation.md, why D)",
            "guards": "house.yaml's 5 railings have no members ('drawn ... but not dimensioned', absent.members): not "
                      "drawn (layout.yaml not_drawn.guards). The guard rules read open sides, which nothing produces yet "
                      "(evaluation.md, why G), so drawing them would change no verdict",
            "interior doors, sliders, garage doors, main-floor partitions": "layout.yaml assumptions: house.yaml "
                      "describes only the front door and the marked escape windows; a drawn door is read as a door"},
        "assumptions": [dict(a) for a in lay["assumptions"]] + [
            {"what": "The lot (a stand-in rectangle) and its south edge as the street",
             "why": "Check my project needs a property line and a street edge to send anything",
             "effect": "none on egress; the Ithaca zoning rows it brings are left out of the comparison"},
            {"what": "Every wall drawn 'New', no smoke partition, no fire rating (the build data's own fields)",
             "why": "the data format needs them; the drawings' house is new construction (A-1 'PROPOSED')",
             "effect": "none: no rule reads a wall's phase or rating"}],
        "stats": {"walls": len(walls), "doors": len(doors), "windows": len(windows), "rooms": len(rooms)},
    }


def ithaca_rd() -> dict:
    """The spreadsheet's design (spreadsheet_design.yaml, the cells it names; the same box as
    packages/model_measurement/tests/make_spreadsheet_model.py): a 73 x 90 ft lot, the street on its 73 ft side, and a
    53 x 35 ft, 35 ft tall house 10 ft from its left side and 30 ft from the street."""
    design_file, facts_file = SITE_DIR / "spreadsheet_design.yaml", SITE_DIR / "spreadsheet_design_model_facts.yaml"
    design = yaml.safe_load(design_file.read_text(encoding="utf-8"))
    m = {k: v["value"] for k, v in design["measurements"].items()}
    cell = {k: v["from"] for k, v in design["measurements"].items()}
    facts = yaml.safe_load(facts_file.read_text(encoding="utf-8"))["lot_facts"]
    width, depth, height = m["lot_width"], m["lot_depth"], m["building_height"]
    left, front = m["side_yard_smaller"], m["front_yard"]
    house_w = m["lot_width"] - m["side_yard_smaller"] - m["side_yard_larger"]       # Inputs!B6
    house_d = m["lot_depth"] - m["front_yard"] - m["rear_yard"]                     # Inputs!B7
    assert house_w * house_d == m["building_area"], "the spreadsheet's footprint is its width times its depth (B10)"
    x0, y0, x1, y1 = left, front, left + house_w, front + house_d
    t = 0.5                                       # ft: an assumed 6 in wall; its outer face on the house's outline
    h = t / 2
    centre = [(x0 + h, y0 + h), (x1 - h, y0 + h), (x1 - h, y1 - h), (x0 + h, y1 - h)]
    sides = ["south (on the street side)", "east (right)", "north (rear)", "west (left)"]
    walls = [{"id": k + 1, "level": "Level 1", "start": list(centre[k]), "end": list(centre[(k + 1) % 4]),
              "thickness_in": t * 12, "status": "New", "smoke_partition": False, "fire_rating": None, "height_ft": height,
              "exterior": True,
              "source": f"the house's {sides[k]} wall: its outer face on the spreadsheet's outline, x {x0:g} to {x1:g}, "
                        f"y {y0:g} to {y1:g} (left offset {cell['side_yard_smaller']}, front offset "
                        f"{cell['front_yard']}; width {house_w:g} and depth {house_d:g}, Inputs!B6 and B7, as "
                        f"spreadsheet_design.yaml works them into side_yard_larger ({cell['side_yard_larger']}) and "
                        f"rear_yard ({cell['rear_yard']})); height {cell['building_height']}; "
                        "thickness ASSUMED (assumptions)"} for k in range(4)]
    outer = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    spots = [((x0 + x1) / 2, y0 - 1), (x1 + 1, (y0 + y1) / 2), ((x0 + x1) / 2, y1 + 1), (x0 - 1, (y0 + y1) / 2)]
    return {
        "project": "106 Ithaca Rd: the architects' spreadsheet design (R-1b), the NY Revit eval",
        "units": "feet", "type_suffix": "106 Ithaca Rd spreadsheet",
        "levels": [{"name": "Level 1", "elevation_ft": facts["grade_elevation"],
                    "source": f"{_rel(facts_file)} lot_facts.grade_elevation ({facts['grade_elevation']}: the house "
                              "sits on the flat ground)"},
                   {"name": "Roof", "elevation_ft": height, "source": f"the roof's top: building_height {cell['building_height']}"}],
        "walls": walls, "doors": [], "windows": [], "rooms": [],
        "floors": [{"level": "Roof", "outline": _ring(outer), "thickness_in": 12.0,
                    "source": f"the flat roof (spreadsheet_design.yaml: 'The spreadsheet's house is a box with no "
                              f"eaves'), its top at {cell['building_height']}, over the house's outline; thickness "
                              "ASSUMED (assumptions)"}],
        "lot": {"outline": _ring([(0, 0), (width, 0), (width, depth), (0, depth)]),
                "source": f"a {width:g} x {depth:g} ft rectangle: lot_width {cell['lot_width']}, lot_depth "
                          f"{cell['lot_depth']} (Inputs!B3 says 'rectangular'); its edge y = 0 is the street "
                          f"({_rel(facts_file)} street_line {facts['street_line']}). Its area is 6,570 sf, not the "
                          f"spreadsheet's typed {m['lot_area']} ({cell['lot_area']}): docs/discrepancies_with_architects.md 2.5"},
        "spot_grades": [{"at": [_r(x), _r(y), facts["grade_elevation"]],
                         "source": f"the flat ground at {facts['grade_elevation']} ({_rel(facts_file)} lot_facts."
                                   "ground_is_flat, grade_elevation), marked 1 ft outside the middle of each wall "
                                   "(the reader takes a wall's spot grade within 2 ft of it)"} for x, y in spots],
        "plan": "x east along the street from the lot's left (west) corner, y north from the street, feet",
        "made_from": {"tool": TOOL, "sources": [{"file": _rel(f), "sha256": _sha(f)} for f in (design_file, facts_file)]},
        "not_drawn": {
            "rooms, doors and windows": "the spreadsheet describes the house as a box (its footprint, height and "
                                        "stories): no interior, so egress waits ('no rooms drawn yet') and is not "
                                        "part of this eval",
            "floors between the stories": "the spreadsheet gives 3 stories (Inputs!B13) but no floor heights; Revit's "
                                          "Check my project doesn't count native floors as stories (only Gordium's "
                                          "floor blocks or a stated count, places/ithaca_city/measure.py _stories), "
                                          "so drawing them would invent heights and change nothing"},
        "assumptions": [
            {"what": "The walls 6 in thick, their outer faces on the spreadsheet's 53 x 35 ft outline",
             "why": "the spreadsheet gives the house's outside size only",
             "effect": "none: coverage, the yards and the height are measured to the outer faces and the top"},
            {"what": "The roof a 12 in flat slab (a Revit floor) whose top is the 35 ft height",
             "why": "the spreadsheet's house is a box; a roof's thickness isn't given",
             "effect": "none: the height is measured to the top"},
            {"what": "The flat ground drawn as four spot grades at 0, 1 ft outside each wall",
             "why": "the Revit reader reads the ground only from spot-grade markers (Gordium: Ground from); "
                    "spreadsheet_design_model_facts.yaml states the ground flat at 0",
             "effect": "none: every marker is at 0"}],
        "stats": {"walls": 4, "doors": 0, "windows": 0, "rooms": 0},
    }


def _apartment_source() -> tuple[Path, dict]:
    f = APARTMENT_DIR / "apartment.yaml"
    return f, yaml.safe_load(f.read_text(encoding="utf-8"))


def _rect(r) -> list:
    x0, y0, x1, y1 = r
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def apartment() -> dict:
    """The eval building as apartment.yaml gives it, every value from a field of it: per level the four exterior
    walls (their outside faces on the outline), the partitions, the doors (Level 1 also the two discharge doors), the
    rooms at their middles, a floor slab under each level and the roof over Level 2."""
    f, a = _apartment_source()
    x0, y0, x1, y1 = a["inside"]
    t, h = a["wall"], a["story_height"]
    c = t / 2
    outer = _rect([x0 - t, y0 - t, x1 + t, y1 + t])
    levels, walls, doors, rooms, floors = [], [], [], [], []
    for lv in a["levels"]:
        name = lv["name"]
        levels.append({"name": name, "elevation_ft": _r(lv["elevation"]), "source": f"apartment.yaml levels[{lv['id']}]"})
        ids = {}
        ext = {"south": ((x0 - t, y0 - c), (x1 + t, y0 - c)), "east": ((x1 + c, y0 - t), (x1 + c, y1 + t)),
               "north": ((x1 + t, y1 + c), (x0 - t, y1 + c)), "west": ((x0 - c, y1 + t), (x0 - c, y0 - t))}
        for side, (s, e) in ext.items():
            ids[side] = len(walls) + 1
            walls.append({"id": ids[side], "level": name, "start": [_r(v) for v in s], "end": [_r(v) for v in e],
                          "thickness_in": _r(t * 12), "status": "New", "smoke_partition": False, "fire_rating": None,
                          "height_ft": _r(h), "exterior": True,
                          "source": f"apartment.yaml: the {side} exterior wall, its inside face on `inside` {a['inside']}, "
                                    f"{t * 12:g} in thick (`wall`), {h:g} ft tall (`story_height`)"})
        for w in a["partitions"]:
            ids[w["name"]] = len(walls) + 1
            walls.append({"id": ids[w["name"]], "level": name, "start": [_r(v) for v in w["start"]],
                          "end": [_r(v) for v in w["end"]], "thickness_in": _r(t * 12), "status": "New",
                          "smoke_partition": False, "fire_rating": None, "height_ft": _r(h), "exterior": False,
                          "source": f"apartment.yaml partitions[{w['name']}]"})
        for d in a["doors"] + (a["discharge_doors"] if lv["elevation"] == a["levels"][0]["elevation"] else []):
            doors.append({"center": [_r(v) for v in d["at"]], "width_in": _r(a["door"]["leaf_in"]),
                          "height_in": _r(a["door"]["height_in"]), "kind": "single",
                          "host_wall": ids[d["wall"]], "house_id": f"{lv['id']}{d['id']}", "exit": False,
                          "operation": "side_hinged",
                          "source": f"apartment.yaml doors[{d['id']}] on {name}, its leaf apartment.yaml door"})
        for r in a["rooms"]:
            rx0, ry0, rx1, ry1 = r["rect"]
            rooms.append({"number": str(len(rooms) + 1), "name": f"{r['name']} {lv['id']}", "level": name,
                          "tag_point": [_r((rx0 + rx1) / 2), _r((ry0 + ry1) / 2)], "boundary": _ring(_rect(r["rect"])),
                          "sleeping": False, "house_id": f"{lv['id']}{r['id']}",
                          "area_sf": _r((rx1 - rx0) * (ry1 - ry0)),
                          "source": f"apartment.yaml rooms[{r['id']}] on {name}"})
        floors.append({"level": name, "outline": _ring(outer), "thickness_in": 12.0,
                       "source": "apartment.yaml: a 12 in slab under the level over the outside of the walls (ASSUMED "
                                 "thickness: assumptions)"})
    top = a["levels"][-1]
    floors.append({"level": top["name"], "outline": _ring(outer), "thickness_in": 12.0, "top_offset_ft": _r(h),
                   "source": "the flat roof over Level 2, its top at the walls' top (ASSUMED thickness: assumptions)"})
    lx0, ly0, lx1, ly1 = a["lot"]
    spots = [((x0 + x1) / 2, y0 - t - 1), (x1 + t + 1, (y0 + y1) / 2), ((x0 + x1) / 2, y1 + t + 1),
             (x0 - t - 1, (y0 + y1) / 2)]
    return {
        "project": "Four-unit apartment building (Gordium's eval building for the NY Building Code, not a real project)",
        "units": "feet", "type_suffix": "NY four-unit eval", "levels": levels, "walls": walls, "doors": doors,
        "windows": [], "rooms": rooms, "floors": floors,
        "lot": {"outline": _ring(_rect(a["lot"])),
                "source": f"apartment.yaml lot {a['lot']}: a stand-in, its south edge (y = {ly0:g}) the street"},
        "spot_grades": [{"at": [_r(x), _r(y), a["ground"]], "source": "apartment.yaml ground: flat, 1 ft outside each "
                                                                      "wall's middle"} for x, y in spots],
        "plan": "x east, y north from the inside face of the south wall, feet",
        "made_from": {"tool": TOOL, "sources": [{"file": _rel(f), "sha256": _sha(f)}]},
        "not_drawn": {"stairs": "the two exit stair enclosures are drawn as rooms only: no Building Code rule here reads a "
                                "stair's risers or treads, and the residential stair rules don't run (the Building Code "
                                "governs)",
                      "windows": "no rule checked reads a window (the Building Code's escape-window sections aren't "
                                 "brought in)",
                      "apartment interiors": "each apartment is one room: the rules checked read the routes from its "
                                             "door, and its own rooms would only lengthen the travel figures, about "
                                             "54 ft against Table 1017.2's 200 ft for Group R-2 (expected.yaml)"},
        "assumptions": [
            {"what": "The slabs and the roof 12 in thick", "why": "the eval building has none given",
             "effect": "none: no rule reads a slab's thickness"},
            {"what": "Every door a 36 x 84 in single leaf, 34 in clear, 80 in high, no swing side",
             "why": "the eval building's doors (apartment.yaml door; no maker named)",
             "effect": "none on the verdicts: the routes pass each door's 34 in clear opening (over the 24 in they need), "
                       "and the exits' separation is measured between the openings' nearest points across the corridor's "
                       "length, which the opening's width along its wall doesn't change"}],
        "stats": {"walls": len(walls), "doors": len(doors), "windows": 0, "rooms": len(rooms)},
    }


def interior_of() -> dict:
    """The interior description the Revit reader gives for the eval building once marked (eval_marks.yaml): its
    levels, rooms (inside the walls, with the route marks), doors (each clear opening's plan, the rooms either side,
    the exits) and each story's outline (the outside and inside faces of its exterior walls), in apartment.yaml's
    plan; the building block from the Project Information marks. What the Python eval checks
    (packages/design_checker/tests/test_four_unit_apartment.py)."""
    _, a = _apartment_source()
    x0, y0, x1, y1 = a["inside"]
    t = a["wall"]
    words = {"Other": "other", "Corridor": "corridor", "Exit stair enclosure": "exit_enclosure",
             "Exterior door at discharge": "exterior_at_discharge"}
    rooms, doors = [], []
    for lv in a["levels"]:
        L = lv["id"]
        for r in a["rooms"]:
            rooms.append({"id": f"{L}{r['id']}", "name": f"{r['name']} {L}", "sleeping": False, "level": L,
                          "floor": [list(p) for p in _rect(r["rect"])], "floor_elevation": lv["elevation"],
                          "ceiling_height": a["story_height"] - 1, "use": words[r["use"]], "lockable": r["lockable"],
                          "pass_through": r["pass_through"], "holes": [], "obstructions": [],
                          **({"function": r["function"]} if "function" in r else {})})
        for d in a["doors"] + (a["discharge_doors"] if lv is a["levels"][0] else []):
            door = {"id": f"{L}{d['id']}", "name": f"{d['name']} {L}", "exit": False, "level": L,
                    # the type's Gordium: Operation as eval_marks.yaml door_types sets it (Side-hinged door), sent
                    # as the Revit reader sends it (section group 6b: 1010.1.2's door kind)
                    "operation": "side_hinged",
                    # the type's clear opening as eval_marks.yaml door_types stamps it: the reader sends a door's
                    # plan (its clear opening) only from that confirmed width, never the leaf's
                    "stated_clear": {"width": a["door"]["clear_width_in"] / 12, "height": a["door"]["clear_height_in"] / 12,
                                     "source": "eval_marks.yaml door_types (an eval assumption: no maker named)"},
                    "plan": {"centre": list(d["at"]), "along": list(d["along"]),
                             "clear_width": a["door"]["clear_width_in"] / 12, "wall_thickness": t},
                    "sides": [s if s == "outside" else f"{L}{s}" for s in d["sides"]]}
            if "exit" in d:
                # the enclosure's room on this story (RouteReader.ExitId: the room every door of which is the exit's)
                door["exit_kind"], door["exit_id"] = words[d["exit"]], f"{L}{d['sides'][1]}"
            doors.append(door)
    return {"format": "gordium.interior/1", "units": "ft",
            "levels": [{"id": lv["id"], "name": lv["name"], "elevation": lv["elevation"]} for lv in a["levels"]],
            # every level of the model (RouteReader.cs all_levels): the building has only its two
            "all_levels": [{"id": lv["id"], "name": lv["name"], "elevation": lv["elevation"]} for lv in a["levels"]],
            "rooms": rooms, "doors": doors, "passages": [],
            "story_outlines": [{"level": lv["id"], "outer": [list(p) for p in _rect([x0 - t, y0 - t, x1 + t, y1 + t])],
                                "inner": [list(p) for p in _rect(a["inside"])]} for lv in a["levels"]],
            "building": dict(a["building"])}


def made() -> dict:
    return {"orangetown": orangetown(), "106_ithaca_rd": ithaca_rd(), "four_unit_apartment": apartment()}


def text(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    fresh = made()
    if argv == ["--check"]:
        stale = [_rel(OUT[k]) for k, d in fresh.items()
                 if not OUT[k].exists() or OUT[k].read_text(encoding="utf-8") != text(d)]
        for s in stale:
            print(f"{s} differs from a fresh build: run {TOOL}")
        return 1 if stale else 0
    for k, d in fresh.items():
        OUT[k].write_text(text(d), encoding="utf-8", newline="\n")
        print(f"wrote {_rel(OUT[k])}: {d['stats']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
