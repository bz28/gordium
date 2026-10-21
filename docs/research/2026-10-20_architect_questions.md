# Research answers to the open zoning questions (City of Ithaca, Chapter 325)

**Purpose:** the research report behind every finding and still-open question recorded with the rules and definitions on 2026-10-20: what was searched, the sources, and what each settled.\
**For:** anyone checking why Gordium reads the law the way it does; architects reviewing a reading.\
**Kept current by:** nobody: a dated record kept as written (only this header was added). New research gets its own dated report.

> **Filed 2026-10-20** as the evidence behind the `research` and `findings` recorded in
> `4_term_definitions/definitions.yaml`, `5_zoning_rules/R-1b.yaml` and the section labels (each one names its
> section here, e.g. `report: docs/research/2026-10-20_architect_questions.md §2.1`). The report is kept as
> written. The BZA packets it cites are linked, not stored. The search script it mentions (`scripts/syn2.py`)
> was a one-off outside the repository; the term index (`4_term_definitions/term_index.yaml`) is the
> repository's version of that search.
>
> **Corrections from the first review of PR 17 (2026-10-20).** The report below is unchanged; the records follow
> these corrections. (1) §4.3: the 12 ft test is not settled. "At any point" points to every side, but whether
> "computed at the main entrance side" limits it is the open question, so it stays open with both readings.
> (2) §4.5: §325-16C(4) says conditions (1) to (3) "shall not apply in the U-1 Zone"; it removes the bonus's
> limits there, not the bonus. (3) §2.4, §2.5 and X2: §325-25C's R-1 clause says "accessory buildings" without
> "frame", so whether the R-1 distances cover buildings that aren't frame is part of the X2 question.

Prepared 2026-10-20 for Gordium. Read-only research; no repository was changed.
Every web source below was accessed **2026-10-20**. Chapter 325 quotes are from Gordium's stored copy
(`regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/chapter_325_zoning_2026-10.jsonl`, branch
`architect-questions`; the PDF says "Downloaded from https://ecode360.com/IT1348 on 2026-10-19"). Page numbers are
that PDF's pages. The illustrations in §325-8A(14) and §325-19C were checked by rendering the PDF pages (the
extracted text does not contain them).

## How to read this

**Class**
- **A** = answered by the code's own text (read across sections). Gordium can apply it.
- **B** = not spelled out in the code, but there is a well-sourced reading. Gordium can state the reading, with the
  strength label below, and the architects should confirm it.
- **C** = disputed or Ithaca-specific and not settled by research. Keep NEEDS REVIEW; the precise question is given.

