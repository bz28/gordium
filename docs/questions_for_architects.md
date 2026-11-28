# Questions for the architects

**Purpose:** the questions about the law that Gordium can't decide on its own, waiting on the architects or the City.\
**For:** the architects.\
**Kept current by:** whoever adds, researches or answers a question, in that same PR.

Gordium checks a design against the city's exact words. In the places below, the words can be read more than one way, and Gordium can't decide them on its own.

**Researched first.** Before a question reaches you, Gordium reads the whole law for it (every section that uses the word, or a word that means the same, from the term index), then the City's own decisions (zoning board records), then the building codes, then other cities. That research, on 2026-10-20, settled 20 of the 37 questions this page used to ask, narrowed 4 more to the part still open, and found 2 new ones (19 then left). The R-1a and R-3a answer keys (2026-10-20) raise 4 questions of their own (§5.3 to §5.6) and carry 3 law-wide ones into their own rules; the R-2a, R-2b and R-2c answer keys (2026-10-21) raise 3 more (§5.7 to §5.9) and carry the same 3 into theirs; the R-3aa, R-3b and RU answer keys (2026-10-25) raise 5 more (§5.10 to §5.14) and carry 7 earlier ones into their own rules (§1.2, §1.3, §4.5, §5.3 to §5.6), each tagged where it is recorded; the occupancy rules (2026-10-27) raise 2 more (§5.15, recorded in 7 districts' rules, and §5.16, in R-1a and R-1b); the coverage audit's gaps (2026-10-27) raise 1 more (§5.17, recorded in all 9 districts' rules); the private garage's car limit (2026-10-29) raises 2 more (§5.18, recorded in 4 districts' rules, and §5.19, in R-2c); the accessory dwelling unit rules (2026-10-29) raise 3 more (§5.20, recorded in 8 districts' rules, §5.21, in R-1a and R-1b, and §5.22, in R-2c), and a bed-and-breakfast inn in R-1 and R-2 (2026-10-29) raises 1 more (§5.23, recorded in 5 districts' rules); the commercial districts' rulebooks (B-1a, B-1b, B-2a, B-2d, B-4, B-5, 2026-11-22) raise 6 more (§5.24 to §5.29); the central business districts' rulebooks (CBD-50 to CBD-140, 2026-11-23) carry 5 of them into their own rules (§5.24 to §5.28, 29 more), and the City's online map raises 1 for the City zoning office (§5.30, CBD-52), so 147 are left (47 different questions). What it settled is listed in §6, with its sources, and recorded with each rule or definition (the full report is `docs/research/2026-10-20_architect_questions.md`). What is left below is what research couldn't settle. Each question says what was searched and why it is still open, and a test fails if a recorded question has no research behind it.

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
`[lot_depth#1]` `[R-1b.rear_yard#1]` `[R-1a.rear_yard#1]` `[R-2a.rear_yard#1]` `[R-2b.rear_yard#1]` `[R-2c.rear_yard#1]` `[R-3a.rear_yard#1]` `[R-3aa.rear_yard#1]` `[R-3b.rear_yard#1]` `[RU.rear_yard#1]`

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
`[lot#1]` `[R-1b.lot_coverage#1]` `[R-1a.lot_coverage#1]` `[R-2a.lot_coverage#1]` `[R-2b.lot_coverage#1]` `[R-2c.lot_coverage#1]` `[R-3a.lot_coverage#1]` `[R-3aa.lot_coverage#1]` `[R-3b.lot_coverage#1]` `[RU.lot_coverage#1]`

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
`[R-1b.height#1]` `[R-1a.height#1]` `[R-2a.height#1]` `[R-2b.height#1]` `[R-2c.height#1]` `[R-3a.height#1]` `[R-3aa.height#1]` `[R-3b.height#1]` `[RU.height#1]`

- **The city's words:** "a parapet wall or cornice for ornament extending above such height five feet or less" (§325-16B, [p.47](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=47)).
- **What research found:** the exemptions for chimneys, spires and parapets change what may stand above the limit, not how height is measured (§6). Whether "such height" means the chart's limit or the bonus height §325-16C allows isn't said, nor whether a parapet that guards a roof deck (not "for ornament") counts. No City record was found.
- **Why it matters:** decides whether a parapet can sit on top of a house that already uses the height bonus.
- **Until you answer:** Today, these features are not checked yet (§325-16A and B will become rules of their own): check them by hand. From a model, a building with a parapet, chimney or similar feature above its roof gets NEEDS REVIEW on height.
- **Options:** (a) the 5 ft is measured from the chart's limit (the stricter reading); (b) from the bonus height.

### 4.6 A basement escape window in a window well: is "grade" the well's floor or the ground around the well?

- **The code's words** (2025 Residential Code of New York State; Ithaca's own code doesn't cover escape windows): a grade-floor escape opening is one "located such that the bottom of the clear opening is not more than 44 inches (1118 mm) above or below the finished ground level adjacent to the opening" (Definitions, p.21), and it may be 5 sq ft instead of 5.7 (R319.2.1 Exception, p.79). "GRADE. The finished ground level adjoining the building at all exterior walls." (p.21). "An emergency escape and rescue opening where the bottom of the clear opening is below the adjacent grade shall be provided with an area well" (R319.4, p.80).
- **What research found:** Ithaca's zoning code has no escape-window rules, and no City or zoning board record touches this (escape windows are state building code, enforced by the City's building division). The state code's own words point both ways: the well's floor is "finished ground level adjacent to the opening" and adjoins the wall; but R319.4 calls an opening that needs a well one "below the adjacent grade", which only makes sense if grade is the ground around the well (by the well-floor reading, no opening in a well would ever be below grade). The ICC's commentary on the same wording wasn't read: Gordium doesn't fetch the ICC's website. Searched 2026-11-13 in the stored 2025 code text.
- **Why it matters:** a basement window whose sill is 10 in above the well's floor and 60 in below the lawn is grade-floor (5 sq ft is enough) by the well-floor reading, and not grade-floor (5.7 sq ft needed) by the surrounding-ground reading. A 5.2 sq ft window passes one and fails the other.
- **Until you answer:** Today, escape windows are not checked yet: check them by hand. From a model, Gordium measures both readings; where they disagree the window gets no grade-floor answer, so a rule that turns on it gets NEEDS REVIEW (the test house `test_data/interior_houses/5_basement_window_well/`).
- **Options:** (a) the ground around the well (the stricter reading: a window deep in a well needs the full 5.7 sq ft); (b) the well's own floor.

### 4.7 An escape window's area well: may a ladder the open window blocks reach 6 in into the well?

