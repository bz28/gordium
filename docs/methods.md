# Methods

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
- **Improve:** cite chart cells directly in rules (PR 7b).

## 4. Chart tables to cells (code, PR 6)

- **What:** reads the chart's drawn rectangles and borders to find rows, district columns and merged cells, then places each word in the cell that contains it. Output: one record per cell (page, section, row, district, value, lines, position). 683 cells on pages 2, 3, 14.
- **Why:** plain text lines lose columns, so "25 ft" can't be tied to R-1B. Drawn boxes are what the PDF actually says about the table.
- **Never guessing:** any uncertainty (a word across a cell edge, a stripe across the row, a split label area, a district without a cell, a row that looks like two, a repeated label under one section) makes the whole row unresolved; an unreadable header makes the page unresolved; rows after an unreadable row get no section.
- **Weaknesses:** the district-name pattern and layout rules are Ithaca's residential charts; another city needs its own checks.
- **Tested by:** every R-1B number matches the R-1b rules (exact pass/fail boundary); every district cross-checked against the plain text (56 rows agree, 0 disagree); the 6 wrapped rows hand-read in every column; 7 planted errors caught; CI reproduces the cells file.
- **Improve:** generalize to other cities' chart layouts, each with the same two-way cross-check.

## 5. Cutting the law into pieces (code, PR 7a)

