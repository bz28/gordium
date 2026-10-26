# #15 rhino-ui at a9a9a45: highlight, notice and pass 2, in Rhino 8 (Mac), 2026-10-26

**Purpose:** the three checks at this head, and two things by eye: the list's first heading whole at the top when
the panel opens, and the list keeping its scroll on live re-checks.\
**For:** the coordinator, the #15 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `highlight_in_rhino.py` as written (it now draws each frame before reading it) | **19 of 19** |
| `notice_in_rhino.py` as written | **3 of 5**: 1 and 3 fail; 1b, 2 and 4 pass |
| `pass2_in_rhino.py` as written (the corner step's second click fixed in the script) | **26 of 26** |

## The notice: not drawn in the real Top view at the default framing

Claim 1 fails: the frame was drawn whole, but the notice wasn't. The live Top viewport is 657 × 668 px (the docked
panel takes the rest of the window), the model on screen x 156–501, y 106–562. The plugin found no place for the
notice: the only other box taken is (543, 119, 61 × 55), small, probably the north arrow. So the limit is the
notice's width (`notice_with_taken_results.json`, from a copy recording `taken`: `notice_taken.py`). At 6361a3f the
notice was drawn in this same view; at this head it isn't, and only the panel says it. Claim 3 fails for the same
reason (it needs the notice drawn before its edit).

**The script's own screenshot misleads:** `capture()` renders the view at 1000 × 640, where the notice fits top left
(`1_framed.png`). The view on screen is 657 px wide, and there it isn't drawn. Captures should use the viewport's
own size.

## By eye

- **The first heading when the panel opens** (`pass2/side_yard.jpg`): "Does not comply · 1" is whole at the top of
  the list, its row selected, the detail below.
- **The list keeping its scroll on re-checks** (`pass2/button_step_panel_list.png`): in the button step, after the
  Parking row was selected and the model checked again, the list is still scrolled to keep that row in view, so the
  "Does not comply · 1" heading is half hidden. That's consistent with the list keeping the architect's scroll; the
  scroll offset itself isn't readable through Rhino's API on the Mac, so this is by eye only.
