"""One definition for things every package does: read a .jsonl file, list the jurisdictions, and describe
approval truthfully. Each test fails if a second copy (or an outdated promise) creeps back in."""

import ast
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


def _jsonl_readers(source: str) -> int:
    """How many JSON-lines readers a module has: a json.loads(x) call where x is the loop variable of an
    enclosing for-loop or comprehension (over lines), whatever the variable is called."""
    tree = ast.parse(source)
    looped = {t.id for node in ast.walk(tree) if isinstance(node, (ast.For, ast.comprehension))
              for t in ast.walk(node.target) if isinstance(t, ast.Name)}
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and node.func.attr == "loads"
               and isinstance(node.func.value, ast.Name) and node.func.value.id == "json"
               and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in looped)


LISTING = re.compile(r"""\.glob\(\s*['"]\*/\*['"]\s*\)""")      # <state>/<place>, either quote style


def test_the_checks_recognise_any_spelling():
    assert _jsonl_readers("rows = [json.loads(l) for l in f]") == 1
    assert _jsonl_readers("for row in f:\n    r = json.loads(row)") == 1
    assert _jsonl_readers("x = json.loads(text)") == 0
    assert LISTING.search("root.glob('*/*')") and LISTING.search('root.glob("*/*")')
    assert not LISTING.search('root.glob("*/*.pdf")')


def test_every_jsonl_file_is_read_by_the_one_reader():
    found = {p.relative_to(REPO).as_posix(): n for p in CODE if (n := _jsonl_readers(p.read_text()))}
    assert found == {"packages/rule_format/rule_format/rulebook.py": 1}, f"use rulebook.read_jsonl: {found}"


def test_every_jurisdiction_listing_uses_the_one_helper():
    found = [f"{p.relative_to(REPO)}:{n}" for p in CODE
             for n, line in enumerate(p.read_text().splitlines(), 1) if LISTING.search(line)]
    assert len(found) == 1 and "rulebook.py" in found[0], f"use rulebook.jurisdictions(): {found}"


APPROVAL = re.compile(r"\barchitect\w*\b[^.\n]{0,80}?\bapprov|\bapprov\w*\b[^.\n]{0,80}?\barchitect", re.IGNORECASE)
# Claims that are false while approval is deferred, however a document is worded around them.
FALSE_CLAIMS = re.compile(r"until (an )?architects? (approves?|answers)|only approved rules|approved rulebook"
                          r"|architects approve\b|architects? confirm each rule|compares the new draft with the approved"
                          r"|architect'?s approval freezes|architect\s*──►", re.IGNORECASE)


def test_docs_dont_promise_approval_while_it_is_deferred():
    """Approval is deferred (2026-10-19): no reviewer is listed and the checker uses draft rules. Until a
    reviewer is added, a document that talks about architects approving rules must say approval is deferred,
    and none may claim the checker waits for, or reads only, approved rules."""
    if yaml.safe_load((REPO / "regulations/reviewers.yaml").read_text()):
        return
    silent = [str(p.relative_to(REPO)) for p in DOCS
              if APPROVAL.search(p.read_text()) and not re.search(r"deferred", p.read_text(), re.IGNORECASE)]
    false = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in DOCS for m in FALSE_CLAIMS.finditer(p.read_text())]
    assert not silent and not false, (silent, false)


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


def test_no_doc_claims_a_rear_yard_floor_across_readings():
    """On the 106 Ithaca Rd lot one reading of the side lot lines gives the 20 ft minimum (item 4.2), so no
    document may claim the rear setback needs more 'under any reading' or quote 22.6 ft as a floor."""
    claims = re.compile(r"(rear|setback)[^.\n]*(any reading|at least 22\.6)|22\.6 ft under", re.IGNORECASE)
    found = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in DOCS for m in claims.finditer(p.read_text())]
    assert not found, found