- **What:** splits Chapter 325 at its own headings into 626 pieces (sections, lettered subsections, one per defined term, editor's notes, front matter). Page furniture (repeated titles, headers, footers) is set aside.
- **Why:** a small piece is one idea, can be judged alone and cited exactly. The law's own numbering is the natural unit.
- **Weaknesses:** heading patterns are tuned to Ithaca's code format.
- **Tested by:** every one of 6,027 lines is in exactly one piece or is furniture; the cut matches the law's table of contents; CI reproduces it.

## 6. Labeling pieces (AI: Haiku; code checks; PR 7a)

- **What:** one recorded AI call per piece labels it rule, flag, reference or not_for_checking. Instructions: `regulations/document_extraction_guide/labeling_guide.md` (role, purpose, process, rules). The answer lists the requirements first, as line numbers (L3–L5), then the label, topic, reason and one exact quote. Code takes the exact words from the cited lines.
- **Why this model:** sorting is simple reading; Haiku labeled all 626 for $0.085. Everything it says is checked by code and reviewed.
- **Why requirements first, by line number:** labeling first and justifying after let the model explain limits away ("the six-unit maximum is descriptive"). Listing requirements first, with code rejecting a label that disagrees with them, removes that. Line numbers instead of copied text remove copying errors (18 of 100 answers failed when asked to copy).
- **Fail-safe rules:** when unsure between not_for_checking and rule/flag, choose rule/flag; procedures are not_for_checking even with "shall".
- **Not repeatable bit for bit:** current models don't accept temperature 0. Every call is recorded; an architect's approval freezes a label.
- **Cost control:** a shared ledger with a hard cap ($1), worst case reserved before each call.
- **Tested by (evals):**
  - First prompt, 28 pieces with an answer key: 25/28, then 26/28 after guide fixes.
  - Independent AI review (Claude) of all 399 rule/flag/reference labels: 354 judged correct (89%); 4 flagged as dangerous (a limit hidden in a definition), 41 minor. Under the category-vs-limit principle adopted afterwards, two of the four (kitchen, bed-and-breakfast inn) are category definitions, so they are open questions for the architects rather than clear misses.
  - Improved prompt (role, purpose, process, line citations) on the 100 pieces with known answers (chosen because the first prompt failed them): 70/100 against the key at the time. Under the later category-vs-limit principle the kitchen answer (reference) counts as right (71/100); dwelling unit (reference, key rule) is an open question for the architects. The rest of the misses are procedures over-labeled as rules (safe direction).
- **The committed labels:** Haiku's answers plus 70 corrections made by an AI review (Claude, reading every rule, flag and reference label against the text), each recorded in `revised: {from, by, date, why}` with the reason rewritten for the new label. They are still drafts: architects approve. (Corrections to kitchen, adult day-care home and bed-and-breakfast inn were undone under the principle below and are open questions for the architects; dwelling unit and rooming unit are labeled rule until the architects decide, also as open questions.)
- **Category vs limit:** a definition whose number sorts things into categories (a kitchen is 60 sq ft or more; an adult day-care home serves up to six adults) is reference: rules use it to classify. A definition that caps what a design may do ("a maximum of six units may be attached", "not more than two unrelated individuals is permitted") is a rule. The test: does it forbid or cap something, or only say what to call it?
- **Weaknesses:** definitions with embedded limits remain the hardest case; procedures get over-labeled as rules.
- **Improve:** a second, independent AI pass on every non-rule piece asking only "does this set a requirement?"; few-shot examples from another city's code (never from the answer key); compare models on the known-answer set.

## 7. Safety nets on labels (code)

- **Requirement-word net:** every piece labeled reference whose text uses requirement wording (shall not, must, maximum, minimum, not less than, "No … shall", in conformity, …) goes on the review list, whatever the AI said.
- **Review list:** every not_for_checking label, every reference with requirement words, every label with an open question for the architects, every piece a rule or definition cites.
- **Provenance (checked by code in CI):** every AI-drafted label must be exactly what an answer in the run records produces, rebuilt with the labeler's own code (same page, lines and words), or say how it differs: a label change is recorded as `revised: {from, by, date, why}`, a change to the sources as `{field: sources, by, date, why}` (which must keep what the AI produced). `python -m section_labeling coverage --check` fails on any unexplained difference.
- **Known limit:** some rule labels' quotes are a lead-in sentence ("the following criteria must be present") rather than the requirement itself. Code doesn't judge quote quality: it checks only that a quote is the city's exact words inside the piece and matches the recorded answer. Whether a quote justifies the label is for the architects' review. Drafting reads the whole piece either way.
- **What a label's sources are for:** they justify the label, nothing more. Finding every requirement in a piece is the drafting step's job, and it reads the whole piece. Two attempts to improve sources by code were undone: adding a "requirement line" by keyword matching (it picked headings and fragments), and a check rejecting heading-only quotes (code can't tell a caption from an uncaptioned first sentence). One label that quoted only its caption (§325-45.5A) cites the whole provision, with a sources revision.
- **Coverage report:** every line of the law, its piece and its label.
- **Weaknesses:** the word net only catches the phrasings it knows. It started with exact phrases and missed "a maximum of", "No … shall" and "less than"; it now matches patterns (any "more/less/fewer/greater than", "exceed/exceeding", "No" plus up to six words then "shall", "limited to" but not "not limited to"). It also flags category definitions (false alarms, by design). It's a backstop, not the main defense.
- **Improve:** the second AI pass above; feed the net's misses back into the word list after each review.

## 8. Rule format and the formula language (code, PR 1)

- **What:** each rule has a title, the city's exact quotes, `applies_when`, `check` (a yes/no formula), `review_when`, worked examples, open questions, answers, and approval fields. Formulas are ordinary math read by Python's parser and checked against an allowed list (comparisons, and/or/not, min/max, `use in [...]`, `a if b else c`) and a fixed list of measurement names with units.
- **Why:** readable by architects, nothing hidden (no code execution), exact and repeatable. No plain-English retelling: retellings kept dropping or adding words; the quotes are the words and the examples show the meaning.
- **Fail closed:** missing, non-numeric, negative or impossible values give "needs review", never "pass".
- **Alternatives considered:** free-form code (unsafe, unreadable), a custom rule language (more to build and learn), JSON logic (hard to read).
- **Weaknesses:** yes/no measurements (e.g. "has a separate entrance") are being added in PR 7b.

## 9. The inspector (code, PR 1 onward)

- **What:** checks every rule, definition and label: sources (listed, unchanged, quotable, exact and unique on cited lines), formula (allowed, true/false, known names), examples (a pass and a fail, each giving its stated result), a use decided by a rule cites its chart row, approvals (a listed architect, not the drafter, no open questions, nothing changed since: an approval fingerprint covers content, id and the cited documents).
- **Weakness:** proves a rule is traceable and well formed, not that it means the right thing. Meaning comes from comparisons (§11) and architects.

## 10. Drafting rules (AI: planned Sonnet; code checks; PR 7b, in progress)

- **Plan:** chart rules get their numbers from cells, never typed by the AI; paragraph rules are drafted from each rule-labeled piece with its definitions and cross-referenced sections; every draft goes through the inspector with retries; every call recorded; hard cap ($5).
- **Model choice to be decided by eval:** draft ~10 rules with Haiku and with Sonnet, grade both against R-1b and the architects' spreadsheet.
- **Fairness:** the AI is never shown R-1b (the answer key).

## 11. Evaluation against independent sources

- **Two readings of the chart:** code (§4) vs the hand-drafted R-1b: all R-1B numbers agree.
- **Two readings of each row:** drawn cells vs plain text lines, for every district.
- **The architects' own check:** their spreadsheet of 106 Ithaca Rd vs our R-1b formulas: 11/11 rows give the same PASS/FAIL (`test_answer_keys.py`). Limits: one house, one zone; their files have their own errors (listed in `docs/discrepancies_with_architects.md`).
- **Planned:** 2–3 more worked examples in other zones from the architects; real Rhino models once measuring exists.

## 12. Reviews (process)

- **Review loop:** for every PR, a fresh reviewer with no context looks for problems, two skeptics try to disprove each one, confirmed findings are fixed and pinned with a test that fails on revert, and rounds repeat until one finds nothing. Large changes are reviewed before they're committed.
- **Lesson learned:** fix the pattern, not the instance: several rounds re-found the same mistake elsewhere after a narrow fix.
- **Pins:** every safeguard is switched off once on purpose to confirm a test fails.

## 13. The rules spreadsheet (code)

- **What:** `python -m rule_export` writes `<place>_rules.xlsx` (for Ithaca, `regulations/jurisdictions/new_york/ithaca_city/ithaca_city_rules.xlsx`): tabs for rules (with worked examples), definitions, use names, open questions, every piece of the law with its label and every change made after the AI, and the source documents (with the ones not yet downloaded, and why). Every field of every format is shown or listed as left out on purpose, and each column is tested to show its field. Each row has the city's exact words, the page, and a link that opens the document at that page. Laid out like the architects' own spreadsheet.
- **Why:** human approval is deferred; the spreadsheet is how people read and check what the code has verified, in a format they already use. Generated from the rule files, never edited, so it can't drift from them.
- **Links:** the city's URL where it serves the PDF itself; otherwise the fingerprinted copy in the repository (private: needs access). The page number is shown too, since some viewers ignore `#page=N`.
- **Tested by:** every rule, definition and use source, open question and piece of the law appears exactly once, attributed to its file, with the right words and link; text never becomes a formula; CI fails if the committed workbook differs from a fresh build (compared by content and look: values, links, fonts, fills, widths and frozen panes, not bytes, since Excel files carry timestamps).

## 14. The project report (code, PR 10)

- **What:** `python -m project_report <project.yaml>` fills in the architects' own two-tab spreadsheet (Inputs, Output; same headers, same order) for one project: its zone picks the rulebook (hand-drafted first, else AI-drafted), every rule in it becomes a row, and our columns (rule id, formula, why it needs review, citation, the city's words, link, rulebook) follow theirs, set apart by a light blue on the headers (not a color in their key). It looks like theirs: Arial in their ink color, their column widths, yellow typed-in values, FAIL in red.
- **Results:** only from `outcome()`, the checker's own code. The table limit is worked out for the lot from the rule's formula (rear yard at 106 Ithaca Rd: max(min(0.25 × 90, 50), 20) = 22.5 ft) for people to read; it never decides the result.
- **Refuses unchecked rules:** the report runs the same per-file checks as `python -m rule_format` (one shared function) on the sources, term files and rulebook, and gives no report if any fails. With approval deferred, this is what stops a rule edited and never checked from giving PASS.
- **Tested by:** the 106 Ithaca Rd report gives the architects' PASS/FAIL on all 11 rows; a rulebook, term file or source list that fails the rule checks gives no report; every result equals `outcome()`; every row's page and link are its rule's source; every NEEDS REVIEW row says why; the architects' columns have their widths, fonts and colors; CI fails if the committed example differs from a fresh build in content or look.
- **Weakness:** one example project; the measurements are typed in (from the architects' sheet), not measured from a model.

## 15. What's not decided or not built

- Rhino plugin language (C# vs Rhino 8 Python); how model objects are identified (layers, names, or asking).
- Site facts: zone lookup from the address, lot lines and area (survey vs city records), ground levels.
- Measuring the model (engineer-written code, tested on real models).
- Human approval: deferred (rules stay drafts, checked by code); the approval fields stay in the formats, unused.
