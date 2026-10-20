# Eval 2026-10-20: drafting prompt A vs the earlier prompt

**Question:** does the rewritten drafting prompt ("prompt A") draft better rules than the earlier one? The rule
for keeping it: at least as good on every measure.

**Prompt A** (in `rule_drafting/drafter.py`, `FORMAT`) gets what the labeling guide got in its rewrite:
- **Who the drafter is:** a senior zoning plan examiner and licensed architect.
- **Why it matters:** Gordium checks designs with plain code, a result must never be a false pass, every number
  must be traceable, and code checks everything the drafter writes.
- **The steps, in order.**

It also states the rules the code enforces today:
- **Policy B:** a typed number is trusted only from a sentence of the paragraph being drafted, a footnote marked
  on the slot's own cell, or that slot's own row label.
- **No placeholder tests:** `applies_when` is left empty rather than filled with a test like `true` or
  `lot_area > 0`.
- **Each text's own rule:** the chart's height row is drafted as a plain limit, and §325-16C's extra height is
  drafted from §325-16C.
- **Every yard named:** when a sentence names several yards, each one gets a rule.
- **Examples cover every branch and tier,** for instance parking above 5 bedrooms.
- **Only `review_when` (or a flag) makes a result "needs review".** An open question doesn't.

**Shared guide:** the drafting guide that is sent with the prompt now marks where drafting by hand differs from
the drafting script, so the two never contradict each other (review round 12).

## How it was run

**The test set.** The same 10 units every time:
- chart page 2 uses, built by code;
- chart page 3 lot size, lot width, building height, lot coverage and yards;
- chart page 14 residential parking;
- law pieces 325-16C, 325-18A and 325-19C.

Every run used the same model (`claude-sonnet-5-5`, effort medium) and the same settings.

**The three runs:**

| Run | Prompt | Record |
|---|---|---|
| Baseline | the earlier prompt, at commit 6f3bdd8, run 2026-10-19 | `runs/baseline_…jsonl` |
| Prompt A, first version | commit 6592c80 | `runs/prompt_a_first_…jsonl` |
| Prompt A, final | commit 01e6682, after review round 12's fixes | `runs/prompt_a_final_…jsonl` |

**How the baseline was replayed.** Its real answers went through today's checks (`replay.py`). Each unit's
recorded attempts were judged in order, the way `draft_unit` judges them. No new calls were made, so the
baseline had no new retries. Its answers predate the `numbers` field, so each typed number was given every
binding policy B could trust, which is the best case for the baseline.

**How the prompt A runs were made.** They are new runs with today's code, retries included. They cost $0.457 and
$0.499, both inside the $5 drafting cap. The drafting ledger now stands at $1.59.

**How everything was graded.** `grade.py` calls the harness's own functions (`tests/test_eval.py`) and records
every result instead of stopping at the first failure. All three runs were graded with the same final harness and
the same answer key.

## Results

| Measure | Earlier prompt | Prompt A, first | **Prompt A, final** |
|---|---|---|---|
| Rules saved (all districts) | 152 | 194 | **202** |
| Units fully accepted (vs. keeping a partial answer) | 7 of 9 | 9 of 9 | **9 of 9** |
| Units accepted on the first try | 4 of 9 | 7 of 9 | **6 of 9** |
| AI calls (incl. retries) / cost | 17 / $0.549 | 12 / $0.457 | **13 / $0.499** |
| R-1b answer key: worked examples that agree | 19 of 29 | 30 of 32 | **29 of 32** |
| Architects' 106 Ithaca Rd spreadsheet: rows that agree | 9 (parking not drafted) | 11 of 11 | **10 of 11** |
| R-1B chart rows enforced exactly (pass at the value, fail just past it) | 10 of 10 | 14 of 14 | **14 of 14** |
| A chart number cited but unused, or wrong | 0 | 0 | **0** |
| Law exceptions judged alone that pass what the answer key fails | 0 | **1** | **0** |
| Inspector: every drafted rulebook passes / a district citing another's cell | yes / 0 | yes / 0 | **yes / 0** |
| R-1b hand rules no drafted rule covers | parking (both) | parking for other uses | **parking for other uses** |

**Prompt A, final, is kept.** It matches or beats the earlier prompt on every measure.

**The first version would not have been kept.** Its §325-16C rules enlarged the front and side yards for extra
height but forgot the rear yard. The chart's separate 35 ft limit hides that today, but once an exception can
relax a limit it would be a false pass. The baseline had drafted all the yards as one "needs review" flag. Review
round 12 found this. The final prompt says every yard a sentence names gets a rule, and the final run handles the
rear yard (as a flag).

**The "for a person" list (63, 72, 73 entries) is not a list of failures.** A template that fits only some
districts' cells lists every other district for a person. For example, RU's rear-yard rule uses footnote 17, so
the other 8 districts appear on its list, and they get their own template with footnote 16. The cells no template
covers are the same kinds in every run:
- R-3aa's "3/2" stories;
- R-2c's multi-number side yards;
- the "-" dormitory cells.

