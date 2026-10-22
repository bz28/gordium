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
from section_labeling.labeler import PRICES, cost, find_quote, numbered, sha
from section_labeling.term_index import related as related_pieces

from .chart_values import FOOTNOTE, NOT_APPLICABLE, footnotes, numbers as cell_numbers, section_refs
from .templates import (CHART_FILE, fill_template, formula_slots, number_places, template_problems,
                        with_occurrence_nudged)

HERE = Path(__file__).parent
GUIDE_FILE = REPO / "regulations/document_extraction_guide/drafting_rules.md"
SETTINGS = yaml.safe_load((HERE / "settings.yaml").read_text(encoding="utf-8"))
UNITS = ("ft", "sf", "count", "text", "yes_no")
OUTCOMES = ["pass", "fail", "needs_review", "not_applicable"]

FORMAT = """\
## Who you are, and why this matters

You are a senior zoning plan examiner and licensed architect. You have years of experience reading municipal
zoning codes and their dimensional charts (use districts, lot size and width, yards, height and stories, lot
coverage, parking, exceptions), and you know how a plan examiner checks a building design against them.

You are turning one section of a city's zoning chart, or one piece of its zoning law, into rule templates for
Gordium. Gordium checks every building design against every rule with plain code (no AI) and tells the
architect pass, fail or needs review. So:
- Never a false pass. A rule that is too loose, or a number that is wrong, tells an architect an illegal design
  is fine. When something the text leaves unclear can change the result, add a review_when for that case (or
  make the template a flag) so the result is "needs review"; never settle it in the formula. An open question
  records the doubt for the architects but doesn't change any result on its own.
- Every number is traceable. A chart number is never typed: it is a slot that code fills from each district's
  own cell. A number you type must be written in evidence that belongs to this rule (see "numbers" below).
- Code checks everything you write (every quote, number, formula and worked example) and sends back what it
  can't verify, with the reason. Nothing is trusted on your word.

## The process, in order

1. Read the whole text given, every line, with the footnotes, sections of the law and definitions given with it.
2. List each requirement it sets for the residential districts listed below: a limit, a minimum, a
   prohibition, a condition, an allowed or forbidden use. A sentence that names several things ("each required
   front, side and rear yard") sets a requirement for each one: every one gets a rule. Procedures
   (applications, permits, fees, notices) are not requirements on a design.
3. Draft only this text's own requirements. A requirement or exception that lives in another section of the
   law is drafted when that section is drafted, not folded into this rule. For example, the chart's height row
   is drafted as "building_height <= {height}"; the extra height that section 325-16C allows (with larger
   yards) is drafted from 325-16C itself, as a rule that relaxes the chart's (see "relaxes").
4. For each requirement write one template: the formula, a slot for every chart number, the quotes, every
   number you type with where it is written, and worked examples.
5. Before answering, check each number you typed against the "numbers" rules, and each example against the
   "examples" rules.
6. If the text sets nothing for the residential districts listed (it is only for other districts, or only
   procedure), return no templates and say why in no_rule_reason.

## What to write

Answer with rule templates in the JSON shape required. Each template becomes one rule per district (when
it has slots) or one rule for every district (when it has none).

- kind: "rule" when code can decide it from measurements; "flag" when it needs an architect's judgment
  (a flag has no check: leave check "").
- check / applies_when / review_when.when: formulas in the formula language. Allowed: measure names,
  numbers, quoted text ("one_family_detached", "R-1b"), + - * /, < <= > >= == !=, in / not in a [list],
  and / or / not, `a if condition else b`, min(a, b, ...) and max(a, b, ...). A yes/no measure is a test on
  its own (`adu_separate_entrance`). check and applies_when must be true/false tests.
- applies_when: only a condition the text itself states (a use, a kind of lot, a size). Leave it "" when the
  rule applies to every lot in the district. Never write a placeholder test (true, lot_area > 0, use != "",
  stories >= 0): it makes the rule depend on a measure it doesn't need, so the rule can't be decided without
  it. A template with slots is filled once per district, so don't test the district in it; test the
  district only in a template with no slots that applies to some districts, written exactly as listed below.
- Use only the measures listed below. If a rule needs a fact that isn't listed, name it in new_measures
  (lowercase_with_underscores, a unit from ft, sf, count, text, yes_no, and what it means); an engineer
  adds it before the rule is used. Never invent a measure without listing it there.
- Slots. A number that comes from the zoning chart is never typed: write a slot {name} and define it in
  slots: the chart page, section and row label exactly as listed, which number in the cell (1 = first),
  how many numbers the cell must have, whether that number is a percent, and the footnote markers the cell
  must carry (["16"] for "50 ft [fn16]"). Code fills the slot from each district's own cell; a district
  whose cell doesn't have that shape gets no rule and goes to a person.
- numbers: one entry for every number you type in applies_when, check or review_when (not slots, not 0),
  naming the one place it is written. A typed number is trusted only from evidence that belongs to this rule:
  - {value, from: "law_quote", quote: <index in quotes>, slot: "", footnote: ""}: a sentence of the paragraph
    being drafted (the text given above, quoted in quotes);
  - {value, from: "slot_footnote", quote: -1, slot: <slot name>, footnote: <note number>}: a footnote whose
    marker is on the slot's own cell ("50 ft [fn16]": note 16);
  - {value, from: "slot_row_label", quote: -1, slot: <slot name>, footnote: ""}: that slot's own row label
    ("First three bed or sleeping rooms").
  Anything else is refused: a sentence of another section of the law, a footnote on another cell, row label
  or section heading, another row's label. A slot's footnote or row label backs a number only where the
  number stands with that slot (in the same arithmetic or min/max, or in the condition that picks the slot's
  value), and only if changing that slot there changes the result of some worked example. A percent is typed
  as its fraction (25% is 0.25); work numbers out in the formula from their inputs (0.02 * 1000), never as a
  result (20).
- Footnotes: a chart cell's footnote marker ([fn16]) points to a note printed under that page's table
  (listed below). Every footnote on a slot's cell, its row label or its section heading has to be quoted,
  and applied in the rule.
- quotes: the exact words that support the rule, as whole sentences, copied character for character
  (footnote markers like [fn11] included). document "chart" only for a footnote under a chart table, with
  its page; document "law" with the piece id for text from a piece of the law given here (page 0). A quote
  must occur once. A chart rule's source is its chart cell: code cites each district's own cell when it fills
  a slot, so a chart row whose section has no footnote is drafted with quotes: [] (no quote needed; never quote
  the row itself, a definition or a related section to have one). Never leave a chart row undrafted because
  there is nothing to quote.
- Conditions: carry each rule's conditions from the text, and only those. Where an existing measure already decides
  whether a requirement applies (accessory_distances_apply for §325-25C's distances), use it alone; never narrow
  it with a new measure (a building "frame" or not). A chart row "per dwelling unit" applies to a dwelling unit:
  limit it to the chart's dwelling uses, send other uses to §325-20 (review), and for a building of several units
  add up every unit or send it to review; one unit's sleeping rooms don't count them all.
- Exceptions: draft every part of an exception (every yard it enlarges) for a district, or none.
- relaxes: an exception that allows more than a chart rule allows (more height when every yard is increased) is
  one rule: applies_when is every condition of the exception, all of them (every yard it enlarges, with its
  increase); check is the most the exception allows; relaxes is the name of the slot whose chart row's rule it
  widens ("height" for the slot of 'Height in feet'). Code links it to that district's chart rule, and the
  checker passes the chart rule when it passes, or when the exception's conditions all hold and its check passes.
  A requirement the exception adds on top (the stories may not be exceeded) is its own rule, with no relaxes.
  relaxes is "" for every other rule.
- Projections into yards: a limit on how far a feature (eaves, cornices) may project into a required yard is a
  rule on each yard measured to the outermost part (the *_eaves measures) against that yard's chart minimum less
  the projection allowed. Where another section enlarges the required yard (the height bonus, for a building over
  the chart height), send that case to review. "The yard stays open" is what the yard rules and this rule check:
  it needs no flag of its own.
- Cell forms: when a row's cells take different forms in different districts (footnotes on some, or several
  numbers, like '35%/40% /50% [fn12]'), write a template for each form, each with that form's slots and its
  footnotes applied ("one number per use" is a choice by use in the formula, every number used). Code fills each
  district from the template its cell fits.
- Ranges: when the text sets a minimum or a range ("three or more", "at least", "not less than", "between 3 and
  6"), the formula enforces every end of it, even when the ends are in different sentences ("a building
  containing three or more dwellings" and "a maximum of six may be attached" are one rule: quote both sentences
  and check both ends). Code tests each quoted lower bound and sends a rule that drops one to a person.
- examples: for a rule, at least one that passes and one that fails, chosen so they exercise the whole
  formula: both sides of every `if` and of every comparison in applies_when; for min or max, an example
  where each part decides; for a tiered rule (parking by bedrooms: up to 3, 4 to 5, more than 5), an example
  in every tier, the top one included. Each given is {measure, value}: measure is a measure name (never a
  slot); value is text: a number, arithmetic on slots ("{front} - 1"), true or false, a use id or a district
  name.
- open_questions: anything the law leaves unclear, for the architects. Never settle it in the formula. An open
  question doesn't change a result: if the unclear point can change one, also add a review_when for it.
- id_suffix: lowercase_with_underscores; the rule's id is the district (or "general") plus this suffix.
"""


