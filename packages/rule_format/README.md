# rule_format

The shape every rule must have, the formula language rules are written in, and the code that checks rule files. Plain code, no AI.

## A rule

```yaml
- id: R-1b.rear_yard                 # district + short name
  kind: rule                         # rule: code checks it · flag: an architect must judge it
  topic: dimensions                  # from regulations/document_extraction_guide/vocabulary.yaml
  title: Rear yard minimum (chart p.3, note 16)   # a one-line label (≤ 80 chars), not a retelling
  applies_when: use == "one_family_detached"     # optional; otherwise applies to everything
  check: rear_yard >= max(min(0.25 * lot_depth, 50), 20)
  review_when:                                   # optional; true -> "needs review"
    - when: lot_depth > 500
      reason: unusually deep lot
  sources:
    - file: zoning_charts_2026-04.pdf            # must be listed in sources.yaml
      page: 3
      lines: [42, 43]                            # where on the page: first and last line of the quote
      quote: "Rear (minimum, % of depth or feet, 25%/ 25%/ 25%/ 25%/ 25%/ 20%/ 25%/ 20%/ 25% / whichever is less) 50 ft [fn16] 50 ft [fn16]"
                                                 # exactly as extracted, starting on line 42 and ending on 43
  examples:                                      # need a pass and a fail; each must come out as stated
    - given: {use: one_family_detached, rear_yard: 25, lot_depth: 90}
      expect: pass
    - given: {use: one_family_detached, rear_yard: 21, lot_depth: 90}
      expect: fail
  notes: 106 Ithaca Rd needs 23.7 ft            # optional explanation; never used to decide a result
  drafted_by: claude
  open_questions: []                             # interpretations for the architects; none allowed once approved
  research: []                                   # for each open question: what was searched, why it's still open
  findings: []                                   # what research settled: the law's answer, or a reading to confirm
  answers: []                                    # architects' answers: {question, answer, answered_by, answered_on}
  status: draft                                  # approved also needs approved_by, approved_on, approved_hash
```

## Rules for each part

A rule can repeat over the parts of a building ("for each sleeping room", "for each escape opening of each sleeping room", "for each stair") and give one result per part, so the panel names the one that fails: "Bedroom 2 › Window 5: net clear area 5.1 sq ft, needs ≥ 5.7 sq ft". Why and what was rejected: [docs/decisions/2026-11-12_rules_for_each_part.md](../../docs/decisions/2026-11-12_rules_for_each_part.md).

```yaml
  for_each: emergency_escape_opening   # a part kind from rule_format/parts.yaml (engineers write the list)
  within: sleeping_room                # optional: grouped by the part they sit in (one of the kind's `within`)
  when_none: fail                      # what the law says when there's nothing to check: fail, needs_review or
                                       # not_applicable (never pass). With `within`: a room with none gets this row
  check: opening_net_clear_area >= (5.0 if opening_at_grade else 5.7)   # the part's measures + the building's
```

`parts.rows(rule, parts, values, allowed)` gives the rows: each part through the same evaluation as `outcome()` (`parts.part_outcome`). A kind not read (not a list), a part with no id or a shared id, a part within a part that isn't there: a needs-review row each, never nothing. `parts.rule_result` gives the rule's one answer (any fail → fail; any needs review → needs review; else pass if any part passes; only not-applicable → not applicable). `outcome()` itself says needs review for a per-part rule, so code that doesn't know about parts never passes one. Validation refuses an unknown part kind, a `within` the kind can't sit in, a missing or `pass` `when_none`, another kind's measures, and a part measure in `applies_when` unless `when_none` is `not_applicable` (say how parts differ inside `check`). The new fields are optional and fingerprinted only when present, so existing rules and their approval fingerprints are unchanged.

