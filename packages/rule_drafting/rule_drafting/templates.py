"""Turn a drafted template into rules (plain code, no AI).

A template is what the AI drafts: a rule whose numbers from the chart are written as slots, e.g.
`front_yard >= {front}` with the slot `front` = the first number of the "Front (minimum)" cell. This module
fills the slots from each district's own cell and cites that cell, so every number in a chart rule comes
from the chart reader. A template with no slots is one rule for every district (`general`).
"""

import ast
import re

from rule_format import formula
from rule_format.rulebook import district_name

from .chart_values import fill, number_text

SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")
CHART_FILE = "zoning_charts_2026-04.pdf"


def formula_fields(template: dict) -> list[tuple[tuple, str]]:
    """(key, formula) for each formula that ends up in the rule: ("applies_when",), ("review_when", i), and
    ("check",) for a rule only (a flag has none)."""
    out = [(("applies_when",), template.get("applies_when", ""))]
    out += [(("review_when", i), r["when"]) for i, r in enumerate(template.get("review_when", []))]
    if template.get("kind") == "rule":
        out.append((("check",), template.get("check", "")))
    return [(k, t) for k, t in out if t.strip()]


def live_formulas(template: dict) -> list[str]:
    return [t for _, t in formula_fields(template)]


def formula_slots(template: dict) -> set[str]:
    """The slots the rule's own formulas use."""
    return {n for t in live_formulas(template) for n in SLOT.findall(t)}


def number_places(template: dict) -> list[tuple[tuple, str, float, set[tuple[str, int]]]]:
    """(key, formula, number, the slot occurrences it stands with) for every number typed in the rule's own
    formulas (not 0). An occurrence is (slot name, its position among the formula's slots). A number stands with
    a slot occurrence when the two are directly related: operands of the same arithmetic or min/max
    (`max(min({pct} * lot_depth, {cap}), 20)`: 20 stands with {cap}), or the number is in the condition that
    picks the branch the occurrence is in (`{first} if sleeping_rooms <= 3 else ...`). Not when they are only
    in the same and/or, the same comparison's two sides, or when the slot only gates the number's branch."""
    out = []
    for key, t in formula_fields(template):
        counter = iter(range(10_000))
        try:
            tree = formula.parse(SLOT.sub(lambda m: f"slot__{m[1]}__{next(counter)}", t))
        except formula.FormulaError:
            continue                                     # reported when the rule is checked
        paths, stack = {}, []

        def walk(node):
            stack.append(node)
            paths[id(node)] = list(stack)
            for child in ast.iter_child_nodes(node):
                walk(child)
            stack.pop()
        walk(tree.body)
        nodes = list(ast.walk(tree.body))
        slots = [n for n in nodes if isinstance(n, ast.Name) and n.id.startswith("slot__")]
        for n in nodes:
            if isinstance(n, ast.Constant) and type(n.value) in (int, float) and n.value != 0:
                near = set()
                for o in slots:
                    if _stands_with(paths[id(n)], paths[id(o)]):
                        name, k = o.id[6:].rsplit("__", 1)
                        near.add((name, int(k)))
                out.append((key, t, n.value, near))
    return out


def with_occurrence_nudged(template: dict, key: tuple, k: int) -> dict:
    """The template with only the k-th slot of one formula changed (x becomes x * 1.5 + 1), to test whether
    that one occurrence decides anything."""
    counter = iter(range(10_000))

    def nudge(text):
        return SLOT.sub(lambda m: f"({{{m[1]}}} * 1.5 + 1)" if next(counter) == k else m[0], text)
    out = dict(template)
    if key[0] == "review_when":
        out["review_when"] = [dict(r) for r in template["review_when"]]
        out["review_when"][key[1]]["when"] = nudge(template["review_when"][key[1]]["when"])
    else:
        out[key[0]] = nudge(template[key[0]])
    return out


def _stands_with(number_path: list, slot_path: list) -> bool:
    i = 0
    while i < min(len(number_path), len(slot_path)) and number_path[i] is slot_path[i]:
        i += 1
    common = number_path[i - 1]                          # the smallest expression holding both
    if isinstance(common, (ast.BinOp, ast.UnaryOp, ast.Call)):
        return True
    if isinstance(common, ast.IfExp):                    # the number picks the branch the slot is in
        return number_path[i] is common.test and slot_path[i] is not common.test
    return False


