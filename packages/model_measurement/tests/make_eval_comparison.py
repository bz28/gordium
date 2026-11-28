"""The route eval on the Children's Odyssey day care (docs/decisions/2026-11-20_route_measurement.md, "The eval"):
each figure sheet LS1.0 measured, set beside Gordium's from the same start to the same exit, with and without the
12-in clearance. Writes test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml (numbers only).

    python make_eval_comparison.py <the model's interior description .json>

The sheet stays outside the repo (open question 5), so its drawn lines are literals here, measured once on the
sheet's vector drawing (pdfplumber, 2026-11-21): the sheet is 1/8 in = 1 ft, 9 pt a foot. Its points are put in
the model's coordinates (feet) by two walls both show: the west outer face (sheet x 302.58 pt, model x 0) and the
north outer face (sheet y 539.10 pt, model y 85.4833); the two exits' inner faces then fall within 0.01 ft of the
model's (5.494 and 189.200), a check on the match. Gordium's figures are worked by the route code from the model.

Travel distance and common path are judged one-sided (the route note's eval, changed 2026-11-21): the sheet draws its
lines orthogonally, never shorter than the natural path the books measure (IBC 1016.1, NFPA 7.6.1), so Gordium's
figure agrees only when all of these hold: it is no longer than the sheet's line as drawn plus 2 percent of it or
2 ft; it is no shorter than the exact straight line from Gordium's start to an end taken apart from the route (the
travel: the sheet's exit's nearest door centre, no tolerance); its end is within the same tolerance of where the
sheet's line ends (the common path, which has no end apart from its routes, rests on this check); and every one of
that figure's rules gives the sheet's verdict. The first test (within
2 percent or 2 ft of the stated figure) is still worked and reported beside it (`before_2026_11_21`)."""

import json
import math
import sys
from pathlib import Path

import yaml

from model_measurement.routes.stops import Stop

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


def _point_at(pieces, length):
    """The point a route's pieces reach after `length` (inches) along them: its end, or where its routes part."""
    left = length
    for q in pieces:
        if q[0] == "line":
            a, b = q[1], q[2]
            d = math.dist(a, b)
            if left <= d + 1e-9:
                t = left / d if d else 0.0
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        else:
            _, c, r, a0, sweep = q
            d = abs(sweep) * r
            if left <= d + 1e-9:
                ang = a0 + math.copysign(left / r, sweep)
                return (c[0] + r * math.cos(ang), c[1] + r * math.sin(ang))
        left -= d
    last = pieces[-1]
    if last[0] == "line":
        return last[2]
    _, c, r, a0, sweep = last
    return (c[0] + r * math.cos(a0 + sweep), c[1] + r * math.sin(a0 + sweep))