def output_schema(topics: list[str]) -> dict:
    text = {"type": "string"}
    slot = {"type": "object", "additionalProperties": False,
            "required": ["name", "page", "section", "row", "number", "numbers_in_cell", "percent", "footnotes"],
            "properties": {"name": text, "page": {"type": "integer"}, "section": text, "row": text,
                           "number": {"type": "integer"}, "numbers_in_cell": {"type": "integer"},
                           "percent": {"type": "boolean"}, "footnotes": {"type": "array", "items": text}}}
    template = {"type": "object", "additionalProperties": False,
                "required": ["id_suffix", "title", "topic", "kind", "applies_when", "check", "relaxes", "slots",
                             "review_when", "quotes", "numbers", "examples", "open_questions", "new_measures"],
                "properties": {
                    "id_suffix": text, "title": text, "topic": {"type": "string", "enum": topics},
                    "kind": {"type": "string", "enum": ["rule", "flag"]}, "applies_when": text, "check": text,
                    "relaxes": text,
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


def system_prompt(ctx: Context, uses: dict, districts: list[str], table: str, notes: dict[int, dict],
                  several: frozenset = frozenset()) -> str:
    """The fixed instructions: identical for every unit, so they're cached after the first call. several: the uses
    that are a building of several dwelling units by their definitions (several_units), marked in the use list."""
    measures = yaml.safe_load(MEASURES_FILE.read_text(encoding="utf-8"))
    topics = yaml.safe_load(VOCABULARY_FILE.read_text(encoding="utf-8"))["topics"]
    return (f"{GUIDE_FILE.read_text(encoding="utf-8")}\n{FORMAT}\n## Measures (with units)\n"
            + "\n".join(f"- {n} ({m['unit']}): {m['meaning']}" for n, m in measures.items())
            + "\n\n## Use ids (for the use measure)\n" + "\n".join(
                f"- {k}: {v['name']}" + (" (a building of several dwelling units, by its definition)" if k in several else "")
                for k, v in uses.items())
            + "\n\n## Residential districts (for the district measure: write them like this)\n"
            + ", ".join(districts)
            + "\n\n## Topics\n" + "\n".join(f"- {k}: {' '.join(v.split())}" for k, v in topics.items())
            + "\n\n## The zoning chart's rows (for slots)" + table
            + "\n\n## Footnotes under the chart tables (document \"chart\", with the page)\n" + chart_notes(notes) + "\n")


def _sentences(text: str) -> str:
    return " ".join(text.split())


def unit_message(unit: dict, context: dict) -> str:
    """The unit's whole text (a law piece's every line, numbered) plus what it points to: the lines its label
    cites (hints only), footnotes, sections of the law, definitions."""
    number = {(p, n): i for i, (p, n, _) in enumerate(unit.get("lines", []), 1)}
    if unit.get("lines"):
        parts = [unit["intro"] + " Its whole text follows, every line numbered L1, L2, ... (the numbers are not part "
                 "of the city's words: never put them in a quote). A '--- page N ---' line marks a page break; a quote "
                 "can't run across one. Draft every requirement in the whole text.", numbered(unit["lines"])]
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
    if context.get("dropped"):
        parts.append("It also points to these sections, left out for length (don't draft from them; a person checks "
                     "them): " + ", ".join(context["dropped"]))
    if context.get("unfound"):
        parts.append("It also points to these sections, which match no section of the law it was given (don't draft "
                     "from them; a person checks them): " + ", ".join(context["unfound"]))
    if context.get("related"):
        parts.append("Related sections (the term index lists them for words this text uses). Background only, for "
                     "what the words mean and what else applies: each sets its own rules, so don't draft or quote "
                     "from them here; if this text's rule depends on one, say so in open_questions:\n" + "\n\n".join(
                         f"[piece {p['id']}] {p['title']}\n{p['text']}" for p in context["related"]))
    if context.get("related_dropped"):
        parts.append("More related sections, left out for length: " + ", ".join(context["related_dropped"]))
    if context["definitions"]:
        parts.append("Definitions used (for meaning; quote them only if a rule rests on them):\n" + "\n".join(
            f"- {d}" for d in context["definitions"]))
    return "\n\n".join(parts)


RELATED_LIMIT = 12_000      # characters of related sections (by the term index) shown as background


def gather_context(unit: dict, law: dict, chart: dict, definitions: dict) -> dict:
    """Footnotes, sections and definitions the unit's text points to, and (law["terms"], the term index) the
    related sections that use the same words, as background only: never quotable, never a source of numbers.
    law: {file, pieces, rows, terms?};
    chart: {notes: {page: {n: note}}}. A reference to §325-29 takes 325-29 and its lettered subsections
    (325-29A, 325-29B ...), never 325-29.1, a section of its own. The sections stop at 20,000 characters;
    whatever doesn't fit is named in "dropped" (and in the message), never left out silently. A reference that
    matches no section of the law is named in "unfound" the same way."""
    text = unit["text"]
    markers = sorted({n for m in re.findall(r"\[fn([^\]]*)\]", text) for n in m.split(",") if n.strip()}, key=int)
    notes = [{"page": unit["page"], **chart["notes"][unit["page"]][n]} for n in markers
             if unit.get("page") in chart["notes"] and n in chart["notes"][unit["page"]]]
    refs = section_refs(text + " " + " ".join(n["text"] for n in notes))
    pieces, dropped, unfound, size = [], [], [], 0
    for ref in refs:
        matches = [pid for pid in law["pieces"] if pid == ref or pid.startswith(ref) and pid[len(ref):len(ref) + 1].isalpha()]
        if not matches:
            unfound.append(ref)
        for pid in matches:
            piece = law["pieces"][pid]
            if pid != unit.get("piece") and all(p["id"] != pid for p in pieces) and pid not in dropped:
                body = piece_text(law["rows"], piece)
                if size + len(body) > 20_000:
                    dropped.append(pid)
                    continue
                pieces.append({"id": pid, "title": piece["title"], "text": body})
                size += len(body)
    lower = text.lower()
    defs = [f"{v['term']}: " + " ".join(_sentences(s["quote"]) for s in v["sources"])
            for v in definitions.values() if v["term"].split("(")[0].strip().lower() in lower]
    related, related_dropped, size = [], [], 0
    seen = {unit.get("piece")} | {p["id"] for p in pieces} | set(dropped)
    # Only sections that set requirements (labeled rule or flag: law["requires"]) are worth the space; the most
    # relevant first, so the limit cuts the least relevant (definitions are given separately, above).
    candidates = {pid: piece_text(law["rows"], law["pieces"][pid])
                  for pid in (related_pieces(law["terms"], text) if law.get("terms") else [])
                  if pid in law["pieces"] and pid not in seen and pid in law.get("requires", law["pieces"])}
    for pid in related_pieces(law["terms"], text, candidates) if candidates else []:
        body = candidates[pid]
        if size + len(body) > RELATED_LIMIT:
            related_dropped.append(pid)
            continue
        related.append({"id": pid, "title": law["pieces"][pid]["title"], "text": body})
        size += len(body)
    return {"notes": notes, "pieces": pieces, "dropped": dropped, "unfound": unfound, "definitions": defs,
            "related": related, "related_dropped": related_dropped}


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


NOTE_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(%|sf\b|square feet|ft\b|feet|foot|units?\b|spaces?\b)", re.IGNORECASE)


def note_amounts(text: str) -> list[float]:
    """The amounts a chart note states, with their unit: "+500 sf for each additional occupant" -> [500];
    "For the first 1-3 units; +750 sf" -> [3, 750]; "50% of the developable lot area" -> [0.5]. A marker or a
    pointer ("(4)", "notes 1 - 6", "§325-16") isn't an amount."""
    out = []
    for m in NOTE_AMOUNT.finditer(re.sub(r"^\s*\(\d+\)", "", text)):
        n = float(m[1].replace(",", ""))
        out.append(n / 100 if m[2] == "%" else n)
    return out


def _typed_numbers(template: dict) -> list[float]:
    from rule_format import formula
    texts = [template.get("applies_when", ""), template.get("check", "")] + [r["when"] for r in template.get("review_when") or []]
    found = []
    for t in texts:
        try:
            found += formula.numbers(re.sub(r"\{[a-z0-9_]+\}", "x", t)) if t.strip() else []
        except formula.FormulaError:
            return []                                    # reported with the formula
    return found


def dropped_amounts(template: dict, notes: dict[int, dict]) -> dict[tuple, list[str]]:
    """{(page, note): why} for each note on a slot's own cell that states an amount the rule's formulas don't use
    (R-2C's '2,500 sf [fn4]': "+500 sf for each additional occupant"; a draft that quoted the note and dropped the
    500 passed every larger household). Settled per district by settle_dropped_amounts: only a flag kept there that
    cites the note sends it to a person; otherwise the rule isn't kept there."""
    if template["kind"] != "rule":
        return {}
    typed = _typed_numbers(template)
    out: dict[tuple, list[str]] = {}
    for slot in template["slots"]:
        for n in sorted(set(slot["footnotes"]), key=lambda n: (len(n), n)):
            note = notes.get(slot["page"], {}).get(n)
            if note is None:
                continue
            for amount in dict.fromkeys(note_amounts(note["text"])):
                if not any(abs(amount - x) < 1e-9 for x in typed):
                    out.setdefault((slot["page"], n), []).append(
                        f"slot {slot['name']}: footnote {n} states {amount:g}, which the rule doesn't apply (apply it "
                        f"in the formula, or send the note to a person with a flag quoting it): {note['text']!r}")
    return out


def flagged_notes(rules: list[dict], notes: dict[int, dict]) -> set[tuple]:
    """The notes a kept flag cites whole: a resolved chart source on the note's page that covers every line of
    the note (never a quote that merely contains a few of its words)."""
    out = set()
    for r in rules:
        if r.get("kind") != "flag":
            continue
        for x in r.get("sources") or []:
            if x.get("file") != CHART_FILE or "lines" not in x:
                continue
            for n, note in (notes.get(x["page"]) or {}).items():
                words = lambda t: " ".join(re.sub(r"^\s*\(\d+\)", "", str(t)).split())   # noqa: E731
                if x["lines"][0] <= note["lines"][0] and note["lines"][1] <= x["lines"][1] \
                        and words(note["text"]) in words(x.get("quote", "")):       # the whole note, not a part of it
                    out.add((x["page"], n))
    return out


def settle_dropped_amounts(pending: list, out: dict, notes: dict[int, dict], unit: dict, ctx: Context) -> None:
    """Round 10 (P0): a rule that leaves out a note's amount is kept in a district only where a flag kept for that
    district (or for every district) cites the note whole. Decided from what was kept, after every template is
    checked: a refused flag, one kept only elsewhere, or one quoting a fragment exempts nothing."""
    for t, dropped in pending:
        kept_anywhere = False
        for district in sorted(out["rules"]):
            mine = [r for r in out["rules"][district] if r["id"] == f"{district}.{t['id_suffix']}"]
            if not mine:
                continue
            everywhere = [r for r in out["rules"].get("general", []) if not r.get("applies_when") or outcome(
                {"kind": "flag", "applies_when": r["applies_when"]}, {"district": district}, ctx.allowed()) != "not_applicable"]
            covered = flagged_notes(out["rules"][district] + everywhere, notes)   # a general flag that applies here
            whys = [w for key, ws in dropped.items() if key not in covered for w in ws]
            if not whys:
                kept_anywhere = True
                continue
            out["rules"][district] = [r for r in out["rules"][district] if r not in mine]
            out["unresolved"] += [{"rule": r["id"], "why": "; ".join(whys[:2]),
                                   "cells": [[x["page"], x["cell"]["section"], x["cell"]["row"], x["cell"]["column"]]
                                             for x in r["sources"] if isinstance(x.get("cell"), dict)]} for r in mine]
        if not kept_anywhere:
            out["rejected"].append({"rule": f"{unit['id']}.{t['id_suffix']}",
                                    "why": "; ".join(w for ws in dropped.values() for w in ws)[:600]})
            out["templates"] = [x for x in out["templates"] if x is not t]
    out["rules"] = {d: rs for d, rs in out["rules"].items() if rs}


def cells_used(out: dict) -> dict[tuple, set[int]]:
    """Each district cell's numbers that fill a slot of a rule kept in the end."""
    templates = {t["id_suffix"]: t for t in out["templates"]}
    used: dict[tuple, set[int]] = {}
    for rules in out["rules"].values():
        for r in rules:
            t = templates.get(r["id"].split(".", 1)[1])
            for x in r.get("sources") or [] if t else []:
                c = x.get("cell")
                if not isinstance(c, dict):
                    continue
                for sl in t["slots"]:
                    if (sl["page"], sl["section"], sl["row"].strip()) == (x["page"], c["section"], c["row"]):
                        used.setdefault((x["page"], c["section"], c["row"], c["column"]), set()).add(sl["number"])
    return used


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


def _binding_items(template: dict, notes: dict[int, dict], own_piece: str | None = None) -> tuple[list[str], list[dict]]:
    """Check each entry of `numbers` names ONE evidence item that holds its value and that can be trusted
    (Ben's policy, 2026-10-20). Code can check that evidence holds a number, never what the number is about,
    so only evidence that belongs to the rule itself is trusted:
    - law_quote: a sentence of the piece being drafted (a chart unit has none; another section's sentence,
      such as 325-16B's parapet "five feet or less", is never trusted);
    - slot_footnote: a footnote whose marker is on that slot's own cell ("50 ft [fn16]": note 16), never a
      note on another cell, the row label or the section heading;
    - slot_row_label: that slot's own row label ("First three bed or sleeping rooms").
    Anything else is rejected, so the unit is retried and in the end listed for a person: an untrusted
    number never reaches a rule. A number that only labels or points ("(3)", "§ 325-20D(1)") doesn't count;
    a percent counts only as its fraction (25% is 0.25). Returns (problems, the valid entries)."""
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
            if q["piece"] != own_piece:
                p.append(f"{where}: the sentence is from §{q['piece']}, not the text being drafted; a number is "
                         "trusted only from a sentence of the text being drafted")
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
                note = notes.get(slot["page"], {}).get(b["footnote"])
                if b["footnote"] not in slot["footnotes"] or note is None:
                    p.append(f"{where}: footnote {b['footnote']!r} isn't marked on slot {b['slot']!r}'s own cell; a "
                             "number is trusted only from a footnote on the slot's own cell")
                    continue
                text = note["text"]
        if not v_close(v, source_numbers(text, percent_as_number=False)):
            p.append(f"{where}: {v:g} isn't written in it: {text!r}")
            continue
        valid.append(b)
    for _, text, n, near in number_places(template):           # (whether a backing slot decides: after filling)
        if not any(abs(b["value"] - n) < 1e-9 and (b["from"] == "law_quote" or b["slot"] in {s for s, _ in near})
                   for b in valid):
            p.append(_unbacked(n, text))
    return p, valid


def _unbacked(n: float, text: str) -> str:
    return (f"number {n:g} in {text!r} isn't backed where it stands: bind it to a sentence of the text being drafted, "
            "or to the own-cell footnote or the row label of a slot it stands with (the same arithmetic, or the "
            "condition that picks the slot's value) where that slot decides something; a chart number must be a slot")


def _backing(template: dict, valid: list[dict], filled: list[tuple[str, dict]], cells: dict, sources: list[dict],
             drafted_by: str, allowed: dict) -> list[str]:
    """Every place a number is typed must be backed where it stands. A trusted law quote binding with that value
    backs it. A slot binding backs it only through an occurrence of that slot the number stands with which itself
    decides something: changed alone, some worked example in some district comes out differently (so
    `3 + 0 * {x}` or `min(3, {x})` with a large {x} back nothing there, whatever else {x} does)."""
    decides = {}

    def occurrence_decides(key, k):
        if (key, k) not in decides:
            changed = with_occurrence_nudged(template, key, k)
            decides[key, k] = any(
                outcome(new, ex["given"], allowed) != outcome(rule, ex["given"], allowed)
                for column, rule in filled for new in [fill_template(changed, column, cells, sources, drafted_by)[0]]
                if new is not None for ex in rule["examples"])
        return decides[key, k]

    problems = []
    for key, text, n, near in number_places(template):
        same = [b for b in valid if abs(b["value"] - n) < 1e-9]
        if any(b["from"] == "law_quote" for b in same):
            continue
        if not any(name == b["slot"] and occurrence_decides(key, k) for b in same for name, k in sorted(near)):
            problems.append(_unbacked(n, text))
    return problems


def v_close(v: float, values) -> bool:
    return any(abs(v - x) < 1e-9 for x in values)


CATCH_ALL_ROW = re.compile(r"^\s*other use\b", re.IGNORECASE)


GENERIC = {"or", "and", "related", "building", "buildings", "use", "other", "except", "office", "structure"}


def dwelling_kind_uses(law: dict, ctx: Context) -> dict[str, str]:
    """{use id: the words of §325-3B that make it a kind of dwelling}, found by definition, never guessed from the use
    id or the label's wording: (1) its own definition (the defined term with its chart label's words) says it is a
    dwelling (DORMITORY "A multiple dwelling ..."; BED-AND-BREAKFAST INN "... single dwelling unit ..."); or (2) an item
    of the MULTIPLE DWELLING definition names it ("(4) A building used or occupied as a convalescent, old-age or nursing
    home": the chart's "Nursing, convalescent or rest home"; two of the label's own words in one item). The chart's
    lot-size and lot-width rows name dwelling types, so for these uses its catch-all "Other use" row may not apply."""
    out = {}
    multiple = next((p for pid, p in law.get("pieces", {}).items() if pid.startswith("325-3B:")
                     and {"dwelling", "multiple"} <= set(_words(p.get("title", "")))), None)
    items = []
    if multiple is not None:
        text = " ".join(piece_text(law["rows"], multiple).split())
        items = [x.strip() for x in re.split(r"\(\d+\)", text.split("—", 1)[-1]) if x.strip()]
    for use in sorted(ctx.uses):
        found = use_definition(use, law, ctx)
        if found:
            genus = found[1]["definition"].split("—", 1)[-1].split(".", 1)[0]
            if re.search(r"\bdwelling\b", genus, re.IGNORECASE):
                out[use] = genus.strip()
                continue
        words = set(_words(use_label(use, ctx))) - GENERIC
        for item in items:
            if len(words & set(_words(item))) >= 2:
                out[use] = f"a multiple dwelling: {item.rstrip('.')}"
                break
    return out


def unclear_catch_all(rule: dict, law: dict, ctx: Context) -> dict:
    """A chart rule filled from an "Other use" row that applies by `use not in [...]` reaches every use the row doesn't
    name, among them uses the law defines as a kind of dwelling (a dormitory is "a multiple dwelling", so the
    multiple-family row, with its note 7, may be the one that applies). The law doesn't settle which row, so such a
    use needs review, never a pass (stage 1 grade, 2026-10-20: R-3a dormitory lot size passed where the answer key
    says needs review). Applied by code to every drafted chart rule, whatever the AI wrote."""
    if not any(CATCH_ALL_ROW.match(str((s.get("cell") or {}).get("row", ""))) for s in rule.get("sources") or []):
        return rule
    named = set(re.findall(r'"([a-z0-9_]+)"', str(rule.get("applies_when", "")))) \
        if "use not in" in str(rule.get("applies_when", "")) else None
    if named is None:
        return rule
    already = " ".join(str(r.get("when", "")) for r in rule.get("review_when") or [])
    add = [{"when": f'use == "{u}"',
            "reason": f"§325-3 defines this use as {genus[:90]!r}, a kind of dwelling, so which row of the chart applies to "
                      "it (this \"Other use\" row or a dwelling row, with its notes) is unclear: a person decides."}
           for u, genus in dwelling_kind_uses(law, ctx).items() if u not in named and f'"{u}"' not in already]
    if not add:
        return rule
    rows = [copy_of(r) for x in add for r in ctx.use_rows.get(x["when"].split('"')[1], [])[:1]]   # each use's own row
    return rule | {"review_when": list(rule.get("review_when") or []) + add,
                   "sources": list(rule.get("sources") or []) + [r for r in rows if r not in rule.get("sources", [])]}


SCOPE_PHRASE = re.compile(r"\b(?:in|within)\s+(?:either\s+)?the\s+((?:R-[\w-]+|RU)(?:(?:\s*,\s*(?:or\s+|and\s+)?|\s+or\s+|"
                          r"\s+and\s+)(?:R-[\w-]+|RU))*)\s+(?:Zoning\s+)?Districts?\b", re.IGNORECASE)
NEIGHBOR = re.compile(r"\b(?:abut\w*|adjacent|adjoin\w*|next\s+to|across)\b[^.;]{0,40}$", re.IGNORECASE)
EXCLUDES = re.compile(r"\b(?:except|other\s+than|not|outside|excluding)\b[^.;]{0,25}$", re.IGNORECASE)


def text_scope(text: str, districts) -> tuple[set[str] | None, list[str]]:
    """The districts a law piece names as its own scope ("any permitted use in the R-3a or R-3b Zoning District"), or
    None when it names none. A phrase after "abut", "adjacent", "adjoins", "next to" or "across" names the neighbor,
    not the scope ("abuts land in either the R-1a or R-1b Zoning District"). A phrase after "except", "other than",
    "not", "outside" or "excluding" names districts the piece leaves out: read as a scope it would drop the rules
    everywhere else (a silent pass), so the scope is unreadable and a person decides. A family name stands for its
    districts (R-1: R-1a, R-1b; R-U: RU). Returns (scope, what it couldn't read)."""
    flat = " ".join(text.split())
    scope, unread = set(), []
    for m in SCOPE_PHRASE.finditer(flat):
        before = flat[max(0, m.start() - 60):m.start()]
        if EXCLUDES.search(before):
            unread.append(f"{m.group(0)!r} (a district the text leaves out)")
            continue
        if NEIGHBOR.search(before):
            continue
        for name in re.split(r"\s*,\s*(?:or\s+|and\s+)?|\s+or\s+|\s+and\s+", m.group(1)):
            key = name.replace("-", "").upper()
            exact = {d for d in districts if d.replace("-", "").upper() == key}
            family = {d for d in districts if d.replace("-", "").upper().startswith(key) and len(d.replace("-", "")) > len(key)
                      and d.replace("-", "")[len(key)].isalpha() and not key[-1].isalpha()}
            if exact or family:
                scope |= exact or family
            else:
                unread.append(name)
    return (scope or None) if not unread else None, unread


def in_scope(rule: dict, scope: set[str]) -> list[dict]:
    """A rule drafted from a law piece whose text names its districts applies only there, by where it is saved, never
    by a formula (the checker works out every part of an `and`, so `district in [...] and abuts_r1_district` still
    needs review where abuts_r1_district isn't measured). A district's rule outside the scope is dropped; a rule for
    every district (general) is saved instead in each scope district's own rulebook, with that district's id."""
    district, rest = rule["id"].split(".", 1)
    if district != "general":
        return [rule] if district in scope else []
    return [rule | {"id": f"{d}.{rest}"} for d in sorted(scope)]


WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "twelve": 12, "twenty": 20, "fifty": 50}
_NUM = r"(\d+(?:,\d{3})*(?:\.\d+)?|" + "|".join(WORD_NUMBERS) + r")"
LOWER_BOUND = re.compile(
    rf"\b{_NUM}\s+or\s+more\b|\bat\s+least\s+{_NUM}\b|\bnot\s+less\s+than\s+{_NUM}\b|\bminimum\s+of\s+{_NUM}\b"
    rf"|\bbetween\s+{_NUM}\s+and\s+{_NUM}\b|\b{_NUM}\s+to\s+{_NUM}\b", re.IGNORECASE)
STOP = {"the", "a", "an", "of", "or", "and", "to", "in", "on", "for", "be", "may", "shall", "is", "are", "by", "any", "with"}


def _value(token: str) -> float:
    return float(WORD_NUMBERS.get(token.lower(), token.replace(",", "")))


def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+(?:-[a-z]+)?", text.lower()) if w not in STOP and len(w) > 2}


def _bound_unit(sentence: str, end: int) -> str:
    """The unit of a bound, from the words after it: "eight feet" ft, "6,000 square feet" sf, "three or more one-family
    dwellings" count."""
    after = sentence[end:end + 30].lower()
    if re.match(r"\s*(?:square\s+feet|sq\.?\s*ft|sf)\b", after):
        return "sf"
    if re.match(r"\s*(?:feet|foot|ft)\b", after):
        return "ft"
    if re.match(r"\s*(?:percent|%)", after):
        return "percent"
    return "count"


def _measure_unit(name: str, ctx: Context) -> str | None:
    from rule_format.rulebook import MEASURES_FILE, load as load_yaml
    known = (load_yaml(MEASURES_FILE) or {}) if MEASURES_FILE.exists() else {}
    m = known.get(name) or ctx.proposed.get(name) or {}
    return m.get("unit") if isinstance(m, dict) else None


def lower_bounds(rule: dict, unit: dict, law: dict, ctx: Context) -> list[tuple[float, str, dict | None]]:
    """(the bound, the sentence that states it, its source when it isn't one of the rule's quotes) for every lower bound
    or range ("three or more", "at least 20", "not less than", "between 3 and 6") in the rule's own quotes, or in a
    sentence of its own law piece about the same thing (two words in common with a quote): the §325-3B attached
    dwelling's "three or more one-family dwellings" sits in the sentence before the quoted "A maximum of six"."""
    quotes = [s_.get("quote", "") for s_ in rule.get("sources") or [] if isinstance(s_, dict)]
    sentences = [(q, None) for q in quotes]
    piece = law.get("pieces", {}).get(unit.get("piece") or "")
    if piece is not None:
        words = set().union(*(_content(q) for q in quotes)) if quotes else set()
        text = " ".join(piece_text(law["rows"], piece).split())
        for sentence in re.split(r"(?<=[.;])\s+", text):
            if sentence not in quotes and len(_content(sentence) & words) >= 2:
                sentences.append((sentence, piece))
    out = []
    for sentence, from_piece in sentences:
        found = []
        for m in LOWER_BOUND.finditer(sentence):
            value = _value(next(g for g in m.groups() if g))
            if value > 1:                             # "one or more" sets nothing to check
                found.append((value, _bound_unit(sentence, m.end())))
        if found:
            source = find_quote(sentence, from_piece, law["file"], ctx)[0] if from_piece is not None else None
            out.append((found, sentence, source))
    return out


def unenforced_lower_bound(rule: dict, unit: dict, law: dict, ctx: Context) -> dict:
    """A drafted rule that keeps one end of a range and drops the other (§325-3B's attached dwelling: "three or more"
    units, "a maximum of six"; the draft checked only <= 6, so a two-unit building passed). Judged by meaning: in the
    rule's own passing example, each measure its check tests is set just under the bound; if the rule still passes for
    every one, the bound isn't enforced, and the rule sends a design under it to review (citing the sentence), never a
    pass, until it is re-drafted. Rules it can't judge (no check, no passing example) are left as they are."""
    from rule_format import formula
    from rule_format.rulebook import outcome
    if not rule.get("check"):
        return rule
    passing = next((ex["given"] for ex in rule.get("examples") or [] if ex.get("expect") == "pass"), None)
    if passing is None:
        return rule
    kinds = ctx.kinds()
    tested = sorted(n for n in _checked_names(rule) if kinds.get(n) == "number")
    review, sources = list(rule.get("review_when") or []), list(rule.get("sources") or [])
    allowed = ctx.allowed()
    def enforced(value, names):
        under = value - 1 if value == int(value) else value * 0.99
        return any(outcome(rule, passing | {n: under}, allowed) != "pass" for n in names)

    for found, sentence, source in lower_bounds(rule, unit, law, ctx):
        # only a measure of the bound's own unit can be held to it ("three or more dwellings" is no height), and a
        # sentence with several bounds for different cases (8 ft residential, 10 ft otherwise) is kept when one holds
        fits = [(v, [n for n in tested if _measure_unit(n, ctx) == u]) for v, u in found]
        fits = [(v, names) for v, names in fits if names]
        if not fits or any(enforced(v, names) for v, names in fits):
            continue
        value, names = min(fits)
        when = " or ".join(f"{n} < {int(value) if value == int(value) else value}" for n in names)
        if any(r.get("when") == when for r in review):
            continue
        review.append({"when": when, "reason": f"The law sets a lower bound ({sentence[:120]!r}) this rule doesn't "
                                               "check; a person checks it until the rule is re-drafted."})
        if source is not None and source not in sources:
            sources.append(copy_of(source))
    return rule if len(review) == len(rule.get("review_when") or []) else rule | {"review_when": review, "sources": sources}


SEVERAL_UNITS = re.compile(r"\b(?:two|three|four|\d+)\b[^.]{0,30}\b(?:dwelling units|one-family dwellings)\b", re.IGNORECASE)


def several_units(use: str, law: dict, ctx: Context) -> bool:
    """The use is a building of more than one dwelling unit, by its definition (TWO-FAMILY "two dwelling units";
    SEMIDETACHED "two one-family dwellings"; ATTACHED "three or more") or its chart label (Multiple family dwelling)."""
    found = use_definition(use, law, ctx)
    text = found[1]["definition"].split("—", 1)[-1] if found else ""
    one = re.search(r"not more than one\s+(?:\[page \d+\]\s+)?dwelling unit", text, re.IGNORECASE)
    return bool(SEVERAL_UNITS.search(text)) and not one or "multiple" in use_label(use, ctx).lower()


def residential_parking_problems(rule: dict, law: dict, ctx: Context) -> list[str]:
    """A rule from the chart's residential parking rows ("... bed or sleeping rooms per dwelling unit") applies to a
    dwelling unit: a use the chart doesn't call a dwelling goes to §325-20 ("For all other uses see §325-20"), and a
    building of several units needs every unit counted, which one unit's sleeping rooms can't do. Such a rule that
    passes either is refused (the drafted bedroom formula passed a church and a two-family house)."""
    from rule_format.rulebook import outcome
    rows = [s_["cell"] for s_ in rule.get("sources") or [] if isinstance(s_.get("cell"), dict)]
    if not any(c.get("section", "").startswith("Residential") and "per dwelling unit" in c.get("row", "") for c in rows):
        return []
    passing = next((ex["given"] for ex in rule.get("examples") or [] if ex.get("expect") == "pass"), None)
    if passing is None:
        return []
    out = []
    for use in sorted(ctx.uses):
        dwelling = "dwelling" in use_label(use, ctx).lower()
        if dwelling and not several_units(use, law, ctx):
            continue
        if outcome(rule, passing | {"use": use}, ctx.allowed()) == "pass":
            why = ("isn't a dwelling: other uses go to §325-20" if not dwelling else
                   "is a building of several dwelling units: every unit's requirement is added up")
            out.append(f"it passes {use} ({why}); limit applies_when, or send that use to review")
    return out[:2]


def narrowing_problems(rule: dict, ctx: Context) -> list[str]:
    """A rule may not narrow a measured fact with an unmeasured one about the same thing: §325-25C's drafts required
    accessory_is_frame on top of accessory_distances_apply (which already decides whether the distances apply, under
    every reading), so a building not stated as frame escaped the distances once that fact existed."""
    from rule_format import formula
    from rule_format.rulebook import MEASURES_FILE, load as load_yaml
    when = rule.get("applies_when")
    if not when:
        return []
    known = (load_yaml(MEASURES_FILE) or {}) if MEASURES_FILE.exists() else {}
    names = formula.names(when)
    # only a measured yes/no fact decides whether something applies; the text selectors district and use never do
    # (the base district can't decide the South Hill overlay)
    measured = {n: known[n] for n in names if isinstance(known.get(n), dict) and known[n].get("unit") == "yes_no"}
    out = []
    for n in sorted(names - set(measured)):
        meaning = (ctx.proposed.get(n) or {}).get("meaning", "")
        if not meaning or ctx.kinds().get(n) != "boolean":
            continue
        for m, entry in measured.items():
            stem = lambda t: {w[:-1] if w.endswith("s") else w for w in _content(t)} - {"lot", "district", "zoning",
                                                                                       "city", "apply", "located"}
            if len(stem(meaning) & stem(entry.get("meaning", ""))) >= 2:          # the same subject (accessory building)
                out.append(f"{n} narrows {m}, which already decides this; use {m} alone")
    return out


def all_or_none(answer: dict, unit: dict, out: dict) -> None:
    """The parts of one exception go together (§325-16C's extra height: the larger front, side and rear yards): the
    answer's slotted templates that share one condition (applies_when) are its parts, as the AI wrote them, whether
    or not they survived. A part refused outright drops the parts in every district; a part that couldn't be filled
    in a district (a footnote, several numbers: not a "-", which only says the use isn't permitted there) drops the
    parts in that district. Independent templates (§325-8B's one per use) are not parts of anything. In place."""
    prefix = unit.get("prefix", "")
    groups: dict[str, list[str]] = {}
    for t in answer.get("templates") or []:
        when = " ".join(str(t.get("applies_when") or "").split())
        if t.get("slots") and when:
            groups.setdefault(when, []).append(prefix + t["id_suffix"])
    rejected = {r["rule"] for r in out["rejected"]}
    for parts in (g for g in groups.values() if len(g) > 1):
        whole = any(f"{unit['id']}.{sfx}" in rejected for sfx in parts)
        short = {g["rule"].split(".")[0] for g in out["unresolved"] if g.get("cells")
                 and g["rule"].split(".", 1)[-1] in parts and "the chart shows" not in g.get("why", "")}
        for d in sorted(out["rules"]):
            if not (whole or d in short):
                continue
            gone = [r for r in out["rules"][d] if r["id"].split(".", 1)[1] in parts]
            out["rules"][d] = [r for r in out["rules"][d] if r not in gone]
            out["unresolved"] += [{"rule": r["id"], "why": "another part of this exception couldn't be drafted "
                                                           f"{'at all' if whole else 'for this district'}, so none of its "
                                                           "parts is kept: a person checks it"} for r in gone]
        out["rules"] = {d: rs for d, rs in out["rules"].items() if rs}


def link_relaxes(rule: dict, template: dict, column: str | None, unit: dict, drafted: dict) -> tuple[dict | None, str | None]:
    """Link an exception to the chart rule it widens (`relaxes`, rule_format README): the one rule of this district's
    drafted rulebook, from another unit, that cites this district's cell of the named slot's row. None found (the
    chart row isn't drafted there, or two rules cite it) and the exception isn't kept there: the chart rule stays
    as strict as it is, and a person checks the exception."""
    name = template["relaxes"].strip()
    slot = next((x for x in template["slots"] if x["name"] == name), None)
    if slot is None or column is None:
        return None, f"relaxes {name!r} must name one of this template's slots"
    district = district_name(column)
    cell = {"section": slot["section"], "row": slot["row"].strip(), "column": column}
    own = f"{district}.{unit.get('prefix', '')}"
    from rule_format import formula
    widened = formula.names(rule["check"]) - {"use", "district"}
    targets = [r for r in drafted.get(district) or [] if r.get("kind") == "rule" and not r.get("relaxes")
               and not r["id"].startswith(own) and any(x.get("cell") == cell and x.get("page") == slot["page"]
                                                       for x in r.get("sources") or [])
               and formula.names(r["check"]) & widened]          # it limits what the exception allows more of
    if missing := missing_conditions(rule, ctx_kinds=None):
        return None, missing
    if len(targets) != 1:
        return None, (f"the chart rule it widens ({slot['row'].strip()!r}) is "
                      + ("not drafted for this district" if not targets else "cited by several rules here")
                      + ": the chart rule stays as it is and a person checks the exception")
    head = {k: rule[k] for k in ("id", "kind", "topic", "title")}
    return head | {"relaxes": targets[0]["id"]} | {k: v for k, v in rule.items() if k not in head}, None


CONDITION_WORDS = {"front": ["front_yard"], "side": ["side_yard_smaller", "side_yard_larger"], "rear": ["rear_yard"],
                   "stories": ["stories"]}


def missing_conditions(rule: dict, ctx_kinds=None) -> str | None:
    """Round 10 (P0): a relaxing rule passes the rule it widens when its conditions hold, so a condition left out is a
    false pass (a bonus with only the front yard passed 1 ft side yards). Every yard (or the stories) its quoted law
    names must be in its applies_when, and must decide it: with that measure at 0, the exception doesn't apply."""
    from rule_format import formula
    law = " ".join(str(x.get("quote", "")) for x in rule.get("sources") or [] if x.get("file") != CHART_FILE).lower()
    named = [m for w, ms in CONDITION_WORDS.items() if re.search(rf"\b{w}\b", law) for m in ms]
    have = formula.names(rule.get("applies_when") or "")
    if absent := [m for m in named if m not in have]:
        return (f"a rule that relaxes another must carry every condition its law sets: {', '.join(absent)} "
                "(named in its quotes) isn't in applies_when; the chart rule stays as it is and a person checks it")
    passing = next((ex["given"] for ex in rule.get("examples") or [] if ex.get("expect") == "pass"), None)
    if passing is None:
        return "a rule that relaxes another needs a passing example (with every condition met)"
    from rule_format.rulebook import outcome as _outcome
    loose = [m for m in named if _outcome(rule, passing | {m: 0}, {}) != "not_applicable"]
    if loose:
        return (f"a rule that relaxes another must apply only when every condition holds: with {', '.join(loose)} at 0 "
                "it still applies; the chart rule stays as it is and a person checks it")
    return None


def _widened(rule: dict, context: dict) -> list[dict]:
    """The rule a relaxing rule widens, so a rulebook check of the relaxing rule sees its target."""
    target = rule.get("relaxes")
    if not target:
        return []
    return [r for r in (context.get("drafted") or {}).get(target.split(".")[0]) or [] if r["id"] == target]


def undecided_uses_flag(out: dict, law: dict, ctx: Context) -> None:
    """The chart's residential parking ("... per dwelling unit", and "For all other uses see §325-20") sets a
    requirement for every use. A drafted rule limited to the dwellings it can count (one unit's sleeping rooms: the
    one-family houses) leaves the buildings of several units, and every other use, with no rule: their parking was
    unchecked without a word (stage 1's gap re-draft; the hand keys flag them). Code adds, in each district, one
    flag for every use no rule of the unit decides (needs review; it never passes), citing the same cells."""
    import json as _json
    for district, rules in sorted(out["rules"].items()):
        mine = [r for r in rules if any(isinstance(x.get("cell"), dict) and x["cell"].get("section", "").startswith("Residential")
                                        and "per dwelling unit" in x["cell"].get("row", "") for x in r.get("sources") or [])]
        if not mine or any(not r.get("applies_when") for r in rules):
            continue
        decided = sorted(u for u in ctx.uses if any(
            outcome({"kind": "flag", "applies_when": r["applies_when"]}, {"use": u}, ctx.allowed()) != "not_applicable"
            for r in rules))
        left = sorted(set(ctx.uses) - set(decided))
        if not left:
            continue
        cells = [x for r in mine for x in r["sources"] if isinstance(x.get("cell"), dict)]
        several = [u for u in left if "dwelling" in use_label(u, ctx).lower()]
        rules.append({"id": f"{district}.{mine[0]['id'].split('.', 1)[1]}_undecided_uses", "kind": "flag",
                      "topic": mine[0]["topic"], "title": "Parking for the uses no drafted rule decides (a person checks)",
                      "applies_when": f"use not in {_json.dumps(decided)}",
                      "sources": [dict(c) for i, c in enumerate(cells) if c not in cells[:i]],
                      "examples": [{"given": {"use": u}, "expect": "needs_review"} for u in (several or left)[:2]]
                      + [{"given": {"use": decided[0]}, "expect": "not_applicable"}],
                      "notes": "Added by code, not drafted: the chart's parking applies to every use (per dwelling unit, "
                               "and for all other uses §325-20), and the drafted rules decide only "
                               + ", ".join(decided) + ". A building of several dwelling units needs every unit counted; "
                               "other uses go to §325-20.",
                      "drafted_by": mine[0]["drafted_by"], "status": "draft"})


def _could_apply(applies_when: str, use: str, ctx: Context) -> bool:
    return not applies_when or outcome({"kind": "flag", "applies_when": applies_when}, {"use": use},
                                       ctx.allowed()) != "not_applicable"


def filled_elsewhere(gap: dict, used: dict, cells: dict, templates: dict, out: dict, ctx: Context) -> bool:
    """A district cell one template couldn't fill (its footnotes or how many numbers it states differ from the other
    districts': R-2C's '35%/40% /50% [fn12]') isn't a gap when templates written for that form fill it: every number
    the cell states fills a slot of a rule kept for that district (fn12's three numbers, one per use), and for every
    use the failed template could apply to, some kept rule citing the cell applies too (a 'first number' narrowed to
    one use would leave the others unchecked). A cell only partly used, or partly covered, stays a gap."""
    keys = [tuple(c) for c in gap.get("cells") or []]
    if not keys:
        return False
    for key in keys:
        cell = cells.get(key)
        stated = set(range(1, len(cell_numbers(cell["value"])) + 1)) if cell else set()
        if not stated or not stated <= used.get(key, set()):
            return False
    district, suffix = gap["rule"].split(".", 1)
    failed = templates.get(suffix)
    when = (failed or {}).get("applies_when", "") or ""
    if failed is None or "{" in when:
        return False
    citing = [r for r in out["rules"].get(district, []) if any(
        isinstance(x.get("cell"), dict) and (x["page"], x["cell"]["section"], x["cell"]["row"], x["cell"]["column"]) in keys
        for x in r.get("sources") or [])]
    return all(any(_could_apply(r.get("applies_when", ""), u, ctx) for r in citing)
               for u in sorted(ctx.uses) if _could_apply(when, u, ctx))


def check_answer(answer: dict, unit: dict, context: dict, law: dict, ctx: Context, columns: list[str],
                 cells: dict, notes: dict[int, dict], drafted_by: str) -> dict:
    """Turn an answer into rules, every one checked by the inspector. Returns {rules: {district: [rule]},
    unresolved: [{rule, why}] (districts whose cells don't fit a working template), rejected: [{rule, why}]
    (templates that work nowhere), proposed: {name: measure}, problems: [...] (the rejections, as text)}."""
    out = {"rules": {}, "unresolved": [], "rejected": [], "proposed": {}, "problems": [], "templates": []}
    # a law piece that names its districts ("in the R-3a or R-3b Zoning District") applies only there, whatever the AI wrote
    scope, unread = text_scope(unit["text"], ctx.districts) if unit.get("piece") else (None, [])
    suffixes = [unit.get("prefix", "") + t["id_suffix"] for t in answer["templates"]]
    pending = []                               # (template, its dropped note amounts): settled from the kept flags
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
        binding_problems, valid = _binding_items(t, notes, unit.get("piece"))
        p += binding_problems
        if p:
            out["rejected"].append({"rule": f"{unit['id']}.{t['id_suffix']}", "why": "; ".join(p)})
            continue
        good, gaps = [], []                     # filled and valid; or (where, why) for a person
        saved, ctx.proposed = ctx.proposed, ctx.proposed | proposed
        try:
            for column in (columns if t["slots"] else [None]):
                if scope is not None and column is not None and district_name(column) not in scope:
                    continue                    # the law doesn't apply in this district: nothing to fill or list
                rule, why = fill_template(t, column, cells, sources, drafted_by)
                if why is None and (t.get("relaxes") or "").strip():
                    rule, why = link_relaxes(rule, t, column, unit, context.get("drafted") or {})
                if why is None:
                    rule, why = unclear_exemption(unclear_catch_all(rule, law, ctx), unit, law, ctx)
                if why is None:
                    rule = unenforced_lower_bound(rule, unit, law, ctx)
                if why is None and (bad := residential_parking_problems(rule, law, ctx) + narrowing_problems(rule, ctx)):
                    why = "; ".join(bad)
                if why is None and unread:
                    why = (f"the text names districts its scope can't be read from ({', '.join(unread)}): a person "
                           "decides which districts this rule applies to")
                elif why is None and scope is not None:
                    placed = in_scope(rule, scope)
                    for r in placed:            # each scope district's own copy, checked in its own rulebook
                        if problems := [x for x in validate({"district": r["id"].split(".")[0],
                                                             "rules": [r] + _widened(r, context)}, ctx)
                                        if x.startswith(r["id"] + ":")]:
                            gaps.append({"rule": r["id"], "why": "; ".join(problems[:3])})
                        else:
                            good.append((column, r))
                    continue                    # outside the scope: the law doesn't apply there, nothing to list
                if why is None and (problems := [x for x in validate({"district": rule["id"].split(".")[0],
                                                                      "rules": [rule] + _widened(rule, context)}, ctx)
                                                 if x.startswith(rule["id"] + ":")]):
                    why = "; ".join(problems[:3])
                if why is None:
                    good.append((column, rule))
                else:                           # the cells it couldn't fill, so they aren't listed a second time
                    gaps.append({"rule": f"{district_name(column) if column else 'general'}.{t['id_suffix']}", "why": why,
                                 "cells": [[s["page"], s["section"], s["row"].strip(), column] for s in t["slots"]]})
            if good:
                if unbacked := _backing(t, valid, good, cells, sources, drafted_by, ctx.allowed()):
                    gaps, good = [{"rule": f"{unit['id']}.{t['id_suffix']}", "why": w} for w in unbacked], []
                elif dropped := dropped_amounts(t, notes):
                    pending.append((t, dropped))
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
    settle_dropped_amounts(pending, out, notes, unit, ctx)
    used = cells_used(out)
    templates = {unit.get("prefix", "") + t["id_suffix"]: t for t in answer["templates"]}
    out["unresolved"] = [g for g in out["unresolved"] if not filled_elsewhere(g, used, cells, templates, out, ctx)]
    undecided_uses_flag(out, law, ctx)
    if unit.get("piece"):
        all_or_none(answer, unit, out)
    out["unresolved"] += exemption_gaps(unit, out, ctx)
    out["problems"] = [f"{r['rule']}: {r['why']}" for r in out["rejected"]]
    if scope is not None:
        out["scope"] = sorted(scope)
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


def chart_gaps(unit: dict, result: dict, cells: dict, columns: list[str]) -> list[dict]:
    """For a chart unit: every district cell of its section that states something ("-" and empty state
    nothing) and that no saved rule cites, for a person. So a row the drafter skipped can't vanish, in any
    district; a cell a template couldn't fill is already listed (by fill_template's reason) and isn't repeated."""
    if "section" not in unit:
        return []
    cited = {(s["page"], s["cell"]["section"], s["cell"]["row"], s["cell"]["column"]) for rules in result["rules"].values()
             for r in rules for s in r["sources"] if s.get("file") == CHART_FILE and "cell" in s}
    listed = {tuple(c) for g in result["unresolved"] for c in g.get("cells", [])}
    out = []
    for key, cell in cells.items():
        page, section, row, column = key
        if (page, section) != (unit["page"], unit["section"]) or column not in columns:
            continue
        if FOOTNOTE.sub("", cell["value"]).strip() in NOT_APPLICABLE or key in cited or key in listed:
            continue
        district = district_name(column)
        out.append({"rule": f"{district}.{unit['id']}",
                    "why": f"chart page {page}, {section!r}, row {row!r}: the {column} cell {cell['value']!r} has no "
                           "drafted rule (a person checks the requirement it sets)"})
    return out


EXCEPT = re.compile(r"\bexcept (?:an? )?((?:[a-z]+-family|[a-z]+)(?: or (?:[a-z]+-family|[a-z]+))*) dwellings?\b", re.IGNORECASE)
# A definition that makes a use a building of several dwellings: "A building containing three or more one-family
# dwellings" (ONE-FAMILY ATTACHED DWELLING), or one calling it a multiple dwelling.
SEVERAL_DWELLINGS = re.compile(r"\b(?:two|three|four|five|six|\d+)\s+or\s+more\b[^.]{0,40}\bdwellings\b|\bmultiple\s+dwelling",
                               re.IGNORECASE)


def _words(text: str) -> tuple[str, ...]:
    """A name's words, for matching a use's chart row label to a defined term ("One-family dwelling, semi-detached"
    and "ONE-FAMILY SEMIDETACHED DWELLING" are the same words)."""
    clean = re.sub(r"\[fn[\d,]+\]|[•]", " ", text)
    return tuple(sorted(re.sub(r"[^a-z]", "", w) for w in re.split(r"[\s,]+", clean.lower()) if re.sub(r"[^a-z]", "", w)))


def _same_words(a: tuple, b: tuple) -> bool:
    """The same words, a hyphen joining two of them aside ("DAY-CARE" and "day care", "SEMIDETACHED" and "semi-detached")."""
    def joined(t):
        t = list(t)
        return {tuple(sorted(t))} | {tuple(sorted(t[:i] + [t[i] + t[i + 1]] + t[i + 2:])) for i in range(len(t) - 1)} | \
            {tuple(sorted(t[:i] + [t[i + 1] + t[i]] + t[i + 2:])) for i in range(len(t) - 1)}
    return bool(joined(a) & joined(b))


def use_label(use: str, ctx: Context) -> str:
    """A use's own chart row label, from the row uses.yaml cites ("One-family dwelling, attached [fn4] - - ..."):
    the words before the marks."""
    quote = (ctx.use_rows.get(use) or [{}])[0].get("quote", "")
    return re.split(r"\s+(?:[•\-]|SP)(?:\s|\[|$)", quote, maxsplit=1)[0].strip()


def use_definition(use: str, law: dict, ctx: Context) -> tuple[str, dict] | None:
    """(the defined term, its source) for a use whose chart label is a term §325-3B defines, found by the term's own
    words (ONE-FAMILY ATTACHED DWELLING for "One-family dwelling, attached"), never guessed from the use id."""
    label = _words(use_label(use, ctx))
    for pid, piece in law.get("pieces", {}).items():
        if pid.startswith("325-3B:") and label and _same_words(_words(piece.get("title", "")), label):
            text = " ".join(piece_text(law["rows"], piece).split())
            sentence = re.split(r"(?<=[.;])\s", text, maxsplit=1)[0]
            source, _why = find_quote(sentence, piece, law["file"], ctx)
            return piece["title"], (source or {}) | {"definition": text}
    return None


def _exempted(rule: dict, use: str, ctx: Context) -> bool:
    """The rule's condition leaves this use out, whatever its form (`use not in [...]`, `use != "..."`, a tuple, a
    positive `use in [...]`): judged by the evaluator, never by reading the formula's text."""
    from rule_format.rulebook import outcome
    if not rule.get("applies_when"):
        return False
    return outcome({"kind": "flag", "applies_when": rule["applies_when"]}, {"use": use}, ctx.allowed()) == "not_applicable"


def _drop_from_exemption(when: str, use: str) -> str | None:
    """applies_when with `use` taken out of the exemption, rewritten on its parsed form: a `use not in [...]` (or
    (...)) list loses the use, a `use != "use"` test is dropped from the `and`. None for any other form: a person
    decides; "" when the exemption was the whole condition (nothing is left: the rule applies to every use). The text
    is rebuilt from the parsed pieces, never edited as a string."""
    import ast
    from rule_format import formula
    tree = formula.parse(when).body
    parts = tree.values if isinstance(tree, ast.BoolOp) and isinstance(tree.op, ast.And) else [tree]
    out, changed = [], False
    for part in parts:
        src = ast.get_source_segment(when, part)
        if isinstance(part, ast.Compare) and len(part.ops) == 1 and isinstance(part.left, ast.Name) \
                and part.left.id == "use":
            op, right = part.ops[0], part.comparators[0]
            if isinstance(op, ast.NotIn) and isinstance(right, (ast.List, ast.Tuple)):
                kept = [e.value for e in right.elts if isinstance(e, ast.Constant)]
                if use in kept:
                    kept = [u for u in kept if u != use]
                    changed = True
                    if kept:
                        out.append("use not in [" + ", ".join(f'"{u}"' for u in kept) + "]")
                    continue
            if isinstance(op, ast.NotEq) and isinstance(right, ast.Constant) and right.value == use:
                changed = True
                continue
        out.append(f"({src})" if isinstance(part, ast.BoolOp) else src)
    return " and ".join(out) if changed else None


def unclear_exemption(rule: dict, unit: dict, law: dict, ctx: Context) -> tuple[dict | None, str | None]:
    """A law piece exempting "a one-family or two-family dwelling" doesn't plainly exempt a use §325-3B defines as a
    building of several dwellings (ONE-FAMILY ATTACHED DWELLING: "A building containing three or more one-family
    dwellings"). A drafted rule that leaves such a use out says "doesn't apply" where the law is unclear: a false
    pass. Judged by meaning (the evaluator says the rule doesn't apply to the use); the use is taken out of the
    exemption on the formula's parsed form and sent to review, citing the definition. A form that can't be rewritten
    sends the rule to a person: (None, why). Returns (rule, None) otherwise."""
    m = EXCEPT.search(" ".join(unit.get("text", "").split()))
    if not (m and unit.get("piece")):
        return rule, None
    family = [w.lower() for w in re.split(r"\s+or\s+", m.group(1))]          # one-family, two-family
    review, sources, gone = list(rule.get("review_when") or []), list(rule.get("sources") or []), set()
    for use in sorted(ctx.uses):
        label = use_label(use, ctx).lower()
        if not (any(f in label for f in family) and _exempted(rule, use, ctx)):
            continue
        found = use_definition(use, law, ctx)
        if not (found and SEVERAL_DWELLINGS.search(found[1]["definition"])):
            continue
        term, source = found
        when = _drop_from_exemption(rule["applies_when"], use)
        if when == "":                          # the exemption was the whole condition: the rule applies to every use
            candidate = {k: v for k, v in rule.items() if k != "applies_when"}
        else:
            candidate = rule | {"applies_when": when} if when else None
        if candidate is None or _exempted(candidate, use, ctx):
            return None, (f"the exemption ({m.group(0)!r}) may not cover {use}, which §325-3B defines as a building of "
                          "several dwellings, and this rule's condition can't be rewritten by code: a person decides")
        quote = " ".join(source["definition"].split())[:160]
        review.append({"when": f'use == "{use}"',
                       "reason": f"§325-3B defines {term} as {quote!r}: whether the exemption ({m.group(0)!r}) covers it "
                                 "is unclear. A person decides."})
        cite = {k: v for k, v in source.items() if k != "definition"}
        sources += [copy_of(r) for r in ctx.use_rows.get(use, [])[:1] + ([cite] if cite.get("quote") else [])
                    if r not in sources]
        rule, gone = candidate, gone | {use}
    if not gone:
        return rule, None
    return rule | {"review_when": review, "sources": sources,
                   "examples": [ex for ex in rule.get("examples") or [] if ex["given"].get("use") not in gone]}, None


def copy_of(source: dict) -> dict:
    """A source's own copy, so a saved rulebook never shares one object between rules (no YAML aliases)."""
    import copy
    return copy.deepcopy(source)


def _checked_names(rule: dict) -> set[str]:
    """The measures a rule's check is about: the measure each comparison tests (lot_area in `lot_area >= 9000`,
    building_area in `building_area <= 0.75 * 0.35 * lot_area`, where lot_area is only an input), selectors aside."""
    import ast
    from rule_format import formula
    if not rule.get("check"):
        return set()
    return {n.left.id for n in ast.walk(formula.parse(rule["check"]))
            if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name)} - {"use", "district"}


