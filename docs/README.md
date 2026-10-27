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
| [apps/rhino_plugin/GUIDE.md](../apps/rhino_plugin/GUIDE.md) | The user guide: every screen, button and question in Gordium in Rhino, in plain words | Architects | Any button, tick box, command or prompt changes (a test fails until it is updated) |
| [apps/rhino_plugin/README.md](../apps/rhino_plugin/README.md) | The Rhino commands: what each does, what happens on a check, and how we know it works | Engineers, architects trying it | A Rhino command changes |
| [regulations/document_extraction_guide/README.md](../regulations/document_extraction_guide/README.md) | How any regulation document becomes rules; what the guide's files are | Engineers adding a city | The process changes |
| [regulations/document_extraction_guide/drafting_rules.md](../regulations/document_extraction_guide/drafting_rules.md) | How to write a definition or a rule from the law (for AI and people alike) | Anyone drafting rules | A drafting rule changes |
| [regulations/document_extraction_guide/labeling_guide.md](../regulations/document_extraction_guide/labeling_guide.md) | How to label one piece of the law; also the AI labeler's fixed instructions | Anyone labeling | The labeling instructions change |

## Decide: decisions, plans and open questions

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [decisions/2026-10-20_rhino_talks_to_python.md](decisions/2026-10-20_rhino_talks_to_python.md) | Decision: all measuring and checking runs in Gordium's own Python; Rhino only copies the model across and draws the answer | Engineers | The Rhino–Python connection changes |
| [design/rhino_ui_spec.md](design/rhino_ui_spec.md) | The approved build spec for the Rhino screens: every acceptance criterion and how it is verified | Engineers, designers | The Rhino UI's design changes |
| [decisions/2026-10-20_data_sources_and_permissions.md](decisions/2026-10-20_data_sources_and_permissions.md) | Decision: which map services the address lookup asks, what we may store from each, when permission emails are needed; how Gordium compares with an architect's due diligence | Ben, engineers | A source is added or a permission answer arrives |
| [plans/product_plan_draft.md](plans/product_plan_draft.md) | DRAFT: how Gordium reaches customers (install, sign-in, what runs where, what it takes to build) | Ben | Ben reacts; each choice then becomes a decision |
| [plans/known_gaps_vs_practice.md](plans/known_gaps_vs_practice.md) | What architects look into on a real project that Gordium doesn't yet, each with a proposed next step | Ben, architects, shareholders | A gap is closed or found |
| [decisions/2026-10-21_fails_whatever_the_missing_number.md](decisions/2026-10-21_fails_whatever_the_missing_number.md) | Decision: a rule that fails for every value a missing number could take does not comply (proven from the formula, never sampled); missing data never complies | Architects, engineers | Rule-checking changes |
| [decisions/2026-10-21_eaves_need_confirmation.md](decisions/2026-10-21_eaves_need_confirmation.md) | Decision: Gordium never decides on its own that an overhang is an eave; one inside a required yard needs review until the architect marks it as eaves | Architects, engineers | Overhang measurement changes |
| [questions_for_architects.md](questions_for_architects.md) | The questions about the law research couldn't settle | Architects | A question is added, researched or answered |

## Evidence: how we know it's right

