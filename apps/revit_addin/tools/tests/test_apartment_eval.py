"""The Building Code eval's marks file (test_data/test_sites/new_york/ithaca_city/four_unit_apartment/eval_marks.yaml)
says exactly what apartment.yaml says, for the rooms and doors the build data places: so the model checked in Revit
is the interior the Python eval checks (design_checker/tests/test_four_unit_apartment.py)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "evals"))

import eval_marks_request as marks_tool  # noqa: E402
import make_ny_build_data as build  # noqa: E402

FOLDER = REPO / "test_data/test_sites/new_york/ithaca_city/four_unit_apartment"
MARKS_CS = (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")
PROJECT_MARKS = set(re.findall(r'"(Gordium: [^"]+)", new\("[0-9a-f-]+"\)', MARKS_CS))


def load(name):
    return yaml.safe_load((FOLDER / name).read_text(encoding="utf-8"))


def test_every_room_is_marked_as_the_building_says():
    marks, data, source = load("eval_marks.yaml"), json.loads((FOLDER / "revit_build_data.json").read_text("utf-8")), \
        load("apartment.yaml")
    by_id = {r["id"]: r for r in source["rooms"]}
    assert [m["number"] for m in marks["rooms"]] == [r["number"] for r in data["rooms"]]
    for m, r in zip(marks["rooms"], data["rooms"]):
        want = by_id[r["house_id"][2:]]
        assert (m["name"], m["use"], m["lockable"], m["pass_through"]) == \
            (r["name"], want["use"], want["lockable"], want["pass_through"])
    made = marks_tool.request(marks, "built.rvt", "marked.rvt")
    assert {e["mark"] for e in made["marks"] if "room" in e} == {"Gordium: Sleeping room", "Gordium: Use",
                                                                 "Gordium: Can be locked", "Gordium: Pass through"}


def test_the_exits_are_the_stair_enclosure_doors_and_only_those():
    marks, data = load("eval_marks.yaml"), json.loads((FOLDER / "revit_build_data.json").read_text("utf-8"))
    exits = {e["door"]: e["exit"] for e in marks["exits"]}
    enclosure = {f"D{k:02d}" for k, d in enumerate(data["doors"], start=1) if d["house_id"][2:] in ("W", "E")}
    assert set(exits) == enclosure == {"D01", "D02", "D07", "D08"}
    assert set(exits.values()) == {"Exit stair enclosure"}
    interior = build.interior_of()
    assert sorted(d["id"] for d in interior["doors"] if "exit_kind" in d) == ["L1E", "L1W", "L2E", "L2W"]


def test_the_project_marks_are_the_add_ins_and_state_the_building_block():
    marks = load("eval_marks.yaml")
    given = {e["mark"]: e["value"] for e in marks["project_information"]}
    assert set(given) <= PROJECT_MARKS
    # the add-in's BuildingFacts reads these two into the building block apartment.yaml states
    assert [g.strip() for g in given["Gordium: Occupancy groups"].split(",")] == \
        load("apartment.yaml")["building"]["occupancy_groups"]
    assert given["Gordium: Sprinkler system"].lower() == load("apartment.yaml")["building"]["sprinkler_system"]
    assert marks_tool.check_request(marks, "m.rvt")["marks"]["Gordium: Stories"] == 2


def test_the_real_workers_answer_compares_as_worked_out(tmp_path):
    """The eval building's interior as the Revit reader reads it, sent as Check my project sends it (a stand-in site:
    no egress rule reads the outside), compared with expected.yaml by the comparison Ben runs on the Revit result."""
    import compare_check_result as compare
    from design_checker.__main__ import answer

    site = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-3a",
             "use": "multiple_family", "lot_surveyed": False, "street_line": [[[0, 0], [60, 0]]]}
    got = answer({"id": 1, "cmd": "check_site", "protocol": "1.3", "site": site, "facts": facts,
                  "interior": build.interior_of()})
    assert got["ok"], got.get("error")
    (tmp_path / "a.json").write_text(json.dumps(got), encoding="utf-8")
    made = compare.compare_apartment(compare.result_of(tmp_path / "a.json"))
    assert made["ok"], made["summary"]
    # every rule of the rulebook, each worked out in expected.yaml (2026-11-23: 74; section group 4a, 2026-11-25:
    # 77, Table 1020.3's width rule and its two-or-more-groups flag, and 1020.3's corridor capacity)
    assert made["summary"]["as_worked_out"] == 309   # group 4b: 88, Table 1020.2's seven rows, its two-or-more-groups and Group I-2 flags, the fire-partition and hoistway flags; group 4c, 2026-11-25: 91, 1020.4's, 1020.6's and 1020.7's flags; group 5a, 2026-11-25: 93, 1005.3.1's stairway and 1005.3.2's other-component flags (the corridor capacity was 4a's); group 5b: 96, 1005.4's, 1005.5's and 1005.6's flags; group 5c: 99, 1005.7.1's, 1005.7.2's and 1005.7.3's flags; group 6a: 104, 1010.1.1's door width and height rules, its capacity flag, 1010.1's and 1010.1.1.1's flags; group 6b: 106, 1010.1.2's door-kind flag and 1010.1.2.1's swing rule; Chapter 7 part a, 2026-11-26: 134, the 28 fire-barrier and shaft-enclosure flags (703.2.1.1, 703.5, 707, 713); Chapter 7 part b: 158, the 24 opening-protective flags (716.1, Tables 716.1(1) to (3), 716.2 to 716.2.4); part c: 189, the 31 fire partition, smoke barrier and smoke partition flags (708 to 710); part d: 212, the 23 floor, vertical opening and penetration flags (711, 712, 714.1 to 714.5); Chapter 9 part a, 2026-11-27: 221, its three sprinkler rules (903.2.5.1, 903.2.6, 903.2.8) and six flags; part b: 249, its eight per-room sprinkler rules (903.2.1.1 to 903.2.9) and 20 flags; part c: 274, its two voice/alarm rules (907.2.1.1, 907.2.3) and 23 flags; part d: 309, its 35 flags (907.2.6 to 907.2.11, 907.5.2.2)
    assert made["summary"]["as_worked_out"] == len(load("expected.yaml")["results"])
    # and a kinder verdict than the hand-work is named a false pass, never ok
    got["result"]["egress"]["results"]["general.bc_table_1006_3_4_1__r2_dwelling_units"] = "pass"
    (tmp_path / "b.json").write_text(json.dumps(got), encoding="utf-8")
    worse = compare.compare_apartment(compare.result_of(tmp_path / "b.json"))
    assert not worse["ok"] and worse["summary"]["false_passes"] == ["general.bc_table_1006_3_4_1__r2_dwelling_units"]


def test_every_door_has_its_types_clear_opening_stamped_as_the_description_reads_it():
    """The first Revit run (2026-11-22): no door type's clear opening was stamped, so the reader sent no door's plan
    (RouteReader: a route passes a door only through its type's confirmed clear width) and no story's routes were
    measured. Every door the build places is in a door_types entry, with the width the description reads."""
    marks, data = load("eval_marks.yaml"), json.loads((FOLDER / "revit_build_data.json").read_text("utf-8"))
    stamped = {d: t for t in marks["door_types"] for d in t["doors"]}
    assert set(stamped) == {f"D{k:02d}" for k in range(1, len(data["doors"]) + 1)}
    door = load("apartment.yaml")["door"]
    for k, d in enumerate(data["doors"], start=1):
        t = stamped[f"D{k:02d}"]
        assert (t["leaf_in"], t["clear_width_in"], t["clear_height_in"]) == \
            (d["width_in"], door["clear_width_in"], door["clear_height_in"])
    made = marks_tool.request(marks, "built.rvt", "marked.rvt")
    assert sum("clear" in e for e in made["marks"]) == len(data["doors"])
    assert all(d["plan"]["clear_width"] == d["stated_clear"]["width"] == door["clear_width_in"] / 12
               for d in build.interior_of()["doors"])
