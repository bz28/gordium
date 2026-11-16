"""Check the rules for each part (bedrooms, escape openings, stairs): one row per part, named, as panel items.

Plain code, no AI. Each part's result is rule_format.parts.rows' (the same outcome() as every zoning rule); this
module names each row for the architect ("Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft"), gives
each rule its one answer (parts.rule_result), and turns the rows into panel items whose overall answer is
present.state's, the same as the zoning rows'. Design: docs/decisions/2026-11-12_rules_for_each_part.md.
"""

import ast

from rule_format import formula, parts
from rule_format.parts import part_outcome

from design_checker import present

STATUS = {"pass": present.COMPLIES, "fail": present.FAILS, "needs_review": present.REVIEW}
UNIT_WORDS = {"sf": "sq ft", "count": "", "yes_no": "", "text": ""}
SIGNS = {ast.GtE: "≥", ast.Gt: ">", ast.LtE: "≤", ast.Lt: "<"}
MIRROR = {ast.GtE: ast.LtE, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.Lt: ast.Gt}
INTERIOR_NOT_STARTED = "interior.not_started"
INTERIOR_NOT_STARTED_WHY = "the interior isn't checked yet (bedrooms, escape openings, stairs, exit doors): " \
                           "start the interior to check them"


def part_rules(rules: list[dict]) -> list[dict]:
    """The rules for each part in a rulebook (for_each)."""
    return [r for r in rules if parts.is_part_rule(r)]


def check_parts(rules: list[dict], given, values: dict, allowed: dict, has_none: dict | None = None) -> dict:
    """Every per-part rule's rows, each rule's one answer, and the panel items.

    given: the parts read, {kind: [part, …]} (parts.rows), or None when the interior isn't being checked at all
    (the architect hasn't started it): then no part is checked and one counted item says so, so the design is never
    shown as complying with rules nobody checked (needs review: principle 4). values: the building's measures.
    has_none: what the interior description says the house has none of ({kind: {"source", "words", "parts"}},
    model_measurement.interior's): each row it makes not applicable says so, with its source, and `set_aside` lists
    them by claim ({kind: [rule key, …]}) for the panel to show (egress.py)."""
    rules = part_rules(rules)
    if given is None:
        items = [_item(INTERIOR_NOT_STARTED, None, "Interior", present.REVIEW, INTERIOR_NOT_STARTED_WHY)] \
            if rules else []
        return {"rows": [], "results": {_key(r, n): "needs_review" for n, r in enumerate(rules, 1)}, "items": items,
                "set_aside": {}}
    stated = _stated(given)
    given, why_not = cautious(given)
    home = _homes(given)
    claims = has_none if isinstance(has_none, dict) else {}
    out, results, set_aside = [], {}, {k: [] for k in claims}
    for n, rule in enumerate(rules, 1):
        got = parts.rows(rule, given, values, allowed)
        for row in got:
            if not row.get("within") and row["id"] is not None:   # a window checked on its own: its room named too
                row["home"] = home.get((row["part"], row["id"]))
            claim = _claim_of(rule, row, given, claims, stated, values, allowed)
            if claim is None and row["outcome"] == "pass" and (doubt := _reading_read(rule, row, claims, stated)):
                # a pass that reads a measure resting on a reading still to confirm: never a pass on it
                row["outcome"] = "needs_review"
                row["reason"] = (f"complies only if this reading is confirmed: {claims[doubt]['words']} "
                                 f"({claims[doubt]['source']})")
                row["has_none"] = doubt
            elif claim is not None:
                row["reason"] = ("not applicable if confirmed: " if claims[claim].get("reading") is True else
                                 "not applicable: ") + f"{claims[claim]['words']} ({claims[claim]['source']})"
                row["has_none"] = claim
                if _key(rule, n) not in set_aside[claim]:
                    set_aside[claim].append(_key(rule, n))
            row["line"] = line(row, rule, values, allowed, why_not.get((row["part"], row["id"])))
        out += got
        key = _key(rule, n)          # two rules with one id (never validated so): one answer from both, never kinder
        results[key] = parts.rule_result(got + [{"outcome": results[key]}] if key in results else got)
    items, ids = [], set()
    for r in out:
        if r["outcome"] in STATUS:
            items.append(_item(_row_id(r, ids), r["rule"], label(r), STATUS[r["outcome"]], r["line"], r))
    return {"rows": out, "results": results, "items": items, "set_aside": set_aside}


