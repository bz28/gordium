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
                                  locate, outcome, source_numbers, validate)
from section_labeling.budget import worst_case
from section_labeling.labeler import cost, find_quote, sha

from .chart_values import section_refs
from .chart_values import footnotes
from .templates import (CHART_FILE, fill_template, formula_slots, number_places, template_problems,
                        with_occurrence_nudged)

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
  formula itself from quoted inputs (0.02 * 1000), never as a result (20). A number you type must be
  written in a law sentence you quote, in a footnote of one of your slots, or in a slot's row label; a
  number from a chart cell is always a slot, never typed. A percent is typed as its fraction (2% is 0.02).
- numbers: one entry for every number you type in applies_when, check or review_when (not slots, not 0),
  naming where it is written: {value, from: "law_quote", quote: <index in quotes>, slot: "", footnote: ""},
  or {value, from: "slot_footnote", quote: -1, slot: <slot name>, footnote: <note number>}, or
  {value, from: "slot_row_label", quote: -1, slot: <slot name>, footnote: ""}. A slot's footnote or row
  label backs a number only where the number stands with that slot: in the same arithmetic or min/max, or in
  the condition that picks the slot's value, and only where that slot occurrence decides something. Each place
  a number is typed is checked on its own. A number backed by a chart note or row label is sent to an
  architect as an open question (code can't tell what the note's number is about): prefer a law quote.
- Every slot must decide something: changing its value must change some worked example's outcome.
- Footnotes: a chart cell's footnote marker ([fn16]) points to a note printed under that page's table
  (listed below). Every footnote on a slot's cell, its row label or its section heading has to be quoted,
  and applied in the rule.
- quotes: the exact words that support the rule, as whole sentences, copied character for character
  (footnote markers like [fn11] included). document "chart" only for a footnote under a chart table, with
  its page; document "law" with the piece id for text from a piece of the law given here (page 0). A quote
  must occur once.
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
                             "quotes", "numbers", "examples", "open_questions", "new_measures"],
                "properties": {
                    "id_suffix": text, "title": text, "topic": {"type": "string", "enum": topics},
                    "kind": {"type": "string", "enum": ["rule", "flag"]}, "applies_when": text, "check": text,
                    "slots": {"type": "array", "items": slot},
                    "review_when": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["when", "reason"],
                        "properties": {"when": text, "reason": text}}},
                    "quotes": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False, "required": ["document", "page", "piece", "text"],
                        "properties": {"document": {"type": "string", "enum": ["chart", "law"]}, "page": {"type": "integer"},
                                       "piece": text, "text": text}}},
                    "numbers": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "required": ["value", "from", "quote", "slot", "footnote"],
                        "properties": {"value": {"type": "number"},
                                       "from": {"type": "string", "enum": ["law_quote", "slot_footnote", "slot_row_label"]},
                                       "quote": {"type": "integer"}, "slot": text, "footnote": text}}},
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


def chart_notes(notes: dict[int, dict]) -> str:
    """The footnotes printed under each chart table, by page."""
    return "\n".join(f"- page {page}: {n['text']}" for page, by_number in sorted(notes.items())
                     for n in by_number.values())


def system_prompt(ctx: Context, uses: dict, districts: list[str], table: str, notes: dict[int, dict]) -> str:
    """The fixed instructions: identical for every unit, so they're cached after the first call."""
    measures = yaml.safe_load(MEASURES_FILE.read_text())
    topics = yaml.safe_load(VOCABULARY_FILE.read_text())["topics"]
    return (f"{GUIDE_FILE.read_text()}\n{FORMAT}\n## Measures (with units)\n"
            + "\n".join(f"- {n} ({m['unit']}): {m['meaning']}" for n, m in measures.items())
            + "\n\n## Use ids (for the use measure)\n" + "\n".join(f"- {k}: {v['name']}" for k, v in uses.items())
            + "\n\n## Residential districts (for the district measure: write them like this)\n"
            + ", ".join(districts)
            + "\n\n## Topics\n" + "\n".join(f"- {k}: {' '.join(v.split())}" for k, v in topics.items())
            + "\n\n## The zoning chart's rows (for slots)" + table
            + "\n\n## Footnotes under the chart tables (document \"chart\", with the page)\n" + chart_notes(notes) + "\n")


def _sentences(text: str) -> str:
    return " ".join(text.split())


