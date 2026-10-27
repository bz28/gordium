# Methods

**Purpose:** every technique Gordium uses to turn the law into checkable rules and check designs: what it does, why it was chosen, what else was considered, its weak spots and how it is tested.\
**For:** engineers and reviewers who want to evaluate or challenge a choice.\
**Kept current by:** the engineer who adds or changes a technique, in that same PR.

Every technique Gordium uses to turn a city's zoning documents into checkable rules: what it does, how, why it was chosen, what else was considered, its known weaknesses, how it's tested, and ideas to improve it. Written so the choices can be evaluated and challenged later. Numbers are from the City of Ithaca run (2026-10).

Who does each step: **code** (plain, deterministic, no AI), **AI** (a recorded API call; drafts only), **people** (reviewers, architects).

---

## 1. Source documents and fingerprints (code)

- **What:** each official PDF is kept unedited in `1_source_documents/` and listed in `sources.yaml` with its link, download date and SHA-256 fingerprint. A document that can't be read reliably yet is marked `quotable: false` with the reason.
- **Why:** a rule is only as trustworthy as the exact document it cites. The fingerprint proves which version a rule came from; any change to the PDF invalidates everything quoted from it.
- **Alternatives considered:** storing only links (the city can change the file silently); a database (harder to review and version than files in git).
- **Weaknesses:** downloading is manual. The zoning maps and the Southside ordinance are marked not quotable (scrambled map labels, two-column pages).
- **Tested by:** every check re-computes each fingerprint; a missing, changed or duplicate document, or a typo in the list, is reported and that document's text isn't trusted.
- **Improve:** automate downloads with change detection; column-aware reading for two-column pages.

## 2. PDF to text (code, PR 3)

- **What:** reads every character with its position (pdfplumber/pdfminer, pinned versions), removes fake-bold duplicates, drops text tilted more than 5°, groups characters into numbered lines, and seals small raised footnote numbers as `[fn11]`.
- **Why:** a PDF holds positioned letters, not sentences. Fixed rules with fixed thresholds give the same text every time, which line-cited quotes depend on. Not AI: an AI could silently "fix" or paraphrase text.
- **Thresholds:** duplicate within 1 pt; line grouping within 3 pt; footnote = smaller than 80% of the page's most common size and raised at least 20% of it.
- **Weaknesses:** two-column layouts mix lines; scanned PDFs (images) have no text (no OCR); thresholds are tuned on Ithaca's documents.
- **Tested by:** CI re-reads every PDF and requires byte-identical output; tests on real sentences, footnotes and tilted labels.
- **Improve:** column detection; OCR for scanned documents; per-document threshold checks.

## 3. Quotes and line citations (code, PR 1)

- **What:** every source cites `file, page, lines: [first, last], quote`. Quote and page are split into tokens (whole words, whole numbers like `2.5` or `3/2`, footnote tokens). The quote must be an unbroken token run that starts on the first cited line, ends on the last, and occurs only once on the page.
- **Why:** whole tokens stop accidental matches ("5 ft" inside "25 ft"); exact lines plus uniqueness make each citation point at one place. An earlier page-wide search needed ever more special cases; recording the position was the root fix.
- **Weaknesses:** a line pins a chart row, not its column (closed by chart cells, §4); a quote must be copied exactly.
- **Tested by:** tests on numbers inside numbers, fractions, decimals, footnotes, district names, wrong lines, repeated quotes.
- **Improve:** cite chart cells directly in rules (PR 8).

## 4. Chart tables to cells (code, PR 6)

The chart reader is built on its own branch (PR 6). Rule drafting (PR 8, also a side branch) builds on it; both join the main line when they are merged. On a branch without it, the tests and CI step named here don't run.

- **What:** reads the chart's drawn rectangles and borders to find rows, district columns and merged cells, then places each word in the cell that contains it. Output: one record per cell (page, section, row, district, value, lines, position). 683 cells on pages 2, 3, 14.
- **Why:** plain text lines lose columns, so "25 ft" can't be tied to R-1B. Drawn boxes are what the PDF actually says about the table.
- **Never guessing:** any uncertainty (a word across a cell edge, a stripe across the row, a split label area, a district without a cell, a row that looks like two, a repeated label under one section) makes the whole row unresolved; an unreadable header makes the page unresolved; rows after an unreadable row get no section.
- **Weaknesses:** the district-name pattern and layout rules are Ithaca's residential charts; another city needs its own checks.
- **Tested by:** every R-1B number matches the R-1b rules (exact pass/fail boundary); every district cross-checked against the plain text (56 rows agree, 0 disagree); the 6 wrapped rows hand-read in every column; 7 planted errors caught; CI reproduces the cells file.
- **Improve:** generalize to other cities' chart layouts, each with the same two-way cross-check.

