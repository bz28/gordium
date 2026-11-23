import copy
import datetime
import json
import math

import pytest
import yaml

from rule_format.rulebook import (TERM_SCHEMAS, Context, _canonical, approval_hash, load, locate, outcome, quote_at, tokenize,
                                  pending_research, validate, validate_terms)


def quote_found(quote, tokens):
    """Token-boundary tests: is the quote somewhere on a one-line page made of these tokens?"""
    return bool(locate(quote, {1: tokens}))

PAGE_3 = {41: "Side (other side minimum) 10 ft 10 ft",
          42: "Rear (minimum, % of depth or feet, 25%/ 25%/",
          43: "whichever is less) 50 ft [fn16] 50 ft [fn16]",
          66: "(16) But not less than 20 ft.",
          67: "(18) A lot deeper than 500 ft is reviewed by the Board."}
QUOTE = "Rear (minimum, % of depth or feet, 25%/ 25%/ whichever is less) 50 ft [fn16]"
SOURCE = {"file": "charts.pdf", "page": 3, "lines": [42, 43], "quote": QUOTE}
NOTES = [{"file": "charts.pdf", "page": 3, "lines": [66, 66], "quote": "(16) But not less than 20 ft."},
         {"file": "charts.pdf", "page": 3, "lines": [67, 67], "quote": "(18) A lot deeper than 500 ft is reviewed by the Board."}]
RULE = {
    "id": "R-1b.rear_yard",
    "kind": "rule",
    "topic": "dimensions",
    "title": "Rear yard minimum (chart p.3, note 16)",
    "applies_when": 'use == "one_family_detached"',
    "check": "rear_yard >= max(min(0.25 * lot_depth, 50), 20)",
    "review_when": [{"when": "lot_depth > 500", "reason": "unusually deep lot"}],
    "sources": [SOURCE, *NOTES],
    "examples": [
        {"given": {"use": "one_family_detached", "rear_yard": 25, "lot_depth": 90}, "expect": "pass"},
        {"given": {"use": "one_family_detached", "rear_yard": 21, "lot_depth": 90}, "expect": "fail"},
    ],
    "drafted_by": "claude",
    "status": "draft",
}
ALLOWED = {"use": {"one_family_detached", "church"}}
CTX = Context(
    measures={"use", "rear_yard", "lot_depth"},
    uses={"one_family_detached"},
    topics={"dimensions"},
    sources={"charts.pdf": {"file": "charts.pdf", "sha256": "a" * 64}},
    reviewers={"jane"},
    pages={"charts.pdf": {3: {n: tokenize(t) for n, t in PAGE_3.items()}}},
)
APPROVED = {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 19),
            "approved_hash": approval_hash(RULE, CTX)}


@pytest.fixture
def ctx():
    return copy.deepcopy(CTX)


def rulebook(**changes):
    rule = copy.deepcopy(RULE) | changes
    return {"district": "R-1b", "rules": [{k: v for k, v in rule.items() if v is not None}]}


@pytest.mark.parametrize("values, expected", [
    ({"use": "church", "rear_yard": 0, "lot_depth": 90}, "not_applicable"),
    ({"use": "one_family_detached", "rear_yard": 30, "lot_depth": 90}, "pass"),
    ({"use": "one_family_detached", "rear_yard": 10, "lot_depth": 90}, "fail"),
    ({"use": "one_family_detached", "rear_yard": 30, "lot_depth": 600}, "needs_review"),
    ({"use": "one_family_detached", "lot_depth": 90}, "needs_review"),               # missing
    ({"use": "one_family_detached", "rear_yard": 50, "lot_depth": math.nan}, "needs_review"),  # failed measurement
    ({"use": "one_family_detached", "rear_yard": "far", "lot_depth": 90}, "needs_review"),     # wrong type
    ({"rear_yard": 30, "lot_depth": 90}, "needs_review"),                            # use unknown
])
def test_outcome(values, expected):
    assert outcome(RULE, values, ALLOWED) == expected


@pytest.mark.parametrize("check, values", [
    ("stories != 4", {"stories": "4"}),                       # text where a number belongs
    ('use not in ["church"]', {"use": 5}),                     # number where text belongs
    ("not (rear_yard < 0 < use)", {"rear_yard": 5, "use": "x"}),  # bad link after a false one
    ("not (rear_yard < 1e300 * 1e300 - 1e300 * 1e300)", {"rear_yard": 5}),  # arithmetic gives NaN
    ("not (lot_area * 1e308 == 1)", {"lot_area": 5}),         # arithmetic overflows to infinity
    ("stories == use", {"stories": "3", "use": "3"}),          # stories must be a number (measures.yaml)
])
def test_bad_values_never_pass(check, values):
    assert outcome({"kind": "rule", "check": check}, values, ALLOWED) == "needs_review"


def test_non_boolean_check_never_passes():
    rule = RULE | {"check": "rear_yard - 20"}  # gives a number, not true/false
    assert outcome(rule, {"use": "one_family_detached", "rear_yard": 10, "lot_depth": 90}, ALLOWED) == "needs_review"


def test_unrecognized_use_needs_review():
    allowed = {"use": {"one_family_detached"}}
    assert outcome(RULE, {"use": "One-Family", "rear_yard": 1, "lot_depth": 90}, allowed) == "needs_review"
    church_only = {"kind": "rule", "check": 'use not in ["church"]'}
    assert outcome(church_only, {"use": "Church"}, {"use": {"church", "one_family_detached"}}) == "needs_review"


def test_outcome_fails_closed():
    church_only = {"kind": "rule", "check": 'use not in ["church"]'}
    with pytest.raises(TypeError):
        outcome(church_only, {"use": "castle"})                       # the use list is required
    assert outcome(church_only, {"use": "castle"}, {}) == "needs_review"   # no list given = unrecognized


def test_approval_needs_redoing_when_a_cited_document_is_replaced(ctx):
    assert validate(rulebook(**APPROVED), ctx) == []
    ctx.sources["charts.pdf"]["sha256"] = "b" * 64                    # a new version of the charts
    assert any("cited document was replaced" in p for p in validate(rulebook(**APPROVED), ctx))


def test_negative_or_huge_measurements_need_review():
    values = {"use": "one_family_detached", "lot_depth": 90}
    assert outcome(RULE, values | {"rear_yard": -30}, ALLOWED) == "needs_review"
    assert outcome(RULE, values | {"rear_yard": 10**400}, ALLOWED) == "needs_review"


def test_flag_always_needs_review():
    flag = {k: v for k, v in RULE.items() if k != "check"} | {"kind": "flag"}
    assert outcome(flag, {"use": "one_family_detached", "rear_yard": 99, "lot_depth": 90}, ALLOWED) == "needs_review"


def test_valid_rulebooks(ctx):
    assert validate(rulebook(), ctx) == []
    assert validate(rulebook(**APPROVED), ctx) == []


