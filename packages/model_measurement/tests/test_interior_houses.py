"""The six made-up houses (test_data/interior_houses/): every measure the code gives equals the one worked out by
hand in the house's expected.yaml (written, with its working, before the code ran on it), every measure it can't
give is the one expected.yaml says, and nothing else. Then the measured parts go through the checker's per-part
rows (design_checker.each_part) with SYNTHETIC rules, end to end.
"""

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

from design_checker import each_part
from model_measurement.interior import KINDS, measure_file
from model_measurement.interior.stops import STOPS

HOUSES = Path(__file__).parents[3] / "test_data" / "interior_houses"
NAMES = sorted(p.name for p in HOUSES.iterdir() if (p / "house.yaml").exists())

_spec = importlib.util.spec_from_file_location(
    "synthetic_parts", Path(__file__).parents[2] / "rule_format/tests/test_parts.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)
AREA, RISER, ALLOWED = synthetic.AREA, synthetic.RISER, synthetic.ALLOWED
HEADROOM = dict(RISER, id="R-1b.synthetic_headroom", title="SYNTHETIC stair headroom", check="stair_headroom >= 80",
                examples=[{"given": {"stair_headroom": 81}, "expect": "pass"},
                          {"given": {"stair_headroom": 79}, "expect": "fail"}])


NOT_YET = {STOPS["not_measured_yet"], STOPS["in_more_not_rules"]}


def test_there_are_six_houses():
    assert NAMES == ["1_ranch_compliant", "2_two_story_small_window", "3_tall_riser", "4_loft",
                     "5_basement_window_well", "6_door_stated_clear"]


@pytest.mark.parametrize("name", NAMES)
def test_each_measure_is_the_hand_worked_one(name):
    got = measure_file(HOUSES / name / "house.yaml")
    expected = yaml.safe_load((HOUSES / name / "expected.yaml").read_text(encoding="utf-8"))
    not_read = set(expected.get("not_read", []))
    assert {k for k, v in got["parts"].items() if v is None} == not_read
    for kind in KINDS:
        if kind in not_read:
            continue
        want = expected["parts"].get(kind, {})
        parts = {p["id"]: p for p in got["parts"][kind]}
        assert set(parts) == set(want), kind
        for pid, w in want.items():
            p = parts[pid]
            assert p.get("within") == w.get("within"), pid
            assert set(p["measures"]) == set(w["measures"]), pid
            for m, v in w["measures"].items():
                assert p["measures"][m] == pytest.approx(v, abs=1e-6), (pid, m)
                assert type(p["measures"][m]) is type(v) or isinstance(v, float), (pid, m)
            # measures parts.yaml lists that this code doesn't work out yet are pinned in test_interior_measures
            assert {m for m, why in p["not_measured"].items() if why not in NOT_YET} == set(w.get("not_measured", [])), pid
            for m, v in (w.get("more") or {}).items():
                assert p["more"][m] == pytest.approx(v, abs=1e-6), (pid, m)
            for m, used in (w.get("from") or {}).items():       # which the clear size came from: drawn or stated
                assert p["from"][m]["used"] == used, (pid, m)
    assert got["not_checked"] == []


def test_every_measure_a_part_carries_is_its_kinds_own():
    """`measures` holds only parts.yaml's names for the part's kind (the checker reads nothing else); and every
    parts.yaml measure is either measured or has a reason, never silently missing."""
    from rule_format.parts import measure_kinds
    for name in NAMES:
        got = measure_file(HOUSES / name / "house.yaml")
        for kind, parts in got["parts"].items():
            own = set(measure_kinds(kind)) if kind != "guard" else {"guard_height", "guard_opening_sphere"}
            for p in parts or []:
                assert set(p["measures"]) <= own, (name, p["id"])
                assert own <= set(p["measures"]) | set(p["not_measured"]), (name, p["id"])


def rows(name, rules):
    got = measure_file(HOUSES / name / "house.yaml")
    checked = each_part.check_parts([copy.deepcopy(r) for r in rules], got["parts"], {"use": "one_family_detached"},
                                    ALLOWED)
    return checked["results"], {(r.get("within") or {}).get("id", "") + "/" + str(r.get("id")): r["outcome"]
                                for r in checked["rows"]}


def test_end_to_end_the_ranch_passes():
    results, _ = rows("1_ranch_compliant", [AREA, RISER])
    # 6.125 and 5.416667 sq ft, both grade-floor (5 sq ft), heights 36 and 26; no stairs
    assert results == {AREA["id"]: "pass", RISER["id"]: "not_applicable"}


def test_end_to_end_the_small_window_fails_and_is_named():
    results, by = rows("2_two_story_small_window", [AREA, RISER])
    assert results == {AREA["id"]: "fail", RISER["id"]: "pass"}
    assert by["bed3/w5"] == "fail" and by["bed4/w6"] == "pass"     # 5.125 sq ft, not grade-floor


def test_end_to_end_the_tall_riser_fails():
    results, by = rows("3_tall_riser", [RISER])
    assert results == {RISER["id"]: "fail"} and by["/s"] == "fail"   # 9 in over 8.25


def test_end_to_end_an_unmeasured_window_needs_review_never_passes():
    results, by = rows("4_loft", [AREA])
    assert by["main/wa"] == "needs_review"                           # an awning window with no maker's opening
    assert by["loft/None"] == "fail"                                 # the loft: a sleeping room with none marked
    assert results == {AREA["id"]: "fail"}


def test_end_to_end_the_low_headroom_fails():
    results, by = rows("5_basement_window_well", [AREA, HEADROOM])
    assert by["bbed/we2"] == "fail"                                  # 3.33 sq ft and 20 in high
    assert by["/bs"] == "fail"                                       # 76 in under the main floor's edge
    assert results[HEADROOM["id"]] == "fail" and results[AREA["id"]] == "fail"


DOOR = dict(RISER, id="R-1b.synthetic_door_width", title="SYNTHETIC exit door clear width", for_each="egress_door",
            check="door_clear_width >= 33.75",
            examples=[{"given": {"door_clear_width": 34}, "expect": "pass"},
                      {"given": {"door_clear_width": 33.5}, "expect": "fail"}])


def test_end_to_end_the_makers_smaller_door_width_fails():
    results, by = rows("6_door_stated_clear", [DOOR])
    # drawn 34.0 alone would pass (>= 33.75); the maker's 33.5 is the less favourable, so it counts and fails
    assert by["/d1"] == "fail" and results == {DOOR["id"]: "fail"}


def test_the_command_prints_the_measures(capsys):
    from model_measurement.interior.__main__ import main
    assert main([str(HOUSES / "2_two_story_small_window" / "house.yaml")]) == 0
    printed = yaml.safe_load(capsys.readouterr().out)
    assert printed["parts"]["emergency_escape_opening"][0]["measures"]["opening_net_clear_area"] == 5.125
    assert main([]) == 2
