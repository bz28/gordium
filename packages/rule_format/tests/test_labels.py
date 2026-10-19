"""Section labels are checked like rules: real quotes inside their piece, known labels, approvals."""

import copy
import datetime
from pathlib import Path

import pytest

from rule_format.labels import load_pieces, piece_fingerprint, validate_labels
from rule_format.rulebook import Context, approval_hash
from rule_format.labels import LABEL_APPROVED

REPO = Path(__file__).resolve().parents[3]
ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
LAW = "chapter_325_zoning_2026-10.pdf"
QUOTE = "In any district, any main building may be erected to a height in excess of that"


@pytest.fixture(scope="module")
def base():
    ctx = Context.for_jurisdiction(ITHACA)
    ctx.reviewers = {"jane"}
    header, pieces = load_pieces(ITHACA / "2_extracted_text/chapter_325_zoning_2026-10.sections.jsonl")
    return ctx, header, pieces


def entry(base, **changes):
    _, header, pieces = base
    e = {"label": "rule", "topic": "dimensions", "reason": "Lets a building exceed the height limit on conditions.",
         "sources": [{"file": LAW, "page": 47, "lines": [6, 6], "quote": QUOTE}],
         "piece_sha256": piece_fingerprint(pieces["325-16C"], header["sha256"]),
         "drafted_by": "section_labeling/claude-haiku-5-5", "status": "draft"}
    return {k: v for k, v in (e | changes).items() if v is not None}


def check(base, labels):
    ctx, header, pieces = base
    return validate_labels({"document": LAW, "labels": labels}, ctx, header, pieces)


def test_a_valid_label(base):
    assert check(base, {"325-16C": entry(base)}) == []


@pytest.mark.parametrize("changes, problem", [
    ({"label": "maybe"}, "label must be one of"),
    ({"topic": "vibes"}, "unknown topic"),
    ({"reason": " "}, "missing 'reason'"),
    ({"colour": "red"}, "unknown field 'colour'"),
    ({"piece_sha256": "0" * 64}, "the piece changed since it was labeled"),
    ({"sources": [{"file": LAW, "page": 47, "lines": [3, 3],
                   "quote": "B. Ornamental and architectural features. The provisions of this chapter shall not apply to prevent the"}]},
     "outside this piece"),                               # real words, but from §325-16B
    ({"sources": [{"file": LAW, "page": 47, "lines": [6, 6], "quote": "any building may be erected"}]}, "not on this page"),
    ({"sources": []}, "needs at least one source"),
    ({"sources": [{"file": "zoning_charts_2026-04.pdf", "page": 47, "lines": [6, 6], "quote": "x"}]},
     "quote must come from chapter_325_zoning_2026-10.pdf"),                 # another PDF, even on the piece's lines
    ({"drafted_by": None}, "missing 'drafted_by'"),
    ({"status": "approved", "approved_by": "claude", "approved_on": datetime.date(2026, 10, 20)}, "approved_by must be a reviewer"),
])
def test_bad_labels_are_rejected(base, changes, problem):
    assert any(problem in p for p in check(base, {"325-16C": entry(base, **changes)}))


def test_a_reviewers_question_blocks_approval_until_an_architect_answers(base):
    ctx, _, _ = base
    approved = {"status": "approved", "approved_by": "jane", "approved_on": datetime.date(2026, 10, 20)}
    doubted = entry(base, open_questions=["Is this really a rule? It reads like procedure."], **approved)
    assert any("open_questions remain" in p for p in check(base, {"325-16C": doubted}))
    answer = {"question": "Is this really a rule?", "answer": "Yes: it changes the height limit.",
              "answered_by": "jane", "answered_on": datetime.date(2026, 10, 20)}
    answered = entry(base, answers=[answer], **approved)
    answered["approved_hash"] = approval_hash(answered | {"id": "325-16C"}, ctx, LABEL_APPROVED)
    assert check(base, {"325-16C": answered}) == []
    reworded = answered | {"answers": [answer | {"answer": "No."}]}             # an answer is frozen too
    assert any("changed since it was approved" in p for p in check(base, {"325-16C": reworded}))


def test_a_label_for_a_piece_that_does_not_exist(base):
    assert check(base, {"325-99Z": entry(base)}) == ["325-99Z: no such piece in the sections file"]


def test_approved_label_needs_reapproval_after_an_edit(base):
    ctx, _, _ = base
    e = entry(base, status="approved", approved_by="jane", approved_on=datetime.date(2026, 10, 20))
    e["approved_hash"] = approval_hash(e | {"id": "325-16C"}, ctx, LABEL_APPROVED)
    assert check(base, {"325-16C": e}) == []
    for edit in ({"label": "flag"}, {"topic": "procedures"}, {"reason": "Something else."}):
        assert any("changed since it was approved" in p for p in check(base, {"325-16C": e | edit}))
    assert any("changed since it was approved" in p for p in check(base, {"325-16B": e}))   # moved to another piece


def test_the_file_must_name_its_document_and_match_the_pdf_version(base):
    ctx, header, pieces = base
    assert "doesn't match the sections file" in validate_labels({"document": "x.pdf", "labels": {}}, ctx, header, pieces)[0]
    old = copy.deepcopy(header) | {"sha256": "0" * 64}
    assert "different version" in validate_labels({"document": LAW, "labels": {}}, ctx, old, pieces)[0]
    assert "exactly 'document' and 'labels'" in validate_labels({"labels": {}}, ctx, header, pieces)[0]


REV = {"from": "reference", "by": "Claude (review)", "date": datetime.date(2026, 10, 19), "why": "sets a limit"}


@pytest.mark.parametrize("revised, problem", [
    ("from reference", "'revised' must be a list"),
    ([REV | {"extra": 1}], "each revision needs exactly from, by, date, why"),
    ([{k: v for k, v in REV.items() if k != "date"}], "each revision needs exactly"),
    ([REV | {"from": "maybe"}], "not a label"),
    ([REV | {"why": " "}], "by and why must be text"),
    ([REV | {"date": "2026-10-19x"}], "must be a date"),
    ([REV | {"from": "rule"}], "a revision must change it"),                 # rule -> rule changes nothing
    ([REV, REV], "revision 1 is from 'reference' to the same label"),       # an earlier no-op in the chain
])
def test_bad_revisions_are_rejected(base, revised, problem):
    assert any(problem in p for p in check(base, {"325-16C": entry(base, revised=revised)}))


def test_a_revision_is_recorded_and_frozen_at_approval(base):
    ctx, _, _ = base
    assert check(base, {"325-16C": entry(base, revised=[REV])}) == []
    there_and_back = [REV | {"from": "rule"}, REV]                             # rule -> reference -> rule is fine
    assert check(base, {"325-16C": entry(base, revised=there_and_back)}) == []
    approved = entry(base, revised=[REV], status="approved", approved_by="jane", approved_on=datetime.date(2026, 10, 20))
    approved["approved_hash"] = approval_hash(approved | {"id": "325-16C"}, ctx, LABEL_APPROVED)
    assert check(base, {"325-16C": approved}) == []
    assert any("changed since it was approved" in p
               for p in check(base, {"325-16C": approved | {"revised": [REV | {"why": "other"}]}}))
