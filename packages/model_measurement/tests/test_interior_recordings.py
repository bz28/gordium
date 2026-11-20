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
    ids = {x["id"]: f"host-{x['id']}" for x in d["rooms"] + d["windows"]}
    return {"host": "test", "house": name, "step": r.STEP, "ids": ids,
            "recorded": {"by": "test_interior_recordings", "date": "2026-11-20", "tool": "python"},
            "interior": {"format": "gordium.interior/1", "units": "ft", "rooms": rooms, "openings": openings}}


@pytest.mark.parametrize("name", r.STEP_HOUSES)
def test_a_house_described_as_drawn_passes(name):
    assert r.recording_problems(described(name)) == []


def test_the_steps_scope_is_the_design_notes():
    assert r.STEP_HOUSES == ("1_ranch_compliant", "2_two_story_small_window", "5_basement_window_well")
    assert r.SCOPE == {
        "sleeping_room": {"sleeping_room_floor_area", "floor_area_drawn", "least_ceiling_height"},
        "emergency_escape_opening": {"opening_net_clear_width", "opening_net_clear_height", "opening_net_clear_area",
                                     "opening_sill_height", "opening_is_door", "opening_door_hinged_or_sliding"}}


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
        o["ground_outside"] = -8 / 12                                # a ground nobody drew: grade-floor is not in step 3
    assert any("w1 opening_at_grade = True: not in step 3" in p for p in r.recording_problems(rec))
    rec = described("5_basement_window_well")
    we1 = next(o for o in rec["interior"]["openings"] if o["id"] == "host-we1")
    we1.update(ground_outside=0, area_well={"floor_elevation": -66 / 12, "width": 40 / 12, "projection": 3})
    assert any("we1 area_well_area" in p for p in r.recording_problems(rec))


def test_a_kind_of_a_later_step_must_not_be_read():
    rec = described("2_two_story_small_window")
    rec["interior"]["stairs"] = []                                   # "none" said by a reader that can't know it
    assert any("stair read (0 parts)" in p for p in r.recording_problems(rec))


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
    assert r.recording_problems({**rec, "house": "3_tall_riser"})[0].startswith("test/3_tall_riser: not a house of step 3")
    assert any("recorded for step 4" in p for p in r.recording_problems({**rec, "step": 4}))
    assert any("says how it was recorded" in p for p in r.recording_problems({**rec, "recorded": {"by": "x"}}))
    assert any("no id map" in p for p in r.recording_problems({**rec, "ids": None}))
    twice = copy.deepcopy(rec)
    twice["ids"]["w2"] = twice["ids"]["w1"]
    assert any("recorded as the same element" in p for p in r.recording_problems(twice))


def test_a_host_with_any_recording_has_every_house_of_the_step():
    assert r.coverage_problems({"revit": {"1_ranch_compliant": {}}}) == [
        "revit: no recording for 2_two_story_small_window, 5_basement_window_well"]
    assert r.coverage_problems({"revit": {h: {} for h in r.STEP_HOUSES}}) == []


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
    assert d["not_drawn"] == ["doors"]
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