**Two runs is a small sample, and answers vary from run to run** (the model can't be pinned to identical output).
The first and final runs differ partly by chance, not only because of the prompt change.

## Every R-1b difference in the final run, judged

1. **Stories, `stories = 3` with no height given. Same in substance.** The hand rule quotes §325-16C(2) ("the
   number of stories permitted may not be exceeded"). So does the drafted 325-16C stories rule, which applies only
   above 35 ft. The hand example gives no height, so the result is "needs review". A real check always has the
   height.
2. **Height 35 ft (and the architects' 106 Ithaca Rd height row). Drafted rule incomplete: "needs review" where
   the answer is PASS.** There is one cause. The drafter made §325-16C's rear-yard increase a flag with no
   condition, so it applies to every building, even one at or under 35 ft. It should apply only above the limit.
   Its open question explains the flag: how the required rear yard is computed before the extra height is added.
   The grade's note that the stories rule "needs stories" only lists a name in that rule's formula. That rule
   applies only above 35 ft, so it doesn't affect this example. This is cautious, not wrong: never a false pass.
3. **Height 37 ft with every yard 2 ft larger. The drafted rules say FAIL; the law and the hand key say PASS.**
   The chart's "height ≤ 35 ft" and §325-16C's "up to 10% more if every yard grows 1 ft per extra foot" are
   separate rules. Every rule must pass, so the exception can't relax the limit. This is the cautious direction (a
   false FAIL), and the drafter followed its instructions. The cause is that the rule format has no way to say
   one rule relaxes another. **Ben decides** how: a "relaxes" link between rules, or one combined rule drafted from
   the exception. The new check that judges exceptions alone (row above) keeps that future change from turning an
   incomplete exception into a false pass, for each yard §325-16C(1) names. The answer key has one 37 ft example
   per yard with only that yard not enlarged: the front yard; the smaller side yard (10 ft, while the larger is at
   its enlarged 12 ft; the larger can never be smaller than the smaller, so this one example covers both sides);
   and the rear yard.

**Earlier prompt's differences, for comparison:**
- **Front and side yards (4 examples):** the rules applied only when `lot_area > 0`, a placeholder test, so they
  couldn't be decided without the lot area.
- **Height (5 examples):** the chart's 35 ft limit was refused, because the draft folded §325-16C's 10% into it
  and policy B doesn't trust that 0.1 there. Only the bonus rules and a yards flag remained, so the result was
  "needs review".
- **Stories (1 example):** as in item 1 above.

**325-18A (porches and decks count as part of the building):**
- The earlier prompt and the final prompt A drafted a flag.
- The first prompt A drafted no rule, with the reason that the city's definitions already count these structures
  in yards and coverage. That makes it a measurement matter (`yard_projections` in the definitions), and the line
  was listed for a person.
- All three are safe.

## Questions for the architects found by this eval

- **Which side yard does each side column bind?** The chart has two side-yard columns. Column 12 ("one side yard
  will be at least …") and Column 13 ("One side yard shall be at least …") don't say which yard is which. The final
  draft holds the larger yard to Column 12 and the smaller to Column 13. That reading fits R-2c, where Column 12
  (10/15 ft) is larger than Column 13 (0/5/10 ft). The chart reader's own test assumes the opposite. For R-1B both
  are 10 ft, so the harness accepts either reading there (`readings` in `tests/test_eval.py`).

## Changes to the grading harness (`tests/test_eval.py`, applied to every run)

Each change is pinned by a test that fails if the change is undone.
1. **Answer-key examples are judged as R-1b lots,** as the spreadsheet comparison already did. Pinned by
   `test_an_answer_key_example_is_judged_as_an_r1b_lot`.
2. **A rule drafted from a law piece is graded on what it quotes, not on the chart cells it reads as inputs.**
   This is the answer key's own convention. Pinned by `test_a_law_pieces_rule_doesnt_cover_the_chart_rows_it_only_reads`.
   The exact-value test also skips those rules, because their cells are inputs, not their limit. The idle-number
   check still covers them: `test_a_law_pieces_rule_that_ignores_a_cell_it_cites_is_caught`.
3. **Law exceptions judged alone must never pass what the answer key fails** (`exception_false_passes`). The
   answer key gained two 37 ft examples, one with only the smaller side yard not enlarged (10 ft; the larger is at
   its enlarged 12 ft, and since the larger side yard is never smaller than the smaller, this covers both sides)
   and one with only the rear yard not enlarged (the front-yard example was already there). Pinned by `test_an_exception_that_forgets_any_yard_is_caught`,
   which leaves each yard out in turn.
4. **Either reading of the side-yard columns counts where R-1B can't tell them apart.** This applies only while
   R-1B's two side minimums are equal. The two columns are judged as a pair: one must bind the smaller side yard
   and the other the larger, never both the same yard. A wrong number still shows. Pinned by
   `test_either_reading_of_the_side_yard_columns_counts_and_a_wrong_number_still_shows`.

## Next prompt improvements (not tested yet)

- **A flag needs its condition too.** §325-16C's rear-yard flag, and the 325-18A and 325-19C flags, have no
  `applies_when`, so they make every design "needs review". For corner lots, a `corner_lot` measure has to be
  proposed first.

## To reproduce

Work from a scratch checkout of the matching commit (`git worktree add --detach <dir> <commit>`), with
`PYTHONPATH` set to its `packages/*`.

- **The baseline:** run `python replay.py runs/baseline_…jsonl`, then `python grade.py baseline_grade.json`.
- **A prompt A run:** run `python -m rule_drafting draft --only <the 10 units> --yes`, then
  `python grade.py <file>`. This needs an API key and costs money.
