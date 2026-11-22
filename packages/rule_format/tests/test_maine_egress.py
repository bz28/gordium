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


# the sheet's travel and common path start in a classroom, a room subject to occupancy: the figure of both books'
# measures (the IBC's from every point, NFPA's from points subject to occupancy: route note decision 1b)
MEASURED = {   # each check of the answer key: the measures the sheet's number is, in the rules' units
    "Exit access travel distance (the most remote point to an exit)": (
        ("egress_travel_distance", "egress_travel_distance_occupied"), 130.667),
    "Common path of egress travel": (("common_path_of_travel", "common_path_of_travel_occupied"), 48.5),
    "Dead-end corridor": (("corridor_dead_end_length",), 21.5),
    "Exit (or exit access doorway) remoteness": (("exit_remoteness_ratio",), 0.8745),
    "Accessory storage area on the story": (("story_accessory_area",), 1428),
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
            measures, value = MEASURED[check["what"]]
            measure = next((m for m in measures if m in parts.formula_names(r)), None)
            if measure is None:
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
    assert has["general.nfpa_16_2_6_2_point_in_room_to_exit"] == "egress_travel_distance_occupied <= 150"
    assert has["general.ibc_1014_3_common_path"] == "common_path_of_travel <= 75"
    assert has["general.nfpa_16_2_5_3_1_common_path_sprinklered"] == "common_path_of_travel_occupied <= 100"
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
    long_path = {"common_path_of_travel_occupied": 110}
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


# ---- review round 2 (2026-11-20) -----------------------------------------------------------------------------------

@pytest.mark.parametrize("rid", ["general.nfpa_16_2_5_2_dead_end", "general.nfpa_17_2_5_2_dead_end"])
def test_the_dead_end_review_reason_is_project_neutral_and_points_to_the_readme(rules, rid):
    """The reason is shown to the architect as the row's Why: no "below" (there is nothing below it there) and no
    one project's date; it names where the open question is."""
    reason = rules[rid]["review_when"][0]["reason"]
    assert "below" not in reason and "2016" not in reason, reason
    assert "regulations/jurisdictions/maine/maine_state/README.md" in reason and "open question 2" in reason


@pytest.mark.parametrize("rid", ["general.ibc_table_1015_1_other_occupancies", "general.ibc_table_1016_1_other_occupancies",
                                 "general.ibc_table_1018_1_other_occupancies"])
def test_a_tables_other_rows_reach_a_mixed_day_care_building(ctx, rules, rid):
    """A day care with another occupancy in the building (or with that unstated) needs a person for the other rows;
    only a day care stated to hold no other occupancy leaves them aside."""
    from rule_format.rulebook import outcome
    r = rules[rid]
    i4 = {"occupancy_group_i4": True}
    assert outcome(r, i4 | {"other_occupancy_present": True}, ctx.allowed()) == "needs_review"
    assert outcome(r, i4, ctx.allowed()) == "needs_review"
    assert outcome(r, i4 | {"other_occupancy_present": False}, ctx.allowed()) == "not_applicable"
    assert outcome(r, {"occupancy_group_i4": False}, ctx.allowed()) == "needs_review"


def test_every_rule_citing_a_readme_open_question_is_named_in_that_question(rules):
    """Review round 3: a reason sending the architect to "open question N" of the README must be about question N,
    which names the rule (the dead-end reasons cited question 2 in words describing question 1)."""
    import re
    readme = (MAINE / "README.md").read_text(encoding="utf-8")
    items = dict(re.findall(r"^(\d+)\. (.*)$", readme.split("## Open questions", 1)[1], re.M))
    cited = 0
    for rid, r in rules.items():
        for w in r.get("review_when") or []:
            for n in re.findall(r"open question (\d+) of regulations/jurisdictions/maine/maine_state/README\.md",
                                " ".join(w["reason"].split())):
                cited += 1
                assert f"`{rid}`" in items[n], (rid, n)
    assert cited >= 2
    assert "whether that flat 20 ft governs" in rules["general.nfpa_16_2_5_2_dead_end"]["review_when"][0]["reason"]
    assert "flat 20-ft dead-end limit governs" in items["2"]


def test_each_book_reads_the_travel_measure_its_own_words_define(rules):
    """NFPA 101 measures travel and common path from points "subject to occupancy" (7.6.1(1), A.3.3.47): its rules
    read the `_occupied` measures, which leave out a room the architect marks not occupied; the 2009 IBC from "the
    most remote point within a story" (1016.1): its rules read the measures over every room (route note decision
    1b). A rule reading the other book's measure is the false pass (IBC) or the needless review (NFPA)."""
    shared, occupied = {"egress_travel_distance", "common_path_of_travel"}, \
        {"egress_travel_distance_occupied", "common_path_of_travel_occupied"}
    seen = {"ibc": 0, "nfpa": 0}
    for rid, r in rules.items():
        names = set()
        texts = [r.get("check") or "", r.get("applies_when") or ""] + [w["when"] for w in r.get("review_when") or []]
        for text in texts:
            names |= formula_names_of(text)
        books = {s["file"] for s in r.get("sources") or []}
        if books == {"gov.law.nfpa.101.2012.pdf"} and names & (shared | occupied):
            assert not names & shared and names & occupied, rid
            assert any(v["field"] in ("check", "applies_when") for v in r.get("revised") or []), rid   # said why
            seen["nfpa"] += 1
        if books == {"icc.ibc.2009.pdf"} and names & (shared | occupied):
            assert not names & occupied, rid
            seen["ibc"] += 1
    assert seen == {"ibc": 2, "nfpa": 8}


def formula_names_of(text):
    from rule_format import formula
    return formula.names(text) if text.strip() else set()


def test_an_nfpa_definition_names_the_measure_nfpa_defines():
    """NFPA 101 measures travel and common path from points subject to occupancy (7.6.1(1)): a definition drawn only
    from NFPA 101 that names a measure names the _occupied one, never the IBC's (review round 1, 2026-11-22)."""
    import yaml
    from rule_format.rulebook import REPO
    defs = yaml.safe_load((REPO / "regulations/jurisdictions/maine/maine_state/4_term_definitions/definitions.yaml")
                          .read_text(encoding="utf-8"))
    for key, d in defs.items():
        if not isinstance(d, dict) or not d.get("sources"):
            continue
        if {s.get("file") for s in d["sources"]} != {"gov.law.nfpa.101.2012.pdf"}:
            continue
        notes = d.get("notes") or ""
        for measure in ("common_path_of_travel", "egress_travel_distance"):
            if f"by {measure} " in notes or f"by {measure}." in notes or f"by {measure}(" in notes:
                raise AssertionError(f"{key}: names {measure}, not {measure}_occupied")