**Source ranks** (Ben's order; every answer lists its sources in this order)
1. Ithaca code text (Chapter 325 and the City's zoning charts)
2. Ithaca official interpretations and Board of Zoning Appeals (BZA) records: City staff notices, BZA worksheets
   (the City's own column-by-column compliance tables), Zoning Administrator statements
3. NYS Uniform Code / IBC / IRC wording and ICC commentary
4. Other municipalities' codes

**Strength of a reading = its best source.** Strong = rank 1; City practice = rank 2; Moderate = rank 3;
**Weak** = only rank 4 (other cities). Applicants' own calculations printed in BZA packets are noted as
"practitioner evidence" (they show how Ithaca architects work, not what the City decided) and never raise a label.

**One general recommendation for every C item:** where readings differ, Gordium can compute every listed reading
and report PASS only if all of them pass, FAIL only if all of them fail, and NEEDS REVIEW otherwise. This keeps
"never a false pass" without waiting for the answer, and it shrinks NEEDS REVIEW to the designs where the reading
actually matters.

**Synonym search.** For each question, every synonym that architects and the code use was searched across all
168 pages of Chapter 325 (script: `scripts/syn2.py`; full hit list per term in the Appendix). The "Terms searched"
line in each answer lists only the sections that are actually relevant after reading each hit; false hits (for
example "garage sales", "vehicle overhang", "leave") are named in the Appendix. Notable result: **"storey" never
appears; "survey" never appears (the only hit is "surveyor" in a definition of offices); "setback" is used almost
only in the form districts (§325-45.x), parking (§325-20), ADUs (§325-28) and telecom (§325-29.x), while the
residential rules say "yard".**

---

## Summary table

| # | Question | Class | Gordium's rule or reading | Strength | Key source |
|---|---|---|---|---|---|
| 1.1 | Where 106 Ithaca Rd's lot outline came from; survey? | C (fact) | Only the architects can answer; nothing in the code requires a survey | n/a | — |
| 1.2 | Side lot lines / lot depth on a lot with >4 sides | **B** | Draw a line perpendicular to the front lot line from each end of the front lot line to the furthest rear line; lot depth = average of the two. 106 Ithaca Rd (County outline): (92.01 + 100.28) ÷ 2 = 96.15 ft, so the rear yard needed is 24.0 ft and the 25 ft design passes | City practice | Zoning Administrator's sworn method, BZA Appeal #3202, 815 S. Aurora St (2019–2022) |
| 1.3 | Lot area without a survey | C | Code never defines "lot area" or asks for a survey. Interim: use the survey; without one, compute both the model and the tax-map area and bracket | — | none found |
| 1.4 | Lot width on a curved street | C | Code says "frontage measured on a public right-of-way" / "width at street line"; arc vs chord is not stated. Bracket both | Weak (for either) | §325-8A(7); other cities split |
| 1.5 | Lot depth when side lines are equal | A | Equal lines → that length. On a skewed lot the City measures perpendicular to the front line (see 1.2) | Strong | §325-8A(14)(a) + illustration |
| 2.1 | Yards measured to wall or eave | **A** | Measure to the nearest part of the building (walls, cantilevered floors, porches, decks, steps). Sills, belt courses, cornices and eaves may project **up to 2 ft** into a required yard; more than 2 ft is a violation of that yard | Strong + City practice | §325-18B, §325-3 SIDE YARD, §325-45.2B; 132 Cherry St (2026), Sears St (2026) |
| 2.2 | Corner lots: front yard on every street | **A** | Every yard facing a street is a front yard (residential districts) | Strong + City practice | §325-19C + illustration, §325-25A; 202 Second St, 402 S Cayuga St, 339 S Geneva St |
| 2.3 | Corner lots: the one remaining side yard | **B** | One side yard remains; it is checked against **Column 13** ("other side"); Column 12's slot becomes the "2nd Front Yard" | City practice | BZA worksheets #3174 (2021), ZONE-25-12 (2026); notices #3078 (2017), #3093 (2018) |
| 2.4 | Side yards for detached garage / shed | **A** | Chart side yards apply to the main building only. Detached accessory structures follow §325-25: not in a required front yard; frame ones ≥3 ft from side and rear lot lines, in R-1 ≥6 ft side / ≥3 ft rear. Attached garage = part of main building | Strong + City practice | §325-25; 412 E Yates St #3093 (2018) |
| 2.5 | What may be in the rear yard | **A** | List of every exception in the code (see detail) | Strong | §325-3 YARD; §325-25; §325-18; §325-28; §325-3 BUILDING AREA/TERRACE |
| 3.1 | Garage in building area / coverage | **B** | Garages (attached and detached) **count**. "Parking areas and parking spaces" excluded = open, uncovered parking | Strong text + City practice | §325-3 BUILDING AREA; Column 10; §325-25; 412 E Yates St #3093 (2018) |
| 3.2 | Footprint at ground vs. outline above ground | **B** (C residue) | Count everything above ground seen from above: cantilevered floors, balconies >2 ft, porches, decks, ramps, landings. Not below-grade structures. Eaves up to 2 ft not counted (moderate); eaves >2 ft = C | Strong for floors/balconies; Weak for eaves | Column 10 "above ground", §325-18A; §325-18B |
| 4.1 | Height of a pitched roof | **B** (C residue) | Midpoint between eave and ridge, on the roof section with the highest elevation. Which "eave" (lowest eave / wall plate / drip edge) = C | Moderate–weak | §325-3 HEIGHT; IRC "mean roof height"; NY villages (Depew, Hewlett Bay Park, S. Blooming Grove) |
| 4.2 | Grade plane averaging | C | Code fixes: measure at the walls; where ground slopes away, lowest point within 6 ft or the lot line. Averaging method not fixed → bracket simple per-side and wall-length-weighted | Moderate (for "no single method") | §325-3 GRADE PLANE = IBC §202; 2012 IBC Handbook |
| 4.3 | Main entrance; 12 ft test | A (12 ft) / C (main entrance) | 12 ft test: any point on any side. "Main entrance side": undefined → C | Strong (12 ft) | §325-3 STORY; BCNYS "story above grade plane" |
| 4.4 | Basement vs cellar | C | Interim conservative: if the story tests are met, count it as a story | Moderate (direction only) | §325-3; IBC/BCNYS has no cellar exemption |
| 4.5 | Height bonus: which yards | **A** | Every required front, side and rear yard +1 ft per ft; main buildings only; stories still capped; bonus ≤10% of the limit; not in U-1 | Strong | §325-16C |
| 4.6 | Parapets/chimneys above the limit | A (exemptions) / C (parapet on bonus height) | Exemptions don't change how height is measured; roof features ≤20% of ground floor / ≤30% of roof plane. Whether the 5 ft parapet allowance stacks on bonus height = C | Strong / — | §325-16A, §325-16B |
| 4.7 | Typo "he vertical distance" | A | Read as "The"; no effect | Strong | §325-3 |
| 5.1 | Chart marks •, -, SP | **B** | SP = special permit (§325-9B(1)); • = listed as permitted (§325-8A(2)); - = not permitted (omitted; §325-8B(3)) | Strong (inference from text) | §325-8A(2), §325-8B(3), §325-9B(1) |
| 5.2 | "Public utility structure" = "public utility facilities" | **B** | Same use; outcome identical either way (special permit) | Strong (inference) | chart p.2 row order mirrors §325-9B(1)(b)–(c) |
| 5.3 | Permitted (•) use can still have conditions | **A** | Yes: Column 2 uses are "subject to the further regulations in this section and of Article V" | Strong | §325-8A(2), §325-8B(8) |
| 5.4 | ADU parking | **A** | **No** off-street parking is required for an ADU | Strong | §325-28C(2) |
| 6 | Definitions: category or limit | **B** | All five are categories (they name the use); a design that misses one is a different use, which the use rules then judge | Strong (structure of the code) | §325-3 vs operative sections |
| X1 | Porches, decks, steps, ramps, landings in yards | **A** (steps: B) | All count as part of the building for yards and coverage; City also counts steps and stair walls | Strong + City practice | §325-18A; 209 Bryant Ave #3224 (R-1b, 2022); 511 S Plain #3175; 815 S Aurora #3282 |
| X2 | Accessory structure: non-frame (masonry) building; accessory height | C | §325-25C covers only "frame" buildings; no accessory height limit in §325-25 | — | §325-25 |
| X3 | ADU size/setbacks; "primary front yard" | A (numbers) / C ("primary" vs "secondary" front yard) | 40% of primary floor area (attached); detached new: 800 sf footprint, 2 stories and 20 ft, side/rear 5 ft or primary setback whichever is less | Strong | §325-28C |
| X4 | Corner visibility triangle | A | Nothing >2 ft high within 20 ft triangle at the street corner | Strong | §325-17B |

**Counts (28 rows): A = 11** (1.5, 2.1, 2.2, 2.4, 2.5, 4.5, 4.7, 5.3, 5.4, X1, X4) · **B = 8** (1.2, 2.3, 3.1, 3.2,
4.1, 5.1, 5.2, 6) · **C = 6** (1.1, 1.3, 1.4, 4.2, 4.4, X2) · **split A/C = 3** (4.3, 4.6, X3). Rows 3.2 and 4.1 also
carry a small C residue (eaves in coverage; which eave) that stays NEEDS REVIEW. Of the B readings, 4 rest on City
practice (1.2, 2.3, 3.1, steps in X1), 4 on the code's own text read together (3.2, 5.1, 5.2, 6), and 1 is
moderate-to-weak (4.1, building-code analogy + other NY municipalities).

---

## 1. The lot

### 1.1 Where did the 106 Ithaca Rd lot outline come from? Is there a stamped survey? — **C (a fact only the architects know)**
- **Code (rank 1):** nothing in Chapter 325 requires a survey or says which drawing defines the lot. The word
  "survey" never appears (the only hit, p.5, is "surveyor" in BUSINESS OR PROFESSIONAL OFFICE). §325-38 (p.116) only
  says the Director must determine "that all of the provisions of this chapter ... have been complied with."
- **City practice (rank 2):** the City relies on surveys when it has them. ZONE-26-4..7, 113–119 Sears St (BZA
  3 Mar 2026): "upon survey of the as-built condition of the new subdivided lots, it was found that the new homes did
  not meet the secondary side yard requirements of 5'"
  (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_03032026-3164, p.22). No published City rule
  requiring a survey for a permit was found.
- **Question stays as written** (§1.1 of the questions doc).

### 1.2 Lot depth on a lot with more than four sides — **B (City practice)**
- **Code (rank 1):** "Such percentage shall be taken of the lot depth. If the two side lot lines are of unequal
  lengths, the rear yard percentage shall be taken of the average of the two lengths. (See illustration below.)"
  (§325-8A(14)(a), p.25). The illustration (rendered from p.25) labels "L = AVERAGE LOT DEPTH" and "D = REAR YARD
  DEPTH = STATED % OF L (FROM COL. 14)", with L drawn **perpendicular to the street** between the street line and a
  slanted rear line. "Lot depth" itself is not defined anywhere (synonym search: "lot depth" appears only in
  §325-8A(14) and the form districts §325-45.2E/F).
- **City interpretation (rank 2), directly on point:** BZA Appeal #3202, 815 S. Aurora St (R-3b), a **five-sided lot
  with three side lines** ("The side lot lines are indicated with the letter's 'E', 'B', and 'C'"). The City's staff
  memo to the BZA (MW 12/28/2021) and the Zoning Administrator's sworn affidavit (Gino Leonardi, 27 Nov 2019, Tompkins
  County index EF2019-0509) state the method:
  > "The graphic depiction in the Zoning Ordinance provides that side lot lines should be drawn at a 90-degree angle
  > perpendicular to the front lot line to determine the average lot depth. Accordingly, when a parcel is irregular in
  > shape, the side lot lines are drawn by extending lines at a 90-degree angle perpendicular to the front lot line
  > from each end point of the front lot line and extending to the furthest rear line."

  Worked there as (342.81 + 183.52) ÷ 2 = 263.16 ft. Staff rejected the appellants' alternative of mixing a drawn
  side line with a computed one as "inconsistent with the uniform enforcement and text of the ordinance."
  Sources: https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_02012022-2446 (pp.20–21, Exhibit E, affidavit
  pp.46ff) and https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_01042022-2431. The BZA's final written
  decision (finalized 8 Feb 2022, agenda https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_02082022-2447)
  was **not found** online; a later City notice (Appeal #3282, Nov 2024) says "the original project was zoning
  compliant" (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_11052024-2945, p.44), which is consistent
  with the method having been upheld, but is not proof.
- **Applied to 106 Ithaca Rd** (computed from the County 2026 outline in
  `test_data/.../106_ithaca_rd/gis/county_parcel_2026-10-20.json`, front = the 73.52 ft Ithaca Rd edge): the
  perpendicular from the #104 end of the front line reaches the rear line at **92.01 ft**; the perpendicular from the
  other end runs along the long side and reaches the jog at **100.28 ft**. Average **96.15 ft** → required rear yard
  25% = **24.04 ft** → the 25 ft design **passes** (it passes under options (a) and (c) of the questions doc too, and
  fails only under (b)). On the model's own outline (each side ≈2% shorter) the result is about 94 ft / 23.5 ft.
  (A second reading of "furthest rear line" would extend the second perpendicular past the jog to the main rear line
  extended; the affidavit's own exhibit stops at the first rear-facing line, so 100.28 ft is used here. Worth one
  line of confirmation.)
- **Other sources (rank 4):** practice elsewhere varies (midpoint-to-midpoint, average of extremes, official's
  discretion); a Massachusetts court rejected an ad-hoc diagonal method on an odd lot. Not needed given rank 2.
- **Gordium's reading:** the Zoning Administrator's perpendicular method, labelled "City practice (815 S. Aurora,
  2019–2022)". It adds a new **option (e)** to question 1.2; ask the architects to confirm and, ideally, ask the City
  for the BZA's #3202 resolution.
- **Terms searched:** lot depth / depth of lot (§325-8A(14); §325-45.2E/F), side/rear/front lot line (§325-3 YARD
  p.20; §325-25C), rear yard (§325-3, §325-8A(14), §325-19A).

### 1.3 Lot area, especially without a survey — **C**
- **Code (rank 1):** "lot area" is never defined; Column 10 uses "total lot area" (§325-8A(10), p.25); Column 6 uses
  "Area in Square Feet" (§325-8A(6), p.24); §325-17A "No lot shall be so reduced in area that any required yard
  will be smaller…" (p.48). LOT (p.14) is "a portion or parcel of land, considered as a unit". No survey requirement.
- **City practice (rank 2):** BZA worksheets give lot areas to the hundredth of a square foot (e.g. 113 Sears St,
  "2,669" proposed vs "2671.3" as built, ZONE-26-4, 2026), i.e. from surveys, and the Sears St case turned on an
  as-built survey. This shows practice but not a written rule.
- **Why not settled:** no City document says what to do without a survey.
- **Interim:** bracket (model area and tax-map area); for 106 Ithaca Rd coverage fails under all three areas, so the
  result does not change.
- **Question for the City zoning office:** "For a zoning compliance review, do you require a stamped survey for lot
  area, and if none exists, which do you accept: the tax map, a deed description, or the designer's drawing?"
- **Terms searched:** lot area (§325-8A, §325-11B, §325-17A, §325-35B), survey (no hits), coverage.

### 1.4 Lot width on a curved street — **C**
- **Code (rank 1):** Column 7 is "Minimum Lot Size, Width in Feet at Street Line" and "Lots … shall have frontage
  measured on a public right-of-way equal to or greater than the width specified" (§325-8A(7), p.24). §325-20E(2)–(3)
  (p.57) also uses "width at the street line". BUILDING LOT (p.14) requires "frontage on a street". The words point
  to a measurement **on the street line itself** (which on a curve is the arc), but "width" can also mean the
  straight distance across; the code never says.
- **City practice (rank 2):** BZA worksheets report "Lot Width (Feet)" as a single figure (e.g. "265.83", Appeal
  #3174, 2021) without method. Nothing found on curves.
- **Other cities (rank 4):** split. Fairfax County VA used the chord until 2019, then moved to measuring at the
  setback line; staff reported Charlotte, Loudoun and Prince William use the arc
  (https://www.fairfaxcounty.gov/planningcommission/sites/planningcommission/files/assets/documents/pdf/2019%20verbatims/verbatim121119zoalotwidthdeconly.pdf);
  Everett MA allows straight line or along the curve; Buena NJ measures a tangent at the building line. **Weak**.
- **Interim:** bracket arc and chord. 106 Ithaca Rd passes either way (73–76 ft vs 50 ft).
- **Question for the City:** "On a curved street, is Column 7 frontage the length along the right-of-way line (arc)
  or the straight distance between the side lot corners (chord)?"
- **Terms searched:** frontage (§325-3 p.14, §325-8A(7), §325-19B, §325-20E), lot width / width at street
  (§325-8A, §325-20E).

### 1.5 Lot depth when the side lines are equal — **A**
- **Code (rank 1):** the averaging sentence only applies "If the two side lot lines are of unequal lengths"
  (§325-8A(14)(a)); otherwise "Such percentage shall be taken of the lot depth", which for equal lines is that length.
- **Caveat (rank 2):** on a skewed (parallelogram) lot the City's method in 1.2 measures **perpendicular** to the front
  line, which is shorter than the slanted side. Gordium should use the perpendicular depth there.

---

## 2. Yards

### 2.1 Measured to the wall or to the eave? — **A** (strong + City practice)
- **Code (rank 1):**
  - SIDE YARD: "The required width of side yards shall be measured horizontally from the nearest point of the side
    lot line to the nearest part of any building." FRONT/REAR YARD: "the least distance between the front [rear] lot
    line and the front [rear] of such main building." (§325-3, p.20)
  - "§325-18B. Projecting architectural features. The space in any required yard shall be open and unobstructed
    except for ordinary projections of windowsills, belt courses, cornices, eaves and other architectural features;
    provided, however, that such features shall not project more than two feet into any required yard." (p.49)
  - Ithaca's own newer drafting says the same thing explicitly: "BUILDING PROJECTIONS — No part of any building shall
    encroach into any setback, except as described below: (1) Overhanging eaves and bay windows may project up to two
    feet into any required setback." (§325-45.2B, p.131, Collegetown form districts.) This confirms the City reads an
    eave as part of the building that is *allowed* 2 ft into the yard.
  - §325-18A (p.49): porches, decks, balconies projecting more than 2 ft, ramps and landings "shall be considered a
    part of the building in both the determination of required yards and lot coverage".
- **City practice (rank 2):**
  - ZONE-25-12, 132 Cherry St (2026): building "8' 6" from the inside edge of the sidewalk on the ground floor and
    3'6" … on the upper floors… would provide a front yard of 3.5'" → the City measured to the **overhanging upper
    floors**, not the ground-floor wall (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_03032026-3164,
    p.3).
  - ZONE-26-4..7, 113–119 Sears St (2026): houses 4.6–4.9 ft from the side line where 5 ft is required, because "the
    wall overhangs the foundation"; the variance was for the wall face, while the (non-vented) soffit beyond it was
    not treated as the yard line (same packet, pp.22–23, 39).
- **Gordium's rule:** measure each yard to the nearest part of the building (walls, cantilevered floors, porches,
  decks, balconies >2 ft, ramps, landings, steps; see X1). Separately, check that sills, belt courses, cornices and
  eaves project **no more than 2 ft** into any required yard; more than 2 ft fails that yard. This is option (a) in
  the questions doc, with the clarification that an over-2-ft eave is a violation, not a change of measuring point.
- **Small C residue:** whether a bay window in an R district is an "other architectural feature" (§325-18B) or a
  part of the building. §325-45.2B treats bay windows like eaves, but only in the form districts.
- **Terms searched:** yard, setback, eave/overhang/soffit (§325-18B; §325-45.2B; false hits §325-15A "leave",
  §325-20D "vehicle overhang"), projection/encroach (§325-18A/B, §325-45.2B, §325-28C), cornice (§325-16B, §325-18B).

### 2.2 Corner lots: one front yard per street — **A** (strong + City practice)
- **Code (rank 1):** "C. Corner lot transition. On corner lots in residential districts; buildings must be erected so
  that yards facing public streets shall conform to the minimum front yard requirements of said residential
  district. Such lots shall be deemed to have two adjoining front yards." (§325-19C, p.50). The illustration (rendered
  p.50) labels FRONT YARD on both streets, one SIDE YARD and one REAR YARD. Also "Corner lots shall be considered to
  have two front yards." (§325-25A, p.66); "on corner lots with more than one front yard … front yard parking …
  shall only be permitted on one of the front yards" (§325-20E(4), p.57); CORNER LOT definition (p.7).
- **City practice (rank 2):** 202 Second St, 2014: "The property at 202 Second Street is a corner lot and has two
  front yards. One faces Monroe Street and the other faces Second Street. These front yards are required to be 10 foot
  deep." (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/04012014-330); 402 S. Cayuga St, 2015 "on the
  corner of South Titus and South Cayuga Streets and has two front yards"
  (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/05052015-769); #3174 Hancock St (2021) even uses a
  "3rd Front Yard" for a lot on three streets.
- **Gordium's rule:** option (a) confirmed. (Note §325-19C is limited to residential districts; §325-25A's corner rule
  for accessory structures applies everywhere.)

### 2.3 Corner lots: how many side yards, and which minimum — **B (City practice)**
- **Code (rank 1):** §325-19C + illustration: two front yards; §325-8A(14)(d): "the yard on the opposite side of the lot
  from the street whose address the lot bears shall be designated as the rear yard" (pp.25–26). That leaves one side
  yard. Columns 12/13 (p.25) don't say which value it gets.
- **City practice (rank 2), consistent over 12 years:** the City's BZA worksheets **relabel Column 12 as "2nd Front"
  and keep Column 13 "Other Side Yard"** for the remaining side yard:
  - Appeal #3174, 503 and 625 Hancock St (R-3b, 2021): worksheet header "2nd Front | Other Side Yard", required
    "10 | 10 | 5" (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_01052021-2224, pp.20–22).
  - ZONE-25-12, 132 Cherry St (2026): header "2nd Front | Other Side" (packet _03032026-3164, p.4).
  - Notices: #3078, 339 S. Geneva St (R-3aa, 2017) "Column 11, Front Yard, Column 12, Other Front Yard, Column 13, Side
    Yard" with "a 5' side yard is required" (R-3aa Column 13 = 5 ft, Column 12 = 10 ft)
    (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_07132017-1397); #3093, 412 E. Yates St (2018) "Column
    11, Front Yard, Column 12, Other Front Yard, Column 13, Side Yard"
    (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_04032018-1576); 202 Second St (2014) same pattern.
- **Gordium's reading:** option (b), Column 13, labelled "City practice". In R-1b both are 10 ft, so 106-type houses
  are unaffected.

### 2.4 Do the chart's side yards apply to a detached garage or shed? — **A**
- **Code (rank 1):** "§325-25. Accessory structures, including private garages, storage sheds, toolhouses, garden
  houses, playhouses or similar structures, shall be exempt from side yard requirements contained in the District
  Regulations Chart in § 325-8 and shall be governed by the requirements below: A. … permitted in any side or rear
  yard but not in a required front yard… Corner lots shall be considered to have two front yards. B. … may be placed
  anywhere on a building lot if it is entirely below the finished grade or entirely below the first-floor level…
  C. Frame accessory buildings may not be placed less than three feet from any side lot line or rear lot line in all
  districts, except in R-1 Districts, where accessory buildings may not be placed less than six feet from any side
  lot line nor less than three feet from any rear lot line… D. … detached garage or carport … across a common lot line
  by mutual agreement … shall be permitted." (pp.66–67). §325-7B (p.24): a yard required for one building can't be
  counted as another building's yard.
- **City practice (rank 2):** #3093, 412 E. Yates St (2018): new garage "will have 1 foot of the 3 feet required by the
  zoning ordinance for the side yard" and "3 feet from the rear lot line, meeting the rear yard setback" (§325-25C
  applied, not the chart). 202 Second St (2014): "the garage on the lot does not meet the setback requirements for
  framed accessory buildings under Section 325-25".
