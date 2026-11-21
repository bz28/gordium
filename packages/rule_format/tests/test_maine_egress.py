"""Maine's commercial egress rules (the 2009 IBC and NFPA 101 2012) against the architect's own hand check of a
day-care centre (test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml), and the rules' shape: every IBC
requirement a flag (its copy is read from OCR only, not verified), every NFPA rule standing on the second reading.
Needs no code cache (the rules' numbers come from the repo's verification files); the quotes are checked word for
word by `python -m rule_format` where the cache is. Decided: docs/decisions/2026-11-20_commercial_egress_maine.md."""

import copy

import pytest
import yaml

from rule_format import parts
from rule_format.rulebook import REPO, Context, load, rulebook_file_problems, validate

MAINE = REPO / "regulations/jurisdictions/maine/maine_state"
RULEBOOK = MAINE / "5_building_code_rules/drafted/general.yaml"
KEY = REPO / "test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml"
IBC, NFPA = "icc.ibc.2009.pdf", "gov.law.nfpa.101.2012.pdf"


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(MAINE)


@pytest.fixture(scope="module")
def rules():
    return {r["id"]: r for r in load(RULEBOOK)["rules"]}


def books(rule):
    return {s["file"] for s in rule["sources"]}


def test_the_rulebook_is_valid(ctx):
    assert rulebook_file_problems(RULEBOOK, ctx) == []


def test_every_ibc_requirement_is_a_flag_and_every_nfpa_rule_stands_on_one_book(rules):
    for rid, r in rules.items():
        if IBC in books(r):
            assert r["kind"] == "flag" and books(r) == {IBC}, rid
            if "check" in r:
                assert "not verified" in r["notes"] and all("drafted_check" in e for e in r["examples"]
                                                            if e["expect"] == "needs_review" and e.get("rows")
                                                            and any(x.get("part") for x in e["rows"])), rid
        else:
            assert books(r) == {NFPA}, rid


def test_an_ibc_flag_made_a_rule_is_refused(ctx, rules):
    r = copy.deepcopy(rules["general.ibc_1016_1_travel_distance"])
    r["kind"] = "rule"
    for e in r["examples"]:
        e.pop("drafted_check", None)
    got = validate({"district": "general", "rules": [r]}, ctx)
    assert any("never read a second time" in p for p in got), got


def _key_examples(rule):
    return [e for e in rule["examples"] if "The answer key" in (e.get("note") or "")]


MEASURED = {   # each check of the answer key: the measure the sheet's number is, in the rules' units
    "Exit access travel distance (the most remote point to an exit)": ("egress_travel_distance", 130.667),
    "Common path of egress travel": ("common_path_of_travel", 48.5),
    "Dead-end corridor": ("corridor_dead_end_length", 21.5),
    "Exit (or exit access doorway) remoteness": ("exit_remoteness_ratio", 0.8745),
    "Accessory storage area on the story": ("story_accessory_area", 1428),
}


def test_the_rules_reproduce_the_architects_hand_check(ctx, rules):
    """Each answer-key check's rules exist and each has a worked example on the sheet's own numbers whose result, as
    the rule decides it (an IBC flag's drafted test: drafted_check), is the sheet's: pass. The IBC flag itself still
    needs review (OCR copy), so the sheet's design is never passed on the IBC's unverified numbers."""
    key = yaml.safe_load(KEY.read_text(encoding="utf-8"))
    seen = set()
    for check in key["checks"]:
        for rid in check["gordium_rules"]:
            assert rid in rules, rid
            r = rules[rid]
            if check["what"] not in MEASURED or "check" not in r:
                continue
            measure, value = MEASURED[check["what"]]
            if measure not in parts.formula_names(r):
                continue
            found = _key_examples(r)
            assert found, rid
            for e in found:
                given = [p["measures"].get(measure) for p in e["parts"][r["for_each"]]]
                assert given == [pytest.approx(value, abs=1e-3)], (rid, given)
                want = (check.get("gordium_result") or {}).get(rid, check["result"])
                as_rule = e.get("drafted_check", e["expect"])
                assert check["result"] == "pass" and as_rule == want, rid
                assert e["expect"] == ("needs_review" if r["kind"] == "flag" else want), rid
                seen.add(rid)
    assert {"general.ibc_1016_1_travel_distance", "general.nfpa_16_2_6_2_point_in_room_to_exit",
            "general.ibc_1014_3_common_path", "general.nfpa_16_2_5_3_1_common_path_sprinklered",
            "general.ibc_1018_4_dead_end", "general.nfpa_16_2_5_2_dead_end", "general.ibc_1015_2_1_remoteness",
            "general.ibc_508_2_1_accessory_area"} <= seen


