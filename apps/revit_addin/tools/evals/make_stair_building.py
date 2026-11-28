"""The stair test building (Building Code section group 7: stairs 1011, handrails 1014, guards 1015): one exit stair
enclosure, two stories, with a code-sized two-flight stair (a switchback: up east, a turn landing, up west), a
landing at each floor, a handrail on both sides of each flight and a guard at Level 2's open landing edge; on each
story a corridor west of the enclosure, its door into the enclosure marked an exit stair enclosure (so the stair is
outside every dwelling unit: none of 1011.5.2's, 1011.11's or 1015.3's dwelling-unit exceptions can apply), opening
onto the landing. Written as the interior description (gordium.interior/1) the checker reads, in inches, in two
variants:

    stair_enclosure_compliant.yaml   every stair, handrail and guard figure within the 2025 Building Code of New York
                                      State's limits (worked by hand in the file's header)
    stair_enclosure_failing.yaml     the same stair with known failures, each past every exception open to it: 8 in
                                      risers (1011.5.2: at most 7 in; 7 3/4 in within a dwelling unit), a beam leaving
                                      76 in of headroom over the upper flight (1011.3: 80 in), no handrail on the upper
                                      flight's wall side (1011.11: both sides), and a 34 in guard (1015.3: 42 in; 36 in
                                      within a dwelling unit)

Gordium's own test building, not a real project, and not built in Revit (its stairs are checked from the description;
ModelBuild doesn't place stairs yet). The four-unit apartment's enclosures (9 x 6 ft) can't hold a code-sized stair:
docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md, "Open design items".

    python apps/revit_addin/tools/evals/make_stair_building.py            write both
    python apps/revit_addin/tools/evals/make_stair_building.py --check    exit 1 when either isn't current

Plain code, no AI.
"""

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
OUT = REPO / "test_data/test_sites/new_york/stair_enclosure"

# the plan, inches: x east, y north, inside the enclosure's finished walls x 0..W_LONG, y 0..W_WIDE
WIDTH = 44            # each flight's width between its walls (1011.2: 44 in, 36 in for an occupant load under 50)
WALL = 4              # the wall between the two flights
TREAD = 11            # 1011.5.2: at least 11 in
LANDING = 44          # each landing as deep as the stair is wide (1011.6)
TREADS = 8            # per flight: 9 risers, the last onto the landing above
RAIL = 3.5            # a handrail's projection into the flight from its wall (1014.9: at most 4 1/2 in)
BEAM = (84, 96)       # the failing variant's beam over flight 2, x from and to
CORRIDOR = 120        # the corridor west of the enclosure, x -WALL-120 .. -WALL
DOOR_Y = 22           # each story's door into the enclosure, centred on y 22 (onto the landing at x 0..44)


