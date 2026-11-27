# New York's Building Code Chapter 4, the parts that change the means of egress: the plan (2026-11-26)

**Purpose:** how Gordium brings in the sections of Chapter 4 (special detailed requirements based on occupancy and use) of the 2025 Building Code of New York State that change Chapter 10's means of egress: which sections, what is a rule and what a flag, the building facts each reads, and the order of work.\
**For:** engineers extending `new_york_state_building/`; Ben (scope, order); reviewers of each part's PR.\
**Kept current by:** the engineer who drafts a part, in that same branch (the part's status line below).

Follows [Chapter 10 for every occupancy group](2026-11-23_ny_building_egress_all_occupancies.md), whose pipeline each part reuses: the pieces brought in (`sources.yaml`), every number read a second time from the page images (`text_verification.yaml`), labels, a rule or a flag for each piece labeled one, the coverage report, the four-unit apartment's check before and after.

## What Chapter 4 does to egress

Chapter 4 adds requirements for particular buildings and uses: a covered or open mall (402), a high-rise (403), an atrium (404), an underground building (405), Groups I-2 and I-3 (407, 408), stages and platforms (410), special amusement areas (411), aircraft-related occupancies (412), Groups I-1 and R (420), ambulatory care facilities (422) and others. Most of what these sections ask is not in the model Gordium reads (a mall's width between kiosks, a smoke compartment's size, a stair's smokeproof enclosure), so most are **flags**: a person's check, shown only where the building may be that use. A section becomes a **rule** only where the measures that exist settle it.

## Decisions

1. **One block in the one rulebook.** The checker reads one rulebook per law folder (`rule_format.rulebook.building_code_rulebook`, `Place.inherited_rulebooks`, `design_checker/egress.py` `laws`), so Chapter 4's rules are their own block in `drafted/general.yaml`, just before `general.bc_508_2_1_classification` (after the 308.5 rules), so its changes and Chapter 10's (appended at the end) never touch the same lines. Labels and second readings go in book order.
2. **Each flag shows only where the building may be that use** (`applies_when`), read from a stated fact: the building's occupancy group (`occupancy_group`), the atrium (`building_has_atrium`), and a space with its own exits or travel limit (`special_egress_spaces`, whose words already name a covered or open mall, 402.8, and a special amusement area, 411). A fact not stated shows the flag: what the law leaves open never passes. Where no fact says it, a new stated fact is added and put on the Revit-fields queue.
3. **A section that tightens a Chapter 10 limit a rule passes on** (a mall tenant's 200 ft and its second exit at 75 ft or 50 occupants, 402.8.3 and 402.8.5) is held by a review on that rule wherever the building may be that use; the sweep is part of each part's review.

## Parts, in order

- **a. Malls and atriums:** 402.1 with 402.1.1, 402.8 whole; 404.1, 404.9 to 404.11.
- **b. High-rise and underground buildings:** 403.1, 403.2.2, 403.5, 403.6; 405.1, 405.4.1, 405.7.
- **c. Group I-2:** 407.2 to 407.6, 407.10.
- **d. Group I-3, Groups I-1 and R, ambulatory care:** 408.3, 408.4, 408.6, 408.8; 420; 422.3.
- **e. The rest:** 406.4.3 and 406.5.7 (parking garages), 410.5 (stages and platforms), 411.4 (special amusement areas), 412 (aircraft-related), 415.11.3 and 415.11.6 (Group H-5), 428.3.5 (laboratories).

## Status

- **a.** In progress (2026-11-26).
