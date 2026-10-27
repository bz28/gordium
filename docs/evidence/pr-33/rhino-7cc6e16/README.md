# PR #33 and #32 in Rhino at 7cc6e16 (2026-10-27)

**Purpose:** Rhino 8 (Mac) results after the row-pitch fix.\
**For:** reviewers.\
**Kept current by:** never changed (a dated record).

- `autocomplete_in_rhino.py`: **15 of 15** as written. Rows are 16 pt apart; the list is 16 pt (one row) and 128 pt (eight); the painted gap under the last text is 1.5 to 3.5 pt.
- `progress_cancel_in_rhino.py` (#32): **29 of 29** with Rhino in front (`osascript` activate first); the keyboard claim passed.
- Root cause: `list_row_px` called `RectOfRow`, which Rhino's Mac table lacks (it has `RectForRow(IntPtr)`), so it always fell back to 20 px a row.
- Still by hand: the keys (Down, Enter, Enter; click a suggestion; Esc closes only the list).
