# Eval 2026-10-20: drafting prompt A vs the earlier prompt

**Question:** does the rewritten drafting prompt ("prompt A") draft better rules than the earlier one? It is
kept only if it is at least as good on every measure.

**Prompt A** (in `rule_drafting/drafter.py`, `FORMAT`) adds what the labeling guide gained in its rewrite: who
the drafter is (a senior zoning plan examiner and licensed architect), why it matters (Gordium checks designs with
plain code; never a false pass; every number traceable; code checks everything), and the steps in order. It
states today's number rule (Ben's policy B: a typed number is trusted only from a sentence of the paragraph
being drafted, a footnote marked on the slot's own cell, or that slot's own row label; anything else is
refused). Three new instructions came from the earlier run's rejections: leave `applies_when` empty rather than
writing a placeholder test (`true`, `lot_area > 0`); draft only the text's own requirements (the chart's height
row is drafted as a plain limit, and §325-16C's extra height is drafted from §325-16C); and choose worked
examples that cover every branch and tier (parking above 5 bedrooms). It removes two outdated statements
(numbers sent to an architect as open questions; every slot must decide something).

## How it was run

- **Same 10 units both times:** chart page 2 uses (built by code), chart page 3 lot size, lot width, building
  height, lot coverage and yards, chart page 14 residential parking, and law pieces 325-16C, 325-18A and 325-19C.
  Same model (`claude-sonnet-5-5`, effort medium), same settings.
- **Baseline:** the earlier prompt's real answers from 2026-10-19 (`runs/baseline_…jsonl`, commit 6f3bdd8),
  replayed through today's checks with `replay.py`. Each unit's recorded attempts are judged in order, the
  same way `draft_unit` judges them. Those answers predate the `numbers` field, so each typed number gets every
  binding policy B could trust. That is the best case for the baseline. No new calls were made.
- **Prompt A:** a new run of the same units on 2026-10-20 (`runs/prompt_a_…jsonl`), with today's code including
  retries. It cost $0.457, inside the $5 drafting cap; the ledger stands at $1.10.
- **Graded by** `grade.py`, which calls the functions in `tests/test_eval.py` and records every result instead of
  stopping at the first failure. Both runs were graded with the same harness, after the two harness fixes below.

## Results

| Measure | Earlier prompt | Prompt A |
|---|---|---|
| Rules saved (all districts) | 152 | **194** |
| Units fully accepted (vs. keeping a partial answer) | 7 of 9 | **9 of 9** |
| Units accepted on the first try | 4 of 9 | **7 of 9** |
| AI calls (incl. retries) / cost | 17 / $0.549 | **12 / $0.457** |
| R-1b answer key: worked examples that agree | 19 of 27 | **28 of 30** |
| Architects' 106 Ithaca Rd spreadsheet: rows that agree | 9 of 10 drafted (parking not drafted) | **11 of 11** |
| R-1B chart values enforced exactly (pass at the value, fail just past it) | 11 of 11 | **15 of 15** |
| Inspector: every drafted rulebook passes | yes | yes |
| A district citing another district's cell | 0 | 0 |
| R-1b hand rules no drafted rule covers | parking (one-family, other uses) | parking for other uses |

**Prompt A is kept.** It matches or beats the earlier prompt on every measure. It never gives a false pass.

The "for a person" list grew from 63 to 72 entries. These are not failures. When a template fits only one
district's cell, every other district is listed for a person. For example, RU's rear-yard rule uses footnote 17,
so the other 8 districts appear on the list for that template, and they get their own template with footnote
16. The cells no template covers are the same kinds as before: R-3aa's "3/2" stories, R-2c's multi-number side
yards, and the "-" dormitory cells.

## Every R-1b difference, judged

Earlier prompt (8 differences):
- **Front and side yards (4 examples): the drafted rule is wrong in form, though the number is right.** It
  applies only when `lot_area > 0`, a placeholder test, so it can't be decided without the lot area. Prompt A's
  "never a placeholder test" fixes this.
- **Height (3 examples): the drafted rules are incomplete.** The chart's 35 ft limit was refused, because the
  draft folded §325-16C's 10% bonus into the chart rule and policy B doesn't trust that 0.1 there. Only the bonus
  rules remained, so height came out "needs review" (106 Ithaca Rd too). Prompt A fixes this by drafting each
  text's own rule.
- **Stories (1 example): no real difference** (see below).

Prompt A (2 differences):
- **Stories, `stories = 3` with no height given: no real difference.** The hand rule quotes §325-16C(2)
  ("the number of stories permitted may not be exceeded"), and so does the drafted 325-16C rule. That rule applies
  only above 35 ft, and the hand example gives no height, so the result is "needs review". Height is always
  measured in a real check.
- **Height 37 ft with every yard 2 ft larger: the drafted rules say FAIL, while the law, and the hand key, say
  PASS.** The chart's "height ≤ 35 ft" and §325-16C's "up to 10% more if every yard grows 1 ft per extra foot"
  are drafted as separate rules, and every rule must pass, so the exception can't relax the chart limit. This is
  the cautious direction (a false FAIL, never a false pass). Prompt A follows its instructions correctly here.
  The cause is that the rule format has no way to say one rule relaxes another. **This needs a decision from Ben**
  before the checker is built: a "relaxes" link between rules, or one combined rule drafted from the exception.

## Two fixes to the grading harness (`tests/test_eval.py`, applied to both runs)

1. **Answer-key examples are judged as R-1b lots.** The spreadsheet comparison already said the lot is in R-1b,
   but the worked-example comparison didn't. A drafted rule that names a district (`district != "RU"`) therefore
   came out "needs review" for a missing district, which the checker always knows. Pinned by
   `test_an_answer_key_example_is_judged_as_an_r1b_lot`.
2. **A rule drafted from a law piece is about what it quotes, not about the chart cells it reads.** The answer key
   follows this convention for its own rules. Without it, §325-16C's "front yard grows with extra height" was
   graded as a front-yard rule (and its 25 ft input as a front-yard limit), which mixed a height example into the
   front-yard comparison. Pinned by `test_a_law_pieces_rule_doesnt_cover_the_chart_rows_it_only_reads`.

## To reproduce

From a scratch checkout of this branch (`git worktree add --detach <dir> HEAD`), with `PYTHONPATH` set to its
`packages/*`:
- **Baseline:** run `python replay.py runs/baseline_…jsonl`, then `python grade.py baseline_grade.json`.
- **Prompt A:** run `python -m rule_drafting draft --only <the 10 units> --yes` (needs a key and costs money), then
  `python grade.py prompt_a_grade.json`.
