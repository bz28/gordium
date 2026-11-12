# New York State's own law

Law that every New York place inherits (a place lists this folder in its `jurisdiction.yaml` under `inherits:`; Ithaca does). It is not a place: its settings file is `state.yaml`, not `jurisdiction.yaml`, so the place registry and the Rhino plugin never treat it as one. Why, and how: [docs/decisions/2026-11-12_building_code_text.md](../../../../docs/decisions/2026-11-12_building_code_text.md).

- **The book:** the 2025 Residential Code of New York State (one- and two-family houses and townhouses up to three stories), in force since 2025-12-31.
- **Brought in so far (egress step 1):** R318 means of egress, R319 emergency escape and rescue openings, R320 handrails, R321 guards and window fall protection, R325.6 and R325.7 (stairway lighting, which R318.7.10 requires), R201 (how definitions apply), and every Section R202 definition those use. No rules yet.
- **Copyright:** the book is ICC's. The repo keeps only short exact quotes with their section, page and a link; the book and its text are in the code cache outside the repo (`1_source_documents/sources.yaml` says where and why). Where the cache is missing (CI), the checks that need the text are skipped and say so.
- **`text_verification.yaml`:** every number in the brought-in pieces, read a second time from the page images by a reader who never saw the extracted text, and whether the two readings agree (all 167 pieces agree). Everything is **verified against the Public.Resource.Org copy only; check against an exact copy bought from ICC**.

See `regulations/README.md` for what each numbered step means. There is no `5_zoning_rules/` yet: egress rules come in a later step.

## References in the brought-in sections that are not brought in

Every reference in the brought-in sections was followed (found by code: each "Section", "Table", "Appendix" and standard named). Those inside R318-R321 and R325.6 are brought in. These are not, each judged not to be egress (a material, structural, plumbing, electrical-supply or existing-building matter):

- R507.2.2 (plastic composite treads, handrails and guards: materials; from R318.7.5.4, R320.7, R321.1.4)
- R101.2 Exception 6 (which lodging houses the code covers; from R318.1.1)
- P2904 (sprinkler systems; from R319.1 Exception 3)
- R405.1 and Table R401.4.1(2) (foundation drainage and soils; from R319.4.3)
- Appendix BO (alterations and repairs of existing basements; from R319.7)
- E3401.2.1 (when a house has electrical power; from the exceptions of R325.6 and R325.7)
- the outside standards ICC 500 (storm shelters; R319.1) and ASTM F2090 (window opening control devices; R319.1.1, R321.2.1)
- "accessed", printed in italics but not defined in Section R202: R201.3 sends such a word to another New York code's definition; that code is not brought in.
- "unit" in R319.1 is printed in italics alone only because the book breaks the styling inside "dwelling *unit*" (p.102, line 35); the term is DWELLING UNIT, and its definition is brought in by the roman-type match.

## Ways into these sections from outside them

- R316.4 (habitable attics, p.99, not brought in) applies "the applicable provisions of Section R318" to habitable attics. Which attics count is for a later step.
