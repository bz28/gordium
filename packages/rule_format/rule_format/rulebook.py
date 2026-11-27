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
import itertools
import json
import os
import pickle
import re
import sys
import threading
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import formula, parts
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
               "approved_hash", "revised", *parts.PART_FIELDS}
# A drafted rule changed after the AI's draft says so, oldest first, as a label does (labels.py): one entry per
# field changed, {field, by, date, why}; a rule added whole after the AI's draft is {field: rule, by, date, why}.
# The AI's own answer stays in the run record (and drafted/records/as_drafted/), so every difference is explained.
REVISED_FIELDS = (RULE_FIELDS - {"id", "revised", "drafted_by", "status", "approved_by", "approved_on",
                                 "approved_hash"}) | {"rule"}
TEXT_FIELDS = ("id", "kind", "topic", "title", "drafted_by", "status", "approved_by")
TITLE_MAX = 80                                    # a label, one line: long enough to name, too short to retell
ITEM_FIELDS = {"review_when": {"when", "reason"}, "sources": {"file", "page", "lines", "quote", "cell", "not_limits"},
               "examples": {"given", "expect", "note", "drafted_check", *parts.EXAMPLE_FIELDS}}
CELL_FIELDS = {"section", "row", "column"}   # a chart cell source: {file, page, cell: {section, row, column}}
APPROVED_FIELDS = ("id", "kind", "topic", "title", "applies_when", "check", "review_when", "sources", "findings",
                   "answers")
UNIT_KINDS = {"text": "text", "yes_no": "boolean"}       # every other unit (ft, sf, count) is a number
MEASURE_KINDS = {name: UNIT_KINDS.get(m["unit"], "number") for name, m in yaml.safe_load(MEASURES_FILE.read_text(encoding="utf-8")).items()}
# Measures a draft asked for that aren't in measures.yaml yet: listed for engineers, never used silently.
PROPOSED_MEASURES = "drafted/records/proposed_measures.yaml"   # under the folder's rulebooks (rules_folder)


def needed_by_problems(proposed: Path, rulebooks: list) -> list[str]:
    """A proposed measure's `needed_by` must name exactly the rules whose applies_when, check or review_when read it
    (worked out from their formulas), so the list can't drift from the rules (review round 2, 2026-11-23)."""
    listed = load(proposed) or {}
    reads: dict[str, set] = {}
    for path in rulebooks:
        for r in (load(path) or {}).get("rules") or []:
            if not isinstance(r, dict):
                continue
            texts = [r.get("applies_when"), r.get("check")] + [w.get("when") for w in r.get("review_when") or []
                                                                if isinstance(w, dict)]
            for t in texts:
                if isinstance(t, str):
                    try:
                        names = formula.names(t)
                    except formula.FormulaError:
                        continue
                    for n in names & set(listed):
                        reads.setdefault(n, set()).add(r.get("id"))
    out = []
    for name, m in listed.items():
        got = set(m.get("needed_by") or []) if isinstance(m, dict) else set()
        want = reads.get(name, set())
        if got - want:
            out.append(f"{name}: needed_by names {sorted(got - want)}, which don't read it")
        if want - got:
            out.append(f"{name}: needed_by misses {sorted(want - got)}, which read it")
    return out


def _listed_values(record: dict) -> set:
    """The text values a proposed text measure's record lists (`values:`, each a text), else none."""
    values = record.get("values")
    return {v for v in values if isinstance(v, str)} if isinstance(values, list) else set()


def outcome(rule: dict, values: dict, allowed: dict[str, set]) -> str:
    """allowed: the values each text measure may take, e.g. {"use": the city's use names}.
    Required, so no caller can forget it. A value outside the list, or a text measure with
    no list, is unrecognized. A measure that isn't in measures.yaml (one a draft proposed) is described here by
    its kind instead: "number" or "boolean". A missing or unusable measure is unknown: the result is pass or fail
    only if it is the same whatever that measure turns out to be (three-valued logic, formula.evaluate); else
    needs review. A rule for each part (for_each: parts.py) has no one answer for the whole building: needs review
    here, so code that doesn't know about parts can never pass one (its rows: parts.rows)."""
    if parts.is_part_rule(rule):
        return "needs_review"
    return _outcome(rule, values, allowed)


def _kinds(allowed: dict, extra: dict | None = None) -> dict:
    """What every measure is (formula.evaluate's kinds): measures.yaml's, then `extra` (a part's measures), then
    `allowed` (the text values a text measure may take, or a proposed measure's kind)."""
    return MEASURE_KINDS | (extra or {}) | {k: v if isinstance(v, str) else frozenset(v) for k, v in allowed.items()}


def _outcome(rule: dict, values: dict, allowed: dict[str, set], extra: dict | None = None) -> str:
    """outcome() itself, for one set of values: the whole building's, or (parts.part_outcome) one part's, with
    `extra` describing the part's own measures."""
    kinds = _kinds(allowed, extra)
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


