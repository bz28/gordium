"""Draft rules with one recorded AI call per unit, and check every answer with code.

A unit is one chart section (e.g. page 3, "Yard Dimensions") or one piece of the law labeled rule or
flag. For one unit:
  1. Send the fixed instructions (drafting_rules.md, the rule format, every measure, use, district and
     topic, and the residential chart's rows; cached, so repeats are cheap) and the unit's text, with the
     footnotes and sections of the law it points to and the definitions it uses.
  2. The model must answer with rule templates (structured output: no other shape is possible). Chart
     numbers are slots, never typed; code fills them from each district's own cell (templates.py).
  3. Code resolves every quote to its exact lines, fills the slots, and runs the inspector on every rule.
     If no rule passes, the model is told why and asked again (up to max_attempts); after that the unit
     is listed for a person. Districts whose cells don't fit a template are listed for a person too.
  4. Every attempt is recorded: settings, prompt and input fingerprints, the raw answer, tokens, cost.

The hand-drafted R-1b rulebook is never shown to the model: it is the answer key the drafts are graded on.
The client is passed in, so tests use a fake one and never need a key or the network.
"""

import datetime
import json
import re
from pathlib import Path

import yaml

from document_extraction.sections import piece_text
from rule_format.rulebook import (MEASURES_FILE, REPO, VOCABULARY_FILE, Context, _source_problems, district_name,
                                  locate, validate)
from section_labeling.budget import worst_case
from section_labeling.labeler import cost, find_quote, sha

from .chart_values import section_refs
from .templates import CHART_FILE, fill_template, template_problems

HERE = Path(__file__).parent
GUIDE_FILE = REPO / "regulations/document_extraction_guide/drafting_rules.md"
SETTINGS = yaml.safe_load((HERE / "settings.yaml").read_text())
PRICES = yaml.safe_load((REPO / "packages/section_labeling/section_labeling/prices.yaml").read_text())
UNITS = ("ft", "sf", "count", "text", "yes_no")
OUTCOMES = ["pass", "fail", "needs_review", "not_applicable"]

FORMAT = """\
## What to write

Answer with rule templates in the JSON shape required. Each template becomes one rule per district (when
it has slots) or one rule for every district (when it has none).

- kind: "rule" when code can decide it from measurements; "flag" when it needs an architect's judgment
  (a flag has no check: leave check "").
- check / applies_when / review_when.when: formulas in the formula language. Allowed: measure names,
  numbers, quoted text ("one_family_detached", "R-1b"), + - * /, < <= > >= == !=, in / not in a [list],
  and / or / not, `a if condition else b`, min(a, b, ...) and max(a, b, ...). A yes/no measure is a test on
  its own (`adu_separate_entrance`). check and applies_when must be true/false tests.
- Use only the measures listed below. If a rule needs a fact that isn't listed, name it in new_measures
  (lowercase_with_underscores, a unit from ft, sf, count, text, yes_no, and what it means); an engineer
  adds it before the rule can be approved. Never invent a measure without listing it there.
- Numbers. A number that comes from the zoning chart is never typed: write a slot {name} and define it in
  slots: the chart page, section and row label exactly as listed, which number in the cell (1 = first),
  how many numbers the cell must have, whether that number is a percent, and the footnote markers the cell
  must carry (["16"] for "50 ft [fn16]"). Code fills the slot from each district's own cell; a district
  whose cell doesn't have that shape gets no rule and goes to a person. Any other number must be written
  in one of your quotes (a percent like 10% is written 0.1; "three" counts as 3). Work numbers out in the
  formula itself from quoted inputs (35 + 0.1 * 35), never as a result (38.5).
- quotes: the exact words that support the rule, as whole sentences, copied character for character
  (footnote markers like [fn11] included). document "chart" for a footnote or line on the chart page given;
  document "law" with the piece id for text from a piece of the law given here. A quote must occur once.
- examples: at least one that passes and one that fails (for a rule). Each given value is text: a number,
  arithmetic on slots ("{front} - 1"), true or false, a use id or a district name.
- open_questions: anything the law leaves unclear, for the architects. Never settle it in the formula.
- id_suffix: lowercase_with_underscores; the rule's id is the district (or "general") plus this suffix.
- If the text sets nothing for the residential districts listed (it is only for other districts, or only
  procedure), return no templates and say why in no_rule_reason.
"""


