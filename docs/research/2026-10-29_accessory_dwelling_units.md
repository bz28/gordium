# Research: accessory dwelling units (City of Ithaca, §325-28)

**Purpose:** the research behind the accessory-dwelling-unit rules (`<district>.adu_*` in R-1a to R-3b, and `RU.adu_not_permitted`): what the law says, what was searched, what it settled, and why three questions stay open.\
**For:** anyone checking why Gordium reads the ADU rules the way it does; architects answering the questions.\
**Kept current by:** nobody: a dated record. New research gets its own dated report.

Chapter 325 quotes are from Gordium's stored copy
(`regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/chapter_325_zoning_2026-10.jsonl`); page numbers
are that PDF's pages. Chart quotes are from `zoning_charts_2026-04.pdf`.

**Class** (as in `2026-10-20_architect_questions.md`): **A** = answered by the code's own text; **B** = Gordium's
reading, well sourced, shown to the architect to confirm; **C** = genuinely unclear, an open question.

## 1. What the law says — A

- **Where an ADU is allowed.** Chart p.2 line 30 (Accessory Uses): "Accessory Dwelling Unit • • • • • • • •": eight
  marks, in the columns R-1A to R-3B. RU's cell is blank (§8).
- **What an ADU is** (§325-3B, p.4 lines 7-17): "A smaller, secondary dwelling unit located on the same lot as a
  primary residential, commercial, or mixed-use structure. An ADU must have a separate entrance from the outside of
  the building or through a common hall and must provide living, cooking, sanitary, and sleeping facilities."
  Attached: "connected to or contained within the primary structure, such as a basement, building addition, or
  attached garage". Detached: "located within an existing or newly constructed accessory structure such as a
  detached garage, carriage house, or other freestanding building."
- **§325-28** (added 5-7-2025 by Ord. No. 2025-04, p.71-72). C. ADU requirements:
  - "(1) A maximum of one ADU is allowed per parcel."
  - "(2) There shall be no off-street parking requirement for an ADU."
  - "(3) An ADU may have a maximum of two bedrooms."
  - "(4) ADUs may not be located in the primary front yard."
  - "(5) An ADU may be leased separately but may not be sold separately from the primary structure." "(6) A parcel
    may not be subdivided to separate an ADU from the primary structure with which it is associated."
  - "(7) All ADUs shall meet the following size requirements: (a) Attached ADU: The ADU shall not exceed 40% of the
    floor area of the primary structure. (b) Detached ADU, existing accessory building: none. [1] An existing
    accessory building may be altered or expanded, provided that it does not exceed the size limitations for new
    construction. (c) Detached ADU, new construction: [1] 800 SF maximum building footprint. [2] Maximum height of
    two stories and 20'."
  - "(8) All ADUs shall meet the following setback requirements: (a) Attached ADU: same as primary structure. (b)
    Detached ADU, existing accessory building: none. [1] An existing accessory building may be altered or
    expanded, provided that it does not further encroach upon any setback requirement for new construction. [2]
    Detached ADU, new construction: [a] Side and rear setback: 5' or setback required for primary structure,
    whichever is less. [b] Front setback, secondary front yard: same as primary structure."
- §325-28B: "This section applies to all accessory dwelling units (ADUs) within the City of Ithaca. Area
  requirements for new construction shall apply to any ADU that is permitted on or after the effective date of
  this section."

Two drafting notes, neither changing a rule: in (8) the new-construction item is numbered "[2]" under (b) where (7)
has "(c)"; read by its words, it is the new-construction case, parallel to (7)(c). And (2) is already recorded as a
finding in every district's parking rule (`adu_needs_no_parking`).

