# Research: the rules the residential coverage audit found missing (City of Ithaca, Chapter 325)

**Purpose:** the research behind the rules added on 2026-10-27 for the gaps the residential coverage audit (PR #39) found: each further primary building's lot area (§325-8B(1)) and RU's limit on primary buildings (chart p.2 note 3), the 3-to-6-unit cap on an attached building (§325-3B), a yard used for two buildings (§325-7B), the South Hill Overlay (§325-8E), and new structures near streams (§325-26). What the law says, what was searched, how each question was classified.\
**For:** anyone checking why Gordium reads these rules the way it does; architects confirming a reading.\
**Kept current by:** nobody: a dated record. New research gets its own dated report.

Chapter 325 quotes are from Gordium's stored copy
(`regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/chapter_325_zoning_2026-10.jsonl`); page numbers
are that PDF's pages. Chart quotes are from `zoning_charts_2026-04.pdf`.

**Class** (as in `2026-10-20_architect_questions.md`): **A** = answered by the code's own text; **B** = Gordium's
reading, well sourced, shown to the architect to confirm; **C** = genuinely unclear, an open question.

**What was searched, in Ben's order.**
1. The code text: every piece the term index lists for "lot" and "yard" and their synonyms, the §325-3B definitions
   of PRIMARY STRUCTURE, STRUCTURE, ACCESSORY BUILDING OR STRUCTURE, ACCESSORY DWELLING UNIT, LOT, LOT BUILDING,
   YARD (front, side, rear), the dwelling types (one-family detached, semi-detached, attached; two-family; multiple;
   ROW HOUSE); §325-7, §325-8A(6), §325-8B, §325-8E, §325-25, §325-26; the chart p.2 (use rows, notes 2 and 3) and
   p.3 (lot sizes, note 3). A text search of the whole chapter for "stream", "inlet", "creek", "waterway",
   "watercourse", "bank", "water level", "primary", "principal building", "main building", "South Hill".
2. City interpretations and BZA records: web searches on 2026-10-27 for City of Ithaca Board of Zoning Appeals
   decisions, Planning Board records and City interpretations on §325-26, §325-8B(1), §325-7B, §325-8E and attached
   houses found none (ecode360 refused automated fetching; nothing on cityofithaca.org or in news reports applied
   these sections). News reports on the South Hill Overlay's adoption (The Ithacan,
   https://theithacan.org/27659/news/zoning-laws-prevent-building-of-student-housing-on-south-hill/; Ithaca Times,
   https://www.ithaca.com/news/ithaca/new-overlay-zoning-proposal-seeks-to-wrangle-south-hill-rentals/article_86b34dd4-a3a3-11e7-87ea-fb9a48ab4094.html;
   both read 2026-10-27) say its aim was one primary structure per tax parcel; they don't give its boundary.
3. NYS Uniform Code / IBC commentary: these are zoning sections with no building-code counterpart.
4. Other cities' codes: §325-7B is the standard zoning clause found in many New York codes (for example Yonkers
   §43-33 and East Rockaway §288-83, read through search summaries on 2026-10-27, not in full); none found spells
   out how the yards of two principal buildings on one lot are divided.

## 1. Each further primary building's lot area (§325-8B(1)) — A

§325-8B(1) (p.26): "For minimum lot size requirements stated in Column 6, Area in Square Feet, for all residential
use districts, each square-footage requirement applies separately to the initial permitted primary use and to each
additional permitted primary use located in a separate building on the property in question (e.g., in R-2b
Districts, an area of 3,000 square feet is required for a one family house or a two-family house, and an additional
area of 3,000 square feet is required for each additional one-family house or two-family house on the property)."
The chart's lot-size heading carries note 3, "(3) See §325-8(B)(1)." (p.3).

So with two or more primary buildings the lot needs each building's figure, added together. Gordium checks it in
every residential district (`<district>.lot_area_each_primary_building`):
- one primary building: the use's own figure once, as the use's own lot-area rule asks (a use whose figure grows
  with units, rooms or occupants, or is a flag or an open question, is left to its own rule);
- two or more, every one holding the lot's use (`primary_buildings_same_use`): the use's figure once per building;
- a building of another use, or that not said: needs review (each building's own figure, added by hand);
- a use whose figure grows with the units, rooms let or occupants (R-2c's notes 4 to 6, R-3's note 7, R-3b's note
  8, RU's note 9), or is itself a flag or an open question for one building (a zero-lot-line house in R-3, a
  dormitory or nursing home), with two or more buildings: needs review, since how they split between the buildings
  isn't known.

## 2. What is a primary building? — A, with a B

§325-3B PRIMARY STRUCTURE (p.17): "A single structure (located on a parcel) containing a use permitted in the zoning
district in which it is located." ACCESSORY BUILDING OR STRUCTURE (p.4): "A structure, the use of which is
incidental to that of the main building and which is located on the same premises." ACCESSORY DWELLING UNIT (p.4):
on "the same lot as a primary residential, commercial, or mixed-use structure". So a garage, a shed and an ADU are
not primary buildings (A).

**How Gordium counts them (B, measuring):** a massing model can't show what a building is used for. The main
building is one. A solid standing apart from it is counted as a second only if it could hold a home (enclosed, at
least a 7 ft story tall, a habitable room's 70 sf: the test Gordium already uses for which building could be the
main one) and the architect hasn't listed it as an accessory building. A shed or a deck is never counted. A large
garage or a second house can't be told apart, so both are read (every one an accessory building / every one a
primary building), and a rule that the count could change waits for the architect's count (needs review).

## 3. RU: how many primary buildings (chart p.2 note 3) — A, with the open question kept

"(3) Properties less than 60,000 SF may only have one primary structure. Properties greater than 60,000 SF may have
two primary uses, if approved by ILPC and Planning Board. Properties with at least 90,000 SF can have as many as
three primary uses if approved by ILPC and Planning Board." With the count, `RU.primary_structures` is now a rule:
one complies on any lot; two on a lot over 60,000 sf, or three on 90,000 sf or more, need review for the two
approvals (Gordium can't know they were given); fewer square feet or more buildings do not comply. The existing open
question (questions §5.13: a lot of exactly 60,000 sf; whether "primary uses" means buildings) stays open; two
buildings on exactly 60,000 sf need review under both readings, so it changes no result yet. Each building is read
as one primary use (Gordium's use is one per lot): Gordium's reading of the question's second part for now, to confirm; under the other reading (uses, not buildings) two buildings of one use on a large lot need no approvals, where Gordium says needs review (the cautious side).

## 4. Three to six units in an attached building (§325-3B) — A

ONE-FAMILY ATTACHED DWELLING (p.8): "A building containing three or more one-family dwellings ... A maximum of six
one-family dwelling units may be attached to form a single building." R-2c checked it already; R-3a, R-3aa, R-3b and
RU now do too (`<district>.attached_units_per_building`), from the whole building's units the architect states (a
blank needs review). Whether a row of seven or more could instead be built as a multiple dwelling (§325-3B MULTIPLE
DWELLING (5): "row house, townhouse") is not settled by the code (the definitions point both ways, as in questions
§5.6); Gordium doesn't steer the architect to it, and doesn't check a row house's own limits yet.
