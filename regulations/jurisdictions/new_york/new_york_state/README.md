# New York State's own law

Law that every New York place inherits (a place lists this folder in its `jurisdiction.yaml` under `inherits:`; Ithaca does). For now the link is declared and checked; nothing reads this folder's law into a place's check yet, since there are no egress rules yet. It is not a place: its settings file is `state.yaml`, not `jurisdiction.yaml`, so the place registry and the Rhino plugin never treat it as one. Why, and how: [docs/decisions/2026-11-12_building_code_text.md](../../../../docs/decisions/2026-11-12_building_code_text.md).

- **The book:** the 2025 Residential Code of New York State (one- and two-family houses and townhouses up to three stories), in force since 2025-12-31.
- **Brought in so far (egress step 1):** R318 means of egress, R319 emergency escape and rescue openings, R320 handrails, R321 guards and window fall protection, R325.6 and R325.7 (stairway lighting, which R318.7.10 requires), R201 (how definitions apply), and every Section R202 definition those use. No rules yet.
- **Copyright:** the book is ICC's. The repo keeps only short exact quotes with their section, page and a link; the book and its text are in the code cache outside the repo (`1_source_documents/sources.yaml` says where and why). Where the cache is missing (CI), the checks that need the text are skipped and say so.
- **`text_verification.yaml`:** every number in the brought-in pieces, read a second time from the page images by a reader who never saw the extracted text, and whether the two readings agree (all 169 pieces agree). Everything is **verified against the Public.Resource.Org copy only; check against an exact copy bought from ICC**.

See `regulations/README.md` for what each numbered step means. There is no `5_zoning_rules/` yet: egress rules come in a later step.

## References in the brought-in sections that are not brought in

Every reference in the brought-in sections was followed (found by code, `document_extraction/icc_references.py`: each section, table, appendix, chapter and standard a brought-in piece names; `python -m document_extraction.icc_references` lists them again where the code cache has the book). Those inside R318-R321, R325.6 and R325.7 are brought in. These are not: all but one are a material, structural, plumbing, electrical-supply or outside-standard matter; Appendix BO is egress law, but for work on existing buildings, which is for a later step:

- R507.2.2 (plastic composite treads, handrails and guards: materials; from R318.7.5.4, R320.7, R321.1.4)
- R101.2 Exception 6 (which lodging houses the code covers; from R318.1.1)
- P2904 (sprinkler systems; from R319.1 Exception 3)
- R405.1 and Table R401.4.1(2) (foundation drainage and soils; from R319.4.3)
- Appendix BO (existing buildings; from R319.7): it holds egress law for alterations (BO105.8 means of egress, BO105.10 stairs, handrails and guards, BO105.11 escape openings, pp.968-973). Gordium checks new work only until it is brought in
- E3401.2.1 (when a house has electrical power; from the exceptions of R325.6 and R325.7)
- the outside standards ICC 500 (storm shelters; R319.1) and ASTM F2090 (window opening control devices; R319.1.1, R321.2.1)
- "accessed", printed in italics but not defined in Section R202: R201.3 sends such a word to another New York code's definition; that code is not brought in.
- "unit" in R319.1 is printed in italics alone only because the book breaks the styling inside "dwelling *unit*" (p.102, line 35); the term is DWELLING UNIT, and its definition is brought in by the roman-type match.
- "above" in the definition of STORY ABOVE GRADE PLANE is printed in italics with "grade plane" in item 1 (p.52, line 36), though the line above prints only "grade plane" in italics; the term is GRADE PLANE, brought in, and "above" keeps its ordinary meaning.

## What the book's text gets wrong

- **R318.7.1's metric conversions** (p.100, line 25): "31 1/2 inches (787 mm)" and "27 inches (698 mm)"; 31 1/2 inches is 800 mm and 27 inches is 686 mm. Gordium's reading: the inches govern, the millimetres being a conversion printed after them; a reading for the architects to confirm before a rule is drafted from these widths. The label's notes say so, and a test (`rule_format/tests/test_state_law.py`, where the code cache is) finds every "inches (mm)" pair in the brought-in pieces that does not convert and requires its label's notes to name it.

## Ways into these sections from outside them

Found by the same code: the whole book (all 1,079 pages, read once by the same extractor into the code cache, `gov.ny.residential.2025.full.jsonl`) searched for R318, R319, R320, R321, R325.6 and R325.7 outside the brought-in pieces, leaving out the table of contents (p.16), the list of standards (p.852) and the index (pp.1070-1076), which only list section numbers. None of these is brought in yet; each changes or extends what the brought-in sections apply to:

- R314.4 mezzanines (p.97): their means of egress follows R318.
- R315.5 sleeping lofts (p.98): R318 "as modified by" R315.5.1 to R315.5.3, with their own stair, landing and ladder limits. A house with a sleeping loft needs these before its loft stair can be checked.
- R316.4 habitable attics (p.99): "the applicable provisions of Section R318".
- R324.4.7 glazing beside the bottom stair landing (p.107): an exception for glass protected by a guard that meets R321.
- R502.3.1 floor joists (p.166): attics reached by a fixed stairway per R318.7 (a structural load matter).
- R507.10 deck guards (p.204): R321.
- M1602.1 outdoor air openings (p.529): refers to R325.6.
- Appendix BB tiny houses (pp.880-881): loft stairs, landings, handrails, ladders, guards and escape openings, modifying R318-R321.
- Appendix BF patio covers (p.898): exits per R318.
- Appendix BO existing buildings (pp.965-973): see above.
