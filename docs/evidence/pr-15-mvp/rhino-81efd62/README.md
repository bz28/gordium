# PR #15 checked in Rhino at 81efd62: the highlight and the notice

**Purpose:** what `highlight_in_rhino.py` and `notice_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, and how the failing side yard's label looks.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

Claim 2 of the highlight check: each label within one label height of its line, a leader when farther than
12 px, never on the notice, the status box, the north arrow or its own line.

| Run | Result |
|---|---|
| `highlight_in_rhino.py`, every claim recorded (`highlight_results.json`) | **19 of 19** |
| `notice_in_rhino.py` as written (`notice_results.json`) | **5 of 5** |

Both ran in the real docked Top viewport (656 × 668 px), each frame drawn before it was read.

## The failing southwest side yard's label

With labels on (`2_labels_on_off_every_line.png`) and off (`4_red_amber_top.png`), "✕ Side yard, Southwest /
7'-0 5/8", needs 10'-0" (approx.)" sits right beside its red dimension line, within a label's height, so it is
plainly that yard's. It is readable in both.

One thing to look at: the label's box starts at the house's bottom edge and covers the lot just below the house's
front-left corner, including the top of the front yard's dimension line. The claim counts lines crossed only for
labels set beside their line.

The notice: two compact lines bottom right with labels on, three top left with labels off; no figure split across
lines; clear of the model and the north arrow.