- **The code's words** (2025 Building Code of New York State; the Residential Code's R319.4.1 and R319.4.2 have the same words): "The ladder or steps required by Section 1031.5.2 shall be permitted to encroach not more than 6 inches (152 mm) into the required dimensions of the area well." (1031.5.1 exception, p.360); "Area wells with a vertical depth of more than 44 inches (1118 mm) shall be equipped with an approved permanently affixed ladder or steps. The ladder or steps shall not be obstructed by the emergency escape and rescue opening when the window or door is in the open position." (1031.5.2, p.360).
- **What research found:** the plain reading is that a blocked ladder isn't "the ladder or steps required by Section 1031.5.2" (the section requires one that isn't blocked), so its reach has no exception; but the exception names the ladder the section requires, not one that complies with it. No ICC commentary was found, and no New York State code interpretation on the point (searched 2026-11-26). The City of Boise's handout on the IRC's earlier wording has the ladder "usable with the window in the fully open position", which leans toward the plain reading but says nothing of its reach. The searches are recorded in the rules (general.bc_1031_5_area_well_required, general.bc_1031_5_1_area_well_min_width, general.bc_1031_5_1_area_well_min_projection: their research).
- **Why it matters:** a basement bedroom's window in a 50 in deep well, whose ladder reaches 4 in into the well and sits where the window, fully open, blocks it.
- **Until you answer:** Today, with typed-in numbers, escape windows are checked by hand. From a model, the window fails 1031.5.2 either way (its ladder is blocked); under the Building Code its well-size rules fail too (Gordium assumes the strict reading, since those rules can't hold a review on this question beside their limits, 2026-11-27); under the Residential Code its well-size rules get NEEDS REVIEW. Neither ever passes on it.
- **Options:** (a) a blocked ladder's reach isn't excused (the well's size fails too); (b) the exception allows its 6 in as well, and only 1031.5.2 fails it.

---

## 5. Accessory buildings, accessory dwelling units, and the R-3a, R-2c, R-3aa, R-3b, RU and B districts

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
- **Until you answer:** Today, whether a detached ADU is in the primary front yard is typed as a yes or no, so the person typing it applies a reading. From a model, Gordium measures it with each street read as the primary one (the ADU nearer that street than the front of the house): it passes or fails only where both readings agree, and gets NEEDS REVIEW otherwise (R-1b.adu_front_yard; the same rule in R-1a to R-3b). The secondary front yard is held to the district's required front yard (Gordium's reading, §6).
- **Options:** (a) the front yard on the street the address is on; (b) the one the designer names.

### 5.3 R-3a (and R-3aa, R-3b, RU): lot size for a dormitory or a nursing home
`[R-3a.lot_area_other_use#1]` `[R-3aa.lot_area_other_use#1]` `[R-3b.lot_area_other_use#1]` `[RU.lot_area_other_use#1]`

- **The city's words:** "DORMITORY — A multiple dwelling which provides sleeping accommodations…" and "(4) A building used or occupied as a convalescent, old-age or nursing home" under DWELLING, MULTIPLE (§325-3, [p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7)). The chart's lot-size rows (p.3) have "Multiple family dwelling" and "Other use", but no dormitory or nursing-home row. Their figures by district: R-3a and R-3aa, multiple dwelling 6,000 sf new or 7,000 sf by conversion with note 7 ("+750 sf for each additional unit; +500 sf per room let for profit"), other use 6,000 sf; R-3b, 3,500 sf new or 4,000 sf by conversion with note 8 ("+500 sf for each additional unit; +300 sf per room let for profit"), other use 4,000 sf; RU, 16,500 sf with note 9 ("+1,500 sf for each additional unit"), other use 30,000 sf.
- **What research found:** the definitions make both multiple dwellings, but the chart lists them as uses of their own and gives the fraternity house (also a multiple dwelling) its own row, which suggests a use with no row is an "Other use". No City record found.
- **Why it matters:** a 40-bed dormitory on a 7,000 sf R-3a lot passes as an "Other use" but may need far more under note 7.
- **Until you answer:** Today and from a model, a dormitory or nursing home on a lot under 6,000 sf fails (both readings agree), and on a larger lot gets NEEDS REVIEW (R-3a.lot_area_other_use). The same in R-3aa, whose figures are R-3a's (R-3aa.lot_area_other_use; only a nursing home matters there, since a dormitory isn't permitted in R-3aa). In R-3b (multiple dwelling 3,500 sf new or 4,000 sf by conversion plus note 8, "Other use" 4,000 sf) and RU (a dormitory: multiple dwelling 16,500 sf plus note 9's 1,500 sf per unit past three, "Other use" 30,000 sf; a nursing home isn't permitted in RU) the readings differ on both sides of "Other use", so a dormitory or nursing-home lot gets NEEDS REVIEW from the least the multiple-family reading asks (3,500 sf in R-3b, 16,500 sf in RU) and fails below it, where both readings fail (R-3b.lot_area_other_use, RU.lot_area_other_use).
- **Options:** one answer covers every district, only the figures differ: (a) the multiple-family row and its note apply (R-3a and R-3aa: 6,000 sf new or 7,000 sf by conversion, note 7; R-3b: 3,500 sf or 4,000 sf, note 8; RU: 16,500 sf, note 9); (b) "Other use" applies (6,000 sf in R-3a and R-3aa; 4,000 sf in R-3b; 30,000 sf in RU).

### 5.4 R-3a (and R-3aa, R-3b): lot size and width for a zero-lot-line house
`[R-3a.lot_size_zero_lot_line#1]` `[R-3aa.lot_size_zero_lot_line#1]` `[R-3b.lot_size_zero_lot_line#1]`

- **The city's words:** the chart marks "One-family dwelling, detached, zero lot line" SP for R-3A (p.2), but its R-3A lot-size and lot-width cells are "-" (p.3). §325-8B(4): a special-permit use takes "the regulations … of whichever district has the stricter regulations" where it "is permitted by right in another district" ([p.26](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=26)).
- **What research found:** no residential district permits the use by right (R-2C, R-3A, R-3AA and R-3B mark it SP; the rest "-"), so §325-8B(4) has nothing to borrow, and §325-9B(1) doesn't list it. No City record found.
- **Why it matters:** it decides whether a zero-lot-line house on a 4,000 sf, 35 ft wide R-3a lot can even be proposed.
- **Until you answer:** Today and from a model, a zero-lot-line house in R-3a, R-3aa or R-3b gets NEEDS REVIEW (it needs a special permit anyway). R-3AA's and R-3B's cells are "-" too; their "Other use" rows are 6,000 sf and 50 ft (R-3aa), 4,000 sf and 40 ft (R-3b).
- **Options:** (a) no minimum; (b) the "Other use" rows (6,000 sf and 50 ft in R-3a and R-3aa; 4,000 sf and 40 ft in R-3b); (c) whatever the Planning and Development Board sets with the special permit.

### 5.5 R-3a next to R-1: what land "directly abuts"? Only land sharing a lot line, or also across a street, alley, creek or other waterway, railroad or other right-of-way, or touching only at a corner?
`[R-3a.abutting_r1#1]` `[R-3aa.abutting_r1#2]` `[R-3b.abutting_r1#1]`

- **The city's words:** "E. Development in R-3 Districts which abut R-1 Districts. The development of any permitted use in the R-3a or R-3b Zoning District, except a one-family or two-family dwelling, shall be subject to the following special conditions if the land on which the development occurs directly abuts land in either the R-1a or R-1b Zoning District" (§325-19E, [p.50](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=50)): 150% lot size, R-1's height, 75% coverage, 150% side and rear yards where they abut R-1 land.
- **What research found:** §325-9B(1)(j) says "abutting or across a street", treating the two as different; §325-11B says "abuts land, other than a public right-of-way", implying street land can abut; a district boundary may follow a street's center line or its edge (§325-6A). "Directly" isn't defined. No City record found.
- **Why it matters:** an apartment building on an R-3a lot facing R-1 houses across the street is limited to 35 ft instead of 40 ft (and likely 3 stories instead of 4) and 26.25% coverage instead of 35%, or not, depending on the answer.
- **Until you answer:** Today and from a model, Gordium asks you whether the lot abuts R-1 land (abuts_r1_district), worded the cautious way, its reading to confirm: "Is any R-1a or R-1b land touching this lot (even at a corner), or across a street, alley, creek or other waterway, railroad or other right-of-way from it?" Not answered yet, or yes: every R-3a use §325-19E covers gets NEEDS REVIEW (R-3a.abutting_r1), and the same in R-3b (R-3b.abutting_r1, the same words) and R-3aa (R-3aa.abutting_r1, if §325-19E reaches it at all: §5.11). No: §325-19E doesn't apply.
- **Options:** (a) only R-1a or R-1b land sharing a lot line counts; (b) R-1a or R-1b land across a street counts too; (c) across an alley, creek or other waterway, railroad or other right-of-way too; and whether land touching only at a corner counts.

