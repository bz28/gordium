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


def test_the_model_codes_requirement_verbs_put_a_reference_on_the_review_list():
    # review round 5: ICC books require with "shall comply", "shall be provided", "shall meet" (R319.7, R318.7.10)
    piece = {"id": "R319.7", "title": "Alterations", "lines": [[1, 1, 3]]}
    for text, word in (("Alterations of existing basements shall comply with Appendix BO.", "shall comply"),
                       ("Stairways shall be provided with illumination.", "shall be provided"),
                       ("Stair treads and risers shall meet the requirements of this section.", "shall meet"),
                       ("Doors shall be permitted to swing over stairs.", "shall be permitted")):
        rows = [{"file": "b.pdf"}, {"page": 1, "line": 1, "text": text}]
        assert coverage.requirement_words(rows, piece) == [word]


def test_a_rule_named_by_its_book_counts_for_its_section_and_the_tables_it_quotes():
    """Maine's state folder holds two books, so its rules are named by book first (general.ibc_1016_1_...): the book
    word is no part of a piece number. A rule written for a section is written for each table piece it quotes too
    (Table 1016.1 holds 1016.1's numbers), never for any other piece it quotes, nor for a table it doesn't."""
    pieces = {"1016.1": {"id": "1016.1", "title": "Travel distance limitations", "lines": [[1, 1, 5]]},
              "Table 1016.1": {"id": "Table 1016.1", "title": "TABLE 1016.1", "kind": "table", "lines": [[1, 6, 9]]},
              "1014.3": {"id": "1014.3", "title": "Common path", "lines": [[1, 10, 12]]},
              "Table 1015.1": {"id": "Table 1015.1", "title": "TABLE 1015.1", "kind": "table", "lines": [[1, 13, 14]]}}
    labels = {pid: {"label": "rule"} for pid in pieces}
    src = lambda a, b: {"file": "b.pdf", "page": 1, "lines": [a, b]}
    rules = [{"id": "general.ibc_1016_1_travel", "sources": [src(1, 2), src(7, 7), src(10, 10)]},
             {"id": "general.nfpa_1014_3_common_path", "sources": [src(6, 6)]}]       # names 1014.3, quotes only a table
    got = coverage.rules_for_pieces("b.pdf", pieces, labels, rules)
    assert got == {"1016.1": ["general.ibc_1016_1_travel"], "Table 1016.1": ["general.ibc_1016_1_travel"],
                   "1014.3": [], "Table 1015.1": []}
    # New York's names (r318_...) carry no book word and are read as before
    assert coverage.rules_for_pieces("b.pdf", {"R318.2": {"id": "R318.2", "title": "x", "lines": [[1, 1, 1]]}},
                                     {"R318.2": {"label": "rule"}}, [{"id": "general.r318_2_door",
                                                                     "sources": [src(1, 1)]}]) == \
        {"R318.2": ["general.r318_2_door"]}