def exemption_gaps(unit: dict, result: dict, ctx: Context) -> list[dict]:
    """A law piece that exempts named dwellings ("any permitted use ..., except a one-family or two-family dwelling")
    reaches every other use. A use a drafted rule leaves out (judged by the evaluator: the rule doesn't apply to it)
    that the exemption doesn't name, and that no other rule of the unit applies to in that district, goes to a
    person: otherwise a group house on an R-3a lot next to R-1 escapes §325-19E's 150% lot area unchecked."""
    m = EXCEPT.search(" ".join(unit.get("text", "").split()))
    if not m or not unit.get("piece"):
        return []
    family = [w.lower() for w in re.split(r"\s+or\s+", m.group(1))]
    out = []
    for district, rules in result["rules"].items():
        for r in rules:
            for use in sorted(ctx.uses):
                if any(f in use_label(use, ctx).lower() for f in family) or not _exempted(r, use, ctx):
                    continue
                measured = _checked_names(r)
                if any(not _exempted(o, use, ctx) and _checked_names(o) & measured for o in rules if o is not r):
                    continue                    # another rule of the unit checks the same thing for it here
                out.append({"rule": r["id"], "why": f"the law exempts only {m.group(1)} dwellings, but this rule leaves "
                                                   f"out {use} and no other rule of {unit['id']} covers it here: a person "
                                                   "checks it"})
    return out


