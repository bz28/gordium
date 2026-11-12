"""The coverage of a book only partly brought in (New York's Residential Code, kept outside the repo): every line of
the pages read is a piece, furniture, or a named part not brought in; and without the book (CI) the report is still
checked, from the sections file's line counts."""

from section_labeling import coverage
from section_labeling.__main__ import extracted_rows, read_labels
from rule_format.labels import load_pieces
from rule_format.rulebook import CODE_CACHE_ENV, REPO

NY = REPO / "regulations/jurisdictions/new_york/new_york_state"
BOOK = "gov.ny.residential.2025.pdf"
CUT = NY / "2_extracted_text/gov.ny.residential.2025.sections.jsonl"


def _rows(pages):
    return [{"file": "b.pdf"}, *({"page": p, "line": n, "text": ""} for p, count in pages.items()
                                for n in range(1, count + 1))]


def test_a_line_of_a_part_not_brought_in_is_accounted_for_only_when_named():
    header = {"file": "b.pdf", "furniture": [[1, 1]], "problems": [], "line_counts": {"1": 4},
              "outside": [[1, 4, 4, "R317"]]}
    pieces = {"R318": {"id": "R318", "title": "MEANS OF EGRESS", "lines": [[1, 2, 3]]}}
    assert coverage.line_problems(_rows({1: 4}), header, pieces) == []
    header["outside"] = []
    assert coverage.line_problems(_rows({1: 4}), header, pieces) == ["p.1 line 4: in no piece"]


def test_without_the_book_the_report_is_rebuilt_from_line_counts_and_matches_the_committed_one(monkeypatch, tmp_path):
    monkeypatch.setenv(CODE_CACHE_ENV, str(tmp_path / "no_cache"))
    rows = extracted_rows(NY, BOOK)
    assert rows[0].get("no_text") is True and all(r["text"] == "" for r in rows[1:])
    header, pieces = load_pieces(CUT)
    assert len(rows) - 1 == sum(header["line_counts"].values())
    report = coverage.report(rows, header, pieces, read_labels(NY, BOOK))
    assert "problems cutting the book:** 0 ✓" in report and "unlabeled 0" in report
    assert report == (NY / "6_coverage_report/gov.ny.residential.2025.md").read_text(encoding="utf-8")