def _ft(p) -> list:
    return [round(p[0] / FT, 3), round(p[1] / FT, 3)]


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
    if "rooms_not_measured" in more:
        out.update(rooms_not_measured={room: str(why) for room, why in sorted(more["rooms_not_measured"].items())},
                   over_rooms_measured=round(more["figure"], 3) if "figure" in more else None,
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
        gordium[r] = (routes.route(corner, [co["sheet_exit"]]), routes.route(corner), at_point(routes, corner))
    nearest = gordium[12.0][1]
    plain_route, plain_common = gordium[0.0][0], gordium[0.0][2]
    start = [round(corner[0] / FT, 3), round(corner[1] / FT, 3)]
    # the travel's end, taken apart from the route: the sheet's exit's door centre (the nearest, if it has several:
    # the smaller floor); the common path's, where its two routes part (no point stands apart from the routes)
    door = min((d for d in story.exits() if d.exit_id == co["sheet_exit"]), key=lambda d: math.dist(corner, d.centre))
    split = plain_common.at if plain_common.at is not None else _point_at(plain_common.routes[0].pieces,
                                                                           plain_common.length)
    out["figures"]["travel_distance"]["gordium"] = {
        "from": list(start), "from_room": f"{co['start_room']}, its north-east corner (the sheet's start)",
        "to_the_sheets_exit_with_12_in": round(gordium[12.0][0].length / FT, 3),
        "to_the_sheets_exit_no_clearance": round(plain_route.length / FT, 3),
        "to_no_clearance": _ft(door.centre), "to_door": door.id,
        "own_ends_straight_exact": math.dist(corner, door.centre) / FT,
        "to_the_nearest_exit_with_12_in": round(nearest.length / FT, 3), "nearest_exit": nearest.exit_id,
        "story": _why(story, measured, "egress_travel_distance")}
    out["figures"]["common_path"]["gordium"] = {
        "from": list(start), "with_12_in": round(gordium[12.0][2].length / FT, 3),
        "no_clearance": round(plain_common.length / FT, 3), "exits": list(gordium[12.0][2].exits),
        "split_no_clearance": _ft(split), "own_ends_straight_exact": math.dist(corner, split) / FT,
        "story": _why(story, measured, "common_path_of_travel")}
    near = [next(d for d in story.exits() if math.dist((d.centre[0] / FT, d.centre[1] / FT), q) < 0.05)
            for q in co["same_pair"]]
    # the figures against the sheet's, as straight.ratio works them; where the outlines don't hold the story (#281:
    # the routes then give no ratio) the same figures, with why the routes don't, never a crash
    refused = None
    try:
        far, across, ratio = straight.ratio(story)
    except Stop as s:
        if s.key not in ("outline_short", "outline_not_outer"):
            raise
        far, across, refused = straight.remoteness(story), straight.diagonal(story), s.reason
        ratio = far.length / across.length
    out["figures"]["remoteness"]["gordium"] = {
        "same_pair_nearest_edges": round(straight.opening(near[0]).distance(straight.opening(near[1])) / FT, 3),
        "farthest_pair_nearest_edges": round(far.length / FT, 3), "farthest_pair": list(far.exits),
        "farthest_pair_door_centres": round(far.centres / FT, 3)}
    out["figures"]["diagonal"]["gordium"] = {
        "corner_to_corner": round(across.length / FT, 3), "ends": [[round(v / FT, 3) for v in p] for p in across.corners],
        "ratio": round(ratio, 4), **({"not_given_by_the_routes": refused} if refused else {})}
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
    out["verdicts"] = _verdicts(measured)
    _judge_all(out)
    out["storage"]["under_all_four_readings"] = _storage_readings(measured)
    out["by_hand"] = BY_HAND
    out_path.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n")
    return out


SHEET_DEAD_END_WIDTH = 10.0     # ft: the sheet's "(length < 2.5 x 10' = 25')" (hand_check.yaml)
HAND_CHECK = Path(__file__).resolve().parents[3] / "test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml"
SHEET_VALUES = {"occupancy_group_i4": True, "sprinklered_903_3_1_1": True, "sprinklered_903_3_1_2": False,
                "nfpa_day_care_occupancy": True, "day_care_existing": False, "sprinklered_9_7": True,
                "sprinkler_supervised_9_7": True}       # the sheet's building: hand_check.yaml's header


def _verdicts(measured) -> dict:
    """The decision's "every verdict the same as the sheet's": each rule hand_check.yaml names for a route check,
    run on the parts by parts.rows (the checker's rows), beside the sheet's result."""
    from rule_format import parts as part_rules
    from rule_format.rulebook import REPO, Context, load
    maine = REPO / "regulations/jurisdictions/maine/maine_state"
    rules = {r["id"]: r for r in load(maine / "5_building_code_rules/drafted/general.yaml")["rules"]}
    allowed = Context.for_jurisdiction(maine).allowed()
    key = yaml.safe_load(HAND_CHECK.read_text(encoding="utf-8"))
    out, by_figure = {}, {}
    for figure, check in zip(("travel_distance", "common_path", "dead_end", "remoteness", "storage"),
                             key["checks"][:5]):    # travel, common path, dead end, remoteness, storage
        by_figure[figure] = list(check["gordium_rules"])
        for rid in check["gordium_rules"]:
            got = part_rules.rule_result(part_rules.rows(rules[rid], measured["parts"], SHEET_VALUES, allowed))
            out[rid] = {"gordium": got, "sheet": check["result"], "same": got == check["result"]}
    return {"rules": out, "every_verdict_the_same": all(v["same"] for v in out.values()), "by_figure": by_figure}


def _storage_readings(measured) -> dict:
    """508.2.1's check (accessory <= 10 percent of the story) under each of the four pairs of area readings
    (decision 8), worked by parts.rows on the story part (the rule made a rule here: the IBC's is a flag)."""
    from rule_format import parts as part_rules
    from rule_format.rulebook import REPO, Context, load
    maine = REPO / "regulations/jurisdictions/maine/maine_state"
    rule = next(r for r in load(maine / "5_building_code_rules/drafted/general.yaml")["rules"]
                if r["id"] == "general.ibc_508_2_1_accessory_area")
    rule = dict(rule, kind="rule")
    allowed = Context.for_jurisdiction(maine).allowed()
    sp = measured["parts"]["story"][0]
    combos = part_rules.reading_combinations(rule, sp, set(part_rules.measure_kinds("story")), sp["measures"])
    if not combos:
        return {"judged": False, "why": "the story's area readings aren't there to combine"}
    each = {words: part_rules.part_outcome(rule, {**SHEET_VALUES, **values}, allowed) for words, values in combos}
    return {"judged": True, "each_pair": each, "complies_under_all_four": set(each.values()) == {"pass"},
            "sheet": "pass"}


TOLERANCES = {   # the decision's "Agreement asked" (docs/decisions/2026-11-20_route_measurement.md, "The eval")
    "travel_distance": "Gordium's no-clearance figure, from the sheet's start to the sheet's exit, no longer than the "
                       "sheet's line as drawn plus 2 percent of it or 2 ft, whichever is larger, no shorter than the "
                       "straight line from its start to the sheet's exit's door centre, that door centre within the "
                       "same of where the sheet's line ends, and every rule of this figure giving the sheet's verdict "
                       "(changed 2026-11-21: the sheet's line is orthogonal, never shorter than the natural path IBC "
                       "1016.1 and NFPA 7.6.1 measure)",
    "common_path": "Gordium's no-clearance figure from the sheet's start no longer than the sheet's line as drawn "
                   "plus 2 percent of it or 2 ft, whichever is larger, where its two routes part within the same of "
                   "where the sheet's line ends (the check that catches a figure measured too short: the straight "
                   "line to that point is shown too, but can't catch it, the point being read off the routes), and "
                   "every rule of this figure giving the sheet's verdict (changed 2026-11-21, as for the travel "
                   "distance)",
    "dead_end": "length within 1 ft, width within 1 in",
    "remoteness": "within 1 ft of Gordium's nearest-edge figure or of its door-centre figure",
    "diagonal": "within 6 in",
    "storage_inside": "the inside-walls figure within 1 percent",
    "story_area": "the outer-faces story area within 1 percent of 16,539 sf (the sheet's 16,509 is a recorded error)",
}


BEFORE = {   # the first test, until 2026-11-21: still worked and reported, so nothing it found is hidden
    "travel_distance": "within 2 percent or 2 ft, whichever is larger, of Gordium's no-clearance figure",
    "common_path": "within 2 percent or 2 ft, whichever is larger, of Gordium's no-clearance figure",
}


def _no_longer(drawn, ours, verdicts, rules, words, straight, end_ok=True) -> dict:
    """The test since 2026-11-21: Gordium's figure no longer than the sheet's line as drawn plus the tolerance; no
    shorter than the straight line from Gordium's start to its end (`straight`, exact, never from rounded
    coordinates); where it ends within the tolerance of where the sheet's line ends (`end_ok`, the `end` item); and
    each of the figure's rules giving the sheet's verdict. For the travel the end is the sheet's exit's door centre,
    taken apart from the route, so the floor catches a route measured too short. For the common path the end is
    where Gordium's two routes part, read off the routes at the figure's own length, so the floor alone can't catch
    a too-short figure (the straight line to a point the route reaches is never longer than the way there): the end
    item does, a split point short of the sheet's is outside it (review round 3)."""
    allowed = round(max(0.02 * drawn, 2.0), 3)
    same = {rid: verdicts[rid]["same"] for rid in rules}
    if ours is None:
        return {"tolerance": words, "within_tolerance": None, "why": "Gordium gives no figure", "verdicts_same": same}
    short = ours <= drawn + allowed + 1e-9
    long_enough = ours >= straight - 1e-6
    return {"tolerance": words, "sheet_line_as_drawn": drawn, "own_ends_straight": straight, "gordium": ours,
            "longer_than_drawn_by": round(ours - drawn, 3), "allowed": allowed, "no_longer": short,
            "no_shorter_than_own_straight": long_enough, "end_within_tolerance": bool(end_ok), "verdicts_same": same,
            "within_tolerance": bool(short and long_enough and end_ok and all(same.values()))}


def _end(sheet_end, ours, allowed, what) -> dict:
    """Where Gordium's figure ends (its exit's door centre, or where its two routes part) beside where the sheet's
    line ends: its own agreement item, within the figure's tolerance."""
    apart = round(math.dist(sheet_end, ours), 3)
    return {"what": what, "sheet": list(sheet_end), "gordium": list(ours), "apart": apart, "allowed": allowed,
            "within_tolerance": apart <= allowed + 1e-9}


def _verdict(sheet, ours, allowed, words) -> dict:
    if ours is None:
        return {"tolerance": words, "within_tolerance": None, "why": "Gordium gives no figure"}
    best = min(ours, key=lambda v: abs(v - sheet)) if isinstance(ours, list) else ours
    diff = round(best - sheet, 3)
    return {"tolerance": words, "sheet": sheet, "gordium": best, "difference": diff,
            "allowed": round(allowed, 3), "within_tolerance": abs(diff) <= allowed + 1e-9}


def _no_dead_end(by_corridor) -> str:
    """Why no dead end of Gordium's is judged: it measured none on the corridor (and why), or its dead ends start
    elsewhere than the sheet's line."""
    stops = [c["not_measured"] for c in by_corridor.values() if "not_measured" in c]
    if not any(c.get("dead_ends") for c in by_corridor.values()):
        return ("Gordium measured no dead end on this corridor: " + "; ".join(stops)) if stops else             "Gordium found no dead end on these corridors"
    return "Gordium's dead ends start elsewhere: none within 3 ft of the sheet's line"


def _judge_all(out) -> None:
    """Each figure against the decision's tolerance: within or outside, and by how much (worked here, never written
    in)."""
    f = out["figures"]
    for name in ("travel_distance", "common_path"):
        sheet = f[name]["sheet_stated"]
        g = f[name]["gordium"]
        ours = g.get("to_the_sheets_exit_no_clearance", g.get("no_clearance"))
        end = g.get("to_no_clearance", g.get("split_no_clearance"))
        allowed = round(max(0.02 * f[name]["sheet_line_as_drawn"], 2.0), 3)
        item = _end(f[name]["sheet_line_in_model"][-1], end, allowed,
                    "the sheet's exit's door centre" if name == "travel_distance" else "where Gordium's two routes part")
        f[name]["agreement"] = _no_longer(f[name]["sheet_line_as_drawn"], ours, out["verdicts"]["rules"],
                                          out["verdicts"]["by_figure"][name], TOLERANCES[name],
                                          g["own_ends_straight_exact"], item["within_tolerance"])
        f[name]["agreement"]["own_ends_straight"] = round(g["own_ends_straight_exact"], 3)
        f[name]["agreement"]["end"] = item
        f[name]["agreement"]["before_2026_11_21"] = _verdict(sheet, ours, max(0.02 * sheet, 2.0), BEFORE[name])
    # the dead end the sheet's line runs along: the one whose closed end is nearest the line's start (within 3 ft)
    start = f["dead_end"]["sheet_line_in_model"][0]
    ends = [d for c in f["dead_end"]["gordium"].values() for d in c.get("dead_ends", [])
            if math.dist(d["from"], start) <= 3.0]
    mine = min(ends, key=lambda d: math.dist(d["from"], start)) if ends else None
    length = _verdict(f["dead_end"]["sheet_stated"], mine["length"] if mine else None, 1.0, "length within 1 ft")
    width = _verdict(SHEET_DEAD_END_WIDTH, mine["least_width"] if mine else None, 1 / 12, "width within 1 in")
    f["dead_end"]["agreement"] = {"tolerance": TOLERANCES["dead_end"], "length": length, "least_width": width,
                                  "dead_end": list(mine["from"]) if mine else _no_dead_end(f["dead_end"]["gordium"]),
                                  "within_tolerance": None if mine is None else
                                  bool(length["within_tolerance"] and width["within_tolerance"])}
    g = f["remoteness"]["gordium"]
    f["remoteness"]["agreement"] = _verdict(f["remoteness"]["sheet_stated"],
                                            [g["farthest_pair_nearest_edges"], g["farthest_pair_door_centres"]], 1.0,
                                            TOLERANCES["remoteness"])
    f["diagonal"]["agreement"] = _verdict(f["diagonal"]["sheet_stated"], f["diagonal"]["gordium"]["corner_to_corner"],
                                          0.5, TOLERANCES["diagonal"])
    st = out["storage"]
    st["agreement_inside"] = _verdict(st["sheet_stated_sf"], st["gordium_inside_sf"], 0.01 * st["sheet_stated_sf"],
                                      TOLERANCES["storage_inside"])
    st["agreement_story_area"] = _verdict(16539, st["gordium_story_sf"][-1], 0.01 * 16539, TOLERANCES["story_area"])


BY_HAND = {   # worked by hand from the sheet and the model, not by the route code: each with its working
    "travel_distance": "the sheet's line turns at right angles and runs the corridor's centre line to the east exit; "
                       "Gordium's is the shortest walk to the same exit",
    "common_path": "the sheet's line turns at right angles to the room's door; Gordium's two routes share the walk "
                   "to and past that door",
    "dead_end_centre_line_reading": {"figure": 32.011, "working": "the stub's closed end, y 74.85 (the corridor "
                                     "outline), to the main corridor's centre line, (37.844 + 47.833) / 2 = 42.839: "
                                     "74.85 - 42.839 = 32.011 ft; the sheet ends at the widening's near edge, y "
                                     "53.17 (open question 2: NFPA 101 A.7.5.1.5 measures to the centre line)"},
    "remoteness": "the sheet measures the west and east corridor exits; decision 7 takes the farthest-apart pair",
    "diagonal": "the sheet's ticks are not at the traced outer outline's corners (its north-east tick about 3 ft "
                "north of the traced north face): a trace or drawing difference, not settled",
    "storage": "the sheet doesn't list its rooms; Gordium counts the rooms marked accessory_storage",
    "story_sf_correct": {"figure": 16539, "working": "the sheet's 16,509 is a recorded error (hand_check.yaml)"},
}


if __name__ == "__main__":
    main(sys.argv[1])
    print(OUT)
