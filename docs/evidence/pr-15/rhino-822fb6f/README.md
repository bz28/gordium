# PR #15 checked in Rhino at 822fb6f: labels, notice and label timing

**Purpose:** what `highlight_in_rhino.py`, `notice_in_rhino.py` and the redraw-timing probe showed in Rhino 8 (Mac) on 2026-10-26, docked Top 657 × 668 px, the sample house moved 5 ft so its southwest side yard fails.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Checks

| Script | Result |
|---|---|
| `highlight_in_rhino.py` (`highlight_results.json`) | **19 of 19** with one test-script fix (below); as written it stops with an error |
| `notice_in_rhino.py` (`notice_results.json`) | **5 of 5** |

**Test-script bug (in the script, not the plugin):** line 214 reads `b_[8] < order`. Each label record has 8 fields
(indexes 0 to 7), with `order` the last, so `b_[8]` raises IndexError and the run stops after 12 claims. The run
here used a copy with `b_[7]`. Nothing else changed.

Claim 2 passes in full, "no label covers another (a placed label is HARD for the later ones)" included.

## To an architect's eye

- **`2_labels_on_off_every_line.png`:** every label is next to its own line. None covers another, the house or the
  coloured band. The notice sits below the lot, clear of the drawing, and the status box sits at the top.
  - Small point: the front yard's dimension line runs along the left edge of the "? Front yard" label, without crossing its text.
- **`1b_zoomed_in.png`** (notice): zoomed in tight, the notice is not drawn (the panel says so) and nothing covers the model.

## Label timing (`redraw_timing.json`, probe `redraw_timing_probe.py`)

`g.settle_labels()` is called once after each `set_labels(True)`, then 40 frames are drawn while moving the view:

| per frame: median / mean / worst | labels off | labels on |
|---|---|---|
| Top, zooming | 8.4 / 9.4 / 20 ms | **8.5 / 9.8 / 34 ms** |
| Perspective, orbiting | 8.6 / 9.5 / 15 ms | 8.7 / 9.2 / 12 ms |

The work for the labels inside the drawing is now about 0 ms a frame, meeting the 16 ms target.

**When the view stops** (8 stops while zooming Top: draw one frame, then call `settle_labels(LABEL_STEP_S)`, as
the timer does, until placed):

- `LABEL_STEP_S` is 12 ms, but each tick places at least one label, and one label takes **up to 309 ms**.
- Slowest tick at each stop: 208, 129, 257, **309**, 261, 130, 209, 44 ms. Rhino can't respond during a tick.
- 7 to 9 ticks per stop, taking **0.2 to 1.3 s** in total. The labels are placed that long after the 0.15 s stillness wait.

**By eye** (`timing_stop_before_settle.png` against `timing_stop_after_settle.png`, the same stop): the labels
visibly jump when the view stops.

- Until placed, the frame shows the previous placements.
  - The northeast label sits about 40 px right of its final place.
  - The southwest label is on two lines.
  - The rear label is under the status box.
  - The front yard label and three edge lengths are missing.
- Once placed, the northeast label shifts left, the southwest label reflows to one line, and five labels pop in.
