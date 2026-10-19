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
      quote: "Rear (minimum … 25%/ 50 ft"        # must appear on that page ('…' skips text)
  examples:                                      # each must produce its expected outcome
    - given: {use: one_family_detached, rear_yard: 25, lot_depth: 90}
      expect: pass
  drafted_by: claude
  status: draft                                  # approved also needs approved_by + approved_on
```

## Formulas

Everyday math notation, read by a strict parser that rejects anything else: numbers, quoted text, measure names (`measures.yaml`), `+ - * /` on numbers, comparisons (`< <= > >=` on numbers, `== !=`), `in` / `not in` a `[list]`, `and` `or` `not`, `a if condition else b`, `min()` / `max()` of two or more numbers. Max 500 characters. `check`, `applies_when` and `review_when` must be true/false tests. Units are fixed per measure (ft, sf, count).

## Outcomes (never a false pass)

1. `applies_when` false → **not applicable**
2. `kind: flag` → **needs review**
3. any `review_when` true → **needs review**
4. `check` true / false → **pass** / **fail**

A missing or unusable measurement (none, NaN, infinite), or a value the formula can't evaluate (text vs number, divide by zero), at any step → **needs review**.

## Checking rule files

```bash
python -m rule_format       # validates every jurisdiction's 5_zoning_rules/ and answer keys
pytest packages/rule_format
```

Validation checks: file shape; required fields; no duplicate YAML keys; known measures, uses and topics; formulas parse and are true/false tests; source files listed in `sources.yaml` with matching fingerprints; extracted text made from that exact PDF version; every quote at least 15 characters and found on its cited page; every worked example gives its expected outcome; approved rules approved by someone in `regulations/reviewers.yaml` (never the drafter, never AI) on a real date.
