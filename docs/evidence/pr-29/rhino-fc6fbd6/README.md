# PR #29 checked in Rhino at fc6fbd6: numbers clear of the notice, and redraw time

**Purpose:** what `dimensions_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 in the docked Top view (656 × 668 px), the sample with the failing side yard, and how long a frame takes with labels on.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

`dimensions_in_rhino.py` as written (`dimensions_results.json`): **24 of 25**.

| Claim | Result |
|---|---|
| the notice covers no number (new) | pass |
| no lot edge's length touches a number (new) | pass |
| every number shown sits clear of the status box, the house and the other numbers | **fails**: the failing southwest side yard's "✕ 7'-0 5/8"" sits on the house's red and amber band |
| the rest (one per yard, required lines, colours, square, inside the view, Front, labels off, zoomed out) | pass |

## To an architect's eye (`1_top_labels_on.png`)

- **The notice is now drawn across the model.** "✕ Side yard, Southwest no longer complies · …" runs straight across
  the middle of the plan, over the house and its red and amber band. The notice must never cover the model (the
  #15 rule); it no longer covers a number, but it now covers the drawing.
- The failing southwest number "✕ 7'-0 5/8"" is drawn, red, bottom left, on the house's coloured band.
- The front yard's "? 26'-11 3/4"" is vertical at the bottom left, clear of the notice now.
- The rear "? 27'-6 7/8"" is vertical, clear of the status box; the edge label "69'-6 1/8"" is clear of it now.

## Redraw time (`redraw_timing.json`, the probe from #15's 4bb6d4d record)

40 frames each, every frame drawn in full there and then:

| | labels off | labels on |
|---|---|---|
| Top, zooming: median / mean / worst per frame | 11 / 12 / 20 ms | 15 / 16 / 29 ms |
| Perspective, orbiting: median / worst | 10 / 14 ms | 12 / 28 ms |

No visible lag: the numbers add about 4 ms a frame.