A per-part rule may carry a `limit` (section group 8d): the part's own requirement, apart from whether the law asks it of this part, so code can tell which parts comply (the New York Building Code's escape openings: `design_checker/escape_openings.py` holds every escape-opening rule's limit to each opening with `formula.evaluate`, three-valued, and counts a sleeping room's compliant ones for 1031.2). It reads only the part's own figures (never a fact copied onto the part from another, marked `from` in parts.yaml, like an escape opening's room facts), and it can't drift from the check: validation (`parts.limit_problems`) reads the parsed formulas, not their text, and refuses a check that isn't a top-level `(<limit>) or <set-aside>` (the rest reading none of the limit's measures), any `review_when` that isn't a top-level `... and not (<limit>) and ...`, any `if ... else`, and a limit whose measures the rule reads anywhere else. An escape-opening rule with no limit leaves every opening's compliance unknown, never counted (review round 1 of 8d). The rule export shows it as its own column.

A per-part rule's worked examples are small designs, checked by `parts.rows` itself: the building's measures (`given`), the parts (`parts`, as the checker gets them), every row expected (`rows`: `{part: id, within: id, outcome}`, `part` left out for a row about no one part) and the rule's one answer (`expect`). One must show `when_none` (a row for nothing to check, with the rule's `when_none` answer), and a rule's examples must have a part that passes its check and one that fails it (a "none" row doesn't exercise the check), or the rule is refused. A part missing a number fails when it fails whatever that number is (the 2026-10-21 proof, `rulebook.unknown_settings`, the same one the checker's zoning rows use); else it needs review.

## Formulas

Everyday math notation, read by a strict parser that rejects anything else: numbers, quoted text, measure names (`measures.yaml`), `+ - * /` on numbers, comparisons (`< <= > >=` on numbers, `== !=`), `in` / `not in` a `[list]`, `and` `or` `not`, `a if condition else b`, `min()` / `max()` of two or more numbers. Max 500 characters. `check`, `applies_when` and `review_when` must be true/false tests. Units are fixed per measure (ft, sf, count, text) and enforced: a text value for a number measure (or the reverse) → needs review. `==`, `!=` and `in` only compare like with like.

## Outcomes (never a false pass)

1. `applies_when` false → **not applicable**
2. `kind: flag` → **needs review**
3. any `review_when` true → **needs review**
4. `check` true / false → **pass** / **fail**

Fails closed: `outcome(rule, values, allowed)` requires the city's allowed text values (e.g. `{"use": uses}`). A measurement that is missing or unusable (none, NaN, infinite, negative, wrong kind, a `use` not in the list) is unknown, and unknowns follow three-valued logic: the result is pass or fail only if it is the same for every value that measurement could take (true or unknown is true; false and unknown is false), else **needs review**. A value the formula can't evaluate (divide by zero, a non-finite result) → **needs review**, never hidden under an unknown. A measure with no description can't be type-checked, so any formula using it → **needs review** (never three-valued), as does a formula that can't be read. Every formula is type-checked when rule files are validated (`formula.type_of`): one that is wrong for every value (text vs number, a number as true/false) is refused.

## Places (the registry)

Each place's settings live in its own folder, `regulations/jurisdictions/<state>/<place>/jurisdiction.yaml`: its
name, the codes that tell its land apart (SWIS), its coordinate system and time zone, which chart columns are
districts, its law files, and which lookup and measuring code serve it. `place.py` is the one reader: code asks
`place("new_york/ithaca_city")`, `places()` or `plugin_place()` instead of typing a place's values in. A place with no
settings file, or one with a missing or unusable field, is a plain error (`UnknownPlace`), never another place's
settings in its stead. The Rhino plugin's Python can't read YAML, so `python -m rule_format place --write` copies
what it needs to `packages/design_checker/design_checker/place.json`; `python -m rule_format` checks the copy is
current. Adding a place: [docs/adding_a_place.md](../../docs/adding_a_place.md).

## Checking rule files

```bash
python -m rule_format       # validates every jurisdiction's settings (jurisdiction.yaml), sources, 4_term_definitions/ (definitions.yaml,
                            # uses.yaml), 5_zoning_rules/ and test_data/answer_keys/, and the plugin's place.json
pytest packages/rule_format
```

Validation checks: file shape; required fields; no duplicate YAML keys; known measures, uses and topics; formulas parse and are true/false tests; source files listed in `sources.yaml` with matching fingerprints; extracted text made from that exact PDF version (CI also re-extracts the text from the PDF with `python -m document_extraction --check` and requires an exact match, so it can't be hand-edited); every quote found exactly on its cited lines as whole tokens (see below); at least one passing and one failing worked example, each giving its expected outcome, with values of the right kind; a `title` of one line and at most 80 characters (a label, not a retelling); `open_questions` a list of text, and empty before approval; `answers` each with question, answer, answered_by (a reviewer) and answered_on (a date), and part of the approval fingerprint; approved rules approved by someone in `regulations/reviewers.yaml` (never the drafter, never AI) on a date, with `approved_hash` matching the rule's current content, id and the fingerprints of the documents it cites (`rulebook.approval_hash`), so any edit, move, or replaced source document after approval needs re-approval. A file's `district` must match its file name. (The hash catches later edits; it doesn't prove who approved: see `docs/how_rules_are_checked.md`.)

Architect approval is deferred for now (decided 2026-10-19): rules stay `status: draft` and are used once every other check passes. The approval checks above apply when approval is switched on.

## How quotes are matched

The page text and the quote are both split into **tokens** with one rule (`rulebook.tokenize`): a footnote marker (`[fn11]`), a whole word or number (`rear`, `2.5`, `1,500`, `3/2`, `.5`), or a single other character (`%`, `(`, `§`). `.`, `,` and `/` join only digit to digit (`3/35`, `2.5`), and a leading `.` only starts a number (`.5`); so `minimum/maximum` is three tokens. A quote matches only as a run of **whole tokens**, so `5` can never match inside `25`, `2.5` or `1/2`, `R-1` never inside `R-1b`, and a quote may end on a number before a sentence's period. Spaces and line breaks between words don't matter; inside a number (`2.5`, `1,500`, `3/35`), or around a `.` before a digit (`A.5` is not `A .5`), the quote must match the page exactly. Case, curly quotes and dash styles are unified.

A source gives the **exact position** of its quote: the page and the first and last line (`lines: [first, last]`, the line numbers in `2_extracted_text`). The quote must start on the first line and end on the last, so it can't be matched anywhere else on the page. The quote must occur only once on the page, so a citation points at one place: a bare `35 ft` on a chart row is rejected; quote the row label too (`Height in feet 35 ft 35 ft`). One quote is one unbroken passage; cite separate passages as separate sources. To find the lines, run `python -m rule_format cite <state/place> <file> <page> "<quote>"`.

**Show your work (research before asking).** Rules, definitions and section labels share these checks
(`rulebook.research_problems`). Every open question needs exactly one `research` entry:
`{question (its exact text), searched (piece ids of the law that were read), sources, why_open, readings?, report?}`.
`searched` may be empty only while `why_open` starts with "pending" (a question raised by a drafting run says
`pending: ...`, from `rulebook.pending_research`). `readings` lists the readings still in play as
`{id, reading}` (two or more), for the measurement code to check a design under each. A question research settled
moves to `findings`: `{id?, question, kind, answer, sources, strength?, confirm_with?, report?}`. Kind `law` must
quote the code (a source `{file, page, lines, quote}`, verified like a rule's) and is `strong`. Kind `reading` has
a `strength` no higher than its best source (`strong` = the code, rank 1; `city_practice` = the City's own records,
rank 2; `moderate` = the NYS Uniform Code, IBC or IRC, rank 3; `weak` = other places' codes, rank 4; other sources
are `{rank, cite, url?, quote?}`, named and linked for a person since code can't check them) and says who should
confirm it (`confirm_with`). A question can't be both open and found. `report` names the research report and its
section ("docs/research/2026-10-20_architect_questions.md §2.1"); the file and the section must exist. Findings
are part of the approval fingerprint. An architect's or the City's answer (`answers`) outranks a reading.

Definitions (`4_term_definitions/definitions.yaml`) have `term`, `measures`, `sources` (the city's whole sentences, no paraphrase), `open_questions` with their `research`, `findings`, and once an architect answers a question, `answers`: `{question, answer, answered_by (a reviewer), answered_on}`. The answers are part of the approval fingerprint, so an answer can't change after approval. Use names (`uses.yaml`) have `name` and `sources`.

Section labels (`3_section_labels/<document>.yaml`, see `rule_format/labels.py`) are checked the same way: a label from the vocabulary, a known topic, a reason, a quote that is the city's words **inside its piece**, a fingerprint of the piece as labeled (re-cut or new PDF → label again), and the usual draft/approval rules.

Chart values: a quote pins the **row** (its line) but not the **column**. A source can instead cite one **chart cell**: `{file, page, cell: {section, row, column}}`, checked against the chart reader's cells (`2_extracted_text/*.cells.jsonl`; a part of a table the reader couldn't read with certainty can never be cited). A cited cell counts as citing its row's lines (so it satisfies the use-row check). The drafting script cites cells; a value read from the wrong district's column in a hand-drafted rule is caught by comparing it with the reader's cells (`packages/document_extraction/tests/test_r1b_matches_chart.py`) (architect review is deferred for now).

Numbers: every number in a formula (`check`, `applies_when`, `review_when`) must be written in one of the rule's own sources: a cited quote, or a cited cell or its row label. "25%" supports 0.25, number words count ("three"), footnote markers don't, and 0 needs no source. A worked-out number is written as the arithmetic from cited inputs (`35 + 0.1 * 35`, not 38.5).

Yes/no measures: a measure with unit `yes_no` is a true/false fact from the model ("the accessory dwelling unit has a separate entrance"); a formula may be just its name (`adu_separate_entrance`, `not accessory_in_required_front_yard`), and examples give it `true` or `false`. A measure a draft needs that isn't in `measures.yaml` yet is listed in the jurisdiction's `5_zoning_rules/drafted/records/proposed_measures.yaml`: rules may use it while drafts, but can't be approved until an engineer adds it to `measures.yaml`. `district` is a text measure whose values are the chart's district columns as the city writes them (R-1B → `R-1b`).
