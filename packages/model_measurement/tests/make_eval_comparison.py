"""The route eval on the Children's Odyssey day care (docs/decisions/2026-11-20_route_measurement.md, "The eval"):
each figure sheet LS1.0 measured, set beside Gordium's from the same start to the same exit, with and without the
12-in clearance. Writes test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml (numbers only).

    python make_eval_comparison.py <the model's interior description .json>

The sheet stays outside the repo (open question 5), so its drawn lines are literals here, measured once on the
sheet's vector drawing (pdfplumber, 2026-11-21): the sheet is 1/8 in = 1 ft, 9 pt a foot. Its points are put in
the model's coordinates (feet) by two walls both show: the west outer face (sheet x 302.58 pt, model x 0) and the
north outer face (sheet y 539.10 pt, model y 85.4833); the two exits' inner faces then fall within 0.01 ft of the
model's (5.494 and 189.200), a check on the match. Gordium's figures are worked by the route code from the model."""

import json
import math
import sys
from pathlib import Path

import yaml

FT = 12.0
OUT = Path(__file__).resolve().parents[3] / "test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml"
PT_PER_FT = 9.0                      # 1/8 in = 1 ft at 72 pt an inch
WEST_FACE_PT, NORTH_FACE_PT, NORTH_FACE_FT = 302.58, 539.10, 85.4833
EAST_EXIT = "90a6a430-1684-4046-81c7-ffbf1c99b587-0005bcac"      # D12, centred (189.53, 42.82)


def model(p):
    """A sheet point (pt, y down) in the model's coordinates (ft, y up)."""
    return round((p[0] - WEST_FACE_PT) / PT_PER_FT, 3), round(NORTH_FACE_FT - (p[1] - NORTH_FACE_PT) / PT_PER_FT, 3)


def drawn(points):
    return round(sum(math.dist(a, b) for a, b in zip(points, points[1:])) / PT_PER_FT, 3)


SHEET = {   # the sheet's stated figure, and the line it draws for it (vertices in sheet points)
    "travel_distance": {"stated": 130.667, "words": "MAXIMUM TRAVEL DISTANCE TO EXIT = 130'-8\"",
                        "line": [(1552.74, 548.04), (1460.22, 761.58), (1347.42, 761.58), (1347.42, 927.96),
                                 (2008.44, 927.96)]},
    "common_path": {"stated": 48.5, "words": "DISTANCE TO COMMON PATH OF TRAVEL = 48'-6\"",
                    "line": [(1556.46, 549.66), (1462.86, 765.6), (1359.36, 765.6), (1359.36, 862.38)]},
    "dead_end": {"stated": 21.5, "words": "DEAD END CORRIDOR DISTANCE = 21'-6\"",
                 "line": [(1672.68, 636.48), (1672.68, 829.86)]},
    "remoteness": {"stated": 183.833, "words": "PROVIDED REMOTENESS: 183'-10\" (between its ticks)",
                   "line": [(352.02, 944.28), (2005.44, 944.28)]},
    "diagonal": {"stated": 210.208, "words": "BLDG DIA. 210'-2 1/2\" (between its ticks)",
                 "line": [(2029.9, 511.7), (294.0, 1261.2)]},
}


