# 5_building_code_rules

The rulebook for this state law: `drafted/general.yaml`, under the 2025 Building Code of New York State, hand-drafted in Claude Code sessions (drafts, approval deferred): 33 for a Group I-4 day-care centre first (2026-11-21), then every row of Tables 1017.2 and 1006.2.1, 1020.5's dead ends and 1016.2's intervening spaces for every occupancy group (2026-11-23: [the plan](../../../../../docs/decisions/2026-11-23_ny_building_egress_all_occupancies.md)), 59 in all.

- **Rules** (34) where the law is measurable: every number stands on the second reading (`../text_verification.yaml`), checked by `python -m rule_format`; a table's rows read by the building's one occupancy group (`occupancy_group`), each chart-matched in `packages/rule_format/tests/test_ny_building_egress_all_occupancies.py`. **Flags** (25) for classification, allowances that loosen a limit, a building of two or more groups (or the tables' rows not drafted yet, where the architect states another occupancy), and what is not measured from the drawing yet.
- Where the law is open, a rule needs review rather than pass (Table 1006.2.1's common path for a space with two exits: README open question 1).
- Rules repeat over parts (`for_each`: story, space, corridor; `rule_format/parts.yaml`), with the building's facts as proposed measures (`drafted/records/proposed_measures.yaml`), stated by the architect.
- Graded against the Maine architect's hand check of a day care, as if built in New York: `packages/rule_format/tests/test_ny_building_egress.py`.
- Run by Check project for buildings the Building Code governs (2026-11-22: `design_checker/code_scope.py`); the four-unit eval building's hand-worked results: `test_data/test_sites/new_york/ithaca_city/four_unit_apartment/expected.yaml`.
