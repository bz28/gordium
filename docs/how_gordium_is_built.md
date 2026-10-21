# How Gordium is built

**Purpose:** the code-level map: which package and file does each step, and how the pull requests build on each other.\
**For:** engineers joining the project.\
**Kept current by:** every PR that adds a package or changes a step.

A five-minute read on what each piece does, why it exists, and how the pieces connect. Updated in every PR.

## The goal in one line

An architect edits a design in Rhino, and Gordium says, for every zoning rule: **pass**, **fail**, or **needs review**, with the exact page of the city's law behind each answer.

## How the codebase fits together

The city's documents go in on the left. A traceable rulebook, checked by code, comes out in the middle. Designs are checked against it on the right.

```
 City PDFs ─► Text ─► Pieces + labels ─► Definitions ─► Rules ─► Checker ─► Spreadsheet / report ─► Rhino
 (1)          (2)     (3, 6)             (4)            (5)      (calc)     (people read them)        (coming)
                │                                        ▲
                └──── every quote in a rule is checked ───┘
                      against this text, line by line
```

| Step | In → out | Package (code) | Made by | Status |
|---|---|---|---|---|
| 1. Source documents | city websites → the original PDFs, each with a fingerprint | none (`1_source_documents/sources.yaml`) | downloaded by hand | ✅ PR 0 |
| 2. Extracted text | PDFs → every line, with page and position | `document_extraction` | code, same result every time | ✅ PR 3 |
| 3. Pieces and labels | the law's text → 626 pieces, each labeled rule / flag / reference / not for checking | `document_extraction.sections` cuts; `section_labeling` labels | code cuts; AI (Haiku) labels; code checks every label; a second AI (Claude) reviewed them; architect approval deferred | ✅ PR 7 |
| 4. Definitions | the law's definitions → what "height", "story", "lot depth"… mean, in the city's words | data only (`4_term_definitions/`) | written from the law; quotes checked by code | ✅ PR 4 |
| 5. Rules | chart cells + rule pieces → one file per zone: title, the city's quotes, a formula, worked examples | data (`5_zoning_rules/`); `rule_format` defines and inspects them | R-1b drafted by Claude in conversation (PR 5); every zone by AI with code checks (PR 8, full run not done) | 🔨 |
| 6. Coverage report | pieces + labels → every line of the law, its piece and its label | `section_labeling` | code | ✅ PR 7 |
| 7. Frozen rulebook | rules that pass every check → a dated version that never changes. Architect approval is deferred for now (decided 2026-10-19); the approval fields wait unused | `rule_format` (planned) | code | Later |

**What people read:**

| Output | In → out | Package | PR |
|---|---|---|---|
| Rules spreadsheet | every rule, definition, use, open question and piece → one workbook with links to the city's words | `rule_export` | 9 |
| Project report | a project's measurements + its zone's rules → the architects' own two-tab format, PASS / FAIL / NEEDS REVIEW per requirement | `project_report` | 10 |
| Questions for the architects | every open question → one plain-English page | `docs/questions_for_architects.md` | 11 |

## The tools that keep it honest

| Tool | What it does | Analogy |
|---|---|---|
| **The rule form and calculator** (`rule_format`) | Every rule has the same boxes; the calculator turns a rule + a design's measurements into pass / fail / needs review. Missing or odd data is always "needs review", never "pass" | A permit form and a calculator with only safe buttons |
| **The inspector** (`python -m rule_format`) | Rejects any rule, definition, use or label with no source, a quote not on its lines, a changed PDF, a typo or wrong examples | The plan examiner |
| **Shared helpers** (`rule_format.rulebook`) | One reader for every `.jsonl` file and one list of jurisdictions (tests fail if a second copy appears); one list of rulebook files | One ruler for the whole office |
| **Automatic checks (CI)** | On every change, GitHub re-runs the tests, re-extracts the PDFs, runs the inspector, and rebuilds the coverage report, the spreadsheet and the report to prove the saved copies are current | An inspection before anything is accepted |
| **Review loop** (`/review`) | A fresh reviewer looks for mistakes, two skeptics try to disprove each one, the rest get fixed with a test, and it repeats until clean | Peer review with a second opinion |