def keep(result: dict, unit: dict, cells: dict, columns: list[str], context: dict, last_attempt: bool = False) -> dict:
    """The answer kept for a unit, with everything it leaves for a person: on the last attempt its rejected
    templates, and always whatever the unit's input states that no saved rule covers (the law lines its
    label cites, the chart cells of its section, the sections it points to that were left out for length). The
    one way an answer is kept, by drafting and by replays."""
    if last_attempt:
        result["unresolved"] += result["rejected"]
        result["problems"] = []
    result["unresolved"] += requirement_gaps(unit, result) + chart_gaps(unit, result, cells, columns) + \
        [
        {"rule": unit["id"], "why": f"it points to {pid}, which was left out of the drafter's input for length "
                                    "(a person checks it)"} for pid in context.get("dropped", [])] + [
        {"rule": unit["id"], "why": f"it points to {pid}, which matches no section of the law, so the drafter never "
                                    "saw it (a person checks it)"} for pid in context.get("unfound", [])]
    return result


STREAM_ABOVE = 16000   # the SDK refuses a plain request it expects to run past 10 minutes (32,000 output tokens did)


def send(client, **request):
    """One API call: streamed when its output limit is large (the SDK requires it; the answer is the same message),
    else a plain request."""
    if request["max_tokens"] > STREAM_ABOVE:
        with client.messages.stream(**request) as stream:
            message = stream.get_final_message()
            if getattr(message, "_request_id", None) is None:      # the final message doesn't carry it; the stream does
                try:
                    message._request_id = getattr(stream, "request_id", None)
                except (AttributeError, TypeError, ValueError):
                    object.__setattr__(message, "_request_id", getattr(stream, "request_id", None))
            return message
    return client.messages.create(**request)


