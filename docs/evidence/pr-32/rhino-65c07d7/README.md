# PR #32 checked in Rhino at 65c07d7: progress, Cancel and the new-address Draw

**Purpose:** what `progress_cancel_in_rhino.py` (as written) showed in Rhino 8 (Mac) on 2026-10-26, the wait window by eye, and the Esc checks that could not be made.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result: 28 of 28 as written (`progress_cancel_results.json`)

- **New 2b passes:** an edit during a check drops its answer, and nothing is shown as checked.
- **4 passes:** Cancel during Draw takes the sample back, and Draw again draws the starting house.
- **The window updates pass:** all three marks, the seconds counting up, and the checker's own steps.
- **New step 8 passes:** the new address's Draw used the house worked out before its undo step opened. It drew 3
  floors at 0–11.67, 11.67–23.33 and 23.33–35 ft, the same as the plan.
- The script now stands in for Rhino's Idle itself, and closes its own document (both fixed since 6ba061b).

**Claim 5 is timing-dependent.** At 2781a5d it failed twice: the script's timer had ticked 4 times, against the 5
the claim wants, when the panel's line had already moved (two different marks). At 65c07d7 it passed. The wait ends
as soon as the panel shows two lines, so the tick count depends on timing.

## By eye

`wait_window.png`: "Slow test: waiting…", a moving mark with seconds, then Cancel and **"Esc or Cancel to stop"** beside it.

## Esc: left for a human (the Mac's screen was locked)

The two Esc checks could not be made. Rhino was the front app, but **the screen was locked**, and key presses sent
while it is locked don't reach any app. With Esc sent once, 2 s into a 12 s slow check, both runs finished
uncancelled (about 13 s): once with the document's window brought to the front from inside Rhino, and once with the
wait window brought to the front. Since the key never arrived, this says nothing either way. Also, Eto reported
`HasFocus` false for the wait window after `BringToFront()` and `Focus()`.

To check by hand, with the screen unlocked, during a slow check:

1. Click in a viewport and press Esc: the check should keep going.
2. Click the wait window and press Esc: the check should stop, saying "Check cancelled".

The probe for a second try is `esc_probe.py` and `esc_drive.py` (it presses Esc once from outside, after bringing a
window to the front from inside Rhino).
