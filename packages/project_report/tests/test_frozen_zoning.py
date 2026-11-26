"""A check reads each zoning rulebook's checks frozen (rule_format/published.py: compile, then freeze), never running
them again per check: the frozen answer equals a live compile_zoning for every district, a missing or stale
certificate gives no report (so no row of that district passes), and the rows come from the very bytes checked.
"""

from pathlib import Path

import pytest

from rule_format import published
from rule_format.rulebook import REPO, load, rulebook_for

from project_report import report

ITHACA = REPO / "regulations/jurisdictions/new_york/ithaca_city"
SITE = REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design.yaml"


def test_the_frozen_zoning_checks_equal_a_live_compile_for_every_district():
    books = published.books_of(ITHACA)
    assert len(books) >= 20 and all(b.parent.name in ("5_zoning_rules", "drafted") for b in books)
    for book in books:
        live = published.compile_zoning(ITHACA, book)
        got = published.frozen(ITHACA, book)
        assert live["problems"] == [] and {k: got[k] for k in live} == live, book.name
        assert got["book"] == book.read_bytes() and got["kinds"]["use"], book.name


def test_a_missing_or_stale_zoning_certificate_gives_no_report(monkeypatch, tmp_path):
    book = rulebook_for(ITHACA, load(SITE)["zone"])
    real = published.certificate_path
    monkeypatch.setattr(published, "certificate_path",
                        lambda f, b: tmp_path / "gone.json" if Path(b) == book else real(f, b))
    with pytest.raises(ValueError, match="frozen copy can't be used.*no certificate at"):
        report.tables(SITE)
    (tmp_path / "gone.json").write_bytes(real(ITHACA, book).read_bytes().replace(b'"sha256": "', b'"sha256": "0', 1))
    with pytest.raises(ValueError, match="is stale"):
        report.tables(SITE)


def test_the_report_and_the_check_take_the_rules_from_the_bytes_checked_never_a_second_read(monkeypatch):
    """Review the old path: the check read the rulebook again after the report's checks (check.py) and built a second
    Context for its uses. Any later read of the rulebook here gives no rules: the rows and the check's rules are
    still the checked ones."""
    book = rulebook_for(ITHACA, load(SITE)["zone"])
    real = report.load
    monkeypatch.setattr(report, "load", lambda p: {"rules": []} if Path(p) == book else real(p))
    t = report.tables(SITE)
    assert t["rules"] == load(book)["rules"] and t["output"] and t["uses"]