def unknown_settings(rule: dict, unknown: list[str], kinds: dict) -> list[dict] | None:
    """The settings the "fails whatever the missing number is" proof (decided 2026-10-21) tries for these unknown
    measures, or None when it can't be made. A rule with a check; no unknown measure in its applies_when or
    review_when; each unknown a number the check is provably truest at when it is 0 (formula.truth_direction -1,
    taken at 0: measures are never negative) or a yes/no fact (tried both ways); anything else, None. A rule that
    fails under every setting fails whatever the unknowns are. Used by the checker's rows (check.fails_whatever) and
    by each part's row (parts.rows): one proof, so it means the same for both."""
    if rule.get("kind") != "rule" or not rule.get("check"):
        return None
    side = formula.names(rule["applies_when"]) if rule.get("applies_when") else set()
    for r in rule.get("review_when") or []:
        side |= formula.names(r["when"])
    if not unknown or any(n in side for n in unknown):
        return None
    numbers = [n for n in unknown if kinds.get(n) == "number"]
    yes_no = [n for n in unknown if kinds.get(n) == "boolean"]
    if len(numbers) + len(yes_no) != len(unknown) or any(
            formula.truth_direction(rule["check"], n) != -1 for n in numbers):
        return None
    return [{**{n: 0 for n in numbers}, **dict(zip(yes_no, ways))}
            for ways in itertools.product((False, True), repeat=len(yes_no))]


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
    """A YAML file (a rulebook, a term file, sources.yaml...) read with the strict loader. Kept by its bytes
    (_kept): re-read every call, parsed again only when its bytes changed, a fresh copy every time."""
    return load_bytes(Path(path).read_bytes())


def load_bytes(data: bytes):
    """load(), for a file's bytes already read (check.options reads each file once, and works from those bytes)."""
    def parse(data: bytes):
        text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")   # exactly as read_text() reads it
        return yaml.load(text, Loader=_StrictLoader)
    return _kept("yaml", data, parse)


def _kept(kind: str, data: bytes, build):
    """build(data), worked out once per exact content. Reading a file is fast; parsing it is the slow part
    (pure-Python YAML: ~20 ms for a rulebook, and one check reads about twenty files; the extracted text is
    ~35 ms more to split into words), and a check is run hundreds of times while an architect edits.

    Never stale: the key is the SHA-256 of the bytes just read (never the file's name or date), so a file whose
    bytes changed in any way is worked out again. Never shared: what is kept is the result pickled (bytes, which
    nothing can change), and every call un-pickles a fresh copy, so a caller that edits what it got can't change
    what the next caller gets. A file that fails to read or parse is never kept: the same error every time.
    `kind` keeps different readings of the same bytes apart."""
    key = (kind, hashlib.sha256(data).digest())
    with _KEPT_LOCK:
        frozen = _KEPT.get(key)
        if frozen is not None:
            _KEPT.move_to_end(key)
    if frozen is None:
        frozen = pickle.dumps(build(data), protocol=pickle.HIGHEST_PROTOCOL)
        with _KEPT_LOCK:
            _KEPT[key] = frozen
            while len(_KEPT) > _KEPT_MAX:
                _KEPT.popitem(last=False)            # the least recently used goes first
    return pickle.loads(frozen)


_KEPT: "OrderedDict[tuple[str, bytes], bytes]" = OrderedDict()   # (kind, SHA-256 of the bytes) -> result, pickled
_KEPT_LOCK = threading.Lock()                        # the Rhino command may check from more than one thread
_KEPT_MAX = 256                                      # results kept; a test run writing many temp files stays bounded


def rulebook_paths(folder) -> list[Path]:
    """The rulebook files in a folder (5_zoning_rules/, an answer-key folder): every .yaml or .yml file
    under it, except the drafting script's own run records (drafted/records/), which aren't rulebooks. The one
    definition, used by the validator, the review list and the spreadsheet export alike."""
    folder = Path(folder)
    # Sorted by the path as written ("/", case kept), the same on every computer: Windows paths sort ignoring case.
    return sorted((p for p in folder.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file()
                   and "records" not in p.relative_to(folder).parts),
                  key=lambda p: p.relative_to(folder).as_posix()) if folder.is_dir() else []


def rulebook_for(jurisdiction, zone: str, exists=Path.is_file) -> Path | None:
    """The rulebook that holds a zone's rules: the hand-drafted 5_zoning_rules/<zone>.yaml when it exists,
    else the AI-drafted 5_zoning_rules/drafted/<zone>.yaml, else None. The one definition, used by the
    project report and the answer-key test alike. `exists(path)`: whether a file is there, on disk unless the caller
    decides from what it has already read (check.options, from the files it read once)."""
    folder = Path(jurisdiction) / "5_zoning_rules"
    return next((p for p in (folder / f"{zone}.yaml", folder / "drafted" / f"{zone}.yaml") if exists(p)), None)


