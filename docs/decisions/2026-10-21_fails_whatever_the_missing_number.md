# A rule that fails whatever a missing number is does not comply (2026-10-21)

**Purpose:** when a rule that waits on a number Gordium couldn't measure still gives "does not comply".\
**For:** architects reading the panel, and engineers changing how rules are checked.\
**Kept current by:** the engineer who changes `design_checker/check.py` (`fails_whatever`) or `rule_format/formula.py` (`truth_direction`), in that PR.

Missing data normally gives **needs review** ([principle 4](../../CLAUDE.md): never a false pass). Sometimes the answer is already known anyway. If a design fails a rule for every value the missing number could take, it fails. This is the same every-reading rule Gordium already uses for open questions. Words in links are defined in the [glossary](../glossary.md).

## Decision

1. **The rule does not comply** when all of these hold:
   - exactly one number the rule needs is unmeasured (no value, no readings);
   - the rule is provably truest when that number is 0;
   - the rule fails at 0.

   Measures are never negative, so it then fails at every value.
2. **"Provably truest at 0" is proven from the formula's structure, never sampled** (`formula.truth_direction`). It is proven only for +, −, max/min, and multiplying or dividing by a positive number, compared with < ≤ > ≥ and combined with and/or/not. Anything else is left to needs review: equality, two measures multiplied together, if-else, a chain like `20 <= h <= 35`, or opposite directions in one rule.
3. **The missing number may not appear in the rule's applies_when or review_when.** Those decide whether the rule applies at all, so the answer can't be known without the number.
4. **Never the other way.** Missing data never makes a rule comply.
5. **On a lot from the tax map**, the rule must also fail when the lot lines are 2 ft off in its favour. There the missing number is taken at 0, where the rule is truest.

### Worked example

The eaves rule for the front yard: eaves ≥ 25 + max(height − 35, 0) − 2. The required distance only grows with the height, so it is at least 23 ft at any height. When the ground isn't given, the height can't be measured:

| Front eaves | Result with the height unknown |
|---|---|
| 15'-0" | **Does not comply**: 15 < 23, whatever the height ("Does not comply even before the §325-16C height bonus") |
| 24'-0" | **Needs review**: meets 23 ft, but a house over 36 ft would need more |
| 22'-0" on a tax-map lot | **Needs review**: 22 < 23 as drawn, but 24 ft if the street line is 2 ft off in its favour |

## Why

"Needs review" on a design that can't comply hides a real failure behind a missing fact. Ben decided on 2026-10-21 that the every-reading rule applies to unknown values too.

## What we rejected

- **Trying sample values:** a few heights can't prove "every height".
- **A general interval evaluator:** larger than the cases need, and more to get wrong. The structural proof covers the rulebook's formulas (the §325-16C height bonus) and leaves everything else as needs review.
- **Complying when the rule passes at every value:** missing data never complies (principle 4).

## Consequences

- An eaves row whose design misses even the base requirement now shows red with the height unknown.
- Pinned in `packages/design_checker/tests/test_moved_and_crossing.py` (the eaves cases, the guard) and `packages/rule_format/tests/test_formula.py` (the proof).
