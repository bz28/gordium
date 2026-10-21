# Questions for the architects

**Purpose:** the questions about the law that Gordium can't decide on its own, waiting on the architects or the City.\
**For:** the architects.\
**Kept current by:** whoever adds, researches or answers a question, in that same PR.

Gordium checks a design against the city's exact words. In the places below, the words can be read more than one way, and Gordium can't decide them on its own.

**Researched first.** Before a question reaches you, Gordium reads the whole law for it (every section that uses the word, or a word that means the same, from the term index), then the City's own decisions (zoning board records), then the building codes, then other cities. That research, on 2026-10-20, settled 20 of the 37 questions this page used to ask, narrowed 4 more to the part still open, and found 2 new ones (19 then left). The R-1a and R-3a answer keys (2026-10-20) raise 4 questions of their own (§5.3 to §5.6) and carry 3 law-wide ones into their own rules; the R-2a, R-2b and R-2c answer keys (2026-10-21) raise 2 more (§5.7, §5.8) and carry the same 3 into theirs, each tagged where it is recorded, so 40 are left (25 different questions). What it settled is listed in §6, with its sources, and recorded with each rule or definition (the full report is `docs/research/2026-10-20_architect_questions.md`). What is left below is what research couldn't settle. Each question says what was searched and why it is still open, and a test fails if a recorded question has no research behind it.

**Please note, until these are answered:** each question below says what Gordium does **today** and what it will do **from a model**, once it measures a Rhino model itself (being built now). There are three cases:
- **NEEDS REVIEW:** Gordium can't decide, so it says so instead of guessing.
- **Gordium assumes a reading:** where the law points one way, Gordium applies that reading and says which. That can give PASS, so please confirm the reading.
- **Not checked yet:** the rule isn't built yet; check it by hand.

Today, measurements are typed in by a person, and Gordium uses whatever number is typed. So for these questions **the person typing the number has to apply a reading by hand, and Gordium can still report PASS.**

From a model, where a question below lists readings, Gordium will check the design under **every** reading: PASS only if it passes under all of them, FAIL only if it fails under all of them, and NEEDS REVIEW otherwise. So an open question only holds up the designs where the answer actually matters (being built).

**How to read each question**
- **The city's words:** the exact text, with the section and a link to the page.
- **What research found:** what was searched, and why it doesn't settle the question.
- **Why it matters:** a real design where the answer changes the result.
- **Until you answer:** what Gordium does today, with typed-in numbers, and from a model.
- **Options:** the readings we can see. Pick one, or tell us another.
- 🔴 **Blocks R-1b today:** the question affects a check Gordium already runs on R-1b single-family houses (like 106 Ithaca Rd). Unmarked questions matter for other uses, other districts, or rules not built yet.