def numbered_text(lines: list[tuple[int, int, str]]) -> str:
    """A law piece's whole text, every line numbered L1, L2, ..., with a '--- page N ---' line at each page break
    (the labeler's numbering, so a line is called the same in both steps)."""
    out, page = [], None
    for i, (p, _, text) in enumerate(lines, 1):
        if page is not None and p != page:
            out.append(f"--- page {p} ---")
        page = p
        out.append(f"L{i}: {text}")
    return "\n".join(out)


def unit_message(unit: dict, context: dict) -> str:
    """The unit's whole text (a law piece's every line, numbered) plus what it points to: the lines its label
    cites (hints only), footnotes, sections of the law, definitions."""
    number = {(p, n): i for i, (p, n, _) in enumerate(unit.get("lines", []), 1)}
    if unit.get("lines"):
        parts = [unit["intro"] + " Its whole text follows, every line numbered L1, L2, ... (the numbers are not part "
                 "of the city's words: never put them in a quote). A '--- page N ---' line marks a page break; a quote "
                 "can't run across one. Draft every requirement in the whole text.", numbered_text(unit["lines"])]
    else:
        parts = [unit["intro"], unit["text"]]
    if unit.get("requirements"):
        def where(s):
            first, last = number.get((s["page"], s["lines"][0])), number.get((s["page"], s["lines"][1]))
            return f"L{first}-L{last}" if first and last else f"page {s['page']}, lines {s['lines'][0]}-{s['lines'][1]}"
        parts.append("Lines its reviewed label cites (hints only: a label may cite just a heading or a lead-in, so "
                     "don't stop at these; every requirement in the whole text needs a rule):\n" + "\n".join(
                         f"- {where(s)}: {s['quote']}" for s in unit["requirements"]))
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


def _within(lines: list[int], span: list[int]) -> bool:
    return span[0] <= lines[0] and lines[1] <= span[1]


def resolve_quotes(template: dict, unit: dict, context: dict, law: dict, ctx: Context,
                   notes: dict[int, dict]) -> tuple[list[dict], list[str]]:
    """Each quote as a source with its exact lines. A chart quote must be a footnote printed under a chart
    table (never a table row: a row's numbers reach a rule only through a slot filled from the district's own
    cell). A law quote must be inside the unit's own piece or a piece it points to."""
    sources, p = [], []
    allowed = {unit["piece"]} if unit.get("piece") else set()
    allowed |= {x["id"] for x in context["pieces"]}
    for q in template["quotes"]:
        if q["document"] == "chart":
            page = q.get("page") or unit.get("page")
            found = locate(q["text"], ctx.pages.get(CHART_FILE, {}).get(page, {})) if page else []
            if len(found) != 1:
                p.append(f"chart quote {q['text']!r} occurs {len(found)} times on chart page {page}; quote it exactly, once")
                continue
            lines = list(found[0])
            if not any(_within(lines, n["lines"]) for n in notes.get(page, {}).values()):
                p.append(f"chart quote {q['text']!r} isn't a footnote under the table on page {page}; chart numbers "
                         "come only from slots")
                continue
            source = {"file": CHART_FILE, "page": page, "lines": lines, "quote": q["text"]}
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


def _footnote_problems(template: dict, sources: list[dict], notes: dict[int, dict]) -> list[str]:
    """Every footnote a slot's cell, row or section carries is quoted: the note changes what the number means
    ("(16) But not less than 20 ft."), so a rule that fills the number must also apply the note."""
    quoted = [(s["page"], s["lines"]) for s in sources if s.get("file") == CHART_FILE and "lines" in s]
    p = []
    for slot in template["slots"]:
        # the cell's own notes, and the notes on its row label and section heading ("Minimum Lot Size [fn3]")
        for n in sorted(set(slot["footnotes"]) | footnotes(slot["row"]) | footnotes(slot["section"]),
                        key=lambda n: (len(n), n)):
            note = notes.get(slot["page"], {}).get(n)
            if note is None:
                p.append(f"slot {slot['name']}: footnote {n} isn't under the table on page {slot['page']}")
            elif not any(page == slot["page"] and _within(lines, note["lines"]) for page, lines in quoted):
                p.append(f"slot {slot['name']}: footnote {n} of {slot['row']!r} isn't quoted: {note['text']!r}")
    return p


def slot_notes(template: dict) -> set[tuple[int, str]]:
    """(page, footnote) for every note on a slot's cell, row label or section heading ("Minimum Lot Size [fn3]")."""
    return {(slot["page"], n) for slot in template["slots"]
            for n in set(slot["footnotes"]) | footnotes(slot["row"]) | footnotes(slot["section"])}