def utf8_console() -> None:
    """Print in UTF-8, whatever the computer's code page: on Windows a command's output sent to a file, a pipe or CI
    is cp1252, which can't print ✓ or ✗ (the command crashed). Every command line calls this first."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").replace("-", "").lower() != "utf8":
            stream.reconfigure(encoding="utf-8")


def read_jsonl(path) -> list[dict]:
    """Every row of a JSON-lines file, read as UTF-8, blank lines skipped. The one reader of the repository's
    .jsonl files (extracted text, sections, run records), so every package reads the same bytes the same way."""
    return _jsonl_rows(Path(path).read_bytes())


def _jsonl_rows(data: bytes) -> list[dict]:
    """read_jsonl for bytes already read: decoded and split exactly as read_text(encoding="utf-8") would."""
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# A state's own law folder, regulations/jurisdictions/<state>/<name>/, holds law every place in that state inherits
# (New York's Residential Code). It has the same numbered steps as a place, but its settings file is state.yaml, not
# jurisdiction.yaml: it is no place (no boundary, no lot lookup), so the place registry and the Rhino plugin's "one
# place" never see it. A place names the state folders it inherits in its jurisdiction.yaml `inherits:` (place.py).
# Decided 2026-11-12: docs/decisions/2026-11-12_building_code_text.md.
STATE_SETTINGS = "state.yaml"


ZONING_RULES = "5_zoning_rules"                  # a place's rulebooks (step 5)
BUILDING_CODE_RULES = "5_building_code_rules"    # a state folder's rulebooks: its building code's rules (egress step 3)


def rules_folder(folder) -> Path:
    """Where a law folder's rulebooks are: 5_zoning_rules/ for a place, 5_building_code_rules/ for a state law folder
    (one with a state.yaml), whose law is a building code, not zoning. The one definition, used by validation, the
    research checks, the coverage review list and drafting."""
    folder = Path(folder)
    return folder / (BUILDING_CODE_RULES if (folder / STATE_SETTINGS).is_file() else ZONING_RULES)


GENERAL_RULES = "general.yaml"                   # a state folder's one rulebook: its building code's rules, every house


def building_code_rulebook(folder, exists=Path.is_file) -> Path | None:
    """A state law folder's rulebook (its building code's rules, for every house, not by district): the
    5_building_code_rules/general.yaml written by hand when it exists, else the AI-drafted drafted/general.yaml, else
    None, as rulebook_for picks a zone's. Read only for a place that inherits the folder (place.Place.inherits): a
    state folder is never checked on its own."""
    base = Path(folder) / BUILDING_CODE_RULES
    return next((p for p in (base / GENERAL_RULES, base / "drafted" / GENERAL_RULES) if exists(p)), None)


def jurisdictions(repo: Path = REPO) -> list[Path]:
    """Every place folder, regulations/jurisdictions/<state>/<place> under `repo`, in a stable order (a state's own
    law folder, which has a state.yaml, is not a place: state_folders)."""
    return [p for p in _law_folders(repo) if not (p / STATE_SETTINGS).is_file()]


def state_folders(repo: Path = REPO) -> list[Path]:
    """Every state law folder (one with a state.yaml), regulations/jurisdictions/<state>/<name>, in a stable order."""
    return [p for p in _law_folders(repo) if (p / STATE_SETTINGS).is_file()]


def law_folders(repo: Path = REPO) -> list[Path]:
    """Every folder of law: the places, then the state law folders. What checks the law's own files (sources,
    extracted text, labels, definitions, coverage) walks."""
    return jurisdictions(repo) + state_folders(repo)


def _law_folders(repo: Path) -> list[Path]:
    return sorted(p for p in (Path(repo) / "regulations/jurisdictions").glob("*/*") if p.is_dir())


# ---- law kept outside the repo ------------------------------------------------------------------------------------
# A copyrighted code book (New York's Residential Code, published by the International Code Council) can't be
# committed: the repo keeps only short exact quotes with their section, page and a link, and its sources.yaml entry
# says `kept_outside_repo: true`. The book itself and its extracted text live in a cache on the machines that have
# it, one folder per fingerprint: <cache>/<sha256>/<file>, and the text of every page, one file per extractor
# version (document_extraction/book_text.py): the same cache for every branch, each reading its own brought-in pages
# from it. Where the cache is missing (CI), every check that needs the text is skipped and says so; nothing is ever
# passed in its stead.
CODE_CACHE_ENV = "GORDIUM_CODE_CACHE"
DEFAULT_CODE_CACHE = Path.home() / "Documents/gordium_archive/code_cache"


def code_cache() -> Path:
    """The folder holding law kept outside the repo ($GORDIUM_CODE_CACHE, else ~/Documents/gordium_archive/code_cache)."""
    import os
    return Path(os.environ.get(CODE_CACHE_ENV) or DEFAULT_CODE_CACHE)


def cached(entry: dict) -> Path:
    """Where a kept-outside document is in the cache."""
    return code_cache() / str(entry.get("sha256")) / entry["file"]


def cached_text(entry: dict) -> Path:
    """Where a kept-outside document's extracted text (every page, this extractor version) is in the cache."""
    from document_extraction.book_text import file_name
    return code_cache() / str(entry.get("sha256")) / file_name(entry)


def brought_in_pages(entry: dict) -> list[int] | None:
    """The pages a kept-outside document's sources.yaml entry brings in (brought_in.pages), or None if it names none."""
    from document_extraction.icc_sections import parse_pages
    spec = entry.get("brought_in", {}).get("pages") if isinstance(entry.get("brought_in"), dict) else None
    return None if spec is None else parse_pages(spec)


def kept_text(entry: dict) -> list[dict]:
    """A kept-outside document's extracted text as this branch brings it in: its brought-in pages chosen from the
    cached whole book, row for row what extract_icc(pdf, those pages) gives (header included)."""
    from document_extraction.book_text import as_printed, select
    pages = brought_in_pages(entry)
    if not pages:                               # never the whole book in its stead (_source_entry_problems)
        raise ValueError(f"{entry['file']}: kept outside the repo with no brought_in.pages")
    return _kept(f"kept text {pages} {_misreads(entry)!r}", cached_text(entry).read_bytes(),
                 lambda data: as_printed(select(_jsonl_rows(data), pages), _misreads(entry))[0])