def main(path):
    from model_measurement.routes import areas, straight
    from model_measurement.routes.common_path import at_point
    from model_measurement.routes.floor import read
    from model_measurement.routes.paths import StoryRoutes
    description = json.loads(Path(path).read_text(encoding="utf-8"))
    story = next(iter(read(description).stories.values()))
    uses = {r["id"]: r.get("use") for r in description["rooms"]}
    room11 = next(r for r in story.rooms.values() if r is not None and r.name == "STORAGE (11)")
    corner = max(room11.outline.exterior.coords, key=lambda c: c[0] + c[1])      # its north-east corner
    out = {"made_by": "packages/model_measurement/tests/make_eval_comparison.py", "units": "ft, sf",
           "sheet_to_model": {"west_outer_face_pt": WEST_FACE_PT, "north_outer_face_pt": NORTH_FACE_PT,
                              "north_outer_face_ft": NORTH_FACE_FT, "pt_per_ft": PT_PER_FT}, "figures": {}}
    for name, s in SHEET.items():
        out["figures"][name] = {"sheet_stated": s["stated"], "sheet_words": s["words"],
                                "sheet_line_as_drawn": drawn(s["line"]),
                                "sheet_line_in_model": [list(model(p)) for p in s["line"]]}
    gordium = {}
    for r in (12.0, 0.0):
        routes = StoryRoutes(story, r)
        to_east = routes.route(corner, [EAST_EXIT])
        nearest = routes.route(corner)
        common = at_point(routes, corner)
        gordium[r] = (to_east.length / FT, nearest.length / FT, common.length / FT)
    start = [round(corner[0] / FT, 3), round(corner[1] / FT, 3)]
    out["figures"]["travel_distance"]["gordium"] = {
        "from": list(start), "from_room": "STORAGE (11), its north-east corner (the sheet's start)",
        "to_the_sheets_exit_with_12_in": round(gordium[12.0][0], 3), "to_the_sheets_exit_no_clearance":
            round(gordium[0.0][0], 3), "to_the_nearest_exit_with_12_in": round(gordium[12.0][1], 3),
        "story_verdict": "needs review: 5 rooms have no route (decision 1a)",
        "why_different": "the sheet's line turns at right angles and runs the corridor's centre line to the east exit; "
                         "Gordium's is the shortest walk to the same exit (its nearest exit is the north door)"}
    out["figures"]["common_path"]["gordium"] = {
        "from": list(start), "with_12_in": round(gordium[12.0][2], 3), "no_clearance": round(gordium[0.0][2], 3),
        "why_different": "the sheet's line turns at right angles to the room's door; Gordium's routes to the north "
                         "and east exits share the walk to and past that door, not the right-angle path"}
    west = next(d for d in story.exits() if abs(d.centre[0] / FT - 4.99) < 0.05 and abs(d.centre[1] / FT - 42.82) < 0.05)
    east = next(d for d in story.exits() if d.exit_id == EAST_EXIT)
    pair = straight.opening(west).distance(straight.opening(east)) / FT
    far, across, ratio = straight.ratio(story)
    out["figures"]["remoteness"]["gordium"] = {
        "same_pair_nearest_edges": round(pair, 3), "farthest_pair_nearest_edges": round(far.length / FT, 3),
        "farthest_pair_door_centres": round(far.centres / FT, 3),
        "why_different": "the sheet measures the west and east corridor exits (Gordium's same pair agrees); "
                         "Gordium's figure is the farthest-apart pair (decision 7), the north-west and east doors"}
    out["figures"]["diagonal"]["gordium"] = {
        "corner_to_corner": round(across.length / FT, 3), "ends": [[round(v / FT, 3) for v in p] for p in across.corners],
        "ratio": round(ratio, 4),
        "why_different": "the sheet's ticks are not at the traced outer outline's corners (its north-east tick lies "
                         "about 3 ft north of the traced north face): a trace or a drawing difference, not settled"}
    out["figures"]["dead_end"]["gordium"] = {
        "measured": None, "why": "the corridor isn't straight legs at right angles: not measured (decision 6)",
        "by_hand_centre_line_reading": round(74.85 - (37.844 + 47.833) / 2, 3),
        "why_different": "the sheet ends the stub's dead end at the widening's near edge (y 53.17); decision 6 "
                         "measures to the crossing corridor's centre line (y 42.84), open question 2"}
    acc = areas.accessory_area(story, uses)
    out["storage"] = {"sheet_stated_sf": 1428, "sheet_story_sf": 16509, "story_sf_correct": 16539,
                      "gordium_inside_sf": round(acc[0].value / FT / FT, 1),
                      "gordium_outer_faces_sf": round(acc[1].value / FT / FT, 1),
                      "gordium_story_sf": [round(x.value / FT / FT, 1) for x in areas.building_area(story)],
                      "rooms": {r.name: round(r.outline.area / FT / FT, 1) for r in story.rooms.values()
                                if r is not None and uses.get(r.id) == "accessory_storage"},
                      "why_different": "the sheet doesn't list its rooms; over the five rooms marked accessory "
                                       "storage, Gordium's outer-faces reading is within 1 percent of the sheet's, "
                                       "its inside reading 17 percent under: the sheet likely measured to the walls' "
                                       "outer faces (open question 3)"}
    OUT.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main(sys.argv[1])