def _stated(given) -> dict:
    """{(kind, part id): {measure: the claim that gave it}}: the measures a part has from what the description says
    the house has none of (model_measurement.interior gives them in the part's `stated`)."""
    out = {}
    for kind, listed in (given.items() if isinstance(given, dict) else []):
        for part in listed if isinstance(listed, list) else []:
            if isinstance(part, dict) and isinstance(part.get("stated"), dict) and isinstance(part.get("id"), str):
                out[(kind, part["id"])] = part["stated"]
    return out


def _reading_read(rule: dict, row: dict, claims: dict, stated: dict) -> str | None:
    """The reading claim (one marked `reading: true`) that gave a measure this rule reads anywhere (applies_when,
    check, review_when) on this row's part, or None."""
    gave = stated.get((rule.get("for_each"), row["id"])) or {}
    try:
        names = parts.formula_names(rule)
    except formula.FormulaError:
        return None
    hit = [gave[m] for m in sorted(names) if m in gave and claims.get(gave[m], {}).get("reading") is True]
    return hit[0] if hit else None


def _part(given: dict, kind, part_id):
    return next((p for p in given.get(kind) or [] if isinstance(p, dict) and p.get("id") == part_id), None)


def _claim_of(rule: dict, row: dict, given: dict, claims: dict, stated: dict, values: dict | None = None,
              allowed: dict | None = None) -> str | None:
    """The claim ("the house has no ramps") that makes this row not applicable, or None. Only a row that is not
    applicable, and only for the reason the claim gives: the rule's "none" row for a kind the claim empties (a
    ramp rule, no ramps; the row for no part a rule's parts sit within: no habitable attics), or a part whose
    applies_when reads a measure the claim gave it (no patio covers, so no window opens into one)."""
    if row["outcome"] != "not_applicable" or not claims:
        return None
    emptied = {k: c for c, claim in claims.items() for k in claim.get("parts") or []}
    kind, parent = rule.get("for_each"), rule.get("within")
    if row.get("none") and kind in emptied and given.get(kind) == []:
        return emptied[kind]
    if row["id"] is None and not row.get("within") and parent in emptied and given.get(parent) == []:
        return emptied[parent]
    gave = stated.get((kind, row["id"])) or {}
    if gave and isinstance(rule.get("applies_when"), str):
        try:
            names = formula.names(rule["applies_when"])
        except formula.FormulaError:
            return None
        hit = [m for m in sorted(names) if m in gave and gave[m] in claims]
        part = _part(given, kind, row["id"])
        if not hit or part is None:
            return None
        # only where the claim decides it: without the claim's measures, the row would not be not applicable (a
        # spiral stair is not applicable to R318.7.1 whatever a loft claim says)
        own = set(parts.measure_kinds(kind))
        mine = {m: v for m, v in (part.get("measures") or {}).items() if m in own and m not in hit}
        without = part_outcome(rule, {**parts.building_values(values or {}), **mine}, allowed or {})
        return gave[hit[0]] if without != "not_applicable" else None
    return None


def cautious(given) -> tuple:
    """(the parts as the rules read them, {(kind, part id): {measure: why it has no value}}). A part's measure that
    its measuring also gives a reason for (`not_measured`) is taken out of its measures: the measuring doubts it,
    so a rule reading it needs review, never a pass on it (model_measurement.interior gives one or the other; this
    holds whatever a host sends). Nothing else changes: anything not a part is left for parts.rows to name."""
    if not isinstance(given, dict):
        return given, {}
    out, why = {}, {}
    for kind, listed in given.items():
        if not isinstance(listed, list):
            out[kind] = listed
            continue
        out[kind] = []
        for part in listed:
            stopped = part.get("not_measured") if isinstance(part, dict) else None
            if isinstance(stopped, dict) and isinstance(part.get("measures"), dict):
                part = dict(part, measures={m: v for m, v in part["measures"].items() if m not in stopped})
            if isinstance(stopped, dict) and isinstance(part.get("id"), str):
                why[(kind, part["id"])] = {m: str(w) for m, w in stopped.items()}
            out[kind].append(part)
    return out, why


