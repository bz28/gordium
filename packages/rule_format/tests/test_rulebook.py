import copy
import datetime
import json
import math

import pytest
import yaml

from rule_format.rulebook import Context, _canonical, approval_hash, load, outcome, quote_found, tokenize, validate

PAGE_3 = "Rear (minimum, % of depth or feet, whichever is less)  25%/ 50 ft 16"
QUOTE = "Rear (minimum, % of depth … whichever is less)  25%/ 50 ft"
RULE = {
    "id": "R-1b.rear_yard",
    "kind": "rule",
    "topic": "dimensions",
    "says": "Rear yard at least 25% of lot depth or 50 ft, whichever is less, never under 20 ft.",
    "applies_when": 'use == "one_family_detached"',
    "check": "rear_yard >= max(min(0.25 * lot_depth, 50), 20)",
    "review_when": [{"when": "lot_depth > 500", "reason": "unusually deep lot"}],
    "sources": [{"file": "charts.pdf", "page": 3, "quote": QUOTE}],
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
    pages={"charts.pdf": {3: tokenize(PAGE_3)}},
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
    ({"says": None}, "missing 'says'"),
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
    ({"sources": [{"file": "other.pdf", "page": 3, "quote": QUOTE}]}, "not in sources.yaml"),
    ({"sources": [{"file": "charts.pdf", "page": "3", "quote": QUOTE}]}, "needs 'page' (number)"),
    ({"sources": [{"file": "charts.pdf", "page": 9, "quote": QUOTE}]}, "page 9 does not exist"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "Rear (minimum, % of depth … 30%/ 50 ft 16 xxxxxx"}]},
     "quote not found"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "…"}]}, "needs 15+ characters"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "50 ft"}]}, "needs 15+ characters"),
    ({"sources": [{"file": "charts.pdf", "page": 3,                       # stitched from single letters
                   "quote": "r … e … a … r … m … i … n … i … m … u … m … 5 … 0 … f … t"}]}, "needs 15+ characters"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": " … ".join(["Rear (minimum, % of"] * 4)}]},
     "at most 2 '…' gaps"),
    ({"sources": [{"file": ["charts.pdf"], "page": 3, "quote": QUOTE}]}, "not in sources.yaml"),
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
])
def test_invalid_rules_are_rejected(ctx, changes, problem):
    problems = validate(rulebook(**changes), ctx)
    assert any(problem in p for p in problems), problems


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
    path.write_text("district: R-1b\nrules:\n  - check: a > 1\n    check: a > 2\n")
    with pytest.raises(yaml.YAMLError, match="duplicate key 'check'"):
        load(path)


def test_quote_parts_must_appear_in_order():
    page = tokenize("one two three four")
    assert quote_found("one … three", page)
    assert quote_found("ONE  TWO", page)
    assert not quote_found("three … one", page)
    assert not quote_found("…", page)


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


def test_earlier_look_alike_does_not_hide_the_real_quote():
    page = tokenize("Rear yard minimum " + "x " * 100 + " Rear yard minimum twenty feet always")
    assert quote_found("Rear yard minimum … twenty feet always", page)


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


def test_quote_pieces_must_be_near_each_other():
    near = tokenize("Rear yard minimum " + "x " * 50 + " twenty feet always")    # 50 words apart
    far = tokenize("Rear yard minimum " + "x " * 70 + " twenty feet always")     # 70 words apart
    assert quote_found("Rear yard minimum … twenty feet always", near)
    assert not quote_found("Rear yard minimum … twenty feet always", far)


def _jurisdiction(tmp_path, pdf_bytes=b"%PDF fake", header_sha=None, rows=()):
    j = tmp_path / "ny" / "town"
    (j / "1_source_documents").mkdir(parents=True)
    (j / "2_extracted_text").mkdir()
    (j / "1_source_documents/doc.pdf").write_bytes(pdf_bytes)
    import hashlib
    sha = hashlib.sha256(b"%PDF fake").hexdigest()
    (j / "1_source_documents/sources.yaml").write_text(f"documents:\n  - file: doc.pdf\n    sha256: {sha}\n")
    lines = [json.dumps({"file": "doc.pdf", "sha256": header_sha or sha}), "", *map(json.dumps, rows)]
    (j / "2_extracted_text/doc.jsonl").write_text("\n".join(lines) + "\n")
    return j


def test_context_loads_extracted_text(tmp_path):
    ctx = Context.for_jurisdiction(_jurisdiction(tmp_path, rows=[{"page": "2", "text": "Hello  World"}]))
    assert ctx.problems == []
    assert ctx.pages["doc.pdf"] == {2: ["hello", "world"]}


def test_context_reports_changed_pdf_and_stale_text(tmp_path):
    ctx = Context.for_jurisdiction(_jurisdiction(tmp_path, pdf_bytes=b"changed", header_sha="old"))
    assert any("fingerprint does not match" in p for p in ctx.problems)
    assert any("different version" in p for p in ctx.problems)
    assert "doc.pdf" not in ctx.pages


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
    (j / "5_zoning_rules/R-1a.yaml").write_text("district: R-1b\nrules: []\n")
    monkeypatch.setattr(cli, "REPO", tmp_path)
    assert cli.main() == 1
    assert "doesn't match the file name 'R-1a'" in capsys.readouterr().out


def test_cli_keeps_going_when_validation_itself_fails(tmp_path, monkeypatch, capsys):
    import rule_format.__main__ as cli
    j = _jurisdiction(tmp_path / "regulations/jurisdictions", rows=[])
    (j / "5_zoning_rules").mkdir()
    for name in ("R-1a", "R-1b"):
        (j / f"5_zoning_rules/{name}.yaml").write_text(f"district: {name}\nrules: []\n")
    def broken(book, ctx):
        raise TypeError("boom")
    monkeypatch.setattr(cli, "validate", broken)
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
    question = {"open_questions": ["Is the yard measured to the wall or the eave?"]}
    assert validate(rulebook(**question), ctx) == []                    # fine as a draft
    approved = APPROVED | question                                          # adding a question blocks approval
    assert any("open_questions remain" in p for p in validate(rulebook(**approved), ctx))
    assert any("'open_questions' must be a list" in p for p in validate(rulebook(open_questions="why?"), ctx))


def test_decimal_point_needs_a_clean_start():
    assert not quote_found(".5 feet of depth here", tokenize("Section A.5 feet of depth here"))
    assert quote_found("5 feet of depth here", tokenize("Section A.5 feet of depth here"))