The tags in square brackets (for example lot_depth#1, the first question about lot depth) say where each question is recorded in Gordium's files. A test fails if a recorded question is missing from this page, so this page is always the complete list. The same questions are in the **Questions** tab of the rules spreadsheet (`ithaca_city_rules.xlsx`), with what was searched for each; what research settled is in its **Findings** tab.

Links to Chapter 325 open our stored copy of the city's PDF (for people with access to the Gordium repository); links to the zoning charts open the city's own website.

**The most important five** (answering these unblocks the most R-1b checks):
1. Where your 106 Ithaca Rd lot outline came from, and whether there is a stamped survey (§1.1)
2. One detail of the City's lot-depth method on an irregular lot like 106 Ithaca Rd (§1.2)
3. Whether roof eaves count toward lot coverage (§3.1)
4. Which eave a pitched roof's height is measured from (§4.1)
5. How the grade plane is averaged (§4.2)

---

## 1. The lot: area, width and depth

### 1.1 Where did your 106 Ithaca Rd lot outline come from? Is there a stamped survey? 🔴

- **What we found:** we compared the lot in your Rhino model with the city's tax parcel map (City of Ithaca `Tax_Parcels`, parcel 500700-84.-2-6; New York State's 2025 parcel layer has the same shape and size) and Tompkins County's 2026 parcel layer, both downloaded 2026-10-20. The County's outline, and the measurements we took from the City's, are kept with Gordium's test data (`test_data/test_sites/new_york/ithaca_city/106_ithaca_rd/gis/`); the City's data itself isn't stored: a precaution until we ask the City's GIS Program for permission, since its zoning layer's terms forbid redistributing the City's data without written consent (the parcel layer itself asks only for the statement below).

    | Edge | Your model | City / State GIS | County 2026 |
    |---|---|---|---|
    | Front (Ithaca Rd) | 73.00 ft, straight | 75.8 ft along a curve of 8 segments | 73.52 ft, straight |
    | Side (toward #104) | 90.28 ft | 92.12 ft | 92.00 ft |
    | Rear | 67.72 ft | 69.51 ft | 68.86 ft |
    | Jog | 10.47 ft | 10.35 ft | 10.35 ft |
    | Long side | 99.37 ft | 101.13 ft | 101.13 ft |
    | **Area** | **6,674.5 sf** | **7,033.7 sf** | **6,900.4 sf** |

    The shapes are the same lot, with the same jog, but each of your sides is about 2% shorter than the city's (90.28 vs 92.12, 67.72 vs 69.51, 99.37 vs 101.13 ft), and your area is 5% smaller. So your lot looks like the city's parcel drawn **slightly too small**: a scaling slip while tracing, or a survey that differs from the tax map. Even the two official maps disagree with each other, by about 133 sf. (Your model's lot measures 6,674.5 sf as drawn; your spreadsheet types 6,674 sf (Inputs!B5), and your workflow document says 6,675 sf.)

    *City outline: "Data contained in this product was amended by the GIS Program, City of Ithaca, NY from a file created by Tompkins County Assessment Office. The originators do not warrant the accuracy or completeness of the information portrayed by the data."*
- **Why it matters:** lot area, lot depth (and so the rear yard, §1.2), and frontage all come from this outline. Coverage fails under every version (1,855 sf against 25% of 6,674, 6,900 or 7,034 sf), but the rear yard depends on both the outline and how depth is measured: see §1.2.
- **Until you answer:** Today, Gordium uses the lot area and depth it is given (yours). From a model, the lot drawn in the model is measured, and without a survey lot size and coverage get NEEDS REVIEW (§1.3). A GIS outline is only ever a cross-check: it never turns a result into a PASS.
- **Please tell us:** (a) where the model's lot outline came from (a survey, traced from the tax map, or something else); (b) whether a stamped survey exists, and if so, could we have a copy?


### 1.2 Lot depth on a lot with more than four sides: one detail of the City's method 🔴
`[lot_depth#1]` `[R-1b.rear_yard#1]` `[R-1a.rear_yard#1]` `[R-2a.rear_yard#1]` `[R-2b.rear_yard#1]` `[R-2c.rear_yard#1]` `[R-3a.rear_yard#1]`

- **The city's words:** "Such percentage shall be taken of the lot depth. If the two side lot lines are of unequal lengths, the rear yard percentage shall be taken of the average of the two lengths." ([Chapter 325 §325-8A(14), p.25](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=25))
- **What research found:** the City has a method. On a five-sided lot (BZA Appeal #3202, 815 S. Aurora St, 2019–2022), the Zoning Administrator swore that "side lot lines should be drawn at a 90-degree angle perpendicular to the front lot line to determine the average lot depth", from each end of the front lot line "to the furthest rear line" ([staff memo and affidavit](https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_02012022-2446)). Gordium now uses that method (§6): on the County outline, (92.01 + 100.28) ÷ 2 = 96.15 ft, so the rear yard must be 24.04 ft and the 25 ft design passes. The one detail left: the perpendicular from the long-side end first meets the jog. The affidavit's own drawing stops at the first rear-facing line, but "the furthest rear line" could mean the main rear line, and the zoning board's written decision wasn't found online.
- **Why it matters:** the R-1b rear yard is 25% of the lot depth (at most 50 ft, at least 20 ft). 106 Ithaca Rd has five sides, including a 10.47 ft jog. Before the City's method was found, these were the readings we could see. On your model's lot they give very different answers for the rear yard your design must have (it has 25 ft):

    | Option | Lot depth | Required rear yard | The 25 ft design |
    |---|---|---|---|
    | (a) the 90.28 and 99.37 ft lines | 94.8 ft | 23.7 ft | PASS |
    | (b) the jog added to the 99.37 ft line it continues | (90.28 + 109.84) ÷ 2 = 100.06 ft | 25.015 ft | **FAIL** (by 0.015 ft) |
    | (c) average of every line that isn't front or rear | (90.28 + 10.47 + 99.37) ÷ 3 = 66.7 ft | 20 ft (the minimum) | PASS |

    And on the city's GIS outline (§1.1), the depth also depends on which outline is used:

    | Lot depth used | Required rear yard | The 25 ft design |
    |---|---|---|
    | 90 ft (your spreadsheet) | 22.5 ft | PASS |
    | 92 ft (assessor's depth; the short side in GIS) | 23.0 ft | PASS |
    | 96.6 ft (average of the two GIS sides) | 24.2 ft | PASS |
    | 101.13 ft (the long side in GIS) | 25.3 ft | **FAIL** |

    On your model's lot, the City's method gives about 94 ft (a 23.5 ft rear yard), close to (a); continuing to the main rear line would be close to (b).
- **Until you answer:** Today, the rear-yard rule uses whatever lot depth it is given. From a model, Gordium measures the lot depth more than one way and gives NEEDS REVIEW on the rear yard when the answers disagree; it will measure the City's method both ways (stopping at the jog, and continuing to the main rear line) (being built).
- **Options:** (a) the perpendicular stops at the first rear-facing line it meets (the jog); (b) it continues to the main rear line, extended; (c) another rule you use. If you can, ask the City for the zoning board's written resolution on Appeal #3202 (February 2022).

### 1.3 What "lot area" should be used, especially without a survey? 🔴
`[lot#1]` `[R-1b.lot_coverage#1]` `[R-1a.lot_coverage#1]` `[R-2a.lot_coverage#1]` `[R-2b.lot_coverage#1]` `[R-2c.lot_coverage#1]` `[R-3a.lot_coverage#1]`

- **The city's words:** "LOT — A portion or parcel of land, considered as a unit, devoted to a certain use or occupied by a building or a group of buildings…" (§325-3, [p.14](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=14)). Chapter 325 never defines "lot area" itself.
- **What research found:** "lot area" is never defined and the word "survey" never appears in Chapter 325. The City works from surveys when it has them (the 2026 Sears St cases turned on an as-built survey), but no City document says what to use without one. Coverage also waits on §3.1 (eaves); garages count (§6).
- **Why it matters:** the R-1b coverage limit is 25% of lot area. 106 Ithaca Rd is about 7,034 sf on the city's tax map, but 6,674 sf in your spreadsheet (6,674.5 sf as drawn in your model). That moves the limit from 1,669 sf to 1,759 sf, and the 1,855 sf house fails under both.
- **Until you answer:** Today, coverage and lot size use the lot area they are given (for 106 Ithaca Rd, your 6,674 sf). From a model, a lot with no survey gets NEEDS REVIEW on lot size and coverage unless every area (the model's and the tax map's) gives the same answer, because the drawn area may not be the legal one (as 106 Ithaca Rd shows, §1.1).
- **Options:** (a) always the survey, and NEEDS REVIEW if there isn't one; (b) the survey if there is one, else the tax map; (c) whatever is drawn in the model, with a warning to check it against a survey. (Or a question for the City: "For a zoning review, do you require a stamped survey for lot area, and if none exists, what do you accept?")

### 1.4 Lot width on a curved street 🔴
`[lot_width#1]`

- **The city's words:** "Lots hereafter used for a permitted use in each use district shall have frontage measured on a public right-of-way equal to or greater than the width specified in this column…" (Column 7, [§325-8A, p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24))
- **What research found:** "width at street line" and "frontage measured on a public right-of-way" point to the street line, but never say along the curve or straight. The City's worksheets give one number without a method, and other places split (some use the curve, some the straight line).
- **Why it matters:** R-1b requires 50 ft of frontage for a one-family house. In the city's GIS, 106 Ithaca Rd's street edge is a curve of 8 segments, 75.8 ft along the curve (your model draws one straight 73 ft line). A curve is always longer than the straight line between its ends, so a lot just under 50 ft could pass one way and fail the other. (106 Ithaca Rd passes either way.)
- **Until you answer:** Today, lot width uses the number it is given (your 73 ft), so a curved street line must be measured by hand. From a model, a curved street line gets NEEDS REVIEW on lot width unless both ways give the same answer.
- **Options:** (a) along the curve; (b) the straight line between the two side lot corners.

---

## 2. Yards

### 2.1 Is a bay window a projection, or part of the building? 🔴
`[yard_projections#1]`

- **The city's words:** "The space in any required yard shall be open and unobstructed except for ordinary projections of windowsills, belt courses, cornices, eaves and other architectural features; provided, however, that such features shall not project more than two feet into any required yard." ([§325-18B, p.49](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=49))
- **What research found:** this sentence settles the old question of wall or eave (§6): yards are measured to the nearest part of the building, and sills, cornices and eaves may project up to 2 ft into a yard. Only the newer form-district rules name bay windows ("Overhanging eaves and bay windows may project up to two feet into any required setback", §325-45.2B, p.131); the residential rules don't, and no City record was found.
- **Why it matters:** a 2 ft bay window on a house 10 ft from the side line is either allowed (a projection) or leaves an 8 ft side yard (part of the building).
- **Until you answer:** Today, yards use the numbers they are given, so a bay window must be measured by hand. From a model, a bay window inside a required yard gets NEEDS REVIEW on that yard unless both readings give the same answer (being built).
- **Options:** (a) a projection, allowed up to 2 ft into the yard like an eave; (b) part of the building: the yard is measured to it.

---

## 3. Lot coverage

### 3.1 Do roof eaves count toward lot coverage? 🔴
`[building_area#1]`

- **The city's words:** "no greater percentage of total lot area may be covered by principal and accessory buildings above ground" (Column 10, [§325-8A, p.25](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=25)).
- **What research found:** coverage is the outline, seen from above, of everything above ground: cantilevered floors, porches, decks, balconies over 2 ft (§6). Garages count (§6). Nothing says whether roof eaves count. Leaving out eaves up to 2 ft would follow §325-18B and the 2 ft balcony threshold, but only by analogy, and no City record was found.
- **Why it matters:** an 18-inch eave around a 53 × 35 ft house adds about 270 sf seen from above, enough to decide PASS or FAIL on a small lot.
- **Until you answer:** Today, coverage uses the building area it is given. From a model, a building with eaves gets NEEDS REVIEW on coverage unless every reading gives the same answer (being built).
- **Options:** (a) eaves don't count; (b) only the part of an eave beyond 2 ft counts; (c) eaves count in full.

---

## 4. Height, grade, stories and basements

### 4.1 A pitched roof's height: which eave? 🔴
`[height_of_building#1]`

- **The city's words:** "HEIGHT OF BUILDING — [T]he vertical distance measured from grade plane to the highest level of a flat or mansard roof or to the average height of a pitched, gabled, hip or gambrel roof… Where a building contains sections of a roof of varying heights, the height of that building shall be measured using that section of the roof that has the highest elevation from grade plane." (§325-3, [p.12](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=12))
- **What research found:** Gordium reads "average height" as midway between eave and ridge, on the highest roof section (§6: the building codes' "mean roof height" and other New York villages use it). Where the eave is taken is not settled: the building codes use the eave, Scarsdale uses the top of the wall plate, and no City record states a method.
- **Why it matters:** R-1b allows 35 ft. On a steep roof the choices can differ by 1–2 ft (the research report's estimate), enough to decide PASS or FAIL near the limit.
- **Until you answer:** Today, height uses the number it is given (your 35 ft). From a model, a flat roof is measured to the top and a pitched roof gets NEEDS REVIEW unless every eave choice gives the same answer (being built).
- **Options:** (a) the lowest eave of that roof section; (b) the top of the wall plate; (c) the roof edge (drip line). And with eaves at different heights on the same section, which one?

### 4.2 How is the grade plane averaged? 🔴
`[grade_plane#1]` `[grade_plane#2]`

- **The city's words:** "GRADE PLANE — A reference plane representing the average of finished ground level on each side of the building at exterior walls." (§325-3, [p.11](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=11))
- **What research found:** the definition fixes where the ground is measured (at the walls; where it slopes away, the lowest point within 6 ft or the lot line), but not how to average. It is the model building code's definition, and that code's own handbook says the method "can vary based on the site conditions". Other places weight by wall length. No City record states a method.
- **Why it matters:** height is measured from the grade plane, and a basement counts as a story when its ceiling is more than 6 ft above it. On a sloped lot, the averaging method moves the grade plane by a foot or more.
- **Until you answer:** Today, height and stories use the numbers they are given. From a model, level ground leaves nothing to decide, and sloped ground gets NEEDS REVIEW on height and stories unless every method gives the same answer.
- **Options for averaging:** (a) one value per side, simple average; (b) weighted by the length of each wall.
- **Options for "a side" of an L-shaped or irregular house:** (a) each wall segment; (b) the four sides of the smallest rectangle around the house; (c) another rule.

### 4.3 Stories: which entrance is the "main entrance", and does it limit the 12 ft test?
`[story#1]` `[story#2]`

- **The city's words:** "Buildings hereafter erected shall be limited to the number of stories herein specified, computed at the main entrance side." ([§325-8A, p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)). And: "A basement shall be deemed to be a story when the finished surface of the floor next above is 1) more than six feet above grade plane or 2) more than 12 feet above the finished ground level at any point." (§325-3, [p.19](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=19))
- **What research found:** "main entrance" is never defined: it appears once in Chapter 325, and the form districts' "functioning entry" doesn't apply here. The 12 ft test's "at any point", like the building code's same test, points to every side, but stories are "computed at the main entrance side", which may limit the count to that side; nothing says which governs. No City record was found.
- **Why it matters:** R-1b allows 3 stories. A house on a slope can be 3 stories at the street and 4 at the back.
- **Until you answer:** Today, stories use the number they are given (your 3). From a model, a sloped site gets NEEDS REVIEW on stories unless every reading gives the same answer.
- **Options:** for the main entrance: (a) the entrance facing the street the address is on; (b) the one the designer names. For the 12 ft test: (a) any point on any side; (b) only the main entrance side.

### 4.4 Basement or cellar, when a space fits both?
`[basement#1]` `[basement#2]` `[cellar#1]` `[cellar#2]`

- **The city's words:** "BASEMENT — That space of a building that is partly below grade which has more than half of its height, measured from floor to ceiling, above the finished ground level at any point." (§325-3, [p.5](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=5)). "CELLAR — That space of a building that is partly or entirely below grade which has more than half of its height… below the average established curb level or finished grade of the ground adjoining the building." (§325-3, [p.6](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=6))
- **What research found:** a walk-out level can fit both, and nothing says which wins. The building codes have no cellar exemption at all (any level that meets the story tests is a story), so this exemption is Ithaca's own and the codes can't settle it. No City record was found.
- **Why it matters:** a basement can count as a story; a cellar never does.
- **Until you answer:** Today, stories use the number they are given. From a model, any lower level on a sloped site gets NEEDS REVIEW on stories unless every reading gives the same answer.
- **Options:** for "at any point" in the basement definition: (a) more than half above ground at one point is enough; (b) at every point around the building. For a space that fits both: (a) a basement (it counts as a story if the floor above meets the 6 ft or 12 ft test); (b) a cellar. And for the cellar test, the curb level or the average adjoining grade when they differ?

### 4.5 A parapet on top of the height bonus?
`[R-1b.height#1]` `[R-1a.height#1]` `[R-2a.height#1]` `[R-2b.height#1]` `[R-2c.height#1]` `[R-3a.height#1]`

- **The city's words:** "a parapet wall or cornice for ornament extending above such height five feet or less" (§325-16B, [p.47](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=47)).
- **What research found:** the exemptions for chimneys, spires and parapets change what may stand above the limit, not how height is measured (§6). Whether "such height" means the chart's limit or the bonus height §325-16C allows isn't said, nor whether a parapet that guards a roof deck (not "for ornament") counts. No City record was found.
- **Why it matters:** decides whether a parapet can sit on top of a house that already uses the height bonus.
- **Until you answer:** Today, these features are not checked yet (§325-16A and B will become rules of their own): check them by hand. From a model, a building with a parapet, chimney or similar feature above its roof gets NEEDS REVIEW on height.
- **Options:** (a) the 5 ft is measured from the chart's limit (the stricter reading); (b) from the bonus height.

---

## 5. Accessory buildings, accessory dwelling units, and the R-3a and R-2c districts

### 5.1 An accessory building that isn't frame; a height limit?
`[325-25C#1]`

- **The city's words:** "C. Frame accessory buildings. Frame accessory buildings may not be placed less than three feet from any side lot line or rear lot line in all districts, except in R-1 Districts, where accessory buildings may not be placed less than six feet from any side lot line nor less than three feet from any rear lot line…" (§325-25C, [p.67](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=67)).
- **What research found:** the chart's side yards don't apply to garages and sheds; §325-25 does (§6). The first sentence sets distances for "frame" buildings. The R-1 clause says "accessory buildings" without "frame", but the subsection is headed "Frame accessory buildings", so whether it covers other buildings isn't settled. §325-25 sets no height limit (detached ADUs have their own). Nothing else in the code or the City's records fills the gap.
- **Why it matters:** outside R-1, a masonry garage could otherwise sit on the lot line; in R-1 (and R-1b, like 106 Ithaca Rd) it may or may not have to keep 6 ft from the side line. And no accessory building has a height limit.
- **Until you answer:** Today, accessory buildings are not checked yet: check them by hand. From a model, an accessory building that isn't frame gets NEEDS REVIEW on its distances (being built).
- **Options:** (a) the frame distances apply to every accessory building; (b) in R-1, the 6 ft side / 3 ft rear distances apply to every accessory building, elsewhere only to frame ones; (c) only "not in a required front yard" applies to a building that isn't frame. And is there a height limit for accessory buildings other than ADUs?

### 5.2 Which front yard is the "primary front yard" for an ADU on a corner lot?
`[325-28C#1]`

- **The city's words:** §325-28C ([p.72](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=72)) keeps an ADU out of the "primary front yard" and gives a detached ADU the main building's setback on the "secondary front yard".
- **What research found:** "primary" and "secondary" front yard are never defined. The yard on the street the address is on (as §325-8A(14)(d) uses it to pick the rear yard) is a plausible reading, but weak.
- **Why it matters:** on a corner lot, it decides where an ADU may go.
- **Until you answer:** Today, ADUs are not checked yet: check them by hand. The same applies from a model until ADU rules are built.
- **Options:** (a) the front yard on the street the address is on; (b) the one the designer names.

### 5.3 R-3a: lot size for a dormitory or a nursing home
`[R-3a.lot_area_other_use#1]`

- **The city's words:** "DORMITORY — A multiple dwelling which provides sleeping accommodations…" and "(4) A building used or occupied as a convalescent, old-age or nursing home" under DWELLING, MULTIPLE (§325-3, [p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7)). The chart's lot-size rows (p.3) have "Multiple family dwelling" (6,000 sf, note 7: "+750 sf for each additional unit; +500 sf per room let for profit") and "Other use" (6,000 sf), but no dormitory or nursing-home row.
- **What research found:** the definitions make both multiple dwellings, but the chart lists them as uses of their own and gives the fraternity house (also a multiple dwelling) its own row, which suggests a use with no row is an "Other use". No City record found.
- **Why it matters:** a 40-bed dormitory on a 7,000 sf R-3a lot passes as an "Other use" but may need far more under note 7.
- **Until you answer:** Today and from a model, a dormitory or nursing home on a lot under 6,000 sf fails (both readings agree), and on a larger lot gets NEEDS REVIEW (R-3a.lot_area_other_use).
- **Options:** (a) the multiple-family row and note 7 apply; (b) "Other use" applies (6,000 sf).

### 5.4 R-3a: lot size and width for a zero-lot-line house
`[R-3a.lot_size_zero_lot_line#1]`

- **The city's words:** the chart marks "One-family dwelling, detached, zero lot line" SP for R-3A (p.2), but its R-3A lot-size and lot-width cells are "-" (p.3). §325-8B(4): a special-permit use takes "the regulations … of whichever district has the stricter regulations" where it "is permitted by right in another district" ([p.26](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=26)).
- **What research found:** no residential district permits the use by right (R-2C, R-3A, R-3AA and R-3B mark it SP; the rest "-"), so §325-8B(4) has nothing to borrow, and §325-9B(1) doesn't list it. No City record found.
- **Why it matters:** it decides whether a zero-lot-line house on a 4,000 sf, 35 ft wide R-3a lot can even be proposed.
- **Until you answer:** Today and from a model, a zero-lot-line house in R-3a gets NEEDS REVIEW (it needs a special permit anyway).
- **Options:** (a) no minimum; (b) the "Other use" rows (6,000 sf, 50 ft); (c) whatever the Planning and Development Board sets with the special permit.

### 5.5 R-3a next to R-1: does land across a street "directly abut"?
`[R-3a.abutting_r1#1]`

- **The city's words:** "E. Development in R-3 Districts which abut R-1 Districts. The development of any permitted use in the R-3a or R-3b Zoning District, except a one-family or two-family dwelling, shall be subject to the following special conditions if the land on which the development occurs directly abuts land in either the R-1a or R-1b Zoning District" (§325-19E, [p.50](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=50)): 150% lot size, R-1's height, 75% coverage, 150% side and rear yards where they abut R-1 land.
- **What research found:** §325-9B(1)(j) says "abutting or across a street", treating the two as different; §325-11B says "abuts land, other than a public right-of-way", implying street land can abut; a district boundary may follow a street's center line or its edge (§325-6A). "Directly" isn't defined. No City record found.
- **Why it matters:** an apartment building on an R-3a lot facing R-1 houses across the street is limited to 35 ft instead of 40 ft (and likely 3 stories instead of 4) and 26.25% coverage instead of 35%, or not, depending on the answer.
- **Until you answer:** Today and from a model, every R-3a use §325-19E covers gets NEEDS REVIEW (R-3a.abutting_r1), since Gordium doesn't know the zoning of the land next to the lot.
- **Options:** (a) only R-1a or R-1b land sharing a lot line counts; (b) R-1a or R-1b land across a street counts too.

### 5.6 R-3a next to R-1: is a row of attached houses exempt from §325-19E?
`[R-3a.abutting_r1#2]`

- **The city's words:** §325-19E exempts "a one-family or two-family dwelling" ([p.50](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=50)). §325-3: "A one-family dwelling may be constructed in any of the following configurations", including "ONE-FAMILY ATTACHED DWELLING — A building containing three or more one-family dwellings"; but also "DWELLING, MULTIPLE … (1) A building containing three or more dwelling units … (5) … row house, townhouse" ([p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7), [p.8](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=8)).
- **What research found:** the definitions point both ways, and no City record was found. Semi-detached and zero-lot-line houses (at most two dwellings) are clearly one-family configurations and are exempt.
- **Why it matters:** a row of five townhouses on an R-3a lot next to R-1 houses may be held to 35 ft and 26.25% coverage, or to R-3a's 40 ft and 35%.
- **Until you answer:** Today and from a model, attached houses in R-3a get NEEDS REVIEW on §325-19E (R-3a.abutting_r1), as every use it may cover does.
- **Options:** (a) exempt, as a one-family configuration; (b) covered, as a multiple dwelling.

### 5.7 R-2c: an attached house with more than five occupants in one unit
`[R-2c.lot_area_one_family_attached#1]`

- **The city's words:** chart note 6, for R-2C's attached houses: "(6) For the first occupant in each dwelling unit; +300 sf for each additional occupant in each dwelling unit; +500 sf for each additional occupant in each dwelling unit in excess of five occupants." (zoning charts, April 2026, p.3). "Occupant" is defined for R-2c only: a person with the right to occupy (§325-3, [p.16](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=16)).
- **What research found:** the note lists both additions with "+" and never says "instead"; every occupant past five is also an "additional occupant", so the 300 sf can be read to apply to them too. Nothing else in Chapter 325 says which, and no City record was found (2026-10-21).
- **Why it matters:** a three-unit row house with seven occupants in one unit and one in each of the others needs 4,500 + 4 × 300 + 2 × 500 = 6,700 sf if the two occupants past five cost 500 sf instead of 300 sf, or 4,500 + 6 × 300 + 2 × 500 = 7,300 sf if they cost both.
- **Until you answer:** Today and from a model, whenever one unit could hold more than five occupants (the building's occupants minus its units is 5 or more) and the lot meets every reading's least, the row gets NEEDS REVIEW (R-2c.lot_area_one_family_attached); the use needs a special permit in R-2c anyway.
- **Options:** (a) each occupant past five adds 500 sf instead of 300 sf; (b) it adds 500 sf on top of the 300 sf (800 sf).

### 5.8 R-2c: the narrow side yard of a semi-detached or attached building
`[R-2c.side_yards#1]`

- **The city's words:** chart notes 14 and 15, for R-2C's side yards ("10 ft /15 ft" one side, "0 ft /5 ft / 10 ft" the other): "(14) The first number applies to one-family detached dwellings, one-family semi-detached dwellings (unattached sides only), one-family attached dwelling (unattached sides only), two-family dwellings, and other uses; the second number applies to one-family detached zero lot line dwellings." "(15) The first number applies to one-family detached zero lot line dwellings and one-family semi-detached dwellings with attached sides; the second number applies to one-family detached dwellings, two-family dwellings, and other uses; …" (zoning charts, April 2026, p.3).
- **What research found:** note 14 gives every unattached side of a semi-detached or attached building 10 ft (Column 12: "one side yard"), and note 15 gives a semi-detached house's attached side 0 ft; but the 5 ft is given only to detached and two-family houses and other uses, and the attached building isn't in note 15 at all. So a semi-detached building standing whole on one lot (two unattached sides), or an attached building's sides, have no stated "other side" figure. No City record was found (2026-10-21).
- **Why it matters:** a semi-detached building on one R-2c lot with 10 ft on one side and 5 ft on the other complies if the second side is 5 ft or 0 ft, and not if every unattached side needs 10 ft.
- **Until you answer:** Today and from a model, a semi-detached or attached building in R-2c complies on side yards only with 10 ft on both sides; under 10 ft on its narrower side gets NEEDS REVIEW (R-2c.side_yards), as it also does because Gordium can't tell which side is the party wall. Under 10 ft on the wider side does not comply.
- **Options:** (a) every unattached side 10 ft; (b) the second side 5 ft, as for a two-family house; (c) 0 ft, note 15's figure for semi-detached dwellings.

---

## 6. What research already settled (please skim; tell us if you disagree)

These were questions on this page. Research answered them, so Gordium uses the answer and shows its source. **The law** means the code's own words answer it. **Gordium's reading · confirm with the zoning office** means the code doesn't spell it out, but the sources support one reading; it is labeled as a reading wherever Gordium shows it, and your answer or the City's outranks it. How sure: *strong* = the code's own text; *City practice* = the City's own decisions; *moderate* = the building codes; *weak* = other cities only. Each is recorded with its rule or definition, and in the spreadsheet's **Findings** tab.

| Was | What Gordium uses now | Kind | Source |
|---|---|---|---|
| Lot depth on an irregular lot (§1.2 before) | Side lot lines drawn at 90° to the front lot line, from each end to the furthest rear line; depth = their average. One detail is still open (§1.2) | Reading · City practice | Zoning Administrator, BZA Appeal #3202 (2019–2022) |
| Lot depth when the side lines are equal | That length (the averaging is only for unequal lines); on a skewed lot, the City's 90° method above | The law | §325-8A(14)(a), p.25 |
| Yards: to the wall or the eave? | To the nearest part of the building (walls, overhanging floors, porches, decks, balconies over 2 ft, ramps, landings). Sills, cornices and eaves may project up to 2 ft into a yard; more is a violation of that yard | The law | §325-18B, p.49; §325-3 SIDE YARD, p.20; City practice: 132 Cherry St (2026) |
| Porch steps and stair walls | Count as part of the building for yards and coverage | Reading · City practice | 209 Bryant Ave (R-1b, 2022), 511 S. Plain St (2021) |
| Corner lots: a front yard on each street | Yes, every street-facing yard is a front yard. Typed-in numbers can't show a corner lot yet: check corner lots by hand | The law | §325-19C, p.50; §325-25A, p.66 |
| Corner lots: the side yard left | Checked against Column 13 ("other side"); Column 12's place becomes the second front yard (in R-1b both are 10 ft) | Reading · City practice | BZA worksheets #3174 (2021), ZONE-25-12 (2026) |
| Side yards for a detached garage or shed | The chart's side yards apply to the main building only; garages and sheds follow §325-25 (not in a required front yard; frame ones 3 ft from side and rear lines; in R-1, 6 ft side and 3 ft rear, and whether that covers buildings that aren't frame is §5.1). Not checked yet: they will be rules of their own | The law | §325-25, pp.66–67 |
| An attached garage | Part of the main building, so the chart's yards apply | Reading · City practice | 409 Campbell Ave (2014) |
| What may be in the rear yard | Accessory buildings (§325-25), detached ADUs (§325-28C), eaves up to 2 ft (§325-18B), patios at grade, parking (§325-20F); porches, decks, ramps and landings are part of the building (§325-18A). Each will be a rule of its own | The law | §325-3 YARD, REAR YARD, p.20 and the sections named |
| Does a garage count toward coverage? | Yes, attached or detached, and carports; "parking areas and parking spaces" means open parking | Reading · City practice | §325-3 BUILDING AREA, p.5; 412 E. Yates St (2018) |
| Footprint at the ground, or from above? | The outline from above of everything above ground; parts wholly below ground don't count. Roof eaves are still open (§3.1) | Reading · strong | Column 10 "above ground", p.25; §325-18A |
| Pitched-roof height | Midway between eave and ridge, on the highest roof section; a mansard to its top. Which eave is still open (§4.1) | Reading · moderate | §325-3, p.12; the building codes' "mean roof height" |
| Height bonus: which yards grow | Every required front, side and rear yard, one foot per foot of extra height; main buildings only; stories still capped; at most 10% | The law | §325-16C, p.47 |
| Chimneys, spires, skylights above the limit | They don't change how height is measured; each covers at most 20% of the ground floor or 30% of its roof plane | The law | §325-16A, p.46 |
| The typo "he vertical distance" | Read as "The" | The law | §325-3, p.12 |
| The chart's marks | • permitted, - not permitted, SP needs a special permit (NEEDS REVIEW) | Reading · strong | §325-8A(2), §325-8B(3), §325-9B(1) |
| "Public utility structure" = "public utility facilities" | The same use; a special permit either way | Reading · strong | chart p.2, §325-9B(1)(c) |
| Can a permitted (•) use still need review? | Yes: Article V's regulations still apply, as rules of their own | The law | §325-8A(2), p.24 |
| Parking for a house with an ADU | An ADU needs no off-street parking | The law | §325-28C(2), p.72 |
| Five definitions with numbers (adult day-care home, bed-and-breakfast inn, kitchen, dwelling unit, rooming unit) | Categories: the number says what to call something, and the use rules judge the rest. Dwelling unit and rooming unit stay labeled "rule": a design that claims one must have it, which gives the same result | Reading · strong | how §325-3 and the operative sections are built |

---

## 7. Your 106 Ithaca Rd example

We checked your worked example against the city's documents. The full list is in `docs/discrepancies_with_architects.md`. These are the items that change a PASS/FAIL result, and we'd like you to confirm each:

- `[discrepancy 2.1]` **Coverage:** the spreadsheet's comparison column says "Within table limit", but 53 × 35 = 1,855 sf is 27.8% of the lot, over the 25% limit. (Its PASS/FAIL column correctly says FAIL.)
- `[discrepancy 2.2]` **Rear yard:** the spreadsheet compares the *required* rear yard (22.5 ft) with the 20 ft minimum, instead of the house's *actual* rear distance (25 ft). It passes by coincidence.
- `[discrepancy 3.1]` **Coverage counts more than the house:** porches, decks, balconies over 2 ft, ramps and landings count too (§325-3, §325-18A).
- `[discrepancy 4.1]` **Rhino model:** the building sits about 76 ft away from the buildable area; all four corners are outside the lot. Intended as a test, or a mistake?
- `[discrepancy 4.2]` **Rhino model:** the rear setback is drawn at 20 ft. Only one reading of this lot's depth allows 20 ft (§1.2, option c); the others require 23.7 ft or 25.015 ft. Which did you intend?
- `[discrepancy 4.3]` **Rhino model:** the building fills the whole buildable area (2,169 sf, about 32.5% of the lot), over the 25% coverage limit.
- `[discrepancy 5.6]` **Workflow document:** says "the current example is within all limits", but coverage fails.

Also about the example: where your lot outline came from, and whether there is a survey, is §1.1. (Zone confirmed R-1b: no overlays, not historic, not in a flood zone.)

---

## 8. What we need from you

1. **2–3 more worked examples in other districts** (for example R-2a, R-3a, and a two-family house), in the same format as 106 Ithaca Rd: the spreadsheet, the Rhino model, and your PASS/FAIL. Each one becomes an answer key that Gordium is graded against.
2. **Examples of the other documents you check** that aren't on your list (anything beyond the zoning map, zoning charts and Chapter 325).
3. **The readings in §6** marked *City practice* or *reading*: tell us if you read any of them differently.
4. **Past Ithaca projects with known city decisions** (permits, zoning board decisions), so we can test Gordium against real outcomes.
5. **Confirm 96 Ithaca Rd is a corner lot** (Ithaca Rd and Mitchell St), as the address lookup finds. If so, both street sides need front yards (§6).

## 9. About scope and how you work

- Is the NYS Building Code (Chapter 5) needed in the first version, or only zoning?
- How long does a zoning check take you today?
- Your setup: Rhino version, Mac or Windows, plugins.
- How far around the site should the model show neighbours? (Your model shows about 400 ft each way.)
- Please skim `docs/how_rules_are_checked.md`, especially "Choices for the architects to confirm".