def _binding_items(template: dict, notes: dict[int, dict]) -> tuple[list[str], list[dict]]:
    """Check each entry of `numbers` names ONE evidence item that holds its value:
    - law_quote: the quote at that index is a sentence of the law (a chart quote is a footnote, and backs a
      number only as its slot's footnote);
    - slot_footnote: a footnote on that slot's own cell, row or section;
    - slot_row_label: that slot's row label ("First three bed or sleeping rooms").
    A number that only labels or points ("(3)", "§ 325-20D(1)") doesn't count; a percent counts only as its
    fraction (25% is 0.25). Returns (problems, the valid entries with their evidence text)."""
    slots = {s["name"]: s for s in template["slots"]}
    live = formula_slots(template)
    p, valid = [], []
    for i, b in enumerate(template.get("numbers", [])):
        v, where = b["value"], f"numbers[{i}] ({b['value']:g} from {b['from']})"
        if b["from"] == "law_quote":
            q = template["quotes"][b["quote"]] if 0 <= b["quote"] < len(template["quotes"]) else None
            if q is None or q["document"] != "law":
                p.append(f"{where}: quote {b['quote']} isn't one of this template's law quotes")
                continue
            text = q["text"]
        else:
            slot = slots.get(b["slot"])
            if slot is None or b["slot"] not in live:
                p.append(f"{where}: slot {b['slot']!r} isn't one this rule's formulas use")
                continue
            if b["from"] == "slot_row_label":
                text = slot["row"]
            else:
                own = set(slot["footnotes"]) | footnotes(slot["row"]) | footnotes(slot["section"])
                note = notes.get(slot["page"], {}).get(b["footnote"])
                if b["footnote"] not in own or note is None:
                    p.append(f"{where}: footnote {b['footnote']!r} isn't on slot {b['slot']!r}'s cell, row or section")
                    continue
                text = note["text"]
        if not v_close(v, source_numbers(text, percent_as_number=False)):
            p.append(f"{where}: {v:g} isn't written in it: {text!r}")
            continue
        valid.append(b | {"text": text})
    for _, text, n, near in number_places(template):           # (whether a backing slot decides: after filling)
        if not any(abs(b["value"] - n) < 1e-9 and (b["from"] == "law_quote" or b["slot"] in {s for s, _ in near})
                   for b in valid):
            p.append(_unbacked(n, text))
    return p, valid


def _unbacked(n: float, text: str) -> str:
    return (f"number {n:g} in {text!r} isn't backed where it stands: bind it to a law quote, or to the footnote or "
            "row label of a slot it stands with (the same arithmetic, or the condition that picks the slot's value) "
            "where that slot decides something; a chart number must be a slot")


def _backing(template: dict, valid: list[dict], filled: list[tuple[str, dict]], cells: dict, sources: list[dict],
             drafted_by: str, allowed: dict) -> tuple[list[str], list[str]]:
    """Every place a number is typed must be backed where it stands. A law quote binding with that value backs
    it. A slot binding backs it only through an occurrence of that slot the number stands with which itself
    decides something: changed alone, some worked example in some district comes out differently (so
    `3 + 0 * {x}` or `min(3, {x})` with a large {x} back nothing there, whatever else {x} does).
    Code can check that a chart note or row label holds the number, never what the number is about (note 7's
    "1-3 units" and the parking row's "First three" look alike), so every number backed only by a slot's
    footnote or row label becomes an open question for an architect; the rule can't be approved until it's
    answered. Returns (problems, open questions)."""
    decides = {}

    def occurrence_decides(key, k):
        if (key, k) not in decides:
            changed = with_occurrence_nudged(template, key, k)
            decides[key, k] = any(
                outcome(new, ex["given"], allowed) != outcome(rule, ex["given"], allowed)
                for column, rule in filled for new in [fill_template(changed, column, cells, sources, drafted_by)[0]]
                if new is not None for ex in rule["examples"])
        return decides[key, k]

    problems, questions = [], []
    for key, text, n, near in number_places(template):
        same = [b for b in valid if abs(b["value"] - n) < 1e-9]
        if any(b["from"] == "law_quote" for b in same):
            continue
        backer = next((b for b in same for name, k in sorted(near)
                       if name == b["slot"] and occurrence_decides(key, k)), None)
        if backer is None:
            problems.append(_unbacked(n, text))
            continue
        what = f"footnote {backer['footnote']}" if backer["from"] == "slot_footnote" else "the row label"
        questions.append(f"The {n:g} in {text!r} was taken from {what} of the chart row {template_slot_row(template, backer['slot'])!r} "
                         f"({backer['text']!r}). Code can't tell what a chart note's number is about: does it mean this here?")
    return problems, questions


