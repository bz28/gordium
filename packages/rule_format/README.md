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

## Formulas

Everyday math notation, read by a strict parser that rejects anything else: numbers, quoted text, measure names (`measures.yaml`), `+ - * /` on numbers, comparisons (`< <= > >=` on numbers, `== !=`), `in` / `not in` a `[list]`, `and` `or` `not`, `a if condition else b`, `min()` / `max()` of two or more numbers. Max 500 characters. `check`, `applies_when` and `review_when` must be true/false tests. Units are fixed per measure (ft, sf, count, text) and enforced: a text value for a number measure (or the reverse) → needs review. `==`, `!=` and `in` only compare like with like.

## Outcomes (never a false pass)

1. `applies_when` false → **not applicable**
2. `kind: flag` → **needs review**
3. any `review_when` true → **needs review**
4. `check` true / false → **pass** / **fail**

### An exception that widens a rule (`relaxes`)

Some law is a limit plus an exception that allows more under conditions: the chart's 35 ft height, and §325-16C's extra 10% when every yard is increased by the extra height. The exception can be its own rule that names the rule it widens:

```yaml
- id: R-1b.height_chart
  check: building_height <= 35
- id: R-1b.height_bonus
  relaxes: R-1b.height_chart        # a rule of the same rulebook (same district)
  applies_when: front_yard >= 25 + (building_height - 35) and ...   # the exception's conditions, all of them
  check: building_height <= 35 + 0.1 * 35
```

The checker reads the widened rule as `its own check or (each relaxing rule's applies_when and its check)`, in the same three-valued logic, so:

- it passes if its own check passes, or if a relaxing rule's conditions are **all** met **and** that rule's check passes; never otherwise;
- an unknown condition can only turn a fail into **needs review**, never into a pass;
- each relaxing rule widens on its own; a relaxing rule's `review_when` applies where the widening is what decides;
- the relaxing rule is still its own rule too, and is never widened itself.

The composition is `apply_relaxes(rules)`, applied where rules are read for checking (`zone_rules`, the project report), and a widened rule's worked examples are judged as the checker reads it. Rule-file checks refuse a `relaxes` that names no rule of the same rulebook, names itself, names a flag (nothing to widen), comes from a rule with no `applies_when` or `check`, or forms a cycle. `test_relaxes.py` shows the hand R-1b height (one combined formula) and the relaxes version give the same verdict for every design in a grid of heights, yards and missing values.

Fails closed: `outcome(rule, values, allowed)` requires the city's allowed text values (e.g. `{"use": uses}`). A measurement that is missing or unusable (none, NaN, infinite, negative, wrong kind, a `use` not in the list) is unknown, and unknowns follow three-valued logic: the result is pass or fail only if it is the same for every value that measurement could take (true or unknown is true; false and unknown is false), else **needs review**. A value the formula can't evaluate (divide by zero, a non-finite result) → **needs review**, never hidden under an unknown. A measure with no description can't be type-checked, so any formula using it → **needs review** (never three-valued), as does a formula that can't be read. Every formula is type-checked when rule files are validated (`formula.type_of`): one that is wrong for every value (text vs number, a number as true/false) is refused.

## Checking rule files

```bash
python -m rule_format       # validates every jurisdiction's sources, 4_term_definitions/ (definitions.yaml,
                            # uses.yaml), 5_zoning_rules/ and test_data/answer_keys/
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
