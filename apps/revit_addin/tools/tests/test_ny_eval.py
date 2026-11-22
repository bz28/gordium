"""The New York Revit eval: its marks files make the requests the add-in reads, agree with the build data and the
description they stand for, and the comparison (compare_check_result.py) names every difference on synthetic results
and on the real checker's answer for each building as Revit will read it."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS / "evals"))

import compare_check_result as compare  # noqa: E402
import eval_marks_request as marks_tool  # noqa: E402

HOUSE = REPO / "test_data/real_houses/orangetown_ny_80_south_william"
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd"
MARKS_CS = (REPO / "apps/revit_addin/src/Gordium.Revit.Reading/Marks.cs").read_text(encoding="utf-8")
# the add-in's own words, read from Marks.cs (never retyped): an operation's word -> the description's, a "This house
# has no ..." tick's name -> its has_none kind
OPERATIONS = dict(re.findall(r'\("([^"]+)", "(\w+)", (?:"\w+"|null)\)', MARKS_CS))
NONE_TICKS = {f"Gordium: This house has no {name}": kind
              for name, kind in re.findall(r'NoneTick\(\s*"([^"]+)", "[0-9a-f-]+",\s*"has_none: (\w+)"', MARKS_CS)}
PROJECT_MARKS = set(re.findall(r'"(Gordium: [^"]+)", new\("[0-9a-f-]+"\)', MARKS_CS)) | set(NONE_TICKS)


def load(folder: Path, name: str):
    return yaml.safe_load((folder / name).read_text(encoding="utf-8"))


def build(folder: Path) -> dict:
    return json.loads((folder / "revit_build_data.json").read_text(encoding="utf-8"))


def lot_edges(data: dict) -> list:
    ring = data["lot"]["outline"]
    return [(tuple(a), tuple(b)) for a, b in zip(ring, ring[1:])]


def street(mark: str) -> tuple:
    x0, y0, x1, y1 = (float(v) for v in mark.split())
    return (x0, y0), (x1, y1)


# ---- the marks files make the add-in's requests --------------------------------------------------------------------

def test_the_operations_and_ticks_are_read_from_the_add_in():
    assert OPERATIONS["Double hung"] == "double_hung" and OPERATIONS["Side-hinged door"] == "side_hinged_door"
    assert NONE_TICKS["Gordium: This house has no ship ladders"] == "ships_ladder"
    assert len(NONE_TICKS) == 8 and "Gordium: Street edge" in PROJECT_MARKS


def test_the_orangetown_marks_are_house_yamls_for_every_room_window_and_door():
    marks, data, house = load(HOUSE, "eval_marks.yaml"), build(HOUSE), load(HOUSE, "house.yaml")
    made = marks_tool.request(marks, "built.rvt", "marked.rvt")
    entries = made["marks"]
    # every room the build places, by its number, with its sleeping mark only (a house carries no route marks)
    rooms = {r["number"]: r for r in data["rooms"]}
    assert sorted((e["room"], e["value"]) for e in entries if "room" in e) == \
        sorted((n, r["sleeping"]) for n, r in rooms.items())
    assert {e["mark"] for e in entries if "room" in e} == {"Gordium: Sleeping room"}
    assert [m["name"] for m in marks["rooms"]] == [rooms[m["number"]]["name"] for m in marks["rooms"]]
    # every window: its Mark is the build's (WN01... in order) for the same house.yaml opening, its marks house.yaml's
    given = {o["id"]: o for o in house["openings"]}
    for k, w in enumerate(data["windows"], start=1):
        m = next(x for x in marks["windows"] if x["window"] == f"WN{k:02d}")
        assert m["id"] == w["house_id"]
        assert (m["escape"], OPERATIONS[m["operation"]]) == (given[w["house_id"]]["escape"], given[w["house_id"]]["operation"])
    assert len(marks["windows"]) == len(data["windows"]) == 14
    door, given_door = marks["doors"][0], house["doors"][0]
    assert (door["door"], door["id"], door["exit_door"], door["escape"]) == ("D01", given_door["id"], given_door["exit"], False)
    assert OPERATIONS[door["operation"]] == given_door["operation"] + "_door"
    assert len(entries) == 17 + 14 * 2 + 3


def test_the_orangetown_check_request_ticks_house_yamls_claims_and_a_street_edge_of_the_lot():
    marks, data, house = load(HOUSE, "eval_marks.yaml"), build(HOUSE), load(HOUSE, "house.yaml")
    check = marks_tool.check_request(marks, "marked.rvt")
    assert check["model"] == "marked.rvt"
    assert set(check["marks"]) <= PROJECT_MARKS
    assert {NONE_TICKS[k] for k, v in check["marks"].items() if k in NONE_TICKS and v} == {c["kind"] for c in house["has_none"]}
    assert "Gordium: This house has no stairs" not in check["marks"]        # its stairs aren't drawn: never "none"
    assert "Gordium: These are all the stairs" not in check["marks"]
    a, b = street(check["marks"]["Gordium: Street edge"])
    assert (a, b) in lot_edges(data) and a[1] == b[1] == min(y for _, y in data["lot"]["outline"])     # the south edge


def test_the_106_check_request_states_the_repositorys_own_lot_facts():
    marks, data = load(SITE, "eval_marks.yaml"), build(SITE)
    facts = load(SITE, "spreadsheet_design_model_facts.yaml")["lot_facts"]
    check = marks_tool.check_request(marks, "built.rvt")["marks"]
    assert set(check) <= PROJECT_MARKS
    assert (check["Gordium: Zone"], check["Gordium: Use"]) == (facts["zone"], facts["use"])
    assert (check["Gordium: Lot surveyed"], check["Gordium: Corner lot"]) == (facts["lot_surveyed"], facts["corner_lot"])
    assert street(check["Gordium: Street edge"]) == tuple(tuple(p) for p in facts["street_line"][0])
    assert street(check["Gordium: Street edge"]) in lot_edges(data)
    assert check["Gordium: Ground from"] == "Spot grades"
    assert marks_tool.request(marks, "built.rvt", "marked.rvt")["marks"] == []       # nothing but Project Information
    design = load(SITE, "spreadsheet_design.yaml")
    assert {d["row"] for d in marks["expected_differences"]} | {n["row"] for n in marks["notes"]} <= set(design["compare"])


def test_a_project_mark_without_its_reason_or_given_twice_stops_the_tool():
    with pytest.raises(marks_tool.BadMarks):
        marks_tool.check_request({"project_information": [{"mark": "Gordium: Zone", "value": "R-1b"}]}, "m")
    with pytest.raises(marks_tool.BadMarks):
        marks_tool.check_request({"project_information": [{"mark": "Gordium: Zone", "value": "R-1b", "why": "x"}] * 2}, "m")
    with pytest.raises(marks_tool.BadMarks):
        marks_tool.request({"by": "x", "windows": [{"window": "WN01", "operation": "Casement"}]}, "m", "c")   # no escape


def test_the_tool_writes_all_three_requests(tmp_path):
    out, built, check = tmp_path / "set.json", tmp_path / "build.json", tmp_path / "check.json"
    assert marks_tool.main([str(HOUSE / "eval_marks.yaml"), "--model", "C:/t/built.rvt", "--save-as", "C:/t/marked.rvt",
                            "--out", str(out), "--build-data", "C:/t/data.json", "--build-out", str(built),
                            "--check-out", str(check)]) == 0
    assert json.loads(built.read_text(encoding="utf-8")) == {"data": "C:/t/data.json", "save_as": "C:/t/built.rvt", "corrections": []}
    assert json.loads(check.read_text(encoding="utf-8"))["model"] == "C:/t/marked.rvt"
    assert json.loads(out.read_text(encoding="utf-8"))["save_as"] == "C:/t/marked.rvt"


# ---- the comparison, on synthetic results ------------------------------------------------------------------------

CHECKER = {"complies": "pass", "does_not_comply": "fail", "needs_review": "needs_review", "not_applicable": "not_applicable"}


def predicted_result() -> dict:
    """A result whose every egress rule is the hand-check's prediction (what the checker says on house.yaml), its
    has_none items the seven claims, ticked."""
    hand = load(HOUSE, "hand_check.yaml")
    return {"statuses": {"R-1b.use": "complies"},
            "egress": {"results": {r["id"]: CHECKER.get(r["predicted"], r["predicted"]) for r in hand["rules"]}},
            "view": {"items": [{"id": f"egress.has_none.{c['kind']}", "status": "not_applicable", "name": c["kind"]}
                               for c in load(HOUSE, "house.yaml")["has_none"]]},
            "sections": [{"key": "new_york/new_york_state", "state": "needs_review", "summary": "..."}]}


def run(tmp_path, building: str, result: dict, name="answer.json") -> dict:
    path = tmp_path / name
    path.write_text(json.dumps({"result": result}), encoding="utf-8")
    return compare.COMPARE[building](compare.result_of(path))


def test_a_result_as_predicted_compares_with_no_false_pass(tmp_path):
    made = run(tmp_path, "orangetown", predicted_result())
    s = made["summary"]
    assert made["ok"] and s["rules"] == 115 and s["as_predicted"] == 115
    assert s["same_as_truth"] == 1 + 63 + 33                     # evaluation.md: the checker agrees on 97
    assert not s["false_passes"] and not s["not_as_predicted"] and not s["not_in_the_result"]
    # every rule more cautious than the truth names evaluation.md's reason for it
    cautious = [r for r in made["rules"] if r["gordium"] != r["truth"]]
    assert len(cautious) == 18 and all("as predicted: " in r["difference"] and "evaluation.md, " in r["difference"]
                                       for r in cautious)
    # the three readings come back as the architect's ticks: each named
    named = [c["item"] for c in made["has_none_items"] if "difference" in c]
    assert sorted(named) == ["egress.has_none.habitable_attic", "egress.has_none.patio_cover", "egress.has_none.ships_ladder"]


def test_a_false_pass_a_rule_not_as_predicted_and_a_missing_rule_are_each_named(tmp_path):
    result = predicted_result()
    results = result["egress"]["results"]
    results["general.r319_2_1_escape_opening_min_net_clear_area"] = "pass"      # truth: needs review
    results["general.r315_2_sleeping_loft_floor_area_limit"] = "needs_review"   # predicted: not applicable
    results["general.r318_7_5_1_stair_riser_height_max"] = "fail"               # truth: needs review
    del results["general.r318_2_egress_door_side_hinged"]
    results["general.made_up_rule"] = "pass"
    made = run(tmp_path, "orangetown", result)
    s = made["summary"]
    assert not made["ok"]
    assert s["false_passes"] == ["general.r319_2_1_escape_opening_min_net_clear_area"]
    assert set(s["not_as_predicted"]) == {"general.r315_2_sleeping_loft_floor_area_limit", "general.r318_7_5_1_stair_riser_height_max"}
    assert s["not_in_the_result"] == ["general.r318_2_egress_door_side_hinged"]
    assert s["not_in_the_hand_check"] == ["general.made_up_rule"]
    by = {r["rule"]: r for r in made["rules"]}
    assert by["general.r319_2_1_escape_opening_min_net_clear_area"]["difference"].startswith("FALSE PASS")
    assert by["general.r318_7_5_1_stair_riser_height_max"]["difference"].startswith("FALSE FAIL")


def test_not_applicable_where_the_truth_applies_is_a_false_pass(tmp_path):
    result = predicted_result()
    result["egress"]["results"]["general.r318_2_egress_door_clear_width"] = "not_applicable"
    assert run(tmp_path, "orangetown", result)["summary"]["false_passes"] == ["general.r318_2_egress_door_clear_width"]


def test_the_result_is_read_from_the_trial_log_by_model(tmp_path):
    log = tmp_path / "results.jsonl"
    other = predicted_result()
    other["egress"]["results"]["general.r318_2_egress_door_side_hinged"] = "needs_review"
    lines = [{"what": "check_project", "file": "C:/t/orangetown_marked.rvt", "answer": json.dumps(predicted_result())},
             {"what": "build_model", "saved": "x.rvt"},
             {"what": "check_project", "file": "C:/t/other.rvt", "answer": json.dumps(other)},
             {"what": "check_project", "file": "C:/t/none.rvt", "missing": ["Gordium: Zone: ..."]}]
    log.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    assert compare.compare_orangetown(compare.result_of(log, "orangetown_marked.rvt"))["ok"]
    assert not compare.compare_orangetown(compare.result_of(log))["ok"]          # the last answered: other.rvt
    with pytest.raises(compare.BadResult):
        compare.result_of(log, "none.rvt")                                       # nothing was sent for it
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"rows": []}), encoding="utf-8")
    with pytest.raises(compare.BadResult):
        compare.result_of(bad)


def spreadsheet_like(**changes) -> dict:
    """A result with the architects' own answer on every row (each side yard by its compass side), changed as asked."""
    statuses = {"R-1b.use": "complies", "R-1b.lot_area_one_family_detached": "complies",
                "R-1b.lot_width_one_family_detached": "complies", "R-1b.stories": "complies", "R-1b.height": "complies",
                "R-1b.lot_coverage": "does_not_comply", "R-1b.front_yard": "complies", "R-1b.side_yards#west": "complies",
                "R-1b.side_yards#east": "complies", "R-1b.rear_yard": "complies", "R-1b.parking_one_family": "complies",
                "R-1b.stream_setback": "needs_review"}
    statuses.update({k.replace("__", "#"): v for k, v in changes.items()})
    return {"statuses": statuses, "view": {"items": [{"id": k, "reason": f"why {k}"} for k in statuses]},
            "measurements": {"lot_area": {"value": 6570.0}}, "sections": [{"key": "zoning", "state": "x", "summary": "y"}]}


