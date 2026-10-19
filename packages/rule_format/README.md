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
      quote: "Rear (minimum, % of depth … whichever is less)"   # must appear on that page ('…' skips text)
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
python -m rule_format       # validates every jurisdiction's 5_zoning_rules/ and answer keys
pytest packages/rule_format
```

Validation checks: file shape; required fields; no duplicate YAML keys; known measures, uses and topics; formulas parse and are true/false tests; source files listed in `sources.yaml` with matching fingerprints; extracted text made from that exact PDF version; every quote found on its cited page as whole tokens (see below; each piece 15+ characters not counting spaces, at most two `…` gaps of up to 60 tokens); at least one passing and one failing worked example, each giving its expected outcome, with values of the right kind; `open_questions` a list of text, and empty before approval; approved rules approved by someone in `regulations/reviewers.yaml` (never the drafter, never AI) on a date, with `approved_hash` matching the rule's current content, id and the fingerprints of the documents it cites (`rulebook.approval_hash`), so any edit, move, or replaced source document after approval needs re-approval. A file's `district` must match its file name. (The hash catches later edits; it doesn't prove who approved: see `docs/how_rules_are_checked.md`.)

## How quotes are matched

The page text and the quote are both split into **tokens** with one rule (`rulebook.tokenize`): a footnote marker (`[fn11]`), a whole word or number (`rear`, `2.5`, `1,500`, `3/2`, `.5`), or a single other character (`%`, `(`, `§`). `.`, `,` and `/` join only digit to digit (`3/35`, `2.5`), and a leading `.` only starts a number (`.5`); so `minimum/maximum` is three tokens. A quote matches only as a run of **whole tokens**, so `5` can never match inside `25`, `2.5` or `1/2`, `R-1` never inside `R-1b`, and a quote may end on a number before a sentence's period. Spaces and line breaks between words don't matter; inside a number (`2.5`, `1,500`, `3/35`), or around a `.` before a digit (`A.5` is not `A .5`), the quote must match the page exactly. Case, curly quotes and dash styles are unified. `…` skips at most 60 tokens (words, numbers and single symbols: about two lines).
