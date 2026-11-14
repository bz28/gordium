# A real house: 80 South William Street (Lot 2), Pearl River, Town of Orangetown, NY

**Purpose:** the first real house for egress checking: a four-bedroom, two-story house with a basement, transcribed from its public planning-board drawings, with every egress rule worked out by hand.\
**For:** anyone testing or changing egress measuring and checking; architects checking the hand answers.\
**Kept current by:** whoever changes the interior description format (`docs/interior/interior_description_format.md`) or adds an egress rule this house should be checked against.

## The source

- **Drawings:** "Proposed Bennington Model", R&L Property Development Corp., Eric Knute Osborn, Architect. Five sheets, A-1 to A-5, dated 30 Dec 2025 (A-3: 21 Aug 2025). Filed with the Town of Orangetown planning board and posted publicly: <https://www.orangetown.com/wp-content/uploads/2026/02/68.20-2-76.2-80-South-William-Street-Lot-2-Arch-Plans.pdf> (SHA-256 `c6879996539fb1df257b58117bcc4bb590811ab63979fb4ab3eeaa639651a34d`).
- **Not in this repository.** The drawings are the architect's copyright, so only our transcription is kept here, with a citation (sheet and callout) for every value. Our copy is in the archive outside the repository.
- **The code:** 2025 Residential Code of New York State, which the title sheet cites.

## The files

| File | What it is |
|---|---|
| `house.yaml` | The house in the interior description format (`gordium.interior/1`). Every value has a `cite` (sheet, drawing, callout); every key the drawings can't fill is under `absent`, with why |
| `expected.yaml` | What the measuring code should return, worked by hand before the code ran (its own commit) |
| `answer_key.yaml` | For each egress rule: what the drawings give, the arithmetic, and the outcome (complies / fails / needs review) |

`packages/model_measurement/tests/test_real_houses.py` checks all three.

## What the drawings give, and what they don't

Construction drawings for a house like this state **requirements more than sizes**. Windows are given as size codes ("3046 DH": a double-hung about 3'-0" by 4'-6"), "Andersen or equal", with a schedule "for design intent only"; the typical stair detail says "9" min" tread and a "7 1/2"" riser, but no floor-to-floor height is given; railings are "36" high". So:

- **Settled from the drawings:** bedroom sizes and ceilings (all comply), every bedroom has an escape window marked, the top landing of the main stair, the single steps onto the bridge, the hallway widths, the landing outside the front door, the level railings' 36 in height, the front door being the side-hinged exit door.
- **Not settled:** every escape window's clear opening (area, height, width, sill height), window fall protection, the basement's escape window and its well, stair risers, treads, headroom and width, guard openings, the exit door's clear width and height. Gordium must say **needs review** for each: never a pass on a guess.
- **Two real risks the arithmetic shows** (answer key): a 3046 double-hung, the only escape window in bedrooms 2 and 3, can come in under 5.7 sf or 24 in high once its frame is deducted; and the main stair's headroom under the second-floor hallway falls below 6'-8" if its treads are deeper than about 10.3 in.

## The drawings disagree with themselves

| # | Where | One sheet says | Another says |
|---|---|---|---|
| 1 | The code edition | A-1 title sheet: "2025 RESIDENTIAL CODE OF NEW YORK STATE" | A-1 stair & railing notes: "COMPLY WITH THE 2020 NYS RESIDENTIAL CODE"; A-2 stair detail: "MINIMUM 6'-9" HEADROOM AS PER 2020 NYS CODE", "TOP RAIL AS PER 2020 NYSRC"; A-5 section: "36" HIGH RAILING AS PER 2020 NYS RESIDENTIAL CODE"; A-2 escape-opening detail cites "R310.2.1" (the 2020 number; the 2025 code's is R319.2.1) |
| 2 | Stair headroom | A-1 stair notes: 6'-8" | A-2 stair detail: 6'-9" (both meet the 2025 code's 6'-8") |
| 3 | Escape window sill | A-1 door & window notes: 44" | A-1 window & door notes: "NOT TO EXCEED 42"" |
| 4 | Master bedroom windows | A-3 plan: "(2) 3046 DH" | A-5 schedule: 3052 |
| 5 | Bedroom 4 windows | A-3 plan: "(2) 3052 DH" | A-5 schedule: 3046 |
| 6 | Master bedroom casements C15 | A-4: marked E (egress) | A-5 schedule: no "EGRESS" remark |
| 7 | Rooms in the schedule | A-5 schedule: "DEN/GUEST 147 SQ. FT." on the first floor | A-2: no such room; the bonus room (A-3), whose windows are marked E, isn't in the schedule |
| 8 | Main stair risers | A-2: "UP 16R" | A-3: "DN 15R" (both fit if the 16th is the 7 1/2" step from the bridge up to the second floor) |
| 9 | Basement escape windows | A-2 plan: "CW14" in areaways ("SEE DETAIL THIS SHEET": A-2's own escape-opening detail, which gives only minimums) | A-5's window-well details, the only areaway details, show a "4040 EASY-BUCK" window |
| 10 | Dates | A-1, A-2, A-4, A-5: 30 Dec 2025 | A-3: 21 Aug 2025 |

## Questions for the drawing's architect

1. Which window units are ordered for the bedrooms' escape windows, and what is each one's net clear opening (width, height, area) and the height of its bottom above the floor? (Bedrooms 2 and 3 depend on a 3046 double-hung.)
2. Master bedroom and bedroom 4: 3046 or 3052? For every 3052 on the second floor (the bonus room's too), is window fall protection provided (R321.2.1: the bottom about 19 in above the floor)?
3. Is the bonus room ever a bedroom? Its windows are marked E; if it is, R319.1 needs it to have its own escape opening checked.
4. The main stair: floor-to-floor height, riser count to the bridge, tread depth, and what the A-2 "10'-0"" along it spans. If it is the run of 14 treads, each is 8.57 in, under 9.
5. The basement stair: floor-to-floor height (13 risers may rise at most 107.25 in).
6. The basement escape windows: the CW14 on the plan or the 4040 in the detail? And the well's size at its outer edge (the detail draws it tapered, dimensioned only at the wall), and does the window open fully in it?
7. The front door: how far below the threshold is the covered porch (R318.3.1: at most 1 1/2 in, or 8 1/4 in for a door that doesn't swing over it)?