- **Attached garage:** part of the main building (BUILDING includes everything "within exterior walls … and a roof";
  ACCESSORY BUILDING is a separate "structure … located on the same premises", p.4), so chart yards apply. Practice:
  409 Campbell Ave (2014) attached garage measured against the 25 ft front yard. **B** for the attached-garage point.
- **Gordium's rule:** option (a) confirmed, plus the §325-25 numbers above become rules of their own. Residue: X2.

### 2.5 What may be built in the rear yard — **A** (a list)
"Except as hereinafter specified" (REAR YARD, p.20) and "unless specifically authorized in this chapter or other
provisions of the City of Ithaca Code" (YARD, p.20) point to these, found by searching every "yard" hit:
1. Accessory structures wholly or partly above grade: "permitted in any side or rear yard" (§325-25A), frame ones
   ≥3 ft from side/rear lines (R-1: 6 ft side, 3 ft rear) (§325-25C); below-grade ones anywhere (§325-25B).
2. Detached ADUs: side and rear setback "5' or setback required for primary structure, whichever is less"
   (§325-28C(8)(b)[2][a], p.72).
3. Projections of sills, belt courses, cornices, eaves ≤2 ft (§325-18B).
4. Terraces/patios at grade (<18 in., no roof): allowed; "neither pergolas or terraces and patios above grade shall be
   located in a required yard" (BUILDING AREA p.5; TERRACE OR PATIO p.19).
