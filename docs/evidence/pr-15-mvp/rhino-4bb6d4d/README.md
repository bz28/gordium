# PR #15 checked in Rhino at 4bb6d4d: label placement, and how long a redraw takes

**Purpose:** what `highlight_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 (claim 2's hard rules and its independent distance search), where the failing side yard's label sits, and what the placement search costs per frame.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

`highlight_in_rhino.py`, every claim recorded (`highlight_results.json`), in the real docked Top view
(656 × 668 px): **18 of 19**.

| Claim 2 part | Result |
|---|---|
| every label keeps every hard rule (on screen; off every building and coloured part, the notice, the status box, the north arrow, its own line and every other yard's dimension) | pass |
| a label within one label height of its line whenever a spot there keeps every hard rule (an independent 4 px search), and led to its line when further than 8 px | pass |
| **no label covers another** | **fails**: the front yard's and the southwest side yard's labels cover each other |

## The southwest label, to an architect's eye

- **Labels off** (`4_red_amber_top.png`): one line, "✕ Side yard, Southwest 7'-0 5/8", needs 10'-0" (approx.)", just
  below the house's front-left corner, at the end of its red line. Off the house and its colouring, readable, plainly
  that yard's.
- **Labels on** (`2_labels_on_off_every_line.png`): the same place, but **the front yard's label can't be seen at
  all**: it is underneath the southwest label. An architect loses the front yard's figure. The southwest label also
  starts right beside the front yard's dimension line, about a pixel off it.

## How long a redraw takes (`redraw_timing.json`, `redraw_timing_probe.py`)

The sample with the side yard failing; 40 frames each, every frame drawn in full there and then (a capture at the
view's size, the same for both columns), Top zoomed in and out step by step, Perspective orbited:

| | labels off | labels on |
|---|---|---|
| Top, zooming: median / mean / worst per frame | 30 / 47 / 142 ms | **502 / 681 / 1,605 ms** |
| Perspective, orbiting: median / worst | 10 / 15 ms | 9 / 14 ms |

With labels on, zooming in Top runs at about two frames a second: lag an architect will feel. The placement search
adds about 470 ms per frame for this sample's handful of labels. Orbiting the perspective is unaffected (no plan
labels are placed there).
