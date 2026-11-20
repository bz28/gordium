"""Interior conformance for a host's recordings (model_measurement.interior.recordings; the Revit interior design
note, section 6): a recording passes only when every measure of this step equals the hand-worked one and every other
comes back not measured. Pinned on a recording made here the way a host's reader describes the drawn house (each
window's maker's clear opening, never its frame), then on each way a reader can go wrong; and on the host recordings
committed (none until the Windows trial records them: then every house of the step must be there)."""

import copy
import json
import subprocess
import sys

import pytest

from model_measurement.interior import recordings as r

ORANGETOWN = "orangetown_ny_80_south_william"


def described(name: str) -> dict:
    """The house as a host's reader would send it from the drawing: rooms (floor, elevation, ceiling pieces) and every
    window (the maker's clear opening on the escape windows), with no frame or sash (the first Revit reader sends
    none) and no ground outside (no Toposolid drawn)."""
    d = r.drawing(name)
    rooms = [{"id": f"host-{x['id']}", "name": x["name"], "sleeping": x["sleeping"], "floor": x["floor"],
              "floor_elevation": x["floor_elevation"], "ceilings": x["ceilings"]} for x in d["rooms"]]
    openings = []
    for w in d["windows"]:
        o = {"id": f"host-{w['id']}", "name": w["name"], "room": f"host-{w['room']}", "escape": w["escape"],
             "operation": w["operation"]}
        if w["clear"]:
            c = w["clear"]
            o["stated_clear"] = {"width": c["width"], "height": c["height"],
                                 "bottom": w["level"] + w["sill"] + c["offset"], "source": c["source"]}
        openings.append(o)
    for dr in d["doors"]:                     # a door is an opening too (marked no escape opening), and a door
        openings.append({"id": f"host-{dr['id']}", "name": dr["name"], "room": f"host-{dr['room']}", "escape": False,
                         "operation": {"side_hinged": "side_hinged_door", "sliding": "sliding_door"}[dr["operation"]]})
    ids = {x["id"]: f"host-{x['id']}" for x in d["rooms"] + d["windows"] + d["stairs"] + d["doors"] + d["guards"]}
    interior = {"format": "gordium.interior/1", "units": "ft", "rooms": rooms, "openings": openings}
    if d["stairs"]:
        interior["stairs"] = [flight(st) for st in d["stairs"]]
    if d["doors"]:                            # its exit mark, operation and maker's confirmed clear opening; nothing drawn
        interior["doors"] = [{"id": f"host-{x['id']}", "name": x["name"], "exit": x["exit"], "operation": x["operation"]}
                             | ({"stated_clear": {k: x["clear"][k] for k in ("width", "height", "source")}} if x["clear"] else {})
                             for x in d["doors"]]
    if d["guards"]:
        interior["guards"] = [guard(g) for g in d["guards"]]
    for key in d["has_none"]:                 # the architect's "this house has none of" ticks (step 6)
        if key in r.NONE_LISTS:
            interior[key] = []
        else:
            interior.setdefault("has_none", []).append({"kind": key, "source": "ticked by the architect (test)"})
    return {"host": "test", "house": name, "step": d["step"], "ids": ids,
            "recorded": {"by": "test_interior_recordings", "date": "2026-11-20", "tool": "python"},
            "interior": interior}