5. Parking: rear/side-yard parking areas are allowed subject to §325-20F's landscape rules (§325-20F, pp.58–60).
6. Separately-erected roof-type features (towers, dishes) follow yard rules measured to "any structural or supporting
   member, pole or guy wire" (§325-16A(2), p.46).
7. **Not** allowed as open yard: porches, decks, balconies >2 ft, ramps, landings (§325-18A: part of the building).
8. Fences/walls (§325-17D) and stream setbacks (§325-26) also apply.

---

## 3. Lot coverage

### 3.1 Does a garage count? — **B** (strong text + City practice)
- **Code (rank 1):** BUILDING AREA = "the principal building and all accessory buildings … but shall not include
  parking areas and parking spaces" (p.5); Column 10: "covered by principal and accessory buildings above ground"
  (p.25); §325-25 lists "private garages" as accessory structures (p.66); GARAGE, PRIVATE is "an enclosed space for the
  storage of one or more motor vehicles" (p.11). The wrinkle: PARKING AREA (3) "Private parking: an area or structure or
  portion of a structure devoted to the parking of motor vehicles by the occupants of a dwelling" (p.17) could be read
  to cover a garage.
- **City practice (rank 2):** #3093, 412 E. Yates St (2018): "demolish the existing 187 SF garage to accommodate the new
  315 SF garage. The new garage will increase the lot coverage from 48% to 52% of the 35% allowed by the ordinance for
  lot coverage by buildings." Practitioner evidence agrees: 409 Willow Ave #3254 (2023) and 607 Mitchell St ZONE-25-6
  (R-1b, 2025) both added the detached garage into coverage
  (https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_07112023-2702;
  https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_08052025-3071).