def test_the_106_rows_compare_with_the_architects_and_name_each_difference(tmp_path):
    made = run(tmp_path, "106_ithaca_rd", spreadsheet_like())
    assert made["ok"] and made["summary"]["same"] == 11 and made["summary"]["rows"] == 11
    rows = {r["row"]: r for r in made["rows"]}
    assert (rows["Minimum left side yard (offset)"]["rule"], rows["Minimum right side yard (offset)"]["rule"]) == \
        ("R-1b.side_yards#west", "R-1b.side_yards#east")
    assert rows["Minimum lot size"]["gordium_measured"] == 6570.0 and rows["Minimum lot size"]["architects_proposed"] == 6674
    assert "coincidence" in rows["Minimum rear yard (offset)"]["note"]
    assert made["other_r1b_rules"] == {"R-1b.stream_setback": "needs_review"}
    # the two differences worked out before the run are named with their source; anything else is unexplained
    made = run(tmp_path, "106_ithaca_rd", spreadsheet_like(**{"R-1b.stories": "needs_review",
                                                             "R-1b.parking_one_family": "not_checked"}))
    assert made["ok"] and made["summary"]["expected_differences"] == ["Maximum stories", "Minimum parking"]
    made = run(tmp_path, "106_ithaca_rd", spreadsheet_like(**{"R-1b.rear_yard": "needs_review"}))
    assert not made["ok"] and made["summary"]["unexplained"] == ["Minimum rear yard (offset)"]
    # a pass where the architects fail is named as such
    made = run(tmp_path, "106_ithaca_rd", spreadsheet_like(**{"R-1b.lot_coverage": "complies"}))
    assert made["summary"]["gordium_passes_what_they_fail"] == ["Percent of lot area"]
    # side yards not told apart: the most cautious of them
    result = spreadsheet_like()
    for side in ("west", "east"):
        del result["statuses"][f"R-1b.side_yards#{side}"]
    result["statuses"].update({"R-1b.side_yards#narrower": "complies", "R-1b.side_yards#wider": "needs_review"})
    rows = {r["row"]: r for r in run(tmp_path, "106_ithaca_rd", result)["rows"]}
    assert rows["Minimum left side yard (offset)"]["gordium"] == "needs_review"