def _homes(given) -> dict:
    """{(kind, part id): the name of the part it sits in}, for each part that says, by an id given once, which
    part it is in (an escape opening's room): words only, so "Bedroom 2 › Window 5" names a window whose rule isn't
    grouped by room."""
    if not isinstance(given, dict):
        return {}
    every = [(k, p) for k, listed in given.items() if isinstance(listed, list) for p in listed
             if isinstance(p, dict) and isinstance(p.get("id"), str)]
    ids = [p["id"] for _, p in every]
    names = {p["id"]: parts._name(p) for _, p in every if ids.count(p["id"]) == 1}
    return {(k, p["id"]): names[p["within"]] for k, p in every
            if isinstance(p.get("within"), str) and p["within"] in names}


def _row_id(row: dict, taken: set) -> str:
    """A row's item id, the same at every check of the same parts: the rule, the part it sits in and the part
    ("general.r319_2_3@br2/w5"), so a re-check's notice and the panel's selection follow the same part. Two rows
    alike (two problems of one rule) get #2, #3."""
    base = f"{row['rule']}@{(row.get('within') or {}).get('id') or '-'}/{row.get('id') or '-'}"
    got, n = base, 1
    while got in taken:
        n += 1
        got = f"{base}#{n}"
    taken.add(got)
    return got


def _key(rule: dict, n: int) -> str:
    """A rule's key among the results: its id, or (a rule without one, never validated so) its place in the list,
    so two such rules never share one answer."""
    return rule["id"] if isinstance(rule.get("id"), str) else f"rule #{n}"


def _title(rule: dict) -> str:
    return rule.get("title") if isinstance(rule.get("title"), str) else rule.get("id") or "the rule"


def _item(item_id, rule_id, name, status, reason, row=None) -> dict:
    """A panel item, with every field the panel and the report read on any item (present.view's)."""
    return {"id": item_id, "rule": rule_id, "name": name, "group": "interior", "status": status,
            "mark": present.MARK[status], "proposed": "", "required": "", "margin": "", "sign": "", "zoom": None,
            "measure": None, "objects": [], "points": None, "hint": None, "reason": reason, "use_detail": False,
            "part": ({k: row[k] for k in ("part", "id", "name", "within")} if row else None),
            "detail": {"line": reason or "", "quotes": [], "citation": "", "links": [], "calc": None, "scope": "",
                       "precision": "", "at_limit": None}}


def label(row: dict) -> str:
    """The part a row is about, as the architect names it: "Bedroom 2 › Window 5", "Bedroom 2", "Stair 1"; for a
    row about no one part, the rule's part kind ("Stairs")."""
    names = [row["within"]["name"]] if row.get("within") else [row["home"]] if row.get("home") else []
    names += [row["name"]] if row.get("name") else []
    if names:
        return " › ".join(names)
    return (row["part"].replace("_", " ").capitalize() + "s") if isinstance(row.get("part"), str) else "Parts"


