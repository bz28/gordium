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
    """How many JSON-lines readers a module has: json.loads applied to each item of a loop or comprehension
    (json.loads(line), json.loads(line.strip()), loads(l) after `from json import loads`, map(json.loads, f)),
    whatever the variable is called. One parse of the loop's own item counts once."""
    tree = ast.parse(source)
    names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "json"
             for a in n.names if a.name == "loads"}

    def is_loads(f):
        return (isinstance(f, ast.Attribute) and f.attr == "loads" and isinstance(f.value, ast.Name)
                and f.value.id == "json") or (isinstance(f, ast.Name) and f.id in names)

    def loads_of(nodes, loop_vars):
        return {id(c) for n in nodes for c in ast.walk(n) if isinstance(c, ast.Call) and is_loads(c.func)
                and c.args and {x.id for x in ast.walk(c.args[0]) if isinstance(x, ast.Name)} & loop_vars}

    def targets(node):
        return {t.id for t in ast.walk(node) if isinstance(t, ast.Name)}

    found = {id(n) for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "map" and n.args and is_loads(n.args[0])}
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            found |= loads_of(node.body, targets(node.target))
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            loop_vars = set().union(*(targets(g.target) for g in node.generators))
            parts = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
            found |= loads_of(parts + [c for g in node.generators for c in g.ifs], loop_vars)
    return len(found)


LISTING = re.compile(r"""\.glob\(\s*['"]\*/\*['"]\s*\)""")      # <state>/<place>, either quote style


def test_the_checks_recognise_any_spelling():
    assert _jsonl_readers("rows = [json.loads(l) for l in f]") == 1
    assert _jsonl_readers("for row in f:\n    r = json.loads(row)") == 1
    assert _jsonl_readers("x = json.loads(text)") == 0
    assert _jsonl_readers("for text in f:\n    pass\nanswer = json.loads(text)") == 0   # same name, not in the loop
    assert _jsonl_readers("rows = [json.loads(l.strip()) for l in f]") == 1
    assert _jsonl_readers("for l in f:\n    r.append(json.loads(l.rstrip()))") == 1
    assert _jsonl_readers("rows = list(map(json.loads, f))") == 1
    assert _jsonl_readers("from json import loads\nrows = [loads(l) for l in f]") == 1
    assert LISTING.search("root.glob('*/*')") and LISTING.search('root.glob("*/*")')
    assert not LISTING.search('root.glob("*/*.pdf")')


def test_every_jsonl_file_is_read_by_the_one_reader():
    found = {p.relative_to(REPO).as_posix(): n for p in CODE if (n := _jsonl_readers(p.read_text()))}
    assert found == {"packages/rule_format/rule_format/rulebook.py": 1}, f"use rulebook.read_jsonl: {found}"


def test_every_jurisdiction_listing_uses_the_one_helper():
    found = [f"{p.relative_to(REPO)}:{n}" for p in CODE
             for n, line in enumerate(p.read_text().splitlines(), 1) if LISTING.search(line)]
    assert len(found) == 1 and "rulebook.py" in found[0], f"use rulebook.jurisdictions(): {found}"


VOCABULARY = [REPO / "regulations/document_extraction_guide/vocabulary.yaml"]
APPROVAL = re.compile(r"\barchitect\w*\b[^.\n]{0,80}?\bapprov|\bapprov\w*\b[^.\n]{0,80}?\barchitect", re.IGNORECASE)
# Claims that are false while approval is deferred, however a document is worded around them.
FALSE_CLAIMS = re.compile(r"until (an )?architects? (approves?|answers)|only approved rules|approved rulebook"
                          r"|\|\s*architects approve\s*\||\(architects approve\)|architects? confirm each rule|compares the new draft with the approved"
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
    # Architects confirming labels, definitions or the vocabulary is the same deferred layer: each sentence
    # that says so must say it's deferred. (An architect confirming their own project's facts is not.)
    confirm = [f"{p.relative_to(REPO)}: {line.strip()[:100]}" for p in DOCS + VOCABULARY
               for line in re.split(r"(?<=[.!?])\s+|\n", p.read_text())
               if re.search(r"architects (would )?confirm", line, re.IGNORECASE) and "defer" not in line.lower()]
    assert not silent and not false and not confirm, (silent, false, confirm)
