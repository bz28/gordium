# PR #28 checked in Rhino at 5ebb288: pass 2 after the merge

**Purpose:** what `pass2_in_rhino.py` showed in Rhino 8 (Mac) on 2026-10-26, step by step, with an architect's eye on each capture.\
**For:** reviewers, engineers.\
**Kept current by:** never changed (a dated record).

## Result

| Run | Result |
|---|---|
| As written | Steps open to labels pass. **scale fails**: zoomed to the lot, no label is recorded at all (`labels: []`) |
| Copy with the scale step corrected (`pass2_settle_in_rhino.py`) | **29 of 30** (`pass2_results.json`) |

The corner step passes, the new street pick included:

- one click on one piece keeps the whole street (Ithaca Rd's 8 pieces, 75'-10");
- the other street is its own 2 pieces (91'-10 3/8"), and neither runs round the corner;
- answering No drops both streets' lines.

Esc at the click prompt (which now cancels the pick) is not exercised by the script.

## Why the scale step fails as written (a test-script problem)

The step records labels by wrapping `ui.label_at`, but since the merge the plugin paints labels with
`ui.paint_label` and never calls `label_at`, so nothing is recorded. The labels are also placed by a timer once the
view is still, and that timer never ticks while a script runs.

The copy makes two changes:

1. After zooming, it draws one frame and calls `g.settle_labels()`.
2. It reads the labels and their leaders from the frame's own record, `STATE["drawn"][view]["labels"]`.

With that, zoomed to the lot, all five edge lengths and all four yard labels are drawn, and none at 1,500 ft.

**The one claim still failing:** "106's short 10'-4 1/8" edge keeps its length, led to it". The length is drawn,
with no leader. By eye (`scale_lot_view.png`) it sits right beside its short diagonal edge at the top left and reads
clearly as that edge's length. The shared placer only adds a leader when a label is more than 8 px from its line, so
this claim's expectation looks out of date. That is for the builder to decide.

## To an architect's eye

- **`scale_lot_view.png`** (lot zoom):
  - Every label is next to its line, and none covers another.
  - The house is still selected from the Zoom-to step, so its yellow outline and the gumball's arrows and plane
    handle clutter the plan; the rear yard label crosses the gumball's plane handle.
  - The northeast side yard label ("✕ … 7'-0", needs 10'-0"") is led to its line.
- **`corner.jpg`:** while the second street is picked, the panel's last line and Rhino's command line both say
  "Street 2: 2 lot-line pieces, 91'-10 3/8" so far — Enter when done". The plan shows each street's line.
  - The panel's results list is scrolled so that its first visible row ("Northeast … short") is cut at the top.
- **`box_box.png`** (no lot): the box clearly says "no lot yet: draw it, or pick a closed outline on the Site
  layer", with Draw my lot…, and Draw is off until a district is picked.
  - It already asks "? Does this lot face two streets?" before any lot exists.
