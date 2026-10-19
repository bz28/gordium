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
MIN_QUOTE_LENGTH = 15     # non-space characters per quoted piece; short pieces match by accident
MAX_QUOTE_PIECES = 3      # at most two '…' gaps in one quote
MAX_QUOTE_GAP = 60        # tokens (words, numbers, symbols) a '…' may skip: about two lines of text
RULE_FIELDS = {"id", "kind", "topic", "says", "applies_when", "check", "review_when", "sources", "examples",
               "notes", "open_questions", "drafted_by", "status", "approved_by", "approved_on", "approved_hash"}
TEXT_FIELDS = ("id", "kind", "topic", "says", "drafted_by", "status", "approved_by")
ITEM_FIELDS = {"review_when": {"when", "reason"}, "sources": {"file", "page", "quote"},
               "examples": {"given", "expect", "note"}}
APPROVED_FIELDS = ("id", "kind", "topic", "says", "applies_when", "check", "review_when", "sources")
MEASURE_KINDS = {name: "text" if m["unit"] == "text" else "number"
                 for name, m in yaml.safe_load(MEASURES_FILE.read_text()).items()}


def outcome(rule: dict, values: dict, allowed: dict[str, set]) -> str:
    """allowed: the values each text measure may take, e.g. {"use": the city's use names}.
    Required, so no caller can forget it. A value outside the list, or a text measure with
    no list, is unrecognized, so the rule needs review."""
    kinds = MEASURE_KINDS | {k: frozenset(v) for k, v in allowed.items()}
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


@dataclass
class Context:
    """Everything a rule is checked against, for one jurisdiction."""
    measures: set[str]
    uses: set[str]
    topics: set[str]
    sources: dict[str, dict]                  # file name -> sources.yaml entry
    reviewers: set[str] = field(default_factory=set)                 # who may approve rules
    pages: dict[str, dict[int, list[str]]] = field(default_factory=dict)  # file -> page -> tokens
    problems: list[str] = field(default_factory=list)                # problems with the sources themselves

    @classmethod
    def for_jurisdiction(cls, jurisdiction_dir) -> "Context":
        j = Path(jurisdiction_dir)
        uses_file = j / "4_term_definitions/uses.yaml"
        listed = {d["file"]: d for d in load(j / "1_source_documents/sources.yaml")["documents"]}
        ctx = cls(measures=set(load(MEASURES_FILE)),
                  uses=set(load(uses_file) or ()) if uses_file.exists() else set(),
                  topics=set(load(VOCABULARY_FILE)["topics"]),
                  reviewers=set(load(REVIEWERS_FILE) or ()),
                  sources=listed)
        for name, entry in listed.items():
            pdf = j / "1_source_documents" / name
            sha = entry.get("sha256")
            if not sha:
                ctx.problems.append(f"{name}: no sha256 in sources.yaml")
            elif not pdf.exists():
                ctx.problems.append(f"{name}: listed in sources.yaml but missing")
            elif hashlib.sha256(pdf.read_bytes()).hexdigest() != sha:
                ctx.problems.append(f"{name}: fingerprint does not match sources.yaml")
            extracted = j / "2_extracted_text" / f"{Path(name).stem}.jsonl"
            if extracted.exists():
                ctx._load_extracted(name, sha, extracted)
        return ctx

    def _load_extracted(self, name, sha, path):
        """Extracted text: a header line {"file", "sha256"}, then one {"page", "text", ...} per line."""
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not rows or rows[0].get("sha256") != sha:
            self.problems.append(f"{path.name}: extracted from a different version of {name}; re-extract")
            return
        pages: dict[int, list[str]] = {}
        for row in rows[1:]:
            pages.setdefault(int(row["page"]), []).append(row["text"])
        self.pages[name] = {p: tokenize(" ".join(t)) for p, t in pages.items()}


# A token is a footnote marker ("[fn11]"), a whole word or number ("rear", "1b", "2.5", "1,500", "3/2",
# ".5"), or a single other character ("%", "(", "/", "§"). '.', ',' and '/' join only digit to digit,
# and a leading '.' starts a number only when no letter, digit or '.' comes right before it ("No.5" is
# "no", ".", "5"), so "minimum/maximum" is three tokens and "3/35" is one.
# Quotes and pages are both split this way, and a quote must match whole tokens, so "5" can never
# match inside "25", "2.5" or "1/2", and "ear" never inside "rear".
TOKEN = re.compile(r"\[fn[^\]\s]*\]|(?:(?<![\w.])\.(?=\d))?[^\W_]+(?:(?<=\d)[.,/](?=\d)[^\W_]+)*|\S")
_UNIFY = str.maketrans("‘’“”–—", "''\"\"--")


def tokenize(text: str) -> list[str]:
    """Lowercase, unify curly quotes and dashes, then split into tokens. Spacing doesn't matter."""
    return TOKEN.findall(text.lower().translate(_UNIFY))


def quote_pieces(quote: str) -> list[list[str]]:
    """The quote's pieces (separated by '…'), each as tokens."""
    return [t for t in map(tokenize, quote.split("…")) if t]


def quote_found(quote: str, page: list[str]) -> bool:
    """True if the quote's pieces appear on the page as whole tokens, in order, each starting
    within MAX_QUOTE_GAP tokens of where the previous piece ended."""
    pieces = quote_pieces(quote)
    return bool(pieces) and _chain(pieces, page, None)