**What Gordium checks** (each ✓ or ✕ only from a measured or stated value; blank needs review; not applicable when
no ADU is planned): (1) one per parcel (stated count); (3) two bedrooms (stated); (4) not in the primary front yard
and, for a detached ADU, not in a required front yard (measured); (7)(a) the attached ADU's share of the floor area
(stated areas; §5); (7)(c) the new detached ADU's footprint, height and stories (measured); (8)(b)[2][a] its side
and rear setbacks (measured); (7)(b) and (8)(b) an existing accessory building: what is within the
new-construction limits passes, what is beyond them needs review (it may stay as it is but not grow, which a model
of the finished design can't show). Not checked: (5) and (6) (ownership, not design), the definition's separate
entrance and facilities and the building code (the plans' review, not zoning measurements).

## 2. A detached ADU's building is an accessory structure — A

The DETACHED definition puts the ADU "within an existing or newly constructed accessory structure", so §325-25's
rules for accessory structures reach its building as well as §325-28's: §325-25A, "permitted in any side or rear yard
but not in a required front yard", and, in R-1, §325-25C's six feet from a side lot line (§6). Recorded as the
finding `adu_building_is_accessory_structure` (kind law) in each district's `adu_front_yard`. Gordium measures the
ADU's building once, as the ADU (the solid the architect picks, `adu_building`), never also as an ordinary accessory
building, so §325-25C's three feet (less than §325-28's five) is never the deciding figure outside R-1.

## 3. What was searched

1. **The code text:** every piece the term index lists for an accessory dwelling unit and its words (accessory
   building or structure, accessory use, primary structure, dwelling unit, dwelling, one-family and two-family
   dwelling, habitable space, story, yard, front yard): §325-3B's definitions; §325-8A (the chart's columns: (3)
   accessory uses "are listed"); §325-8B; §325-19C (corner lots); §325-25 and A to D (accessory structures);
   §325-28 A to C; and "floor area" and "setback" wherever they occur (p.9 two-family dwelling, p.14 kitchen,
   p.36 light accessory structure, p.54 parking ratios, p.59 parking setbacks, p.113 §325-38's setback
   deficiencies, the form districts' charts). None defines floor area, a bedroom, or the primary or secondary
   front yard.
2. **City interpretations and Board of Zoning Appeals records:** web searches on 2026-10-29 ("City of Ithaca
   accessory dwelling unit zoning interpretation"; "Ithaca Board of Zoning Appeals accessory dwelling unit";
   "Ithaca ADU setback 325-25"; "Ithaca ADU 40% floor area") found no City interpretation or BZA decision on
   §325-28 (it is from 2025). What was found is the legislative history, as reported:
   - Ithaca Times, 2025-03-07, "Ithaca Common Council advances accessory dwelling unit policy, debates key
     provisions"
     (https://www.ithaca.com/news/ithaca/ithaca-common-council-advances-accessory-dwelling-unit-policy-debates-key-provisions/article_57d66044-facd-11ef-a5a6-93d46f9f9efa.html):
     the side setback was raised from 4 ft to 5 ft "to align with" the state fire code; an earlier draft had a
     600 sf footprint.
   - 607 News Now, 2025-04-08 (https://607newsnow.com/?p=16334): the draft gave an existing accessory structure no
     footprint or setback requirements, and new construction 5 ft side and rear setbacks or the primary's,
     whichever is less, 800 sf, two stories and 20 ft.
   - WSKG, 2025-04-10, and the Ithaca Times: adopted May 7, 2025, 8-3.
   - New York Upstate planning news, 2026-04-08: the City's request for proposals for a pre-approved ADU design.
   None of these speaks to §325-25C, to the floor-area base, or to RU.
3. **NYS Uniform Code / IBC / IRC:** the fire-separation distance behind the 5 ft (IRC R302.1: exterior walls under
   5 ft from a lot line need fire-resistance ratings) explains the figure, not which zoning section governs. The
   IRC R305.1 7 ft ceiling height is what Gordium's measurement uses to say a plain solid under 21 ft tall holds at
   most two stories.
4. **Other cities:** ADU laws word the size limit both ways ("of the primary dwelling", "of the existing primary
   dwelling unit"), by search summary only (2026-10-29); none settles Ithaca's words.

## 4. The secondary front yard's setback — B

"[b] Front setback, secondary front yard: same as primary structure." **Reading** (finding
`secondary_front_setback_is_the_required_one`, strength moderate, to confirm with the architects): the front yard the
district requires of the primary structure (25 ft in R-1a, R-1b, R-2a; 10 ft in R-2b, R-2c, R-3a, R-3aa, R-3b), not
the distance the house happens to stand back. Sources: the same list's side and rear setback is the "setback
required for primary structure" (p.72 line 29), and §325-25A keeps every accessory structure out of "a required front
yard" (p.66 line 38), the same figure. Gordium measures the ADU's least distance to the nearer street
(`adu_front_yard`), so on a corner lot the secondary front yard is held to it too.

Which yard is the primary front yard on a corner lot is the open question 325-28C#1 (the section labels;
`2026-10-20_architect_questions.md` §X3; questions page §5.2). Gordium reads each street as the primary one and the
rule complies only if it does under both. "In the primary front yard" is measured from the FRONT YARD definition
(§325-3B, p.20): "the depth of which shall be the least distance between the front lot line and the front of such
main building": some part of the ADU, seen from above, nearer the street lot line than the front of the main
building; where that front is (the outline with or without what might be eaves, the walls at the ground) is read
every way the drawing allows.

## 5. Open question: 40% of what floor area? — C

"(a) Attached ADU: The ADU shall not exceed 40% of the floor area of the primary structure." Chapter 325 doesn't
define floor area, and doesn't say whether the attached ADU is part of "the primary structure" for this count. The
ATTACHED definition puts the ADU "within the primary structure" (the whole, ADU included); the two-family dwelling's
"one unit may be no larger than 50% of the floor area of the larger" (p.9) compares two units (the ADU against the
rest). Readings: (a) `whole_structure`, 40% of the whole primary structure; (b) `rest_of_structure`, 40% of the
rest of it. For a 1,500 sf house containing the ADU: (a) allows 600 sf, (b) allows 1,500 / 3.5 = 428.6 sf (from
a ≤ 0.4 × (1,500 − a)).

**What Gordium does:** the architect states the ADU's floor area and the whole primary structure's (`adu_floor_area`,
`primary_floor_area`). Within (b) passes (both readings); over (a) fails (both); between needs review. Recorded in
every district's `adu_attached_size`.

## 6. Open question: R-1, 6 ft or 5 ft from a side lot line? — C

§325-25C: "in R-1 Districts, ... accessory buildings may not be placed less than six feet from any side lot line nor
less than three feet from any rear lot line" (p.67). §325-28C(8): a new detached ADU's "Side and rear setback: 5' or
setback required for primary structure, whichever is less" (p.72), and in R-1 the primary structure's required side
yards are 10 ft and its rear yard at least 20 ft, so 5 ft. §325-28 is later (2025) and specific ("All ADUs shall meet
the following setback requirements"); §325-25C is general and older; neither says it overrides the other, and both
are met at 6 ft. The Council's debate (§3) set 5 ft for fire-code reasons without mentioning §325-25C. Whether
§325-25C's R-1 clause reaches buildings that aren't frame is itself open (325-25C#1, questions page §5.1).
Readings: (a) `adu_section_governs`, 5 ft; (b) `both_apply`, 6 ft.

**What Gordium does:** in R-1a and R-1b, 6 ft or more passes, under 5 ft fails, 5 ft to under 6 ft needs review.
Rear: 5 ft under both (§325-25C's 3 ft is less). Recorded in `R-1a.adu_detached_setbacks` and
`R-1b.adu_detached_setbacks`.

## 7. Open question: R-2c, a primary structure whose required side is 0 ft — C

In R-2c the chart's other-side minimum is "0 ft /5 ft / 10 ft [fn15]": note 15's 0 ft is for zero-lot-line houses
and semi-detached houses on their attached sides (and attached houses are treated alike by the R-2c side-yard rule's
own open question, questions page §5.8). "Whichever is less" then gives 0 ft if the primary structure's least
required side is meant, though that 0 ft is for a party wall on the lot line, not a freestanding building. Readings:
(a) `five_feet`; (b) `primary_least_side`, 0 ft.

**What Gordium does:** 5 ft or more passes; under 5 ft fails for every other use (their required sides are 10 ft and
5 ft) and needs review for a zero-lot-line, semi-detached or attached house. Recorded in `R-2c.adu_detached_setbacks`.

## 8. RU's blank cell — B

The ADU row has eight marks, R-1A to R-3B; RU's cell is blank, not "-". **Reading** (finding `blank_cell_not_listed`,
strength strong, to confirm with the City zoning office): not permitted in RU. §325-8A(3): accessory uses permitted
"are listed" (p.24); §325-8B(3): uses are cumulative "except where otherwise indicated by specific prohibition or
omission" (p.26). §325-28B's "This section applies to all accessory dwelling units (ADUs) within the City of Ithaca"
sets the requirements wherever an ADU may be; it doesn't permit one everywhere (the definition's "commercial, or
mixed-use structure" shows ADUs are allowed in other districts' charts too, each by its own listing). The blank,
unlike the "-" the chart uses elsewhere, may be an oversight in the 2025 amendment, which is why the City is the one
to confirm. **What Gordium does:** `RU.adu_not_permitted`: no ADU passes, an ADU fails, not said needs review.
