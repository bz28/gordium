# #15 rhino-ui at 7a16aa6: pass 2 and the one-click street side, in Rhino 8 (Mac), 2026-10-25 (RHINO_QUEUE 13)

**Purpose:** the corner step's claims 10 and 12, the by-hand equivalent of one click on one Ithaca Rd piece, and
the full pass 2 at this head.\
**For:** the coordinator, the #15 job, reviewers.\
**Kept current by:** never changed (a dated record).

## The corner step (claims 10 and 12): all pass, once the script clicks the side street

As written, the corner step's second click is the lot outline's middle segment. On 106's outline that is another
Ithaca Rd piece, not the side street: Gordium said "that lot line is on a street already kept". So the third part
of claim 10 failed on the script's click (`corner.json` from that run is replaced by the corrected run below; the
first run's detail is in the coordinator report). With the second click on the lot line that joins Ithaca Rd's east
end (`pass2_corner_fixed.py`, otherwise the same script):

| Claim | Result |
|---|---|
| 10 a corner lot's street side takes every street clicked, Enter when done | pass |
| 10 one click on one piece keeps the whole street, and says so: "Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage" | pass |
| 10 the other street is its own 2 pieces, "Street 2: 2 lot-line pieces, 91'-10 3/8" of frontage", no question asked | pass |
| 12 answering No in the box drops both streets' lines | pass |

## The by-hand equivalent (`one_click/`): pass

Corner lot? Yes, Change…, ONE click on one Ithaca Rd piece (the 4th), Enter. All 8 Ithaca Rd pieces are kept, with
"Ithaca Rd: 8 lot-line pieces, 75'-10" of frontage". In Top (`top_whole_ithaca_rd_highlighted.png`) the blue street
highlight runs the whole bottom edge, Ithaca Rd, and none of the side lot lines (the green on the sides is the lot
outline's own highlight).

## The full pass 2 at this head: 25 of 26

Every step passes except one claim in the "button" step: **"2 the button is on screen without scrolling"**. The
detail area under the rows is 51 px tall (top 623); the "Enter bedrooms and parking spaces…" button (top 655,
20 px) ends 1 px below it. In the panel as docked (`2_button_step_panel_docked.jpg`) the button shows in full at the
bottom of the detail area. It is a 1 px overflow, but the detail area has become very short (51 px), which is worth
a look. The driver stopped after that step, so the remaining steps ran on from the same document: grey, then the
corner step (corrected as above), labels, scale, close (exactly one checker, none left) and the empty file's box
(claim 6) all pass.
