# #15 rhino-ui at 6361a3f: pass 2, the notice and the highlight, in Rhino 8 (Mac), 2026-10-25

**Purpose:** pass 2 in full, the notice and highlight checks, and an architect's look at the label, notice and panel.\
**For:** the coordinator, the #15 job, reviewers.\
**Kept current by:** never changed (a dated record).

| Run | Result |
|---|---|
| `pass2_in_rhino.py` in full, its corner step's second click on the side street (`pass2/pass2_corner_fixed.py`; this head still clicks the outline's middle segment, another Ithaca Rd piece) | **26 of 26** |
| `notice_in_rhino.py` as written (`notice/notice_as_written_results.json`) | 1 of 5: every "what the view drew" record is empty |
| `notice_in_rhino.py`, the frame drawn before it is read (`notice/notice_sync_draw.py`) | **5 of 5** |
| `highlight_in_rhino.py`, the frames drawn before they are read (`highlight/highlight_sync_draw.py`) | **19 of 19** (as written it read empty records and then stopped on them) |

**Why the scripts as written read nothing:** they clear the view's draw record, call `view.Redraw()` and read the
record straight back. On the Mac, `Redraw()` only schedules the frame, so the record is still empty when read.
Adding `view.CaptureToBitmap(...)` right after `Redraw()` draws the frame there and then, with Gordium's drawing
included, and every claim passes. This is a test-script change only; the scripts should do the same.

## To an architect's eye

- **The southwest label** (`highlight/2_labels_on_off_every_line.png`, `4_red_amber_top.png`) sits outside the
  drawing, left of the left lot line, in red: "✕ Side yard, Southwest / 7'-0 5/8", needs 10'-0" (approx.)". It sits
  right at the outer end of its red dimension line, so the tie is obvious; a leader, if drawn, is too short to see as
  a line of its own. It's readable and clear of the lot.
- **The notice:** two compact, readable lines, clear of the model. With labels on it sits bottom right, below the
  front lot line; with labels off, top left.
- **The panel** (`pass2/button.jpg`): the detail area is now 160 px tall (51 px at 7a16aa6). The reason, the "Enter
  bedrooms and parking spaces…" button and the code's citations show, and the rest scrolls. The rows list above is
  shorter for it: the "Does not comply · 1" heading was half hidden under the column headings (the list scrolled a
  little).
