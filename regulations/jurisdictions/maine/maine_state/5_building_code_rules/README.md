# 5_building_code_rules

The rulebook for this state law: `drafted/general.yaml`, 67 rules for a day-care centre under the 2009 IBC and NFPA 101 (2012), hand-drafted in a Claude Code session (2026-11-20; drafts, approval deferred).

- **IBC rules are all flags** (29, 12 of them keeping a drafted check; 4 for the tables' rows other than I-4 and day care, and Table 508.2.5): the IBC copy is read from OCR only, not verified (`../text_verification.icc.ibc.2009.yaml`), so no IBC rule may pass a design. Where a requirement is measurable, the flag keeps its `check` as the drafted test, and each worked example's `drafted_check` is what that test gives, proved by `python -m rule_format`. When a purchased ICC copy is read a second time, these become rules.
- **NFPA rules** (Chapter 16 new, Chapter 17 existing, and 6.1.14.4: 18 rules, 20 flags) are rules where measurable, using only the second reading's numbers (`../text_verification.gov.law.nfpa.101.2012.yaml`); permissions that turn on sections not brought in, and the 50-ft sprinkler increase of 16.2.6.3 and 17.2.6.3 (a permission the second reading reads as no limit of its own), are flags.
- **Each IBC and NFPA pair** records in its notes that both apply and the stricter governs.
- Rules repeat over parts (`for_each`: story, space, corridor, means_of_egress_door; `rule_format/parts.yaml`), with the building's facts as proposed measures (`drafted/records/proposed_measures.yaml`: occupancy group, sprinkler system, new or existing, client spaces opening outside), stated by the architect.
- Graded against the architect's hand check: `test_data/answer_keys/portland_me_19_libby_st/hand_check.yaml` (`packages/rule_format/tests/test_maine_egress.py`).
