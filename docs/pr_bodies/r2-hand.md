## What this PR does

Gordium can check a design only in zones whose rules it has. This PR adds the zoning rules for three more City of Ithaca residential districts, R-2a, R-2b and R-2c, written by hand from the City's own documents. They do two jobs: they are an **answer key** for grading the AI-drafted rules for these zones, and, once this PR is merged, the start box offers R-2a, R-2b and R-2c to architects like R-1a and R-3a (they are hand-written and were reviewed over 7 rounds). They are not in the current demo, because the demo doesn't include this branch.

## Words used below

- **Rulebook:** one file per zoning district listing every limit (lot size, height, yards…) as a formula code can check, each with the City's exact words. Example: `R-2c.yaml`.
- **Answer key:** a rulebook written by hand, without looking at anything the AI drafted, so the AI's work can be graded against it.
- **Chart:** the City's District Regulations Chart (April 2026). Page 2 lists the uses allowed in each district; page 3 the numbers; page 14 parking.
- **Note (chart note):** a numbered footnote on the chart that changes a number. Example: R-2c's note 5 says the lot size grows with the number of occupants.
- **Occupant:** for R-2c only, the code (§325-3B) counts every person with the right to occupy a unit (a lessee, someone paying rent), whether they live there yet or not.
- **Stated fact:** something the Rhino model can't show, which the architect types in (bedrooms, dwelling units, occupants). Until it is entered, a row that needs it says "needs review", never "complies".
- **Reading:** one way of understanding unclear words in the law. Where the law can be read more than one way, Gordium checks every reading: **complies** only if every reading passes, **does not comply** only if every reading fails, otherwise **needs review**.
- **Open question:** a place where the law reads more than one way and research didn't settle it. It goes to the architects (or the City) with the evidence.
- **Flag:** a rule Gordium can't decide yet; it always says "needs review", so a person checks it.
- **False pass:** Gordium saying "complies" when the law says otherwise. The one thing Gordium must never do.
- **Generative test:** a test that makes thousands of random designs and checks the rule's answer for each against an answer worked out a different way.
- **Revert check:** proving a test is real: undo the fix, and the test must fail.

## What we built

1. **R-2a rulebook** (21 rules, 98 worked examples). Two-family district with R-1's yards: 5,000 sf lots for houses (6,000 sf other uses), 45 ft wide (50 ft), 30% coverage, 25 ft front yard, 10 ft side yards on both sides, rear 25% of the lot depth.
2. **R-2b rulebook** (21 rules, 99 examples). Smaller lots: 3,000 sf (4,000 sf other uses), 35 ft wide (40 ft), 35% coverage, 10 ft front yard, side yards 10 ft on one side and 5 ft on the other.
3. **R-2c rulebook** (26 rules, 229 examples), the hardest column on the chart:
   - lot size grows with the occupants (notes 4, 5, 6): a detached house 2,500 sf for the first occupant + 500 sf for each more; semi-detached and two-family 2,000 sf for the first occupant in each unit + 400 sf for each more; attached (row) houses 1,500 sf per unit + 300 sf for each more, more past five in a unit;
   - coverage 35%, 40% or 50% depending on the house type (note 12); side yards by house type (notes 14, 15), including 0 ft at a semi-detached house's party wall;
   - zero-lot-line and attached houses need a special permit.