def flight(st: dict) -> dict:
    """A drawn flight as the Revit reader sends it: the floor at its foot; each tread's nosing from the run (equal
    risers and treads, along its path), then the floor's edge at the head, as drawn (house 3's 1 1/2 in above the
    run's top: its last riser 9 in); each side a wall's face, or open; what is overhead; no handrails (railings:
    step 5)."""
    (x0, y0), (x1, y1) = st["path"]
    length = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    half = st["width"] / 2

    def across(k, z):
        cx, cy = x0 + ux * st["tread"] * k, y0 + uy * st["tread"] * k
        return [[cx + uy * half, cy - ux * half, z], [cx - uy * half, cy + ux * half, z]]

    overhead = list(st["overhead"])
    if st["upper_floor"]:                     # the upper floor's underside short of its opening: its piece over the foot
        u = st["upper_floor"]
        z = u["top"] - st["slab"]
        (a0, a1), (h0, h1) = (u["outer"][0], u["outer"][3]), (u["hole"][0], u["hole"][3])
        overhead.append([[*a0, z], [*h0[:1], a0[1], z] if ux else [a0[0], h0[1], z],
                         [*h0[:1], a1[1], z] if ux else [a1[0], h0[1], z], [*a1, z]])
    out = {"id": f"host-{st['id']}", "name": st["name"], "bottom_elevation": st["foot"]["top"], "spiral": False,
           "sides": {w["side"]: w["face"] for w in st["walls"]} | {s: "open" for s in st["open_sides"]},
           "overhead": overhead}
    out["nosings"] = [across(k, st["base"] + st["riser"] * (k + 1)) for k in range(st["risers"] - 1)] \
        + [across(st["risers"] - 1, st["head_top"])]
    if st["handrails"]:                       # each drawn handrail's inner edge (step 5)
        out["handrails"] = [{"side": h["side"], "inner_edge": h["inner"]} for h in st["handrails"]]
    return out


def guard(g: dict) -> dict:
    """A drawn level guard as the Revit reader sends it: the floor's top, its top rail's top, its ends at the wall and
    the post, each rail and baluster as a rectangle in its own elevation (u from the path's start)."""
    w = g["level"]
    rails = [g["top_rail"], *g["rails"]]
    b = g["balusters"]
    members = [{"left": 0.0, "right": g["length"], "bottom": w + r["bottom"], "top": w + r["top"]} for r in rails]
    members += [{"left": b["first"] + k * b["spacing"], "right": b["first"] + k * b["spacing"] + b["width"],
                 "bottom": w + b["bottom"], "top": w + b["top"]} for k in range(b["count"])]
    return {"id": f"host-{g['id']}", "name": g["name"], "walking_surface": w, "top": w + g["top"],
            "extent": {"left": 0.0, "right": g["length"]}, "members": members}


@pytest.mark.parametrize("name", r.STEP_HOUSES)
def test_a_house_described_as_drawn_passes(name):
    assert r.recording_problems(described(name)) == []


def test_the_steps_scope_is_the_design_notes():
    rooms = {"sleeping_room": {"sleeping_room_floor_area", "floor_area_drawn", "least_ceiling_height"},
             "emergency_escape_opening": {"opening_net_clear_width", "opening_net_clear_height", "opening_net_clear_area",
                                          "opening_sill_height", "opening_is_door", "opening_door_hinged_or_sliding"}}
    stairs = {"stair_riser_height", "stair_riser_variation", "stair_total_rise", "stair_risers", "stair_tread_depth",
              "stair_tread_variation", "stair_headroom", "stair_clear_width",
              "stair_spiral"}                                                   # never the width at the handrail
    doors = {"door_clear_width", "door_clear_height", "door_side_hinged"}
    handrails = {"stair_clear_width_at_handrail", "stair_handrail_sides"}
    assert r.STEP == 6
    assert r.HOUSE_STEP == {"1_ranch_compliant": 6, "2_two_story_small_window": 6, "3_tall_riser": 4, "4_loft": 6,
                            "5_basement_window_well": 6, "6_door_stated_clear": 6, ORANGETOWN: 6}
    # step 6: each list the house gives empty is in scope, read as that empty list (no measures)
    assert r.scope("1_ranch_compliant") == r.scope("6_door_stated_clear") == rooms | {"egress_door": doors, "stair": set(),
                                                                                       "guard": set()}
    assert r.scope("2_two_story_small_window") == rooms | {"stair": stairs | handrails, "egress_door": doors, "guard": set()}
    # the real house: its rooms, marked escape windows and front door; its stairs and guards not drawn, so not read;
    # and what its seven has_none claims bring: each claimed part kind an empty list, two measures on every opening
    claims = ["alternating_tread_device", "deck_porch_or_cantilever_over_escape_opening", "habitable_attic",
              "patio_cover", "ramp", "ships_ladder", "sleeping_loft"]
    assert sorted(c["kind"] for c in r._house(ORANGETOWN)["has_none"]) == claims
    assert r.scope(ORANGETOWN) == {
        "sleeping_room": rooms["sleeping_room"],
        "emergency_escape_opening": rooms["emergency_escape_opening"] | {"opening_into_patio_cover",
                                                                         "opening_under_projection"},
        "egress_door": doors, "sleeping_loft": set(), "loft_room": set(), "habitable_attic": set(), "ramp": set(),
        "alternating_tread_device": set(), "ships_ladder": set()}
    assert sorted(r.drawing(ORANGETOWN)["has_none"]) == claims       # its own claims ticked; no list is empty
    assert r.scope("3_tall_riser") == rooms | {"stair": stairs}                  # its last riser as drawn (step 4)
    assert r.scope("4_loft") == rooms | {"stair": stairs | handrails, "guard": {"guard_height", "guard_opening_sphere"},
                                         "egress_door": set()}
    # a sliding door: no clear width worked by hand, so no maker's clear opening made up: its height not in scope
    assert r.scope("5_basement_window_well") == rooms | {"egress_door": {"door_side_hinged"}, "guard": set()}
    # every empty list in scope is ticked, and nothing else (no hand-worked house has a has_none claim)
    for name in r.STEP_HOUSES:
        if name == ORANGETOWN:
            continue
        house = r._house(name)
        assert r.drawing(name)["has_none"] == [k for k, kind in r.NONE_LISTS.items()
                                               if house.get(k) == [] and kind in r.scope(name)]
        assert not house.get("has_none")
    assert r.drawing("1_ranch_compliant")["has_none"] == ["stairs", "guards"]
    assert r.drawing("4_loft")["has_none"] == ["doors"]
    assert r.drawing("3_tall_riser")["has_none"] == []