def max_tokens_for(unit_id: str, settings: dict = SETTINGS) -> int:
    """The output limit for one unit: its own (settings' max_tokens_by_unit) or the default."""
    return int((settings.get("max_tokens_by_unit") or {}).get(unit_id, settings["max_tokens"]))


def draft_unit(client, unit: dict, context: dict, system: str, law: dict, ctx: Context, columns: list[str],
               cells: dict, notes: dict[int, dict], record, settings: dict = SETTINGS, budget=None) -> dict:
    """Draft one unit. Every template that works nowhere sends the answer back with the reasons (keeping
    nothing from it) until max_attempts; after the last attempt, the rules that work are kept and every
    rejected template and every requirement no rule cites goes to a person. Returns check_answer's result
    plus "reason" (no rules, and why) or "failed" (no usable answer)."""
    settings = settings | {"max_tokens": max_tokens_for(unit["id"], settings)}   # its worst case and its call
    topics = sorted(ctx.topics)
    drafted_by = f"rule_drafting/{settings['model']}"
    messages = [{"role": "user", "content": unit_message(unit, context)}]
    why, last = "no answer", None
    for attempt in range(1, settings["max_attempts"] + 1):
        worst = worst_case(len(system) + len(json.dumps(messages, default=str)), settings, PRICES)
        if budget is not None:
            budget.reserve(worst)
        response = send(client,                              # if this raises, the worst case stays charged
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
                "context_dropped": context.get("dropped", []), "context_unfound": context.get("unfound", []),
                "answer": text, "problem": why, "usage": usage, "cost_usd": round(spent, 6),
                "budget_usd": settings["budget_usd"], "ledger_spent_usd": round(budget.spent, 6) if budget else None})
        if crash is not None:
            raise crash
        if why is None:
            return keep(result, unit, cells, columns, context)
        if response.stop_reason == "refusal":
            break
        if response.stop_reason == "end_turn":
            messages += [{"role": "assistant", "content": response.content},
                         {"role": "user", "content": f"That answer can't be used: {why}. Answer again for the same "
                                                     "text, with every template (the ones that worked too)."}]
    if last is not None:                        # the last answer that had working rules: keep those
        return keep(last, unit, cells, columns, context, last_attempt=True)
    return {"failed": why, "rules": {}, "unresolved": [], "rejected": [], "proposed": {}, "problems": [], "templates": []}
