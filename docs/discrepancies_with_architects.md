# Where our findings differ from the architects'

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
| Lot area | 6,674.7 sf | ~7,034 sf (City tax parcel) | 🟡 Coverage limit depends on it (25% = 1,669 vs 1,759 sf). A survey would settle it. |
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
| 4.2 | **Rear setback drawn at 20 ft, but the rule requires more.** The code takes 25% of the *average* of the two side lot lines when they differ (Chapter 325 §325-8A(14)(a), p.25). If the 90.28 and 99.37 ft lines are the side lot lines: (90.28 + 99.37) / 2 = 94.8 ft → **23.7 ft**. Under any reading of this 5-sided lot it's at least 22.6 ft, so 20 ft fails either way. (Which lines count as "side lot lines" is an open question.) | 🔴 |
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
| 5.1 | Says 73 × 90 = 6,675 sf; it's 6,570. (6,674.7 is the real irregular lot.) | ⚪ |
| 5.2 | Front offset 25 ft in the doc, 30 ft in the spreadsheet and model. | ⚪ |
| 5.3 | Step 8 switches to a different lot (60 × 120 ft). | ⚪ |
| 5.4 | Steps 6 and 9 are missing; step 11 is unfinished. | ⚪ |
| 5.5 | Parking cell given as "B1"; it's B15. "Restore to 28 ft" should be 35 ft. | ⚪ |
| 5.6 | Says "the current example is within all limits", but coverage fails (see 2.1). | 🔴 |

## Bottom line

The architects used the right documents and copied the R-1b numbers correctly. The mistakes are in **applying** them: comparing the wrong numbers, assuming a rectangular lot, and not counting what the law adds (porches and decks in coverage, how height is measured). Their example house would actually **fail** coverage, and the model would fail rear yard and coverage. These are exactly the mistakes Gordium should catch, so they make good first test cases.

Open questions for them are in `questions_for_architects.md`.
