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


def _uses(pattern: str) -> list[str]:
    """Where a pattern occurs in the packages' code (tests excluded), as file:line."""
    return [f"{p.relative_to(REPO)}:{n}" for p in CODE
            for n, line in enumerate(p.read_text().splitlines(), 1) if re.search(pattern, line)]


def test_every_jsonl_file_is_read_by_the_one_reader():
    uses = _uses(r"json\.loads\(line\)")
    assert len(uses) == 1 and "rulebook.py" in uses[0], f"read .jsonl files with rulebook.read_jsonl: {uses}"


def test_every_jurisdiction_listing_uses_the_one_helper():
    uses = _uses(r'\.glob\("\*/\*')                  # <state>/<place>, however the folder is named
    assert len(uses) == 1 and "rulebook.py" in uses[0], f"list jurisdictions with rulebook.jurisdictions(): {uses}"


def test_docs_dont_promise_approval_while_it_is_deferred():
    """Approval is deferred (2026-10-19): no reviewer is listed and the checker uses draft rules. Until a
    reviewer is added, no document may claim nothing is used before an architect approves it."""
    if yaml.safe_load((REPO / "regulations/reviewers.yaml").read_text()):
        return
    stale = re.compile(r"until an architect approves|only approved rules are used|architects approve every",
                       re.IGNORECASE)
    found = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in DOCS for m in stale.finditer(p.read_text())]
    assert not found, found
