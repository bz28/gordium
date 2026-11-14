"""The house egress drafts and the hand answer key (egress step 3): both valid, compared rule by rule, every
disagreement resolved by reading the law (rule_drafting/book_eval.py; evals/2026-11-13_house_egress/).

Validation needs no code cache for the numbers (text_verification.yaml is in the repo); the quotes are checked word
for word where the cache is (python -m rule_format), and skipped, said so, where it isn't.
"""

import pytest

from rule_drafting import book_eval
from rule_format.rulebook import Context, load, validate

VERDICTS = {"draft_wrong", "drafts_stricter", "key_stricter", "both_follow_the_law"}   # resolutions.yaml says each


@pytest.fixture(scope="module")
def ctx():
    return Context.for_jurisdiction(book_eval.STATE)


@pytest.fixture(scope="module")
def key():
    return book_eval.rules_of(book_eval.KEY)


@pytest.fixture(scope="module")
def drafts():
    return book_eval.rules_of(book_eval.DRAFTS)


def test_the_answer_key_and_the_drafts_are_valid_rulebooks(ctx, key, drafts):
    assert key and drafts
    for path in (book_eval.KEY, book_eval.DRAFTS):
        assert validate(load(path), ctx) == [], path


def test_the_key_was_written_by_hand_and_the_drafts_by_the_recorded_run(key, drafts):
    assert {r["drafted_by"] for r in key} == {"claude_code/claude-opus-5-5 (answer key helper)"}
    assert {r["drafted_by"].split("/")[0] for r in drafts} == {"rule_drafting"}


def test_every_disagreement_is_resolved_by_the_law_and_the_report_is_current(ctx, key, drafts):
    found = book_eval.compare(key, drafts, ctx)
    causes, resolutions = book_eval.resolutions_of()
    unresolved = [f["id"] for f in found if f["id"] not in resolutions]
    assert unresolved == [], unresolved
    stale = sorted(set(resolutions) - {f["id"] for f in found})
    assert stale == [], f"resolutions for disagreements that no longer arise: {stale}"
    assert {r["cause"] for r in resolutions.values()} == set(causes), "a cause no disagreement has, or one not written"
    for name, c in causes.items():
        assert c.get("verdict") in VERDICTS and str(c.get("why", "")).strip() and str(c.get("law", "")).strip(), name
        # a wrong draft says whether it could pass what the law fails (those are the ones a person must fix first)
        assert (type(c.get("false_pass_risk")) is bool) == (c["verdict"] == "draft_wrong"), name
    assert book_eval.REPORT.read_text(encoding="utf-8") == book_eval.report(key, drafts, found, resolutions)


def test_each_fix_to_the_key_is_recorded_in_the_key_itself(key):
    fixes = (load(book_eval.RESOLUTIONS) or {}).get("key_fixes") or []
    by_id = {r["id"]: r for r in key}
    for fix in fixes:
        assert fix.get("what") and fix.get("law"), fix
        if fix["rule"].startswith("general."):
            assert "after the comparison" in str(by_id[fix["rule"]].get("notes", "")).lower(), fix["rule"]


def test_each_verdict_matches_its_rows(ctx, key, drafts):
    """A verdict is a claim about the rows it covers: drafts_stricter means the drafts are further from a pass on
    every one; key_stricter the key; a draft that is wrong without a false-pass risk never passes (or says not
    applicable) where the key fails or needs review; both_follow_the_law never covers a pass by the drafts where
    the key fails. (A false-pass-risk draft needs no row to show it: its why says the design that would.)"""
    _, resolutions = book_eval.resolutions_of()
    rank = book_eval.STRICTNESS
    for f in book_eval.compare(key, drafts, ctx):
        r = resolutions[f["id"]]
        k, d = rank[f["key"]], rank[f["draft"]]
        if r["verdict"] == "drafts_stricter":
            assert d > k, (f["id"], r["cause"], f["key"], f["draft"])
        elif r["verdict"] == "key_stricter":
            assert k > d, (f["id"], r["cause"], f["key"], f["draft"])
        elif r["verdict"] == "draft_wrong" and not r["false_pass_risk"]:
            assert not (d == 1 and k > 1), (f["id"], r["cause"], f["key"], f["draft"])
        elif r["verdict"] == "both_follow_the_law":    # never where the drafts pass what the key fails
            assert not (d == 1 and k == 3), (f["id"], r["cause"], f["key"], f["draft"])


@pytest.mark.parametrize("missing", ["area_well_depth", "area_well_area", "area_well_projection", "area_well_width",
                                     "opening_below_grade"])
def test_a_window_well_with_a_number_missing_never_passes(ctx, key, drafts, missing):
    """The measuring code gives no well depth where the well floor and the grade around it disagree (until the
    architects answer which counts): neither rulebook may pass an area well on an assumed number."""
    from rule_format import parts
    well = {"opening_below_grade": True, "area_well_area": 12, "area_well_projection": 40, "area_well_width": 40,
            "area_well_depth": 30, "area_well_ladder": False, "opening_fully_openable": True}   # passes with all given
    checked = 0
    del well[missing]
    design = {"sleeping_room": [{"id": "b1"}],
              "emergency_escape_opening": [{"id": "w1", "within": "b1", "measures": well}]}
    for rule in key + drafts:
        if book_eval.own_piece(rule) in ("R319.4", "R319.4.1", "R319.4.2") and parts.is_part_rule(rule):
            reads = parts.formula_names(rule)
            if missing in reads:
                got = {r["outcome"] for r in parts.rows(rule, design, {}, ctx.allowed()) if r["id"] == "w1"}
                assert "pass" not in got, (rule["id"], missing, got)
                checked += 1
    assert checked, missing