# ---- the comparison, on the real checker's answer for each building as Revit will read it --------------------------

def _answer(site, facts, interior=None) -> dict:
    from design_checker.__main__ import answer
    got = answer({"id": 1, "cmd": "check_site", "protocol": "1.3", "site": site, "facts": facts, "interior": interior})
    assert got["ok"], got.get("error")
    return got


def test_the_orangetown_reading_checked_by_the_real_worker_compares_as_predicted(tmp_path):
    # the interior a host reads from the drawing the build makes (the same placing: recordings.drawing), sent with a
    # stand-in site, as Check my project sends it; its egress compared with the hand-check
    from model_measurement.interior import recordings
    sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
    from test_real_house_revit_reading import as_read

    site = json.loads((REPO / "test_data/host_conformance/expected/01_box_house.site.json").read_text(encoding="utf-8"))
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": "R-1b",
             "use": "one_family_detached", "lot_surveyed": False, "street_line": [[[0, 0], [60, 0]]]}
    got = _answer(site, facts, as_read(recordings.drawing(compare.HOUSE.name)))
    (tmp_path / "a.json").write_text(json.dumps(got), encoding="utf-8")
    made = compare.compare_orangetown(compare.result_of(tmp_path / "a.json"))
    assert made["ok"], made["summary"]
    assert made["summary"]["as_predicted"] == 115


