# PR #33 checked in Rhino at a3eb1d7: address type-ahead in the start box

**Purpose:** what `autocomplete_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 (stand-in addresses and recorded lookups, no live call), and what is left for a person to check by hand.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

Run in a copy that records every claim (`autocomplete_results.json`), with a 7-minute cap: **claims 1–4 pass (7 of
7 recorded); claims 5–7 were not recorded**, because the run stalled.

| Claim | Result |
|---|---|
| 1 "106": no list, nothing asked (fewer than 4 characters) | pass |
| 2 "106 Itha" a character at a time: one request after the pause, the list shows "106 Ithaca Rd, Ithaca, NY" | pass (`list_106_itha.png`) |
| 3 picked: the address field says it, the list closes, no new request | pass |
| 4 a stale answer: the earlier request stopped; the newer typing's list shows 1060's address; an answer for text no longer typed is dropped; then 96 Ithac's own answer shows 96's address | pass (4 claims) |
| 5 offline, 6 the town added on Look up, 7 an address with no lot | **not recorded** |

**Where it stalled:** at the cap, the box showed step 7's state (`stall_box_no_lot_found.png`): "No City of Ithaca
address found for 12345 Nowhere Blvd, Ithaca, NY 14850 … The lot shown is still 106 Ithaca Rd's: nothing in the
model changed.", with Check off. At the same moment a Gordium wait window was open, "Checking the rules… 0 s", its
seconds not moving (`stall_wait_window.png`). A check seems to have started under the open box, and each waited on
the other. Esc cleared it; I then closed the test document the run had left open.

## To an architect's eye

- The suggestion list sits right under the address, the box's own list: readable. It keeps a fixed height, about
  five rows of empty space for one suggestion, which pushes the rest of the box down.
- In the no-lot state the amber line is one unbroken line about 3,200 px wide, so the box stretches across the
  whole screen.

## Left for a person (keys can't be scripted in Eto)

In Edit site…'s address:
1. Type "106 Itha", press Down: the first suggestion is selected.
2. Press Enter: it is picked into the address field, and the list closes.
3. Press Enter again: Look up runs.
4. Type "120 N Cay", click a suggestion: it is picked.
5. With the list open, press Esc: the list closes, and the box stays open.
