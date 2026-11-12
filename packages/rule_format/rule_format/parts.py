"""Rules for each part: "for each sleeping room", "for each escape opening of each sleeping room", "for each stair".

A per-part rule names the part kind it repeats over (`for_each`), optionally the kind those parts sit in (`within`),
and what the law says when there is nothing to check (`when_none`). The kinds, and the measures each part carries,
are a fixed list engineers write (parts.yaml). The result is one row per part, each decided by the same outcome()
as every zoning rule, so missing values and three-valued logic mean exactly what they mean there. Plain code, no AI.
Why and what was rejected: docs/decisions/2026-11-12_rules_for_each_part.md.

Never a silent pass: parts not read, a malformed part, or nothing to check each give a row of their own.
"""

from pathlib import Path

import yaml

from . import formula
from .formula import EvaluationError, FormulaError, MissingMeasure

PARTS_FILE = Path(__file__).with_name("parts.yaml")
PART_FIELDS = ("for_each", "within", "when_none")      # a rule's fields for repeating over parts
WHEN_NONE = ("fail", "needs_review", "not_applicable")  # never "pass": nothing checked never passes
UNITS = {"ft", "sf", "in", "count", "text", "yes_no"}
UNIT_KINDS = {"text": "text", "yes_no": "boolean"}       # every other unit is a number (as in measures.yaml)
KIND_FIELDS = {"meaning", "within", "measures"}
MEASURE_FIELDS = {"unit", "meaning"}


def registry_problems(kinds, building_measures) -> list[str]:
    """Problems with a parts registry (parts.yaml's shape): every kind a meaning and its measures, each measure a
    known unit and a meaning, measure names unique across kinds and never a building measure's, `within` naming
    other known kinds."""
    if not isinstance(kinds, dict) or not kinds:
        return ["parts.yaml must be a non-empty mapping of part kinds"]
    p, seen = [], {}
    for name, k in kinds.items():
        if not (isinstance(name, str) and formula_name(name)):
            p.append(f"part kind {name!r}: a name is lowercase letters, digits and _")
            continue
        if not isinstance(k, dict):
            p.append(f"{name}: must be a mapping")
            continue
        p += [f"{name}: unknown field {f!r}" for f in k.keys() - KIND_FIELDS]
        if not (isinstance(k.get("meaning"), str) and k["meaning"].strip()):
            p.append(f"{name}: needs a 'meaning'")
        within = k.get("within", [])
        if not (isinstance(within, list) and all(isinstance(w, str) for w in within)):
            p.append(f"{name}: 'within' must be a list of part kinds")
        else:
            p += [f"{name}: within unknown part kind {w!r}" for w in within if w not in kinds or w == name]
        measures = k.get("measures")
        if not isinstance(measures, dict) or not measures:
            p.append(f"{name}: needs 'measures'")
            continue
        for m, d in measures.items():
            if not (isinstance(m, str) and formula_name(m)):
                p.append(f"{name}: measure {m!r}: a name is lowercase letters, digits and _")
                continue
            if not isinstance(d, dict) or d.keys() - MEASURE_FIELDS or d.get("unit") not in UNITS \
                    or not (isinstance(d.get("meaning"), str) and d["meaning"].strip()):
                p.append(f"{name}: measure {m!r} needs a unit from {sorted(UNITS)} and a meaning")
            if m in building_measures:
                p.append(f"{name}: measure {m!r} is also a building measure (measures.yaml)")
            if m in seen:
                p.append(f"{name}: measure {m!r} is also a measure of {seen[m]}")
            seen.setdefault(m, name)
    return p


def formula_name(name: str) -> bool:
    return name.isidentifier() and name == name.lower() and not name.startswith("_")


def load_registry(path=PARTS_FILE, building_measures=None) -> dict:
    """parts.yaml, checked: a registry with problems is refused (ValueError), never half used."""
    if building_measures is None:
        from .rulebook import MEASURE_KINDS
        building_measures = MEASURE_KINDS
    kinds = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if problems := registry_problems(kinds, building_measures):
        raise ValueError(f"{path}: " + "; ".join(problems))
    return kinds


_REGISTRY = None


