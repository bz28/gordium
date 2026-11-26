# Where our findings differ from the architects'

**Purpose:** where Gordium's reading of the law differs from the architects' hand-worked 106 Ithaca Rd example, ranked by whether it changes a result.\
**For:** the architects and Ben.\
**Kept current by:** whoever finds or resolves a difference, in that same PR.

Their worked example: a new single-family house at **106 Ithaca Road (R-1b)**, received 2026-10-17 (workflow doc, links doc, spreadsheet, Rhino model).
Checked by us on 2026-10-19 against the official sources in `regulations/jurisdictions/new_york/ithaca_city/1_source_documents/` and the City's GIS records.

**Severity:** 🔴 changes a pass/fail result · 🟡 wrong or incomplete, but doesn't change the result here · ⚪ minor / tidy-up

## What they got right

- **Zone:** R-1b. Confirmed by the City's parcel record (tax parcel 84.-2-6) and the May 2026 zoning map. No overlay, not historic, not in a flood zone.
- **Every R-1b number in their spreadsheet** matches the zoning charts (p.3 dimensions, p.14 parking).
- **Documents:** they used the right ones (zoning map, zoning charts, Chapter 325). Their links point to the current versions.

## 1. The lot

| | Architects | Official / us | Severity |
|---|---|---|---|
| Lot area | 6,674.5 sf as drawn (6,674 in the spreadsheet) | ~7,034 sf (City tax parcel) | 🟡 Coverage limit depends on it (25% = 1,669 vs 1,759 sf). A survey would settle it. |
| Street edge | One straight 73 ft line | Curved | 🟡 Affects front yard and lot area |
| Spreadsheet lot | 73 × 90 ft rectangle | Irregular 5-sided lot | 🟡 Yards and depth are approximations |

## 2. The spreadsheet

| # | Issue | Severity |
|---|---|---|
| 2.1 | **Coverage:** shows "Within table limit", but 53 × 35 = 1,855 sf = 27.8% of the lot, **over** the 25% limit. (Its own PASS/FAIL column correctly says FAIL.) | 🔴 |
| 2.2 | **Rear yard:** compares the *required* rear yard (22.5 ft) with the 20 ft minimum, instead of the house's *actual* rear distance (25 ft). Passes by coincidence. Also ignores the 50 ft cap, and the "Back offset" input is never used. | 🔴 |
| 2.3 | **Use check:** passes whenever the limit says "Permitted", whatever use is entered. | 🟡 |
| 2.4 | **PASS/FAIL formula** decides "at least" vs "at most" by searching the row label for the words "minimum"/"maximum". The coverage row has neither and works by luck. | 🟡 |
| 2.5 | **Lot area** is typed in (6,674), not calculated, though labelled "derived". It doesn't equal 73 × 90 (6,570). | ⚪ |

## 3. Rules the spreadsheet leaves out (from Chapter 325)

| # | What the law says | Why it matters | Severity |
|---|---|---|---|
| 3.1 | **Coverage counts more than the house:** all buildings on the lot, plus porches, decks, balconies sticking out over 2 ft, ramps and landings (§325-3 "building area", §325-18A). | A porch or deck can push a passing design over 25%. | 🔴 |
| 3.2 | **Height is measured from the "grade plane"** (the average ground level around the walls), and to the **average height of a pitched roof**, not its peak (§325-3). | Their 35 ft is a typed number, not measured this way. | 🟡 |
| 3.3 | **A basement can count as a story** if its ceiling is more than 6 ft above the grade plane or 12 ft above the ground at any point (§325-3). | Affects the 3-story limit on sloped lots. | 🟡 |
| 3.4 | **Eaves, cornices and sills may stick into a required yard by up to 2 ft** (§325-18B). Porches and decks may not. | Changes how yards are measured. | ⚪ |

## 4. The Rhino model

