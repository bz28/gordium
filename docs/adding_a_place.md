# Adding a new place

**Purpose:** the steps that take Gordium from the City of Ithaca to a second place (a city, town or village with its own zoning code).\
**For:** engineers adding a place; Ben deciding when one is ready.\
**Kept current by:** any PR that changes what a place needs (a new setting, a new step, an adapter's interface).

A place is mostly **data** (its documents, rules and settings) plus **two pieces of its own code**: how its map services are asked (the lookup adapter) and how its law defines each measurement (the measuring adapter). Everything else is shared, and finds the place through the **registry**: the place's settings file, read by `packages/rule_format/rule_format/place.py`. The chart reader, the drafter, the coverage audit and the Rhino plugin already do; a test (`test_place.py`) fails if shared code names a place's folder or law files.

**Not done yet:** Ithaca's lookup and measuring code still sit in shared folders (`packages/site_lookup/site_lookup/` and `packages/model_measurement/model_measurement/measure.py`), and the lookup still has its own copy of Ithaca's boundary codes (SWIS), coordinate system and address ending. The measuring and lookup steps below describe where they move, so they read those from the settings.

Each numbered folder below is under `regulations/jurisdictions/<state>/<place>/` (lowercase with underscores, e.g. `new_york/ithaca_city`). Folder meanings: [regulations/README.md](../regulations/README.md).

## The checklist, in order

1. **Settings file.** `jurisdiction.yaml` in the place's folder: copy Ithaca's (`regulations/jurisdictions/new_york/ithaca_city/jurisdiction.yaml`) and change every value; each field's comment says what it is for. `python -m rule_format` refuses a file with a missing or unusable field. First, because the steps below read it: extraction finds the chart's district columns with it, and `python -m rule_format` and the coverage audit find the law files by it.
2. **Documents.** The zoning code, its charts and maps, unchanged, in `1_source_documents/`, each listed in `sources.yaml` with its fingerprint (SHA-256), where it came from and when.
3. **Extraction.** `python -m document_extraction` writes `2_extracted_text/` (code, no AI). A new document layout may need the section splitter taught it (`document_extraction/sections.py`).
4. **Section labels.** Each piece of the law labeled Rule / Flag / Reference / Not for checking (`3_section_labels/`). This step uses AI and costs money: **it needs Ben's OK before it runs.** How: [labeling_guide.md](../regulations/document_extraction_guide/labeling_guide.md).
5. **Term definitions.** How this place defines height, story, grade plane, the yards… (`4_term_definitions/`), each with the place's exact words. Then resolve before asking: the whole law, research ranked as in [CLAUDE.md](../CLAUDE.md), then open questions.
6. **Rulebooks.** One file per district in `5_zoning_rules/`, named as the place writes the district. How: [drafting_rules.md](../regulations/document_extraction_guide/drafting_rules.md). `python -m rule_format` checks every quote and example.
7. **Coverage report.** `python -m section_labeling coverage` proves no piece of the law was skipped (`6_coverage_report/`).
8. **Measuring adapter.** The place's own measurement definitions, written by engineers and tested on real models (principle 6, never AI): a folder `packages/model_measurement/model_measurement/places/<name>/` giving the same functions Ithaca's does. Reuse Ithaca's code only where the two laws say the same thing, and say so in a comment citing both.
9. **Lookup adapter.** How the place's map services are asked: a folder `packages/site_lookup/site_lookup/adapters/<name>/` with its own `endpoints.yaml` (each source's store policy decided first: [data sources and permissions](decisions/2026-10-20_data_sources_and_permissions.md)), district names and pending rezonings.
10. **Answer keys and test sites.** Architects' hand-checked rules in `test_data/answer_keys/<state>/<place>/`; real lots with models and expected results in `test_data/test_sites/<state>/<place>/`, worked out by hand from the law, never from Gordium's output.

## Before it reaches architects

- **The Rhino plugin checks one place.** With two places that have settings, the plugin stops with a plain error until it has a place picker (a small change: it reads its place from `design_checker/place.json`, which `python -m rule_format place --write` makes from the settings). Build the picker in the same PR as the second place.
- **Wording.** Some on-screen messages say "the City" (the City's map, the City's tax map). Reword them for a place that isn't a city.
- **Shared measure names.** `packages/rule_format/rule_format/measures.yaml` lists every measure, Ithaca-only ones included (`abuts_r1_district`, `south_hill_overlay`). A second place adds its own there; split it by place if the list grows confusing.
