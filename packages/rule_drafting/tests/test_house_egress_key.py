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
    # every draft is the recorded run's, but a rule added whole after it (revised: field rule), which says whose
    added = {r["id"] for r in drafts if any(x["field"] == "rule" for x in r.get("revised") or [])}
    assert {r["drafted_by"].split("/")[0] for r in drafts if r["id"] not in added} == {"rule_drafting"}
    assert {r["drafted_by"] for r in drafts if r["id"] in added} == {
        "claude_code/claude-opus-5-5 (for Ben, after the AI's draft)"}


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


# ---- the drafts fixed after the comparison (review round 5: resolutions.yaml draft_fixes) ----------------------

AS_DRAFTED = book_eval.DRAFTS.parent / "records/as_drafted/general.yaml"
RUNS = book_eval.DRAFTS.parent / "records/runs"


@pytest.fixture(scope="module")
def as_drafted():
    return book_eval.rules_of(AS_DRAFTED)


def fixes():
    return (load(book_eval.RESOLUTIONS) or {}).get("draft_fixes") or []


def reverted(drafts, as_drafted, rule_ids):
    """The drafts with these rules put back as the AI drafted them (a rule added after the draft taken out)."""
    ai = {r["id"]: r for r in as_drafted}
    return [ai[r["id"]] if r["id"] in rule_ids else r for r in drafts if r["id"] not in rule_ids or r["id"] in ai]


def case_verdicts(case_id, key, drafts, as_drafted, ctx):
    """(key's verdict, the drafts' verdict) on the part a disagreement was found on, for the same design: the
    worked example the case names, taken from the key, or from the AI's own drafts (a fix may renumber examples)."""
    pid, whose, rest = case_id.split("/", 2)
    rule_n, label = rest.rsplit("/", 1)
    rule_id, n = rule_n.rsplit("#", 1)
    source = {r["id"]: r for r in (key if whose == "key" else as_drafted)}[rule_id]
    k = [r for r in key if book_eval.own_piece(r) == pid]
    d = [r for r in drafts if book_eval.own_piece(r) == pid]
    ex = book_eval.completed(source["examples"][int(n) - 1], k + d)
    part = ("", "") if label == "the building" else ("", label[len("none in "):]) if label.startswith("none in ") \
        else (label, "")
    allowed = ctx.allowed()
    return book_eval.verdicts(k, ex, allowed).get(part, "no row"), book_eval.verdicts(d, ex, allowed).get(part, "no row")


def test_every_wrong_draft_is_fixed_and_every_stricter_one_only_needs_review(ctx, key, drafts):
    """No cause left is a draft that is wrong; a cause left where the drafts are stricter than the law gives needs
    review on every row, never a fail (a known difference, kept: resolutions.yaml)."""
    causes, resolutions = book_eval.resolutions_of()
    assert not [n for n, c in causes.items() if c["verdict"] == "draft_wrong"]
    for f in book_eval.compare(key, drafts, ctx):
        if resolutions[f["id"]]["verdict"] == "drafts_stricter":
            assert f["draft"] == "needs_review", (f["id"], f["draft"])


def test_each_draft_fix_says_what_why_and_the_law(drafts):
    by_id = {r["id"]: r for r in drafts}
    assert {f["cause"] for f in fixes()} >= {"r318_2_doors_counted", "r319_1_room_a_loft_opens_to"}
    for fix in fixes():
        assert fix["verdict"] in VERDICTS and fix["why"].strip() and fix["fixed"].strip() and fix["law"].strip()
        assert (type(fix.get("false_pass_risk")) is bool) == (fix["verdict"] == "draft_wrong"), fix["cause"]
        assert fix["cases"] and fix["rules"], fix["cause"]
        for rid in fix["rules"]:           # each rule it changed records the change, naming the cause
            assert any(fix["cause"] in r["why"] for r in by_id[rid].get("revised") or []), (fix["cause"], rid)


@pytest.mark.parametrize("fix", fixes(), ids=lambda f: f["cause"])
def test_each_fixed_draft_agrees_with_the_key_where_the_ai_draft_did_not(ctx, key, drafts, as_drafted, fix):
    """Every disagreement a fix settled, on the same design: the fixed drafts give the key's answer, and the AI's own
    rules (the fix reverted) don't. The revert is part of the test, so it fails on revert by construction."""
    back = reverted(drafts, as_drafted, set(fix["rules"]))
    assert back != drafts and len(back) >= len(drafts) - 1
    for case in fix["cases"]:
        k, d = case_verdicts(case, key, drafts, as_drafted, ctx)
        assert k == d, (case, "fixed drafts", k, d)
        k, d = case_verdicts(case, key, back, as_drafted, ctx)
        assert k != d, (case, "the AI's own rules agree: the case is no evidence of the fix", k, d)


