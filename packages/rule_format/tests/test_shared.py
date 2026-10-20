"""One definition for things every package does: read a .jsonl file, list the jurisdictions, and describe
approval truthfully. Each test fails if a second copy (or an outdated promise) creeps back in."""

import re

import yaml

from rule_format.rulebook import REPO, jurisdictions, read_jsonl

CODE = [p for p in (REPO / "packages").rglob("*.py") if "tests" not in p.relative_to(REPO).parts]
# Paths are judged inside the repository: a checkout can itself sit in a folder named .claude.
DOCS = [p for p in REPO.rglob("*.md")
        if not {".git", ".claude", ".venv", "node_modules"} & set(p.relative_to(REPO).parts)
        and p.name != "CLAUDE.md"]   # CLAUDE.md states the project's principles; it is changed by its own PR
assert DOCS and CODE


def test_read_jsonl_reads_utf8_and_skips_blank_lines(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_bytes('{"t": "§325-3 — “quoted”"}\n\n{"t": 2}\n'.encode("utf-8"))
    assert read_jsonl(path) == [{"t": "§325-3 — “quoted”"}, {"t": 2}]


def test_jurisdictions_lists_each_place_folder(tmp_path):
    assert REPO / "regulations/jurisdictions/new_york/ithaca_city" in jurisdictions()
    (tmp_path / "regulations/jurisdictions/ny/a").mkdir(parents=True)
    (tmp_path / "regulations/jurisdictions/ny/README.md").write_text("")
    assert jurisdictions(tmp_path) == [tmp_path / "regulations/jurisdictions/ny/a"]


def test_every_jsonl_file_is_read_by_the_one_reader():
    copies = [p for p in CODE if p.name != "rulebook.py" and re.search(r"json\.loads\(line\)", p.read_text())]
    assert not copies, f"read .jsonl files with rule_format.rulebook.read_jsonl: {copies}"


def test_every_jurisdiction_listing_uses_the_one_helper():
    pattern = re.compile(r'\.glob\("\*/\*')       # <state>/<place>, however the folder is named
    copies = [p for p in CODE if p.name != "rulebook.py" and pattern.search(p.read_text())]
    assert not copies, f"list jurisdictions with rule_format.rulebook.jurisdictions(): {copies}"


def test_docs_dont_promise_approval_while_it_is_deferred():
    """Approval is deferred (2026-10-19): no reviewer is listed and the checker uses draft rules. Until a
    reviewer is added, no document may claim nothing is used before an architect approves it."""
    if yaml.safe_load((REPO / "regulations/reviewers.yaml").read_text()):
        return
    stale = re.compile(r"until an architect approves|only approved rules are used|architects approve every",
                       re.IGNORECASE)
    found = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in DOCS for m in stale.finditer(p.read_text())]
    assert not found, found


def test_discrepancy_4_2_matches_the_rear_yard_arithmetic():
    """Item 4.2 (the 106 Ithaca Rd rear setback) must state the readings as the R-1b formula gives them:
    one reading of the lot's side lines allows the drawn 20 ft, so it may not say 20 ft fails 'under any reading'."""
    def required(depth):
        return max(min(0.25 * depth, 50), 20)
    readings = {"23.7": (90.28 + 99.37) / 2,              # the two long side lines
                "25.015": (90.28 + (99.37 + 10.47)) / 2,  # the jog added to the line it continues
                "20": (90.28 + 10.47 + 99.37) / 3}        # every line that isn't front or rear
    assert [round(required(d), 3) for d in readings.values()] == [23.706, 25.015, 20]
    item = next(line for line in (REPO / "docs/discrepancies_with_architects.md").read_text().splitlines()
                if line.startswith("| 4.2 "))
    assert "any reading" not in item and all(f"{k} ft" in item for k in readings)


def test_the_106_ithaca_rd_lot_area_is_quoted_as_measured():
    """The architects' model lot measures 6,674.5 sf (shoelace area of its Site polyline) and their
    spreadsheet types 6,674. A third figure, 6,674.7, once spread through the docs and rules; keep it out."""
    lot = [(395.432, 360.94), (439.51, 419.13), (367.546, 473.642), (326.184, 420.017), (315.713, 420.262)]
    area = abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(lot, lot[1:] + lot[:1]))) / 2
    assert round(area, 1) == 6674.5
    files = [p for p in REPO.rglob("*") if p.suffix in (".md", ".yaml") and p.is_file()
             and not {".git", ".claude", ".venv"} & set(p.relative_to(REPO).parts)]
    assert not [p.relative_to(REPO) for p in files if re.search(r"6,?674\.7", p.read_text())]