def test_house_2s_stair_drawn_and_read_measures_as_worked_by_hand():
    rec = described("2_two_story_small_window")
    assert r.recording_problems(rec) == []
    s1 = rec["interior"]["stairs"][0]
    for end in s1["nosings"][-1]:
        end[2] += 1 / 12                                                # the head floor an inch high: a tall top riser
    assert any("s1 stair_riser_height = 8.5, expected 7.5" in p for p in r.recording_problems(rec))
    rec = described("2_two_story_small_window")
    del rec["interior"]["stairs"][0]["overhead"]
    assert any("s1 stair_headroom not measured" in p for p in r.recording_problems(rec))
    rec = described("2_two_story_small_window")
    rec["interior"]["stairs"][0]["handrails"] = []                     # its handrail missed: "none" read
    assert any("s1 stair_handrail_sides = 0, expected 1" in p for p in r.recording_problems(rec))
    rec = described("2_two_story_small_window")
    del rec["interior"]["stairs"][0]["handrails"]
    assert any("s1 stair_clear_width_at_handrail not measured" in p for p in r.recording_problems(rec))
    rec = described("2_two_story_small_window")
    h = rec["interior"]["stairs"][0]["handrails"][0]["inner_edge"]
    h[0][1] = h[1][1] = h[0][1] + 1 / 12                                # read an inch farther in
    assert any("s1 stair_clear_width_at_handrail = 31.5, expected 32.5" in p for p in r.recording_problems(rec))


def test_doors_drawn_and_read_measure_as_worked_by_hand():
    d = r.drawing("6_door_stated_clear")
    (door,) = d["doors"]
    assert door["clear"]["width"] * 12 == pytest.approx(33.5)          # the maker's, the smaller
    assert door["clear"]["height"] * 12 == pytest.approx(79.25)        # the drawn, the smaller
    assert door["width"] * 12 == pytest.approx(35.75) and door["outward"] == [0, -1]
    rec = described("6_door_stated_clear")
    assert r.recording_problems(rec) == []
    rec["interior"]["doors"][0]["stated_clear"]["width"] += 0.5 / 12   # a maker's figure larger than the less favourable
    assert any("d1 door_clear_width = 34.0, expected 33.5" in p for p in r.recording_problems(rec))
    rec = described("1_ranch_compliant")
    del next(x for x in rec["interior"]["doors"] if x["id"] == "host-d1")["stated_clear"]
    assert any("d1 door_clear_width not measured" in p for p in r.recording_problems(rec))
    # house 5's sliding door: no maker's clear opening is drawn, so its height comes back not measured
    five = r.drawing("5_basement_window_well")
    assert [x["clear"] for x in five["doors"]] == [None]
    rec = described("5_basement_window_well")
    assert r.recording_problems(rec) == []
    rec["interior"]["doors"][0]["stated_clear"] = {"width": 3.0, "height": 80 / 12, "source": "made up"}
    assert any("de door_clear_height = 80.0: not in step 6" in p for p in r.recording_problems(rec))


