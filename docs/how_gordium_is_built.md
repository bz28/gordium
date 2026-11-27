# How Gordium is built

**Purpose:** the code-level map: for each step of [How Gordium works, step by step](https://claude.ai/artifact/5LAxAN2qpWFUMDBBDpLQrh), which package and files do it, and how the pull requests build on each other.\
**For:** engineers joining the project.\
**Kept current by:** every PR that adds a package or changes a step.

Read the [step-by-step walkthrough](https://claude.ai/artifact/5LAxAN2qpWFUMDBBDpLQrh) first: it tells the story in plain English. This page follows the same steps and says where each one lives in the code. Words in links are defined in the [glossary](glossary.md).

## The goal in one line

An architect edits a design in Rhino, and Gordium says, for every zoning rule: **complies**, **does not comply** or **needs review**, with the exact page of the City's law behind each answer.

## The two halves

```
 Part 1, once per version of the law (our computers)          Part 2, every edit (the architect's computer, no AI)
 City PDFs ─► Text ─► Pieces + labels ─► Definitions ─► Rules ═══► Rhino ─► worker: measure ─► check ─► show
 (1)          (2)     (3, 6)             (4)            (5)          start box   (model_measurement) (rule_format) (panel)
                │                                        ▲
                └──── every quote in a rule is checked ───┘
                      against this text, line by line
```

## Part 1: turning the law into rules

| Step | In → out | Package (code) | Made by | Status |
|---|---|---|---|---|
| 1. Source documents | city websites → the original PDFs, each with a fingerprint | none (`1_source_documents/sources.yaml`; the fingerprint check is in `rule_format`) | downloaded by hand | ✅ PR 0 |
| 2. Extracted text | PDFs → every line, with page and position | `document_extraction` (`extract.py`; `charts.py` reads the chart tables into cells) | code, same result every time | ✅ PR 3 |
| 3. Pieces and labels | the law's text → 626 pieces, each labeled rule / flag / reference / not for checking | `document_extraction.sections` cuts; `section_labeling` labels | code cuts; AI (Haiku) labels; code checks every label; a second AI (Claude) reviewed them; architect approval deferred | ✅ PR 7 |
| 4. Definitions and term index | the law's definitions → what "height", "story", "lot depth"… mean, in the City's words; every section that uses each word or a synonym | data (`4_term_definitions/definitions.yaml`, `term_index.yaml`); the index is built by `section_labeling.term_index` | written from the law; quotes checked by code | ✅ PR 4, PR 17 |
| 5. Rules | chart cells + rule pieces → one file per zone: title, the City's quotes, a formula, worked examples | data (`5_zoning_rules/`); `rule_drafting` drafts; `rule_format` defines and inspects them | R-1b drafted by Claude in conversation (PR 5); every zone by AI with code checks (PR 8, full run not done) | 🔨 |
| 5b. Research | each open question → the law's answer, Gordium's reading, or still open with what was searched | recorded in the rule and definition files (`research`, `findings`); report in `docs/research/` | research by Claude, checked by `rule_format` (a settled question can't also be open) | ✅ R-1b, PR 17 |
| 6. Coverage report | pieces + labels → every line of the law, its piece and its label | `section_labeling` | code | ✅ PR 7 |
| 7. Frozen rulebook | rules that pass every check → a dated version that never changes. Architect approval is deferred for now (decided 2026-10-19); the approval fields wait unused | `rule_format` (planned) | code | Later |

**What people read:**

| Output | In → out | Package | PR |
|---|---|---|---|
| Rules spreadsheet | every rule, definition, use, open question and piece → one workbook with links to the City's words | `rule_export` | 9 |
| Project report | a project's measurements + its zone's rules → the architects' own two-tab format, PASS / FAIL / NEEDS REVIEW per requirement | `project_report` | 10 |
| Questions for the architects | every open question → one plain-English page | `docs/questions_for_architects.md` | 11 |
| Egress permit sheets | a house's egress check + its interior description → G-001 code analysis, LS-101 life-safety plan, A-601 escape-window schedule (PDF, SVG, CSV, XLSX), each result the check's own ([plan](permit_sheets/plan.md)) | `permit_sheets` | 109 |

## Part 2: checking a design in Rhino

Rhino only draws. Measuring and checking happen in a background Python process, the [worker](glossary.md#worker); why is in [the Rhino-to-Python decision](decisions/2026-10-20_rhino_talks_to_python.md).

| Walkthrough step | What the code does | Where |
|---|---|---|
| GordiumStart: the start box | Opens the prefilled box; saves each answer as a fact in the .3dm | `apps/rhino_plugin/gordium_start.py`, `gordium_ui.py` (`start_box`) |
| Look up an address | Asks the public map services; each answer becomes a suggested fact with its source | `site_lookup` (PR 16; in the start box from PR 19) |
| Draw: the largest legal starting house | The envelope (lot shrunk by every yard, up to the height limit), then the starting house inside it, proved by the checker before it is drawn | `envelope_builder` (`envelope.py`, `start.py`) |
| Every edit: send | With **Check after every edit** ticked (off at first, kept with the file; otherwise the panel says the results are out of date until **Check** is pressed), waits until the model is still for 0.5 s, copies the lot and building into a temporary .3dm, sends it to the worker | `apps/rhino_plugin/gordium_live.py`, `gordium_rhino.py`; the decisions as plain testable code in `design_checker/rhino_logic.py` |
| Every edit: measure | Lot area, width, depth; yards; building area; height; stories, by the City's definitions | `model_measurement` (`read_3dm.py`, `places/ithaca_city/measure.py`: the City's definitions) |
| Every edit: check | Each rule's result; missing data or an unclear rule → needs review, unless the rule provably fails at every value the missing number could take (`check.fails_whatever`) → does not comply; a missing number never causes a pass: a rule complies with one missing only when the known numbers already settle it, whatever the missing one is (three-valued logic, `formula.evaluate`) ([decision](decisions/2026-10-21_fails_whatever_the_missing_number.md)); an open question with named readings is checked under every reading (complies only if all pass); an overhang in a yard needs review until the architect marks it as eaves ([eaves decision](decisions/2026-10-21_eaves_need_confirmation.md)) | `design_checker` (`check.py`, worker in `__main__.py`), through `project_report` to `rule_format.rulebook.outcome()` |
| Every edit: show | The status box, the panel, red only on the part that is over, the shortfall as a dimension | words and numbers from `design_checker/present.py`; drawn by `apps/rhino_plugin/gordium_ui.py` |
| Zoning report… | The architects' spreadsheet format, opened, with where it was saved | `project_report` |

## The tools that keep it honest

| Tool | What it does | Analogy |
|---|---|---|
| **The rule form and calculator** (`rule_format`) | Every rule has the same boxes; the calculator turns a rule + a design's measurements into pass / fail / needs review. Missing or odd data is always "needs review", never "pass" | A permit form and a calculator with only safe buttons |
| **The inspector** (`python -m rule_format`) | Rejects any rule, definition, use or label with no source, a quote not on its lines, a changed PDF, a typo or wrong examples | The plan examiner |
| **Shared helpers** (`rule_format.rulebook`) | One reader for every `.jsonl` file and one list of jurisdictions (tests fail if a second copy appears); one list of rulebook files | One ruler for the whole office |
| **Automatic checks (CI)** | On every change, GitHub re-runs the tests, re-extracts the PDFs, runs the inspector, and rebuilds the coverage report, the spreadsheet, the measured models and the report to prove the saved copies are current (the full list: `.github/workflows/ci.yml`; the same checks on Windows, in `.github/workflows/windows.yml`, run nightly on main and when a PR is about to merge) | An inspection before anything is accepted |
| **Review loop** (`/review`) | A fresh reviewer looks for mistakes, skeptics try to disprove each one (two for anything that could give a false pass, one for wording), the rest get fixed with a test, and it repeats until clean | Peer review with a second opinion |

## How the pull requests build on each other

| PR | Adds | Why it comes here |
|---|---|---|
| 0 | Folders, the City's PDFs, the architects' example | The foundation |
| 1 | The rule form, the calculator, the inspector, CI | Everything after it writes rules, so the form comes first |
| 2 | Gordium's own instructions for the AI, the review loop, the PR template | How every later PR is built and reviewed |
| 3 | Text extracted from the PDFs (`document_extraction`) | The inspector needs it to verify quotes |
| 4 | Definitions and use names, this document | Rules depend on these words |
| 5 | R-1b rules drafted by Claude in conversation, matched against the architects' spreadsheet (11/11) | A second, independent reading; an answer key once architects approve it (deferred for now) |
| 6 | The chart reader: every chart cell tied to its zone (on PR 5, beside PR 7; PR 8 brings it into the main line) | Numbers come from cells, never typed |
| 7 | The law cut into pieces, each labeled by AI and checked by code; the coverage report (`section_labeling`) | Proves nothing in the law was skipped |
| 8 | Rule drafting for every zone (`rule_drafting`, built on 7, with 6 merged in; 9 builds on it) | Scales PR 5 to every zone |
| 9 | The rules spreadsheet (`rule_export`) | How people read and check the rules |
| 10 | The project report in the architects' format (`project_report`) | A design's answer, in the form architects already use |
| 11 | The questions page for the architects | What only they can decide |
| 12 | Measuring a Rhino model the way the City defines each measurement (`model_measurement`) | The design side of the check |
| 13 | GordiumCheck in Rhino: the largest legal building (`envelope_builder`) and live re-checks (`design_checker`) | The check runs where architects design |
| 14–15 | Starting a project in Rhino, and the Gordium panel (`apps/rhino_plugin`) | What the architect sees |
| 16 | Looking up an address (`site_lookup`; side branch, joins after 15) | The start box fills itself |
| 17 | The term index (every section that uses a defined word) and the "show your work" check on open questions, with the 2026-10-20 research filed in | Only what research can't settle reaches the architects |
| 18 | Measuring pitched roofs, eaves in yards, porch steps, accessory buildings and corner lots; the every-reading rule in the checker (`model_measurement`, `design_checker`) | The shapes real houses have, and unclear law checked every reasonable way |

## Where each piece of information comes from

| Information | Document | Where | Used for |
|---|---|---|---|
| Which zone a lot is in | Zoning maps (May 2026) + City GIS records | Map p.1 (city), p.8 (Collegetown/East Hill) | Picking the right rule file (106 Ithaca Rd = R-1b) |
| Allowed uses per zone | Zoning charts (Apr 2026) | p.2 | `uses.yaml`, "is this use allowed?" rules |
| Lot size, width, height, stories, coverage, yards | Zoning charts | p.3 (residential) | The numbers in each zone's rules |
| Parking | Zoning charts | p.14 | Parking rules |
| What words mean (height, story, grade plane, yards…) | Chapter 325, §325-3 | pp. 4–21 | `definitions.yaml`; how Rhino models are measured |
| What each chart column means (lot width = street frontage; stories counted at the main entrance; rear yard % of the *average* side lot line) | Chapter 325, §325-8 | pp. 24–26 | Definitions and rules |
| Porches/decks count toward coverage and yards; eaves may project 2 ft | Chapter 325, §325-18 | p.49 | Definitions and rules |
| Height exceptions (chimneys, equipment…) | Chapter 325, §325-16 | pp. 46–48 | Later rules |
| Southside rezoning (not yet in the charts or Chapter 325 online) | Ordinance No. 2025-12 | whole document | Southside residential zones (later) |

Every document above is recorded in `regulations/jurisdictions/new_york/ithaca_city/1_source_documents/sources.yaml` with its link, download date and fingerprint. The City's map data (GIS) is different: it is a live query, not a document. A project's zone is the architect's own confirmed statement ("I confirm" in the start box), with the online map recorded only as the suggestion it came from.

## Related documents

Who decides what (architects, Ben) is in [CLAUDE.md](../CLAUDE.md). Every other document is listed in the [docs index](README.md).