def _variant(failing: bool) -> dict:
    riser = 8 if failing else 6.5                      # 1011.5.2: 4 to 7 in (7 3/4 in within a dwelling unit)
    story = 18 * riser                                 # floor to floor: two flights of 9 risers
    run = TREADS * TREAD
    long_ = LANDING + run + LANDING                    # bottom (and Level 2) landing, the flight, the turn landing
    wide = WIDTH + WALL + WIDTH
    ceiling = story + 108                              # Level 2's ceiling, 9 ft over its floor
    slab = story - 12                                  # Level 2's landing underside (a 12 in floor)
    turn = 9 * riser                                   # the turn landing's elevation
    # the failing variant's beam over flight 2, x 84..96: 76 in above the nosing line where it is highest under the
    # beam (at x 84, the line rising toward -x from the turn landing's edge at x 132, a riser every 11 in)
    beam = turn + riser * (1 + (LANDING + run - BEAM[0]) / TREAD) + 76
    f1 = {"y0": 0, "y1": WIDTH}                        # flight 1, up toward +x, along the south wall
    f2 = {"y0": WIDTH + WALL, "y1": wide}              # flight 2, up toward -x, along the north wall

    def nosings(x0, step, z0, y0, y1):
        return [[[x0 + step * k, y0, z0 + riser * (k + 1)], [x0 + step * k, y1, z0 + riser * (k + 1)]]
                for k in range(TREADS + 1)]

    def plan(*pts):
        return [list(p) for p in pts]

    # flight 1: its first nosing at the bottom landing's edge x 44, its last the turn landing's edge
    flight1 = {
        "id": "f1", "name": "Flight 1 (Level 1 to the turn landing)", "bottom_elevation": 0, "spiral": False,
        "nosings": nosings(LANDING, TREAD, 0, f1["y0"], f1["y1"]),
        # looking up the stair (toward +x): left is the centre wall (north), right the south wall
        "sides": {"left": plan((LANDING - 12, f1["y1"]), (LANDING + run + 12, f1["y1"])),
                  "right": plan((LANDING - 12, f1["y0"]), (LANDING + run + 12, f1["y0"]))},
        # each handrail one tread past the bottom nosing and 12 in past the top one (1014.7: not continuous between
        # flights), within the sides
        "handrails": [{"side": "left", "inner_edge": plan((LANDING - TREAD, f1["y1"] - RAIL), (LANDING + run + 12, f1["y1"] - RAIL))},
                      {"side": "right", "inner_edge": plan((LANDING - TREAD, f1["y0"] + RAIL), (LANDING + run + 12, f1["y0"] + RAIL))}],
        # above it: Level 2's landing slab over x 0..44, the enclosure's ceiling beyond
        "overhead": [[[0, 0, slab], [LANDING, 0, slab], [LANDING, wide, slab], [0, wide, slab]],
                     [[LANDING, 0, ceiling], [long_, 0, ceiling], [long_, wide, ceiling], [LANDING, wide, ceiling]]],
    }
    # flight 2: up toward -x from the turn landing, its last nosing Level 2's landing edge at x 44
    flight2 = {
        "id": "f2", "name": "Flight 2 (the turn landing to Level 2)", "bottom_elevation": turn, "spiral": False,
        "nosings": nosings(LANDING + run, -TREAD, turn, f2["y1"], f2["y0"]),
        # looking up the stair (toward -x): left is the centre wall (south), right the north wall
        "sides": {"left": plan((LANDING + run + 12, f2["y0"]), (LANDING - 12, f2["y0"])),
                  "right": plan((LANDING + run + 12, f2["y1"]), (LANDING - 12, f2["y1"]))},
        "handrails": [{"side": "left", "inner_edge": plan((LANDING + run + TREAD, f2["y0"] + RAIL), (LANDING - 12, f2["y0"] + RAIL))}]
        + ([] if failing else
           [{"side": "right", "inner_edge": plan((LANDING + run + TREAD, f2["y1"] - RAIL), (LANDING - 12, f2["y1"] - RAIL))}]),
        "overhead": [[[0, 0, ceiling], [long_, 0, ceiling], [long_, wide, ceiling], [0, wide, ceiling]]]
        + ([[[BEAM[0], f2["y0"], beam], [BEAM[1], f2["y0"], beam], [BEAM[1], f2["y1"], beam], [BEAM[0], f2["y1"], beam]]]
           if failing else []),
    }
    # Level 2's landing (x 0..44) is open over flight 1 below along x 44, y 0..44: a guard there, 42 in (34 failing)
    top = story + (34 if failing else 42)
    # balusters 1 1/2 in wide, 3 1/2 in apart, from 2 1/2 in off the south wall to the centre wall: no opening over 3 1/2 in
    balusters = [{"left": 2.5 + 5 * k, "right": 4 + 5 * k, "bottom": story + 3.5, "top": top - 1.5} for k in range(9)]
    guard = {"id": "g1", "name": "Level 2 landing guard", "walking_surface": story, "top": top,
             "extent": {"left": 0, "right": WIDTH},
             "members": [{"left": 0, "right": WIDTH, "bottom": top - 1.5, "top": top},
                         {"left": 0, "right": WIDTH, "bottom": story, "top": story + 3.5}] + balusters}

    def room(level, z, floor):
        return {"id": f"{level}S", "name": f"Stair {level}", "sleeping": False, "level": level, "use": "other",
                "lockable": False, "pass_through": False, "floor_elevation": z,
                "floor": floor, "holes": [], "obstructions": []}

    def corridor(level, z):
        x0, x1 = -WALL - CORRIDOR, -WALL
        return {"id": f"{level}C", "name": f"Corridor {level}", "sleeping": False, "level": level, "use": "corridor",
                "lockable": False, "pass_through": True, "floor_elevation": z,
                "floor": plan((x0, 0), (x1, 0), (x1, wide), (x0, wide)), "holes": [], "obstructions": []}

    def door(level):
        return {"id": f"{level}D", "name": f"Stair door {level}", "level": level, "sides": [f"{level}C", f"{level}S"],
                "exit": False, "exit_kind": "exit_enclosure", "exit_id": f"{level}S", "operation": "side_hinged",
                "plan": {"centre": [-WALL / 2, DOOR_Y], "along": [0, 1], "clear_width": 34, "wall_thickness": WALL}}

    return {
        "format": "gordium.interior/1",
        "units": "in",
        "levels": [{"id": "L1", "name": "Level 1", "elevation": 0}, {"id": "L2", "name": "Level 2", "elevation": story}],
        # Level 1's floor at 0 under the whole enclosure; Level 2's only its landing (x 0..44): the rest is open to
        # the flights below, which is the edge its guard stands at
        "rooms": [room("L1", 0, plan((0, 0), (long_, 0), (long_, wide), (0, wide))),
                  room("L2", story, plan((0, 0), (LANDING, 0), (LANDING, wide), (0, wide))),
                  corridor("L1", 0), corridor("L2", story)],
        "openings": [],
        "doors": [door("L1"), door("L2")],             # (exit: a house's required exit door; this is no house)
        "passages": [],
        "stairs": [flight1, flight2],
        "guards": [guard],
        # NFPA 13 throughout: an R-2 building needs a sprinkler system whatever its size (903.2.8, Chapter 9 part a),
        # so a compliant building states one
        "building": {"occupancy_groups": ["R-2"], "sprinkler_system": "nfpa_13"},
    }


