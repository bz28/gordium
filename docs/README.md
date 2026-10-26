# Docs index

**Purpose:** every document in the repository in one list: what each is for, who it is for, and when it changes.\
**For:** anyone looking for the right document.\
**Kept current by:** every PR that adds, moves or removes a document (a test fails if a document is missing here or a link is broken).

New here? Read the [Start here](../README.md#start-here) path first. Words you don't know are in the [glossary](glossary.md).

**One topic, one home.** Each topic is explained in one document; others link to it rather than repeat it. If two documents disagree, the one listed as the topic's home below wins and the other is fixed.

## Online documents

Kept on claude.ai, not in this repository, so they can be read without GitHub.

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [The System Map](https://claude.ai/artifact/BMkp3eyrgemdqcwhi9oFxf) | The one high-level design document: the flow, each stage, the key decisions in one line each, what's open | Everyone | A PR changes the flow or a key decision |
| [How Gordium works, step by step](https://claude.ai/artifact/5LAxAN2qpWFUMDBBDpLQrh) | The flow as plain-English pseudocode, with what is built and what isn't | Everyone who wants the detail behind the map | A step is built or changes |
| [Questions for the Architects](https://claude.ai/artifact/NDesCLC5tfFWDQJq3ah8A9) | The open questions, laid out for the architects to answer | Architects | A question is added, researched or answered |

## Understand: what Gordium is and how it works

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [README.md](../README.md) | The front door: what Gordium is, the reading path, running the tests | Everyone | The reading path or setup changes |
| [CLAUDE.md](../CLAUDE.md) | How we work: the principles, the repository layout, conventions, the review and merge process | Everyone who changes the repository | A working rule changes |
| [glossary.md](glossary.md) | Plain-English definitions of every term the documents use | Everyone | A new term is introduced |
| [demo/README.md](demo/README.md) | Current screenshots and a short animation of Gordium in Rhino | Architects, shareholders | The Rhino screens change |
| [how_gordium_is_built.md](how_gordium_is_built.md) | The code-level map: which package does each step, and how the PRs build on each other | Engineers | A package or step is added or changes |
| [how_rules_are_checked.md](how_rules_are_checked.md) | The promises Gordium makes about its rules, and the check and test behind each | Architects, shareholders, engineers | A rule check is added or changes |
| [methods.md](methods.md) | Every technique: how it works, why, alternatives, weak spots, how it's tested | Engineers, reviewers | A technique is added or changes |

## Use: how to do a job

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [apps/rhino_plugin/QUICKSTART.md](../apps/rhino_plugin/QUICKSTART.md) | Gordium in Rhino from scratch: install once, then your first project step by step | Architects, anyone trying it | A step an architect follows changes |
| [apps/rhino_plugin/README.md](../apps/rhino_plugin/README.md) | The Rhino commands: what each does, what happens on a check, and how we know it works | Engineers, architects trying it | A Rhino command changes |
| [regulations/document_extraction_guide/README.md](../regulations/document_extraction_guide/README.md) | How any regulation document becomes rules; what the guide's files are | Engineers adding a city | The process changes |
| [regulations/document_extraction_guide/drafting_rules.md](../regulations/document_extraction_guide/drafting_rules.md) | How to write a definition or a rule from the law (for AI and people alike) | Anyone drafting rules | A drafting rule changes |
| [regulations/document_extraction_guide/labeling_guide.md](../regulations/document_extraction_guide/labeling_guide.md) | How to label one piece of the law; also the AI labeler's fixed instructions | Anyone labeling | The labeling instructions change |

## Decide: decisions, plans and open questions

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [decisions/2026-10-20_rhino_talks_to_python.md](decisions/2026-10-20_rhino_talks_to_python.md) | Decision: all measuring and checking runs in Gordium's own Python; Rhino only copies the model across and draws the answer | Engineers | The Rhino–Python connection changes |
| [design/rhino_ui_spec.md](design/rhino_ui_spec.md) | The approved build spec for the Rhino screens: every acceptance criterion and how it is verified | Engineers, designers | The Rhino UI's design changes |
| [questions_for_architects.md](questions_for_architects.md) | The questions about the law research couldn't settle | Architects | A question is added, researched or answered |

## Evidence: how we know it's right

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [discrepancies_with_architects.md](discrepancies_with_architects.md) | Where Gordium's reading differs from the architects' 106 Ithaca Rd example, by severity | Architects, Ben | A difference is found or resolved |
| [test_data/README.md](../test_data/README.md) | What the test data is: answer keys and real test sites | Engineers | A kind of test data is added |
| [test_data/answer_keys/new_york/ithaca_city/README.md](../test_data/answer_keys/new_york/ithaca_city/README.md) | The architects' own hand checks of R-1b | Engineers, architects | An answer key is received |
| [test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/README.md](../test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/README.md) | The 106 Ithaca Rd sample site: model, zone, official records | Engineers | The sample site's files change |
| [test_data/.../scenarios/README.md](../test_data/test_sites/new_york/ithaca_city/scenarios/README.md) | Ten R-1b designs with results hand-worked by Claude before Gordium ran, not yet verified by an architect | Engineers, architects | A scenario is added or a disagreement resolved |
| [evidence/pr-15-mvp/rhino-27c8e5d/README.md](evidence/pr-15-mvp/rhino-27c8e5d/README.md) | PR #15's notice and highlight checked in Rhino at 27c8e5d: the notice compact and never over the model, and what failed from the scripts' set-up | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/README.md](evidence/pr-15-mvp/README.md) | The MVP screens checked in Rhino: each scripted check's claims, results and screenshots | Engineers, Ben, architects | A Rhino check of the MVP screens is run again |
| [packages/rule_drafting/evals/2026-10-19_model_choice/README.md](../packages/rule_drafting/evals/2026-10-19_model_choice/README.md) | Eval: which AI model drafts rules well enough (Haiku vs Sonnet) | Engineers, Ben | Never (a dated record) |
| [packages/rule_drafting/evals/2026-10-20_prompt_a/README.md](../packages/rule_drafting/evals/2026-10-20_prompt_a/README.md) | Eval: the rewritten drafting instructions vs the earlier ones | Engineers, Ben | Never (a dated record) |
| [3_section_labels/chapter_325_zoning_2026-10.review.md](../regulations/jurisdictions/new_york/ithaca_city/3_section_labels/chapter_325_zoning_2026-10.review.md) | The labels a person should look at first | Reviewers | Generated by code; never hand-edited |
| [6_coverage_report/chapter_325_zoning_2026-10.md](../regulations/jurisdictions/new_york/ithaca_city/6_coverage_report/chapter_325_zoning_2026-10.md) | Proof every line of the law is in exactly one labeled piece | Architects, reviewers | Generated by code; never hand-edited |

## Reference: one page per package and per step

**Packages** (the code, one folder per job):

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [rule_format](../packages/rule_format/README.md) | The shape of a rule, the formula language, and the inspector that checks rule files | Engineers | The rule format changes |
| [document_extraction](../packages/document_extraction/README.md) | Step 2: every line of every PDF with its page and position; the chart reader | Engineers | Extraction changes |
| [section_labeling](../packages/section_labeling/README.md) | Step 3: cut the law into pieces, label each, prove nothing was skipped | Engineers | Labeling changes |
| [rule_drafting](../packages/rule_drafting/README.md) | Step 5: AI drafts rules for every district; code checks every draft | Engineers | Drafting changes |
| [rule_export](../packages/rule_export/README.md) | The rules spreadsheet people read, with links to the City's words | Engineers | The spreadsheet changes |
| [project_report](../packages/project_report/README.md) | A project's compliance report in the architects' own spreadsheet format | Engineers | The report changes |
| [model_measurement](../packages/model_measurement/README.md) | Measures a Rhino model the way the City defines each measurement (lot, yards, building area, height) | Engineers | A measurement is added or changes |
| [envelope_builder](../packages/envelope_builder/README.md) | The largest building the rules allow on a lot (the envelope) | Engineers | The envelope changes |
| [design_checker](../packages/design_checker/README.md) | Checks a design in one call: measure, run the zone's rules, work out the envelope | Engineers | The check changes |

**Regulation steps** (the data for each city, in numbered steps):

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [regulations/README.md](../regulations/README.md) | What the regulations folder holds and how its steps are numbered | Everyone | The steps change |
| [City of Ithaca](../regulations/jurisdictions/new_york/ithaca_city/README.md) | Which Ithaca (the City, not the Town) and which districts | Everyone | Scope changes |
| [1_source_documents](../regulations/jurisdictions/new_york/ithaca_city/1_source_documents/README.md) | The City's original documents, never edited, with fingerprints | Engineers | A document is added or replaced |
| [2_extracted_text](../regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/README.md) | The text pulled from those documents (generated) | Engineers | Extraction changes |
| [3_section_labels](../regulations/jurisdictions/new_york/ithaca_city/3_section_labels/README.md) | What kind of text each piece of the law is | Engineers, reviewers | Labels change |
| [4_term_definitions](../regulations/jurisdictions/new_york/ithaca_city/4_term_definitions/README.md) | How Ithaca defines the words its rules depend on | Engineers, architects | A definition changes |
| [5_zoning_rules](../regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/README.md) | The rulebook: one file per district | Engineers, architects | The rule fields change |
| [6_coverage_report](../regulations/jurisdictions/new_york/ithaca_city/6_coverage_report/README.md) | What the coverage report proves | Reviewers | The report changes |
| [7_published_rulebooks](../regulations/jurisdictions/new_york/ithaca_city/7_published_rulebooks/README.md) | Frozen rulebook versions (not built yet) | Engineers | Freezing is built |
