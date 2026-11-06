# Research: the private garage's car limit (City of Ithaca, zoning chart p.2 notes 6 and 7)

**Purpose:** the research behind `<district>.private_garage` (R-1a, R-1b, R-2a, R-2b, R-2c): what the law says, what was searched, and why two questions stay open.\
**For:** anyone checking why Gordium reads the garage limit the way it does; architects answering the questions.\
**Kept current by:** nobody: a dated record. New research gets its own dated report.

Chapter 325 quotes are from Gordium's stored copy
(`regulations/jurisdictions/new_york/ithaca_city/2_extracted_text/chapter_325_zoning_2026-10.jsonl`); page numbers
are that PDF's pages. Chart quotes are from `zoning_charts_2026-04.pdf`.

**Class** (as in `2026-10-20_architect_questions.md`): **A** = answered by the code's own text; **B** = Gordium's
reading, well sourced, shown to the architect to confirm; **C** = genuinely unclear, an open question.

## 1. What the law says — A

- Chart p.2 line 32 (Accessory Uses): "Private garage •[fn6] •[fn6] •[fn6] •[fn6] •[fn7] • • • •", in the columns
  R-1A, R-1B, R-2A, R-2B, R-2C, R-3A, R-3AA, R-3B, RU. Note 6 (line 47): "(6) For not more than three cars." Note 7
  (line 48): "(7) For not more than six cars per building." R-3a, R-3aa, R-3b and RU have no note: no limit.
- §325-8A(3) (p.24): "(3) Column 3: Permitted Accessory Uses. Uses permitted to be accessory to the main use of the
  premises are listed, subject to the further regulations of Article V."
- §325-3B (p.11): "GARAGE, PRIVATE — An enclosed space for the storage of one or more motor vehicles, provided that no
  business, occupation or service is conducted for profit therein." So a carport (not enclosed) isn't a private
  garage, and an attached garage is one (an enclosed space, wherever it is).

So a private garage holding more than the note's cars isn't a permitted accessory use in those districts.

## 2. What was searched

1. **The code text:** every piece that mentions a garage, a car, a carport or vehicle storage: §325-3B ACCESSORY USE
   (p.4: "(7) Garages within a residential building or on the premises thereof used primarily for the storage of
   passenger-type motor vehicles"), ACCESSORY BUILDING OR STRUCTURE, ACCESSORY DWELLING UNIT, ATTACHED and DETACHED
   (an ADU may be in an attached or detached garage), BUILDING, STRUCTURE, PRIMARY STRUCTURE, LOT, BUILDING, GARAGE,
   PRIVATE, PARKING AREA ("(3) Private parking: an area or structure or portion of a structure devoted to the parking
   of motor vehicles by the occupants of a dwelling located on the same building lot"), PARKING GARAGE, PARKING SPACE;
   §325-8A (the chart's columns; (4) says the parking spaces "shall be provided for each building hereafter erected or
   altered"); §325-20 (off-street parking: D, E, F count cars in parking areas, not in garages); §325-25 ("Accessory
   structures, including private garages, storage sheds ...": where they may stand) and §325-25A, C, D (a detached
   garage or carport across a common lot line). None counts cars in garages, or says whether note 6 is per garage.
2. **City interpretations and Board of Zoning Appeals records:** web searches on 2026-10-29 ("City of Ithaca Board of
   Zoning Appeals private garage three cars variance"; "Ithaca NY zoning private garage not more than three cars
   interpretation"; "Ithaca R-2c garage six cars per building") found no City interpretation or BZA decision on
   either note. The City's 2010 zoning chart, posted by the Fall Creek neighborhood association
   (https://www.fhia.org/wp-content/uploads/Minutes/Ithaca_zoning_regulations_section_325-8.pdf, read 2026-10-29), has
   the same limits in other words ("Private garage for not more than 3 cars" in R-1 and R-2; "Private garage for not
   more than ... cars per building" in R-2c, its number not legible in the PDF's text; and in R-3 "Private garage for
   4 or more cars"), so the wording is old and was never clarified there. Matter of Avramis v Sarachan (2012,
   https://nycourts.gov/REPORTER/3dseries/2012/2012_05364.htm), which search results describe as an Ithaca BZA case
   on parking spaces, couldn't be read (the page refused automated reading, 2026-10-29); by that summary it is about
   parking spaces, not the garage limit.
3. **NYS Uniform Code / IBC:** no counterpart (a zoning use limit, not a building-code one).
4. **Other cities:** several codes cap a private garage's cars (Lynbrook and Hempstead, NY, for example, by search
   summary only, 2026-10-29); none read settles how Ithaca's note is counted.

## 3. Open question: each garage, or the lot? (R-1a, R-1b, R-2a, R-2b) — C

"For not more than three cars" is written on the use "Private garage", and a private garage is "an enclosed space",
which fits a limit on each garage; but nothing says whether a lot may have two garages of three cars each. Readings:
(a) each private garage; (b) all the lot's private garages together.

**What Gordium does:** the architect states the cars all the lot's garages hold together (`garage_cars`) and, only
when that is over three, how many garages (`private_garages`). Three or fewer in all complies under both readings;
more than three times the garages means some garage holds more than three, which fails under both; in between needs
review. A blank needs review, never a pass.

## 4. Open question: per what building? (R-2c) — C

"Six cars per building" doesn't say which building. A private garage may stand alone or be "within a residential
building" (ACCESSORY USE (7)); §325-8A(4)'s "for each building" is a building that needs parking, a primary
building. Readings: (a) each building holding a private garage; (b) each primary building, its garages together;
(c) the whole lot.

**What Gordium does:** as in §3, with six: six or fewer in all complies under every reading; more than six times both
the garages and the primary buildings (`primary_buildings`, counted as for §325-8B(1)) fails under every reading; in
between needs review.
