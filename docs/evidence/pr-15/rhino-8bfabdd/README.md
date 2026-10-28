# PR #15 checked in Rhino at 8bfabdd: labels while moving and at rest

**Purpose:** what `highlight_in_rhino.py`, `notice_in_rhino.py` and the new `redraw_timing_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, docked Top 657 × 668 px, the sample house moved 5 ft so its southwest side yard fails.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Script | Result |
|---|---|
| `highlight_in_rhino.py` as written | **19 of 19** |
| `notice_in_rhino.py` as written | **5 of 5** |
| `redraw_timing_in_rhino.py`, every claim recorded (`redraw_timing_results.json`) | **4 of 5** |

`redraw_timing_in_rhino.py`, claim by claim:

- **1. Label work while moving: passes.** Labels on add 0.5 ms a frame. Top zoom median 10.9 ms on against 10.4 off;
  Perspective orbit 10.8 against 10.6.
- **2 and 2b. Labels drawn while moving: pass.** 87 labels were checked: none breaks a HARD rule, and none is plainly
  wrong (off the view edge, the axis icon, the boxes and the other labels).
- **3. One pass of at most 80 ms at each stop: fails at 2 of 8 stops.** Every stop is placed in ONE pass, but placing
  took 22.2, 72.1, **87.5**, 74.8, **80.7**, 67.6, 21.0 and 9.0 ms (all 9 labels each time). The pass with its
  redraw took about the same. The view must be still for 0.08 s first.
- **4. The frame after the pass is settled: passes.** Every label is drawn where it was placed and keeps every HARD rule.

## By eye: no jump, but the labels pop in (`stop_before_pass.png`, `stop_after_pass.png`)

- **Nothing is misplaced while moving.** In the frame just before the pass, no labels are drawn at all.
- **No label jumps when the view stops.** After the pass, all nine appear at once, each in its final place. Nothing
  slides or reflows as at 5b46c99; they simply appear, about 0.08 s plus 9 to 88 ms after the view stops.

## The world-axis icon (`axis_icon_zoom.png`, the bottom-left corner of `stop_after_pass.png` at 4×)

Measured on this Mac, in the 657 × 668 view:

| | Real icon (axes and letters) | Plugin's square (`AXIS_ICON_PX = 72`) |
|---|---|---|
| left to right | x 34 to 76 | x 0 to 72 |
| top to bottom | y 593 to 634 | y 596 to 668 |
| corner to keep clear, from the bottom left | **about 76 × 75 px** | 72 × 72 px |

- The 72 px square doesn't cover the icon: the "x" letter reaches about 4 px past its right edge, and the "y" letter
  about 3 px above its top.
- As placed, the "✕ Side yard, Southwest" label starts at x = 76, about 1 px from the "x" letter.
- The axes themselves are about 42 px long, drawn about 34 px in from the left and bottom edges.
