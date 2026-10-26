# #15 rhino-ui at 0a94fc4: the notice and the highlight, in Rhino 8 (Mac), 2026-10-26

**Purpose:** the notice check (claims 1 and 3 failed at a9a9a45) and the highlight check (screenshots now at the
view's own size), and the notice to an architect's eye in the real docked Top view.\
**For:** the coordinator, the #15 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `notice_in_rhino.py` as written | **5 of 5** |
| `highlight_in_rhino.py`, every claim recorded | **19 of 19** |

The real Top viewport is 656 × 668 px (the docked panel takes the rest). At step 1 the notice is drawn top left,
342 × 76 px from y 34 to 110; the model starts at y 110.

## To an architect's eye (`highlight/4_red_amber_top.png` labels off, `2_labels_on_off_every_line.png` labels on)

- **The notice:** labels off, top left in three short lines: "✕ Side yard, Southwest no longer complies" /
  "7'-0 5/8" proposed · 10'-0" required" / "at least 0'-11 1/4" short". Labels on, bottom right in two lines. No
  measurement is split across lines; it's readable and clear of the north arrow. Labels off, its bottom edge just
  meets the lot's top-left corner; labels on, it's clear of the model.
- **New: the failing southwest side yard's label is far from its line, with no visible leader.**
  - With labels on, it sits top left, directly under the status box, about 330 px from its red dimension line at the
    bottom left.
  - With labels off, it sits below the lot, about 130 px under its line.
  - In neither can a leader to the line be seen, so nothing on screen ties the label to its yard. At 6361a3f it sat
    right at the outer end of its line.
- Other labels (labels on): each beside its own line, readable.
