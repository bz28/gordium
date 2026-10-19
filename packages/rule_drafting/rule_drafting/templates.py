"""Turn a drafted template into rules (plain code, no AI).

A template is what the AI drafts: a rule whose numbers from the chart are written as slots, e.g.
`front_yard >= {front}` with the slot `front` = the first number of the "Front (minimum)" cell. This module
fills the slots from each district's own cell and cites that cell, so every number in a chart rule comes
from the chart reader. A template with no slots is one rule for every district (`general`).
"""

import re

from rule_format import formula
from rule_format.rulebook import district_name

from .chart_values import fill, number_text

SLOT = re.compile(r"\{([a-z][a-z0-9_]*)\}")
CHART_FILE = "zoning_charts_2026-04.pdf"


def slot_names(template: dict) -> set[str]:
    texts = [template.get("check", ""), template.get("applies_when", "")]
    texts += [r["when"] for r in template.get("review_when", [])]
    texts += [g["value"] for ex in template.get("examples", []) for g in ex["given"]]
    return {n for t in texts for n in SLOT.findall(t)}


def template_problems(template: dict) -> list[str]:
    """Shape problems a template has before any filling: slots used but not defined, or defined twice."""
    defined = [s["name"] for s in template["slots"]]
    p = [f"slot {{{n}}} is used but not defined in 'slots'" for n in sorted(slot_names(template) - set(defined))]
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
