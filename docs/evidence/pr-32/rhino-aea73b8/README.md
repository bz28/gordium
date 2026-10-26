# PR #32 checked in Rhino at aea73b8: live progress and Cancel

**Purpose:** what `progress_cancel_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, and how the wait window looks to an architect.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

Run as written, outside a command, with the slow checker (`tests/slow_checker.py`) and a 10-minute cap.
`progress_cancel_results.json` holds 16 claims recorded: **15 pass, 1 fails, and claims 5–7 never ran.**

| Claim | Result |
|---|---|
| 0, 1: the sample checked; Rhino keeps running while the check waits; the wait says the checker's own steps; the panel says Checking… with the live line; the slow check finishes | pass |
| 2: Cancel returns within 2.5 s with nothing shown as checked; the model and the file as they were; the next check works | pass |
| 3: Zoning report… cancelled: the report file as it was, no half-written copy; Gordium says so | pass |
| 4: Cancel during GordiumStart's Draw: nothing drawn; the model and the file's strings as when the box was shown; "Draw cancelled" | pass |
| **4: Draw again (nothing cancelled) draws the starting house** | **fails** (`{"drawn": 1}`) |
| 5, 6 (live mode), 7 (the start box's lookup cancelled) | **not reached** |

**After that failure the run did not finish.** Rhino's command line said "progress_cancel_in_rhino FAILED: see …
/out.json", but `"done": true` was never written, and a Gordium wait window stayed open: "Slow test: waiting… /
○●○ 0 s / Cancel", its seconds not moving (`timeout_wait_window_left_open.png`). So the "Draw again" ran on with
the slow checker. My 10-minute cap captured the windows and pressed Esc, which closed the wait window. I then
closed the test document the script had left open.

## The wait window, to an architect's eye

Captured from outside during the run (`wait_window_*.png`): "Checking the rules…" or "Slow test: waiting…" in bold,
a three-dot mark, the seconds (0 s, 1 s, 3 s…), and Cancel. It's readable, and nothing is shown as pass or fail
while it checks. In every capture (at 7, 9, 11, 15 and 19 s, two of them byte for byte the same) the mark sat on
the middle dot. Either the mark doesn't move, or my 2-second captures fell on the same point of its cycle; I can't
tell which from these.
