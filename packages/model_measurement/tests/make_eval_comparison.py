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


CO = {"start_room": "STORAGE (11)", "sheet_exit": EAST_EXIT,          # the model's own names for the sheet's
      "same_pair": ((4.99, 42.82), (189.53, 42.82))}                  # start, exit, and remoteness pair (ft)


def _why(story, measured, name) -> dict:
    """The story's verdict on a route measure, as routes.measure gives it: its figure, or its reason and the
    figure over the rooms with a route."""
    sp = measured["parts"]["story"][0]
    if name in sp["measures"]:
        return {"figure": round(sp["measures"][name], 3)}
    more = sp["more"].get(name) or {}
    out = {"not_measured": sp["not_measured"].get(name)}
    if "rooms_without_route" in more:
        out.update(rooms_without_route=sorted(more["rooms_without_route"]),
                   over_rooms_with_a_route=round(more["figure"], 3) if "figure" in more else None,
                   from_room=more.get("room"), at=more.get("at"))
    return out


def main(path, out_path=OUT, co=CO):
    from model_measurement.routes import areas, dead_ends, measure, straight
    from model_measurement.routes.common_path import at_point
    from model_measurement.routes.floor import read
    from model_measurement.routes.paths import StoryRoutes
    description = json.loads(Path(path).read_text(encoding="utf-8"))
    story = next(iter(read(description).stories.values()))
    uses = {r["id"]: r.get("use") for r in description["rooms"]}
    room = next(r for r in story.rooms.values() if r is not None and r.name == co["start_room"])
    corner = max(room.outline.exterior.coords, key=lambda c: c[0] + c[1])      # its north-east corner
    out = {"made_by": "packages/model_measurement/tests/make_eval_comparison.py (run it to reproduce this file)",
           "units": "ft, sf",
           "sheet_to_model": {"west_outer_face_pt": WEST_FACE_PT, "north_outer_face_pt": NORTH_FACE_PT,
                              "north_outer_face_ft": NORTH_FACE_FT, "pt_per_ft": PT_PER_FT}, "figures": {}}
    for name, s in SHEET.items():
        out["figures"][name] = {"sheet_stated": s["stated"], "sheet_words": s["words"],
                                "sheet_line_as_drawn": drawn(s["line"]),
                                "sheet_line_in_model": [list(model(p)) for p in s["line"]]}
    measured = measure(description)                          # the story's verdicts, as the rules get them
    gordium = {}
    for r in (12.0, 0.0):
        routes = StoryRoutes(story, r)
        gordium[r] = (routes.route(corner, [co["sheet_exit"]]).length / FT, routes.route(corner),
                      at_point(routes, corner))
    nearest = gordium[12.0][1]
    start = [round(corner[0] / FT, 3), round(corner[1] / FT, 3)]
    out["figures"]["travel_distance"]["gordium"] = {
        "from": list(start), "from_room": f"{co['start_room']}, its north-east corner (the sheet's start)",
        "to_the_sheets_exit_with_12_in": round(gordium[12.0][0], 3),
        "to_the_sheets_exit_no_clearance": round(gordium[0.0][0], 3),
        "to_the_nearest_exit_with_12_in": round(nearest.length / FT, 3), "nearest_exit": nearest.exit_id,
        "story": _why(story, measured, "egress_travel_distance")}
    out["figures"]["common_path"]["gordium"] = {
        "from": list(start), "with_12_in": round(gordium[12.0][2].length / FT, 3),
        "no_clearance": round(gordium[0.0][2].length / FT, 3), "exits": list(gordium[12.0][2].exits),
        "story": _why(story, measured, "common_path_of_travel")}
    near = [next(d for d in story.exits() if math.dist((d.centre[0] / FT, d.centre[1] / FT), q) < 0.05)
            for q in co["same_pair"]]
    far, across, ratio = straight.ratio(story)
    out["figures"]["remoteness"]["gordium"] = {
        "same_pair_nearest_edges": round(straight.opening(near[0]).distance(straight.opening(near[1])) / FT, 3),
        "farthest_pair_nearest_edges": round(far.length / FT, 3), "farthest_pair": list(far.exits),
        "farthest_pair_door_centres": round(far.centres / FT, 3)}
    out["figures"]["diagonal"]["gordium"] = {
        "corner_to_corner": round(across.length / FT, 3), "ends": [[round(v / FT, 3) for v in p] for p in across.corners],
        "ratio": round(ratio, 4)}
    found = dead_ends.corridors(story, uses, StoryRoutes(story))
    out["figures"]["dead_end"]["gordium"] = {
        rid: ({"not_measured": c.stop} if c.stop else
              {"dead_ends": [{"from": [round(v / FT, 3) for v in d.start],
                              "length": round(d.length[dead_ends.WITHOUT] / FT, 3),
                              "least_width": round(d.width[dead_ends.WITHOUT] / FT, 3)} for d in c.dead_ends]})
        for rid, c in sorted(found.items())}
    acc = areas.accessory_area(story, uses)
    out["storage"] = {"sheet_stated_sf": 1428, "sheet_story_sf": 16509,
                      "gordium_inside_sf": round(acc[0].value / FT / FT, 1),
                      "gordium_outer_faces_sf": round(acc[1].value / FT / FT, 1),
                      "gordium_story_sf": [round(x.value / FT / FT, 1) for x in areas.building_area(story)],
                      "rooms": {r.name: round(r.outline.area / FT / FT, 1) for r in story.rooms.values()
                                if r is not None and uses.get(r.id) == "accessory_storage"}}
    out["by_hand"] = BY_HAND
    out_path.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")
    return out


BY_HAND = {   # worked by hand from the sheet and the model, not by the route code: each with its working
    "travel_distance": "the sheet's line turns at right angles and runs the corridor's centre line to the east exit; "
                       "Gordium's is the shortest walk to the same exit",
    "common_path": "the sheet's line turns at right angles to the room's door; Gordium's two routes share the walk "
                   "to and past that door",
    "dead_end_centre_line_reading": {"figure": 32.011, "working": "the stub's closed end, y 74.85 (the corridor "
                                     "outline), to the main corridor's centre line, (37.844 + 47.833) / 2 = 42.839: "
                                     "74.85 - 42.839 = 32.011 ft; the sheet ends at the widening's near edge, y "
                                     "53.17 (open question 2)"},
    "remoteness": "the sheet measures the west and east corridor exits; decision 7 takes the farthest-apart pair",
    "diagonal": "the sheet's ticks are not at the traced outer outline's corners (its north-east tick about 3 ft "
                "north of the traced north face): a trace or drawing difference, not settled",
    "storage": "the sheet doesn't list its rooms; Gordium's outer-faces reading is within 1 percent of the sheet's",
    "story_sf_correct": {"figure": 16539, "working": "the sheet's 16,509 is a recorded error (hand_check.yaml)"},
}


if __name__ == "__main__":
    main(sys.argv[1])
    print(OUT)
