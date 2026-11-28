"""Egress names the code sections Gordium doesn't check yet (Ben, 2026-11-15): one needs-review line, "Not checked yet
by Gordium: window fall protection (R321.2.1), hallway width (R318.6) and 84 more: check these by hand", every
section in its detail. Without it, a design whose every checked egress rule complies would read "Egress complies"
while whole sections (window fall protection, hallway width...) were never checked: a false pass.

What is pinned here (each fails on revert):
- the line is there on a checked house, names R321.2.1 and R318.6 first and lists every section the generated
  coverage list says has no rules;
- a case where every checked egress rule complies: egress complies only once the list is empty, and needs review
  while it isn't (the design never reads as complying);
- no rooms drawn: egress still waits (grey "Egress waiting: no rooms drawn yet", waiting_only), the line is not
  added, and the waiting row's detail lists the sections instead;
- the list comes from data: 6_coverage_report/<book>.rules.yaml (generated from the labels and the rulebook, never
  a list in code); a section whose rules aren't loaded counts as not checked; a missing list needs review;
- the pieces labeled flag (a judgment, e.g. R319.5 replacement windows) are listed too, after the rule pieces (review
  round 1: they were raised nowhere);
- the generated list: a rule counts for a piece only when its id names the piece and it quotes that piece.
"""

import copy
import shutil
import sys

import yaml

from design_checker import egress, present
import sys as _sys  # noqa: E402
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))   # egress_house beside this file
import egress_house  # noqa: E402
from design_checker.check import check_site, summary
from rule_format.labels import load_pieces
from rule_format.rulebook import REPO, load
from section_labeling import coverage

sys.path.insert(0, str(REPO / "packages/design_checker/tests"))
sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
from test_egress import FACTS, ITHACA, SITE, STATE, ranch  # noqa: E402

BOOK = "gov.ny.residential.2025.pdf"
LIST = STATE / "6_coverage_report/gov.ny.residential.2025.rules.yaml"
CUT = STATE / "2_extracted_text/gov.ny.residential.2025.sections.jsonl"
LABELS = STATE / "3_section_labels/gov.ny.residential.2025.yaml"
NOT_YET = "egress.not_checked_yet"
COMPLYING_ZONING = [{"id": "R-1b.rear_yard", "rule": "R-1b.rear_yard", "name": "Rear yard", "group": "building",
                     "status": present.COMPLIES}]


def uncovered():
    return load(LIST)["not_checked_yet"]


def egress_items(items):
    return [i for i in items if i["group"] == present.LAW_GROUP]


def test_the_line_is_on_a_checked_house_and_lists_every_section_not_checked_yet():
    result = check_site(SITE, dict(FACTS), interior=ranch())
    [line] = [i for i in egress_items(result["view"]["items"]) if i["id"] == NOT_YET]
    assert line["status"] == present.REVIEW and line["rule"] is None
    assert line["name"] == ("Not checked yet by Gordium: window fall protection (R321.2.1), hallway width (R318.6) "
                            f"and {len(uncovered()) - 2} more: check these by hand")
    assert "\n" not in line["name"]                                   # one line in the panel
    assert {"R321.2.1", "R318.6", "R319.1.1", "R318.1"} <= set(uncovered())
    for section in uncovered():                                        # every one in its detail, by its section
        assert f"({section})" in line["reason"]
    assert sorted(line["detail"]["citation"].split(", ")) == sorted(uncovered())
    assert line["reason"].startswith("Gordium doesn't check these sections of the NY State Residential Code 2025 yet")
    assert "6_coverage_report" not in line["reason"] and line["reason"].endswith(".")      # no file path: plain words
    assert result["sections"][1]["state"] != present.COMPLIES


def test_the_flag_sections_are_listed_too_after_the_rule_sections():
    """Review round 1 (F1, two sceptics): the 56 pieces labeled flag had no rule and were raised nowhere."""
    data = load(LIST)
    flags = [p for p, e in data["pieces"].items() if e["label"] == "flag"]
    assert {"R319.5", "R507.10", "R316.2", "R320.7"} <= set(flags) <= set(uncovered())
    law = egress.laws(ITHACA)["laws"][0]
    [line] = egress._not_yet_items(law)
    rules_part, _, flags_part = line["reason"].partition(egress.FLAGS_WORDS)
    assert "(R321.2.1)" in rules_part and "(R319.5)" not in rules_part
    for p in flags:
        assert f"({p})" in flags_part
    assert sorted(flags, key=lambda p: flags_part.index(f"({p})")) == flags         # in the book's order
    assert "existing buildings: work must not make the building unsafe or less compliant (BO102.1)" in flags_part
    assert "General (" not in flags_part
    assert "Window fall protection" not in flags_part
    assert f"and {len(uncovered()) - 2} more" in line["name"]


