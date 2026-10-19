# Answer keys — City of Ithaca

The architects' own hand checks, and our rules written to compare against them.

- `Gordium_Single_Family_Simple_v1.xlsx` — the architects' R-1b check for 106 Ithaca Road (received 2026-10-17, unedited). Sheets: **Inputs** (lot, house and R-1b table values with page references) and **Output** (each requirement: limit, proposed, PASS/FAIL). All its limits match the April 2026 zoning charts (p.3 dimensions, p.14 parking; checked 2026-10-19). It does not cover chart footnote 10 (height: see §325-16).
Our own R-1b rules are not here: they're a draft in the rulebook, `regulations/jurisdictions/new_york/ithaca_city/5_zoning_rules/R-1b.yaml` (drafted by Claude, not yet approved by the architects).

**How R-1b is compared with the architects:** `test_sites/new_york/ithaca_city/106_ithaca_rd/spreadsheet_design.yaml` turns the spreadsheet's design into our measurements, naming the cell each one comes from. The test `packages/rule_format/tests/test_answer_keys.py` reads the spreadsheet itself, checks every measurement against its cells, runs our draft R-1b rules, and requires our PASS/FAIL to equal theirs on all 11 rows. Today they all match, including coverage FAIL.

Errors found in the spreadsheet: see `docs/discrepancies_with_architects.md` (section 2).
