# rule_format

The shape every rule must have, the formula language rules are written in, and the code that checks rule files. Plain code, no AI.

## A rule

```yaml
- id: R-1b.rear_yard                 # district + short name
  kind: rule                         # rule: code checks it · flag: an architect must judge it
  topic: dimensions                  # from regulations/document_extraction_guide/vocabulary.yaml
  says: Rear yard at least 25% of lot depth or 50 ft, whichever is less, never under 20 ft.
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
  drafted_by: claude
  open_questions: []                             # interpretations for the architects; none allowed once approved
  status: draft                                  # approved also needs approved_by, approved_on, approved_hash
```

## Formulas

Everyday math notation, read by a strict parser that rejects anything else: numbers, quoted text, measure names (`measures.yaml`), `+ - * /` on numbers, comparisons (`< <= > >=` on numbers, `== !=`), `in` / `not in` a `[list]`, `and` `or` `not`, `a if condition else b`, `min()` / `max()` of two or more numbers. Max 500 characters. `check`, `applies_when` and `review_when` must be true/false tests. Units are fixed per measure (ft, sf, count, text) and enforced: a text value for a number measure (or the reverse) → needs review. `==`, `!=` and `in` only compare like with like.

## Outcomes (never a false pass)

1. `applies_when` false → **not applicable**
2. `kind: flag` → **needs review**
3. any `review_when` true → **needs review**
4. `check` true / false → **pass** / **fail**

Fails closed: `outcome(rule, values, allowed)` requires the city's allowed text values (e.g. `{"use": uses}`), and a measurement that is missing or unusable (none, NaN, infinite, negative, wrong kind, a `use` not in the list, or a measure with no description), or a value the formula can't evaluate (text vs number, divide by zero, a non-finite result), at any step → **needs review**.

## Checking rule files

```bash
python -m rule_format       # validates every jurisdiction's sources, 4_term_definitions/ (definitions.yaml,
                            # uses.yaml), 5_zoning_rules/ and test_data/answer_keys/
pytest packages/rule_format
```

Validation checks: file shape; required fields; no duplicate YAML keys; known measures, uses and topics; formulas parse and are true/false tests; source files listed in `sources.yaml` with matching fingerprints; extracted text made from that exact PDF version (CI also re-extracts the text from the PDF with `python -m document_extraction --check` and requires an exact match, so it can't be hand-edited); every quote found exactly on its cited lines as whole tokens (see below); at least one passing and one failing worked example, each giving its expected outcome, with values of the right kind; `open_questions` a list of text, and empty before approval; approved rules approved by someone in `regulations/reviewers.yaml` (never the drafter, never AI) on a date, with `approved_hash` matching the rule's current content, id and the fingerprints of the documents it cites (`rulebook.approval_hash`), so any edit, move, or replaced source document after approval needs re-approval. A file's `district` must match its file name. (The hash catches later edits; it doesn't prove who approved: see `docs/how_rules_are_checked.md`.)

Architect approval is deferred for now (decided 2026-10-19): rules stay `status: draft` and are used once every other check passes. The approval checks above apply when approval is switched on.

## How quotes are matched

The page text and the quote are both split into **tokens** with one rule (`rulebook.tokenize`): a footnote marker (`[fn11]`), a whole word or number (`rear`, `2.5`, `1,500`, `3/2`, `.5`), or a single other character (`%`, `(`, `§`). `.`, `,` and `/` join only digit to digit (`3/35`, `2.5`), and a leading `.` only starts a number (`.5`); so `minimum/maximum` is three tokens. A quote matches only as a run of **whole tokens**, so `5` can never match inside `25`, `2.5` or `1/2`, `R-1` never inside `R-1b`, and a quote may end on a number before a sentence's period. Spaces and line breaks between words don't matter; inside a number (`2.5`, `1,500`, `3/35`), or around a `.` before a digit (`A.5` is not `A .5`), the quote must match the page exactly. Case, curly quotes and dash styles are unified.

A source gives the **exact position** of its quote: the page and the first and last line (`lines: [first, last]`, the line numbers in `2_extracted_text`). The quote must start on the first line and end on the last, so it can't be matched anywhere else on the page. The quote must occur only once on the page, so a citation points at one place: a bare `35 ft` on a chart row is rejected; quote the row label too (`Height in feet 35 ft 35 ft`). One quote is one unbroken passage; cite separate passages as separate sources. To find the lines, run `python -m rule_format cite <state/place> <file> <page> "<quote>"`.

Definitions (`4_term_definitions/definitions.yaml`) have `term`, `measures`, `sources` (the city's whole sentences, no paraphrase), `open_questions`, and once an architect answers a question, `answers`: `{question, answer, answered_by (a reviewer), answered_on}`. The answers are part of the approval fingerprint, so an answer can't change after approval. Use names (`uses.yaml`) have `name` and `sources`.

Chart values: a quote pins the **row** (its line) but not yet the **column**. Until the chart reader (step 5, next PRs) cites table cells by row and column, a value read from the wrong district's column is caught by comparing the hand-written answer key with the chart reader's output, and by architect review.