def registry() -> dict:
    """The part kinds (parts.yaml), read once."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = load_registry()
    return _REGISTRY


def is_part_rule(rule: dict) -> bool:
    """A rule with any of the per-part fields: never answered as a whole-building rule."""
    return isinstance(rule, dict) and any(k in rule for k in PART_FIELDS)


def measure_kinds(kind: str) -> dict:
    """The measures a part of this kind carries, by their kind ("number", "boolean" or "text"); {} for an unknown
    kind."""
    k = registry().get(kind) if isinstance(kind, str) else None
    return {m: UNIT_KINDS.get(d["unit"], "number") for m, d in (k or {}).get("measures", {}).items()}


def all_measures() -> set[str]:
    """Every part measure of every kind: a building rule may use none of them."""
    return {m for k in registry().values() for m in k["measures"]}


def rule_problems(rule: dict) -> list[str]:
    """Problems with a rule's per-part fields (validation). A rule without them has none."""
    if not is_part_rule(rule):
        return []
    kinds, p = registry(), []
    kind, within, none = rule.get("for_each"), rule.get("within"), rule.get("when_none")
    if "for_each" not in rule:
        return ["'within' and 'when_none' only go with 'for_each'"]
    if not isinstance(kind, str) or kind not in kinds:
        p.append(f"for_each: unknown part kind {kind!r} (rule_format/parts.yaml lists {sorted(kinds)})")
    elif "within" in rule and (not isinstance(within, str) or within not in kinds.get(kind, {}).get("within", [])):
        p.append(f"within: a {kind} can sit within {kinds[kind].get('within', [])}, not {within!r}")
    if isinstance(rule.get("applies_when"), str) and none != "not_applicable" and isinstance(kind, str):
        try:
            on_part = sorted(formula.names(rule["applies_when"]) & set(measure_kinds(kind)))
        except FormulaError:
            on_part = []                 # an applies_when that can't be read is refused by the rule's own checks
        if on_part:
            p.append(f"applies_when uses {on_part}, measures of the part: a rule that must find a {_words(kind)} "
                     f"(when_none: {none}) can't rule parts out, or a {_words(rule.get('within') or 'building')} "
                     f"whose every {_words(kind)} is ruled out has no row that fails; say how parts differ inside "
                     f"'check' (a if condition else b)")
    if none not in WHEN_NONE:
        p.append(f"when_none: what the law says when there is nothing to check, one of {WHEN_NONE} "
                 f"(never pass), got {none!r}")
    return p


def _name(part: dict) -> str:
    n = part.get("name")
    return n.strip() if isinstance(n, str) and n.strip() else part["id"]


def _words(kind: str) -> str:
    return kind.replace("_", " ")


def _plural(kind: str) -> str:
    return _words(kind) + "s"


def _read(parts, kind: str, everywhere: dict) -> tuple[list[dict] | None, list[str]]:
    """The well-formed parts of one kind, and a problem for each that isn't. None if the kind wasn't read."""
    given = parts.get(kind) if isinstance(parts, dict) else None
    if not isinstance(given, list):
        return None, []
    good, problems = [], []
    for n, part in enumerate(given, 1):
        if not isinstance(part, dict):
            problems.append(f"{_words(kind)} #{n} isn't a part (a mapping)")
        elif not (isinstance(part.get("id"), str) and part["id"].strip()):
            problems.append(f"{_words(kind)} #{n} has no id")
        elif everywhere.get(part["id"], 0) > 1:
            problems.append(f"two parts have the id {part['id']!r}")
        elif "measures" in part and not isinstance(part["measures"], dict):
            problems.append(f"{_words(kind)} {_name(part)}: its measures aren't a mapping")
        else:
            good.append(part)
    # one problem per duplicated id, however many parts share it
    return good, list(dict.fromkeys(problems))


def _ids(parts) -> dict:
    """How many parts carry each id, over every kind given (ids are unique across the whole building)."""
    count = {}
    for given in (parts.values() if isinstance(parts, dict) else []):
        for part in given if isinstance(given, list) else []:
            if isinstance(part, dict) and isinstance(part.get("id"), str):
                count[part["id"]] = count.get(part["id"], 0) + 1
    return count


def _ref(part: dict, kind: str) -> dict:
    return {"kind": kind, "id": part["id"], "name": _name(part)}


def _row(rule, result, part=None, within=None, reason=None, values=None) -> dict:
    return {"rule": rule.get("id"), "part": rule["for_each"], "id": part["id"] if part else None,
            "name": _name(part) if part else None, "within": within, "outcome": result, "reason": reason,
            "values": values or {}}


def part_outcome(rule: dict, values: dict, allowed: dict) -> str:
    """One part's result: outcome() of the rule (its per-part fields set aside) over the building's values and the
    part's own, with the part's measures described by parts.yaml."""
    from .rulebook import _outcome
    plain = {k: v for k, v in rule.items() if k not in PART_FIELDS}
    return _outcome(plain, values, allowed, measure_kinds(rule.get("for_each")))