def slot_names(template: dict) -> set[str]:
    """Every slot the template refers to, its examples' values included."""
    examples = [g["value"] for ex in template.get("examples", []) for g in ex["given"]]
    return formula_slots(template) | {n for t in examples for n in SLOT.findall(t)}


def template_problems(template: dict) -> list[str]:
    """Shape problems a template has before any filling: slots used but not defined, defined twice, or defined
    but used by no formula (a slot's footnotes and row label count as evidence for the rule's typed numbers, so a
    slot that decides nothing could lend a cell's note to a number it has nothing to do with)."""
    defined = [s["name"] for s in template["slots"]]
    p = [f"slot {{{n}}} is used but not defined in 'slots'" for n in sorted(slot_names(template) - set(defined))]
    p += [f"slot {n!r} is defined but no formula uses it (check, applies_when, review_when)"
          for n in sorted(set(defined) - formula_slots(template))]
    if template["kind"] == "flag" and template.get("check", "").strip():
        p.append("a flag has no check (an architect decides it): leave check empty")
    p += [f"slot {n!r} is defined twice" for n in sorted({n for n in defined if defined.count(n) > 1})]
    p += [f"slot {s['name']!r}: footnote {f!r} must be the note's number, like \"16\""
          for s in template["slots"] for f in s["footnotes"] if not re.fullmatch(r"\d+", f)]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", template["id_suffix"]):
        p.append(f"id_suffix {template['id_suffix']!r} must be lowercase_with_underscores")
    return p


def _substitute(text: str, values: dict[str, float]) -> str:
    return SLOT.sub(lambda m: number_text(values[m[1]]), text)


def _example_value(text: str, values: dict[str, float]):
    """An example value as written by the drafter: true/false, a number or arithmetic on slots
    ("{front} - 1"), or text (a use name, a district)."""
    t = text.strip()
    if t.lower() in ("true", "false"):
        return t.lower() == "true"
    if SLOT.search(t) or re.fullmatch(r"[\d.\s+\-*/()]+", t):
        n = formula.evaluate(_substitute(t, values), {}, {})
        if type(n) not in (int, float):                    # "()" or "[]" is not a number
            raise formula.EvaluationError(f"example value {text!r} isn't a number")
        return int(n) if float(n).is_integer() else round(n, 10)
    return t


def fill_template(template: dict, column: str | None, cells: dict, quote_sources: list[dict],
                  drafted_by: str) -> tuple[dict | None, str | None]:
    """(the rule for this district column, None), or (None, why it can't be filled). With column None the
    template must have no slots, and the rule is a general one."""
    values, cell_sources = {}, []
    for slot in template["slots"]:
        key = (slot["page"], slot["section"], slot["row"].strip(), column)
        n, why = fill(slot, cells.get(key))
        if why:
            return None, f"{slot['row']!r}: {why}"
        values[slot["name"]] = n
        source = {"file": CHART_FILE, "page": slot["page"],
                  "cell": {"section": slot["section"], "row": slot["row"].strip(), "column": column}}
        if source not in cell_sources:
            cell_sources.append(source)
    district = district_name(column) if column else "general"
    rule = {"id": f"{district}.{template['id_suffix']}", "kind": template["kind"], "topic": template["topic"],
            "title": template["title"]}
    if template.get("applies_when", "").strip():
        rule["applies_when"] = _substitute(template["applies_when"], values)
    if template["kind"] == "rule":
        rule["check"] = _substitute(template["check"], values)
    if template.get("review_when"):
        rule["review_when"] = [{"when": _substitute(r["when"], values), "reason": r["reason"]} for r in template["review_when"]]
    rule["sources"] = cell_sources + quote_sources
    try:
        rule["examples"] = [{"given": {g["measure"]: _example_value(g["value"], values) for g in ex["given"]},
                             "expect": ex["expect"]} for ex in template["examples"]]
    except (formula.FormulaError, formula.EvaluationError, formula.MissingMeasure) as e:
        return None, f"an example value can't be worked out: {e}"
    if template.get("open_questions"):
        rule["open_questions"] = list(template["open_questions"])
    rule["notes"] = (f"Drafted by the rule-drafting script; numbers filled by code from the {district} cells."
                     if column else "Drafted by the rule-drafting script.")
    rule |= {"drafted_by": drafted_by, "status": "draft"}
    return rule, None