@pytest.mark.parametrize("changes, problem", [
    ({"id": "R-2a.rear_yard"}, "id must start with 'R-1b.'"),
    ({"kind": "maybe"}, "kind must be one of"),
    ({"topic": "vibes"}, "unknown topic"),
    ({"title": None}, "missing 'title'"),
    ({"title": "   "}, "missing 'title'"),
    ({"title": "Rear yard\nminimum"}, "one-line label"),
    ({"title": "Rear yard\rminimum"}, "one-line label"),
    ({"title": "Rear yard at least 25% of lot depth or 50 ft, whichever is less, but never under 20 ft."},
     "one-line label"),                                                      # a retelling, not a label
    ({"says": "Rear yard at least 25% of lot depth."}, "unknown field 'says'"),
    ({"answers": [{"question": "q?", "answer": "a", "answered_by": "claude",
                   "answered_on": datetime.date(2026, 10, 20)}]}, "answered_by must be a reviewer"),
    ({"check": None}, "a 'rule' needs a 'check'"),
    ({"check": "rear_yard >= setback"}, "unknown measure 'setback'"),
    ({"applies_when": 'use == "castle"'}, "unknown use 'castle'"),
    ({"check": "import os"}, "cannot read formula"),
    ({"check": "rear_yard - 20"}, "must be a true/false test"),
    ({"check": "rear_yard >= 20, lot_depth > 0"}, "must be a true/false test"),
    ({"check": 35}, "formula must be text"),
    ({"check": ["rear_yard >= 20"]}, "formula must be text"),
    ({"review_when": [{"when": "lot_depth > 1"}]}, "needs a 'reason'"),
    ({"review_when": {"when": "lot_depth > 1"}}, "'review_when' must be a list of mappings"),
    ({"sources": []}, "needs at least one source"),
    ({"sources": ["charts.pdf p3"]}, "'sources' must be a list of mappings"),
    ({"sources": [SOURCE | {"file": "other.pdf"}]}, "not in sources.yaml"),
    ({"sources": [SOURCE | {"page": "3"}]}, "needs 'page' (number), 'lines'"),
    ({"sources": [{k: v for k, v in SOURCE.items() if k != "lines"}]}, "needs 'page' (number), 'lines'"),
    ({"sources": [SOURCE | {"lines": [42]}]}, "needs 'page' (number), 'lines'"),
    ({"sources": [SOURCE | {"page": 9}]}, "page 9 does not exist"),
    ({"sources": [SOURCE | {"quote": "Rear (minimum, % of depth or feet, 30%/"}]}, "not on this page"),
    ({"sources": [SOURCE | {"lines": [41, 43]}]}, "isn't at lines 41-43; it is at lines 42-43"),   # range too wide
    ({"sources": [SOURCE | {"lines": [42, 42]}]}, "isn't at lines 42-42; it is at lines 42-43"),   # too narrow
    ({"sources": [SOURCE | {"quote": "Rear (minimum … 50 ft"}]}, "one exact passage"),
    ({"sources": [SOURCE | {"quote": "…"}]}, "one exact passage"),
    ({"sources": [SOURCE | {"file": ["charts.pdf"]}]}, "not in sources.yaml"),
    ({"examples": []}, "worked examples that pass and that fail"),
    ({"examples": [{"given": {}, "expect": "needs_review"}]}, "worked examples that pass and that fail"),
    ({"examples": RULE["examples"] + [{"given": {"use": "one_family_detached", "rear_yard": 25, "lot_depth": 90},
                                       "expect": "fail"}]}, "expected fail, got pass"),
    ({"examples": RULE["examples"] + [{"given": {"use": "one_family_detached", "rear_yard": "25", "lot_depth": 90},
                                       "expect": "needs_review"}]}, "wrong kind of value for ['rear_yard']"),
    ({"topic": ["dimensions"]}, "'topic' must be text"),
    ({"id": ["R-1b.x"]}, "'id' must be text"),
    ({"drafted_by": ["claude", "jane"]} | APPROVED, "'drafted_by' must be text"),
    (APPROVED | {"approved_by": ["jane"]}, "'approved_by' must be text"),
    (APPROVED | {"check": "rear_yard >= 20"}, "changed since it was approved"),
    (APPROVED | {"approved_hash": None}, "changed since it was approved"),
    (APPROVED | {"id": "R-1b.rear_yard_copy"}, "changed since it was approved"),
    (APPROVED | {"drafted_by": "Jane "}, "can't be approved by the person who drafted it"),
    ({"examples": RULE["examples"] + [{"given": {"use": "castle"}, "expect": "needs_review"}]}, "unknown use 'castle'"),
    ({"examples": RULE["examples"] + [{"given": {1: 2}, "expect": "needs_review"}]}, "'given' must be a mapping"),
    ({"examples": [{"given": {}, "expect": ["pass"]}]}, "worked examples that pass and that fail"),
    ({"examples": [{"given": {"rear_yrd": 30}, "expect": "needs_review"}]}, "unknown measures ['rear_yrd']"),
    ({"examples": [{"given": "x", "expect": "pass"}]}, "'given' must be a mapping"),
    ({"status": "approved"}, "approved_by must be a reviewer"),
    (APPROVED | {"approved_by": "claude"}, "approved_by must be a reviewer"),
    (APPROVED | {"drafted_by": "jane"}, "can't be approved by the person who drafted it"),
    (APPROVED | {"approved_on": "last week"}, "approved_on must be a date"),
    ({"drafted_by": None}, "missing 'drafted_by'"),
    ({"colour": "red"}, "unknown field 'colour'"),
    # a change after the AI's draft (house egress review, round 5): {field, by, date, why}, as a label's
    ({"revised": {"field": "check"}}, "'revised' must be a list of {field, by, date, why}"),
    ({"revised": [{"field": "check", "by": "Claude", "date": datetime.date(2026, 11, 13)}]}, "exactly field, by, date, why"),
    ({"revised": [{"field": "colour", "by": "Claude", "date": datetime.date(2026, 11, 13), "why": "w"}]},
     "revised field 'colour'"),
    ({"revised": [{"field": "status", "by": "Claude", "date": datetime.date(2026, 11, 13), "why": "w"}]},
     "revised field 'status'"),
    ({"revised": [{"field": "check", "by": " ", "date": datetime.date(2026, 11, 13), "why": "w"}]}, "must be text"),
    ({"revised": [{"field": "check", "by": "Claude", "date": "2026-11-13", "why": "w"}]}, "must be a date"),
])
def test_invalid_rules_are_rejected(ctx, changes, problem):
    problems = validate(rulebook(**changes), ctx)
    assert any(problem in p for p in problems), problems


def test_a_rule_records_its_changes_after_the_ais_draft(ctx):
    revised = [{"field": "check", "by": "Claude for Ben", "date": datetime.date(2026, 11, 13), "why": "the law"},
               {"field": "rule", "by": "Claude for Ben", "date": datetime.date(2026, 11, 13), "why": "added"}]
    assert validate(rulebook(revised=revised), ctx) == []


