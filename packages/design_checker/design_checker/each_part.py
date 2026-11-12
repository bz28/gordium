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
INTERIOR_NOT_STARTED = "interior.not_started"
INTERIOR_NOT_STARTED_WHY = "the interior isn't checked yet (bedrooms, escape openings, stairs, exit doors): " \
                           "start the interior to check them"


def part_rules(rules: list[dict]) -> list[dict]:
    """The rules for each part in a rulebook (for_each)."""
    return [r for r in rules if parts.is_part_rule(r)]


def check_parts(rules: list[dict], given, values: dict, allowed: dict) -> dict:
    """Every per-part rule's rows, each rule's one answer, and the panel items.

    given: the parts read, {kind: [part, …]} (parts.rows), or None when the interior isn't being checked at all
    (the architect hasn't started it): then no part is checked and one counted item says so, so the design is never
    shown as complying with rules nobody checked (needs review: principle 4). values: the building's measures."""
    rules = part_rules(rules)
    if given is None:
        items = [_item(INTERIOR_NOT_STARTED, None, "Interior", present.REVIEW, INTERIOR_NOT_STARTED_WHY)] \
            if rules else []
        return {"rows": [], "results": {r["id"]: "needs_review" for r in rules}, "items": items}
    out, results = [], {}
    for rule in rules:
        got = parts.rows(rule, given, values, allowed)
        for row in got:
            row["line"] = line(row, rule, values, allowed)
        out += got
        results[rule["id"]] = parts.rule_result(got)
    items = [_item(f"{r['rule']}#{n}", r["rule"], label(r), STATUS[r["outcome"]], r["line"], r)
             for n, r in enumerate(out, 1) if r["outcome"] in STATUS]
    return {"rows": out, "results": results, "items": items}


def _item(item_id, rule_id, name, status, reason, row=None) -> dict:
    return {"id": item_id, "rule": rule_id, "name": name, "group": "interior", "status": status,
            "mark": present.MARK[status], "proposed": "", "required": "", "margin": "", "reason": reason,
            "part": ({k: row[k] for k in ("part", "id", "name", "within")} if row else None)}


def label(row: dict) -> str:
    """The part a row is about, as the architect names it: "Bedroom 2 › Window 5", "Bedroom 2", "Stair 1"; for a
    row about no one part, the rule's part kind ("Stairs")."""
    names = [row["within"]["name"]] if row.get("within") else []
    names += [row["name"]] if row.get("name") else []
    if names:
        return " › ".join(names)
    return (row["part"].replace("_", " ").capitalize() + "s") if isinstance(row.get("part"), str) else "Parts"


def line(row: dict, rule: dict, values: dict, allowed: dict) -> str:
    """One line naming the part and why: "Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft"."""
    head = label(row)
    if row["reason"]:
        return f"{head}: {row['reason']}"
    if row["outcome"] == "fail":
        known = {**parts.building_values(values), **row["values"]}
        return f"{head}: {_first_failing(rule, known, allowed) or rule['title']}"
    if row["outcome"] == "needs_review":
        missing = [m for m, v in row["values"].items() if not _usable(v)]
        if missing:
            return f"{head}: {', '.join(_words(rule, m) for m in missing)} not measured (or not usable)"
        return f"{head}: {rule['title']}: needs review"
    return f"{head}: {rule['title']}" + (": complies" if row["outcome"] == "pass" else ": not applicable")


def _usable(v) -> bool:
    """A value a formula can use (formula._measure's test, kind aside): text, yes/no, or a finite number ≥ 0."""
    return type(v) in (str, bool) or type(v) in (int, float) and v == v and abs(v) != float("inf") and v >= 0


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
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.left, ast.Name)
                and type(node.ops[0]) in SIGNS):
            continue
        if part_outcome({**rule, "check": ast.unparse(node), "review_when": []}, values, allowed) != "fail":
            continue
        name, need = node.left.id, _value(ast.unparse(node.comparators[0]), values, rule, allowed)
        if need is None:
            continue
        return f"{_words(rule, name)} {_n(values.get(name))}{_unit(rule, name)}, needs {SIGNS[type(node.ops[0])]} " \
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
