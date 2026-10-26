# PR #33 checked in Rhino at df08fc0: address type-ahead

**Purpose:** what `autocomplete_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 in the real start box, with the box captured on screen.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Run | Result |
|---|---|
| As written | 9 of 10, then it stops at claim 6 |
| Copy that records every claim (`autocomplete_results.json`) | **14 of 15**, with claim 7 (no lot, said once) passing |

- **The list fits 1 and 8 rows (claim 2):** 26 pt for one row, 194 pt for eight (as Rhino lays it out, 24 a row).
- **The box grows with the list and stays on screen:** 377 pt tall with one row, 545 pt with eight, always 780 pt wide.
- **No lot (7):** the message wraps inside the box and is said once, with no second "No lot found for …" line.
- **96 is found (6), but the claim fails on spelling.** The lookup asked for "96 Ithaca Rd, Ithaca, NY" and the box
  says "Shown dashed: 96 Ithaca Road, Ithaca, NY, 14850's lot…", the geocoder's own spelling. The claim looks for
  "96 Ithaca Rd", so it fails although the address was found. The claim is too strict. The box's wording ("Road",
  and a comma before the ZIP) could also be tidied to the address as the architect typed it.

## To an architect's eye (`list_open_sheet.png`: "106 Itha" above, "200 " below)

- **With the list open, Cancel and Check stay visible.** The box grows, and nothing is cut off.
- **The eight-row list has an empty band at the bottom.** The rows are painted about 16 pt apart, but the list is
  sized for 24 pt rows. Under "200 Hazel St, Ithaca, NY" is roughly 60–70 pt of empty list. The script's "no empty
  row" claim passes because it uses Rhino's laid-out row height (24 pt), not what is painted.
- The one-row list fits its row.

## Left for a human (keys can't be scripted in Eto; the screen was also locked)

In the address field:
1. Type "106 Itha", press Down (the first suggestion is selected), press Enter (picked), then Enter again (Look up).
2. Type "120 N Cay" and click a suggestion.
3. With the list open, press Esc: it should close the list and not the box.