def test_the_sheets_limits_are_the_rules_numbers(rules):
    """The limits the sheet applies are the ones the rules compare with: 200 and 150 ft travel, 75 and 100 ft common
    path, 20 ft and 2.5 x the width (IBC) and 50 ft (NFPA sprinklered) dead ends, one-third of the diagonal, 10%."""
    has = {rid: rules[rid]["check"] for rid in rules if "check" in rules[rid]}
    assert "egress_travel_distance <= 200" in has["general.ibc_1016_1_travel_distance"]
    assert has["general.nfpa_16_2_6_2_point_in_room_to_exit"] == "egress_travel_distance <= 150"
    assert has["general.ibc_1014_3_common_path"] == "common_path_of_travel <= 75"
    assert has["general.nfpa_16_2_5_3_1_common_path_sprinklered"] == "common_path_of_travel <= 100"
    assert "2.5 * corridor_dead_end_least_width" in has["general.ibc_1018_4_dead_end"]
    assert "50 if" in has["general.nfpa_16_2_5_2_dead_end"] and "else 20" in has["general.nfpa_16_2_5_2_dead_end"]
    assert "1 / 3 if" in has["general.ibc_1015_2_1_remoteness"]
    assert has["general.ibc_508_2_1_accessory_area"] == "story_accessory_area <= 0.10 * story_building_area"


def test_most_restrictive_is_recorded_for_each_pair(rules):
    for rid in ("general.ibc_1014_3_common_path", "general.ibc_1016_1_travel_distance", "general.ibc_1018_4_dead_end",
                "general.ibc_1018_1_corridor_rating", "general.ibc_1004_1_1_occupant_load",
                "general.nfpa_16_2_5_2_dead_end", "general.nfpa_16_2_5_3_1_common_path_sprinklered",
                "general.nfpa_16_3_6_corridor_walls", "general.nfpa_16_1_7_1_occupant_load"):
        notes = rules[rid]["notes"]
        assert "Most restrictive" in notes and "both apply" in notes and "stricter governs" in notes, rid


def test_every_piece_labeled_rule_or_flag_has_a_rule():
    for stem in ("icc.ibc.2009", "gov.law.nfpa.101.2012"):
        got = yaml.safe_load((MAINE / f"6_coverage_report/{stem}.rules.yaml").read_text(encoding="utf-8"))
        assert got["not_checked_yet"] == [], stem


def test_nfpa_feet_printed_ft_back_a_length(ctx):
    """NFPA 101 prints feet as "ft", which numbers.py reads as no unit; the quote's own "ft" makes it a length in
    feet (code_numbers._in_feet), and only there: a number the quote doesn't print in ft backs no length."""
    from rule_format import code_numbers
    dead_end = next(s for s in load(RULEBOOK)["rules"] if s["id"] == "general.nfpa_16_2_5_2_dead_end")["sources"][0]
    rule = {"kind": "rule", "check": "corridor_dead_end_length <= 20", "for_each": "corridor"}
    assert code_numbers.problems(rule, [dead_end], ctx) == []
    assert code_numbers.problems(dict(rule, check="corridor_dead_end_length > 20"), [dead_end], ctx)   # direction
    assert code_numbers.problems(dict(rule, check="corridor_dead_end_length <= 6100"), [dead_end], ctx)  # the mm
    cut = dict(dead_end, quote="No dead-end corridor shall exceed 20")     # no "ft" printed: no length
    assert any("isn't one of" in p for p in code_numbers.problems(rule, [cut], ctx))


