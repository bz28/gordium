# Drawing-style dimensions (PR #29) at 2c82f69: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the re-run after the f6642a9 findings (labels off screen, the height words in the house), and an
architect's look at Top and Front.\
**For:** the coordinator, the #29 job, reviewers.\
**Kept current by:** never changed (a dated record).

`dimensions_in_rhino.py` as written (it runs through now): **18 of 19** (`dimensions_results.json`). The Top
viewport is 656 × 668 px here.

| Claim | Result |
|---|---|
| Every label shown wholly inside the view, at the default zoom and at Zoom Extents (new) | pass |
| Front: the height's words along it, outside the house, inside the view (new) | pass |
| One per yard, dashed required lines, no shared starts, red fails, grey complies, 10'-0" required line, square within 0.1°; the Front height dimension; labels off; zoomed out | pass |
| **1 every label shown sits on screen clear of the status box, the house and the other labels** | **fails**: the front yard's label overlaps the southwest yard's (labels 0 and 2) |

## To an architect's eye

**Top, default zoom** (`1_top_labels_on.png`):
- The **failing** southwest side yard: "✕ 7'-0 5/8" < 10'-0"" in red, on a leader, just above the notice bar.
  Readable, and "<" reads as "less than required". The short form drops the yard's name, but the notice just below
  names it.
- **The front yard's label can't be read.** "? 26'-11 3/4"" is set vertically ("forced") at the very left edge, over
  the southwest label, and runs down under the notice bar.
- The rear yard: "? Rear yard 27'-6 7/8" (approx.)", vertical, reading bottom to top, beside its line on a leader.
  Readable.
- The northeast side yard (complies): "✓ 32'-4 1/4"", grey, on its line. Readable.
- The "min" tags are faint and small. "min 25'-5 1/8"" at the top is half covered by the edge label "69'-6 1/8"",
  and "min 10'-0"" on the left sits inside the red and amber strip.
- No text is mirrored.

**Top, Zoom Extents** (`1b_top_zoom_extents.png`): every label is whole. But the front yard's vertical label
("? Front yard 26'-11 3/4" (approx.)") stands left of the house, alongside the side yard, not near its own line
(which runs down from the house's front corner). An architect could take it for a side-yard dimension. The two
"min" tags at the top (21'-1 5/8" and 25'-5 1/2") sit close together, and the rear dimension line runs through the
first.

**Front** (`2_front.png`): "✓ Building height 35'-0"" runs along its vertical line, beside the house and outside it.
Readable. Fixed since f6642a9.