def _misreads(entry: dict) -> dict:
    """Where a scanned book's OCR misreads the page, by line (sources.yaml brought_in.misread; book_text.as_printed):
    every check reads the brought-in text with them put right."""
    b = entry.get("brought_in")
    return dict(b.get("misread") or {}) if isinstance(b, dict) else {}


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
    # a chart column that holds several districts -> the districts it holds (jurisdiction.yaml districts.shared_columns:
    # Ithaca's one "Central Business" column for CBD-50 ... CBD-140)
    shared_columns: dict[str, list[str]] = field(default_factory=dict)
    proposed: dict[str, dict] = field(default_factory=dict)          # measures drafts asked for, not yet in measures.yaml
    pieces: set[str] = field(default_factory=set)                    # every piece id the law is cut into (research cites them)
    uncached: dict[str, str] = field(default_factory=dict)           # file -> why its text can't be read here (cache)
    skipped: list[str] = field(default_factory=list)                 # checks not run here for want of the cache
    # a book's second reading of its numbers (a state folder's text_verification.yaml), by file: {"pieces": {piece
    # id: its entry}, "lines": {piece id: [[page, first, last], ...]}}; a rule citing it uses only those numbers
    # (code_numbers.py)
    verification: dict[str, dict] = field(default_factory=dict)

    def kinds(self) -> dict:
        """Every usable measure's kind: "number", "text" or "boolean" (this context's measures, plus the
        proposed ones)."""
        return {n: MEASURE_KINDS.get(n, "number") for n in self.measures} | {
            n: UNIT_KINDS.get(m.get("unit"), "number") for n, m in self.proposed.items()}

    def allowed(self) -> dict:
        """What outcome() needs here: the text values each text measure may take, and each proposed
        measure's kind (a proposed text measure takes only the values its record lists, `values:`; with none
        listed, every value is unrecognized)."""
        proposed = {n: _listed_values(self.proposed[n]) if k == "text" else k for n, k in self.kinds().items()
                    if n in self.proposed}
        return {"use": self.uses, "district": self.districts} | proposed

    def _problem(self, name: str, message: str):
        self.problems.append(f"{name}: {message}")
        self.file_problems.setdefault(name, []).append(message)

    @classmethod
    def for_jurisdiction(cls, jurisdiction_dir, use_cache: bool = True) -> "Context":
        """Everything a folder's rules are checked against. `use_cache=False`: a book kept outside the repo is never
        read from the code cache (its quotes are listed as not checked here, exactly as on a machine without the
        cache), so a design's check gives the same answer on every machine (design_checker/egress.py); the quotes
        are checked word for word by `python -m rule_format` where the cache exists."""
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
            outside = entry.get("kept_outside_repo") is True
            pdf = cached(entry) if outside else j / "1_source_documents" / name
            extracted = cached_text(entry) if outside else j / "2_extracted_text" / f"{Path(name).stem}.jsonl"
            sha = entry.get("sha256")
            if outside and (j / "1_source_documents" / name).exists():
                ctx._problem(name, "is kept outside the repo (kept_outside_repo), but a copy is in 1_source_documents")
            elif outside and (j / "2_extracted_text" / f"{Path(name).stem}.jsonl").exists():
                ctx._problem(name, "is kept outside the repo (kept_outside_repo), but its text is in 2_extracted_text")
            elif not sha:
                ctx._problem(name, "no sha256 in sources.yaml")
            elif outside and not use_cache:         # a design's check: the same on every machine (skipped, as below)
                ctx.uncached[name] = "kept outside the repo; its quotes are checked by python -m rule_format where " \
                                     "the code cache exists, never at a design's check"
            elif outside and not pdf.exists():      # skipped, never passed: every quote of it is listed as not checked
                ctx.uncached[name] = (f"kept outside the repo, and not in the code cache here ({_shown_cache(pdf)}); "
                                      "checked where the cache exists")
            elif not pdf.exists():
                ctx._problem(name, "listed in sources.yaml but missing")
            elif hashlib.sha256(pdf.read_bytes()).hexdigest() != sha:
                ctx._problem(name, "fingerprint does not match sources.yaml")
            elif outside and not extracted.exists():
                ctx._problem(name, f"its extracted text isn't in the code cache for this extractor version "
                                   f"({_shown_cache(extracted)}): run python -m document_extraction (it needs "
                                   "pdfplumber; the version is book_text.extractor_key)")
            # Text is only trusted for a document whose own checks all passed. With use_cache=False (a design's
            # check) a kept-outside book's text is never read from the code cache, even where the cache has it, so
            # the check gives the same answer on every machine (docs/decisions/2026-11-23_laws_validation_speed.md)
            if extracted.exists() and name not in ctx.file_problems and not (outside and not use_cache):
                ctx._load_extracted(name, sha, extracted, brought_in_pages(entry) if outside else None,
                                    _misreads(entry) if outside else None)
                # (an outside book with no brought_in.pages has a problem, so is never loaded whole)
            cut = j / "2_extracted_text" / f"{Path(name).stem}.sections.jsonl"
            if cut.exists():
                ctx.pieces |= {row["id"] for row in read_jsonl(cut)[1:]}
            if outside and cut.exists() and name in ctx.pages:
                for problem in _stale_cache_problems(extracted, cut, _misreads(entry)):
                    ctx._problem(name, problem)
            cells = j / "2_extracted_text" / f"{Path(name).stem}.cells.jsonl"
            if entry.get("chart_pages") and cells.exists() and name not in ctx.file_problems:
                ctx._load_cells(name, sha, cells, j)
        ctx.verification = _verification(j)
        proposed = rules_folder(j) / PROPOSED_MEASURES
        if proposed.exists():
            listed_measures = load(proposed) or {}
            ctx.proposed = {n: m for n, m in listed_measures.items() if isinstance(m, dict) and n not in ctx.measures}
        return ctx

    def _load_cells(self, name, sha, path, j):
        """Chart cells read by the chart reader (document_extraction/charts.py). Only cells it read with
        certainty are in the file; unresolved parts of a table can never be cited. `j`: the jurisdiction, whose
        settings say which chart columns are districts."""
        from .place import place
        column, shared = place(j).district_column, place(j).shared_columns
        found = _kept(f"cells {sha} {column.pattern} {sorted(shared.items())!r}", Path(path).read_bytes(),
                      lambda data: _cells_of(data, sha, column, shared))
        if found is None:
            self._problem(name, f"{path.name} was read from a different version; re-extract")
            return
        cells, districts = found
        self.districts |= districts
        self.shared_columns |= shared
        self.cells[name] = cells

    def _load_extracted(self, name, sha, path, pages=None, misreads=None):
        """Extracted text: a header line {"file", "sha256"}, then one {"page", "line", "text", ...} per line.
        The header ties it to the PDF version; CI re-extracts the text from the PDF (python -m
        document_extraction --check) and requires an exact match, so this file can't be edited by hand. `pages`: only
        these pages (a book kept outside the repo: its cached text is the whole book; the branch brings in some)."""
        found = _kept(f"extracted {sha} {pages} {misreads!r}", Path(path).read_bytes(),
                      lambda data: _pages_of(data, sha, pages, misreads))
        if found is None:
            self._problem(name, f"{path.name} was extracted from a different version; re-extract")
            return
        self.pages[name] = found


