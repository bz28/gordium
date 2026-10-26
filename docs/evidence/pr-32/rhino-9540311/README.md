# PR #32 checked in Rhino at 9540311: the wait window and the keyboard

**Purpose:** what `progress_cancel_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, with the Mac's screen locked throughout.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Run | Result |
|---|---|
| As written | 2 of 3, then it stops at the new claim 1 |
| Copy that records every claim (`progress_cancel_results.json`) | **28 of 29**; everything but the new claim 1 passes |

**New claim 1 fails:** "the wait window has the keyboard once shown, and then says 'Esc or Cancel to stop'". In
all 10 samples the window did not have the keyboard (`focus` false), and its hint read **"Click Cancel to stop"**.
That is the right fallback for a window without the keyboard (`wait_window.png`).

**This can't be judged with the screen locked.** Both runs were made with the screen locked (`locked.swift`:
locked 1). A locked Mac has no active app, so `makeKeyAndOrderFront` may not be able to make any window key; it was
the same with `BringToFront` and `Focus` at 65c07d7. The claim needs a run with the screen unlocked, and so do the
Esc checks left for a human at 65c07d7.

## By eye

The wait window reads "Finding the largest building that complies… / ○●○ 1 s / [Cancel] Click Cancel to stop".
The hint matches what the window can do: without the keyboard, it never offers Esc.
