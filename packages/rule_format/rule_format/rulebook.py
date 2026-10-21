"""Load a district rule file, decide a rule's outcome, and validate rules.

Outcome order (never a false pass):
  1. applies_when false            -> not_applicable
  2. kind is "flag"                -> needs_review (an architect must judge it)
  3. any review_when true          -> needs_review
  4. check true / false            -> pass / fail
A missing or unusable measurement, or a value the formula can't evaluate -> needs_review
"""

import datetime
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import formula
from .formula import EvaluationError, FormulaError, MissingMeasure

REPO = Path(__file__).resolve().parents[3]
MEASURES_FILE = Path(__file__).with_name("measures.yaml")
VOCABULARY_FILE = REPO / "regulations/document_extraction_guide/vocabulary.yaml"
REVIEWERS_FILE = REPO / "regulations/reviewers.yaml"

OUTCOMES = ("pass", "fail", "needs_review", "not_applicable")
KINDS = ("rule", "flag")  # rule: code checks it; flag: an architect must judge it
STATUSES = ("draft", "approved")
# A rule has a short `title`, not a plain-English retelling: the city's words are in `sources`, the
# meaning is the `check` and its `examples`. (Retellings kept dropping or adding words.)
RULE_FIELDS = {"id", "kind", "topic", "title", "applies_when", "check", "review_when", "sources", "examples",
               "notes", "open_questions", "research", "findings", "answers", "drafted_by", "status", "approved_by", "approved_on",
               "approved_hash", "relaxes"}
TEXT_FIELDS = ("id", "kind", "topic", "title", "drafted_by", "status", "approved_by", "relaxes")
TITLE_MAX = 80                                    # a label, one line: long enough to name, too short to retell
ITEM_FIELDS = {"review_when": {"when", "reason"}, "sources": {"file", "page", "lines", "quote", "cell", "not_limits"},
               "examples": {"given", "expect", "note"}}
CELL_FIELDS = {"section", "row", "column"}   # a chart cell source: {file, page, cell: {section, row, column}}
APPROVED_FIELDS = ("id", "kind", "topic", "title", "applies_when", "check", "review_when", "sources", "findings",
                   "answers")
UNIT_KINDS = {"text": "text", "yes_no": "boolean"}       # every other unit (ft, sf, count) is a number
MEASURE_KINDS = {name: UNIT_KINDS.get(m["unit"], "number") for name, m in yaml.safe_load(MEASURES_FILE.read_text(encoding="utf-8")).items()}
# Measures a draft asked for that aren't in measures.yaml yet: listed for engineers, never used silently.
PROPOSED_MEASURES = "5_zoning_rules/drafted/records/proposed_measures.yaml"


def outcome(rule: dict, values: dict, allowed: dict[str, set]) -> str:
    """allowed: the values each text measure may take, e.g. {"use": the city's use names}.
    Required, so no caller can forget it. A value outside the list, or a text measure with
    no list, is unrecognized. A measure that isn't in measures.yaml (one a draft proposed) is described here by
    its kind instead: "number" or "boolean". A missing or unusable measure is unknown: the result is pass or fail
    only if it is the same whatever that measure turns out to be (three-valued logic, formula.evaluate); else
    needs review."""
    kinds = MEASURE_KINDS | {k: v if isinstance(v, str) else frozenset(v) for k, v in allowed.items()}
    try:
        if "applies_when" in rule and not _condition(rule["applies_when"], values, kinds):
            return "not_applicable"
        if rule["kind"] == "flag":
            return "needs_review"
        if any(_condition(r["when"], values, kinds) for r in rule.get("review_when", [])):
            return "needs_review"
        return "pass" if _condition(rule["check"], values, kinds) else "fail"
    except (MissingMeasure, EvaluationError, FormulaError, ArithmeticError):
        return "needs_review"         # a formula that can't be read (never frozen so) is never a crash


def apply_relaxes(rules: list[dict]) -> list[dict]:
    """An exception that widens another rule (`relaxes: <rule id>`: §325-16C's extra height relaxes the chart's height
    limit), applied by composing the relaxed rule, so every verdict path (outcome, the every-reading check) reads it
    unchanged. The relaxed rule passes if its own check passes, or if a rule relaxing it applies and passes its
    own check: `base or (when_1 and check_1) or ... or (when_n and check_n)`, worked out in three-valued logic, so an
    unknown relaxer can only make a failing base need review, never pass. A relaxer's review_when becomes the relaxed
    rule's, where the relaxation is what decides. A relaxer is never widened by this; it stays its own rule too. Rules
    with no relaxer are returned as they are (validate checks relaxes: same rulebook, a rule with a condition, no cycle)."""
    by_target: dict[str, list[dict]] = {}
    for r in rules:
        if isinstance(r.get("relaxes"), str):
            by_target.setdefault(r["relaxes"], []).append(r)
    if not by_target:
        return rules
    out = []
    for r in rules:
        relaxers = by_target.get(r.get("id"))
        if not relaxers or r.get("kind") != "rule" or not r.get("check"):
            out.append(r)
            continue
        widen = " or ".join(f"(({x['applies_when']}) and ({x['check']}))" for x in relaxers)
        review = list(r.get("review_when") or []) + [
            {"when": f"not ({r['check']}) and ({x['applies_when']}) and ({w['when']})", "reason": w.get("reason", "")}
            for x in relaxers for w in x.get("review_when") or []]
        out.append(r | {"check": f"({r['check']}) or ({widen})", "review_when": review,
                        "relaxed_by": [x["id"] for x in relaxers]})
    return out


def _relaxes_problems(rules: list[dict]) -> list[str]:
    """`relaxes` names a rule of the same rulebook (so the same district), from a rule with a condition and a check
    (an exception holds only when all its conditions are met), never itself, never a flag, and never in a cycle."""
    ids = {r.get("id"): r for r in rules if isinstance(r, dict)}
    p = []
    for r in rules:
        target = r.get("relaxes") if isinstance(r, dict) else None
        if target is None:
            continue
        rid = r.get("id")
        if target == rid:
            p.append(f"{rid}: relaxes itself")
        elif target not in ids:
            p.append(f"{rid}: relaxes {target!r}, which isn't a rule of this rulebook")
        elif ids[target].get("kind") != "rule" or not ids[target].get("check"):
            p.append(f"{rid}: relaxes {target!r}, which has no check to widen")
        if r.get("kind") != "rule" or not r.get("check") or not r.get("applies_when"):
            p.append(f"{rid}: a relaxing rule needs its condition (applies_when) and its own check")
        seen, at = {rid}, target
        while at in ids and isinstance(ids[at].get("relaxes"), str):
            at = ids[at]["relaxes"]
            if at in seen:
                p.append(f"{rid}: relaxes in a cycle")
                break
            seen.add(at)
    return p


def _condition(text: str, values: dict, kinds: dict) -> bool:
    result = formula.evaluate(text, values, kinds)
    if type(result) is not bool:
        raise EvaluationError(f"{text!r} did not give true/false")
    return result


