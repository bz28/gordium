# New York's Building Code egress for every occupancy group: the plan (2026-11-23)

**Purpose:** how Gordium turns Chapter 10 (Means of Egress) of the 2025 Building Code of New York State into checkable rules for every occupancy group, not only Group I-4: which sections, which table rows, what is a rule and what a flag, the building facts they read, and the order of work.\
**For:** engineers extending `new_york_state_building/`; Ben (scope, order); reviewers of each section group's commits.\
**Kept current by:** the engineer who drafts a section group, in that same branch (the group's status line below).

Follows [the Building Code's first step](2026-11-21_ny_building_code.md) (Group I-4 only) and [which New York code](2026-11-22_which_ny_code.md). Ben, 2026-11-23: every occupancy, starting with the four-unit apartment (Group R-2), offices (B), shops (M), assembly (A) and schools (E).

## What the existing measures can already check, for any occupancy

The route measuring (`model_measurement/routes`) gives, per story: exit count, exit access travel distance, the remoteness ratio and the story's areas; per space (each room not a corridor): its exit access doorways, its common path, the remoteness of its doorways, the rooms its path crosses; per corridor: width and dead ends. Facts the model can't show are the architect's, in the interior description's `building` block (occupancy groups, sprinkler system). What that supports with no new measure:

| Requirement | Measures | New measure needed |
|---|---|---|
| 1006.2.1 and Table 1006.2.1, every row: a space's second exit by occupant load and common path | `space_exit_count`, `space_common_path`, `space_occupant_load` | none (the occupant load is stated or, from step 2, computed) |
| 1017.2 and Table 1017.2, every row: travel distance | `egress_travel_distance` | none |
| 1020.5 and its exceptions, every group: dead ends | `corridor_dead_end_length`, `corridor_dead_end_least_width` | none |
| 1007.1 exit separation, every group, where two are required | `exit_remoteness_ratio`, `space_exit_remoteness_ratio` | none (needs the "how many are required" of 1006.2.1 and 1006.3 per group) |
| 1006.3.3 and 1006.3.4, Tables 1006.3.4(1) and (2): a story's exits | `story_exit_count`, `story_occupant_load`, `egress_travel_distance`, `story_first_above_or_below_grade` | the story's number above grade plane; Group R-2's dwelling units per story (stated) |
| 1020.3 and Table 1020.3: corridor width | `corridor_width`, `corridor_occupant_load` | none (the occupant load stated, later computed) |
| 1004.5 and Table 1004.5: occupant load | none today | each room's function (Table 1004.5's list, stated) and its floor area (gross and net readings) |
| 1005.3 egress capacity | none today | each exit's and door's clear width along the route, the load it serves |
| 1010 doors, 1011 stairs, 1014 handrails, 1015 guards | the house measuring's door, stair, handrail and guard parts (`model_measurement/interior`) | the Building Code check must read those parts too (today it reads only the routes) |
| 1031 emergency escape and rescue (Group R-2, R-3, R-4, I-1) | the house measuring's escape openings | as above |

Note: in this book Section 1030 is **Assembly** and **1031 is Emergency Escape and Rescue** (pp.353, 359).

## Decisions

