import copy

import pytest

from rule_format.rulebook import Context, normalize, outcome, quote_found, validate

RULE = {
    "id": "R-1b.rear_yard",
    "kind": "rule",
    "topic": "dimensions",
    "says": "Rear yard at least 25% of lot depth or 50 ft, whichever is less, never under 20 ft.",
    "applies_when": 'use == "one_family_detached"',
    "check": "rear_yard >= max(min(0.25 * lot_depth, 50), 20)",
    "review_when": [{"when": "lot_depth > 500", "reason": "unusually deep lot"}],
    "sources": [{"file": "charts.pdf", "page": 3, "quote": "Rear (minimum … 25%/ 50 ft"}],
    "examples": [
        {"given": {"use": "one_family_detached", "rear_yard": 25, "lot_depth": 90}, "expect": "pass"},
        {"given": {"use": "one_family_detached", "rear_yard": 21, "lot_depth": 90}, "expect": "fail"},
    ],
    "drafted_by": "claude",
    "status": "draft",
}


@pytest.fixture
def ctx():
    return Context(
        measures={"use", "rear_yard", "lot_depth"},
        uses={"one_family_detached"},
        topics={"dimensions"},
        sources={"charts.pdf": {"file": "charts.pdf"}},
        pages={"charts.pdf": {3: normalize("Rear (minimum, % of depth)  25%/ 50 ft 16")}},
    )


def rulebook(**changes):
    rule = copy.deepcopy(RULE) | changes
    return {"district": "R-1b", "rules": [{k: v for k, v in rule.items() if v is not None}]}


@pytest.mark.parametrize("values, expected", [
    ({"use": "church", "rear_yard": 0, "lot_depth": 90}, "not_applicable"),
    ({"use": "one_family_detached", "rear_yard": 30, "lot_depth": 90}, "pass"),
    ({"use": "one_family_detached", "rear_yard": 10, "lot_depth": 90}, "fail"),
    ({"use": "one_family_detached", "rear_yard": 30, "lot_depth": 600}, "needs_review"),
    ({"use": "one_family_detached", "lot_depth": 90}, "needs_review"),        # missing measurement
    ({"rear_yard": 30, "lot_depth": 90}, "needs_review"),                     # use unknown
])
def test_outcome(values, expected):
    assert outcome(RULE, values) == expected


def test_flag_always_needs_review():
    flag = {k: v for k, v in RULE.items() if k != "check"} | {"kind": "flag"}
    assert outcome(flag, {"use": "one_family_detached", "rear_yard": 99, "lot_depth": 90}) == "needs_review"


def test_valid_rulebook(ctx):
    assert validate(rulebook(), ctx) == []


@pytest.mark.parametrize("changes, problem", [
    ({"id": "R-2a.rear_yard"}, "id must start with 'R-1b.'"),
    ({"kind": "maybe"}, "kind must be one of"),
    ({"topic": "vibes"}, "unknown topic"),
    ({"says": None}, "missing 'says'"),
    ({"check": None}, "a 'rule' needs a 'check'"),
    ({"check": "rear_yard >= setback"}, "unknown measure 'setback'"),
    ({"applies_when": 'use == "castle"'}, "unknown use 'castle'"),
    ({"check": "import os"}, "cannot read formula"),
    ({"review_when": [{"when": "lot_depth > 1"}]}, "needs a 'reason'"),
    ({"sources": []}, "needs at least one source"),
    ({"sources": [{"file": "other.pdf", "page": 3, "quote": "x"}]}, "not in sources.yaml"),
    ({"sources": [{"file": "charts.pdf", "page": 9, "quote": "Rear"}]}, "page 9 does not exist"),
    ({"sources": [{"file": "charts.pdf", "page": 3, "quote": "Rear 30%"}]}, "quote not found"),
    ({"examples": []}, "needs at least one worked example"),
    ({"examples": [{"given": {"use": "one_family_detached", "rear_yard": 25, "lot_depth": 90},
                    "expect": "fail"}]}, "expected fail, got pass"),
    ({"status": "approved"}, "need 'approved_by' and 'approved_on'"),
    ({"drafted_by": None}, "missing 'drafted_by'"),
    ({"colour": "red"}, "unknown field 'colour'"),
])
def test_invalid_rules_are_rejected(ctx, changes, problem):
    problems = validate(rulebook(**changes), ctx)
    assert any(problem in p for p in problems), problems


def test_duplicate_ids_are_rejected(ctx):
    book = rulebook()
    book["rules"] *= 2
    assert any("duplicate id" in p for p in validate(book, ctx))


def test_quote_parts_must_appear_in_order():
    page = normalize("one two three four")
    assert quote_found("one … three", page)
    assert quote_found("ONE  TWO", page)
    assert not quote_found("three … one", page)