class _StrictLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate keys instead of silently keeping the last one."""

    def construct_mapping(self, node, deep=False):
        keys = [self.construct_object(k, deep=deep) for k, _ in node.value]
        if dup := next((k for k in keys if keys.count(k) > 1), None):
            raise yaml.constructor.ConstructorError(None, None, f"duplicate key {dup!r}", node.start_mark)
        return super().construct_mapping(node, deep)


def load(path):
    return yaml.load(Path(path).read_text(encoding="utf-8"), Loader=_StrictLoader)


def rulebook_paths(folder) -> list[Path]:
    """The rulebook files in a folder (5_zoning_rules/, an answer-key folder): every .yaml or .yml file
    under it, except the drafting script's own run records (drafted/records/), which aren't rulebooks. The one
    definition, used by the validator, the review list and the spreadsheet export alike."""
    folder = Path(folder)
    # Sorted by the path as written ("/", case kept), the same on every computer: Windows paths sort ignoring case.
    return sorted((p for p in folder.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file()
                   and "records" not in p.relative_to(folder).parts),
                  key=lambda p: p.relative_to(folder).as_posix()) if folder.is_dir() else []


def rulebook_for(jurisdiction, zone: str) -> Path | None:
    """The rulebook that holds a zone's rules: the hand-drafted 5_zoning_rules/<zone>.yaml when it exists,
    else the AI-drafted 5_zoning_rules/drafted/<zone>.yaml, else None. The one definition, used by the
    project report and the answer-key test alike. "general" (drafted/general.yaml, the rules for every district)
    is never a zone: None."""
    if zone == GENERAL:
        return None
    folder = Path(jurisdiction) / "5_zoning_rules"
    return next((p for p in (folder / f"{zone}.yaml", folder / "drafted" / f"{zone}.yaml") if p.is_file()), None)


GENERAL = "general"     # the AI-drafted rules for every district (drafted/general.yaml): never a zone of its own


def zone_rulebooks(jurisdiction, zone: str) -> list[Path]:
    """Every rulebook file whose rules apply to a zone: its rulebook (`rulebook_for`), and, when that is the
    AI-drafted one, the AI-drafted drafted/general.yaml too: the drafting script writes a law piece's rules for every
    district there (accessory-building distances, eaves), so a drafted district checked without it would silently
    drop them (a shed 4 ft from an R-1 side line shown as complying). A hand rulebook carries its own (R-1b), so
    general.yaml isn't added to it. Empty when the zone has no rulebook; "general" itself is never a zone."""
    book = rulebook_for(jurisdiction, zone)
    if book is None:
        return []
    general = Path(jurisdiction) / "5_zoning_rules/drafted" / f"{GENERAL}.yaml"
    return [book] + ([general] if book.parent.name == "drafted" and general.is_file() else [])


def is_ai_drafted(jurisdiction, zone: str) -> bool:
    """The zone's rules are the AI's drafts (no hand rulebook)."""
    book = rulebook_for(jurisdiction, zone)
    return book is not None and book.parent.name == "drafted"


def zone_rules(jurisdiction, zone: str) -> list[dict]:
    """The rules of every file in `zone_rulebooks`, in that order, each `relaxes` link applied (apply_relaxes)."""
    return apply_relaxes([r for p in zone_rulebooks(jurisdiction, zone) for r in (load(p) or {}).get("rules") or []])


def utf8_console() -> None:
    """Print in UTF-8, whatever the computer's code page: on Windows a command's output sent to a file, a pipe or CI
    is cp1252, which can't print ✓ or ✗ (the command crashed). Every command line calls this first."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").replace("-", "").lower() != "utf8":
            stream.reconfigure(encoding="utf-8")


def read_jsonl(path) -> list[dict]:
    """Every row of a JSON-lines file, read as UTF-8, blank lines skipped. The one reader of the repository's
    .jsonl files (extracted text, sections, run records), so every package reads the same bytes the same way."""
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def jurisdictions(repo: Path = REPO) -> list[Path]:
    """Every jurisdiction folder, regulations/jurisdictions/<state>/<place> under `repo`, in a stable order."""
    return sorted(p for p in (Path(repo) / "regulations/jurisdictions").glob("*/*") if p.is_dir())


@dataclass
class Context:
    """Everything a rule is checked against, for one jurisdiction."""
    measures: set[str]
    uses: set[str]
    topics: set[str]
    sources: dict[str, dict]                  # file name -> sources.yaml entry
    reviewers: set[str] = field(default_factory=set)                 # who may approve rules
    pages: dict[str, dict[int, dict[int, list[str]]]] = field(default_factory=dict)  # file -> page -> line -> tokens
    problems: list[str] = field(default_factory=list)                # problems with the sources themselves
    file_problems: dict[str, list[str]] = field(default_factory=dict)  # the same, by source file
    use_rows: dict[str, list[dict]] = field(default_factory=dict)    # use -> its sources in uses.yaml
    cells: dict[str, dict[tuple, dict]] = field(default_factory=dict)  # file -> (page, section, row, column) -> cell
    districts: set[str] = field(default_factory=set)                 # district names, as the city writes them
    proposed: dict[str, dict] = field(default_factory=dict)          # measures drafts asked for, not yet in measures.yaml
    pieces: set[str] = field(default_factory=set)                    # every piece id the law is cut into (research cites them)

    def kinds(self) -> dict:
        """Every usable measure's kind: "number", "text" or "boolean" (this context's measures, plus the
        proposed ones)."""
        return {n: MEASURE_KINDS.get(n, "number") for n in self.measures} | {
            n: UNIT_KINDS.get(m.get("unit"), "number") for n, m in self.proposed.items()}

    def allowed(self) -> dict:
        """What outcome() needs here: the text values each text measure may take, and each proposed
        measure's kind (a proposed text measure has no list of values yet, so it is unrecognized)."""
        proposed = {n: set() if k == "text" else k for n, k in self.kinds().items() if n in self.proposed}
        return {"use": self.uses, "district": self.districts} | proposed

    def _problem(self, name: str, message: str):
        self.problems.append(f"{name}: {message}")
        self.file_problems.setdefault(name, []).append(message)

    @classmethod
    def for_jurisdiction(cls, jurisdiction_dir) -> "Context":
        j = Path(jurisdiction_dir)
        uses_file = j / "4_term_definitions/uses.yaml"
        documents = load(j / "1_source_documents/sources.yaml")["documents"]
        listed = {d["file"]: d for d in documents}
        ctx = cls(measures=set(load(MEASURES_FILE)),
                  uses=set(uses_list := (load(uses_file) or {}) if uses_file.exists() else {}),
                  use_rows=_use_rows(uses_list),
                  topics=set(load(VOCABULARY_FILE)["topics"]),
                  reviewers=set(load(REVIEWERS_FILE) or ()),
                  sources=listed)
        counts = Counter(d["file"] for d in documents)
        for name in listed:                                      # sources.yaml order, so output is stable
            if counts[name] > 1:
                ctx._problem(name, "listed more than once in sources.yaml")
        for name, entry in listed.items():
            for problem in _source_entry_problems(entry):
                ctx._problem(name, problem)
        for name, entry in listed.items():
            pdf = j / "1_source_documents" / name
            sha = entry.get("sha256")
            if not sha:
                ctx._problem(name, "no sha256 in sources.yaml")
            elif not pdf.exists():
                ctx._problem(name, "listed in sources.yaml but missing")
            elif hashlib.sha256(pdf.read_bytes()).hexdigest() != sha:
                ctx._problem(name, "fingerprint does not match sources.yaml")
            extracted = j / "2_extracted_text" / f"{Path(name).stem}.jsonl"
            # Text is only trusted for a document whose own checks all passed.
            if extracted.exists() and name not in ctx.file_problems:
                ctx._load_extracted(name, sha, extracted)
            cut = j / "2_extracted_text" / f"{Path(name).stem}.sections.jsonl"
            if cut.exists():
                ctx.pieces |= {row["id"] for row in read_jsonl(cut)[1:]}
            cells = j / "2_extracted_text" / f"{Path(name).stem}.cells.jsonl"
            if entry.get("chart_pages") and cells.exists() and name not in ctx.file_problems:
                ctx._load_cells(name, sha, cells)
        proposed = j / PROPOSED_MEASURES
        if proposed.exists():
            listed_measures = load(proposed) or {}
            ctx.proposed = {n: m for n, m in listed_measures.items() if isinstance(m, dict) and n not in ctx.measures}
        return ctx

    def _load_cells(self, name, sha, path):
        """Chart cells read by the chart reader (document_extraction/charts.py). Only cells it read with
        certainty are in the file; unresolved parts of a table can never be cited."""
        rows = read_jsonl(path)
        if not rows or rows[0].get("sha256") != sha:
            self._problem(name, f"{path.name} was read from a different version; re-extract")
            return
        cells = {}
        for r in rows[1:]:
            if "columns" in r:
                self.districts |= {district_name(c["name"]) for c in r["columns"] if DISTRICT_COLUMN.fullmatch(c["name"])}
            elif "value" in r and not r.get("heading"):
                cells[(r["page"], r["section"], r["row"].strip(), r["column"])] = r
        self.cells[name] = cells

    def _load_extracted(self, name, sha, path):
        """Extracted text: a header line {"file", "sha256"}, then one {"page", "line", "text", ...} per line.
        The header ties it to the PDF version; CI re-extracts the text from the PDF (python -m
        document_extraction --check) and requires an exact match, so this file can't be edited by hand."""
        rows = read_jsonl(path)
        if not rows or rows[0].get("sha256") != sha:
            self._problem(name, f"{path.name} was extracted from a different version; re-extract")
            return
        pages: dict[int, dict[int, list[str]]] = {}
        for row in rows[1:]:
            pages.setdefault(int(row["page"]), {})[int(row["line"])] = tokenize(row["text"])
        self.pages[name] = pages


