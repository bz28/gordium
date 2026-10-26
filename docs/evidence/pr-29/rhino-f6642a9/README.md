# Drawing-style dimensions (PR #29) at f6642a9: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the first run with the labels drawn along their lines (Text3d), and what the plan and elevation show
to an architect's eye.\
**For:** the coordinator, the #29 job, reviewers.\
**Kept current by:** never changed (a dated record).

`dimensions_in_rhino.py` as written stops with a ZeroDivisionError after 8 claims (`as_written_results.json`): its
loop `for k, … in enumerate(o.yard_dims)` reuses `k`, the feet-to-model scale, so the next conversion divides by
zero. That is a test-script error. With only that loop variable renamed (`dimensions_k_fixed.py`):
**15 of 16** (`all_claims_results.json`).

| Claim | Result |
|---|---|
| One dimension per yard; each with its dashed required line; no two share a start; the failing one red; a complying one neutral grey; the required line 10'-0" from its lot line; each square to its lot-line piece (within 0.1°) | pass |
| Front: only the height's dimension, vertical from the grade plane, the row's figure, beside the house, its colour | pass |
| Labels off: the failing yard's words stay; zoomed out: no dimension | pass |
| **1 every label shown sits on screen clear of the status box, the house and the other labels** | **fails**: three of the four yard labels are off screen, wholly or partly (front yard y 794–1,026 px, rear yard y -382 to -164 px, southwest x from -192 px) |

## What an architect sees

**Top, labels on** (`1_top_labels_on.png`):
- The northeast side yard (complies) reads well: grey, upright, on its own line. It does run past the right lot
  line, over the curve.
- **The failing southwest side yard's label runs off the left edge of the view.** Only "…5/8", needs 10'-0"
  (approx." shows. Its red line and text sit beside the red strip.
- **The front and rear yards' labels can't be seen at all.** They are placed past the ends of their lines, below and
  above the view.
- The "min 25'-0"" and "min 10'-0"" tags and the dashed required lines are drawn, but very faint and small, hard to
  read. The top "min 25'-0"" sits partly under the edge label "69'-6 1/8"".

**Top, labels off** (`4_top_labels_off.png`): the one label that stays, the failing yard's, is still cut off at the
left edge, so the most important words can't be read.

**Front** (`2_front.png`): the height dimension is vertical, grey (it complies) and beside the house. But **its
label "✓ Building height 35'-0"" sits inside the building**, over the house, not along its line.
