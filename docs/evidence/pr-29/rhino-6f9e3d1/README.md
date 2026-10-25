# Drawing-style dimensions (PR #29) at 6f9e3d1: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** the re-run after the ca08449 findings, and what the plan shows to an architect's eye.\
**For:** the coordinator, the #29 job, reviewers.\
**Kept current by:** never changed (a dated record).

`dimensions_in_rhino.py` at this head (it records every claim): **14 of 14** (`dimensions_results.json`). That
includes the new claims: no two yard dimensions start at the same point; each is square to the lot-line piece it
ends on (0.0° for all four); every yard has its faint required line.

## Better than at ca08449

- The four dimensions start at four different points: no two share a corner.
- The failing southwest side yard's red dimension shows at the lot line, beside its label (`1_top_labels_on.png`).
- With labels off, only the failing yard's words stay, and the notice moves to the top (`4_top_labels_off.png`).
- Front: the height dimension reads well (`2_front.png`). Zoomed out: none (`3_top_zoomed_out.png`).

## Still wrong to an architect's eye (`1_top_labels_on.png`)

1. **The front yard's label can't be seen.** Its dimension is drawn and recorded ("? Front yard 26'-11 3/4"
   (approx.)"), but the dimension runs down under the "no longer complies" notice bar at the bottom of the view, and
   the label isn't visible anywhere in the frame.
2. **The rear yard's dimension runs under the status box.** It goes straight up from the house's back corner
   (x ≈ 43 ft) through the edge label "69'-6 1/8"" and on under the status box at the top.
3. **The northeast side yard's label is far from its dimension.** The dimension runs from the house's back right
   corner to the right lot line, but its label "✓ Side yard, Northeast 32'-4 1/4"" sits inside the house near the top
   left. It reads as if it labels the house's back wall.
4. **A complying yard isn't green.** The northeast dimension is drawn near-black (ARGB -14407636, about RGB 36, 42,
   44). The PR says green for complies. The needs-review yards are a dark amber (RGB about 138, 88, 0) and the failing
   yard is red.
5. **The faint required lines are hard to see** at this zoom. The claim confirms they are drawn; on screen they barely
   register against the yard colours.
