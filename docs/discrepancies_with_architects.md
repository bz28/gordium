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
| P2 | **Dead end** | 21'-6" (limit 2.5 × 10 ft = 25 ft) | not measured (the corridor jogs and widens; the first version measures only straight legs at right angles) | Measured by hand on the model along the corridor's centre line: about 32 ft. NFPA 101 A.7.5.1.5 measures a dead end along the centre line to "point C, located at the centerline of the corridor". If that reading holds, the dead end **exceeds** 25 ft. Tracked in `docs/decisions/2026-11-20_route_measurement.md` (open questions 1 and 2: which centre line, and where a dead end ends). | 🔴 |
| P3 | **Travel distance** | 130'-8" (limit 200 ft) | 118.76 ft from the sheet's start (STORAGE (11)'s north-east corner) to the sheet's exit, 12 in clear of corners (116.03 ft with no clearance); over the whole floor, 110.25 ft to the nearest exit over the rooms with a route, and 5 rooms have none, so needs review | The sheet's path is drawn orthogonally (along the grid); Gordium's is the shortest real walk, 12 in clear of corners, which is shorter. Both are well under 200 ft. Outside the eval's tolerance (`figures.travel_distance`: 14.6 ft against 2.6 ft allowed, on the no-clearance figure). | 🟡 |
| P4 | **Common path** | 48'-6" (limit 75 ft) | 42.60 ft from the sheet's start, 12 in clear of corners (41.07 ft with no clearance); over the whole floor, 43.45 ft from MOUNTAIN CLASSROOM (3) over the rooms with a route, and **6** rooms have no route to one of the two exits: the 5 of P5 plus CORRIDOR (26) | Same reason as P3. CORRIDOR (26) reaches one exit but has no route to the exit `...0005bc94` (the point (55.308, 78.082) in it has none): **not yet investigated** (a door not read, a room it may not cross, or a corner closer than 12 in). Until then the common path needs review. Outside the eval's tolerance (`figures.common_path`: 7.4 ft against 2.0 ft allowed, on the no-clearance figure). | 🟡 |
| P5 | **Five rooms with no legal route** | not discussed | STORAGE (13) (only into STORAGE (14)); ELEC. (21) and CLOSET (40) (only into the kitchen); SPRINKLERED ABANDONED SPACE (32) and SPRINKLERED ABANDONED SPACE (33) | IBC 2009 1014.2 item 4 and NFPA 7.5.2.1: no egress through kitchens, storerooms or closets. The sheet marks one abandoned space's door "permanently fixed shut". Proposed: a "not occupied" mark (NFPA 7.6.1 measures from points "subject to occupancy"). | 🟡 |
| P6 | **Building diagonal** | 210'-2½" | 213.0 ft | Unexplained so far (2.8 ft, 1.3%, against the stated figure; 2.9 ft against the sheet's line as drawn, 210.09 ft): outside the eval's tolerance (`figures.diagonal`: 0.5 ft allowed). The sheet's ticks aren't at the traced outline's corners (its north-east tick is about 3 ft north of the traced north face): a trace or drawing difference, not settled. One third of either diagonal is about 70 to 71 ft, far below either remoteness figure (P8). | ⚪ |
| P7 | **Storage area** | 1,428 sf | 1,178.8 sf inside the walls; 1,414.3 sf to the walls' outer faces | The eval compares the inside-walls figure (decision 8), and it is **17% under the sheet**: outside the eval's tolerance (`storage.agreement_inside`: 249.2 sf against 14.28 sf allowed). The outer-faces figure is within 1% of the sheet. The sheet doesn't list its rooms; Gordium counts the rooms marked accessory storage (an eval assumption, `eval_marks.yaml`). So either the sheet measures to the outer faces, or it counts other rooms: not settled. The rule complies under all four readings of where an area is measured (the largest accessory area, 1,414.3 sf, against 10% of the smallest story area, 15,970 sf inside the walls: 1,597 sf). | 🟡 |
| P8 | **Exit remoteness** | 183'-10" (the west and east corridor exits) | 187.16 ft between the farthest-apart pair of exits, nearest edges (189.29 ft door centres); 183.71 ft for the sheet's own pair | Decision 7 takes the farthest-apart pair; the sheet measures a different pair. On the sheet's pair the two agree (0.12 ft). Outside the eval's tolerance as compared (`figures.remoteness`: 3.3 ft against 1.0 ft allowed). Either way the exits are far more than one third of the diagonal apart (about 71 ft). | ⚪ |
| P9 | **The eight route rules' verdicts** | pass, each | needs review, each (`verdicts`: `ibc_1016_1_travel_distance`, `nfpa_16_2_6_2_point_in_room_to_exit`, `ibc_1014_3_common_path`, `nfpa_16_2_5_3_1_common_path_sprinklered`, `ibc_1018_4_dead_end`, `nfpa_16_2_5_2_dead_end`, `ibc_1015_2_1_remoteness`, `ibc_508_2_1_accessory_area`) | None fails. Five are drafted as flags (the 2009 IBC copy is OCR only, so a person decides: IBC 1016.1, 1014.3, 1018.4, 1015.2.1, 508.2.1), so they need review even when measured; travel distance waits on the 5 rooms with no route (P5), common path on 6 (P4); the dead ends aren't measured (P2). | 🟡 |
