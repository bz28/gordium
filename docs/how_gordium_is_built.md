# How Gordium is built

A five-minute read on what each piece does, why it exists, and how the pieces connect. Updated in every PR.

## The goal in one line

An architect edits a design in Rhino, and Gordium says, for every zoning rule: **pass**, **fail**, or **needs review**, with the exact page of the city's law behind each answer.

## The assembly line

The city's documents go in on the left. A traceable rulebook, checked by code, comes out on the right. A design is then checked against that rulebook.

```
 City PDFs ──► Text ──► Definitions ──► Rules ──► Frozen ──► Check a
 (step 1)     (step 2)   (step 4)       (step 5)   rulebook    Rhino design
                 │                         ▲        (step 7)    (later)
                 └── every quote is ───────┘
                     checked against this text
```

| Step | What it is | Why it exists | Made by | Status |
|---|---|---|---|---|
| 1. Source documents | The city's original PDFs, never edited, each with a fingerprint | Everything traces back to these | Downloaded from official sites | ✅ PR 0 |
| 2. Extracted text | Every line of every PDF, with its page and position | So a computer can check that a quote is really on its page | Code (same result every time) | ✅ PR 3 |
| 3. Section labels | Every paragraph of the law tagged: rule / flag / pointer / not relevant | Proves nothing in the law was skipped | Code, then AI for leftovers, checked by code (architect confirmation deferred) | Later |
| 4. Definitions | What "height", "story", "lot depth"… mean in Ithaca, in the city's words; unclear points as questions | A rule's numbers mean nothing until the words are defined | Written from the law under the drafting rules; quotes checked by code | 🔨 PR 4 |
| 5. Rules | One file per zone: each rule in plain English + a formula + its source | What designs are checked against | Hand-written for R-1b, then code reads the charts for every zone | Next |
| 6. Coverage report | List of every paragraph: handled or a gap | Proof for architects that we read everything | Code | Later |
| 7. Frozen rulebook | Rules that pass every code check are saved as a dated version that never changes. Architect approval is deferred for now (decided 2026-10-19); the approval fields wait unused | Same design = same answer | Code freezes | Later |

## The tools that keep it honest

| Tool | What it does | Analogy |
|---|---|---|
| **The rule form** (`packages/rule_format`) | Every rule has the same boxes: plain English, formula, source quote, worked examples, who drafted/approved it | A permit application form |
| **The calculator** (same package) | Turns a rule + a design's measurements into pass / fail / needs review. Missing or odd data is always "needs review", never "pass" | A calculator with only safe buttons |
| **The inspector** (`python -m rule_format`) | Rejects any rule, definition or use name that has no source, a quote not on its page, a changed PDF, a typo, wrong examples, or an illegitimate approval | The plan examiner |
| **The text extractor** (`packages/document_extraction`) | Copies text out of the PDFs with page and position; marks footnote numbers as `[fn11]` so they're never read as values | A searchable photocopy of the code book |
| **Automatic checks (CI)** | On every change, GitHub re-runs all tests, re-extracts the text to prove it's unchanged, and runs the inspector | An inspection before anything is accepted |
| **Review loop** (`/review`) | A fresh reviewer looks for mistakes, two skeptics try to disprove each one, the rest get fixed with a test, and it repeats until clean | Peer review with a second opinion |

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

Every document above is recorded in `regulations/jurisdictions/new_york/ithaca_city/1_source_documents/sources.yaml` with its link, download date and fingerprint. The one exception is the city's map data (GIS) lookup: it's a live database query, not a document, so it's recorded with its date and results in the test site's README instead. Zone confirmations will need a saved, fingerprinted record before they're used in checking.

## How the pull requests build on each other

| PR | Adds | Why it comes here |
|---|---|---|
| 0 | Folders, the city's PDFs, the architects' example | The foundation |
| 1 | The rule form, the calculator, the inspector, CI, the guide `how_rules_are_checked.md` | Everything after it writes rules, so the form comes first |
| 2 | Gordium's own instructions for the AI, the review loop, the plain-language PR template | How every later PR is built and reviewed |
| 3 | Text extracted from the PDFs | The inspector needs it to verify quotes |
| 4 | Ithaca's definitions and use names, this document | Rules depend on these words |
| 5 (next) | R-1b rules written by hand, the first real rulebook | The "answer key" the automation must match |
| 6 (next) | Code that reads the chart tables → rules for all 9 residential zones; compared with PR 5 | Proves the automation is right, then scales it |

## What people still decide

- **Architects** answer the open questions in `docs/questions_for_architects.md`. Approving each rule is deferred for now (decided 2026-10-19): AI drafts, code checks every draft, and people read the rules through a generated spreadsheet with links to the city's exact words. AI never approves.
- **Ben** reviews and merges every PR (commits to PR branches don't need his approval; he approves at merge time).

## Related documents

- `docs/how_rules_are_checked.md`: the promises Gordium makes and how each is enforced and tested
- `docs/discrepancies_with_architects.md`: where our findings differ from the architects' worked example
- `docs/questions_for_architects.md`: open questions
