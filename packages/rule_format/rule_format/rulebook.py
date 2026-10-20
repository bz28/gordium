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
               "notes", "open_questions", "answers", "drafted_by", "status", "approved_by", "approved_on",
               "approved_hash"}
TEXT_FIELDS = ("id", "kind", "topic", "title", "drafted_by", "status", "approved_by")
TITLE_MAX = 80                                    # a label, one line: long enough to name, too short to retell
ITEM_FIELDS = {"review_when": {"when", "reason"}, "sources": {"file", "page", "lines", "quote", "cell"},
               "examples": {"given", "expect", "note"}}
CELL_FIELDS = {"section", "row", "column"}   # a chart cell source: {file, page, cell: {section, row, column}}
APPROVED_FIELDS = ("id", "kind", "topic", "title", "applies_when", "check", "review_when", "sources", "answers")
UNIT_KINDS = {"text": "text", "yes_no": "boolean"}       # every other unit (ft, sf, count) is a number
MEASURE_KINDS = {name: UNIT_KINDS.get(m["unit"], "number") for name, m in yaml.safe_load(MEASURES_FILE.read_text()).items()}
# Measures a draft asked for that aren't in measures.yaml yet: listed for engineers, never used silently.
PROPOSED_MEASURES = "5_zoning_rules/drafted/records/proposed_measures.yaml"


def outcome(rule: dict, values: dict, allowed: dict[str, set]) -> str:
    """allowed: the values each text measure may take, e.g. {"use": the city's use names}.
    Required, so no caller can forget it. A value outside the list, or a text measure with
    no list, is unrecognized, so the rule needs review. A measure that isn't in measures.yaml (one a
    draft proposed) is described here by its kind instead: "number" or "boolean"."""
    kinds = MEASURE_KINDS | {k: v if isinstance(v, str) else frozenset(v) for k, v in allowed.items()}
    try:
        if "applies_when" in rule and not _condition(rule["applies_when"], values, kinds):
            return "not_applicable"
        if rule["kind"] == "flag":
            return "needs_review"
        if any(_condition(r["when"], values, kinds) for r in rule.get("review_when", [])):
            return "needs_review"
        return "pass" if _condition(rule["check"], values, kinds) else "fail"
    except (MissingMeasure, EvaluationError, ArithmeticError):
        return "needs_review"


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
    return yaml.load(Path(path).read_text(), Loader=_StrictLoader)


def rulebook_paths(folder) -> list[Path]:
    """The rulebook files in a folder (5_zoning_rules/, an answer-key folder): every .yaml or .yml file
    under it, except the drafting script's own run records (drafted/records/), which aren't rulebooks. The one
    definition, used by the validator, the review list and the spreadsheet export alike."""
    folder = Path(folder)
    return sorted(p for p in folder.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file()
                  and "records" not in p.relative_to(folder).parts) if folder.is_dir() else []


def rulebook_for(jurisdiction, zone: str) -> Path | None:
    """The rulebook that holds a zone's rules: the hand-drafted 5_zoning_rules/<zone>.yaml when it exists,
    else the AI-drafted 5_zoning_rules/drafted/<zone>.yaml, else None. The one definition, used by the
    project report and the answer-key test alike."""
    folder = Path(jurisdiction) / "5_zoning_rules"
    return next((p for p in (folder / f"{zone}.yaml", folder / "drafted" / f"{zone}.yaml") if p.is_file()), None)


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
    for i, rule in enumerate(rules, 1):
        if not isinstance(rule, dict):
            problems.append(f"rule #{i}: must be a mapping")
            continue
        rid = rule["id"] if isinstance(rule.get("id"), str) else f"rule #{i}"
        problems += [f"{rid}: {p}" for p in _rule_problems(rule, district, ctx)]
        if rid in seen:
            problems.append(f"{rid}: duplicate id")
        seen.add(rid)
    return problems


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
            p += [f"unknown measure '{n}' in {f!r}" for n in sorted(formula.names(f) - set(kinds))]
            p += _text_problems(f, {"use": ctx.uses, "district": ctx.districts})
        except FormulaError as e:
            p.append(str(e))

    p += _source_problems(sources, ctx, district) if sources is not None else []
    p += _use_row_problems(rule, sources or [], ctx)
    p += _number_problems(rule, sources or [], ctx)

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
    p = open_question_problems(entry) + _answer_problems(entry.get("answers", []), ctx)
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


# Definitions (4_term_definitions/definitions.yaml) and use names (uses.yaml): each entry is
# keyed by its id and cites the city's exact words, like a rule does.
TERM_SCHEMAS = {
    # "id" is the entry's key in the file: rules refer to terms by it, so renaming one needs re-approval.
    # A definition is the city's own words (whole sentences in `sources`), with no paraphrase: restating a
    # definition kept dropping limiting words. Interpretations are open_questions until an architect
    # answers; the answers are part of what's approved, so the measurement code follows a frozen record.
    "definitions": {"label": "term", "approved": ("id", "term", "measures", "sources", "answers"),
                    "fields": {"term", "measures", "sources", "open_questions", "answers", "notes"}},
    "uses": {"label": "name", "approved": ("id", "name", "sources"), "fields": {"name", "sources", "notes"}},
}
APPROVAL_FIELDS = {"drafted_by", "status", "approved_by", "approved_on", "approved_hash"}


def _answer_problems(answers, ctx: Context) -> list[str]:
    """Architects' answers to open questions: [{question, answer, answered_by, answered_on}]."""
    if not (isinstance(answers, list) and all(isinstance(a, dict) for a in answers)):
        return ["'answers' must be a list of {question, answer, answered_by, answered_on}"]
    p = []
    for a in answers:
        if a.keys() != {"question", "answer", "answered_by", "answered_on"}:
            p.append("each answer needs exactly question, answer, answered_by, answered_on")
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
