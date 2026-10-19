import copy
import datetime
import json
import math

import pytest
import yaml

from rule_format.rulebook import Context, load, normalize, outcome, quote_found, validate

PAGE_3 = "Rear (minimum, % of depth or feet, whichever is less)  25%/ 50 ft 16"
QUOTE = "Rear (minimum, % of depth … 25%/ 50 ft"
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
APPROVED = {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 19)}


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
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "Rear (minimum, 30%/ 50 ft"}]}, "quote not found"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "…"}]}, "quote too short"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "50 ft"}]}, "quote too short"),
    ({"examples": []}, "needs at least one worked example"),
    ({"examples": [{"given": {"use": "one_family_detached", "rear_yard": 25, "lot_depth": 90},
                    "expect": "fail"}]}, "expected fail, got pass"),
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