def template_slot_row(template: dict, name: str) -> str:
    return next(s["row"] for s in template["slots"] if s["name"] == name)


def v_close(v: float, values) -> bool:
    return any(abs(v - x) < 1e-9 for x in values)


def _idle_slots(template: dict, filled: list[tuple[str, dict]], cells: dict, sources: list[dict], drafted_by: str,
                allowed: dict) -> list[str]:
    """Slots whose value decides nothing: changed in the formulas (not the examples), no worked example in any
    district comes out differently. `0 * {x}`, `{x} == {x}` or a condition no example reaches all land here,
    whatever their shape."""
    idle = []
    for name in sorted(formula_slots(template)):
        if not any(outcome(changed, ex["given"], allowed) != outcome(rule, ex["given"], allowed)
                   for column, rule in filled
                   for changed in [fill_template(template, column, cells, sources, drafted_by, nudge=name)[0]]
                   if changed is not None for ex in rule["examples"]):
            idle.append(f"slot {{{name}}} decides nothing: changing it changes no worked example's outcome")
    return idle


def check_answer(answer: dict, unit: dict, context: dict, law: dict, ctx: Context, columns: list[str],
                 cells: dict, notes: dict[int, dict], drafted_by: str) -> dict:
    """Turn an answer into rules, every one checked by the inspector. Returns {rules: {district: [rule]},
    unresolved: [{rule, why}] (districts whose cells don't fit a working template), rejected: [{rule, why}]
    (templates that work nowhere), proposed: {name: measure}, problems: [...] (the rejections, as text)}."""
    out = {"rules": {}, "unresolved": [], "rejected": [], "proposed": {}, "problems": [], "templates": []}
    suffixes = [unit.get("prefix", "") + t["id_suffix"] for t in answer["templates"]]
    for t in answer["templates"]:
        t = t | {"id_suffix": unit.get("prefix", "") + t["id_suffix"]}   # a law piece's rules carry its id
        p = template_problems(t)
        if suffixes.count(t["id_suffix"]) > 1:
            p.append(f"id_suffix {t['id_suffix']!r} is used by more than one template in this answer")
        proposed = {}
        for m in t["new_measures"]:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", m["name"]):
                p.append(f"new measure {m['name']!r} must be lowercase_with_underscores")
            elif m["name"] not in ctx.measures:
                proposed[m["name"]] = {"unit": m["unit"], "meaning": m["meaning"]}
        sources, quote_problems = resolve_quotes(t, unit, context, law, ctx, notes)
        p += quote_problems + (_footnote_problems(t, sources, notes) if not quote_problems else [])
        binding_problems, valid = _binding_items(t, notes)
        p += binding_problems
        if p:
            out["rejected"].append({"rule": f"{unit['id']}.{t['id_suffix']}", "why": "; ".join(p)})
            continue
        good, gaps = [], []                     # filled and valid; or (where, why) for a person
        saved, ctx.proposed = ctx.proposed, ctx.proposed | proposed
        try:
            for column in (columns if t["slots"] else [None]):
                rule, why = fill_template(t, column, cells, sources, drafted_by)
                if why is None and (problems := validate({"district": rule["id"].split(".")[0], "rules": [rule]}, ctx)):
                    why = "; ".join(problems[:3])
                if why is None:
                    good.append((column, rule))
                else:
                    gaps.append({"rule": f"{district_name(column) if column else 'general'}.{t['id_suffix']}", "why": why})
            if good and (idle := _idle_slots(t, good, cells, sources, drafted_by, ctx.allowed())):
                gaps, good = [{"rule": f"{unit['id']}.{t['id_suffix']}", "why": w} for w in idle], []
            if good:
                unbacked, questions = _backing(t, valid, good, cells, sources, drafted_by, ctx.allowed())
                if unbacked:
                    gaps, good = [{"rule": f"{unit['id']}.{t['id_suffix']}", "why": w} for w in unbacked], []
                for _, rule in good:
                    if questions:
                        rule["open_questions"] = rule.get("open_questions", []) + questions
        finally:
            ctx.proposed = saved
        good = [rule for _, rule in good]
        if good:                                # the template works: districts that don't fit go to a person
            out["templates"].append(t)
            out["proposed"] |= proposed
            for rule in good:
                out["rules"].setdefault(rule["id"].split(".")[0], []).append(rule)
            out["unresolved"] += gaps
        else:                                   # it works nowhere: the drafter is told why and tries again
            out["rejected"].append({"rule": f"{unit['id']}.{t['id_suffix']}",
                                    "why": "; ".join(f"{g['rule']}: {g['why']}" for g in gaps[:3])})
    out["problems"] = [f"{r['rule']}: {r['why']}" for r in out["rejected"]]
    return out


