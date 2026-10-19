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
MIN_QUOTE_LENGTH = 15     # characters after normalizing; short quotes match by accident
RULE_FIELDS = {"id", "kind", "topic", "says", "applies_when", "check", "review_when",
               "sources", "examples", "notes", "drafted_by", "status", "approved_by", "approved_on"}


def outcome(rule: dict, values: dict) -> str:
    try:
        if "applies_when" in rule and not _condition(rule["applies_when"], values):
            return "not_applicable"
        if rule["kind"] == "flag":
            return "needs_review"
        if any(_condition(r["when"], values) for r in rule.get("review_when", [])):
            return "needs_review"
        return "pass" if _condition(rule["check"], values) else "fail"
    except (MissingMeasure, EvaluationError):
        return "needs_review"


def _condition(text: str, values: dict) -> bool:
    result = formula.evaluate(text, values)
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
    pages: dict[str, dict[int, str]] = field(default_factory=dict)  # file -> page -> normalized text
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
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if not rows or rows[0].get("sha256") != sha:
            self.problems.append(f"{path.name}: extracted from a different version of {name}; re-extract")
            return
        pages: dict[int, list[str]] = {}
        for row in rows[1:]:
            pages.setdefault(int(row["page"]), []).append(row["text"])
        self.pages[name] = {p: normalize(" ".join(t)) for p, t in pages.items()}


def normalize(text: str) -> str:
    """Lowercase, unify quotes and dashes, drop all whitespace: PDF spacing is unreliable."""
    text = text.lower().translate(str.maketrans("‘’“”–—", "''\"\"--"))
    return re.sub(r"\s+", "", text)


def quote_found(quote: str, page_text: str) -> bool:
    """True if every part of the quote (parts separated by '…') appears on the page, in order."""
    parts = [p for p in map(normalize, quote.split("…")) if p]
    pos = 0
    for part in parts:
        pos = page_text.find(part, pos)
        if pos < 0:
            return False
        pos += len(part)
    return bool(parts)


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
        rid = rule.get("id", f"rule #{i}")
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

    conditions = [rule[k] for k in ("applies_when", "check") if k in rule]
    for r in review_when or []:
        if not r.get("reason"):
            p.append("each review_when needs a 'reason'")
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

    if rule.get("kind") == "rule" and not examples:
        p.append("a 'rule' needs at least one worked example")
    for n, ex in enumerate(examples or [], 1):
        given = ex.get("given")
        if not isinstance(given, dict):
            p.append(f"example {n}: 'given' must be a mapping of measurements")
        elif unknown := sorted(given.keys() - ctx.measures):
            p.append(f"example {n}: unknown measures {unknown}")
        elif ex.get("expect") not in OUTCOMES:
            p.append(f"example {n}: expect must be one of {OUTCOMES}")
        elif not p and (got := outcome(rule, given)) != ex["expect"]:
            p.append(f"example {n}: expected {ex['expect']}, got {got}")

    if rule.get("status") not in STATUSES:
        p.append(f"status must be one of {STATUSES}")
    if not rule.get("drafted_by"):
        p.append("missing 'drafted_by'")
    if rule.get("status") == "approved":
        if rule.get("approved_by") not in ctx.reviewers:
            p.append("approved_by must be a reviewer listed in regulations/reviewers.yaml")
        elif rule.get("approved_by") == rule.get("drafted_by"):
            p.append("a rule can't be approved by the person who drafted it")
        if not isinstance(rule.get("approved_on"), datetime.date):
            p.append("approved_on must be a date (YYYY-MM-DD)")
    return p


def _source_problems(sources: list[dict], ctx: Context) -> list[str]:
    if not sources:
        return ["needs at least one source"]
    p = []
    for s in sources:
        name, page, quote = s.get("file"), s.get("page"), s.get("quote")
        if name not in ctx.sources:
            p.append(f"source file {name!r} is not in sources.yaml")
        elif type(page) is not int or not isinstance(quote, str):
            p.append(f"source {name}: needs 'page' (number) and 'quote' (text)")
        elif len(normalize(quote.replace("…", ""))) < MIN_QUOTE_LENGTH:
            p.append(f"source {name}: quote too short to be traceable ({MIN_QUOTE_LENGTH}+ characters)")
        elif name not in ctx.pages:
            p.append(f"source {name}: no extracted text, quote not verified")
        elif page not in ctx.pages[name]:
            p.append(f"source {name}: page {page} does not exist")
        elif not quote_found(quote, ctx.pages[name][page]):
            p.append(f"source {name} p.{page}: quote not found: {quote!r}")
    return p