def _chain(pieces: list[list[str]], page: list[str], end: int | None) -> bool:
    """Try every occurrence of the first piece, so an earlier look-alike can't hide a real match."""
    if not pieces:
        return True
    first, n = pieces[0], len(pieces[0])
    last_start = len(page) - n if end is None else min(len(page) - n, end + MAX_QUOTE_GAP)
    for at in range(0 if end is None else end, last_start + 1):
        if page[at:at + n] == first and _chain(pieces[1:], page, at + n):
            return True
    return False


def approval_hash(rule: dict, ctx: "Context") -> str:
    """Fingerprint of what an architect approves: the rule's content and the exact versions of the
    documents it cites. Any later edit, or a replaced source PDF, changes it."""
    sources = rule.get("sources")
    cited = sorted({s["file"] for s in sources if isinstance(s, dict) and isinstance(s.get("file"), str)}
                   if isinstance(sources, list) else [])
    approved = {k: rule.get(k) for k in APPROVED_FIELDS} | {
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
    if not rule.get("says"):
        p.append("missing 'says' (plain-English rule)")
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
            p += [f"unknown measure '{n}' in {f!r}" for n in sorted(formula.names(f) - ctx.measures)]
            p += [f"unknown use '{u}' in {f!r}" for u in sorted(formula.strings(f) - ctx.uses)]
        except FormulaError as e:
            p.append(str(e))

    p += _source_problems(sources, ctx) if sources is not None else []

    expects = {ex.get("expect") for ex in examples or [] if isinstance(ex.get("expect"), str)}
    if rule.get("kind") == "rule" and not {"pass", "fail"} <= expects:
        p.append("a 'rule' needs worked examples that pass and that fail, so its check is really exercised")
    for n, ex in enumerate(examples or [], 1):
        given = ex.get("given")
        if not isinstance(given, dict) or not all(isinstance(k, str) for k in given):
            p.append(f"example {n}: 'given' must be a mapping of measurement names to values")
        elif unknown := sorted(given.keys() - ctx.measures):
            p.append(f"example {n}: unknown measures {unknown}")
        elif wrong := sorted(k for k, v in given.items() if MEASURE_KINDS.get(k) == "number"
                             and type(v) not in (int, float) or MEASURE_KINDS.get(k) == "text" and type(v) is not str):
            p.append(f"example {n}: wrong kind of value for {wrong} (see measures.yaml units)")
        elif "use" in given and given["use"] not in ctx.uses:
            p.append(f"example {n}: unknown use {given['use']!r}")
        elif ex.get("expect") not in OUTCOMES:
            p.append(f"example {n}: expect must be one of {OUTCOMES}")
        elif not p and (got := outcome(rule, given, {"use": ctx.uses})) != ex["expect"]:
            p.append(f"example {n}: expected {ex['expect']}, got {got}")

    p += open_question_problems(rule)

    if rule.get("status") not in STATUSES:
        p.append(f"status must be one of {STATUSES}")
    if not rule.get("drafted_by"):
        p.append("missing 'drafted_by'")
    if rule.get("status") == "approved":
        if rule.get("approved_by") not in ctx.reviewers:
            p.append("approved_by must be a reviewer listed in regulations/reviewers.yaml")
        elif rule["approved_by"].casefold().strip() == rule["drafted_by"].casefold().strip():
            p.append("a rule can't be approved by the person who drafted it")
        if not isinstance(rule.get("approved_on"), datetime.date):
            p.append("approved_on must be a date (YYYY-MM-DD)")
        if rule.get("approved_hash") != approval_hash(rule, ctx):
            p.append("changed since it was approved, or a cited document was replaced (approved_hash doesn't match); needs re-approval")
    return p


def open_question_problems(entry: dict) -> list[str]:
    """Interpretations the law leaves open, for the architects: a list of text. Nothing with open
    questions can be approved (so the checker never uses it) until the answers are recorded."""
    questions = entry.get("open_questions", [])
    if not (isinstance(questions, list) and all(isinstance(q, str) and q.strip() for q in questions)):
        return ["'open_questions' must be a list of text"]
    if questions and entry.get("status") == "approved":
        return ["can't be approved while open_questions remain; record the architects' answers first"]
    return []


def _source_problems(sources: list[dict], ctx: Context) -> list[str]:
    if not sources:
        return ["needs at least one source"]
    p = []
    for s in sources:
        name, page, quote = s.get("file"), s.get("page"), s.get("quote")
        if not isinstance(name, str) or name not in ctx.sources:
            p.append(f"source file {name!r} is not in sources.yaml")
        elif type(page) is not int or not isinstance(quote, str):
            p.append(f"source {name}: needs 'page' (number) and 'quote' (text)")
        elif not (pieces := quote_pieces(quote)) or min(len("".join(p)) for p in pieces) < MIN_QUOTE_LENGTH:
            p.append(f"source {name}: each quoted piece needs {MIN_QUOTE_LENGTH}+ characters to be traceable")
        elif len(pieces) > MAX_QUOTE_PIECES:
            p.append(f"source {name}: at most {MAX_QUOTE_PIECES - 1} '…' gaps in a quote")
        elif name not in ctx.pages:
            p.append(f"source {name}: no extracted text, quote not verified")
        elif page not in ctx.pages[name]:
            p.append(f"source {name}: page {page} does not exist")
        elif not quote_found(quote, ctx.pages[name][page]):
            p.append(f"source {name} p.{page}: quote not found: {quote!r}")
    return p