HEADERS = {
    False: """# The stair test building, compliant: every stair, handrail and guard figure within the 2025 Building Code of
# New York State (section group 7; written by apps/revit_addin/tools/evals/make_stair_building.py, never edited by
# hand). Inches. Worked by hand: risers 6.5 in (1011.5.2: 4 to 7 in), 18 of them, 117 in floor to floor; treads 11 in
# (at least 11 in); each flight 44 in wide between its walls (1011.2: 44 in) with a handrail on both sides projecting
# 3.5 in (1014.9: at most 4 1/2 in), so 37 in clear between them; headroom over flight 1 at its first nosing 105 - 6.5
# = 98.5 in, and over flight 2 108 in to the ceiling (1011.3: 80 in); landings 44 in deep (1011.6: the stair's width); Level 2's
# open landing edge guarded 42 in high (1015.3: 42 in), no opening in it over 3.5 in (1015.4: a 4 in sphere doesn't
# pass); each handrail runs one tread past the bottom nosing and 12 in past the top one (1014.7). Each story's door
# from its corridor is marked an exit stair enclosure: the stair is in no dwelling unit. Not described (so not
# claimed): the handrails' height and grip (1014.2, 1014.4) and the landings' own outlines.
# Gordium's own test building, not a real project.
""",
    True: """# The stair test building, failing: the compliant one (stair_enclosure_compliant.yaml) with known failures
# (section group 7; written by apps/revit_addin/tools/evals/make_stair_building.py, never edited by hand). Inches.
# Risers 8 in, so 144 in floor to floor (1011.5.2: at most 7 in; 7 3/4 in within a dwelling unit); a beam over flight
# 2 leaving 76 in of headroom above its nosings (1011.3: 80 in); no handrail on flight 2's north wall side (its right,
# looking up; 1011.11: on both sides), so 40.5 in clear at its one handrail; Level 2's landing guard 34 in high
# (1015.3: 42 in; 36 in within a dwelling unit). Each failure is past every exception open to this stair (an R-2
# building's stair, marked in no dwelling unit as the compliant one is; a guard at a landing). Everything else as the compliant variant. Gordium's own test building,
# not a real project.
""",
}


def texts() -> dict:
    out = {}
    for failing, name in ((False, "stair_enclosure_compliant.yaml"), (True, "stair_enclosure_failing.yaml")):
        body = yaml.safe_dump(_variant(failing), sort_keys=False, default_flow_style=None, width=120)
        out[OUT / name] = HEADERS[failing] + "\n" + body
    return out


def main(argv: list[str]) -> int:
    got = texts()
    if "--check" in argv:
        stale = [p for p, t in got.items() if not p.exists() or p.read_text(encoding="utf-8") != t]
        for p in stale:
            print(f"{p.relative_to(REPO)} isn't current: run make_stair_building.py")
        return 1 if stale else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for p, t in got.items():
        p.write_text(t, encoding="utf-8", newline="\n")
        print(f"wrote {p.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