def test_the_106_design_checked_by_the_real_worker_differs_from_the_architects_only_where_expected(tmp_path):
    # the spreadsheet's box as a host reads it (the Rhino reading of the same design: the Revit reader copies its
    # decisions), with the facts the eval's Project Information marks state and the build's spot grades
    from design_checker import site_json

    full = load(SITE, "spreadsheet_design_model_facts.yaml")["lot_facts"]
    site = site_json.read_model(SITE / "spreadsheet_design_model.3dm", full, True)
    site["grade"] = {"source": "spot", "points": [s["at"] for s in build(SITE)["spot_grades"]]}
    marks = marks_tool.check_request(load(SITE, "eval_marks.yaml"), "m")["marks"]
    facts = {"jurisdiction": "regulations/jurisdictions/new_york/ithaca_city", "zone": marks["Gordium: Zone"],
             "use": marks["Gordium: Use"], "lot_surveyed": marks["Gordium: Lot surveyed"],
             "corner_lot": marks["Gordium: Corner lot"], "grade_from": "spot",
             "street_line": [list(map(list, street(marks["Gordium: Street edge"])))]}
    got = _answer(site, facts)
    (tmp_path / "a.json").write_text(json.dumps(got), encoding="utf-8")
    made = compare.compare_106(compare.result_of(tmp_path / "a.json"))
    assert made["ok"], made["summary"]
    assert made["summary"]["same"] == 9
    assert made["summary"]["expected_differences"] == ["Maximum stories", "Minimum parking"]
    # never kinder: the stories row needs review, never a pass on the count the spreadsheet types
    assert {r["row"]: r["gordium"] for r in made["rows"]}["Maximum stories"] == "needs_review"
    # the design read back off the model: the drawn lot's 6,570 sf, the house's 1,855
    rows = {r["row"]: r for r in made["rows"]}
    assert rows["Minimum lot size"]["gordium_measured"] == 6570.0
    assert rows["Percent of lot area"]["gordium_measured"] == 1855.0


def test_the_command_line_writes_the_comparison_and_says_whether_it_is_ok(tmp_path, capsys):
    path = tmp_path / "answer.json"
    path.write_text(json.dumps(predicted_result()), encoding="utf-8")
    out = tmp_path / "c.yaml"
    assert compare.main(["orangetown", str(path), "--out", str(out)]) == 0
    assert yaml.safe_load(out.read_text(encoding="utf-8"))["summary"]["as_predicted"] == 115
    bad = copy.deepcopy(predicted_result())
    bad["egress"]["results"]["general.r319_2_1_escape_opening_min_net_clear_area"] = "pass"
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert compare.main(["orangetown", str(path), "--out", str(out)]) == 1
    assert "NOT OK" in capsys.readouterr().out
