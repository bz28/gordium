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
        def the_item(arg):              # the loop's own item, maybe stripped: l, l.strip(), l.rstrip("\\n")
            if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute)
                    and arg.func.attr in ("strip", "rstrip", "lstrip", "decode")):
                arg = arg.func.value
            return isinstance(arg, ast.Name) and arg.id in loop_vars
        return {id(c) for n in nodes for c in ast.walk(n) if isinstance(c, ast.Call) and is_loads(c.func)
                and c.args and the_item(c.args[0])}

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
    assert _jsonl_readers('answers = [json.loads(r["answer"]) for r in records]') == 0   # a field, not a line
    assert _jsonl_readers('answers = [json.loads(r.get("answer")) for r in records]') == 0
    assert _jsonl_readers("for p in paths:\n    d = json.loads(p.read_text())") == 0       # a whole file
    assert LISTING.search("root.glob('*/*')") and LISTING.search('root.glob("*/*")')
    assert not LISTING.search('root.glob("*/*.pdf")')


def test_every_jsonl_file_is_read_by_the_one_reader():
    found = {p.relative_to(REPO).as_posix(): n for p in CODE if (n := _jsonl_readers(p.read_text()))}
    assert found == {"packages/rule_format/rule_format/rulebook.py": 1}, f"use rulebook.read_jsonl: {found}"


def test_every_jurisdiction_listing_uses_the_one_helper():
    found = [f"{p.relative_to(REPO)}:{n}" for p in CODE
             for n, line in enumerate(p.read_text().splitlines(), 1) if LISTING.search(line)]
    assert len(found) == 1 and "rulebook.py" in found[0], f"use rulebook.jurisdictions(): {found}"


# YAML files people read too (their comments describe the workflow): the vocabulary, definitions, rulebooks.
REGULATION_YAML = [p for p in (REPO / "regulations").rglob("*.yaml") if "runs" not in p.relative_to(REPO).parts]
assert REGULATION_YAML
APPROVAL = re.compile(r"\barchitect\w*\b[^.\n]{0,80}?\bapprov|\bapprov\w*\b[^.\n]{0,80}?\barchitect", re.IGNORECASE)
# Claims that are false while approval is deferred, however a document is worded around them.
FALSE_CLAIMS = re.compile(r"until (an )?architects? (approves?|answers)|only approved rules|approved rulebook"
                          r"|\|\s*architects approve\s*\||\(architects approve\)|architects? confirm each rule|compares the new draft with the approved"
                          r"|architect'?s approval freezes|architect\s*──►", re.IGNORECASE)


ARCHITECT_REVIEW = re.compile(
    r"\barchitects?\s+(would\s+)?(confirm|review|check|approve|sign)s?\b"                  # architects confirm...
    r"|\b(confirmed|reviewed|checked|approved|signed off)\s+by\b[^.\n]{0,30}?\barchitects?\b"  # ...confirmed by architects
    r"|\bthen architects\b|\barchitect review\b", re.IGNORECASE)
NOT_A_PROMISE = re.compile(r"defer|once (it is |approval is )?switched on|when approval is switched on|\bwould\b"
                           r"|their (own )?(site|design|project)|facts about|by hand|answers? (the |any )?open questions", re.IGNORECASE)


def _promises_architect_review(sentence: str) -> bool:
    """A sentence that presents architects checking drafts as happening now (not deferred, not conditional).
    An architect confirming their own project's facts, or answering open questions, is not that."""
    return bool(ARCHITECT_REVIEW.search(sentence)) and not NOT_A_PROMISE.search(sentence)


def test_the_architect_review_matcher():
    for promise in ["confirmed by step 2 and by architects", "an architect confirms each label",
                    "reviewers and architects check the rest", "Code, then AI for leftovers, then architects",
                    "is caught by comparing outputs, and by architect review", "Draft: architects approve",
                    "caught by comparing the answer key with the chart, and by architect review"]:
        assert _promises_architect_review(promise), promise
    for fine in ["the architect confirms the facts about their site and design",
                 "Architects answer the open questions", "architect approval is deferred for now",
                 "Choices for the architects to confirm", "Rules checked by hand by architects",
                 "Something only an architect can judge", "the architects' R-1b check for 106 Ithaca Road",
                 "an answer key once approval is switched on", "Architects would confirm each definition"]:
        assert not _promises_architect_review(fine), fine


def test_docs_dont_promise_approval_while_it_is_deferred():
    """Approval is deferred (2026-10-19): nothing is approved and the checker uses draft rules. Until something
    is approved (listing a reviewer alone doesn't switch approval on), a document that talks about architects
    approving rules must say approval is deferred, and none may claim the checker waits for approved rules."""
    if any(re.search(r"^\s*status:\s*approved\b", p.read_text(), re.MULTILINE) for p in REGULATION_YAML):
        return                                   # approval is switched on once anything is approved
    silent = [str(p.relative_to(REPO)) for p in DOCS + REGULATION_YAML
              if APPROVAL.search(p.read_text()) and not re.search(r"deferred", p.read_text(), re.IGNORECASE)]
    false = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in DOCS for m in FALSE_CLAIMS.finditer(p.read_text())]
    # Architects approving, confirming, checking or reviewing drafts is the deferred layer: each sentence that
    # says so must say it's deferred (or describe what happens once it is switched on).
    confirm = [f"{p.relative_to(REPO)}: {line.strip()[:100]}" for p in DOCS + REGULATION_YAML
               for line in re.split(r"(?<=[.!?])\s+|\n", p.read_text()) if _promises_architect_review(line)]
    assert not silent and not false and not confirm, (silent, false, confirm)


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
    assert "requires more.**" not in item              # the headline may not settle the open question either


def test_no_doc_claims_a_rear_yard_floor_across_readings():
    """On the 106 Ithaca Rd lot one reading of the side lot lines gives the 20 ft minimum (item 4.2), so no
    document may claim the rear setback needs more 'under any reading' or quote 22.6 ft as a floor."""
    claims = re.compile(r"(rear|setback)[^.\n]*(any reading|at least 22\.6)|22\.6 ft under", re.IGNORECASE)
    found = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in DOCS for m in claims.finditer(p.read_text())]
    assert not found, found


def test_the_106_ithaca_rd_areas_are_quoted_as_measured():
    """The areas of the architects' model, as measured (shoelace area of its Site polylines, in feet): the
    lot is 6,674.5 sf (their spreadsheet types 6,674) and the buildable-area outline 2,169.2 sf. Figures
    that match neither (6,674.7 and 2,169.5 once spread through the docs) are kept out."""
    def area(points):
        return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2
    lot = [(395.432, 360.94), (439.51, 419.13), (367.546, 473.642), (326.184, 420.017), (315.713, 420.262)]
    buildable = [(344.641, 411.2), (377.402, 386.822), (409.558, 429.273), (377.381, 453.647)]
    assert (round(area(lot), 1), round(area(buildable), 1)) == (6674.5, 2169.2)
    site = (REPO / "test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/README.md").read_text()
    assert "6,674.5 sf" in site and "2,169.2 sf" in site
    files = [p for p in REPO.rglob("*") if p.suffix in (".md", ".yaml") and p.is_file()
             and not {".git", ".claude", ".venv"} & set(p.relative_to(REPO).parts)]
    assert not [p.relative_to(REPO) for p in files if re.search(r"6,?674\.7|2,?169\.5", p.read_text())]
