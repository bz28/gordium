import copy
import datetime
import json
import math

import pytest
import yaml

from rule_format.rulebook import Context, approval_hash, load, normalize, outcome, quote_found, validate

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
APPROVED = {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 19),
            "approved_hash": approval_hash(RULE)}


@pytest.fixture
def ctx():
    return Context(
        measures={"use", "rear_yard", "lot_depth"},
        uses={"one_family_detached"},
        topics={"dimensions"},
        sources={"charts.pdf": {"file": "charts.pdf"}},
        reviewers={"jane"},
        pages={"charts.pdf": {3: normalize(PAGE_3)}},
    )


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
    assert outcome(RULE, values) == expected


@pytest.mark.parametrize("check, values", [
    ("stories != 4", {"stories": "4"}),                       # text where a number belongs
    ('use not in ["church"]', {"use": 5}),                     # number where text belongs
    ("not (rear_yard < 0 < use)", {"rear_yard": 5, "use": "x"}),  # bad link after a false one
    ("not (rear_yard < 1e300 * 1e300 - 1e300 * 1e300)", {"rear_yard": 5}),  # arithmetic gives NaN
    ("not (lot_area * 1e308 == 1)", {"lot_area": 5}),         # arithmetic overflows to infinity
    ("stories == use", {"stories": "3", "use": "3"}),          # stories must be a number (measures.yaml)
])
def test_bad_values_never_pass(check, values):
    assert outcome({"kind": "rule", "check": check}, values) == "needs_review"


def test_non_boolean_check_never_passes():
    rule = RULE | {"check": "rear_yard - 20"}  # gives a number, not true/false
    assert outcome(rule, {"use": "one_family_detached", "rear_yard": 10, "lot_depth": 90}) == "needs_review"


def test_flag_always_needs_review():
    flag = {k: v for k, v in RULE.items() if k != "check"} | {"kind": "flag"}
    assert outcome(flag, {"use": "one_family_detached", "rear_yard": 99, "lot_depth": 90}) == "needs_review"


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
    page = normalize("one two three four")
    assert quote_found("one … three", page)
    assert quote_found("ONE  TWO", page)
    assert not quote_found("three … one", page)
    assert not quote_found("…", page)


def test_quote_number_must_not_match_inside_a_bigger_number():
    page = normalize("Rear yard minimum 25 feet in depth for all lots; side yard 5 feet in depth for all lots")
    assert quote_found("5 feet in depth for all lots", page)          # the real '5 feet', later on the page
    assert not quote_found("5 feet in depth for all lots", normalize("Rear yard 25 feet in depth for all lots"))
    assert not quote_found("yard 2", normalize("yard 25"))


def test_quote_pieces_must_be_near_each_other():
    near = normalize("Rear yard minimum " + "x" * 100 + " twenty feet always")
    far = normalize("Rear yard minimum " + "x" * 400 + " twenty feet always")
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
    assert ctx.pages["doc.pdf"] == {2: "helloworld"}


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
