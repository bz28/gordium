# Drawing-style dimensions (PR #29) at ca08449: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** what `dimensions_in_rhino.py` showed, and what the screenshots show to an architect's eye.\
**For:** the coordinator, the #29 job, reviewers.\
**Kept current by:** never changed (a dated record).

Run in a copy that records every claim without stopping (`all_claims_results.json`): **10 of 13**.

| Claim | Result |
|---|---|
| the left side yard does not comply | pass |
| 1 Top: one dimension per measured yard | **fails, the test's own count**: 4 drawn, 4 dimensions, but "yards: 0" (it counts items by a `measure` key the check's items don't carry) |
| 1 each yard dimension has its faint required line | **fails**: 3 required lines for 4 dimensions |
| 1 the failing side yard's dimension is red | pass |
| 1 the side yard's required line is 10'-0" from its lot line | pass (10.0 ft) |
| 1 each yard's dimension is square to its lot line (within 2°) | **fails**: the front yard's is 3.9° off (the sample's street side is 8 short tax-map pieces); the other three 0.0° |
| 2 Front: only the height's dimension; vertical from the grade plane; the height row's figure; beside the house; its colour | pass (5 claims) |
| 3 zoomed out to the neighbourhood: no dimension | pass |
| 4 labels off: the failing yard's words stay, a complying yard's go | pass |

## What the screenshots show (an architect's eye)

- **Front** (`2_front.png`): reads well. One vertical dimension beside the house, ticked at both ends, "✓ Building
  height 35'-0"".
- **Labels off** (`4_top_labels_off.png`) and **zoomed out** (`3_top_zoomed_out.png`): as described.
- **Top with labels on** (`1_top_labels_on.png`) is hard to read:
  - Every dimension starts at the building's nearest point, which on this house is a corner, so two dimensions
    share each corner. The recorded ends: the rear and northeast side yards both start at (43.8, 65.2); the front
    and southwest side yards both start at the southwest corner (7.9–10.7, 27.8). Their labels pile up at those
    corners: "Rear yard" and "Side yard, Northeast" butt against each other at the top, under the status box.
  - The failing southwest side yard's dimension line runs inside the red and amber highlight strips (the highlight
    reaches the lot line), so its line and ticks can't be told apart. The one dimension that matters most is the
    hardest to see.
  - The "no longer complies" notice bar covers the bottom of the plan, and the southwest label overlaps it. The
    status box covers the top of the house.
  - Suggestion (for #29 to decide): place a dimension along the middle of the wall's run nearest the lot line
    rather than at a corner, offset labels from each other, and draw the dimension above the highlight.