1. **One building fact, `occupancy_group`: the building's one group, or `mixed`.** From the `building` block's `occupancy_groups` (code_scope.building_measures): one group stated gives that group (`R-2`); two or more give `mixed`; none stated, left out (every rule that reads it needs review). A text measure with its list of values in `proposed_measures.yaml` (`values:`). `occupancy_group_i4` and `other_occupancy_present` stay, so the I-4 rules read as before.
2. **A rule per printed table row**, its id naming the table (`general.bc_table_1017_2_b`), its quote the row's own line, `applies_when: occupancy_group in [the row's groups]`. Each row is chart-matched by a test: every column passes at its limit and fails just past it, page cited. The I-4 rows stay the existing I-4 rules (no verdict of theirs changes).
3. **A mixed building is a person's check** (1004.4: each portion by its own occupancy; a shared component meets the most stringent): the row rules are not applicable to `mixed`, and one flag per table says so. Per-room occupancy marks would let a mixed building be checked by portion: a later step.
4. **Footnotes:** a footnote that tightens a cell is in the check; one that loosens it under a condition the model can't show is a `review_when` (never a pass on it) or a flag. A condition the architect can state (the sprinkler system) is a fact; one not stated needs review. Fact added: `assembly_fixed_seating` (Table 1006.2.1 note c: 1030.8; Table 1017.2 note a: 1030.7), stated in the `building` block. An NFPA 13D system (903.3.1.3) is neither 903.3.1.1 nor 903.3.1.2, so it gets the columns without a sprinkler system (Table 1017.2 note e says the same for R-3 and R-4); where Table 1006.2.1 note g sends it elsewhere (1006.2.2.6), the R-3 and R-4 row needs review.
5. **The "other occupancies" flags are narrowed** to `occupancy_group == "mixed"` (or to their own group: 1017.2.2 to F-1 and S-1, 1017.2.3 to H-5) as each table's rows are drafted, so only what is not drafted falls back to needs review.
6. **What the law leaves open never passes**, as for I-4: Table 1006.2.1's common path over the row's value in a space with two exits needs review (README open question 1, now for every row).

## Section groups, in order

Each group: its pieces brought in (`sources.yaml`, extracted, labeled, definitions by italics, every number read a second time from the page images), its rules and flags, the chart-match tests, worked examples per occupancy, the coverage report regenerated, the four-unit apartment's check run before and after.

1. **Rows of the tables already brought in** (no new pieces): Table 1006.2.1 (every row: common path and a space's one exit), Table 1017.2 (every row: travel distance), 1020.5 (dead ends, exceptions 1 to 4 for every group). Status: drafted 2026-11-23: 23 rules (10 rows of Table 1017.2, 12 of Table 1006.2.1, 1020.5 for every group but I-4) and 2 flags (Table 1017.2 note a's other sections, always shown; Group H's sprinkler system), five other-occupancy flags narrowed; a space that is itself an exit (`space_is_exit`, a stair enclosure entered by its exit door) is not one Table 1006.2.1 counts; chart-matched in `packages/rule_format/tests/test_ny_building_egress_all_occupancies.py`. The Building Code check now reads an unstated fact as unknown, as the rules' worked examples do (`design_checker/egress.py` `_law_values`), so a travel distance within every limit isn't held for an increase it doesn't need. It also settles two I-4-era rules where the answer is the same whatever the unstated facts are: a space with one exit access doorway passes 1007.1.1's and 1007.1.2's separation rules (`space_exit_count < 2 or ...`) with no occupancy or sprinkler system stated (the four-unit apartment's check as sent, with no building block: 2 pass, before none). The four-unit apartment (R-2, no sprinkler system): travel 53.95 ft passes (200 ft), no dead end, each apartment's one door fails (R-2 row: Not Permitted without a sprinkler system).
2. **1006.3, 1007 and 1016.2 for every group:** 1016.2 (intervening spaces) drafted 2026-11-23 for every group but I-4 (`general.bc_1016_2_intervening_spaces_other_groups`: item 6's exceptions, a kitchen of the same dwelling or sleeping unit and a Group M stockroom, need review where they are all that fails), its flag narrowed to a mixed building. Still to do: Table 1006.3.4(1) (Group R-2 dwelling units) brought in; 1006.3.3's single-exit allowance and 1007.1's "where two are required" read every row of Tables 1006.3.4(1) and (2).
3. **1004 occupant load:** 1004 and Table 1004.5 brought in; a room's function (stated) and floor area (two readings, inside its walls and to their outer faces) give a computed occupant load, never less than Table 1004.5's (1004.5), used where none is stated.
4. **1020 corridors:** 1020.1 to 1020.7, Tables 1020.2 and 1020.3 brought in: width by occupancy and occupant load (a rule), fire-resistance rating (stated rating against the table), continuity and air movement (flags).
5. **1005 egress width:** 1005.3.1 and 1005.3.2 capacity factors (0.3 and 0.2 inch per occupant; 0.2 and 0.15 with a sprinkler system and an emergency voice/alarm system, a stated fact), 1005.5 distribution, 1005.7 encroachment.
6. **1010 doors:** size (1010.1.1), swing (1010.1.2.1), landings, hardware and panic hardware by occupant load; the Building Code check reads the interior measuring's door parts.
7. **1011 stairs, 1014 handrails, 1015 guards:** width, risers and treads, headroom, handrail and guard heights and openings, by occupancy (the dwelling-unit exceptions included).
8. **1031 emergency escape and rescue:** where required (Groups R-2 per 1006.3.4, R-3, R-4, I-1), size and operation, from the escape-opening parts.
9. **The rest of Chapter 10** (1003 general, 1008 illumination, 1009 accessible egress, 1012 ramps, 1013 signs, 1016, 1018 aisles, 1019, 1021 to 1030): rules where measured, flags otherwise.

## Order and why

Group 1 first: the measures exist, the tables are already read twice, and it gives the apartment its first real verdicts (travel distance, a dwelling unit's one exit, dead ends). Then group 2 (the apartment's story exits and separation), then the occupant load (group 3), which every load-based limit waits on. The rest follow the parts the measuring gives.

## Review round 1 (2026-11-23): what tightens a table for some condition

Two P0 findings (a fixed-seat assembly space passing on Table 1006.2.1's 75 ft; Group R-3 and R-4 with an NFPA 13D system passing Table 1017.2's 200 ft) and one P1 (a horizontal exit made the room beyond it an exit) led to a sweep of every footnote and cross-reference of the drafted tables, and of the sections elsewhere that tighten them. Each is now encoded where measured, or a review wherever its condition is stated or not ruled out; none falls back on the looser table value. `test_every_cross_reference_in_a_drafted_piece_has_a_handler` lists each with its handler, so a reference added without one fails.

| Where | Tightens | Handled by |
|---|---|---|
| Table 1006.2.1 note c, 1030.8 (brought in) | a room used for assembly purposes with fixed seating, in any group (303.1.1 to 303.1.3: an E school's auditorium, a B lecture hall): 30 ft from any seat (75 ft under 50), any number of exits | every Table 1006.2.1 row (and Group I-4's) needs review over it where `assembly_fixed_seating` is yes or not stated (seats aren't drawn); flag `bc_1030_8_...` on the fact alone |
| 1018.4 (brought in) | Group M merchandise pads: 30 ft from any point in a pad (75 ft for 50 or fewer) | the row needs review over it where `merchandise_pads` is yes or not stated; flag `bc_1018_4_...` |
| Table 1017.2 note e, 1006.2.2.6 (brought in) | Groups R-3 and R-4 with NFPA 13D: 125 ft and 75 ft | the row's limit, and rule `bc_1006_2_2_6_...`; new fact `sprinklered_903_3_1_3` |
| 1006.2.2.1 to 1006.2.2.5 (brought in) | boiler, refrigeration, refrigerated and electrical rooms: two exits; refrigeration rooms 150 ft unsprinklered | a one-exit space within its row needs review, and every travel row, where `special_egress_spaces` is yes or not stated; five flags |
| Table 1017.2 note a: 402.8 malls (200 ft), 411.2 special amusement areas, 412.6 aircraft, 3103.4 temporary structures (100 ft), 3104.9 walkways (200 ft) | each its own distance | every travel row needs review where `special_egress_spaces` is yes or not stated |
| note a: 407.4 (Group I-2) | 407.4.2: 50 ft within a sleeping room (brought in); 407.4.4 care suites | rule `bc_407_4_2_...` and the I-2 travel row (over 50 ft: review); care suites are `special_egress_spaces`'; 1016.2 needs review for I-2 with care suites not ruled out (407.4.4.1) |
| note a: 408.6.1, 408.8.1 (Group I-3) | smoke-barrier doors within 150 and 200 ft | the I-3 travel row never passes; 1016.2 needs review for I-3 (408.6.3) |
| 1017.3.2.3 | 200 ft within an atrium | rows allowing more than 200 ft need review over it where `building_has_atrium` is yes or not stated |
| 1017.3 exception 1, 1030.7 (brought in) | open parking garages measured to a riser; assembly seating's travel along the aisles, never over the seats, in any group | Group S-2 over its row needs review; every travel row (Group I-4's and 1006.2.2.6's too) needs review while fixed seating isn't ruled out |
| 1006.3.4 (note a) | a one-exit story's 75 or 125 ft | the story-exit rules (`bc_1006_3_3_story_exits`; every group in section group 2) |
| Routes `_is_exit` (P1) | a horizontal exit's far room counted as an exit | only `exit_enclosure` and `exit_passageway` doors make the room they enter an exit |

Checked on purpose and found loosening, not tightening: 1017.2.1 (balcony), 1017.2.2 (F-1, S-1), 1017.2.3 (H-5), 412.6 (aircraft manufacturing), 1030.7's exceptions, 1006.2.1's exceptions 1 and 3, Table 1006.2.1 note f; each already needs review only within the increase. New stated facts: `sprinklered_903_3_1_3` (from `sprinkler_system: nfpa_13d`), `special_egress_spaces`, `merchandise_pads` (the interior format's building block); the Revit add-in has no marks for the last two yet, so a Revit check leaves them unstated and the rows they guard need review.

## Review round 2 (2026-11-23)

Five findings: fixed seating held only Group A rows (1030.7 and 1030.8 apply to any room used for assembly with fixed seats, whatever its group: now every travel and common-path row, Group I-4's included, and the flag on the fact alone; 1030.7 brought in); the Group I-4 rows lacked the sweep's `special_egress_spaces` and balcony reviews (added); the interior format's `special_egress_spaces` comment missed care suites and vehicular ramps; `needed_by` had drifted (rebuilt, and `python -m rule_format` now refuses any drift, which found Maine's too); the README's piece and number counts were stale (a test now ties them to the second reading). The class fix: `packages/rule_format/tests/test_ny_building_tightening_walk.py` walks every group (and mixed, and unstated), every value of every building fact the drafted rules read (the walk fails if a rule reads one it doesn't vary), and measures just inside and past each tightened limit, against an oracle written from the table above: no travel or common-path row passes where a tightening applies. At `a1425e1a` it found 2,451 such passes across 24 rules (fixed seating in every group but A, the I-4 rows, 1006.2.2.6's rule; with 407.4.2's rule, which measures a sleeping room's own travel, left out of its scope); after the fixes, none.

## What the four-unit apartment still waits on

Its remaining needs-review lines (1006.3.3's story exits, 1006.2.1.1, 508.2.3, and from group 4 a corridor's width and capacity) read an occupant load, which nothing gives yet: the routes leave `story_occupant_load`, `space_occupant_load` and `corridor_occupant_load` to the architect, and no host sends them. Group 3 needs a room's Table 1004.5 function from the model (a new room mark, e.g. "Gordium: Function", in the Revit add-in and the interior format), or the architect's stated loads; a whole building's one group can't stand in for it (an R-2 building's small exercise room is part of R-2 yet loaded at 50 sq ft per occupant, denser than residential's 200). The check request as sent carries no `building` block, so its occupancy and sprinkler system are unstated there: every row rule needs review, and only answers true whatever they are stand (two separation rules pass).