SOURCE_FIELDS = {"file", "title", "publisher", "url", "downloaded_on", "sha256", "pages", "contents", "notes",
                 "adopted_on", "created_on", "quotable", "not_quotable_because", "layout", "chart_pages"}
LAYOUTS = {"ecode360"}   # document layouts the section splitter knows (document_extraction/sections.py)
# A chart column that is a district, as the chart prints it (R-1B, R-3AA, RU): the one definition, used by the
# chart reader, the inspector and the drafter alike. Ithaca's residential names; another city adds its own here.
DISTRICT_COLUMN = re.compile(r"R-\d[A-Z]*|RU")


def district_name(column: str) -> str:
    """A chart column as the city writes the district in its law and in file names: R-1B -> R-1b."""
    m = re.fullmatch(r"([A-Z]+-\d+)([A-Z]*)", column)
    return m[1] + m[2].lower() if m else column


def _text_problems(f: str, allowed: dict[str, set]) -> list[str]:
    """Each quoted value must be one the measure it is compared with can take: a use for `use`, a district
    for `district`. So `use == "R-2a"` (a district written where a use belongs) can't pass the inspector and
    then never apply. A quoted value compared with anything else (another measure, or nothing) is refused."""
    out = []
    for name, value in formula.compared_strings(f):
        if name not in allowed:
            out.append(f"text value '{value}' in {f!r} must be compared with "
                       f"{' or '.join(sorted(allowed))}, not {name or 'nothing'}")
        elif value not in allowed[name]:
            out.append(f"unknown {name} '{value}' in {f!r}")
    return out


def _use_rows(uses) -> dict[str, list[dict]]:
    """Each use's well-formed cited rows from uses.yaml. Malformed entries are left out here and
    reported by validate_terms(uses), so a typo there can't crash rule validation."""
    if not isinstance(uses, dict):
        return {}
    return {k: [r for r in v.get("sources") if isinstance(r, dict) and isinstance(r.get("file"), str)
                and type(r.get("page")) is int and _is_line_range(r.get("lines"))]
            for k, v in uses.items() if isinstance(v, dict) and isinstance(v.get("sources"), list)}


def _is_line_range(lines) -> bool:
    return isinstance(lines, list) and len(lines) == 2 and all(type(n) is int for n in lines)


def _use_row_problems(rule: dict, sources: list[dict], ctx: "Context") -> list[str]:
    """A rule that decides about a use (in `check` or `review_when`) must cite that use's own row,
    the one uses.yaml cites, so every allowed or flagged use is traceable. (`applies_when` only scopes
    a rule; its own quotes cover that.)"""
    decisions = [rule.get("check")] + [r.get("when") for r in _list_of_dicts(rule, "review_when") or []]
    named = set()
    for f in decisions:
        try:
            named |= formula.strings(f) if isinstance(f, str) else set()
        except FormulaError:
            pass                                                # reported with the formula
    cited = _cited_lines(sources, ctx)
    return [f"use '{u}' is decided here but its row isn't cited (cite {r['file']} p.{r['page']} lines {r['lines']})"
            for u in sorted(named & set(ctx.use_rows)) for r in ctx.use_rows[u][:1]
            if not any((r["file"], r["page"], n) in cited
                                                          for n in range(r["lines"][0], r["lines"][1] + 1))]


def _cell(s: dict, ctx: "Context") -> dict | None:
    """The chart cell a well-formed cell source points at, or None."""
    c = s.get("cell")
    if not (isinstance(c, dict) and c.keys() == CELL_FIELDS and all(isinstance(c[k], str) for k in CELL_FIELDS)):
        return None
    return ctx.cells.get(s.get("file"), {}).get((s.get("page"), c["section"], c["row"].strip(), c["column"]))


def _cited_lines(sources: list[dict], ctx: "Context") -> set[tuple]:
    """(file, page, line) of every line the sources cite: a quote's lines, or a cell's row."""
    out = set()
    for s in sources:
        if (cell := _cell(s, ctx)) is not None:
            out |= {(s["file"], s["page"], n) for n in cell["row_lines"]}
        elif isinstance(s.get("file"), str) and type(s.get("page")) is int and _is_line_range(s.get("lines")):
            out |= {(s["file"], s["page"], n) for n in range(s["lines"][0], s["lines"][1] + 1)}
    return out


_PARTS = r"(?:\s*\([0-9a-z]{1,4}\))*"                                    # (3)(b)
_REF = (r"(?:(?:[a-z]-)?\d+[\d.\-]*[a-z]{0,2}(?![a-z])" + _PARTS +           # 325-20d(3)(b), 81-a, c-54
        r"|[a-z]?\([0-9a-z]{1,4}\)" + _PARTS +                              # b(7), (2)
        r"|[a-z](?![a-z]))")                                                # subsection c
_REFS = rf"{_REF}(?:\s*(?:,|and|or|through|to|&)\s*(?:§+\s*)?{_REF})*"   # §§ 325-8 and 325-9; b(7) to b(10)
NOT_A_LIMIT = re.compile(
    r"\[fn[^\]]*\]"                                                    # a footnote marker
    r"|\[(?:amended|added|repealed)[^\]]*\]"                           # an amendment note
    r"|(?:^|(?<=[.:;]))\s*(?:\(\s*(?:\d+|[a-z])\s*\)\s*)+"             # list markers opening the text or a sentence/clause
    rf"|\b(?:sections?\s+)?\d+\s*u\.\s*s\.\s*c\.\s*(?:§+\s*)?{_REFS}"  # a federal law: Section 47 U.S.C. 332(c)(7)
    rf"|§+\s*{_REFS}"                                                  # a section reference: § 325-20D(3)(b)
    rf"|\b(?:sub)?(?:sections?|paragraphs?|divisions?)\s+{_REFS}"      # Subsection B(7), Subsections (1), (2) and (3)
    rf"|\b(?:columns?|chapters?|articles?|ord(?:inance)?\.?\s*nos?\.|local laws?\s*no\.)\s*{_REFS}")
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "twenty": 20, "fifty": 50, "hundred": 100}