def piece_result(rules, piece, design, given, ctx):
    """The worst result the rules of one piece give a design (fail, then needs review, then pass)."""
    from rule_format import parts
    from rule_format.rulebook import outcome
    got = {row["outcome"] for r in rules if book_eval.own_piece(r) == piece and parts.is_part_rule(r)
           for row in parts.rows(r, design, given, ctx.allowed())}
    got |= {outcome(r, given, ctx.allowed()) for r in rules
            if book_eval.own_piece(r) == piece and not parts.is_part_rule(r)}
    return min(got, key=book_eval.WORST.index)


def test_a_two_family_house_whose_doors_serve_one_unit_no_longer_passes(ctx, drafts, as_drafted):
    """The false pass the AI's count allowed (cause r318_2_doors_counted): two dwelling units, two good egress doors
    (both may serve one unit). The AI's count passes it once its proposed measure egress_doors is measured (today it
    isn't, so it needs review: the false pass was waiting for that measure); the fixed drafts need review."""
    from rule_format import parts
    from rule_format.rulebook import _outcome
    good = {"door_side_hinged": True, "door_clear_width": 34, "door_clear_height": 80}
    design = {"egress_door": [{"id": "d1", "measures": good}, {"id": "d2", "measures": good}]}
    given = {"dwelling_units": 2, "egress_doors": 2}
    count = next(r for r in as_drafted if r["id"] == "general.r318_2_egress_door_per_dwelling_unit")
    assert _outcome(count, given, ctx.allowed(), {"egress_doors": "number"}) == "pass"
    assert "egress_doors" not in {n for r in drafts for n in parts.formula_names(r)}
    assert piece_result([r for r in drafts if "readily_openable" not in r["id"]], "R318.2", design, given,
                        ctx) == "needs_review"
    one = {"dwelling_units": 1}                       # and a house with none marked fails
    assert piece_result(drafts, "R318.2", {"egress_door": []}, one, ctx) == "fail"


def test_a_loft_whose_room_is_not_labeled_no_longer_passes(ctx, drafts, as_drafted):
    """The false pass of cause r319_1_room_a_loft_opens_to: a bedroom with a good escape opening, and a sleeping loft
    whose room isn't labeled (no loft_room). The AI's rules pass R319.1; the fixed drafts need review."""
    design = {"sleeping_room": [{"id": "b1"}], "basement": [], "habitable_attic": [], "loft_room": [],
              "emergency_escape_opening": [{"id": "w1", "within": "b1",
                                            "measures": {"opening_operable": True, "opening_opens_to_yard": True}}],
              "sleeping_loft": [{"id": "l1"}]}
    assert piece_result(as_drafted, "R319.1", design, {}, ctx) == "pass"
    assert piece_result(drafts, "R319.1", design, {}, ctx) == "needs_review"


@pytest.mark.parametrize("measure", ["area_well_projection", "area_well_width"])
def test_an_area_well_with_a_ladder_never_passes_on_its_unmeasured_reach(ctx, drafts, as_drafted, measure):
    """Found while fixing (round 5): a well 36 in on one side with a ladder, which may reach more than R319.4.1's 6 in
    into it (not measured), passes the AI's rules once the opening opens fully; the fixed drafts need review. Under
    30 in it fails even with a ladder, where the AI's rules only need review. Each side's rule is checked on its own,
    the other side's rule left as fixed (review round 5: a revert of one of the two was pinned by nothing)."""
    well = {"opening_below_grade": True, "area_well_area": 12, "area_well_projection": 40, "area_well_width": 40,
            "area_well_depth": 40, "area_well_ladder": True, "opening_fully_openable": True}
    design = lambda n: {"emergency_escape_opening": [{"id": "w1", "measures": well | {measure: n}}]}
    sides = {"general.r319_4_1_area_well_min_projection", "general.r319_4_1_area_well_min_width"}
    rid = f"general.r319_4_1_area_well_min_{measure.removeprefix('area_well_')}"
    full = "general.r319_4_1_area_well_allows_full_opening"
    ai = [r for r in reverted(drafts, as_drafted, sides | {full}) if r["kind"] == "rule"]   # its flag set aside
    assert piece_result(ai, "R319.4.1", design(36), {}, ctx) == "pass"
    assert piece_result(drafts, "R319.4.1", design(36), {}, ctx) == "needs_review"
    this_side = reverted(drafts, as_drafted, {rid})               # only this side's rule as the AI drafted it
    assert piece_result(this_side, "R319.4.1", design(24), {}, ctx) == "needs_review"
    assert piece_result(drafts, "R319.4.1", design(24), {}, ctx) == "fail"


