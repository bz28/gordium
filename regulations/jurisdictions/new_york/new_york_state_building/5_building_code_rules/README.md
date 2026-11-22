# 5_building_code_rules

The rulebook for this state law: `drafted/general.yaml`, 30 rules for a Group I-4 day-care centre first, under the 2025 Building Code of New York State, hand-drafted in a Claude Code session (2026-11-21; drafts, approval deferred).

- **Rules** (10) where the law is measurable: every number stands on the second reading (`../text_verification.yaml`), checked by `python -m rule_format`. **Flags** (20) for classification, allowances that loosen a limit, the tables' rows for other groups (shown where the architect states another occupancy), and what is not measured from the drawing yet.
- Where the law is open, a rule needs review rather than pass (Table 1006.2.1's common path for a space with two exits: README open question 1).
- Rules repeat over parts (`for_each`: story, space, corridor; `rule_format/parts.yaml`), with the building's facts as proposed measures (`drafted/records/proposed_measures.yaml`), stated by the architect.
- Graded against the Maine architect's hand check of a day care, as if built in New York: `packages/rule_format/tests/test_ny_building_egress.py`.