def line(row: dict, rule: dict, values: dict, allowed: dict, why_not: dict | None = None) -> str:
    """One line naming the part and why: "Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft".
    `why_not`: the part's measuring's reason for each measure it has no value for (its `not_measured`), said
    wherever the line names that measure as not measured."""
    head = label(row)
    why_not = why_not or {}

    def gone(m: str) -> str:
        return f"{_words(rule, m)} (not measured: {why_not[m]})" if m in why_not else _words(rule, m)
    if row["reason"]:
        return f"{head}: {row['reason']}"
    if row["outcome"] == "fail":
        known = {**parts.building_values(values), **row["values"]}
        if row.get("unknown"):           # proven (parts.fails_whatever): it fails whatever the measures not given are
            if any(m in why_not for m in row["unknown"]):
                return f"{head}: {_title(rule)}: does not comply whatever the " + \
                    " and the ".join(gone(m) for m in row["unknown"])
            names = " and the ".join(_words(rule, m) for m in row["unknown"])
            return f"{head}: {_title(rule)}: does not comply whatever the {names} (not measured)"
        return f"{head}: {_first_failing(rule, known, allowed) or _title(rule)}"
    if row["outcome"] == "needs_review":
        from rule_format.rulebook import _kinds
        kinds = _kinds(allowed, parts.measure_kinds(rule.get("for_each")))
        known = {**parts.building_values(values), **row["values"]}
        # the part's measures and the building's the rule reads (stories, use…): each one missing or unusable
        missing = [m for m in sorted(parts.formula_names(rule)) if not _usable(known.get(m), kinds.get(m))]
        if missing and any(m in why_not for m in missing):
            return f"{head}: " + "; ".join(f"{_words(rule, m)} not measured: {why_not[m]}" if m in why_not
                                          else f"{_words(rule, m)} not measured (or not usable)" for m in missing)
        if missing:
            return f"{head}: {', '.join(_words(rule, m) for m in missing)} not measured (or not usable)"
        return f"{head}: {_title(rule)}: needs review"
    return f"{head}: {_title(rule)}" + (": complies" if row["outcome"] == "pass" else ": not applicable")


def _usable(v, kind) -> bool:
    """A value a formula can use for a measure of this kind (formula._measure's test): yes/no for "boolean", text for
    "text", a finite number ≥ 0 (never true/false) for a number."""
    if kind == "boolean":
        return type(v) is bool
    if kind == "text":
        return type(v) is str
    if isinstance(kind, (set, frozenset)):          # a text measure with its allowed values (the city's uses)
        return type(v) is str and v in kind
    return type(v) in (int, float) and v == v and abs(v) != float("inf") and v >= 0


def _unit(rule: dict, measure: str) -> str:
    d = parts.registry().get(rule["for_each"], {}).get("measures", {}).get(measure) or {}
    u = UNIT_WORDS.get(d.get("unit"), d.get("unit") or "")
    return f" {u}" if u else ""


def _words(rule: dict, measure: str) -> str:
    return measure.replace("opening_", "").replace("stair_", "").replace("door_", "").replace("_", " ")


def _first_failing(rule: dict, values: dict, allowed: dict) -> str | None:
    """The first comparison of the check that fails, in plain words: "net clear area 5.1 sq ft, needs ≥ 5.7 sq ft".
    Each comparison is decided by outcome() itself (part_outcome), so the words never disagree with the result."""
    for node in _all_of(formula.parse(rule["check"]).body):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in SIGNS):
            continue
        left, op, right = node.left, type(node.ops[0]), node.comparators[0]
        if not isinstance(left, ast.Name) and isinstance(right, ast.Name):    # "5.7 <= area": read as "area >= 5.7"
            left, op, right = right, MIRROR[op], left
        if not isinstance(left, ast.Name):
            continue
        if part_outcome({**rule, "check": ast.unparse(node), "review_when": []}, values, allowed) != "fail":
            continue
        name, need = left.id, _value(ast.unparse(right), values, rule, allowed)
        if need is None:
            continue
        return f"{_words(rule, name)} {_n(values.get(name))}{_unit(rule, name)}, needs {SIGNS[op]} " \
               f"{_n(need)}{_unit(rule, name)}"
    return None


def _all_of(node) -> list:
    """The comparisons the check needs every one of: the check itself, or the parts of an `and` (nested `and`s
    too). A comparison inside `or`, `not` or if-else isn't on its own the reason a part fails, so it is never named."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return [n for v in node.values for n in _all_of(v)]
    return [node]


def _value(text: str, values: dict, rule: dict, allowed: dict):
    from rule_format.rulebook import _kinds
    try:
        got = formula.evaluate(text, values, _kinds(allowed, parts.measure_kinds(rule["for_each"])))
    except (formula.EvaluationError, formula.MissingMeasure, ArithmeticError):
        return None
    return got if type(got) in (int, float) else None


def _n(x) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".") if isinstance(x, float) else f"{x:,}" if isinstance(x, int) else str(x)