def test_a_list_whose_own_not_checked_yet_disagrees_is_read_the_cautious_way(tmp_path):
    folder = tmp_path / "new_york_state"
    (folder / "6_coverage_report").mkdir(parents=True)
    data = load(LIST)
    data["not_checked_yet"].append("R319.2.3")                  # has rules, but the list's own key names it
    data["not_checked_yet"].append("R399.8")                    # and one its pieces leave out
    (folder / "6_coverage_report" / LIST.name).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    missing, _ = egress._not_checked_yet(folder, egress.laws(ITHACA)["laws"][0]["rules"])
    by = {m["section"]: m for m in missing}
    assert by["R319.2.3"]["heading"] == data["pieces"]["R319.2.3"]["heading"]      # read with its piece
    assert by["R399.8"]["heading"] == "R399.8"


# the ranch is one story (every room on one floor, no stairs): stated so, since "no stairs" beside two or more stories
# isn't taken (model_measurement.interior._stairs_against_floors; egress_house.HOUSE states 3 for other houses)
RANCH_VALUES = {**egress_house.HOUSE, "stories_above_grade_plane": 1}


def complying_law():
    """Only the egress rules whose every row on the ranch complies: every checked egress rule complies."""
    found = copy.deepcopy(egress.laws(ITHACA))
    law = found["laws"][0]
    got = egress.check(found, ranch(), dict(RANCH_VALUES), egress_house.ALLOWED)
    bad = {i["rule"] for i in got["items"] if i["status"] != present.COMPLIES}
    law["rules"] = [r for r in law["rules"] if r["id"] not in bad and r["id"] in got["results"]
                    and got["results"][r["id"]] == "pass"]
    assert len(law["rules"]) >= 5
    return found


def test_egress_never_complies_while_sections_are_not_checked_even_when_every_checked_rule_complies():
    found = complying_law()
    everything = copy.deepcopy(found)
    everything["laws"][0]["not_checked_yet"] = []               # the day every section has rules
    got = egress.check(everything, ranch(), dict(RANCH_VALUES), egress_house.ALLOWED)
    assert {i["status"] for i in got["items"]} == {present.COMPLIES}
    assert got["sections"][0]["state"] == present.COMPLIES      # the case is real: without the list, it complies

    got = egress.check(found, ranch(), dict(RANCH_VALUES), egress_house.ALLOWED)
    rules_rows = [i for i in got["items"] if i["rule"]]
    assert rules_rows and {i["status"] for i in rules_rows} == {present.COMPLIES}    # every checked rule complies
    assert [i["id"] for i in got["items"] if i["status"] != present.COMPLIES] == [NOT_YET]
    assert got["sections"][0]["state"] == present.REVIEW
    sections = len(found["laws"][0]["not_checked_yet"])
    # grouped (docs/decisions/2026-11-16_results_grouping.md): only Gordium's gap left, so "needs review" first
    assert got["sections"][0]["summary"] == \
        f"needs review · {len(rules_rows)} comply · {sections} sections not checked yet"
    view = {"items": copy.deepcopy(COMPLYING_ZONING)}
    egress.add_to_view(view, got, "City of Ithaca")
    assert view["sections"][0]["state"] == present.COMPLIES and view["sections"][1]["state"] == present.REVIEW
    assert view["state"] == present.REVIEW and view["waiting_only"] is False
    assert view["summary"] == (f"Zoning complies · Egress: needs review · {len(rules_rows)} comply · {sections} "
                               "sections not checked yet")
    passing = [{"Error": "PASS", "Requirement": "Rear yard", "Rule id": "R-1b.rear_yard"}]
    assert summary(passing, view["items"])["state"] == "review"


def test_no_rooms_drawn_egress_still_waits_and_its_row_lists_the_sections():
    view = {"items": copy.deepcopy(COMPLYING_ZONING)}
    got = egress.check(egress.laws(ITHACA), None, dict(egress_house.HOUSE), {})
    egress.add_to_view(view, got, "City of Ithaca")
    [row] = egress_items(view["items"])                          # the waiting row alone: no needs-review line
    assert row["id"] == "egress.waiting" and row["status"] == present.NOT_CHECKED
    assert view["sections"][1] == {"key": "new_york/new_york_state", "title": "Egress (NY State Residential Code 2025)",
                                   "state": egress.WAITING, "summary": "waiting, no rooms drawn yet"}
    assert view["summary"] == "Zoning complies · Egress waiting: no rooms drawn yet"
    assert view["waiting_only"] is True and view["state"] == present.REVIEW       # grey, still never a pass
    assert row["reason"].startswith(egress.WAITING_WHY + ". Not checked yet by Gordium, even once the rooms are drawn")
    for section in uncovered():
        assert f"({section})" in row["reason"]
    # and with rooms that are an empty list (massing only): the same
    rooms_empty = egress.check(egress.laws(ITHACA), dict(ranch(), rooms=[]), dict(RANCH_VALUES), {})
    assert [i["id"] for i in rooms_empty["items"]] == ["egress.waiting"]


