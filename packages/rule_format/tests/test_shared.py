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


# A backstop, not a parser: it catches the usual ways of saying architects check drafts now. Verbs in any tense,
# up to three words between "architects" and the verb (but not "to"/"can"/"may"..., which make it a possibility),
# and the noun forms (architect's / architects' / architect- review, approval...).
_VERB = r"(?:confirm|review|check|approv|sign)\w*"
_GAP = r"(?:[\s,]+(?!(?:to|can|could|may|might|would)\b)\w+){0,3}?"
ARCHITECT_REVIEW = re.compile(
    rf"\barchitects?\b(?!['\u2019-]){_GAP}[\s,]+{_VERB}\b"
    rf"|\b(?:confirmed|reviewed|checked|approved|signed off)\s+by\b[^.\n]{{0,30}}?\barchitects?\b"
    r"|\bthen architects\b"
    r"|\barchitect(?:s['\u2019]|['\u2019]s|s)?[\s-]+(?:review|confirm\w*|check\w*|sign-?off|approv\w*)\b", re.IGNORECASE)
# What makes such a phrase not a promise. A sentence that says approval is deferred, or describes what happens
# once it is switched on, is fine wherever it says so. The narrower excuses ("by hand", "facts about their
# site") only count right next to the phrase, so they can't excuse an unrelated promise in the same sentence.
DEFERRED = re.compile(r"\b(approval|review|reviews|it|this|that|they)\s+((is|are|stays|remains)\s+)?deferred"
                      r"|deferred\s+(for now|until)|\(deferred|\bonce (approval|it) is (switched )?on\b|\bonce approved\b"
                      r"|\bonce (the )?architects? approves?|when (approval is|it's|it is) switched on|\bwould\b",
                      re.IGNORECASE)
NEARBY_EXCUSE = re.compile(r"facts about their (own )?(site|design|project)|checked by hand by architects"
                           r"|answers? (the |any )?open questions", re.IGNORECASE)
_WINDOW = 40


def _promises_architect_review(sentence: str) -> bool:
    """A sentence that presents architects checking drafts as happening now (not deferred, not conditional).
    An architect confirming their own project's facts, or answering open questions, is not that."""
    if DEFERRED.search(sentence):
        return False
    return any(not NEARBY_EXCUSE.search(sentence[max(0, m.start() - _WINDOW):m.end() + _WINDOW])
               for m in ARCHITECT_REVIEW.finditer(sentence))


def _sentences(text: str, yaml_comments: bool = False) -> list[str]:
    """Whole sentences: lines wrapped inside a paragraph (or inside a YAML comment) are joined back together.
    Headings, list items, table rows and code-block lines each stand alone."""
    sentences, current, in_code = [], [], False
    def flush():
        if current:
            sentences.extend(re.split(r"(?<=[.!?])\s+", " ".join(current)))
            current.clear()
    for line in text.splitlines():
        if yaml_comments:
            line = line.split("#", 1)[1] if "#" in line else ""
        stripped = line.strip()
        if stripped.startswith("```"):
            flush(); in_code = not in_code; continue
        if in_code or re.match(r"(#|\||[-*+]\s|\d+\.\s)", stripped):
            flush(); current.append(stripped); flush(); continue
        if not stripped:
            flush(); continue
        current.append(stripped)
    flush()
    return [s for s in sentences if s]


def test_the_architect_review_matcher():
    for promise in ["confirmed by step 2 and by architects", "an architect confirms each label",
                    "reviewers and architects check the rest", "Code, then AI for leftovers, then architects",
                    "is caught by comparing outputs, and by architect review", "Draft: architects approve",
                    "caught by comparing the answer key with the chart, and by architect review",
                    "once per code version: an architect confirms each rule is right",
                    "Architects will confirm each label", "An architect must approve each rule",
                    "Labels need architect confirmation", "an architect's review catches the wrong column",
                    "Architects approved each rule", "An architect confirmed each label",
                    "Architects have approved the rulebook", "Architects are reviewing each rule",
                    "Architects carefully check each rule", "the architects' review catches errors",
                    "architect-approved rules", "Architects review every draft rule by hand",
                    "Architects review each rule against their design",
                    "Architects review each label; the deferred items listed at the end of this long document go to Ben"]:
        assert _promises_architect_review(promise), promise
    for fine in ["the architect confirms the facts about their site and design",
                 "Architects answer the open questions", "architect approval is deferred for now",
                 "Choices for the architects to confirm", "Rules checked by hand by architects",
                 "Something only an architect can judge", "the architects' R-1b check for 106 Ithaca Road",
                 "an answer key once approval is switched on", "Architects would confirm each definition",
                 "An architect can approve each rule once approval is switched on"]:
        assert not _promises_architect_review(fine), fine


def test_sentences_are_joined_across_wrapped_lines():
    comment = "key: 1  # Rules are drafts. Architects check each\n# rule before use.\nother: 2\n"
    assert "Architects check each rule before use." in _sentences(comment, yaml_comments=True)
    prose = "Rules are drafts. Architects check each\nrule before use.\n\n- a list item\n"
    assert "Architects check each rule before use." in _sentences(prose)
    assert _sentences("- one item\n- two items\n") == ["- one item", "- two items"]


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
               for line in _sentences(p.read_text(), yaml_comments=p.suffix == ".yaml")
               if _promises_architect_review(line)]
    assert not silent and not false and not confirm, (silent, false, confirm)