def source_numbers(text: str, percent_as_number: bool = True) -> set[float]:
    """Numbers written in a quote or a cell: digits ("6,000", "2.5", "3/2" gives 3 and 2) and whole number
    words ("three", not the "two" of "two-family"). Numbers that only label or point aren't limits and
    don't count: footnote markers ([fn16], and "(16)" opening a note), list numbers ("(3)" opening a sentence
    or clause), section, column, chapter and ordinance references (§325-16, Column 12, Chapter 228,
    [Amended 6-5-2013 by Ord. No. 2013-15]). A percent counts divided by 100: "25%" supports 0.25, and also
    25 unless percent_as_number is False (a typed number in a draft must be the fraction)."""
    text = NOT_A_LIMIT.sub(" ", text.lower())
    percent = r"(\d[\d,]*(?:\.\d+)?)\s*(?:%|percent\b)"
    fractions = {float(n.replace(",", "")) / 100 for n in re.findall(percent, text)}
    if not percent_as_number:
        text = re.sub(percent, " ", text)
    found = {float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?|(?<![\w.])\.\d+", text)}
    found |= {float(NUMBER_WORDS[w]) for w in re.findall(r"(?<![\w-])([a-z]+)(?![\w-])", text) if w in NUMBER_WORDS}
    return found | fractions


def _number_problems(rule: dict, sources: list[dict], ctx: "Context") -> list[str]:
    """Every number a formula uses must be written in one of the rule's own sources (a cited quote, or a
    cited chart cell or its row label), so no limit can be typed in from nowhere. 0 needs no source."""
    supported = {0.0}
    for s in sources:
        if (cell := _cell(s, ctx)) is not None:
            supported |= source_numbers(f"{cell['value']} {cell['row']}")
        elif isinstance(s.get("quote"), str):
            supported |= source_numbers(s["quote"])
    formulas = [(k, rule[k]) for k in ("applies_when", "check") if isinstance(rule.get(k), str)]
    formulas += [("review_when", r["when"]) for r in _list_of_dicts(rule, "review_when") or [] if isinstance(r.get("when"), str)]
    p = []
    for key, text in formulas:
        try:
            missing = [n for n in formula.numbers(text) if not any(abs(n - s) < 1e-9 for s in supported)]
        except FormulaError:
            continue                                         # reported with the formula
        p += [f"number {n:g} in '{key}' isn't written in any cited quote or chart cell" for n in dict.fromkeys(missing)]
    return p


def _unused_number_problems(rule: dict, sources: list[dict], ctx: "Context") -> list[str]:
    """The other direction: every number a cited footnote or law quote states must be used by the rule's
    formulas, or be declared by that source in `not_limits` ({number: why it isn't a limit here}). "(16) But not
    less than 20 ft." with a formula that drops the 20 is then a problem, not a silent false pass. Checked: the
    law (a city code chapter: sources.yaml layout ecode360) and numbered notes ("(16) ..."). Left out: chart
    rows (a row lists every district's number; the rule uses its own column's) and cited cells. Not yet for
    rules the drafting scripts wrote (drafted_by "rule_drafting/..."): their quotes can't declare not_limits yet;
    the drafting job turns it on for them. Not for a flag: it always needs review, and the numbers in its quote
    are the limits it asks a person to apply by hand, shown to them with the quote."""
    if str(rule.get("drafted_by", "")).startswith("rule_drafting/") or rule.get("kind") == "flag":
        return []
    used = [0.0]
    for key in ("applies_when", "check"):
        if isinstance(rule.get(key), str):
            try:
                used += formula.numbers(rule[key])
            except FormulaError:
                return []                                     # reported with the formula
    for r in _list_of_dicts(rule, "review_when") or []:
        if isinstance(r.get("when"), str):
            try:
                used += formula.numbers(r["when"])
            except FormulaError:
                return []
    p = []
    for s in sources:
        declared = s.get("not_limits")
        if declared is not None and not (isinstance(declared, dict) and all(
                type(k) in (int, float) and isinstance(v, str) and v.strip() for k, v in declared.items())):
            p.append(f"source {s.get('file')}: not_limits must map each number to why it isn't a limit here")
            declared = {}
        declared = declared or {}
        quote = s.get("quote")
        if not isinstance(quote, str) or _cell(s, ctx) is not None:
            continue
        law = isinstance(s.get("file"), str) and (ctx.sources.get(s["file"]) or {}).get("layout") == "ecode360"
        if not law and not re.match(r"^\s*\(\d+\)", quote):
            continue                                          # not the law, nor a note: a chart row lists every district
        stated = source_numbers(quote, percent_as_number=False)
        for n in sorted(declared):
            if not any(abs(n - x) < 1e-9 for x in stated):
                p.append(f"source {s.get('file')}: not_limits names {n:g}, which its quote doesn't state")
        for n in sorted(stated):
            if not any(abs(n - u) < 1e-9 for u in used) and not any(abs(n - d) < 1e-9 for d in declared):
                p.append(f"number {n:g} in the quote \"{quote[:60]}…\" is never used by the rule's formulas "
                         "(use it, or declare it in that source's not_limits with why it isn't a limit here)")
    return p


def _cell_source_problems(s: dict, ctx: "Context", district: str | None = None) -> list[str]:
    """A chart cell cited by its page, section, row and district column, exactly as the chart reader read
    it (2_extracted_text/<chart>.cells.jsonl). The cell's value is what's cited; there is no quote. In a
    district's rulebook the cell must be that district's own column; a rulebook for every district
    (`general`) can't cite one district's cell."""
    name, c = s["file"], s.get("cell")
    if district is not None and isinstance(c, dict) and isinstance(c.get("column"), str):
        if district == "general":
            return [f"source {name}: a rule for every district can't cite one district's cell ({c['column']})"]
        if district_name(c["column"]) != district:
            return [f"source {name}: cell column {c['column']} isn't district {district}"]
    if s.keys() != {"file", "page", "cell"}:
        return [f"source {name}: a cell source has exactly file, page and cell (no lines or quote)"]
    if not (isinstance(c, dict) and c.keys() == CELL_FIELDS and all(isinstance(c[k], str) for k in CELL_FIELDS)):
        return [f"source {name}: 'cell' needs section, row and column (text)"]
    if s["page"] not in ctx.sources[name].get("chart_pages", []):
        return [f"source {name}: page {s['page']!r} isn't one of the chart pages read into cells"]
    if name not in ctx.cells:
        return [f"source {name}: no cells file, cell not verified"]
    if _cell(s, ctx) is None:
        return [f"source {name} p.{s['page']}: no cell {c['section']!r} / {c['row']!r} / {c['column']!r} "
                "(or the chart reader couldn't read it with certainty)"]
    return []


def not_quotable(entry: dict) -> str | None:
    """Why a listed document can't be quoted, or None. Fails closed: only `quotable` true or unset
    allows quotes. Shared by validation and the cite helper so they never disagree."""
    if entry.get("quotable", True) is not True:
        return f"isn't quotable yet: {entry.get('not_quotable_because') or 'see sources.yaml'}"
    return None


def _source_entry_problems(entry: dict) -> list[str]:
    """sources.yaml is edited by hand, so its gates must fail closed: no unknown keys (a typo could
    drop a gate), `quotable` is true or false, and a document marked not quotable says why."""
    p = [f"unknown field {k!r} in sources.yaml" for k in entry if k not in SOURCE_FIELDS]
    if "quotable" in entry and not isinstance(entry["quotable"], bool):
        p.append("'quotable' must be true or false")
    if entry.get("quotable") is False and not (isinstance(entry.get("not_quotable_because"), str)
                                               and entry["not_quotable_because"].strip()):
        p.append("marked not quotable but 'not_quotable_because' is missing")
    if "layout" in entry and entry["layout"] not in LAYOUTS:
        p.append(f"'layout' must be one of {sorted(LAYOUTS)}")
    chart_pages = entry.get("chart_pages", [])
    if not (isinstance(chart_pages, list) and all(type(n) is int and n >= 1 for n in chart_pages)
            and len(set(chart_pages)) == len(chart_pages)
            and (type(entry.get("pages")) is not int or all(n <= entry["pages"] for n in chart_pages))):
        p.append("'chart_pages' must be a list of distinct page numbers in the document")
    return p


# A token is a footnote marker ("[fn11]"), a whole word or number ("rear", "1b", "2.5", "1,500", "3/2",
# ".5"), or a single other character ("%", "(", "/", "§"). '.', ',' and '/' join only digit to digit,
# and a leading '.' starts a number only when no letter, digit, '_' or '.' comes right before it ("No.5" is
# "no", ".", "5"), so "minimum/maximum" is three tokens and "3/35" is one.
# Quotes and pages are both split this way, and a quote must match whole tokens, so "5" can never
# match inside "25", "2.5" or "1/2", and "ear" never inside "rear".
TOKEN = re.compile(r"\[fn[^\]\s]*\]|(?:(?<![\w.])\.(?=\d))?[^\W_]+(?:(?<=\d)[.,/](?=\d)[^\W_]+)*|\S")
_UNIFY = str.maketrans("‘’“”–—", "''\"\"--")


def tokenize(text: str) -> list[str]:
    """Lowercase, unify curly quotes and dashes, then split into tokens. Spacing between words doesn't
    matter; spacing inside a number, or around a '.' before a digit ("A.5" vs "A .5"), does."""
    return TOKEN.findall(text.lower().translate(_UNIFY))


def locate(quote: str, page: dict[int, list[str]]) -> list[tuple[int, int]]:
    """Every place the quote occurs on the page, as (first line, last line), one entry per occurrence.
    The quote must be an unbroken run of whole tokens; it may span any number of consecutive lines."""
    q = tokenize(quote)
    line_of = [n for n in sorted(page) for _ in page[n]]
    tokens = [t for n in sorted(page) for t in page[n]]
    return [(line_of[i], line_of[i + len(q) - 1]) for i in range(len(tokens) - len(q) + 1)
            if q and tokens[i:i + len(q)] == q] if q else []


def quote_at(quote: str, page: dict[int, list[str]], first: int, last: int) -> bool:
    """True if the quote occurs exactly once on the page, starting on line `first` and ending on line
    `last`. Unique, so a citation points at one place (a bare "35 ft" on a chart row doesn't qualify)."""
    return locate(quote, page) == [(first, last)]


def approval_hash(entry: dict, ctx: "Context", fields: tuple[str, ...] = APPROVED_FIELDS) -> str:
    """Fingerprint of what an architect approves: the entry's content and the exact versions of the
    documents it cites. Any later edit, or a replaced source PDF, changes it."""
    sources = entry.get("sources")
    cited = sorted({s["file"] for s in sources if isinstance(s, dict) and isinstance(s.get("file"), str)}
                   if isinstance(sources, list) else [])
    approved = {k: entry.get(k) for k in fields} | {
        "source_fingerprints": {f: ctx.sources.get(f, {}).get("sha256") for f in cited}}
    return hashlib.sha256(json.dumps(_canonical(approved)).encode()).hexdigest()


def _canonical(value):
    """A fixed, JSON-safe form of any YAML value, so the fingerprint never depends on key order
    and never fails on odd shapes (mixed key types, dates). 1 and "1" stay different."""
    if isinstance(value, dict):
        items = [[[type(k).__name__, str(k)], _canonical(v)] for k, v in value.items()]
        return {"map": sorted(items, key=lambda kv: json.dumps(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, bytes):  # YAML !!binary
        return {"bytes": value.hex()}
    if isinstance(value, (set, frozenset)):  # YAML !!set: order must not depend on Python's hashing
        return {"set": sorted((_canonical(v) for v in value), key=json.dumps)}
    if isinstance(value, (datetime.date, datetime.datetime)):
        return {"date": value.isoformat()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"can't fingerprint a {type(value).__name__}: {value!r}")


def validate(rulebook, ctx: Context) -> list[str]:
    """Problems with the rules in one file. An empty list means valid.
    (Problems with the sources themselves are in ctx.problems.)"""
    if not isinstance(rulebook, dict) or not rulebook.get("district"):
        return ["file must be a mapping with a 'district'"]
    rules = rulebook.get("rules")
    if not isinstance(rules, list) or not rules:
        return ["'rules' must be a non-empty list"]
    district, problems, seen = rulebook["district"], [], set()
    linked = _relaxes_problems(rules)
    for i, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            problems.append(f"rule #{i}: must be a mapping")
            continue
        rid = rule["id"] if isinstance(rule.get("id"), str) else f"rule #{i}"
        problems += [f"{rid}: {p}" for p in _rule_problems(rule, district, ctx)]
        if rid in seen:
            problems.append(f"{rid}: duplicate id")
        seen.add(rid)
    return problems + linked


def _list_of_dicts(rule, key):
    value = rule.get(key, [])
    return value if isinstance(value, list) and all(isinstance(v, dict) for v in value) else None


def _rule_problems(rule: dict, district: str, ctx: Context) -> list[str]:
    p = [f"unknown field '{k}'" for k in rule.keys() - RULE_FIELDS]
    p += [f"'{k}' must be text" for k in TEXT_FIELDS if k in rule and not isinstance(rule[k], str)]
    if p:
        return p  # later checks rely on these fields being well-formed
    if not str(rule.get("id", "")).startswith(f"{district}."):
        p.append(f"id must start with '{district}.'")
    if rule.get("kind") not in KINDS:
        p.append(f"kind must be one of {KINDS}")
    if rule.get("topic") not in ctx.topics:
        p.append(f"unknown topic {rule.get('topic')!r}")
    title = rule.get("title")
    if not (isinstance(title, str) and title.strip()):
        p.append("missing 'title' (a short label)")
    elif len(title) > TITLE_MAX or len(title.strip().splitlines()) > 1:
        p.append(f"'title' is a one-line label of at most {TITLE_MAX} characters; the rule is its quotes and check")
    if (rule.get("kind") == "rule") != ("check" in rule):
        p.append("a 'rule' needs a 'check'; a 'flag' must not have one")
    review_when, sources, examples = (_list_of_dicts(rule, k) for k in ("review_when", "sources", "examples"))
    for key, value in (("review_when", review_when), ("sources", sources), ("examples", examples)):
        if value is None:
            p.append(f"'{key}' must be a list of mappings")
        for item in value or []:
            p += [f"{key}: unknown field {k!r}" for k in item if k not in ITEM_FIELDS[key]]
    if any("unknown field" in x for x in p):
        return p  # the approval fingerprint and other checks rely on well-formed items

    kinds = ctx.kinds()
    conditions = [rule[k] for k in ("applies_when", "check") if k in rule]
    for r in review_when or []:
        if not (isinstance(r.get("reason"), str) and r["reason"].strip()):
            p.append("each review_when needs a 'reason' (text)")
        conditions.append(r.get("when"))
    for f in conditions:
        if not isinstance(f, str):
            p.append(f"formula must be text, got {f!r}")
            continue
        try:
            if not formula.is_condition(f):
                p.append(f"{f!r} must be a true/false test (a comparison, and/or, or not)")
            elif (name := formula.bare_name(f)) and kinds.get(name) != "boolean":
                p.append(f"{f!r} is just a measure name; only a yes/no measure can be a test on its own")
            unknown = sorted(formula.names(f) - set(kinds))
            p += [f"unknown measure '{n}' in {f!r}" for n in unknown]
            p += _text_problems(f, {"use": ctx.uses, "district": ctx.districts})
            if not unknown:                 # well-typed for every value, or it is no rule (formula.type_of)
                formula.type_of(f, kinds)
        except FormulaError as e:
            p.append(str(e))

    p += _source_problems(sources, ctx, district) if sources is not None else []
    p += _use_row_problems(rule, sources or [], ctx)
    p += _number_problems(rule, sources or [], ctx)
    p += _unused_number_problems(rule, sources or [], ctx)

    expects = {ex.get("expect") for ex in examples or [] if isinstance(ex.get("expect"), str)}
    if rule.get("kind") == "rule" and not {"pass", "fail"} <= expects:
        p.append("a 'rule' needs worked examples that pass and that fail, so its check is really exercised")
    for n, ex in enumerate(examples or [], 1):
        given = ex.get("given")
        if not isinstance(given, dict) or not all(isinstance(k, str) for k in given):
            p.append(f"example {n}: 'given' must be a mapping of measurement names to values")
        elif unknown := sorted(given.keys() - set(kinds)):
            p.append(f"example {n}: unknown measures {unknown}")
        elif wrong := sorted(k for k, v in given.items() if not _fits(kinds[k], v)):
            p.append(f"example {n}: wrong kind of value for {wrong} (see measures.yaml units)")
        elif "use" in given and given["use"] not in ctx.uses:
            p.append(f"example {n}: unknown use {given['use']!r}")
        elif "district" in given and given["district"] not in ctx.districts:
            p.append(f"example {n}: unknown district {given['district']!r}")
        elif ex.get("expect") not in OUTCOMES:
            p.append(f"example {n}: expect must be one of {OUTCOMES}")
        elif not p and (got := outcome(rule, given, ctx.allowed())) != ex["expect"]:
            p.append(f"example {n}: expected {ex['expect']}, got {got}")

    p += _approval_problems(rule, ctx, APPROVED_FIELDS)
    if rule.get("status") == "approved":
        used = set().union(*(formula.names(f) for f in conditions if isinstance(f, str) and _parses(f)))
        p += [f"uses proposed measure '{m}': an engineer must add it to measures.yaml before this can be approved"
              for m in sorted(used & set(ctx.proposed))]
    return p


def _fits(kind: str, value) -> bool:
    """An example value of the right kind: a number, text, or (for a yes/no measure) true/false."""
    return {"number": type(value) in (int, float), "text": type(value) is str, "boolean": type(value) is bool}[kind]


def _parses(text: str) -> bool:
    try:
        formula.parse(text)
        return True
    except FormulaError:
        return False


def _approval_problems(entry: dict, ctx: Context, fields: tuple[str, ...]) -> list[str]:
    p = open_question_problems(entry) + research_problems(entry, ctx) + _answer_problems(entry.get("answers", []), ctx, entry)
    if entry.get("status") not in STATUSES:
        p.append(f"status must be one of {STATUSES}")
    if not entry.get("drafted_by"):
        p.append("missing 'drafted_by'")
    if entry.get("status") == "approved":
        if entry.get("approved_by") not in ctx.reviewers:
            p.append("approved_by must be a reviewer listed in regulations/reviewers.yaml")
        elif isinstance(entry.get("drafted_by"), str) and \
                entry["approved_by"].casefold().strip() == entry["drafted_by"].casefold().strip():
            p.append("can't be approved by the person who drafted it")
        if not isinstance(entry.get("approved_on"), datetime.date):
            p.append("approved_on must be a date (YYYY-MM-DD)")
        if entry.get("approved_hash") != approval_hash(entry, ctx, fields):
            p.append("changed since it was approved, or a cited document was replaced (approved_hash doesn't match); needs re-approval")
    return p


def open_question_problems(entry: dict) -> list[str]:
    """Interpretations the law leaves open, for the architects: a list of text. Nothing with open
    questions can be approved (so the checker never uses it) until the answers are recorded
    in `answers` (question, answer, answered_by, answered_on), which is part of what's approved."""
    questions = entry.get("open_questions", [])
    if not (isinstance(questions, list) and all(isinstance(q, str) and q.strip() for q in questions)):
        return ["'open_questions' must be a list of text"]
    if questions and entry.get("status") == "approved":
        return ["can't be approved while open_questions remain; record the architects' answers first"]
    return []


# Resolve before asking: a question reaches the architects only after the law and the City's practice were
# searched. Each open question carries its `research` (what was searched, what was found, why it is still
# open); a question research settled moves to `findings`: the law's own answer (kind law, quoted and checked
# here) or a reading the sources support (kind reading, as strong as its best source, for someone to confirm).
STRENGTHS = {"strong": 1, "city_practice": 2, "moderate": 3, "weak": 4}   # a reading is as strong as its best source
SOURCE_RANKS = {1: "the city's code or charts", 2: "the City's own interpretations and zoning board (BZA) records",
                3: "the NYS Uniform Code, IBC or IRC and their commentary", 4: "other places' codes"}
PENDING = "pending"     # why_open of a question not researched yet starts with it: "pending the 2026-10-20 research pass"
RESEARCH_FIELDS = {"question", "searched", "sources", "why_open", "readings", "report"}
FINDING_FIELDS = {"id", "question", "kind", "answer", "sources", "strength", "confirm_with", "still_open", "report"}
SLUG = re.compile(r"[a-z][a-z0-9_]*")


def pending_research(question: str, why: str) -> dict:
    """The research entry for a question raised by code (a drafting run): nothing searched yet, and it says so."""
    return {"question": question, "searched": [], "sources": [], "why_open": f"{PENDING}: {why}"}


def _research_source_problems(sources, ctx: Context, where: str) -> tuple[list[str], int | None]:
    """Problems with research sources, and the best (lowest) rank among them. A source is the code itself
    ({file, page, lines, quote}, rank 1, its quote checked like a rule's) or another one: {rank (2-4), cite,
    url?, quote?}, which can't be checked here, so it is named and linked for a person."""
    if not isinstance(sources, list) or not all(isinstance(x, dict) for x in sources):
        return [f"{where}: 'sources' must be a list of sources"], None
    p, ranks = [], []
    for x in sources:
        if "file" in x:
            p += [f"{where}: {m}" for m in _source_problems([x], ctx)]
            ranks.append(1)
        elif x.keys() - {"rank", "cite", "url", "quote"} or not ({"rank", "cite"} <= x.keys()):
            p.append(f"{where}: a source is the code ({{file, page, lines, quote}}) or {{rank, cite, url?, quote?}}")
        elif x["rank"] not in (2, 3, 4):
            p.append(f"{where}: rank must be 2, 3 or 4 ({'; '.join(f'{k} = {v}' for k, v in SOURCE_RANKS.items())}); "
                     "the code itself is cited by file, page, lines and quote")
        elif not (isinstance(x["cite"], str) and x["cite"].strip()):
            p.append(f"{where}: 'cite' must say what the source is")
        elif "url" in x and not (isinstance(x["url"], str) and x["url"].startswith("https://")):
            p.append(f"{where}: 'url' must be an https:// link")
        else:
            ranks.append(x["rank"])
    return p, min(ranks, default=None)


def _report_problems(item: dict, where: str) -> list[str]:
    """`report`: the research report it came from, "docs/research/<file>.md §<section>"; the file must exist."""
    if "report" not in item:
        return []
    path, _, section = item["report"].partition(" §") if isinstance(item["report"], str) else (None, "", "")
    if not path or not (REPO / path).is_file():
        return [f"{where}: 'report' must name a research report in the repository, like "
                "'docs/research/2026-10-20_architect_questions.md §2.1'"]
    if section and not re.search(rf"^#+ {re.escape(section)}[ .]", (REPO / path).read_text(encoding="utf-8"), re.M):
        return [f"{where}: {path} has no section {section} (a heading like '### {section} ...')"]
    return []


def research_problems(entry: dict, ctx: Context) -> list[str]:
    """Show your work: every open question has exactly one `research` entry, {question (its exact text),
    searched (the piece ids of the law read for it), sources, why_open, report?}; `searched` may be empty only
    while why_open says it is pending. Each of `findings` is {question, kind, answer, sources, strength?,
    confirm_with?, report?}: kind law is answered by the code's own words (a quote, checked; strength strong),
    kind reading by sources that support it (strength no higher than its best source; confirm_with says who
    should confirm it). A finding's question can't still be open."""
    questions = entry.get("open_questions", [])
    questions = [q for q in questions if isinstance(q, str)] if isinstance(questions, list) else []  # shape: above
    research, findings = entry.get("research", []), entry.get("findings", [])
    if not (isinstance(research, list) and all(isinstance(x, dict) for x in research)):
        return ["'research' must be a list of {question, searched, sources, why_open}"]
    if not (isinstance(findings, list) and all(isinstance(x, dict) for x in findings)):
        return ["'findings' must be a list of {question, kind, answer, sources, ...}"]
    p, covered = [], [x.get("question") for x in research]
    for q in questions:
        if covered.count(q) != 1:
            p.append(f"open question {q[:70]!r}{'...' if len(q) > 70 else ''} needs exactly one 'research' entry "
                     "(searched: the sections read for it; sources; why_open: why the law and practice don't settle "
                     f"it, or '{PENDING} ...' until it is researched)")
    for x in research:
        where = f"research on {str(x.get('question'))[:50]!r}"
        if x.keys() - RESEARCH_FIELDS or not ({"question", "searched", "sources", "why_open"} <= x.keys()):
            p.append(f"{where}: needs exactly question, searched, sources, why_open (and report, if any)")
            continue
        if x["question"] not in questions:
            p.append(f"{where}: isn't one of the open questions (answered? move what was found to 'findings')")
        if not (isinstance(x["why_open"], str) and x["why_open"].strip()):
            p.append(f"{where}: 'why_open' must say why the question is still open")
            continue
        pending = x["why_open"].startswith(PENDING)
        searched = x["searched"]
        if not (isinstance(searched, list) and all(isinstance(i, str) for i in searched)):
            p.append(f"{where}: 'searched' must be a list of piece ids")
        elif not searched and not pending:
            p.append(f"{where}: 'searched' lists no sections; list what was read, or say why_open: '{PENDING} ...'")
        elif ctx.pieces and (unknown := [i for i in searched if i not in ctx.pieces]):
            p.append(f"{where}: searched pieces that don't exist: {', '.join(unknown)}")
        p += _research_source_problems(x["sources"], ctx, where)[0] + _report_problems(x, where)
        # The readings still in play, for the measurement code to compute every one: a design complies only if
        # it passes under all of them, fails only if it fails under all of them, and otherwise needs review.
        readings = x.get("readings", [])
        if not (isinstance(readings, list) and all(isinstance(g, dict) and g.keys() == {"id", "reading"}
                                                   and isinstance(g["id"], str) and SLUG.fullmatch(g["id"])
                                                   and isinstance(g["reading"], str) and g["reading"].strip()
                                                   for g in readings)):
            p.append(f"{where}: 'readings' must be a list of {{id (lowercase_with_underscores), reading (text)}}")
        elif len({g["id"] for g in readings}) != len(readings):
            p.append(f"{where}: each reading's id is used once")
        elif len(readings) == 1:
            p.append(f"{where}: one reading isn't open; list two or more, or record it as a finding")
    ids = [x.get("id") for x in findings if isinstance(x, dict) and "id" in x]
    if len(set(ids)) != len(ids):
        p.append("each finding's id is used once")
    for x in findings:
        where = f"finding on {str(x.get('question'))[:50]!r}"
        if x.keys() - FINDING_FIELDS or not ({"question", "kind", "answer", "sources"} <= x.keys()):
            p.append(f"{where}: needs question, kind, answer, sources (and strength, confirm_with, report)")
            continue
        if x["question"] in questions:
            p.append(f"{where}: the question is still in open_questions; a question is open or found, not both")
        if "id" in x and not (isinstance(x["id"], str) and SLUG.fullmatch(x["id"])):
            p.append(f"{where}: 'id' (what measurement code calls it) is lowercase_with_underscores")
        if not (isinstance(x["answer"], str) and x["answer"].strip()):
            p.append(f"{where}: 'answer' must be text")
        problems, best = _research_source_problems(x["sources"], ctx, where)
        p += problems + _report_problems(x, where)
        if x["kind"] == "law":
            if not (isinstance(x["sources"], list) and any(isinstance(s, dict) and "file" in s for s in x["sources"])):
                p.append(f"{where}: an answer from the law quotes the law (a source with file, page, lines, quote)")
            if x.get("strength", "strong") != "strong":
                p.append(f"{where}: an answer from the law is strong; a weaker one is a reading")
        elif x["kind"] == "reading":
            if x.get("strength") not in STRENGTHS:
                p.append(f"{where}: a reading's 'strength' must be one of {', '.join(STRENGTHS)}")
            elif best is not None and STRENGTHS[x["strength"]] < best:
                p.append(f"{where}: strength {x['strength']!r} is stronger than its best source (rank {best}: "
                         f"{SOURCE_RANKS[best]})")
            elif best is None:
                p.append(f"{where}: a reading needs at least one valid source")
            if not (isinstance(x.get("confirm_with"), str) and x["confirm_with"].strip()):
                p.append(f"{where}: a reading says who should confirm it ('confirm_with')")
        else:
            p.append(f"{where}: 'kind' must be law or reading")
    return p


# Definitions (4_term_definitions/definitions.yaml) and use names (uses.yaml): each entry is
# keyed by its id and cites the city's exact words, like a rule does.
TERM_SCHEMAS = {
    # "id" is the entry's key in the file: rules refer to terms by it, so renaming one needs re-approval.
    # A definition is the city's own words (whole sentences in `sources`), with no paraphrase: restating a
    # definition kept dropping limiting words. Interpretations are open_questions until an architect
    # answers; the answers are part of what's approved, so the measurement code follows a frozen record.
    "definitions": {"label": "term", "approved": ("id", "term", "measures", "sources", "findings", "answers"),
                    "fields": {"term", "measures", "sources", "open_questions", "research", "findings", "answers",
                               "notes"}},
    "uses": {"label": "name", "approved": ("id", "name", "sources"), "fields": {"name", "sources", "notes"}},
}
APPROVAL_FIELDS = {"drafted_by", "status", "approved_by", "approved_on", "approved_hash"}


def _pickable(entry: dict, question) -> set:
    """What an answer to `question` may pick: that question's research readings' ids, or the id of the finding
    that answers that same question (never a finding about another question)."""
    ids = {f.get("id") for f in entry.get("findings") or [] if isinstance(f, dict) and f.get("question") == question}
    for x in entry.get("research") or []:
        if isinstance(x, dict) and x.get("question") == question:
            ids |= {g.get("id") for g in x.get("readings") or [] if isinstance(g, dict)}
    return ids - {None}


def _answer_problems(answers, ctx: Context, entry: dict | None = None) -> list[str]:
    """Architects' (or the City's) answers to open questions: [{question, answer, answered_by, answered_on,
    reading?}]. `reading` is the id of the reading the answer picks (one of the question's research readings,
    or a finding's id it confirms): the measuring code then measures only that reading
    (model_measurement/interpretations.py). An answer outranks Gordium's reading. The question stays listed
    with its research (and its readings) until the entry is approved, so `reading` is checked against them."""
    entry = entry if isinstance(entry, dict) else {}
    if not (isinstance(answers, list) and all(isinstance(a, dict) for a in answers)):
        return ["'answers' must be a list of {question, answer, answered_by, answered_on}"]
    p = []
    for a in answers:
        if a.keys() - {"reading"} != {"question", "answer", "answered_by", "answered_on"}:
            p.append("each answer needs exactly question, answer, answered_by, answered_on (and reading, if any)")
        elif "reading" in a and not (isinstance(a["reading"], str) and SLUG.fullmatch(a["reading"])):
            p.append("an answer's 'reading' names the reading (or finding) it picks, by its id "
                     "(lowercase_with_underscores), so the measuring code follows it")
        elif "reading" in a and a["reading"] not in _pickable(entry, a.get("question")):
            p.append(f"an answer's 'reading' {a['reading']!r} isn't one of its question's research readings or one of "
                     "this entry's findings")
        elif not all(isinstance(a[k], str) and a[k].strip() for k in ("question", "answer", "answered_by")):
            p.append("an answer's question, answer and answered_by must be text")
        elif a["answered_by"] not in ctx.reviewers:
            p.append(f"answered_by must be a reviewer in regulations/reviewers.yaml, not {a['answered_by']!r}")
        elif not isinstance(a["answered_on"], datetime.date):
            p.append("answered_on must be a date (YYYY-MM-DD)")
    return p


def validate_terms(entries, ctx: Context, schema: str) -> list[str]:
    """Problems with a definitions or uses file. An empty list means valid."""
    s = TERM_SCHEMAS[schema]
    if not isinstance(entries, dict) or not entries:
        return ["file must be a non-empty mapping of id -> entry"]
    problems = []
    for key, entry in entries.items():
        if not (isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]*", key)):
            problems.append(f"{key!r}: ids are lowercase_with_underscores")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{key}: must be a mapping")
            continue
        p = [f"unknown field '{k}'" for k in entry.keys() - s["fields"] - APPROVAL_FIELDS]
        p += [f"'{k}' must be text" for k in (s["label"], "drafted_by", "status", "approved_by")
              if k in entry and not isinstance(entry[k], str)]
        if p:
            problems += [f"{key}: {x}" for x in p]
            continue
        if not entry.get(s["label"]):
            p.append(f"missing '{s['label']}'")
        measures = entry.get("measures", [])
        if not (isinstance(measures, list) and all(isinstance(m, str) for m in measures)):
            p.append("'measures' must be a list of measure names")
        else:
            p += [f"unknown measure '{m}'" for m in measures if m not in ctx.measures]
        sources = _list_of_dicts(entry, "sources")
        p += ["'sources' must be a list of mappings"] if sources is None else _source_problems(sources, ctx)
        p += _approval_problems(entry | {"id": key}, ctx, s["approved"])
        problems += [f"{key}: {x}" for x in p]
    return problems


def _source_problems(sources: list[dict], ctx: Context, district: str | None = None) -> list[str]:
    """Problems with sources. district: the rulebook a rule is in, so a cited cell must be its own column."""
    if not sources:
        return ["needs at least one source"]
    p = []
    for s in sources:
        name, page, lines, quote = s.get("file"), s.get("page"), s.get("lines"), s.get("quote")
        if not isinstance(name, str) or name not in ctx.sources:
            p.append(f"source file {name!r} is not in sources.yaml")
        elif reason := not_quotable(ctx.sources[name]):
            p.append(f"source {name} {reason}")
        elif name in ctx.file_problems:
            p.append(f"source {name} has problems: {'; '.join(ctx.file_problems[name])}")
        elif "cell" in s:
            p += _cell_source_problems(s, ctx, district)
        elif not (type(page) is int and isinstance(quote, str) and tokenize(quote) and _is_line_range(lines)):
            p.append(f"source {name}: needs 'page' (number), 'lines' ([first, last]) and 'quote' (text)")
        elif "…" in quote or "..." in quote:
            p.append(f"source {name}: a quote is one exact passage; cite separate passages as separate sources")
        elif name not in ctx.pages:
            p.append(f"source {name}: no extracted text, quote not verified")
        elif page not in ctx.pages[name]:
            p.append(f"source {name}: page {page} does not exist")
        elif not quote_at(quote, ctx.pages[name][page], *lines):
            found = locate(quote, ctx.pages[name][page])
            at = ", ".join(f"{a}-{b}" for a, b in found)
            if len(found) > 1:
                p.append(f"source {name} p.{page}: quote appears {len(found)} times (lines {at}); "
                         f"quote more words so it's unique: {quote!r}")
            else:
                p.append(f"source {name} p.{page}: quote isn't at lines {lines[0]}-{lines[1]}"
                         f"{f'; it is at lines {at}' if found else '; not on this page'}: {quote!r}")
    return p


# ---- one file's checks, shared by `python -m rule_format` and everything that uses a rulebook -----------

def research_entries(jurisdiction) -> list[tuple[str, dict]]:
    """(where, entry) for every entry that can hold open questions: definitions, rules (5_zoning_rules) and
    section labels. `where` names it for a message ("definitions.yaml story", "R-1b.yaml R-1b.height")."""
    j = Path(jurisdiction)
    out = []
    definitions = j / "4_term_definitions/definitions.yaml"
    if definitions.exists():
        out += [(f"definitions.yaml {k}", e) for k, e in (load(definitions) or {}).items() if isinstance(e, dict)]
    # Named by the path under 5_zoning_rules/, so the AI-drafted drafted/R-1b.yaml is never taken for the hand R-1b.yaml
    # (the two share rule ids, like R-1b.use, and one's open questions mustn't be charged to the other's findings).
    for path in rulebook_paths(j / "5_zoning_rules"):
        name = path.relative_to(j / "5_zoning_rules").as_posix()
        out += [(f"{name} {r.get('id')}", r) for r in (load(path) or {}).get("rules") or [] if isinstance(r, dict)]
    for path in sorted((j / "3_section_labels").glob("*.yaml")):
        book = load(path) or {}
        out += [(f"{path.name} {k}", e) for k, e in (book.get("labels") or {}).items() if isinstance(e, dict)]
    return out


def _quoted_phrases(text: str) -> list[list[str]]:
    """The tokens of each phrase a question quotes ("at any point"), three words or more."""
    return [t for t in (tokenize(m) for m in re.findall(r'["\u201c]([^"\u201d]+)["\u201d]', text)) if len(t) >= 3]


def _contains(tokens: list[str], part: list[str]) -> bool:
    return any(tokens[i:i + len(part)] == part for i in range(len(tokens) - len(part) + 1))


def open_question_tags(entries: list[tuple[str, dict]]) -> dict[str, tuple[str, str, dict]]:
    """{"<id>#<n>": (where, question, its research)}: the n-th open question of each entry, the tags the questions
    page and the spreadsheet use (where ends with the entry's id)."""
    tags = {}
    for where, e in entries:
        for n, q in enumerate(q for q in e.get("open_questions") or [] if isinstance(q, str)):
            x = next((r for r in e.get("research") or [] if isinstance(r, dict) and r.get("question") == q), {})
            tags[f"{where.rsplit(' ', 1)[-1]}#{n + 1}"] = (where, q, x)
    return tags


def _overlap(a: dict, b: dict) -> bool:
    return (isinstance(a, dict) and isinstance(b, dict) and "file" in a and "file" in b
            and (a.get("file"), a.get("page")) == (b.get("file"), b.get("page"))
            and _is_line_range(a.get("lines")) and _is_line_range(b.get("lines"))
            and a["lines"][0] <= b["lines"][1] and b["lines"][0] <= a["lines"][1])


def finding_conflicts(entries: list[tuple[str, dict]]) -> list[str]:
    """A question is settled or open, never both, across every rule, definition and label. A finding may touch
    what an open question still asks only by saying so, in `still_open: ["<id>#<n>", ...]` (each a real open
    question, and the answer says what is still open). Touching means: the open question quotes words the
    finding quotes, or its research cites lines the finding cites (in any entry). And in an entry that still has
    open questions, every finding carries `still_open` (an empty list when it leaves none of them open), so the
    relation is stated on purpose, never guessed from words like "eave"."""
    tags = open_question_tags(entries)
    p = []
    for where, e in entries:
        own = {t for t, (w, _, _) in tags.items() if w == where}
        for f in e.get("findings") or []:
            if not isinstance(f, dict):
                continue
            name = f"{where}: the finding {f.get('id') or str(f.get('question', ''))[:40]!r}"
            listed = f.get("still_open", [])
            if not (isinstance(listed, list) and all(isinstance(t, str) for t in listed)):
                p.append(f"{name}: 'still_open' must be a list of open-question tags like '325-25C#1'")
                continue
            if unknown := [t for t in listed if t not in tags]:
                p.append(f"{name}: still_open names {', '.join(unknown)}, which isn't an open question "
                         "(answered or renumbered?)")
            if listed and "still open" not in str(f.get("answer", "")):
                p.append(f"{name}: lists still_open questions, so its answer must say what is still open")
            if own and "still_open" not in f:
                p.append(f"{name}: its entry still has open questions ({', '.join(sorted(own))}), so it says which "
                         "of them it leaves open: still_open: [...] (or [] for none)")
            code = [c for c in f.get("sources") or [] if isinstance(c, dict) and "file" in c and isinstance(c.get("quote"), str)]
            quoted = [tokenize(c["quote"]) for c in code]
            for tag, (owhere, q, x) in tags.items():
                if tag in listed:
                    continue
                same = [ph for ph in _quoted_phrases(q) if any(_contains(t, ph) for t in quoted)]
                shared = [c for c in code if any(_overlap(c, s) for s in x.get("sources") or [])]
                if same or shared:
                    why = (f"quotes {' '.join(same[0])!r}, which the open question {tag} asks about" if same else
                           f"cites p.{shared[0]['page']} lines {shared[0]['lines'][0]}-{shared[0]['lines'][1]}, which "
                           f"the research on open question {tag} cites")
                    p.append(f"{name} {why} ({owhere}: {q[:50]}...): narrow the finding to what is settled and name "
                             f"the question in still_open: [{tag!r}], or make it a reading")
    return p


def term_file_problems(jurisdiction, ctx: Context) -> dict[Path, list[str]]:
    """Each term file (4_term_definitions/<schema>.yaml) that exists, with its problems."""
    found = {}
    for schema in TERM_SCHEMAS:
        path = Path(jurisdiction) / "4_term_definitions" / f"{schema}.yaml"
        if path.exists():
            try:
                found[path] = validate_terms(load(path), ctx, schema)
            except Exception as e:  # reported, never raised: one broken file mustn't hide the rest
                found[path] = [f"validator error ({type(e).__name__}: {e})"]
    return found


def rulebook_file_problems(path, ctx: Context) -> list[str]:
    """Everything wrong with one rulebook file: it can be read, passes `validate`, and its district is its
    file name."""
    path = Path(path)
    try:
        book = load(path)
        problems = validate(book, ctx)
        if isinstance(book, dict) and book.get("district") != path.stem:
            problems.append(f"district {book.get('district')!r} doesn't match the file name {path.stem!r}")
        return problems
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        return [f"can't read file ({type(e).__name__}: {e})"]
    except Exception as e:  # reported, never raised: one broken file mustn't hide the rest
        return [f"validator error ({type(e).__name__}: {e})"]
