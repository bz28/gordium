# PR #15 checked in Rhino at 319dc5d: the highlight, and the southwest label against the front yard's dimension

**Purpose:** what `highlight_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26 (claim 2 now also fails a label covering another yard's dimension line), and where the failing side yard's label sits.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

`highlight_in_rhino.py`, every claim recorded (`highlight_results.json`): **19 of 19**, in the real docked Top
viewport (656 × 668 px).

## The southwest label, by eye

With labels on (`2_labels_on_off_every_line.png`) and off (`4_red_amber_top.png`):
- **Clear of the front yard's dimension.** "✕ Side yard, Southwest / 7'-0 5/8", needs 10'-0" (approx.)" sits just
  above its red dimension line; the front yard's dimension starts below the house, under the label, and the label
  no longer covers it (at 81efd62 it covered the line's top).
- **It now sits on the house.** The label covers the house's lower-left corner: part of the amber band (the part
  that is wrong) and the floor plan's lines. An architect reads it as written on the building. Beside its line
  outside the house, or on a short leader, would keep the house and its colouring clear.