4. **New facts the architect can enter** (each asked by the panel's "Enter …" button, only on a row that needs it): occupants; the most occupants in any one unit (optional: it settles a two-family or semi-detached lot exactly); the units in the whole attached building. A "Lot facts disagree" row appears when two counts contradict each other.
5. **The panel shows the required value** for limits that depend on the house type (R-2c's side yards and coverage), which used to show "—".
6. **Three open questions for the architects** (§5.7 to §5.9 on `docs/questions_for_architects.md`), and three law-wide ones carried into these zones.
7. **Offered in the start box:** like every hand-written rulebook, R-2a, R-2b and R-2c appear in the start box's zone list once merged (QUICKSTART names them; a test checks the list).
8. **Tests that keep these rules honest:** the chart test now checks R-2a, R-2b and R-2c cell by cell (each of R-2c's stacked figures for its own house type); a generative test for R-2c's lot sizes; a hand table of 14 boundary cases from the law text.

Every rule cites the City's exact words (chart cells, chart lines, code quotes with page and line), as R-1b, R-1a and R-3a do. Written blind: nothing the AI drafted was opened while writing.

## One example, start to finish

A two-family house on a 40 × 100 ft lot (4,000 sf) in R-2c, two occupants.

1. **The law:** chart p.3, R-2c's two-family lot size is "2,000 sf [fn5]"; note 5: "For the first occupant in each dwelling unit; +400 sf for each additional occupant in each dwelling unit." Gordium reads the 2,000 sf as once per unit (a finding to confirm with the City), so two units need 2 × 2,000 = 4,000 sf to start.
2. **What the split changes:** one occupant in each unit needs 4,000 sf (no additional occupants). Both in one unit (the other empty) needs 4,000 + 400 = 4,400 sf.
3. **Without the split entered:** Gordium doesn't know which, so the row shows **needs review**, with an "Enter the most occupants in one unit" button.
4. **The architect enters "1"** (one in each unit): the row shows **complies** (4,000 sf ≥ 4,000 sf).
5. **Or enters "2"** (both in one unit): **does not comply** (4,000 sf < 4,400 sf).
6. **On a 30 × 100 ft lot (3,000 sf):** **does not comply** whatever the split, and no button is offered (nothing could change it).

## How we know it works

- **Chart test** (`test_r1b_matches_chart.py`, now for R-2a, R-2b, R-2c): each rule passes exactly at its district's chart value and fails just past it; every number in every cited cell decides something; every numbered cell is cited; the use rule matches the page-2 marks.
- **Generative readings test** (`test_r2c_lot_size_readings.py`): for R-2c's semi-detached, two-family and attached lot sizes, it works out every reading on its own, unit by unit, straight from notes 5 and 6 (every split of the occupants, each row house's own lot or the whole building's, note 6's 500 sf instead of or on top of the 300 sf), over 3,000 random designs per row, and checks the rule's answer is the every-reading combination. All three answers (complies, does not comply, needs review) occur.
- **Law table:** 14 boundary cases worked by hand from the law text (not from the rule or the test's model). Both the rule and the generative model must match it, so a mistake they share is still caught.
- **Hand-worked examples:** every rule has examples just inside and just outside each limit (426 in all), checked by the rule validator.
- **Revert checks:** every fix from review is pinned by a test that fails when the fix is undone (listed below); 13 wrong numbers put into the files by hand were each caught.
- **Grade of the AI drafts against these keys** (the drafting job's grader, `drafting-stage1` 9ae22e7, after its re-draft):

  | Key | Examples | Agree | Disagree | Not drafted | False passes |
  |---|---|---|---|---|---|
  | R-2a | 98 | 73 | 11 | 14 | 0 |
  | R-2b | 99 | 73 | 12 | 14 | 0 |
  | R-2c | 227 | 78 | 31 | 118 | 0 |

  No false passes in the R-2 zones. Most of R-2c's "not drafted" examples are the occupant-based lot sizes and the use-dependent side yards, which the AI drafts leave out; the panel lists those cells as "not checked" (verified by running the checker on an R-2c design with the drafts switched on).

## Open questions for the architects

- **§5.7 Note 6 past five occupants in a unit:** does each occupant past five add 500 sf instead of the 300 sf, or on top of it? The note lists both with "+" and never says "instead"; nothing else in the code says. Gordium complies only under the stricter reading.
- **§5.8 The narrow side yard of a semi-detached or attached building on one lot:** notes 14 and 15 give 10 ft on unattached sides and 0 ft on a semi-detached house's attached side, but no figure for the second side of a semi-detached building standing whole on one lot, or for an attached building's sides. Readings: 10 ft, 5 ft or 0 ft. Gordium complies only at 10 ft.
- **§5.9 Whose lot an attached house's figures are for:** each row house's own lot, or the whole building's? The code leans to the building's lot (the 50 ft lot width a single row-house lot can't meet; note 15 gives attached houses no 0 ft side; §325-8B(1); the Collegetown districts that allow row houses on lot lines say so, §325-45.2), but note 14's "unattached sides only" points the other way. No City record found. Gordium checks both.

Carried from R-1b into these zones (already on the page): parapets above the height bonus (§4.5), lot depth on odd lots (§1.2), lot area without a survey (§1.3). The page now lists 41 questions (26 different).

## Not in this PR

- As for R-1b: parapets above the height limit, accessory uses, accessory dwelling units, occupancy limits (including R-2c's habitable-space-per-person table), the South Hill overlay, cluster subdivisions, loading for nonresidential uses.
- Corner lots: one side yard is left and the City checks it against the smaller figure; Gordium asks the larger one (stricter, never a false pass) until a corner-lot measure exists (as in R-3a).

## Review rounds

- **Round 1:** 4 found, all fixed. A semi-detached or attached lot with 0 units entered needed 0 sf and complied; lot sizes assumed every unit has at least one occupant (now: complies only with every occupant in one unit); the panel showed "—" as the required side yard and coverage; "dwelling units" had two meanings (now: this lot's units).
- **Coordinator follow-up:** an ordinary two-family house on 4,000 sf needed review; added the optional "most occupants in one unit", which settles it exactly.
- **Round 2:** 3 found. A row house on its own lot was held to three units (the 3-to-6 count is per building: now its own rule on its own fact); the optional fact was asked, and given as the reason, where it couldn't change the row; the Enter prompt accepted 0 for a fact whose minimum is 1, and the refusal crashed the button (now one minimum per fact, and a message instead of a crash).
- **Round 3:** 2 found. Per-lot vs whole-building was an interpretation recorded only in notes (now researched and an open question with both readings, §5.9); question 5.7 and a test description were stale.
- **Round 4:** 1 serious. The building's-lot reading used a floor of three units, not the building's stated units, so one unit of a six-unit building complied on 4,500 sf. Method changed: each reading written out separately and checked by the generative test. Also cited §325-45.2 with its page.
- **Round 5:** 1 serious. "At least as many units as the building" let 4 units pass beside a stated 3-unit building (now: exactly the building's units; more gives its own reason and a "Lot facts disagree" row). Added the 14-row law table as a third check, so a mistake shared by the rule and the test model is caught.
- **Round 6:** the rule verified by an independent exhaustive sweep and all 14 law-table rows checked by hand. One small fix: the "Lot facts disagree" row now offers a working "Enter …" button.
- **Round 7:** confirmation round: clean.
- **Merge of answer-keys (c342d10):** both branches' stated facts kept (R-2c's occupants, split and building units; #20's "abuts R-1 land" and the stories count); review round on the merge: round 8 (pending at hand-off; the PR opens after it is clean).

## Test Plan

- [x] `full_suite.py` on 1b15c9f (after merging answer-keys c342d10; pytest and every CI step): 1606 passed, 9 skipped, 9 xfailed; CI steps: 7 run, all passed (document_extraction --check, rule_format, section_labeling coverage --check, rule_export --check, model_measurement --check, project_report --check)
- [x] `python -m rule_format`: 9 files checked, 0 with problems
- [x] Chart test for R-2a, R-2b, R-2c: every limit exact, every cited number decides something
- [x] Generative readings test: 3,000 random designs per R-2c lot-size row, every one equal to the every-reading combination
- [x] Law table: 14 boundary cases from the law text, matched by both the rule and the model
- [x] Revert checks: each review fix's pin fails with the fix undone (rounds 1 to 6); the law table fails with the model's round-5 mistake put back
- [x] Grade of the AI drafts: 0 false passes in R-2a, R-2b, R-2c
- [x] Independence: nothing in `5_zoning_rules/drafted/` or the drafting runs was read while writing; no AI calls
- [ ] GitHub checks green (Actions billing: CI runs locally until fixed; Windows can't be checked locally)
- [x] Review rounds until one comes back clean (round 7)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01NL5c31gf3hkiiPUoGve2zh