def _verification(j: Path) -> dict[str, dict]:
    """A law folder's second reading of each book's numbers (text_verification.yaml, or one file per book,
    text_verification.<book>.yaml: verification_files) with the lines of each piece, for code_numbers, by book; a
    file that can't be read is left out (its own check, state_law.verification_problems, says why)."""
    out = {}
    for path in verification_files(j):
        try:
            book = load(path)
            name = book["document"]
            cut = read_jsonl(j / "2_extracted_text" / f"{Path(name).stem}.sections.jsonl")
            out[name] = {"pieces": dict(book["pieces"]), "lines": {r["id"]: r["lines"] for r in cut[1:]},
                         # its numbers were never read a second time (state_law.py): no rule may use them
                         "not_verified": book.get("not_verified")}
        except Exception:        # reported by its own check, never a crash here
            continue
    return out


def verification_files(j) -> list[Path]:
    """A law folder's records of the second reading of its books' numbers: text_verification.yaml (one book, as New
    York's), then text_verification.<book>.yaml, one per book (Maine's two books)."""
    j = Path(j)
    return [p for p in [j / "text_verification.yaml", *sorted(j.glob("text_verification.*.yaml"))] if p.is_file()]


def _stale_cache_problems(extracted: Path, cut: Path, misreads: dict | None = None) -> list[str]:
    """A cached text that is not the one the repo's pieces were cut from (edited, or left from another extraction):
    each piece's words must still have the fingerprint the sections file records. Only `python -m
    document_extraction --check` re-extracts, so without this an edited cache would feed every other check."""
    from document_extraction.book_text import as_printed
    from document_extraction.icc_sections import text_fingerprint
    lines = {(r["page"], r["line"]): r for r in as_printed(read_jsonl(extracted), misreads)[0][1:]}
    out = []
    for piece in read_jsonl(cut)[1:]:
        members = [lines.get((pg, n)) for pg, a, b in piece["lines"] for n in range(a, b + 1)]
        if None in members or text_fingerprint(members) != piece["text_sha256"]:
            out.append(f"{_shown_cache(extracted)}: {piece['id']}'s words are not the ones its piece was cut from; "
                       "run python -m document_extraction")
    return out


def _shown_cache(path: Path) -> str:
    """A cache path as messages show it: from the cache folder, so a message reads the same on every machine."""
    try:
        return "<code cache>/" + path.relative_to(code_cache()).as_posix()
    except ValueError:
        return path.as_posix()


def _cells_of(data: bytes, sha: str, district_column: re.Pattern, shared: dict | None = None) -> tuple | None:
    """A .cells.jsonl file's bytes -> (its cells, its districts: the columns `district_column` matches, and the districts
    each column of `shared` holds), or None when
    its header names another PDF version than `sha` (checked before any row is read, so a stale file is always
    "re-extract", never a crash)."""
    rows = _jsonl_rows(data)
    if not rows or rows[0].get("sha256") != sha:
        return None
    cells, districts = {}, set()
    for r in rows[1:]:
        if "columns" in r:
            districts |= {district_name(c["name"]) for c in r["columns"] if district_column.fullmatch(c["name"])}
            districts |= {d for c in r["columns"] for d in (shared or {}).get(c["name"], [])}
        elif "value" in r and not r.get("heading"):
            cells[(r["page"], r["section"], r["row"].strip(), r["column"])] = r
    return cells, districts


def _pages_of(data: bytes, sha: str, only: list[int] | None = None, misreads: dict | None = None) -> dict | None:
    """An extracted-text .jsonl file's bytes -> page -> line -> the line's words (`only`: these pages), or None when
    its header names another PDF version than `sha` (checked before any row is read, as for _cells_of)."""
    rows = _jsonl_rows(data)
    if not rows or rows[0].get("sha256") != sha:
        return None
    if misreads:                       # a scanned book: its OCR's misreads put right (book_text.as_printed)
        from document_extraction.book_text import as_printed
        rows = as_printed(rows, misreads)[0]
    pages: dict[int, dict[int, list[str]]] = {}
    keep = None if only is None else set(only)
    for row in rows[1:]:
        if keep is not None and int(row["page"]) not in keep:
            continue
        pages.setdefault(int(row["page"]), {})[int(row["line"])] = tokenize(row["text"])
    return pages


SOURCE_FIELDS = {"file", "title", "publisher", "url", "downloaded_on", "sha256", "pages", "contents", "notes",
                 "adopted_on", "created_on", "quotable", "not_quotable_because", "layout", "chart_pages",
                 "kept_outside_repo", "copy", "terms", "edition", "in_force", "brought_in", "style"}