| # | Issue | Severity |
|---|---|---|
| 4.1 | **The building is ~76 ft away from the buildable area.** All four of its corners are outside the lot. | 🔴 |
| 4.2 | **Rear setback drawn at 20 ft; most readings of the side lot lines require more (23.7 or 25.015 ft).** The code takes 25% of the *average* of the two side lot lines when they differ (Chapter 325 §325-8A(14)(a), p.25). If the 90.28 and 99.37 ft lines are the side lot lines: (90.28 + 99.37) / 2 = 94.8 ft → **23.7 ft**. Most readings of this 5-sided lot need more than 20 ft: 23.7 ft as above, or 25.015 ft if the jog is added to the 99.37 ft line it continues ((90.28 + 109.84) / 2 = 100.06 ft). Only averaging all three lines that aren't front or rear ((90.28 + 10.47 + 99.37) / 3 = 66.7 ft) gives the 20 ft minimum. So 20 ft fails under most readings, not all. (Which lines count as "side lot lines" is an open question.) | 🔴 |
| 4.3 | **The building fills the whole buildable area** (2,169 sf ≈ 32.5% of the lot), over the 25% coverage limit. | 🔴 |
| 4.4 | The building is ~53 × 41 ft. The spreadsheet's house is 53 × 35 ft. | 🟡 |
| 4.5 | The buildable-area outline is on the "Site" layer, not "Setback". | ⚪ |
| 4.6 | Front setback drawn at 30 ft (the minimum is 25 ft). That's allowed, just stricter than needed. Intended? | ⚪ |

**Confirmed by measuring the model with code (PR 11, `packages/model_measurement/tests/test_models.py`).** As sent, the house solid is outside the lot, so Gordium measures the lot (6,674.5 sf, 73.0 ft frontage) and the height (35 ft) but gives no yards (4.1). With the solid moved onto its own outline on the Site layer (an exact copy, shifted by 48.68 ft and 58.78 ft):

| Measure | Their spreadsheet | Their model, measured | Why they differ |
|---|---|---|---|
| Lot width | 73 | 73.0 | same |
| Front yard | 30 | 30.0 | same |
| Side yards | 10 / 10 | 10.0 / 10.0 | same |
| Height | 35 | 35.0 | same |
| Building area | 1,855 sf (53 × 35) | 2,169.2 sf | the model's house is about 53.3–53.6 × 40.4–40.8 ft, not quite rectangular (4.4) |
| Rear yard | 25 ft | 20.0 ft | the model's deeper house; 20 ft is the spreadsheet's unused "Back offset" input (2.2) |
| Lot depth | 90 ft | no single value: 94.82 ft (the jog as a rear lot line) or 100.06 ft (as a side lot line) | §325-8A(14)(a) averages the two side lot lines; 90 ft is neither reading (4.2) |

With those numbers the R-1b results agree with the spreadsheet on 7 of its 11 rows. The other four are NEEDS REVIEW: rear yard and height (both use the lot depth) until the architects say which lines are the side lot lines, and lot size and coverage (both use the lot area) because the model's lot is drawn from the City's map, not a survey. Under either reading the model's 20 ft rear yard is short (23.7 or 25.0 ft required).

## 5. The workflow document

| # | Issue | Severity |
|---|---|---|
| 5.1 | Says 73 × 90 = 6,675 sf; it's 6,570. (The irregular lot as drawn is 6,674.5 sf.) | ⚪ |
| 5.2 | Front offset 25 ft in the doc, 30 ft in the spreadsheet and model. | ⚪ |
| 5.3 | Step 8 switches to a different lot (60 × 120 ft). | ⚪ |
| 5.4 | Steps 6 and 9 are missing; step 11 is unfinished. | ⚪ |
| 5.5 | Parking cell given as "B1"; it's B15. "Restore to 28 ft" should be 35 ft. | ⚪ |
| 5.6 | Says "the current example is within all limits", but coverage fails (see 2.1). | 🔴 |

## Bottom line

The architects used the right documents and copied the R-1b numbers correctly. The mistakes are in **applying** them: comparing the wrong numbers, assuming a rectangular lot, and not counting what the law adds (porches and decks in coverage, how height is measured). Their example house would actually **fail** coverage, and the model would fail rear yard and coverage. These are exactly the mistakes Gordium should catch, so they make good first test cases.

