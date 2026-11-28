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


def test_a_checks_verdicts_come_from_the_checked_rulebook_never_a_second_read_in_check(monkeypatch):
    """Review round 1 of PR 4 (F2): check.py read the rulebook again after the report's checks, so a rulebook saved in
    between could decide a verdict from rules no one checked. With check.load giving rules that would fail everything
    for this rulebook, the check's rows are the same as with the real one."""
    import copy
    import sys
    from design_checker import check
    sys.path.insert(0, str(REPO / "packages/model_measurement/tests"))
    from test_measure import FACTS, box, lot
    site = {"units": "ft", "lot": lot([(0, 0), (60, 0), (60, 110), (0, 110)]),
            "buildings": [box(10, 25, 40, 75, 0, 30)], "problems": []}
    before = check.check_site(copy.deepcopy(site), dict(FACTS))["view"]["items"]
    book = rulebook_for(ITHACA, FACTS["zone"])
    real = check.load

    def edited(p):
        got = real(p)
        if Path(p) == book:
            got = copy.deepcopy(got)
            for r in got["rules"]:
                if r.get("check"):
                    r["check"] = "front_yard < 0"
        return got
    monkeypatch.setattr(check, "load", edited)
    after = check.check_site(copy.deepcopy(site), dict(FACTS))["view"]["items"]
    assert [(i["id"], i["status"]) for i in after] == [(i["id"], i["status"]) for i in before]


def test_the_worker_publishes_before_its_first_answer(monkeypatch):
    """Review round 3 of PR 4 (F1): a missing zoning certificate refuses the whole check, and nothing published for a
    worker started by the Rhino plugin or by hand. `python -m design_checker serve` makes the certificates current
    (published.ensure: the fresh-process publish, never a live check) before it reads a request."""
    from design_checker import __main__ as worker

    class Stop(Exception):
        pass
    asked = []
    monkeypatch.setattr(published, "ensure", lambda missing_only=False: asked.append(missing_only) or _stop())
    monkeypatch.setattr(worker, "serve", lambda **kw: asked.append("served"))

    def _stop():
        raise Stop
    with pytest.raises(Stop):
        worker.main(["serve"])
    assert asked == [False]


def test_ensure_on_current_certificates_hashes_each_file_once(monkeypatch):
    """Review round 3 of PR 4 (F2): Ithaca's 21 districts share their inputs, and ensure() hashed them again for each,
    about 25 times slower than before PR 4. Within one ensure, each file is hashed once."""
    published.ensure()
    seen = []
    real = published._sha
    monkeypatch.setattr(published, "_sha", lambda p: seen.append(str(p)) or real(p))
    assert published.ensure() == []
    assert seen and len(seen) == len(set(seen))