def output_schema(topics: list[str]) -> dict:
    text = {"type": "string"}
    slot = {"type": "object", "additionalProperties": False,
            "required": ["name", "page", "section", "row", "number", "numbers_in_cell", "percent", "footnotes"],
            "properties": {"name": text, "page": {"type": "integer"}, "section": text, "row": text,
                           "number": {"type": "integer"}, "numbers_in_cell": {"type": "integer"},
                           "percent": {"type": "boolean"}, "footnotes": {"type": "array", "items": text}}}
    template = {"type": "object", "additionalProperties": False,
                "required": ["id_suffix", "title", "topic", "kind", "applies_when", "check", "slots", "review_when",
                             "quotes", "examples", "open_questions", "new_measures"],
                "properties": {
                    "id_suffix": text, "title": text, "topic": {"type": "string", "enum": topics},
                    "kind": {"type": "string", "enum": ["rule", "flag"]}, "applies_when": text, "check": text,
                    "slots": {"type": "array", "items": slot},
                    "review_when": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["when", "reason"],
                        "properties": {"when": text, "reason": text}}},
                    "quotes": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["document", "piece", "text"],
                        "properties": {"document": {"type": "string", "enum": ["chart", "law"]}, "piece": text, "text": text}}},
                    "examples": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["given", "expect"],
                        "properties": {"given": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False, "required": ["measure", "value"],
                            "properties": {"measure": text, "value": text}}},
                            "expect": {"type": "string", "enum": OUTCOMES}}}},
                    "open_questions": {"type": "array", "items": text},
                    "new_measures": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["name", "unit", "meaning"],
                        "properties": {"name": text, "unit": {"type": "string", "enum": list(UNITS)}, "meaning": text}}}}}
    return {"type": "json_schema", "schema": {
        "type": "object", "additionalProperties": False, "required": ["templates", "no_rule_reason"],
        "properties": {"templates": {"type": "array", "items": template}, "no_rule_reason": text}}}


def chart_table(sections: list[tuple[int, str]], rows_of) -> str:
    """Every chart row the drafter may make a slot from, with each district's value."""
    out = []
    for page, section in sections:
        out.append(f"\nPage {page}, section {section!r}:")
        for label, cells in rows_of(page, section).items():
            out.append(f"- row {label!r}: " + " | ".join(f"{col}: {c['value']}" for col, c in cells.items()))
    return "\n".join(out)


def system_prompt(ctx: Context, uses: dict, districts: list[str], table: str) -> str:
    """The fixed instructions: identical for every unit, so they're cached after the first call."""
    measures = yaml.safe_load(MEASURES_FILE.read_text())
    topics = yaml.safe_load(VOCABULARY_FILE.read_text())["topics"]
    return (f"{GUIDE_FILE.read_text()}\n{FORMAT}\n## Measures (with units)\n"
            + "\n".join(f"- {n} ({m['unit']}): {m['meaning']}" for n, m in measures.items())
            + "\n\n## Use ids (for the use measure)\n" + "\n".join(f"- {k}: {v['name']}" for k, v in uses.items())
            + "\n\n## Residential districts (for the district measure: write them like this)\n"
            + ", ".join(districts)
            + "\n\n## Topics\n" + "\n".join(f"- {k}: {' '.join(v.split())}" for k, v in topics.items())
            + "\n\n## The zoning chart's rows (for slots)" + table + "\n")


def _sentences(text: str) -> str:
    return " ".join(text.split())