## 5. Cutting the law into pieces (code, PR 7)

- **What:** splits Chapter 325 at its own headings into 626 pieces (sections, lettered subsections, one per defined term, editor's notes, front matter). Page furniture (repeated titles, headers, footers) is set aside.
- **Why:** a small piece is one idea, can be judged alone and cited exactly. The law's own numbering is the natural unit.
- **Weaknesses:** heading patterns are tuned to Ithaca's code format.
- **Tested by:** every one of 6,027 lines is in exactly one piece or is furniture; the cut matches the law's table of contents; CI reproduces it.

## 6. Labeling pieces (AI: Haiku; code checks; PR 7)

- **What:** one recorded AI call per piece labels it rule, flag, reference or not_for_checking. Instructions: `regulations/document_extraction_guide/labeling_guide.md` (role, purpose, process, rules). The answer lists the requirements first, as line numbers (L3–L5), then the label, topic, reason and one exact quote. Code takes the exact words from the cited lines.
- **Why this model:** sorting is simple reading; Haiku labeled all 626 for $0.085. Everything it says is checked by code and reviewed.
- **Why requirements first, by line number:** labeling first and justifying after let the model explain limits away ("the six-unit maximum is descriptive"). Listing requirements first, with code rejecting a label that disagrees with them, removes that. Line numbers instead of copied text remove copying errors (18 of 100 answers failed when asked to copy).
- **Fail-safe rules:** when unsure between not_for_checking and rule/flag, choose rule/flag; procedures are not_for_checking even with "shall".
- **Not repeatable bit for bit:** current models don't accept temperature 0. Every call is recorded and every label is rebuilt from the records by code; once approval is switched on (deferred for now), an architect's approval would freeze a label.
- **The instructions have changed since the recorded runs:** the run records hold one fingerprint per version of the guide used during the 2026-10-19 runs. After the last recorded call, the guide changed twice: rule 3 was rewritten into the category-vs-limit principle below (a real change to how definitions with numbers are labeled, so a re-run could label the kitchen or adult day-care home definitions differently), and later its approval sentences were reworded. No recorded run used the current guide. The kitchen, adult day-care home and bed-and-breakfast inn labels (reference) are Haiku's answers from the first full run, which used an earlier guide; the review's corrections to them were undone under the category-vs-limit principle, and the 2026-10-20 research read each as a category (a finding recorded with the label, from the code's own structure). A re-run would send, and record, the current guide.
- **Cost control:** a shared ledger with a hard cap ($1), worst case reserved before each call.
- **Tested by (evals):**
  - First prompt, 28 pieces with an answer key: 25/28, then 26/28 after guide fixes.
  - Independent AI review (Claude) of all 399 rule/flag/reference labels: 354 judged correct (89%); 4 flagged as dangerous (a limit hidden in a definition), 41 minor. Under the category-vs-limit principle adopted afterwards, two of the four (kitchen, bed-and-breakfast inn) are category definitions, so they are open questions for the architects rather than clear misses.
  - Second review (Claude) of all 244 not_for_checking labels, looking only for the dangerous miss: a piece that constrains a design but would never be checked. 239 confirmed (325-27I among them, after a closer look); 5 changed (325-15F gas station site plan review and 325-29.6D collocation on a site with unpermitted equipment to flag; 325-29.17A-C, which say how the wireless requirements apply to a collocation, to reference); 0 open questions. 325-27I (who may operate a short-term rental) stays not_for_checking: it limits the operator, not the building. None of the 4 borderline pieces concerns house design.
  - Improved prompt (role, purpose, process, line citations) on the 100 pieces with known answers (chosen because the first prompt failed them): 70/100 against the key at the time. Under the later category-vs-limit principle the kitchen answer (reference) counts as right (71/100); dwelling unit (reference, key rule) is an open question for the architects. The rest of the misses are procedures over-labeled as rules (safe direction).
- **The committed labels:** Haiku's answers plus 70 corrections made by an AI review (Claude, reading every rule, flag and reference label against the text) and 5 from the second review of every not_for_checking label, each recorded in `revised: {from, by, date, why}` with the reason rewritten for the new label. They are still drafts (architect approval is deferred for now, decided 2026-10-19). (Corrections to kitchen, adult day-care home and bed-and-breakfast inn were undone under the principle below; the 2026-10-20 research read all five numbered definitions as categories, and dwelling unit and rooming unit stay labeled rule, which gives the same result: findings recorded with each label, §17.)
- **Category vs limit:** a definition whose number sorts things into categories (a kitchen is 60 sq ft or more; an adult day-care home serves up to six adults) is reference: rules use it to classify. A definition that caps what a design may do ("a maximum of six units may be attached", "not more than two unrelated individuals is permitted") is a rule. The test: does it forbid or cap something, or only say what to call it?
- **Weaknesses:** definitions with embedded limits remain the hardest case; procedures get over-labeled as rules.
- **Improve:** a second, independent AI pass on every non-rule piece asking only "does this set a requirement?"; few-shot examples from another city's code (never from the answer key); compare models on the known-answer set.

## 7. Safety nets on labels (code)

- **Requirement-word net:** every piece labeled reference whose text uses requirement wording (shall not, must, maximum, minimum, not less than, "No … shall", in conformity, …) goes on the review list, whatever the AI said.
- **Review list:** every not_for_checking label, every reference with requirement words, every label with an open question for the architects, every piece a rule or definition cites.
- **Provenance (checked by code in CI):** every AI-drafted label must be exactly what an answer in the run records produces, rebuilt with the labeler's own code (same page, lines and words), or say how it differs: a label change is recorded as `revised: {from, by, date, why}`, a change to the sources as `{field: sources, by, date, why}` (which must keep what the AI produced). `python -m section_labeling coverage --check` fails on any unexplained difference.
- **Known limit:** some rule labels' quotes are a lead-in sentence ("the following criteria must be present") rather than the requirement itself. Code doesn't judge quote quality: it checks only that a quote is the city's exact words inside the piece and matches the recorded answer. Whether a quote justifies the label is for whoever reads the rules spreadsheet (architect review is deferred). Drafting reads the whole piece either way.
- **What a label's sources are for:** they justify the label, nothing more. Finding every requirement in a piece is the drafting step's job, and it reads the whole piece. Two attempts to improve sources by code were undone: adding a "requirement line" by keyword matching (it picked headings and fragments), and a check rejecting heading-only quotes (code can't tell a caption from an uncaptioned first sentence). One label that quoted only its caption (§325-45.5A) cites the whole provision, with a sources revision.
- **Coverage report:** every line of the law, its piece and its label.
- **Weaknesses:** the word net only catches the phrasings it knows. It started with exact phrases and missed "a maximum of", "No … shall" and "less than"; it now matches patterns (any "more/less/fewer/greater than", "exceed/exceeding", "No" plus up to six words then "shall", "limited to" but not "not limited to"). It also flags category definitions (false alarms, by design). It's a backstop, not the main defense.
- **Improve:** the second AI pass above; feed the net's misses back into the word list after each review.

## 8. Rule format and the formula language (code, PR 1)

- **What:** each rule has a title, the city's exact quotes, `applies_when`, `check` (a yes/no formula), `review_when`, worked examples, open questions, answers, and approval fields. Formulas are ordinary math read by Python's parser and checked against an allowed list (comparisons, and/or/not, min/max, `use in [...]`, `a if b else c`) and a fixed list of measurement names with units.
- **Why:** readable by architects, nothing hidden (no code execution), exact and repeatable. No plain-English retelling: retellings kept dropping or adding words; the quotes are the words and the examples show the meaning.
- **Fail closed:** missing, non-numeric, negative or impossible values give "needs review", never "pass".
- **Alternatives considered:** free-form code (unsafe, unreadable), a custom rule language (more to build and learn), JSON logic (hard to read).
- **Yes/no measurements:** a measure with unit `yes_no` (e.g. "the accessory dwelling unit has a separate entrance") is a test on its own in a formula (PR 8). A measure a draft needs that isn't listed yet is proposed for an engineer and blocks approval until added.

## 9. The inspector (code, PR 1 onward)

- **What:** checks every rule, definition and label: sources (listed, unchanged, quotable, exact and unique on cited lines), formula (allowed, true/false, known names), examples (a pass and a fail, each giving its stated result), a use decided by a rule cites its chart row, approvals (a listed architect, not the drafter, no open questions, nothing changed since: an approval fingerprint covers content, id and the cited documents).
- **Weakness:** proves a rule is traceable and well formed, not that it means the right thing. Meaning comes from comparisons (§11) and architects.

## 10. Drafting rules (AI: Sonnet; code checks; PR 8, built, 10-unit test graded, full run not done)

- **What:** `packages/rule_drafting` drafts rules for every residential district. A unit is one chart section (e.g. page 3 "Yard Dimensions"), one piece of the law labeled rule or flag, or the chart's page 2 use lists. One recorded AI call per unit; drafts go to `5_zoning_rules/drafted/<district>.yaml` and `general.yaml`, the script's records to `drafted/records/`.
- **Inputs:** for a law piece, its **whole text**: every line, numbered L1, L2, ... with page breaks marked (the labeler's numbering). A label's sources justify the label (newer labels also cite the requirement lines; older ones may cite only a heading or lead-in), so the drafter gets them only as **hints**: it drafts every requirement in the whole text, and any line the label cites that no drafted rule cites is listed for a person. Also the sections of the law it points to and the definitions it uses. For every unit, cached instructions: the drafting rules, the formula language, every measure, use and district, the chart's rows and the footnotes under each table.
- **Chart numbers are never typed:** the AI writes a template whose chart numbers are slots (`front_yard >= {front}`); code fills each slot from each district's own cell and cites that cell. A cell of another shape (another count of numbers, other footnotes, "-") is never filled: that district goes to a person. Every footnote on a filled cell must be quoted and applied. A chart quote must be a footnote under a table, never a table row. A number the AI types (not a slot) must be bound, in the answer's `numbers`, to one evidence item it names, and code checks that exact item holds the value. Code can check that evidence holds a number, never what the number is about (note 7's "1-3 units" and the parking row's "First three" look alike), so only evidence that belongs to the rule itself is trusted (Ben's decision, 2026-10-20): a footnote whose marker is on the slot's own cell ("50 ft [fn16]": note 16), that slot's own row label ("First three bed or sleeping rooms"), or a sentence of the paragraph being drafted. Anything else (a note on another cell, on the row label or on the section heading, or a sentence of another section of the law) is refused: the unit is retried and then listed for a person, so an untrusted number never reaches a rule. A trusted footnote or row label backs a number only where the number stands with that slot (in the same arithmetic or min/max, or in the condition that picks the slot's value), each place a number is typed checked on its own, and only where that slot occurrence itself decides something (changed alone, some worked example comes out differently), so `0 * {x}` or `min(3, {x})` can't smuggle in a cell's note. A flag has no check. A number that only labels or points ("(3)", "§ 325-20D(1)", "Column 12") doesn't count, and a percent counts only as its fraction (25% is 0.25). The grading tests give a drafted rule's declared new measures the value its own passing example gives them, and name, in the disagreement, every other input the hand example lacks (never filled from the draft), so a missing input never hides a disagreement.
- **The permitted uses** (chart p.2 marks •, SP, -) are built by plain code, not the AI; the notes on their rows and column headings (occupancy, the South Hill Overlay) are quoted and listed for a person, since no measure checks them. The accessory-use section is recorded as not drafted until a measure for accessory uses exists.
- **Nothing in a unit's input can vanish:** every district cell of a chart section that states something (anything but "-" or empty) must be cited by a saved rule or listed for a person, whatever the drafter answered (including "no rule here"); the law lines a label cites likewise; and a referenced section left out of the input for length is named to the drafter and listed for a person. Replaying prompt A's final run through this check (no API calls, `evals/2026-10-20_prompt_a/coverage_replay.json`) lists 22 cells its drafts had skipped: the lot sizes for attached and multiple-family dwellings in R-2C, R-3A, R-3AA, R-3B and RU (19) and dormitory parking in R-3A, R-3B and RU (3). Before the check they would have had no rule and no entry for a person.
- **Checks on every draft:** the inspector, including two checks added for this: every number in a formula is written in a cited quote or cell (the number trace), and a cited cell is the rule's own district's column. A rejected template is sent back with the reasons (up to 2 retries); then its unit keeps the templates that work and lists the rest for a person. A fact we don't measure yet is proposed (`records/proposed_measures.yaml`), never invented, and blocks approval until an engineer adds it.
- **The instructions (prompt A, 2026-10-20):** like the labeling guide, they say who the drafter is (a senior zoning plan examiner and licensed architect), why it matters (plain-code checking, never a false pass, every number traceable, code checks everything) and the steps in order, then today's rules: policy B for typed numbers; `applies_when` left empty rather than a placeholder test (`true`, `lot_area > 0`); only the text's own requirements (the chart's height is a plain limit, §325-16C's extra height is drafted from §325-16C); worked examples that cover every branch and tier.
- **Fairness:** the AI is never shown R-1b (the answer key), and the drafting rules use neutral examples, not R-1b's.
- **Cost and cap:** a 10-unit test batch costs about $0.46–0.55 (measured); the whole set (171 AI calls: 7 chart sections, 164 law pieces) has an upper bound of ~$14.60 (every answer at the full 8,192-token limit; real answers are far shorter). Hard cap $5 in its own ledger; a run whose estimate exceeds it is refused, so the full run waits for a measured average from the test batch.
- **Graded by** (`tests/test_eval.py`, once drafts exist): the hand R-1b's worked examples (judged as R-1b lots); each cited R-1B chart value enforced exactly and every cited chart number actually used; the architects' spreadsheet (11 rows); each district citing only its own cells; every unit producing rules, a reason or a person entry. A rule drafted from a law piece is graded on what it quotes, not on the chart cells it reads as inputs (the answer key's own convention).
- **Test batch, 10 units, Sonnet** (`packages/rule_drafting/evals/2026-10-20_prompt_a/`): the earlier prompt (its real answers replayed through today's checks) vs prompt A (a new run, $0.499): rules saved 152 → 202; units fully accepted 7 → 9 of 9; first-try acceptance 4 → 6 of 9; R-1b worked examples agreeing 19/29 → 29/32; the architects' spreadsheet 9 rows → 10 of 11; R-1B chart rows enforced exactly 10/10 → 14/14; law exceptions judged alone passing what the answer key fails 0 → 0; inspector clean in both. Prompt A was kept. Its first version was not good enough: its §325-16C rules forgot the rear yard (an exception judged alone passed what the key fails), which review round 12 found; the final prompt says every yard a sentence names gets a rule. The remaining differences are cautious, never a false pass: a rear-yard flag with no condition makes height "needs review" even at 35 ft, and a 37 ft house with every yard 2 ft larger, legal under §325-16C, fails the chart's separately drafted 35 ft limit (see Weaknesses).
- **Weaknesses:** one AI call per unit can't see rules from other units, so an exception in one section of the law (the height bonus) and the limit it changes (the chart's height) are drafted as separate rules, and every rule must pass: the exception can't relax the limit, which gives a false FAIL on a design that uses it. How an exception relaxes a limit (a link between rules, or one combined rule) is a decision for the checker. Model: Sonnet; in the same 10-unit test Haiku gave no usable answer for 5 of 9 AI units (4 cut off at the token limit, 1 never valid), Sonnet for none (`packages/rule_drafting/evals/2026-10-19_model_choice/`).

## 11. Evaluation against independent sources

- **Two readings of the chart** (PR 6, the chart reader): code (§4) vs the hand-drafted R-1b: all R-1B numbers agree.
- **Two readings of each row** (PR 6): drawn cells vs plain text lines, for every district.
- **The architects' own check:** their spreadsheet of 106 Ithaca Rd vs our R-1b formulas: 11/11 rows give the same PASS/FAIL (`test_answer_keys.py`). Limits: one house, one zone; their files have their own errors (listed in `docs/discrepancies_with_architects.md`).
- **Planned:** 2–3 more worked examples in other zones from the architects; real Rhino models once measuring exists.

## 12. Reviews (process)

- **Review loop:** for every PR, a fresh reviewer with no context looks for problems, two skeptics try to disprove each one, confirmed findings are fixed and pinned with a test that fails on revert, and rounds repeat until one finds nothing. Large changes are reviewed before they're committed.
- **Lesson learned:** fix the pattern, not the instance: several rounds re-found the same mistake elsewhere after a narrow fix.
- **Pins:** every safeguard is switched off once on purpose to confirm a test fails.

## 13. The rules spreadsheet (code)

- **What:** `python -m rule_export` writes `<place>_rules.xlsx` (for Ithaca, `regulations/jurisdictions/new_york/ithaca_city/ithaca_city_rules.xlsx`): tabs for rules (with worked examples), definitions, use names, open questions, every piece of the law with its label and every change made after the AI, and the source documents (with the ones not yet downloaded, and why). Every field of every format is shown or listed as left out on purpose, and each column is tested to show its field. Each row has the city's exact words (for a chart cell, its value as the chart reader read it, cited by section · row · district column), the page, and a link that opens the document at that page. Laid out like the architects' own spreadsheet.
- **Why:** human approval is deferred; the spreadsheet is how people read and check what the code has verified, in a format they already use. Generated from the rule files, never edited, so it can't drift from them.
- **Links:** the city's URL where it serves the PDF itself; otherwise the fingerprinted copy in the repository (private: needs access). The page number is shown too, since some viewers ignore `#page=N`.
- **Tested by:** every rule, definition and use source, open question and piece of the law appears exactly once, attributed to its file, with the right words and link; text never becomes a formula; CI fails if the committed workbook differs from a fresh build (compared by content and look: values, links, fonts, fills, widths and frozen panes, not bytes, since Excel files carry timestamps).

## 14. The project report (code, PR 10)

- **What:** `python -m project_report <project.yaml>` fills in the architects' own two-tab spreadsheet (Inputs, Output; same headers, same order) for one project: its zone picks the rulebook (hand-drafted first, else AI-drafted), every rule in it becomes a row, and our columns (rule id, formula, why it needs review, citation, the city's words, link, rulebook) follow theirs, set apart by a light blue on the headers (not a color in their key). It looks like theirs: Arial in their ink color, their column widths, yellow typed-in values, FAIL in red.
- **Results:** only from `outcome()`, the checker's own code. The table limit is worked out for the lot from the rule's formula (rear yard at 106 Ithaca Rd: max(min(0.25 × 90, 50), 20) = 22.5 ft) for people to read; it never decides the result.
- **Refuses unchecked rules:** the report runs the same per-file checks as `python -m rule_format` (one shared function) on the sources, term files and rulebook, and gives no report if any fails. With approval deferred, this is what stops a rule edited and never checked from giving PASS.
- **Tested by:** the 106 Ithaca Rd report gives the architects' PASS/FAIL on all 11 rows; a rulebook, term file or source list that fails the rule checks gives no report; every result equals `outcome()`; every row's page and link are its rule's source; every NEEDS REVIEW row says why; the architects' columns have their widths, fonts and colors; CI fails if the committed example differs from a fresh build in content or look.
- **Weakness:** one example project; the measurements are typed in (from the architects' sheet), not measured from a model.

## 15. Measuring a Rhino model (code, PR 11)

- **What:** `model_measurement` reads a .3dm with rhino3dm (Rhino's own file library) and measures lot area, width and depth, the yards, building area and height as the city's definitions say (`4_term_definitions/definitions.yaml`). What a model can't show (street side, ground level, use, stories, bedrooms, parking) comes from lot facts the architect states. Geometry with shapely (pinned).
- **Never a guess:** where the law reads more than one way (a jog: side or rear lot line? a curved street: along the curve or straight across? an overhang: to the wall or to the edge above? a pitched roof's "average height"), every reading is measured; the same number under all of them is the value, otherwise no value, the readings, and the open question, so the checker says NEEDS REVIEW.
- **Working:** every value records how it was found, the objects, the definition, and the two points a distance was measured between; the project file's `from` carries it into the report.
- **Why one code path:** Rhino's Python is 3.9; ours is 3.12. Rhino copies the objects into a small .3dm and our Python measures it, so CI and the live model use the same reader (`docs/decisions/2026-10-20_rhino_talks_to_python.md`).
- **Tested by:** the architects' design drawn exactly as their spreadsheet describes gives every one of their numbers and their PASS/FAIL on 11/11 rows; their own model, measured, confirms the discrepancies in `discrepancies_with_architects.md` §4 by code; made-up lots with known answers cover tilted lots, a curved street, a jog, corner lots, two buildings, an overhang and a pitched roof; CI re-measures every committed model.
- **Weakness:** curved walls and roofs, sloped ground and story counting aren't measured yet (reported, never approximated); a part above the main roof (a chimney, parapet or bulkhead) gives NEEDS REVIEW, with the height read both leaving it out and to its top.

## 16. Starting a project in Rhino (code, PR 14)

- **What:** `GordiumStart` (or `GordiumCheck` on an empty model) shows one prefilled box first (address, zone,
  building type, street side, survey, corner lot, ground). On OK it draws the lot and the largest legal starting
  building as stacked floor blocks (`envelope_builder.start`): inside every yard, at the coverage and height
  limits, one block per story. On any lot shape the building is measured and checked with the checker's own rules
  before it is drawn; if it would break one, nothing is drawn and Gordium says it can't generate a starting
  building on this lot shape yet, so the architect draws one and Gordium checks it. After an edit the results grey out ("Model changed since the
  last check — press Check") until the panel's Check; with Check after every edit ticked, Gordium checks again by
  itself. After a check the corner message updates, failing parts turn red, and a short note shows in the view
  only when a rule newly fails.
- **Stories from the shape:** Gordium's own floor blocks (each marked as one story when drawn) are counted.
  Anything else stacked (a podium, a bulkhead, a roof solid) and any typed count are readings: if they disagree
  it's a question. One solid with no floors asks for floors or a count. Never guessed from the height.
- **"Complies" without a guess:** a rule waiting on how the law reads (which lines are side lot lines) is worked
  out under every reading; if every reading passes, the design is said to comply whichever way the question is
  answered. The rule's result stays NEEDS REVIEW. A lot not yet surveyed is a missing fact, not a reading: those
  rules say "passes with the lot as drawn (confirm the survey)" and stay amber.
- **Tested by:** the generated building passes every outside R-1b rule on made-up lots and 106 Ithaca Rd, and is
  maximal (1 ft more on any side breaks a rule); over 60 random lot shapes no building placed breaks a rule; the whole flow run in Rhino 8 from an empty document (PR
  description).

## 17. The term index and "show your work" research (code, then research; PR 17)

- **What:** the term index (`4_term_definitions/term_index.yaml`, generated by `python -m section_labeling coverage`) lists, for every defined term and every word that means the same (`regulations/document_extraction_guide/term_synonyms.yaml`: yard, setback, open space; eave, overhang, cornice, projection...), every piece of the law that uses it, with page and line. Whole words, any case, plurals (+s, +es, and consonant + y → ies: balcony → balconies), phrases split across a line break. Three things read it: the drafting AI (related sections, as background it may not quote), the rules spreadsheet (a "Related sections" column) and whoever researches an open question.
- **The rule it serves (resolve before asking):** before a question goes to the architects, read the whole law for it through the index, then the City's own decisions (zoning board records), then the building codes, then other cities, in that order. Each open question carries `research: {question, searched (piece ids), sources, why_open, readings}`; a settled one moves to `findings: {id, question, kind: law | reading, answer, sources, strength, confirm_with}`. `python -m rule_format` refuses an open question without research, a finding from the law without a quote it can verify, and a reading that claims more strength than its best source (strong = the code; City practice = the City's records; moderate = building codes; weak = other cities only). A question raised by code (a drafting run) says `why_open: pending: ...` with nothing searched, so it is honest about not being researched yet.
- **Why:** an early question to the architects ("are yards measured to the wall or the eave?") was answered by §325-18B, the eaves rule, which the definition of a yard never mentions. The index finds it ("yard" lists §325-18B), and the check makes the search visible.
- **What the 2026-10-20 research did** (`docs/research/2026-10-20_architect_questions.md`): of 37 open questions, 20 were settled (the law or a well-sourced reading, recorded as findings), 4 were narrowed to the part still open, and 2 new ones were found (non-frame accessory buildings; the ADU's "primary front yard"), leaving 19 open, on 12 topics in `docs/questions_for_architects.md` (plus the survey question for 106 Ithaca Rd). Readings are shown as "Gordium's reading · confirm with ..."; an architect's or the City's answer outranks them.
- **Readings still in play:** an open question lists its readings by id (`lowest_eave`, `wall_plate`, `drip_edge`), so the measurement code can check a design under every one: PASS only if all pass, FAIL only if all fail, otherwise NEEDS REVIEW (PR 18, being built).
- **A question is settled or open, never both:** `python -m rule_format` also checks across every rule, definition and label that a finding which quotes words an open question asks about, or cites lines an open question's research cites, names that question in `still_open: ["325-25C#1"]` (a real open question, by the questions page's tag) and says in its answer what is still open; in an entry that still has open questions, every finding carries `still_open` (empty when it leaves none open), so the relation is stated, never guessed. The spreadsheet shows it. A test holds every number and district name in a law answer to its quotes. A first review found the 12 ft story test filed as the law while the main-entrance question still asked whether it applies on every side, and a height-bonus answer saying more about U-1 than its quote did.
- **Weaknesses:** the synonym list is hand-curated, so a word nobody thought of is missed; common words ("height", "yard") list dozens of sections, so the drafter gets the densest few (rule and flag pieces, most uses per word, 12,000 characters). Sources outside the code (zoning board packets) are linked and named but can't be checked by code; the report says what was read.
- **Tested by:** the index lists §325-18B for "yard" and §325-16A/B/C for height; a synonym alone is found; every definition has a synonyms entry; CI rebuilds the index and fails on any difference. The check refuses each kind of missing or overclaimed research (one test each), every committed open question has real research (none pending), and every finding's quote is verified on its page.
- **Improve:** grow the synonym list from each review's misses; research each new drafted question before it reaches the questions page.
## 17. Looking up a site from its address (code, `packages/site_lookup`)

- **What:** `python -m site_lookup "<address>"` turns an address into start-box facts, each
  exactly `{value, source, confirmed_by, date}` (source "from tax map" for the lot, "suggested by Gordium"
  otherwise), with a status beside each (suggested / needs review / ask) and the service it came from. EPSG:2261
  is US survey feet; lengths are converted to Gordium's international feet (× 1200/3937 ÷ 0.3048 = 1.000002).
  No AI.
- **How:** the NYS Geocoder's address point (the County's address points as a cross-check) → the tax parcel
  containing it, outline asked for in EPSG:2261 (NY State Plane, feet) and measured by our own code (never the
  service's area field) → the parcel's SWIS code must be the City of Ithaca's (500700), otherwise refused → lot
  lines that run along a street centerline (within 30°) and sit within half the right-of-way + 10 ft of it are
  street lines; two streets is a corner lot, and Gordium asks for the front → USGS 3DEP elevations at the
  corners (today's ground, an estimate) → the City zoning map's zone under the lot, always a suggestion, with
  rezonings the online map may not show yet (`amendments.yaml`: a padded box around each ordinance's map
  area; Ord. 2025-12 Southside from the May 2026 Southside Form District Map) flagged for lots touching them,
  until someone has checked the online map shows the rezoning (`map_shows_since`, set by hand; the map's own
  edit date never clears one, since any edit moves it).
- **Never a false pass:** two zones, two streets, a mismatched street, a far County point, an overlay, a
  failing service, or incomplete evidence (missing elevations, unknown road widths, a match with no parcel,
  City flags unavailable): each becomes ask or needs review with a plain reason, never a silent choice. The
  strongest status wins (ask > needs review > suggested).
- **Licensing:** City and County layers are used live and never stored; a project's snapshot keeps each fact
  value, reason and note only as far as the strictest source it was worked out from allows (`store` in
  `endpoints.yaml`), plus each source's URL, date and SHA-256. Test fixtures hold State and USGS answers only; the City stand-ins are synthetic.
- **Tested by:** recorded State and USGS answers for 106, 109 and 96 Ithaca Rd, a Town of Ithaca address and
  an unknown one, with synthetic stand-in City layers (106: parcel 84.-2-6, 7,033.7 sf, 75.8
  ft on Ithaca Rd, interior, ground 735–749 ft, R-1b suggested; 109 and 96: corner lots, ask). A live check
  runs with `GORDIUM_LIVE=1`.
- **Weakness:** the tax map is approximate (about ±2 ft); the Southside area is a padded box, not the
  districts' own outline, and an amendment stays flagged until someone checks the online map shows it
  (`map_shows_since`); overlays are found but not checked.

## 18. What's not decided or not built

- How model objects are identified beyond the layers (names, or asking every time).
- Site facts: wiring the address lookup into the start box; survey vs city records for the lot lines.
- Measuring curved walls and roofs, sloped ground, and stories from floors in the model.
- Human approval: deferred (rules stay drafts, checked by code); the approval fields stay in the formats, unused.
