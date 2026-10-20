# Questions for the architects

Gordium checks a design by reading the city's exact words. In the places below, the words can be read more than one way, so Gordium marks the result **NEEDS REVIEW** instead of guessing. Each answer you give turns a NEEDS REVIEW into an automatic PASS or FAIL for every future project.

**How to read each question**
- **The city's words:** the exact text, with the section and a link to the page.
- **Why it matters:** a real design where the answer changes the result.
- **Until you answer:** what Gordium does now. Measurements are typed in today; the step that measures a Rhino model is being built, and it follows these notes.
- **Options:** the readings we can see. Pick one, or tell us another.
- 🔴 **Blocks R-1b today:** the question affects a check Gordium already runs on R-1b single-family houses (like 106 Ithaca Rd). Unmarked questions matter for other uses, other districts, or rules not built yet.

The tags in square brackets (for example lot_depth#1, the first question about lot depth) say where each question is recorded in Gordium's files. A test fails if a recorded question is missing from this page, so this page is always the complete list. The same questions are in the **Questions** tab of the rules spreadsheet (`ithaca_city_rules.xlsx`).

Links to Chapter 325 open our stored copy of the city's PDF (for people with access to the Gordium repository); links to the zoning charts open the city's own website.

**The most important five** (answering these unblocks the most R-1b checks):
1. Which lines are the side lot lines on an irregular lot (§1.1)
2. What lot area to use without a survey (§1.2)
3. What counts toward lot coverage: garages and overhangs (§3.1, §3.2)
4. Where yards are measured to: the wall or the eave (§2.1)
5. How building height is measured on a pitched roof (§4.1)

---

## 1. The lot: area, width and depth

### 1.1 Which lines are the "side lot lines" on a lot with more than four sides? 🔴
`[lot_depth#1]` `[R-1b.rear_yard#1]`

- **The city's words:** "Such percentage shall be taken of the lot depth. If the two side lot lines are of unequal lengths, the rear yard percentage shall be taken of the average of the two lengths." ([Chapter 325 §325-8A(14), p.25](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=25))
- **Why it matters:** the R-1b rear yard is 25% of the lot depth (at most 50 ft, at least 20 ft). 106 Ithaca Rd has five sides, including a 10.47 ft jog. If the 90.28 ft and 99.37 ft lines are the side lot lines, the depth is 94.8 ft and the rear yard must be 23.7 ft. Other readings give at least 22.6 ft. The difference can decide PASS or FAIL for a house placed close to the rear.
- **Until you answer:** the rear-yard rule uses whatever lot depth it is given. When measured from a model, a lot with more than two side lines gets NEEDS REVIEW on the rear yard.
- **Options:** (a) the two longest lines that touch the street line; (b) the two lines that touch the street line, plus any jog added to the line it continues; (c) average every line that isn't the front or rear line; (d) another rule you use.

### 1.2 What "lot area" should be used, especially without a survey? 🔴
`[lot#1]`

- **The city's words:** "LOT — A portion or parcel of land, considered as a unit, devoted to a certain use or occupied by a building or a group of buildings…" (§325-3, [p.14](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=14)). Chapter 325 never defines "lot area" itself.
- **Why it matters:** the R-1b coverage limit is 25% of lot area. 106 Ithaca Rd is about 7,034 sf on the city's tax map, but 6,674.7 sf in your model. That moves the limit from 1,669 sf to 1,759 sf, and the 1,855 sf house fails under both.
- **Until you answer:** coverage uses the lot area it is given (for 106 Ithaca Rd, your 6,674 sf). When measured from a model, the area inside the drawn lot lines is used, with a reminder to check it against a survey.
- **Options:** (a) always the survey, and NEEDS REVIEW if there isn't one; (b) the survey if there is one, else the tax map; (c) whatever is drawn in the model, with a warning to check it against a survey.

### 1.3 Lot width on a curved street 🔴
`[lot_width#1]`

- **The city's words:** "Lots hereafter used for a permitted use in each use district shall have frontage measured on a public right-of-way equal to or greater than the width specified in this column…" (Column 7, [§325-8A, p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24))
- **Why it matters:** R-1b requires 50 ft of frontage for a one-family house. 106 Ithaca Rd's street edge is curved. A curve is longer than the straight line between its ends, so a lot just under 50 ft could pass one way and fail the other.
- **Until you answer:** a straight street line is simply measured; a curved one gets NEEDS REVIEW on lot width.
- **Options:** (a) along the curve; (b) the straight line between the two side lot corners.

### 1.4 Lot depth when the two side lot lines are equal
`[lot_depth#2]`

- **The city's words:** as in 1.1: "If the two side lot lines are of unequal lengths, the rear yard percentage shall be taken of the average of the two lengths."
- **Why it matters:** the law only says what to do when the lines differ. We assume equal lines mean the depth is that length.
- **Until you answer:** uses that length.
- **Options:** (a) yes, the common length; (b) something else (please explain).

---

## 2. Yards

### 2.1 Are yards measured to the wall, or to the eave? 🔴
`[yard_projections#1]`

- **The city's words:** "The space in any required yard shall be open and unobstructed except for ordinary projections of windowsills, belt courses, cornices, eaves and other architectural features; provided, however, that such features shall not project more than two feet into any required yard." ([§325-18B, p.49](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=49))
- **Why it matters:** every yard check (front, both sides, rear) depends on it. A house 10 ft from the side line with an 18-inch eave is either 10 ft away (to the wall) or 8.5 ft away (to the eave).
- **Until you answer:** yards are measured to the wall, and a model whose eaves reach into a required yard gets NEEDS REVIEW on that yard.
- **Options:** (a) to the wall, with eaves allowed up to 2 ft into the yard; (b) to the outermost edge of anything, eaves included; (c) to the wall, but to the eave when it projects more than 2 ft.

### 2.2 Corner lots: one front yard per street 🔴
`[front_yard#1]`

- **The city's words:** "(1) FRONT YARD — An open space extending the full width of the lot between a main building and the front lot line… the depth of which shall be the least distance between the front lot line and the front of such main building." (§325-3, [p.20](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=20)). §325-19C (p.50) adds that on corner lots in residential districts, "yards facing public streets shall conform to the minimum front yard requirements", giving "two adjoining front yards".
- **Why it matters:** on a corner lot, both street sides need the 25 ft front yard instead of 10 ft side yards. That costs 15 ft of buildable width.
- **Until you answer:** Gordium asks which line faces the street. Corner lots aren't handled yet and get NEEDS REVIEW.
- **Options:** (a) confirm: every street-facing yard is a front yard, and only the rest are side or rear yards; (b) another reading.

### 2.3 Corner lots: how many side yards are left?
`[side_yard#2]`

- **The city's words:** "Buildings hereafter erected in each use district must have two side yards as specified in this column and Column 12." (Column 13, [§325-8A, p.25](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=25)). On a corner lot, §325-19C (p.50) makes two front yards, and §325-8A(14)(d) (pp.25–26) makes the yard opposite the address street the rear yard, which leaves one side yard.
- **Why it matters:** decides how close a corner-lot house can be to its one remaining side line.
- **Until you answer:** corner lots get NEEDS REVIEW.
- **Options:** (a) the one side yard uses the larger minimum (Column 13); (b) the smaller one (Column 12); (c) another reading.

### 2.4 Do side yards apply to a detached garage or shed?
`[side_yard#1]`

- **The city's words:** "The required width of side yards shall be measured horizontally from the nearest point of the side lot line to the nearest part of any building." (§325-3, [p.20](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=20)). §325-25 (p.66) says accessory structures (private garages, sheds, toolhouses, garden houses, playhouses) "shall be exempt from side yard requirements contained in the District Regulations Chart" and follow §325-25's own rules.
- **Why it matters:** a detached garage near the side line would fail the chart's 10 ft side yard, but §325-25 may allow it.
- **Until you answer:** side yards are checked against the main house only. Accessory buildings aren't checked yet; §325-25 will become rules of its own.
- **Options:** (a) confirm: chart side yards are measured to the main building only; (b) another reading.

### 2.5 What may be built in the rear yard?
`[rear_yard#1]`

- **The city's words:** "(3) REAR YARD — An open space extending the full width of a lot between the rearmost main building and the rear lot line, unoccupied and unobstructed by buildings or structures from the ground upward except as hereinafter specified…" (§325-3, [p.20](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=20))
- **Why it matters:** "except as hereinafter specified" points to later sections (for example accessory buildings) that allow things in the rear yard. We want to be sure we find all of them.
- **Until you answer:** the rear yard is checked against the main house only.
- **Options:** please list the sections you rely on for what may go in a rear yard.

---

## 3. Lot coverage: what counts

### 3.1 Does a garage count toward building area? 🔴
`[building_area#1]` `[R-1b.lot_coverage#1]`

- **The city's words:** "BUILDING AREA — The total area (taken on a horizontal plane at the main grade level) of the principal building and all accessory buildings, including porches, attached or free standing decks… The total building area shall be used for determining required yards and maximum percentage of allowed lot coverage but shall not include parking areas and parking spaces." (§325-3, [p.5](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=5))
- **Why it matters:** a 12 × 22 ft garage is 264 sf. On a 6,674 sf R-1b lot, coverage is capped at 1,669 sf, so the garage alone can decide PASS or FAIL.
- **Until you answer:** coverage uses the building area it is given. When measured from a model, a model with a garage gets NEEDS REVIEW on coverage.
- **Options:** (a) garages count (they are accessory buildings); (b) garages don't count (they are "parking spaces"); (c) attached garages count, detached don't, or the reverse.

### 3.2 Footprint at the ground, or everything above ground? 🔴
`[building_area#2]` `[R-1b.lot_coverage#2]`

- **The city's words:** the definition says "taken on a horizontal plane at the main grade level" (§325-3, p.5). The coverage column says "no greater percentage of total lot area may be covered by principal and accessory buildings above ground." (Column 10, [§325-8A, p.25](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=25))
- **Why it matters:** a second floor that overhangs the first, or deep roof eaves, add area seen from above but not at the ground. A buried garage under a deck adds area at the ground but not above it.
- **Until you answer:** coverage uses the building area it is given. When measured from a model, a building whose outline from above differs from its footprint at the ground gets NEEDS REVIEW on coverage.
- **Options:** (a) footprint where the building meets the ground; (b) the outline of everything above ground, seen from above; (c) (b) but without roof eaves.

---

## 4. Height, grade, stories and basements

### 4.1 How is the "average height" of a pitched roof measured? 🔴
`[height_of_building#1]`

- **The city's words:** "HEIGHT OF BUILDING — [T]he vertical distance measured from grade plane to the highest level of a flat or mansard roof or to the average height of a pitched, gabled, hip or gambrel roof…" (§325-3, [p.12](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=12))
- **Why it matters:** R-1b allows 35 ft. A gable with eaves at 28 ft and ridge at 44 ft is 36 ft at the midpoint (fails), but much less if measured another way.
- **Until you answer:** height uses the number it is given (your 35 ft). When measured from a model, a flat roof is measured to the top and a pitched roof gets NEEDS REVIEW.
- **Options:** (a) midway between the eave and the ridge; (b) if eaves differ, the lowest eave; (c) the highest eave; (d) a different method for hip and gambrel roofs (please describe).

### 4.2 How is the grade plane averaged? 🔴
`[grade_plane#1]` `[grade_plane#2]`

- **The city's words:** "GRADE PLANE — A reference plane representing the average of finished ground level on each side of the building at exterior walls." (§325-3, [p.11](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=11))
- **Why it matters:** height is measured from the grade plane, and a basement counts as a story when its ceiling is more than 6 ft above it. On a sloped lot, the averaging method moves the grade plane by a foot or more.
- **Until you answer:** on level ground there is nothing to decide. When measured from a model, sloped ground gets NEEDS REVIEW on height and stories.
- **Options for averaging:** (a) one value per side, simple average; (b) weighted by the length of each wall.
- **Options for "a side" of an L-shaped or irregular house:** (a) each wall segment; (b) the four sides of the smallest rectangle around the house; (c) another rule.

### 4.3 Which entrance is the "main entrance"?
`[story#1]` `[story#2]`

- **The city's words:** "Buildings hereafter erected shall be limited to the number of stories herein specified, computed at the main entrance side." ([§325-8A, p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)). And: "A basement shall be deemed to be a story when the finished surface of the floor next above is 1) more than six feet above grade plane or 2) more than 12 feet above the finished ground level at any point." (§325-3, [p.19](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=19))
- **Why it matters:** R-1b allows 3 stories. A house on a slope can be 3 stories at the street and 4 at the back.
- **Until you answer:** stories use the number it is given (your 3). When measured from a model, a sloped site gets NEEDS REVIEW on stories.
- **Options:** for the main entrance: (a) the entrance facing the street; (b) the one the architect names. For the 12 ft test: (a) every side; (b) only the main entrance side.

### 4.4 Basement or cellar, when a space fits both?
`[basement#1]` `[basement#2]` `[cellar#1]` `[cellar#2]`

- **The city's words:** "BASEMENT — That space of a building that is partly below grade which has more than half of its height, measured from floor to ceiling, above the finished ground level at any point." (§325-3, [p.5](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=5)). "CELLAR — That space of a building that is partly or entirely below grade which has more than half of its height… below the average established curb level or finished grade of the ground adjoining the building." (§325-3, [p.6](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=6))
- **Why it matters:** a basement can count as a story; a cellar never does. A walk-out lower level on a slope can be more than half above ground on one side and more than half below on average, so it fits both definitions.
- **Until you answer:** when measured from a model, any lower level on a sloped site gets NEEDS REVIEW on stories.
- **Options:** (a) "at any point" means one point is enough, and a space that fits both is a basement; (b) it is a cellar; (c) for the cellar test, use the curb level when it exists, else the average adjoining grade (or tell us which wins when they differ).

### 4.5 The height bonus: how much bigger must the yards get? 🔴
`[R-1b.height#1]` `[R-1b.height#2]`

- **The city's words:** "In any district, any main building may be erected to a height in excess of that specified for the district, provided that: (1) Each required front, side and rear yard is increased one foot on the ground for each one foot of such additional height." ([§325-16C, p.47](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=47)). The bonus is capped at 10% (3.5 ft in R-1b).
- **Why it matters:** a 37 ft R-1b house is legal only if every yard is 2 ft bigger than usual.
- **Until you answer:** Gordium's R-1b height rule reads it as: every yard (front, both sides, rear) must be its normal minimum plus the extra height. The bonus is applied to the main building only.
- **Options:** (a) confirm both readings; (b) only some yards grow (which?); (c) the bonus also applies to accessory buildings.

### 4.6 Parapets and cornices above the limit
`[R-1b.height#3]` `[height_of_building#3]`

- **The city's words:** the height definition excludes "bulkheads, housing for mechanical equipment, towers and similar constructions not intended for human occupancy" (§325-3, p.12). §325-16A and B (p.46) separately exempt chimneys, spires, skylights and ornamental parapets or cornices up to 5 ft.
- **Why it matters:** decides whether a parapet can sit on top of a house that already uses the height bonus.
- **Until you answer:** these features aren't checked yet; §325-16A and B will become rules of their own.
- **Options:** (a) confirm these exemptions don't change how height itself is measured; (b) a parapet is allowed on top of the bonus height too; (c) it isn't.

### 4.7 A typo in the city's text (please just confirm)
`[height_of_building#2]`

- The official code reads "he vertical distance" where it means "The vertical distance". We quote it as printed and read it as "The". No effect on meaning.

---

## 5. Uses and parking

### 5.1 What do the chart's marks mean? 🔴
`[R-1b.use#1]`

- **The city's words:** the chart on [p.2](https://www.cityofithacany.gov/DocumentCenter/View/20523/COI-Zoning-Charts_0426#page=2) marks each use with •, - or SP, with no legend. §325-9B(1) (p.30) lists "uses… which require a special permit from the Planning and Development Board".
- **Why it matters:** every use check depends on it.
- **Until you answer:** Gordium reads • as permitted, - as not permitted, and SP as needing a special permit (NEEDS REVIEW).
- **Options:** (a) confirm; (b) correct us.

### 5.2 Is "public utility structure" the same as "public utility facilities"?
`[R-1b.use#2]`

- **The city's words:** the chart (p.2) says "Public utility structure except office"; §325-9B(1)(c) (p.30) says "Public utility facilities in all districts."
- **Until you answer:** treated as the same use (special permit).
- **Options:** (a) same; (b) different (please explain).

### 5.3 Can a permitted use still need review?
`[R-1b.use#3]`

- **The city's words:** "Uses which are permitted in each use district are listed, subject to the further regulations in this section and of Article V." (Column 2, [§325-8A, p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24))
- **Why it matters:** a use marked • may still have conditions elsewhere (occupancy limits, chart notes).
- **Until you answer:** a • use passes the use check; the other conditions will be rules of their own.
- **Options:** (a) confirm that approach; (b) list the conditions you check for a • use.

### 5.4 A house with an accessory dwelling unit: parking for both?
`[R-1b.parking_one_family#1]`

- **The city's words:** "First three bed or sleeping rooms per dwelling 1 space per dwelling unit" (chart [p.14](https://www.cityofithacany.gov/DocumentCenter/View/20523/COI-Zoning-Charts_0426#page=14)).
- **Why it matters:** R-1b allows an ADU. If parking is per unit, a house with an ADU needs more spaces.
- **Until you answer:** ADUs aren't checked yet.
- **Options:** (a) parking per unit, ADU included; (b) the ADU needs none of its own; (c) §325-28's ADU rules decide (please point us to the part).

---

## 6. Definitions: a category, or a limit?

Some definitions contain numbers. Gordium needs to know whether the number only says **what to call** something (a category), or **caps a design** (a limit). Our rule of thumb: if it only sorts things into names, it's a category; if it forbids or caps something, it's a limit. Please confirm or correct each.

| Definition | The city's words | Our reading today | `tag` |
|---|---|---|---|
| Adult day-care home ([p.4](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=4)) | "adult day care is provided to not more than six adults at one time" | Category: more than six makes it a different use | `[325-3B:adult_day_care_home#1]` |
| Bed-and-breakfast inn ([p.5](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=5)) | "provides five to 10 guest rooms, limited to two persons or one family per guest room" | Category | `[325-3B:bed_and_breakfast_inn#1]` |
| Kitchen ([p.14](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=14)) | "60 square feet or more in floor area, with a minimum width of five feet" | Category: smaller is a kitchenette, not a kitchen | `[325-3B:kitchen#1]` |
| Dwelling unit ([p.9](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=9)) | "having a separate entrance from the outside of the building or through a common hall" | Treated as a limit (every unit needs one) until you answer | `[325-3B:dwelling_unit#1]` |
| Rooming unit ([p.18](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=18)) | the kitchen-or-separate-entrance wording | Treated as a limit until you answer, the same as dwelling unit | `[325-3B:rooming_unit#1]` |

None of these affect a one-family R-1b house today.

---

## 7. Your 106 Ithaca Rd example

We checked your worked example against the city's documents. The full list is in `docs/discrepancies_with_architects.md`. These are the items that change a PASS/FAIL result, and we'd like you to confirm each:

- `[discrepancy 2.1]` **Coverage:** the spreadsheet's comparison column says "Within table limit", but 53 × 35 = 1,855 sf is 27.8% of the lot, over the 25% limit. (Its PASS/FAIL column correctly says FAIL.)
- `[discrepancy 2.2]` **Rear yard:** the spreadsheet compares the *required* rear yard (22.5 ft) with the 20 ft minimum, instead of the house's *actual* rear distance (25 ft). It passes by coincidence.
- `[discrepancy 3.1]` **Coverage counts more than the house:** porches, decks, balconies over 2 ft, ramps and landings count too (§325-3, §325-18A).
- `[discrepancy 4.1]` **Rhino model:** the building sits about 76 ft away from the buildable area; all four corners are outside the lot. Intended as a test, or a mistake?
- `[discrepancy 4.2]` **Rhino model:** the rear setback is drawn at 20 ft, but the rule requires at least 22.6 ft under any reading of this lot (23.7 ft if the 90.28 and 99.37 ft lines are the side lot lines).
- `[discrepancy 4.3]` **Rhino model:** the building fills the whole buildable area (2,169 sf, about 32.5% of the lot), over the 25% coverage limit.
- `[discrepancy 5.6]` **Workflow document:** says "the current example is within all limits", but coverage fails.

Also about the example:
- Where did your lot outline come from, and is there a survey? Your lot is 6,674.7 sf; the city's tax parcel is about 7,034 sf with a curved street side. (Zone confirmed R-1b: no overlays, not historic, not in a flood zone.)

---

## 8. What we need from you

1. **2–3 more worked examples in other districts** (for example R-2a, R-3a, and a two-family house), in the same format as 106 Ithaca Rd: the spreadsheet, the Rhino model, and your PASS/FAIL. Each one becomes an answer key that Gordium is graded against.
2. **Examples of the other documents you check** that aren't on your list (anything beyond the zoning map, zoning charts and Chapter 325).
3. **The chart symbols** (§5.1): confirm what •, - and SP mean.
4. **Past Ithaca projects with known city decisions** (permits, zoning board decisions), so we can test Gordium against real outcomes.

## 9. About scope and how you work

- Is the NYS Building Code (Chapter 5) needed in the first version, or only zoning?
- How long does a zoning check take you today?
- Your setup: Rhino version, Mac or Windows, plugins.
- How far around the site should the model show neighbours? (Your model shows about 400 ft each way.)
- Please skim `docs/how_rules_are_checked.md`, especially "Choices for the architects to confirm".