def _none_outcome(rule: dict, values: dict, allowed: dict) -> str:
    """The result when there is nothing to check: the rule's when_none, if the rule applies to this building.
    Its applies_when is worked out over the building's values with every part measure unknown (three-valued: one
    that could go either way, when when_none isn't "not applicable", needs review). A review_when over the
    building's values alone that holds, or might, needs review; one about a part has no part to look at."""
    from .rulebook import _condition, _kinds
    answer = rule["when_none"]
    kinds = _kinds(allowed, measure_kinds(rule["for_each"]))
    part = set(measure_kinds(rule["for_each"]))
    try:
        if "applies_when" in rule and not _condition(rule["applies_when"], values, kinds):
            return "not_applicable"
    except (MissingMeasure, EvaluationError, FormulaError, ArithmeticError):
        return "not_applicable" if answer == "not_applicable" else "needs_review"
    if answer == "not_applicable":
        return answer
    for r in rule.get("review_when", []):
        if formula.names(r["when"]) & part:
            continue
        try:
            if _condition(r["when"], values, kinds):
                return "needs_review"
        except (MissingMeasure, EvaluationError, FormulaError, ArithmeticError):
            return "needs_review"
    return answer


def rows(rule: dict, parts, values: dict, allowed: dict) -> list[dict]:
    """The rule's rows: one per part (with `within`: per part, grouped under the part it sits in; a part it sits in
    with none of them gets one row, the rule's when_none), never none at all.

    parts: {kind: [{"id", "name"?, "within"?: <id of the part it sits in>, "measures"?: {measure: value}}]}. A kind
    the rule needs that isn't a list wasn't read: one needs-review row. values: the building's measures. Only the
    part kind's own measures are taken from a part (a part can't change a building value)."""
    if rule_problems(rule):
        return [_row(rule if isinstance(rule.get("for_each"), str) else dict(rule, for_each=None), "needs_review",
                     reason="the rule's per-part fields aren't valid")]
    kind, parent = rule["for_each"], rule.get("within")
    own = set(measure_kinds(kind))
    everywhere = _ids(parts)
    children, problems = _read(parts, kind, everywhere)
    parents, parent_problems = _read(parts, parent, everywhere) if parent else ([], [])
    unread = [k for k, got in ((kind, children), (parent, parents)) if k and got is None]
    if unread:
        return [_row(rule, "needs_review", reason=f"the {' and the '.join(_plural(k) for k in unread)} aren't read yet")]
    out = [_row(rule, "needs_review", reason=p) for p in parent_problems + problems]

    def checked(part, within=None):
        mine = {m: v for m, v in (part.get("measures") or {}).items() if m in own}
        return _row(rule, part_outcome(rule, {**values, **mine}, allowed), part, within,
                    values={m: mine.get(m) for m in sorted(formula_names(rule) & own)})

    if not parent:
        out += [checked(p) for p in children]
        if not children and not problems:
            out.append(_row(rule, _none_outcome(rule, values, allowed), reason=f"no {_plural(kind)}"))
        return out
    by_parent = {p["id"]: [] for p in parents}
    # every part id given, and its kind: a part within a kind this rule isn't about (a basement) isn't its business
    kind_of = {p["id"]: k for k, given in (parts.items() if isinstance(parts, dict) else [])
               if isinstance(given, list) for p in given if isinstance(p, dict) and isinstance(p.get("id"), str)}
    for c in children:
        where = c.get("within")
        if where in by_parent:
            by_parent[where].append(c)
        elif kind_of.get(where) in registry()[kind].get("within", []) and kind_of.get(where) != parent \
                and everywhere.get(where) == 1:
            continue
        elif everywhere.get(where, 0) > 1:
            continue                     # its parent's duplicated id is already a needs-review row
        else:
            out.append(_row(rule, "needs_review", c,
                            reason=f"{_words(kind)} {_name(c)} isn't within any {_words(parent)} that was read"))
    for p in parents:
        within = _ref(p, parent)
        mine = by_parent[p["id"]]
        out += [checked(c, within) for c in mine]
        if not mine:
            out.append(_row(rule, _none_outcome(rule, values, allowed), within=within,
                            reason=f"no {_words(kind)}"))
    if not parents and not parent_problems:
        out.append(_row(rule, "not_applicable", reason=f"no {_plural(parent)}"))
    return out


def formula_names(rule: dict) -> set[str]:
    return set().union(*(formula.names(t) for t in [rule.get("applies_when"), rule.get("check")]
                         + [r.get("when") for r in rule.get("review_when", [])] if isinstance(t, str)))


def rule_result(rule_rows: list[dict]) -> str:
    """A per-part rule's one answer from its rows: fail if any row fails; else needs review if any does; else pass
    if any row passes; else (only not-applicable rows) not applicable. No rows is needs review: nothing checked
    never passes."""
    got = {r["outcome"] for r in rule_rows}
    for o in ("fail", "needs_review", "pass"):
        if o in got:
            return o
    return "not_applicable" if got == {"not_applicable"} else "needs_review"