def requirement_gaps(unit: dict, result: dict) -> list[dict]:
    """The lines the unit's label cites that no drafted rule cites: for a person. The label's sources are hints
    (it may cite only a heading), so this can list a line with no rule in it; a person says so. Never silent."""
    cited = {(s["page"], n) for rules in result["rules"].values() for r in rules for s in r["sources"]
             if s.get("file") != CHART_FILE and "lines" in s for n in range(s["lines"][0], s["lines"][1] + 1)}
    return [{"rule": f"{unit['id']}.requirement_p{s['page']}_l{s['lines'][0]}",
             "why": f"the label cites this and no drafted rule does (a person checks whether it sets a rule): {s['quote']!r}"}
            for s in unit.get("requirements", [])
            if not any((s["page"], n) in cited for n in range(s["lines"][0], s["lines"][1] + 1))]


def draft_unit(client, unit: dict, context: dict, system: str, law: dict, ctx: Context, columns: list[str],
               cells: dict, notes: dict[int, dict], record, settings: dict = SETTINGS, budget=None) -> dict:
    """Draft one unit. Every template that works nowhere sends the answer back with the reasons (keeping
    nothing from it) until max_attempts; after the last attempt, the rules that work are kept and every
    rejected template and every requirement no rule cites goes to a person. Returns check_answer's result
    plus "reason" (no rules, and why) or "failed" (no usable answer)."""
    topics = sorted(ctx.topics)
    drafted_by = f"rule_drafting/{settings['model']}"
    messages = [{"role": "user", "content": unit_message(unit, context)}]
    why, last = "no answer", None
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
        result, crash = None, None
        if response.stop_reason != "end_turn":
            why = f"stopped early ({response.stop_reason})"
        else:
            try:
                answer = json.loads(text)
                result = check_answer(answer, unit, context, law, ctx, columns, cells, notes, drafted_by)
                if result["problems"]:
                    why = "; ".join(result["problems"][:6])
                    last = result if result["rules"] else last
                elif result["rules"] or answer["no_rule_reason"].strip():
                    why = None
                    result["reason"] = "" if result["rules"] else answer["no_rule_reason"].strip()
                else:
                    why = "no rules and no reason given"
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                why = f"unreadable answer ({type(e).__name__})"
            except Exception as e:                   # a bug of ours: record the paid attempt, then stop loudly
                why, crash = f"crashed while checking the answer ({type(e).__name__}: {e})", e
        record({"unit": unit["id"], "attempt": attempt, "date": datetime.datetime.now(datetime.UTC).isoformat(),
                "model": settings["model"], "effort": settings["effort"], "max_tokens": settings["max_tokens"],
                "system_sha256": sha(system), "input_sha256": sha(json.dumps(messages, sort_keys=True, default=str)),
                "request_id": getattr(response, "_request_id", None), "stop_reason": response.stop_reason,
                "answer": text, "problem": why, "usage": usage, "cost_usd": round(spent, 6),
                "budget_usd": settings["budget_usd"], "ledger_spent_usd": round(budget.spent, 6) if budget else None})
        if crash is not None:
            raise crash
        if why is None:
            result["unresolved"] += requirement_gaps(unit, result)
            return result
        if response.stop_reason == "refusal":
            break
        if response.stop_reason == "end_turn":
            messages += [{"role": "assistant", "content": response.content},
                         {"role": "user", "content": f"That answer can't be used: {why}. Answer again for the same "
                                                     "text, with every template (the ones that worked too)."}]
    if last is not None:                        # the last answer that had working rules: keep those
        last["unresolved"] += last["rejected"] + requirement_gaps(unit, last)
        last["problems"] = []
        return last
    return {"failed": why, "rules": {}, "unresolved": [], "rejected": [], "proposed": {}, "problems": [], "templates": []}
