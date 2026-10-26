# PR #29 checked in Rhino at e4e5018: dimensions through the shared placer

**Purpose:** what `dimensions_in_rhino.py` and `mvp_checks_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, docked Top 656 × 668 px, the sample with the failing southwest side yard.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Script | Result |
|---|---|
| `dimensions_in_rhino.py` as written | **21 of 24**: no label is recorded at all, so the three label claims fail |
| copy with each frame really drawn (`dimensions_drawn_in_rhino.py`, `dimensions_results.json`) | **24 of 24** |
| `mvp_checks_in_rhino.py` as written (`mvp_results.json`) | **13 of 13** |

## Why the dimensions script fails as written (a test-script problem)

Its `drawn()` calls `view.Redraw()` and then `g.settle_labels()`. On the Mac, `Redraw()` only schedules the frame,
so no frame is drawn, no labels are asked for, and `settle_labels()` has nothing to place. The copy draws each frame
on the spot with `view.CaptureToBitmap(size)`, before and after settling, counting the settled frame once. Nothing
else changed.

## To an architect's eye (`1_top_labels_on.png`, `mvp_labels_off.png`)

- Every number is placed beside its line, and none covers another, the house or the status box.
- **Numbers split in the middle.** Two lot-edge lengths wrap onto two lines: "101'-1 / 1/2"" and "92'-1 / 3/8"". A
  dimension should never break inside the number.
- The failing southwest yard's label puts "✕" alone on one line, with "7'-0 5/8"" under it.
- "? 26'-11 3/4"" (front yard) sits on the bottom edge of the view.
- "min 10'-0"" lies on the view's axis icon.
- No notice is drawn in this view (`1_top_notice.png` is the same picture as `1_top_labels_on.png`).
- **Labels off** (MVP): the failing yard's shortfall is said in the notice at the top left. Nothing is beside the
  yard itself, and the status box isn't drawn in that frame.