def test_house_4s_loft_guard_and_stair_drawn_and_read_measure_as_worked_by_hand():
    d = r.drawing("4_loft")
    loft = next(x for x in d["rooms"] if x["id"] == "loft")
    assert min(x for x, _ in loft["floor"]) == pytest.approx(24.5)    # drawn clear of the bedroom it is over
    assert "within the height of main" in d["notes"][0]
    assert d["levels"][0]["wall_height"] == pytest.approx(9.0)        # the bedroom's walls stop at the loft's level
    (g,) = d["guards"]
    assert (g["level"], g["top"], g["length"]) == (9.0, pytest.approx(3.0), pytest.approx(4.0))
    assert g["balusters"]["count"] == 9 and g["balusters"]["width"] * 12 == pytest.approx(1.5)
    assert g["balusters"]["spacing"] * 12 == pytest.approx(5.0) and g["balusters"]["first"] * 12 == pytest.approx(3.5)
    rec = described("4_loft")
    assert r.recording_problems(rec) == []
    lg = rec["interior"]["guards"][0]
    lg["members"].pop()                                               # a baluster missed: a wider gap
    assert any("lg guard_opening_sphere = 3.5, expected" not in p and "lg guard_opening_sphere" in p
               for p in r.recording_problems(rec))
    rec = described("4_loft")
    del rec["interior"]["guards"]
    assert any("guard not read" in p for p in r.recording_problems(rec))


def test_house_3s_tall_riser_is_drawn_at_the_head_and_measured_as_drawn():
    d = r.drawing("3_tall_riser")
    s = d["stairs"][0]
    assert (s["risers"], s["riser"], s["base"], s["head_top"]) == (13, 0.625, -8.25, 0.0)
    assert s["head_above_run"] == pytest.approx(0.125)                 # 99 in = 13 x 7.5 + 1.5 at the head
    assert s["open_sides"] == ["right"] and [w["side"] for w in s["walls"]] == ["left"]   # the guard: step 5
    assert "1.5 in above the run's top" in d["notes"][0]
    rec = described("3_tall_riser")
    # the last riser measured to the floor at the head (R318.7.5.1, Q1): -0.75 ft to 0, 9 in; the hand-worked
    # answers (riser 9, variation 9 - 7.5 = 1.5, total 99, 13 risers) hold with the tall riser at the head
    top = rec["interior"]["stairs"][0]["nosings"]
    assert (top[-2][0][2], top[-1][0][2]) == (pytest.approx(-0.75), 0.0)
    assert r.recording_problems(rec) == []
    got = r.measure(rec["interior"])["parts"]["stair"][0]
    assert (got["measures"]["stair_riser_height"], got["measures"]["stair_riser_variation"]) == (9.0, 1.5)
    s = rec["interior"]["stairs"][0]                                   # a reader sending the run's own top instead
    s["nosings"] = flight({**d["stairs"][0], "head_top": d["stairs"][0]["head_top"] - 0.125})["nosings"]
    problems = r.recording_problems(rec)
    assert any("s stair_riser_height = 7.5, expected 9.0" in p for p in problems)
    assert any("s stair_riser_variation = 0.0, expected 1.5" in p for p in problems)
    rec = described("3_tall_riser")                                    # and one sending none: not measured fails too
    del rec["interior"]["stairs"][0]["nosings"]
    assert any("s stair_riser_height not measured" in p for p in r.recording_problems(rec))