### 5.6 R-3a next to R-1: is a row of attached houses exempt from §325-19E?
`[R-3a.abutting_r1#2]` `[R-3aa.abutting_r1#3]` `[R-3b.abutting_r1#2]`

- **The city's words:** §325-19E exempts "a one-family or two-family dwelling" ([p.50](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=50)). §325-3: "A one-family dwelling may be constructed in any of the following configurations", including "ONE-FAMILY ATTACHED DWELLING — A building containing three or more one-family dwellings"; but also "DWELLING, MULTIPLE … (1) A building containing three or more dwelling units … (5) … row house, townhouse" ([p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7), [p.8](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=8)).
- **What research found:** the definitions point both ways, and no City record was found. Semi-detached and zero-lot-line houses (at most two dwellings) are clearly one-family configurations and are exempt.
- **Why it matters:** a row of five townhouses on an R-3a lot next to R-1 houses may be held to 35 ft and 26.25% coverage, or to R-3a's 40 ft and 35%.
- **Until you answer:** Today and from a model, attached houses in R-3a (and R-3b, R-3aa) get NEEDS REVIEW on §325-19E (R-3a.abutting_r1, R-3b.abutting_r1, R-3aa.abutting_r1) when the lot abuts R-1 land or that isn't stated yet (abuts_r1_district, §5.5), as every use it may cover does.
- **Options:** (a) exempt, as a one-family configuration; (b) covered, as a multiple dwelling.

### 5.7 R-2c: an attached house with more than five occupants in one unit
`[R-2c.lot_area_one_family_attached#2]`

- **The city's words:** chart note 6, for R-2C's attached houses: "(6) For the first occupant in each dwelling unit; +300 sf for each additional occupant in each dwelling unit; +500 sf for each additional occupant in each dwelling unit in excess of five occupants." (zoning charts, April 2026, p.3). "Occupant" is defined for R-2c only: a person with the right to occupy (§325-3, [p.16](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=16)).
- **What research found:** the note lists both additions with "+" and never says "instead"; every occupant past five is also an "additional occupant", so the 300 sf can be read to apply to them too. Nothing else in Chapter 325 says which, and no City record was found (2026-10-21).
- **Why it matters:** a three-unit row house with seven occupants in one unit and one in each of the others needs 4,500 + 4 × 300 + 2 × 500 = 6,700 sf if the two occupants past five cost 500 sf instead of 300 sf, or 4,500 + 6 × 300 + 2 × 500 = 7,300 sf if they cost both.
- **Until you answer:** Today and from a model, the lot complies only if it is enough with the 500 sf on top of the 300 sf (and every occupant in one unit, since the split isn't asked); short of that, but enough with the 500 sf instead of the 300 sf (and this lot's occupants spread one to each of its units first), it gets NEEDS REVIEW (R-2c.lot_area_one_family_attached); the use needs a special permit in R-2c anyway.
- **Options:** (a) each occupant past five adds 500 sf instead of 300 sf; (b) it adds 500 sf on top of the 300 sf (800 sf).

### 5.8 R-2c: the narrow side yard of a semi-detached or attached building
`[R-2c.side_yards#1]`

- **The city's words:** chart notes 14 and 15, for R-2C's side yards ("10 ft /15 ft" one side, "0 ft /5 ft / 10 ft" the other): "(14) The first number applies to one-family detached dwellings, one-family semi-detached dwellings (unattached sides only), one-family attached dwelling (unattached sides only), two-family dwellings, and other uses; the second number applies to one-family detached zero lot line dwellings." "(15) The first number applies to one-family detached zero lot line dwellings and one-family semi-detached dwellings with attached sides; the second number applies to one-family detached dwellings, two-family dwellings, and other uses; …" (zoning charts, April 2026, p.3).
- **What research found:** note 14 gives every unattached side of a semi-detached or attached building 10 ft (Column 12: "one side yard"), and note 15 gives a semi-detached house's attached side 0 ft; but the 5 ft is given only to detached and two-family houses and other uses, and the attached building isn't in note 15 at all. So a semi-detached building standing whole on one lot (two unattached sides), or an attached building's sides, have no stated "other side" figure. No City record was found (2026-10-21).
- **Why it matters:** a semi-detached building on one R-2c lot with 10 ft on one side and 5 ft on the other complies if the second side is 5 ft or 0 ft, and not if every unattached side needs 10 ft.
- **Until you answer:** Today and from a model, a semi-detached or attached building in R-2c complies on side yards only with 10 ft on both sides; under 10 ft on its narrower side gets NEEDS REVIEW (R-2c.side_yards), as it also does because Gordium can't tell which side is the party wall. Under 10 ft on the wider side does not comply.
- **Options:** (a) every unattached side 10 ft; (b) the second side 5 ft, as for a two-family house; (c) 0 ft, note 15's figure for semi-detached dwellings.

### 5.9 R-2c: is an attached house's lot size for each row house's own lot, or for the whole building's lot?
`[R-2c.lot_area_one_family_attached#1]`

