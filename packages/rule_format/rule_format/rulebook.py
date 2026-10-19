"""Load a district rule file, decide a rule's outcome, and validate rules.

Outcome order (never a false pass):
  1. applies_when false            -> not_applicable
  2. kind is "flag"                -> needs_review (an architect must judge it)
  3. any review_when true          -> needs_review
  4. check true / false            -> pass / fail
A missing measure at any step    -> needs_review
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import formula
from .formula import FormulaError, MissingMeasure

REPO = Path(__file__).resolve().parents[3]
MEASURES_FILE = Path(__file__).with_name("measures.yaml")
VOCABULARY_FILE = REPO / "regulations/document_extraction_guide/vocabulary.yaml"

OUTCOMES = ("pass", "fail", "needs_review", "not_applicable")
KINDS = ("rule", "flag")  # rule: code checks it; flag: an architect must judge it
STATUSES = ("draft", "approved")
RULE_FIELDS = {"id", "kind", "topic", "says", "applies_when", "check", "review_when",
               "sources", "examples", "notes", "drafted_by", "status", "approved_by", "approved_on"}


def outcome(rule: dict, values: dict) -> str:
    try:
        if "applies_when" in rule and not formula.evaluate(rule["applies_when"], values):
            return "not_applicable"
        if rule["kind"] == "flag":
            return "needs_review"
        if any(formula.evaluate(r["when"], values) for r in rule.get("review_when", [])):
            return "needs_review"
        return "pass" if formula.evaluate(rule["check"], values) else "fail"
    except MissingMeasure:
        return "needs_review"


def load(path) -> dict:
    return yaml.safe_load(Path(path).read_text())


@dataclass
class Context:
    """Everything a rule is checked against, for one jurisdiction."""
    measures: set[str]
    uses: set[str]
    topics: set[str]
    sources: dict[str, dict]                  # file name -> sources.yaml entry
    pages: dict[str, dict[int, str]] = field(default_factory=dict)  # file -> page -> normalized text
    problems: list[str] = field(default_factory=list)                # problems found while loading

    @classmethod
    def for_jurisdiction(cls, jurisdiction_dir) -> "Context":
        j = Path(jurisdiction_dir)
        uses_file = j / "4_term_definitions/uses.yaml"
        listed = {d["file"]: d for d in load(j / "1_source_documents/sources.yaml")["documents"]}
        ctx = cls(measures=set(load(MEASURES_FILE)),
                  uses=set(load(uses_file)) if uses_file.exists() else set(),
                  topics=set(load(VOCABULARY_FILE)["topics"]), sources=listed)
        for name, entry in listed.items():
            pdf = j / "1_source_documents" / name
            if not pdf.exists():
                ctx.problems.append(f"{name}: listed in sources.yaml but missing")
            elif hashlib.sha256(pdf.read_bytes()).hexdigest() != entry["sha256"]:
                ctx.problems.append(f"{name}: fingerprint does not match sources.yaml")
            extracted = j / "2_extracted_text" / f"{Path(name).stem}.jsonl"
            if extracted.exists():
                pages: dict[int, list[str]] = {}
                for line in extracted.read_text().splitlines():
                    row = json.loads(line)
                    pages.setdefault(row["page"], []).append(row["text"])
                ctx.pages[name] = {p: normalize(" ".join(t)) for p, t in pages.items()}
        return ctx


def normalize(text: str) -> str:
    """Lowercase, unify quotes and dashes, drop all whitespace: PDF spacing is unreliable."""
    text = text.lower().translate(str.maketrans("‘’“”–—", "''\"\"--"))
    return re.sub(r"\s+", "", text)


def quote_found(quote: str, page_text: str) -> bool:
    """True if every part of the quote (parts separated by '…') appears on the page, in order."""
    pos = 0
    for part in filter(None, map(normalize, quote.split("…"))):
        pos = page_text.find(part, pos)
        if pos < 0:
            return False
        pos += len(part)
    return True


def validate(rulebook: dict, ctx: Context) -> list[str]:
    """Return a list of problems. An empty list means the rulebook is valid."""
    problems = list(ctx.problems)
    district = rulebook.get("district")
    if not district:
        return problems + ["missing 'district'"]
    seen = set()
    for i, rule in enumerate(rulebook.get("rules") or []):
        rid = rule.get("id", f"rule #{i + 1}")
        problems += [f"{rid}: {p}" for p in _rule_problems(rule, district, ctx)]
        if rid in seen:
            problems.append(f"{rid}: duplicate id")
        seen.add(rid)
    if not seen:
        problems.append("no rules")
    return problems


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

    formulas = [rule[k] for k in ("applies_when", "check") if k in rule]
    for r in rule.get("review_when", []):
        if not r.get("reason"):
            p.append("each review_when needs a 'reason'")
        formulas.append(r.get("when", ""))
    for f in formulas:
        try:
            p += [f"unknown measure '{n}' in {f!r}" for n in sorted(formula.names(f) - ctx.measures)]
            p += [f"unknown use '{u}' in {f!r}" for u in sorted(formula.strings(f) - ctx.uses)]
        except FormulaError as e:
            p.append(str(e))

    p += _source_problems(rule.get("sources"), ctx)

    examples = rule.get("examples") or []
    if rule.get("kind") == "rule" and not examples:
        p.append("a 'rule' needs at least one worked example")
    for n, ex in enumerate(examples, 1):
        if ex.get("expect") not in OUTCOMES:
            p.append(f"example {n}: expect must be one of {OUTCOMES}")
        elif not p and (got := outcome(rule, ex.get("given") or {})) != ex["expect"]:
            p.append(f"example {n}: expected {ex['expect']}, got {got}")

    if rule.get("status") not in STATUSES:
        p.append(f"status must be one of {STATUSES}")
    if not rule.get("drafted_by"):
        p.append("missing 'drafted_by'")
    if rule.get("status") == "approved" and not (rule.get("approved_by") and rule.get("approved_on")):
        p.append("approved rules need 'approved_by' and 'approved_on'")
    return p


def _source_problems(sources, ctx: Context) -> list[str]:
    if not sources:
        return ["needs at least one source"]
    p = []
    for s in sources:
        name, page, quote = s.get("file"), s.get("page"), s.get("quote")
        if name not in ctx.sources:
            p.append(f"source file {name!r} is not in sources.yaml")
        elif not (isinstance(page, int) and quote):
            p.append(f"source {name}: needs 'page' (number) and 'quote'")
        elif name not in ctx.pages:
            p.append(f"source {name}: no extracted text, quote not verified")
        elif page not in ctx.pages[name]:
            p.append(f"source {name}: page {page} does not exist")
        elif not quote_found(quote, ctx.pages[name][page]):
            p.append(f"source {name} p.{page}: quote not found: {quote!r}")
    return p