def test_house_3_as_drawn_fails_r318_7_5_1_once_nothing_else_is_open():
    """The eval: house 3 as the Revit reader sends it (its 9 in riser at the head, `spiral: false`) through the real
    checker. R318.7.5.1: "The riser height shall be not more than 8 1/4 inches" (9 > 8.25) and "The greatest riser
    height within any flight of stairs shall not exceed the smallest by more than 3/8 inch" (9 - 7.5 = 1.5 > 0.375):
    both fail. Each rule's one remaining open input is R315.5's sleeping-loft stair (review_when), which the house
    doesn't state: with the architect's "no sleeping lofts" tick both are does_not_comply, without it both need
    review (never a pass either way)."""
    from design_checker.check import check_site
    sys.path.insert(0, str(r.REPO / "packages/permit_sheets"))
    from permit_sheets import goldens

    def statuses(ticked):
        interior = described("3_tall_riser")["interior"]
        if ticked:
            interior["has_none"] = [{"kind": "sleeping_loft", "source": "ticked by the architect (test)"}]
        got = check_site(goldens.site(), dict(goldens.FACTS), name="3", today=goldens.DATE, interior=interior)
        return {i["rule"]: (i["status"], i["reason"]) for i in got["view"]["items"]
                if i["rule"] in ("general.r318_7_5_1_stair_riser_height_max", "general.r318_7_5_1_stair_riser_variation_max")}

    ticked = statuses(True)
    assert [s for s, _ in ticked.values()] == ["does_not_comply", "does_not_comply"]
    for status, reason in statuses(False).values():
        assert status == "needs_review" and "serves sleeping loft not measured" in reason


def test_a_stair_in_a_house_not_yet_in_the_stairs_step_isnt_drawn():
    d = r.drawing("5_basement_window_well")
    assert d["stairs"] == [] and "stairs" in d["not_drawn"]


def test_a_value_out_by_more_than_a_millionth_fails():
    rec = described("1_ranch_compliant")
    rec["interior"]["rooms"][0]["floor"][1][0] += 0.01               # bed1 a hair wider
    assert any("bed1 sleeping_room_floor_area" in p for p in r.recording_problems(rec))
    rec = described("1_ranch_compliant")
    w1 = next(o for o in rec["interior"]["openings"] if o["id"] == "host-w1")
    w1["stated_clear"]["bottom"] += 1 / 12                           # the sill read an inch high
    assert any("w1 opening_sill_height" in p for p in r.recording_problems(rec))


def test_an_in_scope_measure_not_measured_fails():
    rec = described("2_two_story_small_window")
    del next(x for x in rec["interior"]["rooms"] if x["id"] == "host-bed4")["ceilings"]
    problems = r.recording_problems(rec)
    assert any("bed4 floor_area_drawn" not in p and "bed4 least_ceiling_height not measured" in p for p in problems)
    rec = described("5_basement_window_well")
    del next(o for o in rec["interior"]["openings"] if o["id"] == "host-we2")["stated_clear"]
    assert any("we2 opening_net_clear_area not measured" in p for p in r.recording_problems(rec))


def test_a_measure_out_of_scope_given_a_value_fails():
    rec = described("1_ranch_compliant")
    for o in rec["interior"]["openings"]:
        o["ground_outside"] = -8 / 12                                # a ground nobody drew: grade-floor is in no step yet
    assert any("w1 opening_at_grade = True: not in step 6" in p for p in r.recording_problems(rec))
    rec = described("5_basement_window_well")
    we1 = next(o for o in rec["interior"]["openings"] if o["id"] == "host-we1")
    we1.update(ground_outside=0, area_well={"floor_elevation": -66 / 12, "width": 40 / 12, "projection": 3})
    assert any("we1 area_well_area" in p for p in r.recording_problems(rec))


def test_a_kind_of_a_later_step_must_not_be_read():
    rec = described("5_basement_window_well")
    rec["interior"]["stairs"] = []                                   # "none" said by a reader that can't know it
    assert any("stair read (0 parts): not in step 6" in p for p in r.recording_problems(rec))
    rec = described("3_tall_riser")
    rec["interior"]["doors"] = []
    assert any("egress_door read (0 parts): not in step 4" in p for p in r.recording_problems(rec))


def test_an_empty_list_the_house_gives_must_come_back_empty():
    # step 6: the tick "this house has no ..." read back as the empty list, never left out, never a part
    for name, key, kind in (("1_ranch_compliant", "stairs", "stair"), ("2_two_story_small_window", "guards", "guard"),
                            ("4_loft", "doors", "egress_door"), ("5_basement_window_well", "guards", "guard")):
        rec = described(name)
        assert rec["interior"][key] == [] and r.recording_problems(rec) == []
        del rec["interior"][key]                                    # the tick not read
        assert any(f"{kind} not read" in p for p in r.recording_problems(rec)), name