- **The city's words:** R-2C's attached rows: 1,500 sf (note 6: "For the first occupant in each dwelling unit; +300 sf for each additional occupant…") and a 50 ft minimum lot width; note 14 gives the attached house's 10 ft side yard to its "unattached sides only" (zoning charts, April 2026, p.3). "ONE-FAMILY ATTACHED DWELLING — A building containing three or more one-family dwellings … A maximum of six" (§325-3, [p.8](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=8)).
- **What research found:** the code points both ways, more strongly to the building's lot. For the building's lot: a 50 ft lot width can't be met by a single row house's lot (a row-house module's facade is at most 25 ft, §325-3 ROW HOUSE, [p.18](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=18)); note 15 gives a semi-detached house 0 ft on its "attached sides" but gives the attached house no such figure; §325-8B(1) applies a lot-size figure to each primary building on the property ([p.26](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=26)); and where the code means row houses to stand on lot lines it says so: the Collegetown form districts give "Row house 0 feet" side setback (§325-45.2, p.149), which R-2c's chart doesn't (that lets a row house stand on its side lot lines; it doesn't by itself say each has its own lot). For each row house's own lot: note 14's "unattached sides only". The subdivision chapter (290) isn't among our documents, and no City record or zoning board decision was found (2026-10-21).
- **Why it matters:** a row house on its own 20 × 100 ft lot (2,000 sf, one occupant) complies if each lot is held to its own unit (1,500 sf), and not if the lot must hold a building of at least three units (4,500 sf), or be 50 ft wide.
- **Until you answer:** Today and from a model, Gordium checks both: an attached lot complies only if it holds the whole building (its units here exactly the building's units, which the architect states) and is enough for all of it, at least three units; it does not comply only if it is short even for its own units; NEEDS REVIEW between (R-2c.lot_area_one_family_attached). A row house's lot holding one unit of a larger building is never a pass, since the other lots' occupants aren't stated; nor is a lot stated with more units than its building (part of another building, or a count off). The use needs a special permit in R-2c anyway.
- **Options:** (a) each row house's own lot, held to its own units; (b) the building's lot, held to the whole building (its three to six units and all their occupants).

### 5.10 R-3aa: may a small one-story building skip the 2-story minimum, and does the minimum reach a garage or shed?
`[R-3aa.stories#1]`

- **The city's words:** R-3AA's stories cell is "3/2 [fn11]": "(11) The first number refers to the maximum building stories allowed, the second number refers to the minimum building stories required." (zoning charts, April 2026, p.3). "(15) Column 16: Minimum Height of Building, Height in Feet. Buildings hereafter erected shall have a minimum height as specified herein; provided, however, that the requirements of this column shall not apply to development, including additions and/or expansions of existing development where the new development or addition or expansion of the existing development does not exceed a footprint of 500 square feet." (§325-8A(15), [p.26](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=26)) and "(10) See § 325-8A(15) for applicability of minimum height regulations." (§325-8B(10), [p.27](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=27)).
- **What research found:** the residential chart (p.3) has no "Minimum Building Height" section and no note repeating the exemption; R-3AA's minimum stories is its only minimum-height figure. The chart's other sheets do have such sections, with a stories row and a feet row (commercial p.5, special purpose p.7, West End p.8, waterfront p.11, Collegetown p.13), and the commercial sheet puts the exemption on its section in the same words ("(6) Minimum building height requirement shall not apply to development … does not exceed a footprint of 500 square feet.", p.5): the City counts a minimum number of stories as a "minimum building height requirement". That points to the exemption covering R-3AA too (through §325-8B(10), 2012), but p.3 attaches no such note. On garages and sheds the City's texts point both ways. For the main building only: the special purpose sheet's minimum "Only applies to new construction of non-industrial primary structures" (p.7 note 4), Collegetown's is set on a "Primary Use" row (p.13), and, in the downtown and business districts it names (CBD-60 to CBD-140, B-1a, B-1b, B-2c, B-2d), "no primary use building shall be erected that is less than two stories" (§325-16G, [p.48](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=48)). For every building: note 11 and §325-8A(15) ("Buildings hereafter erected") don't say primary, and the waterfront sheet's "(6) Accessory structures of less than 250 SF may be 1 story" (p.11) implies its minimum otherwise reaches them. No City record found (2026-10-25).
- **Why it matters:** a one-story 450 sf studio as the main building on an R-3aa lot complies if the exemption covers the minimum stories, and does not if it doesn't (a one-story addition of 400 sf to an existing one-story house is the same question). A two-story house with a one-story 600 sf garage complies if the minimum is for the main building only, and does not if it reaches the garage.
- **Until you answer:** Today and from a model, a one-story design in R-3aa whose buildings cover 500 sf or less gets NEEDS REVIEW (R-3aa.stories), and so does a one-story main building beside accessory buildings (together they may cover more than 500 sf while the main building covers less); a one-story design covering more than 500 sf, with no accessory building on the lot, does not comply; a 2- or 3-story main building with any accessory building on the lot gets NEEDS REVIEW (Gordium counts the main building's stories only). Gordium checks the building as drawn, so a one-story addition of 500 sf or less to an existing one-story building shows as does not comply when the whole building covers more: check §325-8A(15) by hand (a stricter answer, never a false pass).
- **Options:** for small buildings: (a) the 500 sf exemption covers R-3AA's minimum stories; (b) every building in R-3aa needs at least 2 stories. For accessory buildings: (c) the minimum is for the main building only; (d) it reaches every building on the lot (with the exemption, if (a)).

### 5.11 R-3aa next to R-1: does §325-19E apply in R-3aa at all?
`[R-3aa.abutting_r1#1]`

- **The city's words:** "E. Development in R-3 Districts which abut R-1 Districts. The development of any permitted use in the R-3a or R-3b Zoning District, except a one-family or two-family dwelling, shall be subject to the following special conditions…", each figured from "the District Regulations Chart for the R-3a or R-3b District" (§325-19E, [p.50](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=50)). The chart's note 1, "For special conditions on development of property in R-3 that directly abuts R-1, see §325-9.", sits on its "R-3" heading, which spans R-3A, R-3AA and R-3B (zoning charts, April 2026, p.3).
- **What research found:** §325-19E's own words name R-3a and R-3b only, twice; §325-4 lists R-3aa as a district of its own, and the code names R-3 districts one by one where it means some of them (cluster subdivisions: "R-3a and R-3b", §325-11B(1), [p.38](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=38)). R-3aa existed before §325-19E was adopted (§325-19E was "[Added 7-3-2019 by Ord. No. 2019-12]"; §325-4, which lists "R-3aa Residential", was last amended "11-1-2017 by Ord. No. 2017-14", [p.22](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=22)), so leaving it out may be deliberate. But the heading and the chart's note say "R-3", and elsewhere "R-3" means all three (§325-9B(1)(g)). No City record or zoning board decision found (2026-10-25).
- **Why it matters:** an apartment building on an R-3aa lot next to R-1 houses needs 9,000 sf instead of 6,000 sf, 26.25% coverage instead of 35%, and 15 ft and 7.5 ft side yards (150% of 10 ft and 5 ft) if §325-19E applies; R-3aa's own limits if it doesn't.
- **Until you answer:** Today and from a model, Gordium doesn't leave §325-19E out of R-3aa: where the lot abuts R-1 land or that isn't stated yet (abuts_r1_district, §5.5), every use §325-19E would cover gets NEEDS REVIEW (R-3aa.abutting_r1). No R-1 land near the lot: §325-19E can't apply.
- **Options:** (a) §325-19E applies in R-3aa as in R-3a and R-3b; (b) only in R-3a and R-3b, the districts it names.

### 5.12 RU: where must the green space be?
`[RU.green_space#1]`

- **The city's words:** RU's coverage cell is "25% [fn13]": "(13) 50% of the developable lot area, after the required setbacks have been calculated, must be retained as green space." (zoning charts, April 2026, p.3). "GREEN SPACE — A portion of a lot that is set aside for public or private use without any construction or parking areas. … Where a minimum green space requirement applies, at least 75% of the required area shall be softscape…" (§325-3, [p.11](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=11), [p.12](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=12)).
- **What research found:** "developable lot area" isn't defined anywhere in Chapter 325; the plain reading is the lot less its required yards ("setbacks"). The note says how much green space (half of that area), not where it must lie. No City record found (2026-10-25).
- **Why it matters:** on a 100 × 150 ft RU lot the developable area is 80 × 87.5 = 7,000 sf, so 3,500 sf must be green space. If it must lie inside that area, a 3,750 sf building (the 25% coverage limit) can't fit beside it (3,750 + 3,500 > 7,000); if the required yards count, it can.
- **Until you answer:** Today and from a model, green space is not checked yet: every RU design gets NEEDS REVIEW on it (RU.green_space), to check by hand.
- **Options:** (a) the green space must lie inside the developable area; (b) it may lie anywhere on the lot, the required yards included.

### 5.13 RU: how many primary buildings on a lot of exactly 60,000 sf, and are "primary uses" buildings?
`[RU.primary_structures#1]`

- **The city's words:** the chart's RU heading carries note 3: "(3) Properties less than 60,000 SF may only have one primary structure. Properties greater than 60,000 SF may have two primary uses, if approved by ILPC and Planning Board. Properties with at least 90,000 SF can have as many as three primary uses if approved by ILPC and Planning Board." (zoning charts, April 2026, p.2). "PRIMARY STRUCTURE — A single structure (located on a parcel) containing a use permitted in the zoning district in which it is located." (§325-3, [p.17](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=17)).
- **What research found:** the first sentence counts structures, the next two "primary uses"; §325-8B(1) speaks of "each additional permitted primary use located in a separate building" ([p.26](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=26)), so the code treats the two together, but the note doesn't say it. "Less than" and "greater than" 60,000 sf leave a lot of exactly 60,000 sf in neither. The note isn't in Chapter 325's text, and no City record was found (2026-10-25).
- **Why it matters:** a second house on an RU lot of exactly 60,000 sf may be proposed (with the Landmarks and Planning Board approvals) or not.
- **Until you answer:** Today and from a model, Gordium counts the primary buildings (from the model where it can tell, else as the architect states it). One complies on any RU lot; two on a lot over 60,000 sf, or three on 90,000 sf or more, get NEEDS REVIEW for the two approvals; two on a lot of exactly 60,000 sf get NEEDS REVIEW too (under either reading); fewer square feet, or more buildings, do not comply (RU.primary_structures). Each building is read as one primary use (Gordium's reading for now, to confirm: if "primary uses" means uses, two buildings of one use on a large lot need no approvals, where Gordium says NEEDS REVIEW).
- **Options:** for exactly 60,000 sf: (a) one primary structure; (b) two, with the approvals. And whether "primary uses" means primary structures.

### 5.14 RU: one new apartment building, fraternity house or dormitory every 500 ft: one of what?
`[RU.spacing_500_ft#1]`

- **The city's words:** RU's marks for multiple dwellings, fraternity houses and dormitories are "•[fn5]": "(5) Restricted to one every 500 feet for new construction, measured from the edge of the property line." (zoning charts, April 2026, p.2).
- **What research found:** the note is written on all three rows, and §325-3 makes a fraternity house and a dormitory multiple dwellings too ([p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7)), which points to "one of any of the three"; but it can be read row by row. "For new construction" says which buildings it restricts, not which neighbours count. The note isn't in Chapter 325's text, and no City record was found (2026-10-25).
- **Why it matters:** a new apartment building 300 ft from an existing fraternity house is allowed under the row-by-row reading and not under the any-of-the-three reading.
- **Until you answer:** Today and from a model, the 500 ft spacing is not checked yet: a new multiple dwelling, fraternity house or dormitory in RU gets NEEDS REVIEW on it (RU.spacing_500_ft), to check by hand; one stated as a conversion of an existing building doesn't (the note is for new construction).
- **Options:** (a) no other multiple dwelling, fraternity house or dormitory within 500 ft; (b) no other of the same use; (c) only buildings built new count.

### 5.15 A two-family house: are unrelated housemates "roomers or boarders"?
`[R-2a.occupancy_two_family#1]` `[R-2b.occupancy_two_family#1]` `[R-2c.occupancy_two_family#1]` `[R-3a.occupancy_two_family#1]` `[R-3aa.occupancy_two_family#1]` `[R-3b.occupancy_two_family#1]` `[RU.occupancy_two_family#1]`

- **The city's words:** "DWELLING, MULTIPLE ... (3) A building containing living, sanitary and sleeping facilities occupied by one or two families and more than two roomers or boarders, exclusive of minor dependent children in the care of a parent or relative, residing with either one of such families." And: "In R-2 and CR-2 Zones, each unit of a two-family dwelling may be occupied by an individual or family and not more than two unrelated individuals." (§325-3B, [p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7), [p.9](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=9))
- **What research found:** "roomer" and "boarder" aren't defined. BOARDINGHOUSE speaks of meals for paying guests, and FUNCTIONAL FAMILY UNIT sets "separate roomers" against a household sharing the whole unit, which points to lodgers who pay; nothing says an unrelated housemate isn't one. No City record found (2026-10-27). Full research: `docs/research/2026-10-27_occupancy_and_home_occupation.md` §6.4.
- **Why it matters:** an R-2 two-family house with a family and two unrelated housemates in each unit (four in the building) is allowed if housemates aren't roomers, and is a multiple dwelling (not allowed in R-2) if they are.
- **Until you answer:** Today and from a model, a two-family dwelling with more than one unrelated person in a unit gets NEEDS REVIEW (R-2a.occupancy_two_family and the same rule in R-2b, R-2c, R-3a, R-3aa, R-3b, RU); in R-2, three or more in a unit does not comply.
- **Options:** (a) every unrelated person counts as a roomer or boarder, across the whole building; (b) only people renting a room (with or without meals) count.

### 5.16 R-1 with an accessory dwelling unit: whose home makes the house "owner-occupied"?
`[R-1a.occupancy_one_family#1]` `[R-1b.occupancy_one_family#1]`

- **The city's words:** "In the R-1 Zones, occupancy by an individual or a family and not more than two unrelated individuals is permitted if the dwelling is owner-occupied." A one-family dwelling is "A dwelling unit occupied exclusively for residential purposes" ([p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7)); an ADU is "A smaller, secondary dwelling unit located on the same lot" ([p.4](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=4)); OWNER: "principal residence in property" ([p.16](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=16)).
- **What research found:** "the dwelling" being "A dwelling unit" points to the house itself, as does PRIMARY RESIDENCE ("A dwelling unit where the owner ... resides"); DWELLING ("Any building or structure or part thereof") and OWNER ("in property") point to the whole property. §325-28 (ADUs, added 2025) sets no owner-occupancy or occupancy rule of its own. No City record found (2026-10-27). Full research: `docs/research/2026-10-27_occupancy_and_home_occupation.md` §3.
- **Why it matters:** an owner living in a backyard ADU while the main house holds a family and two unrelated housemates complies under one reading and not under the other; and if the one-family limits reach the ADU, its own occupants count too.
- **Until you answer:** Today and from a model, Gordium asks whether the owner lives in the one-family dwelling itself (not only in an ADU) and whether an ADU is on the lot; two unrelated individuals in an owner-occupied house with an ADU on the lot, or with that not said, get NEEDS REVIEW (R-1b.occupancy_one_family has that review condition; the same in R-1a). An owner living only in the ADU answers no, so two unrelated individuals in the house do not comply today: under option (b) that would be a false fail (never a false pass).
- **Options:** (a) the owner must live in the house itself; (b) the owner living in either unit counts; and whether the ADU's own occupants are held to the one-family limits.

### 5.17 Two primary buildings on one lot: how are their yards kept apart (§325-7B)?
`[R-1a.yards_not_shared#1]` `[R-1b.yards_not_shared#1]` `[R-2a.yards_not_shared#1]` `[R-2b.yards_not_shared#1]` `[R-2c.yards_not_shared#1]` `[R-3a.yards_not_shared#1]` `[R-3aa.yards_not_shared#1]` `[R-3b.yards_not_shared#1]` `[RU.yards_not_shared#1]`

- **The city's words:** "No part of a yard or other open space about any building required for the purposes of complying with the provisions of this chapter shall be included as a part of a yard or other open space similarly required for another building." (§325-7B, [p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)). Each yard is defined between a building and a lot line, for example "SIDE YARD — An open space extending from the front yard to the rear yard between any building and the side lot line" (§325-3, [p.20](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=20)).
- **What research found:** the code never defines a yard between two buildings on one lot, and §325-7B says only that one building's required yard can't be another's, not where one ends and the next begins. No City interpretation or Board of Zoning Appeals decision was found (2026-10-27); other New York codes with the same clause don't spell it out either. Accessory buildings are settled: §325-25 lets them stand in side and rear yards. Full research: `docs/research/2026-10-27_audit_gaps.md` §5.
- **Why it matters:** two houses side by side on a wide R-1b lot, 12 ft apart, each 10 ft from its own side lot line: allowed if each needs only its yards to the lot lines, not if the 12 ft between them must hold both houses' 10 ft side yards (20 ft).
- **Until you answer:** Today and from a model, a lot with two or more primary buildings gets NEEDS REVIEW on this (R-1b.yards_not_shared and the same rule in every residential district), to check by hand; a lot with one primary building (garages and sheds aside) isn't affected.
- **Options:** (a) each building's yards measured from it to the lot lines, and no building inside another's required yard; (b) also the space between two buildings at least their facing yards added together.

### 5.18 R-1 and R-2a/R-2b: is "not more than three cars" for each private garage, or for all the lot's garages together?
`[R-1a.private_garage#1]` `[R-1b.private_garage#1]` `[R-2a.private_garage#1]` `[R-2b.private_garage#1]`

- **The city's words:** the chart lists "Private garage" as a permitted accessory use, marked note 6 in R-1A, R-1B, R-2A and R-2B: "(6) For not more than three cars." ([chart p.2](https://www.cityofithacany.gov/DocumentCenter/View/20523/COI-Zoning-Charts_0426)). "GARAGE, PRIVATE — An enclosed space for the storage of one or more motor vehicles, provided that no business, occupation or service is conducted for profit therein." (§325-3B, [p.11](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=11)). Column 3's accessory uses "are listed, subject to the further regulations of Article V" (§325-8A(3), [p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)).
- **What research found:** the definition makes a private garage "an enclosed space", which fits a limit on each garage, but nothing in Chapter 325 says whether a lot may have two garages of three cars each. No other section counts cars in garages: §325-20's parking rules, §325-25's accessory structures ("including private garages") and the ACCESSORY USE definition (garages "within a residential building or on the premises thereof") don't. No City interpretation or Board of Zoning Appeals decision was found (web search, 2026-10-29); the City's 2010 chart (posted by the Fall Creek neighborhood association) has the same words, "Private garage for not more than 3 cars", and doesn't settle it either. Full research: `docs/research/2026-10-29_private_garage.md` §3.
- **Why it matters:** a house with an attached two-car garage and a detached two-car garage (four cars in all) complies if the limit is for each garage, and does not if it is for the whole lot.
- **Until you answer:** Today and from a model, Gordium asks for the cars all the lot's private garages hold together (in the start box) and, only when that is over three, how many garages there are. Three or fewer in all passes (both readings); more than three for each garage fails (some garage holds more than three: both readings); in between, and while either answer is blank, it gets NEEDS REVIEW (R-1b.private_garage has that review condition; the same in R-1a, R-2a, R-2b).
- **Options:** (a) three cars at most in each private garage; (b) three cars at most in all the lot's private garages together.

### 5.19 R-2c: "six cars per building": per what building?
`[R-2c.private_garage#1]`

- **The city's words:** in R-2C the chart's "Private garage" is marked note 7: "(7) For not more than six cars per building." ([chart p.2](https://www.cityofithacany.gov/DocumentCenter/View/20523/COI-Zoning-Charts_0426)). §325-8A(4) uses the same words for parking: "The off-street parking spaces listed in this column shall be provided for each building hereafter erected or altered" ([p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)).
- **What research found:** a private garage is "an enclosed space" (§325-3B), which may stand alone or be "within a residential building" (ACCESSORY USE (7), [p.4](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=4)); §325-8A(4)'s "each building" is a building that needs parking, a primary building. So "building" may be each building holding a garage, each primary building on the lot, or the whole lot. No City interpretation or Board of Zoning Appeals decision was found (web search, 2026-10-29); the City's 2010 chart gives R-2c the same "cars per building". Full research: `docs/research/2026-10-29_private_garage.md` §4.
- **Why it matters:** an R-2c lot with two houses and one eight-car garage between them complies if the six cars are counted per primary building (four each), and does not if they are counted per garage building or for the whole lot.
- **Until you answer:** Today and from a model, Gordium asks for the cars all the lot's private garages hold together and, only when that is over six, how many garages there are; it counts the primary buildings as for §325-8B(1). Six or fewer in all passes (every reading); more than six times both the garages and the primary buildings fails (every reading); in between, and while an answer is blank, it gets NEEDS REVIEW (R-2c.private_garage).
- **Options:** (a) each building holding a private garage; (b) each primary building, its garages together; (c) the whole lot.

### 5.20 An attached ADU's 40%: of the whole house, or of the rest of it?
`[R-1a.adu_attached_size#1]` `[R-1b.adu_attached_size#1]` `[R-2a.adu_attached_size#1]` `[R-2b.adu_attached_size#1]` `[R-2c.adu_attached_size#1]` `[R-3a.adu_attached_size#1]` `[R-3aa.adu_attached_size#1]` `[R-3b.adu_attached_size#1]`

- **The city's words:** "(a) Attached ADU: The ADU shall not exceed 40% of the floor area of the primary structure." (§325-28C(7), [p.72](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=72)). An attached ADU is "connected to or contained within the primary structure, such as a basement, building addition, or attached garage" (§325-3B, [p.4](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=4)).
- **What research found:** Chapter 325 doesn't define floor area, and doesn't say whether the ADU itself counts in "the primary structure". "Contained within the primary structure" points to the whole house, ADU included; the two-family dwelling's "one unit may be no larger than 50% of the floor area of the larger" (§325-3B, [p.9](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=9)) compares one unit with the other, which points to the rest. No City interpretation or Board of Zoning Appeals decision on ADUs was found (web search, 2026-10-29; §325-28 is from 2025). Full research: `docs/research/2026-10-29_accessory_dwelling_units.md` §5.
- **Why it matters:** a 1,500 sf house with a 500 sf basement ADU complies if the 40% is of the whole house (600 sf at most), and does not if it is of the rest (0.4 × 1,000 = 400 sf).
- **Until you answer:** Today and from a model, the architect types the ADU's floor area and the whole house's (the model's solids don't show floors). Within 40% of the rest passes (both readings); over 40% of the whole fails (both); in between, and while either area is blank, it gets NEEDS REVIEW (R-1b.adu_attached_size has that review condition; the same in R-1a to R-3b).
- **Options:** (a) 40% of the whole primary structure, the ADU included; (b) 40% of the rest of it, the ADU left out.

### 5.21 R-1: a detached ADU 6 ft or 5 ft from a side lot line?
`[R-1a.adu_detached_setbacks#1]` `[R-1b.adu_detached_setbacks#1]`

- **The city's words:** "in R-1 Districts, where accessory buildings may not be placed less than six feet from any side lot line nor less than three feet from any rear lot line" (§325-25C, [p.67](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=67)). "[2] Detached ADU, new construction: [a] Side and rear setback: 5' or setback required for primary structure, whichever is less." (§325-28C(8), [p.72](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=72)).
- **What research found:** a detached ADU's building is an accessory structure (§325-3B), so both sections reach it. §325-28 (2025) is the later, more specific one ("All ADUs shall meet the following setback requirements"); §325-25C is older and general; neither says it overrides the other, and both are met at 6 ft. As reported (Ithaca Times, 2025-03-07), the Council raised the ADU side setback from 4 ft to 5 ft to match the state fire code, without mentioning §325-25C. Whether §325-25C's R-1 clause covers buildings that aren't frame is §5.1. No City record found (2026-10-29). Full research: `docs/research/2026-10-29_accessory_dwelling_units.md` §6.
- **Why it matters:** a new backyard cottage in R-1b 5½ ft from the side lot line complies under §325-28 and not under §325-25C.
- **Until you answer:** Today and from a model, 6 ft or more passes, under 5 ft fails, and 5 ft to under 6 ft gets NEEDS REVIEW (R-1b.adu_detached_setbacks has that review condition; the same in R-1a). The rear is 5 ft under both.
- **Options:** (a) 5 ft (§325-28 governs ADUs); (b) 6 ft (§325-25C applies too).

### 5.22 R-2c: when the house's required side yard is 0 ft, is the ADU's?
`[R-2c.adu_detached_setbacks#1]`

- **The city's words:** "Side and rear setback: 5' or setback required for primary structure, whichever is less." (§325-28C(8), [p.72](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=72)). R-2c's other-side minimum is "0 ft /5 ft / 10 ft", note 15: "The first number applies to one-family detached zero lot line dwellings and one-family semi-detached dwellings with attached sides" ([chart p.3](https://www.cityofithacany.gov/DocumentCenter/View/20523/COI-Zoning-Charts_0426)).
- **What research found:** note 15's 0 ft is for a party wall or a zero-lot-line house's wall on the lot line, not a freestanding building; but "whichever is less" takes the primary structure's own required setback, which is 0 ft on that side, and nothing says which side of the house is meant. No City record found (2026-10-29). Full research: `docs/research/2026-10-29_accessory_dwelling_units.md` §7.
- **Why it matters:** an ADU 2 ft from the side lot line behind a semi-detached house complies under one reading and not the other.
- **Until you answer:** Today and from a model, 5 ft or more passes; under 5 ft fails for every other use, and gets NEEDS REVIEW for a zero-lot-line, semi-detached or attached house (R-2c.adu_detached_setbacks).
- **Options:** (a) 5 ft (the 0 ft is for party walls, not ADUs); (b) the lesser of 5 ft and the house's least required side, 0 ft.

### 5.23 R-1 and R-2: is a bed-and-breakfast inn prohibited, or allowed with a special permit?
`[R-1a.use#1]` `[R-1b.use#1]` `[R-2a.use#1]` `[R-2b.use#1]` `[R-2c.use#1]`

- **The city's words:** the zoning chart marks "Bed-and-breakfast inn - - - - - SP SP SP SP §325-10(C)(2)": "-" (not permitted) in R-1a, R-1b, R-2a, R-2b and R-2c, SP in R-3a, R-3aa, R-3b and RU (zoning charts, April 2026, p.2). But §325-9B(1) lists "(p) Bed-and-breakfast inns in all districts." among the uses needing a special permit from the Planning and Development Board ([p.31](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=31)).
- **What research found:** each side has support. For a permit: the list says "in all districts", and on the residential chart every other "in all districts" use (cemeteries, public utility facilities, towers, neighborhood gardens) is SP everywhere. For the chart: §325-9B(1) introduces its list as "The uses listed under the district regulations in § 325-8" ([p.30](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=30)), and §325-8A makes the chart part of the chapter ([p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)), so the list describes the chart; the chart's own row cites the permit conditions (§325-10(C)(2)) beside its "-" marks; and elsewhere the chart departs from "all districts" both ways (bed-and-breakfast inns are "•" in the waterfront districts, p.10, and "-" in CR-1, CR-2, MU-1 and MU-2, p.12). §325-9F(1)(c) ("in all residential districts", [p.34](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=34)) and §325-10C(2) set the permit's term and conditions; they presume a permit and grant none. No City interpretation or Board of Zoning Appeals decision on a bed-and-breakfast inn in R-1 or R-2 was found (web search 2026-10-29).
- **Why it matters:** an owner-managed house in R-1b offered as a 5-room bed-and-breakfast inn may apply for a special permit under one reading, and is not allowed under the other.
- **Until you answer:** Today and from a model, a bed-and-breakfast inn in R-1 or R-2 gets NEEDS REVIEW (R-1b.use and the same rule in R-1a, R-2a, R-2b, R-2c), saying it may be prohibited or allowed only with the special permit; before 2026-10-29 it did not comply.
- **Options:** (a) the chart governs: not permitted in R-1 and R-2; (b) §325-9B(1)(p) governs: allowed with a Planning and Development Board special permit.

### 5.24 B-2d, B-4, B-5 and CBD: a motel's lot size, the chart's or §325-22A's 20,000 sf?
`[B-4.lot_area_hotel_motel#1]` `[B-5.lot_area_hotel_motel#1]` `[CBD-50.lot_area_hotel_motel#1]` `[CBD-60.lot_area_hotel_motel#1]` `[CBD-85.lot_area_hotel_motel#1]` `[CBD-100.lot_area_hotel_motel#1]` `[CBD-120.lot_area_hotel_motel#1]` `[CBD-140.lot_area_hotel_motel#1]`

- **The city's words:** the commercial chart's Motel rows give B-2D, B-4 and B-5 "3,000 sf" and "40 ft" (zoning charts, April 2026, [p.5](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/zoning_charts_2026-04.pdf#page=5)), and B-2A "20,000 sf" and "100 ft"; §325-22A says "Motels shall maintain a minimum lot size of 20,000 square feet and a minimum frontage of 100 feet on a public right-of-way." ([p.64](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=64)). (In B-2d a hotel or motel isn't permitted, chart p.4, so only B-4 and B-5 ask.) The CBD column (p.5, one column for CBD-50 to CBD-140) leaves a motel's lot size blank and gives it 10 ft of width; there a hotel or motel is permitted (p.4, •).
- **What research found:** §325-8B(8) makes every chart column subject to Article V, which holds §325-22, so the stricter figure reads as governing; the chart's smaller cell may mean small-lot motels were meant to be allowed. No City record found.
- **Why it matters:** a motel on a 10,000 sf B-4 lot meets the chart and not the law.
- **Until you answer:** Today and from a model, a hotel or motel lot with 20,000 sf and 100 ft complies; one with the other-use figures (3,000 sf, 40 ft; in CBD, 10 ft and no lot size) but less than 20,000 sf or 100 ft gets NEEDS REVIEW (a hotel that isn't a motel needs only the other-use row); less fails.
- **Options:** (a) §325-22A governs (20,000 sf and 100 ft); (b) the chart governs in these districts (3,000 sf and 40 ft; in CBD, 10 ft and no lot size).

### 5.25 B-2a, B-4 and CBD require no front yard (CBD no side yards either): does the height bonus ask for them?
`[B-2a.height#1]` `[B-4.height#1]` `[CBD-50.height#1]` `[CBD-60.height#1]` `[CBD-85.height#1]` `[CBD-100.height#1]` `[CBD-120.height#1]` `[CBD-140.height#1]`

- **The city's words:** §325-16C: "(1) Each required front, side and rear yard is increased one foot on the ground for each one foot of such additional height." ([p.47](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=47)); the chart's front yard for B-2A and B-4 is "-" (p.5), and the CBD column's front and both side yards are "-" (its rear yard is 10 ft).
- **What research found:** with no front yard required there may be nothing to increase, or a 0 ft yard that grows. No City record found.
- **Why it matters:** a 44 ft B-2a building at the sidewalk complies under one reading and not the other; so does a 64 ft CBD-60 building (its height is 60 ft, chart note 5) built to its street and side lines.
- **Until you answer:** Today and from a model, Gordium assumes the stricter reading: a building using the bonus must stand back from the street (in CBD, and from its side lines) by its extra height, so it may say does not comply where the other reading complies, never the reverse.
- **Options:** (a) the front yard grows from 0 ft; (b) no front yard is required, bonus or not.

### 5.26 B-1a, B-1b, B-2d and CBD-60 to CBD-140: may a building of 500 sf or less skip the two-story minimum?
`[B-1a.min_stories#1]` `[B-1b.min_stories#1]` `[B-2d.min_stories#1]` `[CBD-60.min_stories#1]` `[CBD-85.min_stories#1]` `[CBD-100.min_stories#1]` `[CBD-120.min_stories#1]` `[CBD-140.min_stories#1]`

- **The city's words:** chart note 6: "Minimum building height requirement shall not apply to development, including additions and/or expansions of existing development where the new development or addition or expansion of the existing development does not exceed a footprint of 500 square feet." (p.5, on the heading over both the stories and the feet rows); §325-16G: "Notwithstanding anything to the contrary contained herein, in the CBD-60, … B-1a, B-1b, B-2c, and B-2d Zoning Districts, no primary use building shall be erected that is less than two stories" ([p.48](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=48)), with no such exception; §325-8A(15) gives the 500 sf exception for Column 16, the height in feet ([p.26](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=26)).
- **What research found:** the exception is written for the feet; the two-story rule says "notwithstanding anything to the contrary". No City record found. (The R-3aa question §5.10 is the residential twin.)
- **Why it matters:** a one-story 400 sf kiosk in B-1b or CBD-60. (CBD-50 isn't asked: §325-16G doesn't name it, so only the chart's minimum and its note 6 apply there, and a building of 500 sf or less is exempt.)
- **Until you answer:** Today and from a model, a one-story building whose buildings cover 500 sf or less gets NEEDS REVIEW; larger, does not comply.
- **Options:** (a) note 6 lifts both minimums; (b) it lifts only the height in feet; two stories are always required.

### 5.27 B-4, B-5 and CBD: is an accessory dwelling unit permitted? The chart's cell is blank
`[B-4.accessory_dwelling_unit#1]` `[B-5.accessory_dwelling_unit#1]` `[CBD-50.accessory_dwelling_unit#1]` `[CBD-60.accessory_dwelling_unit#1]` `[CBD-85.accessory_dwelling_unit#1]` `[CBD-100.accessory_dwelling_unit#1]` `[CBD-120.accessory_dwelling_unit#1]` `[CBD-140.accessory_dwelling_unit#1]`

- **The city's words:** the commercial chart's "Accessory Dwelling Unit" row marks • for B-1A to B-2D and leaves B-4, B-5 and CBD blank (p.4); §325-3B defines an ADU as "A smaller, secondary dwelling unit located on the same lot as a primary residential, commercial, or mixed-use structure" ([p.4](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=4)).
- **What research found:** the definition contemplates an ADU beside a commercial building; the chart neither permits nor forbids it here. No City record found.
- **Until you answer:** Today and from a model, an ADU on a B-4, B-5 or CBD lot gets NEEDS REVIEW (and in every B and CBD district §325-28's limits are checked by hand for now).
- **Options:** (a) permitted (a blank is no prohibition); (b) not permitted (only • is permitted).

### 5.28 B-1a, B-1b, B-4, B-5 and CBD: chart p.15 gives "-" for parking. None required, or §325-20?
`[B-1a.parking#1]` `[B-1b.parking#1]` `[B-4.parking#1]` `[B-5.parking#1]` `[CBD-50.parking#1]` `[CBD-60.parking#1]` `[CBD-85.parking#1]` `[CBD-100.parking#1]` `[CBD-120.parking#1]` `[CBD-140.parking#1]`

- **The city's words:** §325-8A(4): "The off-street parking spaces listed in this column shall be provided for each building hereafter erected or altered." ([p.24](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=24)); the commercial parking chart (p.15) gives B-2A and B-2D a figure per use and "-" on every row for B-1A, B-1B, B-4, B-5 and CBD, with note 2: "For all other uses see §325-20."
- **What research found:** §325-20's general standards give no count by district. Its table's footnote 2 (§325-20D(3)(b), [p.55](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=55)) says "See also the District Regulations Chart for districts in which off-street parking is not required", which supports (a), most strongly in CBD, whose column is "-" even on the "Other Uses" row where B-2A and B-2D say "See §325-20"; but the chart never says which mark means "not required". No City interpretation found.
- **Until you answer:** Today and from a model, every B and CBD lot gets NEEDS REVIEW for parking (Gordium never reads "-" as none required).
- **Options:** (a) no off-street parking is required in these districts; (b) §325-20 or another section sets it.

### 5.29 B-1a and B-1b: lot size for a dormitory or a nursing home
`[B-1a.lot_area_other_use#1]` `[B-1b.lot_area_other_use#1]`

- **The city's words:** the commercial chart's lot-size rows (p.5) have "Multiple family dwelling" (6,000 sf new, 7,000 sf by conversion, note 2: "For the first 1-3 units; +750 sf for each additional unit; +500 sf per room let for profit.") and "Other use" (5,000 sf in B-1A, 3,000 sf in B-1B), but no dormitory or nursing-home row; §325-3 defines both as multiple dwellings ([p.7](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=7)). The same question as §5.3, with B-1's figures (in B-2a to B-5 every row is 3,000 sf, so the answer doesn't matter there).
- **What research found:** as §5.3. No City record found.
- **Until you answer:** Today and from a model, a dormitory or nursing home on a lot under the other-use figure fails (both readings agree), and on a larger lot gets NEEDS REVIEW (B-1a.lot_area_other_use, B-1b.lot_area_other_use).
- **Options:** (a) the multiple-family row and note 2 apply (6,000 sf new or 7,000 sf by conversion); (b) "Other use" applies (5,000 sf in B-1a, 3,000 sf in B-1b).

### 5.30 For the City zoning office: CBD-52 on the City's online map

- **The city's words:** §325-4 lists "CBD Central Business" and "CBD-50 Central Business" ([p.22](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/chapter_325_zoning_2026-10.pdf#page=22)); the zoning charts' one CBD column is headed "CBD-50, -60, -85, -100, -120, -140" (April 2026, [p.5](https://github.com/bz28/gordium/blob/main/regulations/jurisdictions/new_york/ithaca_city/1_source_documents/zoning_charts_2026-04.pdf#page=5)), and its note 5 makes each one's height its suffix. The City's online zoning map (its City_Zoning layer, looked up 2026-11-23) codes six blocks of West State Street, the 300 and 400 blocks between N Meadow St and N Albany St, "CBD-52".
- **What research found:** CBD-52 is in neither Chapter 325 (as downloaded 2026-10-19: §325-4, §325-8D and §325-16G name no CBD-52) nor the April 2026 charts, and the printed zoning map (May 2026, p.5, "CBD District Map") has no CBD-52 in its legend: it colours those blocks like CBD-50. A 2019 news report (Ithacating, "News Tidbits 5/11/19", https://ithacating.com/2019/05/12/news-tidbits-5-11-19/, read 2026-11-23) describes a proposed West State Street downzoning to "CBD-52" (CBD-62 with 20% or more affordable housing) that included the 300 and 400 blocks; nothing found says whether it was adopted. Searched: §325-4, §325-8, §325-16, the charts' notes 1, 4 and 5, the printed map's legend, the City's online map, the web.
- **Why it matters:** if CBD-52 is in force, its height (52 ft, or 62 ft with affordable housing?), its other rules (a West State Street setback was proposed) and whether it shares the CBD column are unknown to Gordium; if it isn't, those blocks are some other CBD district.
- **Until you answer:** Today and from a model, a lot the City's map codes CBD-52 gets NEEDS REVIEW for its zone, with this reason; Gordium never reads it as CBD-50 or as a 52 ft district, and checks nothing until the district is chosen.
- **Options:** (a) CBD-52 was adopted: send the ordinance (its height and other rules); (b) it wasn't: which district are the 300 and 400 blocks of West State Street (CBD-50, as the printed map's colour suggests, or CBD-60)?

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
| Is a detached ADU's building an accessory building? | Yes: an ADU in an accessory structure, so §325-25A keeps it out of a required front yard too | The law | §325-3B, p.4; §325-25A, p.66 |
| A detached ADU's secondary front yard ("same as primary structure") | The district's required front yard (25 ft in R-1a, R-1b, R-2a; 10 ft elsewhere), not how far back the house happens to stand | Reading · moderate | §325-28C(8), p.72; §325-25A, p.66 |
| An ADU in RU | Not permitted: the chart lists the ADU for R-1a to R-3b and leaves RU's cell blank (a design with one gets FAIL); confirm with the City zoning office | Reading · strong | chart p.2 line 30; §325-8A(3), §325-8B(3), pp.24, 26 |
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
