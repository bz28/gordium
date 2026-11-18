# A rule that fails whatever a missing number is does not comply (2026-10-21)

**Purpose:** when a rule that waits on a number Gordium couldn't measure still gives "does not comply".\
**For:** architects reading the panel, and engineers changing how rules are checked.\
**Kept current by:** the engineer who changes `design_checker/check.py` (`fails_whatever`) or `rule_format/formula.py` (`truth_direction`), in that PR.

Missing data normally gives **needs review** ([principle 4](../../CLAUDE.md): never a false pass). Sometimes the answer is already known anyway. If a design fails a rule for every value the missing number could take, it fails. This is the same every-reading rule Gordium already uses for open questions. Words in links are defined in the [glossary](../glossary.md).

## Decision

1. **The rule does not comply** when every value it needs that is missing (no value, no readings) is one of these, and the rule fails under every setting of them:
   - a number the rule is provably truest at when it is 0: it is taken at 0 (measures are never negative);
   - a yes/no fact: tried both ways.

   Then it fails whatever the missing values are. Any other missing value (a text, a number not proven) leaves it needs review.
2. **"Provably truest at 0" is proven from the formula's structure, never sampled** (`formula.truth_direction`). It is proven only for +, −, max/min, and multiplying or dividing by a positive number, compared with < ≤ > ≥ and combined with and/or/not. Anything else is left to needs review: equality, two measures multiplied together, if-else, a chain like `20 <= h <= 35`, or opposite directions in one rule.
3. **No missing value may appear in the rule's applies_when or review_when.** Those decide whether the rule applies at all, so the answer can't be known without the number.
4. **Never the other way.** This proof only ever turns needs review into does not comply; a missing number never causes a pass. A rule complies with a number missing only when the known numbers already settle it: formulas use three-valued logic (`formula.evaluate`: "True or unknown is True"), so `building_height <= 35 or front_yard >= 40` with a 30 ft house and the front yard unknown passes, because no front yard could change the answer, and the row complies (`check.row_verdict`; not on a tax-map lot with a lot measure in the rule, where it needs review). A rule the missing number could still decide needs review; so does one that passes at every value only by working the formula through (`max(front_yard, 50) >= 40` stays needs review). No false pass is possible: a definite answer comes back only when it holds for every value the missing number could take.
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
- **A matching proof for passing** (proving from the formula's structure that a rule passes at every value, as item 2 does for failing): not added. A missing number never causes a pass (principle 4); a rule complies with a number missing only where three-valued logic already shows no value could change the answer (item 4).

## Consequences

- An eaves row whose design misses even the base requirement now shows red with the height unknown.
- It runs before a rule waiting on an interior fact (bedrooms, parking) is set aside as "not checked yet": a rule proven to fail is never hidden there.
- Pinned in `packages/design_checker/tests/test_moved_and_crossing.py` (the eaves cases, the guard, several unknowns, interior rows) and `packages/rule_format/tests/test_formula.py` (the proof).