def test_a_section_whose_rules_arent_loaded_counts_as_not_checked():
    found = egress.laws(ITHACA)
    law = found["laws"][0]
    assert "R319.2.3" not in [m["section"] for m in law["not_checked_yet"]]
    law["rules"] = [r for r in law["rules"] if not r["id"].startswith("general.r319_2_3_")]
    missing, problem = egress._not_checked_yet(STATE, law["rules"])
    assert problem is None and "R319.2.3" in [m["section"] for m in missing]


def test_the_sections_come_from_the_coverage_list_and_a_missing_list_needs_review(tmp_path):
    folder = tmp_path / "new_york_state"
    (folder / "6_coverage_report").mkdir(parents=True)
    rules = egress.laws(ITHACA)["laws"][0]["rules"]
    data = load(LIST)
    data["pieces"]["R399.9"] = {"heading": "Made up › Test piece", "rules": []}     # a piece only this list names
    (folder / "6_coverage_report" / LIST.name).write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    shutil.copy(STATE / egress.NAMES, folder / egress.NAMES)
    missing, problem = egress._not_checked_yet(folder, rules)
    assert problem is None
    assert [m["section"] for m in missing][:2] == ["R321.2.1", "R318.6"]        # section_names.yaml's order first
    made_up = next(m for m in missing if m["section"] == "R399.9")
    assert made_up == {"section": "R399.9", "heading": "Made up › Test piece", "name": "Made up › Test piece",
                       "label": "rule", "file": "new_york_state/6_coverage_report/gov.ny.residential.2025.rules.yaml"}
    assert all(m["label"] == "flag" for m in missing[missing.index(made_up) + 1:])    # flags after every rule piece
    (folder / "6_coverage_report" / LIST.name).unlink()
    missing, problem = egress._not_checked_yet(folder, rules)
    assert missing == [] and "no 6_coverage_report/*.rules.yaml" in problem
    (folder / "6_coverage_report" / LIST.name).write_text("pieces: [1, 2]\n", encoding="utf-8")
    missing, problem = egress._not_checked_yet(folder, rules)
    assert missing == [] and "can't be read" in problem
    law = dict(egress.laws(ITHACA)["laws"][0], not_checked_yet=[], coverage_problem=problem)
    [item] = egress._not_yet_items(law)
    assert item["status"] == present.REVIEW and "check the whole law by hand" in item["reason"]
    waiting = egress._waiting_item(law)              # while no rooms are drawn: said in the waiting row (round 4)
    assert waiting["status"] == present.NOT_CHECKED and "check the whole law by hand" in waiting["reason"]


def test_the_generated_list_matches_the_labels_and_the_rulebook():
    header, pieces = load_pieces(CUT)
    labels = load(LABELS)["labels"]
    rules = load(STATE / "5_building_code_rules/drafted/general.yaml")["rules"]
    text = coverage.rule_coverage(BOOK, pieces, labels, "5_building_code_rules/drafted/general.yaml", rules)
    assert text == LIST.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert set(data["pieces"]) == {p for p, e in labels.items() if e["label"] in ("rule", "flag")}
    assert all(e["label"] == labels[p]["label"] for p, e in data["pieces"].items())
    assert data["not_checked_yet"] == [p for p, e in data["pieces"].items() if not e["rules"]]
    # R315.5.2.3 is quoted by R318.7.6's loft-landing rule, which doesn't check it: quoting alone isn't a rule for it
    assert "R315.5.2.3" in data["not_checked_yet"]
    # R318.3.1's rules (general.r318_3_1_...) are never credited to R318.3
    assert all(not r.startswith("general.r318_3_1_") for r in data["pieces"]["R318.3"]["rules"])
    # a rule named for a piece that quotes none of it isn't a rule for it
    fake = [{"id": "general.r321_2_1_window_fall", "sources": rules[0]["sources"]}]
    assert coverage.rules_for_pieces(BOOK, pieces, labels, fake)["R321.2.1"] == []


def test_every_plain_name_is_for_a_rule_piece_and_every_section_not_checked_has_one():
    names = load(STATE / egress.NAMES)["names"]
    pieces = load(LIST)["pieces"]
    assert set(names) <= set(pieces)
    assert set(uncovered()) <= set(names)              # rule and flag pieces alike (review round 3)
    assert all(isinstance(v, str) and v.strip() for v in names.values())