## How the pull requests build on each other

| PR | Adds | Why it comes here |
|---|---|---|
| 0 | Folders, the city's PDFs, the architects' example | The foundation |
| 1 | The rule form, the calculator, the inspector, CI | Everything after it writes rules, so the form comes first |
| 2 | Gordium's own instructions for the AI, the review loop, the PR template (side branch off main; its files join when it merges) | How every later PR is built and reviewed |
| 3 | Text extracted from the PDFs (`document_extraction`) | The inspector needs it to verify quotes |
| 4 | Definitions and use names, this document | Rules depend on these words |
| 5 | R-1b rules drafted by Claude in conversation, matched against the architects' spreadsheet (11/11) | A second, independent reading; an answer key once architects approve it (deferred for now) |
| 6 | The chart reader: every chart cell tied to its zone (on PR 5, beside PR 7; PR 8 brings it into the main line) | Numbers come from cells, never typed |
| 7 | The law cut into pieces, each labeled by AI and checked by code; the coverage report (`section_labeling`) | Proves nothing in the law was skipped |
| 8 | Rule drafting for every zone (`rule_drafting`, built on 7, with 6 merged in; 9 builds on it) | Scales PR 5 to every zone |
| 9 | The rules spreadsheet (`rule_export`) | How people read and check the rules |
| 10 | The project report in the architects' format (`project_report`) | A design's answer, in the form architects already use |
| 11 | The questions page for the architects | What only they can decide |
| 12+ | Measuring a Rhino model, the Rhino command (coming) | The design side of the check |

## Where each piece of information comes from

| Information | Document | Where | Used for |
|---|---|---|---|
| Which zone a lot is in | Zoning maps (May 2026) + city GIS records | Map p.1 (city), p.8 (Collegetown/East Hill) | Picking the right rule file (106 Ithaca Rd = R-1b) |
| Allowed uses per zone | Zoning charts (Apr 2026) | p.2 | `uses.yaml`, "is this use allowed?" rules |
| Lot size, width, height, stories, coverage, yards | Zoning charts | p.3 (residential) | The numbers in each zone's rules |
| Parking | Zoning charts | p.14 | Parking rules |
| What words mean (height, story, grade plane, yards…) | Chapter 325, §325-3 | pp. 4–21 | `definitions.yaml`; later, how Rhino models are measured |
| What each chart column means (lot width = street frontage; stories counted at the main entrance; rear yard % of the *average* side lot line) | Chapter 325, §325-8 | pp. 24–26 | Definitions and rules |
| Porches/decks count toward coverage and yards; eaves may project 2 ft | Chapter 325, §325-18 | p.49 | Definitions and rules |
| Height exceptions (chimneys, equipment…) | Chapter 325, §325-16 | pp. 46–48 | Later rules |
| Southside rezoning (not yet in the charts or Chapter 325 online) | Ordinance No. 2025-12 | whole document | Southside residential zones (later) |

Every document above is recorded in `regulations/jurisdictions/new_york/ithaca_city/1_source_documents/sources.yaml` with its link, download date and fingerprint. The one exception is the city's map data (GIS): it's a live database query, not a document, so it's recorded with its date and results in the test site's README instead. Zone confirmations will need a saved, fingerprinted record before they're used in checking.

## What people still decide

- **Architects** answer the open questions in `docs/questions_for_architects.md`. Approving each rule is deferred for now (decided 2026-10-19): AI drafts, code checks every draft, and people read the rules through the rules spreadsheet, with links to the city's exact words. AI never approves.
- **Ben** reviews and merges every PR (commits to PR branches don't need his approval; he approves at merge time).

## Related documents

- `docs/methods.md`: every technique, why it was chosen, its weaknesses and how it's tested
- `docs/how_rules_are_checked.md`: the promises Gordium makes and how each is enforced and tested
- `docs/discrepancies_with_architects.md`: where our findings differ from the architects' worked example
- `docs/questions_for_architects.md`: open questions