Open questions for them are in `questions_for_architects.md`.

---

# Children's Odyssey, 19 Libby St, Portland ME: for review

**What this is:** where Gordium's figures, the architect's life-safety sheet (LS1.0) and our own eval files disagree on the
childcare centre. Nothing in `test_data/answer_keys/` is changed to settle any of these: each is logged here with its
proof, for Ben (and, where it's the law, the architects) to review. Gordium's figures are from
`test_data/answer_keys/portland_me_19_libby_st/eval_comparison.yaml` (made by `tests/make_eval_comparison.py`).

| # | What | Sheet (LS1.0) | Gordium / the model | Why, and the proof | Severity |
|---|---|---|---|---|---|
| P1 | **CLOSET (40): which room its door opens into** | its door swings into KITCHEN (10), in the kitchen's corner by the corridor wall | the same: door D06 joins CLOSET (40) and KITCHEN (10); the closet spans x 22.2 to 26.0 ft, inside the kitchen's 1.0 to 26.0 ft, and INFANT/TODDLER CLASSROOM (5) starts at 26.6 ft | **Our own `eval_marks.yaml` (PR #144) says "a closet off INFANT/TODDLER CLASSROOM 5 (door D06)"**: its note disagrees with the sheet and the model. Found 2026-11-21 reading the model's description (door D06's `sides`) and a crop of the sheet. The marks themselves (Closet, lockable) are unaffected; only the note's wording. Proposed: correct the note. | ⚪ |
| P2 | **Dead end** | 21'-6" (limit 2.5 × 10 ft = 25 ft) | **32.01 ft**, least width 9.33 ft (`figures.dead_end`: the east stub, closed end at x 152.55, y 74.85, measured since 2026-11-22 along the centre line to the main corridor's centre line, y 42.84) | NFPA 101 2012 A.7.5.1.5 measures a dead end "along the centerline of the corridor to point C, located at the centerline of the corridor": not to the near edge of the widened area, where the sheet's line ends (y 53.17, which gives the sheet's 21'-6"). The stub opens into a stretch where the main corridor widens to 15.3 ft; to that stretch's own middle it would be 29.35 ft; Gordium takes the farther centre line (route note decision 6, amended 2026-11-22). Either way it **exceeds** 25 ft, so the stub fails IBC 1018.4 (20 ft, exception 3 needing under 2.5 × the least width); NFPA 16.2.5.2 allows 50 ft sprinklered. The least width is 9.33 ft, not 10: a 4-in wall end narrows the stub's mouth in the model (x 147.54 to 147.90, y 53.17 to 53.83), outside the eval's 1-in tolerance (`figures.dead_end.agreement`). The model has more dead ends the sheet doesn't show: the corridor's west part, 67.1 ft from its west end to the north wing, if the vestibule beyond door D34 (a lobby, not a corridor) doesn't count, 0 if it does (open question 7, two readings); the west stub (to y 73.83), 58.1 ft without the playroom door D24, 7.2 ft with it; door alcoves of 7.6 to 30.1 ft. Tracked in `docs/decisions/2026-11-20_route_measurement.md` (open question 2: which centre line where the crossing corridor widens; open question 7: doors into rooms with another way out). | 🔴 |
| P3 | **Travel distance** | 130'-8" (limit 200 ft) | 118.76 ft from the sheet's start (STORAGE (11)'s north-east corner) to the sheet's exit, 12 in clear of corners (116.03 ft with no clearance); over the whole floor, 110.25 ft to the nearest exit over the rooms with a route, and 5 rooms have none, so needs review | The sheet's path is drawn orthogonally (along the grid); Gordium's is the shortest real walk, 12 in clear of corners, which is shorter. Both are well under 200 ft. The eval's test since 2026-11-21 is one-sided (`docs/decisions/2026-11-20_route_measurement.md`, "The eval": an orthogonal line is never shorter than the natural path IBC 1016.1 and NFPA 7.6.1 measure): Gordium's 116.03 ft is no longer than the sheet's line as drawn, 130.33 ft, plus 2.6 ft (`no_longer` true), but `figures.travel_distance` still doesn't agree, as its two rules' verdicts differ from the sheet's (P9). Under the first test it is outside tolerance (`figures.travel_distance.agreement.before_2026_11_21`: 14.6 ft against 2.6 ft allowed, on the no-clearance figure). | 🟡 |
| P4 | **Common path** | 48'-6" (limit 75 ft) | 42.60 ft from the sheet's start, 12 in clear of corners (41.07 ft with no clearance); over the whole floor, 43.45 ft from MOUNTAIN CLASSROOM (3) over the rooms measured, and **5** rooms aren't measured (those of P5, no route to the exit `...0005bc94`) | Same reason as P3. CORRIDOR (26) no longer stops (since 2026-11-22): its tied routes are now taken all together (route note decision 5, amended), never listed; the point that stopped it, (63.232, 37.844), had one route listed 128 times, split at the tangent points of a row of alcove corners' rings. The five rooms of P5 have no route to the exit `...0005bc94`, each from its own point (for example SPRINKLERED ABANDONED SPACE (32) from (55.308, 78.082)). Until then the common path needs review. Under the eval's test since 2026-11-21 (as in P3), Gordium's 41.07 ft is no longer than the sheet's line as drawn, 48.40 ft, plus 2.0 ft (`no_longer` true), but `figures.common_path` still doesn't agree, as its two rules' verdicts differ from the sheet's (P9). Under the first test it is outside tolerance (`figures.common_path.agreement.before_2026_11_21`: 7.4 ft against 2.0 ft allowed, on the no-clearance figure). | 🟡 |
| P5 | **Five rooms with no legal route** | not discussed | STORAGE (13) (only into STORAGE (14)); ELEC. (21) and CLOSET (40) (only into the kitchen); SPRINKLERED ABANDONED SPACE (32) and SPRINKLERED ABANDONED SPACE (33) | IBC 2009 1014.2 item 4 and NFPA 7.5.2.1: no egress through kitchens, storerooms or closets. Since 2026-11-21 Gordium's reading (route note decision 1a, open question 11, to confirm) lets a closet, storeroom or toilet that opens only into the room it serves leave through that room, but never through a room that can be locked (1014.2 item 2). The eval marks KITCHEN (10) and STORAGE (14) `lockable: true` (`eval_marks.yaml`: "kept locked"), so CLOSET (40) and STORAGE (13) still have no route, and the eval file now says why (the room they open into can be locked). NFPA 16.2.2.2.4 requires a day care's closet, storage and kitchen latches to open from inside: if these rooms lock only against entry, the mark would be `lockable: false` and both would get a route: the architect's to say (open question 11). ELEC. (21) is marked `other`, which the reading doesn't cover. The sheet marks one abandoned space's door "permanently fixed shut". Since 2026-11-22 a room may be marked `not_occupied` (Revit's `Gordium: Not occupied`; route note decision 1b): NFPA's travel and common path then leave its points out (7.6.1(1) measures from points "subject to occupancy"), saying so; the 2009 IBC's don't (1016.1 measures from "the most remote point within a story", no carve-out), so the IBC rows still wait on these rooms. The eval's marks file (an answer key) doesn't mark them: whether 32 and 33 are subject to occupancy is the architects' to say (route note open question 12). | 🟡 |
| P6 | **Building diagonal** | 210'-2½" | 213.0 ft | Unexplained so far (2.8 ft, 1.3%, against the stated figure; 2.9 ft against the sheet's line as drawn, 210.09 ft): outside the eval's tolerance (`figures.diagonal`: 0.5 ft allowed). The sheet's ticks aren't at the traced outline's corners (its north-east tick is about 3 ft north of the traced north face): a trace or drawing difference, not settled. One third of either diagonal is about 70 to 71 ft, far below either remoteness figure (P8). | ⚪ |
| P7 | **Storage area** | 1,428 sf | 1,178.8 sf inside the walls; 1,414.3 sf to the walls' outer faces | The eval compares the inside-walls figure (decision 8), and it is **17% under the sheet**: outside the eval's tolerance (`storage.agreement_inside`: 249.2 sf against 14.28 sf allowed). The outer-faces figure is within 1% of the sheet. The sheet doesn't list its rooms; Gordium counts the rooms marked accessory storage (an eval assumption, `eval_marks.yaml`). So either the sheet measures to the outer faces, or it counts other rooms: not settled. The rule complies under all four readings of where an area is measured (the largest accessory area, 1,414.3 sf, against 10% of the smallest story area, 15,970 sf inside the walls: 1,597 sf). | 🟡 |
| P8 | **Exit remoteness** | 183'-10" (the west and east corridor exits) | 187.16 ft between the farthest-apart pair of exits, nearest edges (189.29 ft door centres); 183.71 ft for the sheet's own pair | Decision 7 takes the farthest-apart pair; the sheet measures a different pair. On the sheet's pair the two agree (0.12 ft). Outside the eval's tolerance as compared (`figures.remoteness`: 3.3 ft against 1.0 ft allowed). Either way the exits are far more than one third of the diagonal apart (about 71 ft). | ⚪ |
| P9 | **The eight route rules' verdicts** | pass, each | needs review, each (`verdicts`: `ibc_1016_1_travel_distance`, `nfpa_16_2_6_2_point_in_room_to_exit`, `ibc_1014_3_common_path`, `nfpa_16_2_5_3_1_common_path_sprinklered`, `ibc_1018_4_dead_end`, `nfpa_16_2_5_2_dead_end`, `ibc_1015_2_1_remoteness`, `ibc_508_2_1_accessory_area`) | None fails. Five are drafted as flags (the 2009 IBC copy is OCR only, so a person decides: IBC 1016.1, 1014.3, 1018.4, 1015.2.1, 508.2.1), so they need review even when measured; travel distance and common path wait on the 5 rooms with no route (P5); the dead ends are measured (P2) but NFPA 16.2.5.2 needs review on the corridor's west dead ends, each given as two readings (open question 7), and IBC 1018.4 is a flag (the east stub's 32.0 ft would fail it). | 🟡 |
| P10 | **Kitchen and storerooms marked lockable** | not on the sheet | our own `eval_marks.yaml` marks KITCHEN (10) and STORAGE (14) `lockable: true` ("kept locked"), so under Gordium's reading for a room that opens only into the room it serves (route note decision 1a, open question 11) CLOSET (40) and STORAGE (13) still have no route | NFPA 101 2012 16.2.2.2.4 (p.174 of the PDF): "Every door latch to closets, storage areas, kitchens, and other similar spaces or areas shall be such that clients can open the door from inside the space or area"; A.16.2.2.2.4 (p.412): "The purpose of this requirement is to prevent arrangements whereby a client can be trapped in a space or area". So in this day care those rooms likely can't be "locked to prevent egress" (IBC 2009 1014.2 item 2, OCR copy only). If the mark should be `lockable: false`, CLOSET (40) and STORAGE (13) get routes under the new reading. Logged for Ben's review; `eval_marks.yaml` is not changed. | 🟡 |

# NY Residential Code answer key: area wells (R319.4.1)

**What this is:** where Gordium's reading of R319.4.1 differs from the architects' house egress answer key
(`test_data/answer_keys/new_york/new_york_state/general.yaml`, `general.r319_4_1_area_well_size`). The key is not changed;
each point is logged with its proof for the architects (2026-11-26, PR feat/r319-well-encroachment).

| # | What | Answer key | Gordium | Why, and the proof | Severity |
|---|---|---|---|---|---|
| W1 | **A well 30 in to under 36 in wide or out from the wall, with a ladder or steps clear of the open window, or not said whether** (the key's review: `area_well_ladder`, both sizes 30 in or more and the opening fully openable, any depth, any area; the key has no reach measure) | needs review | reads it as a fail (the well's own size must be 36 in; the ladder may only take up to 6 in of those 36 in), but kept as **needs review** to match the key until the architects answer, where a ladder is required (a well over 44 in deep) and reaches in 6 in or less with nothing else in the well. It **fails** where the key needs review in four cases: a well 44 in deep or less (no ladder is required, so none may encroach), a ladder or steps that reach 0 in (they take nothing of the 36 in), a ladder or steps reaching more than 6 in, and anything else reaching into the well (no exception allows it) | R319.4.1: "The horizontal area of the area well shall be not less than 9 square feet (0.9 m²), with a horizontal projection and width of not less than 36 inches (914 mm)." Exception: "The ladder or steps required by Section R319.4.2 shall be permitted to encroach not more than 6 inches (152 mm) into the required dimensions of the area well." (p.103). The exception lets the ladder stand *inside* the required 36 in, not make the well smaller; Gordium's Building Code rule (BCNYS 1031.5.1, the same words) fails such a well. The key's own note reads the sizes as "the well's own size, the ladder not taken off", and its band existed because the ladder's reach wasn't measured; it is now (`area_well_ladder_encroachment`). | 🟡 |
| W3 | **A well 36 in or more each way, with a ladder or steps clear of the open window, or not said whether** (the key's example 4: 36 by 48 in, 12 sq ft, a ladder) | needs review (its review, the ladder's reach not measured; a well under 9 sq ft too, since its review comes first) | of 9 sq ft or more, **passes** once nothing else reaches in and the ladder's reach is stated as 0 (at any depth), or 6 in or less in a well over 44 in deep for a ladder clear of the window (the exception's own allowance); under 9 sq ft (a half-round well) the area rule fails with a reach of 0, and whatever the reach in a well 44 in deep or less (no ladder is required there, so the exception doesn't apply), and needs review with a required ladder reaching 6 in or less in a deeper well. It **fails** where the ladder reaches in more than 6 in, or at all in a well 44 in deep or less, or anything else reaches into the well; and needs review where a reach, the depth or (within 6 in) whether the ladder is clear isn't stated | The exception's words allow exactly this; the key's review was for the unmeasured reach. Gordium passes where the key reviews, the direction that matters, so it is logged for the architects with the exception's words (W1). | 🟡 |
| W2 | **A well 36 in or more each way and 9 sq ft or more, its ladder or steps said not clear of the open window (or none), nothing said about what reaches into it** (the key's example 1: 36 by 48 in, 12 sq ft) | pass | needs review until both reaches are stated: how far a ladder or steps reach in (`area_well_ladder_encroachment`, Revit's Gordium: Well ladder encroachment; the key's `area_well_ladder: false` is "no ladder clear of the window", not "no ladder") and how far anything else does (`area_well_other_encroachment`, Gordium: Well other encroachment) | The exception allows only the required ladder or steps into the required dimensions; a gas meter or a downspout bracket in them has no exception. The key's example has no measure for either (cause `r319_4_1_reach_not_in_the_example`, `packages/rule_drafting/evals/2026-11-13_house_egress/resolutions.yaml`). | ⚪ |
| W4 | **The same well, its ladder or steps the open window obstructs, reaching in 6 in or less, over 44 in deep or the depth not said, with nothing else in it (or not said)** | pass (its `area_well_ladder` is false, so its review doesn't fire) | needs review on the size rules (an open question: whether an obstructed ladder is "The ladder or steps required by Section R319.4.2"; with the depth not said, whether a ladder is required at all); R319.4.2's own rule fails the obstruction in a well over 44 in deep, and needs review where the depth isn't said | R319.4.2: "The ladder or steps shall not be obstructed by the emergency escape and rescue opening where the window or door is in the open position." | ⚪ |
| W5 | **The same well, its ladder or steps not clear of the open window (or none), with something else in it** (a meter, a downspout bracket) | pass (it has no measure for it) | fails | The exception names only the ladder or steps; nothing else may encroach into the required dimensions. | 🟡 |
| W6 | **The same well, its ladder or steps the open window obstructs, reaching in more than 6 in, or reaching in at all in a well 44 in deep or less** | pass (its `area_well_ladder` is false, so its review doesn't fire) | fails | No ladder or steps the exception names may reach in there: past 6 in it allows none, and a well 44 in deep or less requires none (R319.4.1's exception, R319.4.2). | 🟡 |
