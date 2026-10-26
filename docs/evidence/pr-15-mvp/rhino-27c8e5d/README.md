# The notice and the highlight (#15 rhino-ui) at 27c8e5d: checked in Rhino 8 (Mac), 2026-10-25

**Purpose:** `notice_in_rhino.py` (claims 1, 1b, 2, 3, 4), `highlight_in_rhino.py` claim 1b, the notice by eye.\
**For:** the coordinator, the #15 job, reviewers.\
**Kept current by:** never changed (a dated record).

## notice_in_rhino.py (`notice/`): 3 of 5

| Claim | Result |
|---|---|
| 1 moved 5 ft left and checked: the notice says the side yard no longer complies, compact and clear of the model | pass |
| 1b zoomed in tight: compact and over none of the model, or not drawn (the panel says it) | pass: not drawn, the panel says it (`1b_zoomed_in.png`) |
| 2 moved back and checked: no notice left of the earlier model | pass (`2_back_no_notice.png`) |
| 3 the model changed since the check: the notice isn't drawn over it | **fails, the script's set-up**: it needs the notice drawn just before the edit, but step 3 starts after `ZoomExtents()`, where the lot fills the Top view (model on screen y 30–637 of 668 px), so no corner is clear and, by the notice's own rule, it isn't drawn. After the edit it isn't drawn either (`3_changed_no_notice.png`), which is what the claim is about. |
| 4 another document in front: no notice left | **fails, the script's set-up**: it needs a notice still held after step 3, but step 3's edit already ended it (a changed model ends the notice). |

## highlight_in_rhino.py (`highlight/`): 17 of 19

- **Claim 1b (labels off): pass.** The notice is top left (342 × 76 px), clear of the model.
- **Claim 1b (labels on): fails, but the screen disagrees with the claim.** The claim works out the notice's place
  with only the status box taken and gets "no corner clear". In the capture with labels on
  (`2_labels_on_off_every_line.png`) the notice is drawn bottom right, just below the front lot line, clear of the
  model and the status box. The claim's own calculation should be checked against what the drawing uses.
- **Claim 2 (no label crosses a line or another label): fails**: the southwest side yard's label is recorded as
  crossing 13 lines.
- Every other claim passes: red and amber where they belong, their colours, the notice's and the panel's
  "at least 0'-11 1/4" short", the label positions, the dark background.

## The notice, to an architect's eye

- **Compact and readable:** two short lines, red ✕ and the yard's name, then the required and the shortfall.
- **Never over the model:** top left with labels off (`4_red_amber_top.png`), bottom right with labels on; not drawn
  when zoomed in tight, where the panel says it instead.
- **Gone when it no longer applies:** after moving back and checking, and after an edit with no check.