| Document | Purpose | For whom | Updated when |
|---|---|---|---|
| [discrepancies_with_architects.md](discrepancies_with_architects.md) | Where Gordium's reading differs from the architects' 106 Ithaca Rd example, by severity | Architects, Ben | A difference is found or resolved |
| [test_data/README.md](../test_data/README.md) | What the test data is: answer keys and real test sites | Engineers | A kind of test data is added |
| [test_data/answer_keys/new_york/ithaca_city/README.md](../test_data/answer_keys/new_york/ithaca_city/README.md) | The architects' own hand checks of R-1b | Engineers, architects | An answer key is received |
| [test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/README.md](../test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/README.md) | The 106 Ithaca Rd sample site: model, zone, official records | Engineers | The sample site's files change |
| [research/2026-10-20_architect_questions.md](research/2026-10-20_architect_questions.md) | The research behind every finding and still-open question: what was searched, the sources, what each settled | Anyone checking a reading of the law; architects | Never (a dated record); new research gets its own report |
| [test_data/.../106_ithaca_rd/gis/README.md](../test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/gis/README.md) | The official lot outlines of 106 Ithaca Rd, with their terms of use, compared with the architects' lot | Engineers, architects | An outline is re-measured |
| [test_data/.../scenarios/README.md](../test_data/test_sites/new_york/ithaca_city/scenarios/README.md) | Ten R-1b designs with results hand-worked by Claude before Gordium ran, not yet verified by an architect | Engineers, architects | A scenario is added or a disagreement resolved |
| [evidence/pr-27/rhino-ea88c18/README.md](evidence/pr-27/rhino-ea88c18/README.md) | PR #27's Check button checked in Rhino at ea88c18: the one-script run against the phased run across real idle | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-23/README.md](evidence/pr-23/README.md) | PR #23's in-Rhino evidence: the neighbourhood map around a looked-up lot, each claim asserted by a script | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-19/README.md](evidence/pr-19/README.md) | PR #19's in-Rhino evidence: the start box, the address lookup and live mode, each claim asserted by a script | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-26/rhino-cb4b6e0/README.md](evidence/pr-26/rhino-cb4b6e0/README.md) | PR #26's in-Rhino evidence: re-lookup (Look up previews, Draw replaces, Keep my building), Undo and Redo of a Draw, and the undo probe | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15/rhino-8bfabdd/README.md](evidence/pr-15/rhino-8bfabdd/README.md) | PR #15 checked in Rhino at 8bfabdd: highlight 19 of 19, notice 5 of 5, timing 4 of 5 (one pass at every stop, 2 stops over 80 ms); no jump, labels pop in; the axis icon needs about 76 x 75 px, not 72 | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15/rhino-5b46c99/README.md](evidence/pr-15/rhino-5b46c99/README.md) | PR #15 checked in Rhino at 5b46c99: highlight 19 of 19, notice 5 of 5 as written; settle ticks up to 22 ms, 1-6 ticks, 9-71 ms; the labels still jump when the view stops | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15/rhino-822fb6f/README.md](evidence/pr-15/rhino-822fb6f/README.md) | PR #15 checked in Rhino at 822fb6f: highlight 19 of 19 (a script index fixed), notice 5 of 5; label work 0 ms a frame, but a settle tick takes up to 309 ms and the labels jump when the view stops | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/rhino-4bb6d4d/README.md](evidence/pr-15-mvp/rhino-4bb6d4d/README.md) | PR #15 checked in Rhino at 4bb6d4d: label placement 18 of 19 (the front yard label hidden under the SW label); zooming Top with labels on about 500 ms a frame | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/rhino-319dc5d/README.md](evidence/pr-15-mvp/rhino-319dc5d/README.md) | PR #15 checked in Rhino at 319dc5d: the highlight in full; the southwest label clear of the front yard's dimension, now on the house | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/rhino-a31661e/README.md](evidence/pr-15-mvp/rhino-a31661e/README.md) | PR #15 checked in Rhino at a31661e: the bend question needs a Yes or a No (Enter asks again, Esc changes nothing); pass 2 in full | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/rhino-81efd62/README.md](evidence/pr-15-mvp/rhino-81efd62/README.md) | PR #15 checked in Rhino at 81efd62: the highlight and the notice in full; the failing side yard's label right beside its line | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/rhino-a9a9a45/README.md](evidence/pr-15-mvp/rhino-a9a9a45/README.md) | PR #15 checked in Rhino at a9a9a45: highlight and pass 2 in full; the notice not drawn in the real docked Top view | Reviewers, engineers | Never (a dated record) |
| [evidence/pr-15-mvp/rhino-6361a3f/README.md](evidence/pr-15-mvp/rhino-6361a3f/README.md) | PR #15 checked in Rhino at 6361a3f: pass 2, the notice and the highlight, once each frame is drawn before it is read | Reviewers, engineers | Never (a dated record) |
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
| [site_lookup](../packages/site_lookup/README.md) | Type an address, get the site: the lot, street side, corner lot, ground and a zoning suggestion, each with its source | Engineers | The lookup changes |
| [model_measurement](../packages/model_measurement/README.md) | Measures a Rhino model the way the City defines each measurement (lot, yards, building area, height) | Engineers | A measurement is added or changes |
| [envelope_builder](../packages/envelope_builder/README.md) | The largest building the rules allow on a lot (the envelope) | Engineers | The envelope changes |
| [design_checker](../packages/design_checker/README.md) | Checks a design in one call: measure, run the zone's rules, work out the envelope | Engineers | The check changes |
| [the stress test](../packages/design_checker/tests/stress/README.md) | Simulated design edits, each compared with an independent answer key (never a false pass); its two sample sizes | Engineers | The stress test changes |

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