# ---- review round 1 (2026-11-20): what the law leaves open, or the rule doesn't count, never passes ----------------

def _rows(rule, kind, measures, given, ctx):
    return [r["outcome"] for r in parts.rows(rule, {kind: [{"id": "p1", "measures": measures}]}, given, ctx.allowed())]


NEW_SPRINKLERED = {"nfpa_day_care_occupancy": True, "day_care_existing": False, "sprinklered_9_7": True,
                   "sprinkler_supervised_9_7": True}


@pytest.mark.parametrize("rid", ["general.nfpa_16_2_5_2_dead_end", "general.nfpa_17_2_5_2_dead_end"])
def test_a_dead_end_over_20_ft_needs_review_while_maines_flat_20_ft_is_open(ctx, rules, rid):
    given = NEW_SPRINKLERED | {"day_care_existing": rid.startswith("general.nfpa_17"), "existing_change_of_use": False}
    for length, want in ((15, "pass"), (21.5, "needs_review"), (45, "needs_review"), (55, "fail")):
        assert _rows(rules[rid], "corridor", {"corridor_dead_end_length": length}, given, ctx) == [want], length
    unsprinklered = given | {"sprinklered_9_7": False}
    assert _rows(rules[rid], "corridor", {"corridor_dead_end_length": 21.5}, unsprinklered, ctx) == ["fail"]


@pytest.mark.parametrize("rid", ["general.nfpa_16_1_7_1_occupant_load", "general.nfpa_17_1_7_1_occupant_load"])
def test_an_occupant_load_with_other_uses_on_the_story_needs_review(ctx, rules, rid):
    given = {"nfpa_day_care_occupancy": True, "day_care_existing": rid.startswith("general.nfpa_17"),
             "existing_change_of_use": False}
    base = {"story_occupant_load": 105, "story_day_care_net_area": 3500}
    assert _rows(rules[rid], "story", base | {"story_other_use_area": 0}, given, ctx) == ["pass"]
    assert _rows(rules[rid], "story", base | {"story_other_use_area": 1500}, given, ctx) == ["needs_review"]
    assert _rows(rules[rid], "story", base, given, ctx) == ["needs_review"]          # not said: never a pass


def test_chapter_16_reaches_an_existing_day_care_unless_no_change_of_use_is_stated(ctx, rules):
    """NFPA 4.6.11 and Chapter 43 (not brought in) can make a changed existing building meet Chapter 16: an existing
    day care is held to Chapter 16 too unless the architect states there was no change of use."""
    r = rules["general.nfpa_16_2_5_3_1_common_path_sprinklered"]
    existing = NEW_SPRINKLERED | {"day_care_existing": True}
    long_path = {"common_path_of_travel": 110}
    assert _rows(r, "story", long_path, existing, ctx) == ["needs_review"]                 # change of use not said
    assert _rows(r, "story", long_path, existing | {"existing_change_of_use": True}, ctx) == ["fail"]
    assert _rows(r, "story", long_path, existing | {"existing_change_of_use": False}, ctx) == ["not_applicable"]


def test_every_table_has_a_rule_named_for_it_never_a_sections_rule_standing_in():
    for stem in ("icc.ibc.2009", "gov.law.nfpa.101.2012"):
        got = yaml.safe_load((MAINE / f"6_coverage_report/{stem}.rules.yaml").read_text(encoding="utf-8"))
        for pid, e in got["pieces"].items():
            if pid.startswith("Table "):
                assert e["rules"] and all("_table_" in r for r in e["rules"]), (pid, e["rules"])


def test_the_decision_note_says_what_is_done_with_the_ocrs_misreads():
    """No Maine book puts a misread right in its text (sources.yaml has no brought_in.misread): the IBC's are named in
    the labels' notes. The decision note must say so, not that they are put right by line."""
    sources = load(MAINE / "1_source_documents/sources.yaml")["documents"]
    assert not any("misread" in (d.get("brought_in") or {}) for d in sources)
    note = " ".join((REPO / "docs/decisions/2026-11-20_commercial_egress_maine.md").read_text(encoding="utf-8").split())
    assert "misreads are put right by line" not in note and "named in the labels' notes" in note
