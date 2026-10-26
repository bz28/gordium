# PR #33 checked in Rhino at ee8f2ce: address type-ahead

**Purpose:** what `autocomplete_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 in the real start box, and the box watched on screen.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result: claims 1 to 7, 12 of 12 (`autocomplete_results.json`, run twice)

The run used a copy that records every claim, with one fix to the test script (below).

| Claim | Measured |
|---|---|
| 1. fewer than 4 characters: no list, nothing asked | pass |
| 2. one request after the pause; the list fits 1 row and 8 rows, no scroll bar, no empty row | pass: 1 row is 30 px tall (Rhino's own layout 28, 24 a row); 8 rows are 198 px (196) |
| 3. picked: the field says it, the list closes, no new request | pass |
| 4. a stale request is stopped; an answer for text no longer typed is dropped | pass (4 claims) |
| 5. offline: no list, the quiet note, Look up still on | pass |
| 6. no town typed: asked for "96 Ithaca Rd, Ithaca, NY" | pass |
| 7. no lot found: the box says so, the lot shown is still 106's, model unchanged; **box under 1,200 px** | pass: the box is **780 pt** wide throughout (it was about 3,200 px at a3eb1d7) |

## Test-script bugs (in the scripts, not the plugin)

1. **A cached module is read.** Line 43 imports `rhino_logic` at the top, before `fresh_module()` drops the cached
   modules. In a Rhino that has already loaded another head's `rhino_logic`, `logic.SUGGESTIONS_UNAVAILABLE` is
   missing and the run stops after claim 4 (the first run here: #32's 6ba061b module was loaded). The copy drops the
   cached `rhino_logic` before that import.
2. **It leaves its document open.** It closes `OpenDocuments()[:-1]`, every document but the last, and its own test
   document was last. It stayed open after each run; I closed it with the leftovers rule. #32's script has the same
   bug.

## To an architect's eye (`autocomplete_sheet.jpg`, on-screen captures every 0.4 s)

- **With the list open, the box's buttons are cut off.** The box keeps its height (690 px at 2×) when the list opens
  under the address. The list pushes the rest down, so Cancel and Check fall off the bottom edge
  (`list_open_buttons_cut.png`, "1060 Ith" with its one suggestion). Even one row is enough to cut them off; eight
  rows (198 px) would push much more off. The 8-row list was not caught on screen (it was shown between captures);
  the script measured its size.
- The one-row list reads well. It is exactly one row, with no empty row or scroll bar, and the text sits a little
  high in its row.
- Offline: the quiet note "Suggestions unavailable: type the full address and press Look up." appears under the
  address, and Look up stays on.
- No lot found (`no_lot_box.png`): the amber line wraps inside the 780-pt box.
  - It says the same thing twice: "? No City of Ithaca address found … nothing in the model changed." and,
    under it, "No lot found for … (the line above says why): correct the address and press Look up, or put back
    106 Ithaca Rd."
- Claim 6's own lookup ("96 Ithaca Rd, Ithaca, NY") ended with "A map service answered with an error"
  (`claim6_lookup_answer.jpg`). The script claims only what was asked, not the answer.

## Left for a human (keys can't be scripted in Eto)

In the address field:
1. Type "106 Itha", press Down (the first suggestion is selected), press Enter (picked), then Enter again (Look up).
2. Type "120 N Cay" and click a suggestion.
3. With the list open, press Esc: it should close the list and not the box.
