"""The checker's rows for rules for each part (design_checker/each_part.py): each part named, and the design's one
answer the same as present.state's over zoning and part rows together.

Every rule here is SYNTHETIC (rule_format/tests/test_parts.py): made-up text, never the building code.
"""

import copy
import importlib.util
from pathlib import Path

import pytest

from design_checker import each_part, present

_spec = importlib.util.spec_from_file_location(
    "synthetic_parts", Path(__file__).parents[2] / "rule_format/tests/test_parts.py")
synthetic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(synthetic)
AREA, RISER, ALLOWED = synthetic.AREA, synthetic.RISER, synthetic.ALLOWED
opening, house = synthetic.opening, synthetic.house
ZONING = {"use": "one_family_detached"}
ZONING_ITEM = {"id": "R-1b.rear_yard", "rule": "R-1b.rear_yard", "name": "Rear yard", "group": "building",
               "status": present.COMPLIES}     # the zoning rows: all complying


def checked(given, rules=(AREA, RISER)):
    return each_part.check_parts([copy.deepcopy(r) for r in rules], given, ZONING, ALLOWED)


def design(got):
    return present.state([ZONING_ITEM] + got["items"])


def test_the_panel_names_the_one_bad_bedroom():
    got = checked(house(opening("w1", "br1", name="Window 1"), opening("w5", "br2", area=5.1, name="Window 5"))
                  | {"stair": [{"id": "s1", "name": "Stair 1", "measures": {"stair_riser_height": 8.5}}]})
    lines = {i["status"]: [] for i in got["items"]}
    for i in got["items"]:
        lines[i["status"]].append(i["reason"])
    assert lines[present.FAILS] == ["Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft",
                                    "Stair 1: riser height 8.5 in, needs ≤ 8.25 in"]
    assert lines[present.COMPLIES] == ["Bedroom 1 › Window 1: SYNTHETIC escape opening area: complies"]
    assert got["results"] == {AREA["id"]: "fail", RISER["id"]: "fail"}
    assert design(got) == present.FAILS
    assert [i["name"] for i in got["items"] if i["status"] == present.FAILS] == ["Bedroom 2 › Window 5", "Stair 1"]


def test_a_bedroom_with_no_window_never_passes():
    got = checked(house(opening("w1", "br1")) | {"stair": []})
    fails = [i for i in got["items"] if i["status"] == present.FAILS]
    assert [i["reason"] for i in fails] == ["Bedroom 2: no emergency escape opening"]
    assert design(got) == present.FAILS


def test_a_missing_measurement_needs_review_and_says_which():
    got = checked(house(opening("w1", "br1", height=None), opening("w2", "br2")) | {"stair": []})
    review = [i["reason"] for i in got["items"] if i["status"] == present.REVIEW]
    assert review == ["Bedroom 1 › w1: net clear height not measured (or not usable)"]
    assert design(got) == present.REVIEW


def test_parts_not_read_need_review():
    got = checked({"stair": []})                    # the bedrooms and openings weren't read
    assert design(got) == present.REVIEW
    assert any("aren't read yet" in i["reason"] for i in got["items"])


def test_interior_not_started_is_one_counted_item_never_a_pass():
    got = checked(None)
    assert [(i["id"], i["status"]) for i in got["items"]] == [(each_part.INTERIOR_NOT_STARTED, present.REVIEW)]
    assert design(got) == present.REVIEW
    assert got["rows"] == [] and set(got["results"].values()) == {"needs_review"}
    assert each_part.check_parts([], None, ZONING, ALLOWED)["items"] == []    # no per-part rules: nothing to say


def test_all_good_complies_and_not_applicable_rows_are_left_out():
    got = checked(house(opening("w1", "br1"), opening("w2", "br2")) | {"stair": []})
    assert design(got) == present.COMPLIES
    assert got["results"] == {AREA["id"]: "pass", RISER["id"]: "not_applicable"}
    assert all(i["rule"] != RISER["id"] for i in got["items"])          # no stairs: not applicable, not shown


@pytest.mark.parametrize("given", [
    house(opening("w1", "br1"), opening("w1", "br2")),
    house(opening("w1", "br1"), opening("w2", "br9")),
    house(opening("w1", "br1", area=float("nan")), opening("w2", "br2")),
    house(opening("w1", "br1", area=-6), opening("w2", "br2")),
    house(opening("w1", "br1", area="big"), opening("w2", "br2")),
    {"sleeping_room": [{"id": "br1"}], "emergency_escape_opening": "w1"},
])
def test_the_design_never_complies_with_a_doubtful_part(given):
    got = checked(given | {"stair": []})
    assert design(got) in (present.REVIEW, present.FAILS)
    # the design's answer is the per-rule answers' most cautious: never kinder than any rule's
    assert got["results"][AREA["id"]] in ("needs_review", "fail")