@pytest.mark.parametrize("book, problem", [
    (None, "must be a mapping with a 'district'"),                 # empty file
    ({"district": "R-1b", "rules": {"a": 1}}, "'rules' must be a non-empty list"),
    ({"district": "R-1b", "rules": ["x"]}, "must be a mapping"),
])
def test_badly_shaped_files_are_reported_not_crashed(ctx, book, problem):
    assert any(problem in p for p in validate(book, ctx))


def test_duplicate_ids_are_rejected(ctx):
    book = rulebook()
    book["rules"] *= 2
    assert any("duplicate id" in p for p in validate(book, ctx))


def test_duplicate_yaml_keys_are_rejected(tmp_path):
    path = tmp_path / "R-1b.yaml"
    path.write_text("district: R-1b\nrules:\n  - check: a > 1\n    check: a > 2\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError, match="duplicate key 'check'"):
        load(path)




def test_quote_number_must_not_match_inside_a_bigger_number():
    page = tokenize("Rear yard minimum 25 feet in depth for all lots; side yard 5 feet in depth for all lots")
    assert quote_found("5 feet in depth for all lots", page)          # the real '5 feet', later on the page
    assert not quote_found("5 feet in depth for all lots", tokenize("Rear yard 25 feet in depth for all lots"))
    assert not quote_found("yard 2", tokenize("yard 25"))


@pytest.mark.parametrize("page", [
    "rear yard 2.5 feet in depth for all lots",       # decimal
    "rear yard 1,500 feet in depth for all lots",     # thousands separator
])
def test_quote_number_must_be_the_whole_number(page):
    assert not quote_found("5 feet in depth for all lots", tokenize(page))
    assert not quote_found("500 feet in depth for all lots", tokenize(page))


@pytest.mark.parametrize("quote, page", [
    ("rear yard minimum shall be 2.", "rear yard minimum shall be 2.5 feet"),   # ends on '.', page goes on
    (".5 feet in depth for all lots", "rear yard 2.5 feet in depth for all lots"),
    (",500 square feet of lot area", "lot of 1,500 square feet of lot area"),
    ("5 acres minimum lot size", "a lot of .5 acres minimum lot size"),          # decimal without a leading 0
])
def test_quote_edges_cannot_cut_a_number(quote, page):
    assert not quote_found(quote, tokenize(page))


@pytest.mark.parametrize("quote, page", [
    ("2 the required yard depth", "1/2 the required yard depth"),                 # fraction
    ("required stories are 3 4 3", "required stories are 3 4 3/2"),
])
def test_quote_edges_cannot_cut_a_fraction(quote, page):
    assert not quote_found(quote, tokenize(page))


@pytest.mark.parametrize("quote, page", [
    ("maximum number of stories: 3", "Maximum number of stories: 3. Lot coverage"),  # sentence period
    ("minimum lot width of 50", "minimum lot width of 50, except corner lots"),      # list comma
    ("designation of R-1 or R-2", "designation of R-1 or R-2, see §325-8(E)."),
])
def test_quote_may_end_on_a_number_before_punctuation(quote, page):
    assert quote_found(quote, tokenize(page))


def test_approval_check_survives_badly_shaped_sources(ctx):
    for bad in (["charts.pdf"], [{"file": ["charts.pdf"]}], "charts.pdf", 5, [{**RULE["sources"][0], 5: "x"}]):
        assert validate(rulebook(**APPROVED, sources=bad), ctx)   # must report problems, not crash
    for odd in ({"check": {5: "x", "a": 1}},                                   # nested mixed key types
                {"sources": [{**RULE["sources"][0], "quote": {5: "x", "a": 1}}]},
                {"review_when": [{"when": {5: "x", "a": 1}, "reason": "r"}]}):
        assert validate(rulebook(**APPROVED | odd), ctx)                       # reported, never a crash
    assert any("unknown field 3" in p for p in validate(
        rulebook(**APPROVED, review_when=[{"when": "lot_depth > 500", "reason": "x", 3: 1}]), ctx))


def test_separate_table_cells_do_not_merge():
    assert not quote_found("25 ft 50 ft 45 ft 35 ft", tokenize("2 5 ft 50 ft 45 ft 35 ft"))


def test_quote_must_start_on_a_word_boundary():
    assert not quote_found("ear yard minimum depth", tokenize("Rear yard minimum depth"))




@pytest.mark.parametrize("text, expected", [
    ("Rear yard: 25%/ 50 ft [fn16]", ["rear", "yard", ":", "25", "%", "/", "50", "ft", "[fn16]"]),
    ("2.5 feet, 1,500 sf, 3/2 stories, .5 acres", ["2.5", "feet", ",", "1,500", "sf", ",", "3/2", "stories", ",", ".5", "acres"]),
    ("R-1b and R-1", ["r", "-", "1b", "and", "r", "-", "1"]),
    ("stories: 3. Lot", ["stories", ":", "3", ".", "lot"]),
    ("“Quoted” — dash", ['"', "quoted", '"', "-", "dash"]),
    ("maximum 3/35, minimum/maximum", ["maximum", "3/35", ",", "minimum", "/", "maximum"]),
    ("(see above).The rear", ["(", "see", "above", ")", ".", "the", "rear"]),
    ("Sec. 4.A.5 feet, No.5, ...5", ["sec", ".", "4", ".", "a", ".", "5", "feet", ",", "no", ".", "5", ",", ".", ".", ".", "5"]),
])
def test_tokenize(text, expected):
    assert tokenize(text) == expected


@pytest.mark.parametrize("quote, page", [
    ("Front setback, minimum/maximum 0 feet", "Front setback, minimum/maximum 0 feet/2 feet"),   # Ch. 325 p.157
    ("Waterfront District regulations", "WE/WFD West End/Waterfront District regulations"),   # p.23
    ("Maximum stories: 3", "Maximum stories: 3.Lot coverage 35%"),                          # no space after '.'
    ("The rear yard shall be", "(see above).The rear yard shall be"),
])
def test_quote_may_start_or_end_at_word_punctuation(quote, page):
    assert quote_found(quote, tokenize(page))


def test_quote_cannot_cut_a_district_name():
    assert not quote_found("designation of R-1 or R-2", tokenize("designation of R-1b or R-2a"))




def _jurisdiction(tmp_path, pdf_bytes=b"%PDF fake", header_sha=None, rows=()):
    j = tmp_path / "ny" / "town"
    (j / "1_source_documents").mkdir(parents=True)
    (j / "2_extracted_text").mkdir()
    (j / "1_source_documents/doc.pdf").write_bytes(pdf_bytes)
    import hashlib
    sha = hashlib.sha256(b"%PDF fake").hexdigest()
    (j / "1_source_documents/sources.yaml").write_text(f"documents:\n  - file: doc.pdf\n    sha256: {sha}\n", encoding="utf-8")
    lines = [json.dumps({"file": "doc.pdf", "sha256": header_sha or sha}), "", *map(json.dumps, rows)]
    (j / "2_extracted_text/doc.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return j


def test_context_loads_extracted_text(tmp_path):
    ctx = Context.for_jurisdiction(_jurisdiction(tmp_path, rows=[{"page": "2", "line": 1, "text": "Hello  World"}]))
    assert ctx.problems == []
    assert ctx.pages["doc.pdf"] == {2: {1: ["hello", "world"]}}


def test_context_reports_changed_pdf_and_stale_text(tmp_path):
    changed = Context.for_jurisdiction(_jurisdiction(tmp_path / "a", pdf_bytes=b"changed"))
    assert any("fingerprint does not match" in p for p in changed.problems)
    assert "doc.pdf" not in changed.pages
    stale = Context.for_jurisdiction(_jurisdiction(tmp_path / "b", header_sha="old"))
    assert any("different version" in p for p in stale.problems)
    assert any("different version" in p for p in stale.file_problems["doc.pdf"])
    assert "doc.pdf" not in stale.pages


def test_cli_reports_broken_folders_and_files_instead_of_crashing(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    (tmp_path / "regulations/jurisdictions/ny/no_sources").mkdir(parents=True)  # no sources.yaml
    j = _jurisdiction(tmp_path / "regulations/jurisdictions", rows=[])
    (j / "5_zoning_rules/R-1b.yaml").mkdir(parents=True)                        # a folder named like a file
    (j / "5_zoning_rules/R-2a.yaml").write_bytes(b"\xff\xfe not text")
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.main() == 1
    out = capsys.readouterr().out
    assert "no_sources: can't load sources" in out
    assert "R-2a.yaml" in out and "can't read file" in out


def test_cli_reports_district_not_matching_file_name(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    j = _jurisdiction(tmp_path / "regulations/jurisdictions", rows=[])
    (j / "5_zoning_rules").mkdir()
    (j / "5_zoning_rules/R-1a.yaml").write_text("district: R-1b\nrules: []\n", encoding="utf-8")
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.main() == 1
    assert "doesn't match the file name 'R-1a'" in capsys.readouterr().out


def test_cli_keeps_going_when_validation_itself_fails(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    j = _jurisdiction(tmp_path / "regulations/jurisdictions", rows=[])
    (j / "5_zoning_rules").mkdir()
    for name in ("R-1a", "R-1b"):
        (j / f"5_zoning_rules/{name}.yaml").write_text(f"district: {name}\nrules: []\n", encoding="utf-8")
    def broken(book, ctx):
        raise TypeError("boom")
    import rule_format.rulebook as rulebook
    monkeypatch.setattr(rulebook, "validate", broken)        # the one per-file check the CLI uses
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.main() == 1
    out = capsys.readouterr().out
    assert out.count("validator error (TypeError: boom)") == 2


def test_fingerprint_is_stable_for_any_yaml_value():
    assert _canonical({3, 1, 2}) == {"set": [1, 2, 3]}                 # YAML !!set, any hash seed
    assert _canonical(b"\x01") == {"bytes": "01"}                       # YAML !!binary
    assert _canonical({1: "a"}) != _canonical({"1": "a"})                # 1 and "1" stay different


def test_review_reason_must_be_text(ctx):
    bad = rulebook(review_when=[{"when": "lot_depth > 500", "reason": {"a", "b"}}])
    assert any("needs a 'reason' (text)" in p for p in validate(bad, ctx))


def test_rule_with_open_questions_cannot_be_approved(ctx):
    question = {"open_questions": ["Is the yard measured to the wall or the eave?"],
                "research": [pending_research("Is the yard measured to the wall or the eave?", "a test")]}
    assert validate(rulebook(**question), ctx) == []                    # fine as a draft
    approved = APPROVED | question                                          # adding a question blocks approval
    assert any("open_questions remain" in p for p in validate(rulebook(**approved), ctx))
    assert any("'open_questions' must be a list" in p for p in validate(rulebook(open_questions="why?"), ctx))


def test_decimal_point_needs_a_clean_start():
    assert tokenize("A .5") == ["a", ".5"] and tokenize("A.5") == ["a", ".", "5"]   # documented spacing case
    assert not quote_found(".5 feet of depth here", tokenize("Section A.5 feet of depth here"))
    assert quote_found("5 feet of depth here", tokenize("Section A.5 feet of depth here"))


def test_quote_must_sit_exactly_on_the_cited_lines():
    page = {n: tokenize(t) for n, t in PAGE_3.items()}
    assert quote_at(QUOTE, page, 42, 43)
    assert quote_at("Rear (minimum, % of depth", page, 42, 42)            # part of one line
    assert not quote_at("Rear (minimum, % of depth", page, 42, 43)        # doesn't reach line 43
    assert not quote_at("Side (other side minimum) 10 ft", page, 42, 42)  # it's on line 41
    assert not quote_at(QUOTE, page, 42, 44)                              # line 44 doesn't exist
    assert locate("50 ft [fn16]", page) == [(43, 43), (43, 43)]                 # it appears twice on line 43


def test_locate_finds_long_and_repeated_quotes():
    page = {n: tokenize(f"word{n} filler") for n in range(1, 16)}
    long = " ".join(f"word{n} filler" for n in range(1, 13))
    assert locate(long, page) == [(1, 12)]                                  # no line cap
    assert any("it is at lines 1-12" in p for p in _source_issue(page, long, [2, 13]))
    assert locate("filler", page)[:2] == [(1, 1), (2, 2)]                    # one entry per occurrence


def _source_issue(page, quote, lines):
    from rule_format.rulebook import _source_problems
    ctx = copy.deepcopy(CTX)
    ctx.pages["charts.pdf"][3] = page
    return _source_problems([{"file": "charts.pdf", "page": 3, "lines": lines, "quote": quote}], ctx)


def test_cite_helper(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    place = "ny/town"
    _jurisdiction(tmp_path / "regulations/jurisdictions", rows=[
        {"page": 2, "line": 1, "text": "Rear yard minimum twenty feet"},
        {"page": 2, "line": 2, "text": "Side yard ten feet, side yard ten feet"}])
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.cite([place, "doc.pdf", "2", "Rear yard minimum twenty feet"]) == 0
    assert "lines: [1, 1]" in capsys.readouterr().out
    assert cli.cite([place, "doc.pdf", "2", "side yard ten feet"]) == 1          # occurs twice on line 2
    assert "more than once" in capsys.readouterr().out
    assert cli.cite([place, "doc.pdf", "9", "x"]) == 1 and "no page 9" in capsys.readouterr().out
    assert cli.cite([place, "typo.pdf", "2", "x"]) == 1 and "not in sources.yaml" in capsys.readouterr().out
    sources = tmp_path / "regulations/jurisdictions" / place / "1_source_documents/sources.yaml"
    sources.write_text(sources.read_text(encoding="utf-8") + "    quotable: false\n    not_quotable_because: two columns\n", encoding="utf-8")
    assert cli.cite([place, "doc.pdf", "2", "Rear yard minimum twenty feet"]) == 1   # same answer as validation
    assert "isn't quotable yet: two columns" in capsys.readouterr().out
    assert cli.cite(["ny/nowhere", "doc.pdf", "2", "x"]) == 1 and "no jurisdiction" in capsys.readouterr().out


def test_cite_reports_stale_extracted_text(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    _jurisdiction(tmp_path / "regulations/jurisdictions", header_sha="old", rows=[])
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.cite(["ny/town", "doc.pdf", "2", "x"]) == 1
    assert "different version" in capsys.readouterr().out


def test_cite_reports_only_the_asked_files_problems(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    import hashlib
    j = _jurisdiction(tmp_path / "regulations/jurisdictions", header_sha="old", rows=[])   # doc.pdf: stale text
    (j / "1_source_documents/d.pdf").write_bytes(b"other")                                 # d.pdf: no text at all
    sha = hashlib.sha256(b"other").hexdigest()
    with open(j / "1_source_documents/sources.yaml", "a", encoding="utf-8") as f:
        f.write(f"  - file: d.pdf\n    sha256: {sha}\n")
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.cite(["ny/town", "d.pdf", "1", "x"]) == 1
    out = capsys.readouterr().out
    assert "d.pdf: no extracted text" in out and "doc" not in out


def test_quote_must_be_unique_on_the_page():
    page = {n: tokenize(t) for n, t in PAGE_3.items()}
    repeated = _source_issue(page, "50 ft [fn16]", [43, 43])
    assert any("appears 2 times" in p and "unique" in p for p in repeated)
    assert not any("isn't at lines" in p for p in repeated)
    assert _source_issue(page, QUOTE, [42, 43]) == []


def test_text_is_not_trusted_for_a_document_that_failed_its_checks(tmp_path):
    ctx = Context.for_jurisdiction(_jurisdiction(tmp_path, pdf_bytes=b"replaced", rows=[{"page": 1, "line": 1, "text": "x"}]))
    assert "doc.pdf" not in ctx.pages and "fingerprint does not match sources.yaml" in ctx.file_problems["doc.pdf"]


def test_document_listed_twice_is_reported(tmp_path):
    j = _jurisdiction(tmp_path, rows=[{"page": 1, "line": 1, "text": "x"}])
    s = (j / "1_source_documents/sources.yaml").read_text(encoding="utf-8")
    (j / "1_source_documents/sources.yaml").write_text(s + s.split("documents:\n", 1)[1], encoding="utf-8")
    ctx = Context.for_jurisdiction(j)
    assert "listed more than once in sources.yaml" in ctx.file_problems["doc.pdf"]
    assert "doc.pdf" not in ctx.pages                                         # its text isn't trusted


def test_documents_marked_not_quotable_are_refused(ctx):
    ctx.sources["charts.pdf"] |= {"quotable": False, "not_quotable_because": "two columns get mixed"}
    assert any("isn't quotable yet: two columns get mixed" in p for p in validate(rulebook(), ctx))


@pytest.mark.parametrize("entry, problem", [
    ({"file": "a.pdf", "sha256": "x", "quoteable": False}, "unknown field 'quoteable'"),
    ({"file": "a.pdf", "sha256": "x", "quotable": "false"}, "'quotable' must be true or false"),
    ({"file": "a.pdf", "sha256": "x", "quotable": False}, "'not_quotable_because' is missing"),
    ({"file": "a.pdf", "sha256": "x", "chart_pages": "2, 3"}, "'chart_pages' must be a list"),
    ({"file": "a.pdf", "sha256": "x", "chart_pages": [2, 2]}, "'chart_pages' must be a list"),
    ({"file": "a.pdf", "sha256": "x", "chart_pages": [0]}, "'chart_pages' must be a list"),
    ({"file": "a.pdf", "sha256": "x", "pages": 17, "chart_pages": [18]}, "'chart_pages' must be a list"),
])
def test_source_list_entries_fail_closed(entry, problem):
    from rule_format.rulebook import _source_entry_problems
    assert any(problem in p for p in _source_entry_problems(entry))


@pytest.mark.parametrize("value", ["false", 0, None])
def test_not_quotable_check_fails_closed(ctx, value):
    ctx.sources["charts.pdf"]["quotable"] = value
    assert any("isn't quotable yet" in p for p in validate(rulebook(), ctx))


def test_source_entry_problems_reach_the_file(tmp_path):
    j = _jurisdiction(tmp_path, rows=[{"page": 1, "line": 1, "text": "x"}])
    s = (j / "1_source_documents/sources.yaml").read_text(encoding="utf-8")
    (j / "1_source_documents/sources.yaml").write_text(s + "    quoteable: false\n", encoding="utf-8")
    ctx = Context.for_jurisdiction(j)
    assert any("unknown field 'quoteable'" in p for p in ctx.file_problems["doc.pdf"]) and "doc.pdf" not in ctx.pages


DEFINITION = {
    "term": "REAR YARD",
    "measures": ["rear_yard"],
    "sources": [SOURCE],
    "open_questions": ["Which line is the rear lot line on an irregular lot?"],
    "research": [{"question": "Which line is the rear lot line on an irregular lot?", "searched": [], "sources": [],
                  "why_open": "pending the 2026-10-20 research pass"}],
    "drafted_by": "claude",
    "status": "draft",
}


def test_valid_definitions_and_uses(ctx):
    assert validate_terms({"rear_yard": DEFINITION}, ctx, "definitions") == []
    use = {"name": "One-family dwelling, detached", "sources": DEFINITION["sources"],
           "drafted_by": "claude", "status": "draft"}
    assert validate_terms({"one_family_detached": use}, ctx, "uses") == []


@pytest.mark.parametrize("entries, problem", [
    ({}, "non-empty mapping"),
    ({"Rear Yard": DEFINITION}, "lowercase_with_underscores"),
    ({"rear_yard": DEFINITION | {"measures": ["rear_yrd"]}}, "unknown measure 'rear_yrd'"),
    ({"rear_yard": DEFINITION | {"says": "Open space behind the house."}}, "unknown field 'says'"),
    ({"rear_yard": DEFINITION | {"term": ["REAR YARD"]}}, "'term' must be text"),
    ({"rear_yard": DEFINITION | {"open_questions": "which line?"}}, "'open_questions' must be a list"),
    ({"rear_yard": DEFINITION | {"colour": "red"}}, "unknown field 'colour'"),
    ({"rear_yard": DEFINITION | {"sources": [SOURCE | {"quote": "Rear (minimum, % of depth or feet, 30%/"}]}},
     "not on this page"),
    ({"rear_yard": DEFINITION | {"status": "approved", "approved_by": "claude",
                                 "approved_on": datetime.date(2026, 10, 19)}}, "approved_by must be a reviewer"),
])
def test_invalid_definitions_are_rejected(ctx, entries, problem):
    assert any(problem in p for p in validate_terms(entries, ctx, "definitions"))


ANSWER = {"question": "Which line is the rear lot line on an irregular lot?", "answer": "The one opposite the street.",
          "answered_by": "jane", "answered_on": datetime.date(2026, 10, 20)}


@pytest.mark.parametrize("answers, problem", [
    ("the one opposite", "'answers' must be a list"),
    ([{"question": "q?", "answer": "a"}], "exactly question, answer, answered_by, answered_on"),
    ([ANSWER | {"answer": "  "}], "must be text"),
    ([ANSWER | {"question": 3}], "must be text"),
    ([ANSWER | {"answered_by": "claude"}], "answered_by must be a reviewer"),
    ([ANSWER | {"answered_on": "2026-10-20x"}], "answered_on must be a date"),
])
def test_invalid_answers_are_rejected(ctx, answers, problem):
    assert any(problem in p for p in validate_terms({"rear_yard": DEFINITION | {"answers": answers}}, ctx, "definitions"))


def test_answered_definition_can_be_approved(ctx):
    fields = TERM_SCHEMAS["definitions"]["approved"]
    answered = {k: v for k, v in DEFINITION.items() if k not in ("open_questions", "research")} | {"answers": [ANSWER]}
    approved = answered | {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 20),
                           "approved_hash": approval_hash(answered | {"id": "rear_yard"}, ctx, fields)}
    assert validate_terms({"rear_yard": approved}, ctx, "definitions") == []
    reworded = approved | {"answers": [ANSWER | {"answer": "The one at the back."}]}  # an answer is frozen too
    assert any("changed since it was approved" in p for p in validate_terms({"rear_yard": reworded}, ctx, "definitions"))


def test_approved_definition_needs_reapproval_after_an_edit(ctx):
    fields = TERM_SCHEMAS["definitions"]["approved"]
    answered = {k: v for k, v in DEFINITION.items() if k not in ("open_questions", "research")}
    approved = answered | {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 19),
                           "approved_hash": approval_hash(answered | {"id": "rear_yard"}, ctx, fields)}
    assert validate_terms({"rear_yard": approved}, ctx, "definitions") == []
    for edit in ({"term": "REAR YARDS"}, {"measures": ["rear_yard", "lot_depth"]}, {"answers": [ANSWER]},
                 {"sources": [SOURCE | {"lines": [41, 43], "quote": "10 ft [fn15] " + QUOTE}]}):
        assert any("changed since it was approved" in p
                   for p in validate_terms({"rear_yard": approved | edit}, ctx, "definitions"))
    assert any("changed since it was approved" in p                          # renamed: rules use the key
               for p in validate_terms({"side_yard": approved}, ctx, "definitions"))
    reopened = approved | {"open_questions": ["new doubt?"]}                 # a new question blocks approval
    assert any("open_questions remain" in p for p in validate_terms({"rear_yard": reopened}, ctx, "definitions"))


def test_definition_with_open_questions_cannot_be_approved(ctx):
    approved = DEFINITION | {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 19)}
    approved["approved_hash"] = approval_hash(approved | {"id": "rear_yard"}, ctx, TERM_SCHEMAS["definitions"]["approved"])
    assert any("open_questions remain" in p for p in validate_terms({"rear_yard": approved}, ctx, "definitions"))


def test_approved_entry_without_drafter_is_reported_not_crashed(ctx):
    entry = {k: v for k, v in DEFINITION.items() if k not in ("drafted_by", "open_questions", "research")}
    entry |= {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 19)}
    assert any("missing 'drafted_by'" in p for p in validate_terms({"rear_yard": entry}, ctx, "definitions"))


def test_a_use_decided_by_a_rule_must_cite_its_row(ctx):
    ctx.use_rows = {"one_family_detached": [SOURCE]}
    decides = rulebook(check='use == "one_family_detached" and rear_yard >= 20', applies_when=None,
                       examples=[{"given": {"use": "one_family_detached", "rear_yard": 25, "lot_depth": 90}, "expect": "pass"},
                                 {"given": {"use": "one_family_detached", "rear_yard": 10, "lot_depth": 90}, "expect": "fail"}])
    assert validate(decides, ctx) == []                                       # its row (lines 42-43) is cited
    elsewhere = {**SOURCE, "lines": [41, 41], "quote": "10 ft [fn15]"}
    ctx.use_rows = {"one_family_detached": [elsewhere]}
    assert any("use 'one_family_detached' is decided here but its row isn't cited" in p
               for p in validate(decides, ctx))
    assert validate(rulebook(), ctx) == []                                    # applies_when only scopes the rule
    flags = rulebook(review_when=[{"when": 'use == "one_family_detached"', "reason": "check by hand"}])
    assert any("use 'one_family_detached' is decided here" in p for p in validate(flags, ctx))  # review_when decides too


@pytest.mark.parametrize("uses", [["one_family_detached"], {"x": {"sources": "p.2"}},
                                  {"x": {"sources": [{"page": 2, "lines": [9, 9]}]}}, {"x": "y"}])
def test_malformed_uses_are_left_out_not_crashed(uses):
    from rule_format.rulebook import _use_rows
    assert _use_rows(uses) in ({}, {"x": []})


@pytest.mark.parametrize("edit", [{"title": "Rear yard"}, {"answers": [ANSWER | {"answer": "The one at the back."}]},
                                  {"answers": []}])
def test_approved_rule_needs_reapproval_after_answer_or_title_edit(ctx, edit):
    answered = copy.deepcopy(RULE) | {"answers": [ANSWER]}
    approved = answered | {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 20),
                           "approved_hash": approval_hash(answered, ctx)}
    assert validate({"district": "R-1b", "rules": [approved]}, ctx) == []
    assert any("changed since it was approved" in p
               for p in validate({"district": "R-1b", "rules": [approved | edit]}, ctx))


# Chart cells as sources, numbers traced to sources, yes/no and proposed measures, district names.
REAR_CELL = {"page": 3, "section": "Yard Dimensions", "row": "Rear (minimum, % of depth or feet, whichever is less)",
             "column": "R-1B", "value": "25%/ 50 ft [fn16]", "row_lines": [42, 43]}
CELL_SOURCE = {"file": "charts.pdf", "page": 3,
               "cell": {"section": "Yard Dimensions", "row": REAR_CELL["row"], "column": "R-1B"}}


@pytest.fixture
def chart_ctx(ctx):
    ctx.sources["charts.pdf"]["chart_pages"] = [3]
    ctx.cells = {"charts.pdf": {(3, "Yard Dimensions", REAR_CELL["row"], "R-1B"): REAR_CELL}}
    ctx.districts = {"R-1b", "R-2a"}
    ctx.measures |= {"district"}
    return ctx


def test_a_cited_chart_cell_supports_its_numbers(chart_ctx):
    assert validate(rulebook(sources=[CELL_SOURCE, *NOTES]), chart_ctx) == []


@pytest.mark.parametrize("source, problem", [
    (CELL_SOURCE | {"cell": CELL_SOURCE["cell"] | {"row": "Rear yard"}}, "no cell"),
    (CELL_SOURCE | {"page": 2}, "isn't one of the chart pages"),
    (CELL_SOURCE | {"lines": [42, 43]}, "exactly file, page and cell"),
    (CELL_SOURCE | {"cell": {"row": "Rear"}}, "needs section, row and column"),
])
def test_bad_cell_sources_are_rejected(chart_ctx, source, problem):
    assert any(problem in p for p in validate(rulebook(sources=[source, *NOTES]), chart_ctx))


@pytest.mark.parametrize("check, number", [("rear_yard >= max(min(0.3 * lot_depth, 50), 20)", "0.3"),
                                           ("rear_yard >= max(min(0.25 * lot_depth, 55), 20)", "55")])
def test_a_number_not_written_in_any_source_is_rejected(ctx, check, number):
    assert any(f"number {number} in 'check' isn't written" in p for p in validate(rulebook(check=check), ctx))


def test_numbers_can_come_from_number_words_and_row_labels():
    from rule_format.rulebook import source_numbers
    assert {3.0, 4.0, 5.0} <= source_numbers("First three bed or sleeping rooms; 4-5 bed rooms")
    assert source_numbers("50 ft [fn16]") == {50.0}                           # no footnote number, no 0.5
    assert source_numbers("6,000 sf 25% and 10 percent") == {6000.0, 25.0, 0.25, 10.0, 0.1}  # only percents / 100
    assert source_numbers("two-family dwelling") == set()                     # "two" in a compound isn't a count
    assert source_numbers("(10) See §325-16.") == set()                       # a note's marker and a section number
    assert 3.0 not in source_numbers("(3) In each district, the number of additional feet may not exceed 10% of the height")
    assert source_numbers("as specified in this column and Column 12 [Amended 10-1-2014 by Ord. No. 2014-12]") == set()
    # references as Chapter 325 writes them (strings from its extracted text)
    for ref in ("the requirements of § 325-20D(1) are met.", "See § 325-20D(3)(b).", "except as provided in Subsection B(7)",
                "pursuant to Section 325-16 of this chapter", "in accordance with §§ 325-8 and 325-9",
                "§ 81-a of the General City Law", "Article 78 of the Civil Practice", "Note: Former Subsection B(9)"):
        assert source_numbers(ref) == set(), ref
    assert source_numbers("50% of the lot", percent_as_number=False) == {0.5}   # a typed percent is its fraction


def test_no_number_is_left_in_any_reference_in_the_citys_text():
    """Every '§ ...', 'Section ...', 'Subsection ...' in Chapter 325, up to the next plain word: no number survives."""
    import json, re
    from rule_format.rulebook import REPO, source_numbers
    path = REPO / "regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/chapter_325_zoning_2026-10.jsonl"
    left = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        text = json.loads(line).get("text", "")
        for m in re.finditer(r"(?i)(?:§+|\bsub(?:section|paragraph)s?\b|\bsections?\b)\s*[\w.\-()§, ]*?(?=\s+[a-z]{3,}\b|$)", text):
            ref = re.split(r"(?i)\s+(?:zoning|ithaca)\b", m.group(0))[0]           # page headers: "§ 325-16 ZONING § 325-16"
            if source_numbers(ref) and not re.search(r"(?i)\((?:january|february|march|april|may|june|july|august|september|october|november|december) ", ref):
                left.add(ref)
    assert sorted(left) == []


def test_a_cell_from_another_districts_column_is_rejected(chart_ctx):
    other = {"page": 3, "section": "Yard Dimensions", "row": REAR_CELL["row"], "column": "R-2A",
             "value": "25%/ 50 ft [fn16]", "row_lines": [42, 43]}
    chart_ctx.cells["charts.pdf"][(3, "Yard Dimensions", REAR_CELL["row"], "R-2A")] = other
    foreign = CELL_SOURCE | {"cell": CELL_SOURCE["cell"] | {"column": "R-2A"}}
    assert any("cell column R-2A isn't district R-1b" in p for p in validate(rulebook(sources=[foreign, *NOTES]), chart_ctx))
    general = {"district": "general", "rules": [copy.deepcopy(RULE) | {"id": "general.rear_yard", "sources": [CELL_SOURCE, *NOTES]}]}
    assert any("can't cite one district's cell" in p for p in validate(general, chart_ctx))


def test_a_shared_columns_cell_is_each_of_its_districts_own_and_no_other(chart_ctx):
    """One chart column can hold several districts (Ithaca's "Central Business" column, CBD-50 ... CBD-140:
    jurisdiction.yaml districts.shared_columns): each of them may cite its cells; a district it doesn't hold may not."""
    shared = REAR_CELL | {"column": "Central Business"}
    chart_ctx.cells["charts.pdf"][(3, "Yard Dimensions", REAR_CELL["row"], "Central Business")] = shared
    chart_ctx.shared_columns = {"Central Business": ["R-1b", "R-2a"]}
    cbd = CELL_SOURCE | {"cell": CELL_SOURCE["cell"] | {"column": "Central Business"}}
    assert validate(rulebook(sources=[cbd, *NOTES]), chart_ctx) == []
    chart_ctx.shared_columns = {"Central Business": ["R-2a"]}
    assert any("cell column Central Business isn't district R-1b" in p
               for p in validate(rulebook(sources=[cbd, *NOTES]), chart_ctx))


def test_ithacas_cbd_rulebooks_cite_the_one_central_business_column():
    from rule_format.place import place
    from rule_format.rulebook import REPO, column_districts
    j = REPO / "regulations/jurisdictions/new_york/ithaca_city"
    shared = place(j).shared_columns
    assert column_districts("Central Business", shared) == ["CBD-50", "CBD-60", "CBD-85", "CBD-100", "CBD-120", "CBD-140"]
    assert column_districts("B-2A", shared) == ["B-2a"]


def test_a_yes_no_measure_can_be_a_test_on_its_own(ctx):
    ctx.proposed = {"adu_separate_entrance": {"unit": "yes_no", "meaning": "ADU has a separate entrance"}}
    rule = {"id": "R-1b.adu_entrance", "kind": "rule", "topic": "dimensions", "title": "ADU entrance",
            "check": "adu_separate_entrance", "sources": [SOURCE],
            "examples": [{"given": {"adu_separate_entrance": True}, "expect": "pass"},
                         {"given": {"adu_separate_entrance": False}, "expect": "fail"}],
            "drafted_by": "claude", "status": "draft"}
    assert validate({"district": "R-1b", "rules": [rule]}, ctx) == []
    assert any("wrong kind of value" in p for p in validate({"district": "R-1b", "rules": [
        rule | {"examples": [{"given": {"adu_separate_entrance": 1}, "expect": "pass"}]}]}, ctx))
    assert any("only a yes/no measure" in p for p in validate(rulebook(check="rear_yard"), ctx))   # a number isn't a test
    approved = rule | {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 20)}
    approved["approved_hash"] = approval_hash(approved, ctx)
    assert any("proposed measure 'adu_separate_entrance'" in p
               for p in validate({"district": "R-1b", "rules": [approved]}, ctx))


def test_a_proposed_measure_is_unknown_until_listed(ctx):
    rule = rulebook(check="rear_yard >= 20 and adu_separate_entrance")
    assert any("unknown measure 'adu_separate_entrance'" in p for p in validate(rule, ctx))


def test_district_names_are_known_text_values(chart_ctx):
    scoped = rulebook(applies_when='district == "R-1b"', sources=[CELL_SOURCE, *NOTES],
                      examples=[{"given": {"district": "R-1b", "rear_yard": 25, "lot_depth": 90}, "expect": "pass"},
                                {"given": {"district": "R-1b", "rear_yard": 21, "lot_depth": 90}, "expect": "fail"},
                                {"given": {"district": "R-2a", "rear_yard": 0, "lot_depth": 90}, "expect": "not_applicable"}])
    assert validate(scoped, chart_ctx) == []
    assert any("unknown district 'R-9z'" in p for p in validate(rulebook(
        examples=RULE["examples"] + [{"given": {"district": "R-9z"}, "expect": "needs_review"}]), chart_ctx))


def test_district_names_are_written_as_the_city_writes_them():
    from rule_format.rulebook import district_name
    assert [district_name(c) for c in ("R-1B", "R-3AA", "RU", "R-2C")] == ["R-1b", "R-3aa", "RU", "R-2c"]


@pytest.mark.parametrize("applies_when, problem", [
    ('district == "R-1b" or use == "R-2a"', "unknown use 'R-2a'"),      # a district where a use belongs: dead
    ('district == "one_family_detached"', "unknown district 'one_family_detached'"),
    ('use in ["one_family_detached", "R-1b"]', "unknown use 'R-1b'"),
    ('lot_area > 0 and "R-1b" == "R-1b"', "must be compared with district or use"),
])
def test_a_quoted_value_must_fit_the_measure_it_is_compared_with(chart_ctx, applies_when, problem):
    assert any(problem in p for p in validate(rulebook(sources=[CELL_SOURCE, *NOTES], applies_when=applies_when),
                                              chart_ctx)), applies_when


def test_quoted_values_that_fit_their_measure_pass(chart_ctx):
    good = 'district == "R-1b" and use in ["one_family_detached"]'
    assert not any("unknown" in p or "compared with" in p
                   for p in validate(rulebook(sources=[CELL_SOURCE, *NOTES], applies_when=good), chart_ctx))


def test_one_definition_of_a_district_column():
    """The chart reader, the inspector and the drafter decide 'is this column a district' the same way, so an
    extra all-caps heading (NOTES, SP) can't become a district in one place and not another: each from the place's
    own settings (its jurisdiction.yaml, through the registry), with no copy of the pattern in their code."""
    from pathlib import Path
    from rule_format.place import place
    column = place("new_york/ithaca_city").district_column
    names = ["R-1A", "R-1B", "R-3AA", "RU", "NOTES", "SP", "ADU", "Additional Regulations"]
    assert [n for n in names if column.fullmatch(n)] == ["R-1A", "R-1B", "R-3AA", "RU"]
    packages = Path(__file__).resolve().parents[2]
    for code in ("document_extraction/document_extraction/charts.py", "rule_format/rule_format/rulebook.py",
                 "rule_drafting/rule_drafting/chart_values.py", "rule_drafting/rule_drafting/__main__.py"):
        text = (packages / code).read_text(encoding="utf-8")
        assert "R-\\d" not in text and "DISTRICT_COLUMN =" not in text, code


# ---- every number a cited footnote or law quote states is used, or declared not a limit ----------------------

def test_a_number_a_cited_note_states_but_the_formula_drops_is_rejected(ctx):
    """eval-integrity P1-1: dropping note 16's 20 ft floor from the formula left every check passing."""
    dropped = rulebook(check="rear_yard >= min(0.25 * lot_depth, 50)")
    assert any('number 20 in the quote "(16) But not less than 20 ft.' in p for p in validate(dropped, ctx))
    assert not any("is never used" in p for p in validate(rulebook(), ctx))          # the real rule uses it


def test_a_number_that_isnt_a_limit_is_declared_with_why(ctx):
    sources = [SOURCE, NOTES[0] | {"not_limits": {20: "for this test"}}, NOTES[1]]
    assert not any("is never used" in p for p in validate(rulebook(check="rear_yard >= min(0.25 * lot_depth, 50)",
                                                                   sources=sources), ctx))
    stale = [SOURCE, NOTES[0] | {"not_limits": {30: "not in the quote"}}, NOTES[1]]
    assert any("not_limits names 30, which its quote doesn't state" in p for p in validate(rulebook(sources=stale), ctx))
    for bad in ({20: ""}, [20], {"20": "a text key"}):
        broken = [SOURCE, NOTES[0] | {"not_limits": bad}, NOTES[1]]
        assert any("not_limits must map each number" in p for p in validate(rulebook(sources=broken), ctx)), bad


def test_a_chart_row_listing_every_district_is_not_held_to_it(chart_ctx):
    """A chart row's quote lists every district's numbers; the rule uses its own column's."""
    problems = validate(rulebook(check="rear_yard >= max(0.25 * lot_depth, 20)", sources=[SOURCE, *NOTES]), chart_ctx)
    assert not any("number 50 in the quote" in p for p in problems)


def test_a_flag_isnt_held_to_the_numbers_in_its_quote(ctx):
    """A flag always needs review: the limits its quote states are for the person to apply, so they need no
    not_limits (R-3a's abutting and loading flags); a rule quoting the same note is still held to them."""
    flag = rulebook(kind="flag", check=None, review_when=None, examples=None)
    assert not any("is never used" in p for p in validate(flag, ctx))
    assert any("number 20 in the quote" in p for p in validate(rulebook(check="rear_yard >= min(0.25 * lot_depth, 50)"), ctx))


def test_a_rule_whose_formula_is_wrong_for_every_value_is_refused(ctx):
    """Compile, then freeze: an ill-typed formula is a validation problem, so no frozen rule can be ill-typed."""
    assert any("compare two numbers or two texts" in p
               for p in validate(rulebook(check='rear_yard >= 20 or use == 5'), ctx))
    assert any("compare two numbers or two texts" in p
               for p in validate(rulebook(check='(rear_yard >= 20) == (lot_depth > 1)'), ctx))
    assert not any("kind" in p for p in validate(rulebook(), ctx))


def test_an_unreadable_formula_needs_review_never_a_crash():
    """Review round 3 of 0582c65: rulebook.outcome on a formula that can't be read (too long, not the language)
    is needs review, not an exception."""
    from rule_format.rulebook import outcome
    for check in ("rear_yard >= " + " + ".join(["1"] * 300), "rear_yard >= 20 if"):
        assert outcome({"kind": "rule", "check": check}, {"rear_yard": 30}, {}) == "needs_review"