def unit_message(unit: dict, context: dict) -> str:
    """The unit's own text plus what it points to: footnotes, sections of the law, definitions."""
    parts = [unit["intro"], unit["text"]]
    if context["notes"]:
        parts.append("Footnotes under the chart (document \"chart\"):\n" + "\n".join(
            f"- page {n['page']}: {n['text']}" for n in context["notes"]))
    if context["pieces"]:
        parts.append("Sections of the law it points to (document \"law\", by piece id):\n" + "\n\n".join(
            f"[piece {p['id']}] {p['title']}\n{p['text']}" for p in context["pieces"]))
    if context["definitions"]:
        parts.append("Definitions used (for meaning; quote them only if a rule rests on them):\n" + "\n".join(
            f"- {d}" for d in context["definitions"]))
    return "\n\n".join(parts)


def gather_context(unit: dict, law: dict, chart: dict, definitions: dict) -> dict:
    """Footnotes, sections and definitions the unit's text points to. law: {file, pieces, rows};
    chart: {notes: {page: {n: note}}}."""
    text = unit["text"]
    markers = sorted({n for m in re.findall(r"\[fn([^\]]*)\]", text) for n in m.split(",") if n.strip()}, key=int)
    notes = [{"page": unit["page"], **chart["notes"][unit["page"]][n]} for n in markers
             if unit.get("page") in chart["notes"] and n in chart["notes"][unit["page"]]]
    refs = section_refs(text + " " + " ".join(n["text"] for n in notes))
    pieces, size = [], 0
    for ref in refs:
        for pid, piece in law["pieces"].items():
            if (pid == ref or pid.startswith(ref) and not pid[len(ref):len(ref) + 1].isdigit()) \
                    and pid != unit.get("piece") and all(p["id"] != pid for p in pieces):
                body = piece_text(law["rows"], piece)
                if size + len(body) > 20_000:
                    break
                pieces.append({"id": pid, "title": piece["title"], "text": body})
                size += len(body)
    lower = text.lower()
    defs = [f"{v['term']}: " + " ".join(_sentences(s["quote"]) for s in v["sources"])
            for v in definitions.values() if v["term"].split("(")[0].strip().lower() in lower]
    return {"notes": notes, "pieces": pieces, "definitions": defs}


def resolve_quotes(template: dict, unit: dict, context: dict, law: dict, ctx: Context) -> tuple[list[dict], list[str]]:
    """Each quote as a source with its exact lines: a chart footnote on the unit's chart page, or text inside
    the unit's own piece or a piece it points to."""
    sources, p = [], []
    allowed = {unit["piece"]} if unit.get("piece") else set()
    allowed |= {x["id"] for x in context["pieces"]}
    for q in template["quotes"]:
        if q["document"] == "chart":
            page = unit.get("page")
            found = locate(q["text"], ctx.pages.get(CHART_FILE, {}).get(page, {})) if page else []
            if len(found) != 1:
                p.append(f"chart quote {q['text']!r} occurs {len(found)} times on chart page {page}; quote it exactly, once")
                continue
            source = {"file": CHART_FILE, "page": page, "lines": list(found[0]), "quote": q["text"]}
            if problems := _source_problems([source], ctx):
                p += problems
                continue
        else:
            if q["piece"] not in allowed:
                p.append(f"law quote cites piece {q['piece']!r}, which isn't one given here ({sorted(allowed)})")
                continue
            source, why = find_quote(q["text"], law["pieces"][q["piece"]], law["file"], ctx)
            if why:
                p.append(f"law quote {q['text']!r} in piece {q['piece']}: {why}")
                continue
        if source not in sources:
            sources.append(source)
    return sources, p