- **Gordium's reading:** option (a): garages (attached or detached) and carports (roofed structures) count; the
  exclusion means open, uncovered parking spaces and parking areas. Label "City practice".
- **Terms searched:** garage/carport (§325-3, §325-25, §325-20E; false hits §325-15D "garage sales"), accessory
  building/structure, coverage, building area, parking space/area.

### 3.2 Footprint at the ground, or everything above ground? — **B** for most parts, **C** for eaves over 2 ft
- **Code (rank 1):** BUILDING AREA is "taken on a horizontal plane at the main grade level" (p.5), but Column 10 —
  the operative rule — counts what is "covered by principal and accessory buildings **above ground**" and adds
  "balconies projecting more than two feet from a building" (p.25), which exist only above grade. So the operative
  test is coverage seen from above, and things that don't touch the ground (balconies) still count. §325-25B lets
  wholly below-grade accessory structures go anywhere.
- **City practice (rank 2):** no coverage case on cantilevers found; for yards the City measured to overhanging upper
  floors (132 Cherry St, 2026), which is the same "above ground" logic.
- **Gordium's reading:** count the outline from above of everything above ground: walls, cantilevered upper floors,
  porches (roofed), decks, balconies >2 ft, ramps, landings. Don't count below-grade structures (a buried garage) but
  do count a deck on top of one. Eaves/cornices projecting ≤2 ft: not counted (**weak**, by analogy to §325-18B and the
  2 ft balcony threshold; no Ithaca source). Eaves >2 ft: **C**.
- **Question for the City:** "Do roof eaves count toward Column 10 coverage, and if so beyond what depth?"

---

## 4. Height, grade, stories, basements

### 4.1 "Average height" of a pitched roof — **B** (moderate-to-weak) with a **C** residue
- **Code (rank 1):** HEIGHT OF BUILDING: "…to the highest level of a flat or mansard roof or to the average height of
  a pitched, gabled, hip or gambrel roof… Where a building contains sections of a roof of varying heights, the height
  of that building shall be measured using that section of the roof that has the highest elevation from grade plane."
  (§325-3, p.12). This settles: mansard → top; gambrel → averaged like a gable; multi-section roofs → the highest
  section. §325-45.2B (p.130) adds for form districts that each step-back portion is measured from "the average grade
  plane adjoining that portion".
- **City practice (rank 2):** none found that states the method.
- **Codes (rank 3):** IRC/RCNYS "MEAN ROOF HEIGHT. The average of the roof eave height and the height to the highest
  point on the roof surface, except that eave height shall be used for roof angle of less than or equal to 10
  degrees." (IRC ch.2; quoted at https://www.thebuildingcodeforum.com/forum/threads/eave-height.36727/latest). This is
  a wind-design term, not a zoning one, so it supports "midpoint" only by analogy. The IBC's own height definition
  ("average height of the highest roof surface") is the same idea.
- **Other cities (rank 4):** NY villages measure "the mean height between eaves and ridge for gable, hip and gambrel
  roofs" (Village of South Blooming Grove local law,
  https://www.villageofsouthbloominggrove.com/wp-content/uploads/Local-Law-REV-7-28-21.pdf; City of Depew,
  https://www.zoneomics.com/code/depew-NY/chapter_16; Village of Hewlett Bay Park "midway between the eaves and the
  peak", https://www.zoneomics.com/code/hewlett-bay-park-NY/chapter_1); Scarsdale instead uses "halfway between the top
  of the plate and the ridge" (https://www.zoneomics.com/code/scarsdale-NY/chapter_1); Dover OH, St. Paul MN, Scituate
  MA: eave–ridge midpoint.
- **Gordium's reading:** option (a), midpoint between eave and ridge of the highest roof section, labelled
  "moderate (IRC analogy) / common NY practice".
- **C residue, precise question:** "For the eave, do you use the lowest eave of that roof section, the top of the wall
  plate, or the roof edge (drip line)? And with eaves at different heights on the same section, which one?"
  (Scarsdale vs IRC shows real disagreement; 1–2 ft of difference on a steep roof.)
- **Terms searched:** height, ridge/eave, gable/hip/gambrel/mansard (§325-3 only), story (§325-8A(8)–(9)).

