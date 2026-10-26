# Depth-tested lines (PR #31) at c174a2d: checked in Rhino 8 (Mac), 2026-10-26

**Purpose:** `depth_in_rhino.py`: lines on top in plan, hidden behind the house in a shaded perspective, the
height's dimension seen through the see-through envelope in Front.\
**For:** the coordinator, the #31 job, reviewers.\
**Kept current by:** never changed (a dated record).

Run as written (captures at the view's own size, every claim recorded): **9 of 9** (`depth_results.json`).

| Claim | Result |
|---|---|
| Top: the lines go on top; the yard dimensions drawn on screen | pass (`1_top.png`) |
| Perspective (Shaded, from the street): no line on top; the yard dimensions drawn in the model | pass |
| Where the house hides the rear yard's dimension, none of it shows; where nothing hides it, it shows (pixels) | pass |
| Front (Shaded): the height's dimension depth-tested; the see-through envelope never hides it | pass (`4_front_shaded.png`) |

To an architect's eye:
- **Top:** the northeast "27'-4 1/4"" and the front "27'-0 3/4"" numbers sit on their own lines.
  - The rear yard's line runs up through the edge label "69'-6 1/8"" and under the status box.
  - The left side yard's dimension shows no number, and the edge label "101'-1 1/2"" sits over its line.
- **Perspective** (`2_perspective_shaded.png`): nothing shows through the house, as it should. But the camera is so
  close that the house fills the frame, so the picture shows little on its own; the pixel claims are the evidence.
- **Front:** the "35'-0"" height dimension reads clearly through the see-through envelope. The whole house is
  coloured amber here (the height needs review on this lot). This branch doesn't carry #28's "only the offending
  part" colouring.