def test_what_the_house_has_none_of_must_be_the_houses_own():
    rec = described("1_ranch_compliant")                             # a claim no hand-worked house makes
    rec["interior"]["has_none"] = [{"kind": "deck_porch_or_cantilever_over_escape_opening", "source": "ticked (test)"}]
    problems = r.recording_problems(rec)
    assert any("has none of ['deck_porch_or_cantilever_over_escape_opening']" in p and "expected []" in p for p in problems)
    rec = described("1_ranch_compliant")                             # a claim of a part kind out of scope, too
    rec["interior"]["has_none"] = [{"kind": "ramp", "source": "ticked (test)"}]
    problems = r.recording_problems(rec)
    assert any("ramp read (0 parts): not in step 6" in p for p in problems)
    assert any("has none of ['ramp']" in p for p in problems)
    rec = described("1_ranch_compliant")                             # sent but not taken (no source) is not the house's either
    rec["interior"]["has_none"] = [{"kind": "ramp"}]
    assert any("has none of ['ramp'] (taken: [])" in p for p in r.recording_problems(rec))


def test_a_kind_in_scope_not_read_fails_and_says_why():
    rec = described("1_ranch_compliant")
    del rec["interior"]["rooms"][2]["sleeping"]                      # one room unmarked: no room read
    assert any("sleeping_room not read" in p for p in r.recording_problems(rec))


def test_a_part_missing_extra_or_in_the_wrong_room_fails():
    rec = described("1_ranch_compliant")
    rec["interior"]["openings"] = [o for o in rec["interior"]["openings"] if o["id"] != "host-w2"]
    assert any("w2 wasn't measured" in p for p in r.recording_problems(rec))
    rec = described("1_ranch_compliant")
    next(o for o in rec["interior"]["openings"] if o["id"] == "host-w3")["escape"] = True     # the living room's
    assert any("not checked (in a room that isn't a sleeping room) are ['w3']" in p for p in r.recording_problems(rec))
    next(o for o in rec["interior"]["openings"] if o["id"] == "host-w3")["room"] = "host-bed1"
    assert any("w3 measured, but the house has no such" in p for p in r.recording_problems(rec))
    rec = described("1_ranch_compliant")
    next(o for o in rec["interior"]["openings"] if o["id"] == "host-w1")["room"] = "host-bed2"
    assert any("w1 is within bed2, expected bed1" in p for p in r.recording_problems(rec))


def test_the_recording_must_say_what_it_is():
    rec = described("1_ranch_compliant")
    assert r.recording_problems({**rec, "house": "7_nowhere"})[0].startswith("test/7_nowhere: not a house of any step")
    assert any("recorded for step 3, not step 6" in p for p in r.recording_problems({**rec, "step": 3}))
    two = described("2_two_story_small_window")                     # a step-5 recording of a house now in step 6
    assert any("recorded for step 5, not step 6" in p for p in r.recording_problems({**two, "step": 5}))
    assert any("says how it was recorded" in p for p in r.recording_problems({**rec, "recorded": {"by": "x"}}))
    assert any("no id map" in p for p in r.recording_problems({**rec, "ids": None}))
    twice = copy.deepcopy(rec)
    twice["ids"]["w2"] = twice["ids"]["w1"]
    assert any("recorded as the same element" in p for p in r.recording_problems(twice))


def test_a_host_with_any_recording_has_every_house_of_the_step():
    assert r.coverage_problems({"revit": {"1_ranch_compliant": {}}}) == [
        "revit: no recording for 2_two_story_small_window, 3_tall_riser, 4_loft, 5_basement_window_well, "
        "6_door_stated_clear, orangetown_ny_80_south_william"]
    assert r.coverage_problems({"revit": {h: {} for h in r.STEP_HOUSES}}) == []
    # the real house too: its recording is required, not just checked when present
    assert r.coverage_problems({"revit": {h: {} for h in r.STEP_HOUSES if h != ORANGETOWN}}) == [
        f"revit: no recording for {ORANGETOWN}"]