# Document layouts the section splitters know: ecode360 (document_extraction/sections.py), icc (an ICC code book,
# document_extraction/icc_sections.py), two_column (a book in two columns read from its text layer, with its `style`:
# document_extraction/columns.py and columns_sections.py)
LAYOUTS = {"ecode360", "icc", "two_column"}
# A chart column that is a district, as the chart prints it (R-1B, R-3AA, RU), is each place's own: its
# jurisdiction.yaml districts.chart_column, through the registry (place.py: Place.district_column), the one
# definition the chart reader, the inspector and the drafter all use.


def column_districts(column: str, shared: dict | None = None) -> list[str]:
    """The districts a chart column is for: those a shared column holds (jurisdiction.yaml districts.shared_columns,
    e.g. Ithaca's "Central Business" column for CBD-50 ... CBD-140), else the one the column names (R-1B -> R-1b)."""
    return list((shared or {}).get(column) or [district_name(column)])


def district_name(column: str) -> str:
    """A chart column as the city writes the district in its law and in file names: R-1B -> R-1b."""
    m = re.fullmatch(r"([A-Z]+-\d+)([A-Z]*)", column)
    return m[1] + m[2].lower() if m else column


def _text_problems(f: str, allowed: dict[str, set]) -> list[str]:
    """Each quoted value must be one the measure it is compared with can take: a use for `use`, a district
    for `district`, a listed value for a proposed text measure (its `values:`). So `use == "R-2a"` (a district written where a use belongs) can't pass the inspector and
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
    from . import code_numbers
    if code_numbers.cites_book(sources, ctx):      # a building code read twice: its second reading's numbers only
        return code_numbers.problems(rule, sources, ctx)
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
        if district not in column_districts(c["column"], ctx.shared_columns):
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
    if entry.get("kept_outside_repo") is True:
        # The code cache holds every page of the book, for every branch: without the pages this branch brings in, a
        # quote from any page of it would be checked as law brought in.
        try:
            pages = brought_in_pages(entry)
        except (TypeError, ValueError):
            pages = None
        if not pages:
            p.append("kept outside the repo, so it needs brought_in.pages (the pages read, e.g. '34-56, 99'): "
                     "only those of the cached book are read")
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
    # a rule's per-part fields (parts.py) only when it has them: every fingerprint made before them is unchanged
    approved |= {k: entry[k] for k in parts.PART_FIELDS if k in entry}
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
    # A flag has no check, except one citing a book whose numbers were never read a second time (not_verified,
    # state_law.py): there it keeps the check it would have as a rule, its drafted test, shown and tested by its
    # examples' drafted_check, never run for a result (outcome(): a flag always needs review).
    drafted = rule.get("kind") == "flag" and "check" in rule
    if (rule.get("kind") == "rule") != ("check" in rule) and not (drafted and _cites_unverified(rule, ctx)):
        p.append("a 'rule' needs a 'check'; a 'flag' must not have one (unless it cites a book not verified: "
                 "text_verification not_verified, where its check is the drafted test)")
    p += parts.rule_problems(rule)       # for_each, within, when_none (a rule for each part)
    review_when, sources, examples = (_list_of_dicts(rule, k) for k in ("review_when", "sources", "examples"))
    for key, value in (("review_when", review_when), ("sources", sources), ("examples", examples)):
        if value is None:
            p.append(f"'{key}' must be a list of mappings")
        for item in value or []:
            p += [f"{key}: unknown field {k!r}" for k in item if k not in ITEM_FIELDS[key]]
    if any("unknown field" in x for x in p):
        return p  # the approval fingerprint and other checks rely on well-formed items

    # a rule for each part may use its part kind's measures too (parts.yaml), and no other kind's
    try:                              # parts.yaml broken: said as a problem (and by python -m rule_format), never a crash
        own = parts.measure_kinds(rule.get("for_each"))
        foreign = parts.all_measures() - set(own)
    except (ValueError, OSError) as e:
        own, foreign = {}, set()
        p.append(f"rule_format/parts.yaml can't be read, so part measures can't be told apart: {e}")
    kinds = ctx.kinds() | own
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
            # a part's measure (parts.yaml) only in a rule for each part of that kind, even if a draft proposed it
            p += [f"'{n}' in {f!r} is a measure of a part (rule_format/parts.yaml): only a rule for each "
                  f"{_part_kind_of(n)} may use it" for n in sorted(formula.names(f) & foreign)]
            p += [f"unknown measure '{n}' in {f!r}" for n in unknown]
            p += _text_problems(f, {"use": ctx.uses, "district": ctx.districts} | {   # and a proposed text measure's
                n: v for n, v in ctx.allowed().items() if n in ctx.proposed and isinstance(v, set)})   # listed values
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
    # a rule for each part: each example is a small design, its building's measures in `given` and its parts' in
    # `parts`, checked by the rows the checker gives (parts.examples_problems); a whole-building rule has no parts
    per_part = parts.is_part_rule(rule)
    building = ctx.kinds() if per_part else kinds
    for n, ex in enumerate(examples or [], 1):
        given = ex.get("given")
        if not per_part and (extra := [k for k in parts.EXAMPLE_FIELDS if k in ex]):
            p.append(f"example {n}: {extra} only go with a rule for each part (for_each)")
        elif not isinstance(given, dict) or not all(isinstance(k, str) for k in given):
            p.append(f"example {n}: 'given' must be a mapping of measurement names to values")
        elif unknown := sorted(given.keys() - set(building)):
            p.append(f"example {n}: unknown measures {unknown}" + (
                " (a part's measures go in 'parts')" if per_part and set(unknown) & set(own) else ""))
        elif wrong := sorted(k for k, v in given.items() if not _fits(kinds[k], v)):
            p.append(f"example {n}: wrong kind of value for {wrong} (see measures.yaml units)")
        elif "use" in given and given["use"] not in ctx.uses:
            p.append(f"example {n}: unknown use {given['use']!r}")
        elif "district" in given and given["district"] not in ctx.districts:
            p.append(f"example {n}: unknown district {given['district']!r}")
        elif ex.get("expect") not in OUTCOMES:
            p.append(f"example {n}: expect must be one of {OUTCOMES}")
        elif not per_part and not p and (got := outcome(rule, given, ctx.allowed())) != ex["expect"]:
            p.append(f"example {n}: expected {ex['expect']}, got {got}")
    if per_part:
        p += parts.examples_problems(rule, examples or [], ctx.allowed(), run=not p)
    p += _drafted_check_problems(rule, examples or [], ctx, run=not p)

    p += rule_revision_problems(rule.get("revised", []))
    p += _approval_problems(rule, ctx, APPROVED_FIELDS)
    if rule.get("status") == "approved":
        used = set().union(*(formula.names(f) for f in conditions if isinstance(f, str) and _parses(f)))
        p += [f"uses proposed measure '{m}': an engineer must add it to measures.yaml before this can be approved"
              for m in sorted(used & set(ctx.proposed))]
    return p


def _cites_unverified(rule: dict, ctx: Context) -> bool:
    """Whether a rule cites a book whose numbers were never read a second time (text_verification not_verified)."""
    sources = rule.get("sources")
    return isinstance(sources, list) and any(
        isinstance(s, dict) and isinstance(s.get("file"), str)
        and (ctx.verification.get(s["file"]) or {}).get("not_verified") for s in sources)


def _drafted_check_problems(rule: dict, examples: list, ctx: Context, run: bool) -> list[str]:
    """A flag's drafted test (a flag citing a book not verified keeps its check: _rule_problems): each example's
    `drafted_check` is what the check gives when the flag is run as a rule (its one answer, for a rule for each
    part), proved here, with at least one that passes and one that fails, so the drafted formula is exercised. The
    flag's own result (`expect`) is still needs review (or not applicable). drafted_check goes only with such a
    flag."""
    drafted = rule.get("kind") == "flag" and isinstance(rule.get("check"), str)
    given = [(n, ex) for n, ex in enumerate(examples, 1) if "drafted_check" in ex]
    if not drafted:
        return [f"example {n}: drafted_check goes only with a flag that keeps a drafted check" for n, _ in given]
    p, seen = [], set()
    as_rule = dict(rule, kind="rule")
    for n, ex in given:
        want = ex["drafted_check"]
        if want not in OUTCOMES:
            p.append(f"example {n}: drafted_check must be one of {OUTCOMES}")
            continue
        seen.add(want)
        if not run:
            continue
        got = parts.worked_example(as_rule, ex, ctx.allowed())
        got = got[0] if isinstance(got, tuple) else got
        if got != want:
            p.append(f"example {n}: the drafted check gives {got}, not {want} (drafted_check)")
    if not {"pass", "fail"} <= seen:
        p.append("a flag that keeps a drafted check needs examples whose drafted_check passes and fails, so the "
                 "drafted test is really exercised")
    return p


def rule_revision_problems(revised) -> list[str]:
    """A rule's changes after the AI's draft (REVISED_FIELDS): each {field, by, date, why}, by and why text."""
    if not (isinstance(revised, list) and all(isinstance(r, dict) for r in revised)):
        return ["'revised' must be a list of {field, by, date, why}"]
    p = []
    for r in revised:
        if r.keys() != {"field", "by", "date", "why"}:
            p.append("each revision needs exactly field, by, date, why")
        elif r["field"] not in REVISED_FIELDS:
            p.append(f"revised field {r['field']!r}: not a field a revision can change ({sorted(REVISED_FIELDS)})")
        elif not all(isinstance(r[k], str) and r[k].strip() for k in ("by", "why")):
            p.append("a revision's by and why must be text")
        elif not isinstance(r["date"], datetime.date):
            p.append("a revision's date must be a date (YYYY-MM-DD)")
    return p


def _part_kind_of(measure: str) -> str:
    return next((k for k, d in parts.registry().items() if measure in d["measures"]), "part").replace("_", " ")


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
    """`report`: the research report it came from, "docs/research/<file>.md §<section>"; the file must exist, and be
    under docs/research/ (a law's certificate lists that folder: rule_format/published.py, so a report that appears or
    goes there is seen; one anywhere else would not be)."""
    if "report" not in item:
        return []
    path, _, section = item["report"].partition(" §") if isinstance(item["report"], str) else (None, "", "")
    if not path or not path.startswith("docs/research/") or ".." in Path(path).parts or not (REPO / path).is_file():
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
        elif name in ctx.uncached:          # skipped, never passed: listed so the run says what it didn't check
            ctx.skipped.append(f"{name} p.{page} lines {lines}: quote not checked here ({ctx.uncached[name]})")
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
    """(where, entry) for every entry that can hold open questions: definitions, rules (rules_folder) and
    section labels. `where` names it for a message ("definitions.yaml story", "R-1b.yaml R-1b.height")."""
    j = Path(jurisdiction)
    out = []
    definitions = j / "4_term_definitions/definitions.yaml"
    if definitions.exists():
        out += [(f"definitions.yaml {k}", e) for k, e in (load(definitions) or {}).items() if isinstance(e, dict)]
    for path in rulebook_paths(rules_folder(j)):
        out += [(f"{path.name} {r.get('id')}", r) for r in (load(path) or {}).get("rules") or [] if isinstance(r, dict)]
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


# The words an architect reads (a rule's title, notes, review reasons, worked examples' notes: the checker shows
# them) carry no engineer's key: no snake_case name of a measure or fact, no rule id (review round 2, 2026-11-23).
# A file path or a URL is a reference, not a key, so it is set aside first: a URL, a path from one of the repo's top
# folders, or a file name the repo holds. Anything else joined by a slash (front_yard/side_yard) or ending like a file
# (lot_area.md) is still read for keys (review round 2, 2026-11-24). Required where the law's settings say
# `plain_words: true` (state.yaml, or a place's jurisdiction.yaml).
_TOP_FOLDERS = ("apps", "docs", "packages", "regulations", "test_data")
_PATHLIKE = re.compile(rf"https?://\S+|\b(?:{'|'.join(_TOP_FOLDERS)})(?:/[\w.-]+)+/?")
_FILE_NAME = re.compile(r"\b[\w-]+\.(?:py|yaml|md|json|jsonl)\b")
_repo_file_names: set[str] | None = None
# Names that are no file of the repo's own: made by tools as they run (Python's caches, pip's egg-info, the add-in's
# build and test folders, hidden files such as a publish's lock), and what `python -m rule_format publish` writes (the
# 7_published_rulebooks folders while rules are draft, their certificates). The walk below skips them, and so do the
# folder listings a published law's certificate keeps (rule_format/published.py): one rule for both, so a certificate
# never leaves out a name this walk could see, and publishing never changes what it sees.
# Every name the repo's .gitignore files ignore is one (test_published pins it): Rhino's lock and backup files beside
# an open model (review round 2) are no more the repo's than a Python cache. Except a name Python can import: a
# compiled module (.pyd, .pyc) beside a validator's .py is imported in its place, so it must change the listing
# (review round 3); Python's own caches are in __pycache__, left out whole.
# The Revit pane's apartment answer is made before the C# tests (apps/revit_addin/tools/evals/make_apartment_answer.py,
# gitignored) in a folder Maine's compile walks: made after a publish, it would otherwise make that certificate stale.
GENERATED_NAMES = ("__pycache__", "bin", "obj", "TestResults", "7_published_rulebooks", "venv", "dist", "build",
                   "four_unit_apartment_check_answer.json")
PUBLISHED_SUFFIX = ".published.json"
GENERATED_SUFFIXES = (".egg-info", PUBLISHED_SUFFIX, ".rhl", ".3dmbak")


def generated_name(name: str) -> bool:
    return name.startswith(".") or name in GENERATED_NAMES or name.endswith(GENERATED_SUFFIXES)


def _in_repo(name: str) -> bool:
    """Whether a file of this name is in the repo's top folders (read once, skipping generated names:
    generated_name)."""
    global _repo_file_names
    if _repo_file_names is None:
        names = set()
        for top in _TOP_FOLDERS:
            for _, dirs, files in os.walk(REPO / top):
                dirs[:] = [d for d in dirs if not generated_name(d)]
                names.update(f for f in files if not generated_name(f))
        _repo_file_names = names
    return name in _repo_file_names


def _set_aside_references(text: str) -> str:
    text = _PATHLIKE.sub(" ", text)
    return _FILE_NAME.sub(lambda m: " " if _in_repo(m.group(0)) else m.group(0), text)
# a district rule's id is one even with no underscore (R-1a.height, RU.use: round 1 of the Ithaca review, 2026-11-24)
_ENGINEER_KEY = re.compile(r"\b(?:[A-Z]{1,4}-\d+[A-Za-z]*|[A-Z]{2,4})\.[a-z][a-z0-9_]*[a-z0-9]\b|"
                           r"\bgeneral\.[a-z0-9_.]*[a-z0-9_]|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
PLACE_SETTINGS = "jurisdiction.yaml"   # a place's settings (place.py SETTINGS, which imports this module)


def plain_words_problems(book: dict) -> list[str]:
    out = []
    for r in book.get("rules") or []:
        if not isinstance(r, dict):
            continue
        texts = [("title", r.get("title")), ("notes", r.get("notes"))]
        texts += [(f"review_when {n} reason", w.get("reason")) for n, w in enumerate(r.get("review_when") or [], 1)
                  if isinstance(w, dict)]
        texts += [(f"example {n} note", e.get("note")) for n, e in enumerate(r.get("examples") or [], 1)
                  if isinstance(e, dict)]
        for where, t in texts:
            if isinstance(t, str):
                keys = sorted(set(_ENGINEER_KEY.findall(_set_aside_references(t))))
                if keys:
                    out.append(f"{r.get('id')}: its {where} shows an engineer's key to the architect: {', '.join(keys)} "
                               f"(say it in plain words)")
    return out


def _plain_words_law(path: Path) -> bool:
    """Whether the law folder the rulebook is in asks for plain words (state.yaml `plain_words: true`, or the place's
    jurisdiction.yaml for its own rulebooks). The nearest settings file decides; an answer key (test_data/) has none."""
    for folder in path.parents:
        for name in (STATE_SETTINGS, PLACE_SETTINGS):
            settings = folder / name
            if settings.is_file():
                return (load(settings) or {}).get("plain_words") is True
    return False


def rulebook_file_problems(path, ctx: Context) -> list[str]:
    """Everything wrong with one rulebook file: it can be read, passes `validate`, and its district is its
    file name."""
    path = Path(path)
    try:
        book = load(path)
        problems = validate(book, ctx)
        if isinstance(book, dict) and book.get("district") != path.stem:
            problems.append(f"district {book.get('district')!r} doesn't match the file name {path.stem!r}")
        if isinstance(book, dict) and _plain_words_law(path):
            problems += plain_words_problems(book)
        return problems
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        return [f"can't read file ({type(e).__name__}: {e})"]
    except Exception as e:  # reported, never raised: one broken file mustn't hide the rest
        return [f"validator error ({type(e).__name__}: {e})"]