def check_answer(answer: dict, unit: dict, context: dict, law: dict, ctx: Context, columns: list[str],
                 cells: dict, drafted_by: str) -> dict:
    """Turn an answer into rules, every one checked by the inspector.
    Returns {rules: {district: [rule]}, unresolved: [{rule, why}], proposed: {name: measure}, problems: [...]}."""
    out = {"rules": {}, "unresolved": [], "proposed": {}, "problems": [], "templates": []}
    for t in answer["templates"]:
        t = t | {"id_suffix": unit.get("prefix", "") + t["id_suffix"]}   # a law piece's rules carry its id
        p = template_problems(t)
        for m in t["new_measures"]:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", m["name"]):
                p.append(f"new measure {m['name']!r} must be lowercase_with_underscores")
            elif m["name"] not in ctx.measures:
                out["proposed"][m["name"]] = {"unit": m["unit"], "meaning": m["meaning"]}
        sources, quote_problems = resolve_quotes(t, unit, context, law, ctx)
        p += quote_problems
        if p:
            out["problems"] += [f"{t['id_suffix']}: {x}" for x in p]
            continue
        saved, ctx.proposed = ctx.proposed, ctx.proposed | out["proposed"]
        good, gaps = [], []                     # filled and valid; or (where, why) for a person
        for column in (columns if t["slots"] else [None]):
            rule, why = fill_template(t, column, cells, sources, drafted_by)
            if why is None and (problems := validate({"district": rule["id"].split(".")[0], "rules": [rule]}, ctx)):
                why = "; ".join(problems[:3])
            if why is None:
                good.append(rule)
            else:
                gaps.append({"rule": f"{district_name(column) if column else 'general'}.{t['id_suffix']}", "why": why})
        ctx.proposed = saved
        if good:                                # the template works: districts that don't fit go to a person
            out["templates"].append(t)
            for rule in good:
                out["rules"].setdefault(rule["id"].split(".")[0], []).append(rule)
            out["unresolved"] += gaps
        else:                                   # it works nowhere: the drafter is told why and tries again
            out["problems"] += [f"{g['rule']}: {g['why']}" for g in gaps[:3]]
    return out


def draft_unit(client, unit: dict, context: dict, system: str, law: dict, ctx: Context, columns: list[str],
               cells: dict, record, settings: dict = SETTINGS, budget=None) -> dict:
    """Draft one unit. Returns check_answer's result plus {"reason"} (no rules, and why) or
    {"failed": why} when no usable answer came back."""
    topics = sorted(ctx.topics)
    drafted_by = f"rule_drafting/{settings['model']}"
    messages = [{"role": "user", "content": unit_message(unit, context)}]
    why = "no answer"
    for attempt in range(1, settings["max_attempts"] + 1):
        worst = worst_case(len(system) + len(json.dumps(messages, default=str)), settings, PRICES)
        if budget is not None:
            budget.reserve(worst)
        response = client.messages.create(                   # if this raises, the worst case stays charged
            model=settings["model"], max_tokens=settings["max_tokens"],
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            output_config={"effort": settings["effort"], "format": output_schema(topics)})
        usage = {k: getattr(response.usage, k, 0) or 0 for k in
                 ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
        spent = cost(usage, settings["model"])
        if budget is not None:
            budget.settle(worst, spent)
        text = next((b.text for b in response.content if b.type == "text"), "")
        result = None
        if response.stop_reason != "end_turn":
            why = f"stopped early ({response.stop_reason})"
        else:
            try:
                answer = json.loads(text)
                result = check_answer(answer, unit, context, law, ctx, columns, cells, drafted_by)
                if result["rules"] or (not answer["templates"] and answer["no_rule_reason"].strip()):
                    why = None
                    result["reason"] = answer["no_rule_reason"].strip()
                else:
                    why = "; ".join(result["problems"][:6]) or "no template produced a valid rule"
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                why = f"unreadable answer ({type(e).__name__})"
        record({"unit": unit["id"], "attempt": attempt, "date": datetime.datetime.now(datetime.UTC).isoformat(),
                "model": settings["model"], "effort": settings["effort"], "max_tokens": settings["max_tokens"],
                "system_sha256": sha(system), "input_sha256": sha(json.dumps(messages, sort_keys=True, default=str)),
                "request_id": getattr(response, "_request_id", None), "stop_reason": response.stop_reason,
                "answer": text, "problem": why, "usage": usage, "cost_usd": round(spent, 6),
                "budget_usd": settings["budget_usd"], "ledger_spent_usd": round(budget.spent, 6) if budget else None})
        if why is None:
            return result
        if response.stop_reason == "refusal":
            break
        if response.stop_reason == "end_turn":
            messages += [{"role": "assistant", "content": response.content},
                         {"role": "user", "content": f"That answer can't be used: {why}. Answer again for the same text."}]
    return {"failed": why, "rules": {}, "unresolved": [], "proposed": {}, "problems": [], "templates": []}