def test_every_committed_recording_passes():
    recorded = r.recordings()
    assert r.coverage_problems(recorded) == []
    for host, by in recorded.items():
        for name, rec in by.items():
            assert rec.get("house") == name and rec.get("host") == host, (host, name)
            assert r.recording_problems(rec) == [], (host, name)


def test_the_drawing_is_the_houses_own_data():
    d = r.drawing("1_ranch_compliant")
    assert [x["id"] for x in d["rooms"]] == ["bed1", "bed2", "living"]
    level = d["levels"][0]
    assert level["box"] == [[0, 0], [23, 25]] and level["fillers"] == [[[12, 10], [23, 11]]]   # the 12 in between rooms
    assert sorted(level["separations"]) == [[[0, 11], [12, 11]], [[12, 0], [12, 10]]]
    w1 = next(w for w in d["windows"] if w["id"] == "w1")
    assert (w1["width"], w1["height"], w1["sill"]) == (26 / 12, 3.0, 2.5)                    # its frame, from house.yaml
    assert w1["clear"]["width"] * 12 == pytest.approx(24.5) and w1["clear"]["offset"] == 0   # the measuring code's
    assert d["not_drawn"] == [] and d["step"] == 6 and d["stairs"] == [] and d["guards"] == []
    assert [x["id"] for x in d["doors"]] == ["d1", "d2"] and {x["room"] for x in d["doors"]} == {"living"}
    assert d["doors"][1]["clear"] is None                            # the back door: not drawn, so nothing worked out
    assert level["wall_height"] == pytest.approx(8 + 1 / 12)                                # up to the ceilings' top
    basement = r.drawing("5_basement_window_well")["levels"][0]
    assert basement["elevation"] + basement["wall_height"] < 0                              # never up past the level over it
    we2 = next(w for w in r.drawing("5_basement_window_well")["windows"] if w["id"] == "we2")
    assert we2["clear"]["source"] == "maker's data sheet (made up)" and we2["clear"]["offset"] == 0


def test_the_command_line_prints_each_house_and_a_recordings_problems(tmp_path):
    out = subprocess.run([sys.executable, "-m", "model_measurement.interior.recordings", "draw"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout.splitlines()
    assert [json.loads(line)["house"] for line in out] == list(r.STEP_HOUSES)
    good = tmp_path / "1_ranch_compliant.json"
    good.write_text(json.dumps(described("1_ranch_compliant")), encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "model_measurement.interior.recordings", "check", str(good)],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert json.loads(out) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    out = subprocess.run([sys.executable, "-m", "model_measurement.interior.recordings", "check", str(bad)],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    assert json.loads(out)[0].startswith("not JSON")


def test_the_real_houses_claims_must_come_back_and_bring_only_their_own_measures():
    rec = described(ORANGETOWN)
    assert len(rec["interior"]["has_none"]) == 7 and r.recording_problems(rec) == []
    # a claim the reader didn't send (blocked): its kind isn't taken, so its part kinds aren't read and the openings
    # lose the measure it brings
    rec["interior"]["has_none"] = [c for c in rec["interior"]["has_none"] if c["kind"] != "patio_cover"]
    problems = r.recording_problems(rec)
    assert any("has none of" in p and "patio_cover" in p for p in problems)
    assert any("m1 opening_into_patio_cover not measured" in p for p in problems)
    # a claim the house doesn't make (the drawings show a basement): refused
    rec = described(ORANGETOWN)
    rec["interior"]["has_none"].append({"kind": "basement", "source": "ticked (test)"})
    assert any("has none of" in p and "basement" in p for p in r.recording_problems(rec))
    # step 5's scope (no claims) would refuse the empty lists the claims bring: the claims are what put them in scope
    assert r.claimed({"emergency_escape_opening": set()}, ["ramp"]) == {"emergency_escape_opening": set(), "ramp": set()}
    assert r.claimed({"emergency_escape_opening": set(), "stair": set()}, ["sleeping_loft"]) == {
        "emergency_escape_opening": set(), "stair": {"stair_serves_sleeping_loft"}, "sleeping_loft": set(),
        "loft_room": set()}
