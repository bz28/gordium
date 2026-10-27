# PR #15 checked in Rhino at 5b46c99: labels, notice and label timing

**Purpose:** what `highlight_in_rhino.py`, `notice_in_rhino.py` (both as written) and the redraw-timing probe showed in Rhino 8 (Mac) on 2026-10-26, docked Top 657 × 668 px, the sample house moved 5 ft so its southwest side yard fails.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Checks, as written

| Script | Result |
|---|---|
| `highlight_in_rhino.py` (`highlight_results.json`) | **19 of 19**; the `b_[8]` bug from 822fb6f is fixed |
| `notice_in_rhino.py` (`notice_results.json`) | **5 of 5** |

## Label timing (`redraw_timing.json`, probe `redraw_timing_probe.py`)

After `set_labels(True)`, one frame is drawn, then `g.settle_labels()` places every label once: **11.1 ms**
(framed view). Then 40 frames while moving the view:

| per frame: median / mean / worst | labels off | labels on |
|---|---|---|
| Top, zooming | 9.7 / 12.3 / 69 ms | **10.7 / 11.8 / 25 ms** |
| Perspective, orbiting | 9.8 / 10.5 / 16 ms | 10.1 / 10.9 / 17 ms |

**When the view stops:** at 8 stops while zooming Top (×1.25 four times, then ×0.8 four times), one frame is drawn,
then `settle_labels(LABEL_STEP_S)` is called, as the timer does, until the labels are placed. `LABEL_STEP_S` is now
16 ms.

| Stop | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| ticks | 2 | 2 | 5 | 6 | 5 | 2 | 2 | 1 |
| slowest tick, ms | 21.7 | 18.1 | 15.6 | 14.5 | 15.6 | 19.2 | **22.3** | 9.2 |
| whole settle, ms | 21.9 | 36.1 | 66.8 | **71.4** | 66.5 | 36.7 | 22.7 | 9.1 |

Against the targets:

- **Slowest tick ≤ 16 ms: not met.** The worst is 22.3 ms, and 4 of 8 stops go over: a single label's placement can pass the
  16 ms budget.
- **One tick: met at 1 of 8 stops.** 2 to 6 ticks otherwise; zoomed in the most, 5 to 6.
- **Whole settle ≤ 30 ms: met at 3 of 8 stops.** Otherwise 36 to 71 ms.
- Against 822fb6f (ticks up to 309 ms, settles 0.2 to 1.3 s), it is 14 to 18 times faster.

## By eye: a visible jump when the view stops (`timing_stop_before_settle.png`, `timing_stop_after_settle.png`)

Still there, the same as at 822fb6f, but about 0.22 s after the view stops (the 0.15 s stillness wait, plus 67 ms of
ticks at this stop) instead of up to 1.4 s.

- Until the labels are placed, the frame shows the previous placements.
  - The northeast label sits about 40 px right of its final place.
  - The southwest label is on two lines.
  - The rear label is under the status box.
  - The front yard label and three edge lengths are missing.
- Then the northeast label shifts left, the southwest label reflows onto one line, and five labels pop in.