def test_every_row_that_counts_is_an_item():
    """No row is dropped on the way to the panel: each pass, fail and needs-review row is one item."""
    got = checked(house(opening("w1", "br1"), opening("w2", "br2", area=1), {"id": "w3", "within": "br9"})
                  | {"stair": [{"id": "s1", "measures": {}}]})
    counted = [r for r in got["rows"] if r["outcome"] != "not_applicable"]
    assert len(got["items"]) == len(counted) == 4
    assert [i["status"] for i in got["items"]] == [each_part.STATUS[r["outcome"]] for r in counted]
    assert len({i["id"] for i in got["items"]}) == 4


def test_the_line_names_only_a_comparison_the_check_needs():
    """Inside `or` / `not` a comparison alone isn't the reason: the line falls back to the rule's title."""
    rule = copy.deepcopy(RISER) | {"check": "not (stair_riser_height > 7.75 or stair_tread_depth < 10)"}
    got = each_part.check_parts([rule], {"stair": [{"id": "s1", "name": "Stair 1",
                                                    "measures": {"stair_riser_height": 7, "stair_tread_depth": 9}}]},
                                ZONING, ALLOWED)
    assert [i["reason"] for i in got["items"]] == ["Stair 1: SYNTHETIC stair riser"]
    both = copy.deepcopy(RISER) | {"check": "stair_riser_height <= 8.25 and (stair_tread_depth >= 9 and stories <= 3)"}
    got = each_part.check_parts([both], {"stair": [{"id": "s1", "name": "Stair 1",
                                                    "measures": {"stair_riser_height": 7, "stair_tread_depth": 8}}]},
                                ZONING | {"stories": 2}, ALLOWED)
    assert [i["reason"] for i in got["items"]] == ["Stair 1: tread depth 8 in, needs ≥ 9 in"]


def test_rows_about_no_part_and_unusable_values_are_worded_plainly():
    assert each_part.label({"part": None, "within": None, "name": None}) == "Parts"
    assert each_part.label({"part": "stair", "within": None, "name": None}) == "Stairs"
    for bad in (-3, "6", True):
        got = checked(house(opening("w1", "br1", area=bad), opening("w2", "br2")) | {"stair": []})
        assert [i["reason"] for i in got["items"] if i["status"] == present.REVIEW] == \
            ["Bedroom 1 › w1: net clear area not measured (or not usable)"], bad


def test_a_rule_without_an_id_or_title_never_crashes_or_shares_an_answer():
    no_id = {k: v for k, v in RISER.items() if k not in ("id", "title")}
    good = copy.deepcopy(RISER) | {"id": None}
    stairs = {"stair": [{"id": "s1", "measures": {"stair_riser_height": 9}}]}
    got = each_part.check_parts([no_id, dict(good, check="stair_riser_height <= 10")], stairs, ZONING, ALLOWED)
    assert got["results"] == {"rule #1": "fail", "rule #2": "pass"}
    assert design(got) == present.FAILS


def test_lines_name_a_missing_building_measure_and_read_a_mirrored_limit():
    rule = copy.deepcopy(AREA) | {"check": "opening_net_clear_area >= (5 if stories > 1 else 4)"}
    got = each_part.check_parts([rule], house(opening("w1", "br1"), rooms=("br1",)), ZONING, ALLOWED)
    assert [i["reason"] for i in got["items"]] == ["Bedroom 1 › w1: stories not measured (or not usable)"]
    mirrored = copy.deepcopy(AREA) | {"check": "5.7 <= opening_net_clear_area"}
    got = each_part.check_parts([mirrored], house(opening("w1", "br1", area=5.1), rooms=("br1",)), ZONING, ALLOWED)
    assert [i["reason"] for i in got["items"]] == ["Bedroom 1 › w1: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft"]


def test_two_rules_with_one_id_give_the_more_cautious_answer():
    a = copy.deepcopy(AREA) | {"check": "opening_net_clear_area >= 100"}
    b = copy.deepcopy(AREA)
    for order in ([a, b], [b, a]):
        got = each_part.check_parts(order, house(opening("w1", "br1"), rooms=("br1",)), ZONING, ALLOWED)
        assert got["results"] == {AREA["id"]: "fail"}


def test_an_applies_when_that_isnt_text_gives_a_review_row():
    got = each_part.check_parts([copy.deepcopy(RISER) | {"applies_when": ["x"]}],
                                {"stair": [{"id": "s1", "measures": {"stair_riser_height": 7}}]}, ZONING, ALLOWED)
    assert [i["status"] for i in got["items"]] == [present.REVIEW]