### 4.2 Grade plane averaging — **C**
- **Code (rank 1):** "GRADE PLANE — A reference plane representing the average of finished ground level on each side
  of the building at exterior walls. On the sides of the building where grade is level, the measurement will be
  taken at a point adjoining the building. Where the finished ground level slopes away from the exterior walls, the
  measurement shall be taken at the lowest point within the area between the building and the lot line or, where the
  lot line is more than six feet from the building, between the building and a point six feet from the building."
  (§325-3, p.11). This fixes *where* to measure (A), but not *how to average*.
- **Codes (rank 3):** Ithaca's wording is the IBC §202 definition with "on each side of the building" added. ICC's
  2012 IBC Handbook: "The method for calculating grade plane can vary based on the site conditions. Where the slope is
  generally consistent … it may only require the averaging of a few points along the exterior wall of a
  rectangular-shaped building… Where the slope is inconsistent or retaining walls are utilized, or where the building
  footprint is complex … a more exacting method for calculating the grade plane must be utilized."
  (https://media.iccsafe.org/news/eNews/2014v11n20/2012_ibc_handbook_p32-34.pdf). So the model code itself prescribes
  no single method.
- **Other cities (rank 4):** wall-length-weighted averages: Newton MA, Montgomery County MD, Kirkland WA, Sunshine Coast
  BC (https://montgomerycountymd.gov/DPS/Process/zspe/building-height.html;
  https://kirklandwa.gov/files/sharedassets/public/v/3/planning-amp-building/planning-applications-and-forms/average-building-elevation-handout.pdf).
- **Practitioner evidence (Ithaca):** applicants state "The average grade plane is USGS 789.30" with calculations
  attached (232-236 Dryden Rd, #3150, 2020, https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_02042020-2046),
  method not stated in the text.
- **Interim:** bracket (a) one value per side, simple average and (b) length-weighted; "a side" = each wall segment
  vs bounding-rectangle side — bracket both.
- **Question for the City:** "When you check a submitted grade-plane calculation, do you accept a simple average of one
  point per side, or do you require a wall-length-weighted average around the whole perimeter? For an L-shaped house,
  is each wall segment a 'side'?"

### 4.3 The "main entrance" and the 12 ft test — **A** (12 ft test) / **C** (main entrance)
- **Code (rank 1):** Column 8 stories are "computed at the main entrance side" (§325-8A(8), p.24). STORY: "A basement
  shall be deemed to be a story when the finished surface of the floor next above is 1) more than six feet above grade
  plane or 2) more than 12 feet above the finished ground level at any point." (p.19). "Main entrance" is not defined
  (synonym search: only §325-8A(8); the form districts use "functioning entry", §325-45.2B).
- **Codes (rank 3):** the 6 ft / 12 ft wording is the IBC/BCNYS "story above grade plane" definition, whose 12 ft test
  is read at any single point on the perimeter (NYS DOS rule text, https://dos.ny.gov/2024-12-2-rule-text-uniform-code).
- **Answer:** 12 ft test = **every side, any point** (A). Main entrance: C.
- **Question:** "Which entrance is the 'main entrance' for Column 8, the one facing the street the address is on, or
  the one the designer designates? And when a basement passes the story test on the downhill side only, does 'computed
  at the main entrance side' override the 'at any point' test?"

### 4.4 Basement or cellar when a space fits both — **C**
- **Code (rank 1):** BASEMENT "partly below grade which has more than half of its height … above the finished ground
  level **at any point**" (p.5); CELLAR "more than half of its height … below the average established curb level or
  finished grade of the ground adjoining the building" (p.6); "A cellar shall not be deemed a story" (p.19). A walk-out
  can fit both; nothing says which wins. "Basement/cellar" appear only in §325-3.
- **Codes (rank 3):** the IBC/BCNYS has no cellar exemption: any level meeting the story-above-grade-plane tests is a
  story. The cellar carve-out is Ithaca-specific, which is why this stays C.
- **Interim (never a false pass):** if the floor above meets the 6 ft or 12 ft test, count the level as a story
  (option (a)), and say so.
- **Question:** "A walk-out level more than half above ground on the downhill side but more than half below the average
  adjoining grade: basement (can be a story) or cellar (never a story)? For the cellar test, curb level or adjoining
  grade when both exist?"

### 4.5 Height bonus: which yards grow — **A**
- "(1) Each required front, side and rear yard is increased one foot on the ground for each one foot of such
  additional height. (2) In all districts, the number of stories permitted may not be exceeded. (3) … the number of
  additional feet may not exceed 10% of the maximum building height … (4) … shall not apply in the U-1 Zone."
  (§325-16C, p.47). Applies to "any main building", so not to accessory buildings. Option (a) confirmed.

### 4.6 Parapets and cornices above the limit — **A** for the exemptions, **C** for stacking on the bonus
- **Code (rank 1):** §325-16A (p.46) exempts spires, cupolas, mechanical penthouses, stair towers, chimneys,
  skylights, solar devices etc. "not intended for human occupancy", but "(2) In no case shall the horizontal surface
  area covered or occupied by such feature exceed 20% of the total ground floor area of the building or 30% of the area
  of the roof plane on which it is located, whichever is less." §325-16B (p.47): "a parapet wall or cornice for
  ornament extending above such height five feet or less." The height definition separately excludes bulkheads and
  mechanical housing. These exemptions change what may stick up, not where height is measured to (A).
- **C residue:** whether "the building height limit" in §325-16B means the chart limit or the bonus height under
  §325-16C, and whether a parapet that is a roof-deck guard (not "for ornament") qualifies. Interim: measure the 5 ft
  from the chart limit (stricter).

### 4.7 Typo — **A**
"he vertical distance" (p.12) is plainly "The"; no effect.

---

## 5. Uses and parking

### 5.1 Chart marks — **B (strong, inference from the code's text)**
- §325-8A(2): "Uses which are permitted in each use district are listed" (p.24); §325-8B(3): permitted uses are
  cumulative "except where otherwise indicated by specific prohibition or omission" (p.26); §325-9B(1): "The uses listed
  under the district regulations in § 325-8, District regulations, which require a special permit from the Planning and
  Development Board, are as follows: … (b) Cemeteries … (c) Public utility facilities … (i) Home occupations…" (p.30).
  The chart's SP rows carry exactly these cross-references (e.g. "Home occupation SP … §325-9B(1)(i)", chart p.2).
- No legend on the chart (checked all text of `zoning_charts_2026-04.pdf`). Reading: • permitted, - not permitted,
  SP special permit. (Side note for the architects: §325-3 defines SPECIAL PERMIT as issued by "the Board of Appeals",
  §325-9B(1) says the Planning and Development Board; it doesn't change the check.)

### 5.2 "Public utility structure" vs "public utility facilities" — **B**
The chart's SP rows run "Cemetery or related building", then "Public utility structure except office" (p.2), the same
order as §325-9B(1)(b) cemeteries, (c) public utility facilities. Same use; result is SP (NEEDS REVIEW) either way.

### 5.3 Can a permitted use still need review? — **A**
Column 2: "subject to the further regulations in this section and of Article V" (§325-8A(2)); §325-8B(8): "All columns
… are subject to the supplementary regulations stated in Article V". Yes; those are separate rules.

### 5.4 ADU parking — **A**
"§325-28C(2) There shall be no off-street parking requirement for an ADU." (p.72; added 5-7-2025 by Ord. 2025-04).
Option (b). The house's own parking is unchanged. (Chart p.14's "1 space per dwelling unit" is overridden for the ADU
by this specific section.)

## 6. Definitions: category or limit — **B (strong, from how the code is built)**
Definitions in §325-3 say what a word means; requirements live in the operative sections (§325-8 chart, Article V).
So the numbers are categories: adult day-care home (≤6 adults), bed-and-breakfast inn (5–10 rooms), kitchen (≥60 sf,
≥5 ft wide). Dwelling unit / rooming unit "separate entrance": also a category, but because a space lacking it is not
a dwelling unit, any design that *claims* a dwelling unit must have it; Gordium's "limit" treatment gives the same
result, so keep it. No City source found either way.

---

## Not-covered sections: extra measurement items

### X1 Porches, decks, balconies, steps, ramps, landings — **A** (steps: **B**, City practice)
- **Code:** §325-18A (p.49) and Column 10 (p.25): porches, attached or freestanding decks, balconies projecting more
  than two feet, ramps and landings count for both yards and coverage. PORCH "shall be deemed part of the building"
  (p.17). DECK includes "ramps, and/or landings and other devices connecting one level with another" (p.7).
- **City practice (steps are not named in §325-18A, but the City counts them):** #3224, 209 Bryant Ave (**R-1b**, 2022):
  "the existing front porch located 10.6' from the property line … The relocated porch steps will further reduce the
  front yard to 8.5' of the required 25'" (https://www.cityofithaca.org/AgendaCenter/ViewFile/Agenda/_07052022-2516,
  p.15); #3175, 511 S. Plain St (2021): "The front porch steps … project 5' into the required front yard, reducing the
  front yard to 5'"; #3282, 815 S. Aurora (2024): a stair's block wall "encroaches into the required side yard by 3'
  1""; #2981, 312 Elmwood Ave (**R-1b**, 2015): a 217 sf "deck/landing for the rear stairs" raised coverage to 25.9%.
- **Gordium's rule:** yards and coverage are measured to porches, decks, balconies >2 ft, ramps, landings and steps.

### X2 Accessory structures: gaps — **C**
§325-25C sets distances only for "frame accessory buildings"; masonry/metal accessory buildings have no distance rule
in §325-25 beyond "not in a required front yard". §325-25 sets no height limit for accessory buildings (detached ADUs
have their own, §325-28C(7)(c)[2]). Question: "Which side/rear distances apply to a non-frame accessory building, and
is there a height limit for accessory buildings other than ADUs?"

### X3 ADUs — **A** for the numbers, **C** for "primary front yard"
§325-28C (p.72): one ADU per parcel; ≤2 bedrooms; not in the primary front yard; attached ADU ≤40% of the primary
structure's floor area, setbacks same as primary; detached new ADU ≤800 sf footprint, ≤2 stories and 20 ft, side and
rear setback "5' or setback required for primary structure, whichever is less", "Front setback, secondary front yard:
same as primary structure". "Primary"/"secondary" front yard are undefined. Plausible reading: primary = the yard on the
street the address faces (as in §325-8A(14)(d)); weak. Question: "On a corner lot, which front yard is the 'primary
front yard' for §325-28C(4)?"

### X4 Corner visibility triangle — **A**
§325-17B (p.48): on residential corner lots nothing over 2 ft high within the triangle formed by the two street lines and
a line joining points 20 ft from their intersection.

---

## What is left for the architects / the City zoning office

1. **106 Ithaca Rd outline and survey** (1.1): where it came from; is there a stamped survey.
2. **Confirm the City's perpendicular lot-depth method** (1.2) as option (e), and whether the second perpendicular stops
   at the jog (100.28 ft) or continues to the main rear line. Ideally get the BZA's written #3202 resolution (Feb 2022).
3. **Lot area without a survey** (1.3): which source the City accepts.
4. **Curved frontage** (1.4): arc or chord.
5. **Which "eave"** for the pitched-roof midpoint (4.1).
6. **Grade-plane averaging** (4.2): simple per side vs length-weighted; what is a "side".
7. **Main entrance** and how it combines with the 12 ft "any point" test (4.3).
8. **Basement vs cellar** for walk-outs (4.4).
9. **Eaves in coverage** (3.2) and bay windows in yards (2.1 residue).
10. **Parapet on top of bonus height** (4.6).
11. **Non-frame accessory buildings and accessory height** (X2).
12. **"Primary front yard"** for ADUs on corner lots (X3).

Confirm-only (Gordium can apply now, labelled as City practice): 2.3 Column 13 for the corner-lot side yard; 3.1
garages count; X1 steps count.

---

## Appendix A: synonym search across all of Chapter 325

Automated (`scripts/syn2.py` over the extracted text; table of contents pages 1–2 excluded; section/subsection
assigned from the nearest "§ 325-N." heading and lettered subsection, pages 3–21 grouped as §325-3 definitions). Each
hit was then read; known false hits are listed after each term.

| Term group | Sections found (page) | Notes |
|---|---|---|
| yard | §325-3 (5,19,20,21); §325-7B (24); §325-8A (25,26); §325-8C (27); §325-9B (31); §325-10C (37); §325-11B (39); §325-12D,G (41,42); §325-15D,E (45); §325-16A,C (46,47); §325-17A (48); §325-18A,B,C (49); §325-19A,B,C,E (49–51); §325-20D,E,F (52,57–59); §325-22F (64); §325-24F (65); §325-25, 25A (66); §325-28C (72); §325-29.3C (78); §325-35A (113); §325-41C (124); §325-45.1F (129); §325-45.2B,G (133,157); §325-45.5F (164) | "yard" in §325-15D = "yard sales" |
| setback / set back | §325-3 (21); §325-8B,C (27,28); §325-10C (37); §325-18C (49); §325-20E,F,H,I (57–61); §325-28C (72); §325-29.2B,C (77); §325-29.3C (79); §325-29.8A, 29.9, 29.9B (91–94); §325-35A,B (113); §325-45.2B,E,F,G (131–160) | residential rules use "yard"; "setback" mainly in form districts, parking, ADUs, telecom |
| eave / overhang / soffit | §325-18B (49); §325-45.2B (131,133) | false: §325-15A "leave"; §325-20D "vehicle overhang" (parking) |
| projection / encroach / cantilever / bay window | §325-3 (5,9,17,18,19); §325-8A (25); §325-18A,B (49); §325-28C (72); §325-45.2B (131,133); others (§325-9C, 11C, 12B/F/G/I, 20D/F, 29.2A, 29.8B, 29.9B, 45.1D, 45.4A) | most others are "project" = development project |
| cornice / parapet / belt course / windowsill | §325-16B (47); §325-18B (49) | |
| porch / stoop | §325-3 (5,17); §325-8A (25); §325-18A (49); §325-45.2B,E,F (131–151) | §325-15D "porch sales" false |
| deck / balcony / terrace / patio / pergola | §325-3 (5,7,19 + others); §325-8A (25); §325-18A (49); §325-45.2B,E,F | some §325-3/§325-9 hits are unrelated words |
| steps / stair / landing / ramp | §325-3 (5,7); §325-8A (25); §325-16A (46, "stairtowers"); §325-18A (49); §325-20D (54,55); §325-45.2B (131) | "steps" never named as a yard element in R rules |
| accessory building / structure | §325-3 (4,5,13,14); §325-8A (25); §325-10C (36); §325-20F,G (58–61); §325-25, A–C (66–67); §325-28A,C (71–72); §325-45.x | |
| garage / carport | §325-3 (4,6,11,17); §325-20E (57); §325-25, 25D (66,67); §325-45.2E,F | §325-15D "garage sales" false; §325-29.10C telecom |
| shed / toolhouse / playhouse / garden house | §325-25 (66); §325-45.2E (138,142,145) | §325-24B, §325-29.11C unrelated |
| story / stories | §325-3 (9,15,19); §325-8A (24,25); §325-16C,F,G (47,48); §325-28C (72); §325-45.x | |
| storey | **none** | |
| half story / attic / mezzanine | §325-3 (15,17,19) | §325-29.4–29.8 hits are false matches inside other words in the telecom article; "half story" never appears |
| basement / cellar | §325-3 only (4,5,6,19) | |
| height | §325-3 (5,6,9,12,14,20,21); §325-8A (24–26); §325-16A–F (46–48); §325-17B,D (48,49); §325-19E (50); §325-28C (72); many telecom/form-district hits | |
| grade plane | §325-3 (11,12,19); §325-45.2B (130) | |
| finished grade / ground / curb level | §325-3 (5,6,11); §325-25A,B (66,67) | |
| main entrance / functioning entry | §325-8A(8) (24); §325-45.2B,E,F | "main entrance" appears only once |
| lot depth | §325-8A(14) (25); §325-45.2E,F | never defined |
| lot width / width at street | §325-8A(7) (24); §325-11B (38); §325-20E (57); §325-45.2E,F,G; §325-45.5C | |
| frontage | §325-3 (14); §325-8A(7) (24); §325-8C (27,28); §325-19B (50); §325-22A (64); §325-29.2B (77); §325-43 (126) | |
| front/rear/side lot line | §325-3 YARD (20); §325-25C (67) | lot lines themselves are never defined |
| corner lot | §325-3 (7); §325-8A(14)(d) (25); §325-17B (48); §325-19C (50); §325-20E(4) (57); §325-25A (66); §325-45.2E,F,G | |
| through lot | §325-8A(14)(d) (25) | |
| coverage | §325-3 (5,20,21); §325-8A(10) (25); §325-16A (46); §325-18A (49); §325-19E (50); §325-20F; others in telecom/form districts | |
| building area | §325-3 (5); §325-16G (48); §325-20F (59) | |
| footprint | §325-8A(15) (26); §325-16D,F (47,48); §325-28A,C (71,72); §325-45.2 | |
| lot area | §325-8A (25); §325-11B (38,39); §325-17A (48); §325-35B (113) | never defined |
| survey | §325-3 (5) "surveyor" only | **no survey requirement anywhere** |
| ADU / accessory apartment | §325-3 (4); §325-27D (68); §325-28 (71–72); §325-45.1F (129, refers to former §325-10) | |
| parking space / area | §325-3 (5,7,11,17); §325-8A (24); §325-20 throughout; others | |
| chimney / bulkhead / penthouse / spire | §325-3 (12); §325-16A (46); §325-45.2B (131) | |

## Appendix B: Ithaca BZA records used (all accessed 2026-10-20)

All 84 BZA agenda packets for 2018–2026 were downloaded from the City's AgendaCenter (category 21) plus older
notices, text-extracted, and searched for every term above. Records cited:

| Record | What it shows | URL |
|---|---|---|
| 1 Apr 2014: 202 Second St; 409 Campbell Ave | corner lot = two front yards; §325-25 setbacks for frame garage; attached garage vs 25 ft front yard | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/04012014-330 |
| 5 May 2015: 402 S. Cayuga St; #2981 312 Elmwood Ave (R-1b) | two front yards; deck/landing counted in coverage | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/05052015-769 |
| 13 Jul 2017: #3078 339 S. Geneva St | "Column 12, Other Front Yard, Column 13, Side Yard"; 5 ft side yard | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_07132017-1397 |
| 3 Apr 2018: #3093 412 E. Yates St | garage counted in coverage (48%→52%); §325-25C 3 ft side; corner-lot column labels | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_04032018-1576 |
| 4 Feb 2020: #3150 232-236 Dryden Rd | practitioner grade-plane and basement-story calculation | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_02042020-2046 |
| 5 Jan 2021: #3174 Hancock St; #3175 511 S. Plain St | worksheets "2nd Front / Other Side Yard"; porch steps reduce yards | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_01052021-2224 |
| 4 Jan / 1 Feb / 8 Feb 2022: #3202 815 S. Aurora St | Zoning Administrator's average-lot-depth method on a 5-sided lot | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_01042022-2431 ; .../_02012022-2446 ; .../_02082022-2447 |
| 5 Jul 2022: #3224 209 Bryant Ave (R-1b) | porch steps counted in front yard | https://www.cityofithaca.org/AgendaCenter/ViewFile/Agenda/_07052022-2516 |
| 11 Jul 2023: #3254 409 Willow Ave | applicant counted detached garage in coverage | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_07112023-2702 |
| 5 Nov 2024: #3282 815 S. Aurora St | stair wall counted in side yard; "original project was zoning compliant" | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_11052024-2945 |
| 5 Aug 2025: ZONE-25-6 607 Mitchell St (R-1b) | applicant counted garage, deck, house in coverage | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_08052025-3071 |
| 3 Mar 2026: ZONE-25-12 132 Cherry St; ZONE-26-4..7 113–119 Sears St | front yard measured to upper-floor overhang; side yard measured to overhanging wall; worksheet "2nd Front / Other Side" | https://www.cityofithacany.gov/AgendaCenter/ViewFile/Agenda/_03032026-3164 |

Searched but not found: BZA minutes or resolution text for #3202; any City guidance document on height, grade plane,
eaves, curved frontage or survey requirements; City permit-application instructions (web search returned only Town
of Ithaca pages, a different municipality).