def test_every_change_after_the_ai_is_recorded_in_the_rule(drafts, as_drafted, ctx):
    """Principle 5: a drafted rule differs from the AI's own (records/as_drafted/) only in the fields its `revised`
    names; a rule added after the draft says so (field: rule) and isn't the drafting script's; none is dropped."""
    ai = {r["id"]: r for r in as_drafted}
    assert set(ai) <= {r["id"] for r in drafts}, "a drafted rule was dropped"
    for r in drafts:
        named = {x["field"] for x in r.get("revised") or []}
        if r["id"] not in ai:
            assert named == {"rule"} and not r["drafted_by"].startswith("rule_drafting/"), r["id"]
            continue
        changed = {k for k in set(r) | set(ai[r["id"]]) if k != "revised" and r.get(k) != ai[r["id"]].get(k)}
        assert changed == named, (r["id"], "changed", sorted(changed), "recorded", sorted(named))


def test_the_ai_rules_kept_as_drafted_are_the_recorded_calls_answers(as_drafted):
    """records/as_drafted/ holds the AI's own rules: each one's formulas are those of the last recorded answer that
    drafted it (records/runs/), so a change after the draft can't hide in the copy."""
    import json
    answers = {}
    for path in sorted(RUNS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            call = json.loads(line)
            if call.get("answer"):
                for t in json.loads(call["answer"])["templates"]:
                    answers[f"general.{book_eval.slug(call['unit'])}_{t['id_suffix']}"] = t
    for r in as_drafted:
        t = answers[r["id"]]
        assert (r["kind"], r.get("check", ""), r.get("applies_when", ""), r.get("for_each", ""),
                r.get("when_none", "")) == \
            (t["kind"], t["check"], t["applies_when"], t["for_each"], t["when_none"]), r["id"]
        assert [x["when"] for x in r.get("review_when") or []] == [x["when"] for x in t["review_when"]], r["id"]


def test_fully_openable_is_asked_of_the_opening_as_installed_in_its_well():
    """R319.4.1's full-opening rule reads opening_fully_openable: its meaning must ask about the opening as installed,
    the area well included, or a sash blocked by the well wall passes on the window's own hardware (review round 5)."""
    from rule_format import parts
    meaning = parts.registry()["emergency_escape_opening"]["measures"]["opening_fully_openable"]["meaning"]
    assert "as installed" in meaning and "area well" in meaning, meaning


def test_a_guard_top_that_is_the_stairs_handrail_is_held_to_r320_2_at_any_drop(ctx, key, drafts):
    """Review round 6: limiting R321.1.2 to required guards (a drop over 30 in) left a guard top that serves as the
    stair's only handrail checked by nothing on a lower drop (no handrail part is modeled for it): a 42 in one passed.
    It is the stair's handrail, and R320.2's 34 to 38 in holds at any drop: both the drafts and the key fail it."""
    def design(height, top):
        return {"stair": [{"id": "s1", "measures": {"stair_riser_count": 4, "stair_handrail_sides": 1,
                                                    "stair_spiral": False, "stair_serves_sleeping_loft": False}}],
                "handrail": [],
                "open_side": [{"id": "e1", "measures": {"open_side_drop": 24, "guard_present": True,
                                                        "open_side_on_stair": True, "guard_is_handrail": True,
                                                        "guard_height": height, "guard_height_max": top}}]}
    for rules in (drafts, key):
        assert piece_result(rules, "R321.1.2", design(42, 44), {}, ctx) == "fail"
        assert piece_result(rules, "R321.1.2", design(36, 37), {}, ctx) == "pass"
        # review round 7: above 38 in only somewhere may be a fitting R320.2 exception 2 allows: needs review, as
        # the same rail modeled as a handrail part does; a required guard's top keeps R321.1.2's 38 in at most
        assert piece_result(rules, "R321.1.2", design(35, 40), {}, ctx) == "needs_review"
        required = design(35, 40)
        required["open_side"][0]["measures"]["open_side_drop"] = 36
        assert piece_result(rules, "R321.1.2", required, {}, ctx) == "fail"
